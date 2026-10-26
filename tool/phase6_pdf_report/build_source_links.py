# -*- coding: utf-8 -*-
"""
⑯ หน้ารายการแหล่งข้อมูล — เติมลิงก์ของเอกสารต้นทางให้รอบเก่า (🆕 2026-10-14)

ผลของสาย Paper/Social/News ก่อนวันที่ 2026-10-14 เก็บแค่ชื่อเรื่องของเอกสารใน triplet_provenance ไม่ได้เก็บลิงก์ (รอบใหม่เก็บใน "documents"
ของไฟล์ผลสายเอง - ไม่ต้องใช้ไฟล์นี้) สคริปต์นี้หาลิงก์ย้อนหลังจากชื่อเรื่อง แล้วเขียน phase6_source_links.json ในโฟลเดอร์รอบ
(report_data._source_documents อ่านไฟล์นี้เมื่อผลสายไม่มีลิงก์) - ไม่แตะไฟล์ผลของไปป์ไลน์เลย (hash ใน manifest จึงไม่เปลี่ยน)

ลำดับการหา (ชื่อเรื่องต้องตรงกันหลังตัดตัวอักษรที่ไม่ใช่คำ - ชื่อที่สายตัดไว้ 80 ตัวอักษรใช้ "ขึ้นต้นด้วย"):
  ข่าว       cache การ scrape ของไปป์ไลน์ (memory/scraped_cache.json ทั้ง 2 ที่) - ไม่เรียกเครือข่าย
  งานวิจัย    scrapers/data/mdpi_papers.jsonl (MDPI) -> OpenAlex API (OPEN_ALEX_KEY) เฉพาะที่ยังไม่พบ
  Reddit     oauth.reddit.com/search (REDDIT_CLIENT_ID/SECRET - เหมือน discover_reddit.py) ค้นด้วยชื่อเรื่อง
  YouTube    YouTube Data API search.list (YOUTUBE_API_KEY - เหมือน discover_youtube.py) ค้นด้วยชื่อเรื่อง
  Pantip     ไม่ต้องหา - เอกสารคือหน้าผลค้นหาของคำค้น ลิงก์ = pantip.com/search?q=<คำค้น> (report_data ประกอบเอง)
หาไม่พบ/ชื่อไม่ตรง = ไม่ใส่ลิงก์ (รายงานแสดงแค่ชื่อ) ไม่เดา

คีย์อ่านจาก main/.env เฉพาะ 4 ตัวที่ใช้ (ไม่พิมพ์ค่าออกหน้าจอ); --no-api = ใช้เฉพาะไฟล์ในเครื่อง

รัน:  python tool/phase6_pdf_report/build_source_links.py --run <รอบ> [<รอบ> ...] [--no-api] [--force]
"""
import argparse
import html
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from report_data import LINKS_FILE, STREAM_FILES, _doc_title, _provenance_docs, read_json  # noqa: E402

ROOT = HERE.parents[1]                      # main/
OUTPUT = ROOT / "output"
ENV_PATH = ROOT / ".env"
NEWS_CACHES = (ROOT / "memory" / "scraped_cache.json",
               ROOT / "tool" / "phase2_three_streams" / "news" / "memory" / "scraped_cache.json")
MDPI_JSONL = ROOT / "tool" / "phase1_paper_stream" / "scrapers" / "data" / "mdpi_papers.jsonl"
ENV_KEYS = ("YOUTUBE_API_KEY", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "OPEN_ALEX_KEY")
USER_AGENT = "windows:exfac-trend-research:v0.1 (by /u/exfac_research)"   # เหมือน discover_reddit.py
MIN_PREFIX = 25            # ชื่อสั้นกว่านี้ไม่ใช้การจับคู่แบบขึ้นต้น (กันตรงมั่ว)
PAUSE = 0.6                # วินาทีระหว่างการเรียก API


def norm(text):
    return re.sub(r"\W+", " ", html.unescape(text or "").lower()).strip()


def same_title(full, partial):
    """ชื่อเรื่องตรงกัน: เท่ากัน หรืออันใดอันหนึ่งเป็นส่วนขึ้นต้นของอีกอัน (ยาวอย่างน้อย MIN_PREFIX) - ชื่อที่สายตัด/cache ตัดไว้"""
    a, b = norm(full), norm(partial)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= MIN_PREFIX and long_.startswith(short)


def read_env(path=ENV_PATH):
    """เฉพาะ ENV_KEYS จากไฟล์ .env (บรรทัด KEY=VALUE) - dotenv อ่านไฟล์นี้ไม่ได้ทั้งไฟล์เพราะ SERPAPI_KEY เป็นหลายบรรทัด"""
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = re.match(r"^\s*([A-Z_]+)\s*=\s*(.*?)\s*$", line)
            if m and m.group(1) in ENV_KEYS:
                out[m.group(1)] = m.group(2).strip().strip("\"'")
    return out


# ---------------------------------------------------------------- ตัวหาลิงก์ (ฟังก์ชันล้วนรับข้อมูล/ตัวเรียกเข้ามา เทสได้) ------
def load_news_cache(paths=NEWS_CACHES):
    """cache การ scrape -> [(ชื่อเรื่อง, URL บทความจริง)] (decoded_url ถ้าเป็น http ไม่งั้นคีย์ของ cache)"""
    rows = []
    for p in paths:
        if Path(p).exists():
            for url, v in (json.loads(Path(p).read_text(encoding="utf-8")) or {}).items():
                real = v.get("decoded_url") if str(v.get("decoded_url") or "").startswith("http") else url
                if v.get("title") and str(real).startswith("http"):
                    rows.append((v["title"], real))
    return rows


def find_in_rows(title, rows):
    """[(ชื่อ, URL)] -> URL ของแถวแรกที่ชื่อตรง หรือ None"""
    return next((u for t, u in rows if same_title(title, t)), None)


def load_mdpi(path=MDPI_JSONL):
    rows = []
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                url = r.get("mdpi_url") or r.get("doi_url")
                if r.get("title") and url:
                    rows.append((r["title"], url))
    return rows


def openalex_lookup(title, key, get):
    """OpenAlex ค้นด้วยชื่อ -> (URL, ชื่อเต็ม) ของงานที่ชื่อตรง หรือ None; get(url, params, headers) -> dict (JSON)"""
    data = get("https://api.openalex.org/works", {"search": title, "per-page": 5, "api_key": key}, {})
    for w in (data or {}).get("results") or []:
        if same_title(title, w.get("title")):
            url = w.get("doi") or ((w.get("primary_location") or {}).get("landing_page_url"))
            if url:
                return url, w.get("title")
    return None


def reddit_lookup(title, token, get):
    """Reddit oauth search ด้วยชื่อเรื่อง (ทั้งชื่อ แล้วลองแค่ช่วงต้น) -> (permalink เต็ม, ชื่อเต็ม) หรือ None"""
    for q in dict.fromkeys([title[:120], title[:50]]):
        data = get("https://oauth.reddit.com/search", {"q": q, "limit": 10, "type": "link", "sort": "relevance"},
                   {"Authorization": f"bearer {token}", "User-Agent": USER_AGENT})
        for ch in ((data or {}).get("data") or {}).get("children") or []:
            d = ch.get("data") or {}
            if same_title(title, d.get("title")) and d.get("permalink"):
                return "https://www.reddit.com" + d["permalink"], html.unescape(d["title"])
    return None


def youtube_lookup(title, key, get):
    """YouTube search.list ด้วยชื่อเรื่อง (ทั้งชื่อ -> ตัดอีโมจิ/สัญลักษณ์ -> ช่วงต้น 40 ตัวอักษร) -> (watch URL, ชื่อเต็ม) หรือ None
    ชื่อที่มีอีโมจิบางชื่อค้นทั้งชื่อแล้วได้ 0 ผล (เจอ Centella BATTLE 🍀 ...) จึงต้องมีรอบตัดสัญลักษณ์"""
    plain = re.sub(r"[^\w\s\u0E00-\u0E7F!?.,'&-]", "", title).strip()
    for q in dict.fromkeys(x for x in (title, plain, title[:40], plain[:40]) if x):
        data = get("https://www.googleapis.com/youtube/v3/search",
                   {"part": "snippet", "type": "video", "maxResults": 5, "q": q, "key": key}, {})
        for it in (data or {}).get("items") or []:
            sn = it.get("snippet") or {}
            vid = (it.get("id") or {}).get("videoId")
            if vid and same_title(title, html.unescape(sn.get("title") or "")):
                return f"https://www.youtube.com/watch?v={vid}", html.unescape(sn["title"])
    return None


def http_get_json(url, params, headers, attempts=3):
    """GET -> JSON; 429 / 5xx ลองใหม่สูงสุด attempts ครั้ง (รอเพิ่มทีละ PAUSE วินาที) - รอบแรกของการรันจริงมีเอกสารหลุดเพราะโดนจำกัดความถี่"""
    import requests
    for i in range(attempts):
        time.sleep(PAUSE * (i + 1) * (1 if i == 0 else 4))
        r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT, **headers}, timeout=30)
        if r.status_code in (429, 500, 502, 503) and i < attempts - 1:
            continue
        r.raise_for_status()
        return r.json()


def reddit_token(env):
    import requests
    r = requests.post("https://www.reddit.com/api/v1/access_token", data={"grant_type": "client_credentials"},
                      auth=(env["REDDIT_CLIENT_ID"], env["REDDIT_CLIENT_SECRET"]), headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


# ---------------------------------------------------------------- ต่อรอบ ------------------------------------------------------
def build_for_run(run_dir, news_rows, mdpi_rows, env, use_api, memo, force=False, get=http_get_json):
    """หาลิงก์ของเอกสารในรอบ -> (links {ชื่อเรื่องใน provenance: {url, title, how}}, ไม่พบ [ชื่อเรื่อง], สรุปต่อกลุ่ม {กลุ่ม: (พบ, ทั้งหมด)})
    memo = {ชื่อเรื่อง: ผลที่หาไว้แล้วในรอบอื่นของการรันนี้} (รอบ snapshot ใช้ผลสายชุดเดียวกัน - ไม่เรียก API ซ้ำ)"""
    existing = {} if force else ((read_json(run_dir / LINKS_FILE) or {}).get("links") or {})
    links, missing, summary = dict(existing), [], {}
    token = {}
    for group, stream_name in (("papers", "Paper"), ("discussions", "Social"), ("news", "News")):
        stream = read_json(run_dir / STREAM_FILES[stream_name]) or {}
        have = {d.get("title") for d in stream.get("documents") or [] if isinstance(d, dict) and d.get("link")}
        hit = total = 0
        for title, _ in _provenance_docs(stream).values():
            platform, shown = _doc_title(title)
            if platform == "Pantip":
                continue                                    # ลิงก์ = หน้าค้นหา report_data ประกอบเอง
            total += 1
            if title in have or (title in links and links[title].get("url")):
                hit += 1
                continue
            if title not in memo:
                memo[title] = _resolve(group, platform, shown, news_rows, mdpi_rows, env, use_api, token, get)
            found = memo[title]
            if found:
                links[title] = found
                hit += 1
            else:
                missing.append(title)
        summary[group] = (hit, total)
    return links, missing, summary


def _resolve(group, platform, shown, news_rows, mdpi_rows, env, use_api, token, get):
    """1 เอกสาร -> {"url", "title", "how"} หรือ None (API ล้มเหลว = None แล้วไปต่อ ไม่หยุดทั้งรอบ)"""
    try:
        if group == "news":
            url = find_in_rows(shown, news_rows)
            return {"url": url, "title": None, "how": "scrape-cache"} if url else None
        if group == "papers":
            url = find_in_rows(shown, mdpi_rows)
            if url:
                return {"url": url, "title": None, "how": "mdpi-file"}
            if use_api and env.get("OPEN_ALEX_KEY"):
                hit = openalex_lookup(shown, env["OPEN_ALEX_KEY"], get)
                return {"url": hit[0], "title": hit[1], "how": "openalex"} if hit else None
            return None
        if not use_api:
            return None
        if platform == "Reddit" and env.get("REDDIT_CLIENT_ID") and env.get("REDDIT_CLIENT_SECRET"):
            token.setdefault("reddit", reddit_token(env))
            hit = reddit_lookup(shown, token["reddit"], get)
            return {"url": hit[0], "title": hit[1], "how": "reddit-search"} if hit else None
        if platform == "YouTube" and env.get("YOUTUBE_API_KEY"):
            hit = youtube_lookup(shown, env["YOUTUBE_API_KEY"], get)
            return {"url": hit[0], "title": hit[1], "how": "youtube-search"} if hit else None
    except Exception as e:  # noqa: BLE001 - เครือข่าย/โควตา/คีย์ผิด: ข้ามเอกสารนี้ (พิมพ์ชนิดข้อผิดพลาดเท่านั้น ไม่พิมพ์ URL ที่อาจมีคีย์)
        print(f"    ⚠️ หาลิงก์ไม่สำเร็จ ({type(e).__name__}) - ข้าม: {shown[:50]}")
    return None


def main():
    parser = argparse.ArgumentParser(description="⑯ เติมลิงก์เอกสารต้นทางของรอบเก่า (phase6_source_links.json)")
    parser.add_argument("--run", nargs="+", required=True, help="ชื่อโฟลเดอร์รอบใน main/output (ใส่ได้หลายรอบ)")
    parser.add_argument("--no-api", action="store_true", help="ใช้เฉพาะไฟล์ในเครื่อง (ไม่เรียก OpenAlex/Reddit/YouTube)")
    parser.add_argument("--force", action="store_true", help="หาใหม่ทั้งหมด (ปกติเก็บลิงก์ที่หาไว้แล้ว)")
    args = parser.parse_args()

    env = read_env()
    news_rows, mdpi_rows = load_news_cache(), load_mdpi()
    print(f"cache ข่าว {len(news_rows)} ชิ้น · MDPI {len(mdpi_rows)} ชิ้น · คีย์ที่พบ: {sorted(env) or '-'}")
    memo = {}
    for name in args.run:
        run_dir = OUTPUT / name
        if not run_dir.is_dir():
            print(f"❌ ไม่พบโฟลเดอร์รอบ {run_dir}")
            continue
        links, missing, summary = build_for_run(run_dir, news_rows, mdpi_rows, env, not args.no_api, memo, args.force)
        payload = {"_note": "ลิงก์ของเอกสารต้นทาง (หา-ย้อนหลังจากชื่อเรื่อง) - สร้างโดย tool/phase6_pdf_report/build_source_links.py",
                   "generated_at": datetime.now().isoformat(timespec="seconds"), "links": links, "unresolved": missing}
        (run_dir / LINKS_FILE).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ {name}: " + " · ".join(f"{g} {h}/{t}" for g, (h, t) in summary.items()) + f" -> {LINKS_FILE}")
        for t in missing:
            print(f"    ไม่พบลิงก์: {t[:70]}")


if __name__ == "__main__":
    main()
