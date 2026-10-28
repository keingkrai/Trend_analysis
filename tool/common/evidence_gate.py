# -*- coding: utf-8 -*-
"""
ตัวตรวจ "ข้อความของ LLM อ้างหลักฐานจริงไหม" ที่ใช้ร่วมกัน (2026-10-27) - ไม่ import bootstrap / ไม่เรียก API ใช้ได้ทุกขั้นและเทสต์ได้ตรงๆ

ใช้กับรอบที่ข้อมูลมีแต่สาย Search (Google Trends คำค้นกำลังขึ้น): STEPIC (⑭-⑮, phase5_report/stepic_evidence.py),
จุดเด่นเทรนด์ (⑪, phase3_supply_layer/highlight_evidence.py) และข้อความต่อเทรนด์ในรายงาน (⑯, phase6_pdf_report/enrich.py)

หลัก: LLM ได้ชุดหลักฐานชุดเดียว + ต้องแนบ "ข้อความที่คัดลอกตรงตัวจากชุดหลักฐาน" ทุกข้อความที่เขียน - โค้ดตรวจว่ามีอยู่จริง ไม่ผ่าน = ตัดทิ้ง
ข้อจำกัดที่รู้: ตรวจได้เฉพาะ (1) มีข้อความที่คัดลอกจริงอย่างน้อย 1 ข้อ (2) ตัวเลขหลายหลัก (3) คำค้นในเครื่องหมายคำพูดเดี่ยว -
ถ้อยคำอธิบายอื่นในประโยคยังตรวจด้วยโค้ดไม่ได้ (จึงให้ prompt ห้ามเพิ่มเอง และสแกนคำต้องห้ามหลังรัน)
"""
import re

NO_DATA = "No data"

PLACE_NAMES = {"TH": "Thailand", "WW": "worldwide", "US": "the US", "JP": "Japan", "KR": "South Korea", "GB": "the UK",
               "AU": "Australia", "HK": "Hong Kong", "ID": "Indonesia", "MY": "Malaysia", "VN": "Vietnam", "PH": "the Philippines",
               "TW": "Taiwan", "IN": "India", "ZA": "South Africa", "AE": "the UAE", "SG": "Singapore", "FR": "France",
               "ES": "Spain", "DE": "Germany", "CH": "Switzerland"}


def norm(text):
    """เทียบข้อความแบบไม่สนตัวพิมพ์/ช่องว่างซ้ำ (คำไทยที่ Google เว้นวรรคให้คงเดิมตามชุดหลักฐาน)"""
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def verify_snippets(snippets, evidence_norm):
    """ข้อความที่คัดลอกจากชุดหลักฐานจริง (ไม่สนตัวพิมพ์/ช่องว่างซ้ำ) -> รายการที่ผ่าน (ไม่ซ้ำ ลำดับเดิม) ตัดที่สั้นเกินไป (< 3 ตัวอักษร)"""
    if isinstance(snippets, str):
        snippets = [snippets]
    out = []
    for s in snippets or []:
        s = str(s).strip()
        if len(s) >= 3 and norm(s) not in evidence_norm and ":" in s:
            head, tail = s.split(":", 1)
            # LLM มักใส่ป้ายของบรรทัดหลักฐานนำหน้า (เช่น "rising searches: คลื่น ความ ร้อน") - ตัดป้ายสั้นๆ ออก ส่วนที่เหลือยังต้องตรงตัว
            if len(head.split()) <= 6 and not re.search(r"\d", head):
                s = tail.strip()
        if len(s) >= 3 and norm(s) in evidence_norm and s not in out:
            out.append(s)
    return out


_NUM_RE = re.compile(r"\d[\d,.]*%?")
_QUOTED_RE = re.compile(r"(?<![\w])'([^'\n]{3,80}?)'(?![\w])")


def _has_number(num, evidence_norm):
    """ตัวเลขนี้อยู่ในชุดหลักฐานเป็นตัวเลขทั้งก้อน (ไม่ใช่ส่วนหนึ่งของเลขที่ยาวกว่า) - "7" ไม่ตรงกับ "169" หรือ "2.7" """
    return re.search(r"(?<![\d.,])" + re.escape(num) + r"(?![\d])", evidence_norm) is not None


def numbers_supported(text, evidence_norm):
    """ตัวเลขหลายหลัก (หรือมี %) ทุกตัวในข้อความต้องอยู่ในชุดหลักฐาน - ตัวเลขหลักเดียวที่ไม่มี % ไม่ตรวจ (เช่น "3 forces")"""
    for m in _NUM_RE.findall(str(text or "")):
        token = m.rstrip(".,")
        num = token.rstrip("%")
        if (len(re.sub(r"\D", "", num)) >= 2 or "%" in token) and not _has_number(num, evidence_norm):
            return False
    return True


def quotes_supported(text, evidence_norm):
    """ทุกข้อความที่อยู่ในเครื่องหมายคำพูดเดี่ยว (คำค้นที่ LLM อ้างถึง) ต้องอยู่ในชุดหลักฐานตรงตัว - กันการแต่งคำค้น/ชื่อขึ้นเอง"""
    return all(norm(q) in evidence_norm for q in _QUOTED_RE.findall(str(text or "")))


def trend_searches(row, limit=20):
    """คำค้นจริงของเทรนด์จากแถวผลสาย Search (Source Themes ที่ยืนยัน + Members) -> list ไม่ซ้ำ ลำดับเดิม
    Members เก็บเป็นข้อความคั่นด้วย ", " - ใช้เฉพาะส่วนที่ยังไม่อยู่ในรายการ (คำค้นบางคำมีจุลภาคในตัว จึงใช้ Source Themes ก่อน)"""
    queries = list(dict.fromkeys(q for th in (row.get("Source Themes") or []) for q in th.get("evidence") or [] if q))
    queries += [q.strip() for q in str(row.get("Members") or "").split(",") if q.strip() and q.strip() not in queries]
    return queries[:limit] if limit else queries


def trend_evidence_lines(row, limit=20):
    """บรรทัดหลักฐานของเทรนด์ 1 ตัว (ใช้เหมือนกันใน STEPIC และ ⑪): ชื่อเทรนด์ (ป้ายที่ไปป์ไลน์ตั้ง ไม่ใช่หลักฐาน) + พื้นที่ + หมวด Google + คำค้นจริง
    ไม่ใส่ข้อความที่ LLM เขียนเองในสาย (outlook / ส่วนผสม / ประโยชน์ / กลุ่มเป้าหมาย) - เป็นการตีความ ไม่ใช่ข้อมูล"""
    cats = list(dict.fromkeys(th.get("category") for th in (row.get("Source Themes") or []) if th.get("category")))
    return [f"Trend: {row.get('Trend Name')}", f"  places where its searches rise: {', '.join(row.get('Places') or [])}",
            f"  Google categories its searches sit in: {', '.join(cats)}",
            "  rising searches: " + " | ".join(trend_searches(row, limit))]


def sanitize(text):
    """ไม่มีเครื่องหมายคำพูดคู่/แบ็กสแลชในชุดหลักฐาน: LLM คัดลอกข้อความมาใส่ JSON ตรงตัว ถ้ามี " อยู่ข้างใน JSON จะเสีย (เจอจริงในรอบแรกของ STEPIC)"""
    return str(text).replace('"', "'").replace("\\", "/")


def place_phrase(codes):
    """["TH", "WW"] -> "Thailand and worldwide" (ภาษาอังกฤษ ข้อความตายตัวจากข้อมูล ไม่ผ่าน LLM)"""
    names = [PLACE_NAMES.get(c, c) for c in codes or []]
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else (names[0] if names else "")


# 🆕 (2026-10-28) คำบอกการเตรียมตัว/วางแผน/ความรู้สึก (ภาษาไทย) ที่ LLM เติมให้โปรไฟล์ ⑪ ทั้งที่คำค้นไม่ได้บอก (เช่น คำค้นเป็นชื่อการประกวด -> "เตรียมตัวสำหรับการประกวด",
# "การถูกมองบนเวที") - เกตเดิมตรวจแค่ว่าข้อความที่อ้างมีอยู่จริง ไม่ได้ตรวจว่าข้อสรุปตามมาจากคำค้น จึงตรวจคำเหล่านี้เพิ่ม: ผ่านเมื่อคำนั้นอยู่ในหลักฐานเอง (มีคำค้นที่มีคำนั้น)
UNSUPPORTED_TH = re.compile(r"เตรียม|วางแผน|รู้สึก|มั่นใจ|กังวล|สบายใจ|วิตก|ถูกมอง")


def unsupported_words(text, evidence_norm):
    """คำบอกการเตรียมตัว/วางแผน/ความรู้สึกในข้อความ ที่ไม่ปรากฏในชุดหลักฐาน (evidence_norm = norm(ชุดหลักฐาน)) -> list (ว่าง = ผ่าน)"""
    return sorted({w for w in UNSUPPORTED_TH.findall(str(text or "")) if norm(w) not in evidence_norm})
