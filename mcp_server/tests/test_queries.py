# -*- coding: utf-8 -*-
"""เทียบผลของ mcp_server/queries.py กับไฟล์ผลลัพธ์จริงของรอบอ้างอิง - ไม่เรียก API ไม่แก้ไฟล์

ถ้าไม่มีรอบอ้างอิงในเครื่อง (เช่นหลัง clone ซึ่งไม่มีโฟลเดอร์ output/) เทสต์กลุ่มที่ต้องใช้ข้อมูลจะข้ามเอง
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mcp_server import queries  # noqa: E402

REFERENCE_RUN = "beauty_and_personal_care_20260916_082438"
RUN_DIR = queries.OUTPUT_ROOT / REFERENCE_RUN
pytestmark = pytest.mark.skipif(not RUN_DIR.is_dir(), reason=f"ไม่มีรอบอ้างอิง {REFERENCE_RUN} ในเครื่องนี้")


def _raw(name):
    with open(RUN_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def test_list_runs_includes_reference_run():
    runs = queries.list_runs()
    run = next((r for r in runs if r["run_id"] == REFERENCE_RUN), None)
    assert run is not None, [r["run_id"] for r in runs]
    assert run["topic"] and run["has_report"] and run["has_products"]
    assert run["n_trends_selected"] == _raw(queries.HIGHLIGHTS)["top_n"]
    assert set(run["brands_checked"]) == {p.stem.replace("phase3_brand_coverage_", "")
                                          for p in RUN_DIR.glob("phase3_brand_coverage_*.json")}


def test_run_summary_matches_files():
    s = queries.get_run_summary(REFERENCE_RUN)
    h, m = _raw(queries.HIGHLIGHTS), _raw(queries.MANIFEST)
    assert s["run_id"] == REFERENCE_RUN
    assert (s["n_trends_selected"], s["n_trends_total"]) == (h["top_n"], h["n_trends_total"])
    assert len(s["excluded_trends"]) == len(h["excluded_trends"])
    assert all(t["reason"] for t in s["excluded_trends"])
    assert set(s["stages"]) == set(m)
    assert s["stages"]["extract_trend_highlights"]["models_used"] == m["extract_trend_highlights"]["models_used"]


def test_list_trends_matches_selected_set_and_ranks():
    trends = queries.list_trends(REFERENCE_RUN)
    selected = _raw(queries.HIGHLIGHTS)["selected_trends"]
    assert len(trends) == len(selected)
    assert [t["top_rank"] for t in trends] == list(range(1, len(selected) + 1))
    assert {t["trend"] for t in trends} == {s["trend"] for s in selected}
    rank_rows = {(r["Stream"], r["Trend Name"]): r for r in _raw(queries.RANKS)}
    forecast = {row[1]: row for row in _raw(queries.FORECAST)["master_report"]}
    for t in trends:
        raw = rank_rows[(t["stream"], t["trend"])]
        assert t["overall_rank"] == raw["Overall Rank"]
        assert t["rank_score"] == raw["Rank Score"]
        assert t["status"] == forecast[t["trend"]][3]        # คอลัมน์ Status ใน master_report
        assert t["z_delta"] == forecast[t["trend"]][6]
        assert t["n_products_matched"] > 0


def test_get_trend_returns_highlight_and_keywords():
    t = queries.get_trend("Pregnancy-Safe", REFERENCE_RUN)        # จับคู่ชื่อบางส่วนได้
    assert t["trend"] == "Pregnancy-Safe Dermocosmetics" and t["stream"] == "News"
    profile = next(p for p in _raw(queries.HIGHLIGHTS)["profiles"] if p["trend"] == t["trend"])
    assert t["highlight"]["job_to_be_done"] == profile["job_to_be_done"]
    assert t["highlight"]["trend_type"] == profile["trend_type"]
    stream = _raw(queries.STREAM_FILES["News"])
    kw = next(k for k in stream["keywords"] if k["Trend Name"] == t["trend"])
    assert t["search_keywords"] == kw["Search_Keywords"]
    assert len(t["top_products_preview"]) == 3


def test_get_top_products_matches_match_file():
    res = queries.get_top_products("Clinical Dermatology Hair Care", REFERENCE_RUN, limit=5)
    raw = _raw(queries.MATCHES)["results"]["News::Clinical Dermatology Hair Care"]
    assert res["products"] == raw["top_matches"][:5]
    assert res["n_products_compared"] == raw["n_products_compared"]
    sims = [p["similarity"] for p in res["products"]]
    assert sims == sorted(sims, reverse=True)


def test_brand_coverage_uses_display_ranks():
    brands = queries.list_brands(REFERENCE_RUN)
    assert "Srichand" in brands
    cov = queries.get_brand_coverage("srichand", REFERENCE_RUN, limit=5)
    raw = _raw("phase3_brand_coverage_Srichand.json")
    assert cov["brand"] == raw["brand"] and cov["n_skus"] == raw["n_skus"]
    assert len(cov["coverage"]) == len(raw["coverage"])
    assert [c["trend_rank"] for c in cov["coverage"]] == list(range(1, len(cov["coverage"]) + 1))
    assert all(len(c["products"]) <= 5 for c in cov["coverage"])


def test_report_section_extraction():
    sections = queries.list_report_sections(REFERENCE_RUN)
    assert "1. Executive Summary" in sections
    full = queries.get_report(REFERENCE_RUN)["text"]
    assert full == (RUN_DIR / queries.REPORT).read_text(encoding="utf-8")
    part = queries.get_report(REFERENCE_RUN, "Executive Summary")
    assert part["section"].endswith("Executive Summary")
    assert part["text"].startswith("## 1. Executive Summary")
    assert len(part["text"]) < len(full)


def test_yearly_ranks_match_saved_ranks_excel():
    """ตารางอันดับต้องตรงกับไฟล์ ranks ที่ Plot_bump_chart บันทึกไว้ในรอบนี้"""
    pd = pytest.importorskip("pandas")
    files = sorted(RUN_DIR.glob("step5c_df_cluster_forecast_ranks_*.xlsx"))
    if not files:
        pytest.skip("รอบนี้ยังไม่มีไฟล์ ranks ที่บันทึกไว้")
    saved = pd.read_excel(files[-1], index_col=0)
    saved.index = saved.index.astype(str)
    out = queries.get_yearly_ranks(REFERENCE_RUN)
    assert out["years"] == list(saved.index)
    assert set(out["ranks"]) == set(saved.columns)
    for trend in saved.columns:
        assert out["ranks"][trend] == {y: int(v) for y, v in saved[trend].items()}
    assert out["current_year"] in out["years"]
    ranks_now = [r["rank"] for r in out["current_year_ranking"]]
    assert ranks_now == sorted(ranks_now) == list(range(1, len(out["ranks"]) + 1))


def test_unknown_names_give_useful_errors():
    with pytest.raises(ValueError, match="ไม่พบรอบ"):
        queries.get_run_summary("ไม่มีรอบนี้")
    with pytest.raises(ValueError, match="ไม่พบเทรนด์"):
        queries.get_trend("ไม่มีเทรนด์นี้", REFERENCE_RUN)
    with pytest.raises(ValueError, match="ไม่พบแบรนด์"):
        queries.get_brand_coverage("ไม่มีแบรนด์นี้", REFERENCE_RUN)
    with pytest.raises(ValueError, match="ไม่พบหัวข้อ"):
        queries.get_report(REFERENCE_RUN, "หัวข้อที่ไม่มี")


def test_queries_does_not_import_bootstrap():
    """ห้ามพึ่ง bootstrap เพราะมันผูก OUTPUTS กับ run เดียวตอน import ทำให้ server สลับรอบไม่ได้
    (ตรวจที่คำสั่ง import จริงด้วย AST ไม่ใช่ค้นข้อความ - docstring ในไฟล์พูดถึงชื่อนี้อยู่)"""
    import ast
    tree = ast.parse(Path(queries.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(m.split(".")[0] in ("common", "bootstrap", "trend_final", "trend_final_v2") for m in imported), imported
