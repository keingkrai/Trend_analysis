# -*- coding: utf-8 -*-
"""
เทสตัวเทียบผล ⑫ สองรอบ (phase3_supply_layer/compare_supply_runs.py) - ข้อมูลจำลอง ไม่เรียก API

รัน: pytest main/tool/tests/test_compare_supply_runs.py -v
"""
import json
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOL_DIR / "phase3_supply_layer"))

import compare_supply_runs as cs  # noqa: E402


def _m(brand, name, sim=0.3):
    return {"brand": brand, "product_name": name, "similarity": sim}


def _tier(label, n, brand, name):
    return {"label": label, "n_total": n, "product": _m(brand, name)}


def _trend(top, tiers, main="Skin Care", n=100):
    return {"trend_name": "T1", "stream": "paper", "n_products_compared": n, "main_category": {"category": main},
            "top_matches": [_m(b, p) for b, p in top],
            "by_category": {"categories": [{"group": f"{main} · Serum", "price_tiers": tiers}]}}


def _write(tmp_path, name, trend, total):
    d = tmp_path / name
    d.mkdir()
    (d / cs.RESULT_NAME).write_text(json.dumps({"n_products_total": total, "results": {"paper::T1": trend}}), encoding="utf-8")
    return d


def test_compare_counts_overlap_new_entries_and_shop(tmp_path):
    old = _trend([("A", f"p{i}") for i in range(15)],
                 [_tier("low", 10, "A", "p0"), _tier("mid", 10, "A", "p1"), _tier("high", 10, "A", "p2")])
    new_top = [("A", "p0"), ("A", "p1"), ("E", "new1"), ("A", "p3"), ("E", "new2")] + [("A", f"p{i}") for i in range(5, 15)]
    new = _trend(new_top, [_tier("low", 14, "A", "p0"), _tier("mid", 12, "E", "new1"), _tier("high", 10, "A", "p2")], n=140)
    shop = {("E", "new1"): "Eve and Boy", ("E", "new2"): "Eve and Boy"}
    old_dir, new_dir = _write(tmp_path, "old", old, 1000), _write(tmp_path, "new", new, 1400)
    rows, meta = cs.compare_runs(old_dir, new_dir, shop_of=shop)
    r = rows[0]
    assert meta == {"n_products_old": 1000, "n_products_new": 1400}
    assert r["same_top1"] and r["overlap5"] == 3 and r["new_top5_from_eve"] == 2
    assert {e[1] for e in r["entered5"]} == {"new1", "new2"} and all(e[2] == "Eve and Boy" for e in r["entered5"])
    assert [t["same_best"] for t in r["tiers"]] == [True, False, True]
    assert r["tiers"][1]["best_new_shop"] == "Eve and Boy" and r["tiers"][0]["n_new"] == 14


def test_changed_main_category_is_reported_and_tiers_skipped(tmp_path):
    old = _trend([("A", "p0")], [_tier("low", 1, "A", "p0")], main="Skin Care")
    new = _trend([("A", "p0")], [_tier("low", 1, "A", "p0")], main="Sun Care")
    old_dir, new_dir = _write(tmp_path, "o", old, 10), _write(tmp_path, "n", new, 10)
    r = cs.compare_runs(old_dir, new_dir, shop_of={})[0][0]
    assert (r["main_old"], r["main_new"]) == ("Skin Care", "Sun Care") and r["column_changed"] and r["tiers"] == []


def test_markdown_has_one_row_per_trend(tmp_path):
    old = _trend([("A", "p0")], [_tier("low", 1, "A", "p0")])
    d1, d2 = _write(tmp_path, "o", old, 10), _write(tmp_path, "n", old, 12)
    rows, meta = cs.compare_runs(d1, d2, shop_of={})
    md = cs.render_markdown(rows, meta, "o", "n")
    assert "10 -> 12" in md and md.count("| T1 |") >= 2          # ตารางสรุป + ตารางช่วงราคา
