# -*- coding: utf-8 -*-
"""
เทสการจัดสินค้า (แคตตาล็อก Konvy; เดิม Watsons) เข้า taxonomy ของ product_category.csv (tool/product/euromonitor_mapping.py)

ไม่เรียก API - ใช้แถวปลอมที่จำลองปัญหาจริงของข้อมูลต้นทาง (ป้าย Watsons เสียบางแถว: ผ้าอนามัยติดป้าย Men's Shaving,
สีผมติดป้ายอาหารเสริม ฯลฯ) + เทสรวมกับไฟล์จริงแถวสุดท้าย (ข้ามถ้าไม่มี konvy_product.csv)

รัน: pytest main/tool/tests/test_euromonitor_mapping.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from product import euromonitor_mapping as em


def _row(name, pt=None, cat=None, sub=None, seg=None, industry=None):
    return {"product_name": name, "Product_Type": pt, "Category": cat, "Sub_category": sub, "Segment": seg,
            "Industry": industry}


def _classify(*args, **kw):
    r = em.classify_row(_row(*args, **kw))
    return r["EM_L1"], r["EM_L2"], r["EM_L3"], r["EM_L4"]


# ---------------------------------------------------------------------------
# taxonomy + resolve()
# ---------------------------------------------------------------------------

def test_taxonomy_is_the_single_source_and_rules_reference_real_l4():
    # import สำเร็จ = _validate() ผ่านแล้ว (ทุก L4 ที่กฎอ้างถึงมีในไฟล์) - เช็คเพิ่มว่าอ่านครบทุกระดับ
    assert ("Beauty and Personal Care", "Sun Care", "Adult Sun Care", "Face Sunscreen") in em.PATHS
    assert len(em.BY_L4) > 300
    assert em.BEAUTY_L1 == "Beauty and Personal Care" and em.GROUP_LEVEL == "L2"


def test_resolve_picks_level2_from_gender_for_l4_under_several_parents():
    assert em.resolve("Products For Shaving", "gillette proglide blades")[1] == "Men's Grooming"
    assert em.resolve("Products For Shaving", "gillette venus women blades")[1] == "Depilatories"
    assert em.resolve("Products With Antiperspirant Activity", "rexona men roll on")[1] == "Men's Grooming"
    assert em.resolve("Products With Antiperspirant Activity", "rexona roll on")[1] == "Deodorants"


def test_resolve_leaves_level3_blank_when_only_premium_vs_mass_differs():
    path = em.resolve("Cream", "moisturizing cream")
    assert path[1] == "Skin Care" and path[2] == "" and path[3] == "Cream"      # ข้อมูลไม่มีว่า Premium/Mass - ไม่เดา
    assert em.resolve("Face Mask")[2] == ""


def test_resolve_level3_from_text_and_fragrance_gender():
    assert em.resolve("Premium Fragrances", "eau de parfum for men")[2] == "Premium Men's Fragrances"
    assert em.resolve("Premium Fragrances", "eau de parfum")[2] == "Premium Fragrances"
    assert em.resolve("Other Tooth Care Products", "electric toothbrush head")[2] == "Electric Toothbrush Replacement Heads"
    assert em.resolve("B&C Toiletries", "baby wipes")[2] == "Baby Wipes"
    assert em.resolve("Hair Tie / Scrunchie")[:2] == ("Accessories", "Accessories")   # ชื่อ L4 มี " / " ในชื่อเอง ห้ามแยก


# ---------------------------------------------------------------------------
# classify_row(): ป้าย Watsons เสีย -> เชื่อชื่อสินค้า/ชนิดสินค้า
# ---------------------------------------------------------------------------

def test_sanitary_napkin_with_corrupted_men_shaving_labels_goes_to_intimate_hygiene():
    l1, l2, l3, l4 = _classify("Sofy Body Fit Slim Wing 23 cm. 16'S", "Shaving Cream", "Men's Grooming", "Shaving", "Men's Shaving")
    assert (l1, l2, l4) == ("Beauty and Personal Care", "Bath and Shower", "Sanitary Pads & Liners")


def test_eye_liner_is_not_mistaken_for_panty_liner():
    assert _classify("Cathy Doll Gel Liner 0.07g. Deep Brown", "Gel Liner", "Makeup", "Eye Makeup", "Eye Liner")[1:] \
        == ("Colour Cosmetics", "Eye Make-Up", "Eye Liner")
    assert _classify("Sofy Pantiliner Slim 20 Pcs.", "Pantyliner")[3] == "Sanitary Pads & Liners"
    assert _classify("Elis Panty Liner 15cm", "panty liner")[3] == "Sanitary Pads & Liners"


def test_non_beauty_items_hiding_in_beauty_labels_leave_the_beauty_l1():
    assert _classify("Sisse One Day Soft Contact Lens -3.25 (10 pcs)", "Moisturizing Cream", "Skincare", "Face Moisture", "Cream")[:2] \
        == ("Health & Wellness", "Eye Care")
    assert _classify("Pegavision Daily Kaori Laurel Brown-2.50 (10 pcs)", "Eye Contour Care", "Skincare", "Eye Contour Care")[3] \
        == "Daily Disposable Contact Lens"                                   # ชื่อมีแค่ค่าสายตา ไม่มีคำว่า lens
    assert _classify("Downy Liquid Concentrate Detergent 460 Ml.", "Laundry Detergent", "Hygiene & Bath")[:2] == ("Household", "Laundry Care")
    assert _classify("Kowa 3D Mask CTP Size M", "Face Mask", "Hygiene & Bath", "Bath & Shower", "Other Skin Cleansing")[1] \
        == "Protective Gear"
    assert _classify("Dr.PONG Magnesium Oxide 60 Capsules", "Magnesium Oxide Supplement", "General Health Supplements",
                     "Other Food Supplement", "Other Food Supplement Products", "Food Supplement")[0] == "Food Supplement"


def test_makeup_tools_and_toothbrush_set_are_not_confused():
    assert _classify("Essence Blush Brush 1pcs.", "Blush Brush", "Makeup")[1:] \
        == ("Makeup Tools & Equipment", "Makeup Tools", "Makeup Brushes (Face)")
    assert _classify("Dentiste Travel Pack (Toothpaste 20 G. + Toothbrush)", "Travel toothpaste and toothbrush set", "Hygiene & Bath",
                     "Oral Care")[1] == "Oral Care"
    assert _classify("Meilinda Handy Pocket Brush 4Pcs.", "Makeup Brush Set", "Makeup")[3] == "Makeup Brush Sets"


def test_name_overrides_wrong_label_but_keeps_watsons_segment_when_consistent():
    # สีผมติดป้ายอาหารเสริม -> Hair Care
    assert _classify("Phyto Permanent Color Ammonia-Free 3 Dark Brown", "permanent hair color", "Beauty Supplements",
                     "Hair Growth Supplement", "Hair Growth Capsule")[1] == "Hair Care"
    # น้ำหอมติดป้าย Lipstick -> Fragrances
    assert _classify("Za First Hug Eau De Parfum 20Ml.", "Eye Liner", "Makeup", "Eye Makeup", "Eye Liner")[1] == "Fragrances"
    # perfume body lotion เป็นโลชั่น ไม่ใช่น้ำหอม
    assert _classify("2SOME1 Whitening Perfume Body Lotion 40g.", "Perfume Body Lotion", "Fragrances", "Fine Fragrance",
                     "Premium Fragrances")[1] == "Skin Care"
    # Segment ของ Watsons ละเอียดกว่า (Premium/Mass ในชื่อ L4) -> เก็บไว้เมื่อ L2 ตรงกัน
    assert _classify("Dior Sauvage Eau De Parfum 60ml.", "Eau de parfum", "Fragrances", "Fine Fragrance", "Premium Fragrances")[3] \
        == "Premium Fragrances"
    assert _classify("Aqua+ Multi-Protection Sunscreen SPF 50+ 50ml.", "Sunscreen", "Skincare", "Face Sunscreen", "Face Sunscreen")[1:3] \
        == ("Sun Care", "Adult Sun Care")


def test_kids_products_stay_in_baby_and_child():
    assert _classify("BZU BZU Silky Soft Kids Shampoo 600ml.", "Kids Shampoo", "Hair Care", "Hair Care", "Shampoo")[1] \
        == "Baby and Child-specific Products"
    assert _classify("D-Nee For New Born Head Body Baby Wash 380 Ml.", "Baby wash", "Baby Care", "Baby Skincare", "B&C Skin Care")[1] \
        == "Baby and Child-specific Products"


def test_every_classification_is_a_real_taxonomy_path():
    rows = [("Sofy Wing 23 cm", "Sanitary Napkin"), ("Eucerin Hyaluron Serum 30 ml.", "Serum"),
            ("Mystery Product 100 g.", None), ("Hair It Magic Touch-Up Hair Mascara", "Hair Mascara"),
            ("Rexona Men Roll On 45 ml.", "Roll-on Deodorant"), ("Gillette Fusion Razor", "Razor")]
    valid = set(em.PATHS)
    for name, pt in rows:
        r = em.classify_row(_row(name, pt))
        path = (r["EM_L1"], r["EM_L2"], r["EM_L3"], r["EM_L4"])
        if r["EM_status"] == "mapped":
            assert path in valid or (path[2] == "" and any(p[:2] + p[3:] == path[:2] + path[3:] for p in valid)), (name, path)
        else:
            assert path == ("", "", "", "") and r["EM_Group"] == em.UNMAPPED


# ---------------------------------------------------------------------------
# Category ของต้นทางที่เป็นชื่อ Level 2 ของ taxonomy (Konvy) ใช้ตัดสิน L4 ที่อยู่ใต้หลาย parent
# ---------------------------------------------------------------------------

def test_source_category_that_is_a_level2_name_breaks_ties_for_ambiguous_l4():
    # มีดโกนผู้หญิงที่ชื่อไม่บอกเพศ: ไม่มีป้าย -> Men's Grooming (ค่าตั้งต้นของ L4 นี้); ป้าย Category = Depilatories -> Depilatories
    razor = {"product_name": "Schick Intuition Perfect Touch 83g", "Product_Type": "Five-Blade Razor",
             "Segment": "Products For Shaving"}
    assert em.classify_row({**razor})["EM_L2"] == "Men's Grooming"
    assert em.classify_row({**razor, "Category": "Depilatories"})["EM_L2"] == "Depilatories"
    # antiperspirant ของแบรนด์ผู้ชาย: ค่าตั้งต้น Deodorants; ป้าย Men's Grooming -> Men's Grooming
    deo = {"product_name": "EXPLOR Body Spray Ocean Black 100ml", "Product_Type": "Body Spray Deodorant",
           "Segment": "Products With Antiperspirant Activity"}
    assert em.classify_row({**deo})["EM_L2"] == "Deodorants"
    assert em.classify_row({**deo, "Category": "Men's Grooming"})["EM_L2"] == "Men's Grooming"


def test_source_category_that_is_not_a_level2_name_has_no_effect():
    razor = {"product_name": "Schick Intuition Perfect Touch 83g", "Product_Type": "Five-Blade Razor",
             "Segment": "Products For Shaving"}
    assert em.classify_row({**razor, "Category": "Skincare"}) == em.classify_row({**razor})   # ป้ายแบบ Watsons เดิม


# ---------------------------------------------------------------------------
# load_catalog(): กรอง L1 = Beauty and Personal Care, index คงเลขแถวเดิม
# ---------------------------------------------------------------------------

def test_load_catalog_keeps_only_beauty_l1_and_original_row_index(tmp_path):
    csv = tmp_path / "mini.csv"
    pd.DataFrame([
        {"brand": "A", "product_name": "Eucerin Hyaluron Serum 30 ml.", "Product_Type": "Serum", "Category": "Skincare",
         "Sub_category": "Face Moisture", "Segment": "Serum", "Industry": "Personal Care / Cosmetics"},
        {"brand": "B", "product_name": "Sisse One Day Soft Contact Lens (10 pcs)", "Product_Type": "Contact Lens", "Category": None,
         "Sub_category": None, "Segment": None, "Industry": None},
        {"brand": "C", "product_name": "Kundal Shampoo 500 Ml.", "Product_Type": "Shampoo", "Category": "Hair Care",
         "Sub_category": "Hair Care", "Segment": "Shampoo", "Industry": "Personal Care / Cosmetics"},
    ]).to_csv(csv, index=False, encoding="utf-8-sig")

    beauty = em.load_catalog(csv)
    assert list(beauty.index) == [0, 2]                       # แถว 1 (คอนแทคเลนส์) ถูกกรอง - index ไม่ถูก reset
    assert list(beauty["EM_Group"]) == ["Skin Care", "Hair Care"]   # EM_Group = Level 2
    assert set(beauty["EM_L1"]) == {"Beauty and Personal Care"}

    everything = em.load_catalog(csv, beauty_only=False)
    assert len(everything) == 3 and everything.loc[1, "EM_L1"] == "Health & Wellness"

    narrow = em.load_catalog(csv, usecols=["brand", "product_name"])   # ขอแค่บางคอลัมน์ - คอลัมน์จัดหมวดถูกเพิ่มให้เอง
    assert {"brand", "product_name", "EM_L2", "EM_Group"} <= set(narrow.columns) and len(narrow) == 2


# ---------------------------------------------------------------------------
# ไฟล์จริงทั้งชุด
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_catalog():
    if not em.CSV_PATH.exists():
        pytest.skip("ไม่มี market_product.csv (รัน tool/product/build_market_catalog.py)")
    return em.load_catalog(beauty_only=False)


def test_real_catalog_every_row_has_a_valid_path_and_beauty_is_the_majority(real_catalog):
    assert (real_catalog["EM_status"] == "unmapped").sum() == 0
    valid = set(em.PATHS)
    valid_blank_l3 = {(a, b, d) for a, b, _, d in valid}
    paths = set(zip(real_catalog.EM_L1, real_catalog.EM_L2, real_catalog.EM_L3, real_catalog.EM_L4))
    bad = [p for p in paths if p not in valid and not (p[2] == "" and (p[0], p[1], p[3]) in valid_blank_l3)]
    assert bad == []
    beauty = real_catalog[real_catalog["EM_L1"] == em.BEAUTY_L1]
    assert len(beauty) > 0.75 * len(real_catalog)
    assert {"Skin Care", "Colour Cosmetics", "Hair Care", "Sun Care"} <= set(beauty["EM_Group"])


# ---------------------------------------------------------------------------
# ผล LLM: pick_label / apply_llm_labels / load_catalog(labels=...) / ตัวแยกคำตอบ
# ---------------------------------------------------------------------------

def _id(l2, l4):
    """รหัส path แรกในไฟล์ที่ตรง L2 + L4 (เทสไม่ผูกกับเลขลำดับตายตัว)"""
    return next(i for i, p in em.PATH_BY_ID.items() if p[1] == l2 and p[3] == l4)


def test_pick_label_two_votes_agree_disagree_and_single():
    skin, cream = _id("Skin Care", "Serum"), _id("Skin Care", "Cream")
    frag, hair = _id("Fragrances", "Body Mists & Splashes"), _id("Hair Care", "Shampoo")
    # 2 รอบตรงกันที่ L2 (path ละเอียดต่างกันได้) -> ใช้รอบที่มั่นใจกว่า
    assert em.pick_label({"hints": (skin, 3), "nohints": (cream, 2)}, "Colour Cosmetics") == (skin, "high", "llm")
    assert em.pick_label({"hints": (skin, 1), "nohints": (cream, 3)}, "x")[0] == cream
    assert em.pick_label({"hints": (skin, 2), "nohints": (cream, 1)}, "x")[1] == "medium"
    # ไม่ตรง -> เลือกรอบที่ตรงกับกฎ (ทั้งสองทิศ)
    assert em.pick_label({"hints": (frag, 2), "nohints": (skin, 3)}, "Skin Care") == (skin, "medium", "llm(no-hints)+rules")
    assert em.pick_label({"hints": (skin, 2), "nohints": (frag, 3)}, "Skin Care") == (skin, "medium", "llm(hints)+rules")
    # ไม่ตรงกันทั้งสามฝ่าย -> รอบที่ส่งคำใบ้ ความมั่นใจต่ำ
    assert em.pick_label({"hints": (skin, 3), "nohints": (hair, 3)}, "Oral Care") == (skin, "low", "llm(hints,disputed)")
    # รอบเดียว / ตอบ 0 (ไม่เข้าหมวดไหน) -> None = ใช้กฎ
    assert em.pick_label({"nohints": (hair, 3)}, "x") == (hair, "high", "llm(single)")
    assert em.pick_label({"hints": (0, 3), "nohints": (0, 3)}, "x") is None
    assert em.pick_label({"hints": (999999, 3)}, "x") is None


def test_apply_llm_labels_overrides_rules_keeps_rule_columns_and_falls_back():
    rows = pd.DataFrame([
        {"brand": "A", "product_name": "Siriraj Moisturizing Lotion 180 ml.", "Product_Type": "Contact Lenses", "Category": None,
         "Sub_category": None, "Segment": None, "Industry": None},          # ป้ายเสีย: กฎเชื่อ Product_Type -> Eye Care
        {"brand": "B", "product_name": "Kundal Shampoo 500 Ml.", "Product_Type": "Shampoo", "Category": "Hair Care",
         "Sub_category": "Hair Care", "Segment": "Shampoo", "Industry": None},   # ไม่มีผล LLM -> คงผลกฎ
    ])
    rows = em.add_euromonitor_columns(rows)
    assert rows.loc[0, "EM_L2"] == "Eye Care"
    lotion = _id("Skin Care", "General Body Moisturizer")
    labels = {em.product_key(rows.loc[0].to_dict()): {"hints": (lotion, 3), "nohints": (lotion, 3)}}
    out = em.apply_llm_labels(rows, labels)
    assert (out.loc[0, "EM_L1"], out.loc[0, "EM_L2"], out.loc[0, "EM_Group"]) == ("Beauty and Personal Care", "Skin Care", "Skin Care")
    assert out.loc[0, "EM_source"] == "llm" and out.loc[0, "EM_confidence"] == "high"
    assert out.loc[0, "EM_rule_L2"] == "Eye Care"                         # ผลของกฎเก็บไว้เทียบ
    assert out.loc[1, "EM_L2"] == "Hair Care" and not out.loc[1, "EM_source"].startswith("llm")
    assert rows.loc[0, "EM_L2"] == "Eye Care"                              # ไม่แก้ DataFrame ที่ส่งเข้ามา


def test_load_catalog_uses_injected_llm_labels_before_the_beauty_filter(tmp_path):
    csv = tmp_path / "mini.csv"
    pd.DataFrame([
        {"brand": "A", "product_name": "Sofy Body Fit Wing 23 cm.", "Product_Type": "Shaving Cream", "Category": "Men's Grooming",
         "Sub_category": "Shaving", "Segment": "Men's Shaving", "Industry": None},
        {"brand": "B", "product_name": "Mystery Capsules 30 tabs", "Product_Type": "Cream", "Category": "Skincare",
         "Sub_category": "Face Moisture", "Segment": "Cream", "Industry": None},
    ]).to_csv(csv, index=False, encoding="utf-8-sig")
    raw = pd.read_csv(csv, encoding="utf-8-sig")
    vit = _id("Vitamins & Minerals", "Other Vitamin Supplement")
    labels = {em.product_key(raw.loc[1].to_dict()): {"hints": (vit, 3), "nohints": (vit, 3)}}   # LLM: อาหารเสริม ไม่ใช่ความงาม
    beauty = em.load_catalog(csv, labels=labels)
    assert list(beauty.index) == [0]                                       # แถว 1 ถูก LLM ย้ายไป Food Supplement แล้วกรองออก
    assert em.load_catalog(csv, beauty_only=False, labels=labels).loc[1, "EM_L1"] == "Food Supplement"
    assert em.load_catalog(csv, beauty_only=False, use_llm=False).loc[1, "EM_L1"] == "Beauty and Personal Care"   # กฎล้วน


def test_llm_answer_parser_user_prompt_and_missing_item_retry():
    from product import classify_products_llm as c

    pid = _id("Skin Care", "Serum")
    # ตรวจรหัสกับไฟล์จริง: เลขสินค้านอกชุด / path id ไม่มีจริง / ความมั่นใจนอก 1-3 -> ทิ้ง; 0 = ไม่เข้าหมวดไหน ผ่าน
    text = '{"r": [[1, %d, 3], [2, 0, 1], [3, 999999, 2], [9, %d, 3], [2, %d, 2], [1, %d, 7]]}' % (pid, pid, pid, pid)
    assert c.parse_answer(text, 3) == {1: (pid, 3), 2: (0, 1)}             # รายการซ้ำเลขเดิม ใช้ตัวแรก
    assert c.parse_answer("not json at all", 3) == {}
    assert len(c.paths_table().splitlines()) == len(em.PATHS) and c.paths_table().splitlines()[0].startswith("1 | ")

    row = {"brand": "Eucerin", "product_name": "Hyaluron Serum 30 ml.", "Product_Type": "Serum", "Segment": "Serum", "sale_price_thb": "1,290.00"}
    with_hints, without = c.user_prompt([row], True), c.user_prompt([row], False)
    assert 'retailer_type="Serum"' in with_hints and 'retailer_segment="Serum"' in with_hints and "price_thb=1290" in with_hints
    assert "retailer_type" not in without and 'name="Hyaluron Serum 30 ml."' in without

    class FakeClient:   # รอบแรกตอบแค่ชิ้นที่ 1 และ 3 จาก 3 ชิ้น -> ต้องถามซ้ำเฉพาะชิ้นที่ขาด
        def __init__(self):
            self.calls = []
            self.chat = self
            self.completions = self

        def create(self, **kw):
            n_items = kw["messages"][1]["content"].count("\n") 
            self.calls.append(n_items)
            reply = '{"r": [[1, %d, 3], [3, %d, 2]]}' % (pid, pid) if len(self.calls) == 1 else '{"r": [[1, %d, 3]]}' % pid
            msg = type("M", (), {"content": reply})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    client = FakeClient()
    answers, calls = c.classify_batch(client, "fake-model", [row, row, row], use_hints=True, log=lambda *_: None)
    assert answers == {0: (pid, 3), 2: (pid, 2), 1: (pid, 3)} and calls == 2
    assert client.calls == [3, 1]                                           # รอบที่ 2 ถามเหลือ 1 ชิ้น


def test_product_key_is_stable_across_whitespace_but_not_across_products():
    a = {"brand": "Eucerin", "product_name": "Hyaluron Serum 30 ml.", "Product_Type": "Serum"}
    assert em.product_key(a) == em.product_key({**a, "brand": "  Eucerin ", "product_name": "Hyaluron Serum 30 ml. "})
    assert em.product_key(a) != em.product_key({**a, "product_name": "Hyaluron Serum 50 ml."})
