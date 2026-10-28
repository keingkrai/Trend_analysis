# -*- coding: utf-8 -*-
"""
⑯ PDF Report — แต่ละเทรนด์ผูกกับแรงขับ STEPIC ด้านไหน และตอบกลุ่มผู้บริโภค (persona) กลุ่มไหน
-> หน้า heatmap เทรนด์ x (6 แรงขับ + persona) (feedback 2026-09-28: เปลี่ยนหน้าตัวหนังสือเป็นภาพ - หน้า STEPIC และ
Personas เดิมเป็นข้อความระดับตลาด ไม่บอกว่าเกี่ยวกับเทรนด์ไหน)

ให้ LLM ตัดสินต่อช่องเป็น 3 ระดับ (2 = เชื่อมโยงหลัก, 1 = เกี่ยวข้อง, 0 = ไม่เห็นความเชื่อมโยงในข้อมูล) พร้อมหลักฐานสั้นๆ
จากข้อมูลที่ส่งไป - ไม่ขอตัวเลขคะแนน (หลักเดียวกับ Longevity v2: LLM ให้ verdict โค้ดรวมผล) ช่องที่ระดับ > 0 แต่ไม่มี
หลักฐานถูกปรับเป็น 0 (QA ข้อ 3 ของ Longevity v2) - ไม่มี LLM -> ไม่มีหน้านี้ (ไม่เดาความเชื่อมโยงด้วยกฎ)

เรียก LLM เทรนด์ละ 1 ครั้ง ผลเป็นภาษาอังกฤษ (หลักฐานไม่แสดงในรายงาน เก็บใน phase6_report_context.json ไว้ตรวจย้อนหลัง)
cache ที่ไฟล์ภาษาอังกฤษ (phase6_report_enrichment.json) คีย์ "links" - ไม่ import bootstrap (เทสได้ไม่ยิง API)
"""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from enrich import _clean, build_input, input_hash
from report_data import has_thai

PROMPT_VERSION_LINKS = 1
LEVELS = (0, 1, 2)
MAX_EVIDENCE_WORDS = 30

SYSTEM_PROMPT_LINKS = """You map ONE consumer trend to the macro forces and the consumer personas of a trend report.
You receive the trend (name, English context and a profile written in Thai), the report's six STEPIC forces and its
emerging consumer personas.

For every force and every persona give a level:
  2 = main link: the trend's own input clearly depends on this force / is clearly built for this persona
  1 = supporting link: related, but not central
  0 = no clear link in the input
Judge only from the text given - no outside knowledge. For level 1 or 2, "evidence" names the specific part of the
trend input that makes the link, in at most 25 English words. For level 0, "evidence" is "". Use level 2 sparingly.
No Thai characters in the answer.

Return JSON only:
{"stepic": {"<force exactly as given>": {"level": 0, "evidence": ""}, ... all six forces ...},
 "personas": [{"level": 0, "evidence": ""}, ... one per persona, in the same order ...]}"""

# 🆕 (2026-10-28) รอบสาย Search ไม่มี persona - ถามเฉพาะแรงขับ (ไม่มีคีย์ personas ในคำตอบ)
SYSTEM_PROMPT_LINKS_FORCES = (SYSTEM_PROMPT_LINKS
                              .replace(" and the consumer personas of a trend report", " of a trend report")
                              .replace(", the report's six STEPIC forces and its\nemerging consumer personas.", " and the report's STEPIC forces.")
                              .replace("For every force and every persona give a level:", "For every force give a level:")
                              .replace(" / is clearly built for this persona", "")
                              .split("Return JSON only:")[0]
                              + 'Return JSON only:\n{"stepic": {"<force exactly as given>": {"level": 0, "evidence": ""}, ... every force given ...}}')


def build_links_input(trend, stepic, personas):
    """ข้อมูลเทรนด์ (ชุดเดียวกับที่ใช้เรียบเรียงข้อความ) + หัวข้อ/สรุปของ 6 แรงขับ + persona - ใช้คำนวณ hash ของ cache ด้วย"""
    return {
        "trend": build_input(trend),
        "stepic_forces": [{"force": s["dimension"], "headline": _clean(s.get("headline")), "summary": _clean(s.get("body"))}
                          for s in stepic],
        "personas": [{k: _clean(p.get(k)) for k in ("name", "description", "value_driver")} for p in personas],
    }


def _cell(raw):
    """{level, evidence} ที่ผ่านการตรวจ หรือ None - ระดับ > 0 ที่ไม่มีหลักฐาน -> 0, หลักฐานยาวเกินตัดที่จำนวนคำ"""
    if not isinstance(raw, dict):
        return None
    try:
        level = int(raw.get("level"))
    except (TypeError, ValueError):
        return None
    evidence = _clean(raw.get("evidence"))
    if level not in LEVELS or has_thai(evidence):
        return None
    if not level or not evidence:
        return {"level": 0, "evidence": ""}
    return {"level": level, "evidence": " ".join(evidence.split()[:MAX_EVIDENCE_WORDS])}


def validate_links(parsed, payload):
    """ต้องครบทุกแรงขับ (ชื่อตรงตามที่ส่งไป) และ persona ครบจำนวน ทุกช่องผ่าน _cell - คืนผลที่เก็บกวาดแล้ว หรือ None"""
    if not isinstance(parsed, dict) or not isinstance(parsed.get("stepic"), dict):
        return None
    stepic = {}
    for force in (s["force"] for s in payload["stepic_forces"]):
        cell = _cell(parsed["stepic"].get(force))
        if cell is None:
            return None
        stepic[force] = cell
    raw_personas = parsed.get("personas") if payload["personas"] else []
    if not isinstance(raw_personas, list) or len(raw_personas) != len(payload["personas"]):
        return None
    personas = [_cell(p) for p in raw_personas]
    if any(p is None for p in personas):
        return None
    return {"stepic": stepic, "personas": personas}


def summarize_links(trends, forces, n_personas):
    """จำนวนเทรนด์ต่อคอลัมน์: main = ระดับ 2, any = ระดับ 1 ขึ้นไป (แถวสรุปท้าย heatmap)"""
    linked = [t["links"] for t in trends if t.get("links")]

    def count(levels):
        return {"main": sum(1 for v in levels if v == 2), "any": sum(1 for v in levels if v >= 1)}

    return {"stepic": {f: count([l["stepic"][f]["level"] for l in linked]) for f in forces},
            "personas": [count([l["personas"][i]["level"] for l in linked]) for i in range(n_personas)],
            "n_trends": len(linked)}


def link_trends(ctx, cache, llm_call=None, parse=json.loads, refresh=False, max_workers=4, log=print):
    """เติม t["links"] = {"stepic": {แรงขับ: {level, evidence}}, "personas": [{level, evidence}, ...]} ให้เทรนด์ที่ได้ผล
    และ ctx["links_summary"] (ถ้ามีอย่างน้อย 1 เทรนด์) - รายงานไม่มี STEPIC หรือ persona -> ไม่ทำอะไร
    cache: cache ภาษาอังกฤษ คีย์ "links" - คืนสรุปจำนวนต่อแหล่ง"""
    # 🆕 (2026-10-27) แรงขับที่คำค้นไม่ยืนยัน ("No data") ไม่อยู่ใน heatmap - ไม่ให้ LLM ให้ระดับกับสิ่งที่ไม่มีข้อมูล
    stepic = [s for s in (ctx.get("stepic") or []) if not s.get("no_data")]
    personas = (ctx.get("personas") or [])[:3]
    ctx.pop("links_summary", None)
    for t in ctx["trends"]:
        t.pop("links", None)
    if not stepic:
        return {}
    store = cache.setdefault("links", {})
    todo, counts = [], {}
    for t in ctx["trends"]:
        payload = build_links_input(t, stepic, personas)
        h = input_hash(payload, PROMPT_VERSION_LINKS)
        cached = store.get(t["name"])
        output = validate_links(cached.get("output"), payload) if cached and cached.get("input_hash") == h else None
        if output and not refresh:
            t["links"] = output
            counts["llm (cached)"] = counts.get("llm (cached)", 0) + 1
        else:
            todo.append((t, payload, h))

    def _one(job):
        # ถามซ้ำ 1 ครั้งถ้าคำตอบไม่ผ่านการตรวจ - รอบ 082438 มี 1 ใน 10 เทรนด์ที่ครั้งแรกไม่ผ่าน แต่ถามใหม่ด้วยข้อมูลเดิมผ่าน
        t, payload, h = job
        err = None
        for _ in range(2):
            try:
                content = llm_call(SYSTEM_PROMPT_LINKS if payload["personas"] else SYSTEM_PROMPT_LINKS_FORCES,
                                   json.dumps(payload, ensure_ascii=False, indent=1), max_tokens=1500)
                output = validate_links(parse(content), payload)
                if output:
                    return t, h, output, None
            except Exception as e:  # noqa: BLE001 - เทรนด์เดียวพังต้องไม่ทำให้ทั้งรายงานพัง
                err = e
        return t, h, None, err

    if todo and llm_call is not None:
        log(f"  จับคู่เทรนด์กับแรงขับ STEPIC{' / persona' if personas else ''} ด้วย LLM {len(todo)} เทรนด์...")
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for t, h, output, err in pool.map(_one, todo):
                if output:
                    store[t["name"]] = {"input_hash": h, "output": output,
                                        "created_at": datetime.now().isoformat(timespec="seconds")}
                    t["links"] = output
                    counts["llm"] = counts.get("llm", 0) + 1
                else:
                    why = f"{type(err).__name__}: {str(err)[:120]}" if err else "คำตอบไม่ผ่านการตรวจ (ขาดช่อง/ระดับผิด)"
                    log(f"  ⚠️ {t['name']}: ไม่อยู่ในหน้า heatmap - {why}")
    missing = sum(1 for t in ctx["trends"] if "links" not in t)
    if missing:
        counts["not linked"] = missing
    if any(t.get("links") for t in ctx["trends"]):
        ctx["links_summary"] = summarize_links(ctx["trends"], [s["dimension"] for s in stepic], len(personas))
    return counts
