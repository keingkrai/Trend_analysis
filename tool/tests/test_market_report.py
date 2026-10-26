# -*- coding: utf-8 -*-
"""
Unit test ของ ⑲ Phase 5 (market_i18n / market_report_data / market_charts / build_market_report) - ข้อมูลปลอมทั้งหมด
สร้าง HTML จริงจากเทมเพลต แต่ไม่พิมพ์ PDF (ไม่ต้องเปิด Chromium) ไม่เรียก API

รัน: pytest main/tool/tests/test_market_report.py -v
"""
import re
import string
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase7_market_report"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase6_pdf_report"))

from build_market_report import JUDGEMENT, make_env, month_year, render  # noqa: E402
from market_charts import share_chart_svg  # noqa: E402
from market_i18n import OUTLET_LABELS, STRINGS, date_text  # noqa: E402
from market_report_data import COLUMN_PX, FACTOR_MIN_FINDINGS, Citations, build_context, plan_columns  # noqa: E402

TOTAL = "Beauty and Personal Care"
BRAND = {"company_name": "Test Co", "logo": None, "logo_for_dark_bg": False, "accent_color": "#E8611A"}


def _fields(text):
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def test_strings_same_keys_and_placeholders_in_both_languages():
    assert set(STRINGS["en"]) == set(STRINGS["th"])
    for k in STRINGS["en"]:
        assert _fields(STRINGS["en"][k]) == _fields(STRINGS["th"][k]), k
    assert set(OUTLET_LABELS["en"]) == set(OUTLET_LABELS["th"])


def test_strings_never_judge_brands_outside_method_page():
    for lang, L in STRINGS.items():
        for k, text in L.items():
            if not k.startswith("m_"):          # หน้าวิธีการอธิบายกติกา "ห้ามบอกว่าชนะ/แพ้" เอง
                assert not JUDGEMENT[lang].search(text), (lang, k)


def test_date_and_month_text():
    assert date_text(date(2026, 10, 12), "en") == "12 Oct 2026"
    assert date_text(date(2026, 10, 12), "th") == "12 ต.ค. 2026"          # ค.ศ. ทั้ง 2 ฉบับ
    assert month_year([2021, 1], "en") == "Jan 2021" and month_year([2026, 8], "th") == "ส.ค. 2026"


def test_citations_number_by_first_use():
    ev = [{"id": "q1", "results": [{"rid": f"q1-r0{i}", "title": f"t{i}", "domain": "a.th", "link": f"https://a.th/{i}",
                                    "page_date": "2024-01-01", "kind": "news"} for i in (1, 2, 3)]}]
    c = Citations(ev)
    assert c.cite(["q1-r03", "q1-r01"]) == [1, 2]
    assert c.cite(["q1-r01", "q1-r09"]) == [2]                          # rid ที่ไม่มีจริงไม่ได้เลข
    assert [s["n"] for s in c.sources("en")] == [1, 2] and c.sources("th")[0]["kind"] == "ข่าว"


# ---------------------------------------------------------------------------
# ข้อมูลปลอมของทั้งรายงาน
# ---------------------------------------------------------------------------

def _size(v19, v25, share):
    return {"value": {"2019": v19, "2025": v25, "2030": v25 * 1.3}, "cagr_hist": 4.4, "cagr_forecast": 5.3,
            "share_of_total": share}


def _inputs():
    facts = {
        "meta": {"base_year": 2019, "last_year": 2025, "forecast_year": 2030, "edition": 2026,
                 "fda": {"first": [2021, 1], "complete_through": [2026, 8], "rows": 1000}},
        "market": {TOTAL: _size(200000, 269685, 100.0), "Skin Care": _size(80000, 106295, 39.4),
                   "Hair Care": _size(30000, 47270, 17.5)},
        "categories": {
            TOTAL: {"channel": {"ecommerce": {"2019": 2.5, "2025": 13.7},
                                "leaves": [{"outlet": "Retail E-Commerce", "share_base": 2.5, "share_last": 13.7, "change_pp": 11.2},
                                           {"outlet": "Department Stores", "share_base": 11.8, "share_last": 8.8, "change_pp": -3.0},
                                           {"outlet": "Other Non-Grocery Retailers", "share_base": 3.0, "share_last": 0.6, "change_pp": -2.4}]},
                    "brands": {"others": {"2019": 29.7, "2025": 37.6}, "movers": []},
                    "fda": {"import_share": {"2021": 36.8, "2025": 51.3}, "by_year": {"2021": 79932, "2025": 90249}}},
            "Skin Care": {"brands": {"movers": [{"brand": "Zeta", "series": {"2019": 1.0, "2025": 4.0}},
                                                {"brand": "Alpha", "series": {"2019": 3.0, "2025": 1.0}}]}},
            "Hair Care": {"brands": {"movers": []}},
        },
    }
    questions = [
        {"id": "q01", "level": "market", "topic": "Retail E-Commerce", "brand": None, "categories": [TOTAL],
         "question_en": "Q online?", "question_th": "คำถามออนไลน์", "facts": {}},
        {"id": "q02", "level": "market", "topic": "Direct Selling", "brand": None, "categories": ["Skin Care"],
         "question_en": "Q direct?", "question_th": "คำถามขายตรง", "facts": {}},
        {"id": "q03", "level": "brand", "topic": "Zeta", "brand": "Zeta", "categories": ["Skin Care"],
         "question_en": "Q Zeta?", "question_th": "คำถาม Zeta",
         "facts": {"owner": "Z Co", "tier": "premium", "fda_by_year": {"2021": 3, "2025": 9},
                   "by_category": [{"category": "Skin Care", "share_base": 1.0, "share_last": 4.0, "change_pp": 3.0}]}},
        {"id": "q04", "level": "brand", "topic": "Alpha", "brand": "Alpha", "categories": ["Skin Care"],
         "question_en": "Q Alpha?", "question_th": "คำถาม Alpha",
         "facts": {"owner": "A Co", "tier": "mass", "fda_by_year": None,
                   "by_category": [{"category": "Skin Care", "share_base": 3.0, "share_last": 1.0, "change_pp": -2.0,
                                    "absorbed": ["Alpha Old"]}]}},
    ]

    def fnd(factor, rel, rids, en="News reports say x.", th="ข่าวรายงานว่า x"):
        return {"factor": factor, "relevance": rel, "statement_en": en, "statement_th": th, "evidence": rids, "quote": "q"}
    results = {
        "q01": {"findings": [fnd("consumer_shift", "direct", ["q01-r01"])], "passages": {"q01-r01": {"source": "a.th"}}},
        "q02": {"findings": [], "passages": {}},
        "q03": {"findings": [fnd("marketing", "background", ["q03-r01"]), fnd("marketing", "direct", ["q03-r02", "q03-r01"]),
                             fnd("other", "direct", ["q03-r02"]), fnd("reputation", "background", ["q03-r01"])],
                "passages": {"q03-r01": {"source": "b.th"}, "q03-r02": {"source": "c.th"}}},
        "q04": {"findings": [fnd("channel_shift", "direct", ["q04-r01"])], "passages": {"q04-r01": {"source": "d.th"}}},
    }
    findings = {"meta": {"status": {"ok": 3, "no_evidence": 1, "failed": 0, "not_run": 0}}, "results": results,
                "by_factor": {"marketing": {"brands": ["Zeta"], "n_sources": 2}, "channel_shift": {"brands": ["Alpha"], "n_sources": 1},
                              "consumer_shift": {"brands": [], "n_sources": 1}}}
    evidence = [{"id": q, "results": [{"rid": rid, "title": rid, "domain": "x.th", "link": f"https://x.th/{rid}",
                                       "page_date": "2024-05-01", "kind": "web"} for rid in sorted(r["passages"])]}
                for q, r in results.items()]
    return {"facts": facts, "questions": questions, "findings": findings, "evidence": evidence}


@pytest.fixture(params=["en", "th"])
def ctx(request):
    return build_context(_inputs(), request.param, "Test Co", date(2026, 10, 12))


def test_factor_pages_data_first_and_other_hidden(ctx):
    ids = [p["id"] for p in ctx["factor_pages"]]
    assert ids[:3] == ["channel_shift", "concentration", "launch_activity"]   # ปัจจัยข้อมูลก่อน (premium ไม่มีข้อมูล)
    assert "other" not in ids and set(ids[3:]) == {"marketing", "consumer_shift", "reputation"}
    channel = ctx["factor_pages"][0]
    assert len(channel["data_lines"]) == 2                                   # "Other ..." ไม่แสดง


def test_findings_direct_first_and_cited(ctx):
    zeta = next(b for b in ctx["brand_pages"] if b["brand"] == "Zeta")
    assert [f["relevance"] for f in zeta["findings"]] == ["direct", "direct", "background"]   # 3 จาก 4 ข้อ
    assert zeta["shown_of"] == STRINGS[ctx["lang"]]["shown_of"].format(k=3, n=4)
    assert all(f["cites"] for f in zeta["findings"])
    numbers = sorted({n for p in ctx["factor_pages"] + ctx["brand_pages"] for f in p["findings"] for n in f["cites"]})
    assert numbers == [s["n"] for s in ctx["sources"]]                        # ทุกเลขที่อ้างมีในหน้าแหล่งข้อมูล


def test_brand_pages_and_missing(ctx):
    assert [b["brand"] for b in ctx["brand_pages"]] == ["Zeta", "Alpha"]      # ลำดับคำถาม ไม่ใช่ตามการเปลี่ยนแปลง
    alpha = ctx["brand_pages"][1]
    assert alpha["absorbed"] and "Alpha Old" in alpha["absorbed"] and alpha["fda"] == ""
    assert [m["subject"] for m in ctx["missing"]] == [OUTLET_LABELS[ctx["lang"]]["Direct Selling"]]


def test_overview_rows_follow_factor_pages_and_list_brands_a_to_z(ctx):
    L = STRINGS[ctx["lang"]]
    assert [r["label"] for r in ctx["overview"]] == [p["label"] for p in ctx["factor_pages"]]
    assert all(r["brands"] == sorted(r["brands"]) for r in ctx["overview"])
    tags = [r["tag"] for r in ctx["overview"]]
    assert tags[:3] == [L["data_tag"]] * 3 and set(tags[3:]) == {L["web_tag"]}
    online = ctx["overview"][0]["seen"][0]
    assert "2.5%" in online and "13.7%" in online                            # ตัวเลขจากข้อมูล ไม่ใช่จาก LLM
    rep = next(r for r in ctx["overview"] if r["label"] == "Trust and reputation" or r["label"] == "ความเชื่อมั่นและชื่อเสียง")
    assert rep["seen"] == [L["only_background"]]                             # ข้อพื้นหลังไม่ขึ้นหน้าภาพรวม


def test_report_is_compact(ctx):
    html = render(ctx, BRAND, {"Zeta": None, "Alpha": None}, datetime(2026, 10, 12), make_env())
    labels = [s[0] for s in _sections(html)]
    # 2 คอลัมน์ต่อหน้า (1 คอลัมน์ = 1 ปัจจัยหรือหลายปัจจัยที่มีเนื้อหาน้อย) / 3 แบรนด์ต่อหน้า / "ยังไม่พบคำอธิบาย" อยู่ในหน้าวิธีการ
    assert sum(lbl.startswith("Factors") for lbl in labels) == -(-len(ctx["factor_columns"]) // 2)
    assert len(ctx["factor_columns"]) <= len(ctx["factor_pages"])
    assert sum(lbl.startswith("Brands") for lbl in labels) == -(-len(ctx["brand_pages"]) // 3)
    assert not any("explanation" in lbl.lower() for lbl in labels)


def test_factor_columns_hold_every_factor_once_in_order(ctx):
    placed = [p["id"] for col in ctx["factor_columns"] for p in col]
    assert placed == [p["id"] for p in ctx["factor_pages"]]                   # ครบ ลำดับเดิม ไม่ซ้ำ
    html = render(ctx, BRAND, {"Zeta": None, "Alpha": None}, datetime(2026, 10, 12), make_env())
    assert html.count('class="fblock"') == len(ctx["factor_pages"])


def test_factor_without_findings_says_so_and_sales_factor_keeps_its_numbers(ctx):
    L = STRINGS[ctx["lang"]]
    html = render(ctx, BRAND, {"Zeta": None, "Alpha": None}, datetime(2026, 10, 12), make_env())
    launch = next(p for p in ctx["factor_pages"] if p["id"] == "launch_activity")
    assert launch["data_lines"] and not launch["findings"]
    assert L["no_findings_line"] in html                                         # ข้อความที่ถูกต้องสำหรับปัจจัยมีตัวเลขแต่ไม่มีข่าว
    assert html.count(L["no_data_line"]) == 0                                    # ไม่มีกล่อง "ไม่มีตัววัด..." ซ้ำทุกปัจจัยข่าว


# ---------------------------------------------------------------------------
# plan_columns: จัดปัจจัยลงคอลัมน์ตามความสูงเนื้อหา
# ---------------------------------------------------------------------------

def _block(fixed, costs, direct=None):
    k = min(FACTOR_MIN_FINDINGS, len(costs))
    return {"fixed": fixed, "costs": list(costs), "min_k": k, "grow": len(costs) if direct is None else direct}


def _column_height(blocks, col):
    return sum(blocks[i]["fixed"] + sum(blocks[i]["costs"][:k]) for i, k in col) + 16 * (len(col) - 1)


def test_plan_columns_sparse_blocks_share_a_column_and_nothing_overflows():
    blocks = [_block(100, [50] * 8), _block(100, [50]), _block(100, []), _block(100, [50] * 8)]
    plan = plan_columns(blocks)
    assert [[i for i, _ in col] for col in plan] == [[0, 1], [2, 3]]            # ลำดับเดิม ปัจจัยเบาอยู่ร่วมคอลัมน์
    assert all(_column_height(blocks, col) <= COLUMN_PX for col in plan)
    assert plan[0][0][1] > FACTOR_MIN_FINDINGS                                  # ที่เหลือถูกเติมด้วยข้อเพิ่ม
    assert len(plan) % 2 == 0


def test_plan_columns_fills_direct_before_background_and_shares_evenly():
    big = _block(300, [50] * 4)                                                 # กินคอลัมน์เกือบทั้งหมด จับคู่กับใครไม่ได้
    both_direct = [big, _block(60, [30] * 6), _block(60, [30] * 6)]
    plan = plan_columns(both_direct)
    ks = dict(plan[1])
    assert set(ks) == {1, 2} and abs(ks[1] - ks[2]) <= 1                         # เติมให้ปัจจัยที่แสดงน้อยกว่าก่อน
    assert _column_height(both_direct, plan[1]) <= COLUMN_PX and ks[1] + ks[2] == 10   # จนเต็มคอลัมน์
    one_background = [big, _block(60, [30] * 6, direct=1), _block(60, [30] * 6)]
    plan = plan_columns(one_background)
    ks = dict(plan[1])
    assert all(_column_height(one_background, col) <= COLUMN_PX for col in plan)
    assert ks[2] == 6                                                           # ข้อ direct ของอีกปัจจัยครบก่อน
    assert FACTOR_MIN_FINDINGS <= ks[1] < 6                                     # แล้วจึงเติมข้อพื้นหลังด้วยที่ที่เหลือ


def test_plan_columns_background_only_factor_is_shown_fully_when_there_is_room():
    blocks = [_block(80, [50, 50, 50], direct=0)]
    assert plan_columns(blocks) == [[(0, 3)]]                                   # ไม่มีข้อ direct แต่คอลัมน์ว่าง -> แสดงครบ


def test_plan_columns_rounds_to_whole_pages_and_handles_empty():
    assert plan_columns([]) == []
    big = [_block(100, [60] * 4) for _ in range(5)]                             # แต่ละปัจจัยกินเกือบทั้งคอลัมน์ -> 5 คอลัมน์
    plan = plan_columns(big)
    assert len(plan) == 6 or len(plan) == 5                                     # ปัดเป็นคู่ถ้ามีปัจจัยพอแยก
    assert [i for col in plan for i, _ in col] == [0, 1, 2, 3, 4]


def _sections(html):
    return re.findall(r'(?s)<section class="page[^"]*" data-label="([^"]+)">(.*?)</section>', html)


def test_rendered_html_has_euromonitor_citation_last_and_no_judgement(ctx):
    html = render(ctx, BRAND, {"Zeta": None, "Alpha": None}, datetime(2026, 10, 12), make_env())
    sections = _sections(html)
    assert sections[0][0] == "Cover" and sections[-1][0] == "Data sources and copyright"
    assert "Euromonitor International Ltd 2026" in sections[-1][1]
    for label, body in sections:
        text = re.sub(r"<[^>]+>", " ", body)
        assert "{" not in text and "None" not in text, label              # ตัวแทนค่าที่ไม่ถูกแทน / ค่าว่าง
        # หน้าวิธีการอธิบายกติกา "ห้ามบอกว่าชนะ/แพ้" เอง / หน้าแหล่งข้อมูลเป็นหัวข้อข่าวของคนอื่น
        if label != "Method" and not label.startswith("Sources"):
            assert not JUDGEMENT[ctx["lang"]].search(text), label


def test_share_chart():
    svg = share_chart_svg({"2016": 1.0, "2019": 2.0, "2025": None, "2024": 3.0}, 2019, 2025)
    assert svg.startswith("<svg") and "2.0%" in svg
    assert share_chart_svg({"2019": 1.0}, 2019, 2025) is None
