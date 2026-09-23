# -*- coding: utf-8 -*-
"""อ่านผลลัพธ์ของไปป์ไลน์จากโฟลเดอร์ `output/<run_id>/` - ฟังก์ชันล้วน ไม่มี state ไม่เรียก API ไม่แก้ไฟล์

ทำไมไม่ import `common.bootstrap`: `bootstrap` คำนวณ `OUTPUTS` ตอน import จาก env `TREND_RUN_ID` โปรเซสหนึ่ง
จึงผูกกับรอบเดียวตลอด ซึ่งใช้กับ server ที่ต้องสลับรอบตามคำขอไม่ได้ - ที่นี่รับ `run_id` เป็นพารามิเตอร์แล้ว
ประกอบ path เอง

ทุกฟังก์ชันคืนค่าที่แปลงเป็น JSON ได้ทันที และโยน `ValueError` พร้อมรายการตัวเลือกที่มีจริงเมื่อหาไม่เจอ
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # โฟลเดอร์บนสุดของ repo (มี main.py)
OUTPUT_ROOT = ROOT / "output"
FORECAST_SUBDIR = "serpapi_forecast_run"

HIGHLIGHTS = "phase3_trend_highlights_result.json"
MATCHES = "phase3_scale_validation_nvidia_result.json"
RANKS = "phase2_rank_score_final_mode_result.json"
FORECAST = "phase2_paper_social_z_delta_result.json"
LONGEVITY = "phase2_longevity_cross_source_result.json"
REPORT = "phase4_master_trend_report.md"
MANIFEST = "_manifest.json"
STREAM_FILES = {"Paper": "phase1_paper_stream_result.json",
                "Social": "phase2_social_stream_result.json",
                "News": "phase2_news_stream_result.json"}
MASTER_REPORT_COLS = ["cluster_id", "trend", "model", "status", "current_z", "forecast_avg_z", "z_delta",
                      "peak_month", "keywords", "context", "data_quality", "pct_months_with_data"]


# ---------------------------------------------------------------- helpers
def _read_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _jsonable(value):
    """numpy/pandas -> ชนิดพื้นฐานของ Python (ค่าที่มาจาก Excel เป็น numpy scalar)"""
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def run_dir(run_id: str | None = None) -> Path:
    """โฟลเดอร์ของรอบ - ไม่ระบุ = รอบล่าสุดที่มีผล ⑪"""
    if run_id:
        path = OUTPUT_ROOT / run_id
        if not path.is_dir():
            raise ValueError(f"ไม่พบรอบ {run_id!r} - รอบที่มีอยู่: {[r['run_id'] for r in list_runs()]}")
        return path
    runs = list_runs()
    if not runs:
        raise ValueError(f"ยังไม่มีรอบไหนใน {OUTPUT_ROOT} - รัน main.py อย่างน้อย 1 รอบก่อน")
    return OUTPUT_ROOT / runs[0]["run_id"]


def _match_trend(name: str, available: list[str]) -> str:
    """จับคู่ชื่อเทรนด์แบบยืดหยุ่น: ตรงตัว -> ไม่สนตัวพิมพ์ -> เป็นส่วนหนึ่งของชื่อ (ต้องเหลือตัวเลือกเดียว)"""
    if name in available:
        return name
    low = {a.lower(): a for a in available}
    if name.lower() in low:
        return low[name.lower()]
    hits = [a for a in available if name.lower() in a.lower()]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ValueError(f"ชื่อ {name!r} ตรงกับหลายเทรนด์: {hits}")
    raise ValueError(f"ไม่พบเทรนด์ {name!r} - เทรนด์ในรอบนี้: {available}")


def _bump_module():
    """ใช้ฟังก์ชันจัดอันดับของ Plot_bump_chart.py ตัวเดิม (ตัดแถว Holdout/เลือก best model เหมือนกราฟและรายงาน)
    - โมดูลนั้น print ระหว่างทาง ผู้เรียกต้องเปลี่ยนปลายทาง stdout เพราะ MCP ใช้ stdout คุยกับ client"""
    spec = importlib.util.spec_from_file_location("_plot_bump_chart", ROOT / "Plot_bump_chart.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("_plot_bump_chart", module)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- runs
def list_runs() -> list[dict]:
    """ทุกรอบที่รันไว้ เรียงจากใหม่ไปเก่า (ข้ามโฟลเดอร์ที่ขึ้นต้นด้วย _ ซึ่งไม่ใช่ผลรัน)"""
    runs = []
    if not OUTPUT_ROOT.is_dir():
        return runs
    for path in OUTPUT_ROOT.iterdir():
        if not path.is_dir() or path.name.startswith("_"):
            continue
        manifest = _read_json(path / MANIFEST, {}) or {}
        highlights = _read_json(path / HIGHLIGHTS, {}) or {}
        stages = list(manifest)
        topic = next((s.get("topic") for s in manifest.values() if s.get("topic")), None)
        updated = max((s.get("timestamp", "") for s in manifest.values()), default="")
        runs.append({
            "run_id": path.name,
            "topic": topic,
            "updated": updated or None,
            "stages_done": stages,
            "n_trends_selected": highlights.get("top_n"),
            "has_products": (path / MATCHES).exists(),
            "has_report": (path / REPORT).exists(),
            "brands_checked": sorted(p.stem.replace("phase3_brand_coverage_", "")
                                     for p in path.glob("phase3_brand_coverage_*.json")),
        })
    return sorted(runs, key=lambda r: (r["updated"] or "", r["run_id"]), reverse=True)


def get_run_summary(run_id: str | None = None) -> dict:
    """ภาพรวมของรอบ: หัวข้อ จำนวนเทรนด์ เทรนด์ที่ถูกคัดออก และแต่ละขั้นรันเมื่อไหร่ด้วยโมเดลอะไร"""
    path = run_dir(run_id)
    highlights = _read_json(path / HIGHLIGHTS, {}) or {}
    manifest = _read_json(path / MANIFEST, {}) or {}
    stages = {name: {"timestamp": s.get("timestamp"), "topic": s.get("topic"), "years": s.get("years"),
                     "models_used": s.get("models_used")} for name, s in manifest.items()}
    return {
        "run_id": path.name,
        "topic": next((s.get("topic") for s in manifest.values() if s.get("topic")), None),
        "years": next((s.get("years") for s in manifest.values() if s.get("years")), None),
        "n_trends_total": highlights.get("n_trends_total"),
        "n_trends_selected": highlights.get("top_n"),
        "requested_top_n": highlights.get("requested_top_n"),
        "excluded_trends": [{"trend": t.get("trend"), "stream": t.get("stream"),
                             "overall_rank": t.get("overall_rank"), "reason": t.get("reason")}
                            for t in highlights.get("excluded_trends", [])],
        "failed_trends": highlights.get("failed_trends", []),
        "brands_checked": sorted(p.stem.replace("phase3_brand_coverage_", "")
                                 for p in path.glob("phase3_brand_coverage_*.json")),
        "has_report": (path / REPORT).exists(),
        "stages": stages,
    }


def get_manifest(run_id: str | None = None) -> dict:
    """manifest ดิบของรอบ (hash ไฟล์ input/output + โมเดลที่ใช้จริง + เวลา ของทุกขั้น)"""
    path = run_dir(run_id)
    manifest = _read_json(path / MANIFEST)
    if manifest is None:
        raise ValueError(f"รอบ {path.name} ไม่มี {MANIFEST}")
    return manifest


# ---------------------------------------------------------------- trends
def _forecast_rows(path: Path) -> dict[str, dict]:
    data = _read_json(path / FORECAST, {}) or {}
    rows = {}
    for row in data.get("master_report") or []:
        item = dict(zip(MASTER_REPORT_COLS, row))
        rows[item["trend"]] = item
    return rows


def _longevity_rows(path: Path) -> dict[str, dict]:
    data = _read_json(path / LONGEVITY, {}) or {}
    out = {}
    for stream, rows in data.items():
        for row in rows:
            out[(stream, row.get("Trend Name"))] = row
    return out


def list_trends(run_id: str | None = None) -> list[dict]:
    """เทรนด์ชุดที่ไปป์ไลน์คัดไว้ (Top N ของ ⑪) เรียงตามอันดับที่แสดงผล พร้อมค่าพยากรณ์และจำนวนสินค้าที่จับคู่ได้

    `overall_rank` = อันดับจาก Rank Score ของ ⑥ (จาก 15 เทรนด์), `top_rank` = อันดับ 1..N ในชุดที่ใช้จริง
    """
    path = run_dir(run_id)
    highlights = _read_json(path / HIGHLIGHTS)
    if highlights is None:
        raise ValueError(f"รอบ {path.name} ยังไม่มีผล ⑪ ({HIGHLIGHTS}) - ชุดเทรนด์ยังไม่ถูกคัด")
    forecasts, longevity = _forecast_rows(path), _longevity_rows(path)
    matches = (_read_json(path / MATCHES, {}) or {}).get("results", {})
    out = []
    for item in highlights.get("selected_trends", []):
        name, stream = item.get("trend"), item.get("stream")
        fc = forecasts.get(name, {})
        lg = longevity.get((stream, name), {})
        match = matches.get(f"{stream}::{name}", {})
        out.append(_jsonable({
            "top_rank": item.get("top_rank"),
            "overall_rank": item.get("overall_rank"),
            "trend": name,
            "stream": stream,
            "rank_score": item.get("rank_score"),
            "z_delta": item.get("z_delta"),
            "status": fc.get("status"),
            "best_model": fc.get("model"),
            "peak_month": fc.get("peak_month"),
            "data_quality": fc.get("data_quality"),
            "longevity_score": lg.get("Longevity Score"),
            "longevity_band": lg.get("Longevity Band"),
            "n_products_matched": len(match.get("top_matches", [])),
        }))
    return sorted(out, key=lambda r: r["top_rank"] or 99)


def get_trend(trend: str, run_id: str | None = None) -> dict:
    """รายละเอียดเทรนด์เดียว: จุดเด่นจาก ⑪ ค่าพยากรณ์ คีย์เวิร์ดที่ใช้ค้น Google Trends และสินค้าที่ใกล้ที่สุด 3 อันดับ"""
    path = run_dir(run_id)
    rows = list_trends(path.name)
    name = _match_trend(trend, [r["trend"] for r in rows])
    row = next(r for r in rows if r["trend"] == name)

    highlights = _read_json(path / HIGHLIGHTS, {}) or {}
    profile = next((p for p in highlights.get("profiles", []) if p.get("trend") == name), {})
    stream_data = _read_json(path / STREAM_FILES.get(row["stream"], ""), {}) or {}
    keywords = next((k for k in stream_data.get("keywords", []) if k.get("Trend Name") == name), {})
    cluster = next((c for c in stream_data.get("trends", []) if c.get("Trend Name") == name), {})
    match = (_read_json(path / MATCHES, {}) or {}).get("results", {}).get(f"{row['stream']}::{name}", {})
    return _jsonable({
        **row,
        "highlight": {k: v for k, v in profile.items() if k not in ("trend", "stream")},
        "cluster": {"size": cluster.get("Cluster Size"), "key_ingredients": cluster.get("Key Ingredients"),
                    "key_benefits": cluster.get("Key Benefits"), "target": cluster.get("Target"),
                    "analysis_th": cluster.get("Analysis (Thai)")},
        "search_keywords": keywords.get("Search_Keywords"),
        "product_search_keywords": keywords.get("Product_Search_Keywords"),
        "similarity_stats": match.get("similarity_stats"),
        "top_products_preview": [{"product_name": m.get("product_name"), "brand": m.get("brand"),
                                  "similarity": m.get("similarity")} for m in match.get("top_matches", [])[:3]],
    })


def get_top_products(trend: str, run_id: str | None = None, limit: int = 5) -> dict:
    """สินค้าใน Watsons ที่ใกล้เคียงเทรนด์นี้ที่สุด เรียงตาม similarity (เหตุผลมีเฉพาะ 5 อันดับแรกที่ ⑫ ให้ LLM เขียนไว้)

    similarity เป็นตัวเรียงลำดับ ไม่ใช่คำตัดสินว่า "ใช่" - ดูข้อจำกัดใน README หัวข้อความคลาดเคลื่อน
    """
    path = run_dir(run_id)
    data = _read_json(path / MATCHES)
    if data is None:
        raise ValueError(f"รอบ {path.name} ยังไม่มีผล ⑫ ({MATCHES})")
    keys = {k.split("::", 1)[1]: k for k in data.get("results", {})}
    name = _match_trend(trend, sorted(keys))
    result = data["results"][keys[name]]
    return _jsonable({
        "run_id": path.name,
        "trend": name,
        "stream": result.get("stream"),
        "n_products_compared": result.get("n_products_compared"),
        "similarity_stats": result.get("similarity_stats"),
        "products": result.get("top_matches", [])[:limit],
    })


# ---------------------------------------------------------------- brands
def list_brands(run_id: str | None = None) -> list[str]:
    """แบรนด์ที่เคยค้นในรอบนี้ (ผลของ ⑬)"""
    path = run_dir(run_id)
    return sorted(p.stem.replace("phase3_brand_coverage_", "") for p in path.glob("phase3_brand_coverage_*.json"))


def get_brand_coverage(brand: str, run_id: str | None = None, limit: int = 5) -> dict:
    """แบรนด์นี้มีสินค้าใกล้แต่ละเทรนด์แค่ไหน - `rank_vs_market` คืออันดับเทียบสินค้าทั้งตลาด 10,622 ชิ้น"""
    path = run_dir(run_id)
    available = list_brands(path.name)
    if not available:
        raise ValueError(f"รอบ {path.name} ยังไม่มีผล ⑬ (ยังไม่เคยค้นแบรนด์ไหน)")
    low = {b.lower(): b for b in available}
    picked = low.get(brand.lower().replace(" ", "_"))
    if picked is None:
        hits = [b for b in available if brand.lower() in b.lower()]
        if len(hits) != 1:
            raise ValueError(f"ไม่พบแบรนด์ {brand!r} ในรอบนี้ - ที่มี: {available}")
        picked = hits[0]
    data = _read_json(path / f"phase3_brand_coverage_{picked}.json", {}) or {}
    coverage = []
    for item in (data.get("coverage") or {}).values():
        coverage.append({
            "trend": item.get("trend_name"),
            "stream": item.get("stream"),
            "trend_rank": item.get("trend_top_rank") or item.get("trend_overall_rank"),
            "products": item.get("brand_top_matches", [])[:limit],
        })
    coverage.sort(key=lambda c: c["trend_rank"] or 99)
    return _jsonable({"run_id": path.name, "brand": data.get("brand", picked),
                      "n_skus": data.get("n_skus"), "coverage": coverage})


# ---------------------------------------------------------------- report / ranks
def list_report_sections(run_id: str | None = None) -> list[str]:
    """หัวข้อทั้งหมดใน Master Report ของรอบนี้"""
    path = run_dir(run_id) / REPORT
    if not path.exists():
        raise ValueError(f"รอบนี้ยังไม่มี {REPORT} (ยังไม่ได้รัน ⑭-⑮)")
    return [m.group(2).strip() for m in re.finditer(r"^(#{1,3}) (.+)$", path.read_text(encoding="utf-8"), re.M)]


def get_report(run_id: str | None = None, section: str | None = None) -> dict:
    """Master Report ทั้งฉบับ หรือเฉพาะหัวข้อที่ระบุ (จับคู่ชื่อหัวข้อแบบไม่สนตัวพิมพ์/เป็นส่วนหนึ่งของชื่อได้)"""
    path = run_dir(run_id)
    file = path / REPORT
    if not file.exists():
        raise ValueError(f"รอบ {path.name} ยังไม่มี {REPORT} (ยังไม่ได้รัน ⑭-⑮)")
    text = file.read_text(encoding="utf-8")
    if section is None:
        return {"run_id": path.name, "section": None, "text": text}
    heads = [(m.start(), len(m.group(1)), m.group(2).strip()) for m in re.finditer(r"^(#{1,3}) (.+)$", text, re.M)]
    hits = [h for h in heads if section.lower() in h[2].lower()]
    if not hits:
        raise ValueError(f"ไม่พบหัวข้อ {section!r} - หัวข้อที่มี: {[h[2] for h in heads]}")
    start, level, title = hits[0]
    end = next((s for s, lv, _ in heads if s > start and lv <= level), len(text))
    return {"run_id": path.name, "section": title, "text": text[start:end].strip()}


def get_yearly_ranks(run_id: str | None = None) -> dict:
    """อันดับความสนใจรายปีภายในชุด Top N (ชุดเดียวกับ bump chart และลำดับหัวข้อในรายงาน)

    ใช้ฟังก์ชันของ Plot_bump_chart.py ตัวเดิม - เลือกเฉพาะแถวของโมเดลที่ชนะ ตัดแถว Holdout ทิ้ง แล้วเฉลี่ย z-score
    ต่อปี อันดับ 1 = ปีนั้นคนสนใจมากที่สุดในกลุ่ม
    """
    path = run_dir(run_id)
    forecast_dir = path / FORECAST_SUBDIR
    if not forecast_dir.is_dir():
        raise ValueError(f"รอบ {path.name} ยังไม่มีผลพยากรณ์ ({FORECAST_SUBDIR}/)")
    bump = _bump_module()
    with contextlib.redirect_stdout(sys.stderr):        # กัน print ไปปน protocol ของ MCP
        top_n = bump.resolve_top_n(forecast_dir, None)
        df = bump.load_forecast(forecast_dir)
        # "ปีปัจจุบัน" = ปีของเดือนจริงเดือนสุดท้าย (แถว Fit) เหมือนที่รายงานใช้เรียงหัวข้อ ไม่ใช่ปีสุดท้ายของการพยากรณ์
        fit = df[df["Type"] == "Fit"]
        current_year = str(int(fit["Date"].dt.year.max())) if not fit.empty else None
        ranks = bump.compute_ranks(df)
        highlight = bump.select_highlight(ranks, forecast_dir, top_n)
        table = bump.compute_plot_ranks(ranks, highlight)[highlight]
        years = [bump.period_label(d) for d in table.index]
    by_trend = {trend: dict(zip(years, [int(v) for v in table[trend].tolist()])) for trend in highlight}
    return _jsonable({
        "run_id": path.name,
        "years": years,
        "current_year": current_year,
        "last_forecast_year": years[-1] if years else None,
        "ranks": by_trend,
        "current_year_ranking": sorted(
            ({"trend": t, "rank": r[current_year]} for t, r in by_trend.items() if current_year in r),
            key=lambda x: x["rank"]) if current_year else [],
    })
