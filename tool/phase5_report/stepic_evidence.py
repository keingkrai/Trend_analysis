# -*- coding: utf-8 -*-
"""
⑭-⑮ STEPIC แบบ "ใช้เฉพาะสิ่งที่คำค้นยืนยัน" - ใช้กับรอบที่ข้อมูลมีแค่สาย Search (Google Trends คำค้นกำลังขึ้น) (2026-10-27)

ปัญหาที่เจอจากรอบแรก (beauty_and_personal_care_20261027_164405): STEPIC เดิม (tf2.analyze_trend + integrate_stepic) ถูกออกแบบมาให้ได้ข้อมูลจากงานวิจัย/ข่าว
เมื่อเหลือแค่คำค้น LLM เติมเนื้อหามิติเทคโนโลยี/นโยบาย/อุตสาหกรรมเองจากความรู้ของมัน (เช่น extremophile, พอลิเมอร์สังเคราะห์, กฎสาร UV, ค่าปรับ,
ห่วงโซ่อุปทาน - ข้อมูลไม่มีเลย) และ prompt เดิมยังสั่งให้ "ให้ proof point จาก UN, research reports" จึงชวนให้แต่ง

หลักของไฟล์นี้ (ตัวเลข/ข้อเท็จจริงตัดสินด้วยโค้ด ส่วน LLM ทำแค่งานภาษา เหมือนทั้งไปป์ไลน์):
1. LLM ได้ "ชุดหลักฐาน" ชุดเดียว (คำค้นจริงต่อเทรนด์ + พื้นที่ + ตัวเลขการเติบโตจากโมเดล + สินค้าจริงที่ ⑫ จับคู่) และถูกสั่งให้ใช้เฉพาะชุดนี้
2. ทุกมิติ/บุคคล/สัญญาณ/ข้อสรุป ต้องแนบ "evidence" = ข้อความที่คัดลอกตรงตัวจากชุดหลักฐาน - โค้ดตรวจว่ามีอยู่ในชุดหลักฐานจริง ที่ไม่ผ่าน = ตัดทิ้ง
   (proof_point ที่แสดงในรายงานคือข้อความที่ผ่านการตรวจเท่านั้น ไม่ใช่ที่ LLM เขียน)
3. มิติที่ไม่มีหลักฐานที่ตรวจผ่านเลย = status "no_evidence" + ทุกช่องเป็น "No data" (ไม่ปล่อยว่าง/แต่งเติม)
4. ตัวเลขหลายหลักที่ไม่อยู่ในชุดหลักฐาน -> ช่องนั้นเป็น "No data"

ไม่ import bootstrap / ไม่เรียก API เอง (รับฟังก์ชัน chat_json เข้ามา) - เทสต์ได้ตรงๆ
"""
import json
import re

# ตัวตรวจที่ใช้ร่วมกับ ⑪ และ ⑯ อยู่ที่ common/evidence_gate.py (เทสต์เดิมยังเรียกผ่านชื่อในไฟล์นี้ได้)
from common.evidence_gate import (NO_DATA, norm as _norm, numbers_supported, quotes_supported,  # noqa: F401,E402
                                  sanitize, trend_evidence_lines, trend_searches, verify_snippets)

NO_DATA_NOTE = "The rising searches in this run say nothing about this force."
DIMENSIONS = ("society", "technology", "environment", "policy", "industry", "creativity")

# ช่วยตัดสินว่า "หลักฐานของมิตินี้" คืออะไร - บอก LLM ว่าถ้าคำค้นไม่ได้พูดถึงสิ่งนี้ ให้ตอบ no_evidence
DIMENSION_GUIDE = {
    "society": "who is searching, where, and what change in behaviour or need the searches show",
    "technology": "ONLY if a search itself names a technology, device, treatment or technical ingredient",
    "environment": "ONLY if searches name weather, climate, pollution, haze, heat, a season or sustainability",
    "policy": "ONLY if searches name a law, rule, regulation, recall, government programme or authority",
    "industry": "ONLY the growth numbers and which shop products are closest to each trend. The shop products show only "
                "which products are closest to a trend, not market share or leaders, so market_structure, competitive_landscape, "
                "key_players and investment_signal are No data unless the evidence states them. Say 'median of the trends in "
                "this run', never 'market growth'",
    "creativity": "ONLY looks, styles, occasions or ways of using products that a search itself names. "
                  "product_innovation and differentiation_strategy are No data unless a search names them",
}

import re  # noqa: E402

# 🆕 (2026-10-28) มิติที่ "คำค้นต้องพูดถึงเรื่องนั้นเอง" - ข้อความที่ LLM คัดลอกมาถูกต้องแต่ไม่เกี่ยวกับมิติ (เช่น คำค้นครีมกันแดดถูกใช้เป็นหลักฐานของ Environment ->
# "แสงแดดกระตุ้นให้คนหาเรื่องกันแดด") ผ่านการตรวจ "มีอยู่จริง" ได้ จึงตรวจเพิ่มด้วยคำหัวข้อ: ไม่มีข้อความที่ผ่านการตรวจข้อไหนมีคำของมิตินั้นเลย = no_evidence
DIMENSION_TOPIC = {
    "environment": re.compile(
        r"\b(weather|climate|pollution|polluted|haze|heat|heatwave|rain|rainy|storm|typhoon|snow|wind|windy|temperature|season|seasonal|winter|"
        r"monsoon|flood|drought|humid|humidity|fog|air quality|pm ?2\.5|sustainable|sustainability|recycle|recycled|recycling|plastic|carbon)\b"
        r"|อากาศ|ร้อน|หนาว|ฝน|ฝุ่น|พายุ|ฤดู|มลพิษ|น้ำท่วม|น้ำ ท่วม|ภัยแล้ง|ความชื้น|ความ ชื้น|รีไซเคิล|ยั่งยืน"),
    "policy": re.compile(
        r"\b(law|laws|regulation|regulations|regulatory|ban|banned|rule|rules|recall|government|ministry|fda|authority|tax|tariff|policy|legal|"
        r"license|licence|permit|approved|approval)\b"
        r"|กฎหมาย|กฎ ระเบียบ|ประกาศ|ห้าม|ภาษี|กระทรวง|รัฐบาล|เรียก คืน|ใบอนุญาต|นโยบาย"),
}

SYSTEM_DIMENSION = """You write one section of a trend report using ONLY the EVIDENCE block you are given.
The evidence is: rising Google searches from the last 12 months with the places they rise in, growth numbers from a
forecast model, and real products from a shop catalogue. You have no other knowledge for this task.

Rules:
1. Every statement must restate or directly summarise something written in the evidence. Do not add ingredients,
   technologies, studies, laws, regulations, companies, brands, statistics, prices or causes that are not written in the
   evidence. Do not explain why people search unless the searches themselves say it. Do not make forecasts of your own.
   Do not recommend actions and do not guess with words like may, might, could or can about what brands or products do.
   When you mention a search, put it in single quotes exactly as written in the evidence.
2. "evidence" = 1 to 4 exact quotes copied character for character from the evidence block (one search, a short phrase with
   a number, a product name), each at most 15 words, never spanning several lines. The quotes must be the ones your
   statements rest on. Never put a double quote character inside a quote or an answer.
3. If the evidence says nothing about this dimension, return {"status": "no_evidence", "note": "<one sentence on what is missing>"}.
4. If the evidence supports only some of the fields, fill those and write exactly "No data" for each field it does not support.
5. Plain English, short sentences, no marketing language.
Return VALID JSON only."""

SYSTEM_INTEGRATE = """You write the summary of a trend report using ONLY the EVIDENCE block and the verified dimension sections you are given.
You have no other knowledge for this task.

Rules:
1. Every statement must restate or directly summarise something in the evidence. Do not add ingredients, technologies,
   studies, laws, companies, brands, statistics or causes that are not written in it. Do not forecast anything yourself.
2. "evidence" (top level, in every persona and in every signal) = 1 to 4 exact quotes copied character for character from
   the EVIDENCE block or from the list of verified quotes (one search, a short phrase with a number), each at most 15 words,
   never spanning several lines. Never quote the dimension sections themselves: they are your earlier summaries, not evidence.
   Never put a double quote character inside a quote or an answer.
3. A field the evidence does not support is "" (empty string). A list the evidence does not support is [].
4. emerging_personas: 0 to 3. A persona is a group of searchers the evidence shows (who, where, what they look up).
   value_driver and channel_preference stay "" unless the evidence shows them.
5. cross_dimensional_signals: 0 to 4. Only combine dimensions whose section has status "evidence". "dimensions" = 2 or 3
   dimension names in capitals joined by " + ". A signal says only that the evidence shows both things at the same time.
   Never say that one causes, drives, triggers or prepares for the other: searches do not show causes. "implication" is "".
6. 3_month_projection is "" (the growth numbers are yearly, not 3-month).
7. key_risk and key_opportunity: only what the evidence or growth numbers directly show; otherwise "".
8. "Tracked terms" in the growth numbers were chosen to measure a trend; they are not proof that people searched for them.
Return VALID JSON only."""

INTEGRATE_SCHEMA = """Provide one JSON object with exactly this structure (all values plain text):

{
  "mega_trend_name": "...",
  "macro_direction": "...",
  "core_concept": "...",
  "3_month_projection": "...",
  "key_risk": "...",
  "key_opportunity": "...",
  "evidence": ["..."],
  "emerging_personas": [
    {"name": "...", "description": "...", "value_driver": "", "channel_preference": "", "evidence": ["..."]}
  ],
  "cross_dimensional_signals": [
    {"dimensions": "SOCIETY + ENVIRONMENT", "signal": "...", "implication": "...", "evidence": ["..."]}
  ]
}"""


def build_evidence(stream_data, selected_names, growth_facts, product_context):
    """ชุดหลักฐานชุดเดียวของรอบ -> ข้อความ: ขอบเขตข้อมูล + ต่อเทรนด์ (พื้นที่ + หมวด Google + คำค้นจริง) + ตัวเลขการเติบโต + สินค้าจริง
    selected_names = ชื่อเทรนด์ที่ ⑪ คัด (None = ทุกเทรนด์) / ไม่ใส่ข้อความที่ LLM เขียนเองในสาย (outlook/ความต้องการ) - เป็นการตีความ ไม่ใช่ข้อมูล"""
    meta = stream_data.get("search_meta") or {}
    lines = ["EVIDENCE",
             f"Scope: rising Google searches over the last 12 months, {meta.get('n_queries', '?')} searches in "
             f"{meta.get('n_categories', '?')} Google categories, places: {', '.join(meta.get('places') or [])} "
             "(TH = Thailand, WW = worldwide)."]
    for t in stream_data.get("trends") or []:
        if selected_names is not None and t.get("Trend Name") not in selected_names:
            continue
        lines += [""] + trend_evidence_lines(t)
    lines += ["", "Growth numbers (forecast model, worldwide Google Trends):", growth_facts_text(growth_facts),
              "", "Real products from the shop catalogue closest to each trend:", str(product_context or "")]
    return sanitize("\n".join(lines))


def growth_facts_text(growth_facts):
    """ตัวเลขการเติบโตจาก mo.stepic_growth_facts (ข้อความ JSON) -> บรรทัดข้อความธรรมดาต่อเทรนด์ (อ่านง่ายและไม่มี JSON ให้ LLM คัดลอกแล้วทำ JSON พัง)"""
    try:
        data = json.loads(growth_facts) if isinstance(growth_facts, str) else growth_facts
        lines = [str(data.get("note") or "")]
        market = data.get("market") or {}
        lines.append("Market: " + ", ".join(f"{k} = {v}" for k, v in market.items() if v is not None))
        for t in data.get("trends") or []:
            ch = t.get("expected_search_growth_pct_vs_last_12_months") or {}
            lines.append(f"Trend {t.get('trend')}: tracked terms (chosen to measure the trend, not proof of searches) {', '.join(t.get('keywords') or [])}; expected search growth vs last "
                         f"12 months (%): " + ", ".join(f"{k} {v}" for k, v in ch.items())
                         + "; vs market: " + ", ".join(f"{k} {v}" for k, v in (t.get("growth_vs_market") or {}).items()))
        return "\n".join(lines)
    except (ValueError, AttributeError, TypeError):
        return str(growth_facts or "")


def ask_json(chat_json, system, prompt, label, valid, tries=3, log=print):
    """เรียก LLM ซ้ำได้ `tries` ครั้งจนได้คำตอบที่ parse ได้และผ่าน valid(dict) - ล้มทุกครั้ง = RuntimeError (ห้ามกลายเป็น "ไม่มีหลักฐาน" เงียบๆ)"""
    last = None
    for attempt in range(1, tries + 1):
        parsed = chat_json(system, prompt, label)
        if isinstance(parsed, dict) and not parsed.get("error") and valid(parsed):
            return parsed
        last = parsed
        log(f"  ⚠️ {label}: คำตอบใช้ไม่ได้ (ครั้งที่ {attempt}/{tries})")
    raise RuntimeError(f"{label}: คำตอบของ LLM ใช้ไม่ได้ครบ {tries} ครั้ง ({str(last)[:120]}) - ไม่นับเป็น \"ไม่มีหลักฐาน\" รันขั้นนี้ใหม่")


def _clean_field(value, evidence_norm):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False) if value else ""
    text = text.strip()
    if not text or text.lower() in ("no data", "n/a", "none", "unknown"):
        return NO_DATA
    return text if numbers_supported(text, evidence_norm) and quotes_supported(text, evidence_norm) else NO_DATA


def no_evidence_dimension(fields, note=None):
    """มิติที่ไม่มีหลักฐาน: ทุกช่อง "No data" (ตัวเขียน md ต้นฉบับอ่านช่องเหล่านี้ - ไม่ปล่อยให้ได้ N/A) + status/note ให้รายงาน PDF ใช้"""
    return {"status": "no_evidence", "note": note or NO_DATA_NOTE, **{f: NO_DATA for f in fields}}


def build_dimension(parsed, fields, evidence_norm, topic=None):
    """คำตอบดิบของ LLM ต่อ 1 มิติ -> dict ที่ผ่านการตรวจ (status evidence) หรือ no_evidence
    ผ่านเมื่อมี evidence ที่ตรวจแล้วอย่างน้อย 1 ข้อ และอย่างน้อย 1 ช่องมีเนื้อหา - proof_point = evidence ที่ตรวจแล้ว (ไม่ใช่ข้อความของ LLM)
    topic = regex คำหัวข้อของมิติ (DIMENSION_TOPIC) - ไม่มี evidence ที่ตรวจแล้วข้อไหนตรงเลย = no_evidence"""
    if not isinstance(parsed, dict) or parsed.get("error") or str(parsed.get("status") or "").lower() == "no_evidence":
        note = parsed.get("note") if isinstance(parsed, dict) and isinstance(parsed.get("note"), str) else None
        return no_evidence_dimension(fields, note)
    verified = verify_snippets(parsed.get("evidence"), evidence_norm)
    if topic is not None:
        verified = [q for q in verified if topic.search(_norm(q))]
    content = {f: _clean_field(parsed.get(f), evidence_norm) for f in fields if f != "proof_point"}
    if not verified or all(v == NO_DATA for v in content.values()):
        return no_evidence_dimension(fields)
    return {"status": "evidence", **content, "proof_point": " | ".join(verified)}


# 🆕 (2026-10-28) ประโยค consumer_intent_signal ของข้อความวิเคราะห์ต่อเทรนด์ (Step 9d) ของรอบสาย Search - 1 ประโยคต่อเทรนด์ จากคำค้นจริงของเทรนด์นั้นอย่างเดียว
SYSTEM_INTENT = """You write ONE sentence for a trend report using ONLY the EVIDENCE block: rising Google searches for one trend and the
places they rise in. You have no other knowledge for this task.

Rules:
1. Say what the searches are, in their own terms. If they are names of events, shows, people or places, write that people search
   for those names. Say a search is for a product or a problem only when the search itself names it. Do not say why people search,
   what they feel or want. Do not add ingredients, brands, studies, numbers or places that are not in the evidence. Do not use
   may, might, could or should.
2. When you mention a search, put it in single quotes exactly as written in the evidence.
3. "evidence" = 1 to 3 exact quotes copied character for character from the evidence block (one search each, at most 15 words,
   never containing a double quote) that your sentence rests on.
4. If the searches name nothing you can describe, return {"consumer_intent_signal": "No data", "evidence": []}.
5. Plain English, at most 30 words.
Return VALID JSON only: {"consumer_intent_signal": "...", "evidence": ["..."]}"""


def build_intent(parsed, evidence_norm):
    """คำตอบดิบของ LLM -> {"text", "evidence"} - ผ่านเมื่อมีข้อความที่คัดลอกแล้วตรงกับหลักฐานอย่างน้อย 1 ข้อ และตัวเลข/คำค้นในเครื่องหมายคำพูดเดี่ยวอยู่ในหลักฐาน
    ไม่ผ่าน = {"text": "", "evidence": []} (ผู้เรียกใช้ประโยคสำรองจากคำค้นจริง)"""
    parsed = parsed if isinstance(parsed, dict) else {}
    text = re.sub(r"\s+", " ", parsed["consumer_intent_signal"]).strip() if isinstance(parsed.get("consumer_intent_signal"), str) else ""
    quotes = verify_snippets(parsed.get("evidence"), evidence_norm)
    if not text or text.lower() in ("no data", "n/a", "none") or not quotes:
        return {"text": "", "evidence": []}
    if not (numbers_supported(text, evidence_norm) and quotes_supported(text, evidence_norm)):
        return {"text": "", "evidence": []}
    return {"text": text, "evidence": quotes}


def write_intents(chat_json, rows_by_name, trend_names, log=print):
    """{ชื่อเทรนด์: {"text", "evidence"}} - เรียก LLM ทีละเทรนด์ด้วยคำค้นจริงของเทรนด์นั้น (ชุดหลักฐานแยกกัน ตรวจข้อความที่คัดลอกกับชุดของตัวเอง)
    LLM ตอบใช้ไม่ได้ครบ 3 ครั้ง = ไม่มีประโยคของ LLM สำหรับเทรนด์นั้น (ใช้ประโยคสำรองจากคำค้นจริง - ไม่ใช่การบอกว่าไม่มีข้อมูล) พร้อมบอกใน log"""
    out = {}
    for name in trend_names:
        row = rows_by_name.get(name)
        if not row:
            continue
        evidence_text = sanitize(chr(10).join(["EVIDENCE"] + trend_evidence_lines(row)))
        try:
            parsed = ask_json(chat_json, SYSTEM_INTENT, evidence_text, f"intent {name[:30]}",
                              lambda d: isinstance(d.get("consumer_intent_signal"), str), log=log)
        except RuntimeError as e:
            log(f"  ⚠️ {name}: {e} - ใช้ประโยคสำรองจากคำค้นจริง")
            continue
        out[name] = build_intent(parsed, _norm(evidence_text))
        log(f"  intent {name[:34]:34} -> " + ("evidence" if out[name]["text"] else "ไม่มีข้อความที่ตรวจผ่าน (ใช้ประโยคสำรอง)"))
    return out


def analyze_dimensions(chat_json, evidence_text, user_query, stepic_fields, log=print):
    """6 มิติ (เรียก LLM ทีละมิติ) -> {มิติ: dict} - โครงช่องต่อมิติตาม stepic_fields (STEPIC_FIELDS ของ run_stepic_report)"""
    evidence_norm = _norm(evidence_text)
    out = {}
    for dim in DIMENSIONS:
        fields = stepic_fields[dim]
        system = SYSTEM_DIMENSION + f"\n\nFocus trend: {user_query}"
        prompt = (f"Dimension: {dim.upper()}. Evidence for this dimension means: {DIMENSION_GUIDE[dim]}.\n\n"
                  f"Fields to provide (except proof_point): {', '.join(f for f in fields if f != 'proof_point')}\n\n"
                  f"{evidence_text}\n\n"
                  'JSON: {"status": "evidence", "evidence": ["exact quote", ...], ' +
                  ", ".join(f'"{f}": "..."' for f in fields if f != "proof_point") + "}\n"
                  'or {"status": "no_evidence", "note": "..."}')
        parsed = ask_json(chat_json, system, prompt, f"STEPIC {dim}",
                          lambda d: str(d.get("status") or "").lower() in ("evidence", "no_evidence"), log=log)
        out[dim] = build_dimension(parsed, fields, evidence_norm, DIMENSION_TOPIC.get(dim))
        log(f"  {dim:12} -> {out[dim]['status']}" + (f" ({len(out[dim]['proof_point'].split(' | '))} quotes)" if out[dim]["status"] == "evidence" else ""))
    return out


def _dims_text(raw):
    return json.dumps({d: v for d, v in raw.items()}, ensure_ascii=False, indent=1)


def build_final(parsed, raw_dims, evidence_norm):
    """คำตอบดิบของ LLM (สังเคราะห์รวม) -> final ที่ผ่านการตรวจ: ข้อสรุประดับบน/persona/signal ที่ evidence ไม่ผ่าน = ตัดทิ้งเป็นค่าว่าง
    signal ต้องใช้เฉพาะมิติที่ status evidence | คืน dict โครงเดียวกับ STEPIC_FINAL_SCHEMA เดิม + evidence ที่ตรวจแล้ว"""
    parsed = parsed if isinstance(parsed, dict) and not parsed.get("error") else {}
    top_ev = verify_snippets(parsed.get("evidence"), evidence_norm)
    final = {k: "" for k in ("mega_trend_name", "macro_direction", "core_concept", "3_month_projection", "key_risk", "key_opportunity")}
    blanked = []   # บันทึกการตรวจ: ช่องที่ LLM เขียนแต่โค้ดตัดทิ้ง + เหตุผล (เห็นได้ในผลลัพธ์ ไม่เงียบ)
    for k in final:
        if not parsed.get(k):
            continue
        value = _clean_field(parsed.get(k), evidence_norm)
        if not top_ev:
            blanked.append(f"{k}: no verified top-level quote")
        elif value == NO_DATA:
            blanked.append(f"{k}: number or quoted search not in the evidence")
        else:
            final[k] = value
    final["3_month_projection"] = ""   # ตัวเลขของโมเดลเป็นรายปี ไม่ใช่ 3 เดือน - หน้ารายงานหัวข้อ "Next 3 months" จึงไม่ใช้ข้อความนี้
    final["evidence"] = top_ev
    given = parsed.get("evidence") if isinstance(parsed.get("evidence"), list) else [parsed.get("evidence")] if parsed.get("evidence") else []
    final["_audit"] = {"top_quotes_given": len(given), "top_quotes_verified": len(top_ev), "fields_blanked": blanked,
                       "top_quotes_not_found": [str(q)[:120] for q in given if str(q) not in top_ev][:4]}
    personas = []
    for p in parsed.get("emerging_personas") or []:
        ev = verify_snippets(p.get("evidence") if isinstance(p, dict) else None, evidence_norm)
        if not ev or not p.get("name") or not p.get("description"):
            continue
        personas.append({"name": str(p["name"]).strip(), "description": _clean_field(p["description"], evidence_norm),
                         "value_driver": "" if _clean_field(p.get("value_driver"), evidence_norm) == NO_DATA else str(p["value_driver"]).strip(),
                         "channel_preference": "" if _clean_field(p.get("channel_preference"), evidence_norm) == NO_DATA else str(p["channel_preference"]).strip(),
                         "evidence": ev})
    final["emerging_personas"] = [p for p in personas if p["description"] != NO_DATA][:3]
    ok_dims = {d.upper() for d, v in raw_dims.items() if v.get("status") == "evidence"}
    signals = []
    for s in parsed.get("cross_dimensional_signals") or []:
        if not isinstance(s, dict):
            continue
        dims = s.get("dimensions")
        names = [d.strip().upper() for d in (dims if isinstance(dims, list) else str(dims or "").split("+")) if str(d).strip()]
        ev = verify_snippets(s.get("evidence"), evidence_norm)
        if len(names) < 2 or not set(names) <= ok_dims or not ev or not s.get("signal"):
            continue
        sig = _clean_field(s["signal"], evidence_norm)
        if sig == NO_DATA:
            continue
        # implication = ข้อเสนอ/เหตุผลเชิงสาเหตุ - คำค้นยืนยันไม่ได้ จึงเว้นว่างเสมอ (signal บอกแค่ว่าขึ้นพร้อมกัน)
        signals.append({"dimensions": " + ".join(names), "signal": sig, "implication": "", "evidence": ev})
    final["cross_dimensional_signals"] = signals[:4]
    return final


def integrate_evidence(chat_json, evidence_text, raw_dims, user_query):
    """สังเคราะห์รวมจากหลักฐาน + มิติที่ตรวจแล้ว (เรียก LLM 1 ครั้ง) -> final ที่ผ่านการตรวจ"""
    system = SYSTEM_INTEGRATE + f"\n\nFocus trend: {user_query}"
    quotes = "\n".join(f"{d}: {s['proof_point']}" for d, s in raw_dims.items() if s.get("status") == "evidence" and s.get("proof_point"))
    prompt = (f"{evidence_text}\n\nVerified quotes by dimension (each is copied from the evidence; you may use them as quotes):\n"
              f"{quotes}\n\nDimension sections (status no_evidence means the evidence says nothing about it; context only, never quote them):\n"
              f"{_dims_text({d: {k: v for k, v in s.items() if k not in ('proof_point',)} for d, s in raw_dims.items()})}\n\n"
              f"{INTEGRATE_SCHEMA}")
    parsed = ask_json(chat_json, system, prompt, "STEPIC integration",
                      lambda d: any(k in d for k in ("mega_trend_name", "macro_direction", "emerging_personas")))
    return build_final(parsed, raw_dims, _norm(evidence_text))
