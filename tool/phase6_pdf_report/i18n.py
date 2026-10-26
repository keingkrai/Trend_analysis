# -*- coding: utf-8 -*-
"""
⑯ PDF Report — ข้อความตายตัวของรายงาน 2 ภาษา (อังกฤษ/ไทย) + แปลงข้อมูลในรอบให้เป็นภาษาที่เลือก

เทมเพลตเดียวใช้ทั้ง 2 ภาษา: ข้อความตายตัว (หัวข้อหน้า, ป้ายกำกับ, ภาคผนวก) อยู่ใน STRINGS ส่วนค่าที่ขั้นก่อนหน้าตอบเป็นชุดคำตายตัว
(สถานะ, investment signal ฯลฯ) แปลงด้วย ENUM_TH ตรงๆ ไม่ผ่าน LLM - ข้อความยาวที่ LLM เขียน (บทวิเคราะห์) แปลใน enrich.py

หลักภาษาไทย: ชื่อเทรนด์ คีย์เวิร์ดค้นหา ชื่อแบรนด์/สินค้า และศัพท์เทคนิคคงเป็นภาษาอังกฤษ (ชื่อเทรนด์คือคีย์ที่ใช้ทั้งไปป์ไลน์
และคีย์เวิร์ดคือคำที่ค้น Google Trends จริง) ปี ค.ศ. เหมือนฉบับอังกฤษ (ข้อมูล Google Trends เป็น ค.ศ.)
"""
import copy
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import unquote

# 🆕 (2026-10-19) ปีระยะสั้น/ระยะยาวอ่านจาก common/horizons.py ที่เดียว - ข้อความตายตัวเขียนตัวแทนค่า @S@ (ปีระยะสั้น) @SR@ (ช่วงปี
# ระยะสั้น เช่น 1-3) @LR@ (ช่วงปีระยะยาว เช่น 4-5) แล้วแทนค่าครั้งเดียวท้าย STRINGS (apply_tokens) - ไม่ต้องไล่แก้ .format() ทุกจุด
_TOOL_DIR = str(Path(__file__).resolve().parents[1])
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)
from common.horizons import apply_tokens  # noqa: E402

LANGS = ("en", "th")

STRINGS = {
    "en": {
        "na": "n/a",
        "price_na": "Price n/a",
        "thb": "THB {v}",
        "copyright": "Copyright © {year} {company}",
        "rights": "All Rights Reserved",
        "cover_sub": "Trend Report",
        "cover_outlook": " · Outlook to {end}",
        "cover_sources": "Search data: Worldwide Google Trends (English keywords) | Product evidence: Konvy",
        "report_summary": "Report Summary",
        "prepared_by": "Prepared by:",
        "briefing": "Briefing:",
        "briefing_text": "The top {n} trends in {topic} are forecast to grow faster than the market in year @S@. They "
                         "were selected from {total} candidate trends identified in scientific publications, "
                         "consumer conversations and industry news, then forecast with worldwide Google Trends "
                         "data{end}.",
        "briefing_total_na": "the",
        "briefing_end": " to {end}",
        "top_insights": "Top Insights",
        "top_microtrends": "Top Microtrends",
        "trend_label": "Trend -",
        "insight_label": "Insight -",
        "takeaway": "Takeaway",
        "opportunity_label": "Opportunity -",
        "risk_label": "Risk -",
        "market_overview": "Market Overview",
        "trend_strength": "Trend strength",
        "current_signal": "current market signal",
        "direction": "Direction",
        "next_years": "next {years} years",
        "few": "few",
        "est_duration": "Estimated duration",
        "of_shift": "of the overall shift",
        "market_summary": "Market summary",
        "insufficient": "Not enough evidence",
        "grade_excellent": "Excellent",
        "grade_good": "Good",
        "grade_average": "Average",
        "grade_below_average": "Below Average",
        "ladder_difference": "What's different",
        "ladder_benefit": "What it does",
        "ladder_feeling": "How it feels",
        "dr_header": "Trend Drivers | Macro Forces & Personas",
        "dr_intro": "Which of the six macro forces drive each trend, and which emerging consumer personas it serves.",
        "dr_forces": "Macro forces (STEPIC)",
        "dr_personas": "Emerging personas",
        "dr_main": "Main link",
        "dr_some": "Supporting link",
        "dr_none": "No clear link in the evidence",
        "dr_total": "Trends with a main link",
        "dr_note": "Each mark is an AI judgement based only on this report's evidence for the trend, and must cite "
                   "the supporting text - marks without supporting text are dropped. Rule-based numbers elsewhere in "
                   "the report (expected growth, durability) do not use these marks.",
        "t5_header": "Top 5 Trends | Short Term vs Long Term",
        "t5_intro": "Top 5 trends with the highest growth potential in each period, out of {total} trends found",
        "t5_period": "Year {y} · {period}",
        "t5_links": "Lines join the same trend",
        "t5_past": "Last 12 months",
        "t5_both": "● Both periods · {other} rank {n}",
        "t5_short_only": "◇ Short term only · long-term rank {n} of {total}",
        "t5_long_only": "◆ Long term only · short-term rank {n} of {total}",
        "t5_legend_both": "In both lists = core trend",
        "t5_legend_short": "Short term only",
        "t5_legend_long": "Long term only",
        "t5_legend_all": "All {n} trends on the next page",
        # 🆕 (2026-10-02) แถบไทม์ไลน์นิยามระยะสั้น/ระยะยาว ใต้บรรทัด intro (แทน t5_legend_pct / t5_vs_last12)
        "t5_tl_base": "Baseline · {period}",
        "t5_tl_term": "= next {a}-{b} years · {start} - {end}",
        "t5_tl_year": "Year {y}",
        "t5_tl_rank": "Year {y} · used for ranking",
        "t5_tl_key": "% = expected average growth per year (compounded) in searches, from the last 12 months up to that "
                     "year. Compare trends within the same column only",
        "t5_rank_by": "Ranked by year {y} · {period}",
        # 🆕 (2026-10-02) ระยะสั้น = ปีที่ 2, ระยะยาว = ปีที่ 5 - {bands} = ประโยคช่วงคลาดเคลื่อนจาก band_text (เทมเพลตประกอบ)
        "t5_note": "Expected growth = average growth per year (compounded) in searches, from the last 12 months up to that "
                   "year, from a model that learned from past Google Trends data (2016-2022){bands}. These are not guaranteed "
                   "growth rates. 'Last 12 months' is actual Google Trends data.",
        "band_first": ", 8 times in 10 the actual result was {lo}% to +{hi}% from the year-{y} figure",
        "band_next": " and {lo}% to +{hi}% from the year-{y} figure",
        "ov_header": "All Trends | Year 1 to Year 5",
        "ov_intro": "All {n} trends found in this run. Numbers = expected change in searches compared with the last 12 months, ordered by year @S@.",
        "ov_trend": "Trend",
        "ov_year": "Year {y}",
        "ov_long_rank": "Year {y} rank",
        "ov_page": "Page",
        "ov_note_col": "Note",
        "m_yoy_header": "All Trends | YoY view (vs the year before)",
        "m_yoy_intro": "All {n} trends found in this run, ordered by expected growth to year @S@. Numbers = expected change in "
                       "searches compared with the year before (YoY); year 1 is compared with the last 12 months.",
        "m_yoy_note": "YoY for year n = expected searches in year n ÷ expected searches in year n-1, minus 1. Rows are ordered by "
                      "expected growth to year @S@ against the last 12 months (not by the YoY figure) and 'Year 5 rank' by growth "
                      "to year 5 on the same basis. Numbers are forecasts{bands}. Each year has its own bar scale - compare bars "
                      "within the same column only. Dashed line = the market as a whole; bar colour compares each cell with the "
                      "market's YoY of the same year, so a trend can be above the market in one year and below it the next. "
                      "Detail pages cover trends above the dashed line in year @S@ that have matching products.",
        "m_cagr_header": "All Trends | CAGR view (average per year)",
        "m_cagr_intro": "All {n} trends found in this run, ordered by expected growth to year @S@. Numbers = expected average yearly "
                        "growth in searches (CAGR, compounded) from the last 12 months up to that year.",
        "m_cagr_note": "CAGR for year n = (expected searches in year n ÷ average of the last 12 months) to the power 1/n, minus 1; "
                       "year 1 is the change against the last 12 months. Rows are ordered by expected growth to year @S@ and 'Year 5 "
                       "rank' by growth to year 5, both against the last 12 months. Numbers are forecasts{bands}. Each year has its "
                       "own bar scale - compare bars within the same column only. Dashed line = the market as a whole (half of all "
                       "keywords are expected to rise more, half less); bar colour = above / below the market level of that year. "
                       "Detail pages cover trends above the dashed line in year @S@ that have matching products.",
        # 🆕 (2026-10-19) หน้าเดียวที่มีทั้ง CAGR และ YoY (แทนหน้า m_cagr_* + m_yoy_* แยก)
        "m_both_header": "All Trends | CAGR and YoY",
        "m_both_intro": "All {n} trends in this run. Each year: bar = CAGR (average growth per year, compounded), "
                        "number beside it = YoY (change vs the year before).",
        "m_both_y1": "CAGR = YoY",
        "m_both_cagr": "CAGR",
        "m_both_yoy": "YoY",
        "m_both_legend_yoy": "YoY number: dark = at or above the market's YoY of that year, grey = below",
        "m_both_note": "CAGR for year n = (expected searches in year n ÷ average of the last 12 months) to the power 1/n, minus 1. "
                       "YoY for year n = expected searches in year n ÷ expected searches in year n-1, minus 1. Year 1 is the change against "
                       "the last 12 months, so both are the same. Rows are ordered by expected growth to year @S@ and 'Year 5 rank' by growth "
                       "to year 5, both against the last 12 months. Numbers are forecasts{bands}. Each year has its own bar scale - compare "
                       "bars within the same column only. Dashed line = the market as a whole; bar colour = above / below the market level "
                       "of that year; a grey YoY number is below the market's YoY of that year. "
                       "Detail pages cover trends above the dashed line in year @S@ that have matching products.",
        # 🆕 (2026-10-19) หน้ากราฟจุดกระจาย (report.html.j2 scatter_svg + หน้า "All Trends CAGR and YoY")
        "m_sc_intro": "All {n} trends. Each dot is one trend: across = CAGR (average growth per year), up = YoY (change vs the year before).",
        "m_sc_x": "CAGR (average growth per year)",
        "m_sc_y": "YoY (change vs the year before)",
        "m_sc_note": "CAGR for year n = (expected searches in year n ÷ average of the last 12 months) to the power 1/n, minus 1. "
                   "YoY for year n = expected searches in year n ÷ expected searches in year n-1, minus 1. The number on a dot is the # in "
                   "the list below, ordered by expected growth to year @S@ against the last 12 months. Numbers are forecasts{bands}. "
                   "Dashed lines = the market as a whole; blue = the trend is above the market level of that year. "
                   "Detail pages cover trends above the market line in year @S@ that have matching products.",
        "m_band_first": ": in back-tests, 8 times in 10 the actual search level was within {lo}% to +{hi}% of the forecast for year {y}",
        "m_band_next": " and {lo}% to +{hi}% for year {y}",
        "ov_line": "Market as a whole",
        "ov_line_detail": "{above} trends above the line ({detail} with detail pages) · {below} below",
        "ov_legend_above": "Above the market as a whole",
        "ov_legend_below": "Below the market as a whole",
        "ov_legend_market": "Market as a whole",
        "ov_channel": "Sales channel · no products found in the market",
        "ov_no_data": "Too little detail · no products found in the market",
        "ov_decline": "⚠ Searches down in the last 6 months",
        "ov_legend_decline": "Searches in the last 6 months more than 10% below the same months a year earlier "
                             "(actual data)",
        # 🆕 (2026-10-02) {bands} = ช่วงคลาดเคลื่อนปีที่ 2 / 5 จาก growth_score.FORECAST_BAND_80 (ไฟล์ผล ⑥) - เทมเพลตประกอบ
        "ov_note": "Numbers are forecasts. In back-tests{bands}. Each year has its own bar scale - "
                   "compare bars within the same column only. Dashed line = the market as a whole (half of all keywords "
                   "are expected to rise more, half less). Detail pages cover trends above the line in year @S@ that have "
                   "matching products.",
        "stepic_header": "Macro Forces | STEPIC",
        "stepic_intro": "Six forces shaping the market: Society, Technology, Environment, Policy, Industry and Creativity.",
        "personas_header": "Emerging Consumer Personas",
        "value_driver": "Value driver",
        "preferred_channels": "Preferred channels",
        "signals_header": "Cross-Dimensional Signals & Outlook",
        "next_3_months": "NEXT 3 MONTHS",
        "consumer_insights": "Consumer Insights",
        "divider_sub": "Top {n} Trends & Overlooked Opportunities",
        "divider_text": "Each trend is presented on two pages. The first shows the trend with its "
                        "short-term and long-term signals, its search-interest forecast and a workshop "
                        "question that frames the opportunity for your brand. The second shows the products"
                        " currently listed at Konvy that best match the trend. Trends are ordered by "
                        "expected search growth in year @S@.",
        "short_term": "Short term",
        "long_term": "Long term",
        "breadth": "Sources confirming",
        "short_term_def": "Years @SR@: expected change in searches compared with the last 12 months - trends are ranked by year @S@.",
        "long_term_def": "Years @LR@, the same measure - the long-term list is ranked by year 5, which is much less certain.",
        "breadth_def": "In how many of the 3 independent source types (scientific publications, consumer conversations, "
                       "industry news) the trend's search keywords were found.",
        "chart_caption": "Expected growth in searches",
        "chart_caption_end": " (vs the last 12 months)",
        "chart_alt": "Forecast chart",
        "legend_cagr": "Average growth per year",
        "legend_yoy": "Change vs the year before",
        "legend_hist": "Actual",
        "legend_avg": "12-month avg",
        "kpi_short": "Short term · year @S@",
        "kpi_long": "Long term · year 5",
        "kpi_vs_last12": "vs last 12 months",
        "kpi_cagr_sub": "a year on average, vs last 12 months",
        "cagr_fact": "Blue figures = average growth per year (compounded) vs the last 12 months; grey figures = change vs the year before "
                     "(year 1 is the same for both)",
        "kpi_sources": "Sources confirming",
        "of_3": "of 3",
        "target_consumer": "Target consumer",
        "tracked_keywords": "Tracked search keywords",
        "months_with_data": "search data in {pct}% of months",
        "rank_score": "Year @S@: expected to rise more than {v}% of market keywords",
        "overlooked": "Overlooked Opportunity {n}",
        "workshop_question": "Workshop Question",
        "evidence_sub": "Market evidence - examples of products at Konvy that best match this trend",
        "no_products": "No product-matching results for this trend in this run.",
        "np_sub": "Market evidence",
        "np_title": "No products found in the market",
        "np_channel": "This trend describes a sales channel or a buying behaviour, not product features, so no products "
                      "at Konvy could be matched to it. The trend itself is explained on the previous page.",
        "np_no_data": "The information behind this trend is too thin to describe a product, so no products at Konvy "
                      "could be matched to it. The trend itself is explained on the previous page.",
        "evidence_note": "Products are ranked by how well each product's description matches the trend{stats}. These are "
                         "the best matches that exist today - not confirmed to deliver the trend.",
        "evidence_stats": " (this trend: best {best}, average {mean} across {n} products)",
        "cat_sub": "Market evidence - examples of products at Konvy that best match this trend, by category",
        "cat_dist": "Which categories the top {n} matches for this trend belong to",
        "cat_dist_of": "(the best {pct}% of {total} products)",
        # 🆕 (2026-10-08) หมวดหลักที่ LLM เลือกหมวดเดียว - แถบ/คอลัมน์ = ชนิดสินค้าในหมวดนั้น
        "cat_sub_main": "Market evidence - examples at Konvy that best match this trend, in its main category: {category}",
        "cat_dist_main": "Which {category} product types the top {n} matches for this trend belong to",
        "cat_dist_main_of": "(this category has {total} products)",
        "cat_other": "Other categories",
        "cat_count": "{n} match the trend, out of {total} products in this group",
        "cat_price": "Median {median} · range {lo}-{hi}",
        "cat_rank": "#{n} match in the whole store",
        "cat_all_types": "All product types",
        # 🆕 (2026-10-12) ช่วงราคาต่อปริมาณ (unit_i18n.UNIT_STRINGS ทับข้อความช่วงเมื่อรอบนั้นใช้ราคาต่อปริมาณ)
        "unit_ml": "ml", "unit_g": "g", "unit_ml_g": "ml/g", "unit_pcs": "pcs", "mini": "trial size",
        # 🆕 (2026-10-07) ช่วงราคาตลาดต่อคอลัมน์
        "cat_by_price": "By price: {parts}",
        "tier_low": "Low price", "tier_mid": "Mid price", "tier_high": "High price", "tier_all": "All prices",
        "tier_low_s": "Low", "tier_mid_s": "Mid", "tier_high_s": "High", "tier_all_s": "All",
        "cat_note_tiers": "Categories are standard product categories (Euromonitor Level 2, Beauty and "
                          "Personal Care only), ordered by how many of the best matches they hold. Fewer "
                          "than 3 = left out; with fewer than four, the largest is split by product type. "
                          "Price tiers split every product of the category or type in the store into three "
                          "equal-sized groups by price - the same bands for every trend. Each row is the "
                          "best match in that tier. Bar = match strength vs the best match shown; # = place"
                          " among all {n} products. 'Match' = the product description is close to the "
                          "trend; not confirmed to deliver it.",
        "cat_note_main": "Main category ({category}) is chosen by AI from what the trend means, using the categories of "
                         "the best-matching products as evidence. Columns = product types of that category with the most "
                         "matches (at least 3). Price tiers = thirds of that type's store prices, the same for every "
                         "trend; each row = best match in that tier. Bar = match strength vs the best match shown; # = "
                         "place among all {n} products. 'Match' = the product description is close to the trend; not "
                         "confirmed to deliver it.",
        "cat_other_main": "Other product types",
        "cat_note": "Categories are standard product categories (Euromonitor Level 2, Beauty and Personal "
                    "Care only), ordered by how many of the best matches they hold. Categories with fewer "
                    "than 3 are left out; when fewer than four remain, the largest is split by product "
                    "type. Bar = how well the product's description matches the trend, relative to the best"
                    " match shown; # = its place among all {n} products in the store. These are the best "
                    "matches that exist today, not confirmed trend fits.",
        "method_header": "Appendix | Methodology",
        "method_1_title": "1. Evidence collection",
        "method_1": "Articles are gathered from three independent source types: scientific publications, consumer "
                    "conversations and industry news. An AI model extracts subject-relation-object statements from "
                    "each document, and a statement is kept only when its supporting sentence is found word-for-word "
                    "in the source. Statements are grouped into trend candidates by graph clustering (Louvain, 20-run "
                    "consensus){total}.",
        "method_1_total": " - {n} candidates in this run",
        "method_2_title": "2. Search-interest forecast",
        "method_2": "Each trend's search keywords are tracked monthly in worldwide Google Trends (no category filter). Expected growth for years 1 to 5 = average search interest expected in that year ÷ the last 12 months, from a random-forest model trained on the past growth of all keywords (its inputs include last year's growth, growth against the same months a year earlier, recent momentum, distance from peak and volatility), and a trend's score is the percentile of its expected growth (the average of its keywords) among all keywords in the run. Back-tests 2016-2022 on two data sets: rankings agreed with actual growth at Spearman about 0.52 (year 1), 0.45 (year 3) and 0.40 (year 5); a trend's expected level was off by a median 6% (year 1), 12% (year 3) and 20% (year 5), and the shaded range in the charts held 80% of outcomes. The dashed monthly line spreads each yearly level over the trend's seasonal pattern from the four years before August 2025. Last year's growth is not ranked on its own for now: the unfiltered Google Trends series jumps for every keyword from August 2025, which inflates it.",
        "method_3_title": "3. Ranking and selection",
        "method_3": "Trends are ranked by expected search growth in year @S@, the short term (0.5 = market median). "
                    "Detail pages cover only the trends above the market median ({n} in this report){np_note} "
                    "Trends below the median appear only in the overview tables and charts. Durability (Longevity "
                    "Score) is calculated with fixed rules from evidence verdicts - numbers are never produced by "
                    "the AI. The Market Overview figures are the median of all trends (half of the trends are "
                    "above, half below).",
        "method_3_np": ", {k} of them sales-channel or shopping-behaviour trends with no product attributes, so "
                       "their second page explains that no matching products were found.",
        "method_3_np_none": ".",
        "method_4_title": "4. Product matching",
        "method_4": "Each trend's profile (benefits, job-to-be-done, point of difference) is turned into numbers that "
                    "capture its meaning (a text embedding) and compared with the descriptions of {n} Konvy products "
                    "- the closer the meaning, the better the match. The best matches are listed with a short "
                    "AI-written reason.",
        "method_4_cat": "Each trend's profile (benefits, job-to-be-done, point of difference) is turned into numbers that "
                        "capture its meaning (a text embedding) and compared with the descriptions of {n} Konvy products "
                        "- the closer the meaning, the better the match. The top 1% of matches show which categories the "
                        "trend touches; the four categories holding the most of them (Euromonitor Level 2, at least 3 "
                        "products each) are listed with their three best matches each; when fewer than four qualify, the "
                        "largest category is split by product type.",
        "method_4_main": "Each trend's profile (benefits, job-to-be-done, point of difference) is turned into numbers that "
                         "capture its meaning (a text embedding) and compared with the descriptions of {n} Konvy products "
                         "- the closer the meaning, the better the match. An AI then chooses the one main category "
                         "(Euromonitor Level 2) the trend belongs to, from the trend's meaning and the categories of the "
                         "best matches; complementary categories are not counted. The product types of that category with "
                         "the most matches are shown by price tier - low, mid and high thirds of that product type's "
                         "prices in the store - with the best match in each tier.",
        "method_4_tiers": "Each trend's profile (benefits, job-to-be-done, point of difference) is turned into numbers that "
                          "capture its meaning (a text embedding) and compared with the descriptions of {n} Konvy products "
                          "- the closer the meaning, the better the match. The top 1% of matches show which categories the "
                          "trend touches; the four categories holding the most of them (Euromonitor Level 2, at least 3 "
                          "products each; the largest is split by product type when fewer than four qualify) are shown by "
                          "price tier - low, mid and high thirds of that category's prices in the store - with the best "
                          "match in each tier.",
        # 🆕 (2026-10-21) หน้าสินค้าของเทรนด์ = แผนที่ "ความใกล้เทรนด์ x ยอดขาย" ระดับหมวด L2 (l2_map.py)
        "l2_sub": "Market evidence - how the {n} {category} products at Konvy match this trend, and how well they sell",
        "l2_corner_y": "Sales on Konvy ↓", "l2_corner_x": "Match with the trend →",
        "l2_lv_excellent": "Excellent", "l2_lv_good": "Good", "l2_lv_average": "Average", "l2_lv_below_average": "Below average",
        "l2_x_first": "top {p}% of the category", "l2_x_mid": "{a}-{b}% of the category", "l2_x_last": "beyond {p}%",
        "l2_y_strong": "Strong sales", "l2_y_strong_sub": "top {p}%", "l2_y_steady": "Steady sales", "l2_y_steady_sub": "middle",
        "l2_y_slow": "Slow sales", "l2_y_slow_sub": "bottom {p}%",
        "l2_empty": "no products",
        "l2_card_match": "Match #{rank}",
        "l2_sales_top": "Sales top {p}%", "l2_sold": "{n} sold", "l2_soldout": "Sold out", "l2_reviews": "{n} reviews",
        "l2_review1": "1 review", "l2_zero": "No sales while in stock",
        "l2_take": "Among the closest matches (top {p}% of the category), {s}% sell strongly and {l}% sell slowly; across all "
                   "{category} products it is {sa}% and {la}%.",
        "l2_note": "Each product of {category} (the trend's main category) is placed by how close its description is to the trend "
                   "(columns = position among the category's {total} products). Rows = its Konvy sales compared with the other "
                   "{category} products (units sold x price; sold-out items use reviews). The product shown = the closest match in "
                   "that cell; products with no sales data are left out. Shading = grade after sales lift or lower a product one "
                   "step (strong sales lift an Average product to Good; Excellent needs a top-{p1}% match and strong sales; "
                   "slow sales lower one step).",
        "method_4_l2": "Each trend's profile (benefits, job-to-be-done, point of difference) is turned into numbers that "
                       "capture its meaning (a text embedding) and compared with the descriptions of {n} Konvy products "
                       "- the closer the meaning, the better the match. An AI then chooses the one main category "
                       "(Euromonitor Level 2) the trend belongs to, from the trend's meaning and the categories of the "
                       "best matches; complementary categories are not counted. Every product of that category is placed by "
                       "how close it is to the trend (top {p1}%, {p1}-{p2}%, {p2}-{p3}% of the category, then the rest) and by "
                       "its Konvy sales compared with the other products of the category (the top {s1}% = strong sales, the "
                       "bottom {s2}% or no sales while in stock = slow sales; sold-out products use review counts). The "
                       "closest match in each cell is shown. Sales are lifetime Konvy sales (units x today's price), an "
                       "estimate and not company sales.",
        "notes_header": "Appendix | Notes & Data",
        "run_details": "Run details",
        "topic": "Topic",
        "run_id": "Run ID",
        "data_collected": "Data collected",
        "report_generated": "Report generated",
        "forecast_window": "Forecast window",
        "language_models": "AI models",
        "report_copy": "English copy",
        "how_to_use": "How to use this report",
        "how_to_use_text": "This report is a decision-support tool, not a final answer. Steps that use AI (query generation, "
                           "trend naming, profiles and the English copy in this report) can vary between runs. Product "
                           "matching has not yet been measured against human-labelled examples, so matched products show "
                           "where the shelf is closest to a trend - not proof that a product delivers it.",
        "data_not_available": "Data not available in this run",
        # 🆕 (2026-10-14) กล่อง "แหล่งที่มาของข้อมูล" ท้ายหน้า Notes (source_rows) - ไม่ใช้คำว่า Paper/Social (ไม่แสดงสายหลักฐาน)
        "data_sources": "Where the data comes from",
        "data_src_papers": "Research articles",
        "data_src_discussions": "Online channels",
        "data_src_news": "News",
        "data_src_search": "Search interest",
        "data_src_products": "Products",
        "data_src_categories": "Product categories",
        "data_src_used": "{n} used",
        "data_src_searched": "searched {names}",
        "data_src_posts": "{n} {posts} used",
        "data_src_post_one": "post or video",
        "data_src_post_many": "posts and videos",
        "data_src_news_intl": "{n} international {articles} used",
        "data_src_news_th": "{n} Thai {articles} used",
        "data_src_article_one": "article",
        "data_src_article_many": "articles",
        "data_src_search_text": "Google Trends, worldwide, monthly - {n} keywords",
        "data_src_search_asof": "data up to {month}",
        "data_src_products_text": "Konvy - {n} beauty and personal care products",
        "data_src_collected": "collected {dates}",
        "data_src_categories_text": "Euromonitor classification, Levels 1-4",
        "data_docs_header": "Appendix | Source list",
        "data_doc_search": "search: {q}",
        "mo_faster": "Trends above the market (year @S@)",
        "mo_faster_val": "{n} of {total}",
        "mo_faster_sub": "expected change in searches in year @S@",
        "kpi_past": "Last 12 months (actual)",
        "vs_prev12": "vs previous 12 months",
        "kpi_recent": "Last 6 months {v} vs a year earlier",
        "kpi_longevity": "Durability {v}/100",
        "no_history": "No forecast for this trend in this run",
        "durability": "Durability",
        "durability_def": "Score 0-100 - how likely the trend is to last beyond a short-lived fad, scored with fixed rules from the evidence. Excellent 70+, Good 55-69, Average 40-54, Below Average under 40.",
        "legend_fc": "Expected monthly",
        "legend_band": "80% range of yearly avg",
        # 🆕 (2026-10-01) หน้าภาพรวมตลาด: ตัวเลขของเทรนด์ตรงกลางเป็นค่าหลัก (เดิมเป็นป้าย Moderate / Strengthening / Medium-term)
        "mo_short": "Year @S@ search vs the last 12 months",
        "mo_short_sub": "Middle of the {n} trends: half above, half below",
        "mo_long": "Year 5 search vs the last 12 months",
        "mo_long_sub": "5-year total, not per year · middle of the {n} trends",
        "mo_dur": "Durability (0-100)",
        "mo_dur_sub": "Middle of the {n} trends · scored from the evidence",
        # 🆕 (2026-10-01) ตัวเลข "12 เดือนที่ผ่านมา" / "6 เดือนล่าสุด" สูงเกินจริงจากการกระโดดของข้อมูล (report_data.PAST_CLEAN_FROM)
        "past_mark": "*",
        "past_note": "* Worldwide Google Trends data jumped for every keyword from Aug 2025 (by different "
                     "amounts). The last-12-month and last-6-month figures are therefore inflated and "
                     "should not be used to compare trends - use the expected figures instead.",
        "ov_short": "Short term",
        "ov_long": "Long term",
        "ov_short_def": "Short term = years @SR@",
        "ov_long_def": "Long term = years @LR@",
        "u_upto": "up to {v}",
        "u_from": "from {v}",
    },
    "th": {
        "na": "ไม่มีข้อมูล",
        "price_na": "ไม่มีข้อมูลราคา",
        "thb": "{v} บาท",
        "copyright": "Copyright © {year} {company}",
        "rights": "สงวนลิขสิทธิ์",
        "cover_sub": "รายงานเทรนด์",
        "cover_outlook": " · มองไปถึง {end}",
        "cover_sources": "ข้อมูลการค้นหา: Google Trends ทั่วโลก (คีย์เวิร์ดภาษาอังกฤษ) | หลักฐานสินค้า: Konvy",
        "report_summary": "สรุปรายงาน",
        "prepared_by": "จัดทำโดย:",
        "briefing": "ภาพรวม:",
        "briefing_text": "{n} เทรนด์อันดับต้นในหมวด {topic} (คาดว่าโตสูงกว่าระดับตลาดในปีที่ @S@) คัดจากเทรนด์ตั้งต้น "
                         "{total} เทรนด์ที่พบในงานวิจัย บทสนทนาของผู้บริโภค และข่าวอุตสาหกรรม "
                         "แล้วพยากรณ์ด้วยข้อมูล Google Trends ทั่วโลก{end}",
        "briefing_total_na": "ทั้งหมด",
        "briefing_end": " ถึง {end}",
        "top_insights": "อินไซต์หลัก",
        "top_microtrends": "เทรนด์ย่อยอันดับต้น",
        "trend_label": "เทรนด์ -",
        "insight_label": "อินไซต์ -",
        "takeaway": "ข้อสรุปสำคัญ",
        "opportunity_label": "โอกาส -",
        "risk_label": "ความเสี่ยง -",
        "market_overview": "ภาพรวมตลาด",
        "trend_strength": "ความแข็งแรงของเทรนด์",
        "current_signal": "สัญญาณตลาดปัจจุบัน",
        "direction": "ทิศทาง",
        "next_years": "ใน {years} ปีข้างหน้า",
        "few": "อีกไม่กี่",
        "est_duration": "ระยะเวลาโดยประมาณ",
        "of_shift": "ของการเปลี่ยนแปลงโดยรวม",
        "market_summary": "สรุปภาพตลาด",
        "insufficient": "หลักฐานไม่พอ",
        "grade_excellent": "ดีเยี่ยม",
        "grade_good": "ดี",
        "grade_average": "ปานกลาง",
        "grade_below_average": "ต่ำกว่าเกณฑ์",
        "ladder_difference": "จุดต่าง",
        "ladder_benefit": "ประโยชน์",
        "ladder_feeling": "ความรู้สึก",
        "dr_header": "แรงขับของเทรนด์ | แรงขับมหภาคและกลุ่มผู้บริโภค",
        "dr_intro": "แรงขับมหภาค 6 ด้านข้อใดขับเคลื่อนแต่ละเทรนด์ และเทรนด์นั้นตอบกลุ่มผู้บริโภคที่กำลังเกิดขึ้นกลุ่มไหน",
        "dr_forces": "แรงขับมหภาค (STEPIC)",
        "dr_personas": "กลุ่มผู้บริโภคที่กำลังเกิดขึ้น",
        "dr_main": "เชื่อมโยงหลัก",
        "dr_some": "เกี่ยวข้อง",
        "dr_none": "ไม่พบความเชื่อมโยงในข้อมูล",
        "dr_total": "จำนวนเทรนด์ที่เชื่อมโยงหลัก",
        "dr_note": "แต่ละช่องเป็นการตัดสินของ AI จากหลักฐานของเทรนด์ในรายงานนี้เท่านั้น "
                   "และต้องอ้างข้อความที่สนับสนุน ช่องที่ไม่มีข้อความสนับสนุนถูกตัดออก "
                   "ตัวเลขที่คิดด้วยกฎตายตัวในส่วนอื่นของรายงาน (การเติบโตที่คาด, โอกาสอยู่ยาว) ไม่ได้ใช้ผลนี้",
        "t5_header": "เทรนด์เด่น | ระยะสั้น เทียบ ระยะยาว",
        "t5_intro": "Top 5 เทรนด์ที่มีโอกาสเติบโตสูงสุดในแต่ละช่วง จากทั้งหมด {total} เทรนด์ที่พบ",
        "t5_period": "ปีที่ {y} · {period}",
        "t5_links": "เส้นเชื่อมเทรนด์เดียวกัน",
        "t5_past": "12 เดือนที่ผ่านมา",
        "t5_both": "● ทั้งสองระยะ · {other}อันดับ {n}",
        "t5_short_only": "◇ เฉพาะระยะสั้น · ระยะยาวอันดับ {n} จาก {total}",
        "t5_long_only": "◆ เฉพาะระยะยาว · ระยะสั้นอันดับ {n} จาก {total}",
        "t5_legend_both": "ติดทั้งสองระยะ = เทรนด์หลัก",
        "t5_legend_short": "ติดเฉพาะระยะสั้น",
        "t5_legend_long": "ติดเฉพาะระยะยาว",
        "t5_legend_all": "ครบทั้ง {n} เทรนด์ในหน้าถัดไป",
        "t5_tl_base": "ฐานเทียบ · {period}",
        "t5_tl_term": "= {a}-{b} ปีข้างหน้า · {start} - {end}",
        "t5_tl_year": "ปีที่ {y}",
        "t5_tl_rank": "ปีที่ {y} · ใช้จัดอันดับ",
        "t5_tl_key": "ตัวเลข % = อัตราการเติบโตเฉลี่ยต่อปี (ทบต้น) ของยอดค้นหาที่คาด นับจาก 12 เดือนล่าสุดถึงปีนั้น "
                     "ให้เทียบเฉพาะเทรนด์ในคอลัมน์เดียวกัน",
        "t5_rank_by": "เรียงตามปีที่ {y} · {period}",
        "t5_note": "การเติบโตที่คาด = อัตราเฉลี่ยต่อปี (ทบต้น) ของยอดค้นหาที่คาด นับจากค่าเฉลี่ย 12 เดือนล่าสุดถึงปีนั้น "
                   "จากโมเดลที่เรียนจากข้อมูล Google Trends ในอดีต (ปี 2016-2022){bands} ตัวเลขนี้ไม่ใช่ % การเติบโตที่รับประกัน "
                   "\"12 เดือนที่ผ่านมา\" คือข้อมูลจริงจาก Google Trends",
        "band_first": " 8 ใน 10 ครั้ง ผลจริงอยู่ในช่วง {lo}% ถึง +{hi}% ของตัวเลขปีที่ {y}",
        "band_next": " และ {lo}% ถึง +{hi}% ของตัวเลขปีที่ {y}",
        "ov_header": "ภาพรวมทุกเทรนด์ | ปีที่ 1 ถึงปีที่ 5",
        "ov_intro": "{n} เทรนด์ที่พบในรอบนี้ ตัวเลข = ยอดค้นหาที่คาดว่าจะเปลี่ยนไปเทียบกับ 12 เดือนล่าสุด เรียงตามปีที่ @S@",
        "ov_trend": "เทรนด์",
        "ov_year": "ปีที่ {y}",
        "ov_long_rank": "อันดับปี {y}",
        "ov_page": "หน้า",
        "ov_note_col": "หมายเหตุ",
        "m_yoy_header": "ภาพรวมทุกเทรนด์ | มุมมอง YoY (เทียบปีก่อนหน้า)",
        "m_yoy_intro": "{n} เทรนด์ที่พบในรอบนี้ เรียงตามการเติบโตที่คาดถึงปีที่ @S@ ตัวเลข = ยอดค้นหาที่คาดว่าจะเปลี่ยนไปเทียบกับปีก่อนหน้า "
                       "(YoY) ปีที่ 1 เทียบกับ 12 เดือนล่าสุด",
        "m_yoy_note": "YoY ของปีที่ n = (ยอดค้นหาที่คาดในปีที่ n ÷ ยอดค้นหาที่คาดในปีที่ n-1) ลบ 1 · แถวเรียงตามการเติบโตที่คาดถึงปีที่ @S@ "
                      "เทียบ 12 เดือนล่าสุด (ไม่ได้เรียงตามค่า YoY) และ \"อันดับปี 5\" เรียงตามการเติบโตถึงปีที่ 5 ฐานเดียวกัน · "
                      "ตัวเลขเป็นค่าคาดการณ์{bands} · แต่ละปีใช้สเกลแท่งของตัวเอง ให้เทียบความยาวแท่งเฉพาะในคอลัมน์เดียวกัน · "
                      "เส้นประ = ระดับตลาดโดยรวม สีแท่งเทียบแต่ละช่องกับ YoY ของตลาดในปีเดียวกัน เทรนด์จึงอาจสูงกว่าตลาดในปีหนึ่ง "
                      "แล้วต่ำกว่าในปีถัดไป · หน้ารายละเอียดทำเฉพาะเทรนด์เหนือเส้นประในปีที่ @S@ ที่จับคู่สินค้าได้",
        "m_cagr_header": "ภาพรวมทุกเทรนด์ | มุมมอง CAGR (เฉลี่ยต่อปี)",
        "m_cagr_intro": "{n} เทรนด์ที่พบในรอบนี้ เรียงตามการเติบโตที่คาดถึงปีที่ @S@ ตัวเลข = อัตราการเติบโตเฉลี่ยต่อปีแบบทบต้น (CAGR) "
                        "ของยอดค้นหาที่คาด นับจาก 12 เดือนล่าสุดถึงปีนั้น",
        "m_cagr_note": "CAGR ของปีที่ n = (ยอดค้นหาที่คาดในปีที่ n ÷ ค่าเฉลี่ย 12 เดือนล่าสุด) ยกกำลัง 1/n ลบ 1 ปีที่ 1 คือการเปลี่ยนแปลงเทียบ "
                       "12 เดือนล่าสุด · แถวเรียงตามการเติบโตที่คาดถึงปีที่ @S@ และ \"อันดับปี 5\" เรียงตามการเติบโตถึงปีที่ 5 "
                       "ทั้งคู่เทียบ 12 เดือนล่าสุด · ตัวเลขเป็นค่าคาดการณ์{bands} · แต่ละปีใช้สเกลแท่งของตัวเอง ให้เทียบความยาวแท่ง"
                       "เฉพาะในคอลัมน์เดียวกัน · เส้นประ = ระดับตลาดโดยรวม (คีย์เวิร์ดครึ่งหนึ่งคาดว่าเพิ่มมากกว่านี้ อีกครึ่งน้อยกว่า) "
                       "สีแท่ง = สูงกว่า/ต่ำกว่าระดับตลาดของปีนั้น · หน้ารายละเอียดทำเฉพาะเทรนด์เหนือเส้นประในปีที่ @S@ ที่จับคู่สินค้าได้",
        # 🆕 (2026-10-19) หน้าเดียวที่มีทั้ง CAGR และ YoY (แทนหน้า m_cagr_* + m_yoy_* แยก)
        "m_both_header": "ภาพรวมทุกเทรนด์ | CAGR และ YoY",
        "m_both_intro": "{n} เทรนด์ที่พบในรอบนี้ แต่ละปี: แท่งกราฟ = CAGR (เติบโตเฉลี่ยต่อปีแบบทบต้น) "
                        "ตัวเลขข้างกัน = YoY (เปลี่ยนเทียบปีก่อนหน้า)",
        "m_both_y1": "CAGR = YoY",
        "m_both_cagr": "CAGR",
        "m_both_yoy": "YoY",
        "m_both_legend_yoy": "ตัวเลข YoY: สีเข้ม = ไม่ต่ำกว่า YoY ของตลาดในปีนั้น สีเทา = ต่ำกว่า",
        "m_both_note": "CAGR ของปีที่ n = (ยอดค้นหาที่คาดในปีที่ n ÷ ค่าเฉลี่ย 12 เดือนล่าสุด) ยกกำลัง 1/n ลบ 1 · "
                       "YoY ของปีที่ n = (ยอดค้นหาที่คาดในปีที่ n ÷ ยอดค้นหาที่คาดในปีที่ n-1) ลบ 1 · ปีที่ 1 เทียบ 12 เดือนล่าสุด "
                       "ทั้งสองค่าจึงเท่ากัน · แถวเรียงตามการเติบโตที่คาดถึงปีที่ @S@ และ \"อันดับปี 5\" เรียงตามการเติบโตถึงปีที่ 5 "
                       "ทั้งคู่เทียบ 12 เดือนล่าสุด · ตัวเลขเป็นค่าคาดการณ์{bands} · แต่ละปีใช้สเกลแท่งของตัวเอง ให้เทียบความยาวแท่ง"
                       "เฉพาะในคอลัมน์เดียวกัน · เส้นประ = ระดับตลาดโดยรวม สีแท่ง = สูงกว่า/ต่ำกว่าระดับตลาดของปีนั้น "
                       "ตัวเลข YoY สีเทา = ต่ำกว่า YoY ของตลาดในปีนั้น · หน้ารายละเอียดทำเฉพาะเทรนด์เหนือเส้นประในปีที่ @S@ ที่จับคู่สินค้าได้",
        # 🆕 (2026-10-19) หน้ากราฟจุดกระจาย (report.html.j2 scatter_svg + หน้า "All Trends CAGR and YoY")
        "m_sc_intro": "{n} เทรนด์ที่พบในรอบนี้ 1 จุด = 1 เทรนด์ แนวนอน = CAGR (เติบโตเฉลี่ยต่อปี) แนวตั้ง = YoY (เปลี่ยนเทียบปีก่อนหน้า)",
        "m_sc_x": "CAGR (เติบโตเฉลี่ยต่อปี)",
        "m_sc_y": "YoY (เปลี่ยนเทียบปีก่อนหน้า)",
        "m_sc_note": "CAGR ของปีที่ n = (ยอดค้นหาที่คาดในปีที่ n ÷ ค่าเฉลี่ย 12 เดือนล่าสุด) ยกกำลัง 1/n ลบ 1 · "
                   "YoY ของปีที่ n = (ยอดค้นหาที่คาดในปีที่ n ÷ ยอดค้นหาที่คาดในปีที่ n-1) ลบ 1 · เลขบนจุดคือลำดับในรายชื่อด้านล่าง "
                   "เรียงตามการเติบโตที่คาดถึงปีที่ @S@ เทียบ 12 เดือนล่าสุด · ตัวเลขเป็นค่าคาดการณ์{bands} · "
                   "เส้นประ = ระดับตลาดโดยรวม จุดสีฟ้า = เทรนด์สูงกว่าระดับตลาดของปีนั้น · "
                   "หน้ารายละเอียดทำเฉพาะเทรนด์เหนือเส้นตลาดในปีที่ @S@ ที่จับคู่สินค้าได้",
        "m_band_first": " ทดสอบย้อนหลัง 8 ใน 10 ครั้ง ระดับยอดค้นหาจริงอยู่ในช่วง {lo}% ถึง +{hi}% ของค่าที่พยากรณ์ปีที่ {y}",
        "m_band_next": " และ {lo}% ถึง +{hi}% ของปีที่ {y}",
        "ov_line": "ระดับตลาดโดยรวม",
        "ov_line_detail": "เหนือเส้น {above} เทรนด์ (มีหน้ารายละเอียด {detail}) · ใต้เส้น {below} เทรนด์",
        "ov_legend_above": "สูงกว่าระดับตลาดโดยรวม",
        "ov_legend_below": "ต่ำกว่าระดับตลาดโดยรวม",
        "ov_legend_market": "ระดับตลาดโดยรวม",
        "ov_channel": "ช่องทางการขาย · ไม่พบสินค้าในตลาด",
        "ov_no_data": "ข้อมูลไม่พอ · ไม่พบสินค้าในตลาด",
        "ov_decline": "⚠ ค้นหาลดลงจริง 6 เดือนล่าสุด",
        "ov_legend_decline": "ยอดค้นหา 6 เดือนล่าสุดต่ำกว่าช่วงเดียวกันของปีก่อนเกิน 10% (ข้อมูลจริง)",
        "ov_note": "ตัวเลขเป็นค่าคาดการณ์ ทดสอบย้อนหลังแล้ว{bands} "
                   "· แต่ละปีใช้สเกลแท่งของตัวเอง ให้เทียบความยาวแท่งเฉพาะในคอลัมน์เดียวกัน · เส้นประ = ระดับตลาด"
                   "โดยรวม (คีย์เวิร์ดครึ่งหนึ่งคาดว่าเพิ่มมากกว่านี้ อีกครึ่งน้อยกว่า) · หน้ารายละเอียดทำเฉพาะเทรนด์เหนือเส้นในปีที่ @S@ "
                   "ที่จับคู่สินค้าได้",
        "stepic_header": "แรงขับระดับมหภาค | STEPIC",
        "stepic_intro": "6 แรงขับที่กำหนดทิศทางตลาด: สังคม เทคโนโลยี สิ่งแวดล้อม นโยบาย อุตสาหกรรม และความคิดสร้างสรรค์",
        "personas_header": "กลุ่มผู้บริโภคที่กำลังเกิดขึ้น",
        "value_driver": "สิ่งที่ให้คุณค่า",
        "preferred_channels": "ช่องทางที่ใช้",
        "signals_header": "สัญญาณข้ามมิติและแนวโน้มข้างหน้า",
        "next_3_months": "3 เดือนข้างหน้า",
        "consumer_insights": "อินไซต์ผู้บริโภค",
        "divider_sub": "{n} เทรนด์อันดับต้นและโอกาสที่ถูกมองข้าม",
        "divider_text": "แต่ละเทรนด์มี 2 หน้า: เทรนด์พร้อมสัญญาณระยะสั้นและระยะยาว กราฟพยากรณ์ความสนใจการค้นหา "
                        "และคำถามเวิร์กช็อปที่ชี้โอกาสให้แบรนด์ของคุณ และสินค้าบน Konvy ที่ตรงกับเทรนด์ที่สุด "
                        "เทรนด์เรียงตามการเติบโตของการค้นหาที่คาดในปีที่ @S@",
        "short_term": "ระยะสั้น",
        "long_term": "ระยะยาว",
        "breadth": "แหล่งที่ยืนยัน",
        "short_term_def": "ปีที่ @SR@: ยอดค้นหาที่คาดว่าจะเปลี่ยนไปเทียบกับ 12 เดือนล่าสุด เทรนด์เรียงตามปีที่ @S@",
        "long_term_def": "ปีที่ @LR@ วัดแบบเดียวกัน รายการระยะยาวเรียงตามปีที่ 5 ซึ่งไม่แน่นอนกว่าระยะสั้นมาก",
        "breadth_def": "พบคีย์เวิร์ดของเทรนด์นี้ในกี่แหล่งจาก 3 แหล่งอิสระ (งานวิจัย · บทสนทนาของผู้บริโภค · ข่าวอุตสาหกรรม)",
        "chart_caption": "การเติบโตของยอดค้นหาที่คาด",
        "chart_caption_end": " (เทียบ 12 เดือนล่าสุด)",
        "chart_alt": "กราฟพยากรณ์",
        "legend_cagr": "เติบโตเฉลี่ยต่อปี",
        "legend_yoy": "เปลี่ยนเทียบปีก่อนหน้า",
        "legend_hist": "ข้อมูลจริง",
        "legend_avg": "เฉลี่ย 12 เดือน",
        "kpi_short": "ระยะสั้น · ปีที่ @S@",
        "kpi_long": "ระยะยาว · ปีที่ 5",
        "kpi_vs_last12": "เทียบ 12 เดือนล่าสุด",
        "kpi_cagr_sub": "เฉลี่ยต่อปี เทียบ 12 เดือนล่าสุด",
        "cagr_fact": "ตัวเลขสีน้ำเงิน = อัตราการเติบโตเฉลี่ยต่อปี (ทบต้น) เทียบ 12 เดือนล่าสุด ตัวเลขสีเทา = เปลี่ยนเทียบปีก่อนหน้า "
                     "(ปีที่ 1 เท่ากันทั้งสองค่า)",
        "kpi_sources": "แหล่งที่ยืนยัน",
        "of_3": "จาก 3",
        "target_consumer": "กลุ่มเป้าหมาย",
        "tracked_keywords": "คีย์เวิร์ดค้นหาที่ติดตาม",
        "months_with_data": "มีข้อมูลการค้นหา {pct}% ของเดือน",
        "rank_score": "ปีที่ @S@: คาดว่ายอดค้นหาเพิ่มมากกว่า {v}% ของคีย์เวิร์ดในตลาด",
        "overlooked": "โอกาสที่ถูกมองข้าม {n}",
        "workshop_question": "คำถามเวิร์กช็อป",
        "evidence_sub": "หลักฐานในตลาด - ตัวอย่างสินค้าบน Konvy ที่ตรงกับเทรนด์นี้ที่สุด",
        "no_products": "รอบนี้ไม่มีผลจับคู่สินค้าสำหรับเทรนด์นี้",
        "np_sub": "หลักฐานในตลาด",
        "np_title": "ไม่พบสินค้าในตลาด",
        "np_channel": "เทรนด์นี้พูดถึงช่องทางการขายหรือพฤติกรรมการซื้อ ไม่ได้บอกคุณสมบัติของสินค้า จึงไม่พบสินค้าบน Konvy ที่ตรงกับเทรนด์นี้ "
                      "คำอธิบายเทรนด์อยู่ในหน้าก่อนหน้า",
        "np_no_data": "ข้อมูลของเทรนด์นี้ไม่พอจะระบุคุณสมบัติสินค้า จึงไม่พบสินค้าบน Konvy ที่ตรงกับเทรนด์นี้ "
                      "คำอธิบายเทรนด์อยู่ในหน้าก่อนหน้า",
        "evidence_note": "เรียงสินค้าตามว่าคำอธิบายสินค้าตรงกับเทรนด์แค่ไหน{stats} เป็นสินค้าที่ตรงที่สุดที่มีอยู่ตอนนี้ "
                         "ไม่ใช่สินค้าที่ยืนยันแล้วว่าตอบเทรนด์",
        "evidence_stats": " (เทรนด์นี้: สูงสุด {best} เฉลี่ย {mean} จากสินค้า {n} รายการ)",
        "cat_sub": "หลักฐานในตลาด - ตัวอย่างสินค้าบน Konvy ที่ตรงกับเทรนด์นี้ที่สุด แยกตามหมวดสินค้า",
        "cat_dist": "สินค้า {n} ชิ้นแรกที่ตรงกับเทรนด์นี้ที่สุดอยู่หมวดไหนบ้าง",
        "cat_dist_of": "({pct}% แรกจากสินค้า {total} ชิ้น)",
        "cat_sub_main": "ตัวอย่างสินค้าบน Konvy ที่ตรงกับเทรนด์นี้ที่สุด ในหมวดหลักของเทรนด์: {category}",
        "cat_dist_main": "สินค้า {n} ชิ้นแรกที่ตรงกับเทรนด์นี้ที่สุดในหมวด {category} เป็นสินค้าชนิดไหนบ้าง",
        "cat_dist_main_of": "(หมวดนี้มีสินค้าทั้งหมด {total} ชิ้น)",
        "cat_other": "หมวดอื่น",
        "cat_count": "ตรงเทรนด์ {n} ชิ้น จากสินค้า {total} ชิ้นในกลุ่มนี้",
        "cat_price": "ราคากลาง {median} · ช่วง {lo}-{hi}",
        "cat_rank": "ตรงเทรนด์อันดับ {n} จากทั้งร้าน",
        "cat_all_types": "ทุกชนิดสินค้า",
        "unit_ml": "มล.", "unit_g": "ก.", "unit_ml_g": "มล./ก.", "unit_pcs": "ชิ้น", "mini": "ขนาดทดลอง",
        "cat_by_price": "แยกตามราคา: {parts}",
        "tier_low": "ราคาต่ำ", "tier_mid": "ราคากลาง", "tier_high": "ราคาสูง", "tier_all": "ทุกช่วงราคา",
        "tier_low_s": "ต่ำ", "tier_mid_s": "กลาง", "tier_high_s": "สูง", "tier_all_s": "ทั้งหมด",
        "cat_note_tiers": "หมวด = หมวดสินค้ามาตรฐาน (Euromonitor Level 2 เฉพาะความงามและของใช้ส่วนตัว) "
                          "เรียงตามจำนวนสินค้าที่ตรงเทรนด์ที่สุด (ไม่ถึง 3 ชิ้นไม่แสดง ถ้าเหลือไม่ถึง 4 หมวด "
                          "หมวดใหญ่สุดแตกตามชนิดสินค้า) ช่วงราคา = แบ่งสินค้าทั้งร้านของหมวดหรือชนิดนั้นเป็น 3 "
                          "กลุ่มเท่ากันตามราคา ทุกเทรนด์ใช้ช่วงเดียวกัน แต่ละแถว = ชิ้นที่ตรงเทรนด์ที่สุดในช่วงนั้น แถบ = "
                          "ความตรงเทียบชิ้นที่ตรงที่สุดในหน้านี้ อันดับ = ลำดับเมื่อเทียบสินค้าทั้งร้าน {n} ชิ้น ตรงเทรนด์ "
                          "= คำอธิบายสินค้าใกล้กับเทรนด์ ยังไม่ได้ยืนยันว่าตอบเทรนด์จริง",
        "cat_note_main": "หมวดหลัก ({category}) ให้ AI เลือกจากความหมายของเทรนด์ "
                         "โดยใช้หมวดของสินค้าที่ตรงเทรนด์ที่สุดเป็นหลักฐาน คอลัมน์ = "
                         "ชนิดสินค้าของหมวดนั้นที่มีสินค้าตรงเทรนด์มากที่สุด (อย่างน้อยชนิดละ 3 ชิ้น) ช่วงราคา = 3 "
                         "กลุ่มเท่ากันตามราคาสินค้าทั้งร้านของชนิดนั้น ทุกเทรนด์ใช้ช่วงเดียวกัน แต่ละแถว = "
                         "ชิ้นที่ตรงเทรนด์ที่สุดในช่วงนั้น แถบ = ความตรงเทียบชิ้นที่ตรงที่สุดในหน้านี้ อันดับ = "
                         "ลำดับในสินค้าทั้งร้าน {n} ชิ้น ตรงเทรนด์ = คำอธิบายสินค้าใกล้กับเทรนด์ "
                         "ยังไม่ได้ยืนยันว่าตอบเทรนด์จริง",
        "cat_other_main": "ชนิดสินค้าอื่น",
        "cat_note": "หมวด = หมวดสินค้ามาตรฐาน (Euromonitor Level 2 เฉพาะความงามและของใช้ส่วนตัว) "
                    "เรียงตามจำนวนสินค้าที่ตรงเทรนด์ที่สุดในหมวดนั้น หมวดที่มีไม่ถึง 3 ชิ้นไม่แสดง และถ้าเหลือไม่ถึง "
                    "4 หมวด หมวดที่ใหญ่ที่สุดจะแตกตามชนิดสินค้า แถบ = คำอธิบายสินค้าตรงกับเทรนด์แค่ไหน "
                    "เทียบกับชิ้นที่ตรงที่สุดในหน้านี้ อันดับ = ลำดับความตรงเมื่อเทียบสินค้าทั้งร้าน {n} ชิ้น "
                    "เป็นสินค้าที่ตรงที่สุดที่มีอยู่ ไม่ใช่สินค้าที่ยืนยันแล้วว่าตอบเทรนด์",
        "method_header": "ภาคผนวก | วิธีการ",
        "method_1_title": "1. การเก็บหลักฐาน",
        "method_1": "รวบรวมบทความจากแหล่งอิสระ 3 ประเภท ได้แก่ งานวิจัย บทสนทนาของผู้บริโภค และข่าวอุตสาหกรรม โมเดล "
                    "AI สกัดข้อความรูปแบบ ประธาน-ความสัมพันธ์-กรรม จากแต่ละเอกสาร "
                    "และเก็บไว้เฉพาะข้อความที่พบประโยคหลักฐานตรงตัวในเอกสารต้นทาง "
                    "จากนั้นจัดกลุ่มเป็นเทรนด์ตั้งต้นด้วยการจัดกลุ่มกราฟ (Louvain โหวต 20 รอบ){total}",
        "method_1_total": " - รอบนี้ได้ {n} เทรนด์ตั้งต้น",
        "method_2_title": "2. การพยากรณ์ความสนใจการค้นหา",
        "method_2": "ติดตามคีย์เวิร์ดค้นหาของแต่ละเทรนด์ใน Google Trends ทั่วโลกรายเดือน (ไม่ระบุหมวด) การเติบโตที่คาดในปีที่ 1 ถึง 5 = ค่าเฉลี่ยการค้นหาที่คาดในปีนั้น ÷ ค่าเฉลี่ย 12 เดือนล่าสุด จากโมเดล random forest ที่ฝึกจากการเติบโตในอดีตของทุกคีย์เวิร์ด (ข้อมูลเข้าได้แก่ การโตปีที่แล้ว การโตเทียบเดือนเดียวกันของปีก่อน แรงส่งช่วงสั้น ระยะห่างจากจุดสูงสุด และความผันผวน) และคะแนนของเทรนด์ = percentile ของการเติบโตที่คาด (ค่าเฉลี่ยของคีย์เวิร์ดในเทรนด์) เทียบคีย์เวิร์ดทั้งหมดในรอบ ทดสอบย้อนหลังปี 2016-2022 กับข้อมูล 2 ชุด อันดับสอดคล้องกับการโตจริงที่ Spearman ประมาณ 0.52 (ปีที่ 1) 0.45 (ปีที่ 3) และ 0.40 (ปีที่ 5) ระดับที่คาดของเทรนด์คลาดจากของจริงเป็นค่ากลาง 6% (ปีที่ 1) 12% (ปีที่ 3) และ 20% (ปีที่ 5) และแถบในกราฟครอบคลุมผลจริง 80% เส้นประรายเดือนกระจายระดับรายปีตามจังหวะฤดูกาลของเทรนด์จาก 4 ปีก่อน ส.ค. 2025 ตอนนี้ยังไม่ใช้การโตปีที่แล้วจัดอันดับโดยตรง เพราะข้อมูล Google Trends แบบไม่ระบุหมวดกระโดดขึ้นทุกคีย์เวิร์ดตั้งแต่ ส.ค. 2025 ทำให้ตัวเลขนี้สูงเกินจริง",
        "method_3_title": "3. การจัดอันดับและคัดเลือก",
        "method_3": "จัดอันดับเทรนด์ด้วยการเติบโตของการค้นหาที่คาดในปีที่ @S@ ซึ่งเป็นระยะสั้น (0.5 = ค่ากลางตลาด) "
                    "หน้ารายละเอียดทำเฉพาะเทรนด์เหนือค่ากลางตลาด (รายงานนี้มี {n} เทรนด์){np_note} "
                    "ส่วนเทรนด์ที่ต่ำกว่าค่ากลางแสดงเฉพาะในตารางและกราฟภาพรวม "
                    "โอกาสอยู่ยาว (Longevity Score) คำนวณด้วยกฎตายตัวจากผลตัดสินหลักฐาน "
                    "ตัวเลขทุกตัวไม่ได้มาจาก AI ตัวเลขในหน้าภาพรวมตลาดเป็นค่าตรงกลางของทุกเทรนด์ (ครึ่งหนึ่งสูงกว่า "
                    "อีกครึ่งต่ำกว่า)",
        "method_3_np": " ในจำนวนนี้ {k} เทรนด์เป็นเทรนด์ช่องทางการขายหรือพฤติกรรมการซื้อที่ไม่มีคุณสมบัติสินค้า "
                       "หน้าที่ 2 ของเทรนด์เหล่านี้จึงอธิบายว่าไม่พบสินค้าที่ตรงกับเทรนด์",
        "method_3_np_none": "",
        "method_4_title": "4. การจับคู่สินค้า",
        "method_4": "แปลงโปรไฟล์ของแต่ละเทรนด์ (ประโยชน์ งานที่ผู้บริโภคต้องการให้สำเร็จ จุดต่าง) "
                    "เป็นตัวเลขที่แทนความหมาย (text embedding) แล้วเทียบกับคำอธิบายของสินค้า Konvy {n} ชิ้น "
                    "ยิ่งความหมายใกล้กัน ยิ่งตรงกับเทรนด์ แสดงสินค้าที่ตรงที่สุดพร้อมเหตุผลสั้นๆ ที่ AI เขียน",
        "method_4_cat": "แปลงโปรไฟล์ของแต่ละเทรนด์ (ประโยชน์ งานที่ผู้บริโภคต้องการให้สำเร็จ จุดต่าง) "
                        "เป็นตัวเลขที่แทนความหมาย (text embedding) แล้วเทียบกับคำอธิบายของสินค้า Konvy {n} ชิ้น "
                        "ยิ่งความหมายใกล้กัน ยิ่งตรงกับเทรนด์ สินค้า 1% แรกที่ตรงที่สุดบอกว่าเทรนด์แตะหมวดไหนบ้าง แสดง 4 "
                        "หมวดที่มีสินค้ากลุ่มนี้มากที่สุด (หมวด Euromonitor Level 2 อย่างน้อยหมวดละ 3 ชิ้น) หมวดละ 3 "
                        "ชิ้นที่ตรงที่สุด ถ้ามีไม่ถึง 4 หมวด หมวดที่ใหญ่ที่สุดจะแตกตามชนิดสินค้า",
        "method_4_main": "แปลงโปรไฟล์ของแต่ละเทรนด์ (ประโยชน์ งานที่ผู้บริโภคต้องการให้สำเร็จ จุดต่าง) "
                         "เป็นตัวเลขที่แทนความหมาย (text embedding) แล้วเทียบกับคำอธิบายของสินค้า Konvy {n} ชิ้น "
                         "ยิ่งความหมายใกล้กัน ยิ่งตรงกับเทรนด์ จากนั้นให้ AI เลือกหมวดหลักหมวดเดียว (Euromonitor Level 2) "
                         "ที่เทรนด์นี้อยู่ จากความหมายของเทรนด์และหมวดของสินค้าที่ตรงที่สุด ไม่นับหมวดควบคู่ "
                         "แล้วแสดงชนิดสินค้าของหมวดนั้นที่มีสินค้าตรงเทรนด์มากที่สุด แยกเป็นช่วงราคาต่ำ/กลาง/สูง "
                         "(แบ่งราคาสินค้าทั้งร้านของชนิดสินค้านั้นเป็น 3 กลุ่มเท่ากัน) "
                         "พร้อมชิ้นที่ตรงเทรนด์ที่สุดในแต่ละช่วง",
        "method_4_tiers": "แปลงโปรไฟล์ของแต่ละเทรนด์ (ประโยชน์ งานที่ผู้บริโภคต้องการให้สำเร็จ จุดต่าง) "
                          "เป็นตัวเลขที่แทนความหมาย (text embedding) แล้วเทียบกับคำอธิบายของสินค้า Konvy {n} ชิ้น "
                          "ยิ่งความหมายใกล้กัน ยิ่งตรงกับเทรนด์ สินค้า 1% แรกที่ตรงที่สุดบอกว่าเทรนด์แตะหมวดไหนบ้าง แสดง 4 "
                          "หมวดที่มีสินค้ากลุ่มนี้มากที่สุด (หมวด Euromonitor Level 2 อย่างน้อยหมวดละ 3 ชิ้น ถ้าไม่ถึง 4 "
                          "หมวด หมวดใหญ่สุดแตกตามชนิดสินค้า) แยกเป็นช่วงราคาต่ำ/กลาง/สูง "
                          "(แบ่งราคาสินค้าทั้งร้านของหมวดนั้นเป็น 3 กลุ่มเท่ากัน) พร้อมชิ้นที่ตรงเทรนด์ที่สุดในแต่ละช่วง",
        # 🆕 (2026-10-21) หน้าสินค้าของเทรนด์ = แผนที่ "ความใกล้เทรนด์ x ยอดขาย" ระดับหมวด L2 (l2_map.py)
        "l2_sub": "หลักฐานจากตลาด - สินค้า {category} {n} ชิ้นบน Konvy ตรงกับเทรนด์แค่ไหน และขายได้แค่ไหน",
        "l2_corner_y": "ยอดขายบน Konvy ↓", "l2_corner_x": "ความตรงกับเทรนด์ →",
        "l2_lv_excellent": "Excellent", "l2_lv_good": "Good", "l2_lv_average": "Average", "l2_lv_below_average": "Below average",
        "l2_x_first": "{p}% แรกของหมวด", "l2_x_mid": "{a}-{b}% แรกของหมวด", "l2_x_last": "ไม่ถึง {p}% แรก",
        "l2_y_strong": "ขายดี", "l2_y_strong_sub": "{p}% แรก", "l2_y_steady": "ขายปานกลาง", "l2_y_steady_sub": "ช่วงกลาง",
        "l2_y_slow": "ขายได้น้อย", "l2_y_slow_sub": "{p}% ล่างสุด",
        "l2_empty": "ไม่มีสินค้า",
        "l2_card_match": "ตรงเทรนด์อันดับ {rank}",
        "l2_sales_top": "ยอดขาย {p}% แรก", "l2_sold": "ขายแล้ว {n} ชิ้น", "l2_soldout": "ของหมด", "l2_reviews": "{n} รีวิว",
        "l2_review1": "1 รีวิว", "l2_zero": "ขายได้ 0 ชิ้นทั้งที่มีของ",
        "l2_take": "ในสินค้าที่ตรงเทรนด์ที่สุด ({p}% แรกของหมวด) ขายดี {s}% และขายได้น้อย {l}% ส่วนสินค้า {category} ทั้งหมวด "
                   "เป็น {sa}% และ {la}%",
        "l2_note": "สินค้า {category} (หมวดหลักของเทรนด์) แต่ละชิ้นถูกวางตามความใกล้เทรนด์ของคำอธิบายสินค้า (คอลัมน์ = ตำแหน่งในสินค้า "
                   "ทั้ง {total} ชิ้นของหมวด) และตามยอดขายบน Konvy เทียบกับสินค้า {category} ชิ้นอื่น (แถว; จำนวนที่ขาย x ราคา "
                   "ของหมดใช้จำนวนรีวิว) · สินค้าที่แสดง = ชิ้นที่ใกล้เทรนด์ที่สุดในช่องนั้น สินค้าที่ไม่มีข้อมูลยอดขายไม่ถูกแสดง · "
                   "สีพื้น = เกรดหลังยอดขายดึงขึ้นหรือลง 1 ขั้น (ขายดีดึง Average ขึ้นเป็น Good · Excellent ต้องตรงเทรนด์ {p1}% แรก "
                   "และขายดี ตรงเทรนด์มากที่สุดแต่ขายปานกลางได้ Good · ขายได้น้อยลง 1 ขั้น)",
        "method_4_l2": "แปลงโปรไฟล์ของแต่ละเทรนด์ (ประโยชน์ งานที่ผู้บริโภคต้องการให้สำเร็จ จุดต่าง) "
                       "เป็นตัวเลขที่แทนความหมาย (text embedding) แล้วเทียบกับคำอธิบายของสินค้า Konvy {n} ชิ้น "
                       "ยิ่งความหมายใกล้กัน ยิ่งตรงกับเทรนด์ จากนั้นให้ AI เลือกหมวดหลักหมวดเดียว (Euromonitor Level 2) "
                       "ที่เทรนด์นี้อยู่ จากความหมายของเทรนด์และหมวดของสินค้าที่ตรงที่สุด ไม่นับหมวดควบคู่ "
                       "สินค้าทุกชิ้นของหมวดนั้นถูกวางตามความใกล้เทรนด์ ({p1}% แรก, {p1}-{p2}%, {p2}-{p3}% ของหมวด แล้วที่เหลือ) "
                       "และตามยอดขายบน Konvy เทียบกับสินค้าอื่นในหมวด ({s1}% แรก = ขายดี, {s2}% ล่างสุด หรือขายได้ 0 ชิ้น"
                       "ทั้งที่มีของ = ขายได้น้อย สินค้าที่ของหมดใช้จำนวนรีวิวแทน) แล้วแสดงชิ้นที่ตรงเทรนด์ที่สุดในแต่ละช่อง "
                       "ยอดขายเป็นยอดสะสมของ Konvy (จำนวนที่ขาย x ราคาปัจจุบัน) เป็นค่าประมาณ ไม่ใช่ยอดขายของบริษัท",
        "notes_header": "ภาคผนวก | หมายเหตุและข้อมูล",
        "run_details": "รายละเอียดรอบรัน",
        "topic": "หัวข้อ",
        "run_id": "รหัสรอบ",
        "data_collected": "วันที่เก็บข้อมูล",
        "report_generated": "วันที่สร้างรายงาน",
        "forecast_window": "ช่วงพยากรณ์",
        "language_models": "โมเดล AI",
        "report_copy": "ข้อความภาษาไทย",
        "how_to_use": "วิธีใช้รายงานนี้",
        "how_to_use_text": "รายงานนี้เป็นเครื่องมือช่วยตัดสินใจ ไม่ใช่คำตอบสุดท้าย ขั้นตอนที่ใช้ AI (สร้างคำค้น, "
                           "ตั้งชื่อเทรนด์, โปรไฟล์เทรนด์ และข้อความภาษาไทยในรายงานนี้) ให้ผลต่างกันได้ในแต่ละรอบ "
                           "การจับคู่สินค้ายังไม่เคยวัดความแม่นยำเทียบกับตัวอย่างที่คนตรวจ "
                           "สินค้าที่จับคู่ได้จึงบอกว่าชั้นวางสินค้าใกล้เคียงเทรนด์ตรงไหน "
                           "ไม่ใช่หลักฐานว่าสินค้านั้นตอบเทรนด์ได้จริง",
        "data_not_available": "ข้อมูลที่ไม่มีในรอบนี้",
        "data_sources": "แหล่งที่มาของข้อมูล",
        "data_src_papers": "งานวิจัย",
        "data_src_discussions": "ช่องทางออนไลน์",
        "data_src_news": "ข่าว",
        "data_src_search": "ความสนใจค้นหา",
        "data_src_products": "สินค้า",
        "data_src_categories": "หมวดสินค้า",
        "data_src_used": "ใช้ {n} ชิ้น",
        "data_src_searched": "ค้นจาก {names}",
        "data_src_posts": "ใช้ {n} {posts}",
        "data_src_post_one": "โพสต์/คลิป",
        "data_src_post_many": "โพสต์/คลิป",
        "data_src_news_intl": "ข่าวต่างประเทศ ใช้ {n} {articles}",
        "data_src_news_th": "ข่าวไทย ใช้ {n} {articles}",
        "data_src_article_one": "ชิ้น",
        "data_src_article_many": "ชิ้น",
        "data_src_search_text": "Google Trends ทั่วโลก รายเดือน - {n} คีย์เวิร์ด",
        "data_src_search_asof": "ข้อมูลถึง {month}",
        "data_src_products_text": "Konvy - สินค้าความงามและของใช้ส่วนตัว {n} ชิ้น",
        "data_src_collected": "เก็บข้อมูล {dates}",
        "data_src_categories_text": "การจัดหมวดของ Euromonitor ระดับ 1-4",
        "data_docs_header": "ภาคผนวก | รายการแหล่งข้อมูล",
        "data_doc_search": "ค้นหา: {q}",
        "mo_faster": "เทรนด์ที่สูงกว่าระดับตลาด (ปีที่ @S@)",
        "mo_faster_val": "{n} จาก {total}",
        "mo_faster_sub": "ยอดค้นหาที่คาดว่าจะเปลี่ยนในปีที่ @S@",
        "kpi_past": "12 เดือนที่ผ่านมา (ข้อมูลจริง)",
        "vs_prev12": "เทียบ 12 เดือนก่อนหน้า",
        "kpi_recent": "6 เดือนล่าสุด {v} เทียบปีก่อน",
        "kpi_longevity": "โอกาสอยู่ยาว {v}/100",
        "no_history": "รอบนี้ไม่มีค่าพยากรณ์ของเทรนด์นี้",
        "durability": "โอกาสอยู่ยาว",
        "durability_def": "คะแนน 0-100 บอกว่าเทรนด์มีโอกาสอยู่ได้นาน ไม่ใช่แค่กระแสชั่วคราว มากน้อยแค่ไหน ให้คะแนนด้วยกฎตายตัวจากหลักฐาน ดีเยี่ยม 70 ขึ้นไป, ดี 55-69, ปานกลาง 40-54, ต่ำกว่าเกณฑ์ ต่ำกว่า 40",
        "legend_fc": "คาดการณ์รายเดือน",
        "legend_band": "ช่วง 80% ของค่าเฉลี่ยปี",
        "mo_short": "การค้นหาปีที่ @S@ เทียบ 12 เดือนล่าสุด",
        "mo_short_sub": "ค่าตรงกลางของ {n} เทรนด์: ครึ่งหนึ่งสูงกว่านี้ อีกครึ่งต่ำกว่า",
        "mo_long": "การค้นหาปีที่ 5 เทียบ 12 เดือนล่าสุด",
        "mo_long_sub": "รวม 5 ปี ไม่ใช่ต่อปี · ค่าตรงกลางของ {n} เทรนด์",
        "mo_dur": "โอกาสอยู่ยาว (0-100)",
        "mo_dur_sub": "ค่าตรงกลางของ {n} เทรนด์ · คะแนนจากหลักฐาน",
        "past_mark": "*",
        "past_note": "* ข้อมูล Google Trends ของทุกคีย์เวิร์ดกระโดดขึ้นพร้อมกันตั้งแต่ ส.ค. 2025 (แต่ละคำมากน้อยไม่เท่ากัน) "
                     "ตัวเลข 12 เดือนและ 6 เดือนล่าสุดจึงสูงเกินจริง และไม่ควรใช้เทียบระหว่างเทรนด์ ให้ดูตัวเลขที่คาดแทน",
        "ov_short": "ระยะสั้น",
        "ov_long": "ระยะยาว",
        "ov_short_def": "ระยะสั้น = ปีที่ @SR@",
        "ov_long_def": "ระยะยาว = ปีที่ @LR@",
        "u_upto": "ไม่เกิน {v}",
        "u_from": "ตั้งแต่ {v}",
    },
}
STRINGS = apply_tokens(STRINGS)

# ค่าชุดคำตายตัวจาก ⑦ (ดู trend_final_v2_subset.py: status ใน forecast_trend, compute_investment_signal และ enum ในพรอมต์
# cluster_analysis/market_overview) - ค่าที่ไม่อยู่ในตารางคงเป็นภาษาอังกฤษตามเดิม
ENUM_TH = {
    "Major Breakout": "ทะยานแรง", "Rising": "กำลังขึ้น", "Stable": "ทรงตัว", "Fading": "กำลังลดลง",
    "Invest Now": "ลงทุนได้ทันที", "Monitor": "เฝ้าติดตาม", "Wait": "รอดูก่อน",
    "High": "สูง", "Medium": "ปานกลาง", "Low": "ต่ำ",
    "Emerging": "เริ่มก่อตัว", "Growing": "กำลังเติบโต", "Peaking": "ใกล้จุดสูงสุด", "Declining": "ขาลง",
    "Organic Seasonality": "ตามฤดูกาล", "External Shock": "ปัจจัยภายนอกกระทบ",
    "Structural Growth": "เติบโตเชิงโครงสร้าง", "Mixed/Uncertain": "ผสม/ไม่ชัดเจน",
    "Short-term": "ระยะสั้น", "Medium-term": "ระยะกลาง", "Long-term": "ระยะยาว",
    "Weak": "อ่อน", "Moderate": "ปานกลาง", "Strong": "แข็งแรง",
    "Strengthening": "แข็งแกร่งขึ้น", "Weakening": "อ่อนตัวลง",
    # Longevity band (bootstrap.LONGEVITY_BANDS - report_data เปลี่ยน "_" เป็นช่องว่างแล้ว)
    "durable": "อยู่ยาว", "likely durable": "น่าจะอยู่ยาว", "leaning durable": "ค่อนไปทางอยู่ยาว",
    "undetermined": "ยังสรุปไม่ได้", "leaning fad": "ค่อนไปทางกระแสชั่วคราว", "likely fad": "น่าจะเป็นกระแสชั่วคราว",
}
DIMENSION_TH = {
    "SOCIETY": "สังคม", "TECHNOLOGY": "เทคโนโลยี", "ENVIRONMENT": "สิ่งแวดล้อม", "POLICY": "นโยบาย",
    "INDUSTRY": "อุตสาหกรรม", "CREATIVITY": "ความคิดสร้างสรรค์",
}
# ป้ายของไฟล์ที่ขาด (report_data.build_context's need()) -> ภาษาไทย
MISSING_TH = {
    "Rank Score": "คะแนนจัดอันดับ (Rank Score)", "Google Trends forecast": "ผลพยากรณ์ Google Trends",
    "Category aggregation": "สรุประดับหมวด", "Product matching": "ผลจับคู่สินค้า",
    "STEPIC synthesis": "บทสังเคราะห์ STEPIC", "STEPIC analysis": "บทวิเคราะห์ STEPIC",
    "Monthly forecast series": "ค่าพยากรณ์รายเดือน", "Growth score": "คะแนนการเติบโต",
}
MONTH_TH = {"Jan": "ม.ค.", "Feb": "ก.พ.", "Mar": "มี.ค.", "Apr": "เม.ย.", "May": "พ.ค.", "Jun": "มิ.ย.",
            "Jul": "ก.ค.", "Aug": "ส.ค.", "Sep": "ก.ย.", "Oct": "ต.ค.", "Nov": "พ.ย.", "Dec": "ธ.ค."}


def enum(value, lang):
    return ENUM_TH.get(value, value) if lang == "th" and isinstance(value, str) else value


def month_year(text, lang):
    """"Aug 2029" -> "ส.ค. 2029" (ปี ค.ศ. คงเดิม) - รูปแบบอื่นคืนค่าเดิม"""
    if lang != "th" or not isinstance(text, str):
        return text
    return re.sub(r"\b(" + "|".join(MONTH_TH) + r")\b", lambda m: MONTH_TH[m.group(1)], text)


def date_long(d, lang, with_time=False):
    """datetime -> "16 Sep 2026" / "16 ก.ย. 2026" (+ เวลา)"""
    text = d.strftime("%d %b %Y %H:%M" if with_time else "%d %b %Y")
    return month_year(text, lang)


def date_range(first, last, lang):
    """ช่วงวันที่ (date หรือข้อความ ISO "2026-10-06") -> "6 - 9 Oct 2026" / "28 Sep - 9 Oct 2026" / วันเดียว "6 Oct 2026"
    อ่านค่าไม่ได้ -> "" (ผู้เรียกข้ามส่วนนี้)"""
    try:
        a = date.fromisoformat(str(first)[:10])
        b = date.fromisoformat(str(last or first)[:10])
    except ValueError:
        return ""
    if b < a:
        a, b = b, a
    if a == b:
        text = f"{a.day} {a.strftime('%b %Y')}"
    elif (a.year, a.month) == (b.year, b.month):
        text = f"{a.day} - {b.day} {b.strftime('%b %Y')}"
    elif a.year == b.year:
        text = f"{a.day} {a.strftime('%b')} - {b.day} {b.strftime('%b %Y')}"
    else:
        text = f"{a.day} {a.strftime('%b %Y')} - {b.day} {b.strftime('%b %Y')}"
    return month_year(text, lang)


def source_rows(meta, lang):
    """meta["sources"] (report_data._data_sources) -> [(ชื่อแหล่ง, รายละเอียด)] ของภาษานั้น สำหรับกล่อง "แหล่งที่มาของข้อมูล"
    แหล่งที่รอบนี้ไม่มีข้อมูล (ไม่มีไฟล์/จำนวนเป็น 0) ไม่มีแถว (เจ้าของงานเลือก 2026-10-14) - meta["data_as_of"] ต้อง localize แล้ว"""
    s = STRINGS[lang]
    src = (meta or {}).get("sources") or {}
    rows = []

    p = src.get("papers") or {}
    if p.get("n_used"):
        parts = [s["data_src_used"].format(n=f"{p['n_used']:,}")]
        if p.get("databases"):
            parts.append(s["data_src_searched"].format(names=", ".join(p["databases"])))
        rows.append((s["data_src_papers"], " - ".join(parts)))

    d = src.get("discussions") or {}
    if d.get("platforms"):
        total = sum(x["n"] for x in d["platforms"])
        names = ", ".join(f"{x['name']} {x['n']:,}" for x in d["platforms"])
        noun = s["data_src_post_one" if total == 1 else "data_src_post_many"]
        rows.append((s["data_src_discussions"], f"{s['data_src_posts'].format(n=f'{total:,}', posts=noun)} - {names}"))

    n = src.get("news") or {}
    parts = []
    for key, label in (("intl", "data_src_news_intl"), ("th", "data_src_news_th")):
        part = n.get(key) or {}
        if part.get("n_used"):
            noun = s["data_src_article_one" if part["n_used"] == 1 else "data_src_article_many"]
            parts.append(s[label].format(n=f"{part['n_used']:,}", articles=noun))
    if parts:
        rows.append((s["data_src_news"], " - ".join(parts)))

    q = src.get("search") or {}
    if q.get("n_keywords"):
        parts = [s["data_src_search_text"].format(n=f"{q['n_keywords']:,}")]
        if (meta or {}).get("data_as_of"):
            parts.append(s["data_src_search_asof"].format(month=meta["data_as_of"]))
        rows.append((s["data_src_search"], " - ".join(parts)))

    g = src.get("products") or {}
    if g.get("n"):
        parts = [s["data_src_products_text"].format(n=f"{g['n']:,}")]
        dates = date_range(g.get("collected_from"), g.get("collected_to"), lang) if g.get("collected_from") else ""
        if dates:
            parts.append(s["data_src_collected"].format(dates=dates))
        rows.append((s["data_src_products"], " - ".join(parts)))

    if src.get("categories"):
        rows.append((s["data_src_categories"], s["data_src_categories_text"]))
    return rows


def source_doc_groups(meta, lang):
    """meta["source_docs"] (report_data._source_documents) -> [{"label", "docs": [{"name", "platform", "url"}]}] ของภาษานั้น
    กลุ่มที่ไม่มีเอกสารไม่มี - ใช้ชื่อกลุ่มเดียวกับกล่องแหล่งที่มา; Pantip แสดงเป็น "ค้นหา: <คำค้น>" เพราะเอกสารคือหน้าผลค้นหา"""
    s = STRINGS[lang]
    docs = (meta or {}).get("source_docs") or {}
    groups = []
    for key, label in (("papers", "data_src_papers"), ("discussions", "data_src_discussions"), ("news", "data_src_news")):
        # shown = URL ที่อ่านออก (ถอดรหัส %xx ของคำค้นไทย) - href ใช้ url เดิม
        items = [{"name": s["data_doc_search"].format(q=d["title"]) if d.get("search") else d["title"],
                  "platform": d.get("platform"), "url": d.get("url"), "shown": unquote(d["url"]) if d.get("url") else None}
                 for d in docs.get(key) or [] if d.get("title")]
        if items:
            groups.append({"label": s[label], "docs": items})
    return groups


def dimensions(text, lang):
    """"SOCIETY + INDUSTRY" -> "สังคม + อุตสาหกรรม" """
    if lang != "th" or not isinstance(text, str):
        return text
    return re.sub(r"[A-Z]+", lambda m: DIMENSION_TH.get(m.group(0), m.group(0)), text)


def _pick(translated, original):
    """ใช้คำแปลถ้ามี ไม่มี (แปลไม่สำเร็จ) ใช้ต้นฉบับภาษาอังกฤษ"""
    return translated if isinstance(translated, str) and translated.strip() else original


def localize(ctx, lang):
    """context กลาง -> context ของภาษาที่เลือก (สำเนาใหม่ ไม่แก้ของเดิม) ให้เทมเพลตอ่านช่องชื่อเดิมได้ทั้ง 2 ภาษา

    en: ใช้ตามเดิม (ข้อความจาก t["text"])
    th: t["text"] <- t["text_th"], ข้อความรายงานระดับหน้า <- ctx["th"] (จาก enrich.translate_report_texts),
        ชุดคำตายตัวแปลงด้วย ENUM_TH, ชื่อสินค้าใช้ชื่อเต็มที่มีภาษาไทย, เดือนเป็นภาษาไทย"""
    if lang == "en":
        return ctx
    out = copy.deepcopy(ctx)
    th = ctx.get("th") or {}
    meta = out["meta"]
    meta["forecast_start"] = month_year(meta.get("forecast_start"), lang)
    meta["forecast_end"] = month_year(meta.get("forecast_end"), lang)
    meta["data_as_of"] = month_year(meta.get("data_as_of"), lang)
    if out.get("growth"):
        out["growth"]["periods"] = {k: month_year(v, lang) for k, v in out["growth"]["periods"].items()}

    ov = out["overview"]
    for k in ("current_trend_strength", "overall_direction", "estimated_trend_duration"):
        if k in ov["market"]:
            ov["market"][k] = enum(ov["market"][k], lang)
    ov["market"]["summary"] = _pick((th.get("market") or {}).get("summary"), ov["market"].get("summary"))

    tk_th = th.get("takeaway") or {}
    for k in out["takeaway"]:
        out["takeaway"][k] = _pick(tk_th.get(k), out["takeaway"][k])

    stepic_th = (th.get("stepic") or {}).get("items") or []
    for i, s in enumerate(out["stepic"]):
        s_th = stepic_th[i] if i < len(stepic_th) else {}
        s["headline"] = _pick(s_th.get("headline"), s["headline"])
        s["body"] = _pick(s_th.get("body"), s["body"])
        s["dimension_label"] = DIMENSION_TH.get(s["dimension"].upper(), s["dimension"])
    for key, fields in (("personas", ("name", "description", "value_driver", "channel_preference")),
                        ("signals", ("signal", "implication"))):
        items_th = (th.get(key) or {}).get("items") or []
        for i, item in enumerate(out[key]):
            item_th = items_th[i] if i < len(items_th) else {}
            for f in fields:
                if f in item:
                    item[f] = _pick(item_th.get(f), item[f])
            if key == "signals":
                item["dimensions"] = dimensions(item.get("dimensions"), lang)

    for t in out["trends"]:
        text_th = t.get("text_th") or {}
        t["text"] = {k: _pick(text_th.get(k), (t.get("text") or {}).get(k))
                     for k in ("headline", "trend", "insight", "workshop_question")}
        t["text"]["source"] = text_th.get("source", "")
        t["target"] = _pick(text_th.get("target"), t.get("target"))
        # Means-End 3 บรรทัดฉบับไทย - ไม่มีก็ไม่ใช้ฉบับอังกฤษแทน (เทมเพลตกลับไปใช้ย่อหน้า Trend/Insight ภาษาไทย)
        t["ladder"] = t.get("ladder_th")
        t["longevity_band"] = enum(t.get("longevity_band"), lang)
        a = t.get("analysis") or {}
        for k in ("investment_signal", "confidence_level", "trend_stage", "primary_driver", "estimated_duration"):
            if k in a:
                a[k] = enum(a[k], lang)
        reasons = text_th.get("product_reasons") or []
        for i, p in enumerate(t.get("products", [])):
            p["name"] = p.get("name_full") or p.get("name")
            p["reason"] = _pick(reasons[i] if i < len(reasons) else None, p.get("reason"))
        # สินค้าแยกหมวดไม่มีเหตุผลจาก LLM - แค่ใช้ชื่อเต็มที่มีภาษาไทย (ชื่อหมวดคงเป็นภาษาอังกฤษตาม Konvy)
        for c in (t.get("categories") or {}).get("categories", []):
            for p in c["products"] + [x["product"] for x in c.get("price_tiers") or [] if x.get("product")]:
                p["name"] = p.get("name_full") or p.get("name")
        for c in ((t.get("l2") or {}).get("cells") or {}).values():   # 🆕 (2026-10-21) สินค้าตัวแทนของหน้าแผนที่หมวด L2
            if c.get("product"):
                c["product"]["name"] = c["product"].get("name_full") or c["product"].get("name")

    for e in out["excluded"]:
        e["reason"] = e.get("reason_th") or e["reason"]
    out["missing"] = [next((m.replace(en, th_label, 1) for en, th_label in MISSING_TH.items() if m.startswith(en)), m)
                      for m in out["missing"]]
    return out
