# -*- coding: utf-8 -*-
"""
⑬ ยอดขายของสินค้า Konvy แต่ละชิ้น เทียบในกลุ่มเดียวกับที่ตัดเกรด (หมวด L2 x ช่วงราคาต่อปริมาณ) - เจ้าของงานสั่ง 2026-10-19
ให้ยอดขายเข้าไปอยู่ในเกณฑ์เกรดสินค้าของ ⑰ (เกรด = ความใกล้เทรนด์เป็นตัวตั้ง ปรับตามยอดขายไม่เกิน 1 ขั้น - กติกาอยู่ที่ brand_data.py)

ฟังก์ชันล้วน (pandas/numpy) ไม่เรียก API/LLM - เก็บเฉพาะ "ข้อมูลดิบ" ของยอดขาย (เปอร์เซ็นไทล์ในกลุ่ม + ธง) ลงผล ⑬
เส้นตัด Strong/Slow อยู่ที่รายงาน (config/brand_report.json > sales) จึงปรับเส้นตัดได้โดยไม่ต้องรัน ⑬ ใหม่

ที่มาของตัวเลข (ตรวจกับข้อมูลจริง 2026-10-19):
  - sold_count = ยอดขายสะสมตลอดอายุสินค้าที่หน้าสินค้า Konvy แสดง; sales_values = sold_count x ราคาปัจจุบัน (ประมาณการ ไม่ใช่รายได้จริง)
  - สินค้าที่ **ของหมด** (stock <= 0) Konvy ซ่อนตัวนับ -> sold_count = 0 เสมอ (ไม่มีสินค้าที่ขายได้แล้วสต็อก 0 เลย) จึงห้ามอ่านเป็น "ขายไม่ได้":
    ใช้เปอร์เซ็นไทล์ "จำนวนรีวิว" เทียบสินค้าที่ยังมีของในกลุ่มแทน (รีวิวสัมพันธ์กับยอดขาย Spearman ~0.8) ไม่มีรีวิว = ไม่ทราบ
  - ยอดขาย 0 ที่ **ยังมีของ** = ขายไม่ได้จริง (มีรีวิวแค่ 0.4%) -> zero = True
  - ร้านที่ไม่มีตัวนับยอดขาย (Eve and Boy - ถอดออกจากตลาดแล้วตั้งแต่ 2026-10-19) / กลุ่มที่มีสินค้ามียอดขาย < MIN_POOL ชิ้น = ไม่ทราบ

คืนต่อสินค้า: {"pct" (0-1 หรือ None), "basis" ("sales" | "reviews" | "none"), "soldout", "zero", "sold", "value", "reviews"}
"""
import numpy as np
import pandas as pd

MIN_POOL = 10          # กลุ่ม (หมวด x ช่วงราคา) ที่มีสินค้ามียอดขายน้อยกว่านี้ -> ไม่ทราบ (เปอร์เซ็นไทล์ไม่นิ่ง)
UNKNOWN = {"pct": None, "basis": "none", "soldout": False, "zero": False, "sold": None, "value": None, "reviews": None}


def _num(v):
    try:
        return None if v is None or v != v else float(v)
    except (TypeError, ValueError):
        return None


def market_sales(rows, tier_key=None, min_pool=MIN_POOL):
    """rows = สินค้าของตลาด (build_market_rows) แต่ละชิ้นมี group (หมวด L2), sale_price_thb, sold_count, stock, review_count และเลขช่วง
    ราคา r[tier_key] (ถ้า tier_key ไม่ใช่ None) -> list ของ dict ยอดขาย เรียงตรงกับ rows"""
    n = len(rows)
    if not n:
        return []
    d = pd.DataFrame({
        "g": [r.get("group") for r in rows],
        "t": [(_num(r.get(tier_key)) if tier_key else 0.0) for r in rows],
        "sold": [_num(r.get("sold_count")) for r in rows],
        "stock": [_num(r.get("stock")) for r in rows],
        "price": [_num(r.get("sale_price_thb")) for r in rows],
        "rev": [_num(r.get("review_count")) for r in rows],
    })
    d["value"] = d["sold"] * d["price"]
    sold0 = d["sold"].eq(0)
    d["soldout"] = sold0 & d["stock"].le(0)                       # ของหมด -> Konvy ซ่อนตัวนับ
    d["zero"] = sold0 & d["stock"].gt(0)                          # ยังมีของแต่ขาย 0 = ขายไม่ได้จริง
    has = d["sold"].notna() & d["t"].notna() & d["price"].notna() & d["g"].notna()
    # sold = 0 แต่ไม่รู้สต็อก -> แยกไม่ออกว่าหมดหรือขายไม่ได้ -> ไม่ทราบ
    has &= ~(sold0 & d["stock"].isna())
    pool = has & ~d["soldout"]
    keys = ["g", "t"]
    d["sp"] = np.nan
    d["pool_n"] = np.nan
    if pool.any():
        grp = d[pool].groupby(keys)["value"]
        d.loc[pool, "sp"] = grp.rank(pct=True)                    # ค่าเฉลี่ยของอันดับที่เสมอกัน
        d.loc[pool, "pool_n"] = grp.transform("size")
    # รีวิวของสินค้าที่ยังมีของ (ว่าง = 0) ต่อกลุ่ม เรียงแล้ว - ไว้หาเปอร์เซ็นไทล์ของสินค้าที่หมด
    rev_pool = {k: np.sort(v.fillna(0).to_numpy()) for k, v in d[pool].groupby(keys)["rev"]} if pool.any() else {}

    out = []
    for i in range(n):
        x = d.iloc[i]
        if not has.iloc[i]:
            out.append(dict(UNKNOWN))
            continue
        rec = {"pct": None, "basis": "none", "soldout": bool(x["soldout"]), "zero": bool(x["zero"]),
               "sold": int(x["sold"]), "value": round(float(x["value"])), "reviews": None if pd.isna(x["rev"]) else int(x["rev"])}
        if x["soldout"]:
            arr = rev_pool.get((x["g"], x["t"]))
            if arr is not None and len(arr) >= min_pool and not pd.isna(x["rev"]):
                rec["pct"] = round(float((np.searchsorted(arr, x["rev"], "left") + np.searchsorted(arr, x["rev"], "right")) / 2 / len(arr)), 4)
                rec["basis"] = "reviews"
        elif x["pool_n"] >= min_pool:
            rec["pct"] = round(float(x["sp"]), 4)
            rec["basis"] = "sales"
        else:
            rec["zero"] = False      # กลุ่มเล็กเกินไป -> ไม่ทราบ (ไม่ลงโทษ)
        out.append(rec)
    return out
