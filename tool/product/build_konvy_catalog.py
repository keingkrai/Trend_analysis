# -*- coding: utf-8 -*-
"""
แปลง konvy_product.xlsx (แคตตาล็อกสินค้าหลักแทน Watsons ตั้งแต่ 2026-10-11) เป็น konvy_product.csv ที่ pipeline อ่าน

ทำไมแปลงเป็น CSV: ⑫ ⑬ และรายงานอ่านแคตตาล็อกหลายจุด (load_catalog, report_data, brand_data ...) - อ่าน xlsx ขนาด 30 MB แต่ละครั้งช้า
(~20 วินาที) และโค้ดปลายทางใช้ชื่อคอลัมน์ชุดเดิมจาก watsons_product.csv จึงเติมคอลัมน์ชื่อเดิม (alias) ให้ครบ แล้วปลายทางไม่ต้องแก้

คอลัมน์ที่ Konvy มีชื่อเดียวกับ Watsons อยู่แล้ว (ไม่ต้องแปลง): product_name, brand_name, Industry/Category/Sub_category/Segment/Product_Type,
Key_Benefits/Primary_Use_Case/Product_Insights ..., product_url, sold_count, sales_values, FDA_Noti ฯลฯ
ที่ต้องเติม:
  brand           <- raw_brand_name   (Watsons: brand = ชื่อแบรนด์ตามหน้าสินค้า, brand_name = ชื่อที่ทำความสะอาดแล้ว - Konvy เหมือนกัน)
  sale_price_thb  <- sale_price       ("฿1,290" -> 1290.0)
  original_price_thb <- original_price
  discount        <- discount_percent ("-48%" -> "48% off" ให้เหมือนรูปแบบเดิม)
  main_image      <- image_url
  product_code    <- product_id
  rating_stars    <- rating_score,  reviews <- review_count,  sold <- sold_count,  source <- source_platform
ไม่มี `ingredients` (Konvy ไม่มีรายการส่วนผสมดิบ) - build_product_text() ใช้ Ingredient_Functions แทน

ใช้: python tool/product/build_konvy_catalog.py            # konvy_product.xlsx -> konvy_product.csv (ทุกแถว; การกรอง Beauty ทำที่ load_catalog)
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
XLSX_PATH = HERE / "konvy_product.xlsx"
CSV_PATH = HERE / "konvy_product.csv"

# ชื่อคอลัมน์เดิม (Watsons) <- คอลัมน์ของ Konvy
ALIASES = {
    "brand": "raw_brand_name",
    "product_code": "product_id",
    "main_image": "image_url",
    "rating_stars": "rating_score",
    "reviews": "review_count",
    "sold": "sold_count",
    "source": "source_platform",
}
REQUIRED = ["product_name", "raw_brand_name", "sale_price", "product_id", "image_url", "Industry", "Category", "Sub_category",
            "Segment", "Product_Type", "Key_Benefits", "Primary_Use_Case", "Product_Insights", "Ingredient_Functions", "sold_count"]


def parse_price(v):
    """"฿1,290" / "1,290.00" / 99 -> 1290.0 / 1290.0 / 99.0; ว่างหรืออ่านไม่ได้ -> None"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = re.sub(r"[^0-9.]", "", str(v))
    try:
        return float(s) if s else None
    except ValueError:
        return None


def parse_discount(v):
    """"-48%" -> "48% off" (รูปแบบเดิมของไฟล์ Watsons); ว่าง/อ่านไม่ได้ -> None"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(v))
    return f"{m.group(1)}% off" if m else None


def to_catalog_frame(raw):
    """DataFrame ดิบจาก konvy_product.xlsx -> DataFrame schema ที่ pipeline อ่าน (คอลัมน์ของ Konvy ครบ + alias ชื่อเดิม)
    แถวซ้ำ product_id ตัดเหลือแถวแรก; ไม่แก้ raw"""
    missing = [c for c in REQUIRED if c not in raw.columns]
    if missing:
        raise KeyError(f"konvy_product.xlsx ขาดคอลัมน์ที่ pipeline ต้องใช้: {missing}")
    df = raw.drop_duplicates(subset="product_id", keep="first").reset_index(drop=True)
    out = df.copy()
    for new, old in ALIASES.items():
        if new not in out.columns and old in out.columns:
            out[new] = out[old]
    out["sale_price_thb"] = [parse_price(v) for v in df["sale_price"]]
    out["original_price_thb"] = [parse_price(v) for v in df.get("original_price", [None] * len(df))]
    out["discount"] = [parse_discount(v) for v in df.get("discount_percent", [None] * len(df))]
    return out


def main():
    ap = argparse.ArgumentParser(description="แปลง konvy_product.xlsx -> konvy_product.csv (schema ที่ pipeline อ่าน)")
    ap.add_argument("--src", type=Path, default=XLSX_PATH)
    ap.add_argument("--out", type=Path, default=CSV_PATH)
    args = ap.parse_args()

    print(f"อ่าน {args.src.name} ...")
    raw = pd.read_excel(args.src)
    out = to_catalog_frame(raw)
    out.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"บันทึก {args.out.name}: {len(out)} แถว (ตัดซ้ำ product_id {len(raw) - len(out)}) · {out['brand'].nunique()} แบรนด์ · "
          f"ราคาอ่านได้ {out['sale_price_thb'].notna().mean():.1%} · sold_count มี {out['sold_count'].notna().mean():.1%}")
    print("Industry:", out["Industry"].value_counts().head(6).to_dict())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
