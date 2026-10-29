# -*- coding: utf-8 -*-
"""⑥ โมเดลล็อกจากชุดคีย์เวิร์ดกลาง (growth_pool.py, 🆕 2026-10-29) - ไม่เรียก API ใช้ข้อมูลสังเคราะห์เล็กๆ

รัน: pytest tool/tests/test_growth_pool.py -v
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase2_three_streams"))

import numpy as np
import pandas as pd
import pytest

import growth_pool as gp
import growth_score as gs


def _pool(n=10, seed=3):
    """ชุดกลางปลอม: n คำ รายเดือน 2004-01..2026-08 โตคนละอัตรา + ฤดูกาล"""
    months = pd.date_range("2004-01-01", "2026-08-01", freq="MS")
    rng = np.random.default_rng(seed)
    out = {}
    for k in range(n):
        level = 30 * np.exp(0.002 * (k % 5 - 2) * np.arange(len(months))) * (1 + 0.15 * np.sin(np.arange(len(months)) / 12 * 2 * np.pi))
        out[f"kw{k}"] = pd.Series(np.clip(level + rng.normal(0, 3, len(months)), 0, 100).round(), index=months)
    return out


def _synthetic_run(tmp_path, pool):
    """ผล ⑦ ปลอมที่ใช้คีย์เวิร์ดเดียวกับชุดกลาง (kw0..kw9 อยู่ใน 2 เทรนด์)"""
    rows = [{"Keyword": k, "start_date": d, "search_avg": v} for k, s in pool.items() for d, v in s.items()]
    pd.DataFrame(rows).to_excel(tmp_path / gs.MONTHLY_FILE, index=False)
    pd.DataFrame([{"Keyword": k, "cluster_name": f"Trend {i % 2}"} for i, k in enumerate(pool)]).to_excel(
        tmp_path / gs.KEYWORD_MAP_FILE, index=False)
    return tmp_path


def test_real_pool_matches_its_manifest_and_is_big_enough():
    pool, manifest = gp.load_pool()                       # ตรวจ hash ในตัว
    assert len(pool) == manifest["n_keywords"] >= gp.MIN_POOL_KEYWORDS
    assert all(s.index[0] <= gp.FIRST_MONTH and s.index.is_monotonic_increasing for s in pool.values())
    assert all(k == k.lower() for k in pool)              # ชื่อคำเป็นตัวพิมพ์เล็กเหมือน load_monthly


def test_save_and_load_roundtrip_and_tamper_check(tmp_path):
    pool = _pool(4)
    manifest = gp.save_pool(pool, ["run_a"], tmp_path)
    loaded, m2 = gp.load_pool(tmp_path)
    assert manifest["n_keywords"] == 4 and m2["sources"] == ["run_a"] and manifest["forecast_band_80"] is None
    assert sorted(loaded) == sorted(pool)
    pd.testing.assert_series_equal(loaded["kw1"], pool["kw1"], check_names=False, check_freq=False)
    # แก้ไฟล์ชุดกลางโดยไม่ผ่าน --build-pool -> hash ไม่ตรง ต้องหยุด (กันโมเดลกับแถบ 80% ไม่ตรงกัน)
    gp.save_pool(_pool(4, seed=9), ["run_a"], tmp_path / "other")
    (tmp_path / gp.POOL_FILE).write_bytes((tmp_path / "other" / gp.POOL_FILE).read_bytes())
    with pytest.raises(ValueError, match="hash"):
        gp.load_pool(tmp_path)


def test_cache_key_changes_with_pool_and_last_trusted(tmp_path):
    m = gp.save_pool(_pool(4), [], tmp_path)
    a = gp.cache_key(m, "2025-06-01")
    assert a == gp.cache_key(m, pd.Timestamp("2025-06-01"))
    assert a != gp.cache_key(m, "2024-06-01")
    assert a != gp.cache_key({**m, "sha256": "x" * 64}, "2025-06-01")


def test_band_from_manifest_prefers_calibrated_band():
    band, source = gp.band_from_manifest({"forecast_band_80": {"1": [-0.2, 0.3], "5": [-0.4, 0.9]}})
    assert band[1] == (-0.2, 0.3) and band[5] == (-0.4, 0.9) and source == "pool walk-forward"
    band, source = gp.band_from_manifest({"forecast_band_80": None})
    assert band == gs.FORECAST_BAND_80 and "calibrate" in source


def test_frozen_model_trains_once_then_loads_from_cache(tmp_path, monkeypatch):
    gp.save_pool(_pool(10), ["run_a"], tmp_path / "pool")
    calls = []
    real = gs.train_models
    monkeypatch.setattr(gs, "train_models", lambda *a, **k: calls.append(1) or real(*a, **k))
    first = gp.frozen_model("2025-06-01", tmp_path / "pool", tmp_path / "cache", log=lambda *_: None)
    second = gp.frozen_model("2025-06-01", tmp_path / "pool", tmp_path / "cache", log=lambda *_: None)
    assert len(calls) == 1                                          # ครั้งที่ 2 โหลดแคช
    assert first["n_train"] == second["n_train"] and sorted(second["models"]) == [1, 2, 3, 4, 5]
    assert first["info"]["mode"] == "pool" and "ชุดกลางมี 10 คำ" in first["info"]["warning"]   # < 300 คำ เตือน
    gp.frozen_model("2024-06-01", tmp_path / "pool", tmp_path / "cache", log=lambda *_: None)
    assert len(calls) == 2                                          # LAST_TRUSTED_MONTH เปลี่ยน -> ฝึกใหม่


def test_pool_mode_scores_use_the_frozen_model_and_manifest_band(tmp_path):
    pool = _pool(10)
    gp.save_pool(pool, ["run_a"], tmp_path / "pool")
    manifest_path = tmp_path / "pool" / gp.MANIFEST_FILE
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["forecast_band_80"] = {str(h): [-0.5, 1.0] for h in gs.HORIZONS}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "run").mkdir()
    run = _synthetic_run(tmp_path / "run", pool)
    result = gs.compute_growth_scores(run, model="pool", pool_dir=tmp_path / "pool", cache_dir=tmp_path / "cache")
    info = result["method"]["model"]
    assert info["mode"] == "pool" and info["run_keywords"] == 10 and info["run_keywords_in_pool"] == 10
    assert info["band_source"] == "pool walk-forward"
    assert result["method"]["forecast_band_80"]["3"] == [-0.5, 1.0]            # แถบของโมเดล pool ไม่ใช่ FORECAST_BAND_80
    c = result["clusters"][0]
    lo, mid, hi = c["forecast"]["low"][0], c["forecast"]["levels"][0], c["forecast"]["high"][0]
    # ระดับที่คาดถูกปัดทศนิยม 2 ตำแหน่งก่อนแสดง จึงเทียบแบบมีความคลาดเคลื่อนเล็กน้อย
    assert lo == pytest.approx((mid + 1) * 0.5 - 1, abs=0.02) and hi == pytest.approx((mid + 1) * 2.0 - 1, abs=0.02)
    assert result["method"]["n_samples"] > 1000 and len(result["keywords"]) == 10


def test_pool_mode_scores_same_keywords_the_same_way_every_run(tmp_path):
    """ข้อดีของโมเดลล็อก: คีย์เวิร์ดเดียวกันได้คำทายเท่าเดิมไม่ว่ารอบนั้นมีคำอื่นมาด้วยกี่คำ"""
    pool = _pool(10)
    gp.save_pool(pool, [], tmp_path / "pool")
    (tmp_path / "small").mkdir()
    (tmp_path / "big").mkdir()
    small = gs.compute_growth_scores(_synthetic_run(tmp_path / "small", {k: pool[k] for k in ["kw0", "kw1", "kw2"]}),
                                     model="pool", pool_dir=tmp_path / "pool", cache_dir=tmp_path / "cache")
    big = gs.compute_growth_scores(_synthetic_run(tmp_path / "big", pool), model="pool",
                                   pool_dir=tmp_path / "pool", cache_dir=tmp_path / "cache")
    a = {k["keyword"]: k["pred_y3"] for k in small["keywords"]}
    b = {k["keyword"]: k["pred_y3"] for k in big["keywords"]}
    assert all(a[k] == pytest.approx(b[k]) for k in a)


def test_model_choice_comes_from_env_and_rejects_unknown_values(tmp_path, monkeypatch):
    pool = _pool(6)
    run = _synthetic_run(tmp_path, pool)
    monkeypatch.setenv("GROWTH_MODEL", "per-run")
    assert gs.compute_growth_scores(run)["method"]["model"]["mode"] == "per-run"
    with pytest.raises(ValueError, match="pool หรือ per-run"):
        gs.compute_growth_scores(run, model="bogus")
    assert gs.GROWTH_MODEL == "pool"                                # ค่าเริ่มต้นของ production
