# -*- coding: utf-8 -*-
"""
ภาษาง่ายสำหรับข้อความที่ LLM เขียนในรายงาน ⑯/⑰/⑱ (🆕 2026-10-12 ขั้น D ของแผนภาษาง่าย)

มี 3 อย่าง (ฟังก์ชันล้วน ไม่ import bootstrap/API):
1) PLAIN_RULES_EN / PLAIN_RULES_TH - กติกาที่ต่อท้ายพรอมต์ของ enrich.py ทุกจุดที่ LLM เขียนข้อความให้คนอ่าน
2) plain_cleanup(text, lang) - แทนศัพท์เฉพาะที่หลุดมาด้วยคำธรรมดาแบบตายตัว (ไม่แตะตัวเลข/ความหมาย) ใช้กับผล LLM และเหตุผลจับคู่เดิม
3) find_banned(text, lang) - ตรวจคำต้องห้ามที่ยังเหลือ (สคริปต์ตรวจภาษา ขั้น E ใช้ชุดเดียวกัน)

ตั้งใจไม่แก้ "YoY" / "accelerating to X%" ด้วยการแทนคำ - เป็นเรื่องความหมายของตัวเลข ให้พรอมต์ห้ามและตัวตรวจจับ
"""
import re

PLAIN_RULES_EN = """
Plain-language rules - the readers are brand, marketing and product people, not data analysts or scientists:
- Write short sentences (about 20 words at most), one idea each. Lead with what is happening or what it means for a brand.
- Use everyday words. Say "AI" not "language model"; "products" not "SKUs"; "goal" or "need" not "job-to-be-done";
  "key difference" not "point of difference"; "match" not "similarity"; "search interest" not "search volume index".
  Never use: YoY, CAGR, momentum, cohort, synergy, leverage, holistic, paradigm, ecosystem, multi-modal.
- Keep ingredient, brand, company and product names and standards (e.g. SPF, retinol, PDRN) exactly as written. Do not
  explain a term unless the input already explains it. Never add facts.
- Every percentage is an expected change in search interest compared with the last 12 months, cumulative for the period
  shown. Never call it "YoY", "per year", "growth rate" or "accelerating to X%". Keep every number and unit exactly as given.
- Do not reverse or soften a comparison. If the input says A differs from ordinary products because of B, say exactly that.
- Example of the style wanted: instead of "Leveraging multi-modal bio-convergence to optimise dermal barrier outcomes" write
  "Products that combine two repair ingredients to make the skin barrier stronger".
"""

PLAIN_RULES_TH = """
Plain-language rules for the Thai copy - the readers are Thai brand, marketing and product people, not data analysts or scientists:
- Write Thai that is understood at first reading: short sentences (about 25 Thai words at most), one idea each. Lead with
  what is happening or what it means for a brand. Use everyday words and do not stack long noun phrases.
- Never transliterate a technical term into Thai sounds. Keep the English term (e.g. PDRN, retinol, SPF, NADES) or, if the
  input already contains the Thai word, reuse it.
- Say "AI" not "โมเดลภาษา"; "ชิ้น" or "รายการสินค้า" not "SKU"; "สิ่งที่ผู้บริโภคต้องการให้สำเร็จ" not "Job to be done";
  "ตรงกับเทรนด์" not "similarity". Never use YoY, CAGR, momentum, cohort.
- Every percentage is an expected change in search interest compared with the last 12 months (cumulative for the period
  shown). Never call it "YoY", "ต่อปี" or "เร่งตัวเป็น X%". Keep every number and unit exactly as given.
- Do not reverse or soften a comparison: if the source says A differs from ordinary products because of B, keep that direction.
- Example of the style wanted: instead of "การบูรณาการเทคโนโลยีชีวภาพหลายรูปแบบเพื่อยกระดับสมรรถนะของเกราะป้องกันผิว" write
  "ผลิตภัณฑ์ที่รวมสารบำรุง 2 ชนิดไว้ด้วยกัน เพื่อให้เกราะป้องกันผิวแข็งแรงขึ้น".
"""

# แทนที่ตายตัว (ไม่แตะตัวเลข) - (รูปแบบ regex, คำที่ใช้แทน) ตัวพิมพ์ใหญ่ต้นประโยคคงไว้
_CLEANUP = {
    "en": [
        (re.compile(r"\bcosine similarity\b", re.I), "match score"),
        (re.compile(r"\bjobs?[- ]to[- ]be[- ]done\b", re.I), "goal"),
        (re.compile(r"\bpoints? of difference\b", re.I), "key difference"),
        (re.compile(r"\blanguage[- ]models?\b", re.I), "AI"),
        (re.compile(r"\bSKUs\b"), "products"),
        (re.compile(r"\bSKU\b"), "product"),
        (re.compile(r"\bsimilarity\b", re.I), "match"),
        (re.compile(r"\bholistic\b", re.I), "all-round"),   # 🆕 (2026-10-14) "holistic health support" -> "all-round health support"
    ],
    "th": [
        (re.compile(r"โมเดลภาษา"), "AI"),
        (re.compile(r"\bSKUs?\b"), "ชิ้น"),
        (re.compile(r"\bJobs?[- ]to[- ]be[- ]done\b", re.I), "สิ่งที่ผู้บริโภคต้องการให้สำเร็จ"),
        (re.compile(r"\bJTBD\b"), "สิ่งที่ผู้บริโภคต้องการให้สำเร็จ"),
        (re.compile(r"\bcosine similarity\b", re.I), "คะแนนความตรงเทรนด์"),
    ],
}

# คำต้องห้ามในข้อความหน้าหลัก (ตรวจหลังแทนที่แล้ว) - ชุดเดียวกับสคริปต์ตรวจภาษา
_BANNED = {
    "en": [r"\bYoY\b", r"\bCAGR\b", r"\bmomentum\b", r"\bcohort\b", r"\bsynergy\b", r"\bholistic\b", r"\bparadigm\b",
           r"\blanguage[- ]model", r"\bjobs?[- ]to[- ]be[- ]done\b", r"\bpoints? of difference\b", r"\bSKUs?\b",
           r"\bsimilarity\b", r"\bcosine\b", r"\bembedding\b", r"accelerating to", r"⑪|⑫|⑬|⑭|⑮"],
    "th": [r"\bYoY\b", r"\bCAGR\b", r"\bmomentum\b", r"โมเดลภาษา", r"\bSKUs?\b", r"\bJob", r"\bJTBD\b", r"\bcosine\b",
           r"\bembedding\b", r"\bsimilarity\b", r"เร่งตัวเป็น", r"⑪|⑫|⑬|⑭|⑮", r"Run ID"],
}
_BANNED_RE = {lang: [re.compile(p, re.I) for p in pats] for lang, pats in _BANNED.items()}


def _keep_case(match, replacement):
    """ต้นประโยค (ตัวแรกใหญ่ ตัวที่สองเล็ก เช่น "Job", "Language") คงตัวพิมพ์ใหญ่; ตัวย่อ (SKU, SKUs) ไม่นับ - แทนด้วยตัวเล็กตามปกติ"""
    word = match.group(0)
    title_case = word[:1].isupper() and not word[1:2].isupper()
    return replacement[:1].upper() + replacement[1:] if title_case and replacement[:1].islower() else replacement


_THAI_RE = re.compile("[\u0E00-\u0E7F]")
_AI_ATTACHED = re.compile("(?<=[\u0E00-\u0E7F])AI|AI(?=[\u0E00-\u0E7F])")


def _space_latin_th(text):
    """"ใช้AIเทียบ" -> "ใช้ AI เทียบ" (คำที่แทนด้วย AI ติดอักษรไทย - ไทยไม่เว้นวรรค ต้องเว้นรอบคำอังกฤษเอง)"""
    return re.sub(r"\s{2,}", " ", _AI_ATTACHED.sub(lambda m: " AI " if m.group(0) == "AI" else m.group(0), text)).strip()


_A_AI = re.compile(r"\b([Aa]) (AI)\b")
_AN_WORD = re.compile(r"\b([Aa])n (products?|match(?:es)?|goals?|key difference|match score)\b")


def _fix_articles(text):
    """หลังแทนคำ: "a language model" -> "a AI" ต้องเป็น "an AI"; "an SKU" -> "an product" ต้องเป็น "a product" """
    text = _A_AI.sub(lambda m: m.group(1) + "n AI", text)
    return _AN_WORD.sub(lambda m: m.group(1) + " " + m.group(2), text)


def plain_cleanup(text, lang):
    """แทนศัพท์เฉพาะที่หลุดมาด้วยคำธรรมดา - lang "en" / "th"; ไม่ใช่ข้อความ/ไม่มีอะไรต้องแก้ = คืนค่าเดิม"""
    if not isinstance(text, str) or not text:
        return text
    changed = False
    for pattern, replacement in _CLEANUP.get(lang, ()):
        text, n = pattern.subn(lambda m, r=replacement: _keep_case(m, r), text)
        changed = changed or n > 0
    if changed and lang == "th":
        text = _space_latin_th(text)
    if changed and lang == "en":
        text = _fix_articles(text)
    return text


def find_banned(text, lang):
    """คำต้องห้ามที่พบในข้อความ (ไม่ซ้ำ ตามลำดับที่พบ) - ลิสต์ว่าง = ผ่าน"""
    if not isinstance(text, str):
        return []
    hits = sorted((m.start(), m.group(0)) for pattern in _BANNED_RE.get(lang, ()) for m in pattern.finditer(text))
    found = []
    for _, word in hits:
        if word.lower() not in (x.lower() for x in found):
            found.append(word)
    return found


def cleanup_deep(obj, lang):
    """plain_cleanup กับทุกสตริงในโครงสร้าง dict/list (คืนโครงสร้างใหม่ ไม่แก้ของเดิม) - ใช้กับผล LLM ทั้งก้อน"""
    if isinstance(obj, str):
        return plain_cleanup(obj, lang)
    if isinstance(obj, list):
        return [cleanup_deep(x, lang) for x in obj]
    if isinstance(obj, dict):
        return {k: cleanup_deep(v, lang) for k, v in obj.items()}
    return obj
