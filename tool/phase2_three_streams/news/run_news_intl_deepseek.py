# -*- coding: utf-8 -*-
"""
รัน News-Intl stream เต็มรูปแบบผ่าน DeepSeek (NVIDIA NIM) — ทางเลือกหลักระหว่างรอเครดิต OpenRouter
(GPT-5.6-Luna)

**สถานะความเชื่อถือ (2026-09-10):** เจ้าของงานตัดสินใจให้ใช้ผลจากสคริปต์นี้เป็นผลจริง (ไม่ติดธง
"unverified" อีกต่อไป) หลังจาก:
- deepseek-v4-pro-0813 ผ่านการทดสอบ anti-hallucination ซ้ำ 3/3 ครั้งติด (ไม่แต่งชื่อแบรนด์ที่ไม่มีใน
  ข้อมูลจริง - อ้างถึง trap term เฉพาะตอนบอกว่า "ไม่มีในข้อมูล" เท่านั้น)
- มี `generate_trend_report_with_retry()` (retry wrapper + max_retries=0) แก้ปัญหา timeout เงียบ ~900s
  ให้เห็น progress ทุก attempt และ early-exit ทันทีที่สำเร็จ
- มี `verify_report_against_source()` เป็นตาข่ายนิรภัย deterministic ตรวจรายงานย้อนหลังทุกครั้ง
  (บันทึกผลไว้ในฟิลด์ `_verification` ของไฟล์ผลลัพธ์)

**หมายเหตุ:** ฟังก์ชันอื่นในสตรีม (select_top_news บังคับ Typhoon เองภายใน, triplet extraction,
cluster naming/Longevity, keyword extraction) ไม่ใช่งานสังเคราะห์เรื่องเล่าจากตัวอย่างฝังพรอมต์แบบ
report generation จึงไม่มีเหตุผลให้เชื่อว่าเสี่ยงหลอนแบบเดียวกัน - รันผ่าน DeepSeek เดียวกันทั้งหมด
"""
import json
import sys
import time
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common import bootstrap
from common.bootstrap import OUTPUTS, use_deepseek_nvidia, generate_trend_report_with_retry, \
    verify_report_against_source

sys.path.insert(0, str(Path(__file__).resolve().parent))
from news_intl_stream import run_news_intl_stream

tf = bootstrap.tf
MODEL_USED = "deepseek-ai/deepseek-v4-pro-0813 (NVIDIA NIM)"

if __name__ == "__main__":
    print("=" * 70)
    print("News-Intl ผ่าน DeepSeek (NVIDIA NIM) + retry wrapper")
    print("=" * 70)

    # patch generate_trend_report_with_llm ให้วิ่งผ่าน retry wrapper (max_attempts=3)
    # bootstrap.generate_trend_report_with_retry เรียก _original_generate_trend_report ภายใน ไม่ใช่
    # ชื่อที่ patch นี้ - ไม่มี recursion
    _orig = tf.generate_trend_report_with_llm
    tf.generate_trend_report_with_llm = lambda topic, scraped_data: \
        generate_trend_report_with_retry(topic, scraped_data, max_attempts=3)[0]

    t0 = time.time()
    try:
        with use_deepseek_nvidia():
            result = run_news_intl_stream()
    finally:
        tf.generate_trend_report_with_llm = _orig
    elapsed = time.time() - t0

    if result is None:
        print("❌ ล้มเหลว - ไม่มีผลลัพธ์")
        sys.exit(1)

    # ตาข่ายนิรภัย: ตรวจรายงานย้อนหลังกับข้อมูลต้นทางจริง
    #  ต้อง reconstruct scraped_data จาก cache (run_news_intl_stream ไม่คืนมันกลับมาโดยตรง) - ใช้
    #  รายงานเทียบกับ pool ที่ scrape ได้จริงผ่าน tf.url_cache แทน
    verification = None
    try:
        scraped_texts = [{"title": v.get("title", ""), "content": v.get("cleaned_text", "")}
                          for v in tf.url_cache.values() if v.get("cleaned_text")]
        verification = verify_report_against_source(result["report"], scraped_texts)
    except Exception as e:
        print(f"⚠️ verification ล้มเหลว (ไม่กระทบผลลัพธ์หลัก): {e}")

    out_path = OUTPUTS / "phase2_news_intl_stream_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "_model_used": MODEL_USED,
            "_verification": verification,
            "_elapsed_seconds": round(elapsed, 1),
            "topic": result["topic"], "queries": result["queries"], "pool_size": result["pool_size"],
            "n_scraped": result["n_scraped"], "report": result["report"],
            "n_triplets": result["n_triplets"], "n_clusters": result["n_clusters"],
            "trends": result["df_trends"].to_dict(orient="records"),
            "keywords": result["df_keywords"].to_dict(orient="records"),
        }, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(result["df_trends"].to_string())
    print("=" * 80)
    if verification:
        print(f"\n🔍 verification: asserted={verification['asserted']}  "
              f"negated_safe={verification['negated_safe']}")
    print(f"\n✅ Saved -> {out_path}  (ใช้เวลา {elapsed / 60:.1f} นาที)")
