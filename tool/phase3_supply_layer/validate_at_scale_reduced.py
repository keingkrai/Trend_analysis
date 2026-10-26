# -*- coding: utf-8 -*-
"""
Phase 3 — เวอร์ชันลดสเกล: ใช้ embedding สินค้าจริง 800 ชิ้นที่ Gemini ทำสำเร็จไปแล้ว (จาก
validate_at_scale.py รอบก่อนที่โดน 429 ตอน 800/1,774) แทนที่จะรอ embed ครบ 1,774 ตัว

**ต้องมี Gemini quota/credit พร้อมใช้ก่อน** (เช็คด้วย probe เล็กๆ ก่อนรันเสมอ - ดู __main__ ด้านล่าง)
- ยิง Gemini แค่ 5 ครั้ง (5 trend profile เท่านั้น) ไม่แตะสินค้าเลยสักตัว เพราะ 800 ตัวมีอยู่แล้ว
- ยังคง save checkpoint เดิมไว้ครบ (ไม่แก้/ลบ) เผื่ออนาคตอยากต่อให้ครบ 1,774 จริง

ดู Detail/05 งานที่ยังไม่ได้ทำ/Backlog และแนวทางต่อไป.md ข้อ 31/34 (ตัดสินใจ 2026-09-09: ลดสเกลจาก
1,774 เหลือ 800 ที่มีอยู่แล้ว เพื่อเลี่ยงทั้งปัญหา Gemini free-tier quota หมด และปัญหา CPU ช้าเกินไป
ของทางเลือก local embedding - Qwen3-Embedding-0.6B ทดสอบแล้วว่า 1,774 ชิ้นจะใช้เวลา ~5.6 ชม. บนเครื่องนี้
(RAM เหลือแค่ 2.3GB, ไม่มี GPU) เจ้าของงานเลือกใช้ 800 ที่มีอยู่แล้วแทนหลังจากได้เห็นตัวเลขนี้)
"""
import json
import os
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import OUTPUTS, PROJECT_ROOT, CHECKPOINTS
from match_supply import TREND_PROFILES, build_trend_matchable_text, cosine_similarity

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)
from openai import OpenAI

client = OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                 api_key=os.getenv("GEMINI_KEY"))

# 🆕 (2026-09-11) เดิม hardcode "workspace"/"outputs" (ชื่อก่อนเปลี่ยนเป็น tool/+output/) - เปลี่ยนมาใช้
# OUTPUTS export แทน (ไฟล์นี้ไม่ได้อยู่ใน STAGES ของ main.py แล้ว - เก็บไว้เป็น legacy reference)
CHECKPOINT_PATH = CHECKPOINTS / "phase3_product_embeddings_checkpoint.pkl"
RESULT_PATH = OUTPUTS / "phase3_scale_validation_800_result.json"
TOP_K = 15


def build_product_text(row):
    parts = [str(row.get("Product Name", "")), str(row.get("Product Content", ""))[:500],
              str(row.get("Ingredients", ""))]
    return " ".join(p for p in parts if p and p != "nan")


def quota_available():
    """probe เล็กสุด (1 ข้อความ) ก่อนยิงจริง - กันยิง 5 ครั้งแล้วพังกลางทางแบบรอบก่อนๆ"""
    try:
        client.embeddings.create(model="gemini-embedding-001", input=["quota probe"])
        return True
    except Exception as e:
        print(f"⚠️ Gemini quota ยังไม่พร้อม: {str(e)[:150]}")
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 3 — ทดสอบสเกลลด: 5 เทรนด์จริง vs สินค้าจริง 800 ชิ้น (จาก checkpoint Gemini เดิม)")
    print("=" * 70)

    if not CHECKPOINT_PATH.exists():
        print(f"❌ ไม่มี checkpoint ที่ {CHECKPOINT_PATH} - รัน validate_at_scale.py มาก่อนอย่างน้อย 1 ครั้ง")
        sys.exit(1)

    with open(CHECKPOINT_PATH, "rb") as f:
        product_embeddings = pickle.load(f)
    print(f"โหลด embedding สินค้าจริงจาก checkpoint: {len(product_embeddings)} ชิ้น")

    print("\nเช็ค Gemini quota ก่อน (probe 1 ครั้ง)...")
    if not quota_available():
        print("\n❌ ยังยิงไม่ได้ - รอ quota/credit กลับมาก่อนแล้วรันสคริปต์นี้ใหม่ (ไม่ต้องทำอะไรกับ")
        print("   checkpoint 800 ชิ้น มันปลอดภัยอยู่แล้ว)")
        sys.exit(1)
    print("✅ quota พร้อม - ไปต่อ")

    df = pd.read_parquet(PROJECT_ROOT / "database" / "product_fda.parquet")
    df_cached = df.loc[df.index.isin(product_embeddings.keys())]
    print(f"กรองเหลือแค่แถวที่มี embedding แล้ว: {len(df_cached)}/{len(df)} รายการ")

    print("\nกำลัง embed 5 trend profile (ยิง Gemini แค่ 5 ครั้ง)...")
    trend_vectors = {}
    for profile in TREND_PROFILES:
        text = build_trend_matchable_text(profile)
        resp = client.embeddings.create(model="gemini-embedding-001", input=[text])
        trend_vectors[profile["trend"]] = np.array(resp.data[0].embedding)
        print(f"  ✅ {profile['trend']}")
    print("เสร็จแล้ว (ไม่แตะ embedding สินค้าเลยแม้แต่ตัวเดียว - ใช้ของเดิมจาก checkpoint ทั้งหมด)")

    print("\nกำลังคำนวณ cosine similarity ทุกคู่ (deterministic ไม่ยิง API เพิ่ม)...")
    all_results = {}
    for trend_name, tvec in trend_vectors.items():
        scored = []
        for idx, pvec in product_embeddings.items():
            if idx not in df_cached.index:
                continue
            row = df_cached.loc[idx]
            sim = cosine_similarity(tvec, pvec)
            scored.append({"product_name": row["Product Name"], "brand": row["Brand"], "similarity": round(sim, 4)})
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        all_results[trend_name] = {
            "top_matches": scored[:TOP_K],
            "n_products_compared": len(scored),
            "similarity_stats": {
                "max": round(max(s["similarity"] for s in scored), 4),
                "min": round(min(s["similarity"] for s in scored), 4),
                "mean": round(float(np.mean([s["similarity"] for s in scored])), 4),
            },
        }

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "_note": "สเกลลด (800/1774 SKU จริง) - ตัดสินใจ 2026-09-09 ดู Backlog ข้อ 31/34",
            "n_products_total": len(df_cached), "top_k": TOP_K, "results": all_results,
        }, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    for trend_name, r in all_results.items():
        print(f"\n🎯 เทรนด์: {trend_name}")
        print(f"   similarity: max={r['similarity_stats']['max']} mean={r['similarity_stats']['mean']} "
              f"min={r['similarity_stats']['min']}")
        print(f"   Top 5 จาก {r['n_products_compared']} สินค้าจริง:")
        for m in r["top_matches"][:5]:
            print(f"     [{m['similarity']:.4f}] {m['brand']} - {m['product_name'][:70]}")

    print(f"\nบันทึกผลเต็มลง {RESULT_PATH}")
