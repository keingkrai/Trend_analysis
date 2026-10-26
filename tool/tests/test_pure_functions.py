# -*- coding: utf-8 -*-
"""
Unit test ของฟังก์ชัน pure ที่ audit (m4) ระบุชื่อตรงๆ ว่าไม่มีเทสเลย: compute_longevity,
aggregate_forecast (aggregate_to_category_level/aggregate_to_overall_level), compute_rank_score

"pure function" = input เดียวกันต้องได้ output เดียวกันเสมอ ไม่มี side effect/สุ่ม/เรียก API - 3 ตัวนี้
ทำหน้าที่ "คำนวณคะแนนจาก verdict ที่ตัดสินไว้แล้ว" ซึ่งเป็นหลักการหลักของโปรเจกต์นี้ (LLM ให้ verdict,
โค้ดคำนวณคะแนน ไม่ให้ LLM คิดเลขเอง) - จึงสำคัญที่สุดที่ต้องเทสได้แบบไม่ต้องยิง API

รัน: pytest tool/tests/test_pure_functions.py -v
"""
import sys
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "phase2_three_streams")))
sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "phase2_three_streams" / "social")))

import numpy as np
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


def test_compute_rank_score_positive_z_delta_gets_stream_bonus():
    single = compute_rank_score(10, [10, 5], stream_count=1, z_delta=0.5)
    confirmed = compute_rank_score(10, [10, 5], stream_count=2, z_delta=0.5)
    assert confirmed["score"] > single["score"]
    assert confirmed["score"] == pytest.approx(0.5 * 1.1)


def test_compute_rank_score_negative_z_delta_not_amplified_by_stream_bonus():
    """🆕 (2026-09-12, audit M5) เดิม score = z_delta * bonus ตรงๆ ทำให้เทรนด์ขาลงที่ยืนยันข้ามสายยิ่ง
    ติดลบมากขึ้น (-0.5 -> -0.55) - regression test กันกลับไปพังอีก: เทรนด์ขาลงต้องได้คะแนนเท่าเดิมไม่ว่า
    จะยืนยันกี่สาย"""
    single = compute_rank_score(10, [10, 5], stream_count=1, z_delta=-0.5)
    confirmed = compute_rank_score(10, [10, 5], stream_count=3, z_delta=-0.5)
    assert single["score"] == confirmed["score"] == -0.5


def test_compute_rank_score_preliminary_mode_when_no_z_delta():
    result = compute_rank_score(10, [10, 5], stream_count=2, z_delta=None)
    assert result["mode"].startswith("preliminary")
    assert result["score"] == pytest.approx(1.0 * 1.2)  # normalized_size=1.0 * bonus (1+0.2*(2-1))


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


# ---------------------------------------------------------------------------
# สำเนาผลพยากรณ์เฉพาะ Top N (⑪) - 🆕 (2026-09-16)
# ---------------------------------------------------------------------------

def _import_highlights_module():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3_supply_layer"))
    import trend_highlights
    return trend_highlights


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
    import brand_coverage as rbc

    assert rbc.display_trend_rank({"trend_top_rank": 10, "trend_overall_rank": 11}) == 10
    assert rbc.display_trend_rank({"trend_overall_rank": 11}) == 11  # ผลรอบเก่าที่ยังไม่มี top rank
    row = {"trend_name": "High-Efficiency Sun", "stream": "Social", "trend_overall_rank": 11, "trend_top_rank": 10,
           "brand_best_product": "P", "brand_best_score": 0.3, "match_reason": "r",
           "brand_best_rank_vs_market": 5, "brand_best_percentile_vs_market": 99,
           "brand_n_skus_considered": 3, "tier": "t", "market_best_product": "m", "market_best_score": 0.4}
    md = rbc.build_brand_section_markdown("Srichand", 64, 10622, {"k": row})
    assert "| High-Efficiency Sun | #10 | Social |" in md and "#11" not in md
    assert "อันดับเทรนด์ (⑥)" not in md


# ---------------------------------------------------------------------------
# SERPAPI_KEY หลายคีย์ (.env ของ GI_CH) - 🆕 (2026-09-26)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ('["k1", "k2"]', ["k1", "k2"]),
    ("k1,k2", ["k1", "k2"]),
    ("k1", ["k1"]),
    ('"k1", "k2"', ["k1", "k2"]),
    ("", []),
    (None, []),
    ("[", ["["]),  # รายการที่ไม่ครบ (เช่นแบ่งหลายบรรทัดใน .env) ไม่ทำให้พัง - ได้ค่าดิบกลับไป
])
def test_parse_serpapi_keys(raw, expected):
    from common.bootstrap import parse_serpapi_keys
    assert parse_serpapi_keys(raw) == expected


# ---------------------------------------------------------------------------
# ⑬ สินค้านอกแคตตาล็อก Watsons (--products) - 🆕 (2026-09-26)
# ---------------------------------------------------------------------------

def _brand_coverage_module():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3_supply_layer"))
    import brand_coverage
    return brand_coverage


def test_rank_if_inserted_counts_market_products_scoring_higher():
    rbc = _brand_coverage_module()
    market = np.sort(np.array([0.1, 0.5, 0.9]))
    assert rbc.rank_if_inserted(market, 0.95) == 1
    assert rbc.rank_if_inserted(market, 0.9) == 1   # คะแนนเท่ากัน = อันดับเดียวกัน (นับเฉพาะตัวที่สูงกว่า)
    assert rbc.rank_if_inserted(market, 0.7) == 2
    assert rbc.rank_if_inserted(market, 0.0) == 4


def test_compute_coverage_ranks_watsons_and_external_products_against_the_same_market():
    rbc = _brand_coverage_module()
    market_df = pd.DataFrame({"brand": ["A", "B", "Mine"], "product_name": ["a1", "b1", "m1"],
                              "sale_price_thb": ["1,200.00", None, "99"]}, index=[10, 11, 12])
    market_vecs = np.array([[1.0, 0.0], [0.6, 0.8], [0.0, 1.0]])
    trends = ({"S::T": np.array([1.0, 0.0])}, {"S::T": "T"}, {"S::T": "S"}, {"S::T": {"trend": "T"}})
    watsons_item = {"row": market_df.loc[12], "pos": 2}
    external = {"row": pd.Series({"product_name": "x1", "sale_price_thb": "250", "Category": "Skincare"}),
                "pos": None, "vec": np.array([0.8, 0.6]), "extra": {"platform": "Shopee", "image_url": None}}

    report = rbc.compute_coverage(market_df, [10, 11, 12], market_vecs, [watsons_item, external], trends,
                                  {("S", "T"): 4}, {("S", "T"): 1}, reason_fn=lambda profile, row: "why")
    r = report["S::T"]
    top = r["brand_top_matches"]
    # x1 (cos 0.8) ชนะ m1 (cos 0) - แทรกเข้าตลาดได้อันดับ 2 (a1 = 1.0 สูงกว่า, b1 = 0.6 ต่ำกว่า)
    assert [m["product_name"] for m in top] == ["x1", "m1"]
    assert top[0]["rank_vs_market"] == 2 and top[0]["platform"] == "Shopee" and top[0]["sale_price_thb"] == 250.0
    assert top[0]["category"] == "Skincare" and top[0]["match_reason"] == "why"
    assert top[1]["rank_vs_market"] == 3  # m1 อยู่ในตลาดเอง: อันดับตามตำแหน่งจริง
    assert r["brand_best_product"] == "x1" and r["brand_best_rank_vs_market"] == 2
    assert r["brand_best_percentile_vs_market"] == round((3 - 1) / 3 * 100)
    assert r["market_best_product"] == "A - a1" and r["brand_n_skus_considered"] == 2
    assert r["trend_overall_rank"] == 4 and r["trend_top_rank"] == 1


def test_load_external_products_drops_blank_names_and_keeps_the_richest_duplicate(tmp_path):
    rbc = _brand_coverage_module()
    path = tmp_path / "p.csv"
    pd.DataFrame({"product_name": ["Serum", "Serum", "", "Cream"],
                  "Key_Benefits": [None, "hydrating barrier repair", "x", "moisture"],
                  "platform": ["Lazada", "Shopee", "Shopee", "Konvy"]}).to_csv(path, index=False)
    df = rbc.load_external_products(path)
    assert list(df["product_name"]) == ["Serum", "Cream"]
    assert df.loc[0, "platform"] == "Shopee"  # แถวที่มีข้อความให้ embed มากกว่า


def test_embed_external_products_caches_by_text(tmp_path, monkeypatch):
    rbc = _brand_coverage_module()
    monkeypatch.setattr(rbc, "EXTERNAL_CHECKPOINT_PATH", tmp_path / "ext.pkl")
    df = pd.DataFrame({"product_name": ["Serum", "Cream"], "Key_Benefits": ["hydrating", "moisture"]})
    calls = []
    fake = lambda text: calls.append(text) or np.array([len(text), 1.0])  # noqa: E731
    first = rbc.embed_external_products(df, embed=fake)
    second = rbc.embed_external_products(df, embed=fake)
    assert len(calls) == 2 and set(first) == {0, 1}
    assert all(np.array_equal(first[i], second[i]) for i in first)


def test_external_portfolio_matches_brand_data_shape():
    rbc = _brand_coverage_module()
    df = pd.DataFrame({"sale_price_thb": ["100", "1,000.00", None], "Sub_category": ["Face Serum", "Face Serum", None]})
    p = rbc.external_portfolio(df)
    assert p == {"n_skus": 3, "top_subcategories": [{"name": "Face Serum", "n": 2}],
                 "price_min": 100.0, "price_median": 550.0, "price_max": 1000.0}


# ---------------------------------------------------------------------------
# STEPIC: LLM ตอบคนละโครงแต่ละรอบ (common/stepic_shape.py) - 🆕 (2026-09-26)
# ---------------------------------------------------------------------------

# โครงจริงของ 2 รอบ (ตัดข้อความให้สั้น)
STEPIC_082438 = {
    "technology": {"dimension": "TECHNOLOGY", "analysis": {"core_technology": "Bio delivery", "innovation_driver": "Stability",
                                                           "adoption_stage": "Early"}},
    "industry": {"concept": "Bio-Convergent", "information": "info", "strategic_positioning": {"winning_strategy": "Clinical"},
                 "market_structure": {"transformation": "t", "channel_shift": "c"}},
    "creativity": {"creativity_analysis": {"brand_expression": "Bio-Vector", "product_innovation": "NADES"}},
}
STEPIC_111455 = {
    "technology": {"trend_analysis": {"focus_trend": "bpc", "dimension": "TECHNOLOGY",
                                      "analysis": {"core_technology": "Transdermal", "innovation_driver": "Barrier",
                                                   "adoption_stage": "Growth"}}},
    "industry": {"market_structure": {"concept": "Convergence", "information": "channels"},
                 "strategic_positioning": {"concept": "Science-Backed", "information": "safety"},
                 "investment_signal": {"concept": "Capital", "information": "delivery tech"}},
    "creativity": {"concept": "c", "brand_expression": "Visible science", "product_innovation": "Sensory"},
}


@pytest.mark.parametrize("raw, core", [(STEPIC_082438, "Bio delivery"), (STEPIC_111455, "Transdermal")])
def test_stepic_technology_is_found_however_it_is_wrapped(raw, core):
    from common.stepic_shape import normalize_stepic, stepic_for_report
    assert normalize_stepic(raw)["technology"]["core_technology"] == core
    report = stepic_for_report(raw)
    assert report["technology"]["core_technology"] == core and report["technology"]["adoption_stage"]
    assert "society" not in report  # มิติที่ไม่มีไม่ใส่ (ตัวเขียนรายงานข้ามมิติที่ว่างอยู่แล้ว)


def test_stepic_report_fields_are_text_not_dicts():
    from common.stepic_shape import stepic_for_report
    industry = stepic_for_report(STEPIC_111455)["industry"]
    assert industry["market_structure"] == "Convergence: channels"
    assert industry["strategic_positioning"] == "Science-Backed: safety"
    assert stepic_for_report(STEPIC_082438)["industry"]["market_structure"] == "transformation: t; channel shift: c"
    assert stepic_for_report(STEPIC_082438)["creativity"]["brand_expression"] == "Bio-Vector"


def test_stepic_shape_ignores_missing_or_bad_input():
    from common.stepic_shape import as_text, normalize_stepic
    assert normalize_stepic(None)["technology"] == {} and normalize_stepic({"policy": "text"})["policy"] == {}
    assert as_text(None) == "" and as_text(["a", "", {"concept": "b"}]) == "a; b"


def test_signals_and_personas_read_either_field_name():
    from common.stepic_shape import normalize_personas, normalize_signals
    assert normalize_signals([{"dimensions": "SOCIETY + INDUSTRY", "signal": "s", "implication": "i"},
                              {"convergence_pattern": "SOCIETY x TECHNOLOGY", "signal": "s2"}, "junk"]) == [
        {"dimensions": "SOCIETY + INDUSTRY", "signal": "s", "implication": "i"},
        {"dimensions": "SOCIETY x TECHNOLOGY", "signal": "s2", "implication": ""}]
    got = normalize_personas([{"name": "A", "description": "d", "motivations": ["Fortify", "Transparency"]},
                              {"name": "B", "value_driver": "v", "channel_preference": "TikTok"}])
    assert got[0]["value_driver"] == "Fortify; Transparency" and got[0]["channel_preference"] == ""
    assert got[1] == {"name": "B", "description": "", "value_driver": "v", "channel_preference": "TikTok"}
