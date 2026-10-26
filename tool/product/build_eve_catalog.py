# -*- coding: utf-8 -*-
"""
แปลง eveandboy.xlsx (ร้านออนไลน์ที่ 2 ต่อจาก Konvy - เพิ่มเข้ามา 2026-10-15) เป็น eveandboy_product.csv ที่ pipeline อ่านได้

schema ตระกูลเดียวกับ konvy_product.xlsx (Industry/Category/Sub_category/Segment/Product_Type/Key_Benefits/Ingredient_Functions ...)
ที่ต่างจาก Konvy:
  - ไม่มี size_std / unit_std / dimension_orig / pack_mult / size_flag (ผู้ให้ข้อมูลทำให้เฉพาะ Konvy) -> คำนวณด้วย size_standardiser.py
    (ทดสอบกับ Konvy แล้วตรงกับของผู้ให้ข้อมูล ~99%) ผลอยู่ในคอลัมน์ชื่อเดียวกับ Konvy
  - ไม่มี sold_count (ว่าง 100%), rating/review มีเพียง ~13% -> ปล่อยว่าง (ใช้แสดงผลเท่านั้น ไม่เข้าการจัดอันดับ)
  - มี availability / stock (หมด 55%) -> เติม in_stock (stock > 0)
  - brand_name เป็นตัวพิมพ์ใหญ่ ("L'OREAL") ชื่อไม่เหมือน Konvy ("Loreal Paris") - จับคู่ตอนรวมแคตตาล็อก (build_market_catalog.py)
  - คอนแทคเลนส์บางรุ่นถูกติด Category เป็น Colour Cosmetics -> ติดธง is_lens ให้ตัดตอนรวม

ขั้นตอนนี้ "ไม่ตัดแถว" นอกจาก product_id ซ้ำ (เหมือน build_konvy_catalog.py) - การตัด stock/เลนส์/ซ้ำกับ Konvy ทำที่ build_market_catalog.py
ใช้: python tool/product/build_eve_catalog.py            # eveandboy.xlsx -> eveandboy_product.csv
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

TOOL_DIR = Path(__file__).resolve().parent.parent
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

from product import build_konvy_catalog as bk  # noqa: E402
from product import size_standardiser as ss  # noqa: E402

HERE = Path(__file__).resolve().parent
XLSX_PATH = HERE / "eveandboy.xlsx"
CSV_PATH = HERE / "eveandboy_product.csv"
RETAILER = "Eve and Boy"

# คอลัมน์ที่ pipeline ต้องใช้ - Eve ไม่มี size_std... จึงไม่อยู่ในรายการ (สร้างเอง)
REQUIRED = [c for c in bk.REQUIRED if c != "sold_count"] + ["product_size", "size_unit", "stock"]

# คอนแทคเลนส์: ชื่อบอกตรง ๆ หรือลงท้ายด้วยค่าสายตาติดลบ ("Wish On Me Brown -2.75", "Teddy Brown -5")
# ค่าสายตา 0.00 เดี่ยว ๆ ไม่ใช้ (ชนกับเฉดสีผม 5.05 / เลขเฉดอื่น)
_LENS_NAME_RE = re.compile(r"contact\s*lens|คอนแทค", re.I)
_LENS_POWER_RE = re.compile(r"\s-\d{1,2}(?:\.\d{1,2})?\s*$")


def is_contact_lens(name, category=None):
    """ชื่อสินค้า (+ Category ของไฟล์) -> True ถ้าเป็นคอนแทคเลนส์ (ไม่ใช่เครื่องสำอาง)"""
    text = str(name or "")
    if str(category or "").strip().lower() == "eye care":
        return True
    return bool(_LENS_NAME_RE.search(text) or _LENS_POWER_RE.search(text))


def _id_text(v):
    """2085169013014.0 -> "2085169013014"; ว่าง -> "" """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return str(v).strip()


def to_catalog_frame(raw):
    """DataFrame ดิบจาก eveandboy.xlsx -> DataFrame schema ที่ pipeline อ่าน (คอลัมน์ของ Eve ครบ + alias ชื่อเดิม + คอลัมน์ขนาดมาตรฐาน)
    แถวซ้ำ product_id ตัดเหลือแถวแรก; ไม่แก้ raw"""
    missing = [c for c in REQUIRED if c not in raw.columns]
    if missing:
        raise KeyError(f"eveandboy.xlsx ขาดคอลัมน์ที่ pipeline ต้องใช้: {missing}")
    base = raw.copy()
    if "sold_count" not in base.columns:
        base["sold_count"] = float("nan")
    # product_id เป็น float ในไฟล์ (บาร์โค้ด 13 หลัก) -> สตริงจำนวนเต็ม; product_code ดิบของ Eve = รหัสกลุ่ม (ซ้ำหลายแถว/ตัวเลือก)
    # ไม่ใช่ id ต่อแถวเหมือน Konvy -> เก็บเป็น product_group_code และให้ product_code = product_id (ไม่ซ้ำ) ตาม schema เดิม
    base["product_id"] = [_id_text(v) for v in base["product_id"]]
    if "product_code" in base.columns:
        base = base.rename(columns={"product_code": "product_group_code"})
    out = bk.to_catalog_frame(base)
    out = ss.add_size_columns(out)
    stock = pd.to_numeric(out["stock"], errors="coerce")
    out["in_stock"] = stock.fillna(0) > 0
    out["is_lens"] = [is_contact_lens(n, c) for n, c in zip(out["product_name"], out["Category"])]
    out["retailer"] = RETAILER
    return out


def main():
    ap = argparse.ArgumentParser(description="แปลง eveandboy.xlsx -> eveandboy_product.csv (schema ที่ pipeline อ่าน)")
    ap.add_argument("--src", type=Path, default=XLSX_PATH)
    ap.add_argument("--out", type=Path, default=CSV_PATH)
    args = ap.parse_args()

    print(f"อ่าน {args.src.name} ...")
    raw = pd.read_excel(args.src)
    out = to_catalog_frame(raw)
    out.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"บันทึก {args.out.name}: {len(out)} แถว (ตัดซ้ำ product_id {len(raw) - len(out)}) · {out['brand'].nunique()} แบรนด์ · "
          f"ราคาอ่านได้ {out['sale_price_thb'].notna().mean():.1%} · มีสต็อก {out['in_stock'].mean():.1%} · เลนส์ {out['is_lens'].sum()} แถว")
    print("ขนาดใช้ได้:", f"{out['size_flag'].isin(ss.USABLE_FLAGS).mean():.1%}", out["size_flag"].value_counts().to_dict())
    print("Industry:", out["Industry"].value_counts().head(6).to_dict())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
