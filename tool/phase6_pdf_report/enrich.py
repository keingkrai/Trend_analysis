# -*- coding: utf-8 -*-
"""
⑯ PDF Report — ข้อความต่อเทรนด์ (headline / Trend / Insight / Workshop Question) ภาษาอังกฤษและภาษาไทย
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

from report_data import first_sentences, has_thai

# เปลี่ยนพรอมต์เมื่อไร ให้เพิ่มเลขของภาษานั้น - cache เดิมจะถูกคำนวณใหม่อัตโนมัติ (อยู่ใน hash)
PROMPT_VERSION = 1
PROMPT_VERSION_TH = 1
FIELDS = ("headline", "trend", "insight", "workshop_question")
PROFILE_FIELDS = ("attribute", "functional_consequence", "psychosocial_consequence", "job_to_be_done",
                  "point_of_difference", "point_of_parity")
NOT_ENOUGH_DATA = "ข้อมูลไม่พอ"

SYSTEM_PROMPT = """You are the editor of an English-language consumer trend report written in the style of Trend Hunter.
You receive ONE trend: its name, English context from a forecasting pipeline, and a trend profile written in Thai
(Means-End Chain / Jobs-to-be-Done fields). Rewrite this material as clear, natural business English.

Rules:
- Use ONLY facts contained in the input. Do not add brands, numbers, ingredients, claims or statistics that are not in the input.
- A Thai field whose value is "ข้อมูลไม่พอ" means "not enough data" - ignore that field.
- Third person, present tense. English only. No markdown, no bullet points, no Thai characters.

Return JSON only:
{
  "headline": "one sentence, max 16 words, saying what is happening in the market",
  "trend": "2-3 sentences: what the trend is - the product attribute or technology, what it does for the user, and how it differs from ordinary products in the category",
  "insight": "2-3 sentences: why consumers want it - the job they need done, in which situation, and how the result makes them feel",
  "workshop_question": "one question for a brand workshop, starting with 'How can your brand', max 40 words, ending with '?'"
}"""

SYSTEM_PROMPT_TH = """You are the editor of a Thai-language consumer trend report written in the style of Trend Hunter,
for Thai business readers. You receive ONE trend: its name, English context from a forecasting pipeline, a trend
profile already written in Thai (Means-End Chain / Jobs-to-be-Done fields), and the English reasons why some products
match the trend. Write the report copy in natural, professional Thai.

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
  "workshop_question": "one Thai question for a brand workshop, starting with 'แบรนด์ของคุณ' and ending with '?'",
  "target": "the target consumer from the input, translated into one short Thai phrase",
  "product_reasons": ["the Thai translation of each product match reason - same order and same count as the input list"]
}"""

SYSTEM_PROMPT_TH_TRANSLATE = """Translate the JSON values below from English into natural, professional Thai for a
business trend report read by Thai marketing and product teams.

Rules:
- Return JSON only, with exactly the same keys, nesting and list lengths as the input. Translate values only - never keys.
- Keep brand names, company names, product names, ingredient names, standards and technical terms (e.g. ISDIN, Puig,
  NADES, SPF, ISO 17516) in English exactly as written.
- Do not add or remove facts, numbers or claims. No markdown. Empty strings stay empty."""


def _clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def build_input(trend):
    """ข้อมูลที่ส่งให้ LLM ต่อเทรนด์ - ใช้คำนวณ hash ของ cache ด้วย (ข้อมูลเปลี่ยน = เรียกใหม่)"""
    a = trend.get("analysis") or {}
    profile = trend.get("profile") or {}
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
    """คืน dict ข้อความที่ผ่าน หรือ None - ต้องครบทุกช่อง เป็นภาษาอังกฤษล้วน และคำถามลงท้ายด้วย ?"""
    if not isinstance(parsed, dict):
        return None
    out = {}
    for f in FIELDS:
        value = _clean(parsed.get(f))
        if not value or has_thai(value):
            return None
        out[f] = value
    if not out["workshop_question"].endswith("?"):
        return None
    return out


def validate_th(parsed, payload):
    """ฉบับไทย: ครบทุกช่อง มีอักษรไทยจริง คำถามลงท้ายด้วย ? และเหตุผลสินค้าครบจำนวนเท่าต้นฉบับ (ลำดับเดียวกัน)"""
    if not isinstance(parsed, dict):
        return None
    out = {}
    for f in FIELDS:
        value = _clean(parsed.get(f))
        if not value or not has_thai(value):
            return None
        out[f] = value
    if not out["workshop_question"].endswith("?"):
        return None
    target = _clean(parsed.get("target"))
    if payload["context_en"]["target_consumer"] and not has_thai(target):
        return None
    out["target"] = target
    src = payload.get("product_match_reasons_en", [])
    reasons = parsed.get("product_reasons")
    if not isinstance(reasons, list) or len(reasons) != len(src):
        return None
    out["product_reasons"] = [_clean(r) for r in reasons]
    if any(s and not has_thai(r) for s, r in zip(src, out["product_reasons"])):
        return None
    return out


def _lower_first(text):
    return text[:1].lower() + text[1:] if text and not text[:2].isupper() else text


def _sentence(text):
    """ต่อท้ายด้วยจุดถ้ายังไม่มีเครื่องหมายจบประโยค - ข้อความจาก ⑦ บางช่องไม่มีจุดท้าย พอต่อกันแล้วประโยคชนกัน"""
    text = _clean(text)
    return text if not text or text[-1] in ".!?" else f"{text}."


def fallback_texts(trend):
    """ข้อความสำรองจากภาษาอังกฤษที่มีอยู่แล้วในผล ⑦ (ไม่เรียก LLM) - ใช้เมื่อไม่มี/ไม่ผ่านผลจาก LLM"""
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
    target = _clean(trend.get("target")).rstrip(".")
    question = (f"How can your brand lead the {trend['name']} trend for {_lower_first(target)}?" if target
                else f"How can your brand lead the {trend['name']} trend?")
    return {"headline": headline, "trend": first_sentences(trend_text, 520),
            "insight": first_sentences(insight, 520), "workshop_question": question}


def fallback_texts_th(trend):
    """ข้อความสำรองฉบับไทย (ไม่เรียก LLM): ใช้จุดเด่นเทรนด์ภาษาไทยจาก ⑪ ตรงๆ - ⑪ ไม่มีข้อมูลเลยค่อยใช้ข้อความสำรองอังกฤษ
    กลุ่มเป้าหมายและเหตุผลจับคู่สินค้าไม่มีต้นฉบับภาษาไทย จึงคงภาษาอังกฤษไว้"""
    profile = trend.get("profile") or {}

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
        "workshop_question": f"แบรนด์ของคุณจะคว้าโอกาสจากเทรนด์ {trend['name']} ได้อย่างไร?",
        "target": _clean(trend.get("target")),
        "product_reasons": [p.get("reason") or "" for p in trend.get("products", [])],
    }


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
    ({headline, trend, insight, workshop_question, source} + ฉบับไทยมี target และ product_reasons เพิ่ม)

    cache: dict จากไฟล์ cache ของภาษานั้น (หรือ {}) - แก้ไขในตัว คืนค่ากลับด้วยเพื่อให้ผู้เรียกบันทึก
    llm_call: None = ไม่เรียก LLM (ใช้ cache ที่ hash ตรงก่อน ไม่มีค่อย fallback)
    คืน (cache, สรุปจำนวนต่อแหล่ง)"""
    spec = _SPECS[lang]
    key = spec["key"]
    items = cache.setdefault("items", {})
    todo = []
    for t in trends:
        t.pop(key, None)
        payload = spec["build"](t)
        h = input_hash(payload, spec["version"])
        cached = items.get(t["name"])
        output = spec["validate"](cached.get("output"), payload) if cached and cached.get("input_hash") == h else None
        if output and not refresh:
            t[key] = {**output, "source": "llm (cached)"}
        else:
            todo.append((t, payload, h))

    def _one(job):
        t, payload, h = job
        try:
            content = _call(llm_call, spec["prompt"], json.dumps(payload, ensure_ascii=False, indent=1),
                            spec["max_tokens"])
            return t, h, spec["validate"](parse(content), payload), None
        except Exception as e:  # noqa: BLE001 - เทรนด์เดียวพังต้องไม่ทำให้ทั้งรายงานพัง
            return t, h, None, e

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
PROMPT_VERSION_CONDENSE = 1
# จำนวนคำสูงสุดต่อช่อง (ภาษาอังกฤษ) - ตรวจด้วย validate_condensed ยอมเกินได้ CONDENSE_TOLERANCE เท่า
CONDENSE_LIMITS = {
    "stepic": {"headline": 6, "body": 20},
    "signals": {"signal": 22, "implication": 12, "outlook": 35},
}
CONDENSE_TOLERANCE = 1.25

SYSTEM_PROMPT_CONDENSE = """You edit one slide of an English consumer trend report that has too much text.
Shorten every JSON value so it stays within its word limit (given in "limits"), keeping the single most important
idea. Keep brand, company, ingredient and technical names (e.g. ISDIN, NADES, SPF, ISO) and keep numbers exactly as
written. Do not add facts. Plain English sentences, no markdown, no bullet characters.

Return JSON only, with the same keys and the same number of items as the input "content" - never include "limits":
{"items": [...], ...}"""


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


def validate_condensed(section, src, out):
    """โครงเดียวกับต้นฉบับ (คีย์/จำนวนข้อ) ทุกช่องที่ต้นฉบับมีข้อความต้องไม่ว่าง เป็นภาษาอังกฤษ และไม่เกินจำนวนคำ"""
    limits = CONDENSE_LIMITS[section]
    if not isinstance(out, dict) or not isinstance(out.get("items"), list) or len(out["items"]) != len(src["items"]):
        return None
    if "outlook" in src and not isinstance(out.get("outlook"), str):
        return None

    def ok(field, source, value):
        value = _clean(value)
        if not source:
            return ""
        if not value or has_thai(value) or _word_count(value) > limits[field] * CONDENSE_TOLERANCE:
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
        try:
            content = llm_call(SYSTEM_PROMPT_CONDENSE, json.dumps(request, ensure_ascii=False, indent=1),
                               max_tokens=1500)
            parsed = parse(content)
            if isinstance(parsed, dict) and isinstance(parsed.get("content"), dict):
                parsed = parsed["content"]  # บางครั้งโมเดลห่อคำตอบกลับมาใน "content" เหมือนคำขอ
            return section, h, validate_condensed(section, payload, parsed), None
        except Exception as e:  # noqa: BLE001 - ส่วนเดียวพังต้องไม่ทำให้ทั้งรายงานพัง
            return section, h, None, e

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


# ช่องที่เป็น "ชื่อเรียก" (เช่น "The Clinical Bio-Convergence", "The Evidence-First Curator") - LLM มักคงเป็นภาษาอังกฤษ
# แบบชื่อเฉพาะ ซึ่งยอมรับได้ ช่องนี้จึงไม่บังคับให้มีอักษรไทย (ช่องอื่นบังคับ) - เจอจริงรอบ 082438: takeaway ถูกตีตก
# ทั้งส่วนเพราะชื่อ mega trend ไม่ได้แปล
NAME_FIELDS = {"mega_trend_name", "name"}


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
    text = _clean(out) if isinstance(out, str) else None
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
        try:
            content = llm_call(SYSTEM_PROMPT_TH_TRANSLATE, json.dumps(payload, ensure_ascii=False, indent=1),
                               max_tokens=4000)
            return section, h, validate_same_shape(payload, parse(content)), None
        except Exception as e:  # noqa: BLE001 - ส่วนเดียวพังต้องไม่ทำให้ทั้งรายงานพัง
            return section, h, None, e

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
        try:
            content = llm_call(SYSTEM_PROMPT_TH_TRANSLATE, json.dumps(payload, ensure_ascii=False, indent=1),
                               max_tokens=2500)
            return key, h, validate_same_shape(payload, parse(content)), None
        except Exception as e:  # noqa: BLE001 - กลุ่มเดียวพังต้องไม่ทำให้ทั้งรายงานพัง
            return key, h, None, e

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
