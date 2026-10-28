# -*- coding: utf-8 -*-
"""
⑯/⑰/⑱ — ข้อความเมื่อช่วงราคาของรอบนั้นแบ่งจาก "ราคาต่อปริมาณ" (฿ ต่อ ml/g/ชิ้น เทียบภายในชนิดสินค้า) แทนราคาขาย
(🆕 2026-10-12 เจ้าของงานเลือก - tool/phase3_supply_layer/unit_price_tiers.py, config/market_tiers.json)

ผล ⑫/⑬ เก็บ tier_basis ไว้ ("unit_price" / "price") - renderer เอาข้อความชุดนี้ทับข้อความเดิมเฉพาะเมื่อเป็น unit_price
ผลรอบเก่า (price) จึงออกมาเหมือนเดิมทุกตัวอักษร

คีย์ unit_ml / unit_g / unit_pcs / mini ใช้ใน filter ulabel/urange ของ render.py (อยู่ใน i18n.STRINGS ฐาน ไม่ต้องทับ)
"""
UNIT_STRINGS = {
    "en": {
        # ⑯ หน้าสินค้าของเทรนด์
        "tier_low": "Low unit price", "tier_mid": "Mid unit price", "tier_high": "High unit price", "tier_all": "All unit prices",
        "cat_by_price": "By price per unit: {parts}",
        "cat_note_tiers": "Categories are standard product categories (Euromonitor Level 2, Beauty and "
                          "Personal Care only), ordered by how many of the best matches they hold. Fewer "
                          "than 3 = left out; with fewer than four, the largest is split by product type. "
                          "Tiers = price per ml, g or piece against products of the same type, in thirds "
                          "(trial and sachet sizes do not set the lines). Each row = best match in that "
                          "tier. Bar = match strength vs the best match shown; # = place among all {n} "
                          "products. 'Match' = description close to the trend; not confirmed to deliver it.",
        "cat_note_main": "Main category ({category}) is chosen by AI from the trend's meaning, using the categories of the "
                         "best-matching products as evidence. Columns = product types with the most matches (at least 3). "
                         "Tiers = price per ml, g or piece against products of the same type, in thirds (trial and sachet "
                         "sizes do not set the lines). Each row = best match in that tier. # = place among all {n} "
                         "products. 'Match' = description close to the trend; not confirmed to deliver it.",
        "method_4_main": "Each trend's profile (benefits, job-to-be-done, point of difference) is turned into numbers that "
                         "capture its meaning (a text embedding) and compared with the descriptions of {n} Konvy products "
                         "- the closer the meaning, the better the match. An AI then chooses the one main category "
                         "(Euromonitor Level 2) the trend belongs to, from the trend's meaning and the categories of the "
                         "best matches; complementary categories are not counted. The product types of that category with "
                         "the most matches are shown by unit-price tier - low, mid and high thirds of the price per ml, g "
                         "or piece among products of the same type - with the best match in each tier.",
        "method_4_tiers": "Each trend's profile (benefits, job-to-be-done, point of difference) is turned into numbers that "
                          "capture its meaning (a text embedding) and compared with the descriptions of {n} Konvy products "
                          "- the closer the meaning, the better the match. The top 1% of matches show which categories the "
                          "trend touches; the four categories holding the most of them (Euromonitor Level 2, at least 3 "
                          "products each; the largest is split by product type when fewer than four qualify) are shown by "
                          "unit-price tier - low, mid and high thirds of the price per ml, g or piece within the same "
                          "product type - with the best match in each tier.",
        # ⑰ รายงานความพร้อมของแบรนด์
        "lv_def_first": "best product is in the top {p}% of its type & unit-price group",
        "overall_line_excellent": "{lvb} in {k} of {n} trends - most trends have a product in the top {p}% of products of the "
                                  "same type.",
        "overall_line": "{lvb} in {k} of {n} trends - most trends have a product in the top {p}% of products of the same "
                        "type.",
        "overall_line_below": "{lvb} in only {k} of {n} trends - most trends have no product in the top {p}% of products of the "
                              "same type.",
        "vs_note": "Each column = top 5 products in the group used for {brand}'s grade (# = rank in that "
                   "group). Blue = {brand}'s products. Bottom row = {brand}'s best product when it is "
                   "outside the top 5. No product in the trend's category: that category's top 5 across all"
                   " unit-price groups.",
        "grid_sub": "your best match in each unit-price group · highlighted = the group used for this trend's fit "
                    "level",
        "grid_top": "Top 5 in category (all unit prices)",
        "trend_note": "Category = the main product category an AI chose for the trend from what it means (complementary "
                      "categories are not counted). Unit-price groups = price per ml, g or piece compared with products "
                      "of the same type, split into three equal-sized groups (low / mid / high); each product keeps its "
                      "group in every trend. Each cell = {brand}'s best match in that category & group and its level "
                      "among the group's products. Top 5 = the best matches for the trend in the whole category, any "
                      "brand and price. 'Match' = the product description is close to the trend; not yet verified by "
                      "people.",
        "m_fit": "For each trend: (1) category - an AI chooses the one main product category (Euromonitor Level 2) "
                 "the trend belongs to from what it means to the shopper, using the categories of the Konvy "
                 "products that best match the trend ({n} compared) as evidence; complementary categories are not "
                 "counted. (2) unit-price group - each product's price per ml, g or piece is compared with "
                 "products of the same type (for example serum with serum) and split into three equal-sized groups "
                 "(low / mid / high); trial and sachet sizes do not set the lines but are placed by them. (3) "
                 "level - each {brand} product is ranked by how well it matches the trend within its own category "
                 "& unit-price group: Excellent = top {p1}%, Good = top {p1}-{p2}%, Average = top {p2}-{p3}%, "
                 "Below average = beyond the top {p3}% (#1 of a group always counts as top {p1}%). The trend's level is "
                 "the level of {brand}'s best product in that category; no product there = Below average. Overall "
                 "fit = the highest level reached by more than half of the trends (that level or better); exactly "
                 "half does not count, so 'most trends' always holds.",
        # ⑱ รายงานหมวด x ระดับราคา
        "cat_how_body": "Each trend belongs to one main category, chosen by an AI from what the trend "
                        "means, and gets its own page. Inside that category, products are compared within "
                        "unit-price groups (low / mid / high). Unit price = price per ml, g or piece, "
                        "compared with products of the same type, each group a third of them. {brand}'s "
                        "best product in each group gets a fit level.",
        "cat_note": "Unit-price groups = price per ml, g or piece compared within the same product type and split "
                    "into three equal-sized groups (the same method as the trend report). Rank = position among the "
                    "products of this category and group, ordered by how well the product description matches the "
                    "trend (1 = best match). 'Match' = the description is close to the trend; not yet verified by "
                    "people.",
        "m_tier_title": "Unit-price groups",
        "m_tier": "Every product's price per ml, g or piece (price ÷ total size, packs counted) is compared with "
                  "the products of the same type in the store (for example serum with serum) and split into three "
                  "equal-sized groups - low, mid and high. The lines are the same for every trend and every brand "
                  "(the same method as the trend report's product pages), so {brand} is always compared with "
                  "products that give similar value for volume. Trial and sachet sizes are placed by the lines but "
                  "do not set them.",
        "m_rank": "\"#8\" = {brand}'s best product in that group is the 8th best match for the trend among the "
                  "products of the same category and unit-price group (each group's header shows how many). Fit "
                  "level: Excellent = top {p1}%, Good = top {p1}-{p2}%, Average = top {p2}-{p3}%, Below average = "
                  "beyond the top {p3}% (#1 of a group always counts as top {p1}%) - the same levels as the Brand × Trend "
                  "Fit report. The rank among all {n} products is shown below it.",
        "m_limits": "A match score shows how closely product text matches the trend description - not sales, quality "
                    "or consumer preference, and it has not yet been validated against human judgement. Gift sets and "
                    "bundles are included in their category and their total size is used. Products without a usable "
                    "size are placed by shelf price within their type. Level 2 categories are broad (for example Skin "
                    "Care mixes serums, masks and cleansers) - groups are formed within product types.",
        "no_brand_category": "{brand} has no product in {category} - the best matches in each unit-price group are shown.",
        "top_pct": "top {p}% of the group",
    },
    "th": {
        "tier_low": "ราคาต่อปริมาณต่ำ", "tier_mid": "ราคาต่อปริมาณกลาง", "tier_high": "ราคาต่อปริมาณสูง", "tier_all": "ทุกช่วง",
        "cat_by_price": "แยกตามราคาต่อปริมาณ: {parts}",
        "cat_note_tiers": "หมวด = หมวดสินค้ามาตรฐาน (Euromonitor Level 2 เฉพาะความงามและของใช้ส่วนตัว) "
                          "เรียงตามจำนวนสินค้าที่ตรงเทรนด์ที่สุด (ไม่ถึง 3 ชิ้นไม่แสดง ถ้าเหลือไม่ถึง 4 หมวด "
                          "หมวดใหญ่สุดแตกตามชนิดสินค้า) ช่วง = ราคาต่อ มล., ก. หรือชิ้น เทียบกับสินค้าชนิดเดียวกัน แบ่ง "
                          "ต่ำ/กลาง/สูง อย่างละ 1 ใน 3 (ขนาดทดลอง/ซองไม่กำหนดเส้น) แต่ละแถว = "
                          "ชิ้นที่ตรงเทรนด์ที่สุดในช่วงนั้น อันดับ = ลำดับจากสินค้าทั้งร้าน {n} ชิ้น ตรงเทรนด์ = "
                          "คำอธิบายสินค้าใกล้กับเทรนด์ ยังไม่ได้ยืนยันว่าตอบเทรนด์จริง",
        "cat_note_main": "หมวดหลัก ({category}) ให้ AI เลือกจากความหมายของเทรนด์ · ตรงเทรนด์ = คำอธิบายสินค้าใกล้กับเทรนด์ "
                         "ยังไม่ได้ยืนยันว่าตอบเทรนด์จริง · ช่วงราคา = ราคาต่อ มล., ก. หรือชิ้น เทียบกับสินค้าชนิดเดียวกัน "
                         "แบ่ง 3 กลุ่มเท่าๆ กัน (ขนาดทดลอง/ซองไม่กำหนดเส้นแบ่ง) · อันดับนับจากสินค้าทั้งร้าน {n} ชิ้น",
        "method_4_main": "แปลงโปรไฟล์ของแต่ละเทรนด์ (ประโยชน์ งานที่ผู้บริโภคต้องการให้สำเร็จ จุดต่าง) "
                         "เป็นตัวเลขที่แทนความหมาย (text embedding) แล้วเทียบกับคำอธิบายของสินค้า Konvy {n} ชิ้น "
                         "ยิ่งความหมายใกล้กัน ยิ่งตรงกับเทรนด์ จากนั้นให้ AI เลือกหมวดหลักหมวดเดียว (Euromonitor Level 2) "
                         "ที่เทรนด์นี้อยู่ จากความหมายของเทรนด์และหมวดของสินค้าที่ตรงที่สุด ไม่นับหมวดควบคู่ "
                         "แล้วแสดงชนิดสินค้าของหมวดนั้นที่มีสินค้าตรงเทรนด์มากที่สุด แยกเป็นช่วงราคาต่อปริมาณต่ำ/กลาง/สูง "
                         "(แบ่งราคาต่อ มล., ก. หรือชิ้นของสินค้าชนิดนั้นทั้งร้านเป็น 3 กลุ่มเท่ากัน) "
                         "พร้อมชิ้นที่ตรงเทรนด์ที่สุดในแต่ละช่วง",
        "method_4_tiers": "แปลงโปรไฟล์ของแต่ละเทรนด์ (ประโยชน์ งานที่ผู้บริโภคต้องการให้สำเร็จ จุดต่าง) "
                          "เป็นตัวเลขที่แทนความหมาย (text embedding) แล้วเทียบกับคำอธิบายของสินค้า Konvy {n} ชิ้น "
                          "ยิ่งความหมายใกล้กัน ยิ่งตรงกับเทรนด์ สินค้า 1% แรกที่ตรงที่สุดบอกว่าเทรนด์แตะหมวดไหนบ้าง แสดง 4 "
                          "หมวดที่มีสินค้ากลุ่มนี้มากที่สุด (หมวด Euromonitor Level 2 อย่างน้อยหมวดละ 3 ชิ้น ถ้าไม่ถึง 4 "
                          "หมวด หมวดใหญ่สุดแตกตามชนิดสินค้า) แยกเป็นช่วงราคาต่อปริมาณต่ำ/กลาง/สูง (แบ่งราคาต่อ มล., ก. "
                          "หรือชิ้นภายในชนิดสินค้าเดียวกันเป็น 3 กลุ่มเท่ากัน) พร้อมชิ้นที่ตรงเทรนด์ที่สุดในแต่ละช่วง",
        "lv_def_first": "สินค้าที่ดีที่สุดอยู่ใน {p}% แรกของประเภทและกลุ่มราคาเดียวกัน",
        "overall_line_excellent": "{lvb} {k} จาก {n} เทรนด์ - ส่วนใหญ่มีสินค้าอยู่ใน {p}% แรกของสินค้าประเภทเดียวกัน",
        "overall_line": "{lvb} {k} จาก {n} เทรนด์ - ส่วนใหญ่มีสินค้าอยู่ใน {p}% แรกของสินค้าประเภทเดียวกัน",
        "overall_line_below": "{lvb} แค่ {k} จาก {n} เทรนด์ - ส่วนใหญ่ยังไม่มีสินค้าอยู่ใน {p}% แรกของสินค้าประเภทเดียวกัน",
        "vs_note": "แต่ละคอลัมน์ = 5 อันดับแรกของสินค้ากลุ่มเดียวกับที่ใช้ตัดเกรดของ {brand} · ช่องสีฟ้า = สินค้าของ "
                   "{brand} · แถวล่าง = สินค้าที่ดีที่สุดของ {brand} เมื่อไม่ติด 5 อันดับแรก · ไม่มีสินค้าในหมวดนี้ "
                   "= แสดง 5 อันดับแรกของหมวดทุกกลุ่มราคา",
        "grid_sub": "สินค้าของคุณที่ตรงเทรนด์ที่สุดในแต่ละกลุ่มราคาต่อปริมาณ · ช่องที่ไฮไลต์ = "
                    "กลุ่มที่ใช้ตัดเกรดของเทรนด์นี้",
        "grid_top": "Top 5 ในหมวด (ทุกช่วง)",
        "trend_note": "หมวด = หมวดหลักของเทรนด์ที่ AI เลือกจากความหมายของเทรนด์ · กลุ่มราคาต่อปริมาณ = ราคาต่อ "
                      "มล./ก./ชิ้น เทียบกับสินค้าชนิดเดียวกัน แบ่ง 3 กลุ่มเท่าๆ กัน · แต่ละช่อง = สินค้าของ {brand} "
                      "ที่ตรงเทรนด์ที่สุดในกลุ่มนั้น พร้อมเกรดเมื่อเทียบกับสินค้าในกลุ่ม · Top 5 = "
                      "สินค้าที่ตรงเทรนด์ที่สุดทั้งหมวด · ตรงเทรนด์ = คำอธิบายสินค้าใกล้กับเทรนด์ "
                      "ยังไม่ได้ตรวจยืนยันโดยคน",
        "m_fit": "ในแต่ละเทรนด์: (1) หมวด - AI เลือกหมวดหลักหมวดเดียว (Euromonitor Level 2) ที่เทรนด์อยู่ "
                 "จากความหมายของเทรนด์ต่อผู้ซื้อ โดยใช้หมวดของสินค้า Konvy ที่ตรงเทรนด์ที่สุด (เทียบ {n} ชิ้น) "
                 "เป็นหลักฐานประกอบ ไม่นับหมวดควบคู่ (2) ช่วงราคาต่อปริมาณ - ราคาต่อ มล., ก. "
                 "หรือชิ้นของสินค้าทุกชิ้นถูกเทียบกับสินค้าชนิดเดียวกัน (เช่น เซรั่มกับเซรั่ม) แล้วแบ่งเป็น 3 "
                 "กลุ่มเท่าๆ กัน (ต่ำ / กลาง / สูง) "
                 "ขนาดทดลอง/ซองไม่ได้เป็นตัวกำหนดเส้นแบ่งแต่ถูกจัดกลุ่มตามเส้นนั้น วิธีเดียวกับรายงานเทรนด์ (3) "
                 "ระดับ - สินค้า {brand} แต่ละชิ้นจัดอันดับตามความตรงเทรนด์ในหมวดและช่วงราคาต่อปริมาณของตัวเอง: "
                 "Excellent = {p1}% แรก, Good = {p1}-{p2}% แรก, Average = {p2}-{p3}% แรก, Below average = ไม่ถึง "
                 "{p3}% แรก (อันดับ 1 ของกลุ่มนับเป็น {p1}% แรกเสมอ) ระดับของเทรนด์ = ระดับของสินค้าที่ดีที่สุดของ "
                 "{brand} ในหมวดนั้น ไม่มีสินค้าในหมวดนั้น = Below average ภาพรวมของแบรนด์ = "
                 "ระดับสูงสุดที่เทรนด์เกินครึ่งทำได้ถึง (นับระดับนั้นหรือดีกว่า) ครึ่งพอดีไม่นับ คำว่า "
                 "\"เทรนด์ส่วนใหญ่\" จึงเป็นจริงเสมอ",
        "cat_how_body": "แต่ละเทรนด์อยู่ในหมวดหลักหมวดเดียวที่ AI เลือกจากความหมายของเทรนด์ และได้หน้าของตัวเอง "
                        "ในหมวดนั้น สินค้าถูกเทียบภายในช่วงราคาต่อปริมาณ (ต่ำ / กลาง / สูง - ราคาต่อ มล., ก. "
                        "หรือชิ้นเทียบกับสินค้าชนิดเดียวกัน แต่ละช่วงคือ 1 ใน 3) แล้วสินค้าที่ดีที่สุดของ {brand} "
                        "ในแต่ละช่วงได้ระดับความพร้อม",
        "cat_note": "ช่วงราคาต่อปริมาณ = ราคาต่อ มล./ก./ชิ้น เทียบกับสินค้าชนิดเดียวกัน แบ่ง 3 กลุ่มเท่าๆ กัน "
                    "(วิธีเดียวกับรายงานเทรนด์) · อันดับ = ตำแหน่งของสินค้าในหมวดและกลุ่มนี้ เรียงตามความตรงเทรนด์ (1 "
                    "= ตรงที่สุด) · ตรงเทรนด์ = คำอธิบายสินค้าใกล้กับเทรนด์ ยังไม่ได้ตรวจยืนยันโดยคน",
        "m_tier_title": "ช่วงราคาต่อปริมาณ",
        "m_tier": "ราคาต่อ มล., ก. หรือชิ้นของสินค้าทุกชิ้น (ราคา ÷ ขนาดรวม นับจำนวนแพ็กแล้ว) "
                  "ถูกเทียบกับสินค้าชนิดเดียวกันในร้าน (เช่น เซรั่มกับเซรั่ม) แล้วแบ่งเป็น 3 กลุ่มเท่ากัน - ต่ำ "
                  "กลาง สูง ทุกเทรนด์และทุกแบรนด์ใช้เส้นแบ่งเดียวกัน (วิธีเดียวกับหน้าสินค้าของรายงานเทรนด์) "
                  "{brand} จึงถูกเทียบกับสินค้าที่ให้ความคุ้มต่อปริมาณใกล้กันเสมอ "
                  "ขนาดทดลอง/ซองถูกจัดกลุ่มตามเส้นแต่ไม่ได้เป็นตัวกำหนดเส้น",
        "m_rank": "\"#8\" = สินค้าที่ดีที่สุดของ {brand} ในกลุ่มนั้นตรงเทรนด์เป็นอันดับที่ 8 "
                  "ในสินค้าหมวดและกลุ่มราคาต่อปริมาณเดียวกัน (จำนวนสินค้าของแต่ละกลุ่มอยู่ที่หัวคอลัมน์) "
                  "ระดับความพร้อม: Excellent = {p1}% แรก, Good = {p1}-{p2}% แรก, Average = {p2}-{p3}% แรก, Below "
                  "average = ไม่ถึง {p3}% แรก (อันดับ 1 ของกลุ่มนับเป็น {p1}% แรกเสมอ) "
                  "ระดับเดียวกับรายงานความพร้อมของแบรนด์ต่อเทรนด์ ด้านล่างคืออันดับจากสินค้าทั้งร้าน {n} ชิ้น",
        "m_limits": "คะแนนความตรงเทรนด์วัดว่าข้อความของสินค้าใกล้กับคำอธิบายเทรนด์แค่ไหน ไม่ใช่ยอดขาย คุณภาพ "
                    "หรือความชอบของผู้บริโภค และยังไม่เคยตรวจเทียบกับการตัดสินของคน "
                    "ชุดของขวัญ/เซ็ตรวมอยู่ในหมวดและใช้ขนาดรวมทั้งชุด "
                    "สินค้าที่ไม่มีขนาดที่ใช้ได้ถูกจัดช่วงตามราคาขายภายในชนิดเดียวกัน หมวดระดับ 2 กว้าง (เช่น Skin Care "
                    "รวมเซรั่ม มาสก์ และคลีนเซอร์) จึงแบ่งกลุ่มภายในชนิดสินค้า",
        "no_brand_category": "{brand} ยังไม่มีสินค้าในหมวด {category} - แสดงสินค้าที่ตรงเทรนด์ที่สุดในแต่ละช่วงราคาต่อปริมาณ",
        "top_pct": "ติด {p}% แรกของกลุ่ม",
    },
}


def with_unit_strings(strings, lang, tier_basis):
    """ข้อความชุดของรายงาน + ข้อความชุดช่วงราคาต่อปริมาณเมื่อ tier_basis == "unit_price" (คืนชุดเดิมตัวเดียวกันถ้าไม่ใช่)"""
    if tier_basis == "unit_price":
        return {**strings, **UNIT_STRINGS[lang]}
    return strings
