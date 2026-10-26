# -*- coding: utf-8 -*-
"""
⑬/⑰/⑱ ชั้นอุปทาน — เทียบสินค้าของแบรนด์ลูกค้ากับเทรนด์แบบ "เทรนด์ -> หมวด -> ช่วงราคา -> สินค้า" (ผู้ใช้เลือก 2026-10-07)

1) เทรนด์ -> หมวด: 🆕 (2026-10-08) หมวด L2 **หลักหมวดเดียว** ที่ LLM เลือก (trend_category.py) - ไม่นับหมวดควบคู่ (เจ้าของงานเลือก)
   เดิมใช้หมวดที่มีสินค้า >= 20% ของ 1% แรกที่ embedding ใกล้เทรนด์ที่สุด ซึ่งพาหมวดที่แค่มีคำซ้ำ (กันแดดชื่อ "Barrier") เข้ามาเป็นหมวดสำคัญ
2) หมวด -> ช่วงราคา: ช่วงราคาตลาดของหมวด (ราคาทุกชิ้นของหมวดในร้านแบ่ง 3 กลุ่มจำนวนเท่ากัน - category_breakdown.tier_ranges)
3) ช่วงราคา -> สินค้า: ในแต่ละกลุ่ม (หมวด x ช่วงราคา) เรียงตามความใกล้เทรนด์ เก็บ top N + สินค้าที่ดีที่สุดของแบรนด์ + อันดับในกลุ่ม
4) สินค้าที่ดีที่สุดของแบรนด์ในหมวด = ชิ้นที่ "% แรกในกลุ่ม" ดีที่สุด (อันดับในกลุ่ม / ขนาดกลุ่ม เท่ากัน -> อันดับน้อยกว่า)

ไม่ตัดเกรด (เกณฑ์ % อยู่ที่รายงาน - config/brand_report.json) ไม่เรียก API/LLM - ฟังก์ชันล้วน
ต่างจาก price_tiers.py (⑱ รุ่นแรก) ที่แบ่งช่วงราคาจากราคาสินค้าของแบรนด์เอง
"""
import math

from category_breakdown import N_PRICE_TIERS, PRICE_TIER_LABELS, UNIT_FIELDS, _tier_of, tier_ranges

TOP_N = 5   # สินค้าอันดับต้นที่เก็บต่อกลุ่ม (หมวด x ช่วงราคา)
PRODUCT_FIELDS = ("product_name", "brand", "sale_price_thb", "similarity")


def _slim(s, **extra):
    base = {k: s.get(k) for k in PRODUCT_FIELDS}
    if "unit_tier" in s:   # 🆕 (2026-10-12) ช่วงราคาต่อปริมาณ: เก็บขนาด/฿ต่อหน่วย/ขนาดทดลองไว้แสดงในรายงาน
        base.update({k: s.get(k) for k in UNIT_FIELDS})
    if s.get("sales") is not None:   # 🆕 (2026-10-19) ยอดขาย Konvy ของสินค้า (sales_level.market_sales) - ใช้ปรับเกรดที่รายงาน
        base["sales"] = s["sales"]
    return {**base, **extra}


def _keyed_cells(priced, n_tiers, tier_key):
    """🆕 (2026-10-12) สินค้า [(อันดับ, สินค้า)] ที่มีเลขช่วงใน s[tier_key] -> (ranges, cells) เฉพาะช่วงที่มีสินค้า ต่ำ -> สูง
    ป้ายช่วงตามเลขมาตรฐาน (3 ช่วง: low/mid/high) - สินค้าที่เลขช่วงเกิน n_tiers ถูกจำกัดไว้ที่ช่วงสูงสุด"""
    labels = PRICE_TIER_LABELS[n_tiers]
    buckets = [[] for _ in labels]
    for rank, s in priced:
        buckets[min(max(int(s[tier_key]), 0), len(labels) - 1)].append((rank, s))
    ranges, cells = [], []
    for label, cell in zip(labels, buckets):
        if not cell:
            continue
        prices = [s["sale_price_thb"] for _, s in cell if s.get("sale_price_thb") is not None]
        ranges.append({"label": label, "price_from": math.floor(min(prices)) if prices else None,
                       "price_to": math.floor(max(prices)) if prices else None})
        cells.append(cell)
    return ranges, cells


def category_fit(scored, brand, main_category, n_tiers=N_PRICE_TIERS, top_n=TOP_N, tier_key=None):
    """scored: สินค้าทุกชิ้นของตลาดสำหรับเทรนด์นี้ (dict มี product_name / brand / group (หมวด L2) / sale_price_thb / similarity)
    brand: ชื่อแบรนด์ลูกค้าตรงตัวกับช่อง brand, main_category: หมวด L2 หลักของเทรนด์ (LLM เลือก - trend_category.py)

    คืน {"n_market", "main_category", "tier_basis" (price / unit_price), "categories": [  # หมวดเดียว (หมวดหลัก); ตลาดไม่มีสินค้าในหมวดนั้นเลย -> []
           {"category", "n_total" (ในร้าน), "n_brand" (สินค้าแบรนด์ในหมวด),
            "tiers": [{"label", "price_from", "price_to", "n_total", "n_brand",
                       "top": [สินค้า + rank_in_tier / rank_in_market], "brand_best": สินค้า + อันดับ หรือ None,
                       "brand_products": [สินค้าของแบรนด์ทุกชิ้นในกลุ่ม + rank_in_tier / rank_in_market] (🆕 2026-10-19)}],
            "brand_best": {สินค้า + rank_in_tier, n_tier, tier, price_from, price_to, rank_in_market} หรือ None}]}
    ตลาดว่าง -> None / สินค้าที่ไม่มีราคาไม่อยู่กลุ่มไหน (นับใน n_total ของหมวดแต่ไม่นับในช่วงราคา)
    🆕 (2026-10-12) tier_key = ชื่อคีย์ของสินค้าที่เก็บเลขช่วง 0..n_tiers-1 ที่คำนวณไว้แล้ว (unit_price_tiers.py: "unit_tier" -
    ช่วงราคาต่อปริมาณเทียบในชนิดสินค้าเดียวกัน) แทนการแบ่งจากราคาขายของทั้งหมวด; ช่วงที่ไม่มีสินค้าเลยถูกตัดทิ้ง
    price_from/price_to ของช่วงแบบนี้ = ราคาขายต่ำสุด/สูงสุดของสินค้าในช่วง (ข้อมูลประกอบ - ไม่ใช่เส้นแบ่ง)"""
    ranked = sorted(scored, key=lambda s: s["similarity"], reverse=True)
    if not ranked:
        return None
    members = [(rank, s) for rank, s in enumerate(ranked, 1) if s["group"] == main_category]
    categories = []
    if members:
        if tier_key:
            priced = [(rank, s) for rank, s in members if s.get(tier_key) is not None]
        else:
            priced = [(rank, s) for rank, s in members if s.get("sale_price_thb") is not None]
        tiers, best = [], None
        if priced:
            if tier_key:
                ranges, cells = _keyed_cells(priced, n_tiers, tier_key)
            else:
                cuts, ranges = tier_ranges([s["sale_price_thb"] for _, s in priced], n_tiers)
                cells = [[] for _ in ranges]
                for rank, s in priced:
                    cells[_tier_of(s["sale_price_thb"], cuts)].append((rank, s))
            for r, cell in zip(ranges, cells):
                mine = [(i, rank, s) for i, (rank, s) in enumerate(cell, 1) if s["brand"] == brand]
                bb = _slim(mine[0][2], rank_in_tier=mine[0][0], rank_in_market=mine[0][1]) if mine else None
                tiers.append({**r, "n_total": len(cell), "n_brand": len(mine),
                              "top": [_slim(s, rank_in_tier=i, rank_in_market=rank)
                                      for i, (rank, s) in enumerate(cell[:top_n], 1)],
                              # 🆕 (2026-10-19) สินค้าของแบรนด์ทุกชิ้นในกลุ่มนี้ (เรียงตามความใกล้เทรนด์) - เกรดสินค้ารวมยอดขายต้องลองทุกชิ้น
                              # ไม่ใช่แค่ชิ้นที่ใกล้เทรนด์ที่สุด (ชิ้นถัดไปอาจขายดีกว่าจนเกรดหลังปรับดีกว่า) brand_best ยังเป็นชิ้นที่ใกล้เทรนด์ที่สุด
                              "brand_products": [_slim(s, rank_in_tier=i, rank_in_market=rank) for i, rank, s in mine],
                              "brand_best": bb})
                if bb and (best is None or (bb["rank_in_tier"] / len(cell), bb["rank_in_tier"])
                           < (best["rank_in_tier"] / best["n_tier"], best["rank_in_tier"])):
                    best = {**bb, "n_tier": len(cell), "tier": r["label"],
                            "price_from": r["price_from"], "price_to": r["price_to"]}
        categories.append({"category": main_category, "n_total": len(members),
                           "n_brand": sum(1 for _, s in members if s["brand"] == brand),
                           "tiers": tiers, "brand_best": best})
    # tier_basis: ช่วงในกลุ่มนี้แบ่งด้วยอะไร (รายงาน/Excel เลือกข้อความป้ายช่วงตามนี้) - ผลรุ่นก่อน 2026-10-12 ไม่มี = price
    return {"n_market": len(ranked), "main_category": main_category, "categories": categories,
            "tier_basis": "unit_price" if tier_key else "price"}
