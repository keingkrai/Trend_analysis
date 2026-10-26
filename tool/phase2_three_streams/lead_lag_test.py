# -*- coding: utf-8 -*-
"""
Phase 2 — Lead-lag testing: สาย Paper นำสาย Social กี่เดือน (หรือย้อนกลับ)?

ดู Detail/05 งานที่ยังไม่ได้ทำ/Workflow v2 — แยกสายแล้วรวม.md คำถามค้างข้อ 3 (ข้อสุดท้ายที่เหลือ):
"สมมติฐาน Paper → Social → ข่าว ถ้าพิสูจน์ได้ว่าหมวดหนึ่งขึ้นก่อนอีกหมวดเฉลี่ย N เดือน นั่นคือความได้เปรียบ
ที่ pipeline ปัจจุบันให้ไม่ได้เลย"

**ไม่ยิง API ใหม่เลย** - ใช้ monthly time series จริงที่ SerpAPI ดึงมาแล้ว (ดู Backlog ข้อ 35.2,
step5a_monthly_trends.xlsx) ทดสอบด้วย cross-correlation แบบเดียวกับที่เสนอไว้ ("ทดสอบได้ด้วยข้อมูลที่มี
อยู่แล้วแบบเดียวกับ walk-forward validation")

## ทำไมเทียบแค่ 1 คู่คลัสเตอร์ ไม่ใช่ทั้งสาย

"Evidence-Based Barrier-Friendly Cleansing" (Paper) กับ "Gentle Barrier-Friendly Cleansing" (Social)
เป็นคู่เดียวที่ **พิสูจน์แล้วว่าเป็นธีมเดียวกันจริง** (คีย์เวิร์ด "gentle cleanser" เจอข้ามสายจริง - ดู
Backlog ข้อ 30/33) - เทียบทั้งสายทั้งก้อน (เฉลี่ยรวมทุกคลัสเตอร์ที่ไม่เกี่ยวข้องกันเลย) จะได้ค่า
correlation ที่ตีความไม่ได้จริง (ปนสัญญาณจากหลายเรื่องที่ไม่เกี่ยวกัน) - คู่นี้เป็นคู่เดียวที่ตีความแบบ
"ธีมเดียวกัน ใครขึ้นก่อน" ได้อย่างมีความหมายจริง

## Methodology

1. z-score แบบ rolling 12 เดือนต่อคีย์เวิร์ด (สูตรเดียวกับ get_rolling_z_score ใน forecast_trend())
2. เฉลี่ย z-score ข้ามคีย์เวิร์ดในคลัสเตอร์เดียวกัน -> ได้อนุกรมเวลาระดับคลัสเตอร์ 2 เส้น
3. จำกัดช่วงเวลาแค่ 5 ปีล่าสุด (ตรงกับ timeframe="today 5-y" ที่ใช้ทั่วทั้งโปรเจกต์) กันข้อมูลเก่าปี 2004
   ที่แทบเป็น 0 ทั้งหมดมาปนสัญญาณ
4. cross-correlation ที่ lag -12 ถึง +12 เดือน หา lag ที่ correlation สูงสุด
   - lag บวก = Paper "นำ" (ขยับ Paper ไปข้างหน้า N เดือนแล้ว correlate กับ Social ปัจจุบันได้ดีที่สุด)
   - lag ลบ = Social "นำ"
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import OUTPUTS

MONTHLY_PATH = OUTPUTS / "serpapi_forecast_run" / "step5a_monthly_trends.xlsx"
YEARS_BACK = 5
MAX_LAG_MONTHS = 12

PAPER_CLUSTER = "Evidence-Based Barrier-Friendly Cleansing"
SOCIAL_CLUSTER = "Gentle Barrier-Friendly Cleansing"


def get_rolling_z_score(x):
    """สูตรเดียวกับ trend_final_v2.py's forecast_trend() เป๊ะ - 12 เดือน rolling z-score"""
    return ((x - x.rolling(window=12, min_periods=4).mean()) / x.rolling(window=12, min_periods=4).std(ddof=1)) \
        .replace([np.inf, -np.inf], 0).fillna(0)


def get_cluster_keywords(cluster_name):
    for fname in ["phase1_paper_stream_result.json", "phase2_social_stream_result.json", "phase2_news_stream_result.json"]:
        with open(OUTPUTS / fname, encoding="utf-8") as f:
            data = json.load(f)
        for row in data["keywords"]:
            if row["Trend Name"] == cluster_name:
                return [k.strip().lower() for k in str(row.get("Search_Keywords", "")).split(",") if k.strip()]
    raise ValueError(f"ไม่เจอคลัสเตอร์ '{cluster_name}' ในผลจริงทั้ง 2 สาย")


def build_cluster_series(monthly_df, keywords, cutoff_date):
    """คืน pd.Series (index=เดือน) ของ z-score เฉลี่ยข้ามคีย์เวิร์ดในคลัสเตอร์นี้"""
    sub = monthly_df[monthly_df["Keyword"].isin(keywords)].copy()
    found_kws = sub["Keyword"].unique()
    print(f"    เจอคีย์เวิร์ดจริงใน monthly data: {len(found_kws)}/{len(keywords)} ({list(found_kws)})")

    pivot = sub.pivot_table(index="start_date", columns="Keyword", values="search_avg", aggfunc="mean").sort_index()
    z_scored = pivot.apply(get_rolling_z_score, axis=0)
    cluster_series = z_scored.mean(axis=1)
    return cluster_series[cluster_series.index >= cutoff_date]


if __name__ == "__main__":
    print("=" * 70)
    print(f"Lead-lag test: '{PAPER_CLUSTER}' (Paper) vs '{SOCIAL_CLUSTER}' (Social)")
    print("=" * 70)

    monthly_df = pd.read_excel(MONTHLY_PATH)
    cutoff = monthly_df["start_date"].max() - pd.DateOffset(years=YEARS_BACK)
    print(f"ช่วงเวลาที่ใช้: {cutoff.date()} ถึง {monthly_df['start_date'].max().date()} ({YEARS_BACK} ปีล่าสุด)\n")

    print(f"[Paper] '{PAPER_CLUSTER}'")
    paper_kws = get_cluster_keywords(PAPER_CLUSTER)
    paper_series = build_cluster_series(monthly_df, paper_kws, cutoff)

    print(f"\n[Social] '{SOCIAL_CLUSTER}'")
    social_kws = get_cluster_keywords(SOCIAL_CLUSTER)
    social_series = build_cluster_series(monthly_df, social_kws, cutoff)

    df_aligned = pd.DataFrame({"paper": paper_series, "social": social_series}).dropna()
    print(f"\nจำนวนเดือนที่ทั้งคู่มีข้อมูลพร้อมกัน: {len(df_aligned)}")

    if len(df_aligned) < 12:
        print("❌ ข้อมูลซ้อนกันน้อยเกินไป (<12 เดือน) - ผลจะไม่น่าเชื่อถือ หยุดที่นี่")
        sys.exit(1)

    print("\nกำลังคำนวณ cross-correlation ที่ lag -12 ถึง +12 เดือน...")
    results = []
    for lag in range(-MAX_LAG_MONTHS, MAX_LAG_MONTHS + 1):
        if lag >= 0:
            # lag บวก: paper ขยับไปข้างหน้า lag เดือน เทียบกับ social ปัจจุบัน (paper นำ)
            shifted_paper = df_aligned["paper"].shift(lag)
            corr = shifted_paper.corr(df_aligned["social"])
        else:
            shifted_social = df_aligned["social"].shift(-lag)
            corr = df_aligned["paper"].corr(shifted_social)
        n_overlap = df_aligned["paper"].shift(lag if lag >= 0 else 0).notna().sum() if lag >= 0 else \
            df_aligned["social"].shift(-lag).notna().sum()
        results.append({"lag_months": lag, "correlation": round(corr, 4) if pd.notna(corr) else None})

    df_results = pd.DataFrame(results)
    print(df_results.to_string(index=False))

    valid = df_results.dropna(subset=["correlation"])
    best = valid.loc[valid["correlation"].abs().idxmax()]
    best_lag = int(best["lag_months"])
    best_corr = float(best["correlation"])
    lag0 = float(df_results[df_results["lag_months"] == 0]["correlation"].iloc[0])

    # 🆕 (2026-09-12, audit m5) เดิม claim "Paper นำ/Social นำ" ทันทีที่ lag ที่ดีที่สุด != 0 โดยไม่เช็คว่า
    # curve สมมาตรรอบ lag=0 หรือเปล่า - cross-correlation ของ 2 อนุกรมที่ "เคลื่อนไหวพร้อมกัน" (co-trending,
    # ไม่มีใครนำใคร) ก็ให้ curve สมมาตรแบบนี้ได้เหมือนกัน (corr(+k) ≈ corr(-k) ≈ corr(0)) ต้องเช็คว่า best_lag
    # ทำได้ดีกว่า "คู่กระจก" (lag ตรงข้ามเครื่องหมาย) และดีกว่า lag=0 อย่างมีนัยสำคัญจริง ก่อนจะกล้าอ้างทิศทาง
    mirror_row = df_results[df_results["lag_months"] == -best_lag]
    mirror_corr = float(mirror_row["correlation"].iloc[0]) \
        if not mirror_row.empty and pd.notna(mirror_row["correlation"].iloc[0]) else None
    SYMMETRY_MARGIN = 0.05  # ห่างกันน้อยกว่านี้ = ถือว่าแยกไม่ออกจาก noise ไม่ใช่โครงสร้างทิศทางจริง
    is_symmetric = (
        best_lag == 0
        or abs(best_corr - lag0) < SYMMETRY_MARGIN
        or (mirror_corr is not None and abs(best_corr - mirror_corr) < SYMMETRY_MARGIN)
    )

    print("\n" + "=" * 70)
    print(f"Lag ที่ |correlation| สูงสุด: {best_lag} เดือน (correlation={best_corr})")
    print(f"Correlation ที่ lag=0 (เคลื่อนไหวพร้อมกัน): {lag0}")
    if mirror_corr is not None:
        print(f"Correlation ที่ lag ตรงข้ามเครื่องหมาย ({-best_lag}): {mirror_corr}")

    if is_symmetric:
        interpretation = (
            "co_trending_no_clear_direction",
            "-> Curve สมมาตรรอบ lag=0 (best_lag กับ lag=0/lag ตรงข้ามต่างกัน < "
            f"{SYMMETRY_MARGIN}) - นี่คือลักษณะของ \"เคลื่อนไหวพร้อมกัน\" (co-trending) ไม่ใช่หลักฐานว่า "
            "Paper หรือ Social 'นำ' อีกฝ่าย ห้ามสรุปทิศทางจากผลนี้",
        )
    elif best_lag > 0:
        interpretation = (
            "paper_leads",
            f"-> Paper 'นำ' Social อยู่ {best_lag} เดือน (ตรงกับสมมติฐาน Paper -> Social, ต่างจาก "
            f"lag=0 และ lag ตรงข้ามชัดเจนพอที่จะไม่ใช่แค่ noise)",
        )
    else:
        interpretation = (
            "social_leads",
            f"-> Social 'นำ' Paper อยู่ {abs(best_lag)} เดือน (ตรงข้ามสมมติฐาน, ต่างจาก lag=0 และ lag "
            f"ตรงข้ามชัดเจนพอที่จะไม่ใช่แค่ noise)",
        )
    print(interpretation[1])

    out_path = OUTPUTS / "phase2_lead_lag_test_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "_note": "Lead-lag test แรกของโปรเจกต์ (ข้อมูลจริง SerpAPI, ไม่ใช่ synthetic) - ดู Backlog",
            "paper_cluster": PAPER_CLUSTER, "social_cluster": SOCIAL_CLUSTER,
            "n_overlapping_months": len(df_aligned), "years_back": YEARS_BACK,
            "results_by_lag": results, "best_lag_months": best_lag,
            "best_correlation": best_corr, "lag0_correlation": lag0, "mirror_lag_correlation": mirror_corr,
            "is_symmetric_co_trending": is_symmetric, "verdict": interpretation[0],
        }, f, ensure_ascii=False, indent=2)
    print(f"\nบันทึกผลเต็มลง {out_path}")
