# -*- coding: utf-8 -*-
"""
⑯/⑰ แผนที่ตลาดระดับหมวด L2 (ฝั่งรายงาน) — อ่าน phase3_l2_market_map.json.gz ของรอบ (⑫ เขียน - tool/phase3_supply_layer/l2_market_map.py)
แล้วจัดอันดับ "ความใกล้เทรนด์" โดยใช้หมวดระดับ 2 อย่างเดียวเป็นกลุ่มเทียบ (🆕 2026-10-21 เจ้าของงานสั่ง):
  อันดับความใกล้เทรนด์ในหมวด -> 4 ระดับตามเกณฑ์ % เดียวกับ ⑰ (config/brand_report.json > fit_top_pct: top 1/5/20% ของหมวด)
🆕 (2026-10-27) ตัดยอดขาย Konvy ออกทั้งหมด (เจ้าของงานสั่ง - เกรดใช้ความใกล้เทรนด์ล้วน ใช้ได้กับสินค้านอก Konvy): ตารางของ ⑯ เหลือแถวเดียว 4 ช่อง
และ ⑰ ไม่มีหน้าแผนที่ ความใกล้ x ยอดขายอีก (โค้ดเดิมอยู่ใน output/_backups/sales_removal_code_20261027)
⑯ ใช้ l2_grid() (จำนวนสินค้าต่อระดับ + สินค้าที่ใกล้เทรนด์ที่สุดในระดับ) ⑰ ใช้ brand_tier() (สินค้าของแบรนด์ในหมวดเป็น "กลุ่ม" เดียว)
ฟังก์ชันล้วน อ่านไฟล์ได้อย่างเดียว ไม่เรียก API - เส้นตัดอยู่ที่ config จึงปรับได้โดยไม่รัน ⑫ ใหม่
"""
import gzip
import json
from pathlib import Path

from brand_data import FIT_LEVELS, fit_level, load_config, rank_cuts

MAP_FILE = "phase3_l2_market_map.json.gz"
CONFIG_FILE = Path(__file__).resolve().parents[2] / "config" / "brand_report.json"
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
    สินค้า = {"brand", "product_name", "sale_price_thb", "size", "unit_label", "rank" (ในหมวด เริ่ม 1)}"""
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
                         "size": r[col["size"]], "unit_label": r[col["unit_label"]], "rank": rank})
    return entry.get("category"), products


def l2_grid(products, cfg=None, make_product=None):
    """สินค้าของหมวด (category_products) -> ตารางความใกล้เทรนด์ แถวเดียว 4 ระดับ:
    {"n", "cuts" (fit_top_pct),
     "cols": [{"level", "n", "product"}] 4 ระดับ - product = สินค้าที่ใกล้เทรนด์ที่สุดในระดับ (+ rank / level) หรือ None (n ใช้แค่คิดบรรทัดสรุป),
     "take": {"n_close", "close_pct"}} (เปอร์เซ็นต์เป็นจำนวนเต็ม)
    make_product(dict) -> dict ของสินค้าสำหรับเทมเพลต (report_data._product เติมรูป/ชื่อเต็ม) ไม่ส่ง = ใช้ dict เดิม"""
    cfg = cfg or load_config(CONFIG_FILE)
    top_pct = cfg["fit_top_pct"]
    n = len(products)
    cuts = rank_cuts(n, top_pct) if n else {}
    cols = {lv: {"level": lv, "n": 0, "product": None} for lv in FIT_LEVELS}
    for p in products:
        lv = fit_level(p["rank"], cuts)
        c = cols[lv]
        c["n"] += 1
        if c["product"] is None:   # สินค้าเรียงจากใกล้เทรนด์ที่สุด - ชิ้นแรกของระดับคือตัวแทนของระดับ
            base = {k: p[k] for k in ("brand", "product_name", "sale_price_thb", "size", "unit_label")}
            item = make_product({**base, "category": ""}) if make_product else dict(base)
            item.update(rank=p["rank"], level=lv)
            c["product"] = item
    n_close = sum(cols[lv]["n"] for lv in CLOSE_LEVELS)
    return {"n": n, "cuts": dict(top_pct), "cols": [cols[lv] for lv in FIT_LEVELS],
            "take": {"n_close": n_close, "close_pct": top_pct["good"]}}


def brand_tier(products, brand):
    """สินค้าของหมวด + ชื่อแบรนด์ -> "กลุ่ม" หน้าตาเดียวกับ tiers[] ของ ⑬ category_fit ที่ brand_data.best_in_tier ใช้:
    {"n_total" (สินค้าทั้งหมวด), "n_brand", "top": [], "brand_products": [สินค้าของแบรนด์ทุกชิ้น + rank_in_tier = อันดับในหมวด]} - ไม่มีสินค้าของแบรนด์ = None"""
    mine = [{"brand": p["brand"], "product_name": p["product_name"], "sale_price_thb": p["sale_price_thb"], "size": p["size"],
             "unit_label": p["unit_label"], "rank_in_tier": p["rank"], "rank_in_market": None}
            for p in products if p["brand"] == brand]
    return {"n_total": len(products), "n_brand": len(mine), "top": [], "brand_products": mine} if mine else None


def l2_category_fit(fit, products, brand, reasons=None):
    """🆕 (2026-10-21) category_fit ของ ⑬ (เทรนด์ -> หมวด -> ช่วงราคา -> สินค้า) -> แบบหมวด L2 อย่างเดียว (เจ้าของงานสั่งให้เกรดทั้ง ⑰ และ Excel ของ ⑬ เทียบในหมวด
    ไม่แยกช่วงราคา): แต่ละหมวดมี "ช่วงราคา" เดียว label "all" = ทั้งหมวด -> ฟังก์ชันเกรดเดิมทุกตัว (brand_data.best_in_category / grade_product / trend_categories
    และ Excel ของ ⑬) ใช้ต่อได้โดยไม่แก้: n_total = สินค้าทั้งหมวด, top = 5 อันดับแรกของหมวด, brand_products = สินค้าของแบรนด์ทุกชิ้นในหมวด
    (rank_in_tier = อันดับในหมวด) - ช่องอื่น (similarity / ขนาด / ฿ต่อหน่วย / อันดับทั้งตลาด / เหตุผลจับคู่) ยืมจากสินค้า
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
            base.update(rank_in_tier=p["rank"])
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
