# -*- coding: utf-8 -*-
"""
⑯ Category Deep-Dive — ข้อมูลของ "ส่วนที่ 2: เจาะรายหมวดของ Google" ในรายงานเทรนด์ ⑯ ของรอบสาย Search (2026-10-28)
เดิมรายงานหลักรวมเทรนด์ที่คัดจากทุกหมวดของ Google เข้าด้วยกัน - ส่วนนี้เปิดทีละหมวดว่าในหมวดนั้นคนค้นอะไรที่กำลังขึ้น (หัวข้อย่อยของหมวด)
และหัวข้อไหนโยงเข้าสินค้าความงาม (เดิมเป็นรายงานแยกเล่ม - รวมเข้ารายงานหลัก 2026-10-28; build_category_dive.py ยังสร้างเล่มแยกได้)

ไฟล์นี้เป็นส่วนข้อมูลล้วน (ไม่ import enrich/LLM - report_data import ได้) ข้อมูลมาจากโฟลเดอร์รอบ (search_stream_work/themes + links ที่ ① เขียนไว้ +
Source Themes ของเทรนด์) ไม่รัน ①-⑫ ใหม่ ไม่ใช้ SerpAPI:
  - หัวข้อย่อยต่อหมวด = กลุ่มคำค้นที่ AI จัดไว้ใน ① (themes.json); จำนวนคำค้น/พื้นที่ (ไทย / ทั่วโลก) / Breakout นับด้วยโค้ดจากข้อมูลจริง
  - "โยงความงาม" = ผลตรวจโยงของ ① (links.json: ทางโยง 1-7 + หมวดสินค้า) - ไม่เอาข้อความตีความของ AI (need / reason) มาแสดง
  - หัวข้อที่โชว์เรียงด้วยกฎเดียวกับตอนคัดเทรนด์: ขึ้นกี่พื้นที่ > มีไทย > จำนวนคำค้น > สัดส่วน Breakout
  - ประโยคอธิบายหัวข้อ (LLM + ตัวตรวจ) อยู่ที่ dive_text.py
ข้อมูลนี้บอกว่าอะไร "กำลังขึ้น" ตอนนี้ ไม่ใช่การพยากรณ์การเติบโตและไม่ใช่ปริมาณการค้นหา
"""
import json
from pathlib import Path

from common.streams import SEARCH_STREAM, STREAM_FILES
from search_talk import WORK, _norm, _qid, _read, category_names

FULL_PAGE_MIN_LINKED = 5            # หมวดที่มีหัวข้อโยงตั้งแต่เท่านี้ = 1 หน้าเต็ม; น้อยกว่า = ครึ่งหน้า (2 หมวดต่อหน้า)
N_LINKED_FULL = 6                   # หัวข้อโยงที่โชว์ต่อหมวด (หน้าเต็ม) - ครึ่งหน้าโชว์ทุกหัวข้อโยง (< FULL_PAGE_MIN_LINKED)
N_OTHER = {"full": 3, "half": 2}    # หัวข้อที่ไม่โยง (เทียบเป็นบริบท "ยังมีอะไรขึ้นในหมวดนี้")
N_EVIDENCE = 16                     # คำค้นต่อหัวข้อที่ส่งให้ LLM (เรียงตามอัตราที่ขึ้น)
N_SHOWN = 3                         # คำค้นตัวอย่างต่อหัวข้อ
PLACE_ORDER = ("TH", "WW")


def _where(places):
    """ชุดพื้นที่ของหัวข้อ -> "th" / "ww" / "both" (ป้ายในการ์ด)"""
    got = {p for p in places if p in PLACE_ORDER}
    return "both" if len(got) > 1 else ("th" if got == {"TH"} else "ww")


def _junk(text):
    """คำค้นที่เป็น URL / ลิงก์แปลกๆ ไม่เหมาะเป็นหลักฐานโชว์ในรายงาน"""
    t = str(text or "").lower()
    return "//" in t or t.startswith("www.") or ".app" in t or ".com" in t


def theme_stats(queries, theme):
    """หัวข้อ 1 หัวข้อ -> ตัวเลขจากข้อมูลจริง (ไม่ซ้ำคำค้น) + คำค้นเรียงตามอัตราที่ขึ้น"""
    ids = list(dict.fromkeys(i for i in theme.get("ids") or [] if isinstance(i, int) and 1 <= i <= len(queries)))
    qs = sorted((queries[i - 1] for i in ids), key=lambda q: -(q.get("max_value") or 0))
    places = sorted({g for q in qs for g in str(q.get("geos") or "").split(",") if g})
    clean = [q for q in qs if not _junk(q.get("query"))]
    return {
        "n": len(qs), "places": places, "has_th": "TH" in places, "where": _where(places),
        "breakout": sum(q.get("value") == "Breakout" for q in qs),
        "breakout_share": round(sum(q.get("value") == "Breakout" for q in qs) / max(len(qs), 1), 3),
        "searches": list(dict.fromkeys(str(q.get("query")) for q in clean))[:N_EVIDENCE],
        "ids": ids,
    }


def rank_key(t):
    """กฎเดียวกับ phase9_search_stream.linked_candidates: ขึ้นกี่พื้นที่ > มีไทย > จำนวนคำค้น > สัดส่วน Breakout"""
    return (-len(t["places"]), not t["has_th"], -t["n"], -t["breakout_share"], t["key"])


def _sources(result, trends):
    """{หมวด: {ชื่อหัวข้อ: {ชื่อเทรนด์: {rank, name, display_name}}}} ของเทรนด์ที่รายงานหลักแสดง (Source Themes)"""
    shown = {t["name"]: t for t in trends or []}
    out = {}
    for row in result.get("trends") or []:
        t = shown.get(row.get("Trend Name"))
        for s in (row.get("Source Themes") or []) if t else []:
            if s.get("category") and s.get("theme"):
                out.setdefault(s["category"], {}).setdefault(s["theme"], {})[t["name"]] = {
                    "rank": t.get("rank"), "name": t["name"], "display_name": t.get("display_name") or t["name"]}
    return out


def load_dive(run_dir, trends=None):
    """โฟลเดอร์รอบ -> dict ของส่วนเจาะรายหมวด หรือ None (ไม่ใช่รอบสาย Search / ไม่มีไฟล์ของ ①)
    trends = เทรนด์ที่รายงานหลักแสดง [{name, display_name, rank}] - ใช้ติดป้ายว่าหัวข้อไหนเป็นที่มาของเทรนด์ในรายงาน (ไม่ส่ง = ไม่มีป้าย)"""
    run_dir = Path(run_dir)
    work = run_dir / WORK
    result = _read(run_dir / STREAM_FILES[SEARCH_STREAM]) or {}
    if not (work / "themes").is_dir() or not result:
        return None
    names = category_names()
    sources = _sources(result, trends)
    cats, all_q, linked_q = [], set(), set()
    for f in sorted((work / "themes").glob("*.json")):
        d = _read(f) or {}
        queries = d.get("queries") or []
        if not queries:
            continue
        name = names.get(f.stem) or f.stem.replace("_", " ")
        place = {"th": 0, "ww": 0, "both": 0}
        for q in queries:
            all_q.add(_qid(q))
            place[{"TH": "th", "WW": "ww", "TH,WW": "both"}.get(q.get("geos"), "both")] += 1
        links = {x.get("theme"): x for x in _read(work / "links" / f.name) or []}
        themes = []
        for th in d.get("themes") or []:
            if not (th.get("name") or "").strip() or th["name"].strip().lower() == "other":
                continue
            stat = theme_stats(queries, th)
            if not stat["n"] or not stat["searches"]:   # ไม่มีคำค้นที่ใช้เป็นหลักฐานได้ (เช่น มีแต่ลิงก์) - ไม่ทำเป็นหัวข้อ
                continue
            x = links.get(th["name"]) or {}
            # หลักฐานของการโยง = คำค้นที่ขั้นตรวจโยงของ ① อ้าง (ตรวจว่าเป็นคำค้นของหัวข้อนี้จริง) - โชว์ 1-2 คำให้เห็นว่าทำไมจึงโยง
            have = {_norm(queries[i - 1].get("query")) for i in stat["ids"]}
            evidence = [e for e in dict.fromkeys(x.get("evidence") or []) if _norm(e) in have and not _junk(e)][:2]
            link = {"path": x["path"], "cats": [c for c in x.get("cats") or [] if c], "evidence": evidence} if x.get("path") else None
            card = {"key": th["name"], **stat, "link": link,
                    "trends": sorted(sources.get(name, {}).get(th["name"], {}).values(), key=lambda t: t.get("rank") or 99)}
            themes.append(card)
            if link:
                linked_q.update(_qid(queries[i - 1]) for i in stat["ids"])
        linked = sorted((t for t in themes if t["link"]), key=rank_key)
        others = sorted((t for t in themes if not t["link"]), key=rank_key)
        full = len(linked) >= FULL_PAGE_MIN_LINKED
        shown_linked = linked[:N_LINKED_FULL] if full else linked
        cats.append({
            "name": name, "key": f.stem, "n": len(queries), **place, "n_themes": len(themes), "n_linked": len(linked),
            "n_linked_searches": sum(t["n"] for t in linked), "full": full,
            "linked": shown_linked, "n_more": len(linked) - len(shown_linked),
            "others": others[:N_OTHER["full" if full else "half"]] if linked else [],   # หมวดที่ไม่มีหัวข้อโยงไม่มีหน้า - ไม่ต้องอธิบาย
            "trend_ranks": sorted({t["rank"] for c in linked for t in c["trends"] if t.get("rank")}),
        })
    if not cats:
        return None
    meta = result.get("search_meta") or {}
    cats.sort(key=lambda c: (-c["n_linked"], -c["n"], c["name"]))
    return {
        "places": list(meta.get("places") or []), "month": meta.get("month"),
        "n_searches": len(all_q), "n_linked_searches": len(linked_q),
        "linked_pct": round(len(linked_q) / len(all_q) * 100, 1) if all_q else 0.0,
        "n_categories": len(cats), "n_topics": sum(c["n_themes"] for c in cats), "n_linked_topics": sum(c["n_linked"] for c in cats),
        "categories": cats, "none_linked": [c["name"] for c in cats if not c["n_linked"]],
    }


def paginate(dive):
    """หมวดที่มีหัวข้อโยง -> หน้า: หมวดใหญ่ 1 หมวดต่อหน้า, หมวดเล็ก 2 หมวดต่อหน้า (เรียงตามเดิม) -> [{"full": bool, "cats": [หมวด]}]
    คำนวณตอนจัดหน้า (ไม่เก็บใน dive) - แก้ dive แล้วหน้าตามเสมอ"""
    pages, small = [], []
    for c in (dive or {}).get("categories") or []:
        if not c["n_linked"]:
            continue
        if c["full"]:
            pages.append({"full": True, "cats": [c]})
        else:
            small.append(c)
    pages += [{"full": False, "cats": small[i:i + 2]} for i in range(0, len(small), 2)]
    for p in pages:   # data-label ของหน้า (ภาษาอังกฤษเสมอ) - ใช้ในเทมเพลตและเลขหน้าอ้างอิงในหน้า Search Talk (pgref)
        names = [c["name"] for c in p["cats"]]
        p["label"] = f"Category {names[0]}" if p["full"] else "Categories " + " + ".join(names)
    return pages


def retag_dive(dive, trends):
    """ป้าย "ในรายงานหลัก: #n ชื่อ" ใช้ชื่อที่แสดง (display_name) ของเทรนด์ - เรียกหลัง display_names.apply_display_names"""
    shown = {t["name"]: t.get("display_name") or t["name"] for t in trends or []}
    for c in (dive or {}).get("categories") or []:
        for t in c["linked"] + c["others"]:
            for x in t["trends"]:
                x["display_name"] = shown.get(x["name"]) or x["display_name"]


def attach_linked_counts(talk, dive):
    """หน้า Search Talk: เติม n_linked (หัวข้อที่โยงความงาม) ให้แถวหมวดที่ชื่อตรงกัน"""
    linked = {c["name"]: c["n_linked"] for c in (dive or {}).get("categories") or []}
    for c in (talk or {}).get("categories") or []:
        c["n_linked"] = linked.get(c["name"], 0)


def localize_dive(dive, lang, place_text):
    """แก้ในตัว: ฉบับไทยใช้ประโยคหัวข้อภาษาไทย (คำค้นคงตามต้นฉบับ) - place_text = ข้อความพื้นที่ของภาษานั้น"""
    dive["places_text"] = place_text
    if lang == "th":
        for cat in dive["categories"]:
            for t in cat["linked"] + cat["others"]:
                t["topic"] = t.get("topic_th")
    return dive


def for_lang(dive, lang, place_text):
    """สำเนาของ dive สำหรับภาษาที่เลือก (ไม่แก้ของเดิม) - ใช้กับเล่มแยก build_category_dive.py"""
    return localize_dive(json.loads(json.dumps(dive, ensure_ascii=False)), lang, place_text)
