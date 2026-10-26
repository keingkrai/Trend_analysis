# -*- coding: utf-8 -*-
"""
⑱ รายงานหมวด × ระดับราคา PDF — ชั้นข้อมูล: ผล ⑬ ของ 1 แบรนด์ (coverage[เทรนด์]["price_tiers"] จาก price_tiers.py) + ข้อมูลเทรนด์
ชุดเดียวกับรายงานเทรนด์ (⑯) -> category context

🆕 (2026-10-07) ใช้ category_fit ของ ⑬ ชุดเดียวกับเกรดใน ⑰: เทรนด์ -> หมวด -> ช่วงราคาตลาด (ต่ำ/กลาง/สูง ช่วงเดียวกับ ⑯)
-> top 5 ของกลุ่ม + สินค้าที่ดีที่สุดของแบรนด์ + เกรด - ⑰ เป็นสรุป ⑱ เป็นรายละเอียดทุกกลุ่ม (เดิม: หมวดหลักหมวดเดียว x ช่วงราคา
ที่แบ่งจากราคาสินค้าของแบรนด์เอง จาก price_tiers - เลิกใช้ในรายงานแล้ว)
ไม่ import bootstrap และไม่เรียก API (เทสได้ด้วยข้อมูลปลอม) - ใช้ตัวช่วยของ ⑰ ซ้ำ (หา/โหลดไฟล์ ⑬, แคตตาล็อก, รูปสินค้า)
"""
import copy

from brand_data import (DEFAULT_CONFIG, FIT_LEVELS, SHORT_IDX, _CatalogIndex, _grade_fields, _price,  # noqa: F401  (ส่งต่อให้สคริปต์)
                        best_in_tier, find_coverage_file, fit_level, grade_product, list_coverage_files, load_catalog, load_config, sales_state, sales_view,
                        rank_cuts, safe_file_part, tier_products)
from l2_map import brand_tier, category_products
from report_data import read_json, strip_thai  # noqa: F401

STATUS_OK, STATUS_NO_BRAND, STATUS_NO_TIERS, STATUS_UNCHECKED = "ok", "no_brand", "no_tiers", "unchecked"


TIER_LABELS = {0: "low", 1: "mid", 2: "high"}
RANGE_LOW_Q, RANGE_HIGH_Q = 0.10, 0.90          # ช่วงที่แสดง = ที่สินค้า 80% ของกลุ่มอยู่ (ตัดถูกสุด/แพงสุดฝั่งละ 10%)
MIN_RANGE_ITEMS = 5                             # กลุ่มที่มีสินค้ามีหน่วยน้อยกว่านี้ ไม่แสดงช่วง (ตัวเลขไม่นิ่ง)


def group_ranges(rows):
    """rows: DataFrame (หรือรายการ dict) ที่มีคอลัมน์ EM_L2 / unit_tier (0..2 หรือว่าง) / unit_kind (gml|pcs|price) / unit_label (ml|g|pcs) /
    unit_price / is_mini -> {(หมวด L2, "low"|"mid"|"high"): {"unit_label", "p10", "p50", "p90", "n"}}

    กลุ่ม = หมวด x ช่วงราคาต่อปริมาณ (เลขช่วงของสินค้าแต่ละชิ้นคิดภายในชนิดสินค้าของมันเอง - unit_price_tiers.py) จึง**ไม่มีเส้นแบ่งเดียวต่อกลุ่ม**
    ช่วงของกลุ่มต่างๆ ซ้อนกันได้เมื่อหมวดมีหลายชนิดสินค้า ตัวเลขที่แสดงคือ P10-P90 ของ ฿ ต่อหน่วย + ค่ากลาง ไม่นับขนาดทดลอง/ซอง
    ต่อกลุ่มใช้เฉพาะหน่วยที่พบมากสุด (ml/g นับรวมเป็น "ml_g" เมื่อแต่ละหน่วย >= 25% ของ ml+g - เหมือนหน้า ⑯; ชิ้นแยกเป็นอีกหน่วย)"""
    import pandas as pd

    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    need = {"EM_L2", "unit_tier", "unit_kind", "unit_label", "unit_price", "is_mini"}
    if df.empty or not need <= set(df.columns):
        return {}
    df = df[df["unit_tier"].notna() & df["unit_price"].notna() & df["unit_kind"].isin(["gml", "pcs"]) & ~df["is_mini"].astype(bool)]
    out = {}
    for (cat, tier), g in df.groupby(["EM_L2", "unit_tier"]):
        label = TIER_LABELS.get(int(tier))
        if label is None or not len(g):
            continue
        counts = g["unit_label"].value_counts()
        vol_mass = counts.get("ml", 0) + counts.get("g", 0)
        if vol_mass and counts.get("ml", 0) >= 0.25 * vol_mass and counts.get("g", 0) >= 0.25 * vol_mass and vol_mass >= counts.get("pcs", 0):
            unit, use = "ml_g", g[g["unit_label"].isin(["ml", "g"])]
        else:
            unit = str(counts.index[0])
            use = g[g["unit_label"] == unit]
        if len(use) < MIN_RANGE_ITEMS:
            continue
        v = use["unit_price"].astype(float)
        out[(str(cat), label)] = {"unit_label": unit, "n": int(len(use)), "p50": float(v.median()),
                                  "p10": float(v.quantile(RANGE_LOW_Q)), "p90": float(v.quantile(RANGE_HIGH_Q))}
    return out


def load_group_ranges(csv_path):
    """แคตตาล็อกจริง (Konvy) -> group_ranges ของทั้งตลาด (ชุดช่วงราคาเดียวกับที่ ⑫/⑬ ใช้ - unit_price_tiers.catalog_unit_tiers)
    ใช้ไม่ได้ (ไม่มีไฟล์/ไม่มีคอลัมน์ขนาด) -> {} ผู้เรียกแสดงหน้าโดยไม่มีช่วง"""
    import sys
    from pathlib import Path

    if not csv_path or not Path(csv_path).exists():
        return {}
    tool_dir = Path(__file__).resolve().parents[1]
    for d in (tool_dir, tool_dir / "phase3_supply_layer"):
        if str(d) not in sys.path:
            sys.path.insert(0, str(d))
    try:
        from product.euromonitor_mapping import load_catalog as load_beauty_catalog
        from unit_price_tiers import catalog_unit_tiers, load_config, uses_unit_price

        if not uses_unit_price(load_config()):
            return {}
        df = load_beauty_catalog(csv_path, beauty_only=True,
                                 usecols=["sale_price_thb", "size_std", "unit_std", "size_flag", "dimension_orig"])
        tiers = catalog_unit_tiers(df)
    except (ValueError, KeyError, ImportError):
        return {}
    return group_ranges(df[["EM_L2"]].join(tiers))


def category_portfolio(catalog, brand, top=4):
    """สินค้าของแบรนด์บน Konvy แยกตามหมวด L2: [{"name", "n", "price_min", "price_max"}] เรียงจากมากไปน้อย (เฉพาะ `top` หมวดแรก)"""
    rows = catalog[catalog["brand"] == brand]
    out = []
    for name, grp in rows.groupby("EM_L2"):
        prices = [p for p in (_price(v) for v in grp["sale_price_thb"]) if p]
        out.append({"name": str(name), "n": int(len(grp)), "price_min": min(prices) if prices else None,
                    "price_max": max(prices) if prices else None})
    return sorted(out, key=lambda r: -r["n"])[:top]


def _item(p, index, brand=None):
    """สินค้าจาก category_fit -> dict ที่เทมเพลตใช้ (ชื่อภาษาอังกฤษ + ชื่อเต็ม, ราคา, รูปจากแคตตาล็อก, is_you = สินค้าของแบรนด์ลูกค้า)"""
    cat = index.pair(p.get("brand"), p.get("product_name"))
    return {**p, "name": strip_thai(p.get("product_name")) or p.get("product_name"), "name_full": p.get("product_name"),
            "brand_label": strip_thai(p.get("brand")) or p.get("brand"), "price_thb": p.get("sale_price_thb"),
            "image_url": cat.get("image_url"), "is_you": bool(brand) and p.get("brand") == brand}


def _fit_sales_map(tier, index, brand, top_pct, scfg, best):
    """🆕 (2026-10-21) ข้อมูลกราฟ "ความใกล้เทรนด์ x ยอดขาย" ของ 1 กลุ่ม (วาดโดย fit_sales_map.render_svg): จุด = สินค้าของแบรนด์ทุกชิ้นในกลุ่ม
    (เจ้าของงานสั่งเอา top 5 ของตลาดออกจากกราฟ - ยังเห็นในหน้า 2 ของเทรนด์), ตำแหน่งในช่อง (fx = ซ้ายไปขวาตามอันดับในช่องระดับ,
    fy = ล่างขึ้นบนตามเปอร์เซ็นไทล์ยอดขายในแถว), จำนวนสินค้าของแบรนด์ต่อช่อง, จำนวนต่อโซน และสินค้าไฮไลต์ A/B/C ใต้กราฟ:
      A = ชิ้นที่ให้เกรดของกลุ่ม (best_in_tier) · B = ใกล้เทรนด์ (Excellent/Good) แต่ยอดขายไม่ถึงขายดี - ชิ้นที่ใกล้ที่สุด
      C = ขายดีแต่ห่างเทรนด์ (ไม่ถึง top 20% ของกลุ่ม) - ชิ้นที่ยอดขายสูงสุด
    ไม่มีสินค้าในกลุ่ม (n_total = 0) หรือแบรนด์ไม่มีสินค้าในกลุ่มนี้ -> None"""
    n = tier.get("n_total") or 0
    if not n:
        return None
    cuts = rank_cuts(n, top_pct)
    bounds, lo = {}, 1
    for lv in FIT_LEVELS:   # ช่วงอันดับของแต่ละช่องระดับ (ช่องสุดท้าย = ที่เหลือถึงอันดับ n)
        hi = cuts.get(lv, n)
        bounds[lv] = (lo, hi)
        lo = hi + 1
    s_hi, s_lo = 1 - scfg["strong_top_pct"] / 100, scfg["slow_bottom_pct"] / 100

    entries = [{"p": p, "key": (p.get("brand"), p.get("product_name")), "g": grade_product(p, n, top_pct, scfg)}
               for p in tier_products(tier)]
    if not entries:
        return None
    mine = entries

    chosen = {}
    if best:
        chosen["A"] = next((e for e in mine if e["p"]["product_name"] == best["raw"].get("product_name")), None)
    lag = [e for e in mine if e["g"]["base"] in ("excellent", "good") and e["g"]["state"] in ("steady", "slow")
           and e not in chosen.values()]
    chosen["B"] = min(lag, key=lambda e: e["p"]["rank_in_tier"]) if lag else None
    off = [e for e in mine if e["g"]["base"] == "below_average" and e["g"]["state"] == "strong"
           and e not in chosen.values()]   # ชิ้นที่เป็น A อยู่แล้วไม่ซ้ำเป็น C
    chosen["C"] = max(off, key=lambda e: (e["p"].get("sales") or {}).get("pct") or 0) if off else None
    chosen = {k: e for k, e in chosen.items() if e}
    letter = {e["key"]: k for k, e in chosen.items()}

    dots, cells = [], {}
    zones = {"close_strong": 0, "close_lag": 0, "off_strong": 0}
    for e in entries:
        p, g = e["p"], e["g"]
        sa = p.get("sales") or {}
        pct = sa.get("pct") if isinstance(sa.get("pct"), (int, float)) else None
        lo_r, hi_r = bounds[g["base"]]
        fx = 1 - (p["rank_in_tier"] - lo_r + 0.5) / (hi_r - lo_r + 1)
        draw_state = g["state"]
        if g["state"] == "unknown":
            # 🆕 (2026-10-21) เอาแถบ "ไม่มีข้อมูลยอดขาย" ออกจากกราฟ (เจ้าของงานสั่ง): สินค้าที่ไม่มีข้อมูลยอดขายวาดกลางแถวปานกลาง - เกรดคิดเหมือนปานกลางอยู่แล้ว
            # (ไม่มีข้อมูล = ยอดขายไม่เปลี่ยนระดับ) หมายเหตุท้ายหน้าบอกไว้
            draw_state, fy = "steady", 0.5
        elif g["state"] == "strong":
            fy = (pct - s_hi) / (1 - s_hi)
        elif g["state"] == "steady":
            fy = (pct - s_lo) / (s_hi - s_lo)
        else:
            fy = 0.0 if sa.get("zero") or pct is None else pct / s_lo
        dots.append({"fit": g["base"], "state": draw_state, "fx": min(max(fx, 0.0), 1.0),
                     "fy": min(max(fy, 0.0), 1.0), "letter": letter.get(e["key"])})
        cells[f"{g['state']}|{g['base']}"] = cells.get(f"{g['state']}|{g['base']}", 0) + 1
        close = g["base"] in ("excellent", "good")
        zones["close_strong"] += close and g["state"] == "strong"
        zones["close_lag"] += close and g["state"] in ("steady", "slow")
        zones["off_strong"] += g["base"] == "below_average" and g["state"] == "strong"
    callouts = [{**_item(e["p"], index, brand), "kind": k, "pct": e["p"]["rank_in_tier"] / n * 100, **_grade_fields(e["g"], e["p"])}
                for k, e in sorted(chosen.items())]
    return {"dots": dots, "cells": cells, "zones": zones, "callouts": callouts, "n_mine": len(mine),
            "cuts": top_pct, "sales": {"strong_top_pct": scfg["strong_top_pct"], "slow_bottom_pct": scfg["slow_bottom_pct"]}}


def _tier_view(tier, index, brand, top_pct, unit_range=None, scfg=None):
    """1 กลุ่ม (หมวด x ช่วงราคาตลาด) -> top N + สินค้าที่ดีที่สุดของแบรนด์พร้อม % แรกในกลุ่มและเกรด (เกณฑ์เดียวกับ ⑰)
    unit_range = group_ranges ของกลุ่มนี้ (ช่วง ฿/หน่วยที่สินค้า 80% ของกลุ่มอยู่) หรือ None
    🆕 (2026-10-19) สินค้าที่ดีที่สุด = ชิ้นที่เกรดหลังปรับยอดขาย Konvy ดีที่สุด (brand_data.best_in_tier) ไม่ใช่ชิ้นที่ใกล้เทรนด์ที่สุดเสมอไป"""
    scfg = scfg or DEFAULT_CONFIG["sales"]
    n_tier = tier.get("n_total") or 0
    tb = best_in_tier(tier, top_pct, scfg) if n_tier else None
    best = None
    if tb:
        raw = tb["raw"]
        best = {**_item(raw, index, brand), "pct": raw["rank_in_tier"] / n_tier * 100, **_grade_fields(tb, raw)}
    return {"label": tier["label"], "price_from": tier.get("price_from"), "price_to": tier.get("price_to"),
            "n_total": n_tier, "n_brand": tier.get("n_brand", 0),
            "top": [{**_item(x, index, brand), "sales": sales_view(x.get("sales"), sales_state(x.get("sales"), scfg))} for x in tier.get("top") or []],
            "brand_best": best, "unit_range": unit_range}


def _l2_view(l2_data, t, brand, index, top_pct, scfg):
    """🆕 (2026-10-21) หน้าที่ 3 ของเทรนด์ใน ⑰ = แผนที่ "ความใกล้เทรนด์ x ยอดขาย" ระดับหมวด L2 อย่างเดียว (เจ้าของงานสั่ง - ไม่แยกช่วงราคา): สินค้าของแบรนด์ทุกชิ้น
    ในหมวดหลักของเทรนด์ถูกวางตามอันดับความใกล้เทรนด์ในหมวด x ยอดขาย Konvy เทียบสินค้าในหมวดเดียวกัน (l2_map.py - ข้อมูลจาก ⑫ --l2-map-only)
    -> {"category", "n_total" (สินค้าทั้งหมวด), "n_brand", "map" (_fit_sales_map)} หรือ None (รอบที่ไม่มีไฟล์แผนที่ / เทรนด์นี้ไม่มีในไฟล์ / แบรนด์ไม่มีสินค้าในหมวด)
    ⚠️ เกรดในหน้านี้เทียบกับทั้งหมวด จึงอาจต่างจากเกรดหน้า 1-2 ของเทรนด์ (เทียบในกลุ่มหมวด x ช่วงราคาต่อปริมาณ) - หมายเหตุท้ายหน้าบอกไว้"""
    cat, products = category_products(l2_data, t["key"], t["name"])
    tier = brand_tier(products, brand) if products else None
    if tier is None:
        return None
    return {"category": cat, "n_total": tier["n_total"], "n_brand": tier["n_brand"],
            "map": _fit_sales_map(tier, index, brand, top_pct, scfg, best_in_tier(tier, top_pct, scfg))}


def _category_page(cat, index, brand, top_pct, ranges=None, scfg=None):
    """หมวดหลักของเทรนด์ (category_fit) -> ข้อมูล 1 หน้า: 3 ช่วงราคาตลาด + ชิ้นที่ดีที่สุดของแบรนด์ในหมวด
    ranges = group_ranges ของตลาด (ส่งมาเมื่อผล ⑬ แบ่งช่วงด้วยราคาต่อปริมาณ)"""
    tiers = [_tier_view(t, index, brand, top_pct, (ranges or {}).get((cat["category"], t["label"])), scfg) for t in cat.get("tiers") or []]
    bests = [(t, t["brand_best"]) for t in tiers if t["brand_best"]]
    tier, best = min(bests, key=lambda x: (FIT_LEVELS.index(x[1]["level"]), x[1]["pct"], x[1]["rank_in_tier"]),
                     default=(None, None))
    return {"category": cat["category"], "n_total": cat.get("n_total"), "brand_n": cat.get("n_brand", 0),
            "tiers": tiers, "best": best, "best_tier": tier, "level": best["level"] if best else None}


def build_category_context(trend_ctx, coverage, catalog, cfg=None, ranges=None, l2_data=None):
    """ผล ⑬ ของ 1 แบรนด์ (dict จาก phase3_brand_coverage_<แบรนด์>.json) + trend_ctx (report_data.build_context ที่เติมข้อความแล้ว)
    -> category context ที่เทมเพลตใช้ (serialize เป็น JSON ได้ ยกเว้นช่อง "trend" ที่เป็น dict เทรนด์เต็ม)
    🆕 (2026-10-07) เทรนด์ -> หมวด -> ช่วงราคาตลาด -> สินค้า (category_fit ของ ⑬ - ชุดเดียวกับเกรดใน ⑰) แต่ละช่วงราคามีเกรดของแบรนด์
    🆕 (2026-10-08) หมวดของเทรนด์ = หมวดหลักหมวดเดียวที่ LLM เลือก (ไม่นับหมวดควบคู่) เทรนด์ละ 1 หน้า"""
    cfg = cfg or DEFAULT_CONFIG
    top_pct = cfg["fit_top_pct"]
    brand = coverage.get("brand") or ""
    index = _CatalogIndex(catalog)
    by_key = coverage.get("coverage") or {}
    by_name = {v.get("trend_name"): v for v in by_key.values()}

    rows = []
    for t in trend_ctx["trends"]:
        c = by_key.get(t["key"]) or by_name.get(t["name"])
        g = t.get("growth") or {}
        row = {"trend": t, "rank": t["rank"], "name": t["name"], "display_name": t.get("display_name") or t["name"],
               "expected_pct": ((g.get("forecast_pct") or []) + [None] * 2)[SHORT_IDX],
               "past_growth_pct": g.get("past_growth_pct"), "status": STATUS_UNCHECKED, "pages": []}
        fit = (c or {}).get("category_fit")
        if c and fit and fit.get("main_category") and fit.get("categories"):
            row["pages"] = [_category_page(x, index, brand, top_pct, ranges if fit.get("tier_basis") == "unit_price" else None,
                                           cfg.get("sales") or DEFAULT_CONFIG["sales"])
                            for x in fit["categories"]]
            row["status"] = STATUS_OK if any(pg["brand_n"] for pg in row["pages"]) else STATUS_NO_BRAND
        elif c:
            row["status"] = STATUS_NO_TIERS   # ผล ⑬ รอบเก่า (ไม่มี category_fit หรือยังเป็นแบบหลายหมวดก่อน 2026-10-08) - เติมด้วย run_brand_coverage.py --category-fit-only
        # 🆕 (2026-10-21) หน้าที่ 3 = แผนที่ความใกล้เทรนด์ x ยอดขายระดับหมวด L2 (l2_data = l2_map.load_map ของรอบ; ไม่ส่ง = ไม่มีหน้านี้)
        row["l2"] = _l2_view(l2_data, t, brand, index, top_pct, cfg.get("sales") or DEFAULT_CONFIG["sales"]) if l2_data and c else None
        rows.append(row)

    ok = [r for r in rows if r["status"] == STATUS_OK]
    # จุดแข็งที่สุด = กลุ่ม (หมวด x ช่วงราคา ข้ามทุกเทรนด์) ที่สินค้าของแบรนด์ได้เกรดดีที่สุด แล้ว % แรกในกลุ่มน้อยที่สุด
    strongest = None
    for r in ok:
        for pg in r["pages"]:
            for tr in pg["tiers"]:
                bb = tr["brand_best"]
                if bb and (strongest is None or (FIT_LEVELS.index(bb["level"]), bb["pct"], bb["rank_in_tier"])
                           < (FIT_LEVELS.index(strongest["level"]), strongest["pct"], strongest["rank_in_tier"])):
                    strongest = {"rank": r["rank"], "name": r["name"], "display_name": r["display_name"], "category": pg["category"], "tier_label": tr["label"],
                                 "price_from": tr["price_from"], "price_to": tr["price_to"], "n_tier": tr["n_total"],
                                 "pct": bb["pct"], "rank_in_tier": bb["rank_in_tier"], "product": bb["name"],
                                 "level": bb["level"]}
    fits = [(c or {}).get("category_fit") for c in by_key.values()]
    fits = [f for f in fits if f]
    # 🆕 (2026-10-12) ช่วงราคาของรอบนี้แบ่งด้วยอะไร - ราคาต่อปริมาณเมื่อทุกเทรนด์ที่ตรวจแล้วใช้ (ผลรอบเก่าไม่มี = ราคาขาย)
    tier_basis = "unit_price" if fits and all(f.get("tier_basis") == "unit_price" for f in fits) else "price"
    group_basis = "l2" if fits and all(f.get("group_basis") == "l2" for f in fits) else "tier"   # 🆕 (2026-10-21) กลุ่มเทียบ = หมวด L2 อย่างเดียว (l2_map.l2_coverage)
    return {
        "brand": brand,
        "tier_basis": tier_basis,
        "group_basis": group_basis,
        "n_skus": coverage.get("n_skus"),
        "n_market": next((c.get("category_fit", {}).get("n_market") for c in by_key.values() if c.get("category_fit")),
                         trend_ctx["meta"].get("n_products_compared")),
        "portfolio": {"n_skus": int((catalog["brand"] == brand).sum()), "categories": category_portfolio(catalog, brand)},
        "top_pct": top_pct,
        "rows": rows,
        "n_checked": sum(1 for r in rows if r["status"] in (STATUS_OK, STATUS_NO_BRAND)),
        "n_ok": len(ok),
        "n_pages": sum(len(r["pages"]) for r in rows),
        # ตารางภาพรวม: 1 แถว = เทรนด์ x หมวด (เทรนด์ที่ไม่ได้ตรวจ 1 แถว) - เทมเพลตแบ่งหน้าละ 10 แถว
        "overview": [{"rank": r["rank"], "name": r["name"], "display_name": r["display_name"], "status": r["status"], "page": pg, "first": i == 0}
                     for r in rows for i, pg in enumerate(r["pages"] or [None])],
        "highlights": {"strongest": strongest, "no_brand": [r["display_name"] for r in rows if r["status"] == STATUS_NO_BRAND]},
        "missing_tiers": [r["display_name"] for r in rows if r["status"] in (STATUS_NO_TIERS, STATUS_UNCHECKED)],
    }


def apply_th(bctx):
    """ฉบับไทย: ชื่อสินค้าเต็ม (มีภาษาไทย) ของทุกชิ้นในรายงาน - คืนสำเนาใหม่"""
    out = copy.deepcopy(bctx)
    for p in image_items(out) + [x for r in out["rows"] for pg in r["pages"] for t in pg["tiers"] for x in t["top"]]:
        p["name"] = p.get("name_full") or p["name"]
    if out["highlights"].get("strongest"):
        hs = out["highlights"]["strongest"]
        match = next((bb for r in out["rows"] if r["rank"] == hs["rank"] for pg in r["pages"] for t in pg["tiers"]
                      for bb in [t["brand_best"]] if bb and pg["category"] == hs["category"] and t["label"] == hs["tier_label"]), None)
        if match:
            hs["product"] = match["name"]
    return out


def image_items(bctx):
    """สินค้าที่ต้องมีรูปในรายงาน: สินค้าที่ดีที่สุดของแบรนด์ในแต่ละหมวด (ปก) และในแต่ละช่วงราคา (top 5 เป็นตัวหนังสือล้วน)
    + 🆕 (2026-10-21) สินค้าไฮไลต์ A/B/C ใต้กราฟ "ความใกล้เทรนด์ x ยอดขาย"
    - อาจซ้ำชิ้นเดียวกัน (ชิ้นที่ดีที่สุดของหมวดคือชิ้นที่ดีที่สุดของช่วงราคาหนึ่ง) แต่เป็นคนละ dict"""
    items = []
    for r in bctx["rows"]:
        for pg in r["pages"]:
            items += ([pg["best"]] if pg["best"] else []) + [t["brand_best"] for t in pg["tiers"] if t["brand_best"]]
        items += ((r.get("l2") or {}).get("map") or {}).get("callouts") or []
    return items
