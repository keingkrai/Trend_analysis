# -*- coding: utf-8 -*-
"""
Unit test ของ ⑲ รายงานส่วนแบ่งตลาด Phase 0-1 (market_data.py + market_facts.py) - ข้อมูลปลอมทั้งหมด ไม่อ่านไฟล์จริง ไม่เรียก API

รัน: pytest main/tool/tests/test_market_facts.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase7_market_report"))

from market_data import (brand_key, mark_leaves, thai_brand_names, tidy_brand_shares, tidy_channel,  # noqa: E402
                         tidy_fda, tidy_market_sizes)
from market_facts import (DEFAULTS, brand_facts, cagr, category_factors, channel_facts,  # noqa: E402
                          fda_complete_through, fda_facts, merged_into)

CFG = {**DEFAULTS, "_base": 2020, "_last": 2025}


# ---------------------------------------------------------------------------
# market_data
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("a,b", [("La Roche-Posay", "LA ROCHE POSAY"), ("L'Oréal Paris", "LOREAL PARIS"),
                                 ("Pond's", "PONDS"), ("CeraVe", "CERAVE")])
def test_brand_key_matches_across_sources(a, b):
    assert brand_key(a) == brand_key(b) != ""


def test_thai_brand_names_most_common_thai_spelling():
    fda = pd.DataFrame({"brand_key": ["MISTINE"] * 3 + ["NIVEA", ""],
                        "brand_th": ["มิสทีน", "มิสทีน", "MISTINE", "NIVEA", "ไม่มีชื่อ"]})
    names = thai_brand_names(fda)
    assert names["MISTINE"] == "มิสทีน"
    assert "NIVEA" not in names.index and "" not in names.index   # ชื่อไม่มีอักษรไทย / ไม่มีคีย์ ไม่นับ


def test_brand_key_keeps_thai_and_handles_missing():
    assert brand_key("ศรีจันทร์ 2") == "ศรีจันทร์2"
    assert brand_key(None) == ""


def test_mark_leaves_parent_with_data_children_is_not_leaf():
    # Total > Retail > Offline > (Grocery, Convenience) / Retail > E-Com / Salons (ไม่มีข้อมูล)
    levels = [0, 1, 2, 3, 3, 2, 1]
    has_data = [True, True, True, True, True, True, False]
    assert mark_leaves(levels, has_data) == [False, False, False, True, True, True, False]


def test_mark_leaves_parent_whose_children_have_no_data_is_leaf():
    assert mark_leaves([1, 2, 2], [True, False, False]) == [True, False, False]


def _channel_raw():
    base = {"Country": "Thailand", "Data Type": "Retail Value RSP", "Category": " Skin Care"}
    tree = [("Total", 0, 100, 100), ("  Retail Offline", 1, 90, 80), ("    Direct Selling", 2, 30, 20),
            ("    Beauty Specialists", 2, 60, 60), ("  Retail E-Commerce", 1, 10, 20), ("  Hair Salons", 1, None, None)]
    rows = [{**base, "Outlet": o, "Outlet Hierarchy": lv, "2020 (%)": a, "2025 (%)": b} for o, lv, a, b in tree]
    return pd.DataFrame(rows + rows + [{"Country": None, "Category": "© Euromonitor"}])   # ต้นไม้ซ้ำ 2 ชุด + แถวลิขสิทธิ์


def test_tidy_channel_dedupes_strips_and_marks_leaves():
    ch = tidy_channel(_channel_raw())
    assert set(ch["category"]) == {"Skin Care"}
    assert len(ch) == 6 * 2                                   # 6 ช่องทาง x 2 ปี (ชุดซ้ำถูกตัด)
    leaves = sorted(ch.loc[ch["is_leaf"], "outlet"].unique())
    assert leaves == ["Beauty Specialists", "Direct Selling", "Retail E-Commerce"]
    assert ch[ch["is_leaf"] & (ch["year"] == 2025)]["share"].sum() == pytest.approx(100)


def _market_raw():
    rows = []
    for cc, mult in (("Historic Current Prices, Forecast Current Prices", 1.0),
                     ("Historic Constant 2025 Prices, Forecast Constant 2025 Prices", 0.9)):
        for year, v in ((2020, 100.0), (2025, 150.0)):
            rows.append({"Country": "Thailand", "Category": "Skin Care", "Data Type": "Retail Value RSP",
                         "Unit": "THB million", "Current/Constant": cc, "Year": year, "Actual": v * mult, "Edition": 2026})
    rows.append({**rows[0], "Unit": "USD million", "Actual": 3.0})   # หน่วยอื่นต้องถูกกรองทิ้ง
    return pd.DataFrame(rows)


def test_tidy_market_sizes_nominal_and_real():
    ms = tidy_market_sizes(_market_raw()).set_index("year")
    assert ms.loc[2025, "value"] == 150 and ms.loc[2025, "value_real"] == pytest.approx(135)
    assert ms["edition"].iloc[0] == 2026


def test_tidy_market_sizes_rejects_duplicates():
    raw = _market_raw()
    with pytest.raises(ValueError):
        tidy_market_sizes(pd.concat([raw, raw.iloc[[0]]]))


def test_tidy_brand_shares_keeps_untracked_years_nan():
    raw = pd.DataFrame([
        {"Country": "Thailand", "Category": "Skin Care", "Unit": "THB million", "Global Brand Name": "A",
         "Global Brand Owner": "X", "Year": 2020, "Percent": None, "Actual": None},
        {"Country": "Thailand", "Category": "Skin Care", "Unit": "THB million", "Global Brand Name": "A",
         "Global Brand Owner": "X", "Year": 2025, "Percent": 1.5, "Actual": 15.0},
        {"Country": "Thailand", "Category": "Skin Care", "Unit": "THB million", "Global Brand Name": "Others",
         "Global Brand Owner": "Others", "Year": 2025, "Percent": 40.0, "Actual": 400.0}])
    b = tidy_brand_shares(raw).set_index(["brand", "year"])
    assert pd.isna(b.loc[("A", 2020), "share"])
    assert not b.loc[("Others", 2025), "is_named"]


def test_tidy_fda_dates_brand_fallback_category_origin():
    raw = pd.DataFrame({
        "วันที่อนุญาต": ["4/1/2564", "15/12/2568", "ไม่ระบุ"],
        "ชื่อการค้า": ["รีญา", "มิซึมิ", "x"],
        "ชื่อการค้า (อังกฤษ)": ["REEYA", "-", "X"],
        "ประเภทการจดแจ้ง": ["ผลิต", "นำเข้า", "ผลิต"],
        "ชื่อผู้ประกอบการ": ["c1", "c2", "c3"], "สถานะการจดแจ้ง": ["สิ้นอายุ", "อนุมัติ", "อนุมัติ"],
        "Category2": ["Skincare", "Eye Make-Up", "Uncertain"], "Category3": [None, None, None]})
    f = tidy_fda(raw)
    assert len(f) == 2                                        # วันที่อ่านไม่ได้ถูกตัด
    assert list(zip(f["year"], f["month"])) == [(2021, 1), (2025, 12)]
    assert list(f["brand"]) == ["REEYA", "มิซึมิ"]              # ชื่ออังกฤษเป็น "-" ใช้ชื่อไทย
    assert list(f["brand_th"]) == ["รีญา", "มิซึมิ"]
    assert list(f["category"]) == ["Skin Care", "Colour Cosmetics"]
    assert list(f["origin"]) == ["local", "import"]


# ---------------------------------------------------------------------------
# market_facts
# ---------------------------------------------------------------------------

def test_cagr():
    assert cagr(100, 121, 2) == pytest.approx(10)
    assert cagr(None, 5, 3) is None and cagr(0, 5, 3) is None and cagr(5, 6, 0) is None


def _brands():
    rows = []
    def add(brand, s20, s25, s24=None):
        for y, s in ((2020, s20), (2024, s24 if s24 is not None else s25), (2025, s25)):
            rows.append({"category": "Skin Care", "brand": brand, "owner": brand + " Co", "year": y, "share": s,
                         "value": None if s is None else s * 10, "is_named": brand not in ("Others", "Total")})
    add("Big", 10.0, 9.0)
    add("Riser", 1.0, 4.0, 3.5)
    add("Faller", 5.0, 2.0)
    add("Newbie", None, 1.2)
    add("Tiny", 0.1, 0.3)          # ต่ำกว่า mover_min_share ทั้งสองปี -> ไม่เป็น mover
    add("Gone", 2.0, None, 1.0)    # Euromonitor เลิกแยกปี 2025 -> ไม่ใช่ mover, ส่วนแบ่งไปรวม Others
    add("Others", 30.0, 38.0)
    return pd.DataFrame(rows)


def test_brand_facts_orders_by_size_not_change():
    b = brand_facts(_brands(), "Skin Care", 2020, 2025, CFG)
    assert [t["brand"] for t in b["top"]] == ["Big", "Riser", "Faller", "Newbie", "Tiny"]
    assert b["top"][1]["change_pp"] == 3.0 and b["top"][1]["change_pp_1y"] == 0.5


def test_brand_facts_new_brands_movers_and_concentration():
    b = brand_facts(_brands(), "Skin Care", 2020, 2025, CFG)
    assert [n["brand"] for n in b["new_brands"]] == ["Newbie"] and b["new_brands"][0]["first_year"] == 2024
    assert b["top"][3]["series"]["2020"] is None                      # ปีที่ไม่ได้ติดตาม ไม่ใช่ 0
    movers = [m["brand"] for m in b["movers"]]
    assert movers[:2] in (["Riser", "Faller"], ["Faller", "Riser"])   # |3.0| เท่ากัน
    assert "Tiny" not in movers and "Others" not in movers and "Gone" not in movers
    assert b["dropped_brands"] == [{"brand": "Gone", "share_base": 2.0, "last_year_seen": 2024, "merged_into": None}]
    assert b["others"]["2025"] == 38.0
    assert b["top5"]["2025"] == pytest.approx(9 + 4 + 2 + 1.2 + 0.3)


def _merge_case():
    """Johnson's รวมเข้า Johnson's Baby (เจ้าของเดียวกัน) ปี 2023 - ตัวเลขใกล้ของจริงหมวด Baby"""
    shares = {"Johnson's": ("Kenvue", {2019: 10.6, 2022: 11.2}),
              "Johnson's Baby": ("Kenvue", {2019: 18.0, 2022: 18.5, 2023: 29.0, 2025: 24.4}),
              "Babi Mild": ("Osotspa", {2019: 11.8, 2022: 11.6, 2023: 11.7, 2025: 12.6}),
              "Others": ("Others", {2019: 17.2, 2022: 10.2, 2023: 9.5, 2025: 15.1})}
    return pd.DataFrame([{"category": "Baby", "brand": b, "owner": o, "year": y, "share": s.get(y), "value": None,
                          "is_named": b != "Others"} for b, (o, s) in shares.items() for y in (2019, 2022, 2023, 2025)])


def test_merged_into_needs_shared_name_word():
    # บริษัทเดียวกัน แบรนด์อื่นโตเองในปีที่แบรนด์หาย (L'Oréal Men Expert / La Roche-Posay ปี 2024) -> ไม่ใช่การรวม
    named = pd.DataFrame({2023: [0.78, 2.37], 2024: [None, 3.24]}, index=["L'Oréal Men Expert", "La Roche-Posay"])
    owners = pd.Series({"L'Oréal Men Expert": "L'Oréal Groupe", "La Roche-Posay": "L'Oréal Groupe"})
    assert merged_into(named, owners, "L'Oréal Men Expert", 2023) is None
    named = pd.DataFrame({2022: [0.23, None], 2023: [None, 0.20]}, index=["The History of Whoo", "The Whoo"])
    owners = pd.Series({"The History of Whoo": "LG H&H", "The Whoo": "LG H&H"})
    assert merged_into(named, owners, "The History of Whoo", 2022) == "The Whoo"


def test_brand_facts_merge_into_same_owner_is_not_a_move():
    b = brand_facts(_merge_case(), "Baby", 2019, 2025, CFG)
    assert b["dropped_brands"][0]["merged_into"] == "Johnson's Baby"
    jb = next(t for t in b["top"] if t["brand"] == "Johnson's Baby")
    assert jb["absorbed"] == ["Johnson's"]
    assert jb["share_base"] == pytest.approx(28.6) and jb["change_pp"] == pytest.approx(-4.2)   # ไม่ใช่ +6.4
    assert b["new_brands"] == []
    factors = category_factors("Baby", {"brands": b}, {**CFG, "_base": 2019})
    conc = next(f for f in factors if f["type"] == "concentration")
    assert conc["dropped_brands"] == [] and conc["others_change_excl_dropped_pp"] == pytest.approx(-2.1)


def test_channel_facts_sorted_by_absolute_change():
    ch = tidy_channel(_channel_raw())
    c = channel_facts(ch, "Skin Care", 2020, 2025)
    assert [r["outlet"] for r in c["leaves"]] == ["Direct Selling", "Retail E-Commerce", "Beauty Specialists"]
    assert c["leaves"][0]["change_pp"] == -10
    assert c["ecommerce"] == {"2020": 10.0, "2025": 20.0}


def _fda():
    rows = []
    for year in (2021, 2022, 2023):
        months = range(1, 13) if year < 2023 else range(1, 9)
        for m in months:
            rows += [{"year": year, "month": m, "brand_key": "OLD", "brand": "Old", "origin": "local"}] * 10
            if year >= 2022:
                rows += [{"year": year, "month": m, "brand_key": "NEW", "brand": "New", "origin": "import"}] * 5
    rows += [{"year": 2023, "month": 9, "brand_key": "OLD", "brand": "Old", "origin": "local"}] * 2   # เดือนที่เพิ่งเริ่มเก็บ
    return pd.DataFrame(rows)


def test_fda_complete_through_ignores_sparse_last_month():
    assert fda_complete_through(_fda()) == (2023, 8)


def test_fda_facts_full_years_partial_year_and_shares():
    d = _fda()
    first_year = d.groupby("brand_key")["year"].min()
    f = fda_facts(d, (2023, 8), first_year, {"OLD"}, CFG)
    assert f["by_year"] == {"2021": 120, "2022": 180}
    assert f["change_pct"] == 50.0 and f["change_years"] == [2021, 2022]
    assert f["partial_year"] == {"year": 2023, "through_month": 8, "n": 120, "n_prev_same_months": 120, "change_pct": 0.0}
    assert f["import_share"]["2022"] == pytest.approx(33.3, abs=0.1)
    assert f["untracked_share"]["2022"] == pytest.approx(33.3, abs=0.1)   # NEW ไม่อยู่ใน Euromonitor
    assert f["new_brands_by_year"] == {"2022": 1}
    assert f["top_new_brands"][0] == {"brand": "New", "first_year": 2022, "n": 100, "tracked_by_euromonitor": False}


def test_category_factors_thresholds():
    b = brand_facts(_brands(), "Skin Care", 2020, 2025, CFG)
    c = {"brands": b, "channel": channel_facts(tidy_channel(_channel_raw()), "Skin Care", 2020, 2025),
         "premium": {"share_base": 28.4, "share_last": 27.9, "change_pp": -0.5, "share_forecast": 27.8},
         "fda": {"change_pct": 5.0}}
    types = {f["type"]: f for f in category_factors("Skin Care", c, CFG)}
    assert set(types) == {"channel_shift", "concentration"}        # premium -0.5 / อย. +5% ต่ำกว่าเกณฑ์
    assert types["concentration"]["others_change_pp"] == 8.0
    assert types["concentration"]["others_change_excl_dropped_pp"] == 6.0   # 2 จุดมาจาก Gone ที่เลิกแยก
    assert types["concentration"]["new_brands"] == ["Newbie"]
    assert all(abs(r["change_pp"]) >= 1 for r in types["channel_shift"]["changes"])


def test_concentration_not_triggered_by_coverage_change_alone():
    # Others +2 จุดทั้งหมดมาจากแบรนด์ที่เลิกแยก และไม่มีแบรนด์ใหม่ -> ไม่นับเป็นปัจจัย
    b = {"others": {"2020": 30.0, "2025": 32.0}, "top5": {}, "new_brands": [], "movers": [],
         "dropped_brands": [{"brand": "Gone", "share_base": 2.0, "last_year_seen": 2023}]}
    assert category_factors("Fragrances", {"brands": b}, CFG) == []
