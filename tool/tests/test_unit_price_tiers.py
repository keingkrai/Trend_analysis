# -*- coding: utf-8 -*-
"""
Unit test ของ unit_price_tiers.py (🆕 2026-10-12: ช่วงราคาต่อปริมาณเทียบในชนิดสินค้าเดียวกัน) + ตัวเลือก tier_key ของ
category_fit / category_breakdown - ข้อมูลปลอมทั้งหมด ไม่เรียก API

รัน: pytest main/tool/tests/test_unit_price_tiers.py -v
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase3_supply_layer"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from category_breakdown import category_breakdown  # noqa: E402
from category_fit import category_fit  # noqa: E402
from unit_price_tiers import (assign_unit_tiers, catalog_unit_tiers, load_config, unit_price_of,  # noqa: E402
                              uses_unit_price)


def row(price, size, l4="Serum", l2="Skin Care", l3="Facial Care", unit="g·ml", flag="ok", dim="volume"):
    return {"price": price, "size": size, "unit_std": unit, "size_flag": flag, "dimension": dim,
            "l2": l2, "l3": l3, "l4": l4}


# ---------------------------------------------------------------------------
# unit_price_of
# ---------------------------------------------------------------------------

def test_unit_price_of_basic_and_units():
    assert unit_price_of(300, 30, "g·ml", "ok", "volume") == (10.0, "gml")
    assert unit_price_of(60, 3, "ชิ้น", "bundle_summed", "count") == (20.0, "pcs")


@pytest.mark.parametrize("args", [
    (None, 30, "g·ml", "ok", ""),            # ไม่มีราคา
    (300, None, "g·ml", "ok", ""),           # ไม่มีขนาด
    (300, 0, "g·ml", "ok", ""),              # ขนาด 0
    (0, 30, "g·ml", "ok", ""),               # ราคา 0
    (300, 30, "g·ml", "ambiguous_x", ""),    # flag ไม่น่าเชื่อ
    (300, 30, "g·ml", "ok", "mixed"),        # 40ml + 40g
    (300, 30, "Pairs", "ok", ""),            # ไม่ใช่หน่วยที่รู้จัก
])
def test_unit_price_of_unusable(args):
    assert unit_price_of(*args) == (None, None)


# ---------------------------------------------------------------------------
# assign_unit_tiers
# ---------------------------------------------------------------------------

def test_tiers_are_relative_within_type_not_across_l2():
    # เซรั่ม ฿10-30/ml และโลชั่น ฿0.5-1.5/ml อยู่ L2 เดียวกัน - เทียบข้ามชนิดจะได้เซรั่มสูงหมด โลชั่นต่ำหมด
    serum = [row(10 * (i + 1) * 30, 30, "Serum") for i in range(30)]          # ฿/ml 10..300
    lotion = [row(0.5 * (i + 1) * 300, 300, "Body Lotion", l3="Body Care") for i in range(30)]   # ฿/ml 0.5..15
    res = assign_unit_tiers(serum + lotion, min_cohort=30)
    for part in (res[:30], res[30:]):
        tiers = [r["unit_tier"] for r in part]
        assert tiers.count(0) == tiers.count(1) == tiers.count(2) == 10
        assert tiers == sorted(tiers)                     # ราคาต่อ ml สูงขึ้น -> ช่วงสูงขึ้น
        assert {r["tier_basis"] for r in part} == {"L4"}


def test_small_l4_falls_back_to_l3_then_l2():
    a = [row(100 + i, 10, "Serum") for i in range(20)]
    b = [row(50 + 3 * i, 10, "Cream") for i in range(20)]                  # ทั้งคู่ L4 เล็ก (<30) แต่ L3 เดียวกัน = 40
    c = [row(10 + i, 10, "Gel", l3="Other Care") for i in range(10)]       # L3 เล็กด้วย -> L2
    res = assign_unit_tiers(a + b + c, min_cohort=30)
    assert {r["tier_basis"] for r in res[:40]} == {"L3"} and {r["cohort_n"] for r in res[:40]} == {40}
    assert {r["tier_basis"] for r in res[40:]} == {"L2"} and {r["cohort_n"] for r in res[40:]} == {50}


def test_units_are_separate_cohorts():
    ml = [row(10 * (i + 1), 10, "Serum") for i in range(30)]
    pcs = [row(100 * (i + 1), 1, "Serum", unit="ชิ้น") for i in range(30)]   # ฿/ชิ้น สูงกว่ามาก แต่ไม่ปนกับ ฿/ml
    res = assign_unit_tiers(ml + pcs, min_cohort=30)
    assert {r["unit_kind"] for r in res[:30]} == {"gml"} and {r["unit_kind"] for r in res[30:]} == {"pcs"}
    assert [r["unit_tier"] for r in res[:30]].count(0) == 10 and [r["unit_tier"] for r in res[30:]].count(0) == 10


def test_mini_sizes_do_not_move_the_cut_lines_but_get_a_tier():
    base = [row(10 * (i + 1) * 30, 30) for i in range(30)]                   # ฿/ml 10..300 ขนาดปกติ 30
    minis = [row(60, 1) for _ in range(10)]                                  # ซอง 1 ml ฿60/ml - ขนาด < 1/4 ของค่ากลาง 30
    with_minis = assign_unit_tiers(base + minis, min_cohort=30)
    without = assign_unit_tiers(base, min_cohort=30)
    assert [r["unit_tier"] for r in with_minis[:30]] == [r["unit_tier"] for r in without]   # เส้นแบ่งไม่ขยับ
    assert all(r["is_mini"] for r in with_minis[30:]) and not any(r["is_mini"] for r in with_minis[:30])
    assert all(r["unit_tier"] in (0, 1, 2) for r in with_minis[30:])                          # ยังได้ช่วง


def test_no_usable_size_falls_back_to_price_within_type():
    sized = [row(10 * (i + 1) * 30, 30) for i in range(30)]
    nosize = [row(150, None), row(9000, None)]
    res = assign_unit_tiers(sized + nosize, min_cohort=30)
    assert res[30]["unit_kind"] == "price" and res[30]["unit_price"] is None
    assert res[30]["unit_tier"] is not None and res[31]["unit_tier"] == 2     # แพงสุดในชนิดเดียวกัน
    assert res[31]["unit_tier"] >= res[30]["unit_tier"]


def test_no_price_has_no_tier_and_tiny_cohort_has_none():
    res = assign_unit_tiers([row(None, 30), row(100, 10, "Rare", l3="Rare3", l2="Rare2"),
                             row(200, 10, "Rare", l3="Rare3", l2="Rare2")], min_cohort=30)
    assert [r["unit_tier"] for r in res] == [None, None, None]               # cohort L2 มี 2 ชิ้น < 3 ช่วง


def test_ties_collapse_to_two_tiers_with_canonical_numbers():
    # ฿/ml มีแค่ 2 ค่า (เส้นแบ่งชนกัน) -> เหลือ 2 ช่วง = 0 กับ 2 ไม่ใช่ 0 กับ 1
    res = assign_unit_tiers([row(5 * 10, 10) for _ in range(20)] + [row(50 * 10, 10) for _ in range(20)], min_cohort=30)
    assert {r["unit_tier"] for r in res} == {0, 2}


def test_deterministic_and_aligned_to_input():
    rows = [row(10 * (i % 40 + 1), 10 + i % 5, "Serum" if i % 2 else "Cream") for i in range(120)]
    assert assign_unit_tiers(rows) == assign_unit_tiers(list(rows))
    assert len(assign_unit_tiers(rows)) == len(rows)


# ---------------------------------------------------------------------------
# catalog_unit_tiers / config
# ---------------------------------------------------------------------------

def test_catalog_unit_tiers_reads_konvy_columns_and_prices_with_commas():
    n = 40
    df = pd.DataFrame({"sale_price_thb": [f"{(i + 1) * 300:,}.00" for i in range(n)], "size_std": [30.0] * n,
                       "unit_std": ["g·ml"] * n, "size_flag": ["ok"] * n, "dimension_orig": ["volume"] * n,
                       "EM_L2": ["Skin Care"] * n, "EM_L3": ["Facial Care"] * n, "EM_L4": ["Serum"] * n},
                      index=range(100, 100 + n))
    out = catalog_unit_tiers(df, {"basis": "unit_price", "n_tiers": 3, "min_cohort": 30, "mini_ratio": 0.25})
    assert list(out.index) == list(df.index) and out["unit_tier"].tolist() == sorted(out["unit_tier"])
    assert out.loc[100, "unit_price"] == 10.0 and out.loc[139, "unit_tier"] == 2 and out.loc[100, "unit_tier"] == 0


def test_catalog_without_size_columns_raises():
    with pytest.raises(ValueError, match="size_std"):
        catalog_unit_tiers(pd.DataFrame({"sale_price_thb": [1.0], "EM_L2": ["x"], "EM_L3": ["x"], "EM_L4": ["x"]}))


def test_config_defaults_and_override(tmp_path):
    assert load_config(tmp_path / "missing.json")["basis"] == "price"
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"basis": "unit_price", "min_cohort": 10, "_note": "x", "junk": 1}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["basis"] == "unit_price" and cfg["min_cohort"] == 10 and cfg["n_tiers"] == 3 and "junk" not in cfg
    assert uses_unit_price(cfg) and not uses_unit_price({"basis": "price"})
    p.write_text(json.dumps({"basis": "nonsense"}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(p)


# ---------------------------------------------------------------------------
# tier_key ใน category_fit / category_breakdown
# ---------------------------------------------------------------------------

def _market():
    """Skin Care 30 ชิ้น: เซรั่ม 15 (ราคาสูง) + โลชั่น 15 (ราคาต่ำ) - unit_tier ต่ำ/กลาง/สูง สลับกันภายในแต่ละชนิด"""
    out = []
    for i in range(15):
        out.append({"product_name": f"S{i}", "brand": "Mine" if i == 7 else "R", "group": "Skin Care", "subgroup": "Serum",
                    "sale_price_thb": 1000.0 + i, "similarity": 0.9 - i * 0.01, "unit_tier": i // 5})
        out.append({"product_name": f"L{i}", "brand": "R", "group": "Skin Care", "subgroup": "Body Lotion",
                    "sale_price_thb": 100.0 + i, "similarity": 0.5 - i * 0.01, "unit_tier": i // 5})
    return out


def test_category_fit_tier_key_groups_by_precomputed_tier_not_price():
    fit = category_fit(_market(), "Mine", "Skin Care", tier_key="unit_tier")
    cat = fit["categories"][0]
    assert [t["label"] for t in cat["tiers"]] == ["low", "mid", "high"]
    assert [t["n_total"] for t in cat["tiers"]] == [10, 10, 10]               # 5 เซรั่ม + 5 โลชั่น ต่อช่วง
    # ช่วงเดียวกันปนเซรั่ม ฿1,000+ กับโลชั่น ฿100+ - price_from/to เป็นราคาที่พบจริง
    assert cat["tiers"][0]["price_from"] == 100 and cat["tiers"][0]["price_to"] == 1004
    # สินค้า Mine = S7 -> unit_tier 1 (mid) ในกลุ่มนั้นอันดับ 3 (S5 S6 ตามหลังโดย S0..S4 ไม่อยู่กลุ่มนี้ -> S5, S6, S7 = 3)
    best = cat["brand_best"]
    assert best["tier"] == "mid" and best["rank_in_tier"] == 3 and best["n_tier"] == 10 and best["rank_in_market"] == 8


def test_category_fit_without_tier_key_is_unchanged():
    scored = _market()
    without = [{k: v for k, v in s.items() if k not in ("unit_tier", "unit_price", "unit_label", "size", "is_mini")}
               for s in scored]
    base = category_fit(without, "Mine", "Skin Care")
    again = category_fit(scored, "Mine", "Skin Care")        # สินค้ามีฟิลด์ unit_* แต่ไม่ส่ง tier_key -> แบ่งตามราคาขายเหมือนเดิม

    def shape(fit):
        return [(t["label"], t["n_total"], t["price_from"], t["price_to"], [p["product_name"] for p in t["top"]],
                 (t["brand_best"] or {}).get("rank_in_tier")) for c in fit["categories"] for t in c["tiers"]]

    assert shape(base) == shape(again) and base["tier_basis"] == again["tier_basis"] == "price"
    assert base["categories"][0]["tiers"][0]["price_to"] < 1000      # แบ่งตามราคาขาย: ช่วงต่ำ = โลชั่น
    assert "unit_tier" not in base["categories"][0]["tiers"][0]["top"][0]   # ไม่มีข้อมูล unit_* ก็ไม่เติมฟิลด์


def test_column_unit_range_ignores_items_of_another_unit_kind():
    """🆕 (2026-10-14) คอลัมน์ Shampoo: แปรงสระผม 59 ฿ ต่อชิ้น อยู่ช่วงต่ำเหมือนกัน - ช่วง ฿/มล. ของคอลัมน์ต้องไม่รวมค่า ฿ ต่อชิ้น"""
    from category_breakdown import _keyed_price_tiers

    def item(name, tier, unit_price, label, mini=False):
        return {"product_name": name, "brand": "B", "similarity": 0.5, "sale_price_thb": 100, "unit_tier": tier,
                "unit_price": unit_price, "unit_label": label, "is_mini": mini}

    members = [(i + 1, s) for i, s in enumerate([
        item("a", 0, 0.12, "ml"), item("b", 0, 0.40, "ml"), item("brush 1", 0, 59.0, "pcs"), item("brush 2", 0, 59.0, "pcs"),
        item("c", 1, 0.50, "g"), item("d", 1, 0.85, "ml"), item("brush 3", 1, 89.0, "pcs"),
        item("e", 2, 0.95, "ml"), item("f", 2, 5.4, "ml"), item("tiny", 2, 40.0, "ml", mini=True)])]
    tiers = {t["label"]: t for t in _keyed_price_tiers(members, set(), 3, "unit_tier")}
    assert (tiers["low"]["unit_from"], tiers["low"]["unit_to"]) == (0.12, 0.4)          # ไม่มี 59 ของแปรง
    assert (tiers["mid"]["unit_from"], tiers["mid"]["unit_to"]) == (0.5, 0.85)          # ไม่มี 89 ของแปรง
    assert (tiers["high"]["unit_from"], tiers["high"]["unit_to"]) == (0.95, 5.4)        # ซองทดลอง 40 ไม่นับ
    assert tiers["low"]["unit_label"] == "ml_g" or tiers["low"]["unit_label"] == "ml"   # ml/g เป็นหน่วยของคอลัมน์ ไม่ใช่ pcs
    # คอลัมน์ที่ส่วนใหญ่เป็นชิ้น (แปรง/อุปกรณ์): ช่วงเป็น ฿ ต่อชิ้น และไม่เอาค่า ฿/ml มาปน
    pcs = [(i + 1, s) for i, s in enumerate([item("p1", 0, 20.0, "pcs"), item("p2", 0, 35.0, "pcs"), item("p3", 0, 40.0, "pcs"),
                                              item("odd", 0, 0.3, "ml")])]
    t = _keyed_price_tiers(pcs, set(), 3, "unit_tier")[0]
    assert (t["unit_from"], t["unit_to"], t["unit_label"]) == (20.0, 40.0, "pcs")


def test_category_fit_tier_key_drops_empty_tiers_and_ignores_unkeyed():
    scored = [{**s, "unit_tier": (0 if s["unit_tier"] == 0 else 2)} for s in _market()]
    scored[0]["unit_tier"] = None                                    # ไม่มีช่วง -> ไม่อยู่กลุ่มไหน
    fit = category_fit(scored, "Mine", "Skin Care", tier_key="unit_tier")
    cat = fit["categories"][0]
    assert [t["label"] for t in cat["tiers"]] == ["low", "high"]
    assert sum(t["n_total"] for t in cat["tiers"]) == len(scored) - 1


def test_category_breakdown_tier_key_uses_precomputed_tiers_per_column():
    scored = _market()
    sizes = {"Skin Care": 30}
    sub = {("Skin Care", "Serum"): 15, ("Skin Care", "Body Lotion"): 15}
    out = category_breakdown(scored, sizes, subgroup_sizes=sub, main_category="Skin Care", pool_fraction=1.0,
                             min_pool=3, tier_key="unit_tier")
    cols = {c["subgroup"]: c for c in out["categories"]}
    assert set(cols) == {"Serum", "Body Lotion"}
    for c in cols.values():
        assert [t["label"] for t in c["price_tiers"]] == ["low", "mid", "high"]
        assert [t["n_total"] for t in c["price_tiers"]] == [5, 5, 5]
    serum_tiers = cols["Serum"]["price_tiers"]
    assert serum_tiers[0]["product"]["product_name"] == "S0" and serum_tiers[2]["product"]["product_name"] == "S10"
    # ไม่ส่ง tier_key = แบ่งจากราคาขายของคอลัมน์ (เดิม) ได้ช่วงเดียวกันเพราะข้อมูลทดสอบเรียงราคาตามช่วง
    plain = category_breakdown(scored, sizes, subgroup_sizes=sub, main_category="Skin Care", pool_fraction=1.0, min_pool=3)
    assert {c["subgroup"] for c in plain["categories"]} == {"Serum", "Body Lotion"}


# ---------------------------------------------------------------------------
# market_tiers / ⑬ (market rows, Excel labels)
# ---------------------------------------------------------------------------
def _catalog(n=40):
    return pd.DataFrame({"sale_price_thb": [f"{(i + 1) * 300:,}.00" for i in range(n)], "size_std": [30.0] * n,
                         "unit_std": ["g·ml"] * n, "size_flag": ["ok"] * n, "dimension_orig": ["volume"] * n,
                         "EM_L2": ["Skin Care"] * n, "EM_L3": ["Facial Care"] * n, "EM_L4": ["Serum"] * n},
                        index=range(100, 100 + n))


def test_market_tiers_respects_basis_and_returns_clean_records():
    from unit_price_tiers import market_tiers

    df = _catalog()
    recs, key, meta = market_tiers(df, {"basis": "price", "n_tiers": 3, "min_cohort": 30, "mini_ratio": 0.25})
    assert recs is None and key is None and meta["tier_basis"] == "price"
    recs, key, meta = market_tiers(df, {"basis": "unit_price", "n_tiers": 3, "min_cohort": 30, "mini_ratio": 0.25})
    assert key == "unit_tier" and meta == {"tier_basis": "unit_price",
                                           "tier_config": {"n_tiers": 3, "min_cohort": 30, "mini_ratio": 0.25}}
    assert set(recs) == set(df.index)
    r = recs[100]
    assert r["unit_tier"] == 0 and r["unit_price"] == 10.0 and r["unit_label"] == "ml" and r["size"] == 30.0 and r["is_mini"] is False
    assert recs[139]["unit_tier"] == 2


def test_market_rows_and_excel_labels_carry_unit_fields():
    import run_brand_coverage as rbc
    from unit_price_tiers import market_tiers

    df = _catalog().assign(product_name=lambda d: [f"P{i}" for i in range(len(d))], brand="B", EM_Group="Skin Care")
    recs, _, _ = market_tiers(df, {"basis": "unit_price", "n_tiers": 3, "min_cohort": 30, "mini_ratio": 0.25})
    rows = rbc.build_market_rows(df, list(df.index), recs)
    assert rows[0]["unit_tier"] == 0 and rows[-1]["unit_tier"] == 2 and rows[0]["unit_label"] == "ml"
    assert "unit_tier" not in rbc.build_market_rows(df, list(df.index))[0]       # ไม่ส่ง tier_recs = เหมือนเดิม
    # ป้ายกลุ่มในชีต Excel: ช่วงราคาต่อปริมาณไม่มีช่วงบาท
    assert rbc.price_group_label({"label": "mid", "price_from": 160, "price_to": 395}, unit=True) == "ราคาต่อปริมาณกลาง"
    assert rbc.price_group_label({"label": "mid", "price_from": 160, "price_to": 395}) == "ราคากลาง 160-395 บาท"
    assert rbc.group_names({"tier_basis": "unit_price"})["high"] == "ราคาต่อปริมาณสูง"
    assert rbc.group_names({})["high"] == "ราคาสูง"


def test_excel_product_rows_show_size_and_unit_price():
    import run_brand_coverage as rbc

    grading = {"top_pct": {"excellent": 1, "good": 5, "average": 20}, "level": lambda rank, n: "good"}
    fit = {"n_market": 100, "main_category": "Skin Care", "tier_basis": "unit_price", "categories": [{
        "category": "Skin Care", "n_total": 30, "n_brand": 1, "brand_best": None, "tiers": [{
            "label": "mid", "price_from": 160, "price_to": 395, "n_total": 10, "n_brand": 1,
            "top": [{"product_name": "Rival", "brand": "R", "sale_price_thb": 300.0, "similarity": 0.4, "rank_in_tier": 1,
                     "rank_in_market": 3, "size": 30.0, "unit_label": "ml", "unit_price": 10.0, "is_mini": False}],
            "brand_best": {"product_name": "Mine", "brand": "B", "sale_price_thb": 60.0, "similarity": 0.3, "rank_in_tier": 4,
                           "rank_in_market": 12, "size": 5.0, "unit_label": "g", "unit_price": 12.0, "is_mini": True}}]}]}
    rows = rbc.trend_product_rows("B", {"k": {"trend_name": "T", "stream": "S", "category_fit": fit, "brand_best_product": None}},
                                  grading=grading)
    assert {r["กลุ่มราคา"] for r in rows} == {"ราคาต่อปริมาณกลาง"}
    rival = next(r for r in rows if r.get("สินค้า") == "Rival")
    mine = next(r for r in rows if r.get("สินค้า") == "Mine")
    assert (rival["ขนาด"], rival["฿ ต่อหน่วย"], rival["ขนาดทดลอง/ซอง"]) == ("30 ml", 10.0, None)
    assert (mine["ขนาด"], mine["฿ ต่อหน่วย"], mine["ขนาดทดลอง/ซอง"]) == ("5 g", 12.0, "ใช่")


def test_column_unit_label_is_shared_and_mixed_ml_g():
    def market(labels):
        out = []
        for i, lab in enumerate(labels):
            out.append({"product_name": f"S{i}", "brand": "R", "group": "Sun Care", "subgroup": "Face Sunscreen",
                        "sale_price_thb": 100.0 + i, "similarity": 0.9 - i * 0.01, "unit_tier": i * 3 // len(labels),
                        "unit_price": 3.0 + i, "unit_label": lab, "size": 30.0, "is_mini": False})
        return out

    sizes = {"Sun Care": 12}
    sub = {("Sun Care", "Face Sunscreen"): 12}
    kw = dict(group_sizes=sizes, subgroup_sizes=sub, main_category="Sun Care", pool_fraction=1.0, min_pool=3, tier_key="unit_tier")
    mixed = category_breakdown(market(["ml", "g"] * 6), **kw)
    only_ml = category_breakdown(market(["ml"] * 12), **kw)
    only_g_mostly = category_breakdown(market(["g"] * 11 + ["ml"]), **kw)
    assert {t["unit_label"] for c in mixed["categories"] for t in c["price_tiers"]} == {"ml_g"}      # ปนกัน -> ml/g ทุกช่วง
    assert {t["unit_label"] for c in only_ml["categories"] for t in c["price_tiers"]} == {"ml"}
    assert {t["unit_label"] for c in only_g_mostly["categories"] for t in c["price_tiers"]} == {"g"}  # g ส่วนใหญ่ (ml < 25%)
