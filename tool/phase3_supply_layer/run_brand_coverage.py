# -*- coding: utf-8 -*-
"""
Phase 3 — ⑬ จับคู่สินค้า (โหมด 1: แบรนด์ที่ขายอยู่บน Konvy จริงอยู่แล้ว; เดิม Watsons) (2026-09-11)
ดู Detail/05 งานที่ยังไม่ได้ทำ/Workflow v2 — แยกสายแล้วรวม.md ส่วน "⑬ จับคู่สินค้า EXFAC"

เจ้าของงานเลือก **โหมด 1** (จาก 2 โหมดที่เสนอ): "แบรนด์ไหนก็ได้ที่ขายอยู่บน Konvy แล้ว" - ผู้ใช้พิมพ์
ชื่อแบรนด์ตอนรัน แทนที่จะแก้ค่าคงที่ในไฟล์แบบ `analysis/run_exfac_trend_match.py` เดิม (ที่ต้อง
COMPANY_NAME/PRODUCT_CATALOG_PATH ก่อนรันทีละบริษัท) — **ไม่ต้องอัปโหลดไฟล์ ไม่ต้อง scrape ใหม่เลย**
เพราะ ⑫ มีข้อมูลสินค้าจริงครบ 10,622 SKU จาก 695 แบรนด์อยู่แล้ว แค่ filter ตาม brand ที่ผู้ใช้เลือก

**ทุก embedding ที่ใช้เป็นของที่คำนวณไว้แล้วจาก ⑫ (`validate_at_scale_nvidia.py`) - ไม่ยิง NVIDIA API
เพิ่มเลยสำหรับฝั่งสินค้า** (โหลด checkpoint .pkl ที่ embed ครบ 10,622 ชิ้นไว้แล้ว) ยิงแค่ 15 ครั้งสำหรับ
เทรนด์ (เหมือนเดิม) แล้วคำนวณ cosine similarity **ใหม่ทั้งหมด** (deterministic, ไม่มีค่า API เลย -
เป็นแค่ numpy dot product ระหว่าง embedding ที่มีอยู่แล้ว) เพื่อได้ full distribution ทั้ง 10,622 ชิ้น
ต่อเทรนด์ (ไม่ใช่แค่ top-15 ที่ ⑫ เซฟไว้) - ใช้หา percentile ที่แบรนด์ที่เลือกอยู่ตรงไหนของทั้งตลาด

โมเดล/มิติต้องตรงกับที่ embed ตอน ⑫ เป๊ะ (nvidia/llama-nemotron-embed-vl-1b-v2, 2048 มิติ, asymmetric
query/passage) - ใช้ไฟล์เดียวกัน (`validate_at_scale_nvidia.py`) import ฟังก์ชันมาโดยตรง ไม่เขียนซ้ำ

🆕 (2026-09-16) ออกผล 2 ไฟล์ต่อแบรนด์ตามที่เจ้าของงานขอ: JSON เดิม + **Excel**
(`phase3_brand_coverage_<แบรนด์>.xlsx` ชีต "สรุป" + "รายเทรนด์") - ข้อมูลชุดเดียวกันเป๊ะ ไม่ได้คำนวณเพิ่ม
ดู `save_coverage_excel()`

🆕 (2026-10-05) เพิ่ม `coverage[เทรนด์]["price_tiers"]` = เทรนด์ -> หมวด L2 หลัก -> 3 ระดับราคาจากราคาสินค้าของแบรนด์เอง
(ดู price_tiers.py) สำหรับรายงาน ⑱ (build_brand_category_report.py) - ใช้ similarity ชุดเดียวกับที่คำนวณอยู่แล้ว ไม่เรียก LLM
เพิ่ม รอบเก่าที่ยังไม่มีคีย์นี้เติมย้อนหลังได้โดยไม่รัน ⑬ ใหม่ทั้งชุด (ไม่แตะเหตุผล LLM เดิม):
    python tool/phase3_supply_layer/run_brand_coverage.py --tiers-only [--brand Mizumi --brand Eucerin]
    (เลือกรอบด้วย TREND_RUN_ID; ไม่ใส่ --brand = ทุกแบรนด์ที่มีไฟล์ ⑬ ในรอบนั้น; embed เทรนด์ใหม่ ~1 เรียก/เทรนด์ ครั้งเดียวใช้ร่วมทุกแบรนด์)
🆕 (2026-10-07) เพิ่ม `coverage[เทรนด์]["category_fit"]` = เทรนด์ -> หมวด L2 ที่เทรนด์แตะ -> ช่วงราคาตลาด -> สินค้า (ดู
category_fit.py) รายงาน ⑰/⑱ ใช้ตัดเกรด - สินค้าที่ดีที่สุดของแบรนด์ในแต่ละหมวดได้เหตุผลจับคู่ (ใช้ของเดิมใน brand_top_matches
ถ้าเป็นชิ้นเดียวกัน ไม่งั้นให้ LLM เขียน) รอบเก่าเติมย้อนหลังได้:
    python tool/phase3_supply_layer/run_brand_coverage.py --category-fit-only [--brand Mizumi] [--no-llm]
🆕 (2026-10-05) Excel มีคอลัมน์ลิงก์สินค้า (JSON เก็บ product_url / market_best_url ตั้งแต่รอบนี้) - Excel ของรอบเก่าสร้างใหม่ได้ด้วย
    python tool/phase3_supply_layer/run_brand_coverage.py --excel-only [--brand Mizumi]   (ไม่คำนวณใหม่ ไม่เรียก API)
"""
import difflib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import OUTPUTS, prompt_run_config  # noqa: E402
from common.match_quality import result_agreement  # noqa: E402

from validate_at_scale_nvidia import (  # noqa: E402
    MAIN_CATEGORY_LABELS, generate_match_reason, get_embedding, load_checkpoint, load_real_trend_profiles,
)
from product.euromonitor_mapping import BEAUTY_L1, load_catalog  # noqa: E402
from match_supply import build_trend_matchable_text, cosine_similarity  # noqa: E402
from price_tiers import N_TIERS, TOP_N, price_tier_breakdown  # noqa: E402
from category_fit import category_fit  # noqa: E402
from sales_level import market_sales  # noqa: E402
from unit_price_tiers import market_tiers  # noqa: E402
from trend_category import main_categories  # noqa: E402

TOP_MATCH_TIER = 67  # percentile >= นี้ = แบรนด์มีของเข้าเทรนด์จริง (เทียบชั้นเดียวกับ match_supply.py)
GAP_TIER = 33        # percentile <= นี้ = ยังไม่มีของเข้าเทรนด์นี้เลย (เทียบกับตลาดทั้งหมด)
# 🆕 (2026-09-16) จำนวนสินค้าของแบรนด์ที่เก็บ+ขอเหตุผลต่อเทรนด์ (เดิมเก็บแค่ชิ้นที่ดีที่สุดชิ้นเดียว) -
# ตรงกับ MATCH_REASON_TOP_K ของ ⑫ ค่าใช้จ่าย LLM = จำนวนเทรนด์ x ค่านี้ ต่อการค้น 1 แบรนด์
BRAND_TOP_K = 5


def save_coverage_excel(path, brand, n_brand_skus, n_market_skus, coverage_report, urls=None, l2=None,
                        market_tops=None, trend_set=None, no_close=None):
    """🆕 (2026-09-16) เซฟผล ⑬ เป็น Excel คู่กับ JSON ตามที่เจ้าของงานขอ - **ข้อมูลชุดเดียวกันเป๊ะกับ JSON**
    ไม่ได้คำนวณอะไรเพิ่มหรือตัดอะไรทิ้ง แค่จัดเป็นตารางให้เปิดอ่าน/ส่งต่อได้โดยไม่ต้องเปิด JSON

    4 ชีต: "สรุป" (แบรนด์/ขนาดตลาด/จำนวนเทรนด์แต่ละสถานะ), **"Top 5 ต่อเทรนด์"** (1 แถว = 1 สินค้า -
    สินค้าของแบรนด์ 5 อันดับแรกในแต่ละเทรนด์ พร้อมเหตุผลรายชิ้น 🆕 2026-09-16 ตามที่เจ้าของงานขอ),
    🆕 (2026-10-05) **"รายเทรนด์"** = หลายแถวต่อเทรนด์ เรียงตามอันดับเทรนด์ จัดตามกลุ่มราคาแบบรายงาน ⑱: ต่อกลุ่มราคา top 5 ของ
    หมวดหลัก (L2) ในกลุ่มนั้น + สินค้าที่ดีที่สุดของแบรนด์พร้อมอันดับในกลุ่ม (ดู trend_product_rows) และ "สรุปรายเทรนด์" (เดิมชื่อ "รายเทรนด์":
    1 แถว = 1 เทรนด์ ภาพรวมเรียงตามคะแนนมากไปน้อย เหมือนลำดับที่พิมพ์ออกหน้าจอ)
    l2 = product_l2_index(แคตตาล็อก), market_tops = {คีย์เทรนด์: top สินค้าของตลาด} สำหรับผลรอบเก่าที่ JSON ยังไม่มี
    market_top_matches (ใช้ top_matches ของ ⑫ รอบเดียวกัน), trend_set = {(สาย, เทรนด์)} ชุดเทรนด์ของรอบ (⑪) - ชีต "รายเทรนด์"
    แสดงเฉพาะเทรนด์ในชุดนี้ (ผล ⑬ เก่าอาจมีเทรนด์จาก ⑪ ชุดก่อนที่รายงานไม่ได้ใช้แล้ว) ไม่ส่ง = ทุกเทรนด์

    รับผลรอบเก่าที่ยังไม่มี `brand_top_matches` ได้ (ตกลงมาใช้ชิ้นที่ดีที่สุดชิ้นเดียวแทน ไม่ error)

    🆕 (2026-10-05) คอลัมน์ "ลิงก์สินค้า" (กดเปิดหน้าสินค้าบน Konvy ได้) ข้างชื่อสินค้าทุกช่อง - ใช้ product_url ที่เก็บใน JSON
    ถ้ามี ไม่มี (ผลรอบเก่า) ค้นจาก urls = product_url_index(แคตตาล็อก)"""
    from openpyxl.styles import Alignment
    from openpyxl.utils import get_column_letter

    grading = fit_grading()   # (เติม sys.path ของ phase6_pdf_report ให้ด้วย - l2_map อยู่ที่นั่น)
    coverage_report = l2_grading(brand, coverage_report)   # 🆕 (2026-10-21) เกรดใน Excel เทียบในหมวด L2 อย่างเดียว (เหมือนรายงาน ⑰) เมื่อรอบนี้มีแผนที่ L2 ของ ⑫
    by_score = sorted(coverage_report.values(), key=lambda v: v["brand_best_score"] or -1, reverse=True)
    urls = urls or {}

    def brand_url(m):
        return m.get("product_url") or urls.get((brand, m.get("product_name")))

    top_rows = []
    for r in by_score:
        if (no_close or {}).get((r.get("stream"), r.get("trend_name"))):   # ไม่ให้เกรด - ไม่แสดงสินค้าของแบรนด์ที่ "ใกล้เทรนด์" ในเทรนด์นี้
            continue
        matches = r.get("brand_top_matches")
        if matches is None:  # ผลรอบเก่า (ก่อน 2026-09-16) - มีแค่ชิ้นที่ดีที่สุดชิ้นเดียว
            matches = [{"rank_in_brand": 1, "product_name": r["brand_best_product"],
                        "category": "", "similarity": r["brand_best_score"],
                        "rank_vs_market": r.get("brand_best_rank_vs_market"),
                        "percentile_vs_market": r.get("brand_best_percentile_vs_market"),
                        "sale_price_thb": None, "sold_count": None,
                        "match_reason": r.get("match_reason", "")}] if r["brand_best_product"] else []
        for m in matches:
            top_rows.append({
                "อันดับเทรนด์": display_trend_rank(r),
                "สาย": r["stream"],
                "เทรนด์": r["trend_name"],
                "อันดับสินค้าในแบรนด์": m["rank_in_brand"],
                "สินค้า": m["product_name"],
                "ลิงก์สินค้า": brand_url(m),
                "หมวด": m.get("category") or "",
                "คะแนนความใกล้เคียง": m["similarity"],
                "อันดับในตลาด": f"{m['rank_vs_market']}/{n_market_skus}" if m.get("rank_vs_market") else None,
                "เปอร์เซ็นไทล์": m.get("percentile_vs_market"),
                "ราคา (฿)": m.get("sale_price_thb"),
                "ขายไปแล้ว": m.get("sold_count"),
                "เหตุผล": m.get("match_reason") or "",
            })
    df_top = pd.DataFrame(top_rows)

    rows = []
    for r in by_score:
        rank_vs_market = r.get("brand_best_rank_vs_market")
        info = trend_grade_info(r.get("category_fit"), grading)
        level, grade_cat, grade_tier = (None, None, None) if info is None else (info["level"], info["category"], info["tier"])
        ag = (no_close or {}).get((r.get("stream"), r.get("trend_name")))
        best = (r.get("brand_top_matches") or [{"product_name": r["brand_best_product"]}])[0]  # ชิ้นอันดับ 1 = brand_best
        rows.append({
            "อันดับเทรนด์": display_trend_rank(r),
            "สาย": r["stream"],
            "เทรนด์": r["trend_name"],
            "สถานะ": r["tier"],
            # 🆕 (2026-10-07) ระดับแบบรายงาน ⑰ (เทรนด์ -> หมวดหลัก -> ช่วงราคาตลาด -> สินค้า)
            "ระดับ (รายงาน)": NO_CLOSE_LEVEL if ag else (LEVEL_NAMES.get(level) if level else None),
            "ระดับมาจาก": no_close_reason(ag) if ag else ((grade_cat if grade_tier == "all" else f"{grade_cat} · {group_names(r.get('category_fit')).get(grade_tier, grade_tier)}")
                           if grade_cat else ("— ไม่มีสินค้าในหมวดของเทรนด์" if level else None)),
            f"สินค้า {brand} ที่ใกล้เทรนด์สุด": r["brand_best_product"] or "— ไม่มี SKU ไหนใกล้เคียงเลย",
            f"ลิงก์สินค้า {brand}": brand_url(best) if r["brand_best_product"] else None,
            "คะแนนความใกล้เคียง": r["brand_best_score"],
            "อันดับในตลาด": f"{rank_vs_market}/{n_market_skus}" if rank_vs_market else None,
            "เปอร์เซ็นไทล์": r["brand_best_percentile_vs_market"],
            "SKU ที่เทียบ": r["brand_n_skus_considered"],
            "เหตุผล": r.get("match_reason") or "",
            "สินค้าที่ดีที่สุดในตลาด (ทุกแบรนด์)": r["market_best_product"],
            "ลิงก์สินค้าในตลาด": r.get("market_best_url") or urls.get(r["market_best_product"]),
            "คะแนนของตลาด": r["market_best_score"],
        })
    df_trends = pd.DataFrame(rows)
    df_products = pd.DataFrame(trend_product_rows(brand, coverage_report, n_market_skus, urls, l2, market_tops,
                                                  trend_set=trend_set, grading=grading, no_close=no_close))

    summary = [("แบรนด์", brand),
               ("จำนวน SKU ของแบรนด์นี้", n_brand_skus),
               ("ขนาดตลาดที่เทียบ (SKU)", n_market_skus),
               ("จำนวนเทรนด์ที่เทียบ", len(df_trends)),
               (f"สินค้าที่แสดงต่อเทรนด์ (สูงสุด {BRAND_TOP_K} อันดับ)", len(df_top))]
    if not df_trends.empty:
        summary += [(f"เทรนด์ที่ '{tier}'", int(n)) for tier, n in df_trends["สถานะ"].value_counts().items()]
    n_nc = sum(1 for r in by_score if (r.get("stream"), r.get("trend_name")) in (no_close or {}))
    if n_nc:
        summary.append(("เทรนด์ที่ไม่ให้เกรด (ไม่มีสินค้าที่ใกล้พอ)", n_nc))
    df_summary = pd.DataFrame(summary, columns=["หัวข้อ", "ค่า"])

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet, frame in (("สรุป", df_summary), ("Top 5 ต่อเทรนด์", df_top), ("รายเทรนด์", df_products),
                             ("สรุปรายเทรนด์", df_trends)):
            frame.to_excel(writer, sheet_name=sheet, index=False)
            ws = writer.sheets[sheet]
            ws.freeze_panes = "A2"
            for i, col in enumerate(frame.columns, start=1):
                longest = max([len(str(col))] + [len(str(v)) for v in frame[col].tolist()] or [0])
                ws.column_dimensions[get_column_letter(i)].width = min(max(12, longest + 2), 55)
                if col == "เหตุผล":  # ข้อความยาว - ตัดบรรทัดในช่องแทนการลากยาวออกนอกจอ
                    for cell in ws[get_column_letter(i)][1:]:
                        cell.alignment = Alignment(wrap_text=True, vertical="top")
            _link_cells(ws, frame)
            if sheet == "รายเทรนด์":
                _shade_brand_rows(ws, frame, brand)


def fit_grading():
    """🆕 (2026-10-07) เกณฑ์เกรดชุดเดียวกับรายงาน ⑰/⑱ (config/brand_report.json ผ่าน brand_data - ไม่เขียนกติกาซ้ำ)
    -> dict: top_pct, level(rank, n) -> "excellent"/.../"below_average", best_in_category(category), best_in_tier(tier)
    🆕 (2026-10-27) เกรดตามความใกล้เทรนด์ล้วน (ตัดยอดขาย Konvy ออก) ใช้ฟังก์ชันของ brand_data ตัวเดียวกับรายงาน ⑰"""
    report_dir = Path(__file__).resolve().parents[1] / "phase6_pdf_report"
    if str(report_dir) not in sys.path:
        sys.path.insert(0, str(report_dir))
    from brand_data import best_in_category, best_in_tier, fit_level, grade_product, load_config, rank_cuts

    cfg = load_config(Path(__file__).resolve().parents[2] / "config" / "brand_report.json")
    top_pct = cfg["fit_top_pct"]
    return {"top_pct": top_pct,
            "level": lambda rank, n: fit_level(rank, rank_cuts(n, top_pct)),
            "grade_product": lambda p, n_tier: grade_product(p, n_tier, top_pct),
            "best_in_category": lambda category: best_in_category(category, top_pct),
            "best_in_tier": lambda tier: best_in_tier(tier, top_pct)}


def l2_grading(brand, coverage_report):
    """🆕 (2026-10-21) ผล ⑬ ของแบรนด์ (dict เทรนด์ -> ผล) -> สำเนาที่ category_fit เป็นแบบหมวด L2 อย่างเดียว (เกรดเทียบในหมวดไม่แยกช่วงราคา - เจ้าของงานสั่งให้ตรงกับรายงาน ⑰)
    ใช้แผนที่ตลาดระดับหมวด L2 ที่ ⑫ เขียนไว้ในโฟลเดอร์รอบ (phase3_l2_market_map.json.gz); ไม่มีไฟล์ = คืนของเดิม (เกรดแบบหมวด x ช่วงราคา) ไม่แตะ JSON"""
    from l2_map import l2_coverage, load_map   # fit_grading เติม sys.path ของ phase6_pdf_report ให้แล้ว

    l2_data = load_map(OUTPUTS)
    if not l2_data:
        return coverage_report
    out = l2_coverage({"brand": brand, "coverage": coverage_report}, l2_data)
    if out.get("_l2_skipped"):
        print(f"  ⚠️ {brand}: เทรนด์ที่ไม่มีในแผนที่ L2 (Excel ใช้เกรดแบบเดิม): {', '.join(out['_l2_skipped'])}")
    return out["coverage"]


def _grading_fns(grading):
    """grading ที่มีแค่ top_pct + level (เช่นในเทสต์) -> เติมฟังก์ชันเกรดจาก brand_data ด้วยเส้นตัดเดียวกัน"""
    if all(k in grading for k in ("best_in_tier", "best_in_category")):
        return grading
    report_dir = Path(__file__).resolve().parents[1] / "phase6_pdf_report"
    if str(report_dir) not in sys.path:
        sys.path.insert(0, str(report_dir))
    from brand_data import best_in_category, best_in_tier

    top_pct = grading["top_pct"]
    return {**grading, "best_in_tier": lambda t: best_in_tier(t, top_pct),
            "best_in_category": lambda c: best_in_category(c, top_pct)}


LEVEL_NAMES = {"excellent": "Excellent", "good": "Good", "average": "Average", "below_average": "Below average"}
LEVEL_ORDER = list(LEVEL_NAMES)
# 🆕 (2026-10-28) เทรนด์ที่ "ไม่มีสินค้าที่ใกล้พอ" (common/match_quality.py: สินค้า 5 ชิ้นที่ใกล้เทรนด์ที่สุดของทั้งร้านอยู่ในหมวดหลักน้อยกว่า 2 ชิ้น) ไม่ให้เกรด -
# เกรดในหมวดหลักของเทรนด์ที่สินค้าใกล้สุดไม่ได้อยู่ในหมวดนั้นไม่สะท้อนเทรนด์ (เหมือนรายงาน ⑯/⑰) - ข้อมูลดิบใน JSON ไม่ถูกแตะ ธงมาจากผล ⑫ ของรอบเดียวกัน
NO_CLOSE_LEVEL = "ไม่ให้เกรด (ไม่มีสินค้าที่ใกล้พอ)"


def no_close_reason(ag):
    return f"— สินค้าที่ใกล้เทรนด์ที่สุดอยู่ในหมวด {ag['category']} แค่ {ag['in_main']} จาก {ag['top_n']} ชิ้น จึงไม่ให้เกรด"


def load_no_close_of_run():
    """{(สาย, เทรนด์): category_agreement} เฉพาะเทรนด์ที่ไม่มีสินค้าที่ใกล้พอ จาก ⑫ ของรอบนี้ (top_matches + main_category) - ไม่มีไฟล์ = {}"""
    path = OUTPUTS / "phase3_scale_validation_nvidia_result.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        results = json.load(f).get("results") or {}
    out = {}
    for key, v in results.items():
        ag = result_agreement(v)
        if ag and not ag["ok"]:
            out[(v.get("stream"), v.get("trend_name") or key.split("::")[-1])] = ag
    return out


def trend_grade_info(fit, grading):
    """category_fit ของ 1 เทรนด์ -> สินค้าของแบรนด์ที่เกรดดีที่สุดในหมวดหลักของเทรนด์ (กติกา ⑰ - ตามความใกล้เทรนด์ล้วน):
    {"level", "category", "tier" (label), "product" (ดิบจาก category_fit)}
    ไม่มีสินค้าในหมวดหลัก -> level "below_average" ที่เหลือเป็น None / ไม่มี category_fit -> None"""
    if not fit:
        return None
    bic = _grading_fns(grading)["best_in_category"]
    best = None
    for c in fit.get("categories") or []:
        tier, tb = bic(c)
        if tb:
            raw = tb["raw"]
            cand = (LEVEL_ORDER.index(tb["level"]), raw["rank_in_tier"] / tier["n_total"], {
                "level": tb["level"], "category": c["category"], "tier": tier["label"], "product": raw})
            best = min(best, cand, key=lambda x: x[:2]) if best else cand
    return best[2] if best else {"level": "below_average", "category": None, "tier": None, "product": None}


def trend_grade(fit, grading):
    """category_fit ของ 1 เทรนด์ -> (ระดับ, หมวด, ช่วงราคา label) ของสินค้าที่ดีที่สุดของแบรนด์ในหมวดหลักของเทรนด์ ตามกติกา ⑰
    (ดู trend_grade_info) ไม่มีสินค้าในหมวดหลัก -> ("below_average", None, None) /
    ไม่มี category_fit -> (None, None, None)"""
    info = trend_grade_info(fit, grading)
    return (None, None, None) if info is None else (info["level"], info["category"], info["tier"])


PRODUCT_ROW_TYPE_MARKET = "Top 5 ตลาด"
PRODUCT_ROW_TYPE_TIER = "Top 5 กลุ่มราคา"
PRODUCT_ROW_TYPE_CATEGORY = "Top 5 ในหมวด"   # 🆕 (2026-10-21) เกรดเทียบในหมวด L2 อย่างเดียว
# ชื่อกลุ่มราคาแบบเดียวกับรายงาน ⑱ ฉบับไทย (brand_category_i18n: tier_low/mid/high/all)
PRICE_GROUP_NAMES = {"low": "ราคาต่ำ", "mid": "ราคากลาง", "high": "ราคาสูง", "all": "ทุกช่วงราคา"}
# 🆕 (2026-10-12) ช่วงจากราคาต่อปริมาณ (฿ ต่อ ml/g/ชิ้น เทียบภายในชนิดสินค้า) - ไม่มีช่วงบาทเดียว จึงไม่ใส่ตัวเลขช่วงในป้าย
PRICE_GROUP_NAMES_UNIT = {"low": "ราคาต่อปริมาณต่ำ", "mid": "ราคาต่อปริมาณกลาง", "high": "ราคาต่อปริมาณสูง", "all": "ทุกช่วง"}


def group_names(fit):
    """category_fit ของเทรนด์ -> ชื่อกลุ่มราคาที่ใช้ (ช่วงราคาต่อปริมาณหรือราคาขาย) - ผลรุ่นก่อนไม่มี tier_basis = ราคาขาย"""
    return PRICE_GROUP_NAMES_UNIT if (fit or {}).get("tier_basis") == "unit_price" else PRICE_GROUP_NAMES


def price_group_label(tier, unit=False):
    """ระดับราคา 1 ระดับของ price_tiers -> ป้ายแบบในรายงาน ⑱ เช่น "ราคาต่ำ 39-198 บาท" / "ทุกช่วงราคา 199 บาท" / "ทุกช่วงราคา"
    unit=True (ช่วงจากราคาต่อปริมาณ) -> ชื่อกลุ่มล้วน ไม่มีช่วงบาท"""
    names = PRICE_GROUP_NAMES_UNIT if unit else PRICE_GROUP_NAMES
    name = names.get(tier.get("label"), tier.get("label") or "")
    lo, hi = tier.get("price_from"), tier.get("price_to")
    if unit or lo is None:
        return name
    return f"{name} {lo:,} บาท" if lo == hi else f"{name} {lo:,}-{hi:,} บาท"


def fit_product_rows(brand, r, trend, grading, market_col, product):
    """🆕 (2026-10-07) แถวของ 1 เทรนด์จาก category_fit (ข้อมูลชุดเดียวกับ ⑰/⑱): หมวดหลักของเทรนด์ (🆕 2026-10-08 LLM เลือกหมวดเดียว) ->
    ต่อช่วงราคาตลาด -> top 5 ของกลุ่ม + สินค้าที่ดีที่สุดของแบรนด์ในกลุ่มพร้อมอันดับ / % แรก / ระดับ"""
    fit = r["category_fit"]
    unit = fit.get("tier_basis") == "unit_price"
    l2 = fit.get("group_basis") == "l2"   # 🆕 (2026-10-21) กลุ่มเทียบ = ทั้งหมวด L2 (l2_map.l2_category_fit) - ป้ายแทนคำว่ากลุ่ม/กลุ่มราคา
    brand_type, best_type = f"สินค้า {brand}", f"ดีที่สุดของ {brand} ในหมวดนี้" if l2 else f"ดีที่สุดของ {brand} ในกลุ่มนี้"
    top_type = PRODUCT_ROW_TYPE_CATEGORY if l2 else PRODUCT_ROW_TYPE_TIER
    k_group, k_n, k_brand, k_rank, k_pct = (("กลุ่มเทียบ", "สินค้าในหมวด", f"สินค้า {brand} ในหมวด", "อันดับในหมวด", "% แรกในหมวด") if l2
                                            else ("กลุ่มราคา", "สินค้าในกลุ่ม", f"สินค้า {brand} ในกลุ่ม", "อันดับในกลุ่ม", "% แรกในกลุ่ม"))
    rows = []
    for c in fit.get("categories") or []:
        cat = {**trend, "หมวด (L2)": c["category"]}
        for tier in c.get("tiers") or []:
            base = {**cat, k_group: "ทั้งหมวด" if l2 else price_group_label(tier, unit), k_n: tier.get("n_total"),
                    k_brand: tier.get("n_brand")}
            for m in tier.get("top") or []:
                mine = m.get("brand") == brand
                rows.append({**base, "ประเภท": f"{top_type} · {brand_type}" if mine else top_type,
                             k_rank: m.get("rank_in_tier"), market_col: m.get("rank_in_market"), **product(m)})
            fns = _grading_fns(grading)
            tb = fns["best_in_tier"](tier)
            if tb:
                bb, n = tb["raw"], tier.get("n_total") or 1
                rows.append({**base, "ประเภท": best_type, k_rank: bb["rank_in_tier"],
                             k_pct: round(bb["rank_in_tier"] / n * 100, 1),
                             "ระดับ": LEVEL_NAMES[tb["level"]],
                             market_col: bb.get("rank_in_market"), **product(bb, brand)})
            else:
                rows.append({**base, "ประเภท": best_type, "สินค้า": f"— ไม่มีสินค้า {brand} ในหมวดนี้" if l2 else f"— ไม่มีสินค้า {brand} ในกลุ่มนี้"})
    return rows


def trend_product_rows(brand, coverage_report, n_market_skus=None, urls=None, l2=None, market_tops=None, top_n=5,
                       trend_set=None, grading=None, no_close=None):
    """🆕 (2026-10-05) แถวของชีต "รายเทรนด์" เรียงตามอันดับเทรนด์ - จัดตามกลุ่มราคาแบบเดียวกับรายงาน ⑱ (ข้อมูล price_tiers ชุดเดียวกัน):
    ต่อเทรนด์ -> ต่อกลุ่มราคา (ระดับราคาของแบรนด์ในหมวดหลัก L2 ของเทรนด์) -> top 5 ของ "หมวด ∩ กลุ่มราคา" + สินค้าที่ดีที่สุดของแบรนด์
    ในกลุ่มนั้น พร้อมอันดับในกลุ่ม / ในหมวด / ทั้งตลาด, ราคา, ความคล้าย และลิงก์
    ผล ⑬ รอบเก่าที่ยังไม่มี price_tiers: top 5 ของตลาดทั้งหมด (market_top_matches ใน JSON หรือ market_tops = top_matches ของ ⑫)
    + สินค้าของแบรนด์ 5 อันดับแรก (กลุ่มราคาว่าง) - เติม price_tiers ด้วย --tiers-only แล้วสร้าง Excel ใหม่ได้
    trend_set = {(สาย, เทรนด์)} -> เอาเฉพาะเทรนด์ในชุดนี้ (ชุดเทรนด์ปัจจุบันของรอบ) ไม่ส่ง = ทุกเทรนด์ในผล ⑬"""
    urls, l2, market_tops = urls or {}, l2 or {}, market_tops or {}
    tier_market = next((v["category_fit"].get("n_market") for v in coverage_report.values() if v.get("category_fit")),
                       next((v["price_tiers"].get("n_market") for v in coverage_report.values() if v.get("price_tiers")), None))
    n_all = tier_market or n_market_skus
    market_col = f"อันดับทั้งตลาด (จาก {n_all:,} SKU)" if n_all else "อันดับทั้งตลาด"
    brand_type, best_type = f"สินค้า {brand}", f"ดีที่สุดของ {brand} ในกลุ่มนี้"
    grading = _grading_fns(grading or fit_grading())

    def product(m, b=None):
        b = b or m.get("brand")
        name = m.get("product_name")
        out = {"แบรนด์": b, "สินค้า": name, "ราคา (฿)": m.get("sale_price_thb"),
               "คะแนนความใกล้เคียง": m.get("similarity"), "ลิงก์สินค้า": m.get("product_url") or urls.get((b, name))}
        if m.get("unit_tier") is not None or m.get("unit_price") is not None or m.get("size") is not None:
            # 🆕 (2026-10-12) ช่วงราคาต่อปริมาณ: ขนาดรวม (คูณแพ็กแล้ว) + ฿ ต่อหน่วย + ธงขนาดทดลอง/ซอง
            unit_name = {"ml": "ml", "g": "g", "pcs": "ชิ้น"}.get(m.get("unit_label"), m.get("unit_label") or "")
            size = m.get("size")
            out["ขนาด"] = f"{size:g} {unit_name}".strip() if size else None
            out["฿ ต่อหน่วย"] = None if m.get("unit_price") is None else round(m["unit_price"], 2)
            out["ขนาดทดลอง/ซอง"] = "ใช่" if m.get("is_mini") else None
        return out

    def order(kv):
        rank = display_trend_rank(kv[1])
        return (rank is None, rank or 0, kv[1].get("trend_name") or "")

    rows = []
    for key, r in sorted(coverage_report.items(), key=order):
        if trend_set is not None and (r.get("stream"), r.get("trend_name")) not in trend_set:
            continue
        pt = r.get("price_tiers")
        trend = {"อันดับเทรนด์": display_trend_rank(r), "เทรนด์": r["trend_name"], "หมวด (L2)": (pt or {}).get("category") or ""}
        ag = (no_close or {}).get((r.get("stream"), r.get("trend_name")))
        if ag:   # 🆕 (2026-10-28) ไม่มีสินค้าที่ใกล้พอ - แถวเดียวบอกเหตุผล ไม่แสดงสินค้า/เกรด
            rows.append({**trend, "ประเภท": "ไม่ให้เกรด", "สินค้า": no_close_reason(ag)})
            continue
        if r.get("category_fit"):   # 🆕 (2026-10-07) เทรนด์ -> หมวด -> ช่วงราคาตลาด -> สินค้า (แบบ ⑰/⑱)
            rows += fit_product_rows(brand, r, trend, grading or fit_grading(), market_col, product)
            continue
        if pt:
            for tier in pt.get("tiers") or []:
                base = {**trend, "กลุ่มราคา": price_group_label(tier), "สินค้าในกลุ่ม": tier.get("n_market"),
                        "แบรนด์ในกลุ่ม": tier.get("n_brands")}
                for m in tier.get("top") or []:
                    kind = f"{PRODUCT_ROW_TYPE_TIER} · {brand_type}" if m.get("is_you") else PRODUCT_ROW_TYPE_TIER
                    rows.append({**base, "ประเภท": kind, "อันดับในกลุ่ม": m.get("rank_in_tier"), "% แรกในกลุ่ม": None,
                                 "อันดับในหมวด": m.get("rank_in_category"), market_col: m.get("rank_in_market"), **product(m)})
                bb = tier.get("brand_best")
                if bb:
                    rows.append({**base, "ประเภท": best_type, "อันดับในกลุ่ม": bb.get("rank_in_tier"),
                                 "% แรกในกลุ่ม": bb.get("top_pct_in_tier"), "อันดับในหมวด": bb.get("rank_in_category"),
                                 market_col: bb.get("rank_in_market"), **product(bb, brand)})
                else:
                    none = (f"— {brand} ไม่มีสินค้าในหมวดนี้" if tier.get("price_from") is None
                            else f"— ไม่มีสินค้า {brand} ในกลุ่มราคานี้")
                    rows.append({**base, "ประเภท": best_type, "สินค้า": none})
            continue
        # ผลรอบเก่า (ไม่มี price_tiers): top 5 ตลาดทั้งหมด + สินค้าของแบรนด์ - กลุ่มราคาว่าง
        for i, m in enumerate((r.get("market_top_matches") or market_tops.get(key) or [])[:top_n], 1):
            b = m.get("brand")
            kind = f"{PRODUCT_ROW_TYPE_MARKET} · {brand_type}" if b == brand else PRODUCT_ROW_TYPE_MARKET
            rows.append({**trend, "หมวด (L2)": l2.get((b, m.get("product_name"))) or m.get("category") or "",
                         "ประเภท": kind, market_col: m.get("rank_in_market") or i, **product(m)})
        matches = r.get("brand_top_matches") or (
            [{"product_name": r["brand_best_product"], "similarity": r.get("brand_best_score"),
              "rank_vs_market": r.get("brand_best_rank_vs_market")}] if r.get("brand_best_product") else [])
        for m in matches:
            rows.append({**trend, "หมวด (L2)": l2.get((brand, m.get("product_name"))) or m.get("category") or "",
                         "ประเภท": brand_type, market_col: m.get("rank_vs_market"), **product(m, brand)})
        if not matches:
            rows.append({**trend, "ประเภท": brand_type, "สินค้า": "— ไม่มี SKU ไหนใกล้เคียงเลย"})
    columns = ["อันดับเทรนด์", "เทรนด์", "หมวด (L2)", "กลุ่มราคา", "สินค้าในกลุ่ม",
               f"สินค้า {brand} ในกลุ่ม", "แบรนด์ในกลุ่ม", "กลุ่มเทียบ", "สินค้าในหมวด", f"สินค้า {brand} ในหมวด",
               "ประเภท", "อันดับในกลุ่ม", "% แรกในกลุ่ม", "% แรกในหมวด", "ระดับ",
               "อันดับในหมวด", market_col, "แบรนด์", "สินค้า", "ราคา (฿)", "ขนาด", "฿ ต่อหน่วย", "ขนาดทดลอง/ซอง",
               "คะแนนความใกล้เคียง", "ลิงก์สินค้า"]
    used = [c for c in columns if any(row.get(c) not in (None, "") for row in rows)] or columns
    return [{c: row.get(c) for c in used} for row in rows]


def _shade_brand_rows(ws, frame, brand):
    """แถวสินค้าของแบรนด์ในชีต "รายเทรนด์" ใส่สีพื้นอ่อน ให้แยกจาก top 5 ได้ด้วยตา"""
    from openpyxl.styles import PatternFill

    if "ประเภท" not in frame.columns:
        return
    fill = PatternFill("solid", start_color="FDEBD9", end_color="FDEBD9")
    for r, kind in enumerate(frame["ประเภท"].tolist(), start=2):
        if kind in (f"สินค้า {brand}", f"ดีที่สุดของ {brand} ในกลุ่มนี้"):
            for cell in ws[r]:
                cell.fill = fill


def product_l2_index(df):
    """🆕 (2026-10-05) แคตตาล็อก -> {(แบรนด์, ชื่อสินค้า): หมวด L2 ของ Euromonitor (EM_L2)}"""
    return {(b, n): g for b, n, g in zip(df["brand"], df["product_name"], df["EM_L2"]) if isinstance(g, str) and g}


def product_url_index(df):
    """🆕 (2026-10-05) แคตตาล็อก -> {(แบรนด์, ชื่อสินค้า): ลิงก์, "แบรนด์ - ชื่อสินค้า": ลิงก์} (รูปแบบหลังคือที่ ⑬ เก็บสินค้าเจ้าตลาด)"""
    index = {}
    for b, n, u in zip(df["brand"], df["product_name"], df["product_url"]):
        if isinstance(u, str) and u.startswith("http"):
            index.setdefault((b, n), u)
            index.setdefault(f"{b} - {n}", u)
    return index


def _link_cells(ws, frame):
    """คอลัมน์ที่ชื่อขึ้นต้นด้วย "ลิงก์" -> ทำเป็น hyperlink ที่กดเปิดได้"""
    from openpyxl.utils import get_column_letter

    for i, col in enumerate(frame.columns, start=1):
        if str(col).startswith("ลิงก์"):
            for cell in ws[get_column_letter(i)][1:]:
                if isinstance(cell.value, str) and cell.value.startswith("http"):
                    cell.hyperlink = cell.value
                    cell.style = "Hyperlink"


def resolve_brand(df, wanted):
    """หาแบรนด์ตรงตัว (case-insensitive) ก่อน ไม่เจอค่อยเดาแบรนด์ใกล้เคียงให้ (พิมพ์ผิด/ตัวพิมพ์)"""
    brands = df["brand"].dropna().unique().tolist()
    lower_map = {b.lower(): b for b in brands}
    if wanted.lower() in lower_map:
        return lower_map[wanted.lower()]
    close = difflib.get_close_matches(wanted, brands, n=5, cutoff=0.5)
    if close:
        print(f"  ⚠️ ไม่เจอแบรนด์ '{wanted}' ตรงตัว - แบรนด์ใกล้เคียงที่มี: {close}")
    return None


def load_trend_overall_rank():
    """🆕 (2026-09-15) โหลดอันดับรวมของเทรนด์ (ข้ามทุกสาย) จาก ⑥ (rank_trends.py's
    phase2_rank_score_final_mode_result.json) ถ้ามี - เจ้าของงานถามว่า "เรามีลำดับเทรนด์ 1 2 3 4 ไหม"
    (มี - ⑥ ทำอยู่แล้ว) แล้วขอให้เติมเข้าผล ⑬ ด้วยว่าเทรนด์นี้อยู่อันดับที่เท่าไหร่

    คืน {(stream, trend_name): overall_rank} - คืน dict ว่างถ้าไม่มีไฟล์ (⑥ ไม่ใช่ required stage เลย
    ใน main.py's STAGES อาจไม่เคยรันมาก่อนในบางรอบ) หรือไฟล์อ่านไม่ได้ - ไม่ error เพราะ ⑬ ต้องทำงาน
    ต่อได้แม้ไม่มีอันดับให้โชว์ (แค่ขึ้น "-" แทน)

    ⚠️ ถ้า ⑥ รันกับข้อมูลคนละชุดกับ ⑪/⑫ ที่ ⑬ นี้ใช้อยู่ (ชื่อเทรนด์ไม่ตรงกันเป๊ะ) lookup จะไม่เจอเงียบๆ
    (คืน None ต่อเทรนด์นั้น) ไม่ผิดพลาด แต่ก็ไม่มีอันดับให้เหมือนกัน - ต้องรัน ⑥ ใหม่กับชุดข้อมูลเดียวกัน
    ถึงจะได้อันดับที่ตรงกันจริง"""
    path = OUTPUTS / "phase2_rank_score_final_mode_result.json"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return {(row.get("Stream"), row.get("Trend Name")): row.get("Overall Rank") for row in data}


def load_trend_top_rank():
    """🆕 (2026-09-16) อันดับภายในชุด Top N (1..N) จาก selected_trends ของ ⑪ - เจ้าของงานตกลงให้แสดงอันดับเป็น
    1-10 แต่อันดับรวมของ ⑥ จัดกับทุกเทรนด์ พอ ⑪ ข้ามเทรนด์ที่จับคู่สินค้าไม่ได้แล้วดึงอันดับถัดไปขึ้นมา เลขจะกระโดด
    (เจอจริงรอบ 082438: 1, 2, 3, 5, ..., 10, 11) จึงใช้เลขนี้แสดงผลแทน - คืน {(stream, trend): top_rank} หรือ {}
    ถ้าเป็นผลรอบเก่าที่ ⑪ ยังไม่มีค่านี้ (แสดงอันดับของ ⑥ แทน ดู display_trend_rank)"""
    path = OUTPUTS / "phase3_trend_highlights_result.json"
    try:
        with open(path, encoding="utf-8") as f:
            selected = json.load(f).get("selected_trends") or []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return {(s["stream"], s["trend"]): s["top_rank"] for s in selected if s.get("top_rank") is not None}


def display_trend_rank(row):
    """อันดับเทรนด์ที่ใช้แสดงผล: อันดับภายใน Top N ถ้ามี ไม่มี (ผลรอบเก่า) ใช้อันดับรวมของ ⑥"""
    top_rank = row.get("trend_top_rank")
    return top_rank if top_rank is not None else row.get("trend_overall_rank")


def build_brand_section_markdown(brand, n_skus, n_market, coverage_report, no_close=None):
    """🆕 (2026-09-14) สร้างข้อความ markdown ของอันดับสินค้าแบรนด์ต่อเทรนด์ - แยกออกมาจาก __main__ ให้
    เทสได้ตรงๆ โดยไม่ต้องรัน embedding/similarity ใหม่ (ของแพง/ช้า) ทุกครั้งที่จะเทส

    🆕 (2026-09-16) ออก 2 ตาราง: ภาพรวม 1 แถว/เทรนด์ (ของเดิม) + "Top {BRAND_TOP_K} สินค้าในแต่ละเทรนด์"
    พร้อมเหตุผลรายชิ้น ตามที่เจ้าของงานขอ - ตารางที่ 2 จะไม่ขึ้นเลยถ้าเป็นผลรอบเก่าที่ไม่มี
    `brand_top_matches` (ไม่ error)"""
    lines = [f"\n---\n\n## Brand Coverage — {brand} ({n_skus} SKU)",
             f"> เพิ่มโดย ⑬ (`run_brand_coverage.py`, โหมด 1) - อันดับสินค้า {brand} เทียบกับสินค้า"
             f"**ทั้งตลาด {n_market} SKU จริง** ต่อเทรนด์ (ไม่ใช่ percentile เทียบแค่เทรนด์อื่นกันเอง) "
             f"| \"อันดับเทรนด์\" = อันดับภายในชุด Top N ของรอบนี้ (1 = Rank Score สูงสุด, \"-\" = ไม่มีข้อมูลอันดับ) "
             f"| \"เหตุผล\" มาจาก LLM - อธิบายเฉยๆ ไม่ตัดสิน similarity ยังเป็นตัวจัดอันดับหลัก "
             f"| ดูสินค้า {BRAND_TOP_K} อันดับแรกของแต่ละเทรนด์ในตารางถัดไป\n",
             f"| เทรนด์ | อันดับเทรนด์ | สาย | สินค้าที่ดีที่สุดของแบรนด์ | อันดับใน {n_market} | "
             f"Percentile | สถานะ | เหตุผล |",
             "|---|---|---|---|---|---|---|---|"]
    for key, r in sorted(coverage_report.items(), key=lambda kv: kv[1]["brand_best_score"] or -1,
                          reverse=True):
        product = (r["brand_best_product"] or "-").replace("|", "&#124;")
        rank = f"{r['brand_best_rank_vs_market']}/{n_market}" if r["brand_best_rank_vs_market"] else "-"
        pct = f"{r['brand_best_percentile_vs_market']}th" if r["brand_best_percentile_vs_market"] is not None else "-"
        trend_rank = display_trend_rank(r)
        trend_rank_str = f"#{trend_rank}" if trend_rank is not None else "-"
        reason = (r.get("match_reason") or "-").replace("|", "&#124;")
        status = "ไม่ให้เกรด (ไม่มีสินค้าที่ใกล้พอ)" if (no_close or {}).get((r.get("stream"), r.get("trend_name"))) else r["tier"]
        lines.append(f"| {r['trend_name']} | {trend_rank_str} | {r['stream']} | {product} | {rank} | "
                      f"{pct} | {status} | {reason} |")

    # 🆕 (2026-09-16) ตาราง top 5 สินค้าต่อเทรนด์ พร้อมเหตุผลรายชิ้น ตามที่เจ้าของงานขอ - ตารางแรกข้างบน
    # ยังเป็นภาพรวม 1 แถว/เทรนด์เหมือนเดิม (ใช้ดูสถานะรวมเร็วๆ) ตารางนี้คือรายละเอียดของแต่ละเทรนด์
    # ข้ามทั้งบล็อกถ้าเป็นผลรอบเก่าที่ยังไม่มี brand_top_matches (ไม่ error)
    detail_rows = []
    for key, r in sorted(coverage_report.items(), key=lambda kv: kv[1]["brand_best_score"] or -1,
                          reverse=True):
        for m in (r.get("brand_top_matches") or []):
            price = m.get("sale_price_thb")
            detail_rows.append(
                f"| {r['trend_name']} | {m['rank_in_brand']} | "
                f"{str(m['product_name']).replace('|', '&#124;')} | {m.get('category') or '-'} | "
                f"{m['similarity']} | {m['rank_vs_market']}/{n_market} | "
                f"{'-' if price is None else f'{price:,.0f}'} | "
                f"{(m.get('match_reason') or '-').replace('|', '&#124;')} |")
    if detail_rows:
        lines += ["",
                  f"### Top {BRAND_TOP_K} สินค้า {brand} ในแต่ละเทรนด์",
                  f"> เรียงตามคะแนนความใกล้เคียง (cosine similarity) ภายในเทรนด์ | \"อันดับในตลาด\" = "
                  f"อันดับของสินค้าชิ้นนั้นเทียบสินค้าทั้งตลาด {n_market} SKU | \"เหตุผล\" มาจาก LLM "
                  f"อธิบายรายชิ้น ไม่ได้ตัดสิน (similarity ยังเป็นตัวจัดอันดับ)\n",
                  f"| เทรนด์ | # | สินค้า | หมวด | คะแนน | อันดับในตลาด | ราคา (฿) | เหตุผล |",
                  "|---|---|---|---|---|---|---|---|"] + detail_rows
    return "\n".join(lines) + "\n"


def append_brand_section_to_report(report_path, brand, n_skus, n_market, coverage_report, no_close=None):
    """🆕 (2026-09-14) เจ้าของงานขอ: อันดับสินค้าแบรนด์ต่อเทรนด์ต้องไปโผล่ใน Master Report ด้วย ไม่ใช่แค่
    อยู่ในไฟล์ ⑬ แยกที่ไม่มีใครอ่านต่อ - ⑬ รัน**หลัง** ⑭-⑮ (run_stepic_report.py) เสมอตามลำดับใน main.py
    จึงต่อท้าย (append) เข้าไฟล์รายงานที่มีอยู่แล้วแทนที่จะย้อนไปแก้ trend_final_v2.py (รายงานเขียนเสร็จ
    ไปแล้วตอนนี้ถึงจะมาถึงจุดนี้) - ถ้ารันหลายแบรนด์ต่อกันในรอบเดียว (main.py's loop) แต่ละแบรนด์จะได้
    section แยกของตัวเอง ต่อท้ายไปเรื่อยๆ ตามลำดับที่พิมพ์

    คืน True ถ้าต่อท้ายสำเร็จ, False ถ้าไม่เจอไฟล์รายงาน (ไม่ error - ไฟล์ ⑬ แยกยังเซฟไว้ปกติเสมอ)"""
    if not report_path.exists():
        return False
    section = build_brand_section_markdown(brand, n_skus, n_market, coverage_report, no_close)
    with open(report_path, "a", encoding="utf-8") as f:
        f.write(section)
    return True


def load_market():
    """ตลาดเดียวกับ ⑫: กรอง L1 = Beauty and Personal Care (2026-10-01) - อันดับ/percentile เทียบกับตลาดความงามเท่านั้น
    คืน (df, all_idx, pos_of_idx, all_vecs): all_vecs แถวเรียงตาม all_idx, pos_of_idx = df index -> ตำแหน่งใน all_vecs/sims
    embedding ไม่ครบ -> จบโปรแกรม (ต้องรัน ⑫ ให้จบก่อน)"""
    df = load_catalog()
    print(f"โหลดสินค้าจริงแล้ว: {len(df)} รายการ (กรอง L1 = {BEAUTY_L1}), {df['brand'].nunique()} แบรนด์")

    # 🆕 (2026-09-12, audit m3) load_checkpoint(df) รับ df เพื่อ remap cache (เก็บด้วย content hash
    # กันเรียงแถวใหม่/อัปเดตแล้วจับคู่ผิด) กลับเป็น {df.index: vector} ตาม df ปัจจุบัน - ค่า None แปลว่า
    # สินค้าแถวนั้นยังไม่เคย embed (เนื้อหาไม่ตรงกับ hash ไหนใน cache เลย)
    product_embeddings = load_checkpoint(df)
    n_ready = sum(1 for v in product_embeddings.values() if v is not None)
    if n_ready < len(df):
        print(f"❌ embedding cache ไม่ครบ ({n_ready}/{len(df)}) - รัน "
              f"validate_at_scale_nvidia.py (⑫) ให้จบก่อน")
        sys.exit(1)
    all_idx = list(product_embeddings.keys())
    pos_of_idx = {idx: pos for pos, idx in enumerate(all_idx)}  # df index -> ตำแหน่งใน all_vecs/sims
    all_vecs = np.stack([product_embeddings[i] for i in all_idx])  # (8738, 2048)
    return df, all_idx, pos_of_idx, all_vecs


def embed_trend_profiles(trend_profiles):
    """trend profile จาก ⑪ -> embedding (input_type=query) คืน (vectors, names, streams, profile_by_key) คีย์ "สาย::เทรนด์" """
    print(f"\nกำลัง embed {len(trend_profiles)} trend profile (input_type=query)...")
    # 🆕 (2026-09-12, audit M4) key ผสม "stream::trend" กันชื่อเทรนด์ชนกันข้ามสายทับกันเงียบๆ
    # (แก้เหมือนกับที่แก้ใน validate_at_scale_nvidia.py)
    trend_vectors, trend_names, trend_streams, trend_profile_by_key = {}, {}, {}, {}
    for profile in trend_profiles:
        stream = profile.get("stream", "?")
        key = f"{stream}::{profile['trend']}"
        text = build_trend_matchable_text(profile)
        # 🆕 (2026-09-16) ข้ามเทรนด์ที่ ⑪ ตอบ "ข้อมูลไม่พอ" ครบทุกฟิลด์ (ข้อความ embed ว่าง -> embedding API
        # ตอบ 400) เหมือนที่ทำใน validate_at_scale_nvidia.py (⑫) - ไม่งั้น ⑬ จะพังด้วยสาเหตุเดียวกัน
        if not text.strip():
            print(f"    ⏭️ ข้าม '{profile['trend']}' [{stream}] - ⑪ ตอบ 'ข้อมูลไม่พอ' ทุกฟิลด์ที่ใช้จับคู่")
            continue
        trend_vectors[key] = get_embedding(text, "query")
        trend_names[key] = profile["trend"]
        trend_streams[key] = stream
        trend_profile_by_key[key] = profile  # 🆕 (2026-09-15) เก็บไว้ป้อน generate_match_reason()
    print("เสร็จแล้ว")
    return trend_vectors, trend_names, trend_streams, trend_profile_by_key


def trend_similarities(all_vecs, tvec):
    """cosine similarity ของเทรนด์เทียบสินค้าทุกชิ้น (แถวเรียงตาม all_vecs)"""
    return all_vecs @ tvec / (np.linalg.norm(all_vecs, axis=1) * np.linalg.norm(tvec) + 1e-12)


def build_market_rows(df, all_idx, tier_recs=None):
    """🆕 (2026-10-05) สินค้าทุกชิ้นของตลาดในรูปที่ price_tier_breakdown ต้องการ (เรียงตาม all_idx) - หมวด = EM_Group (L2)
    เหมือน ⑫; sale_price_thb เป็น string มี comma คั่นหลักพัน (เช่น "1,790.00") ราคาอ่านไม่ได้/<= 0 = None"""
    sub = df.loc[all_idx]
    prices = pd.to_numeric(sub["sale_price_thb"].astype(str).str.replace(",", ""), errors="coerce")
    rows = [{"product_name": n, "brand": b, "group": g, "sale_price_thb": None if pd.isna(p) or p <= 0 else float(p)}
            for n, b, g, p in zip(sub["product_name"], sub["brand"], sub["EM_Group"], prices)]
    if tier_recs is not None:   # 🆕 (2026-10-12) ช่วงราคาต่อปริมาณ (unit_price_tiers.market_tiers) - ชุดเดียวกับที่ ⑫ ติดให้สินค้า
        for r, idx in zip(rows, all_idx):
            t = tier_recs[idx]
            r.update({k: t[k] for k in ("unit_tier", "unit_price", "unit_label", "size", "is_mini")})
    # 🆕 (2026-10-19) ยอดขาย Konvy ของสินค้าแต่ละชิ้น (sales_level.market_sales: เปอร์เซ็นไทล์ในกลุ่ม หมวด x ช่วงราคาต่อปริมาณ + ธงของหมด/ขาย 0)
    # ใช้ปรับเกรดสินค้าที่รายงาน ⑰ - ตลาดที่ไม่มีคอลัมน์ sold_count ข้าม (ไม่มีช่อง "sales" ในผล)
    if "sold_count" in sub.columns:
        for col in ("sold_count", "stock", "review_count"):
            if col in sub.columns:
                for r, v in zip(rows, sub[col]):
                    r[col] = None if pd.isna(v) else float(v)
        for r, sales in zip(rows, market_sales(rows, "unit_tier" if tier_recs is not None else None)):
            r["sales"] = sales
    return rows


def compute_price_tiers(sims, market_rows, brand):
    """similarity ของเทรนด์ 1 เทรนด์ (เรียงตาม market_rows) -> price_tier_breakdown ของแบรนด์"""
    scored = [{**r, "similarity": float(s)} for r, s in zip(market_rows, sims)]
    return price_tier_breakdown(scored, brand, N_TIERS, TOP_N)


def decide_main_categories(sims_by_key, market_rows, profiles, use_llm=True):
    """🆕 (2026-10-08) หมวดหลักของแต่ละเทรนด์ที่ LLM เลือก (trend_category.py - ใช้คำตัดสินเดิมที่ ⑫ บันทึกไว้ในไฟล์ labels ก่อน
    ไม่มี/ข้อความ profile หรือขนาดตลาดเปลี่ยนจึงถาม LLM) -> {คีย์เทรนด์: {"category", "reason", "source"}}
    sims_by_key = {คีย์: similarity ทั้งตลาด (เรียงตาม market_rows)}, profiles = {คีย์: profile จาก ⑪}"""
    entries = {key: (profiles[key], [{**r, "similarity": float(x)} for r, x in zip(market_rows, sims)])
               for key, sims in sims_by_key.items() if key in profiles}
    return main_categories(entries, MAIN_CATEGORY_LABELS, use_llm=use_llm)


def compute_category_fit(sims, market_rows, brand, decision, tier_key=None):
    """🆕 (2026-10-07) similarity ของเทรนด์ 1 เทรนด์ (เรียงตาม market_rows) -> category_fit ของแบรนด์ (ยังไม่มีเหตุผลสินค้า)
    decision = หมวดหลักของเทรนด์ (decide_main_categories) - เก็บเหตุผลที่เลือกหมวดไว้ใน fit["category_reason"]"""
    fit = category_fit([{**r, "similarity": float(s)} for r, s in zip(market_rows, sims)], brand, decision["category"],
                       tier_key=tier_key)
    if fit:
        fit["category_reason"] = decision.get("reason", "")
    return fit


def load_previous_reasons(path):
    """🆕 (2026-10-19) เหตุผลจับคู่ที่ ⑬ เคยเขียนไว้ในไฟล์เดิมของแบรนด์นี้ -> {คีย์เทรนด์: {ชื่อสินค้า: เหตุผล}} (จาก brand_top_matches และ
    สินค้าที่ดีที่สุดต่อหมวดใน category_fit) - เปลี่ยนชุดเทรนด์ (เช่น ปีระยะสั้นเปลี่ยนเป็นปีที่ 3) แล้วรันซ้ำ จะได้ไม่ต้องให้ LLM เขียนซ้ำของเทรนด์เดิม
    (⑪ ใช้จุดเด่นเดิม ข้อความจับคู่จึงเหมือนเดิม) เรียก LLM เฉพาะเทรนด์/สินค้าที่ยังไม่เคยมีเหตุผล - ไม่มีไฟล์/อ่านไม่ได้ = {}"""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for key, entry in (data.get("coverage") or {}).items():
        reasons = {m["product_name"]: m["match_reason"] for m in entry.get("brand_top_matches") or []
                   if m.get("product_name") and m.get("match_reason")}
        for c in ((entry.get("category_fit") or {}).get("categories") or []):
            best = c.get("brand_best") or {}
            if best.get("product_name") and best.get("match_reason"):
                reasons.setdefault(best["product_name"], best["match_reason"])
        if reasons:
            out[key] = reasons
    return out


def attach_fit_reasons(fit, brand_top, brand_rows, profile, use_llm=True, known_reasons=None, grading=None):
    """🆕 (2026-10-07) เหตุผลจับคู่ของสินค้าที่ดีที่สุดของแบรนด์ในแต่ละหมวด: ใช้ของเดิมใน brand_top_matches (ชิ้นเดียวกัน = ชื่อตรงกัน)
    ไม่มี -> ให้ LLM เขียน (generate_match_reason แบบเดียวกับ ⑫/⑬) เมื่อ use_llm ไม่งั้นเว้นว่าง
    brand_rows: {ชื่อสินค้า: แถวใน df} ของแบรนด์ - คืนจำนวนที่ให้ LLM เขียน
    🆕 (2026-10-19) known_reasons = เหตุผลเดิมของเทรนด์นี้จากไฟล์ ⑬ รอบก่อน (load_previous_reasons) - ใช้ก่อนเรียก LLM"""
    known = {**(known_reasons or {}), **{m["product_name"]: m.get("match_reason") for m in brand_top or [] if m.get("match_reason")}}
    n_llm = 0
    for c in (fit or {}).get("categories", []):
        best = c.get("brand_best")
        if not best:
            continue
        reason = known.get(best["product_name"])
        if not reason and use_llm and profile is not None and best["product_name"] in brand_rows:
            reason = generate_match_reason(profile, brand_rows[best["product_name"]])
            known[best["product_name"]] = reason
            n_llm += 1
        best["match_reason"] = reason or ""
        # ชิ้นที่ให้เกรดอาจไม่ใช่ชิ้นที่ใกล้เทรนด์ที่สุด (เกรดดีที่สุดในหมวด) -> เขียนเหตุผลที่ตัวสินค้าในกลุ่มนั้นด้วย (⑰ อ่านจาก
        # match_reason ของชิ้นที่ให้เกรดก่อน ไม่มีค่อยใช้ของ brand_best เมื่อเป็นชิ้นเดียวกัน)
        grading = grading or fit_grading()
        tier, tb = grading["best_in_category"](c)
        raw = tb["raw"] if tb else None
        if raw and raw["product_name"] != best["product_name"]:
            reason = known.get(raw["product_name"])
            if not reason and use_llm and profile is not None and raw["product_name"] in brand_rows:
                reason = generate_match_reason(profile, brand_rows[raw["product_name"]])
                known[raw["product_name"]] = reason
                n_llm += 1
            raw["match_reason"] = reason or ""
    return n_llm


def run_l2_reasons_only(wanted_brands, use_llm=True):
    """🆕 (2026-10-21) เกรดเทียบในหมวด L2 อย่างเดียว (l2_map.l2_category_fit) ทำให้สินค้าที่ให้เกรดของบางเทรนด์เป็นชิ้นที่ไม่เคยมีเหตุผลจับคู่ (⑬ เขียนให้เฉพาะชิ้นที่ให้
    เกรดแบบหมวด x ช่วงราคา) -> ให้ LLM เขียนเฉพาะชิ้นเหล่านั้น เก็บที่ entry["l2_reasons"] = {ชื่อสินค้า: เหตุผล} ในไฟล์ ⑬ (ไม่แตะอย่างอื่น - รายงาน ⑰ อ่านผ่าน
    l2_coverage) ไม่ embed ไม่เรียก API ฝั่งสินค้า; --no-llm = ไม่เขียน"""
    grading = fit_grading()   # เติม sys.path ของ phase6_pdf_report
    from l2_map import l2_coverage, load_map

    l2_data = load_map(OUTPUTS)
    if not l2_data:
        raise SystemExit("❌ ไม่มีแผนที่ตลาดระดับหมวด L2 ของรอบนี้ (phase3_l2_market_map.json.gz) - รัน validate_at_scale_nvidia.py --l2-map-only ก่อน")
    df = load_catalog()
    profiles = {f"{p.get('stream', '?')}::{p['trend']}": p for p in load_real_trend_profiles()}
    for path in coverage_paths(wanted_brands):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        brand, rows, n_llm = data["brand"], brand_rows_by_name(df, data["brand"]), 0
        converted = l2_coverage(data, l2_data)["coverage"]
        for key, entry in data["coverage"].items():
            fit = converted[key].get("category_fit")
            if not fit or fit.get("group_basis") != "l2":
                continue
            for c in fit.get("categories") or []:
                tier, tb = grading["best_in_category"](c)
                name = tb["raw"]["product_name"] if tb else None
                if not name or tb["raw"].get("match_reason") or (entry.get("l2_reasons") or {}).get(name):
                    continue
                if use_llm and profiles.get(key) is not None and name in rows:
                    entry.setdefault("l2_reasons", {})[name] = generate_match_reason(profiles[key], rows[name]) or ""
                    n_llm += 1
                    print(f"  {brand} · {entry.get('trend_name')}: {name[:60]}")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ {brand}: LLM เขียนเหตุผลของสินค้าที่ให้เกรดแบบหมวด L2 เพิ่ม {n_llm} ชิ้น -> {path.name}")


def brand_rows_by_name(df, brand):
    """{ชื่อสินค้า: แถวใน df} ของแบรนด์ (ชื่อซ้ำ -> แถวแรก) ไว้ป้อน generate_match_reason"""
    sub = df[df["brand"] == brand]
    return {name: sub.loc[idx] for idx, name in reversed(list(zip(sub.index, sub["product_name"])))}


def run_category_fit_only(wanted_brands, use_llm=True):
    """🆕 (2026-10-07) เติม category_fit ลงไฟล์ ⑬ ที่มีอยู่แล้ว (ไม่แตะอันดับ/เหตุผลเดิม) - embed เทรนด์อย่างเดียว (ฝั่งสินค้าใช้
    checkpoint) + LLM เฉพาะสินค้าที่ดีที่สุดของหมวดที่ยังไม่มีเหตุผล (--no-llm = เว้นว่าง) wanted_brands ว่าง = ทุกแบรนด์ในรอบ"""
    paths = coverage_paths(wanted_brands)
    df, all_idx, _, all_vecs = load_market()
    tier_recs, tier_key, tier_meta = market_tiers(df)   # 🆕 (2026-10-12) config/market_tiers.json: price / unit_price
    print(f"ช่วงราคา: {tier_meta['tier_basis']} {tier_meta['tier_config']}")
    market_rows = build_market_rows(df, all_idx, tier_recs)
    trend_vectors, _, _, profiles = embed_trend_profiles(load_real_trend_profiles())
    sims_by_key = {key: trend_similarities(all_vecs, tvec) for key, tvec in trend_vectors.items()}
    decisions = decide_main_categories(sims_by_key, market_rows, profiles, use_llm=use_llm)
    for key, d in decisions.items():
        print(f"  หมวดหลัก {key.split('::', 1)[-1][:45]}: {d['category']} ({d['source']})")
    grading = fit_grading()
    for path in paths:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        brand, n_added, n_llm = data["brand"], 0, 0
        rows = brand_rows_by_name(df, brand)
        for key, entry in data["coverage"].items():
            if key not in sims_by_key:
                print(f"  ⚠️ {brand}: เทรนด์ '{key}' ไม่อยู่ในผล ⑪ ปัจจุบัน - ข้าม (ไม่เติม category_fit)")
                continue
            fit = compute_category_fit(sims_by_key[key], market_rows, brand, decisions[key], tier_key)
            n_llm += attach_fit_reasons(fit, entry.get("brand_top_matches"), rows, profiles.get(key), use_llm, grading=grading)
            entry["category_fit"] = fit
            n_added += 1
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ {brand}: เติม category_fit {n_added}/{len(data['coverage'])} เทรนด์ (LLM เขียนเหตุผลเพิ่ม {n_llm}) -> {path.name}")


def _row_price(row):
    """ราคาขายของแถวสินค้า - sale_price_thb เป็น string มี comma คั่นหลักพัน (เช่น "1,790.00") เหมือน ⑫ อ่านไม่ได้ = None"""
    price = row.get("sale_price_thb")
    try:
        return None if pd.isna(price) else float(str(price).replace(",", ""))
    except (ValueError, TypeError):
        return None


def coverage_paths(wanted_brands):
    """ไฟล์ผล ⑬ ของรอบนี้ (OUTPUTS) เฉพาะแบรนด์ที่ขอ (ไม่สนตัวพิมพ์) - ว่าง = ทุกแบรนด์ ไม่พบเลย -> จบโปรแกรม"""
    wanted = {b.lower() for b in wanted_brands}
    paths = []
    for path in sorted(OUTPUTS.glob("phase3_brand_coverage_*.json")):
        with open(path, encoding="utf-8") as f:
            if not wanted or str(json.load(f).get("brand", "")).lower() in wanted:
                paths.append(path)
    if not paths:
        print(f"❌ ไม่พบไฟล์ ⑬ ของแบรนด์ที่ขอในรอบนี้ ({OUTPUTS})")
        sys.exit(1)
    return paths


def market_size_of_run(xlsx_path=None):
    """จำนวน SKU ของตลาดที่ ⑬ ของรอบนี้เทียบ (ไม่ได้เก็บใน JSON): ⑫ ของรอบเดียวกันใช้ตลาดชุดเดียวกัน (n_products_total) -
    ไม่มีไฟล์ ⑫ ใช้ค่าในชีต "สรุป" ของ Excel เดิม"""
    path = OUTPUTS / "phase3_scale_validation_nvidia_result.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            n = json.load(f).get("n_products_total")
        if n:
            return int(n)
    if xlsx_path and Path(xlsx_path).exists():
        summary = pd.read_excel(xlsx_path, sheet_name="สรุป")
        hit = summary.loc[summary["หัวข้อ"] == "ขนาดตลาดที่เทียบ (SKU)", "ค่า"]
        if not hit.empty:
            return int(hit.iloc[0])
    return None


def load_market_tops_of_run(top_n=5):
    """top N สินค้าของตลาดต่อเทรนด์จาก ⑫ ของรอบนี้ (top_matches) - ใช้กับผล ⑬ รอบเก่าที่ยังไม่มี market_top_matches"""
    path = OUTPUTS / "phase3_scale_validation_nvidia_result.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        results = json.load(f).get("results") or {}
    return {k: (v.get("top_matches") or [])[:top_n] for k, v in results.items()}


def run_excel_only(wanted_brands):
    """🆕 (2026-10-05) สร้าง Excel ของ ⑬ ใหม่จาก JSON เดิม (ได้คอลัมน์ลิงก์สินค้า) - ไม่คำนวณใหม่ ไม่เรียก API ไม่แก้ JSON
    ลิงก์ค้นจากแคตตาล็อกเต็ม (ไม่กรองหมวด) เพราะผลรอบเก่าเทียบกับตลาด 10,622 SKU ที่มีสินค้านอกหมวดความงามด้วย"""
    paths = coverage_paths(wanted_brands)
    catalog = load_catalog(beauty_only=False)
    urls, l2 = product_url_index(catalog), product_l2_index(catalog)
    market_tops = load_market_tops_of_run()
    no_close = load_no_close_of_run()   # 🆕 (2026-10-28) เทรนด์ที่ไม่ให้เกรด
    top_rank = load_trend_top_rank()   # อันดับเทรนด์ปัจจุบันของ ⑪ (รายงานใช้เลขนี้) - แสดงใน Excel ให้ตรงกัน ไม่แก้ JSON
    for path in paths:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        coverage = {k: ({**v, "trend_top_rank": top_rank[(v.get("stream"), v.get("trend_name"))]}
                        if (v.get("stream"), v.get("trend_name")) in top_rank else v)
                    for k, v in data["coverage"].items()}
        xlsx_path = path.with_suffix(".xlsx")
        n_market = market_size_of_run(xlsx_path)
        save_coverage_excel(xlsx_path, data["brand"], data.get("n_skus"), n_market, coverage, urls=urls, l2=l2,
                            market_tops=market_tops, trend_set=set(top_rank) or None, no_close=no_close)
        extra = [v["trend_name"] for v in data["coverage"].values() if (v.get("stream"), v.get("trend_name")) not in top_rank]
        if top_rank and extra:
            print(f"  ℹ️ {data['brand']}: {len(extra)} เทรนด์ในผล ⑬ ไม่อยู่ในชุดเทรนด์ของรอบนี้ (⑪) - ไม่ใส่ในชีต \"รายเทรนด์\" "
                  f"(ยังอยู่ในชีตอื่น): {', '.join(extra)}")
        print(f"✅ {data['brand']}: สร้าง Excel ใหม่ (ตลาด {n_market} SKU) -> {xlsx_path.name}")


def run_tiers_only(wanted_brands):
    """🆕 (2026-10-05) เติม price_tiers ลงไฟล์ ⑬ ที่มีอยู่แล้ว (ไม่เรียก LLM ไม่แตะเหตุผล/อันดับเดิม) - ต้องใช้ API ฝั่ง embedding
    เทรนด์เท่านั้น (ฝั่งสินค้าใช้ checkpoint) wanted_brands ว่าง = ทุกแบรนด์ที่มีไฟล์ในรอบนั้น"""
    paths = coverage_paths(wanted_brands)

    df, all_idx, _, all_vecs = load_market()
    market_rows = build_market_rows(df, all_idx)
    trend_vectors, _, _, _ = embed_trend_profiles(load_real_trend_profiles())
    for path in paths:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        brand, n_added = data["brand"], 0
        for key, entry in data["coverage"].items():
            if key not in trend_vectors:
                print(f"  ⚠️ {brand}: เทรนด์ '{key}' ไม่อยู่ในผล ⑪ ปัจจุบัน - ข้าม (ไม่เติม price_tiers)")
                continue
            entry["price_tiers"] = compute_price_tiers(trend_similarities(all_vecs, trend_vectors[key]), market_rows, brand)
            n_added += 1
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ {brand}: เติม price_tiers {n_added}/{len(data['coverage'])} เทรนด์ -> {path.name}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="⑬ Brand Coverage (โหมด 1)")
    parser.add_argument("--tiers-only", action="store_true",
                        help="เติม price_tiers (เทรนด์ -> หมวด -> ระดับราคา สำหรับรายงาน ⑱) ลงไฟล์ ⑬ ที่มีอยู่แล้ว - ไม่เรียก LLM")
    parser.add_argument("--excel-only", action="store_true",
                        help="สร้าง Excel ของไฟล์ ⑬ ที่มีอยู่แล้วใหม่ (เพิ่มคอลัมน์ลิงก์สินค้า) - ไม่คำนวณใหม่ ไม่เรียก API")
    parser.add_argument("--category-fit-only", action="store_true",
                        help="🆕 เติม category_fit (เทรนด์ -> หมวด -> ช่วงราคาตลาด -> สินค้า สำหรับเกรดใน ⑰/⑱) ลงไฟล์ ⑬ ที่มีอยู่แล้ว")
    parser.add_argument("--l2-reasons-only", action="store_true",
                        help="🆕 (2026-10-21) ให้ LLM เขียนเหตุผลจับคู่ของสินค้าที่ให้เกรดแบบเทียบในหมวด L2 อย่างเดียว (เฉพาะชิ้นที่ยังไม่มีเหตุผล) เก็บที่ l2_reasons ในไฟล์ ⑬")
    parser.add_argument("--no-llm", action="store_true",
                        help="ใช้กับ --category-fit-only: ไม่ให้ LLM เขียนเหตุผลของสินค้าที่ยังไม่มี (เว้นว่าง)")
    parser.add_argument("--brand", action="append", default=[],
                        help="ใช้กับ --tiers-only / --excel-only / --category-fit-only: แบรนด์ที่จะทำ (ซ้ำได้)")
    cli = parser.parse_args()
    if cli.category_fit_only:
        run_category_fit_only(cli.brand, use_llm=not cli.no_llm)
        sys.exit(0)
    if cli.l2_reasons_only:
        run_l2_reasons_only(cli.brand, use_llm=not cli.no_llm)
        sys.exit(0)
    if cli.tiers_only:
        run_tiers_only(cli.brand)
        sys.exit(0)
    if cli.excel_only:
        run_excel_only(cli.brand)
        sys.exit(0)

    print("=" * 70)
    print("Phase 3 ⑬ (โหมด 1) — Brand Coverage: แบรนด์บน Konvy vs Top N เทรนด์ของรอบนี้ (จาก ⑪)")
    print("=" * 70)

    df, all_idx, pos_of_idx, all_vecs = load_market()

    brand_wanted, _ = prompt_run_config(default_topic="Eucerin", default_years=3, ask_years=False)
    # prompt_run_config ถามแบบ "หัวข้อ" ทั่วไป - ใช้ค่าที่ได้เป็นชื่อแบรนด์ตรงๆ (ไม่เกี่ยวกับปี)
    brand = resolve_brand(df, brand_wanted)
    if brand is None:
        print(f"❌ ไม่เจอแบรนด์ '{brand_wanted}' บน Konvy เลย (ดูรายชื่อใกล้เคียงด้านบน) - ลองใหม่")
        sys.exit(1)

    brand_idx = df.index[df["brand"] == brand].tolist()
    print(f"✅ พบแบรนด์ '{brand}': {len(brand_idx)} SKU")

    trend_vectors, trend_names, trend_streams, trend_profile_by_key = embed_trend_profiles(load_real_trend_profiles())

    rank_lookup = load_trend_overall_rank()  # 🆕 (2026-09-15) อันดับรวมเทรนด์จาก ⑥ ถ้ามี
    top_rank_lookup = load_trend_top_rank()  # 🆕 (2026-09-16) อันดับภายใน Top N (1..N) จาก ⑪ - ใช้แสดงผล

    print(f"\nกำลังคำนวณ cosine similarity เต็มตลาด ({len(df)} SKU) ต่อเทรนด์ (deterministic, ไม่ยิง API)... "
          f"แล้วให้เหตุผลรายชิ้น (LLM) กับสินค้า {brand} สูงสุด {BRAND_TOP_K} อันดับแรกของแต่ละเทรนด์ "
          f"(~{len(trend_vectors) * min(BRAND_TOP_K, max(len(brand_idx), 1))} เรียก)...")
    tier_recs, tier_key, _ = market_tiers(df)     # 🆕 (2026-10-12) ช่วงราคาตาม config/market_tiers.json
    market_rows = build_market_rows(df, all_idx, tier_recs)  # price_tiers ต่อเทรนด์ (2026-10-05)
    brand_rows = brand_rows_by_name(df, brand)    # category_fit: เหตุผลของสินค้าที่ดีที่สุดต่อหมวด (2026-10-07)

    grading_cfg = fit_grading()
    sims_by_key = {key: trend_similarities(all_vecs, tvec) for key, tvec in trend_vectors.items()}
    decisions = decide_main_categories(sims_by_key, market_rows, trend_profile_by_key)   # 🆕 (2026-10-08) หมวดหลักที่ LLM เลือก
    # 🆕 (2026-10-19) เหตุผลที่เคยเขียนไว้ในไฟล์เดิมของแบรนด์นี้ (สำรองไฟล์เดิมก่อนรันซ้ำ) - ใช้ซ้ำ เรียก LLM เฉพาะเทรนด์/สินค้าใหม่
    previous_reasons = load_previous_reasons(OUTPUTS / f"phase3_brand_coverage_{brand.replace(' ', '_')}.json")
    n_reused = 0

    coverage_report = {}
    for n_done, (key, tvec) in enumerate(trend_vectors.items(), start=1):
        sims = sims_by_key[key]
        order = np.argsort(-sims)  # มากไปน้อย
        n_total = len(all_idx)
        rank_of_pos = np.empty(n_total, dtype=int)
        rank_of_pos[order] = np.arange(n_total)  # rank_of_pos[pos] = 0 คือดีที่สุดในตลาด

        brand_scores = [(idx, float(sims[pos_of_idx[idx]])) for idx in brand_idx if idx in pos_of_idx]
        brand_scores.sort(key=lambda x: x[1], reverse=True)

        if brand_scores:
            best_idx, best_score = brand_scores[0]
            best_rank = int(rank_of_pos[pos_of_idx[best_idx]]) + 1  # 1 = ดีที่สุดในตลาดทั้งหมด
            best_percentile = round((n_total - (best_rank - 1)) / n_total * 100)
            # 🆕 percentile หยาบเกินไปตอนอยู่ใน top 1% ของตลาดที่มี 10,622 ชิ้น (rank 1 กับ rank 100
            # ปัดเป็น "100th percentile" เหมือนกันหมด - เข้าใจผิดว่า "ดีที่สุด" ทั้งที่อาจจะแค่ "ติดกลุ่มบนๆ")
            # ให้ rank ตัวเลขจริงคู่กันเสมอ ไม่ใช้ percentile อย่างเดียวตัดสิน
        else:
            best_idx, best_score, best_percentile, best_rank = None, None, None, None

        market_best_score = float(sims[order[0]])
        market_best_row = df.loc[all_idx[order[0]]]
        # 🆕 (2026-10-05) top 5 ของตลาดในเทรนด์นี้ (ชีต "รายเทรนด์" ของ Excel ใช้) - หมวด = L2 ของ Euromonitor
        market_top = []
        for pos in order[:5]:
            mrow = df.loc[all_idx[pos]]
            url = mrow.get("product_url")
            market_top.append({"rank_in_market": len(market_top) + 1, "product_name": mrow["product_name"],
                               "brand": mrow["brand"], "category": mrow.get("EM_L2") or "",
                               "similarity": round(float(sims[pos]), 4), "sale_price_thb": _row_price(mrow),
                               "product_url": url if isinstance(url, str) else None})

        tier = ("ตามทัน/มีของเข้าเทรนด์" if best_percentile is not None and best_percentile >= TOP_MATCH_TIER
               else "Gap - ยังไม่มีของเข้าเทรนด์นี้" if best_percentile is None or best_percentile <= GAP_TIER
               else "กลางๆ - มีของบ้างแต่ไม่โดดเด่น")

        # 🆕 (2026-09-15) เจ้าของงานขอเพิ่มเหตุผล LLM แบบเดียวกับ ⑫'s generate_match_reason() (Typhoon,
        # ไม่ตัดสิน verdict - แค่อธิบาย) เข้า ⑬ ด้วย - เรียกแค่ต่อเทรนด์ (สินค้าที่ดีที่สุดของแบรนด์ 1
        # ชิ้น) ไม่ใช่ top-5 แบบ ⑫ เพราะ ⑬ สนใจแค่ตัวที่ดีที่สุดของแบรนด์นี้ต่อเทรนด์อยู่แล้ว
        # 🆕 (2026-09-16) เก็บ top 5 สินค้าของแบรนด์ต่อเทรนด์ พร้อมเหตุผล**รายชิ้น** ตามที่เจ้าของงานขอ
        # (เดิมเก็บแค่ชิ้นที่ดีที่สุด 1 ชิ้น + เหตุผล 1 อัน) - similarity ยังเป็นตัวจัดอันดับเหมือนเดิม
        # LLM แค่อธิบายรายชิ้น ไม่ได้ตัดสิน (หลักการเดียวกับ ⑫'s generate_match_reason)
        brand_top = []
        reuse = previous_reasons.get(key, {})
        for rank_in_brand, (idx, score) in enumerate(brand_scores[:BRAND_TOP_K], start=1):
            row = df.loc[idx]
            rank_vs_market = int(rank_of_pos[pos_of_idx[idx]]) + 1
            sold = row.get("sold_count")
            price_val = _row_price(row)
            category = next((str(c) for c in (row.get("EM_L2"), row.get("Category"), row.get("category"))
                             if c is not None and not pd.isna(c) and str(c).strip()), "")
            brand_top.append({
                "rank_in_brand": rank_in_brand,
                "product_name": row["product_name"],
                "category": category,
                "similarity": round(float(score), 4),
                "rank_vs_market": rank_vs_market,
                "percentile_vs_market": round((n_total - (rank_vs_market - 1)) / n_total * 100),
                "sale_price_thb": price_val,
                "sold_count": None if pd.isna(sold) else float(sold),
                "product_url": row.get("product_url") if isinstance(row.get("product_url"), str) else None,
                "match_reason": reuse.get(row["product_name"]) or generate_match_reason(trend_profile_by_key[key], row),
            })
            n_reused += row["product_name"] in reuse
        # เหตุผลระดับเทรนด์ = ของสินค้าอันดับ 1 (ไม่ต้องยิง LLM ซ้ำ) - คีย์เดิมที่ Master Report ใช้อยู่
        match_reason = brand_top[0]["match_reason"] if brand_top else ""
        fit = compute_category_fit(sims, market_rows, brand, decisions[key], tier_key)
        n_fit_llm = attach_fit_reasons(fit, brand_top, brand_rows, trend_profile_by_key[key], known_reasons=reuse, grading=grading_cfg)
        print(f"  [{n_done}/{len(trend_vectors)}] {trend_names[key]} - อธิบาย {len(brand_top)} ชิ้น"
              + (f" (ใช้เหตุผลเดิม {sum(1 for m in brand_top if m['product_name'] in reuse)})" if reuse else "")
              + (f" + สินค้าที่ดีที่สุดต่อหมวด {n_fit_llm} ชิ้น" if n_fit_llm else ""))

        coverage_report[key] = {
            "trend_name": trend_names[key],
            "stream": trend_streams[key],
            # 🆕 (2026-09-15) อันดับรวมของเทรนด์นี้ข้ามทุกสาย (จาก ⑥) - None ถ้า ⑥ ยังไม่เคยรัน หรือ
            # รันกับข้อมูลคนละชุด (ชื่อเทรนด์ไม่ตรงกัน) ดู load_trend_overall_rank() docstring
            "trend_overall_rank": rank_lookup.get((trend_streams[key], trend_names[key])),
            # 🆕 (2026-09-16) อันดับภายในชุด Top N (1..N) ที่ใช้แสดงผล - None ถ้าผล ⑪ เป็นรอบเก่า ดู load_trend_top_rank()
            "trend_top_rank": top_rank_lookup.get((trend_streams[key], trend_names[key])),
            # 🆕 (2026-09-16) top 5 สินค้าของแบรนด์ในเทรนด์นี้ พร้อมเหตุผลรายชิ้น (ชีต "Top 5 ต่อเทรนด์"
            # ใน Excel ใช้ตรงนี้) - คีย์ brand_best_* ด้านล่างคือชิ้นอันดับ 1 ของลิสต์นี้ เก็บไว้เหมือนเดิม
            # เพราะ Master Report/ผลรอบเก่าอ้างถึงอยู่
            "brand_top_matches": brand_top,
            "brand_best_product": (df.loc[best_idx, "product_name"] if best_idx is not None else None),
            "brand_best_score": round(best_score, 4) if best_score is not None else None,
            "match_reason": match_reason,
            "brand_best_rank_vs_market": best_rank,  # 1 = อันดับ 1 ของทั้งตลาด (ตัวเลขจริง แม่นกว่า percentile)
            "brand_best_percentile_vs_market": best_percentile,
            "brand_n_skus_considered": len(brand_scores),
            "tier": tier,
            "market_best_product": f"{market_best_row['brand']} - {market_best_row['product_name']}",
            "market_best_score": round(market_best_score, 4),
            "market_best_url": (market_best_row.get("product_url")
                                if isinstance(market_best_row.get("product_url"), str) else None),
            "market_top_matches": market_top,
            # 🆕 (2026-10-05) เทรนด์ -> หมวด L2 หลัก -> ระดับราคาของแบรนด์ (สำหรับรายงาน ⑱ ดู price_tiers.py)
            "price_tiers": compute_price_tiers(sims, market_rows, brand),
            # 🆕 (2026-10-07) เทรนด์ -> หมวดหลัก (LLM เลือก 2026-10-08) -> ช่วงราคาตลาด -> สินค้า (เกรดใน ⑰/⑱ ดู category_fit.py)
            "category_fit": fit,
        }

    out_path = OUTPUTS / f"phase3_brand_coverage_{brand.replace(' ', '_')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "_note": "⑬ โหมด 1 - แบรนด์บน Konvy vs Top N เทรนด์ของรอบนี้ (embedding เดิมจาก ⑫ ทั้งหมด ไม่ยิง"
                    " API สินค้าเพิ่ม)",
            "brand": brand, "n_skus": len(brand_idx), "coverage": coverage_report,
        }, f, ensure_ascii=False, indent=2)

    # 🆕 (2026-09-16) ไฟล์ Excel คู่กับ JSON (ชื่อเดียวกัน คนละนามสกุล) - ข้อมูลชุดเดียวกัน ดู save_coverage_excel()
    xlsx_path = out_path.with_suffix(".xlsx")
    no_close = load_no_close_of_run()   # 🆕 (2026-10-28) เทรนด์ที่ไม่ให้เกรด (ไม่มีสินค้าที่ใกล้พอ) - ดู common/match_quality.py
    if no_close:
        print(f"  ℹ️ เทรนด์ที่ไม่ให้เกรด (ไม่มีสินค้าที่ใกล้พอ): {', '.join(t for _, t in no_close)}")
    save_coverage_excel(xlsx_path, brand, len(brand_idx), len(all_idx), coverage_report, urls=product_url_index(df),
                        l2=product_l2_index(df), no_close=no_close)

    report_path = OUTPUTS / "phase4_master_trend_report.md"
    if append_brand_section_to_report(report_path, brand, len(brand_idx), len(all_idx), coverage_report, no_close):
        print(f"✅ ต่อท้ายอันดับ {brand} เข้า {report_path.name} แล้ว")
    else:
        print(f"  ⏭️  ไม่เจอ {report_path.name} ในรอบนี้ - ข้ามการต่อท้ายรายงาน (ไฟล์ ⑬ แยกยังเซฟไว้ปกติ)")

    print("\n" + "=" * 70)
    print(f"ผล Brand Coverage: {brand} ({len(brand_idx)} SKU) เทียบ {len(coverage_report)} เทรนด์")
    print("=" * 70)
    for key, r in sorted(coverage_report.items(), key=lambda kv: kv[1]["brand_best_score"] or -1, reverse=True):
        rank_str = f" (อันดับเทรนด์ #{display_trend_rank(r)})" if display_trend_rank(r) is not None else ""
        print(f"\n🎯 [{r['stream']}] {r['trend_name']}{rank_str}  -> {r['tier']}")
        if r["brand_best_product"]:
            print(f"   {brand} ดีที่สุด: {r['brand_best_product']} (score={r['brand_best_score']}, "
                  f"อันดับ {r['brand_best_rank_vs_market']}/{len(all_idx)} ของทั้งตลาด "
                  f"~{r['brand_best_percentile_vs_market']}th percentile)")
            if r.get("match_reason"):
                print(f"   เหตุผล: {r['match_reason']}")
        else:
            print(f"   {brand}: ไม่มี SKU ไหนใกล้เคียงเลย")
        print(f"   ตลาดดีที่สุด (ทุกแบรนด์): {r['market_best_product']} (score={r['market_best_score']})")

    print(f"\n✅ Saved -> {out_path}")
    print(f"✅ Saved (Excel) -> {xlsx_path}")
