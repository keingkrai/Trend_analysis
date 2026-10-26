# -*- coding: utf-8 -*-
"""
⑬/⑱ ชั้นอุปทาน — เทียบสินค้าของแบรนด์ "ในหมวดของเทรนด์ แล้วแบ่งตามช่วงราคาของแบรนด์เอง" (feedback 2026-10-05)

เดิม ⑬ จัดอันดับสินค้าของแบรนด์เทียบกับสินค้า**ทั้งตลาด** (ซีรัมของแบรนด์ต้องแข่งกับกันแดด/มาสก์/เครื่องสำอาง)
ไฟล์นี้ใช้ความคล้าย (similarity) ที่ ⑬ คำนวณกับสินค้าครบทุกชิ้นอยู่แล้ว มาจัดใหม่เป็น 4 ขั้น:
1) เทรนด์ -> หมวด L2 หลัก = หมวดที่มีสินค้าใน 1% แรกของตลาด (pool) มากที่สุด (ตรรกะเดียวกับ category_breakdown.py ของ ⑫)
2) สินค้าของแบรนด์ในหมวดนั้น: จำนวน + ช่วงราคา
3) แบ่งช่วงราคาเป็น N ระดับ (ค่าเริ่มต้น 3) จาก**ราคาสินค้าของแบรนด์เอง**: เรียงราคาแล้วแบ่งกลุ่มเท่าๆ กัน เส้นแบ่งอยู่กึ่งกลาง
   ระหว่างสินค้าสองชิ้นที่ติดกัน ช่วงรวมจำกัดที่ [ราคาต่ำสุด, สูงสุด] ของแบรนด์ - สินค้าตลาดที่ถูก/แพงกว่าช่วงที่แบรนด์ขายไม่ถูกเทียบ
4) ต่อระดับราคา: เรียง "หมวด ∩ ระดับราคา" ตามความคล้าย -> top N + สินค้าที่ดีที่สุดของแบรนด์ในระดับนั้นพร้อมอันดับ
   (อันดับในระดับราคา <= อันดับในหมวด <= อันดับในตลาดทั้งร้านเสมอ เพราะกลุ่มเทียบเล็กลง)

ไม่เรียก API/LLM - ฟังก์ชันล้วน เทสได้ด้วยข้อมูลปลอม (tests/test_pure_functions.py)
ผลเก็บใน coverage[trend]["price_tiers"] ของไฟล์ ⑬ แล้วรายงาน ⑱ (phase6_pdf_report/build_brand_category_report.py) ไปอ่านต่อ
"""
import math

from category_breakdown import POOL_FRACTION, _order

N_TIERS = 3   # จำนวนระดับราคาสูงสุด (แบรนด์มีสินค้าในหมวดน้อย -> ได้น้อยกว่านี้ ดู tier_cuts)
TOP_N = 5     # สินค้าอันดับต้นที่เก็บต่อระดับราคา

# ข้อมูลสินค้าที่เก็บต่อชิ้น (รายงานใช้ชื่อ+แบรนด์ join รูป/ลิงก์จาก konvy_product.csv เอง)
PRODUCT_FIELDS = ("product_name", "brand", "sale_price_thb", "similarity")


def tier_labels(n):
    """ป้าย key ของระดับราคาจากต่ำไปสูง (ใช้เป็นคีย์แปลภาษาในรายงาน)"""
    return {1: ("all",), 2: ("low", "high")}.get(n, ("low", "mid", "high"))


def tier_cuts(prices, n_tiers=N_TIERS):
    """ราคาสินค้าของแบรนด์ -> เส้นแบ่งระดับราคา (บาท จากต่ำไปสูง) ยาว <= n_tiers - 1

    แต่ละระดับต้องมีสินค้าของแบรนด์ >= 2 ชิ้น (จำนวนระดับ = min(n_tiers, จำนวนสินค้า // 2) อย่างน้อย 1) - แบรนด์เล็กได้
    1-2 ระดับ เส้นแบ่งคือค่ากลางระหว่างชิ้นที่ j-1 กับ j ของลิสต์ที่เรียงราคาแล้ว (ราคาซ้ำกันได้ ชิ้นที่ราคา = เส้นแบ่ง
    อยู่ระดับล่าง) เส้นที่ซ้ำกันหรือเท่ากับราคาสูงสุดถูกทิ้ง (ระดับสูงสุดต้องไม่ว่าง)"""
    p = sorted(x for x in prices if x is not None)
    k = max(1, min(n_tiers, len(p) // 2))
    cuts = []
    for i in range(1, k):
        j = round(len(p) * i / k)
        cut = (p[j - 1] + p[j]) / 2
        if (not cuts or cut > cuts[-1]) and cut < p[-1]:
            cuts.append(cut)
    return cuts


def tier_of(price, cuts):
    """ราคา -> ลำดับระดับ (0 = ต่ำสุด) ราคา <= เส้นแบ่งอยู่ระดับล่าง"""
    for i, c in enumerate(cuts):
        if price <= c:
            return i
    return len(cuts)


def tier_bounds(cuts, price_min, price_max):
    """เส้นแบ่ง -> [(ราคาตั้งแต่, ราคาถึง)] เป็นจำนวนเต็มบาทสำหรับแสดงผล (ระดับแรกเริ่มที่ราคาต่ำสุดของแบรนด์
    ระดับสุดท้ายจบที่ราคาสูงสุด) - ราคาขายเป็นจำนวนเต็ม จึงใช้ floor ของเส้นแบ่ง"""
    bounds = []
    for i in range(len(cuts) + 1):
        lo = math.floor(price_min) if i == 0 else math.floor(cuts[i - 1]) + 1
        hi = math.floor(price_max) if i == len(cuts) else math.floor(cuts[i])
        bounds.append((lo, hi))
    return bounds


def _slim(s, **extra):
    out = {k: s.get(k) for k in PRODUCT_FIELDS}
    if out["similarity"] is not None:
        out["similarity"] = round(float(out["similarity"]), 4)
    return {**out, **extra}


def _ranks(s):
    return {"rank_in_market": s["rank_in_market"], "rank_in_category": s["rank_in_category"]}


def _top_pct(rank, n):
    return max(1, round(rank / n * 100)) if n else None


def _tier(label, members, brand, top_n, price_from=None, price_to=None):
    """members: สินค้าของ "หมวด ∩ ระดับราคา" เรียงตามความคล้าย (มี rank_in_market/rank_in_category แล้ว)"""
    mine = [(i, s) for i, s in enumerate(members, 1) if s["brand"] == brand]
    best = None
    if mine:
        i, s = mine[0]
        best = _slim(s, **_ranks(s), rank_in_tier=i, top_pct_in_tier=_top_pct(i, len(members)))
    return {
        "label": label, "price_from": price_from, "price_to": price_to,
        "n_market": len(members), "n_brands": len({s["brand"] for s in members}), "n_brand": len(mine),
        "top": [_slim(s, **_ranks(s), rank_in_tier=i, is_you=s["brand"] == brand)
                for i, s in enumerate(members[:top_n], 1)],
        "brand_best": best,
    }


def price_tier_breakdown(scored, brand, n_tiers=N_TIERS, top_n=TOP_N, pool_fraction=POOL_FRACTION):
    """scored: สินค้าทุกชิ้นของตลาดสำหรับเทรนด์นี้ (dict มี product_name / brand / group (หมวด L2) / sale_price_thb / similarity)
    brand: ชื่อแบรนด์ลูกค้าตรงตัวกับช่อง brand

    คืน {"category", "n_category", "n_market", "pool_size", "pool_in_category",
         "brand": {"name", "n", "n_priced", "price_min", "price_max", "best": {สินค้า + rank_in_category/market, top_pct}},
         "tiers": [{"label" (low/mid/high หรือ all), "price_from", "price_to", "n_market", "n_brands", "n_brand",
                    "top": [top N: สินค้า + rank_in_tier + is_you], "brand_best": {สินค้า + rank_in_tier ...} หรือ None}],
         "excluded": {"cheaper", "pricier", "unpriced"} (สินค้าในหมวดที่อยู่นอกช่วงราคาของแบรนด์/ไม่มีราคา)}
    หรือ None ถ้าไม่มีสินค้า/หาหมวดหลักไม่ได้ (ไม่มีสินค้าไหนใน pool มีหมวด)

    แบรนด์ไม่มีสินค้าในหมวดหลัก (หรือไม่มีราคาเลย) -> tiers มี 1 ระดับ "all" = top N ของหมวดทั้งช่วงราคา
    (ไม่มีช่วงราคา price_from/price_to = None) และ brand_best เป็นสินค้าที่ดีที่สุดของแบรนด์ถ้ามี"""
    ranked = sorted(scored, key=lambda s: s["similarity"], reverse=True)
    if not ranked:
        return None
    pool_size = max(1, round(len(ranked) * pool_fraction))
    order, counts = _order(ranked[:pool_size], lambda s: s["group"])
    if not order:
        return None
    category = order[0]

    cat = []   # สินค้าในหมวดหลัก เรียงตามความคล้าย พร้อมอันดับในตลาดทั้งร้าน / ในหมวด
    for rank, s in enumerate(ranked, 1):
        if s["group"] == category:
            cat.append({**s, "rank_in_market": rank, "rank_in_category": len(cat) + 1})

    mine = [s for s in cat if s["brand"] == brand]
    priced = [s for s in mine if s.get("sale_price_thb") is not None]
    prices = [s["sale_price_thb"] for s in priced]
    price_min, price_max = (min(prices), max(prices)) if prices else (None, None)
    best = mine[0] if mine else None

    brand_info = {
        "name": brand, "n": len(mine), "n_priced": len(priced),
        "price_min": price_min, "price_max": price_max,
        "best": (_slim(best, **_ranks(best), top_pct_in_category=_top_pct(best["rank_in_category"], len(cat)))
                 if best else None),
    }
    result = {"category": category, "n_category": len(cat), "n_market": len(ranked), "pool_size": pool_size,
              "pool_in_category": counts[category], "brand": brand_info}

    if not priced:   # ไม่มีสินค้าของแบรนด์ในหมวดนี้ (หรือไม่มีราคา) -> ไม่มีช่วงราคาให้แบ่ง แสดง top N ทั้งหมวด
        result["tiers"] = [_tier("all", cat, brand, top_n)]
        result["excluded"] = {"cheaper": 0, "pricier": 0,
                              "unpriced": sum(1 for s in cat if s.get("sale_price_thb") is None)}
        return result

    cuts = tier_cuts(prices, n_tiers)
    in_range = [s for s in cat if s.get("sale_price_thb") is not None and price_min <= s["sale_price_thb"] <= price_max]
    labels = tier_labels(len(cuts) + 1)
    tiers = []
    for t, (lo, hi) in enumerate(tier_bounds(cuts, price_min, price_max)):
        members = [s for s in in_range if tier_of(s["sale_price_thb"], cuts) == t]
        tiers.append(_tier(labels[t], members, brand, top_n, lo, hi))
    result["tiers"] = tiers
    result["excluded"] = {
        "cheaper": sum(1 for s in cat if s.get("sale_price_thb") is not None and s["sale_price_thb"] < price_min),
        "pricier": sum(1 for s in cat if s.get("sale_price_thb") is not None and s["sale_price_thb"] > price_max),
        "unpriced": sum(1 for s in cat if s.get("sale_price_thb") is None),
    }
    return result
