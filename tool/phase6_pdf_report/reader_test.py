# -*- coding: utf-8 -*-
"""
ชุดทดสอบผู้อ่านจริงของรายงาน ⑯/⑰/⑱ (🆕 2026-10-12 ขั้น E ของแผนภาษาง่าย)

ใช้ตรวจว่าคนทั่วไป (ไม่ใช่นักวิเคราะห์) "เข้าใจข้อความสำคัญในรายงานตรงกับที่เราตั้งใจ" - สคริปต์ตรวจภาษา (lint_report_language.py)
ตรวจได้แค่คำต้องห้าม/ความยาว ไม่รู้ว่าคนอ่านเข้าใจจริงหรือไม่

ขั้นตอน:
  1) สร้างชุด:   python reader_test.py sheet --lang th            -> output/_reader_test/ (ใบคำถามผู้อ่าน + เฉลยผู้ดำเนินการ + ใบตอบ CSV)
  2) ให้ผู้อ่าน 3-5 คน (ไม่ใช่ DA) เปิดรายงานฉบับจริงแล้วตอบ ~15 นาทีต่อคน - ห้ามอธิบายคำถามระหว่างทำ
  3) กรอกคำตอบลง CSV (1 แถว/คน)   python reader_test.py score answers.csv --lang th --md result.md
  4) ผล: ผ่านเมื่อตอบถูกรวม >= 80% และทุกข้อ >= 60% - ข้อที่ไม่ผ่านจะบอกว่าต้องเขียนข้อความไหนใหม่ (คีย์ในตารางข้อความ)

คำถามอ้างข้อความจริงจากตารางข้อความ (i18n / brand_i18n / brand_category_i18n / unit_i18n) - ถ้าแก้ข้อความ ใบคำถามจะตามไปเอง
"""
import argparse
import csv
import json
import sys
from collections import Counter, OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import brand_category_i18n  # noqa: E402
import brand_i18n  # noqa: E402
import i18n  # noqa: E402
import unit_i18n  # noqa: E402
from common.horizons import apply_tokens  # noqa: E402   # i18n เพิ่ม tool/ เข้า sys.path ให้แล้ว

OUTPUT_ROOT = HERE.parents[1] / "output"
DEFAULT_OUT = OUTPUT_ROOT / "_reader_test"

PASS_OVERALL = 0.80        # ตอบถูกรวมอย่างน้อย
PASS_PER_QUESTION = 0.60   # ทุกข้อต้องถูกอย่างน้อย
MIN_READERS = 3
UNSURE = "?"
LETTERS = "abcd"

REPORT_NAMES = {
    "trend": {"th": "⑯ รายงานเทรนด์", "en": "Trend report"},
    "brand": {"th": "⑰ รายงานความพร้อมของแบรนด์ต่อเทรนด์", "en": "Brand fit report"},
    "category": {"th": "⑱ รายงานเทียบสินค้าตามหมวดและกลุ่มราคา", "en": "Category x price-tier report"},
}
REPORT_PREFIX = {"trend": "T", "brand": "B", "category": "C"}


def _tables():
    """ตารางข้อความของแต่ละรายงาน (ใช้ชุดราคาต่อปริมาณทับ เพราะรายงานปัจจุบันใช้เกณฑ์นี้)"""
    return {"trend": i18n.STRINGS, "brand": brand_i18n.BRAND_STRINGS, "category": brand_category_i18n.CATEGORY_STRINGS}


def text_of(table, key, lang, **fmt):
    """ข้อความจริงของรายงาน (ชุดราคาต่อปริมาณทับถ้ามีคีย์นั้น เหมือนที่รายงานใช้ตอน tier_basis = unit_price) เติมตัวแทนค่าตาม fmt;
    ไม่เจอคีย์ = KeyError"""
    unit = unit_i18n.UNIT_STRINGS.get(lang, {})
    value = unit[key] if key in unit else _tables()[table][lang][key]
    try:
        return value.format(**fmt) if fmt else value
    except (KeyError, IndexError):
        return value


def effective_ref(ref, lang="th"):
    """"brand.vs_note" -> "unit.vs_note" เมื่อรายงานใช้ข้อความชุดราคาต่อปริมาณทับคีย์นั้น (แก้ที่ unit_i18n ไม่ใช่ต้นฉบับ)"""
    table, key = ref.split(".", 1)
    if table != "unit" and key in unit_i18n.UNIT_STRINGS.get(lang, {}):
        return f"unit.{key}"
    return ref


def rewrite_refs(question, lang="th"):
    """คีย์ที่ต้องแก้ของข้อนี้ - ตัดซ้ำหลังแปลงเป็นคีย์ที่รายงานใช้จริง"""
    return list(OrderedDict.fromkeys(effective_ref(r, lang) for r in question["rewrite"]))


def ref_text(ref, lang="th"):
    table, key = ref.split(".", 1)
    source = unit_i18n.UNIT_STRINGS[lang] if table == "unit" else _tables()[table][lang]
    return source[key]


# ---------------------------------------------------------------------------
# คลังคำถาม - ไม่ผูกกับรอบ (ตัวเลขในตัวอย่างเป็นค่าสมมติ) ต่อ 1 ข้อ: คำตอบถูก 1 + ตัวลวง 3 (slot = ตำแหน่ง a-d ของคำตอบถูก)
# ---------------------------------------------------------------------------
def _o(th, en):
    return {"th": th, "en": en}


QUESTIONS = [
    # ----------------------------- ⑯ รายงานเทรนด์
    {
        "id": "T1", "report": "trend", "topic": "ตัวเลข % ที่คาดของปีที่ @S@",
        "where": _o("หน้าเทรนด์ · ตัวเลข % ของ “ปีที่ @S@”", "Trend page - the % shown for 'Year @S@'"),
        "stem": _o("ในหน้าเทรนด์ ปีที่ @S@ แสดงตัวเลข “+29%” ข้อใดอธิบายตัวเลขนี้ได้ถูกที่สุด?",
                   "On a trend page, Year @S@ shows '+29%'. Which statement describes it best?"),
        "correct": _o("ยอดค้นหาในปีที่ @S@ คาดว่าสูงกว่าค่าเฉลี่ย 12 เดือนล่าสุดอยู่ 29%",
                      "Searches in year @S@ are expected to be 29% above the last-12-month average"),
        "wrong": [_o("ยอดขายสินค้าในเทรนด์นี้จะเพิ่มขึ้น 29%", "Sales of products in this trend will rise 29%"),
                  _o("ผู้บริโภค 29% สนใจเทรนด์นี้", "29% of consumers are interested in this trend"),
                  _o("เทรนด์นี้จะโตขึ้น 29% ทุกปีติดต่อกัน", "This trend will grow 29% every year in a row")],
        "slot": 1,
        "rewrite": ["trend.t5_note", "trend.t5_tl_year", "trend.t5_tl_rank", "trend.rank_score"],
    },
    {
        "id": "T2", "report": "trend", "topic": "ทำไม % ระยะยาวสูงกว่า",
        "where": _o("หน้าสรุป Top 5 / แถบเส้นเวลา ปีที่ @S@ กับปีที่ 5", "Top-5 summary / timeline strip, Year @S@ and Year 5"),
        "quotes": {"q": ("trend", "t5_tl_key", {})},
        "stem": _o("หน้าสรุประบุว่า % ระยะยาว (ปีที่ 5) สูงกว่าระยะสั้น (ปีที่ @S@) เกือบทุกเทรนด์ เพราะอะไร?",
                   "The summary shows long-term % (Year 5) higher than short-term % (Year @S@) for almost every trend. Why?"),
        "correct": _o("เพราะนับสะสมจากฐานเดียวกัน ยิ่งไกลก็ยิ่งสะสมมาก ไม่ใช่เติบโตต่อปี",
                      "Because both are counted from the same baseline, so a further year accumulates more - it is not a per-year rate"),
        "wrong": [_o("เพราะเทรนด์เร่งตัวขึ้นทุกปี", "Because every trend speeds up each year"),
                  _o("เพราะระยะยาวใช้ข้อมูลมากกว่า จึงแม่นกว่า", "Because the long term uses more data and is more accurate"),
                  _o("เพราะระยะยาวเลือกเฉพาะเทรนด์ที่ดีที่สุด", "Because the long term only picks the best trends")],
        "slot": 2,
        "rewrite": ["trend.t5_tl_key", "trend.t5_tl_base", "trend.t5_note"],
    },
    {
        "id": "T3", "report": "trend", "topic": "“ตรงเทรนด์อันดับ N จากทั้งร้าน”",
        "where": _o("หน้าสินค้าที่ตรงเทรนด์ · ข้อความใต้ชื่อสินค้า", "Matching-products page - text under a product name"),
        "quotes": {"q": ("trend", "cat_rank", {"n": 3})},
        "stem": _o("ใต้ชื่อสินค้ามีข้อความ “{q}” ข้อความนี้หมายถึงอะไร?",
                   "Under a product name it says \"{q}\". What does it mean?"),
        "correct": _o("คำอธิบายสินค้านี้ตรงกับเทรนด์เป็นอันดับ 3 เมื่อเทียบสินค้าทั้งร้าน",
                      "This product's description matches the trend 3rd best out of all products in the store"),
        "wrong": [_o("สินค้านี้ขายดีเป็นอันดับ 3 ของร้าน", "This product is the 3rd best seller in the store"),
                  _o("สินค้านี้ราคาถูกเป็นอันดับ 3 ของร้าน", "This product is the 3rd cheapest in the store"),
                  _o("สินค้านี้ได้รีวิวดีเป็นอันดับ 3 ของร้าน", "This product has the 3rd best reviews in the store")],
        "slot": 0,
        "rewrite": ["trend.cat_rank", "trend.cat_note", "trend.cat_note_tiers"],
    },
    {
        "id": "T4", "report": "trend", "topic": "“ตรงเทรนด์” ยืนยันอะไรได้บ้าง",
        "where": _o("หน้าสินค้าที่ตรงเทรนด์ · หมายเหตุท้ายหน้า", "Matching-products page - footnote"),
        "quotes": {"q": ("trend", "cat_note_tiers", {"n": 27000})},
        "stem": _o("รายงานบอกว่าสินค้า “ตรงเทรนด์” ข้อใดถูกต้อง?",
                   "The report says a product 'matches' the trend. Which statement is correct?"),
        "correct": _o("คำอธิบายสินค้าใกล้เคียงกับเทรนด์ แต่ยังไม่ได้ยืนยันว่าให้ผลตามเทรนด์จริง",
                      "The product description is close to the trend, but it is not confirmed to deliver it"),
        "wrong": [_o("สินค้านี้ให้ผลตามเทรนด์แล้ว", "The product already delivers the trend"),
                  _o("สินค้านี้ผ่านการทดสอบทางคลินิก", "The product passed clinical testing"),
                  _o("สินค้านี้ขายดีที่สุดในเทรนด์", "The product is the best seller in the trend")],
        "slot": 3,
        "rewrite": ["trend.cat_note", "trend.cat_note_tiers", "unit.cat_note_tiers", "unit.m_limits"],
    },
    {
        "id": "T5", "report": "trend", "topic": "ราคาต่อปริมาณ ต่ำ/กลาง/สูง",
        "where": _o("หน้าสินค้าที่ตรงเทรนด์ · หัวคอลัมน์ช่วงราคา", "Matching-products page - price-group column heading"),
        "quotes": {"q": ("trend", "tier_low", {})},
        "stem": _o("สินค้าอยู่ในคอลัมน์ “{q}” หมายถึงอะไร?", "A product sits in the column \"{q}\". What does that mean?"),
        "correct": _o("ราคาต่อ มล./ก./ชิ้น ของสินค้าต่ำ เมื่อเทียบกับสินค้าชนิดเดียวกันในร้าน",
                      "Its price per ml / g / piece is low compared with products of the same type in the store"),
        "wrong": [_o("ราคาขายต่อชิ้นถูกที่สุดในหน้านี้", "It has the lowest shelf price on this page"),
                  _o("สินค้าลดราคาอยู่", "It is on sale"),
                  _o("สินค้าขนาดเล็ก", "It is a small size")],
        "slot": 1,
        "rewrite": ["trend.tier_low", "trend.tier_mid", "trend.tier_high", "unit.cat_note_tiers", "unit.m_tier"],
    },
    {
        "id": "T6", "report": "trend", "topic": "เครื่องหมาย * ที่ตัวเลข 12 เดือนล่าสุด",
        "where": _o("หน้าเทรนด์ · ตัวเลข “12 เดือนที่ผ่านมา” ที่มี *", "Trend page - the '12 months' figure marked with *"),
        "quotes": {"q": ("trend", "past_note", {})},
        "stem": _o("ตัวเลข 12 เดือนที่ผ่านมามีเครื่องหมาย * ควรใช้ตัวเลขนี้เทียบเทรนด์หรือไม่?",
                   "The last-12-months figure carries an asterisk (*). Should it be used to compare trends?"),
        "correct": _o("ไม่ควร เพราะข้อมูลของทุกคำกระโดดขึ้นพร้อมกัน ตัวเลขจึงสูงเกินจริง ให้ดูตัวเลขที่คาดแทน",
                      "No - the data for every keyword jumped at once, so it is inflated; use the expected figures instead"),
        "wrong": [_o("ควร เพราะเป็นข้อมูลจริง", "Yes, because it is real data"),
                  _o("ไม่ควร เพราะข้อมูลผิดพลาด ต้องรอการแก้ไข", "No, because the data is wrong and awaiting a fix"),
                  _o("ควร แต่ต้องนำไปคูณด้วย 2", "Yes, but multiply it by 2 first")],
        "slot": 0,
        "rewrite": ["trend.past_note", "trend.t5_past"],
    },
    # ----------------------------- ⑰ รายงานความพร้อมของแบรนด์ต่อเทรนด์
    {
        "id": "B1", "report": "brand", "topic": "เกรดภาพรวม",
        "where": _o("หน้าสรุปผู้บริหาร · กล่องภาพรวม", "Executive summary - overall box"),
        "quotes": {"q": ("brand", "overall_rule", {})},
        "stem": _o("หน้าสรุประบุ “ภาพรวม: Good” (เกรดมี Excellent / Good / Average / Below average) ข้อใดอธิบายได้ถูกที่สุด?",
                   "The summary says 'Overall: Good' (grades are Excellent / Good / Average / Below average). Which is correct?"),
        "correct": _o("ในเทรนด์เกินครึ่ง สินค้าที่ดีที่สุดของแบรนด์อยู่ใน 5% แรกของสินค้าประเภทและกลุ่มราคาเดียวกัน",
                      "In more than half of the trends, the brand's best product is in the top 5% of products of the same type and price group"),
        "wrong": [_o("สินค้าทุกชิ้นของแบรนด์ได้คะแนนดี", "Every product of the brand scored well"),
                  _o("แบรนด์ขายดีเป็นอันดับ 5 ของตลาด", "The brand is the 5th best seller in the market"),
                  _o("ตรงเทรนด์เพียง 5% ของสินค้าทั้งหมดของแบรนด์", "Only 5% of the brand's products match trends")],
        "slot": 2,
        "rewrite": ["brand.overall_rule", "brand.overall_line", "brand.lv_def_first", "brand.lv_def_mid", "brand.lv_def_last"],
    },
    {
        "id": "B2", "report": "brand", "topic": "“ติด x% แรก (อันดับ n)”",
        "where": _o("หน้าเทรนด์ของแบรนด์ · แถว “ตำแหน่งในกลุ่ม”", "Brand trend page - the 'position in group' row"),
        "quotes": {"q": ("brand", "pct_val", {"p": 5, "rank": 12})},
        "stem": _o("ในแถว “ตำแหน่งในกลุ่ม” ของสินค้าแบรนด์เขียนว่า “{q}” หมายถึงอะไร?",
                   "In a brand product's 'position in group' row it says \"{q}\". What does it mean?"),
        "correct": _o("สินค้านี้ตรงเทรนด์เป็นอันดับ 12 ในกลุ่มสินค้าที่นำมาเทียบกัน และอยู่ใน 5% บนสุดของกลุ่มนั้น",
                      "This product matches the trend 12th best in the group it is compared in, which puts it in that group's top 5%"),
        "wrong": [_o("สินค้านี้ขายได้ 5% ของยอดขายตลาด", "This product makes 5% of market sales"),
                  _o("สินค้านี้ลดราคาอยู่ 5%", "This product is discounted 5%"),
                  _o("สินค้านี้อยู่อันดับ 12 ของสินค้าทุกประเภทในตลาด", "This product ranks 12th among all products in the market")],
        "slot": 0,
        "rewrite": ["brand.pct_val", "brand.pct_row", "brand.vs_note", "unit.m_rank"],
    },
    {
        "id": "B3", "report": "brand", "topic": "ช่องสีฟ้าในตารางเทียบ",
        "where": _o("หน้าเทียบสินค้า 5 อันดับแรกของกลุ่ม", "Top-5 comparison page"),
        "quotes": {"q": ("brand", "vs_note", {"brand": "Brand"})},
        "stem": _o("ในตารางเทียบสินค้า 5 อันดับแรก ช่องสีฟ้าคืออะไร?",
                   "In the top-5 comparison table, what is a blue cell?"),
        "correct": _o("สินค้าของแบรนด์ลูกค้า", "A product of the customer's brand"),
        "wrong": [_o("สินค้าที่ราคาถูกที่สุด", "The cheapest product"),
                  _o("สินค้าที่เพิ่งวางขายใหม่", "A newly launched product"),
                  _o("สินค้าที่ตรงเทรนด์ที่สุดของทั้งตลาด", "The best match in the whole market")],
        "slot": 3,
        "rewrite": ["brand.vs_note", "unit.vs_note", "brand.your_tag"],
    },
    {
        "id": "B4", "report": "brand", "topic": "“ไม่มีสินค้าในหมวดของเทรนด์”",
        "where": _o("หน้าเทรนด์ของแบรนด์ · เมื่อไม่มีสินค้าในหมวด", "Brand trend page - when the brand has no product in the category"),
        "quotes": {"q": ("brand", "no_key_short", {})},
        "stem": _o("เทรนด์หนึ่งขึ้นว่า “{q}” หมายถึงอะไร?", "A trend shows \"{q}\". What does it mean?"),
        "correct": _o("แบรนด์ยังไม่ได้ขายสินค้าในหมวดหลักที่เทรนด์นี้อยู่",
                      "The brand does not yet sell any product in the main category this trend belongs to"),
        "wrong": [_o("ไม่มีสินค้าใดในตลาดที่ตรงเทรนด์นี้", "No product in the market matches this trend"),
                  _o("ระบบเทียบสินค้าไม่สำเร็จ", "The comparison failed"),
                  _o("สินค้าของแบรนด์หมดสต็อก", "The brand's products are out of stock")],
        "slot": 1,
        "rewrite": ["brand.no_key_short", "brand.no_key", "brand.lv_def_last"],
    },
    {
        "id": "B5", "report": "brand", "topic": "แนวทาง “สร้างใหม่”",
        "where": _o("หน้าสรุป · ตารางเทรนด์/แนวทาง", "Summary - trend and action table"),
        "quotes": {"q": ("brand", "build_def", {})},
        "stem": _o("เทรนด์ที่ถูกจัดเป็นแนวทาง “สร้างใหม่” หมายถึงอะไร?",
                   "A trend labelled 'Build' - what does that mean?"),
        "correct": _o("คาดว่าการค้นหาจะเพิ่มมาก แต่แบรนด์ยังไม่มีสินค้าที่แข็งพอ จึงเป็นโอกาสพัฒนาสินค้า",
                      "Searches are expected to rise a lot but the brand has no strong product yet - a chance to develop one"),
        "wrong": [_o("ควรเลิกขายสินค้าที่เกี่ยวข้อง", "The related products should be discontinued"),
                  _o("เทรนด์นี้กำลังตกลง", "The trend is fading"),
                  _o("ควรเปลี่ยนชื่อและบรรจุภัณฑ์สินค้าเดิม", "Existing products should be renamed and repackaged")],
        "slot": 2,
        "rewrite": ["brand.build", "brand.build_def", "brand.defend_def", "brand.maintain_def", "brand.monitor_def"],
    },
    # ----------------------------- ⑱ รายงานเทียบสินค้าตามหมวดและกลุ่มราคา
    {
        "id": "C1", "report": "category", "topic": "ใครเลือกหมวดของเทรนด์",
        "where": _o("หน้าสรุป · กล่อง “วิธีเทียบ”", "Summary - the 'how it is compared' box"),
        "quotes": {"q": ("category", "cat_how_body", {"brand": "Brand"})},
        "stem": _o("แต่ละเทรนด์ถูกจัดไว้ในหมวดสินค้าหมวดเดียว หมวดนั้นถูกเลือกโดยใคร / อย่างไร?",
                   "Each trend is placed in one product category. Who or what picks that category?"),
        "correct": _o("AI เลือกจากความหมายของเทรนด์", "An AI picks it from what the trend means"),
        "wrong": [_o("แบรนด์ลูกค้าเลือกเอง", "The customer brand picks it"),
                  _o("เลือกจากยอดขายสูงสุดของหมวด", "It is picked by the category with the highest sales"),
                  _o("ทีมงานคัดเลือกด้วยมือทีละสินค้า", "A team picks it by hand, product by product")],
        "slot": 3,
        "rewrite": ["category.cat_how_body", "unit.cat_how_body", "unit.cat_note_main"],
    },
    {
        "id": "C2", "report": "category", "topic": "สินค้าถูกเทียบกับสินค้าแบบไหน",
        "where": _o("หน้าสรุป · กล่อง “วิธีเทียบ” หรือหน้าหมวด", "Summary - 'how it is compared' box, or a category page"),
        "quotes": {"q": ("category", "cat_how_body", {"brand": "Brand"})},
        "stem": _o("สินค้าของแบรนด์ในหน้าหมวดถูกนำไปเทียบกับสินค้าแบบไหน?",
                   "In a category page, which products is the brand's product compared with?"),
        "correct": _o("สินค้าในหมวดเดียวกัน และอยู่ในกลุ่มราคาต่อปริมาณเดียวกัน",
                      "Products in the same category and in the same unit-price group"),
        "wrong": [_o("สินค้าทั้งตลาดทุกประเภท", "All products in the market of every type"),
                  _o("สินค้าของแบรนด์คู่แข่งที่ราคาใกล้เคียงกัน", "Competitor products at a similar shelf price"),
                  _o("สินค้าที่เพิ่งเปิดตัวในปีนี้", "Products launched this year")],
        "slot": 0,
        "rewrite": ["unit.cat_how_body", "unit.m_tier", "unit.m_rank"],
    },
    {
        "id": "C3", "report": "category", "topic": "“ติด x% แรกของกลุ่ม” กับ “ทั้งร้าน: อันดับ n”",
        "where": _o("หน้าหมวด · การ์ดสินค้าที่ดีที่สุดของแบรนด์", "Category page - the brand's best product card"),
        "quotes": {"q1": ("category", "top_pct", {"p": 20}), "q2": ("category", "market_rank", {"rank": 45})},
        "stem": _o("การ์ดสินค้าแสดง “{q1}” และ “{q2}” สองข้อความนี้ต่างกันอย่างไร?",
                   "A product card shows \"{q1}\" and \"{q2}\". How do the two differ?"),
        "correct": _o("ข้อแรกเทียบเฉพาะสินค้ากลุ่มราคาต่อปริมาณเดียวกัน ข้อหลังเทียบสินค้าทั้งร้านทุกกลุ่ม",
                      "The first compares only within the same unit-price group; the second compares against the whole store"),
        "wrong": [_o("ไม่ต่างกัน เป็นข้อมูลเดียวกัน", "They do not differ - it is the same figure"),
                  _o("ข้อแรกวัดยอดขาย ข้อหลังวัดความตรงเทรนด์", "The first measures sales, the second the trend match"),
                  _o("ข้อแรกของแบรนด์ ข้อหลังของคู่แข่ง", "The first is the brand's, the second is the competitor's")],
        "slot": 2,
        "rewrite": ["category.top_pct", "category.market_rank", "unit.top_pct", "unit.m_rank"],
    },
    {
        "id": "C4", "report": "category", "topic": "ไม่มีสินค้าในกลุ่มราคานี้",
        "where": _o("หน้าหมวด · ช่องที่แบรนด์ไม่มีสินค้า", "Category page - a price group in which the brand has no product"),
        "quotes": {"q": ("category", "tier_none", {"brand": "Brand"})},
        "stem": _o("ในหน้าหมวดมีข้อความ “{q}” หมายถึงอะไร?", "A category page says \"{q}\". What does it mean?"),
        "correct": _o("แบรนด์ยังไม่มีสินค้าในหมวดนี้ที่อยู่ในกลุ่มราคาต่อปริมาณนั้น",
                      "The brand has no product in this category within that unit-price group"),
        "wrong": [_o("สินค้ากลุ่มนี้ของแบรนด์หมดสต็อก", "The brand's products in this group are out of stock"),
                  _o("ไม่มีสินค้าของตลาดในกลุ่มราคานี้", "There are no market products in this price group"),
                  _o("สินค้าของแบรนด์อยู่ในกลุ่มราคานี้แต่ไม่ตรงเทรนด์", "The brand has products here but they do not match the trend")],
        "slot": 1,
        "rewrite": ["category.tier_none", "category.no_brand_category", "unit.no_brand_category"],
    },
    {
        "id": "C5", "report": "category", "topic": "ระดับ “Below average”",
        "where": _o("หน้าสรุป/หน้าหมวด · ป้ายระดับความพร้อม", "Summary or category page - the fit-level badge"),
        "quotes": {"q": ("brand", "lv_def_last", {"p": 20})},
        "stem": _o("สินค้าของแบรนด์ได้ระดับ “Below average” หมายถึงอะไร?",
                   "A brand product is rated 'Below average'. What does that mean?"),
        "correct": _o("สินค้าที่ดีที่สุดของแบรนด์ยังไม่ถึง 20% แรกของสินค้ากลุ่มเดียวกัน หรือแบรนด์ไม่มีสินค้าในหมวดนั้น",
                      "The brand's best product is outside the top 20% of its group, or the brand has no product in that category"),
        "wrong": [_o("สินค้าของแบรนด์คุณภาพต่ำ", "The brand's product is poor quality"),
                  _o("ยอดขายต่ำกว่าค่าเฉลี่ยของตลาด", "Sales are below the market average"),
                  _o("ราคาต่ำกว่าค่าเฉลี่ยของตลาด", "The price is below the market average")],
        "slot": 3,
        "rewrite": ["brand.below_average", "brand.lv_def_last", "brand.lv_def_mid", "brand.lv_def_first"],
    },
]
QUESTIONS = apply_tokens(QUESTIONS)   # 🆕 (2026-10-19) @S@ = ปีระยะสั้นจาก common/horizons.py


def option_list(question, lang):
    """ตัวเลือก a-d ของข้อหนึ่ง (คำตอบถูกวางที่ slot) -> [(ตัวอักษร, ข้อความ)]"""
    texts = [w[lang] for w in question["wrong"]]
    texts.insert(question["slot"], question["correct"][lang])
    return list(zip(LETTERS, texts))


def answer_letter(question):
    return LETTERS[question["slot"]]


def resolve_quotes(question, lang):
    """ข้อความจริงในรายงานที่ข้อนี้อ้างถึง -> {ชื่อ: ข้อความ}"""
    out = OrderedDict()
    for name, (table, key, fmt) in (question.get("quotes") or {}).items():
        out[name] = text_of(table, key, lang, **fmt)
    return out


def stem_text(question, lang):
    quotes = resolve_quotes(question, lang)
    return question["stem"][lang].format(**{k: v for k, v in quotes.items()}) if quotes else question["stem"][lang]


def select_questions(report="all"):
    return [q for q in QUESTIONS if report in ("all", q["report"])]


# ---------------------------------------------------------------------------
# เอกสาร: ใบคำถามผู้อ่าน / เฉลยผู้ดำเนินการ / ใบตอบ CSV
# ---------------------------------------------------------------------------
INTRO = {
    "th": [
        "# ใบทดสอบการอ่านรายงาน",
        "",
        "ขอบคุณที่ช่วยอ่านรายงานครับ/ค่ะ - เรากำลังทดสอบ **รายงาน** ไม่ใช่ทดสอบคุณ ไม่มีคำตอบที่ถูกหรือผิดสำหรับคุณ",
        "",
        "- เปิดรายงานฉบับจริงที่ผู้ดำเนินการให้ แล้วหาข้อความที่ระบุในแต่ละข้อ",
        "- เลือกข้อที่คุณคิดว่าถูกที่สุด **จากสิ่งที่อ่านเจอในรายงาน** ถ้าไม่แน่ใจให้เลือก “?” ได้ (ไม่ต้องเดา)",
        "- ถ้าตรงไหนอ่านแล้วงง ให้ขีดหรือจดไว้ในช่อง “จุดที่อ่านแล้วงง” ท้ายใบ",
        "- ใช้เวลาประมาณ 15 นาที ไม่ต้องถามผู้ดำเนินการระหว่างตอบ",
        "",
    ],
    "en": [
        "# Report reading test",
        "",
        "Thank you for reading the report. We are testing the **report**, not you - there is no right or wrong for you.",
        "",
        "- Open the actual report you were given and find the text named in each question.",
        "- Choose the answer you think is best **from what the report says**. If unsure choose '?' - do not guess.",
        "- Note anything confusing in the 'Where I got confused' box at the end.",
        "- It takes about 15 minutes. Please do not ask the facilitator during the test.",
        "",
    ],
}
UNSURE_LABEL = {"th": "? ไม่แน่ใจ", "en": "? Not sure"}
HEADINGS = {
    "th": {"where": "ดูที่", "answers": "ใบตอบ", "confused": "จุดที่อ่านแล้วงง", "reader": "ชื่อผู้อ่าน / บทบาท",
           "summary": "ถ้าต้องบอกเพื่อนร่วมงาน 1 ประโยคว่ารายงานนี้บอกอะไร คุณจะพูดว่า (ไม่นับคะแนน ใช้ดูว่าเข้าใจภาพรวมตรงหรือไม่)"},
    "en": {"where": "Find it at", "answers": "Answers", "confused": "Where I got confused", "reader": "Reader / role",
           "summary": "In one sentence, what would you tell a colleague this report says? (not scored - shows whether the big picture lands)"},
}


def render_sheet(lang="th", report="all"):
    """ใบคำถามผู้อ่าน - ไม่มีเฉลย"""
    lines = list(INTRO[lang])
    h = HEADINGS[lang]
    n = 0
    for rep in ("trend", "brand", "category"):
        qs = [q for q in select_questions(report) if q["report"] == rep]
        if not qs:
            continue
        lines += [f"## {REPORT_NAMES[rep][lang]}", ""]
        for q in qs:
            n += 1
            lines += [f"**{q['id']}. {stem_text(q, lang)}**", "", f"_{h['where']}: {q['where'][lang]}_", ""]
            for letter, text in option_list(q, lang):
                lines.append(f"- ({letter}) {text}")
            lines += [f"- ({UNSURE_LABEL[lang]})", ""]
    lines += ["---", "", f"**{h['reader']}:** ______________________________", "",
              f"**{h['summary']}:**", "", "______________________________________________", "",
              f"**{h['confused']}:**", "", "______________________________________________", "",
              "______________________________________________", ""]
    return "\n".join(lines)


def render_key(lang="th", report="all"):
    """เฉลย + ข้อความที่ต้องแก้หากข้อนั้นไม่ผ่าน - สำหรับผู้ดำเนินการเท่านั้น"""
    lines = ["# เฉลยและคู่มือผู้ดำเนินการ (ห้ามให้ผู้อ่านเห็น)", "",
             f"เกณฑ์ผ่าน: ตอบถูกรวม ≥ {PASS_OVERALL:.0%} และทุกข้อ ≥ {PASS_PER_QUESTION:.0%} · ผู้อ่านอย่างน้อย {MIN_READERS} คน",
             "", "## วิธีดำเนินการ", "",
             "1. เลือกผู้อ่าน 3-5 คนที่ **ไม่ใช่นักวิเคราะห์** (เช่น ผู้จัดการแบรนด์ การตลาด ฝ่ายขาย ผู้บริหาร) คนละ ~15 นาที",
             "2. ให้ผู้อ่านเปิดรายงานฉบับจริง (⑯ / ⑰ / ⑱ ตามที่ทดสอบ) แล้วตอบใบคำถามเอง - ไม่อธิบายคำถาม ไม่ชี้ใบ้",
             "3. สังเกตว่าผู้อ่านหยุดนานหรือเปิดย้อนที่ข้อไหน แล้วจดไว้ (ข้อที่ถูกแต่ใช้เวลานานก็เป็นสัญญาณว่าภาษายังยาก)",
             "4. กรอกคำตอบลงใบ CSV (1 แถว/คน) แล้วรัน `reader_test.py score` เพื่อดูผลและรายการข้อความที่ต้องเขียนใหม่",
             "5. แก้ข้อความที่ไม่ผ่านตามคีย์ที่ระบุ แล้วสร้างรายงานใหม่ + รัน `lint_report_language.py` ก่อนทดสอบรอบถัดไปกับผู้อ่านคนใหม่",
             "", "## เฉลย", ""]
    for q in select_questions(report):
        lines += [f"### {q['id']} · {q['topic']}  ({REPORT_NAMES[q['report']][lang]})", "",
                  f"**คำถาม:** {stem_text(q, lang)}", ""]
        for letter, text in option_list(q, lang):
            mark = "✅" if letter == answer_letter(q) else "  "
            lines.append(f"- {mark} ({letter}) {text}")
        for name, text in resolve_quotes(q, lang).items():
            lines += ["", f"**ข้อความจริงในรายงาน ({name}):** {text[:300]}"]
        lines += ["", "**ถ้าผู้อ่านตอบผิดมาก ให้เขียนข้อความเหล่านี้ใหม่:**", ""]
        for ref in rewrite_refs(q, lang):
            lines.append(f"- `{ref}` - ปัจจุบัน: {ref_text(ref, lang)[:220]}")
        lines.append("")
    return "\n".join(lines)


def answers_template(report="all"):
    """ใบตอบ CSV: 1 แถว/ผู้อ่าน คอลัมน์ reader_id, role, <id คำถาม...>, notes - ใส่ตัวอักษร a-d หรือ ? """
    ids = [q["id"] for q in select_questions(report)]
    return ",".join(["reader_id", "role"] + ids + ["notes"]) + "\n"


# ---------------------------------------------------------------------------
# ตรวจคำตอบ
# ---------------------------------------------------------------------------
def read_answers(path):
    """CSV (แถวละคน) -> [{"reader_id","role","answers":{qid: letter},"notes"}]; ตัวอักษรไม่ใช่ a-d/? ถือว่าไม่ได้ตอบ"""
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not any((v or "").strip() for v in row.values()):
                continue
            answers = {}
            for k, v in row.items():
                if k in ("reader_id", "role", "notes") or k is None:
                    continue
                letter = (v or "").strip().lower()
                if letter in tuple(LETTERS) + (UNSURE,):
                    answers[k.strip()] = letter
            rows.append({"reader_id": (row.get("reader_id") or "").strip(), "role": (row.get("role") or "").strip(),
                         "answers": answers, "notes": (row.get("notes") or "").strip()})
    return rows


def score(rows, report="all", lang="th"):
    """คำตอบผู้อ่าน -> สรุปผลต่อข้อ/ต่อรายงาน/รวม + ข้อความที่ต้องแก้"""
    questions = select_questions(report)
    per_q = []
    for q in questions:
        answered = [r["answers"][q["id"]] for r in rows if q["id"] in r["answers"]]
        right = sum(1 for a in answered if a == answer_letter(q))
        unsure = sum(1 for a in answered if a == UNSURE)
        wrong = Counter(a for a in answered if a not in (answer_letter(q), UNSURE))
        pct = right / len(answered) if answered else None
        top_wrong = None
        if wrong:
            letter, count = wrong.most_common(1)[0]
            top_wrong = {"letter": letter, "count": count, "text": dict(option_list(q, lang))[letter]}
        per_q.append({"id": q["id"], "report": q["report"], "topic": q["topic"], "n": len(answered), "right": right,
                      "unsure": unsure, "pct": pct, "top_wrong": top_wrong, "rewrite": rewrite_refs(q, lang),
                      "pass": pct is not None and pct >= PASS_PER_QUESTION})
    by_report = {}
    for rep in ("trend", "brand", "category"):
        items = [p for p in per_q if p["report"] == rep and p["n"]]
        if items:
            n = sum(p["n"] for p in items)
            by_report[rep] = sum(p["right"] for p in items) / n
    answered_total = sum(p["n"] for p in per_q)
    overall = sum(p["right"] for p in per_q) / answered_total if answered_total else None
    failing = [p for p in per_q if p["pct"] is not None and not p["pass"]]
    verdict = {
        "readers": len(rows), "overall": overall, "by_report": by_report,
        "enough_readers": len(rows) >= MIN_READERS,
        "overall_pass": overall is not None and overall >= PASS_OVERALL,
        "questions_pass": not failing and all(p["n"] for p in per_q),
    }
    verdict["pass"] = verdict["enough_readers"] and verdict["overall_pass"] and verdict["questions_pass"]
    return {"questions": per_q, "verdict": verdict, "failing": failing,
            "rewrite_keys": list(OrderedDict.fromkeys(k for p in failing for k in p["rewrite"]))}


def render_result(result, rows, lang="th"):
    v = result["verdict"]
    fmt = lambda x: "-" if x is None else f"{x:.0%}"   # noqa: E731
    lines = ["# ผลทดสอบผู้อ่าน", "",
             f"ผู้อ่าน {v['readers']} คน" + ("" if v["enough_readers"] else f" - **น้อยกว่า {MIN_READERS} คน ผลยังเชื่อถือไม่ได้**"),
             f"ตอบถูกรวม **{fmt(v['overall'])}** (เกณฑ์ ≥ {PASS_OVERALL:.0%}) · "
             f"ผล: **{'ผ่าน' if v['pass'] else 'ยังไม่ผ่าน'}**", ""]
    if v["by_report"]:
        lines += ["| รายงาน | ตอบถูก |", "|---|---:|"]
        for rep, pct in v["by_report"].items():
            lines.append(f"| {REPORT_NAMES[rep][lang]} | {fmt(pct)} |")
        lines.append("")
    lines += [f"| ข้อ | หัวข้อ | ตอบถูก | ไม่แน่ใจ | ตัวลวงที่คนเลือกมากสุด | ผล |", "|---|---|---:|---:|---|---|"]
    for p in result["questions"]:
        wrong = f"({p['top_wrong']['letter']}) {p['top_wrong']['text']} ×{p['top_wrong']['count']}" if p["top_wrong"] else "-"
        status = "ไม่มีคำตอบ" if p["pct"] is None else ("ผ่าน" if p["pass"] else "**ต้องเขียนใหม่**")
        lines.append(f"| {p['id']} | {p['topic']} | {p['right']}/{p['n']} ({fmt(p['pct'])}) | {p['unsure']} | {wrong} | {status} |")
    if result["rewrite_keys"]:
        lines += ["", "## ข้อความที่ควรเขียนใหม่ (คีย์ในตารางข้อความ)", ""]
        for key in result["rewrite_keys"]:
            lines.append(f"- `{key}`")
    notes = [(r["reader_id"] or "?", r["notes"]) for r in rows if r["notes"]]
    if notes:
        lines += ["", "## จุดที่ผู้อ่านบอกว่างง", ""]
        lines += [f"- **{rid}**: {text}" for rid, text in notes]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="ชุดทดสอบผู้อ่านจริงของรายงาน ⑯/⑰/⑱")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_sheet = sub.add_parser("sheet", help="สร้างใบคำถามผู้อ่าน + เฉลย + ใบตอบ CSV")
    p_sheet.add_argument("--lang", choices=["th", "en"], default="th")
    p_sheet.add_argument("--report", choices=["all", "trend", "brand", "category"], default="all")
    p_sheet.add_argument("--out", default=str(DEFAULT_OUT))
    p_score = sub.add_parser("score", help="ตรวจคำตอบจากใบตอบ CSV")
    p_score.add_argument("answers")
    p_score.add_argument("--lang", choices=["th", "en"], default="th")
    p_score.add_argument("--report", choices=["all", "trend", "brand", "category"], default="all")
    p_score.add_argument("--md", default=None)
    p_score.add_argument("--json", default=None)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    if args.cmd == "sheet":
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        tag = f"{args.lang}_{args.report}"
        files = {f"reader_test_{tag}_sheet.md": render_sheet(args.lang, args.report),
                 f"reader_test_{tag}_key.md": render_key(args.lang, args.report),
                 f"reader_test_{tag}_answers_template.csv": answers_template(args.report)}
        for name, text in files.items():
            (out / name).write_text(text, encoding="utf-8-sig" if name.endswith(".csv") else "utf-8")
            print("เขียน", out / name)
        return 0

    rows = read_answers(args.answers)
    result = score(rows, args.report, args.lang)
    text = render_result(result, rows, args.lang)
    print(text)
    if args.md:
        Path(args.md).write_text(text, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["verdict"]["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
