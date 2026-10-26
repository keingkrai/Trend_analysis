# -*- coding: utf-8 -*-
"""
⑯/⑰ แผนที่ตลาดระดับหมวด L2 (ฝั่งรายงาน) — อ่าน phase3_l2_market_map.json.gz ของรอบ (⑫ เขียน - tool/phase3_supply_layer/l2_market_map.py)
แล้วเทียบ "ความใกล้เทรนด์ x ยอดขาย" โดยใช้หมวดระดับ 2 อย่างเดียวเป็นกลุ่มเทียบ (🆕 2026-10-21 เจ้าของงานสั่ง):
  แกน x = อันดับความใกล้เทรนด์ในหมวด -> 4 ระดับตามเกณฑ์ % เดียวกับ ⑰ (config/brand_report.json > fit_top_pct: top 1/5/20% ของหมวด)
  แกน y = ตำแหน่งยอดขาย Konvy ในหมวดเดียวกัน (ชิ้น x ราคา, ของหมดใช้รีวิว) -> ขายดี / ปานกลาง / ขายช้า / ไม่มีข้อมูล (config > sales)
  เกรดสุดท้าย = ระดับความใกล้เทรนด์ ปรับตามยอดขาย ±1 ขั้น (brand_data.adjust_level - กติกาเดียวกับ ⑰)
⑯ ใช้ l2_grid() (จำนวนสินค้าต่อช่อง + สินค้าที่ใกล้เทรนด์ที่สุดในช่อง) ⑰ ใช้ brand_tier() (สินค้าของแบรนด์ในหมวดเป็น "กลุ่ม" เดียวให้
brand_category_data._fit_sales_map วางจุด)
ฟังก์ชันล้วน อ่านไฟล์ได้อย่างเดียว ไม่เรียก API - เส้นตัดอยู่ที่ config จึงปรับได้โดยไม่รัน ⑫ ใหม่
"""
import gzip
import json
from pathlib import Path

from brand_data import FIT_LEVELS, adjust_level, fit_level, load_config, rank_cuts, sales_state, sales_view

MAP_FILE = "phase3_l2_market_map.json.gz"
CONFIG_FILE = Path(__file__).resolve().parents[2] / "config" / "brand_report.json"
ROWS = ("strong", "steady", "slow", "unknown")
CLOSE_LEVELS = ("excellent", "good")     # "ใกล้เทรนด์" ในบรรทัดสรุป = สองระดับบน (top 5% ของหมวด)


def load_map(run_dir):
    """ไฟล์แผนที่ของรอบ -> dict หรือ None (ไม่มีไฟล์ = รอบที่ยังไม่ได้รัน ⑫ --l2-map-only)"""
    path = Path(run_dir) / MAP_FILE
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def category_products(data, key, trend_name=None):
    """แผนที่ + คีย์เทรนด์ -> (หมวด, [สินค้าเรียงจากใกล้เทรนด์ที่สุด]) หรือ (None, []) ถ้าเทรนด์นี้ไม่มีในไฟล์
    สินค้า = {"brand", "product_name", "sale_price_thb", "size", "unit_label", "rank" (ในหมวด เริ่ม 1), "sales" (รูปเดียวกับ ⑬ - sales_level)}"""
    entry = (data or {}).get("trends", {}).get(key)
    if entry is None and trend_name:
        entry = next((e for e in data.get("trends", {}).values() if e.get("trend_name") == trend_name), None)
    if not entry:
        return None, []
    col = {name: i for i, name in enumerate(data["columns"])}
    products = []
    for rank, i in enumerate(entry["order"], 1):
        r = data["products"][i]
        products.append({"brand": r[col["brand"]], "product_name": r[col["product_name"]], "sale_price_thb": r[col["sale_price_thb"]],
                         "size": r[col["size"]], "unit_label": r[col["unit_label"]], "rank": rank,
                         "sales": {"pct": r[col["sales_pct"]], "basis": r[col["sales_basis"]], "soldout": bool(r[col["soldout"]]),
                                   "zero": bool(r[col["zero"]]), "sold": r[col["sold"]], "value": None, "reviews": r[col["reviews"]]}})
    return entry.get("category"), products


def _pct(k, n):
    return round(k / n * 100) if n else 0


def l2_grid(products, cfg=None, make_product=None):
    """สินค้าของหมวด (category_products) -> ตารางความใกล้ x ยอดขาย:
    {"n", "cuts" (fit_top_pct), "sales" (strong_top_pct / slow_bottom_pct),
     "cols": [{"level", "n"}] 4 ระดับ, "rows": [{"state", "n"}] 4 แถว,
     "cells": {"<แถว>|<ระดับ>": {"n", "product"}}  product = สินค้าที่ใกล้เทรนด์ที่สุดในช่อง (+ level / base_level / rank / sales) หรือ None (n ใช้แค่คิดบรรทัดสรุป - หน้ารายงานไม่แสดงจำนวนต่อช่อง),
     "take": {"n_close", "close_pct", "strong_close", "slow_close", "strong_all", "slow_all"}} (เปอร์เซ็นต์เป็นจำนวนเต็ม)
    make_product(dict) -> dict ของสินค้าสำหรับเทมเพลต (report_data._product เติมรูป/ชื่อเต็ม) ไม่ส่ง = ใช้ dict เดิม"""
    cfg = cfg or load_config(CONFIG_FILE)
    top_pct, scfg = cfg["fit_top_pct"], cfg["sales"]
    n = len(products)
    cuts = rank_cuts(n, top_pct) if n else {}
    cells = {f"{r}|{lv}": {"n": 0, "product": None} for r in ROWS for lv in FIT_LEVELS}
    for p in products:
        fit = fit_level(p["rank"], cuts)
        state = sales_state(p["sales"], scfg)
        c = cells[f"{state}|{fit}"]
        c["n"] += 1
        # ตัวแทนทุกช่อง 4 ระดับ x 3 แถวยอดขาย (🆕 2026-10-21 เจ้าของงานสั่งให้ทุกช่องแสดงแต่สินค้า ไม่บอกจำนวน และเอาแถว "ไม่มีข้อมูลยอดขาย" ออก - สินค้าที่ไม่มีข้อมูลยอดขายจึงไม่ถูกแสดง)
        if c["product"] is None and state != "unknown":
            base = {k: p[k] for k in ("brand", "product_name", "sale_price_thb", "size", "unit_label")}
            item = make_product({**base, "category": ""}) if make_product else dict(base)
            item.update(rank=p["rank"], base_level=fit, level=adjust_level(fit, state), sales=sales_view(p["sales"], state))
            c["product"] = item
    col_tot = {lv: sum(cells[f"{r}|{lv}"]["n"] for r in ROWS) for lv in FIT_LEVELS}
    row_tot = {r: sum(cells[f"{r}|{lv}"]["n"] for lv in FIT_LEVELS) for r in ROWS}
    n_close = sum(col_tot[lv] for lv in CLOSE_LEVELS)
    close = lambda r: sum(cells[f"{r}|{lv}"]["n"] for lv in CLOSE_LEVELS)  # noqa: E731
    return {"n": n, "cuts": dict(top_pct), "sales": {"strong_top_pct": scfg["strong_top_pct"], "slow_bottom_pct": scfg["slow_bottom_pct"]},
            "cols": [{"level": lv, "n": col_tot[lv]} for lv in FIT_LEVELS], "rows": [{"state": r, "n": row_tot[r]} for r in ROWS],
            "cells": cells,
            "take": {"n_close": n_close, "close_pct": top_pct["good"], "strong_close": _pct(close("strong"), n_close),
                     "slow_close": _pct(close("slow"), n_close), "strong_all": _pct(row_tot["strong"], n), "slow_all": _pct(row_tot["slow"], n)}}


def brand_tier(products, brand):
    """สินค้าของหมวด + ชื่อแบรนด์ -> "กลุ่ม" หน้าตาเดียวกับ tiers[] ของ ⑬ category_fit ที่ brand_category_data._fit_sales_map / brand_data.best_in_tier ใช้:
    {"n_total" (สินค้าทั้งหมวด), "n_brand", "top": [], "brand_products": [สินค้าของแบรนด์ทุกชิ้น + rank_in_tier = อันดับในหมวด]} - ไม่มีสินค้าของแบรนด์ = None"""
    mine = [{"brand": p["brand"], "product_name": p["product_name"], "sale_price_thb": p["sale_price_thb"], "size": p["size"],
             "unit_label": p["unit_label"], "rank_in_tier": p["rank"], "rank_in_market": None, "sales": p["sales"]}
            for p in products if p["brand"] == brand]
    return {"n_total": len(products), "n_brand": len(mine), "top": [], "brand_products": mine} if mine else None


def l2_category_fit(fit, products, brand, reasons=None):
    """🆕 (2026-10-21) category_fit ของ ⑬ (เทรนด์ -> หมวด -> ช่วงราคา -> สินค้า) -> แบบหมวด L2 อย่างเดียว (เจ้าของงานสั่งให้เกรดทั้ง ⑰ และ Excel ของ ⑬ เทียบในหมวด
    ไม่แยกช่วงราคา): แต่ละหมวดมี "ช่วงราคา" เดียว label "all" = ทั้งหมวด -> ฟังก์ชันเกรดเดิมทุกตัว (brand_data.best_in_category / grade_product / trend_categories
    และ Excel ของ ⑬) ใช้ต่อได้โดยไม่แก้: n_total = สินค้าทั้งหมวด, top = 5 อันดับแรกของหมวด, brand_products = สินค้าของแบรนด์ทุกชิ้นในหมวด
    (rank_in_tier = อันดับในหมวด, sales = ยอดขายเทียบทั้งหมวด จากแผนที่ ⑫) - ช่องอื่น (similarity / ขนาด / ฿ต่อหน่วย / อันดับทั้งตลาด / เหตุผลจับคู่) ยืมจากสินค้า
    ชิ้นเดียวกันใน category_fit เดิม (top 5 ของหมวดและสินค้าของแบรนด์ทุกชิ้นอยู่ในรายการของช่วงราคาใดช่วงหนึ่งเสมอ) ผลมีธง "group_basis": "l2"
    products = category_products() ของเทรนด์นั้น; ไม่แตะ fit เดิม"""
    categories = []
    for c in fit.get("categories") or []:
        look = {}
        for m in [c.get("brand_best") or {}] + [x for t in c.get("tiers") or [] for x in (t.get("brand_products") or []) + (t.get("top") or [])]:
            if m.get("product_name"):
                look.setdefault((m.get("brand"), m["product_name"]), m)

        def merged(p, look=look):
            base = dict(look.get((p["brand"], p["product_name"])) or {"brand": p["brand"], "product_name": p["product_name"],
                                                                     "sale_price_thb": p["sale_price_thb"], "similarity": None})
            for k in ("n_tier", "tier", "price_from", "price_to"):   # ช่องของ brand_best ระดับหมวดเดิม (ไม่ใช่ของสินค้า)
                base.pop(k, None)
            base.update(rank_in_tier=p["rank"], sales=p["sales"])
            if not base.get("match_reason") and (reasons or {}).get(p["product_name"]):   # เหตุผลที่ ⑬ --l2-reasons-only เขียนให้สินค้าที่ให้เกรดแบบหมวด L2
                base["match_reason"] = reasons[p["product_name"]]
            return base

        n = len(products)
        mine = [merged(p) for p in products if p["brand"] == brand]
        tier = {"label": "all", "price_from": None, "price_to": None, "n_total": n, "n_brand": len(mine),
                "top": [merged(p) for p in products[:5]], "brand_products": mine, "brand_best": mine[0] if mine else None}
        categories.append({"category": c["category"], "n_total": n, "n_brand": len(mine), "tiers": [tier] if n else [],
                           "brand_best": {**mine[0], "n_tier": n, "tier": "all", "price_from": None, "price_to": None} if mine else None})
    return {**fit, "categories": categories, "group_basis": "l2"}


def l2_coverage(coverage, l2_data):
    """ผล ⑬ ของ 1 แบรนด์ (dict จากไฟล์ phase3_brand_coverage_<แบรนด์>.json) -> สำเนาที่ category_fit ของทุกเทรนด์เป็นแบบหมวด L2 อย่างเดียว (l2_category_fit)
    เทรนด์ที่ไม่มีในแผนที่ / หมวดไม่ตรงกับหมวดหลักของ ⑬ คง category_fit เดิมไว้ (รายชื่ออยู่ใน "_l2_skipped" ให้ผู้เรียกเตือน) - ไม่แตะ coverage เดิม
    ไม่มีแผนที่ (None) = คืนของเดิม"""
    if not l2_data:
        return coverage
    brand = coverage.get("brand") or ""
    out, skipped = {}, []
    for key, c in (coverage.get("coverage") or {}).items():
        fit = c.get("category_fit")
        if fit and fit.get("categories"):
            cat, products = category_products(l2_data, key, c.get("trend_name"))
            if products and cat == fit.get("main_category"):
                c = {**c, "category_fit": l2_category_fit(fit, products, brand, c.get("l2_reasons"))}
            else:
                skipped.append(c.get("trend_name") or key)
        out[key] = c
    return {**coverage, "coverage": out, "_l2_skipped": skipped}
