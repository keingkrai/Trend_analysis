# -*- coding: utf-8 -*-
"""
⑯ Category Deep-Dive — ข้อความตายตัว 2 ภาษา (เทมเพลตเดียว: templates/category_dive.html.j2)
ใช้ชุดข้อความของรายงานหลัก (i18n.STRINGS: ลิขสิทธิ์ / ป้ายทางโยง link_path_N / na) + ข้อความเฉพาะเล่มนี้
"""
from i18n import STRINGS

DIVE_STRINGS = {
    "en": {
        "dv_cover_title": "Google Category Deep-Dive: {title}",
        "dv_report_kind": "What is rising in each Google category, and where it meets beauty",
        "dv_cover_sources": "Source: rising Google searches over the last 12 months ({places})",
        "dv_ov_header": "Rising Searches by Google Category",
        "dv_ov_intro": "Searches that rose on Google over the last 12 months ({places}), grouped by Google's own categories. In each category an AI "
                       "grouped the searches into topics and checked which topics connect to beauty and personal care.",
        "dv_stat_searches": "Rising searches",
        "dv_stat_topics": "Topics in {k} categories",
        "dv_stat_linked": "Topics linked to beauty",
        "dv_stat_linked_sub": "{pct}% of all rising searches sit in them",
        "dv_col_cat": "Google category",
        "dv_col_searches": "Rising searches",
        "dv_col_topics": "Topics",
        "dv_col_linked": "Linked to beauty",
        "dv_col_trends": "In report trends",
        "dv_ov_none": "In {k} categories no topic links to beauty products: {names}.",
        "dv_ov_pages": "The next pages cover the {k} categories that have at least one linked topic.",
        "dv_ov_caveat": "Counts are entries on Google's rising lists, not search volume. The link to beauty is an AI check of each topic's example "
                        "searches, not a measured result.",
        "dv_cat_stats": "{n} rising searches · {topics} topics · {linked} linked to beauty",
        "dv_linked_title": "Topics linked to beauty",
        "dv_other_title": "Also rising in this category, with no link to beauty products",
        "dv_more": "{n} more linked topics are not shown",
        "dv_topic_stat": "{n} rising searches · {where}",
        "dv_where_th": "Thailand",
        "dv_where_ww": "Worldwide",
        "dv_where_both": "Thailand and worldwide",
        "dv_breakout": "{b} Breakout",
        "dv_link": "Link: {path} → {cats}",
        "dv_link_eg": "e.g.",
        "dv_examples": "Example searches",
        "dv_feeds": "In this report: #{rank} {name}",
        "dv_cat_note": "Topics are groups of searches made by an AI; each sentence is checked against the searches. Breakout is Google's label for a rise of "
                       "more than 5,000%. Search wording is shown as Google lists it.",
        "dv_notes_header": "How to Read This Report",
        "dv_m_what_title": "What this shows",
        "dv_m_what": "Searches that Google lists as rising over the last 12 months in each of its own categories, for {places}. A search can appear in "
                     "more than one category. Counts are list entries, not search volume.",
        "dv_m_topics_title": "Topics",
        "dv_m_topics": "An AI grouped the searches of each category by what they are about, so one topic can mix searches that Google filed together. "
                       "Topics are ordered by the number of places where they rise, then whether they rise in Thailand, then the number of searches, "
                       "then the share marked Breakout.",
        "dv_m_link_title": "Link to beauty",
        "dv_m_link": "An AI checked each topic's example searches against seven ways a topic can reach beauty and personal care (direct beauty, "
                     "environment, body and health, occasions, activities, ingredients, culture and looks) and named the product categories. "
                     "It is a screening step. The trend pages of the main report apply stricter checks, so a linked topic here is not always a trend there.",
        "dv_m_text_title": "The sentences",
        "dv_m_text": "Each topic sentence is written by an AI from the topic's searches only. Code checks that the searches it quotes exist, that "
                     "numbers and quoted words appear in them, and rejects sentences that explain why people search. A sentence that fails is "
                     "replaced by example searches.",
        "dv_m_limits_title": "Limits",
        "dv_m_limits": "This shows what is rising now. It is not a forecast and not what people search most. Google's own category filing is "
                       "noisy: sport and news searches can appear under Beauty & Fitness. Growth forecasts exist only for the trends in the main report.",
        "dv_talk_col": "Topics linked to beauty",
        "dv_part2_a": "Part 2 starts on page",
        "dv_part2_b": "and goes through the {k} categories that have at least one topic linked to beauty.",
        "dv_m_part2_title": "Part 2: inside each Google category",
        "dv_m_part2": "Part 2 lists, for each Google category, the groups of rising searches that an AI formed (topics). Topics are ordered by the "
                      "number of places where they rise, then whether they rise in Thailand, then the number of searches, then the share marked Breakout. An AI also "
                      "checked each topic's example searches for a link to beauty and personal care. This is a screening step; the trend pages apply "
                      "stricter checks. Each sentence is written from the topic's searches only, code checks the quotes and numbers, and a sentence that "
                      "fails is replaced by example searches. It shows what is rising now, not a forecast.",
        "dv_m_data": "Run {run_id} · {date}",
    },
    "th": {
        "dv_cover_title": "เจาะรายหมวดของ Google: {title}",
        "dv_report_kind": "ในแต่ละหมวดของ Google อะไรกำลังขึ้น และส่วนไหนเชื่อมถึงความงาม",
        "dv_cover_sources": "ที่มา: คำค้นที่กำลังขึ้นบน Google ในรอบ 12 เดือนล่าสุด ({places})",
        "dv_ov_header": "คำค้นที่กำลังขึ้นแยกตามหมวดของ Google",
        "dv_ov_intro": "คำค้นที่กำลังขึ้นบน Google ในรอบ 12 เดือนล่าสุด ({places}) จัดตามหมวดของ Google เอง ในแต่ละหมวด AI จัดคำค้นเป็นหัวข้อ "
                       "แล้วตรวจว่าหัวข้อไหนเชื่อมถึงความงามและการดูแลตัวเอง",
        "dv_stat_searches": "คำค้นที่กำลังขึ้น",
        "dv_stat_topics": "หัวข้อใน {k} หมวด",
        "dv_stat_linked": "หัวข้อที่โยงถึงความงาม",
        "dv_stat_linked_sub": "มีคำค้น {pct}% ของทั้งหมดอยู่ในหัวข้อเหล่านี้",
        "dv_col_cat": "หมวดของ Google",
        "dv_col_searches": "คำค้นที่ขึ้น",
        "dv_col_topics": "หัวข้อ",
        "dv_col_linked": "โยงถึงความงาม",
        "dv_col_trends": "อยู่ในเทรนด์",
        "dv_ov_none": "{k} หมวดไม่มีหัวข้อที่โยงถึงสินค้าความงามเลย: {names}",
        "dv_ov_pages": "หน้าถัดไปแสดง {k} หมวดที่มีหัวข้อที่โยงอย่างน้อย 1 หัวข้อ",
        "dv_ov_caveat": "ตัวเลขนับรายการในรายการ \"กำลังขึ้น\" ของ Google ไม่ใช่ปริมาณการค้นหา การโยงถึงความงามเป็นผลตรวจของ AI จากคำค้นตัวอย่างของแต่ละหัวข้อ "
                        "ไม่ใช่ผลที่วัดได้",
        "dv_cat_stats": "คำค้นที่กำลังขึ้น {n} คำ · {topics} หัวข้อ · โยงถึงความงาม {linked} หัวข้อ",
        "dv_linked_title": "หัวข้อที่โยงถึงความงาม",
        "dv_other_title": "ในหมวดนี้ยังมีสิ่งที่กำลังขึ้น แต่ไม่โยงถึงสินค้าความงาม",
        "dv_more": "ยังมีหัวข้อที่โยงอีก {n} หัวข้อที่ไม่ได้แสดง",
        "dv_topic_stat": "คำค้นที่ขึ้น {n} คำ · {where}",
        "dv_where_th": "ไทย",
        "dv_where_ww": "ทั่วโลก",
        "dv_where_both": "ไทยและทั่วโลก",
        "dv_breakout": "Breakout {b}",
        "dv_link": "โยง: {path} → {cats}",
        "dv_link_eg": "เช่น",
        "dv_examples": "ตัวอย่างคำค้น",
        "dv_feeds": "ในรายงานหลัก: #{rank} {name}",
        "dv_cat_note": "หัวข้อคือกลุ่มคำค้นที่ AI จัดให้ ประโยคอธิบายทุกประโยคถูกตรวจกับคำค้น Breakout คือป้ายของ Google สำหรับคำค้นที่ขึ้นมากกว่า 5,000% "
                       "คำค้นแสดงตามที่ Google ลงรายการไว้",
        "dv_notes_header": "วิธีอ่านรายงานเล่มนี้",
        "dv_m_what_title": "รายงานนี้แสดงอะไร",
        "dv_m_what": "คำค้นที่ Google ลงรายการว่ากำลังขึ้นในรอบ 12 เดือนล่าสุด ในแต่ละหมวดของ Google เอง สำหรับ{places} คำค้นหนึ่งอาจอยู่ได้หลายหมวด "
                     "ตัวเลขนับรายการ ไม่ใช่ปริมาณการค้นหา",
        "dv_m_topics_title": "หัวข้อ",
        "dv_m_topics": "AI จัดคำค้นของแต่ละหมวดตามเนื้อหา หัวข้อหนึ่งจึงอาจรวมคำค้นที่ Google ใส่หมวดเดียวกันแต่เรื่องต่างกัน "
                       "หัวข้อเรียงตามจำนวนพื้นที่ที่ขึ้น ต่อด้วยขึ้นในไทยหรือไม่ จำนวนคำค้น และสัดส่วนที่ติดป้าย Breakout",
        "dv_m_link_title": "การโยงถึงความงาม",
        "dv_m_link": "AI ตรวจคำค้นตัวอย่างของแต่ละหัวข้อกับ 7 ทางที่หัวข้ออาจโยงถึงความงามและการดูแลตัวเอง (ความงามตรงๆ สภาพแวดล้อม ร่างกายและสุขภาพ "
                     "โอกาสและเทศกาล กิจกรรม ส่วนผสม วัฒนธรรมและลุค) พร้อมระบุหมวดสินค้า เป็นแค่ขั้นคัดกรอง หน้าเทรนด์ของรายงานหลักตรวจเข้มกว่านี้ "
                     "หัวข้อที่โยงในเล่มนี้จึงไม่จำเป็นต้องเป็นเทรนด์ในรายงานหลัก",
        "dv_m_text_title": "ประโยคอธิบาย",
        "dv_m_text": "ประโยคของแต่ละหัวข้อ AI เขียนจากคำค้นของหัวข้อนั้นเท่านั้น โค้ดตรวจว่าคำค้นที่ยกมามีอยู่จริง ตัวเลขและคำในเครื่องหมายคำพูดอยู่ในคำค้น "
                     "และตัดประโยคที่อธิบายว่าทำไมคนถึงค้น ประโยคที่ไม่ผ่านจะถูกแทนด้วยตัวอย่างคำค้น",
        "dv_m_limits_title": "ข้อจำกัด",
        "dv_m_limits": "เล่มนี้แสดงสิ่งที่กำลังขึ้นตอนนี้ ไม่ใช่การพยากรณ์ และไม่ใช่สิ่งที่คนค้นมากที่สุด การจัดหมวดของ Google เองก็ปนกัน: "
                       "คำค้นกีฬาและข่าวอาจอยู่ในหมวด Beauty & Fitness การพยากรณ์การเติบโตมีเฉพาะเทรนด์ในรายงานหลัก",
        "dv_talk_col": "หัวข้อที่โยงถึงความงาม",
        "dv_part2_a": "ส่วนที่ 2 เริ่มที่หน้า",
        "dv_part2_b": "เป็นต้นไป แสดงทีละหมวดสำหรับ {k} หมวดที่มีหัวข้อโยงถึงความงามอย่างน้อย 1 หัวข้อ",
        "dv_m_part2_title": "ส่วนที่ 2: เจาะรายหมวดของ Google",
        "dv_m_part2": "ส่วนที่ 2 แสดงทีละหมวดของ Google ว่า AI จัดคำค้นที่กำลังขึ้นเป็นหัวข้ออะไรบ้าง เรียงตามจำนวนพื้นที่ที่ขึ้น ต่อด้วยขึ้นในไทยหรือไม่ "
                      "จำนวนคำค้น และสัดส่วนที่ติดป้าย Breakout AI ยังตรวจคำค้นตัวอย่างของแต่ละหัวข้อว่าโยงถึงความงามและการดูแลตัวเองหรือไม่ "
                      "เป็นแค่ขั้นคัดกรอง หน้าเทรนด์ตรวจเข้มกว่านี้ ประโยคของแต่ละหัวข้อเขียนจากคำค้นของหัวข้อนั้นเท่านั้น โค้ดตรวจคำค้นที่ยกมาและตัวเลข "
                      "ประโยคที่ไม่ผ่านจะถูกแทนด้วยตัวอย่างคำค้น ส่วนนี้แสดงสิ่งที่กำลังขึ้นตอนนี้ ไม่ใช่การพยากรณ์",
        "dv_m_data": "รอบ {run_id} · {date}",
    },
}


def dive_strings(lang):
    """ข้อความตายตัวของเล่มเจาะรายหมวด = ของรายงานหลัก + ข้อความเฉพาะเล่มนี้"""
    return {**STRINGS[lang], **DIVE_STRINGS[lang]}
