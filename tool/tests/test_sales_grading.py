# -*- coding: utf-8 -*-
"""
Unit test ของยอดขาย Konvy ในเกณฑ์เกรดสินค้า (🆕 2026-10-19): sales_level.market_sales (เปอร์เซ็นไทล์ในกลุ่ม + ธงของหมด/ขาย 0),
brand_data (sales_state / adjust_level / grade_product / best_in_tier / trend_categories), category_fit (brand_products + sales),
run_brand_coverage.trend_grade_info - ข้อมูลปลอมทั้งหมด ไม่เรียก API

รัน: pytest main/tool/tests/test_sales_grading.py -v
"""
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent
for sub in ("phase3_supply_layer", "phase6_pdf_report", ""):
    sys.path.insert(0, str(TOOL / sub) if sub else str(TOOL))

import brand_data as bd  # noqa: E402
from category_fit import category_fit  # noqa: E402
from sales_level import market_sales  # noqa: E402

SCFG = {"strong_top_pct": 20, "slow_bottom_pct": 25}
TOP = {"excellent": 1, "good": 5, "average": 20}


def prod(i, sold, stock=10, rev=None, price=100.0, tier=0, group="Skin Care"):
    return {"group": group, "unit_tier": tier, "sale_price_thb": price, "sold_count": sold, "stock": stock, "review_count": rev,
            "product_name": f"P{i}", "brand": "Other"}


def pool(n=12, **kw):
    """n สินค้าที่ขายได้ในกลุ่มเดียว ยอดขายเพิ่มขึ้นตามลำดับ (P1 ต่ำสุด)"""
    return [prod(i, sold=i * 10, rev=i, **kw) for i in range(1, n + 1)]


# ---------------------------------------------------------------------------
# sales_level.market_sales
# ---------------------------------------------------------------------------
def test_percentile_is_rank_within_the_group_and_small_groups_are_unknown():
    rows = pool(12) + [prod(99, 500, tier=1, group="Hair Care")]       # กลุ่มที่สอง 1 ชิ้น -> ไม่ทราบ
    out = market_sales(rows, "unit_tier")
    assert out[11]["pct"] == pytest.approx(1.0) and out[0]["pct"] == pytest.approx(1 / 12, abs=1e-3)
    assert out[11]["basis"] == "sales" and out[11]["sold"] == 120 and out[11]["value"] == 12000
    assert out[12]["pct"] is None and out[12]["basis"] == "none" and out[12]["zero"] is False


def test_sold_out_hides_the_counter_so_reviews_replace_sales_and_zero_means_in_stock_with_no_sales():
    rows = pool(12) + [prod(20, 0, stock=0, rev=11),      # ของหมด + รีวิวมาก -> ไม่ใช่ขายไม่ได้
                       prod(21, 0, stock=0, rev=None),     # ของหมดไม่มีรีวิว -> ไม่ทราบ
                       prod(22, 0, stock=5, rev=None)]     # ยังมีของแต่ขาย 0 -> zero
    out = market_sales(rows, "unit_tier")
    assert out[12]["soldout"] and not out[12]["zero"] and out[12]["basis"] == "reviews" and out[12]["pct"] > 0.8
    assert out[13]["soldout"] and out[13]["pct"] is None and out[13]["basis"] == "none"
    assert out[14]["zero"] and not out[14]["soldout"]
    assert out[0]["pct"] > 0                                  # ของหมดไม่เข้ากลุ่มเทียบยอดขาย


def test_missing_sales_data_and_missing_stock_are_unknown():
    rows = pool(12) + [prod(30, None), prod(31, 0, stock=None)]
    out = market_sales(rows, "unit_tier")
    assert out[12]["basis"] == "none" and out[13]["basis"] == "none" and not out[13]["zero"] and not out[13]["soldout"]
    assert market_sales([]) == []


# ---------------------------------------------------------------------------
# brand_data: กติกา
# ---------------------------------------------------------------------------
def test_sales_state_thresholds():
    assert bd.sales_state(None, SCFG) == "unknown"
    assert bd.sales_state({"pct": None, "zero": False}, SCFG) == "unknown"
    assert bd.sales_state({"pct": 0.80}, SCFG) == "strong" and bd.sales_state({"pct": 0.79}, SCFG) == "steady"
    assert bd.sales_state({"pct": 0.25}, SCFG) == "steady" and bd.sales_state({"pct": 0.24}, SCFG) == "slow"
    assert bd.sales_state({"pct": 0.9, "zero": True}, SCFG) == "slow"          # ขาย 0 ที่ยังมีของ ชนะเปอร์เซ็นไทล์


def test_adjust_level_excellent_needs_strong_sales_and_strong_never_lifts_below_average():
    # 🆕 (2026-10-21) Excellent = ใกล้เทรนด์ top 1% และขายดี ทั้งคู่; ไม่ขายดี (ปานกลาง/ไม่มีข้อมูล) ได้สูงสุด Good
    assert [bd.adjust_level(lv, "strong") for lv in bd.FIT_LEVELS] == ["excellent", "good", "good", "below_average"]
    assert [bd.adjust_level(lv, "slow") for lv in bd.FIT_LEVELS] == ["good", "average", "below_average", "below_average"]
    for s in ("steady", "unknown"):
        assert [bd.adjust_level(lv, s) for lv in bd.FIT_LEVELS] == ["good", "good", "average", "below_average"]


def test_grade_product_excellent_match_without_strong_sales_is_capped_at_good():
    g = bd.grade_product(mk(1, 0.5), 1000, TOP, SCFG)                  # ใกล้เทรนด์ top 1% ขายปานกลาง
    assert (g["base"], g["level"], g["state"], g["move"]) == ("excellent", "good", "steady", "cap")
    g = bd.grade_product({**mk(1, 0.5), "sales": None}, 1000, TOP, SCFG)   # ไม่มีข้อมูลยอดขาย = เหมือนปานกลาง
    assert (g["base"], g["level"], g["state"], g["move"]) == ("excellent", "good", "unknown", "cap")
    g = bd.grade_product(mk(1, 0.9), 1000, TOP, SCFG)                  # ขายดีด้วย -> Excellent คงเดิม
    assert (g["base"], g["level"], g["state"], g["move"]) == ("excellent", "excellent", "strong", None)
    g = bd.grade_product(mk(1, 0.1), 1000, TOP, SCFG)                  # ขายได้น้อย = ลง 1 ขั้นเหมือนเดิม (ไม่ใช่ cap)
    assert (g["base"], g["level"], g["state"], g["move"]) == ("excellent", "good", "slow", "down")


def mk(rank, pct, **sales_extra):
    sales = {"pct": pct, "zero": False, "soldout": False, "basis": "sales", "sold": 50, "value": 5000, "reviews": 3, **sales_extra}
    return {"product_name": f"B{rank}", "brand": "Mine", "sale_price_thb": 99.0, "similarity": 0.5, "rank_in_tier": rank,
            "rank_in_market": rank, "sales": sales}


def test_grade_product_and_best_in_tier_prefers_the_better_adjusted_product():
    # กลุ่ม 1,000 ชิ้น: ที่ 40 = Average (top 20% = 200, Good <= 50 -> 40 คือ Good!) ใช้อันดับที่ชัดเจน: 80 = Average, 300 = Below
    g = bd.grade_product(mk(80, 0.9), 1000, TOP, SCFG)
    assert (g["base"], g["level"], g["state"], g["move"]) == ("average", "good", "strong", "up")
    g = bd.grade_product(mk(30, 0.1), 1000, TOP, SCFG)
    assert (g["base"], g["level"], g["move"]) == ("good", "average", "down")
    tier = {"label": "mid", "n_total": 1000, "brand_best": mk(30, 0.1),
            "brand_products": [mk(30, 0.1), mk(80, 0.9)]}
    best = bd.best_in_tier(tier, TOP, SCFG)
    # ชิ้นใกล้เทรนด์ที่สุด (30) ขายช้า -> Average, ชิ้นที่ 80 ขายดี -> Good: ชนะ
    assert best["raw"]["rank_in_tier"] == 80 and best["level"] == "good"


def test_results_without_brand_products_fall_back_to_brand_best_and_no_sales_means_no_change():
    old = {"label": "low", "n_total": 1000, "brand_best": {**mk(30, 0.1), "sales": None}}
    assert [p["rank_in_tier"] for p in bd.tier_products(old)] == [30]
    best = bd.best_in_tier(old, TOP, SCFG)
    assert best["level"] == best["base"] == "good" and best["move"] is None
    assert bd.best_in_tier({"label": "x", "n_total": 0}, TOP, SCFG) is None
    assert bd.best_in_category({"tiers": []}, TOP, SCFG) == (None, None)


# ---------------------------------------------------------------------------
# category_fit เก็บสินค้าของแบรนด์ทุกชิ้น + ยอดขาย
# ---------------------------------------------------------------------------
def test_category_fit_keeps_all_brand_products_per_tier_with_sales():
    scored = []
    for i in range(1, 11):
        scored.append({"product_name": f"M{i}", "brand": "Mine" if i in (2, 5) else "Other", "group": "Skin Care",
                       "sale_price_thb": 100.0 + i, "similarity": 1 - i / 100, "unit_tier": 0,
                       "sales": {"pct": i / 10, "zero": False}})
    fit = category_fit(scored, "Mine", "Skin Care", tier_key="unit_tier")
    tier = fit["categories"][0]["tiers"][0]
    assert [p["product_name"] for p in tier["brand_products"]] == ["M2", "M5"]
    assert [p["rank_in_tier"] for p in tier["brand_products"]] == [2, 5] and tier["brand_best"]["product_name"] == "M2"
    assert tier["brand_products"][1]["sales"]["pct"] == 0.5 and tier["top"][0]["sales"]["pct"] == 0.1


# ---------------------------------------------------------------------------
# trend_categories: เกรดของเทรนด์ใช้สินค้าที่เกรดหลังปรับดีที่สุด + เหตุผลของชิ้นนั้น
# ---------------------------------------------------------------------------
class _Index:
    def pair(self, brand, name):
        return {}


def test_trend_categories_grade_uses_the_best_adjusted_product_and_its_reason():
    a, b = mk(30, 0.1), mk(80, 0.9)
    b["match_reason"] = "Strong seller that fits."
    fit = {"categories": [{"category": "Skin Care", "n_brand": 2, "n_total": 3000,
                           "brand_best": {**a, "tier": "mid", "n_tier": 1000, "price_from": 1, "price_to": 9, "match_reason": "closest"},
                           "tiers": [{"label": "mid", "n_total": 1000, "n_brand": 2, "price_from": 1, "price_to": 9,
                                      "top": [], "brand_best": a, "brand_products": [a, b]}]}]}
    entry = bd.trend_categories(fit, "Mine", _Index(), TOP, SCFG)[0]
    best = entry["best"]
    assert best["name_full"] == "B80" and best["level"] == "good" and best["base_level"] == "average"
    assert best["sales_state"] == "strong" and best["sales_move"] == "up" and best["reason"] == "Strong seller that fits."
    assert best["sales"]["top_pct"] == 10 and entry["tiers"][0]["best"]["name_full"] == "B80"


def test_config_has_default_sales_cutoffs_and_merges_overrides():
    assert bd.load_config(None)["sales"] == {"strong_top_pct": 20, "slow_bottom_pct": 25}
    cfg_file = Path(__file__).resolve().parents[2] / "config" / "brand_report.json"
    assert bd.load_config(cfg_file)["sales"] == {"strong_top_pct": 20, "slow_bottom_pct": 25}


def test_trend_grade_info_matches_brand_data_and_old_results_still_grade():
    import run_brand_coverage as rbc
    a, b = mk(30, 0.1), mk(80, 0.9)
    fit = {"categories": [{"category": "Skin Care", "tiers": [{"label": "mid", "n_total": 1000, "brand_best": a,
                                                              "brand_products": [a, b]}]}]}
    grading = {"top_pct": TOP, "level": lambda rank, n: bd.fit_level(rank, bd.rank_cuts(n, TOP))}   # grading แบบมีแค่ top_pct
    info = rbc.trend_grade_info(fit, grading)
    assert info["level"] == "good" and info["base"] == "average" and info["move"] == "up" and info["tier"] == "mid"
    assert rbc.trend_grade(fit, grading) == ("good", "Skin Care", "mid")
    assert rbc.trend_grade({"categories": []}, grading) == ("below_average", None, None)
