# -*- coding: utf-8 -*-
"""
⑰ รายงานแบรนด์ PDF — ข้อความตายตัว 2 ภาษา (ต่อยอดจาก i18n.STRINGS ของรายงานเทรนด์: footer/ราคา/"ไม่มีข้อมูล" ใช้ร่วมกัน)

หลักเดียวกับรายงานเทรนด์: ชื่อเทรนด์ คีย์เวิร์ด ชื่อแบรนด์/สินค้า และศัพท์เทคนิคคงเป็นภาษาอังกฤษ ปีเป็น ค.ศ.
ฉบับไทยใช้ชื่อสินค้าเต็ม (มีภาษาไทย) และเหตุผลจับคู่สินค้าที่แปลแล้ว (enrich.translate_items_th)
"""
import copy

from i18n import STRINGS
from common.horizons import apply_tokens   # i18n เพิ่ม tool/ เข้า sys.path ให้แล้ว (บรรทัดบน)

BRAND_STRINGS = {
    "en": {
        "report_kind": "Brand × Trend Fit Report",
        "cover_title": "{brand} × {title} Trends",
        "cover_sources": "Product data: {n} Konvy products | Search data: Worldwide Google Trends",
        "prepared_for": "Prepared for {brand} by {company}",
        "summary_header": "Executive Summary",
        "on_retailer": "{brand} on Konvy",
        "skus": "Products listed",
        "price_range": "Price range",
        "median_price": "median {v}",
        "main_subcategories": "Main categories",
        "fit_across": "Fit across the top {n} trends",
        "excellent": "Excellent", "good": "Good", "average": "Average", "below_average": "Below average",
        "not_checked": "Not checked",
        "lv_def_first": "best product is in the top {p}% of its type & price group and top {s}% in sales",
        "lv_def_mid": "top {p0}-{p}%",
        "lv_def_last": "beyond the top {p}%, or no product in the trend's category",
        "overall_title": "Overall fit",
        "or_better": "{lv} or better",
        "overall_line": "{lvb} in {k} of {n} trends - most trends have a product in the top {p}% of products of the same "
                        "type.",
        "overall_line_below": "{lvb} in only {k} of {n} trends - most trends have no product in the top {p}% of products of the "
                              "same type.",
        "overall_line_excellent": "{lvb} in {k} of {n} trends - most trends have a product in the top {p}% of products of the "
                                  "same type that also sells strongly.",
        "overall_next": "Already {lvb} in {k} of {n} - one more trend → {lv}.",
        "overall_rule": "Overall = the highest level reached by more than half of the trends. Each level = fit to the trend, adjusted for sales.",
        "key_messages": "Key messages",
        "msg_strongest": "Strongest fit - {trend}: {product} ranks #{rank} of {n} products in {group}.",
        "msg_opportunity": "Biggest opportunity - {trend}: searches expected {z} by year @S@, but your best match ranks "
                           "#{rank} of {n} products in {group}.",
        "msg_opportunity_none": "Biggest opportunity - {trend}: searches expected {z} by year @S@, and {brand} has no product in "
                                "its category ({cats}).",
        "msg_quick_win": "Closest to the top of its group - {trend}: your best product trails #1 of {group} by only {gap} "
                         "(match score, out of 1).",
        "msg_none": "No trend could be assessed for this brand in this run.",
        "defend": "Defend", "build": "Build", "maintain": "Maintain", "monitor": "Monitor",
        "defend_def": "Higher expected growth and you already compete - protect and promote.",
        "build_def": "Higher expected growth but no strong product yet - the main development opportunity.",
        "maintain_def": "Lower expected growth and you already compete - keep the current range.",
        "monitor_def": "Lower expected growth and a weak fit - watch before investing.",
        "col_trend": "Trend",
        "no_product": "No product",
        "not_checked_row": "This trend has not been compared with this brand yet",
        "momentum": "Expected (year @S@)",
        "fit_level": "Fit level",
        "action": "Action",
        "your_tag": "Your product",
        # 🆕 (2026-10-07) เทรนด์ -> หมวด -> ช่วงราคา -> สินค้า
        "graded_group": "Compared with products in",
        "vs_header": "Products by Trend",
        "vs_corner": "Rank",
        "vs_note": "Each column = top 5 products in the group used for {brand}'s grade (# = rank in that "
                   "group). Blue = {brand}'s products. Bottom row = {brand}'s best product when it is "
                   "outside the top 5. No product in the trend's category: that category's top 5 at all "
                   "prices.",
        "graded_product": "Your best product for this trend",
        "no_key_short": "No product in the trend's category",
        "grid_title": "{brand} in this trend's category",
        "grid_sub": "your best match in each category & price range · highlighted = the group used for this trend's "
                    "fit level",
        "grid_top": "Top 5 in category (all prices)",
        "key_category_tag": "Main category",
        "no_key": "No {brand} product in this trend's category ({cats}) - {brand} does not yet sell in the "
                  "category this trend lives in.",
        "why_match": "Why it matches",
        "trend_note": "Category = the main product category an AI chose for the trend from what it means (complementary "
                      "categories are not counted). Price ranges = each category's store prices split into three "
                      "equal-sized groups. Each cell = {brand}'s best match in that category & price range and its "
                      "level among the group's products. Top 5 = the best matches for the trend in the whole category, "
                      "any brand and price. 'Match' = the product description is close to the trend; not yet verified "
                      "by people.",
        "opp_header": "Product Development Opportunities",
        "opp_intro": "Trends with higher expected growth where {brand} has no strong product yet (action: Build), "
                     "highest expected growth first.",
        "consumer_need": "Consumer need",
        "product_direction": "Product direction",
        "target": "Target",
        "keywords": "Search keywords",
        "opp_none": "No trend needs the Build action - {brand} already has a Good or Excellent product in every "
                    "higher-growth trend. Focus on defending those positions.",
        "method_header": "Appendix | How to Read This Report",
        "m_fit_title": "Fit level",
        "m_fit": "For each trend: (1) category - an AI chooses the one main product category (Euromonitor Level 2) "
                 "the trend belongs to from what it means to the shopper, using the categories of the Konvy "
                 "products that best match the trend ({n} compared) as evidence; complementary categories are not "
                 "counted. (2) price ranges - each category's store prices split into three equal-sized groups "
                 "(low / mid / high), the same method as the trend report. (3) level - each {brand} product is "
                 "ranked by how well it matches the trend within its own category & price range: Excellent = top "
                 "{p1}%, Good = top {p1}-{p2}%, Average = top {p2}-{p3}%, Below average = beyond the top {p3}% (#1 "
                 "of a group always counts as top {p1}%). The trend's level is the level of {brand}'s best product in "
                 "that category; no product there = Below average. Overall fit = the highest level reached by more "
                 "than half of the trends (that level or better); exactly half does not count, so 'most trends' "
                 "always holds.",
        "m_matrix_title": "Action",
        "m_matrix": "Action combines expected search growth in year @S@ from the trend report (at or above the median of the "
                    "top trends = higher growth) with the fit level (Excellent and Good = strong fit): Defend = higher growth "
                    "and a strong fit; Build = higher growth but no strong product yet; Maintain = lower growth and a strong "
                    "fit; Monitor = lower growth and a weak fit.",
        "m_data_title": "Data",
        "m_data": "Brand comparison: {brand}'s {skus} products compared with the top {t} trends. Market leader = "
                  "the single best-matching product of any brand. Data collected {date}.",
        "m_limits_title": "Limitations",
        "m_limits": "A match score shows how closely product text matches the trend description - not sales, quality "
                    "or consumer preference, and it has not yet been validated against human judgement. Use the fit "
                    "levels to prioritise discussion, not as a final verdict.",
        "last_12m": "Last 12 months (actual)",
        "pct_row": "Position in group",
        "pct_val": "top {p}% (rank #{rank})",
        # 🆕 (2026-10-19) ยอดขาย Konvy เป็นส่วนหนึ่งของเกณฑ์เกรดสินค้า
        "sales_row": "Sales on Konvy",
        "sales_strong": "Strong sales", "sales_steady": "Steady sales", "sales_slow": "Slow sales",
        "sales_unknown": "No sales data",
        "sold_out": "Sold out",
        "sl_sold": "{n} sold", "sl_reviews": "{n} reviews", "sl_zero": "0 sold while in stock",
        "sl_top_sales": "top {p}% of the group by sales", "sl_top_reviews": "top {p}% by reviews",
        "sales_up_note": "Sales lifted the level from {a} to {b}.",
        "sales_down_note": "Sales lowered the level from {a} to {b}.",
        "sales_cap_note": "Excellent needs strong sales as well - this product is a top match for the trend but its sales are "
                          "not strong, so it is graded {b}.",
        "msg_sales": "Sales changed the level in {k} of {n} trends ({u} up, {d} down).",
        "m_sales": "(4) sales - after step (3), each product's level is adjusted by its sales on Konvy (units sold x price, "
                   "compared with the other Konvy products of the same category & group): the top {s1}% = strong sales, which "
                   "lifts an Average product to Good; Excellent needs both a top {p1}% match and strong sales, so a top {p1}% "
                   "match with steady sales or no sales data stays at Good; the bottom {s2}%, or no sales while in stock = slow "
                   "sales, which lowers the level by one step; otherwise steady sales or missing data change nothing. Sold-out products "
                   "use review counts instead, because Konvy hides the sold counter when stock runs out. The trend's level is "
                   "the best adjusted level among {brand}'s products in that category.",
        "m_limits_sales": "Sales come from Konvy only: lifetime units shown on product pages (older products have had longer "
                          "to sell) x today's price, so they are an estimate, not company sales.",
        # 🆕 (2026-10-21) หน้าที่ 3 ของเทรนด์: แผนที่ ความใกล้เทรนด์ x ยอดขาย (fit_sales_map.py)
        "fm_question": "Does each {brand} product match the trend, and does it sell?",
        "fm_lg_you": "{brand} product",
        "fm_lg_hl": "Highlighted below the chart",
        "fm_lg_shade": "Cell shading = final grade:",
        "fm_x_first": "top {p}%", "fm_x_mid": "{a}-{b}%", "fm_x_last": "beyond {p}%",
        "fm_y_strong": "Strong", "fm_y_strong_sub": "top {p}%",
        "fm_y_steady": "Steady", "fm_y_steady_sub": "middle",
        "fm_y_slow": "Slow", "fm_y_slow_sub": "bottom {p}%",
        "fm_axis_x": "Match with the trend →", "fm_axis_y": "Sales on|Konvy ↑",   # "|" = ขึ้นบรรทัดใหม่ (fit_sales_map.render_svg)
        "fm_k_a": "Best grade in this category", "fm_k_b": "Close to the trend, sales lag", "fm_k_c": "Sells well, far from the trend",
        "fm_fit_top": "Fit top {p}%", "fm_sales_top": "Sales top {p}%", "fm_review_one": "1 review", "fm_sold": "{n} sold",
        "fm_l2_count": "{n} products in this category · {b} from {brand}",
        "fm_note": "Each dot = one {brand} product in this category. Left to right: closeness to the trend (columns = position "
                   "among all {total} {category} products). Bottom to top: Konvy sales vs all {category} products (units sold x "
                   "price; sold-out items use reviews); products with no sales data are drawn in the steady row and graded like "
                   "steady sales. Shading = final grade after sales lift or lower it (strong sales lift an Average product to "
                   "Good; Excellent needs a top {p1}% match and strong sales; slow sales lower one step). Dots are nudged apart; "
                   "sales are lifetime Konvy sales, not company sales.",
        "m_map": "Each trend's third page plots every {brand} product in the trend's main category on two measures - how close "
                 "it is to the trend (left to right) and its Konvy sales (bottom to top) - each compared with all products of "
                 "that category, so you can see strong sellers that sit far from the trend and close matches whose sales lag.",
    },
    "th": {
        "report_kind": "รายงานความพร้อมของแบรนด์ต่อเทรนด์",
        "cover_title": "{brand} × เทรนด์ {title}",
        "cover_sources": "ข้อมูลสินค้า: Konvy {n} ชิ้น | ข้อมูลการค้นหา: Google Trends ทั่วโลก",
        "prepared_for": "จัดทำให้ {brand} โดย {company}",
        "summary_header": "สรุปผู้บริหาร",
        "on_retailer": "{brand} บน Konvy",
        "skus": "จำนวนสินค้า",
        "price_range": "ช่วงราคา",
        "median_price": "ราคากลาง {v}",
        "main_subcategories": "หมวดหลัก",
        "fit_across": "ความพร้อมใน {n} เทรนด์อันดับต้น",
        # 🆕 (2026-10-07) ชื่อระดับใช้คำอังกฤษเหมือนฉบับอังกฤษ (ผู้ใช้เลือก)
        "excellent": "Excellent", "good": "Good", "average": "Average", "below_average": "Below average",
        "not_checked": "ยังไม่ได้ตรวจ",
        "lv_def_first": "สินค้าที่ดีที่สุดอยู่ใน {p}% แรกของประเภทและกลุ่มราคาเดียวกัน และ {s}% แรกด้านยอดขาย",
        "lv_def_mid": "{p0}-{p}% แรก",
        "lv_def_last": "ไม่ถึง {p}% แรก หรือไม่มีสินค้าในหมวดของเทรนด์",
        "overall_title": "ภาพรวม",
        "or_better": "{lv} ขึ้นไป",
        "overall_line": "{lvb} {k} จาก {n} เทรนด์ - ส่วนใหญ่มีสินค้าอยู่ใน {p}% แรกของสินค้าประเภทเดียวกัน",
        "overall_line_below": "{lvb} แค่ {k} จาก {n} เทรนด์ - ส่วนใหญ่ยังไม่มีสินค้าอยู่ใน {p}% แรกของสินค้าประเภทเดียวกัน",
        "overall_line_excellent": "{lvb} {k} จาก {n} เทรนด์ - ส่วนใหญ่มีสินค้าอยู่ใน {p}% แรกของสินค้าประเภทเดียวกัน และขายดี",
        "overall_next": "ได้ {lvb} แล้ว {k} จาก {n} เทรนด์ - อีก 1 เทรนด์จะขึ้นเป็น {lv}",
        "overall_rule": "ภาพรวม = ระดับสูงสุดที่เทรนด์เกินครึ่งทำได้ถึง · แต่ละระดับ = ความใกล้เทรนด์ ปรับตามยอดขาย",
        "key_messages": "ประเด็นสำคัญ",
        "msg_strongest": "จุดแข็งที่สุด - {trend}: {product} เป็นอันดับ {rank} จากสินค้า {n} ชิ้นใน {group}",
        "msg_opportunity": "โอกาสใหญ่ที่สุด - {trend}: คาดว่ายอดค้นหาปีที่ @S@ {z} แต่สินค้าของคุณที่ตรงเทรนด์ที่สุดเป็นอันดับ "
                           "{rank} จากสินค้า {n} ชิ้นใน {group}",
        "msg_opportunity_none": "โอกาสใหญ่ที่สุด - {trend}: คาดว่ายอดค้นหาปีที่ @S@ {z} และ {brand} "
                                "ยังไม่มีสินค้าในหมวดของเทรนด์นี้ ({cats})",
        "msg_quick_win": "ใกล้ขึ้นอันดับ 1 ที่สุด - {trend}: สินค้าที่ดีที่สุดของคุณตามอันดับ 1 ของ {group} อยู่แค่ {gap} "
                         "(คะแนนความตรงเทรนด์เต็ม 1)",
        "msg_none": "รอบนี้ประเมินเทรนด์ของแบรนด์นี้ไม่ได้เลย",
        "defend": "ปกป้อง", "build": "สร้างใหม่", "maintain": "รักษาไว้", "monitor": "เฝ้าดู",
        "defend_def": "เทรนด์ที่คาดว่าการค้นหาเพิ่มมาก และคุณมีสินค้าแข่งได้แล้ว - ปกป้องและเร่งโปรโมต",
        "build_def": "เทรนด์ที่คาดว่าการค้นหาเพิ่มมาก แต่ยังไม่มีสินค้าที่แข็ง - โอกาสพัฒนาสินค้าหลัก",
        "maintain_def": "เทรนด์ที่คาดว่าเพิ่มน้อยกว่า และคุณมีสินค้าแข่งได้ - รักษาสินค้าที่มีอยู่",
        "monitor_def": "เทรนด์ที่คาดว่าเพิ่มน้อยกว่า และยังไม่พร้อม - เฝ้าดูก่อนลงทุน",
        "col_trend": "เทรนด์",
        "no_product": "ไม่มีสินค้า",
        "not_checked_row": "ยังไม่ได้เทียบเทรนด์นี้กับแบรนด์ของคุณ",
        "momentum": "คาด (ปีที่ @S@)",
        "fit_level": "ระดับความพร้อม",
        "action": "แนวทาง",
        "your_tag": "สินค้าของคุณ",
        "graded_group": "เทียบกับสินค้ากลุ่ม",
        "vs_header": "สินค้าตามเทรนด์",
        "vs_corner": "อันดับ",
        "vs_note": "แต่ละคอลัมน์ = 5 อันดับแรกของสินค้ากลุ่มเดียวกับที่ใช้ตัดเกรดของ {brand} · ช่องสีฟ้า = สินค้าของ "
                   "{brand} · แถวล่าง = สินค้าที่ดีที่สุดของ {brand} เมื่อไม่ติด 5 อันดับแรก · ไม่มีสินค้าในหมวดนี้ "
                   "= แสดง 5 อันดับแรกของหมวดทุกช่วงราคา",
        "graded_product": "สินค้าที่ดีที่สุดของคุณในเทรนด์นี้",
        "no_key_short": "ไม่มีสินค้าในหมวดของเทรนด์",
        "grid_title": "{brand} ในหมวดของเทรนด์นี้",
        "grid_sub": "สินค้าของคุณที่ตรงเทรนด์ที่สุดในแต่ละช่วงราคา · ช่องที่ไฮไลต์ = กลุ่มที่ใช้ตัดเกรดของเทรนด์นี้",
        "grid_top": "Top 5 ในหมวด (ทุกช่วงราคา)",
        "key_category_tag": "หมวดหลัก",
        "no_key": "ยังไม่มีสินค้า {brand} ในหมวดของเทรนด์นี้ ({cats}) - {brand} ยังไม่ได้ขายในหมวดที่เทรนด์นี้อยู่",
        "why_match": "ทำไมถึงเข้ากับเทรนด์",
        "trend_note": "หมวด = หมวดหลักของเทรนด์ที่ AI เลือกจากความหมายของเทรนด์ (ไม่นับหมวดควบคู่) · ช่วงราคา = "
                      "แบ่งราคาสินค้าทั้งหมวดในร้านเป็น 3 กลุ่มเท่าๆ กัน · แต่ละช่อง = สินค้าของ {brand} "
                      "ที่ตรงเทรนด์ที่สุดในหมวดและช่วงราคานั้น พร้อมเกรดเมื่อเทียบกับสินค้าในกลุ่ม · Top 5 = "
                      "สินค้าที่ตรงเทรนด์ที่สุดทั้งหมวด ทุกแบรนด์ทุกช่วงราคา · ตรงเทรนด์ = คำอธิบายสินค้าใกล้กับเทรนด์ "
                      "ยังไม่ได้ตรวจยืนยันโดยคน",
        "opp_header": "โอกาสพัฒนาสินค้า",
        "opp_intro": "เทรนด์ที่คาดว่าการค้นหาเพิ่มมาก แต่ {brand} ยังไม่มีสินค้าที่แข็ง (แนวทาง สร้างใหม่) "
                     "เรียงจากที่คาดว่าเพิ่มมากที่สุด",
        "consumer_need": "ความต้องการของผู้บริโภค",
        "product_direction": "แนวทางสินค้า",
        "target": "กลุ่มเป้าหมาย",
        "keywords": "คีย์เวิร์ดค้นหา",
        "opp_none": "ไม่มีเทรนด์ที่อยู่ในแนวทาง สร้างใหม่ - {brand} มีสินค้าระดับ Good "
                    "ขึ้นไปในทุกเทรนด์ที่คาดว่าเพิ่มมากแล้ว ควรเน้นรักษาตำแหน่งเหล่านั้น",
        "method_header": "ภาคผนวก | วิธีอ่านรายงานนี้",
        "m_fit_title": "ระดับความพร้อม",
        "m_fit": "ในแต่ละเทรนด์: (1) หมวด - AI เลือกหมวดหลักหมวดเดียว (Euromonitor Level 2) ที่เทรนด์อยู่ "
                 "จากความหมายของเทรนด์ต่อผู้ซื้อ โดยใช้หมวดของสินค้า Konvy ที่ตรงเทรนด์ที่สุด (เทียบ {n} ชิ้น) "
                 "เป็นหลักฐานประกอบ ไม่นับหมวดควบคู่ (2) ช่วงราคา - แบ่งราคาสินค้าทั้งหมวดในร้านเป็น 3 กลุ่มเท่าๆ "
                 "กัน (ต่ำ / กลาง / สูง) วิธีเดียวกับรายงานเทรนด์ (3) ระดับ - สินค้า {brand} "
                 "แต่ละชิ้นจัดอันดับตามความตรงเทรนด์ในหมวดและช่วงราคาของตัวเอง: Excellent = {p1}% แรก, Good = "
                 "{p1}-{p2}% แรก, Average = {p2}-{p3}% แรก, Below average = ไม่ถึง {p3}% แรก (อันดับ 1 ของกลุ่มนับเป็น "
                 "{p1}% แรกเสมอ) ระดับของเทรนด์ = ระดับของสินค้าที่ดีที่สุดของ {brand} ในหมวดนั้น "
                 "ไม่มีสินค้าในหมวดนั้น = Below average ภาพรวมของแบรนด์ = ระดับสูงสุดที่เทรนด์เกินครึ่งทำได้ถึง "
                 "(นับระดับนั้นหรือดีกว่า) ครึ่งพอดีไม่นับ คำว่า \"เทรนด์ส่วนใหญ่\" จึงเป็นจริงเสมอ",
        "m_matrix_title": "แนวทาง",
        "m_matrix": "แนวทางรวมการเติบโตของการค้นหาที่คาดในปีที่ @S@ จากรายงานเทรนด์ (ตั้งแต่ค่ากลางของเทรนด์อันดับต้นขึ้นไป = "
                    "คาดว่าเพิ่มมาก) กับระดับความพร้อม (Excellent และ Good = พร้อม): ปกป้อง = เพิ่มมากและพร้อม, สร้างใหม่ = "
                    "เพิ่มมากแต่ยังไม่มีสินค้าที่แข็ง, รักษาไว้ = เพิ่มน้อยกว่าแต่พร้อม, เฝ้าดู = เพิ่มน้อยกว่าและยังไม่พร้อม",
        "m_data_title": "ข้อมูล",
        "m_data": "ผลการเทียบแบรนด์: สินค้า {brand} {skus} ชิ้น เทียบกับ {t} เทรนด์อันดับต้น เจ้าตลาด = "
                  "สินค้าที่ตรงเทรนด์ที่สุดจากทุกแบรนด์ เก็บข้อมูลวันที่ {date}",
        "m_limits_title": "ข้อจำกัด",
        "m_limits": "คะแนนความตรงเทรนด์วัดว่าข้อความของสินค้าใกล้กับคำอธิบายเทรนด์แค่ไหน ไม่ใช่ยอดขาย คุณภาพ "
                    "หรือความชอบของผู้บริโภค และยังไม่เคยตรวจเทียบกับการตัดสินของคน "
                    "ใช้ระดับความพร้อมเพื่อจัดลำดับการพูดคุย ไม่ใช่คำตัดสินสุดท้าย",
        "last_12m": "12 เดือนที่ผ่านมา (ข้อมูลจริง)",
        "pct_row": "ตำแหน่งในกลุ่ม",
        "pct_val": "ติด {p}% แรก (อันดับ {rank})",
        # 🆕 (2026-10-19) ยอดขาย Konvy เป็นส่วนหนึ่งของเกณฑ์เกรดสินค้า
        "sales_row": "ยอดขายบน Konvy",
        "sales_strong": "ขายดี", "sales_steady": "ขายปานกลาง", "sales_slow": "ขายได้น้อย",
        "sales_unknown": "ไม่มีข้อมูลยอดขาย",
        "sold_out": "ของหมด",
        "sl_sold": "ขายแล้ว {n} ชิ้น", "sl_reviews": "{n} รีวิว", "sl_zero": "ขายได้ 0 ชิ้นทั้งที่มีของ",
        "sl_top_sales": "{p}% แรกของกลุ่มด้านยอดขาย", "sl_top_reviews": "{p}% แรกด้านรีวิว",
        "sales_up_note": "ยอดขายดึงระดับขึ้นจาก {a} เป็น {b}",
        "sales_down_note": "ยอดขายดึงระดับลงจาก {a} เป็น {b}",
        "sales_cap_note": "Excellent ต้องขายดีด้วย - สินค้านี้ตรงเทรนด์มากที่สุดกลุ่มแรก แต่ยอดขายยังไม่ถึงขั้นขายดี จึงได้ {b}",
        "msg_sales": "ยอดขายเปลี่ยนระดับของ {k} จาก {n} เทรนด์ (ขึ้น {u}, ลง {d})",
        "m_sales": "(4) ยอดขาย - หลังขั้น (3) ระดับของสินค้าแต่ละชิ้นถูกปรับตามยอดขายบน Konvy (จำนวนที่ขาย x ราคา เทียบกับสินค้า Konvy "
                   "อื่นในหมวดและกลุ่มเดียวกัน): {s1}% แรก = ขายดี ดึงระดับ Average ขึ้นเป็น Good · "
                   "Excellent ต้องตรงเทรนด์ {p1}% แรก และขายดี ทั้งสองอย่าง ตรงเทรนด์ {p1}% แรกแต่ขายปานกลางหรือไม่มีข้อมูลยอดขายได้สูงสุด Good · "
                   "{s2}% ล่างสุด หรือขายได้ 0 ชิ้นทั้งที่มีของ = ขายได้น้อย ลดระดับลง 1 ขั้น · นอกจากนั้นขายปานกลางหรือไม่มีข้อมูลไม่เปลี่ยนระดับ "
                   "สินค้าที่ของหมดใช้จำนวนรีวิวแทน เพราะ Konvy ซ่อนตัวนับยอดขายเมื่อสต็อกหมด "
                   "ระดับของเทรนด์ = ระดับที่ดีที่สุดหลังปรับของสินค้า {brand} ในหมวดนั้น",
        "m_limits_sales": "ยอดขายมาจาก Konvy ช่องทางเดียว เป็นจำนวนที่ขายสะสมตลอดอายุสินค้าตามหน้าสินค้า (สินค้าเก่าขายมานานกว่า) "
                          "คูณราคาปัจจุบัน จึงเป็นค่าประมาณ ไม่ใช่ยอดขายของบริษัท",
        # 🆕 (2026-10-21) หน้าที่ 3 ของเทรนด์: แผนที่ ความใกล้เทรนด์ x ยอดขาย (fit_sales_map.py)
        "fm_question": "สินค้า {brand} แต่ละชิ้นตรงเทรนด์ไหม และขายได้ไหม",
        "fm_lg_you": "สินค้าของ {brand}",
        "fm_lg_hl": "ไฮไลต์ไว้ใต้กราฟ",
        "fm_lg_shade": "สีพื้นช่อง = เกรดสุดท้าย:",
        "fm_x_first": "{p}% แรก", "fm_x_mid": "{a}-{b}% แรก", "fm_x_last": "ไม่ถึง {p}% แรก",
        "fm_y_strong": "ขายดี", "fm_y_strong_sub": "{p}% แรก",
        "fm_y_steady": "ปานกลาง", "fm_y_steady_sub": "ช่วงกลาง",
        "fm_y_slow": "ขายได้น้อย", "fm_y_slow_sub": "{p}% ล่างสุด",
        "fm_axis_x": "ความตรงกับเทรนด์ →", "fm_axis_y": "ยอดขาย|บน Konvy ↑",
        "fm_k_a": "เกรดดีที่สุดในหมวดนี้", "fm_k_b": "ตรงเทรนด์แต่ยอดขายตามหลัง", "fm_k_c": "ขายดีแต่ไม่ตรงเทรนด์",
        "fm_fit_top": "ตรงเทรนด์ {p}% แรก", "fm_sales_top": "ยอดขาย {p}% แรก", "fm_review_one": "1 รีวิว", "fm_sold": "ขาย {n} ชิ้น",
        "fm_l2_count": "{n} ชิ้นในหมวดนี้ · ของ {brand} {b} ชิ้น",
        "fm_note": "จุดละ 1 ชิ้นของ {brand} ในหมวดนี้ · ซ้ายไปขวา = ความตรงกับเทรนด์ (ช่อง = ตำแหน่งในสินค้า {category} ทั้ง {total} ชิ้น) · "
                   "ล่างขึ้นบน = ยอดขายบน Konvy เทียบสินค้า {category} ทั้งหมวด (จำนวนที่ขาย x ราคา ของหมดใช้จำนวนรีวิว) "
                   "สินค้าที่ไม่มีข้อมูลยอดขายวาดไว้ในแถวปานกลางและตัดเกรดเหมือนขายปานกลาง · สีพื้น = เกรดสุดท้ายหลังยอดขายปรับ "
                   "(ขายดีดึง Average ขึ้นเป็น Good · Excellent ต้องตรงเทรนด์ {p1}% แรกและขายดี · ขายได้น้อยลง 1 ขั้น) · "
                   "จุดถูกเขี่ยออกจากกันเล็กน้อย · ยอดขายเป็นยอดสะสมของ Konvy ไม่ใช่ยอดขายของบริษัท",
        "m_map": "หน้าที่ 3 ของแต่ละเทรนด์วางสินค้า {brand} ทุกชิ้นในหมวดหลักของเทรนด์บนสองแกน - ความตรงกับเทรนด์ (ซ้ายไปขวา) และยอดขายบน "
                 "Konvy (ล่างขึ้นบน) - โดยเทียบกับสินค้าทั้งหมวด เพื่อให้เห็นสินค้าที่ขายดีแต่ไม่ตรงเทรนด์ และสินค้าที่ตรงเทรนด์แต่ยอดขายยังตามหลัง",
    },
}
BRAND_STRINGS = apply_tokens(BRAND_STRINGS)   # 🆕 (2026-10-19) @S@ = ปีระยะสั้นจาก common/horizons.py

# 🆕 (2026-10-21) เกรดทั้งรายงานเทียบในหมวด L2 อย่างเดียว (เจ้าของงานสั่ง - ไม่แยกช่วงราคาต่อปริมาณ/ชนิดสินค้า) -> ข้อความที่เคยพูดถึง "กลุ่มราคา" เปลี่ยนเป็น
# "หมวด" ใช้เมื่อ brand context มี group_basis == "l2" (ทับชุดปกติ + ชุดช่วงราคาต่อปริมาณ ดู with_l2_strings) ผลรอบที่ยังไม่มีแผนที่ L2 ใช้ข้อความเดิม
L2_STRINGS = {
    "en": {
        "lv_def_first": "best product is in the top {p}% of the category and top {s}% in sales",
        "overall_line_excellent": "{lvb} in {k} of {n} trends - most trends have a product in the top {p}% of the products in "
                                  "the same category that also sells strongly.",
        "overall_line": "{lvb} in {k} of {n} trends - most trends have a product in the top {p}% of the products in the same "
                        "category.",
        "overall_line_below": "{lvb} in only {k} of {n} trends - most trends have no product in the top {p}% of the products in "
                              "the same category.",
        "vs_note": "Each column = top 5 products in the trend's category (# = rank in the category). Blue = {brand}'s products. "
                   "Bottom row = {brand}'s best product when it is outside the top 5. No {brand} product in the category: the "
                   "bottom row is left grey.",
        "pct_row": "Position in category",
        "sl_top_sales": "top {p}% of the category by sales",
        "trend_note": "Category = the main product category an AI chose for the trend from what it means (complementary "
                      "categories are not counted). Each product is ranked against all products of that category. Top 5 = the "
                      "best matches for the trend in the whole category, any brand. 'Match' = the product description is close "
                      "to the trend; not yet verified by people.",
        "m_fit": "For each trend: (1) category - an AI chooses the one main product category (Euromonitor Level 2) "
                 "the trend belongs to from what it means to the shopper, using the categories of the Konvy "
                 "products that best match the trend ({n} compared) as evidence; complementary categories are not "
                 "counted. (2) level - each {brand} product is ranked by how well it matches the trend among all products "
                 "of that category: Excellent = top {p1}%, Good = top {p1}-{p2}%, Average = top {p2}-{p3}%, Below average = "
                 "beyond the top {p3}% (#1 of the category always counts as top {p1}%). The trend's level is the level of "
                 "{brand}'s best product in that category; no product there = Below average. Overall fit = the highest "
                 "level reached by more than half of the trends (that level or better); exactly half does not count, so "
                 "'most trends' always holds.",
        "m_sales": "(3) sales - after step (2), each product's level is adjusted by its sales on Konvy (units sold x price, "
                   "compared with the other Konvy products of the same category): the top {s1}% = strong sales, which lifts an "
                   "Average product to Good; Excellent needs both a top {p1}% match and strong sales, so a top {p1}% match with "
                   "steady sales or no sales data stays at Good; the bottom {s2}%, or no sales while in stock = slow sales, "
                   "which lowers the level by one step; otherwise steady sales or missing data change nothing. Sold-out products use "
                   "review counts instead, because Konvy hides the sold counter when stock runs out. The trend's level is the "
                   "best adjusted level among {brand}'s products in that category.",
        "m_limits": "A match score shows how closely product text matches the trend description - not sales, quality "
                    "or consumer preference, and it has not yet been validated against human judgement. Gift sets and "
                    "bundles are included in their category. Level 2 categories are broad (for example Skin Care mixes "
                    "serums, masks and cleansers), so a product is compared with many different product types and "
                    "prices. Use the fit levels to prioritise discussion, not as a final verdict.",
        "cp_tier_count": "{n} products in this category · {b} from {brand}",
        "cp_tier_you_best": "Your best product in this category",
        "cp_top_pct": "top {p}% of the category",
        "cp_tier_none": "No {brand} product in this category",
        "cp_no_brand_category": "{brand} has no product in {category} - the best matches of the category are shown.",
        "cat_note": "Rank = position among all products of this category, ordered by how well the product description "
                    "matches the trend (1 = best match). 'Match' = the description is close to the trend; not yet verified "
                    "by people. Levels compare each product with the whole category; sales position = units sold x price "
                    "compared with the category's products.",
    },
    "th": {
        "lv_def_first": "สินค้าที่ดีที่สุดอยู่ใน {p}% แรกของหมวด และ {s}% แรกด้านยอดขาย",
        "overall_line_excellent": "{lvb} {k} จาก {n} เทรนด์ - ส่วนใหญ่มีสินค้าอยู่ใน {p}% แรกของสินค้าในหมวดเดียวกัน และขายดี",
        "overall_line": "{lvb} {k} จาก {n} เทรนด์ - ส่วนใหญ่มีสินค้าอยู่ใน {p}% แรกของสินค้าในหมวดเดียวกัน",
        "overall_line_below": "{lvb} แค่ {k} จาก {n} เทรนด์ - ส่วนใหญ่ยังไม่มีสินค้าอยู่ใน {p}% แรกของสินค้าในหมวดเดียวกัน",
        "vs_note": "แต่ละคอลัมน์ = 5 อันดับแรกของสินค้าในหมวดของเทรนด์ (# = อันดับในหมวด) · ช่องสีฟ้า = สินค้าของ {brand} · "
                   "แถวล่าง = สินค้าที่ดีที่สุดของ {brand} เมื่อไม่ติด 5 อันดับแรก · ไม่มีสินค้า {brand} ในหมวดนี้ = แถวล่างเป็นสีเทา",
        "pct_row": "ตำแหน่งในหมวด",
        "sl_top_sales": "{p}% แรกของหมวดด้านยอดขาย",
        "trend_note": "หมวด = หมวดหลักของเทรนด์ที่ AI เลือกจากความหมายของเทรนด์ (ไม่นับหมวดควบคู่) · สินค้าแต่ละชิ้นถูกจัดอันดับเทียบกับ"
                      "สินค้าทั้งหมวด · Top 5 = สินค้าที่ตรงเทรนด์ที่สุดทั้งหมวด ทุกแบรนด์ · ตรงเทรนด์ = คำอธิบายสินค้าใกล้กับเทรนด์ "
                      "ยังไม่ได้ตรวจยืนยันโดยคน",
        "m_fit": "ในแต่ละเทรนด์: (1) หมวด - AI เลือกหมวดหลักหมวดเดียว (Euromonitor Level 2) ที่เทรนด์อยู่ "
                 "จากความหมายของเทรนด์ต่อผู้ซื้อ โดยใช้หมวดของสินค้า Konvy ที่ตรงเทรนด์ที่สุด (เทียบ {n} ชิ้น) "
                 "เป็นหลักฐานประกอบ ไม่นับหมวดควบคู่ (2) ระดับ - สินค้า {brand} แต่ละชิ้นจัดอันดับตามความตรงเทรนด์เทียบกับสินค้า"
                 "ทั้งหมวดนั้น: Excellent = {p1}% แรก, Good = {p1}-{p2}% แรก, Average = {p2}-{p3}% แรก, Below average = ไม่ถึง "
                 "{p3}% แรก (อันดับ 1 ของหมวดนับเป็น {p1}% แรกเสมอ) ระดับของเทรนด์ = ระดับของสินค้าที่ดีที่สุดของ {brand} ในหมวดนั้น "
                 "ไม่มีสินค้าในหมวดนั้น = Below average ภาพรวมของแบรนด์ = ระดับสูงสุดที่เทรนด์เกินครึ่งทำได้ถึง "
                 "(นับระดับนั้นหรือดีกว่า) ครึ่งพอดีไม่นับ คำว่า \"เทรนด์ส่วนใหญ่\" จึงเป็นจริงเสมอ",
        "m_sales": "(3) ยอดขาย - หลังขั้น (2) ระดับของสินค้าแต่ละชิ้นถูกปรับตามยอดขายบน Konvy (จำนวนที่ขาย x ราคา เทียบกับสินค้า Konvy "
                   "อื่นในหมวดเดียวกัน): {s1}% แรก = ขายดี ดึงระดับ Average ขึ้นเป็น Good · "
                   "Excellent ต้องตรงเทรนด์ {p1}% แรก และขายดี ทั้งสองอย่าง ตรงเทรนด์ {p1}% แรกแต่ขายปานกลางหรือไม่มีข้อมูลยอดขายได้สูงสุด Good · "
                   "{s2}% ล่างสุด หรือขายได้ 0 ชิ้นทั้งที่มีของ = ขายได้น้อย ลดระดับลง 1 ขั้น · นอกจากนั้นขายปานกลางหรือไม่มีข้อมูลไม่เปลี่ยนระดับ "
                   "สินค้าที่ของหมดใช้จำนวนรีวิวแทน เพราะ Konvy ซ่อนตัวนับยอดขายเมื่อสต็อกหมด "
                   "ระดับของเทรนด์ = ระดับที่ดีที่สุดหลังปรับของสินค้า {brand} ในหมวดนั้น",
        "graded_group": "เทียบกับสินค้าในหมวด",
        "m_limits": "คะแนนความตรงเทรนด์วัดว่าข้อความของสินค้าใกล้กับคำอธิบายเทรนด์แค่ไหน ไม่ใช่ยอดขาย คุณภาพ "
                    "หรือความชอบของผู้บริโภค และยังไม่เคยตรวจเทียบกับการตัดสินของคน ชุดของขวัญ/เซ็ตรวมอยู่ในหมวดของตัวเอง "
                    "หมวดระดับ 2 กว้าง (เช่น Skin Care รวมเซรั่ม มาสก์ และคลีนเซอร์) สินค้าจึงถูกเทียบกับสินค้าหลายชนิดและหลายราคา "
                    "ใช้ระดับความพร้อมเพื่อจัดลำดับการพูดคุย ไม่ใช่คำตัดสินสุดท้าย",
        "cp_tier_count": "{n} ชิ้นในหมวดนี้ · ของ {brand} {b} ชิ้น",
        "cp_tier_you_best": "สินค้าที่ดีที่สุดของคุณในหมวดนี้",
        "cp_top_pct": "ติด {p}% แรกของหมวด",
        "cp_tier_none": "ไม่มีสินค้า {brand} ในหมวดนี้",
        "cp_no_brand_category": "{brand} ยังไม่มีสินค้าในหมวด {category} - แสดงสินค้าที่ตรงเทรนด์ที่สุดของหมวด",
        "cat_note": "อันดับ = ตำแหน่งของสินค้าในสินค้าทั้งหมวด เรียงตามความตรงเทรนด์ (1 = ตรงที่สุด) · ตรงเทรนด์ = คำอธิบายสินค้าใกล้กับ"
                    "เทรนด์ ยังไม่ได้ตรวจยืนยันโดยคน · ระดับเทียบกับสินค้าทั้งหมวด ตำแหน่งยอดขาย = จำนวนที่ขาย x ราคา เทียบกับสินค้าในหมวด",
    },
}


def with_l2_strings(strings, lang, group_basis):
    """ชุดข้อความของรายงาน + ชุดเกรดเทียบในหมวด L2 อย่างเดียวเมื่อ group_basis == "l2" (คืนชุดเดิมตัวเดียวกันถ้าไม่ใช่)"""
    return {**strings, **L2_STRINGS[lang]} if group_basis == "l2" else strings


def brand_strings(lang):
    """ข้อความตายตัวของรายงานแบรนด์ = ข้อความร่วมจากรายงานเทรนด์ (footer, ราคา ฯลฯ) + ข้อความเฉพาะรายงานแบรนด์"""
    return {**STRINGS[lang], **BRAND_STRINGS[lang]}


def apply_th(bctx, reason_translations):
    """brand context (สร้างจาก trend context ที่ localize เป็นไทยแล้ว) -> ฉบับไทย: ชื่อสินค้าเต็ม (มีภาษาไทย) และเหตุผล
    จับคู่สินค้าของแบรนด์ที่แปลแล้ว (กลุ่มไหนแปลไม่สำเร็จ ใช้ภาษาอังกฤษเดิม) - คืนสำเนาใหม่"""
    out = copy.deepcopy(bctx)
    for row in out["rows"]:
        th = reason_translations.get(row["name"]) or []
        for i, p in enumerate(row["products"]):
            p["name"] = p.get("name_full") or p["name"]
            if i < len(th) and th[i]:
                p["reason"] = th[i]
        # 🆕 (2026-10-07) สินค้าในตารางหมวด x ช่วงราคาของหน้าเทรนด์
        for e in row.get("categories") or []:
            for t in e.get("tiers") or []:
                if t.get("best"):
                    t["best"]["name"] = t["best"].get("name_full") or t["best"]["name"]
            for m in e.get("top") or []:
                m["name"] = m.get("name_full") or m["name"]
        for m in (row.get("cell") or {}).get("top") or []:   # หน้า "สินค้าตามเทรนด์ เทียบคู่แข่ง"
            m["name"] = m.get("name_full") or m["name"]
    return out
