# -*- coding: utf-8 -*-
"""
Phase 2 — Rank Score: จัดอันดับเทรนด์ด้วยตัวเลขเดียว รวม 3 สัญญาณ

ตอบคำถาม "ทำไมเทรนด์นี้เป็นอันดับ 1" ด้วยตัวเลขที่อธิบายได้ (ไม่ใช่แค่ลำดับที่ Louvain/LLM จัดมาให้
โดยบังเอิญ) — ดู Detail/05 งานที่ยังไม่ได้ทำ/Backlog และแนวทางต่อไป.md ข้อ 30

    Rank Score = f(Z_Delta, จำนวนสายที่เจอคีย์เวิร์ดนี้, ขนาดคลัสเตอร์)

**ทำไมไม่ใช้ "Longevity Score" (คะแนนที่ LLM ให้เองใน summarize_trend_clusters):** ไม่มี rubric
กำกับเลยในพรอมต์เดิม (`"score": 50` เป็นแค่ตัวอย่าง format ไม่ได้บอกเกณฑ์) เสี่ยงปัญหาเดียวกับ
`investment_signal` ที่เคยพิสูจน์แล้วว่า LLM ตัดสินเชิงตัวเลขเองแม่นแค่ 40.9% แย่กว่ากฎตายตัวจากข้อมูล
ดิบ (63.4%) - ใช้เป็นคำอธิบายประกอบได้ แต่ไม่ใช้จัดอันดับหลัก

## 3 สัญญาณ

1. **Z_Delta** (น้ำหนักหลักเมื่อมี) — จาก `forecast_trend()` ข้อมูล Google Trends จริง ผ่าน walk-forward
   validation แล้วจริง (63.4% แม่นกว่า baseline, ชนะ 6/6 cutoff) — **ยังไม่มีให้ใช้ตอนนี้** เพราะยังไม่มี
   สายไหนใน v2 architecture นี้ไปถึงขั้นยิง Google Trends เลย (ดู Backlog ข้อ 25)
2. **จำนวนสายที่เจอคีย์เวิร์ดเดียวกัน** (โบนัส, ฟรี, deterministic) — นับจาก keyword set ของแต่ละสาย
   (`extract_strategic_keywords` output) ว่าคีย์เวิร์ดของเทรนด์นี้ไปเจอในสายอื่นด้วยไหม
3. **ขนาดคลัสเตอร์ normalize ภายในสายตัวเอง** (fallback ก่อนมี Z_Delta) — จำนวน node ที่ Louvain จัดกลุ่ม
   ให้ (คอลัมน์ "Cluster Size" ที่เพิ่งเพิ่มเข้า `summarize_trend_clusters` — ดู Backlog ข้อ 30) หารด้วย
   คลัสเตอร์ที่ใหญ่ที่สุดในสายเดียวกัน (ห้ามเทียบขนาดดิบข้ามสาย เพราะแต่ละสาย scrape เนื้อหาคนละปริมาณ)

## โหมดการคำนวณ

- **มี Z_Delta แล้ว (โหมดเต็ม):** `Rank Score = Z_Delta × (1 + 0.1 × (จำนวนสาย - 1))`
  - โบนัสจำนวนสายแค่ +10%/สายเพิ่ม (สูงสุด +30% ที่ 4 สาย) เพราะ Z_Delta มีหลักฐานสถิติรองรับแล้ว
    ไม่ควรให้สัญญาณที่ยังไม่ verify (จำนวนสาย) มามีน้ำหนักเทียบเท่า
- **ยังไม่มี Z_Delta (โหมด preliminary):** `Rank Score = ขนาดคลัสเตอร์ normalize × (1 + 0.2 × (จำนวนสาย - 1))`
  - โบนัสจำนวนสายสูงกว่า (+20%/สาย) เพราะเป็นสัญญาณ deterministic ที่เชื่อถือได้กว่าขนาดคลัสเตอร์ดิบ
  - **ต้องติดป้าย "preliminary" เสมอ** ไม่ใช่อันดับสุดท้าย - รอ Z_Delta จริงก่อนเชื่อเต็มที่

## 📖 ความหมายตัวแปร/คอลัมน์ทั้งหมด (อ้างอิงด่วน)

| ชื่อ (ในโค้ด/output) | ความหมาย | มาจากไหน | ช่วงค่า/หน่วย |
|---|---|---|---|
| `z_delta` / **Z_Delta** | ค่าเฉลี่ย z-score ที่พยากรณ์ล่วงหน้า (`Forecast_Avg_Z`) ลบด้วยค่า z-score ปัจจุบัน (`Current_Z`) - บอกว่าเทรนด์นี้ "กำลังจะแรงขึ้นหรือลงแค่ไหน" | `forecast_trend()` → `generate_master_trend_report()` ใน `trend_final.py` (ข้อมูล Google Trends จริงผ่านโมเดลพยากรณ์ 4 ตัว) | ไม่มีเพดานตายตัว (มักอยู่ราว -1 ถึง +2), บวก=กำลังโต, ลบ=กำลังซา, `None`=ยังไม่มีข้อมูล |
| `stream_count` / **Stream_Count** | คีย์เวิร์ดของเทรนด์นี้เจอซ้ำในกี่ใน 4 สาย (News-Intl/News-Thai/Social/Paper) - เอาค่าสูงสุดจากทุกคีย์เวิร์ดของเทรนด์ ไม่ใช่ค่าเฉลี่ย | `build_keyword_stream_index()` เทียบ `Search_Keywords` ข้ามสายทั้งหมด (case-insensitive, exact match) | จำนวนเต็ม 1-4 (1 = เจอสายเดียว, 4 = ยืนยันครบทุกสาย) |
| `cluster_size` / **Cluster_Size** | จำนวน node (คำ/entity) ที่ Louvain จัดรวมไว้ในคลัสเตอร์เดียวกับเทรนด์นี้ - ยิ่งเยอะ = มี "มวลข้อความ" สนับสนุนเยอะ | คอลัมน์ `"Cluster Size"` (`len(cluster)`) ใน `summarize_trend_clusters` override (เพิ่มเข้าแก้ข้อ 30) | จำนวนเต็ม ≥1 - **ห้ามเทียบดิบข้ามสาย** (แต่ละสาย scrape ปริมาณต่างกัน) |
| `cluster_size_normalized` / **Cluster_Size_Normalized** | `cluster_size` หารด้วยคลัสเตอร์ที่ใหญ่สุดใน**สายเดียวกัน** - ทำให้เทียบข้ามสายได้อย่างเป็นธรรม | `normalize_cluster_size()` | 0.0-1.0 (1.0 = คลัสเตอร์ใหญ่สุดในสายของตัวเอง) |
| `stream_bonus` (ตัวแปรภายใน สูตร ไม่โผล่ใน output) | ตัวคูณที่ได้จากจำนวนสาย - ให้รางวัลเทรนด์ที่ยืนยันข้ามแหล่งได้มากกว่า | คำนวณใน `compute_rank_score()`: `1+0.1×(stream_count-1)` (โหมด final) หรือ `1+0.2×(stream_count-1)` (โหมด preliminary) | 1.0 (ไม่มีโบนัส, stream_count=1) ถึง 1.3/1.6 (stream_count=4) |
| **Mode** | บอกว่า Rank Score แถวนี้น่าเชื่อถือแค่ไหน - `"final (Z_Delta)"` = ใช้ตัวเลขที่ verify แล้วจริง, `"preliminary (...)"` = ยังใช้แค่ตัวสำรอง ต้องรอ Z_Delta จริงก่อนเชื่อเต็มที่ | ตัดสินใน `compute_rank_score()` จากว่า `z_delta` เป็น `None` หรือไม่ | ข้อความ 2 แบบเท่านั้น |
| **Rank Score** | ตัวเลขสุดท้ายที่ใช้จัดอันดับ - คำนวณตามสูตรของ Mode นั้นๆ | `compute_rank_score()` | ไม่มีเพดานตายตัว - **เทียบกันได้แค่ภายในผลลัพธ์ชุดเดียวกัน** ไม่ใช่ scale สัมบูรณ์ข้ามรอบการรัน |
| **Overall Rank** | ลำดับ 1, 2, 3... ตาม Rank Score มากไปน้อย รวมทุกสายเข้าด้วยกัน | เรียงลำดับใน `rank_trends_across_streams()` | จำนวนเต็ม 1 ถึง (จำนวนเทรนด์ทั้งหมดทุกสายรวมกัน) |
"""
from collections import defaultdict


def build_keyword_stream_index(keywords_by_stream, field="Search_Keywords"):
    """สร้าง index คีย์เวิร์ด (lowercase, trim) -> set ของชื่อสายที่เจอคีย์เวิร์ดนั้น

    Args:
        keywords_by_stream: dict {stream_name: df_keywords} (output จาก extract_strategic_keywords
            ต่อสาย - คอลัมน์ Trend Name, Search_Keywords, Marketing_Hooks, Visual_Vibes,
            Product_Search_Keywords)
        field: คอลัมน์ที่ใช้เทียบ - ใช้ Search_Keywords เป็นค่าเริ่มต้น (คำค้นที่คนพิมพ์จริง เทียบตรง
            ได้มากกว่า Marketing_Hooks/Visual_Vibes ที่เป็นวลีการตลาด)
    """
    index = defaultdict(set)
    for stream, df_kw in keywords_by_stream.items():
        if df_kw is None or df_kw.empty:
            continue
        for _, row in df_kw.iterrows():
            for w in str(row.get(field, "")).split(","):
                w = w.strip().lower()
                if w:
                    index[w].add(stream)
    return index


def trend_stream_count(trend_keywords_str, keyword_stream_index):
    """หาว่าคีย์เวิร์ดของเทรนด์นี้ (คอมมาคั่น) เจอในกี่สาย - เอาค่าสูงสุดจากคีย์เวิร์ดทั้งหมดของเทรนด์
    (ไม่เอาค่าเฉลี่ย เพราะแค่คีย์เวิร์ดเดียวที่ยืนยันข้ามสายได้ก็มีความหมายแล้ว ไม่ควรถูกเจือจางด้วย
    คีย์เวิร์ดอื่นในเทรนด์เดียวกันที่ไม่มีใครอื่นเจอ)"""
    kws = [w.strip().lower() for w in str(trend_keywords_str).split(",") if w.strip()]
    if not kws:
        return 1
    counts = [len(keyword_stream_index.get(w, set())) for w in kws]
    return max(counts) if counts else 1


def normalize_cluster_size(cluster_size, all_cluster_sizes_same_stream):
    """normalize ขนาดคลัสเตอร์ภายในสายเดียวกันเท่านั้น (0-1) - ห้ามเทียบข้ามสายตรงๆ
    (ดูเหตุผลเต็มใน docstring บนสุดของไฟล์)"""
    max_size = max(all_cluster_sizes_same_stream) if all_cluster_sizes_same_stream else 0
    if max_size <= 0:
        return 0.0
    return cluster_size / max_size


def compute_rank_score(cluster_size, all_cluster_sizes_same_stream, stream_count, z_delta=None):
    """คำนวณ Rank Score เดียวจาก 3 สัญญาณ - ดูสูตรเต็มใน docstring บนสุดของไฟล์

    Returns:
        dict {score, mode, z_delta, stream_count, cluster_size_normalized}
    """
    normalized_size = normalize_cluster_size(cluster_size, all_cluster_sizes_same_stream)
    if z_delta is not None:
        # 🆕 (2026-09-12, audit M5) เดิม score = z_delta * bonus ตรงๆ - ทำให้เทรนด์ขาลงที่ยืนยันข้าม
        # สายยิ่งติดลบมากขึ้น (เช่น -0.5 -> -0.6) ซึ่งดันอันดับลงต่ำกว่าเทรนด์ขาลงสายเดียว - ไม่มีประโยชน์
        # กับจุดประสงค์ของรายงาน (หา "เทรนด์ไหนกำลังจะมา") เพราะทั้งคู่ถูกคัดออกจาก top-N เหมือนกันอยู่แล้ว
        # ให้โบนัสยืนยันข้ามสายมีผลเฉพาะตอนสัญญาณเป็นบวก (ยิ่งมั่นใจว่ากำลังขึ้น) เท่านั้น
        stream_bonus = 1 + 0.1 * (stream_count - 1)
        score = z_delta * stream_bonus if z_delta > 0 else z_delta
        mode = "final (Z_Delta)"
    else:
        stream_bonus = 1 + 0.2 * (stream_count - 1)
        score = normalized_size * stream_bonus
        mode = "preliminary (cluster size - ยังไม่มี Z_Delta จริง)"

    return {
        "score": round(float(score), 4),
        "mode": mode,
        "z_delta": z_delta,
        "stream_count": stream_count,
        "cluster_size_normalized": round(float(normalized_size), 4),
    }


def apply_cross_source_confirmation(df_trends_by_stream, df_keywords_by_stream):
    """🆕 (2026-09-08, Backlog ข้อ 33 "กลุ่ม B") เชื่อม D2 ("ความสามารถปรับใช้ข้ามหมวด") ของ
    Longevity Score v2 เข้ากับข้อมูลข้ามสายจริง - ก่อนหน้านี้ `compute_longevity()` รับพารามิเตอร์
    `cross_source_confirmed` ไว้แล้วแต่ไม่มี caller ไหนส่งค่า True เข้ามาจริงเลย (ดูเอกสาร Longevity
    Score v2 §2 D2 และ §9) ฟังก์ชันนี้คือ caller ตัวนั้น - **ไม่ยิง LLM ใหม่เลย** ใช้กลไกเดียวกับ
    Rank Score (`build_keyword_stream_index`/`trend_stream_count` ด้านบน) ที่พิสูจน์แล้วด้วยข้อมูลจริง
    (ข้อ 30 - "gentle cleanser" เจอทั้งสาย Paper และ Social จริง)

    ทำไมต้องเป็นขั้นแยกต่างหาก ไม่ใช่ผูกไว้ใน summarize_trend_clusters() เอง: เพราะ
    summarize_trend_clusters() วิเคราะห์ทีละคลัสเตอร์ในสายเดียว ณ จุดที่เรียก LLM ยังไม่มีทางรู้ข้อมูล
    ของสายอื่นเลย (สายอื่นอาจยังไม่รันด้วยซ้ำ) - ต้องรอให้ทุกสายมี extract_strategic_keywords แล้วค่อย
    เทียบคีย์เวิร์ดข้ามสายได้จริง (จุดเดียวกับที่ rank_trends_across_streams() ทำอยู่แล้ว)

    Args:
        df_trends_by_stream: dict {stream_name: df_trends} (output จาก summarize_trend_clusters -
            ต้องมีคอลัมน์ "Longevity Breakdown" ที่เพิ่มเข้าไปพร้อมกับฟังก์ชันนี้ - ข้อมูลเก่าก่อนหน้านี้
            ไม่มีคอลัมน์นี้ จะถูกข้ามไปเฉยๆ ไม่ error)
        df_keywords_by_stream: dict {stream_name: df_keywords} (output จาก extract_strategic_keywords)

    Returns:
        dict {stream_name: df_trends} สำเนาใหม่ (ไม่แก้ของเดิม) ที่คอลัมน์ Longevity Score/Band/
        Breakdown ถูกคำนวณใหม่แล้วสำหรับแถวที่ยืนยันข้ามสายจริง เพิ่มคอลัมน์ "Longevity Cross-Source
        Applied" (bool) ไว้บอกความโปร่งใสว่าแถวไหนถูกปรับ
    """
    import pandas as pd

    # import แบบ local กัน circular import (bootstrap.py ไม่ import rank_trends.py กลับ)
    import sys
    from pathlib import Path

    for _p in Path(__file__).resolve().parents:
        if (_p / "common" / "bootstrap.py").exists():
            sys.path.insert(0, str(_p))
            break
    from common.bootstrap import recompute_longevity_score

    keyword_index = build_keyword_stream_index(df_keywords_by_stream)
    result = {}
    n_applied_total = 0

    for stream, df_trends in df_trends_by_stream.items():
        if df_trends is None or df_trends.empty:
            result[stream] = df_trends
            continue

        df_trends = df_trends.copy()
        if "Longevity Breakdown" not in df_trends.columns:
            print(f"  ⚠️ {stream}: ไม่มีคอลัมน์ 'Longevity Breakdown' (ข้อมูลเก่าก่อนแก้ข้อ 33 "
                  f"'กลุ่ม B') - ข้ามการปรับ cross-source ให้สายนี้")
            df_trends["Longevity Cross-Source Applied"] = False
            result[stream] = df_trends
            continue

        df_kw = df_keywords_by_stream.get(stream)
        kw_by_trend = {}
        if df_kw is not None and not df_kw.empty:
            for _, r in df_kw.iterrows():
                kw_by_trend[r["Trend Name"]] = r.get("Search_Keywords", "")

        applied_flags = []
        n_applied_stream = 0
        for idx, row in df_trends.iterrows():
            breakdown = row.get("Longevity Breakdown")
            trend_name = row["Trend Name"]
            stream_count = trend_stream_count(kw_by_trend.get(trend_name, ""), keyword_index)
            already_confirmed = isinstance(breakdown, dict) and breakdown.get("D2") == 1

            if isinstance(breakdown, dict) and stream_count > 1 and not already_confirmed:
                headwind_types = [
                    t.strip() for t in str(row.get("Longevity Headwind Types", "")).split(",") if t.strip()
                ]
                try:
                    comp_delta = int(row.get("Longevity Comparative Delta", 0) or 0)
                except (TypeError, ValueError):
                    comp_delta = 0
                new_result = recompute_longevity_score(breakdown, headwind_types, cross_source_confirmed=True,
                                                       comparative_delta=comp_delta)
                old_score = row["Longevity Score"]
                df_trends.at[idx, "Longevity Score"] = new_result["score"]
                df_trends.at[idx, "Longevity Band"] = new_result["band"]
                df_trends.at[idx, "Longevity Breakdown"] = new_result["breakdown"]
                applied_flags.append(True)
                n_applied_stream += 1
                print(f"    ✅ {stream} / \"{trend_name}\": ยืนยันข้ามสายจริง (พบใน {stream_count} สาย) "
                      f"-> D2 0 หรือ -1 -> 1, Longevity Score {old_score} -> {new_result['score']}")
            else:
                applied_flags.append(False)

        df_trends["Longevity Cross-Source Applied"] = applied_flags
        n_applied_total += n_applied_stream
        result[stream] = df_trends

    if n_applied_total == 0:
        print("  (ไม่มีเทรนด์ไหนถูกปรับรอบนี้ - ไม่มีคีย์เวิร์ดที่ยืนยันข้ามสายเกิน 1 สายสำหรับชุดข้อมูลนี้)")

    return result


def rank_trends_across_streams(df_trends_by_stream, df_keywords_by_stream, z_delta_lookup=None):
    """ฟังก์ชันหลัก - รับผลลัพธ์ทุกสาย คืนตาราง Rank Score รวมทุกเทรนด์ทุกสายเรียงจากมากไปน้อย

    Args:
        df_trends_by_stream: dict {stream_name: df_trends} (output จาก summarize_trend_clusters
            ต้องมีคอลัมน์ "Cluster Size" - ดู Backlog ข้อ 30)
        df_keywords_by_stream: dict {stream_name: df_keywords} (output จาก extract_strategic_keywords)
        z_delta_lookup: dict {(stream_name, trend_name): z_delta} หรือ None ถ้ายังไม่มีข้อมูล
            Google Trends เลย (โหมด preliminary ทั้งหมด)

    Returns:
        DataFrame เรียงจาก Rank Score มากไปน้อย คอลัมน์: Stream, Trend Name, Rank Score, Mode,
        Z_Delta, Stream_Count, Cluster_Size, Cluster_Size_Normalized
    """
    import pandas as pd

    keyword_index = build_keyword_stream_index(df_keywords_by_stream)
    z_delta_lookup = z_delta_lookup or {}

    rows = []
    for stream, df_trends in df_trends_by_stream.items():
        if df_trends is None or df_trends.empty:
            continue
        df_kw = df_keywords_by_stream.get(stream)
        kw_by_trend = {}
        if df_kw is not None and not df_kw.empty:
            for _, r in df_kw.iterrows():
                kw_by_trend[r["Trend Name"]] = r.get("Search_Keywords", "")

        if "Cluster Size" not in df_trends.columns:
            print(f"  ⚠️ {stream}: ไม่มีคอลัมน์ 'Cluster Size' (ข้อมูลเก่าก่อนแก้ข้อ 30) - ใช้ 1 แทนทุกแถว")
        all_sizes = (df_trends["Cluster Size"].tolist() if "Cluster Size" in df_trends.columns
                     else [1] * len(df_trends))

        for _, row in df_trends.iterrows():
            trend_name = row["Trend Name"]
            cluster_size = row.get("Cluster Size", 1)
            stream_count = trend_stream_count(kw_by_trend.get(trend_name, ""), keyword_index)
            z_delta = z_delta_lookup.get((stream, trend_name))

            result = compute_rank_score(cluster_size, all_sizes, stream_count, z_delta)
            rows.append({
                "Stream": stream,
                "Trend Name": trend_name,
                "Rank Score": result["score"],
                "Mode": result["mode"],
                "Z_Delta": result["z_delta"],
                "Stream_Count": result["stream_count"],
                "Cluster_Size": cluster_size,
                "Cluster_Size_Normalized": result["cluster_size_normalized"],
            })

    df_result = pd.DataFrame(rows).sort_values("Rank Score", ascending=False).reset_index(drop=True)
    if not df_result.empty:
        df_result.insert(0, "Overall Rank", range(1, len(df_result) + 1))
    return df_result


if __name__ == "__main__":
    # ทดสอบด้วยข้อมูลจริงเท่าที่มี (Paper + Social) ผสมกับข้อมูลสังเคราะห์เฉพาะส่วนที่ยังไม่มีจริง
    # (Cluster Size - ข้อมูลเก่าก่อนแก้ข้อ 30 ไม่มีคอลัมน์นี้, Z_Delta - ยังไม่มีสายไหนยิง Google Trends)
    import sys
    from pathlib import Path
    import json

    for _p in Path(__file__).resolve().parents:
        if (_p / "common" / "bootstrap.py").exists():
            sys.path.insert(0, str(_p))
            break
    from common.bootstrap import OUTPUTS
    import pandas as pd

    # 🆕 (2026-09-11, Backlog A1) เพิ่มสาย News - 3 สาย: Paper, Social, News
    _sim = {  # ขนาดจำลอง fallback ถ้าไฟล์ผลไม่มีคอลัมน์ "Cluster Size" (ผลเก่าก่อนแก้ข้อ 30)
        "Paper": [42, 38, 25, 19, 11], "Social": [15, 12, 9, 7, 4], "News": [20, 15, 11, 8, 5],
    }
    _files = {
        "Paper": "phase1_paper_stream_result.json",
        "Social": "phase2_social_stream_result.json",
        "News": "phase2_news_stream_result.json",
    }
    trends_by_stream, kw_by_stream, n_sim = {}, {}, 0
    for name, fname in _files.items():
        fp = OUTPUTS / fname
        if not fp.exists():
            print(f"  ⏭️  ข้าม {name} - ไม่มี {fname}")
            continue
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        dt = pd.DataFrame(data["trends"])
        if "Cluster Size" not in dt.columns or dt["Cluster Size"].isna().all():
            dt["Cluster Size"] = _sim[name][: len(dt)]  # จำลอง
            n_sim += 1
        trends_by_stream[name] = dt
        kw_by_stream[name] = pd.DataFrame(data["keywords"])

    print("=" * 70)
    if n_sim:
        print(f"⚠️ {n_sim}/{len(trends_by_stream)} สายใช้ Cluster Size จำลอง (ไฟล์ผลไม่มีคอลัมน์จริง) "
              "- ต้องรันสายใหม่ถึงจะได้ค่าจริง")
    else:
        print("✅ ทุกสายมี Cluster Size จริง")

    # 🆕 (2026-09-11) โหลด Z_Delta จริงจาก fetch_trends_worldwide_serpapi.py ถ้ารันแล้ว - ยกระดับจาก
    # โหมด preliminary (cluster size) เป็น final (Z_Delta) โดยอัตโนมัติ ไม่ต้องแก้โค้ดตอนมีข้อมูลจริง
    # build_trend_keyword_mapping() (ในไฟล์นั้น) ผูก trend_name เป็น key เดียวข้ามทุกสาย (ไม่แยกสาย) จึง
    # map ชื่อเทรนด์ -> Z_Delta ตัวเดียวใช้ได้กับทุกสายที่มีชื่อเทรนด์ตรงกันเป๊ะ
    z_delta_lookup = None
    z_delta_path = OUTPUTS / "phase2_paper_social_z_delta_result.json"
    if z_delta_path.exists():
        with open(z_delta_path, encoding="utf-8") as f:
            zd_data = json.load(f)
        name_to_zdelta = {row[1]: row[6] for row in (zd_data.get("master_report") or [])}
        z_delta_lookup = {}
        for stream, dt in trends_by_stream.items():
            for trend_name in dt["Trend Name"]:
                if trend_name in name_to_zdelta:
                    z_delta_lookup[(stream, trend_name)] = name_to_zdelta[trend_name]
        n_final = len(z_delta_lookup)
        n_total = sum(len(dt) for dt in trends_by_stream.values())
        print(f"✅ พบ {z_delta_path.name} - ได้ Z_Delta จริง {n_final}/{n_total} แถว (โหมด final)")
    else:
        print(f"  ⏭️  ไม่มี {z_delta_path.name} - รันแบบ preliminary ทั้งหมด (cluster size)")
    print("=" * 70)

    # 🆕 (2026-09-12, audit M1) apply_cross_source_confirmation() ถูกเขียนไว้ตั้งแต่ Backlog ข้อ 33 แต่
    # ไม่เคยมี caller เรียกจริงเลยสักที่ - D2 ("ยืนยันข้ามสาย") เลยเป็น 0/-1 เสมอ แถบ "durable" (>=90)
    # เป็นไปไม่ได้เลยในทางปฏิบัติ - เรียกที่นี่ก่อนคำนวณ Rank Score (ต้องมี Cluster Size ครบทุกสายก่อน)
    trends_by_stream = apply_cross_source_confirmation(trends_by_stream, kw_by_stream)

    df_result = rank_trends_across_streams(
        trends_by_stream, kw_by_stream,
        z_delta_lookup=z_delta_lookup,
    )
    print(df_result.to_string(index=False))
    print()
    print("จุดที่ยืนยันด้วยข้อมูลจริง: Stream_Count > 1 หมายถึงคีย์เวิร์ดของเทรนด์นี้เจอในอีกสายจริง")
    boosted = df_result[df_result["Stream_Count"] > 1]
    if not boosted.empty:
        print(boosted[["Stream", "Trend Name", "Stream_Count"]].to_string(index=False))
    else:
        print("(ไม่มีเทรนด์ไหนได้โบนัสจำนวนสายรอบนี้ - overlap คีย์เวิร์ดจริงระหว่าง Paper/Social มีแค่ "
              "1/50 คำ ตามที่วัดไว้ก่อนหน้า และคำนั้นอาจไม่ได้อยู่ใน Rank 1 ของทั้งสองสาย)")

    # 🆕 (2026-09-12, audit M5) เดิมสคริปต์นี้พิมพ์ผลออกจอเฉยๆ ไม่เซฟไฟล์เลย - เซฟทั้ง 2 อย่าง:
    # (1) ตาราง Rank Score รวมทุกสาย (2) Longevity ที่แก้ D2 แล้วต่อสาย ให้ขั้นถัดไปอ่านได้
    # ⚠️ ขั้นถัดไป (⑪ extract_trend_highlights.py, ⑭-⑮ run_stepic_report.py) ยังไม่ได้แก้ให้อ่านไฟล์นี้
    # แทนไฟล์ stream ดิบ - เป็นงานต่อยอดที่ต้องทำแยก (ดู [[แผนแก้ Data Science Audit]])
    rank_out = OUTPUTS / "phase2_rank_score_final_mode_result.json"
    df_result.to_json(rank_out, orient="records", force_ascii=False, indent=2)
    print(f"\n💾 บันทึก Rank Score รวมแล้ว: {rank_out}")

    longevity_out = OUTPUTS / "phase2_longevity_cross_source_result.json"
    with open(longevity_out, "w", encoding="utf-8") as f:
        json.dump(
            {stream: df.to_dict(orient="records") for stream, df in trends_by_stream.items()},
            f, ensure_ascii=False, indent=2, default=str,
        )
    print(f"💾 บันทึก Longevity ที่แก้ D2 (cross-source) แล้ว: {longevity_out}")
