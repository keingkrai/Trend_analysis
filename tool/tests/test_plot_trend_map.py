# -*- coding: utf-8 -*-
"""เทียบ Plot_trend_map.load_trend_data() กับไฟล์ผลลัพธ์จริงของรอบอ้างอิง - ตรวจแค่ฟังก์ชันอ่านข้อมูล
(ฟังก์ชันล้วน ไม่มี state) ไม่ตรวจตัวกราฟ matplotlib เอง

ข้ามทั้งไฟล์ถ้าไม่มีรอบอ้างอิงในเครื่องนี้ (เช่นหลัง clone ซึ่งไม่มีโฟลเดอร์ output/)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

MAIN_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MAIN_DIR))
import Plot_trend_map as ptm  # noqa: E402

REFERENCE_RUN = "beauty_and_personal_care_20260916_082438"
RUN_DIR = MAIN_DIR / "output" / REFERENCE_RUN
pytestmark = pytest.mark.skipif(not RUN_DIR.is_dir(), reason=f"ไม่มีรอบอ้างอิง {REFERENCE_RUN} ในเครื่องนี้")


def _raw(name):
    with open(RUN_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def test_load_trend_data_has_all_15_trends_with_correct_selection():
    points = ptm.load_trend_data(RUN_DIR)
    rank_rows = _raw(ptm.RANK_FILE)
    highlights = _raw(ptm.HIGHLIGHTS_FILE)
    assert len(points) == len(rank_rows) == 15
    assert sum(p["selected"] for p in points) == highlights["top_n"] == 10
    by_name = {p["name"]: p for p in points}
    for t in highlights["selected_trends"]:
        assert by_name[t["trend"]]["top_rank"] == t["top_rank"]
        assert by_name[t["trend"]]["selected"] is True
    for t in highlights["excluded_trends"]:
        assert by_name[t["trend"]]["selected"] is False
        assert by_name[t["trend"]]["excluded_reason"] == t["reason"]
        assert by_name[t["trend"]]["top_rank"] is None


def test_load_trend_data_matches_rank_score_file_exactly():
    points = ptm.load_trend_data(RUN_DIR)
    by_key = {(p["stream"], p["name"]): p for p in points}
    for r in _raw(ptm.RANK_FILE):
        p = by_key[(r["Stream"], r["Trend Name"])]
        assert p["overall_rank"] == r["Overall Rank"]
        assert p["z_delta"] == r["Z_Delta"]
        assert p["stream_count"] == r["Stream_Count"]
        assert p["cluster_size"] == r["Cluster_Size"]
        assert p["rank_score"] == r["Rank Score"]


def test_load_trend_data_matches_forecast_current_z():
    points = ptm.load_trend_data(RUN_DIR)
    by_name = {p["name"]: p for p in points}
    cols = ptm.MASTER_REPORT_COLS
    for row in _raw(ptm.FORECAST_FILE)["master_report"]:
        d = dict(zip(cols, row))
        p = by_name[d["trend"]]
        assert p["current_z"] == d["current_z"]
        assert p["forecast_avg_z"] == d["forecast_avg_z"]
        # z_delta ต้องตรงกันทั้งจากไฟล์ ⑥ (rank) และไฟล์ ⑦ (forecast) - สองขั้นต้องเห็นค่าเดียวกัน
        assert p["z_delta"] == d["z_delta"]


def test_load_trend_data_matches_longevity_file():
    points = ptm.load_trend_data(RUN_DIR)
    by_key = {(p["stream"], p["name"]): p for p in points}
    for stream, rows in _raw(ptm.LONGEVITY_FILE).items():
        for r in rows:
            p = by_key[(stream, r["Trend Name"])]
            assert p["longevity_score"] == r["Longevity Score"]
            assert p["longevity_band"] == r["Longevity Band"]


def test_load_trend_data_survives_missing_optional_files(tmp_path):
    """มีแค่ผล ⑥ (จำเป็น) ไฟล์อื่นหายหมด - ต้องยังทำงานได้ คืนค่า None ในฟิลด์ที่ขาด ไม่ throw"""
    run = tmp_path / "adhoc_run"
    run.mkdir()
    (run / ptm.RANK_FILE).write_text(json.dumps([
        {"Overall Rank": 1, "Stream": "Paper", "Trend Name": "Only Trend", "Z_Delta": 0.5,
         "Stream_Count": 1, "Cluster_Size": 5, "Rank Score": 0.5},
    ]), encoding="utf-8")
    points = ptm.load_trend_data(run)
    assert len(points) == 1
    p = points[0]
    assert p["name"] == "Only Trend" and p["z_delta"] == 0.5
    assert p["current_z"] is None and p["longevity_score"] is None
    assert p["selected"] is False and p["top_rank"] is None and p["excluded_reason"] is None


def test_load_trend_data_requires_rank_file(tmp_path):
    run = tmp_path / "empty_run"
    run.mkdir()
    with pytest.raises(FileNotFoundError, match=ptm.RANK_FILE):
        ptm.load_trend_data(run)
