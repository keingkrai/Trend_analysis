# -*- coding: utf-8 -*-
"""
Phase 2 — เชื่อม ⑧ ชั้น 3-4 (aggregate_forecast.py) กับข้อมูลจริงครั้งแรก (2026-09-11)
ดู Detail/05 งานที่ยังไม่ได้ทำ/Workflow v2 — แยกสายแล้วรวม.md ส่วน "⑧ พยากรณ์ไล่ขึ้นเป็นชั้นๆ"

ปัญหาที่ต้องแก้ก่อน: `fetch_trends_worldwide_serpapi.py`'s `build_trend_keyword_mapping()` รวม
คีย์เวิร์ดจาก 3 สายเป็น dict เดียว (key = trend_name, ไม่ติด tag สาย) ก่อนยิง SerpAPI ครั้งเดียว -
`master_report` ที่ได้ (บันทึกใน phase2_paper_social_z_delta_result.json) จึงเป็น "14 คลัสเตอร์รวม"
ไม่ใช่ per-stream แบบที่ aggregate_to_category_level() ต้องการ (dict {stream: master_report_df})

ทางแก้ **ไม่ยิง SerpAPI ซ้ำ** (ประหยัด quota) — ใช้ผลที่มีอยู่แล้ว + สร้าง "การ์ดผูกกลับ" ว่าแต่ละแถวใน
master_report มาจากสายไหนบ้าง โดยเทียบ "Trend Name" กับ trends ของแต่ละสายตรงๆ (ชุดตัวตนเดียวกับที่
rank_trends.py ใช้ทำ Stream_Count) — เทรนด์ที่ยืนยันข้ามสายจริง (เช่น "Barrier Repair Skincare" ที่เจอ
ทั้ง Paper และ News) จะถูกนับเป็นหลักฐานของ**ทั้งสองสาย** สอดคล้องกับที่ rank_trends.py ทำอยู่แล้ว
(Stream_Count>1 แสดงเป็นแถวแยกของแต่ละสายเหมือนกัน ไม่ dedupe ทิ้ง)
"""
import json
import sys
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import OUTPUTS  # noqa: E402

import pandas as pd  # noqa: E402

from aggregate_forecast import aggregate_to_category_level, aggregate_to_overall_level  # noqa: E402

STREAM_FILES = {
    "Paper": "phase1_paper_stream_result.json",
    "Social": "phase2_social_stream_result.json",
    "News": "phase2_news_stream_result.json",
}

# คอลัมน์ตรงลำดับเป๊ะกับ generate_master_trend_report() ใน trend_final_v2.py (ดูที่มาใน
# fetch_trends_worldwide_serpapi.py's __main__ - master_report เป็น list of list ไม่ใช่ DataFrame)
MASTER_REPORT_COLS = ["cluster_id", "Cluster", "Model", "Status", "Current_Z", "Forecast_Avg_Z",
                      "Z_Delta", "Peak_Month", "Keywords", "Context", "Data_Quality",
                      "Pct_Months_With_Data"]


def build_trend_stream_attribution():
    """{trend_name: set(stream_name)} จาก "Trend Name" จริงในผลลัพธ์ทั้ง 3 สาย - ตัวตนเดียวกับที่
    rank_trends.py ใช้นับ Stream_Count และที่ fetch_trends_worldwide_serpapi.py ใช้เป็น key ตอนรวม
    คีย์เวิร์ด (ดังนั้นชื่อที่ตรงกันเป๊ะข้ามสาย = ยืนยันข้ามสายจริงแบบเดียวกันทั้งระบบ ไม่ใช่นิยามใหม่)"""
    attribution = {}
    missing = []
    for stream, fname in STREAM_FILES.items():
        fp = OUTPUTS / fname
        if not fp.exists():
            missing.append(stream)
            continue
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        for row in data.get("trends", []):
            name = row.get("Trend Name")
            if name:
                attribution.setdefault(name, set()).add(stream)
    if missing:
        print(f"  ⚠️ ไม่มีผลลัพธ์ของสาย: {', '.join(missing)} - จะไม่มีในชั้นหมวด")
    return attribution


def split_master_report_by_stream(master_report, attribution):
    """1 master_report รวม (จาก SerpAPI ครั้งเดียว) -> dict {stream: master_report_df} ตาม
    attribution ด้านบน - เทรนด์ที่ attribution ไม่เจอเลย (ชื่อไม่ตรงกับสายไหนเป๊ะ - ไม่ควรเกิดเพราะ
    build_trend_keyword_mapping() ใช้ trend_name ชุดเดียวกันเป๊ะเป็น key) จะถูกรายงานแยกไว้เฉยๆ"""
    df = pd.DataFrame(master_report, columns=MASTER_REPORT_COLS)
    by_stream_rows = {}
    unmatched = []
    for _, row in df.iterrows():
        streams = attribution.get(row["Cluster"])
        if not streams:
            unmatched.append(row["Cluster"])
            continue
        for s in streams:
            by_stream_rows.setdefault(s, []).append(row)
    by_stream_df = {s: pd.DataFrame(rows) for s, rows in by_stream_rows.items()}
    return by_stream_df, unmatched


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 2 ⑧ — เชื่อมชั้น 3-4 (ต่อหมวด + ภาพรวม) กับ Z_Delta จริง")
    print("=" * 70)

    zd_path = OUTPUTS / "phase2_paper_social_z_delta_result.json"
    if not zd_path.exists():
        print(f"❌ ไม่มี {zd_path.name} - ต้องรัน fetch_trends_worldwide_serpapi.py ก่อน")
        sys.exit(1)
    with open(zd_path, encoding="utf-8") as f:
        zd_data = json.load(f)
    master_report = zd_data.get("master_report") or []
    print(f"โหลด {zd_path.name}: {len(master_report)} คลัสเตอร์รวม (จาก SerpAPI ครั้งเดียว)")

    attribution = build_trend_stream_attribution()
    by_stream, unmatched = split_master_report_by_stream(master_report, attribution)

    for stream in STREAM_FILES:
        n = len(by_stream.get(stream, []))
        print(f"  {stream:8} -> {n} คลัสเตอร์ (นับซ้ำได้ถ้าเทรนด์ยืนยันข้ามสาย)")
    if unmatched:
        print(f"  ⚠️ {len(unmatched)} คลัสเตอร์จับคู่สายไม่ได้เลย (ชื่ออาจไม่ตรงเป๊ะ): {unmatched}")

    df_category = aggregate_to_category_level(by_stream)
    print("\n" + "-" * 70)
    print("ชั้น 3 — ระดับหมวด (ต่อสาย, .mean() ภายในสาย)")
    print("-" * 70)
    print(df_category.to_string(index=False) if not df_category.empty else "(ไม่มีข้อมูล)")

    overall = aggregate_to_overall_level(df_category)
    print("\n" + "-" * 70)
    print("ชั้น 4 — ภาพรวม (equal-weight ข้ามหมวด)")
    print("-" * 70)
    for k, v in overall.items():
        print(f"  {k}: {v}")

    out_path = OUTPUTS / "phase2_category_overall_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "_note": "⑧ ชั้น 3-4 เชื่อมข้อมูลจริงครั้งแรก - ดู run_category_aggregation.py",
            "_source": str(zd_path.name),
            "_unmatched_clusters": unmatched,
            "category_level": df_category.to_dict(orient="records"),
            "overall": overall,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ Saved -> {out_path}")
