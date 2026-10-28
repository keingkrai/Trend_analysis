# -*- coding: utf-8 -*-
"""
Unit test ของ ⑳ ส่งออกให้ LLM (export_llm_data.py, 🆕 2026-10-26): ตารางเทรนด์กลาง / ตารางรวมลูกค้า / brief ต่อลูกค้า / meta + SQLite
และการต่อเข้า main.py (รันครั้งเดียวหลัง ⑰ ของทุกแบรนด์ในรอบ ทั้งโหมด 1/2/3)
ข้อมูลปลอมขนาดเล็กในโฟลเดอร์ชั่วคราว - ไม่เรียก API ไม่แตะโฟลเดอร์ output จริง

รัน: pytest main/tool/tests/test_llm_export.py -v
"""
import csv
import json
import sqlite3
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOL / "phase8_llm_export"))
sys.path.insert(0, str(TOOL.parent))

import export_llm_data as ex  # noqa: E402
import main as pipeline  # noqa: E402  (main/main.py)


def make_ctx():
    growth = [
        {"rank": 1, "name": "Alpha Trend", "key": "Paper::Alpha Trend", "stream": "Paper", "scores": [.9, .8, .7, .6, .5],
         "expected_pct": [10, 20, 30, 40, 50], "cagr_pct": [10, 9, 8, 7, 6], "long_rank": 1, "above_line": True, "past_growth_pct": 60.0,
         "recent_decline": False, "detail_rank": 1, "categories": ["Skin Care"], "keywords": ["a"], "display_name": "Alpha Plain"},
        {"rank": 2, "name": "Beta Trend", "key": "News::Beta Trend", "stream": "News", "scores": [.4, .4, .4, .4, .4],
         "expected_pct": [1, 2, 3, 4, 5], "cagr_pct": [1, 1, 1, 1, 1], "long_rank": 2, "above_line": False, "past_growth_pct": 5.0,
         "recent_decline": True, "detail_rank": None, "categories": [], "keywords": ["b"], "display_name": "Beta Plain"},
    ]
    products = [{"name": f"Rival {i}", "brand": "Rival", "similarity": 0.4 - i / 100, "price_thb": 100.0 + i, "size": 50.0, "unit_label": "ml",
                 "unit_price": 2.0, "is_mini": False, "reason": f"why {i}", "image_url": "http://x"} for i in range(6)]
    detail = {"key": "Paper::Alpha Trend", "name": "Alpha Trend", "display_name": "Alpha Plain", "keywords": ["k1", "k2"],
              "analysis": {"trend_stage": "Growing", "primary_driver": "Structural", "estimated_duration": "Medium-term",
                           "executive_summary": "Summary.", "consumer_intent_signal": "Intent.", "risk_scenario_if_forecast_fails": "Risk."},
              "l2": {"category": "Skin Care"}, "longevity_score": 60, "longevity_band": "durable", "data_quality": "rich", "cluster_size": 5,
              "target": "people", "key_ingredients": "ing", "key_benefits": "ben", "products": products}
    return {"meta": {"run_id": "r1", "topic": "t", "title": "T", "data_as_of": "Aug 2026", "forecast_start": "Sep 2026",
                     "forecast_end": "Aug 2029", "n_products_compared": 100,
                     "sources": {"products": {"collected_from": "2026-10-06", "collected_to": "2026-10-09"}}},
            "growth": {"all": growth, "n_total": 2, "n_detail": 1, "band": {"short": [-21, 26], "long": [-27, 48]},
                       "market_pct": [10, 12, 20, 30, 40], "past_inflated": True},
            "trends": [detail]}


def make_brand(brand="Acme", level="good", has_product=True):
    graded = {"brand": brand, "name": "Acme Serum", "name_full": "Acme Serum", "price_thb": 500.0, "similarity": 0.31234, "rank_in_tier": 3,
              "n_tier": 1000, "pct": 0.3, "size": 30.0, "unit_label": "ml", "unit_price": 16.66666, "is_mini": False, "category": "Skin Care",
              "level": level, "reason": "matches"}
    row = {"rank": 1, "name": "Alpha Trend", "trend": "Alpha Trend", "display_name": "Alpha Plain", "checked": True, "level": level if has_product else "below_average",
           "quadrant": "defend", "key_categories": ["Skin Care"], "no_key_product": not has_product,
           "graded": graded if has_product else None, "products": [graded] if has_product else [],
           "leader": {"brand": "Rival", "name": "Rival Gel", "price_thb": 400.0, "similarity": 0.4, "is_you": False} if has_product else None,
           "gap_to_leader": 0.0877 if has_product else None}
    counts = {lv: int(lv == row["level"]) for lv in ex.FIT_LEVELS}
    return {"brand": brand, "n_skus": 10, "portfolio": {"top_subcategories": [{"name": "Skin Care", "n": 8}], "price_min": 100.0, "price_median": 300.0, "price_max": 900.0},
            "top_pct": {"excellent": 1, "good": 5, "average": 20}, "momentum_split": 0.6,
            "rows": [row], "counts": counts, "n_checked": 1,
            "overall": {"level": row["level"], "n": 1, "k": 1, "at_or_better": {lv: 1 for lv in ex.FIT_LEVELS}, "next": None},
            "highlights": {"strongest": 1, "opportunity": None, "quick_win": None}, "opportunities": [], "missing_trends": [],
            "reasons_th": {"Alpha Trend": ["เหตุผลไทย"] if has_product else []}}


@pytest.fixture
def run(tmp_path):
    (tmp_path / ex.CONTEXT_FILE).write_text(json.dumps(make_ctx()), encoding="utf-8")
    (tmp_path / "phase6_brand_context_Acme.json").write_text(json.dumps(make_brand()), encoding="utf-8")
    return tmp_path


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
def test_files_tables_and_glossary_follow_the_column_spec(run):
    out = ex.export(run)["out_dir"]
    for name, (fname, columns, _d) in ex.TABLES.items():
        with open(out / fname, encoding="utf-8-sig") as f:
            assert next(csv.reader(f)) == [c for c, _t, _x in columns]
    con = sqlite3.connect(out / "llm_export.sqlite")
    assert con.execute("select count(*) from trends").fetchone()[0] == 2            # รวมเทรนด์ใต้เส้นตลาด
    assert con.execute("select count(*) from trend_top_products").fetchone()[0] == 5  # เฉพาะเทรนด์ที่มีสินค้า, ตัดที่ 5
    assert con.execute("select count(*) from customer_trends").fetchone()[0] == 1
    assert con.execute("select count(*) from glossary").fetchone()[0] == sum(len(c) for _f, c, _d in ex.TABLES.values())
    assert json.loads((out / "meta.json").read_text(encoding="utf-8"))["tables"].keys() == ex.TABLES.keys()


def test_trend_table_flags_and_forecast_columns(run):
    out = ex.export(run)["out_dir"]
    rows = {r["name"]: r for r in read_csv(out / "trends.csv")}
    a, b = rows["Alpha Trend"], rows["Beta Trend"]
    assert (a["trend_id"], a["above_market_line"], a["in_product_analysis"]) == ("alpha-trend", "1", "1")
    assert (b["above_market_line"], b["in_product_analysis"], b["recent_decline"]) == ("0", "0", "1")
    assert [a[f"expected_pct_y{y}"] for y in ex.YEARS] == ["10", "20", "30", "40", "50"]
    assert a["cagr_pct_short"] == "8" and a["cagr_pct_long"] == "6"
    assert a["keywords"] == "k1; k2" and a["executive_summary"] == "Summary." and b["executive_summary"] == ""


def test_customer_trend_row_matches_the_brand_context(run):
    out = ex.export(run)["out_dir"]
    row = read_csv(out / "customer_trends.csv")[0]
    assert (row["customer"], row["trend_id"], row["fit_level"]) == ("Acme", "alpha-trend", "good")
    assert row["quadrant"] == "defend" and row["has_product_in_category"] == "1"
    assert row["own_similarity"] == "0.3123" and row["own_unit_price_thb"] == "16.67" and row["own_reason_th"] == "เหตุผลไทย"
    assert row["leader_product"] == "Rival Gel" and row["leader_is_customer"] == "0" and row["gap_to_leader"] == "0.0877"
    assert row["expected_pct_short"] == "30" and row["expected_pct_long"] == "50"       # ปี 3 / ปี 5 ของตารางเทรนด์


def test_no_sales_columns_in_any_table_or_brief(run):
    """🆕 (2026-10-27) เกรดไม่ใช้ยอดขายแล้ว - ไม่มีคอลัมน์/ช่องยอดขายใน CSV, glossary และ brief"""
    out = ex.export(run)["out_dir"]
    for _name, (_fname, columns, _d) in ex.TABLES.items():
        assert not [c for c, _t, _x in columns if "sales" in c or "sold" in c or "units" in c]
    text = (out / "briefs" / "Acme.json").read_text(encoding="utf-8") + (out / "meta.json").read_text(encoding="utf-8")
    assert "sales_states" not in text and "sales_raised" not in text and "units_sold" not in text


def test_customer_row_translates_highlights_and_counts(run):
    out = ex.export(run)["out_dir"]
    c = read_csv(out / "customers.csv")[0]
    assert (c["customer"], c["overall_level"], c["n_good"], c["n_excellent"]) == ("Acme", "good", "1", "0")
    assert c["strongest_trend_id"] == "alpha-trend" and c["opportunity_trend_id"] == "" and c["portfolio_categories"] == "Skin Care:8"


def test_brief_is_self_contained_and_has_no_empty_values(run):
    out = ex.export(run)["out_dir"]
    brief = json.loads((out / "briefs" / "Acme.json").read_text(encoding="utf-8"))
    assert brief["customer"] == "Acme" and brief["summary"]["overall_level"] == "good" and brief["notes"]

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                assert x is not None and x != "" and x != {} and x != []
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(brief)
    t = brief["trends"][0]
    assert t["trend"] == "Alpha Plain" and t["best_product"]["name"] == "Acme Serum" and t["market_leader"]["product"] == "Rival Gel"
    assert t["forecast"]["search_change_pct_vs_last_12m"] == {ex.SY: 30, ex.LY: 50}
    assert "sales" not in t["best_product"] and set(t["fit"]) == {"level", "action_group", "category", "has_product_in_category"}
    assert "closest_market_products" not in t
    assert brief["market_median_search_change_pct"]["year_5"] == 40


def test_trend_without_customer_product_lists_closest_market_products(run):
    (run / "phase6_brand_context_Acme.json").write_text(json.dumps(make_brand(has_product=False)), encoding="utf-8")
    out = ex.export(run)["out_dir"]
    t = json.loads((out / "briefs" / "Acme.json").read_text(encoding="utf-8"))["trends"][0]
    assert t["fit"]["level"] == "below_average" and t["fit"]["has_product_in_category"] is False
    assert "best_product" not in t and "market_leader" not in t
    assert [p["product"] for p in t["closest_market_products"]] == ["Rival 0", "Rival 1", "Rival 2"]


def test_overall_meaning_for_the_lowest_level_counts_average_or_better():
    text = ex.overall_meaning({"level": "below_average", "n": 8, "k": 8, "at_or_better": {"excellent": 0, "good": 0, "average": 1, "below_average": 8}})
    assert text.startswith("only 1 of 8") and "average or better" in text
    assert "3 of 5 checked trends reach good or better" in ex.overall_meaning({"level": "good", "n": 5, "k": 3, "at_or_better": {}})
    assert ex.overall_meaning(None) is None


def test_run_without_brand_results_exports_trend_tables_only(tmp_path):
    (tmp_path / ex.CONTEXT_FILE).write_text(json.dumps(make_ctx()), encoding="utf-8")
    result = ex.export(tmp_path)
    assert result["customers"] == [] and result["n_trends"] == 2
    assert read_csv(result["out_dir"] / "customers.csv") == [] and list((result["out_dir"] / "briefs").glob("*.json")) == []


def test_rerun_removes_briefs_of_brands_that_disappeared(run):
    out = ex.export(run)["out_dir"]
    (run / "phase6_brand_context_Acme.json").rename(run / "phase6_brand_context_Other.json")
    (run / "phase6_brand_context_Other.json").write_text(json.dumps(make_brand("Other")), encoding="utf-8")
    ex.export(run)
    assert sorted(p.name for p in (out / "briefs").glob("*.json")) == ["Other.json"]


def test_thresholds_that_differ_between_brands_are_reported(run):
    other = make_brand("Other")
    other["top_pct"] = {"excellent": 2, "good": 5, "average": 20}
    (run / "phase6_brand_context_Other.json").write_text(json.dumps(other), encoding="utf-8")
    assert any("thresholds differ" in w for w in ex.export(run)["warnings"])


def test_row_with_a_column_outside_the_spec_is_rejected():
    with pytest.raises(ValueError):
        ex._matrix(ex.CUSTOMER_COLUMNS, [{"customer": "x", "surprise": 1}])


def test_slug_is_ascii_and_unique():
    taken = set()
    assert [ex._slug(n, taken) for n in ("A & B", "A  B", "ครีม")] == ["a-b", "a-b-2", "trend"]


# ---------------------------------------------------------------------------
# main.py: ⑳ รันครั้งเดียวหลัง ⑰ ของทุกแบรนด์ในรอบ (โหมด 1/2/3) - จำลอง run_stage กับ input ไม่รันสคริปต์จริง
# ---------------------------------------------------------------------------
@pytest.fixture
def calls(monkeypatch, tmp_path):
    """บันทึกทุกขั้นที่ main.py สั่งรัน เป็น (ชื่อสคริปต์ย่อ, TREND_RUN_ID, ข้อโต้แย้งเพิ่ม)"""
    log = []

    def fake_run_stage(label, rel_path, required, env, base=None, extra_args=()):
        log.append((Path(rel_path).stem, env.get("TREND_RUN_ID"), tuple(extra_args)))
        return True

    monkeypatch.setattr(pipeline, "run_stage", fake_run_stage)
    monkeypatch.setattr(pipeline, "OUTPUT_ROOT", tmp_path)
    return log


def answers(monkeypatch, *typed):
    it = iter(typed)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(it))


def stages(log):
    return [name for name, _run, _extra in log]


def test_run_llm_export_only_when_a_brand_report_was_built(calls):
    env = {"TREND_RUN_ID": "r1"}
    pipeline.run_llm_export(env, 0)
    pipeline.run_llm_export(env, 3, make_pdf=False)
    assert calls == []
    pipeline.run_llm_export(env, 2)
    assert calls == [("export_llm_data", "r1", ())]


def test_mode_2_exports_once_after_all_brands(calls, monkeypatch):
    monkeypatch.setattr(pipeline, "_list_available_runs", lambda *a, **k: [("label", "run_a")])
    monkeypatch.setattr(pipeline, "_choose_run", lambda runs, what: ("label", "run_a"))
    answers(monkeypatch, "Eucerin", "Mizumi", "")
    pipeline.run_mode_brand_lookup()
    assert stages(calls) == ["run_brand_coverage", "build_brand_report", "run_brand_coverage", "build_brand_report", "export_llm_data"]
    assert calls[-1][1] == "run_a" and calls[1][2] == ("--brand", "Eucerin")


def test_mode_2_without_brands_does_not_export(calls, monkeypatch):
    monkeypatch.setattr(pipeline, "_list_available_runs", lambda *a, **k: [("label", "run_a")])
    monkeypatch.setattr(pipeline, "_choose_run", lambda runs, what: ("label", "run_a"))
    answers(monkeypatch, "")
    pipeline.run_mode_brand_lookup()
    assert calls == []


def full_args(**kw):
    base = dict(topic="t", years=3, top_n=5, run_id="run_x", skip_discovery=True, skip_pdf=False, skip_brand=False)
    return pipeline.argparse.Namespace(**{**base, **kw})


def test_mode_1_exports_after_the_last_brand_report(calls, monkeypatch):
    answers(monkeypatch, "Eucerin", "")
    pipeline.run_mode_full_pipeline(full_args())
    assert stages(calls)[-3:] == ["run_brand_coverage", "build_brand_report", "export_llm_data"]
    assert stages(calls).count("export_llm_data") == 1 and calls[-1][1] == "run_x"
    assert stages(calls).index("build_pdf_report") < stages(calls).index("run_brand_coverage")


@pytest.mark.parametrize("kw,typed", [({"skip_pdf": True}, ["Eucerin", ""]), ({"skip_brand": True}, []), ({}, [""])])
def test_mode_1_skips_export_without_brand_reports(calls, monkeypatch, kw, typed):
    answers(monkeypatch, *typed)
    pipeline.run_mode_full_pipeline(full_args(**kw))
    assert "export_llm_data" not in stages(calls)


def test_mode_3_exports_once_after_the_source_brands(calls, monkeypatch, tmp_path):
    from test_refresh_mode import _source_run
    _source_run(tmp_path, name="src_run", brands=("Mizumi", "Eucerin Pro"))
    monkeypatch.setattr(pipeline, "_last_complete_month", lambda today=None: "2026-09")
    args = pipeline.argparse.Namespace(refresh="src_run", skip_pdf=False, skip_brand=False)
    pipeline.run_mode_refresh(args)
    names = stages(calls)
    assert names.count("export_llm_data") == 1 and names[-1] == "export_llm_data"
    assert names[-5:-1] == ["run_brand_coverage", "build_brand_report", "run_brand_coverage", "build_brand_report"]
    assert calls[-1][1] != "src_run" and calls[-1][1] == calls[-2][1]       # ส่งออกที่รอบใหม่ ไม่ใช่รอบเดิม


def test_mode_3_skip_pdf_does_not_export(calls, monkeypatch, tmp_path):
    from test_refresh_mode import _source_run
    _source_run(tmp_path, name="src_run")
    monkeypatch.setattr(pipeline, "_last_complete_month", lambda today=None: "2026-09")
    pipeline.run_mode_refresh(pipeline.argparse.Namespace(refresh="src_run", skip_pdf=True, skip_brand=False))
    assert "export_llm_data" not in stages(calls) and "build_brand_report" not in stages(calls)
