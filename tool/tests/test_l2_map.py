# -*- coding: utf-8 -*-
"""
เทสแผนที่ตลาดระดับหมวด L2 (🆕 2026-10-21): ⑫ l2_market_map.py (เขียน/อ่านไฟล์) และฝั่งรายงาน l2_map.py (ช่อง 4 ระดับความใกล้เทรนด์, สินค้าของแบรนด์)
🆕 (2026-10-27) ตัดยอดขายออกจากเกรดและตารางแล้ว - ข้อมูลยอดขายยังอยู่ในไฟล์แผนที่ของ ⑫ (เทสต์ชั้นข้อมูลไว้) แต่ฝั่งรายงานไม่ใช้
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

CFG = {"fit_top_pct": {"excellent": 1, "good": 5, "average": 20}}


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
    assert products[0]["product_name"] == "skin 0" and "sales" not in products[0]
    assert l2_map.category_products(data, "Paper::missing", "T")[0] == "Skin Care"       # หาด้วยชื่อเทรนด์ได้
    assert l2_map.category_products(data, "Paper::missing") == (None, [])
    assert l2_map.category_products(None, "x") == (None, [])


def test_sales_data_in_the_map_file_is_still_compared_inside_the_whole_category():   # ⑫ ยังเก็บข้อมูลดิบ รายงานไม่ใช้
    df, groups = _catalog()
    table, _ = build_table(df, groups, None, {"Skin Care"})
    pcts = [r[6] for r in table]
    assert pcts == sorted(pcts) and pcts[-1] > 0.9 and pcts[0] < 0.1    # ยอดขายเพิ่มตามเลขชิ้น -> เปอร์เซ็นไทล์เพิ่มตาม


def _products(n=200):
    """สินค้า n ชิ้นเรียงตามความใกล้ (ชิ้นที่ r = อันดับ r ในหมวด)"""
    return [{"brand": "Mine" if r in (1, 2, 150) else "Other", "product_name": f"p{r}", "sale_price_thb": 100.0, "size": None,
             "unit_label": None, "rank": r} for r in range(1, n + 1)]


def test_l2_grid_is_one_row_of_four_levels_with_the_closest_product_in_each():
    grid = l2_map.l2_grid(_products(), CFG)
    assert grid["n"] == 200 and grid["cuts"] == CFG["fit_top_pct"] and set(grid) == {"n", "cuts", "cols", "take"}
    assert [c["level"] for c in grid["cols"]] == ["excellent", "good", "average", "below_average"]
    assert [c["n"] for c in grid["cols"]] == [2, 8, 30, 160]                      # 200 ชิ้น: top 1% = 2, 5% = 10, 20% = 40
    assert [c["product"]["product_name"] for c in grid["cols"]] == ["p1", "p3", "p11", "p41"]   # ชิ้นที่ใกล้เทรนด์ที่สุดของแต่ละระดับ
    assert [c["product"]["level"] for c in grid["cols"]] == ["excellent", "good", "average", "below_average"]
    assert grid["cols"][0]["product"]["rank"] == 1


def test_l2_grid_takeaway_counts_close_matches_and_empty_levels_have_no_product():
    grid = l2_map.l2_grid(_products(), CFG)
    assert grid["take"] == {"n_close": 10, "close_pct": 5}                         # อันดับ 1-10 ของ 200
    tiny = l2_map.l2_grid(_products(3), CFG)                                       # หมวด 3 ชิ้น: ทุกเส้นตัดปัดขึ้นเป็น 1
    assert [c["n"] for c in tiny["cols"]] == [1, 0, 0, 2] and tiny["cols"][1]["product"] is None
    assert l2_map.l2_grid([], CFG)["n"] == 0 and all(c["product"] is None for c in l2_map.l2_grid([], CFG)["cols"])


def test_brand_tier_uses_category_rank_and_skips_brands_without_products():
    tier = l2_map.brand_tier(_products(), "Mine")
    assert tier["n_total"] == 200 and tier["n_brand"] == 3
    assert [p["rank_in_tier"] for p in tier["brand_products"]] == [1, 2, 150]
    assert l2_map.brand_tier(_products(), "Nobody") is None


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


def test_l2_category_fit_borrows_similarity_and_reason_from_the_original_items():
    fit = l2_map.l2_category_fit(_fit_two_tiers(), _products(), "Mine")
    p1 = fit["categories"][0]["tiers"][0]["brand_products"][0]
    assert p1["similarity"] == 0.9 and p1["match_reason"] == "why p1" and p1["rank_in_market"] == 1      # ยืมจาก category_fit เดิม
    assert p1["rank_in_tier"] == 1                                                                          # อันดับเทียบทั้งหมวดจากแผนที่
    p2 = fit["categories"][0]["tiers"][0]["brand_products"][1]                                              # ไม่มีในรายการเดิม: ยังได้ชื่อ/ราคา
    assert p2["product_name"] == "p2" and p2["sale_price_thb"] == 100.0 and p2["similarity"] is None
    reasons = {"p2": "why p2"}
    fit2 = l2_map.l2_category_fit(_fit_two_tiers(), _products(), "Mine", reasons)
    assert fit2["categories"][0]["tiers"][0]["brand_products"][1]["match_reason"] == "why p2"             # l2_reasons ของ ⑬ --l2-reasons-only


def test_existing_grade_functions_work_on_the_l2_fit_and_grade_in_the_category():
    from brand_data import best_in_category

    fit = l2_map.l2_category_fit(_fit_two_tiers(), _products(), "Mine")
    tier, tb = best_in_category(fit["categories"][0], CFG["fit_top_pct"])
    assert tier["label"] == "all" and tb["raw"]["product_name"] == "p1"       # p1 = อันดับ 1 ในหมวด -> Excellent (เกรดตามอันดับล้วน)
    assert tb["level"] == "excellent" and set(tb) == {"raw", "level"}


def test_top_one_percent_is_excellent_whatever_the_sales_and_the_report_no_longer_has_a_sales_adjustment():
    # 🆕 (2026-10-27) Excellent = top 1% ของหมวด อย่างเดียว (เดิมต้องขายดีด้วย) - ไม่มีฟังก์ชัน/ตารางปรับตามยอดขายเหลืออยู่
    import brand_data

    assert not hasattr(brand_data, "adjust_level") and not hasattr(brand_data, "sales_state")
    assert brand_data.grade_product({"rank_in_tier": 1}, 200, CFG["fit_top_pct"])["level"] == "excellent"
    tpl = (Path(__file__).resolve().parent.parent / "phase6_pdf_report" / "templates" / "report.html.j2").read_text(encoding="utf-8")
    assert "final_of" not in tpl and "sales" not in tpl.split("t.l2")[1].split("t.categories")[0]


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
    assert best["สินค้า"] == "p1" and best["ระดับ"] == "Excellent" and best["อันดับในหมวด"] == 1
    assert not any("ยอดขาย" in k for r in rows for k in r)                                                # ตัดคอลัมน์ยอดขายออกจากเกรดแล้ว
    assert any(r.get("ประเภท") == "Top 5 ในหมวด" for r in rows)


def test_images_and_thai_names_reach_the_four_level_products(monkeypatch):
    """🆕 (2026-10-27) l2["cols"] (แถวเดียว) แทน l2["cells"] - โค้ดโหลดรูป (assets) และแปลงชื่อไทย (i18n.localize) ต้องอ่านโครงสร้างใหม่ด้วย
    ไม่งั้นหน้าสินค้าของ ⑯ ได้กล่องเทาแทนรูปโดยไม่มี error"""
    import assets

    grid = l2_map.l2_grid(_products(), CFG, lambda m: {**m, "image_url": f"http://img/{m['product_name']}.jpg", "name": m["product_name"],
                                                       "name_full": "ไทย " + m["product_name"]})
    trend = {"products": [], "l2": {"category": "Skin Care", **grid}}
    monkeypatch.setattr(assets, "fetch_image", lambda url, cache_dir: "data:" + url)
    n_ok, n_urls = assets.attach_product_images([trend], "unused", max_workers=1, log=lambda *_: None)
    assert (n_ok, n_urls) == (4, 4)
    assert [c["product"]["image"] for c in grid["cols"]] == ["data:http://img/p1.jpg", "data:http://img/p3.jpg",
                                                              "data:http://img/p11.jpg", "data:http://img/p41.jpg"]
    src = (Path(__file__).resolve().parent.parent / "phase6_pdf_report" / "i18n.py").read_text(encoding="utf-8")
    assert '(t.get("l2") or {}).get("cols")' in src and '"cells"' not in src.split("def localize")[1]
