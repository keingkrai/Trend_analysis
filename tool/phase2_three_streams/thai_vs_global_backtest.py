# -*- coding: utf-8 -*-
"""
Backtest: เทียบ Google Trends ไทย vs โลก ใช้ตอบ "เทรนด์ไหนกำลังจะมา" ได้จริงไหม

ดู Detail/05 งานที่ยังไม่ได้ทำ/Backlog และแนวทางต่อไป.md ข้อ 5 (แทร็กคีย์เวิร์ดไทย + ต่างประเทศคู่ขนาน)
- เคาะแนวทางไว้แล้วแต่ยังไม่เคยพิสูจน์ว่าได้ผลจริง สคริปต์นี้คือ test case ก่อนลงมือทำใน pipeline

## คำถามที่ต้องพิสูจน์ 2 ข้อ

A. **ไทยตามหลังโลกจริงไหม และกี่เดือน** - หาเดือนที่แต่ละเส้น "ติดลม" (onset) แล้วดูว่าไทยช้ากว่าโลกกี่เดือน
   ถ้าไทยไม่ได้ตามหลังโลกจริง สัญญาณโลกก็ใช้ทำนายไทยไม่ได้ แนวทางนี้ตกตั้งแต่ข้อนี้
B. **กรอบ 4 ช่อง ทำนายได้จริงไหม (walk-forward, ไม่มองอนาคต)** - ที่ cutoff ย้อนหลังหลายจุด จัดช่องด้วย
   ข้อมูล <= cutoff เท่านั้น แล้วไปดู 24 เดือนถัดไปว่าไทยขึ้นจริงไหม ถ้าช่อง "โลกโต x ไทยนิ่ง" ขึ้นจริงบ่อยกว่า
   ช่อง "โลกนิ่ง x ไทยนิ่ง" อย่างชัดเจน = สัญญาณโลกมีค่าในการตอบข้อ 2 จริง

## ทำไมใช้คำระดับส่วนผสม/รูปแบบสินค้า ไม่ใช่คลัสเตอร์จาก pipeline

ต้องการ ground truth ที่รู้ผลแล้ว = ต้องมีประวัติยาวหลายปี คลัสเตอร์จาก pipeline เป็นคำหางยาวที่ geo=TH ข้อมูล
ตายเกือบหมด (ดู Google Trends และ Geo.md) - ใส่คำที่ "ดังในโลกแล้วแต่ไม่มาไทย" ปนไว้ด้วย (jade roller, gua sha,
skin cycling, cbd ฯลฯ) และคำที่เอเชีย/ไทยนำ (glutathione, cushion, body serum) กันการเลือกแต่คำที่รู้อยู่แล้วว่าดัง

## ข้อจำกัดของข้อมูลที่ออกแบบรองรับไว้แล้ว

- ตัดข้อมูลที่ ก.ค. 2025 - Google Trends ผิดปกติพร้อมกันทุกคำตั้งแต่ ส.ค. 2025 (Google Trends และ Geo.md)
- ห้ามเทียบค่าดิบข้ามประเทศ (normalize แยกกันต่อ request) - ใช้แค่อัตราส่วนภายในเส้นเดียวกัน (scale-invariant)
- เส้นไทย = คำไทย + คำอังกฤษ ใน request เดียวกัน (scale เดียวกัน) แล้วบวกกัน - คนไทยค้นทั้งสองแบบ
- ดึงผ่าน pytrends (ฟรี) ไม่เสีย SerpAPI quota - cache ทุก request ไว้ใน output/_experiments/ รันซ้ำไม่ยิงใหม่

ใช้: python tool/phase2_three_streams/thai_vs_global_backtest.py            (ดึงที่ขาด + วิเคราะห์)
     python tool/phase2_three_streams/thai_vs_global_backtest.py --no-fetch (วิเคราะห์จาก cache อย่างเดียว)
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

TIMEFRAME_START = "2012-01-01"
TIMEFRAME_END = "2025-07-31"
OUT_DIR = Path(__file__).resolve().parents[2] / "output" / "_experiments" / "thai_vs_global"
CACHE_DIR = OUT_DIR / "cache"

RISING_RATIO = 1.3      # โต >= 30% เทียบ 12 เดือนก่อนหน้า = "โต"
SUCCESS_RATIO = 1.5     # 24 เดือนถัดไปเฉลี่ยสูงกว่า 12 เดือนล่าสุด >= 1.5 เท่า = "ไทยขึ้นจริง"
SUCCESS_MIN_LEVEL = 5   # และต้องเฉลี่ย >= 5 (จาก 100) กันกรณีขยับจาก 0 เป็น 1-2 แบบ noise
OUTCOME_MONTHS = 24
CUTOFFS = [f"{y}-01-01" for y in range(2017, 2024)]  # 24 เดือนหลัง cutoff สุดท้ายจบก่อน ส.ค. 2025
ONSET_FRAC = 0.25       # onset = เดือนแรกที่ค่าเฉลี่ย 3 เดือนแตะ 25% ของจุดสูงสุดของเส้นนั้น
ONSET_HOLD = 6          # และค่าเฉลี่ย 6 เดือนถัดไปต้องยังอยู่เหนือระดับนั้น (ไม่ใช่แค่ spike)
MIN_NONZERO_MONTHS = 12
BOOTSTRAP_ITERS = 2000

# (ชื่อ, คำค้นโลก, [คำค้นไทยที่รวมกันเป็นเส้นไทย]) - ชื่อใช้เป็น key ทุกที่
CASES = [
    ("niacinamide", "niacinamide", ["ไนอะซินาไมด์", "niacinamide"]),
    ("ceramide", "ceramide", ["เซราไมด์", "ceramide"]),
    ("hyaluronic acid", "hyaluronic acid", ["ไฮยาลูรอน", "hyaluronic"]),
    ("retinol", "retinol", ["เรตินอล", "retinol"]),
    ("micellar water", "micellar water", ["ไมเซล่า", "micellar"]),
    ("cica", "cica", ["ซิก้า", "cica"]),
    ("snail mucin", "snail mucin", ["ครีมหอยทาก", "snail cream"]),
    ("bakuchiol", "bakuchiol", ["บาคูชิออล", "bakuchiol"]),
    ("tranexamic acid", "tranexamic acid", ["ทรานเอกซามิค", "tranexamic"]),
    ("azelaic acid", "azelaic acid", ["อะเซลาอิก", "azelaic"]),
    ("squalane", "squalane", ["สควาเลน", "squalane"]),
    ("salicylic acid", "salicylic acid", ["ซาลิไซลิก", "salicylic"]),
    ("vitamin c serum", "vitamin c serum", ["เซรั่มวิตามินซี", "vitamin c serum"]),
    ("glutathione", "glutathione", ["กลูต้า", "glutathione"]),
    ("cushion foundation", "cushion foundation", ["คุชชั่น", "cushion foundation"]),
    ("sunscreen stick", "sunscreen stick", ["กันแดดแท่ง", "sunscreen stick"]),
    ("cbd cream", "cbd cream", ["ครีมกัญชง", "cbd cream"]),
    ("jade roller", "jade roller", ["ลูกกลิ้งหยก", "jade roller"]),
    ("gua sha", "gua sha", ["กัวซา", "gua sha"]),
    ("skin cycling", "skin cycling", ["สกินไซคลิ่ง", "skin cycling"]),
    ("glass skin", "glass skin", ["ผิวกระจก", "glass skin"]),
    ("rosemary oil", "rosemary oil", ["น้ำมันโรสแมรี่", "rosemary oil"]),
    ("peptide serum", "peptide serum", ["เซรั่มเปปไทด์", "peptide serum"]),
    ("mineral sunscreen", "mineral sunscreen", ["กันแดดฟิสิคอล", "mineral sunscreen"]),
    ("postbiotic", "postbiotic", ["โพสไบโอติก", "postbiotic"]),
    ("scalp serum", "scalp serum", ["เซรั่มหนังศีรษะ", "scalp serum"]),
    ("skin barrier", "skin barrier", ["เกราะป้องกันผิว", "skin barrier"]),
    ("body serum", "body serum", ["เซรั่มทาผิว", "body serum"]),
    ("exosome", "exosome", ["เอ็กโซโซม", "exosome"]),
    ("pdrn", "pdrn", ["pdrn", "แซลมอนดีเอ็นเอ"]),
]


def month_index():
    return pd.date_range(TIMEFRAME_START, TIMEFRAME_END, freq="MS")


def cache_path(terms, geo):
    key = hashlib.md5(f"{geo}|{'|'.join(terms)}|{TIMEFRAME_START}|{TIMEFRAME_END}".encode("utf-8")).hexdigest()[:12]
    return CACHE_DIR / f"{geo or 'WW'}_{key}.csv"


def load_cached(terms, geo):
    path = cache_path(terms, geo)
    if not path.exists():
        return None
    return pd.read_csv(path, index_col=0, parse_dates=True)["value"]


def fetch_series(terms, geo):
    """ดึง 1 request (terms <= 5 คำ scale เดียวกัน) แล้วบวกรวมเป็นเส้นเดียว - cache ลงไฟล์ทันทีที่ได้

    ⚠️ เปิด TrendReq ใหม่ทุก request - ใช้ session ร่วมกันแล้ว request geo="" ที่ตามหลัง geo="TH" ได้ข้อมูล
    ไทยกลับมาแทนข้อมูลโลก (เจอจริงรอบแรก: 12/30 คำเส้น "โลก" ซ้ำกับเส้นไทย 83-100% ของเดือน - ยืนยันแล้วว่า
    session ใหม่ได้ข้อมูลโลกจริง) ทั้งที่ไม่มี error อะไรเลย
    """
    from pytrends.request import TrendReq
    cached = load_cached(terms, geo)
    if cached is not None:
        return cached, "cache"
    df = None
    for wait in [0, 30, 90, 180]:
        if wait:
            print(f"      รอ {wait} วินาทีก่อนลองใหม่...")
            time.sleep(wait)
        try:
            pytrends = TrendReq(hl="en-US", tz=420, timeout=(10, 30))
            pytrends.build_payload(terms, timeframe=f"{TIMEFRAME_START} {TIMEFRAME_END}", geo=geo)
            df = pytrends.interest_over_time()
            break
        except Exception as e:
            print(f"      ⚠️ {type(e).__name__}: {str(e)[:120]}")
    if df is None:
        return None, "failed"
    if df.empty:
        # Google ตอบกลับมาว่าไม่มีข้อมูลเลย = ความสนใจเป็น 0 ทั้งช่วง (ผลจริง ไม่ใช่ error)
        series = pd.Series(0.0, index=month_index())
    else:
        series = df[[c for c in df.columns if c != "isPartial"]].sum(axis=1).astype(float)
        series.index = pd.to_datetime(series.index)
        series = series.reindex(month_index()).fillna(0.0)
    series.rename("value").to_frame().to_csv(cache_path(terms, geo))
    return series, "fetched"


def load_all(fetch=True):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data, missing = {}, []
    for name, global_term, th_terms in CASES:
        pair = {}
        for side, terms, geo in [("global", [global_term], ""), ("th", th_terms, "TH")]:
            if fetch:
                series, how = fetch_series(terms, geo)
                print(f"  {name:20s} {side:6s} {how}")
                if how == "fetched":
                    time.sleep(8)
            else:
                series = load_cached(terms, geo)
            if series is None:
                missing.append(f"{name}/{side}")
            pair[side] = series
        if pair["global"] is not None and pair["th"] is not None:
            data[name] = pair
    return data, missing


def smooth(s):
    return s.rolling(3, min_periods=1).mean()


def onset_month(s):
    """เดือนแรกที่เส้น "ติดลม" จริง (ไม่ใช่ spike เดียว) - None ถ้าไม่เคยติดลม"""
    sm = smooth(s)
    level = ONSET_FRAC * sm.max()
    if level <= 0:
        return None
    for i in range(len(sm) - ONSET_HOLD):
        if sm.iloc[i] >= level and sm.iloc[i:i + ONSET_HOLD].mean() >= level:
            return sm.index[i]
    return None


def months_between(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


def proof_a_onset_lag(data):
    """A: ไทยติดลมช้ากว่าโลกกี่เดือน"""
    rows = []
    first_month = month_index()[0]
    for name, pair in data.items():
        g_on, t_on = onset_month(pair["global"]), onset_month(pair["th"])
        th_nonzero = int((pair["th"] > 0).sum())
        status = "ok"
        if th_nonzero < MIN_NONZERO_MONTHS:
            status = "ไทยข้อมูลน้อยเกินไป"
        elif g_on is None or t_on is None:
            status = "ไม่พบ onset"
        elif months_between(first_month, g_on) < 12 or months_between(first_month, t_on) < 12:
            status = "ติดลมก่อนปี 2013 (ก่อนช่วงข้อมูล วัด lag ไม่ได้)"
        rows.append({
            "name": name,
            "global_onset": g_on.strftime("%Y-%m") if g_on is not None else None,
            "th_onset": t_on.strftime("%Y-%m") if t_on is not None else None,
            "lag_months": months_between(g_on, t_on) if status == "ok" else None,
            "th_nonzero_months": th_nonzero,
            "status": status,
        })
    df = pd.DataFrame(rows)
    valid = df[df["status"] == "ok"]
    lags = valid["lag_months"].astype(int)
    summary = {
        "n_terms": len(df),
        "n_valid": len(valid),
        "median_lag_months": float(lags.median()) if len(lags) else None,
        "iqr_lag_months": [float(lags.quantile(0.25)), float(lags.quantile(0.75))] if len(lags) else None,
        "n_thai_follows (lag > 3)": int((lags > 3).sum()),
        "n_simultaneous (|lag| <= 3)": int((lags.abs() <= 3).sum()),
        "n_thai_leads (lag < -3)": int((lags < -3).sum()),
    }
    return df, summary


def growth_ratio(s, t_idx, before=12, gap=12):
    """ค่าเฉลี่ย `before` เดือนล่าสุด / ค่าเฉลี่ยช่วงก่อนหน้า (ใช้ข้อมูล <= t_idx เท่านั้น) - +1 กันหารศูนย์"""
    last = s.iloc[t_idx - before + 1: t_idx + 1].mean()
    prev = s.iloc[t_idx - before - gap + 1: t_idx - gap + 1].mean()
    return (last + 1) / (prev + 1)


def classify(g_ratio, t_ratio):
    g_up, t_up = g_ratio >= RISING_RATIO, t_ratio >= RISING_RATIO
    if g_up and not t_up:
        return "โลกโต x ไทยนิ่ง (หน้าต่างโอกาส)"
    if g_up and t_up:
        return "โลกโต x ไทยโต (กำลังมาถึง)"
    if t_up:
        return "โลกนิ่ง x ไทยโต (ไทยนำเอง)"
    return "โลกนิ่ง x ไทยนิ่ง"


def proof_b_points(data, cutoffs=CUTOFFS):
    idx = month_index()
    rows = []
    for cutoff in cutoffs:
        t_idx = idx.get_loc(pd.Timestamp(cutoff))
        for name, pair in data.items():
            g, th = pair["global"], pair["th"]
            last12 = th.iloc[t_idx - 11: t_idx + 1].mean()
            future = th.iloc[t_idx + 1: t_idx + 1 + OUTCOME_MONTHS].mean()
            g_ratio, t_ratio = growth_ratio(g, t_idx), growth_ratio(th, t_idx)
            fut_ratio = (future + 1) / (last12 + 1)
            rows.append({
                "cutoff": cutoff[:7], "name": name,
                "global_growth": round(g_ratio, 3), "th_growth": round(t_ratio, 3),
                "box": classify(g_ratio, t_ratio),
                "th_future_ratio": round(fut_ratio, 3), "th_future_level": round(future, 2),
                "th_rose": bool(fut_ratio >= SUCCESS_RATIO and future >= SUCCESS_MIN_LEVEL),
            })
    return pd.DataFrame(rows)


def auc(scores, labels):
    """AUC แบบ Mann-Whitney - โอกาสที่จุดที่ไทยขึ้นจริงมี global_growth สูงกว่าจุดที่ไม่ขึ้น"""
    labels = np.asarray(labels, dtype=bool)
    if labels.all() or (~labels).all():
        return None
    ranks = pd.Series(scores).rank().values
    n_pos, n_neg = labels.sum(), (~labels).sum()
    return float((ranks[labels].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def cluster_bootstrap(points, stat_fn, iters=BOOTSTRAP_ITERS, seed=42):
    """สุ่มทีละ "คำ" (ไม่ใช่ทีละจุด) เพราะจุดของคำเดียวกันข้าม cutoff ไม่อิสระต่อกัน"""
    rng = np.random.default_rng(seed)
    names = points["name"].unique()
    groups = {n: points[points["name"] == n] for n in names}
    stats = []
    for _ in range(iters):
        sample = pd.concat([groups[n] for n in rng.choice(names, size=len(names), replace=True)])
        v = stat_fn(sample)
        if v is not None and not np.isnan(v):
            stats.append(v)
    if not stats:
        return None
    return [round(float(np.percentile(stats, 2.5)), 3), round(float(np.percentile(stats, 97.5)), 3)]


def hit_rate(points, box):
    sub = points[points["box"] == box]
    return sub["th_rose"].mean() if len(sub) else np.nan


def proof_b_summary(points, onsets):
    WINDOW, NOTHING = "โลกโต x ไทยนิ่ง (หน้าต่างโอกาส)", "โลกนิ่ง x ไทยนิ่ง"
    by_box = (points.groupby("box")
              .agg(n_points=("th_rose", "size"), n_terms=("name", "nunique"),
                   th_rose_rate=("th_rose", "mean"), median_future_ratio=("th_future_ratio", "median"))
              .round(3).reset_index())
    diff = hit_rate(points, WINDOW) - hit_rate(points, NOTHING)
    diff_ci = cluster_bootstrap(points, lambda p: hit_rate(p, WINDOW) - hit_rate(p, NOTHING))

    # เฉพาะจุดที่ไทยยังนิ่ง (คำถามข้อ 2 ตรงตัว): การเติบโตของโลกแยกจุดที่ไทยจะขึ้นออกจากจุดที่ไม่ขึ้นได้ไหม
    th_flat = points[points["th_growth"] < RISING_RATIO]
    auc_flat = auc(th_flat["global_growth"], th_flat["th_rose"])
    auc_ci = cluster_bootstrap(th_flat, lambda p: auc(p["global_growth"].values, p["th_rose"].values))

    # เผื่อเวลาเท่าไหร่: จากวันที่จัดเข้าช่องหน้าต่างโอกาส ถึงวันที่ไทยติดลมจริง
    onset_by_name = {r["name"]: r["th_onset"] for r in onsets.to_dict("records") if r["th_onset"]}
    lead_times = []
    for r in points[(points["box"] == WINDOW) & points["th_rose"]].to_dict("records"):
        on = onset_by_name.get(r["name"])
        if on and pd.Timestamp(on) > pd.Timestamp(r["cutoff"]):
            lead_times.append(months_between(pd.Timestamp(r["cutoff"]), pd.Timestamp(on)))

    # ความไวต่อเกณฑ์: ผลต้องไม่พลิกเมื่อขยับเกณฑ์ "ไทยขึ้นจริง"
    sensitivity = []
    for ratio in [1.3, 1.5, 2.0]:
        for min_level in [3, 5, 10]:
            p = points.copy()
            p["th_rose"] = (p["th_future_ratio"] >= ratio) & (p["th_future_level"] >= min_level)
            sensitivity.append({"success_ratio": ratio, "min_level": min_level,
                                "window_rate": round(hit_rate(p, WINDOW), 3),
                                "nothing_rate": round(hit_rate(p, NOTHING), 3)})
    return {
        "by_box": by_box.to_dict("records"),
        "window_minus_nothing": round(float(diff), 3),
        "window_minus_nothing_95ci": diff_ci,
        "auc_global_growth_among_thai_flat": round(auc_flat, 3) if auc_flat is not None else None,
        "auc_95ci": auc_ci,
        "n_thai_flat_points": len(th_flat),
        "window_hit_lead_time_months": {
            "n": len(lead_times),
            "median": float(np.median(lead_times)) if lead_times else None,
            "range": [int(min(lead_times)), int(max(lead_times))] if lead_times else None,
        },
        "sensitivity": sensitivity,
    }


def current_snapshot(data):
    """ใช้กรอบเดียวกันกับเดือนล่าสุดที่ข้อมูลยังเชื่อได้ (ก.ค. 2025) - ยังไม่รู้ผล เป็นแค่ตัวอย่างว่าจะออกมาหน้าตาแบบไหน"""
    t_idx = len(month_index()) - 1
    rows = []
    for name, pair in data.items():
        g_ratio, t_ratio = growth_ratio(pair["global"], t_idx), growth_ratio(pair["th"], t_idx)
        rows.append({"name": name, "global_growth": round(g_ratio, 2), "th_growth": round(t_ratio, 2),
                     "box": classify(g_ratio, t_ratio)})
    return pd.DataFrame(rows).sort_values(["box", "global_growth"], ascending=[True, False])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-fetch", action="store_true", help="วิเคราะห์จาก cache อย่างเดียว ไม่ยิง Google Trends")
    args = parser.parse_args()

    print("=" * 70)
    print(f"Thai vs Global backtest - {len(CASES)} คำ, ข้อมูล {TIMEFRAME_START} ถึง {TIMEFRAME_END}")
    print("=" * 70)
    data, missing = load_all(fetch=not args.no_fetch)
    print(f"\nได้ข้อมูลครบทั้งสองเส้น {len(data)}/{len(CASES)} คำ" + (f" | ขาด: {missing}" if missing else ""))

    # ด่านกันบั๊ก geo รั่วข้าม session ซ้ำ: เส้นโลกกับเส้นไทยมาจากคนละ request ไม่ควรเท่ากันเป๊ะเกินครึ่ง
    leaked = [n for n, p in data.items() if (p["global"].values == p["th"].values).mean() > 0.5]
    if leaked:
        print(f"❌ เส้นโลกซ้ำกับเส้นไทยเกิน 50% ของเดือน (น่าจะ geo รั่ว): {leaked} - ลบ cache ของคำเหล่านี้แล้วรันใหม่")
        sys.exit(1)
    if len(data) < 10:
        print("❌ ข้อมูลน้อยเกินกว่าจะสรุปอะไรได้ หยุดที่นี่ (รันซ้ำเพื่อดึงส่วนที่ขาด - cache เก็บของที่ได้แล้ว)")
        sys.exit(1)

    onsets, summary_a = proof_a_onset_lag(data)
    print("\n[A] ไทยติดลมช้ากว่าโลกกี่เดือน")
    print(onsets.to_string(index=False))
    print(json.dumps(summary_a, ensure_ascii=False, indent=2))

    points = proof_b_points(data)
    summary_b = proof_b_summary(points, onsets)
    print(f"\n[B] Walk-forward {len(CUTOFFS)} cutoff x {len(data)} คำ = {len(points)} จุด")
    print(pd.DataFrame(summary_b["by_box"]).to_string(index=False))
    print(json.dumps({k: v for k, v in summary_b.items() if k != "by_box"}, ensure_ascii=False, indent=2))

    snapshot = current_snapshot(data)
    print("\n[ตัวอย่าง] จัดช่อง ณ ก.ค. 2025")
    print(snapshot.to_string(index=False))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    onsets.to_csv(OUT_DIR / "onset_lag.csv", index=False, encoding="utf-8-sig")
    points.to_csv(OUT_DIR / "backtest_points.csv", index=False, encoding="utf-8-sig")
    snapshot.to_csv(OUT_DIR / "snapshot_2025_07.csv", index=False, encoding="utf-8-sig")
    with open(OUT_DIR / "result.json", "w", encoding="utf-8") as f:
        json.dump({
            "_note": "Backtest ไทย vs โลก (Backlog ข้อ 5) - pytrends, ข้อมูลถึง ก.ค. 2025",
            "timeframe": [TIMEFRAME_START, TIMEFRAME_END], "cutoffs": CUTOFFS,
            "thresholds": {"rising_ratio": RISING_RATIO, "success_ratio": SUCCESS_RATIO,
                           "success_min_level": SUCCESS_MIN_LEVEL, "outcome_months": OUTCOME_MONTHS,
                           "onset_frac": ONSET_FRAC, "onset_hold": ONSET_HOLD},
            "missing": missing, "proof_a": summary_a, "proof_b": summary_b,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nบันทึกผลที่ {OUT_DIR}")
