# -*- coding: utf-8 -*-
"""
Unit test ของ ⑲ Phase 2 (market_questions.py + factors.py) - ข้อเท็จจริงปลอมทั้งหมด ไม่เรียก API

รัน: pytest main/tool/tests/test_market_questions.py -v
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase7_market_report"))

from factors import DATA_FACTORS, FACTORS, WEB_FACTORS  # noqa: E402
from market_facts import category_factors  # noqa: E402
from market_questions import QUESTION_DEFAULTS, build_questions, eligible_categories  # noqa: E402

TOTAL = "Beauty and Personal Care"
CFG = {**QUESTION_DEFAULTS, "focus_categories": 2, "brand_stories_per_category": 2}
FORBIDDEN_EN = re.compile(r"\b(win|wins|winner|winners|lose|loses|loser|losers|losing)\b", re.I)


def _mover(brand, base, last, **kw):
    return {"brand": brand, "owner": brand + " Co", "tier": "mass", "share_base": base, "share_last": last,
            "change_pp": round(last - base, 2), "fda_by_year": None, "fda_first_year": None, **kw}


def _category(movers=(), leaves=(), ecom=(2.0, 15.0), others=(30.0, 40.0), dropped=(), premium=None, fda=None):
    return {
        "brands": {"movers": list(movers), "new_brands": [], "dropped_brands": list(dropped),
                   "others": {"2019": others[0], "2025": others[1]}, "top5": {"2019": 40.0, "2025": 35.0}},
        "channel": {"leaves": [{"outlet": o, "share_base": a, "share_last": b, "change_pp": round(b - a, 2)}
                               for o, a, b in leaves],
                    "ecommerce": {"2019": ecom[0], "2025": ecom[1]}},
        "premium": premium, "fda": fda,
    }


def _facts():
    cats = {
        TOTAL: _category(fda={"import_share": {"2021": 36.8, "2025": 51.3}, "change_pct": 5.0}),
        "Skin Care": _category(
            movers=[_mover("La Roche-Posay", 1.0, 4.0), _mover("Mistine", 3.0, 1.0), _mover("Olay", 2.0, 1.5)],
            leaves=[("Retail E-Commerce", 2.2, 16.7), ("Department Stores", 15.0, 10.9),
                    ("Other Non-Grocery Retailers", 6.0, 0.7), ("Direct Selling", 16.0, 14.4)],
            others=(35.1, 38.4)),
        "Colour Cosmetics": _category(
            movers=[_mover("Mistine", 10.0, 6.2, name_th="มิสทีน"), _mover("Kate", 0.0, 1.4)],
            leaves=[("Retail E-Commerce", 4.9, 22.6), ("Department Stores", 20.0, 11.5)],
            others=(27.2, 43.3), dropped=[{"brand": "Za", "share_base": 0.5, "last_year_seen": 2021, "merged_into": None}],
            premium={"share_base": 33.9, "share_last": 37.6, "change_pp": 3.7, "share_forecast": 38.9}),
        "Fragrances": _category(others=(36.3, 39.0),
                                dropped=[{"brand": "Genie", "share_base": 2.0, "last_year_seen": 2020, "merged_into": None}]),
        "Depilatories": _category(leaves=[("Hypermarkets", 20.0, 14.0)], others=(18.0, 30.0)),
    }
    shares = {TOTAL: 100.0, "Skin Care": 39.4, "Colour Cosmetics": 11.4, "Fragrances": 5.5, "Depilatories": 0.2}
    facts = {"meta": {"base_year": 2019, "last_year": 2025},
             "market": {c: {"share_of_total": s} for c, s in shares.items()},
             "categories": cats}
    cfg = {"channel_min_change_pp": 1.0, "concentration_min_change_pp": 1.0, "premium_min_change_pp": 1.0,
           "launch_min_change_pct": 10, "mover_min_share": 0.5, "_base": 2019, "_last": 2025}
    facts["factors"] = [f for c in cats for f in category_factors(c, cats[c], cfg)]
    return facts


def test_factor_list_is_closed_and_has_both_sources():
    assert set(DATA_FACTORS) == {"channel_shift", "concentration", "premium_shift", "launch_activity"}
    assert "other" in WEB_FACTORS
    assert all({"label_en", "label_th", "description", "source"} <= set(v) for v in FACTORS.values())


def test_eligible_categories_drop_tiny_and_sort_by_size():
    assert eligible_categories(_facts(), CFG) == ["Skin Care", "Colour Cosmetics", "Fragrances"]


def test_market_questions_ecommerce_once_and_outlets_grouped():
    qs = build_questions(_facts(), CFG)["questions"]
    topics = [q["topic"] for q in qs if q["level"] == "market"]
    assert topics.count("Retail E-Commerce") == 1
    dept = next(q for q in qs if q["topic"] == "Department Stores")
    assert dept["categories"] == ["Colour Cosmetics", "Skin Care"]          # เรียงตามขนาดการเปลี่ยน
    assert "Other Non-Grocery Retailers" not in topics                        # ค้นไม่ได้ ไม่ตั้งคำถาม
    assert "Direct Selling" not in topics                                     # เปลี่ยน 1.6 จุด < 3
    assert "Hypermarkets" not in topics                                       # อยู่ในหมวดเล็กเกิน


def test_concentration_uses_like_for_like_change():
    topics = [q["topic"] for q in build_questions(_facts(), CFG)["questions"]]
    assert "concentration:Colour Cosmetics" in topics       # +16.1 - 0.5 (Za) = +15.6
    assert "concentration:Fragrances" not in topics          # +2.7 - 2.0 (Genie) = +0.7
    assert "concentration:Skin Care" not in topics           # +3.3 < 5


def test_premium_and_import_questions():
    qs = {q["topic"]: q for q in build_questions(_facts(), CFG)["questions"]}
    assert "premium:Colour Cosmetics" in qs
    assert qs["fda_imports"]["facts"]["share_last"] == 51.3


def test_brand_questions_merge_categories_and_quote_brand():
    qs = [q for q in build_questions(_facts(), CFG)["questions"] if q["level"] == "brand"]
    assert [q["brand"] for q in qs] == ["La Roche-Posay", "Mistine", "Kate"]
    mistine = qs[1]
    assert mistine["categories"] == ["Skin Care", "Colour Cosmetics"]
    assert all('"Mistine"' in x["q"] for x in mistine["queries"])
    assert '"Mistine" OR "มิสทีน"' in mistine["queries"][1]["q"]              # ข่าวไทยเขียนชื่อไทย
    assert " OR " not in qs[0]["queries"][1]["q"]                              # ไม่มีชื่อไทยใน อย. = ชื่อเดียว
    assert "makeup" in mistine["queries"][0]["q"]                              # หมวดที่เปลี่ยนมากที่สุดของแบรนด์
    assert "not listed in 2019" in qs[2]["question_en"] and "ยังไม่มีชื่อในข้อมูลปี 2019" in qs[2]["question_th"]
    assert "other" not in mistine["factor_hint"] and "channel_shift" in mistine["factor_hint"]


def test_questions_are_neutral_and_counted():
    result = build_questions(_facts(), CFG)
    qs = result["questions"]
    assert [q["id"] for q in qs] == [f"q{i:02d}" for i in range(1, len(qs) + 1)]
    assert result["meta"]["n_searches_planned"] == 4 * len(qs)
    for q in qs:
        assert not FORBIDDEN_EN.search(q["question_en"]), q["question_en"]
        assert "ชนะ" not in q["question_th"] and "แพ้" not in q["question_th"]
        assert [(x["hl"], x["kind"]) for x in q["queries"]] == [("en", "web"), ("th", "web"), ("en", "news"),
                                                                 ("th", "news")]
        assert all(x["gl"] == "th" for x in q["queries"])


def test_brand_news_queries_are_name_only():
    mistine = next(q for q in build_questions(_facts(), CFG)["questions"] if q.get("brand") == "Mistine")
    assert [x["q"] for x in mistine["queries"][2:]] == ['"Mistine" Thailand', '"Mistine" OR "มิสทีน"']
