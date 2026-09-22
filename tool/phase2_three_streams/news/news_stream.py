# -*- coding: utf-8 -*-
"""
Phase 2 — สายข่าว (News) — รวม News-Intl + News-Thai เป็นสายเดียว (2026-09-10)

**ทำไมรวม:** เดิมแยก 4 สาย (Paper/Social/News-Intl/News-Thai) เพราะกลัว prompt ขั้นสังเคราะห์รายงาน
ใหญ่เกิน (locale ไทย/สากลต่างกัน + ข้อมูลเยอะ) - พอมี generate_trend_report_mapreduce() (สรุปทีละ
บทความก่อน reduce) prompt ไม่โตตามจำนวนบทความอีก เหตุผลที่ต้องแยกจึงเหลือน้อยลงมาก เจ้าของงานตัดสินใจ
รวมเป็น 3 สาย: Paper, Social, News (2026-09-10) - ดู Backlog ข้อ 36 + Workflow v2

**สิ่งที่เก็บไว้:** ส่วน fetch แยก 2 แบบ (locale ไทย hl=th vs สากล hl=en - แก้ยาก ใช้ของเดิมที่
ทำงานได้) - merge หลัง fetch โดยติด tag source_region ('th' | 'intl') กับทุกบทความ/triplet เผื่ออยาก
ดูภายหลังว่าคลัสเตอร์ไหนหลักฐานมาจากฝั่งไหนมากกว่า

**LLM (2026-09-10):** select_top_news บังคับ Typhoon เองภายใน (เร็ว มี retry loop - Backlog ข้อ 22)
ที่เหลือ (queries/report/triplet/cluster naming/keywords) รันบน **nemotron-ultra-550b** ช็อตเดียว
(เดิม `use_nvidia(model=NEMOTRON_ULTRA)`) - ย้ายจาก DeepSeek+map-reduce ที่เจอ timeout roulette หนัก
(Backlog ข้อ 36/39) ระหว่างรอเครดิต OpenRouter (GPT-5.6-Luna)

🆕 (2026-09-15) เปลี่ยนทั้ง 2 จุดเป็น AWS Bedrock (`use_bedrock()`) แล้ว - เจ้าของงานสั่ง
เลิกใช้ Typhoon/NVIDIA LLM ทั้งหมด (ดู Detail/.../แผนเปลี่ยนโมเดล LLM — Bedrock + Typhoon.md)
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common import bootstrap
from common.bootstrap import (OUTPUTS, tf, select_top_news, scrape_article, extract_triplets_per_document,
                               build_trend_graph, summarize_trend_clusters, extract_strategic_keywords,
                               use_bedrock, verify_report_against_source, generate_trend_report,
                               MAX_ASSERTED_HALLUCINATIONS, prompt_run_config,
                               check_minimum_evidence)  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from news_intl_stream import generate_intl_queries, fetch_news_intl_pool  # noqa: E402
from news_th_stream import generate_th_queries, fetch_news_th_pool  # noqa: E402

TOPIC = "beauty and personal care trends"  # default - ผู้ใช้พิมพ์เองตอนรัน (prompt_run_config)
N_QUERIES_EACH = 3          # 3 intl + 3 thai
# select_top_news() รัน keyword pre-filter ในตัวเมื่อ pool > 30 รายการ - ตัวกรองนั้นใช้
# topic.lower().split() (คำอังกฤษ) เทียบ title ที่ปนไทย/สากล → เกือบไม่ตรงเลย เหลือ 2 รายการ
# (เจอจริง 2026-09-10 รอบแรก) → ต้องส่ง <= 30 รายการเพื่อ skip ตัวกรอง ให้ LLM layer② (Typhoon,
# เข้าใจความหมายจริง) เป็นตัวกรองเดียว - แบ่งโควตาให้ทั้ง 2 ฝั่งด้วย ไม่ใช่เอา 30 แรก (= สากลล้วน
# เพราะ dedup เรียง intl ก่อน)
SELECT_INTL = 20
SELECT_TH = 10
TOP_K_SCRAPE = 12
CONTENT_CHAR_LIMIT = 6000
MODEL_USED = f"{use_bedrock.MODEL_ID} (AWS Bedrock) — single-shot report"


def _dedup_by_link(items):
    seen, out = set(), []
    for it in items:
        lk = it.get("link", "")
        if lk and lk not in seen:
            seen.add(lk)
            out.append(it)
    return out


def run_news_stream(topic=TOPIC, n_queries_each=N_QUERIES_EACH, top_k=TOP_K_SCRAPE):
    print(f"หัวข้อ: {topic}")

    # --- 1. queries ทั้ง 2 ฝั่ง ---
    q_intl = generate_intl_queries(topic, n_queries_each)
    q_th = generate_th_queries(topic, n_queries_each)
    print(f"คำค้นสากล: {q_intl}")
    print(f"คำค้นไทย: {q_th}")
    if not q_intl and not q_th:
        print("❌ สร้างคำค้นไม่สำเร็จทั้ง 2 ฝั่ง")
        return None

    # --- 2. fetch ทั้ง 2 ฝั่ง + tag source_region ---
    pool_intl = fetch_news_intl_pool(q_intl) if q_intl else []
    for it in pool_intl:
        it["source_region"] = "intl"
    pool_th = fetch_news_th_pool(q_th) if q_th else []
    for it in pool_th:
        it["source_region"] = "th"

    pool = _dedup_by_link(pool_intl + pool_th)
    print(f"  ✅ pool รวม: {len(pool)} รายการ ({len(pool_intl)} สากล + {len(pool_th)} ไทย, dedup แล้ว)")
    if not pool:
        print("❌ ไม่เจอข่าวเลยทั้ง 2 ฝั่ง")
        return None

    # --- 3. select_top_news (Typhoon ภายใน) ---
    # ส่ง <= 30 รายการแบบแบ่งโควตา 2 ฝั่ง (skip keyword pre-filter ที่พังกับ pool ปนภาษา)
    select_pool = _dedup_by_link(pool_intl[:SELECT_INTL] + pool_th[:SELECT_TH])
    print(f"  🎯 ส่งเข้า select_top_news: {len(select_pool)} รายการ "
          f"({min(SELECT_INTL, len(pool_intl))} สากล + {min(SELECT_TH, len(pool_th))} ไทย)")
    top_news = select_top_news(topic, select_pool, top_k=top_k, kind="news")
    print(f"  🧠 เลือกมา {len(top_news)} รายการสำหรับ scrape")

    # --- 4. scrape ---
    scraped_data = []
    for article in top_news:
        link = article["link"]
        region = article.get("source_region", "")
        if link in tf.url_cache:
            cached = tf.url_cache[link]
            # 🆕 ตัด cached content ที่ CONTENT_CHAR_LIMIT ด้วย (บั๊กเดิม: cached article ไม่ถูกตัด
            # เหมือน scrape สด ทำให้ prompt พองถึง 56K - ดู Backlog ข้อ 36)
            scraped_data.append({"title": cached.get("title", article["title"]),
                                  "source": cached.get("source", article.get("source")),
                                  "link": link, "source_region": region,
                                  "content": (cached.get("cleaned_text", "") or "")[:CONTENT_CHAR_LIMIT]})
            print(f"  ⚡ [CACHE] {article['title'][:55]} [{region}]")
            continue
        try:
            print(f"  🌐 [SCRAPE] {article['title'][:55]} [{region}]")
            raw_text, decoded_url = scrape_article(link)
            text_clean = tf.process_and_clean_content(raw_text)
            if len(text_clean) > 150:
                text_clean = text_clean[:CONTENT_CHAR_LIMIT]
                scraped_data.append({"title": article["title"], "source": article["source"],
                                      "link": decoded_url, "source_region": region,
                                      "content": text_clean})
                tf.url_cache[link] = {"query": topic, "title": article["title"],
                                       "source": article["source"], "decoded_url": decoded_url,
                                       "raw_text": raw_text, "cleaned_text": text_clean,
                                       "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        except Exception as e:
            print(f"     ⚠️ scrape ล้มเหลว: {e}")

    if not scraped_data:
        print("❌ scrape ไม่ได้เลยสักบทความ")
        return None
    tf.save_scrape_cache(tf.url_cache)
    n_intl = sum(1 for a in scraped_data if a.get("source_region") == "intl")
    n_th = sum(1 for a in scraped_data if a.get("source_region") == "th")
    print(f"  📄 scrape สำเร็จ {len(scraped_data)} บทความ ({n_intl} สากล + {n_th} ไทย)")

    # --- 5. report — ขั้นเดียวที่รันบน nemotron-ultra-550b (ที่เหลือ Typhoon) ---
    # ultra จำเป็นเฉพาะ report: (1) รับ prompt ใหญ่ 46-80K ช็อตเดียว (2) example-bleed น้อยกว่า Typhoon
    # (เพิ่ม "Data Coverage Notice" เอง) - แต่ ultra ทำ JSON ไม่ได้ (query gen/triplet/cluster พัง)
    # จึงไม่ครอบทั้ง run ด้วย ultra
    print(f"  🧠 สังเคราะห์เป็นรายงาน ({len(scraped_data)} บทความ) [{use_bedrock.MODEL_ID}]...")
    with use_bedrock():  # 🆕 (2026-09-15) เปลี่ยนจาก NVIDIA nemotron-ultra -> AWS Bedrock
        # 🆕 (2026-09-16) prompt ไม่มีตัวอย่างฝัง + บังคับอ้างอิง (Ref N) แทน prompt ต้นฉบับ - replay บทความ News จริง
        # 12 ชิ้นชุดเดียวกัน: prompt ต้นฉบับโดนฟ้อง 42, 36 (มี Post-COVID/Mass-Prestige จากตัวอย่าง) prompt นี้ 13, 26
        report = generate_trend_report(topic, scraped_data)
    if not report or not report.strip():
        print("❌ สังเคราะห์รายงานไม่สำเร็จ (ว่างเปล่า)")
        return None

    # --- 6-9. triplets -> clustering -> cluster naming -> keywords ---
    # 🆕 (2026-09-15, audit M3 ฉบับเต็ม) สกัดทีละเอกสารพร้อมประโยคหลักฐานจากต้นฉบับ แทนการสกัดจากรายงาน
    print("  🧠 สกัด triplet ทีละเอกสาร (พร้อมประโยคหลักฐานจากต้นฉบับ)...")
    triplets, triplet_provenance = extract_triplets_per_document(scraped_data)

    print("  🕸️ Louvain clustering...")
    G, clusters = build_trend_graph(triplets)
    print(f"     ได้ {len(clusters)} คลัสเตอร์")

    print("  🧠 ตั้งชื่อคลัสเตอร์...")
    df_trends = summarize_trend_clusters(clusters, triplets, top_n=5)
    if df_trends.empty:
        print("❌ ตั้งชื่อคลัสเตอร์ไม่สำเร็จเลย")
        return None

    print(f"  🧠 แตกคีย์เวิร์ด ({len(df_trends)} เทรนด์)...")
    df_keywords = extract_strategic_keywords(df_trends)

    return {
        "topic": topic, "queries_intl": q_intl, "queries_th": q_th, "pool_size": len(pool),
        "pool_intl": len(pool_intl), "pool_th": len(pool_th),
        "n_scraped": len(scraped_data), "n_scraped_intl": n_intl, "n_scraped_th": n_th,
        "report": report, "n_triplets": len(triplets), "n_clusters": len(clusters),
        "n_triplets_extracted": len(triplet_provenance), "triplet_provenance": triplet_provenance,
        "df_trends": df_trends, "df_keywords": df_keywords,
        "scraped_data": scraped_data,
    }


if __name__ == "__main__":
    print("=" * 70)
    print(f"News stream (รวม Intl + Thai) — {use_bedrock.MODEL_ID} (AWS Bedrock)")
    print("=" * 70)

    topic, _ = prompt_run_config(default_topic=TOPIC, ask_years=False)

    # 🆕 (2026-09-11) outer = Typhoon (query gen/select/triplet/cluster/keyword) - NVIDIA NIM ทำ JSON
    # ไม่ได้ทุกรุ่น: ultra query-gen คืน {"queries{":["}}] → 0 intl queries → pool 100% ไทยนอกเรื่อง
    # (Backlog ข้อ 39) - เฉพาะ report pop ออกไป ultra ใน run_news_stream()
    t0 = time.time()
    with use_bedrock():  # 🆕 (2026-09-15) เปลี่ยนจาก Typhoon -> AWS Bedrock
        result = run_news_stream(topic=topic)
    elapsed = time.time() - t0

    if result is None:
        print("❌ ล้มเหลว - ไม่มีผลลัพธ์")
        sys.exit(1)

    # 🆕 (2026-09-12, audit m2) กัน "สำเร็จ" ทั้งที่ scrape/สกัดได้แทบไม่มีอะไรเลย
    if not check_minimum_evidence("News", result["n_scraped"], result["n_triplets"], result["n_clusters"]):
        sys.exit(1)

    # ตาข่ายนิรภัย: verify กับข้อความต้นฉบับเต็ม (ไม่ใช่สรุป map)
    verification = None
    try:
        full_texts = [{"title": a["title"], "content": a["content"]} for a in result["scraped_data"]]
        verification = verify_report_against_source(result["report"], full_texts)
        # 🆕 (2026-09-12, audit M3) เดิมคำนวณ verification แล้วเก็บไว้เฉยๆ ไม่เคยหยุดไปป์ไลน์เลย
        n_asserted = len(verification["asserted"])
        if n_asserted > MAX_ASSERTED_HALLUCINATIONS:
            print(f"❌ พบคำที่ดูเหมือนหลอน {n_asserted} คำ (เกิน {MAX_ASSERTED_HALLUCINATIONS}) - "
                  f"ดูรายการ: {verification['asserted']}")
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        print(f"⚠️ verification ล้มเหลว (ไม่กระทบผลหลัก): {e}")

    out_path = OUTPUTS / "phase2_news_stream_result.json"
    payload = {k: v for k, v in result.items() if k not in ("df_trends", "df_keywords", "scraped_data")}
    payload["_model_used"] = MODEL_USED
    payload["_verification"] = verification
    payload["_elapsed_seconds"] = round(elapsed, 1)
    payload["trends"] = result["df_trends"].to_dict(orient="records")
    payload["keywords"] = result["df_keywords"].to_dict(orient="records")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(result["df_trends"].to_string())
    print("=" * 80)
    if verification:
        print(f"\n🔍 verification: asserted={verification['asserted']}  "
              f"negated_safe={verification['negated_safe']}")
    print(f"\n✅ Saved -> {out_path}  (ใช้เวลา {elapsed / 60:.1f} นาที)")
