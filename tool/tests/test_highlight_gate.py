# -*- coding: utf-8 -*-
"""
🆕 (2026-10-27) เกตหลักฐานของ ⑪ (phase3_supply_layer/highlight_evidence.py) และของข้อความต่อเทรนด์ใน ⑯ (enrich.py) สำหรับเทรนด์ของสาย Search
ไม่เรียก API - ตรวจว่ามิติที่ไม่มีข้อความยืนยันกลายเป็น "ข้อมูลไม่พอ" และตัวเลข/ข้อความที่อ้างต้องอยู่ในหลักฐานจริง

รัน: pytest main/tool/tests/test_highlight_gate.py -v
"""
import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TOOL_DIR = TESTS_DIR.parent
for _p in (TOOL_DIR, TOOL_DIR / "phase3_supply_layer", TOOL_DIR / "phase6_pdf_report"):
    sys.path.insert(0, str(_p))

import highlight_evidence as he  # noqa: E402
import enrich  # noqa: E402
from common import evidence_gate as eg  # noqa: E402

ROW = {"Trend Name": "Hair Styling and Repair Care", "Places": ["TH", "WW"],
       "Source Themes": [{"category": "Beauty & Fitness", "theme": "Hair", "evidence": ["how to fix frizzy hair", "ทรง ผม ชาย 2026"]}],
       "Members": "how to fix frizzy hair, ทรง ผม ชาย 2026, anti dandruff shampoo, best hair serum",
       "Key Benefits": "frizz control, hair repair, dandruff control", "Target": "Consumers who want to feel confident"}
EVIDENCE = he.build_user_content(ROW)


def test_evidence_contains_real_searches_and_places_but_not_the_pipeline_written_interpretation():
    assert "how to fix frizzy hair | ทรง ผม ชาย 2026 | anti dandruff shampoo | best hair serum" in EVIDENCE
    assert "places where its searches rise: TH, WW" in EVIDENCE
    assert "dandruff control" not in EVIDENCE and "feel confident" not in EVIDENCE      # ข้อความที่ LLM เขียนไว้ในสายไม่ใช่หลักฐาน
    assert '"' not in EVIDENCE


def _raw(**over):
    base = {"trend": "x", "trend_type": "สินค้า", "attribute": "เซรั่มบำรุงผม", "functional_consequence": "จัดการผมชี้ฟูให้เรียบ",
            "psychosocial_consequence": "มั่นใจเมื่อออกสังคม", "job_to_be_done": "แก้ปัญหาผมชี้ฟูและจัดทรงผม",
            "point_of_difference": "ข้อมูลไม่พอ", "point_of_parity": "ข้อมูลไม่พอ",
            "evidence": {"attribute": ["best hair serum"], "functional_consequence": ["how to fix frizzy hair"],
                         "psychosocial_consequence": [], "job_to_be_done": ["rising searches: how to fix frizzy hair", "ทรง ผม ชาย 2026"],
                         "point_of_difference": [], "point_of_parity": []}}
    return {**base, **over}


def test_fields_without_a_verified_quote_become_not_enough_info_and_reasons_are_recorded():
    p = he.gate_profile(_raw(), EVIDENCE)
    assert p["attribute"] == "เซรั่มบำรุงผม" and p["functional_consequence"] == "จัดการผมชี้ฟูให้เรียบ"
    assert p["job_to_be_done"] == "แก้ปัญหาผมชี้ฟูและจัดทรงผม"
    assert p["psychosocial_consequence"] == he.NO_INFO and p["_audit"] == {"psychosocial_consequence": "no verified quote"}
    assert p["evidence"]["job_to_be_done"][-1] == "ทรง ผม ชาย 2026" and len(p["evidence"]["job_to_be_done"]) == 2
    assert he.matchable_fields(p) == ["functional_consequence", "job_to_be_done"]


def test_invented_quotes_numbers_and_quoted_searches_are_removed():
    bad = _raw(attribute="ซีรั่ม 99% ลดรังแค", evidence={"attribute": ["clinical study on dandruff"], "functional_consequence": ["how to fix frizzy hair"]},
               functional_consequence="ค้นหา 'coachella 2026' เพื่อจัดทรง")
    p = he.gate_profile(bad, EVIDENCE)
    assert p["attribute"] == he.NO_INFO and p["functional_consequence"] == he.NO_INFO
    assert set(p["_audit"]) == {"attribute", "functional_consequence", "psychosocial_consequence", "job_to_be_done"}
    assert p["_audit"]["functional_consequence"] == "number or quoted search not in the evidence"


def test_channel_trend_keeps_no_product_benefits_and_garbage_answers_are_all_not_enough_info():
    p = he.gate_profile(_raw(trend_type="ช่องทาง / พฤติกรรมการซื้อ"), EVIDENCE)
    assert p["trend_type"] == he.TREND_TYPE_CHANNEL
    assert all(p[f] == he.NO_INFO for f in ("functional_consequence", "psychosocial_consequence", "job_to_be_done", "point_of_difference"))
    assert he.matchable_fields(he.gate_profile("garbage", EVIDENCE)) == []
    assert he.parse_usable({"trend_type": "สินค้า", "attribute": "x"}) and not he.parse_usable({"error": "x"})


def test_report_trend_input_uses_real_searches_and_gated_profile_not_pipeline_written_text():
    trend = {"name": "Hair Styling and Repair Care", "rising_searches": eg.trend_searches(ROW, 12),
             "target": "People who search for this in Thailand and worldwide", "key_ingredients": "", "key_benefits": "",
             "analysis": {"executive_summary": "Consumers feel confident", "expected_search_growth_pct": {"year_3": 21.7}},
             "profile": {"attribute": "เซรั่มบำรุงผม", "psychosocial_consequence": "ข้อมูลไม่พอ", "functional_consequence": "จัดการผมชี้ฟูให้เรียบ"}}
    payload = enrich.build_input(trend)
    assert payload["rising_searches"][0] == "how to fix frizzy hair"
    assert payload["context_en"]["expected_search_growth_pct_vs_last_12_months"] == {"year_3": 21.7}
    assert set(payload["profile_th"]) == {"attribute", "functional_consequence"}
    assert "confident" not in str(payload) and enrich.is_search_trend(payload)
    assert enrich.fallback_texts(trend)["headline"] == "Hair Styling and Repair Care"
    # เทรนด์ของ 3 สายเดิม (ไม่มี rising_searches) ยังใช้ข้อมูลเดิมครบ
    assert "key_ingredients" in enrich.build_input({"name": "Old", "analysis": {}, "profile": {}, "key_ingredients": "retinol"})["context_en"]


def test_report_text_with_a_number_not_in_the_input_is_rejected_for_search_trends_only():
    payload = {"trend_name": "x", "rising_searches": ["haze psi"], "context_en": {"expected_search_growth_pct_vs_last_12_months": {"year_3": 21.7}}}
    ok = {"headline": "Searches are expected to grow 21.7% by year 3.", "trend": "t", "insight": "i"}
    bad = {**ok, "headline": "Searches are expected to grow 86% by year 3."}
    assert enrich.guard_search_numbers(ok, payload) == ok and enrich.guard_search_numbers(bad, payload) is None
    assert enrich.guard_search_numbers(bad, {"trend_name": "old"}) == bad          # รอบ 3 สายเดิมไม่ถูกตรวจแบบนี้


def test_matching_text_appends_only_verified_searches_of_matchable_fields_and_can_be_switched_off(monkeypatch):
    import match_supply  # noqa: E402
    profile = {"functional_consequence": "แก้ปัญหาผมฟู", "psychosocial_consequence": "ข้อมูลไม่พอ", "job_to_be_done": "เลือกทรงผม",
               "point_of_difference": "ข้อมูลไม่พอ",
               "evidence": {"functional_consequence": ["how to fix frizzy hair"], "job_to_be_done": ["How to fix  frizzy hair", "ทรง ผม ชาย 2026"],
                            "attribute": ["best hair serum"], "psychosocial_consequence": ["miss universe thailand 2026"]}}
    monkeypatch.delenv("TREND_MATCH_QUOTES", raising=False)
    text = match_supply.build_trend_matchable_text(profile)
    assert text == "แก้ปัญหาผมฟู เลือกทรงผม Searches: how to fix frizzy hair; ทรง ผม ชาย 2026"      # ซ้ำถูกตัด / attribute และมิติที่ไม่มีข้อมูลไม่เข้า
    monkeypatch.setenv("TREND_MATCH_QUOTES", "0")
    assert match_supply.build_trend_matchable_text(profile) == "แก้ปัญหาผมฟู เลือกทรงผม"
    monkeypatch.delenv("TREND_MATCH_QUOTES")
    legacy = {k: v for k, v in profile.items() if k != "evidence"}                                  # เทรนด์ 3 สายเดิมไม่มี evidence - ข้อความเหมือนเดิม
    assert match_supply.build_trend_matchable_text(legacy) == "แก้ปัญหาผมฟู เลือกทรงผม"
    empty = {"functional_consequence": "ข้อมูลไม่พอ", "evidence": {"functional_consequence": ["x"]}}
    assert match_supply.build_trend_matchable_text(empty) == ""                                      # ⑪ ยังตัดเทรนด์ที่ทุกช่องไม่มีข้อมูลได้เหมือนเดิม


# 🆕 (2026-10-28) ตัวกันคำบอกเหตุผล/จุดประสงค์/ความรู้สึก/การวางแผนในข้อความต่อเทรนด์ของสาย Search (enrich.guard_search_purpose)
PAYLOAD = {"trend_name": "x", "rising_searches": ["how to fix frizzy hair", "miss universe thailand 2026", "ทรง ผม 2026"], "context_en": {}}


def _out(**over):
    base = {"headline": "People search for 2026 hairstyles and miss universe thailand 2026.", "trend": "Searches cover shampoo and styling.",
            "insight": "They search for ways to fix frizzy hair.", "target": ""}
    return {**base, **over}


def test_purpose_guard_rejects_reasons_plans_and_feelings_but_not_the_searches_themselves():
    ok = _out()
    assert enrich.guard_search_purpose(ok, PAYLOAD) == ok                                         # "how to fix..." อยู่ในคำค้นจริง - ไม่ใช่เหตุผล
    for field, text in (("headline", "People search for pageants to prepare for the big stage."),
                        ("insight", "They want it because it makes them feel confident."),
                        ("trend", "Searches are a form of planning ahead."),
                        ("insight", "Searches rise in order to cover national events."),
                        ("headline", "คนไทยค้นหางานประกวดเพื่อเตรียมตัวล่วงหน้า"),
                        ("insight", "ผู้คนรู้สึกมั่นใจเมื่อมีข้อมูล"),
                        ("trend", "การค้นหาแสดงถึงการวางแผน")):
        assert enrich.guard_search_purpose(_out(**{field: text}), PAYLOAD) is None, text
    # คำค้นจริงและข้อความในเครื่องหมายคำพูดเดี่ยวมีคำเหล่านี้ได้ตามต้นฉบับ / "เพื่อน" ไม่ใช่ "เพื่อ"
    assert enrich.guard_search_purpose(_out(insight="People search 'how to feel better' and 'tips because why'."), PAYLOAD) is not None
    assert enrich.guard_search_purpose(_out(headline="คนค้นหา ทรง ผม 2026 กับเพื่อนๆ"), PAYLOAD) is not None
    assert enrich.guard_search_purpose(None, PAYLOAD) is None
    old = {"trend_name": "old", "context_en": {}}                                                 # เทรนด์ของ 3 สายเดิมไม่ถูกตรวจ
    assert enrich.guard_search_purpose(_out(headline="to prepare because of the feel"), old) is not None


def test_search_trend_text_is_asked_again_with_the_reason_and_falls_back_to_real_searches():
    trend = {"name": "Hair", "rising_searches": PAYLOAD["rising_searches"], "target": "People who search for this", "analysis": {}, "profile": {},
             "key_ingredients": "", "key_benefits": "", "products": []}
    answers, prompts = [], []

    def llm(system, user, max_tokens=None):
        prompts.append(system)
        return json.dumps(answers.pop(0))

    bad = _out(headline="People search to prepare for events.")
    good = _out()
    answers[:] = [bad, good]
    trends = [dict(trend)]
    _, counts = enrich.enrich_trends(trends, {}, llm_call=llm, max_workers=1, log=lambda *_: None)
    assert counts == {"llm": 1} and len(prompts) == 2 and enrich.SEARCH_RETRY not in prompts[0] and enrich.SEARCH_RETRY in prompts[1]
    assert trends[0]["text"]["headline"] == good["headline"]
    answers[:] = [bad, bad]                                                                        # ถามซ้ำแล้วยังไม่ผ่าน = แทนเฉพาะช่องที่ไม่ผ่านด้วยข้อความสำรองจากคำค้นจริง ช่องที่ผ่านใช้ต่อ
    trends = [dict(trend)]
    cache, quiet = {}, []
    _, counts = enrich.enrich_trends(trends, cache, llm_call=llm, max_workers=1, log=quiet.append)
    text = trends[0]["text"]
    assert counts == {"llm": 1} and text["headline"] == "Hair" and text["trend"] == bad["trend"] and text["insight"] == bad["insight"]
    assert any("แทนช่อง headline" in m for m in quiet) and cache["items"]["Hair"]["output"]["headline"] == "Hair"
    again = [dict(trend)]                                                                          # ข้อความที่แทนแล้วผ่านการตรวจเมื่ออ่านจาก cache
    assert enrich.enrich_trends(again, cache, llm_call=None, log=lambda *_: None)[1] == {"llm (cached)": 1}
    answers[:] = [{"headline": "x"}, {"headline": "x"}]                                            # โครงไม่ครบทั้ง 2 ครั้ง = ข้อความสำรองทั้งชุดจากคำค้นจริง
    trends = [dict(trend)]
    _, counts = enrich.enrich_trends(trends, {}, llm_call=llm, max_workers=1, log=lambda *_: None)
    assert counts == {"fallback": 1} and "how to fix frizzy hair" in trends[0]["text"]["trend"]
    # คำค้นภาษาไทยในเครื่องหมายคำพูดเดี่ยวยกมาในฉบับอังกฤษได้
    thai_quote = _out(trend="People search 'ปากกา ลด น้ำหนัก' and similar terms.")
    assert enrich.validate(thai_quote) is not None and enrich.validate(_out(trend="ผู้ใช้ค้นหาปากกา")) is None
    old = {"name": "Old", "analysis": {}, "profile": {}, "key_ingredients": "retinol", "key_benefits": "", "target": "x", "products": []}
    answers[:] = [bad]                                                                             # รอบ 3 สายเดิม: ถามครั้งเดียว ไม่ตรวจคำบอกเหตุผล
    n = len(prompts)
    enrich.enrich_trends([old], {}, llm_call=lambda s, u, max_tokens=None: json.dumps(answers.pop(0)), max_workers=1, log=lambda *_: None)
    assert len(prompts) == n


def test_thai_fallback_for_search_trends_uses_only_real_searches_not_profile_wording():
    trend = {"name": "Long-Wear", "rising_searches": ["miss universe thailand 2026", "coachella 2026", "songkran 2026"], "target": "People who search for this",
             "profile": {"job_to_be_done": "เตรียมตัวสำหรับการประกวด", "psychosocial_consequence": "การถูกมองบนเวที"}, "products": [{"reason": "r"}]}
    th = enrich.fallback_texts_th(trend)
    assert "miss universe thailand 2026" in th["headline"] and "เตรียม" not in json.dumps(th, ensure_ascii=False) and "ถูกมอง" not in json.dumps(th, ensure_ascii=False)
    assert th["product_reasons"] == ["r"] and "workshop_question" not in th
    legacy = enrich.fallback_texts_th({"name": "Old", "analysis": {}, "key_ingredients": "", "key_benefits": "", "target": "",
                                       "profile": {"job_to_be_done": "เตรียมตัวสำหรับการประกวด"}, "products": []})
    assert "เตรียมตัว" in legacy["insight"]                                                         # รอบ 3 สายเดิมยังใช้โปรไฟล์เหมือนเดิม


# 🆕 (2026-10-28) ⑪: คำบอกการเตรียมตัว/วางแผน/ความรู้สึก/การถูกมอง ที่คำค้นไม่ได้บอก (เช่น คำค้นเป็นชื่อการประกวด -> "เตรียมตัวสำหรับการประกวด") = ข้อมูลไม่พอ
PAGEANT = {"Trend Name": "Pageants", "Places": ["TH"], "Members": "miss universe thailand 2026, coachella 2026, สงกรานต์ 2569",
           "Source Themes": [{"category": "Arts & Entertainment", "theme": "Pageants", "evidence": ["miss universe thailand 2026"]}]}


def test_gate_blanks_preparing_planning_and_feeling_words_the_searches_do_not_contain():
    ev = he.build_user_content(PAGEANT)
    raw = _raw(job_to_be_done="เตรียมตัวสำหรับการประกวดนางงามและงานเทศกาลดนตรี", psychosocial_consequence="การถูกมองในเวทีการประกวด",
               functional_consequence="วางแผนไปงานเทศกาล", point_of_difference="รู้สึกมั่นใจเมื่ออยู่บนเวที",
               evidence={"job_to_be_done": ["miss universe thailand 2026"], "psychosocial_consequence": ["miss universe thailand 2026"],
                         "functional_consequence": ["coachella 2026"], "point_of_difference": ["สงกรานต์ 2569"], "attribute": [], "point_of_parity": []})
    p = he.gate_profile(raw, ev)
    for f in ("job_to_be_done", "psychosocial_consequence", "functional_consequence", "point_of_difference"):
        assert p[f] == he.NO_INFO and p["_audit"][f] == "preparing / planning / feeling word not in the searches", f
    assert he.matchable_fields(p) == []
    # ค้นหาชื่องาน (ไม่เติมเหตุผล) ผ่าน / ถ้าคำค้นเองมีคำนั้น (เช่น "เตรียมตัวสอบ") คำนั้นใช้ได้
    ok = he.gate_profile(_raw(job_to_be_done="ค้นหาชื่อการประกวดนางงามและงานเทศกาลดนตรี", psychosocial_consequence="ข้อมูลไม่พอ",
                              evidence={"job_to_be_done": ["miss universe thailand 2026", "coachella 2026"]}), ev)
    assert ok["job_to_be_done"] == "ค้นหาชื่อการประกวดนางงามและงานเทศกาลดนตรี" and he.matchable_fields(ok) == ["job_to_be_done"]
    study = {"Trend Name": "Exam", "Members": "เตรียมตัวสอบ ทีแคส, ทรง ผม 2026", "Source Themes": []}
    ev2 = he.build_user_content(study)
    out = he.gate_profile(_raw(job_to_be_done="เตรียมตัวสอบ", evidence={"job_to_be_done": ["เตรียมตัวสอบ ทีแคส"]}), ev2)
    assert out["job_to_be_done"] == "เตรียมตัวสอบ" and "job_to_be_done" not in out["_audit"]


def test_prompt_no_longer_gives_a_pageant_as_an_example_of_a_social_situation():
    assert "ประกวด" not in he.SYSTEM_PROMPT_SEARCH.split("psychosocial_consequence:")[1].split("job_to_be_done:")[0]
    job = he.SYSTEM_PROMPT_SEARCH.split("job_to_be_done:")[1].split("point_of_difference:")[0]
    assert "ข้อมูลไม่พอ" in job and "ห้ามเขียนว่า \"ค้นหาชื่อ" in job and "ห้ามเขียนว่าเตรียมตัว" in he.SYSTEM_PROMPT_SEARCH
