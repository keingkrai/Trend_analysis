# -*- coding: utf-8 -*-
"""
⑯ PDF Report — กล่อง "คนกำลังค้นหาอะไร" ในหน้าแรกของแต่ละเทรนด์ (รอบสาย Search, 2026-10-28)
บอกว่าคำค้นที่ประกอบเป็นเทรนด์นี้เกี่ยวกับอะไร แบ่งเป็น 1-3 หัวข้อ แต่ละหัวข้อมีประโยคอธิบายสั้นๆ + คำค้นจริงที่เป็นหลักฐาน

หลัก "ใช้เฉพาะสิ่งที่คำค้นยืนยัน":
  - LLM เห็นเฉพาะคำค้นจริงของเทรนด์ (ไม่เห็นชื่อเทรนด์ ไม่เห็นข้อความตีความของสาย) แบ่งกลุ่มและเขียนประโยคหัวข้อ 2 ภาษาในครั้งเดียว
  - โค้ดตรวจ: คำค้นที่ LLM ยกมาต้องมีอยู่จริงในชุดหลักฐาน (ใช้ข้อความต้นฉบับจากรายการ ไม่ใช่ที่ LLM พิมพ์), ใช้ซ้ำข้ามหัวข้อไม่ได้,
    ตัวเลขและคำค้นในเครื่องหมายคำพูดเดี่ยวในประโยคต้องอยู่ในหลักฐาน, ประโยคอังกฤษห้ามมีอักษรไทย / ไทยต้องมีอักษรไทย; หัวข้อที่ไม่มีคำค้นที่ตรวจผ่านถูกตัด
  - LLM ใช้ไม่ได้ (ไม่มีคีย์ / ตอบไม่ผ่านการตรวจ) = แสดงเฉพาะ "ตัวอย่างคำค้น" จากหลักฐาน ไม่มีประโยคอธิบาย (ไม่เดา)
จำนวนคำค้นและหมวดของ Google ต่อเทรนด์มาจากโค้ด (search_talk.trend_sources)

cache ที่ไฟล์ภาษาอังกฤษ (phase6_report_enrichment.json) คีย์ "talk" - ไม่ import bootstrap (เทสได้ไม่ยิง API)
"""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from common.evidence_gate import norm, numbers_supported, quotes_supported, sanitize, verify_snippets
from enrich import _clean, input_hash
from plain_text import plain_cleanup
from report_data import has_thai

PROMPT_VERSION_TALK = 1
MAX_POINTS = 3
MAX_SEARCHES_PER_POINT = 3
N_FALLBACK_EXAMPLES = 6

SYSTEM_PROMPT_TALK = """You explain what people are searching for inside ONE trend of a beauty trend report, using ONLY the EVIDENCE block:
the rising Google searches that make up the trend. The trend's own name is not given on purpose. You have no other knowledge for this task.

Group the searches into 1 to 3 topics, biggest group first. If the searches share one subject, return one topic. For each topic give:
- "topic_en": at most 12 words of plain English saying what these searches are about, in their own terms. If they are names of events, shows,
  people or places, say that. Call a search a product or a problem only when the search itself names it. Do not say why people search or what
  they feel or want. Do not add ingredients, brands, claims, numbers or places that are not in the evidence. Do not use may, might, could or should.
- "topic_th": the same sentence in plain Thai (everyday words, no jargon).
- "searches": 1 to 3 searches copied exactly from the evidence (each at most 15 words, never containing a double quote) that belong to the topic.
  Use each search once.
Return VALID JSON only: {"points": [{"topic_en": "...", "topic_th": "...", "searches": ["..."]}]}"""


def evidence_text(searches):
    """ชุดหลักฐานของเทรนด์ 1 ตัว = คำค้นจริง (ไม่มีเครื่องหมายคำพูดคู่)"""
    return sanitize("EVIDENCE\nrising searches: " + " | ".join(searches))


def build_talk_input(trend):
    return {"searches": list(trend.get("talk_searches") or [])}


def _original(quote, searches):
    """ข้อความที่ LLM คัดลอกมา -> คำค้นต้นฉบับในรายการ (ไม่ใช่ที่ LLM พิมพ์ - ตัดป้ายหัวข้อ/ช่องว่างที่เกินมา) หรือ None"""
    q = norm(quote)
    hits = [s for s in searches if norm(s) and norm(s) in q]
    return max(hits, key=len) if hits else None


def validate_talk(parsed, searches):
    """คำตอบดิบของ LLM -> {"points": [{topic, topic_th, searches}]} ที่ผ่านการตรวจ หรือ None (ไม่มีหัวข้อที่ใช้ได้)"""
    if not isinstance(parsed, dict) or not isinstance(parsed.get("points"), list) or not searches:
        return None
    ev_norm = norm(evidence_text(searches))
    used, points = set(), []
    for p in parsed["points"]:
        if not isinstance(p, dict):
            continue
        en = plain_cleanup(_clean(p.get("topic_en")), "en")
        th = plain_cleanup(_clean(p.get("topic_th")), "th")
        if not en or not th or has_thai(en) or not has_thai(th):
            continue
        if not all(numbers_supported(t, ev_norm) and quotes_supported(t, ev_norm) for t in (en, th)):
            continue
        shown = []
        for q in verify_snippets(p.get("searches"), ev_norm):
            s = _original(q, searches)
            if s and s not in used and s not in shown and len(shown) < MAX_SEARCHES_PER_POINT:
                shown.append(s)
        if shown:
            used.update(shown)
            points.append({"topic": en, "topic_th": th, "searches": shown})
    return {"points": points[:MAX_POINTS]} if points else None


def _as_raw(stored):
    """ผลที่เก็บใน cache (topic / topic_th / searches ที่ตรวจแล้ว) -> รูปเดียวกับคำตอบดิบของ LLM เพื่อตรวจซ้ำด้วย validate_talk ก่อนใช้ (หลักฐานเปลี่ยน = ใช้ไม่ได้)"""
    points = (stored or {}).get("points") if isinstance(stored, dict) else None
    return {"points": [{"topic_en": p.get("topic"), "topic_th": p.get("topic_th"), "searches": p.get("searches")}
                       for p in points or [] if isinstance(p, dict)]}


def describe_trends(ctx, cache, llm_call=None, parse=json.loads, refresh=False, max_workers=4, log=print):
    """เติม t["talk"] = {"n", "categories", "points": [{topic, topic_th, searches}], "examples": [คำค้น]} ให้เทรนด์ของรอบสาย Search
    (เทรนด์ที่มี talk_searches) - points ว่าง = ไม่มีประโยคอธิบายที่ผ่านการตรวจ ใช้ examples (คำค้นจริงล้วน) แทน
    cache: cache ภาษาอังกฤษ คีย์ "talk" - คืนสรุปจำนวนต่อแหล่ง"""
    store = cache.setdefault("talk", {})
    todo, counts = [], {}
    trends = [t for t in ctx["trends"] if t.get("talk_searches")]
    for t in trends:
        src = t.get("talk_sources") or {}
        t["talk"] = {"n": src.get("n"), "categories": list(src.get("categories") or []), "points": [],
                     "examples": list(t["talk_searches"][:N_FALLBACK_EXAMPLES])}
        payload = build_talk_input(t)
        h = input_hash(payload, PROMPT_VERSION_TALK)
        cached = store.get(t["name"])
        output = validate_talk(_as_raw(cached.get("output")), payload["searches"]) if cached and cached.get("input_hash") == h else None
        if output and not refresh:
            t["talk"]["points"] = output["points"]
            counts["llm (cached)"] = counts.get("llm (cached)", 0) + 1
        else:
            todo.append((t, payload, h))

    def _one(job):
        t, payload, h = job
        err = None
        for _ in range(2):   # ถามซ้ำ 1 ครั้งถ้าคำตอบไม่ผ่านการตรวจ
            try:
                content = llm_call(SYSTEM_PROMPT_TALK, evidence_text(payload["searches"]), max_tokens=1200)
                output = validate_talk(parse(content), payload["searches"])
                if output:
                    return t, h, output, None
            except Exception as e:  # noqa: BLE001 - เทรนด์เดียวพังต้องไม่ทำให้ทั้งรายงานพัง
                err = e
        return t, h, None, err

    if todo and llm_call is not None:
        log(f"  อธิบายว่าคนกำลังค้นหาอะไรในแต่ละเทรนด์ด้วย LLM {len(todo)} เทรนด์...")
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for t, h, output, err in pool.map(_one, todo):
                if output:
                    store[t["name"]] = {"input_hash": h, "output": output, "created_at": datetime.now().isoformat(timespec="seconds")}
                    t["talk"]["points"] = output["points"]
                    counts["llm"] = counts.get("llm", 0) + 1
                else:
                    why = f"{type(err).__name__}: {str(err)[:120]}" if err else "คำตอบไม่ผ่านการตรวจ"
                    log(f"  ⚠️ {t['name']}: แสดงเฉพาะตัวอย่างคำค้น - {why}")
    missing = sum(1 for t in trends if not t["talk"]["points"])
    if missing:
        counts["examples only"] = missing
    return counts
