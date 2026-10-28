# -*- coding: utf-8 -*-
"""
Unit test ของเกณฑ์เกรดสินค้า = ความใกล้เทรนด์ล้วน (🆕 2026-10-27: ตัดยอดขาย Konvy ออกจากเกรดและรายงาน - เกณฑ์ใช้กับสินค้านอก Konvy ได้):
brand_data (fit_level / grade_product / best_in_tier / best_in_category / trend_categories / load_config) และ
run_brand_coverage.trend_grade_info - ข้อมูลปลอมทั้งหมด ไม่เรียก API

รัน: pytest main/tool/tests/test_fit_grading.py -v
"""
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent
for sub in ("phase3_supply_layer", "phase6_pdf_report", ""):
    sys.path.insert(0, str(TOOL / sub) if sub else str(TOOL))

import brand_data as bd  # noqa: E402

TOP = {"excellent": 1, "good": 5, "average": 20}


def mk(rank, **extra):
    return {"product_name": f"B{rank}", "brand": "Mine", "sale_price_thb": 99.0, "similarity": 0.5, "rank_in_tier": rank,
            "rank_in_market": rank, **extra}


def test_grade_is_the_rank_in_the_group_and_nothing_else():
    # กลุ่ม 1,000 ชิ้น: Excellent <= 10, Good <= 50, Average <= 200 - ยอดขายไม่มีผลแม้ข้อมูลยอดขายอยู่ในสินค้า
    for sales in (None, {"pct": 0.99, "zero": False}, {"pct": 0.01, "zero": True}):
        assert [bd.grade_product(mk(r, sales=sales), 1000, TOP)["level"] for r in (1, 10, 11, 50, 51, 200, 201)] ==             ["excellent", "excellent", "good", "good", "average", "average", "below_average"]


def test_rank_one_of_a_tiny_group_is_always_excellent_and_no_rank_is_below_average():
    assert bd.grade_product(mk(1), 3, TOP)["level"] == "excellent"
    assert bd.fit_level(None, bd.rank_cuts(3, TOP)) == "below_average"


def test_best_in_tier_is_the_best_ranked_product():
    tier = {"label": "mid", "n_total": 1000, "brand_best": mk(30), "brand_products": [mk(80), mk(30)]}
    best = bd.best_in_tier(tier, TOP)
    assert best["raw"]["rank_in_tier"] == 30 and best["level"] == "good"


def test_results_without_brand_products_fall_back_to_brand_best():
    old = {"label": "low", "n_total": 1000, "brand_best": mk(30)}
    assert [p["rank_in_tier"] for p in bd.tier_products(old)] == [30]
    assert bd.best_in_tier(old, TOP)["level"] == "good"
    assert bd.best_in_tier({"label": "x", "n_total": 0}, TOP) is None
    assert bd.best_in_category({"tiers": []}, TOP) == (None, None)


class _Index:
    def pair(self, brand, name):
        return {}


def test_trend_categories_grade_uses_the_best_ranked_product_and_its_reason():
    a, b = mk(30), mk(80)
    a["match_reason"] = "Closest match."
    fit = {"categories": [{"category": "Skin Care", "n_brand": 2, "n_total": 3000,
                           "brand_best": {**a, "tier": "mid", "n_tier": 1000, "price_from": 1, "price_to": 9, "match_reason": "closest"},
                           "tiers": [{"label": "mid", "n_total": 1000, "n_brand": 2, "price_from": 1, "price_to": 9,
                                      "top": [], "brand_best": a, "brand_products": [a, b]}]}]}
    entry = bd.trend_categories(fit, "Mine", _Index(), TOP)[0]
    best = entry["best"]
    assert best["name_full"] == "B30" and best["level"] == "good" and best["reason"] == "Closest match."
    assert "sales" not in best and "base_level" not in best and entry["tiers"][0]["best"]["name_full"] == "B30"


def test_config_has_no_sales_cutoffs_any_more():
    assert "sales" not in bd.load_config(None)
    cfg_file = Path(__file__).resolve().parents[2] / "config" / "brand_report.json"
    cfg = bd.load_config(cfg_file)
    assert "sales" not in cfg and cfg["fit_top_pct"] == TOP


def test_trend_grade_info_matches_brand_data_and_old_results_still_grade():
    import run_brand_coverage as rbc
    a, b = mk(30), mk(80)
    fit = {"categories": [{"category": "Skin Care", "tiers": [{"label": "mid", "n_total": 1000, "brand_best": a,
                                                              "brand_products": [a, b]}]}]}
    grading = {"top_pct": TOP, "level": lambda rank, n: bd.fit_level(rank, bd.rank_cuts(n, TOP))}   # grading แบบมีแค่ top_pct
    info = rbc.trend_grade_info(fit, grading)
    assert info["level"] == "good" and info["tier"] == "mid" and set(info) == {"level", "category", "tier", "product"}
    assert rbc.trend_grade(fit, grading) == ("good", "Skin Care", "mid")
    assert rbc.trend_grade({"categories": []}, grading) == ("below_average", None, None)
