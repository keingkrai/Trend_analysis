# -*- coding: utf-8 -*-
"""
เทสตัวทำขนาดสินค้ามาตรฐาน (tool/product/size_standardiser.py) - ใช้กับ eveandboy ที่ไม่มี size_std ของผู้ให้ข้อมูล
เทสสุดท้ายรันกับ konvy_product.csv จริง: คำนวณจากชื่อ+product_size/size_unit/product_pieces (ไม่ดู raw_product_size) แล้วเทียบกับ
size_std ของผู้ให้ข้อมูล - ข้ามถ้าไม่มีไฟล์

รัน: pytest main/tool/tests/test_size_standardiser.py -v
"""
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

TOOL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOL_DIR))

from product import size_standardiser as ss  # noqa: E402

KONVY_CSV = TOOL_DIR / "product" / "konvy_product.csv"


def _std(name, size, unit, pieces=None):
    return ss.standardise_size(name, size, unit, pieces)


def test_plain_mass_and_volume():
    r = _std("Eucerin Spotless Brightening Serum 30ml", 30, "ml", 1)
    assert (r["size_std"], r["unit_std"], r["dimension_orig"], r["size_flag"]) == (30.0, "g·ml", "volume", "ok")
    r = _std("Srichand Powder 10g", 10, "g")
    assert (r["size_std"], r["dimension_orig"], r["size_flag"]) == (10.0, "mass", "ok")


def test_pair_counts_two_pieces_and_pcs_count_stays():
    assert _std("Lens [1 Pair]", 1, "Pairs", 1)["size_std"] == 2.0
    r = _std("Cotton Pads 100 Pcs", 100, "pcs", 100)
    assert (r["size_std"], r["unit_std"], r["dimension_orig"], r["size_flag"]) == (100.0, "ชิ้น", "count", "ok")


def test_pack_multiplier_from_the_name():
    r = _std("Rojukiss Mask [25ml x 3pcs]", 25, "ml", 3)
    assert (r["size_std"], r["pack_mult"], r["size_flag"]) == (75.0, 3.0, "ok")
    r = _std("C2M Hair Color Powder [3pcs x 10g] #Black", 10, "g", 3)
    assert (r["size_std"], r["pack_mult"]) == (30.0, 3.0)
    assert _std("Tissue [280 Sheets x 5pcs]", 280, "Sheets", 5)["size_std"] == 1400.0


def test_size_already_total_is_not_multiplied_twice():
    r = _std("Lotion [500ml x 2pcs]", 1000, "ml", 2)
    assert r["size_std"] == 1000.0 and r["size_flag"] == "ok"


def test_bundle_sum_when_product_size_is_first_term_or_the_total():
    r = _std("&honey Shampoo 40ml + Conditioner 40g", 40, "ml")
    assert (r["size_std"], r["dimension_orig"], r["size_flag"]) == (80.0, "mixed", "bundle_summed")
    r = _std("PANTENE Shampoo + Condi (380ml+380ml.)", 760, "ml", 2)
    assert (r["size_std"], r["size_flag"]) == (760.0, "bundle_summed")


def test_shade_codes_between_terms_do_not_break_the_bundle():
    r = _std("2P Concealer 5g #01 Light Rest + Corrector 5g #00 Peach", 5, "g", 2)
    assert (r["size_std"], r["size_flag"]) == (10.0, "bundle_summed")


def test_free_gift_is_not_part_of_the_paid_size():
    r = _std("CeraVe Lotion 473ml + Free! Foaming Cleanser [30ml x 2pcs]", 473, "ml")
    assert (r["size_std"], r["size_flag"]) == (473.0, "ok")


def test_pieces_without_evidence_is_unverified():
    # เลข 2 ใน "2 LINGERIE" ถูกอ่านเป็นจำนวนชิ้น
    r = _std("CLIO Kill Cover Cushion SPF50+ PA+++ 2 LINGERIE", 15, "g", 2)
    assert r["size_flag"] == "pieces_unverified" and r["size_flag"] not in ss.USABLE_FLAGS


def test_pieces_written_in_the_name_is_evidence():
    r = _std("AGLAM Toner Pad 221g [60 Pads]", 221, "g", 60)
    assert (r["size_std"], r["size_flag"]) == (221.0, "ok")


def test_set_words_make_a_single_size_unusable():
    assert _std("Lip Duo Set", 2, "g", 1)["size_flag"] == "bundle_unresolved"
    assert _std("CLINIQUE Moisture Surge Glow Duo Set", 240, "ml")["size_flag"] == "bundle_unresolved"


def test_not_a_quantity_and_no_size():
    assert _std("Dental Floss 50m", 50, "m")["size_flag"] == "not_a_quantity"
    assert _std("Capsule 1000 mg", 1000, "mg")["size_flag"] == "not_a_quantity"
    assert _std("Thing", None, None)["size_flag"] == "no_size"
    assert math.isnan(_std("Thing", 0, "ml")["size_std"])


def test_two_different_dimensions_with_x_is_ambiguous():
    assert _std("Double Head Pen [0.1g x 0.35ml]", 0.1, "g")["size_flag"] == "ambiguous_x"


def test_usable_flags_match_unit_price_tiers():
    sys.path.insert(0, str(TOOL_DIR / "phase3_supply_layer"))      # unit_price_tiers import category_breakdown แบบพี่น้อง
    import unit_price_tiers as upt
    assert tuple(ss.USABLE_FLAGS) == tuple(upt.USABLE_FLAGS)


def test_add_size_columns_keeps_index_and_does_not_touch_input():
    df = pd.DataFrame({"product_name": ["A 30ml", "B 5g"], "product_size": [30, 5], "size_unit": ["ml", "g"]}, index=[7, 9])
    out = ss.add_size_columns(df)
    assert list(out.index) == [7, 9] and list(out["size_std"]) == [30.0, 5.0]
    assert "size_std" not in df.columns


def test_agrees_with_konvy_provider_values_on_the_real_file():
    if not KONVY_CSV.exists():
        pytest.skip("ไม่มี konvy_product.csv")
    cols = ["product_name", "product_size", "size_unit", "product_pieces", "size_std", "unit_std", "size_flag"]
    k = pd.read_csv(KONVY_CSV, encoding="utf-8-sig", low_memory=False, usecols=cols)
    mine = ss.add_size_columns(k.drop(columns=["size_std", "unit_std", "size_flag"]))
    both = k["size_flag"].isin(ss.USABLE_FLAGS) & mine["size_flag"].isin(ss.USABLE_FLAGS)
    same = ((mine["size_std"] - k["size_std"]).abs() / k["size_std"] < 0.01) & (mine["unit_std"] == k["unit_std"])
    assert both.sum() > 30000
    assert same[both].mean() >= 0.985            # วัดได้ ~99.1% (ส่วนต่างหลักคือของแถมที่ผู้ให้ข้อมูลรวมเข้าไปด้วย)
    # ไม่ปล่อยแถวที่ผู้ให้ข้อมูลบอกว่าใช้ไม่ได้ผ่านเป็นของที่ใช้ได้มากเกินไป (<1%)
    wrongly_usable = (~k["size_flag"].isin(ss.USABLE_FLAGS)) & mine["size_flag"].isin(ss.USABLE_FLAGS)
    assert wrongly_usable.mean() < 0.01
