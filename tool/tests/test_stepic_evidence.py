# -*- coding: utf-8 -*-
"""
🆕 (2026-10-27) STEPIC แบบใช้เฉพาะสิ่งที่คำค้นยืนยัน (phase5_report/stepic_evidence.py) - ไม่เรียก API (LLM จำลอง)
รอบแรกของสาย Search: STEPIC แต่งเนื้อหามิติเทคโนโลยี/นโยบายที่ข้อมูลไม่มี -> ต้อง "ตรวจด้วยโค้ด" ว่าสิ่งที่อ้างอยู่ในชุดหลักฐานจริง

รัน: pytest main/tool/tests/test_stepic_evidence.py -v
"""
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TOOL_DIR = TESTS_DIR.parent
for _p in (TOOL_DIR, TOOL_DIR / "phase5_report", TOOL_DIR / "phase6_pdf_report"):
    sys.path.insert(0, str(_p))

import stepic_evidence as se  # noqa: E402
import report_data  # noqa: E402

FIELDS = {d: ("concept", "key_drivers", "proof_point") for d in se.DIMENSIONS}
STREAM = {"search_meta": {"n_queries": 10701, "n_categories": 25, "places": ["TH", "WW"]},
          "trends": [{"Trend Name": "Haze Skin Protection", "Places": ["TH", "WW"],
                      "Source Themes": [{"category": "News", "theme": "Haze", "evidence": ["haze psi", "nea haze"]}],
                      "Members": "haze psi, nea haze, ทรง ผม ชาย 2026"},
                     {"Trend Name": "Other Trend", "Places": ["TH"], "Source Themes": [], "Members": "dog grooming tips"}]}
GROWTH = ('{"note": "Model forecast.", "market": {"median_expected_growth_pct": 30}, "trends": [{"trend": "Haze Skin Protection", '
          '"keywords": ["skin barrier protection", "sun cream"], "expected_search_growth_pct_vs_last_12_months": {"year_3": 14.2}, '
          '"growth_vs_market": {"year_3": "above"}}]}')
EVIDENCE = se.build_evidence(STREAM, {"Haze Skin Protection"}, GROWTH, 'Product: SPF 50 Sunscreen Gel 12" tube')
NORM = se._norm(EVIDENCE)


def test_evidence_has_no_double_quotes_or_json_so_copied_quotes_cannot_break_the_answer_json():
    assert '"' not in EVIDENCE and "\\" not in EVIDENCE and "{" not in EVIDENCE
    assert "12' tube" in EVIDENCE                                             # " ในชื่อสินค้าถูกแทนด้วย '
    assert "year_3 14.2" in EVIDENCE
    # คีย์เวิร์ดที่ใช้วัด (LLM เสนอ) ถูกติดป้ายว่าไม่ใช่หลักฐานว่ามีคนค้น
    assert "tracked terms (chosen to measure the trend, not proof of searches) skin barrier protection, sun cream" in EVIDENCE


def test_unusable_model_answers_are_retried_then_raise_instead_of_becoming_no_evidence():
    answers = [{"error": "Invalid JSON"}, {"foo": 1}, {"status": "evidence", "evidence": []}]
    calls = []

    def fake(system, prompt, label):
        calls.append(label)
        return answers[len(calls) - 1]

    ok = se.ask_json(fake, "s", "p", "STEPIC society", lambda d: d.get("status") in ("evidence", "no_evidence"), log=lambda *_: None)
    assert ok["status"] == "evidence" and len(calls) == 3
    import pytest
    with pytest.raises(RuntimeError):
        se.ask_json(lambda *_: {"error": "boom"}, "s", "p", "STEPIC policy", lambda d: True, log=lambda *_: None)


def test_evidence_lists_only_selected_trends_with_real_searches_and_places():
    assert "Haze Skin Protection" in EVIDENCE and "Other Trend" not in EVIDENCE
    assert "haze psi | nea haze" in EVIDENCE and "ทรง ผม ชาย 2026" in EVIDENCE
    assert "places where its searches rise: TH, WW" in EVIDENCE and "10701 searches" in EVIDENCE
    assert "SPF 50 Sunscreen Gel" in EVIDENCE


def test_snippets_must_be_copied_from_the_evidence_not_invented():
    assert se.verify_snippets(["HAZE   psi", "extremophile organisms", "ab"], NORM) == ["HAZE   psi"]
    assert se.verify_snippets("nea haze", NORM) == ["nea haze"]
    # ป้ายนำหน้าของบรรทัดหลักฐานถูกตัดได้ แต่ส่วนที่เหลือต้องอยู่ในหลักฐานตรงตัว
    assert se.verify_snippets(["my label: haze psi", "rising searches: not a real search"], NORM) == ["haze psi"]


def test_multi_digit_numbers_must_exist_in_the_evidence_whole():
    assert se.numbers_supported("Expected growth of 14.2% by year 3", NORM)        # 14.2 อยู่ในหลักฐาน
    assert not se.numbers_supported("Expected growth of 86% in year 3", NORM)      # 86 ไม่มี
    assert not se.numbers_supported("growth of 4.2%", NORM)                         # "4.2" ไม่ใช่ส่วนหนึ่งของ 14.2
    assert se.numbers_supported("three forces and 3 trends", NORM)                  # เลขหลักเดียวไม่ตรวจ


def test_quoted_searches_in_text_must_exist_in_the_evidence_but_apostrophes_are_fine():
    assert se.quotes_supported("People look up 'haze psi' and 'nea haze' in Google's lists.", NORM)
    assert not se.quotes_supported("Searches such as 'coachella 2026' rise.", NORM)
    assert se._clean_field("Searches such as 'coachella 2026' rise.", NORM) == se.NO_DATA


def test_dimension_without_verified_evidence_becomes_no_evidence_with_no_data_fields():
    invented = {"status": "evidence", "evidence": ["UN report on extremophiles"], "concept": "Extremophile ingredients", "key_drivers": "x"}
    d = se.build_dimension(invented, FIELDS["technology"], NORM)
    assert d["status"] == "no_evidence" and d["note"] == se.NO_DATA_NOTE
    assert all(d[f] == se.NO_DATA for f in FIELDS["technology"])
    assert se.build_dimension({"status": "no_evidence", "note": "Nothing on regulation."}, FIELDS["policy"], NORM)["note"] == "Nothing on regulation."
    assert se.build_dimension({"error": "boom"}, FIELDS["policy"], NORM)["status"] == "no_evidence"


def test_supported_dimension_keeps_verified_quotes_as_proof_point_and_blanks_unsupported_fields():
    ok = {"status": "evidence", "evidence": ["haze psi", "made up quote"], "concept": "People look up haze readings.",
          "key_drivers": "Cuts cost by 73% in Asia"}
    d = se.build_dimension(ok, FIELDS["environment"], NORM)
    assert d["status"] == "evidence" and d["proof_point"] == "haze psi"          # เฉพาะที่ตรวจผ่าน ไม่ใช่ข้อความของ LLM
    assert d["concept"] == "People look up haze readings."
    assert d["key_drivers"] == se.NO_DATA                                          # 73% ไม่อยู่ในหลักฐาน


def test_analyze_dimensions_runs_each_dimension_and_reports_status():
    calls = []

    def fake(system, prompt, label):
        calls.append(label)
        if label.endswith("society"):
            return {"status": "evidence", "evidence": ["haze psi"], "concept": "People look up haze readings.", "key_drivers": ""}
        return {"status": "no_evidence", "note": "No searches on this."}

    out = se.analyze_dimensions(fake, EVIDENCE, "beauty", FIELDS, log=lambda *_: None)
    assert len(calls) == 6 and out["society"]["status"] == "evidence"
    assert [d for d, v in out.items() if v["status"] == "no_evidence"] == ["technology", "environment", "policy", "industry", "creativity"]


def test_final_drops_unverified_personas_and_signals_and_signals_on_no_evidence_dimensions():
    dims = {d: se.no_evidence_dimension(FIELDS[d]) for d in se.DIMENSIONS}
    dims["society"] = {"status": "evidence", "concept": "c", "proof_point": "haze psi"}
    dims["environment"] = {"status": "evidence", "concept": "c", "proof_point": "nea haze"}
    parsed = {"mega_trend_name": "Haze-season skin care", "macro_direction": "Searches for haze readings rise.", "core_concept": "",
              "3_month_projection": "Expected growth of 99% soon.", "key_risk": "", "key_opportunity": "Sunscreen gel is on the shelf.",
              "evidence": ["haze psi"],
              "emerging_personas": [{"name": "Haze watcher", "description": "Searches haze readings in Thailand.", "value_driver": "", "channel_preference": "Instagram", "evidence": ["haze psi"]},
                                    {"name": "Invented", "description": "Not backed", "evidence": ["quote that is not there"]}],
              "cross_dimensional_signals": [{"dimensions": "SOCIETY + ENVIRONMENT", "signal": "Haze and searches move together.", "implication": "", "evidence": ["nea haze"]},
                                            {"dimensions": "SOCIETY + POLICY", "signal": "Rules tighten.", "evidence": ["haze psi"]},
                                            {"dimensions": "SOCIETY + ENVIRONMENT", "signal": "No proof", "evidence": ["nope"]}]}
    f = se.build_final(parsed, dims, NORM)
    assert f["mega_trend_name"] == "Haze-season skin care" and f["3_month_projection"] == ""      # รายปี ไม่ใช่ 3 เดือน (+ 99% ไม่อยู่ในหลักฐาน)
    parsed["3_month_projection"] = "Searches rise 14.2% in year 3."                              # แม้เลขจะถูก ก็ไม่ใช้ในหัวข้อ 3 เดือน
    assert se.build_final(parsed, dims, NORM)["3_month_projection"] == ""
    sig = se.build_final({**parsed, "cross_dimensional_signals": [{"dimensions": "SOCIETY + ENVIRONMENT", "signal": "Both appear.",
                         "implication": "Haze drives sun care demand.", "evidence": ["nea haze"]}]}, dims, NORM)["cross_dimensional_signals"]
    assert sig[0]["implication"] == ""                                                           # ผลเชิงสาเหตุ คำค้นยืนยันไม่ได้
    audit = se.build_final({**parsed, "key_risk": "Searches fall 99% soon."}, dims, NORM)["_audit"]   # เหตุผลที่ตัดต้องเห็นได้ ไม่เงียบ
    assert audit["fields_blanked"] == ["key_risk: number or quoted search not in the evidence"] and audit["top_quotes_verified"] == 1
    assert [p["name"] for p in f["emerging_personas"]] == ["Haze watcher"]
    assert f["emerging_personas"][0]["value_driver"] == ""
    assert [s["dimensions"] for s in f["cross_dimensional_signals"]] == ["SOCIETY + ENVIRONMENT"]


def test_final_blanks_every_takeaway_field_when_no_top_level_evidence_verifies():
    f = se.build_final({"mega_trend_name": "Invented", "macro_direction": "Invented", "evidence": ["not in evidence"]}, {}, NORM)
    assert f["mega_trend_name"] == "" and f["macro_direction"] == "" and f["evidence"] == []
    assert se.build_final("garbage", {}, NORM)["emerging_personas"] == []


def test_report_tiles_show_no_data_for_dimensions_without_evidence_and_ignore_no_data_fields():
    raw = {"society": {"status": "evidence", "concept": "People look up haze readings.", "behavioral_shift": se.NO_DATA,
                       "projected_impact": se.NO_DATA, "proof_point": "haze psi"},
           "technology": se.no_evidence_dimension(("core_technology", "proof_point")),
           "environment": {"status": "evidence", "environmental_factor": "Haze", "sustainability_opportunity": "No data", "ESG_driver": "No data",
                           "proof_point": "nea haze"}}
    tiles = {t["dimension"]: t for t in report_data._stepic_tiles(raw)}
    assert tiles["Technology"]["no_data"] and tiles["Technology"]["headline"] == "No data"
    assert "no_data" not in tiles["Society"] and "No data" not in tiles["Society"]["body"] and "No data" not in tiles["Environment"]["body"]
    assert "Policy" not in tiles            # มิติที่ไม่มีในผลเลยยังถูกข้ามเหมือนเดิม (รอบ 3 สายเดิม)


def test_environment_and_policy_need_a_search_that_names_the_topic():
    wrong_topic = {"status": "evidence", "evidence": ["haze psi"], "concept": "Sun exposure drives searches.", "key_drivers": "No data"}
    # คำค้นที่คัดลอกถูกต้องแต่ไม่ใช่เรื่องของมิตินั้น (policy) = no_evidence ; เรื่องสภาพอากาศ (environment) = ผ่านเหมือนเดิม
    assert se.build_dimension(wrong_topic, FIELDS["policy"], NORM, se.DIMENSION_TOPIC["policy"])["status"] == "no_evidence"
    assert se.build_dimension(wrong_topic, FIELDS["environment"], NORM, se.DIMENSION_TOPIC["environment"])["status"] == "evidence"
    assert se.build_dimension(wrong_topic, FIELDS["environment"], NORM)["status"] == "evidence"          # ไม่ส่ง topic = พฤติกรรมเดิม
    env, pol = se.DIMENSION_TOPIC["environment"], se.DIMENSION_TOPIC["policy"]
    assert not env.search("best sunscreen for face") and not env.search("สงกรานต์ 2569") and not pol.search("bangkok beauty shop")
    assert env.search("weather today near me") and env.search("คลื่น ความ ร้อน") and env.search("pm 2.5 today") and pol.search("fda recall") and pol.search("กฎหมาย ใหม่")


# 🆕 (2026-10-28) ข้อความวิเคราะห์ต่อเทรนด์ (Step 9d) ของรอบสาย Search: LLM เขียนได้เฉพาะประโยค consumer intent จากคำค้นจริง (ข้อความที่คัดลอกต้องตรงหลักฐาน)
from common import market_overview as _mo  # noqa: E402
from common import trend_analysis as _ta  # noqa: E402

ROW = STREAM["trends"][0]
INTENT_EV = se._norm(se.sanitize(chr(10).join(["EVIDENCE"] + se.trend_evidence_lines(ROW))))


def _facts():
    keys = list(_mo.HORIZON_KEYS)
    return {"trend": "Haze Skin Protection", "keywords": ["skin barrier protection", "sun cream"], "key_ingredients": "invented retinol",
            "key_benefits": "invented barrier repair", "target_consumer": "invented office workers",
            "expected_search_growth_pct_vs_last_12_months": {k: 4.0 + i for i, k in enumerate(keys)},
            "growth_vs_market": {k: "above" for k in keys}, "seasonality": {"peak_months": ["Jun", "Jul"], "swing_pct": 62.5},
            "durability": {"longevity_score": 61, "band": "medium"}, "trend_stage": "Emerging", "primary_driver": "Organic Seasonality",
            "estimated_duration": "Medium-term"}


def test_intent_sentence_needs_a_verified_quote_and_supported_numbers_and_quoted_searches():
    ok = {"consumer_intent_signal": "People search for 'haze psi' and 'nea haze'.", "evidence": ["rising searches: haze psi", "nea haze"]}
    out = se.build_intent(ok, INTENT_EV)
    assert out == {"text": "People search for 'haze psi' and 'nea haze'.", "evidence": ["rising searches: haze psi", "nea haze"]}    # ข้อความเก็บตามที่ LLM คัดลอกมา (ตรวจโดยตัดป้ายหัวข้อออก)
    for bad in ({**ok, "evidence": ["clinical study on haze"]},                                       # ข้อความที่คัดลอกไม่อยู่ในหลักฐาน
                {**ok, "evidence": []},
                {**ok, "consumer_intent_signal": "People search for 'haze mask' and 'nea haze'."},   # คำค้นในเครื่องหมายคำพูดที่ไม่มีจริง
                {**ok, "consumer_intent_signal": "Searches rose 86% in a year."},                     # ตัวเลขไม่อยู่ในหลักฐาน
                {**ok, "consumer_intent_signal": "No data"}, {"consumer_intent_signal": 5}, "garbage", None):
        assert se.build_intent(bad, INTENT_EV) == {"text": "", "evidence": []}


def test_write_intents_asks_per_trend_with_its_own_searches_and_survives_a_failing_trend():
    prompts = []

    def chat(system, prompt, label):
        prompts.append((system, prompt, label))
        return {"consumer_intent_signal": "People search for 'haze psi'.", "evidence": ["haze psi"]} if "haze psi" in prompt else {"error": "x"}

    rows = {"Haze Skin Protection": ROW, "Other Trend": STREAM["trends"][1]}
    quiet = []
    out = se.write_intents(chat, rows, ["Haze Skin Protection", "Other Trend", "Missing"], log=quiet.append)
    assert out["Haze Skin Protection"]["text"] == "People search for 'haze psi'." and "Missing" not in out
    assert "Other Trend" not in out                                                                       # ตอบใช้ไม่ได้ครบ 3 ครั้ง = ไม่มีประโยคของ LLM (ไม่ใช่ "ไม่มีข้อมูล")
    assert sum(1 for _, p, _ in prompts if "dog grooming tips" in p) == 3 and all(s == se.SYSTEM_INTENT for s, _, _ in prompts)
    first = next(p for _, p, _ in prompts if "haze psi" in p)
    assert "dog grooming" not in first and "invented" not in first and '"' not in first                    # คำค้นของเทรนด์นั้นเท่านั้น ไม่มีเครื่องหมายคำพูดคู่


def test_search_analysis_entry_uses_numbers_and_verified_intent_only():
    facts = _facts()
    e = _ta.search_analysis_entry(facts, ["haze psi", "nea haze", "a", "b"], {"text": "People search for 'haze psi'.", "evidence": ["haze psi"]})
    assert e["consumer_intent_signal"] == "People search for 'haze psi'." and e["intent_evidence"] == ["haze psi"] and e["text_source"] == "evidence"
    blob = " ".join(str(v) for v in e.values())
    assert "invented" not in blob and "Durability" not in blob and "61/100" not in blob                    # ไม่เอาข้อความตีความของสายหรือคะแนนความทนทานมาใช้
    assert e["trend_stage"] == "Emerging" and e["expected_search_growth_pct"] == facts["expected_search_growth_pct_vs_last_12_months"]
    assert "Interest is seasonal, peaking around Jun and Jul" in e["driver_explanation"]
    fb = _ta.search_analysis_entry(facts, ["haze psi", "nea haze", "a", "b"], {"text": "", "evidence": []})
    assert fb["consumer_intent_signal"] == "Rising searches include: haze psi, nea haze, a." and fb["text_source"] == "numbers" and fb["intent_evidence"] == []
    assert _ta.search_analysis_entry(facts, [], None)["consumer_intent_signal"] == "No data"
    old = _ta.analysis_entry(facts, None)                                                                   # รอบ 3 สายเดิมไม่เปลี่ยน: ยังใช้ส่วนผสม/ประโยชน์/ความทนทาน
    assert old["consumer_intent_signal"] == "Consumers look for invented barrier repair." and "Durability score 61/100" in old["driver_explanation"]
