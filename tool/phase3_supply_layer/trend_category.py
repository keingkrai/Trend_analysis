# -*- coding: utf-8 -*-
"""
⑫/⑬ ชั้นอุปทาน — หมวดหลัก (L2) ของเทรนด์ โดยให้ LLM เลือก (เจ้าของงานเลือก 2026-10-08)

เดิมหมวดของเทรนด์ = หมวด L2 ที่มีสินค้า >= 20% ของ 1% แรกที่ embedding ใกล้เทรนด์ที่สุด - embedding จับคู่จาก "คำ" ในชื่อสินค้า
จึงพากันดึงสินค้าที่แค่มีคำซ้ำเข้ามา (กันแดดชื่อ "Barrier" ติดเทรนด์ Barrier Repair, สเปรย์ระงับกลิ่นกายติดเทรนด์น้ำหอม)
pilot 24 เทรนด์ (output/_experiments/llm_category/pilot_report.md): LLM เลือกหมวดหลักได้นิ่ง (ถามซ้ำได้หมวดเดิม 24/24) และตรงกับหมวดอันดับ 1
ของ embedding 22/24 - 2 เทรนด์ที่ไม่ตรง LLM ถูกกว่า; ส่วน "หมวดรอง" ไม่นิ่งและ LLM เติมกันแดดให้ทุกเทรนด์สกินแคร์ที่มีสารออกฤทธิ์
เจ้าของงานจึงเลือก: **หมวดต่อเทรนด์ = หมวดหลักหมวดเดียว ไม่นับหมวดควบคู่**

LLM เห็นตัวเทรนด์ (profile จาก ⑪ ครบทุกฟิลด์) + หลักฐานจาก embedding (จำนวนสินค้าต่อหมวดใน 1% แรก + สินค้าที่ใกล้ที่สุด 3 ชิ้นของแต่ละหมวด)
หลักฐานนี้มีสัญญาณรบกวนและบอกไว้ในพรอมต์ - ใช้ให้เห็นว่าร้านขายอะไรใกล้เทรนด์จริง แต่ให้ตัดสินจากความหมายของเทรนด์
(ไม่ส่งหลักฐานมา: เทรนด์กำกวมอย่าง Safe Inhalation Spray ได้ Sun Care เป็นหมวดหลัก - pilot แบบ A)

ผลเก็บในไฟล์ jsonl ต่อท้ายทุกคำตัดสิน (คีย์ = hash ของ เวอร์ชันพรอมต์ + โมเดล + ขนาดตลาด + ข้อความ profile) ⑫ กับ ⑬ จึงได้หมวดเดียวกันเสมอ
และรันซ้ำ/โหมดอัปเดตรอบเดิมได้คำตอบเดิม (LLM temperature 0 ก็ยังตอบไม่เหมือนเดิมเสมอไป) ตลาดเปลี่ยนขนาดหรือแก้พรอมต์ -> ตัดสินใหม่
LLM ตอบไม่ได้ (เครือข่าย/ตอบว่างซ้ำๆ) -> ใช้หมวดอันดับ 1 ของ embedding แทน (source = embedding_fallback) และไม่บันทึกลงไฟล์ จะได้ถามใหม่รอบหน้า

ฟังก์ชันที่เทสได้ (ไม่เรียก API): cache_key / build_evidence / evidence_text / parse_answer / ask (รับ client ปลอมได้) / decide(use_llm=False)
"""
import hashlib
import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MODEL = "zai.glm-5"
PROMPT_VERSION = "v1-2026-10-08"
WORKERS = 3          # ยิงพร้อมกันเกินนี้ GLM-5 ตอบว่างเป็นครั้งคราว (เจอใน pilot) - ลองใหม่พร้อมรอด้วย
MAX_ATTEMPTS = 6
MAX_TOKENS = 3000
EXAMPLES_PER_CATEGORY = 3

# L2 ฝั่งความงามที่ให้เลือก (ไม่รวม "Beauty and Personal Care" ที่เป็นแค่ถังชุด/เซ็ตทั่วไป) + คำอธิบายสั้นจาก L3/L4 ใน product_category.csv
CATEGORIES = {
    "Skin Care": "face and body skincare: cleansers, toners, serums, moisturisers/creams, anti-agers, acne treatments, masks, lip care, "
                 "eye care, exfoliants, make-up removers, body lotions, hand and foot care",
    "Hair Care": "shampoo, conditioner, hair masks/oils/serums, scalp and hair-loss treatments, hair colour, styling, perms",
    "Sun Care": "sunscreen (face and body), after-sun, self-tanning",
    "Colour Cosmetics": "make-up: foundation/concealer/BB-CC, powder, primer, blush/highlighter, eye make-up, mascara, brows, lip colour, nail polish, make-up sets",
    "Makeup Tools & Equipment": "brushes, sponges, puffs, curlers, tweezers, mirrors, make-up bags, brush cleaners, blotting papers",
    "Bath and Shower": "body wash, soap, bath additives, body powder, intimate hygiene and sanitary pads/tampons, hand sanitiser",
    "Deodorants": "deodorant sprays, roll-ons, sticks, creams, antiperspirants, deodorant wipes",
    "Fragrances": "perfume, eau de toilette/cologne, body mists, solid perfume, fragrance sets (premium and mass)",
    "Men's Grooming": "men's shaving, razors, pre/after-shave, men's skincare, beard care, men's toiletries and fragrances",
    "Depilatories": "hair removal: depilatory creams, epilators, women's razors, body-hair bleach",
    "Oral Care": "toothpaste, toothbrushes (manual/electric), mouthwash, floss, whitening, denture care, breath fresheners",
    "Baby and Child-specific Products": "baby/child toiletries, skin care, hair care, sun care, baby wipes, nappy rash treatments",
}

SYSTEM = """You assign a consumer trend to the ONE product category a retailer (Watsons Thailand, beauty and personal care) would stock to serve it.

CATEGORIES (closed list; use the name exactly):
{cats}

Answer with JSON only:
{{"category": "<category>", "reason": "<one short sentence in English>"}}

Rules
- Pick the category whose products a shopper would mainly buy to follow this trend.
- Decide from what the trend MEANS for the shopper (functional benefit, job to be done, point of difference), not from single keywords. A product that only shares a word, ingredient or claim with the trend does not make its category the trend's category (a sunscreen called "barrier" is not part of a barrier-repair skincare trend).
- Choose one category only - complementary categories (for example sunscreen next to a retinol trend) are not wanted.
"""

EVIDENCE = """
MARKET EVIDENCE (noisy): the {pool} products out of {n} in the store whose text is closest to this trend, counted per category, with the closest products of each. Similarity is word-based and can pull in products that only share a word, so use this to see what the store really sells near the trend but decide on the trend's meaning.
{lines}
"""

PROFILE_FIELDS = ("trend", "attribute", "functional_consequence", "psychosocial_consequence", "job_to_be_done",
                  "point_of_difference", "point_of_parity")


def system_prompt():
    return SYSTEM.format(cats="\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items()))


def trend_block(profile):
    f = lambda k: (profile.get(k) or "").strip() or "(none)"
    return (f"TREND: {profile['trend']}\nattribute (key ingredients/features): {f('attribute')}\n"
            f"functional consequence: {f('functional_consequence')}\npsychosocial consequence: {f('psychosocial_consequence')}\n"
            f"job to be done: {f('job_to_be_done')}\npoint of difference: {f('point_of_difference')}\n"
            f"point of parity: {f('point_of_parity')}")


def build_evidence(scored, pool_size, examples=EXAMPLES_PER_CATEGORY):
    """scored: สินค้าทั้งตลาดของเทรนด์ (dict มี group / brand / product_name / similarity) -> หลักฐานจาก pool = pool_size ชิ้นแรกที่ใกล้ที่สุด
    {"pool_size", "n_market", "counts": {หมวด: {"n", "examples": [(อันดับในตลาด, แบรนด์, ชื่อ)]}} เรียงจำนวนมาก -> น้อย}"""
    ranked = sorted(scored, key=lambda s: s["similarity"], reverse=True)
    counts = {}
    for rank, s in enumerate(ranked[:pool_size], 1):
        d = counts.setdefault(s["group"], {"n": 0, "examples": []})
        d["n"] += 1
        if len(d["examples"]) < examples:
            d["examples"].append((rank, s["brand"], s["product_name"]))
    return {"pool_size": min(pool_size, len(ranked)), "n_market": len(ranked),
            "counts": dict(sorted(counts.items(), key=lambda kv: -kv[1]["n"]))}


def evidence_text(ev):
    lines = []
    for g, d in ev["counts"].items():
        ex = "; ".join(f"#{r} {b} {n[:60]}" for r, b, n in d["examples"])
        lines.append(f"- {g}: {d['n']} of {ev['pool_size']} | closest: {ex}")
    return EVIDENCE.format(pool=ev["pool_size"], n=ev["n_market"], lines="\n".join(lines))


def cache_key(profile, n_market):
    """คีย์คำตัดสิน: เวอร์ชันพรอมต์ + โมเดล + ขนาดตลาด + ข้อความ profile ทุกฟิลด์ที่ LLM เห็น (แก้เนื้อหาเทรนด์/พรอมต์/โมเดล/ตลาด -> ตัดสินใหม่)"""
    raw = "\x1f".join([PROMPT_VERSION, MODEL, str(n_market)] + [(profile.get(k) or "").strip() for k in PROFILE_FIELDS])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def parse_answer(text):
    """คำตอบของ LLM -> {"category", "reason"} หรือ None (ไม่ใช่ JSON / หมวดไม่อยู่ในรายการ) - รับคำตอบที่ห่อด้วย code fence"""
    try:
        d = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip()))
    except (ValueError, TypeError):
        return None
    cat = d.get("category") if isinstance(d, dict) else None
    if cat not in CATEGORIES:
        return None
    return {"category": cat, "reason": str(d.get("reason") or "").strip()}


def ask(client, profile, evidence, sleep=time.sleep, model=MODEL):
    """ถาม LLM 1 เทรนด์ -> {"category", "reason"} หรือ None ถ้าลองครบ MAX_ATTEMPTS ครั้งแล้วยังไม่ได้คำตอบที่ใช้ได้ (ตอบว่าง/ไม่ใช่ JSON/หมวดแปลก/ล้มเหลว)"""
    user = trend_block(profile) + evidence_text(evidence)
    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = client.chat.completions.create(
                model=model, temperature=0, max_tokens=MAX_TOKENS, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system_prompt()}, {"role": "user", "content": user}])
            parsed = parse_answer(resp.choices[0].message.content)
            if parsed:
                return parsed
        except Exception as e:   # noqa: BLE001 - คำตอบว่าง/throttle เป็นครั้งคราวเมื่อยิงพร้อมกัน
            print(f"    ⚠️ เลือกหมวดเทรนด์ '{profile.get('trend', '?')[:40]}' ล้มเหลว: {str(e)[:100]}")
        sleep(3 * (attempt + 1))
    return None


def load_labels(path):
    out = {}
    if path and Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            out[d["key"]] = d
    return out


def append_label(path, row):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def fallback(evidence):
    """LLM ตอบไม่ได้ -> หมวดที่มีสินค้ามากที่สุดใน pool ของ embedding (ไม่บันทึกลง cache)"""
    counts = Counter({g: d["n"] for g, d in evidence["counts"].items()})
    cat = counts.most_common(1)[0][0] if counts else None
    return {"category": cat, "reason": "LLM unavailable - the category holding most of the closest products was used",
            "source": "embedding_fallback"}


def main_categories(entries, labels_path, pool_fraction=None, use_llm=True):
    """entries: {id: (profile, scored)} (scored = สินค้าทั้งตลาดของเทรนด์ มี group / brand / product_name / similarity)
    -> {id: {"category", "reason", "source"}} - หลักฐานคิดจาก 1% แรก (POOL_FRACTION ของ category_breakdown) ใช้ร่วมกันทั้ง ⑫ และ ⑬"""
    if pool_fraction is None:
        from category_breakdown import POOL_FRACTION as pool_fraction
    items = [(id_, profile, build_evidence(scored, max(1, round(len(scored) * pool_fraction))))
             for id_, (profile, scored) in entries.items()]
    return decide(items, labels_path, use_llm=use_llm)


def decide(items, labels_path, use_llm=True, workers=WORKERS):
    """items: [(id, profile, evidence)] -> {id: {"category", "reason", "source": "cache" | "llm" | "embedding_fallback"}}
    ไม่เรียก LLM เมื่อทุกเทรนด์มีคำตัดสินใน labels_path แล้ว (หรือ use_llm=False -> ที่ไม่มีใช้ embedding_fallback)"""
    labels = load_labels(labels_path)
    out, todo = {}, []
    for id_, profile, ev in items:
        key = cache_key(profile, ev["n_market"])
        hit = labels.get(key)
        if hit and hit.get("category") in CATEGORIES:
            out[id_] = {"category": hit["category"], "reason": hit.get("reason", ""), "source": "cache"}
        else:
            todo.append((id_, profile, ev, key))
    if todo and use_llm:
        from common.bootstrap import use_bedrock   # import ที่นี่ - ฟังก์ชันอื่นของไฟล์นี้เทสได้โดยไม่ต้องมี bootstrap/API
        with use_bedrock(model_id=MODEL) as client:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                answers = list(pool.map(lambda t: ask(client, t[1], t[2]), todo))
        for (id_, profile, ev, key), ans in zip(todo, answers):
            if ans:
                out[id_] = {**ans, "source": "llm"}
                append_label(labels_path, {"key": key, "trend": profile.get("trend"), "category": ans["category"],
                                           "reason": ans["reason"], "model": MODEL, "prompt_version": PROMPT_VERSION,
                                           "n_market": ev["n_market"], "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
    for id_, profile, ev, key in todo:
        if id_ not in out:
            out[id_] = fallback(ev)
            print(f"    ⚠️ '{profile.get('trend', '?')[:40]}': ใช้หมวดอันดับ 1 ของ embedding แทน LLM ({out[id_]['category']})")
    return out
