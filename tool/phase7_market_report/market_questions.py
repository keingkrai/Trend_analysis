# -*- coding: utf-8 -*-
"""
⑲ รายงานส่วนแบ่งตลาด — Phase 2: เลือกเรื่องจากข้อเท็จจริง (Phase 1) แล้วตั้งคำถาม + คำค้นตามกฎ (ไม่เรียก LLM/API)

ทำไมใช้กฎไม่ใช้ LLM: ตรวจย้อนได้ว่าทำไมเรื่องนี้ถูกเลือก, รันซ้ำได้คำถามเดิม, คุมจำนวน search (เสียโควตา SerpAPI) ได้ก่อนเริ่มค้น
คำถามและคำค้นทั้งหมดอยู่ในไฟล์ผลลัพธ์ให้คนตรวจก่อนรัน Phase 3

เรื่องระดับตลาด (ใช้ทุกหมวดที่มีขนาด >= min_category_share% ของตลาด):
    e-commerce        ส่วนแบ่งช่องทางออนไลน์ทั้งตลาด (เปลี่ยนทุกหมวด จึงถามครั้งเดียวทั้งตลาด)
    ช่องทางอื่น        1 คำถามต่อช่องทางที่เปลี่ยน >= channel_story_min_pp ในหมวดใดหมวดหนึ่ง (ไม่ถามช่องทาง "Other ...")
    concentration     หมวดที่ Others เปลี่ยน >= concentration_story_min_pp (หักแบรนด์ที่ Euromonitor เลิกแยกแล้ว)
    premium           หมวดที่สัดส่วน premium เปลี่ยน >= premium_story_min_pp
    นำเข้า (อย.)       สัดส่วนใบจดแจ้งนำเข้าทั้งตลาดเปลี่ยน >= import_story_min_pp
เรื่องระดับแบรนด์: หมวดใหญ่ focus_categories หมวดแรก หมวดละ brand_stories_per_category แบรนด์ที่ส่วนแบ่งเปลี่ยนมากที่สุด
    (ทั้งขึ้นและลง เทียบแบบรวมแบรนด์ที่ถูกรวมเข้ามาแล้ว) - แบรนด์ที่อยู่หลายหมวดรวมเป็นคำถามเดียว
    การเลือกด้วยขนาดการเปลี่ยนแปลงเป็นเรื่องภายในระบบ - คำถาม/รายงานใช้คำว่า "การเปลี่ยนแปลง" ไม่บอกว่าใครชนะหรือแพ้

ต่อคำถาม 4 คำค้น: เว็บ (อังกฤษ + ไทย) + ข่าว Google News (อังกฤษ + ไทย, kind="news") ค้นในไทย - ตัวกรองช่วงเวลา/engine
ใส่ตอนค้นจริงใน Phase 3

ผลลัพธ์:
    output/<รอบ>/phase7_market_questions.json

Usage:
    python tool/phase7_market_report/market_questions.py                 # รอบ market_share_* ล่าสุดที่มีผล Phase 1
    python tool/phase7_market_report/market_questions.py --run <ชื่อรอบ>
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from factors import FACTORS, WEB_FACTORS  # noqa: E402
from market_data import TOTAL_CATEGORY  # noqa: E402
from market_facts import ECOMMERCE, FACTS_FILE, OUTPUT_ROOT, load_config  # noqa: E402

QUESTIONS_FILE = "phase7_market_questions.json"
QUESTION_DEFAULTS = {"min_category_share": 2.0, "focus_categories": 6, "brand_stories_per_category": 3,
                     "max_brand_stories": 18, "channel_story_min_pp": 3.0, "concentration_story_min_pp": 5.0,
                     "premium_story_min_pp": 2.0, "import_story_min_pp": 10.0}

# คำค้นของหมวด (อังกฤษ, ไทย) - คำที่คนใช้ค้นจริง ไม่ใช่ชื่อหมวดของ Euromonitor
CATEGORY_TERMS = {
    TOTAL_CATEGORY: ("beauty products", "เครื่องสำอาง"),
    "Skin Care": ("skin care", "สกินแคร์"),
    "Hair Care": ("hair care shampoo", "แชมพู ดูแลเส้นผม"),
    "Colour Cosmetics": ("makeup", "เครื่องสำอาง เมคอัพ"),
    "Bath and Shower": ("body wash soap", "สบู่ ครีมอาบน้ำ"),
    "Men's Grooming": ("men's grooming", "ผลิตภัณฑ์ผู้ชาย"),
    "Oral Care": ("toothpaste", "ยาสีฟัน"),
    "Fragrances": ("perfume", "น้ำหอม"),
    "Baby and Child-specific Products": ("baby care products", "ผลิตภัณฑ์เด็ก"),
    "Deodorants": ("deodorant", "โรลออน ระงับกลิ่นกาย"),
    "Sun Care": ("sunscreen", "กันแดด"),
    "Depilatories": ("razor hair removal", "มีดโกน กำจัดขน"),
}
# คำค้นของช่องทางขาย (อังกฤษ, ไทย) - ช่องทางที่ไม่มีในนี้ (เช่น "Other Non-Grocery Retailers") ไม่ถูกตั้งเป็นคำถาม
OUTLET_TERMS = {
    # ไม่ใส่ชื่อแพลตฟอร์ม (Shopee/Lazada/TikTok) - ผลค้นหาจะเป็นหน้าแรกของแพลตฟอร์มแทนบทความ (ทดลองจริง 2026-10-12)
    ECOMMERCE: ("e-commerce online", "อีคอมเมิร์ซ ออนไลน์"),
    "Direct Selling": ("direct selling", "ธุรกิจขายตรง"),
    "Department Stores": ("department store counters", "ห้างสรรพสินค้า เคาน์เตอร์"),
    "Beauty Specialists": ("beauty retail stores", "ร้านเครื่องสำอาง"),
    "Pharmacies": ("pharmacy drugstore", "ร้านขายยา"),
    # ไม่ใส่ชื่อร้าน (Watsons/Boots) - ได้หน้าเว็บของร้านเองแทนบทความ (ทดลองจริง 2026-10-12: 19 ผล เนื้อหาเต็ม 0)
    "Health and Personal Care Stores": ("health and beauty store chains", "ร้านค้าปลีกสุขภาพและความงาม"),
    "Hair Salons": ("hair salon", "ร้านทำผม ซาลอน"),
    "Supermarkets": ("supermarket", "ซูเปอร์มาร์เก็ต"),
    "Hypermarkets": ("hypermarket", "ไฮเปอร์มาร์เก็ต"),
    "Convenience Stores": ("convenience store 7-Eleven", "ร้านสะดวกซื้อ เซเว่น"),
    "Small Local Grocers": ("traditional grocery store", "ร้านโชห่วย"),
}


# ---------------------------------------------------------------------------
# ตัวช่วยข้อความ
# ---------------------------------------------------------------------------

def _pct(x):
    return "n/a" if x is None else f"{x:.1f}%"


def _move_en(base, last, y0, y1, brand=False):
    """"1.0% in 2019 to 4.0% in 2025" - แบรนด์ที่ปีตั้งต้นยังไม่มีชื่อในข้อมูล (ส่วนแบ่ง 0) ใช้ "not listed" """
    start = f"not listed in {y0}" if brand and not base else f"{_pct(base)} in {y0}"
    return f"{start} to {_pct(last)} in {y1}"


def _move_th(base, last, y0, y1, brand=False):
    start = f"ยังไม่มีชื่อในข้อมูลปี {y0}" if brand and not base else f"{_pct(base)} ปี {y0}"
    return f"{start} เป็น {_pct(last)} ปี {y1}"


def _queries(en, th, news_en=None, news_th=None):
    """คำค้นเว็บ (อังกฤษ + ไทย) + คำค้นข่าว (Google News, kind="news") - ไม่ส่งคำค้นข่าว = ใช้คำเดียวกับเว็บ
    ทำไมมีข่าว: ค้นเว็บด้วยชื่อแบรนด์ได้หน้าขายสินค้ามากกว่าข่าวธุรกิจ (ทดลองจริง 2026-10-12: 20 จาก 34 คำถาม LLM ไม่พบ
    คำอธิบาย - หลักฐานเป็นหน้าขายของ/โปรโมชัน)"""
    return [{"q": en, "hl": "en", "gl": "th", "kind": "web"}, {"q": th, "hl": "th", "gl": "th", "kind": "web"},
            {"q": news_en or en, "hl": "en", "gl": "th", "kind": "news"},
            {"q": news_th or th, "hl": "th", "gl": "th", "kind": "news"}]


# ---------------------------------------------------------------------------
# เลือกหมวด
# ---------------------------------------------------------------------------

def eligible_categories(facts, cfg):
    """หมวดสินค้า (ไม่รวมทั้งตลาด) ที่มีขนาด >= min_category_share% ของตลาด เรียงใหญ่ -> เล็ก"""
    cats = [c for c in facts["categories"] if c != TOTAL_CATEGORY
            and (facts["market"][c]["share_of_total"] or 0) >= cfg["min_category_share"]]
    return sorted(cats, key=lambda c: -(facts["market"][c]["share_of_total"] or 0))


# ---------------------------------------------------------------------------
# เรื่องระดับตลาด
# ---------------------------------------------------------------------------

def ecommerce_story(facts, cats, cfg):
    y0, y1 = facts["meta"]["base_year"], facts["meta"]["last_year"]
    total = (facts["categories"][TOTAL_CATEGORY]["channel"] or {}).get("ecommerce") or {}
    base, last = total.get(str(y0)), total.get(str(y1))
    if base is None or last is None:
        return None
    per_cat = []
    for c in cats:
        e = (facts["categories"][c]["channel"] or {}).get("ecommerce") or {}
        per_cat.append({"category": c, "share_base": e.get(str(y0)), "share_last": e.get(str(y1))})
    en, th = OUTLET_TERMS[ECOMMERCE]
    return {
        "level": "market", "topic": ECOMMERCE, "factor_hint": ["channel_shift"], "categories": [TOTAL_CATEGORY],
        "facts": {"share_base": base, "share_last": last, "by_category": per_cat},
        "question_en": f"What is associated with online shops' share of beauty and personal care sales in Thailand "
                       f"moving from {_move_en(base, last, y0, y1)}?",
        "question_th": f"อะไรเกี่ยวข้องกับการที่ส่วนแบ่งยอดขายเครื่องสำอางและของใช้ส่วนตัวผ่านช่องทางออนไลน์ในไทย"
                       f"เปลี่ยนจาก {_move_th(base, last, y0, y1)}",
        "queries": _queries(f"Thailand beauty {en} market growth", f"ตลาดเครื่องสำอาง {th} ไทย เติบโต"),
    }


def outlet_stories(facts, cats, cfg):
    """1 คำถามต่อช่องทาง (ไม่รวม e-commerce) ที่เปลี่ยน >= channel_story_min_pp ในหมวดใดหมวดหนึ่ง - facts แสดงทุกหมวด
    ที่ช่องทางนั้นเปลี่ยน >= 1 จุด"""
    y0, y1 = facts["meta"]["base_year"], facts["meta"]["last_year"]
    by_outlet = {}
    for c in cats:
        for r in (facts["categories"][c]["channel"] or {}).get("leaves", []):
            if r["outlet"] in OUTLET_TERMS and r["outlet"] != ECOMMERCE and abs(r["change_pp"] or 0) >= 1:
                by_outlet.setdefault(r["outlet"], []).append({"category": c, **{k: r[k] for k in
                                                              ("share_base", "share_last", "change_pp")}})
    out = []
    for outlet, rows in by_outlet.items():
        if max(abs(r["change_pp"]) for r in rows) < cfg["channel_story_min_pp"]:
            continue
        rows.sort(key=lambda r: -abs(r["change_pp"]))
        main = rows[0]
        en, th = OUTLET_TERMS[outlet]
        cat_en, cat_th = CATEGORY_TERMS[main["category"]]
        detail_en = "; ".join(f"{r['category']} {_move_en(r['share_base'], r['share_last'], y0, y1)}" for r in rows)
        detail_th = "; ".join(f"{r['category']} {_move_th(r['share_base'], r['share_last'], y0, y1)}" for r in rows)
        out.append({
            "level": "market", "topic": outlet, "factor_hint": ["channel_shift"],
            "categories": [r["category"] for r in rows], "facts": {"by_category": rows},
            "question_en": f"What is associated with the change in the share of sales through {outlet} in Thailand "
                           f"({detail_en})?",
            "question_th": f"อะไรเกี่ยวข้องกับการเปลี่ยนแปลงส่วนแบ่งยอดขายของช่องทาง {outlet} ในไทย ({detail_th})",
            "queries": _queries(f"Thailand {en} {cat_en} sales", f"{th} {cat_th} ยอดขาย"),
        })
    return out


def concentration_stories(facts, cats, cfg):
    y0, y1 = facts["meta"]["base_year"], facts["meta"]["last_year"]
    out = []
    for f in facts["factors"]:
        if f["type"] != "concentration" or f["category"] not in cats:
            continue
        real = f["others_change_excl_dropped_pp"]
        if real is None or abs(real) < cfg["concentration_story_min_pp"]:
            continue
        c = f["category"]
        en, th = CATEGORY_TERMS[c]
        out.append({
            "level": "market", "topic": f"concentration:{c}", "factor_hint": ["concentration"], "categories": [c],
            "facts": {k: f[k] for k in ("others_base", "others_last", "others_change_pp", "dropped_share_base",
                                        "others_change_excl_dropped_pp", "dropped_brands", "top5_base", "top5_last",
                                        "new_brands")},
            "question_en": f"What is associated with the combined share of smaller brands (outside the brands tracked "
                           f"by name) in {c} in Thailand moving from {_move_en(f['others_base'], f['others_last'], y0, y1)}?",
            "question_th": f"อะไรเกี่ยวข้องกับการที่ส่วนแบ่งรวมของแบรนด์เล็ก (นอกรายชื่อแบรนด์หลัก) ในหมวด {c} ของไทย"
                           f"เปลี่ยนจาก {_move_th(f['others_base'], f['others_last'], y0, y1)}",
            "queries": _queries(f"Thailand {en} market new local brands competition",
                                f"ตลาด{th} แบรนด์ใหม่ แบรนด์ไทย แข่งขัน"),
        })
    return out


def premium_stories(facts, cats, cfg):
    y0, y1 = facts["meta"]["base_year"], facts["meta"]["last_year"]
    out = []
    for f in facts["factors"]:
        if f["type"] != "premium_shift" or f["category"] not in cats or abs(f["change_pp"]) < cfg["premium_story_min_pp"]:
            continue
        c = f["category"]
        en, th = CATEGORY_TERMS[c]
        out.append({
            "level": "market", "topic": f"premium:{c}", "factor_hint": ["premium_shift"], "categories": [c],
            "facts": {k: f[k] for k in ("share_base", "share_last", "change_pp", "share_forecast")},
            "question_en": f"What is associated with premium products' share of {c} sales in Thailand moving from "
                           f"{_move_en(f['share_base'], f['share_last'], y0, y1)}?",
            "question_th": f"อะไรเกี่ยวข้องกับการที่ส่วนแบ่งของสินค้าพรีเมียมในหมวด {c} ของไทย"
                           f"เปลี่ยนจาก {_move_th(f['share_base'], f['share_last'], y0, y1)}",
            "queries": _queries(f"Thailand premium {en} market luxury brands", f"{th} พรีเมียม แบรนด์หรู ตลาดไทย"),
        })
    return out


def import_story(facts, cats, cfg):
    """สัดส่วนใบจดแจ้ง อย. ที่เป็นสินค้านำเข้า (ปีเต็มแรก -> ปีเต็มล่าสุด) ทั้งตลาด"""
    fda = facts["categories"][TOTAL_CATEGORY].get("fda")
    if not fda or not fda.get("import_share"):
        return None
    years = sorted(fda["import_share"], key=int)
    y0, y1 = years[0], years[-1]
    base, last = fda["import_share"][y0], fda["import_share"][y1]
    if base is None or last is None or abs(last - base) < cfg["import_story_min_pp"]:
        return None
    per_cat = [{"category": c, "share_base": (facts["categories"][c]["fda"] or {}).get("import_share", {}).get(y0),
                "share_last": (facts["categories"][c]["fda"] or {}).get("import_share", {}).get(y1)}
               for c in cats if facts["categories"][c].get("fda")]
    return {
        "level": "market", "topic": "fda_imports", "factor_hint": ["launch_activity"], "categories": [TOTAL_CATEGORY],
        "facts": {"share_base": base, "share_last": last, "years": [int(y0), int(y1)], "by_category": per_cat},
        "question_en": f"What is associated with imported products' share of new cosmetic notifications at the Thai FDA "
                       f"moving from {_move_en(base, last, y0, y1)}?",
        "question_th": f"อะไรเกี่ยวข้องกับการที่สัดส่วนสินค้านำเข้าในใบจดแจ้งเครื่องสำอางใหม่ของ อย. "
                       f"เปลี่ยนจาก {_move_th(base, last, y0, y1)}",
        "queries": _queries("Thailand imported cosmetics brands China Korea growth",
                            "เครื่องสำอางนำเข้า แบรนด์จีน เกาหลี ตลาดไทย"),
    }


# ---------------------------------------------------------------------------
# เรื่องระดับแบรนด์
# ---------------------------------------------------------------------------

def brand_stories(facts, focus, cfg):
    """แบรนด์ที่ส่วนแบ่งเปลี่ยนมากที่สุดในหมวด focus (หมวดละ brand_stories_per_category) รวมหลายหมวดเป็นแบรนด์เดียว
    เรียงตามหมวดใหญ่ -> เล็ก แล้วตามขนาดการเปลี่ยนแปลงในหมวด - เกิน max_brand_stories ตัดจากท้าย (หมวดเล็ก)"""
    y0, y1 = facts["meta"]["base_year"], facts["meta"]["last_year"]
    factor_types = {}
    for f in facts["factors"]:
        factor_types.setdefault(f["category"], []).append(f["type"])
    stories = {}
    for c in focus:
        for m in facts["categories"][c]["brands"]["movers"][:cfg["brand_stories_per_category"]]:
            s = stories.setdefault(m["brand"], {"brand": m["brand"], "owner": m["owner"], "tier": m["tier"],
                                                "name_th": m.get("name_th"), "fda_by_year": m.get("fda_by_year"),
                                                "fda_first_year": m.get("fda_first_year"), "rows": []})
            s["name_th"] = s["name_th"] or m.get("name_th")
            s["rows"].append({"category": c, "share_base": m["share_base"], "share_last": m["share_last"],
                              "change_pp": m["change_pp"], "absorbed": m.get("absorbed")})
    out = []
    for s in list(stories.values())[:cfg["max_brand_stories"]]:
        b, rows = s["brand"], s["rows"]
        main = max(rows, key=lambda r: abs(r["change_pp"] or 0))
        en, th = CATEGORY_TERMS[main["category"]]
        hints = (sorted({t for r in rows for t in factor_types.get(r["category"], [])})
                 + [f for f in WEB_FACTORS if f != "other"])
        detail_en = "; ".join(f"{r['category']} {_move_en(r['share_base'], r['share_last'], y0, y1, brand=True)}"
                              for r in rows)
        detail_th = "; ".join(f"{r['category']} {_move_th(r['share_base'], r['share_last'], y0, y1, brand=True)}"
                              for r in rows)
        # ข่าวไทยมักเขียนชื่อแบรนด์ไทยเป็นภาษาไทย (มิสทีน, กิฟฟารีน) - คำค้นไทยใส่ทั้งสองชื่อถ้ามีชื่อไทยใน อย.
        name_th = s.get("name_th")
        th_name = f'"{b}" OR "{name_th}"' if name_th and name_th != b else f'"{b}"'
        out.append({
            "level": "brand", "topic": b, "brand": b, "factor_hint": hints, "categories": [r["category"] for r in rows],
            "facts": {k: s[k] for k in ("owner", "tier", "name_th", "fda_by_year", "fda_first_year")}
                     | {"by_category": rows},
            "question_en": f"What is associated with the change in {b}'s share in Thailand ({detail_en})?",
            "question_th": f"อะไรเกี่ยวข้องกับการเปลี่ยนแปลงส่วนแบ่งของ {b} ในไทย ({detail_th})",
            # ข่าว: แค่ชื่อแบรนด์ (+ ประเทศไทย) - ข่าวธุรกิจไม่ค่อยมีคำว่า "market sales" ตรงๆ
            "queries": _queries(f'"{b}" Thailand {en} market sales', f"{th_name} {th} ยอดขาย ตลาด",
                                f'"{b}" Thailand', th_name),
        })
    return out


# ---------------------------------------------------------------------------
# รวม
# ---------------------------------------------------------------------------

def build_questions(facts, cfg):
    cats = eligible_categories(facts, cfg)
    focus = cats[:cfg["focus_categories"]]
    market = [ecommerce_story(facts, cats, cfg), *outlet_stories(facts, cats, cfg),
              *concentration_stories(facts, cats, cfg), *premium_stories(facts, cats, cfg),
              import_story(facts, cats, cfg)]
    questions = [q for q in market if q] + brand_stories(facts, focus, cfg)
    period = [facts["meta"]["base_year"], facts["meta"]["last_year"]]
    for i, q in enumerate(questions, 1):
        q["id"] = f"q{i:02d}"
        q["period"] = period
        q.setdefault("brand", None)
    return {
        "meta": {"generated_at": datetime.now().isoformat(timespec="seconds"), "period": period,
                 "eligible_categories": cats, "focus_categories": focus, "n_questions": len(questions),
                 "n_searches_planned": sum(len(q["queries"]) for q in questions),
                 "config": {k: cfg[k] for k in QUESTION_DEFAULTS}},
        "factors": FACTORS,
        "questions": questions,
    }


def latest_run():
    runs = [d for d in OUTPUT_ROOT.glob("market_share_*") if (d / FACTS_FILE).exists()]
    return max(runs, key=lambda d: (d / FACTS_FILE).stat().st_mtime) if runs else None


def main():
    parser = argparse.ArgumentParser(description="⑲ ตั้งคำถาม + คำค้นจากข้อเท็จจริงส่วนแบ่งตลาด (ไม่เรียก API)")
    parser.add_argument("--run", default=None, help="ชื่อโฟลเดอร์ใน main/output (ไม่ใส่ = market_share_* ล่าสุด)")
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    run_dir = OUTPUT_ROOT / args.run if args.run else latest_run()
    if not run_dir or not (run_dir / FACTS_FILE).exists():
        sys.exit(f"❌ ไม่มี {FACTS_FILE} - รัน market_facts.py ก่อน")
    facts = json.loads((run_dir / FACTS_FILE).read_text(encoding="utf-8"))
    cfg = {**QUESTION_DEFAULTS, **load_config()}
    result = build_questions(facts, cfg)
    out = run_dir / QUESTIONS_FILE
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    m = result["meta"]
    print(f"รอบ {run_dir.name} | หมวดที่ใช้ {len(m['eligible_categories'])} (แบรนด์จาก {len(m['focus_categories'])} หมวดใหญ่)")
    for q in result["questions"]:
        print(f"  {q['id']} [{q['level']:6s}] {q['question_th'][:150]}")
    print(f"\nคำถาม {m['n_questions']} ข้อ = search ที่จะใช้ใน Phase 3 ประมาณ {m['n_searches_planned']} ครั้ง")
    print(f"✅ {out}")


if __name__ == "__main__":
    main()
