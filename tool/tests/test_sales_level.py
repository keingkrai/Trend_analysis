# -*- coding: utf-8 -*-
"""
Unit test ของข้อมูลดิบยอดขาย Konvy ที่ ⑬ ยังเก็บไว้ (sales_level.market_sales + category_fit เก็บยอดขายต่อสินค้า) - ข้อมูลปลอมทั้งหมด ไม่เรียก API
🆕 (2026-10-27) รายงานและเกรดเลิกใช้ยอดขายแล้ว (ดู test_fit_grading.py) แต่ข้อมูลดิบยังอยู่ในผล ⑬ / แผนที่ ⑫ จึงยังเทสต์ไว้

รัน: pytest main/tool/tests/test_sales_level.py -v
"""
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent
for sub in ("phase3_supply_layer", ""):
    sys.path.insert(0, str(TOOL / sub) if sub else str(TOOL))

from category_fit import category_fit  # noqa: E402
from sales_level import market_sales  # noqa: E402


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
