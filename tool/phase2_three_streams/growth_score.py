# -*- coding: utf-8 -*-
"""
Phase 2 — Growth Score: คะแนนการเติบโตของการค้นหา ใช้จัดอันดับเทรนด์แทน Z_Delta (🆕 2026-09-30)

ที่มา (backtest 30 ก.ย. 2026 - main/output/_backups/backtest_ipynb_before_trim_20260930/backtest.ipynb ส่วนที่ 6
และการทดลองต่อยอดปีที่ 3): อันดับ Z_Delta สวนทางกับการโตจริงในปีถัดไป (Spearman −0.20) เพราะในทางปฏิบัติมันวัด
"ตอนนี้ห่างจากระดับปกติแค่ไหน" แล้วคาดว่าจะเด้งกลับ ส่วนการเติบโตที่ผ่านมา (momentum) ได้ +0.43 และผสมอันดับ
momentum กับโมเดลพยากรณ์การเติบโตได้ +0.49 (ปีที่ 1) / +0.50 (ปีที่ 3) - เจ้าของงานเลือกใช้แบบนี้ (30 ก.ย. 2026)

    การเติบโตปีที่ h = log( ค่าเฉลี่ยการค้นหาในปีที่ h ข้างหน้า ÷ ค่าเฉลี่ย 12 เดือนล่าสุด )

ขั้นตอน:
1. ตัวอย่างฝึก = 1 คีย์เวิร์ด ณ 1 เดือนในอดีต (ทุกเดือนตั้งแต่ 2008) ฟีเจอร์ใช้แค่ข้อมูลถึงเดือนนั้น (features_at)
2. โมเดล RandomForest ตัวเดียวต่อปี (ปีที่ 1-5) เรียนจากทุกคีย์เวิร์ดร่วมกัน ใช้เฉพาะตัวอย่างที่ผลจริงอยู่ในช่วงข้อมูล
   ที่เชื่อได้ (LAST_TRUSTED_MONTH) - ตั้งค่าเดียวกับ backtest ทุกอย่าง
   🆕 (2026-10-02) + ฟีเจอร์เทียบเดือนเดียวกันปีก่อน/ความเร่ง - การปรับสเกล ณ เดือนนั้น (pit_scale) มีไว้แต่ยังปิด (PIT_SCALING)
   🆕 (2026-10-29) โมเดลถูกฝึกครั้งเดียวจากชุดคีย์เวิร์ดกลาง ~500 คำ (growth_pool.py, GROWTH_MODEL = "pool") แล้วใช้ทายทุกรอบ -
   เดิมฝึกใหม่จากคีย์เวิร์ดของรอบนั้น รอบสาย Search มี ~44 คำ ทำให้ % ที่คาดเพี้ยนและอันดับไม่นิ่ง ("per-run" ยังใช้ได้เพื่อสร้างรอบเก่าซ้ำ)
3. ทายการเติบโตของทุกคีย์เวิร์ด ณ เดือนล่าสุดของข้อมูล
4. คะแนนคีย์เวิร์ด = percentile ของ (percentile ของ momentum + percentile ของค่าที่โมเดลทาย) / 2 เทียบคีย์เวิร์ดทั้งหมด
   ในรอบ - 0.5 = ค่ากลางของตลาด (ตรงกับที่ backtest ใช้ "ผสมอันดับ") - 🆕 (2026-09-30) ตอนนี้ใช้ percentile ของค่าที่
   โมเดลทายอย่างเดียว (BLEND_MOMENTUM = False) จนกว่าข้อมูลจะพ้นช่วงกระโดดของ cat=0 ดูเหตุผลที่ BLEND_MOMENTUM
5. คะแนนเทรนด์ = มัธยฐานของคะแนนคีย์เวิร์ดในเทรนด์นั้น (ไม่รวมคีย์เวิร์ดที่ข้อมูลน้อยเกินไป)

ข้อจำกัดที่ต้องรู้:
- backtest รายคีย์เวิร์ดยืนยันได้แค่ "ลำดับ" - ขนาดการโตทดสอบแยกที่ระดับเทรนด์ (FORECAST_BAND_80) รายงานจึงแสดง % ที่คาด
  ของเทรนด์คู่กับช่วงคลาดเคลื่อนนั้นเสมอ (🆕 2026-10-02 หน้าภาพรวมทุกเทรนด์ของ ⑯ ใช้ % แทนคำ "เร็ว/ช้า")
- ปีที่ 4-5 ทดสอบได้น้อยกว่า (จุดตัด 11 / 9 จุด เพราะผลจริงต้องจบก่อน LAST_TRUSTED_MONTH) ช่วงคลาดเคลื่อนกว้างกว่ามาก
- คีย์เวิร์ดในการทดสอบถูกเลือกในปี 2026 (survivorship) ตัวเลขความต่อเนื่องจึงน่าจะสูงกว่าความจริง
"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

FORECAST_DIR_NAME = "serpapi_forecast_run"   # ต้องตรงกับ OUTPUT_DIR ของ ⑦ (fetch_trends_worldwide_serpapi.py)
MONTHLY_FILE = "step5a_monthly_trends.xlsx"   # ค่าการค้นหารายเดือนดิบต่อคีย์เวิร์ด (0-100 ของ Google Trends)
KEYWORD_MAP_FILE = "step5b_df_keyword_processed.xlsx"  # คีย์เวิร์ด -> คลัสเตอร์ (ชื่อคลัสเตอร์ = ชื่อเทรนด์)
OUTPUT_FILE = "phase2_growth_score_result.json"

SAMPLE_START = pd.Timestamp("2008-01-01")     # เท่ากับ backtest ส่วนที่ 6
# ข้อมูล Google Trends แบบไม่ระบุหมวด (cat=0) กระโดดขึ้นทุกคีย์เวิร์ดพร้อมกันตั้งแต่ ก.ค.-ส.ค. 2025 (ฝั่ง Google ไม่ใช่
# ความสนใจจริง - ทดสอบเทียบ cat=143 แล้ว 30 ก.ย. 2026) ตัวอย่างฝึกที่ผลจริงเลยเดือนนี้ไปจะสอนโมเดลให้เรียนการกระโดดนั้น
# จึงไม่ใช้ฝึก - ถ้าเปลี่ยนไปดึงข้อมูลแบบระบุหมวดแล้ว ขยับค่านี้ไปข้างหน้าได้
LAST_TRUSTED_MONTH = pd.Timestamp("2025-06-01")

# ปีที่ h ข้างหน้า = เดือนที่ a ถึง b หลังเดือนล่าสุด
# 🆕 (2026-10-02) ขยายเป็น 5 ปี (เจ้าของงาน: ระยะสั้น = ปีที่ 1-2, ระยะยาว = ปีที่ 3-5)
HORIZONS = {1: (1, 12), 2: (13, 24), 3: (25, 36), 4: (37, 48), 5: (49, 60)}
# 🆕 (2026-10-02) + yoy_3m / yoy_6m / accel_12m (backtest แบบ point-in-time 2 รอบข้อมูล: +0.02..+0.05 ทุกปี) - ห้ามเพิ่ม
# ฟีเจอร์ "ระดับ" ดิบ (เช่น log ของค่าเฉลี่ย) ถ้าไม่ผ่าน pit_scale: สเกล Google Trends อิงค่าสูงสุดทั้งช่วงรวมอนาคต = ข้อมูลรั่ว
BASE_FEATURES = ["growth_past_12m", "growth_past_6m", "growth_past_3m", "slope_24m", "level_vs_peak",
                 "volatility_12m", "pct_nonzero_24m", "z_now", "months_since_first_search",
                 "yoy_3m", "yoy_6m", "accel_12m"]
LONG_FEATURES = BASE_FEATURES + ["growth_past_36m", "years_up_of_5", "slope_60m"]
# ชุดฟีเจอร์ต่อปีตามที่ backtest ทดสอบ: ปีที่ 1 = ชุดพื้นฐาน, ปีที่ 2-5 = + ประวัติยาว (ปีที่ 3 ดีกว่าชุดพื้นฐาน 8/13 จุดตัด)
MODEL_FEATURES = {1: BASE_FEATURES, **{h: LONG_FEATURES for h in (2, 3, 4, 5)}}
RF_PARAMS = {"n_estimators": 300, "min_samples_leaf": 20, "random_state": 42, "n_jobs": -1}

# 🆕 (2026-09-30, เจ้าของงานเลือก) ชั่วคราว: คะแนนใช้โมเดลอย่างเดียว ไม่ผสมอันดับ momentum - ข้อมูล cat=0 กระโดดทุกคีย์เวิร์ด
# ตั้งแต่ ส.ค. 2025 ทำให้ momentum (12 เดือนล่าสุด ÷ 12 เดือนก่อน) สูงเกินจริงและสวนทางกับโมเดล (Spearman −0.48 ในรอบ
# 082438 เทียบ +0.63 ในอดีต) ระดับเทียบตลาดกับ % ที่คาดในรายงานเลยขัดกัน - backtest: โมเดลอย่างเดียวจัดอันดับได้ 0.485
# (ปีที่ 1) / 0.434 (ปีที่ 3) เทียบแบบผสม 0.503 / 0.496 - เปิดกลับ (True) เมื่อทั้งสองช่วงที่เทียบพ้นจุดกระโดดแล้ว
# (ข้อมูลถึงเดือน MOMENTUM_CLEAN_FROM ขึ้นไป - compute_growth_scores เตือนให้เอง)
BLEND_MOMENTUM = False
MOMENTUM_CLEAN_FROM = pd.Timestamp("2027-07-01")
# 🆕 (2026-10-02, เจ้าของงานเลือก) ปรับสเกลตัวอย่างฝึก ณ เดือนนั้น (pit_scale) - ยังปิด: backtest 2 รอบข้อมูลจัดอันดับดีกว่า
# (คีย์เวิร์ด ปีที่ 2 0.50 เทียบ 0.47, ปีที่ 5 0.45 เทียบ 0.40) แต่กับข้อมูลจริงตอนนี้อันดับเปลี่ยนมาก (รอบ 082438: Safe Inhalation
# Spray จากที่ 7 ขึ้นที่ 1 - เทรนด์ที่ข้อมูล cat=0 กระโดดหนักสุด) และ % ที่คาดสูงขึ้นอีก (ค่ากลางตลาดปีที่ 5 +133% เทียบ +101%)
# พิสูจน์ไม่ได้ว่าเป็นของจริงหรือผลของข้อมูลกระโดด - เปิด (True) หลังดึงข้อมูลแบบระบุหมวด (cat=143) แล้วตรวจอันดับใหม่
# เปิดแล้วต้องคำนวณ FORECAST_BAND_80 ใหม่ด้วย (แบบ PIT: ปี 1 -10..+19%, ปี 2 -13..+35%, ปี 5 -23..+131%)
PIT_SCALING = False
GROWTH_LINE = 0.5                   # ค่ากลางของตลาด - เส้นแบ่งในหน้าภาพรวมและเกณฑ์ทำหน้ารายละเอียด
GRADE_FLOORS = (0.8, 0.5, 0.2)      # ขอบล่างของระดับ 4 / 3 / 2 (ต่ำกว่า 0.2 = ระดับ 1)
RECENT_MONTHS = 6                   # ป้ายเตือน: ค่าเฉลี่ย 6 เดือนล่าสุด เทียบ 6 เดือนเดียวกันของปีก่อน
DECLINE_THRESHOLD = float(np.log(0.9))   # ลดลงเกิน 10% = ติดป้ายเตือน (ข้อมูลจริง ไม่ใช่การทาย)
HISTORY_MONTHS = 60                 # กราฟหน้าเทรนด์ของรายงาน: ดัชนีการค้นหาจริงย้อนหลัง 5 ปี
# 🆕 (2026-09-30) ระดับที่คาดของเทรนด์ในปีที่ 1/2/3 (กราฟหน้าเทรนด์) - walk-forward 2016-2022 ระดับเทรนด์ (15 เทรนด์ x 13
# จุดตัด): ค่ากลางความคลาดเคลื่อนของระดับ 6.3% / 8.5% / 12.3% (momentum ล้วน 8.2 / 12.1 / 20.1%, ทายว่าไม่เปลี่ยน
# 9.8 / 20.6 / 32.1%) ช่วงด้านล่าง = เปอร์เซ็นไทล์ 10-90 ของ (ผลจริง ÷ ที่ทาย) - แถบในกราฟครอบคลุมผลจริงราว 80%
# 🆕 (2026-10-02) คำนวณใหม่หลังเพิ่มฟีเจอร์ใหม่ + 5 ปี (PIT_SCALING ปิด): walk-forward รวม 2 รอบข้อมูล (082438 + 111455,
# 15 เทรนด์ต่อรอบ, จุดตัด 13/13/13/11/9) เปอร์เซ็นไทล์ 10-90 ของ (ผลจริง ÷ ที่ทาย) ระดับดัชนีเทรนด์ - ค่ากลางความคลาดเคลื่อน
# 5.5 / 8.6 / 12.3 / 16.2 / 19.5% (ทายว่าไม่เปลี่ยน 9.7 / 20.0 / 31.0 / 41.9 / 55.3%) ปีที่ 5 ผลจริงสูงกว่าที่ทาย 62% ของกรณี
# (ปีที่ 1-2 ราวครึ่งต่อครึ่ง) - ค่าเดิม (โมเดล 3 ปีรอบเดียว) = (-0.10, 0.12) / (-0.14, 0.20) / (-0.15, 0.24)
FORECAST_BAND_80 = {1: (-0.10, 0.12), 2: (-0.15, 0.19), 3: (-0.21, 0.26), 4: (-0.25, 0.35), 5: (-0.27, 0.48)}   # โมเดลรายรอบ
# 🆕(2026-10-29, เจ้าของงานสั่ง) โมเดลที่ใช้ทาย: "pool" = โมเดลล็อกฝึกจากชุดกลาง (growth_pool.py) / "per-run" = ฝึกจากคีย์เวิร์ดของรอบ
# (วิธีเดิม - ใช้สร้างรอบเก่าซ้ำให้ได้ตัวเลขเดิม) ; ตั้งต่อครั้งด้วย env GROWTH_MODEL ได้ ; แถบ 80% ของโหมด pool อยู่ใน
# growth_pool/pool_manifest.json (FORECAST_BAND_80 ข้างบนใช้กับโหมด per-run เท่านั้น)
GROWTH_MODEL = "pool"
MIN_RUN_KEYWORDS = 300   # โหมด per-run: ต่ำกว่านี้อันดับไม่นิ่ง (ทดลอง 2026-10-29: ฝึกจาก 150 คำ Spearman ข้ามชุดฝึก 0.6, 300 คำ 0.7-0.87)


def log_growth(new_mean, old_mean):
    """log ของอัตราส่วน (บวก 1 ทั้งเศษและส่วนกันหารด้วย 0) - +0.10 ≈ โต 10%"""
    return float(np.log((new_mean + 1) / (old_mean + 1)))


def has_enough_data(values, i):
    """12 เดือนล่าสุดต้องมีข้อมูลอย่างน้อย 6 เดือน และค่าเฉลี่ยไม่ต่ำกว่า 1 (เกณฑ์เดียวกับ backtest)"""
    if i < 23:
        return False
    past = values[i - 11:i + 1]
    return (past > 0).sum() >= 6 and past.mean() >= 1


def features_at(values, i):
    """ฟีเจอร์ ณ เดือน i - ใช้แค่ values[:i+1] (ไม่เห็นอนาคต) ชุดเดียวกับ backtest ส่วนที่ 6 + ประวัติยาว 3 ตัว
    ฟีเจอร์ประวัติยาวเป็น NaN ถ้าข้อมูลย้อนหลังไม่พอ (RandomForest ของ sklearn >= 1.4 รับ NaN ได้)"""
    past = values[i - 11:i + 1]
    log_values = np.log(values[:i + 1] + 1)
    std = past.std(ddof=1)
    yearly = [values[i - 12 * k - 11:i - 12 * k + 1].mean() if i - 12 * k - 11 >= 0 else np.nan for k in range(6)]
    return {
        "growth_past_12m": log_growth(past.mean(), values[i - 23:i - 11].mean()),
        "growth_past_6m": log_growth(values[i - 5:i + 1].mean(), values[i - 11:i - 5].mean()),
        "growth_past_3m": log_growth(values[i - 2:i + 1].mean(), values[i - 5:i - 2].mean()),
        "slope_24m": float(np.polyfit(np.arange(24), log_values[-24:], 1)[0]),
        "level_vs_peak": float(past.mean() / max(values[:i + 1].max(), 1)),
        "volatility_12m": float(np.std(np.diff(log_values[-13:]))),
        "pct_nonzero_24m": float((values[i - 23:i + 1] > 0).mean()),
        "z_now": float((values[i] - past.mean()) / std) if std > 0 else 0.0,
        "months_since_first_search": int(i - np.argmax(values[:i + 1] > 0)),
        "growth_past_36m": log_growth(past.mean(), yearly[3]) if not np.isnan(yearly[3]) else np.nan,
        "years_up_of_5": (float(sum(yearly[k] > yearly[k + 1] for k in range(5)))
                          if not np.isnan(yearly[5]) else np.nan),
        "slope_60m": float(np.polyfit(np.arange(60), log_values[-60:], 1)[0]) if i >= 59 else np.nan,
        # 🆕 (2026-10-02) เทียบเดือนเดียวกันของปีก่อน (ตัดฤดูกาลออก ต่างจาก growth_past_3m/6m) + ความเร่งของการโตรายปี
        "yoy_3m": log_growth(values[i - 2:i + 1].mean(), values[i - 14:i - 11].mean()),
        "yoy_6m": log_growth(values[i - 5:i + 1].mean(), values[i - 17:i - 11].mean()),
        "accel_12m": (log_growth(past.mean(), values[i - 23:i - 11].mean())
                      - log_growth(values[i - 23:i - 11].mean(), values[i - 35:i - 23].mean())) if i >= 35 else np.nan,
    }


def targets_at(values, i):
    """เป้าหมายปีที่ h (HORIZONS) = log(ค่าเฉลี่ยปีนั้น ÷ ค่าเฉลี่ย 12 เดือนล่าสุด) - NaN ถ้าข้อมูลยังไปไม่ถึงปีนั้น"""
    past_mean = values[i - 11:i + 1].mean()
    return {f"t_y{h}": (log_growth(values[i + a:i + b + 1].mean(), past_mean) if i + b < len(values) else np.nan)
            for h, (a, b) in HORIZONS.items()}


def _month_index(ts):
    return ts.year * 12 + ts.month - 1


def pit_scale(values, i, running_max=None):
    """🆕 (2026-10-02) ปรับสเกลอนุกรมให้ค่าสูงสุดถึงเดือน i = 100 เหมือนดึงข้อมูล ณ เดือนนั้นจริง (point-in-time)
    Google Trends ปรับสเกลแต่ละคีย์เวิร์ดให้ค่าสูงสุดของทั้งช่วงที่ดึง = 100 - 93% ของคีย์เวิร์ดพุ่งสูงสุดหลัง ส.ค. 2025 ค่าในอดีต
    จึงถูกบีบตามระดับที่จะขึ้นไปถึงในอนาคต ฟีเจอร์ที่ขึ้นกับสเกล (pct_nonzero, ค่า +1 ใน log_growth) ตอนฝึกเลยต่างจากตอนใช้งาน
    จริง (ข้อมูลล่าสุดสเกลถึงวันนี้พอดี) - backtest 2 รอบข้อมูล: แก้แค่นี้ Spearman ขึ้น y1 +0.01, y2 +0.03, y5 +0.05
    เดือนล่าสุดของข้อมูลคืนค่าเดิม (ค่าสูงสุดถึงวันนี้ = 100 อยู่แล้ว)"""
    peak = running_max[i] if running_max is not None else values[:i + 1].max()
    return values * (100.0 / peak) if peak > 0 else values


def build_samples(series_by_keyword, start=SAMPLE_START):
    """ตัวอย่างฝึก: ทุกคีย์เวิร์ด x ทุกเดือนตั้งแต่ start ที่ข้อมูลพอ (ฟีเจอร์ + เป้าหมายทุกปี + เดือนของตัวอย่าง)
    🆕 (2026-10-02) PIT_SCALING = True -> คิดฟีเจอร์/เป้าหมาย/เกณฑ์ข้อมูลพอบนอนุกรมที่ปรับสเกล ณ เดือนนั้น (pit_scale)
    past12 = ค่าเฉลี่ย 12 เดือนล่าสุดในสเกลเดียวกัน (backtest ใช้รวมคำเป็นดัชนีเทรนด์)"""
    rows = []
    for keyword, series in series_by_keyword.items():
        raw, dates = series.to_numpy(dtype=float), series.index
        running_max = np.maximum.accumulate(raw) if len(raw) else raw
        for i in range(len(raw)):
            if dates[i] < start:
                continue
            values = pit_scale(raw, i, running_max) if PIT_SCALING else raw
            if not has_enough_data(values, i):
                continue
            rows.append({"keyword": keyword, "month": _month_index(dates[i]), "past12": values[i - 11:i + 1].mean(),
                         **features_at(values, i), **targets_at(values, i)})
    return pd.DataFrame(rows)


def train_models(samples, last_trusted=LAST_TRUSTED_MONTH):
    """โมเดลต่อปี - ใช้เฉพาะตัวอย่างที่ผลจริงของปีนั้นจบไม่เกิน last_trusted คืน ({h: model}, {h: จำนวนตัวอย่าง})"""
    from sklearn.ensemble import RandomForestRegressor

    last = _month_index(last_trusted)
    models, n_train = {}, {}
    for h, (_, b) in HORIZONS.items():
        target = f"t_y{h}"
        known = samples[(samples["month"] + b <= last) & samples[target].notna()]
        if len(known) < 100:
            raise ValueError(f"ตัวอย่างฝึกปีที่ {h} มีแค่ {len(known)} ตัว - ข้อมูลย้อนหลังไม่พอฝึกโมเดล")
        models[h] = RandomForestRegressor(**RF_PARAMS).fit(known[MODEL_FEATURES[h]], known[target])
        n_train[h] = len(known)
    return models, n_train


def predict_keywords(series_by_keyword, models):
    """ทายการเติบโต ณ เดือนล่าสุดของแต่ละคีย์เวิร์ด - คีย์เวิร์ดที่ข้อมูลน้อยเกินไป thin=True และไม่มีค่าทาย"""
    rows, feats = [], []
    for keyword, series in series_by_keyword.items():
        values = series.to_numpy(dtype=float)
        i = len(values) - 1
        row = {"keyword": keyword, "as_of": series.index[-1], "thin": not has_enough_data(values, i),
               "momentum": np.nan}
        if i >= 11 + 12:
            # ค่าเฉลี่ยช่วงเวลาดิบ (ข้อมูลจริง) - ระดับเทรนด์รวมเป็นดัชนีเดียวก่อนเทียบ ดู aggregate_clusters
            row.update(last12_mean=values[i - 11:i + 1].mean(), prev12_mean=values[i - 23:i - 11].mean(),
                       recent_mean=values[i - RECENT_MONTHS + 1:i + 1].mean(),
                       year_ago_mean=values[i - 12 - RECENT_MONTHS + 1:i - 12 + 1].mean())
        if not row["thin"]:
            f = features_at(values, i)
            row["momentum"] = f["growth_past_12m"]
            feats.append((len(rows), f))
        rows.append(row)
    kw = pd.DataFrame(rows)
    for h in models:
        kw[f"pred_y{h}"] = np.nan
    if feats:  # ทายทีเดียวทั้งชุด (ทีละคีย์เวิร์ดช้ามากเพราะ n_jobs=-1 ต้องแตกงานทุกครั้ง)
        idx, x = [j for j, _ in feats], pd.DataFrame([f for _, f in feats])
        for h, model in models.items():
            kw.loc[idx, f"pred_y{h}"] = model.predict(x[MODEL_FEATURES[h]])
    return kw


def blend_scores(kw, use_momentum=None):
    """คะแนนปีที่ h ต่อคีย์เวิร์ด เทียบเฉพาะคีย์เวิร์ดที่ข้อมูลพอ - ค่า 0-1, 0.5 = ค่ากลางของตลาด (คีย์เวิร์ดทั้งหมดในรอบ)
    - use_momentum=True: percentile ของค่าเฉลี่ย (percentile momentum, percentile ค่าที่โมเดลทาย) = แบบผสมใน backtest
    - use_momentum=False: percentile ของค่าที่โมเดลทายอย่างเดียว (ค่าเริ่มต้นตอนนี้ - ดู BLEND_MOMENTUM)"""
    use_momentum = BLEND_MOMENTUM if use_momentum is None else use_momentum
    kw = kw.copy()
    ok = ~kw["thin"].astype(bool)
    mom = kw.loc[ok, "momentum"].rank(pct=True) if use_momentum else None
    for h in HORIZONS:
        pred = kw.loc[ok, f"pred_y{h}"].rank(pct=True)
        kw.loc[ok, f"score_y{h}"] = ((mom + pred) / 2).rank(pct=True) if use_momentum else pred
    return kw


def grade(score):
    """ระดับ 4 ขั้นเทียบตลาด: 4 เร็วกว่ามาก (>= 0.8) / 3 เร็วกว่า (>= 0.5) / 2 ช้ากว่า (>= 0.2) / 1 ช้ากว่ามาก"""
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return None
    return next((4 - k for k, floor in enumerate(GRADE_FLOORS) if score >= floor), 1)


def _pct_change(new_mean, old_mean):
    """% การเปลี่ยนแปลงของค่าเฉลี่ย (บวก 1 กันหารด้วย 0 เหมือน log_growth) - None ถ้าไม่มีข้อมูล"""
    if new_mean is None or old_mean is None or np.isnan(new_mean) or np.isnan(old_mean):
        return None
    return round(float(np.expm1(log_growth(new_mean, old_mean))) * 100, 1)


def aggregate_clusters(kw, mapping, band=None):
    """คีย์เวิร์ด -> เทรนด์ - mapping มีคอลัมน์ Keyword, cluster_name
    - คะแนนแต่ละปี = มัธยฐานของคะแนนคีย์เวิร์ดที่ข้อมูลพอ
    - การโต 12 เดือนที่ผ่านมา และ 6 เดือนล่าสุดเทียบปีก่อน (ข้อมูลจริง) = เทียบค่าเฉลี่ยของดัชนีเทรนด์ (ค่าเฉลี่ยคีย์เวิร์ดที่
      ข้อมูลพอ) - ดัชนีเดียวกับกราฟหน้าเทรนด์ในรายงาน ตัวเลข % กับกราฟจึงตรงกัน
    - ป้ายเตือนใช้เฉพาะคีย์เวิร์ดที่ข้อมูลพอเหมือนคะแนน (คำที่ข้อมูลบาง 0 -> 1 ก็กลายเป็นขึ้น/ลงหลายเท่า)"""
    merged = kw.merge(mapping, left_on="keyword", right_on="Keyword", how="inner")
    scored = kw[~kw["thin"].astype(bool)]
    market = {h: scored[f"pred_y{h}"].dropna().to_numpy() for h in HORIZONS if f"pred_y{h}" in scored}
    out = []
    for name, g in merged.groupby("cluster_name", sort=True):
        ok = g[~g["thin"].astype(bool)]
        rec = {"trend": name, "n_keywords": int(len(g)), "n_scored": int(len(ok))}
        forecast = expected_levels(ok, band)
        for h in HORIZONS:
            if not BLEND_MOMENTUM and forecast and len(market.get(h, [])):
                # 🆕 (2026-09-30) โหมดโมเดลอย่างเดียว: คะแนน = percentile ของการเติบโตที่คาดของดัชนีเทรนด์ (ตัวเลข "คาด +X%"
                # ในรายงาน) เทียบค่าที่ทายของคีย์เวิร์ดทั้งตลาด - ระดับกับ % ที่แสดงจึงไปทางเดียวกันเสมอ (backtest ระดับเทรนด์
                # 0.35 / 0.38 / 0.36 เทียบมัธยฐานคะแนนคีย์เวิร์ด 0.36 / - / 0.39 ต่างกันอยู่ในช่วงสุ่ม)
                g_trend = float(np.log((forecast["levels"][h - 1] + 1) / (forecast["base"] + 1)))
                m = market[h]
                s = ((m < g_trend).sum() + 0.5 * (m == g_trend).sum()) / len(m)
            else:
                s = ok[f"score_y{h}"].median() if len(ok) else np.nan
            rec[f"score_y{h}"] = None if np.isnan(s) else round(float(s), 4)
            rec[f"grade_y{h}"] = grade(rec[f"score_y{h}"])

        def mean(col):
            return float(ok[col].mean()) if len(ok) and col in ok and ok[col].notna().any() else np.nan

        rec["past_growth_pct"] = _pct_change(mean("last12_mean"), mean("prev12_mean"))
        rec["recent_change_pct"] = _pct_change(mean("recent_mean"), mean("year_ago_mean"))
        rec["recent_decline"] = bool(rec["recent_change_pct"] is not None
                                     and rec["recent_change_pct"] < float(np.expm1(DECLINE_THRESHOLD)) * 100)
        rec["forecast"] = forecast
        out.append(rec)
    return out


def expected_levels(ok, band=None):
    """ระดับที่คาดของดัชนีเทรนด์ (ค่าเฉลี่ยคีย์เวิร์ด) ในแต่ละปีของ HORIZONS จากค่าที่โมเดลทายต่อคีย์เวิร์ด:
    ระดับคีย์เวิร์ด = (ค่าเฉลี่ย 12 เดือนล่าสุด + 1) x exp(ค่าที่ทาย) - 1 แล้วเฉลี่ยทุกคำ (แบบเดียวกับดัชนีในกราฟ)
    คืน {"base", "levels", "change_pct", "low", "high"} (low/high = แถบ 80% ของโมเดลที่ใช้ - ไม่ระบุใช้ FORECAST_BAND_80) หรือ None"""
    band = band or FORECAST_BAND_80
    cols = ["last12_mean"] + [f"pred_y{h}" for h in HORIZONS]
    if not len(ok) or any(c not in ok for c in cols) or ok[cols].isna().any(axis=None):
        return None
    base = float(ok["last12_mean"].mean())
    levels = [float(((ok["last12_mean"] + 1) * np.exp(ok[f"pred_y{h}"]) - 1).mean()) for h in HORIZONS]
    return {"base": round(base, 2), "levels": [round(v, 2) for v in levels],
            "change_pct": [_pct_change(v, base) for v in levels],
            "low": [round((v + 1) * (1 + band[h][0]) - 1, 2) for h, v in zip(HORIZONS, levels)],
            "high": [round((v + 1) * (1 + band[h][1]) - 1, 2) for h, v in zip(HORIZONS, levels)]}


SEASONAL_YEARS = 4   # จำนวนปีเต็มที่ใช้หาจังหวะตามฤดูกาลของเทรนด์


def seasonal_factors(index, end=LAST_TRUSTED_MONTH, years=SEASONAL_YEARS):
    """🆕 (2026-09-30) จังหวะตามฤดูกาลของดัชนีเทรนด์: ตัวคูณต่อเดือนปฏิทิน (1-12, เฉลี่ย = 1) = ค่าเฉลี่ยของ (ค่าเดือนนั้น ÷
    ค่าเฉลี่ยของปีนั้น) ใน `years` ปีเต็มที่จบไม่เกิน `end` - ตัดช่วงข้อมูลกระโดด (หลัง LAST_TRUSTED_MONTH) ออก ไม่งั้น
    เดือนที่กระโดดจะถูกนับเป็นฤดูกาล
    backtest (15 เทรนด์ x 13 จุดตัด): เทรนด์ที่มีฤดูกาลชัด (กันแดด แกว่ง 70-109%) ค่ารายเดือนคลาดลดจาก 18.3% เหลือ 13.9%
    ในปีที่ 1 (ปีที่ 2 19.0 -> 17.5%, ปีที่ 3 21.3 -> 22.2%) เทรนด์ฤดูกาลอ่อนไม่ต่าง - คืน list 12 ค่า (ม.ค.-ธ.ค.) หรือ None"""
    s = index[index.index <= end].iloc[-12 * years:]
    if len(s) < 24:
        return None
    ratios = [(block / block.mean()).groupby(block.index.month).mean()
              for block in (s.iloc[12 * y:12 * (y + 1)] for y in range(len(s) // 12)) if block.mean() > 0]
    if not ratios:
        return None
    f = pd.concat(ratios, axis=1).mean(axis=1).reindex(range(1, 13)).fillna(1.0)
    return [round(float(v), 4) for v in f / f.mean()]


def cluster_history(series_by_keyword, kw, mapping, months=HISTORY_MONTHS):
    """ดัชนีการค้นหาจริงรายเดือนต่อเทรนด์ = ค่าเฉลี่ยของคีย์เวิร์ดที่ข้อมูลพอ (ไม่มีเลยใช้ทุกคำ) ย้อนหลัง months เดือน
    -> {ชื่อเทรนด์: {"months": ["2021-09", ...], "values": [...], "seasonal": [12 ตัวคูณ] | None}} ใช้วาดกราฟหน้าเทรนด์"""
    thin = dict(zip(kw["keyword"], kw["thin"].astype(bool)))
    out = {}
    for name, g in mapping.groupby("cluster_name", sort=True):
        words = [k for k in g["Keyword"] if k in series_by_keyword]
        use = [k for k in words if not thin.get(k, True)] or words
        if not use:
            continue
        full = pd.concat([series_by_keyword[k] for k in use], axis=1).mean(axis=1).sort_index()
        index = full.iloc[-months:]
        out[name] = {"months": [d.strftime("%Y-%m") for d in index.index], "values": [round(float(v), 2) for v in index],
                     "seasonal": seasonal_factors(full)}
    return out


def monthly_path(forecast, seasonal, as_of):
    """ค่ารายเดือนที่คาดทุกปีของ HORIZONS ถัดจาก as_of (5 ปี = 60 เดือน) = ระดับรายปีที่คาด x ตัวคูณฤดูกาลของเดือนนั้น
    (ค่าเฉลี่ยทั้งปีจึงเท่ากับระดับรายปีพอดี ตัวเลข "คาด +X%" ไม่เปลี่ยน) - ไม่มีจังหวะฤดูกาลใช้ระดับรายปีตรงๆ"""
    n = 12 * len(forecast["levels"])
    months = [as_of + pd.DateOffset(months=m) for m in range(1, n + 1)]
    values = [forecast["levels"][(m - 1) // 12] * (seasonal[d.month - 1] if seasonal else 1.0)
              for m, d in zip(range(1, n + 1), months)]
    return {"months": [d.strftime("%Y-%m") for d in months], "values": [round(float(v), 2) for v in values]}


def load_monthly(forecast_dir):
    """{คีย์เวิร์ด (ตัวเล็ก): อนุกรมรายเดือนดิบ} + ตารางคีย์เวิร์ด -> คลัสเตอร์ จากผล ⑦"""
    forecast_dir = Path(forecast_dir)
    monthly = pd.read_excel(forecast_dir / MONTHLY_FILE)
    monthly["Keyword"] = monthly["Keyword"].astype(str).str.strip().str.lower()
    monthly["start_date"] = pd.to_datetime(monthly["start_date"])
    series = {k: g.set_index("start_date")["search_avg"].astype(float).sort_index()
              for k, g in monthly.groupby("Keyword")}
    mapping = pd.read_excel(forecast_dir / KEYWORD_MAP_FILE, usecols=["Keyword", "cluster_name"]).drop_duplicates()
    mapping["Keyword"] = mapping["Keyword"].astype(str).str.strip().str.lower()
    return series, mapping


def compute_growth_scores(forecast_dir, last_trusted=LAST_TRUSTED_MONTH, model=None, pool_dir=None, cache_dir=None):
    """ฟังก์ชันหลัก: อ่านผล ⑦ -> โหลดโมเดล -> คะแนนการเติบโตต่อคีย์เวิร์ดและต่อเทรนด์ (dict ที่ serialize เป็น JSON ได้)
    model: "pool" = โมเดลล็อกจากชุดกลาง (growth_pool.py) / "per-run" = ฝึกจากคีย์เวิร์ดของรอบนี้ (วิธีเดิม)
    ไม่ระบุ = env GROWTH_MODEL แล้วค่าคงที่ GROWTH_MODEL ; pool_dir / cache_dir ใช้ในเทสต์"""
    mode = (model or os.environ.get("GROWTH_MODEL") or GROWTH_MODEL).strip().lower()
    if mode not in ("pool", "per-run"):
        raise ValueError(f"GROWTH_MODEL ต้องเป็น pool หรือ per-run (ได้ {mode!r})")
    series, mapping = load_monthly(forecast_dir)
    if mode == "pool":
        import growth_pool  # เรียกตอนใช้ - growth_pool import โมดูลนี้ จึงไม่ import วนที่ระดับบนสุด
        opts = {k: v for k, v in (("pool_dir", pool_dir), ("cache_dir", cache_dir)) if v is not None}
        frozen = growth_pool.frozen_model(last_trusted, **opts)
        models, n_train, n_samples, band = frozen["models"], frozen["n_train"], frozen["n_samples"], frozen["band"]
        model_info = {**frozen["info"], "run_keywords": len(series),
                      "run_keywords_in_pool": sum(1 for k in series if k in frozen["pool_keywords"])}
    else:
        samples = build_samples(series)
        models, n_train = train_models(samples, last_trusted)
        n_samples, band = len(samples), FORECAST_BAND_80
        model_info = {"mode": "per-run", "run_keywords": len(series), "trained_keywords": int(samples["keyword"].nunique())}
        if model_info["trained_keywords"] < MIN_RUN_KEYWORDS:
            model_info["warning"] = (f"ฝึกจากคีย์เวิร์ดของรอบนี้ {model_info['trained_keywords']} คำ (< {MIN_RUN_KEYWORDS}) "
                                     "- ตัวเลข % และอันดับไม่นิ่ง ควรใช้ GROWTH_MODEL=pool")
    if model_info.get("warning"):
        print(f"  ⚠️ {model_info['warning']}")
    kw = blend_scores(predict_keywords(series, models))
    as_of = max(s.index[-1] for s in series.values())
    if not BLEND_MOMENTUM and as_of >= MOMENTUM_CLEAN_FROM:
        print(f"  ℹ️ ข้อมูลถึง {as_of:%Y-%m} พ้นช่วงกระโดดของ cat=0 แล้ว - พิจารณาตั้ง growth_score.BLEND_MOMENTUM = True "
              "(แบบผสม momentum + โมเดล จัดอันดับได้ดีกว่าใน backtest)")
    history = cluster_history(series, kw, mapping)
    clusters = [{**c, "history": history.get(c["trend"])} for c in aggregate_clusters(kw, mapping, band)]
    for c in clusters:  # ค่ารายเดือนที่คาด (เส้นคลื่นในกราฟหน้าเทรนด์) = ระดับรายปี x จังหวะฤดูกาลก่อนช่วงข้อมูลกระโดด
        if c["forecast"] and c["history"]:
            c["forecast"]["monthly"] = monthly_path(c["forecast"], c["history"].get("seasonal"), as_of)
    keywords = kw.merge(mapping, left_on="keyword", right_on="Keyword", how="left").drop(columns=["Keyword", "as_of"])
    keywords = keywords.astype(object).where(keywords.notna(), None)
    return {
        "_note": "⑥ คะแนนการเติบโต (growth_score.py) - คะแนน 0-1 = percentile เทียบคีย์เวิร์ดทั้งหมดในรอบ, 0.5 = ค่ากลางตลาด",
        "as_of": as_of.strftime("%Y-%m"),
        "method": {
            "last_trusted_month": last_trusted.strftime("%Y-%m"),
            "score_method": "blend (momentum + model)" if BLEND_MOMENTUM else "model only",
            "horizons_months": {str(h): list(v) for h, v in HORIZONS.items()},
            "features": {str(h): v for h, v in MODEL_FEATURES.items()},
            "n_train": {str(h): n for h, n in n_train.items()},
            "n_samples": int(n_samples),
            "model": model_info,    # 🆕 (2026-10-29) โหมดโมเดล (pool / per-run) + ขนาดชุดฝึก + คำของรอบนี้ที่อยู่ในชุดกลาง
            "line": GROWTH_LINE, "grade_floors": list(GRADE_FLOORS),
            # 🆕 (2026-10-02) ช่วงคลาดเคลื่อน 80% ต่อปี (ผลจริง ÷ ที่ทาย - 1) - รายงาน ⑯ อ่านไปเขียนหมายเหตุ ไม่ต้องพิมพ์ตัวเลขซ้ำ
            "forecast_band_80": {str(h): list(band[h]) for h in HORIZONS},
            "recent_months": RECENT_MONTHS, "decline_threshold_pct": round(float(np.expm1(DECLINE_THRESHOLD)) * 100, 1),
        },
        "clusters": clusters,
        "keywords": keywords.to_dict(orient="records"),
    }


def save_growth_scores(result, out_dir):
    path = Path(out_dir) / OUTPUT_FILE
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return path
