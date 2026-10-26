# -*- coding: utf-8 -*-
"""
⑲ รายงานส่วนแบ่งตลาด — ข้อความตายตัวของรายงาน PDF (อังกฤษ / ไทย) ชุดเดียวใช้กับเทมเพลตเดียว

กติกา (เจ้าของงาน 2026-10-12):
- ไม่บอกว่าแบรนด์ไหนชนะหรือแพ้ - ใช้ "เปลี่ยนแปลง" / "เกี่ยวข้อง" / "แหล่งข้อมูลรายงานว่า" (ตรวจในเทส: ไม่มีคำว่า win/lose/ชนะ/แพ้)
- ชื่อหมวดของ Euromonitor (Skin Care, Hair Care ...) และชื่อแบรนด์คงภาษาอังกฤษทั้ง 2 ฉบับ ปีเป็น ค.ศ.
- ภาษาง่ายแบบเดียวกับ ⑯/⑰/⑱ (plain_text.py) - ศัพท์เทคนิคอยู่ได้เฉพาะหน้าวิธีการ (คีย์ m_*)
- อ้างอิง Euromonitor ที่หน้าสุดท้าย (คีย์ final_*)
"""

STRINGS = {
    "en": {
        "na": "n/a",
        "report_title": "Thailand Beauty and Personal Care: What Is Moving Market Share",
        "report_kind": "Market share report · {y0} to {y1}",
        "cover_sources": "Sales data: Euromonitor International · New products: Thai FDA · Explanations: news and web sources",
        "copyright": "© {year} {company}",
        "rights": "Market data © Euromonitor International Ltd {edition}. See the last page.",
        # ---- summary ----
        "summary_header": "Summary",
        "kpi_market": "Market size {y}",
        "kpi_market_sub": "Growth {g} a year since {y0} · expected {f} a year to {y2}",
        "kpi_online": "Online share of sales",
        "kpi_others": "Brands outside the main list",
        "kpi_imports": "Imported share of new products",
        "kpi_imports_sub": "New product notifications at the Thai FDA, {y0} to {y1}",
        "kpi_share_sub": "{y0} to {y1}, all categories",
        "key_messages": "Key messages",
        "msg_market": "The market reached {v} in {y1}. It grew {g} a year from {y0}. Euromonitor expects {f} a year to {y2}.",
        "msg_online": "Online shops took {b} of sales in {y1}, up from {a} in {y0}. Online share rose in every category.",
        "msg_others": "Brands outside Euromonitor's main brand list held {b} of sales in {y1}, up from {a} in {y0}. "
                      "Smaller and newer brands now take a larger part of the market.",
        "msg_imports": "Imported products made up {b} of new product notifications in {y1}, up from {a} in {y0}.",
        "msg_evidence": "News and web sources gave an explanation for {n} of {k} changes we checked. "
                        "Each explanation on the following pages names its sources.",
        "how_title": "How to read this report",
        "how_body": "Numbers come from Euromonitor sales data and Thai FDA product notifications. Explanations come from news and "
                    "web sources and show what those sources report. They are linked to the change, not proof of its cause. "
                    "Brands are listed by size or in A-Z order, never by gain or loss.",
        # ---- market size ----
        "market_header": "Market size by category",
        "col_category": "Category",
        "col_value": "Sales {y}",
        "col_share": "Share of market",
        "col_growth": "Growth a year {y0}-{y1}",
        "col_forecast": "Expected a year {y1}-{y2}",
        "market_note": "Retail sales in Thai baht at current prices. Expected growth is Euromonitor's forecast.",
        "thb_bn": "THB {v} bn",
        # ---- factor overview ----
        "overview_header": "What is linked to the changes",
        "overview_intro": "Each row is one factor. Brands are listed A-Z. The last column counts the different sources behind it.",
        "col_factor": "Factor",
        "col_seen": "What we see",
        "col_brands": "Brands linked in sources",
        "col_sources": "Sources",
        "data_tag": "Sales data",
        "web_tag": "News and web",
        "only_background": "Only background information so far, not about sales in Thailand. See the details.",
        # data-factor lines
        "line_online": "Online shops: {a} to {b} of all sales",
        "line_outlet": "{outlet}: {a} to {b}",
        "line_others": "Brands outside the main list: {a} to {b} of all sales",
        "line_others_cat": "{category}: {a} to {b}",
        "line_premium": "Premium share of {category}: {a} to {b}",
        "line_fda": "New product notifications: {n0:,} in {y0} to {n1:,} in {y1}",
        "line_fda_import": "Imported share of these: {a} to {b}",
        # ---- factor page ----
        "factor_header": "Factor: {label}",
        "in_data": "In the sales data ({y0} to {y1})",
        "no_data_line": "This factor has no direct measure in the sales data. The findings come from news and web sources.",
        "no_findings_line": "No news or web page that explains this factor was found for this report.",
        "sources_report": "What sources report",
        "related_brands": "Brands linked in sources: {brands}",
        "shown_of": "Showing the strongest {k} of {n} findings.",
        "tag_direct": "About sales in Thailand",
        "tag_background": "Background",
        "factors_header": "Factors in detail",
        "brands_header": "Brands in detail",
        # ---- brand page ----
        "brand_header": "Brand: {brand}",
        "share_chart": "Share of {category} sales",
        "owner": "Company",
        "tier": "Price group",
        "tier_premium": "Premium", "tier_mass": "Mass", "tier_both": "Premium and mass",
        "share_change": "{category}: {a} in {y0} to {b} in {y1}",
        "share_change_new": "{category}: not listed in {y0} to {b} in {y1}",
        "absorbed": "Includes {names}, which Euromonitor now counts under this brand.",
        "fda_line": "New product notifications at the Thai FDA: {series}",
        "no_findings_brand": "News and web sources did not explain this change.",
        # ---- no evidence ----
        "none_header": "Changes without an explanation yet",
        "none_intro": "Sources did not explain these changes. We do not guess. A new search may find an explanation later.",
        # ---- method ----
        "method_header": "How this report was made",
        "m_data_title": "Data",
        "m_data": "Sales and shares: Euromonitor International, Beauty and Personal Care, Thailand, {edition} edition. Brand "
                  "shares cover {y0} to {y1}; market size has a forecast to {y2}. New products: Thai FDA cosmetic "
                  "notifications {f0} to {f1} ({rows:,} notifications, expired and cancelled ones included).",
        "m_compare_title": "Fair comparisons",
        "m_compare": "Changes start in {y0}, before COVID, because 2020 and 2021 do not follow the trend. When Euromonitor "
                     "merges one brand into another of the same company, both years count the merged brands together. "
                     "When Euromonitor stops listing a brand, its share moves into Others; we take that out before "
                     "saying smaller brands grew.",
        "m_search_title": "Finding explanations",
        "m_search": "For each large change we searched Google and Google News in English and Thai, from {y0} onward, and read "
                    "up to 8 articles. An AI read the articles and wrote short findings. Each finding was checked by "
                    "code: the quoted words must be in the cited article, every number must be in the data or the article, "
                    "and the wording must not say any brand won or lost.",
        "m_limits_title": "Limits",
        "m_limits": "Findings show what sources report at the same time as a change. They do not prove a cause. Brand "
                    "press releases are marked as the brand's own words. Euromonitor names about 90 brands per "
                    "category; all others sit in Others. Thai FDA notifications count new products, not sales.",
        # ---- sources ----
        "sources_header": "Sources",
        "src_news": "News", "src_web": "Web",
        # ---- final page ----
        "final_header": "Data sources and copyright",
        "final_euromonitor": "Source: Euromonitor International, Beauty and Personal Care {edition} edition, Thailand "
                             "(market sizes, company and brand shares, sales channels, premium and mass). Data extracted "
                             "on {extracted}.",
        "final_copyright": "© Euromonitor International Ltd {edition}. Euromonitor data in this report may not be "
                           "reproduced or shared further without written permission from Euromonitor International.",
        "final_fda": "New product notifications: Thai Food and Drug Administration (อย.) cosmetic notification records, "
                     "{f0} to {f1}.",
        "final_web": "Explanations: {n} news and web articles, listed on the Sources pages with links.",
        "final_prepared": "Prepared by {company}.",
    },
    "th": {
        "na": "ไม่มีข้อมูล",
        "report_title": "ตลาดความงามและของใช้ส่วนตัวไทย: อะไรเปลี่ยนส่วนแบ่งตลาด",
        "report_kind": "รายงานส่วนแบ่งตลาด · ปี {y0} ถึง {y1}",
        "cover_sources": "ยอดขาย: Euromonitor International · สินค้าใหม่: อย. · คำอธิบาย: ข่าวและเว็บไซต์",
        "copyright": "© {year} {company}",
        "rights": "ข้อมูลตลาด © Euromonitor International Ltd {edition} ดูหน้าสุดท้าย",
        "summary_header": "สรุป",
        "kpi_market": "มูลค่าตลาดปี {y}",
        "kpi_market_sub": "โตเฉลี่ยปีละ {g} ตั้งแต่ปี {y0} · คาดว่าโตปีละ {f} ถึงปี {y2}",
        "kpi_online": "สัดส่วนยอดขายออนไลน์",
        "kpi_others": "แบรนด์นอกรายชื่อหลัก",
        "kpi_imports": "สัดส่วนสินค้านำเข้าในสินค้าใหม่",
        "kpi_imports_sub": "ใบจดแจ้งเครื่องสำอางใหม่ของ อย. ปี {y0} ถึง {y1}",
        "kpi_share_sub": "ปี {y0} ถึง {y1} ทุกหมวด",
        "key_messages": "ประเด็นสำคัญ",
        "msg_market": "ตลาดมีมูลค่า {v} ในปี {y1} โตเฉลี่ยปีละ {g} ตั้งแต่ปี {y0} และ Euromonitor คาดว่าจะโตปีละ {f} ถึงปี {y2}",
        "msg_online": "ช่องทางออนไลน์มีสัดส่วน {b} ของยอดขายในปี {y1} จาก {a} ในปี {y0} และเพิ่มขึ้นในทุกหมวด",
        "msg_others": "แบรนด์ที่อยู่นอกรายชื่อหลักของ Euromonitor มีส่วนแบ่งรวม {b} ในปี {y1} จาก {a} ในปี {y0} "
                      "แบรนด์เล็กและแบรนด์ใหม่จึงมีสัดส่วนในตลาดมากขึ้น",
        "msg_imports": "สินค้านำเข้าคิดเป็น {b} ของใบจดแจ้งสินค้าใหม่ในปี {y1} จาก {a} ในปี {y0}",
        "msg_evidence": "ข่าวและเว็บไซต์ให้คำอธิบายได้ {n} จาก {k} การเปลี่ยนแปลงที่ตรวจ ทุกคำอธิบายในหน้าถัดไประบุแหล่งที่มา",
        "how_title": "วิธีอ่านรายงานนี้",
        "how_body": "ตัวเลขมาจากข้อมูลยอดขายของ Euromonitor และใบจดแจ้งสินค้าของ อย. ส่วนคำอธิบายมาจากข่าวและเว็บไซต์ "
                    "บอกว่าแหล่งเหล่านั้นรายงานอะไร เป็นสิ่งที่เกี่ยวข้องกับการเปลี่ยนแปลง ไม่ใช่ข้อพิสูจน์ว่าเป็นสาเหตุ "
                    "รายชื่อแบรนด์เรียงตามขนาดหรือตามตัวอักษร ไม่ได้เรียงตามการได้หรือเสียส่วนแบ่ง",
        "market_header": "มูลค่าตลาดแยกตามหมวด",
        "col_category": "หมวด",
        "col_value": "ยอดขายปี {y}",
        "col_share": "สัดส่วนในตลาด",
        "col_growth": "โตเฉลี่ยต่อปี {y0}-{y1}",
        "col_forecast": "คาดว่าโตต่อปี {y1}-{y2}",
        "market_note": "ยอดขายปลีกเป็นเงินบาท ราคาปัจจุบัน ส่วนที่คาดการณ์มาจาก Euromonitor",
        "thb_bn": "{v} พันล้านบาท",
        "overview_header": "อะไรเกี่ยวข้องกับการเปลี่ยนแปลง",
        "overview_intro": "แต่ละแถวคือ 1 ปัจจัย รายชื่อแบรนด์เรียงตามตัวอักษร คอลัมน์สุดท้ายคือจำนวนแหล่งข้อมูลที่ต่างกัน",
        "col_factor": "ปัจจัย",
        "col_seen": "สิ่งที่เห็น",
        "col_brands": "แบรนด์ที่แหล่งข้อมูลกล่าวถึง",
        "col_sources": "แหล่ง",
        "data_tag": "ข้อมูลยอดขาย",
        "web_tag": "ข่าวและเว็บไซต์",
        "only_background": "ตอนนี้มีเพียงข้อมูลพื้นหลัง ยังไม่เกี่ยวกับยอดขายในไทย ดูรายละเอียดในหน้าปัจจัย",
        "line_online": "ออนไลน์: {a} เป็น {b} ของยอดขายทั้งหมด",
        "line_outlet": "{outlet}: {a} เป็น {b}",
        "line_others": "แบรนด์นอกรายชื่อหลัก: {a} เป็น {b} ของยอดขายทั้งหมด",
        "line_others_cat": "{category}: {a} เป็น {b}",
        "line_premium": "สัดส่วนสินค้าพรีเมียมใน {category}: {a} เป็น {b}",
        "line_fda": "ใบจดแจ้งสินค้าใหม่: {n0:,} ใบในปี {y0} เป็น {n1:,} ใบในปี {y1}",
        "line_fda_import": "สัดส่วนสินค้านำเข้า: {a} เป็น {b}",
        "factor_header": "ปัจจัย: {label}",
        "in_data": "ในข้อมูลยอดขาย (ปี {y0} ถึง {y1})",
        "no_data_line": "ปัจจัยนี้ไม่มีตัววัดโดยตรงในข้อมูลยอดขาย สิ่งที่พบมาจากข่าวและเว็บไซต์",
        "no_findings_line": "ยังไม่พบข่าวหรือหน้าเว็บที่อธิบายปัจจัยนี้ในรายงานฉบับนี้",
        "sources_report": "แหล่งข้อมูลรายงานว่า",
        "related_brands": "แบรนด์ที่แหล่งข้อมูลกล่าวถึง: {brands}",
        "shown_of": "แสดง {k} ข้อที่หนักแน่นที่สุดจาก {n} ข้อ",
        "tag_direct": "เกี่ยวกับยอดขายในไทย",
        "tag_background": "ข้อมูลพื้นหลัง",
        "factors_header": "รายละเอียดแต่ละปัจจัย",
        "brands_header": "รายละเอียดแต่ละแบรนด์",
        "brand_header": "แบรนด์: {brand}",
        "share_chart": "ส่วนแบ่งยอดขายใน {category}",
        "owner": "บริษัท",
        "tier": "กลุ่มราคา",
        "tier_premium": "พรีเมียม", "tier_mass": "ทั่วไป", "tier_both": "พรีเมียมและทั่วไป",
        "share_change": "{category}: {a} ปี {y0} เป็น {b} ปี {y1}",
        "share_change_new": "{category}: ยังไม่มีชื่อในข้อมูลปี {y0} เป็น {b} ปี {y1}",
        "absorbed": "รวม {names} ซึ่ง Euromonitor นับรวมกับแบรนด์นี้แล้ว",
        "fda_line": "ใบจดแจ้งสินค้าใหม่ของ อย.: {series}",
        "no_findings_brand": "ข่าวและเว็บไซต์ยังไม่ได้อธิบายการเปลี่ยนแปลงนี้",
        "none_header": "การเปลี่ยนแปลงที่ยังไม่พบคำอธิบาย",
        "none_intro": "แหล่งข้อมูลยังไม่ได้อธิบายการเปลี่ยนแปลงเหล่านี้ เราไม่เดา การค้นหาครั้งต่อไปอาจพบคำอธิบาย",
        "method_header": "วิธีทำรายงานนี้",
        "m_data_title": "ข้อมูล",
        "m_data": "ยอดขายและส่วนแบ่ง: Euromonitor International หมวด Beauty and Personal Care ประเทศไทย ฉบับปี {edition} "
                  "ส่วนแบ่งแบรนด์ปี {y0} ถึง {y1} มูลค่าตลาดมีค่าคาดการณ์ถึงปี {y2} สินค้าใหม่: ใบจดแจ้งเครื่องสำอางของ อย. "
                  "{f0} ถึง {f1} ({rows:,} ใบ รวมใบที่หมดอายุและยกเลิกแล้ว)",
        "m_compare_title": "การเทียบให้เป็นธรรม",
        "m_compare": "การเปลี่ยนแปลงเริ่มนับที่ปี {y0} ก่อนโควิด เพราะปี 2020-2021 ไม่เป็นไปตามแนวโน้ม เมื่อ Euromonitor "
                     "รวมแบรนด์หนึ่งเข้ากับอีกแบรนด์ของบริษัทเดียวกัน จะนับรวมกันทั้งสองปี เมื่อ Euromonitor เลิกแยกแบรนด์ใด "
                     "ส่วนแบ่งของแบรนด์นั้นย้ายไปอยู่ใน Others เราหักส่วนนี้ออกก่อนสรุปว่าแบรนด์เล็กโตขึ้น",
        "m_search_title": "การหาคำอธิบาย",
        "m_search": "การเปลี่ยนแปลงใหญ่แต่ละเรื่อง ค้นด้วย Google และ Google News ทั้งภาษาอังกฤษและไทย ตั้งแต่ปี {y0} "
                    "อ่านบทความได้สูงสุด 8 ชิ้น แล้วให้ AI สรุปเป็นข้อสั้นๆ ทุกข้อผ่านการตรวจด้วยโปรแกรม: "
                    "ข้อความที่ยกมาต้องอยู่ในบทความที่อ้างจริง ตัวเลขทุกตัวต้องมีในข้อมูลหรือบทความ "
                    "และต้องไม่มีถ้อยคำบอกว่าแบรนด์ไหนชนะหรือแพ้",
        "m_limits_title": "ข้อจำกัด",
        "m_limits": "สิ่งที่พบคือสิ่งที่แหล่งข้อมูลรายงานในช่วงเดียวกับการเปลี่ยนแปลง ไม่ใช่ข้อพิสูจน์สาเหตุ ข่าวประชาสัมพันธ์ของแบรนด์"
                    "ระบุว่าเป็นคำของแบรนด์เอง Euromonitor แยกชื่อแบรนด์ราว 90 แบรนด์ต่อหมวด ที่เหลืออยู่ใน Others "
                    "และใบจดแจ้งของ อย. นับจำนวนสินค้าใหม่ ไม่ใช่ยอดขาย",
        "sources_header": "แหล่งข้อมูล",
        "src_news": "ข่าว", "src_web": "เว็บ",
        "final_header": "แหล่งข้อมูลและลิขสิทธิ์",
        "final_euromonitor": "ที่มา: Euromonitor International, Beauty and Personal Care ฉบับปี {edition} ประเทศไทย "
                             "(มูลค่าตลาด ส่วนแบ่งบริษัทและแบรนด์ ช่องทางขาย สินค้าพรีเมียมและทั่วไป) ดึงข้อมูลวันที่ {extracted}",
        "final_copyright": "© Euromonitor International Ltd {edition} ห้ามทำซ้ำหรือเผยแพร่ข้อมูล Euromonitor ในรายงานนี้ต่อ "
                           "โดยไม่ได้รับอนุญาตเป็นลายลักษณ์อักษรจาก Euromonitor International",
        "final_fda": "สินค้าใหม่: ข้อมูลใบจดแจ้งเครื่องสำอางของสำนักงานคณะกรรมการอาหารและยา (อย.) {f0} ถึง {f1}",
        "final_web": "คำอธิบาย: บทความข่าวและเว็บไซต์ {n} ชิ้น รายการพร้อมลิงก์อยู่ในหน้าแหล่งข้อมูล",
        "final_prepared": "จัดทำโดย {company}",
    },
}

# ชื่อช่องทางขายสำหรับผู้อ่าน (ชื่อ Euromonitor เป็นศัพท์เฉพาะ เช่น "Health and Personal Care Stores")
OUTLET_LABELS = {
    "en": {"Retail E-Commerce": "Online shops", "Direct Selling": "Direct selling", "Department Stores": "Department stores",
           "Beauty Specialists": "Beauty stores", "Pharmacies": "Pharmacies",
           "Health and Personal Care Stores": "Health and beauty chains", "Hair Salons": "Hair salons",
           "Supermarkets": "Supermarkets", "Hypermarkets": "Hypermarkets", "Convenience Stores": "Convenience stores",
           "Small Local Grocers": "Local grocery shops", "Forecourt Retailers": "Petrol station shops"},
    "th": {"Retail E-Commerce": "ออนไลน์", "Direct Selling": "ขายตรง", "Department Stores": "ห้างสรรพสินค้า",
           "Beauty Specialists": "ร้านเครื่องสำอาง", "Pharmacies": "ร้านขายยา",
           "Health and Personal Care Stores": "ร้านสุขภาพและความงาม", "Hair Salons": "ร้านทำผม",
           "Supermarkets": "ซูเปอร์มาร์เก็ต", "Hypermarkets": "ไฮเปอร์มาร์เก็ต", "Convenience Stores": "ร้านสะดวกซื้อ",
           "Small Local Grocers": "ร้านโชห่วย", "Forecourt Retailers": "ร้านในปั๊มน้ำมัน"},
}

MONTHS_TH = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")


def date_text(d, lang):
    """date -> "12 Oct 2026" / "12 ต.ค. 2026" (ค.ศ. ทั้ง 2 ภาษา ตามกติกาของรายงานชุดนี้)"""
    if not d:
        return ""
    if lang == "th":
        return f"{d.day} {MONTHS_TH[d.month - 1]} {d.year}"
    return d.strftime("%d %b %Y").lstrip("0")
