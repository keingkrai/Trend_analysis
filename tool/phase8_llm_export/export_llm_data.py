# -*- coding: utf-8 -*-
"""
⑳ LLM export — แปลงผลของรอบ (⑯ เทรนด์ + ⑰ แบรนด์) เป็นไฟล์ที่ส่งต่อให้ LLM / pandas / SQL ใช้ได้ (ไม่ใช่รายงาน)
อ่านไฟล์ของรอบอย่างเดียว ไม่แตะรายงาน ไม่เรียก LLM / API / SerpAPI - รันซ้ำได้ ผลเดิมถูกเขียนทับ

อ่าน:  phase6_report_context.json            ข้อมูลเทรนด์ของรอบ (⑯)
       phase6_brand_context_<แบรนด์>.json     เกรดความพร้อมต่อแบรนด์ (⑰) - ต้องรัน ⑰ ของแบรนด์นั้นก่อน
เขียน: <รอบ>/llm_export/
    meta.json                  รอบ/วันที่ข้อมูล/นิยามเกรด/ข้อควรระวังความน่าเชื่อถือ/คำอธิบายทุกคอลัมน์ (ให้ LLM อ่านก่อน)
    trends.csv                 ตารางเทรนด์กลาง - 1 แถวต่อเทรนด์ (พยากรณ์ปี 1-5 + ข้อความ) ใช้ร่วมทุกลูกค้า
    trend_top_products.csv     สินค้าตลาดที่ใกล้เทรนด์ที่สุด 5 อันดับต่อเทรนด์ (ใช้ร่วมทุกลูกค้า)
    customers.csv              1 แถวต่อลูกค้า (เกรดรวม ภาพรวมสินค้า)
    customer_trends.csv        ตารางรวมทุกลูกค้า - 1 แถวต่อ ลูกค้า x เทรนด์ (เกรด สินค้าที่ดีที่สุด คู่แข่งอันดับ 1)
    llm_export.sqlite          4 ตารางข้างบน + glossary + run_info (ให้ LLM ใช้เครื่องมือ SQL query แทนการอ่านทั้งไฟล์)
    briefs/<แบรนด์>.json       สรุปต่อลูกค้า 1 ไฟล์ อ่านจบในตัว (ใส่ใน prompt ได้ตรงๆ) ช่องไม่มีค่าถูกตัดออก

ตัวเลข/เกรดทั้งหมดมาจากไฟล์ของรายงานโดยตรง (ไม่คำนวณเกรดใหม่) จึงตรงกับ PDF เสมอ - เปลี่ยนเกณฑ์เกรดที่ brand_data.py / config/brand_report.json
แล้วรัน ⑰ ก่อน จึงค่อยรันไฟล์นี้

Usage:
    python tool/phase8_llm_export/export_llm_data.py --run <ชื่อรอบ>
    python tool/phase8_llm_export/export_llm_data.py                 # TREND_RUN_ID หรือรอบล่าสุดที่มี phase6_report_context.json
"""
import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL_DIR = HERE.parent
OUTPUT_ROOT = TOOL_DIR.parent / "output"
sys.path.insert(0, str(TOOL_DIR))
sys.path.insert(0, str(TOOL_DIR / "phase6_pdf_report"))

from brand_data import FIT_LEVELS, QUADRANTS, safe_file_part  # noqa: E402
from common.horizons import LONG_YEAR, SHORT_YEAR, YEARS  # noqa: E402
from report_data import read_json  # noqa: E402

SCHEMA_VERSION = "1.1"   # 1.1 (2026-10-27): sales fields removed from the grade and from every table
CONTEXT_FILE = "phase6_report_context.json"
BRAND_GLOB = "phase6_brand_context_*.json"
EXPORT_DIR = "llm_export"
SQL_TYPES = {"text": "TEXT", "int": "INTEGER", "real": "REAL"}
SY, LY = f"year_{SHORT_YEAR}", f"year_{LONG_YEAR}"      # คีย์ปีใน brief

# ---------------------------------------------------------------------------
# สเปคคอลัมน์ (ชื่อ, ชนิด, คำอธิบาย) - ที่เดียวสำหรับ CSV / SQLite / glossary ใน meta.json (เขียนเป็นอังกฤษ: LLM เป็นคนอ่าน)
# ช่องที่เป็นใช่/ไม่ใช่เก็บเป็น 0/1 · ช่องว่าง = ไม่มีข้อมูล (ไม่ใช่ศูนย์)
# ---------------------------------------------------------------------------
TREND_COLUMNS = [
    ("trend_id", "text", "Stable id of the trend inside this run (slug of the name). Join key for every table."),
    ("name", "text", "Original technical trend name."),
    ("display_name", "text", "Plain-language trend title used in the reports. Use this when writing to customers."),
    ("stream", "text", "Data stream that found the trend: Paper, Social or News."),
    ("rank_short", "int", f"Rank among all trends by growth score at year {SHORT_YEAR} (1 = strongest). Used for the short-term ranking."),
    ("rank_long", "int", f"Rank among all trends by growth score at year {LONG_YEAR}."),
    ("above_market_line", "int", f"1 if the year-{SHORT_YEAR} growth score is above the market median (0.5)."),
    ("in_product_analysis", "int", "1 if the trend was matched against products (it has customer fit grades and top products). "
                                   "0 = below the market line: only forecast numbers exist."),
    ("no_close_product", "int", "1 = the trend was matched but no Konvy product is close enough to show: the 5 products closest to it are mostly outside "
                                "the trend's main category. It then has no top products and no customer fit grades. 0 = matched normally. Empty = not matched."),
    ("match_basis", "text", "What the trend's text matched against products was built from: 'need' = the beauty need an AI inferred from the searches (product types and "
                            "benefits - used first) followed by what the searches show; 'evidence' = what the searches show only. Empty = not matched."),
    *[(f"expected_pct_y{y}", "real", f"Expected search interest in year {y} vs the last 12 months, % (e.g. 53 = 53% higher). Cumulative level, not a yearly change.")
      for y in YEARS],
    *[(f"growth_score_y{y}", "real", f"Growth score at year {y}, 0-1: percentile of the trend's keywords against all keywords of the run (0.5 = market median).")
      for y in YEARS],
    ("cagr_pct_short", "real", f"Expected compound yearly growth up to year {SHORT_YEAR}, %."),
    ("cagr_pct_long", "real", f"Expected compound yearly growth up to year {LONG_YEAR}, %."),
    ("past_growth_pct", "real", "Search growth of the last 12 months vs the 12 months before, %. Inflated for every trend by a jump in the Google Trends data "
                                "(see reliability_notes); compare trends against each other, not against zero."),
    ("recent_decline", "int", "1 if recent months are falling."),
    ("main_category", "text", "Main product category (L2) the trend belongs to - the category customers' products are compared in."),
    ("trend_stage", "text", "Life-cycle stage written by the analysis (e.g. Growing)."),
    ("primary_driver", "text", "What drives the trend (e.g. Structural Growth)."),
    ("estimated_duration", "text", "Expected duration (e.g. Medium-term)."),
    ("longevity_score", "int", "0-100 durability score; higher = more likely to last."),
    ("longevity_band", "text", "Text band of the durability score."),
    ("data_quality", "text", "How much search data supports the trend (rich / ...)."),
    ("n_keywords", "int", "Number of search keywords grouped into the trend."),
    ("keywords", "text", "Main search keywords, separated by '; '."),
    ("target_consumer", "text", "Who the trend is for."),
    ("key_ingredients", "text", "Key ingredients linked to the trend."),
    ("key_benefits", "text", "Key benefits linked to the trend."),
    ("executive_summary", "text", "Two-sentence summary of the trend."),
    ("consumer_intent", "text", "What consumers are looking for (from the search terms)."),
    ("risk_if_forecast_fails", "text", "What could make the forecast wrong."),
]

TOP_PRODUCT_COLUMNS = [
    ("trend_id", "text", "Trend id (join to trends)."),
    ("pos", "int", "1 = Konvy product closest to the trend (by description similarity)."),
    ("brand", "text", "Brand of the market product."),
    ("product", "text", "Product name."),
    ("price_thb", "real", "Current price, THB."),
    ("size", "real", "Pack size in unit_label."),
    ("unit_label", "text", "ml / g / pc ..."),
    ("unit_price_thb", "real", "Price per unit_label, THB."),
    ("is_mini", "int", "1 = trial/mini size."),
    ("similarity", "real", "Cosine similarity between the product and the trend description (higher = closer)."),
    ("reason", "text", "Why the product matches the trend."),
]

CUSTOMER_COLUMNS = [
    ("customer", "text", "Customer (brand) name. Join key."),
    ("n_skus", "int", "Number of the customer's products in the Konvy catalogue."),
    ("portfolio_categories", "text", "Largest categories as 'category:count', separated by '; '."),
    ("price_min_thb", "real", "Cheapest product, THB."),
    ("price_median_thb", "real", "Median product price, THB."),
    ("price_max_thb", "real", "Most expensive product, THB."),
    ("overall_level", "text", f"Overall readiness: {' / '.join(FIT_LEVELS)}. The highest level that MORE than half of the checked trends reach."),
    ("overall_trends_at_level", "int", "How many checked trends reach overall_level or better."),
    ("n_trends_checked", "int", "Trends checked for this customer."),
    ("n_excellent", "int", "Trends graded excellent."),
    ("n_good", "int", "Trends graded good."),
    ("n_average", "int", "Trends graded average."),
    ("n_below_average", "int", "Trends graded below_average."),
    ("one_trend_from_level", "text", "If set: one more trend at or above this level would lift overall_level to it."),
    ("strongest_trend_id", "text", "Trend where the customer's best product is graded best."),
    ("opportunity_trend_id", "text", "Fastest-growing trend where the customer is not yet ready (quadrant build)."),
    ("quick_win_trend_id", "text", "Trend (below excellent) where the customer's best product is closest to the market leader."),
    ("build_trend_ids", "text", "Growing trends where the customer is not ready (quadrant build), by growth, separated by '; '."),
    ("not_checked_trends", "text", "Trends in the report with no result for this customer (the customer's search was run on an older trend list)."),
]

CUSTOMER_TREND_COLUMNS = [
    ("customer", "text", "Customer (brand) name (join to customers)."),
    ("trend_id", "text", "Trend id (join to trends)."),
    ("trend", "text", "Display name of the trend."),
    ("checked", "int", "1 = the customer was checked on this trend; 0 = no result (fit columns are empty)."),
    ("fit_level", "text", f"Customer's grade on the trend: {' / '.join(FIT_LEVELS)}. Best product in the trend's main category, by similarity alone."),
    ("quadrant", "text", f"Action group: {' / '.join(QUADRANTS)}. defend = growing trend and customer ready; build = growing, not ready; "
                         "maintain = slower, ready; monitor = slower, not ready."),
    ("main_category", "text", "Category (L2) the customer was compared in."),
    ("has_product_in_category", "int", "0 = the customer has no product in the trend's main category (fit_level is then below_average)."),
    ("expected_pct_short", "real", f"Trend's expected search level in year {SHORT_YEAR} vs last 12 months, % (copy of trends.expected_pct_y{SHORT_YEAR})."),
    ("expected_pct_long", "real", f"Same at year {LONG_YEAR}."),
    ("growth_score_short", "real", f"Trend's growth score at year {SHORT_YEAR}, 0-1."),
    ("own_product", "text", "Customer's best product for this trend (the one that sets fit_level)."),
    ("own_price_thb", "real", "Its price, THB."),
    ("own_size", "real", "Pack size in own_unit_label."),
    ("own_unit_label", "text", "ml / g / pc ..."),
    ("own_unit_price_thb", "real", "Price per unit_label, THB."),
    ("own_is_mini", "int", "1 = trial/mini size."),
    ("own_similarity", "real", "Cosine similarity between the product and the trend description."),
    ("own_rank_in_category", "int", "Its similarity rank among all Konvy products in the category (1 = closest)."),
    ("own_category_size", "int", "Number of Konvy products in the category."),
    ("own_top_pct_in_category", "real", "Its similarity position as 'top X%' of the category (0.58 = top 0.58%)."),
    ("own_reason_en", "text", "Why the product matches the trend (English)."),
    ("own_reason_th", "text", "Same in Thai (empty if the Thai report was not built)."),
    ("leader_brand", "text", "Brand of the closest Konvy product to the trend in that category."),
    ("leader_product", "text", "That product."),
    ("leader_price_thb", "real", "Its price, THB."),
    ("leader_similarity", "real", "Its similarity to the trend."),
    ("leader_is_customer", "int", "1 = the market leader is the customer's own product."),
    ("gap_to_leader", "real", "leader_similarity minus own_similarity (0 = no gap; smaller = closer to the leader)."),
]

TABLES = {   # ชื่อตาราง -> (ไฟล์ CSV, คอลัมน์, คำอธิบาย) · ลำดับ = ลำดับเขียน
    "trends": ("trends.csv", TREND_COLUMNS, "One row per trend of the run (all trends, including those below the market line). Shared by all customers."),
    "trend_top_products": ("trend_top_products.csv", TOP_PRODUCT_COLUMNS, "The 5 Konvy products closest to each trend. Shared by all customers."),
    "customers": ("customers.csv", CUSTOMER_COLUMNS, "One row per customer: overall readiness and portfolio."),
    "customer_trends": ("customer_trends.csv", CUSTOMER_TREND_COLUMNS, "One row per customer x trend with the customer's grade, best product and the market leader."),
}


def _at(values, year):
    """ลิสต์ต่อปี (ตำแหน่ง 0 = ปีที่ 1) -> ค่าของปีที่ year (ไม่มี = None)"""
    return values[year - 1] if isinstance(values, list) and len(values) >= year else None


def _num(value, digits=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(value, digits) if digits is not None else value


def _flag(value):
    return None if value is None else int(bool(value))


def _slug(name, taken):
    base = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")[:60] or "trend"
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    taken.add(slug)
    return slug


def _compact(obj):
    """ตัดช่องที่ไม่มีค่า (None / "" / ลิสต์-dict ว่าง) ออกจาก brief - 0 และ False ยังอยู่"""
    if isinstance(obj, dict):
        out = {k: _compact(v) for k, v in obj.items()}
        return {k: v for k, v in out.items() if v is not None and v != "" and v != {} and v != []}
    if isinstance(obj, list):
        return [_compact(v) for v in obj]
    return obj


def choose_run(name):
    """--run > TREND_RUN_ID > รอบล่าสุดที่มี phase6_report_context.json"""
    name = name or os.environ.get("TREND_RUN_ID")
    if name:
        run_dir = OUTPUT_ROOT if name == "_legacy_flat" else OUTPUT_ROOT / name
        if not (run_dir / CONTEXT_FILE).exists():
            raise SystemExit(f"❌ รอบ '{name}' ไม่มี {CONTEXT_FILE} - ต้องสร้างรายงานเทรนด์ (⑯) ของรอบนี้ก่อน")
        return run_dir
    runs = [p.parent for p in OUTPUT_ROOT.glob(f"*/{CONTEXT_FILE}")]
    if not runs:
        raise SystemExit(f"❌ ไม่พบรอบที่มี {CONTEXT_FILE} ใน {OUTPUT_ROOT}")
    run_dir = max(runs, key=lambda p: (p / CONTEXT_FILE).stat().st_mtime)
    print(f"ไม่ได้ระบุ --run - ใช้รอบล่าสุดที่มี {CONTEXT_FILE}: {run_dir.name}")
    return run_dir


# ---------------------------------------------------------------------------
# ตารางเทรนด์ (ใช้ร่วมทุกลูกค้า)
# ---------------------------------------------------------------------------
def build_trends(ctx):
    """ctx = phase6_report_context.json -> (แถว trends, แถว trend_top_products, {ชื่อเทรนด์: trend_id})
    ชื่อเทรนด์ไม่ซ้ำกันในรอบ - ไฟล์ของแบรนด์ (⑰) เก็บเทรนด์เป็นชื่ออย่างเดียว จึงจับคู่ด้วยชื่อ"""
    detail = {t.get("key"): t for t in ctx.get("trends") or []}
    taken, rows, tops, by_name = set(), [], [], {}
    for g in (ctx.get("growth") or {}).get("all") or []:
        t = detail.get(g.get("key")) or {}
        a = t.get("analysis") or {}
        tid = _slug(g["name"], taken)
        by_name[g["name"]] = tid
        row = {
            "trend_id": tid, "name": g["name"], "display_name": g.get("display_name") or t.get("display_name") or g["name"],
            "stream": g.get("stream"), "rank_short": g.get("rank"), "rank_long": g.get("long_rank"),
            "above_market_line": _flag(g.get("above_line")), "in_product_analysis": int(g.get("detail_rank") is not None),
            "no_close_product": int(bool(t.get("no_close_product"))) if t else None,   # 🆕 (2026-10-28) common/match_quality.py
            "match_basis": t.get("match_basis") if t else None,   # 🆕 (2026-10-28) need = ความต้องการความงามที่ AI อนุมาน / evidence = คำค้นอย่างเดียว
            "cagr_pct_short": _num(_at(g.get("cagr_pct"), SHORT_YEAR)), "cagr_pct_long": _num(_at(g.get("cagr_pct"), LONG_YEAR)),
            "past_growth_pct": _num(g.get("past_growth_pct")), "recent_decline": _flag(g.get("recent_decline")),
            "main_category": (t.get("l2") or {}).get("category") or ((g.get("categories") or [None])[0]),
            "trend_stage": a.get("trend_stage"), "primary_driver": a.get("primary_driver"), "estimated_duration": a.get("estimated_duration"),
            "longevity_score": t.get("longevity_score"), "longevity_band": t.get("longevity_band"),
            "data_quality": t.get("data_quality"), "n_keywords": t.get("cluster_size"),
            "keywords": "; ".join(t.get("keywords") or g.get("keywords") or []) or None,
            "target_consumer": t.get("target"), "key_ingredients": t.get("key_ingredients"), "key_benefits": t.get("key_benefits"),
            "executive_summary": a.get("executive_summary"), "consumer_intent": a.get("consumer_intent_signal"),
            "risk_if_forecast_fails": a.get("risk_scenario_if_forecast_fails"),
        }
        for y in YEARS:
            row[f"expected_pct_y{y}"] = _num(_at(g.get("expected_pct"), y))
            row[f"growth_score_y{y}"] = _num(_at(g.get("scores"), y))
        rows.append(row)
        for pos, p in enumerate([] if t.get("no_close_product") else (t.get("products") or [])[:5], start=1):   # ไม่มีสินค้าที่ใกล้พอ = ไม่ส่งสินค้า "ใกล้เทรนด์ที่สุด"
            tops.append({"trend_id": tid, "pos": pos, "brand": p.get("brand"), "product": p.get("name") or p.get("name_full"),
                         "price_thb": _num(p.get("price_thb")), "size": _num(p.get("size")), "unit_label": p.get("unit_label"),
                         "unit_price_thb": _num(p.get("unit_price"), 2), "is_mini": _flag(p.get("is_mini")),
                         "similarity": _num(p.get("similarity"), 4), "reason": p.get("reason")})
    return rows, tops, by_name


# ---------------------------------------------------------------------------
# ตารางลูกค้า
# ---------------------------------------------------------------------------
def _own_reason_th(bctx, row):
    """คำแปลไทยของเหตุผลจับคู่สินค้าที่ให้เกรด (reasons_th เรียงตาม row["products"]) - ไม่มี = None"""
    g = row.get("graded") or {}
    texts = (bctx.get("reasons_th") or {}).get(row.get("name")) or []
    for p, text in zip(row.get("products") or [], texts):
        if p.get("name_full") == g.get("name_full") and p.get("category") == g.get("category"):
            return text
    return None


def build_customer(bctx, by_name, trends_by_id):
    """phase6_brand_context_<แบรนด์>.json -> (แถว customers, [แถว customer_trends])"""
    brand = bctx["brand"]
    tid_of = {}      # อันดับของเทรนด์ในรายงานแบรนด์ -> trend_id (ไว้แปลง highlights)
    ct_rows = []
    for r in bctx.get("rows") or []:
        tid = by_name.get(r.get("name"))
        if tid is None:
            continue
        tid_of[r.get("rank")] = tid
        tr = trends_by_id[tid]
        g, leader = r.get("graded") or {}, r.get("leader") or {}
        ct_rows.append({
            "customer": brand, "trend_id": tid, "trend": tr["display_name"], "checked": int(bool(r.get("checked"))),
            "fit_level": r.get("level"),
            "quadrant": r.get("quadrant"), "main_category": (r.get("key_categories") or [None])[0],
            "has_product_in_category": None if not r.get("checked") else int(not r.get("no_key_product")),
            "expected_pct_short": tr[f"expected_pct_y{SHORT_YEAR}"], "expected_pct_long": tr[f"expected_pct_y{LONG_YEAR}"],
            "growth_score_short": tr[f"growth_score_y{SHORT_YEAR}"],
            "own_product": g.get("name"), "own_price_thb": _num(g.get("price_thb")), "own_size": _num(g.get("size")),
            "own_unit_label": g.get("unit_label"), "own_unit_price_thb": _num(g.get("unit_price"), 2), "own_is_mini": _flag(g.get("is_mini")) if g else None,
            "own_similarity": _num(g.get("similarity"), 4), "own_rank_in_category": g.get("rank_in_tier"), "own_category_size": g.get("n_tier"),
            "own_top_pct_in_category": _num(g.get("pct"), 2), "own_reason_en": g.get("reason"), "own_reason_th": _own_reason_th(bctx, r),
            "leader_brand": leader.get("brand"), "leader_product": leader.get("name"), "leader_price_thb": _num(leader.get("price_thb")),
            "leader_similarity": _num(leader.get("similarity"), 4), "leader_is_customer": _flag(leader.get("is_you")) if leader else None,
            "gap_to_leader": _num(r.get("gap_to_leader"), 4),
        })
    port, overall, counts = bctx.get("portfolio") or {}, bctx.get("overall") or {}, bctx.get("counts") or {}
    hl = bctx.get("highlights") or {}
    cust = {
        "customer": brand, "n_skus": bctx.get("n_skus"),
        "portfolio_categories": "; ".join(f"{c['name']}:{c['n']}" for c in port.get("top_subcategories") or []) or None,
        "price_min_thb": port.get("price_min"), "price_median_thb": port.get("price_median"), "price_max_thb": port.get("price_max"),
        "overall_level": overall.get("level"), "overall_trends_at_level": overall.get("k"), "n_trends_checked": bctx.get("n_checked"),
        "n_excellent": counts.get("excellent"), "n_good": counts.get("good"), "n_average": counts.get("average"),
        "n_below_average": counts.get("below_average"), "one_trend_from_level": (overall.get("next") or {}).get("level"),
        "strongest_trend_id": tid_of.get(hl.get("strongest")), "opportunity_trend_id": tid_of.get(hl.get("opportunity")),
        "quick_win_trend_id": tid_of.get(hl.get("quick_win")),
        "build_trend_ids": "; ".join(tid_of[x] for x in bctx.get("opportunities") or [] if x in tid_of) or None,
        "not_checked_trends": "; ".join(bctx.get("missing_trends") or []) or None,
    }
    return cust, ct_rows


# ---------------------------------------------------------------------------
# brief ต่อลูกค้า (อ่านจบในตัว)
# ---------------------------------------------------------------------------
BRIEF_NOTES = [
    "Levels (best to worst): excellent, good, average, below_average. A level compares the customer's best product in the trend's main category "
    "(L2) with all Konvy products of that category by closeness to the trend. It is a relative rank, not product quality.",
    "Forecast numbers are expected Google Trends search interest vs the last 12 months, not sales. Use them to order trends; do not present year-4/5 "
    "percentages as promises (see meta.json reliability_notes).",
    "Use the levels and numbers as given; do not re-grade. Fields with no value are left out (unknown, not zero). Do not mix this customer's data "
    "with another customer's.",
]


def overall_meaning(overall):
    """เกรดรวมเป็นประโยค (ระดับต่ำสุด below_average ไม่มีความหมายว่า "ถึงขึ้นไป" จึงบอกจำนวนที่ถึง average แทน)"""
    if not overall:
        return None
    level, n = overall.get("level"), overall.get("n")
    if level == FIT_LEVELS[-1]:
        return (f"only {(overall.get('at_or_better') or {}).get(FIT_LEVELS[-2])} of {n} checked trends reach {FIT_LEVELS[-2]} or better, "
                f"so no level above {level} is reached by more than half of them")
    return (f"{overall.get('k')} of {n} checked trends reach {level} or better "
            f"(overall level = highest level reached by more than half of the trends)")


def build_brief(meta, bctx, cust, ct_rows, trends_by_id, tops_by_id):
    def entry(ct):
        tr = trends_by_id[ct["trend_id"]]
        has = ct["checked"] and ct["has_product_in_category"]
        return {
            "trend_id": ct["trend_id"], "trend": ct["trend"], "stage": tr["trend_stage"], "what_it_is": tr["executive_summary"],
            "consumer_intent": tr["consumer_intent"],
            "forecast": {"search_change_pct_vs_last_12m": {SY: ct["expected_pct_short"], LY: ct["expected_pct_long"]},
                         "growth_score": {SY: ct["growth_score_short"], LY: tr[f"growth_score_y{LONG_YEAR}"]},
                         "past_12m_change_pct": tr["past_growth_pct"]},
            "fit": {"level": ct["fit_level"],
                    "action_group": ct["quadrant"], "category": ct["main_category"], "has_product_in_category": bool(ct["has_product_in_category"])
                    if ct["checked"] else None},
            "best_product": None if not has else {
                "name": ct["own_product"], "price_thb": ct["own_price_thb"], "size": ct["own_size"], "unit": ct["own_unit_label"],
                "unit_price_thb": ct["own_unit_price_thb"], "is_mini": bool(ct["own_is_mini"]),
                "similarity": ct["own_similarity"], "rank_in_category": ct["own_rank_in_category"], "category_size": ct["own_category_size"],
                "top_pct_in_category": ct["own_top_pct_in_category"],
                "why_it_matches": ct["own_reason_en"], "why_it_matches_th": ct["own_reason_th"]},
            "closest_market_products": None if ct["leader_product"] or not ct["checked"] else [
                {"brand": t["brand"], "product": t["product"], "price_thb": t["price_thb"], "similarity": t["similarity"], "why_it_matches": t["reason"]}
                for t in tops_by_id.get(ct["trend_id"], [])[:3]],
            "market_leader": None if not ct["leader_product"] else {
                "brand": ct["leader_brand"], "product": ct["leader_product"], "price_thb": ct["leader_price_thb"],
                "similarity": ct["leader_similarity"], "is_customer_product": bool(ct["leader_is_customer"]),
                "similarity_gap_to_customer": ct["gap_to_leader"]},
        }

    def named(tid):
        return None if tid is None else {"trend_id": tid, "trend": trends_by_id[tid]["display_name"]}

    checked = [c for c in ct_rows if c["checked"]]
    overall = bctx.get("overall") or {}
    n = overall.get("n")
    return _compact({
        "schema_version": SCHEMA_VERSION, "run_id": meta["run"]["run_id"], "data_as_of": meta["run"]["data_as_of"],
        "customer": cust["customer"],
        "summary": {
            "overall_level": cust["overall_level"],
            "overall_meaning": overall_meaning(overall),
            "one_more_trend_would_lift_to": cust["one_trend_from_level"],
            "trends_by_level": {lv: cust[f"n_{lv}"] for lv in FIT_LEVELS},
            "strongest_trend": named(cust["strongest_trend_id"]),
            "growth_opportunity_not_ready": named(cust["opportunity_trend_id"]),
            "quick_win_closest_to_market_leader": named(cust["quick_win_trend_id"]),
            "growing_trends_not_ready": [named(t) for t in (cust["build_trend_ids"] or "").split("; ") if t],
            "portfolio": {"n_skus": cust["n_skus"], "price_thb": {"min": cust["price_min_thb"], "median": cust["price_median_thb"], "max": cust["price_max_thb"]},
                          "top_categories": [{"category": c["name"], "n": c["n"]} for c in (bctx.get("portfolio") or {}).get("top_subcategories") or []]},
        },
        "market_median_search_change_pct": meta["market_median_expected_pct"],
        "trends": [entry(c) for c in checked],
        "trends_without_result": [c["trend"] for c in ct_rows if not c["checked"]],
        "notes": BRIEF_NOTES,
    })


# ---------------------------------------------------------------------------
# meta.json
# ---------------------------------------------------------------------------
def build_meta(run_dir, ctx, bctxs, customers):
    m, growth = ctx.get("meta") or {}, ctx.get("growth") or {}
    first = bctxs[0] if bctxs else {}
    top = first.get("top_pct") or {"excellent": 1, "good": 5, "average": 20}
    band = growth.get("band") or {}
    market = growth.get("market_pct") or []
    products = (m.get("sources") or {}).get("products") or {}
    warnings = []
    for b in bctxs[1:]:
        if b.get("top_pct") != first.get("top_pct"):
            warnings.append(f"{b.get('brand')}: grading thresholds differ from {first.get('brand')} (⑰ built under another config) - rerun ⑰ for consistent grades")
    notes = [
        "The forecast is expected worldwide Google Trends search interest, not sales or revenue. It has never been checked against real sales data.",
        "Back-test (walk-forward on past years, about 130 keywords): the ranking of keywords correlates with realised growth at about 0.5 (Spearman) "
        f"at year 1, falling to about 0.4 at year {LONG_YEAR}. It is useful for ordering trends, weak for exact numbers.",
        f"Error band: in back-tests the realised level was within {band.get('short', [None, None])[0]}% to +{band.get('short', [None, None])[1]}% of the forecast "
        f"at year {SHORT_YEAR} and {band.get('long', [None, None])[0]}% to +{band.get('long', [None, None])[1]}% at year {LONG_YEAR} in 80% of cases "
        f"(forecast_band_80_pct). Years 4-5 are the least reliable; never quote them as promises.",
        "Past growth (past_growth_pct) is inflated for every trend by a jump in the Google Trends data from Aug 2025; compare trends with each other." if growth.get("past_inflated") else None,
        "Fit grades are relative: they rank the customer's products against Konvy's catalogue only (one online retailer). They use description "
        "similarity only - sales are not part of the grade.",
    ]
    return {
        "schema_version": SCHEMA_VERSION, "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run": {"run_id": m.get("run_id") or run_dir.name, "topic": m.get("topic"), "title": m.get("title"),
                "data_as_of": m.get("data_as_of"), "forecast_start": m.get("forecast_start"), "forecast_end": m.get("forecast_end"),
                "n_trends_total": growth.get("n_total"), "n_trends_with_product_analysis": growth.get("n_detail"),
                "n_products_compared": m.get("n_products_compared"),
                "catalogue": f"Konvy online catalogue, collected {products.get('collected_from')} to {products.get('collected_to')}"},
        "horizons": {"years": list(YEARS), "short_year": SHORT_YEAR, "long_year": LONG_YEAR,
                     "meaning": f"short term = years 1-{SHORT_YEAR} (ranked at year {SHORT_YEAR}); long term = years {SHORT_YEAR + 1}-{LONG_YEAR} (ranked at year {LONG_YEAR})"},
        "market_median_expected_pct": {f"year_{y}": _at(market, y) for y in YEARS},
        "forecast_band_80_pct": {SY: band.get("short"), LY: band.get("long")},
        "reliability_notes": [x for x in notes if x],
        "grading": {
            "levels": list(FIT_LEVELS),
            "product_level": (f"The customer's products in a trend's main category (L2) are ranked by similarity to the trend against all Konvy products "
                              f"of that category: top {top['excellent']}% = excellent, top {top['good']}% = good, top {top['average']}% = average, "
                              f"otherwise below_average. Sales are not used."),
            "trend_level": "Best product level of the customer in the trend's main category; no product there = below_average (has_product_in_category = 0).",
            "overall_level": "Highest level reached by MORE than half of the checked trends (exactly half does not count).",
            "action_groups": {"growth_split": first.get("momentum_split"),
                              "meaning": "growth = year-%d growth score of the trend vs the median of the listed trends; ready = excellent or good. "
                                         "defend = high growth & ready; build = high growth & not ready; maintain = lower growth & ready; "
                                         "monitor = lower growth & not ready." % SHORT_YEAR},
        },
        "usage_notes": [
            "Read this file first. Each customer brief in briefs/ stands alone; the CSV tables and llm_export.sqlite hold the same facts for queries across customers.",
            "Levels and numbers come from the finished reports; use them as given and do not re-grade.",
            "Use display_name when writing to customers; name is the technical title.",
            "Empty values mean 'not available', not zero. Briefs leave such fields out.",
            "Product names belong to each customer. Keep one customer's data out of another customer's output.",
        ],
        "customers": [c["customer"] for c in customers],
        "warnings": warnings,
        "files": {"meta.json": "this file", "briefs/<customer>.json": "self-contained summary per customer (put straight into a prompt)",
                  "llm_export.sqlite": "all tables below + glossary (table, column, type, description) + run_info",
                  **{f: d for f, _c, d in TABLES.values()}},
        "tables": {name: {"file": f, "description": d, "columns": [{"name": c, "type": t, "description": x} for c, t, x in cols]}
                   for name, (f, cols, d) in TABLES.items()},
    }


# ---------------------------------------------------------------------------
# เขียนไฟล์
# ---------------------------------------------------------------------------
def _matrix(columns, rows):
    """แถว dict -> แถวลิสต์ตามลำดับคอลัมน์ (คีย์เกินสเปค = ผิดพลาด กันสเปคกับข้อมูลเพี้ยนกัน)"""
    names = [c for c, _t, _d in columns]
    for r in rows:
        extra = set(r) - set(names)
        if extra:
            raise ValueError(f"แถวมีคอลัมน์ที่ไม่อยู่ในสเปค: {sorted(extra)}")
    return [[r.get(c) for c in names] for r in rows]


def write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:      # utf-8-sig: Excel อ่านภาษาไทยได้
        w = csv.writer(f)
        w.writerow([c for c, _t, _d in columns])
        w.writerows(_matrix(columns, rows))


def write_sqlite(path, tables, meta):
    """tables = {ชื่อ: (คอลัมน์, แถว)} -> ไฟล์ SQLite ใหม่ (+ glossary + run_info ให้ LLM ถามความหมายคอลัมน์ผ่าน SQL ได้)"""
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    try:
        for name, (columns, rows) in tables.items():
            ddl = ", ".join('"%s" %s' % (c, SQL_TYPES[t]) for c, t, _d in columns)
            con.execute('CREATE TABLE "%s" (%s)' % (name, ddl))
            con.executemany('INSERT INTO "%s" VALUES (%s)' % (name, ",".join("?" * len(columns))), _matrix(columns, rows))
        con.execute("CREATE TABLE glossary (table_name TEXT, column_name TEXT, type TEXT, description TEXT)")
        con.executemany("INSERT INTO glossary VALUES (?,?,?,?)",
                        [(name, c, t, d) for name, (columns, _r) in tables.items() for c, t, d in columns])
        con.execute("CREATE TABLE run_info (key TEXT, value TEXT)")
        info = {"schema_version": meta["schema_version"], **meta["run"], "short_year": SHORT_YEAR, "long_year": LONG_YEAR,
                "reliability_notes": " | ".join(meta["reliability_notes"])}
        con.executemany("INSERT INTO run_info VALUES (?,?)", [(k, None if v is None else str(v)) for k, v in info.items()])
        con.commit()
    finally:
        con.close()


def write_json(path, data, indent=2):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


def export(run_dir, out_dir=None):
    """อ่านไฟล์ของรอบแล้วเขียนชุด llm_export - คืน {"out_dir", "n_trends", "customers": [...]}"""
    run_dir = Path(run_dir)
    out_dir = Path(out_dir) if out_dir else run_dir / EXPORT_DIR
    ctx = read_json(run_dir / CONTEXT_FILE)
    if not ctx or not (ctx.get("growth") or {}).get("all"):
        raise SystemExit(f"❌ {CONTEXT_FILE} ว่างหรือไม่มีเทรนด์ - สร้างรายงานเทรนด์ (⑯) ของรอบนี้ใหม่")

    trend_rows, top_rows, by_name = build_trends(ctx)
    trends_by_id = {r["trend_id"]: r for r in trend_rows}
    tops_by_id = {}
    for t in top_rows:
        tops_by_id.setdefault(t["trend_id"], []).append(t)
    bctxs = []
    for path in sorted(run_dir.glob(BRAND_GLOB)):
        b = read_json(path)
        if b and b.get("brand") and b.get("rows"):
            bctxs.append(b)
        else:
            print(f"  ⚠️ ข้าม {path.name} (ไฟล์ว่างหรือไม่มี rows)")
    if not bctxs:
        print("  ⚠️ รอบนี้ยังไม่มีผลแบรนด์ (⑰) - ส่งออกเฉพาะตารางเทรนด์")

    pairs = [build_customer(b, by_name, trends_by_id) for b in bctxs]
    customers = [c for c, _ in pairs]
    ct_rows = [r for _, rows in pairs for r in rows]
    meta = build_meta(run_dir, ctx, bctxs, customers)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "briefs").mkdir(exist_ok=True)
    for stale in (out_dir / "briefs").glob("*.json"):      # แบรนด์ที่หายไปจากรอบ ไม่ให้ brief เก่าค้าง
        stale.unlink()
    data = {"trends": trend_rows, "trend_top_products": top_rows, "customers": customers, "customer_trends": ct_rows}
    for name, (fname, columns, _d) in TABLES.items():
        write_csv(out_dir / fname, columns, data[name])
    write_sqlite(out_dir / "llm_export.sqlite", {n: (cols, data[n]) for n, (_f, cols, _d) in TABLES.items()}, meta)
    write_json(out_dir / "meta.json", meta)
    for b, (cust, rows) in zip(bctxs, pairs):
        write_json(out_dir / "briefs" / f"{safe_file_part(cust['customer'])}.json", build_brief(meta, b, cust, rows, trends_by_id, tops_by_id), indent=1)
    return {"out_dir": out_dir, "n_trends": len(trend_rows), "customers": [c["customer"] for c in customers], "warnings": meta["warnings"]}


def main():
    parser = argparse.ArgumentParser(description="⑳ ส่งออกผลเทรนด์ + ผลลูกค้าเป็นไฟล์สำหรับ LLM (brief ต่อลูกค้า + ตารางรวม + ตารางเทรนด์กลาง)")
    parser.add_argument("--run", default=None, help="ชื่อโฟลเดอร์รอบใน main/output (ไม่ใส่ = TREND_RUN_ID หรือรอบล่าสุด)")
    parser.add_argument("--out", default=None, help="โฟลเดอร์ปลายทาง (ค่าเริ่มต้น <รอบ>/llm_export)")
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    run_dir = choose_run(args.run)
    print("=" * 70)
    print(f"⑳ LLM export — รอบ {run_dir.name}")
    print("=" * 70)
    try:
        result = export(run_dir, args.out)
    except PermissionError as e:
        raise SystemExit(f"❌ เขียนไฟล์ไม่ได้ ({e.filename}) - ปิดไฟล์ที่เปิดค้างอยู่แล้วรันใหม่")
    out_dir = result["out_dir"]
    print(f"เทรนด์ {result['n_trends']} · ลูกค้า {len(result['customers'])}: {', '.join(result['customers']) or '-'}")
    for w in result["warnings"]:
        print(f"  ⚠️ {w}")
    for p in sorted(out_dir.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(out_dir)}  {p.stat().st_size / 1024:,.0f} KB")
    print(f"\n✅ บันทึกแล้ว: {out_dir}")


if __name__ == "__main__":
    main()
