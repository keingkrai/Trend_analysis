# -*- coding: utf-8 -*-
"""
🆕 (2026-10-28) ส่วนเจาะรายหมวดของ Google (phase6_pdf_report/category_dive.py ข้อมูล + dive_text.py ประโยคอธิบาย + templates/_dive_pages.j2)
ข้อมูลมาจากโฟลเดอร์รอบปลอม: ตรวจการจัดหัวข้อ/เรียงตามกฎ/แบ่งหน้า, ตัวตรวจประโยคอธิบาย (ห้ามเลข/คำค้น/เหตุผลที่ไม่มีในคำค้น), cache + ถามซ้ำ,
และเล่มแยก 2 ภาษา (ส่วนที่ 2 ในรายงานหลักทดสอบที่ test_pdf_report.py) - ไม่เรียก API/LLM จริง

รัน: pytest main/tool/tests/test_category_dive.py -v
"""
import json
import sys
from datetime import datetime
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TOOL_DIR = TESTS_DIR.parent
for _p in (TOOL_DIR, TOOL_DIR / "phase6_pdf_report"):
    sys.path.insert(0, str(_p))

import pytest  # noqa: E402

import category_dive as cd  # noqa: E402
import dive_text as dt  # noqa: E402
from common.streams import SEARCH_STREAM, STREAM_FILES  # noqa: E402


def _q(text, geos, value=100, norm=None):
    return {"query_norm": norm or text.lower(), "query": text, "geos": geos, "max_value": value, "value": f"+{value}%" if value < 5000 else "Breakout"}


def _themes(path, names_ids, queries):
    path.write_text(json.dumps({"themes": [{"name": n, "ids": ids} for n, ids in names_ids], "queries": queries}), encoding="utf-8")


@pytest.fixture
def run(tmp_path):
    work = tmp_path / "search_stream_work"
    (work / "themes").mkdir(parents=True)
    (work / "links").mkdir()
    health = [_q("best sunscreen for kids", "TH,WW", 300), _q("best sunscreen", "WW", 200), _q("what causes hair loss", "TH", 150),
              _q("state welfare card 2569", "TH", 5000), _q("flu symptoms", "WW", 90), _q("//spam.replit.app/", "TH", 80),
              _q("tinted sunscreen", "TH,WW", 120)]
    _themes(work / "themes" / "Health.json", [("Sunscreen", [1, 2, 7]), ("Hair", [3]), ("Welfare", [4]), ("Flu", [5]), ("Spam", [6]), ("Other", [5])], health)
    (work / "links" / "Health.json").write_text(json.dumps([
        {"theme": "Sunscreen", "path": 1, "cats": ["Sun Care", "Skin Care"], "need": "กันแดด", "reason": "ไม่แสดง",
         "evidence": ["best sunscreen for kids", "invented quote", "//spam.replit.app/"]},
        {"theme": "Hair", "path": 3, "cats": ["Hair Care"], "evidence": ["what causes hair loss"]},
        {"theme": "Welfare", "path": 0}, {"theme": "Flu", "path": 0}, {"theme": "Spam", "path": 0}]), encoding="utf-8")
    sports = [_q("world cup 2026", "WW", 500), _q("marathon bangkok", "TH", 400)]
    _themes(work / "themes" / "Sports.json", [("Matches", [1]), ("Running", [2])], sports)
    (work / "links" / "Sports.json").write_text(json.dumps([{"theme": "Matches", "path": 0}, {"theme": "Running", "path": 0}]), encoding="utf-8")
    (tmp_path / STREAM_FILES[SEARCH_STREAM]).write_text(json.dumps({
        "search_meta": {"places": ["TH", "WW"], "month": "2026-10", "n_trends": 2},
        "trends": [{"Trend Name": "Sun Care", "Source Themes": [{"category": "Health", "theme": "Sunscreen", "evidence": ["best sunscreen"]}]},
                   {"Trend Name": "Dropped", "Source Themes": [{"category": "Health", "theme": "Hair", "evidence": ["what causes hair loss"]}]}]}),
        encoding="utf-8")
    return tmp_path


TRENDS = [{"name": "Sun Care", "display_name": "Sun Care Plain", "rank": 3}]


def test_topics_are_counted_from_the_data_and_sorted_by_the_selection_rule(run):
    d = cd.load_dive(run, TRENDS)
    assert d["n_categories"] == 2 and d["n_topics"] == 6 and d["n_searches"] == 9      # หัวข้อ "Other" และหัวข้อที่มีแต่ลิงก์ไม่นับ
    health = next(c for c in d["categories"] if c["name"] == "Health")
    assert (health["n"], health["n_themes"], health["n_linked"], health["full"]) == (7, 4, 2, False)
    assert [t["key"] for t in health["linked"]] == ["Sunscreen", "Hair"]                # ขึ้น 2 พื้นที่ > 1 พื้นที่ (กฎ: จำนวนพื้นที่ > มีไทย > จำนวนคำค้น)
    sun = health["linked"][0]
    assert (sun["n"], sun["where"], sun["has_th"]) == (3, "both", True) and sun["link"]["cats"] == ["Sun Care", "Skin Care"]
    assert [t["key"] for t in health["others"]] == ["Welfare", "Flu"]                  # ไม่โยง เรียงตามกฎเดียวกัน
    welfare = health["others"][0]
    assert welfare["breakout"] == 1 and welfare["breakout_share"] == 1.0 and welfare["where"] == "th"


def test_link_evidence_must_be_real_searches_of_the_topic_and_ai_wording_is_not_carried(run):
    d = cd.load_dive(run, TRENDS)
    sun = next(c for c in d["categories"] if c["name"] == "Health")["linked"][0]
    assert sun["link"]["evidence"] == ["best sunscreen for kids"]                      # คำที่ AI แต่งขึ้น / ลิงก์สแปม ถูกตัด
    assert "need" not in json.dumps(d) and "ไม่แสดง" not in json.dumps(d)               # ไม่เอาข้อความตีความ (need/reason) มาแสดง
    assert all("replit" not in s for c in d["categories"] for t in c["linked"] + c["others"] for s in t["searches"])   # คำค้นแบบ URL ไม่เป็นหลักฐาน


def test_report_trends_are_tagged_only_when_the_report_shows_them(run):
    d = cd.load_dive(run, TRENDS)
    health = next(c for c in d["categories"] if c["name"] == "Health")
    assert [(x["rank"], x["display_name"]) for x in health["linked"][0]["trends"]] == [(3, "Sun Care Plain")]
    assert health["linked"][1]["trends"] == [] and health["trend_ranks"] == [3]        # "Dropped" ไม่อยู่ในรายงานหลัก -> ไม่ติดป้าย
    assert cd.load_dive(run)["categories"][0]["trend_ranks"] == []                      # ไม่ส่งเทรนด์ = ไม่มีป้าย


def test_overview_numbers_and_pages(run):
    d = cd.load_dive(run, TRENDS)
    assert d["linked_pct"] == round(d["n_linked_searches"] / d["n_searches"] * 100, 1) and d["n_linked_searches"] == 4   # 3 (กันแดด) + 1 (ผมร่วง)
    assert d["none_linked"] == ["Sports"] and [c["name"] for c in d["categories"]] == ["Health", "Sports"]
    sports = d["categories"][1]
    assert sports["n_linked"] == 0 and sports["others"] == []                            # หมวดที่ไม่มีหัวข้อโยง: ไม่มีหน้า ไม่ต้องอธิบาย
    assert d["places"] == ["TH", "WW"] and "pages" not in d                                # หน้าคำนวณตอนจัดหน้า (paginate) ไม่เก็บใน dive
    assert [(p["full"], p["label"], [c["name"] for c in p["cats"]]) for p in cd.paginate(d)] == [(False, "Categories Health", ["Health"])]


def test_big_categories_get_a_full_page_and_small_ones_share_a_page():
    def cat(name, linked, full):
        return {"name": name, "n_linked": linked, "full": full}
    cats = [cat("A", 9, True), cat("B", 2, False), cat("C", 1, False), cat("D", 1, False), cat("E", 6, True), cat("F", 0, False)]
    pages = cd.paginate({"categories": cats})                                              # F ไม่มีหัวข้อโยง = ไม่มีหน้า
    assert [(p["full"], [c["name"] for c in p["cats"]]) for p in pages] == [(True, ["A"]), (True, ["E"]), (False, ["B", "C"]), (False, ["D"])]
    assert [p["label"] for p in pages] == ["Category A", "Category E", "Categories B + C", "Categories D"]   # data-label ของหน้า (ใช้อ้างเลขหน้า)


def test_none_for_non_search_runs(tmp_path):
    assert cd.load_dive(tmp_path, TRENDS) is None
    (tmp_path / "search_stream_work" / "themes").mkdir(parents=True)
    assert cd.load_dive(tmp_path, TRENDS) is None


# ---------------------------------------------------------------------------
# ตัวตรวจประโยคอธิบาย
# ---------------------------------------------------------------------------
SEARCHES = ["best face sunscreen for men", "best sunscreen for kids", "ไหว้ พระจันทร์ 2569", "how to fix frizzy hair"]


def _item(**over):
    base = {"id": 1, "topic_en": "searches for sunscreen for men and kids", "topic_th": "คำค้นเรื่องครีมกันแดดสำหรับผู้ชายและเด็ก",
            "searches": ["best face sunscreen for men", "Best  Sunscreen for kids"]}
    return {**base, **over}


def test_valid_topic_keeps_the_original_search_text_and_capitalises():
    out = dt.validate_topic(_item(), SEARCHES)
    assert out["topic_en"].startswith("Searches for sunscreen") and out["searches"] == ["best face sunscreen for men", "best sunscreen for kids"]


@pytest.mark.parametrize("over", [
    {"topic_en": "Dates for the Moon Festival in 2026"},                                   # ปี 2569 แปลงเป็น 2026 - ตัวเลขไม่อยู่ในคำค้น
    {"topic_en": "Searches about 'best moisturiser' for dry skin"},                        # คำในเครื่องหมายคำพูดที่ไม่มีในคำค้น
    {"topic_en": "People search to prepare for a trip"},                                   # คำบอกจุดประสงค์
    {"topic_th": "ผู้คนค้นหาเพื่อเตรียมตัวไปเที่ยว"},
    {"topic_en": "การค้นหาครีมกันแดด"},                                                      # ฉบับอังกฤษมีอักษรไทย
    {"topic_th": "searches for sunscreen"},                                                # ฉบับไทยไม่มีอักษรไทย
    {"searches": ["a search the model invented"]},                                         # ไม่มีคำค้นตัวอย่างที่ยืนยันได้
])
def test_topic_is_rejected_when_it_says_more_than_the_searches(over):
    assert dt.validate_topic(_item(**over), SEARCHES) is None


def test_year_written_as_in_the_searches_is_accepted_and_thai_quotes_are_allowed_in_english():
    ok = _item(topic_en="Searches for 'ไหว้ พระจันทร์ 2569' dates", topic_th="วันไหว้พระจันทร์ 2569", searches=["ไหว้ พระจันทร์ 2569"])
    assert dt.validate_topic(ok, SEARCHES)["searches"] == ["ไหว้ พระจันทร์ 2569"]


def test_search_wording_inside_the_searches_is_not_a_purpose_claim():
    # "how to fix frizzy hair" มีคำพวก "to" แต่เป็นคำค้นจริง - ประโยคที่ยกมาในเครื่องหมายคำพูดไม่ถูกตีเป็นเหตุผล
    item = _item(topic_en="Searches such as 'how to fix frizzy hair'", topic_th="คำค้นอย่าง 'how to fix frizzy hair'", searches=["how to fix frizzy hair"])
    assert dt.validate_topic(item, SEARCHES) is not None


# ---------------------------------------------------------------------------
# describe_dive: cache / ถามซ้ำ / ไม่มี LLM
# ---------------------------------------------------------------------------
def _dive(run):
    d = cd.load_dive(run, TRENDS)
    return d, next(c for c in d["categories"] if c["name"] == "Health")


def _answer(health, bad_ids=()):
    topics = []
    for i, t in enumerate(health["linked"] + health["others"], 1):
        s = t["searches"][0]
        item = {"id": i, "topic_en": f"Searches for {s}", "topic_th": f"คำค้นเรื่อง {s}", "searches": [s]}
        if i in bad_ids:
            item["topic_en"] = "People search to prepare for it"      # ไม่ผ่าน - บอกจุดประสงค์
        topics.append(item)
    return {"topics": topics}


def test_describe_asks_again_only_for_rejected_topics_then_uses_cache(run):
    d, health = _dive(run)
    calls = []

    def llm(system, user, max_tokens=None):
        calls.append(user)
        ids = [int(x.split()[1]) for x in user.splitlines() if x.startswith("Topic ")]
        full = _answer(health, bad_ids={2} if len(calls) == 1 else ())
        return json.dumps({"topics": [t for t in full["topics"] if t["id"] in ids]})

    cache = {}
    counts = dt.describe_dive(d, cache, llm_call=llm, max_workers=1, log=lambda *_: None)
    assert counts == {"llm": 4} and len(calls) == 2 and calls[1].count("Topic ") == 1 and "Topic 2" in calls[1]   # ถามซ้ำเฉพาะหัวข้อที่ตก
    assert all(t["topic"] for t in health["linked"] + health["others"]) and health["linked"][0]["topic"].startswith("Searches for")
    d2, health2 = _dive(run)
    calls.clear()
    counts2 = dt.describe_dive(d2, cache, llm_call=llm, max_workers=1, log=lambda *_: None)
    assert counts2 == {"llm (cached)": 4} and calls == []
    assert health2["linked"][0]["topic"] == health["linked"][0]["topic"]


def test_rejected_after_retry_falls_back_to_real_example_searches(run):
    d, health = _dive(run)
    llm = lambda system, user, max_tokens=None: json.dumps(_answer(health, bad_ids={1}))       # noqa: E731
    quiet = []
    counts = dt.describe_dive(d, {}, llm_call=llm, max_workers=1, log=quiet.append)
    first = health["linked"][0]
    assert first["topic"] is None and first["shown"] == first["searches"][:3] and counts["examples only"] == 1
    assert any("Health" in m for m in quiet)


def test_without_llm_and_cache_every_topic_shows_example_searches_only(run):
    d, health = _dive(run)
    counts = dt.describe_dive(d, {}, llm_call=None)
    assert counts == {"examples only": 4}
    assert all(t["topic"] is None and t["shown"] for t in health["linked"] + health["others"])


def test_cached_sentences_are_checked_again_before_use(run):
    d, health = _dive(run)
    llm = lambda system, user, max_tokens=None: json.dumps(_answer(health))                    # noqa: E731
    cache = {}
    dt.describe_dive(d, cache, llm_call=llm, max_workers=1, log=lambda *_: None)
    cache["dive"]["Health"]["output"][0]["topic_en"] = "People search to prepare for it"      # cache ถูกแก้/ตัวตรวจเข้มขึ้น
    d2, health2 = _dive(run)
    calls = []
    counts = dt.describe_dive(d2, cache, llm_call=lambda s, u, max_tokens=None: calls.append(u) or json.dumps(_answer(health2)),
                              max_workers=1, log=lambda *_: None)
    assert len(calls) == 1 and calls[0].count("Topic ") == 1 and counts == {"llm (cached)": 3, "llm": 1}   # ถามใหม่เฉพาะหัวข้อที่ cache ใช้ไม่ได้


def test_thai_copy_uses_thai_sentences_and_keeps_the_searches(run):
    d, health = _dive(run)
    dt.describe_dive(d, {}, llm_call=lambda s, u, max_tokens=None: json.dumps(_answer(health)), max_workers=1, log=lambda *_: None)
    th = cd.for_lang(d, "th", "ไทยและทั่วโลก")
    first = next(c for c in th["categories"] if c["name"] == "Health")["linked"][0]
    assert first["topic"].startswith("คำค้นเรื่อง") and first["shown"] == health["linked"][0]["shown"] and th["places_text"] == "ไทยและทั่วโลก"
    assert health["linked"][0]["topic"].startswith("Searches for")                              # ฉบับอังกฤษไม่ถูกแตะ


# ---------------------------------------------------------------------------
# เทมเพลต 2 ภาษา
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("lang", ["en", "th"])
def test_template_renders_overview_category_pages_and_method(run, lang):
    from dive_i18n import dive_strings
    from render import render_dive_html

    d, health = _dive(run)
    dt.describe_dive(d, {}, llm_call=lambda s, u, max_tokens=None: json.dumps(_answer(health)), max_workers=1, log=lambda *_: None)
    dv = cd.for_lang(d, lang, "Thailand and worldwide" if lang == "en" else "ไทยและทั่วโลก")
    ctx = {"meta": {"run_id": "r1", "title": "Beauty"}}
    brand = {"company_name": "Co", "logo": None, "accent_color": "#E8611A", "logo_for_dark_bg": False}
    html = render_dive_html(ctx, dv, brand, "Deep-Dive", datetime(2026, 10, 28), lang=lang)
    L = dive_strings(lang)
    for label in ('data-label="Cover"', 'data-label="Overview"', 'data-label="Categories Health"', 'data-label="Method"'):
        assert label in html
    assert html.count('class="dv-card') == 2 and html.count('<span class="o">') == 2 and html.count('<tr class="') == 2   # หมวดเล็ก: การ์ด 2 โยง + บรรทัด "ยังมีสิ่งที่ขึ้น" 2 หัวข้อ / ตาราง 2 หมวด
    assert "In report trends" in html or lang == "th"
    assert L["dv_ov_header"] in html and "#3" in html and "Sun Care Plain" in html           # ป้ายเทรนด์ในรายงานหลัก
    assert "'best sunscreen for kids'" in html                                               # หลักฐานของการโยง
    assert "spam.replit" not in html and "ไม่แสดง" not in html
