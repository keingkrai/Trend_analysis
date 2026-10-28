# -*- coding: utf-8 -*-
"""
⑯ PDF Report — ข้อความต่อเทรนด์ (headline / Trend / Insight) ภาษาอังกฤษและภาษาไทย
+ คำแปลภาษาไทยของข้อความระดับรายงาน (Takeaway, STEPIC, Personas, Signals, Market summary)

ทำไมต้องมี: รายงานมี 2 ฉบับ (อังกฤษ + ไทย) แต่ข้อมูลต้นทางปนกัน - จุดเด่นเทรนด์จาก ⑪ (Means-End Chain / JTBD) เป็น
ภาษาไทย ส่วนบทวิเคราะห์จาก ⑦ ⑫ ⑭-⑮ เป็นภาษาอังกฤษ ขั้นนี้ให้ LLM เรียบเรียง/แปล **จากข้อมูลที่มีอยู่แล้วเท่านั้น**
(ห้ามเติมข้อเท็จจริง) แล้ว cache ไว้ - ฉบับอังกฤษที่ phase6_report_enrichment.json ฉบับไทยที่
phase6_report_enrichment_TH.json รันสร้าง PDF ซ้ำกี่รอบก็ไม่เรียก LLM อีก ถ้าข้อมูลต้นทางไม่เปลี่ยน

ไม่มี LLM (--no-llm / Bedrock ล้มเหลว / คำตอบไม่ผ่านการตรวจ) -> ใช้ข้อความสำรอง (fallback_texts / fallback_texts_th /
ต้นฉบับภาษาอังกฤษของข้อความระดับรายงาน) รายงานยังสร้างได้เสมอ แค่ภาษาไม่ลื่นเท่า หรือฉบับไทยมีภาษาอังกฤษปน

โมดูลนี้ไม่ import bootstrap - ผู้เรียกส่งฟังก์ชัน llm_call(system, user[, max_tokens=...]) -> str เข้ามาเอง
(เทสได้โดยไม่ยิง API)
"""
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from plain_text import PLAIN_RULES_EN, PLAIN_RULES_TH, plain_cleanup
from report_data import first_sentences, has_thai
from common.evidence_gate import norm as _evidence_norm, numbers_supported

# เปลี่ยนพรอมต์เมื่อไร ให้เพิ่มเลขของภาษานั้น - cache เดิมจะถูกคำนวณใหม่อัตโนมัติ (อยู่ใน hash)
# 🆕 (2026-10-12) ภาษาง่าย (ขั้น D): พรอมต์ทุกตัวต่อท้ายด้วยกติกาภาษาง่าย (plain_text.py) -> ทุก cache ถูกคำนวณใหม่
PROMPT_VERSION = 2
PROMPT_VERSION_TH = 3
# 🆕 (2026-10-28) ตัด "คำถามเวิร์กช็อป" (workshop_question) ออก - เจ้าของงานสั่งเอาออกจากรายงาน; cache เก่าที่มีช่องนี้ยังใช้ได้ (validate เก็บเฉพาะช่องใน FIELDS)
FIELDS = ("headline", "trend", "insight")
PROFILE_FIELDS = ("attribute", "functional_consequence", "psychosocial_consequence", "job_to_be_done",
                  "point_of_difference", "point_of_parity")
NOT_ENOUGH_DATA = "ข้อมูลไม่พอ"

SYSTEM_PROMPT = """You are the editor of an English-language consumer trend report written in the style of Trend Hunter.
You receive ONE trend: its name, English context from a forecasting pipeline, and a trend profile written in Thai
(Means-End Chain / Jobs-to-be-Done fields). Rewrite this material as clear, plain English that a non-expert understands
on first reading - do not copy the jargon of the source fields.

Rules:
- Use ONLY facts contained in the input. Do not add brands, numbers, ingredients, claims or statistics that are not in the input.
- A Thai field whose value is "ข้อมูลไม่พอ" means "not enough data" - ignore that field.
- Third person, present tense. English only. No markdown, no bullet points, no Thai characters.

Return JSON only:
{
  "headline": "one sentence, max 16 words, saying what is happening in the market",
  "trend": "2-3 sentences: what the trend is - the product attribute or technology, what it does for the user, and how it differs from ordinary products in the category",
  "insight": "2-3 sentences: why consumers want it - the job they need done, in which situation, and how the result makes them feel"
}"""

SYSTEM_PROMPT_TH = """You are the editor of a Thai-language consumer trend report written in the style of Trend Hunter,
for Thai business readers. You receive ONE trend: its name, English context from a forecasting pipeline, a trend
profile already written in Thai (Means-End Chain / Jobs-to-be-Done fields), and the English reasons why some products
match the trend. Write the report copy in plain, natural Thai that a non-expert understands on first reading -
write what it means, do not translate word for word.

Rules:
- Use ONLY facts contained in the input. Do not add brands, numbers, ingredients, claims or statistics that are not in the input.
- A Thai field whose value is "ข้อมูลไม่พอ" means "not enough data" - ignore that field.
- Keep the trend name, brand names, product names, ingredient names and technical terms (e.g. SPF, retinol, PDRN) in
  English exactly as written. Write everything else in Thai. No markdown, no bullet points.

Return JSON only:
{
  "headline": "one Thai sentence, about 20 Thai words at most, saying what is happening in the market",
  "trend": "2-3 Thai sentences: what the trend is - the product attribute or technology, what it does for the user, and how it differs from ordinary products in the category",
  "insight": "2-3 Thai sentences: why consumers want it - the job they need done, in which situation, and how the result makes them feel",
  "target": "the target consumer from the input, translated into one short Thai phrase",
  "product_reasons": ["each product match reason rewritten in plain Thai as one short sentence (not word for word) - same order and same count as the input list"]
}"""

SYSTEM_PROMPT_TH_TRANSLATE = """Rewrite the JSON values below from English into plain Thai for a business trend report read by
Thai marketing and product teams who are not data analysts. Write what each sentence means in simple Thai - do not
translate word for word.

Rules:
- Return JSON only, with exactly the same keys, nesting and list lengths as the input. Rewrite values only - never keys.
- Keep brand names, company names, product names, ingredient names, standards and technical terms (e.g. ISDIN, Puig,
  NADES, SPF, ISO 17516) in English exactly as written. Only the values of the keys "name" and "mega_trend_name" are
  labels that may stay in English; every other value - including every headline - must be written in Thai.
- Do not add or remove facts, numbers or claims. No markdown. Empty strings stay empty.
"""


def _clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


SEARCH_RULES = """Input note: this trend comes from real rising Google searches ("rising_searches"). The profile fields were checked against
those searches; a field that says ข้อมูลไม่พอ has no support.
- Describe only what the searches and the profile show. Do not describe how consumers feel, why they want something or what
  motivates them unless a profile field or a search says it. When the profile is thin, write fewer sentences (one or two per
  field is enough) instead of filling the gap.
- Say what the searches are, in their own terms: if they are names of events, shows, people or places, write "searches for
  <those names>", not searches for products, looks, tips or solutions. Say a search is for a product or a problem only when
  the search itself names it.
- Never add ingredients, claims, brands, places or numbers that are not in the input. Quote a percentage only if it appears in
  expected_search_growth_pct_vs_last_12_months."""


def is_search_trend(payload):
    """เทรนด์ของสาย Search = payload มีคำค้นจริง (rising_searches) - ใช้กติกา/การตรวจหลักฐานชุดนี้แทน"""
    return bool(payload.get("rising_searches"))


def guard_search_numbers(output, payload):
    """ข้อความต่อเทรนด์ของสาย Search: ตัวเลขหลายหลักทุกตัวต้องอยู่ในข้อมูลที่ส่งให้ LLM - ไม่อยู่ = ไม่รับ (ใช้ข้อความสำรอง) คืน output หรือ None"""
    if output is None or not is_search_trend(payload):
        return output
    evidence = _evidence_norm(json.dumps(payload, ensure_ascii=False))
    texts = [output.get(f) for f in FIELDS] + [output.get("target")]
    return output if all(numbers_supported(t, evidence) for t in texts if t) else None


# 🆕 (2026-10-28) คำบอกเหตุผล/จุดประสงค์/ผลที่ตามมา/การวางแผน/ความรู้สึก ("เพื่อเตรียมตัว", "to prepare", "because") ในข้อความต่อเทรนด์ของสาย Search - คำค้นบอกแค่ว่าค้นอะไร ไม่บอกว่าทำไมหรือเตรียมอะไร
# ตรวจช่องที่เป็นข้อความอ้างข้อเท็จจริงทุกช่อง (หัวเรื่อง / Trend / Insight / กลุ่มเป้าหมาย)
# ตัดคำค้นจริง (และข้อความในเครื่องหมายคำพูดเดี่ยว) ออกก่อนตรวจ - คำค้นอย่าง "how to fix frizzy hair" มีคำพวกนี้ได้ตามต้นฉบับ
PURPOSE_RE = {
    "en": re.compile(r"\b(in order to|so that|so (?:they|people|consumers|shoppers) can|because|due to|as a result|therefore|"
                     r"(?:to|for) prepare|prepare for|prepar(?:e|es|ing|ation) for|in preparation|get(?:ting)? ready|"
                     r"to plan|planning|plans? ahead|to (?:look|feel)|"
                     # ความรู้สึกที่คำค้นไม่ได้บอก (SEARCH_RULES ห้ามอยู่แล้วแต่ LLM ยังเขียน)
                     r"feel(?:s|ing|ings)?|confident|confidence|worr(?:y|ies|ied)|anxious|relief|peace of mind|camera-ready)\b", re.I),
    "th": re.compile(r"เพื่อ(?!น)|เตรียม|เนื่องจาก|เพราะ|ดังนั้น|จึง|ส่งผลให้|ทำให้|วางแผน|รู้สึก|มั่นใจ|กังวล|สบายใจ|วิตก"),
}
PURPOSE_FIELDS = ("headline", "trend", "insight", "target")
SEARCH_RETRY = ("\n\nYour previous answer was rejected: it says why people search, what they prepare for, how they feel or what causes what "
                "(for example 'to prepare', 'because', 'planning', 'feel confident', 'เพื่อ', 'เตรียม', 'ทำให้', 'รู้สึก'). Rewrite it and say only what the searches and the "
                "profile show.")


def _without_searches(text, searches):
    """ข้อความ - คำค้นจริงของเทรนด์ - ข้อความในเครื่องหมายคำพูดเดี่ยว (ยาวก่อน กันตัดซ้อน)"""
    for q in sorted((q for q in searches or [] if q), key=len, reverse=True):
        text = re.sub(re.escape(q), " ", text, flags=re.I)
    return re.sub(r"'[^']*'", " ", text)


def purpose_failures(output, payload):
    """ช่องของข้อความต่อเทรนด์ (สาย Search) ที่มีคำบอกเหตุผล/จุดประสงค์/ความรู้สึก/การวางแผนนอกคำค้นจริง -> list ชื่อช่อง (ว่าง = ผ่าน)"""
    if not output or not is_search_trend(payload):
        return []
    return [f for f in PURPOSE_FIELDS
            if any(rx.search(_without_searches(str(output.get(f) or ""), payload.get("rising_searches"))) for rx in PURPOSE_RE.values())]


def guard_search_purpose(output, payload):
    """ข้อความต่อเทรนด์ของสาย Search: ช่องอ้างข้อเท็จจริงที่มีคำบอกเหตุผล/จุดประสงค์ (นอกคำค้นจริง) = ไม่รับ (ถามใหม่ / ใช้ข้อความสำรอง) คืน output หรือ None"""
    if output is None or not is_search_trend(payload):
        return output
    return None if purpose_failures(output, payload) else output


def build_input(trend):
    """ข้อมูลที่ส่งให้ LLM ต่อเทรนด์ - ใช้คำนวณ hash ของ cache ด้วย (ข้อมูลเปลี่ยน = เรียกใหม่)"""
    a = trend.get("analysis") or {}
    profile = trend.get("profile") or {}
    if trend.get("rising_searches"):
        # 🆕 (2026-10-27) เทรนด์ของสาย Search: คำค้นจริง + โปรไฟล์ที่ผ่านเกตหลักฐานแล้ว (⑪) + ตัวเลขการเติบโตจากโมเดลเท่านั้น
        # ไม่ส่งข้อความตีความของ LLM ที่อื่น (ส่วนผสม/ประโยชน์/กลุ่มเป้าหมายของสาย, executive_summary / consumer_intent_signal ของ ⑭-⑮)
        # ไม่ส่งชื่อเทรนด์ (ป้ายที่ไปป์ไลน์ตั้ง เช่น "Long-Wear Occasion Beauty") - ชื่อทำให้ LLM เติมคำว่าความงาม/แต่งหน้าที่คำค้นไม่ได้พูดถึง
        return {
            "rising_searches": trend["rising_searches"],
            "context_en": {"expected_search_growth_pct_vs_last_12_months": a.get("expected_search_growth_pct") or {},
                           "target_consumer": _clean(trend.get("target"))},
            "profile_th": {k: _clean(profile.get(k)) for k in PROFILE_FIELDS
                           if profile.get(k) and NOT_ENOUGH_DATA not in _clean(profile.get(k))},
        }
    return {
        "trend_name": trend["name"],
        "context_en": {
            "executive_summary": _clean(a.get("executive_summary")),
            "consumer_intent_signal": _clean(a.get("consumer_intent_signal")),
            "key_ingredients": _clean(trend.get("key_ingredients")),
            "key_benefits": _clean(trend.get("key_benefits")),
            "target_consumer": _clean(trend.get("target")),
        },
        "profile_th": {k: _clean(profile.get(k)) for k in PROFILE_FIELDS if profile.get(k)},
    }


def build_input_th(trend):
    """เหมือน build_input + เหตุผลจับคู่สินค้า (ภาษาอังกฤษจาก ⑫) ให้แปลในการเรียกครั้งเดียวกัน"""
    return {**build_input(trend),
            "product_match_reasons_en": [_clean(p.get("reason")) for p in trend.get("products", [])]}


def input_hash(payload, version=PROMPT_VERSION):
    raw = json.dumps({"v": version, "input": payload}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate(parsed):
    """คืน dict ข้อความที่ผ่าน หรือ None - ต้องครบทุกช่องและเป็นภาษาอังกฤษล้วน"""
    if not isinstance(parsed, dict):
        return None
    out = {}
    for f in FIELDS:
        value = plain_cleanup(_clean(parsed.get(f)), "en")
        # 🆕 (2026-10-28) คำค้นภาษาไทยในเครื่องหมายคำพูดเดี่ยว ('ปากกา ลด น้ำหนัก') ยกมาตามต้นฉบับได้ในฉบับอังกฤษ
        if not value or has_thai(re.sub(r"'[^']*'", " ", value)):
            return None
        out[f] = value
    return out


def validate_th(parsed, payload):
    """ฉบับไทย: ครบทุกช่อง มีอักษรไทยจริง และเหตุผลสินค้าครบจำนวนเท่าต้นฉบับ (ลำดับเดียวกัน)"""
    if not isinstance(parsed, dict):
        return None
    out = {}
    for f in FIELDS:
        value = plain_cleanup(_clean(parsed.get(f)), "th")
        if not value or not has_thai(value):
            return None
        out[f] = value
    target = _clean(parsed.get("target"))
    if payload["context_en"]["target_consumer"] and not has_thai(target):
        return None
    out["target"] = target
    src = payload.get("product_match_reasons_en", [])
    reasons = parsed.get("product_reasons")
    if not isinstance(reasons, list) or len(reasons) != len(src):
        return None
    out["product_reasons"] = [plain_cleanup(_clean(r), "th") for r in reasons]
    if any(s and not has_thai(r) for s, r in zip(src, out["product_reasons"])):
        return None
    return out


def _sentence(text):
    """ต่อท้ายด้วยจุดถ้ายังไม่มีเครื่องหมายจบประโยค - ข้อความจาก ⑦ บางช่องไม่มีจุดท้าย พอต่อกันแล้วประโยคชนกัน"""
    text = _clean(text)
    return text if not text or text[-1] in ".!?" else f"{text}."


def fallback_texts(trend):
    """ข้อความสำรองจากภาษาอังกฤษที่มีอยู่แล้วในผล ⑦ (ไม่เรียก LLM) - ใช้เมื่อไม่มี/ไม่ผ่านผลจาก LLM"""
    if trend.get("rising_searches"):
        # 🆕 (2026-10-27) เทรนด์ของสาย Search: สำรองจากคำค้นจริงล้วน (ไม่ใช้ข้อความตีความของ ⑭-⑮)
        searches = ", ".join(trend["rising_searches"][:5])
        return {"headline": trend["name"], "trend": f"Rising searches in this trend include: {searches}.",
                "insight": _sentence(_clean(trend.get("target"))) or f"{trend['name']} is rising in Google searches."}
    a = trend.get("analysis") or {}
    summary = _clean(a.get("executive_summary"))
    headline = first_sentences(summary, 110) or trend["name"]
    trend_text = " ".join(x for x in [
        _sentence(f"Key ingredients: {trend['key_ingredients']}") if trend.get("key_ingredients") else "",
        _sentence(f"Key benefits: {trend['key_benefits']}") if trend.get("key_benefits") else "",
        _sentence(a.get("driver_explanation")),
    ] if x) or summary
    insight = " ".join(x for x in [
        _sentence(a.get("consumer_intent_signal")),
        _sentence(f"Target consumer: {trend['target']}") if trend.get("target") else "",
    ] if x) or summary
    return {"headline": headline, "trend": first_sentences(trend_text, 520),
            "insight": first_sentences(insight, 520)}


def fallback_texts_th(trend):
    """ข้อความสำรองฉบับไทย (ไม่เรียก LLM): ใช้จุดเด่นเทรนด์ภาษาไทยจาก ⑪ ตรงๆ - ⑪ ไม่มีข้อมูลเลยค่อยใช้ข้อความสำรองอังกฤษ
    กลุ่มเป้าหมายและเหตุผลจับคู่สินค้าไม่มีต้นฉบับภาษาไทย จึงคงภาษาอังกฤษไว้"""
    profile = trend.get("profile") or {}
    if trend.get("rising_searches"):
        # 🆕 (2026-10-28) เทรนด์ของสาย Search: สำรองจากคำค้นจริงล้วน - ไม่หยิบข้อความโปรไฟล์ (ช่อง "เตรียมตัว/ถูกมอง" ที่ผ่านเกต ⑪ เพราะมีคำค้นอ้างอิง
        # อาจเป็นการตีความ) มาเป็นหัวเรื่อง เพราะข้อความจาก LLM ที่มีคำบอกเหตุผลถูกตัวกัน guard_search_purpose ปฏิเสธแล้ว
        shown = ", ".join(trend["rising_searches"][:5])
        return {"headline": f"คำค้นที่กำลังขึ้นในเทรนด์นี้ เช่น {', '.join(trend['rising_searches'][:2])}",
                "trend": f"คำค้นที่กำลังขึ้นในเทรนด์นี้ ได้แก่ {shown}",
                "insight": "เป็นคำค้นที่กำลังขึ้นบน Google",
                "target": _clean(trend.get("target")),
                "product_reasons": [p.get("reason") or "" for p in trend.get("products", [])]}

    def val(key):
        v = _clean(profile.get(key))
        return "" if not v or NOT_ENOUGH_DATA in v else v

    trend_text = " ".join(x for x in (val("attribute"), val("functional_consequence"), val("point_of_difference")) if x)
    insight = " ".join(x for x in (val("job_to_be_done"), val("psychosocial_consequence")) if x)
    en = fallback_texts(trend)
    return {
        "headline": first_sentences(val("functional_consequence") or val("job_to_be_done"), 110) or en["headline"],
        "trend": first_sentences(trend_text, 520) or en["trend"],
        "insight": first_sentences(insight, 520) or en["insight"],
        "target": _clean(trend.get("target")),
        "product_reasons": [p.get("reason") or "" for p in trend.get("products", [])],
    }


def _with_rules(prompt, rules):
    """แทรกกติกาภาษาง่ายก่อนบรรทัด "Return JSON only" (ถ้าไม่มี = ต่อท้าย)"""
    head, sep, tail = prompt.partition("Return JSON only")
    if not sep:
        return prompt.rstrip() + "\n" + rules
    return head.rstrip() + "\n" + rules.strip("\n") + "\n\n" + sep + tail


SYSTEM_PROMPT = _with_rules(SYSTEM_PROMPT, PLAIN_RULES_EN)
SYSTEM_PROMPT_TH = _with_rules(SYSTEM_PROMPT_TH, PLAIN_RULES_TH)
SYSTEM_PROMPT_TH_TRANSLATE = SYSTEM_PROMPT_TH_TRANSLATE.rstrip() + "\n" + PLAIN_RULES_TH


_SPECS = {
    "en": {"prompt": SYSTEM_PROMPT, "build": build_input, "version": PROMPT_VERSION, "max_tokens": None,
           "validate": lambda parsed, payload: validate(parsed), "fallback": fallback_texts, "key": "text",
           "label": "ภาษาอังกฤษ", "invalid": "คำตอบไม่ผ่านการตรวจ (ขาดช่อง/มีภาษาไทย)"},
    "th": {"prompt": SYSTEM_PROMPT_TH, "build": build_input_th, "version": PROMPT_VERSION_TH, "max_tokens": 2500,
           "validate": validate_th, "fallback": fallback_texts_th, "key": "text_th",
           "label": "ภาษาไทย", "invalid": "คำตอบไม่ผ่านการตรวจ (ขาดช่อง/ไม่มีภาษาไทย/เหตุผลสินค้าไม่ครบ)"},
}


def _call(llm_call, system, user, max_tokens):
    # ฉบับอังกฤษเรียกแบบ 2 อาร์กิวเมนต์เหมือนเดิม (ตอบสั้น ใช้ max_tokens ค่าเริ่มต้นของผู้เรียก)
    return llm_call(system, user) if max_tokens is None else llm_call(system, user, max_tokens=max_tokens)


def enrich_trends(trends, cache, llm_call=None, parse=json.loads, refresh=False, max_workers=4, log=print, lang="en"):
    """เติมข้อความต่อเทรนด์ของภาษาที่เลือกให้ทุกเทรนด์: en -> trend["text"], th -> trend["text_th"]
    ({headline, trend, insight, source} +ฉบับไทยมี target และ product_reasons เพิ่ม)

    cache: dict จากไฟล์ cache ของภาษานั้น (หรือ {}) - แก้ไขในตัว คืนค่ากลับด้วยเพื่อให้ผู้เรียกบันทึก
    llm_call: None = ไม่เรียก LLM (ใช้ cache ที่ hash ตรงก่อน ไม่มีค่อย fallback)
    คืน (cache, สรุปจำนวนต่อแหล่ง)"""
    spec = _SPECS[lang]
    key = spec["key"]
    items = cache.setdefault("items", {})
    todo = []

    def valid(parsed, payload):
        return guard_search_purpose(guard_search_numbers(spec["validate"](parsed, payload), payload), payload)

    for t in trends:
        t.pop(key, None)
        payload = spec["build"](t)
        h = input_hash(payload, spec["version"])
        cached = items.get(t["name"])
        output = valid(cached.get("output"), payload) if cached and cached.get("input_hash") == h else None
        if output and not refresh:
            t[key] = {**output, "source": "llm (cached)"}
        else:
            todo.append((t, payload, h))

    def _one(job):
        t, payload, h = job
        search = is_search_trend(payload)
        err, partial = None, None
        for attempt in range(2 if search else 1):   # 🆕 (2026-10-28) เทรนด์ของสาย Search ถามซ้ำ 1 ครั้งพร้อมบอกเหตุที่ถูกปฏิเสธ (ข้อความมีคำบอกเหตุผล/ตัวเลขที่ไม่มีในข้อมูล)
            try:
                prompt = _with_rules(spec["prompt"], SEARCH_RULES) if search else spec["prompt"]
                content = _call(llm_call, prompt + (SEARCH_RETRY if attempt else ""), json.dumps(payload, ensure_ascii=False, indent=1),
                                spec["max_tokens"])
                if not search:
                    return t, h, valid(parse(content), payload), None
                base = guard_search_numbers(spec["validate"](parse(content), payload), payload)
                bad = purpose_failures(base, payload)
                if base and not bad:
                    return t, h, base, None
                if base:
                    partial = (base, bad)   # โครงครบ ตัวเลขผ่าน แต่บางช่องมีคำบอกเหตุผล - เก็บไว้ใช้ส่วนที่ผ่าน
            except Exception as e:  # noqa: BLE001 - เทรนด์เดียวพังต้องไม่ทำให้ทั้งรายงานพัง
                err = e
                if not search:
                    return t, h, None, e
        if partial:
            # 🆕 (2026-10-28) ถามซ้ำแล้วบางช่องยังมีคำบอกเหตุผล: ใช้ช่องที่ผ่าน + แทนเฉพาะช่องที่ไม่ผ่านด้วยข้อความสำรองจากคำค้นจริง (ดีกว่าทิ้งทั้งชุด)
            base, bad = partial
            fallback = spec["fallback"](t)
            repaired = {**base, **{f: fallback[f] for f in bad}}
            if not purpose_failures(repaired, payload):
                log(f"  ℹ️ {t['name']} ({spec['label']}): แทนช่อง {', '.join(bad)} ด้วยข้อความสำรองจากคำค้นจริง")
                return t, h, repaired, None
        return t, h, None, err

    if todo and llm_call is not None:
        log(f"  เรียบเรียงข้อความ{spec['label']}ด้วย LLM {len(todo)} เทรนด์...")
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(_one, todo))
        for t, h, output, err in results:
            if output:
                items[t["name"]] = {"input_hash": h, "output": output,
                                    "created_at": datetime.now().isoformat(timespec="seconds")}
                t[key] = {**output, "source": "llm"}
            else:
                why = f"{type(err).__name__}: {str(err)[:120]}" if err else spec["invalid"]
                log(f"  ⚠️ {t['name']} ({spec['label']}): ใช้ข้อความสำรอง - {why}")
    for t in trends:
        if key not in t:
            t[key] = {**spec["fallback"](t), "source": "fallback"}

    counts = {}
    for t in trends:
        counts[t[key]["source"]] = counts.get(t[key]["source"], 0) + 1
    cache["prompt_version"] = spec["version"]
    return cache, counts


# ============================================================================
# ย่อความหน้า Macro Forces | STEPIC และ Cross-Dimensional Signals & Outlook (2026-09-26)
# feedback: 2 หน้านี้ตัวหนังสือเยอะเกิน (STEPIC ~320 คำ, Signals ~280 คำ) - เจ้าของงานขอย่อเฉพาะ 2 หน้านี้ หน้าอื่นคงเดิม
# ย่อเป็นภาษาอังกฤษก่อน แล้วฉบับไทยแปลจากฉบับย่อ (translate_report_texts) เนื้อหาสองภาษาจึงตรงกัน
# ข้อความเต็มยังอยู่ใน phase4_stepic_*.json / phase4_master_trend_report.md เหมือนเดิม (ไม่แก้ขั้น ⑭-⑮)
# ============================================================================
PROMPT_VERSION_CONDENSE = 3   # 🆕 (2026-10-28) 2 -> 3: ผ่อนขีดจำกัดช่อง STEPIC (หน้า Macro Forces ที่รวมหน้าแล้วมีที่มากขึ้น + LLM ตอบเกินขีดเดิมบ่อยจนต้องตัดที่ประโยคแรก "…")
# จำนวนคำสูงสุดต่อช่อง (ภาษาอังกฤษ) - ตรวจด้วย validate_condensed ยอมเกินได้ CONDENSE_TOLERANCE เท่า
CONDENSE_LIMITS = {
    "stepic": {"headline": 8, "body": 26},
    "signals": {"signal": 22, "implication": 12, "outlook": 35},
}
CONDENSE_TOLERANCE = 1.25

SYSTEM_PROMPT_CONDENSE = """You edit one slide of an English consumer trend report that has too much text.
Shorten every JSON value so it stays within its word limit (given in "limits"), keeping the single most important
idea. Keep brand, company, ingredient and technical names (e.g. ISDIN, NADES, SPF, ISO) and keep numbers exactly as
written. Do not add facts. Plain English sentences, no markdown, no bullet characters.

Return JSON only, with the same keys and the same number of items as the input "content" - never include "limits":
{"items": [...], ...}"""
SYSTEM_PROMPT_CONDENSE = _with_rules(SYSTEM_PROMPT_CONDENSE, PLAIN_RULES_EN)


def _word_count(text):
    return len(_clean(text).split())


def _trim_words(text, max_words):
    """ข้อความสำรองเมื่อย่อด้วย LLM ไม่ได้: ประโยคแรก แล้วตัดที่จำนวนคำ (ต่อ "…" ถ้าตัด)"""
    text = _clean(text)
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0] if text else ""
    words = sentence.split()
    return sentence if len(words) <= max_words else " ".join(words[:max_words]).rstrip(",;:") + "…"


def build_condense_payloads(ctx):
    """{ส่วน: เนื้อหาที่จะย่อ} - stepic = 6 ช่อง (headline/body), signals = สัญญาณ 4 ข้อ + แนวโน้ม 3 เดือน"""
    payloads = {}
    if ctx.get("stepic"):
        payloads["stepic"] = {"items": [{"headline": _clean(s.get("headline")), "body": _clean(s.get("body"))}
                                        for s in ctx["stepic"]]}
    signals = [{"signal": _clean(s.get("signal")), "implication": _clean(s.get("implication"))}
               for s in (ctx.get("signals") or [])[:4]]
    outlook = _clean((ctx.get("takeaway") or {}).get("projection"))
    if signals or outlook:
        payloads["signals"] = {"items": signals, "outlook": outlook}
    return payloads


def _thai_only_from(value, source):
    """ข้อความภาษาอังกฤษที่ย่อแล้วมีอักษรไทยได้เฉพาะท่อนที่คัดจากต้นฉบับ (คำค้นภาษาไทย) - ในเครื่องหมายคำพูดเดี่ยวไม่ตรวจ"""
    rest = re.sub(r"'[^']*'", " ", value)
    return all(run.strip() in source for run in re.findall(r"[฀-๿][฀-๿ ]*", rest))


def validate_condensed(section, src, out):
    """โครงเดียวกับต้นฉบับ (คีย์/จำนวนข้อ) ทุกช่องที่ต้นฉบับมีข้อความต้องไม่ว่าง เป็นภาษาอังกฤษ และไม่เกินจำนวนคำ"""
    limits = CONDENSE_LIMITS[section]
    if not isinstance(out, dict) or not isinstance(out.get("items"), list) or len(out["items"]) != len(src["items"]):
        return None
    if "outlook" in src and not isinstance(out.get("outlook"), str):
        return None

    def ok(field, source, value):
        value = plain_cleanup(_clean(value), "en")
        if not source:
            return ""
        # 🆕 (2026-10-28) คำค้นภาษาไทย ('ทรง ผม 2026') ยกมาตามต้นฉบับได้ ทั้งในเครื่องหมายคำพูดเดี่ยวและที่ LLM ตัดเครื่องหมายออก (ท่อนไทยต้องมีอยู่ในต้นฉบับ)
        # - เดิมถูกปฏิเสธเพราะมีอักษรไทย ทำให้ย่อไม่สำเร็จเกือบทุกรอบ (ตัดที่ประโยคแรก "…")
        if not value or not _thai_only_from(value, source) or _word_count(value) > limits[field] * CONDENSE_TOLERANCE:
            return None
        return value

    items = []
    for s_item, o_item in zip(src["items"], out["items"]):
        if not isinstance(o_item, dict):
            return None
        item = {f: ok(f, s_item[f], o_item.get(f)) for f in s_item}
        if any(v is None for v in item.values()):
            return None
        items.append(item)
    result = {"items": items}
    if "outlook" in src:
        result["outlook"] = ok("outlook", src["outlook"], out.get("outlook"))
        if result["outlook"] is None:
            return None
    return result


def fallback_condensed(section, src):
    limits = CONDENSE_LIMITS[section]
    result = {"items": [{f: _trim_words(v, limits[f]) for f, v in item.items()} for item in src["items"]]}
    if "outlook" in src:
        result["outlook"] = _trim_words(src["outlook"], limits["outlook"])
    return result


def condense_report_texts(ctx, cache, llm_call=None, parse=json.loads, refresh=False, max_workers=2, log=print):
    """ย่อข้อความหน้า STEPIC และ Signals & Outlook แล้วเขียนทับใน ctx (ctx["stepic"], ctx["signals"],
    ctx["takeaway"]["projection"]) - ต้องเรียกก่อน translate_report_texts เพื่อให้ฉบับไทยแปลจากฉบับย่อ
    cache: cache ภาษาอังกฤษ (phase6_report_enrichment.json) เก็บที่คีย์ "condensed" - คืนสรุปจำนวนต่อแหล่ง"""
    store = cache.setdefault("condensed", {})
    results, todo, counts = {}, [], {}
    payloads = build_condense_payloads(ctx)
    for section, payload in payloads.items():
        h = input_hash(payload, PROMPT_VERSION_CONDENSE)
        cached = store.get(section)
        output = (validate_condensed(section, payload, cached.get("output"))
                  if cached and cached.get("input_hash") == h else None)
        if output and not refresh:
            results[section], counts["llm (cached)"] = output, counts.get("llm (cached)", 0) + 1
        else:
            todo.append((section, payload, h))

    def _one(job):
        section, payload, h = job
        request = {"limits": {f: f"max {n} words" for f, n in CONDENSE_LIMITS[section].items()}, "content": payload}
        err = None
        for _ in range(2):   # 🆕 (2026-10-28) ถามซ้ำ 1 ครั้งถ้าคำตอบไม่ผ่านการตรวจ (LLM เปลี่ยนคำตอบทุกครั้ง - เจอจริงว่าครั้งแรกตก ครั้งที่สองผ่าน)
            try:
                content = llm_call(SYSTEM_PROMPT_CONDENSE, json.dumps(request, ensure_ascii=False, indent=1),
                                   max_tokens=1500)
                parsed = parse(content)
                if isinstance(parsed, dict) and isinstance(parsed.get("content"), dict):
                    parsed = parsed["content"]  # บางครั้งโมเดลห่อคำตอบกลับมาใน "content" เหมือนคำขอ
                output = validate_condensed(section, payload, parsed)
                if output:
                    return section, h, output, None
            except Exception as e:  # noqa: BLE001 - ส่วนเดียวพังต้องไม่ทำให้ทั้งรายงานพัง
                err = e
        return section, h, None, err

    if todo and llm_call is not None:
        log(f"  ย่อข้อความหน้า STEPIC / Signals ด้วย LLM {len(todo)} ส่วน...")
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for section, h, output, err in pool.map(_one, todo):
                if output:
                    store[section] = {"input_hash": h, "output": output,
                                      "created_at": datetime.now().isoformat(timespec="seconds")}
                    results[section], counts["llm"] = output, counts.get("llm", 0) + 1
                else:
                    why = f"{type(err).__name__}: {str(err)[:120]}" if err else "คำตอบยาวเกิน/โครงไม่ตรง"
                    log(f"  ⚠️ ย่อส่วน {section} ไม่สำเร็จ: ตัดที่ประโยคแรกแทน - {why}")
    for section, payload in payloads.items():
        if section not in results:
            results[section] = fallback_condensed(section, payload)
            counts["trimmed (fallback)"] = counts.get("trimmed (fallback)", 0) + 1

    for tile, short in zip(ctx.get("stepic") or [], (results.get("stepic") or {}).get("items", [])):
        if not tile.get("no_data"):   # 🆕 (2026-10-27) "No data" ใช้ข้อความตายตัวของ report_data/i18n ไม่ให้ LLM เรียบเรียงใหม่
            tile.update(short)
    if "signals" in results:
        for sig, short in zip(ctx.get("signals") or [], results["signals"]["items"]):
            sig.update(short)
        if results["signals"].get("outlook"):
            ctx["takeaway"]["projection"] = results["signals"]["outlook"]
    return counts


# ============================================================================
# คำแปลภาษาไทยของข้อความระดับรายงาน (ไม่ผูกกับเทรนด์ไหน) - แยกเรียกทีละส่วน (ส่วนละครั้ง) cache แยกส่วน
# ============================================================================
def build_report_payloads(ctx):
    """ข้อความภาษาอังกฤษระดับรายงานที่ฉบับไทยต้องแปล -> {ส่วน: dict} (ส่วนที่ไม่มีข้อความจะไม่อยู่ในผล)
    ลิสต์ห่อด้วย {"items": [...]} เพราะ LLM ต้องตอบเป็น JSON object"""
    payloads = {}
    takeaway = {k: _clean(v) for k, v in (ctx.get("takeaway") or {}).items() if _clean(v)}
    if takeaway:
        payloads["takeaway"] = takeaway
    summary = _clean(((ctx.get("overview") or {}).get("market") or {}).get("summary"))
    if summary:
        payloads["market"] = {"summary": summary}
    if ctx.get("stepic"):
        payloads["stepic"] = {"items": [{"headline": _clean(s.get("headline")), "body": _clean(s.get("body"))}
                                        for s in ctx["stepic"]]}
    if ctx.get("personas"):
        payloads["personas"] = {"items": [{k: _clean(p.get(k)) for k in
                                           ("name", "description", "value_driver", "channel_preference")}
                                          for p in ctx["personas"][:3]]}
    if ctx.get("signals"):
        payloads["signals"] = {"items": [{k: _clean(s.get(k)) for k in ("signal", "implication")}
                                         for s in ctx["signals"][:4]]}
    return payloads


# ============================================================================
# 🆕 (2026-10-12) ข้อความระดับรายงานฉบับอังกฤษเป็นภาษาง่าย (ขั้น D): takeaway / market summary / personas มาจาก ⑭-⑮ ตรงๆ (ไม่เคยผ่าน
# LLM ของรายงานนี้) - STEPIC และ Signals ถูกย่อแบบภาษาง่ายใน condense_report_texts อยู่แล้ว จึงไม่ทำซ้ำ ต้องเรียกก่อน translate_report_texts
# (ฉบับไทยเขียนใหม่จากฉบับอังกฤษที่ง่ายแล้ว) cache ภาษาอังกฤษ คีย์ "plain_en"
# ============================================================================
PROMPT_VERSION_PLAIN_EN = 1
PLAIN_EN_SECTIONS = ("takeaway", "market", "personas")
PLAIN_EN_KEEP = {"mega_trend_name", "name"}   # ชื่อเรียก (mega trend / persona) คงตามเดิม - ถูกอ้างต่อใน heatmap แรงขับ/persona
PLAIN_EN_MAX_GROWTH = 2.0                      # ยาวกว่าต้นฉบับเกินกี่เท่า (+12 คำ) = ไม่รับ (กันบวมเป็นคำอธิบายใหม่; ประโยคยาวที่ถูกแตกเป็นประโยคสั้นยาวขึ้นได้)

SYSTEM_PROMPT_PLAIN_EN = """You edit the report-level text of an English consumer trend report so that a non-expert reads
it easily. Rewrite every JSON value in plain English with the same meaning and the same facts - shorter sentences,
everyday words, no jargon. Do not merge, drop or reorder items.

Rules:
- Return JSON only, with exactly the same keys, nesting and list lengths as the input. Rewrite values only - never keys.
- Keep names (trend, persona and mega-trend names), brands, ingredients, standards and every number exactly as written.
- Do not add facts, claims or advice that are not in the input. No markdown, no bullet characters.
""" + PLAIN_RULES_EN


def validate_plain_en(src, out, key=None):
    """โครงเดียวกับต้นฉบับ, ภาษาอังกฤษล้วน, ชื่อเรียกคงเดิม, ไม่ว่างเมื่อต้นฉบับไม่ว่าง, ไม่ยาวเกินกำหนด -> ข้อความที่ผ่าน หรือ None"""
    if isinstance(src, dict):
        if not isinstance(out, dict) or set(out) != set(src):
            return None
        cleaned = {k: validate_plain_en(v, out[k], k) for k, v in src.items()}
        return None if any(v is None for v in cleaned.values()) else cleaned
    if isinstance(src, list):
        if not isinstance(out, list) or len(out) != len(src):
            return None
        cleaned = [validate_plain_en(s_, o, key) for s_, o in zip(src, out)]
        return None if any(v is None for v in cleaned) else cleaned
    source = _clean(src)
    if key in PLAIN_EN_KEEP:
        return source
    text = plain_cleanup(_clean(out), "en") if isinstance(out, str) else None
    if text is None or (source and (not text or has_thai(text))):
        return None
    if source and _word_count(text) > PLAIN_EN_MAX_GROWTH * _word_count(source) + 12:
        return None
    return text


def plain_report_texts_en(ctx, cache, llm_call=None, parse=json.loads, refresh=False, max_workers=3, log=print):
    """เขียน takeaway / market summary / personas ฉบับอังกฤษใหม่เป็นภาษาง่าย แล้วเขียนทับใน ctx - คืนสรุปจำนวนต่อแหล่ง
    ไม่มี LLM / ไม่ผ่านการตรวจ = คงต้นฉบับ (ไม่ error)"""
    store = cache.setdefault("plain_en", {})
    results, todo, counts = {}, [], {}
    payloads = {k: v for k, v in build_report_payloads(ctx).items() if k in PLAIN_EN_SECTIONS}
    for section, payload in payloads.items():
        h = input_hash(payload, PROMPT_VERSION_PLAIN_EN)
        cached = store.get(section)
        output = validate_plain_en(payload, cached.get("output")) if cached and cached.get("input_hash") == h else None
        if output and not refresh:
            results[section], counts["llm (cached)"] = output, counts.get("llm (cached)", 0) + 1
        else:
            todo.append((section, payload, h))

    def _one(job):
        section, payload, h = job
        err = None
        for _attempt in range(TRANSLATE_ATTEMPTS):   # ผลของ LLM ต่างกันได้ในแต่ละครั้ง - ถามซ้ำ 1 ครั้งเมื่อคำตอบไม่ผ่านการตรวจ
            try:
                content = llm_call(SYSTEM_PROMPT_PLAIN_EN, json.dumps(payload, ensure_ascii=False, indent=1), max_tokens=3000)
                output = validate_plain_en(payload, parse(content))
                if output:
                    return section, h, output, None
            except Exception as e:  # noqa: BLE001 - ส่วนเดียวพังต้องไม่ทำให้ทั้งรายงานพัง
                err = e
        return section, h, None, err

    if todo and llm_call is not None:
        log(f"  เขียนข้อความระดับรายงาน (อังกฤษ) เป็นภาษาง่ายด้วย LLM {len(todo)} ส่วน...")
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for section, h, output, err in pool.map(_one, todo):
                if output:
                    store[section] = {"input_hash": h, "output": output,
                                      "created_at": datetime.now().isoformat(timespec="seconds")}
                    results[section], counts["llm"] = output, counts.get("llm", 0) + 1
                else:
                    why = f"{type(err).__name__}: {str(err)[:120]}" if err else "คำตอบไม่ผ่านการตรวจ (โครงไม่ตรง/ยาวเกิน/มีภาษาไทย)"
                    log(f"  ⚠️ ส่วน {section}: ใช้ข้อความเดิม - {why}")
    if "takeaway" in results:
        for k, v in results["takeaway"].items():
            if k in ctx.get("takeaway", {}):
                ctx["takeaway"][k] = v
    if "market" in results:
        ctx["overview"]["market"]["summary"] = results["market"]["summary"]
    if "personas" in results:
        for persona, new in zip(ctx.get("personas") or [], results["personas"]["items"]):
            persona.update(new)
    n_keep = len(payloads) - len(results)
    if n_keep > 0:
        counts["original (fallback)"] = n_keep
    return counts


# ช่องที่เป็น "ชื่อเรียก" (เช่น "The Clinical Bio-Convergence", "The Evidence-First Curator") - LLM มักคงเป็นภาษาอังกฤษ
# แบบชื่อเฉพาะ ซึ่งยอมรับได้ ช่องนี้จึงไม่บังคับให้มีอักษรไทย (ช่องอื่นบังคับ) - เจอจริงรอบ 082438: takeaway ถูกตีตก
# ทั้งส่วนเพราะชื่อ mega trend ไม่ได้แปล
NAME_FIELDS = {"mega_trend_name", "name"}
TRANSLATE_ATTEMPTS = 2   # 🆕 (2026-10-12) ถามซ้ำ 1 ครั้งเมื่อคำตอบไม่ผ่านการตรวจ (เช่น หัวข้อยังเป็นอังกฤษ) - ผลของ LLM ต่างกันได้ในแต่ละครั้ง


def validate_same_shape(src, out, key=None):
    """คำแปลต้องโครงเดียวกับต้นฉบับทุกชั้น (คีย์เดิม, ลิสต์ยาวเท่าเดิม) และทุกข้อความที่ต้นฉบับไม่ว่างต้องมีอักษรไทย
    (ยกเว้นช่องชื่อเรียกใน NAME_FIELDS) คืนคำแปลที่เก็บกวาดช่องว่างแล้ว หรือ None ถ้าไม่ผ่าน"""
    if isinstance(src, dict):
        if not isinstance(out, dict) or set(out) != set(src):
            return None
        cleaned = {k: validate_same_shape(v, out[k], k) for k, v in src.items()}
        return None if any(v is None for v in cleaned.values()) else cleaned
    if isinstance(src, list):
        if not isinstance(out, list) or len(out) != len(src):
            return None
        cleaned = [validate_same_shape(s, o, key) for s, o in zip(src, out)]
        return None if any(v is None for v in cleaned) else cleaned
    text = plain_cleanup(_clean(out), "th") if isinstance(out, str) else None
    if text is None or (_clean(src) and not text):
        return None
    if _clean(src) and key not in NAME_FIELDS and not has_thai(text):
        return None
    return text


def translate_report_texts(ctx, cache, llm_call=None, parse=json.loads, refresh=False, max_workers=4, log=print):
    """แปลข้อความระดับรายงานเป็นภาษาไทย -> (คำแปล {ส่วน: dict}, cache, สรุปจำนวนต่อแหล่ง)
    ส่วนที่แปลไม่ได้จะไม่อยู่ในคำแปล - i18n.localize ใช้ต้นฉบับภาษาอังกฤษแทน (ฉบับไทยมีภาษาอังกฤษปนเฉพาะส่วนนั้น)"""
    store = cache.setdefault("report", {})
    translations, todo, counts = {}, [], {}
    for section, payload in build_report_payloads(ctx).items():
        h = input_hash(payload, PROMPT_VERSION_TH)
        cached = store.get(section)
        output = validate_same_shape(payload, cached.get("output")) if cached and cached.get("input_hash") == h else None
        if output and not refresh:
            translations[section] = output
            counts["llm (cached)"] = counts.get("llm (cached)", 0) + 1
        else:
            todo.append((section, payload, h))

    def _one(job):
        section, payload, h = job
        err = None
        for _attempt in range(TRANSLATE_ATTEMPTS):
            try:
                content = llm_call(SYSTEM_PROMPT_TH_TRANSLATE, json.dumps(payload, ensure_ascii=False, indent=1),
                                   max_tokens=4000)
                output = validate_same_shape(payload, parse(content))
                if output:
                    return section, h, output, None
            except Exception as e:  # noqa: BLE001 - ส่วนเดียวพังต้องไม่ทำให้ทั้งรายงานพัง
                err = e
        return section, h, None, err

    if todo and llm_call is not None:
        log(f"  แปลข้อความระดับรายงานเป็นภาษาไทยด้วย LLM {len(todo)} ส่วน...")
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(_one, todo))
        for section, h, output, err in results:
            if output:
                store[section] = {"input_hash": h, "output": output,
                                  "created_at": datetime.now().isoformat(timespec="seconds")}
                translations[section] = output
                counts["llm"] = counts.get("llm", 0) + 1
            else:
                why = f"{type(err).__name__}: {str(err)[:120]}" if err else "คำตอบไม่ผ่านการตรวจ (โครงไม่ตรง/ไม่มีภาษาไทย)"
                log(f"  ⚠️ ส่วน {section}: ใช้ต้นฉบับภาษาอังกฤษ - {why}")
    n_fallback = len(todo) - counts.get("llm", 0)
    if n_fallback:
        counts["english (fallback)"] = n_fallback
    return translations, cache, counts


# ============================================================================
# ⑰ รายงานแบรนด์: แปลรายการข้อความภาษาอังกฤษเป็นภาษาไทยเป็นกลุ่ม (เช่น เหตุผลจับคู่สินค้าของแบรนด์ต่อเทรนด์)
# ============================================================================
def translate_items_th(groups, cache, llm_call=None, parse=json.loads, refresh=False, max_workers=4, log=print,
                       label="ข้อความ"):
    """{คีย์: [ข้อความภาษาอังกฤษ, ...]} -> ({คีย์: [คำแปลภาษาไทย, ...]}, cache, สรุปจำนวนต่อแหล่ง)
    เรียก LLM กลุ่มละ 1 ครั้ง (พรอมต์/ตัวตรวจเดียวกับ translate_report_texts) cache ที่ cache["items"][คีย์]
    กลุ่มที่แปลไม่สำเร็จจะไม่อยู่ในผล - ผู้เรียกใช้ต้นฉบับภาษาอังกฤษแทน"""
    store = cache.setdefault("items", {})
    translations, todo, counts = {}, [], {}
    for key, texts in groups.items():
        payload = {"items": [_clean(t) for t in texts]}
        h = input_hash(payload, PROMPT_VERSION_TH)
        cached = store.get(key)
        output = validate_same_shape(payload, cached.get("output")) if cached and cached.get("input_hash") == h else None
        if output and not refresh:
            translations[key] = output["items"]
            counts["llm (cached)"] = counts.get("llm (cached)", 0) + 1
        else:
            todo.append((key, payload, h))

    def _one(job):
        key, payload, h = job
        err = None
        for _attempt in range(TRANSLATE_ATTEMPTS):
            try:
                content = llm_call(SYSTEM_PROMPT_TH_TRANSLATE, json.dumps(payload, ensure_ascii=False, indent=1),
                                   max_tokens=2500)
                output = validate_same_shape(payload, parse(content))
                if output:
                    return key, h, output, None
            except Exception as e:  # noqa: BLE001 - กลุ่มเดียวพังต้องไม่ทำให้ทั้งรายงานพัง
                err = e
        return key, h, None, err

    if todo and llm_call is not None:
        log(f"  แปล{label}เป็นภาษาไทยด้วย LLM {len(todo)} กลุ่ม...")
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for key, h, output, err in pool.map(_one, todo):
                if output:
                    store[key] = {"input_hash": h, "output": output,
                                  "created_at": datetime.now().isoformat(timespec="seconds")}
                    translations[key] = output["items"]
                    counts["llm"] = counts.get("llm", 0) + 1
                else:
                    why = f"{type(err).__name__}: {str(err)[:120]}" if err else "คำตอบไม่ผ่านการตรวจ (จำนวนไม่ตรง/ไม่มีภาษาไทย)"
                    log(f"  ⚠️ {key}: ใช้ต้นฉบับภาษาอังกฤษ - {why}")
    n_fallback = len(todo) - counts.get("llm", 0)
    if n_fallback:
        counts["english (fallback)"] = n_fallback
    return translations, cache, counts


# ============================================================================
# Means-End 3 บรรทัดสั้นแทนย่อหน้า Trend/Insight ในหน้าเทรนด์ (feedback 2026-09-28: เปลี่ยนตัวหนังสือเป็นภาพ/ข้อความสั้น)
# ย่อจากโปรไฟล์ ⑪ (ภาษาไทย) ครั้งเดียวได้ทั้งอังกฤษและไทย - เนื้อหาสองฉบับจึงตรงกัน cache ที่ไฟล์ภาษาอังกฤษ คีย์ "ladder"
# ไม่มี LLM/ไม่ผ่านการตรวจ -> ไม่เติม (หน้าเทรนด์ใช้ย่อหน้า Trend/Insight เดิม)
# ============================================================================
PROMPT_VERSION_LADDER = 2
# บรรทัด -> ช่องต้นทางในโปรไฟล์ ⑪
LADDER_SOURCES = {"difference": "point_of_difference", "benefit": "functional_consequence",
                  "feeling": "psychosocial_consequence"}
LADDER_MAX_WORDS_EN = 14
LADDER_MAX_CHARS_TH = 90   # ภาษาไทยไม่เว้นวรรคระหว่างคำ นับตัวอักษรแทน (~20 คำ)

SYSTEM_PROMPT_LADDER = """You shorten ONE consumer-trend profile (a Means-End Chain written in Thai) into three short
lines for a presentation slide, in English and in Thai.
  difference = what makes products in this trend different from ordinary products (from point_of_difference)
  benefit    = what the product does for the user (from functional_consequence)
  feeling    = how the result makes the consumer feel (from psychosocial_consequence)

Rules:
- Use ONLY facts in the input. Do not add brands, numbers, ingredients or claims.
- Keep brand, ingredient and technical names (e.g. SPF, retinol, NADES) in English in both languages.
- English lines: at most 14 words, English only. Thai lines: at most about 20 Thai words, natural Thai.
- Short phrases, no final period, no markdown.
- If a source field is missing or says "ข้อมูลไม่พอ", return "" for that line in both languages.

Return JSON only:
{"en": {"difference": "", "benefit": "", "feeling": ""}, "th": {"difference": "", "benefit": "", "feeling": ""}}"""
SYSTEM_PROMPT_LADDER = _with_rules(SYSTEM_PROMPT_LADDER.replace("- Short phrases, no final period, no markdown.",
    "- Short phrases, no final period, no markdown. Thai lines also use everyday Thai words (no transliterated technical terms)."),
    PLAIN_RULES_EN)


def build_ladder_input(trend):
    """โปรไฟล์ ⑪ ที่ใช้ย่อ (เฉพาะช่องที่มีข้อมูลจริง) - ไม่มีทั้ง 3 ช่องต้นทาง -> None (ไม่ต้องเรียก LLM)"""
    profile = trend.get("profile") or {}
    fields = {src: _clean(profile.get(src)) for src in LADDER_SOURCES.values()}
    fields = {k: v for k, v in fields.items() if v and NOT_ENOUGH_DATA not in v}
    if not fields:
        return None
    context = {k: _clean(profile.get(k)) for k in ("attribute", "job_to_be_done")
               if _clean(profile.get(k)) and NOT_ENOUGH_DATA not in _clean(profile.get(k))}
    return {"trend_name": trend["name"], "profile_th": fields, "context_th": context}


def validate_ladder(parsed, payload):
    """ทั้ง 2 ภาษาต้องมีครบทุกบรรทัดที่ต้นทางมีข้อมูล (ต้นทางไม่มี -> บังคับเป็น "") อังกฤษไม่มีอักษรไทยและไม่เกิน
    จำนวนคำ ไทยต้องมีอักษรไทยและไม่ยาวเกิน - คืน {"en": {...}, "th": {...}} หรือ None"""
    if not isinstance(parsed, dict):
        return None
    out = {}
    for lang in ("en", "th"):
        block = parsed.get(lang)
        if not isinstance(block, dict):
            return None
        lines = {}
        for line, src in LADDER_SOURCES.items():
            value = plain_cleanup(_clean(block.get(line)).rstrip("."), lang)
            if src not in payload["profile_th"]:
                lines[line] = ""
                continue
            if not value:
                return None
            if lang == "en" and (has_thai(value) or _word_count(value) > LADDER_MAX_WORDS_EN * CONDENSE_TOLERANCE):
                return None
            if lang == "th" and (not has_thai(value) or len(value) > LADDER_MAX_CHARS_TH * CONDENSE_TOLERANCE):
                return None
            lines[line] = value
        out[lang] = lines
    return out


def condense_means_end(trends, cache, llm_call=None, parse=json.loads, refresh=False, max_workers=4, log=print):
    """เติม t["ladder"] (อังกฤษ) และ t["ladder_th"] (ไทย) = {difference, benefit, feeling} ให้เทรนด์ที่ได้ผล
    cache: cache ภาษาอังกฤษ คีย์ "ladder" - คืนสรุปจำนวนต่อแหล่ง"""
    store = cache.setdefault("ladder", {})
    todo, counts = [], {}

    def apply(t, output, source):
        t["ladder"], t["ladder_th"] = output["en"], output["th"]
        counts[source] = counts.get(source, 0) + 1

    for t in trends:
        t.pop("ladder", None)
        t.pop("ladder_th", None)
        payload = build_ladder_input(t)
        if payload is None:
            continue
        h = input_hash(payload, PROMPT_VERSION_LADDER)
        cached = store.get(t["name"])
        output = validate_ladder(cached.get("output"), payload) if cached and cached.get("input_hash") == h else None
        if output and not refresh:
            apply(t, output, "llm (cached)")
        else:
            todo.append((t, payload, h))

    def _one(job):
        t, payload, h = job
        try:
            content = llm_call(SYSTEM_PROMPT_LADDER, json.dumps(payload, ensure_ascii=False, indent=1), max_tokens=900)
            return t, h, validate_ladder(parse(content), payload), None
        except Exception as e:  # noqa: BLE001 - เทรนด์เดียวพังต้องไม่ทำให้ทั้งรายงานพัง
            return t, h, None, e

    if todo and llm_call is not None:
        log(f"  ย่อ Means-End เป็น 3 บรรทัดด้วย LLM {len(todo)} เทรนด์...")
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for t, h, output, err in pool.map(_one, todo):
                if output:
                    store[t["name"]] = {"input_hash": h, "output": output,
                                        "created_at": datetime.now().isoformat(timespec="seconds")}
                    apply(t, output, "llm")
                else:
                    why = f"{type(err).__name__}: {str(err)[:120]}" if err else "คำตอบยาวเกิน/ขาดบรรทัด/ภาษาไม่ตรง"
                    log(f"  ⚠️ {t['name']}: ใช้ย่อหน้า Trend/Insight เดิม - {why}")
    n_para = len(trends) - sum(counts.values())
    if n_para:
        counts["paragraphs (fallback)"] = n_para
    return counts
