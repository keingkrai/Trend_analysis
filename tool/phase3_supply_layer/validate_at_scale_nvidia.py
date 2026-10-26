# -*- coding: utf-8 -*-
"""
Phase 3 — ทดสอบกลไก matching สเกลใหญ่ (SKU จริงจาก konvy_product.csv - ตั้งแต่ 2026-10-11; เดิม Watsons 10,622 SKU) ผ่าน NVIDIA NIM's
llama-nemotron-embed-vl-1b-v2 แทน Gemini

ทำไมเปลี่ยนจาก Gemini: Gemini free-tier quota (100/นาที) ทำให้รอบก่อน (validate_at_scale.py, ไฟล์เก่า
1,774 SKU) ล้มไป 2 รอบติดจาก 429 - ทดสอบ NVIDIA embedding แล้วผ่าน cross-lingual check (Eucerin/Aigis/
Veet, query ไทย vs passage อังกฤษ) และ burst test 40 ครั้งติดไม่มี error เลย (0.54s/ครั้ง - เร็วกว่า
Gemini pacing ~85/นาทีเดิมมาก)

**เป็น "asymmetric" model - ต้องระบุ input_type ทุกครั้ง** ("query" สำหรับเทรนด์, "passage" สำหรับ
สินค้า) ผ่าน extra_body - ไม่ใช่แค่เปลี่ยนชื่อโมเดลเฉยๆ

มิติ 2048 (Gemini เดิม 3072, watsons10k-Gemini checkpoint ก็คนละพื้นที่) - checkpoint/result ไฟล์ชื่อ
ใหม่แยกจากทุกไฟล์ก่อนหน้า กันสับสน/ใช้ผิด embedding space โดยไม่ตั้งใจ

**ไม่ต้องรอเครดิต OpenRouter เลย** - NVIDIA_API key เดิมที่มีอยู่แล้ว
"""
import hashlib
import json
import os
import pickle
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import PROJECT_ROOT, TOOL_DIR, OUTPUTS, CHECKPOINTS, tf, use_bedrock, refresh_source_dir
from category_breakdown import category_breakdown
from l2_market_map import MAP_FILE, build_table, trend_entry, write_map
from unit_price_tiers import market_tiers
from trend_category import main_categories
from product.euromonitor_mapping import BEAUTY_L1, load_catalog
from match_supply import build_trend_matchable_text, cosine_similarity
from validate_at_scale import build_product_text

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)
from openai import OpenAI

client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.getenv("NVIDIA_API"))
MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2"

# 🆕 (2026-09-11) เดิม hardcode "workspace"/"outputs" ตรงๆ (ชื่อก่อนเปลี่ยนเป็น tool/+output/) พังไปตอน
# เปลี่ยนชื่อโฟลเดอร์ เพราะไม่ได้ผ่าน OUTPUTS export - เปลี่ยนมาใช้ OUTPUTS ตรงๆ แทน (ที่ๆ ผลลัพธ์จริง
# มีอยู่แล้วในนี้พอดี)
CHECKPOINT_PATH = CHECKPOINTS / "phase3_product_embeddings_checkpoint_nvidia.pkl"
RESULT_PATH = OUTPUTS / "phase3_scale_validation_nvidia_result.json"
# 🆕 (2026-10-08) คำตัดสินหมวดหลักของเทรนด์ (LLM - trend_category.py) แชร์ทุกรอบ/ทุกขั้น (⑫ ⑬) นอกโฟลเดอร์รอบ เหมือน checkpoint
MAIN_CATEGORY_LABELS = CHECKPOINTS / "trend_main_category_labels.jsonl"
CHECKPOINT_EVERY = 1000   # บันทึก checkpoint ทุกกี่ชิ้น (ไฟล์รวมหลายร้อย MB เขียนทั้งก้อน จึงไม่ถี่เท่าตอนยิงทีละชิ้น)
PROGRESS_EVERY = 500
EMBED_WORKERS = 6         # ยิงขนานกี่ตัว (วัด 2026-10-11: 4 ตัว ~10 ชิ้น/s, 8 ตัว ~19 ชิ้น/s ไม่มี 429 ในตัวอย่าง 16 ชิ้น) - ปรับด้วย --workers
EMBED_MAX_FAILURES = 20   # ล้มเหลวสะสมถึงเท่านี้ = หยุดทั้งรอบ
TOP_K = 15
# 🆕 (2026-09-14) เหตุผลข้อความต้องยิง LLM จริง (เสีย credit) ต่างจาก similarity ที่คำนวณเองแบบ
# deterministic - จำกัดไว้แค่ top 5 ที่ report ใช้จริง (ดู run_stepic_report.py's
# load_supply_layer_results()'s `r["top_matches"][:5]`) ไม่ใช่ทั้ง TOP_K=15 ที่เก็บไว้เผื่อดูย้อนหลัง
MATCH_REASON_TOP_K = 5


def get_embedding(text, input_type, max_retries=5):
    """input_type: 'query' (เทรนด์) หรือ 'passage' (สินค้า) - จำเป็นเสมอสำหรับ asymmetric model นี้"""
    # 🆕 (2026-09-16) กันข้อความว่างตั้งแต่ต้นทาง - NVIDIA ตอบ 400 ("Input list must be non-empty and all
    # elements must be non-empty") ซึ่งไม่ใช่ error ชั่วคราว retry อีก 5 ครั้งก็ 400 เหมือนเดิมแล้วพังทั้ง
    # ไปป์ไลน์ (เจอจริง 2026-09-16 กับเทรนด์ที่ ⑪ ตอบ "ข้อมูลไม่พอ" ครบทุกฟิลด์ที่ใช้จับคู่)
    if not (text or "").strip():
        raise ValueError("get_embedding: ข้อความว่าง - ผู้เรียกต้องกรองทิ้งก่อนเรียก (ดูจุดข้ามเทรนด์ใน __main__)")
    for attempt in range(max_retries):
        try:
            resp = client.embeddings.create(model=MODEL, input=[text], extra_body={"input_type": input_type})
            return np.array(resp.data[0].embedding)
        except Exception as e:
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "rate" in msg.lower():
                wait = min(10 * (1.5 ** attempt), 120.0)
                print(f"    ⏳ rate limit - รอ {wait:.0f}s แล้วลองใหม่ (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            print(f"    ⚠️ embedding error (ไม่ใช่ rate limit): {str(e)[:150]}")
            time.sleep(3)
    raise RuntimeError(f"get_embedding ล้มเหลวหลัง {max_retries} ครั้ง")


def _product_hash(row):
    """🆕 (2026-09-12, audit m3) hash เนื้อหาที่ใช้ embed จริง (build_product_text) - ไม่ใช่ df.index
    เดิม checkpoint ผูกกับเลขแถวของ DataFrame ตรงๆ ถ้า konvy_product.csv ถูกอัปเดต/เรียงแถวใหม่วันไหน
    embedding จะจับคู่ผิดสินค้าโดยเงียบๆ ไม่มี error เลย - เนื้อหาเดียวกันได้ hash เดียวกันเสมอไม่ว่าจะ
    อยู่แถวไหนของไฟล์ กันปัญหานี้ที่ต้นเหตุ"""
    return hashlib.sha256(build_product_text(row).encode("utf-8")).hexdigest()


def load_checkpoint(df=None):
    """โหลด cache จากดิสก์ - เก็บเป็น {content_hash: vector} (ทนการเรียงแถวใหม่/แถวเพิ่ม-หายได้จริง)
    ถ้าส่ง df มา จะ remap เป็น {df.index: vector} ให้ตรงกับแถวปัจจุบันของ df นั้น เพื่อความเข้ากันได้กับ
    โค้ดที่ยังอ้างอิงด้วย index (เช่น run_brand_coverage.py ที่เรียกฟังก์ชันนี้ตรงๆ ไม่ผ่าน
    embed_all_products)"""
    raw = {}
    if CHECKPOINT_PATH.exists():
        with open(CHECKPOINT_PATH, "rb") as f:
            raw = pickle.load(f)
        print(f"📂 พบ checkpoint เดิม: embed ไปแล้ว {len(raw)} ชิ้น - รันต่อจากจุดนั้น")
    if df is None:
        return raw
    return {idx: raw.get(_product_hash(df.loc[idx])) for idx in df.index}


def save_checkpoint(embeddings_by_hash):
    """เขียนไฟล์ชั่วคราวแล้วค่อยสลับชื่อ - ถูกขัดจังหวะกลางการเขียน (Ctrl+C / ไฟดับ) แล้ว checkpoint เดิมไม่เสีย"""
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CHECKPOINT_PATH.with_name(CHECKPOINT_PATH.name + ".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(embeddings_by_hash, f)
    os.replace(tmp, CHECKPOINT_PATH)


def embed_all_products(df, workers=EMBED_WORKERS):
    """embed สินค้าที่ยังไม่มีใน checkpoint -> {index ของ df: เวกเตอร์}
    🆕 (2026-10-11) ยิงขนาน `workers` ตัว (เดิมทีละชิ้น ~0.5s/ชิ้น = ~3.8 ชม. สำหรับ Konvy 27,000 ชิ้น; วัด 8 ตัวได้ ~19 ชิ้น/s) -
    เนื้อหาเหมือนกันนับเป็นชิ้นเดียว; checkpoint ทุก CHECKPOINT_EVERY ชิ้นและตอนจบ/ถูกขัดจังหวะ (รันซ้ำแล้วทำต่อจากที่ค้าง);
    ชิ้นที่ล้มเหลวไม่ทำให้ทั้งรอบหยุดทันที (เก็บส่วนที่สำเร็จไว้ แล้ว raise ตอนจบ) แต่ถ้าล้มเหลวถึง EMBED_MAX_FAILURES ชิ้นให้หยุดเลย
    (เช่น key ผิด/เครือข่ายล่ม - ไม่ปล่อยให้ retry ไล่ทีละชิ้นทั้งแคตตาล็อก)"""
    embeddings_by_hash = load_checkpoint()
    row_hash = {idx: _product_hash(df.loc[idx]) for idx in df.index}
    todo = {}   # hash -> index แรกที่มีเนื้อหานี้
    for idx in df.index:
        if embeddings_by_hash.get(row_hash[idx]) is None:
            todo.setdefault(row_hash[idx], idx)
    if not todo:
        print("✅ embed ครบทุกชิ้นแล้วจากรอบก่อน - ใช้ cache ทั้งหมด")
        return {idx: embeddings_by_hash[row_hash[idx]] for idx in df.index}

    total, n_todo = len(df), len(todo)
    print(f"กำลัง embed สินค้าจริง {n_todo}/{total} ชิ้นที่เหลือ (ยิงขนาน {workers} ตัว)...")
    t_start = time.time()
    done = failed = 0
    errors = []
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {pool.submit(get_embedding, build_product_text(df.loc[idx]), "passage"): h for h, idx in todo.items()}
        for fut in as_completed(futures):
            try:
                embeddings_by_hash[futures[fut]] = fut.result()
            except Exception as e:   # noqa: BLE001 - get_embedding retry ครบแล้ว/ข้อความว่าง: นับไว้ ทำชิ้นอื่นต่อ
                failed += 1
                errors.append(str(e)[:150])
                if failed >= EMBED_MAX_FAILURES:
                    raise RuntimeError(f"embed ล้มเหลว {failed} ชิ้น - หยุดก่อน (ตัวอย่าง: {errors[0]}) "
                                       f"ส่วนที่สำเร็จแล้ว {done} ชิ้นบันทึกใน checkpoint แล้ว รันซ้ำหลังแก้สาเหตุเพื่อทำต่อ")
                continue
            done += 1
            if done % PROGRESS_EVERY == 0 or done == n_todo - failed:
                elapsed = time.time() - t_start
                rate = done / elapsed if elapsed > 0 else 0
                eta = (n_todo - done - failed) / rate if rate > 0 else float("inf")
                print(f"  [{done}/{n_todo}] {elapsed:.0f}s ผ่านไป, ~{rate:.1f} ชิ้น/s, ETA ~{eta / 60:.1f} นาที"
                      + (f" (ล้มเหลว {failed})" if failed else ""))
            if done % CHECKPOINT_EVERY == 0:
                save_checkpoint(embeddings_by_hash)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)   # ขัดจังหวะ/หยุดกลางทาง: ไม่รองานที่ยังไม่เริ่ม
        if done:
            save_checkpoint(embeddings_by_hash)
    if failed:
        raise RuntimeError(f"embed ไม่สำเร็จ {failed}/{n_todo} ชิ้น (ตัวอย่าง: {errors[0]}) - ส่วนที่สำเร็จบันทึกแล้ว รันซ้ำเพื่อทำต่อ")
    return {idx: embeddings_by_hash[row_hash[idx]] for idx in df.index}


def load_real_trend_profiles():
    """🆕 (2026-09-11) 15 profile จริงจาก extract_trend_highlights.py (Typhoon, ⑪) - แทนที่
    match_supply.py's TREND_PROFILES (5 ตัว, manual ล้วน) ที่ใช้ทดสอบกลไกมาตลอด"""
    path = OUTPUTS / "phase3_trend_highlights_result.json"
    if not path.exists():
        raise SystemExit(f"❌ ไม่มี {path.name} - รัน extract_trend_highlights.py (⑪) ก่อน")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    profiles = data.get("profiles") or []
    if not profiles:
        raise SystemExit(f"❌ {path.name} ไม่มี profile เลย")
    return profiles


def product_groups(df):
    """หมวดของสินค้าแต่ละแถว = Level 2 ของ Euromonitor (EM_Group จาก euromonitor_mapping.load_catalog) ตาม index ของ df"""
    return df["EM_Group"]


def subgroup_sizes(df):
    """{(หมวด L2, ชนิดสินค้า L4): จำนวน SKU} - ตัวหารของคอลัมน์ที่ category_breakdown แตกเป็นชนิดสินค้า"""
    return {k: int(v) for k, v in df.groupby(["EM_Group", "EM_L4"]).size().items()}


def score_products(tvec, df, product_embeddings, groups, tier_records=None):
    """similarity ของเทรนด์นี้กับสินค้าทุกชิ้นที่มีเวกเตอร์ เรียงมากไปน้อย - แต่ละชิ้นมี _idx (แถวใน df) ไว้ใช้ภายใน
    🆕 (2026-10-12) tier_records (unit_price_tiers.market_tiers) ส่งมา = ติดช่วงราคาต่อปริมาณ (unit_tier / unit_price / unit_label /
    size / is_mini) ให้สินค้าทุกชิ้น เพื่อให้ category_breakdown แบ่งช่วงด้วยตัวนี้แทนราคาขาย"""
    scored = []
    for idx, pvec in product_embeddings.items():
        if pvec is None:
            continue
        sim = cosine_similarity(tvec, pvec)
        row = df.loc[idx]
        # 🆕 (2026-09-12, audit M6) เดิมไม่ได้เก็บราคา/ยอดขายเลย - ปลายทาง (run_stepic_report.py)
        # เลย hardcode ค่าว่างเสมอ ทั้งที่มีข้อมูลจริงอยู่แล้ว (sale_price_thb เต็ม 100%, sold_count
        # มีจริงแค่ ~25% ของแถว - เก็บเป็น None ไม่ใช่ 0 เวลาไม่มีข้อมูล กัน "0 ยอดขาย" ปลอมๆ) -
        # sale_price_thb เป็น string มี comma คั่นหลักพัน (เช่น "1,790.00") ต้องตัดออกก่อนแปลงเลข
        price, sold = row.get("sale_price_thb"), row.get("sold_count")
        try:
            price_val = None if pd.isna(price) else float(str(price).replace(",", ""))
        except (ValueError, TypeError):
            price_val = None
        scored.append({
            "product_name": row["product_name"], "brand": row["brand"],
            "category": row.get("EM_L2", ""), "group": groups[idx], "subgroup": row.get("EM_L4") or None,
            "similarity": round(sim, 4),
            "sale_price_thb": price_val,
            "sold_count": None if pd.isna(sold) else float(sold),
            "_idx": idx,  # ใช้เฉพาะภายใน (หา df.loc[idx] เพื่อ generate_match_reason) - ตัดออกก่อนเซฟ
            **({k: tier_records[idx][k] for k in ("unit_tier", "unit_price", "unit_label", "size", "is_mini")}
               if tier_records is not None else {}),
        })
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored


def _match_key(m):
    return (m.get("brand"), m.get("product_name"))


def load_reusable_reasons(source_dir):
    """🆕 (2026-10-07) โหมดอัปเดตรอบเดิม: เหตุผลจับคู่สินค้าที่ ⑫ ของรอบต้นทางเขียนไว้แล้ว ->
    {(stream, trend): {"text": ข้อความจับคู่จาก profile ⑪ ของรอบต้นทาง, "reasons": {(brand, product_name): reason}}}
    ผู้เรียกใช้ซ้ำเฉพาะเทรนด์ที่ข้อความจับคู่ตรงกับ profile ของรอบนี้ (= ⑪ ใช้จุดเด่นเดิม เหตุผลจึงยังพูดถึงเทรนด์เดียวกัน)
    สินค้าที่ไม่เคยได้เหตุผล (เพิ่งเข้า top 5) ให้ LLM เขียนตามปกติ / source_dir None หรือไฟล์ไม่ครบ = {}"""
    if not source_dir:
        return {}
    match_path, highlights_path = source_dir / RESULT_PATH.name, source_dir / "phase3_trend_highlights_result.json"
    if not (match_path.exists() and highlights_path.exists()):
        return {}
    with open(match_path, encoding="utf-8") as f:
        results = json.load(f).get("results") or {}
    with open(highlights_path, encoding="utf-8") as f:
        highlights = json.load(f)
    texts = {(p.get("stream"), p["trend"]): build_trend_matchable_text(p)
             for p in (highlights.get("profiles") or []) + (highlights.get("extra_profiles") or [])}
    reusable = {}
    for r in results.values():
        key = (r.get("stream"), r["trend_name"])
        if key in texts:
            reusable[key] = {"text": texts[key],
                             "reasons": {_match_key(m): m["match_reason"]
                                         for m in r.get("top_matches") or [] if m.get("match_reason")}}
    return reusable


def apply_main_category(r, decision, scored, group_sizes, sub_sizes, tier_key=None):
    """🆕 (2026-10-08) ผลของ 1 เทรนด์ <- หมวดหลักที่ LLM เลือก (decision จาก trend_category) + by_category เฉพาะหมวดนั้น
    r["main_category"] = {"category", "reason", "source"} เก็บไว้ตรวจย้อนหลัง (source: llm / cache / embedding_fallback)"""
    r["main_category"] = decision
    r["by_category"] = category_breakdown(scored, group_sizes, subgroup_sizes=sub_sizes, main_category=decision["category"],
                                          tier_key=tier_key)


def write_l2_map(df, groups, tier_recs, entries, decisions):
    """🆕 (2026-10-21) แผนที่ตลาดระดับหมวด L2 ของรอบนี้ (l2_market_map.py) -> OUTPUTS/phase3_l2_market_map.json.gz
    entries = {คีย์: (profile, scored)}, decisions = {คีย์: {"category": หมวดหลักของเทรนด์}} - รายงาน ⑯ ⑰ ใช้เทียบความใกล้เทรนด์ x ยอดขายในหมวด"""
    wanted = {d["category"] for key, d in decisions.items() if key in entries and d.get("category")}
    table, index_by_idx = build_table(df, groups, tier_recs, wanted)
    trends = {key: trend_entry(scored, decisions[key]["category"], index_by_idx, profile.get("stream", "?"), profile["trend"])
              for key, (profile, scored) in entries.items() if decisions.get(key, {}).get("category")}
    path = OUTPUTS / MAP_FILE
    write_map(path, len(df), table, trends)
    print(f"🗺️ แผนที่ตลาดระดับหมวด L2: {len(trends)} เทรนด์, สินค้า {len(table):,} ชิ้นใน {len(wanted)} หมวด -> {path.name} ({path.stat().st_size / 1e6:.1f} MB)")


TREND_VECTOR_CACHE = CHECKPOINTS / "trend_query_vectors.pkl"   # {sha256(ข้อความเทรนด์): เวกเตอร์ query} ใช้ซ้ำข้ามรอบที่ profile เหมือนกัน


def embed_trend_texts(texts, workers=EMBED_WORKERS, refresh=False):
    """🆕 (2026-10-21) ข้อความเทรนด์ -> {ข้อความ: เวกเตอร์ query} - เก็บ cache ตามเนื้อหาข้อความ (ข้อความเดิมไม่ยิง NVIDIA ซ้ำ) และยิงตัวที่ยังไม่มีขนานกัน
    (NVIDIA ช้าได้ถึงนาทีต่อครั้ง - ยิงทีละเทรนด์ 10+ เทรนด์ต่อรอบใช้เวลานาน); refresh = ไม่ใช้ cache ของข้อความเหล่านี้ (ยิงใหม่แล้วทับ)"""
    key = lambda t: hashlib.sha256(t.encode("utf-8")).hexdigest()  # noqa: E731
    cache = {}
    if TREND_VECTOR_CACHE.exists():
        with open(TREND_VECTOR_CACHE, "rb") as f:
            cache = pickle.load(f)
    todo = sorted({t for t in texts if refresh or key(t) not in cache})
    if todo:
        print(f"  embed ข้อความเทรนด์ใหม่ {len(todo)}/{len(set(texts))} (ขนาน {min(workers, len(todo))} ตัว)...", flush=True)
        with ThreadPoolExecutor(max_workers=min(workers, len(todo))) as pool:
            for text, vec in zip(todo, pool.map(lambda t: get_embedding(t, "query"), todo)):
                cache[key(text)] = vec
        TREND_VECTOR_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(TREND_VECTOR_CACHE, "wb") as f:
            pickle.dump(cache, f)
    return {t: cache[key(t)] for t in set(texts)}


def backfill_l2_map():
    """🆕 (2026-10-21) เขียน phase3_l2_market_map.json.gz ให้รอบที่มีผล ⑫ อยู่แล้ว (หมวดหลักใช้ของผลเดิมใน main_category) - embed เฉพาะเทรนด์
    (NVIDIA เทรนด์ละ 1 ครั้ง) ใช้เวกเตอร์สินค้าจาก cache ไม่เรียก LLM ไม่แตะผล ⑫ เดิม; คำนวณใหม่แล้วสินค้าอันดับ 1 ต้องตรงผลเดิมทุกเทรนด์
    ไม่ตรง = เวกเตอร์เทรนด์หรือตลาดเปลี่ยน -> หยุดโดยไม่บันทึกอะไร"""
    if not RESULT_PATH.exists():
        raise SystemExit(f"❌ ไม่มี {RESULT_PATH.name} - รัน ⑫ แบบปกติก่อน")
    with open(RESULT_PATH, encoding="utf-8") as f:
        result = json.load(f)
    df = load_catalog()
    if not str(result.get("category_level") or "").startswith("L2") or result.get("n_products_total") != len(df):
        raise SystemExit(f"❌ ผล ⑫ รอบนี้ไม่ได้แยกหมวดด้วย L2 ของ Euromonitor บนตลาด {len(df)} SKU "
                         f"(category_level={result.get('category_level')!r}, n_products_total={result.get('n_products_total')}) - ต้องใช้ --categories-only ก่อน")
    profiles = {(p.get("stream", "?"), p["trend"]): p for p in load_real_trend_profiles()}
    product_embeddings = load_checkpoint(df)
    groups = product_groups(df)
    tier_recs, tier_key, tier_meta = market_tiers(df)
    entries, decisions, problems = {}, {}, []
    texts = {}
    for key, r in result["results"].items():
        profile = profiles.get((r.get("stream", "?"), r["trend_name"]))
        text = build_trend_matchable_text(profile) if profile else ""
        if text.strip() and (r.get("main_category") or {}).get("category"):
            texts[key] = text
    vectors = embed_trend_texts(list(texts.values()))
    for key, r in result["results"].items():
        profile = profiles.get((r.get("stream", "?"), r["trend_name"]))
        category = (r.get("main_category") or {}).get("category")
        if key not in texts:
            print(f"  ⏭️ ข้าม '{r['trend_name']}' - ไม่พบ profile จาก ⑪ / ไม่มีข้อความให้ embed / ไม่มีหมวดหลัก")
            continue
        scored = score_products(vectors[texts[key]], df, product_embeddings, groups, tier_recs)
        old_top = ((r.get("top_matches") or [{}])[0]).get("product_name")
        for attempt in range(1, 4):   # ข้อความเทรนด์ยาวมากทำให้ NVIDIA ตอบเวกเตอร์ต่างกันได้ (เจอ 2026-10-21) - ยิงใหม่จนอันดับ 1 ตรงผลเดิม (สูงสุด 3 ครั้ง)
            if not old_top or scored[0]["product_name"] == old_top:
                break
            print(f"  ↻ {r['trend_name']}: อันดับ 1 ไม่ตรงผลเดิม - embed ข้อความเทรนด์ใหม่ครั้งที่ {attempt}/3", flush=True)
            scored = score_products(embed_trend_texts([texts[key]], refresh=True)[texts[key]], df, product_embeddings, groups, tier_recs)
        if old_top and scored[0]["product_name"] != old_top:
            problems.append(r["trend_name"])
            print(f"  ❌ {r['trend_name']}: อันดับ 1 ไม่ตรงกับผลเดิม ({scored[0]['product_name']!r} vs {old_top!r})")
            continue
        entries[key], decisions[key] = (profile, scored), {"category": category}
        print(f"  ✓ {r['trend_name']}: {category} ({sum(1 for s in scored if s['group'] == category):,} สินค้า)")
    if problems:
        raise SystemExit(f"❌ ไม่บันทึก - {len(problems)} เทรนด์คำนวณใหม่แล้วไม่ตรงผลเดิม: {', '.join(problems)}")
    write_l2_map(df, groups, tier_recs, entries, decisions)


def backfill_categories():
    """🆕 (2026-09-28) เติม "by_category" ให้ผล ⑫ ของรอบที่รันก่อนมีการแยกหมวด - embed เทรนด์ใหม่ (NVIDIA
    เทรนด์ละ 1 ครั้ง) ใช้เวกเตอร์สินค้าจาก cache เท่านั้น
    🆕 (2026-10-01) หมวด = Level 2 ของ Euromonitor และตลาดกรองเหลือ L1 = Beauty and Personal Care - ผลที่ได้ต่างจากเดิม:
      - by_category / n_products_compared / similarity_stats / category+group ของ top_matches คิดใหม่จากตลาดที่กรองแล้ว
      - ถ้า top_matches เดิมมีสินค้านอกกลุ่มความงาม (ถูกกรองออกแล้ว) จะสร้าง top_matches ใหม่จากตลาดที่กรอง: ชิ้นที่เคยมี
        ใช้เหตุผล LLM เดิม ชิ้นใหม่ที่เข้า top MATCH_REASON_TOP_K ให้ LLM เขียนเหตุผล (เรียก LLM เฉพาะกรณีนี้)
    เวกเตอร์เทรนด์ต้องได้ผลเดิม: ตรวจว่าสินค้าอันดับ 1 ตรงกับ top_matches เดิม ไม่ตรง = ⑪ เปลี่ยนไปแล้ว -> หยุด"""
    if not RESULT_PATH.exists():
        raise SystemExit(f"❌ ไม่มี {RESULT_PATH.name} - รัน ⑫ แบบปกติก่อน")
    with open(RESULT_PATH, encoding="utf-8") as f:
        result = json.load(f)
    profiles = {(p.get("stream", "?"), p["trend"]): p for p in load_real_trend_profiles()}
    df = load_catalog()
    print(f"ตลาดที่ใช้: {len(df)} SKU (กรอง L1 = {BEAUTY_L1})")
    product_embeddings = load_checkpoint(df)
    groups = product_groups(df)
    group_sizes = groups.value_counts().to_dict()
    sub_sizes = subgroup_sizes(df)
    tier_recs, tier_key, tier_meta = market_tiers(df)   # 🆕 (2026-10-12) ช่วงราคาตามที่ config/market_tiers.json กำหนด
    n_rebuilt = 0
    entries = {}   # คีย์ผล -> (profile, scored) ไว้ให้ LLM เลือกหมวดหลักหลังจบลูป (🆕 2026-10-08)

    for key, r in result["results"].items():
        profile = profiles.get((r.get("stream", "?"), r["trend_name"]))
        text = build_trend_matchable_text(profile) if profile else ""
        if not text.strip():
            print(f"  ⏭️ ข้าม '{r['trend_name']}' - ไม่พบ profile จาก ⑪ หรือไม่มีข้อความให้ embed")
            continue
        scored = score_products(get_embedding(text, "query"), df, product_embeddings, groups, tier_recs)
        entries[key] = (profile, scored)
        old_matches = r.get("top_matches") or []
        old_top = (old_matches or [{}])[0].get("product_name")
        if old_top and scored[0]["product_name"] != old_top:
            raise SystemExit(f"❌ '{r['trend_name']}': อันดับ 1 ไม่ตรงกับผลเดิม ({scored[0]['product_name']!r} vs "
                             f"{old_top!r}) - profile ⑪ เปลี่ยนไปแล้ว ให้รัน ⑫ ใหม่ทั้งขั้นแทน")

        lookup = {_match_key(s): s for s in scored}
        new_keys = [_match_key(s) for s in scored[:TOP_K]]
        if new_keys != [_match_key(m) for m in old_matches]:   # ตลาดที่กรอง/หมวดใหม่ทำให้ top 15 เปลี่ยน (ตัดออก หรือมีสินค้าเข้ามาแทรก)
            old_by_key = {_match_key(m): m for m in old_matches}
            rebuilt = []
            for rank, s in enumerate(scored[:TOP_K]):
                entry = {k: v for k, v in s.items() if k != "_idx"}
                old = old_by_key.get(_match_key(s))
                reason = old.get("match_reason") if old else None
                if rank < MATCH_REASON_TOP_K and not reason:
                    reason = generate_match_reason(profile, df.loc[s["_idx"]])
                entry["match_reason"] = reason if rank < MATCH_REASON_TOP_K or old else None
                rebuilt.append(entry)
            dropped = [m["product_name"][:35] for m in old_matches if _match_key(m) not in set(new_keys)]
            added = [s["product_name"][:35] for s in scored[:TOP_K] if _match_key(s) not in old_by_key]
            r["top_matches"] = rebuilt
            n_rebuilt += 1
            print(f"  ↻ {r['trend_name']}: top_matches สร้างใหม่ (ตัดออก {len(dropped)}: {'; '.join(dropped)} | เพิ่มเข้า {len(added)}: {'; '.join(added)})")
        else:
            for m in old_matches:   # top 15 เหมือนเดิม - แค่หมวด/กลุ่มเปลี่ยนเป็น L2 ของ Euromonitor
                info = lookup[_match_key(m)]
                m["category"], m["group"], m["subgroup"] = info["category"], info["group"], info["subgroup"]

        sims = [s["similarity"] for s in scored]
        r["n_products_compared"] = len(scored)
        r["similarity_stats"] = {"max": round(max(sims), 4), "min": round(min(sims), 4), "mean": round(float(np.mean(sims)), 4)}

    decisions = main_categories(entries, MAIN_CATEGORY_LABELS)
    for key, (profile, scored) in entries.items():
        r = result["results"][key]
        apply_main_category(r, decisions[key], scored, group_sizes, sub_sizes, tier_key)
        cats = ", ".join(f"{c['group']} {c['n_pool']}" for c in r["by_category"]["categories"])
        print(f"  ✓ {r['trend_name']}: [{r['main_category']['category']}] {cats}")
    write_l2_map(df, groups, tier_recs, entries, decisions)

    result["n_products_total"] = len(df)
    result["catalog_filter"] = f"L1 = {BEAUTY_L1}"
    result["category_level"] = "L2 (Euromonitor, product_category.csv)"
    result.update(tier_meta)
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"บันทึกลง {RESULT_PATH} (สร้าง top_matches ใหม่ {n_rebuilt}/{len(result['results'])} เทรนด์)")


def _column_signature(by_category):
    """คอลัมน์ + สินค้าในคอลัมน์ของผลแยกหมวด ไว้ตรวจว่าคำนวณใหม่แล้วได้ผลเดิม"""
    return [(c["group"], [(p["brand"], p["product_name"]) for p in c["products"]])
            for c in (by_category or {}).get("categories", [])]


def backfill_price_tiers():
    """🆕 (2026-10-07) เติมช่วงราคาตลาด (price_tiers - category_breakdown._price_tiers) ให้คอลัมน์หมวดของผล ⑫ ที่มีอยู่
    embed เฉพาะเทรนด์ (NVIDIA เทรนด์ละ 1 ครั้ง) ใช้เวกเตอร์สินค้าจาก cache ไม่เรียก LLM และไม่แตะส่วนอื่นของผลเดิม
    (top_matches / similarity_stats / คอลัมน์ / สินค้าในคอลัมน์ คงเดิมทุกตัว - เติมแค่ price_tiers)
    ต้องเป็นผลที่แยกหมวดด้วย L2 ของ Euromonitor บนตลาดเดียวกับแคตตาล็อกตอนนี้ และคำนวณใหม่แล้วคอลัมน์/สินค้าต้องตรงผลเดิมทุกเทรนด์
    ไม่ตรง = เวกเตอร์เทรนด์หรือตลาดเปลี่ยน -> หยุดโดยไม่บันทึกอะไรเลย (รอบที่ยังใช้หมวดเดิมของ Watsons ให้ใช้ --categories-only แทน
    ซึ่งเปลี่ยนตลาด/หมวดด้วย)"""
    if not RESULT_PATH.exists():
        raise SystemExit(f"❌ ไม่มี {RESULT_PATH.name} - รัน ⑫ แบบปกติก่อน")
    with open(RESULT_PATH, encoding="utf-8") as f:
        result = json.load(f)
    df = load_catalog()
    if not str(result.get("category_level") or "").startswith("L2") or result.get("n_products_total") != len(df):
        raise SystemExit(f"❌ ผล ⑫ รอบนี้ไม่ได้แยกหมวดด้วย L2 ของ Euromonitor บนตลาด {len(df)} SKU "
                         f"(category_level={result.get('category_level')!r}, n_products_total={result.get('n_products_total')}) "
                         f"- เติมช่วงราคาอย่างเดียวไม่ได้ ต้องใช้ --categories-only (เปลี่ยนตลาด/หมวดด้วย)")
    profiles = {(p.get("stream", "?"), p["trend"]): p for p in load_real_trend_profiles()}
    product_embeddings = load_checkpoint(df)
    groups = product_groups(df)
    group_sizes = groups.value_counts().to_dict()
    sub_sizes = subgroup_sizes(df)
    tier_recs, tier_key, tier_meta = market_tiers(df)   # 🆕 (2026-10-12) basis "unit_price" = ช่วงราคาต่อปริมาณ (config/market_tiers.json)
    print(f"ช่วงราคา: {tier_meta['tier_basis']} {tier_meta['tier_config']}")

    updates, problems = {}, []
    for key, r in result["results"].items():
        profile = profiles.get((r.get("stream", "?"), r["trend_name"]))
        text = build_trend_matchable_text(profile) if profile else ""
        if not text.strip() or not (r.get("by_category") or {}).get("categories"):
            print(f"  ⏭️ ข้าม '{r['trend_name']}' - ไม่พบ profile จาก ⑪ / ไม่มีข้อความให้ embed / ไม่มีผลแยกหมวด")
            continue
        scored = score_products(get_embedding(text, "query"), df, product_embeddings, groups, tier_recs)
        new = category_breakdown(scored, group_sizes, subgroup_sizes=sub_sizes, tier_key=tier_key,
                                 main_category=(r.get("main_category") or {}).get("category"))   # ผลก่อน 2026-10-08 ไม่มี = โหมดเดิม
        if _column_signature(new) != _column_signature(r["by_category"]):
            problems.append(r["trend_name"])
            print(f"  ❌ {r['trend_name']}: คอลัมน์/สินค้าในคอลัมน์ไม่ตรงกับผลเดิม")
            continue
        updates[key] = [(c["price_tiers"], c["products"]) for c in new["categories"]]
        tiers = " / ".join(f"{c['group']}: " + ", ".join(f"{t['label']} {t['n_total']}" for t in c["price_tiers"] or [])
                           for c in new["categories"])
        print(f"  ✓ {r['trend_name']}: {tiers}")
    if problems:
        raise SystemExit(f"❌ ไม่บันทึก - {len(problems)} เทรนด์คำนวณใหม่แล้วไม่ตรงผลเดิม: {', '.join(problems)}")

    for key, tiers in updates.items():
        for c, (t, products) in zip(result["results"][key]["by_category"]["categories"], tiers):
            c["price_tiers"] = t
            c["products"] = products   # ชิ้นเดิมทุกตัว (ตรวจแล้วข้างบน) - เพิ่มฟิลด์ขนาด/฿ต่อหน่วยเมื่อใช้ช่วงราคาต่อปริมาณ
    result.update(tier_meta)
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"บันทึกลง {RESULT_PATH} (เติมช่วงราคา {len(updates)}/{len(result['results'])} เทรนด์)")


def generate_match_reason(profile, product_row):
    """🆕 (2026-09-14, แก้ตามที่เจ้าของงานสั่ง "ใช้แค่ similarity ส่วน LLM อยากแค่ให้เหตุผลพอแล้ว") ให้
    LLM เขียนคำอธิบายสั้นๆ ว่าสินค้าจริงชิ้นนี้เกี่ยวกับ Job-to-be-Done ของเทรนด์ยังไง - **ไม่ให้ตัดสิน
    verdict (Match/Partial/No-match) แล้ว** เพราะเจ้าของงานตัดสินใจว่าตัวตัดสินจริงว่า "ใช่ไหม" ยังคงเป็น
    similarity (embedding) เท่านั้น - LLM มีหน้าที่แค่อธิบายให้คนอ่านรายงานเข้าใจ ไม่ใช่ให้คำตัดสินที่แข่ง
    กับ similarity หรือแอบมาแทนที่งาน calibration ของ M6 (ดู Detail/.../แผนแก้ Data Science Audit.md)
    ที่ยังต้องรอ label จากคนจริงอยู่

    รุ่นก่อนหน้านี้ (เวอร์ชันแรกของฟังก์ชันนี้) เคยให้ตัดสิน verdict ด้วย - ถอดออกตามคำสั่งนี้ ไม่ใช่ลืม

    กราวด์คำอธิบายกับข้อความจริง 2 ฝั่งเท่านั้น (JTBD ของเทรนด์ + คำอธิบายสินค้าจริงจาก Konvy) ไม่ส่ง
    similarity score เข้าไปในพรอมต์เลย (กันโมเดลอ้างอิงเลขนั้นแทนที่จะอ่านข้อความจริง) ป้องกันไม่ให้โมเดล
    เดาจากชื่อแบรนด์/ความรู้ภายนอก

    คืน reason (str) - "" ถ้า LLM ตอบผิดรูปแบบ/เรียกไม่สำเร็จ (ไม่ raise - ให้ caller ใส่ "" แล้วรันต่อขั้น
    อื่นได้ ไม่ทำทั้งรอบพังเพราะคู่เดียว)"""
    system_prompt = """You explain, in one short sentence, how a real product relates to what a trend
is about (what shoppers want done). Ground your answer ONLY in the two texts given below - never use
outside brand/product knowledge, and you are not given a match score, so never invent or reference one.

Do NOT judge or classify whether this is a "good match" - just state plainly, in concrete terms,
what the product actually does and how that does or doesn't line up with what the trend is about.
Note real gaps as well as real overlaps if both are present. Use everyday words a non-expert
understands: say "goal" or "need", never "job-to-be-done", "point of difference" or "similarity".

Return ONLY this JSON, under 25 words, no invented claims, no leading "+" on numbers:
{"reason": "..."}"""

    user_prompt = f"""TREND
Functional Consequence: {profile.get('functional_consequence', '')}
Job To Be Done: {profile.get('job_to_be_done', '')}
Point of Difference: {profile.get('point_of_difference', '')}

REAL PRODUCT
Name: {product_row.get('product_name', '')}
Benefits (as listed by retailer): {product_row.get('Key_Benefits', '')}
Description: {str(product_row.get('Product_Insights', ''))[:400]}"""

    try:
        # 🆕 (2026-09-15) เปลี่ยนจาก Typhoon -> Amazon Nova Lite (Bedrock) - จุดนี้เรียกบ่อยที่สุดในระบบ
        # (top-5 matches x ทุกเทรนด์ x ทุกครั้งที่ค้นแบรนด์ผ่าน ⑬) output สั้นแค่ประโยคเดียว (<=25 คำ) ใช้
        # โมเดลใหญ่ไม่คุ้ม - Nova Lite อยู่ cloud เดียวกับ Bedrock เอง latency ต่ำ ราคาถูก เหมาะกับงานปริมาณ
        # มากแบบนี้ที่สุด (ดู Detail/.../แผนเปลี่ยนโมเดล LLM — Bedrock + Typhoon.md)
        with use_bedrock(model_id="amazon.nova-lite-v1:0"):
            resp = tf.client.chat.completions.create(
                model=tf.MODEL_NAME_META,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_prompt}],
                temperature=0.1, max_tokens=150,
                response_format={"type": "json_object"},
            )
        raw = resp.choices[0].message.content or ""
        clean = re.sub(r'([:\[,]\s*)\+(\d)', r'\1\2', raw)  # กัน "+1" ที่ไม่ใช่ JSON ถูกต้อง (เจอจริงกับ
                                                             # Typhoon ใน summarize_trend_clusters() มาแล้ว)
        data = json.loads(clean)
        return (data.get("reason") or "").strip()[:300]
    except Exception as e:
        print(f"      ⚠️ match reason ล้มเหลว ({product_row.get('product_name', '?')[:40]}): {str(e)[:100]}")
        return ""


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="⑫ จับคู่เทรนด์ Top N กับสินค้า Konvy ทั้งร้าน")
    parser.add_argument("--embed-only", action="store_true",
                        help="🆕 embed สินค้าในแคตตาล็อกลง checkpoint อย่างเดียวแล้วจบ - ไม่อ่าน ⑪ ไม่เรียก LLM ไม่แตะผล ⑫ ของรอบไหน "
                             "(รันต่อจากที่ค้างได้; ⑫ รอบถัดไปจะใช้ cache นี้ ไม่ embed ซ้ำ)")
    parser.add_argument("--workers", type=int, default=EMBED_WORKERS,
                        help=f"จำนวนตัวที่ยิง embedding ขนานกัน (ค่าตั้งต้น {EMBED_WORKERS}; เจอ rate limit บ่อยให้ลด)")
    parser.add_argument("--categories-only", action="store_true",
                        help="เติมผลแยกหมวด (by_category) ให้ผล ⑫ ที่มีอยู่แล้ว - ไม่เรียก LLM ไม่แตะผลเดิม")
    parser.add_argument("--price-tiers-only", action="store_true",
                        help="🆕 เติม/คำนวณใหม่ช่วงราคาตลาด (ต่ำ/กลาง/สูง - ราคาขายหรือราคาต่อปริมาณตาม config/market_tiers.json) ให้คอลัมน์หมวดของผล ⑫ ที่มีอยู่ - ไม่เรียก LLM ไม่แตะผลเดิม")
    parser.add_argument("--l2-map-only", action="store_true",
                        help="🆕 (2026-10-21) เขียน phase3_l2_market_map.json.gz (แผนที่ตลาดระดับหมวด L2 - ความใกล้เทรนด์ + ยอดขายต่อสินค้า) ให้ผล ⑫ ที่มีอยู่ "
                             "- embed เฉพาะเทรนด์ ไม่เรียก LLM ไม่แตะผลเดิม")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers ต้อง >= 1")
    if args.embed_only:
        df = load_catalog()
        print(f"แคตตาล็อก: {len(df)} SKU (กรอง L1 = {BEAUTY_L1}) · {df['brand'].nunique()} แบรนด์")
        embed_all_products(df, workers=args.workers)
        print(f"✅ embed ครบ {len(df)} ชิ้น - checkpoint: {CHECKPOINT_PATH}")
        sys.exit(0)
    if args.categories_only:
        backfill_categories()
        sys.exit(0)
    if args.price_tiers_only:
        backfill_price_tiers()
        sys.exit(0)
    if args.l2_map_only:
        backfill_l2_map()
        sys.exit(0)

    print("=" * 70)
    print("Phase 3 ⑫ — ชั้นอุปทาน (NVIDIA embedding): Top N เทรนด์จาก ⑪ vs สินค้าจริงทั้งตลาด")
    print("=" * 70)

    trend_profiles = load_real_trend_profiles()
    print(f"โหลด {len(trend_profiles)} trend profile จาก ⑪ (Top N ตาม Rank Score ของ ⑥)")

    df = load_catalog()
    print(f"โหลดสินค้าจริงแล้ว: {len(df)} รายการ (กรอง L1 = {BEAUTY_L1}), {df['brand'].nunique()} แบรนด์\n")

    print(f"กำลัง embed {len(trend_profiles)} trend profile (input_type=query)...")
    # 🆕 (2026-09-12, audit M4) เดิม key ด้วยชื่อเทรนด์เปล่าๆ - ถ้าชื่อชนกันข้ามสาย (เช่น "Barrier Repair
    # Skincare" เจอทั้ง Paper กับ News) ตัวหลังทับตัวแรกเงียบๆ ใน dict (15 profile เหลือ 14 ผลลัพธ์จริง
    # ตามที่เจอ) - เปลี่ยนเป็น key ผสม "stream::trend" กันชนกัน (เก็บชื่อเทรนด์ล้วนไว้แสดงผลแยกต่างหาก)
    trend_vectors = {}
    trend_names = {}
    trend_streams = {}
    trend_profile_by_key = {}
    skipped_trends = []
    for profile in trend_profiles:
        stream = profile.get("stream", "?")
        key = f"{stream}::{profile['trend']}"
        text = build_trend_matchable_text(profile)
        # 🆕 (2026-09-16) ⑪ ตอบ "ข้อมูลไม่พอ" ได้จริงทั้ง 4 ฟิลด์ที่ใช้จับคู่ (เจอกับเทรนด์เชิงช่องทางขาย เช่น
        # "Livestream Social Commerce" ที่ไม่มีคุณสมบัติสินค้าให้จับเลย) - build_trend_matchable_text() กรอง
        # คำนั้นทิ้งจึงได้ข้อความว่าง แล้วไปตายที่ embedding API (400 x5 -> ทั้งไปป์ไลน์หยุด) ข้ามเทรนด์นั้น
        # แล้วรันต่อดีกว่า เพราะเทรนด์ที่เหลือจับคู่ได้ปกติ - บันทึกไว้ในผลลัพธ์ว่าข้ามอะไรไปเพราะอะไร
        if not text.strip():
            print(f"    ⏭️ ข้าม '{profile['trend']}' [{stream}] - ⑪ ตอบ 'ข้อมูลไม่พอ' ทุกฟิลด์ที่ใช้จับคู่ "
                  f"(ไม่มีข้อความให้ embed)")
            skipped_trends.append({"trend": profile["trend"], "stream": stream,
                                   "reason": "ไม่มีข้อความจับคู่ - ⑪ ตอบ 'ข้อมูลไม่พอ' ครบทั้ง 4 ฟิลด์"})
            continue
        trend_vectors[key] = get_embedding(text, "query")
        trend_names[key] = profile["trend"]
        trend_streams[key] = stream
        trend_profile_by_key[key] = profile
    if not trend_vectors:
        raise SystemExit("❌ ไม่มีเทรนด์ไหนมีข้อความให้จับคู่เลย - หยุดก่อน embed สินค้า (ตรวจผล ⑪ ก่อน)")
    print(f"เสร็จแล้ว ({len(trend_vectors)} เทรนด์"
          + (f", ข้าม {len(skipped_trends)})" if skipped_trends else ")") + "\n")

    product_embeddings = embed_all_products(df, workers=args.workers)
    groups = product_groups(df)
    group_sizes = groups.value_counts().to_dict()
    sub_sizes = subgroup_sizes(df)
    tier_recs, tier_key, tier_meta = market_tiers(df)   # 🆕 (2026-10-12) ช่วงราคาตาม config/market_tiers.json

    print("\nกำลังคำนวณ cosine similarity ทุกคู่ (เทรนด์ x สินค้า) แบบ deterministic (ไม่ยิง API เพิ่ม)...")
    all_results, entries = {}, {}
    for key, tvec in trend_vectors.items():
        scored = score_products(tvec, df, product_embeddings, groups, tier_recs)
        entries[key] = (trend_profile_by_key[key], scored)
        all_results[key] = {
            "trend_name": trend_names[key],
            "stream": trend_streams.get(key, "?"),
            "top_matches": scored[:TOP_K],
            "n_products_compared": len(scored),
            "similarity_stats": {
                "max": round(max(s["similarity"] for s in scored), 4),
                "min": round(min(s["similarity"] for s in scored), 4),
                "mean": round(float(np.mean([s["similarity"] for s in scored])), 4),
            },
        }

    # 🆕 (2026-10-08) หมวดหลักของแต่ละเทรนด์ให้ LLM เลือก (trend_category.py) แล้วแยกสินค้าที่ใกล้เทรนด์ตามหมวดนั้น
    # (by_category - หน้าสินค้าของรายงาน ⑯ ใช้ตัวนี้แทน top_matches; 🆕 2026-09-28)
    print("\nกำลังให้ LLM เลือกหมวดหลัก (L2) ของแต่ละเทรนด์ (คำตัดสินเดิมที่เคยเลือกไว้ใช้ซ้ำ)...")
    decisions = main_categories(entries, MAIN_CATEGORY_LABELS)
    for key, (profile, scored) in entries.items():
        apply_main_category(all_results[key], decisions[key], scored, group_sizes, sub_sizes, tier_key)
        print(f"  ✓ {all_results[key]['trend_name']}: {decisions[key]['category']} ({decisions[key]['source']}) - {decisions[key]['reason'][:90]}")
    write_l2_map(df, groups, tier_recs, entries, decisions)   # 🆕 (2026-10-21) แผนที่ตลาดระดับหมวด L2 ให้รายงาน ⑯ ⑰

    # 🆕 (2026-09-14) เหตุผลข้อความ (Match/Partial/No-match + ทำไม) ต่อ top MATCH_REASON_TOP_K ของแต่ละ
    # เทรนด์ - เดิมมีแต่ similarity ตัวเลข ไม่มีใครอธิบายว่า "ทำไมสินค้านี้เข้ากับเทรนด์" เลย (ดู audit M6)
    n_total_calls = sum(min(MATCH_REASON_TOP_K, len(r["top_matches"])) for r in all_results.values())
    print(f"\nกำลังให้เหตุผล (ไม่ตัดสิน verdict - similarity ยังเป็นตัวจัดอันดับ/ตัดสินหลัก) ต่อสินค้า "
          f"(Typhoon, {n_total_calls} คู่ = {len(all_results)} เทรนด์ x top {MATCH_REASON_TOP_K})...")
    # 🆕 (2026-10-07) โหมดอัปเดตรอบเดิม - ใช้เหตุผลของรอบต้นทางซ้ำ (ดู load_reusable_reasons)
    source_dir = refresh_source_dir()
    reusable = load_reusable_reasons(source_dir)
    n_done = n_reused = 0
    for key, r in all_results.items():
        profile = trend_profile_by_key.get(key, {})
        src = reusable.get((r["stream"], r["trend_name"]))
        old_reasons = src["reasons"] if src and src["text"] == build_trend_matchable_text(profile) else {}
        for m in r["top_matches"][:MATCH_REASON_TOP_K]:
            old = old_reasons.get(_match_key(m))
            if old:
                m["match_reason"] = old
                n_reused += 1
            else:
                m["match_reason"] = generate_match_reason(profile, df.loc[m["_idx"]])
            n_done += 1
            print(f"  [{n_done}/{n_total_calls}]{' ↺' if old else ''} {m['brand']} {m['product_name'][:40]} -> {m['match_reason']}")
        for m in r["top_matches"][MATCH_REASON_TOP_K:]:
            m["match_reason"] = None  # ไม่ได้ถาม (เกิน top K) - ยังคง key ไว้ให้ schema สม่ำเสมอ

    for r in all_results.values():
        for m in r["top_matches"]:
            m.pop("_idx", None)

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "_note": "⑫ ชั้นอุปทาน - Top N เทรนด์จาก ⑪ (คัดด้วย Rank Score ของ ⑥) vs 10,622 SKU จริงผ่าน NVIDIA NIM "
                    "embedding - ครั้งแรกที่รันจบด้วยข้อมูลจริงทั้งสองฝั่ง (2026-09-11) - 2026-10-01: ตลาดกรองเหลือ L1 = Beauty and Personal Care "
                    "และหมวด = Level 2 ของ Euromonitor",
            "n_products_total": len(df), "catalog_filter": f"L1 = {BEAUTY_L1}", "category_level": "L2 (Euromonitor, product_category.csv)",
            # 🆕 (2026-10-12) ช่วงราคาของคอลัมน์ (by_category[].price_tiers) แบ่งด้วยอะไร: price = ราคาขายของทั้งคอลัมน์ /
            # unit_price = ราคาต่อปริมาณเทียบในชนิดสินค้าเดียวกัน (unit_price_tiers.py) - รายงาน ⑯ เลือกข้อความป้ายตามนี้
            **tier_meta,
            "top_k": TOP_K, "results": all_results,
            # 🆕 (2026-09-16) เทรนด์ที่ไม่มีข้อความให้จับคู่ (⑪ ตอบ "ข้อมูลไม่พอ") - เก็บไว้ให้เห็นว่ารอบนี้
            # จับคู่กี่เทรนด์จากทั้งหมดกี่เทรนด์ ไม่ใช่หายเงียบๆ
            "n_trends_total": len(trend_profiles), "n_trends_matched": len(all_results),
            "skipped_trends": skipped_trends,
            # 🆕 (2026-10-07) โหมดอัปเดตรอบเดิม: รอบต้นทาง + จำนวนเหตุผลที่ใช้ของเดิม (None = รันปกติ)
            "reused_from": source_dir.name if source_dir else None, "n_reused_reasons": n_reused,
        }, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    for key, r in all_results.items():
        print(f"\n🎯 เทรนด์ [{r['stream']}]: {r['trend_name']}")
        print(f"   similarity: max={r['similarity_stats']['max']} mean={r['similarity_stats']['mean']} "
              f"min={r['similarity_stats']['min']}")
        print(f"   Top 5 จาก {r['n_products_compared']} สินค้าจริง:")
        for m in r["top_matches"][:5]:
            print(f"     [{m['similarity']:.4f}] {m['brand']} - {m['product_name'][:65]} ({m['category']})")
            if m.get("match_reason"):
                print(f"       -> {m['match_reason']}")

    if source_dir:
        print(f"\nใช้เหตุผลเดิมจากรอบ {source_dir.name}: {n_reused}/{n_total_calls} คู่ (เรียก LLM {n_total_calls - n_reused} คู่)")
    print(f"\nบันทึกผลเต็มลง {RESULT_PATH}")
