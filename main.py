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

🆕 (2026-09-30) เลิกวาดกราฟสรุปของรอบ (Plot_bump_chart.py / Plot_trend_map.py ใช้ค่าพยากรณ์ z-score และ Z_Delta
ที่เจ้าของงานให้เอาออก) - --skip-plots ยังรับได้แต่ไม่มีผล

🆕 (2026-09-25) ⑯ รายงาน PDF 2 ไฟล์ อังกฤษ + ไทย (เฉพาะเทรนด์ ไม่มีหน้าแบรนด์/⑬) รันท้ายโหมด 1 - ข้ามด้วย
--skip-pdf / สร้างใหม่ทีหลังด้วย `python tool/phase6_pdf_report/build_pdf_report.py --run <ชื่อรอบ>`

🆕 (2026-09-26) ⑰ รายงานแบรนด์ x เทรนด์ PDF (อังกฤษ + ไทย) 1 ไฟล์ต่อแบรนด์ - สร้างต่อจาก ⑬ ของแต่ละแบรนด์ในลูปถามแบรนด์
ทั้งโหมด 1 และโหมด 2 (โหมด 1 ข้ามด้วย --skip-pdf) / สร้างใหม่ทีหลังด้วย
`python tool/phase6_pdf_report/build_brand_report.py --run <ชื่อรอบ> --brand <แบรนด์>`
🆕 (2026-10-14) ⑱ รวมเข้า ⑰ แล้ว (หน้าสินค้าต่อเทรนด์ของ ⑰ ใช้หน้าตาเดียวกับ ⑱ เดิม) - ไปป์ไลน์ไม่สร้าง ⑱ แยกอีก (สคริปต์ยังสร้างเองได้):
🆕 (2026-10-05) ⑱ รายงานหมวด x ระดับราคา (อังกฤษ + ไทย) ต่อจาก ⑰ ในลูปเดียวกัน - รันลูกค้า 1 ครั้งได้ 2 รายงาน /
`python tool/phase6_pdf_report/build_brand_category_report.py --run <ชื่อรอบ> --brand <แบรนด์>`

🆕 (2026-10-07) โหมด 3 อัปเดตรอบเดิมด้วย Google Trends ล่าสุด: เลือกรอบที่มีอยู่แล้ว -> สร้างรอบใหม่ (โฟลเดอร์ใหม่ ไม่แตะรอบเดิม)
ที่สำเนาผล ①-⑤ ของรอบเดิม (เทรนด์ + คีย์เวิร์ดเหมือนเดิมทุกตัวอักษร) แล้วรัน ⑦ เป็นต้นไปตามปกติ - หัวข้อ / จำนวนปี / Top N ใช้ของ
รอบเดิม, ⑪ ใช้จุดเด่นเดิม และ ⑫ ใช้เหตุผลจับคู่สินค้าเดิม (env TREND_REFRESH_FROM) รายงานจึงต่างแค่ส่วนที่มาจาก Google Trends
ต่อด้วย ⑬ ⑰ ของแบรนด์ที่รอบเดิมมีผลอยู่ ไม่มีหน้าเทียบกับรอบเดิม (เจ้าของงานเลือก: ได้ไฟล์ชุดใหม่แบบรันปกติ)

Usage:
    python main.py                    # เจอเมนูเลือกโหมด 1/2/3 ก่อน
    python main.py --skip-discovery   # ข้าม ⑩ ไปเลย ไม่ถาม (โหมด 1 อัตโนมัติ)
    python main.py --topic "..." --years 3   # ไม่ต้องพิมพ์โต้ตอบ (โหมด 1 อัตโนมัติ เผื่อรันอัตโนมัติ)
    python main.py --refresh <ชื่อโฟลเดอร์รอบ>   # โหมด 3 ไม่ต้องตอบเมนู/ยืนยัน
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
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
    ("①-⑤ สาย Paper", "phase1_paper_stream/paper_stream.py", True),
    ("①-⑤ สาย Social", "phase2_three_streams/social/social_stream.py", True),
    ("①-⑤ สาย News", "phase2_three_streams/news/news_stream.py", True),
    ("ยืนยัน 3 สายต่างกันจริง (sanity check)", "phase2_three_streams/compare_all_streams.py", False),
    ("⑦ Google Trends จริง (SerpAPI - เสีย quota)", "phase2_three_streams/fetch_trends_worldwide_serpapi.py", True),
    ("⑧-⑨ ชั้นหมวด + ภาพรวม", "phase2_three_streams/run_category_aggregation.py", True),
    # 🆕 (2026-09-16) เปลี่ยนเป็นขั้นที่ต้องผ่าน - ⑪ เป็นต้นไปใช้ผลนี้คัด Top N เทรนด์ (ดู bootstrap.select_top_trends)
    ("⑥ รวมคีย์เวิร์ด + Rank Score (ใช้คัด Top N)", "phase2_three_streams/rank_trends.py", True),
    ("⑪ จับคู่จุดเด่น (LLM)", "phase3_supply_layer/extract_trend_highlights.py", True),
    ("⑫ ชั้นอุปทาน (embed 10,622 SKU จริง)", "phase3_supply_layer/validate_at_scale_nvidia.py", True),
    ("⑭-⑮ STEPIC → Master Report", "phase5_report/run_stepic_report.py", True),
]
DISCOVERY_STAGE = ("⑩ รอบค้นพบเพิ่ม (optional, เสีย quota เล็กน้อย)",
                   "phase2_three_streams/cross_category_discovery.py", False)
BRAND_STAGE = "phase3_supply_layer/run_brand_coverage.py"  # ⑬ - แยกไปด้านล่าง ไม่ใช่ topic เดียวกัน
# 🆕 (2026-09-26) ⑰ รายงานแบรนด์ x เทรนด์ PDF (อังกฤษ + ไทย) 1 ไฟล์ต่อแบรนด์ - รันต่อจาก ⑬ ของแต่ละแบรนด์ในลูปถามแบรนด์
BRAND_REPORT_STAGE = "phase6_pdf_report/build_brand_report.py"
# 🆕 (2026-10-14) ⑱ รายงานหมวด x ระดับราคา รวมเข้า ⑰ แล้ว (หน้าสินค้าต่อเทรนด์ของ ⑰ = หน้าเทรนด์ของ ⑱ เดิม) - ไม่รัน ⑱ แยกอีก
# (สคริปต์ phase6_pdf_report/build_brand_category_report.py ยังอยู่ ใช้สร้าง ⑱ แยกเองได้ถ้าต้องการ)
# 🆕 (2026-09-25) ⑯ รายงาน PDF - ไม่อยู่ใน STAGES เพราะไม่บังคับ (ไม่เกี่ยวกับ ⑬ แบรนด์):
# PDF พังต้องไม่ทำให้รอบรันเป็นชั่วโมงเสีย (ผลทุกขั้นยังอยู่ครบ สร้าง PDF ใหม่ทีหลังได้ด้วยคำสั่งเดี่ยว)
PDF_STAGE = ("⑯ รายงาน PDF (อังกฤษ + ไทย)", "phase6_pdf_report/build_pdf_report.py", False)

# 🆕 (2026-10-07) โหมด 3 อัปเดตรอบเดิม - ผล ①-⑤ ที่สำเนาจากรอบเดิม (ไฟล์เปรียบเทียบ 3 สายไม่บังคับ) แล้วเริ่มรันที่ ⑦
HIGHLIGHTS_FILE = "phase3_trend_highlights_result.json"
STREAM_FILES = ("phase1_paper_stream_result.json", "phase2_social_stream_result.json", "phase2_news_stream_result.json")
REFRESH_OPTIONAL_FILES = ("phase2_all_streams_comparison.json",)
REFRESH_FIRST_STAGE = next(i for i, s in enumerate(STAGES) if s[1].endswith("fetch_trends_worldwide_serpapi.py"))
REFRESH_ENV = "TREND_REFRESH_FROM"   # ต้องตรงกับ tool/common/bootstrap.py's REFRESH_ENV
REFRESH_KEY = "_refresh"             # entry ใน _manifest.json ของรอบใหม่ (ขีดล่างนำหน้า = ไม่ใช่ชื่อขั้น)
SOURCE_STREAM_STAGES = ("paper_stream", "social_stream", "news_stream")

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


def _pipeline_env(**run_vars):
    """env ของทุกขั้นในรอบ: env ปัจจุบัน + ค่าของรอบ (TREND_RUN_ID / TREND_TOPIC / ...) + ให้ output ไทยไม่พัง"""
    env = os.environ.copy()
    env.update(run_vars)
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _print_stage_fix(label, rel_path, run_vars, restart_note):
    """ขั้นจำเป็นพัง - พิมพ์คำสั่งซ่อมเฉพาะขั้นนี้ในรอบเดิม (ตั้ง env ชุดเดียวกับที่ main.py ส่งให้แล้วรันสคริปต์นั้นตรงๆ)"""
    script = TOOL_DIR / rel_path
    print(f"\n🛑 หยุดไปป์ไลน์ที่ '{label}'")
    print(f"   {restart_note}")
    print(f"   ซ่อมเฉพาะขั้นนี้ในรอบเดิม ({run_vars['TREND_RUN_ID']}) โดยไม่รันขั้นก่อนหน้าซ้ำ — ตั้ง env แล้วรัน:")
    print("   PowerShell:  " + "; ".join(f'$env:{k}="{v}"' for k, v in run_vars.items()) + f'; python "{script}"')
    print("   Bash:        " + " ".join(f'{k}="{v}"' for k, v in run_vars.items()) + f' python "{script}"')


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


def _refreshed_from(run_dir):
    """🆕 (2026-10-07) ชื่อรอบต้นทางถ้ารอบนี้สร้างจากโหมด 3 (อ่านจาก _manifest.json) - ไม่ใช่ = สตริงว่าง"""
    try:
        with open(run_dir / "_manifest.json", encoding="utf-8") as f:
            entry = json.load(f).get(REFRESH_KEY) or {}
    except (OSError, json.JSONDecodeError):
        return ""
    return entry.get("refreshed_from") or ""


def _list_available_runs(required=(HIGHLIGHTS_FILE,), include_legacy=True):
    """🆕 (2026-09-15) คืนลิสต์ (label, run_id_for_env, mtime) ของรอบที่มีข้อมูลพอจะเช็คแบรนด์ได้จริง
    (มีผล ⑪ trend profile อยู่) เรียงจากอัปเดตล่าสุดไปเก่าสุด - รวม "ข้อมูลเก่าก่อนมีระบบแยกรอบ" (เก็บ
    แบนๆ ที่ output/ ตรงๆ ไม่มี run_id subfolder) เป็นตัวเลือกพิเศษด้วยถ้ามีจริง (ดู bootstrap.py's
    "_legacy_flat" sentinel) - ไม่เช็ค embedding checkpoint ตรงนี้ (เป็น global ข้ามรอบอยู่แล้ว เช็คจริง
    ที่ run_brand_coverage.py เองตอนรัน จะรายงานชัดเจนถ้าไม่ครบ)

    label ของแต่ละตัวเลือกจะพยายามใส่หัวข้อจริง (จาก _get_run_topic()) นำหน้าเสมอ - ตกมาที่ label เดิม
    (เช่น ชื่อโฟลเดอร์) ถ้าอ่านหัวข้อจริงไม่ได้

    🆕 (2026-10-07) required = ไฟล์ที่รอบต้องมีครบ (โหมด 3 ใช้ผล ①-⑤) เวลาที่ใช้เรียงคือของไฟล์แรก / include_legacy=False
    ไม่รวมชุดข้อมูลเก่าที่ output/ ตรงๆ / รอบที่สร้างจากโหมด 3 มีป้าย [อัปเดตจาก <รอบต้นทาง>]"""
    candidates = []

    legacy_files = [OUTPUT_ROOT / name for name in required]
    if include_legacy and all(p.exists() for p in legacy_files):
        topic = _get_run_topic(OUTPUT_ROOT)
        label = topic or "ข้อมูลเก่า (ก่อนมีระบบแยกรอบ)"
        candidates.append((label, "_legacy_flat", legacy_files[0].stat().st_mtime))

    if OUTPUT_ROOT.exists():
        for d in OUTPUT_ROOT.iterdir():
            # 🆕 (2026-09-15) ข้ามโฟลเดอร์พิเศษทุกอันที่ขึ้นต้นด้วย "_" (ไม่ใช่แค่ _checkpoints เดิม) -
            # ตามธรรมเนียมใหม่ที่ตั้งไว้ตอนจัดระเบียบ output/ (ดู output/README.md): ขีดล่างนำหน้า =
            # ไม่ใช่ผลรัน (เช่น _backups/ ที่เก็บรอบไม่สมบูรณ์/ไฟล์สำรองไว้ - ไม่ควรโผล่เป็นตัวเลือกในเมนู)
            if not d.is_dir() or d.name.startswith("_"):
                continue
            files = [d / name for name in required]
            if all(p.exists() for p in files):
                topic = _get_run_topic(d)
                label = f"{topic} ({d.name})" if topic else d.name
                source = _refreshed_from(d)
                if source:
                    label += f" [อัปเดตจาก {source}]"
                candidates.append((label, d.name, files[0].stat().st_mtime))

    candidates.sort(key=lambda c: c[2], reverse=True)
    return candidates


def _choose_run(runs, what):
    """แสดงรอบให้เลือก (Enter = 1 ล่าสุด) คืน (label, run_id) - ใช้ทั้งโหมด 2 และโหมด 3"""
    print(f"\nรอบที่มีให้เลือก ({what}):")
    for i, (label, _run_id, mtime) in enumerate(runs, 1):
        ts = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {i}. {label}  ({ts})")
    choice_raw = input(f"เลือกรอบ [1-{len(runs)}] (Enter = 1, ล่าสุด): ").strip()
    try:
        choice = int(choice_raw) if choice_raw else 1
    except ValueError:
        choice = 1
    choice = max(1, min(choice, len(runs)))
    label, run_id, _mtime = runs[choice - 1]
    return label, run_id


def run_brand_lookup_loop(env, make_pdf=True):
    """ลูปถามชื่อแบรนด์ต่อเนื่อง เรียก ⑬ (run_brand_coverage.py) ทีละแบรนด์ - ใช้ร่วมกันทั้งโหมด 1
    (ท้ายไปป์ไลน์ที่เพิ่งรันจบ) และโหมด 2 (เลือกรอบเก่ามาเช็ค) กันโค้ดซ้ำ - คืนจำนวนแบรนด์ที่รัน
    🆕 (2026-09-26) make_pdf: หลัง ⑬ ของแต่ละแบรนด์ สร้างรายงานแบรนด์ PDF (⑰) ของแบรนด์นั้นต่อทันที
    🆕 (2026-10-05) แล้วต่อด้วยรายงานหมวด x ระดับราคา (⑱) - ได้ 2 รายงานต่อแบรนด์ในรอบเดียว"""
    print("\n" + "-" * 70)
    print("⑬ จับคู่สินค้า (โหมด 1 — แบรนด์บน Konvy) — ทำได้หลายแบรนด์ต่อเนื่อง พิมพ์ว่างเพื่อจบ")
    print("-" * 70)
    n_brands = 0
    while True:
        brand = input("ชื่อแบรนด์ (Enter เพื่อข้าม/จบ): ").strip()
        if not brand:
            return n_brands
        n_brands += 1
        run_brand(env, brand, make_pdf)


def run_brand(env, brand, make_pdf=True):
    """⑬ ของแบรนด์เดียว แล้วต่อ ⑰ ถ้า make_pdf - 🆕 (2026-10-07) แยกจากลูปถามแบรนด์ให้โหมด 3 รันแบรนด์ของรอบเดิมได้เลย"""
    brand_env = env.copy()
    brand_env["TREND_TOPIC"] = brand  # run_brand_coverage.py ใช้ prompt_run_config ตัวเดียวกัน
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

    label, run_id = _choose_run(runs, "⑪ trend profile พร้อมใช้ - เวลาคืออัปเดต ⑪ ล่าสุด")
    print(f"  ▶ ใช้ข้อมูลจาก: {label}")

    env = _pipeline_env(TREND_RUN_ID=run_id)

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

    run_vars = {"TREND_RUN_ID": run_id, "TREND_TOPIC": topic, "TREND_YEARS": str(years), "TREND_TOP_N": str(top_n)}
    env = _pipeline_env(**run_vars)

    print(f"\nหัวข้อ: {topic!r} | พยากรณ์ {years} ปี ({years * 12} เดือน) | ใช้ Top {top_n} เทรนด์หลังพยากรณ์")
    print(f"ผลลัพธ์รอบนี้: output/{run_id}/")
    print("(ค่าเดียวกันนี้จะถูกส่งให้ทุกขั้นอัตโนมัติ ไม่ต้องพิมพ์ซ้ำ)")

    for label, rel_path, required in STAGES:
        ok = run_stage(label, rel_path, required, env)
        if not ok:
            _print_stage_fix(label, rel_path, run_vars, "รัน main.py ใหม่ทั้งหมด = เริ่มรอบใหม่ (รันขั้นก่อนหน้าซ้ำด้วย)")
            sys.exit(1)

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


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _refresh_config(run_dir):
    """🆕 (2026-10-07) ค่าของรอบเดิมที่โหมด 3 ใช้ต่อ: หัวข้อ / จำนวนปี / Top N ที่ขอ + เดือนสุดท้ายของข้อมูล Google Trends
    (as_of ของ ⑥, "" ถ้ารอบเดิมยังไม่มีผล ⑥) - อ่านไม่ได้ใช้ค่าเริ่มต้นเดียวกับโหมด 1"""
    manifest = _read_json(run_dir / "_manifest.json") or {}
    entries = [v for v in manifest.values() if isinstance(v, dict)]
    topic = (_get_run_topic(run_dir) or next((v["topic"] for v in entries if v.get("topic")), "")
             or "beauty and personal care")
    years_raw = ((manifest.get("fetch_trends_worldwide_serpapi") or {}).get("years")
                 or next((v["years"] for v in entries if v.get("years")), ""))
    try:
        years = max(1, int(years_raw))
    except (TypeError, ValueError):
        years = 3
    highlights = _read_json(run_dir / HIGHLIGHTS_FILE) or {}
    top_n = int(highlights.get("requested_top_n") or DEFAULT_TOP_N)
    as_of = (_read_json(run_dir / "phase2_growth_score_result.json") or {}).get("as_of") or ""
    return {"topic": topic, "years": years, "top_n": top_n, "as_of": as_of}


def _source_brands(run_dir):
    """แบรนด์ที่รอบเดิมมีผล ⑬ (ช่อง brand ในไฟล์ ไม่ใช่ชื่อไฟล์ที่แทนวรรคด้วย _) เรียงตามชื่อไฟล์"""
    brands = []
    for path in sorted(run_dir.glob("phase3_brand_coverage_*.json")):
        brand = (_read_json(path) or {}).get("brand")
        if brand and brand not in brands:
            brands.append(brand)
    return brands


def _count_keywords(run_dir):
    """คีย์เวิร์ดไม่ซ้ำในผล ①-⑤ = จำนวน search ของ SerpAPI ที่ ⑦ จะใช้โดยประมาณ (แยกคำแบบเดียวกับ
    fetch_trends_worldwide_serpapi.build_trend_keyword_mapping)"""
    keywords = set()
    for name in STREAM_FILES:
        for row in (_read_json(run_dir / name) or {}).get("keywords") or []:
            keywords.update(k.strip().lower() for k in str(row.get("Search_Keywords", "")).split(",") if k.strip())
    return len(keywords)


def _last_complete_month(today=None):
    """เดือนล่าสุดที่ Google Trends มีข้อมูลครบ ("YYYY-MM") = เดือนก่อนเดือนนี้ (⑦ ตัดเดือนที่ยังเก็บไม่ครบทิ้ง)"""
    prev = (today or date.today()).replace(day=1) - timedelta(days=1)
    return f"{prev.year}-{prev.month:02d}"


def _prepare_refresh_run(source_dir, run_dir, config):
    """🆕 (2026-10-07) สร้างโฟลเดอร์รอบใหม่ + สำเนาผล ①-⑤ ของรอบเดิม + บันทึกที่มาลง _manifest.json (entry _refresh)
    - timestamp ของ entry = เวลาเริ่มอัปเดต: รายงานใช้ timestamp แรกสุดใน manifest เป็นวันที่ของรอบ (report_data._run_date)
    - models_used = โมเดลที่ 3 สายของรอบเดิมใช้ (รวม entry _refresh ของรอบเดิมถ้ารอบเดิมก็เป็นรอบอัปเดต) ให้รายชื่อโมเดล
      ในรายงานครบเหมือนรอบปกติ / evidence_collected = วันที่เก็บหลักฐาน 3 สายจริง
    คืนรายชื่อไฟล์ที่สำเนา - ผล ①-⑤ ไม่ครบ = หยุดก่อนสร้างโฟลเดอร์"""
    missing = [name for name in STREAM_FILES if not (source_dir / name).exists()]
    if missing:
        raise SystemExit(f"❌ รอบ {source_dir.name} ไม่มีผล ①-⑤ ครบ: {missing}")
    run_dir.mkdir(parents=True)
    copied = []
    for name in STREAM_FILES + REFRESH_OPTIONAL_FILES:
        if (source_dir / name).exists():
            shutil.copyfile(source_dir / name, run_dir / name)
            copied.append(name)

    source_manifest = _read_json(source_dir / "_manifest.json") or {}
    stream_entries = [source_manifest.get(s) or {} for s in SOURCE_STREAM_STAGES + (REFRESH_KEY,)]
    models = {}
    for entry in stream_entries:
        for model, n in (entry.get("models_used") or {}).items():
            models[model] = models.get(model, 0) + int(n or 0)
    collected = (source_manifest.get(REFRESH_KEY) or {}).get("evidence_collected") or min(
        (e["timestamp"] for e in stream_entries[:len(SOURCE_STREAM_STAGES)] if e.get("timestamp")), default="")

    manifest = {REFRESH_KEY: {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "run_id": run_dir.name, "topic": config["topic"], "years": str(config["years"]),
        "refreshed_from": source_dir.name, "source_data_as_of": config["as_of"],
        "evidence_collected": collected, "copied_files": copied, "models_used": models,
    }}
    with open(run_dir / "_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return copied


def run_mode_refresh(args):
    """🆕 (2026-10-07) โหมด 3 — อัปเดตรอบเดิมด้วย Google Trends ล่าสุด: เทรนด์ คีย์เวิร์ด หัวข้อ จำนวนปี Top N จุดเด่น (⑪) และ
    เหตุผลจับคู่สินค้า (⑫) เหมือนรอบเดิม ต่างแค่ข้อมูลการค้นหาที่ ⑦ ดึงใหม่ - ผลลงโฟลเดอร์รอบใหม่ รอบเดิมไม่ถูกแตะ
    ไม่รัน ⑩ (รอบค้นพบเพิ่มเป็นการหาเทรนด์ใหม่ ไม่ใช่การอัปเดต) / --refresh ส่งชื่อรอบมาแล้ว = ไม่ถามเลือกรอบ ไม่ถามยืนยัน
    และไม่ถามแบรนด์เพิ่ม (รันแบรนด์ของรอบเดิมให้อย่างเดียว)"""
    print("\n" + "-" * 70)
    print("โหมด 3: อัปเดตรอบเดิมด้วย Google Trends ล่าสุด (เทรนด์ + คีย์เวิร์ดเดิม ผลลงรอบใหม่)")
    print("-" * 70)

    if args.refresh:
        source_id = args.refresh
    else:
        runs = _list_available_runs(required=STREAM_FILES, include_legacy=False)
        if not runs:
            print("❌ ไม่มีรอบไหนมีผล ①-⑤ ครบ - รันโหมด 1 อย่างน้อย 1 รอบก่อน")
            sys.exit(1)
        _label, source_id = _choose_run(runs, "มีผล ①-⑤ ครบ - เวลาคือตอนเก็บหลักฐาน 3 สาย")
    source_dir = OUTPUT_ROOT / source_id
    if not source_dir.is_dir() or source_id.startswith("_"):
        print(f"❌ ไม่มีรอบ {source_id} ใน {OUTPUT_ROOT}")
        sys.exit(1)

    config = _refresh_config(source_dir)
    brands = [] if args.skip_brand else _source_brands(source_dir)
    latest = _last_complete_month()
    print(f"\n  รอบเดิม: {source_id}")
    print(f"  หัวข้อ: {config['topic']!r} | พยากรณ์ {config['years']} ปี | Top {config['top_n']} (ใช้ค่าของรอบเดิม)")
    print(f"  Google Trends ของรอบเดิมถึง: {config['as_of'] or 'ไม่ทราบ'} | เดือนล่าสุดที่ข้อมูลครบตอนนี้: {latest}")
    n_keywords = _count_keywords(source_dir)
    print(f"  ⑦ จะดึง Google Trends ใหม่ประมาณ {n_keywords} คีย์เวิร์ด = ใช้ SerpAPI ประมาณ {n_keywords} search")
    if brands:
        print(f"  แบรนด์ของรอบเดิมที่จะรัน ⑬ ⑰ ต่อ: {', '.join(brands)}")
    if config["as_of"] and config["as_of"] >= latest:
        print("  ⚠️ ยังไม่มีเดือนใหม่ที่ข้อมูลครบหลังรอบเดิม - ผลจะแทบไม่ต่างจากเดิม")
    if not args.refresh:
        ans = input("\nเริ่มอัปเดตเลยไหม (เสีย SerpAPI quota)? [Y/n]: ").strip().lower()
        if ans in ("n", "no"):
            print("  ⏭️ ยกเลิก - ไม่ได้สร้างรอบใหม่")
            return

    run_id = f"{slugify(config['topic'])}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    copied = _prepare_refresh_run(source_dir, OUTPUT_ROOT / run_id, config)
    run_vars = {"TREND_RUN_ID": run_id, "TREND_TOPIC": config["topic"], "TREND_YEARS": str(config["years"]),
                "TREND_TOP_N": str(config["top_n"]), REFRESH_ENV: source_id}
    env = _pipeline_env(**run_vars)
    print(f"\nผลลัพธ์รอบนี้: output/{run_id}/ (สำเนาจากรอบเดิม: {', '.join(copied)})")

    for label, rel_path, required in STAGES[REFRESH_FIRST_STAGE:]:
        ok = run_stage(label, rel_path, required, env)
        if not ok:
            _print_stage_fix(label, rel_path, run_vars,
                             "เลือกโหมด 3 ใหม่ = สร้างรอบอัปเดตใหม่อีกรอบ (ดึง Google Trends ซ้ำ เสีย quota อีกครั้ง)")
            sys.exit(1)

    if not args.skip_pdf:
        run_stage(*PDF_STAGE, env)

    for brand in brands:
        run_brand(env, brand, make_pdf=not args.skip_pdf)
    if not args.skip_brand and not args.refresh:
        run_brand_lookup_loop(env, make_pdf=not args.skip_pdf)

    print("\n" + "=" * 70)
    print(f"🏁 จบการอัปเดต — ผลทั้งหมดอยู่ที่ {OUTPUT_ROOT / run_id} (รอบเดิม {source_id} ไม่ถูกแตะ)")
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
                        help="ไม่สร้างรายงาน PDF: ⑯ รายงานเทรนด์ท้ายไปป์ไลน์ ⑰ รายงานแบรนด์หลังค้นหาแต่ละแบรนด์")
    # 🆕 (2026-09-30) เลิกวาด Plot_bump_chart / Plot_trend_map (ใช้ค่าพยากรณ์ z-score / Z_Delta) - รับ flag ไว้ไม่ให้คำสั่งเดิมพัง
    parser.add_argument("--skip-plots", action="store_true", help="(ไม่มีผลแล้ว - เลิกวาดกราฟ Z_Delta ตั้งแต่ 2026-09-30)")
    # 🆕 (2026-09-26) --run-id: ผู้เรียก (backend ของ GI_CH) ตั้งชื่อรอบเองเพื่อรู้ว่าผลจะลงโฟลเดอร์ไหน (โหมด 1 เท่านั้น)
    parser.add_argument("--run-id", default=None,
                        help="ชื่อโฟลเดอร์รอบใน output/ (ไม่ใส่ = <หัวข้อ>_<วันเวลา>) - ต้องยังไม่มีหรือว่างอยู่")
    # 🆕 (2026-10-07) โหมด 3 แบบไม่โต้ตอบ (เช่น ตั้งเวลาอัปเดตรายเดือน)
    parser.add_argument("--refresh", default=None, metavar="RUN",
                        help="อัปเดตรอบเดิม (ชื่อโฟลเดอร์ใน output/) ด้วย Google Trends ล่าสุด - ผลลงรอบใหม่ ใช้หัวข้อ/ปี/Top N ของรอบเดิม")
    args = parser.parse_args()
    if args.refresh and (args.topic is not None or args.years is not None or args.top_n is not None):
        parser.error("--refresh ใช้หัวข้อ จำนวนปี และ Top N ของรอบเดิม - ใส่ --topic / --years / --top-n พร้อมกันไม่ได้")

    if args.refresh:
        run_mode_refresh(args)
        return

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
    print("  3. อัปเดตรอบเดิมด้วย Google Trends ล่าสุด (เทรนด์เดิม ผลลงรอบใหม่)")
    mode = input("เลือก [1/2/3] (Enter = 1): ").strip() or "1"

    if mode == "2":
        run_mode_brand_lookup()
    elif mode == "3":
        run_mode_refresh(args)
    else:
        run_mode_full_pipeline(args)


if __name__ == "__main__":
    main()
