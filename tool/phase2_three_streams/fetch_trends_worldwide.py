# -*- coding: utf-8 -*-
"""
Phase 2 — ดึง Google Trends จริง (worldwide) ให้ Paper + Social stream ผ่าน trendspyg แทน SerpAPI

ดู Detail/05 งานที่ยังไม่ได้ทำ/Backlog และแนวทางต่อไป.md (งาน "Google Trends validation") - จุดประสงค์
คือได้ Z_Delta จริงตัวแรกของทั้งโปรเจกต์ v2 (ทุกอย่างก่อนหน้านี้เป็นโหมด preliminary ไม่มี Z_Delta จริง
เลย) ปลดล็อก Rank Score โหมด final + lead-lag testing

**ทำไมใช้ trendspyg ไม่ใช่ SerpAPI:** ทดสอบแล้ว (2026-09-09) ด้วยคีย์เวิร์ดจริงที่รู้ผลอยู่แล้ว
("niacinamide body wash") ได้ผลตรงกับที่เคยวัดด้วย SerpAPI/pytrends เกือบเป๊ะ (geo=TH 1.5% vs เอกสาร
เดิม 0.4%, worldwide 87.0% vs เอกสารเดิม 85%) - trendspyg เป็น "modern maintained alternative to the
archived pytrends" (คำอธิบายจากตัว package เอง) ฟรี 100% ไม่ต้องรอเครดิต SerpAPI/OpenRouter เลย

**เลือกทำแค่ worldwide** (ไม่ทำ geo=TH คู่ขนาน) เพราะ:
1. ตรงกับดีไซน์เดิมของ Paper stream (ใช้ locale worldwide อยู่แล้วตอนดึงข่าว เพราะ geo=TH บล็อก
   เนื้อหาสากล - ดู Google Trends และ Geo.md)
2. คีย์เวิร์ดทั้ง 94 คำเป็นภาษาอังกฤษ - รู้อยู่แล้วว่า geo=TH กับคำอังกฤษหางยาวมักข้อมูลบางมาก (เฉลี่ย
   11.7%, บางคำ 0%) ไม่ใช่เพราะคนไทยไม่สนใจ แต่เพราะค้นด้วยคำไทยต่างหาก (นั่นคือขอบเขตของ Backlog ข้อ 5
   ที่ยังไม่ได้ทำ ไม่ใช่งานนี้)
3. worldwide ให้คุณค่าที่ต้องการแน่นอน (Z_Delta จริง) โดยใช้เวลาแค่ครึ่งเดียว (~25 นาที ไม่ใช่ ~50 นาที)

ใช้ monthly_df_override ที่เพิ่งเพิ่มเข้า forecast_trend() (trend_final_v2.py) - ข้อมูลดิบมาจาก
trendspyg แต่ pipeline การพยากรณ์ที่เหลือทั้งหมด (zero-noise trim, feature engineering, 4 โมเดล +
ตัวกันโมเดลระเบิด, เลือกโมเดลด้วย Holdout RMSE, E4 data quality, master report) เหมือนเดิมทุกประการ
ไม่ได้เขียนซ้ำเลย
"""
import json
import pickle
import sys
import time
from pathlib import Path

import pandas as pd

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import OUTPUTS, PROJECT_ROOT

# 🆕 (2026-09-22) ส่วนที่ใช้จริงของ trend_final_v2.py คัดลอกตรงตัวไว้ใน main/ (common/trend_final_v2_subset.py)
from common import trend_final_v2_subset as tf2  # noqa: E402

from trendspyg import download_google_trends_interest_over_time as fetch_trend  # noqa: E402

CHECKPOINT_PATH = OUTPUTS / "trendspyg_worldwide_checkpoint.pkl"
OUTPUT_DIR = str(OUTPUTS / "trendspyg_forecast_run")


def build_trend_keyword_mapping():
    """รวม cluster_name -> [keywords] จริงจาก Paper + Social (output ของ extract_strategic_keywords)
    ทั้ง 10 คลัสเตอร์ (5+5) รวมกันในคำเรียก forecast_trend() ครั้งเดียว - ประหยัดกว่าเรียกแยก 2 รอบ
    (คีย์เวิร์ด "gentle cleanser" ซ้ำกันข้ามสายจะได้ไม่ต้อง fetch ซ้ำ)
    """
    mapping = {}
    for fname in ["phase1_paper_stream_result.json", "phase2_social_stream_result.json", "phase2_news_stream_result.json"]:
        with open(OUTPUTS / fname, encoding="utf-8") as f:
            data = json.load(f)
        for row in data["keywords"]:
            trend_name = row["Trend Name"]
            kws = [k.strip().lower() for k in str(row.get("Search_Keywords", "")).split(",") if k.strip()]
            if kws:
                mapping[trend_name] = kws
    return mapping


def load_checkpoint():
    if CHECKPOINT_PATH.exists():
        with open(CHECKPOINT_PATH, "rb") as f:
            data = pickle.load(f)
        print(f"📂 พบ checkpoint เดิม: ดึงไปแล้ว {len(data)} คีย์เวิร์ด - ทำต่อจากจุดนั้น")
        return data
    return {}


def save_checkpoint(results):
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_PATH, "wb") as f:
        pickle.dump(results, f)


def fetch_all_keywords(keywords):
    """ดึง interest_over_time จริงทีละคำ (worldwide, 5 ปี) พร้อม checkpoint กันขัดจังหวะ
    คืน dict {keyword: list[{"date", "value", "is_partial"}]}
    """
    results = load_checkpoint()
    # 🆕 FIX (2026-09-09): เจอจริงตอนรันรอบแรก - คำที่ล้มเหลว (Google บล็อก) ถูกบันทึกเป็น [] ลง
    # checkpoint ด้วย ทำให้รอบถัดไปคิดว่า "เสร็จแล้ว" (เพราะเป็น key ใน results อยู่แล้ว) เลยไม่ retry
    # ให้เลย - ต้องเช็คว่า list ว่างเปล่าด้วย ไม่ใช่แค่เช็คว่ามี key
    remaining = [k for k in keywords if k not in results or not results[k]]
    if not remaining:
        print("✅ ดึงครบทุกคำแล้วจาก checkpoint")
        return results

    print(f"กำลังดึง {len(remaining)}/{len(keywords)} คำที่เหลือ (worldwide, today 5-y)...")
    t_start = time.time()
    for i, kw in enumerate(remaining):
        try:
            points = fetch_trend(kw, geo="", timeframe="today 5-y", headless=True)
            results[kw] = points
            nonzero = sum(1 for p in points if p.get("value", 0) not in (0, None))
            print(f"  [{i + 1}/{len(remaining)}] '{kw}' -> {len(points)} จุด, "
                  f"{nonzero}/{len(points)} มีข้อมูล ({time.time() - t_start:.0f}s ผ่านไปในรอบนี้)")
        except Exception as e:
            print(f"  ⚠️ '{kw}' ล้มเหลว: {str(e)[:150]} - ข้ามไปคำถัดไป")
            results[kw] = []

        if (i + 1) % 10 == 0 or i == len(remaining) - 1:
            save_checkpoint(results)

    save_checkpoint(results)
    return results


def build_monthly_df(trend_data):
    """แปลงผล trendspyg (รายสัปดาห์) เป็น monthly_df รูปแบบเดียวกับที่ forecast_trend() ต้องการ
    (คอลัมน์ Keyword, start_date, search_avg) - เฉลี่ยรายสัปดาห์ขึ้นเป็นรายเดือนแบบเดียวกับที่โค้ดเดิม
    ทำกับ SerpAPI (.dt.to_period('M')) + ตัดจุดที่ is_partial=True ทิ้งเหมือนเดิม (กันเดือนล่าสุดทรุดปลอม)
    """
    rows = []
    for kw, points in trend_data.items():
        for p in points:
            if p.get("is_partial"):
                continue
            rows.append({"Keyword": kw, "raw_date": p["date"], "search_avg": p.get("value", 0) or 0})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["raw_date"] = pd.to_datetime(df["raw_date"])
    df["start_date"] = df["raw_date"].dt.to_period("M").dt.to_timestamp()
    monthly_df = df.groupby(["Keyword", "start_date"], as_index=False).agg(search_avg=("search_avg", "mean"))
    return monthly_df


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 2 — Google Trends จริง (worldwide) ให้ Paper + Social ผ่าน trendspyg")
    print("=" * 70)

    trend_keyword_mapping = build_trend_keyword_mapping()
    all_keywords = sorted(set(k for kws in trend_keyword_mapping.values() for k in kws))
    print(f"รวม {len(trend_keyword_mapping)} คลัสเตอร์จริง (Paper 5 + Social 5), "
          f"{len(all_keywords)} คีย์เวิร์ดไม่ซ้ำ")

    trend_data = fetch_all_keywords(all_keywords)
    monthly_df = build_monthly_df(trend_data)
    print(f"\nสร้าง monthly_df แล้ว: {len(monthly_df)} แถว (คีย์เวิร์ด x เดือน)")

    if monthly_df.empty:
        print("❌ ไม่มีข้อมูลเลย - หยุด")
        sys.exit(1)

    print("\nกำลังรัน forecast_trend() เต็มรูปแบบ (feature engineering + 4 โมเดล + ตัวกันโมเดลระเบิด + "
          "E4 data quality) ด้วยข้อมูลจริงจาก trendspyg...")
    cluster_names, df_results, master_report, llm_analysis = tf2.forecast_trend(
        OUTPUT_DIR, trend_keyword_mapping, "Trend Body Wash Thailand 2030 (worldwide, Paper+Social)",
        monthly_df_override=monthly_df,
    )

    OUTPUTS.mkdir(exist_ok=True)
    result_path = OUTPUTS / "phase2_paper_social_z_delta_result.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump({
            "_note": "Z_Delta จริงตัวแรกของโปรเจกต์ v2 (worldwide, ผ่าน trendspyg) - ดู Backlog",
            "master_report": master_report,
        }, f, ensure_ascii=False, indent=2, default=str)

    print("\n" + "=" * 70)
    print("ผลลัพธ์ (เรียงตาม Z_Delta มากไปน้อย):")
    print("=" * 70)
    cols = ["cluster_id", "Cluster", "Model", "Status", "Current_Z", "Forecast_Avg_Z", "Z_Delta",
            "Peak_Month", "Keywords", "Context", "Data_Quality", "Pct_Months_With_Data"]
    for row in master_report:
        d = dict(zip(cols, row))
        print(f"\n🎯 {d['Cluster']} (id={d['cluster_id']})")
        print(f"   Status={d['Status']} | Z_Delta={d['Z_Delta']} | Model={d['Model']}")
        print(f"   Data_Quality={d['Data_Quality']} ({d['Pct_Months_With_Data']}% เดือนมีข้อมูลจริง)")

    print(f"\nบันทึกผลเต็มลง {result_path}")
