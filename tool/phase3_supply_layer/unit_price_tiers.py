# -*- coding: utf-8 -*-
"""
⑫/⑬ ชั้นอุปทาน — ช่วงราคา "ต่อปริมาณ" (฿ ต่อ ml/g หรือ ต่อชิ้น) แทนช่วงราคาขาย (เจ้าของงานเลือก 2026-10-12)

ทำไมเทียบ "ภายในชนิดสินค้า": ราคาต่อปริมาณของทั้งหมวด L2 เรียงตามชนิดสินค้าแทนระดับราคา (Skin Care: เซรั่ม 75% อยู่ช่วงแพง
โลชั่นทาตัว 81% อยู่ช่วงถูก) จึงแบ่งช่วงภายในกลุ่มสินค้าที่เทียบกันได้ (cohort) แล้วค่อยรวมเป็นกลุ่มของหมวด:

1) หน่วย: ml/g (g·ml - ถือว่า 1 ml ~ 1 g) และชิ้น เป็นคนละกลุ่ม ไม่เอามาหารปนกัน
   ใช้ size_std ของ Konvy (คูณจำนวนแพ็กแล้ว - แก้บั๊ก "1.5ml x5 = 1.5 ml" ของ Watsons) เฉพาะ size_flag ok / bundle_summed
   ขนาดผสมหน่วย (dimension = mixed เช่น "40ml + 40g") / ไม่มีขนาด -> ใช้ราคาขายเทียบในกลุ่มแทน (tier_basis = "price")
2) cohort: (หน่วย, L2, L3, L4) ที่มีสินค้า >= min_cohort ไม่ถึง -> (หน่วย, L2, L3) -> (หน่วย, L2) (tier_basis = L4/L3/L2)
3) ขนาดทดลอง/ซอง (ขนาด < mini_ratio ของค่ากลางของ cohort) ไม่ถูกนับตอนหาเส้นแบ่ง (ไม่งั้นดันเส้นแบ่งขึ้น) แต่ยังได้ช่วงตามเส้นนั้น
   (is_mini = True) - ผู้ใช้เลือกแบบนี้ 2026-10-12
4) เส้นแบ่ง = แบ่งสามส่วนเท่าๆ กันด้วย category_breakdown.market_price_cuts (กติกาเดียวกับช่วงราคาเดิม - ราคาซ้ำอยู่ช่วงล่าง)
5) unit_tier เป็นเลขมาตรฐาน 0 / 1 / 2 = ต่ำ / กลาง / สูง (cohort ที่เส้นชนกันจนเหลือ 2 ช่วง -> 0 กับ 2) เพื่อให้รวมข้าม cohort ได้

ผลเป็นคุณสมบัติรายสินค้าที่คำนวณครั้งเดียวต่อแคตตาล็อก - ⑫ (หน้าสินค้า ⑯) กับ ⑬ (เกรด ⑰/⑱) ใช้ค่าชุดเดียวกันจึงตรงกัน
ไม่เรียก API/LLM - ฟังก์ชันล้วน เทสได้ (tests/test_unit_price_tiers.py) ตัวเลือก config/market_tiers.json ("basis": price | unit_price - ตั้งต้น price จนกว่าเจ้าของงานดูผล dry-run แล้วเปลี่ยน)
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path

import pandas as pd

from category_breakdown import _tier_of, market_price_cuts

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "market_tiers.json"
DEFAULTS = {"basis": "price", "n_tiers": 3, "min_cohort": 30, "mini_ratio": 0.25}
BASES = ("price", "unit_price")

USABLE_FLAGS = ("ok", "bundle_summed")                  # size_flag ที่เชื่อขนาดได้
KIND_OF_UNIT = {"g·ml": "gml", "ชิ้น": "pcs"}           # unit_std ของ Konvy -> ชนิดหน่วย (ASCII)
DIMENSION_LABEL = {"volume": "ml", "mass": "g", "count": "pcs"}   # dimension_orig -> หน่วยที่แสดง (g·ml ผสม/ไม่รู้ -> ml)
PRICE_KIND = "price"                                    # ไม่มีขนาด -> เทียบราคาขาย
SIZE_COLUMNS = ("size_std", "unit_std", "size_flag", "dimension_orig", "EM_L2", "EM_L3", "EM_L4", "sale_price_thb")


def load_config(path=CONFIG_PATH):
    """config/market_tiers.json ซ้อนทับค่าตั้งต้น - ไม่มีไฟล์ = ค่าตั้งต้น; basis ต้องเป็น price / unit_price"""
    cfg = dict(DEFAULTS)
    path = Path(path)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    if cfg["basis"] not in BASES:
        raise ValueError(f"market_tiers basis ต้องเป็น {BASES} (ได้ {cfg['basis']!r})")
    return cfg


def uses_unit_price(cfg=None):
    return (cfg or load_config())["basis"] == "unit_price"


def unit_price_of(price, size, unit_std, size_flag, dimension=""):
    """-> (฿ ต่อหน่วย, ชนิดหน่วย "gml"/"pcs") หรือ (None, None) เมื่อใช้ไม่ได้ (ไม่มีราคา/ขนาด, flag ไม่น่าเชื่อ, หน่วยผสม)"""
    kind = KIND_OF_UNIT.get(unit_std)
    if kind is None or size_flag not in USABLE_FLAGS or dimension == "mixed":
        return None, None
    if price is None or size is None or not price > 0 or not size > 0:
        return None, None
    return price / size, kind


def unit_label_of(kind, dimension=""):
    """ชนิดหน่วย + dimension_orig ของแคตตาล็อก -> หน่วยที่แสดง "ml" / "g" / "pcs" (ไม่มี ฿/หน่วย -> None)"""
    if kind == "pcs":
        return "pcs"
    return DIMENSION_LABEL.get(dimension, "ml") if kind == "gml" else None


def _canonical_tier(t, k, n_tiers):
    """ช่วงที่ t จาก k ช่วงของ cohort -> เลขมาตรฐาน 0..n_tiers-1 (ต่ำสุด = 0, สูงสุด = n_tiers - 1, k = 1 -> กลาง)"""
    if k <= 1:
        return (n_tiers - 1) // 2
    return round(t * (n_tiers - 1) / (k - 1))


def _levels(kind, l2, l3, l4):
    """cohort จากแคบไปกว้าง [(ชื่อระดับ, คีย์)] - ไม่มี L3/L4 (ค่าว่าง) ข้ามระดับนั้น"""
    out = []
    if l4:
        out.append(("L4", (kind, l2, l3 or "", l4)))
    if l3:
        out.append(("L3", (kind, l2, l3)))
    out.append(("L2", (kind, l2)))
    return out


def _pick_level(levels, counts, min_cohort):
    """ระดับแคบสุดที่มีสมาชิก >= min_cohort; ไม่มีระดับไหนถึง -> ระดับกว้างสุด (L2)"""
    for name, key in levels:
        if counts[key] >= min_cohort:
            return name, key
    return levels[-1]


def _population(items):
    """items: [(ตำแหน่งแถว, ค่า, ขนาด หรือ None, [(ระดับ, คีย์), ...])] -> {คีย์ cohort: [(ตำแหน่ง, ค่า, ขนาด)]}
    ทุกสินค้าอยู่ในประชากรของ**ทุกระดับ**ที่ครอบสินค้านั้น (L4 และ L3 และ L2 ของมัน) - เส้นแบ่งของ cohort ที่ขยับไประดับกว้างจึงมาจาก
    ทั้งกลุ่ม ไม่ใช่เฉพาะสินค้าของชนิดเล็กที่ตกมาใช้ระดับนั้น"""
    pop = defaultdict(list)
    for i, v, size, levels in items:
        for _, key in levels:
            pop[key].append((i, v, size))
    return pop


def _cut_lines(mem, n_tiers, mini_ratio):
    """ประชากร [(ตำแหน่ง, ค่า, ขนาด)] -> (เส้นแบ่ง, ขนาดที่ถือเป็นขนาดทดลอง/ซองต่ำกว่านี้ หรือ None)
    ขนาดทดลองไม่นับตอนหาเส้นแบ่ง (เหลือน้อยกว่า n_tiers ชิ้น -> ใช้ทุกชิ้น)"""
    sizes = [s for _, _, s in mem if s is not None]
    mini_below = mini_ratio * statistics.median(sizes) if sizes else None
    base = [v for _, v, s in mem if mini_below is None or s is None or s >= mini_below]
    return market_price_cuts(base if len(base) >= n_tiers else [v for _, v, _ in mem], n_tiers), mini_below


def assign_unit_tiers(rows, n_tiers=DEFAULTS["n_tiers"], min_cohort=DEFAULTS["min_cohort"],
                      mini_ratio=DEFAULTS["mini_ratio"]):
    """rows: [{"price", "size", "unit_std", "size_flag", "dimension", "l2", "l3", "l4"}] (price/size เป็นเลขหรือ None)
    -> [{"unit_price", "unit_kind" (gml/pcs/price/None), "unit_label" (ml/g/pcs หรือ None), "size",
         "unit_tier" (0..n_tiers-1 หรือ None), "tier_basis" (L4/L3/L2 ของ cohort), "cohort_n", "is_mini"}] เรียงตาม rows
    สินค้าไม่มีราคา -> unit_tier None; cohort เล็กกว่า n_tiers ชิ้น (แบ่งไม่ได้) -> unit_tier None"""
    unit = [unit_price_of(r.get("price"), r.get("size"), r.get("unit_std"), r.get("size_flag"), r.get("dimension") or "")
            for r in rows]
    out = [{"unit_price": up, "unit_kind": kind, "unit_label": unit_label_of(kind, r.get("dimension") or ""),
            "size": r.get("size"), "unit_tier": None, "tier_basis": None, "cohort_n": 0, "is_mini": False}
           for r, (up, kind) in zip(rows, unit)]

    # 1) สินค้าที่มี ฿/หน่วย: cohort = (หน่วย, L2, L3, L4) -> (หน่วย, L2, L3) -> (หน่วย, L2) ระดับแคบสุดที่มี >= min_cohort
    items = [(i, up, r["size"], _levels(kind, r["l2"], r.get("l3"), r.get("l4")))
             for i, (r, (up, kind)) in enumerate(zip(rows, unit)) if up is not None]
    pop = _population(items)
    lines = {}
    for i, up, size, levels in items:
        name, key = _pick_level(levels, _Counts(pop), min_cohort)
        if len(pop[key]) < n_tiers:
            continue
        if key not in lines:
            lines[key] = _cut_lines(pop[key], n_tiers, mini_ratio)
        cuts, mini_below = lines[key]
        out[i].update(unit_tier=_canonical_tier(_tier_of(up, cuts), len(cuts) + 1, n_tiers), tier_basis=name,
                      cohort_n=len(pop[key]), is_mini=mini_below is not None and size < mini_below)

    # 2) ไม่มี ฿/หน่วย (ไม่มีขนาด/หน่วยผสม/flag ไม่น่าเชื่อ) -> เทียบราคาขายภายในกลุ่มเดียวกัน (ทุกหน่วยรวมกัน เส้นแบ่งจากทั้งกลุ่ม)
    pitems = [(i, r["price"], None, _levels(PRICE_KIND, r["l2"], r.get("l3"), r.get("l4")))
              for i, r in enumerate(rows) if r.get("price") is not None and r["price"] > 0]
    ppop = _population(pitems)
    plines = {}
    for i, price, _, levels in pitems:
        if unit[i][0] is not None:
            continue
        name, key = _pick_level(levels, _Counts(ppop), min_cohort)
        if len(ppop[key]) < n_tiers:
            continue
        if key not in plines:
            plines[key] = market_price_cuts([v for _, v, _ in ppop[key]], n_tiers)
        cuts = plines[key]
        out[i].update(unit_kind=PRICE_KIND, tier_basis=name, cohort_n=len(ppop[key]),
                      unit_tier=_canonical_tier(_tier_of(price, cuts), len(cuts) + 1, n_tiers))
    return out


class _Counts:
    """{คีย์: จำนวนสมาชิกของประชากร} แบบไม่สร้าง dict ซ้ำทุกแถว - คีย์ที่ไม่มี = 0"""
    def __init__(self, pop):
        self.pop = pop

    def __getitem__(self, key):
        return len(self.pop.get(key, ()))


def _num(v):
    """string มี comma ("1,790.00") / ตัวเลข -> float; อ่านไม่ได้/NaN = None"""
    if v is None or (isinstance(v, float) and v != v):
        return None
    try:
        out = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return None if out != out else out


def catalog_unit_tiers(df, cfg=None):
    """แคตตาล็อก (load_catalog: มี EM_L2/L3/L4 + คอลัมน์ขนาดของ Konvy) -> DataFrame index เดียวกับ df
    คอลัมน์ unit_price, unit_kind, unit_tier, tier_basis, cohort_n, is_mini - แคตตาล็อกที่ไม่มีคอลัมน์ขนาด (Watsons เดิม) -> ValueError"""
    cfg = cfg or load_config()
    missing = [c for c in SIZE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"แคตตาล็อกไม่มีคอลัมน์ขนาด {missing} - ใช้ tool/product/build_konvy_catalog.py สร้าง konvy_product.csv")
    rows = [{"price": _num(p), "size": _num(s), "unit_std": u, "size_flag": f, "dimension": d, "l2": a, "l3": b, "l4": c}
            for p, s, u, f, d, a, b, c in zip(df["sale_price_thb"], df["size_std"], df["unit_std"], df["size_flag"],
                                              df["dimension_orig"], df["EM_L2"], df["EM_L3"], df["EM_L4"])]
    res = assign_unit_tiers(rows, cfg["n_tiers"], cfg["min_cohort"], cfg["mini_ratio"])
    return pd.DataFrame(res, index=df.index)


def tier_records(tiers):
    """🆕 catalog_unit_tiers() -> {index แถวแคตตาล็อก: {unit_tier, unit_price, unit_label, size, is_mini, unit_kind, tier_basis}}
    ค่าว่าง (NaN) เป็น None - ⑫ (score_products) และ ⑬ (build_market_rows) ใช้ติดสินค้าแต่ละชิ้นให้ตรงกัน"""
    def clean(v):
        return None if v is None or (isinstance(v, float) and v != v) else v

    out = {}
    for idx, r in tiers.to_dict("index").items():
        t = clean(r["unit_tier"])
        out[idx] = {"unit_tier": None if t is None else int(t), "unit_price": clean(r["unit_price"]),
                    "unit_label": clean(r["unit_label"]), "size": clean(r["size"]), "is_mini": bool(r["is_mini"]),
                    "unit_kind": clean(r["unit_kind"]), "tier_basis": clean(r["tier_basis"])}
    return out


def market_tiers(df, cfg=None):
    """df (load_catalog) + config -> (records หรือ None, tier_key หรือ None, meta)
    basis "price" -> (None, None, meta) ไม่แตะอะไรเลย; "unit_price" -> records จาก tier_records + tier_key "unit_tier"
    meta = {"tier_basis", "tier_config"} เก็บลงผล ⑫/⑬ ให้รายงาน/backfill รู้ว่าผลนี้แบ่งช่วงด้วยอะไร"""
    cfg = cfg or load_config()
    meta = {"tier_basis": cfg["basis"], "tier_config": {k: cfg[k] for k in ("n_tiers", "min_cohort", "mini_ratio")}}
    if cfg["basis"] != "unit_price":
        return None, None, meta
    return tier_records(catalog_unit_tiers(df, cfg)), "unit_tier", meta
