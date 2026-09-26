# -*- coding: utf-8 -*-
"""
⑰ รายงานแบรนด์ PDF — ชั้นข้อมูล: ผล ⑬ ของ 1 แบรนด์ + ข้อมูลเทรนด์ชุดเดียวกับรายงานเทรนด์ (⑯) -> brand context

ไม่ import bootstrap และไม่เรียก API (เทสได้ด้วยข้อมูลปลอม) - ข้อมูลเทรนด์รับมาจาก report_data.build_context()
ที่รายงานเทรนด์ใช้อยู่แล้ว เทรนด์/ลำดับ/ตัวเลขจึงตรงกับรายงานเทรนด์ของรอบเดียวกันเสมอ

ทำไมไม่ใช้ช่อง "tier" ของ ⑬: tier วัดจาก percentile ของ "สินค้าที่ดีที่สุดของแบรนด์" ซึ่งแทบเกิน 67 เสมอเมื่อแบรนด์มีหลาย
SKU (ค่าสูงสุดของหลายตัวอย่างเอียงขึ้นเสมอ) - รอบ 082438 ทั้ง 5 แบรนด์ x 10 เทรนด์ได้ "ตามทัน" ครบ 50 คู่ แม้ Sureeporn
(7 SKU, สินค้าที่ใกล้สุดอยู่อันดับ 3,049) ที่นี่จึงจัดระดับจาก "อันดับจริงในตลาด" (brand_best_rank_vs_market) ตามเกณฑ์ใน
config/brand_report.json แทน - ไม่แก้ ⑬ (tier เดิมยังใช้ใน master report/Excel ตามเดิม)
"""
import difflib
import re
import statistics
from pathlib import Path

import pandas as pd

from report_data import read_json, strip_thai

FIT_LEVELS = ("leading", "competitive", "behind", "gap")
QUADRANTS = ("defend", "build", "maintain", "monitor")
COVERAGE_GLOB = "phase3_brand_coverage_*.json"
DEFAULT_CONFIG = {
    "fit_rank_thresholds": {"leading": 25, "competitive": 100, "behind": 500},
    "momentum_split": "median",
    "strong_fit_levels": ["leading", "competitive"],
    "products_per_trend": 3,
}


def load_config(path=None):
    cfg = {k: v for k, v in (read_json(path) or {}).items() if not k.startswith("_")} if path else {}
    merged = {**DEFAULT_CONFIG, **cfg}
    merged["fit_rank_thresholds"] = {**DEFAULT_CONFIG["fit_rank_thresholds"], **cfg.get("fit_rank_thresholds", {})}
    return merged


def fit_level(rank, thresholds):
    """อันดับของสินค้าที่ดีที่สุดของแบรนด์ในตลาด -> leading / competitive / behind / gap (ไม่มีสินค้า = gap)"""
    if not isinstance(rank, (int, float)):
        return "gap"
    for level in ("leading", "competitive", "behind"):
        if rank <= thresholds[level]:
            return level
    return "gap"


def momentum_split(trends, setting):
    """เส้นแบ่งแรงส่งของ Trend Fit Matrix: "median" = ค่ากลาง Z_Delta ของเทรนด์ในรายงาน, ตัวเลข = ใช้ตรงๆ"""
    if isinstance(setting, (int, float)):
        return float(setting)
    values = [t["z_delta"] for t in trends if isinstance(t.get("z_delta"), (int, float))]
    return statistics.median(values) if values else 0.0


def quadrant(z_delta, level, split, strong_levels):
    """แรงส่งสูง/ต่ำ (เทียบเส้นแบ่ง) x แบรนด์พร้อม/ยังไม่พร้อม -> defend / build / maintain / monitor"""
    high = isinstance(z_delta, (int, float)) and z_delta >= split
    strong = level in strong_levels
    if high:
        return "defend" if strong else "build"
    return "maintain" if strong else "monitor"


def list_coverage_files(run_dir):
    return sorted(Path(run_dir).glob(COVERAGE_GLOB))


def find_coverage_file(run_dir, wanted):
    """ชื่อแบรนด์ที่ผู้ใช้พิมพ์ -> ไฟล์ผล ⑬ ของแบรนด์นั้น (เทียบกับช่อง "brand" ในไฟล์แบบไม่สนตัวพิมพ์ ไม่เจอค่อยเดาชื่อ
    ใกล้เคียง) - ⑬ แก้ชื่อที่พิมพ์ให้ตรงกับแบรนด์จริงก่อนเซฟ (resolve_brand) ชื่อไฟล์จึงอาจไม่ตรงกับที่พิมพ์"""
    by_brand = {}
    for path in list_coverage_files(run_dir):
        data = read_json(path) or {}
        by_brand[str(data.get("brand") or path.stem.replace("phase3_brand_coverage_", "")).lower()] = path
    wanted = str(wanted or "").strip().lower()
    if wanted in by_brand:
        return by_brand[wanted]
    close = difflib.get_close_matches(wanted, list(by_brand), n=1, cutoff=0.8)
    return by_brand[close[0]] if close else None


def _price(value):
    try:
        return None if value is None or pd.isna(value) else float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def load_catalog(csv_path):
    """แคตตาล็อก Watsons เฉพาะคอลัมน์ที่ใช้ (รูป/ลิงก์/ราคา/หมวด) - ผล ⑬ ไม่ได้เก็บรูปไว้จึงต้อง join ด้วยชื่อ"""
    if not csv_path or not Path(csv_path).exists():
        return pd.DataFrame(columns=["brand", "product_name", "main_image", "product_url", "sale_price_thb",
                                     "Category", "Sub_category"])
    df = pd.read_csv(csv_path, encoding="utf-8-sig", low_memory=False,
                     usecols=["brand", "product_name", "main_image", "product_url", "sale_price_thb",
                              "Category", "Sub_category"])
    return df.drop_duplicates(subset=["brand", "product_name"], keep="first")


class _CatalogIndex:
    """ค้นแถวสินค้าด้วย (แบรนด์, ชื่อ) หรือด้วยสตริง "แบรนด์ - ชื่อ" แบบที่ ⑬ เก็บชื่อสินค้าเจ้าตลาดไว้"""

    def __init__(self, catalog):
        self.by_pair, self.by_label = {}, {}
        for r in catalog.itertuples(index=False):
            row = {"brand": r.brand, "product_name": r.product_name, "price_thb": _price(r.sale_price_thb),
                   "image_url": r.main_image if isinstance(r.main_image, str) and r.main_image.startswith("http")
                   else None,
                   "product_url": r.product_url if isinstance(r.product_url, str) else None}
            self.by_pair[(r.brand, r.product_name)] = row
            self.by_label[f"{r.brand} - {r.product_name}"] = row

    def pair(self, brand, name):
        return self.by_pair.get((brand, name), {})

    def label(self, text):
        return self.by_label.get(text, {})


def portfolio_stats(catalog, brand):
    """ภาพรวมสินค้าของแบรนด์บน Watsons: จำนวน SKU, หมวดย่อยหลัก, ช่วงราคา"""
    rows = catalog[catalog["brand"] == brand]
    prices = [p for p in (_price(v) for v in rows["sale_price_thb"]) if p]
    subs = rows["Sub_category"].dropna().value_counts().head(4)
    return {
        "n_skus": int(len(rows)),
        "top_subcategories": [{"name": str(k), "n": int(v)} for k, v in subs.items()],
        "price_min": min(prices) if prices else None,
        "price_median": statistics.median(prices) if prices else None,
        "price_max": max(prices) if prices else None,
    }


def _leader(coverage_row, trend, index):
    """สินค้าอันดับ 1 ของตลาดสำหรับเทรนด์นี้ (จาก ⑬) - ถ้าเป็นชิ้นเดียวกับอันดับ 1 ของ ⑫ ใช้เหตุผลจับคู่ของ ⑫ ได้เลย
    ไม่ต้องเรียก LLM เพิ่ม (ส่ง trend ที่ผ่าน i18n.localize มา = ได้เหตุผลภาษาไทยที่รายงานเทรนด์ cache ไว้แล้ว)"""
    label = coverage_row.get("market_best_product") or ""
    row = index.label(label)
    brand = row.get("brand") or (label.split(" - ", 1)[0] if " - " in label else "")
    name_full = row.get("product_name") or (label.split(" - ", 1)[1] if " - " in label else label)
    reason = next((p.get("reason") or "" for p in trend.get("products") or []
                   if p.get("name_full") == name_full and p.get("brand") == (strip_thai(brand) or brand)), "")
    return {
        "brand": strip_thai(brand) or brand,
        "name": strip_thai(name_full) or name_full,
        "name_full": name_full,
        "price_thb": row.get("price_thb"),
        "image_url": row.get("image_url"),
        "similarity": coverage_row.get("market_best_score"),
        "reason": reason,
    }


def build_brand_context(trend_ctx, coverage, catalog, cfg):
    """ผล ⑬ ของ 1 แบรนด์ (dict จาก phase3_brand_coverage_<แบรนด์>.json) + trend_ctx (report_data.build_context
    ที่เติมข้อความ text/text_th แล้ว) -> brand context ที่เทมเพลตใช้ (serialize เป็น JSON ได้)"""
    brand = coverage.get("brand") or ""
    index = _CatalogIndex(catalog)
    thresholds = cfg["fit_rank_thresholds"]
    split = momentum_split(trend_ctx["trends"], cfg["momentum_split"])
    by_key = coverage.get("coverage") or {}
    by_name = {v.get("trend_name"): v for v in by_key.values()}
    k = int(cfg.get("products_per_trend", 3))

    rows = []
    for t in trend_ctx["trends"]:
        c = by_key.get(t["key"]) or by_name.get(t["name"])
        row = {"trend": t, "rank": t["rank"], "name": t["name"], "z_delta": t.get("z_delta"), "checked": bool(c)}
        if not c:
            # เทรนด์ใน Top N ที่ผล ⑬ ของแบรนด์นี้ไม่มี (ผล ⑬ มาจากรอบเก่า/ชุดเทรนด์ต่างกัน) - แสดงว่า "ยังไม่ได้ตรวจ"
            row.update(level=None, quadrant=None, products=[], leader=None, best_rank=None, gap_to_leader=None,
                       n_in_top_competitive=0)
            rows.append(row)
            continue
        matches = c.get("brand_top_matches") or (
            [{"product_name": c["brand_best_product"], "similarity": c.get("brand_best_score"),
              "rank_vs_market": c.get("brand_best_rank_vs_market"), "match_reason": c.get("match_reason", "")}]
            if c.get("brand_best_product") else [])
        products = []
        for m in matches[:k]:
            cat = index.pair(brand, m.get("product_name"))
            products.append({
                "name": strip_thai(m.get("product_name")) or m.get("product_name"),
                "name_full": m.get("product_name"),
                "category": m.get("category") or "",
                "price_thb": m.get("sale_price_thb") if m.get("sale_price_thb") is not None else cat.get("price_thb"),
                "rank": m.get("rank_vs_market"),
                "similarity": m.get("similarity"),
                "reason": m.get("match_reason") or "",
                # สินค้านอกแคตตาล็อก Watsons (⑬ --products) มีรูปของตัวเองในผล ⑬ - ไม่มีในแคตตาล็อกให้ join
                "image_url": m.get("image_url") or cat.get("image_url"),
            })
        best_rank = c.get("brand_best_rank_vs_market")
        level = fit_level(best_rank, thresholds)
        best_score, leader_score = c.get("brand_best_score"), c.get("market_best_score")
        row.update(
            level=level,
            quadrant=quadrant(t.get("z_delta"), level, split, cfg["strong_fit_levels"]),
            products=products,
            leader=_leader(c, t, index),
            best_rank=best_rank,
            gap_to_leader=(round(leader_score - best_score, 4)
                           if isinstance(leader_score, (int, float)) and isinstance(best_score, (int, float)) else None),
            # สินค้าของแบรนด์ที่ติดกลุ่ม "แข่งขันได้" ขึ้นไป (นับจาก top 5 ที่ ⑬ เก็บไว้ - สูงสุด 5)
            n_in_top_competitive=sum(1 for m in matches if isinstance(m.get("rank_vs_market"), int)
                                     and m["rank_vs_market"] <= thresholds["competitive"]),
        )
        rows.append(row)

    checked = [r for r in rows if r["checked"]]
    counts = {lv: sum(1 for r in checked if r["level"] == lv) for lv in FIT_LEVELS}
    strongest = min((r for r in checked if r["best_rank"]), key=lambda r: r["best_rank"], default=None)
    weak = [r for r in checked if r["quadrant"] == "build"] or [r for r in checked if r["level"] in ("behind", "gap")]
    opportunity = max(weak, key=lambda r: r["z_delta"] or 0, default=None)
    closest = [r for r in checked if r["level"] != "leading" and r["gap_to_leader"] is not None
               and r is not strongest and r is not opportunity]
    quick_win = min(closest, key=lambda r: r["gap_to_leader"], default=None)
    build = sorted((r for r in checked if r["quadrant"] == "build"), key=lambda r: -(r["z_delta"] or 0))

    return {
        "brand": brand,
        "n_skus": coverage.get("n_skus"),
        "n_market": trend_ctx["meta"].get("n_products_compared"),
        # 🆕 (2026-09-26) แบรนด์ที่ไม่มีบน Watsons: ⑬ --products เก็บภาพรวมสินค้าในไฟล์ไว้ใน coverage เอง
        "portfolio": coverage.get("portfolio") or portfolio_stats(catalog, brand),
        "product_source": coverage.get("product_source") or "watsons",
        "platforms": coverage.get("platforms") or [],
        "thresholds": thresholds,
        "momentum_split": round(split, 2),
        "rows": rows,
        "counts": counts,
        "n_checked": len(checked),
        "highlights": {"strongest": strongest["rank"] if strongest else None,
                       "opportunity": opportunity["rank"] if opportunity else None,
                       "quick_win": quick_win["rank"] if quick_win else None},
        "opportunities": [r["rank"] for r in build[:4]],
        "missing_trends": [r["name"] for r in rows if not r["checked"]],
    }


def brand_reason_groups(bctx):
    """เหตุผลจับคู่สินค้าของแบรนด์ (ภาษาอังกฤษจาก ⑬) ที่ฉบับไทยต้องแปล -> {ชื่อเทรนด์: [เหตุผล, ...]}"""
    return {r["name"]: [p["reason"] for p in r["products"]] for r in bctx["rows"]
            if r["products"] and any(p["reason"] for p in r["products"])}


def safe_file_part(brand):
    """ชื่อแบรนด์ -> ส่วนของชื่อไฟล์ (แบบเดียวกับ ⑬: เว้นวรรคเป็น _) ตัดอักขระที่ Windows ห้าม"""
    return re.sub(r'[<>:"/\\|?*]', "", str(brand)).replace(" ", "_")
