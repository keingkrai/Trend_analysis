# -*- coding: utf-8 -*-
"""สาย Search ส่วน LLM (GLM-5 บน Bedrock): (1) รวมคำค้นที่กำลังขึ้นของแต่ละหมวด Google เป็นหัวข้อ 2 รอบ
(2) โยงหัวข้อไปหาเครื่องสำอางผ่าน 7 ทางโยงที่ตั้งไว้ล่วงหน้า + หมวดสินค้า Euromonitor L2 (ชุดเดียวกับ ⑫)
LLM ทำแค่งานภาษา: ตอบเป็น id ของคำค้น / ทางโยง / หลักฐาน - จำนวน ประเทศ ตัวอย่าง นับจากข้อมูลจริงในโค้ด
กฎ (โค้ด): หัวข้อที่โยงได้ต้องอ้างคำค้นตัวอย่างอย่างน้อย 1 คำ ไม่งั้นนับเป็นไม่โยง | หมวดสินค้าต้องอยู่ในรายการ
ย้ายจากการทดลอง output/_experiments/open_talk_20261027/ (themes_by_category.py, themes_other_pass.py, link_themes.py)"""
import json
import re
import time

MODEL = "zai.glm-5"
N_EXAMPLES = 12

GROUP_SYSTEM = """You summarise what people are searching for.
You get Google search queries that rose sharply over the last 12 months inside one Google Trends category, from one or more places
(TH = Thailand, WW = worldwide, other two-letter codes = countries). Queries may be in any language; Thai words may be split by spaces.

Group the queries into 6-15 themes that describe what people are searching for. A theme is a topic, event or need
(for example "Winter Olympics 2026", "state welfare card registration", "GLP-1 weight-loss drugs", "how-to cleaning tips"),
not a list of similar words. Every theme needs at least 3 queries. Put queries that fit no theme into one theme named "Other".
Google sometimes files queries under the wrong category; still group them by what they are about.
Use only the queries given. Do not add facts that the queries do not show.

Return JSON only:
{"themes":[{"name":"<short English name>","name_th":"<short Thai name>","about":"<one short English sentence>","ids":[<query ids>]}]}
Each query id goes into exactly one theme."""

REGROUP_SYSTEM = """You summarise what people are searching for.
You get Google search queries that rose sharply over the last 12 months and were filed by Google under one category,
from one or more places (TH = Thailand, WW = worldwide, other two-letter codes = countries). Queries may be in any language;
Thai words may be split by spaces. These queries were left over after a first grouping; the existing theme names are listed.

Group the queries into up to 20 NEW themes that describe what people are searching for. A theme is a topic, event or need,
not a list of similar words. Every theme needs at least 3 queries. Do not reuse an existing theme name.
Google often files queries under the wrong category; group them by what they are about, whatever category that is.
Queries that fit no theme of 3 or more stay out (do not list them). Use only the queries given; do not add facts.

Return JSON only:
{"themes":[{"name":"<short English name>","name_th":"<short Thai name>","about":"<one short English sentence>","ids":[<query ids>]}]}
Each query id goes into at most one theme."""

PATHS = {
    1: ("ความงามตรงๆ", "the theme itself is about a beauty or personal-care product, concern, look, treatment or routine"),
    2: ("สภาพแวดล้อม", "weather, season, heat, humidity, rain, air pollution or haze changes skin, hair, sweat or sun-protection needs"),
    3: ("ร่างกายและสุขภาพ", "a drug, symptom, condition, ageing or hormone with a visible effect on skin, hair, teeth or body odour"),
    4: ("โอกาสและเทศกาล", "a holiday, festival, ceremony, pageant, concert or gift occasion where people dress up, need long-wear or waterproof make-up, or buy beauty gifts"),
    5: ("กิจกรรมและไลฟ์สไตล์", "an activity people do (sport, running, gym, travel, outdoor) that creates a care need (sweat-proof sun care, body care, travel sizes)"),
    6: ("ส่วนผสมข้ามหมวด", "a food, drink, supplement or substance that is also used, or starting to be used, as a cosmetic ingredient"),
    7: ("วัฒนธรรมและลุค", "a show, star, idol or event whose specific look people copy - ONLY when at least one example query itself is a beauty query (make-up, hair, skin, nails, surgery) about it"),
}
PATH_EN = {1: "Direct beauty", 2: "Environment", 3: "Body & health", 4: "Occasions & festivals", 5: "Activities & lifestyle",
           6: "Cross-category ingredient", 7: "Culture & looks"}
PRODUCT_CATS = ["Skin Care", "Sun Care", "Hair Care", "Colour Cosmetics", "Fragrances", "Bath and Shower", "Deodorants",
                "Oral Care", "Men's Grooming", "Depilatories", "Makeup Tools & Equipment", "Baby and Child-specific Products",
                "Beauty and Personal Care"]

LINK_SYSTEM = ("You link themes of rising Google searches to beauty and personal care demand for a cosmetics manufacturer.\n"
               "Each theme has a name, a short description and numbered example searches with the places where they are rising.\n\n"
               "For each theme choose exactly one path:\n"
               + "\n".join(f"{k}: {v[1]}" for k, v in PATHS.items())
               + "\n0: no realistic link (most sport results, politics, finance, lottery, games, apps, AI tools, films without a copied look, general news).\n\n"
               "Rules:\n- Judge from the example searches, not from what you know about the topic. Be strict: when unsure, use 0.\n"
               "- For paths 1-7 give 'evidence': 1-3 example numbers that show the link. If no example shows it, use path 0.\n"
               "- 'cats': 1-2 product categories from this list only: " + "; ".join(PRODUCT_CATS)
               + " (use 'Beauty and Personal Care' only for gift sets or kits).\n"
               "- 'need': the beauty need in short Thai (at most 8 words), e.g. 'กันแดดกันเหงื่อ'.\n"
               "- 'reason': one short Thai sentence on why this theme moves that need. No marketing language, no product claims.\n"
               "For path 0 give only id and path.\n"
               'Return JSON only: {"links":[{"id":<theme id>,"path":<0-7>,"cats":["..."],"need":"...","reason":"...","evidence":[<example numbers>]}]}\n'
               "Return exactly one item per theme id.")


def cat_key(cat):
    return re.sub(r"[^A-Za-z0-9]+", "_", cat)


def _call(client, system, user, max_tokens, parse, ok, label):
    """เรียก LLM ซ้ำได้ 5 ครั้งจนผ่าน ok(parsed) - คืนผลที่ parse แล้ว หรือ None"""
    from common.bootstrap import safe_json_parse
    for attempt in range(5):
        try:
            r = client.chat.completions.create(
                model=MODEL, temperature=0, max_tokens=max_tokens, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            out = parse(safe_json_parse(r.choices[0].message.content) or {})
            if ok(out):
                return out
            print(f"  ⚠️ {label}: คำตอบไม่ครบ ลองใหม่", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ {label}: {str(e)[:120]}", flush=True)
        time.sleep(5 * (attempt + 1))
    print(f"  ❌ {label}: ไม่สำเร็จ", flush=True)
    return None


def group_category(client, cat, queries, cache):
    """queries = [{query_norm, query, geos, max_value}] ของ 1 หมวด -> {"themes": [{name, name_th, about, ids}], "queries": queries}
    รอบ 1 จัด 6-15 หัวข้อ + Other / รอบ 2 จัดคำที่เหลือเป็นหัวข้อเพิ่มไม่เกิน 20 - ที่จัดไม่ได้จริงอยู่ใน Other"""
    f = cache / f"{cat_key(cat)}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    ids = set(range(1, len(queries) + 1))

    def parse(d, valid):
        seen, out = set(), []
        for t in d.get("themes", []):
            t_ids = [i for i in t.get("ids", []) if isinstance(i, int) and i in valid and i not in seen]
            seen.update(t_ids)
            if t_ids:
                out.append({**t, "ids": t_ids})
        return out

    user = f"Category: {cat}\nQueries:\n" + "\n".join(f"{i} | {q['geos']} | {q['query']}" for i, q in enumerate(queries, 1))
    first = _call(client, GROUP_SYSTEM, user, 16000, lambda d: parse(d, ids),
                  lambda out: out is not None and len({i for t in out for i in t["ids"]}) >= 0.9 * len(ids), f"{cat} รอบ 1")
    if first is None:
        return None
    kept = [t for t in first if t.get("name", "").strip().lower() != "other"]
    used = {i for t in kept for i in t["ids"]}
    left = [i for i in sorted(ids) if i not in used]
    themes = kept
    if len(left) >= 3:
        user2 = ("Existing themes: " + "; ".join(t["name"] for t in kept) + "\nQueries:\n"
                 + "\n".join(f"{i} | {queries[i - 1]['geos']} | {queries[i - 1]['query']}" for i in left))
        second = _call(client, REGROUP_SYSTEM, user2, 16000,
                       lambda d: [t for t in parse(d, set(left)) if len(t["ids"]) >= 3], lambda out: out is not None, f"{cat} รอบ 2")
        themes = kept + (second or [])
    used = {i for t in themes for i in t["ids"]}
    rest = [i for i in sorted(ids) if i not in used]
    if rest:
        themes.append({"name": "Other", "name_th": "อื่นๆ", "about": "", "ids": rest})
    out = {"themes": themes, "queries": queries}
    cache.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    n_other = len(rest)
    print(f"  ✅ {cat}: {len(themes) - (1 if rest else 0)} หัวข้อ | อื่นๆ {n_other}/{len(queries)}", flush=True)
    return out


def theme_examples(grouped, theme):
    qs = grouped["queries"]
    return sorted((qs[i - 1] for i in theme["ids"]), key=lambda q: -(q["max_value"] or 0))


def link_category(client, cat, grouped, cache):
    """หัวข้อของ 1 หมวด -> [{theme, path, cats, need, reason, evidence, note}] (path 0 = ไม่โยง)"""
    f = cache / f"{cat_key(cat)}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    themes = [t for t in grouped["themes"] if t.get("name", "").strip().lower() != "other"]
    if not themes:
        return []
    examples = [[[q["query"], q["geos"]] for q in theme_examples(grouped, t)[:N_EXAMPLES]] for t in themes]
    user = f"Google category: {cat}\n\n" + "\n\n".join(
        f"Theme id={i}: {t.get('name', '')} / {t.get('name_th', '')}\nAbout: {t.get('about', '')}\nExamples:\n"
        + "\n".join(f"  {j}. {q} [{g}]" for j, (q, g) in enumerate(ex, 1))
        for i, (t, ex) in enumerate(zip(themes, examples), 1))
    want = set(range(1, len(themes) + 1))
    links = _call(client, LINK_SYSTEM, user, 12000,
                  lambda d: [x for x in d.get("links", []) if x.get("id") in want and x.get("path") in range(0, 8)],
                  lambda out: out is not None and len({x["id"] for x in out}) >= 0.95 * len(want), f"{cat} โยง")
    if links is None:
        return None
    out = []
    for x in links:
        t, ex = themes[x["id"] - 1], examples[x["id"] - 1]
        ev = [ex[j - 1][0] for j in x.get("evidence", []) or [] if isinstance(j, int) and 1 <= j <= len(ex)]
        path = x["path"]
        note = ""
        if path and not ev:   # กฎ: ไม่มีคำค้นตัวอย่างเป็นหลักฐาน = ไม่โยง
            path, note = 0, "no evidence"
        out.append({"theme": t.get("name", ""), "path": path, "cats": [c for c in x.get("cats", []) or [] if c in PRODUCT_CATS][:2] if path else [],
                    "need": x.get("need", "") if path else "", "reason": x.get("reason", "") if path else "",
                    "evidence": ev if path else [], "note": note, "llm_path": x["path"]})
    cache.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  ✅ {cat}: โยงได้ {sum(1 for o in out if o['path'])}/{len(out)} หัวข้อ", flush=True)
    return out
