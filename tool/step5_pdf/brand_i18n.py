# -*- coding: utf-8 -*-
"""
⑰ รายงานแบรนด์ PDF — ข้อความตายตัว 2 ภาษา (ต่อยอดจาก i18n.STRINGS ของรายงานเทรนด์: footer/ราคา/"ไม่มีข้อมูล" ใช้ร่วมกัน)

หลักเดียวกับรายงานเทรนด์: ชื่อเทรนด์ คีย์เวิร์ด ชื่อแบรนด์/สินค้า และศัพท์เทคนิคคงเป็นภาษาอังกฤษ ปีเป็น ค.ศ.
ฉบับไทยใช้ชื่อสินค้าเต็ม (มีภาษาไทย) และเหตุผลจับคู่สินค้าที่แปลแล้ว (enrich.translate_items_th)
"""
import copy

from i18n import STRINGS

BRAND_STRINGS = {
    "en": {
        "report_kind": "Brand × Trend Fit Report",
        "cover_title": "{brand} × {title} Trends",
        "cover_sources": "Product data: {n} Watsons Thailand SKUs | Search data: Worldwide Google Trends",
        "prepared_for": "Prepared for {brand} by {company}",
        "summary_header": "Executive Summary",
        "on_watsons": "{brand} on Watsons Thailand",
        "skus": "SKUs listed",
        "price_range": "Price range",
        "median_price": "median {v}",
        "main_subcategories": "Main sub-categories",
        "fit_across": "Fit across the top {n} trends",
        "leading": "Leading", "competitive": "Competitive", "behind": "Behind", "gap": "Gap",
        "not_checked": "Not checked",
        "leading_def": "best product ranks 1-{a} in the market",
        "competitive_def": "ranks {a}-{b}",
        "behind_def": "ranks {a}-{b}",
        "gap_def": "beyond {a}, or no product",
        "key_messages": "Key messages",
        "msg_strongest": "Strongest fit - {trend}: {product} ranks #{rank} of {n} SKUs.",
        "msg_opportunity": "Biggest opportunity - {trend}: momentum {z}, but your closest product ranks #{rank}.",
        "msg_opportunity_none": "Biggest opportunity - {trend}: momentum {z}, and {brand} has no product close to it.",
        "msg_quick_win": "Closest to the leader - {trend}: your best product trails the market leader by only {gap} "
                         "similarity.",
        "msg_none": "No trend could be assessed for this brand in this run.",
        "matrix_header": "Trend Fit Matrix",
        "matrix_intro": "Right = faster forecast growth (Z_Delta). Up = {brand}'s closest product ranks higher among "
                        "{n} SKUs (log scale). Vertical line = median momentum of the top trends ({split}).",
        "matrix_x": "Momentum (Z_Delta) - forecast growth",
        "matrix_y": "Rank of your closest product (1 = closest)",
        "defend": "Defend", "build": "Build", "maintain": "Maintain", "monitor": "Monitor",
        "defend_def": "Fast-growing trend where you already compete - protect and promote.",
        "build_def": "Fast-growing trend with no strong product yet - the main development opportunity.",
        "maintain_def": "Slower trend where you already compete - keep the current range.",
        "monitor_def": "Slower trend with a weak fit - watch before investing.",
        "overview_header": "Fit Overview | Top {n} Trends",
        "col_trend": "Trend", "col_momentum": "Momentum", "col_best": "Your best product", "col_price": "Price",
        "col_rank": "Rank in market", "col_gap": "Gap to leader", "col_fit": "Fit", "col_action": "Action",
        "no_product": "No product",
        "not_checked_row": "Not checked for this brand - re-run the brand check (⑬) for this run",
        "momentum": "Momentum",
        "peak_interest": "Peak interest",
        "fit_level": "Fit level",
        "action": "Action",
        "your_best_rank": "Your best rank",
        "rank_of": "#{rank} of {n}",
        "your_products": "Your closest products",
        "market_leader": "Market leader",
        "you_lead": "{brand} leads this trend",
        "rank_n": "Rank #{rank}",
        "match": "Match {v}",
        "no_brand_products": "No {brand} product is close to this trend.",
        "trend_note": "Rank = position among {n} Watsons Thailand SKUs by similarity between the trend profile and "
                      "the product description (1 = closest). Similarity-based - not yet verified by people.",
        "opp_header": "Product Development Opportunities",
        "opp_intro": "Fast-growing trends where {brand} has no strong product yet (Build quadrant), strongest momentum "
                     "first.",
        "consumer_need": "Consumer need",
        "product_direction": "Product direction",
        "target": "Target",
        "keywords": "Search keywords",
        "opp_none": "No trend falls in the Build quadrant - {brand} already has a competitive product in every "
                    "fast-growing trend. Focus on defending those positions.",
        "method_header": "Appendix | How to Read This Report",
        "m_fit_title": "Fit level",
        "m_fit": "For each trend, every Watsons Thailand SKU ({n}) is ranked by how similar its description is to the "
                 "trend profile. The fit level uses the rank of {brand}'s closest product: Leading 1-{a}, Competitive "
                 "{a1}-{b}, Behind {b1}-{c}, Gap beyond {c} or no product.",
        "m_matrix_title": "Trend Fit Matrix",
        "m_matrix": "Momentum (Z_Delta) comes from the worldwide Google Trends forecast in the trend report. Trends at "
                    "or above the median momentum of the top trends ({split}) count as fast-growing. Leading and "
                    "Competitive count as a strong fit.",
        "m_data_title": "Data",
        "m_data": "Brand check (⑬) of run {run_id}: {brand}'s {skus} SKUs compared with the top {t} trends. Market "
                  "leader = the single closest SKU of any brand. Data collected {date}.",
        "m_limits_title": "Limitations",
        "m_limits": "Similarity measures how closely product text matches the trend profile - not sales, quality or "
                    "consumer preference, and it has not yet been validated against human judgement. Use the fit "
                    "levels to prioritise discussion, not as a final verdict.",
    },
    "th": {
        "report_kind": "รายงานความพร้อมของแบรนด์ต่อเทรนด์",
        "cover_title": "{brand} × เทรนด์ {title}",
        "cover_sources": "ข้อมูลสินค้า: Watsons ประเทศไทย {n} SKU | ข้อมูลการค้นหา: Google Trends ทั่วโลก",
        "prepared_for": "จัดทำให้ {brand} โดย {company}",
        "summary_header": "สรุปผู้บริหาร",
        "on_watsons": "{brand} บน Watsons ประเทศไทย",
        "skus": "จำนวนสินค้า (SKU)",
        "price_range": "ช่วงราคา",
        "median_price": "ราคากลาง {v}",
        "main_subcategories": "หมวดย่อยหลัก",
        "fit_across": "ความพร้อมใน {n} เทรนด์อันดับต้น",
        "leading": "นำตลาด", "competitive": "แข่งขันได้", "behind": "ตามหลัง", "gap": "ช่องว่าง",
        "not_checked": "ยังไม่ได้ตรวจ",
        "leading_def": "สินค้าที่ดีที่สุดอยู่อันดับ 1-{a} ของตลาด",
        "competitive_def": "อันดับ {a}-{b}",
        "behind_def": "อันดับ {a}-{b}",
        "gap_def": "เกินอันดับ {a} หรือไม่มีสินค้า",
        "key_messages": "ประเด็นสำคัญ",
        "msg_strongest": "จุดแข็งที่สุด - {trend}: {product} อยู่อันดับ {rank} จาก {n} SKU",
        "msg_opportunity": "โอกาสใหญ่ที่สุด - {trend}: แรงส่ง {z} แต่สินค้าที่ใกล้ที่สุดของคุณอยู่อันดับ {rank}",
        "msg_opportunity_none": "โอกาสใหญ่ที่สุด - {trend}: แรงส่ง {z} และ {brand} ยังไม่มีสินค้าที่ใกล้เคียง",
        "msg_quick_win": "ใกล้เจ้าตลาดที่สุด - {trend}: สินค้าที่ดีที่สุดของคุณห่างจากสินค้าอันดับ 1 เพียง {gap} "
                         "(ค่าความคล้าย)",
        "msg_none": "รอบนี้ประเมินเทรนด์ของแบรนด์นี้ไม่ได้เลย",
        "matrix_header": "Trend Fit Matrix | แผนที่ความพร้อมต่อเทรนด์",
        "matrix_intro": "ยิ่งไปทางขวา = พยากรณ์ว่าโตเร็วกว่า (Z_Delta) ยิ่งสูง = สินค้าที่ใกล้เทรนด์ที่สุดของ {brand} อยู่อันดับ"
                        "ต้นกว่าใน {n} SKU (สเกล log) เส้นแนวตั้ง = ค่ากลางแรงส่งของเทรนด์อันดับต้น ({split})",
        "matrix_x": "แรงส่ง (Z_Delta) - การเติบโตที่พยากรณ์",
        "matrix_y": "อันดับสินค้าที่ใกล้ที่สุดของคุณ (1 = ใกล้ที่สุด)",
        "defend": "ปกป้อง", "build": "สร้างใหม่", "maintain": "รักษาไว้", "monitor": "เฝ้าดู",
        "defend_def": "เทรนด์โตเร็วที่คุณมีสินค้าแข่งได้แล้ว - ปกป้องและเร่งโปรโมต",
        "build_def": "เทรนด์โตเร็วแต่ยังไม่มีสินค้าที่แข็ง - โอกาสพัฒนาสินค้าหลัก",
        "maintain_def": "เทรนด์โตช้ากว่าที่คุณมีสินค้าแข่งได้ - รักษาสินค้าที่มีอยู่",
        "monitor_def": "เทรนด์โตช้ากว่าและยังไม่พร้อม - เฝ้าดูก่อนลงทุน",
        "overview_header": "ภาพรวมความพร้อม | {n} เทรนด์อันดับต้น",
        "col_trend": "เทรนด์", "col_momentum": "แรงส่ง", "col_best": "สินค้าที่ดีที่สุดของคุณ", "col_price": "ราคา",
        "col_rank": "อันดับในตลาด", "col_gap": "ห่างจากเจ้าตลาด", "col_fit": "ระดับ", "col_action": "แนวทาง",
        "no_product": "ไม่มีสินค้า",
        "not_checked_row": "ยังไม่ได้ตรวจเทรนด์นี้กับแบรนด์ - รันการค้นหาแบรนด์ (⑬) ของรอบนี้ใหม่",
        "momentum": "แรงส่ง",
        "peak_interest": "จุดสูงสุด",
        "fit_level": "ระดับความพร้อม",
        "action": "แนวทาง",
        "your_best_rank": "อันดับที่ดีที่สุดของคุณ",
        "rank_of": "อันดับ {rank} จาก {n}",
        "your_products": "สินค้าของคุณที่ใกล้เทรนด์ที่สุด",
        "market_leader": "เจ้าตลาด",
        "you_lead": "{brand} คือเจ้าตลาดของเทรนด์นี้",
        "rank_n": "อันดับ {rank}",
        "match": "ความคล้าย {v}",
        "no_brand_products": "ยังไม่มีสินค้า {brand} ที่ใกล้เคียงเทรนด์นี้",
        "trend_note": "อันดับ = ตำแหน่งใน {n} SKU ของ Watsons ประเทศไทย เรียงตามความคล้ายระหว่างโปรไฟล์เทรนด์กับคำอธิบาย"
                      "สินค้า (1 = ใกล้ที่สุด) วัดจากความคล้ายของข้อความ ยังไม่ได้ตรวจยืนยันโดยคน",
        "opp_header": "โอกาสพัฒนาสินค้า",
        "opp_intro": "เทรนด์โตเร็วที่ {brand} ยังไม่มีสินค้าที่แข็ง (ช่อง สร้างใหม่) เรียงจากแรงส่งมากไปน้อย",
        "consumer_need": "ความต้องการของผู้บริโภค",
        "product_direction": "แนวทางสินค้า",
        "target": "กลุ่มเป้าหมาย",
        "keywords": "คีย์เวิร์ดค้นหา",
        "opp_none": "ไม่มีเทรนด์ในช่อง สร้างใหม่ - {brand} มีสินค้าที่แข่งขันได้ในทุกเทรนด์ที่โตเร็วแล้ว "
                    "ควรเน้นรักษาตำแหน่งเหล่านั้น",
        "method_header": "ภาคผนวก | วิธีอ่านรายงานนี้",
        "m_fit_title": "ระดับความพร้อม",
        "m_fit": "ในแต่ละเทรนด์ สินค้าทุก SKU บน Watsons ประเทศไทย ({n}) ถูกจัดอันดับตามความคล้ายระหว่างคำอธิบายสินค้ากับ"
                 "โปรไฟล์เทรนด์ ระดับความพร้อมใช้อันดับของสินค้า {brand} ที่ใกล้ที่สุด: นำตลาด 1-{a}, แข่งขันได้ "
                 "{a1}-{b}, ตามหลัง {b1}-{c}, ช่องว่าง เกิน {c} หรือไม่มีสินค้า",
        "m_matrix_title": "Trend Fit Matrix",
        "m_matrix": "แรงส่ง (Z_Delta) มาจากผลพยากรณ์ Google Trends ทั่วโลกในรายงานเทรนด์ เทรนด์ที่แรงส่งตั้งแต่ค่ากลางของ"
                    "เทรนด์อันดับต้น ({split}) ขึ้นไปนับว่าโตเร็ว ระดับนำตลาดและแข่งขันได้นับว่าพร้อม",
        "m_data_title": "ข้อมูล",
        "m_data": "ผลค้นหาแบรนด์ (⑬) ของรอบ {run_id}: สินค้า {brand} {skus} SKU เทียบกับ {t} เทรนด์อันดับต้น "
                  "เจ้าตลาด = SKU ที่ใกล้ที่สุดจากทุกแบรนด์ เก็บข้อมูลวันที่ {date}",
        "m_limits_title": "ข้อจำกัด",
        "m_limits": "ความคล้ายวัดว่าข้อความของสินค้าใกล้กับโปรไฟล์เทรนด์แค่ไหน ไม่ใช่ยอดขาย คุณภาพ หรือความชอบของผู้บริโภค "
                    "และยังไม่เคยตรวจเทียบกับการตัดสินของคน ใช้ระดับความพร้อมเพื่อจัดลำดับการพูดคุย ไม่ใช่คำตัดสินสุดท้าย",
    },
}


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
        if row.get("leader"):
            row["leader"]["name"] = row["leader"].get("name_full") or row["leader"]["name"]
    return out
