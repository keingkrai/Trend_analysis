# -*- coding: utf-8 -*-
"""
Unit test ของ ⑲ Phase 4 (market_synthesis.py) - หลักฐานและ LLM ปลอมทั้งหมด ไม่เรียก Bedrock

รัน: pytest main/tool/tests/test_market_synthesis.py -v
"""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase7_market_report"))

from market_synthesis import (SYNTH_DEFAULTS, SYSTEM_PROMPT, aggregate_by_factor, build_payload,  # noqa: E402
                              check_finding, excerpt, number_ok, parse_date, quote_in, select_passages, synthesize)

CFG = dict(SYNTH_DEFAULTS)
PERIOD = [2019, 2025]


@pytest.mark.parametrize("text,expected", [
    ("2024-03-05", date(2024, 3, 5)),
    ("Oct 7, 2565 BE", date(2022, 10, 7)),
    ("Mar 17, 2021", date(2021, 3, 17)),
    ("22 ต.ค. 2567", date(2024, 10, 22)),
    ("3 days ago", date(2026, 10, 12)),
    ("2 วันที่ผ่านมา", date(2026, 10, 12)),
    ("sometime", None), (None, None),
])
def test_parse_date(text, expected):
    assert parse_date(text, today=date(2026, 10, 12)) == expected


def test_excerpt_keeps_keyword_lines_or_intro():
    text = "intro line about the site\nMistine ปรับช่องทางขายสู่ออนไลน์\nเมนู\nอีกบรรทัดเกี่ยวกับ มิสทิน และตัวแทนขายตรง"
    assert excerpt(text, ["mistine", "มิสทิน"], 1000) == ("Mistine ปรับช่องทางขายสู่ออนไลน์\n"
                                                          "อีกบรรทัดเกี่ยวกับ มิสทิน และตัวแทนขายตรง")
    assert excerpt(text, ["nothing"], 20) == "intro line"           # ไม่เจอ -> ช่วงต้น (ครึ่งหนึ่งของเพดาน)
    assert excerpt(text, ["nothing"], 20, intro_fallback=False) == ""


def _q(level="brand"):
    return {"id": "q20", "level": level, "topic": "Mistine", "brand": "Mistine" if level == "brand" else None,
            "categories": ["Colour Cosmetics"], "question_en": "What is associated with Mistine 5.4% to 1.6%?",
            "facts": {"name_th": "มิสทิน", "by_category": [{"share_base": 5.4, "share_last": 1.6}]},
            "factor_hint": ["channel_shift"], "queries": [{"q": '"Mistine" Thailand makeup', "hl": "en", "gl": "th"}]}


RESULTS = [
    {"rid": "q20-r01", "domain": "news.th", "title": "Mistine shifts to online", "snippet": "Mistine moves online",
     "page_status": "ok", "page_date": "2024-05-01", "serp_date": None, "mentions_brand": True,
     "text": "menu\nMistine ลดการพึ่งพาตัวแทนขายตรง หันไปขายผ่าน TikTok Shop ในปี 2567 ยอดขายออนไลน์โต 40%"},
    {"rid": "q20-r02", "domain": "old.th", "title": "Mistine 2015", "snippet": "old news", "page_status": "ok",
     "page_date": "2015-01-01", "serp_date": None, "mentions_brand": True, "text": "Mistine in 2015"},
    {"rid": "q20-r03", "domain": "other.th", "title": "Unrelated", "snippet": "nothing", "page_status": "ok",
     "page_date": None, "serp_date": "Oct 7, 2565 BE", "mentions_brand": False, "text": "unrelated"},
    {"rid": "q20-r04", "domain": "blog.th", "title": "Mistine review", "snippet": "Mistine lipstick review 2023",
     "page_status": "error", "page_date": None, "serp_date": "3 วันที่ผ่านมา", "mentions_brand": True, "text": ""},
]


def test_select_passages_filters_old_and_off_brand():
    passages, dropped = select_passages(_q(), RESULTS, 2019, CFG)
    assert [p["rid"] for p in passages] == ["q20-r01", "q20-r04"]          # เนื้อหาเต็มก่อน snippet
    assert dropped == {"too_old": 1, "no_brand": 1, "shop_social": 0}


def test_select_passages_drops_shop_and_social_snippets():
    shop = {**RESULTS[3], "rid": "q20-r05", "link": "https://priceza.com/s/mistine", "snippet": "Mistine ราคา 99 บาท"}
    passages, dropped = select_passages(_q(), RESULTS + [shop], 2019, CFG)
    assert "q20-r05" not in [p["rid"] for p in passages] and dropped["shop_social"] == 1
    assert "menu" not in passages[0]["text"] and passages[0]["date"] == "2024-05-01"


@pytest.mark.parametrize("n,pool,ok", [
    (13.7, [13.71], True), (5.4, [5.4], True), (2024, [2567], True), (2567, [2024], True),
    (40, [40.0], True), (41, [40.0], False), (3.1, [3.14159], True), (3.2, [3.14], False),
])
def test_number_ok(n, pool, ok):
    assert number_ok(n, pool) is ok


def test_quote_in_ignores_thai_spacing_but_not_words():
    text = "Mistine ลดการพึ่งพาตัวแทนขายตรง หันไปขายผ่าน TikTok Shop"
    assert quote_in("ลดการพึ่งพา ตัวแทนขายตรง หันไปขายผ่าน", text)
    assert not quote_in("ลดการพึ่งพาตัวแทนขายส่ง หันไปขายผ่าน", text)


def _payload():
    passages, _ = select_passages(_q(), RESULTS, 2019, CFG)
    return build_payload(_q(), passages, PERIOD)


GOOD = {"factor": "distribution", "relevance": "direct", "statement_en": "Sources report Mistine relied less on direct-selling agents and sold "
        "more through TikTok Shop in 2024.", "statement_th": "แหล่งข่าวรายงานว่า Mistine พึ่งตัวแทนขายตรงน้อยลงและขายผ่าน "
        "TikTok Shop มากขึ้นในปี 2024", "evidence": ["q20-r01"], "quote": "ลดการพึ่งพาตัวแทนขายตรง หันไปขายผ่าน TikTok Shop"}


def test_check_finding_accepts_good_and_converts_be_year():
    ok, why = check_finding(GOOD, _payload())
    assert why is None and ok["factor"] == "distribution"


@pytest.mark.parametrize("change,reason", [
    ({"factor": "made_up"}, "factor not allowed"),
    ({"factor": "premium_shift"}, "factor not allowed"),                   # ไม่อยู่ใน hint ของคำถามนี้
    ({"relevance": "strong"}, "bad relevance"),
    ({"relevance": None}, "bad relevance"),
    ({"evidence": ["q20-r09"]}, "unknown rid"),
    ({"evidence": ["q20-r02"]}, "unknown rid"),                            # ถูกตัดเพราะเก่า -> ไม่ได้ส่งให้ LLM
    ({"quote": "Mistine เป็นผู้นำตลาดเครื่องสำอางไทย"}, "quote not found"),
    ({"statement_en": "Mistine sales online grew 55% in 2024."}, "number not in facts"),
    ({"statement_en": "Mistine lost to online brands."}, "winner/loser"),
    ({"statement_th": "Mistine moved online"}, "wrong language"),
    ({"statement_en": "Mistine ย้ายไปออนไลน์"}, "wrong language"),
    ({"statement_en": "Mistine momentum moved online."}, "banned word"),
])
def test_check_finding_rejections(change, reason):
    ok, why = check_finding({**GOOD, **change}, _payload())
    assert ok is None and why.startswith(reason)


def test_numbers_from_facts_are_allowed():
    ok, _ = check_finding({**GOOD, "statement_en": "Mistine share went from 5.4% to 1.6% while it moved online."},
                          _payload())
    assert ok


def test_system_prompt_formats():
    assert "At most 5 findings" in SYSTEM_PROMPT.format(max_findings=5)


def _evidence():
    return [{"id": "q20", "results": RESULTS}]


def test_synthesize_retries_then_caches():
    calls = []

    def llm(system, user, max_tokens=0):
        calls.append(user)
        if len(calls) == 1:                         # ครั้งแรก: finding ไม่ผ่าน (quote แต่งเอง)
            return json.dumps({"findings": [{**GOOD, "quote": "ประโยคที่ไม่มีอยู่จริงในหลักฐานเลย"}]})
        return json.dumps({"findings": [GOOD]})

    cache = {}
    res = synthesize([_q()], _evidence(), PERIOD, cache, CFG, llm_call=llm, log=lambda *_: None)
    assert len(calls) == 2 and res["q20"]["status"] == "ok" and len(res["q20"]["findings"]) == 1
    assert res["q20"]["rejected"] == ["quote not found in cited passages"]
    res2 = synthesize([_q()], _evidence(), PERIOD, cache, CFG, llm_call=llm, log=lambda *_: None)
    assert len(calls) == 2 and res2["q20"]["from_cache"]


def test_synthesize_empty_answer_is_no_evidence_and_no_passages_skips_llm():
    res = synthesize([_q()], _evidence(), PERIOD, {}, CFG, llm_call=lambda *a, **k: '{"findings": []}',
                     log=lambda *_: None)
    assert res["q20"]["status"] == "no_evidence"
    called = []
    res = synthesize([_q()], [{"id": "q20", "results": [RESULTS[1]]}], PERIOD, {}, CFG,
                     llm_call=lambda *a, **k: called.append(1), log=lambda *_: None)
    assert res["q20"]["status"] == "no_evidence" and not called          # หลักฐานเก่าหมด = ไม่ถาม LLM


def test_aggregate_by_factor_counts_sources_and_sorts_brands():
    results = {"q20": {"findings": [GOOD], "passages": {"q20-r01": {"source": "news.th"}}},
               "q18": {"findings": [{**GOOD, "evidence": ["q18-r01"], "relevance": "background"}],
                       "passages": {"q18-r01": {"source": "a.th"}}}}
    qs = [{**_q(), "id": "q20"}, {**_q(), "id": "q18", "brand": "La Roche-Posay", "categories": ["Skin Care"]}]
    agg = aggregate_by_factor(qs, results)
    assert agg["distribution"]["brands"] == ["La Roche-Posay", "Mistine"]
    assert agg["distribution"]["n_sources"] == 2 and agg["distribution"]["n_findings"] == 2
    assert agg["distribution"]["n_direct"] == 1
