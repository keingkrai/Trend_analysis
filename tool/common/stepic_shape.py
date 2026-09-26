# -*- coding: utf-8 -*-
"""
STEPIC (⑭) — จัดรูปคำตอบของ LLM ทีละมิติให้เป็นแบบเดียว ก่อนเขียน Master Report (⑮) และหน้า STEPIC ใน PDF (⑯)

🆕 (2026-09-26) ปัญหาที่เจอจริง: tf2.analyze_trend() ขอ JSON แต่ไม่ได้บังคับโครง GLM-5 จึงตอบคนละโครงในแต่ละรอบ
- technology: รอบ 082438 = {"dimension", "analysis": {...}}, รอบ 111455 = {"trend_analysis": {"analysis": {...}}}
- creativity: บางรอบห่อไว้ใน {"creativity_analysis": {...}}
- industry: บางรอบช่อง market_structure / competitive_landscape เป็น dict ({"concept", "information", ...}) ไม่ใช่ข้อความ
ตัวเขียนรายงาน (trend_final_v2_subset.generate_master_markdown_report - สำเนาตรงตัว ห้ามแก้) อ่านช่องที่ชั้นบนสุด
เลยได้ "N/A" ทั้งมิติ (Technology ทั้ง 2 รอบ) หรือพิมพ์ dict ดิบออกมา (Industry รอบ 111455) และ PDF ข้ามมิติที่หาไม่เจอ

ไฟล์นี้ไม่ import bootstrap และไม่เรียก API - ใช้ได้ทั้งจาก step4_report และ step5_pdf และเทสได้ตรงๆ
"""

DIMENSIONS = ("society", "technology", "environment", "policy", "industry", "creativity")
_WRAPPERS = ("analysis", "trend_analysis")


def flatten_dimension(value, dim=""):
    """คำตอบของมิติเดียว -> dict ชั้นเดียว: แกะ dict ที่มีคีย์เดียวซ้อนอยู่ และยกช่องใน "analysis" / "trend_analysis" /
    "<มิติ>_analysis" ขึ้นมาชั้นบน (ช่องที่มีอยู่แล้วชั้นบนไม่ถูกทับ) - ค่าที่ไม่ใช่ dict คืนเป็น {}"""
    if not isinstance(value, dict):
        return {}
    wrappers = _WRAPPERS + (f"{dim}_analysis",)
    current = dict(value)
    for _ in range(5):  # ห่อซ้อนกันไม่เกินไม่กี่ชั้นในทางปฏิบัติ
        if len(current) == 1 and isinstance(next(iter(current.values())), dict):
            current = dict(next(iter(current.values())))
            continue
        key = next((k for k in wrappers if isinstance(current.get(k), dict)), None)
        if key is None:
            break
        inner = current.pop(key)
        current = {**inner, **current}
    return current


def normalize_stepic(raw):
    """ทั้ง 6 มิติ -> {มิติ: dict ชั้นเดียว} (มิติที่ไม่มีได้ {}) - โครงข้อมูลข้างในยังเหมือนเดิม (list/dict ไม่ถูกแปลง)"""
    raw = raw if isinstance(raw, dict) else {}
    return {dim: flatten_dimension(raw.get(dim), dim) for dim in DIMENSIONS}


def as_text(value):
    """ค่าของช่อง -> ข้อความสำหรับแสดงผล: dict ที่มี concept/information -> "concept: information",
    dict อื่น -> "คีย์: ค่า; ...", list -> คั่นด้วย "; " - ค่าว่างได้ "" """
    if value is None:
        return ""
    if isinstance(value, dict):
        head, body = value.get("concept"), value.get("information")
        if head or body:
            return ": ".join(str(x) for x in (head, body) if x)
        return "; ".join(f"{k.replace('_', ' ')}: {as_text(v)}" for k, v in value.items() if as_text(v))
    if isinstance(value, (list, tuple)):
        return "; ".join(as_text(v) for v in value if as_text(v))
    return str(value).strip()


def stepic_for_report(raw):
    """สิ่งที่ส่งให้ generate_master_markdown_report(): จัดรูปแล้ว และทุกช่องเป็นข้อความ (ไม่มี dict/list ดิบไปโผล่ในรายงาน)"""
    report = {}
    for dim, fields in normalize_stepic(raw).items():
        if fields:
            report[dim] = {k: as_text(v) for k, v in fields.items()}
    return report


# 🆕 (2026-09-26) บทสังเคราะห์ (integrate_stepic -> phase4_stepic_final_insight.json) ก็ตั้งชื่อช่องต่างกันแต่ละรอบ:
# สัญญาณข้ามมิติ รอบ 082438 = "dimensions", รอบ 111455 = "convergence_pattern" (PDF ฉบับไทยพิมพ์ "None")
# personas รอบ 082438 = value_driver/channel_preference, รอบ 111455 = motivations (list) (PDF ไม่แสดงเลย)
_SIGNAL_DIMENSIONS = ("dimensions", "convergence_pattern", "dimension", "pattern")
_PERSONA_DRIVERS = ("value_driver", "motivations", "key_motivations", "drivers")
_PERSONA_CHANNELS = ("channel_preference", "preferred_channels", "channels")


def _first_text(item, keys):
    return next((as_text(item[k]) for k in keys if as_text(item.get(k))), "")


def normalize_signals(items):
    """สัญญาณข้ามมิติ -> [{"dimensions", "signal", "implication"}] (ข้อความทุกช่อง ช่องที่ไม่มีได้ "")"""
    return [{"dimensions": _first_text(s, _SIGNAL_DIMENSIONS), "signal": as_text(s.get("signal")),
             "implication": as_text(s.get("implication"))}
            for s in (items or []) if isinstance(s, dict)]


def normalize_personas(items):
    """personas -> [{"name", "description", "value_driver", "channel_preference"}] (ข้อความทุกช่อง)"""
    return [{"name": as_text(p.get("name")), "description": as_text(p.get("description")),
             "value_driver": _first_text(p, _PERSONA_DRIVERS),
             "channel_preference": _first_text(p, _PERSONA_CHANNELS)}
            for p in (items or []) if isinstance(p, dict)]
