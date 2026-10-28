# -*- coding: utf-8 -*-
"""
🆕 (2026-10-07) โหมด 3 ของ main.py — อัปเดตรอบเดิมด้วย Google Trends ล่าสุด (เทรนด์ + คีย์เวิร์ดเดิม ผลลงรอบใหม่)
ทดสอบส่วนที่ไม่เรียก API: เตรียมโฟลเดอร์รอบใหม่ อ่านค่าของรอบเดิม และการใช้จุดเด่น (⑪) / เหตุผลจับคู่ (⑫) ของรอบเดิมซ้ำ

รัน: pytest main/tool/tests/test_refresh_mode.py -v
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
TOOL_DIR = TESTS_DIR.parent
for _p in (TOOL_DIR, TOOL_DIR / "phase3_supply_layer", TOOL_DIR / "phase6_pdf_report", TOOL_DIR.parent):
    sys.path.insert(0, str(_p))

import main as pipeline  # noqa: E402  (main/main.py)
import extract_trend_highlights as eth  # noqa: E402
import validate_at_scale_nvidia as vsn  # noqa: E402
from common import bootstrap  # noqa: E402
from match_supply import build_trend_matchable_text  # noqa: E402
from report_data import _models_used, _run_date  # noqa: E402


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _profile(trend, stream="Social", job="ลดสิว"):
    return {"trend": trend, "stream": stream, "trend_type": "สินค้า", "attribute": "a",
            "functional_consequence": "ลดการอักเสบ", "psychosocial_consequence": "มั่นใจ",
            "job_to_be_done": job, "point_of_difference": "อ่อนโยน", "point_of_parity": "p"}


def _source_run(root, name="topic_20260916_082438", brands=("Mizumi", "Eucerin Pro")):
    """รอบเดิมจำลอง: ผล 3 สาย + ไฟล์เปรียบเทียบ + ⑪ + ⑥ growth + ⑬ + manifest"""
    run = root / name
    keywords = {"phase1_paper_stream_result.json": "Retinol, peptide serum",
                "phase2_social_stream_result.json": "retinol ,Body Wash",
                "phase2_news_stream_result.json": "sunscreen"}
    for fname, kws in keywords.items():
        _write(run / fname, {"topic": "beauty and personal care", "trends": [],
                             "keywords": [{"Trend Name": fname, "Search_Keywords": kws}]})
    _write(run / "phase2_all_streams_comparison.json", {"ok": True})
    _write(run / "phase3_trend_highlights_result.json",
           {"requested_top_n": 8, "profiles": [_profile("Acne")], "extra_profiles": [_profile("Sun", "News")]})
    _write(run / "phase2_growth_score_result.json", {"as_of": "2026-08"})
    for b in brands:
        _write(run / f"phase3_brand_coverage_{b.replace(' ', '_')}.json", {"brand": b})
    _write(run / "_manifest.json", {
        "paper_stream": {"timestamp": "2026-09-16T08:24:38", "years": "3", "models_used": {"zai.glm-5": 14}},
        "social_stream": {"timestamp": "2026-09-16T09:00:00", "years": "3",
                          "models_used": {"zai.glm-5": 14, "mistral.large": 1}},
        "news_stream": {"timestamp": "2026-09-16T10:00:00", "years": "3", "models_used": {"zai.glm-5": 15}},
        "fetch_trends_worldwide_serpapi": {"timestamp": "2026-09-16T11:00:00", "years": "4"},
    })
    return run


# ---------------------------------------------------------------------------
# main.py - อ่านค่าของรอบเดิม + เตรียมรอบใหม่
# ---------------------------------------------------------------------------

def test_refresh_config_reads_topic_years_top_n_and_data_month_of_source_run(tmp_path):
    cfg = pipeline._refresh_config(_source_run(tmp_path))
    # จำนวนปีเอาจากขั้น ⑦ ก่อน (ค่าที่ใช้พยากรณ์จริง) ไม่ใช่ entry แรกที่เจอ
    assert cfg == {"topic": "beauty and personal care", "years": 4, "top_n": 8, "as_of": "2026-08"}


def test_refresh_config_falls_back_to_defaults_when_files_are_missing(tmp_path):
    run = tmp_path / "bare"
    run.mkdir()
    assert pipeline._refresh_config(run) == {"topic": "beauty and personal care", "years": 3,
                                             "top_n": pipeline.DEFAULT_TOP_N, "as_of": ""}


def test_source_brands_use_brand_field_not_file_name(tmp_path):
    assert pipeline._source_brands(_source_run(tmp_path)) == ["Eucerin Pro", "Mizumi"]


def test_count_keywords_counts_unique_lowercase_keywords_across_streams(tmp_path):
    # retinol ซ้ำ 2 สาย (ตัวพิมพ์/ช่องว่างต่างกัน) นับครั้งเดียว
    assert pipeline._count_keywords(_source_run(tmp_path)) == 4


@pytest.mark.parametrize("today, expected", [(date(2026, 10, 7), "2026-09"), (date(2026, 1, 1), "2025-12"),
                                             (date(2026, 3, 31), "2026-02")])
def test_last_complete_month_is_previous_calendar_month(today, expected):
    assert pipeline._last_complete_month(today) == expected


def test_prepare_refresh_run_copies_stream_results_and_records_source(tmp_path):
    source = _source_run(tmp_path)
    run = tmp_path / "topic_20261007_101500"
    cfg = pipeline._refresh_config(source)

    copied = pipeline._prepare_refresh_run(source, run, cfg)

    # 🆕 (2026-10-27) รอบเก่า = 3 สายเดิม (ไม่มีไฟล์สาย Search ให้สำเนา)
    assert copied == list(pipeline.LEGACY_STREAM_FILES) + ["phase2_all_streams_comparison.json"]
    for name in copied:
        assert (run / name).read_bytes() == (source / name).read_bytes()
    # ผลขั้นอื่นของรอบเดิม (⑪ ⑥ ⑬) ต้องไม่ติดมา - ⑦ เป็นต้นไปต้องคำนวณใหม่ในรอบนี้
    assert not (run / "phase3_trend_highlights_result.json").exists()
    assert not list(run.glob("phase3_brand_coverage_*.json"))
    entry = json.loads((run / "_manifest.json").read_text(encoding="utf-8"))[pipeline.REFRESH_KEY]
    assert entry["refreshed_from"] == source.name and entry["run_id"] == run.name
    assert entry["source_data_as_of"] == "2026-08" and entry["years"] == "4"
    assert entry["evidence_collected"] == "2026-09-16T08:24:38"
    assert entry["models_used"] == {"zai.glm-5": 43, "mistral.large": 1}
    assert pipeline._refreshed_from(run) == source.name and pipeline._refreshed_from(source) == ""


def test_refresh_of_a_refreshed_run_keeps_original_evidence_date_and_models(tmp_path):
    first = tmp_path / "topic_20261007_101500"
    pipeline._prepare_refresh_run(_source_run(tmp_path), first, {"topic": "t", "years": 3, "as_of": ""})
    second = tmp_path / "topic_20261107_101500"
    pipeline._prepare_refresh_run(first, second, {"topic": "t", "years": 3, "as_of": ""})
    entry = json.loads((second / "_manifest.json").read_text(encoding="utf-8"))[pipeline.REFRESH_KEY]
    assert entry["refreshed_from"] == first.name
    assert entry["evidence_collected"] == "2026-09-16T08:24:38"
    assert entry["models_used"] == {"zai.glm-5": 43, "mistral.large": 1}


def test_prepare_refresh_run_copies_search_stream_result_of_new_runs(tmp_path):
    """🆕 (2026-10-27) รอบใหม่มีแต่ผลสาย Search (Google Trends) - สำเนาไฟล์นั้น + รายชื่อที่ตรวจไว้ ไม่ต้องมี 3 สายเดิม"""
    source = tmp_path / "search_run"
    _write(source / "phase2_search_stream_result.json", {"topic": "beauty", "trends": [],
                                                          "keywords": [{"Trend Name": "Haze", "Search_Keywords": "a, b"}]})
    (source / "phase2_search_candidates.csv").write_text("keep,rank\n1,1\n", encoding="utf-8")
    _write(source / "_manifest.json", {"search_stream": {"timestamp": "2026-10-27T10:00:00", "models_used": {"zai.glm-5": 52}}})
    run = tmp_path / "beauty_20261028_090000"

    copied = pipeline._prepare_refresh_run(source, run, {"topic": "beauty", "years": 3, "as_of": ""})

    assert copied == ["phase2_search_stream_result.json", "phase2_search_candidates.csv"]
    entry = json.loads((run / "_manifest.json").read_text(encoding="utf-8"))[pipeline.REFRESH_KEY]
    assert entry["models_used"] == {"zai.glm-5": 52} and entry["evidence_collected"] == "2026-10-27T10:00:00"
    assert pipeline._get_run_topic(source) == "beauty" and pipeline._count_keywords(source) == 2


def test_prepare_refresh_run_stops_before_creating_folder_when_stream_results_missing(tmp_path):
    source = _source_run(tmp_path)
    (source / "phase2_news_stream_result.json").unlink()
    run = tmp_path / "new_run"
    with pytest.raises(SystemExit):
        pipeline._prepare_refresh_run(source, run, {"topic": "t", "years": 3, "as_of": ""})
    assert not run.exists()


def test_report_dates_refreshed_run_by_refresh_time_and_lists_source_models(tmp_path):
    """รายงานใช้ timestamp แรกสุดใน manifest เป็นวันที่ของรอบ - รอบอัปเดตต้องเป็นวันที่อัปเดต ไม่ใช่วันเก็บหลักฐานของรอบเดิม"""
    run = tmp_path / "topic_20261007_101500"
    pipeline._prepare_refresh_run(_source_run(tmp_path), run, {"topic": "t", "years": 3, "as_of": ""})
    manifest = json.loads((run / "_manifest.json").read_text(encoding="utf-8"))
    manifest["rank_trends"] = {"timestamp": "2099-01-01T00:00:00", "models_used": {}}
    assert _run_date(run, manifest).date() == datetime.now().date()
    assert _models_used(manifest) == ["zai.glm-5", "mistral.large"]


def test_list_available_runs_filters_by_required_files_and_labels_refreshed_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "OUTPUT_ROOT", tmp_path)
    source = _source_run(tmp_path)
    refreshed = tmp_path / "topic_20261007_101500"
    pipeline._prepare_refresh_run(source, refreshed, {"topic": "t", "years": 3, "as_of": ""})
    (tmp_path / "_backups").mkdir()
    (tmp_path / "half_run").mkdir()   # ไม่มีผล ①-⑤ ครบ
    _write(tmp_path / "half_run" / "phase1_paper_stream_result.json", {"topic": "x"})

    runs = {run_id: label for label, run_id, _ in
            pipeline._list_available_runs(required=pipeline.LEGACY_STREAM_FILES, include_legacy=False)}
    assert set(runs) == {source.name, refreshed.name}
    assert runs[refreshed.name].endswith(f"[อัปเดตจาก {source.name}]") and "อัปเดตจาก" not in runs[source.name]
    # โหมด 2 (ค่าเริ่มต้น) ยังต้องมีผล ⑪ - รอบอัปเดตที่ยังไม่ถึง ⑪ ไม่โผล่
    assert [r[1] for r in pipeline._list_available_runs()] == [source.name]


def test_refresh_starts_at_google_trends_stage():
    assert pipeline.STAGES[pipeline.REFRESH_FIRST_STAGE][1].endswith("fetch_trends_worldwide_serpapi.py")
    assert pipeline.REFRESH_ENV == bootstrap.REFRESH_ENV


# ---------------------------------------------------------------------------
# bootstrap.refresh_source_dir
# ---------------------------------------------------------------------------

def test_refresh_source_dir_none_when_env_unset_and_stops_when_folder_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "_OUTPUT_ROOT", tmp_path)
    monkeypatch.delenv(bootstrap.REFRESH_ENV, raising=False)
    assert bootstrap.refresh_source_dir() is None
    (tmp_path / "old_run").mkdir()
    monkeypatch.setenv(bootstrap.REFRESH_ENV, "old_run")
    assert bootstrap.refresh_source_dir() == tmp_path / "old_run"
    monkeypatch.setenv(bootstrap.REFRESH_ENV, "missing_run")
    with pytest.raises(SystemExit):
        bootstrap.refresh_source_dir()


# ---------------------------------------------------------------------------
# ⑪ / ⑫ ใช้ผลของรอบเดิมซ้ำ
# ---------------------------------------------------------------------------

def test_reusable_profiles_include_detail_and_extra_profiles(tmp_path):
    source = _source_run(tmp_path)
    reusable = eth.load_reusable_profiles(source)
    assert set(reusable) == {("Social", "Acne"), ("News", "Sun")}
    assert reusable[("Social", "Acne")]["job_to_be_done"] == "ลดสิว"
    assert eth.load_reusable_profiles(None) == {}
    assert eth.load_reusable_profiles(tmp_path / "no_such_run") == {}


def test_reusable_profiles_keep_source_exclusion_decisions_without_llm(tmp_path):
    """เทรนด์ที่รอบเดิมตัดสินว่าจับคู่ไม่ได้ได้ profile แทนที่ซึ่งให้เหตุผลเดิมผ่าน exclusion_reason ตัวเดียวกับ ⑪ -
    เหตุผลที่ไม่รู้จัก (เช่น ล้มเหลวทางเทคนิค) ไม่ใช้ซ้ำ ให้ LLM ตัดสินใหม่"""
    source = _source_run(tmp_path)
    path = source / "phase3_trend_highlights_result.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["checked_trends"] = [
        {"stream": "Social", "trend": "Acne", "matchable": True, "reason": None},
        {"stream": "News", "trend": "Livestream", "matchable": False, "reason": eth.REASON_CHANNEL},
        {"stream": "Paper", "trend": "Vague", "matchable": False, "reason": eth.REASON_NO_TEXT},
        {"stream": "Paper", "trend": "Odd", "matchable": False, "reason": "อย่างอื่น"}]
    data["excluded_trends"] = [{"stream": "News", "trend": "Old", "reason": eth.REASON_CHANNEL}]  # รอบเก่าที่ไม่มี checked
    _write(path, data)

    reusable = eth.load_reusable_profiles(source)
    assert ("Paper", "Odd") not in reusable
    assert reusable[("Social", "Acne")]["job_to_be_done"] == "ลดสิว"            # profile จริงไม่ถูกทับ
    stubs = {k: reusable[k] for k in [("News", "Livestream"), ("Paper", "Vague"), ("News", "Old")]}
    assert stubs[("News", "Livestream")]["trend_type"] == eth.TREND_TYPE_CHANNEL
    assert stubs[("Paper", "Vague")]["trend_type"] == eth.TREND_TYPE_PRODUCT
    assert all(build_trend_matchable_text(p) == "" for p in stubs.values())   # ⑫ ไม่มีข้อความให้ embed เหมือนเดิม


def test_reusable_reasons_keyed_by_trend_with_source_matchable_text(tmp_path):
    source = _source_run(tmp_path)
    _write(source / vsn.RESULT_PATH.name, {"results": {
        "Social::Acne": {"trend_name": "Acne", "stream": "Social", "top_matches": [
            {"brand": "A", "product_name": "Gel", "match_reason": "ลดสิวได้"},
            {"brand": "B", "product_name": "Cream", "match_reason": ""},        # ไม่มีเหตุผล = ไม่ใช้ซ้ำ
            {"brand": "C", "product_name": "Toner", "match_reason": None}]},
        "Paper::Gone": {"trend_name": "Gone", "stream": "Paper", "top_matches": [   # ไม่มี profile ใน ⑪ = ข้าม
            {"brand": "A", "product_name": "Gel", "match_reason": "x"}]},
    }})
    reusable = vsn.load_reusable_reasons(source)
    assert set(reusable) == {("Social", "Acne")}
    assert reusable[("Social", "Acne")]["reasons"] == {("A", "Gel"): "ลดสิวได้"}
    # ⑫ ใช้ซ้ำเฉพาะเมื่อข้อความจับคู่ของ profile รอบนี้ตรงกับรอบเดิม (⑪ ใช้จุดเด่นเดิม)
    assert reusable[("Social", "Acne")]["text"] == build_trend_matchable_text(_profile("Acne"))
    assert reusable[("Social", "Acne")]["text"] != build_trend_matchable_text(_profile("Acne", job="กันแดด"))
    assert vsn.load_reusable_reasons(None) == {}
    assert vsn.load_reusable_reasons(tmp_path / "no_such_run") == {}
