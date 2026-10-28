# -*- coding: utf-8 -*-
"""
⑯ PDF Report — หน้า "คนกำลังค้นหาอะไรมากขึ้น" ของรอบสาย Search (2026-10-28; แทนหน้า persona ที่คำค้นให้ข้อมูลไม่พอ)

ข้อมูลทั้งหมดมาจากโฟลเดอร์รอบ (search_stream_work/themes + links ที่ ① เขียนไว้ + Source Themes ของแต่ละเทรนด์) - ไม่เรียก API ไม่ใช้ LLM ในขั้นนี้:
  - จำนวนคำค้นที่กำลังขึ้นต่อหมวดหลักของ Google (ชื่อหมวดตามที่ Google ใส่) แยกไทย / ทั่วโลก / ทั้งสองพื้นที่ นับด้วยโค้ด
  - "ส่วนที่เป็นที่มาของเทรนด์ในรายงาน" = คำค้นในกลุ่มที่ป้อนเทรนด์ที่รายงานนี้แสดง (Source Themes ของเทรนด์) - ไม่ใช้ตัวเลขการโยงถึงความงามของ AI ทั้งหมด เพราะกลุ่มที่โยงแล้ว
    บางกลุ่ม (เช่น ผลบอล สภาพอากาศ) ไม่ได้เทรนด์ที่มีสินค้าจับคู่ได้ในรายงาน - ตัวเลขการโยงของ AI (n_link_check) ใช้แค่เล่าขั้นตอน
  - (เดิมมีการ์ดตัวอย่างคำค้นต่อหมวดเป็นหน้าที่ 2 - ถูกแทนที่ด้วยส่วนที่ 2 "เจาะรายหมวดของ Google" ของ category_dive.py เมื่อ 2026-10-28)
ข้อมูลนี้บอกว่าอะไร "กำลังขึ้น" ในการค้นหา ไม่ใช่สิ่งที่ถูกพูดถึงมากที่สุด (ไม่มีจำนวนครั้งที่ค้น)

ไม่ import bootstrap - เทสได้ด้วยโฟลเดอร์ปลอม
"""
import json
import re
from pathlib import Path

from common.streams import SEARCH_STREAM, STREAM_FILES

WORK = "search_stream_work"
GT_CATEGORIES = Path(__file__).resolve().parents[1] / "phase9_search_stream" / "gt_categories.json"
PLACE_KEYS = {"TH": "th", "WW": "ww", "TH,WW": "both"}


def cat_key(name):
    """ชื่อหมวด -> ชื่อไฟล์ (เหมือน phase9_search_stream/themes.py cat_key)"""
    return re.sub(r"[^A-Za-z0-9]+", "_", name)


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def category_names():
    """{ชื่อไฟล์: ชื่อหมวดตามที่ Google ใส่} จากรายการหมวดระดับ 1 ของ Google (gt_categories.json)"""
    data = _read(GT_CATEGORIES) or {}
    return {cat_key(c["name"]): c["name"] for c in data.get("children") or [] if c.get("name")}


def _norm(text):
    return " ".join(str(text or "").lower().split())


def _qid(q):
    return q.get("query_norm") or _norm(q.get("query"))


def _link_check_ids(themes, links):
    """ids (เริ่มที่ 1 = ลำดับในรายการคำค้นของหมวด) ของกลุ่มที่ขั้นตรวจโยงของ ① โยงถึงความงามแล้ว (link path <> 0)"""
    path = {x.get("theme"): x.get("path") or 0 for x in links or []}
    return {i for th in themes or [] if path.get(th.get("name")) for i in th.get("ids") or []}


def load_talk(run_dir, trends=None):
    """โฟลเดอร์รอบ -> dict ของหน้า "คนกำลังค้นหาอะไรมากขึ้น" หรือ None (ไม่ใช่รอบสาย Search / ไม่มีไฟล์ของ ①)
    trends = เทรนด์ของรายงาน [{name, display_name, rank}] - ใช้หาว่ากลุ่มคำค้นไหนเป็นที่มาของเทรนด์ที่รายงานแสดง (ไม่ส่ง = ไม่มีส่วนนั้น)"""
    run_dir = Path(run_dir)
    work = run_dir / WORK
    result = _read(run_dir / STREAM_FILES[SEARCH_STREAM]) or {}
    if not (work / "themes").is_dir() or not result:
        return None
    names = category_names()
    shown = {t["name"]: t for t in trends or []}
    sources = {}   # หมวด -> {ชื่อกลุ่ม: {"trends": {ชื่อเทรนด์: เทรนด์}}} ของเทรนด์ที่รายงานแสดงเท่านั้น
    for row in result.get("trends") or []:
        t = shown.get(row.get("Trend Name"))
        for s in (row.get("Source Themes") or []) if t else []:
            if s.get("category") and s.get("theme"):
                sources.setdefault(s["category"], {}).setdefault(s["theme"], {"trends": {}})["trends"][t["name"]] = t

    cats, all_q, check_q, fed_q = [], set(), set(), set()
    for f in sorted((work / "themes").glob("*.json")):
        d = _read(f) or {}
        queries = d.get("queries") or []
        if not queries:
            continue
        name = names.get(f.stem) or f.stem.replace("_", " ")
        place = {"th": 0, "ww": 0, "both": 0}
        for q in queries:
            place[PLACE_KEYS.get(q.get("geos"), "both")] += 1
            all_q.add(_qid(q))
        for i in _link_check_ids(d.get("themes"), _read(work / "links" / f.name)):
            if 1 <= i <= len(queries):
                check_q.add(_qid(queries[i - 1]))
        themes = {th.get("name"): th for th in d.get("themes") or []}
        fed_ids = set()
        for theme, g in sources.get(name, {}).items():
            ids = {i for i in (themes.get(theme) or {}).get("ids") or [] if 1 <= i <= len(queries)}
            if not ids:
                continue
            fed_ids |= ids
        for i in fed_ids:
            fed_q.add(_qid(queries[i - 1]))
        cats.append({"name": name, "n": len(queries), **place, "fed": len(fed_ids)})
    if not cats:
        return None
    cats.sort(key=lambda c: (-c["n"], c["name"]))
    meta = result.get("search_meta") or {}
    top = [{"name": c["name"], "fed": c["fed"]} for c in sorted(cats, key=lambda c: (-c["fed"], c["name"])) if c["fed"]][:2]
    return {
        "n_searches": len(all_q), "n_categories": len(cats), "places": list(meta.get("places") or []), "month": meta.get("month"),
        "n_link_check": len(check_q), "n_trends_built": meta.get("n_trends"), "n_trends_shown": len(shown) or None,
        "n_fed": len(fed_q), "fed_pct": round(len(fed_q) / len(all_q) * 100, 1) if all_q else 0.0,
        "n_no_fed": sum(1 for c in cats if not c["fed"]), "top_fed": top,
        "categories": cats,
    }


def trend_sources(run_dir, trend_names):
    """🆕 (2026-10-28) ต่อเทรนด์: จำนวนคำค้นที่กำลังขึ้นในกลุ่มที่ป้อนเทรนด์นี้ (ไม่ซ้ำ) + หมวดของ Google ที่คำค้นเหล่านั้นอยู่ (เรียงตามจำนวน) - โชว์ในกล่อง "คนกำลังค้นหาอะไร" ของหน้าเทรนด์
    -> {ชื่อเทรนด์: {"n": จำนวน, "categories": [ชื่อหมวด]}} เฉพาะเทรนด์ที่หาได้ (รอบที่ไม่ใช่สาย Search / ไม่มีไฟล์ = {})"""
    run_dir = Path(run_dir)
    work = run_dir / WORK
    result = _read(run_dir / STREAM_FILES[SEARCH_STREAM]) or {}
    if not (work / "themes").is_dir() or not result:
        return {}
    names = category_names()
    stems = {name: stem for stem, name in names.items()}
    cache, wanted, out = {}, set(trend_names or []), {}
    for row in result.get("trends") or []:
        if row.get("Trend Name") not in wanted:
            continue
        seen, by_cat = set(), {}
        for s in row.get("Source Themes") or []:
            cat = s.get("category")
            if not cat or not s.get("theme"):
                continue
            if cat not in cache:
                cache[cat] = _read(work / "themes" / f"{stems.get(cat) or cat_key(cat)}.json") or {}
            d = cache[cat]
            queries = d.get("queries") or []
            theme = next((th for th in d.get("themes") or [] if th.get("name") == s["theme"]), None)
            for i in (theme or {}).get("ids") or []:
                if 1 <= i <= len(queries):
                    q = _qid(queries[i - 1])
                    if q not in seen:
                        seen.add(q)
                        by_cat[cat] = by_cat.get(cat, 0) + 1
        if seen:
            out[row["Trend Name"]] = {"n": len(seen), "categories": [c for c, _ in sorted(by_cat.items(), key=lambda kv: (-kv[1], kv[0]))]}
    return out
