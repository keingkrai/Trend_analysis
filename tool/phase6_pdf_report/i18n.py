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
        "cover_sources": "Search data: Worldwide Google Trends (English keywords) | Product evidence: Watsons Thailand",
        "report_summary": "Report Summary",
        "prepared_by": "Prepared by:",
        "briefing": "Briefing:",
        "briefing_text": "The top {n} product trends in {topic}, selected from {total} candidate trends identified in "
                         "scientific publications, consumer conversations and industry news, then forecast with "
                         "worldwide Google Trends data{end}.",
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
        "overall_momentum": "Overall momentum (Z_Delta)",
        "trend_strength": "Trend strength",
        "current_signal": "current market signal",
        "direction": "Direction",
        "next_years": "next {years} years",
        "few": "few",
        "est_duration": "Estimated duration",
        "of_shift": "of the overall shift",
        "market_summary": "Market summary",
        "momentum_by_trend": "Momentum by trend",
        "momentum_sub": "Z_Delta = forecast average minus current search interest (z-score). Higher = faster expected growth.",
        "thr_rising": "Rising 0.2",
        "thr_breakout": "Major Breakout 0.8",
        "trend_map_header": "Trend Map | Growth vs Confirmation",
        "trend_map_intro": "Each dot is one of the top {n} trends. Right = faster forecast growth (Z_Delta). Higher = the "
                           "trend's keywords were found in more of the independent data streams; each stream beyond "
                           "the first adds +10% to the Rank Score.",
        "trend_map_alt": "Trend map: Z_Delta vs number of confirming sources",
        "trend_map_note": "Dot size = amount of supporting evidence (size of the trend's keyword cluster). Numbers in "
                          "dots are the report ranks.",
        "bump_header": "Rank Trajectory | Top {n} Trends by Year",
        "bump_intro": "Each line is a trend's rank among the top {n} in each year, by average search interest "
                      "(z-score) - 1 is the highest. Years that include forecast months combine history and forecast.",
        "bump_alt": "Bump chart: yearly rank of each top trend",
        "bump_note": "Ranks are relative to the other top trends only, so every year uses ranks 1-{n}.",
        "bump_note_end": " The final year ends at {end} and may cover only part of that year.",
        "stepic_header": "Macro Forces | STEPIC",
        "stepic_intro": "Six forces shaping the market: Society, Technology, Environment, Policy, Industry and Creativity.",
        "personas_header": "Emerging Consumer Personas",
        "value_driver": "Value driver",
        "preferred_channels": "Preferred channels",
        "signals_header": "Cross-Dimensional Signals & Outlook",
        "next_3_months": "NEXT 3 MONTHS",
        "consumer_insights": "Consumer Insights",
        "divider_sub": "Top {n} Trends & Overlooked Opportunities",
        "divider_text": "Each trend is presented on three pages: the trend and the consumer insight behind it, with its "
                        "search-interest forecast; a workshop question that frames the opportunity for your brand; and "
                        "the closest products currently listed at Watsons Thailand. Trends are ordered by Rank Score.",
        "momentum": "Momentum",
        "durability": "Durability",
        "breadth": "Breadth",
        "momentum_def": "Z_Delta - forecast average minus current search interest, in standard deviations. Above 0.2 = "
                        "Rising, above 0.8 = Major Breakout.",
        "durability_def": "Longevity Score (0-100) - how likely the trend is to last beyond a short-lived fad, scored "
                          "with fixed rules from the evidence.",
        "breadth_def": "Number of independent evidence sources (out of 3) whose search keywords overlap with the trend.",
        "chart_caption": "Search interest",
        "chart_caption_end": " - history and forecast to {end}",
        "chart_alt": "Forecast chart",
        "no_forecast": "No forecast series in this run",
        "status": "Status",
        "peak_interest": "Peak interest",
        "investment_signal": "Investment signal",
        "confidence": "Confidence",
        "trend_stage": "Trend stage",
        "main_driver": "Main driver",
        "duration": "Duration",
        "target_consumer": "Target consumer",
        "rank": "Rank",
        "sources_of_3": "{n}/3 sources",
        "tracked_keywords": "Tracked search keywords",
        "linked_concepts": "{n} linked concepts",
        "months_with_data": "{pct}% months with data",
        "rank_score": "Rank score {v}",
        "overlooked": "Overlooked Opportunity {n}:",
        "workshop_question": "Workshop Question",
        "evidence_sub": "Market evidence - the closest products currently listed at Watsons Thailand",
        "no_products": "No product-matching results for this trend in this run.",
        "evidence_note": "Products are ranked by cosine similarity between the trend profile and each product's "
                         "description{stats}. These are the nearest existing products, not verified trend fits.",
        "evidence_stats": " (this trend: best {best}, average {mean} across {n} SKUs)",
        "method_header": "Appendix | Methodology",
        "method_1_title": "1. Evidence collection",
        "method_1": "Articles are gathered from three independent source types: scientific publications, consumer "
                    "conversations and industry news. A language model extracts subject-relation-object statements "
                    "from each document, and a statement is kept only when its supporting sentence is found "
                    "word-for-word in the source. Statements are grouped into trend candidates by graph clustering "
                    "(Louvain, 20-run consensus){total}.",
        "method_1_total": " - {n} candidates in this run",
        "method_2_title": "2. Search-interest forecast",
        "method_2": "Each candidate's search keywords are tracked in worldwide Google Trends (monthly) and converted to "
                    "z-scores. Four models - Holt-Winters, linear regression, random forest and XGBoost - are compared "
                    "on a 6-month holdout, and the most accurate one forecasts the next {years} years. Z_Delta = "
                    "forecast average minus the current level. Status: above 0.8 Major Breakout, above 0.2 Rising, "
                    "below -0.2 Fading, otherwise Stable.",
        "method_3_title": "3. Ranking and selection",
        "method_3": "Rank Score = Z_Delta x (1 + 0.1 x (sources sharing the trend's keywords - 1)) when Z_Delta is "
                    "positive, otherwise Z_Delta. Trends are taken in Rank Score order; sales-channel trends with no "
                    "product attributes are skipped until {n} product trends are selected. Durability (Longevity "
                    "Score) is calculated with fixed rules from evidence verdicts - numbers are never produced by the "
                    "language model.",
        "method_4_title": "4. Product matching",
        "method_4": "Each trend's profile (benefits, job-to-be-done, point of difference) is converted to a text "
                    "embedding and compared with {n} Watsons Thailand SKUs by cosine similarity. The closest products "
                    "are listed with a short model-written rationale.",
        "notes_header": "Appendix | Notes & Data",
        "run_details": "Run details",
        "topic": "Topic",
        "run_id": "Run ID",
        "data_collected": "Data collected",
        "report_generated": "Report generated",
        "forecast_window": "Forecast window",
        "language_models": "Language models",
        "report_copy": "English copy",
        "not_included": "Trends not included",
        "rank_n": "rank {n}",
        "how_to_use": "How to use this report",
        "how_to_use_text": "This report is a decision-support tool, not a final answer. Steps that use a language model "
                           "(query generation, trend naming, profiles and the English copy in this report) can vary "
                           "between runs. Product matching has not yet been measured against human-labelled examples, "
                           "so matched products show where the shelf is closest to a trend - not proof that a product "
                           "delivers it.",
        "data_not_available": "Data not available in this run",
    },
    "th": {
        "na": "ไม่มีข้อมูล",
        "price_na": "ไม่มีข้อมูลราคา",
        "thb": "{v} บาท",
        "copyright": "Copyright © {year} {company}",
        "rights": "สงวนลิขสิทธิ์",
        "cover_sub": "รายงานเทรนด์",
        "cover_outlook": " · มองไปถึง {end}",
        "cover_sources": "ข้อมูลการค้นหา: Google Trends ทั่วโลก (คีย์เวิร์ดภาษาอังกฤษ) | หลักฐานสินค้า: Watsons ประเทศไทย",
        "report_summary": "สรุปรายงาน",
        "prepared_by": "จัดทำโดย:",
        "briefing": "ภาพรวม:",
        "briefing_text": "{n} เทรนด์สินค้าอันดับต้นในหมวด {topic} คัดจากเทรนด์ตั้งต้น {total} เทรนด์ที่พบในงานวิจัย "
                         "บทสนทนาของผู้บริโภค และข่าวอุตสาหกรรม แล้วพยากรณ์ด้วยข้อมูล Google Trends ทั่วโลก{end}",
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
        "overall_momentum": "แรงส่งโดยรวม (Z_Delta)",
        "trend_strength": "ความแข็งแรงของเทรนด์",
        "current_signal": "สัญญาณตลาดปัจจุบัน",
        "direction": "ทิศทาง",
        "next_years": "ใน {years} ปีข้างหน้า",
        "few": "อีกไม่กี่",
        "est_duration": "ระยะเวลาโดยประมาณ",
        "of_shift": "ของการเปลี่ยนแปลงโดยรวม",
        "market_summary": "สรุปภาพตลาด",
        "momentum_by_trend": "แรงส่งรายเทรนด์",
        "momentum_sub": "Z_Delta = ค่าเฉลี่ยที่พยากรณ์ลบความสนใจการค้นหาปัจจุบัน (z-score) ยิ่งสูง = คาดว่าโตเร็วยิ่งขึ้น",
        "thr_rising": "กำลังขึ้น 0.2",
        "thr_breakout": "ทะยานแรง 0.8",
        "trend_map_header": "แผนที่เทรนด์ | การเติบโต เทียบ การยืนยันจากหลายแหล่ง",
        "trend_map_intro": "แต่ละจุดคือหนึ่งใน {n} เทรนด์อันดับต้น ยิ่งไปทางขวา = พยากรณ์ว่าโตเร็วกว่า (Z_Delta) ยิ่งสูง = "
                           "พบคีย์เวิร์ดของเทรนด์ในแหล่งข้อมูลอิสระมากกว่า ทุกแหล่งที่เพิ่มจากแหล่งแรกบวก Rank Score 10%",
        "trend_map_alt": "แผนที่เทรนด์: Z_Delta เทียบจำนวนแหล่งที่ยืนยัน",
        "trend_map_note": "ขนาดจุด = ปริมาณหลักฐานที่สนับสนุน (ขนาดกลุ่มคีย์เวิร์ดของเทรนด์) ตัวเลขในจุดคืออันดับในรายงาน",
        "bump_header": "เส้นทางอันดับ | {n} เทรนด์อันดับต้นรายปี",
        "bump_intro": "แต่ละเส้นคืออันดับของเทรนด์ในกลุ่ม {n} อันดับต้นในแต่ละปี ตามความสนใจการค้นหาเฉลี่ย (z-score) "
                      "อันดับ 1 คือสูงสุด ปีที่มีเดือนพยากรณ์รวมทั้งข้อมูลจริงและค่าพยากรณ์",
        "bump_alt": "Bump chart: อันดับรายปีของเทรนด์อันดับต้น",
        "bump_note": "อันดับเทียบกันเองเฉพาะเทรนด์อันดับต้น ทุกปีจึงใช้อันดับ 1-{n}",
        "bump_note_end": " ปีสุดท้ายสิ้นสุดที่ {end} อาจครอบคลุมไม่เต็มปี",
        "stepic_header": "แรงขับระดับมหภาค | STEPIC",
        "stepic_intro": "6 แรงขับที่กำหนดทิศทางตลาด: สังคม เทคโนโลยี สิ่งแวดล้อม นโยบาย อุตสาหกรรม และความคิดสร้างสรรค์",
        "personas_header": "กลุ่มผู้บริโภคที่กำลังเกิดขึ้น",
        "value_driver": "สิ่งที่ให้คุณค่า",
        "preferred_channels": "ช่องทางที่ใช้",
        "signals_header": "สัญญาณข้ามมิติและแนวโน้มข้างหน้า",
        "next_3_months": "3 เดือนข้างหน้า",
        "consumer_insights": "อินไซต์ผู้บริโภค",
        "divider_sub": "{n} เทรนด์อันดับต้นและโอกาสที่ถูกมองข้าม",
        "divider_text": "แต่ละเทรนด์มี 3 หน้า: เทรนด์และอินไซต์ผู้บริโภคเบื้องหลัง พร้อมกราฟพยากรณ์ความสนใจการค้นหา, "
                        "คำถามเวิร์กช็อปที่ชี้โอกาสให้แบรนด์ของคุณ และสินค้าที่ใกล้เคียงที่สุดซึ่งวางขายอยู่ใน Watsons "
                        "ประเทศไทยตอนนี้ เทรนด์เรียงตาม Rank Score",
        "momentum": "แรงส่ง",
        "durability": "ความยั่งยืน",
        "breadth": "ความกว้าง",
        "momentum_def": "Z_Delta - ค่าเฉลี่ยที่พยากรณ์ลบความสนใจการค้นหาปัจจุบัน หน่วยเป็นส่วนเบี่ยงเบนมาตรฐาน เกิน 0.2 = "
                        "กำลังขึ้น เกิน 0.8 = ทะยานแรง",
        "durability_def": "Longevity Score (0-100) - โอกาสที่เทรนด์จะอยู่ได้นานกว่ากระแสชั่วคราว ให้คะแนนด้วยกฎตายตัวจากหลักฐาน",
        "breadth_def": "จำนวนแหล่งหลักฐานอิสระ (จาก 3) ที่คีย์เวิร์ดค้นหาซ้อนทับกับเทรนด์นี้",
        "chart_caption": "ความสนใจการค้นหา",
        "chart_caption_end": " - ข้อมูลย้อนหลังและพยากรณ์ถึง {end}",
        "chart_alt": "กราฟพยากรณ์",
        "no_forecast": "รอบนี้ไม่มีข้อมูลพยากรณ์รายเดือน",
        "status": "สถานะ",
        "peak_interest": "จุดสูงสุด",
        "investment_signal": "สัญญาณลงทุน",
        "confidence": "ความมั่นใจ",
        "trend_stage": "ระยะของเทรนด์",
        "main_driver": "แรงขับหลัก",
        "duration": "ระยะเวลา",
        "target_consumer": "กลุ่มเป้าหมาย",
        "rank": "อันดับ",
        "sources_of_3": "{n}/3 แหล่ง",
        "tracked_keywords": "คีย์เวิร์ดค้นหาที่ติดตาม",
        "linked_concepts": "{n} แนวคิดที่เชื่อมโยง",
        "months_with_data": "มีข้อมูล {pct}% ของเดือน",
        "rank_score": "Rank score {v}",
        "overlooked": "โอกาสที่ถูกมองข้าม {n}:",
        "workshop_question": "คำถามเวิร์กช็อป",
        "evidence_sub": "หลักฐานในตลาด - สินค้าที่ใกล้เคียงที่สุดซึ่งวางขายอยู่ใน Watsons ประเทศไทย",
        "no_products": "รอบนี้ไม่มีผลจับคู่สินค้าสำหรับเทรนด์นี้",
        "evidence_note": "เรียงสินค้าตาม cosine similarity ระหว่างโปรไฟล์เทรนด์กับคำอธิบายสินค้าแต่ละตัว{stats} "
                         "เป็นสินค้าที่ใกล้เคียงที่สุดที่มีอยู่ ไม่ใช่สินค้าที่ยืนยันแล้วว่าตอบเทรนด์",
        "evidence_stats": " (เทรนด์นี้: สูงสุด {best} เฉลี่ย {mean} จาก {n} SKU)",
        "method_header": "ภาคผนวก | วิธีการ",
        "method_1_title": "1. การเก็บหลักฐาน",
        "method_1": "รวบรวมบทความจากแหล่งอิสระ 3 ประเภท ได้แก่ งานวิจัย บทสนทนาของผู้บริโภค และข่าวอุตสาหกรรม "
                    "โมเดลภาษาสกัดข้อความรูปแบบ ประธาน-ความสัมพันธ์-กรรม จากแต่ละเอกสาร และเก็บไว้เฉพาะข้อความที่พบประโยค"
                    "หลักฐานตรงตัวในเอกสารต้นทาง จากนั้นจัดกลุ่มเป็นเทรนด์ตั้งต้นด้วยการจัดกลุ่มกราฟ (Louvain โหวต 20 รอบ){total}",
        "method_1_total": " - รอบนี้ได้ {n} เทรนด์ตั้งต้น",
        "method_2_title": "2. การพยากรณ์ความสนใจการค้นหา",
        "method_2": "ติดตามคีย์เวิร์ดค้นหาของแต่ละเทรนด์ใน Google Trends ทั่วโลก (รายเดือน) แล้วแปลงเป็น z-score "
                    "เทียบ 4 โมเดล - Holt-Winters, linear regression, random forest และ XGBoost - บนช่วงทดสอบ 6 เดือน "
                    "โมเดลที่แม่นที่สุดใช้พยากรณ์ {years} ปีข้างหน้า Z_Delta = ค่าเฉลี่ยที่พยากรณ์ลบระดับปัจจุบัน "
                    "สถานะ: เกิน 0.8 ทะยานแรง, เกิน 0.2 กำลังขึ้น, ต่ำกว่า -0.2 กำลังลดลง, นอกนั้นทรงตัว",
        "method_3_title": "3. การจัดอันดับและคัดเลือก",
        "method_3": "Rank Score = Z_Delta x (1 + 0.1 x (จำนวนแหล่งที่พบคีย์เวิร์ดของเทรนด์ - 1)) เมื่อ Z_Delta เป็นบวก "
                    "ไม่อย่างนั้นใช้ Z_Delta ตรงๆ คัดเทรนด์ตามลำดับ Rank Score โดยข้ามเทรนด์ช่องทางการขายที่ไม่มีคุณสมบัติ"
                    "สินค้า จนครบ {n} เทรนด์สินค้า ความยั่งยืน (Longevity Score) คำนวณด้วยกฎตายตัวจากผลตัดสินหลักฐาน "
                    "ตัวเลขทุกตัวไม่ได้มาจากโมเดลภาษา",
        "method_4_title": "4. การจับคู่สินค้า",
        "method_4": "แปลงโปรไฟล์ของแต่ละเทรนด์ (ประโยชน์, งานที่ผู้บริโภคต้องการให้สำเร็จ, จุดต่าง) เป็น text embedding "
                    "แล้วเทียบกับสินค้า Watsons ประเทศไทย {n} SKU ด้วย cosine similarity แสดงสินค้าที่ใกล้เคียงที่สุด"
                    "พร้อมเหตุผลสั้นๆ ที่โมเดลเขียน",
        "notes_header": "ภาคผนวก | หมายเหตุและข้อมูล",
        "run_details": "รายละเอียดรอบรัน",
        "topic": "หัวข้อ",
        "run_id": "Run ID",
        "data_collected": "วันที่เก็บข้อมูล",
        "report_generated": "วันที่สร้างรายงาน",
        "forecast_window": "ช่วงพยากรณ์",
        "language_models": "โมเดลภาษา",
        "report_copy": "ข้อความภาษาไทย",
        "not_included": "เทรนด์ที่ไม่ได้รวมไว้",
        "rank_n": "อันดับ {n}",
        "how_to_use": "วิธีใช้รายงานนี้",
        "how_to_use_text": "รายงานนี้เป็นเครื่องมือช่วยตัดสินใจ ไม่ใช่คำตอบสุดท้าย ขั้นตอนที่ใช้โมเดลภาษา (สร้างคำค้น, "
                           "ตั้งชื่อเทรนด์, โปรไฟล์เทรนด์ และข้อความภาษาไทยในรายงานนี้) ให้ผลต่างกันได้ในแต่ละรอบ "
                           "การจับคู่สินค้ายังไม่เคยวัดความแม่นยำเทียบกับตัวอย่างที่คนตรวจ สินค้าที่จับคู่ได้จึงบอกว่า"
                           "ชั้นวางสินค้าใกล้เคียงเทรนด์ตรงไหน ไม่ใช่หลักฐานว่าสินค้านั้นตอบเทรนด์ได้จริง",
        "data_not_available": "ข้อมูลที่ไม่มีในรอบนี้",
    },
}

# ค่าชุดคำตายตัวจาก ⑦ (ดู trend_final_v2_subset.py: status ใน forecast_trend, compute_investment_signal และ enum ในพรอมต์
# cluster_analysis/market_overview) - ค่าที่ไม่อยู่ในตารางคงเป็นภาษาอังกฤษตามเดิม
ENUM_TH = {
    "Major Breakout": "ทะยานแรง", "Rising": "กำลังขึ้น", "Stable": "ทรงตัว", "Fading": "กำลังลดลง",
    "Invest Now": "ลงทุนได้ทันที", "Monitor": "เฝ้าติดตาม", "Wait": "รอดูก่อน",
    "High": "สูง", "Medium": "ปานกลาง", "Low": "ต่ำ",
    "Emerging": "เริ่มก่อตัว", "Growing": "กำลังเติบโต", "Peaking": "/*74กล้จุดสูงสุด", "Declining": "ขาลง",
    "Organic Seasonality": "ตามฤดูกาล", "External Shock": "ปัจจัยภายนอกกระทบ",
    "Structural Growth": "เติบโตเชิงโครงสร้าง", "Mixed/Uncertain": "ผสม/ไม่ชัดเจน",
    "Short-term": "ระยะสั้น", "Medium-term": "ระยะกลาง", "Long-term": "ระยะยาว",
    "Weak": "อ่อน", "Moderate": "ปานกลาง", "Strong": "แข็งแรง",
    "Strengthening": "แข็งแกร่งขึ้น", "Weakening": "อ่อนตัวลง",
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
    "Monthly forecast series": "ค่าพยากรณ์รายเดือน",
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

    ov = out["overview"]
    ov["overall"]["Status"] = enum(ov["overall"].get("Status"), lang)
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
        t["status"] = enum(t.get("status"), lang)
        t["peak_month"] = month_year(t.get("peak_month"), lang)
        a = t.get("analysis") or {}
        for k in ("investment_signal", "confidence_level", "trend_stage", "primary_driver", "estimated_duration"):
            if k in a:
                a[k] = enum(a[k], lang)
        reasons = text_th.get("product_reasons") or []
        for i, p in enumerate(t.get("products", [])):
            p["name"] = p.get("name_full") or p.get("name")
            p["reason"] = _pick(reasons[i] if i < len(reasons) else None, p.get("reason"))

    for e in out["excluded"]:
        e["reason"] = e.get("reason_th") or e["reason"]
    out["missing"] = [next((m.replace(en, th_label, 1) for en, th_label in MISSING_TH.items() if m.startswith(en)), m)
                      for m in out["missing"]]
    return out
