# -*- coding: utf-8 -*-
"""
🆕 (2026-10-28) หน้า "คนกำลังค้นหาอะไรมากขึ้น" ของรอบสาย Search (phase6_pdf_report/search_talk.py) - นับด้วยโค้ด ไม่เรียก API/LLM
ตัวเลขทั้งหมดมาจากโฟลเดอร์รอบปลอม: ตรวจจำนวนต่อหมวด การแยกพื้นที่ ส่วนที่เป็นที่มาของเทรนด์ในรายงาน และตัวอย่างที่ต้องตรงกับคำค้นจริง

รัน: pytest main/tool/tests/test_search_talk.py -v
"""
import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TOOL_DIR = TESTS_DIR.parent
for _p in (TOOL_DIR, TOOL_DIR / "phase6_pdf_report"):
    sys.path.insert(0, str(_p))

import pytest  # noqa: E402

import search_talk as st  # noqa: E402
from common.streams import SEARCH_STREAM, STREAM_FILES  # noqa: E402


def _q(text, geos, norm=None):
    return {"query_norm": norm or text.lower(), "query": text, "geos": geos, "max_value": 100, "value": "+100%"}


@pytest.fixture
def run(tmp_path):
    work = tmp_path / "search_stream_work"
    (work / "themes").mkdir(parents=True)
    (work / "links").mkdir()
    health = [_q("best sunscreen for kids", "TH,WW"), _q("best sunscreen", "WW"), _q("what causes hair loss", "TH"),
              _q("state welfare card", "TH"), _q("flu symptoms", "WW")]
    (work / "themes" / "Health.json").write_text(json.dumps({
        "themes": [{"name": "Sunscreen", "ids": [1, 2]}, {"name": "Hair", "ids": [3]}, {"name": "Welfare", "ids": [4, 5]}],
        "queries": health}), encoding="utf-8")
    (work / "links" / "Health.json").write_text(json.dumps([
        {"theme": "Sunscreen", "path": 1, "evidence": ["best sunscreen for kids", "best sunscreen"]},
        {"theme": "Hair", "path": 2, "evidence": ["what causes hair loss"]},
        {"theme": "Welfare", "path": 0, "evidence": []}]), encoding="utf-8")
    sports = [_q("world cup 2026", "WW"), _q("marathon bangkok", "TH"), _q("best sunscreen", "TH", norm="best sunscreen")]
    (work / "themes" / "Sports.json").write_text(json.dumps({
        "themes": [{"name": "Matches", "ids": [1]}, {"name": "Running", "ids": [2, 3]}], "queries": sports}), encoding="utf-8")
    (work / "links" / "Sports.json").write_text(json.dumps([
        {"theme": "Matches", "path": 3, "evidence": ["world cup 2026"]}, {"theme": "Running", "path": 0, "evidence": []}]), encoding="utf-8")
    (tmp_path / STREAM_FILES[SEARCH_STREAM]).write_text(json.dumps({
        "search_meta": {"places": ["TH", "WW"], "month": "2026-10", "n_trends": 3},
        "trends": [
            {"Trend Name": "Sun Care", "Source Themes": [
                {"category": "Health", "theme": "Sunscreen", "evidence": ["best sunscreen for kids", "invented search not in the list", "best sunscreen"]}]},
            {"Trend Name": "Hair", "Source Themes": [{"category": "Health", "theme": "Hair", "evidence": ["what causes hair loss"]}]},
            {"Trend Name": "Dropped Trend", "Source Themes": [{"category": "Sports", "theme": "Matches", "evidence": ["world cup 2026"]}]}]}),
        encoding="utf-8")
    return tmp_path


TRENDS = [{"name": "Sun Care", "display_name": "Sun Care Plain", "rank": 2}, {"name": "Hair", "display_name": None, "rank": 1}]


def test_counts_places_and_unique_searches(run):
    d = st.load_talk(run, TRENDS)
    assert d["n_categories"] == 2 and d["n_searches"] == 7                       # "best sunscreen" อยู่ 2 หมวดนับครั้งเดียว (7 = 8 รายการ - 1 ซ้ำ)
    health = next(c for c in d["categories"] if c["name"] == "Health")
    assert (health["n"], health["th"], health["ww"], health["both"]) == (5, 2, 2, 1)
    assert [c["name"] for c in d["categories"]] == ["Health", "Sports"]           # เรียงตามจำนวนคำค้นมาก -> น้อย
    assert d["places"] == ["TH", "WW"] and d["month"] == "2026-10" and d["n_trends_built"] == 3 and d["n_trends_shown"] == 2


def test_only_groups_behind_shown_trends_count_as_behind_the_report(run):
    d = st.load_talk(run, TRENDS)
    cats = {c["name"]: c for c in d["categories"]}
    assert cats["Health"]["fed"] == 3 and cats["Sports"]["fed"] == 0              # เทรนด์ "Dropped Trend" ไม่ได้อยู่ในรายงาน -> กลุ่มผลบอลไม่นับ
    assert d["n_fed"] == 3 and d["fed_pct"] == round(3 / 7 * 100, 1) and d["n_no_fed"] == 1
    assert d["top_fed"] == [{"name": "Health", "fed": 3}]
    assert d["n_link_check"] == 4                                                  # การโยงของ AI (path <> 0): 3 ในกลุ่มสุขภาพ + ผลบอล 1 = 4 รายการ ไม่ซ้ำ
    assert st.load_talk(run, [])["n_fed"] == 0 and st.load_talk(run)["n_fed"] == 0   # ไม่ส่งเทรนด์ = ไม่มีส่วน "เป็นที่มา"


def test_none_for_non_search_runs(run, tmp_path_factory):
    assert "cards" not in st.load_talk(run, TRENDS)                                 # หน้าตัวอย่างคำค้นต่อหมวดถูกแทนที่ด้วยส่วนที่ 2 เจาะรายหมวด (category_dive.py)
    empty = tmp_path_factory.mktemp("old_run")                                     # รอบ 3 สายเดิม: ไม่มีโฟลเดอร์ของ ① -> ไม่มีหน้า
    assert st.load_talk(empty, TRENDS) is None
    (empty / "search_stream_work" / "themes").mkdir(parents=True)
    assert st.load_talk(empty, TRENDS) is None                                      # มีโฟลเดอร์แต่ไม่มีผลลัพธ์ของสาย


def test_category_names_follow_google_and_file_keys():
    names = st.category_names()
    assert names["Arts_Entertainment"] == "Arts & Entertainment" and names["Beauty_Fitness"] == "Beauty & Fitness" and len(names) == 25
    assert st.cat_key("Arts & Entertainment") == "Arts_Entertainment"


def test_trend_sources_count_unique_searches_and_categories_per_trend(run):
    out = st.trend_sources(run, ["Sun Care", "Hair", "Dropped Trend", "Missing"])
    assert out["Sun Care"] == {"n": 2, "categories": ["Health"]} and out["Hair"] == {"n": 1, "categories": ["Health"]}
    assert out["Dropped Trend"] == {"n": 1, "categories": ["Sports"]} and "Missing" not in out
    assert list(st.trend_sources(run, ["Hair"])) == ["Hair"]                      # ขอเฉพาะเทรนด์ที่ต้องการ
    assert st.trend_sources(run.parent / "nowhere", ["Hair"]) == {}               # ไม่ใช่รอบสาย Search
