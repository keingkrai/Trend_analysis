# -*- coding: utf-8 -*-
"""
⑯ PDF Report — ชั้นข้อมูล: อ่านไฟล์ผลรันในโฟลเดอร์รอบ แล้วประกอบเป็น dict เดียว (context) ที่เทมเพลตใช้

ไม่ import bootstrap และไม่เรียก API - อ่านไฟล์อย่างเดียว จึงเทสได้ด้วยโฟลเดอร์รอบปลอม (ดู tests/test_pdf_report.py)
ไฟล์ไหนไม่มี -> ส่วนนั้นว่างเปล่า + จดไว้ใน context["missing"] ให้หน้า appendix แจ้ง แทนที่จะพังทั้งรายงาน
(ยกเว้นผล ⑪ ที่เป็นตัวกำหนดชุด Top N - ไม่มีไฟล์นี้ก็ไม่มีเทรนด์ให้ทำรายงาน)

ตัวเลขทุกตัวในรายงานมาจากไฟล์ตรงนี้เท่านั้น - ส่วนที่ใช้ LLM (enrich.py) แค่เรียบเรียงข้อความภาษาอังกฤษ ไม่แตะตัวเลข
สาย Paper/Social/News ยังเก็บไว้ใน context (ใช้เป็นคีย์จับคู่ข้ามไฟล์) แต่เทมเพลตไม่แสดง - เจ้าของงานขอไม่ให้บอกสาย
"""
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from statistics import median
from html import unescape
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import pandas as pd

from plain_text import plain_cleanup

HIGHLIGHTS_FILE = "phase3_trend_highlights_result.json"
RANK_FILE = "phase2_rank_score_final_mode_result.json"
LONGEVITY_FILE = "phase2_longevity_cross_source_result.json"
FORECAST_FILE = "phase2_paper_social_z_delta_result.json"
MATCH_FILE = "phase3_scale_validation_nvidia_result.json"
STEPIC_FINAL_FILE = "phase4_stepic_final_insight.json"
STEPIC_RAW_FILE = "phase4_stepic_raw_analysis.json"
GROWTH_FILE = "phase2_growth_score_result.json"
TREND_ANALYSIS_FILE = "phase4_trend_analysis.json"   # 🆕 (2026-10-01) ข้อความวิเคราะห์ต่อเทรนด์จากโมเดลการเติบโต (⑭-⑮) - รอบเก่าไม่มี ใช้ของ ⑦ แทน
MARKET_FILE = "phase4_market_overview.json"   # 🆕 (2026-10-01) ภาพรวมตลาดจากคะแนนการเติบโต (⑭-⑮) - รอบเก่าไม่มี ใช้ของ ⑦ แทน
MANIFEST_FILE = "_manifest.json"
STREAM_FILES = {
    "Paper": "phase1_paper_stream_result.json",
    "Social": "phase2_social_stream_result.json",
    "News": "phase2_news_stream_result.json",
}

# ลำดับคอลัมน์ของ master_report ใน phase2_paper_social_z_delta_result.json (แถวเป็น list ไม่มีชื่อคอลัมน์ -
# ลำดับตรวจกับ trend_final_v2_subset.py แล้ว)
MASTER_REPORT_COLS = ["cluster_id", "trend", "model", "status", "current_z", "forecast_avg_z", "z_delta",
                      "peak_month", "keywords", "context", "data_quality", "pct_months_with_data"]

# ข้อความภาษาไทยที่ขั้นก่อนหน้าเขียนไว้เป็นค่าตายตัว -> ภาษาอังกฤษ (รายงานเป็นภาษาอังกฤษทั้งเล่ม)
# ต้องตรงกับ extract_trend_highlights.py's exclusion_reason() ทุกตัวอักษร
EXCLUSION_REASON_EN = {
    "เทรนด์ประเภทช่องทาง/พฤติกรรมการซื้อ - ไม่มีคุณสมบัติสินค้าให้จับคู่":
        "Sales-channel / shopping-behaviour trend - no product attributes to match against products",
    "ข้อมูลไม่พอทุกช่องที่ใช้จับคู่สินค้า": "Not enough product information to match against products",
}
# เหตุผลที่ไม่ได้มาจาก ⑪ (ค่าที่ build_context ใส่เองเมื่อไม่มีเหตุผล) -> ภาษาไทย สำหรับฉบับภาษาไทย
EXCLUSION_REASON_TH = {"Trend profile extraction failed": "สกัดจุดเด่นเทรนด์ไม่สำเร็จ"}

# 🆕 (2026-09-30) เจ้าของงานให้เอา Z_Delta ออกจากทุกส่วนที่คนเห็น - หน้า Dashboard / แผนที่กลยุทธ์ 2x2 / Trend Map ถูกลบ
# ระยะสั้น/ระยะยาวใช้คะแนนการเติบโตปีที่ 1/3 ของ ⑥ แทน (ดูหน้า Top 5 และภาพรวมทุกเทรนด์ด้านล่าง) ส่วน Longevity Score
# ยังแสดงในหน้าเทรนด์เป็นข้อมูลประกอบ (ความยั่งยืนเชิงเหตุผล) ด้วยเกรด 4 ขั้นเดิม
GRADES = ("excellent", "good", "average", "below_average")
LONG_TERM_FLOORS = (70, 55, 40)     # ขอบล่างของ Excellent / Good / Average (55 = band "leaning_durable")

# 🆕 (2026-09-30) หน้า Top 5 ระยะสั้น/ระยะยาว และหน้าภาพรวมทุกเทรนด์ (แทนหน้า Rank Trajectory) - ใช้คะแนนการเติบโตของ ⑥
# (Growth_Y1..Y5 = percentile เทียบคีย์เวิร์ดทั้งหมดในรอบ) ค่าคงที่ต้องตรงกับ growth_score.GROWTH_LINE และ
# bootstrap.TOP_K_PER_HORIZON (ไม่ import โมดูลไปป์ไลน์ - ดู docstring บนสุด)
GROWTH_LINE = 0.5
TOP_K = 5
# 🆕 (2026-10-02) พยากรณ์ 5 ปี - ระยะสั้น = ปีที่ 1-2 (จัดอันดับ/เส้นแบ่งด้วยปีที่ 2), ระยะยาว = ปีที่ 3-5 (จัดอันดับด้วยปีที่ 5)
# 🆕 (2026-10-19) ระยะสั้นเปลี่ยนเป็นปีที่ 1-3 (จัดอันดับด้วยปีที่ 3) - ค่าอยู่ที่ common/horizons.py ที่เดียว (ไฟล์เล็กไม่ import อะไร
# จึงไม่ขัดกับกฎ "ชั้นข้อมูลนี้ไม่ import bootstrap") ต้องตรงกับ growth_score.HORIZONS
_TOOL_DIR = str(Path(__file__).resolve().parents[1])
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)
from common.horizons import LONG_YEAR, SHORT_YEAR, YEARS  # noqa: E402,F401
# 🆕 (2026-10-26, รวมจากอีกสายพัฒนา) อ่านคำตอบ STEPIC ได้ไม่ว่า LLM จะห่อ/ตั้งชื่อช่องแบบไหน - ไฟล์เล็กไม่ import bootstrap
from common.stepic_shape import as_text, normalize_personas, normalize_stepic  # noqa: E402
# 🆕 (2026-10-01) ข้อมูล Google Trends แบบไม่ระบุหมวดกระโดดขึ้นทุกคีย์เวิร์ดตั้งแต่ ส.ค. 2025 (แต่ละคำไม่เท่ากัน) ตัวเลข
# "12 เดือนที่ผ่านมา" / "6 เดือนล่าสุด" จึงสูงเกินจริงจนกว่าข้อมูลถึงเดือนนี้ (ทั้งสองช่วงที่เทียบพ้นจุดกระโดด) - เทมเพลต
# ติด * และหมายเหตุ past_note ค่าต้องตรงกับ growth_score.MOMENTUM_CLEAN_FROM
PAST_CLEAN_FROM = "2027-07"
CHANNEL_REASON = "เทรนด์ประเภทช่องทาง/พฤติกรรมการซื้อ - ไม่มีคุณสมบัติสินค้าให้จับคู่"  # = ⑪'s exclusion_reason()
# 🆕 (2026-10-15) เจ้าของงานให้เอาเทรนด์ที่ไม่พบสินค้าในตลาด (⑪ ตัดสินแล้วว่าจับคู่สินค้าไม่ได้: ช่องทางการขาย / ข้อมูลไม่พอ)
# ออกจากรายงานทั้งเล่ม - ไม่มีหน้า ไม่มีแถวในตารางภาพรวม/CAGR/YoY ไม่นับในจำนวนเทรนด์ (เดิม 2026-10-14 มีหน้าอธิบาย +
# "ไม่พบสินค้าในตลาด") True = กลับไปแสดงแบบ 2026-10-14 (ไฟล์ผล ⑥/⑪/⑫ ไม่ถูกแตะ - ตัดที่ชั้นรายงานอย่างเดียว)
SHOW_NO_PRODUCT_TRENDS = False

_THAI_RE = re.compile(r"[฀-๿]+")
_SMALL_WORDS = {"and", "or", "of", "in", "on", "for", "the", "a", "an", "to", "with", "vs"}


# ============================================================================
# ตัวช่วยทั่วไป
# ============================================================================
def read_json(path):
    """คืน None ถ้าไฟล์ไม่มี/อ่านไม่ได้ - ผู้เรียกตัดสินเองว่าจะข้ามส่วนนั้นหรือหยุด"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def has_thai(text):
    return bool(_THAI_RE.search(str(text or "")))


def strip_thai(text):
    """ตัดตัวอักษรไทยออก - ชื่อสินค้าบางตัว (Watsons เดิม)มีคำอธิบายภาษาไทยต่อท้าย (เช่น "... 100 G. ครีมบำรุงผิวหน้า")
    ซึ่งรายงานภาษาอังกฤษไม่ต้องการ แล้วเก็บกวาดช่องว่าง/เครื่องหมายที่เหลือค้าง"""
    text = _THAI_RE.sub(" ", str(text or ""))
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -–|,/").strip()


def smart_title(text):
    """"beauty and personal care" -> "Beauty and Personal Care" (คำเชื่อมสั้นๆ ไม่ขึ้นตัวใหญ่ยกเว้นคำแรก,
    คำที่มีตัวใหญ่อยู่แล้ว เช่น "K-Beauty"/"SPF" คงไว้ตามเดิม)"""
    words = str(text or "").strip().split()
    out = []
    for i, w in enumerate(words):
        if w != w.lower():
            out.append(w)
        elif i > 0 and w in _SMALL_WORDS:
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def first_sentences(text, max_chars):
    """ตัดข้อความยาวที่ขอบประโยค (ไม่เกิน max_chars) - ใช้กับช่องที่พื้นที่จำกัด เช่น ช่อง STEPIC
    ถ้าประโยคแรกยาวเกินเองให้ตัดที่ขอบคำแล้วต่อ "…" (ไม่ตัดกลางคำ)"""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= max_chars:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = ""
    for s in sentences:
        candidate = f"{out} {s}".strip()
        if len(candidate) > max_chars:
            break
        out = candidate
    if out:
        return out
    return text[:max_chars].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def split_headline(text, max_chars=70):
    """แยก "หัวข้อ: รายละเอียด" (รูปแบบที่ STEPIC ตอบบ่อย) เป็น (headline, rest) - ไม่มี ":" ใช้ประโยคแรกแทน"""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if ":" in text[:max_chars + 1]:
        head, rest = text.split(":", 1)
        return head.strip(), rest.strip()
    head = first_sentences(text, max_chars)
    rest = text[len(head):].strip() if not head.endswith("…") else text
    return head.rstrip("."), rest


def _num(value):
    try:
        return None if value is None or pd.isna(value) else float(value)
    except (TypeError, ValueError):
        return None


# ============================================================================
# โหลดแต่ละส่วน
# ============================================================================
def load_master_report(forecast):
    """แถว master_report (list) -> {ชื่อคลัสเตอร์: dict ตาม MASTER_REPORT_COLS}"""
    rows = {}
    for row in (forecast or {}).get("master_report", []):
        if not isinstance(row, (list, tuple)) or len(row) < len(MASTER_REPORT_COLS):
            continue
        rec = dict(zip(MASTER_REPORT_COLS, row))
        rows[rec["trend"]] = rec
    return rows


def load_trend_rows(run_dir):
    """แถวเทรนด์เต็ม (Target/Key Benefits/Longevity ฯลฯ) -> {(stream, ชื่อเทรนด์): row}
    ใช้ Longevity ที่ปรับข้ามสายแล้ว (⑥) ก่อน ถ้าไม่มีค่อยใช้แถวดิบจากไฟล์ผลแต่ละสาย (เหมือน run_stepic_report.py)"""
    rows = {}
    for stream, fname in STREAM_FILES.items():
        for t in (read_json(run_dir / fname) or {}).get("trends", []):
            rows[(stream, t.get("Trend Name"))] = t
    cross = read_json(run_dir / LONGEVITY_FILE) or {}
    for stream, trends in cross.items():
        if not isinstance(trends, list):
            continue
        for t in trends:
            key = (stream, t.get("Trend Name"))
            rows[key] = {**rows.get(key, {}), **t}
    return rows


def load_product_catalog(csv_path):
    """{(brand, product_name): {image, url}} จาก konvy_product.csv - ผล ⑫ ไม่ได้เก็บรูป/ลิงก์ไว้ จึงต้อง join
    ด้วยชื่อ (ชื่อซ้ำ - ใช้แถวแรก)"""
    if not csv_path or not Path(csv_path).exists():
        return {}
    df = pd.read_csv(csv_path, encoding="utf-8-sig", low_memory=False,
                     usecols=["brand", "product_name", "main_image", "product_url"])
    df = df.drop_duplicates(subset=["brand", "product_name"], keep="first")
    catalog = {}
    for r in df.itertuples(index=False):
        catalog[(r.brand, r.product_name)] = {
            "image": r.main_image if isinstance(r.main_image, str) and r.main_image.startswith("http") else None,
            "url": r.product_url if isinstance(r.product_url, str) else None,
        }
    return catalog


def long_term_grade(score, insufficient=False):
    """เกรดระยะยาวจาก Longevity: 70+ excellent, 55+ good, 40+ average, ต่ำกว่านั้น below_average
    หลักฐานไม่พอ -> "insufficient" แยกต่างหาก (คะแนน ~50 ของแถวนี้แปลว่า "ไม่รู้" ไม่ใช่ Average)"""
    if insufficient:
        return "insufficient"
    if not isinstance(score, (int, float)):
        return None
    return next((g for g, floor in zip(GRADES, LONG_TERM_FLOORS) if score >= floor), "below_average")


def growth_periods(as_of):
    """"2026-08" (เดือนล่าสุดของข้อมูล) -> ช่วงเวลาของแต่ละคอลัมน์: past = 12 เดือนล่าสุด, y1..y5 = ปีข้างหน้า
    เช่น {"past": "Sep 2025 - Aug 2026", "y1": "Sep 2026 - Aug 2027", ...}"""
    base = pd.Timestamp(f"{as_of}-01")

    def span(first):
        return f"{first:%b %Y} - {first + pd.DateOffset(months=11):%b %Y}"

    return {"past": span(base - pd.DateOffset(months=11)),
            **{f"y{h}": span(base + pd.DateOffset(months=12 * (h - 1) + 1)) for h in YEARS}}


def market_expected_pct(growth):
    """🆕 (2026-10-02) % การค้นหาที่คาดของคีย์เวิร์ดตรงกลางตลาด ทุกปีของ YEARS = มัธยฐานของค่าที่โมเดลทาย (log) ของทุกคีย์เวิร์ดที่
    ข้อมูลพอ - ระดับเดียวกับเส้นแบ่ง GROWTH_LINE (ครึ่งหนึ่งคาดว่าเพิ่มมากกว่านี้) ใช้ในแถวระดับตลาดของหน้าภาพรวม
    None ถ้าผล ⑥ ไม่มีค่าที่ทายรายคีย์เวิร์ด"""
    kws = [k for k in (growth or {}).get("keywords") or [] if not k.get("thin")]
    out = []
    for h in YEARS:
        preds = [p for p in (_num(k.get(f"pred_y{h}")) for k in kws) if p is not None]
        out.append(round(math.expm1(median(preds)) * 100, 1) if preds else None)
    return out if any(v is not None for v in out) else None


SHOW_SCATTER_PAGE = True    # 🆕 (2026-10-19) หน้าเดียวแบบกราฟจุดกระจาย CAGR (แกนนอน) x YoY (แกนตั้ง) ปีที่ 2 / ปีที่ 5 + รายชื่อเทรนด์ตามเลข
                            # (เจ้าของงานเลือกแบบ D แทนตารางด้านล่าง) - ตั้ง False = ไม่สร้างหน้านี้
SHOW_COMBINED_PAGE = False  # 🆕 (2026-10-19) หน้าตารางที่มีทั้ง CAGR (แท่ง) และ YoY (ตัวเลข) ต่อปี - สลับกับหน้ากราฟจุด (ค่าเริ่มต้นปิด)
SHOW_CAGR_PAGE = False  # 🆕 (2026-10-14) หน้าภาคผนวกเทียบแบบ CAGR (เจ้าของงานขอไว้ดูเทียบ) - ตั้ง False = ไม่สร้างหน้านี้
                        # (2026-10-19 ปิดแล้ว เพราะมีหน้ารวม SHOW_COMBINED_PAGE; True = กลับมาสร้างหน้าแยกเดิมได้)
SHOW_YOY_PAGE = False   # 🆕 (2026-10-14) หน้าภาคผนวกเทียบแบบ YoY (เทียบปีก่อนหน้า) - เช่นเดียวกัน
SHOW_CUMULATIVE_PAGE = False   # 🆕 (2026-10-14) หน้าภาพรวมทุกเทรนด์แบบสะสม (เทียบ 12 เดือนล่าสุด) - เจ้าของงานให้เอาออก เหลือ CAGR / YoY
                               # (True = กลับมาแสดงหน้านั้นต่อจากหน้า Top 5; ตัวเลขสะสมยังอยู่ในหน้า Top 5 และหน้าเทรนด์)


def cagr_pct(cumulative_pct, years):
    """% เปลี่ยนสะสมเทียบ 12 เดือนล่าสุด (ปีที่ `years`) -> CAGR % = (1 + สะสม)^(1 / จำนวนปี) - 1 (ปีที่ 1 = ค่าเดิม)
    ไม่มีค่า / ระดับติดลบเกิน -100% -> None"""
    if cumulative_pct is None or years < 1 or 1 + cumulative_pct / 100 <= 0:
        return None
    return round(((1 + cumulative_pct / 100) ** (1 / years) - 1) * 100, 3)   # 3 ตำแหน่ง: ตัวเลขที่แสดงปัดจากค่านี้ (ปัด 1 ตำแหน่งก่อนแล้วปัดเป็นจำนวนเต็ม = ปัดซ้อน 5.45 -> 5.5 -> 6)


def cagr_view(gp):
    """หน้าภาพรวมทุกเทรนด์ (build_growth_pages) ฉบับ CAGR: เทรนด์/ลำดับ/เส้นแบ่ง/สีแท่งชุดเดียวกัน - เปลี่ยนเฉพาะ % ที่คาดของแต่ละปี
    และระดับตลาดโดยรวมเป็น CAGR แล้วคำนวณแท่งกราฟใหม่ตามสเกลของค่า CAGR - สำเนาใหม่ ไม่แก้ gp เดิม"""
    n = len(gp["years"])
    items = [{**{k: v for k, v in x.items() if k != "bars"},   # แท่งคำนวณใหม่ตามค่า CAGR (ไม่ใช้ของหน้าสะสม)
              "expected_pct": [cagr_pct(v, i + 1) for i, v in enumerate((x.get("expected_pct") or [None] * n)[:n])]}
             for x in gp["all"]]
    market = [cagr_pct(v, i + 1) for i, v in enumerate((gp.get("market_pct") or [None] * n)[:n])]
    market = market if any(v is not None for v in market) else None
    return {**gp, "all": items, "market_pct": market, "market_x": overview_bars(items, market), "cagr_view": None,
            "yoy_view": None}


def yoy_series(cumulative):
    """% เปลี่ยนสะสมเทียบ 12 เดือนล่าสุด ปีที่ 1..n -> % เปลี่ยนเทียบปีก่อนหน้าของแต่ละปี (ปีที่ 1 เทียบ 12 เดือนล่าสุด = ค่าเดิม)
    YoY ปี n = (1 + สะสม n) / (1 + สะสม n-1) - 1; ปีใดไม่มีค่า -> None และปีถัดไปที่ต้องใช้ปีนั้นเป็นฐานก็ None"""
    out, prev = [], 0.0
    for c in cumulative:
        if c is None or prev is None or 1 + prev / 100 <= 0 or 1 + c / 100 <= 0:
            out.append(None)
            prev = None if c is None else c
            continue
        out.append(round(((1 + c / 100) / (1 + prev / 100) - 1) * 100, 3))
        prev = c
    return out


def yoy_view(gp):
    """หน้าภาพรวมทุกเทรนด์ฉบับ YoY (เทียบปีก่อนหน้า): เทรนด์/ลำดับ (ตามคะแนนปีที่ 2)/เส้นแบ่งชุดเดียวกับหน้าภาพรวม - เปลี่ยนค่าแต่ละช่องและ
    ระดับตลาดโดยรวมเป็น YoY แล้วคำนวณแท่งกราฟใหม่ สีแท่ง = เทียบ YoY ของตลาดในปีเดียวกัน (ไม่ใช่คะแนนการเติบโตสะสม เพราะ YoY ไม่เรียง
    ตามค่าสะสม - เทรนด์เหนือตลาดแบบสะสมอาจโตต่ำกว่าตลาดในปีนั้น) - สำเนาใหม่ ไม่แก้ gp เดิม"""
    n = len(gp["years"])
    market = yoy_series(((gp.get("market_pct") or [None] * n) + [None] * n)[:n])
    market = market if any(v is not None for v in market) else None
    items = []
    for x in gp["all"]:
        vals = yoy_series(((x.get("expected_pct") or []) + [None] * n)[:n])
        scores = [None if v is None else (1.0 if market is None or market[i] is None or v >= market[i] else 0.0)
                  for i, v in enumerate(vals)]
        if market is None:
            scores = list(x.get("scores") or [None] * n)
        items.append({**{k: v for k, v in x.items() if k != "bars"}, "expected_pct": vals, "scores": scores})
    return {**gp, "all": items, "market_pct": market, "market_x": overview_bars(items, market), "cagr_view": None,
            "yoy_view": None}


def combined_view(gp):
    """🆕 (2026-10-19) หน้าเดียวที่มีทั้ง CAGR และ YoY: แถว/ลำดับ/เส้นแบ่ง/แท่งกราฟ/สีแท่งเป็นของมุมมอง CAGR (cagr_view) +
    yoy_pct = YoY ของแต่ละปี และ yoy_up = YoY ไม่ต่ำกว่า YoY ตลาดปีเดียวกัน (None ถ้าไม่มีค่าตลาด/ไม่มีค่าปีนั้น)
    ระดับตลาด: market_pct (CAGR - เส้นประบนแท่ง) + market_yoy - สำเนาใหม่ ไม่แก้ gp เดิม"""
    gc, gy = cagr_view(gp), yoy_view(gp)
    assert [x["key"] for x in gc["all"]] == [x["key"] for x in gy["all"]]   # สองมุมมองมาจาก gp["all"] ชุดเดียวกัน ลำดับต้องตรงกัน
    market_yoy = gy["market_pct"]
    items = []
    for c, y in zip(gc["all"], gy["all"]):
        vals = list(y["expected_pct"])
        up = [None if v is None or market_yoy is None or market_yoy[i] is None else v >= market_yoy[i]
              for i, v in enumerate(vals)]
        items.append({**c, "yoy_pct": vals, "yoy_up": up})
    return {**gc, "all": items, "market_yoy": market_yoy, "cagr_view": None, "yoy_view": None, "combined_view": None}


# ---------- 🆕 (2026-10-19) หน้ากราฟจุดกระจาย CAGR x YoY (scatter_view) ----------
SCATTER_W, SCATTER_H = 450, 268
SCATTER_PAD = {"l": 42, "r": 14, "t": 26, "b": 38}      # ซ้าย (ป้ายแกนตั้ง) / ขวา / บน (ชื่อกราฟ) / ล่าง (ป้ายแกนนอน + ชื่อแกน)
_LABEL_SLOTS = ((7, 4, "start"), (-7, 4, "end"), (7, -5, "start"), (-7, -5, "end"), (7, 13, "start"), (-7, 13, "end"))   # ตำแหน่งเลขกำกับจุดที่ลองตามลำดับ
_DOT_R = 4.5


def _nice_step(span, max_ticks=5):
    raw = span / max_ticks
    return next((s for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 500) if s >= raw), 1000)


def _axis(values):
    """ช่วงแกน (ครอบ 0 และค่าทั้งหมด + เผื่อหัว 8%) ปัดเป็นขั้นสวย ๆ -> (ต่ำสุด, สูงสุด, [ค่าขีดบนแกน])"""
    lo, hi = min([0.0] + values), max([0.0] + values)
    hi += (hi - lo) * 0.08 or 1.0
    step = _nice_step(hi - lo)
    lo_t, hi_t = math.floor(lo / step) * step, math.ceil(hi / step) * step
    return lo_t, hi_t, [lo_t + i * step for i in range(int(round((hi_t - lo_t) / step)) + 1)]


def _label_box(p, slot, width):
    dx, dy, anchor = slot
    x0 = p["cx"] + dx if anchor == "start" else p["cx"] + dx - width
    return (x0, p["cy"] + dy - 9, x0 + width, p["cy"] + dy + 2)


def _place_labels(points, bounds):
    """เลขกำกับจุด (อันดับในตารางภาพรวม): ลองตำแหน่งรอบจุดตามลำดับ เลือกอันแรกที่ไม่ทับเลขอื่น/จุดอื่น/ออกนอกกรอบกราฟ"""
    placed = []
    for p in points:
        width = 6.2 * len(str(p["rank"])) + 1
        chosen = _LABEL_SLOTS[0]
        for slot in _LABEL_SLOTS:
            x0, y0, x1, y1 = box = _label_box(p, slot, width)
            inside = bounds[0] <= x0 and x1 <= bounds[2] and bounds[1] <= y0 and y1 <= bounds[3]
            clear = all(x1 <= b[0] or b[2] <= x0 or y1 <= b[1] or b[3] <= y0 for b in placed)
            dots_clear = all(not (x0 - _DOT_R < q["cx"] < x1 + _DOT_R and y0 - _DOT_R < q["cy"] < y1 + _DOT_R)
                             for q in points if q is not p)
            if inside and clear and dots_clear:
                chosen = slot
                break
        placed.append(_label_box(p, chosen, width))
        p["lx"], p["ly"], p["anchor"] = p["cx"] + chosen[0], p["cy"] + chosen[1], chosen[2]


def scatter_view(gb):
    """หน้ากราฟจุดกระจาย: 1 จุด = 1 เทรนด์ แกนนอน = CAGR แกนตั้ง = YoY ของปีระยะสั้น (ปีที่ 2) และปีระยะยาว (ปีที่ 5) - gb = combined_view
    คืนพิกัด SVG ที่คำนวณแล้วให้เทมเพลตวาดอย่างเดียว: จุด (สีตามคะแนนเทียบเส้นตลาดเหมือนแท่งในตาราง), เส้นประระดับตลาด,
    ขีดแกน, เลขกำกับ + รายชื่อเทรนด์ตามเลข (key) (🆕 2026-10-19 เจ้าของงานให้เอาเส้นทแยง YoY = CAGR ออก)"""
    pad, w, h = SCATTER_PAD, SCATTER_W, SCATTER_H
    x0, x1, y0, y1 = pad["l"], w - pad["r"], pad["t"], h - pad["b"]
    n = len(gb["years"])
    out = {"n_total": gb["n_total"], "w": w, "h": h, "x0": x0, "x1": x1, "y0": y0, "y1": y1}
    plotted = {}
    for side, year in (("short", gb["short_year"]), ("long", gb["long_year"])):
        i = year - 1
        pts = [{"rank": x["rank"], "x": x["expected_pct"][i], "y": x["yoy_pct"][i],
                "up": isinstance(x["scores"][i], (int, float)) and x["scores"][i] >= gb["line"]}
               for x in gb["all"] if x["expected_pct"][i] is not None and x["yoy_pct"][i] is not None]
        mx = (gb.get("market_pct") or [None] * n)[i]
        my = (gb.get("market_yoy") or [None] * n)[i]
        xlo, xhi, xticks = _axis([p["x"] for p in pts] + ([mx] if mx is not None else []))
        ylo, yhi, yticks = _axis([p["y"] for p in pts] + ([my] if my is not None else []))

        def px(v):
            return round(x0 + (v - xlo) / (xhi - xlo) * (x1 - x0), 1)

        def py(v):
            return round(y1 - (v - ylo) / (yhi - ylo) * (y1 - y0), 1)

        for p in pts:
            p["cx"], p["cy"] = px(p["x"]), py(p["y"])
        _place_labels(pts, (x0, y0, x1, y1))
        out[side] = {
            "year": year, "points": pts,
            "xticks": [{"p": px(t), "label": f"{t:g}%"} for t in xticks], "yticks": [{"p": py(t), "label": f"{t:g}%"} for t in yticks],
            "market": {"x": px(mx) if mx is not None else None, "y": py(my) if my is not None else None},
            "zero_y": py(0) if ylo < 0 else None,
        }
        plotted[side] = {p["rank"] for p in pts}
    out["key"] = [{"rank": x["rank"], "name": x["name"], "key": x["key"], "detail_rank": x["detail_rank"],
                   "decline": bool(x["recent_decline"]), "above": bool(x["above_line"]),
                   "missing": not (x["rank"] in plotted["short"] and x["rank"] in plotted["long"])} for x in gb["all"]]
    out["any_decline"] = any(k["decline"] for k in out["key"])
    return out


def overview_bars(items, market_pct):
    """🆕 (2026-10-02) แท่งกราฟในช่องปีที่ 1-5 ของหน้าภาพรวม - ตำแหน่งเป็น % ของพื้นที่แท่งในช่อง สเกลแยกต่อปี
    (ช่วง = 0 ถึงค่าสูงสุด/ต่ำสุดของปีนั้น รวมระดับตลาด) เพราะหน้านี้ใช้เทียบเทรนด์ในปีเดียวกัน - สเกลเดียวทั้งตาราง
    แท่งปีที่ 1 จะสั้นจนแยกไม่ออก - ใส่ x["bars"] = [{left, width, end} | None] ต่อปี ให้ทุกแถว คืนตำแหน่งเส้นตลาดทุกปี"""
    n = len(YEARS)
    market_pct = market_pct or [None] * n
    market_x = []
    for h in range(n):
        vals = [v for v in [x["expected_pct"][h] for x in items] + [market_pct[h]] if v is not None]
        lo, hi = min([0.0] + vals), max([0.0] + vals)
        span = (hi - lo) or 1.0

        def pos(v):
            return round((v - lo) / span * 100, 1)

        zero = pos(0.0)
        for x in items:
            v = x["expected_pct"][h]
            end = pos(v) if v is not None else None
            x.setdefault("bars", [None] * n)[h] = None if end is None else {
                "left": min(zero, end), "width": round(abs(end - zero), 1), "end": max(zero, end)}
        market_x.append(pos(market_pct[h]) if market_pct[h] is not None else None)
    return market_x if any(v is not None for v in market_x) else None


def build_growth_pages(rank_rows, growth, highlights, trends, master):
    """ข้อมูลหน้า Top 5 ระยะสั้น/ระยะยาว และหน้าภาพรวมทุกเทรนด์ - None ถ้าผล ⑥ ยังไม่มีคะแนนการเติบโต (รอบเก่า)

    ภาพรวม: ทุกเทรนด์เรียงตามคะแนนปีที่ SHORT_YEAR (เส้นแบ่งที่ GROWTH_LINE = ค่ากลางตลาด)
    Top 5: เลือกจากทุกเทรนด์ที่ ⑪ ตัดสินว่าจับคู่สินค้าได้ (checked_trends) ไม่ใช่แค่ชุดที่มีหน้ารายละเอียด
    ระยะสั้นเรียงตามปีที่ SHORT_YEAR ระยะยาวเรียงตามปีที่ LONG_YEAR - links = คู่ (แถวฝั่งสั้น, แถวฝั่งยาว) ของเทรนด์เดียวกัน
    🆕 (2026-10-02) 5 ปี: เดิมปีที่ 1 / 3 - long_rank = อันดับตามปีที่ LONG_YEAR (เดิม y3_rank)"""
    short_f, long_f = f"Growth_Y{SHORT_YEAR}", f"Growth_Y{LONG_YEAR}"
    rows = [r for r in rank_rows if _num(r.get(short_f)) is not None]
    if not rows:
        return None
    matchable = {(c.get("stream"), c.get("trend")): (bool(c.get("matchable")), c.get("reason"))
                 for c in highlights.get("checked_trends") or []}
    # ผล ⑪ ก่อนมี checked_trends: ชุดที่เลือก = จับคู่ได้, ชุดที่ข้าม = จับคู่ไม่ได้, ที่เหลือ = ไม่รู้
    for s in highlights.get("selected_trends", []):
        matchable.setdefault((s.get("stream"), s.get("trend")), (True, None))
    for e in highlights.get("excluded_trends", []):
        matchable.setdefault((e.get("stream"), e.get("trend")), (False, e.get("reason")))
    detail = {(t["stream"], t["name"]): t for t in trends}
    expected = {c.get("trend"): (c.get("forecast") or {}).get("change_pct")
                for c in (growth or {}).get("clusters") or []}

    def by(field):
        return sorted((r for r in rows if _num(r.get(field)) is not None),
                      key=lambda r: (-float(r[field]), r.get("Overall Rank") or 0))

    long_rank = {(r.get("Stream"), r.get("Trend Name")): i for i, r in enumerate(by(long_f), 1)}
    items = []
    for i, r in enumerate(by(short_f), 1):
        key = (r.get("Stream"), r.get("Trend Name"))
        ok, reason = matchable.get(key, (None, None))
        t = detail.get(key) or {}
        items.append({
            "rank": i, "name": key[1], "key": f"{key[0]}::{key[1]}", "stream": key[0],
            "scores": [_num(r.get(f"Growth_Y{h}")) for h in YEARS],
            # 🆕 (2026-10-02) หน้าภาพรวมแสดง % การค้นหาที่คาด (เทียบ 12 เดือนล่าสุด) แทนคำ "เร็ว/ช้า" - สีช่องยังตามคะแนน
            "expected_pct": (list(expected.get(key[1]) or []) + [None] * len(YEARS))[:len(YEARS)],
            "long_rank": long_rank.get(key),
            "above_line": float(r[short_f]) >= GROWTH_LINE,
            "past_growth_pct": _num(r.get("Past_Growth_Pct")),
            "recent_decline": bool(r.get("Recent_Decline")),
            "stream_count": r.get("Stream_Count"),
            "matchable": ok,
            "no_match_kind": ("channel" if reason == CHANNEL_REASON else "no_data") if ok is False else None,
            "detail_rank": t.get("rank"),
            # หมวดแม่ (L2) ไม่ซ้ำ - คอลัมน์ที่แตกเป็นชนิดสินค้า ("Skin Care · Serum") นับเป็นหมวดแม่เดียวกัน
            "categories": list(dict.fromkeys(c.get("parent") or c["group"]
                                             for c in ((t.get("categories") or {}).get("categories") or [])))[:2],
            "keywords": [k.strip() for k in str((master.get(key[1]) or {}).get("keywords") or "").split(",")
                         if k.strip()][:2],
        })

    for x in items:   # 🆕 (2026-10-14) หน้า Top 5 แสดง CAGR (ตัวเลขสะสมยังอยู่ใน expected_pct)
        x["cagr_pct"] = [cagr_pct(v, i + 1) for i, v in enumerate(x["expected_pct"])]
    short = [x for x in items if x["matchable"]][:TOP_K]
    long_ = sorted((x for x in items if x["matchable"] and x["long_rank"]), key=lambda x: x["long_rank"])[:TOP_K]
    short_keys, long_keys = [x["key"] for x in short], [x["key"] for x in long_]
    n_above = sum(x["above_line"] for x in items)
    as_of = (growth or {}).get("as_of")
    market_pct = market_expected_pct(growth)
    market_x = overview_bars(items, market_pct)
    gp = {
        "all": items,
        "top5": {"short": [{**x, "both": x["key"] in long_keys, "other_rank": x["long_rank"]} for x in short],
                 "long": [{**x, "both": x["key"] in short_keys, "other_rank": x["rank"]} for x in long_],
                 "links": [[i, long_keys.index(k)] for i, k in enumerate(short_keys) if k in long_keys]},
        "n_total": len(items), "n_above": n_above, "n_below": len(items) - n_above,
        "n_matchable": sum(1 for x in items if x["matchable"]),
        "n_detail": sum(1 for x in items if x["detail_rank"]),
        "line": GROWTH_LINE, "market_pct": market_pct, "market_x": market_x,
        "years": list(YEARS), "short_year": SHORT_YEAR, "long_year": LONG_YEAR,
        # 🆕 (2026-10-02) ช่วงคลาดเคลื่อน 80% ของปีระยะสั้น/ยาว เป็น % ปัดเต็ม (จาก growth_score.FORECAST_BAND_80 ในไฟล์ผล ⑥)
        "band": {k: [round(v * 100) for v in ((growth or {}).get("method") or {}).get("forecast_band_80", {}).get(str(y))]
                 for k, y in (("short", SHORT_YEAR), ("long", LONG_YEAR))
                 if ((growth or {}).get("method") or {}).get("forecast_band_80", {}).get(str(y))},
        "as_of": as_of, "periods": growth_periods(as_of) if as_of else {},
        "past_inflated": bool(as_of) and as_of < PAST_CLEAN_FROM,
    }
    gp["show_cumulative"] = SHOW_CUMULATIVE_PAGE
    gp["cagr_view"] = cagr_view(gp) if SHOW_CAGR_PAGE else None
    gp["yoy_view"] = yoy_view(gp) if SHOW_YOY_PAGE else None
    cv = combined_view(gp) if (SHOW_COMBINED_PAGE or SHOW_SCATTER_PAGE) else None     # ข้อมูล CAGR + YoY ชุดเดียว ใช้ทั้งหน้าตารางและหน้ากราฟจุด
    gp["combined_view"] = cv if SHOW_COMBINED_PAGE else None
    gp["scatter_view"] = scatter_view(cv) if SHOW_SCATTER_PAGE else None
    return gp


def _run_date(run_dir, manifest):
    """วันที่เก็บข้อมูลรอบนี้: timestamp แรกสุดใน manifest -> วันที่ท้ายชื่อโฟลเดอร์ -> เวลาแก้ไขไฟล์ ⑪"""
    stamps = [v.get("timestamp") for v in (manifest or {}).values() if isinstance(v, dict) and v.get("timestamp")]
    if stamps:
        return min(datetime.fromisoformat(s) for s in stamps)
    m = re.search(r"(\d{8}_\d{6})$", run_dir.name)
    if m:
        return datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
    return datetime.fromtimestamp((run_dir / HIGHLIGHTS_FILE).stat().st_mtime)


def _models_used(manifest):
    totals = {}
    for stage in (manifest or {}).values():
        if isinstance(stage, dict):
            for model, n in (stage.get("models_used") or {}).items():
                totals[model] = totals.get(model, 0) + int(n or 0)
    return sorted(totals, key=lambda m: -totals[m])


# 🆕 (2026-10-14) กล่อง "แหล่งที่มาของข้อมูล" หน้า Notes - ฐานที่สาย Paper ค้น (paper_stream.py) ผลรันไม่ได้เก็บว่างานวิจัยแต่ละฉบับ
# มาจากฐานไหน จึงบอกได้แค่ "ค้นจาก" ฐานเหล่านี้ (ทุกรอบตั้งแต่ 2026-09-11 ค้นครบ 4 ฐาน)
PAPER_DATABASES = ("ScienceDaily", "MDPI", "OpenAlex", "PubMed Central")
_PLATFORM_RE = re.compile(r"^(Reddit|YouTube|Pantip)\s*:", re.I)
_PLATFORM_NAMES = {n.lower(): n for n in ("Reddit", "YouTube", "Pantip")}


def _provenance_docs(stream):
    """triplet_provenance ของผลสาย -> {doc_index: ชื่อเรื่อง, source_region} ของเอกสารที่ให้หลักฐานจริง (1 เอกสารมีหลาย triplet นับครั้งเดียว)"""
    docs = {}
    for p in (stream or {}).get("triplet_provenance") or []:
        if isinstance(p, dict):
            docs.setdefault(p.get("doc_index"), (p.get("title") or "", p.get("source_region") or ""))
    return docs


LINKS_FILE = "phase6_source_links.json"   # สร้างโดย build_source_links.py สำหรับรอบเก่าที่ผลสายไม่ได้เก็บลิงก์เอกสาร (รอบใหม่เก็บใน "documents")
_PLATFORM_ORDER = {"Reddit": 0, "YouTube": 1, "Pantip": 2}
_URL_RE = re.compile(r"https?://[^\s,]+")
_ASR_NOTE_RE = re.compile(r"\s*\[automatic speech-to-text.*$", re.S)


def _doc_title(title):
    """ชื่อเรื่องใน triplet_provenance -> (แพลตฟอร์ม หรือ None, ชื่อที่แสดง) - ตัดคำนำหน้า "Reddit: " และหมายเหตุถอดเสียงของ YouTube"""
    m = _PLATFORM_RE.match(title)
    platform = _PLATFORM_NAMES[m.group(1).lower()] if m else None
    text = _ASR_NOTE_RE.sub("", title[m.end():] if m else title).strip()
    return platform, text


def _clean_url(url):
    """ตัดพารามิเตอร์ติดตาม utm_* ออกจาก URL (ข่าวจาก RSS มาพร้อม utm_campaign ฯลฯ ยาวและไม่จำเป็น) - ส่วนอื่นคงเดิม"""
    if "utm_" not in url.lower():
        return url                                    # ไม่มีพารามิเตอร์ติดตาม = ไม่แตะ (คงการเข้ารหัสเดิม เช่นลิงก์ค้นหา Pantip)
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _source_documents(run_dir):
    """รายการเอกสารต้นทางของรอบ (หน้า "รายการแหล่งข้อมูล" ท้ายรายงาน) -> {papers, discussions, news: [{title, url, platform, search}]}
    เฉพาะกลุ่มที่มีเอกสาร; เอกสารคือที่ให้หลักฐานจริง (เหมือนจำนวนในกล่องแหล่งที่มา)
    ลิงก์: "documents" ในผลสาย (รอบใหม่) -> phase6_source_links.json (build_source_links.py สำหรับรอบเก่า) -> ไม่มีลิงก์ (แสดงแค่ชื่อ)
    Pantip: เอกสารคือหน้าผลค้นหาของคำค้นหนึ่ง (ชื่อ = คำค้น) ลิงก์ = หน้าค้นหาของคำนั้นเสมอ (search = True)"""
    links = (read_json(run_dir / LINKS_FILE) or {}).get("links") or {}
    out = {}
    for key, stream_name in (("papers", "Paper"), ("discussions", "Social"), ("news", "News")):
        stream = read_json(run_dir / STREAM_FILES[stream_name]) or {}
        saved = {d.get("title"): d for d in stream.get("documents") or [] if isinstance(d, dict)}
        items = []
        for title, _ in _provenance_docs(stream).values():
            platform, shown = _doc_title(title)
            found = _URL_RE.search(str((saved.get(title) or {}).get("link") or ""))
            side = links.get(title) or {}
            url = found.group(0) if found else side.get("url")
            if platform == "Pantip":
                url = "https://pantip.com/search?q=" + quote(shown)
            items.append({"title": unescape(side.get("title") or shown), "url": _clean_url(url) if url else None,
                          "platform": platform, "search": platform == "Pantip"})
        if key == "discussions":
            items.sort(key=lambda d: _PLATFORM_ORDER.get(d["platform"], 9))
        if items:
            out[key] = items
    return out


def _catalog_collected(csv_path):
    """วันเก็บข้อมูลของแคตตาล็อกสินค้า (คอลัมน์ scraped_date แบบ dd/mm/yyyy) -> (วันแรก, วันสุดท้าย) เป็นข้อความ ISO หรือ (None, None)"""
    if not csv_path or not Path(csv_path).exists():
        return None, None
    try:
        col = pd.read_csv(csv_path, encoding="utf-8-sig", usecols=["scraped_date"], low_memory=False)["scraped_date"]
    except (ValueError, OSError):
        return None, None
    days = pd.to_datetime(col, format="%d/%m/%Y", errors="coerce").dropna()
    if days.empty:
        return None, None
    return days.min().date().isoformat(), days.max().date().isoformat()


def no_product_keys(highlights):
    """{(stream, trend): เหตุผล} ของเทรนด์ที่ ⑪ ตัดสินแล้วว่าจับคู่สินค้าไม่ได้ - checked_trends (matchable = False) และ
    excluded_trends (รอบเก่าที่ยังไม่มี checked_trends) - ไม่รวม failed_trends (ล้มเหลวทางเทคนิค ไม่ใช่ผลตัดสิน)"""
    out = {}
    for c in highlights.get("checked_trends") or []:
        if c.get("matchable") is False:
            out[(c.get("stream"), c.get("trend"))] = c.get("reason")
    for e in highlights.get("excluded_trends") or []:
        out.setdefault((e.get("stream"), e.get("trend")), e.get("reason"))
    return out


def market_without_trends(market, growth, rank_rows, trend_rows, dropped_names):
    """🆕 (2026-10-15) ภาพรวมตลาด (phase4_market_overview.json - มัธยฐานการเติบโต / จำนวนเทรนด์เหนือตลาด / ข้อความสรุป) คิดจากทุกเทรนด์ในรอบ
    เมื่อตัดเทรนด์ที่ไม่พบสินค้าออกจากรายงาน ตัวเลขและข้อความต้องไม่นับ/ไม่เอ่ยชื่อมัน (เจอจริงรอบ 111455: ข้อความสรุปยังเอ่ยชื่อเทรนด์ที่ถูกตัด)
    + 🆕 (2026-10-19) เมื่อไฟล์เขียนตอนระยะสั้นเป็นปีอื่น (ตัวเลข/ข้อความสรุปพูดถึงปีที่ 2 แต่รายงานใช้ปีที่ 3)
    -> คิดใหม่จากเทรนด์ที่เหลือด้วยฟังก์ชันเดียวกับ ⑭-⑮ (common/market_overview.py - ป้าย 3 ช่องจากกฎตายตัว, basis, ข้อความสรุปที่ประกอบจากตัวเลข
    แทนข้อความของ LLM; ฉบับภาษาง่าย/ไทยเขียนต่อได้ตามปกติผ่าน enrich) - คืน market เดิมถ้าไม่มีเทรนด์ที่ตัดอยู่ในผลการเติบโต"""
    clusters = (growth or {}).get("clusters") or []
    kept = [c for c in clusters if c.get("trend") not in dropped_names]
    # 🆕 (2026-10-19) ไฟล์ ⑭-⑮ ที่เขียนตอนระยะสั้นเป็นปีอื่น (basis.short_year ไม่ตรงค่าปัจจุบัน หรือเป็นรุ่นก่อนมีช่องนี้) คิดใหม่จากผลการเติบโตเช่นกัน
    basis = (market or {}).get("basis")
    stale = bool(basis) and basis.get("short_year") != SHORT_YEAR
    if not stale and (not dropped_names or len(kept) == len(clusters)):
        return market
    tool_dir = str(Path(__file__).resolve().parents[1])
    if tool_dir not in sys.path:
        sys.path.insert(0, tool_dir)
    from common import market_overview as mo   # ฟังก์ชันล้วน (numpy) - ไม่แตะ bootstrap/LLM
    durability = [(trend_rows.get((r.get("Stream"), r.get("Trend Name"))) or {}).get("Longevity Score") for r in rank_rows]
    snapshot = mo.market_snapshot(kept, durability)
    if not snapshot:
        return market
    return {**(market or {}), **mo.market_overview(snapshot, None, (market or {}).get("query"))}


def _page_trends(highlights, rank_rows, rank_by_key):
    """เทรนด์ที่มีหน้าในรายงาน (รายการ dict แบบ selected_trends ของ ⑪ + ช่อง top_rank / no_products)
    มีคะแนนการเติบโต: ผ่านดัชนีตลาดเท่านั้น (ชุดที่ ⑪ เลือกแต่ต่ำกว่าเส้นถูกตัด) + เหนือเส้นแต่จับคู่สินค้าไม่ได้ (checked_trends /
    excluded_trends) เรียงตามคะแนนปีที่ SHORT_YEAR แล้วอันดับเดิมของ ⑥; ไม่มีคะแนน (รอบเก่า) = ชุดของ ⑪ ตามเดิม"""
    selected = list(highlights.get("selected_trends") or [])
    short_f = f"Growth_Y{SHORT_YEAR}"
    score = {(r.get("Stream"), r.get("Trend Name")): _num(r.get(short_f)) for r in rank_rows}
    if not any(v is not None for v in score.values()):
        return selected
    passes = lambda key: (score.get(key) is not None and score[key] >= GROWTH_LINE)   # noqa: E731
    picked = [s for s in selected if passes((s.get("stream"), s.get("trend")))]
    have = {(s.get("stream"), s.get("trend")) for s in picked}
    for key, reason in no_product_keys(highlights).items():   # ถูกตัดจาก rank_rows แล้วเมื่อ SHOW_NO_PRODUCT_TRENDS = False -> passes() เป็นเท็จ
        if key not in have and passes(key):
            rk = rank_by_key.get(key, {})
            picked.append({"stream": key[0], "trend": key[1], "overall_rank": rk.get("Overall Rank"),
                           "rank_score": rk.get("Rank Score"), "no_products": "channel" if reason == CHANNEL_REASON else "no_data"})
    picked.sort(key=lambda s: (-score[(s.get("stream"), s.get("trend"))], s.get("overall_rank") or 0))
    return [{**s, "top_rank": i} for i, s in enumerate(picked, 1)]


def product_trends(ctx):
    """ctx ที่เหลือเฉพาะเทรนด์ที่มีผลจับคู่สินค้า (ตัดหน้าอธิบายเทรนด์แบบไม่พบสินค้า) และเรียงอันดับ 1.. ใหม่ - ใช้กับรายงานแบรนด์ (⑰)
    ที่เทียบสินค้าของแบรนด์กับสินค้าในตลาด"""
    keep = [t for t in ctx["trends"] if not t.get("no_products")]
    return {**ctx, "trends": [{**t, "rank": i} for i, t in enumerate(keep, 1)]}


def _data_sources(run_dir, matches, growth, catalog_path, has_categories):
    """แหล่งข้อมูลของรอบนี้ (ภาษากลาง - ข้อความต่อภาษาประกอบใน i18n.source_rows) -> dict ที่มีเฉพาะแหล่งที่มีข้อมูลจริง
    papers {n_used, databases} / discussions {platforms [{name, n}]} / news {intl, th: {n_used}} /
    search {n_keywords} / products {n, collected_from, collected_to} / categories True
    n_used = จำนวนเอกสารที่ให้หลักฐาน (มี triplet อย่างน้อย 1) ไม่ใช่จำนวนที่ดึงมา (เจ้าของงานไม่ให้แสดงจำนวนที่ค้นเจอก่อนคัด 2026-10-14)"""
    out = {}
    paper = read_json(run_dir / STREAM_FILES["Paper"]) or {}
    n_paper = len(_provenance_docs(paper))
    if n_paper:
        out["papers"] = {"n_used": n_paper, "databases": list(PAPER_DATABASES)}

    counts = {}
    for title, _ in _provenance_docs(read_json(run_dir / STREAM_FILES["Social"])).values():
        m = _PLATFORM_RE.match(title)
        if m:
            name = _PLATFORM_NAMES[m.group(1).lower()]
            counts[name] = counts.get(name, 0) + 1
    if counts:
        out["discussions"] = {"platforms": [{"name": k, "n": v} for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]}

    news = read_json(run_dir / STREAM_FILES["News"]) or {}
    regions = [r for _, r in _provenance_docs(news).values()]
    n_intl, n_th = regions.count("intl"), regions.count("th")
    if not (n_intl or n_th):   # ผลรอบเก่าไม่มี source_region ต่อเอกสาร - ใช้จำนวนที่สายเก็บไว้แยกภูมิภาคถ้ามี
        n_intl, n_th = news.get("n_scraped_intl") or 0, news.get("n_scraped_th") or 0
    news_src = {k: {"n_used": n} for k, n in (("intl", n_intl), ("th", n_th)) if n}
    if news_src:
        out["news"] = news_src

    keywords = {k.get("keyword") for k in (growth or {}).get("keywords") or [] if isinstance(k, dict) and k.get("keyword")}
    if keywords:
        out["search"] = {"n_keywords": len(keywords)}

    if (matches or {}).get("n_products_total"):
        first, last = _catalog_collected(catalog_path)
        out["products"] = {"n": matches["n_products_total"], "collected_from": first, "collected_to": last}
    if has_categories:
        out["categories"] = True
    return out


def _stepic_tiles(raw):
    """6 ช่อง STEPIC -> [{dimension, headline, body}] - แต่ละมิติ LLM ตอบคนละโครง (ดู run_stepic_report.py)
    จึงต้องระบุช่องที่ใช้ต่อมิติ ช่องไหนหายก็ตกไปใช้ช่องถัดไปที่มีข้อความ"""
    if not raw:
        return []
    # 🆕 (2026-10-01) LLM ตอบโครงไม่คงที่ระหว่างรอบ: technology/creativity/industry บางรอบซ้อนอยู่ใน analysis /
    # creativity_analysis / industry บางรอบแบน (run_stepic_report.normalize_stepic_raw แปลงเป็นแบบแบนแล้ว) - อ่านได้ทั้งสองแบบ
    # 🆕 (2026-10-26) ห่อ "trend_analysis" (รอบ 111455 ก่อนแก้ที่ต้นทาง) แกะด้วย common/stepic_shape ก่อน - ได้ครบ 6 ช่อง
    raw = {**raw, **{dim: fields for dim, fields in normalize_stepic(raw).items() if fields}}

    def flat(dim, inner):
        d = raw.get(dim) or {}
        return {**d, **d[inner]} if isinstance(d.get(inner), dict) else d

    tech, creat, ind = flat("technology", "analysis"), flat("creativity", "creativity_analysis"), flat("industry", "industry")
    soc, env, pol = (raw.get(k) or {} for k in ("society", "environment", "policy"))
    sp = ind.get("strategic_positioning")
    spec = [
        ("Society", soc.get("concept"), [soc.get("behavioral_shift"), soc.get("projected_impact")]),
        ("Technology", tech.get("core_technology"), [tech.get("innovation_driver"), tech.get("commercialization_signal")]),
        ("Environment", env.get("environmental_factor"), [env.get("sustainability_opportunity"), env.get("ESG_driver")]),
        ("Policy", pol.get("regulatory_trend"), [pol.get("business_impact"), pol.get("legal_barrier_or_support")]),
        ("Industry", ind.get("concept") or as_text(ind.get("market_structure")),
         [sp.get("winning_strategy") if isinstance(sp, dict) else sp, ind.get("information"), as_text(sp),
          as_text(ind.get("competitive_landscape"))]),
        ("Creativity", creat.get("brand_expression"), [creat.get("product_innovation"), creat.get("differentiation_strategy")]),
    ]
    tiles = []
    for dim, head_src, body_srcs in spec:
        if not head_src and not any(body_srcs):
            continue
        headline, rest = split_headline(head_src or "")
        body = next((b for b in body_srcs if b), "") or rest
        tiles.append({"dimension": dim, "headline": headline, "body": first_sentences(body, 420)})
    return tiles


def _personas(items):
    """🆕 (2026-10-26) persona ที่ LLM เรียกช่อง value driver / ช่องทางต่างกัน (motivations ฯลฯ) -> ช่องมาตรฐานของเทมเพลต
    ช่องอื่นของ persona คงไว้ตามเดิม"""
    out = []
    for p, norm in zip([p for p in items or [] if isinstance(p, dict)], normalize_personas(items)):
        out.append({**p, **{k: v for k, v in norm.items() if v}})
    return out


def _signals(items):
    """🆕 (2026-10-01) สัญญาณข้ามมิติ -> {dimensions: "SOCIETY + INDUSTRY", signal, implication} - บางรอบ LLM ตอบ
    {signal_type, dimensions: [...], insight} (ดู run_stepic_report.normalize_stepic_final)"""
    out = []
    for s in items or []:
        if not isinstance(s, dict):
            continue
        dims = s.get("dimensions") or s.get("convergence_pattern")   # รอบ 111455 ตั้งชื่อช่องนี้ (ดู common/stepic_shape.py)
        out.append({**s,
                    "dimensions": " + ".join(str(d).upper() for d in dims if d) if isinstance(dims, list) else dims or "",
                    "signal": s.get("signal") or s.get("insight") or s.get("description") or "",
                    "implication": s.get("implication") or ""})
    return out


def _product(m, catalog):
    extra = catalog.get((m.get("brand"), m.get("product_name")), {})
    return {
        "name": strip_thai(m.get("product_name")) or m.get("product_name"),
        "name_full": m.get("product_name"),  # ชื่อเต็มที่มีภาษาไทย - ฉบับภาษาไทยใช้ตัวนี้ (i18n.localize)
        "brand": strip_thai(m.get("brand")) or m.get("brand"),
        "category": m.get("category") or "",
        "similarity": _num(m.get("similarity")),
        "price_thb": _num(m.get("sale_price_thb")),
        "rank_in_market": m.get("rank_in_market"),
        "reason": plain_cleanup(m.get("match_reason") or "", "en"),   # 🆕 (2026-10-12) ศัพท์เฉพาะ -> คำธรรมดา (plain_text.py)
        "image_url": extra.get("image"),
        "product_url": extra.get("url"),
        # 🆕 (2026-10-12) ช่วงราคาต่อปริมาณ: ขนาดรวม / ฿ ต่อหน่วย / ขนาดทดลอง (ผล ⑫ รอบเก่าไม่มี -> None)
        "size": _num(m.get("size")), "unit_label": m.get("unit_label"), "unit_price": _num(m.get("unit_price")),
        "is_mini": bool(m.get("is_mini")),
    }


def _products(match_result, catalog, top_k):
    return [_product(m, catalog) for m in (match_result or {}).get("top_matches", [])[:top_k]]


def category_products(c):
    """🆕 (2026-10-07) สินค้าทุกชิ้นของคอลัมน์หมวดที่รายงานใช้ (3 ชิ้นที่ใกล้ที่สุด + ชิ้นที่ใกล้ที่สุดของแต่ละช่วงราคา) -
    ให้การโหลดรูป/การใช้ชื่อเต็มภาษาไทยครอบคลุมสินค้าในช่วงราคาด้วย (อาจซ้ำชิ้นเดียวกันได้)"""
    return list(c.get("products") or []) + [t["product"] for t in c.get("price_tiers") or [] if t.get("product")]


def _categories(match_result, catalog):
    """ผลแยกหมวดของ ⑫ (by_category - category_breakdown.py) -> สินค้าต่อหมวดพร้อมรูป/ลิงก์
    รอบที่รัน ⑫ ก่อนมีการแยกหมวด -> None (เทมเพลตใช้หน้าสินค้าแบบเดิม 5 ชิ้นแทน)"""
    bc = (match_result or {}).get("by_category")
    if not bc or not bc.get("categories"):
        return None
    cats = [{"group": c.get("group"), "parent": c.get("parent") or c.get("group"), "subgroup": c.get("subgroup"),
             "color": c.get("color", i) if isinstance(c.get("color", i), int) and c.get("color", i) < 4 else i,
             "n_pool": c.get("n_pool"), "n_total": c.get("n_total"),
             "median_price_thb": _num(c.get("median_price_thb")), "min_price_thb": _num(c.get("min_price_thb")),
             "max_price_thb": _num(c.get("max_price_thb")),
             "products": [_product(m, catalog) for m in c.get("products", [])],
             # 🆕 (2026-10-07) ช่วงราคาตลาด ต่ำ/กลาง/สูง ของคอลัมน์ + ชิ้นที่ใกล้ที่สุดในแต่ละช่วง (ผล ⑫ รอบเก่าไม่มี -> None)
             "price_tiers": [{**{k: t.get(k) for k in ("label", "price_from", "price_to", "n_total", "n_pool",
                                                       "unit_from", "unit_to", "unit_label")},
                              "product": _product(t["product"], catalog) if t.get("product") else None}
                             for t in c.get("price_tiers") or []] or None}
            for i, c in enumerate(bc["categories"])]
    sims = [p["similarity"] for c in cats for p in category_products(c) if p["similarity"] is not None]
    n_all = match_result.get("n_products_compared")
    return {"pool_size": bc.get("pool_size"), "distribution": bc.get("distribution") or [], "categories": cats,
            # 🆕 (2026-10-08) หมวดหลักที่ LLM เลือก (⑫ main_category) + จำนวนสินค้าทั้งหมวดในร้าน - ผลรอบเก่าไม่มี = None (หน้าแบบเดิม)
            "main_category": bc.get("main_category"), "main_n_total": bc.get("n_category"),
            "max_similarity": max(sims) if sims else None, "has_tiers": any(c["price_tiers"] for c in cats),
            # สัดส่วน pool จากทั้งร้าน ("1" = 1%) - ⑫ ใช้ POOL_FRACTION 1% แต่ปัดเป็นจำนวนชิ้นแล้ว
            "pool_pct": f"{round(bc['pool_size'] / n_all * 100, 1):g}" if n_all and bc.get("pool_size") else ""}


# ============================================================================
# ประกอบ context
# ============================================================================
def build_context(run_dir, catalog_path=None, top_products=5):
    """อ่านทุกไฟล์ของรอบ -> (context, history)

    context เป็น dict ที่ serialize เป็น JSON ได้ (บันทึกเป็น phase6_report_context.json ไว้ดูย้อนหลัง/ดีบัก)
    history = {ชื่อเทรนด์: {"months", "values"}} ดัชนีการค้นหาจริงรายเดือน (ผล ⑥ growth) ใช้วาดกราฟหน้าเทรนด์
    🆕 (2026-09-30) ไม่ใช้ค่าพยากรณ์ z-score/Z_Delta ของ ⑦ แล้ว (เจ้าของงานให้เอาออกจากทุกส่วนที่คนเห็น) - จากผล ⑦
    ยังอ่านแค่คีย์เวิร์ด คุณภาพข้อมูล และบทวิเคราะห์ตลาดของ LLM"""
    run_dir = Path(run_dir)
    missing = []

    def need(fname, label):
        data = read_json(run_dir / fname)
        if data is None:
            missing.append(f"{label} ({fname})")
        return data

    highlights = read_json(run_dir / HIGHLIGHTS_FILE)
    if not highlights or not highlights.get("selected_trends"):
        raise FileNotFoundError(f"ไม่พบชุด Top N จาก ⑪ ({HIGHLIGHTS_FILE}) ใน {run_dir} - ต้องรัน ⑪ ก่อน")

    manifest = read_json(run_dir / MANIFEST_FILE) or {}
    rank_rows = need(RANK_FILE, "Rank Score") or []
    # 🆕 (2026-10-15) เทรนด์ที่ไม่พบสินค้าในตลาดถูกตัดจากอันดับก่อนประกอบทุกส่วน - หน้าเทรนด์ ตารางภาพรวม/CAGR/YoY Top 5
    # และจำนวนเทรนด์รวมจึงไม่มีมัน (เลขอันดับเรียงใหม่เอง) เก็บรายชื่อไว้ใน context["no_product_trends"] ไว้ตรวจย้อนหลัง
    no_product = []
    if not SHOW_NO_PRODUCT_TRENDS:
        dropped = no_product_keys(highlights)
        no_product = [{"stream": r.get("Stream"), "name": r.get("Trend Name"),
                       "reason": dropped[(r.get("Stream"), r.get("Trend Name"))]}
                      for r in rank_rows if (r.get("Stream"), r.get("Trend Name")) in dropped]
        rank_rows = [r for r in rank_rows if (r.get("Stream"), r.get("Trend Name")) not in dropped]
    forecast = need(FORECAST_FILE, "Google Trends forecast") or {}
    matches = need(MATCH_FILE, "Product matching") or {}
    stepic_final = need(STEPIC_FINAL_FILE, "STEPIC synthesis") or {}
    stepic_raw = need(STEPIC_RAW_FILE, "STEPIC analysis") or {}

    master = load_master_report(forecast)
    trend_analysis = read_json(run_dir / TREND_ANALYSIS_FILE) or forecast.get("llm_forecast_analysis") or {}
    analysis_by_name = {c.get("cluster_name"): c for c in trend_analysis.get("cluster_analysis", [])}
    rank_by_key = {(r.get("Stream"), r.get("Trend Name")): r for r in rank_rows}
    trend_rows = load_trend_rows(run_dir)
    profiles = {(p.get("stream"), p.get("trend")): p for p in highlights.get("profiles", [])}
    catalog = load_product_catalog(catalog_path)
    match_results = matches.get("results") or {}

    # 🆕 (2026-10-14) หน้าเทรนด์ = เฉพาะเทรนด์ที่ผ่านดัชนีตลาด (คะแนนปีที่ SHORT_YEAR >= GROWTH_LINE) เรียงตามคะแนนนั้น:
    # เทรนด์ที่ ⑪ เลือกไว้แต่ต่ำกว่าเส้นไม่มีหน้า (เจอในรอบ snapshot ที่เลือกชุดไว้ด้วยลำดับเก่า) และเทรนด์เหนือเส้นที่จับคู่สินค้า
    # ไม่ได้ (ช่องทางการขาย / ข้อมูลไม่พอ) มีหน้าอธิบายเทรนด์ + ข้อความว่าไม่พบสินค้าในตลาด (no_products) - ผล ⑥ รอบเก่าไม่มีคะแนน
    # การเติบโต = ใช้ชุดที่ ⑪ เลือกเหมือนเดิม
    selected_list = _page_trends(highlights, rank_rows, rank_by_key)
    trends = []
    for i, sel in enumerate(selected_list, 1):
        stream, name = sel.get("stream"), sel.get("trend")
        key = f"{stream}::{name}"
        mr = master.get(name, {})
        rk = rank_by_key.get((stream, name), {})
        row = trend_rows.get((stream, name), {})
        keywords = [k.strip() for k in str(mr.get("keywords") or "").split(",") if k.strip()]
        trends.append({
            "rank": sel.get("top_rank") or i,
            "no_products": sel.get("no_products"),   # None = มีผลจับคู่สินค้า / "channel" / "no_data" = ไม่พบสินค้าในตลาด
            "overall_rank": sel.get("overall_rank"),
            "name": name,
            "key": key,
            "stream": stream,  # ใช้จับคู่ข้ามไฟล์เท่านั้น - เทมเพลตไม่แสดง
            "rank_score": _num(rk.get("Rank Score", sel.get("rank_score"))),
            # 🆕 (2026-09-30) คะแนนการเติบโตของ ⑥ (ปีที่ 1/2/3 เทียบตลาด) + การโตจริง 12 เดือนที่ผ่านมา
            "growth": {"scores": [_num(rk.get(f"Growth_Y{h}")) for h in YEARS],
                       "grades": [rk.get(f"Grade_Y{h}") for h in YEARS],
                       "past_growth_pct": _num(rk.get("Past_Growth_Pct")),
                       "recent_change_pct": _num(rk.get("Recent_Change_Pct")),
                       "recent_decline": bool(rk.get("Recent_Decline"))},
            "keywords": keywords,
            "data_quality": mr.get("data_quality") or "",
            "pct_months_with_data": _num(mr.get("pct_months_with_data")),
            "stream_count": rk.get("Stream_Count"),
            "cluster_size": rk.get("Cluster_Size", row.get("Cluster Size")),
            "longevity_score": row.get("Longevity Score"),
            "longevity_band": (row.get("Longevity Band") or "").replace("_", " "),
            # ธงจาก ⑤ (ยกหลักฐานได้ ≤ 2 จาก 5 มิติ) - คะแนน ~50 ของแถวแบบนี้แปลว่า "ไม่รู้" ไม่ใช่ "กลางๆ"
            "longevity_insufficient": bool(row.get("Longevity Insufficient Evidence")),
            "target": row.get("Target") or "",
            "key_ingredients": row.get("Key Ingredients") or "",
            "key_benefits": row.get("Key Benefits") or "",
            "analysis": analysis_by_name.get(name, {}),
            "profile": {k: v for k, v in profiles.get((stream, name), {}).items() if k not in ("stream", "trend")},
            "products": _products(match_results.get(key), catalog, top_products),
            "categories": _categories(match_results.get(key), catalog),
            "similarity_stats": (match_results.get(key) or {}).get("similarity_stats") or {},
            "n_products_compared": (match_results.get(key) or {}).get("n_products_compared"),
        })

    # 🆕 (2026-10-21) แผนที่ตลาดระดับหมวด L2 (⑫ --l2-map-only): หน้าสินค้าของเทรนด์เทียบ "ความใกล้เทรนด์ x ยอดขาย" ทั้งหมวดหลัก (l2_map.py)
    # รอบที่ยังไม่มีไฟล์แผนที่ = t["l2"] เป็น None แล้วเทมเพลตใช้หน้าสินค้าแบบเดิม (ชนิดสินค้า x ช่วงราคา)
    from brand_data import load_config as load_brand_config
    from l2_map import CONFIG_FILE as L2_CONFIG_FILE, category_products as l2_products, l2_grid, load_map as load_l2_map

    l2_data = load_l2_map(run_dir)
    l2_cfg = load_brand_config(L2_CONFIG_FILE)
    for t in trends:
        cat, prods = l2_products(l2_data, t["key"], t["name"]) if l2_data and not t["no_products"] else (None, [])
        t["l2"] = {"category": cat, **l2_grid(prods, l2_cfg, lambda m: _product(m, catalog))} if prods else None

    excluded = []
    for e in highlights.get("excluded_trends", []) + highlights.get("failed_trends", []):
        reason = e.get("reason") or "Trend profile extraction failed"
        excluded.append({"name": e.get("trend"), "overall_rank": e.get("overall_rank"),
                         "reason": EXCLUSION_REASON_EN.get(reason, strip_thai(reason) or "Excluded from the Top N"),
                         # ฉบับภาษาไทยใช้เหตุผลต้นฉบับจาก ⑪ ตรงๆ (เป็นภาษาไทยอยู่แล้ว)
                         "reason_th": reason if has_thai(reason) else EXCLUSION_REASON_TH.get(reason, reason)})

    for t in trends:
        t["long_term_grade"] = long_term_grade(t["longevity_score"], t["longevity_insufficient"])

    # 🆕 (2026-09-30) หน้า Top 5 ระยะสั้น/ระยะยาว + ภาพรวมทุกเทรนด์ (None = ผล ⑥ รอบเก่ายังไม่มีคะแนนการเติบโต)
    # และดัชนีการค้นหาจริงรายเดือนสำหรับกราฟหน้าเทรนด์
    growth = read_json(run_dir / GROWTH_FILE) or {}
    growth_pages = build_growth_pages(rank_rows, growth, highlights, trends, master)
    if not growth:
        missing.append(f"Growth score ({GROWTH_FILE})")
    # กราฟหน้าเทรนด์: ดัชนีการค้นหาจริง + ระดับที่คาดปีที่ 1-3 (🆕 2026-09-30 ส่วนทำนายจากโมเดลการเติบโต)
    history = {c["trend"]: {**c["history"], "forecast": c.get("forecast")}
               for c in growth.get("clusters") or [] if c.get("history")}
    for t in trends:
        fc = (history.get(t["name"]) or {}).get("forecast") or {}
        t["growth"]["forecast_pct"] = (list(fc.get("change_pct") or []) + [None] * len(YEARS))[:len(YEARS)]
        # 🆕 (2026-10-14) กล่อง KPI / ตัวเลขบนกราฟของหน้าเทรนด์ใช้ CAGR (เฉลี่ยต่อปีแบบทบต้นนับจาก 12 เดือนล่าสุด) แทนตัวเลขสะสม
        t["growth"]["forecast_cagr"] = [cagr_pct(v, i + 1) for i, v in enumerate(t["growth"]["forecast_pct"])]
    periods = (growth_pages or {}).get("periods") or {}

    paper = read_json(run_dir / STREAM_FILES["Paper"]) or {}
    topic = paper.get("topic") or next((v.get("topic") for v in manifest.values()
                                        if isinstance(v, dict) and v.get("topic")), "") or run_dir.name
    years = next((v.get("years") for v in manifest.values() if isinstance(v, dict) and v.get("years")), "")
    run_date = _run_date(run_dir, manifest)
    stepic_final = stepic_final or {}

    context = {
        "meta": {
            "run_id": run_dir.name,
            "topic": topic,
            "title": smart_title(topic),
            "years": years,
            "top_n": len(trends),
            # จำนวนเทรนด์รวมไม่นับเทรนด์ที่ถูกตัดเพราะไม่พบสินค้า (ให้ตรงกับตารางภาพรวม)
            "n_trends_total": (highlights["n_trends_total"] - len(no_product)
                               if highlights.get("n_trends_total") is not None else None),
            "n_products_compared": matches.get("n_products_total"),
            # 🆕 (2026-10-12) ช่วงราคาของหน้าสินค้าแบ่งด้วยอะไร: price (ราคาขาย) / unit_price (ราคาต่อปริมาณ) - ⑫ เก็บไว้ในผล
            "tier_basis": matches.get("tier_basis") or "price",
            "run_date": run_date.isoformat(timespec="minutes"),
            # ช่วงคาดการณ์ = ต้นปีที่ 1 ถึงท้ายปีที่ 3 ของคะแนนการเติบโต ("Sep 2026 - Aug 2027" -> "Sep 2026")
            "forecast_start": periods.get("y1", "").split(" - ")[0],
            "forecast_end": periods.get("y3", "").split(" - ")[-1],
            "forecast_years": 3 if periods else None,
            "data_as_of": pd.Timestamp(f"{growth['as_of']}-01").strftime("%b %Y") if growth.get("as_of") else "",
            "models_used": _models_used(manifest),
            "sources": _data_sources(run_dir, matches, growth, catalog_path, any(t["categories"] for t in trends)),
            "source_docs": _source_documents(run_dir),
        },
        "overview": {
            "market": market_without_trends(
                read_json(run_dir / MARKET_FILE) or (forecast.get("llm_forecast_analysis") or {}).get("market_overview") or {},
                growth, rank_rows, trend_rows, {n["name"] for n in no_product}),
        },
        "takeaway": {
            "mega_trend_name": stepic_final.get("mega_trend_name", ""),
            "macro_direction": stepic_final.get("macro_direction", ""),
            "core_concept": stepic_final.get("core_concept", ""),
            "projection": stepic_final.get("3_month_projection", ""),
            "key_opportunity": stepic_final.get("key_opportunity", ""),
            "key_risk": stepic_final.get("key_risk", ""),
        },
        "stepic": _stepic_tiles(stepic_raw),
        "personas": _personas(stepic_final.get("emerging_personas")),
        "signals": _signals(stepic_final.get("cross_dimensional_signals")),
        "trends": trends,
        "growth": growth_pages,
        "excluded": excluded,
        "no_product_trends": no_product,
        "missing": missing,
    }
    return context, history
