# -*- coding: utf-8 -*-
"""
⑲ รายงานส่วนแบ่งตลาด — Phase 4: LLM อ่านหลักฐานจากเว็บ (Phase 3) แล้วสรุปว่าอะไรเกี่ยวข้องกับการเปลี่ยนแปลงในแต่ละคำถาม
จัดเข้าปัจจัยในรายการชุดปิด (factors.py) พร้อมอ้างอิง rid ของหลักฐาน - โค้ดตรวจทุกข้อก่อนเก็บ

ก่อนส่ง LLM (โค้ด):
    - ตัดหลักฐานที่เก่ากว่า 1 ม.ค. ของปีตั้งต้น (วันที่ของหน้า หรือวันที่ในผลค้นหา - แปลง พ.ศ. / เดือนไทยแล้ว)
      ไม่มีวันที่ = เก็บไว้ แต่บอก LLM ว่าไม่ทราบวันที่
    - คำถามแบรนด์ใช้เฉพาะผลที่มีชื่อแบรนด์ (mentions_brand)
    - เนื้อหาเต็มตัดเหลือบรรทัดที่มีคำสำคัญของคำถาม (ชื่อแบรนด์ / ช่องทาง / หมวด) - ไม่เจอเลย: คำถามตลาดใช้ช่วงต้นของหน้า
LLM (GLM-5 ผ่าน Bedrock เหมือน ⑯/⑰) ตอบ findings: ปัจจัย, ประโยคอังกฤษ + ไทย, rid ที่อ้าง, ข้อความที่ยกมาตรงตัว
ตรวจแต่ละ finding (ไม่ผ่าน = ตัดทิ้งเฉพาะข้อนั้น บันทึกเหตุผลไว้):
    - ปัจจัยอยู่ในรายการที่อนุญาตของคำถามนั้น
    - rid ที่อ้างมีอยู่ในหลักฐานที่ส่งไปจริง และข้อความที่ยกมา (quote) อยู่ในหลักฐานที่อ้างตัวอักษรต่อตัวอักษร (กันแต่งแหล่ง)
    - ตัวเลขทุกตัวในประโยคมีในข้อเท็จจริงของคำถามหรือในหลักฐานที่อ้าง (ยอมให้แปลงปี พ.ศ. <-> ค.ศ.) - LLM ไม่คิดเลขเอง
    - ประโยคอังกฤษไม่มีอักษรไทย ประโยคไทยมีอักษรไทย ไม่มีคำว่าชนะ/แพ้ และคำต้องห้ามของภาษาง่าย
LLM ตอบมาแต่ไม่ผ่านเลยสักข้อ -> ถามซ้ำ 1 ครั้ง; ไม่มี finding = "ยังไม่พบคำอธิบายจากแหล่งข้อมูล" (ไม่เดา)
ผลรวมรายปัจจัย (by_factor) ให้หน้าภาพรวมของรายงาน: คำถาม / แบรนด์ / หมวด / จำนวนแหล่งอ้างอิง

cache: ผลต่อคำถามผูกกับ hash ของข้อมูลที่ส่ง (ข้อมูลเปลี่ยน = ถามใหม่) - รันซ้ำไม่เรียก LLM

ผลลัพธ์:
    output/<รอบ>/phase7_market_findings.json

Usage:
    python tool/phase7_market_report/market_synthesis.py                    # รอบ market_share_* ล่าสุด
    python tool/phase7_market_report/market_synthesis.py --only q18 q20     # บางคำถาม (ทดลองก่อนรันทั้งชุด)
    python tool/phase7_market_report/market_synthesis.py --refresh          # ถามใหม่ทั้งหมด ไม่ใช้ cache
"""
import argparse
import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from factors import FACTORS, WEB_FACTORS  # noqa: E402
from market_facts import OUTPUT_ROOT, load_config  # noqa: E402
from market_questions import CATEGORY_TERMS, OUTLET_TERMS, QUESTIONS_FILE, latest_run  # noqa: E402
from market_search import EVIDENCE_FILE, is_skipped  # noqa: E402

FINDINGS_FILE = "phase7_market_findings.json"
# 2 (2026-10-12): เพิ่ม relevance (direct/background) + บอกว่าใครพูด + ตัดข่าวแบรนด์ทั่วไป - ทดลองรุ่น 1 กับ 3 คำถาม
# ผ่านการตรวจหมดแต่ Mistine ได้ข่าวขยายไปจีน/รางวัลในจีน (ไม่ได้อธิบายส่วนแบ่งในไทยที่ลดลง) และคำโฆษณาแบรนด์เขียนเป็นข้อเท็จจริง
PROMPT_VERSION = 2
RELEVANCE = ("direct", "background")
SYNTH_DEFAULTS = {"max_passages": 12, "page_excerpt_chars": 1500, "max_findings": 5, "llm_workers": 4}
THAI_RE = re.compile(r"[ก-๛]")
JUDGEMENT_EN = re.compile(r"\b(win|wins|won|winner|winners|winning|lose|loses|lost|loser|losers|losing)\b", re.I)
JUDGEMENT_TH = re.compile(r"ชนะ|แพ้|ผู้ชนะ|ผู้แพ้")
BANNED_EN = re.compile(r"\b(YoY|CAGR|momentum|cohort|synergy|leverage|holistic|paradigm)\b", re.I)
BANNED_TH = re.compile(r"\b(YoY|CAGR|momentum|cohort)\b", re.I)
MONTHS_EN = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                         "dec"), 1)}
MONTHS_TH = {m: i for i, m in enumerate(("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.",
                                         "ต.ค.", "พ.ย.", "ธ.ค."), 1)}
QUERY_STOPWORDS = {"thailand", "market", "sales", "growth", "brands", "brand", "products", "new", "local",
                   "competition", "premium", "luxury", "and", "the", "ยอดขาย", "ตลาด", "ไทย", "ตลาดไทย", "เติบโต",
                   "แบรนด์ใหม่", "แบรนด์ไทย", "แข่งขัน", "พรีเมียม", "แบรนด์หรู"}


# ---------------------------------------------------------------------------
# วันที่
# ---------------------------------------------------------------------------

def _year(y):
    """ปี พ.ศ. (> 2400) -> ค.ศ."""
    return y - 543 if y > 2400 else y


def parse_date(text, today=None):
    """วันที่จากหน้าเว็บ/ผลค้นหา -> date หรือ None
    รองรับ: 2024-03-05 / "Oct 7, 2565 BE" / "Mar 17, 2021" / "22 ต.ค. 2567" / "3 days ago" / "2 วันที่ผ่านมา" (= วันนี้)"""
    if not text:
        return None
    s = str(text).strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(_year(int(m.group(1))), int(m.group(2)), int(m.group(3)))
    m = re.match(r"([A-Za-z]{3})[a-z]*\.? (\d{1,2}), (\d{4})", s)
    if m and m.group(1).lower() in MONTHS_EN:
        return date(_year(int(m.group(3))), MONTHS_EN[m.group(1).lower()], int(m.group(2)))
    m = re.match(r"(\d{1,2}) (\S+) (\d{4})", s)
    if m and m.group(2) in MONTHS_TH:
        return date(_year(int(m.group(3))), MONTHS_TH[m.group(2)], int(m.group(1)))
    if re.search(r"\bago\b|ที่ผ่านมา|ที่แล้ว", s):
        return today or date.today()
    return None


def evidence_date(result):
    return parse_date(result.get("page_date")) or parse_date(result.get("serp_date"))


# ---------------------------------------------------------------------------
# เตรียมหลักฐาน
# ---------------------------------------------------------------------------

def keywords_for(question):
    """คำสำคัญของคำถาม - แบรนด์: ชื่อแบรนด์ (อังกฤษ + ไทย) เท่านั้น (คำหมวดอย่าง "care" ดึงบรรทัดที่ไม่เกี่ยวมาเยอะ)
    ตลาด: คำค้นของหมวดและช่องทาง + คำในคำค้นที่ไม่ใช่คำทั่วไป"""
    words = set()
    if question["level"] == "brand":
        facts = question.get("facts") or {}
        return sorted(n.lower() for n in (question.get("brand"), facts.get("name_th")) if n)
    for term in [question.get("topic")] + list(question.get("categories") or []):
        for en_th in (CATEGORY_TERMS.get(term), OUTLET_TERMS.get(term)):
            for t in en_th or ():
                words.update(w.lower() for w in t.split() if len(w) >= 3)
    for x in question.get("queries") or []:
        q = re.sub(r"-site:\S+", " ", x["q"]).replace('"', " ")
        words.update(w.lower() for w in re.split(r"\s+", q) if len(w) >= 3 and w != "OR")
    return sorted(w for w in words if w not in QUERY_STOPWORDS)


def excerpt(text, keywords, max_chars, intro_fallback=True):
    """บรรทัดที่มีคำสำคัญ (เรียงตามเดิม) ไม่เกิน max_chars - ไม่เจอเลย: ช่วงต้นของหน้า (ถ้า intro_fallback) หรือ "" """
    lines = [l for l in (text or "").split("\n") if l.strip()]
    hits = [l for l in lines if any(k in l.lower() for k in keywords)]
    if not hits:
        return (text or "")[: max_chars // 2] if intro_fallback else ""
    out, used = [], 0
    for line in hits:
        if used + len(line) > max_chars:
            break
        out.append(line)
        used += len(line) + 1
    return "\n".join(out) or hits[0][:max_chars]


def select_passages(question, results, base_year, cfg):
    """หลักฐานที่ส่ง LLM: ตัดที่เก่ากว่าปีตั้งต้น / คำถามแบรนด์ที่ไม่มีชื่อแบรนด์ - เนื้อหาเต็มก่อน แล้วค่อย snippet"""
    start = date(base_year, 1, 1)
    keywords = keywords_for(question)
    brand_q = question["level"] == "brand"
    full, snippets, dropped = [], [], {"too_old": 0, "no_brand": 0, "shop_social": 0}
    for r in results:
        if is_skipped(r.get("link")):     # ร้านค้า/โซเชียล - snippet เป็นรายการสินค้า/โพสต์ ไม่ใช่หลักฐาน
            dropped["shop_social"] += 1
            continue
        d = evidence_date(r)
        if d and d < start:
            dropped["too_old"] += 1
            continue
        if brand_q and not r.get("mentions_brand"):
            dropped["no_brand"] += 1
            continue
        base = {"rid": r["rid"], "source": r["domain"], "kind": r.get("kind", "web"),
                "date": d.isoformat() if d else None, "title": r.get("title") or ""}
        if r.get("page_status") == "ok" and r.get("text"):
            body = excerpt(r["text"], keywords, cfg["page_excerpt_chars"], intro_fallback=not brand_q)
            if body:
                full.append({**base, "text": f"{r.get('snippet') or ''}\n{body}".strip()})
                continue
        if r.get("snippet"):
            snippets.append({**base, "text": r["snippet"]})
    return (full + snippets)[: cfg["max_passages"]], dropped


def allowed_factors(question):
    """ปัจจัยที่ใช้ได้: ปัจจัยข้อมูลที่เกี่ยวกับคำถาม + ปัจจัยเว็บทั้งหมด (รวม "other")"""
    return list(dict.fromkeys([f for f in question.get("factor_hint") or [] if f in FACTORS] + WEB_FACTORS))


def build_payload(question, passages, period):
    return {
        "question": question["question_en"],
        "subject": {"level": question["level"], "brand": question.get("brand"),
                    "categories": question.get("categories"), "period": period},
        "facts": question.get("facts") or {},
        "factors": {f: FACTORS[f]["description"] for f in allowed_factors(question)},
        "passages": passages,
    }


def input_hash(payload):
    raw = json.dumps({"v": PROMPT_VERSION, "input": payload}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You explain changes in the Thai beauty and personal care market for a market report.
You receive ONE question about a measured change (the numbers in "facts" come from Euromonitor sales data or Thai FDA
product notifications), a closed list of factors, and numbered web passages (rid, source, date, title, text).

Task: find what the passages say is linked to the change in the question. Use only the passages and the facts. No outside
knowledge. Passages may be in Thai or English.

For each finding return:
- "factor": one id from "factors" (use "other" only if nothing fits)
- "relevance": "direct" if the passage itself talks about the subject's sales, share, sales channels, prices, customers or
  competition in Thailand; "background" if it is true about the subject but the passage does not connect it to sales or
  share in Thailand
- "statement_en": one plain English sentence (at most 30 words) saying what the sources report
- "statement_th": the same sentence in plain Thai (at most 40 Thai words)
- "evidence": 1-3 rids of passages that support it
- "quote": a short exact quote (5-25 words) copied character for character from ONE of the cited passages, in the
  passage's own language - no translation, no added or removed words

Rules:
- Only use passages about the question's subject (the brand, channel or category) in Thailand. Skip passages about other
  countries unless they clearly speak about Thailand, and skip product listings or ads with no information.
- Keep only findings that help explain the change in "facts" (its direction is given by the numbers). Skip general brand
  news (awards, events, launches abroad) unless the passage links it to sales, channels, prices, products, customers or
  competition in Thailand. Prefer "direct" findings.
- Say who says it. News: "News reports say ..." / "ข่าวรายงานว่า ...". The brand's own page, ad or press release:
  "The brand says ..." / "แบรนด์ระบุว่า ...". A market study: "A market report says ..." / "รายงานตลาดระบุว่า ...".
  Never state a brand's own claim (e.g. "trusted by doctors") as a fact.
- Report what sources say, not causes you infer. Write "is linked to", "sources report", "at the same time" - never
  "caused", "because of", "ทำให้" or "ส่งผลให้" unless the passage itself says so.
- Numbers: use only numbers that appear in "facts" or in the cited passage. Never calculate new numbers.
- Neutral wording: never say a brand won, lost, beat others or is a winner or loser. Describe what changed.
- Keep brand, company and category names exactly as given, in English, in both languages. Years in the Thai sentence use
  the Christian era (e.g. 2024).
- Plain language for brand and marketing readers: short sentences, everyday words. Never use YoY, CAGR, momentum, cohort,
  synergy, leverage.
- At most {max_findings} findings. Merge findings that say the same thing. One idea per finding.
- If no passage explains the change, return {{"findings": []}}. An empty answer is better than a weak one.

Return JSON only: {{"findings": [{{"factor": "...", "relevance": "direct", "statement_en": "...", "statement_th": "...",
"evidence": ["q18-r03"], "quote": "..."}}]}}"""


# ---------------------------------------------------------------------------
# ตรวจคำตอบ
# ---------------------------------------------------------------------------

def _norm(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def quote_in(quote, text):
    """ข้อความที่ยกมาอยู่ในหลักฐานจริง - เทียบแบบไม่สนตัวพิมพ์/ช่องว่างซ้ำ หรือแบบตัดช่องว่างทั้งหมด (ภาษาไทยไม่มีกติกา
    เว้นวรรคตายตัว LLM มักยกมาถูกแต่เว้นวรรคต่างจากต้นฉบับ) - ไม่ยอมให้คำต่างกันเลย"""
    q, t = _norm(quote), _norm(text)
    if q and q in t:
        return True
    q2, t2 = re.sub(r"\s+", "", q), re.sub(r"\s+", "", t)
    return len(q2) >= 15 and q2 in t2


def _numbers(text):
    """ตัวเลขในข้อความ -> รายการ float (ตัด , คั่นหลักพัน)"""
    return [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", str(text or ""))]


def _all_numbers(obj):
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in _all_numbers(v)]
    if isinstance(obj, list):
        return [n for v in obj for n in _all_numbers(v)]
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        return [float(obj)]
    if isinstance(obj, str):
        return _numbers(obj)
    return []


def number_ok(n, pool):
    """n มีใน pool (ยอมให้ปัดทศนิยมตามที่เขียน เช่น 13.71 -> 13.7, และแปลงปี พ.ศ. <-> ค.ศ.)"""
    decimals = len(str(n).split(".")[1].rstrip("0")) if "." in str(n) else 0
    for p in pool:
        if round(p, decimals) == round(n, decimals):
            return True
        if 1900 <= n <= 2100 and p == n + 543 or 2400 <= n <= 2700 and p == n - 543:
            return True
    return False


def check_finding(f, payload, max_findings=None):
    """finding ที่เก็บกวาดแล้ว หรือ (None, เหตุผล)"""
    if not isinstance(f, dict):
        return None, "not an object"
    factor = str(f.get("factor") or "").strip()
    if factor not in payload["factors"]:
        return None, f"factor not allowed: {factor}"
    relevance = str(f.get("relevance") or "").strip().lower()
    if relevance not in RELEVANCE:
        return None, f"bad relevance: {relevance}"
    en, th = _norm(f.get("statement_en")), str(f.get("statement_th") or "").strip()
    th = re.sub(r"\s+", " ", th)
    if not en or not th:
        return None, "missing statement"
    if THAI_RE.search(en) or not THAI_RE.search(th):
        return None, "wrong language"
    if JUDGEMENT_EN.search(en) or JUDGEMENT_TH.search(th):
        return None, "winner/loser wording"
    if BANNED_EN.search(en) or BANNED_TH.search(th):
        return None, "banned word"
    passages = {p["rid"]: p for p in payload["passages"]}
    rids = [r for r in (f.get("evidence") or []) if isinstance(r, str)]
    if not rids or any(r not in passages for r in rids):
        return None, f"unknown rid: {rids}"
    quote = _norm(f.get("quote"))
    if len(quote.split()) < 2 and len(quote) < 15:
        return None, "quote too short"
    if not any(quote_in(quote, passages[r]["title"] + " " + passages[r]["text"]) for r in rids):
        return None, "quote not found in cited passages"
    pool = _all_numbers(payload["facts"]) + _all_numbers(payload["question"]) + _all_numbers(payload["subject"])
    pool += [n for r in rids for n in _numbers(passages[r]["title"] + " " + passages[r]["text"])]
    bad = [n for n in _numbers(en) + _numbers(th) if not number_ok(n, pool)]
    if bad:
        return None, f"number not in facts or cited passages: {bad[:3]}"
    return {"factor": factor, "relevance": relevance,
            "statement_en": re.sub(r"\s+", " ", str(f["statement_en"])).strip(),
            "statement_th": th, "evidence": rids, "quote": re.sub(r"\s+", " ", str(f["quote"])).strip()}, None


def validate(parsed, payload, max_findings):
    """(findings ที่ผ่าน, เหตุผลที่ตัดทิ้ง) - คำตอบรูปแบบผิด = (None, [...])"""
    if not isinstance(parsed, dict) or not isinstance(parsed.get("findings"), list):
        return None, ["bad JSON shape"]
    kept, dropped = [], []
    for f in parsed["findings"][:max_findings]:
        ok, why = check_finding(f, payload)
        if ok:
            kept.append(ok)
        else:
            dropped.append(why)
    return kept, dropped


# ---------------------------------------------------------------------------
# รัน
# ---------------------------------------------------------------------------

def synthesize(questions, evidence, period, cache, cfg, llm_call=None, parse=json.loads, refresh=False, log=print):
    """ผลต่อคำถาม {qid: {...}} - ใช้ cache ถ้าข้อมูลที่ส่งเหมือนเดิม; ไม่มี llm_call = ใช้แค่ cache"""
    ev = {q["id"]: q["results"] for q in evidence}
    system = SYSTEM_PROMPT.format(max_findings=cfg["max_findings"])
    results, todo = {}, []
    for q in questions:
        passages, dropped = select_passages(q, ev.get(q["id"], []), period[0], cfg)
        payload = build_payload(q, passages, period)
        h = input_hash(payload)
        base = {"id": q["id"], "n_passages": len(passages), "dropped_evidence": dropped,
                "passages": {p["rid"]: {k: p[k] for k in ("source", "kind", "date", "title")} for p in passages}}
        cached = cache.get(q["id"])
        if cached and cached.get("input_hash") == h and not refresh:
            results[q["id"]] = {**base, **{k: cached[k] for k in ("findings", "rejected", "status")}, "from_cache": True}
        elif not passages:
            results[q["id"]] = {**base, "findings": [], "rejected": [], "status": "no_evidence"}
        else:
            todo.append((q, payload, h, base))

    def one(job):
        q, payload, h, base = job
        rejected, err = [], None
        for _ in range(2):   # ถามซ้ำ 1 ครั้งเมื่อคำตอบผิดรูปแบบ หรือมี finding แต่ไม่ผ่านเลยสักข้อ
            try:
                content = llm_call(system, json.dumps(payload, ensure_ascii=False), max_tokens=2500)
                kept, why = validate(parse(content), payload, cfg["max_findings"])
            except Exception as e:  # noqa: BLE001 - คำถามเดียวพังต้องไม่ล้มทั้งขั้น
                err, kept, why = e, None, [f"{type(e).__name__}: {str(e)[:120]}"]
            rejected += why
            if kept is not None and (kept or not why):
                return q, h, base, kept, rejected, None
        return q, h, base, None, rejected, err

    if todo and llm_call is not None:
        log(f"  LLM สรุปหลักฐาน {len(todo)} คำถาม...")
        with ThreadPoolExecutor(max_workers=cfg["llm_workers"]) as pool:
            for q, h, base, kept, rejected, err in pool.map(one, todo):
                if kept is None:
                    log(f"  ⚠️ {q['id']}: ไม่ได้คำตอบที่ผ่านการตรวจ ({'; '.join(rejected[-2:])[:160]})")
                    results[q["id"]] = {**base, "findings": [], "rejected": rejected, "status": "failed"}
                    continue
                status = "ok" if kept else "no_evidence"
                cache[q["id"]] = {"input_hash": h, "findings": kept, "rejected": rejected, "status": status,
                                  "created_at": datetime.now().isoformat(timespec="seconds")}
                results[q["id"]] = {**base, "findings": kept, "rejected": rejected, "status": status}
    for q, _, _, base in todo:
        results.setdefault(q["id"], {**base, "findings": [], "rejected": [], "status": "not_run"})
    return results


def aggregate_by_factor(questions, results):
    """ต่อปัจจัย: คำถาม / แบรนด์ / หมวด / จำนวนแหล่งอ้างอิง (โดเมนไม่ซ้ำ) - เรียงแบรนด์ตามตัวอักษร (ไม่ตัดสินชนะ/แพ้)"""
    by_q = {q["id"]: q for q in questions}
    out = {}
    for qid, r in results.items():
        q = by_q[qid]
        for f in r["findings"]:
            a = out.setdefault(f["factor"], {"questions": [], "brands": set(), "categories": set(), "sources": set(),
                                             "n_findings": 0, "n_direct": 0})
            a["n_findings"] += 1
            a["n_direct"] += f.get("relevance") == "direct"
            if qid not in a["questions"]:
                a["questions"].append(qid)
            if q.get("brand"):
                a["brands"].add(q["brand"])
            a["categories"].update(q.get("categories") or [])
            a["sources"].update(r["passages"][rid]["source"] for rid in f["evidence"] if rid in r["passages"])
    return {k: {"questions": v["questions"], "brands": sorted(v["brands"]), "categories": sorted(v["categories"]),
                "n_sources": len(v["sources"]), "n_findings": v["n_findings"], "n_direct": v["n_direct"]}
            for k, v in sorted(out.items(), key=lambda kv: list(FACTORS).index(kv[0]))}


def make_llm_call(bs):
    """เรียก LLM ของ tf ปัจจุบัน (ใช้ภายใน `with bs.use_bedrock():`) ตอบเป็น JSON - แบบเดียวกับ ⑯/⑰"""
    def llm_call(system, user, max_tokens=2500):
        response = bs.tf.client.chat.completions.create(
            model=bs.tf.MODEL_NAME_META,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0, max_tokens=max_tokens, response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    return llm_call


def main():
    parser = argparse.ArgumentParser(description="⑲ LLM สรุปหลักฐานเป็นปัจจัย พร้อมอ้างอิง (ตรวจด้วยโค้ด)")
    parser.add_argument("--run", default=None, help="ชื่อโฟลเดอร์ใน main/output (ไม่ใส่ = market_share_* ล่าสุด)")
    parser.add_argument("--only", nargs="*", default=None, help="เฉพาะคำถามเหล่านี้ เช่น q18 q20")
    parser.add_argument("--refresh", action="store_true", help="ถาม LLM ใหม่ ไม่ใช้ cache")
    parser.add_argument("--no-llm", action="store_true", help="ใช้แค่ cache")
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    run_dir = OUTPUT_ROOT / args.run if args.run else latest_run()
    if not run_dir or not (run_dir / EVIDENCE_FILE).exists():
        sys.exit(f"❌ ไม่มี {EVIDENCE_FILE} - รัน market_search.py ก่อน")
    qfile = json.loads((run_dir / QUESTIONS_FILE).read_text(encoding="utf-8"))
    evidence = json.loads((run_dir / EVIDENCE_FILE).read_text(encoding="utf-8"))["questions"]
    questions, period = qfile["questions"], qfile["meta"]["period"]
    if args.only:
        questions = [q for q in questions if q["id"] in args.only]
    cfg = {**SYNTH_DEFAULTS, **load_config()}
    out_path = run_dir / FINDINGS_FILE
    previous = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    cache = previous.get("cache", {})

    if args.no_llm:
        results = synthesize(questions, evidence, period, cache, cfg, refresh=False)
    else:
        import os
        os.environ["TREND_RUN_ID"] = run_dir.name   # ก่อน import bootstrap - ไม่งั้นได้โฟลเดอร์ adhoc_ ว่างเพิ่ม
        from common import bootstrap as bs
        with bs.use_bedrock():
            results = synthesize(questions, evidence, period, cache, cfg, make_llm_call(bs), bs.safe_json_parse,
                                 args.refresh)
    if args.only:   # เก็บผลของคำถามอื่นจากรอบก่อนไว้
        results = {**previous.get("results", {}), **results}
    all_questions = qfile["questions"]
    results = {q["id"]: results[q["id"]] for q in all_questions if q["id"] in results}
    output = {"meta": {"generated_at": datetime.now().isoformat(timespec="seconds"), "period": period,
                       "prompt_version": PROMPT_VERSION, "config": {k: cfg[k] for k in SYNTH_DEFAULTS},
                       "status": {s: sum(r["status"] == s for r in results.values())
                                  for s in ("ok", "no_evidence", "failed", "not_run")}},
              "by_factor": aggregate_by_factor([q for q in all_questions if q["id"] in results], results),
              "results": results, "cache": cache}
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")

    by_q = {q["id"]: q for q in all_questions}
    for qid, r in results.items():
        if args.only and qid not in args.only:
            continue
        print(f"\n{qid} [{r['status']}] {by_q[qid]['question_th'][:110]}  (หลักฐาน {r['n_passages']}, "
              f"ตัดทิ้ง {len(r['rejected'])})")
        for f in r["findings"]:
            print(f"   - [{FACTORS[f['factor']]['label_th']} / {f['relevance']}] {f['statement_th']}  {f['evidence']}")
    print(f"\nสถานะ: {output['meta']['status']}")
    print("ต่อปัจจัย:", {k: (v["n_findings"], v["n_sources"]) for k, v in output["by_factor"].items()})
    print(f"✅ {out_path}")


if __name__ == "__main__":
    main()
