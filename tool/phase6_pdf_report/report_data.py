# -*- coding: utf-8 -*-
"""
⑯ PDF Report — ชั้นข้อมูล: อ่านไฟล์ผลรันในโฟลเดอร์รอบ แล้วประกอบเป็น dict เดียว (context) ที่เทมเพลตใช้

ไม่ import bootstrap และไม่เรียก API - อ่านไฟล์อย่างเดียว จึงเทสได้ด้วยโฟลเดอร์รอบปลอม (ดู tests/test_pdf_report.py)
ไฟล์ไหนไม่มี -> ส่วนนั้นว่างเปล่า + จดไว้ใน context["missing"] ให้หน้า appendix แจ้ง แทนที่จะพังทั้งรายงาน
(ยกเว้นผล ⑪ ที่เป็นตัวกำหนดชุด Top N - ไม่มีไฟล์นี้ก็ไม่มีเทรนด์ให้ทำรายงาน)

ตัวเลขทุกตัวในรายงานมาจากไฟล์ตรงนี้เท่านั้น - ส่วนที่ใช้ LLM (enrich.py) แค่เรียบเรียงข้อความภาษาอังกฤษ ไม่แตะตัวเลข
สาย Paper/Social/News ยังเก็บไว้ใน context (ใช้เป็นคีย์จับคู่ข้ามไฟล์) แต่เทมเพลตไม่แสดง - เจ้าของงานขอไม่ให้บอกสาย
"""
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

HIGHLIGHTS_FILE = "phase3_trend_highlights_result.json"
RANK_FILE = "phase2_rank_score_final_mode_result.json"
LONGEVITY_FILE = "phase2_longevity_cross_source_result.json"
FORECAST_FILE = "phase2_paper_social_z_delta_result.json"
CATEGORY_FILE = "phase2_category_overall_result.json"
MATCH_FILE = "phase3_scale_validation_nvidia_result.json"
STEPIC_FINAL_FILE = "phase4_stepic_final_insight.json"
STEPIC_RAW_FILE = "phase4_stepic_raw_analysis.json"
MANIFEST_FILE = "_manifest.json"
FORECAST_SUBDIR = "serpapi_forecast_run"
STREAM_FILES = {
    "Paper": "phase1_paper_stream_result.json",
    "Social": "phase2_social_stream_result.json",
    "News": "phase2_news_stream_result.json",
}

# ลำดับคอลัมน์ของ master_report ใน phase2_paper_social_z_delta_result.json (แถวเป็น list ไม่มีชื่อคอลัมน์ -
# ลำดับเดียวกับ Plot_trend_map.py's MASTER_REPORT_COLS ซึ่งตรวจกับ trend_final_v2_subset.py แล้ว)
MASTER_REPORT_COLS = ["cluster_id", "trend", "model", "status", "current_z", "forecast_avg_z", "z_delta",
                      "peak_month", "keywords", "context", "data_quality", "pct_months_with_data"]

# ข้อความภาษาไทยที่ขั้นก่อนหน้าเขียนไว้เป็นค่าตายตัว -> ภาษาอังกฤษ (รายงานเป็นภาษาอังกฤษทั้งเล่ม)
# ต้องตรงกับ extract_trend_highlights.py's exclusion_reason() ทุกตัวอักษร
EXCLUSION_REASON_EN = {
    "เทรนด์ประเภทช่องทาง/พฤติกรรมการซื้อ - ไม่มีคุณสมบัติสินค้าให้จับคู่":
        "Sales-channel / shopping-behaviour trend - no product attributes to match against products",
    "ข้อมูลไม่พอทุกช่องที่ใช้จับคู่สินค้า": "Not enough product information to match against products",
}
# เหตุผลที่ไม่ได้มาจาก ⑪ (ค่าที่ build_context ใส่เองเมื่อไม่มีเหตุผล) -> ภาษาไทย สำหรับฉบับภาษาไทย
EXCLUSION_REASON_TH = {"Trend profile extraction failed": "สกัดจุดเด่นเทรนด์ไม่สำเร็จ"}

_THAI_RE = re.compile(r"[฀-๿]+")
_SMALL_WORDS = {"and", "or", "of", "in", "on", "for", "the", "a", "an", "to", "with", "vs"}


# ============================================================================
# ตัวช่วยทั่วไป
# ============================================================================
def read_json(path):
    """คืน None ถ้าไฟล์ไม่มี/อ่านไม่ได้ - ผู้เรียกตัดสินเองว่าจะข้ามส่วนนั้นหรือหยุด"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def has_thai(text):
    return bool(_THAI_RE.search(str(text or "")))


def strip_thai(text):
    """ตัดตัวอักษรไทยออก - ชื่อสินค้า Watsons หลายตัวมีคำอธิบายภาษาไทยต่อท้าย (เช่น "... 100 G. ครีมบำรุงผิวหน้า")
    ซึ่งรายงานภาษาอังกฤษไม่ต้องการ แล้วเก็บกวาดช่องว่าง/เครื่องหมายที่เหลือค้าง"""
    text = _THAI_RE.sub(" ", str(text or ""))
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -–|,/").strip()


def smart_title(text):
    """"beauty and personal care" -> "Beauty and Personal Care" (คำเชื่อมสั้นๆ ไม่ขึ้นตัวใหญ่ยกเว้นคำแรก,
    คำที่มีตัวใหญ่อยู่แล้ว เช่น "K-Beauty"/"SPF" คงไว้ตามเดิม)"""
    words = str(text or "").strip().split()
    out = []
    for i, w in enumerate(words):
        if w != w.lower():
            out.append(w)
        elif i > 0 and w in _SMALL_WORDS:
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def first_sentences(text, max_chars):
    """ตัดข้อความยาวที่ขอบประโยค (ไม่เกิน max_chars) - ใช้กับช่องที่พื้นที่จำกัด เช่น ช่อง STEPIC
    ถ้าประโยคแรกยาวเกินเองให้ตัดที่ขอบคำแล้วต่อ "…" (ไม่ตัดกลางคำ)"""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= max_chars:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = ""
    for s in sentences:
        candidate = f"{out} {s}".strip()
        if len(candidate) > max_chars:
            break
        out = candidate
    if out:
        return out
    return text[:max_chars].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def split_headline(text, max_chars=70):
    """แยก "หัวข้อ: รายละเอียด" (รูปแบบที่ STEPIC ตอบบ่อย) เป็น (headline, rest) - ไม่มี ":" ใช้ประโยคแรกแทน"""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if ":" in text[:max_chars + 1]:
        head, rest = text.split(":", 1)
        return head.strip(), rest.strip()
    head = first_sentences(text, max_chars)
    rest = text[len(head):].strip() if not head.endswith("…") else text
    return head.rstrip("."), rest


def _num(value):
    try:
        return None if value is None or pd.isna(value) else float(value)
    except (TypeError, ValueError):
        return None


# ============================================================================
# โหลดแต่ละส่วน
# ============================================================================
def load_master_report(forecast):
    """แถว master_report (list) -> {ชื่อคลัสเตอร์: dict ตาม MASTER_REPORT_COLS}"""
    rows = {}
    for row in (forecast or {}).get("master_report", []):
        if not isinstance(row, (list, tuple)) or len(row) < len(MASTER_REPORT_COLS):
            continue
        rec = dict(zip(MASTER_REPORT_COLS, row))
        rows[rec["trend"]] = rec
    return rows


def load_trend_rows(run_dir):
    """แถวเทรนด์เต็ม (Target/Key Benefits/Longevity ฯลฯ) -> {(stream, ชื่อเทรนด์): row}
    ใช้ Longevity ที่ปรับข้ามสายแล้ว (⑥) ก่อน ถ้าไม่มีค่อยใช้แถวดิบจากไฟล์ผลแต่ละสาย (เหมือน run_stepic_report.py)"""
    rows = {}
    for stream, fname in STREAM_FILES.items():
        for t in (read_json(run_dir / fname) or {}).get("trends", []):
            rows[(stream, t.get("Trend Name"))] = t
    cross = read_json(run_dir / LONGEVITY_FILE) or {}
    for stream, trends in cross.items():
        if not isinstance(trends, list):
            continue
        for t in trends:
            key = (stream, t.get("Trend Name"))
            rows[key] = {**rows.get(key, {}), **t}
    return rows


def load_product_catalog(csv_path):
    """{(brand, product_name): {image, url}} จาก watsons_product.csv - ผล ⑫ ไม่ได้เก็บรูป/ลิงก์ไว้ จึงต้อง join
    ด้วยชื่อ (ชื่อซ้ำมี 14 แถวจาก 10,622 - ใช้แถวแรก)"""
    if not csv_path or not Path(csv_path).exists():
        return {}
    df = pd.read_csv(csv_path, encoding="utf-8-sig", low_memory=False,
                     usecols=["brand", "product_name", "main_image", "product_url"])
    df = df.drop_duplicates(subset=["brand", "product_name"], keep="first")
    catalog = {}
    for r in df.itertuples(index=False):
        catalog[(r.brand, r.product_name)] = {
            "image": r.main_image if isinstance(r.main_image, str) and r.main_image.startswith("http") else None,
            "url": r.product_url if isinstance(r.product_url, str) else None,
        }
    return catalog


def find_forecast_workbook(run_dir):
    """ไฟล์พยากรณ์รายเดือน: ใช้สำเนา Top N ของ ⑪ ก่อน (เล็กกว่า) ไม่มีค่อยใช้ไฟล์เต็มของ ⑦"""
    folder = run_dir / FORECAST_SUBDIR
    tops = sorted(folder.glob("step5c_df_cluster_forecast_top*.xlsx"))
    if tops:
        return tops[-1]
    full = folder / "step5c_df_cluster_forecast.xlsx"
    return full if full.exists() else None


def load_forecast_series(run_dir, names):
    """ค่า z-score รายเดือนของโมเดลที่ถูกเลือก (best_model) ต่อเทรนด์ -> {ชื่อ: DataFrame(Date, z_score, Type)}
    ใช้แถว Fit เป็นช่วงย้อนหลัง (ตรงกับที่ ⑦ ใช้คำนวณ Current_Z/Z_Delta) และ Forecast เป็นช่วงอนาคต
    ไม่นับแถว Holdout (ซ้ำเดือนกับ Fit - ดูเหตุผลเดียวกันใน Plot_bump_chart.py's compute_ranks)"""
    path = find_forecast_workbook(run_dir)
    if path is None:
        return {}
    df = pd.read_excel(path)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df[(df["Model"] == df["best_model"]) & (df["Type"].isin(["Fit", "Forecast"]))]
    df = df[df["cluster_name"].isin(set(names))]
    return {name: g.sort_values("Date")[["Date", "z_score", "Type"]].reset_index(drop=True)
            for name, g in df.groupby("cluster_name")}


def _run_date(run_dir, manifest):
    """วันที่เก็บข้อมูลรอบนี้: timestamp แรกสุดใน manifest -> วันที่ท้ายชื่อโฟลเดอร์ -> เวลาแก้ไขไฟล์ ⑪"""
    stamps = [v.get("timestamp") for v in (manifest or {}).values() if isinstance(v, dict) and v.get("timestamp")]
    if stamps:
        return min(datetime.fromisoformat(s) for s in stamps)
    m = re.search(r"(\d{8}_\d{6})$", run_dir.name)
    if m:
        return datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
    return datetime.fromtimestamp((run_dir / HIGHLIGHTS_FILE).stat().st_mtime)


def _models_used(manifest):
    totals = {}
    for stage in (manifest or {}).values():
        if isinstance(stage, dict):
            for model, n in (stage.get("models_used") or {}).items():
                totals[model] = totals.get(model, 0) + int(n or 0)
    return sorted(totals, key=lambda m: -totals[m])


def _stepic_tiles(raw):
    """6 ช่อง STEPIC -> [{dimension, headline, body}] - แต่ละมิติ LLM ตอบคนละโครง (ดู run_stepic_report.py)
    จึงต้องระบุช่องที่ใช้ต่อมิติ ช่องไหนหายก็ตกไปใช้ช่องถัดไปที่มีข้อความ"""
    if not raw:
        return []
    tech = (raw.get("technology") or {}).get("analysis") or {}
    creat = (raw.get("creativity") or {}).get("creativity_analysis") or {}
    soc, env, pol, ind = (raw.get(k) or {} for k in ("society", "environment", "policy", "industry"))
    spec = [
        ("Society", soc.get("concept"), [soc.get("behavioral_shift"), soc.get("projected_impact")]),
        ("Technology", tech.get("core_technology"), [tech.get("innovation_driver"), tech.get("commercialization_signal")]),
        ("Environment", env.get("environmental_factor"), [env.get("sustainability_opportunity"), env.get("ESG_driver")]),
        ("Policy", pol.get("regulatory_trend"), [pol.get("business_impact"), pol.get("legal_barrier_or_support")]),
        ("Industry", ind.get("concept"),
         [(ind.get("strategic_positioning") or {}).get("winning_strategy"), ind.get("information")]),
        ("Creativity", creat.get("brand_expression"), [creat.get("product_innovation"), creat.get("differentiation_strategy")]),
    ]
    tiles = []
    for dim, head_src, body_srcs in spec:
        if not head_src and not any(body_srcs):
            continue
        headline, rest = split_headline(head_src or "")
        body = next((b for b in body_srcs if b), "") or rest
        tiles.append({"dimension": dim, "headline": headline, "body": first_sentences(body, 420)})
    return tiles


def _products(match_result, catalog, top_k):
    out = []
    for m in (match_result or {}).get("top_matches", [])[:top_k]:
        extra = catalog.get((m.get("brand"), m.get("product_name")), {})
        out.append({
            "name": strip_thai(m.get("product_name")) or m.get("product_name"),
            "name_full": m.get("product_name"),  # ชื่อเต็มที่มีภาษาไทย - ฉบับภาษาไทยใช้ตัวนี้ (i18n.localize)
            "brand": strip_thai(m.get("brand")) or m.get("brand"),
            "category": m.get("category") or "",
            "similarity": _num(m.get("similarity")),
            "price_thb": _num(m.get("sale_price_thb")),
            "reason": m.get("match_reason") or "",
            "image_url": extra.get("image"),
            "product_url": extra.get("url"),
        })
    return out


# ============================================================================
# ประกอบ context
# ============================================================================
def build_context(run_dir, catalog_path=None, top_products=5):
    """อ่านทุกไฟล์ของรอบ -> (context, forecast_series)

    context เป็น dict ที่ serialize เป็น JSON ได้ (บันทึกเป็น phase6_report_context.json ไว้ดูย้อนหลัง/ดีบัก)
    forecast_series เป็น DataFrame รายเดือนต่อเทรนด์ - ใหญ่ ไม่เก็บลง context ใช้วาดกราฟอย่างเดียว"""
    run_dir = Path(run_dir)
    missing = []

    def need(fname, label):
        data = read_json(run_dir / fname)
        if data is None:
            missing.append(f"{label} ({fname})")
        return data

    highlights = read_json(run_dir / HIGHLIGHTS_FILE)
    if not highlights or not highlights.get("selected_trends"):
        raise FileNotFoundError(f"ไม่พบชุด Top N จาก ⑪ ({HIGHLIGHTS_FILE}) ใน {run_dir} - ต้องรัน ⑪ ก่อน")

    manifest = read_json(run_dir / MANIFEST_FILE) or {}
    rank_rows = need(RANK_FILE, "Rank Score") or []
    forecast = need(FORECAST_FILE, "Google Trends forecast") or {}
    category = need(CATEGORY_FILE, "Category aggregation") or {}
    matches = need(MATCH_FILE, "Product matching") or {}
    stepic_final = need(STEPIC_FINAL_FILE, "STEPIC synthesis") or {}
    stepic_raw = need(STEPIC_RAW_FILE, "STEPIC analysis") or {}

    master = load_master_report(forecast)
    analysis_by_name = {c.get("cluster_name"): c
                        for c in (forecast.get("llm_forecast_analysis") or {}).get("cluster_analysis", [])}
    rank_by_key = {(r.get("Stream"), r.get("Trend Name")): r for r in rank_rows}
    trend_rows = load_trend_rows(run_dir)
    profiles = {(p.get("stream"), p.get("trend")): p for p in highlights.get("profiles", [])}
    catalog = load_product_catalog(catalog_path)
    match_results = matches.get("results") or {}

    trends = []
    for i, sel in enumerate(highlights["selected_trends"], 1):
        stream, name = sel.get("stream"), sel.get("trend")
        key = f"{stream}::{name}"
        mr = master.get(name, {})
        rk = rank_by_key.get((stream, name), {})
        row = trend_rows.get((stream, name), {})
        keywords = [k.strip() for k in str(mr.get("keywords") or "").split(",") if k.strip()]
        trends.append({
            "rank": sel.get("top_rank") or i,
            "overall_rank": sel.get("overall_rank"),
            "name": name,
            "key": key,
            "stream": stream,  # ใช้จับคู่ข้ามไฟล์เท่านั้น - เทมเพลตไม่แสดง
            "rank_score": _num(sel.get("rank_score", rk.get("Rank Score"))),
            "z_delta": _num(sel.get("z_delta", rk.get("Z_Delta", mr.get("z_delta")))),
            "status": mr.get("status") or "",
            "current_z": _num(mr.get("current_z")),
            "forecast_avg_z": _num(mr.get("forecast_avg_z")),
            "peak_month": mr.get("peak_month") or "",
            "best_model": mr.get("model") or "",
            "keywords": keywords,
            "data_quality": mr.get("data_quality") or "",
            "pct_months_with_data": _num(mr.get("pct_months_with_data")),
            "stream_count": rk.get("Stream_Count"),
            "cluster_size": rk.get("Cluster_Size", row.get("Cluster Size")),
            "longevity_score": row.get("Longevity Score"),
            "longevity_band": (row.get("Longevity Band") or "").replace("_", " "),
            "target": row.get("Target") or "",
            "key_ingredients": row.get("Key Ingredients") or "",
            "key_benefits": row.get("Key Benefits") or "",
            "analysis": analysis_by_name.get(name, {}),
            "profile": {k: v for k, v in profiles.get((stream, name), {}).items() if k not in ("stream", "trend")},
            "products": _products(match_results.get(key), catalog, top_products),
            "similarity_stats": (match_results.get(key) or {}).get("similarity_stats") or {},
            "n_products_compared": (match_results.get(key) or {}).get("n_products_compared"),
        })

    excluded = []
    for e in highlights.get("excluded_trends", []) + highlights.get("failed_trends", []):
        reason = e.get("reason") or "Trend profile extraction failed"
        excluded.append({"name": e.get("trend"), "overall_rank": e.get("overall_rank"),
                         "reason": EXCLUSION_REASON_EN.get(reason, strip_thai(reason) or "Excluded from the Top N"),
                         # ฉบับภาษาไทยใช้เหตุผลต้นฉบับจาก ⑪ ตรงๆ (เป็นภาษาไทยอยู่แล้ว)
                         "reason_th": reason if has_thai(reason) else EXCLUSION_REASON_TH.get(reason, reason)})

    series = load_forecast_series(run_dir, [t["name"] for t in trends])
    if not series:
        missing.append(f"Monthly forecast series ({FORECAST_SUBDIR}/step5c_df_cluster_forecast*.xlsx)")
    forecast_dates = [d for s in series.values() for d in s.loc[s["Type"] == "Forecast", "Date"]]

    paper = read_json(run_dir / STREAM_FILES["Paper"]) or {}
    topic = paper.get("topic") or next((v.get("topic") for v in manifest.values()
                                        if isinstance(v, dict) and v.get("topic")), "") or run_dir.name
    years = next((v.get("years") for v in manifest.values() if isinstance(v, dict) and v.get("years")), "")
    run_date = _run_date(run_dir, manifest)
    stepic_final = stepic_final or {}

    context = {
        "meta": {
            "run_id": run_dir.name,
            "topic": topic,
            "title": smart_title(topic),
            "years": years,
            "top_n": len(trends),
            "n_trends_total": highlights.get("n_trends_total"),
            "n_products_compared": matches.get("n_products_total"),
            "run_date": run_date.isoformat(timespec="minutes"),
            "forecast_start": min(forecast_dates).strftime("%b %Y") if forecast_dates else "",
            "forecast_end": max(forecast_dates).strftime("%b %Y") if forecast_dates else "",
            "models_used": _models_used(manifest),
        },
        "overview": {
            "overall": category.get("overall") or {},
            "market": (forecast.get("llm_forecast_analysis") or {}).get("market_overview") or {},
        },
        "takeaway": {
            "mega_trend_name": stepic_final.get("mega_trend_name", ""),
            "macro_direction": stepic_final.get("macro_direction", ""),
            "core_concept": stepic_final.get("core_concept", ""),
            "projection": stepic_final.get("3_month_projection", ""),
            "key_opportunity": stepic_final.get("key_opportunity", ""),
            "key_risk": stepic_final.get("key_risk", ""),
        },
        "stepic": _stepic_tiles(stepic_raw),
        "personas": stepic_final.get("emerging_personas") or [],
        "signals": stepic_final.get("cross_dimensional_signals") or [],
        "trends": trends,
        "excluded": excluded,
        "missing": missing,
    }
    return context, series
