# -*- coding: utf-8 -*-
"""
ปีที่ใช้เป็น "ระยะสั้น" / "ระยะยาว" ของไปป์ไลน์และรายงานทั้งระบบ - ที่เดียวที่ต้องแก้เมื่อเจ้าของงานเปลี่ยนนิยาม

🆕 (2026-10-19) เดิมปีที่ระยะสั้นฝังแยกกัน 5 ที่ (bootstrap.SHORT_YEAR, report_data.SHORT_YEAR, rank_trends.RANK_YEAR,
market_overview.SHORT_KEY, brand_data.SHORT_IDX) ให้ "ตรงกัน" ด้วยคอมเมนต์ - ตอนเปลี่ยนจากปีที่ 2 เป็นปีที่ 3 จึงต้องไล่แก้ทุกที่
ตอนนี้ทุกที่อ่านจากไฟล์นี้ + ข้อความตายตัวใช้ตัวแทนค่า (apply_tokens) แทนการเขียนเลขปีตรงๆ

- ระยะสั้น = ปีที่ 1..SHORT_YEAR (จัดอันดับ / เส้นแบ่งตลาด / เลือกหน้ารายละเอียด / Top 5 ระยะสั้น ใช้คะแนนปีที่ SHORT_YEAR)
- ระยะยาว = ปีที่ SHORT_YEAR+1..LONG_YEAR (Top 5 ระยะยาวจัดอันดับด้วยปีที่ LONG_YEAR)
- ต้องตรงกับ growth_score.HORIZONS (ปี 1-5) - ไฟล์นี้ไม่ import อะไรเลย เพื่อให้ทุกโมดูล (รวมชั้นข้อมูลรายงานที่ห้าม import bootstrap)
  ใช้ได้

ตัวแทนค่าในข้อความ: "@S@" = ปีระยะสั้น (3), "@L@" = ปีระยะยาว (5), "@SR@" = ช่วงระยะสั้น ("1-3"), "@LR@" = ช่วงระยะยาว ("4-5")
"""

YEARS = (1, 2, 3, 4, 5)
SHORT_YEAR, LONG_YEAR = 3, 5

assert 1 <= SHORT_YEAR < LONG_YEAR <= YEARS[-1], "ระยะสั้นต้องมาก่อนระยะยาวและอยู่ในช่วงปีที่พยากรณ์"

SHORT_IDX, LONG_IDX = SHORT_YEAR - 1, LONG_YEAR - 1                 # ตำแหน่งในลิสต์ต่อปี (index 0 = ปีที่ 1)
SHORT_KEY, LONG_KEY = f"year_{SHORT_YEAR}", f"year_{LONG_YEAR}"      # คีย์ใน market_overview / trend_analysis
SHORT_RANGE = "1" if SHORT_YEAR == 1 else f"1-{SHORT_YEAR}"
LONG_RANGE = str(LONG_YEAR) if SHORT_YEAR + 1 == LONG_YEAR else f"{SHORT_YEAR + 1}-{LONG_YEAR}"

TOKENS = {"@SR@": SHORT_RANGE, "@LR@": LONG_RANGE, "@S@": str(SHORT_YEAR), "@L@": str(LONG_YEAR)}


def apply_tokens(obj):
    """แทนตัวแทนค่าปีในข้อความ (str / dict / list / tuple ซ้อนกันได้) - คืนสำเนาใหม่ ชนิดอื่นคืนตามเดิม"""
    if isinstance(obj, str):
        for token, value in TOKENS.items():
            obj = obj.replace(token, value)
        return obj
    if isinstance(obj, dict):
        return {k: apply_tokens(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [apply_tokens(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(apply_tokens(v) for v in obj)
    return obj
