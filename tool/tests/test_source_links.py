# -*- coding: utf-8 -*-
"""
เทสหน้ารายการแหล่งข้อมูลของ ⑯ (หัวข้อ + URL) - report_data._source_documents / i18n.source_doc_groups / เทมเพลต /
build_source_links.py (ตัวหาลิงก์ย้อนหลังของรอบเก่า) - ไม่เรียก API จริง (ส่งฟังก์ชัน get ปลอมเข้าไป)

รัน: pytest main/tool/tests/test_source_links.py -v
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase6_pdf_report"))

import pytest  # noqa: E402

import build_source_links as bsl  # noqa: E402
from enrich import enrich_trends  # noqa: E402
from i18n import localize, source_doc_groups  # noqa: E402
from render import render_html  # noqa: E402
from report_data import _doc_title, build_context  # noqa: E402

BRAND = {"company_name": "Acme", "logo": None, "prepared_by": "", "accent_color": "#E8611A"}


def _ctx(run):
    """context ที่ enrich แล้ว (เทมเพลตต้องมีข้อความต่อเทรนด์) - ข้อความสำรองไม่เรียก LLM"""
    ctx, _ = build_context(run)
    enrich_trends(ctx["trends"], {}, llm_call=None, log=lambda *_: None)
    return ctx


def _write(folder, name, data):
    with open(folder / name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _prov(*titles):
    return [{"triplet": ["a", "r", "b"], "doc_index": i, "title": t, "source_region": "", "evidence": "e", "verified": True}
            for i, t in enumerate(titles)]


@pytest.fixture
def run_dir(tmp_path):
    run = tmp_path / "topic_20260101_000000"
    run.mkdir()
    _write(run, "phase3_trend_highlights_result.json", {
        "top_n": 1, "n_trends_total": 1, "profiles": [],
        "selected_trends": [{"overall_rank": 1, "stream": "Social", "trend": "Barrier Care", "rank_score": 0.9, "top_rank": 1}],
        "excluded_trends": [], "failed_trends": []})
    return run


ASR = " [automatic speech-to-text transcript: product/ingredient names may be misrecognized]"


def _streams(run):
    _write(run, "phase1_paper_stream_result.json", {
        "triplet_provenance": _prov("Study A", "Study B"),
        "documents": [{"title": "Study A", "source": "MDPI (native)", "link": "https://www.mdpi.com/a"}]})   # รอบใหม่: ลิงก์ในผลสาย
    _write(run, "phase2_social_stream_result.json", {
        "triplet_provenance": _prov("YouTube: clip one" + ASR, "Pantip: ผมร่วง ทำไงดี", "Reddit: post one")})
    _write(run, "phase2_news_stream_result.json", {
        "triplet_provenance": _prov("Deal A"),
        "documents": [{"title": "Deal A", "source": "Intl RSS", "link": "https://news.example/a?utm_source=rss&id=7&utm_medium=x"}]})


def test_doc_title_strips_prefix_and_asr_note():
    assert _doc_title("YouTube: คลิป ตัวอย่าง" + ASR) == ("YouTube", "คลิป ตัวอย่าง")
    assert _doc_title("Reddit: [B&A] post") == ("Reddit", "[B&A] post")
    assert _doc_title("Study A") == (None, "Study A")


def test_source_documents_links_order_and_pantip(run_dir):
    _streams(run_dir)
    _write(run_dir, "phase6_source_links.json", {"links": {
        "Study B": {"url": "https://doi.org/b", "title": None},
        "Reddit: post one": {"url": "https://www.reddit.com/r/x/1", "title": "post one &amp; more - full title"}}})
    docs = build_context(run_dir)[0]["meta"]["source_docs"]
    assert [(d["title"], d["url"]) for d in docs["papers"]] == [("Study A", "https://www.mdpi.com/a"),   # ลิงก์ในผลสาย
                                                                ("Study B", "https://doi.org/b")]      # ลิงก์จากไฟล์เสริม
    # เรียง Reddit -> YouTube -> Pantip; ชื่อเต็มจากไฟล์เสริมแทนชื่อที่สายตัดไว้; YouTube ไม่มีลิงก์ = url None (แสดงแค่ชื่อ)
    assert [(d["platform"], d["title"], d["url"]) for d in docs["discussions"]] == [
        ("Reddit", "post one & more - full title", "https://www.reddit.com/r/x/1"), ("YouTube", "clip one", None),
        ("Pantip", "ผมร่วง ทำไงดี", "https://pantip.com/search?q=%E0%B8%9C%E0%B8%A1%E0%B8%A3%E0%B9%88%E0%B8%A7%E0%B8%87%20%E0%B8%97%E0%B8%B3%E0%B9%84%E0%B8%87%E0%B8%94%E0%B8%B5")]
    assert docs["discussions"][2]["search"] is True and docs["news"] == [
        {"title": "Deal A", "url": "https://news.example/a?id=7", "platform": None, "search": False}]   # ตัด utm_* ออก


def test_source_documents_empty_run_has_no_page(run_dir):
    assert build_context(run_dir)[0]["meta"]["source_docs"] == {}
    html = render_html(_ctx(run_dir), BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert 'data-label="Sources"' not in html


def test_source_list_page_en_th(run_dir):
    _streams(run_dir)
    ctx = _ctx(run_dir)
    en = render_html(ctx, BRAND, {}, "T", datetime(2026, 1, 1), "x")
    assert 'data-label="Sources"' in en and "Appendix | Source list" in en
    assert 'href="https://www.mdpi.com/a"' in en and "search: ผมร่วง ทำไงดี" in en and "Deal A" in en
    assert "pantip.com/search?q=ผมร่วง ทำไงดี" in en                    # ข้อความลิงก์ถอดรหัส %xx (href ยังเป็นแบบเข้ารหัส)
    assert "automatic speech-to-text" not in en                       # หมายเหตุถอดเสียงไม่ขึ้นหน้ารายงาน
    th = render_html(localize(ctx, "th"), BRAND, {}, "T", datetime(2026, 1, 1), "x", lang="th")
    assert "ภาคผนวก | รายการแหล่งข้อมูล" in th and "ค้นหา: ผมร่วง ทำไงดี" in th and "ช่องทางออนไลน์" in th
    groups = source_doc_groups(ctx["meta"], "en")
    assert [g["label"] for g in groups] == ["Research articles", "Online channels", "News"]


# ---------------------------------------------------------------- build_source_links ---------------------------------------------

def test_same_title_handles_truncation_and_entities():
    assert bsl.same_title("[B&A] 14 days using La Roche-Posay Cicaplast", "[B&amp;A] 14 days using La Roche-Posay Cicaplast Baume B5+")
    assert bsl.same_title("Puig Takes Full Ownership of ISDIN in €1.2 Billion Deal", "Puig Takes Full Ownership of ISDIN in €1.2 Bil")
    assert not bsl.same_title("Hair", "Hair loss in men")                    # สั้นเกิน - ไม่จับคู่แบบขึ้นต้น
    assert not bsl.same_title("Tretinoin anniversary 1 year", "1 year difference")


def test_lookups_pick_exact_title_and_retry_queries():
    asked = []

    def reddit_get(url, params, headers):
        asked.append(params["q"])
        if len(asked) == 1:
            return {"data": {"children": [{"data": {"title": "something else entirely about hair", "permalink": "/r/a/1"}}]}}
        return {"data": {"children": [{"data": {"title": "Tretinoin anniversary 1 year of using it for acne scars and early aging",
                                                "permalink": "/r/b/2/"}}]}}

    long_title = "Tretinoin anniversary 1 year of using it for acne scars and early aging"   # > 50 ตัวอักษร = มีรอบค้นช่วงต้นด้วย
    assert bsl.reddit_lookup(long_title, "tok", reddit_get) == ("https://www.reddit.com/r/b/2/", long_title)

    def yt_get(url, params, headers):
        if "🍀" in params["q"]:
            return {"items": []}                                              # ชื่อมีอีโมจิ -> 0 ผล แล้วลองชื่อที่ตัดสัญลักษณ์
        return {"items": [{"id": {"videoId": "abc123"}, "snippet": {"title": "Centella BATTLE เซรั่ม ปลอบประโลม &amp; อื่นๆ"}}]}

    assert bsl.youtube_lookup("Centella BATTLE 🍀 เซรั่ม ปลอบประโลม", "k", yt_get) == (
        "https://www.youtube.com/watch?v=abc123", "Centella BATTLE เซรั่ม ปลอบประโลม & อื่นๆ")

    def oa_get(url, params, headers):
        return {"results": [{"title": "Other paper", "doi": "https://doi.org/x"},
                            {"title": "Topical Retinoids in Acne", "doi": "https://doi.org/10.3390/y", "primary_location": {}}]}

    assert bsl.openalex_lookup("Topical Retinoids in Acne", "k", oa_get) == ("https://doi.org/10.3390/y", "Topical Retinoids in Acne")
    assert bsl.openalex_lookup("Nothing like it here at all, truly", "k", oa_get) is None


def test_build_for_run_local_sources_memo_and_keep_existing(run_dir):
    _streams(run_dir)
    news = [("Deal A", "https://news.example/deal-a")]
    mdpi = [("Study B", "https://www.mdpi.com/b")]
    calls = []

    def get(url, params, headers):
        calls.append(url)
        return {"items": [{"id": {"videoId": "v1"}, "snippet": {"title": "clip one"}}]}

    memo = {}
    env = {"YOUTUBE_API_KEY": "k"}                                          # ไม่มีคีย์ Reddit -> Reddit หาไม่ได้ ไม่พัง
    links, missing, summary = bsl.build_for_run(run_dir, news, mdpi, env, True, memo, get=get)
    assert "Deal A" not in links and links["Study B"]["how"] == "mdpi-file"   # ข่าวมีลิงก์ใน "documents" แล้ว - ไม่หาซ้ำ
    assert links["YouTube: clip one" + ASR]["url"] == "https://www.youtube.com/watch?v=v1"
    assert missing == ["Reddit: post one"] and summary == {"papers": (2, 2), "discussions": (1, 2), "news": (1, 1)}
    # Study A มีลิงก์ใน "documents" แล้ว - ไม่หาซ้ำ; Pantip ไม่ถูกนับ (ลิงก์ = หน้าค้นหา)
    assert "Study A" not in links
    n_calls = len(calls)
    bsl.build_for_run(run_dir, news, mdpi, env, True, memo, get=get)         # รอบที่สองใช้ memo - ไม่เรียก API ซ้ำ
    assert len(calls) == n_calls
    _, _, summary_offline = bsl.build_for_run(run_dir, news, mdpi, {}, False, {}, get=get)   # --no-api: เฉพาะไฟล์ในเครื่อง
    assert summary_offline == {"papers": (2, 2), "discussions": (0, 2), "news": (1, 1)}
