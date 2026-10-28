# -*- coding: utf-8 -*-
"""
🆕 (2026-10-28) ฐานจับคู่สินค้า "ความต้องการความงามที่ AI อนุมาน" ของเทรนด์สาย Search (beauty_need) - ฟังก์ชันล้วน ไม่เรียก API
เหตุ: เทรนด์ที่คำค้นไม่ใช่เรื่องความงาม (มาราธอน/จักรยาน, ยาลดน้ำหนัก) ได้สินค้าที่ไม่เกี่ยวเลยเมื่อจับคู่ด้วยข้อความจากคำค้นอย่างเดียว
(ทดลองกับรอบ 164405: ใช้ความต้องการที่ AI อนุมานอย่างเดียวได้สินค้าตรงหมวดแทบทุกเทรนด์ แต่ Daily Skincare ได้แปรงแต่งหน้า - ต่อท้ายด้วยข้อความจากคำค้นแก้ได้)

รัน: pytest main/tool/tests/test_need_matching.py -v
"""
import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TOOL_DIR = TESTS_DIR.parent
for _p in (TOOL_DIR, TOOL_DIR / "phase3_supply_layer"):
    sys.path.insert(0, str(_p))

import pytest  # noqa: E402

import extract_trend_highlights as eth  # noqa: E402
import highlight_evidence as he  # noqa: E402
import match_supply  # noqa: E402
import trend_category as tc  # noqa: E402
from common.match_quality import match_basis, need_text  # noqa: E402

CLUSTER = {"stream": "Search", "Trend Name": "Active Lifestyle", "Key Benefits": "sweat resistance, water resistance",
           "Product Keywords": "sport sunscreen, sweat-proof deodorant, sport sunscreen", "Link Paths": ["Activities & lifestyle"],
           "Product Categories": ["Deodorants", "Sun Care"],
           "Source Themes": [{"category": "Hobbies", "theme": "Running", "need": "กันแดดกันเหงื่อ / กันเหงื่อ", "evidence": ["marathon"]},
                             {"category": "News", "theme": "Shoes", "need": "กันเหงื่อ", "evidence": []}]}
NEED = he.beauty_need(CLUSTER)


@pytest.fixture(autouse=True)
def _default_basis(monkeypatch):
    monkeypatch.delenv("TREND_MATCH_BASIS", raising=False)
    monkeypatch.delenv("TREND_MATCH_QUOTES", raising=False)


def _profile(**over):
    base = {"trend": "Active Lifestyle", "trend_type": "สินค้า", "attribute": "ข้อมูลไม่พอ", "functional_consequence": "หาแผนฝึกวิ่ง",
            "psychosocial_consequence": "ข้อมูลไม่พอ", "job_to_be_done": "ข้อมูลไม่พอ", "point_of_difference": "ข้อมูลไม่พอ",
            "point_of_parity": "ข้อมูลไม่พอ", "evidence": {"functional_consequence": ["running plans for beginners"]}, "beauty_need": NEED}
    return {**base, **over}


def test_beauty_need_is_taken_from_the_stream_row_deduplicated_and_marked_as_ai_inferred():
    assert NEED["source"] == "ai_inferred" and NEED["product_keywords"] == ["sport sunscreen", "sweat-proof deodorant"]
    assert NEED["key_benefits"] == "sweat resistance, water resistance" and NEED["needs_th"] == ["กันแดดกันเหงื่อ", "กันเหงื่อ"]
    assert NEED["link_paths"] == ["Activities & lifestyle"] and NEED["product_categories"] == ["Deodorants", "Sun Care"]
    assert he.beauty_need({"Trend Name": "x"}) is None and he.beauty_need(None) is None            # ไม่มีทั้งชนิดสินค้าและประโยชน์ = ไม่มี
    assert he.beauty_need({"Key Benefits": "firming"})["product_keywords"] == []                    # มีแค่ประโยชน์ก็ได้


def test_matching_text_starts_from_the_need_then_adds_what_the_searches_show():
    text = match_supply.build_trend_matchable_text(_profile())
    assert text.startswith("sport sunscreen, sweat-proof deodorant. sweat resistance, water resistance ")
    assert text.endswith("หาแผนฝึกวิ่ง Searches: running plans for beginners")
    assert match_basis(_profile()) == "need" and need_text(_profile()) == "sport sunscreen, sweat-proof deodorant. sweat resistance, water resistance"


def test_a_trend_with_nothing_from_the_searches_is_still_matchable_through_the_need():
    nothing = _profile(functional_consequence="ข้อมูลไม่พอ", evidence={})
    assert match_supply.build_trend_matchable_text(nothing) == "sport sunscreen, sweat-proof deodorant. sweat resistance, water resistance"


def test_switch_and_legacy_profiles_keep_the_old_evidence_only_text(monkeypatch):
    old = "หาแผนฝึกวิ่ง Searches: running plans for beginners"
    monkeypatch.setenv("TREND_MATCH_BASIS", "evidence")
    assert match_supply.build_trend_matchable_text(_profile()) == old and match_basis(_profile()) == "evidence"
    monkeypatch.delenv("TREND_MATCH_BASIS")
    legacy = {k: v for k, v in _profile().items() if k != "beauty_need"}                              # โปรไฟล์ 3 สายเดิม / รอบก่อนวันนี้
    assert match_supply.build_trend_matchable_text(legacy) == old and match_basis(legacy) == "evidence"
    empty = _profile(functional_consequence="ข้อมูลไม่พอ", evidence={}, beauty_need=None)
    assert match_supply.build_trend_matchable_text(empty) == ""                                       # ไม่มีความต้องการ = ⑪ ยังตัดเทรนด์ได้เหมือนเดิม


def test_main_category_decision_sees_the_need_and_is_not_served_from_an_old_cache_entry():
    plain = {k: v for k, v in _profile().items() if k != "beauty_need"}
    assert "beauty need (inferred by an AI from the searches): sport sunscreen" in tc.trend_block(_profile())
    assert "beauty need" not in tc.trend_block(plain)
    assert tc.cache_key(_profile(), 100) != tc.cache_key(plain, 100)                                  # เริ่มใช้ความต้องการ = ตัดสินหมวดใหม่
    assert tc.cache_key(plain, 100) == tc.cache_key({**plain, "beauty_need": None}, 100)              # เทรนด์เดิมไม่มี = คีย์เดิม


def test_reusing_this_runs_profiles_skips_the_empty_stubs_so_they_are_asked_again(tmp_path):
    real = {"trend": "A", "stream": "Search", "trend_type": "สินค้า", "functional_consequence": "แก้ผมฟู", "evidence": {}}
    (tmp_path / eth.HIGHLIGHTS_FILE).write_text(json.dumps({
        "profiles": [real], "extra_profiles": [],
        "checked_trends": [{"stream": "Search", "trend": "B", "matchable": False, "reason": eth.REASON_NO_TEXT}],
        "excluded_trends": [{"stream": "Search", "trend": "B", "matchable": False, "reason": eth.REASON_NO_TEXT}]}), encoding="utf-8")
    with_stubs = eth.load_reusable_profiles(tmp_path)
    assert set(with_stubs) == {("Search", "A"), ("Search", "B")}                                      # โหมดอัปเดตรอบเดิม: เหมือนเดิม
    assert set(eth.load_reusable_profiles(tmp_path, include_stubs=False)) == {("Search", "A")}        # ใช้โปรไฟล์ของรอบนี้ซ้ำ: เฉพาะที่มีข้อมูลจริง


def test_clusters_of_the_search_stream_carry_the_product_keywords(tmp_path, monkeypatch):
    stream = tmp_path / "phase2_search_stream_result.json"
    stream.write_text(json.dumps({
        "trends": [{"Trend Name": "A", "Key Benefits": "firming"}, {"Trend Name": "B"}],
        "keywords": [{"Trend Name": "A", "Product_Search_Keywords": "firming lotion, serum"}]}), encoding="utf-8")
    monkeypatch.setattr(eth, "present_streams", lambda outputs: {eth.SEARCH_STREAM: stream})
    a, b = eth.load_all_clusters()
    assert a["Product Keywords"] == "firming lotion, serum" and "Product Keywords" not in b
    assert he.beauty_need(a)["product_keywords"] == ["firming lotion", "serum"]
