# -*- coding: utf-8 -*-
"""
⑭-⑮ ข้อความวิเคราะห์ต่อเทรนด์ (cluster_analysis) จากโมเดลการเติบโตของ ⑥ แทน Step 6-7 ของ ⑦ (2026-10-01)

เดิม LLM ของ ⑦ เขียนวิเคราะห์ต่อเทรนด์ (trend_stage / primary_driver / executive_summary / consumer_intent_signal ...) โดยเห็นแต่
ผล z-score ซึ่งไหลเข้ารายงาน md หัวข้อ 4 และเป็นข้อมูลตั้งต้นของข้อความหัวเรื่องบนหน้าเทรนด์ในรายงาน PDF ไฟล์นี้เป็นฟังก์ชันล้วน
(ไม่เรียก LLM / ไม่อ่านไฟล์) ที่ทำให้ผลชุดเดียวกันมาจากโมเดลการเติบโต:

- ป้ายชุดคำตายตัว (trend_stage, primary_driver, estimated_duration) คิดด้วยกฎจากเส้นทางการเติบโตที่คาด ความแกว่งตามฤดูกาล และ
  Longevity Score - ไม่ให้ LLM ตัดสิน (หลักการเดียวกับ compute_investment_signal: ตัวเลข/ป้ายมาจากกฎ LLM แค่อธิบายเหตุผล)
- ข้อความ (executive_summary, consumer_intent_signal, driver_explanation, risk_scenario_if_forecast_fails) LLM เรียบเรียงจาก
  trend_facts() เท่านั้น ข้อความที่อ้างตัวเลข % ที่ไม่อยู่ในข้อเท็จจริงของเทรนด์นั้นจะถูกทิ้งและใช้ประโยคสำรองที่ประกอบจากตัวเลขแทน
- โครง dict ต่อเทรนด์ตรงกับ cluster_analysis ของ ⑦ (ชื่อฟิลด์เดิม) รายงาน md และ enrich.py อ่านต่อได้โดยไม่ต้องแก้ - ไม่มี
  investment_signal (เดิมคิดจาก Z_Delta) และ confidence_level
"""
import re

from common import market_overview as mo

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
# ความแกว่งตามฤดูกาล = (ตัวคูณเดือนสูงสุด - ต่ำสุด) x 100 (ตัวคูณเฉลี่ย = 1): รอบ 082438 กันแดด/สเปรย์ 72-109 เทรนด์อื่นไม่เกิน 28
SEASON_SWING_PCT = 50.0
TEXT_FIELDS = ("executive_summary", "consumer_intent_signal", "driver_explanation", "risk_scenario_if_forecast_fails")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?%")


def seasonality(seasonal):
    """ตัวคูณฤดูกาล 12 เดือน (growth_score.seasonal_factors) -> {"swing_pct", "peak_months", "strong"} หรือ None"""
    if not seasonal or len(seasonal) != 12:
        return None
    swing = (max(seasonal) - min(seasonal)) * 100
    top = sorted(sorted(range(12), key=lambda i: -seasonal[i])[:2])
    return {"swing_pct": round(swing), "peak_months": [MONTHS[i] for i in top], "strong": swing >= SEASON_SWING_PCT}


def _short_long(change):
    """(ระยะสั้น, ระยะยาว) = การเติบโตที่คาดปีที่ SHORT_YEAR และปีที่ LONG_YEAR (%) - 🆕 (2026-10-02) เดิมปีที่ 1 และ 3,
    🆕 (2026-10-19) ปีที่ 3 และ 5 (common/horizons.py)"""
    return change[mo.HORIZON_KEYS.index(mo.SHORT_KEY)], change[mo.HORIZON_KEYS.index(mo.LONG_KEY)]


def trend_stage(change):
    """เส้นทางที่คาด ปีที่ 1-5 (%) -> Declining / Stable / Peaking / Growing / Emerging (s = ปีระยะสั้น, l = ปีที่ 5)
    l ต่ำกว่า -DIRECTION_BAND = Declining, อยู่ในช่วง +-DIRECTION_BAND = Stable, สูงเกินแต่ไม่สูงกว่า s = Peaking (โตไปแล้ว
    แต่ต่อจากนี้แบน), สูงเกินและ s ถึง STRENGTH_FLOORS[1] = Growing, s ยังไม่ถึง (ค่อยๆ เร่งทีหลัง) = Emerging"""
    s, l = _short_long(change)
    if l <= -mo.DIRECTION_BAND:
        return "Declining"
    if l < mo.DIRECTION_BAND:
        return "Stable"
    if l <= s:
        return "Peaking"
    return "Growing" if s >= mo.STRENGTH_FLOORS[1] else "Emerging"


def primary_driver(change, season):
    """ลักษณะของเส้นทางที่คาด (ไม่ใช่สาเหตุ - เหตุผลให้ LLM อธิบายใน driver_explanation):
    ฤดูกาลชัด = Organic Seasonality, โตทั้งระยะสั้น (ปีที่ SHORT_YEAR) และระยะยาว (ปี 5) = Structural Growth, นอกนั้น Mixed/Uncertain"""
    if season and season["strong"]:
        return "Organic Seasonality"
    s, l = _short_long(change)
    if s >= mo.STRENGTH_FLOORS[1] and l >= mo.DIRECTION_BAND:
        return "Structural Growth"
    return "Mixed/Uncertain"


def trend_facts(cluster, keywords, row):
    """ข้อเท็จจริงของเทรนด์เดียว (ส่งให้ LLM + ใช้ทำป้าย/ประโยคสำรอง) - None ถ้าไม่มีผลพยากรณ์
    cluster = แถวเทรนด์ใน growth_score | keywords = คีย์เวิร์ดของเทรนด์ | row = แถว Longevity ข้ามแหล่ง (มี Key Ingredients /
    Key Benefits / Target / Longevity Score) หรือ {}"""
    change = mo.expected_changes(cluster)
    if change is None:
        return None
    row = row or {}
    season = seasonality((cluster.get("history") or {}).get("seasonal"))
    score = row.get("Longevity Score")
    return {
        "trend": cluster["trend"],
        "keywords": keywords,
        "key_ingredients": row.get("Key Ingredients") or None,
        "key_benefits": row.get("Key Benefits") or None,
        "target_consumer": row.get("Target") or None,
        "expected_search_growth_pct_vs_last_12_months": dict(zip(mo.HORIZON_KEYS, change)),
        "growth_vs_market": {k: mo.vs_market(cluster.get(f"score_y{i}")) for i, k in enumerate(mo.HORIZON_KEYS, 1)},
        "seasonality": ({"peak_months": season["peak_months"], "swing_pct": season["swing_pct"]}
                        if season and season["strong"] else None),
        "durability": {"longevity_score": score, "band": str(row.get("Longevity Band") or "").replace("_", " ") or None},
        "trend_stage": trend_stage(change),
        "primary_driver": primary_driver(change, season),
        "estimated_duration": mo.duration_label(score),
    }


def allowed_numbers(facts):
    """ตัวเลข % ที่ข้อความของเทรนด์นี้อ้างได้ (ทั้งแบบปัดเต็มและทศนิยม 1 ตำแหน่ง)"""
    values = [abs(v) for v in facts["expected_search_growth_pct_vs_last_12_months"].values()]
    if facts.get("seasonality"):
        values.append(facts["seasonality"]["swing_pct"])
    return {x for v in values for x in (float(round(v)), round(v, 1))}


def numbers_ok(text, allowed):
    """เลข % ทุกตัวในข้อความต้องอยู่ในชุดที่ให้ไว้ (ไม่มีเลข % เลยก็ผ่าน)"""
    return all(any(abs(float(m) - a) < 0.051 for a in allowed) for m in _PERCENT.findall(text))


def fallback_texts(facts):
    """ประโยคสำรองประกอบจากตัวเลข - ใช้เมื่อ LLM เขียนไม่ได้หรือข้อความไม่ผ่านการตรวจเลข"""
    g, vs = facts["expected_search_growth_pct_vs_last_12_months"], facts["growth_vs_market"]
    s_key, l_key, s_year, l_year = mo.SHORT_KEY, mo.LONG_KEY, mo.SHORT_YEAR, mo.LONG_YEAR       # 🆕 (2026-10-19) common/horizons.py
    words = ", ".join(facts["keywords"][:3])
    intent = (f"Consumers look for {facts['key_benefits']}." if facts.get("key_benefits")
              else f"Consumers search for {words}." if words else "")
    parts = [f"Search interest is expected to change {g['year_1']:+.0f}% in year 1, {g[s_key]:+.0f}% in year {s_year} and "
             f"{g[l_key]:+.0f}% in year {l_year} compared with the last 12 months ({vs[s_key]} in year {s_year})."]
    if facts.get("seasonality"):
        s = facts["seasonality"]
        parts.append(f"Interest is seasonal, peaking around {' and '.join(s['peak_months'])} (swing {s['swing_pct']}%).")
    d = facts["durability"]
    if d.get("longevity_score") is not None:
        parts.append(f"Durability score {d['longevity_score']}/100" + (f" ({d['band']})." if d.get("band") else "."))
    return {
        "executive_summary": (f"Search interest in {facts['trend']} is expected to change {g[s_key]:+.0f}% by year {s_year} and "
                              f"{g[l_key]:+.0f}% by year {l_year} compared with the last 12 months ({vs[s_key]} in year {s_year})."),
        "consumer_intent_signal": intent,
        "driver_explanation": " ".join(parts),
        "risk_scenario_if_forecast_fails": ("Actual search growth could fall short of the expected path; later years are "
                                            f"much less certain than years {mo.SHORT_RANGE}, so read the five-year figure as a direction."),
    }


def analysis_entry(facts, llm=None):
    """รวมป้ายตามกฎ + ข้อความจาก LLM (ผ่านการตรวจเลขแล้วเท่านั้น) / ประโยคสำรอง -> dict โครงเดียวกับ cluster_analysis ของ ⑦"""
    fallback, llm, allowed = fallback_texts(facts), llm or {}, allowed_numbers(facts)
    texts, from_llm = {}, 0
    for key in TEXT_FIELDS:
        value = re.sub(r"\s+", " ", llm.get(key)).strip() if isinstance(llm.get(key), str) else ""
        if value and numbers_ok(value, allowed):
            texts[key], from_llm = value, from_llm + 1
        else:
            texts[key] = fallback[key]
    return {
        "cluster_name": facts["trend"], "keywords": facts["keywords"],
        "trend_stage": facts["trend_stage"], "primary_driver": facts["primary_driver"],
        "estimated_duration": facts["estimated_duration"], **texts,
        "expected_search_growth_pct": facts["expected_search_growth_pct_vs_last_12_months"],
        "text_source": "llm" if from_llm == len(TEXT_FIELDS) else "mixed" if from_llm else "numbers",
    }
