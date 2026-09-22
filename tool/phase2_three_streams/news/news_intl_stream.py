# -*- coding: utf-8 -*-
"""
Phase 2 — สายข่าวต่างประเทศ (News-Intl)
ดู workspace/phase2_three_streams/README.md และ
Detail/05 งานที่ยังไม่ได้ทำ/Workflow v2 — แยกสายแล้วรวม.md

เป้าหมาย: แยกสายข่าวออกจาก Paper (ที่เคยปนกันใน config/rss_feeds.json) เป็นสายของตัวเอง
ฝั่งต่างประเทศ - ใช้ RSS ที่เป็นอังกฤษ/สากลอยู่แล้วโดยธรรมชาติ (B2B_Industry + B2C_Review + Mintel
จาก Market) ไม่รวม Scientific_Papers (เป็นของสาย Paper แล้ว) และไม่รวม baramizilab.co.th/
brandinside.asia (เป็นของสาย News-Thai แทน)

หลักการเดียวกับที่ทำให้ Paper stream ใช้ locale hl=en&gl=US แทน hl=th&gl=TH - Google News
domain-targeted search ของสาย Paper พิสูจน์แล้วว่า locale ไทย (ที่ pipeline หลัก hardcode ไว้ทุกจุด)
บล็อกเนื้อหาสากลจนเหลือ 0 ผลลัพธ์ - ข่าวอุตสาหกรรมความงามสากลก็มีความเสี่ยงแบบเดียวกัน จึงใช้
locale อังกฤษที่นี่ด้วย (ไม่ใช้ domain-targeted search เลย เพราะ RSS 11 แหล่งครอบคลุมพอแล้ว
ใช้ Google News แบบ general search เสริมแทน)

**ใช้ฟังก์ชันเดิมจาก trend_final.py ทั้งหมด** (ผ่าน bootstrap) เหมือน paper_stream.py/social_stream.py
"""
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import (PROJECT_ROOT, OUTPUTS, tf, safe_json_parse, select_top_news, scrape_article,
                               extract_beauty_triplets, build_trend_graph, summarize_trend_clusters,
                               extract_strategic_keywords, prompt_run_config, generate_trend_report)  # noqa: E402

import feedparser  # noqa: E402
import requests  # noqa: E402

TOPIC = "beauty and personal care trends"  # default - ผู้ใช้พิมพ์เองตอนรัน (ปกติรันผ่าน news_stream.py แทน)
N_QUERIES = 3
YEARS_BACK = 2
TOP_K_SCRAPE = 8
CONTENT_CHAR_LIMIT = 6000  # ข่าวสั้นกว่าเปเปอร์วิชาการมาก ใช้ limit เดิมของ pipeline หลักพอ

# RSS 11 แหล่งที่เป็นอังกฤษ/สากลอยู่แล้วโดยธรรมชาติ (ตัด Scientific_Papers ออก - เป็นของสาย Paper แล้ว
# ตัด baramizilab.co.th/brandinside.asia ออก - เป็นของสาย News-Thai แทน)
INTL_RSS_GROUPS = ("B2B_Industry", "B2C_Review")
INTL_MARKET_URL = "https://www.mintel.com/insights/beauty-and-personal-care/feed/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

SYSTEM_PROMPT_QUERIES = """You are a beauty industry trade journalist searching international
industry news, market research, and consumer-review publications for coverage relevant to this topic.

IMPORTANT: International trade press does not write country-specific or future-year-specific
coverage (nobody publishes an article titled "Thailand body wash trends 2030"). It covers global
product/ingredient/format trends instead. Strip out any country name and any specific year from the
topic - generate queries about the underlying PRODUCT CATEGORY and its trends only. The articles
found will be evaluated afterward for relevance to the target market; they don't need to mention it
themselves.

Generate search queries a trade journalist would actually type - industry/market-research language,
not consumer slang and not scientific-paper language.

Rules:
- 2-5 words, like a real search query
- NEVER include a country name or a specific/future year
- Cover different angles: market trends, product launches, ingredient movements, consumer sentiment

Example: topic "Trend Body Wash Thailand 2030" -> queries about "body wash" / "shower gel" /
"personal cleansing" trends in general, NOT "body wash Thailand 2030".

Answer JSON only: {"queries": ["query 1", "query 2", ...]}
"""


def generate_intl_queries(topic, n):
    try:
        response = tf.client.chat.completions.create(
            model=tf.MODEL_NAME_META,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_QUERIES},
                {"role": "user", "content": f"Topic: '{topic}'\nGenerate {n} queries."},
            ],
            temperature=0.3,
            max_tokens=800,  # 🆕 กันเผื่อโมเดลที่มี thinking ฝัง (ดู Backlog ข้อ 29) - เดิมไม่มี
            response_format={"type": "json_object"},
        )
        parsed = safe_json_parse(response.choices[0].message.content)
        return parsed.get("queries", []) if parsed else []
    except Exception as e:
        print(f"⚠️ Error generating queries: {e}")
        return []


def fetch_news_intl_pool(queries, years_back=YEARS_BACK):
    all_news = []
    seen_links = set()

    # 1. RSS ตรงจาก B2B_Industry + B2C_Review + Mintel
    print("  📡 ดึง RSS (B2B_Industry + B2C_Review + Mintel)...")
    rss_groups, _ = tf.load_feed_config()
    urls = [u for g in INTL_RSS_GROUPS for u in rss_groups.get(g, [])] + [INTL_MARKET_URL]
    for url in urls:
        try:
            feed = feedparser.parse(url)
            n = 0
            for entry in feed.entries[:15]:
                link = entry.get("link", "")
                if link and link not in seen_links:
                    seen_links.add(link)
                    all_news.append({"title": entry.get("title", "No Title"), "link": link,
                                      "source": "Intl RSS"})
                    n += 1
            print(f"     {url} -> {n} รายการ")
        except Exception as e:
            print(f"     ⚠️ ดึง {url} ไม่ได้: {e}")

    # 2. Google News แบบ general search, locale อังกฤษ (ไม่จำกัดโดเมน - RSS ครอบคลุมพอแล้ว)
    base_url = "https://news.google.com/rss/search"
    current_year = datetime.now().year
    for q in queries:
        print(f"  🔍 ค้น Google News (Intl) สำหรับ: '{q}'...")
        for i in range(years_back):
            start_year, end_year = current_year - i - 1, current_year - i
            time_query = f"{q} after:{start_year}-01-01 before:{end_year}-01-01"
            url = f"{base_url}?q={urllib.parse.quote(time_query)}&hl=en&gl=US&ceid=US:en"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=30)
                feed = feedparser.parse(resp.content)
                for entry in feed.entries:
                    if entry.link not in seen_links:
                        seen_links.add(entry.link)
                        all_news.append({"title": entry.title, "link": entry.link,
                                          "source": "Google News (Intl)"})
            except Exception as e:
                print(f"     ⚠️ {e}")

    print(f"  ✅ รวมทั้งหมด {len(all_news)} รายการ")
    return all_news


def run_news_intl_stream(topic=TOPIC, n_queries=N_QUERIES, top_k=TOP_K_SCRAPE):
    print(f"หัวข้อ: {topic}")
    queries = generate_intl_queries(topic, n_queries)
    print(f"คำค้นที่สร้าง: {queries}")
    if not queries:
        print("❌ สร้างคำค้นไม่สำเร็จ")
        return None

    pool = fetch_news_intl_pool(queries)
    if not pool:
        print("❌ ไม่เจอข่าวเลย")
        return None

    top_news = select_top_news(topic, pool, top_k=top_k, kind="news")
    print(f"  🧠 เลือกมา {len(top_news)} รายการสำหรับ scrape")

    scraped_data = []
    for article in top_news:
        link = article["link"]
        if link in tf.url_cache:
            cached = tf.url_cache[link]
            scraped_data.append({"title": cached.get("title", article["title"]),
                                  "source": cached.get("source", article.get("source")),
                                  "link": link, "content": cached.get("cleaned_text", "")})
            print(f"  ⚡ [CACHE] {article['title'][:60]}")
            continue
        try:
            print(f"  🌐 [SCRAPE] {article['title'][:60]}")
            raw_text, decoded_url = scrape_article(link)  # bootstrap: แก้บั๊ก Apify Run object แล้ว
            text_clean = tf.process_and_clean_content(raw_text)
            if len(text_clean) > 150:
                text_clean = text_clean[:CONTENT_CHAR_LIMIT]
                scraped_data.append({"title": article["title"], "source": article["source"],
                                      "link": decoded_url, "content": text_clean})
                tf.url_cache[link] = {"query": topic, "title": article["title"], "source": article["source"],
                                       "decoded_url": decoded_url, "raw_text": raw_text,
                                       "cleaned_text": text_clean,
                                       "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        except Exception as e:
            print(f"     ⚠️ scrape ล้มเหลว: {e}")

    if not scraped_data:
        print("❌ scrape ไม่ได้เลยสักบทความ")
        return None
    tf.save_scrape_cache(tf.url_cache)

    print(f"  🧠 สังเคราะห์เป็นรายงาน ({len(scraped_data)} บทความ)...")
    # 🆕 (2026-09-16) prompt ไม่มีตัวอย่างฝัง + บังคับอ้างอิง (Ref N) เหมือนทุกสายในไปป์ไลน์หลัก - ดู generate_trend_report()
    report = generate_trend_report(topic, scraped_data)
    if not report or not report.strip():
        print("❌ สังเคราะห์รายงานไม่สำเร็จ (ว่างเปล่า)")
        return None

    print("  🧠 สกัด triplet...")
    triplets = extract_beauty_triplets(report)  # bootstrap: เพิ่ม max_tokens แล้ว (ข้อ 29)
    print(f"     ได้ {len(triplets)} triplets")

    print("  🕸️ Louvain clustering...")
    G, clusters = build_trend_graph(triplets)
    print(f"     ได้ {len(clusters)} คลัสเตอร์")

    print("  🧠 ตั้งชื่อคลัสเตอร์...")
    df_trends = summarize_trend_clusters(clusters, triplets, top_n=5)  # bootstrap: เพิ่ม max_tokens แล้ว
    if df_trends.empty:
        print("❌ ตั้งชื่อคลัสเตอร์ไม่สำเร็จเลย")
        return None

    print(f"  🧠 แตกคีย์เวิร์ด ({len(df_trends)} เทรนด์)...")
    df_keywords = extract_strategic_keywords(df_trends)  # bootstrap: เพิ่ม max_tokens แล้ว (ข้อ 29)

    return {
        "topic": topic, "queries": queries, "pool_size": len(pool), "n_scraped": len(scraped_data),
        "report": report, "n_triplets": len(triplets), "n_clusters": len(clusters),
        "df_trends": df_trends, "df_keywords": df_keywords,
    }


if __name__ == "__main__":
    # ⚠️ ปกติรันผ่าน news_stream.py (สายรวม 3 สาย) - ไฟล์นี้เก็บไว้ debug ฝั่งสากลเดี่ยวๆ
    topic, _ = prompt_run_config(default_topic=TOPIC, ask_years=False)
    from common.bootstrap import use_bedrock
    with use_bedrock():  # 🆕 (2026-09-15) เปลี่ยนจาก NVIDIA nemotron-ultra -> AWS Bedrock
        result = run_news_intl_stream(topic=topic)

    if result is None:
        raise SystemExit(1)

    out_path = OUTPUTS / "phase2_news_intl_stream_result.json"
    import json
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "topic": result["topic"], "queries": result["queries"], "pool_size": result["pool_size"],
            "n_scraped": result["n_scraped"], "report": result["report"],
            "n_triplets": result["n_triplets"], "n_clusters": result["n_clusters"],
            "trends": result["df_trends"].to_dict(orient="records"),
            "keywords": result["df_keywords"].to_dict(orient="records"),
        }, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(result["df_trends"].to_string())
    print("=" * 80)
    print(f"\nSaved -> {out_path}")
