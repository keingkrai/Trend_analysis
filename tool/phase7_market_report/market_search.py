# -*- coding: utf-8 -*-
"""
⑲ รายงานส่วนแบ่งตลาด — Phase 3: ค้นเว็บตามคำค้นของ Phase 2 แล้วดึงเนื้อหาหน้าเว็บเป็นหลักฐาน (เสียโควตา SerpAPI)

ขั้นตอน:
1. ค้น Google ผ่าน SerpAPI (common/serpapi_keys.POOL - เปลี่ยนคีย์เองเมื่อหมด) จำกัดช่วงวันที่ตั้งแต่ 1 ม.ค. ของปีตั้งต้น
   (search_date_filter) ผลค้นหา cache ใน output/_checkpoints/market_search/ (คีย์ = พารามิเตอร์ ไม่รวม api_key)
   รันซ้ำ / รอบอื่นที่ใช้คำค้นเดิมไม่เสียโควตาซ้ำ
2. ก่อนค้นจริง: นับคำค้นที่ยังไม่มีใน cache แล้วเช็คโควตารวมทุกคีย์ (account.json ไม่เสีย search) ไม่พอ = หยุด
3. ต่อคำถาม: สลับผลของคำค้นอังกฤษกับไทยตามอันดับ ตัด URL ซ้ำ ข้ามเว็บขายของ/โซเชียล (ไม่มีเนื้อหาบทความ) แล้วดึง
   pages_per_question หน้าแรก (requests + BeautifulSoup, PDF ด้วย pypdf) - cache ใน output/_checkpoints/market_pages/
   หน้าเว็บที่ดึงไม่ได้ยังเก็บ title/snippet ไว้ (Phase 4 ใช้ snippet ได้ แต่หลักฐานจากเนื้อหาเต็มน่าเชื่อกว่า)
   ไม่ใช้ Apify (เสียเงิน/ช้า) - หน้าที่ถูกบล็อกบันทึกสาเหตุไว้
4. แบรนด์: ติดป้าย mentions_brand ถ้าชื่อแบรนด์ (อังกฤษหรือไทยจาก อย.) อยู่ในหัวข้อ/snippet/เนื้อหา

ผลลัพธ์:
    output/<รอบ>/phase7_market_evidence.json   ต่อคำถาม: ผลค้นหาทุกรายการ (rid เช่น q18-r03) + เนื้อหาหน้าเว็บที่ดึงได้

Usage:
    python tool/phase7_market_report/market_search.py --dry-run          # ดูแผน: จำนวน search ที่ต้องจ่ายจริง + โควตาที่เหลือ
    python tool/phase7_market_report/market_search.py                    # ค้นจริง (รอบ market_share_* ล่าสุด)
    python tool/phase7_market_report/market_search.py --run <รอบ> --max-searches 40
"""
import argparse
import hashlib
import io
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from market_facts import OUTPUT_ROOT, load_config  # noqa: E402
from market_questions import QUESTIONS_FILE, latest_run  # noqa: E402

EVIDENCE_FILE = "phase7_market_evidence.json"
CHECKPOINTS = OUTPUT_ROOT / "_checkpoints"
SEARCH_CACHE = CHECKPOINTS / "market_search"
PAGE_CACHE = CHECKPOINTS / "market_pages"
SEARCH_DEFAULTS = {"search_date_filter": True, "pages_per_question": 8, "page_text_max_chars": 15000,
                   "fetch_workers": 8, "fetch_timeout": 20}
# เว็บที่ไม่มีเนื้อหาบทความ (ร้านค้า / โซเชียล / วิดีโอ) - เก็บผลค้นหาไว้ แต่ไม่ดึงหน้าและไม่นับเป็นหน้าที่ดึง
# เทียบทั้งชื่อโดเมน (โดเมนนั้นหรือโดเมนย่อย) ไม่ใช่ข้อความบางส่วน - today.line.me (LINE TODAY ข่าว) ต้องไม่ถูกข้าม
SKIP_DOMAINS = ("shopee.co.th", "shopee.com", "lazada.co.th", "lazada.com", "tiktok.com", "facebook.com",
                "instagram.com", "youtube.com", "youtu.be", "twitter.com", "x.com", "pinterest.com", "amazon.com",
                "aliexpress.com", "konvy.com", "watsons.co.th", "bigc.co.th", "makro.pro", "lotuss.com",
                "boots.co.th", "eveandboy.com", "lemon8-app.com", "priceza.com", "central.co.th", "hdmall.co.th")
# ตัดเว็บที่ผลค้นหามักเป็นหน้าแรกของร้าน/โพสต์โซเชียลออกตั้งแต่ตอนค้น (ทดลองจริง 2026-10-12: คำค้น e-commerce ได้
# หน้าแรก Shopee + โพสต์ Facebook 17 จาก 20 รายการ) - ไม่ตัดทั้ง SKIP_DOMAINS เพราะคำค้นยาวเกินไป
EXCLUDE_SITES = ("facebook.com", "shopee.co.th", "lazada.co.th", "tiktok.com", "youtube.com", "instagram.com")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36",
      "Accept-Language": "th-TH,th;q=0.9,en;q=0.8"}


# ---------------------------------------------------------------------------
# ค้นหา + cache
# ---------------------------------------------------------------------------

def search_params(query, cfg, base_year, today=None):
    """พารามิเตอร์ SerpAPI ของคำค้นหนึ่ง (ไม่มี api_key - POOL ใส่ให้)"""
    news = query.get("kind") == "news"
    # ข่าวไม่ใส่ -site: - SerpAPI ค้าง (ReadTimeout 90 วินาที) ทุกครั้งที่คำค้นข่าวมี -site: แม้ตัวเดียว ส่วนข่าวที่ไม่มี
    # ตอบใน 1-2 วินาที (ทดสอบจริง 2026-10-12) และผลข่าวมาจากเว็บข่าวอยู่แล้ว
    q = query["q"] if news else query["q"] + "".join(f" -site:{s}" for s in EXCLUDE_SITES)
    params = {"engine": "google", "q": q, "hl": query["hl"], "gl": query["gl"],
              "google_domain": "google.co.th", "num": 10}
    if news:
        params["tbm"] = "nws"     # Google News - ได้บทความข่าวที่มีวันที่ แทนหน้าขายสินค้า
    if cfg["search_date_filter"]:
        today = today or datetime.now()
        params["tbs"] = f"cdr:1,cd_min:1/1/{base_year},cd_max:{today.month}/{today.day}/{today.year}"
    return params


def cache_key(params):
    return hashlib.sha1(json.dumps({k: v for k, v in params.items() if k != "api_key"}, sort_keys=True,
                                   ensure_ascii=False).encode("utf-8")).hexdigest()


def _keep(response):
    """เก็บเฉพาะส่วนที่ใช้ (ผลค้นหาเต็มของ SerpAPI ใหญ่และมีลิงก์ที่มี api_key)"""
    rows = response.get("organic_results") or response.get("news_results") or []   # ข่าว (tbm=nws) อยู่ใน news_results
    organic = [{k: r.get(k) for k in ("position", "title", "link", "snippet", "date", "source")} for r in rows]
    return {"organic_results": organic, "error": response.get("error"),
            "total_results": (response.get("search_information") or {}).get("total_results")}


TRANSIENT_ERRORS = ("run out of searches or are unusable", "try again later", "couldn't get valid results")


def _is_transient(error):
    """error ที่ลองใหม่แล้วอาจได้ผล (คีย์หมดทุกตัว / SerpAPI ขัดข้องชั่วคราว) - ไม่ cache"""
    return bool(error) and any(t in error.lower() for t in TRANSIENT_ERRORS)


def cached_search(params, pool, cache_dir=SEARCH_CACHE):
    """(ผลค้นหา, ใช้ search จริงไหม) - ผลที่ได้จริง (รวม "ไม่มีผล") cache ไว้ ผลที่ล้มชั่วคราวไม่ cache
    (cache เก่าที่เป็น error ชั่วคราว - ก่อนแก้ 2026-10-12 - ถือว่าไม่มี cache)"""
    path = Path(cache_dir) / f"{cache_key(params)}.json"
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if not _is_transient(cached.get("error")):
            return cached, False
    result = _keep(pool.search(params))
    if _is_transient(result["error"]):
        return result, True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"params": params, **result}, ensure_ascii=False, indent=1), encoding="utf-8")
    return result, True


def _is_cached(params, cache_dir=SEARCH_CACHE):
    path = Path(cache_dir) / f"{cache_key(params)}.json"
    return path.exists() and not _is_transient(json.loads(path.read_text(encoding="utf-8")).get("error"))


def uncached_count(questions, cfg, base_year, cache_dir=SEARCH_CACHE, today=None):
    """คำค้นที่ต้องจ่ายจริง (ไม่นับการค้นซ้ำแบบไม่จำกัดวันที่ - เกิดเฉพาะคำค้นที่ไม่ได้ผล บอกไม่ได้ล่วงหน้า)"""
    return sum(not _is_cached(search_params(x, cfg, base_year, today), cache_dir)
               for q in questions for x in q["queries"])


def needs_retry(result, names=()):
    """ผลที่ใช้ไม่ได้: error / ไม่มีผล / คำถามแบรนด์แต่ไม่มีผลไหนมีชื่อแบรนด์ในหัวข้อหรือ snippet
    (ทดลองจริง: "Colgate" + ตัวกรองวันที่ -> Google ทิ้งคำเกือบหมด ได้เรื่อง "market" ของตลาดการเงินยุโรป)"""
    organic = result.get("organic_results") or []
    if result.get("error") or not organic:
        return True
    names = [n for n in names if n]
    return bool(names) and not any(mentions(names, r.get("title"), r.get("snippet")) for r in organic)


# ---------------------------------------------------------------------------
# เลือกหน้าที่จะดึง
# ---------------------------------------------------------------------------

def domain_of(url):
    host = urlsplit(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_skipped(url):
    host = domain_of(url)
    return any(host == s or host.endswith("." + s) for s in SKIP_DOMAINS)


def _norm_url(url):
    p = urlsplit(url or "")
    return (domain_of(url) + p.path.rstrip("/")).lower()


def merge_results(per_query):
    """ผลของหลายคำค้น [(hl, kind, results)] -> รายการเดียว สลับตามอันดับ (ตามลำดับคำค้นที่ส่งมา) ตัด URL ซ้ำ"""
    merged, seen = [], set()
    longest = max((len(r) for *_, r in per_query), default=0)
    for i in range(longest):
        for hl, kind, results in per_query:
            if i >= len(results):
                continue
            r = results[i]
            key = _norm_url(r.get("link"))
            if not r.get("link") or key in seen:
                continue
            seen.add(key)
            merged.append({**r, "query_hl": hl, "kind": kind})
    return merged


def pick_pages(results, n):
    """หน้าแรก n หน้าที่ไม่ใช่เว็บที่ข้าม"""
    return [r["link"] for r in results if not is_skipped(r["link"])][:n]


# ---------------------------------------------------------------------------
# ดึงหน้าเว็บ
# ---------------------------------------------------------------------------

_DATE_META = ("article:published_time", "og:published_time", "datepublished", "pubdate", "publishdate",
              "date", "dc.date", "dc.date.issued", "parsely-pub-date", "article:modified_time")


def page_date(soup):
    """วันที่เผยแพร่จาก meta / JSON-LD / <time> -> "YYYY-MM-DD" หรือ None"""
    for m in soup.find_all("meta"):
        name = (m.get("property") or m.get("name") or m.get("itemprop") or "").lower()
        if name in _DATE_META:
            hit = re.search(r"\d{4}-\d{2}-\d{2}", m.get("content") or "")
            if hit:
                return hit.group(0)
    for s in soup.find_all("script", type="application/ld+json"):
        hit = re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})', s.string or "")
        if hit:
            return hit.group(1)
    t = soup.find("time", attrs={"datetime": True})
    hit = re.search(r"\d{4}-\d{2}-\d{2}", t["datetime"]) if t else None
    return hit.group(0) if hit else None


def html_text(content, max_chars):
    """(เนื้อหาหลัก, วันที่) จาก HTML - ตัดเมนู/สคริปต์ เก็บบรรทัดที่ยาว >= 40 ตัวอักษร (ตัดเมนูและปุ่มที่หลุดมา)"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content, "lxml")
    date = page_date(soup)
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "iframe"]):
        tag.decompose()

    def text_of(node):
        lines, out = [re.sub(r"\s+", " ", x).strip() for x in node.get_text("\n").split("\n")], []
        for line in lines:
            if len(line) >= 40 and (not out or out[-1] != line):
                out.append(line)
        return "\n".join(out)

    root = soup.find("article") or soup.find("main")
    text = text_of(root) if root else ""
    if len(text) < 500 and soup.body:          # <article> ว่าง/สั้นเกิน (บางเว็บใช้ห่อแค่หัวข้อ) -> ทั้งหน้า
        text = text_of(soup.body)
    return text[:max_chars], date


def pdf_text(content, max_chars, max_pages=20):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    parts = [(p.extract_text() or "") for p in reader.pages[:max_pages]]
    return re.sub(r"[ \t]+", " ", "\n".join(parts)).strip()[:max_chars]


def fetch_page(url, max_chars, timeout=20, get=None):
    """{"status": ok | skipped | error, "text", "date", "error"} - get ส่งของปลอมได้ตอนเทส"""
    if is_skipped(url):
        return {"status": "skipped", "text": "", "date": None, "error": "shop/social site"}
    if get is None:
        import requests
        get = requests.get
    try:
        resp = get(url, headers=UA, timeout=timeout, allow_redirects=True)
        if resp.status_code >= 400:
            return {"status": "error", "text": "", "date": None, "error": f"HTTP {resp.status_code}"}
        ctype = (resp.headers.get("content-type") or "").lower()
        if "pdf" in ctype or url.lower().split("?")[0].endswith(".pdf"):
            text, date = pdf_text(resp.content, max_chars), None
        elif "html" in ctype or not ctype:
            text, date = html_text(resp.content, max_chars)
        else:
            return {"status": "skipped", "text": "", "date": None, "error": f"content-type {ctype}"}
    except Exception as e:  # noqa: BLE001 - หน้าเดียวพังไม่ควรล้มทั้งขั้น
        return {"status": "error", "text": "", "date": None, "error": f"{type(e).__name__}: {str(e)[:150]}"}
    if len(text) < 200:
        return {"status": "error", "text": text, "date": date, "error": "too little text (blocked or script-only page)"}
    return {"status": "ok", "text": text, "date": date, "error": None}


def cached_fetch(url, cfg, cache_dir=PAGE_CACHE, get=None):
    path = Path(cache_dir) / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    page = {"url": url, "fetched_at": datetime.now().isoformat(timespec="seconds"),
            **fetch_page(url, cfg["page_text_max_chars"], cfg["fetch_timeout"], get)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
    return page


# ---------------------------------------------------------------------------
# รวม
# ---------------------------------------------------------------------------

def mentions(names, *texts):
    blob = " ".join(t or "" for t in texts).lower()
    return any(n and n.lower() in blob for n in names)


def run_search(questions, cfg, base_year, pool, max_searches=None, fetch=None, search_cache=SEARCH_CACHE):
    """ค้น + ดึงหน้า -> (คำถามพร้อมหลักฐาน, สถิติ) - fetch(url) ส่งของปลอมได้ตอนเทส"""
    fetch = fetch or (lambda url: cached_fetch(url, cfg))
    stats = {"searches_paid": 0, "searches_cached": 0, "search_errors": 0, "skipped_by_cap": 0,
             "relaxed_retries": 0, "relaxed_used": 0}

    def search(params):
        """ค้น 1 ครั้ง (นับสถิติ + เพดาน) - เกินเพดานและไม่มีใน cache = None"""
        if max_searches is not None and stats["searches_paid"] >= max_searches and not _is_cached(params, search_cache):
            stats["skipped_by_cap"] += 1
            return None
        result, paid = cached_search(params, pool, search_cache)
        stats["searches_paid" if paid else "searches_cached"] += 1
        return result

    per_question = []
    for q in questions:
        names = [q.get("brand"), (q.get("facts") or {}).get("name_th")] if q["level"] == "brand" else []
        per_query = []
        for x in q["queries"]:
            result = search(search_params(x, cfg, base_year))
            if result is None:
                continue
            relaxed = False
            # ไม่ได้ผล / ผลไม่มีชื่อแบรนด์ -> ค้นซ้ำแบบไม่จำกัดวันที่ (ตัวกรองวันที่ + -site: + "..." บางครั้งเข้มจน Google
            # ไม่คืนผลหรือทิ้งคำค้นเกือบหมด) - ใช้ผลใหม่เฉพาะเมื่อดีกว่า
            if cfg["search_date_filter"] and needs_retry(result, names):
                stats["relaxed_retries"] += 1
                retry = search(search_params(x, {**cfg, "search_date_filter": False}, base_year))
                if retry is not None and not needs_retry(retry, names):
                    result, relaxed = retry, True
                    stats["relaxed_used"] += 1
            if result.get("error"):
                stats["search_errors"] += 1
            per_query.append((x["hl"], x.get("kind", "web"),
                              [{**r, "relaxed": relaxed} for r in result.get("organic_results") or []]))
        # ข่าวก่อนเว็บ (บทความข่าวธุรกิจตรงคำถามกว่าเว็บทั่วไป) - ภายในกลุ่มคงลำดับเดิม (อังกฤษ, ไทย)
        per_query.sort(key=lambda p: p[1] != "news")
        per_question.append(merge_results(per_query))

    to_fetch = sorted({u for results in per_question for u in pick_pages(results, cfg["pages_per_question"])})
    with ThreadPoolExecutor(max_workers=cfg["fetch_workers"]) as ex:
        pages = dict(zip(to_fetch, ex.map(fetch, to_fetch)))
    stats["pages_ok"] = sum(p["status"] == "ok" for p in pages.values())
    stats["pages_failed"] = sum(p["status"] != "ok" for p in pages.values())

    out = []
    for q, results in zip(questions, per_question):
        names = [q.get("brand"), (q.get("facts") or {}).get("name_th")] if q["level"] == "brand" else []
        items = []
        for i, r in enumerate(results, 1):
            page = pages.get(r["link"])
            item = {"rid": f"{q['id']}-r{i:02d}", "query_hl": r["query_hl"], "kind": r["kind"],
                    "position": r.get("position"),
                    "title": r.get("title"), "link": r["link"], "domain": domain_of(r["link"]),
                    "snippet": r.get("snippet"), "serp_date": r.get("date"), "date_filter": not r.get("relaxed"),
                    "page_status": page["status"] if page else ("skipped" if is_skipped(r["link"]) else "not_fetched"),
                    "page_date": page.get("date") if page else None,
                    "page_error": page.get("error") if page else None,
                    "text": page["text"] if page and page["status"] == "ok" else ""}
            if names:
                item["mentions_brand"] = mentions(names, item["title"], item["snippet"], item["text"])
            items.append(item)
        out.append({k: q[k] for k in ("id", "level", "topic", "brand", "categories", "question_en", "question_th")}
                   | {"results": items})
    return out, stats


def main():
    parser = argparse.ArgumentParser(description="⑲ ค้นเว็บ + ดึงหน้าเว็บเป็นหลักฐาน (เสียโควตา SerpAPI)")
    parser.add_argument("--run", default=None, help="ชื่อโฟลเดอร์ใน main/output (ไม่ใส่ = market_share_* ล่าสุด)")
    parser.add_argument("--dry-run", action="store_true", help="แค่บอกจำนวน search ที่ต้องจ่ายจริง + โควตาที่เหลือ")
    parser.add_argument("--max-searches", type=int, default=None, help="จ่าย search จริงไม่เกินเท่านี้")
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    run_dir = OUTPUT_ROOT / args.run if args.run else latest_run()
    if not run_dir or not (run_dir / QUESTIONS_FILE).exists():
        sys.exit(f"❌ ไม่มี {QUESTIONS_FILE} - รัน market_questions.py ก่อน")
    qfile = json.loads((run_dir / QUESTIONS_FILE).read_text(encoding="utf-8"))
    questions, base_year = qfile["questions"], qfile["meta"]["period"][0]
    cfg = {**SEARCH_DEFAULTS, **load_config()}

    from common.serpapi_keys import POOL
    need = uncached_count(questions, cfg, base_year)
    if args.max_searches is not None:
        need = min(need, args.max_searches)
    left, _ = POOL.refresh_quota()
    print(f"รอบ {run_dir.name}: {len(questions)} คำถาม, {sum(len(q['queries']) for q in questions)} คำค้น "
          f"- ต้องค้นจริง {need} ครั้ง (ที่เหลือมีใน cache) | โควตาเหลือรวม {left} จาก {len(POOL.keys)} คีย์")
    if args.dry_run:
        return
    if need > left:
        sys.exit(f"❌ โควตาไม่พอ ({left} < {need}) - หยุดก่อนค้น")

    evidence, stats = run_search(questions, cfg, base_year, POOL, args.max_searches)
    result = {"meta": {"generated_at": datetime.now().isoformat(timespec="seconds"), "period": qfile["meta"]["period"],
                       "date_filter": cfg["search_date_filter"], **stats,
                       "config": {k: cfg[k] for k in SEARCH_DEFAULTS}},
              "questions": evidence}
    out = run_dir / EVIDENCE_FILE
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nsearch: จ่ายจริง {stats['searches_paid']} | จาก cache {stats['searches_cached']} | error {stats['search_errors']}"
          f" | ข้ามเพราะเกินเพดาน {stats['skipped_by_cap']}")
    print(f"หน้าเว็บ: ดึงได้ {stats['pages_ok']} | ไม่ได้ {stats['pages_failed']}")
    for q in evidence:
        ok = sum(r["page_status"] == "ok" for r in q["results"])
        extra = ""
        if q["level"] == "brand":
            extra = f" | กล่าวถึงแบรนด์ {sum(r.get('mentions_brand', False) for r in q['results'])}"
        print(f"  {q['id']} {q['topic'][:40]:40s} ผลค้นหา {len(q['results']):2d} | เนื้อหาเต็ม {ok}{extra}")
    print(f"✅ {out}")


if __name__ == "__main__":
    main()
