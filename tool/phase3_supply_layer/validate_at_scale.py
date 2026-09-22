# -*- coding: utf-8 -*-
"""
Phase 3 — ทดสอบกลไก matching ที่สเกลใหญ่ขึ้นจริง กับฐานข้อมูลสินค้าจริงทั้งหมด

ดู Detail/05 งานที่ยังไม่ได้ทำ/Backlog และแนวทางต่อไป.md ข้อ 31 - เกณฑ์ความสำเร็จเดิม
(validate_against_step8_overmatch.py) ทดสอบกับ**แค่ 3 สินค้าที่เลือกมือ** ยังไม่ใช่สเกลใหญ่จริง
สคริปต์นี้ embed สินค้าจริงทั้งหมดใน watsons_product.csv (ไม่ใช่แค่ตัวอย่างที่รู้คำตอบอยู่แล้ว) แล้วดูว่า
top-K ที่จับคู่ได้จริงสมเหตุสมผลไหม เมื่อต้องแข่งกับสินค้าที่ไม่เกี่ยวข้องเลยหลายพันตัว (Makeup, Baby
Care, Vitamins ฯลฯ)

**🆕 (2026-09-09) สลับจาก `database/product_fda.parquet` (1,774 SKU) เป็น
`workspace/product/watsons_product.csv` (10,622 SKU จริง - ใหญ่กว่าเดิม ~6 เท่า) ตามที่เจ้าของงาน
ตัดสินใจ** - checkpoint/result ไฟล์เปลี่ยนชื่อใหม่ทั้งคู่ (ไม่ใช้ไฟล์เดิมต่อ) เพราะ index ของ DataFrame
คนละไฟล์ไม่ตรงกัน - ถ้าใช้ checkpoint เดิมจะได้ embedding ผิดสินค้าโดยไม่รู้ตัว (index 0-799 ของไฟล์เก่า
คือคนละสินค้ากับ index 0-799 ของไฟล์ใหม่)

**ไม่ต้องรอเครดิต OpenRouter เลย** - ใช้ Gemini embedding (free tier) เหมือน match_supply.py เดิม
ทุกประการ เพียงแต่สเกลใหญ่กว่ามาก (10,622 สินค้า + 5 เทรนด์ ≈ 10,627 embedding calls - ที่ pacing
~85/นาทีเดิม ใช้เวลา **~2 ชั่วโมง** ไม่ใช่ ~20 นาทีแบบไฟล์เก่าอีกต่อไป - ควรพิจารณาโมเดล embedding ที่
เร็วกว่า/ไม่มี rate limit แบบ Gemini free tier ก่อนรันเต็มสเกล เช่น NVIDIA NIM's
llama-nemotron-embed-vl-1b-v2 ที่เพิ่งทดสอบผ่าน cross-lingual check แล้ว (~5s/call ไม่เจอ 429 ในการ
ทดสอบสั้นๆ - ยังไม่เคยพิสูจน์ที่สเกลนี้)

## ข้อจำกัดจริงที่ต้องออกแบบรอบนี้ (ต่างจาก match_supply.py เดิมที่มีแค่ 27 ประโยคตลาด)

ทดสอบแล้ว (2026-09-09): Gemini free-tier quota (`embed_content_free_tier_requests`, limit 100/นาที)
นับเป็น**รายชิ้นที่ embed จริง ไม่ใช่ต่อ HTTP request** - ส่ง 100 ข้อความในคำขอเดียวก็ยังโดน 429 เหมือน
ยิง 100 ครั้งแยกกัน (ทดสอบตรงๆ แล้วเจอ 429 ทันทีที่ item ที่ 100+ ในนาทีเดียวกัน) - แปลว่า batching
หลายข้อความในคำขอเดียวไม่ได้ช่วยเลี่ยง rate limit เลย มีแต่ pacing (เว้นจังหวะ) เท่านั้นที่ช่วยได้จริง
ที่ ~1,779 embedding รวม ใช้เวลาอย่างน้อย ~18 นาทีตามทฤษฎี (คำนวณ pacing แบบระมัดระวังไว้ที่ ~85/นาที
เผื่อ overhead จริงจะยาวกว่านั้นเล็กน้อย)

**Checkpoint กันขัดจังหวะ:** เขียน embedding ที่ทำเสร็จแล้วลงไฟล์ทุก ๆ CHECKPOINT_EVERY ชิ้น - รันซ้ำ
ได้โดยไม่ต้อง embed ใหม่ตั้งแต่ต้นถ้าถูกขัดจังหวะกลางทาง (เช่น เน็ตหลุด, โดน 429 ค้างนาน)
"""
import json
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import OUTPUTS, PROJECT_ROOT, TOOL_DIR, CHECKPOINTS
from match_supply import TREND_PROFILES, build_trend_matchable_text, cosine_similarity

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)
from openai import OpenAI

client = OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                 api_key=os.getenv("GEMINI_KEY"))

# 🆕 (2026-09-09) ชื่อไฟล์ใหม่ (ต่อท้าย _watsons10k) - ห้ามใช้ชื่อเดิมซ้ำ เพราะ index ของสินค้าคนละไฟล์
# ไม่ตรงกัน (ดู docstring บนสุด) checkpoint เก่า (800 ชิ้นจาก product_fda.parquet) ยังเก็บไว้เฉยๆ ไม่ลบ
# 🆕 (2026-09-11) เดิม hardcode "workspace"/"outputs" (ชื่อก่อนเปลี่ยนเป็น tool/+output/) - เปลี่ยนมาใช้
# OUTPUTS export แทน (ไฟล์นี้ไม่ได้อยู่ใน STAGES ของ main.py แล้ว - เก็บไว้เป็น legacy reference)
CHECKPOINT_PATH = CHECKPOINTS / "phase3_product_embeddings_checkpoint_watsons10k.pkl"
RESULT_PATH = OUTPUTS / "phase3_scale_validation_watsons10k_result.json"
BATCH_SIZE = 5           # ต่อ 1 HTTP request (ไม่ช่วยเลี่ยง rate limit แต่ลด overhead จำนวน request)
# 🆕 (2026-09-09) เจอจริง 2 ครั้งติด: pacing 85/นาที (ใต้ 100/นาทีตามสเปก) ยังโดน 429 ค้างต่อเนื่องจน
# retry 10 ครั้ง (~22 นาที) ไม่หาย ทั้งที่ probe เดี่ยวๆ ระหว่างนั้นผ่านปกติ - แปลว่า throughput ที่ทน
# ได้จริงต่อเนื่องต่ำกว่า 100/นาทีตามสเปกมาก (latency ของแต่ละ call เองก็กิน budget เวลาไปด้วย ทำให้
# rate จริงพุ่งเกินตอน burst) ลดเหลือ 40/นาทีให้มี margin กว้างขึ้นมาก
ITEMS_PER_MINUTE = 40
SLEEP_PER_BATCH = 60.0 * BATCH_SIZE / ITEMS_PER_MINUTE
TOP_K = 15


def embed_batch_with_retry(texts, max_retries=10):
    """embed หลายข้อความในคำขอเดียว (ลด HTTP overhead) พร้อม retry เมื่อโดน 429 (อ่าน retry delay จาก
    ข้อความ error ตรงๆ ถ้ามี ไม่งั้น fallback แบบ exponential backoff)

    🆕 (2026-09-09) เจอจริงระหว่างรันเต็ม 1,774 สินค้า: 429 ค้างต่อเนื่อง 5 ครั้งติด (แต่ละครั้งรอ ~57s
    ตามที่ error บอก) เกิน max_retries=5 เดิมจนสคริปต์ crash ทั้งที่โควตาจริงกลับมาใช้ได้ปกติหลังจากนั้น
    ไม่นาน (ทดสอบ probe เดี่ยวๆ แล้วผ่านทันที) - แปลว่าเป็นการค้างชั่วคราวที่นานกว่า per-minute quota
    ปกติเล็กน้อย ไม่ใช่โควตาหมดจริงถาวร - เพิ่ม max_retries เป็น 10 + exponential backoff (ไม่ใช่คงที่
    60s ทุกครั้ง) ให้ทนต่อการค้างแบบนี้ได้โดยไม่ต้อง manual resume บ่อย (checkpoint กันของเดิมหายอยู่แล้ว
    ถึงจะ crash จริงก็ไม่เสียของเดิม)
    """
    for attempt in range(max_retries):
        try:
            resp = client.embeddings.create(model="gemini-embedding-001", input=texts)
            return [np.array(d.embedding) for d in resp.data]
        except Exception as e:
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                import re as _re
                m = _re.search(r"retry in ([\d.]+)s", msg)
                base_wait = float(m.group(1)) + 2 if m else 60.0
                wait = min(base_wait * (1.4 ** attempt), 240.0)  # exponential, cap ที่ 4 นาที/ครั้ง
                print(f"    ⏳ 429 ชนโควตา - รอ {wait:.0f}s แล้วลองใหม่ (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            print(f"    ⚠️ embedding error (ไม่ใช่ 429): {e}")
            time.sleep(5)
    raise RuntimeError(f"embed_batch ล้มเหลวหลัง {max_retries} ครั้ง")


def build_product_text(row):
    """🆕 (2026-09-09) เหมือน validate_against_step8_overmatch.py's build_product_text() ทุกประการ -
    ใช้ฟิลด์เชิงความหมายจาก watsons_product.csv (Key_Benefits/Primary_Use_Case/Product_Insights)
    แทน Product Name+Content+Ingredients ตื้นๆ แบบเดิมจาก product_fda.parquet"""
    parts = [
        str(row.get("product_name", "")),
        str(row.get("Key_Benefits", "")),
        str(row.get("Primary_Use_Case", "")),
        str(row.get("Product_Insights", ""))[:500],
        str(row.get("ingredients", ""))[:300],
    ]
    return " ".join(p for p in parts if p and p.lower() != "nan")


def load_checkpoint():
    if CHECKPOINT_PATH.exists():
        with open(CHECKPOINT_PATH, "rb") as f:
            data = pickle.load(f)
        print(f"📂 พบ checkpoint เดิม: embed ไปแล้ว {len(data)} ชิ้น - รันต่อจากจุดนั้น")
        return data
    return {}


def save_checkpoint(embeddings_by_idx):
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_PATH, "wb") as f:
        pickle.dump(embeddings_by_idx, f)


def embed_all_products(df):
    """embed สินค้าจริงทั้งหมด พร้อม checkpoint กันขัดจังหวะ - คืน dict {index: vector}"""
    embeddings_by_idx = load_checkpoint()
    remaining_idx = [i for i in df.index if i not in embeddings_by_idx]
    if not remaining_idx:
        print("✅ embed ครบทุกชิ้นแล้วจากรอบก่อน - ใช้ cache ทั้งหมด")
        return embeddings_by_idx

    total = len(df)
    print(f"กำลัง embed สินค้าจริง {len(remaining_idx)}/{total} ชิ้นที่เหลือ "
          f"(pacing ~{ITEMS_PER_MINUTE}/นาที เผื่อ margin จาก limit จริง 100/นาที)...")
    t_start = time.time()

    for batch_start in range(0, len(remaining_idx), BATCH_SIZE):
        batch_idx = remaining_idx[batch_start:batch_start + BATCH_SIZE]
        texts = [build_product_text(df.loc[i]) for i in batch_idx]
        vectors = embed_batch_with_retry(texts)
        for i, vec in zip(batch_idx, vectors):
            embeddings_by_idx[i] = vec

        done = len(embeddings_by_idx)
        if done % 200 < BATCH_SIZE or batch_start + BATCH_SIZE >= len(remaining_idx):
            save_checkpoint(embeddings_by_idx)
            elapsed = time.time() - t_start
            print(f"  [{done}/{total}] checkpoint บันทึกแล้ว ({elapsed:.0f}s ผ่านไปในรอบนี้)")

        time.sleep(SLEEP_PER_BATCH)

    save_checkpoint(embeddings_by_idx)
    return embeddings_by_idx


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 3 — ทดสอบสเกลใหญ่: 5 เทรนด์จริง vs สินค้าจริง 1,774 SKU (ไม่ใช่แค่ 3 ตัวที่เลือกมือ)")
    print("=" * 70)

    df = pd.read_csv(TOOL_DIR / "product" / "watsons_product.csv", low_memory=False)
    print(f"โหลดสินค้าจริงแล้ว: {len(df)} รายการ, {df['brand'].nunique()} แบรนด์\n")

    print("กำลัง embed 5 trend profile (ไม่ต้อง pacing เพราะมีแค่ 5 ชิ้น)...")
    trend_vectors = {}
    for profile in TREND_PROFILES:
        text = build_trend_matchable_text(profile)
        trend_vectors[profile["trend"]] = embed_batch_with_retry([text])[0]
    print("เสร็จแล้ว\n")

    product_embeddings = embed_all_products(df)

    print("\nกำลังคำนวณ cosine similarity ทุกคู่ (เทรนด์ x สินค้า) แบบ deterministic (ไม่ยิง API เพิ่ม)...")
    all_results = {}
    for trend_name, tvec in trend_vectors.items():
        scored = []
        for idx, pvec in product_embeddings.items():
            sim = cosine_similarity(tvec, pvec)
            row = df.loc[idx]
            scored.append({
                "product_name": row["product_name"], "brand": row["brand"],
                "similarity": round(sim, 4),
            })
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        all_results[trend_name] = {
            "top_matches": scored[:TOP_K],
            "bottom_matches": scored[-5:],
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
            "_note": "ทดสอบสเกลใหญ่ 1,774 SKU จริง (ไม่ใช่ mockup) - ดู Backlog ข้อ 31/34",
            "n_products_total": len(df), "top_k": TOP_K, "results": all_results,
        }, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    for trend_name, r in all_results.items():
        print(f"\n🎯 เทรนด์: {trend_name}")
        print(f"   similarity: max={r['similarity_stats']['max']} mean={r['similarity_stats']['mean']} "
              f"min={r['similarity_stats']['min']}")
        print(f"   Top {min(5, TOP_K)} จาก {r['n_products_compared']} สินค้าจริง:")
        for m in r["top_matches"][:5]:
            print(f"     [{m['similarity']:.4f}] {m['brand']} - {m['product_name'][:70]}")

    print("\n" + "=" * 70)
    print(f"บันทึกผลเต็มลง {RESULT_PATH}")
