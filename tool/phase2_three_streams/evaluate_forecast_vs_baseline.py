# -*- coding: utf-8 -*-
"""
Phase 2 (C1 audit finding) — ทดสอบว่าโมเดลพยากรณ์ที่ deploy จริงใน trend_final_v2.py (recursive
multi-step, horizon 3-36 เดือน) แม่นกว่า naive baseline จริงไหม ที่ horizon ที่ใช้งานจริง

ที่มา: Detail/05 งานที่ยังไม่ได้ทำ/แผนแก้ Data Science Audit.md ข้อ C1 - audit พบว่า holdout evaluation
เดิมใน forecast_trend() วัดความแม่นแบบ 1-step (ป้อน feature จากค่าจริงตรงๆ) แต่การพยากรณ์จริงที่ deploy
เป็น recursive (ป้อนค่าที่ทำนายได้กลับเป็น lag ของก้าวถัดไป) - คนละงานกัน ต้องทดสอบที่ horizon จริงถึงจะรู้

**ไม่แตะ trend_final_v2.py เลย** - เขียนเป็น evaluation harness แยกต่างหาก (กันความเสี่ยงกับโค้ด
production) แต่จำลองตรรกะ recursive forecast + feature set ให้ตรงกับต้นฉบับเป๊ะ (เทียบ FEATURE_COLS/
model spec กับ trend_final_v2.py:2206/2033-2036 แล้ว)

**ไม่ยิง SerpAPI เพิ่มเลย** - ใช้ step5b_df_keyword_processed.xlsx ที่มีอยู่แล้วจาก
output/legacy_flat_before_run_ids/serpapi_forecast_run/ (feature เดียวกับที่ trend_final_v2.py คำนวณไว้
แล้วจริง - ไฟล์นี้เป็น flat legacy จากก่อนมีระบบแยกผลตาม run_id (2026-09-11) จึงอ้างอิง path ตรงๆ ไม่ผ่าน
OUTPUTS ต่อรอบ - 🆕 2026-09-16 ชุด legacy ถูกจัดเข้าโฟลเดอร์เดียวแล้ว path จึงลึกขึ้นมา 1 ชั้น)

🆕 (2026-09-15) ชื่อไฟล์เดิมมีช่องว่างเกิน ("step5c_ df_..." ไม่ใช่ "step5c_df_...") เป็น typo ใน
trend_final_v2.py ที่แก้ไปแล้ว (ตัดช่องว่างออก) พร้อมเปลี่ยนชื่อไฟล์จริงที่มีอยู่แล้วให้ตรงกัน

Usage:
    python evaluate_forecast_vs_baseline.py
"""
import sys
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import TOOL_DIR  # noqa: E402

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from statsmodels.tsa.holtwinters import ExponentialSmoothing

# เหมือน trend_final_v2.py:2206 เป๊ะ (feature_cols)
FEATURE_COLS = ["lag_1", "lag_3", "lag_12", "rolling_mean_3m", "z_volatility_3m", "z_velocity"]
HORIZONS = [3, 6, 12]
# 🆕 (2026-09-16) ย้ายตามชุด legacy ที่ถูกจัดเข้าโฟลเดอร์เดียว (เดิมอยู่แบนๆ ที่ output/ ตรงๆ)
DATA_PATH = (TOOL_DIR.parent / "output" / "legacy_flat_before_run_ids" / "serpapi_forecast_run"
             / "step5b_df_keyword_processed.xlsx")


def _recursive_forecast(model, seed_df, horizon, future_dates):
    """เหมือน trend_final_v2.py:_recursive_forecast() เป๊ะ (บรรทัด 2004-2026) - ป้อนค่าที่ทำนายได้
    กลับเป็น lag ของก้าวถัดไปแบบ recursive ทีละก้าว (ไม่ใช่ป้อน feature จากค่าจริงเหมือน holdout เดิม)"""
    curr_df = seed_df.copy()
    forecast_vals = []
    for step in range(horizon):
        def get_lag(offset):
            return curr_df["z_score"].iloc[-offset] if len(curr_df) >= offset else 0
        vol = curr_df["z_score"].iloc[-3:].std() if len(curr_df) >= 3 else curr_df["z_score"].std()
        row = {
            "lag_1": get_lag(1), "lag_3": get_lag(3), "lag_12": get_lag(12),
            "rolling_mean_3m": curr_df["z_score"].iloc[-3:].mean() if len(curr_df) >= 3 else curr_df["z_score"].mean(),
            "z_volatility_3m": vol, "z_velocity": get_lag(1) - get_lag(3),
        }
        pred = model.predict(pd.DataFrame([row])[FEATURE_COLS])[0]
        forecast_vals.append(pred)
        new_row = curr_df.iloc[-1:].copy()
        new_row["start_date"] = future_dates[step]
        new_row["z_score"] = pred
        curr_df = pd.concat([curr_df, new_row], ignore_index=True)
    return np.array(forecast_vals)


def naive_baselines(train_series, horizon):
    """3 baseline ที่ audit เสนอ - ไม่ fit อะไรเลย คำนวณจากค่าจริงตรงๆ"""
    last = float(train_series.iloc[-1])
    persistence = np.full(horizon, last)

    if len(train_series) >= 12:
        seasonal = train_series.iloc[-12:].values[:horizon]
        if len(seasonal) < horizon:
            seasonal = np.concatenate([seasonal, np.full(horizon - len(seasonal), last)])
    else:
        seasonal = persistence.copy()

    slope = float(train_series.iloc[-1] - train_series.iloc[-2]) if len(train_series) >= 2 else 0.0
    drift = last + slope * np.arange(1, horizon + 1)

    return {"persistence": persistence, "seasonal_naive": seasonal, "drift": drift}


def rmse(pred, actual):
    return float(np.sqrt(np.mean((np.asarray(pred, dtype=float) - np.asarray(actual, dtype=float)) ** 2)))


def evaluate_one_series(g, horizon):
    """g: DataFrame ของ 1 kw_cluster_id เรียงตามวันที่แล้ว - คืน dict ผล RMSE ทุกวิธีที่ horizon นี้
    หรือ None ถ้าประวัติไม่พอ (ต้องการ train >= 8 แถวเสมอ เหมือน can_holdout ต้นฉบับ)"""
    if len(g) < horizon + 8:
        return None
    train_df = g.iloc[:-horizon].reset_index(drop=True)
    test_df = g.iloc[-horizon:]
    actual = test_df["z_score"].values
    future_dates = test_df["start_date"].tolist()

    out = {}
    for name, vals in naive_baselines(train_df["z_score"], horizon).items():
        out[name] = rmse(vals, actual)

    model_specs = {
        "RandomForest": lambda: RandomForestRegressor(n_estimators=200, random_state=42),
        "LinearRegression": lambda: LinearRegression(),
        "XGBoost": lambda: xgb.XGBRegressor(n_estimators=200, learning_rate=0.05, random_state=42),
    }
    for name, make in model_specs.items():
        try:
            model = make()
            model.fit(train_df[FEATURE_COLS], train_df["z_score"])
            fc = _recursive_forecast(model, train_df, horizon, future_dates)
            out[name] = rmse(fc, actual)
        except Exception:
            out[name] = None

    try:
        hw = ExponentialSmoothing(train_df["z_score"].values, trend="add", seasonal="add",
                                   seasonal_periods=12, initialization_method="estimated").fit()
        out["HoltWinters"] = rmse(hw.forecast(horizon), actual)
    except Exception:
        out["HoltWinters"] = None

    return out


if __name__ == "__main__":
    if not DATA_PATH.exists():
        raise SystemExit(f"❌ ไม่มี {DATA_PATH} - ต้องรัน ⑦ (fetch_trends_worldwide_serpapi.py) มาก่อน "
                          f"อย่างน้อย 1 ครั้งเพื่อได้ไฟล์ feature จริง")

    print("=" * 70)
    print("C1 audit — โมเดลพยากรณ์ที่ deploy จริง (recursive) vs naive baseline ที่ horizon จริง")
    print(f"ข้อมูล: {DATA_PATH.name}")
    print("=" * 70)

    df = pd.read_excel(DATA_PATH)
    df["start_date"] = pd.to_datetime(df["start_date"])

    method_names = ["persistence", "seasonal_naive", "drift", "RandomForest", "LinearRegression",
                     "XGBoost", "HoltWinters"]
    naive_names = {"persistence", "seasonal_naive", "drift"}
    ml_names = set(method_names) - naive_names

    all_rows = []
    for h in HORIZONS:
        print(f"\n--- horizon = {h} เดือน ---")
        n_tested, n_ml_beats_all_naive = 0, 0
        for kw_cluster_id, g in df.groupby("kw_cluster_id"):
            g = g.sort_values("start_date").reset_index(drop=True)
            res = evaluate_one_series(g, h)
            if res is None:
                continue
            n_tested += 1
            res["kw_cluster_id"] = kw_cluster_id
            res["cluster_name"] = g["cluster_name"].iloc[0]
            res["horizon"] = h
            all_rows.append(res)

            best_naive = min(res[n] for n in naive_names if res.get(n) is not None)
            best_ml = min((res[n] for n in ml_names if res.get(n) is not None), default=None)
            if best_ml is not None and best_ml < best_naive:
                n_ml_beats_all_naive += 1

        pct = round(100 * n_ml_beats_all_naive / n_tested, 1) if n_tested else 0.0
        print(f"  ทดสอบได้ {n_tested}/127 series (ประวัติพอ >= {h + 8} เดือน)")
        print(f"  ML โมเดลใดๆ ชนะ naive baseline ที่ดีที่สุด: {n_ml_beats_all_naive}/{n_tested} ({pct}%)")

    df_all = pd.DataFrame(all_rows)
    out_path = TOOL_DIR.parent / "output" / "phase2_c1_forecast_vs_baseline_result.json"
    df_all.to_json(out_path, orient="records", indent=2)

    print("\n" + "=" * 70)
    print("สรุปค่าเฉลี่ย RMSE ต่อวิธี ต่อ horizon (ยิ่งต่ำยิ่งดี):")
    print("=" * 70)
    summary = df_all.groupby("horizon")[method_names].mean(numeric_only=True).round(4)
    print(summary.to_string())
    print(f"\n💾 บันทึกผลเต็มลง {out_path}")
