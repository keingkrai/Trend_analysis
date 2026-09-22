# -*- coding: utf-8 -*-
"""
Phase 2 — ชั้นพยากรณ์ 3-4 (รวมระดับกลุ่ม → หมวด → ภาพรวม)
ดู Detail/05 งานที่ยังไม่ได้ทำ/Workflow v2 — แยกสายแล้วรวม.md ส่วน "⑧ พยากรณ์ไล่ขึ้นเป็นชั้นๆ"

ชั้น 1-2 (คีย์เวิร์ด×กลุ่ม → กลุ่ม) มีอยู่แล้วใน `trend_final.py`'s `forecast_trend()` — ฟังก์ชันนั้น
คืน `master_report` (DataFrame หนึ่งแถวต่อ "กลุ่ม/คลัสเตอร์" คอลัมน์ Current_Z/Forecast_Avg_Z/Z_Delta)
ที่นี่คือของใหม่ทั้งหมด (ไม่มีเทียบเท่าใน trend_final.py เลย ไม่ใช่การแก้บั๊ก) รับ master_report
**ต่อสาย** (News-Intl/News-Thai/Social/Paper) มารวมขึ้นอีก 2 ชั้น:

    ชั้น 3: .mean() ภายในแต่ละสาย → 1 แถวต่อสาย (หมวด)
    ชั้น 4: .mean() ข้ามสายทั้งหมด → 1 ค่าภาพรวม

🆕 การตัดสินใจเรื่องถ่วงน้ำหนัก (2026-08-31): **ทุกหมวดเสียงเท่ากัน (ค่าเฉลี่ยของค่าเฉลี่ย)** ไม่ถ่วง
ตามจำนวนกลุ่ม — เหตุผล: ถ้าถ่วงตามจำนวนกลุ่ม หมวดที่มีโครงสร้างข้อมูลน้อยกว่าโดยธรรมชาติ (เช่น Paper
ที่แหล่งวิชาการมีจำกัดกว่าข่าว) จะถูกกลบเสียงในภาพรวมเสมอ ทั้งที่อาจเป็นสัญญาณนำที่มีค่า (Means-End/
JTBD framing เดียวกับที่ใช้ตัดสินใจเรื่องอื่นๆ ใน workflow นี้ - เสียงข้างน้อยไม่ใช่เสียงที่ผิด)

⚠️ ยังไม่เคยรันกับข้อมูลจริงจาก Google Trends เลย เพราะยังไม่มีสายไหนไปถึงขั้น `forecast_trend()` ใน
v2 architecture นี้ (Phase 1/2 หยุดแค่ขั้นแตกคีย์เวิร์ด ยังไม่ได้ยิง SerpAPI) - ทดสอบด้วยข้อมูลสังเคราะห์
(synthetic master_report ที่มีรูปร่าง/คอลัมน์เดียวกับของจริงเป๊ะ) ก่อน เพื่อพิสูจน์ว่า logic การรวมชั้น
ถูกต้อง โดยเฉพาะพฤติกรรม "หมวดกลุ่มน้อยไม่ถูกกลบเสียง" - ต้องรันกับผลจริงซ้ำอีกครั้งทันทีที่มี
master_report จริงจากทุกสาย (ดู __main__ ท้ายไฟล์นี้สำหรับตัวอย่างการทดสอบสังเคราะห์)
"""
import pandas as pd


def _status_from_z_delta(z_delta):
    """เกณฑ์เดียวกับ generate_master_trend_report() ใน trend_final.py ทุกประการ (บรรทัด ~2009)
    ต้องใช้ threshold เดียวกันเป๊ะ ไม่งั้นสถานะระดับหมวด/ภาพรวมจะเทียบกับสถานะระดับกลุ่มไม่ได้"""
    if z_delta > 0.8:
        return "Major Breakout"
    if z_delta > 0.2:
        return "Rising"
    if z_delta < -0.2:
        return "Fading"
    return "Stable"


def aggregate_to_category_level(master_reports_by_stream):
    """ชั้น 3: รวม master_report ระดับกลุ่ม (ต่อสาย) ขึ้นเป็นระดับหมวด - .mean() ภายในแต่ละสายเท่านั้น

    Args:
        master_reports_by_stream: dict {stream_name: master_report_df}
            master_report_df คือ DataFrame ที่ได้จาก trend_final.py's generate_master_trend_report()
            (ผ่าน forecast_trend()) ต้องมีคอลัมน์อย่างน้อย: Current_Z, Forecast_Avg_Z, Z_Delta
            สายที่ไม่มีข้อมูล (None/DataFrame ว่าง/คลัสเตอร์ทั้งหมดถูกกรองออกไปก่อนหน้านี้) จะถูกข้าม
            ไปเฉยๆ ไม่ error - เกิดขึ้นได้จริง (เช่น News-Intl ที่ยังได้ 0 triplets อยู่ตอนนี้ ดู Backlog
            ข้อ 23)

    Returns:
        DataFrame หนึ่งแถวต่อสาย: Stream, N_Clusters, Current_Z, Forecast_Avg_Z, Z_Delta, Status
    """
    rows = []
    for stream, df in master_reports_by_stream.items():
        if df is None or df.empty:
            print(f"  ⚠️ ข้าม {stream} - ไม่มี master_report (สายนี้อาจยังไม่มีคลัสเตอร์ที่พยากรณ์ได้)")
            continue
        for col in ("Current_Z", "Forecast_Avg_Z", "Z_Delta"):
            if col not in df.columns:
                raise ValueError(f"master_report ของ {stream} ขาดคอลัมน์ {col} - ไม่ใช่รูปแบบเดียวกับ "
                                  f"generate_master_trend_report() ของ trend_final.py")
        rows.append({
            "Stream": stream,
            "N_Clusters": len(df),
            "Current_Z": round(float(df["Current_Z"].mean()), 3),
            "Forecast_Avg_Z": round(float(df["Forecast_Avg_Z"].mean()), 3),
            "Z_Delta": round(float(df["Z_Delta"].mean()), 3),
        })
    result = pd.DataFrame(rows)
    if not result.empty:
        result["Status"] = result["Z_Delta"].apply(_status_from_z_delta)
    return result


def aggregate_to_overall_level(df_category_level):
    """ชั้น 4: รวมระดับหมวด (ผลจาก aggregate_to_category_level) ขึ้นเป็นภาพรวมเดียว

    ทุกหมวดเสียงเท่ากันเสมอ (ค่าเฉลี่ยของค่าเฉลี่ยที่ชั้น 3 คำนวณไว้แล้ว) - ไม่ถ่วงน้ำหนักตามจำนวนกลุ่ม
    ตามการตัดสินใจ 2026-08-31 (ดู docstring บนสุดของไฟล์)

    Returns:
        dict {Current_Z, Forecast_Avg_Z, Z_Delta, Status, N_Streams, Streams_Included} หรือ {} ถ้าไม่มี
        หมวดไหนมีข้อมูลเลย
    """
    if df_category_level is None or df_category_level.empty:
        return {}
    current_z = df_category_level["Current_Z"].mean()
    forecast_avg_z = df_category_level["Forecast_Avg_Z"].mean()
    z_delta = df_category_level["Z_Delta"].mean()
    return {
        "Current_Z": round(float(current_z), 3),
        "Forecast_Avg_Z": round(float(forecast_avg_z), 3),
        "Z_Delta": round(float(z_delta), 3),
        "Status": _status_from_z_delta(z_delta),
        "N_Streams": len(df_category_level),
        "Streams_Included": list(df_category_level["Stream"]),
    }


if __name__ == "__main__":
    # ทดสอบด้วยข้อมูลสังเคราะห์ (ไม่ยิง API ใดๆ) - เป้าหมายคือพิสูจน์ 2 อย่าง:
    # (1) การรวมชั้นทำงานถูกต้องทางคณิตศาสตร์
    # (2) "ทุกหมวดเสียงเท่ากัน" จริง - หมวดที่มีกลุ่มน้อย (Paper, 2 กลุ่ม) ไม่ถูกกลบเสียงโดยหมวดที่มี
    #     กลุ่มเยอะกว่า (Social, 5 กลุ่ม) แม้ N_Clusters ต่างกันมาก
    paper_mr = pd.DataFrame([
        {"cluster_id": 1, "Cluster": "Waterless Beauty and Solid Cleansing", "Current_Z": 0.1,
         "Forecast_Avg_Z": 1.5, "Z_Delta": 1.4},  # แรงมาก (สมมติ)
        {"cluster_id": 2, "Cluster": "Evidence-Based Barrier-Friendly Cleansing", "Current_Z": 0.3,
         "Forecast_Avg_Z": 1.1, "Z_Delta": 0.8},
    ])
    social_mr = pd.DataFrame([
        {"cluster_id": 1, "Cluster": "Antibacterial Body Wash 2030", "Current_Z": 0.2,
         "Forecast_Avg_Z": 0.3, "Z_Delta": 0.1},  # นิ่ง
        {"cluster_id": 2, "Cluster": "BHA-infused body care", "Current_Z": 0.1,
         "Forecast_Avg_Z": 0.2, "Z_Delta": 0.1},
        {"cluster_id": 3, "Cluster": "Allergy-Safe Scent-Customizable Beauty", "Current_Z": 0.0,
         "Forecast_Avg_Z": 0.15, "Z_Delta": 0.15},
        {"cluster_id": 4, "Cluster": "Gentle Barrier-Friendly Cleansing", "Current_Z": 0.4,
         "Forecast_Avg_Z": 0.5, "Z_Delta": 0.1},
        {"cluster_id": 5, "Cluster": "Local Beauty Preferences in Thailand", "Current_Z": -0.1,
         "Forecast_Avg_Z": 0.0, "Z_Delta": 0.1},
    ])
    news_intl_mr = pd.DataFrame()  # ยังไม่มีข้อมูลจริง (ข้อ 23 ยังไม่แก้) - จำลองเป็นสายที่ยังว่าง
    news_th_mr = None  # ยังไม่เคยรันเต็มเลย - จำลองเป็น None ตรงๆ

    print("=" * 70)
    print("ทดสอบชั้น 3-4 ด้วยข้อมูลสังเคราะห์ (ไม่ใช่ผลจริง)")
    print("=" * 70)

    by_stream = {"Paper": paper_mr, "Social": social_mr, "News-Intl": news_intl_mr, "News-Thai": news_th_mr}
    df_category = aggregate_to_category_level(by_stream)
    print("\n--- ชั้น 3: ระดับหมวด ---")
    print(df_category.to_string(index=False))

    overall = aggregate_to_overall_level(df_category)
    print("\n--- ชั้น 4: ภาพรวม ---")
    for k, v in overall.items():
        print(f"  {k}: {v}")

    print("\n--- ตรวจสอบ 'ทุกหมวดเสียงเท่ากัน' ---")
    paper_z = df_category[df_category["Stream"] == "Paper"]["Z_Delta"].iloc[0]
    social_z = df_category[df_category["Stream"] == "Social"]["Z_Delta"].iloc[0]
    naive_flat_mean = pd.concat([paper_mr["Z_Delta"], social_mr["Z_Delta"]]).mean()
    print(f"  Paper Z_Delta (2 กลุ่ม, เฉลี่ยแรงกว่าเยอะ): {paper_z}")
    print(f"  Social Z_Delta (5 กลุ่ม, นิ่งกว่า): {social_z}")
    print(f"  ภาพรวม (equal-weight, ที่ใช้จริง): {overall['Z_Delta']}")
    print(f"  ถ้าใช้ flat mean ข้ามกลุ่มทั้งหมดแทน (ไม่ equal-weight): {round(naive_flat_mean, 3)}")
    assert abs(overall["Z_Delta"] - (paper_z + social_z) / 2) < 1e-9, "equal-weight คำนวณผิด!"
    print("  ✅ ยืนยัน: overall Z_Delta = ค่าเฉลี่ยของ (Paper, Social) เท่านั้น ไม่ถูกดึงเข้าใกล้ Social "
          "ทั้งที่ Social มีกลุ่มเยอะกว่า 2.5 เท่า - equal-weight ทำงานถูกต้อง")
    print(f"  (เทียบ: flat mean จะเอนเอียงไปทาง Social มากกว่า เพราะมี 5 กลุ่มเทียบ Paper แค่ 2 กลุ่ม)")
