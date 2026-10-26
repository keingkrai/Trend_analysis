# -*- coding: utf-8 -*-
"""
⑭-⑮ ภาพรวมตลาด + ข้อมูลพยากรณ์ที่ส่งเข้า STEPIC - คิดจากคะแนนการเติบโตของ ⑥ (growth_score.py) (2026-10-01)

เดิมสองจุดนี้มาจากผล ⑦ (z-score / Z_Delta): ข้อความสรุปตลาดกับป้าย 3 ช่องบนหน้า Market Overview ที่ LLM ของ ⑦ เลือกเอง
และข้อมูลพยากรณ์ที่ป้อนเข้า STEPIC (master_report) - ผลที่ได้คือข้อความบางตอนพูดถึง "breakout" ทั้งที่การจัดอันดับ
ในรายงานเปลี่ยนไปใช้การเติบโตที่คาดแล้ว ไฟล์นี้เป็นฟังก์ชันล้วน (ไม่เรียก LLM / ไม่อ่านไฟล์) ใช้ผล phase2_growth_score_result.json:

- market_snapshot: ภาพรวมตัวเลขของทุกเทรนด์ (มัธยฐานการเติบโตที่คาดปีที่ 1-5, จำนวนเทรนด์ที่สูงกว่าตลาด, ความยั่งยืน)
  🆕 (2026-10-02) 5 ปี: ระยะสั้น = ปีที่ 2 (SHORT_KEY), ระยะยาว = ปีที่ 5 (LONG_KEY) ตามที่เจ้าของงานกำหนด
  🆕 (2026-10-19) ระยะสั้น = ปีที่ 3 - ค่าอยู่ที่ common/horizons.py
- market_labels: ป้าย 3 ช่อง (Trend strength / Direction / Estimated duration) จากตัวเลขข้างบนด้วยกฎตายตัว - ไม่ให้ LLM เลือก
- stepic_growth_facts: ข้อความ JSON ต่อเทรนด์ที่ส่งเข้า STEPIC แทน master_report เดิม
- fallback_summary / market_overview: ข้อความสรุปตลาดสำรองที่ประกอบจากตัวเลข (ใช้เมื่อ LLM เขียนไม่ได้) และ dict ที่บันทึกลงไฟล์
"""
import json

import numpy as np

try:
    from common.horizons import LONG_KEY, LONG_RANGE, LONG_YEAR, SHORT_KEY, SHORT_RANGE, SHORT_YEAR, YEARS
except ImportError:      # รันไฟล์ตรงๆ จากโฟลเดอร์ common
    from horizons import LONG_KEY, LONG_RANGE, LONG_YEAR, SHORT_KEY, SHORT_RANGE, SHORT_YEAR, YEARS

HORIZON_KEYS = tuple(f"year_{y}" for y in YEARS)
# 🆕 (2026-10-19) ระยะสั้น/ระยะยาวอ่านจาก common/horizons.py ที่เดียว (เดิมเขียน "year_2" ตรงนี้ให้ตรงกับ bootstrap ด้วยคอมเมนต์)


def vs_market(score, line=0.5):
    """🆕 (2026-10-02) เทียบตลาดแค่ 2 ระดับ (เหนือ/ใต้ค่ากลาง) - เลิกใช้คำ "faster/slower (much)" ตามคำแนะนำ DA: จุดตัด 4 ระดับ
    เป็นค่าที่ตั้งเอง ไม่ได้ทดสอบ และ LLM จะยกคำนั้นไปเขียนต่อในรายงาน"""
    return None if score is None else ("above market median" if score >= line else "below market median")


# เกณฑ์ป้าย - ตั้งตามความคลาดเคลื่อนของโมเดลใน backtest ให้ป้ายสูง/ต่ำต่างจากศูนย์เกินระดับสัญญาณรบกวน ปรับได้ที่นี่ที่เดียว
# 🆕 (2026-10-02) ย้ายจากปีที่ 1/3 เป็นปีที่ 2/5 (ค่ากลางตลาดปีที่ 2 ~ +17%, ปีที่ 5 คลาดได้ราว ±25-50%) - ค่าที่ตั้งเอง
# 🆕 (2026-10-19) ระยะสั้นเปลี่ยนเป็นปีที่ 3: เกณฑ์ตั้งเป็น "% ต่อปีเฉลี่ย" (9.54 / 2.96 = ค่า 20 / 6 สะสมที่ปีที่ 2 เดิม) แล้วแปลงเป็นสะสมตามปี
# ระยะสั้น -> ป้ายความหมายเท่าเดิมไม่ว่าจะเปลี่ยนปี (ปีที่ 2 = 20.0 / 6.0 เหมือนเดิมเป๊ะ, ปีที่ 3 = 31.4 / 9.1) - ค่าที่ตั้งเองเช่นกัน
STRENGTH_PER_YEAR = (9.54, 2.96)
STRENGTH_FLOORS = tuple(round(((1 + p / 100) ** SHORT_YEAR - 1) * 100, 1) for p in STRENGTH_PER_YEAR)
# มัธยฐานการเติบโตที่คาดปีระยะสั้นของเทรนด์ (%): >= STRENGTH_FLOORS[0] Strong / >= STRENGTH_FLOORS[1] Moderate / ต่ำกว่า Weak
DIRECTION_BAND = 25.0            # มัธยฐานการเติบโตที่คาดปีที่ 5 (%): >= +25 Strengthening / <= -25 Weakening / ระหว่างนั้น Stable
DURATION_FLOORS = (70, 40)       # มัธยฐาน Longevity Score (0-100): >= 70 Long-term / >= 40 Medium-term / ต่ำกว่า Short-term


def expected_changes(cluster):
    """การเติบโตที่คาดทุกปีของ HORIZON_KEYS (%) ของเทรนด์ - None ถ้าไม่มีผลพยากรณ์ (หรือผล ⑥ รุ่นเก่าที่มีแค่ 3 ปี)"""
    change = (cluster.get("forecast") or {}).get("change_pct")
    ok = change and len(change) == len(HORIZON_KEYS) and all(v is not None for v in change)
    return [float(v) for v in change] if ok else None


def market_snapshot(clusters, durability_scores=(), line=0.5):
    """ภาพรวมตัวเลขของทุกเทรนด์ใน growth_score (clusters = ผล compute_growth_scores) - None ถ้าไม่มีเทรนด์ที่มีผลพยากรณ์
    line = ค่ากลางของตลาด (growth_score.GROWTH_LINE) - คะแนนตั้งแต่เส้นนี้ขึ้นไปคือ "สูงกว่าตลาด" """
    trends = []
    for c in clusters:
        change = expected_changes(c)
        if change is None:
            continue
        trends.append({"trend": c["trend"], "change_pct": change,
                       "scores": [c.get(f"score_y{h}") for h in range(1, len(HORIZON_KEYS) + 1)]})
    if not trends:
        return None
    si = HORIZON_KEYS.index(SHORT_KEY)
    trends.sort(key=lambda t: (-(t["scores"][si] or 0), -t["change_pct"][si]))
    changes = np.array([t["change_pct"] for t in trends], dtype=float)
    median = np.median(changes, axis=0)
    durability = [float(v) for v in durability_scores if v is not None]
    return {
        "n_trends": len(trends),
        "n_faster_than_market": {k: int(sum((t["scores"][i] or 0) >= line for t in trends))
                                 for i, k in enumerate(HORIZON_KEYS)},
        "median_change_pct": {k: round(float(median[i]), 1) for i, k in enumerate(HORIZON_KEYS)},
        "share_growing_pct": {k: round(float((changes[:, i] > 0).mean() * 100)) for i, k in enumerate(HORIZON_KEYS)},
        "median_durability": round(float(np.median(durability)), 1) if durability else None,
        "trends": trends,
    }


def duration_label(durability):
    """Longevity Score (0-100) -> Long-term / Medium-term / Short-term (None ถ้าไม่มีคะแนน)"""
    if durability is None:
        return None
    return ("Long-term" if durability >= DURATION_FLOORS[0] else
            "Medium-term" if durability >= DURATION_FLOORS[1] else "Short-term")


def market_labels(snapshot):
    """ป้าย 3 ช่องบนหน้า Market Overview (ชุดคำเดียวกับที่ LLM ของ ⑦ เคยเลือก - i18n แปลไทยได้เหมือนเดิม)"""
    short = snapshot["median_change_pct"][SHORT_KEY]
    long_ = snapshot["median_change_pct"][LONG_KEY]
    return {
        "current_trend_strength": ("Strong" if short >= STRENGTH_FLOORS[0] else
                                   "Moderate" if short >= STRENGTH_FLOORS[1] else "Weak"),
        "overall_direction": ("Strengthening" if long_ >= DIRECTION_BAND else
                              "Weakening" if long_ <= -DIRECTION_BAND else "Stable"),
        "estimated_trend_duration": duration_label(snapshot.get("median_durability")),
    }


def fallback_summary(snapshot):
    """ข้อความสรุปตลาดประกอบจากตัวเลขล้วนๆ - ใช้เมื่อ LLM เขียนไม่ได้ (หรือรันแบบไม่เรียก LLM)"""
    med, n = snapshot["median_change_pct"], snapshot["n_trends"]
    lead = ", ".join(t["trend"] for t in snapshot["trends"][:3])
    return (f"Search interest across the {n} trends found is expected to change by a median of {med[SHORT_KEY]:+.0f}% "
            f"in year {SHORT_YEAR} and {med[LONG_KEY]:+.0f}% by year {LONG_YEAR}, compared with the last 12 months. "
            f"{snapshot['n_faster_than_market'][SHORT_KEY]} of {n} trends are above the market median in year {SHORT_YEAR}. "
            f"The highest expected are {lead}.")


def market_overview(snapshot, summary=None, query=None):
    """dict ที่บันทึกลง phase4_market_overview.json - โครงเดียวกับ market_overview ของ ⑦ (ป้าย 3 ช่อง + summary)
    เพิ่ม basis = ตัวเลขที่ใช้ตัดสินป้าย (หน้า Market Overview แสดงใต้ป้าย)"""
    out = {"query": query, **market_labels(snapshot), "summary": (summary or "").strip() or fallback_summary(snapshot),
           "summary_source": "llm" if (summary or "").strip() else "numbers",
           # 🆕 (2026-10-19) ชื่อคีย์กลาง (เดิม median_change_pct_year_2 / _year_5) + short_year / long_year บอกว่าตัวเลขนี้คิดที่ปีไหน -
           # ⑯ เทียบกับค่าปัจจุบันแล้วคิดใหม่เองเมื่อไฟล์เก่าเขียนตอนระยะสั้นเป็นปีอื่น (report_data.market_without_trends)
           "basis": {"short_year": SHORT_YEAR, "long_year": LONG_YEAR,
                     "median_change_pct_short": snapshot["median_change_pct"][SHORT_KEY],
                     "median_change_pct_long": snapshot["median_change_pct"][LONG_KEY],
                     "median_durability": snapshot.get("median_durability"),
                     "n_trends": snapshot["n_trends"]}}
    return out


def llm_facts(snapshot):
    """ข้อเท็จจริงที่ให้ LLM เขียนข้อความสรุปตลาด (เฉพาะตัวเลขของโมเดลการเติบโต - ไม่มี z-score)"""
    return {
        "n_trends": snapshot["n_trends"],
        "median_expected_change_pct": snapshot["median_change_pct"],
        "n_trends_faster_than_market": snapshot["n_faster_than_market"],
        "trends_fastest_first": [
            {"trend": t["trend"], "expected_change_pct": dict(zip(HORIZON_KEYS, t["change_pct"])),
             "short_term_vs_market": vs_market(t["scores"][HORIZON_KEYS.index(SHORT_KEY)])}
            for t in snapshot["trends"]],
    }


def stepic_growth_facts(clusters, keywords, selected, longevity, snapshot):
    """ข้อมูลพยากรณ์ที่ส่งเข้า STEPIC แทน master_report (z-score) เดิม - คืนข้อความ JSON
    clusters/keywords = ผล growth_score (compute_growth_scores) | selected = ชุด Top N ของ ⑪ (None = ทุกเทรนด์)
    longevity = {(stream, trend): แถว Longevity} จาก load_cross_source_longevity()
    ไม่ใส่การโตจริง 12 เดือนที่ผ่านมา: ข้อมูล Google Trends กระโดดทุกคำตั้งแต่ ส.ค. 2025 ตัวเลขนั้นจึงเกินจริงทุกเทรนด์
    และ LLM จะตีความเป็นกระแสพุ่ง"""
    words = {}
    for k in keywords or []:
        words.setdefault(k.get("cluster_name"), []).append(k["keyword"])
    by_name = {c["trend"]: c for c in clusters}
    picked = ([(s.get("stream"), s["trend"]) for s in selected] if selected is not None
              else [(None, c["trend"]) for c in clusters])
    trends = []
    for stream, name in picked:
        c = by_name.get(name)
        change = expected_changes(c) if c else None
        if change is None:
            continue
        lv = longevity.get((stream, name)) or {}
        trends.append({
            "trend": name,
            "keywords": words.get(name, []),
            "expected_search_growth_pct_vs_last_12_months": dict(zip(HORIZON_KEYS, change)),
            "growth_vs_market": {k: vs_market(c.get(f"score_y{i}")) for i, k in enumerate(HORIZON_KEYS, 1)},
            "durability": {"longevity_score": lv.get("Longevity Score"),
                           "band": str(lv.get("Longevity Band") or "").replace("_", " ") or None},
        })
    return json.dumps({
        "note": ("Model forecast of worldwide Google Trends search interest. expected_search_growth_pct_vs_last_12_months "
                 "= forecast average of each year 1-5 compared with the last 12 months (all vs the same base, "
                 f"not year over year). Short term = years {SHORT_RANGE}, long term = years {LONG_RANGE}. growth_vs_market compares each "
                 f"trend with the median of all keywords in the run. Later years are much less certain than years {SHORT_RANGE}."),
        "market": {"n_trends": snapshot["n_trends"] if snapshot else None,
                   "median_expected_growth_pct": (snapshot or {}).get("median_change_pct"),
                   f"n_trends_above_market_year_{SHORT_YEAR}": ((snapshot or {}).get("n_faster_than_market") or {}).get(SHORT_KEY)},
        "trends": trends,
    }, ensure_ascii=False)
