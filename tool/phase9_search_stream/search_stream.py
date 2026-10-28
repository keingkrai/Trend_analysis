# -*- coding: utf-8 -*-
"""①-⑤ สาย Search (Google Trends) - ใช้แทน 3 สายเดิม Paper / Social / News ตั้งแต่ 2026-10-27 (เจ้าของงานสั่ง)

แนวคิด: เริ่มจากสิ่งที่คนค้นเพิ่มขึ้นจริงในทุกหมวดของ Google ไม่ใส่หัวข้อตั้งต้น แล้วค่อยโยงหาความต้องการเครื่องสำอาง
1) ดึงคำค้นที่กำลังขึ้นรายหมวด (rising.py) - ค่าเริ่มต้น ไทย + ทั่วโลก ทุกหมวดระดับ 1-2 (~600 search ต่อเดือน, cache รายเดือน)
2) LLM รวมคำค้นของแต่ละหมวดเป็นหัวข้อ 2 รอบ แล้วโยงหัวข้อไปหาเครื่องสำอางผ่าน 7 ทางโยง (themes.py)
3) คัดหัวข้อที่โยงได้ด้วยกฎตัวเลข (ขึ้นกี่พื้นที่ > มีไทย > จำนวนคำค้น) แล้วให้ LLM รวมหัวข้อที่เป็นความต้องการเดียวกัน
   และเขียนโปรไฟล์เทรนด์ฝั่งความงามจากคำค้นจริงเท่านั้น + คำค้นฝั่งความงามที่ ⑦ ใช้วัดการเติบโต
4) จุดตรวจ: เขียน phase2_search_candidates.csv - รันแบบโต้ตอบจะหยุดให้แก้คอลัมน์ keep (0 = ตัดทิ้ง) ก่อนไปต่อ
5) เขียน phase2_search_stream_result.json รูปแบบเดียวกับผลของสายเดิม (trends / keywords / report / documents) -> ⑦ เป็นต้นไปใช้ได้เลย

ค่าตั้ง (env): TREND_SEARCH_GEOS (ทุกหมวดระดับ 1-2, ค่าเริ่มต้น TH,WW) | TREND_SEARCH_GEOS_TOP (เฉพาะหมวดใหญ่, ค่าเริ่มต้นว่าง
เช่น US,JP,KR) | TREND_SEARCH_TOP_K (จำนวนเทรนด์ที่ส่งให้ ⑦, ค่าเริ่มต้น 20) | TREND_SEARCH_REVIEW=0 (ไม่หยุดให้ตรวจ)
งานกลางทางเก็บที่ <รอบ>/search_stream_work/ (รันซ้ำในรอบเดิมใช้ต่อ ไม่ถาม LLM ซ้ำ)
ใช้: python tool/phase9_search_stream/search_stream.py (main.py เรียกเป็นขั้นแรก)"""
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import quote

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.bootstrap import CHECKPOINTS, OUTPUTS, PROJECT_ROOT, use_bedrock  # noqa: E402
from common.streams import SEARCH_STREAM, STREAM_FILES  # noqa: E402
import rising  # noqa: E402
import themes as th  # noqa: E402

RESULT_FILE = STREAM_FILES[SEARCH_STREAM]
CANDIDATES_FILE = "phase2_search_candidates.csv"
WORK = OUTPUTS / "search_stream_work"
GEOS_DEEP = [g for g in (os.getenv("TREND_SEARCH_GEOS") or "TH,WW").split(",") if g.strip()]
GEOS_TOP = [g for g in (os.getenv("TREND_SEARCH_GEOS_TOP") or "").split(",") if g.strip()]
TOP_K = int(os.getenv("TREND_SEARCH_TOP_K") or 20)
CANDIDATE_POOL = 2 * TOP_K            # หัวข้อที่ส่งให้ LLM รวม/เขียนโปรไฟล์ (รวมแล้วเหลือไม่เกิน TOP_K เทรนด์)
QUOTA_RESERVE = 6 * TOP_K + 50        # โควตาที่ต้องเหลือให้ ⑦ (เทรนด์ละ ~5-6 คีย์เวิร์ด)
WORKERS = 5
DOC_CAP = 30                          # จำนวนรายการ (หมวด x พื้นที่) สูงสุดที่ใส่ในรายการแหล่งที่มาของรายงาน (60 ทำให้หน้า Source list ล้นกล่อง)
PLACE_EN = {"TH": "Thailand", "WW": "Worldwide"}

PROFILE_SYSTEM = """You turn rising Google search themes into beauty and personal care trends for a cosmetics manufacturer.
Each candidate already has a link path, product categories, a beauty need (Thai), evidence searches and example searches with places.

1) Merge candidates only when they describe the same beauty need (for example three haze or air-quality themes from different
   Google categories). Keep different needs separate.
2) For each trend write, in English unless marked Thai, using ONLY what the searches show:
   - trend_name: 3-7 words naming the beauty need and what drives it (for example "Haze-Season Skin Protection").
     No brand, person, show or event names.
   - key_ingredients: ingredients named in the searches, comma-separated; empty string if the searches name none.
   - key_benefits: 2-4 benefits the need implies, comma-separated.
   - target: who and where, from the places and searches (for example "Consumers in Singapore and Malaysia during haze").
   - outlook: 1-2 sentences restating what the searches show. No forecasts, no numbers that are not given.
   - analysis_th: one Thai sentence saying the same.
   - search_keywords: 3-6 English Google searches ordinary consumers type for the beauty-side need (lowercase, 1-4 words,
     generic, no brand/person/event names). These are used to measure search growth, so prefer stable everyday terms.
   - product_keywords: 2-4 product-type terms (for example "sweat-proof sunscreen").
Return JSON only:
{"trends":[{"ids":[<candidate ids>],"trend_name":"...","key_ingredients":"...","key_benefits":"...","target":"...",
"outlook":"...","analysis_th":"...","search_keywords":["..."],"product_keywords":["..."]}]}
Every candidate id appears in exactly one trend."""


def per_category_queries(rows):
    """{หมวดใหญ่: [{query_norm, query, geos, max_value, value}]} คำค้นไม่ซ้ำต่อหมวด (รวมทุกพื้นที่และหมวดย่อย)"""
    agg = {}
    for r in sorted(rows, key=lambda r: -(r["extracted_value"] or 0)):
        key = (r["l1"], r["query_norm"])
        a = agg.setdefault(key, {"query_norm": r["query_norm"], "query": r["query"], "geos": set(),
                                 "max_value": r["extracted_value"], "value": r["value"]})
        a["geos"].add(r["geo"])
    out = defaultdict(list)
    for (l1, _), a in agg.items():
        out[l1].append({**a, "geos": ",".join(sorted(a["geos"]))})
    return {k: sorted(v, key=lambda q: q["query_norm"]) for k, v in out.items()}


def run_llm(by_cat):
    groups, links = {}, {}
    with use_bedrock() as client:
        with ThreadPoolExecutor(WORKERS) as ex:
            for cat, g in zip(by_cat, ex.map(lambda c: th.group_category(client, c, by_cat[c], WORK / "themes"), by_cat)):
                groups[cat] = g
        ready = {c: g for c, g in groups.items() if g}
        with ThreadPoolExecutor(WORKERS) as ex:
            for cat, ln in zip(ready, ex.map(lambda c: th.link_category(client, c, ready[c], WORK / "links"), ready)):
                links[cat] = ln or []
    failed = [c for c, g in groups.items() if not g]
    if failed:
        print(f"  ⚠️ จัดหัวข้อไม่สำเร็จ {len(failed)} หมวด (ข้ามไป): {failed}")
    return groups, links


def linked_candidates(groups, links):
    """หัวข้อที่โยงได้ทุกหัวข้อ + ตัวเลขจากข้อมูลจริง เรียงด้วยกฎ: ขึ้นกี่พื้นที่ > มีไทย > จำนวนคำค้น > สัดส่วน Breakout"""
    out = []
    for cat, ln in links.items():
        by_name = {t.get("name", ""): t for t in groups[cat]["themes"]}
        for x in ln:
            t = by_name.get(x["theme"])
            if not x["path"] or not t:
                continue
            qs = th.theme_examples(groups[cat], t)
            places = sorted({g for q in qs for g in q["geos"].split(",")})
            out.append({"category": cat, "theme": t.get("name", ""), "theme_th": t.get("name_th", ""), "about": t.get("about", ""),
                        **{k: x[k] for k in ("path", "cats", "need", "reason", "evidence")}, "places": places,
                        "has_th": "TH" in places, "n_searches": len(qs),
                        "breakout_share": round(sum(q.get("value") == "Breakout" for q in qs) / max(len(qs), 1), 3),
                        "examples": [[q["query"], q["geos"]] for q in qs[:10]], "query_norms": [q["query_norm"] for q in qs]})
    out.sort(key=lambda c: (-len(c["places"]), not c["has_th"], -c["n_searches"], -c["breakout_share"]))
    return out


def clean_terms(terms, limit):
    seen, out = set(), []
    for t in terms or []:
        t = " ".join(str(t).lower().replace(",", " ").split())
        if t and len(t.split()) <= 4 and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:limit]


def build_profiles(candidates):
    """LLM รวมหัวข้อที่เป็นความต้องการเดียวกัน + เขียนโปรไฟล์เทรนด์ -> [{ids, trend_name, ...}] เรียงตามหัวข้อที่ดีที่สุดในกลุ่ม"""
    f = WORK / "profiles.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    user = "Candidates:\n\n" + "\n\n".join(
        f"id={i} | Google category: {c['category']} | theme: {c['theme']}\npath: {th.PATH_EN[c['path']]} | product categories: "
        f"{', '.join(c['cats'])} | need (Thai): {c['need']}\nplaces: {', '.join(c['places'])} | evidence: {' | '.join(c['evidence'])}\n"
        f"examples: {' | '.join(f'{q} [{g}]' for q, g in c['examples'])}"
        for i, c in enumerate(candidates, 1))
    want = set(range(1, len(candidates) + 1))
    with use_bedrock() as client:
        res = th._call(client, PROFILE_SYSTEM, user, 12000, lambda d: d.get("trends", []),
                       lambda out: out is not None and want <= {i for t in out for i in t.get("ids", []) if isinstance(i, int)},
                       "โปรไฟล์เทรนด์")
    if res is None:
        raise SystemExit("❌ เขียนโปรไฟล์เทรนด์ไม่สำเร็จ")
    seen, profiles = set(), []
    for t in res:
        ids = [i for i in t.get("ids", []) if isinstance(i, int) and i in want and i not in seen]
        kws = clean_terms(t.get("search_keywords"), 6)
        if not ids or not kws or not str(t.get("trend_name") or "").strip():
            continue
        seen.update(ids)
        profiles.append({**t, "ids": ids, "search_keywords": kws, "product_keywords": clean_terms(t.get("product_keywords"), 4)})
    profiles.sort(key=lambda p: min(p["ids"]))
    WORK.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(profiles, ensure_ascii=False, indent=1), encoding="utf-8")
    return profiles


def write_candidates(profiles, candidates):
    path = OUTPUTS / CANDIDATES_FILE
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["keep", "rank", "trend_name", "path", "product_categories", "need", "places", "n_searches",
                    "search_keywords", "source_themes", "evidence"])
        for i, p in enumerate(profiles, 1):
            cs = [candidates[j - 1] for j in p["ids"]]
            w.writerow([1 if i <= TOP_K else 0, i, p["trend_name"], " / ".join(sorted({th.PATHS[c["path"]][0] for c in cs})),
                        "; ".join(sorted({k for c in cs for k in c["cats"]})), " / ".join(dict.fromkeys(c["need"] for c in cs)),
                        ",".join(sorted({g for c in cs for g in c["places"]})), sum(c["n_searches"] for c in cs),
                        ", ".join(p["search_keywords"]), " | ".join(f"{c['category']}: {c['theme']}" for c in cs),
                        " | ".join(q for c in cs for q in c["evidence"])])
    return path


def review(path):
    """จุดตรวจก่อน ⑦ (เสียโควตา): รันแบบโต้ตอบ = หยุดให้แก้คอลัมน์ keep แล้วกด Enter / ไม่โต้ตอบหรือ TREND_SEARCH_REVIEW=0 = ข้าม"""
    if os.getenv("TREND_SEARCH_REVIEW", "1") == "0" or not sys.stdin.isatty():
        print(f"  ℹ️ ข้ามจุดตรวจ (ไม่ได้รันแบบโต้ตอบ หรือ TREND_SEARCH_REVIEW=0) - ใช้แถวที่ keep = 1 ใน {path.name}")
    else:
        print(f"\n🔎 จุดตรวจ: เปิด {path} แล้วแก้คอลัมน์ keep (1 = ใช้, 0 = ตัดทิ้ง) บันทึกไฟล์ แล้วกด Enter เพื่อไปต่อ")
        try:
            input("   กด Enter เมื่อพร้อม: ")
        except (EOFError, OSError):
            pass
    with open(path, encoding="utf-8-sig") as fh:
        return {int(r["rank"]) for r in csv.DictReader(fh) if str(r.get("keep", "")).strip() not in ("", "0")}


def documents(selected, candidates, rows):
    """รายการ (หมวด x พื้นที่) ที่มีคำค้นของเทรนด์ที่คัดไว้ -> แหล่งที่มาในรายงาน (เรียงตามจำนวนคำค้นที่ให้ ไม่เกิน DOC_CAP)"""
    norms = {q for p in selected for j in p["ids"] for q in candidates[j - 1]["query_norms"]}
    count = Counter((r["cat_id"], r["geo"], r["l1"], r["l2"]) for r in rows if r["query_norm"] in norms)
    docs = []
    for (cat_id, geo, l1, l2), n in count.most_common(DOC_CAP):
        place = PLACE_EN.get(geo, geo)
        link = f"https://trends.google.com/trends/explore?cat={cat_id}&date={quote(rising.DATE_RANGE)}" + (f"&geo={geo}" if geo != "WW" else "")
        docs.append({"title": f"Google Trends rising searches · {l1}{' > ' + l2 if l2 else ''} · {place}", "link": link,
                     "source": "Google Trends", "n_searches": n})
    return docs


def overview_text(meta, selected):
    lines = [f"Rising Google searches over the last 12 months ({', '.join(PLACE_EN.get(g, g) for g in meta['places'])}): "
             f"{meta['n_queries']:,} rising searches across {meta['n_categories']} Google categories were grouped into "
             f"{meta['n_themes']} themes; {meta['n_linked']} themes link to beauty and personal care demand. "
             f"{len(selected)} trends were picked from the most widely rising linked themes."]
    for i, p in enumerate(selected, 1):
        lines.append(f"{i}. {p['trend_name']} - {p.get('outlook', '')}")
    return "\n".join(lines)


def main():
    t0 = time.time()
    topic = (os.getenv("TREND_TOPIC") or "").strip() or "beauty and personal care"
    print("=" * 70)
    print(f"①-⑤ สาย Search (Google Trends คำค้นกำลังขึ้นรายหมวด) | ทุกหมวดระดับ 1-2: {','.join(GEOS_DEEP)}"
          + (f" | หมวดใหญ่: {','.join(GEOS_TOP)}" if GEOS_TOP else "") + f" | เทรนด์สูงสุด {TOP_K}")
    print("=" * 70)
    cats = rising.load_categories()
    jobs = rising.plan_jobs(cats, GEOS_DEEP, GEOS_TOP)
    folder = rising.cache_dir(CHECKPOINTS)
    print(f"1) ดึงคำค้นที่กำลังขึ้น {len(jobs)} รายการ (หมวด x พื้นที่)", flush=True)
    rising.fetch_all(jobs, folder, QUOTA_RESERVE)
    rows = rising.load_rows(jobs, folder, cats)
    by_cat = per_category_queries(rows)
    n_lists = sum(1 for g, c in jobs if (folder / f"{g}_{c}.json").exists())
    print(f"   ได้ {len(rows):,} แถว | คำค้นไม่ซ้ำ {len({r['query_norm'] for r in rows}):,} | {len(by_cat)} หมวดใหญ่ | {n_lists} รายการ")

    print("2) LLM จัดหัวข้อและโยงเครื่องสำอาง", flush=True)
    groups, links = run_llm(by_cat)
    n_themes = sum(1 for g in groups.values() if g for t in g["themes"] if t.get("name", "").strip().lower() != "other")
    candidates = linked_candidates(groups, links)
    print(f"   หัวข้อ {n_themes} | โยงเครื่องสำอางได้ {len(candidates)}")
    if not candidates:
        raise SystemExit("❌ ไม่มีหัวข้อที่โยงเครื่องสำอางได้ - ไม่มีเทรนด์ให้ขั้นต่อไป")

    pool = candidates[:CANDIDATE_POOL]
    print(f"3) รวมหัวข้อและเขียนโปรไฟล์เทรนด์จาก {len(pool)} หัวข้ออันดับต้น", flush=True)
    profiles = build_profiles(pool)
    path = write_candidates(profiles, pool)
    print(f"   ได้ {len(profiles)} เทรนด์ -> {path.name} (keep = 1 สำหรับ {min(TOP_K, len(profiles))} อันดับแรก)")
    for i, p in enumerate(profiles, 1):
        print(f"   {'✓' if i <= TOP_K else ' '} {i:>2}. {p['trend_name']}  [{', '.join(p['search_keywords'])}]")

    keep = review(path)
    selected = [p for i, p in enumerate(profiles, 1) if i in keep]
    if not selected:
        raise SystemExit("❌ ไม่มีเทรนด์ที่ keep = 1 - ไม่มีอะไรให้ขั้นต่อไป")

    trends, keywords = [], []
    for i, p in enumerate(selected, 1):
        cs = [pool[j - 1] for j in p["ids"]]
        members = list(dict.fromkeys([q for c in cs for q in c["evidence"]] + [q for c in cs for q, _ in c["examples"]]))[:15]
        trends.append({"Cluster ID": f"S{i}", "Rank": i, "Trend Name": p["trend_name"],
                       "Key Ingredients": p.get("key_ingredients") or "", "Key Benefits": p.get("key_benefits") or "",
                       "Members": ", ".join(members), "Cluster Size": sum(c["n_searches"] for c in cs),
                       "Target": p.get("target") or "", "Longevity Score": None, "Longevity Band": None,
                       "Outlook": p.get("outlook") or "", "Analysis (Thai)": p.get("analysis_th") or "",
                       "Link Paths": sorted({th.PATH_EN[c["path"]] for c in cs}),
                       "Link Path Ids": sorted({c["path"] for c in cs}),
                       "Product Categories": sorted({k for c in cs for k in c["cats"]}),
                       "Places": sorted({g for c in cs for g in c["places"]}),
                       "Source Themes": [{"category": c["category"], "theme": c["theme"], "need": c["need"],
                                          "evidence": c["evidence"]} for c in cs]})
        keywords.append({"Trend Name": p["trend_name"], "Search_Keywords": ", ".join(p["search_keywords"]),
                         "Marketing_Hooks": "", "Visual_Vibes": "", "Product_Search_Keywords": ", ".join(p["product_keywords"])})
    meta = {"n_lists": n_lists, "n_categories": len(by_cat), "places": GEOS_DEEP + [g for g in GEOS_TOP if g not in GEOS_DEEP],
            "n_queries": len({r["query_norm"] for r in rows}), "n_themes": n_themes, "n_linked": len(candidates),
            "n_trends": len(selected), "month": folder.name, "date_range": rising.DATE_RANGE}
    result = {"topic": topic, "stream": SEARCH_STREAM, "n_scraped": len(rows), "report": overview_text(meta, selected),
              "trends": trends, "keywords": keywords, "documents": documents(selected, pool, rows), "search_meta": meta,
              "_elapsed_seconds": round(time.time() - t0, 1)}
    out = OUTPUTS / RESULT_FILE
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    n_kw = len({k for p in selected for k in p["search_keywords"]})
    print(f"\n✅ {out.name}: {len(selected)} เทรนด์, {n_kw} คีย์เวิร์ดให้ ⑦ (~{n_kw} search) | {time.time() - t0:.0f} วินาที")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)
    main()
