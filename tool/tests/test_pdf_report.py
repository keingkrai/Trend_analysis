# -*- coding: utf-8 -*-
"""
เทสของ ⑯ PDF Report (tool/phase6_pdf_report/) - ไม่ยิง API และไม่เปิด Chromium
ใช้โฟลเดอร์รอบปลอมใน tmp_path: ตรวจว่าไฟล์ขาดแล้วรายงานยังประกอบได้ (แค่จดไว้ใน missing), ข้อความไทยที่เป็นค่าตายตัว
ถูกแปลงเป็นอังกฤษ, cache ของ LLM ใช้ซ้ำได้จริง และเทมเพลตได้จำนวนหน้าตรงตามข้อมูล

รัน: pytest main/tool/tests/test_pdf_report.py -v
"""
import html
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase6_pdf_report"))

from datetime import datetime  # noqa: E402

import pytest  # noqa: E402

import pandas as pd  # noqa: E402
from enrich import enrich_trends, fallback_texts, validate  # noqa: E402
from render import render_html  # noqa: E402
from report_data import (build_context, cagr_pct, first_sentences, smart_title, split_headline,  # noqa: E402
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
    ok = {"headline": "A", "trend": "B", "insight": "C"}
    assert validate(ok) == ok
    assert validate({**ok, "trend": "มีภาษาไทย"}) is None
    assert validate({**ok, "workshop_question": "How can your brand do X?"}) == ok   # cache เก่าที่ยังมีคำถามเวิร์กช็อป: ช่องนี้ถูกทิ้ง ไม่ทำให้ตกการตรวจ
    assert validate({"headline": "A"}) is None


def test_enrich_uses_cache_and_falls_back(run_dir):
    ctx, _ = build_context(run_dir)
    calls = []

    def fake_llm(system, user):
        calls.append(user)
        if "Stable Retinol" in user:
            raise RuntimeError("boom")
        return json.dumps({"headline": "H", "trend": "T", "insight": "I"})

    cache, counts = enrich_trends(ctx["trends"], {}, llm_call=fake_llm, max_workers=1, log=lambda *_: None)
    assert counts == {"llm": 1, "fallback": 1}
    assert ctx["trends"][0]["text"]["headline"] == "H"
    assert all("workshop_question" not in t["text"] for t in ctx["trends"])

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
    assert "workshop_question" not in out


def test_render_page_count(run_dir):
    ctx, _ = build_context(run_dir)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    for t in ctx["trends"]:
        for p in t["products"]:
            p["image"] = None
    html = render_html(ctx, BRAND, {}, "Topic Trend Forecast", datetime(2026, 1, 1), "2 fallback")
    # ปก + summary + overview + หน้าคั่น + 2 หน้าต่อเทรนด์ + appendix 2 หน้า (ไม่มีหน้าแบรนด์)
    # (ไม่มี takeaway/STEPIC/personas/signals เพราะรอบปลอมไม่มีไฟล์ STEPIC, ไม่มีหน้า Top 5/ภาพรวมเพราะไม่มีคะแนนการเติบโต)
    # 🆕 (2026-09-30) ไม่มีหน้า Dashboard / แผนที่กลยุทธ์ 2x2 / Trend Map แล้ว (สร้างจาก Z_Delta)
    assert html.count('<section class="page') == 4 + 2 * 2 + 2
    assert "Z_Delta" not in html and "z-score" not in html
    assert "Paper" not in html and "Social" not in html  # ไม่แสดงสายหลักฐาน
    assert "Live Commerce" not in html                   # เทรนด์ที่ถูกข้ามไม่อยู่ในรายงาน (หน้า Notes ไม่มีรายชื่อแล้ว)
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


# ============================================================================
# 🆕 (2026-09-30) หน้าเทรนด์ไม่มี Z_Delta แล้ว: ช่องตัวเลขจากคะแนนการเติบโต + กราฟการค้นหาจริง (ไม่มีเส้นพยากรณ์)
# ============================================================================
from charts import growth_chart_svg, history_chart_svg  # noqa: E402
from report_data import long_term_grade  # noqa: E402


def _history(months=60, base=20.0, jump_last12=10.0):
    dates = pd.date_range(end="2026-08-01", periods=months, freq="MS")
    values = [base + (jump_last12 if i >= months - 12 else 0.0) for i in range(months)]
    return {"months": [d.strftime("%Y-%m") for d in dates], "values": values}


def test_longevity_grade_thresholds():
    # 70+ / 55+ / 40+ / ต่ำกว่า 40 และหลักฐานไม่พอแยกออกมา ไม่นับเป็น average
    assert [long_term_grade(s) for s in (85, 70, 69, 55, 54, 40, 39, 5, None)] == [
        "excellent", "excellent", "good", "good", "average", "average", "below_average", "below_average", None]
    assert long_term_grade(50, insufficient=True) == "insufficient"


def test_history_chart_shows_actual_windows_and_forecast_years():
    svg = history_chart_svg(_history())
    assert svg.startswith("<svg") and "Last 12 months" in svg and "Previous year" in svg
    assert "avg 30" in svg and "avg 20" in svg and "Year 1" not in svg          # ไม่มีค่าคาด -> ไม่มีส่วนคาดการณ์
    fc = {"base": 30.0, "levels": [33.0, 35.0, 36.0], "change_pct": [9.7, 16.1, 19.4],
          "low": [28.7, 29.1, 29.6], "high": [37.1, 42.2, 45.9]}
    svg = history_chart_svg({**_history(), "forecast": fc})
    assert "Year 1" in svg and "Year 3" in svg and "+10%" in svg and "+8%" in svg and "+6%" in svg
    assert "+19%" not in svg and "+16%" not in svg                       # ไม่ใช่ตัวเลขสะสม (เขียนเป็น CAGR ตั้งแต่ 2026-10-14)
    wave = {"months": [str(p)[:7] for p in pd.date_range("2026-09-01", periods=36, freq="MS")],
            "values": [33.0 + (5 if i % 12 < 6 else -5) for i in range(36)]}
    with_wave = history_chart_svg({**_history(), "forecast": {**fc, "monthly": wave}})
    assert with_wave.startswith("<svg") and len(with_wave) > len(svg)          # มีเส้นคลื่นรายเดือนเพิ่ม
    th = history_chart_svg({**_history(), "forecast": fc}, lang="th")
    assert "12 เดือนล่าสุด" in th and "เฉลี่ย 30" in th and "ปีที่ 2" in th
    assert history_chart_svg(None) is None and history_chart_svg(_history(months=20)) is None


def test_growth_chart_has_cagr_line_and_yoy_numbers_under_each_year():
    """🆕 (2026-10-19) กราฟหน้ารายเทรนด์: ตัวเลข CAGR เหนือจุด + ชื่อปี + ตัวเลข YoY ใต้แกน (ปี 1 เทียบ 12 เดือนล่าสุด จึงเท่า CAGR)"""
    cum = [8.4, 12.0, 15.2, 20.1, 30.4]
    cagr, yoy = [cagr_pct(v, i + 1) for i, v in enumerate(cum)], yoy_series(cum)
    svg = growth_chart_svg(cagr, yoy)
    assert svg.startswith("<svg") and all(f"Year {n}" in svg for n in range(1, 6))
    assert "+8%" in svg and "+6%" in svg and "+5%" in svg                    # CAGR ปี 1, 2, 3-5 (ปัดจากค่าจริง)
    assert "+3%" in svg and "+4%" in svg and "+9%" in svg                    # YoY ปี 2/3, 4, 5
    assert "CAGR" not in svg and "YoY" not in svg                            # ไม่มีศัพท์ในกราฟ - legend อธิบายด้วยสี
    th = growth_chart_svg(cagr, yoy, lang="th")
    assert "ปีที่ 1" in th and "ปีที่ 5" in th
    assert growth_chart_svg(None, None) is None and growth_chart_svg([None] * 5, [None] * 5) is None
    partial = growth_chart_svg([10.0, None, 8.0, None, None], [10.0, None, None, None, None])      # ปีที่ขาด -> ไม่พัง ป้าย n/a
    assert partial.startswith("<svg") and "n/a" in partial
    assert growth_chart_svg([-5.0, 2.0, 3.0, 3.0, 4.0], yoy_series([-5.0, -3.0, -1.0, 2.0, 5.0])).startswith("<svg")   # ติดลบ


def _rendered_ctx(run_dir):
    ctx, _ = build_context(run_dir)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None, lang="th")
    # 🆕 (2026-10-02) 5 ปี: ระยะสั้น = ปีที่ 2 (คะแนน 0.82), ระยะยาว = ปีที่ 5
    for t, (grades, past, decline, lon) in zip(ctx["trends"], [([4, 4, 3, 3, 3], 31.0, False, 51),
                                                                ([3, 2, 2, 2, 2], -6.0, True, 85)]):
        t.update(growth={"scores": [0.85, 0.82, 0.82, 0.6, 0.6], "grades": grades, "past_growth_pct": past,
                         "recent_change_pct": -15.0 if decline else 8.0, "recent_decline": decline,
                         "forecast_pct": [8.4, 12.0, 15.2, 20.1, 30.4] if not decline else [None] * 5,
                         "forecast_cagr": ([cagr_pct(v, i + 1) for i, v in enumerate([8.4, 12.0, 15.2, 20.1, 30.4])]
                                           if not decline else [None] * 5)},
                 longevity_score=lon, long_term_grade=long_term_grade(lon))
    for t in ctx["trends"]:
        for p in t["products"]:
            p["image"] = None
    return ctx


def test_trend_pages_use_growth_kpis_and_no_z_delta(run_dir):
    ctx = _rendered_ctx(run_dir)
    html = render_html(ctx, BRAND, {"Barrier Care": "data:image/svg+xml;base64,AAAA"}, "T", datetime(2026, 1, 1), "x")
    assert 'data-label="Workshop' not in html                        # ไม่มีหน้า Workshop เดี่ยวแล้ว
    assert len(re.findall(r'data-label="Trend \d', html)) == 2 and html.count('data-label="Evidence ') == 2
    assert 'class="ws"' not in html and "Workshop Question" not in html    # 🆕 (2026-10-28) ตัดแถบคำถามเวิร์กช็อปออกจากหน้าเทรนด์
    for gone in ("Trend Dashboard", "Strategy Matrix", "Trend Map", "Rank Trajectory"):
        assert f'data-label="{gone}"' not in html
    assert "Z_Delta" not in html and "Invest" not in html and "Harvest" not in html
    # ช่องตัวเลข: ระยะสั้น ปีที่ 3 / ระยะยาว ปีที่ 5 (% ที่คาด - 🆕 2026-10-02 แทนแถบ "เร็ว/ช้ากว่าตลาด"; 2026-10-19 ระยะสั้น 2 -> 3 ปี)
    # / 12 เดือนที่ผ่านมา (ข้อมูลจริง) / แหล่ง + Longevity
    assert "Short term · year 3" in html and "Long term · year 5" in html and "Last 12 months (actual)" in html
    # 🆕 (2026-10-14) KPI = CAGR: สะสมปีที่ 3 +15.2% -> +4.8% ต่อปี (+5%), สะสมปีที่ 5 +30.4% -> +5.5% ต่อปี (+5%)
    assert html.count("+5%<small>a year on average, vs last 12 months</small>") == 2
    assert "+15%<small>" not in html and "+30%<small>" not in html and "year 2" not in html
    assert "Blue figures = average growth per year (compounded) vs the last 12 months; grey figures = change vs the year before" in html
    assert "faster than market" not in html.lower() and "+31%" in html and "-6%" in html
    assert "Searches down in the last 6 months" in html and "Last 6 months +8% vs a year earlier" in html
    assert "Durability 51/100" in html and "</span>Average</span>" in html      # Longevity 51 = Average
    assert "Year 3 · " in html and "Year 5 · " in html                            # ช่วงเวลาใต้ตัวเลข
    # 🆕 (2026-10-19) กราฟหน้าเทรนด์ = เส้น CAGR + แท่ง YoY ปี 1-5 (legend ไม่ใช้ศัพท์) แทนกราฟประวัติ + แถบ 80%
    assert "Average growth per year</span>" in html and "Change vs the year before</span>" in html
    assert "Expected monthly" not in html and "80% range of yearly avg" not in html and "Actual</span>" not in html
    assert "<b>Expected growth in searches</b>" in html and "No forecast for this trend in this run" in html   # เทรนด์ 2 ไม่มีกราฟ
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "ระยะสั้น · ปีที่ 3" in th and "ระยะยาว · ปีที่ 5" in th and "เร็วกว่าตลาด" not in th and "โอกาสอยู่ยาว 51/100" in th
    assert "ความยั่งยืน" not in th and "ปีที่ 3: คาดว่ายอดค้นหาเพิ่มมากกว่า 82% ของคีย์เวิร์ดในตลาด" in th
    # คะแนนปีระยะสั้น (ปีที่ 3 = 0.82) แสดงเป็น % ของคีย์เวิร์ดในตลาด ไม่ใช่เลข 0-1 / ไม่มีผลการเติบโตของรอบ -> ไม่มีหมายเหตุ *
    assert "Year 3: expected to rise more than 82% of market keywords" in html and "Growth score 0." not in html
    assert 'class="kpi-note"' not in html and "Last 12 months (actual)*" not in html
    assert "Z_Delta" not in th and th.count('<section class="page') == html.count('<section class="page')


def test_market_overview_has_no_z_delta(run_dir):
    ctx = _rendered_ctx(run_dir)
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    page = html[html.index('data-label="Market Overview"'):]
    page = page[:page.index("</section>")]
    assert "Trends above the market (year 3)" in page and "mbar" not in page and "Momentum by trend" not in page


# ============================================================================
# หน้าสินค้าแยกหมวด (⑫ by_category) - feedback: แยกสินค้า 3-5 หมวดต่อเทรนด์
# ============================================================================
def _match_product(name, group, sim, rank, price=199.0):
    return {"product_name": name, "brand": "Acme", "category": "Skincare", "group": group, "similarity": sim,
            "sale_price_thb": price, "sold_count": None, "rank_in_market": rank}


def _with_categories(run_dir):
    """ผล ⑫ ปลอม: Barrier Care มี by_category 2 หมวด, Stable Retinol เป็นผลรอบเก่า (ไม่มี by_category)"""
    _write(run_dir, "phase3_scale_validation_nvidia_result.json", {"n_products_total": 1000, "results": {
        "Social::Barrier Care": {
            "n_products_compared": 1000, "top_matches": [_match_product("Cream A", "Face Moisture", 0.4, 1)],
            "by_category": {"pool_size": 10,
                            "distribution": [{"group": "Face Moisture", "n": 6}, {"group": "Baby Skincare", "n": 3},
                                             {"group": None, "n": 1}],
                            "categories": [
                                {"group": "Face Moisture", "n_pool": 6, "n_total": 300, "median_price_thb": 250,
                                 "min_price_thb": 99, "max_price_thb": 1290,
                                 "products": [_match_product("Cream A 50 ml. ครีมบำรุง", "Face Moisture", 0.4, 1)]},
                                {"group": "Baby Skincare", "n_pool": 3, "n_total": 40, "median_price_thb": 150,
                                 "min_price_thb": 120, "max_price_thb": 180,
                                 "products": [_match_product("Baby Lotion", "Baby Skincare", 0.3, 4)]}]}},
        "Paper::Stable Retinol": {"n_products_compared": 1000,
                                  "top_matches": [_match_product("Serum B", "Face Moisture", 0.35, 1)]},
    }})
    return _rendered_ctx(run_dir)


def test_build_context_reads_categories_and_keeps_old_runs(run_dir):
    ctx = _with_categories(run_dir)
    cats = ctx["trends"][0]["categories"]
    assert [c["group"] for c in cats["categories"]] == ["Face Moisture", "Baby Skincare"]
    assert cats["pool_pct"] == "1" and cats["max_similarity"] == 0.4
    assert cats["categories"][0]["products"][0]["name"] == "Cream A 50 ml."    # ตัดคำอธิบายไทยออกในฉบับอังกฤษ
    assert cats["categories"][1]["products"][0]["rank_in_market"] == 4
    assert ctx["trends"][1]["categories"] is None                              # ผล ⑫ รอบเก่า


def test_render_category_evidence_page_with_fallback(run_dir):
    ctx = _with_categories(run_dir)
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert html.count('class="cat-cols"') == 1 and html.count('class="prod-row"') == 1   # เทรนด์ 2 ใช้หน้าแบบเดิม
    assert "Which categories the top 10 matches for this trend belong to" in html and "(the best 1% of 1,000 products)" in html
    assert "#4 match in the whole store" in html and "Other categories" in html
    ev = html[html.index('data-label="Evidence 1"'):]
    assert "SKU" not in ev[:ev.index("</section>")]                            # หน้าหลักไม่ใช้คำว่า SKU (ภาคผนวกใช้ได้)
    assert html.count('<span class="pa">All product types</span>') == 2                # ผลเก่าไม่มี parent/subgroup ยังแสดงได้
    assert "four categories holding the most" in html                          # ภาคผนวกบอกวิธีแยกหมวด
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "Cream A 50 ml. ครีมบำรุง" in th and "ตรงเทรนด์อันดับ 4 จากทั้งร้าน" in th and "หมวดอื่น" in th and "ทุกชนิดสินค้า" in th
    assert th.count('<section class="page') == html.count('<section class="page')


def test_render_split_category_columns_share_parent_colour(run_dir):
    """🆕 (2026-10-01) หมวดที่ครองหน้าแตกเป็นชนิดสินค้า: หัวคอลัมน์ 2 บรรทัด สีตามหมวดแม่ จำนวนคอลัมน์ตามที่มีจริง"""
    _write(run_dir, "phase3_scale_validation_nvidia_result.json", {"n_products_total": 1000, "results": {
        "Social::Barrier Care": {
            "n_products_compared": 1000, "top_matches": [_match_product("Shampoo A", "Hair Care", 0.4, 1)],
            "by_category": {"pool_size": 10, "distribution": [{"group": "Hair Care", "n": 9}, {"group": None, "n": 1}],
                            "categories": [
                                {"group": "Hair Care · Shampoo", "parent": "Hair Care", "subgroup": "Shampoo", "color": 0,
                                 "n_pool": 5, "n_total": 300, "products": [_match_product("Shampoo A", "Hair Care", 0.4, 1)]},
                                {"group": "Hair Care · Hair Oil & Serum", "parent": "Hair Care", "subgroup": "Hair Oil & Serum",
                                 "color": 0, "n_pool": 4, "n_total": 80,
                                 "products": [_match_product("Oil B", "Hair Care", 0.3, 2)]}]}},
    }})
    ctx = _rendered_ctx(run_dir)
    cats = ctx["trends"][0]["categories"]["categories"]
    assert [(c["parent"], c["subgroup"], c["color"]) for c in cats] == [("Hair Care", "Shampoo", 0), ("Hair Care", "Hair Oil & Serum", 0)]
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert 'grid-template-columns: repeat(2, 1fr)' in html
    assert html.count('<div class="ch cat-c0"><span class="pa">Hair Care</span>') == 2 and "cat-c1" not in html.split('class="cat-cols"')[1]
    assert "the largest is split by product type" in html


def test_render_category_columns_by_price_tier(run_dir):
    """🆕 (2026-10-07) คอลัมน์ที่มีช่วงราคา: แถว = ช่วงราคาตลาด (ชิ้นที่ใกล้ที่สุดของแต่ละช่วง) + จำนวนใกล้เทรนด์ต่อช่วง
    คอลัมน์ไม่มีช่วงราคา (ผล ⑫ รอบเก่า) ยังเป็น 3 ชิ้นเดิม"""
    def tier(label, lo, hi, n_pool, name, rank, price):
        return {"label": label, "price_from": lo, "price_to": hi, "n_total": 100, "n_pool": n_pool,
                "product": _match_product(name, "Skin Care", 0.4 - rank / 100, rank, price)}

    _write(run_dir, "phase3_scale_validation_nvidia_result.json", {"n_products_total": 1000, "results": {
        "Social::Barrier Care": {
            "n_products_compared": 1000, "top_matches": [_match_product("Gel A", "Skin Care", 0.4, 1)],
            "by_category": {"pool_size": 10, "distribution": [{"group": "Skin Care", "n": 10}],
                            "categories": [
                                {"group": "Skin Care", "n_pool": 8, "n_total": 300,
                                 "products": [_match_product("Gel A", "Skin Care", 0.4, 1)],
                                 "price_tiers": [tier("low", 29, 198, 3, "Gel Low ครีมเจล", 7, 149.0),
                                                 tier("mid", 199, 340, 0, "Gel Mid", 26, 275.0),
                                                 tier("high", 341, 1290, 5, "Gel A", 1, 699.0)]},
                                {"group": "Sun Care", "n_pool": 2, "n_total": 50,
                                 "products": [_match_product("Sun B", "Sun Care", 0.3, 4)]}]}},
    }})
    ctx = _rendered_ctx(run_dir)
    cats = ctx["trends"][0]["categories"]
    assert cats["has_tiers"] and cats["categories"][1]["price_tiers"] is None
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert html.count('class="cp tiered"') == 3
    assert "By price: Low 3 · Mid 0 · High 5" in html
    assert "<b>Low price</b> THB 29-198" in html and "<b>High price</b> THB 341-1,290" in html
    assert "#26 match in the whole store" in html and "Gel Low" in html and "ครีมเจล" not in html
    assert "#4 match in the whole store" in html                                # คอลัมน์ไม่มีช่วงราคา = แบบเดิม
    assert "Price tiers split every product" in html and "by price tier - low, mid and high thirds" in html
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "แยกตามราคา: ต่ำ 3 · กลาง 0 · สูง 5" in th and "<b>ราคาต่ำ</b> 29-198 บาท" in th
    assert "Gel Low ครีมเจล" in th and "ช่วงราคา = แบ่งสินค้าทั้งร้าน" in th


def test_render_category_page_with_llm_main_category(run_dir):
    """🆕 (2026-10-08) หมวดหลักที่ LLM เลือก (by_category.main_category): หัวหน้า/แถบ/หมายเหตุพูดถึงหมวดหลักและชนิดสินค้า
    ไม่ใช่ "หมวดไหนถือสินค้าใกล้เทรนด์" - ผลรอบเก่า (ไม่มี main_category) คงข้อความเดิม (ทดสอบข้างบน)"""
    def tier(label, lo, hi, n_pool, name, rank, price):
        return {"label": label, "price_from": lo, "price_to": hi, "n_total": 100, "n_pool": n_pool,
                "product": _match_product(name, "Skin Care", 0.4 - rank / 100, rank, price)}

    def col(sub, n_pool, color):
        return {"group": f"Skin Care · {sub}", "parent": "Skin Care", "subgroup": sub, "color": color, "n_pool": n_pool,
                "n_total": 120, "products": [_match_product(f"{sub} A", "Skin Care", 0.4, 1)],
                "price_tiers": [tier("low", 29, 198, 1, f"{sub} Low", 7, 149.0), tier("mid", 199, 340, 2, f"{sub} Mid", 9, 275.0),
                                tier("high", 341, 1290, 3, f"{sub} High", 12, 699.0)]}

    _write(run_dir, "phase3_scale_validation_nvidia_result.json", {"n_products_total": 1000, "results": {
        "Social::Barrier Care": {
            "n_products_compared": 1000, "top_matches": [_match_product("Serum A", "Skin Care", 0.4, 1)],
            "by_category": {"pool_size": 10, "main_category": "Skin Care", "n_category": 3231,
                            "distribution": [{"group": "Serum", "n": 6}, {"group": "Cream", "n": 4}],
                            "categories": [col("Serum", 6, 0), col("Cream", 4, 1)]}},
    }})
    ctx = _rendered_ctx(run_dir)
    cats = ctx["trends"][0]["categories"]
    assert cats["main_category"] == "Skin Care" and cats["main_n_total"] == 3231
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert "in its main category: Skin Care" in html
    assert "Which Skin Care product types the top 10 matches for this trend belong to" in html and "this category has 3,231 products" in html
    assert '<span class="pa">Skin Care</span>Serum' in html and '<span class="pa">Skin Care</span>Cream' in html
    assert html.count('class="cp tiered"') == 6 and "chosen by AI" in html and "An AI then chooses" in html
    assert "Which categories hold" not in html
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "หมวดหลักของเทรนด์: Skin Care" in th and "ในหมวด Skin Care เป็นสินค้าชนิดไหนบ้าง" in th and "ให้ AI เลือก" in th


# ============================================================================
# 🆕 (2026-10-08) ชื่อที่แสดงในรายงาน (display_names.py) - ชื่อในไปป์ไลน์ไม่เปลี่ยน
# ============================================================================
from display_names import DISPLAY_FILE, apply_display_names, load_display_names  # noqa: E402


def test_display_names_load_and_apply(run_dir):
    assert load_display_names(run_dir) == {}                                    # ไม่มีไฟล์ = ชื่อเดิม
    _write(run_dir, DISPLAY_FILE, {"names": {"Social::Barrier Care": {"display": "Skin Recovery Needs", "source": "manual"},
                                             "News::Unknown": {"display": "  ", "source": "manual"},
                                             "Paper::Draft": {"display": "Draft Name", "source": "llm", "approved": False},
                                             "Paper::Ok": {"display": "Checked Name", "source": "llm", "approved": True}}})
    names = load_display_names(run_dir)
    # ชื่อว่างไม่นับ / ร่างจาก LLM ที่ยังไม่ผ่านการตรวจไม่ใช้ / ร่างที่ตรวจแล้ว (approved) ใช้
    assert names == {"Social::Barrier Care": "Skin Recovery Needs", "Paper::Ok": "Checked Name"}
    ctx = _rendered_ctx(run_dir)
    t = next(x for x in ctx["trends"] if x["key"] == "Social::Barrier Care")
    t["text"]["insight"] = "Barrier care keeps growing; BARRIER CARE fans want calm skin."
    t["text_th"] = {**(t.get("text_th") or {}), "insight": "เทรนด์ Barrier Care โตต่อ"}
    shared = t["text"]   # ข้อความใน ctx อาจเป็น object เดียวกับ cache ของ LLM - ต้องไม่ถูกแก้ (สำเนาใหม่เท่านั้น)
    assert apply_display_names(ctx, names) == 1
    assert shared["insight"].startswith("Barrier care")
    t = next(x for x in ctx["trends"] if x["key"] == "Social::Barrier Care")
    assert (t["name"], t["key"], t["display_name"]) == ("Barrier Care", "Social::Barrier Care", "Skin Recovery Needs")
    assert t["text"]["insight"] == "Skin Recovery Needs keeps growing; Skin Recovery Needs fans want calm skin."
    assert t["text_th"]["insight"] == "เทรนด์ Skin Recovery Needs โตต่อ"
    other = next(x for x in ctx["trends"] if x["key"] != "Social::Barrier Care")
    assert other["display_name"] == other["name"]                               # ไม่มีในไฟล์ = ชื่อเดิม


def test_render_uses_display_names(run_dir):
    _write(run_dir, DISPLAY_FILE, {"names": {"Social::Barrier Care": {"display": "Skin Recovery Needs", "source": "manual"}}})
    ctx = _rendered_ctx(run_dir)
    apply_display_names(ctx, load_display_names(run_dir))
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    body = re.sub(r"<style>.*?</style>|<script>.*?</script>", "", html, flags=re.S)
    assert "<h2>Skin Recovery Needs</h2>" in body and "Barrier Care" not in body
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "<h2>Skin Recovery Needs</h2>" in th


def test_brand_reports_use_display_names(run_dir):
    ctx, coverage, catalog = _brand_fixture(run_dir, rank=20)
    t = next(x for x in ctx["trends"] if x["name"] == "Barrier Care")
    apply_display_names(ctx, {t["key"]: "Skin Recovery Needs"})
    b = build_brand_context(ctx, coverage, catalog, DEFAULT_CONFIG)
    row = next(r for r in b["rows"] if r["name"] == "Barrier Care")             # name ยังเป็นชื่อเดิม (ใช้จับคู่ผล ⑬)
    assert row["display_name"] == "Skin Recovery Needs" and row["checked"]
    html = render_brand_html(ctx, b, {**BRAND, "company_name": "S&J"}, {}, "T", datetime(2026, 9, 26))
    assert "<h2>Skin Recovery Needs</h2>" in html and ">Barrier Care<" not in html


# ============================================================================
# เฟส C: Means-End 3 บรรทัด (แทนย่อหน้า Trend/Insight) และ heatmap เทรนด์ x แรงขับ STEPIC / persona
# ============================================================================
from enrich import condense_means_end, validate_ladder  # noqa: E402
from trend_links import SYSTEM_PROMPT_LINKS_FORCES, link_trends, validate_links  # noqa: E402

LADDER_PAYLOAD = {"trend_name": "Barrier Care", "profile_th": {"point_of_difference": "ซ่อมเกราะผิว",
                                                               "functional_consequence": "ลดการระคายเคือง"},
                  "context_th": {}}
LADDER_OK = {"en": {"difference": "Repairs the skin barrier", "benefit": "Less irritation", "feeling": ""},
             "th": {"difference": "ซ่อมเกราะผิว", "benefit": "ลดการระคายเคือง", "feeling": ""}}


def test_validate_ladder():
    assert validate_ladder(LADDER_OK, LADDER_PAYLOAD) == LADDER_OK
    # ต้นทางไม่มี psychosocial_consequence -> บังคับบรรทัด feeling เป็นค่าว่าง แม้โมเดลจะเขียนมา
    extra = {"en": {**LADDER_OK["en"], "feeling": "Calm"}, "th": {**LADDER_OK["th"], "feeling": "สบายใจ"}}
    assert validate_ladder(extra, LADDER_PAYLOAD)["en"]["feeling"] == ""
    assert validate_ladder({**LADDER_OK, "en": {**LADDER_OK["en"], "benefit": ""}}, LADDER_PAYLOAD) is None
    assert validate_ladder({**LADDER_OK, "en": {**LADDER_OK["en"], "benefit": "ลด"}}, LADDER_PAYLOAD) is None
    too_long = " ".join(["word"] * 20)
    assert validate_ladder({**LADDER_OK, "en": {**LADDER_OK["en"], "benefit": too_long}}, LADDER_PAYLOAD) is None
    assert validate_ladder({**LADDER_OK, "th": {**LADDER_OK["th"], "benefit": "Less irritation"}}, LADDER_PAYLOAD) is None


def test_condense_means_end_caches_and_skips_empty_profiles(run_dir):
    ctx, _ = build_context(run_dir)   # Barrier Care มีแค่ job_to_be_done, Stable Retinol ไม่มีโปรไฟล์
    ctx["trends"][0]["profile"] = {"point_of_difference": "ซ่อมเกราะผิว", "functional_consequence": "ลดการระคายเคือง",
                                   "psychosocial_consequence": "ข้อมูลไม่พอ"}
    calls = []

    def fake_llm(system, user, max_tokens=900):
        calls.append(user)
        return json.dumps(LADDER_OK)

    cache = {}
    counts = condense_means_end(ctx["trends"], cache, llm_call=fake_llm, max_workers=1, log=lambda *_: None)
    assert counts == {"llm": 1, "paragraphs (fallback)": 1} and len(calls) == 1
    assert ctx["trends"][0]["ladder"]["difference"] == "Repairs the skin barrier"
    assert ctx["trends"][0]["ladder_th"]["benefit"] == "ลดการระคายเคือง"
    assert "ladder" not in ctx["trends"][1]
    calls.clear()
    assert condense_means_end(ctx["trends"], cache, llm_call=None, log=lambda *_: None)["llm (cached)"] == 1
    assert calls == []


STEPIC = [{"dimension": d, "headline": f"{d} shift", "body": "b"} for d in ("Society", "Technology", "Environment",
                                                                            "Policy", "Industry", "Creativity")]
PERSONAS = [{"name": "The Curator", "description": "d", "value_driver": "v"},
            {"name": "The Parent", "description": "d", "value_driver": "v"}]


def _links_answer(society=2, curator=1, evidence="barrier repair is science-led"):
    stepic = {s["dimension"]: {"level": 0, "evidence": ""} for s in STEPIC}
    stepic["Society"] = {"level": society, "evidence": evidence}
    stepic["Technology"] = {"level": 1, "evidence": ""}           # ระดับ > 0 ไม่มีหลักฐาน -> ต้องถูกปรับเป็น 0
    return {"stepic": stepic, "personas": [{"level": curator, "evidence": "evidence-first buyers"},
                                           {"level": 0, "evidence": ""}]}


def test_validate_links_drops_marks_without_evidence():
    payload = {"stepic_forces": [{"force": s["dimension"]} for s in STEPIC], "personas": PERSONAS}
    out = validate_links(_links_answer(), payload)
    assert out["stepic"]["Society"]["level"] == 2 and out["stepic"]["Technology"] == {"level": 0, "evidence": ""}
    assert [p["level"] for p in out["personas"]] == [1, 0]
    assert validate_links({**_links_answer(), "personas": [{"level": 1, "evidence": "x"}]}, payload) is None
    bad = _links_answer()
    bad["stepic"]["Policy"] = {"level": 3, "evidence": "x"}
    assert validate_links(bad, payload) is None
    del bad["stepic"]["Policy"]
    assert validate_links(bad, payload) is None                    # ขาดแรงขับ
    assert validate_links(_links_answer(evidence="มีภาษาไทย"), payload) is None


def test_link_trends_summary_and_cache(run_dir):
    ctx, _ = build_context(run_dir)
    ctx["stepic"], ctx["personas"] = STEPIC, PERSONAS

    def fake_llm(system, user, max_tokens=1500):
        return json.dumps(_links_answer(society=2 if "Barrier Care" in user else 1))

    cache = {}
    assert link_trends(ctx, cache, llm_call=fake_llm, max_workers=1, log=lambda *_: None) == {"llm": 2}
    s = ctx["links_summary"]
    assert s["stepic"]["Society"] == {"main": 1, "any": 2} and s["stepic"]["Technology"] == {"main": 0, "any": 0}
    assert s["personas"][0] == {"main": 0, "any": 2} and s["n_trends"] == 2
    assert link_trends(ctx, cache, llm_call=None, log=lambda *_: None) == {"llm (cached)": 2}
    # 🆕 (2026-10-28) ไม่มี persona (รอบสาย Search) -> ถามเฉพาะแรงขับ (cache เดิมใช้ไม่ได้เพราะข้อมูลที่ส่งต่างกัน) และ heatmap ไม่มีคอลัมน์ persona
    ctx["personas"] = []
    prompts = []

    def forces_only(system, user, max_tokens=1500):
        prompts.append(system)
        return json.dumps({"stepic": _links_answer(society=2 if "Barrier Care" in user else 1)["stepic"]})

    assert link_trends(ctx, cache, llm_call=forces_only, max_workers=1, log=lambda *_: None) == {"llm": 2}
    assert set(prompts) == {SYSTEM_PROMPT_LINKS_FORCES} and "persona" not in SYSTEM_PROMPT_LINKS_FORCES.lower()
    s = ctx["links_summary"]
    assert s["personas"] == [] and s["stepic"]["Society"] == {"main": 1, "any": 2} and all(t["links"]["personas"] == [] for t in ctx["trends"])
    payload = {"stepic_forces": [{"force": f["dimension"]} for f in STEPIC], "personas": []}
    assert validate_links({"stepic": _links_answer()["stepic"]}, payload)["personas"] == []
    ctx["stepic"] = []                                               # ไม่มีแรงขับให้จับคู่ -> ไม่มีหน้า heatmap
    assert link_trends(ctx, cache, llm_call=None, log=lambda *_: None) == {} and "links_summary" not in ctx


def test_render_ladder_and_drivers_page(run_dir):
    ctx = _rendered_ctx(run_dir)
    ctx["stepic"], ctx["personas"] = STEPIC, PERSONAS
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert 'data-label="Trend Drivers"' not in html and 'class="ladder"' not in html   # ยังไม่มีผล -> หน้าเดิม

    link_trends(ctx, {}, llm_call=lambda s, u, max_tokens=0: json.dumps(_links_answer()), max_workers=1,
                log=lambda *_: None)
    ctx["trends"][0]["ladder"] = LADDER_OK["en"]
    ctx["trends"][0]["ladder_th"] = LADDER_OK["th"]
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert 'data-label="Trend Drivers"' in html and html.count('class="lv2 dim-society"') == 2
    assert "The Curator" in html and "Trends with a main link" in html
    assert html.count('class="ladder"') == 1 and "What&#39;s different" in html and "Repairs the skin barrier" in html
    assert html.count("<b>Trend -</b>") == 2    # การ์ดหน้า Summary + เทรนด์ 2 ที่ไม่มี ladder (ใช้ย่อหน้าเดิม)
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "จุดต่าง" in th and "ซ่อมเกราะผิว" in th and "Repairs the skin barrier" not in th
    assert th.count('<section class="page') == html.count('<section class="page')


def test_cover_date_has_four_digit_year_and_data_sources(run_dir):
    ctx, _ = build_context(run_dir)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 9, 25), "x")
    assert '<div class="cover-date">25.09.2026</div>' in html
    assert ("Search data: Worldwide Google Trends (English keywords) | Product evidence: Konvy") in html


# ============================================================================
# ฉบับภาษาไทย (phase6_trend_report_TH.pdf)
# ============================================================================
from enrich import fallback_texts_th, translate_report_texts, validate_same_shape, validate_th  # noqa: E402
from i18n import date_long, dimensions, enum, localize, month_year  # noqa: E402

TH_OK = {"headline": "ตลาดโต", "trend": "เทรนด์ดี", "insight": "ผู้บริโภคต้องการ",
         "target": "ผู้หญิงผิวแพ้ง่าย", "product_reasons": ["ช่วยปลอบผิว"]}
TH_PAYLOAD = {"context_en": {"target_consumer": "Sensitive-skin women"}, "product_match_reasons_en": ["Soothes skin"]}


def test_validate_th():
    assert validate_th(TH_OK, TH_PAYLOAD)["product_reasons"] == ["ช่วยปลอบผิว"]
    assert validate_th({**TH_OK, "trend": "English only"}, TH_PAYLOAD) is None          # ต้องมีอักษรไทย
    assert "workshop_question" not in validate_th({**TH_OK, "workshop_question": "แบรนด์ของคุณ"}, TH_PAYLOAD)   # cache เก่า: ช่องคำถามถูกทิ้ง
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
    assert "workshop_question" not in out
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
    assert enum("Peaking", "th") == "ใกล้จุดสูงสุด" and enum("leaning fad", "th") == "ค่อนไปทางกระแสชั่วคราว"
    assert dimensions("SOCIETY + INDUSTRY", "th") == "สังคม + อุตสาหกรรม"
    assert date_long(datetime(2026, 9, 16), "th") == "16 ก.ย. 2026"


def test_localize_th_does_not_touch_english_context(run_dir):
    ctx, _ = build_context(run_dir)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None, lang="th")
    ctx["trends"][0]["products"] = [{"name": "Cream 50 ml.", "name_full": "Cream 50 ml. ครีม", "reason": "Soothes"}]
    ctx["trends"][0]["text_th"]["product_reasons"] = ["ช่วยปลอบผิว"]
    th = localize(ctx, "th")
    assert th["trends"][0]["products"][0] == {"name": "Cream 50 ml. ครีม", "name_full": "Cream 50 ml. ครีม",
                                              "reason": "ช่วยปลอบผิว"}
    assert "workshop_question" not in th["trends"][0]["text"]
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
    too_long = {"items": [{"headline": " ".join(["word"] * 12), "body": "fine"}]}
    assert validate_condensed("stepic", src, too_long) is None                # เกินขีดจำกัดหัวข้อ x 1.25
    assert validate_condensed("stepic", src, {"items": []}) is None             # จำนวนข้อไม่ตรง
    assert validate_condensed("stepic", src, {"items": [{"headline": "ไทย", "body": "b"}]}) is None
    # 🆕 (2026-10-28) คำค้นภาษาไทยที่คัดจากต้นฉบับผ่านได้ (มีเครื่องหมายคำพูดหรือไม่ก็ตาม) - ท่อนไทยที่ไม่มีในต้นฉบับยังไม่ผ่าน
    src_th = {"items": [{"headline": "h", "body": "People search for 'ทรง ผม 2026' and more."}]}
    assert validate_condensed("stepic", src_th, {"items": [{"headline": "Hair", "body": "People search for 'ทรง ผม 2026'."}]})
    assert validate_condensed("stepic", src_th, {"items": [{"headline": "Hair", "body": "People search for ทรง ผม 2026."}]})
    assert validate_condensed("stepic", src_th, {"items": [{"headline": "Hair", "body": "People search for ทรง ผมยาว."}]}) is None


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
                        overall_level, quadrant, rank_cuts)
from brand_i18n import apply_th  # noqa: E402
from enrich import translate_items_th  # noqa: E402
from render import render_brand_html  # noqa: E402

CUTS = rank_cuts(1000, DEFAULT_CONFIG["fit_top_pct"])   # กลุ่มปลอม 1,000 ชิ้น (_fit) -> 10 / 50 / 200


def _fit(rank=20, n_tier=1000, reason="Soothes skin."):
    """🆕 (2026-10-07) category_fit ของ 1 เทรนด์ในรูปที่ category_fit.category_fit คืน: 🆕 (2026-10-08) หมวดหลักหมวดเดียว (Skin Care -
    LLM เลือก) / Zenith Cream (ราคา 199) อยู่ช่วงราคากลางที่อันดับ rank (None = ไม่มีสินค้าในหมวดนี้) ทุกกลุ่มมี n_tier ชิ้น"""
    def tier(label, lo, hi, best_rank=None, name=None, price=None):
        top = [{"product_name": f"Rival {label} {i}", "brand": "Rival", "sale_price_thb": float(lo + i), "similarity": 0.4 - i / 100,
                "rank_in_tier": i, "rank_in_market": i * 3} for i in range(1, 6)]
        bb = None
        if best_rank:
            bb = {"product_name": name, "brand": "Zenith", "sale_price_thb": price, "similarity": 0.30,
                  "rank_in_tier": best_rank, "rank_in_market": best_rank * 3}
            if best_rank <= 5:
                top[best_rank - 1] = dict(bb)
        return {"label": label, "price_from": lo, "price_to": hi, "n_total": n_tier, "n_brand": 1 if best_rank else 0,
                "top": top, "brand_best": bb}

    def best_of(tiers, label):
        t = next(x for x in tiers if x["label"] == label)
        return ({**t["brand_best"], "n_tier": n_tier, "tier": label, "price_from": t["price_from"], "price_to": t["price_to"],
                 "match_reason": reason} if t["brand_best"] else None)

    skin = [tier("low", 5, 159), tier("mid", 160, 395, rank, "Zenith Cream", 199.0), tier("high", 396, 9245)]
    return {"n_market": 1000, "main_category": "Skin Care", "category_reason": "Barrier repair is skincare.", "categories": [
        {"category": "Skin Care", "n_total": 3 * n_tier, "n_brand": 1 if rank else 0, "tiers": skin,
         "brand_best": best_of(skin, "mid")}]}


def _brand_fixture(run_dir, **fit_kw):
    """trend ctx (2 เทรนด์) + ผล ⑬ ของแบรนด์ Zenith ที่มีแค่เทรนด์แรก (พร้อม category_fit - ดู _fit)"""
    ctx, _ = build_context(run_dir)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None, lang="th")
    ctx["meta"]["n_products_compared"] = 1000
    # 🆕 2026-09-30 แกนการเติบโตแทน Z_Delta / 🆕 2026-10-02 แกนใช้คะแนนปีที่ 2 + แสดง % ที่คาดปีที่ 2 / 🆕 2026-10-19 ระยะสั้นเป็นปีที่ 3
    for t, score, fc in zip(ctx["trends"], (0.82, 0.64), ([9.0, 16.0, 23.4, 40.0, 50.0], [4.0, 8.0, 12.0, 25.0, 30.0])):
        t["growth"] = {"scores": [0.5, 0.5, score, 0.6, 0.6], "grades": [3, 3, 4, 3, 3], "past_growth_pct": 12.0,
                       "recent_change_pct": 5.0, "recent_decline": False, "forecast_pct": fc}
    coverage = {"brand": "Zenith", "n_skus": 12, "coverage": {"Social::Barrier Care": {
        "trend_name": "Barrier Care", "brand_best_product": "Zenith Cream", "brand_best_score": 0.30,
        "brand_best_rank_vs_market": 60, "market_best_product": "Other - Other Cream", "market_best_score": 0.35,
        "brand_top_matches": [{"product_name": "Zenith Cream", "similarity": 0.30, "rank_vs_market": 60,
                               "sale_price_thb": 199.0, "match_reason": "Soothes skin."}],
        "category_fit": _fit(**fit_kw)}}}
    catalog = pd.DataFrame([{"brand": "Other", "product_name": "Other Cream", "main_image": None, "product_url": None,
                             "sale_price_thb": "1,290.00", "EM_L2": "Skin Care"},
                            {"brand": "Zenith", "product_name": "Zenith Cream", "main_image": None, "product_url": None,
                             "sale_price_thb": "199.00", "EM_L2": "Skin Care"}])
    return ctx, coverage, catalog


def test_fit_level_and_quadrant():
    """🆕 (2026-10-07) 4 ระดับตาม % แรก (top 1 / 5 / 20%) - อันดับ 1 ของกลุ่มได้ Excellent เสมอ"""
    assert CUTS == {"excellent": 10, "good": 50, "average": 200}
    assert rank_cuts(8738, DEFAULT_CONFIG["fit_top_pct"]) == {"excellent": 87, "good": 436, "average": 1747}
    assert rank_cuts(13, DEFAULT_CONFIG["fit_top_pct"]) == {"excellent": 1, "good": 1, "average": 2}   # กลุ่มเล็ก
    assert [fit_level(r, CUTS) for r in (1, 10, 11, 50, 51, 200, 201, None)] == \
        ["excellent", "excellent", "good", "good", "average", "average", "below_average", "below_average"]
    with pytest.raises(ValueError):
        rank_cuts(None, DEFAULT_CONFIG["fit_top_pct"])
    strong = DEFAULT_CONFIG["strong_fit_levels"]
    assert quadrant(0.9, "excellent", 0.7, strong) == "defend"
    assert quadrant(0.9, "average", 0.7, strong) == "build"
    assert quadrant(0.5, "good", 0.7, strong) == "maintain"
    assert quadrant(0.5, "below_average", 0.7, strong) == "monitor"


def test_overall_level_more_than_half():
    """🆕 (2026-10-07) เกรดรวม = ระดับสูงสุดที่เทรนด์ "เกินครึ่ง" ทำได้ถึง (ครึ่งพอดีไม่นับ) + ระดับถัดไปเมื่ออีก 1 เทรนด์ก็ขึ้น
    กรณีตัวอย่างที่คุยกับผู้ใช้ (Excellent / Good / Average / Below average)"""
    def ov(e, g, a, b):
        r = overall_level({"excellent": e, "good": g, "average": a, "below_average": b}, e + g + a + b)
        return r["level"], r["k"], r["next"] and (r["next"]["level"], r["next"]["k"])

    assert ov(0, 6, 0, 0) == ("good", 6, None)                        # Srichand: ทุกเทรนด์ top 5%
    assert ov(3, 3, 0, 0) == ("good", 6, ("excellent", 3))            # Eucerin: Excellent ครึ่งพอดี ไม่นับ
    assert ov(0, 0, 2, 4) == ("below_average", 6, None)               # Watsons
    assert ov(2, 0, 0, 4) == ("below_average", 6, None)               # แบรนด์เฉพาะทาง
    assert ov(2, 1, 1, 2) == ("average", 4, ("good", 3))              # ผลผสม
    assert ov(3, 0, 0, 2) == ("excellent", 3, None)                   # 5 เทรนด์ (เลขคี่)
    assert ov(3, 3, 3, 3) == ("average", 9, ("good", 6))              # 12 เทรนด์ กระจายเท่ากัน
    assert ov(5, 4, 1, 0) == ("good", 9, ("excellent", 5))            # Mizumi รอบ snapshot
    assert ov(0, 1, 0, 0) == ("good", 1, None)                        # ตรวจแค่ 1 เทรนด์: ไม่บอก "ได้แล้ว 0 จาก 1"
    assert overall_level({}, 0) is None


def test_brand_context_grades_by_key_category_and_price_group(run_dir):
    """🆕 (2026-10-07) เทรนด์ -> หมวด -> ช่วงราคา -> สินค้า: อันดับ 20 จาก 1,000 ในกลุ่ม Skin Care · ราคากลาง = Good (top 2%)"""
    ctx, coverage, catalog = _brand_fixture(run_dir, rank=20)
    b = build_brand_context(ctx, coverage, catalog, DEFAULT_CONFIG)
    first, second = b["rows"]
    assert first["checked"] and first["level"] == "good" and not first["no_key_product"]
    assert first["quadrant"] == "defend"     # การเติบโต 0.82 เหนือค่ากลาง + Good = พร้อม (กันตัวแปรเทรนด์ถูกทับในลูป)
    # 🆕 (2026-10-07) ตารางหมวด x ช่วงราคา: ทุกช่วงราคาของหมวด + สินค้าที่ใกล้ที่สุดของแบรนด์ + ช่องที่ใช้เป็นเกรดของเทรนด์
    skin_tiers = first["categories"][0]["tiers"]
    assert [(x["label"], x["price_from"], x["price_to"], x["graded"]) for x in skin_tiers] == \
        [("low", 5, 159, False), ("mid", 160, 395, True), ("high", 396, 9245, False)]
    assert skin_tiers[0]["best"] is None and (skin_tiers[1]["best"]["name"], skin_tiers[1]["best"]["level"]) == ("Zenith Cream", "good")
    # top 5 ของทั้งหมวด (รวมทุกช่วงราคา เรียงตามอันดับในร้าน) พร้อมช่วงราคาของแต่ละชิ้น
    top = first["categories"][0]["top"]
    assert [(m["pos"], m["rank_in_market"], m["tier"]) for m in top] == [(1, 3, "low"), (2, 3, "mid"), (3, 3, "high"), (4, 6, "low"), (5, 6, "mid")]
    assert not any(m["is_you"] for m in top)
    assert [(e["category"], e["key"]) for e in first["categories"]] == [("Skin Care", True)]   # หมวดหลักหมวดเดียว
    g = first["graded"]
    assert (g["category"], g["tier"], g["rank_in_tier"], g["n_tier"], g["level"]) == ("Skin Care", "mid", 20, 1000, "good")
    assert g["reason"] == "Soothes skin."
    assert first["products"] == [g]
    cell = first["cell"]
    assert (cell["category"], cell["tier"], cell["n_total"], len(cell["top"]), cell["you_in_top"]) == ("Skin Care", "mid", 1000, 5, False)
    assert first["leader"]["name"] == "Rival mid 1" and first["gap_to_leader"] == round(0.39 - 0.30, 4)
    assert not second["checked"] and b["missing_trends"] == ["Stable Retinol"]   # ผล ⑬ ไม่มีเทรนด์นี้
    assert b["counts"] == {"excellent": 0, "good": 1, "average": 0, "below_average": 0} and b["highlights"]["strongest"] == 1
    assert "key_share" not in b and b["portfolio"]["n_skus"] == 1


def test_brand_context_grades_main_category_only(run_dir):
    """🆕 (2026-10-08) เกรดของเทรนด์ = สินค้าที่ดีที่สุดของแบรนด์ในหมวดหลักหมวดเดียว (ไม่นับหมวดควบคู่ เช่น กันแดดของเทรนด์เรตินอล)"""
    ctx, cov, cat = _brand_fixture(run_dir, rank=300)       # อันดับ 300 จาก 1,000 ในกลุ่ม = เกิน top 20%
    first = build_brand_context(ctx, cov, cat, DEFAULT_CONFIG)["rows"][0]
    assert first["level"] == "below_average" and first["graded"]["category"] == "Skin Care"
    # 🆕 (2026-10-27) เกรดตามอันดับล้วน (ตัดยอดขายออก): อันดับ 1 ของกลุ่ม = Excellent ไม่ต้องมีข้อมูลยอดขาย (จำกัดที่ Good)
    ctx, cov, cat = _brand_fixture(run_dir, rank=1)
    first = build_brand_context(ctx, cov, cat, DEFAULT_CONFIG)["rows"][0]
    assert first["level"] == "excellent" and "base_level" not in first["graded"] and "sales_move" not in first["graded"]
    assert first["cell"]["you_in_top"] and [m["is_you"] for m in first["cell"]["top"]] == [True, False, False, False, False]
    assert first["cell"]["top"][0]["level"] == "excellent"
    assert any(m["is_you"] for m in first["categories"][0]["top"])       # และติด top 5 ของทั้งหมวด


def test_brand_context_no_product_in_trend_category(run_dir):
    """ไม่มีสินค้าในหมวดของเทรนด์เลย -> Below average + top 5 ทุกช่วงราคาของหมวดนั้น (เช่น Mizumi x เทรนด์แฮร์แคร์)"""
    ctx, cov, cat = _brand_fixture(run_dir, rank=None)
    first = build_brand_context(ctx, cov, cat, DEFAULT_CONFIG)["rows"][0]
    assert first["level"] == "below_average" and first["no_key_product"] and first["graded"] is None
    assert first["key_categories"] == ["Skin Care"] and first["cell"] is None
    assert not any(x["graded"] for e in first["categories"] for x in e["tiers"])            # ไม่มีช่องที่ใช้เป็นเกรด


def test_brand_context_requires_category_fit_with_main_category(run_dir):
    ctx, cov, cat = _brand_fixture(run_dir)
    del cov["coverage"]["Social::Barrier Care"]["category_fit"]
    with pytest.raises(ValueError, match="category-fit-only"):
        build_brand_context(ctx, cov, cat, DEFAULT_CONFIG)
    ctx, cov, cat = _brand_fixture(run_dir)
    del cov["coverage"]["Social::Barrier Care"]["category_fit"]["main_category"]   # ผล ⑬ แบบหลายหมวด (ก่อน 2026-10-08)
    with pytest.raises(ValueError, match="category-fit-only"):
        build_brand_context(ctx, cov, cat, DEFAULT_CONFIG)


def test_find_coverage_file(run_dir):
    assert find_coverage_file(run_dir, "zenith").name == "phase3_brand_coverage_Zenith.json"   # ไม่สนตัวพิมพ์
    assert find_coverage_file(run_dir, "Zenit").name == "phase3_brand_coverage_Zenith.json"    # พิมพ์ตกไป 1 ตัว
    assert find_coverage_file(run_dir, "Nothing Like It") is None


def test_render_brand_report_both_languages(run_dir):
    ctx, coverage, catalog = _brand_fixture(run_dir, rank=20)
    brand_style = {**BRAND, "company_name": "S&J"}
    b_en = build_brand_context(ctx, coverage, catalog, DEFAULT_CONFIG)
    cat_en = build_category_context(ctx, coverage, catalog, DEFAULT_CONFIG)       # 🆕 2026-10-14 หน้าสินค้าต่อเทรนด์ที่รวมมาจาก ⑱
    en = render_brand_html(ctx, b_en, brand_style, {}, "Zenith × Topic Trends", datetime(2026, 9, 26), cat=cat_en)
    # ปก + สรุป + สินค้าตามเทรนด์ เทียบคู่แข่ง (1 หน้า) + เทรนด์ 1 (2 หน้า) + เทรนด์ 2 (ไม่ได้ตรวจ 1 หน้า) + โอกาส + ภาคผนวก
    # (🆕 2026-10-07 ไม่มีหน้า Trend Fit Matrix / ภาพรวมความพร้อมแล้ว)
    assert en.count('<section class="page') == 3 + 3 + 2
    assert 'data-label="Fit Matrix"' not in en and 'data-label="Fit Overview"' not in en
    # 🆕 (2026-10-07) หน้า "สินค้าตามเทรนด์ เทียบคู่แข่ง": คอลัมน์ = top 5 ของกลุ่มที่ใช้ให้เกรด, แถวล่าง = สินค้าของคุณ (นอก top 5)
    vs = en[en.index('data-label="Product Overview"'):]
    vs = vs[:vs.index("</section>")]
    assert "<h2>Products by Trend</h2>" in vs and "Skin Care · Mid price · THB 160-395" in vs
    assert vs.count('class="vs-c is-you"') == 1 and ">#20</div>" in vs and "/ 1,000" not in vs and "Rival mid 1" not in vs   # ชื่อถูกตัดแบรนด์ออก
    assert '<span class="rk-brand">Rival</span> mid 1' in vs and "Not checked" in vs and 'class="vs-c vs-empty"' in vs
    assert 'data-label="Brand Trend 1 Detail"' in en and 'data-label="Brand Trend 2 Detail"' not in en
    assert "Executive Summary | Zenith" in en and "Your best product for this trend" in en and "Consumer need" in en
    # 🆕 (2026-10-07) หน้าเทรนด์: ตารางหมวดสำคัญ x ช่วงราคา (ช่วงบาท / สินค้าที่ใกล้ที่สุด / เกรด) ไม่มีสัดส่วน/อันดับ/top 5
    # 🆕 (2026-10-14) หน้า 2 = หน้าเทรนด์ของ ⑱ เดิม (เจ้าของงานสั่งรวม): 3 กลุ่มราคา x (top 5 ของกลุ่ม + สินค้าที่ดีที่สุดของแบรนด์ + อันดับ)
    detail = en[en.index('data-label="Brand Trend 1 Detail"'):]
    detail = detail[:detail.index("</section>")]
    assert detail.count('class="tier-grid k3"') == 1 and detail.count('class="tier"') == 3 and "<b>Skin Care</b>" in detail
    assert "Low price" in detail and "Mid price" in detail and "High price" in detail and "THB 160-395" in detail
    assert "<b>#20</b>" in detail and "top 2.0% of the group" in detail and "whole store: #60" in detail and "/ 1,000" not in detail
    assert "Your best product in this group" in detail and '<span class="rk-brand">Zenith</span> Cream' in detail
    assert detail.count("No Zenith product in this tier") == 2 and 'class="tr is-you"' not in detail   # อันดับ 20 ไม่ติด top 5
    assert "Soothes skin." in en and "Position in group" in en and "<b>Trend -</b>" in detail
    assert "Skin Care · Mid price <span class=\"muted\">(THB 160-395)</span>" in en
    page = en[en.index('data-label="Brand Trend 1"'):]
    page = page[:page.index("</section>")]
    assert "Top 5 in" not in page and 'class="ct-key"' not in page and "70%" not in page
    # 🆕 (2026-10-12) หน้า 1 บอกตำแหน่งในกลุ่มเป็น % แรก (อันดับในวงเล็บ - ไม่มี "จาก n")
    assert "Position in group" in page and "top 2.0% (rank #20)" in page and "of 1,000" not in page
    # ระดับ 4 ขั้น + กล่องเกรดรวม + ภาคผนวกอธิบายเทรนด์ -> หมวด -> ช่วงราคา -> สินค้า
    assert all(f'fit-{lv}"></span>{nm}' in en for lv, nm in (("excellent", "Excellent"), ("good", "Good"),
                                                             ("average", "Average"), ("below_average", "Below average")))
    assert "best product is in the top 1% of its type &amp; price group" in en and "in sales" not in en
    assert "Overall fit" in en and "Good or better in 1 of 1 trends - most trends have a product in the top 5% of products of the same type" in en
    assert "complementary categories are not counted" in en and "#1 of a group always counts as top 1%" in en and "are key" not in en
    assert "Strongest fit - Barrier Care: Zenith Cream ranks #20 of 1,000 products in Skin Care · Mid price." in en
    assert "Action combines expected search growth in year 3" in en                     # ภาคผนวกอธิบายแนวทางแทน matrix
    assert "Leading" not in en and "Competitive" not in en and "Top 5 products closest to this trend" not in en
    assert ">+23%</div>" in en and "Expected (year 3)" in en                           # กล่องตัวเลขในหน้า 1 ของเทรนด์
    body = re.sub(r"<style>.*?</style>", "", en, flags=re.S).lower()                     # คอมเมนต์ใน CSS ไม่นับ
    assert "faster" not in body and "slower" not in body and "fast-growing" not in body
    lth = localize(ctx, "th")
    b_th = apply_th(build_brand_context(lth, coverage, catalog, DEFAULT_CONFIG), {"Barrier Care": ["ช่วยปลอบผิว"]})
    cat_th = apply_th_category(build_category_context(lth, coverage, catalog, DEFAULT_CONFIG))
    th = render_brand_html(lth, b_th, brand_style, {}, "Zenith × เทรนด์ Topic", datetime(2026, 9, 26), lang="th", cat=cat_th)
    assert th.count('<section class="page') == en.count('<section class="page')
    assert "สรุปผู้บริหาร | Zenith" in th and "ช่วยปลอบผิว" in th
    th_detail = th[th.index('data-label="Brand Trend 1 Detail"'):]
    th_detail = th_detail[:th_detail.index("</section>")]
    assert "ราคาต่ำ" in th_detail and "160-395 บาท" in th_detail and "<b>#20</b>" in th_detail and "ทั้งร้าน: อันดับ 60" in th_detail
    assert "ติด 2.0% แรกของกลุ่ม" in th_detail and "ไม่มีสินค้า Zenith ในระดับราคานี้" in th_detail
    assert "ตำแหน่งในกลุ่ม" in th and "Skin Care · ราคากลาง" in th
    assert "สินค้าที่ดีที่สุดของคุณในเทรนด์นี้" in th and "สินค้าที่ใช้ตัดเกรด" not in th
    assert 'fit-good"></span>Good' in th and "Good ขึ้นไป 1 จาก 1 เทรนด์" in th and "ภาพรวม" in th
    assert "นำตลาด" not in th and "แข่งขันได้" not in th
    th_body = re.sub(r"<style>.*?</style>", "", th, flags=re.S)
    assert "+23%" in th_body and "เร็ว" not in th_body and "ช้า" not in th_body


def test_render_brand_trend_page_variants(run_dir):
    """บรรทัด "อีก 1 เทรนด์" ของกล่องเกรดรวม / ไม่มีสินค้าในหมวดสำคัญ -> ข้อความ + ตารางเฉพาะหมวดสำคัญที่ไม่มีช่องไฮไลต์"""
    brand_style = {**BRAND, "company_name": "S&J"}
    ctx, coverage, catalog = _brand_fixture(run_dir, rank=3)
    b = build_brand_context(ctx, coverage, catalog, DEFAULT_CONFIG)
    vs = render_brand_html(ctx, b, brand_style, {}, "T", datetime(2026, 9, 26))
    vs = vs[vs.index('data-label="Product Overview"'):]
    vs = vs[:vs.index("</section>")]
    # สินค้าของคุณติดอันดับ 3 ของกลุ่ม -> ไฮไลต์ในแถวนั้น และแถวล่างของเทรนด์นั้นเว้นว่าง
    assert vs.count('class="vs-c is-you"') == 1 and "#3</div>" in vs and vs.count('class="vs-c vs-empty"') == 2
    tie = {**b, "overall": overall_level({"excellent": 3, "good": 3}, 6)}
    en_tie = render_brand_html(ctx, tie, brand_style, {}, "T", datetime(2026, 9, 26))
    assert "Excellent or better" not in en_tie and "Already Excellent in 3 of 6 - one more trend → Excellent." in en_tie
    ctx, coverage, catalog = _brand_fixture(run_dir, rank=None)
    b = build_brand_context(ctx, coverage, catalog, DEFAULT_CONFIG)
    en = render_brand_html(ctx, b, brand_style, {}, "Zenith × Topic Trends", datetime(2026, 9, 26))
    assert "No Zenith product in this trend&#39;s category (Skin Care)" in en and "No product in the trend&#39;s category" in en
    # ไม่ส่ง cat (ผลหมวดจาก ⑬ ไม่ครบ) -> ไม่มีหน้าสินค้าต่อเทรนด์ เหลือหน้าเดียวและหมายเหตุอยู่ในหน้านั้น
    assert 'data-label="Brand Trend 1 Detail"' not in en and 'class="tier-grid' not in en
    # 🆕 (2026-10-14) ส่ง cat และแบรนด์ไม่มีสินค้าในหมวด -> ยังมีหน้านั้น: ข้อความแจ้ง + สินค้าที่ตรงเทรนด์ที่สุดของแต่ละกลุ่มราคา
    en_cat = render_brand_html(ctx, b, brand_style, {}, "Zenith × Topic Trends", datetime(2026, 9, 26),
                               cat=build_category_context(ctx, coverage, catalog, DEFAULT_CONFIG))
    det = en_cat[en_cat.index('data-label="Brand Trend 1 Detail"'):]
    det = det[:det.index("</section>")]
    assert "Zenith has no product in Skin Care" in det and det.count("No Zenith product in this tier") == 3
    assert "Category = the main product category an AI chose for the trend" in en
    assert "Skin Care · All prices" in en                       # หน้าเทียบคู่แข่ง: ไม่มีสินค้าในหมวดของเทรนด์ -> top 5 ทั้งหมวด
    assert "Average or better in only 0 of 1 trends - most trends have no product in the top 20%" in en
    assert "and Zenith has no product in its category (Skin Care)." in en       # ประเด็นสำคัญ: โอกาสใหญ่ที่สุด


# ============================================================================
# ⑱ รายงานหมวด x ช่วงราคา (phase6_brand_category_report_<แบรนด์>.pdf) - รายงานคู่กับ ⑰
# 🆕 (2026-10-07) หมวดสำคัญละ 1 หน้า x ช่วงราคาตลาด + เกรดต่อช่วงราคา (category_fit ชุดเดียวกับ ⑰)
# ============================================================================
from brand_category_data import STATUS_NO_BRAND, STATUS_NO_TIERS, STATUS_OK, STATUS_UNCHECKED  # noqa: E402
from brand_category_data import apply_th as apply_th_category  # noqa: E402
from brand_category_data import build_category_context  # noqa: E402
from render import render_brand_category_html  # noqa: E402


def test_category_context_pages_grades_and_th(run_dir):
    ctx, coverage, catalog = _brand_fixture(run_dir, rank=20)
    b = build_category_context(ctx, coverage, catalog, DEFAULT_CONFIG)
    first, second = b["rows"]
    assert (first["status"], second["status"]) == (STATUS_OK, STATUS_UNCHECKED)       # เทรนด์ที่สองไม่อยู่ในผล ⑬ ของแบรนด์
    (skin,) = first["pages"]                                                           # หมวดหลักหมวดเดียว = 1 หน้า
    assert (skin["category"], skin["brand_n"]) == ("Skin Care", 1) and "share" not in skin
    assert [t["label"] for t in skin["tiers"]] == ["low", "mid", "high"]
    mid = skin["tiers"][1]
    assert (mid["brand_best"]["rank_in_tier"], mid["brand_best"]["level"], mid["n_total"]) == (20, "good", 1000)
    assert skin["tiers"][0]["brand_best"] is None and skin["level"] == "good" and skin["best_tier"]["label"] == "mid"
    s = b["highlights"]["strongest"]
    assert (s["name"], s["category"], s["tier_label"], s["rank_in_tier"], s["level"]) == ("Barrier Care", "Skin Care", "mid", 20, "good")
    assert b["n_ok"] == 1 and b["n_pages"] == 1 and b["missing_tiers"] == ["Stable Retinol"] and b["n_market"] == 1000
    # ตารางภาพรวม: 1 แถว = เทรนด์ x หมวด (เทรนด์ที่ไม่ได้ตรวจ 1 แถว)
    assert [(o["name"], o["first"], o["page"]["category"] if o["page"] else None) for o in b["overview"]] == \
        [("Barrier Care", True, "Skin Care"), ("Stable Retinol", True, None)]
    assert b["portfolio"]["categories"][0] == {"name": "Skin Care", "n": 1, "price_min": 199.0, "price_max": 199.0}
    # ผล ⑬ เก่า (ไม่มี category_fit หรือเป็นแบบหลายหมวดก่อน 2026-10-08) -> แจ้งให้เติมด้วย --category-fit-only ไม่ error
    ctx2, cov2, cat2 = _brand_fixture(run_dir, rank=20)
    del cov2["coverage"]["Social::Barrier Care"]["category_fit"]["main_category"]
    assert build_category_context(ctx2, cov2, cat2, DEFAULT_CONFIG)["rows"][0]["status"] == STATUS_NO_TIERS
    del cov2["coverage"]["Social::Barrier Care"]["category_fit"]
    assert build_category_context(ctx2, cov2, cat2, DEFAULT_CONFIG)["rows"][0]["status"] == STATUS_NO_TIERS
    # ฉบับไทยใช้ชื่อเต็ม
    b["rows"][0]["pages"][0]["tiers"][0]["top"][0]["name_full"] = "Rival low 1 เซรั่ม"
    assert apply_th_category(b)["rows"][0]["pages"][0]["tiers"][0]["top"][0]["name"] == "Rival low 1 เซรั่ม"


def test_category_context_brand_without_products_in_key_categories(run_dir):
    ctx, coverage, catalog = _brand_fixture(run_dir, rank=None)
    b = build_category_context(ctx, coverage, catalog, DEFAULT_CONFIG)
    assert b["rows"][0]["status"] == STATUS_NO_BRAND and b["highlights"]["no_brand"] == ["Barrier Care"]
    assert b["highlights"]["strongest"] is None and b["n_ok"] == 0 and b["n_checked"] == 1


def test_render_category_report_both_languages(run_dir):
    ctx, coverage, catalog = _brand_fixture(run_dir, rank=20)
    brand_style = {**BRAND, "company_name": "S&J"}
    b_en = build_category_context(ctx, coverage, catalog, DEFAULT_CONFIG)
    en = render_brand_category_html(ctx, b_en, brand_style, {}, "Zenith × Topic", datetime(2026, 10, 5))
    # ปก + สรุป + ภาพรวม + เทรนด์ 1 (หมวดหลักหมวดเดียว 1 หน้า) + เทรนด์ 2 (ไม่ได้ตรวจ 1 หน้า) + ภาคผนวก
    assert en.count('<section class="page') == 3 + 1 + 1 + 1
    assert "Low price" in en and "High price" in en and "THB 160-395" in en
    assert "<b>#20</b>" in en and " of 1,000" not in en and "/ 1,000" not in en and "whole store: #60" in en and "top 2.0% of the group" in en
    assert 'fit-good"></span>Good' in en
    body = re.sub(r"<style>.*?</style>", "", en, flags=re.S)
    assert "% of the trend" not in body and "key categor" not in body.lower()
    assert "Trend category" in body and "Complementary" in body
    assert en.count('class="tr is-you"') == 0
    ctx4, cov4, cat4 = _brand_fixture(run_dir, rank=4)
    en4 = render_brand_category_html(ctx4, build_category_context(ctx4, cov4, cat4, DEFAULT_CONFIG), brand_style, {}, "Zenith × Topic",
                                     datetime(2026, 10, 5))
    assert en4.count('class="tr is-you"') == 1 and 'class="rk-you">Your product<' in en4   # อันดับ 4 ติด top 5 ของกลุ่ม
    assert "Strongest position - Barrier Care: in Skin Care at Mid price THB 160-395, your Zenith Cream ranks #20 (Good)." in en
    assert "has not been compared with this brand yet" in en                                # เทรนด์ที่สอง ⑬ ไม่ได้ตรวจ
    lth = localize(ctx, "th")
    b_th = apply_th_category(build_category_context(lth, coverage, catalog, DEFAULT_CONFIG))
    th = render_brand_category_html(lth, b_th, brand_style, {}, "Zenith × เทรนด์", datetime(2026, 10, 5), lang="th")
    assert th.count('<section class="page') == en.count('<section class="page')
    assert "ราคาต่ำ" in th and "160-395 บาท" in th and "<b>#20</b>" in th and "จาก 1,000" not in th and "/ 1,000" not in th and "ทั้งร้าน: อันดับ 60" in th
    assert "หมวดสำคัญ" not in re.sub(r"<style>.*?</style>", "", th, flags=re.S) and "ภาคผนวก" in th and "สรุปผู้บริหาร | Zenith" in th


def test_render_category_report_no_brand_and_single_price(run_dir):
    ctx, coverage, catalog = _brand_fixture(run_dir, rank=None)
    en = render_brand_category_html(ctx, build_category_context(ctx, coverage, catalog, DEFAULT_CONFIG),
                                    {**BRAND, "company_name": "S&J"}, {}, "Zenith × Topic", datetime(2026, 10, 5))
    assert "Zenith has no product in Skin Care" in en and "No Zenith product in this tier" in en
    # ราคาเดียว (ช่วงราคาเริ่ม = สิ้นสุด) แสดงเป็นราคาเดียว ไม่ใช่ "THB 199-199"
    ctx2, cov2, cat2 = _brand_fixture(run_dir, rank=20)
    cov2["coverage"]["Social::Barrier Care"]["category_fit"]["categories"][0]["tiers"][1].update(price_from=199, price_to=199)
    en2 = render_brand_category_html(ctx2, build_category_context(ctx2, cov2, cat2, DEFAULT_CONFIG),
                                     {**BRAND, "company_name": "S&J"}, {}, "Zenith × Topic", datetime(2026, 10, 5))
    assert "THB 199<" in en2 and "THB 199-199" not in en2


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


# ============================================================================
# 🆕 (2026-09-30) หน้า Top 5 ระยะสั้น/ระยะยาว + ภาพรวมทุกเทรนด์ (แทนหน้า Rank Trajectory) - คะแนนการเติบโตของ ⑥
# ============================================================================
from report_data import CHANNEL_REASON, build_growth_pages, growth_periods, overview_bars  # noqa: E402


def _grade(s):
    return 4 if s >= 0.8 else 3 if s >= 0.5 else 2 if s >= 0.2 else 1


def _rank_row(rank, stream, name, short, long_, **extra):
    """🆕 (2026-10-02) 5 ปี: ระยะสั้น = ปีที่ 2 (จัดอันดับ/เส้นแบ่ง), ระยะยาว = ปีที่ 5
    🆕 (2026-10-19) ระยะสั้น = ปีที่ 3 (common/horizons.py) -> คะแนนระยะสั้นใส่ที่ปี 1-3, ปีที่ 4 = ค่ากลาง, ปีที่ 5 = ระยะยาว"""
    mid = round((short + long_) / 2, 2)
    scores = {1: short, 2: short, 3: short, 4: mid, 5: long_}
    return {"Overall Rank": rank, "Stream": stream, "Trend Name": name, "Rank Score": short, "Mode": "final (growth)",
            **{f"Growth_Y{h}": v for h, v in scores.items()}, **{f"Grade_Y{h}": _grade(v) for h, v in scores.items()},
            "Past_Growth_Pct": 10.0, "Recent_Decline": False, "Stream_Count": 1, **extra}


# (สาย, ชื่อ, ระยะสั้น, ระยะยาว) - T2 ช่องทางขาย, T6-T7 ใต้เส้น, T7 ระยะยาวสูงสุด
_SEVEN = [("Paper", "T1", 0.9, 0.6), ("News", "T2", 0.8, 0.2), ("Social", "T3", 0.7, 0.5), ("Paper", "T4", 0.6, 0.4),
          ("Paper", "T5", 0.55, 0.3), ("Social", "T6", 0.45, 0.1), ("News", "T7", 0.3, 0.95)]


def test_build_growth_pages_top5_from_all_matchable_trends():
    rows = [_rank_row(i, s, n, y1, y3) for i, (s, n, y1, y3) in enumerate(_SEVEN, 1)]
    rows[6]["Recent_Decline"] = True
    checked = [{"stream": s, "trend": n, "matchable": n != "T2", "reason": CHANNEL_REASON if n == "T2" else None}
               for s, n, _, _ in _SEVEN]
    highlights = {"selected_trends": [{"stream": s, "trend": n} for s, n, _, _ in _SEVEN if n in ("T1", "T3", "T4", "T5")],
                  "checked_trends": checked}
    trends = [{"stream": "Paper", "name": "T1", "rank": 1,
               "categories": {"categories": [{"group": "Face Sunscreen"}, {"group": "Body Sunscreen"},
                                             {"group": "Face Moisture"}]}}]
    gp = build_growth_pages(rows, {"as_of": "2026-08"}, highlights, trends, {"T6": {"keywords": "kw a, kw b, kw c"}})
    assert [x["name"] for x in gp["all"]] == ["T1", "T2", "T3", "T4", "T5", "T6", "T7"]
    assert (gp["n_above"], gp["n_below"], gp["n_matchable"], gp["n_detail"]) == (5, 2, 6, 1)
    by = {x["name"]: x for x in gp["all"]}
    assert by["T7"]["long_rank"] == 1 and by["T6"]["long_rank"] == 7 and by["T7"]["recent_decline"]
    assert by["T2"]["no_match_kind"] == "channel" and by["T1"]["no_match_kind"] is None
    assert by["T1"]["categories"] == ["Face Sunscreen", "Body Sunscreen"] and by["T6"]["keywords"] == ["kw a", "kw b"]
    assert by["T1"]["detail_rank"] == 1 and by["T6"]["detail_rank"] is None
    short, long_ = gp["top5"]["short"], gp["top5"]["long"]
    assert [x["name"] for x in short] == ["T1", "T3", "T4", "T5", "T6"]      # ข้าม T2 (จับคู่ไม่ได้)
    assert [x["name"] for x in long_] == ["T7", "T1", "T3", "T4", "T5"]      # T7 ใต้เส้นแต่ระยะยาวสูงสุด
    assert [x["both"] for x in short] == [True, True, True, True, False] and short[4]["other_rank"] == 7
    assert not long_[0]["both"] and long_[0]["other_rank"] == 7
    assert gp["top5"]["links"] == [[0, 1], [1, 2], [2, 3], [3, 4]]
    assert gp["past_inflated"]                                                 # ข้อมูลถึง 2026-08 ยังไม่พ้นจุดกระโดด
    assert not build_growth_pages(rows, {"as_of": "2027-07"}, highlights, trends, {})["past_inflated"]


def test_overview_bars_scale_per_year():
    """🆕 (2026-10-02) แท่งกราฟหน้าภาพรวม: สเกลแยกต่อปี ครอบ 0 / ค่าติดลบ / ระดับตลาด - ไม่มีค่าที่คาด = ไม่มีแท่ง"""
    items = [{"expected_pct": [10.0, 40.0, None, None, None]}, {"expected_pct": [-5.0, 20.0, None, None, None]}]
    market_x = overview_bars(items, [5.0, 10.0, None, None, None])
    assert items[0]["bars"][0] == {"left": 33.3, "width": 66.7, "end": 100.0}     # 0 อยู่ที่ 1/3 เพราะมีค่าติดลบ
    assert items[1]["bars"][0] == {"left": 0.0, "width": 33.3, "end": 33.3}       # แท่งติดลบวิ่งจาก 0 ไปซ้าย
    assert items[1]["bars"][1] == {"left": 0.0, "width": 50.0, "end": 50.0}       # ปีที่ 2 สเกลของตัวเอง (สูงสุด 40)
    assert items[0]["bars"][2] is None and market_x == [66.7, 25.0, None, None, None]
    assert overview_bars([{"expected_pct": [None] * 5}], None) is None


def test_growth_periods_and_old_rank_files():
    p = growth_periods("2026-08")
    assert p == {"past": "Sep 2025 - Aug 2026", "y1": "Sep 2026 - Aug 2027", "y2": "Sep 2027 - Aug 2028",
                 "y3": "Sep 2028 - Aug 2029", "y4": "Sep 2029 - Aug 2030", "y5": "Sep 2030 - Aug 2031"}
    old = [{"Overall Rank": 1, "Stream": "News", "Trend Name": "A", "Rank Score": 0.9, "Z_Delta": 0.9}]
    assert build_growth_pages(old, None, {}, [], {}) is None


def _with_growth_files(run_dir):
    _write(run_dir, "phase2_rank_score_final_mode_result.json", [
        _rank_row(1, "Social", "Barrier Care", 0.8, 0.6), _rank_row(2, "News", "Live Commerce", 0.7, 0.3),
        _rank_row(3, "Paper", "Stable Retinol", 0.4, 0.9, Recent_Decline=True)])
    # 🆕 (2026-10-02) % ที่คาดต่อเทรนด์ 5 ปี + ค่าที่ทายรายคีย์เวิร์ด (มัธยฐาน = ระดับตลาด +5/+17/+22/+27/+35%, คำ thin ไม่นับ)
    # + ช่วงคลาดเคลื่อน 80% ของปีที่ 2 / 5 (หมายเหตุใต้ตาราง)
    _write(run_dir, "phase2_growth_score_result.json", {
        "as_of": "2026-08",
        "method": {"forecast_band_80": {"3": [-0.21, 0.26], "5": [-0.23, 1.31]}},       # ปีระยะสั้น = 3 (growth_score.FORECAST_BAND_80)
        "clusters": [{"trend": "Barrier Care", "forecast": {"change_pct": [13.6, 28.2, 40.0, 47.7, 60.2]}},
                     {"trend": "Live Commerce", "forecast": {"change_pct": [-0.3, 23.3, 30.1, 36.3, 41.0]}}],
        "keywords": [{**{f"pred_y{h}": math.log(1 + v) for h, v in enumerate(ps, 1)}, "thin": thin}
                     for ps, thin in [((0.0, 0.1, 0.15, 0.2, 0.25), False), ((0.05, 0.17, 0.22, 0.27, 0.35), False),
                                      ((0.09, 0.3, 0.35, 0.4, 0.5), False), ((9.0,) * 5, True)]]})
    return _rendered_ctx(run_dir)


def test_render_top5_and_overview_pages(run_dir):
    ctx = _with_growth_files(run_dir)
    ctx["growth"]["show_cumulative"] = True        # ค่าเริ่มต้นปิดหน้าภาพรวมแบบสะสมแล้ว (SHOW_CUMULATIVE_PAGE) - เทสต์นี้ตรวจหน้านั้น
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    without = render_html({**ctx, "growth": None}, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert 'data-label="Top 5 Short vs Long"' in html and 'data-label="All Trends"' in html
    assert 'data-label="Top 5' not in without and 'data-label="Rank Trajectory"' not in html
    assert html.count('<section class="page') == without.count('<section class="page') + 3     # Top 5 + ภาพรวม + หน้ารวม CAGR และ YoY
    assert 'data-label="All Trends CAGR and YoY"' in html and 'data-label="All Trends CAGR and YoY"' not in without
    assert 'data-label="All Trends CAGR"' not in html and 'data-label="All Trends YoY"' not in html   # หน้าแยกเดิมปิดแล้ว
    assert "Market as a whole" in html and "Year 3 · Sep 2028 - Aug 2029" in html and "Year 5 · Sep 2030 - Aug 2031" in html
    band = "8 times in 10 the actual result was -21% to +26% from the year-3 figure and -23% to +131% from the year-5 figure"
    assert html.count(band) == 1                                               # หน้าภาพรวมแบบสะสม (เปิดในเทสต์นี้)
    levels = "8 times in 10 the actual search level was within -21% to +26% of the forecast for year 3 and -23% to +131% for year 5"
    assert html.count(levels) == 2                                             # หน้า Top 5 + หน้ากราฟจุด CAGR และ YoY
    top5 = html[html.index('data-label="Top 5'):].split("</section>")[0]
    # Top 5 = CAGR (Barrier Care ปี 3: 40.0% สะสม -> +12% ต่อปี, ปี 5: 60.2% -> +10%)
    assert "+12%</b>" in top5 and "+10%</b>" in top5 and "+40%</b>" not in top5 and "faster" not in top5
    assert "average growth per year (compounded)" in top5 and "counted from the baseline" not in top5
    for label in ("Top 5 Short vs Long", "All Trends"):                        # คำสถิติอยู่แค่ภาคผนวก
        page = html[html.index(f'data-label="{label}"'):]
        assert "median" not in page[:page.index("</section>")].lower() and "Spearman" not in page[:page.index("</section>")]
    assert "Last 12 months* <b>" in html and 'class="kpi-note"' in html
    assert html.count("jumped for every keyword from Aug 2025") == 1 + html.count('class="kpi-note"')
    assert 'data-ref="Trend 1"' in html and 'data-ref="Trend 2"' not in html  # เลขหน้าเติมตอนพิมพ์ (fillPageRefs)
    # 🆕 (2026-10-15) Live Commerce (ช่องทางการขาย ไม่พบสินค้า) ถูกตัดออกจากรายงานทั้งเล่ม - ไม่มีหน้า ไม่มีแถวในตาราง
    assert "Live Commerce" not in html and "no products found in the market" not in html
    assert "Searches down in the last 6 months" in html and "+10%" in html
    assert "Paper" not in html and "Social" not in html                            # ยังไม่แสดงสายหลักฐาน
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert th.count('<section class="page') == html.count('<section class="page')
    assert "ภาพรวมทุกเทรนด์" in th and "ปีที่ 3 · ก.ย. 2028 - ส.ค. 2029" in th and "ระดับตลาดโดยรวม" in th
    assert "8 ใน 10 ครั้ง ผลจริงอยู่ในช่วง -21% ถึง +26% ของตัวเลขปีที่ 3 และ -23% ถึง +131% ของตัวเลขปีที่ 5" in th

    # หน้า All Trends: ระยะสั้น = ปี 1-3, ระยะยาว = ปี 4-5 (หัวกลุ่มคอลัมน์ + เส้นคั่น + คำอธิบายสี) - 🆕 2026-10-19 เดิม 1-2 / 3-5
    def overview(doc):
        start = doc.index('data-label="All Trends"')
        return doc[start:doc.index("</section>", start)]
    en_page, th_page = overview(html), overview(th)
    assert "ค่ากลาง" not in th_page and "แหล่งที่ยืนยัน" not in th_page and "ตัวเลขเป็นค่าคาดการณ์" in th_page
    # 🆕 (2026-10-02) คำแนะนำ DA: ตัวเลข % ที่คาดแทนคำ "เร็ว/ช้า" + ไม่มีคอลัมน์ 12 เดือนที่ผ่านมา (สูงเกินจริง)
    assert ">+14%</span>" in en_page and ">+60%</span>" in en_page
    assert 'class="hb mk b1"' in en_page and ">+5%</span>" in en_page and ">+17%</span>" in en_page and ">+35%</span>" in en_page
    assert en_page.count('class="bar up"') + en_page.count('class="bar dn"') == 5 and 'class="lg mk"' in en_page   # เหลือ 1 เทรนด์ x 5 ปี
    assert en_page.count(">–</span>") == 5                                       # Stable Retinol ไม่มีค่าที่คาด
    assert "Year 5 rank" in en_page and "อันดับปี 5" in th_page
    for word in ("Faster", "Slower", "faster", "slower", "Last 12 months"):
        assert word not in en_page, word
    for word in ("เร็ว", "ช้า", "สูงเกินจริง", "ปีที่ผ่านมา"):
        assert word not in th_page, word
    assert "สูงกว่าระดับตลาดโดยรวม" in th_page and "ต่ำกว่าระดับตลาดโดยรวม" in th_page
    assert '<th class="g-short" colspan="3">Short term</th><th class="g-long" colspan="2">Long term</th>' in en_page
    assert "Short term = years 1-3" in en_page and "Long term = years 4-5" in en_page
    assert en_page.count('hb b1"') == 2 and en_page.count('hb b2"') == 2          # เส้นคั่นก่อนปี 1 และก่อนปี 4 ทุกแถว
    assert 'class="ctr b1">Year 1' in en_page and 'class="ctr b2">Year 4' in en_page and "Expected (vs last 12" not in en_page
    assert '<th class="g-short" colspan="3">ระยะสั้น</th><th class="g-long" colspan="2">ระยะยาว</th>' in th_page
    assert "ระยะสั้น = ปีที่ 1-3" in th_page and "ระยะยาว = ปีที่ 4-5" in th_page


# ============================================================================
# 🆕 (2026-10-01) โครง JSON ของ STEPIC ไม่คงที่ระหว่างรอบ - หน้า STEPIC / Signals ต้องครบทั้งสองแบบ
# ============================================================================
from report_data import _signals, _stepic_tiles  # noqa: E402

_TECH = {"core_technology": "NADES", "innovation_driver": "Stability", "commercialization_signal": "Launches"}
_CREA = {"brand_expression": "Clinical green", "product_innovation": "Cold process"}


def _stepic_raw(nested):
    base = {"society": {"concept": "Wellness", "behavioral_shift": "Protocols"},
            "environment": {"environmental_factor": "Bio-based", "sustainability_opportunity": "Green"},
            "policy": {"regulatory_trend": "Safety", "business_impact": "Costs"}}
    if nested:   # รอบ 2026-09-17
        return {**base, "technology": {"dimension": "Technology", "analysis": _TECH},
                "creativity": {"creativity_analysis": _CREA},
                "industry": {"concept": "Bio-Performance", "strategic_positioning": {"winning_strategy": "Own the lab"}}}
    return {**base, "technology": _TECH, "creativity": _CREA,   # รอบ 2026-10-01
            "industry": {"concept": "Bio-Performance", "information": "Info",
                         "industry": {"strategic_positioning": "Own the lab"}}}


def test_stepic_tiles_read_nested_and_flat_shapes():
    for nested in (True, False):
        tiles = _stepic_tiles(_stepic_raw(nested))
        assert [t["dimension"] for t in tiles] == ["Society", "Technology", "Environment", "Policy", "Industry",
                                                   "Creativity"]
        by = {t["dimension"]: t for t in tiles}
        assert by["Technology"]["headline"] == "NADES" and by["Creativity"]["body"] == "Cold process"
        assert by["Industry"]["body"] == "Own the lab"


def test_signals_accept_list_dimensions_and_insight():
    old = [{"dimensions": "SOCIETY + INDUSTRY", "signal": "M&A", "implication": "Clinics win"}]
    new = [{"signal_type": "Convergence", "dimensions": ["Society", "Industry"], "insight": "M&A"}]
    assert _signals(old)[0]["dimensions"] == "SOCIETY + INDUSTRY" and _signals(old)[0]["implication"] == "Clinics win"
    s = _signals(new)[0]
    assert s["dimensions"] == "SOCIETY + INDUSTRY" and s["signal"] == "M&A" and s["implication"] == ""


# ---------------------------------------------------------------------------------------------
# หน้าอธิบายวิธีคิดการทำนาย (build_method_page.py) - ใช้ผลจริงของรอบอ้างอิง ข้ามถ้าไม่มี (ไม่เปิด Chromium)
# ---------------------------------------------------------------------------------------------
METHOD_RUN = Path(__file__).resolve().parents[2] / "output" / "beauty_and_personal_care_20260916_082438"


@pytest.mark.skipif(not (METHOD_RUN / "phase2_growth_score_result.json").exists(), reason="ไม่มีรอบอ้างอิง")
def test_method_page_fills_real_numbers_in_both_languages():
    import build_method_page as bmp
    import growth_score as gs

    growth = json.loads((METHOD_RUN / gs.OUTPUT_FILE).read_text(encoding="utf-8"))
    trend = next(c["trend"] for c in growth["clusters"] if "Acne" in c["trend"])
    cluster = next(c for c in growth["clusters"] if c["trend"] == trend)
    row, ex = bmp.example_values(METHOD_RUN, growth, trend)
    brand = {"company_name": "Acme", "logo": None}
    docs = {lang: bmp.build_html(lang, brand, METHOD_RUN, growth, trend, row, ex, "data:image/svg+xml;base64,AA==")
            for lang in ("en", "th")}
    for lang, doc in docs.items():
        assert not re.search(r"\{[a-z0-9_]+(:[^}]*)?\}", re.sub(r"<style>.*?</style>", "", doc, flags=re.S)), lang
        assert f"{growth['method']['n_train']['1']:,}" in doc and row["keyword"] in doc and html.escape(trend) in doc
        assert f"{cluster['forecast']['change_pct'][4]:+.0f}%" in doc          # คาด +X% ปีที่ 5 ตรงกับผล ⑥
        assert f"{cluster['score_y3']:.2f}" in doc and f"{cluster['score_y5']:.2f}" in doc      # ปีระยะสั้น = 3 (common/horizons.py)
        assert "yr 3" in doc or "ปี 3" in doc
    assert "How the Growth Forecast Works" in docs["en"] and "วิธีคิดการทำนายการเติบโตของเทรนด์" in docs["th"]
    assert re.search(r"[ก-๙]", docs["th"]) and not re.search(r"[ก-๙]", re.sub(r"<style>.*?</style>", "", docs["en"], flags=re.S))


def _market_page(html):
    start = html.index('data-label="Market Overview"')
    return html[start:html.index("</section>", start)]


def test_market_overview_tiles_show_growth_basis_and_fall_back(run_dir):
    ctx = _rendered_ctx(run_dir)
    ctx["overview"]["market"] = {"current_trend_strength": "Moderate", "overall_direction": "Strengthening",
                                 "estimated_trend_duration": "Medium-term", "summary": "Search is rising.",
                                 "basis": {"short_year": 3, "long_year": 5, "median_change_pct_short": 15.2,
                                           "median_change_pct_long": 40.6, "median_durability": 66.4, "n_trends": 15}}
    en = _market_page(render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x"))
    assert "Year 3 search vs the last 12 months" in en and ">+15%<" in en and ">+41%<" in en and ">66/100<" in en
    assert "Middle of the 15 trends: half above, half below" in en and "5-year total, not per year" in en
    assert "Moderate" not in en and "Search is rising." in en and "current market signal" not in en
    th = _market_page(render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th"))
    assert "การค้นหาปีที่ 3 เทียบ 12 เดือนล่าสุด" in th and "ค่าตรงกลางของ 15 เทรนด์" in th and ">66/100<" in th
    assert "ปานกลาง" not in th and "ความยั่งยืน" not in th
    ctx["overview"]["market"].pop("basis")                                   # รอบเก่าไม่มี basis -> คำใต้ป้ายเดิม
    old = _market_page(render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x"))
    assert "current market signal" in old and "of the overall shift" in old and "Middle of the" not in old


def test_report_context_prefers_growth_market_overview_file(run_dir):
    ctx, _ = build_context(run_dir)
    assert "basis" not in ctx["overview"]["market"]                          # ไม่มีไฟล์ใหม่ -> ใช้ของ ⑦ (หรือว่าง)
    _write(run_dir, "phase4_market_overview.json", {"current_trend_strength": "Weak", "summary": "New text.",
                                                    "basis": {"median_change_pct_year_1": 1.0}})
    ctx, _ = build_context(run_dir)
    assert ctx["overview"]["market"]["summary"] == "New text." and ctx["overview"]["market"]["basis"]


def test_report_context_prefers_growth_trend_analysis_file(run_dir):
    ctx, _ = build_context(run_dir)
    before = ctx["trends"][0]["analysis"]
    assert "text_source" not in before                                       # ไม่มีไฟล์ใหม่ -> ใช้ของ ⑦ (หรือว่าง)
    name = ctx["trends"][0]["name"]
    _write(run_dir, "phase4_trend_analysis.json", {"cluster_analysis": [
        {"cluster_name": name, "executive_summary": "Growth-based summary.", "text_source": "llm"}]})
    ctx, _ = build_context(run_dir)
    assert ctx["trends"][0]["analysis"]["executive_summary"] == "Growth-based summary."
    assert ctx["trends"][1]["analysis"] == {}                                # เทรนด์ที่ไม่อยู่ในไฟล์ใหม่ไม่ย้อนไปใช้ของ ⑦


# ============================================================================
# 🆕 (2026-10-12) ช่วงราคาต่อปริมาณ (tier_basis = unit_price) - ข้อความช่วง/วิธีการ + ขนาด · ฿ ต่อหน่วย บนการ์ดสินค้า
# ผลรอบเก่า (tier_basis ไม่มี = price) ยังออกมาเหมือนเดิมทุกตัวอักษร (ทดสอบข้างบน)
# ============================================================================
def _unit_fields(size=30.0, unit_price=8.6, label="ml", mini=False, tier=1):
    return {"size": size, "unit_label": label, "unit_price": unit_price, "is_mini": mini, "unit_tier": tier}


def test_render_trend_report_unit_price_tiers(run_dir):
    def tier(label, lo, hi, unit_from, unit_to, name, rank, price, **unit):
        return {"label": label, "price_from": lo, "price_to": hi, "n_total": 100, "n_pool": 2,
                "unit_from": unit_from, "unit_to": unit_to, "unit_label": "ml",
                "product": {**_match_product(name, "Skin Care", 0.4 - rank / 100, rank, price), **unit}}

    _write(run_dir, "phase3_scale_validation_nvidia_result.json", {
        "n_products_total": 1000, "tier_basis": "unit_price",
        "results": {"Social::Barrier Care": {
            "n_products_compared": 1000, "top_matches": [_match_product("Serum A", "Skin Care", 0.4, 1)],
            "by_category": {"pool_size": 10, "main_category": "Skin Care", "n_category": 3231,
                            "distribution": [{"group": "Serum", "n": 10}],
                            "categories": [{"group": "Skin Care · Serum", "parent": "Skin Care", "subgroup": "Serum", "color": 0,
                                            "n_pool": 10, "n_total": 120,
                                            "products": [_match_product("Serum A", "Skin Care", 0.4, 1)],
                                            "price_tiers": [
                                                tier("low", 45, 899, 0.81, 9.97, "Big Bottle", 7, 299.0, **_unit_fields(120, 2.49, tier=0)),
                                                tier("mid", 59, 1500, 9.97, 22.67, "Mid Jar", 9, 345.0, **_unit_fields(30, 11.5)),
                                                tier("high", 220, 2400, 22.9, 657.33, "Tiny Vial", 12, 220.0,
                                                     **_unit_fields(7, 31.43, mini=True, tier=2))]}]}}}})
    ctx = _rendered_ctx(run_dir)
    assert ctx["meta"]["tier_basis"] == "unit_price"
    t = ctx["trends"][0]["categories"]["categories"][0]["price_tiers"]
    assert (t[0]["unit_from"], t[0]["unit_to"], t[2]["unit_label"]) == (0.81, 9.97, "ml")
    assert t[2]["product"]["is_mini"] is True and t[1]["product"]["size"] == 30.0
    en = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert "<b>Low unit price</b> up to THB 9.97/ml" in en and "<b>Mid unit price</b> THB 9.97-22.7/ml" in en
    assert "<b>High unit price</b> from THB 22.9/ml" in en
    assert "120 ml · THB 2.49/ml" in en and "30 ml · THB 11.5/ml" in en and "7 ml · THB 31.4/ml · trial size" in en
    assert "By price per unit:" in en and "price per ml, g or piece" in en and "THB 45-899" not in en
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "<b>ราคาต่อปริมาณต่ำ</b> ไม่เกิน 9.97 บาท/มล." in th and "7 มล. · 31.4 บาท/มล. · ขนาดทดลอง" in th
    assert "แยกตามราคาต่อปริมาณ:" in th and "ช่วงราคา = ราคาต่อ มล., ก. หรือชิ้น" in th and "45-899 บาท" not in th


def _unit_fit(**kw):
    """_fit ของรอบ unit_price: ทุกสินค้ามี size/unit_price/unit_label และช่วงเป็นราคาขายที่พบจริงในกลุ่ม (ข้อมูลประกอบ)"""
    fit = _fit(**kw)
    fit["tier_basis"] = "unit_price"
    for c in fit["categories"]:
        for t in c["tiers"]:
            for m in t["top"] + ([t["brand_best"]] if t["brand_best"] else []):
                m.update(size=30.0, unit_label="ml", unit_price=round((m.get("sale_price_thb") or 100) / 30, 2), is_mini=False,
                         unit_tier=1)
        if c["brand_best"]:
            c["brand_best"].update(size=30.0, unit_label="ml", unit_price=6.63, is_mini=False, unit_tier=1)
    return fit


def test_brand_reports_unit_price_basis(run_dir):
    brand_style = {**BRAND, "company_name": "S&J"}
    ctx, coverage, catalog = _brand_fixture(run_dir, rank=20)
    coverage["coverage"]["Social::Barrier Care"]["category_fit"] = _unit_fit(rank=20)
    b = build_brand_context(ctx, coverage, catalog, DEFAULT_CONFIG)
    assert b["tier_basis"] == "unit_price"
    g = b["rows"][0]["graded"]
    assert (g["size"], g["unit_label"], g["unit_price"]) == (30.0, "ml", 6.63)
    en = render_brand_html(ctx, b, brand_style, {}, "T", datetime(2026, 10, 12))
    body = html.unescape(re.sub(r"<style>.*?</style>", "", en, flags=re.S))
    assert "Mid unit price" in body and "THB 160-395" not in body and "(THB" not in body.split("Compared with products in")[1][:200]
    assert "30 ml · THB 6.63/ml" in body and "of its type & unit-price group" in body and "in sales" not in body and "unit-price groups" in body.lower()
    th = render_brand_html(localize(ctx, "th"), b, brand_style, {}, "T", datetime(2026, 10, 12), lang="th")
    assert "ราคาต่อปริมาณกลาง" in th and "ช่วงราคาต่อปริมาณ" in th and "160-395 บาท" not in th
    # ผลเก่า (ไม่มี tier_basis) -> ราคาขายเหมือนเดิม
    ctx2, cov2, cat2 = _brand_fixture(run_dir, rank=20)
    old = build_brand_context(ctx2, cov2, cat2, DEFAULT_CONFIG)
    assert old["tier_basis"] == "price"
    assert "THB 160-395" in render_brand_html(ctx2, old, brand_style, {}, "T", datetime(2026, 10, 12))


def test_category_report_unit_price_basis(run_dir):
    brand_style = {**BRAND, "company_name": "S&J"}
    ctx, coverage, catalog = _brand_fixture(run_dir, rank=20)
    coverage["coverage"]["Social::Barrier Care"]["category_fit"] = _unit_fit(rank=20)
    b = build_category_context(ctx, coverage, catalog, DEFAULT_CONFIG)
    assert b["tier_basis"] == "unit_price"
    en = render_brand_category_html(ctx, b, brand_style, {}, "T", datetime(2026, 10, 12))
    body = html.unescape(re.sub(r"<style>.*?</style>", "", en, flags=re.S))
    assert "Mid unit price" in body and "THB 160-395" not in body and 'class="tier-range"' not in body
    assert "in Skin Care at Mid unit price, your Zenith Cream ranks #20 (Good)." in body
    assert "Unit-price groups" in body and "30 ml · THB 6.63/ml" in body
    th = render_brand_category_html(localize(ctx, "th"), apply_th_category(b), brand_style, {}, "T", datetime(2026, 10, 12), lang="th")
    assert "ราคาต่อปริมาณกลาง" in th and "ช่วงราคาต่อปริมาณ" in th and "160-395 บาท" not in th


# ---------------------------------------------------------------- แหล่งที่มาของข้อมูล (หน้า Notes) -------------------------

def _sources_run(run_dir, tmp_path):
    """รอบปลอม + ผลสายทั้ง 3 (มี triplet_provenance), ผล ⑥ (คีย์เวิร์ดซ้ำ 1 คำ), ⑫ (จำนวนสินค้า) และแคตตาล็อกที่มีวันเก็บข้อมูล"""
    def prov(titles, region=""):
        return [{"triplet": ["a", "r", "b"], "doc_index": i, "title": t, "source_region": region, "evidence": "e", "verified": True}
                for i, t in enumerate(titles)] + [{"triplet": ["c", "r", "d"], "doc_index": 0, "title": titles[0],
                                                   "source_region": region, "evidence": "e2", "verified": True}]

    _write(run_dir, "phase1_paper_stream_result.json", {"pool_size": 126, "n_scraped": 4,
                                                         "triplet_provenance": prov(["Study A", "Study B", "Study C"])})
    _write(run_dir, "phase2_social_stream_result.json", {"n_scraped": 7, "triplet_provenance": prov(
        ["Reddit: post 1", "Reddit: post 2", "Pantip: รีวิว", "YouTube: clip"])})
    _write(run_dir, "phase2_news_stream_result.json", {"pool_intl": 630, "pool_th": 463, "n_scraped_intl": 2, "n_scraped_th": 0,
                                                        "triplet_provenance": prov(["Deal A", "Deal B"], "intl")})
    _write(run_dir, "phase2_growth_score_result.json", {"as_of": "2026-08", "keywords": [
        {"keyword": "retinol"}, {"keyword": "retinol"}, {"keyword": "ceramide"}], "clusters": []})
    _write(run_dir, "phase3_scale_validation_nvidia_result.json", {"n_products_total": 27216, "results": {}})
    csv = tmp_path / "catalog.csv"
    pd.DataFrame({"scraped_date": ["06/10/2026", "09/10/2026", "07/10/2026"], "brand": ["A", "B", "C"],
                  "product_name": ["p1", "p2", "p3"], "main_image": [None] * 3, "product_url": [None] * 3}).to_csv(csv, index=False)
    return csv


def test_data_sources_from_run_files(run_dir, tmp_path):
    csv = _sources_run(run_dir, tmp_path)
    src = build_context(run_dir, catalog_path=csv)[0]["meta"]["sources"]
    assert src["papers"]["n_used"] == 3                                               # เอกสารเดียวหลาย triplet นับครั้งเดียว
    assert src["discussions"]["platforms"] == [{"name": "Reddit", "n": 2}, {"name": "Pantip", "n": 1}, {"name": "YouTube", "n": 1}]
    assert src["news"] == {"intl": {"n_used": 2}}                                     # ข่าวไทย 0 ชิ้น = ไม่มีคีย์ th
    assert src["search"] == {"n_keywords": 2}                                         # นับคีย์เวิร์ดไม่ซ้ำ
    assert src["products"] == {"n": 27216, "collected_from": "2026-10-06", "collected_to": "2026-10-09"}
    assert "categories" not in src                                                    # รอบนี้ไม่มีหน้าหมวด


def test_data_sources_missing_files_are_skipped(run_dir):
    assert build_context(run_dir)[0]["meta"]["sources"] == {}


def test_source_rows_en_th_and_skip_empty(run_dir, tmp_path):
    from i18n import date_range, localize, source_rows
    ctx, _ = build_context(run_dir, catalog_path=_sources_run(run_dir, tmp_path))
    en = dict(source_rows(ctx["meta"], "en"))
    assert en["Research articles"].startswith("3 used - searched") and "OpenAlex" in en["Research articles"]
    assert en["Online channels"] == "4 posts and videos used - Reddit 2, Pantip 1, YouTube 1"
    assert en["News"] == "2 international articles used"                             # ไม่มีข่าวไทย = ไม่พูดถึงเลย
    assert "2 keywords" in en["Search interest"] and "Aug 2026" in en["Search interest"]
    assert en["Products"] == "Konvy - 27,216 beauty and personal care products - collected 6 - 9 Oct 2026"
    assert "Product categories" not in en
    th = dict(source_rows(localize(ctx, "th")["meta"], "th"))
    assert th["ข่าว"] == "ข่าวต่างประเทศ ใช้ 2 ชิ้น"
    assert th["สินค้า"].endswith("เก็บข้อมูล 6 - 9 ต.ค. 2026") and "ส.ค. 2026" in th["ความสนใจค้นหา"]
    one = {"sources": {"news": {"th": {"n_used": 1}}, "discussions": {"platforms": [{"name": "Pantip", "n": 1}]}}}
    assert dict(source_rows(one, "en")) == {"News": "1 Thai article used",
                                            "Online channels": "1 post or video used - Pantip 1"}   # เอกพจน์
    assert source_rows({"sources": {}}, "en") == [] and source_rows(None, "th") == []
    assert date_range("2026-10-06", "2026-10-06", "en") == "6 Oct 2026"
    assert date_range("2026-09-28", "2026-10-09", "en") == "28 Sep - 9 Oct 2026"
    assert date_range("2025-12-30", "2026-01-02", "en") == "30 Dec 2025 - 2 Jan 2026"
    assert date_range(None, None, "en") == ""


def test_notes_page_lists_data_sources(run_dir, tmp_path):
    from i18n import localize
    ctx, _ = build_context(run_dir, catalog_path=_sources_run(run_dir, tmp_path))
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert "Where the data comes from" in html and "Research articles" in html and "Online channels" in html
    assert "Paper" not in html and "Social" not in html                              # ยังไม่เรียกชื่อสายหลักฐาน
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "แหล่งที่มาของข้อมูล" in th and "ช่องทางออนไลน์" in th
    # รอบที่ไม่มีข้อมูลแหล่งเลย: ไม่มีกล่อง (ไม่ใช่กล่องว่าง)
    for f in ("phase1_paper_stream_result.json", "phase2_social_stream_result.json", "phase2_news_stream_result.json",
              "phase2_growth_score_result.json", "phase3_scale_validation_nvidia_result.json"):
        (run_dir / f).unlink()
    ctx2, _ = build_context(run_dir)
    enrich_trends(ctx2["trends"], {}, llm_call=None, log=lambda *_: None)
    assert "Where the data comes from" not in render_html(ctx2, BRAND, {}, "T", datetime(2026, 1, 1), "x")


# ============================================================================
# 🆕 (2026-10-14) หน้าสินค้าของ ⑰: ช่วง ฿/หน่วยของแต่ละกลุ่มราคา (ที่สินค้า 80% ของกลุ่มอยู่ + ค่ากลาง)
# ============================================================================
from brand_category_data import group_ranges  # noqa: E402


def _unit_rows():
    rows = []
    # Skin Care กลุ่มต่ำ: 10 ชิ้น 1..10 บาท/มล. + 1 ชิ้นขนาดทดลอง (ไม่นับ) + 1 ชิ้นไม่มี ฿/หน่วย (ไม่นับ)
    rows += [{"EM_L2": "Skin Care", "unit_tier": 0, "unit_kind": "gml", "unit_label": "ml", "unit_price": float(v), "is_mini": False}
             for v in range(1, 11)]
    rows += [{"EM_L2": "Skin Care", "unit_tier": 0, "unit_kind": "gml", "unit_label": "ml", "unit_price": 500.0, "is_mini": True},
             {"EM_L2": "Skin Care", "unit_tier": 0, "unit_kind": "price", "unit_label": None, "unit_price": None, "is_mini": False}]
    # กลุ่มกลาง: ml และ g ปนกัน (แต่ละหน่วย >= 25%) -> ป้าย ml_g
    rows += [{"EM_L2": "Skin Care", "unit_tier": 1, "unit_kind": "gml", "unit_label": u, "unit_price": float(v), "is_mini": False}
             for v, u in zip(range(10, 20), ["ml", "g"] * 5)]
    # Makeup Tools: ชิ้น 6 ชิ้น; Hair Care กลุ่มสูง: มีแค่ 3 ชิ้น -> ไม่แสดงช่วง
    rows += [{"EM_L2": "Makeup Tools & Equipment", "unit_tier": 2, "unit_kind": "pcs", "unit_label": "pcs", "unit_price": 20.0 + i,
              "is_mini": False} for i in range(6)]
    rows += [{"EM_L2": "Hair Care", "unit_tier": 2, "unit_kind": "gml", "unit_label": "ml", "unit_price": 5.0, "is_mini": False}] * 3
    return rows


def test_group_ranges_p10_p90_units_and_min_items():
    r = group_ranges(_unit_rows())
    low = r[("Skin Care", "low")]
    assert low["unit_label"] == "ml" and low["n"] == 10 and low["p50"] == 5.5            # ขนาดทดลอง/ไม่มี ฿ ต่อหน่วย ไม่นับ
    assert round(low["p10"], 2) == 1.9 and round(low["p90"], 2) == 9.1
    assert r[("Skin Care", "mid")]["unit_label"] == "ml_g" and r[("Skin Care", "mid")]["n"] == 10
    assert r[("Makeup Tools & Equipment", "high")]["unit_label"] == "pcs"
    assert ("Hair Care", "high") not in r                                                 # < 5 ชิ้น = ตัวเลขไม่นิ่ง ไม่แสดง
    assert group_ranges([]) == {} and group_ranges([{"EM_L2": "x"}]) == {}


def test_brand_page_shows_group_ranges_and_unit_note(run_dir):
    ctx, coverage, catalog = _brand_fixture(run_dir, rank=20)
    fit = coverage["coverage"]["Social::Barrier Care"]["category_fit"]
    fit["tier_basis"] = "unit_price"
    ranges = {("Skin Care", "low"): {"unit_label": "ml", "n": 50, "p10": 0.42, "p50": 1.33, "p90": 8.58},
              ("Skin Care", "mid"): {"unit_label": "ml_g", "n": 50, "p10": 1.8, "p50": 3.39, "p90": 19.9}}
    # 🆕 (2026-10-14) top 5 แสดงราคา/ปริมาตรใต้ราคา (เฉพาะชิ้นที่มี ฿ ต่อหน่วย)
    first_top = fit["categories"][0]["tiers"][0]["top"]
    first_top[0].update(unit_price=3.64, unit_label="ml")
    first_top[1].update(unit_price=0.5, unit_label="g")
    cat = build_category_context(ctx, coverage, catalog, DEFAULT_CONFIG, ranges)
    low, mid, high = cat["rows"][0]["pages"][0]["tiers"]
    assert low["unit_range"]["p90"] == 8.58 and high["unit_range"] is None
    # ผล ⑬ แบบราคาขาย (ไม่มี tier_basis = unit_price) ไม่แนบช่วง ฿/หน่วย
    ctx2, cov2, cat2 = _brand_fixture(run_dir, rank=20)
    assert build_category_context(ctx2, cov2, cat2, DEFAULT_CONFIG, ranges)["rows"][0]["pages"][0]["tiers"][0]["unit_range"] is None
    b = build_brand_context(ctx, coverage, catalog, DEFAULT_CONFIG)
    assert b["tier_basis"] == "unit_price"
    en = render_brand_html(ctx, b, {**BRAND, "company_name": "S&J"}, {}, "T", datetime(2026, 10, 14), cat=cat)
    det = en[en.index('data-label="Brand Trend 1 Detail"'):]
    det = det[:det.index("</section>")]
    assert "Price range THB 0.42-8.58/ml<" in det and "Price range THB 1.80-19.9/ml/g<" in det and "median" not in det
    assert det.count('class="tier-typical"') == 2 and 'class="tier-grid k3 ranged"' in det             # 2 กลุ่มมีช่วง (กลุ่มสูงไม่มี)
    assert det.count('<span class="un">') == 2 and '<span class="un">THB 3.64/ml</span>' in det and '<span class="un">THB 0.50/g</span>' in det
    assert "where 80% of the group" in det and "Unit-price groups = price per ml, g or piece" in det    # หมายเหตุตามโหมดราคาต่อปริมาณ
    assert "this category&#39;s store prices split into three" not in det
    th = render_brand_html(localize(ctx, "th"), b, {**BRAND, "company_name": "S&J"}, {}, "T", datetime(2026, 10, 14), lang="th",
                           cat=apply_th_category(build_category_context(localize(ctx, "th"), coverage, catalog, DEFAULT_CONFIG, ranges)))
    th_det = th[th.index('data-label="Brand Trend 1 Detail"'):]
    th_det = th_det[:th_det.index("</section>")]
    assert "ช่วงราคา 0.42-8.58 บาท/มล.<" in th_det and "ค่ากลาง" not in th_det and "ส่วนใหญ่" not in th_det and "ช่วงราคาต่อปริมาณ = ราคาต่อ มล./ก./ชิ้น" in th_det


# ============================================================================
# 🆕 (2026-10-14) หน้าเทรนด์ = เฉพาะเทรนด์ที่ผ่านดัชนีตลาด; เทรนด์ที่จับคู่สินค้าไม่ได้ (ช่องทางการขาย) มีหน้าอธิบาย + "ไม่พบสินค้าในตลาด"
# 🆕 (2026-10-15) เจ้าของงานให้เอาเทรนด์ที่ไม่พบสินค้าออกจากระบบ: ค่าเริ่มต้น (SHOW_NO_PRODUCT_TRENDS = False) ตัดทั้งหน้า/แถวตาราง/จำนวน
# สวิตช์ = True ยังออกมาแบบ 2026-10-14 (ทดสอบด้วย monkeypatch)
# ============================================================================
import report_data as rd  # noqa: E402
from report_data import no_product_keys, product_trends  # noqa: E402


def _page_rule_run(run_dir):
    """3 เทรนด์ที่ ⑪ เลือก (A เหนือเส้น, B ใต้เส้น) + ช่องทางการขาย C เหนือเส้น (excluded) + D เหนือเส้นแต่ข้อมูลไม่พอ (checked) + E ใต้เส้น"""
    _write(run_dir, "phase3_trend_highlights_result.json", {
        "top_n": 2, "requested_top_n": 5, "n_trends_total": 5, "growth_line": 0.5, "profiles": [],
        "selected_trends": [
            {"overall_rank": 1, "stream": "Social", "trend": "Trend A", "rank_score": 0.9, "top_rank": 1},
            {"overall_rank": 5, "stream": "Paper", "trend": "Trend B", "rank_score": 0.3, "top_rank": 2},   # ใต้เส้น (เลือกไว้ด้วยลำดับเก่า)
        ],
        "excluded_trends": [{"overall_rank": 2, "stream": "News", "trend": "Live Commerce",
                             "reason": "เทรนด์ประเภทช่องทาง/พฤติกรรมการซื้อ - ไม่มีคุณสมบัติสินค้าให้จับคู่"}],
        "failed_trends": [],
        "checked_trends": [{"overall_rank": 3, "stream": "Paper", "trend": "Trend D", "matchable": False,
                            "reason": "ข้อมูลไม่พอทุกช่องที่ใช้จับคู่สินค้า"},
                           {"overall_rank": 4, "stream": "Paper", "trend": "Trend E", "matchable": False,
                            "reason": "ข้อมูลไม่พอทุกช่องที่ใช้จับคู่สินค้า"}]})
    scores = [(1, "Social", "Trend A", 0.9), (2, "News", "Live Commerce", 0.8), (3, "Paper", "Trend D", 0.6),
              (4, "Paper", "Trend E", 0.4), (5, "Paper", "Trend B", 0.3)]
    _write(run_dir, "phase2_rank_score_final_mode_result.json",
           [_rank_row(i, st, nm, sc, sc) for i, st, nm, sc in scores])


def test_no_product_trends_removed_from_context_by_default(run_dir):
    _page_rule_run(run_dir)
    ctx, _ = build_context(run_dir)
    # เทรนด์ที่ไม่พบสินค้า (Live Commerce ช่องทางการขาย, D / E ข้อมูลไม่พอ) ไม่มีหน้า ไม่มีแถวภาพรวม ไม่นับในจำนวนเทรนด์
    assert [(t["rank"], t["name"], t["no_products"]) for t in ctx["trends"]] == [(1, "Trend A", None)]
    gp = ctx["growth"]
    assert [x["name"] for x in gp["all"]] == ["Trend A", "Trend B"] and gp["n_total"] == 2 and gp["n_above"] == 1
    assert [x["rank"] for x in gp["all"]] == [1, 2]                                        # เรียงเลขใหม่
    assert all(x["matchable"] is not False for x in gp["all"]) and ctx["meta"]["n_trends_total"] == 2   # 5 - 3
    assert ctx["meta"]["top_n"] == 1
    # ร่องรอย: รายชื่อที่ถูกตัดอยู่ใน context + เหตุผลเดิมของ ⑪ ยังอยู่ใน excluded
    assert [t["name"] for t in ctx["no_product_trends"]] == ["Live Commerce", "Trend D", "Trend E"]
    assert [e["name"] for e in ctx["excluded"]] == ["Live Commerce"]
    assert set(no_product_keys(json.loads((run_dir / "phase3_trend_highlights_result.json").read_text(encoding="utf-8")))) == {
        ("News", "Live Commerce"), ("Paper", "Trend D"), ("Paper", "Trend E")}


def test_no_product_trends_removed_from_rendered_report(run_dir):
    _page_rule_run(run_dir)
    ctx, _ = build_context(run_dir)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    for lang, doc_ctx in (("en", ctx), ("th", localize(ctx, "th"))):
        doc = render_html(doc_ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x", lang=lang)
        assert 'data-label="Trend 1"' in doc and 'data-label="Trend 2"' not in doc and 'data-label="Evidence 2"' not in doc
        body = re.sub(r"<(style|script)>.*?</\1>", "", doc, flags=re.S)   # CSS มีคำ "Trend Drivers"
        for word in ("Live Commerce", "Trend D", "Trend E", "No products found in the market", "ไม่พบสินค้าในตลาด"):
            assert word not in body, (lang, word)


def test_market_overview_recomputed_without_no_product_trends(run_dir, monkeypatch):
    """ภาพรวมตลาด (มัธยฐาน/จำนวนเทรนด์/ข้อความสรุป) ต้องไม่นับและไม่เอ่ยชื่อเทรนด์ที่ถูกตัด - คิดใหม่จากเทรนด์ที่เหลือ"""
    ctx = _with_growth_files(run_dir)                     # Barrier Care + Stable Retinol (ไม่มีผลพยากรณ์) + Live Commerce (ถูกตัด)
    market = ctx["overview"]["market"]
    assert market["basis"]["n_trends"] == 1 and market["summary_source"] == "numbers"
    assert market["basis"]["median_change_pct_short"] == 40.0 and market["basis"]["median_change_pct_long"] == 60.2   # Barrier Care ตัวเดียว (ปี 3 / ปี 5)
    assert market["basis"]["short_year"] == rd.SHORT_YEAR and market["basis"]["long_year"] == rd.LONG_YEAR
    assert "Live Commerce" not in market["summary"] and "Barrier Care" in market["summary"]
    # ไม่มีเทรนด์ที่ตัด (หรือชื่อที่ตัดไม่อยู่ในผลการเติบโต) = ภาพรวมเดิมไม่ถูกแตะ
    same = {"summary": "LLM text", "basis": {"short_year": rd.SHORT_YEAR, "n_trends": 15}}
    clusters = {"clusters": [{"trend": "A", "forecast": {"change_pct": [1, 2, 3, 4, 5]}}]}
    assert rd.market_without_trends(same, clusters, [], {}, set()) is same
    assert rd.market_without_trends(same, clusters, [], {}, {"Z"}) is same
    # 🆕 (2026-10-19) ไฟล์ ⑭-⑮ ที่เขียนตอนระยะสั้นเป็นปีอื่น (ปีที่ 2) -> คิดใหม่ที่ปีระยะสั้นปัจจุบัน ไม่เอาตัวเลข/ข้อความปีเก่ามาแสดง
    stale = {"summary": "Median +2% in year 2.", "basis": {"short_year": 2, "n_trends": 1, "median_change_pct_short": 2.0}}
    redone = rd.market_without_trends(stale, clusters, [], {}, set())
    assert redone is not stale and redone["basis"]["short_year"] == rd.SHORT_YEAR
    assert redone["basis"]["median_change_pct_short"] == 3.0 and "year 2" not in redone["summary"]
    assert rd.market_without_trends({"summary": "old file without basis"}, clusters, [], {}, set())["summary"] == "old file without basis"
    monkeypatch.setattr(rd, "SHOW_NO_PRODUCT_TRENDS", True)    # สวิตช์เปิด = ไม่ตัด -> ภาพรวมจากไฟล์ตามเดิม
    ctx_on, _ = build_context(run_dir)
    assert "basis" not in ctx_on["overview"]["market"] and ctx_on["no_product_trends"] == []


def test_page_trends_only_above_market_line_with_no_product_pages(run_dir, monkeypatch):
    monkeypatch.setattr(rd, "SHOW_NO_PRODUCT_TRENDS", True)     # สวิตช์เปิด = แบบ 2026-10-14
    _page_rule_run(run_dir)
    ctx, _ = build_context(run_dir)
    got = [(t["rank"], t["name"], t["no_products"]) for t in ctx["trends"]]
    # เรียงตามคะแนนปีที่ 2: A (0.9), ช่องทาง (0.8), ข้อมูลไม่พอ (0.6) - Trend B (เลือกไว้แต่ 0.3 ใต้เส้น) และ E (0.4) ไม่มีหน้า
    assert got == [(1, "Trend A", None), (2, "Live Commerce", "channel"), (3, "Trend D", "no_data")]
    assert ctx["meta"]["top_n"] == 3 and all(t["products"] == [] for t in ctx["trends"][1:])
    only = product_trends(ctx)["trends"]
    assert [(t["rank"], t["name"]) for t in only] == [(1, "Trend A")]                   # ⑰ เทียบสินค้า - ไม่รวมหน้าไม่พบสินค้า


def test_no_product_trend_pages_in_report_en_th(run_dir, monkeypatch):
    monkeypatch.setattr(rd, "SHOW_NO_PRODUCT_TRENDS", True)     # สวิตช์เปิด = แบบ 2026-10-14
    _page_rule_run(run_dir)
    ctx, _ = build_context(run_dir)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    en = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert 'data-label="Trend 2"' in en and 'data-label="Evidence 2"' in en and 'data-label="Trend 3"' in en
    ev = en[en.index('data-label="Evidence 2"'):]
    ev = ev[:ev.index("</section>")]
    assert "No products found in the market" in ev and "sales channel or a buying behaviour" in ev
    ev3 = en[en.index('data-label="Evidence 3"'):]
    assert "too thin to describe a product" in ev3[:ev3.index("</section>")]
    assert 'data-label="Trend 4"' not in en and 'data-label="Evidence 4"' not in en       # Trend B ต่ำกว่าเส้น/E ใต้เส้น = ไม่มีหน้า
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "ไม่พบสินค้าในตลาด" in th and "พูดถึงช่องทางการขายหรือพฤติกรรมการซื้อ" in th


# ============================================================================
# 🆕 (2026-10-14) หน้าภาคผนวก "ภาพรวมทุกเทรนด์ - CAGR" (ค่าเดียวกับหน้าภาพรวม แปลงเป็นอัตราเติบโตเฉลี่ยต่อปีแบบทบต้น - ไว้ดูเทียบ)
# ============================================================================
from report_data import cagr_pct, cagr_view  # noqa: E402


@pytest.fixture
def legacy_pages(monkeypatch):
    """🆕 (2026-10-19) หน้า CAGR และหน้า YoY แยกถูกแทนด้วยหน้ารวม (SHOW_COMBINED_PAGE) แล้ว สองหน้านี้ปิดเป็นค่าเริ่มต้น
    เทสต์ของหน้าแยกเดิมจึงเปิดสวิตช์กลับมาเอง (และปิดหน้ารวมให้เทสต์ไม่ปนกัน)"""
    monkeypatch.setattr(rd, "SHOW_CAGR_PAGE", True)
    monkeypatch.setattr(rd, "SHOW_YOY_PAGE", True)
    monkeypatch.setattr(rd, "SHOW_COMBINED_PAGE", False)
    monkeypatch.setattr(rd, "SHOW_SCATTER_PAGE", False)


def test_cagr_pct_values():
    assert cagr_pct(29.0, 1) == 29.0                       # ปีที่ 1 = ค่าเดิม
    assert round(cagr_pct(29.0, 2), 1) == 13.6             # 1.29^(1/2) - 1
    assert round(cagr_pct(125.0, 5), 1) == 17.6            # 2.25^(1/5) - 1
    assert cagr_pct(0.0, 3) == 0.0 and round(cagr_pct(-20.0, 2), 1) == -10.6
    assert cagr_pct(30.4, 5) < 5.5 and cagr_pct(12.0, 2) > 5.8     # ปัดครั้งเดียวจากค่าจริง (เดิมปัดซ้อน 5.45 -> 5.5 -> 6)
    assert cagr_pct(None, 2) is None and cagr_pct(-100.0, 2) is None and cagr_pct(-150.0, 3) is None


def test_cagr_view_keeps_order_flags_and_does_not_touch_original(run_dir, legacy_pages):
    ctx = _with_growth_files(run_dir)
    gp = ctx["growth"]
    before = [list(x["expected_pct"]) for x in gp["all"]]
    gc = gp["cagr_view"]
    assert [x["name"] for x in gc["all"]] == [x["name"] for x in gp["all"]]                      # ลำดับ/เทรนด์เดิม
    assert [x["above_line"] for x in gc["all"]] == [x["above_line"] for x in gp["all"]]
    assert [x["scores"] for x in gc["all"]] == [x["scores"] for x in gp["all"]]                 # สีแท่งตามเดิม
    assert [list(x["expected_pct"]) for x in gp["all"]] == before                               # ไม่แก้ของเดิม
    first, first_c = gp["all"][0], gc["all"][0]
    assert first_c["expected_pct"][0] == first["expected_pct"][0]                               # ปีที่ 1 เท่ากัน
    assert first_c["expected_pct"][1] == cagr_pct(first["expected_pct"][1], 2)
    assert first_c["expected_pct"][4] == cagr_pct(first["expected_pct"][4], 5)
    assert gc["market_pct"][4] == cagr_pct(gp["market_pct"][4], 5) and gc["cagr_view"] is None
    assert all(x["bars"][1] for x in gc["all"] if x["expected_pct"][1] is not None)             # แท่งคำนวณใหม่


def test_cagr_page_renders_en_th_and_is_in_appendix(run_dir, legacy_pages):
    ctx = _with_growth_files(run_dir)
    en = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    page = en[en.index('data-label="All Trends CAGR"'):]
    page = page[:page.index("</section>")]
    assert "All Trends | CAGR view (average per year)" in page and "compounded" in page
    assert "the All Trends page" not in page                                    # ไม่อ้างหน้าที่ไม่มีแล้ว
    assert "In back-tests" not in page or "of the forecast for year 2" in page
    assert ">+14%</span>" in page                                  # Barrier Care ปีที่ 1 = +14% (ค่าเดิม); ปีที่ 2 = 1.282^(1/2)-1 = +13%
    # ค่าเริ่มต้น: ไม่มีหน้าภาพรวมแบบสะสมแล้ว - CAGR ต่อจากหน้า Top 5 ก่อนเทรนด์
    assert 'data-label="All Trends"' not in en and "Appendix | All Trends" not in en
    assert en.index('data-label="Top 5 Short vs Long"') < en.index('data-label="All Trends CAGR"') < en.index('data-label="Trend 1"')
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "ภาพรวมทุกเทรนด์ | มุมมอง CAGR (เฉลี่ยต่อปี)" in th and "อัตราการเติบโตเฉลี่ยต่อปี" in th
    assert th.count('<section class="page') == en.count('<section class="page')


def test_cagr_page_uses_display_names(run_dir, legacy_pages):
    from display_names import apply_display_names
    ctx = _with_growth_files(run_dir)
    apply_display_names(ctx, {"Social::Barrier Care": "Skin Barrier Recovery"})
    en = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    page = en[en.index('data-label="All Trends CAGR"'):]
    page = page[:page.index("</section>")]
    assert "Skin Barrier Recovery" in page and "Barrier Care" not in page


# ============================================================================
# 🆕 (2026-10-14) หน้าภาคผนวก "ภาพรวมทุกเทรนด์ - YoY" (เทียบปีก่อนหน้า - ไว้ดูเทียบ)
# ============================================================================
from report_data import yoy_series, yoy_view  # noqa: E402


def test_yoy_series_values_and_gaps():
    r1 = lambda xs: [None if v is None else round(v, 1) for v in xs]                       # noqa: E731
    assert r1(yoy_series([16.0, 29.0, 53.0, 70.0, 125.0])) == [16.0, 11.2, 18.6, 11.1, 32.4]    # ปีที่ 1 เทียบ 12 เดือนล่าสุด
    assert r1(yoy_series([10.0, None, 44.0, 59.0, 121.0])) == [10.0, None, None, 10.4, 39.0]    # ปีที่ขาด = ปีถัดไปไม่มีฐาน
    assert yoy_series([None] * 5) == [None] * 5 and r1(yoy_series([-20.0, -10.0])) == [-20.0, 12.5]


def test_yoy_view_colours_follow_market_yoy_and_leave_original(run_dir, legacy_pages):
    ctx = _with_growth_files(run_dir)
    gp = ctx["growth"]
    before = [list(x["expected_pct"]) for x in gp["all"]]
    gy = gp["yoy_view"]
    assert [x["name"] for x in gy["all"]] == [x["name"] for x in gp["all"]]                    # ลำดับเดิม
    assert [list(x["expected_pct"]) for x in gp["all"]] == before and gy["yoy_view"] is None and gy["cagr_view"] is None
    assert gy["market_pct"] == yoy_series(gp["market_pct"])
    for x in gy["all"]:
        for i, v in enumerate(x["expected_pct"]):
            if v is not None:                                                                  # สีแท่ง = เทียบ YoY ตลาดปีเดียวกัน
                assert x["scores"][i] == (1.0 if v >= gy["market_pct"][i] else 0.0)
    first, first_y = gp["all"][0], gy["all"][0]
    assert first_y["expected_pct"][0] == first["expected_pct"][0]                              # ปีที่ 1 เท่ากัน


def test_yoy_page_renders_en_th_after_cagr_in_appendix(run_dir, legacy_pages):
    ctx = _with_growth_files(run_dir)
    en = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    page = en[en.index('data-label="All Trends YoY"'):]
    page = page[:page.index("</section>")]
    assert "All Trends | YoY view (vs the year before)" in page and "the All Trends page" not in page
    assert "not by the YoY figure" in page                                      # บอกเกณฑ์เรียงแถวเอง เพราะไม่มีหน้าสะสมให้ดูแล้ว
    assert en.index('data-label="All Trends CAGR"') < en.index('data-label="All Trends YoY"') < en.index('data-label="Trend 1"')
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "ภาพรวมทุกเทรนด์ | มุมมอง YoY (เทียบปีก่อนหน้า)" in th and th.count('<section class="page') == en.count('<section class="page')


def test_cumulative_overview_page_is_off_by_default_and_switchable(run_dir, legacy_pages):
    ctx = _with_growth_files(run_dir)
    assert ctx["growth"]["show_cumulative"] is False
    en = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert 'data-label="All Trends"' not in en and "All Trends | Year 1 to Year 5" not in en
    assert 'data-label="Top 5 Short vs Long"' in en and 'data-label="All Trends CAGR"' in en and 'data-label="All Trends YoY"' in en
    # หน้า CAGR/YoY อธิบายตัวเองได้: เกณฑ์เรียงแถว + เส้นประ + หน้ารายละเอียด + ช่วงคลาดเคลื่อนของระดับยอดค้นหา
    for label in ("All Trends CAGR", "All Trends YoY"):
        page = en[en.index(f'data-label="{label}"'):]
        page = page[:page.index("</section>")]
        assert "ordered by expected growth to year 3" in page and "Dashed line = the market as a whole" in page
        assert "Detail pages cover trends above the dashed line in year 3" in page
        assert "8 times in 10 the actual search level was within -21% to +26% of the forecast for year 3" in page
        assert "-23% to +131% for year 5" in page
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "ภาพรวมทุกเทรนด์ | ปีที่ 1 ถึงปีที่ 5" not in th and "ทดสอบย้อนหลัง 8 ใน 10 ครั้ง ระดับยอดค้นหาจริงอยู่ในช่วง -21% ถึง +26%" in th
    ctx["growth"]["show_cumulative"] = True                                      # สวิตช์: เปิดกลับมาได้
    again = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert again.index('data-label="All Trends"') < again.index('data-label="All Trends CAGR"')


# ============================================================================
# 🆕 (2026-10-19) หน้าเดียวที่มีทั้ง CAGR (แท่ง) และ YoY (ตัวเลข) ต่อปี - แทนหน้า CAGR + หน้า YoY แยก
# ============================================================================
from report_data import combined_view, scatter_view  # noqa: E402


@pytest.fixture
def combined_table(monkeypatch):
    """🆕 (2026-10-19) หน้ารวมแบบตาราง (SHOW_COMBINED_PAGE) ถูกแทนด้วยหน้ากราฟจุด (SHOW_SCATTER_PAGE) เป็นค่าเริ่มต้นแล้ว
    เทสต์หน้าตารางจึงเปิดสวิตช์ตารางเอง (และปิดหน้ากราฟจุดให้เทสต์ไม่ปนกัน)"""
    monkeypatch.setattr(rd, "SHOW_COMBINED_PAGE", True)
    monkeypatch.setattr(rd, "SHOW_SCATTER_PAGE", False)


def _both_page(doc):
    """หน้าตาราง CAGR + YoY (label 'All Trends CAGR and YoY Table')"""
    page = doc[doc.index('data-label="All Trends CAGR and YoY Table"'):]
    return page[:page.index("</section>")]


def _yoy_cells(page, name):
    """[(" lo" | "", "ตัวเลข")] ของช่อง YoY ปีที่ 2-5 ในแถวของเทรนด์ `name`"""
    row = page[page.index(f'<td class="nm">{name}</td>'):]
    return re.findall(r'<td class="yo( lo)?">([^<]*)</td>', row[:row.index("</tr>")])


def _make_slow_trend(gp):
    """ให้ Stable Retinol (ในฟิกซ์เจอร์ไม่มีค่าที่คาด) มีค่าที่คาดที่ YoY ปีที่ 1 และ 5 ต่ำกว่าตลาด: +23% / +30% / +36% / +41% สะสม"""
    next(x for x in gp["all"] if x["name"] == "Stable Retinol")["expected_pct"] = [-0.3, 23.3, 30.1, 36.3, 41.0]


def test_combined_view_pairs_cagr_and_yoy_and_leaves_original(run_dir, combined_table):
    ctx = _with_growth_files(run_dir)
    gp = ctx["growth"]
    assert gp["cagr_view"] is None and gp["yoy_view"] is None                                  # หน้าแยกเดิมปิดเป็นค่าเริ่มต้น
    before = [list(x["expected_pct"]) for x in gp["all"]]
    gb = gp["combined_view"]
    assert [x["name"] for x in gb["all"]] == [x["name"] for x in gp["all"]]                    # ลำดับ/เทรนด์เดิม
    assert [list(x["expected_pct"]) for x in gp["all"]] == before                              # ไม่แก้ของเดิม
    assert gb["cagr_view"] is None and gb["yoy_view"] is None and gb["combined_view"] is None
    assert gb["market_pct"] == cagr_view(gp)["market_pct"] and gb["market_yoy"] == yoy_series(gp["market_pct"])
    src, by = {x["name"]: x for x in gp["all"]}, {x["name"]: x for x in gb["all"]}
    bc = by["Barrier Care"]
    assert bc["expected_pct"] == [cagr_pct(v, i + 1) for i, v in enumerate(src["Barrier Care"]["expected_pct"])]
    assert bc["yoy_pct"] == yoy_series(src["Barrier Care"]["expected_pct"])
    assert bc["expected_pct"][0] == bc["yoy_pct"][0] == src["Barrier Care"]["expected_pct"][0]  # ปีที่ 1 CAGR = YoY
    assert all(bc["bars"][i] for i in range(5)) and bc["scores"] == src["Barrier Care"]["scores"]   # แท่งตาม CAGR สีแท่งเดิม
    # YoY ตลาด (จากค่าทายรายคีย์เวิร์ด): +5 / +11.4 / +4.3 / +4.1 / +6.3% -> Barrier Care ไม่ต่ำกว่าตลาดทุกปี
    assert bc["yoy_up"] == [True] * 5
    assert by["Stable Retinol"]["yoy_pct"] == [None] * 5 and by["Stable Retinol"]["yoy_up"] == [None] * 5
    _make_slow_trend(gp)
    slow = {x["name"]: x for x in combined_view(gp)["all"]}["Stable Retinol"]
    assert slow["yoy_up"] == [False, True, True, True, False]                                   # ปีที่ 1 และ 5 ต่ำกว่า YoY ตลาด


def test_combined_page_renders_both_numbers_en_th(run_dir, combined_table):
    ctx = _with_growth_files(run_dir)
    _make_slow_trend(ctx["growth"])
    ctx = {**ctx, "growth": {**ctx["growth"], "combined_view": combined_view(ctx["growth"])}}
    en = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    page = _both_page(en)
    assert "All Trends | CAGR and YoY" in page and "compounded" in page and "YoY (change vs the year before)" in page
    assert "CAGR = YoY" in page and page.count('<th class="ctr">YoY</th>') == 4                 # ปีที่ 1 ช่องเดียว ปีที่ 2-5 มี CAGR | YoY
    assert ">+14%</span>" in page                                                               # Barrier Care ปีที่ 1 (CAGR = YoY)
    expected = [f"{round(v):+d}%" for v in yoy_series([13.6, 28.2, 40.0, 47.7, 60.2])[1:]]
    cells = _yoy_cells(page, "Barrier Care")
    assert [t for _, t in cells] == expected and expected[0] == "+13%" and not any(lo for lo, _ in cells)
    slow = _yoy_cells(page, "Stable Retinol")
    assert [lo for lo, _ in slow] == ["", "", "", " lo"]                                        # ปีที่ 5 ต่ำกว่า YoY ตลาด -> เทา
    assert [t for _, t in slow] == [f"{round(v):+d}%" for v in yoy_series([-0.3, 23.3, 30.1, 36.3, 41.0])[1:]]
    assert '<span class="w">⚠</span>' in page                                                  # Stable Retinol ค้นหาลดลงล่าสุด
    assert page.count('class="yo mk"') == 4 and 'class="yo mk">+11%</td>' in page              # แถวตลาดโดยรวม: YoY ปีที่ 2
    assert "ordered by expected growth to year 3" in page and "Dashed line = the market as a whole" in page
    assert "Detail pages cover trends above the dashed line in year 3" in page
    assert "8 times in 10 the actual search level was within -21% to +26% of the forecast for year 3" in page
    assert en.index('data-label="Top 5 Short vs Long"') < en.index('data-label="All Trends CAGR and YoY Table"') < en.index('data-label="Trend 1"')
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "ภาพรวมทุกเทรนด์ | CAGR และ YoY" in th and "ตัวเลข YoY: สีเข้ม" in th
    assert th.count('<section class="page') == en.count('<section class="page')


def test_combined_page_uses_display_names(run_dir, combined_table):
    from display_names import apply_display_names
    ctx = _with_growth_files(run_dir)
    apply_display_names(ctx, {"Social::Barrier Care": "Skin Barrier Recovery"})
    page = _both_page(render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x"))
    assert "Skin Barrier Recovery" in page and "Barrier Care" not in page


def test_combined_page_switch_off_and_missing_market_level(run_dir, combined_table, monkeypatch):
    ctx = _with_growth_files(run_dir)
    gp = {**ctx["growth"], "market_pct": None, "market_x": None}                                # ผล ⑥ รอบเก่าไม่มีระดับตลาด
    gb = combined_view(gp)
    assert gb["market_pct"] is None and gb["market_yoy"] is None
    assert all(u is None for x in gb["all"] for u in x["yoy_up"])
    page = _both_page(render_html({**ctx, "growth": {**gp, "combined_view": gb}}, BRAND, {}, "T", datetime(2026, 1, 1), "x"))
    assert 'class="yo mk"' not in page and '<tr class="cut"><td colspan="14">' in page         # แถวเส้นแบ่งแถวเดียวเต็มความกว้าง
    assert [t for _, t in _yoy_cells(page, "Stable Retinol")] == ["–"] * 4                      # ไม่มีค่าที่คาด
    monkeypatch.setattr(rd, "SHOW_COMBINED_PAGE", False)
    off = render_html(_with_growth_files(run_dir), BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert 'data-label="All Trends CAGR and YoY Table"' not in off and 'data-label="Top 5 Short vs Long"' in off


# ============================================================================
# 🆕 (2026-10-19) หน้ากราฟจุดกระจาย CAGR x YoY (แบบ D แทนหน้าตาราง) - ค่าเริ่มต้นของหน้า "All Trends CAGR and YoY"
# ============================================================================
from report_data import _axis, _place_labels  # noqa: E402


def _scatter_page(doc):
    page = doc[doc.index('data-label="All Trends CAGR and YoY"'):]
    return page[:page.index("</section>")]


def test_scatter_axis_covers_zero_and_negatives():
    lo, hi, ticks = _axis([3.0, 13.0])
    assert lo == 0 and hi >= 13 and ticks[0] == 0 and ticks[-1] == hi and len(ticks) <= 7
    lo, hi, ticks = _axis([-1.0, 12.0])
    assert lo <= -1 and 0 in ticks and ticks == sorted(ticks)
    assert _axis([])[:2] == (0, 1)                                   # ไม่มีค่าเลย -> แกนเริ่มต้นยังวาดได้


def test_scatter_labels_do_not_stack_on_close_points():
    pts = [{"rank": i, "cx": 100.0 + i, "cy": 100.0} for i in (1, 2, 3)]       # 3 จุดเกือบทับกัน
    _place_labels(pts, (40, 26, 436, 230))
    assert len({(p["lx"], p["ly"], p["anchor"]) for p in pts}) == 3
    edge = [{"rank": 12, "cx": 436.0, "cy": 100.0}]                            # ชิดขอบขวา -> เลขต้องไปทางซ้ายไม่ล้นกรอบ
    _place_labels(edge, (40, 26, 436, 230))
    assert edge[0]["anchor"] == "end"


def test_scatter_view_points_key_and_defaults(run_dir):
    gp = _with_growth_files(run_dir)["growth"]
    assert gp["combined_view"] is None and gp["scatter_view"] is not None                      # ตารางปิด กราฟจุดเปิดเป็นค่าเริ่มต้น
    sv = gp["scatter_view"]
    assert (sv["short"]["year"], sv["long"]["year"]) == (3, 5)                                   # ระยะสั้น = ปีที่ 3 (common/horizons.py)
    for side in ("short", "long"):
        h = sv[side]
        assert len(h["points"]) == 1 and h["points"][0]["rank"] == 1                          # Stable Retinol ไม่มีค่าที่คาด -> ไม่มีจุด
        p = h["points"][0]
        assert sv["x0"] <= p["cx"] <= sv["x1"] and sv["y0"] <= p["cy"] <= sv["y1"] and p["up"]
        assert h["market"]["x"] is not None and h["market"]["y"] is not None and "diag" not in h     # เส้นทแยง YoY = CAGR เอาออกแล้ว (2026-10-19)
        assert h["xticks"][0]["label"] == "0%" and len(h["yticks"]) >= 2
    keys = {k["name"]: k for k in sv["key"]}
    assert keys["Barrier Care"]["missing"] is False and keys["Stable Retinol"]["missing"] is True
    assert keys["Stable Retinol"]["decline"] and sv["any_decline"]


def test_scatter_page_renders_en_th_and_replaces_table(run_dir):
    ctx = _with_growth_files(run_dir)
    en = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    page = _scatter_page(en)
    assert 'data-label="All Trends CAGR and YoY Table"' not in en                                  # ตารางปิด
    assert "All Trends | CAGR and YoY" in page and page.count('<svg class="sc"') == 2 and page.count("<circle") == 2
    assert "Short term · Year 3 · Sep 2028 - Aug 2029" in page and "Long term · Year 5 · Sep 2030 - Aug 2031" in page
    assert "CAGR (average growth per year)" in page and "YoY (change vs the year before)" in page
    assert 'class="dg"' not in page and "Dotted line" not in page and "speeding up" not in page       # ไม่มีเส้นทแยง/คำอธิบายเส้น
    assert "<b>1</b>Barrier Care" in page and "Stable Retinol" in page and "⚠" in page and "(n/a)" in page
    assert 'data-ref="Trend 1"' in page                                                          # เลขหน้ารายละเอียดของเทรนด์ที่มีหน้า
    assert "8 times in 10 the actual search level was within -21% to +26% of the forecast for year 3" in page
    assert "year 2" not in page and "years 1-2" not in page
    assert en.index('data-label="Top 5 Short vs Long"') < en.index('data-label="All Trends CAGR and YoY"') < en.index('data-label="Trend 1"')
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    th_page = _scatter_page(th)
    assert "CAGR (เติบโตเฉลี่ยต่อปี)" in th_page and "ระยะสั้น · ปีที่ 3 · ก.ย. 2028 - ส.ค. 2029" in th_page and "ระยะยาว · ปีที่ 5" in th_page   # เดือนเป็นไทย (i18n.localize)
    assert th.count('<section class="page') == en.count('<section class="page')


def test_scatter_page_uses_display_names_and_switch_off(run_dir, monkeypatch):
    from display_names import apply_display_names
    ctx = _with_growth_files(run_dir)
    apply_display_names(ctx, {"Social::Barrier Care": "Skin Barrier Recovery"})
    page = _scatter_page(render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x"))
    assert "Skin Barrier Recovery" in page and "Barrier Care" not in page
    monkeypatch.setattr(rd, "SHOW_SCATTER_PAGE", False)
    off = render_html(_with_growth_files(run_dir), BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert 'data-label="All Trends CAGR and YoY"' not in off and 'data-label="Top 5 Short vs Long"' in off


# 🆕 (2026-10-28) สินค้าที่ใกล้เทรนด์ที่สุด 5 ชิ้นของทั้งร้านอยู่ในหมวดหลักน้อยกว่า 2 ชิ้น = หน้าสินค้าบอกว่าไม่มีสินค้าที่ใกล้พอ (common/match_quality.py)
from common.match_quality import category_agreement, no_close_product, result_agreement  # noqa: E402


def test_category_agreement_counts_top_five_groups_in_main_category():
    assert category_agreement(["Skin Care"] * 5, "Skin Care") == {"category": "Skin Care", "top_n": 5, "in_main": 5, "min_required": 2, "ok": True}
    assert category_agreement(["Skin Care", "Hair Care", "Skin Care", "Hair Care", "Hair Care", "Skin Care"], "Skin Care")["in_main"] == 2   # นับแค่ 5 อันดับแรก
    assert category_agreement(["Hair Care"] * 4 + ["Skin Care"], "Skin Care")["ok"] is False
    assert category_agreement(["Hair Care"] * 4 + ["Skin Care"], "Skin Care")["in_main"] == 1
    assert category_agreement(["Hair Care"] * 5, None) is None and category_agreement([], "Skin Care") is None     # ตัดสินไม่ได้ = ไม่ซ่อน
    assert category_agreement(["Skin Care"], "Skin Care")["min_required"] == 1                                    # สินค้าน้อยกว่า 5 ชิ้น
    r = {"main_category": {"category": "Skin Care"}, "top_matches": [{"group": "Hair Care"}] * 5}
    assert result_agreement(r)["in_main"] == 0 and no_close_product(r) and not no_close_product({"top_matches": r["top_matches"]})
    assert result_agreement({"main_category": "Skin Care", "top_matches": [{"category": "Skin Care"}] * 3})["ok"]   # รูปแบบเก่า: main_category เป็นข้อความ


def test_trend_without_close_product_gets_notice_page_in_both_languages(run_dir):
    _write(run_dir, "phase3_scale_validation_nvidia_result.json", {"n_products_total": 1000, "results": {
        "Social::Barrier Care": {"n_products_compared": 1000, "main_category": {"category": "Skin Care"},
                                 "top_matches": [_match_product(f"Shampoo {i}", "Hair Care", 0.3 - i / 100, i + 1) for i in range(5)]},
        "Paper::Stable Retinol": {"n_products_compared": 1000, "main_category": {"category": "Skin Care"},
                                  "top_matches": [_match_product(f"Serum {i}", "Skin Care", 0.35 - i / 100, i + 1) for i in range(5)]},
    }})
    ctx = _rendered_ctx(run_dir)
    assert [t["no_close_product"] for t in ctx["trends"]] == [True, False]
    assert ctx["trends"][0]["category_agreement"]["in_main"] == 0 and ctx["trends"][0]["l2"] is None
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    ev = html[html.index('data-label="Evidence 1"'):]
    ev = ev[:ev.index("</section>")]
    assert "No close product in the market" in ev and "none of the 5 closest products are" in ev and "Skin Care" in ev and "Shampoo" not in ev
    assert html.count("No close product in the market") == 1                               # เทรนด์ 2 ไม่ถูกกระทบ
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "ไม่มีสินค้าที่ใกล้เทรนด์พอในตลาด" in th and "ไม่มีสักชิ้นใน 5 ชิ้นที่ใกล้ที่สุด" in th


def test_brand_report_leaves_out_trends_without_close_product_and_says_so(run_dir):
    """🆕 (2026-10-28) ⑰: เทรนด์ที่ไม่มีสินค้าที่ใกล้พอไม่ถูกให้เกรด (ตัดออกจาก rows เลขอันดับคงตามรายงานเทรนด์) และหน้าสรุปบอกชื่อ"""
    ctx, coverage, catalog = _brand_fixture(run_dir, rank=20)
    ag = {"category": "Skin Care", "top_n": 5, "in_main": 0, "min_required": 2, "ok": False}
    marked = {**ctx, "trends": [ctx["trends"][0], {**ctx["trends"][1], "no_close_product": True, "category_agreement": ag}]}
    out = product_trends(marked)
    second = ctx["trends"][1]["name"]
    assert [t["name"] for t in out["trends"]] == [ctx["trends"][0]["name"]]
    assert out["no_close_trends"] == [{"rank": 2, "name": second, "display_name": second, "category": "Skin Care"}]
    b = build_brand_context(out, coverage, catalog, DEFAULT_CONFIG)
    assert len(b["rows"]) == 1 and b["n_checked"] == 1 and b["no_close_trends"] == out["no_close_trends"]
    html = render_brand_html(out, b, {**BRAND, "company_name": "S&J"}, {}, "T", datetime(2026, 9, 26))
    note = html[html.index('class="nc-note"'):]
    assert "Not graded (no close product in the market)" in note[:note.index("</div>")] and second in note[:note.index("</div>")]
    plain = build_brand_context(product_trends(ctx), coverage, catalog, DEFAULT_CONFIG)       # ไม่มีเทรนด์ที่ถูกธง = ไม่มีหมายเหตุ
    assert plain["no_close_trends"] == [] and 'class="nc-note"' not in render_brand_html(
        product_trends(ctx), plain, {**BRAND, "company_name": "S&J"}, {}, "T", datetime(2026, 9, 26))
    from brand_i18n import brand_strings
    assert "ไม่ได้ให้เกรด" in brand_strings("th")["no_close_note"].format(trends="x")


# 🆕 (2026-10-28) รอบสาย Search: หน้า "คนกำลังค้นหาอะไรมากขึ้น" 2 หน้าแทนหน้า persona (search_talk.py) และตารางแรงขับไม่มีคอลัมน์ persona
TALK = {"n_searches": 10701, "n_categories": 3, "places": ["TH", "WW"], "places_text": "Thailand and worldwide", "month": "2026-10",
        "n_link_check": 810, "n_trends_built": 15, "n_trends_shown": 2, "n_fed": 210, "fed_pct": 2.0, "n_no_fed": 1,
        "top_fed": [{"name": "Health", "fed": 81}, {"name": "Beauty & Fitness", "fed": 92}],
        "categories": [{"name": "Health", "n": 841, "th": 379, "ww": 384, "both": 78, "fed": 81},
                       {"name": "Beauty & Fitness", "n": 406, "th": 189, "ww": 172, "both": 45, "fed": 92},
                       {"name": "Finance", "n": 382, "th": 177, "ww": 164, "both": 41, "fed": 0}]}


def test_search_run_has_talk_pages_and_no_personas_page(run_dir):
    ctx = _rendered_ctx(run_dir)
    ctx["stepic"], ctx["personas"], ctx["talk"] = STEPIC, [], TALK
    link_trends(ctx, {}, llm_call=lambda s, u, max_tokens=0: json.dumps({"stepic": _links_answer()["stepic"]}), max_workers=1,
                log=lambda *_: None)
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert 'data-label="Search Talk"' in html and 'data-label="Search Talk Examples"' not in html and 'data-label="Personas"' not in html
    page = html[html.index('data-label="Search Talk"'):]
    page = page[:page.index("</section>")]
    assert "What People Are Searching For" in page and "10,701" in page and "(Thailand and worldwide)" in page
    assert "2.0% of all" in page and "810 of these searches" in page and "Health (81) and Beauty &amp; Fitness (92)" in page
    assert page.count('class="talk-row"') == 3 and page.count('class="fed"') == 2                  # แถบ "เป็นที่มาของเทรนด์" เฉพาะหมวดที่มี
    drivers = html[html.index('data-label="Trend Drivers"'):]
    drivers = drivers[:drivers.index("</section>")]
    assert "Trend Drivers | Macro Forces<" in drivers and "personas" not in drivers.lower() and 'class="lv2 per"' in drivers   # legend ยังมี; ไม่มีคอลัมน์ persona
    assert 'class="p"' not in drivers
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "คนกำลังค้นหาอะไรมากขึ้น" in th and "(ไทยและทั่วโลก)" in th and "เป็นที่มาของเทรนด์ในรายงาน" in th
    assert th.count('<section class="page') == html.count('<section class="page')


def _dive():
    """🆕 (2026-10-28) ส่วนที่ 2 เจาะรายหมวดของ Google (category_dive.py) - ข้อมูลทำมือ: 1 หมวดใหญ่ (หน้าเต็ม) + 1 หมวดเล็ก + 1 หมวดไม่มีหัวข้อโยง"""
    def card(key, **kw):
        return {"key": key, "n": 20, "places": ["TH", "WW"], "has_th": True, "where": "both", "breakout": 2, "breakout_share": .1,
                "searches": ["best sunscreen for kids"], "ids": [1], "link": None, "trends": [], "topic": "Searches for sunscreen",
                "topic_th": "คำค้นเรื่องครีมกันแดด", "shown": ["best sunscreen for kids"], **kw}

    linked = card("S", link={"path": 1, "cats": ["Sun Care"], "evidence": ["best sunscreen for kids"]},
                  trends=[{"rank": 1, "name": "Barrier Care", "display_name": "Barrier Care"}])

    def cat(name, full, n_linked=1):
        return {"name": name, "key": name, "n": 841, "th": 1, "ww": 1, "both": 1, "n_themes": 3, "n_linked": n_linked, "n_linked_searches": 20,
                "full": full, "linked": [linked] if n_linked else [], "n_more": 0, "others": [card("O", topic=None, shown=["realme c100"])] if n_linked else [],
                "trend_ranks": [1] if n_linked else []}
    return {"places": ["TH", "WW"], "places_text": "Thailand and worldwide", "month": "2026-10", "n_searches": 10701, "n_linked_searches": 810,
            "linked_pct": 7.6, "n_categories": 3, "n_topics": 90, "n_linked_topics": 2,
            "categories": [cat("Health", True), cat("News", False), cat("Finance", False, 0)], "none_linked": ["Finance"]}


def test_search_run_report_has_part_two_category_pages_and_a_linked_column_on_the_talk_page(run_dir):
    ctx = _rendered_ctx(run_dir)
    ctx["stepic"], ctx["personas"], ctx["dive"] = STEPIC, [], _dive()
    ctx["talk"] = {**TALK, "categories": [{**c, "n_linked": n} for c, n in zip(TALK["categories"], (16, 13, 0))]}
    link_trends(ctx, {}, llm_call=lambda s, u, max_tokens=0: json.dumps({"stepic": _links_answer()["stepic"]}), max_workers=1, log=lambda *_: None)
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    # ส่วนที่ 2: หน้าเต็มของหมวดใหญ่ + 1 หน้ารวมหมวดเล็ก (หมวดที่ไม่มีหัวข้อโยงไม่มีหน้า) อยู่หลังหน้าเทรนด์ก่อนภาคผนวก
    labels = re.findall(r'<section class="page[^"]*" data-label="([^"]+)"', html)
    i = labels.index("Category Health")
    assert labels[i:i + 3] == ["Category Health", "Categories News", "Methodology"] and "Category Finance" not in labels
    assert max(i for i, label in enumerate(labels) if label.startswith("Evidence ")) < labels.index("Category Health")
    part2 = html[html.index('data-label="Category Health"'):html.index('data-label="Methodology"')]
    assert "Searches for sunscreen" in part2 and "In this report: #1 Barrier Care" in part2 and "Link: Direct beauty → Sun Care" in part2
    assert "'best sunscreen for kids'" in part2 and "Topics linked to beauty" in part2
    talk = html[html.index('data-label="Search Talk"'):]
    talk = talk[:talk.index("</section>")]
    assert talk.count('class="talk-row lk4"') == 3 and talk.count('class="lk"') == 3 and "Part 2 starts on page" in talk
    assert 'data-ref="Category Health"' in talk and "In 1 categories no topic links to beauty products: Finance." in talk
    method = html[html.index('data-label="Methodology"'):]
    method = method[:method.index("</section>")]
    assert 'ap-grid dv-ext' in method and "Part 2: inside each Google category" in method
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "คำค้นเรื่องครีมกันแดด" in th and "Searches for sunscreen" not in th and "ส่วนที่ 2 เริ่มที่หน้า" in th and "ในรายงานหลัก: #1 Barrier Care" in th
    assert th.count('<section class="page') == html.count('<section class="page')
    without = dict(ctx, dive=None)                                                           # รอบที่ไม่มีส่วนเจาะรายหมวด (รอบเก่า / ไม่มีไฟล์ของ ①)
    plain = render_html(without, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert 'data-label="Category' not in plain and "ap-grid dv-ext" not in plain and "Part 2 starts on page" not in plain
    assert plain.count('<section class="page') == html.count('<section class="page') - 2


def test_search_run_merges_forces_heatmap_and_signals_into_one_page_when_at_most_three_forces_have_data(run_dir):
    """🆕 (2026-10-28) รอบสาย Search: STEPIC + Trend Drivers + Signals 3 หน้าว่างเกินไป (คำค้นยืนยันแรงขับได้น้อย) - รวมเป็นหน้า "Macro Forces" หน้าเดียว"""
    def build(with_data):
        ctx = _rendered_ctx(run_dir)
        ctx["meta"]["search_stream"] = True
        ctx["personas"] = []
        ctx["stepic"] = [{**s, "no_data": s["dimension"] not in with_data} for s in STEPIC]
        ctx["signals"] = [{"dimensions": "SOCIETY + INDUSTRY", "signal": "Searches for hair styling show high expected growth.", "implication": ""}]
        link_trends(ctx, {}, llm_call=lambda s, u, max_tokens=0: json.dumps({"stepic": _links_answer()["stepic"]}), max_workers=1, log=lambda *_: None)
        return ctx

    few = build({"Society", "Industry", "Creativity"})
    html = render_html(few, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    labels = re.findall(r'<section class="page[^"]*" data-label="([^"]+)"', html)
    assert "Macro Forces" in labels and not {"STEPIC", "Trend Drivers", "Signals"} & set(labels)
    page = html[html.index('data-label="Macro Forces"'):]
    page = page[:page.index("</section>")]
    assert page.count('class="st-tile') == 3 and "No evidence in this run&#39;s searches for: Technology, Environment, Policy." in page
    assert page.count("<tr>") == len(few["trends"]) + 1 and "Searches for hair styling show high expected growth." in page   # แถวเทรนด์ + แถวรวม (แถวหัวตารางมี class)
    assert page.count('<th class="f">') == 3 and "Signals &amp; outlook" in page                  # heatmap เฉพาะแรงขับที่มีข้อมูล
    th = render_html(localize(few, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert th.count('<section class="page') == html.count('<section class="page') and "คำค้นรอบนี้ไม่มีหลักฐานเกี่ยวกับ" in th
    many = build({"Society", "Industry", "Creativity", "Technology"})                              # มีข้อมูล 4 ช่อง = ใช้ 3 หน้าเดิม
    old = render_html(many, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    old_labels = re.findall(r'<section class="page[^"]*" data-label="([^"]+)"', old)
    assert {"STEPIC", "Trend Drivers", "Signals"} <= set(old_labels) and "Macro Forces" not in old_labels
    assert len(old_labels) == len(labels) + 2


def test_pages_say_when_products_are_matched_to_a_beauty_need_an_ai_inferred(run_dir):
    """🆕 (2026-10-28) เทรนด์สาย Search จับคู่สินค้าด้วยความต้องการความงามที่ AI อนุมาน (beauty_need) - หน้าเทรนด์ติดป้ายว่าไม่ใช่สิ่งที่คนค้นหาโดยตรง"""
    ctx = _rendered_ctx(run_dir)
    ctx["meta"]["search_stream"] = True
    need = {"source": "ai_inferred", "product_keywords": ["sport sunscreen", "sweat-proof deodorant"], "key_benefits": "sweat resistance"}
    p = {"name": "Banana Boat Sport Sunscreen", "brand": "Banana Boat", "price_thb": 299, "image": None, "rank": 3}
    ctx["trends"][0].update(beauty_need=need, match_basis="need", no_close_product=False, l2={
        "n": 1200, "category": "Sun Care", "cuts": {"excellent": 1, "good": 5, "average": 20},
        "cols": [{"level": lv, "product": p} for lv in ("excellent", "good", "average", "below_average")], "take": {"close_pct": 4, "n_close": 50}})
    ctx["trends"][1].update(beauty_need=None, match_basis="evidence")
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    page1 = html[html.index('data-label="Trend 1"'):]
    page1 = page1[:page1.index("</section>")]
    assert 'class="bn"' in page1 and "Beauty need" in page1 and "sport sunscreen · sweat-proof deodorant" in page1
    assert "AI-inferred" not in page1 and "Not what people searched" not in page1                       # เจ้าของงานสั่งเอาป้าย "(AI อนุมาน)" และบรรทัดหมายเหตุออกจากกล่อง
    page2 = html[html.index('data-label="Evidence 1"'):]
    page2 = page2[:page2.index("</section>")]
    assert "inferred from this trend&#39;s searches (sport sunscreen, sweat-proof deodorant)" in page2
    other = html[html.index('data-label="Trend 2"'):]
    assert 'class="bn"' not in other[:other.index("</section>")]                                     # เทรนด์ที่จับคู่จากคำค้นอย่างเดียวไม่มีป้าย
    method = html[html.index('data-label="Methodology"'):]
    assert "starts from the beauty need an AI inferred" in method[:method.index("</section>")]
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "ความต้องการความงาม" in th and "อนุมานจากคำค้น และใช้จับคู่" not in th and "สินค้าถูกจับคู่กับความต้องการความงามที่ AI อนุมาน" in th
    ctx["trends"][0].update(beauty_need=None, match_basis="evidence")
    plain = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert 'class="bn"' not in plain and "starts from the beauty need an AI inferred" not in plain   # ไม่มีเทรนด์ที่ใช้ความต้องการ = ไม่มีป้ายและไม่มีประโยควิธีการ


def test_old_three_stream_runs_keep_the_personas_page_and_have_no_talk_pages(run_dir):
    ctx = _rendered_ctx(run_dir)
    ctx["stepic"], ctx["personas"] = STEPIC, PERSONAS
    assert not ctx.get("talk")
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert 'data-label="Personas"' in html and "The Curator" in html and 'data-label="Search Talk"' not in html
    assert "What People Are Searching For" not in html


def test_build_context_drops_personas_and_adds_talk_only_for_search_runs(run_dir):
    final = {"emerging_personas": [{"name": "P", "description": "d", "value_driver": "", "channel_preference": "",
                                    "evidence": ["q"]}], "mega_trend_name": "x"}
    _write(run_dir, "phase4_stepic_final_insight.json", final)
    old, _ = build_context(run_dir)
    assert [p["name"] for p in old["personas"]] == ["P"] and old["talk"] is None            # รอบ 3 สายเดิมยังมี persona
    work = run_dir / "search_stream_work" / "themes"
    work.mkdir(parents=True)
    (work / "Health.json").write_text(json.dumps({"themes": [{"name": "T", "ids": [1]}], "queries": [
        {"query_norm": "best sunscreen", "query": "best sunscreen", "geos": "TH"}]}), encoding="utf-8")
    from common.streams import SEARCH_STREAM, STREAM_FILES
    _write(run_dir, STREAM_FILES[SEARCH_STREAM], {"search_meta": {"places": ["TH", "WW"], "n_queries": 1, "n_categories": 1},
                                                  "trends": [], "documents": []})
    new, _ = build_context(run_dir)
    assert new["personas"] == [] and new["meta"]["search_stream"]
    assert new["talk"]["n_searches"] == 1 and new["talk"]["places_text"] == "Thailand and worldwide"
    assert new["talk"]["categories"][0]["name"] == "Health"


# 🆕 (2026-10-28) กล่อง "คนกำลังค้นหาอะไร" ในหน้าแรกของเทรนด์ (trend_talk.py): หัวข้อ 2 ภาษา + คำค้นจริง; ไม่มีผล LLM = ตัวอย่างคำค้นล้วน; รอบ 3 สายเดิมยังมีบรรทัดกลุ่มเป้าหมาย
def test_trend_page_shows_what_people_search_with_real_searches_in_both_languages(run_dir):
    ctx = _rendered_ctx(run_dir)
    ctx["trends"][0]["talk"] = {"n": 27, "categories": ["Beauty & Fitness", "Health"], "examples": ["a1", "a2"], "points": [
        {"topic": "2026 hairstyles", "topic_th": "ทรงผมปี 2026", "searches": ["ทรง ผม 2026", "สี ผม 2026"]},
        {"topic": "fixing frizz", "topic_th": "แก้ผมชี้ฟู", "searches": ["how to fix frizzy hair"]}]}
    ctx["trends"][1]["talk"] = {"n": None, "categories": [], "points": [], "examples": ["example search one", "example search two"]}
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    first = html[html.index('data-label="Trend 1"'):]
    first = first[:first.index("</section>")]
    assert "What people are searching" in first and "27 rising searches in Beauty &amp; Fitness, Health" in first
    assert "2026 hairstyles" in first and "<i>ทรง ผม 2026</i>" in first and "<i>how to fix frizzy hair</i>" in first
    assert 'class="tgt"' not in first                                             # แทนบรรทัดกลุ่มเป้าหมายที่ซ้ำกันทุกเทรนด์
    second = html[html.index('data-label="Trend 2"'):]
    second = second[:second.index("</section>")]
    assert "Example searches" in second and "<i>example search one</i>" in second and "rising searches in" not in second   # ไม่มีผล LLM = ตัวอย่างล้วน ไม่มีจำนวน
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "ทรงผมปี 2026" in th and "2026 hairstyles" not in th and "<i>ทรง ผม 2026</i>" in th and "คนกำลังค้นหาอะไร" in th
    assert "27 คำค้นที่กำลังขึ้นในหมวด Beauty &amp; Fitness, Health" in th
    assert th.count('<section class="page') == html.count('<section class="page')


def test_trend_page_without_talk_keeps_the_target_consumer_line(run_dir):
    ctx = _rendered_ctx(run_dir)
    ctx["trends"][0]["target"] = "Skin-care minded shoppers"
    assert "talk" not in ctx["trends"][0]
    html = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    first = html[html.index('data-label="Trend 1"'):]
    assert 'class="tgt"' in first[:first.index("</section>")] and "What people are searching" not in first[:first.index("</section>")]
