# -*- coding: utf-8 -*-
"""
Unit test ของ ⑲ Phase 3 (market_search.py) - SerpAPI และหน้าเว็บปลอมทั้งหมด ไม่ยิงเน็ตจริง ไม่เสียโควตา

รัน: pytest main/tool/tests/test_market_search.py -v
"""
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase7_market_report"))

from market_search import (SEARCH_DEFAULTS, cache_key, cached_search, fetch_page, html_text, merge_results,  # noqa: E402
                           needs_retry, pick_pages, run_search, search_params, uncached_count)

CFG = {**SEARCH_DEFAULTS, "pages_per_question": 2}
TODAY = datetime(2026, 10, 12)


class FakePool:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def search(self, params):
        q = params["q"].split(" -site:")[0]          # คำค้นจริงมี -site: ต่อท้าย (search_params)
        relaxed = "tbs" not in params                 # ค้นซ้ำแบบไม่จำกัดวันที่
        self.calls.append(q + (" [relaxed]" if relaxed else ""))
        if relaxed and (q, "relaxed") in self.responses:
            return self.responses[(q, "relaxed")]
        return self.responses.get(q, {"organic_results": []})


def _org(*links, title="t"):
    return {"organic_results": [{"position": i, "title": f"{title}{i}", "link": u, "snippet": f"s{i}"}
                                for i, u in enumerate(links, 1)]}


def test_search_params_date_filter_and_no_key():
    p = search_params({"q": "x", "hl": "th", "gl": "th"}, CFG, 2019, TODAY)
    assert p["tbs"] == "cdr:1,cd_min:1/1/2019,cd_max:10/12/2026" and "api_key" not in p
    assert p["q"].startswith("x -site:facebook.com") and "-site:shopee.co.th" in p["q"] and "tbm" not in p
    news = search_params({"q": "x", "hl": "th", "gl": "th", "kind": "news"}, CFG, 2019, TODAY)
    assert news["tbm"] == "nws" and cache_key(news) != cache_key(p)
    assert news["q"] == "x"                                   # ข่าว + -site: = SerpAPI ค้าง
    # คำค้นเว็บเดิม (ก่อนมี kind) ได้ cache key เดิม - ไม่เสียโควตาซ้ำ
    assert cache_key(search_params({"q": "x", "hl": "th", "gl": "th", "kind": "web"}, CFG, 2019, TODAY)) == cache_key(p)
    assert "tbs" not in search_params({"q": "x", "hl": "th", "gl": "th"}, {**CFG, "search_date_filter": False}, 2019)
    assert cache_key({**p, "api_key": "secret"}) == cache_key(p)


def test_news_results_are_read():
    from market_search import _keep
    kept = _keep({"news_results": [{"position": 1, "title": "n", "link": "https://news.th/a", "snippet": "s",
                                    "date": "2 days ago", "source": "News TH", "thumbnail": "x"}]})
    assert kept["organic_results"][0]["link"] == "https://news.th/a" and "thumbnail" not in kept["organic_results"][0]


def test_cached_search_pays_once(tmp_path):
    pool = FakePool({"x": _org("https://a.com/1")})
    params = {"engine": "google", "q": "x", "tbs": "t"}
    r1, paid1 = cached_search(params, pool, tmp_path)
    r2, paid2 = cached_search(params, pool, tmp_path)
    assert (paid1, paid2) == (True, False) and pool.calls == ["x"]
    assert r2["organic_results"][0]["link"] == "https://a.com/1"
    assert "secret" not in (tmp_path / f"{cache_key(params)}.json").read_text(encoding="utf-8")


def test_transient_errors_are_not_cached(tmp_path):
    for err in ("SerpAPI: all 12 keys have run out of searches or are unusable",
                "We couldn't get valid results for this search. Please try again later."):
        pool = FakePool({"x": {"error": err}})
        cached_search({"q": "x", "tbs": "t"}, pool, tmp_path)
        cached_search({"q": "x", "tbs": "t"}, pool, tmp_path)
        assert pool.calls == ["x", "x"]                   # ลองใหม่ได้


def test_old_cached_transient_error_counts_as_uncached(tmp_path):
    params = {"q": "x", "tbs": "t"}
    (tmp_path / f"{cache_key(params)}.json").write_text('{"error": "Please try again later."}', encoding="utf-8")
    pool = FakePool({"x": _org("https://a.com")})
    result, paid = cached_search(params, pool, tmp_path)
    assert paid and result["organic_results"]


@pytest.mark.parametrize("result,names,retry", [
    ({"error": "Google hasn't returned any results for this query."}, (), True),
    ({"organic_results": []}, (), True),
    ({"organic_results": [{"title": "Market Turmoil", "snippet": "EU market"}]}, ("Colgate", "คอลเกต"), True),
    ({"organic_results": [{"title": "คอลเกต ยาสีฟัน", "snippet": ""}]}, ("Colgate", "คอลเกต"), False),
    ({"organic_results": [{"title": "anything", "snippet": ""}]}, (), False),   # คำถามตลาดไม่ตรวจชื่อ
])
def test_needs_retry(result, names, retry):
    assert needs_retry(result, names) is retry


def test_run_search_retries_without_date_filter(tmp_path):
    questions = [{"id": "q32", "level": "brand", "topic": "Colgate", "brand": "Colgate", "categories": [],
                  "question_en": "?", "question_th": "?", "facts": {"name_th": "คอลเกต"},
                  "queries": [{"q": "c", "hl": "en", "gl": "th"}]}]
    junk = {"organic_results": [{"position": 1, "title": "Market Turmoil", "link": "https://fsb.org/x", "snippet": ""}]}
    good = {"organic_results": [{"position": 1, "title": "Colgate Thailand", "link": "https://news.th/c", "snippet": ""}]}
    pool = FakePool({"c": junk, ("c", "relaxed"): good})
    evidence, stats = run_search(questions, CFG, 2019, pool, fetch=lambda u: {"status": "error", "text": "",
                                                                              "date": None, "error": "x"},
                                 search_cache=tmp_path)
    assert pool.calls == ["c", "c [relaxed]"]
    assert stats["relaxed_retries"] == 1 and stats["relaxed_used"] == 1 and stats["searches_paid"] == 2
    item = evidence[0]["results"][0]
    assert item["link"] == "https://news.th/c" and item["date_filter"] is False


def test_uncached_count(tmp_path):
    qs = [{"queries": [{"q": "x", "hl": "en", "gl": "th"}, {"q": "y", "hl": "th", "gl": "th"}]}]
    assert uncached_count(qs, CFG, 2019, tmp_path, TODAY) == 2
    cached_search(search_params(qs[0]["queries"][0], CFG, 2019, TODAY), FakePool({}), tmp_path)
    assert uncached_count(qs, CFG, 2019, tmp_path, TODAY) == 1


def test_merge_results_interleaves_and_dedupes():
    en = _org("https://www.a.com/x/", "https://b.com/y")["organic_results"]
    th = _org("https://a.com/x", "https://c.com/z")["organic_results"]
    merged = merge_results([("en", "web", en), ("th", "web", th)])
    assert [m["link"] for m in merged] == ["https://www.a.com/x/", "https://b.com/y", "https://c.com/z"]
    assert [m["query_hl"] for m in merged] == ["en", "en", "th"] and {m["kind"] for m in merged} == {"web"}


def test_run_search_puts_news_first(tmp_path):
    questions = [{"id": "q01", "level": "market", "topic": "t", "brand": None, "categories": [], "question_en": "?",
                  "question_th": "?", "queries": [{"q": "w", "hl": "en", "gl": "th", "kind": "web"},
                                                  {"q": "n", "hl": "en", "gl": "th", "kind": "news"}]}]
    pool = FakePool({"w": _org("https://web.th/1"), "n": _org("https://news.th/1")})
    evidence, _ = run_search(questions, CFG, 2019, pool, fetch=lambda u: {"status": "error", "text": "", "date": None,
                                                                          "error": "x"}, search_cache=tmp_path)
    assert [(r["domain"], r["kind"]) for r in evidence[0]["results"]] == [("news.th", "news"), ("web.th", "web")]


def test_pick_pages_skips_shops_and_social():
    results = [{"link": u} for u in ("https://shopee.co.th/p", "https://www.tiktok.com/@a", "https://news.th/a",
                                     "https://m.facebook.com/x", "https://www.youtube.com/watch", "https://blog.th/b",
                                     "https://mag.th/c")]
    assert pick_pages(results, 2) == ["https://news.th/a", "https://blog.th/b"]


def test_news_on_lookalike_domains_is_not_skipped():
    # LINE TODAY เป็นเว็บข่าว / โดเมนที่แค่มีคำว่า x.com อยู่ในชื่อไม่ใช่ X
    results = [{"link": "https://today.line.me/th/v2/article/abc"}, {"link": "https://www.marketingoops.com/a"}]
    assert pick_pages(results, 5) == ["https://today.line.me/th/v2/article/abc", "https://www.marketingoops.com/a"]


ARTICLE = ("<html><head><meta property='article:published_time' content='2024-03-05T08:00:00+07:00'></head>"
           "<body><nav>Home | News | Contact us and more links here ok</nav><article>"
           + "<p>" + "La Roche-Posay ขยายจุดขายในร้านขายยาทั่วประเทศไทยในปี 2023 " * 20 + "</p>"
           + "<p>short</p></article><footer>Copyright footer text that is long enough to count</footer></body></html>")


def test_html_text_article_date_and_noise_removed():
    text, date = html_text(ARTICLE.encode("utf-8"), 10000)
    assert date == "2024-03-05"
    assert "ร้านขายยา" in text and "short" not in text and "Copyright" not in text and "Contact" not in text


def test_html_text_falls_back_to_body_when_article_is_tiny():
    html = "<html><body><article><h1>Title only</h1></article><div><p>" + "เนื้อหาหลักอยู่นอก article " * 40 \
           + "</p></div></body></html>"
    text, _ = html_text(html.encode("utf-8"), 10000)
    assert "เนื้อหาหลักอยู่นอก article" in text


class Resp:
    def __init__(self, code, body=b"", ctype="text/html; charset=utf-8"):
        self.status_code, self.content, self.headers = code, body, {"content-type": ctype}


def test_fetch_page_statuses():
    assert fetch_page("https://news.th/a", 9999, get=lambda *a, **k: Resp(403))["error"] == "HTTP 403"
    ok = fetch_page("https://news.th/a", 9999, get=lambda *a, **k: Resp(200, ARTICLE.encode("utf-8")))
    assert ok["status"] == "ok" and ok["date"] == "2024-03-05"
    thin = fetch_page("https://news.th/a", 9999, get=lambda *a, **k: Resp(200, b"<html><body>Enable JS</body></html>"))
    assert thin["status"] == "error"
    assert fetch_page("https://shopee.co.th/x", 9999)["status"] == "skipped"
    assert fetch_page("https://x.th/a.zip", 9999, get=lambda *a, **k: Resp(200, b"zip", "application/zip"))["status"] == "skipped"


def test_run_search_end_to_end(tmp_path):
    questions = [{"id": "q18", "level": "brand", "topic": "Mistine", "brand": "Mistine", "categories": ["Skin Care"],
                  "question_en": "?", "question_th": "?", "facts": {"name_th": "มิสทิน"},
                  "queries": [{"q": "en-q", "hl": "en", "gl": "th"}, {"q": "th-q", "hl": "th", "gl": "th"}]}]
    pool = FakePool({"en-q": _org("https://a.th/1", "https://shopee.co.th/2", title="Mistine "),
                     "th-q": _org("https://b.th/3", title="มิสทิน ")})
    pages = {"https://a.th/1": {"status": "ok", "text": "ข่าวมิสทิน ปรับช่องทางขาย", "date": "2024-01-01", "error": None},
             "https://b.th/3": {"status": "error", "text": "", "date": None, "error": "HTTP 403"}}
    evidence, stats = run_search(questions, CFG, 2019, pool, fetch=lambda u: pages[u], search_cache=tmp_path)
    items = evidence[0]["results"]
    assert [i["rid"] for i in items] == ["q18-r01", "q18-r02", "q18-r03"]
    # ลำดับ: EN#1 (a.th), TH#1 (b.th), EN#2 (shopee)
    assert items[0]["mentions_brand"] and items[0]["page_status"] == "ok"      # ชื่อไทยจาก อย. ก็นับ
    assert items[1]["domain"] == "b.th" and items[1]["page_status"] == "error" and items[1]["text"] == ""
    assert items[2]["domain"] == "shopee.co.th" and items[2]["page_status"] == "skipped"
    assert stats["searches_paid"] == 2 and stats["pages_ok"] == 1 and stats["pages_failed"] == 1
    _, stats2 = run_search(questions, CFG, 2019, pool, fetch=lambda u: pages[u], search_cache=tmp_path)
    assert stats2["searches_paid"] == 0 and stats2["searches_cached"] == 2


def test_run_search_respects_max_searches(tmp_path):
    questions = [{"id": "q01", "level": "market", "topic": "t", "brand": None, "categories": [], "question_en": "?",
                  "question_th": "?", "queries": [{"q": "a", "hl": "en", "gl": "th"}, {"q": "b", "hl": "th", "gl": "th"}]}]
    pool = FakePool({})
    _, stats = run_search(questions, CFG, 2019, pool, max_searches=1, fetch=lambda u: None, search_cache=tmp_path)
    # "a" ไม่ได้ผล -> ค้นซ้ำแบบไม่จำกัดวันที่ถูกเพดานกัน + "b" ถูกเพดานกัน = 2
    assert pool.calls == ["a"] and stats["skipped_by_cap"] == 2
