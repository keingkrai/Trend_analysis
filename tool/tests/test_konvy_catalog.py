# -*- coding: utf-8 -*-
"""
เทสแคตตาล็อก Konvy (2026-10-11 แทน Watsons): ตัวแปลง konvy_product.xlsx -> konvy_product.csv, ข้อความส่วนผสมที่ใช้ embed,
และตัวคัดแถวที่ส่งให้ LLM จัดหมวด - ไม่เรียก API; เทสไฟล์จริงข้ามถ้าไม่มี konvy_product.csv

รัน: pytest main/tool/tests/test_konvy_catalog.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

TOOL_DIR = Path(__file__).resolve().parent.parent
for _p in (TOOL_DIR, TOOL_DIR / "phase3_supply_layer"):
    sys.path.insert(0, str(_p))

from product import build_konvy_catalog as bk  # noqa: E402
from product import classify_products_llm as cl  # noqa: E402
from product import euromonitor_mapping as em  # noqa: E402


def _raw(**over):
    row = {"product_name": "Alright Super Whitening Soap 100g", "raw_brand_name": "Alright", "brand_name": "Alright",
           "sale_price": "฿1,290", "original_price": "฿1,890", "discount_percent": "-32%", "product_id": 65730,
           "image_url": "https://s2.konvy.com/x.jpg", "Industry": "Beauty and Personal Care", "Category": "Bath and Shower",
           "Sub_category": "Bar Soap", "Segment": "Bar Soap", "Product_Type": "Whitening bar soap", "Key_Benefits": "k",
           "Primary_Use_Case": "u", "Product_Insights": "i", "Ingredient_Functions": "Vitamin C brightens", "sold_count": 12.0,
           "rating_score": 4.0, "review_count": 3.0, "source_platform": "Konvy"}
    row.update(over)
    return row


# ---------------------------------------------------------------------------
# ตัวแปลง
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, want", [("฿99", 99.0), ("฿1,290", 1290.0), ("1,290.50", 1290.5), (250, 250.0),
                                       (None, None), (float("nan"), None), ("", None), ("ฟรี", None)])
def test_parse_price(raw, want):
    assert bk.parse_price(raw) == want


def test_parse_discount_uses_the_old_off_format():
    assert bk.parse_discount("-48%") == "48% off"
    assert bk.parse_discount(None) is None and bk.parse_discount("") is None


def test_catalog_frame_adds_old_column_names_and_keeps_konvy_columns():
    out = bk.to_catalog_frame(pd.DataFrame([_raw()]))
    r = out.iloc[0]
    assert r["brand"] == "Alright" and r["product_code"] == 65730 and r["main_image"] == "https://s2.konvy.com/x.jpg"
    assert r["sale_price_thb"] == 1290.0 and r["original_price_thb"] == 1890.0 and r["discount"] == "32% off"
    assert r["sold"] == 12.0 and r["sold_count"] == 12.0 and r["rating_stars"] == 4.0 and r["reviews"] == 3.0
    assert r["sale_price"] == "฿1,290" and r["brand_name"] == "Alright"      # คอลัมน์เดิมของ Konvy ยังอยู่


def test_catalog_frame_brand_is_the_listing_brand_not_the_cleaned_one():
    out = bk.to_catalog_frame(pd.DataFrame([_raw(raw_brand_name="&honey", brand_name="honey")]))
    assert out.loc[0, "brand"] == "&honey" and out.loc[0, "brand_name"] == "honey"   # เหมือน Watsons: brand = ตามหน้าสินค้า


def test_catalog_frame_drops_duplicate_product_id_and_does_not_touch_input():
    raw = pd.DataFrame([_raw(), _raw(product_name="dup"), _raw(product_id=2, product_name="b")])
    out = bk.to_catalog_frame(raw)
    assert list(out["product_id"]) == [65730, 2] and out.loc[0, "product_name"] != "dup"
    assert len(raw) == 3 and "brand" not in raw.columns


def test_catalog_frame_missing_required_column_is_an_error():
    with pytest.raises(KeyError, match="Ingredient_Functions"):
        bk.to_catalog_frame(pd.DataFrame([_raw()]).drop(columns=["Ingredient_Functions"]))


# ---------------------------------------------------------------------------
# ข้อความส่วนผสมที่ใช้ embed
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def vas():
    try:
        import validate_at_scale as mod
    except Exception as e:   # noqa: BLE001 - ต้องมี GEMINI_KEY/.env ตอน import (สร้าง client)
        pytest.skip(f"import validate_at_scale ไม่ได้: {e}")
    return mod


def test_embed_text_uses_ingredient_functions_when_there_is_no_ingredients_column(vas):
    text = vas.build_product_text({"product_name": "Serum", "Key_Benefits": "hydrates", "Ingredient_Functions": "Niacinamide evens tone"})
    assert text.endswith("Niacinamide evens tone")


def test_embed_text_prefers_raw_ingredients_and_skips_na_rows(vas):
    assert vas._ingredient_text({"ingredients": "Aqua, Glycerin", "Ingredient_Functions": "moisturizes"}) == "Aqua, Glycerin"
    assert vas._ingredient_text({"Ingredient_Functions": "N/A - textile product"}) == ""
    assert vas._ingredient_text({"Ingredient_Functions": "n/a - cosmetic tool without active ingredients"}) == ""
    assert vas._ingredient_text({"ingredients": float("nan"), "Ingredient_Functions": float("nan")}) == ""
    assert "N/A" not in vas.build_product_text({"product_name": "Brush", "Ingredient_Functions": "N/A - tool"})


# ---------------------------------------------------------------------------
# แถวที่ส่งให้ LLM จัดหมวด
# ---------------------------------------------------------------------------

def test_beauty_candidates_skips_only_rows_that_label_and_rules_both_call_non_beauty():
    df = pd.DataFrame([
        {"product_name": "Eucerin Hyaluron Serum 30 ml", "Product_Type": "Serum", "Segment": "Serum", "Industry": em.BEAUTY},
        {"product_name": "Cotton T-Shirt Basic", "Product_Type": "T-shirt", "Segment": "Tops", "Industry": "Apparel"},
        {"product_name": "Kundal Shampoo 500 Ml.", "Product_Type": "Shampoo", "Segment": "Shampoo", "Industry": "Accessories"},   # ป้ายผิด กฎเห็นว่าความงาม
    ])
    got = cl.beauty_candidates(df)
    assert list(got.index) == [0, 2]


def test_beauty_candidates_keeps_everything_without_an_industry_column():
    df = pd.DataFrame([{"product_name": "a"}, {"product_name": "b"}])
    assert len(cl.beauty_candidates(df)) == 2


# ---------------------------------------------------------------------------
# ไฟล์จริง
# ---------------------------------------------------------------------------

def test_real_konvy_csv_has_the_columns_the_pipeline_reads():
    if not bk.CSV_PATH.exists():
        pytest.skip("ไม่มี konvy_product.csv (รัน tool/product/build_konvy_catalog.py)")
    head = pd.read_csv(bk.CSV_PATH, encoding="utf-8-sig", nrows=50, low_memory=False)
    need = {"brand", "product_name", "sale_price_thb", "sold_count", "main_image", "product_url", "product_code",
            "Industry", "Category", "Sub_category", "Segment", "Product_Type", "Key_Benefits", "Primary_Use_Case",
            "Product_Insights", "Ingredient_Functions"}
    assert need <= set(head.columns)
    assert head["sale_price_thb"].notna().all() and head["sale_price_thb"].map(lambda v: isinstance(v, float)).all()
