# -*- coding: utf-8 -*-
"""
🆕 (2026-10-27) สาย Search (Google Trends คำค้นกำลังขึ้นรายหมวด) ที่ใช้แทน 3 สายเดิม - ทดสอบส่วนที่เป็นกฎ (ไม่เรียก API จริง)
รายชื่อสายที่เดียว · การรวมคำค้น · กฎหลักฐานของการโยง · กฎเรียงหัวข้อ · แหล่งที่มาในรายงาน

รัน: pytest main/tool/tests/test_search_stream.py -v
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

TESTS_DIR = Path(__file__).resolve().parent
TOOL_DIR = TESTS_DIR.parent
for _p in (TOOL_DIR, TOOL_DIR / "phase9_search_stream", TOOL_DIR / "phase6_pdf_report"):
    sys.path.insert(0, str(_p))

from common import streams  # noqa: E402
import rising  # noqa: E402
import themes as th  # noqa: E402
import search_stream as ss  # noqa: E402
import i18n  # noqa: E402


class FakeClient:
    """แทน Bedrock client: ตอบ JSON ที่กำหนดไว้ (เหมือน openai SDK: .chat.completions.create().choices[0].message.content)"""

    def __init__(self, payload):
        self.payload = payload
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **_):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.payload)))])


def test_present_streams_only_returns_streams_with_result_files(tmp_path):
    (tmp_path / "phase2_search_stream_result.json").write_text("{}", encoding="utf-8")
    assert list(streams.present_streams(tmp_path)) == ["Search"]
    for f in ("phase1_paper_stream_result.json", "phase2_social_stream_result.json", "phase2_news_stream_result.json"):
        (tmp_path / f).write_text("{}", encoding="utf-8")
    # 3 สายเดิมก่อน Search เสมอ - รอบเก่าเรียงเหมือนเดิม
    assert list(streams.present_streams(tmp_path)) == ["Paper", "Social", "News", "Search"]


def test_norm_joins_thai_words_google_splits_but_keeps_spaces_between_latin_words():
    assert rising.norm("ทรง ผม ชาย 2026") == "ทรงผมชาย 2026"
    assert rising.norm("  Best   Face Masks  ") == "best face masks"


def test_categories_count_repeated_ids_once_as_top_level():
    cats = rising.load_categories()
    ids = [c["cat_id"] for c in cats]
    assert len(ids) == len(set(ids))
    pets = next(c for c in cats if c["cat_id"] == 66)
    assert pets["level"] == 1 and pets["l1"] == "Pets & Animals"
    assert sum(c["level"] == 1 for c in cats) == 25


def test_plan_jobs_deep_places_get_every_category_top_places_only_top_level():
    cats = rising.load_categories()
    jobs = rising.plan_jobs(cats, ["TH", "WW"], ["US", "TH"])
    assert len([j for j in jobs if j[0] == "TH"]) == len(cats)       # TH อยู่ทั้งสองแบบ ไม่ดึงซ้ำ
    assert len([j for j in jobs if j[0] == "US"]) == 25


def test_per_category_queries_merges_places_and_keeps_highest_growth_spelling():
    rows = [{"l1": "Health", "geo": "WW", "query": "Sunscreen  SPF", "query_norm": "sunscreen spf", "extracted_value": 300, "value": "+300%"},
            {"l1": "Health", "geo": "TH", "query": "sunscreen spf", "query_norm": "sunscreen spf", "extracted_value": 5200, "value": "Breakout"},
            {"l1": "News", "geo": "TH", "query": "haze", "query_norm": "haze", "extracted_value": 100, "value": "+100%"}]
    out = ss.per_category_queries(rows)
    assert out["Health"] == [{"query_norm": "sunscreen spf", "query": "sunscreen spf", "geos": "TH,WW",
                              "max_value": 5200, "value": "Breakout"}]
    assert [q["query"] for q in out["News"]] == ["haze"]


def _grouped():
    queries = [{"query_norm": f"q{i}", "query": f"q{i}", "geos": g, "max_value": 100 - i, "value": v}
               for i, (g, v) in enumerate([("TH,WW", "Breakout"), ("TH", "+50%"), ("WW", "+20%"), ("WW", "+10%")], 1)]
    return {"themes": [{"name": "Haze", "name_th": "หมอกควัน", "about": "", "ids": [1, 2]},
                       {"name": "Piercing", "name_th": "เจาะ", "about": "", "ids": [3, 4]},
                       {"name": "Other", "name_th": "อื่นๆ", "about": "", "ids": []}], "queries": queries}


def test_link_without_example_evidence_becomes_no_link_and_bad_categories_are_dropped(tmp_path):
    client = FakeClient({"links": [
        {"id": 1, "path": 2, "cats": ["Skin Care", "Hats"], "need": "กันฝุ่น", "reason": "r", "evidence": [1]},
        {"id": 2, "path": 1, "cats": ["Colour Cosmetics"], "need": "x", "reason": "y", "evidence": []}]})
    out = th.link_category(client, "News", _grouped(), tmp_path)
    haze, piercing = out
    assert (haze["path"], haze["cats"], haze["evidence"]) == (2, ["Skin Care"], ["q1"])
    assert (piercing["path"], piercing["note"], piercing["llm_path"], piercing["cats"]) == (0, "no evidence", 1, [])
    assert (tmp_path / "News.json").exists()   # cache - รันซ้ำไม่ถาม LLM


def test_candidates_ordered_by_places_then_thailand_then_size():
    g = _grouped()
    groups = {"News": g, "Health": {**g, "themes": [{**g["themes"][1], "name": "Dry skin"}]}}
    links = {"News": [{"theme": "Haze", "path": 2, "cats": ["Skin Care"], "need": "n", "reason": "", "evidence": ["q1"]},
                      {"theme": "Piercing", "path": 0, "cats": [], "need": "", "reason": "", "evidence": []}],
             "Health": [{"theme": "Dry skin", "path": 3, "cats": ["Skin Care"], "need": "n", "reason": "", "evidence": ["q3"]}]}
    out = ss.linked_candidates(groups, links)
    assert [c["theme"] for c in out] == ["Haze", "Dry skin"]          # ไม่โยง = ไม่เป็นตัวเลือก
    assert out[0]["places"] == ["TH", "WW"] and out[0]["has_th"] and out[0]["breakout_share"] == 0.5
    assert out[1]["places"] == ["WW"] and not out[1]["has_th"]


def test_clean_terms_lowercases_dedupes_and_drops_long_phrases():
    assert ss.clean_terms(["Sweat Proof Sunscreen", "sweat proof  sunscreen", "a b c d e", "", "Lip,Balm"], 6) == \
        ["sweat proof sunscreen", "lip balm"]


def test_report_source_rows_show_rising_searches_in_both_languages():
    meta = {"sources": {"rising": {"n_lists": 598, "n_categories": 25, "places": ["TH", "WW"], "n_queries": 10701, "n_trends": 12}}}
    en = dict(i18n.source_rows(meta, "en"))
    th_rows = dict(i18n.source_rows(meta, "th"))
    assert en["Rising searches"] == "10,701 rising Google searches from 598 category lists (Thailand, worldwide) - 12 trends picked"
    assert "ไทย, ทั่วโลก" in th_rows["คำค้นที่กำลังขึ้น"]
    groups = i18n.source_doc_groups({"source_docs": {"rising": [{"title": "Google Trends rising searches · Health · Thailand",
                                                                 "url": "https://trends.google.com/trends/explore?cat=45&geo=TH"}]}}, "en")
    assert groups[0]["label"] == "Rising searches" and groups[0]["docs"][0]["url"].endswith("geo=TH")
