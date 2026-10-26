# -*- coding: utf-8 -*-
"""
Unit test ของฟังก์ชัน pure ที่ audit (m4) ระบุชื่อตรงๆ ว่าไม่มีเทสเลย: compute_longevity,
aggregate_forecast (aggregate_to_category_level/aggregate_to_overall_level), compute_rank_score

"pure function" = input เดียวกันต้องได้ output เดียวกันเสมอ ไม่มี side effect/สุ่ม/เรียก API - 3 ตัวนี้
ทำหน้าที่ "คำนวณคะแนนจาก verdict ที่ตัดสินไว้แล้ว" ซึ่งเป็นหลักการหลักของโปรเจกต์นี้ (LLM ให้ verdict,
โค้ดคำนวณคะแนน ไม่ให้ LLM คิดเลขเอง) - จึงสำคัญที่สุดที่ต้องเทสได้แบบไม่ต้องยิง API

รัน: pytest main/tool/tests/test_pure_functions.py -v
"""
import sys
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "phase2_three_streams")))
sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "phase2_three_streams" / "social")))

import pandas as pd
import pytest

from common.bootstrap import (_BedrockClientShim, compute_longevity, evidence_in_document,
                              recompute_longevity_score, verify_report_against_source)
from discover_pantip import clean_pantip_query, extract_search_results_text
from discover_reddit import format_comment_tree
from aggregate_forecast import aggregate_to_category_level, aggregate_to_overall_level
from rank_trends import compute_rank_score, normalize_cluster_size


# ---------------------------------------------------------------------------
# compute_longevity() / recompute_longevity_score()
# ---------------------------------------------------------------------------

def _dim(verdict, evidence="some real quoted evidence"):
    return {"verdict": verdict, "evidence": evidence, "note": ""}


def _payload(d1=1, d2=0, d3=1, d4=1, d5=1, headwind_types=None):
    return {
        "D1": _dim(d1), "D2": _dim(d2), "D3": _dim(d3), "D4": _dim(d4), "D5": _dim(d5),
        "headwind": {"types": headwind_types or []},
    }


def test_compute_longevity_all_positive_no_headwind_gets_high_band():
    # ตัวอย่าง [สูง] จาก Longevity Score v2 doc §2: D1=D3=D4=D5=+1, ไม่มี headwind
    result = compute_longevity(_payload(d1=1, d2=1, d3=1, d4=1, d5=1))
    assert result["score"] == 95  # 50 + (12+10+11+6+6) = 95, ชนเพดาน max(5, min(95, ...))
    assert result["band"] == "durable"


def test_compute_longevity_all_negative_gets_low_band():
    result = compute_longevity(_payload(d1=-1, d2=-1, d3=-1, d4=-1, d5=-1))
    assert result["score"] == 5  # 50 - 45 = 5, ชนพื้น max(5, ...)
    assert result["band"] == "likely_fad"


def test_compute_longevity_headwind_penalty_scales_with_count():
    base = compute_longevity(_payload(d1=1, d2=0, d3=1, d4=1, d5=1))
    one_headwind = compute_longevity(_payload(d1=1, d2=0, d3=1, d4=1, d5=1, headwind_types=["A"]))
    two_headwind = compute_longevity(_payload(d1=1, d2=0, d3=1, d4=1, d5=1, headwind_types=["A", "B"]))
    assert one_headwind["score"] == base["score"] - 10
    assert two_headwind["score"] == base["score"] - 20  # -20 ไม่ใช่ -30 (คงที่ตั้งแต่ 2 ตัวขึ้นไป)


def test_compute_longevity_cross_source_confirmed_forces_d2_positive():
    """🆕 (2026-09-12, audit M1) นี่คือจุดที่เคยเป็นโค้ดตาย (ไม่มี caller ส่ง True มาเลย) จนกระทั่งแก้
    ให้ rank_trends.py เรียกจริง - เทสนี้ล็อกพฤติกรรมไว้กันกลับไปพังอีก"""
    without = compute_longevity(_payload(d1=1, d2=-1, d3=1, d4=1, d5=1), cross_source_confirmed=False)
    with_confirm = compute_longevity(_payload(d1=1, d2=-1, d3=1, d4=1, d5=1), cross_source_confirmed=True)
    assert with_confirm["breakdown"]["D2"] == 1
    assert with_confirm["score"] > without["score"]


def test_compute_longevity_insufficient_evidence_when_coverage_low():
    payload = _payload()
    for k in ["D1", "D2", "D3"]:
        payload[k]["evidence"] = ""  # ไม่มีหลักฐานจริง 3/5 มิติ
    result = compute_longevity(payload)
    assert result["evidence_coverage"] == 2
    assert result["insufficient_evidence"] is True


def test_recompute_longevity_score_matches_compute_longevity_without_confirmation():
    """recompute_longevity_score ต้องให้ผลตรงกับ compute_longevity ทุกประการเมื่อไม่มีการปรับข้ามสาย/
    comparative - สองฟังก์ชันนี้ต้อง "เห็นตรงกัน" เสมอ ไม่งั้น Longevity Score จะเพี้ยนระหว่างขั้น"""
    payload = _payload(d1=1, d2=0, d3=-1, d4=1, d5=0, headwind_types=["A"])
    original = compute_longevity(payload)
    recomputed = recompute_longevity_score(original["breakdown"], original["headwind_types"])
    assert recomputed["score"] == original["score"]
    assert recomputed["band"] == original["band"]


def test_recompute_longevity_score_comparative_delta_applies():
    """🆕 (2026-09-11, §10.1) comparative_delta ต้องบวกเข้าไปตรงๆ - นี่คือกลไกที่แก้ปัญหา "85/95 กระจุก" """
    breakdown = {"D1": 1, "D2": 0, "D3": 1, "D4": 1, "D5": 1}
    baseline = recompute_longevity_score(breakdown, [])
    penalized = recompute_longevity_score(breakdown, [], comparative_delta=-22)
    assert penalized["score"] == baseline["score"] - 22


# ---------------------------------------------------------------------------
# aggregate_to_category_level() / aggregate_to_overall_level()
# ---------------------------------------------------------------------------

def test_aggregate_category_level_averages_within_stream():
    df = pd.DataFrame([
        {"Current_Z": 0.0, "Forecast_Avg_Z": 1.0, "Z_Delta": 1.0},
        {"Current_Z": 0.2, "Forecast_Avg_Z": 0.6, "Z_Delta": 0.4},
    ])
    result = aggregate_to_category_level({"Paper": df})
    row = result.iloc[0]
    assert row["Stream"] == "Paper"
    assert row["N_Clusters"] == 2
    assert row["Z_Delta"] == pytest.approx(0.7)
    assert row["Status"] == "Rising"  # 0.7 > 0.2 ตามเกณฑ์ _status_from_z_delta


def test_aggregate_category_level_skips_empty_or_none_streams():
    df = pd.DataFrame([{"Current_Z": 0.1, "Forecast_Avg_Z": 0.9, "Z_Delta": 0.8}])
    result = aggregate_to_category_level({
        "Paper": df, "News-Intl": pd.DataFrame(), "News-Thai": None,
    })
    assert len(result) == 1
    assert result.iloc[0]["Stream"] == "Paper"


def test_aggregate_overall_level_equal_weight_not_skewed_by_cluster_count():
    """🆕 regression test ของ smoke test เดิมใน aggregate_forecast.py's __main__ (2026-08-31 decision)
    - หมวดที่มีคลัสเตอร์น้อย (Paper, 2 กลุ่ม, Z_Delta แรงมาก) ต้องมีน้ำหนักเท่ากับหมวดที่มีคลัสเตอร์เยอะ
    (Social, 5 กลุ่ม, นิ่งกว่า) ไม่ใช่ถูกกลบเสียงเพราะจำนวนกลุ่มน้อยกว่า"""
    paper_mr = pd.DataFrame([
        {"Current_Z": 0.1, "Forecast_Avg_Z": 1.5, "Z_Delta": 1.4},
        {"Current_Z": 0.3, "Forecast_Avg_Z": 1.1, "Z_Delta": 0.8},
    ])
    social_mr = pd.DataFrame([
        {"Current_Z": 0.2, "Forecast_Avg_Z": 0.3, "Z_Delta": 0.1},
        {"Current_Z": 0.1, "Forecast_Avg_Z": 0.2, "Z_Delta": 0.1},
        {"Current_Z": 0.0, "Forecast_Avg_Z": 0.15, "Z_Delta": 0.15},
        {"Current_Z": 0.4, "Forecast_Avg_Z": 0.5, "Z_Delta": 0.1},
        {"Current_Z": -0.1, "Forecast_Avg_Z": 0.0, "Z_Delta": 0.1},
    ])
    df_category = aggregate_to_category_level({"Paper": paper_mr, "Social": social_mr})
    overall = aggregate_to_overall_level(df_category)

    paper_z = df_category[df_category["Stream"] == "Paper"]["Z_Delta"].iloc[0]
    social_z = df_category[df_category["Stream"] == "Social"]["Z_Delta"].iloc[0]
    naive_flat_mean = pd.concat([paper_mr["Z_Delta"], social_mr["Z_Delta"]]).mean()

    assert overall["Z_Delta"] == pytest.approx((paper_z + social_z) / 2)
    # ถ้า equal-weight ไม่ทำงาน overall จะเลื่อนเข้าใกล้ naive_flat_mean (เอนเอียงไปทาง Social ที่มี
    # 5 กลุ่มเทียบ Paper แค่ 2) - ยืนยันว่าทั้งสองค่าต่างกันจริง ไม่ใช่บังเอิญเท่ากัน
    assert overall["Z_Delta"] != pytest.approx(naive_flat_mean)


def test_aggregate_overall_level_empty_input_returns_empty_dict():
    assert aggregate_to_overall_level(pd.DataFrame()) == {}
    assert aggregate_to_overall_level(None) == {}


# ---------------------------------------------------------------------------
# compute_rank_score() / normalize_cluster_size()
# ---------------------------------------------------------------------------

def test_normalize_cluster_size_basic():
    assert normalize_cluster_size(10, [10, 5, 2]) == 1.0
    assert normalize_cluster_size(5, [10, 5, 2]) == 0.5
    assert normalize_cluster_size(10, []) == 0.0


def test_compute_rank_score_uses_growth_without_stream_bonus():
    """🆕 (2026-09-30) โหมด final = คะแนนการเติบโตปีที่ 1 ตรงๆ ไม่มีโบนัสจำนวนสาย - ถ้าคูณโบนัส เทรนด์ที่โตช้ากว่าตลาด
    (ต่ำกว่า 0.5) แต่เจอหลายสายจะขึ้นไปอยู่เหนือเทรนด์ที่โตเร็วกว่า ลำดับจะขัดกับเส้นแบ่งค่ากลางตลาดในรายงาน"""
    single = compute_rank_score(10, [10, 5], stream_count=1, growth=0.48)
    confirmed = compute_rank_score(10, [10, 5], stream_count=3, growth=0.48)
    assert single["score"] == confirmed["score"] == 0.48
    assert single["mode"].startswith("final")


def test_compute_rank_score_preliminary_mode_when_no_growth():
    result = compute_rank_score(10, [10, 5], stream_count=2, growth=None)
    assert result["mode"].startswith("preliminary")
    assert result["score"] == pytest.approx(1.0 * 1.2)  # normalized_size=1.0 * bonus (1+0.2*(2-1))


def test_rank_trends_final_before_preliminary_and_ties_broken_by_streams():
    from rank_trends import RANK_YEAR, rank_trends_across_streams

    trends = {"Paper": pd.DataFrame({"Trend Name": ["A", "B", "D"], "Cluster Size": [10, 5, 7]}),
              "Social": pd.DataFrame({"Trend Name": ["C"], "Cluster Size": [8]})}
    keywords = {"Paper": pd.DataFrame({"Trend Name": ["A", "B", "D"], "Search_Keywords": ["x, y", "z", "w"]}),
                "Social": pd.DataFrame({"Trend Name": ["C"], "Search_Keywords": ["x"]})}
    # 🆕 (2026-10-02) Rank Score = คะแนนปีระยะสั้น (rank_trends.RANK_YEAR = common/horizons.SHORT_YEAR; 2026-10-19 ปีที่ 3) - คอลัมน์ Growth_Y1..Y5
    ry = RANK_YEAR
    growth = {("Paper", "A"): {f"score_y{ry}": 0.6, "score_y5": 0.7, f"grade_y{ry}": 3, "past_growth_pct": 12.0},
              ("Social", "C"): {f"score_y{ry}": 0.6, "score_y5": 0.2},
              ("Paper", "D"): {f"score_y{ry}": 0.61, "score_y1": 0.1}}
    df = rank_trends_across_streams(trends, keywords, growth_lookup=growth)
    # D คะแนนสูงสุดแม้เจอสายเดียว (ไม่มีโบนัส) / A กับ C เท่ากันและเจอ 2 สายทั้งคู่ -> เรียงตามชื่อ / B ไม่มีคะแนน -> ท้ายสุด
    assert list(df["Trend Name"]) == ["D", "A", "C", "B"]
    assert list(df["Overall Rank"]) == [1, 2, 3, 4]
    assert "Z_Delta" not in df.columns                    # 🆕 2026-09-30 เอาออกจากไฟล์อันดับแล้ว
    a = df[df["Trend Name"] == "A"].iloc[0]
    assert a["Growth_Y5"] == 0.7 and a[f"Grade_Y{ry}"] == 3 and a["Past_Growth_Pct"] == 12.0 and "Growth_Y4" in df.columns
    assert a["Stream_Count"] == 2 and df.iloc[-1]["Mode"].startswith("preliminary")


def test_rerank_rows_equals_a_fresh_ranking_for_any_year(monkeypatch):
    """🆕 (2026-10-19) จัดอันดับใหม่จากแถวที่บันทึกไว้ (ไม่ฝึกโมเดลซ้ำ) ต้องได้ผลเดียวกับ rank_trends_across_streams ของปีนั้นทุกประการ -
    ใช้ปรับรอบที่รันไปแล้วเมื่อเปลี่ยนปีระยะสั้น (common/horizons.py)"""
    import rank_trends as rt

    trends = {"Paper": pd.DataFrame({"Trend Name": ["A", "B", "D"], "Cluster Size": [10, 5, 7]}),
              "Social": pd.DataFrame({"Trend Name": ["C"], "Cluster Size": [8]})}
    keywords = {"Paper": pd.DataFrame({"Trend Name": ["A", "B", "D"], "Search_Keywords": ["x, y", "z", "w"]}),
                "Social": pd.DataFrame({"Trend Name": ["C"], "Search_Keywords": ["x"]})}
    growth = {("Paper", "A"): {"score_y2": 0.6, "score_y3": 0.3, "score_y5": 0.7},
              ("Social", "C"): {"score_y2": 0.6, "score_y3": 0.9, "score_y5": 0.2},
              ("Paper", "D"): {"score_y2": 0.61, "score_y3": 0.3, "score_y5": 0.4}}
    cols = ["Trend Name", "Overall Rank", "Rank Score", "Mode"]
    fresh = {}
    for year in (2, 3, 5):
        monkeypatch.setattr(rt, "RANK_YEAR", year)
        fresh[year] = rt.rank_trends_across_streams(trends, keywords, growth_lookup=growth)
    for year in (2, 3, 5):
        rows = fresh[3].to_dict("records")                                       # เริ่มจากอันดับที่จัดด้วยปีที่ 3
        again = pd.DataFrame(rt.rerank_rows(rows, year))
        assert again[cols].to_dict("records") == fresh[year][cols].to_dict("records"), year
    assert list(fresh[3]["Trend Name"]) != list(fresh[2]["Trend Name"])         # เปลี่ยนปีแล้วอันดับเปลี่ยนจริง (ข้อมูลทดสอบสร้างให้ต่าง)
    assert fresh[3].iloc[-1]["Mode"].startswith("preliminary")                  # เทรนด์ไม่มีคะแนนยังอยู่ท้ายสุด
    original = fresh[3].to_dict("records")
    before = [(r["Trend Name"], r["Overall Rank"], r["Rank Score"]) for r in original]
    rt.rerank_rows(original, 5)                                                 # ไม่แก้ rows เดิม - คืนสำเนาใหม่
    assert [(r["Trend Name"], r["Overall Rank"], r["Rank Score"]) for r in original] == before


def test_short_and_long_year_come_from_one_place():
    """🆕 (2026-10-19) ระยะสั้น/ระยะยาวเดิมฝังแยก 5 ที่ให้ "ตรงกัน" ด้วยคอมเมนต์ - ตอนนี้ทุกโมดูลต้องอ่านจาก common/horizons.py"""
    import rank_trends as rt
    from common import bootstrap, horizons, market_overview as mo
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase6_pdf_report"))
    import brand_data
    import report_data
    assert (horizons.SHORT_YEAR, horizons.LONG_YEAR) == (3, 5)
    assert horizons.SHORT_RANGE == "1-3" and horizons.LONG_RANGE == "4-5"
    assert bootstrap.SHORT_YEAR == report_data.SHORT_YEAR == rt.RANK_YEAR == mo.SHORT_YEAR == horizons.SHORT_YEAR
    assert bootstrap.LONG_YEAR == report_data.LONG_YEAR == mo.LONG_YEAR == horizons.LONG_YEAR
    assert mo.SHORT_KEY == "year_3" and brand_data.SHORT_IDX == horizons.SHORT_YEAR - 1
    assert report_data.YEARS == rt.GROWTH_YEARS == horizons.YEARS
    assert horizons.apply_tokens({"a": ["@S@ @SR@ @LR@", ("x @L@",)]}) == {"a": ["3 1-3 4-5", ("x 5",)]}


# ---------------------------------------------------------------------------
# growth_score.py - คะแนนการเติบโตที่ใช้จัดอันดับแทน Z_Delta (🆕 2026-09-30)
# ---------------------------------------------------------------------------
import numpy as np  # noqa: E402

import growth_score as gs  # noqa: E402


def _series(values, start="2004-01-01"):
    return pd.Series(np.asarray(values, dtype=float), index=pd.date_range(start, periods=len(values), freq="MS"))


def test_pit_scale_makes_past_peak_100_and_keeps_latest_month():
    """🆕 (2026-10-02) ตัวอย่างฝึกปรับสเกล ณ เดือนนั้น: ค่าสูงสุดถึงเดือน i = 100 / เดือนล่าสุดไม่เปลี่ยน (ค่าสูงสุดถึงวันนี้ = 100)"""
    raw = np.array([5.0, 10.0, 20.0, 100.0, 50.0])
    assert list(gs.pit_scale(raw, 1)[:2]) == [50.0, 100.0]          # ณ เดือน 1 ค่าสูงสุดคือ 10 -> 100
    assert list(gs.pit_scale(raw, 4)) == list(raw)                 # ค่าสูงสุดถึงเดือนสุดท้าย = 100 อยู่แล้ว
    assert list(gs.pit_scale(np.zeros(3), 2)) == [0.0, 0.0, 0.0]
    # เจ้าของงานเลือก (2026-10-02) ยังไม่เปิดจนกว่าจะดึงข้อมูล cat=143 - เปิดแล้วต้องคำนวณ FORECAST_BAND_80 ใหม่
    assert gs.PIT_SCALING is False


def test_new_yoy_and_acceleration_features():
    values = np.array([10.0] * 12 + [20.0] * 12 + [40.0] * 12)       # เดือน 35 = ล่าสุด
    f = gs.features_at(values, 35)
    assert f["yoy_3m"] == pytest.approx(np.log(41 / 21)) and f["yoy_6m"] == pytest.approx(np.log(41 / 21))
    # การโตปีล่าสุด log(41/21) ลบการโตปีก่อน log(21/11)
    assert f["accel_12m"] == pytest.approx(np.log(41 / 21) - np.log(21 / 11))
    assert np.isnan(gs.features_at(values, 30)["accel_12m"])          # ประวัติไม่ถึง 36 เดือน
    assert all(c in gs.MODEL_FEATURES[h] for h in gs.HORIZONS for c in ("yoy_3m", "yoy_6m", "accel_12m"))


def test_growth_features_do_not_look_ahead():
    rng = np.random.default_rng(0)
    values = rng.integers(5, 60, 120).astype(float)
    changed = values.copy()
    changed[80:] = 99  # เปลี่ยนเฉพาะอนาคตหลังเดือน 79
    a, b = gs.features_at(values, 79), gs.features_at(changed, 79)
    assert a == b
    assert np.isnan(gs.features_at(values, 40)["years_up_of_5"])       # ประวัติไม่ถึง 6 ปี
    assert not np.isnan(gs.features_at(values, 79)["years_up_of_5"])


def test_growth_targets_are_yearly_means_vs_last_12_months():
    values = np.array([10.0] * 24 + [20.0] * 12 + [30.0] * 12)       # เดือน 23 = ล่าสุด
    t = gs.targets_at(values, 23)
    assert t["t_y1"] == pytest.approx(np.log(21 / 11)) and t["t_y2"] == pytest.approx(np.log(31 / 11))
    assert np.isnan(t["t_y3"])                                        # ข้อมูลยังไม่ถึงปีที่ 3
    assert gs.has_enough_data(values, 23) and not gs.has_enough_data(np.zeros(30), 29)


def test_growth_grade_thresholds():
    assert [gs.grade(s) for s in (1.0, 0.8, 0.79, 0.5, 0.49, 0.2, 0.19, 0.0, None)] == [4, 4, 3, 3, 2, 2, 1, 1, None]


def test_blend_scores_are_market_percentiles_and_skip_thin_keywords():
    kw = pd.DataFrame({"keyword": list("abcde"), "thin": [False, False, False, False, True],
                       "momentum": [0.3, 0.1, 0.2, -0.1, None], "pred_y1": [0.2, 0.0, 0.1, -0.2, None],
                       "pred_y2": [0.2, 0.0, 0.1, -0.2, None], "pred_y3": [-0.3, 0.0, 0.1, 0.4, None],
                       "pred_y4": [0.2, 0.0, 0.1, -0.2, None], "pred_y5": [0.2, 0.0, 0.1, -0.2, None]})
    blend = gs.blend_scores(kw, use_momentum=True)
    assert list(blend["score_y1"][:4]) == [1.0, 0.5, 0.75, 0.25]     # ดีที่สุดทั้ง 2 อย่าง = 1.0
    assert np.isnan(blend["score_y1"].iloc[4])                        # ข้อมูลบาง ไม่มีคะแนน
    assert blend["score_y3"].iloc[0] < blend["score_y1"].iloc[0]      # ปีที่ 3 โมเดลทายต่ำสุด -> คะแนนลดลง
    # 🆕 (2026-09-30) ค่าเริ่มต้นตอนนี้ = โมเดลอย่างเดียว (momentum เพี้ยนจากข้อมูล cat=0 ที่กระโดด)
    assert gs.BLEND_MOMENTUM is False
    model = gs.blend_scores(kw)
    assert list(model["score_y3"][:4]) == [0.25, 0.5, 0.75, 1.0]     # อันดับตามค่าที่ทายปีที่ 3 ล้วน ไม่สน momentum


def test_aggregate_clusters_scores_index_growth_and_decline_flag():
    kw = pd.DataFrame({"keyword": ["a", "b", "c", "d"], "thin": [False, False, False, True],
                       "score_y1": [0.9, 0.7, 0.2, None], "score_y2": [0.5, 0.5, 0.5, None],
                       "score_y3": [0.1, 0.3, 0.8, None], "score_y4": [0.5] * 3 + [None], "score_y5": [0.5] * 3 + [None],
                       "last12_mean": [20, 40, 30, 3], "prev12_mean": [10, 30, 20, 1],
                       "recent_mean": [8, 16, 26, 5], "year_ago_mean": [10, 20, 20, 10]})
    mapping = pd.DataFrame({"Keyword": ["a", "b", "c", "d"], "cluster_name": ["T1", "T1", "T2", "T2"]})
    t1, t2 = gs.aggregate_clusters(kw, mapping)
    assert t1["trend"] == "T1" and t1["score_y1"] == 0.8 and t1["grade_y1"] == 4 and t1["n_scored"] == 2
    # ดัชนีเทรนด์ = ค่าเฉลี่ยคีย์เวิร์ด: 12 เดือนล่าสุด 30 เทียบ 20 -> (30+1)/(20+1) = +47.6% (ตรงกับกราฟในรายงาน)
    assert t1["past_growth_pct"] == pytest.approx(47.6, abs=0.1)
    assert t1["recent_decline"] and t1["recent_change_pct"] == pytest.approx(-18.8, abs=0.1)   # 12 เทียบ 15
    assert t2["n_keywords"] == 2 and t2["n_scored"] == 1 and t2["score_y3"] == 0.8
    # คีย์เวิร์ดข้อมูลบาง (d ลดลงครึ่งหนึ่ง) ไม่นับ - เหลือแค่ c ที่ขึ้น (26+1)/(20+1)
    assert not t2["recent_decline"] and t2["recent_change_pct"] == pytest.approx(28.6, abs=0.1)


def test_model_only_trend_score_follows_expected_growth():
    """🆕 (2026-09-30) โหมดโมเดลอย่างเดียว: คะแนนเทรนด์ = percentile ของ % ที่คาดของเทรนด์เทียบค่าที่ทายของทุกคีย์เวิร์ด
    - เทรนด์ที่คาดโตมากกว่าต้องได้ระดับเท่ากันหรือสูงกว่าเสมอ (ไม่มี "ช้ากว่าตลาด" ที่คาด % สูงกว่า "เร็วกว่าตลาด")"""
    preds = [0.02, 0.05, 0.08, 0.30, 0.00, 0.10]
    kw = pd.DataFrame({"keyword": list("abcdef"), "thin": [False] * 6, "last12_mean": [20, 20, 20, 20, 50, 50],
                       **{f"pred_y{h}": preds for h in gs.HORIZONS}})
    kw = gs.blend_scores(kw)
    mapping = pd.DataFrame({"Keyword": list("abcdef"), "cluster_name": ["T1", "T1", "T2", "T2", "T3", "T3"]})
    by = {c["trend"]: c for c in gs.aggregate_clusters(kw, mapping)}
    order_pct = sorted(by, key=lambda t: by[t]["forecast"]["change_pct"][0])
    order_score = sorted(by, key=lambda t: by[t]["score_y1"])
    assert order_pct == order_score
    # T2 คาดโตราว +20% สูงกว่าค่าที่ทายของ 5 ใน 6 คำ -> percentile ประมาณ 0.83 = ระดับ 4
    assert by["T2"]["grade_y1"] == 4 and 0.8 <= by["T2"]["score_y1"] <= 0.85


def test_expected_levels_are_mean_index_with_backtest_band():
    ok = pd.DataFrame({"last12_mean": [9.0, 29.0], "pred_y1": [np.log(1.1)] * 2, "pred_y2": [0.0] * 2,
                       "pred_y3": [np.log(0.8)] * 2, "pred_y4": [np.log(1.5)] * 2, "pred_y5": [np.log(2.0)] * 2})
    fc = gs.expected_levels(ok)
    # ดัชนีปัจจุบัน 19 -> ปีที่ 1 (10x1.1-1 + 30x1.1-1)/2 = 21 (+10%), ปีที่ 2 เท่าเดิม, ปีที่ 3 = 15 (-20%), 4 = 29, 5 = 39
    assert fc["base"] == 19.0 and fc["levels"] == [21.0, 19.0, 15.0, 29.0, 39.0]
    assert fc["change_pct"] == [10.0, 0.0, -20.0, 50.0, 100.0]
    lo, hi = gs.FORECAST_BAND_80[1]
    assert fc["low"][0] == round(22 * (1 + lo) - 1, 2) and fc["high"][0] == round(22 * (1 + hi) - 1, 2)
    assert gs.expected_levels(ok.drop(columns="pred_y3")) is None and gs.expected_levels(ok.iloc[:0]) is None


def test_seasonal_factors_skip_the_jump_and_keep_yearly_mean():
    # เดือน ม.ค.-มิ.ย. สูง (15) ก.ค.-ธ.ค. ต่ำ (5) ทุกปี แล้วหลัง มิ.ย. 2025 กระโดดเป็น 100 (ต้องไม่ถูกนับเป็นฤดูกาล)
    idx = pd.date_range("2019-07-01", "2026-08-01", freq="MS")
    values = [100.0 if d > pd.Timestamp("2025-06-01") else (15.0 if d.month <= 6 else 5.0) for d in idx]
    f = gs.seasonal_factors(pd.Series(values, index=idx))
    assert f[0] == pytest.approx(1.5) and f[11] == pytest.approx(0.5) and sum(f) == pytest.approx(12)
    path = gs.monthly_path({"levels": [20.0, 22.0, 24.0]}, f, pd.Timestamp("2026-08-01"))
    assert path["months"][0] == "2026-09" and len(path["values"]) == 36
    assert np.mean(path["values"][:12]) == pytest.approx(20.0)                 # ค่าเฉลี่ยปีเท่ากับระดับรายปีพอดี
    assert path["values"][4] == pytest.approx(30.0) and path["values"][0] == pytest.approx(10.0)   # ม.ค. สูง ก.ย. ต่ำ
    assert gs.monthly_path({"levels": [20.0, 22.0, 24.0]}, None, pd.Timestamp("2026-08-01"))["values"][0] == 20.0


def test_cluster_history_is_mean_of_scored_keywords():
    series = {"a": _series([10] * 70), "b": _series([30] * 70), "c": _series([0] * 70)}
    kw = pd.DataFrame({"keyword": ["a", "b", "c"], "thin": [False, False, True]})
    mapping = pd.DataFrame({"Keyword": ["a", "b", "c"], "cluster_name": ["T", "T", "U"]})
    hist = gs.cluster_history(series, kw, mapping, months=60)
    assert len(hist["T"]["values"]) == 60 and set(hist["T"]["values"]) == {20.0}   # ไม่รวมคำข้อมูลบาง
    assert hist["T"]["months"][-1] == "2009-10" and hist["U"]["values"][0] == 0.0  # เทรนด์ที่มีแต่คำบาง ใช้ทุกคำ


def _synthetic_run(tmp_path, n_keywords=24):
    """ผล ⑦ ปลอม: คีย์เวิร์ด 24 คำ 3 คลัสเตอร์ ข้อมูลรายเดือน 2004-01..2026-08 (โตคนละอัตรา + ฤดูกาล)"""
    months = pd.date_range("2004-01-01", "2026-08-01", freq="MS")
    rng = np.random.default_rng(1)
    rows, mapping = [], []
    for k in range(n_keywords):
        trend = 0.002 * (k % 6 - 2)
        level = 30 * np.exp(trend * np.arange(len(months))) * (1 + 0.15 * np.sin(np.arange(len(months)) / 12 * 2 * np.pi))
        values = np.clip(level + rng.normal(0, 3, len(months)), 0, 100).round()
        rows += [{"Keyword": f"kw{k}", "start_date": d, "search_avg": v} for d, v in zip(months, values)]
        mapping.append({"Keyword": f"kw{k}", "cluster_name": f"Trend {k % 3}"})
    pd.DataFrame(rows).to_excel(tmp_path / gs.MONTHLY_FILE, index=False)
    pd.DataFrame(mapping).to_excel(tmp_path / gs.KEYWORD_MAP_FILE, index=False)
    return tmp_path


def test_train_models_only_uses_outcomes_before_last_trusted_month(tmp_path):
    series, _ = gs.load_monthly(_synthetic_run(tmp_path, n_keywords=6))
    samples = gs.build_samples(series)
    _, n_early = gs.train_models(samples, pd.Timestamp("2015-06-01"))
    _, n_late = gs.train_models(samples, pd.Timestamp("2025-06-01"))
    last = 2015 * 12 + 5
    assert n_early[1] == int(((samples["month"] + 12 <= last) & samples["t_y1"].notna()).sum())
    assert n_early[3] < n_early[1] < n_late[1]


def test_compute_growth_scores_end_to_end(tmp_path):
    result = gs.compute_growth_scores(_synthetic_run(tmp_path))
    assert result["as_of"] == "2026-08" and result["method"]["last_trusted_month"] == "2025-06"
    assert result["method"]["forecast_band_80"]["5"] == list(gs.FORECAST_BAND_80[5])
    assert result["method"]["score_method"] == "model only"
    clusters = {c["trend"]: c for c in result["clusters"]}
    assert sorted(clusters) == ["Trend 0", "Trend 1", "Trend 2"]
    for c in clusters.values():
        assert 0 <= c["score_y1"] <= 1 and c["grade_y1"] in (1, 2, 3, 4) and c["n_scored"] == 8
        assert len(c["history"]["values"]) == gs.HISTORY_MONTHS and c["history"]["months"][-1] == "2026-08"
        assert len(c["forecast"]["monthly"]["values"]) == 60 and len(c["history"]["seasonal"]) == 12
        assert len(c["forecast"]["levels"]) == 5 and all(lo <= v <= hi for lo, v, hi in
                                                          zip(c["forecast"]["low"], c["forecast"]["levels"], c["forecast"]["high"]))
    assert len(result["keywords"]) == 24 and all(0 <= k["score_y1"] <= 1 for k in result["keywords"])
    path = gs.save_growth_scores(result, tmp_path)
    assert path.name == gs.OUTPUT_FILE and path.exists()


# ---------------------------------------------------------------------------
# evidence_in_document() - 🆕 (2026-09-15, audit M3 ฉบับเต็ม)
# ---------------------------------------------------------------------------

def test_evidence_in_document_exact_quote_passes():
    doc = "Niacinamide at 5% reduced transepidermal water loss after four weeks of use."
    assert evidence_in_document("reduced transepidermal water loss after four weeks", doc)


def test_evidence_in_document_ignores_case_whitespace_and_quote_style():
    doc = 'Users said the serum felt   "light"\nand non-greasy on oily skin.'
    assert evidence_in_document("The serum felt “light” and non-greasy", doc)


def test_evidence_in_document_thai_quote_matches_thai_source():
    """ต้นเหตุที่ต้องเปลี่ยนวิธี: ตัวเช็คเดิมเทียบคำอังกฤษกับเอกสารไทยไม่ได้เลย สาย Social จึงพัง"""
    doc = "ใช้กันแดดตัวนี้มาสองเดือน เนื้อบางเบาไม่เหนียวเหนอะหนะเลย เหมาะกับหน้ามัน"
    assert evidence_in_document("เนื้อบางเบาไม่เหนียวเหนอะหนะเลย", doc)


def test_evidence_in_document_paraphrase_fails():
    doc = "Niacinamide at 5% reduced transepidermal water loss after four weeks of use."
    assert not evidence_in_document("niacinamide improves skin barrier hydration", doc)


def test_evidence_in_document_translated_quote_fails_against_thai_source():
    doc = "ใช้กันแดดตัวนี้มาสองเดือน เนื้อบางเบาไม่เหนียวเหนอะหนะเลย"
    assert not evidence_in_document("the texture is light and not sticky at all", doc)


def test_evidence_in_document_ellipsis_fragments_must_all_exist():
    doc = "Retinol causes irritation in many users. Encapsulation in dendrimers improved tolerability."
    assert evidence_in_document("Retinol causes irritation ... improved tolerability", doc)
    assert not evidence_in_document("Retinol causes irritation ... cured acne completely", doc)


def test_evidence_in_document_too_short_or_empty_fails():
    doc = "Retinol is widely used in anti-aging products."
    assert not evidence_in_document("retinol", doc)
    assert not evidence_in_document("", doc)


# ---------------------------------------------------------------------------
# _BedrockClientShim เรียกซ้ำ/ตัวสำรอง - 🆕 (2026-09-15) ใช้ client ปลอม ไม่ยิง AWS จริง
# ---------------------------------------------------------------------------

class _FakeConverseClient:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return {"output": {"message": {"content": [{"text": outcome}]}}, "stopReason": "end_turn",
                "usage": {"inputTokens": 1, "outputTokens": 1}}


_JSON = {"type": "json_object"}


def _call(client, response_format=None, max_tokens=100):
    shim = _BedrockClientShim(client, "zai.glm-5", "openai.gpt-oss-120b-1:0")
    return shim.chat.completions.create(messages=[{"role": "user", "content": "hi"}],
                                        max_tokens=max_tokens, response_format=response_format)


def _models(client):
    return [c["modelId"] for c in client.calls]


def test_bedrock_shim_retries_same_model_once_on_garbage_json():
    client = _FakeConverseClient(["This is and (2 11/z)a", '{"ok": 1}'])
    assert _call(client, _JSON).choices[0].message.content == '{"ok": 1}'
    assert _models(client) == ["zai.glm-5", "zai.glm-5"]


def test_bedrock_shim_uses_fallback_after_two_bad_json():
    client = _FakeConverseClient(["garbage", "more garbage", '{"ok": 1}'])
    assert _call(client, _JSON).choices[0].message.content == '{"ok": 1}'
    assert _models(client) == ["zai.glm-5", "zai.glm-5", "openai.gpt-oss-120b-1:0"]


def test_bedrock_shim_api_error_goes_straight_to_fallback():
    client = _FakeConverseClient([RuntimeError("ServiceUnavailableException"), '{"ok": 1}'])
    assert _call(client, _JSON).choices[0].message.content == '{"ok": 1}'
    assert _models(client) == ["zai.glm-5", "openai.gpt-oss-120b-1:0"]


def test_bedrock_shim_plain_text_call_is_not_retried():
    client = _FakeConverseClient(["# Report\nnot JSON and that is fine"])
    _call(client)
    assert _models(client) == ["zai.glm-5"]


def test_bedrock_shim_reasoning_fallback_gets_token_allowance_and_low_effort():
    """gpt-oss คิดก่อนตอบ - ทดสอบจริงแล้วว่า max_tokens=30 หมดตอนคิดจนไม่มีข้อความตอบเลย"""
    client = _FakeConverseClient(["", "Ceramide Care for Calm Skin"])
    assert _call(client, max_tokens=30).choices[0].message.content == "Ceramide Care for Calm Skin"
    primary, fallback = client.calls
    assert primary["inferenceConfig"]["maxTokens"] == 30
    assert "additionalModelRequestFields" not in primary
    assert fallback["inferenceConfig"]["maxTokens"] == 30 + 1024
    assert fallback["additionalModelRequestFields"] == {"reasoning_effort": "low"}


def test_bedrock_shim_returns_last_result_when_all_attempts_fail():
    client = _FakeConverseClient(["bad", "bad", "still bad"])
    assert _call(client, _JSON).choices[0].message.content == "still bad"


def test_bedrock_shim_raises_when_every_attempt_errors():
    client = _FakeConverseClient([RuntimeError("down"), RuntimeError("also down")])
    with pytest.raises(RuntimeError, match="also down"):
        _call(client, _JSON)


# ---------------------------------------------------------------------------
# ตัวช่วยเก็บข้อมูลสาย Social - 🆕 (2026-09-15) แก้ต้นเหตุคำหลอนฝั่งข้อมูล
# ---------------------------------------------------------------------------

def test_clean_pantip_query_removes_site_name():
    """LLM ชอบเติม "pantip" ในคำค้น ทำให้ค้นในเว็บ Pantip ไม่เจอกระทู้เลย"""
    assert clean_pantip_query("ผมร่วง ศีรษะล้าน pantip") == "ผมร่วง ศีรษะล้าน"
    assert clean_pantip_query("Pantip รีวิวกันแดด") == "รีวิวกันแดด"
    assert clean_pantip_query("กันแดด พันทิป") == "กันแดด"
    assert clean_pantip_query("pantip") == ""


_PANTIP_PAGE = """menu
search
เข้าสู่ระบบ / สมัครสมาชิก
ผลการค้นหา
เรียงตาม
รูปแบบการแสดง:
เคยใช้มอยซ์เซราวีโลชั่นแล้วเป็นสิวอุดตัน เปลี่ยนเป็นใช้อะไรดี
คห.1 ลาโรช B 5 มีสารแอคทีฟที่ดีก็จริง
tune
ตัวกรองค้นหา
checkboxก้นครัว
© 2026 Internet Marketing co., ltd"""


def test_extract_search_results_text_keeps_only_thread_list():
    text = extract_search_results_text(_PANTIP_PAGE)
    assert text.startswith("เคยใช้มอยซ์เซราวีโลชั่น")
    assert text.endswith("มีสารแอคทีฟที่ดีก็จริง")
    assert "checkbox" not in text and "เข้าสู่ระบบ" not in text


def test_extract_search_results_text_returns_original_when_layout_changes():
    assert extract_search_results_text("เนื้อหาอย่างเดียว ไม่มีตัวคั่น") == "เนื้อหาอย่างเดียว ไม่มีตัวคั่น"


def _comment(body, score=1, author="user", replies=None):
    data = {"body": body, "score": score, "author": author,
            "replies": {"data": {"children": replies}} if replies else ""}
    return {"kind": "t1", "data": data}


def test_format_comment_tree_includes_replies_under_category_comments():
    """กระทู้โหวต Holy Grail จริง: คอมเมนต์ระดับบนเป็นแค่ชื่อหมวด ชื่อสินค้าอยู่ใน reply"""
    children = [_comment("SUNSCREEN THAT WORKS WELL UNDER MAKEUP:", 38,
                         replies=[_comment("beauty of joseon aqua", 61), _comment("Skin 1004 hylu cica", 40)])]
    text = format_comment_tree(children)
    assert "- (38) SUNSCREEN THAT WORKS WELL UNDER MAKEUP:" in text
    assert "  - (61) beauty of joseon aqua" in text


def test_format_comment_tree_skips_more_automod_and_deleted():
    children = [_comment("rules reminder", author="AutoModerator"), _comment("[deleted]"),
                {"kind": "more", "data": {}}, _comment("CeraVe PM lotion", 12)]
    assert format_comment_tree(children) == "- (12) CeraVe PM lotion"


def test_format_comment_tree_respects_char_budget():
    children = [_comment("x" * 200, i) for i in range(10)]
    text = format_comment_tree(children, max_chars=500)
    assert 1 <= text.count("- (") < 10
    assert len(text) - text.count("\n") <= 500


# ---------------------------------------------------------------------------
# verify_report_against_source() - 🆕 (2026-09-16) คำขึ้นต้นประโยคติดไปกับชื่อจริง
# ---------------------------------------------------------------------------

_PUIG_SOURCE = [{"title": "Puig Takes Full Ownership of ISDIN", "content": "Puig completed the deal."}]


def test_verify_report_strips_sentence_starter_before_real_name():
    """เจอจริงในรอบรัน News: "While Puig" โดนฟ้องว่าหลอนทั้งที่ Puig มีในต้นทาง"""
    report = "While Puig expanded its dermatology portfolio, the deal closed quickly."
    assert "While Puig" not in verify_report_against_source(report, _PUIG_SOURCE)["asserted"]


def test_verify_report_still_flags_absent_name_after_sentence_starter():
    report = "While Glossier expanded into pharmacies, margins improved."
    assert "While Glossier" in verify_report_against_source(report, _PUIG_SOURCE)["asserted"]


def test_verify_report_does_not_strip_the_from_brand_names():
    """ไม่ตัด "The" เพราะมีแบรนด์จริงที่ขึ้นต้นด้วย The - ถ้าไม่มีในต้นทางต้องยังโดนฟ้อง"""
    source = [{"title": "Serum review", "content": "An ordinary niacinamide serum was reviewed."}]
    report = "Consumers compared it with The Ordinary serum line."
    assert "The Ordinary" in verify_report_against_source(report, source)["asserted"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# ---------------------------------------------------------------------------
# use_bedrock(module=...) - 🆕 (2026-09-16) แพตช์ trend_final_v2 ได้ (Step 6-7 ใน forecast_trend() เคยยิง
# OpenRouter 402 เพราะ use_bedrock() เดิมแพตช์แค่ trend_final v1)
# ---------------------------------------------------------------------------

def test_use_bedrock_patches_given_module_and_restores_it(monkeypatch):
    import types

    import boto3
    from common.bootstrap import tf, use_bedrock

    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "ABSK-test")
    monkeypatch.setattr(boto3, "client", lambda *a, **k: _FakeConverseClient([]))
    target = types.SimpleNamespace(__name__="fake_tf2", client="openrouter", MODEL_NAME="old",
                                   MODEL_NAME_META="old-meta")
    v1_client = tf.client

    with use_bedrock(module=target):
        assert isinstance(target.client, _BedrockClientShim)
        assert target.MODEL_NAME == target.MODEL_NAME_META == use_bedrock.MODEL_ID
        assert tf.client is v1_client
    assert (target.client, target.MODEL_NAME, target.MODEL_NAME_META) == ("openrouter", "old", "old-meta")


# ---------------------------------------------------------------------------
# Top N เทรนด์หลังพยากรณ์ - 🆕 (2026-09-16) ⑪ ⑫ ⑬ รายงาน และ notebook ใช้ชุดเดียวกันจาก Rank Score ของ ⑥
# ---------------------------------------------------------------------------

def test_get_top_n_trends_default_env_and_bad_values(monkeypatch):
    from common.bootstrap import TOP_N_TRENDS_DEFAULT, get_top_n_trends

    monkeypatch.delenv("TREND_TOP_N", raising=False)
    assert get_top_n_trends() == TOP_N_TRENDS_DEFAULT == 10
    monkeypatch.setenv("TREND_TOP_N", "7")
    assert get_top_n_trends() == 7
    for bad in ("0", "-3", "abc"):
        monkeypatch.setenv("TREND_TOP_N", bad)
        assert get_top_n_trends() == 10


def _write_rank_file(tmp_path, n=15):
    import json

    # เขียนกลับลำดับ (15 -> 1) ให้ฟังก์ชันต้องเรียงตาม Overall Rank เอง ไม่พึ่งลำดับในไฟล์
    rows = [{"Overall Rank": i, "Stream": ["Paper", "Social", "News"][i % 3], "Trend Name": f"T{i}",
             "Rank Score": round(1.6 - i * 0.1, 2), "Mode": "final (Z_Delta)", "Z_Delta": round(1.6 - i * 0.1, 2)}
            for i in range(n, 0, -1)]
    path = tmp_path / "phase2_rank_score_final_mode_result.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def test_select_top_trends_takes_first_n_by_overall_rank(tmp_path):
    from common.bootstrap import select_top_trends

    picked = select_top_trends(n=10, rank_path=_write_rank_file(tmp_path))
    assert [p["overall_rank"] for p in picked] == list(range(1, 11))
    assert picked[0]["trend"] == "T1" and picked[0]["stream"] == "Social"


def test_select_top_trends_n_larger_than_available_returns_all(tmp_path):
    from common.bootstrap import select_top_trends

    assert len(select_top_trends(n=20, rank_path=_write_rank_file(tmp_path, n=15))) == 15


def test_select_top_trends_missing_rank_file_stops_instead_of_using_everything(tmp_path):
    from common.bootstrap import select_top_trends

    with pytest.raises(SystemExit):
        select_top_trends(n=10, rank_path=tmp_path / "missing.json")


def _ranked(n=15):
    return [{"overall_rank": i, "stream": "News", "trend": f"T{i}"} for i in range(1, n + 1)]


def test_collect_top_n_skips_no_data_trend_and_promotes_next_rank():
    from common.bootstrap import collect_top_n_with_matchable_data

    calls = []

    def make_profile(item):
        calls.append(item["overall_rank"])
        return {"trend": item["trend"], "has_data": item["overall_rank"] != 4}

    selected, profiles, excluded, failed = collect_top_n_with_matchable_data(
        _ranked(), make_profile, lambda p: None if p["has_data"] else "ช่องทาง/พฤติกรรมการซื้อ", 10)
    assert [s["overall_rank"] for s in selected] == [1, 2, 3, 5, 6, 7, 8, 9, 10, 11]
    assert [x["overall_rank"] for x in excluded] == [4] and not failed
    assert excluded[0]["reason"] == "ช่องทาง/พฤติกรรมการซื้อ"
    assert len(profiles) == 10
    assert calls == list(range(1, 12))  # หยุดทันทีที่ครบ 10 ไม่เรียกอันดับ 12-15
    # อันดับที่ใช้แสดงผลต้องเป็น 1-10 ต่อเนื่อง แม้อันดับเดิมจาก ⑥ จะกระโดด (ข้าม 4 ไปถึง 11)
    assert [s["top_rank"] for s in selected] == list(range(1, 11))
    assert selected[-1]["overall_rank"] == 11 and selected[-1]["top_rank"] == 10


def test_collect_top_n_records_technical_failure_separately_from_no_data():
    from common.bootstrap import collect_top_n_with_matchable_data

    def make_profile(item):
        if item["overall_rank"] == 2:
            raise RuntimeError("bedrock timeout")
        return {"trend": item["trend"]}

    selected, _, excluded, failed = collect_top_n_with_matchable_data(_ranked(), make_profile, lambda p: None, 3)
    assert [f["overall_rank"] for f in failed] == [2] and "timeout" in failed[0]["error"]
    assert not excluded
    assert [s["overall_rank"] for s in selected] == [1, 3, 4]


def test_collect_top_n_returns_fewer_when_not_enough_trends_have_data():
    from common.bootstrap import collect_top_n_with_matchable_data

    selected, _, excluded, _ = collect_top_n_with_matchable_data(
        _ranked(5), lambda item: {"ok": item["overall_rank"] <= 3}, lambda p: None if p["ok"] else "ข้อมูลไม่พอ", 10)
    assert len(selected) == 3 and len(excluded) == 2


# (overall_rank, คะแนนระยะสั้น, คะแนนระยะยาว) - T2 เป็นเทรนด์ช่องทางขาย, T7 อยู่ใต้เส้นแต่ระยะยาวสูงสุด
# 🆕 (2026-10-02) ระยะสั้น = ปีที่ 2, ระยะยาว = ปีที่ 5 (load_ranked_trends ใส่ไว้ใน growth_short / growth_long)
_GROWTH_RANKED = [(1, 0.9, 0.7), (2, 0.8, 0.6), (3, 0.7, 0.5), (4, 0.6, 0.4), (5, 0.55, 0.3), (6, 0.4, 0.2),
                  (7, 0.3, 0.95), (8, 0.2, 0.1)]


def _growth_ranked():
    return [{"overall_rank": r, "stream": "News", "trend": f"T{r}", "growth_short": y1, "growth_long": y3}
            for r, y1, y3 in _GROWTH_RANKED]


def test_collect_detail_and_top_k_detail_above_line_plus_top5_checks():
    """🆕 (2026-09-30) หน้ารายละเอียด = เหนือค่ากลางตลาด (0.5) ที่จับคู่ได้ / ตรวจเพิ่มแค่ที่ต้องใช้ใน Top 5 ระยะสั้น/ยาว"""
    from common.bootstrap import collect_detail_and_top_k

    calls = []

    def make_profile(item):
        calls.append(item["trend"])
        return {"trend": item["trend"]}

    out = collect_detail_and_top_k(_growth_ranked(), make_profile,
                                   lambda p: "ช่องทาง/พฤติกรรมการซื้อ" if p["trend"] == "T2" else None, n=10)
    assert [s["trend"] for s in out["selected"]] == ["T1", "T3", "T4", "T5"]        # T6-T8 อยู่ใต้เส้น
    assert [s["top_rank"] for s in out["selected"]] == [1, 2, 3, 4]
    # Top 5 ระยะสั้นต้องการ T6 เพิ่ม (T2 จับคู่ไม่ได้) / Top 5 ระยะยาวต้องการ T7 / T8 ไม่ต้องตรวจเลย
    assert [p["trend"] for p in out["extra_profiles"]] == ["T6", "T7"]
    assert sorted(calls) == ["T1", "T2", "T3", "T4", "T5", "T6", "T7"] and len(calls) == 7   # ตรวจตัวละครั้งเดียว
    assert [x["trend"] for x in out["excluded"]] == ["T2"] and not out["failed"]
    checked = {c["trend"]: c["matchable"] for c in out["checked"]}
    assert checked == {"T1": True, "T2": False, "T3": True, "T4": True, "T5": True, "T6": True, "T7": True}


def test_collect_detail_and_top_k_caps_detail_at_n_and_keeps_old_rank_files_working():
    from common.bootstrap import collect_detail_and_top_k

    out = collect_detail_and_top_k(_growth_ranked(), lambda item: {"trend": item["trend"]}, lambda p: None, n=2)
    assert [s["trend"] for s in out["selected"]] == ["T1", "T2"]
    assert [p["trend"] for p in out["extra_profiles"]] == ["T3", "T4", "T5", "T7"]
    # ผล ⑥ รอบเก่า (ไม่มีคะแนนการเติบโต) -> เหมือน collect_top_n_with_matchable_data ไม่มีการตรวจเพิ่ม
    old = collect_detail_and_top_k(_ranked(15), lambda item: {"trend": item["trend"]}, lambda p: None, n=3)
    assert [s["overall_rank"] for s in old["selected"]] == [1, 2, 3] and not old["extra_profiles"]


def test_collect_detail_and_top_k_records_failures_outside_checked():
    from common.bootstrap import collect_detail_and_top_k

    def make_profile(item):
        if item["trend"] == "T3":
            raise RuntimeError("bedrock timeout")
        return {"trend": item["trend"]}

    out = collect_detail_and_top_k(_growth_ranked(), make_profile, lambda p: None, n=10)
    assert [f["trend"] for f in out["failed"]] == ["T3"] and "timeout" in out["failed"][0]["error"]
    assert "T3" not in {c["trend"] for c in out["checked"]}
    assert [s["trend"] for s in out["selected"]] == ["T1", "T2", "T4", "T5"]


# ---------------------------------------------------------------------------
# สำเนาผลพยากรณ์เฉพาะ Top N (⑪) - 🆕 (2026-09-16)
# ---------------------------------------------------------------------------

def _import_highlights_module():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3_supply_layer"))
    import extract_trend_highlights
    return extract_trend_highlights


def test_export_top_n_forecast_keeps_only_selected_names_file_by_count_and_removes_stale(tmp_path):
    eth = _import_highlights_module()
    src = tmp_path / "step5c_df_cluster_forecast.xlsx"
    pd.DataFrame({"cluster_name": ["A", "A", "B", "C", "D"], "z_score": [1, 2, 3, 4, 5]}).to_excel(
        src, sheet_name="Sheet1", index=False)
    stale = tmp_path / "step5c_df_cluster_forecast_top7.xlsx"
    stale.write_bytes(b"old copy from a previous N")

    out = eth.export_top_n_forecast([{"trend": "A"}, {"trend": "C"}], tmp_path)

    assert out.name == "step5c_df_cluster_forecast_top2.xlsx"
    back = pd.read_excel(out, sheet_name="Sheet1")
    assert list(back["cluster_name"]) == ["A", "A", "C"] and list(back["z_score"]) == [1, 2, 4]
    assert not stale.exists()
    assert len(pd.read_excel(src)) == 5  # ต้นฉบับครบเหมือนเดิม


def test_export_top_n_forecast_skips_quietly_when_forecast_missing(tmp_path):
    eth = _import_highlights_module()
    assert eth.export_top_n_forecast([{"trend": "A"}], tmp_path) is None


def test_brand_coverage_displays_top_rank_and_falls_back_to_overall_rank_for_old_results():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3_supply_layer"))
    import run_brand_coverage as rbc

    assert rbc.display_trend_rank({"trend_top_rank": 10, "trend_overall_rank": 11}) == 10
    assert rbc.display_trend_rank({"trend_overall_rank": 11}) == 11  # ผลรอบเก่าที่ยังไม่มี top rank
    row = {"trend_name": "High-Efficiency Sun", "stream": "Social", "trend_overall_rank": 11, "trend_top_rank": 10,
           "brand_best_product": "P", "brand_best_score": 0.3, "match_reason": "r",
           "brand_best_rank_vs_market": 5, "brand_best_percentile_vs_market": 99,
           "brand_n_skus_considered": 3, "tier": "t", "market_best_product": "m", "market_best_score": 0.4}
    md = rbc.build_brand_section_markdown("Srichand", 64, 10622, {"k": row})
    assert "| High-Efficiency Sun | #10 | Social |" in md and "#11" not in md
    assert "อันดับเทรนด์ (⑥)" not in md


def test_brand_coverage_excel_has_clickable_product_links(tmp_path):
    """🆕 (2026-10-05) Excel ของ ⑬ มีลิงก์สินค้าข้างชื่อสินค้า - ใช้ลิงก์ใน JSON ก่อน ไม่มี (ผลรอบเก่า) ค้นจากแคตตาล็อก"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3_supply_layer"))
    import run_brand_coverage as rbc
    from openpyxl import load_workbook

    catalog = pd.DataFrame({"brand": ["Zen", "Zen", "Other"], "product_name": ["Cream", "Gel", "Serum"],
                            "product_url": ["https://w/cream", None, "https://w/serum"]})
    urls = rbc.product_url_index(catalog)
    assert urls[("Zen", "Cream")] == "https://w/cream" and urls["Other - Serum"] == "https://w/serum"
    assert ("Zen", "Gel") not in urls                                                     # ไม่มีลิงก์ = ไม่ใส่
    row = {"trend_name": "T", "stream": "Social", "trend_top_rank": 1, "brand_best_product": "Cream",
           "brand_best_score": 0.3, "match_reason": "r", "brand_best_rank_vs_market": 5,
           "brand_best_percentile_vs_market": 99, "brand_n_skus_considered": 2, "tier": "t",
           "market_best_product": "Other - Serum", "market_best_score": 0.4,
           "brand_top_matches": [   # ชิ้นแรกไม่มีลิงก์ใน JSON (รอบเก่า) -> ค้นจากแคตตาล็อก, ชิ้นที่สองมีลิงก์ใน JSON แล้ว
               {"rank_in_brand": 1, "product_name": "Cream", "similarity": 0.3, "rank_vs_market": 5},
               {"rank_in_brand": 2, "product_name": "Gel", "similarity": 0.2, "rank_vs_market": 9,
                "product_url": "https://w/gel-json"}]}
    path = tmp_path / "cov.xlsx"
    rbc.save_coverage_excel(path, "Zen", 2, 8738, {"Social::T": row}, urls=urls)
    wb = load_workbook(path)
    top = wb["Top 5 ต่อเทรนด์"]
    head = [c.value for c in top[1]]
    col = head.index("ลิงก์สินค้า") + 1
    assert head[col - 2] == "สินค้า"                                                     # อยู่ข้างชื่อสินค้า
    cells = [top.cell(row=r, column=col) for r in (2, 3)]
    assert [c.value for c in cells] == ["https://w/cream", "https://w/gel-json"]
    assert all(c.hyperlink is not None and c.hyperlink.target == c.value for c in cells)  # กดเปิดได้
    trend = wb["สรุปรายเทรนด์"]                                                         # ชีตภาพรวมเดิม (1 แถว/เทรนด์)
    head = [c.value for c in trend[1]]
    assert trend.cell(row=2, column=head.index("ลิงก์สินค้า Zen") + 1).value == "https://w/cream"
    assert trend.cell(row=2, column=head.index("ลิงก์สินค้าในตลาด") + 1).value == "https://w/serum"


def test_previous_reasons_are_reused_so_only_new_trends_call_the_llm(tmp_path):
    """🆕 (2026-10-19) ⑬ รันซ้ำหลังเปลี่ยนชุดเทรนด์: เหตุผลเดิมในไฟล์แบรนด์ (brand_top_matches + สินค้าที่ดีที่สุดต่อหมวด) ถูกใช้ซ้ำ"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3_supply_layer"))
    import json as _json
    import run_brand_coverage as rbc

    old = {"coverage": {
        "Social::A": {"brand_top_matches": [{"product_name": "P1", "match_reason": "r1"}, {"product_name": "P2", "match_reason": ""}],
                      "category_fit": {"categories": [{"brand_best": {"product_name": "P3", "match_reason": "r3"}},
                                                      {"brand_best": None}]}},
        "Paper::B": {"brand_top_matches": [], "category_fit": None}}}
    path = tmp_path / "phase3_brand_coverage_X.json"
    path.write_text(_json.dumps(old), encoding="utf-8")
    assert rbc.load_previous_reasons(path) == {"Social::A": {"P1": "r1", "P3": "r3"}}        # เทรนด์ที่ไม่มีเหตุผลเลยไม่อยู่ในผล
    assert rbc.load_previous_reasons(tmp_path / "missing.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert rbc.load_previous_reasons(bad) == {}
    fit = {"categories": [{"brand_best": {"product_name": "P3"}}, {"brand_best": {"product_name": "P9"}}]}
    n_llm = rbc.attach_fit_reasons(fit, [], {}, None, use_llm=False, known_reasons={"P3": "r3"})
    assert n_llm == 0 and fit["categories"][0]["brand_best"]["match_reason"] == "r3" and fit["categories"][1]["brand_best"]["match_reason"] == ""


def test_price_group_label_matches_category_report():
    """🆕 (2026-10-05) ป้ายกลุ่มราคาในชีต "รายเทรนด์" แบบเดียวกับรายงาน ⑱ ฉบับไทย"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3_supply_layer"))
    import run_brand_coverage as rbc

    assert rbc.price_group_label({"label": "low", "price_from": 39, "price_to": 198}) == "ราคาต่ำ 39-198 บาท"
    assert rbc.price_group_label({"label": "high", "price_from": 300, "price_to": 1250}) == "ราคาสูง 300-1,250 บาท"
    assert rbc.price_group_label({"label": "all", "price_from": 199, "price_to": 199}) == "ทุกช่วงราคา 199 บาท"
    assert rbc.price_group_label({"label": "all", "price_from": None, "price_to": None}) == "ทุกช่วงราคา"


def test_brand_coverage_excel_rows_and_grade_from_category_fit():
    """🆕 (2026-10-07) ชีต "รายเทรนด์" / "สรุปรายเทรนด์" ใช้ category_fit ชุดเดียวกับรายงาน ⑰/⑱: หมวดหลักของเทรนด์ (LLM เลือก 2026-10-08)
    -> ช่วงราคาตลาด -> top 5 + สินค้าที่ดีที่สุดของแบรนด์พร้อมระดับ"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3_supply_layer"))
    import run_brand_coverage as rbc
    from category_fit import category_fit

    rows = [("A", 100, "X"), ("A", 300, "X"), ("B", 50, "X"), ("A", 200, "Z"), ("A", 100, "Z"), ("B", 60, "Z"),
            ("A", 300, "X"), ("A", 200, "X"), ("B", 70, "X"), ("A", 100, "X"), ("B", None, "X"), ("A", 200, "X")]
    scored = [{"product_name": f"P{i}", "brand": b, "group": g, "sale_price_thb": None if p is None else float(p),
               "similarity": 0.99 - i / 100} for i, (g, p, b) in enumerate(rows)]
    grading = {"top_pct": {"excellent": 1, "good": 5, "average": 20},
               "level": lambda rank, n: "excellent" if rank == 1 else "below_average"}
    # 🆕 (2026-10-21) Excellent = ใกล้เทรนด์ top 1% และขายดี: P3 (อันดับ 1) ไม่มีข้อมูลยอดขาย -> ได้สูงสุด Good
    fit = category_fit(scored, "Z", "A")   # หมวดหลัก A หมวดเดียว (B ไม่นับ แม้สินค้า Z ใน B ก็ใกล้เทรนด์)
    assert rbc.trend_grade(fit, grading) == ("good", "A", "mid")
    assert rbc.trend_grade_info(fit, grading)["move"] == "cap"
    scored[3]["sales"] = {"pct": 0.9, "zero": False, "soldout": False, "basis": "sales", "sold": 50, "value": 5000, "reviews": 3}
    fit = category_fit(scored, "Z", "A")   # P3 ขายดี (top 20%) -> Excellent
    assert rbc.trend_grade(fit, grading) == ("excellent", "A", "mid") and rbc.trend_grade(None, grading) == (None, None, None)
    nobody = category_fit(scored, "Nobody", "A")
    assert rbc.trend_grade(nobody, grading) == ("below_average", None, None)
    assert rbc.trend_grade(category_fit(scored, "Z", "B"), grading)[1] == "B"     # หมวดหลักเปลี่ยน เกรดก็มาจากหมวดนั้น

    cov = {"Social::T": {"trend_name": "T", "stream": "Social", "trend_top_rank": 1, "category_fit": fit}}
    out = rbc.trend_product_rows("Z", cov, grading=grading)
    a_mid_best = [r for r in out if r["หมวด (L2)"] == "A" and r["กลุ่มราคา"] == "ราคากลาง 101-200 บาท"
                  and r["ประเภท"] == "ดีที่สุดของ Z ในกลุ่มนี้"]
    assert len(a_mid_best) == 1 and a_mid_best[0]["สินค้า"] == "P3" and a_mid_best[0]["ระดับ"] == "Excellent"
    assert a_mid_best[0]["อันดับในกลุ่ม"] == 1 and a_mid_best[0]["% แรกในกลุ่ม"] == 33.3
    assert {r["หมวด (L2)"] for r in out} == {"A"} and "สัดส่วนในเทรนด์ (%)" not in out[0] and "หมวดสำคัญ" not in out[0]
    assert any(r["สินค้า"] == "— ไม่มีสินค้า Z ในกลุ่มนี้" for r in out)                     # ช่วงราคาสูงของ A ไม่มีสินค้า Z
    assert "อันดับทั้งตลาด (จาก 12 SKU)" in out[0]


def _tier_entry(name, rank, brand_products, **extra):
    return {"trend_name": name, "stream": "Social", "trend_top_rank": rank, "tier": "t", "match_reason": "",
            "brand_best_product": brand_products[0] if brand_products else None, "brand_best_score": 0.3,
            "brand_best_rank_vs_market": 40 if brand_products else None, "brand_best_percentile_vs_market": 99,
            "brand_n_skus_considered": 2, "market_best_product": "A - A1", "market_best_score": 0.4,
            "brand_top_matches": [{"rank_in_brand": i + 1, "product_name": p, "similarity": 0.3 - i / 100,
                                   "rank_vs_market": 40 + i, "category": "Skincare"}
                                  for i, p in enumerate(brand_products)], **extra}


def _tiers_fixture():
    """price_tiers ตามรูปที่ price_tiers.price_tier_breakdown คืน: ราคาต่ำ (สินค้าแบรนด์ติด top 5 อันดับ 2) + ราคาสูง"""
    def item(i, brand="A", price=100.0, **extra):
        return {"product_name": f"{brand}{i}", "brand": brand, "sale_price_thb": price, "similarity": 0.5 - i / 100,
                "rank_in_market": i * 3, "rank_in_category": i * 2, "rank_in_tier": i, "is_you": False, **extra}
    low_top = [item(i) for i in range(1, 6)]
    low_top[1] = item(2, "Zen", 120.0, product_name="Cream", is_you=True)
    return {"category": "Skin Care", "n_category": 3231, "n_market": 8738, "pool_size": 87, "pool_in_category": 79,
            "brand": {"name": "Zen", "n": 4, "price_min": 39.0, "price_max": 898.0},
            "tiers": [{"label": "low", "price_from": 39, "price_to": 198, "n_market": 1151, "n_brands": 208, "n_brand": 2,
                       "top": low_top, "brand_best": {**item(2, "Zen", 120.0, product_name="Cream"),
                                                      "top_pct_in_tier": 1}},
                      {"label": "high", "price_from": 199, "price_to": 898, "n_market": 579, "n_brands": 159, "n_brand": 2,
                       "top": [item(i, "B", 500.0) for i in range(1, 6)], "brand_best": None}],
            "excluded": {}}


def test_brand_coverage_trend_sheet_groups_products_by_price_tier_like_category_report(tmp_path):
    """🆕 (2026-10-05) ชีต "รายเทรนด์" จัดตามกลุ่มราคาแบบรายงาน ⑱: ต่อกลุ่ม top 5 + สินค้าที่ดีที่สุดของแบรนด์ พร้อมอันดับในกลุ่ม
    เทรนด์ที่ผล ⑬ ยังไม่มี price_tiers (รอบเก่า) ใช้ top 5 ตลาดทั้งหมด + สินค้าของแบรนด์แทน"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3_supply_layer"))
    import run_brand_coverage as rbc
    from openpyxl import load_workbook

    market = [{"product_name": f"M{i}", "brand": "M", "similarity": 0.5 - i / 100, "sale_price_thb": 100.0}
              for i in range(1, 7)]
    coverage = {   # ใส่เทรนด์อันดับ 2 ก่อน - ชีตต้องเรียงตามอันดับเทรนด์
        "Social::Old": _tier_entry("Old", 2, ["Gel"]),
        "Social::First": _tier_entry("First", 1, ["Cream", "Gel"], price_tiers=_tiers_fixture()),
    }
    l2 = {("M", "M1"): "Hair Care", ("Zen", "Gel"): "Sun Care"}
    rows = rbc.trend_product_rows("Zen", coverage, 10622, {}, l2, {"Social::Old": market})
    first = [r for r in rows if r["เทรนด์"] == "First"]
    assert rows[0]["เทรนด์"] == "First" and len(first) == (5 + 1) + (5 + 1)               # 2 กลุ่ม x (top 5 + แบรนด์ 1 แถว)
    assert [r["กลุ่มราคา"] for r in first] == ["ราคาต่ำ 39-198 บาท"] * 6 + ["ราคาสูง 199-898 บาท"] * 6
    assert [r["ประเภท"] for r in first[:6]] == (["Top 5 กลุ่มราคา", "Top 5 กลุ่มราคา · สินค้า Zen"]
                                                 + ["Top 5 กลุ่มราคา"] * 3 + ["ดีที่สุดของ Zen ในกลุ่มนี้"])
    best = first[5]
    assert (best["สินค้า"], best["อันดับในกลุ่ม"], best["% แรกในกลุ่ม"], best["อันดับในหมวด"]) == ("Cream", 2, 1, 4)
    assert best["อันดับทั้งตลาด (จาก 8,738 SKU)"] == 6                                   # ขนาดตลาดจาก price_tiers ไม่ใช่ 10,622
    assert (first[0]["สินค้าในกลุ่ม"], first[0]["แบรนด์ในกลุ่ม"], first[0]["หมวด (L2)"]) == (1151, 208, "Skin Care")
    assert first[-1]["สินค้า"] == "— ไม่มีสินค้า Zen ในกลุ่มราคานี้"
    old = [r for r in rows if r["เทรนด์"] == "Old"]
    assert [r["ประเภท"] for r in old] == ["Top 5 ตลาด"] * 5 + ["สินค้า Zen"]
    assert old[0]["หมวด (L2)"] == "Hair Care" and old[-1]["หมวด (L2)"] == "Sun Care" and old[0]["กลุ่มราคา"] is None
    # ชุดเทรนด์ของรอบ (⑪): เทรนด์ที่ไม่อยู่ในชุด (ผล ⑬ เก่า) ไม่ใส่ในชีตนี้
    only = rbc.trend_product_rows("Zen", coverage, 10622, {}, l2, {"Social::Old": market}, trend_set={("Social", "First")})
    assert {r["เทรนด์"] for r in only} == {"First"}
    # แบรนด์ไม่มีสินค้าในหมวดหลัก -> 1 กลุ่ม "ทุกช่วงราคา" + ข้อความแจ้ง
    nobrand = {**_tiers_fixture(), "tiers": [{"label": "all", "price_from": None, "price_to": None, "n_market": 895,
                                              "n_brands": 95, "top": [], "brand_best": None}]}
    rows2 = rbc.trend_product_rows("Zen", {"k": _tier_entry("Hair", 1, [], price_tiers=nobrand)})
    assert rows2[-1]["กลุ่มราคา"] == "ทุกช่วงราคา" and rows2[-1]["สินค้า"] == "— Zen ไม่มีสินค้าในหมวดนี้"

    path = tmp_path / "cov.xlsx"
    rbc.save_coverage_excel(path, "Zen", 4, 10622, coverage, urls={}, l2=l2, market_tops={"Social::Old": market})
    wb = load_workbook(path)
    assert wb.sheetnames == ["สรุป", "Top 5 ต่อเทรนด์", "รายเทรนด์", "สรุปรายเทรนด์"]
    ws = wb["รายเทรนด์"]
    head = [c.value for c in ws[1]]
    kind = head.index("ประเภท") + 1
    shaded = [r for r in range(2, ws.max_row + 1)
              if ws.cell(row=r, column=kind).value in ("สินค้า Zen", "ดีที่สุดของ Zen ในกลุ่มนี้")]
    assert len(shaded) == 3 and all(ws.cell(row=r, column=1).fill.start_color.rgb.endswith("FDEBD9") for r in shaded)


# ---------------------------------------------------------------------------
# ⑫ category_breakdown - สินค้าที่ใกล้เทรนด์แยกตามหมวด (feedback 2026-09-28) - หมวด = L2 ของ Euromonitor ที่ผู้เรียกส่งมา
# (การจัดหมวดสินค้าเทสที่ test_euromonitor_mapping.py)
# ---------------------------------------------------------------------------
sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "phase3_supply_layer")))
from category_breakdown import category_breakdown, market_price_cuts  # noqa: E402


def _scored(groups_sims):
    return [{"product_name": f"P{i}", "brand": "B", "group": g, "similarity": s, "sale_price_thb": 100.0 * (i + 1)}
            for i, (g, s) in enumerate(groups_sims)]


def test_category_breakdown_picks_top_groups_in_pool_and_keeps_market_rank():
    # 200 ชิ้น x pool_fraction 0.05 = pool 10 ชิ้น
    items =([("A", 0.9 - i * 0.001) for i in range(4)] + [("B", 0.85 - i * 0.001) for i in range(4)]
             + [("C", 0.80), ("D", 0.79)] + [("E", 0.1)] * 190)
    out = category_breakdown(_scored(items), {"A": 40, "B": 50, "C": 5, "D": 9, "E": 190}, pool_fraction=0.05,
                             n_categories=3, per_category=2, n_distribution=2, min_pool=1)   # เทสลำดับ ไม่ใช่เกณฑ์ขั้นต่ำ
    assert out["pool_size"] == 10
    assert [c["group"] for c in out["categories"]] == ["A", "B", "C"]   # A=B=4 ชิ้น -> A ก่อน (ใกล้กว่า), C=D=1 -> C
    assert out["distribution"] == [{"group": "A", "n": 4}, {"group": "B", "n": 4}, {"group": None, "n": 2}]
    a, b, c = out["categories"]
    assert (a["n_pool"], a["n_total"]) == (4, 40)
    assert [p["rank_in_market"] for p in b["products"]] == [5, 6]       # อันดับเมื่อเทียบทั้งร้าน
    assert a["median_price_thb"] == 250.0 and a["min_price_thb"] == 100.0 and a["max_price_thb"] == 400.0
    assert set(a["products"][0]) == {"product_name", "brand", "category", "group", "subgroup", "similarity",
                                     "sale_price_thb", "sold_count", "rank_in_market"}   # ไม่มี _idx หรือฟิลด์ภายในหลุดออกไป
    assert (a["parent"], a["subgroup"], a["color"]) == ("A", None, 0) and out["categories"][2]["color"] == 2


def _scored_sub(rows):
    """rows: [(หมวด, ชนิดสินค้า, จำนวน)] เรียงตามที่ให้มา (ใกล้ที่สุดก่อน) -> สินค้าปลอมพร้อม subgroup"""
    out, sim = [], 0.9
    for g, sub, n in rows:
        for _ in range(n):
            out.append({"product_name": f"P{len(out)}", "brand": "B", "group": g, "subgroup": sub, "similarity": sim,
                         "sale_price_thb": 100.0})
            sim -= 0.001
    return out


def test_category_breakdown_splits_dominant_category_by_product_type():
    # pool 20 ชิ้น: Hair Care 18 (Shampoo 8 / Mask 5 / Oil 3 / Comb 2), Skin Care 2 -> Skin ไม่ถึง 3 ชิ้น ไม่ได้คอลัมน์
    rows = [("Hair Care", "Shampoo", 8), ("Hair Care", "Mask", 5), ("Hair Care", "Oil", 3), ("Hair Care", "Comb", 2),
            ("Skin Care", "Serum", 2), ("Skin Care", "Serum", 180)]
    sizes = {("Hair Care", "Shampoo"): 300, ("Hair Care", "Mask"): 120, ("Hair Care", "Oil"): 80}
    out = category_breakdown(_scored_sub(rows), {"Hair Care": 900, "Skin Care": 3000}, pool_fraction=0.1,
                             subgroup_sizes=sizes)
    assert out["pool_size"] == 20
    assert [c["group"] for c in out["categories"]] == ["Hair Care · Shampoo", "Hair Care · Mask", "Hair Care · Oil"]
    assert [(c["parent"], c["subgroup"], c["color"]) for c in out["categories"]] ==         [("Hair Care", "Shampoo", 0), ("Hair Care", "Mask", 0), ("Hair Care", "Oil", 0)]   # สีเดียวกับหมวดแม่
    assert [(c["n_pool"], c["n_total"]) for c in out["categories"]] == [(8, 300), (5, 120), (3, 80)]
    assert all(p["subgroup"] == c["subgroup"] for c in out["categories"] for p in c["products"])
    assert out["distribution"] == [{"group": "Hair Care", "n": 18}, {"group": "Skin Care", "n": 2}]   # แถบยังเป็น L2


def test_category_breakdown_splits_only_as_many_columns_as_needed():
    # Skin 12 (Serum 6 / Cream 4 / Mask 2), Colour 5, Sun 3 -> 3 หมวดผ่านเกณฑ์ ขาด 1 คอลัมน์ -> แตก Skin เป็น 2 ชนิด
    rows = [("Skin Care", "Serum", 6), ("Colour", "Lip", 5), ("Skin Care", "Cream", 4), ("Sun", "Face", 3),
            ("Skin Care", "Mask", 2), ("Other", "X", 180)]
    out = category_breakdown(_scored_sub(rows), {}, pool_fraction=0.1)
    assert [c["group"] for c in out["categories"]] == ["Skin Care · Serum", "Skin Care · Cream", "Colour", "Sun"]
    assert [c["color"] for c in out["categories"]] == [0, 0, 1, 2]
    # ชนิดสินค้าในหมวดใหญ่ไม่ถึงเกณฑ์ 2 ชนิด -> แตกไม่ได้ คอลัมน์น้อยกว่า 4 ได้ (เทมเพลตยืดคอลัมน์ตามจำนวน)
    few = [("Skin Care", "Serum", 15), ("Skin Care", "Cream", 2), ("Sun", "Face", 3), ("Other", "X", 180)]
    assert [c["group"] for c in category_breakdown(_scored_sub(few), {}, pool_fraction=0.1)["categories"]] == ["Skin Care", "Sun"]


def test_category_breakdown_fills_products_from_outside_pool_and_handles_empty():
    items = [("A", 0.9), ("B", 0.8)] + [("A", 0.1)] * 98
    out = category_breakdown(_scored(items), {"A": 99, "B": 1}, pool_fraction=0.02, per_category=3)
    assert [len(c["products"]) for c in out["categories"]] == [3, 1]   # A เติมจากนอก pool ได้, B มีชิ้นเดียว
    assert category_breakdown([], {}) == {"pool_size": 0, "distribution": [], "categories": []}


def test_market_price_cuts_equal_thirds_ties_and_small_columns():
    """🆕 (2026-10-07) ช่วงราคาตลาด: แบ่งจำนวนสินค้าเท่าๆ กัน เส้น = ราคาสูงสุดของช่วงล่าง ราคาที่ซ้ำเส้นอยู่ช่วงล่าง"""
    assert market_price_cuts([10, 20, 30, 40, 50, 60, 70, 80, 90]) == [30, 60]        # 3 / 3 / 3
    assert market_price_cuts([90, None, 10, 50, 20, 30, 40, 60, 70, 80]) == [30, 60]  # ไม่เรียง + ไม่มีราคา ไม่นับ
    assert market_price_cuts([10, 20, 20, 20, 20, 30]) == [20]                         # เส้นชนกัน -> เหลือ 2 ช่วง
    assert market_price_cuts([199] * 5) == []                                          # ราคาเดียวทั้งคอลัมน์ -> ช่วงเดียว
    assert market_price_cuts([10, 20]) == [10] and market_price_cuts([10]) == []


def test_category_breakdown_price_tiers_from_whole_store():
    """🆕 (2026-10-07) แต่ละคอลัมน์: ช่วงราคาจากราคาทั้งร้านของคอลัมน์ + จำนวนใน pool + ชิ้นที่ใกล้ที่สุดในแต่ละช่วง"""
    # หมวด A 9 ชิ้น ราคา 100..900 (ชิ้นแรกใกล้ที่สุด) + หมวด Z 91 ชิ้น -> pool 10% = 10 ชิ้น: A 9 ชิ้นแรก + Z 1 ชิ้น
    items = [{"product_name": f"A{i}", "brand": "B", "group": "A", "similarity": 0.9 - i * 0.01,
              "sale_price_thb": float(p)} for i, p in enumerate([900, 100, 500, 200, 800, 300, 400, 700, 600])]
    items += [{"product_name": f"Z{i}", "brand": "B", "group": "Z", "similarity": 0.5 - i * 0.001, "sale_price_thb": 50.0}
              for i in range(91)]
    out = category_breakdown(items, {"A": 9, "Z": 91}, pool_fraction=0.1, min_pool=1)
    a = out["categories"][0]
    assert a["group"] == "A"
    tiers = a["price_tiers"]
    assert [(t["label"], t["price_from"], t["price_to"], t["n_total"], t["n_pool"]) for t in tiers] == \
        [("low", 100, 300, 3, 3), ("mid", 301, 600, 3, 3), ("high", 601, 900, 3, 3)]
    assert [(t["product"]["product_name"], t["product"]["rank_in_market"]) for t in tiers] == \
        [("A1", 2), ("A2", 3), ("A0", 1)]                         # ชิ้นที่ใกล้ที่สุดของแต่ละช่วง + อันดับในร้าน
    assert [p["product_name"] for p in a["products"]] == ["A0", "A1", "A2"]   # 3 ชิ้นที่ใกล้ที่สุดเหมือนเดิม
    z = out["categories"][1]
    assert [(t["label"], t["n_total"], t["n_pool"]) for t in z["price_tiers"]] == [("all", 91, 1)]   # ราคาเดียว = ช่วงเดียว
    # ปิดการแบ่งช่วงราคา / ไม่มีราคาเลย -> None
    assert category_breakdown(items, {}, pool_fraction=0.1, min_pool=1, n_price_tiers=0)["categories"][0]["price_tiers"] is None
    unpriced = [{**s, "sale_price_thb": None} for s in items]
    assert category_breakdown(unpriced, {}, pool_fraction=0.1, min_pool=1)["categories"][0]["price_tiers"] is None


# ---------------------------------------------------------------------------
# ⑬/⑰/⑱ category_fit - เทรนด์ -> หมวดที่เทรนด์แตะ -> ช่วงราคาตลาด -> สินค้า (2026-10-07)
# ---------------------------------------------------------------------------
from category_fit import category_fit  # noqa: E402


def test_category_fit_trend_category_price_product():
    # (หมวด, ราคา, แบรนด์) เรียงจากใกล้เทรนด์ที่สุด - หมวดหลัก A (🆕 2026-10-08 LLM เลือกหมวดเดียว) / B ไว้เทียบว่าไม่ถูกนับ
    rows = [("A", 100, "X"), ("A", 300, "X"), ("B", 50, "X"), ("A", 200, "Z"), ("A", 100, "Z"), ("B", 60, "Z"),
            ("A", 300, "X"), ("A", 200, "X"), ("B", 70, "X"), ("A", 100, "X"), ("B", None, "X"), ("A", 200, "X")]
    scored = [{"product_name": f"P{i}", "brand": b, "group": g, "sale_price_thb": None if p is None else float(p),
               "similarity": 0.99 - i / 100} for i, (g, p, b) in enumerate(rows)]
    fit = category_fit(scored, "Z", "A")
    assert (fit["n_market"], fit["main_category"]) == (12, "A") and "pool_size" not in fit
    (a,) = fit["categories"]                                       # หมวดหลักหมวดเดียว
    assert (a["category"], a["n_total"], a["n_brand"]) == ("A", 8, 2) and "n_pool" not in a
    # ราคาหมวด A: 100 x3 / 200 x3 / 300 x2 -> 3 ช่วง (ราคาที่เท่าเส้นอยู่ช่วงล่าง)
    assert [(t["label"], t["price_from"], t["price_to"], t["n_total"], t["n_brand"]) for t in a["tiers"]] ==         [("low", 100, 100, 3, 1), ("mid", 101, 200, 3, 1), ("high", 201, 300, 2, 0)]
    low, mid, high = a["tiers"]
    assert [x["product_name"] for x in low["top"]] == ["P0", "P4", "P9"] and [x["rank_in_tier"] for x in low["top"]] == [1, 2, 3]
    assert (low["brand_best"]["product_name"], low["brand_best"]["rank_in_tier"], low["brand_best"]["rank_in_market"]) == ("P4", 2, 5)
    assert high["brand_best"] is None
    # ชิ้นที่ดีที่สุดของหมวด = % แรกในกลุ่มดีที่สุด (P3 อันดับ 1 จาก 3 ในช่วงกลาง ดีกว่า P4 อันดับ 2 จาก 3 ในช่วงต่ำ)
    best = a["brand_best"]
    assert (best["product_name"], best["tier"], best["rank_in_tier"], best["n_tier"], best["rank_in_market"]) == ("P3", "mid", 1, 3, 4)
    assert (best["price_from"], best["price_to"]) == (101, 200)
    # หมวดหลัก B: สินค้าไม่มีราคาไม่เข้าช่วงไหน (นับใน n_total ของหมวด)
    (b,) = category_fit(scored, "Z", "B")["categories"]
    assert (b["category"], b["n_total"]) == ("B", 4)
    assert [t["n_total"] for t in b["tiers"]] == [1, 1, 1] and b["brand_best"]["product_name"] == "P5"
    # แบรนด์ไม่มีสินค้า -> brand_best None / หมวดหลักที่ตลาดไม่มีสินค้าเลย -> ไม่มีหมวด / ตลาดว่าง
    none = category_fit(scored, "Nobody", "A")
    assert [c["category"] for c in none["categories"]] == ["A"] and none["categories"][0]["brand_best"] is None
    assert category_fit(scored, "Z", "Q")["categories"] == [] and category_fit([], "Z", "A") is None


def _typed(rows):
    """(หมวด, ชนิดสินค้า, ราคา) เรียงจากใกล้เทรนด์ที่สุด -> scored ปลอม"""
    return [{"product_name": f"P{i}", "brand": "B", "group": g, "subgroup": sub, "sale_price_thb": float(p),
             "similarity": 0.99 - i / 100} for i, (g, sub, p) in enumerate(rows)]


def test_category_breakdown_main_category_columns_are_product_types_of_that_category():
    """🆕 (2026-10-08) main_category (LLM เลือก): pool = สินค้าใกล้เทรนด์สุดในหมวดนั้น คอลัมน์ = ชนิดสินค้า (>= min_pool) ของหมวด
    สินค้าหมวดอื่นที่ใกล้กว่า (กันแดดของเทรนด์เรตินอล) ไม่เข้า pool / คอลัมน์ แต่ rank_in_market ยังนับทั้งร้าน"""
    rows = [("Sun Care", "Sun Protection", 300)] * 2 + \
           [("Skin Care", "Serum", 100 + i) for i in range(4)] + [("Skin Care", "Cream", 200 + i) for i in range(3)] + \
           [("Skin Care", "Mask", 50)] + [("Skin Care", "Serum", 400)] * 2 + [("Hair Care", "Shampoo", 80)] * 8   # 20 ชิ้น x 0.5 = pool 10
    out = category_breakdown(_typed(rows), {"Skin Care": 10}, pool_fraction=0.5, min_pool=3, main_category="Skin Care",
                             subgroup_sizes={("Skin Care", "Serum"): 6, ("Skin Care", "Cream"): 3})
    assert out["main_category"] == "Skin Care" and out["n_category"] == 10 and out["pool_size"] == 10
    assert [(d["group"], d["n"]) for d in out["distribution"]] == [("Serum", 6), ("Cream", 3), ("Mask", 1)]
    assert [(c["group"], c["parent"], c["subgroup"], c["color"], c["n_pool"], c["n_total"]) for c in out["categories"]] == \
        [("Skin Care · Serum", "Skin Care", "Serum", 0, 6, 6), ("Skin Care · Cream", "Skin Care", "Cream", 1, 3, 3)]
    serum = out["categories"][0]
    assert [p["product_name"] for p in serum["products"]] == ["P2", "P3", "P4"]
    assert [p["rank_in_market"] for p in serum["products"]] == [3, 4, 5]          # อันดับทั้งร้านนับกันแดด 2 ชิ้นข้างหน้าด้วย
    assert sum(t["n_pool"] for t in serum["price_tiers"]) == 6 and all(t["n_total"] for t in serum["price_tiers"])


def test_category_breakdown_main_category_single_column_and_empty():
    # ชนิดสินค้าถึงเกณฑ์ชนิดเดียว -> คอลัมน์เดียวทั้งหมวด (ไม่แตกเหลือชนิดเดียว)
    one = category_breakdown(_typed([("Hair Care", "Shampoo", 100 + i) for i in range(5)] + [("Hair Care", "Oil", 90)]), {"Hair Care": 6},
                             pool_fraction=1.0, min_pool=3, main_category="Hair Care")
    assert [(c["group"], c["subgroup"], c["n_pool"], c["n_total"]) for c in one["categories"]] == [("Hair Care", None, 6, 6)]
    # ตลาดไม่มีสินค้าในหมวดหลัก / ตลาดว่าง
    none = category_breakdown(_typed([("Skin Care", "Serum", 100)] * 3), {}, pool_fraction=1.0, main_category="Fragrances")
    assert none == {"pool_size": 0, "distribution": [], "categories": [], "main_category": "Fragrances", "n_category": 0}
    assert category_breakdown([], {}, main_category="Skin Care")["main_category"] == "Skin Care"


# ---------------------------------------------------------------------------
# trend_category - หมวดหลักของเทรนด์ที่ LLM เลือก (2026-10-08)
# ---------------------------------------------------------------------------
import trend_category as tc  # noqa: E402

_PROFILE = {"trend": "Barrier Care", "attribute": "ceramide", "functional_consequence": "repairs the barrier",
            "psychosocial_consequence": "ข้อมูลไม่พอ", "job_to_be_done": "calm skin", "point_of_difference": "lipids"}


def _ev(n_market=8738):
    rows = [{"group": "Skin Care", "brand": "A", "product_name": f"Cream {i}", "similarity": 0.9 - i / 100} for i in range(5)] + \
           [{"group": "Sun Care", "brand": "S", "product_name": f"Sun {i}", "similarity": 0.8 - i / 100} for i in range(3)] + \
           [{"group": "Hair Care", "brand": "H", "product_name": "Shampoo", "similarity": 0.1}]
    return {**tc.build_evidence(rows, 6), "n_market": n_market}


def test_trend_category_evidence_and_cache_key():
    ev = _ev()
    assert ev["pool_size"] == 6 and [(g, d["n"]) for g, d in ev["counts"].items()] == [("Skin Care", 5), ("Sun Care", 1)]
    assert ev["counts"]["Skin Care"]["examples"] == [(1, "A", "Cream 0"), (2, "A", "Cream 1"), (3, "A", "Cream 2")]
    assert "Skin Care: 5 of 6" in tc.evidence_text(ev) and "#6 S Sun 0" in tc.evidence_text(ev)
    k = tc.cache_key(_PROFILE, 8738)
    assert k == tc.cache_key(dict(_PROFILE), 8738) and k != tc.cache_key(_PROFILE, 10622)          # ตลาดเปลี่ยน -> ตัดสินใหม่
    assert k != tc.cache_key({**_PROFILE, "functional_consequence": "different"}, 8738)
    assert "Barrier Care" in tc.trend_block(_PROFILE) and "(none)" in tc.trend_block({**_PROFILE, "attribute": ""})


def test_trend_category_parse_answer_and_ask():
    assert tc.parse_answer('{"category": "Skin Care", "reason": " ok "}') == {"category": "Skin Care", "reason": "ok"}
    assert tc.parse_answer('```json\n{"category": "Sun Care", "reason": "x"}\n```')["category"] == "Sun Care"
    assert tc.parse_answer('{"category": "Sunscreen"}') is None and tc.parse_answer("") is None and tc.parse_answer("not json") is None
    assert tc.parse_answer('{"main": "Skin Care"}') is None and tc.parse_answer("[1]") is None

    class Resp:
        def __init__(self, text):
            self.choices = [type("C", (), {"message": type("M", (), {"content": text})()})()]

    class Client:
        def __init__(self, answers):
            self.answers, self.calls = list(answers), 0
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **kw):
            self.calls += 1
            a = self.answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return Resp(a)

    waits = []
    c = Client(["", RuntimeError("throttle"), '{"category": "Skin Care", "reason": "r"}'])   # ตอบว่าง / ล้มเหลว -> รอแล้วลองใหม่
    assert tc.ask(c, _PROFILE, _ev(), sleep=waits.append)["category"] == "Skin Care" and c.calls == 3 and waits == [3, 6]
    assert tc.ask(Client([""] * tc.MAX_ATTEMPTS), _PROFILE, _ev(), sleep=lambda *_: None) is None


def test_trend_category_decide_uses_cache_and_falls_back(tmp_path):
    path = tmp_path / "labels.jsonl"
    # ไม่มี cache + ไม่ให้เรียก LLM -> หมวดอันดับ 1 ของ embedding (source embedding_fallback) และไม่บันทึกลงไฟล์
    out = tc.decide([("t", _PROFILE, _ev())], path, use_llm=False)
    assert out["t"]["category"] == "Skin Care" and out["t"]["source"] == "embedding_fallback" and not path.exists()
    # มีคำตัดสินในไฟล์ (ขนาดตลาดเดียวกัน) -> ใช้ซ้ำ ไม่ถาม LLM; ขนาดตลาดต่างกัน -> ไม่ใช้
    tc.append_label(path, {"key": tc.cache_key(_PROFILE, 8738), "category": "Hair Care", "reason": "from file"})
    out = tc.decide([("t", _PROFILE, _ev())], path, use_llm=False)
    assert (out["t"]["category"], out["t"]["reason"], out["t"]["source"]) == ("Hair Care", "from file", "cache")
    assert tc.decide([("t", _PROFILE, _ev(10622))], path, use_llm=False)["t"]["source"] == "embedding_fallback"
    # ไฟล์มีหมวดที่ไม่อยู่ในรายการ (พรอมต์เก่า) -> ไม่เชื่อ
    tc.append_label(path, {"key": tc.cache_key(_PROFILE, 10622), "category": "Gardening", "reason": ""})
    assert tc.decide([("t", _PROFILE, _ev(10622))], path, use_llm=False)["t"]["source"] == "embedding_fallback"


# ---------------------------------------------------------------------------
# ⑬/⑱ price_tiers - เทรนด์ -> หมวด L2 หลัก -> ระดับราคาจากราคาสินค้าของแบรนด์เอง (feedback 2026-10-05)
# ---------------------------------------------------------------------------
from price_tiers import price_tier_breakdown, tier_bounds, tier_cuts, tier_of  # noqa: E402


def test_tier_cuts_midpoints_ties_and_small_brands():
    # ตัวอย่างจริง: ซีรัม Mizumi 9 ชิ้น -> 3 ระดับ 3/3/3 เส้นแบ่งกึ่งกลางระหว่างชิ้นที่ 3-4 และ 6-7
    prices = [59, 59, 88, 299, 576, 576, 798, 890, 898]
    cuts = tier_cuts(prices)
    assert cuts == [193.5, 687.0]
    assert [tier_of(p, cuts) for p in prices] == [0, 0, 0, 1, 1, 1, 2, 2, 2]
    assert tier_bounds(cuts, 59, 898) == [(59, 193), (194, 687), (688, 898)]
    # ระดับละ >= 2 ชิ้น: 2-3 ชิ้น -> 1 ระดับ, 4-5 ชิ้น -> 2 ระดับ, 6+ ชิ้น -> 3 ระดับ
    assert tier_cuts([10, 20, 30]) == [] and len(tier_cuts([10, 20, 30, 40])) == 1 and len(tier_cuts(range(1, 7))) == 2
    # ราคาซ้ำกันทั้งหมด -> แบ่งไม่ได้ (เส้นแบ่งเท่ากับราคาสูงสุดถูกทิ้ง) ราคาที่ = เส้นแบ่งอยู่ระดับล่าง
    assert tier_cuts([100] * 8) == [] and tier_of(198, [198.0, 299.0]) == 0 and tier_of(199, [198.0, 299.0]) == 1
    assert tier_cuts([None, None]) == [] and tier_bounds([], 39, 898) == [(39, 898)]


def _market(rows):
    """rows: [(แบรนด์, หมวด, ราคา)] เรียงตามที่ให้มา (ใกล้เทรนด์ที่สุดก่อน) -> สินค้าปลอม similarity ลดลงเรื่อยๆ"""
    return [{"product_name": f"{b} P{i}", "brand": b, "group": g, "sale_price_thb": p, "similarity": 0.9 - i * 0.001}
            for i, (b, g, p) in enumerate(rows)]


def _tier_market():
    """ตลาด 100 ชิ้น (pool 1% = 1 ชิ้น -> ใช้ pool_fraction 0.1 = 10 ชิ้น): Skin 6 ชิ้นใน 10 อันดับแรก -> หมวดหลัก = Skin"""
    top = [("X", "Skin", 50), ("Z", "Colour", 100), ("Mine", "Skin", 120), ("Y", "Skin", 300), ("Mine", "Skin", 250),
           ("Y", "Skin", 900), ("Y", "Skin", 20), ("Mine", "Skin", 400), ("W", "Colour", 100), ("Y", "Skin", None)]
    rest = [("Y", "Skin", 60 + i) for i in range(40)] + [("Q", "Hair", 50)] * 50
    return _market(top + rest)


def test_price_tier_breakdown_category_then_tiers():
    out = price_tier_breakdown(_tier_market(), "Mine", pool_fraction=0.1)
    assert out["category"] == "Skin" and out["pool_size"] == 10 and out["pool_in_category"] == 8
    assert out["n_category"] == 48 and out["n_market"] == 100
    b = out["brand"]
    assert (b["n"], b["n_priced"], b["price_min"], b["price_max"]) == (3, 3, 120, 400)
    assert b["best"]["rank_in_market"] == 3 and b["best"]["rank_in_category"] == 2   # Colour อันดับ 2 ไม่นับในหมวด Skin
    # แบรนด์ 3 ชิ้น (120/250/400) -> 1 ระดับ ช่วงราคา 120-400 ตัดสินค้าที่ถูก/แพงกว่า (50, 20, 900, 60-99) และไม่มีราคาออก
    (tier,) = out["tiers"]
    assert tier["label"] == "all" and (tier["price_from"], tier["price_to"]) == (120, 400)
    assert [t["product_name"] for t in tier["top"]] == ["Mine P2", "Y P3", "Mine P4", "Mine P7"]
    assert [t["rank_in_tier"] for t in tier["top"]] == [1, 2, 3, 4] and [t["is_you"] for t in tier["top"]] == [True, False, True, True]
    assert tier["n_market"] == 4 and tier["n_brand"] == 3 and tier["n_brands"] == 2
    assert tier["brand_best"]["rank_in_tier"] == 1 and tier["brand_best"]["rank_in_market"] == 3
    assert out["excluded"] == {"cheaper": 42, "pricier": 1, "unpriced": 1}


def test_price_tier_breakdown_three_tiers_rank_never_worse_than_market():
    rows = [("Mine", "Skin", p) for p in (50, 60, 70, 200, 220, 240, 800, 850, 900)]
    market = [("Y", "Skin", 55 + 10 * i) for i in range(40)] + rows + [("Y", "Skin", 75)] * 20   # แทรกคู่แข่งปนกัน
    scored = _market(market + [("Q", "Hair", 100)] * 31)
    out = price_tier_breakdown(scored, "Mine", pool_fraction=0.5, top_n=3)
    tiers = out["tiers"]
    assert [t["label"] for t in tiers] == ["low", "mid", "high"]
    assert [(t["price_from"], t["price_to"]) for t in tiers] == [(50, 135), (136, 520), (521, 900)]
    assert [t["n_brand"] for t in tiers] == [3, 3, 3]
    for t in tiers:
        best = t["brand_best"]
        assert 1 <= best["rank_in_tier"] <= best["rank_in_category"] <= best["rank_in_market"]
        assert len(t["top"]) == 3 and all(50 <= x["sale_price_thb"] <= 900 for x in t["top"])
        assert best["top_pct_in_tier"] == max(1, round(best["rank_in_tier"] / t["n_market"] * 100))
    # top ของแต่ละระดับเรียงตามความคล้าย (rank_in_market เพิ่มขึ้น)
    assert all([x["rank_in_market"] for x in t["top"]] == sorted(x["rank_in_market"] for x in t["top"]) for t in tiers)


def test_price_tier_breakdown_brand_without_products_in_category_and_empty():
    out = price_tier_breakdown(_tier_market(), "Nobody", pool_fraction=0.1)
    assert out["brand"]["n"] == 0 and out["brand"]["best"] is None
    (tier,) = out["tiers"]
    assert tier["label"] == "all" and tier["price_from"] is None and tier["brand_best"] is None
    assert [t["rank_in_tier"] for t in tier["top"]] == [1, 2, 3, 4, 5] and not any(t["is_you"] for t in tier["top"])
    assert price_tier_breakdown([], "Mine") is None
    assert price_tier_breakdown([{"product_name": "a", "brand": "b", "group": None, "sale_price_thb": 1, "similarity": 1}], "b") is None


# ---------------------------------------------------------------------------
# ⑭-⑮ แปลงโครง JSON ของ STEPIC ให้คงที่ (🆕 2026-10-01 - LLM ตอบโครงต่างกันระหว่างรอบ)
# ---------------------------------------------------------------------------

def _import_stepic_report():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase5_report"))
    import run_stepic_report
    return run_stepic_report


def test_normalize_stepic_raw_flattens_nested_dimensions():
    rsr = _import_stepic_report()
    raw = {"technology": {"dimension": "Technology", "analysis": {"core_technology": "NADES"}},
           "creativity": {"creativity_analysis": {"brand_expression": "Green"}},
           "industry": {"concept": "C", "market_structure": {"transformation": "T", "channel_shift": "S"},
                        "industry": {"strategic_positioning": "Own the lab", "concept": "ignored"}}}
    out = rsr.normalize_stepic_raw(raw)
    assert out["technology"]["core_technology"] == "NADES" and "analysis" not in out["technology"]
    assert out["creativity"]["brand_expression"] == "Green"
    assert out["industry"]["strategic_positioning"] == "Own the lab" and out["industry"]["concept"] == "C"
    assert out["industry"]["market_structure"] == "T · S"
    assert raw["technology"]["analysis"]                      # ไม่แก้ของเดิม
    flat = {"technology": {"core_technology": "X"}}
    assert rsr.normalize_stepic_raw(flat) == flat


def test_normalize_stepic_final_signals():
    rsr = _import_stepic_report()
    final = {"cross_dimensional_signals": [{"signal_type": "Tension", "dimensions": ["Policy", "Environment"],
                                            "insight": "EU rules push green R&D"}]}
    s = rsr.normalize_stepic_final(final)["cross_dimensional_signals"][0]
    assert s["dimensions"] == "POLICY + ENVIRONMENT" and s["signal"] == "EU rules push green R&D"
    assert s["implication"] == "" and s["signal_type"] == "Tension"


def test_normalize_stepic_raw_unwraps_any_wrapper_name():
    rsr = _import_stepic_report()
    raw = {"policy": {"policy_dimension": {"details": {"regulatory_trend": "Mandatory testing",
                                                       "business_impact": ["Cost", "Audit"]}}},
           "society": {"concept": "C", "meta": {"source": "x"}}}
    out = rsr.normalize_stepic_raw(raw)
    assert out["policy"] == {"regulatory_trend": "Mandatory testing", "business_impact": ["Cost", "Audit"]}
    assert out["society"]["meta"] == {"source": "x"}          # dict ที่ไม่มีฟิลด์ของมิตินั้น = ไม่ใช่ตัวห่อ


def test_integrate_stepic_asks_for_reader_schema(monkeypatch):
    import types
    rsr = _import_stepic_report()
    calls = []

    def create(**kw):
        calls.append(kw)
        msg = types.SimpleNamespace(content='{"mega_trend_name": "M", "emerging_personas": []}')
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)], usage=None)

    fake = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
    monkeypatch.setattr(rsr.tf2, "client", fake)
    assert rsr.integrate_stepic({"society": {"concept": "C"}}, "beauty") == {"mega_trend_name": "M",
                                                                             "emerging_personas": []}
    prompt = calls[0]["messages"][1]["content"]
    for key in ('"value_driver"', '"channel_preference"', '"dimensions"', '"signal"', '"implication"'):
        assert key in prompt
    assert rsr.integrate_stepic({}, "beauty") == {} and len(calls) == 1


# ---------------------------------------------------------------------------
# common/market_overview.py - ภาพรวมตลาด + ข้อมูลเข้า STEPIC จากคะแนนการเติบโต (2026-10-01)
# ---------------------------------------------------------------------------

def _growth_clusters():
    def c(name, change, scores, grades):
        return {"trend": name, "forecast": {"change_pct": change} if change else None,
                **{f"score_y{h}": scores[h - 1] for h in range(1, 6)}, **{f"grade_y{h}": grades[h - 1] for h in range(1, 6)}}
    # 🆕 (2026-10-02) 5 ปี - ระยะสั้น = ปีที่ 2, ระยะยาว = ปีที่ 5
    return [c("Alpha", [14.0, 28.0, 40.0, 48.0, 60.0], [0.82, 0.73, 0.75, 0.76, 0.78], [4, 3, 3, 3, 3]),
            c("Beta", [6.0, 10.0, 11.0, 12.0, 13.0], [0.55, 0.34, 0.25, 0.20, 0.18], [3, 2, 2, 2, 1]),
            c("Gamma", [-1.0, 11.0, 15.0, 20.0, 26.0], [0.17, 0.36, 0.34, 0.33, 0.40], [1, 2, 2, 2, 2]),
            c("NoForecast", None, [0.5] * 5, [3] * 5)]


def test_market_snapshot_medians_counts_and_order():
    from common import market_overview as mo
    snap = mo.market_snapshot(_growth_clusters(), durability_scores=[66, 50, None, 83])
    assert snap["n_trends"] == 3                                        # เทรนด์ที่ไม่มีผลพยากรณ์ไม่นับ
    assert snap["median_change_pct"] == {"year_1": 6.0, "year_2": 11.0, "year_3": 15.0, "year_4": 20.0, "year_5": 26.0}
    assert snap["n_faster_than_market"] == {"year_1": 2, "year_2": 1, "year_3": 1, "year_4": 1, "year_5": 1}
    assert snap["share_growing_pct"]["year_1"] == 67 and snap["median_durability"] == 66.0
    assert [t["trend"] for t in snap["trends"]] == ["Alpha", "Gamma", "Beta"]   # คะแนนปี 2 มาก -> น้อย
    assert mo.market_snapshot([_growth_clusters()[3]]) is None


def test_market_labels_thresholds():
    """🆕 (2026-10-19) เกณฑ์ Strong / Moderate ตั้งเป็น % ต่อปีเฉลี่ย แล้วแปลงเป็นสะสมตามปีระยะสั้น (STRENGTH_FLOORS) - ทดสอบที่ขอบของค่าปัจจุบัน"""
    from common import market_overview as mo
    hi, lo = mo.STRENGTH_FLOORS
    for short, long_, durability, expected in [
            (hi, 25.0, 70, ("Strong", "Strengthening", "Long-term")),
            (round(hi - 0.1, 1), 24.9, 69.9, ("Moderate", "Stable", "Medium-term")),
            (lo, -24.9, 40, ("Moderate", "Stable", "Medium-term")),
            (round(lo - 0.1, 1), -25.0, 39.9, ("Weak", "Weakening", "Short-term"))]:
        snap = {"median_change_pct": {mo.SHORT_KEY: short, mo.LONG_KEY: long_}, "median_durability": durability}
        labels = mo.market_labels(snap)
        assert (labels["current_trend_strength"], labels["overall_direction"],
                labels["estimated_trend_duration"]) == expected, (short, long_, durability)


def test_strength_floors_keep_the_same_per_year_meaning_when_short_year_changes():
    """เกณฑ์เดิมตั้งไว้ที่ปีที่ 2 (+20% / +6% สะสม) = 9.54% / 2.96% ต่อปี - เปลี่ยนปีระยะสั้นแล้วป้ายต้องมีความหมายต่อปีเท่าเดิม"""
    from common import market_overview as mo
    floors = lambda year: tuple(round(((1 + p / 100) ** year - 1) * 100, 1) for p in mo.STRENGTH_PER_YEAR)   # noqa: E731
    assert floors(2) == (20.0, 6.0) and floors(3) == (31.4, 9.1)
    assert mo.STRENGTH_FLOORS == floors(mo.SHORT_YEAR)


def test_market_overview_summary_llm_or_numbers_fallback():
    from common import market_overview as mo
    snap = mo.market_snapshot(_growth_clusters(), [66, 50, 83])
    llm = mo.market_overview(snap, "  Search is rising.  ", "beauty")
    assert llm["summary"] == "Search is rising." and llm["summary_source"] == "llm" and llm["query"] == "beauty"
    short = snap["median_change_pct"][mo.SHORT_KEY]                                 # 🆕 (2026-10-19) ปีระยะสั้นจาก common/horizons.py
    assert llm["basis"] == {"short_year": mo.SHORT_YEAR, "long_year": mo.LONG_YEAR, "median_change_pct_short": short,
                            "median_change_pct_long": 26.0, "median_durability": 66.0, "n_trends": 3}
    fb = mo.market_overview(snap, None)
    assert fb["summary_source"] == "numbers" and f"{short:+.0f}%" in fb["summary"] and "1 of 3" in fb["summary"]
    assert f"year {mo.SHORT_YEAR}" in fb["summary"] and "year 2" not in fb["summary"]
    assert "faster" not in fb["summary"] and "year 5" in fb["summary"]
    assert "Alpha" in fb["summary"] and "z-score" not in fb["summary"].lower()
    assert mo.market_overview({**snap, "median_durability": None}, "x")["estimated_trend_duration"] is None


def test_stepic_growth_facts_has_growth_not_z_score_or_past_growth():
    import json
    from common import market_overview as mo
    clusters = _growth_clusters()
    keywords = [{"keyword": "a1", "cluster_name": "Alpha"}, {"keyword": "a2", "cluster_name": "Alpha"},
                {"keyword": "b1", "cluster_name": "Beta"}]
    longevity = {("Paper", "Alpha"): {"Longevity Score": 66, "Longevity Band": "likely_durable"}}
    snap = mo.market_snapshot(clusters, [66])
    facts = json.loads(mo.stepic_growth_facts(clusters, keywords, [{"stream": "Paper", "trend": "Alpha"}], longevity, snap))
    assert [t["trend"] for t in facts["trends"]] == ["Alpha"]                  # เฉพาะชุดที่ ⑪ คัด
    a = facts["trends"][0]
    assert a["keywords"] == ["a1", "a2"]
    assert a["expected_search_growth_pct_vs_last_12_months"] == {"year_1": 14.0, "year_2": 28.0, "year_3": 40.0,
                                                                 "year_4": 48.0, "year_5": 60.0}
    assert a["growth_vs_market"]["year_2"] == "above market median"       # 🆕 ไม่มีคำ faster/slower แล้ว
    assert "faster" not in json.dumps(facts) and "slower" not in json.dumps(facts)
    assert a["durability"] == {"longevity_score": 66, "band": "likely durable"}
    assert facts["market"]["median_expected_growth_pct"]["year_1"] == 6.0
    text = json.dumps(facts).lower()
    assert "z_delta" not in text and "z-score" not in text and "past_growth" not in text
    everything = json.loads(mo.stepic_growth_facts(clusters, keywords, None, {}, snap))
    assert [t["trend"] for t in everything["trends"]] == ["Alpha", "Beta", "Gamma"]
    assert everything["trends"][1]["durability"] == {"longevity_score": None, "band": None}


def test_write_market_summary_prompt_and_failures(monkeypatch):
    import types
    from common import market_overview as mo
    rsr = _import_stepic_report()
    calls = []

    def fake(content):
        def create(**kw):
            calls.append(kw)
            msg = types.SimpleNamespace(content=content)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)], usage=None)
        return types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))

    snap = mo.market_snapshot(_growth_clusters(), [66])
    monkeypatch.setattr(rsr.tf2, "client", fake('{"summary": " Interest grows. "}'))
    assert rsr.write_market_summary(snap, "beauty") == "Interest grows."
    prompt = calls[0]["messages"][1]["content"]
    assert "Alpha" in prompt and "median_expected_change_pct" in prompt and "Do not mention z-scores" in prompt
    monkeypatch.setattr(rsr.tf2, "client", fake("not json"))
    assert rsr.write_market_summary(snap, "beauty") is None
    monkeypatch.setattr(rsr.tf2, "client", fake('{"summary": ""}'))
    assert rsr.write_market_summary(snap, "beauty") is None


# ---------------------------------------------------------------------------
# common/trend_analysis.py - ข้อความวิเคราะห์ต่อเทรนด์จากโมเดลการเติบโต แทน Step 6-7 ของ ⑦ (2026-10-01)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("change,expected", [   # 🆕 (2026-10-02) ตัดสินจากปีระยะสั้นกับปีที่ 5 (ระยะยาว) · 🆕 (2026-10-19) ระยะสั้น = ปีที่ 3
    # เกณฑ์ปีระยะสั้น = STRENGTH_FLOORS[1] = +9.1% สะสมที่ปีที่ 3 (= 2.96% ต่อปี เท่ากับ +6% ที่ปีที่ 2 เดิม)
    ([14.0, 28.0, 40.0, 48.0, 60.0], "Growing"),
    ([1.0, 4.0, 8.0, 20.0, 30.0], "Emerging"),         # ปี 3 ยังไม่ถึง +9.1% แต่ปี 5 สูง = เร่งทีหลัง
    ([15.0, 20.0, 35.0, 30.0, 30.0], "Peaking"),       # โตแล้วแต่ปี 5 ไม่สูงกว่าปี 3
    ([2.0, 5.0, 8.0, 10.0, 12.0], "Stable"),
    ([-8.0, -12.0, -20.0, -25.0, -30.0], "Declining"),
    ([3.0, 6.0, 9.1, 20.0, 25.0], "Growing"),          # ขอบ: ปี 3 = +9.1 และปี 5 = +25 พอดี นับเป็นโต
    ([3.0, 5.9, 9.0, 20.0, 25.0], "Emerging"),
    ([2.0, 5.0, 8.0, 12.0, 24.9], "Stable"),
    ([-8.0, -12.0, -20.0, -25.0, -25.0], "Declining"), # ขอบ: ปี 5 = -25 พอดี
])
def test_trend_stage_rules(change, expected):
    from common import trend_analysis as ta
    assert ta.trend_stage(change) == expected


def test_seasonality_and_primary_driver():
    from common import trend_analysis as ta
    flat = [1.0] * 12
    sunny = [0.7, 0.8, 0.9, 1.0, 1.4, 1.5, 1.2, 1.0, 0.9, 0.8, 0.9, 0.9]
    assert ta.seasonality(None) is None and ta.seasonality([1.0] * 11) is None
    s = ta.seasonality(sunny)
    assert s == {"swing_pct": 80, "peak_months": ["May", "Jun"], "strong": True}
    assert ta.seasonality(flat)["strong"] is False
    assert ta.primary_driver([5.0, 10.0, 15.0, 20.0, 30.0], s) == "Organic Seasonality"          # ฤดูกาลชัดมาก่อน
    assert ta.primary_driver([5.0, 10.0, 15.0, 20.0, 30.0], ta.seasonality(flat)) == "Structural Growth"
    assert ta.primary_driver([1.0, 4.0, 8.0, 20.0, 30.0], None) == "Mixed/Uncertain"      # ปีระยะสั้น (ปี 3) ยังไม่ถึง +9.1%


def _trend_cluster(name="Alpha", change=(14.0, 28.0, 40.0, 48.0, 60.0), seasonal=None):
    return {"trend": name, "forecast": {"change_pct": list(change)},
            **{f"score_y{h}": s for h, s in zip(range(1, 6), (0.82, 0.73, 0.75, 0.76, 0.78))},
            "history": {"seasonal": seasonal}}


def test_trend_facts_labels_and_fields():
    from common import trend_analysis as ta
    row = {"Longevity Score": 66, "Longevity Band": "likely_durable", "Key Benefits": "clear skin", "Target": "teens"}
    f = ta.trend_facts(_trend_cluster(), ["a1", "a2"], row)
    assert f["trend_stage"] == "Growing" and f["primary_driver"] == "Structural Growth"
    assert f["estimated_duration"] == "Medium-term" and f["seasonality"] is None
    assert f["durability"] == {"longevity_score": 66, "band": "likely durable"}
    assert f["growth_vs_market"]["year_2"] == "above market median" and f["target_consumer"] == "teens"
    assert ta.trend_facts({"trend": "X", "forecast": None}, [], {}) is None
    assert ta.trend_facts(_trend_cluster(), [], None)["estimated_duration"] is None


def test_analysis_entry_keeps_valid_llm_text_and_replaces_wrong_numbers():
    from common import trend_analysis as ta
    f = ta.trend_facts(_trend_cluster(), ["a1", "a2"], {"Longevity Score": 66, "Key Benefits": "clear skin"})
    good = {"executive_summary": "Expected +14% in year 1 and 48% by year 3.",
            "consumer_intent_signal": "Shoppers want clear skin.",
            "driver_explanation": "Growth of 14% to 28% to 48.0%.",
            "risk_scenario_if_forecast_fails": "Demand may stall."}
    e = ta.analysis_entry(f, good)
    assert e["text_source"] == "llm" and e["executive_summary"] == good["executive_summary"]
    assert e["cluster_name"] == "Alpha" and e["keywords"] == ["a1", "a2"] and e["trend_stage"] == "Growing"
    bad = {**good, "executive_summary": "Search will explode 300% soon.", "driver_explanation": "  "}
    e = ta.analysis_entry(f, bad)
    assert e["text_source"] == "mixed" and "300%" not in e["executive_summary"]
    assert "+40% by year 3" in e["executive_summary"] and "+60% by year 5" in e["executive_summary"]   # ประโยคสำรอง (ปีระยะสั้น = 3)
    assert "year 2" not in e["executive_summary"]
    assert e["driver_explanation"] and e["consumer_intent_signal"] == "Shoppers want clear skin."
    none = ta.analysis_entry(f, None)
    assert none["text_source"] == "numbers" and "Consumers look for clear skin." == none["consumer_intent_signal"]
    assert "investment_signal" not in none and "confidence_level" not in none


def test_analysis_entry_seasonal_numbers_and_fallback_wording():
    from common import trend_analysis as ta
    sunny = [0.7, 0.8, 0.9, 1.0, 1.4, 1.5, 1.2, 1.0, 0.9, 0.8, 0.9, 0.9]
    f = ta.trend_facts(_trend_cluster("Sun", (4.0, 12.0, 15.0, 19.0, 22.0), sunny), ["spf"], {"Longevity Score": 48})
    assert f["seasonality"] == {"peak_months": ["May", "Jun"], "swing_pct": 80}
    assert f["primary_driver"] == "Organic Seasonality"
    assert ta.numbers_ok("Peaks in June with an 80% swing, +4% in year 1.", ta.allowed_numbers(f))
    assert not ta.numbers_ok("Up 81%.", ta.allowed_numbers(f))
    fb = ta.fallback_texts(f)
    assert "May and Jun" in fb["driver_explanation"] and "swing 80%" in fb["driver_explanation"]
    assert "Durability score 48/100" in fb["driver_explanation"]


def test_write_trend_analysis_prompt_retry_and_failure(monkeypatch):
    import types
    rsr = _import_stepic_report()
    seen = []

    def fake(*answers):
        queue = list(answers)

        def create(**kw):
            seen.append(kw)
            msg = types.SimpleNamespace(content=queue.pop(0) if len(queue) > 1 else queue[0])
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)], usage=None)
        return types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))

    from common import trend_analysis as ta
    facts = [ta.trend_facts(_trend_cluster(), ["a1"], {"Key Benefits": "clear skin"})]
    ok = '{"cluster_analysis": [{"cluster_name": "Alpha", "executive_summary": "S."}]}'
    monkeypatch.setattr(rsr.tf2, "client", fake("not json", ok))
    out = rsr.write_trend_analysis(facts, "beauty")
    assert out == {"Alpha": {"cluster_name": "Alpha", "executive_summary": "S."}} and len(seen) == 2   # ครั้งแรกพัง ลองซ้ำ
    prompt = seen[0]["messages"][1]["content"]
    assert "Alpha" in prompt and "clear skin" in prompt and "Do not mention z-scores" in prompt
    seen.clear()
    monkeypatch.setattr(rsr.tf2, "client", fake("not json"))
    assert rsr.write_trend_analysis(facts, "beauty") == {} and len(seen) == 2
