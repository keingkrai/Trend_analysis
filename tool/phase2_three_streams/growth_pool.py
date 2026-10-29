# -*- coding: utf-8 -*-
"""
Phase 2 — ⑥ โมเดลล็อกจากชุดคีย์เวิร์ดกลาง (🆕 2026-10-29)

ปัญหาที่แก้: เดิม ⑥ ฝึกโมเดลใหม่ทุกรอบจากคีย์เวิร์ดของรอบนั้นเอง รอบสาย Search ส่งมาแค่ ~44 คำ (รอบเก่า ~145) ทำให้
  - % ที่คาดเพี้ยนตามชุดฝึก (รอบ 164405 ปีที่ 1 -10% ทั้ง 15 เทรนด์ ขณะที่รอบเก่า +8%)
  - อันดับไม่นิ่ง: โมเดล 2 ตัวที่ฝึกจากชุดสุ่ม 40 คำ อันดับของคำเดียวกันสอดคล้องกันแค่ 0.1-0.5 (Spearman) ต้อง >= 300 คำ
    จึงถึง 0.8 (ทดลอง 2026-10-29 บนชุด 517 คำ, walk-forward 2016-2024 กันคำทดสอบไว้ 100 คำ)
  - ชุด 40 คำแพ้ momentum ที่ปีที่ 3 และ 5 (0.30 vs 0.40, 0.31 vs 0.50) ชุดเต็มชนะที่ปีที่ 1 และ 3 (0.51 vs 0.38, 0.44 vs 0.40)

วิธีแก้: ฝึกครั้งเดียวจากชุดกลาง (growth_pool/pool_series.csv.gz = ค่าการค้นหารายเดือนของคีย์เวิร์ดจากทุกรอบที่เคยรัน)
แล้วให้ ⑥ โหลดโมเดลนั้นไปทายคีย์เวิร์ดของแต่ละรอบ - ทุกรอบใช้โมเดลเดียวกัน เทียบข้ามรอบได้ ไม่ขึ้นกับว่ารอบนั้นมีกี่คำ
  - โมเดลไม่ได้เก็บใน repo (ใหญ่) - ฝึกจากไฟล์ชุดกลางตอนใช้ครั้งแรกแล้วแคชไว้ที่ output/_checkpoints/growth_pool_models/
    (คีย์แคช = hash ของชุดกลาง + LAST_TRUSTED_MONTH + พารามิเตอร์/ฟีเจอร์ของโมเดล จึงฝึกใหม่เองเมื่อค่าใดค่าหนึ่งเปลี่ยน)
  - แถบ 80% (FORECAST_BAND_80) ของโมเดลนี้อยู่ใน growth_pool/pool_manifest.json คำนวณจาก walk-forward ที่ "กันคีย์เวิร์ดของรอบ
    ที่ทดสอบออกจากชุดฝึก" (เหมือนกรณีรอบใหม่ที่มีคำใหม่) - รันใหม่ด้วย --calibrate ทุกครั้งที่สร้างชุดกลางใหม่

คำสั่ง (รันจากโฟลเดอร์บนสุดของ repo):
  python tool/phase2_three_streams/growth_pool.py --status       ดูชุดกลางปัจจุบัน
  python tool/phase2_three_streams/growth_pool.py --build-pool   สร้างชุดกลางใหม่จาก output/*/serpapi_forecast_run (ทับของเดิม)
  python tool/phase2_three_streams/growth_pool.py --calibrate    คำนวณแถบ 80% + ความแม่นใหม่ ลงใน pool_manifest.json (~10 นาที)
  python tool/phase2_three_streams/growth_pool.py --warm         ฝึกโมเดลล่วงหน้าและแคช

เมื่อไหร่ควรสร้างชุดกลางใหม่: LAST_TRUSTED_MONTH ขยับ, ดึงข้อมูลแบบระบุหมวด (cat=143), หรือมีคีย์เวิร์ดใหม่สะสมเกิน ~20% ของชุด
ข้อจำกัด: ชุดกลางเป็นคีย์เวิร์ดด้านความงามทั้งหมด - ยังไม่ได้ทดสอบกับหัวข้ออื่น
"""
import argparse
import glob
import gzip
import hashlib
import json
import pickle
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import growth_score as gs  # noqa: E402

MAIN_DIR = HERE.parents[1]
OUTPUT_ROOT = MAIN_DIR / "output"
POOL_DIR = HERE / "growth_pool"
POOL_FILE = "pool_series.csv.gz"
MANIFEST_FILE = "pool_manifest.json"
CACHE_DIR = OUTPUT_ROOT / "_checkpoints" / "growth_pool_models"

MODEL_VERSION = 1            # เพิ่มเมื่อเปลี่ยนวิธีฝึกที่ไม่อยู่ในคีย์แคชอื่น (เช่น เปลี่ยนชนิดโมเดล)
MIN_POOL_KEYWORDS = 300      # ต่ำกว่านี้อันดับไม่นิ่ง (Spearman ข้ามชุดฝึก < 0.8) - ใช้เตือนทั้งชุดกลางและโหมดรายรอบ
FIRST_MONTH = pd.Timestamp("2008-01-01")   # คีย์เวิร์ดต้องมีข้อมูลตั้งแต่ปีนี้ (ตรงกับ SAMPLE_START)
# รอบที่ใช้คำนวณแถบ 80% (ตรงกับที่เคยใช้) - 15 เทรนด์ต่อรอบ
CALIBRATION_RUNS = ("beauty_and_personal_care_20260916_082438", "beauty_and_personal_care_20260925_111455")
EVAL_CUTOFFS = pd.date_range("2016-06-01", "2022-06-01", freq="6MS")   # จุดตัดเดียวกับ notebooks/backtest.ipynb (13 จุด)


# ---------------------------------------------------------------------------
# ชุดกลาง
# ---------------------------------------------------------------------------

def collect_run_series(output_root=OUTPUT_ROOT):
    """รวมอนุกรมรายเดือนดิบของ ⑦ จากทุกรอบ: คีย์เวิร์ดละ 1 อนุกรม (ตัวพิมพ์เล็ก) ใช้ไฟล์ที่ดึงล่าสุดถ้าซ้ำ
    ข้าม _backups (ซ้ำกับรอบจริง) และ trendspyg (สั้น เริ่ม 2021) - คืน (pool, [โฟลเดอร์ต้นทาง])"""
    best = {}
    pattern = str(Path(output_root) / "**" / "step5a_monthly_trends.xlsx")
    for f in sorted(glob.glob(pattern, recursive=True)):
        if "_backups" in f or "trendspyg" in f:
            continue
        df = pd.read_excel(f, usecols=["Keyword", "start_date", "search_avg"])
        df["Keyword"] = df["Keyword"].astype(str).str.strip().str.lower()
        df["start_date"] = pd.to_datetime(df["start_date"])
        for k, g in df.groupby("Keyword"):
            s = g.drop_duplicates("start_date").set_index("start_date")["search_avg"].astype(float).sort_index()
            key = (s.index[-1], len(s))
            if k not in best or key > best[k][0]:
                best[k] = (key, s, Path(f).relative_to(output_root).parts[0])
    pool = {k: v[1] for k, v in best.items() if v[1].index[0] <= FIRST_MONTH}
    used = sorted({best[k][2] for k in pool})
    return pool, used


def _pool_bytes(path):
    with gzip.open(path, "rb") as f:
        return f.read()


def pool_sha256(pool_dir=POOL_DIR):
    """hash ของเนื้อไฟล์ที่แตกแล้ว (ไม่ขึ้นกับเวลาที่บีบไฟล์)"""
    return hashlib.sha256(_pool_bytes(Path(pool_dir) / POOL_FILE)).hexdigest()


def save_pool(pool, sources, pool_dir=POOL_DIR):
    """เขียนชุดกลาง + manifest ใหม่ (แถบ 80%/ความแม่นเดิมถูกล้าง - ต้องรัน --calibrate ใหม่) คืน manifest"""
    pool_dir = Path(pool_dir)
    pool_dir.mkdir(parents=True, exist_ok=True)
    frames = [pd.DataFrame({"keyword": k, "month": s.index.strftime("%Y-%m-%d"), "search_avg": s.to_numpy()})
              for k, s in sorted(pool.items())]
    pd.concat(frames, ignore_index=True).to_csv(pool_dir / POOL_FILE, index=False, compression="gzip")
    months = [s.index for s in pool.values()]
    manifest = {
        "model_version": MODEL_VERSION,
        "built": date.today().isoformat(),
        "n_keywords": len(pool),
        "first_month": min(m[0] for m in months).strftime("%Y-%m"),
        "last_month": max(m[-1] for m in months).strftime("%Y-%m"),
        "sources": sources,
        "sha256": pool_sha256(pool_dir),
        "forecast_band_80": None,
        "backtest": None,
    }
    (pool_dir / MANIFEST_FILE).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def load_pool(pool_dir=POOL_DIR):
    """(pool, manifest) - ตรวจ hash กับ manifest: ถ้าไฟล์ถูกแก้โดยไม่ผ่าน --build-pool จะหยุด (กันโมเดลกับแถบ 80% ไม่ตรงกัน)"""
    pool_dir = Path(pool_dir)
    manifest = json.loads((pool_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    if manifest.get("sha256") != pool_sha256(pool_dir):
        raise ValueError(f"{POOL_FILE} ไม่ตรงกับ {MANIFEST_FILE} (hash ต่างกัน) - สร้างใหม่ด้วย growth_pool.py --build-pool")
    df = pd.read_csv(pool_dir / POOL_FILE, parse_dates=["month"])
    pool = {k: g.set_index("month")["search_avg"].astype(float).sort_index() for k, g in df.groupby("keyword")}
    return pool, manifest


# ---------------------------------------------------------------------------
# โมเดลล็อก (ฝึกจากชุดกลาง + แคช)
# ---------------------------------------------------------------------------

def cache_key(manifest, last_trusted):
    """ทุกอย่างที่ทำให้โมเดลต่างกัน - เปลี่ยนค่าใดค่าหนึ่งแคชเดิมจะไม่ถูกใช้"""
    spec = {"pool": manifest["sha256"], "last_trusted": str(pd.Timestamp(last_trusted).date()), "version": MODEL_VERSION,
            "sample_start": str(gs.SAMPLE_START.date()), "pit": gs.PIT_SCALING, "rf": gs.RF_PARAMS,
            "features": gs.MODEL_FEATURES, "horizons": {str(h): v for h, v in gs.HORIZONS.items()}}
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]


def band_from_manifest(manifest):
    """({ปี: (ต่ำ, สูง)}, ที่มา) - ถ้ายังไม่ได้คำนวณแถบของโมเดลนี้ ใช้ค่าของโมเดลรายรอบพร้อมบอกในผล"""
    raw = manifest.get("forecast_band_80")
    if raw:
        return {int(h): (float(v[0]), float(v[1])) for h, v in raw.items()}, "pool walk-forward"
    return dict(gs.FORECAST_BAND_80), "per-run default (ยังไม่ได้ --calibrate)"


def frozen_model(last_trusted=gs.LAST_TRUSTED_MONTH, pool_dir=POOL_DIR, cache_dir=CACHE_DIR, log=print):
    """{"models", "n_train", "n_samples", "band", "info"} - โหลดจากแคช ถ้าไม่มีฝึกใหม่จากชุดกลางแล้วบันทึก"""
    last_trusted = pd.Timestamp(last_trusted)
    pool, manifest = load_pool(pool_dir)
    key = cache_key(manifest, last_trusted)
    path = Path(cache_dir) / f"pool_{key}.pkl.gz"       # pickle ธรรมดา + gzip (joblib เตือนกับ numpy รุ่นใหม่) ; *.pkl อยู่ใน .gitignore
    cached = None
    if path.exists():
        try:
            with gzip.open(path, "rb") as f:
                cached = pickle.load(f)
        except Exception as e:  # แคชเสีย/ต่างเวอร์ชัน sklearn -> ฝึกใหม่
            log(f"  ⚠️ อ่านแคชโมเดลไม่ได้ ({e.__class__.__name__}) - ฝึกใหม่")
    if cached is None:
        log(f"  ⏳ ฝึกโมเดลล็อกจากชุดกลาง {len(pool)} คำ (ครั้งแรกใช้เวลาหลายนาที จากนั้นแคชไว้ที่ {path.parent})")
        samples = gs.build_samples(pool)
        models, n_train = gs.train_models(samples, last_trusted)
        cached = {"models": models, "n_train": n_train, "n_samples": int(len(samples)),
                  "n_keywords_trained": int(samples["keyword"].nunique())}
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wb", compresslevel=3) as f:
            pickle.dump(cached, f, protocol=pickle.HIGHEST_PROTOCOL)
    band, band_source = band_from_manifest(manifest)
    info = {"mode": "pool", "version": manifest.get("model_version", MODEL_VERSION), "pool_built": manifest["built"],
            "pool_keywords": manifest["n_keywords"], "pool_keywords_trained": cached["n_keywords_trained"],
            "pool_sha256": manifest["sha256"][:12], "cache_key": key, "band_source": band_source,
            "backtest": manifest.get("backtest")}
    if manifest["n_keywords"] < MIN_POOL_KEYWORDS:
        info["warning"] = f"ชุดกลางมี {manifest['n_keywords']} คำ (< {MIN_POOL_KEYWORDS}) อันดับอาจไม่นิ่ง"
    return {"models": cached["models"], "n_train": cached["n_train"], "n_samples": cached["n_samples"],
            "band": band, "info": info, "pool_keywords": set(pool)}


# ---------------------------------------------------------------------------
# แถบ 80% + ความแม่น (walk-forward, กันคีย์เวิร์ดของรอบที่ทดสอบออกจากชุดฝึก)
# ---------------------------------------------------------------------------

def calibrate(run_names=CALIBRATION_RUNS, pool_dir=POOL_DIR, output_root=OUTPUT_ROOT, cutoffs=EVAL_CUTOFFS, log=print):
    """ทดสอบแบบเดียวกับ notebooks/backtest.ipynb ส่วน 5.4: ทุกจุดตัด ฝึกด้วยเฉลยที่รู้ก่อนจุดตัด ทายคีย์เวิร์ดของรอบ
    แล้วรวมเป็นระดับดัชนีเทรนด์ (15 เทรนด์ต่อรอบ) - ผลจริง ÷ ที่ทาย ของดัชนีเทรนด์ -> เปอร์เซ็นไทล์ 10 / 90 = แถบ 80%
    ต่างจากเดิมที่คีย์เวิร์ดของรอบที่ทดสอบไม่อยู่ในชุดฝึก (คำใหม่ของรอบถัดไปก็ไม่อยู่ในชุดกลางเช่นกัน) แถบจึงกว้างกว่าเดิมเล็กน้อย
    คืน dict {"forecast_band_80", "level_err_pct", "spearman_keyword", "spearman_trend", "n_trend_points", ...}"""
    from sklearn.ensemble import RandomForestRegressor
    from scipy.stats import spearmanr

    pool, _ = load_pool(pool_dir)
    samples = gs.build_samples(pool)
    last_idx = gs._month_index(gs.LAST_TRUSTED_MONTH)
    trend_rows, kw_rho, trend_rho = [], [], []
    for run in run_names:
        series, mapping = gs.load_monthly(Path(output_root) / run / gs.FORECAST_DIR_NAME)
        test_kw = set(series)
        for h, (_, b) in gs.HORIZONS.items():
            feats, tgt = gs.MODEL_FEATURES[h], f"t_y{h}"
            for c in cutoffs:
                ci = gs._month_index(c)
                if ci + b > last_idx:                   # เฉลยปีที่ h ยังไม่จบก่อนช่วงข้อมูลที่เชื่อได้
                    continue
                tr = samples[(samples["month"] + b <= ci) & samples[tgt].notna() & ~samples["keyword"].isin(test_kw)]
                te = samples[(samples["month"] == ci) & samples["keyword"].isin(test_kw) & samples[tgt].notna()]
                if len(tr) < 100 or len(te) < 15:
                    continue
                model = RandomForestRegressor(**gs.RF_PARAMS).fit(tr[feats], tr[tgt])
                te = te.assign(pred=model.predict(te[feats]))
                kw_rho.append((h, spearmanr(te["pred"], te[tgt])[0]))
                merged = te.merge(mapping, left_on="keyword", right_on="Keyword")   # คำที่อยู่ 2 เทรนด์นับทั้งสอง
                rows = []
                for name, g in merged.groupby("cluster_name"):
                    base = g["past12"].mean()
                    rows.append({"horizon": h, "run": run, "cutoff": c, "cluster": name,
                                 "model": gs.log_growth(((g["past12"] + 1) * np.exp(g["pred"]) - 1).mean(), base),
                                 "actual": gs.log_growth(((g["past12"] + 1) * np.exp(g[tgt]) - 1).mean(), base)})
                trend_rows += rows
                if len(rows) >= 5:
                    trend_rho.append((h, spearmanr([r["model"] for r in rows], [r["actual"] for r in rows])[0]))
            log(f"  {run[-6:]} ปีที่ {h}: เสร็จ (จุดตัดสะสม {sum(1 for r in trend_rows if r['horizon'] == h) // 15})")
    tb = pd.DataFrame(trend_rows)
    ratio = np.expm1(tb["actual"] - tb["model"])
    out = {"forecast_band_80": {}, "level_err_pct": {}, "no_change_err_pct": {}, "above_forecast_pct": {},
           "spearman_keyword": {}, "spearman_trend": {}, "n_trend_points": {}}
    for h in gs.HORIZONS:
        r = ratio[tb["horizon"] == h]
        key = str(h)
        out["forecast_band_80"][key] = [round(float(r.quantile(0.10)), 2), round(float(r.quantile(0.90)), 2)]
        out["level_err_pct"][key] = round(100 * float(r.abs().median()), 1)
        out["no_change_err_pct"][key] = round(100 * float(np.expm1(tb.loc[tb["horizon"] == h, "actual"]).abs().median()), 1)
        out["above_forecast_pct"][key] = round(100 * float((r > 0).mean()), 0)
        out["spearman_keyword"][key] = round(float(np.mean([v for hh, v in kw_rho if hh == h])), 3)
        out["spearman_trend"][key] = round(float(np.mean([v for hh, v in trend_rho if hh == h])), 3)
        out["n_trend_points"][key] = int(len(r))
    out["method"] = ("walk-forward ทุก 6 เดือน 2016-06..2022-06 บน 2 รอบ (" + ", ".join(r[-6:] for r in run_names) +
                     "), กันคีย์เวิร์ดของรอบที่ทดสอบออกจากชุดฝึก, ระดับดัชนีเทรนด์")
    return out


def save_calibration(result, pool_dir=POOL_DIR):
    path = Path(pool_dir) / MANIFEST_FILE
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["forecast_band_80"] = result["forecast_band_80"]
    manifest["backtest"] = {k: v for k, v in result.items() if k != "forecast_band_80"}
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true", help="ดูชุดกลางปัจจุบัน")
    ap.add_argument("--build-pool", action="store_true", help="สร้างชุดกลางใหม่จากผลทุกรอบ (ทับของเดิม)")
    ap.add_argument("--calibrate", action="store_true", help="คำนวณแถบ 80%% + ความแม่นลง manifest")
    ap.add_argument("--warm", action="store_true", help="ฝึกโมเดลล่วงหน้าและแคช")
    a = ap.parse_args()
    if a.build_pool:
        pool, sources = collect_run_series()
        m = save_pool(pool, sources)
        print(f"✅ ชุดกลาง {m['n_keywords']} คำ ({m['first_month']}..{m['last_month']}) จาก {len(sources)} โฟลเดอร์ -> {POOL_DIR}")
        print("   ⚠️ แถบ 80% ถูกล้าง - รัน --calibrate ต่อ")
    if a.calibrate:
        result = calibrate()
        print("✅ แถบ 80%:", result["forecast_band_80"])
        print("   ความคลาดเคลื่อนมัธยฐาน (%):", result["level_err_pct"], "| ทายว่าไม่เปลี่ยน:", result["no_change_err_pct"])
        print("   Spearman คีย์เวิร์ด:", result["spearman_keyword"], "| เทรนด์:", result["spearman_trend"])
        print("   บันทึกที่", save_calibration(result))
    if a.warm:
        m = frozen_model()
        print("✅ โมเดลพร้อม:", m["info"], "| n_train", m["n_train"])
    if a.status or not (a.build_pool or a.calibrate or a.warm):
        pool, m = load_pool()
        print(f"ชุดกลาง {m['n_keywords']} คำ · {m['first_month']}..{m['last_month']} · สร้าง {m['built']} · sha {m['sha256'][:12]}")
        print("แถบ 80%:", m["forecast_band_80"] or "ยังไม่ได้ --calibrate", "| ความแม่น:", m["backtest"] or "-")


if __name__ == "__main__":
    main()
