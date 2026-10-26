# -*- coding: utf-8 -*-
"""
เทสแคตตาล็อกตลาด Konvy + Eve and Boy (2026-10-15): ตัวแปลง eveandboy.xlsx, การรวม/ตัดซ้ำข้ามร้าน, ตัด stock, ตารางชื่อแบรนด์ -
ไม่เรียก API; เทสไฟล์จริงข้ามถ้าไม่มี eveandboy_product.csv / market_product.csv

รัน: pytest main/tool/tests/test_market_catalog.py -v
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

TOOL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOL_DIR))

from product import build_eve_catalog as be  # noqa: E402
from product import build_market_catalog as bm  # noqa: E402

ALIASES = {"loreal": "LOreal Paris", "maybelline": "Maybelline New York"}


def _eve_raw(**over):
    row = {"product_name": "SRICHAND Skin Glow Primer 15g", "brand_name": "SRICHAND", "raw_brand_name": "SRICHAND",
           "product_size": 15.0, "size_unit": "g", "product_pieces": 1.0, "Industry": "Beauty and Personal Care",
           "Category": "Colour Cosmetics", "Sub_category": "Face", "Segment": "Primer", "Product_Type": "Primer",
           "Key_Benefits": "k", "Primary_Use_Case": "u", "Product_Insights": "i", "Ingredient_Functions": "Niacinamide",
           "product_id": 8850000000011.0, "sale_price": 89.0, "original_price": 99.0, "discount_percent": 10.0, "stock": 3.0,
           "image_url": "https://x/y.jpg", "product_url": "https://www.eveandboy.com/product/x", "rating_score": None,
           "review_count": None, "product_code": 8850000000011.0, "source_platform": "Eve and Boy", "availability": "InStock",
           "ingredients": "Water, Glycerin"}
    row.update(over)
    return row


def _eve(rows):
    return be.to_catalog_frame(pd.DataFrame([_eve_raw(**r) for r in rows]))


def _konvy_row(**over):
    row = {"product_id": "1", "product_name": "Srichand Skin Glow Primer 15g", "brand": "Srichand", "brand_name": "Srichand",
           "Industry": "Beauty and Personal Care", "Category": "Colour Cosmetics", "sale_price_thb": 89.0, "stock": 10,
           "size_std": 15.0, "unit_std": "g·ml", "size_flag": "ok", "sold_count": 5.0, "Ingredient_Functions": "x",
           "product_url": "https://konvy.com/1"}
    row.update(over)
    return row


def _konvy(rows):
    return pd.DataFrame([_konvy_row(**r) for r in rows])


# ---------------------------------------------------------------------------
# ตัวแปลง Eve
# ---------------------------------------------------------------------------

def test_eve_frame_has_pipeline_columns_and_size_columns():
    out = _eve([{}])
    r = out.iloc[0]
    assert r["brand"] == "SRICHAND" and r["sale_price_thb"] == 89.0 and r["main_image"] == "https://x/y.jpg"
    assert r["product_id"] == "8850000000011" and r["product_code"] == "8850000000011"   # สตริงจำนวนเต็ม ไม่ใช่ float
    assert r["product_group_code"] == 8850000000011.0
    assert (r["size_std"], r["unit_std"], r["size_flag"]) == (15.0, "g·ml", "ok")
    assert bool(r["in_stock"]) is True and bool(r["is_lens"]) is False and r["retailer"] == "Eve and Boy"
    assert pd.isna(r["sold_count"])                                  # Eve ไม่มียอดขาย


def test_eve_out_of_stock_and_duplicate_ids():
    out = _eve([{"stock": 0.0, "availability": "OutOfStock"}, {"product_name": "other"}])
    assert len(out) == 1 and bool(out.iloc[0]["in_stock"]) is False      # product_id ซ้ำ -> เหลือแถวแรก


def test_eve_missing_required_column_is_an_error():
    raw = pd.DataFrame([_eve_raw()]).drop(columns=["Ingredient_Functions"])
    with pytest.raises(KeyError, match="Ingredient_Functions"):
        be.to_catalog_frame(raw)


@pytest.mark.parametrize("name, cat, want", [
    ("IRISENCE Shine On Me Brown -2.75", "Colour Cosmetics", True),
    ("KITTY KAWAII ONEDAY Latte Brown -0.5", "Colour Cosmetics", True),
    ("ANGEL ZONE Contact Lens Malika Brown 14.2 [1 Pair] #-1.75", "Eye Care", True),
    ("Any Name", "Eye Care", True),
    ("คอนแทคเลนส์ รายเดือน", "Colour Cosmetics", True),
    ("Schwarzkopf Natural & Easy Golden Light Brown 5.05", "Hair Care", False),       # เฉดสีผม ไม่ใช่ค่าสายตา
    ("MAC Eyeshadow Palette Rose Lens Embedded In Burgundy", "Colour Cosmetics", False),
    ("Srichand Powder SPF35 PA+++ 10g", "Colour Cosmetics", False),
])
def test_is_contact_lens(name, cat, want):
    assert be.is_contact_lens(name, cat) is want


# ---------------------------------------------------------------------------
# ชื่อแบรนด์ / คำในชื่อ
# ---------------------------------------------------------------------------

def test_norm_brand_ignores_case_spaces_and_punctuation():
    assert bm.norm_brand("L'OREAL") == bm.norm_brand("loreal") == "loreal"
    assert bm.norm_brand("Dr.PONG") == bm.norm_brand("DR PONG")


def test_name_tokens_drop_size_and_brand_keep_shade_numbers():
    a = bm.name_tokens("Peripera Ink Mood Glowy Tint 4g #34 Coral", ("Peripera",))
    b = bm.name_tokens("PERIPERA Ink Mood Glowy Tint 34 CORAL", ("PERIPERA",))
    assert a == b and "34" in a and "4g" not in a
    c = bm.name_tokens("PERIPERA Ink Mood Glowy Tint 35 CORAL", ("PERIPERA",))
    assert c != b                                                       # เฉดต่างกัน = คนละสินค้า
    assert bm.name_tokens("Cushion SPF50+ PA++++ 02", ()) == bm.name_tokens("Cushion SPF50 PA+++ 2", ())   # + และศูนย์นำหน้า


# ---------------------------------------------------------------------------
# รวมแคตตาล็อก
# ---------------------------------------------------------------------------

def test_same_product_on_both_shops_keeps_the_konvy_row():
    merged, pairs, s = bm.merge_catalogs(_konvy([{}]), _eve([{}]), aliases={})
    assert len(merged) == 1 and merged.iloc[0]["retailer"] == "Konvy" and merged.iloc[0]["also_on"] == "Eve and Boy"
    assert merged.iloc[0]["eve_price"] == 89.0 and merged.iloc[0]["eve_url"].endswith("/x")
    assert s["duplicates_merged"] == 1 and len(pairs) == 1


def test_different_shade_size_or_far_price_are_not_merged():
    k = _konvy([{"product_name": "Brand Tint 4g #02 Rose", "brand": "Brand", "size_std": 4.0}])
    for name, size, price in [("BRAND Tint 03 ROSE", 4.0, 89.0),       # เฉดต่าง
                              ("BRAND Tint 02 ROSE", 10.0, 89.0),      # ขนาดต่าง
                              ("BRAND Tint 02 ROSE", 4.0, 899.0)]:     # ราคาห่าง > 3 เท่า
        e = _eve([{"product_name": name, "brand_name": "BRAND", "raw_brand_name": "BRAND", "product_size": size, "sale_price": price}])
        merged, _, s = bm.merge_catalogs(k, e, aliases={})
        assert len(merged) == 2 and s["duplicates_merged"] == 0, (name, size, price)


def test_unusable_size_is_never_merged():
    k = _konvy([{"size_flag": "pieces_unverified"}])
    merged, _, s = bm.merge_catalogs(k, _eve([{}]), aliases={})
    assert len(merged) == 2 and s["duplicates_merged"] == 0


def test_brand_alias_and_spelling_unify_eve_brand_with_konvy():
    k = _konvy([{"product_name": "Loreal Paris Revitalift Serum 30ml", "brand": "LOreal Paris", "size_std": 30.0}])
    e = _eve([{"product_name": "L'OREAL Revitalift Serum", "brand_name": "L'OREAL", "raw_brand_name": "L'OREAL", "product_size": 30.0,
               "sale_price": 799.0}, {"product_name": "SRICHAND Other 10g", "product_size": 10.0, "product_id": 2.0}])
    k.loc[0, "sale_price_thb"] = 799.0
    merged, _, s = bm.merge_catalogs(k, e, aliases=ALIASES | {"loreal": "LOreal Paris"})
    assert s["duplicates_merged"] == 1
    srich = merged[merged["product_name"].str.contains("Other")].iloc[0]
    assert srich["brand"] == "SRICHAND" and srich["brand_listing"] == "SRICHAND"


def test_eve_brand_uses_konvy_spelling_when_only_case_differs():
    k = _konvy([{"product_name": "Eucerin Serum 30ml", "brand": "Eucerin", "size_std": 30.0}])
    e = _eve([{"product_name": "EUCERIN Different Cream 50g", "brand_name": "EUCERIN", "raw_brand_name": "EUCERIN", "product_size": 50.0}])
    merged, _, _ = bm.merge_catalogs(k, e, aliases={})
    assert set(merged["brand"]) == {"Eucerin"} and merged[merged["retailer"] == "Eve and Boy"].iloc[0]["brand_listing"] == "EUCERIN"


def test_out_of_stock_rows_are_dropped_before_merging():
    # Konvy หมด แต่ Eve มี -> เหลือแถว Eve; Eve หมด Konvy มี -> เหลือแถว Konvy
    merged, _, s = bm.merge_catalogs(_konvy([{"stock": 0}]), _eve([{}]), aliases={})
    assert len(merged) == 1 and merged.iloc[0]["retailer"] == "Eve and Boy"
    merged, _, s = bm.merge_catalogs(_konvy([{}]), _eve([{"stock": 0.0}]), aliases={})
    assert len(merged) == 1 and merged.iloc[0]["retailer"] == "Konvy" and pd.isna(merged.iloc[0]["also_on"])
    assert s["eve_oos_dropped"] == 1


def test_keep_oos_brands_and_no_stock_filter():
    k = _konvy([{"stock": 0, "brand": "Eucerin", "product_name": "Eucerin Serum 30ml"},
                {"stock": 0, "product_id": "2", "product_name": "Other Thing 30ml"}])
    e = _eve([{"stock": 0.0, "product_id": 3.0, "product_name": "ZZ Unique", "brand_name": "ZZ", "raw_brand_name": "ZZ"}])
    merged, _, _ = bm.merge_catalogs(k, e, aliases={}, keep_oos_brands=["eucerin"])
    assert list(merged["brand"]) == ["Eucerin"]
    merged, _, _ = bm.merge_catalogs(k, e, aliases={}, stock_filter=False)
    assert len(merged) == 3


def test_include_eve_false_gives_konvy_only_market_with_same_rules_and_columns():
    # 🆕 (2026-10-19) ตลาด Konvy ล้วน: กฎสต็อก/keep-oos เหมือนเดิม คอลัมน์เท่าตลาดรวม ไม่มีแถว Eve
    k = _konvy([{"product_name": "Konvy A 10g", "size_std": 10.0},
                {"product_id": "2", "stock": 0, "product_name": "Konvy Out 10g", "size_std": 10.0},
                {"product_id": "3", "stock": 0, "brand": "Eucerin", "product_name": "Eucerin Serum 30ml", "size_std": 30.0}])
    e = _eve([{"product_id": 9.0, "product_name": "ZZ Unique 5g", "brand_name": "ZZ", "raw_brand_name": "ZZ", "product_size": 5.0}])
    both, _, _ = bm.merge_catalogs(k, e, aliases={}, keep_oos_brands=["eucerin"])
    only, pairs, s = bm.merge_catalogs(k, e, aliases={}, keep_oos_brands=["eucerin"], include_eve=False)
    assert "Eve and Boy" in set(both["retailer"])
    assert set(only["retailer"]) == {"Konvy"} and list(only["product_id"]) == ["1", "3"]
    assert list(only.columns) == list(both.columns)
    assert s["include_eve"] is False and s["eve_rows_out"] == 0 and pairs.empty
    assert len(e) == 1                                         # input ไม่ถูกแก้


def test_no_eve_cli_writes_side_files_next_to_out_and_not_the_live_ones(tmp_path, monkeypatch):
    k = _konvy([{"product_name": "Konvy A 10g", "size_std": 10.0}])
    e = _eve([{"product_id": 9.0, "product_name": "ZZ Unique 5g", "brand_name": "ZZ", "raw_brand_name": "ZZ", "product_size": 5.0}])
    k.to_csv(tmp_path / "k.csv", index=False, encoding="utf-8-sig")
    e.to_csv(tmp_path / "e.csv", index=False, encoding="utf-8-sig")
    live_pairs, live_summary = tmp_path / "live_pairs.csv", tmp_path / "live_summary.json"
    monkeypatch.setattr(bm, "PAIRS_CSV", live_pairs)
    monkeypatch.setattr(bm, "SUMMARY_JSON", live_summary)
    monkeypatch.setattr(bm, "ALIASES_JSON", tmp_path / "none.json")
    out = tmp_path / "konvy_only.csv"
    monkeypatch.setattr(sys, "argv", ["x", "--konvy", str(tmp_path / "k.csv"), "--eve", str(tmp_path / "e.csv"),
                                      "--out", str(out), "--no-eve"])
    bm.main()
    assert set(pd.read_csv(out, encoding="utf-8-sig", low_memory=False)["retailer"]) == {"Konvy"}
    assert (tmp_path / "konvy_only_pairs.csv").exists() and (tmp_path / "konvy_only_summary.json").exists()
    assert not live_pairs.exists() and not live_summary.exists()


def test_lens_rows_are_dropped_and_raw_ingredients_do_not_override_function_text():
    e = _eve([{"product_name": "IRISENCE Wish Brown -2.75", "brand_name": "IRISENCE", "raw_brand_name": "IRISENCE"},
              {"product_id": 5.0, "product_name": "MILLE Gloss 3g", "brand_name": "MILLE", "raw_brand_name": "MILLE", "product_size": 3.0}])
    merged, _, s = bm.merge_catalogs(_konvy([{"product_name": "Konvy Only 10g", "size_std": 10.0}]), e, aliases={})
    assert s["eve_lens_dropped"] == 1 and len(merged) == 2
    assert "ingredients" not in merged.columns and merged["ingredients_raw"].notna().any()


def test_product_ids_stay_unique_and_inputs_untouched():
    k = _konvy([{"product_id": "8850000000011", "product_name": "Konvy Only 10g", "size_std": 10.0}])
    e = _eve([{}])
    k_before, e_before = k.copy(), e.copy()
    merged, _, _ = bm.merge_catalogs(k, e, aliases={})
    assert merged["product_id"].is_unique
    pd.testing.assert_frame_equal(k, k_before)
    pd.testing.assert_frame_equal(e, e_before)


def test_alias_file_is_valid_and_has_no_alias_loops():
    data = json.loads(bm.ALIASES_JSON.read_text(encoding="utf-8"))["aliases"]
    assert data, "config/brand_aliases.json ว่าง"
    canon = {bm.norm_brand(c) for c in data}
    alias_keys = [bm.norm_brand(a) for v in data.values() for a in v]
    assert len(alias_keys) == len(set(alias_keys))          # ชื่อเดียวกันไม่ชี้ไปสองแบรนด์
    assert not (set(alias_keys) & canon)                    # alias ไม่ใช่ชื่อหลักของอีกรายการ (ไม่เป็นโซ่)
    assert bm.load_aliases() == {bm.norm_brand(a): c for c, v in data.items() for a in v}


def test_pipeline_reads_the_market_catalog_everywhere():
    sys.path.insert(0, str(TOOL_DIR / "phase6_pdf_report"))
    from product import euromonitor_mapping as em
    import build_pdf_report as bpr
    assert em.CSV_PATH == bm.OUT_CSV
    assert bpr.PRODUCT_CSV == bm.OUT_CSV      # รายงานต้องอ่านตลาดชุดเดียวกับที่ ⑫/⑬ ใช้


# ---------------------------------------------------------------------------
# ไฟล์จริง
# ---------------------------------------------------------------------------

def test_real_market_catalog_if_built():
    p = TOOL_DIR / "product" / "market_product.csv"
    if not p.exists():
        pytest.skip("ยังไม่ได้รัน build_market_catalog.py")
    m = pd.read_csv(p, encoding="utf-8-sig", low_memory=False,
                    usecols=["product_id", "retailer", "stock", "is_lens", "size_flag", "brand", "product_name"])
    assert m["product_id"].is_unique
    summary = json.loads((TOOL_DIR / "product" / "market_product_summary.json").read_text(encoding="utf-8"))
    oos = m[pd.to_numeric(m["stock"], errors="coerce").fillna(0) <= 0]
    if summary.get("stock_filter"):                      # แถวสต็อกหมดต้องเป็นแบรนด์ที่สั่งยกเว้นไว้เท่านั้น
        keep = {bm.norm_brand(b) for b in summary.get("keep_oos_brands", [])}
        assert set(oos["brand"].map(bm.norm_brand)) <= keep
    lens = m.loc[m["retailer"] == "Eve and Boy", "is_lens"].map(lambda v: v is True or str(v).lower() == "true")
    assert not lens.any()
    # 🆕 (2026-10-19) ตลาดจริงเป็น Konvy ล้วน (--no-eve; Eve ไม่มียอดขาย) - ถ้ากลับไปรวม Eve ต้องมีทั้งสองร้าน
    assert set(m["retailer"]) == ({"Konvy", "Eve and Boy"} if summary.get("include_eve", True) else {"Konvy"})
