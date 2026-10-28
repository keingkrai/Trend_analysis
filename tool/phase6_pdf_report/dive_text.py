# -*- coding: utf-8 -*-
"""
⑯ Category Deep-Dive — ประโยคอธิบายหัวข้อรายหมวด (LLM + ตัวตรวจ) ของส่วน "เจาะรายหมวดของ Google" (2026-10-28)
LLM เขียนประโยค 2 ภาษาจากคำค้นจริงของหัวข้อเท่านั้น (ไม่เห็นชื่อหัวข้อ/ชื่อหมวด) แล้วโค้ดตรวจ:
  - คำค้นที่ยกมาต้องมีจริงในหัวข้อ (ใช้ข้อความต้นฉบับ ไม่ใช่ที่ LLM พิมพ์)
  - ตัวเลข / ข้อความในเครื่องหมายคำพูดเดี่ยวต้องอยู่ในคำค้นของหัวข้อ (ปี 2569 ห้ามแปลงเป็น 2026)
  - ห้ามคำบอกเหตุผล/จุดประสงค์/ความรู้สึก (enrich.PURPOSE_RE) - ไม่ผ่าน = ถามซ้ำ 1 ครั้ง แล้วโชว์เฉพาะตัวอย่างคำค้นจริง
cache ที่ไฟล์ภาษาอังกฤษของรายงานหลัก (phase6_report_enrichment.json) คีย์ "dive" - ตรวจซ้ำก่อนใช้ทุกครั้ง; ไม่ import bootstrap (เทสได้ไม่ยิง API)
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from category_dive import N_SHOWN
from common.evidence_gate import norm, numbers_supported, quotes_supported, sanitize, verify_snippets
from enrich import PURPOSE_RE, _clean, _without_searches, input_hash
from plain_text import plain_cleanup
from report_data import has_thai
from trend_talk import _original, evidence_text

PROMPT_VERSION_DIVE = 1

SYSTEM_PROMPT_DIVE = """You explain groups of rising Google searches for a beauty trend report, using ONLY the EVIDENCE block.
Each topic is one group of searches. The topic's own name is not given on purpose. You have no other knowledge for this task.

For every topic return:
- "topic_en": at most 14 words of plain English saying what these searches are about, in their own terms. If they are names of events, shows,
  people, places, games or apps, say that. Call a search a product or a problem only when the search itself names it. Do not say why people
  search, what they prepare for, what they feel or want. Do not add ingredients, brands, claims, numbers or places that are not in the evidence.
  Use a number only if the searches of that topic contain it, written the same way (keep 2569 as 2569, never convert it to 2026).
  Do not use may, might, could or should.
- "topic_th": the same sentence in plain Thai (everyday words, no jargon).
- "searches": 1 to 3 searches of that topic copied exactly from the evidence (each at most 15 words, never containing a double quote).
Return VALID JSON only, one item per topic id: {"topics": [{"id": 1, "topic_en": "...", "topic_th": "...", "searches": ["..."]}]}"""

SEARCH_RETRY_DIVE = ("\n\nYour previous answer for some topics was rejected: it said why people search, what they prepare for or feel, or it quoted a "
                     "search that is not in the evidence, or it used a number (such as a year) that is not written that way in that topic's searches. "
                     "Answer these topics again and say only what the searches show.")


def build_payload(themes):
    """หัวข้อที่โชว์ของ 1 หมวด -> ข้อมูลที่ส่งให้ LLM (คำค้นจริงล้วน ไม่มีชื่อหัวข้อ/ชื่อหมวด ไม่ให้ชื่อชี้นำคำเขียน)"""
    return {"topics": [{"id": i, "searches": list(t["searches"])} for i, t in enumerate(themes, 1)]}


def _user_text(topics):
    return sanitize("EVIDENCE\n" + "\n".join(f"Topic {t['id']}\nrising searches: " + " | ".join(t["searches"]) for t in topics))


def validate_topic(item, searches):
    """คำตอบดิบของ LLM ของ 1 หัวข้อ -> {"id", "topic_en", "topic_th", "searches"} ที่ผ่านการตรวจ หรือ None"""
    if not isinstance(item, dict) or not searches:
        return None
    ev = norm(evidence_text(searches))
    en = plain_cleanup(_clean(item.get("topic_en")), "en")
    th = plain_cleanup(_clean(item.get("topic_th")), "th")
    if not en or not th or has_thai(re.sub(r"'[^']*'", " ", en)) or not has_thai(th):
        return None
    if not all(numbers_supported(t, ev) and quotes_supported(t, ev) for t in (en, th)):
        return None
    if any(rx.search(_without_searches(t, searches)) for t in (en, th) for rx in PURPOSE_RE.values()):
        return None
    shown = []
    for q in verify_snippets(item.get("searches"), ev):
        s = _original(q, searches)
        if s and s not in shown and len(shown) < N_SHOWN:
            shown.append(s)
    return {"id": item.get("id"), "topic_en": en[:1].upper() + en[1:], "topic_th": th, "searches": shown} if shown else None


def _validate_all(parsed, payload):
    """คำตอบดิบ -> {id: ผลที่ผ่าน} เฉพาะ id ที่อยู่ในข้อมูลที่ส่ง (ซ้ำ id = ใช้ตัวแรก)"""
    by_id = {t["id"]: t["searches"] for t in payload["topics"]}
    out = {}
    for item in (parsed.get("topics") if isinstance(parsed, dict) else None) or []:
        i = item.get("id") if isinstance(item, dict) else None
        if i in by_id and i not in out:
            ok = validate_topic(item, by_id[i])
            if ok:
                out[i] = ok
    return out


def _apply(themes, got):
    for i, t in enumerate(themes, 1):
        if i in got:
            t.update(topic=got[i]["topic_en"], topic_th=got[i]["topic_th"], shown=got[i]["searches"])


def describe_dive(dive, cache, llm_call=None, parse=json.loads, refresh=False, max_workers=4, log=print):
    """เติม t["topic"] / t["topic_th"] / t["shown"] ให้หัวข้อที่โชว์ของทุกหมวดที่มีหน้า - หัวข้อที่ไม่ผ่านการตรวจ: topic = None, shown = ตัวอย่างคำค้นจริง
    cache: cache ภาษาอังกฤษ คีย์ "dive" {ชื่อหมวด: {input_hash, output: [ผลที่ผ่านของแต่ละหัวข้อ]}} - คืนสรุปจำนวนต่อแหล่ง"""
    store = cache.setdefault("dive", {})
    todo, counts = [], {}
    for cat in (dive or {}).get("categories") or []:
        themes = cat["linked"] + cat["others"]
        for t in themes:
            t.update(topic=None, topic_th=None, shown=t["searches"][:N_SHOWN])
        if not themes:
            continue
        payload = build_payload(themes)
        h = input_hash(payload, PROMPT_VERSION_DIVE)
        cached = store.get(cat["name"])
        got = {}
        if cached and cached.get("input_hash") == h and not refresh:
            got = _validate_all({"topics": cached.get("output")}, payload)   # ตรวจซ้ำก่อนใช้ - หลักฐานเปลี่ยน/ตัวตรวจเข้มขึ้น = ใช้ไม่ได้
        if len(got) == len(themes):
            _apply(themes, got)
            counts["llm (cached)"] = counts.get("llm (cached)", 0) + len(themes)
        else:
            todo.append((cat, themes, payload, h, got))

    def _one(job):
        cat, themes, payload, h, got = job
        n_cached, got, err = len(got), dict(got), None
        for attempt in range(2):   # ถามซ้ำ 1 ครั้งเฉพาะหัวข้อที่ยังไม่ผ่าน
            left = [t for t in payload["topics"] if t["id"] not in got]
            if not left:
                break
            try:
                content = llm_call(SYSTEM_PROMPT_DIVE + (SEARCH_RETRY_DIVE if attempt else ""), _user_text(left), max_tokens=2500)
                got.update(_validate_all(parse(content), {"topics": left}))
            except Exception as e:  # noqa: BLE001 - หมวดเดียวพังต้องไม่ทำให้ทั้งรายงานพัง
                err = e
        return cat, themes, h, got, err, n_cached

    if todo and llm_call is not None:
        log(f"  อธิบายหัวข้อรายหมวดด้วย LLM {len(todo)} หมวด...")
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for cat, themes, h, got, err, n_cached in pool.map(_one, todo):
                _apply(themes, got)
                if got:
                    store[cat["name"]] = {"input_hash": h, "output": [got[i] for i in sorted(got)],   # เก็บเท่าที่ผ่าน - รอบหน้าถามเฉพาะหัวข้อที่เหลือ
                                          "created_at": datetime.now().isoformat(timespec="seconds")}
                if n_cached:
                    counts["llm (cached)"] = counts.get("llm (cached)", 0) + n_cached
                if len(got) > n_cached:
                    counts["llm"] = counts.get("llm", 0) + len(got) - n_cached
                if len(got) < len(themes):
                    why = f"{type(err).__name__}: {str(err)[:120]}" if err else "คำตอบไม่ผ่านการตรวจ"
                    log(f"  ⚠️ {cat['name']}: แสดงเฉพาะตัวอย่างคำค้น {len(themes) - len(got)} หัวข้อ - {why}")
                    counts["examples only"] = counts.get("examples only", 0) + len(themes) - len(got)
    elif todo:
        for cat, themes, payload, h, got in todo:   # ไม่มี LLM: ใช้เท่าที่ cache ผ่าน ที่เหลือเป็นตัวอย่างคำค้น
            _apply(themes, got)
            if got:
                counts["llm (cached)"] = counts.get("llm (cached)", 0) + len(got)
            counts["examples only"] = counts.get("examples only", 0) + len(themes) - len(got)
    return counts
