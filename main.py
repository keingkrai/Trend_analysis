# -*- coding: utf-8 -*-
"""
Thin orchestrator — รันไปป์ไลน์ v2 ทั้งชุด (①-⑮) ตามลำดับด้วยคำสั่งเดียว

**ไม่แก้โค้ดข้างในสคริปต์ไหนเลย** — แค่เรียกแต่ละสคริปต์ที่มีอยู่แล้ว (proven, ทดสอบผ่านแล้วทุกตัว)
ตามลำดับที่ถูกต้อง ผ่าน subprocess เหมือนรันมือทุกประการ - ดู tool/README.md ตาราง "①-⑮ ทำอะไร"
สำหรับรายละเอียดว่าแต่ละสคริปต์ทำอะไร/เซฟผลที่ไหน

ถามหัวข้อ + จำนวนปีพยากรณ์ **ครั้งเดียวตอนเริ่ม** แล้วส่งต่อเป็น env var (TREND_TOPIC/TREND_YEARS)
ให้ทุกสคริปต์ย่อยใช้ค่าเดียวกัน (ของเดิมแต่ละสคริปต์ถามเองทุกตัวผ่าน prompt_run_config() -
ตั้ง env ไว้ล่วงหน้าจะข้ามการถามอัตโนมัติ)

**⚠️ ⑦ (SerpAPI) และ ⑩ (รอบค้นพบเพิ่ม) เสียโควตา SerpAPI จริง** - สคริปต์เดิมเช็ค quota เองอยู่แล้ว
ก่อนยิงจริง (หยุดเองถ้าไม่พอ) แต่ควรรู้ไว้ก่อนกด

🆕 (2026-09-11) ย้ายจาก workspace/main.py มาไว้ที่ root ตามโครงสร้างใหม่ /tool + /output + main.py
(เดิม workspace/ = ตอนนี้คือ tool/, เดิม workspace/outputs/ = ตอนนี้คือ output/ ที่ root)

🆕 (2026-09-12) แต่ละรอบรันเก็บผลแยกโฟลเดอร์ตาม "หัวข้อ_วันเวลา" (`output/<run_id>/`) ไม่เขียนทับรอบเก่า
อีกต่อไป - ตั้ง env TREND_RUN_ID ให้ทุก stage ใช้ค่าเดียวกัน (bootstrap.py เป็นคนอ่านค่านี้ไปคำนวณ OUTPUTS)

🆕 (2026-09-15) เพิ่มเมนูเลือกโหมดตอนเริ่ม ตามที่เจ้าของงานขอ:
  1. รันเทรนด์ทั้งชุด (①-⑮) - พฤติกรรมเดิมทุกประการ ไม่เปลี่ยนอะไรเลย
  2. ค้นหาแบรนด์สินค้าในเทรนด์ (⑬ อย่างเดียว) - ใช้ผล ⑪/⑫ ของรอบที่มีอยู่แล้ว ไม่ต้องรันเทรนด์ใหม่
     (⑬ ไม่เคยผูกกับการรันเทรนด์ใหม่จริงๆ อยู่แล้ว - ใช้ embedding checkpoint ที่แคชไว้ + trend
     profile ของรอบใดรอบหนึ่งที่เลือก) ให้เลือกว่าจะเช็คกับรอบไหน (list โฟลเดอร์ output/ ที่มี
     ⑪ output จริงให้เลือก, default = รอบล่าสุด, รวมชุดข้อมูลเก่าก่อนมีระบบแยกรอบด้วยถ้ามี - ดู
     bootstrap.py's "_legacy_flat" sentinel)
  --topic/--years ยังใช้ได้เหมือนเดิมสำหรับรันอัตโนมัติ (ข้ามเมนูไปโหมด 1 ตรงๆ)

🆕 (2026-09-25) โหมด 1 วาดกราฟสรุปของรอบให้เองหลังขั้นบังคับครบ (Plot_bump_chart.py -> trend_bump_chart.png +
step5c_df_cluster_forecast_ranks_*.xlsx, Plot_trend_map.py -> trend_top10_zdelta_streamcount.png) - ข้ามด้วย --skip-plots

🆕 (2026-09-25) ⑯ รายงาน PDF 2 ไฟล์ อังกฤษ + ไทย (เฉพาะเทรนด์ ไม่มีหน้าแบรนด์/⑬) รันท้ายโหมด 1 - ข้ามด้วย
--skip-pdf / สร้างใหม่ทีหลังด้วย `python tool/step5_pdf/trend_report_pdf.py --run <ชื่อรอบ>`

🆕 (2026-09-26) ⑰ รายงานแบรนด์ x เทรนด์ PDF (อังกฤษ + ไทย) 1 ไฟล์ต่อแบรนด์ - สร้างต่อจาก ⑬ ของแต่ละแบรนด์ในลูปถามแบรนด์
ทั้งโหมด 1 และโหมด 2 (โหมด 1 ข้ามด้วย --skip-pdf) / สร้างใหม่ทีหลังด้วย
`python tool/step5_pdf/brand_report_pdf.py --run <ชื่อรอบ> --brand <แบรนด์>`

Usage:
    python main.py                    # เจอเมนูเลือกโหมด 1/2 ก่อน
    python main.py --skip-discovery   # ข้าม ⑩ ไปเลย ไม่ถาม (โหมด 1 อัตโนมัติ)
    python main.py --topic "..." --years 3   # ไม่ต้องพิมพ์โต้ตอบ (โหมด 1 อัตโนมัติ เผื่อรันอัตโนมัติ)
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
TOOL_DIR = PROJECT_ROOT / "tool"
OUTPUT_ROOT = PROJECT_ROOT / "output"
# 🆕 (2026-09-16) จำนวนเทรนด์ที่ใช้ต่อหลังพยากรณ์ (⑪ เป็นต้นไป) คัดด้วย Rank Score ของ ⑥ - ต้องตรงกับ
# tool/common/bootstrap.py's TOP_N_TRENDS_DEFAULT (ไม่ import มาตรงๆ เพราะ main.py เป็นตัวเรียก subprocess
# บางๆ ไม่โหลดโมดูลหนักของ pipeline)
DEFAULT_TOP_N = 10


def slugify(text, max_len=50):
    """หัวข้อ -> ชื่อโฟลเดอร์ที่ปลอดภัย (ตัดอักขระที่ Windows path ห้ามใช้, เว้นวรรค->_, ตัดความยาว)"""
    text = re.sub(r'[<>:"/\\|?*]', "", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text[:max_len] or "topic"

# (label, script path relative to TOOL_DIR, required?) - required=False แปลว่าพังแล้วไปต่อได้
# (สคริปต์ต่อจากนี้จะเช็ค input file เองแล้ว error ชัดเจนถ้าขั้นก่อนหน้าไม่ผ่านจริง)
STAGES = [
    ("①-⑤ สาย Paper", "step1_evidence/paper/paper_stream.py", True),
    ("①-⑤ สาย Social", "step1_evidence/social/social_stream.py", True),
    ("①-⑤ สาย News", "step1_evidence/news/news_stream.py", True),
    ("ยืนยัน 3 สายต่างกันจริง (sanity check)", "step1_evidence/check_streams_differ.py", False),
    ("⑦ Google Trends จริง (SerpAPI - เสีย quota)", "step2_forecast/forecast_google_trends.py", True),
    ("⑧-⑨ ชั้นหมวด + ภาพรวม", "step2_forecast/summarize_categories.py", True),
    # 🆕 (2026-09-16) เปลี่ยนเป็นขั้นที่ต้องผ่าน - ⑪ เป็นต้นไปใช้ผลนี้คัด Top N เทรนด์ (ดู bootstrap.select_top_trends)
    ("⑥ รวมคีย์เวิร์ด + Rank Score (ใช้คัด Top N)", "step2_forecast/rank_trends.py", True),
    ("⑪ จับคู่จุดเด่น (LLM)", "step3_products/trend_highlights.py", True),
    ("⑫ ชั้นอุปทาน (embed 10,622 SKU จริง)", "step3_products/match_products.py", True),
    ("⑭-⑮ STEPIC → Master Report", "step4_report/stepic_report.py", True),
]
DISCOVERY_STAGE = ("⑩ รอบค้นพบเพิ่ม (optional, เสีย quota เล็กน้อย)",
                   "step2_forecast/discovery_round.py", False)
BRAND_STAGE = "step3_products/brand_coverage.py"  # ⑬ - แยกไปด้านล่าง ไม่ใช่ topic เดียวกัน
# 🆕 (2026-09-26) ⑰ รายงานแบรนด์ x เทรนด์ PDF (อังกฤษ + ไทย) 1 ไฟล์ต่อแบรนด์ - รันต่อจาก ⑬ ของแต่ละแบรนด์ในลูปถามแบรนด์
BRAND_REPORT_STAGE = "step5_pdf/brand_report_pdf.py"
# 🆕 (2026-09-25) ⑯ รายงาน PDF - ไม่อยู่ใน STAGES เพราะไม่บังคับ (ไม่เกี่ยวกับ ⑬ แบรนด์):
# PDF พังต้องไม่ทำให้รอบรันเป็นชั่วโมงเสีย (ผลทุกขั้นยังอยู่ครบ สร้าง PDF ใหม่ทีหลังได้ด้วยคำสั่งเดี่ยว)
PDF_STAGE = ("⑯ รายงาน PDF (อังกฤษ + ไทย)", "step5_pdf/trend_report_pdf.py", False)
# 🆕 (2026-09-25) กราฟสรุปผลของรอบ - สคริปต์อยู่ที่ root ของ repo (ไม่ใช่ tool/) รับ --run <run_id> ไม่ถามเลือกรอบ
# ไม่บังคับ: กราฟพังต้องไม่ทำให้รอบรันเป็นชั่วโมงเสีย (รันซ้ำเดี่ยวๆ ทีหลังได้ด้วย python <สคริปต์> --run <รอบ>)
# ต้องรันหลัง STAGES ครบ - อ่านผล ⑦ (step5c) และ ⑪ (ชุด Top N)
PLOT_STAGES = [
    ("📊 Bump chart + ตารางอันดับรายปี (step5c)", "Plot_bump_chart.py"),
    ("📊 แผนที่เทรนด์ Top N (Z_Delta vs Stream_Count)", "Plot_trend_map.py"),
]


def run_stage(label, rel_path, required, env, base=TOOL_DIR, extra_args=()):
    """base = โฟลเดอร์ที่ rel_path นับจาก (ค่าเริ่มต้น tool/ - สคริปต์กราฟอยู่ที่ root จึงส่ง base=PROJECT_ROOT)"""
    script = base / rel_path
    print("\n" + "=" * 70)
    print(f"▶ {label}")
    print(f"  ({rel_path})")
    print("=" * 70)
    result = subprocess.run([sys.executable, str(script), *extra_args], cwd=str(PROJECT_ROOT), env=env)
    if result.returncode != 0:
        tag = "❌ พัง (จำเป็น - หยุดที่นี่)" if required else "⚠️ พัง (ไม่บังคับ - ไปต่อ)"
        print(f"\n{tag}: {label} (exit code {result.returncode})")
        if required:
            return False
    else:
        print(f"\n✅ เสร็จ: {label}")
    return True


def _get_run_topic(run_dir):
    """🆕 (2026-09-15) อ่านหัวข้อจริงที่ใช้รันรอบนี้ จาก phase1_paper_stream_result.json's "topic"
    field (บันทึกไว้ตั้งแต่ ①-⑤ สาย Paper ขั้นแรกสุด) - เจ้าของงานขอให้เมนูโหมด 2 โชว์ชื่อหัวข้อจริงที่
    กำลังจะเอาไปเทียบด้วย ไม่ใช่แค่ label ทั่วไป ("ข้อมูลเก่า...") หรือชื่อโฟลเดอร์ที่ผ่าน slugify()
    (ตัดวรรค/ตัดความยาว 50 ตัวอักษร) จนบางทีอ่านแล้วไม่รู้เรื่องว่าหัวข้อจริงคืออะไร

    คืน "" ถ้าอ่านไม่ได้ (ไฟล์ไม่มี/parse ไม่ได้/ไม่มีฟิลด์ topic) - ไม่ error ให้ caller ใช้ label เดิม
    แทนถ้าอ่านหัวข้อจริงไม่ได้"""
    path = run_dir / "phase1_paper_stream_result.json"
    if not path.exists():
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            return (json.load(f).get("topic") or "").strip()
    except (json.JSONDecodeError, OSError):
        return ""


def _list_available_runs():
    """🆕 (2026-09-15) คืนลิสต์ (label, run_id_for_env, mtime) ของรอบที่มีข้อมูลพอจะเช็คแบรนด์ได้จริง
    (มีผล ⑪ trend profile อยู่) เรียงจากอัปเดตล่าสุดไปเก่าสุด - รวม "ข้อมูลเก่าก่อนมีระบบแยกรอบ" (เก็บ
    แบนๆ ที่ output/ ตรงๆ ไม่มี run_id subfolder) เป็นตัวเลือกพิเศษด้วยถ้ามีจริง (ดู bootstrap.py's
    "_legacy_flat" sentinel) - ไม่เช็ค embedding checkpoint ตรงนี้ (เป็น global ข้ามรอบอยู่แล้ว เช็คจริง
    ที่ brand_coverage.py เองตอนรัน จะรายงานชัดเจนถ้าไม่ครบ)

    label ของแต่ละตัวเลือกจะพยายามใส่หัวข้อจริง (จาก _get_run_topic()) นำหน้าเสมอ - ตกมาที่ label เดิม
    (เช่น ชื่อโฟลเดอร์) ถ้าอ่านหัวข้อจริงไม่ได้"""
    candidates = []

    legacy_highlights = OUTPUT_ROOT / "phase3_trend_highlights_result.json"
    if legacy_highlights.exists():
        topic = _get_run_topic(OUTPUT_ROOT)
        label = topic or "ข้อมูลเก่า (ก่อนมีระบบแยกรอบ)"
        candidates.append((label, "_legacy_flat", legacy_highlights.stat().st_mtime))

    if OUTPUT_ROOT.exists():
        for d in OUTPUT_ROOT.iterdir():
            # 🆕 (2026-09-15) ข้ามโฟลเดอร์พิเศษทุกอันที่ขึ้นต้นด้วย "_" (ไม่ใช่แค่ _checkpoints เดิม) -
            # ตามธรรมเนียมใหม่ที่ตั้งไว้ตอนจัดระเบียบ output/ (ดู output/README.md): ขีดล่างนำหน้า =
            # ไม่ใช่ผลรัน (เช่น _backups/ ที่เก็บรอบไม่สมบูรณ์/ไฟล์สำรองไว้ - ไม่ควรโผล่เป็นตัวเลือกในเมนู)
            if not d.is_dir() or d.name.startswith("_"):
                continue
            highlights = d / "phase3_trend_highlights_result.json"
            if highlights.exists():
                topic = _get_run_topic(d)
                label = f"{topic} ({d.name})" if topic else d.name
                candidates.append((label, d.name, highlights.stat().st_mtime))

    candidates.sort(key=lambda c: c[2], reverse=True)
    return candidates


def run_brand_lookup_loop(env, make_pdf=True):
    """ลูปถามชื่อแบรนด์ต่อเนื่อง เรียก ⑬ (brand_coverage.py) ทีละแบรนด์ - ใช้ร่วมกันทั้งโหมด 1
    (ท้ายไปป์ไลน์ที่เพิ่งรันจบ) และโหมด 2 (เลือกรอบเก่ามาเช็ค) กันโค้ดซ้ำ - คืนจำนวนแบรนด์ที่รัน
    🆕 (2026-09-26) make_pdf: หลัง ⑬ ของแต่ละแบรนด์ สร้างรายงานแบรนด์ PDF (⑰) ของแบรนด์นั้นต่อทันที"""
    print("\n" + "-" * 70)
    print("⑬ จับคู่สินค้า (โหมด 1 — แบรนด์บน Watsons) — ทำได้หลายแบรนด์ต่อเนื่อง พิมพ์ว่างเพื่อจบ")
    print("-" * 70)
    n_brands = 0
    while True:
        brand = input("ชื่อแบรนด์ (Enter เพื่อข้าม/จบ): ").strip()
        if not brand:
            return n_brands
        n_brands += 1
        brand_env = env.copy()
        brand_env["TREND_TOPIC"] = brand  # brand_coverage.py ใช้ prompt_run_config ตัวเดียวกัน
        run_stage(f"⑬ Brand Coverage — {brand}", BRAND_STAGE, False, brand_env)
        if make_pdf:
            # ถ้า ⑬ พัง (ไม่มีผลของแบรนด์นี้) ⑰ จะแจ้งเองว่าไม่พบผลแล้วจบ - ไม่บังคับ ไม่หยุดลูป
            run_stage(f"⑰ รายงานแบรนด์ PDF — {brand}", BRAND_REPORT_STAGE, False, brand_env,
                      extra_args=["--brand", brand])


def run_mode_brand_lookup():
    """🆕 (2026-09-15) โหมด 2 — ค้นหาแบรนด์สินค้าในเทรนด์จากรอบที่มีอยู่แล้ว ไม่ต้องรันเทรนด์ใหม่เลย
    (⑬ ไม่เคยพึ่งการรันเทรนด์ใหม่จริงๆ - ใช้ embedding checkpoint ที่แคชไว้จาก ⑫ + trend profile ของ
    รอบใดรอบหนึ่งที่เลือกจาก ⑪) ต่างจากโหมด 1 ตรงที่ข้ามการรัน STAGES ทั้งหมดไปเลย"""
    print("\n" + "-" * 70)
    print("โหมด 2: ค้นหาแบรนด์สินค้าในเทรนด์ (ใช้ผลรอบที่มีอยู่แล้ว ไม่ต้องรันเทรนด์ใหม่)")
    print("-" * 70)

    runs = _list_available_runs()
    if not runs:
        print("❌ ไม่มีรอบไหนพร้อมเช็คแบรนด์เลย (ต้องมีผล ⑪ อย่างน้อย 1 รอบก่อน)")
        print("   รันโหมด 1 (รันเทรนด์ทั้งชุด) อย่างน้อย 1 รอบก่อน แล้วค่อยกลับมาโหมดนี้")
        sys.exit(1)

    print("\nรอบที่มีให้เลือก (⑪ trend profile พร้อมใช้):")
    for i, (label, _run_id, mtime) in enumerate(runs, 1):
        ts = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {i}. {label}  (⑪ อัปเดตล่าสุด {ts})")

    choice_raw = input(f"เลือกรอบ [1-{len(runs)}] (Enter = 1, ล่าสุด): ").strip()
    try:
        choice = int(choice_raw) if choice_raw else 1
    except ValueError:
        choice = 1
    choice = max(1, min(choice, len(runs)))
    label, run_id, _mtime = runs[choice - 1]
    print(f"  ▶ ใช้ข้อมูลจาก: {label}")

    env = os.environ.copy()
    env["TREND_RUN_ID"] = run_id
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    run_brand_lookup_loop(env)

    print("\n" + "=" * 70)
    print("🏁 จบ - เช็คแบรนด์เสร็จแล้ว")
    print("=" * 70)


def run_mode_full_pipeline(args):
    """โหมด 1 — รันไปป์ไลน์ทั้งชุด ①-⑮ (พฤติกรรมเดิมทุกประการ ก่อนมีเมนูเลือกโหมด)"""
    print("=" * 70)
    print("Trend Pipeline v2 — รันเต็ม ①-⑮ (thin orchestrator, ไม่แก้โค้ดข้างในเลย)")
    print("=" * 70)

    topic = args.topic or input("หัวข้อเทรนด์ (Enter = beauty and personal care): ").strip() \
        or "beauty and personal care"
    if args.years is not None:
        years = args.years
    else:
        years_raw = input("พยากรณ์ไปกี่ปี (Enter = 3): ").strip()
        years = int(years_raw) if years_raw else 3
    # 🆕 (2026-09-16) จำนวนเทรนด์ที่ใช้ต่อหลังพยากรณ์ - ①-⑦ ยังทำครบทุกเทรนด์ (สายละ 5) แล้วคัด N อันดับแรกตาม
    # Rank Score ของ ⑥ ให้ ⑪ ⑫ ⑬ และรายงานใช้ชุดเดียวกัน
    if args.top_n is not None:
        top_n = max(1, args.top_n)
    else:
        top_n_raw = input(f"ใช้กี่เทรนด์อันดับแรกหลังพยากรณ์ (Enter = {DEFAULT_TOP_N}): ").strip()
        top_n = max(1, int(top_n_raw)) if top_n_raw else DEFAULT_TOP_N

    # 🆕 (2026-09-26) --run-id: ผู้เรียก (backend ของ GI_CH) ตั้งชื่อรอบเองเพื่อรู้ว่าผลจะลงโฟลเดอร์ไหน
    run_id = args.run_id or f"{slugify(topic)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = OUTPUT_ROOT / run_id
    if run_dir.exists() and any(run_dir.iterdir()):
        print(f"❌ มีโฟลเดอร์รอบ {run_id} ที่มีไฟล์อยู่แล้ว - ใช้ชื่อรอบอื่น (ไม่เขียนทับรอบเดิม)")
        sys.exit(1)

    env = os.environ.copy()
    env["TREND_TOPIC"] = topic
    env["TREND_YEARS"] = str(years)
    env["TREND_TOP_N"] = str(top_n)
    env["TREND_RUN_ID"] = run_id
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    print(f"\nหัวข้อ: {topic!r} | พยากรณ์ {years} ปี ({years * 12} เดือน) | ใช้ Top {top_n} เทรนด์หลังพยากรณ์")
    print(f"ผลลัพธ์รอบนี้: output/{run_id}/")
    print("(ค่าเดียวกันนี้จะถูกส่งให้ทุกขั้นอัตโนมัติ ไม่ต้องพิมพ์ซ้ำ)")

    for label, rel_path, required in STAGES:
        ok = run_stage(label, rel_path, required, env)
        if not ok:
            script = TOOL_DIR / rel_path
            print(f"\n🛑 หยุดไปป์ไลน์ที่ '{label}'")
            print("   รัน main.py ใหม่ทั้งหมด = เริ่มรอบใหม่ (รันขั้นก่อนหน้าซ้ำด้วย)")
            print(f"   ซ่อมเฉพาะขั้นนี้ในรอบเดิม ({run_id}) โดยไม่รันขั้นก่อนหน้าซ้ำ — ตั้ง env แล้วรัน:")
            print(f'   PowerShell:  $env:TREND_RUN_ID="{run_id}"; $env:TREND_TOPIC="{topic}"; '
                  f'$env:TREND_YEARS="{years}"; $env:TREND_TOP_N="{top_n}"; python "{script}"')
            print(f'   Bash:        TREND_RUN_ID={run_id} TREND_TOPIC="{topic}" TREND_YEARS={years} '
                  f'TREND_TOP_N={top_n} python "{script}"')
            sys.exit(1)

    if not args.skip_plots:
        for label, script_name in PLOT_STAGES:
            run_stage(label, script_name, False, env, base=PROJECT_ROOT, extra_args=["--run", run_id])

    if not args.skip_discovery:
        ans = input("\nรัน ⑩ รอบค้นพบเพิ่มไหม (optional, เสีย SerpAPI quota เล็กน้อย)? [y/N]: ").strip().lower()
        if ans == "y":
            run_stage(*DISCOVERY_STAGE, env)
        else:
            print("  ⏭️  ข้าม ⑩")

    if not args.skip_pdf:
        run_stage(*PDF_STAGE, env)

    if not args.skip_brand:
        run_brand_lookup_loop(env, make_pdf=not args.skip_pdf)

    print("\n" + "=" * 70)
    print(f"🏁 จบไปป์ไลน์ — ผลทั้งหมดอยู่ที่ {PROJECT_ROOT / 'output' / run_id}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="รันไปป์ไลน์ v2 ทั้งชุด ①-⑮ ตามลำดับ")
    parser.add_argument("--topic", default=None, help="หัวข้อเทรนด์ (ไม่ใส่ = ถามตอนรัน)")
    parser.add_argument("--years", type=int, default=None, help="จำนวนปีพยากรณ์ (ไม่ใส่ = ถามตอนรัน)")
    parser.add_argument("--top-n", type=int, default=None,
                        help=f"จำนวนเทรนด์อันดับแรกที่ใช้หลังพยากรณ์ (ไม่ใส่ = ถามตอนรัน, Enter = {DEFAULT_TOP_N})")
    parser.add_argument("--skip-discovery", action="store_true", help="ข้าม ⑩ ไปเลย ไม่ถาม")
    parser.add_argument("--skip-brand", action="store_true", help="ข้าม ⑬ (จับคู่แบรนด์) ไปเลย ไม่ถาม")
    parser.add_argument("--skip-pdf", action="store_true",
                        help="ไม่สร้างรายงาน PDF: ⑯ รายงานเทรนด์ท้ายไปป์ไลน์ และ ⑰ รายงานแบรนด์หลังค้นหาแต่ละแบรนด์")
    parser.add_argument("--skip-plots", action="store_true", help="ไม่วาด bump chart / แผนที่เทรนด์ หลังขั้นบังคับครบ")
    parser.add_argument("--run-id", default=None,
                        help="ชื่อโฟลเดอร์รอบใน output/ (ไม่ใส่ = <หัวข้อ>_<วันเวลา>) - ต้องยังไม่มีหรือว่างอยู่")
    args = parser.parse_args()

    # 🆕 (2026-09-15) --topic ที่ส่งมาทาง CLI แปลว่าตั้งใจรันอัตโนมัติ (เช่น scheduler) - ข้ามเมนูไป
    # โหมด 1 ตรงๆ เหมือนพฤติกรรมเดิมก่อนมีเมนู ไม่บังคับให้ตอบเมนูก่อนทุกครั้งตอนรันแบบไม่โต้ตอบ
    if args.topic is not None:
        run_mode_full_pipeline(args)
        return

    print("=" * 70)
    print("Trend Pipeline v2")
    print("=" * 70)
    print("เลือกโหมด:")
    print("  1. รันเทรนด์ทั้งชุด (①-⑮)")
    print("  2. ค้นหาแบรนด์สินค้าในเทรนด์ (ใช้ผลรอบที่มีอยู่แล้ว ไม่ต้องรันใหม่)")
    mode = input("เลือก [1/2] (Enter = 1): ").strip() or "1"

    if mode == "2":
        run_mode_brand_lookup()
    else:
        run_mode_full_pipeline(args)


if __name__ == "__main__":
    main()
