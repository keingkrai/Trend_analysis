# -*- coding: utf-8 -*-
"""
Phase 3 — ⑬ จับคู่สินค้า (โหมด 1: แบรนด์ที่ขายอยู่บน Watsons จริงอยู่แล้ว) (2026-09-11)
ดู Detail/05 งานที่ยังไม่ได้ทำ/Workflow v2 — แยกสายแล้วรวม.md ส่วน "⑬ จับคู่สินค้า EXFAC"

เจ้าของงานเลือก **โหมด 1** (จาก 2 โหมดที่เสนอ): "แบรนด์ไหนก็ได้ที่ขายอยู่บน Watsons แล้ว" - ผู้ใช้พิมพ์
ชื่อแบรนด์ตอนรัน แทนที่จะแก้ค่าคงที่ในไฟล์แบบ `analysis/run_exfac_trend_match.py` เดิม (ที่ต้อง
COMPANY_NAME/PRODUCT_CATALOG_PATH ก่อนรันทีละบริษัท) — **ไม่ต้องอัปโหลดไฟล์ ไม่ต้อง scrape ใหม่เลย**
เพราะ ⑫ มีข้อมูลสินค้าจริงครบ 10,622 SKU จาก 695 แบรนด์อยู่แล้ว แค่ filter ตาม brand ที่ผู้ใช้เลือก

**ทุก embedding ที่ใช้เป็นของที่คำนวณไว้แล้วจาก ⑫ (`match_products.py`) - ไม่ยิง NVIDIA API
เพิ่มเลยสำหรับฝั่งสินค้า** (โหลด checkpoint .pkl ที่ embed ครบ 10,622 ชิ้นไว้แล้ว) ยิงแค่ 15 ครั้งสำหรับ
เทรนด์ (เหมือนเดิม) แล้วคำนวณ cosine similarity **ใหม่ทั้งหมด** (deterministic, ไม่มีค่า API เลย -
เป็นแค่ numpy dot product ระหว่าง embedding ที่มีอยู่แล้ว) เพื่อได้ full distribution ทั้ง 10,622 ชิ้น
ต่อเทรนด์ (ไม่ใช่แค่ top-15 ที่ ⑫ เซฟไว้) - ใช้หา percentile ที่แบรนด์ที่เลือกอยู่ตรงไหนของทั้งตลาด

โมเดล/มิติต้องตรงกับที่ embed ตอน ⑫ เป๊ะ (nvidia/llama-nemotron-embed-vl-1b-v2, 2048 มิติ, asymmetric
query/passage) - ใช้ไฟล์เดียวกัน (`match_products.py`) import ฟังก์ชันมาโดยตรง ไม่เขียนซ้ำ

🆕 (2026-09-16) ออกผล 2 ไฟล์ต่อแบรนด์ตามที่เจ้าของงานขอ: JSON เดิม + **Excel**
(`phase3_brand_coverage_<แบรนด์>.xlsx` ชีต "สรุป" + "รายเทรนด์") - ข้อมูลชุดเดียวกันเป๊ะ ไม่ได้คำนวณเพิ่ม
ดู `save_coverage_excel()`

🆕 (2026-09-26) แบรนด์ที่ไม่มีบน Watsons: `--products <csv> --brand <ชื่อ>` ใช้สินค้าจากไฟล์แทน (เช่นสินค้าที่
Health Check ของ GI_CH scrape จาก Shopee/Lazada/Konvy) - embed ด้วยข้อความสูตรเดียวกับ ⑫ (`build_product_text`)
cache แยกไฟล์ (`EXTERNAL_CHECKPOINT_PATH`) แล้วจัดอันดับเทียบตลาด Watsons ชุดเดิม: อันดับ = อันดับที่สินค้าชิ้นนั้นจะได้
ถ้าแทรกเข้าไปในตลาด 10,622 SKU (`rank_if_inserted`) ความหมายเดียวกับโหมด Watsons - การคำนวณต่อเทรนด์อยู่ใน
`compute_coverage()` ใช้ร่วมกันทั้ง 2 โหมด

Usage:
    TREND_RUN_ID=<รอบ> TREND_TOPIC=Mizumi python tool/step3_products/brand_coverage.py      # แบบเดิม (main.py)
    TREND_RUN_ID=<รอบ> python tool/step3_products/brand_coverage.py --brand Mizumi
    TREND_RUN_ID=<รอบ> python tool/step3_products/brand_coverage.py --brand "My Brand" --products products.csv
"""
import argparse
import difflib
import hashlib
import json
import pickle
import statistics
import sys
from pathlib import Path

import numpy as np
import pandas as pd

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import CHECKPOINTS, OUTPUTS, TOOL_DIR, prompt_run_config  # noqa: E402

from match_products import (  # noqa: E402
    generate_match_reason, get_embedding, load_checkpoint, load_real_trend_profiles,
)
from match_supply import build_trend_matchable_text, cosine_similarity  # noqa: E402
from validate_at_scale import build_product_text  # noqa: E402

# 🆕 (2026-09-26) เวกเตอร์ของสินค้านอกแคตตาล็อก Watsons (--products) - คนละไฟล์กับ cache ของ ⑫ ที่ ⑫ เขียนทับทั้งไฟล์
# ระหว่างรัน (ถ้าใช้ไฟล์เดียวกัน 2 โปรเซสจะเขียนทับกันหาย)
EXTERNAL_CHECKPOINT_PATH = CHECKPOINTS / "external_product_embeddings_nvidia.pkl"
# คอลัมน์ของไฟล์ --products: บังคับแค่ product_name ที่เหลือใส่เท่าที่มี (ข้อความ embed ใช้สูตรเดียวกับ ⑫)
EXTERNAL_COLUMNS = ("product_name", "brand", "Key_Benefits", "Primary_Use_Case", "Product_Insights", "ingredients",
                    "Category", "Sub_category", "sale_price_thb", "sold_count", "image_url", "product_url", "platform")

TOP_MATCH_TIER = 67  # percentile >= นี้ = แบรนด์มีของเข้าเทรนด์จริง (เทียบชั้นเดียวกับ match_supply.py)
GAP_TIER = 33        # percentile <= นี้ = ยังไม่มีของเข้าเทรนด์นี้เลย (เทียบกับตลาดทั้งหมด)
# 🆕 (2026-09-16) จำนวนสินค้าของแบรนด์ที่เก็บ+ขอเหตุผลต่อเทรนด์ (เดิมเก็บแค่ชิ้นที่ดีที่สุดชิ้นเดียว) -
# ตรงกับ MATCH_REASON_TOP_K ของ ⑫ ค่าใช้จ่าย LLM = จำนวนเทรนด์ x ค่านี้ ต่อการค้น 1 แบรนด์
BRAND_TOP_K = 5


def save_coverage_excel(path, brand, n_brand_skus, n_market_skus, coverage_report):
    """🆕 (2026-09-16) เซฟผล ⑬ เป็น Excel คู่กับ JSON ตามที่เจ้าของงานขอ - **ข้อมูลชุดเดียวกันเป๊ะกับ JSON**
    ไม่ได้คำนวณอะไรเพิ่มหรือตัดอะไรทิ้ง แค่จัดเป็นตารางให้เปิดอ่าน/ส่งต่อได้โดยไม่ต้องเปิด JSON

    3 ชีต: "สรุป" (แบรนด์/ขนาดตลาด/จำนวนเทรนด์แต่ละสถานะ), **"Top 5 ต่อเทรนด์"** (1 แถว = 1 สินค้า -
    สินค้าของแบรนด์ 5 อันดับแรกในแต่ละเทรนด์ พร้อมเหตุผลรายชิ้น 🆕 2026-09-16 ตามที่เจ้าของงานขอ) และ
    "รายเทรนด์" (1 แถว = 1 เทรนด์ ภาพรวมเรียงตามคะแนนมากไปน้อย เหมือนลำดับที่พิมพ์ออกหน้าจอ)

    รับผลรอบเก่าที่ยังไม่มี `brand_top_matches` ได้ (ตกลงมาใช้ชิ้นที่ดีที่สุดชิ้นเดียวแทน ไม่ error)"""
    from openpyxl.styles import Alignment
    from openpyxl.utils import get_column_letter

    by_score = sorted(coverage_report.values(), key=lambda v: v["brand_best_score"] or -1, reverse=True)

    top_rows = []
    for r in by_score:
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
        rows.append({
            "อันดับเทรนด์": display_trend_rank(r),
            "สาย": r["stream"],
            "เทรนด์": r["trend_name"],
            "สถานะ": r["tier"],
            f"สินค้า {brand} ที่ใกล้เทรนด์สุด": r["brand_best_product"] or "— ไม่มี SKU ไหนใกล้เคียงเลย",
            "คะแนนความใกล้เคียง": r["brand_best_score"],
            "อันดับในตลาด": f"{rank_vs_market}/{n_market_skus}" if rank_vs_market else None,
            "เปอร์เซ็นไทล์": r["brand_best_percentile_vs_market"],
            "SKU ที่เทียบ": r["brand_n_skus_considered"],
            "เหตุผล": r.get("match_reason") or "",
            "สินค้าที่ดีที่สุดในตลาด (ทุกแบรนด์)": r["market_best_product"],
            "คะแนนของตลาด": r["market_best_score"],
        })
    df_trends = pd.DataFrame(rows)

    summary = [("แบรนด์", brand),
               ("จำนวน SKU ของแบรนด์นี้", n_brand_skus),
               ("ขนาดตลาดที่เทียบ (SKU)", n_market_skus),
               ("จำนวนเทรนด์ที่เทียบ", len(df_trends)),
               (f"สินค้าที่แสดงต่อเทรนด์ (สูงสุด {BRAND_TOP_K} อันดับ)", len(df_top))]
    if not df_trends.empty:
        summary += [(f"เทรนด์ที่ '{tier}'", int(n)) for tier, n in df_trends["สถานะ"].value_counts().items()]
    df_summary = pd.DataFrame(summary, columns=["หัวข้อ", "ค่า"])

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet, frame in (("สรุป", df_summary), ("Top 5 ต่อเทรนด์", df_top), ("รายเทรนด์", df_trends)):
            frame.to_excel(writer, sheet_name=sheet, index=False)
            ws = writer.sheets[sheet]
            ws.freeze_panes = "A2"
            for i, col in enumerate(frame.columns, start=1):
                longest = max([len(str(col))] + [len(str(v)) for v in frame[col].tolist()] or [0])
                ws.column_dimensions[get_column_letter(i)].width = min(max(12, longest + 2), 55)
                if col == "เหตุผล":  # ข้อความยาว - ตัดบรรทัดในช่องแทนการลากยาวออกนอกจอ
                    for cell in ws[get_column_letter(i)][1:]:
                        cell.alignment = Alignment(wrap_text=True, vertical="top")


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


def build_brand_section_markdown(brand, n_skus, n_market, coverage_report):
    """🆕 (2026-09-14) สร้างข้อความ markdown ของอันดับสินค้าแบรนด์ต่อเทรนด์ - แยกออกมาจาก __main__ ให้
    เทสได้ตรงๆ โดยไม่ต้องรัน embedding/similarity ใหม่ (ของแพง/ช้า) ทุกครั้งที่จะเทส

    🆕 (2026-09-16) ออก 2 ตาราง: ภาพรวม 1 แถว/เทรนด์ (ของเดิม) + "Top {BRAND_TOP_K} สินค้าในแต่ละเทรนด์"
    พร้อมเหตุผลรายชิ้น ตามที่เจ้าของงานขอ - ตารางที่ 2 จะไม่ขึ้นเลยถ้าเป็นผลรอบเก่าที่ไม่มี
    `brand_top_matches` (ไม่ error)"""
    lines = [f"\n---\n\n## Brand Coverage — {brand} ({n_skus} SKU)",
             f"> เพิ่มโดย ⑬ (`brand_coverage.py`, โหมด 1) - อันดับสินค้า {brand} เทียบกับสินค้า"
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
        lines.append(f"| {r['trend_name']} | {trend_rank_str} | {r['stream']} | {product} | {rank} | "
                      f"{pct} | {r['tier']} | {reason} |")

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


def append_brand_section_to_report(report_path, brand, n_skus, n_market, coverage_report):
    """🆕 (2026-09-14) เจ้าของงานขอ: อันดับสินค้าแบรนด์ต่อเทรนด์ต้องไปโผล่ใน Master Report ด้วย ไม่ใช่แค่
    อยู่ในไฟล์ ⑬ แยกที่ไม่มีใครอ่านต่อ - ⑬ รัน**หลัง** ⑭-⑮ (stepic_report.py) เสมอตามลำดับใน main.py
    จึงต่อท้าย (append) เข้าไฟล์รายงานที่มีอยู่แล้วแทนที่จะย้อนไปแก้ trend_final_v2.py (รายงานเขียนเสร็จ
    ไปแล้วตอนนี้ถึงจะมาถึงจุดนี้) - ถ้ารันหลายแบรนด์ต่อกันในรอบเดียว (main.py's loop) แต่ละแบรนด์จะได้
    section แยกของตัวเอง ต่อท้ายไปเรื่อยๆ ตามลำดับที่พิมพ์

    คืน True ถ้าต่อท้ายสำเร็จ, False ถ้าไม่เจอไฟล์รายงาน (ไม่ error - ไฟล์ ⑬ แยกยังเซฟไว้ปกติเสมอ)"""
    if not report_path.exists():
        return False
    section = build_brand_section_markdown(brand, n_skus, n_market, coverage_report)
    with open(report_path, "a", encoding="utf-8") as f:
        f.write(section)
    return True


def embed_trend_profiles(trend_profiles):
    """profile ของ ⑪ -> เวกเตอร์เทรนด์ (input_type=query) คืน (vectors, names, streams, profile_by_key) ใช้ key
    "stream::trend" กันชื่อเทรนด์ชนกันข้ามสาย"""
    trend_vectors, trend_names, trend_streams, trend_profile_by_key = {}, {}, {}, {}
    for profile in trend_profiles:
        stream = profile.get("stream", "?")
        key = f"{stream}::{profile['trend']}"
        text = build_trend_matchable_text(profile)
        # 🆕 (2026-09-16) ข้ามเทรนด์ที่ ⑪ ตอบ "ข้อมูลไม่พอ" ครบทุกฟิลด์ (ข้อความ embed ว่าง -> embedding API
        # ตอบ 400) เหมือนที่ทำใน match_products.py (⑫) - ไม่งั้น ⑬ จะพังด้วยสาเหตุเดียวกัน
        if not text.strip():
            print(f"    ⏭️ ข้าม '{profile['trend']}' [{stream}] - ⑪ ตอบ 'ข้อมูลไม่พอ' ทุกฟิลด์ที่ใช้จับคู่")
            continue
        trend_vectors[key] = get_embedding(text, "query")
        trend_names[key] = profile["trend"]
        trend_streams[key] = stream
        trend_profile_by_key[key] = profile  # 🆕 (2026-09-15) เก็บไว้ป้อน generate_match_reason()
    return trend_vectors, trend_names, trend_streams, trend_profile_by_key


def rank_if_inserted(market_sims_ascending, score):
    """อันดับของสินค้านอกแคตตาล็อกถ้าแทรกเข้าไปในตลาด (1 = ใกล้เทรนด์ที่สุด) = จำนวนสินค้าในตลาดที่คะแนนสูงกว่า + 1"""
    n = len(market_sims_ascending)
    return int(n - np.searchsorted(market_sims_ascending, score, side="right")) + 1


def _price_value(price):
    """sale_price_thb เป็น string มี comma คั่นหลักพัน (เช่น "1,790.00") - เหมือน ⑫"""
    try:
        return None if price is None or pd.isna(price) else float(str(price).replace(",", ""))
    except (ValueError, TypeError):
        return None


def compute_coverage(market_df, market_idx, market_vecs, brand_items, trends, rank_lookup, top_rank_lookup,
                     reason_fn=generate_match_reason):
    """⑬ ต่อเทรนด์: คะแนนและอันดับของสินค้าแบรนด์เทียบทั้งตลาด (ย้ายมาจาก __main__ เดิม - ผลของโหมด Watsons เหมือนเดิม)

    market_df/market_idx/market_vecs: ตลาด Watsons (แถว market_idx[i] มีเวกเตอร์ market_vecs[i])
    brand_items: [{"row": แถวสินค้า, "pos": ตำแหน่งในตลาด หรือ None, "vec": เวกเตอร์ (เมื่อ pos เป็น None),
                   "extra": ฟิลด์ที่ต่อท้ายผลของสินค้าชิ้นนั้น (เช่นลิงก์/รูปของสินค้านอกแคตตาล็อก)}] เรียงตามลำดับเดิม
    trends: ผลของ embed_trend_profiles() / reason_fn(profile, row) -> เหตุผลจาก LLM (เทสส่งตัวปลอมได้)"""
    trend_vectors, trend_names, trend_streams, trend_profile_by_key = trends
    n_total = len(market_idx)
    coverage_report = {}
    for n_done, (key, tvec) in enumerate(trend_vectors.items(), start=1):
        sims = market_vecs @ tvec / (np.linalg.norm(market_vecs, axis=1) * np.linalg.norm(tvec) + 1e-12)
        order = np.argsort(-sims)  # มากไปน้อย
        rank_of_pos = np.empty(n_total, dtype=int)
        rank_of_pos[order] = np.arange(n_total)  # rank_of_pos[pos] = 0 คือดีที่สุดในตลาด
        sims_ascending = None

        scored = []  # (item, similarity, อันดับในตลาด 1 = ดีที่สุด)
        for item in brand_items:
            if item.get("pos") is not None:
                scored.append((item, float(sims[item["pos"]]), int(rank_of_pos[item["pos"]]) + 1))
            else:
                vec = item["vec"]
                score = float(vec @ tvec / (np.linalg.norm(vec) * np.linalg.norm(tvec) + 1e-12))
                if sims_ascending is None:
                    sims_ascending = np.sort(sims)
                scored.append((item, score, rank_if_inserted(sims_ascending, score)))
        scored.sort(key=lambda x: x[1], reverse=True)

        if scored:
            best_item, best_score, best_rank = scored[0]  # best_rank: 1 = ดีที่สุดในตลาดทั้งหมด
            best_percentile = round((n_total - (best_rank - 1)) / n_total * 100)
            # 🆕 percentile หยาบเกินไปตอนอยู่ใน top 1% ของตลาดที่มี 10,622 ชิ้น (rank 1 กับ rank 100
            # ปัดเป็น "100th percentile" เหมือนกันหมด - เข้าใจผิดว่า "ดีที่สุด" ทั้งที่อาจจะแค่ "ติดกลุ่มบนๆ")
            # ให้ rank ตัวเลขจริงคู่กันเสมอ ไม่ใช้ percentile อย่างเดียวตัดสิน
        else:
            best_item, best_score, best_percentile, best_rank = None, None, None, None

        market_best_score = float(sims[order[0]])
        market_best_row = market_df.loc[market_idx[order[0]]]

        tier = ("ตามทัน/มีของเข้าเทรนด์" if best_percentile is not None and best_percentile >= TOP_MATCH_TIER
               else "Gap - ยังไม่มีของเข้าเทรนด์นี้" if best_percentile is None or best_percentile <= GAP_TIER
               else "กลางๆ - มีของบ้างแต่ไม่โดดเด่น")

        # 🆕 (2026-09-15) เหตุผล LLM แบบเดียวกับ ⑫'s generate_match_reason() (ไม่ตัดสิน verdict - แค่อธิบาย)
        # 🆕 (2026-09-16) เก็บ top 5 สินค้าของแบรนด์ต่อเทรนด์ พร้อมเหตุผล**รายชิ้น** ตามที่เจ้าของงานขอ
        # (เดิมเก็บแค่ชิ้นที่ดีที่สุด 1 ชิ้น + เหตุผล 1 อัน) - similarity ยังเป็นตัวจัดอันดับเหมือนเดิม
        brand_top = []
        for rank_in_brand, (item, score, rank_vs_market) in enumerate(scored[:BRAND_TOP_K], start=1):
            row = item["row"]
            sold = row.get("sold_count")
            category = next((str(c) for c in (row.get("Category"), row.get("category"))
                             if c is not None and not pd.isna(c) and str(c).strip()), "")
            brand_top.append({
                "rank_in_brand": rank_in_brand,
                "product_name": row["product_name"],
                "category": category,
                "similarity": round(float(score), 4),
                "rank_vs_market": rank_vs_market,
                "percentile_vs_market": round((n_total - (rank_vs_market - 1)) / n_total * 100),
                "sale_price_thb": _price_value(row.get("sale_price_thb")),
                "sold_count": None if sold is None or pd.isna(sold) else float(sold),
                "match_reason": reason_fn(trend_profile_by_key[key], row),
                **(item.get("extra") or {}),
            })
        # เหตุผลระดับเทรนด์ = ของสินค้าอันดับ 1 (ไม่ต้องยิง LLM ซ้ำ) - คีย์เดิมที่ Master Report ใช้อยู่
        match_reason = brand_top[0]["match_reason"] if brand_top else ""
        print(f"  [{n_done}/{len(trend_vectors)}] {trend_names[key]} - อธิบาย {len(brand_top)} ชิ้น")

        coverage_report[key] = {
            "trend_name": trend_names[key],
            "stream": trend_streams[key],
            # 🆕 (2026-09-15) อันดับรวมของเทรนด์นี้ข้ามทุกสาย (จาก ⑥) - None ถ้า ⑥ ยังไม่เคยรัน หรือ
            # รันกับข้อมูลคนละชุด (ชื่อเทรนด์ไม่ตรงกัน) ดู load_trend_overall_rank() docstring
            "trend_overall_rank": rank_lookup.get((trend_streams[key], trend_names[key])),
            # 🆕 (2026-09-16) อันดับภายในชุด Top N (1..N) ที่ใช้แสดงผล - None ถ้าผล ⑪ เป็นรอบเก่า ดู load_trend_top_rank()
            "trend_top_rank": top_rank_lookup.get((trend_streams[key], trend_names[key])),
            # 🆕 (2026-09-16) top 5 สินค้าของแบรนด์ในเทรนด์นี้ พร้อมเหตุผลรายชิ้น - คีย์ brand_best_* ด้านล่างคือ
            # ชิ้นอันดับ 1 ของลิสต์นี้ เก็บไว้เหมือนเดิมเพราะ Master Report/ผลรอบเก่าอ้างถึงอยู่
            "brand_top_matches": brand_top,
            "brand_best_product": best_item["row"]["product_name"] if best_item is not None else None,
            "brand_best_score": round(best_score, 4) if best_score is not None else None,
            "match_reason": match_reason,
            "brand_best_rank_vs_market": best_rank,  # 1 = อันดับ 1 ของทั้งตลาด (ตัวเลขจริง แม่นกว่า percentile)
            "brand_best_percentile_vs_market": best_percentile,
            "brand_n_skus_considered": len(scored),
            "tier": tier,
            "market_best_product": f"{market_best_row['brand']} - {market_best_row['product_name']}",
            "market_best_score": round(market_best_score, 4),
        }
    return coverage_report


def load_external_products(csv_path):
    """ไฟล์ --products -> DataFrame: ต้องมี product_name ตัดแถวชื่อว่าง และตัดชื่อซ้ำ (สินค้าเดียวกันขายหลายแพลตฟอร์ม)
    โดยเก็บแถวที่มีข้อความให้ embed มากที่สุด"""
    df = pd.read_csv(csv_path, encoding="utf-8-sig", low_memory=False)
    if "product_name" not in df.columns:
        raise SystemExit(f"❌ {csv_path} ไม่มีคอลัมน์ product_name")
    df = df[df["product_name"].notna() & (df["product_name"].astype(str).str.strip() != "")].copy()
    df["_text_len"] = [len(build_product_text(row)) for _, row in df.iterrows()]
    df = (df.sort_values("_text_len", ascending=False, kind="stable")
            .drop_duplicates(subset=["product_name"], keep="first")
            .sort_index()
            .drop(columns="_text_len"))
    return df.reset_index(drop=True)


def _save_external_cache(cache):
    EXTERNAL_CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = EXTERNAL_CHECKPOINT_PATH.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(cache, f)
    tmp.replace(EXTERNAL_CHECKPOINT_PATH)


def embed_external_products(df, embed=None):
    """สินค้าจากไฟล์ -> {แถว: เวกเตอร์} (input_type=passage) cache ด้วย hash ของข้อความที่ embed จริง แถวที่ไม่มีข้อความ
    ให้ embed ได้ None - embed(text) ใช้แทน get_embedding ได้ (เทส)"""
    embed = embed or (lambda text: get_embedding(text, "passage"))
    cache = {}
    if EXTERNAL_CHECKPOINT_PATH.exists():
        with open(EXTERNAL_CHECKPOINT_PATH, "rb") as f:
            cache = pickle.load(f)
    vectors, new = {}, 0
    for idx, row in df.iterrows():
        text = build_product_text(row)
        if not text.strip():
            vectors[idx] = None
            continue
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if key not in cache:
            cache[key] = embed(text)
            new += 1
            if new % 100 == 0:
                _save_external_cache(cache)
        vectors[idx] = cache[key]
    if new:
        _save_external_cache(cache)
    n_ready = sum(v is not None for v in vectors.values())
    print(f"  embed สินค้าจากไฟล์: ใหม่ {new} ชิ้น, จาก cache {n_ready - new} ชิ้น, ไม่มีข้อความ {len(vectors) - n_ready} ชิ้น")
    return vectors


def external_portfolio(df):
    """ภาพรวมสินค้าจากไฟล์ รูปเดียวกับ step5_pdf/brand_data.portfolio_stats() (ใช้แทนเมื่อแบรนด์ไม่มีบน Watsons)"""
    prices = [p for p in (_price_value(v) for v in df["sale_price_thb"]) if p] if "sale_price_thb" in df.columns else []
    subs = df["Sub_category"].dropna().value_counts().head(4) if "Sub_category" in df.columns else pd.Series(dtype=int)
    return {
        "n_skus": int(len(df)),
        "top_subcategories": [{"name": str(k), "n": int(v)} for k, v in subs.items()],
        "price_min": min(prices) if prices else None,
        "price_median": statistics.median(prices) if prices else None,
        "price_max": max(prices) if prices else None,
    }


def _text_or_none(value):
    return None if value is None or pd.isna(value) or not str(value).strip() else str(value)


def external_brand_items(ext, vectors):
    """สินค้าจากไฟล์ + เวกเตอร์ -> brand_items ของ compute_coverage() (ข้ามแถวที่ไม่มีข้อความให้ embed)"""
    items = []
    for idx, row in ext.iterrows():
        if vectors.get(idx) is None:
            continue
        extra = {k: _text_or_none(row.get(k)) for k in ("image_url", "product_url", "platform")}
        items.append({"row": row, "pos": None, "vec": vectors[idx], "extra": extra})
    return items


def main(argv=None):
    parser = argparse.ArgumentParser(description="⑬ แบรนด์ vs Top N เทรนด์ของรอบ (TREND_RUN_ID)")
    parser.add_argument("--brand", default=None, help="ชื่อแบรนด์ (ไม่ใส่ = TREND_TOPIC หรือถาม)")
    parser.add_argument("--products", default=None,
                        help="CSV สินค้าของแบรนด์ที่ไม่มีบน Watsons (ต้องมี product_name) - ไม่ใส่ = ใช้สินค้าบน Watsons")
    args = parser.parse_args(argv)

    print("=" * 70)
    print("Phase 3 ⑬ — Brand Coverage: สินค้าของแบรนด์ vs Top N เทรนด์ของรอบนี้ (จาก ⑪)")
    print("=" * 70)

    df = pd.read_csv(TOOL_DIR / "product" / "watsons_product.csv", low_memory=False)
    print(f"โหลดสินค้าจริงแล้ว: {len(df)} รายการ, {df['brand'].nunique()} แบรนด์")

    # 🆕 (2026-09-12, audit m3) load_checkpoint(df) รับ df เพื่อ remap cache (เก็บด้วย content hash
    # กันเรียงแถวใหม่/อัปเดตแล้วจับคู่ผิด) กลับเป็น {df.index: vector} ตาม df ปัจจุบัน - ค่า None แปลว่า
    # สินค้าแถวนั้นยังไม่เคย embed (เนื้อหาไม่ตรงกับ hash ไหนใน cache เลย)
    product_embeddings = load_checkpoint(df)
    n_ready = sum(1 for v in product_embeddings.values() if v is not None)
    if n_ready < len(df):
        print(f"❌ embedding cache ไม่ครบ ({n_ready}/{len(df)}) - รัน "
              f"match_products.py (⑫) ให้จบก่อน")
        sys.exit(1)
    all_idx = list(product_embeddings.keys())
    pos_of_idx = {idx: pos for pos, idx in enumerate(all_idx)}  # df index -> ตำแหน่งใน all_vecs/sims
    all_vecs = np.stack([product_embeddings[i] for i in all_idx])  # (10622, 2048)

    if args.products:
        brand = (args.brand or "").strip()
        if not brand:
            raise SystemExit("❌ --products ต้องใส่ --brand ด้วย")
        ext = load_external_products(args.products)
        print(f"✅ สินค้าจากไฟล์ของ '{brand}': {len(ext)} รายการ (ไม่ซ้ำชื่อ)")
        brand_items = external_brand_items(ext, embed_external_products(ext))
        n_brand_skus = len(ext)
        platforms = (sorted({p for p in ext["platform"].dropna().astype(str) if p.strip()})
                     if "platform" in ext.columns else [])
        source = {"product_source": "external", "platforms": platforms, "portfolio": external_portfolio(ext)}
    else:
        brand_wanted = args.brand
        if not brand_wanted:
            brand_wanted, _ = prompt_run_config(default_topic="Watsons", default_years=3, ask_years=False)
            # prompt_run_config ถามแบบ "หัวข้อ" ทั่วไป - ใช้ค่าที่ได้เป็นชื่อแบรนด์ตรงๆ (ไม่เกี่ยวกับปี)
        brand = resolve_brand(df, brand_wanted)
        if brand is None:
            print(f"❌ ไม่เจอแบรนด์ '{brand_wanted}' บน Watsons เลย (ดูรายชื่อใกล้เคียงด้านบน) - ลองใหม่")
            sys.exit(1)
        brand_idx = df.index[df["brand"] == brand].tolist()
        print(f"✅ พบแบรนด์ '{brand}': {len(brand_idx)} SKU")
        brand_items = [{"row": df.loc[idx], "pos": pos_of_idx[idx]} for idx in brand_idx if idx in pos_of_idx]
        n_brand_skus = len(brand_idx)
        source = {"product_source": "watsons"}

    trend_profiles = load_real_trend_profiles()
    print(f"\nกำลัง embed {len(trend_profiles)} trend profile (input_type=query)...")
    trends = embed_trend_profiles(trend_profiles)
    print("เสร็จแล้ว")

    rank_lookup = load_trend_overall_rank()  # 🆕 (2026-09-15) อันดับรวมเทรนด์จาก ⑥ ถ้ามี
    top_rank_lookup = load_trend_top_rank()  # 🆕 (2026-09-16) อันดับภายใน Top N (1..N) จาก ⑪ - ใช้แสดงผล

    print(f"\nกำลังคำนวณ cosine similarity เต็มตลาด ({len(df)} SKU) ต่อเทรนด์ (deterministic, ไม่ยิง API)... "
          f"แล้วให้เหตุผลรายชิ้น (LLM) กับสินค้า {brand} สูงสุด {BRAND_TOP_K} อันดับแรกของแต่ละเทรนด์ "
          f"(~{len(trends[0]) * min(BRAND_TOP_K, max(len(brand_items), 1))} เรียก)...")
    coverage_report = compute_coverage(df, all_idx, all_vecs, brand_items, trends, rank_lookup, top_rank_lookup)

    out_path = OUTPUTS / f"phase3_brand_coverage_{brand.replace(' ', '_')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "_note": "⑬ แบรนด์ vs Top N เทรนด์ของรอบนี้ - สินค้าบน Watsons ใช้ embedding เดิมจาก ⑫ (ไม่ยิง API"
                    " สินค้าเพิ่ม), product_source=external = สินค้าจากไฟล์ จัดอันดับเทียบตลาด Watsons ชุดเดียวกัน",
            "brand": brand, "n_skus": n_brand_skus, "n_market_skus": len(all_idx), **source,
            "coverage": coverage_report,
        }, f, ensure_ascii=False, indent=2)

    # 🆕 (2026-09-16) ไฟล์ Excel คู่กับ JSON (ชื่อเดียวกัน คนละนามสกุล) - ข้อมูลชุดเดียวกัน ดู save_coverage_excel()
    xlsx_path = out_path.with_suffix(".xlsx")
    save_coverage_excel(xlsx_path, brand, n_brand_skus, len(all_idx), coverage_report)

    report_path = OUTPUTS / "phase4_master_trend_report.md"
    if append_brand_section_to_report(report_path, brand, n_brand_skus, len(all_idx), coverage_report):
        print(f"✅ ต่อท้ายอันดับ {brand} เข้า {report_path.name} แล้ว")
    else:
        print(f"  ⏭️  ไม่เจอ {report_path.name} ในรอบนี้ - ข้ามการต่อท้ายรายงาน (ไฟล์ ⑬ แยกยังเซฟไว้ปกติ)")

    print("\n" + "=" * 70)
    print(f"ผล Brand Coverage: {brand} ({n_brand_skus} SKU) เทียบ {len(coverage_report)} เทรนด์")
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


if __name__ == "__main__":
    main()
