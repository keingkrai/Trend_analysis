# -*- coding: utf-8 -*-
"""
⑪ จุดเด่นเทรนด์ แบบ "ใช้เฉพาะสิ่งที่คำค้นยืนยัน" - ใช้กับเทรนด์ของสาย Search (Google Trends คำค้นกำลังขึ้น) (2026-10-27)

ปัญหา: ⑪ เดิมอ่าน "ส่วนผสม/ประโยชน์/กลุ่มเป้าหมาย/บริบท" ซึ่งเป็นข้อความที่ LLM เขียนไว้แล้วในขั้นสายหลักฐาน (ตีความซ้อนตีความ) และสั่งให้เขียน
"ผู้บริโภครู้สึก/ถูกมองยังไง" ทุกครั้ง - รอบแรกของสาย Search ได้ข้อความเช่น "มั่นใจในการออกสังคมจากผมที่ดูสุขภาพดี" ที่คำค้นไม่ได้บอก

ที่นี่ LLM อ่านคำค้นจริงของเทรนด์ (ชุดหลักฐาน) แล้วเขียนทีละมิติพร้อมข้อความที่คัดลอกจากหลักฐาน - โค้ดตรวจว่ามีอยู่จริง (common/evidence_gate.py)
มิติที่ไม่มีข้อความยืนยัน = "ข้อมูลไม่พอ" (ค่าเดียวกับที่ ⑫ ข้ามตอนสร้างข้อความจับคู่ - match_supply.build_trend_matchable_text)
ข้อจำกัด: ผลคือโปรไฟล์บางลงและข้อความจับคู่สั้นลง - ดูผลต่อสินค้าที่จับคู่ได้ (⑫) ก่อน/หลังเสมอ

ไม่ import bootstrap / ไม่เรียก API เอง - เทสต์ได้ตรงๆ
"""
import json

from common.evidence_gate import (norm, numbers_supported, quotes_supported, sanitize, trend_evidence_lines,
                                  unsupported_words, verify_snippets)

NO_INFO = "ข้อมูลไม่พอ"
FIELDS = ("attribute", "functional_consequence", "psychosocial_consequence", "job_to_be_done", "point_of_difference",
          "point_of_parity")
TREND_TYPE_PRODUCT = "สินค้า"
TREND_TYPE_CHANNEL = "ช่องทาง/พฤติกรรมการซื้อ"

SYSTEM_PROMPT_SEARCH = """คุณคือนักวิเคราะห์กลยุทธ์แบรนด์ หน้าที่ของคุณคือสรุป "จุดเด่นเชิงแนวคิด" ของเทรนด์เครื่องสำอางสำหรับจับคู่กับสินค้าจริง
โดยใช้หลัก Means-End Chain, Jobs to Be Done และ Points-of-Parity/Points-of-Difference

ข้อมูลที่ให้คือ EVIDENCE: คำค้นจริงที่กำลังขึ้นใน Google (ชื่อเทรนด์เป็นป้ายที่ไปป์ไลน์ตั้ง ไม่ใช่หลักฐาน) คุณไม่มีความรู้อื่นสำหรับงานนี้

กฎ:
1. ทุกมิติต้องเขียนจากคำค้นใน EVIDENCE เท่านั้น เป็นวลีสั้นภาษาไทยที่ "สรุปสิ่งที่คำค้นแสดง" ห้ามเติมส่วนผสม เทคโนโลยี ผลลัพธ์ ความรู้สึก
   กลุ่มคน สถิติ หรือเหตุผลที่คำค้นไม่ได้บอก ห้ามคาดเดาด้วยคำว่า อาจ น่าจะ ควร ห้ามเขียนว่าผู้ค้นเตรียมตัว วางแผน หรือทำสิ่งใดเพื่อเหตุผลใด
   เว้นแต่คำค้นเองบอกคำนั้น
2. ทุกมิติแนบ "evidence" = คำค้น/วลีที่คัดลอกตรงตัวจาก EVIDENCE 1-3 ข้อ (ข้อละไม่เกิน 15 คำ ห้ามมีเครื่องหมายคำพูดคู่) ที่มิตินั้นอาศัย
3. มิติที่ EVIDENCE ไม่รองรับ ให้ตอบ "ข้อมูลไม่พอ" และ evidence เป็น [] - อย่าฝืนเขียน
4. มิติ:
   - attribute: คุณสมบัติ/ส่วนผสม/ชนิดสินค้าที่คำค้นระบุชื่อตรงๆ
   - functional_consequence: คำค้นแสดงว่าผู้ค้นอยากแก้ปัญหา/ได้ผลลัพธ์อะไร
   - psychosocial_consequence: เฉพาะเมื่อตัวคำค้นเองมีคำบอกความรู้สึกหรือการถูกมอง (เช่น มั่นใจ อาย กังวล) - ชื่องาน เหตุการณ์ คน หรือสถานที่
     ไม่นับว่าเป็นความรู้สึกหรือการถูกมอง ไม่งั้น "ข้อมูลไม่พอ"
   - job_to_be_done: สิ่งที่ผู้ค้นกำลังหาตามที่คำค้นแสดงตรงๆ และสินค้าความงาม/ดูแลตัวเองตอบได้ เช่น หาครีมกันแดดสำหรับเด็ก แก้ปัญหาผมร่วง
     ถ้าคำค้นเป็นเพียงชื่องาน ชื่อการประกวด ชื่อคน ชื่อสถานที่ ทีมกีฬา ข่าว สภาพอากาศ หรือโรค โดยไม่พูดถึงสินค้าหรือปัญหาผิว/ผม/ร่างกายที่สินค้าแก้ได้
     ให้ตอบ "ข้อมูลไม่พอ" (ห้ามเขียนว่า "ค้นหาชื่อ..." และห้ามเขียนว่าเตรียมตัว เข้าร่วม แต่งตัว หรือไปงานนั้น)
   - point_of_difference: ความต่างที่คำค้นระบุเอง (เช่น กันน้ำ ติดทน) ไม่งั้น "ข้อมูลไม่พอ"
   - point_of_parity: "ข้อมูลไม่พอ" เว้นแต่คำค้นระบุมาตรฐานพื้นฐานของสินค้า
   มิติ 2, 3, 4, 5 จะถูกใช้จับคู่กับสินค้าจริง ต้องเป็นแนวคิด/ประโยชน์ ไม่ใช่แค่ชื่อส่วนผสม
5. trend_type ตอบได้ 2 ค่า: "สินค้า" (ค่าเริ่มต้น - ใช้เมื่อคำค้นพูดถึงตัวสินค้า คุณสมบัติ ปัญหาที่สินค้าแก้ หรือเมื่อคำค้นไม่ได้พูดถึงสินค้า
   ใดๆ เลย เช่น ข่าว สภาพอากาศ โรค กีฬา การเดินทาง วันหยุด - กรณีหลังให้มิติ 2-5 เป็น "ข้อมูลไม่พอ") หรือ "ช่องทาง/พฤติกรรมการซื้อ"
   (เฉพาะเมื่อคำค้นระบุชัดว่าเป็นวิธีขาย/ซื้อ แพลตฟอร์ม ราคา โปรโมชัน โดยไม่บอกคุณสมบัติสินค้า) ถ้าเป็นช่องทาง ให้มิติ 2-5 เป็น
   "ข้อมูลไม่พอ" ทั้งหมด ห้ามเลือก "ช่องทาง/พฤติกรรมการซื้อ" เพียงเพราะคำค้นไม่เกี่ยวกับสินค้า

ตอบเป็น JSON เท่านั้น:
{
  "trend": "<ชื่อเทรนด์>",
  "trend_type": "สินค้า | ช่องทาง/พฤติกรรมการซื้อ",
  "attribute": "...", "functional_consequence": "...", "psychosocial_consequence": "...",
  "job_to_be_done": "...", "point_of_difference": "...", "point_of_parity": "...",
  "evidence": {"attribute": ["..."], "functional_consequence": ["..."], "psychosocial_consequence": [],
               "job_to_be_done": ["..."], "point_of_difference": [], "point_of_parity": []}
}"""


def build_user_content(cluster):
    """ชุดหลักฐานของเทรนด์ 1 ตัว (คำค้นจริง + พื้นที่ + หมวด Google) - ไม่มีเครื่องหมายคำพูดคู่"""
    return sanitize("\n".join(["EVIDENCE"] + trend_evidence_lines(cluster)))


def _text(value):
    return str(value).strip() if isinstance(value, str) else ""


def gate_profile(parsed, evidence_text):
    """คำตอบดิบของ LLM -> โปรไฟล์ที่ผ่านการตรวจ: มิติที่ไม่มีข้อความยืนยันที่คัดลอกจริง (หรือมีตัวเลข/คำค้นในเครื่องหมายคำพูดที่ไม่อยู่ในหลักฐาน)
    เป็น "ข้อมูลไม่พอ" - เก็บข้อความที่ตรวจผ่านไว้ใน profile["evidence"] และเหตุผลที่ตัดไว้ใน profile["_audit"]"""
    parsed = parsed if isinstance(parsed, dict) else {}
    ev_norm = norm(evidence_text)
    given = parsed.get("evidence") if isinstance(parsed.get("evidence"), dict) else {}
    profile = {"trend": parsed.get("trend"), "trend_type": str(parsed.get("trend_type") or "").replace(" ", "")}
    evidence, audit = {}, {}
    for f in FIELDS:
        value, quotes = _text(parsed.get(f)), verify_snippets(given.get(f), ev_norm)
        if not value or value == NO_INFO:
            reason = None   # LLM บอกเองว่าข้อมูลไม่พอ - ไม่ใช่การตัดของโค้ด
        elif not quotes:
            reason = "no verified quote"
        elif not (numbers_supported(value, ev_norm) and quotes_supported(value, ev_norm)):
            reason = "number or quoted search not in the evidence"
        elif unsupported_words(value, ev_norm):
            reason = "preparing / planning / feeling word not in the searches"
        else:
            reason = ""
        profile[f] = value if reason == "" else NO_INFO
        evidence[f] = quotes if reason == "" else []
        if reason:
            audit[f] = reason
    if profile["trend_type"] == TREND_TYPE_CHANNEL:   # กฎเดิมของ ⑪: ช่องทางขายไม่ใช่สินค้า - ห้ามมีประโยชน์ของสินค้าไปจับคู่
        for f in ("functional_consequence", "psychosocial_consequence", "job_to_be_done", "point_of_difference"):
            profile[f], evidence[f] = NO_INFO, []
    profile["evidence"] = evidence
    profile["_audit"] = audit
    return profile


def _terms(value):
    """รายการคำ/ข้อความคั่นด้วยจุลภาค -> list ไม่ซ้ำ คงลำดับ (ว่าง/ไม่ใช่ข้อความ = [])"""
    items = value if isinstance(value, list) else str(value or "").split(",")
    return list(dict.fromkeys(str(x).strip() for x in items if str(x).strip()))


def beauty_need(cluster):
    """🆕 (2026-10-28) "ความต้องการความงามที่ AI อนุมาน" ของเทรนด์สาย Search = ผลของขั้น ①-⑤ (phase9_search_stream: ชนิดสินค้า + ประโยชน์ + หมวดสินค้า + ทางโยง)
    ไม่ใช่สิ่งที่คำค้นบอกเอง (เช่น คำค้นเป็นมาราธอน/จักรยาน -> "sport sunscreen, sweat-proof deodorant") - ⑫ ใช้เป็นข้อความหลักจับคู่สินค้า
    (match_supply.build_trend_matchable_text) และรายงานติดป้ายว่าเป็นการอนุมาน; คืน None ถ้าไม่ใช่เทรนด์สาย Search / ไม่มีทั้งชนิดสินค้าและประโยชน์"""
    if not isinstance(cluster, dict):
        return None
    products = _terms(cluster.get("Product Keywords"))
    benefits = " ".join(str(cluster.get("Key Benefits") or "").split())
    if not products and not benefits:
        return None
    needs = list(dict.fromkeys(n.strip() for s in cluster.get("Source Themes") or [] if isinstance(s, dict)
                               for n in str(s.get("need") or "").split("/") if n.strip()))
    return {"source": "ai_inferred", "product_keywords": products, "key_benefits": benefits, "needs_th": needs,
            "link_paths": list(cluster.get("Link Paths") or []), "product_categories": list(cluster.get("Product Categories") or [])}


def matchable_fields(profile):
    """มิติที่ ⑫ ใช้จับคู่ (2-5) ที่ยังมีข้อมูล - ใช้รายงานผลก่อน/หลังเกต"""
    return [f for f in ("functional_consequence", "psychosocial_consequence", "job_to_be_done", "point_of_difference")
            if profile.get(f) and profile[f] != NO_INFO]


def parse_usable(parsed):
    """คำตอบที่ parse ได้และมี trend_type + ช่องมิติ (ใช้ตัดสินว่าต้องถามซ้ำไหม)"""
    return isinstance(parsed, dict) and "trend_type" in parsed and any(f in parsed for f in FIELDS)


def dumps(profile):
    return json.dumps(profile, ensure_ascii=False)
