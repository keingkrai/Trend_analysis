# -*- coding: utf-8 -*-
"""
🆕 (2026-10-28) กล่อง "คนกำลังค้นหาอะไร" ในหน้าแรกของแต่ละเทรนด์ (phase6_pdf_report/trend_talk.py) - LLM แบ่งกลุ่มคำค้นจริง โค้ดตรวจทุกคำค้นที่อ้าง
ไม่ยิง API (LLM ปลอม)

รัน: pytest main/tool/tests/test_trend_talk.py -v
"""
import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TOOL_DIR = TESTS_DIR.parent
for _p in (TOOL_DIR, TOOL_DIR / "phase6_pdf_report"):
    sys.path.insert(0, str(_p))

import trend_talk as tt  # noqa: E402

SEARCHES = ["how to fix frizzy hair", "how to stop hair loss", "ทรง ผม 2026", "สี ผม 2026", "best deep conditioners", "hairstyle analysis"]
GOOD = {"points": [
    {"topic_en": "2026 hairstyles and hair colors", "topic_th": "ทรงผมและสีผมปี 2026", "searches": ["ทรง ผม 2026", "rising searches: สี ผม 2026"]},
    {"topic_en": "fixing hair problems", "topic_th": "แก้ปัญหาเส้นผม", "searches": ["How to  fix frizzy hair", "how to stop hair loss", "ทรง ผม 2026"]}]}


def test_validate_keeps_only_real_searches_as_written_in_the_list_and_never_reuses_one():
    out = tt.validate_talk(GOOD, SEARCHES)
    assert out["points"][0] == {"topic": "2026 hairstyles and hair colors", "topic_th": "ทรงผมและสีผมปี 2026", "searches": ["ทรง ผม 2026", "สี ผม 2026"]}
    assert out["points"][1]["searches"] == ["how to fix frizzy hair", "how to stop hair loss"]       # ข้อความต้นฉบับจากรายการ / "ทรง ผม 2026" ใช้ซ้ำข้ามหัวข้อไม่ได้
    assert tt.validate_talk({"points": []}, SEARCHES) is None and tt.validate_talk("garbage", SEARCHES) is None and tt.validate_talk(GOOD, []) is None


def test_validate_drops_invented_searches_unsupported_numbers_quotes_and_wrong_language_topics():
    bad_search = {"points": [{"topic_en": "a topic", "topic_th": "หัวข้อ", "searches": ["clinical study on hair", "invented search"]}]}
    assert tt.validate_talk(bad_search, SEARCHES) is None                                              # ไม่มีคำค้นที่ตรวจผ่าน = ไม่มีหัวข้อ
    mixed = {"points": [
        {"topic_en": "grew 86% in a year", "topic_th": "โตขึ้น 86%", "searches": ["ทรง ผม 2026"]},                      # ตัวเลขไม่อยู่ในหลักฐาน
        {"topic_en": "people look up 'coachella 2026'", "topic_th": "ค้นหา 'coachella 2026'", "searches": ["สี ผม 2026"]},   # คำค้นในเครื่องหมายคำพูดที่ไม่มีจริง
        {"topic_en": "หัวข้อภาษาไทยในช่องอังกฤษ", "topic_th": "หัวข้อ", "searches": ["สี ผม 2026"]},
        {"topic_en": "english in thai slot", "topic_th": "english only", "searches": ["สี ผม 2026"]},
        {"topic_en": "hair styling analysis", "topic_th": "วิเคราะห์ทรงผม", "searches": ["hairstyle analysis"]}]}
    out = tt.validate_talk(mixed, SEARCHES)
    assert [p["topic"] for p in out["points"]] == ["hair styling analysis"]


def test_validate_caps_points_and_searches_per_point():
    many = {"points": [{"topic_en": f"topic {i}", "topic_th": f"หัวข้อ {i}", "searches": [SEARCHES[i]]} for i in range(5)]}
    assert len(tt.validate_talk(many, SEARCHES)["points"]) == tt.MAX_POINTS
    one = {"points": [{"topic_en": "all of it", "topic_th": "ทั้งหมด", "searches": SEARCHES}]}
    assert len(tt.validate_talk(one, SEARCHES)["points"][0]["searches"]) == tt.MAX_SEARCHES_PER_POINT


def _ctx():
    return {"trends": [{"name": "Hair", "talk_searches": SEARCHES, "talk_sources": {"n": 27, "categories": ["Beauty & Fitness"]}},
                       {"name": "Old Stream Trend"}]}   # ไม่มี talk_searches = เทรนด์ของ 3 สายเดิม


def test_describe_trends_asks_with_real_searches_only_caches_and_falls_back_to_examples():
    prompts, answers = [], [GOOD]

    def llm(system, user, max_tokens=0):
        prompts.append((system, user))
        return json.dumps(answers[0])

    ctx, cache, quiet = _ctx(), {}, []
    assert tt.describe_trends(ctx, cache, llm_call=llm, log=quiet.append) == {"llm": 1}
    t = ctx["trends"][0]["talk"]
    assert t["n"] == 27 and t["categories"] == ["Beauty & Fitness"] and len(t["points"]) == 2 and t["examples"] == SEARCHES
    assert "talk" not in ctx["trends"][1] and len(prompts) == 1 and prompts[0][0] == tt.SYSTEM_PROMPT_TALK
    assert "Hair" not in prompts[0][1] and "27" not in prompts[0][1] and '"' not in prompts[0][1]       # ไม่ส่งชื่อเทรนด์/ข้อความตีความ/ตัวเลขของโค้ด และไม่มีเครื่องหมายคำพูดคู่
    assert "ทรง ผม 2026 | สี ผม 2026" in prompts[0][1]
    # cache: ข้อมูลเดิม = ไม่เรียกซ้ำ ; คำค้นเปลี่ยน = เรียกใหม่
    ctx2 = _ctx()
    assert tt.describe_trends(ctx2, cache, llm_call=None) == {"llm (cached)": 1} and ctx2["trends"][0]["talk"]["points"] == t["points"]
    ctx3 = _ctx()
    ctx3["trends"][0]["talk_searches"] = SEARCHES[:4]
    assert tt.describe_trends(ctx3, cache, llm_call=llm, log=quiet.append) == {"llm": 1} and len(prompts) == 2
    # LLM ตอบไม่ผ่านการตรวจ (ถามซ้ำ 2 ครั้ง) / ไม่มี LLM = ตัวอย่างคำค้นล้วน ไม่มีประโยคอธิบาย
    answers[0] = {"points": [{"topic_en": "x", "topic_th": "ก", "searches": ["invented"]}]}
    ctx4 = _ctx()
    n_before = len(prompts)
    assert tt.describe_trends(ctx4, {}, llm_call=llm, log=quiet.append) == {"examples only": 1} and len(prompts) == n_before + 2
    assert ctx4["trends"][0]["talk"]["points"] == [] and ctx4["trends"][0]["talk"]["examples"] == SEARCHES
    ctx5 = _ctx()
    assert tt.describe_trends(ctx5, {}, llm_call=None) == {"examples only": 1} and ctx5["trends"][0]["talk"]["points"] == []
    assert any("แสดงเฉพาะตัวอย่างคำค้น" in m for m in quiet)
