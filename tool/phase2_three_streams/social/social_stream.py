# -*- coding: utf-8 -*-
"""
Phase 2 — สาย Social (Pantip + Reddit รวมกัน)
ดู workspace/phase2_three_streams/README.md และ
Detail/05 งานที่ยังไม่ได้ทำ/Workflow v2 — แยกสายแล้วรวม.md

เป้าหมาย: รวมเนื้อหาจาก Pantip (ไทย) + Reddit (สากล) + YouTube (ไทย) เป็นสายเดียว → สกัด triplet +
Louvain clustering แบบเดียวกับสาย Paper (Phase 1)

**ใช้ฟังก์ชันเดิมจาก trend_final.py ทั้งหมด** (ผ่าน bootstrap) เหมือน paper_stream.py:
  generate_trend_report_with_llm, extract_beauty_triplets, build_trend_graph,
  summarize_trend_clusters, extract_strategic_keywords
ส่วนการดึงเนื้อหาดิบ ใช้ discover_pantip.py + discover_reddit.py + discover_youtube.py (สำเนาในโฟลเดอร์
นี้) ตรงๆ ไม่เขียนใหม่

หมายเหตุ: Pantip/YouTube ใช้คำค้นไทย, Reddit ใช้คำค้นอังกฤษ - ตามหลักการ "ไม่แปลข้ามภาษา"

🆕 (2026-09-10, Backlog ข้อ 39):
- **เอา YouTube กลับเข้าสาย Social** (เคยถอด 2026-08-28 เพราะกรองคลิปเก่าไม่ได้) - เฟส 0 แก้แล้ว
  (`publishedAfter` + `published_at` + กรองซ้ำ) / transcript: caption เป็นหลัก (~1.5s/คลิป) whisper สำรอง
- **LLM: nemotron-ultra-550b ช็อตเดียว** (เดิม `use_nvidia(model=NEMOTRON_ULTRA)` ใน __main__) - ลอง
  nemotron-super-120b (พัง Longevity v2 JSON 5/5) และ DeepSeek + map-reduce (timeout roulette หนัก)
  มาแล้ว - ultra-550b รับ report ใหญ่ช็อตเดียว, Longevity v2 JSON ผ่าน, เสถียร ~110s/call
  🆕 (2026-09-15) เปลี่ยนเป็น AWS Bedrock (`use_bedrock()`) แล้ว - เจ้าของงานสั่งเลิก
  ใช้ Typhoon/NVIDIA LLM ทั้งหมด (ดู Detail/.../แผนเปลี่ยนโมเดล LLM — Bedrock + Typhoon.md)

✅ ตัวกรองอายุเนื้อหา (ทำแล้ว 2026-09-10 - ปิด doc TODO):
- Reddit: กรอง `created_utc` < 2 ปี → เรียง engagement (score + comments×2) → เอา top 10
- YouTube: `publishedAfter` = now − 2 ปี + กรอง `publishedAt` ซ้ำฝั่งเรา (เอา ≤7 คลิป)
- Pantip: ยังไม่เก็บวันที่กระทู้ (TODO เล็กแยก) - เอาทั้งหมด
"""
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import (PROJECT_ROOT, OUTPUTS, tf, safe_json_parse,
                               use_bedrock, verify_report_against_source, MAX_ASSERTED_HALLUCINATIONS,
                               extract_triplets_per_document, build_trend_graph, summarize_trend_clusters,
                               extract_strategic_keywords, prompt_run_config, generate_trend_report,
                               check_minimum_evidence)  # noqa: E402

# ใช้ฟังก์ชันที่มีอยู่แล้วในโฟลเดอร์เดียวกันตรงๆ - ไม่เขียนกลไกดึงข้อมูลใหม่
import discover_pantip as dp  # noqa: E402
import discover_reddit as dr  # noqa: E402
import discover_youtube as dy  # noqa: E402  (🆕 2026-09-10 - เอา YouTube กลับเข้าสาย Social, Backlog ข้อ 39)

TOPIC = "beauty and personal care trends"  # default - ผู้ใช้พิมพ์เองตอนรัน (prompt_run_config)
N_QUERIES = 4  # เท่ากับที่แต่ละ pilot ใช้เดิม
YEARS_BACK = 2  # กรองเนื้อหาเก่ากว่านี้ (Reddit ผ่าน created_utc, YouTube ผ่าน publishedAfter)
REDDIT_TOP_K = 10  # หลังกรองอายุ เอาโพสต์ที่ engagement สูงสุดกี่โพสต์
YT_MAX_VIDEOS = 7  # เอาคลิปที่ได้ transcript กี่คลิป (คุมขนาด prompt report)
YT_TRANSCRIPT_CHARS = 3000  # ตัด transcript แต่ละคลิปที่กี่ตัวอักษร (คุมขนาด prompt)


def fetch_social_scraped_data(topic, n_queries=N_QUERIES):
    """คืนค่า list ของ dict {"title", "source", "link", "content"} รูปแบบเดียวกับที่
    generate_trend_report_with_llm() ต้องการ - แปลงผลจาก Pantip/Reddit ให้เข้ากับรูปแบบนี้
    เพื่อเดินตาม pipeline เดียวกับสาย Paper (scrape -> synthesize report -> extract triplets)"""
    scraped_data = []

    # --- Pantip (ไทย) ---
    print("=== ดึงข้อมูล Pantip ===")
    pantip_queries = [q for q in map(dp.clean_pantip_query, dp.generate_thai_queries(topic, n_queries)) if q]
    print(f"คำค้นไทยที่สร้าง: {pantip_queries}")
    if pantip_queries:
        pantip_results = dp.search_pantip(pantip_queries)
        for r in pantip_results:
            # 🆕 (2026-09-15) หน้าที่ค้นไม่เจอกระทู้เลยมีแต่เมนูเว็บ เคยหลุดเข้ารายงาน 2 จาก 4 หน้า
            if not r.get("raw_text") or not r.get("topic_links"):
                print(f"    ⏭️  ข้าม Pantip '{r['query']}' (ไม่เจอกระทู้)")
                continue
            scraped_data.append({
                "title": f"Pantip: {r['query']}",
                "source": "Pantip",
                "link": ", ".join(r.get("topic_links", [])[:3]) or "https://pantip.com",
                "content": dp.extract_search_results_text(r["raw_text"])[:6000],
            })
    else:
        print("⚠️ สร้างคำค้น Pantip ไม่สำเร็จ - ข้ามสายนี้")

    # --- Reddit (สากล) ---
    print("\n=== ดึงข้อมูล Reddit ===")
    if not dr.REDDIT_CLIENT_ID or not dr.REDDIT_CLIENT_SECRET:
        print("⚠️ ไม่มี REDDIT_CLIENT_ID/SECRET ใน .env - ข้ามสายนี้")
    else:
        reddit_queries = dr.generate_english_queries(topic, n_queries)
        print(f"คำค้นอังกฤษที่สร้าง: {reddit_queries}")
        if reddit_queries:
            # 🆕 (2026-09-15) ค้นเฉพาะ subreddit ความงาม - เดิมค้นทั้ง Reddit แล้ว 5 จาก 10 โพสต์ที่ติดอันดับ
            # engagement เป็นเรื่องนอกหัวข้อ (หนัง, เดท, แฟนกินข้าว)
            reddit_results = dr.search_reddit(reddit_queries, subreddits=dr.BEAUTY_SUBREDDITS)
            # 🆕 (2026-09-10) รวมโพสต์ทั้งหมด → กรองอายุ (created_utc < YEARS_BACK ปี) → เรียง
            # engagement (score + comments×2) → เอา top REDDIT_TOP_K - ปิด doc TODO เรื่อง Reddit
            # age filter (เดิม 44% เก่ากว่า 1 ปี, เก่าสุด 9.5 ปี) + คุมจำนวนไม่ให้ท่วม prompt
            cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=365 * YEARS_BACK)).timestamp()
            all_posts, seen_ids, seen_titles = [], set(), set()
            for r in reddit_results:
                for p in r.get("posts", []):
                    pid = p.get("permalink") or p.get("title")
                    # 🆕 (2026-09-15) กันโพสต์เดียวกันที่ cross-post คนละ subreddit (เคยเข้ารายงานซ้ำ 2 ครั้ง)
                    title_key = " ".join(p.get("title", "").lower().split())
                    if pid in seen_ids or title_key in seen_titles:
                        continue
                    seen_ids.add(pid)
                    seen_titles.add(title_key)
                    cu = p.get("created_utc")
                    if cu is not None and cu < cutoff_ts:
                        continue  # เก่าเกิน YEARS_BACK
                    all_posts.append(p)
            all_posts.sort(key=lambda p: (p.get("score", 0) or 0) + 2 * (p.get("num_comments", 0) or 0),
                            reverse=True)
            kept = all_posts[:REDDIT_TOP_K]
            n_old = sum(1 for r in reddit_results for p in r.get("posts", [])) - len(all_posts)
            print(f"  Reddit: {len(all_posts)} โพสต์ในกรอบ {YEARS_BACK} ปี "
                  f"(ตัดเก่า/ซ้ำ {n_old}) → เอา top {len(kept)} ตาม engagement")
            for p in kept:
                body = f"{p['title']}\n{p['selftext']}" if p.get("selftext") else p["title"]
                # 🆕 (2026-09-15) เนื้อหาจริงของกระทู้ถาม/กระทู้โหวตอยู่ในคอมเมนต์ (ดู dr.fetch_top_comments)
                try:
                    comments = dr.fetch_top_comments(p["id"]) if p.get("id") else ""
                except Exception as e:
                    print(f"    ⚠️ ดึงคอมเมนต์ไม่ได้ '{p['title'][:40]}': {e}")
                    comments = ""
                if comments:
                    body += f"\n\nTop comments (upvotes in parentheses):\n{comments}"
                scraped_data.append({
                    "title": f"Reddit: {p['title'][:80]}",
                    "source": f"Reddit {p.get('subreddit', '')}",
                    "link": p.get("permalink", "https://reddit.com"),
                    "content": body,
                    "source_region": "intl",
                    "published_at": (datetime.fromtimestamp(p["created_utc"], timezone.utc).isoformat()
                                      if p.get("created_utc") else ""),
                })
        else:
            print("⚠️ สร้างคำค้น Reddit ไม่สำเร็จ - ข้ามสายนี้")

    # --- YouTube (ไทย) 🆕 (2026-09-10, Backlog ข้อ 39) ---
    print("\n=== ดึงข้อมูล YouTube ===")
    if not dy.YOUTUBE_API_KEY:
        print("⚠️ ไม่มี YOUTUBE_API_KEY ใน .env - ข้ามสายนี้")
    else:
        yt_queries = dy.generate_thai_queries(topic, dy.N_QUERIES)
        print(f"คำค้น YouTube (ไทย): {yt_queries}")
        yt_videos, seen_vid = [], set()
        for q in yt_queries:
            for v in dy.search_youtube(q, dy.MAX_VIDEOS_PER_QUERY, years_back=YEARS_BACK):
                if v["video_id"] not in seen_vid:
                    seen_vid.add(v["video_id"])
                    yt_videos.append(v)
        print(f"  เจอ {len(yt_videos)} คลิป (ในกรอบ {YEARS_BACK} ปี) - ดึง transcript "
              f"(caption เป็นหลัก ~1.5s/คลิป, whisper สำรองเฉพาะที่ปิด caption)...")
        n_ok = 0
        for v in yt_videos:
            if n_ok >= YT_MAX_VIDEOS:
                break
            t0 = time.time()
            transcript, caption_source = dy.get_transcript(v)
            if transcript and len(transcript) > 100:
                # 🆕 (2026-09-15) บอก LLM ผ่านชื่อเอกสาร (prompt รายงานและตัวสกัด triplet แสดง Title ด้วย) ว่าเป็น
                # ข้อความถอดเสียงอัตโนมัติ - รอบก่อน LLM เดาคำเพี้ยน "ไทอม" เป็น Niacinamide/Tranexamic Acid
                asr_note = ("" if caption_source == "manual_caption"
                            else " [automatic speech-to-text transcript: product/ingredient names may be misrecognized]")
                scraped_data.append({
                    "title": f"YouTube: {v['title'][:80]}{asr_note}",
                    "source": "YouTube",
                    "link": v["url"],
                    "content": transcript[:YT_TRANSCRIPT_CHARS],
                    "source_region": "th",
                    "published_at": v.get("published_at", ""),
                    "caption_source": caption_source,
                })
                n_ok += 1
                print(f"    ✅ [{n_ok}] {v['title'][:50]} ({len(transcript)} ตัวอักษร, {time.time()-t0:.0f}s)")
            else:
                print(f"    ⏭️  ข้าม (transcript ว่าง/สั้นเกิน): {v['title'][:50]}")

    return scraped_data


def run_social_stream(topic=TOPIC, n_queries=N_QUERIES):
    print(f"หัวข้อ: {topic}")
    scraped_data = fetch_social_scraped_data(topic, n_queries)
    print(f"\nรวมเนื้อหาที่ดึงได้: {len(scraped_data)} ชิ้น "
          f"({sum(1 for s in scraped_data if s['source']=='Pantip')} จาก Pantip, "
          f"{sum(1 for s in scraped_data if 'Reddit' in s['source'])} จาก Reddit)")
    if not scraped_data:
        print("❌ ไม่ได้เนื้อหาจากทั้ง 2 แหล่งเลย")
        return None

    print(f"\n🧠 สังเคราะห์เป็นรายงาน [{use_bedrock.MODEL_ID}]...")
    with use_bedrock():  # 🆕 (2026-09-15) เปลี่ยนจาก NVIDIA nemotron-ultra -> AWS Bedrock
        # 🆕 (2026-09-16) prompt ไม่มีตัวอย่างฝัง + บังคับอ้างอิง (Ref N) แทน prompt ต้นฉบับของ trend_final.py -
        # RCA 2026-09-15: ต้นฉบับดันให้แต่ง PDRN/market share/ความรู้นอกข้อมูล ดู generate_trend_report()
        social_report = generate_trend_report(topic, scraped_data)
    if not social_report or not social_report.strip():
        print("❌ สังเคราะห์รายงานไม่สำเร็จ (ว่างเปล่า)")
        return None

    # 🆕 (2026-09-15, audit M3 ฉบับเต็ม) สกัดทีละเอกสารพร้อมประโยคหลักฐานจากต้นฉบับ แทนการสกัดจากรายงาน -
    # หลักฐานจาก Pantip/YouTube เป็นภาษาไทยได้ เพราะเช็คกับเอกสารภาษาเดิม
    print("🧠 สกัด triplet ทีละเอกสาร (พร้อมประโยคหลักฐานจากต้นฉบับ)...")
    triplets, triplet_provenance = extract_triplets_per_document(scraped_data)

    print("🕸️ Louvain clustering...")
    G, clusters = build_trend_graph(triplets)
    print(f"   ได้ {len(clusters)} คลัสเตอร์")

    print("🧠 ตั้งชื่อคลัสเตอร์...")
    df_trends = summarize_trend_clusters(clusters, triplets, top_n=5)  # bootstrap: เพิ่ม max_tokens แล้ว
    if df_trends.empty:
        print("❌ ตั้งชื่อคลัสเตอร์ไม่สำเร็จเลย")
        return None

    print(f"🧠 แตกคีย์เวิร์ด ({len(df_trends)} เทรนด์)...")
    df_keywords = extract_strategic_keywords(df_trends)  # bootstrap: เพิ่ม max_tokens แล้ว (ข้อ 29)

    return {
        "topic": topic, "n_scraped": len(scraped_data), "social_report": social_report,
        "n_triplets": len(triplets), "n_clusters": len(clusters),
        "n_triplets_extracted": len(triplet_provenance), "triplet_provenance": triplet_provenance,
        "df_trends": df_trends, "df_keywords": df_keywords, "scraped_data": scraped_data,
    }


if __name__ == "__main__":
    import json
    import time as _t

    topic, _ = prompt_run_config(default_topic=TOPIC, ask_years=False)

    # 🆕 (2026-09-11) outer = Typhoon (query gen/select/triplet/cluster/keyword) - NVIDIA NIM ทำ JSON
    # ไม่ได้ทุกรุ่น (Backlog ข้อ 39) - เฉพาะ report pop ออกไป ultra-550b ใน run_social_stream()
    # ประวัติ: super-120b พัง Longevity v2 JSON / DeepSeek + map-reduce timeout roulette / ultra query-gen
    # คืน JSON พัง → ลงเอยที่ report=ultra, ที่เหลือ=Typhoon
    t0 = _t.time()
    with use_bedrock():  # 🆕 (2026-09-15) เปลี่ยนจาก Typhoon -> AWS Bedrock
        result = run_social_stream(topic=topic)
    elapsed = _t.time() - t0

    if result is None:
        raise SystemExit(1)

    # 🆕 (2026-09-12, audit m2) กัน "สำเร็จ" ทั้งที่ scrape/สกัดได้แทบไม่มีอะไรเลย
    if not check_minimum_evidence("Social", result["n_scraped"], result["n_triplets"], result["n_clusters"]):
        raise SystemExit(1)

    # ตาข่ายนิรภัย: verify รายงานกับข้อความต้นฉบับเต็ม
    verification = None
    try:
        full_texts = [{"title": s["title"], "content": s["content"]} for s in result["scraped_data"]]
        verification = verify_report_against_source(result["social_report"], full_texts)
        # 🆕 (2026-09-15) สาย Social แค่เตือน ไม่หยุดไปป์ไลน์ (เจ้าของงานสั่ง) - ต้นทางส่วนใหญ่เป็นภาษาไทย แต่ตัวตรวจ
        # เทียบคำอังกฤษแบบตรงตัว ตัวเลขจึงวัดความต่างของภาษา/ป้ายหัวข้อมากกว่าการหลอนจริง (RCA 2026-09-15: ใน 46 คำ
        # ที่ฟ้อง หลอนจริงแค่ ~3-4 คำ) - รายการคำยังบันทึกใน _verification ของไฟล์ผลลัพธ์ให้ตรวจเองได้
        n_asserted = len(verification["asserted"])
        if n_asserted > MAX_ASSERTED_HALLUCINATIONS:
            print(f"⚠️ ตัวตรวจฟ้อง {n_asserted} คำ (เกิน {MAX_ASSERTED_HALLUCINATIONS}) - สาย Social ไม่หยุดไปป์ไลน์ "
                  f"ดูรายการใน _verification ของไฟล์ผลลัพธ์: {verification['asserted']}")
    except Exception as e:
        print(f"⚠️ verification ล้มเหลว (ไม่กระทบผลหลัก): {e}")

    out_path = OUTPUTS / "phase2_social_stream_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "_model_used": f"{use_bedrock.MODEL_ID} (AWS Bedrock) — single-shot report",
            "_verification": verification,
            "_elapsed_seconds": round(elapsed, 1),
            "topic": result["topic"], "n_scraped": result["n_scraped"],
            "social_report": result["social_report"], "n_triplets": result["n_triplets"],
            "n_clusters": result["n_clusters"],
            "n_triplets_extracted": result["n_triplets_extracted"],
            "triplet_provenance": result["triplet_provenance"],
            "trends": result["df_trends"].to_dict(orient="records"),
            "keywords": result["df_keywords"].to_dict(orient="records"),
        }, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(result["df_trends"].to_string())
    print("-" * 80)
    print(result["df_keywords"].to_string())
    print("=" * 80)
    print(f"\nSaved -> {out_path}")
