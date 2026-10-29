# -*- coding: utf-8 -*-
"""
Phase 2 — Rank Score: จัดอันดับเทรนด์ด้วยตัวเลขเดียว

ตอบคำถาม "ทำไมเทรนด์นี้เป็นอันดับ 1" ด้วยตัวเลขที่อธิบายได้ (ไม่ใช่แค่ลำดับที่ Louvain/LLM จัดมาให้
โดยบังเอิญ) — ดู Detail/05 งานที่ยังไม่ได้ทำ/Backlog และแนวทางต่อไป.md ข้อ 30

🆕 (2026-09-30) เปลี่ยนเกณฑ์หลักจาก Z_Delta เป็นคะแนนการเติบโตของการค้นหาปีที่ 1 (growth_score.py) - backtest
พบว่าอันดับ Z_Delta สวนทางกับการโตจริงในปีถัดไป (Spearman −0.20) ส่วนคะแนนการเติบโต (ผสม momentum กับโมเดล
พยากรณ์การเติบโต) ได้ +0.49 ดูที่มาใน growth_score.py

    โหมด final:        Rank Score = คะแนนการเติบโตปีที่ RANK_YEAR (0-1, 0.5 = ค่ากลางตลาด) ไม่มีโบนัสจำนวนสาย
                       🆕 (2026-10-02) ปีที่ 2 แทนปีที่ 1 - เจ้าของงานกำหนดระยะสั้น = 2 ปี (ระยะยาว = ปีที่ 5)
                       🆕 (2026-10-19) ปีที่ 3 (ระยะสั้น = 3 ปี) - ค่าอยู่ที่ common/horizons.py · rerank_rows() / --rerank จัดอันดับใหม่จากไฟล์ผลเดิม
    โหมด preliminary:  Rank Score = ขนาดคลัสเตอร์ normalize × (1 + 0.2 × (จำนวนสาย - 1)) (ไม่มีข้อมูล Google Trends)

ทำไมตัดโบนัสจำนวนสายออกจากโหมด final: รายงานขีดเส้นแบ่งที่ค่ากลางตลาด (0.5) และทำหน้ารายละเอียดเฉพาะเทรนด์เหนือเส้น
ถ้าคูณโบนัสเข้าไป เทรนด์ที่โตช้ากว่าตลาดแต่เจอ 2 สายจะได้อันดับเหนือเทรนด์ที่โตเร็วกว่าตลาด ลำดับกับเส้นแบ่งจะขัดกัน
จำนวนสาย (Stream_Count) ยังเก็บไว้แสดงในรายงานและใช้ตัดสินกรณีคะแนนเท่ากัน

เนื้อหาด้านล่างเป็นคำอธิบายรุ่นเดิม (Z_Delta) เก็บไว้เป็นประวัติ - ตัวเลขที่ใช้จริงดูตามย่อหน้าบน

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


def compute_rank_score(cluster_size, all_cluster_sizes_same_stream, stream_count, growth=None):
    """คำนวณ Rank Score เดียว - ดูสูตรเต็มใน docstring บนสุดของไฟล์

    growth = คะแนนการเติบโตปีที่ 1 ของเทรนด์ (growth_score.py, 0-1) หรือ None ถ้ายังไม่มีข้อมูล Google Trends

    Returns:
        dict {score, mode, growth, stream_count, cluster_size_normalized}
    """
    normalized_size = normalize_cluster_size(cluster_size, all_cluster_sizes_same_stream)
    if growth is not None:
        # 🆕 (2026-09-30) ใช้คะแนนการเติบโตตรงๆ ไม่คูณโบนัสจำนวนสาย (เหตุผลใน docstring บนสุดของไฟล์)
        score = growth
        mode = "final (growth)"
    else:
        stream_bonus = 1 + 0.2 * (stream_count - 1)
        score = normalized_size * stream_bonus
        mode = "preliminary (cluster size - ยังไม่มีคะแนนการเติบโตจริง)"

    return {
        "score": round(float(score), 4),
        "mode": mode,
        "growth": growth,
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


# 🆕 (2026-10-02) ปีของคะแนนการเติบโตที่บันทึก (ต้องตรงกับ growth_score.HORIZONS) และปีที่ใช้จัดอันดับหลัก
# (= ระยะสั้นของรายงาน) · 🆕 (2026-10-19) อ่านจาก common/horizons.py ที่เดียว (เดิมเขียน 2 ตรงนี้แล้ว "ให้ตรงกับ" โมดูลอื่นด้วยคอมเมนต์)
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_TOOL_DIR = str(_Path(__file__).resolve().parents[1])
if _TOOL_DIR not in _sys.path:
    _sys.path.insert(0, _TOOL_DIR)
from common.horizons import SHORT_YEAR as RANK_YEAR, YEARS as GROWTH_YEARS  # noqa: E402


def rank_trends_across_streams(df_trends_by_stream, df_keywords_by_stream, growth_lookup=None):
    """ฟังก์ชันหลัก - รับผลลัพธ์ทุกสาย คืนตาราง Rank Score รวมทุกเทรนด์ทุกสายเรียงจากมากไปน้อย

    Args:
        df_trends_by_stream: dict {stream_name: df_trends} (output จาก summarize_trend_clusters
            ต้องมีคอลัมน์ "Cluster Size" - ดู Backlog ข้อ 30)
        df_keywords_by_stream: dict {stream_name: df_keywords} (output จาก extract_strategic_keywords)
        growth_lookup: dict {(stream_name, trend_name): แถวเทรนด์จาก growth_score.compute_growth_scores()
            ["clusters"]} หรือ None ถ้ายังไม่มีข้อมูล Google Trends (โหมด preliminary ทั้งหมด)

    Returns:
        DataFrame เรียงโหมด final ก่อน แล้วตาม Rank Score มากไปน้อย (เท่ากันใช้จำนวนสายตัดสิน) คอลัมน์:
        Stream, Trend Name, Rank Score, Mode, Growth_Y1..Y5, Grade_Y1..Y5, Past_Growth_Pct,
        Recent_Change_Pct, Recent_Decline, Stream_Count, Cluster_Size, Cluster_Size_Normalized
        (🆕 2026-09-30 ไม่มีคอลัมน์ Z_Delta แล้ว - เจ้าของงานให้เอาออกจากทุกส่วนที่คนเห็น)
    """
    import pandas as pd

    keyword_index = build_keyword_stream_index(df_keywords_by_stream)
    growth_lookup = growth_lookup or {}

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
            g = growth_lookup.get((stream, trend_name)) or {}

            result = compute_rank_score(cluster_size, all_sizes, stream_count, g.get(f"score_y{RANK_YEAR}"))
            rows.append({
                "Stream": stream,
                "Trend Name": trend_name,
                "Rank Score": result["score"],
                "Mode": result["mode"],
                **{f"Growth_Y{h}": g.get(f"score_y{h}") for h in GROWTH_YEARS},
                **{f"Grade_Y{h}": g.get(f"grade_y{h}") for h in GROWTH_YEARS},
                "Past_Growth_Pct": g.get("past_growth_pct"),
                "Recent_Change_Pct": g.get("recent_change_pct"),
                "Recent_Decline": g.get("recent_decline"),
                "Stream_Count": result["stream_count"],
                "Cluster_Size": cluster_size,
                "Cluster_Size_Normalized": result["cluster_size_normalized"],
            })

    df_result = pd.DataFrame(rows)
    if df_result.empty:
        return df_result
    # โหมด final ก่อนเสมอ (คะแนนโหมด preliminary คนละสเกล เทียบกันตรงๆ ไม่ได้) แล้วตามคะแนน เท่ากันใช้จำนวนสาย
    df_result["_final"] = df_result["Mode"].str.startswith("final")
    df_result = (df_result.sort_values(["_final", "Rank Score", "Stream_Count", "Trend Name"],
                                       ascending=[False, False, False, True])
                 .drop(columns="_final").reset_index(drop=True))
    df_result.insert(0, "Overall Rank", range(1, len(df_result) + 1))
    return df_result


def rerank_rows(rows, year=RANK_YEAR):
    """🆕 (2026-10-19) จัดอันดับใหม่จากแถวของไฟล์ผลที่บันทึกไว้แล้ว (list ของ dict - phase2_rank_score_final_mode_result.json) ด้วยคะแนนปีที่ `year`
    โดยไม่ฝึกโมเดลพยากรณ์ซ้ำ - ใช้เมื่อเจ้าของงานเปลี่ยนปีระยะสั้น (common/horizons.py) กับรอบที่รันไปแล้ว: ไฟล์เก็บ Growth_Y1..Y5 ครบอยู่แล้ว
    และโหมด final คือ Rank Score = Growth_Y{year} ปัด 4 ตำแหน่ง (compute_rank_score) จึงคิดซ้ำได้เหมือนรัน ⑥ ใหม่ทุกประการ
    (เทสต์เทียบกับไฟล์จริงด้วย year เดิม) · แถวโหมด preliminary คงคะแนนเดิม · เรียงด้วยกฎเดียวกับ rank_trends_across_streams:
    final ก่อน -> Rank Score มากไปน้อย -> Stream_Count มากไปน้อย -> ชื่อเทรนด์ · คืนสำเนาใหม่ ไม่แก้ rows เดิม"""
    def is_final(r):
        return str(r.get("Mode") or "").startswith("final")

    out = []
    for r in rows:
        r = dict(r)
        growth = r.get(f"Growth_Y{year}")
        if is_final(r) and growth is not None:
            r["Rank Score"] = round(float(growth), 4)
        out.append(r)
    out.sort(key=lambda r: (not is_final(r), -(r.get("Rank Score") or 0), -(r.get("Stream_Count") or 0), r.get("Trend Name") or ""))
    for i, r in enumerate(out, 1):
        r["Overall Rank"] = i
    return out


def _note_rerank_in_manifest(path):
    """ไฟล์ผลเปลี่ยนหลัง ⑥ เขียนไว้ -> ขั้นถัดไปจะเตือน "hash ไม่ตรง" ทุกครั้ง: อัปเดต hash ของ ⑥ ใน _manifest.json ของรอบ + จดว่าจัดใหม่ด้วยปีไหน
    (ไม่มี manifest / ไม่มีรายการ rank_trends = ไม่ทำอะไร)"""
    import hashlib
    import json as _json
    from datetime import datetime

    manifest = path.parent / "_manifest.json"
    if not manifest.exists():
        return
    data = _json.loads(manifest.read_text(encoding="utf-8"))
    entry = data.get("rank_trends")
    if not isinstance(entry, dict):
        return
    entry.setdefault("output_hashes", {})[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    entry["reranked"] = {"year": RANK_YEAR, "timestamp": datetime.now().isoformat(timespec="seconds")}
    manifest.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _rerank_file_cli(path):
    """python rank_trends.py --rerank <phase2_rank_score_final_mode_result.json> - เขียนทับไฟล์ (สำรองก่อนเอง) แล้วพิมพ์ว่าอันดับไหนขยับ"""
    import json as _json
    import pandas as pd

    path = _Path(path)
    rows = _json.loads(path.read_text(encoding="utf-8"))
    before = {(r["Stream"], r["Trend Name"]): r["Overall Rank"] for r in rows}
    new_rows = rerank_rows(rows)
    pd.DataFrame(new_rows).to_json(path, orient="records", force_ascii=False, indent=2)
    moved = [(r["Overall Rank"], before[(r["Stream"], r["Trend Name"])], r["Trend Name"]) for r in new_rows
             if before[(r["Stream"], r["Trend Name"])] != r["Overall Rank"]]
    _note_rerank_in_manifest(path)
    print(f"✅ จัดอันดับใหม่ด้วยคะแนนปีที่ {RANK_YEAR}: {len(new_rows)} เทรนด์ -> {path}")
    print(f"   อันดับขยับ {len(moved)} เทรนด์" + ("" if not moved else ": " + ", ".join(f"{b}->{a} {n}" for a, b, n in moved)))


if __name__ == "__main__":
    if "--rerank" in _sys.argv:
        _rerank_file_cli(_sys.argv[_sys.argv.index("--rerank") + 1])
        _sys.exit(0)

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
    # 🆕 (2026-10-27) รายชื่อสายที่เดียว (common/streams.py) - อ่านเฉพาะสายที่รอบนี้มีไฟล์ผล (รอบใหม่ = Search อย่างเดียว)
    from common.streams import present_streams
    trends_by_stream, kw_by_stream, n_sim = {}, {}, 0
    for name, fp in present_streams(OUTPUTS).items():
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        dt = pd.DataFrame(data["trends"])
        if "Cluster Size" not in dt.columns or dt["Cluster Size"].isna().all():
            dt["Cluster Size"] = _sim.get(name, [10] * len(dt))[: len(dt)]  # จำลอง
            n_sim += 1
        trends_by_stream[name] = dt
        kw_by_stream[name] = pd.DataFrame(data["keywords"])

    print("=" * 70)
    if n_sim:
        print(f"⚠️ {n_sim}/{len(trends_by_stream)} สายใช้ Cluster Size จำลอง (ไฟล์ผลไม่มีคอลัมน์จริง) "
              "- ต้องรันสายใหม่ถึงจะได้ค่าจริง")
    else:
        print("✅ ทุกสายมี Cluster Size จริง")

    # 🆕 (2026-09-30) คะแนนการเติบโต (growth_score.py) จากค่าการค้นหารายเดือนของ ⑦ - ใช้จัดอันดับแทน Z_Delta
    # (Z_Delta ไม่ถูกอ่าน/บันทึกในขั้นนี้แล้ว) ชื่อคลัสเตอร์ของ ⑦ = ชื่อเทรนด์ (ไม่ซ้ำข้ามสาย) จึงผูกกับ
    # (สาย, ชื่อเทรนด์) ด้วยชื่ออย่างเดียวได้
    from growth_score import FORECAST_DIR_NAME, MONTHLY_FILE, compute_growth_scores, save_growth_scores
    growth_lookup = None
    forecast_dir = OUTPUTS / FORECAST_DIR_NAME
    n_total = sum(len(dt) for dt in trends_by_stream.values())
    if (forecast_dir / MONTHLY_FILE).exists():
        growth = compute_growth_scores(forecast_dir)
        growth_path = save_growth_scores(growth, OUTPUTS)
        by_name = {c["trend"]: c for c in growth["clusters"] if c.get(f"score_y{RANK_YEAR}") is not None}
        growth_lookup = {(stream, name): by_name[name]
                         for stream, dt in trends_by_stream.items() for name in dt["Trend Name"] if name in by_name}
        _m = growth["method"].get("model") or {}
        print(f"✅ คะแนนการเติบโต ณ {growth['as_of']} (โมเดล {_m.get('mode', '?')}, ฝึกด้วยข้อมูลถึง "
              f"{growth['method']['last_trusted_month']}, ตัวอย่างฝึก {growth['method']['n_train']}) - "
              f"ได้ {len(growth_lookup)}/{n_total} เทรนด์ (โหมด final)")
        if _m.get("mode") == "pool":
            print(f"   ชุดกลาง {_m['pool_keywords']} คำ (สร้าง {_m['pool_built']}) · คำของรอบนี้ที่อยู่ในชุดกลาง "
                  f"{_m['run_keywords_in_pool']}/{_m['run_keywords']} · แถบ 80%: {_m['band_source']}")
        print(f"💾 บันทึกคะแนนการเติบโต: {growth_path}")
    else:
        print(f"  ⏭️  ไม่มี {FORECAST_DIR_NAME}/{MONTHLY_FILE} (ยังไม่ได้รัน ⑦) - รันแบบ preliminary ทั้งหมด (cluster size)")
    print("=" * 70)

    # 🆕 (2026-09-12, audit M1) apply_cross_source_confirmation() ถูกเขียนไว้ตั้งแต่ Backlog ข้อ 33 แต่
    # ไม่เคยมี caller เรียกจริงเลยสักที่ - D2 ("ยืนยันข้ามสาย") เลยเป็น 0/-1 เสมอ แถบ "durable" (>=90)
    # เป็นไปไม่ได้เลยในทางปฏิบัติ - เรียกที่นี่ก่อนคำนวณ Rank Score (ต้องมี Cluster Size ครบทุกสายก่อน)
    trends_by_stream = apply_cross_source_confirmation(trends_by_stream, kw_by_stream)

    df_result = rank_trends_across_streams(
        trends_by_stream, kw_by_stream,
        growth_lookup=growth_lookup,
    )
    print(df_result[["Overall Rank", "Stream", "Trend Name", "Rank Score",
                     *dict.fromkeys(["Growth_Y1", f"Growth_Y{RANK_YEAR}", "Growth_Y5"]),
                     "Past_Growth_Pct", "Recent_Decline", "Stream_Count"]].to_string(index=False))
    print()
    print("Stream_Count > 1 = คีย์เวิร์ดของเทรนด์นี้เจอในอีกสายจริง (ใช้ตัดสินกรณีคะแนนเท่ากัน ไม่เป็นโบนัสแล้ว)")
    confirmed = df_result[df_result["Stream_Count"] > 1]
    if not confirmed.empty:
        print(confirmed[["Stream", "Trend Name", "Stream_Count"]].to_string(index=False))
    else:
        print("(ไม่มีเทรนด์ไหนเจอคีย์เวิร์ดซ้ำข้ามสายรอบนี้)")

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
