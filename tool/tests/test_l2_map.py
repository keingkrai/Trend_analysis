# -*- coding: utf-8 -*-
"""
เทสแผนที่ตลาดระดับหมวด L2 (🆕 2026-10-21): ⑫ l2_market_map.py (เขียน/อ่านไฟล์) และฝั่งรายงาน l2_map.py (ช่อง ความใกล้เทรนด์ x ยอดขาย, สินค้าของแบรนด์)
ไม่เรียก API - ใช้ข้อมูลปลอมขนาดเล็ก

รัน: pytest main/tool/tests/test_l2_map.py -v
"""
import sys
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
_TOOL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TOOL / "phase3_supply_layer"))
sys.path.insert(0, str(_TOOL / "phase6_pdf_report"))

import pandas as pd  # noqa: E402

import l2_map  # noqa: E402
from l2_market_map import COLUMNS, build_table, read_map, trend_entry, write_map  # noqa: E402

CFG = {"fit_top_pct": {"excellent": 1, "good": 5, "average": 20}, "sales": {"strong_top_pct": 20, "slow_bottom_pct": 25}}


def _catalog(n=40):
    """หมวด Skin Care n ชิ้น (ยอดขายเพิ่มตามเลขชิ้น) + 3 ชิ้นหมวด Hair Care"""
    rows = [{"brand": "Mine" if i % 10 == 0 else "Other", "product_name": f"skin {i}", "sale_price_thb": f"{100 + i},0.00".replace(",0.00", ".00"),
             "sold_count": float(i * 10), "stock": 5.0, "review_count": float(i)} for i in range(n)]
    rows += [{"brand": "Other", "product_name": f"hair {i}", "sale_price_thb": "50.00", "sold_count": 1.0, "stock": 5.0, "review_count": 1.0}
             for i in range(3)]
    df = pd.DataFrame(rows)
    groups = pd.Series(["Skin Care"] * n + ["Hair Care"] * 3, index=df.index)
    return df, groups


def _scored(df, groups):
    """ความใกล้ = กลับลำดับ: ชิ้นที่ 0 ใกล้เทรนด์ที่สุด (ยอดขายต่ำสุด) - เรียงมากไปน้อยตามความใกล้"""
    return [{"_idx": i, "group": groups[i], "similarity": 1 - i / 100} for i in df.index]


def test_build_table_keeps_only_wanted_groups_and_orders_by_similarity():
    df, groups = _catalog()
    table, index = build_table(df, groups, None, {"Skin Care"})
    assert len(table) == 40 and all(r[2] == "Skin Care" for r in table)
    entry = trend_entry(_scored(df, groups), "Skin Care", index, "Paper", "T")
    assert entry["order"] == list(range(40))                    # สินค้าหมวดอื่นไม่เข้า order
    assert len(table[0]) == len(COLUMNS)


def test_map_file_roundtrip_and_category_products(tmp_path):
    df, groups = _catalog()
    table, index = build_table(df, groups, None, {"Skin Care"})
    write_map(tmp_path / "m.json.gz", len(df), table, {"Paper::T": trend_entry(_scored(df, groups), "Skin Care", index, "Paper", "T")})
    data = read_map(tmp_path / "m.json.gz")
    cat, products = l2_map.category_products(data, "Paper::T")
    assert cat == "Skin Care" and [p["rank"] for p in products] == list(range(1, 41))
    assert products[0]["product_name"] == "skin 0" and products[0]["sales"]["sold"] == 0
    assert l2_map.category_products(data, "Paper::missing", "T")[0] == "Skin Care"       # หาด้วยชื่อเทรนด์ได้
    assert l2_map.category_products(data, "Paper::missing") == (None, [])
    assert l2_map.category_products(None, "x") == (None, [])


def test_sales_are_compared_inside_the_whole_category_not_by_price_tier():
    df, groups = _catalog()
    table, _ = build_table(df, groups, None, {"Skin Care"})
    pcts = [r[6] for r in table]
    assert pcts == sorted(pcts) and pcts[-1] > 0.9 and pcts[0] < 0.1    # ยอดขายเพิ่มตามเลขชิ้น -> เปอร์เซ็นไทล์เพิ่มตาม


def _products(n=200):
    """สินค้า n ชิ้นเรียงตามความใกล้ ยอดขาย: ชิ้นที่ 1 ขายช้า, ชิ้นที่ 2 ขายดี, ที่เหลือปานกลาง"""
    out = []
    for r in range(1, n + 1):
        pct = 0.1 if r == 1 else 0.95 if r == 2 else 0.5
        out.append({"brand": "Mine" if r in (1, 2, 150) else "Other", "product_name": f"p{r}", "sale_price_thb": 100.0, "size": None,
                    "unit_label": None, "rank": r,
                    "sales": {"pct": pct, "basis": "sales", "soldout": False, "zero": False, "sold": 10, "value": None, "reviews": None}})
    return out


def test_l2_grid_counts_every_product_once_and_shows_closest_in_each_cell():
    grid = l2_map.l2_grid(_products(), CFG)
    assert grid["n"] == 200 and sum(c["n"] for c in grid["cols"]) == 200 and sum(r["n"] for r in grid["rows"]) == 200
    assert sum(c["n"] for c in grid["cells"].values()) == 200
    assert grid["cuts"] == CFG["fit_top_pct"]
    slow_exc, strong_exc = grid["cells"]["slow|excellent"], grid["cells"]["strong|excellent"]
    assert slow_exc["n"] == 1 and slow_exc["product"]["product_name"] == "p1" and slow_exc["product"]["level"] == "good"   # ขายช้าลดเกรด 1 ขั้น
    assert strong_exc["n"] == 1 and strong_exc["product"]["product_name"] == "p2" and strong_exc["product"]["level"] == "excellent"
    assert grid["cells"]["steady|excellent"]["n"] == 0 and grid["cells"]["steady|excellent"]["product"] is None   # 200 ชิ้น: top 1% = 2 อันดับ
    assert grid["cells"]["steady|good"]["product"]["product_name"] == "p3"                                        # ชิ้นที่ใกล้ที่สุดในช่อง
    below = grid["cells"]["steady|below_average"]["product"]    # 🆕 ทุกช่อง 4 ระดับ x 3 แถวมีสินค้าตัวแทน (หน้ารายงานไม่แสดงจำนวนต่อช่อง)
    assert below["product_name"] == "p41" and below["level"] == "below_average"   # ชิ้นแรกที่เกิน top 20% ของ 200 ชิ้น = อันดับ 41
    assert grid["cells"]["unknown|good"]["product"] is None                       # แถวไม่มีข้อมูลยอดขายไม่มีตัวแทน (ไม่แสดง)


def test_l2_grid_takeaway_compares_close_matches_with_the_whole_category():
    grid = l2_map.l2_grid(_products(), CFG)
    take = grid["take"]
    assert take["close_pct"] == 5 and take["n_close"] == sum(c["n"] for c in grid["cols"][:2]) == 10      # ranks 1-10 of 200
    assert take["strong_close"] == 10 and take["slow_close"] == 10      # p2 ขายดี, p1 ขายช้า จาก 10 ชิ้นที่ใกล้ที่สุด
    assert take["strong_all"] == 0 and take["slow_all"] == 0            # ทั้งหมวด 1/200 ปัดเป็น 0%


def test_brand_tier_uses_category_rank_and_skips_brands_without_products():
    tier = l2_map.brand_tier(_products(), "Mine")
    assert tier["n_total"] == 200 and tier["n_brand"] == 3
    assert [p["rank_in_tier"] for p in tier["brand_products"]] == [1, 2, 150]
    assert l2_map.brand_tier(_products(), "Nobody") is None


def test_fit_sales_map_places_brand_products_by_category_rank_and_sales():
    from brand_category_data import _fit_sales_map
    from brand_data import best_in_tier

    class _Index:
        def pair(self, brand, name):
            return {}

    tier = l2_map.brand_tier(_products(), "Mine")
    m = _fit_sales_map(tier, _Index(), "Mine", CFG["fit_top_pct"], CFG["sales"], best_in_tier(tier, CFG["fit_top_pct"], CFG["sales"]))
    assert len(m["dots"]) == 3 and sum(m["cells"].values()) == 3
    assert m["cells"]["strong|excellent"] == 1 and m["cells"]["slow|excellent"] == 1 and m["cells"]["steady|below_average"] == 1
    assert {c["kind"] for c in m["callouts"]} <= {"A", "B", "C"} and m["zones"]["close_strong"] == 1 and m["zones"]["close_lag"] == 1


# ---------------------------------------------------------------------------
# 🆕 (2026-10-21) เกรดทั้ง ⑰ + Excel ของ ⑬ เทียบในหมวด L2 อย่างเดียว: category_fit (หมวด x ช่วงราคา) -> หมวดเดียว
# ---------------------------------------------------------------------------

def _fit_two_tiers():
    """category_fit ของ ⑬ แบบเดิม: 2 ช่วงราคา ชิ้นของแบรนด์ 'p1' (ช่วงต่ำ) กับ 'p150' (ช่วงสูง) พร้อมเหตุผล/ความใกล้/อันดับตลาด"""
    p1 = {"brand": "Mine", "product_name": "p1", "sale_price_thb": 100.0, "similarity": 0.9, "rank_in_tier": 1, "rank_in_market": 1, "match_reason": "why p1",
          "sales": {"pct": 0.5, "basis": "sales", "soldout": False, "zero": False, "sold": 5, "value": 500.0, "reviews": None}}
    p150 = {**p1, "product_name": "p150", "similarity": 0.3, "rank_in_tier": 7, "rank_in_market": 150, "match_reason": ""}
    top = [{"brand": "Other", "product_name": "p3", "sale_price_thb": 100.0, "similarity": 0.8, "rank_in_tier": 1, "rank_in_market": 3, "sales": None}]
    return {"n_market": 999, "main_category": "Skin Care", "tier_basis": "unit_price", "categories": [{
        "category": "Skin Care", "n_total": 200, "n_brand": 2,
        "tiers": [{"label": "low", "n_total": 100, "n_brand": 1, "top": top, "brand_products": [p1], "brand_best": p1},
                  {"label": "high", "n_total": 100, "n_brand": 1, "top": [], "brand_products": [p150], "brand_best": p150}],
        "brand_best": {**p1, "n_tier": 100, "tier": "low", "price_from": 1, "price_to": 9}}]}


def test_l2_category_fit_has_one_tier_for_the_whole_category_with_category_ranks():
    fit = l2_map.l2_category_fit(_fit_two_tiers(), _products(), "Mine")
    assert fit["group_basis"] == "l2" and fit["tier_basis"] == "unit_price" and fit["main_category"] == "Skin Care"
    (cat,) = fit["categories"]
    (tier,) = cat["tiers"]
    assert tier["label"] == "all" and tier["n_total"] == 200 and tier["n_brand"] == 3
    assert [p["rank_in_tier"] for p in tier["brand_products"]] == [1, 2, 150]            # อันดับในหมวด ไม่ใช่ในช่วงราคา
    assert tier["top"][0]["product_name"] == "p1" and len(tier["top"]) == 5
    assert cat["brand_best"]["rank_in_tier"] == 1 and cat["brand_best"]["n_tier"] == 200 and cat["brand_best"]["tier"] == "all"


def test_l2_category_fit_borrows_similarity_and_reason_from_the_original_items_and_new_sales():
    fit = l2_map.l2_category_fit(_fit_two_tiers(), _products(), "Mine")
    p1 = fit["categories"][0]["tiers"][0]["brand_products"][0]
    assert p1["similarity"] == 0.9 and p1["match_reason"] == "why p1" and p1["rank_in_market"] == 1      # ยืมจาก category_fit เดิม
    assert p1["sales"]["pct"] == 0.1 and p1["sales"]["value"] is None                                       # ยอดขายเทียบทั้งหมวดจากแผนที่
    p2 = fit["categories"][0]["tiers"][0]["brand_products"][1]                                              # ไม่มีในรายการเดิม: ยังได้ชื่อ/ราคา
    assert p2["product_name"] == "p2" and p2["sale_price_thb"] == 100.0 and p2["similarity"] is None
    reasons = {"p2": "why p2"}
    fit2 = l2_map.l2_category_fit(_fit_two_tiers(), _products(), "Mine", reasons)
    assert fit2["categories"][0]["tiers"][0]["brand_products"][1]["match_reason"] == "why p2"             # l2_reasons ของ ⑬ --l2-reasons-only


def test_existing_grade_functions_work_on_the_l2_fit_and_grade_in_the_category():
    from brand_data import best_in_category

    fit = l2_map.l2_category_fit(_fit_two_tiers(), _products(), "Mine")
    tier, tb = best_in_category(fit["categories"][0], CFG["fit_top_pct"], CFG["sales"])
    assert tier["label"] == "all" and tb["raw"]["product_name"] == "p2"       # p2 = อันดับ 2 ในหมวด ขายดี -> Excellent ; p1 ขายช้าถูกลดเป็น Good
    assert tb["level"] == "excellent" and tb["state"] == "strong"


def test_top_match_without_strong_sales_is_good_not_excellent_in_the_l2_grid():
    # 🆕 (2026-10-21) Excellent = top 1% ของหมวด และขายดี: ใกล้เทรนด์ top 1% ที่ขายปานกลางได้ Good ; ช่องสีของ ⑯ ใช้กฎเดียวกัน
    from brand_data import adjust_level

    assert adjust_level("excellent", "steady") == "good" and adjust_level("excellent", "unknown") == "good"
    assert adjust_level("excellent", "strong") == "excellent" and adjust_level("good", "strong") == "good"
    tpl = (Path(__file__).resolve().parent.parent / "phase6_pdf_report" / "templates" / "report.html.j2").read_text(encoding="utf-8")
    assert '"steady": {"excellent": "good"' in tpl


def test_l2_coverage_converts_matching_trends_and_skips_others(tmp_path):
    df, groups = _catalog(40)
    table, index = build_table(df, groups, None, {"Skin Care"})
    write_map(tmp_path / "m.json.gz", len(df), table, {"Paper::T": trend_entry(_scored(df, groups), "Skin Care", index, "Paper", "T")})
    data = read_map(tmp_path / "m.json.gz")
    cov = {"brand": "Mine", "coverage": {"Paper::T": {"trend_name": "T", "category_fit": _fit_two_tiers()},
                                         "Paper::U": {"trend_name": "U", "category_fit": _fit_two_tiers()},      # ไม่มีในแผนที่
                                         "Paper::V": {"trend_name": "V"}}}                                      # ไม่มี category_fit
    out = l2_map.l2_coverage(cov, data)
    assert out["coverage"]["Paper::T"]["category_fit"]["group_basis"] == "l2"
    assert out["coverage"]["Paper::U"]["category_fit"].get("group_basis") is None and out["_l2_skipped"] == ["U"]
    assert out["coverage"]["Paper::V"] == cov["coverage"]["Paper::V"]
    assert cov["coverage"]["Paper::T"]["category_fit"]["categories"][0]["tiers"][0]["label"] == "low"        # ของเดิมไม่ถูกแก้
    assert l2_map.l2_coverage(cov, None) is cov                                                              # ไม่มีแผนที่ = ของเดิม


def test_excel_rows_for_an_l2_fit_use_category_labels_and_category_columns():
    import run_brand_coverage as rbc

    fit = l2_map.l2_category_fit(_fit_two_tiers(), _products(), "Mine")
    cov = {"Paper::T": {"stream": "Paper", "trend_name": "T", "category_fit": fit, "trend_top_rank": 1}}
    rows = rbc.trend_product_rows("Mine", cov, grading=rbc.fit_grading())
    assert rows and all("กลุ่มเทียบ" in r and "อันดับในหมวด" in r for r in rows)
    assert {r["กลุ่มเทียบ"] for r in rows} == {"ทั้งหมวด"} and "กลุ่มราคา" not in rows[0]
    best = next(r for r in rows if r.get("ประเภท") == "ดีที่สุดของ Mine ในหมวดนี้")
    assert best["สินค้า"] == "p2" and best["ระดับ"] == "Excellent" and best["อันดับในหมวด"] == 2
    assert any(r.get("ประเภท") == "Top 5 ในหมวด" for r in rows)


def test_products_without_sales_data_are_drawn_in_the_steady_row_and_not_in_a_strip():
    from brand_category_data import _fit_sales_map
    from brand_data import best_in_tier
    import fit_sales_map as fm

    class _Index:
        def pair(self, brand, name):
            return {}

    prods = _products()
    prods[149]["sales"] = {"pct": None, "basis": "none", "soldout": False, "zero": False, "sold": None, "value": None, "reviews": None}   # p150 ไม่มีข้อมูล
    tier = l2_map.brand_tier(prods, "Mine")
    m = _fit_sales_map(tier, _Index(), "Mine", CFG["fit_top_pct"], CFG["sales"], best_in_tier(tier, CFG["fit_top_pct"], CFG["sales"]))
    assert {d["state"] for d in m["dots"]} <= {"strong", "steady", "slow"}                       # ไม่มีสถานะ unknown ในกราฟ
    nodata = next(d for d in m["dots"] if d["fit"] == "below_average")
    assert nodata["state"] == "steady" and nodata["fy"] == 0.5
    L = {k: "x" for k in ("excellent", "good", "average", "below_average", "fm_x_first", "fm_x_mid", "fm_x_last", "fm_y_strong_sub",
                          "fm_y_steady_sub", "fm_y_slow_sub", "fm_axis_x", "fm_y_strong", "fm_y_steady", "fm_y_slow")}
    L["fm_axis_y"] = "a|b"
    svg = fm.render_svg(m, L)
    assert svg.startswith("<svg") and "stroke-dasharray" not in svg and 'class="cn' not in svg      # ไม่มีแถบไม่มีข้อมูล ไม่มีตัวเลขจำนวนในช่อง
