# -*- coding: utf-8 -*-
"""
⑱ รายงานหมวด × ระดับราคา PDF — ข้อความตายตัว 2 ภาษา (ต่อยอดจาก brand_i18n.brand_strings: ปก/footer/ราคา/"ไม่มีข้อมูล"/ชื่อหัวตาราง
ที่ใช้ร่วมกับ ⑰ ถูกส่งต่อมาให้ แล้วข้อความเฉพาะรายงานนี้ทับ/เพิ่มที่นี่)

หลักเดียวกับ ⑰: ชื่อเทรนด์ ชื่อแบรนด์/สินค้า และศัพท์เทคนิคคงเป็นภาษาอังกฤษ ฉบับไทยใช้ชื่อสินค้าเต็ม (มีภาษาไทย)
"""
from brand_i18n import brand_strings

CATEGORY_STRINGS = {
    "en": {
        "report_kind": "Brand × Category × Price Group Report",
        "cat_cover_title": "{brand} × {title}",
        "cat_overview_header": "Category & Price Group Overview | Top {n} Trends",
        "cat_summary_header": "Executive Summary",
        "cat_how": "How it works",
        "cat_how_body": "Each trend belongs to one main category, chosen by an AI from what the trend "
                        "means, and gets its own page. Inside that category, products are compared within "
                        "the category's market price ranges (low / mid / high - each a third of the "
                        "category's prices in the store). {brand}'s best product in each range gets a fit "
                        "level.",
        "cat_compared": "Trends compared",
        "cat_in_portfolio": "{brand}'s products by category",
        "msg_strongest": "Strongest position - {trend}: in {category} at {price}, your {product} ranks #{rank} "
                         "({level}).",
        "msg_no_brand": "No {brand} product in the category of: {trends}.",
        "msg_all_have": "{brand} has products in the category of every trend compared.",
        "msg_scope": "{k} of {n} trends compared by category and price tier.",
        "msg_missing": "Not compared yet: {trends}.",
        "msg_none": "No trend could be compared for this brand in this run.",
        "col_category": "Category", "col_in_cat": "Your products",
        "tier_range": "THB {a}-{b}",
        "no_tiers_row": "This trend has not been compared with this brand yet",
        "cat_main": "Category",
        "cat_page": "category {i} of {k}",
        "cat_your_products": "Your products in category",
        "cat_your_best": "Your best level here",
        "tier_count": "{n} products in this group · {b} from {brand}",
        "tier_top": "Top {n} best matches for the trend",
        "tier_you_best": "Your best product in this group",
        "tier_none": "No {brand} product in this tier",
        "top_pct": "top {p}% of the group",
        "market_rank": "whole store: #{rank}",
        "no_brand_category": "{brand} has no product in {category} - the best matches in each price range are shown.",
        "cat_note": "Price ranges = this category's store prices split into three equal-sized groups (the same method "
                    "as the trend report). Rank = position among the products of this category and price range, "
                    "ordered by how well the product description matches the trend (1 = best match). 'Match' = the "
                    "description is close to the trend; not yet verified by people.",
        "m_cat_title": "Trend category",
        "m_cat": "For each trend, every Konvy product ({n}) is ranked by how well its description matches the "
                 "trend. The best-matching 1% are grouped by category (Euromonitor Level 2) as evidence; an AI "
                 "then chooses the one main category the trend belongs to from what it means, and the trend gets "
                 "its own page. Complementary categories are not counted.",
        "m_tier_title": "Price ranges",
        "m_tier": "Each category's prices across the whole store are sorted and split into three equal-sized groups - "
                  "low, mid and high. The bands are the same for every trend and every brand (the same method as the trend "
                  "report's product pages), so {brand} is always compared with products sold at similar prices.",
        "m_rank_title": "Reading the ranks",
        "m_rank": "\"#8\" = {brand}'s best product in that price range is the 8th best match for the trend among the "
                  "products of the same category and price range (each range's header shows how many). Fit level: "
                  "Excellent = top {p1}%, Good = top {p1}-{p2}%, Average = top {p2}-{p3}%, Below average = beyond "
                  "the top {p3}% (#1 of a range is always Excellent) - the same levels as the Brand × Trend Fit "
                  "report. The rank among all {n} products is shown below it.",
        "cat_data": "Brand comparison: {brand}'s {skus} products compared with the top {t} trends. Data collected "
                    "{date}.",
        "m_limits_title": "Limitations",
        "m_limits": "A match score shows how closely product text matches the trend description - not sales, quality "
                    "or consumer preference, and it has not yet been validated against human judgement. Gift sets and "
                    "bundles are included in their category and can raise the top tier. Products without a price are "
                    "not compared. Level 2 categories are broad (for example Skin Care mixes serums, masks and "
                    "cleansers).",
    },
    "th": {
        "report_kind": "รายงานเทียบสินค้าแบรนด์ตามหมวดและกลุ่มราคา",
        "cat_cover_title": "{brand} × {title}",
        "cat_overview_header": "ภาพรวมหมวดและกลุ่มราคา | {n} เทรนด์อันดับต้น",
        "cat_summary_header": "สรุปผู้บริหาร",
        "cat_how": "วิธีเทียบ",
        "cat_how_body": "แต่ละเทรนด์อยู่ในหมวดหลักหมวดเดียวที่ AI เลือกจากความหมายของเทรนด์ และได้หน้าของตัวเอง "
                        "ในหมวดนั้น สินค้าถูกเทียบภายในช่วงราคาตลาดของหมวด (ต่ำ / กลาง / สูง แต่ละช่วงคือ 1 ใน 3 "
                        "ของราคาสินค้าในหมวดทั้งร้าน) แล้วสินค้าที่ดีที่สุดของ {brand} ในแต่ละช่วงได้ระดับความพร้อม",
        "cat_compared": "เทรนด์ที่เทียบได้",
        "cat_in_portfolio": "สินค้าของ {brand} แยกตามหมวด",
        "msg_strongest": "จุดแข็งที่สุด - {trend}: ในหมวด {category} {price} {product} อยู่อันดับ {rank} "
                         "({level})",
        "msg_no_brand": "ยังไม่มีสินค้า {brand} ในหมวดของเทรนด์: {trends}",
        "msg_all_have": "{brand} มีสินค้าในหมวดของทุกเทรนด์ที่เทียบ",
        "msg_scope": "เทียบตามหมวดและระดับราคาได้ {k} จาก {n} เทรนด์",
        "msg_missing": "ยังไม่ได้เทียบ: {trends}",
        "msg_none": "รอบนี้เทียบเทรนด์ของแบรนด์นี้ไม่ได้เลย",
        "col_category": "หมวด", "col_in_cat": "สินค้าของคุณ",
        "tier_range": "{a}-{b} บาท",
        "no_tiers_row": "ยังไม่ได้เทียบเทรนด์นี้กับแบรนด์นี้",
        "cat_main": "หมวด",
        "cat_page": "หมวด {i} จาก {k}",
        "cat_your_products": "สินค้าของคุณในหมวดนี้",
        "cat_your_best": "ระดับที่ดีที่สุดของคุณ",
        "tier_count": "{n} ชิ้นในกลุ่มนี้ · ของ {brand} {b} ชิ้น",
        "tier_top": "{n} อันดับแรกที่ตรงเทรนด์",
        "tier_you_best": "สินค้าที่ดีที่สุดของคุณในกลุ่มนี้",
        "tier_none": "ไม่มีสินค้า {brand} ในระดับราคานี้",
        "top_pct": "ติด {p}% แรกของกลุ่ม",
        "market_rank": "ทั้งร้าน: อันดับ {rank}",
        "no_brand_category": "{brand} ยังไม่มีสินค้าในหมวด {category} - แสดงสินค้าที่ตรงเทรนด์ที่สุดในแต่ละช่วงราคา",
        "cat_note": "ช่วงราคา = แบ่งราคาสินค้าทั้งหมวดในร้านเป็น 3 กลุ่มเท่าๆ กัน (วิธีเดียวกับรายงานเทรนด์) · อันดับ "
                    "= ตำแหน่งของสินค้าในหมวดและช่วงราคานี้ เรียงตามความตรงเทรนด์ (1 = ตรงที่สุด) · ตรงเทรนด์ = "
                    "คำอธิบายสินค้าใกล้กับเทรนด์ ยังไม่ได้ตรวจยืนยันโดยคน",
        "m_cat_title": "หมวดของเทรนด์",
        "m_cat": "ในแต่ละเทรนด์ สินค้าทุกชิ้นบน Konvy ({n} ชิ้น) ถูกจัดอันดับตามความตรงกับเทรนด์ 1% "
                 "แรกถูกจัดกลุ่มตามหมวด (Euromonitor ระดับ 2) เป็นหลักฐานประกอบ แล้ว AI "
                 "เลือกหมวดหลักหมวดเดียวที่เทรนด์อยู่จากความหมายของเทรนด์ และเทรนด์ได้หน้าของตัวเอง "
                 "ไม่นับหมวดควบคู่",
        "m_tier_title": "ช่วงราคา",
        "m_tier": "ราคาสินค้าทั้งหมวดในร้านถูกเรียงแล้วแบ่งเป็น 3 กลุ่มเท่ากัน - ต่ำ กลาง สูง ทุกเทรนด์และทุกแบรนด์ใช้ช่วงเดียวกัน (วิธีเดียวกับหน้าสินค้าของรายงานเทรนด์) "
                  "{brand} จึงถูกเทียบกับสินค้าที่ขายในราคาใกล้กันเสมอ",
        "m_rank_title": "วิธีอ่านอันดับ",
        "m_rank": "\"#8\" = สินค้าที่ดีที่สุดของ {brand} ในช่วงราคานั้นตรงเทรนด์เป็นอันดับที่ 8 "
                  "ในสินค้าหมวดและช่วงราคาเดียวกัน (จำนวนสินค้าของแต่ละช่วงอยู่ที่หัวคอลัมน์) ระดับความพร้อม: "
                  "Excellent = {p1}% แรก, Good = {p1}-{p2}% แรก, Average = {p2}-{p3}% แรก, Below average = ไม่ถึง "
                  "{p3}% แรก (อันดับ 1 ของกลุ่มได้ Excellent เสมอ) ระดับเดียวกับรายงานความพร้อมของแบรนด์ต่อเทรนด์ "
                  "ด้านล่างคืออันดับจากสินค้าทั้งร้าน {n} ชิ้น",
        "cat_data": "ผลการเทียบแบรนด์: สินค้า {brand} {skus} ชิ้น เทียบกับ {t} เทรนด์อันดับต้น เก็บข้อมูลวันที่ "
                    "{date}",
        "m_limits_title": "ข้อจำกัด",
        "m_limits": "คะแนนความตรงเทรนด์วัดว่าข้อความของสินค้าใกล้กับคำอธิบายเทรนด์แค่ไหน ไม่ใช่ยอดขาย คุณภาพ "
                    "หรือความชอบของผู้บริโภค และยังไม่เคยตรวจเทียบกับการตัดสินของคน "
                    "ชุดของขวัญ/เซ็ตรวมอยู่ในหมวดและอาจดันระดับราคาสูง สินค้าที่ไม่มีราคาไม่ถูกนำมาเทียบ หมวดระดับ 2 "
                    "กว้าง (เช่น Skin Care รวมเซรั่ม มาสก์ และคลีนเซอร์)",
    },
}


# 🆕 (2026-10-14) ⑱ ถูกรวมเข้า ⑰ (เจ้าของงานสั่ง) - หน้าสินค้าต่อเทรนด์ของ ⑰ ใช้หน้าตาเดียวกับหน้าเทรนด์ของ ⑱ ข้อความของหน้านั้นมาจากชุดนี้
# โดยเติมคำนำหน้า cp_ (เช่น report_kind ของ ⑱ จะไม่ทับของ ⑰)
PAGE_KEYS = ("cat_main", "cat_page", "cat_your_products", "cat_your_best", "tier_count", "tier_you_best", "tier_none",
             "top_pct", "market_rank", "no_brand_category", "cat_note", "tier_range")


PAGE_EXTRA = {
    "en": {
        "tier_typical": "Price range {r}",
        "range_note": "Price range = where 80% of the group's products sit (cheapest and priciest 10% left out). Groups are formed "
                      "within each product type, so the ranges of different groups can overlap. The small line under a price = "
                      "price per ml, g or piece.",
    },
    "th": {
        "tier_typical": "ช่วงราคา {r}",
        "range_note": "ช่วงราคา = ช่วงที่สินค้า 80% ของกลุ่มอยู่ (ตัดถูกสุดและแพงสุดฝั่งละ 10%) · กลุ่มแบ่งภายในชนิดสินค้าเดียวกัน "
                      "ช่วงของแต่ละกลุ่มจึงซ้อนกันได้ · บรรทัดเล็กใต้ราคา = ราคาต่อ มล./ก./ชิ้น",
    },
}


def trend_page_strings(lang):
    """ข้อความของหน้าสินค้าต่อเทรนด์ใน ⑰ -> {"cp_<คีย์>": ข้อความ}"""
    return {**{"cp_" + k: CATEGORY_STRINGS[lang][k] for k in PAGE_KEYS},
            **{"cp_" + k: v for k, v in PAGE_EXTRA[lang].items()}}


def category_strings(lang):
    """ข้อความตายตัวของ ⑱ = ข้อความของ ⑰ (ซึ่งรวมของรายงานเทรนด์แล้ว) + ข้อความเฉพาะ ⑱"""
    return {**brand_strings(lang), **CATEGORY_STRINGS[lang]}
