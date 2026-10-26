# -*- coding: utf-8 -*-
"""
⑫ ชั้นอุปทาน — แยกสินค้าที่ใกล้เทรนด์ตามหมวด (feedback 2026-09-28: อยากเห็นสินค้าของแต่ละเทรนด์แยกเป็น 3-5 หมวด)

เดิม ⑫ เก็บแค่ 15 อันดับแรกของทั้งร้าน ผลจึงกระจุกหมวดเดียว (รอบ 082438: Safe Inhalation Spray Cosmetics อยู่
Hygiene & Bath ครบ 15/15, Pregnancy-Safe Dermocosmetics อยู่ Baby Care 11/15) - ไฟล์นี้ใช้ similarity ที่ ⑫ คำนวณ
กับสินค้าครบทุกชิ้นอยู่แล้ว: เอา 1% แรกของทั้งร้าน (pool) ดูว่ากระจายอยู่หมวดไหน เลือก 4 หมวดที่มีสินค้าใน pool
มากที่สุด แล้วเก็บ 3 ชิ้นที่ใกล้ที่สุดของแต่ละหมวด

หมวด = Level 2 (Category) ของ Euromonitor ตาม tool/product/product_category.csv (EM_Group จาก euromonitor_mapping.py)
และกรองเหลือเฉพาะ Level 1 = Beauty and Personal Care ตั้งแต่โหลดสินค้า (2026-10-01) - ผู้เรียกส่ง "group" ของแต่ละชิ้นมาเอง
(เดิมใช้ Sub_category ของ Watsons 42 หมวด + แตก Hair Care ด้วย Product_Type: เลิกแล้ว เพราะ L2 ของ Euromonitor
แยก Hair Care/Skin Care/Sun Care/Colour Cosmetics ฯลฯ ไว้ให้แล้ว)
🆕 (2026-10-01) หมวดที่มีสินค้าใน pool ไม่ถึง MIN_POOL_PER_CATEGORY ไม่ได้คอลัมน์ และถ้าคอลัมน์ไม่ครบ 4 หมวดที่ใหญ่ที่สุด
ถูกแตกเป็นชนิดสินค้า (Level 4 เช่น "Skin Care · Serum") ดู _columns()
🆕 (2026-10-07) แต่ละคอลัมน์แบ่งช่วงราคา ต่ำ / กลาง / สูง จากราคาสินค้า**ทั้งร้าน**ของคอลัมน์นั้น (แบ่งจำนวนเท่าๆ กัน ดู
market_price_cuts) - ทุกเทรนด์/ลูกค้าจึงได้ช่วงเดียวกันในหมวดเดียวกัน แต่ละช่วงเก็บชิ้นที่ใกล้เทรนด์ที่สุด + จำนวนชิ้นใน pool
(ต่างจาก price_tiers.py ของ ⑬/⑱ ที่แบ่งจากราคาสินค้าของแบรนด์ลูกค้าเอง)

🆕 (2026-10-08) ส่ง main_category (หมวดหลักที่ LLM เลือกต่อเทรนด์ - trend_category.py) มา = เฉพาะหมวดนั้น คอลัมน์เป็นชนิดสินค้า (L4)
ของหมวด และ pool = สินค้าที่ใกล้เทรนด์ที่สุดในหมวดนั้น (_main_breakdown) ไม่ส่ง = โหมดเดิมข้างบน (เก็บไว้ให้ผลรอบเก่า/เทส)

ไม่เรียก API/LLM - ฟังก์ชันล้วน เทสได้ด้วยข้อมูลปลอม (tests/test_pure_functions.py)
"""
import math
import statistics
from collections import Counter

POOL_FRACTION = 0.01   # 1% แรกของสินค้าความงามทั้งร้าน (~8,800 SKU -> ~88 ชิ้น) ใช้ดูว่าเทรนด์ใกล้หมวดไหน
N_CATEGORIES = 4       # หมวดที่แสดงในรายงาน (พอดี 4 คอลัมน์ในหน้า 16:9)
PER_CATEGORY = 3       # สินค้าต่อหมวด
N_DISTRIBUTION = 5     # หมวดในแถบสัดส่วน - ที่เหลือรวมเป็น "หมวดอื่น" (group = None)

# ข้อมูลสินค้าที่เก็บต่อชิ้น (รายงานใช้ชื่อ+แบรนด์ join รูป/ลิงก์จาก konvy_product.csv เอง)
MIN_POOL_PER_CATEGORY = 3   # คอลัมน์ต้องมีสินค้าใน pool อย่างน้อยเท่านี้ (1-2 ชิ้นเป็นหลักฐานอ่อน - เดิมเจอ "Bath and Shower 1")

# ข้อมูลสินค้าที่เก็บต่อชิ้น (รายงานใช้ชื่อ+แบรนด์ join รูป/ลิงก์จาก konvy_product.csv เอง)
# subgroup = ชนิดสินค้า (Level 4 ของ Euromonitor) ใช้แตกหมวดที่ครองหน้า
PRODUCT_FIELDS = ("product_name", "brand", "category", "group", "subgroup", "similarity", "sale_price_thb", "sold_count")

# 🆕 (2026-10-12) ฟิลด์ช่วงราคาต่อปริมาณที่ติดมากับสินค้า (unit_price_tiers.py) - ใส่ในผลเฉพาะเมื่อสินค้ามี unit_tier
UNIT_FIELDS = ("unit_price", "unit_label", "size", "is_mini", "unit_tier")


def product_view(s):
    """สินค้า (dict ของ scored) -> ฟิลด์ที่เก็บลงผล: PRODUCT_FIELDS (+ UNIT_FIELDS เมื่อสินค้ามีช่วงราคาต่อปริมาณ)"""
    out = {k: s.get(k) for k in PRODUCT_FIELDS}
    if "unit_tier" in s:
        out.update({k: s.get(k) for k in UNIT_FIELDS})
    return out


N_PRICE_TIERS = 3   # 🆕 (2026-10-07) ช่วงราคาต่อคอลัมน์ (0 = ไม่แบ่ง)
PRICE_TIER_LABELS = {1: ("all",), 2: ("low", "high"), 3: ("low", "mid", "high")}   # คีย์แปลภาษาในรายงาน (ต่ำ -> สูง)


def market_price_cuts(prices, n_tiers=N_PRICE_TIERS):
    """🆕 (2026-10-07) ราคาสินค้าทุกชิ้นของคอลัมน์ในร้าน -> เส้นแบ่ง (บาท) สูงสุด n_tiers - 1 เส้น เรียงต่ำไปสูง
    แบ่งให้แต่ละช่วงมีจำนวนสินค้าเท่าๆ กัน เส้น = ราคาสูงสุดของช่วงล่าง (ราคาที่ซ้ำกับเส้นอยู่ช่วงล่างทั้งหมด จำนวนจึงไม่เท่าเป๊ะ)
    ราคาซ้ำกันมากจนเส้นชนกัน/เท่าราคาสูงสุด -> ทิ้งเส้นนั้น (ช่วงน้อยลง ช่วงบนสุดต้องไม่ว่าง)"""
    p = sorted(x for x in prices if x is not None)
    cuts = []
    for i in range(1, n_tiers):
        j = round(len(p) * i / n_tiers)
        if 0 < j < len(p):
            cut = p[j - 1]
            if (not cuts or cut > cuts[-1]) and cut < p[-1]:
                cuts.append(cut)
    return cuts


def _tier_of(price, cuts):
    """ราคา -> ลำดับช่วง (0 = ต่ำสุด) ราคา <= เส้นแบ่งอยู่ช่วงล่าง"""
    return next((i for i, c in enumerate(cuts) if price <= c), len(cuts))


def tier_ranges(prices, n_tiers=N_PRICE_TIERS):
    """ราคาทุกชิ้นของกลุ่ม -> (เส้นแบ่ง, [{"label", "price_from", "price_to"}] เป็นบาทเต็ม ต่ำ -> สูง) ใช้ร่วมกับ category_fit.py"""
    cuts = market_price_cuts(prices, n_tiers)
    lo, hi = math.floor(min(prices)), math.floor(max(prices))
    return cuts, [{"label": label,
                   "price_from": lo if t == 0 else math.floor(cuts[t - 1]) + 1,
                   "price_to": hi if t == len(cuts) else math.floor(cuts[t])}
                  for t, label in enumerate(PRICE_TIER_LABELS[len(cuts) + 1])]


def _keyed_price_tiers(members, pool_ids, n_tiers, tier_key):
    """🆕 (2026-10-12) ช่วงจากเลขที่คำนวณไว้แล้วในสินค้า (s[tier_key] = 0..n_tiers-1 - unit_price_tiers.py "unit_tier": ราคาต่อปริมาณ
    เทียบในชนิดสินค้าเดียวกัน) ผลรูปเดียวกับ _price_tiers; ช่วงที่ไม่มีสินค้าเลยถูกตัดทิ้ง price_from/price_to = ราคาขายต่ำสุด/สูงสุดในช่วง"""
    labels = PRICE_TIER_LABELS[n_tiers]
    cells = [{"label": lb, "n_total": 0, "n_pool": 0, "product": None, "_prices": [], "_units": []} for lb in labels]
    for rank, s in members:
        t = s.get(tier_key)
        if t is None:
            continue
        cell = cells[min(max(int(t), 0), len(labels) - 1)]
        cell["n_total"] += 1
        cell["n_pool"] += id(s) in pool_ids
        if s.get("sale_price_thb") is not None:
            cell["_prices"].append(s["sale_price_thb"])
        if cell["product"] is None:
            cell["product"] = {**product_view(s), "rank_in_market": rank}
        if s.get("unit_price") is not None:
            cell["_units"].append((s["unit_price"], bool(s.get("is_mini")), s.get("unit_label")))
    # หน่วยของป้ายช่วงทั้งคอลัมน์ใช้ร่วมกัน (ไม่ให้ช่วงต่ำเป็น "/g" แต่ช่วงกลางเป็น "/ml"): หน่วยเดียวที่พบ หรือ ml_g เมื่อพบ ml กับ g
    # ปนกัน (ชนิดสินค้าที่ขายทั้งเป็นมิลลิลิตรและกรัม เช่นกันแดด) - ตัวสินค้าแต่ละชิ้นยังแสดงหน่วยของตัวเอง
    # 🆕 (2026-10-14) ชนิดหน่วยของคอลัมน์ = ml/g (ปริมาตร-น้ำหนัก ถือเป็นหน่วยเดียวกัน) หรือ ชิ้น - เอาชนิดที่มีสินค้ามากกว่า ช่วง ฿/หน่วย
    # นับเฉพาะสินค้าชนิดหน่วยเดียวกับคอลัมน์ (เดิมเอา ฿ ต่อชิ้นของแปรงสระผม 59 ฿ ไปปนกับ ฿ ต่อ ml ได้ช่วง "ไม่เกิน 59 บาท/มล.")
    counts = Counter(l for c in cells for _, _, l in c["_units"] if l)
    vol_mass = counts.get("ml", 0) + counts.get("g", 0)
    col_kind = "gml" if vol_mass >= counts.get("pcs", 0) else "pcs"
    kind_labels = ("ml", "g") if col_kind == "gml" else ("pcs",)
    if col_kind == "gml" and vol_mass and counts.get("ml", 0) >= 0.25 * vol_mass and counts.get("g", 0) >= 0.25 * vol_mass:
        col_label = "ml_g"
    elif counts:
        col_label = Counter({k: v for k, v in counts.items() if k in kind_labels}).most_common(1)[0][0]
    else:
        col_label = None
    out = []
    for c in cells:
        if not c["n_total"]:
            continue
        pr, units = c.pop("_prices"), c.pop("_units")
        # ช่วง ฿/หน่วย ที่พบในช่วงนี้ (ไม่นับขนาดทดลอง/ซอง - ไม่งั้นช่วงสูงดูสูงเกินจริง)
        same_kind = [(u, mini) for u, mini, lab in units if lab in kind_labels]
        core = [u for u, mini in same_kind if not mini] or [u for u, _ in same_kind]
        out.append({**c, "price_from": math.floor(min(pr)) if pr else None, "price_to": math.floor(max(pr)) if pr else None,
                    "unit_from": round(min(core), 2) if core else None, "unit_to": round(max(core), 2) if core else None,
                    "unit_label": col_label})
    return out or None


def _price_tiers(members, pool_ids, n_tiers, tier_key=None):
    """members: [(อันดับในร้าน, สินค้า)] ของคอลัมน์ ครบทั้งร้าน เรียงตามความใกล้เทรนด์ / pool_ids: id() ของสินค้าใน pool
    -> [{"label", "price_from", "price_to" (บาทเต็ม), "n_total" (สินค้าในร้าน), "n_pool" (ใน pool),
         "product": ชิ้นที่ใกล้เทรนด์ที่สุดในช่วงนั้น (PRODUCT_FIELDS + rank_in_market)}] หรือ None ถ้าไม่มีราคาเลย
    สินค้าที่ไม่มีราคาไม่เข้าช่วงไหน; tier_key ส่งมา = ใช้เลขช่วงที่คำนวณไว้แล้วในสินค้า (_keyed_price_tiers)"""
    if tier_key and n_tiers:
        return _keyed_price_tiers(members, pool_ids, n_tiers, tier_key)
    prices = [s["sale_price_thb"] for _, s in members if s.get("sale_price_thb") is not None]
    if not prices or not n_tiers:
        return None
    cuts, ranges = tier_ranges(prices, n_tiers)
    tiers = [{**r, "n_total": 0, "n_pool": 0, "product": None} for r in ranges]
    for rank, s in members:
        if s.get("sale_price_thb") is None:
            continue
        tier = tiers[_tier_of(s["sale_price_thb"], cuts)]
        tier["n_total"] += 1
        tier["n_pool"] += id(s) in pool_ids
        if tier["product"] is None:
            tier["product"] = {**product_view(s), "rank_in_market": rank}
    return tiers


def _order(items, key):
    """เรียงหมวดตามจำนวนใน pool มากไปน้อย เท่ากัน -> หมวดที่มีชิ้นใกล้ที่สุดก่อน (items เรียงตาม similarity แล้ว)"""
    counts, best = Counter(), {}
    for s in items:
        k = key(s)
        if k:
            counts[k] += 1
            best.setdefault(k, s["similarity"])
    return sorted(counts, key=lambda g: (-counts[g], -best[g])), counts


def _columns(pool, order, counts, n_categories, min_pool):
    """เลือกคอลัมน์ [(หมวด L2, ชนิดสินค้า หรือ None)] - 🆕 (2026-10-01) หมวด L2 ฝั่งความงามมีแค่ ~13 หมวดและมักมีหมวดเดียวครอง
    pool (เช่น Hair Care 86 จาก 87) หน้าสินค้าจึงเหลือ 2-3 คอลัมน์ เจ้าของงานเลือกให้แตกหมวดที่ใหญ่ที่สุดเป็นชนิดสินค้า (L4):
    1) คอลัมน์ = หมวด L2 ที่มีสินค้าใน pool >= min_pool (ไม่มีหมวดไหนถึง -> ใช้หมวดอันดับต้นตามเดิม)
    2) ไม่ถึง n_categories -> แทนหมวดที่ใหญ่ที่สุดที่ยังไม่แตกด้วยชนิดสินค้าใน pool ที่ถึง min_pool (ต้องได้อย่างน้อย 2 ชนิด)
       เท่าที่ช่องว่างพอ ทำซ้ำกับหมวดถัดไปจนครบหรือแตกไม่ได้แล้ว - คอลัมน์ชนิดสินค้าเรียงต่อกันในตำแหน่งของหมวดแม่"""
    qualified = [g for g in order if counts[g] >= min_pool] or order
    columns = [(g, None) for g in qualified[:n_categories]]
    tried = set()
    while len(columns) < n_categories:
        cand = next(((i, g) for i, (g, sub) in enumerate(columns) if sub is None and g not in tried), None)
        if cand is None:
            break
        i, g = cand
        tried.add(g)
        sub_order, sub_counts = _order([s for s in pool if s["group"] == g], lambda s: s.get("subgroup"))
        subs = [x for x in sub_order if sub_counts[x] >= min_pool]
        if len(subs) < 2:
            continue
        columns[i:i + 1] = [(g, x) for x in subs[:n_categories - len(columns) + 1]]
    return columns


def _assemble(ranked, pool, columns, color_of, group_sizes, subgroup_sizes, per_category, n_price_tiers, tier_key=None):
    """คอลัมน์ [(หมวด L2, ชนิดสินค้า หรือ None)] -> รายการ categories ของผลลัพธ์ - ใช้ร่วมกันทั้งโหมดหมวดจาก pool และโหมดหมวดหลัก
    members = (อันดับในร้าน, สินค้า) ครบทั้งร้านของแต่ละคอลัมน์ เรียงตามความใกล้ - คอลัมน์ไม่ซ้อนกัน (หมวดที่แตกแล้วไม่มีคอลัมน์หมวดแม่)"""
    def member(s, col):
        return s["group"] == col[0] and (col[1] is None or s.get("subgroup") == col[1])

    members = {col: [] for col in columns}
    for rank, s in enumerate(ranked, 1):
        col = next((c for c in columns if member(s, c)), None)
        if col is not None:
            members[col].append((rank, s))

    pool_ids = {id(s) for s in pool}
    categories = []
    for col in columns:
        g, sub = col
        in_pool = [s for s in pool if member(s, col)]
        prices = [s["sale_price_thb"] for s in in_pool if s.get("sale_price_thb") is not None]
        total = (subgroup_sizes or {}).get(col, 0) if sub else group_sizes.get(g, 0)
        categories.append({
            "group": f"{g} · {sub}" if sub else g, "parent": g, "subgroup": sub, "color": color_of(col),
            "n_pool": len(in_pool), "n_total": total,
            "median_price_thb": statistics.median(prices) if prices else None,
            "min_price_thb": min(prices) if prices else None,
            "max_price_thb": max(prices) if prices else None,
            "products": [{**product_view(s), "rank_in_market": rank}
                         for rank, s in members[col][:per_category]],
            "price_tiers": _price_tiers(members[col], pool_ids, n_price_tiers, tier_key),
        })
    return categories


def _main_breakdown(ranked, main, group_sizes, pool_size, n_categories, per_category, n_distribution, min_pool,
                    subgroup_sizes, n_price_tiers, tier_key=None):
    """🆕 (2026-10-08) หมวดหลักที่ LLM เลือก (trend_category.py) หมวดเดียว: pool = pool_size ชิ้นที่ใกล้เทรนด์ที่สุด**ในหมวดหลัก**
    (ไม่ใช่ทั้งร้าน - ไม่งั้นเทรนด์ที่สินค้าใกล้สุดอยู่หมวดอื่นจะเหลือสินค้าในหมวดหลักไม่กี่ชิ้น) คอลัมน์ = ชนิดสินค้า (Level 4) ของหมวดหลัก
    ที่มีสินค้าใน pool >= min_pool เรียงตามจำนวน สูงสุด n_categories คอลัมน์ (ต้องได้อย่างน้อย 2 ชนิด ไม่งั้นคอลัมน์เดียวทั้งหมวด)
    แถบสัดส่วน (distribution) = ชนิดสินค้าใน pool; rank_in_market ยังเป็นอันดับเทียบสินค้าทั้งร้าน เหมือนโหมดเดิม"""
    pool = [s for s in ranked if s["group"] == main][:pool_size]
    out = {"pool_size": len(pool), "distribution": [], "categories": [], "main_category": main,
           "n_category": group_sizes.get(main, 0)}
    if not pool:
        return out
    order, counts = _order(pool, lambda s: s.get("subgroup"))
    out["distribution"] = [{"group": g, "n": counts[g]} for g in order[:n_distribution]]
    rest = len(pool) - sum(d["n"] for d in out["distribution"])
    if rest:
        out["distribution"].append({"group": None, "n": rest})
    subs = [g for g in order if counts[g] >= min_pool]
    columns = [(main, g) for g in subs[:n_categories]] if len(subs) >= 2 else [(main, None)]
    out["categories"] = _assemble(ranked, pool, columns, lambda col: order.index(col[1]) if col[1] else 0,
                                  group_sizes, subgroup_sizes, per_category, n_price_tiers, tier_key)
    return out


def category_breakdown(scored, group_sizes, pool_fraction=POOL_FRACTION, n_categories=N_CATEGORIES,
                       per_category=PER_CATEGORY, n_distribution=N_DISTRIBUTION, min_pool=MIN_POOL_PER_CATEGORY,
                       subgroup_sizes=None, n_price_tiers=N_PRICE_TIERS, main_category=None, tier_key=None):
    """scored: สินค้าทุกชิ้นของเทรนด์นี้ (dict มีอย่างน้อย group / similarity / sale_price_thb และ subgroup ถ้าจะให้แตกหมวดได้)
    group_sizes: {หมวด: จำนวน SKU ทั้งร้าน}, subgroup_sizes: {(หมวด, ชนิดสินค้า): จำนวน SKU ทั้งร้าน}
    (ตัวหารของ "ใกล้เทรนด์ x จาก y ชิ้นในหมวด")

    คืน {"pool_size", "distribution": [{"group", "n"}, ... , {"group": None, "n": หมวดอื่นรวม}],
         "categories": [{"group" (ป้าย: "Skin Care" หรือ "Skin Care · Serum"), "parent", "subgroup", "color",
                         "n_pool", "n_total", "median/min/max_price_thb",
                         "products": [ข้อมูลตาม PRODUCT_FIELDS + rank_in_market],
                         "price_tiers": ช่วงราคาจากราคาตลาดของคอลัมน์ (ดู _price_tiers) หรือ None}]}
    scored ต้องเป็นสินค้า**ทั้งร้าน** (ช่วงราคาคิดจากราคาทุกชิ้นของคอลัมน์ใน scored) - n_price_tiers = 0 ไม่แบ่งช่วงราคา
    distribution (แถบสัดส่วน) เป็นระดับหมวด L2 เสมอ - color = ลำดับของหมวดแม่ในแถบนั้น (คอลัมน์ที่แตกจากหมวดเดียวกันได้สีเดียวกัน)
    สินค้าในคอลัมน์ไม่จำกัดว่าต้องอยู่ใน pool; rank_in_market = อันดับความใกล้เมื่อเทียบสินค้าทั้งร้าน (1 = ใกล้เทรนด์ที่สุด)
    🆕 (2026-10-08) main_category (หมวด L2 ที่ LLM เลือก - trend_category.py): เฉพาะหมวดนั้น คอลัมน์ = ชนิดสินค้าของหมวด ดู _main_breakdown
    (ผลมีคีย์ "main_category" เพิ่ม และ distribution เป็นระดับชนิดสินค้า); ไม่ส่ง = โหมดเดิม (หมวดที่มีสินค้าใน pool มากที่สุด)
    🆕 (2026-10-12) tier_key (เช่น "unit_tier" จาก unit_price_tiers.py): ช่วงของแต่ละคอลัมน์ใช้เลขช่วงที่คำนวณไว้แล้วในสินค้า (ราคาต่อปริมาณ
    เทียบในชนิดสินค้าเดียวกัน) แทนการแบ่งจากราคาขายของคอลัมน์ - ไม่ส่ง = แบ่งจากราคาขายเหมือนเดิม"""
    ranked = sorted(scored, key=lambda s: s["similarity"], reverse=True)
    if not ranked:
        return {"pool_size": 0, "distribution": [], "categories": [], **({"main_category": main_category} if main_category else {})}
    pool_size = max(1, round(len(ranked) * pool_fraction))
    if main_category:
        return _main_breakdown(ranked, main_category, group_sizes, pool_size, n_categories, per_category, n_distribution,
                               min_pool, subgroup_sizes, n_price_tiers, tier_key)
    pool = ranked[:pool_size]
    order, counts = _order(pool, lambda s: s["group"])

    distribution = [{"group": g, "n": counts[g]} for g in order[:n_distribution]]
    rest = pool_size - sum(d["n"] for d in distribution)
    if rest:
        distribution.append({"group": None, "n": rest})

    columns = _columns(pool, order, counts, n_categories, min_pool)
    categories = _assemble(ranked, pool, columns, lambda col: order.index(col[0]),
                           group_sizes, subgroup_sizes, per_category, n_price_tiers, tier_key)
    return {"pool_size": pool_size, "distribution": distribution, "categories": categories}
