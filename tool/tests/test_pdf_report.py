# -*- coding: utf-8 -*-
"""
เทสของ ⑯ PDF Report (tool/step5_pdf/) - ไม่ยิง API และไม่เปิด Chromium
ใช้โฟลเดอร์รอบปลอมใน tmp_path: ตรวจว่าไฟล์ขาดแล้วรายงานยังประกอบได้ (แค่จดไว้ใน missing), ข้อความไทยที่เป็นค่าตายตัว
ถูกแปลงเป็นอังกฤษ, cache ของ LLM ใช้ซ้ำได้จริง และเทมเพลตได้จำนวนหน้าตรงตามข้อมูล

รัน: pytest main/tool/tests/test_pdf_report.py -v
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "step5_pdf"))

from datetime import datetime  # noqa: E402

import pytest  # noqa: E402

import pandas as pd  # noqa: E402
from charts import BUMP_CHART_KEY, TREND_MAP_KEY, bump_chart_svg, trend_map_svg, yearly_ranks  # noqa: E402
from enrich import enrich_trends, fallback_texts, validate  # noqa: E402
from render import render_html  # noqa: E402
from report_data import (build_context, first_sentences, smart_title, split_headline,  # noqa: E402
                         strip_thai)

BRAND = {"company_name": "Acme", "logo": None, "prepared_by": "", "accent_color": "#E8611A"}


def _write(folder, name, data):
    with open(folder / name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


@pytest.fixture
def run_dir(tmp_path):
    """รอบปลอมที่มีแค่ผล ⑪ (ขั้นต่ำสุดที่ทำรายงานได้) + ผล ⑬ ของ 1 แบรนด์ (ใส่ไว้เพื่อพิสูจน์ว่า PDF เมินมัน)"""
    run = tmp_path / "topic_20260101_000000"
    run.mkdir()
    _write(run, "phase3_trend_highlights_result.json", {
        "top_n": 2, "n_trends_total": 3,
        "profiles": [{"trend": "Barrier Care", "stream": "Social", "trend_type": "สินค้า",
                      "job_to_be_done": "ฟื้นฟูผิว"}],
        "selected_trends": [
            {"overall_rank": 1, "stream": "Social", "trend": "Barrier Care", "rank_score": 0.9, "z_delta": 0.9,
             "top_rank": 1},
            {"overall_rank": 3, "stream": "Paper", "trend": "Stable Retinol", "rank_score": 0.4, "z_delta": 0.4,
             "top_rank": 2},
        ],
        "excluded_trends": [{"overall_rank": 2, "stream": "News", "trend": "Live Commerce",
                             "reason": "เทรนด์ประเภทช่องทาง/พฤติกรรมการซื้อ - ไม่มีคุณสมบัติสินค้าให้จับคู่"}],
        "failed_trends": [],
    })
    _write(run, "phase3_brand_coverage_Zenith.json", {"brand": "Zenith", "n_skus": 12, "coverage": {
        "Social::Barrier Care": {"trend_name": "Barrier Care", "tier": "Gap - ยังไม่มีของเข้าเทรนด์นี้",
                                 "brand_best_product": "Zenith Cream 50 ml. ครีมบำรุง", "brand_best_score": 0.1,
                                 "brand_best_percentile_vs_market": 20, "market_best_product": "Other Cream",
                                 "market_best_score": 0.4},
    }})
    return run


def test_strip_thai_and_title():
    assert strip_thai("Johnson's Baby Cream 100 G. ครีมบำรุงผิวหน้า ผิวกาย") == "Johnson's Baby Cream 100 G."
    assert smart_title("beauty and personal care") == "Beauty and Personal Care"
    assert smart_title("K-Beauty in thailand") == "K-Beauty in Thailand"


def test_first_sentences_cuts_on_boundary():
    text = "One two three. Four five six. Seven eight nine."
    assert first_sentences(text, 30) == "One two three. Four five six."
    assert first_sentences("a" * 10 + " " + "b" * 50, 20).endswith("…")
    assert split_headline("The Shift: consumers move to clinics") == ("The Shift", "consumers move to clinics")


def test_build_context_with_missing_files(run_dir):
    ctx, series = build_context(run_dir)
    assert [t["name"] for t in ctx["trends"]] == ["Barrier Care", "Stable Retinol"]
    assert [t["rank"] for t in ctx["trends"]] == [1, 2]
    assert series == {}
    # ไฟล์ที่ขาดถูกจดไว้ ไม่ทำให้พัง
    assert any("Rank Score" in m for m in ctx["missing"])
    assert any("STEPIC" in m for m in ctx["missing"])
    # เหตุผลภาษาไทยที่เป็นค่าตายตัวถูกแปลงเป็นอังกฤษ
    assert ctx["excluded"][0]["reason"].startswith("Sales-channel")
    # ผล ⑬ ไม่เกี่ยวกับ PDF - ไฟล์ phase3_brand_coverage_*.json ในโฟลเดอร์รอบถูกเมินทั้งหมด
    assert "brands" not in ctx


def test_build_context_requires_highlights(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_context(tmp_path)


def test_validate_llm_output():
    ok = {"headline": "A", "trend": "B", "insight": "C", "workshop_question": "How can your brand do X?"}
    assert validate(ok) == ok
    assert validate({**ok, "trend": "มีภาษาไทย"}) is None
    assert validate({**ok, "workshop_question": "How can your brand do X"}) is None
    assert validate({"headline": "A"}) is None


def test_enrich_uses_cache_and_falls_back(run_dir):
    ctx, _ = build_context(run_dir)
    calls = []

    def fake_llm(system, user):
        calls.append(user)
        if "Stable Retinol" in user:
            raise RuntimeError("boom")
        return json.dumps({"headline": "H", "trend": "T", "insight": "I",
                           "workshop_question": "How can your brand win?"})

    cache, counts = enrich_trends(ctx["trends"], {}, llm_call=fake_llm, max_workers=1, log=lambda *_: None)
    assert counts == {"llm": 1, "fallback": 1}
    assert ctx["trends"][0]["text"]["workshop_question"] == "How can your brand win?"
    assert ctx["trends"][1]["text"]["workshop_question"].endswith("?")

    # รอบสอง: ข้อมูลเดิม -> ใช้ cache ไม่เรียก LLM ซ้ำสำหรับเทรนด์ที่สำเร็จแล้ว
    ctx2, _ = build_context(run_dir)
    calls.clear()
    _, counts2 = enrich_trends(ctx2["trends"], cache, llm_call=None, log=lambda *_: None)
    assert counts2 == {"llm (cached)": 1, "fallback": 1}
    assert calls == []


def test_fallback_texts_are_sentences():
    t = {"name": "Barrier Care", "target": "Sensitive-skin consumers", "key_ingredients": "", "key_benefits": "repair",
         "analysis": {"executive_summary": "Demand is rising. More detail here.",
                      "consumer_intent_signal": "Seeking gentle care"}}
    out = fallback_texts(t)
    assert out["headline"] == "Demand is rising. More detail here."
    assert "Seeking gentle care. Target consumer" in out["insight"]
    assert out["workshop_question"] == "How can your brand lead the Barrier Care trend for sensitive-skin consumers?"


def test_render_page_count(run_dir):
    ctx, _ = build_context(run_dir)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    for t in ctx["trends"]:
        for p in t["products"]:
            p["image"] = None
    html = render_html(ctx, BRAND, {}, "Topic Trend Forecast", datetime(2026, 1, 1), "2 fallback")
    # ปก + summary + overview + หน้าคั่น + 3 หน้าต่อเทรนด์ + appendix 2 หน้า (ไม่มีหน้าแบรนด์)
    # (ไม่มี takeaway/STEPIC/personas/signals เพราะรอบปลอมไม่มีไฟล์ STEPIC)
    assert html.count('<section class="page') == 4 + 3 * 2 + 2
    assert "Paper" not in html and "Social" not in html  # ไม่แสดงสายหลักฐาน
    assert "Acme" in html  # ชื่อบริษัทใน footer (branding) ไม่ใช่แบรนด์ที่เทียบ
    assert "Zenith" not in html and "Brand Coverage" not in html and "Brand coverage" not in html


def test_logo_placement_follows_logo_for_dark_bg(run_dir):
    """โลโก้ตัวหนังสือสีขาว (logo_for_dark_bg): หน้าพื้นดำไม่มีกล่องขาวบัง, หน้าพื้นขาววางบนกล่องดำ
    ส่วนโลโก้ปกติ: หน้าพื้นดำวางบนกล่องขาว เหมือนเดิม"""
    ctx, _ = build_context(run_dir)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    logo = "data:image/png;base64,AAAA"

    def render(**extra):
        return render_html(ctx, {**BRAND, "logo": logo, **extra}, {}, "T", datetime(2026, 1, 1), "x")

    plain = render()
    assert 'class="logo-chip"' in plain and 'logo-chip on-black' not in plain
    dark_logo = render(logo_for_dark_bg=True)
    assert 'class="logo-chip"' not in dark_logo          # ไม่มีกล่องขาวบังตัวหนังสือสีขาวบนแถบดำ
    assert 'logo-chip on-black' in dark_logo             # หน้าพื้นขาว (หัวเทรนด์/สรุป) ใช้กล่องดำแทน


def test_trend_map_chart_and_page():
    """Z_Delta x Stream_Count: มี SVG เมื่อมีข้อมูล (ชื่อเทรนด์เป็นตัวอักษรใน SVG) / None เมื่อไม่มี stream_count
    และหน้า Trend Map โผล่ในรายงานก็ต่อเมื่อมีกราฟ"""
    trends = [{"rank": 1, "name": "Barrier Care", "z_delta": 0.9, "stream_count": 2, "cluster_size": 12},
              {"rank": 2, "name": "Stable Retinol", "z_delta": 0.4, "stream_count": 1, "cluster_size": None}]
    svg = trend_map_svg(trends)
    assert svg.startswith("<svg") and "Barrier Care" in svg and "Stable Retinol" in svg
    assert trend_map_svg([{**t, "stream_count": None} for t in trends]) is None
    assert trend_map_svg([]) is None


def test_render_has_trend_map_page_only_with_chart(run_dir):
    ctx, _ = build_context(run_dir)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    for t in ctx["trends"]:
        for p in t["products"]:
            p["image"] = None
    without = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    with_map = render_html(ctx, BRAND, {TREND_MAP_KEY: "data:image/svg+xml;base64,AAAA"}, "T", datetime(2026, 1, 1), "x")
    assert 'data-label="Trend Map"' not in without
    assert 'data-label="Trend Map"' in with_map
    assert with_map.count('<section class="page') == without.count('<section class="page') + 1


def _series(values_by_year):
    rows = [{"Date": pd.Timestamp(f"{y}-06-01"), "z_score": z, "Type": "Fit"} for y, z in values_by_year.items()]
    return pd.DataFrame(rows)


def test_yearly_ranks_and_bump_chart():
    """อันดับรายปีภายในกลุ่ม: 1 = z-score เฉลี่ยสูงสุด, ครบ 1..N ทุกปีแม้ค่าเท่ากัน (method=first เรียงตามชื่อ), ตัดปีก่อน 2023"""
    series = {"B": _series({2022: 9, 2023: 1.0, 2024: 3.0}), "A": _series({2022: 0, 2023: 1.0, 2024: 2.0}),
              "C": _series({2023: 0.5, 2024: 5.0})}
    ranks = yearly_ranks(series)
    assert list(ranks.index) == [2023, 2024]
    assert ranks.loc[2023].to_dict() == {"A": 1, "B": 2, "C": 3}   # A กับ B เท่ากัน -> A ก่อน (ชื่อเรียงก่อน)
    assert ranks.loc[2024].to_dict() == {"A": 3, "B": 2, "C": 1}
    trends = [{"rank": 1, "name": "A"}, {"rank": 2, "name": "B"}, {"rank": 3, "name": "C"}]
    svg = bump_chart_svg(series, trends)
    assert svg.startswith("<svg") and "#1 A" in svg and "#3 C" in svg
    assert bump_chart_svg({"A": _series({2023: 1.0})}, trends[:1]) is None   # ปีเดียว วาดเส้นไม่ได้
    assert bump_chart_svg({}, trends) is None


def test_yearly_ranks_match_plot_bump_chart_excel():
    """เทียบกับตารางอันดับที่ Plot_bump_chart.py บันทึกไว้จริงของรอบอ้างอิง (ข้ามถ้าเครื่องนี้ไม่มีรอบ/ไฟล์นั้น)"""
    from report_data import load_forecast_series
    run = Path(__file__).resolve().parents[2] / "output" / "beauty_and_personal_care_20260916_082438"
    excels = sorted(run.glob("step5c_df_cluster_forecast_ranks_*.xlsx"))
    if not excels or not (run / "phase3_trend_highlights_result.json").exists():
        pytest.skip("ไม่มีรอบอ้างอิงหรือตารางอันดับของ Plot_bump_chart ในเครื่องนี้")
    ref = pd.read_excel(excels[-1], index_col=0)
    ref.index = ref.index.astype(int)
    series = load_forecast_series(run, list(ref.columns))
    mine = yearly_ranks(series).reindex(index=ref.index, columns=ref.columns)
    assert mine.equals(ref)


def test_render_has_bump_page_only_with_chart(run_dir):
    ctx, _ = build_context(run_dir)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    for t in ctx["trends"]:
        for p in t["products"]:
            p["image"] = None
    without = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    with_bump = render_html(ctx, BRAND, {BUMP_CHART_KEY: "data:image/svg+xml;base64,AAAA"}, "T", datetime(2026, 1, 1), "x")
    assert 'data-label="Rank Trajectory"' not in without
    assert 'data-label="Rank Trajectory"' in with_bump
    assert with_bump.count('<section class="page') == without.count('<section class="page') + 1


def test_cover_date_has_four_digit_year_and_data_sources(run_dir):
    ctx, _ = build_context(run_dir)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 9, 25), "x")
    assert '<div class="cover-date">25.09.2026</div>' in html
    assert ("Search data: Worldwide Google Trends (English keywords) | Product evidence: Watsons Thailand") in html


# ============================================================================
# ฉบับภาษาไทย (phase6_trend_report_TH.pdf)
# ============================================================================
from enrich import fallback_texts_th, translate_report_texts, validate_same_shape, validate_th  # noqa: E402
from i18n import date_long, dimensions, enum, localize, month_year  # noqa: E402

TH_OK = {"headline": "ตลาดโต", "trend": "เทรนด์ดี", "insight": "ผู้บริโภคต้องการ",
         "workshop_question": "แบรนด์ของคุณจะทำอย่างไร?", "target": "ผู้หญิงผิวแพ้ง่าย", "product_reasons": ["ช่วยปลอบผิว"]}
TH_PAYLOAD = {"context_en": {"target_consumer": "Sensitive-skin women"}, "product_match_reasons_en": ["Soothes skin"]}


def test_validate_th():
    assert validate_th(TH_OK, TH_PAYLOAD)["product_reasons"] == ["ช่วยปลอบผิว"]
    assert validate_th({**TH_OK, "trend": "English only"}, TH_PAYLOAD) is None          # ต้องมีอักษรไทย
    assert validate_th({**TH_OK, "workshop_question": "แบรนด์ของคุณ"}, TH_PAYLOAD) is None  # ต้องลงท้ายด้วย ?
    assert validate_th({**TH_OK, "product_reasons": []}, TH_PAYLOAD) is None               # เหตุผลต้องครบทุกสินค้า
    assert validate_th({**TH_OK, "target": "Sensitive women"}, TH_PAYLOAD) is None


def test_fallback_texts_th_uses_thai_profile():
    t = {"name": "Barrier Care", "target": "Sensitive-skin consumers", "key_ingredients": "", "key_benefits": "",
         "analysis": {"executive_summary": "Demand is rising."},
         "profile": {"attribute": "ข้อมูลไม่พอ", "functional_consequence": "ลดการระคายเคือง",
                     "job_to_be_done": "ฟื้นฟูผิว"},
         "products": [{"reason": "Soothes skin"}]}
    out = fallback_texts_th(t)
    assert out["trend"] == "ลดการระคายเคือง"            # ข้าม "ข้อมูลไม่พอ"
    assert out["insight"] == "ฟื้นฟูผิว"
    assert out["workshop_question"] == "แบรนด์ของคุณจะคว้าโอกาสจากเทรนด์ Barrier Care ได้อย่างไร?"
    assert out["product_reasons"] == ["Soothes skin"]   # ไม่มีต้นฉบับไทย -> คงภาษาอังกฤษ


def test_validate_same_shape_allows_english_names():
    src = {"mega_trend_name": "The Shift", "macro_direction": "Markets move."}
    assert validate_same_shape(src, {"mega_trend_name": "The Shift", "macro_direction": "ตลาดเปลี่ยน"})
    assert validate_same_shape(src, {"mega_trend_name": "The Shift", "macro_direction": "Markets move."}) is None
    assert validate_same_shape(src, {"mega_trend_name": "The Shift"}) is None                     # คีย์ไม่ครบ
    items = {"items": [{"name": "Curator", "description": "A buyer."}]}
    assert validate_same_shape(items, {"items": []}) is None                                      # ลิสต์สั้นกว่า
    assert validate_same_shape(items, {"items": [{"name": "Curator", "description": "ผู้ซื้อ"}]})


def test_translate_report_texts_caches_and_falls_back():
    ctx = {"takeaway": {"mega_trend_name": "The Shift", "macro_direction": "Markets move."},
           "overview": {"market": {"summary": "Strong market."}}, "stepic": [], "personas": [], "signals": []}
    calls = []

    def fake_llm(system, user, max_tokens=900):
        calls.append(user)
        if "Strong market" in user:
            return json.dumps({"summary": "English again"})   # ไม่ผ่าน (ไม่มีภาษาไทย) -> ใช้ต้นฉบับ
        return json.dumps({"mega_trend_name": "The Shift", "macro_direction": "ตลาดเปลี่ยน"})

    tr, cache, counts = translate_report_texts(ctx, {}, llm_call=fake_llm, max_workers=1, log=lambda *_: None)
    assert tr == {"takeaway": {"mega_trend_name": "The Shift", "macro_direction": "ตลาดเปลี่ยน"}}
    assert counts == {"llm": 1, "english (fallback)": 1}
    calls.clear()
    tr2, _, counts2 = translate_report_texts(ctx, cache, llm_call=None, log=lambda *_: None)
    assert tr2 == tr and calls == [] and counts2 == {"llm (cached)": 1, "english (fallback)": 1}


def test_i18n_helpers():
    assert month_year("Aug 2029", "th") == "ส.ค. 2029" and month_year("Aug 2029", "en") == "Aug 2029"
    assert enum("Major Breakout", "th") == "ทะยานแรง" and enum("Something New", "th") == "Something New"
    assert dimensions("SOCIETY + INDUSTRY", "th") == "สังคม + อุตสาหกรรม"
    assert date_long(datetime(2026, 9, 16), "th") == "16 ก.ย. 2026"


def test_localize_th_does_not_touch_english_context(run_dir):
    ctx, _ = build_context(run_dir)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None, lang="th")
    ctx["trends"][0]["status"] = "Rising"
    ctx["trends"][0]["products"] = [{"name": "Cream 50 ml.", "name_full": "Cream 50 ml. ครีม", "reason": "Soothes"}]
    ctx["trends"][0]["text_th"]["product_reasons"] = ["ช่วยปลอบผิว"]
    th = localize(ctx, "th")
    assert th["trends"][0]["status"] == "กำลังขึ้น" and ctx["trends"][0]["status"] == "Rising"
    assert th["trends"][0]["products"][0] == {"name": "Cream 50 ml. ครีม", "name_full": "Cream 50 ml. ครีม",
                                              "reason": "ช่วยปลอบผิว"}
    assert th["trends"][0]["text"]["workshop_question"].startswith("แบรนด์ของคุณ")
    assert th["excluded"][0]["reason"].startswith("เทรนด์ประเภทช่องทาง")   # เหตุผลต้นฉบับจาก ⑪
    assert th["missing"][0].startswith("คะแนนจัดอันดับ")
    assert localize(ctx, "en") is ctx


def test_render_th_same_pages_thai_labels(run_dir):
    ctx, _ = build_context(run_dir)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None, lang="th")
    en = render_html(ctx, BRAND, {}, "T", datetime(2026, 9, 25), "x")
    th = render_html(localize(ctx, "th"), BRAND, {}, "พยากรณ์เทรนด์ T", datetime(2026, 9, 25), "x", lang="th")
    assert th.count('<section class="page') == en.count('<section class="page')
    assert '<html lang="th">' in th and 'class="lang-th"' in th
    assert "<h2>สรุปรายงาน |" in th and "ภาคผนวก | วิธีการ" in th and "<h2>Report Summary" not in th
    assert "Barrier Care" in th                      # ชื่อเทรนด์คงเป็นภาษาอังกฤษ
    assert "Paper" not in th and "Social" not in th  # ไม่แสดงสายหลักฐาน
    assert '<div class="cover-date">25.09.2026</div>' in th


# ============================================================================
# ย่อข้อความหน้า Macro Forces | STEPIC และ Signals & Outlook (feedback: ตัวหนังสือเยอะเกิน)
# ============================================================================
from enrich import (CONDENSE_LIMITS, build_report_payloads, condense_report_texts,  # noqa: E402
                    fallback_condensed, validate_condensed)

# ประโยคแรกยาว 45 คำ - เกินทุกขีดจำกัดใน CONDENSE_LIMITS (สูงสุด 35 คำ)
LONG = " ".join(["word"] * 45) + ". Second one."


def _condense_ctx():
    return {"stepic": [{"dimension": "Society", "headline": "A very long headline about society today", "body": LONG}],
            "signals": [{"dimensions": "SOCIETY + INDUSTRY", "signal": LONG, "implication": LONG}],
            "takeaway": {"mega_trend_name": "The Shift", "projection": LONG}}


def test_validate_condensed_enforces_word_limits():
    src = {"items": [{"headline": "h", "body": "b"}]}
    ok = {"items": [{"headline": "Clinical Wellness Shift", "body": "Consumers now pick products by evidence."}]}
    assert validate_condensed("stepic", src, ok) == ok
    too_long = {"items": [{"headline": "one two three four five six seven eight nine", "body": "fine"}]}
    assert validate_condensed("stepic", src, too_long) is None                # เกิน 6 คำ x 1.25
    assert validate_condensed("stepic", src, {"items": []}) is None             # จำนวนข้อไม่ตรง
    assert validate_condensed("stepic", src, {"items": [{"headline": "ไทย", "body": "b"}]}) is None


def test_fallback_condensed_trims_to_first_sentence_and_limit():
    out = fallback_condensed("signals", {"items": [{"signal": LONG, "implication": "Short one. Next."}], "outlook": LONG})
    assert out["items"][0]["implication"] == "Short one."
    assert len(out["items"][0]["signal"].split()) == CONDENSE_LIMITS["signals"]["signal"]
    assert out["items"][0]["signal"].endswith("…")


def test_condense_updates_context_caches_and_feeds_thai_translation():
    ctx = _condense_ctx()
    calls = []

    def fake_llm(system, user, max_tokens=900):
        calls.append(user)
        if '"outlook"' in user:
            return json.dumps({"items": [{"signal": "Pharmacy and beauty merge.", "implication": "Clinics win."}],
                               "outlook": "More clinical M&A ahead."})
        return json.dumps({"items": [{"headline": "Clinical Wellness", "body": "Shoppers want proof."}]})

    cache = {}
    counts = condense_report_texts(ctx, cache, llm_call=fake_llm, max_workers=1, log=lambda *_: None)
    assert counts == {"llm": 2}
    assert ctx["stepic"][0]["headline"] == "Clinical Wellness" and ctx["stepic"][0]["dimension"] == "Society"
    assert ctx["signals"][0]["signal"] == "Pharmacy and beauty merge."
    assert ctx["takeaway"]["projection"] == "More clinical M&A ahead."
    # ฉบับไทยแปลจากฉบับย่อ ไม่ใช่ต้นฉบับยาว
    payloads = build_report_payloads(ctx)
    assert payloads["stepic"]["items"][0]["body"] == "Shoppers want proof."
    assert payloads["takeaway"]["projection"] == "More clinical M&A ahead."

    # รอบสองด้วยข้อมูลเดิม: ใช้ cache ไม่เรียก LLM
    ctx2, calls[:] = _condense_ctx(), []
    assert condense_report_texts(ctx2, cache, llm_call=None, log=lambda *_: None) == {"llm (cached)": 2}
    assert calls == [] and ctx2["stepic"][0]["body"] == "Shoppers want proof."


def test_condense_without_llm_trims():
    ctx = _condense_ctx()
    counts = condense_report_texts(ctx, {}, llm_call=None, log=lambda *_: None)
    assert counts == {"trimmed (fallback)": 2}
    assert len(ctx["stepic"][0]["body"].split()) <= CONDENSE_LIMITS["stepic"]["body"]


# ============================================================================
# ⑰ รายงานแบรนด์ x เทรนด์ (phase6_brand_report_<แบรนด์>.pdf)
# ============================================================================
from brand_data import (DEFAULT_CONFIG, build_brand_context, find_coverage_file, fit_level,  # noqa: E402
                        quadrant)
from brand_i18n import apply_th  # noqa: E402
from charts import fit_matrix_svg  # noqa: E402
from enrich import translate_items_th  # noqa: E402
from render import render_brand_html  # noqa: E402

TH_RANKS = DEFAULT_CONFIG["fit_rank_thresholds"]


def _brand_fixture(run_dir, best_rank=20):
    """trend ctx (2 เทรนด์) + ผล ⑬ ของแบรนด์ Zenith ที่มีแค่เทรนด์แรก - tier เป็น "Gap" แต่อันดับจริง = best_rank"""
    ctx, _ = build_context(run_dir)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None, lang="th")
    coverage = {"brand": "Zenith", "n_skus": 12, "coverage": {"Social::Barrier Care": {
        "trend_name": "Barrier Care", "tier": "ตามทัน/มีของเข้าเทรนด์", "brand_best_product": "Zenith Cream",
        "brand_best_score": 0.30, "brand_best_rank_vs_market": best_rank, "market_best_product": "Other - Other Cream",
        "market_best_score": 0.35,
        "brand_top_matches": [{"product_name": "Zenith Cream", "similarity": 0.30, "rank_vs_market": best_rank,
                               "sale_price_thb": 199.0, "match_reason": "Soothes skin."}]}}}
    catalog = pd.DataFrame([{"brand": "Other", "product_name": "Other Cream", "main_image": None, "product_url": None,
                             "sale_price_thb": "1,290.00", "Category": "Skincare", "Sub_category": "Face Moisture"},
                            {"brand": "Zenith", "product_name": "Zenith Cream", "main_image": None, "product_url": None,
                             "sale_price_thb": "199.00", "Category": "Skincare", "Sub_category": "Face Moisture"}])
    return ctx, coverage, catalog


def test_fit_level_and_quadrant():
    assert [fit_level(r, TH_RANKS) for r in (1, 25, 26, 100, 101, 500, 501, None)] == \
        ["leading", "leading", "competitive", "competitive", "behind", "behind", "gap", "gap"]
    strong = DEFAULT_CONFIG["strong_fit_levels"]
    assert quadrant(0.9, "leading", 0.7, strong) == "defend"
    assert quadrant(0.9, "gap", 0.7, strong) == "build"
    assert quadrant(0.5, "competitive", 0.7, strong) == "maintain"
    assert quadrant(0.5, "behind", 0.7, strong) == "monitor"


def test_brand_context_uses_market_rank_not_coverage_tier(run_dir):
    """tier ของ ⑬ บอก "ตามทัน" แต่อันดับจริง 3,049 -> ระดับต้องเป็น "ช่องว่าง" (ปัญหาที่เจอจริงกับ Sureeporn)"""
    ctx, coverage, catalog = _brand_fixture(run_dir, best_rank=3049)
    b = build_brand_context(ctx, coverage, catalog, DEFAULT_CONFIG)
    assert b["rows"][0]["level"] == "gap"
    assert b["counts"] == {"leading": 0, "competitive": 0, "behind": 0, "gap": 1}


def test_brand_context_rows_leader_and_missing(run_dir):
    ctx, coverage, catalog = _brand_fixture(run_dir)
    b = build_brand_context(ctx, coverage, catalog, DEFAULT_CONFIG)
    first, second = b["rows"]
    assert first["level"] == "leading" and first["checked"]
    assert first["leader"]["brand"] == "Other" and first["leader"]["price_thb"] == 1290.0
    assert first["gap_to_leader"] == 0.05
    assert first["products"][0]["price_thb"] == 199.0
    assert not second["checked"] and b["missing_trends"] == ["Stable Retinol"]   # ผล ⑬ ไม่มีเทรนด์นี้
    assert b["highlights"]["strongest"] == 1 and b["n_checked"] == 1
    assert b["portfolio"]["n_skus"] == 1 and b["portfolio"]["price_min"] == 199.0


def test_find_coverage_file(run_dir):
    assert find_coverage_file(run_dir, "zenith").name == "phase3_brand_coverage_Zenith.json"   # ไม่สนตัวพิมพ์
    assert find_coverage_file(run_dir, "Zenit").name == "phase3_brand_coverage_Zenith.json"    # พิมพ์ตกไป 1 ตัว
    assert find_coverage_file(run_dir, "Nothing Like It") is None


def test_render_brand_report_both_languages(run_dir):
    ctx, coverage, catalog = _brand_fixture(run_dir)
    brand_style = {**BRAND, "company_name": "S&J"}
    b_en = build_brand_context(ctx, coverage, catalog, DEFAULT_CONFIG)
    en = render_brand_html(ctx, b_en, brand_style, {}, "Zenith × Topic Trends", datetime(2026, 9, 26))
    # ปก + สรุป + matrix + ตารางภาพรวม + เทรนด์ละ 1 หน้า (2) + โอกาส + ภาคผนวก
    assert en.count('<section class="page') == 4 + 2 + 2
    assert "Executive Summary | Zenith" in en and "Market leader" in en and "Other Cream" in en
    assert "Paper" not in en and "Social" not in en                                     # ไม่แสดงสายหลักฐาน
    lth = localize(ctx, "th")
    b_th = apply_th(build_brand_context(lth, coverage, catalog, DEFAULT_CONFIG), {"Barrier Care": ["ช่วยปลอบผิว"]})
    th = render_brand_html(lth, b_th, brand_style, {}, "Zenith × เทรนด์ Topic", datetime(2026, 9, 26), lang="th")
    assert th.count('<section class="page') == en.count('<section class="page')
    assert "สรุปผู้บริหาร | Zenith" in th and "เจ้าตลาด" in th and "ช่วยปลอบผิว" in th


def test_fit_matrix_svg(run_dir):
    ctx, coverage, catalog = _brand_fixture(run_dir)
    b = build_brand_context(ctx, coverage, catalog, DEFAULT_CONFIG)
    labels = {"x": "x", "y": "y", "levels": {"leading": "L", "competitive": "C", "behind": "B", "gap": "G"},
              "defend": "D", "build": "Bu", "maintain": "M", "monitor": "Mo"}
    svg = fit_matrix_svg(b["rows"], b["momentum_split"], 100, TH_RANKS, 10622, labels)
    assert svg.startswith("<svg")
    assert fit_matrix_svg([r for r in b["rows"] if not r["checked"]], 0.5, 100, TH_RANKS, 10622, labels) is None


def test_translate_items_th_caches():
    calls = []

    def fake_llm(system, user, max_tokens=900):
        calls.append(user)
        return json.dumps({"items": ["ช่วยปลอบผิว", "ให้ความชุ่มชื้น"]})

    groups = {"Barrier Care": ["Soothes skin.", "Moisturises."]}
    tr, cache, counts = translate_items_th(groups, {}, llm_call=fake_llm, max_workers=1, log=lambda *_: None)
    assert tr == {"Barrier Care": ["ช่วยปลอบผิว", "ให้ความชุ่มชื้น"]} and counts == {"llm": 1}
    calls.clear()
    tr2, _, counts2 = translate_items_th(groups, cache, llm_call=None, log=lambda *_: None)
    assert tr2 == tr and calls == [] and counts2 == {"llm (cached)": 1}
