# -*- coding: utf-8 -*-
"""
⑰ รายงานแบรนด์ PDF — ชั้นข้อมูล: ผล ⑬ ของ 1 แบรนด์ + ข้อมูลเทรนด์ชุดเดียวกับรายงานเทรนด์ (⑯) -> brand context

ไม่ import bootstrap และไม่เรียก API (เทสได้ด้วยข้อมูลปลอม) - ข้อมูลเทรนด์รับมาจาก report_data.build_context()
ที่รายงานเทรนด์ใช้อยู่แล้ว เทรนด์/ลำดับ/ตัวเลขจึงตรงกับรายงานเทรนด์ของรอบเดียวกันเสมอ

🆕 (2026-10-07) เกรดคิดแบบ เทรนด์ -> หมวด -> ช่วงราคาตลาด -> สินค้า (category_fit ของ ⑬ - ดู build_brand_context)
แทนอันดับในตลาดทั้งร้าน เกณฑ์ % เดิม (1/5/20) ใช้กับอันดับในกลุ่ม หมวด x ช่วงราคา

ทำไมไม่ใช้ช่อง "tier" ของ ⑬: tier วัดจาก percentile ของ "สินค้าที่ดีที่สุดของแบรนด์" ซึ่งแทบเกิน 67 เสมอเมื่อแบรนด์มีหลาย
SKU (ค่าสูงสุดของหลายตัวอย่างเอียงขึ้นเสมอ) - รอบ 082438 ทั้ง 5 แบรนด์ x 10 เทรนด์ได้ "ตามทัน" ครบ 50 คู่ แม้ Sureeporn
(7 SKU, สินค้าที่ใกล้สุดอยู่อันดับ 3,049) ที่นี่จึงจัดระดับจาก "อันดับจริงในตลาด" (brand_best_rank_vs_market) คิดเป็น % แรกของตลาด ตามเกณฑ์ใน
config/brand_report.json แทน - ไม่แก้ ⑬ (tier เดิมยังใช้ใน master report/Excel ตามเดิม)
"""
import difflib
import re
import statistics
import sys
from pathlib import Path

import pandas as pd

from plain_text import plain_cleanup
from report_data import SHORT_YEAR, read_json, strip_thai

# 🆕 (2026-10-07) 4 ระดับตาม "% แรกของตลาด" แทนอันดับตายตัว (นำตลาด <=25 / แข่งขันได้ <=100 / ตามหลัง <=500 / ช่องว่าง)
# - อันดับตายตัวเปลี่ยนความหมายเมื่อขนาดตลาดเปลี่ยน (8,738 vs 10,622 SKU) ส่วน % เทียบข้ามรอบได้
FIT_LEVELS = ("excellent", "good", "average", "below_average")
QUADRANTS = ("defend", "build", "maintain", "monitor")
COVERAGE_GLOB = "phase3_brand_coverage_*.json"
DEFAULT_CONFIG = {
    "fit_top_pct": {"excellent": 1, "good": 5, "average": 20},
    "momentum_split": "median",
    "strong_fit_levels": ["excellent", "good"],
}


def load_config(path=None):
    cfg = {k: v for k, v in (read_json(path) or {}).items() if not k.startswith("_")} if path else {}
    merged = {**DEFAULT_CONFIG, **cfg}
    merged["fit_top_pct"] = {**DEFAULT_CONFIG["fit_top_pct"], **cfg.get("fit_top_pct", {})}
    return merged


def rank_cuts(n_market, top_pct):
    """% แรกของตลาด -> อันดับสุดท้ายของแต่ละระดับ เช่น 8,738 SKU กับ 1/5/20% -> excellent 87, good 436, average 1,747
    (อันดับ r อยู่ใน top p% เมื่อ r <= n x p / 100 จึงปัดลง)"""
    if not n_market:
        raise ValueError("ไม่รู้จำนวน SKU ทั้งตลาด (n_products_compared ของ ⑫) - คำนวณ % แรกของตลาดไม่ได้")
    return {lv: max(1, int(n_market * top_pct[lv] / 100)) for lv in FIT_LEVELS[:-1]}


def fit_level(rank, cuts):
    """อันดับในตลาดของสินค้า -> excellent / good / average / below_average (ไม่มีสินค้า = below_average)
    cuts = rank_cuts() - ใช้ทั้งกับสินค้าที่ดีที่สุดของแบรนด์ (ระดับของเทรนด์) และสินค้าแต่ละชิ้นในหน้าเทรนด์"""
    if not isinstance(rank, (int, float)):
        return "below_average"
    for level in FIT_LEVELS[:-1]:
        if rank <= cuts[level]:
            return level
    return "below_average"


# ---------------------------------------------------------------------------
# 🆕 (2026-10-27) เกรดสินค้า = ความใกล้เทรนด์อย่างเดียว (เจ้าของงานสั่งตัดยอดขาย Konvy ออกจากเกรดและรายงานทั้งหมด): เกณฑ์ใช้ได้กับสินค้านอก Konvy
# ด้วย (ไม่ต้องมีตัวนับยอดขาย) - เกรดก่อนหน้านี้ (2026-10-19..21) ปรับ +-1 ขั้นตามยอดขายและ Excellent ต้องขายดีด้วย; โค้ดเดิมอยู่ใน
# output/_backups/sales_removal_code_20261027 (ข้อมูลดิบยอดขายยังอยู่ในผล ⑬ / แผนที่ ⑫ แต่รายงานไม่ใช้)
# ---------------------------------------------------------------------------
def grade_product(p, n_tier, top_pct):
    """สินค้า 1 ชิ้นในกลุ่มที่มี n_tier ชิ้น (p มี rank_in_tier) -> {"level"} ตามอันดับ % แรกของกลุ่มล้วนๆ"""
    return {"level": fit_level(p["rank_in_tier"], rank_cuts(n_tier, top_pct))}


def tier_products(tier):
    """สินค้าของแบรนด์ในกลุ่ม (หมวด x ช่วงราคา) ของ category_fit - ผล ⑬ ก่อน 2026-10-19 ไม่มี brand_products มีแต่ชิ้นที่ใกล้เทรนด์ที่สุด"""
    prods = tier.get("brand_products")
    if prods is None:
        bb = tier.get("brand_best")
        prods = [bb] if bb else []
    return prods


def best_in_tier(tier, top_pct):
    """สินค้าของแบรนด์ที่เกรดดีที่สุดในกลุ่ม (= ชิ้นที่อันดับในกลุ่มดีที่สุด) -> {"raw", "level"} หรือ None"""
    n = tier.get("n_total")
    if not n:
        return None
    best = None
    for p in tier_products(tier):
        g = grade_product(p, n, top_pct)
        key = (FIT_LEVELS.index(g["level"]), p["rank_in_tier"] / n, p["rank_in_tier"])
        if best is None or key < best[0]:
            best = (key, p, g)
    return None if best is None else {"raw": best[1], **best[2]}


def best_in_category(category, top_pct):
    """category_fit["categories"][i] -> (tier, best_in_tier) ของกลุ่มที่สินค้าของแบรนด์ได้เกรดดีที่สุด หรือ (None, None)"""
    found = [(t, best_in_tier(t, top_pct)) for t in category.get("tiers") or []]
    found = [(t, b) for t, b in found if b]
    if not found:
        return None, None
    return min(found, key=lambda x: (FIT_LEVELS.index(x[1]["level"]), x[1]["raw"]["rank_in_tier"] / x[0]["n_total"],
                                     x[1]["raw"]["rank_in_tier"]))


SHORT_IDX = SHORT_YEAR - 1  # 🆕 (2026-10-19) ระยะสั้น = ปีที่ SHORT_YEAR (common/horizons.py; เดิมเขียนเลข 1 ตายตัว = ปีที่ 2)


def trend_growth(t):
    """🆕 (2026-09-30) คะแนนการเติบโตระยะสั้นของเทรนด์ (report_data: t["growth"]["scores"], 0-1) - แทน Z_Delta
    🆕 (2026-10-02) ปีที่ 2 (เดิมปีที่ 1) · 🆕 (2026-10-19) ปีที่ SHORT_YEAR"""
    scores = (t.get("growth") or {}).get("scores") or []
    v = scores[SHORT_IDX] if len(scores) > SHORT_IDX else None
    return v if isinstance(v, (int, float)) else None


def momentum_split(trends, setting):
    """เส้นแบ่งการเติบโตของแนวทาง (Defend/Build/Maintain/Monitor): "median" = ค่ากลางคะแนนการเติบโตระยะสั้น (ปีที่ 2) ของเทรนด์ในรายงาน,
    ตัวเลข = ใช้ตรงๆ (สเกลคะแนน 0-1) - ไม่ใช้ 0.5 (ค่ากลางตลาด) เพราะเทรนด์ในรายงานอยู่เหนือเส้นนั้นเกือบทั้งหมด"""
    if isinstance(setting, (int, float)):
        return float(setting)
    values = [g for g in (trend_growth(t) for t in trends) if g is not None]
    return statistics.median(values) if values else 0.5


def overall_level(counts, n):
    """🆕 (2026-10-07) เกรดรวมของแบรนด์ = ระดับสูงสุดที่ "เกินครึ่ง" ของเทรนด์ที่ตรวจแล้วทำได้ถึง (นับระดับนั้นหรือดีกว่ารวมกัน)
    ครึ่งพอดีไม่นับ (3/3/3/3 -> Average, Excellent 3 + Good 3 -> Good) เพื่อให้ประโยค "เทรนด์ส่วนใหญ่ ..." เป็นจริงเสมอ
    counts = {ระดับ: จำนวนเทรนด์} / n = จำนวนเทรนด์ที่ตรวจแล้ว -> {"level", "n", "k" (จำนวนเทรนด์ที่ได้ระดับนั้นขึ้นไป),
    "at_or_better" (ทุกระดับ), "next": {"level", "k"} ของระดับถัดขึ้นไปเมื่ออีกแค่ 1 เทรนด์ก็ขึ้นระดับ (ไม่งั้น None)}
    ไม่มีเทรนด์ที่ตรวจ -> None"""
    if not n:
        return None
    need = n // 2 + 1  # "เกินครึ่ง"
    at_or_better, total = {}, 0
    for lv in FIT_LEVELS:
        total += counts.get(lv, 0)
        at_or_better[lv] = total
    level = next((lv for lv in FIT_LEVELS if at_or_better[lv] >= need), FIT_LEVELS[-1])
    i = FIT_LEVELS.index(level)
    up = FIT_LEVELS[i - 1] if i > 0 else None
    # ไม่บอกระดับถัดไปเมื่อยังไม่มีเทรนด์ไหนถึงเลย ("ได้แล้ว 0 จาก 1" อ่านแปลก - เกิดได้เมื่อตรวจแค่ 1 เทรนด์)
    nxt = {"level": up, "k": at_or_better[up]} if up and at_or_better[up] and need - at_or_better[up] == 1 else None
    return {"level": level, "n": n, "k": at_or_better[level], "at_or_better": at_or_better, "next": nxt}


def quadrant(growth, level, split, strong_levels):
    """การเติบโตสูง/ต่ำ (เทียบเส้นแบ่ง) x แบรนด์พร้อม/ยังไม่พร้อม -> defend / build / maintain / monitor"""
    high = isinstance(growth, (int, float)) and growth >= split
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
    """แคตตาล็อกสินค้า (Konvy) เฉพาะสินค้าความงาม (EM_L1 = Beauty and Personal Care) พร้อมหมวด L2 (EM_L2) ตาม product_category.csv
    ผล ⑬ ไม่ได้เก็บรูปไว้จึงต้อง join ด้วยชื่อ - ตลาดเดียวกับ ⑫/⑬ (กรอง L1 แล้ว) จำนวน SKU จึงตรงกับที่ ⑬ นับ"""
    cols = ["brand", "product_name", "main_image", "product_url", "sale_price_thb", "EM_L2"]
    if not csv_path or not Path(csv_path).exists():
        return pd.DataFrame(columns=cols)
    # import ตรงนี้ (ไม่ใช่บนสุดของไฟล์): โมดูลนี้ต้องเทสได้โดยไม่แตะ bootstrap/API - euromonitor_mapping ใช้แค่ pandas
    tool_dir = str(Path(__file__).resolve().parents[1])
    if tool_dir not in sys.path:
        sys.path.insert(0, tool_dir)
    from product.euromonitor_mapping import load_catalog as load_beauty_catalog
    df = load_beauty_catalog(csv_path, beauty_only=True,
                             usecols=["brand", "product_name", "main_image", "product_url", "sale_price_thb"])
    return df[cols].drop_duplicates(subset=["brand", "product_name"], keep="first")


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
    """ภาพรวมสินค้าของแบรนด์บน Konvy: จำนวน SKU, หมวดหลัก (Level 2 ของ Euromonitor), ช่วงราคา"""
    rows = catalog[catalog["brand"] == brand]
    prices = [p for p in (_price(v) for v in rows["sale_price_thb"]) if p]
    subs = rows["EM_L2"].dropna().value_counts().head(4)
    return {
        "n_skus": int(len(rows)),
        "top_subcategories": [{"name": str(k), "n": int(v)} for k, v in subs.items()],
        "price_min": min(prices) if prices else None,
        "price_median": statistics.median(prices) if prices else None,
        "price_max": max(prices) if prices else None,
    }


def _group_product(m, index, brand=None):
    """🆕 (2026-10-07) สินค้าจาก category_fit (top ของกลุ่ม / สินค้าที่ดีที่สุดของแบรนด์) -> รูปแบบที่เทมเพลตใช้
    (ชื่อตัดภาษาไทยสำหรับฉบับอังกฤษ + ชื่อเต็ม, รูปและราคาจากแคตตาล็อกเมื่อไม่มี)"""
    b = m.get("brand") or brand or ""
    cat = index.pair(b, m.get("product_name"))
    return {"brand": strip_thai(b) or b, "name": strip_thai(m.get("product_name")) or m.get("product_name"),
            "name_full": m.get("product_name"),
            "price_thb": m.get("sale_price_thb") if m.get("sale_price_thb") is not None else cat.get("price_thb"),
            "similarity": m.get("similarity"), "rank_in_tier": m.get("rank_in_tier"),
            "rank_in_market": m.get("rank_in_market"), "image_url": cat.get("image_url"),
            # 🆕 (2026-10-12) ช่วงราคาต่อปริมาณ: ขนาดรวม / ฿ ต่อหน่วย / ขนาดทดลอง (ผล ⑬ รอบเก่าไม่มี -> None)
            "size": m.get("size"), "unit_label": m.get("unit_label"), "unit_price": m.get("unit_price"),
            "is_mini": bool(m.get("is_mini"))}


def _grade_fields(g, raw):
    """grade_product() / best_in_tier() -> ช่องเกรดที่เทมเพลตใช้ (level = เกรดตามอันดับในกลุ่ม)"""
    return {"level": g["level"]}


def trend_categories(fit, brand, index, top_pct):
    """🆕 (2026-10-07) เทรนด์ -> หมวด -> ช่วงราคา -> สินค้า (category_fit ของ ⑬) -> หมวดของเทรนด์:
    🆕 (2026-10-08) category_fit มีหมวดหลักหมวดเดียว (LLM เลือก - ไม่นับหมวดควบคู่) จึงได้รายการ 1 รายการ; "key" เป็น True เสมอ
    (เก็บชื่อฟิลด์ไว้ให้เทมเพลตเดิม)
    [{"category", "key", "n_brand", "n_total", "best": สินค้าที่ดีที่สุดของแบรนด์ในหมวด + กลุ่มราคา/อันดับในกลุ่ม/เกรด หรือ None,
      "cell": กลุ่ม (หมวด x ช่วงราคา) ของสินค้าชิ้นนั้น + top N ของกลุ่ม หรือ None}]
    เกรด = อันดับในกลุ่มตามเกณฑ์ % เดียวกับเดิม (rank_cuts ของขนาดกลุ่ม - อันดับ 1 ของกลุ่มได้ Excellent เสมอ)
    🆕 (2026-10-27) เกรดตามความใกล้เทรนด์ล้วน (ตัดยอดขายออก) - "best" = สินค้าของแบรนด์ที่อันดับดีที่สุดในกลุ่ม"""
    out = []
    for c in fit.get("categories") or []:
        entry = {"category": c["category"], "key": True,
                 "n_brand": c.get("n_brand", 0), "n_total": c.get("n_total"), "best": None, "cell": None, "tiers": []}
        # 🆕 (2026-10-07) ตารางหมวด x ช่วงราคาในหน้าเทรนด์: ทุกช่วงราคาตลาดของหมวด + สินค้าของแบรนด์ที่เกรดดีที่สุดในช่วงนั้น
        for t in c.get("tiers") or []:
            tb = best_in_tier(t, top_pct)
            best_t = None
            if tb:
                raw = tb["raw"]
                best_t = {**_group_product(raw, index, brand), "pct": raw["rank_in_tier"] / t["n_total"] * 100, **_grade_fields(tb, raw)}
            entry["tiers"].append({"label": t["label"], "price_from": t.get("price_from"), "price_to": t.get("price_to"),
                                   "n_total": t.get("n_total"), "best": best_t, "graded": False})
        tier, tb = best_in_category(c, top_pct)
        if tb:
            raw = tb["raw"]
            closest = c.get("brand_best") or {}
            # เหตุผลจับคู่ของชิ้นที่ให้เกรด: ⑬ เขียนไว้ที่ตัวสินค้าในกลุ่มเมื่อชิ้นนั้นไม่ใช่ชิ้นที่ใกล้เทรนด์ที่สุด ไม่งั้นใช้ของ brand_best
            reason = raw.get("match_reason") or (closest.get("match_reason") if closest.get("product_name") == raw.get("product_name") else "")
            best = _group_product(raw, index, brand)
            best.update(category=c["category"], tier=tier["label"], price_from=tier.get("price_from"), price_to=tier.get("price_to"),
                        n_tier=tier["n_total"], pct=raw["rank_in_tier"] / tier["n_total"] * 100, **_grade_fields(tb, raw),
                        reason=plain_cleanup(reason or "", "en"))   # 🆕 (2026-10-12) ศัพท์เฉพาะ -> คำธรรมดา
            # top 5 ของกลุ่ม - สินค้าของแบรนด์ทุกชิ้นที่ติด top 5 ถูกไฮไลต์พร้อมเกรด (🆕 2026-10-07 หน้า "สินค้าตามเทรนด์ เทียบคู่แข่ง")
            # you_in_top = สินค้าที่ดีที่สุดของแบรนด์ (ชิ้นที่ให้เกรด) อยู่ใน top 5 แล้ว -> ไม่ต้องแสดงแถวล่างแยก
            top = []
            for i, m in enumerate(tier.get("top", [])):
                pos = m.get("rank_in_tier") or i + 1
                mine = m.get("brand") == brand
                top.append({**_group_product(m, index), "pos": pos, "is_you": mine,
                            "level": grade_product({**m, "rank_in_tier": pos}, tier["n_total"], top_pct)["level"] if mine else None})
            entry["best"] = best
            entry["cell"] = {"category": c["category"], "tier": tier["label"], "price_from": tier.get("price_from"),
                             "price_to": tier.get("price_to"), "n_total": tier["n_total"], "top": top,
                             "you_in_top": any(m["is_you"] and m["name_full"] == best["name_full"] for m in top)}
        # 🆕 (2026-10-07) top 5 ของทั้งหมวด (ทุกช่วงราคา ทุกแบรนด์) สำหรับหน้า 2 ของเทรนด์ = รวม top ของทุกช่วงราคาแล้วเรียงตามอันดับ
        # ในร้าน (5 อันดับแรกของหมวดอยู่ใน 5 อันดับแรกของช่วงราคาตัวเองเสมอ) + บอกช่วงราคา และธงสินค้าของแบรนด์ลูกค้า
        merged = sorted(((m, t["label"]) for t in c.get("tiers") or [] for m in t.get("top") or []),
                        key=lambda x: x[0].get("rank_in_market") or 0)[:5]
        entry["top"] = [{**_group_product(m, index), "pos": i + 1, "tier": label, "is_you": m.get("brand") == brand}
                        for i, (m, label) in enumerate(merged)]
        out.append(entry)
    return out


def _level_order(product):
    """เรียงสินค้า: เกรดดีกว่าก่อน แล้ว % แรกในกลุ่มน้อยกว่าก่อน"""
    return FIT_LEVELS.index(product["level"]), product["pct"], product["rank_in_tier"]


def build_brand_context(trend_ctx, coverage, catalog, cfg):
    """ผล ⑬ ของ 1 แบรนด์ (dict จาก phase3_brand_coverage_<แบรนด์>.json) + trend_ctx (report_data.build_context
    ที่เติมข้อความ text/text_th แล้ว) -> brand context ที่เทมเพลตใช้ (serialize เป็น JSON ได้)
    🆕 (2026-10-07) เกรดแบบ "เทรนด์ -> หมวด -> ช่วงราคา -> สินค้า" (ผู้ใช้เลือก): ต่อเทรนด์ ดูหมวดที่เทรนด์แตะ (category_fit
    ของ ⑬) สินค้าของแบรนด์ในหมวดของเทรนด์เทียบในกลุ่ม หมวด x ช่วงราคาตลาด ของตัวเอง แล้วเกรดของเทรนด์ = เกรดที่ดีที่สุดในหมวดนั้น
    🆕 (2026-10-08) หมวดของเทรนด์ = หมวดหลักหมวดเดียวที่ LLM เลือก (ไม่นับหมวดควบคู่ เจ้าของงานเลือก) - ไม่มีสินค้าในหมวดนั้นเลย =
    Below average (no_key_product)"""
    brand = coverage.get("brand") or ""
    index = _CatalogIndex(catalog)
    top_pct = cfg["fit_top_pct"]
    strong_levels = cfg["strong_fit_levels"]
    split = momentum_split(trend_ctx["trends"], cfg["momentum_split"])
    by_key = coverage.get("coverage") or {}
    by_name = {v.get("trend_name"): v for v in by_key.values()}

    rows = []
    for t in trend_ctx["trends"]:
        c = by_key.get(t["key"]) or by_name.get(t["name"])
        g = t.get("growth") or {}
        row = {"trend": t, "rank": t["rank"], "name": t["name"], "growth": trend_growth(t),
               # 🆕 (2026-10-08) ชื่อที่แสดง (display_names.py) - name ยังเป็นชื่อเดิม ใช้จับคู่/เป็นคีย์ของคำแปล
               "display_name": t.get("display_name") or t["name"],
               "growth_grade": ((g.get("grades") or []) + [None] * (SHORT_IDX + 1))[SHORT_IDX],
               # 🆕 (2026-10-02) % การค้นหาที่คาดปีที่ SHORT_YEAR (เทียบ 12 เดือนล่าสุด) - รายงานแสดงตัวเลขนี้แทนคำ "เร็ว/ช้า"
               "expected_pct": ((g.get("forecast_pct") or []) + [None] * (SHORT_IDX + 1))[SHORT_IDX],
               "past_growth_pct": g.get("past_growth_pct"),
               "checked": bool(c)}
        if not c:
            # เทรนด์ใน Top N ที่ผล ⑬ ของแบรนด์นี้ไม่มี (ผล ⑬ มาจากรอบเก่า/ชุดเทรนด์ต่างกัน) - แสดงว่า "ยังไม่ได้ตรวจ"
            row.update(level=None, quadrant=None, categories=[], products=[], graded=None, cell=None, leader=None,
                       gap_to_leader=None, no_key_product=False, key_categories=[])
            rows.append(row)
            continue
        if not c.get("category_fit"):
            raise ValueError(f"ผล ⑬ ของ {brand} เทรนด์ '{t['name']}' ไม่มี category_fit (ผลรอบก่อน 2026-10-07) - รัน "
                             f"run_brand_coverage.py --category-fit-only --brand {brand} ก่อน")
        if not c["category_fit"].get("main_category"):
            raise ValueError(f"ผล ⑬ ของ {brand} เทรนด์ '{t['name']}' ยังเป็นแบบหลายหมวด (ก่อน 2026-10-08) ไม่มีหมวดหลักที่ LLM เลือก - รัน "
                             f"run_brand_coverage.py --category-fit-only --brand {brand} ก่อน")
        cats = trend_categories(c["category_fit"], brand, index, top_pct)
        key_bests = [e["best"] for e in cats if e["key"] and e["best"]]
        graded = min(key_bests, key=_level_order, default=None)
        cell = next((e["cell"] for e in cats if e["best"] is graded), None) if graded else None
        for e in cats:   # ช่องของตารางหมวด x ช่วงราคาที่ใช้เป็นเกรดของเทรนด์ (ไฮไลต์ในหน้าเทรนด์) - อย่าใช้ชื่อ t (= เทรนด์)
            for tier in e["tiers"]:
                tier["graded"] = graded is not None and e["best"] is graded and tier["label"] == graded["tier"]
        leader = (cell["top"][0] if cell and cell["top"] else None)
        level = graded["level"] if graded else "below_average"
        row.update(
            level=level,
            quadrant=quadrant(trend_growth(t), level, split, strong_levels),
            categories=cats,
            # สินค้าที่ดีที่สุดของแบรนด์ในแต่ละหมวดที่เทรนด์แตะ (รูป / คำแปลเหตุผลใช้ลิสต์นี้)
            products=[e["best"] for e in cats if e["best"]],
            graded=graded, cell=cell, leader=leader,
            no_key_product=graded is None,
            key_categories=[e["category"] for e in cats if e["key"]],
            gap_to_leader=(round(leader["similarity"] - graded["similarity"], 4)
                           if leader and graded and isinstance(leader.get("similarity"), (int, float))
                           and isinstance(graded.get("similarity"), (int, float)) else None),
        )
        rows.append(row)

    checked = [r for r in rows if r["checked"]]
    counts = {lv: sum(1 for r in checked if r["level"] == lv) for lv in FIT_LEVELS}
    strongest = min((r for r in checked if r["graded"]), key=lambda r: _level_order(r["graded"]), default=None)
    weak = [r for r in checked if r["quadrant"] == "build"] or [r for r in checked if r["level"] not in strong_levels]
    opportunity = max(weak, key=lambda r: r["growth"] or 0, default=None)
    closest = [r for r in checked if r["level"] != "excellent" and r["gap_to_leader"] is not None
               and r is not strongest and r is not opportunity]
    quick_win = min(closest, key=lambda r: r["gap_to_leader"], default=None)
    build = sorted((r for r in checked if r["quadrant"] == "build"), key=lambda r: -(r["growth"] or 0))

    fits = [(v or {}).get("category_fit") for v in by_key.values()]
    fits = [f for f in fits if f]
    # 🆕 (2026-10-12) ช่วงราคาของรอบนี้แบ่งด้วยอะไร - ใช้ราคาต่อปริมาณเมื่อทุกเทรนด์ที่ตรวจแล้วใช้ (ผลรอบเก่าไม่มี tier_basis = ราคาขาย)
    tier_basis = "unit_price" if fits and all(f.get("tier_basis") == "unit_price" for f in fits) else "price"
    # 🆕 (2026-10-21) เกรดเทียบในหมวด L2 อย่างเดียว (l2_map.l2_coverage แปลง category_fit ให้แล้ว) - ข้อความ/ป้ายของรายงานเปลี่ยนตาม (brand_i18n.L2_STRINGS)
    group_basis = "l2" if fits and all(f.get("group_basis") == "l2" for f in fits) else "tier"
    return {
        "brand": brand,
        "tier_basis": tier_basis,
        "group_basis": group_basis,
        "n_skus": coverage.get("n_skus"),
        "n_market": trend_ctx["meta"].get("n_products_compared"),
        "portfolio": portfolio_stats(catalog, brand),
        "top_pct": top_pct,
        "strong_levels": strong_levels,
        "momentum_split": round(split, 2),
        "rows": rows,
        "counts": counts,
        "overall": overall_level(counts, len(checked)),
        "n_checked": len(checked),
        "highlights": {"strongest": strongest["rank"] if strongest else None,
                       "opportunity": opportunity["rank"] if opportunity else None,
                       "quick_win": quick_win["rank"] if quick_win else None},
        "opportunities": [r["rank"] for r in build[:4]],
        "missing_trends": [r["display_name"] for r in rows if not r["checked"]],
        # 🆕 (2026-10-28) เทรนด์ที่ไม่ได้ให้เกรดเพราะไม่มีสินค้าที่ใกล้พอ (report_data.product_trends ตัดออกจาก rows แล้ว) - บอกในหน้าสรุป
        "no_close_trends": list(trend_ctx.get("no_close_trends") or []),
    }


def brand_reason_groups(bctx):
    """เหตุผลจับคู่สินค้าของแบรนด์ (ภาษาอังกฤษจาก ⑬) ที่ฉบับไทยต้องแปล -> {ชื่อเทรนด์: [เหตุผล, ...]}"""
    return {r["name"]: [p["reason"] for p in r["products"]] for r in bctx["rows"]
            if r["products"] and any(p["reason"] for p in r["products"])}


def safe_file_part(brand):
    """ชื่อแบรนด์ -> ส่วนของชื่อไฟล์ (แบบเดียวกับ ⑬: เว้นวรรคเป็น _) ตัดอักขระที่ Windows ห้าม"""
    return re.sub(r'[<>:"/\\|?*]', "", str(brand)).replace(" ", "_")
