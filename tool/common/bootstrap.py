# -*- coding: utf-8 -*-
"""
bootstrap — ตัวหาตำแหน่งโปรเจกต์ให้ทุกสคริปต์ใน tool/

ทำไมต้องมี: สคริปต์ใน tool/ อยู่ลึกไม่เท่ากัน (phase2_three_streams/social/ ลึก 3 ชั้น
ส่วน phase0_cleanup/ ลึก 1 ชั้น) การเขียน BASE_DIR = parent.parent แบบตายตัวเหมือนใน analysis/
เดิมจะพังทันทีที่ย้ายไฟล์ - ตัวนี้เดินขึ้นไปหาไฟล์ .env แทน จึงย้ายไฟล์ไปไหนก็ยังหาเจอ

🆕 (2026-09-11) `PROJECT_ROOT` กับ `OUTPUTS` เป็นคนละเรื่องกันตั้งใจ แยกออกจากกันเพราะเคยพังมาแล้ว:
`tool/` ถูกย้ายมาซ้อนอยู่ใต้โฟลเดอร์ `main/` (สำหรับแพ็กเป็นชุดที่ใช้จริงเฉพาะ v2) แต่ `trend_final.py`
(ห้ามแตะ ห้ามย้าย เด็ดขาด) ยังอยู่ที่ root เดิมเสมอ ไม่ได้ตามมาด้วย - สูตรเดิม `PROJECT_ROOT =
TOOL_DIR.parent` ตรงๆ (fixed-depth) เลยคำนวณผิดทันทีที่ `tool/` ลึกกว่าเดิม 1 ชั้น ต้อง**เดินขึ้นไปหา
`trend_final.py` แบบ dynamic จริง** (เหมือน `data_prep/scrape_watsons.py`/`tool/notebooks/trend.ipynb`
ที่แก้ไปแล้วก่อนหน้านี้) แทน - ผลคือ **ไม่ต้องมีสำเนา `trend_final.py`/`trend_final_v2.py` ซ้ำอยู่ในหลาย
ที่เลย มีต้นฉบับที่เดียวจริงตลอด ไม่ว่า `tool/` จะถูกย้ายไปซ้อนลึกแค่ไหนก็ตาม**

ส่วน `OUTPUTS` ต้องอยู่ **ข้างๆ `tool/` เสมอ** (ไม่ใช่ข้างๆ `trend_final.py`) เพราะผลรันของ v2 ต้องอยู่
ด้วยกันกับโค้ดที่สร้างมันตอนย้ายทั้งชุด - เลยคำนวณจาก `TOOL_DIR.parent` ตรงๆ (ไม่ผ่านการเดินขึ้นหา
`trend_final.py`) คนละสูตรกับ `PROJECT_ROOT` โดยเจตนา

🆕 (2026-09-22) สองย่อหน้าบนเป็นประวัติ - ตอนนี้ `PROJECT_ROOT` = `main/` เสมอ (ไม่เดินขึ้นไปหา `trend_final.py`
แล้ว) และ `tf` ชี้ไปที่ `common/trend_final_subset.py` (ส่วนที่ใช้จริงของ `trend_final.py` คัดลอกตรงตัว) - ทุกอย่าง
ที่ไปป์ไลน์ใช้อยู่ใน `main/` แล้ว ต้นฉบับไม่ถูกแก้ (ย้ายไปเก็บที่ `_archive/root_legacy_20260922/`) ดู
`tests/test_trend_final_subset.py`

🆕 (2026-09-12) `OUTPUTS` แยกเป็น**ต่อรอบ** (`output/<run_id>/`) แล้ว ตามที่เจ้าของงานขอ - เดิมทุกรอบรัน
เขียนทับไฟล์ชื่อเดิมใน `output/` แบนๆ เห็นผลลัพธ์ปนกันหมดแยกไม่ออกว่ารอบไหน `<run_id>` มาจาก env
`TREND_RUN_ID` ที่ `main.py` ตั้งให้ครั้งเดียวตอนเริ่ม (หัวข้อ+วันเวลา) แล้วส่งต่อให้ทุก stage
subprocess ใช้ค่าเดียวกัน (เหมือน `TREND_TOPIC`/`TREND_YEARS`) - ถ้าไม่มี (รันสคริปต์เดี่ยวๆ เองโดยไม่
ผ่าน `main.py` และไม่ได้ตั้ง env เอง) fallback เป็น `adhoc_<timestamp>` ใหม่ทุกครั้ง (กันปนกับรอบจริง)
🆕 (2026-09-16) โฟลเดอร์ `adhoc_*` ที่ไม่มีไฟล์เลยจะลบตัวเองตอนจบโปรเซส (atexit + `os.rmdir`) - ดูเหตุผล
ที่ไม่ย้ายไปสร้างตอนเขียนไฟล์จริงแทน ในคอมเมนต์ตรงจุดที่ลงมือ (ใต้ `OUTPUTS.mkdir()`)
ถ้าจะซ่อมเฉพาะขั้นที่พังของรอบเดิม ให้ตั้ง `TREND_RUN_ID=<ชื่อโฟลเดอร์รอบนั้น>` เองก่อนรันสคริปต์นั้นตรงๆ
(main.py พิมพ์คำสั่งที่ต้องใช้ให้เองตอนพัง)

**ข้อยกเว้น:** ไฟล์ที่เป็น cache ข้ามรอบได้จริง (ไม่ขึ้นกับหัวข้อ) เช่น embedding ของแคตตาล็อกสินค้า
10,622 SKU ต้อง**ไม่**อยู่ใต้ `<run_id>` เพราะจะถูก re-embed ใหม่ทุกรอบ (เสีย NVIDIA API เปล่าๆ) - ใช้
`CHECKPOINTS` (แบนๆ อยู่นอก `<run_id>` เสมอ) แทน `OUTPUTS` สำหรับไฟล์ประเภทนี้โดยเฉพาะ

วิธีใช้ (วางไว้บนสุดของสคริปต์ ก่อน import อย่างอื่นที่ต้องใช้ .env):

    import sys
    from pathlib import Path
    for _p in Path(__file__).resolve().parents:
        if (_p / "common" / "bootstrap.py").exists():
            sys.path.insert(0, str(_p)); break
    from common.bootstrap import PROJECT_ROOT, TOOL_DIR, OUTPUTS, CHECKPOINTS, tf
"""
import atexit
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve()

# tool/common/bootstrap.py -> tool/ (ตำแหน่งนี้คงที่เสมอ ไม่ว่า tool/ เองจะถูกย้ายไปซ้อนลึกแค่ไหน)
TOOL_DIR = _HERE.parent.parent
WORKSPACE = TOOL_DIR  # ชื่อเดิม เก็บไว้เผื่อโค้ดเก่าที่ยัง import WORKSPACE อยู่ (ไม่มีใครใช้จริง ณ ตอนนี้)

# output/ อยู่ข้างๆ tool/ เสมอ - ไม่เกี่ยวกับว่า trend_final.py อยู่ไกลแค่ไหน (ดู docstring ด้านบน)
_OUTPUT_ROOT = TOOL_DIR.parent / "output"
_RUN_ID = os.environ.get("TREND_RUN_ID") or f"adhoc_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
# 🆕 (2026-09-15) sentinel พิเศษ "_legacy_flat" - ชี้ OUTPUTS ไปที่ output/ ตรงๆ ไม่มี run_id subfolder
# ใช้กับผลรันจริงที่มีอยู่ก่อนระบบแยกรอบ (2026-09-11) จะมีถึง (เก็บแบนๆ ที่ output/ root) - main.py's
# โหมด 2 (ค้นหาแบรนด์จากรอบที่มีอยู่แล้ว โดยไม่ต้องรันเทรนด์ใหม่) ใช้ค่านี้เวลาผู้ใช้เลือกชุดข้อมูลเก่านี้
# ไม่กระทบพฤติกรรมเดิมเลยถ้าไม่ได้ตั้ง TREND_RUN_ID=_legacy_flat ตรงๆ
if _RUN_ID == "_legacy_flat":
    OUTPUTS = _OUTPUT_ROOT
else:
    OUTPUTS = _OUTPUT_ROOT / _RUN_ID  # ผลลัพธ์เฉพาะรอบนี้ (ดู docstring ด้านบน)
OUTPUTS.mkdir(parents=True, exist_ok=True)

# 🆕 (2026-09-16) โฟลเดอร์ adhoc_* ที่ไม่มีไฟล์เลยตอนจบโปรเซส ให้ลบตัวเองทิ้ง - ทุกครั้งที่สคริปต์เดี่ยวๆ
# หรือชุดเทส import ไฟล์นี้โดยไม่ได้ตั้ง TREND_RUN_ID จะเกิดโฟลเดอร์ว่างเพิ่ม 1 อันทันทีตั้งแต่ตอน import
# (สะสมไป 72 อันแล้วครั้งหนึ่ง ต้องมาไล่ลบมือ) - **ไม่ย้ายไปสร้างตอนเขียนไฟล์จริงแทน** เพราะมีสคริปต์ 25 ไฟล์
# ที่ open(OUTPUTS / "...", "w") ตรงๆ โดยไม่ได้ mkdir เอง ถ้าเอาการสร้างข้างบนออกจะพังตอนเซฟผลท้ายรอบ
# (เสียทั้งรอบรันที่ใช้เวลาเป็นชั่วโมง) - ลบตอนจบจึงปลอดภัยกว่า: ระหว่างรันโฟลเดอร์ยังอยู่ตลอดเหมือนเดิม และ
# os.rmdir() ลบได้เฉพาะโฟลเดอร์ที่ว่างจริงเท่านั้น ถ้ามีผลลัพธ์อยู่ข้างในแม้แต่ไฟล์เดียวจะไม่แตะเลย
if _RUN_ID.startswith("adhoc_"):
    def _remove_run_dir_if_empty(_path=OUTPUTS):
        try:
            os.rmdir(_path)
        except OSError:
            pass  # มีไฟล์ผลลัพธ์อยู่ข้างใน (หรือโดนลบไปแล้ว) - ปล่อยไว้ตามเดิม

    atexit.register(_remove_run_dir_if_empty)

CHECKPOINTS = _OUTPUT_ROOT / "_checkpoints"  # cache ข้ามรอบ (ไม่ขึ้นกับหัวข้อ) - แบนๆ เสมอ ไม่แยกตามรอบ
CHECKPOINTS.mkdir(parents=True, exist_ok=True)

# 🆕 (2026-09-22) PROJECT_ROOT = main/ เสมอ - ทุกอย่างที่ไปป์ไลน์ใช้อยู่ใน main/ แล้ว (.env, config/,
# ส่วนที่ใช้จริงของ trend_final.py/trend_final_v2.py) ไม่ต้องเดินขึ้นไปหา trend_final.py ที่ root อีกต่อไป
# (เดิมเดินขึ้นไปหา - ดู docstring ด้านบน) ต้นฉบับไม่ถูกแก้ ย้ายไปเก็บใน _archive/ แล้ว
PROJECT_ROOT = TOOL_DIR.parent

# โหลด .env ของ main/
from dotenv import load_dotenv  # noqa: E402
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# ส่วนที่ใช้จริงของ trend_final.py คัดลอกตรงตัวไว้ที่ common/trend_final_subset.py - ชื่อ `tf` เหมือนเดิม
# โค้ดที่เรียก tf.xxx จึงไม่ต้องแก้ (ต้อง import หลัง load_dotenv เสมอ)
from common import trend_final_subset as tf  # noqa: E402,F401

# ตั้ง stdout เป็น utf-8 เพราะ console ไทยบน Windows เป็น cp874 ทำให้ print ภาษาไทย/emoji crash
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# 🆕 (2026-09-12, audit m2) เกณฑ์ขั้นต่ำแบบ sanity guardrail (ไม่ใช่เกณฑ์คุณภาพที่ calibrate แล้ว - รอ
# label จากคนก่อนตามแผนใน [[แผนแก้ Data Science Audit]] M1/M6) จับแค่กรณีพังชัดเจน (scraper/LLM ล้มเหลว
# จนได้ข้อมูลเกือบศูนย์) กันไปป์ไลน์ "สำเร็จ" (exit 0) ทั้งที่หลักฐานบางเกินจะเชื่อถือได้เลย
MIN_SCRAPED, MIN_TRIPLETS, MIN_CLUSTERS = 5, 5, 1


def check_minimum_evidence(stream_name, n_scraped, n_triplets, n_clusters):
    """คืน True ถ้าผ่านเกณฑ์ขั้นต่ำ, False ถ้าไม่ผ่าน (caller ควร sys.exit(1) เพื่อให้ main.py หยุด
    ไปป์ไลน์ที่ required stage นี้ แทนที่จะปล่อยให้ขั้นถัดไปทำงานต่อด้วยข้อมูลที่บางเกินไป)"""
    problems = []
    if n_scraped < MIN_SCRAPED:
        problems.append(f"scraped={n_scraped} < {MIN_SCRAPED}")
    if n_triplets < MIN_TRIPLETS:
        problems.append(f"triplets={n_triplets} < {MIN_TRIPLETS}")
    if n_clusters < MIN_CLUSTERS:
        problems.append(f"clusters={n_clusters} < {MIN_CLUSTERS}")
    if problems:
        print(f"❌ {stream_name}: หลักฐานบางเกินไป จะไม่ถือว่าสำเร็จ ({', '.join(problems)})")
        return False
    return True


# ---------------------------------------------------------------------------
# 🆕 (2026-09-12, audit C5) reproducibility manifest ต่อขั้น - เขียนอัตโนมัติผ่าน atexit ไม่ต้องแก้โค้ด
# เพิ่มในแต่ละสคริปต์ของ 10 ขั้นเลย (ทุกขั้นของ v2 import bootstrap.py อยู่แล้วเป็นบรรทัดแรกๆ)
#
# ทำไมต้องมี: audit ขอ "manifest ต่อขั้น (hash input, โมเดล, เวลา) + ขั้นถัดไปตรวจ manifest ขั้นก่อนหน้า
# ก่อนเริ่ม" ระบบแยก output/<run_id>/ ที่ทำไปแล้ว (2026-09-12, เหตุผลอื่น) แก้ปัญหา "ผลจากคนละรอบปนกัน"
# ไปส่วนหนึ่งแล้ว แต่ยังไม่รู้ **ภายในรอบเดียวกัน** ว่าขั้นไหนใช้โมเดลอะไรจริง (โปรเจกต์นี้มี fallback
# Typhoon/NVIDIA/Gemini/Gemma/DeepSeek เยอะมากเวลา credit หลัก (OpenRouter) หมด - ถ้าไม่บันทึกไว้จะไม่มี
# ทางรู้ย้อนหลังว่ารายงานฉบับหนึ่งมาจากโมเดลอะไรบ้างผสมกัน) และไม่รู้ว่าไฟล์ input ที่ขั้นถัดไปอ่านจริง
# ตรงกับที่ขั้นก่อนหน้าเขียนไว้ล่าสุดหรือเปล่า (เช่น ไฟล์ถูกแก้มือระหว่างดีบัก/มาจากคนละรอบเพราะลืมตั้ง
# TREND_RUN_ID)
#
# STAGE_IO_MAP คือ source of truth เดียวว่า "สคริปต์ไหนอ่าน/เขียนไฟล์อะไรจริง" (ตรวจจาก grep "OUTPUTS /"
# ทั้งโปรเจกต์ 2026-09-12 ไม่ได้เดา) - ต้องแก้ตรงนี้จุดเดียวถ้าขั้นไหนเปลี่ยนไฟล์ input/output จริง
STAGE_IO_MAP = {
    "paper_stream": {"inputs": [], "outputs": ["phase1_paper_stream_result.json"]},
    "social_stream": {"inputs": [], "outputs": ["phase2_social_stream_result.json"]},
    "news_stream": {"inputs": [], "outputs": ["phase2_news_stream_result.json"]},
    "fetch_trends_worldwide_serpapi": {
        "inputs": ["phase1_paper_stream_result.json", "phase2_social_stream_result.json",
                   "phase2_news_stream_result.json"],
        "outputs": ["phase2_paper_social_z_delta_result.json"],
    },
    "run_category_aggregation": {
        "inputs": ["phase2_paper_social_z_delta_result.json"],
        "outputs": ["phase2_category_overall_result.json"],
    },
    "rank_trends": {
        "inputs": ["phase2_paper_social_z_delta_result.json", "phase1_paper_stream_result.json",
                   "phase2_social_stream_result.json", "phase2_news_stream_result.json"],
        "outputs": ["phase2_rank_score_final_mode_result.json", "phase2_longevity_cross_source_result.json"],
    },
    "extract_trend_highlights": {
        # 🆕 (2026-09-16) + ผล ⑥ ใช้คัด Top N เทรนด์ + ผลพยากรณ์ของ ⑦ ใช้ทำสำเนา step5c_..._top{N}.xlsx
        # (ไฟล์สำเนาชื่อเปลี่ยนตาม N จึงไม่ได้ใส่ใน outputs ที่ต้องเป็นชื่อตายตัว)
        "inputs": ["phase1_paper_stream_result.json", "phase2_social_stream_result.json",
                   "phase2_news_stream_result.json", "phase2_rank_score_final_mode_result.json",
                   "serpapi_forecast_run/step5c_df_cluster_forecast.xlsx"],
        "outputs": ["phase3_trend_highlights_result.json"],
    },
    "validate_at_scale_nvidia": {
        "inputs": ["phase3_trend_highlights_result.json"],
        "outputs": ["phase3_scale_validation_nvidia_result.json"],
    },
    "cross_category_discovery": {
        "inputs": [],
        "outputs": ["phase2_cross_category_discovery_result.json"],
    },
    "run_stepic_report": {
        # 🆕 (2026-09-16) + ผล ⑪ ใช้อ่านชุด Top N ที่คัดไว้ (selected_trends) ให้รายงานตรงกับ ⑪-⑫
        "inputs": ["phase1_paper_stream_result.json", "phase2_social_stream_result.json",
                   "phase2_news_stream_result.json", "phase3_scale_validation_nvidia_result.json",
                   "phase2_paper_social_z_delta_result.json", "phase2_longevity_cross_source_result.json",
                   "phase3_trend_highlights_result.json"],
        "outputs": ["phase4_master_trend_report.md", "phase4_stepic_raw_analysis.json",
                    "phase4_stepic_final_insight.json"],
    },
}

_MODELS_USED_THIS_STAGE = {}  # {model_name: จำนวนครั้งที่ patch เข้าใช้จริงในขั้นนี้}


def record_model_used(model_name):
    """ให้ use_typhoon()/use_nvidia()/use_gemini()/use_gemma()/use_deepseek()/use_deepseek_nvidia()
    (และ use_typhoon_v2() ใน run_stepic_report.py) เรียกตอน patch จริง เพื่อให้ manifest ของขั้นนี้
    บันทึกไว้ว่า "เผลอใช้โมเดลสำรอง" ตัวไหนบ้าง - ไม่ต้องรอ manifest write ตอนจบ ก็สะสมไว้ในตัวแปรนี้ก่อน"""
    _MODELS_USED_THIS_STAGE[model_name] = _MODELS_USED_THIS_STAGE.get(model_name, 0) + 1


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_stage_manifest():
    """atexit hook - เขียน/อัปเดต entry ของขั้นนี้ใน OUTPUTS/_manifest.json อัตโนมัติตอน interpreter จบ
    (ทั้งจบปกติ, sys.exit(), และ unhandled exception - เทสแล้วว่า atexit ยังทำงานทั้ง 3 กรณี) ไม่ต้องให้
    แต่ละสคริปต์เรียกเอง เพราะทุกขั้นของ v2 import bootstrap.py (โมดูลนี้) อยู่แล้วเป็นบรรทัดแรกๆ

    stage ที่ไม่อยู่ใน STAGE_IO_MAP (สคริปต์ทดลอง/legacy/pytest ฯลฯ) จะไม่ถูกบันทึก - กันไฟล์ manifest
    รกด้วยสคริปต์ที่ไม่ได้อยู่ใน main.py's STAGES จริง"""
    stage = Path(sys.argv[0]).stem
    if stage not in STAGE_IO_MAP:
        return
    io = STAGE_IO_MAP[stage]

    manifest_path = OUTPUTS / "_manifest.json"
    manifest = {}
    if manifest_path.exists():
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, OSError):
            manifest = {}

    input_hashes, input_warnings = {}, []
    for fname in io["inputs"]:
        fp = OUTPUTS / fname
        if not fp.exists():
            input_warnings.append(f"{fname}: ไม่เจอไฟล์ (ขั้นก่อนหน้ายังไม่ได้รันในรอบนี้)")
            continue
        try:
            actual_hash = _sha256_file(fp)
        except OSError:
            continue
        input_hashes[fname] = actual_hash
        # เทียบกับ hash ที่ขั้นที่เขียนไฟล์นี้ (หาจาก STAGE_IO_MAP) ประกาศไว้ตอนตัวเองเขียนเสร็จ - ถ้าไม่
        # ตรง แปลว่าไฟล์เปลี่ยนไปหลังจากนั้น (แก้มือ/มาจากคนละรอบ) ไม่ block แค่เตือน (ดูเหตุผลในเอกสาร)
        producer = next((s for s, v in STAGE_IO_MAP.items() if fname in v["outputs"]), None)
        if producer and producer in manifest:
            expected_hash = manifest[producer].get("output_hashes", {}).get(fname)
            if expected_hash and expected_hash != actual_hash:
                input_warnings.append(
                    f"{fname}: hash ไม่ตรงกับตอน '{producer}' เขียนไว้ล่าสุด (ไฟล์เปลี่ยนหลังจากนั้น) "
                    f"expected={expected_hash[:12]} actual={actual_hash[:12]}"
                )

    output_hashes = {}
    for fname in io["outputs"]:
        fp = OUTPUTS / fname
        if fp.exists():
            try:
                output_hashes[fname] = _sha256_file(fp)
            except OSError:
                pass

    manifest[stage] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "run_id": os.environ.get("TREND_RUN_ID", ""),
        "topic": os.environ.get("TREND_TOPIC", ""),
        "years": os.environ.get("TREND_YEARS", ""),
        "models_used": dict(_MODELS_USED_THIS_STAGE),
        "input_hashes": input_hashes,
        "output_hashes": output_hashes,
        "input_warnings": input_warnings,
    }
    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    except OSError:
        return

    if input_warnings:
        print(f"\n⚠️  [manifest] {stage}: พบปัญหา reproducibility {len(input_warnings)} จุด "
              f"(ดู {manifest_path.name}):")
        for w in input_warnings:
            print(f"   - {w}")


atexit.register(_write_stage_manifest)


def prompt_run_config(default_topic="beauty and personal care trends", default_years=3,
                       ask_years=False):
    """ถาม topic (+ จำนวนปีคาดการณ์ ถ้า ask_years=True) จากผู้ใช้ตอนรันสคริปต์

    ลำดับการหาค่า (ทั้ง topic และ years):
      1. env var  (TREND_TOPIC / TREND_YEARS)  — สำหรับรัน non-interactive / background job
      2. input()  — ถ้ารันแบบ interactive (มี TTY)
      3. default  — ถ้า input ว่าง หรือ EOF/OSError (เช่นรันใน background ที่ stdin ปิด)

    คืน (topic: str, horizon_months: int)  โดย horizon_months = years * 12
    (ask_years=False → horizon_months = default_years*12 เสมอ ไม่ถาม — สาย stream ไม่ได้ใช้ค่านี้)
    """
    topic = (os.getenv("TREND_TOPIC") or "").strip()
    if not topic:
        try:
            topic = input(f"📝 หัวข้อที่ต้องการวิเคราะห์เทรนด์ [{default_topic}]: ").strip()
        except (EOFError, OSError):
            topic = ""
    topic = topic or default_topic

    years = default_years
    if ask_years:
        raw = (os.getenv("TREND_YEARS") or "").strip()
        if not raw:
            try:
                raw = input(f"📅 คาดการณ์ล่วงหน้ากี่ปี [{default_years}]: ").strip()
            except (EOFError, OSError):
                raw = ""
        if raw:
            try:
                years = max(1, int(raw))
            except ValueError:
                print(f"  ⚠️ '{raw}' ไม่ใช่จำนวนเต็ม - ใช้ default {default_years} ปี")

    print(f"  ▶ หัวข้อ: '{topic}'" + (f"  |  คาดการณ์ {years} ปี ({years * 12} เดือน)" if ask_years else ""))
    return topic, years * 12


# ---------------------------------------------------------------------------
# 🆕 (2026-09-16) Top N เทรนด์ที่ใช้ต่อหลังพยากรณ์ - เจ้าของงานเลือกทาง B: ①-⑦ และ ⑥ ยังทำครบทุกเทรนด์
# (สายละ 5 = 15) เพราะต้องพยากรณ์ก่อนถึงจะรู้ว่าเทรนด์ไหนมาแรง แล้วตั้งแต่ ⑪ เป็นต้นไป (⑪ ⑫ ⑬ รายงาน
# และ bump chart ใน trend.ipynb) ใช้เฉพาะ N อันดับแรกตาม Rank Score ของ ⑥ (Z_Delta + โบนัสยืนยันข้ามสาย)
# ชุดเดียวกันทั้งหมด - เดิมรายงานใช้ทั้ง 15 ส่วน notebook คัด 10 ตัวด้วยอันดับ z-score ปีสุดท้าย ตรงกันแค่
# 6/10 (ตรวจกับรอบ 2026-09-16) เลยต้องมีเกณฑ์คัดเดียวที่ทุกขั้นเรียกใช้ร่วมกัน
# ---------------------------------------------------------------------------
TOP_N_TRENDS_DEFAULT = 10
RANK_SCORE_FILE = "phase2_rank_score_final_mode_result.json"


def get_top_n_trends():
    """จำนวนเทรนด์ที่ใช้ต่อหลังพยากรณ์ - อ่านจาก env TREND_TOP_N (main.py ถามแล้วตั้งให้ทุกขั้น) ไม่มีหรือ
    ไม่ใช่จำนวนเต็มบวก = TOP_N_TRENDS_DEFAULT (รันสคริปต์เดี่ยวๆ ก็ได้ค่าเดียวกับค่าเริ่มต้นของ main.py)"""
    raw = (os.getenv("TREND_TOP_N") or "").strip()
    if not raw:
        return TOP_N_TRENDS_DEFAULT
    try:
        n = int(raw)
    except ValueError:
        n = 0
    if n < 1:
        print(f"  ⚠️ TREND_TOP_N='{raw}' ไม่ใช่จำนวนเต็มบวก - ใช้ค่าเริ่มต้น {TOP_N_TRENDS_DEFAULT}")
        return TOP_N_TRENDS_DEFAULT
    return n


def load_ranked_trends(rank_path=None):
    """ทุกเทรนด์จากผล ⑥ (rank_trends.py) เรียงตาม Overall Rank - คืน list:
    [{"overall_rank", "stream", "trend", "rank_score", "z_delta", "mode"}, ...]

    ไม่มีไฟล์ของ ⑥ = หยุดพร้อมบอกให้รัน ⑥ ก่อน (ไม่แอบกลับไปใช้ทุกเทรนด์เงียบๆ เพราะผลจะไม่ตรงกับที่
    ผู้ใช้ตั้ง N ไว้)"""
    path = Path(rank_path) if rank_path else OUTPUTS / RANK_SCORE_FILE
    if not path.exists():
        raise SystemExit(f"❌ ไม่มี {path.name} - ต้องรัน ⑥ rank_trends.py ก่อน (ใช้คัด Top N เทรนด์)")
    with open(path, encoding="utf-8") as f:
        rows = sorted(json.load(f), key=lambda r: r["Overall Rank"])
    if not rows:
        raise SystemExit(f"❌ {path.name} ไม่มีเทรนด์เลย - ตรวจผล ⑥ ก่อน")
    return [{"overall_rank": int(r["Overall Rank"]), "stream": r["Stream"], "trend": r["Trend Name"],
             "rank_score": r.get("Rank Score"), "z_delta": r.get("Z_Delta"), "mode": r.get("Mode")}
            for r in rows]


def select_top_trends(n=None, rank_path=None):
    """เทรนด์ N อันดับแรกตาม Rank Score ของ ⑥ (ยังไม่ได้ดูว่ามีข้อมูลให้จับคู่สินค้าไหม - ⑪ ใช้
    collect_top_n_with_matchable_data() แทนเพื่อข้ามตัวที่ข้อมูลไม่พอ) - ถ้า N มากกว่าจำนวนเทรนด์ที่มีจะคืน
    ทั้งหมดพร้อมบอก, ถ้าอันดับยังเป็นโหมด preliminary (ไม่มี Z_Delta จริง) จะเตือนให้เห็น"""
    n = n or get_top_n_trends()
    ranked = load_ranked_trends(rank_path)
    if n > len(ranked):
        print(f"  ℹ️ ขอ Top {n} แต่มีเทรนด์ทั้งหมด {len(ranked)} ตัว - ใช้ทั้งหมด")
    picked = ranked[:n]
    preliminary = [r["trend"] for r in picked if not str(r.get("mode") or "").startswith("final")]
    if preliminary:
        print(f"  ⚠️ {len(preliminary)} เทรนด์ใน Top {n} ยังจัดอันดับแบบ preliminary (ไม่มี Z_Delta จริง ใช้ขนาด"
              f"คลัสเตอร์แทน): {preliminary}")
    return picked


def collect_top_n_with_matchable_data(ranked, make_profile, exclusion_reason, n):
    """🆕 (2026-09-16) เดินตามอันดับ (ranked จาก load_ranked_trends) สร้างจุดเด่นทีละเทรนด์ด้วย
    make_profile(item) แล้วเก็บเฉพาะตัวที่ exclusion_reason(profile) คืน None จนได้ครบ n ก็หยุด (ไม่เรียก
    LLM เกินจำเป็น) - exclusion_reason คืนข้อความเหตุผลถ้าไม่ควรนับเข้า Top N - เจ้าของงานเลือก: เทรนด์ที่
    จับคู่สินค้าไม่ได้ (⑪ ระบุว่าเป็นประเภทช่องทาง/พฤติกรรมการซื้อ หรือข้อมูลไม่พอทุกช่องที่ใช้จับคู่) ไม่นับเข้า
    Top N แล้วเลื่อนอันดับถัดไปขึ้นมาแทน ให้รายงาน/กราฟได้ N ตัวที่จับคู่สินค้าได้ครบทุกตัว

    ตัดสินจากผลของ ⑪ ไม่ใช่จากช่องส่วนผสม/ประโยชน์ของข้อมูลต้นทางที่ว่าง - ตรวจกับรอบ 2026-09-16 แล้ว
    ถ้าใช้ช่องต้นทางจะตัดอันดับ 1 (Pregnancy-Safe Dermocosmetics) ทิ้งผิดๆ ทั้งที่ ⑪ สกัดจุดเด่นจากช่อง
    กลุ่มเป้าหมายได้และจับคู่สินค้าได้จริง

    make_profile ที่ raise = ล้มเหลวทางเทคนิค เก็บลง failed แยกจาก excluded (ไม่ใช่ "ข้อมูลไม่พอ") -
    ผู้เรียกควรหยุดให้รันใหม่ เพราะถ้าปล่อยผ่าน ชุด Top N จะเปลี่ยนเพราะ error ชั่วคราวไม่ใช่เพราะข้อมูล

    คืน (selected, profiles, excluded, failed) - selected/excluded/failed เป็น item จาก ranked"""
    selected, profiles, excluded, failed = [], [], [], []
    for item in ranked:
        if len(selected) >= n:
            break
        try:
            profile = make_profile(item)
        except Exception as e:
            failed.append({**item, "error": str(e)[:300]})
            continue
        reason = exclusion_reason(profile)
        if reason:
            excluded.append({**item, "reason": reason})
            continue
        # top_rank = อันดับภายในชุด Top N (1..N) ใช้แสดงผลทุกที่ - overall_rank ยังเก็บอันดับเดิมจาก ⑥ ที่จัดกับ
        # ทุกเทรนด์ไว้ตรวจย้อน (เมื่อมีตัวถูกข้าม เลข overall_rank จะกระโดด เช่น 1,2,3,5,...,11 จึงไม่ควรเอาไปแสดง)
        selected.append({**item, "top_rank": len(selected) + 1})
        profiles.append(profile)
    return selected, profiles, excluded, failed


class use_typhoon:
    """Context manager สลับ tf.client/tf.MODEL_NAME/tf.MODEL_NAME_META ไปเป็น Typhoon ชั่วคราว

    ทำไมต้องมี: OpenRouter credit หมด (2026-08-28) - Typhoon เป็น endpoint แบบ OpenAI-compatible
    เหมือนกัน (ดู TYPHOON_BASE_URL/TYPHOON_API_KEY/TYPHOON_MODEL ที่เตรียมช่องไว้ใน .env อยู่แล้ว
    แต่ไม่เคยถูกใช้จริง) - ฟังก์ชันใน trend_final.py เรียก client/MODEL_NAME/MODEL_NAME_META แบบ
    bare name จาก __globals__ ของโมดูลตัวเอง เหมือนกับ safe_json_parse ด้านบน - สลับตรงนี้ทีเดียว
    จึงพอสำหรับทุกฟังก์ชันที่ใช้ร่วมโดยไม่ต้องเขียนใหม่ และคืนค่าเดิมให้อัตโนมัติตอนออกจาก `with`

    ⚠️ ต้อง patch ทั้ง MODEL_NAME และ MODEL_NAME_META - เจอบั๊กจริงตอนรัน Phase 2 สาย Social
    (2026-08-28): patch แค่ MODEL_NAME_META ตัวเดียวตอนแรก แล้ว extract_strategic_keywords/
    summarize_trend_clusters ผ่านได้ปกติ (ใช้ MODEL_NAME_META) แต่ generate_trend_report_with_llm()
    ใช้ตัวแปรคนละตัว (`model=MODEL_NAME`) ยังชี้ไปที่โมเดล OpenRouter เดิมอยู่ พอยิงผ่าน Typhoon client
    เลยได้ "Error code: 400 - Model not found" ทันที (ค่าเดิม MODEL_NAME/MODEL_NAME_META ใน .env
    เท่ากันอยู่แล้วโดยบังเอิญ เลยไม่เคยเห็นความต่างของตัวแปรทั้งสองมาก่อน)

    วิธีใช้:
        with use_typhoon():
            df_keywords = tf.extract_strategic_keywords(df_trends)
    """

    def __enter__(self):
        import os
        from openai import OpenAI

        base_url = os.getenv("TYPHOON_BASE_URL")
        api_key = os.getenv("TYPHOON_API_KEY")
        model = os.getenv("TYPHOON_MODEL")
        if not (base_url and api_key and model):
            raise RuntimeError(
                "TYPHOON_BASE_URL / TYPHOON_API_KEY / TYPHOON_MODEL ยังไม่ครบใน .env - "
                "เติมให้ครบก่อนใช้ use_typhoon()"
            )
        self._orig_client = tf.client
        self._orig_model_name = tf.MODEL_NAME
        self._orig_model_meta = tf.MODEL_NAME_META
        tf.client = OpenAI(base_url=base_url, api_key=api_key)
        tf.MODEL_NAME = model
        tf.MODEL_NAME_META = model
        print(f"  🌀 สลับไปใช้ Typhoon ชั่วคราว (model={model}, base_url={base_url})")
        record_model_used(model)  # 🆕 (2026-09-12, audit C5) - manifest ต้องรู้ว่าขั้นนี้ใช้ fallback
        return tf.client

    def __exit__(self, exc_type, exc_val, exc_tb):
        tf.client = self._orig_client
        tf.MODEL_NAME = self._orig_model_name
        tf.MODEL_NAME_META = self._orig_model_meta
        # 🆕 (2026-09-15) เดิม hardcode "สลับกลับเป็น OpenRouter แล้ว" เฉยๆ - ผิดตั้งแต่มี use_bedrock()
        # เพราะจุดที่เรียก use_typhoon() ซ้อนอยู่ใน use_bedrock() แล้วค่าที่คืนจริงคือ Bedrock ไม่ใช่
        # OpenRouter (ทำให้เจ้าของงานเข้าใจผิดว่ายังใช้ OpenRouter อยู่ตอนดู log จริง) - พิมพ์ชื่อโมเดลจริง
        # ที่กำลังคืนกลับไปแทน ตรงกับพฤติกรรมจริงเสมอไม่ว่าจะซ้อนอยู่ใน context ไหน
        print(f"  🌀 สลับกลับเป็นโมเดลเดิมแล้ว (model={self._orig_model_name})")
        return False


class use_nvidia:
    """Context manager สลับ tf.client/tf.MODEL_NAME/tf.MODEL_NAME_META ไปเป็น NVIDIA NIM ชั่วคราว

    ทำไมต้องมี: ทดสอบแล้ว (2026-08-28) ว่า Typhoon เอาตัวอย่างที่ฝังในพรอมต์ของ
    generate_trend_report_with_llm() (เช่น "CeraVe", "PDRN", "JK Beauty") ไปแต่งเป็นข้อค้นพบจริง
    ทั้งที่ไม่มีในข้อมูลเลย ต่างจาก GPT-5.6-Luna (โมเดลหลักผ่าน OpenRouter) ที่ปฏิเสธตัวอย่างพวกนี้ถูก
    ต้องเสมอ - ทดสอบ nvidia/nemotron-3-super-120b-a12b ด้วย prompt เดียวกันแล้วพบว่าปฏิเสธถูกต้อง
    เหมือน GPT-5.6-Luna จึงใช้เป็นตัวเลือกสำรองที่ปลอดภัยกว่า Typhoon สำหรับฟังก์ชันนี้โดยเฉพาะ

    NVIDIA_API ใช้กับ NIM catalog แบบ OpenAI-compatible ตรงๆ ที่ https://integrate.api.nvidia.com/v1
    (ต่างจาก ChatNVIDIA/langchain ที่ import ไว้ใน trend_final.py แต่ไม่เคยถูกใช้จริง - เป็นโค้ดตายจาก
    ตอนเปลี่ยนมาใช้ OpenRouter) เช็ค client.models.list() แล้วพบว่ารุ่นที่เคยรู้จัก (llama-3.1-70b-
    instruct ฯลฯ) ถูก NVIDIA เลิกให้บริการหมดแล้ว (410 Gone) ต้องดึงรายชื่อจริงมาดูก่อนเลือก

    🆕 (2026-09-10) รับ `model` param เลือกรุ่นได้ - default = super-120b (เดิม) / ใช้
    `NEMOTRON_ULTRA` (550b-a55b) สำหรับสาย News/Social เพราะ:
    - super-120b พัง summarize_trend_clusters (Longevity v2) JSON 5/5 - **ultra-550b ผ่าน**
    - deepseek-v4-pro (NVIDIA NIM) เจอ timeout roulette (127-300s+ แกว่ง, ~17% timeout แม้ prompt จิ๋ว)
      - ultra-550b เสถียร ~105-120s/call, รับ prompt ใหญ่ช็อตเดียว (ไม่ต้อง map-reduce)
    - anti-hallucination: ultra ดีกว่า super - เพิ่ม "Data Coverage Notice" ระบุสิ่งที่ไม่มีในข้อมูลเอง

    วิธีใช้: เหมือน use_typhoon() ทุกประการ
        with use_nvidia():                       # super-120b (default)
            df_keywords = tf.extract_strategic_keywords(df_trends)
        with use_nvidia(model=NEMOTRON_ULTRA):   # ultra-550b
            result = run_news_stream(topic=topic)
    """

    MODEL = "nvidia/nemotron-3-super-120b-a12b"
    BASE_URL = "https://integrate.api.nvidia.com/v1"

    def __init__(self, model=None, timeout=300):
        self.model = model or self.MODEL
        self.timeout = timeout

    def __enter__(self):
        import os
        from openai import OpenAI

        api_key = os.getenv("NVIDIA_API")
        if not api_key:
            raise RuntimeError("NVIDIA_API ยังไม่มีใน .env")
        self._orig_client = tf.client
        self._orig_model_name = tf.MODEL_NAME
        self._orig_model_meta = tf.MODEL_NAME_META
        tf.client = OpenAI(base_url=self.BASE_URL, api_key=api_key, timeout=self.timeout,
                           max_retries=1)
        tf.MODEL_NAME = self.model
        tf.MODEL_NAME_META = self.model
        print(f"  🟩 สลับไปใช้ NVIDIA NIM ชั่วคราว (model={self.model})")
        record_model_used(self.model)  # 🆕 (2026-09-12, audit C5)
        return tf.client

    def __exit__(self, exc_type, exc_val, exc_tb):
        tf.client = self._orig_client
        tf.MODEL_NAME = self._orig_model_name
        tf.MODEL_NAME_META = self._orig_model_meta
        print("  🟩 สลับกลับเป็น OpenRouter แล้ว")
        return False


# nemotron ตัวใหญ่ - ใช้กับสาย News/Social (Longevity v2 JSON ผ่าน + เสถียรกว่า deepseek NVIDIA NIM)
NEMOTRON_ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"


class use_gemini:
    """Context manager สลับ tf.client/tf.MODEL_NAME/tf.MODEL_NAME_META ไปเป็น Gemini (Google AI Studio) ชั่วคราว

    ทำไมต้องมี: `select_top_news()` (ข้อ 13/22 ใน Backlog) พังกับ NVIDIA nemotron เพราะโมเดลตอบ
    chain-of-thought ยาวปนอยู่ใน content เดียวกับ JSON แล้วโดน max_tokens ตัดก่อนถึง JSON จริง -
    เจ้าของงานยืนยันแล้วว่าไม่แก้โครงสร้าง select_top_news (ถูกต้องอยู่แล้ว ปัญหาคือพฤติกรรมโมเดล)
    จึงลองเปลี่ยนโมเดลแทน - ใช้ endpoint แบบ OpenAI-compatible ของ Google
    (https://generativelanguage.googleapis.com/v1beta/openai/) เสียบเข้า pattern เดียวกับ
    use_typhoon()/use_nvidia() ได้ตรงๆ

    GEMINI_KEY ต้องเป็น API key จริงจาก https://aistudio.google.com/apikey (ขึ้นต้น "AIzaSy...")
    ไม่ใช่ Project ID ที่ Google สร้างอัตโนมัติให้ (ขึ้นต้น "gen-lang-client-...") - เจอเคสใส่ผิดจริง
    ตอนตั้งค่าครั้งแรก (2026-08-31) ทดสอบยิง client.models.list() แล้วได้ 400 Please pass a valid
    API key จนกว่าจะเปลี่ยนเป็นคีย์จริง

    ⚠️ พบด้วยว่าโมเดลนี้เปิด "thinking" (reasoning) อัตโนมัติ กิน token ไปกับการคิดที่มองไม่เห็นก่อน
    แล้วค่อยตอบ JSON จริง - ทดสอบกับ pool 30 รายการจริงแล้วพบว่า max_tokens=500 ธรรมดาไม่พอ
    (thinking กิน ~480/500 token จนเหลือแค่ ~11 token ให้ JSON จริง ตอบมาไม่ครบ finish_reason="length")
    แก้ได้ด้วยการส่ง extra_body={"reasoning_effort": "none"} ตอนเรียก chat.completions.create -
    ทดสอบซ้ำแล้วได้ JSON ครบสะอาด finish_reason="stop" เลือกข่าวถูกต้อง 8/8 - **ต้องใส่พารามิเตอร์นี้
    เองตรงจุดที่เรียก ไม่ได้ผูกไว้ใน context manager นี้** เพราะเป็นพารามิเตอร์เฉพาะของ Gemini
    ไม่รับประกันว่า provider อื่น (Typhoon/NVIDIA/OpenRouter) จะไม่ error ถ้าได้รับ extra_body นี้ไปด้วย

    วิธีใช้: เหมือน use_typhoon()/use_nvidia() ทุกประการ (แต่ถ้าเรียกฟังก์ชันที่ต้องการ JSON แบบสั้น
    เช่น select_top_news ให้ส่ง extra_body={"reasoning_effort": "none"} เพิ่มเองตรงจุดเรียก)
        with use_gemini():
            df_keywords = tf.extract_strategic_keywords(df_trends)
    """

    # "gemini-flash-latest" ชี้ไปที่ gemini-3.7-flash (รุ่นล่าสุด) - free tier ของรุ่นล่าสุดจำกัดแค่
    # 20 request/วัน/โปรเจกต์/โมเดล (เจอจริง 2026-08-31 ตอนรัน News-Intl โดนโควตาหมดจากการทดสอบ)
    # ใช้ gemini-2.5-flash แทน (รุ่นก่อนหน้า โควตาแยกคนละก้อน ยังไม่โดนใช้ระหว่างทดสอบ)
    MODEL = "gemini-2.5-flash"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

    def __enter__(self):
        import os
        from openai import OpenAI

        api_key = os.getenv("GEMINI_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_KEY ยังไม่มีใน .env")
        self._orig_client = tf.client
        self._orig_model_name = tf.MODEL_NAME
        self._orig_model_meta = tf.MODEL_NAME_META
        tf.client = OpenAI(base_url=self.BASE_URL, api_key=api_key)
        tf.MODEL_NAME = self.MODEL
        tf.MODEL_NAME_META = self.MODEL
        print(f"  💎 สลับไปใช้ Gemini ชั่วคราว (model={self.MODEL})")
        record_model_used(self.MODEL)  # 🆕 (2026-09-12, audit C5)
        return tf.client

    def __exit__(self, exc_type, exc_val, exc_tb):
        tf.client = self._orig_client
        tf.MODEL_NAME = self._orig_model_name
        tf.MODEL_NAME_META = self._orig_model_meta
        print("  💎 สลับกลับเป็น OpenRouter แล้ว")
        return False


def strip_gemma_thought(content):
    r"""ตัด <thought>...</thought> ที่ Gemma ฝังมาก่อนคำตอบจริงเสมอออก - **ต้องเรียกก่อน
    safe_json_parse ทุกครั้ง** เวลาใช้กับ Gemma (ดู use_gemma() ด้านล่างสำหรับเหตุผลเต็ม)

    ⚠️ บั๊กจริงที่พบและแก้ (2026-09-01): ถ้าไม่ตัด <thought> ออกก่อน `safe_json_parse`'s regex fallback
    (`re.search(r"(\{.*\}|\[.*\})", content, re.DOTALL)`) จะ greedy match จาก "{" ตัวแรกในความคิด (ที่
    Gemma มักร่าง JSON ตัวอย่าง/draft ไว้ข้างในระหว่างคิดด้วย) ไปจนถึง "}" ตัวสุดท้ายในคำตอบจริง ทำให้
    parse ผิดหรือได้ JSON ที่เป็นแค่ draft ไม่ใช่คำตอบสุดท้าย - ทดสอบยืนยันแล้วว่าเกิดขึ้นจริงกับ prompt
    ที่ให้โมเดลคิดหลายมุมก่อนสรุปคำตอบ (เช่น สร้างคำค้นหลายแบบ)
    """
    if not content:
        return content
    idx = content.find("</thought>")
    if idx != -1:
        return content[idx + len("</thought>"):].strip()
    return content


class use_gemma:
    """Context manager สลับ tf.client/tf.MODEL_NAME/tf.MODEL_NAME_META ไปเป็น Gemma 4 26B-A4B ชั่วคราว

    ทำไมต้องมี: เจ้าของงานอยากลดต้นทุนจุดที่ "ไม่ต้องวิเคราะห์" (แตกคำค้น, สกัด triplet, แตกคีย์เวิร์ด -
    งานเชิงกลไก ไม่ใช่งานสังเคราะห์อิสระที่เสี่ยงหลอนแบบ generate_trend_report) ด้วยโมเดลเล็กกว่า
    GPT-5.6-Luna - ทดสอบ Gemma 4 E2B ตามที่เสนอมาก่อน แต่ **ไม่มีให้ใช้ผ่าน Google AI Studio API เลย**
    (เช็คด้วย client.models.list() มีแค่ gemma-4-26b-a4b-it กับ gemma-4-31b-it - E2B น่าจะออกแบบมา
    สำหรับรันบนเครื่อง/edge device โดยเฉพาะ ไม่เปิดผ่าน cloud API ของ Google) เจ้าของงานเลือกใช้
    26B-A4B แทน (MoE จริงแค่ ~4B parameter ตอน inference คล้าย Typhoon's A3B) ผ่าน GEMINI_KEY เดิม
    ไม่ต้องหา key/provider ใหม่เลย

    ⚠️ พบด้วยว่า Gemma มี "thinking" ฝังในตัว **ปิดไม่ได้เลย** (ต่างจาก Gemini) - ทดสอบส่ง
    `extra_body={"reasoning_effort": "none"}` แบบเดียวกับที่ใช้กับ Gemini แล้วได้ error ตรงๆ:
    `400 - Thinking budget is not supported for this model` - ความคิดออกมาเป็นข้อความ
    `<thought>...</thought>` ฝังอยู่ใน content ตรงๆ (ไม่ใช่ hidden token แบบ Gemini) ตามด้วยคำตอบจริง
    ทดสอบแล้วว่าต้องให้ max_tokens กว้างพอ (300+ แม้กับคำตอบสั้นๆ) ไม่งั้นโดนตัดกลางความคิดก่อนถึง
    คำตอบจริงเหมือนปัญหาเดิมที่เจอกับ Gemini/NVIDIA (ดู use_gemini() ด้านบน)

    **ต้องเรียก `strip_gemma_thought(content)` ก่อน `safe_json_parse` เสมอ** - ไม่งั้นเสี่ยงได้ JSON
    ร่างจากข้างในความคิดแทนคำตอบจริง (ดู docstring ของ strip_gemma_thought ด้านบน)

    วิธีใช้: เหมือน use_typhoon()/use_gemini() แต่ต้อง strip thought ก่อน parse เสมอ
        with use_gemma():
            response = tf.client.chat.completions.create(
                model=tf.MODEL_NAME_META, messages=[...], max_tokens=600,
                response_format={"type": "json_object"},
            )
            data = safe_json_parse(strip_gemma_thought(response.choices[0].message.content))
    """

    MODEL = "gemma-4-26b-a4b-it"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

    def __enter__(self):
        import os
        from openai import OpenAI

        api_key = os.getenv("GEMINI_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_KEY ยังไม่มีใน .env")
        self._orig_client = tf.client
        self._orig_model_name = tf.MODEL_NAME
        self._orig_model_meta = tf.MODEL_NAME_META
        # timeout=120: เจอจริง (2026-09-01) ว่า client default timeout สั้นเกินสำหรับ Gemma บางครั้ง -
        # <thought> ที่ยาวไม่แน่นอนทำให้บาง request ใช้เวลานานกว่าปกติ ("Request timed out" 2 รอบติด
        # กับ batch ที่มี system prompt ยาว) ทดสอบแยกด้วย timeout=90 ผ่านใน 12.7s ปกติ - ให้ margin เผื่อ
        tf.client = OpenAI(base_url=self.BASE_URL, api_key=api_key, timeout=120)
        tf.MODEL_NAME = self.MODEL
        tf.MODEL_NAME_META = self.MODEL
        print(f"  🪶 สลับไปใช้ Gemma ชั่วคราว (model={self.MODEL})")
        record_model_used(self.MODEL)  # 🆕 (2026-09-12, audit C5)
        return tf.client

    def __exit__(self, exc_type, exc_val, exc_tb):
        tf.client = self._orig_client
        tf.MODEL_NAME = self._orig_model_name
        tf.MODEL_NAME_META = self._orig_model_meta
        print("  🪶 สลับกลับเป็น OpenRouter แล้ว")
        return False


class use_deepseek:
    """Context manager สลับ tf.MODEL_NAME/tf.MODEL_NAME_META ไปเป็น DeepSeek (ผ่าน OpenRouter เดิม) ชั่วคราว

    ทำไมต้องมี: เจ้าของงานอยากลดต้นทุนจุด "ไม่ต้องวิเคราะห์" ต่อ (ข้อ 4 ในแผน optimize) ด้วยโมเดลถูก
    กว่า Typhoon/Gemma อีก - เช็คราคาจริงจาก OpenRouter public models endpoint (ไม่ต้องมี credit ก็ดู
    ได้) พบว่า `deepseek/deepseek-v4-flash-0731` ถูกมาก: input $0.065/1M, output $0.18/1M (ถูกกว่า
    GPT-5.6-Luna ที่ $0.20/$1.20 ต่อ 1M ประมาณ 3-7 เท่า) แถม context window ใหญ่ถึง 1.31M token

    **เลือก `-0731` (รุ่นปักหมุดวันที่) แทน `deepseek-v4-flash-latest`** (มี `~` นำหน้าใน listing =
    alias ไม่ปักหมุดรุ่น) - บทเรียนจาก Gemini "gemini-flash-latest" ที่ชี้ไปรุ่นล่าสุดเสมอแล้วโควตา
    หมดเร็วกว่ารุ่นปักหมุด (ดู use_gemini() ด้านบน) แม้ OpenRouter จะคิดราคาต่างจาก free-tier quota
    ของ Google ก็ตาม แต่หลักการเดียวกัน (ปักหมุดรุ่น = คาดเดาพฤติกรรมได้แน่นอนกว่า)

    ⚠️ **ยังไม่เคยทดสอบจริง** (2026-09-01) - OpenRouter credit ยังไม่พอยิงตอนที่เขียนโค้ดนี้ (เจ้าของงาน
    ยืนยันว่ายังไม่เติม) เขียนไว้พร้อมใช้ทันทีที่มีเครดิต - ยังไม่รู้ว่ามีพฤติกรรม "thinking" ฝังแบบ
    Gemini/Gemma หรือไม่ (DeepSeek มีทั้งสาย R1 ที่คิดออกเสียงชัดเจน กับสาย V3/V4-flash ที่ไม่ใช่ reasoning
    model โดยดีไซน์ - เลือก v4-flash เพราะไม่ใช่สาย R1 แต่ยังไม่ได้ verify ด้วยการยิงจริง) **ต้องทดสอบ
    แบบเดียวกับ Typhoon/Gemini/Gemma ก่อนใช้งานจริงเสมอ** (ดูว่า JSON ออกสะอาดไหม, มี thought แฝงไหม)

    วิธีใช้: เหมือน use_typhoon() แต่ base_url เดิม (OpenRouter) ไม่ต้องเปลี่ยน client เลย แค่เปลี่ยน model
        with use_deepseek():
            df_keywords = tf.extract_strategic_keywords(df_trends)
    """

    MODEL = "deepseek/deepseek-v4-flash-0731"

    def __enter__(self):
        self._orig_model_name = tf.MODEL_NAME
        self._orig_model_meta = tf.MODEL_NAME_META
        # ไม่ต้องสร้าง client ใหม่ - DeepSeek อยู่บน OpenRouter เดิม (base_url/api_key เดียวกับ
        # tf.client ที่มีอยู่แล้ว) แค่เปลี่ยนชื่อโมเดลที่ยิงไปพอ
        tf.MODEL_NAME = self.MODEL
        tf.MODEL_NAME_META = self.MODEL
        print(f"  🐋 สลับไปใช้ DeepSeek ชั่วคราว (model={self.MODEL}, ผ่าน OpenRouter เดิม)")
        record_model_used(self.MODEL)  # 🆕 (2026-09-12, audit C5)
        return tf.client

    def __exit__(self, exc_type, exc_val, exc_tb):
        tf.MODEL_NAME = self._orig_model_name
        tf.MODEL_NAME_META = self._orig_model_meta
        print("  🐋 สลับกลับเป็นโมเดลเดิมแล้ว")
        return False


class use_deepseek_nvidia:
    """Context manager สลับ tf.client/tf.MODEL_NAME/tf.MODEL_NAME_META ไปเป็น DeepSeek ผ่าน **NVIDIA
    NIM** ชั่วคราว - อย่าสับสนกับ use_deepseek() ด้านบน (คนละ deployment: นั่นคือ OpenRouter
    `deepseek/deepseek-v4-flash-0731` ยังไม่เคยทดสอบ ติดเครดิต OpenRouter ส่วนตัวนี้ผ่าน NVIDIA NIM
    ใช้ NVIDIA_API key เดิม ไม่ติดเครดิตอะไรเลย)

    ทำไมต้องมี: เจ้าของงานเสนอ `build.nvidia.com/deepseek-ai/deepseek-v4-pro-0813` (2026-09-09) - เช็ค
    จริงด้วย client.models.list() ผ่าน NVIDIA_API เดิม พบว่ามีจริง 3 ตัว: deepseek-v4-pro-0813,
    deepseek-v4-flash-0731, deepseek-coder-6.7b-instruct

    **⚠️ ห้ามใช้กับ generate_trend_report_with_llm() เด็ดขาด** - ทดสอบ anti-hallucination แบบเดียวกับ
    ที่ใช้คัดกรอง Typhoon/NVIDIA nemotron แล้ว (ป้อนข้อมูล scraped จริงที่ไม่มีคำว่า CeraVe/PDRN/JK
    Beauty/found & found/L'Oreal/La Roche-Posay เลย) **deepseek-v4-pro-0813 หลอนจริง** (แต่งคำเหล่านี้
    ใส่รายงานเอง 4 คำ) - ลองเพิ่มเกราะป้องกัน prompt แบบเข้มที่สุดแล้วก็ยังหลอน 3 คำ (ลดจาก 4) **ไม่ใช่
    ปัญหาที่แก้ด้วย prompt ได้ - เป็นข้อจำกัดความสามารถของโมเดล เหมือนที่สรุปไว้แล้วกับ NVIDIA nemotron/
    Typhoon (ข้อ 19)** ใช้ได้แค่กับงานที่ไม่ใช่การสังเคราะห์เรื่องเล่าจากตัวอย่างที่ฝังในพรอมต์ (เช่น
    extract_beauty_triplets, summarize_trend_clusters, extract_strategic_keywords, generate_th_queries)

    **ทดสอบ JSON compliance แล้ว** (deepseek-v4-pro-0813): ตอบ JSON สะอาด finish_reason=stop ไม่มี
    <thought> รั่วไหลใน content เหมือน Gemma/Gemini - ไม่ต้อง strip_gemma_thought() เลย

    ⚠️ **ช้ามาก** - ทดสอบแล้ว ~66-274 วินาที/call (prompt เล็กไปจนถึงใหญ่) คาดว่าเป็น reasoning ฝั่ง
    เซิร์ฟเวอร์ที่ไม่โชว์ใน content (คล้าย OpenAI o1-style) หรือคิว NVIDIA NIM community tier - ไม่เหมาะ
    กับงานที่ต้องยิงหลายครั้งติดกันเร็วๆ (เช่น select_top_news ที่มี retry loop) ใช้ได้ดีกับงานที่ยิง
    ไม่กี่ครั้ง/รอบ (ตั้งชื่อคลัสเตอร์ 5 ครั้ง, สกัด triplet 2-3 batch ฯลฯ) เท่านั้น

    วิธีใช้: เหมือน use_nvidia() ทุกประการ (base_url เดียวกัน คนละ model)
        with use_deepseek_nvidia():
            df_keywords = extract_strategic_keywords(df_trends)
    """

    MODEL = "deepseek-ai/deepseek-v4-pro-0813"
    BASE_URL = "https://integrate.api.nvidia.com/v1"

    def __enter__(self):
        import os
        from openai import OpenAI

        api_key = os.getenv("NVIDIA_API")
        if not api_key:
            raise RuntimeError("NVIDIA_API ยังไม่มีใน .env")
        self._orig_client = tf.client
        self._orig_model_name = tf.MODEL_NAME
        self._orig_model_meta = tf.MODEL_NAME_META
        # 🆕 (2026-09-10) max_retries=0 - เจอจริงว่า openai SDK default (max_retries=2) แอบ retry เอง
        # เงียบๆ เวลา timeout ทำให้ "fail" 1 ครั้งจริงๆ กินเวลา ~3x ของ timeout ที่ตั้งไว้ (300s เห็น
        # elapsed จริง ~900s ทั้ง pro และ flash) โดยไม่มี log ระหว่างทางเลย - ปิดตรงนี้แล้วให้
        # generate_trend_report_with_retry() ด้านล่างทำ retry เองแทน จะได้เห็น progress ทุกครั้ง
        tf.client = OpenAI(base_url=self.BASE_URL, api_key=api_key, timeout=300, max_retries=0)
        tf.MODEL_NAME = self.MODEL
        tf.MODEL_NAME_META = self.MODEL
        print(f"  🐋 สลับไปใช้ DeepSeek ผ่าน NVIDIA NIM ชั่วคราว (model={self.MODEL}, ช้า ~1-4 นาที/call)")
        record_model_used(self.MODEL)  # 🆕 (2026-09-12, audit C5)
        return tf.client

    def __exit__(self, exc_type, exc_val, exc_tb):
        tf.client = self._orig_client
        tf.MODEL_NAME = self._orig_model_name
        tf.MODEL_NAME_META = self._orig_model_meta
        print("  🐋 สลับกลับเป็นโมเดลเดิมแล้ว")
        return False


class _BedrockMessage:
    """เลียนแบบ openai SDK's response.choices[0].message (มีแค่ .content ที่ทุกจุดเรียกใช้จริง)"""
    def __init__(self, content):
        self.content = content


class _BedrockChoice:
    """เลียนแบบ openai SDK's response.choices[0]"""
    def __init__(self, content, finish_reason):
        self.message = _BedrockMessage(content)
        self.finish_reason = finish_reason


class _BedrockUsage:
    """เลียนแบบ openai SDK's response.usage (ใช้กับ tf.total_input_tokens/total_output_tokens ที่มีอยู่แล้ว)"""
    def __init__(self, input_tokens, output_tokens):
        self.prompt_tokens = input_tokens
        self.completion_tokens = output_tokens


class _BedrockResponse:
    """เลียนแบบ openai SDK's ChatCompletion object ทั้งก้อน - ให้ resp.choices[0].message.content /
    resp.usage.prompt_tokens ใช้งานได้เหมือนเดิมทุกจุดที่มีอยู่แล้วในโปรเจกต์ (ทั้ง trend_final.py/
    trend_final_v2.py) โดยไม่ต้องแก้โค้ดผู้เรียกแม้แต่บรรทัดเดียว"""
    def __init__(self, converse_resp):
        # 🆕 content เป็น list ของ block (text/toolUse/...) - งานทั้งหมดในโปรเจกต์นี้เป็น text ล้วน
        # เอาเฉพาะ block ที่มี "text" มาต่อกัน (ปกติจะมีแค่ 1 block พอดี)
        blocks = converse_resp.get("output", {}).get("message", {}).get("content", [])
        text = "".join(b.get("text", "") for b in blocks)
        finish_reason_map = {  # แปลง Bedrock's stopReason -> ค่าที่โค้ดเดิมคุ้นเคย (OpenAI-style)
            "end_turn": "stop", "max_tokens": "length", "stop_sequence": "stop",
        }
        stop_reason = converse_resp.get("stopReason", "end_turn")
        self.choices = [_BedrockChoice(text, finish_reason_map.get(stop_reason, stop_reason))]
        usage = converse_resp.get("usage", {})
        self.usage = _BedrockUsage(usage.get("inputTokens", 0), usage.get("outputTokens", 0))


# โมเดลแบบ reasoning คิดก่อนตอบ และนับการคิดรวมใน maxTokens - งบเล็ก (เช่น 30) หมดตอนคิดจนไม่มีข้อความ
# ตอบเลย (gpt-oss-120b ทดสอบจริง 2026-09-15: stop=max_tokens, มีแต่ reasoningContent) จึงเพิ่มงบคิดให้
_REASONING_MODEL_PREFIXES = ("openai.gpt-oss",)
_REASONING_TOKEN_ALLOWANCE = 1024


def _is_usable_json(text):
    parsed = safe_json_parse(text or "")
    return isinstance(parsed, (dict, list)) and bool(parsed)


class _BedrockCompletions:
    """เลียนแบบ openai SDK's client.chat.completions (มีแค่ .create ที่ทุกจุดเรียกใช้จริง) - แปลง
    OpenAI-style messages=[{"role":..., "content":...}] -> Bedrock Converse API format แล้วแปลงผลกลับ

    🆕 (2026-09-15) เรียกซ้ำอัตโนมัติ (ครอบคลุมทุกจุดที่เรียกผ่าน shim นี้ ไม่ต้องแก้ผู้เรียก):
    - ผู้เรียกขอ JSON (ส่ง response_format มา) แต่ได้ข้อความที่ parse ไม่ได้ -> เรียกโมเดลเดิมซ้ำ 1 ครั้ง
      (อาการตอบมั่วที่เจอในรอบรันจริงเป็นแบบนานๆ ครั้ง) ถ้ายังไม่ได้ -> โมเดลสำรอง
    - เรียก API พัง (boto3 retry ในตัวไปแล้ว) หรือได้ข้อความว่าง -> ข้ามไปโมเดลสำรองเลย
    - ถ้าทุกทางไม่ได้: คืนผลสุดท้ายให้ผู้เรียกจัดการแบบเดิม หรือ raise error ตัวสุดท้าย"""
    def __init__(self, bedrock_client, model_id, fallback_model_id=None):
        self._client = bedrock_client
        self._model_id = model_id
        self._fallback_model_id = fallback_model_id if fallback_model_id != model_id else None

    def _converse(self, model_id, messages, temperature, max_tokens):
        system_blocks = [{"text": m["content"]} for m in (messages or []) if m.get("role") == "system"]
        conv_messages = [
            {"role": m["role"], "content": [{"text": m["content"]}]}
            for m in (messages or []) if m.get("role") != "system"
        ]
        kwargs = {"modelId": model_id, "messages": conv_messages}
        if system_blocks:
            kwargs["system"] = system_blocks
        is_reasoning = model_id.startswith(_REASONING_MODEL_PREFIXES)
        inference_config = {}
        if max_tokens is not None:
            inference_config["maxTokens"] = max_tokens + (_REASONING_TOKEN_ALLOWANCE if is_reasoning else 0)
        if temperature is not None:
            inference_config["temperature"] = temperature
        if inference_config:
            kwargs["inferenceConfig"] = inference_config
        if is_reasoning:
            kwargs["additionalModelRequestFields"] = {"reasoning_effort": "low"}
        return _BedrockResponse(self._client.converse(**kwargs))

    def create(self, model=None, messages=None, temperature=None, max_tokens=None,
               response_format=None, **_ignored):
        wants_json = response_format is not None
        plan = [self._model_id] + ([self._model_id] if wants_json else [])
        if self._fallback_model_id:
            plan.append(self._fallback_model_id)

        last_resp, last_error, reason, prev = None, None, "", None
        for model_id in plan:
            if prev is not None:
                if last_error is not None and model_id == self._model_id:
                    continue
                print(f"  🔁 {prev}: {reason} -> เรียกซ้ำด้วย {model_id}")
                if model_id != self._model_id:
                    record_model_used(model_id)
            prev = model_id
            try:
                resp = self._converse(model_id, messages, temperature, max_tokens)
            except Exception as e:
                last_error, reason = e, type(e).__name__
                continue
            last_error = None
            text = resp.choices[0].message.content
            if not text.strip():
                last_resp, reason = resp, "ได้ข้อความว่าง"
                continue
            if wants_json and not _is_usable_json(text):
                last_resp, reason = resp, "JSON ใช้ไม่ได้"
                continue
            return resp

        if last_resp is not None:
            return last_resp
        raise last_error


class _BedrockChat:
    def __init__(self, bedrock_client, model_id, fallback_model_id=None):
        self.completions = _BedrockCompletions(bedrock_client, model_id, fallback_model_id)


class _BedrockClientShim:
    """ตัวห่อทั้งก้อนให้หน้าตาเหมือน openai.OpenAI object - มีแค่ .chat.completions.create ที่ทุกจุดใน
    โปรเจกต์นี้เรียกใช้จริง (ไม่ครอบคลุม .embeddings/.models ฯลฯ เพราะไม่มีใครเรียกผ่าน tf.client แบบนั้น)"""
    def __init__(self, bedrock_client, model_id, fallback_model_id=None):
        self.chat = _BedrockChat(bedrock_client, model_id, fallback_model_id)


class use_bedrock:
    """Context manager สลับ tf.client/tf.MODEL_NAME/tf.MODEL_NAME_META ไปเป็น AWS Bedrock ชั่วคราว
    - เหมือน use_typhoon()/use_nvidia()/use_gemini() ทุกประการจากมุมมองผู้เรียก (with use_bedrock(): ...)
    แต่ Bedrock ใช้ boto3 + AWS credentials (bearer token หรือ SigV4) ไม่ใช่ OpenAI-compatible REST เหมือน
    5 ตัวข้างบนเลย (ดู Detail/05 งานที่ยังไม่ได้ทำ/แผนเปลี่ยนโมเดล LLM — Bedrock + Typhoon.md ข้อ "สิ่งที่
    ต้องทำก่อนเริ่มลงมือจริง" ข้อ 1) จึงต้องมี shim (_BedrockClientShim ด้านบน) แปลง boto3's converse()
    ให้หน้าตาเหมือน openai SDK's chat.completions.create() ทุกจุดที่มีอยู่แล้วในโปรเจกต์ (tf.client.chat.
    completions.create(...) ใน trend_final.py/trend_final_v2.py หลายสิบจุด) จะได้ไม่ต้องแก้โค้ดผู้เรียก
    เลยสักบรรทัด เหมือนตอนสลับ Typhoon/NVIDIA/Gemini - เป็นหลักการเดียวกันทั้งไฟล์

    **โมเดล:** หลัก `MODEL_ID` = GLM-5, สำรอง `FALLBACK_MODEL_ID` = Mistral Large 3 (เรียกซ้ำ/สลับสำรองอัตโนมัติ
    ใน `_BedrockCompletions.create()`) - ประวัติการเลือก (2026-09-15): Claude Sonnet 5 (account ไม่มีสิทธิ์
    Anthropic) → DeepSeek V3.2 (ตอบมั่วเป็นครั้งคราวในรอบรันจริง) → GLM-5 จากเทสเทียบจริง ดู Detail/05 งาน
    ที่ยังไม่ได้ทำ/แผนเปลี่ยนโมเดล LLM — Bedrock + Typhoon.md หัวข้อ "เลือกโมเดล GLM-5" - สลับเฉพาะจุดได้ผ่าน
    `use_bedrock(model_id=...)`

    รองรับ auth 2 แบบ (ตรวจ .env ตามลำดับนี้ - ใช้แบบแรกที่เจอค่า):
    1) **AWS_BEARER_TOKEN_BEDROCK** - Bedrock API key แบบ bearer token (ขึ้นต้นด้วย "ABSK" = long-term
       API key ที่ผูกกับ IAM user ตัวเดียว, หรือ short-term ก็ได้) ยืนยันจากเอกสาร AWS จริงแล้ว
       (2026-09-15, https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-use.html): แค่ set เป็น
       environment variable ชื่อนี้ตรงๆ แล้ว boto3.client("bedrock-runtime", region_name=...) จะใช้ได้เลย
       โดยไม่ต้องส่ง aws_access_key_id/aws_secret_access_key เลย (คนละกลไกกับ SigV4 key pair ด้านล่าง)
    2) **AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY** - SigV4 key pair แบบดั้งเดิม (IAM user access key
       ปกติ ขึ้นต้นด้วย AKIA/ASIA ไม่ใช่ ABSK) เผื่อในอนาคตเปลี่ยนไปใช้แบบนี้แทน

    ต้องมีค่าจริงอย่างใดอย่างหนึ่งใน .env ก่อนใช้ (ยังไม่มีค่าจริงจนกว่าเจ้าของงานจะเอาคีย์มาวาง - เตรียม
    โค้ดไว้ให้พร้อมใช้ทันทีที่มีคีย์ ไม่ต้องแก้โค้ดอะไรเพิ่มแล้ว)

    วิธีใช้: เหมือน use_typhoon()/use_nvidia() ทุกประการ
        with use_bedrock():
            df_keywords = tf.extract_strategic_keywords(df_trends)
    """

    # 🆕 (2026-09-15) GLM-5 หลัก / Mistral Large 3 สำรอง (เดิม gpt-oss-120b) - เลือกจากเทสเทียบจริง ดูหัวข้อ
    # "เลือกโมเดล GLM-5" ใน Detail/05 งานที่ยังไม่ได้ทำ/แผนเปลี่ยนโมเดล LLM — Bedrock + Typhoon.md
    MODEL_ID = "zai.glm-5"
    FALLBACK_MODEL_ID = "mistral.mistral-large-3-675b-instruct"

    def __init__(self, model_id=None, region=None, module=None):
        self.model_id = model_id or self.MODEL_ID
        self.region = region or os.getenv("AWS_REGION") or "us-east-1"
        # 🆕 (2026-09-16) module: โมดูลที่จะแพตช์ (default = trend_final v1 ที่ tf ชี้ไป) - trend_final_v2 มี
        # client/MODEL_NAME ของตัวเองแยกกัน ต้องส่ง module=tf2 เช่น `with use_bedrock(module=tf2):` รอบ
        # forecast_trend() (Step 6-7 ข้างในเคยยิง OpenRouter ที่เครดิตหมด -> 402 ทุกรอบ)
        self.module = module or tf

    def __enter__(self):
        import boto3

        bearer_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")
        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

        if bearer_token:
            # 🆕 Bedrock API key (ABSK) - ต้อง set เป็น env var ชื่อนี้ตรงๆ ให้ boto3 มองเห็นเอง
            # (ไม่ใช่ parameter ที่ส่งเข้า boto3.client() ตรงๆ เหมือน access_key/secret_key)
            os.environ["AWS_BEARER_TOKEN_BEDROCK"] = bearer_token
            bedrock_client = boto3.client("bedrock-runtime", region_name=self.region)
        elif access_key and secret_key:
            bedrock_client = boto3.client(
                "bedrock-runtime", region_name=self.region,
                aws_access_key_id=access_key, aws_secret_access_key=secret_key,
            )
        else:
            raise RuntimeError(
                "ยังไม่มีคีย์ AWS Bedrock ใน .env - เติม AWS_BEARER_TOKEN_BEDROCK (คีย์ที่ขึ้นต้นด้วย "
                "ABSK) หรือ AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY ก่อนใช้ use_bedrock() "
                "(ดู Detail/05 งานที่ยังไม่ได้ทำ/แผนเปลี่ยนโมเดล LLM — Bedrock + Typhoon.md)"
            )
        m = self.module
        self._orig_client = m.client
        self._orig_model_name = m.MODEL_NAME
        self._orig_model_meta = m.MODEL_NAME_META
        m.client = _BedrockClientShim(bedrock_client, self.model_id, self.FALLBACK_MODEL_ID)
        m.MODEL_NAME = self.model_id
        m.MODEL_NAME_META = self.model_id
        record_model_used(self.model_id)
        print(f"  🟧 สลับไปใช้ AWS Bedrock ชั่วคราว (model={self.model_id}, region={self.region}, "
              f"module={m.__name__})")
        return m.client

    def __exit__(self, exc_type, exc_val, exc_tb):
        m = self.module
        m.client = self._orig_client
        m.MODEL_NAME = self._orig_model_name
        m.MODEL_NAME_META = self._orig_model_meta
        print("  🟧 สลับกลับเป็นโมเดลเดิมแล้ว")
        return False


def generate_trend_report_with_retry(topic, scraped_data, max_attempts=3):
    """wrapper รอบ tf.generate_trend_report_with_llm() - ใช้คู่กับ use_deepseek_nvidia() เท่านั้น
    (ต้องเรียกภายใน `with use_deepseek_nvidia():` เพราะพึ่ง max_retries=0 ที่ตั้งไว้ตรงนั้น)

    ทำไมต้องมี: เจอจริง (2026-09-10) ว่า pro-0813 สำเร็จแค่ ~40% ต่อการเรียก 1 ครั้ง (2/5 รอบทดสอบ) ที่
    เหลือ timeout ไปเงียบๆ - openai SDK default retry (max_retries=2) ทำให้แต่ละครั้งที่ fail กินเวลา
    ~900s โดยไม่มีสัญญาณอะไรระหว่างทางเลยว่ากำลังลองซ้ำอยู่ - ฟังก์ชันนี้ปิด SDK retry (ผ่าน
    use_deepseek_nvidia's max_retries=0) แล้วทำ retry เอง พร้อม log ให้เห็นทุกครั้งว่าลองรอบไหน
    ใช้เวลาเท่าไหร่ ไม่ใช่รอเงียบๆ ไม่รู้อะไรเลย

    **ข้อควรรู้:** นี่แก้ "การมองเห็น/ควบคุม" การ retry ได้จริง แต่ไม่ได้แก้ต้นตอความไม่เสถียรของคิว
    NVIDIA NIM community tier เอง (เป็นโครงสร้างพื้นฐานฝั่งเขา ควบคุมไม่ได้จากโค้ดเรา) - ถ้า 3 ครั้งยัง
    ไม่สำเร็จเลย โอกาสสูงว่าเป็นช่วงที่คิวหนักจริงๆ ไม่ใช่บั๊ก

    Returns: (report_str, n_attempts_used) - report_str = "" ถ้าล้มเหลวครบทุกรอบ
    """
    import time

    # เรียก _original_generate_trend_report (เก็บไว้ตอนโหลด module ก่อน monkey-patch) ไม่ใช่
    # tf.generate_trend_report_with_llm ตรงๆ - กัน recursion ถ้า runner patch ชื่อนั้นให้วิ่งผ่าน
    # wrapper ตัวนี้ (บทเรียนเดียวกับ _original_tf_safe_json_parse ด้านล่าง)
    for attempt in range(1, max_attempts + 1):
        print(f"  🔁 DeepSeek retry wrapper: attempt {attempt}/{max_attempts}...")
        t0 = time.time()
        try:
            report = _original_generate_trend_report(topic, scraped_data)
        except Exception as e:
            report = ""
            print(f"    ❌ exception: {e}")
        elapsed = time.time() - t0
        if report:
            print(f"    ✅ สำเร็จรอบที่ {attempt} ({elapsed:.1f}s)")
            return report, attempt
        print(f"    ❌ ล้มเหลว/timeout รอบที่ {attempt} ({elapsed:.1f}s)")

    print(f"  ❌ ล้มเหลวครบ {max_attempts} รอบ - ยอมแพ้")
    return "", max_attempts


def summarize_article_for_report(article, topic, max_chars=8000, max_attempts=3):
    """map step ของ generate_trend_report_mapreduce() - สรุป 1 บทความให้เหลือ ~250 คำ โดยยังเก็บ
    ข้อมูลที่ report ต้องใช้ครบ (เทรนด์/ส่วนผสม/pain point/market driver/ตัวเลข/ชื่อแบรนด์คัดลอกตรงตัว)

    เป็นงาน "สกัด" ไม่ใช่ "สังเคราะห์" - อยู่ในหมวดที่โปรเจกต์พิสูจน์แล้วว่าโมเดลรองไม่หลอน (เหมือน
    extract_beauty_triplets / extract_strategic_keywords) - prompt เขียนใหม่ ไม่มีตัวอย่างแบรนด์ฝัง
    กำชับให้คัดลอกชื่อแบรนด์ตรงตัวเท่านั้น เขียน 'none' ถ้าไม่มี

    ใช้ tf.client/tf.MODEL_NAME ปัจจุบัน (= DeepSeek เมื่ออยู่ใน use_deepseek_nvidia())

    คืน str (สรุป) หรือ "" ถ้าล้มเหลวครบทุกรอบ/บทความสั้นเกินไป
    """
    import time

    title = article.get("title", "")
    content = (article.get("content") or "")[:max_chars]
    if len(content) < 100:
        return ""

    system_prompt = (
        "You extract structured facts from a single trade/news article for later report synthesis. "
        "Output ONLY what is explicitly stated in the article text. Do NOT add outside knowledge, "
        "do NOT infer brands, numbers, or trends that aren't written. If a section has nothing, "
        "write 'none'."
    )
    user_prompt = f"""Article title: {title}

Article text:
{content}

Extract the following, staying strictly within the article text (topic context: "{topic}"):

KEY TRENDS: (what shifts/movements the article describes)
INGREDIENTS / FORMATS: (named ingredients, product formats, technologies)
CONSUMER NEEDS & PAIN POINTS: (what consumers want or struggle with, per the article)
MARKET DRIVERS: (economic, cultural, regulatory forces named)
BRANDS & PRODUCTS NAMED: (copy exact names verbatim; write 'none' if the article names no brand)
NUMBERS & STATISTICS: (copy figures verbatim with their context; 'none' if absent)

Keep the whole extraction under 250 words. Be terse."""

    for attempt in range(1, max_attempts + 1):
        t0 = time.time()
        try:
            resp = tf.client.chat.completions.create(
                model=tf.MODEL_NAME,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_prompt}],
                temperature=0.1, max_tokens=550,  # hard cap - DeepSeek ไม่เคารพ "under 250 words"
            )                                       # เจอจริงว่าสรุปยาว ~1,100 tokens/ชิ้น (Social 25 ชิ้น
                                                    # → reduce 27.6K timeout ครบ 3 รอบ)
            out = (resp.choices[0].message.content or "").strip()
            if out:
                print(f"      ✅ map: {title[:45]} ({time.time() - t0:.0f}s)")
                return out
            print(f"      ❌ map attempt {attempt}: empty ({time.time() - t0:.0f}s)")
        except Exception as e:
            print(f"      ❌ map attempt {attempt}: {str(e)[:80]} ({time.time() - t0:.0f}s)")
    return ""


def generate_trend_report_mapreduce(topic, scraped_data, max_attempts=3, min_articles=3):
    """report generation แบบ map-reduce - แก้ปัญหา prompt ใหญ่เกิน (News-Intl จริง ~56K tokens
    timeout 3/3 กับ DeepSeek ผ่าน NVIDIA NIM community tier - ดู Backlog ข้อ 35/36)

    map:    สรุปแต่ละบทความแยก (summarize_article_for_report, max_tokens=550 hard cap)
    reduce: เรียก report prompt ต้นฉบับ (_original_generate_trend_report - ไม่แตะ trend_final.py)
            ด้วย content = สรุป → prompt เล็กลงมาก
            - **≤ 8 สรุป: reduce ระดับเดียว** (News 7-9 สรุป = 12-14K ผ่าน)
            - **> 8 สรุป: 2-level reduce** (batch ละ 8 → mini-report → รวม mini-report)
              เจอจริง Social 25 สรุป → reduce ระดับเดียว 27.6K → DeepSeek timeout ครบ 3 รอบ

    รายงานที่ได้มีโครงสร้าง/ตัวอย่างเหมือน generate_trend_report_with_llm() เป๊ะ สลับกับ
    GPT-5.6-Luna ได้ - verify_report_against_source() ปลายทางยังเทียบกับข้อความต้นฉบับเต็มได้
    (เรียกด้วย scraped_data ตัวเต็ม ไม่ใช่สรุป)

    คืน str (รายงาน) หรือ "" ถ้า map สำเร็จ < min_articles หรือ reduce ล้มเหลวครบทุกรอบ
    """
    import time

    print(f"  🗺️  map-reduce report: สรุป {len(scraped_data)} บทความก่อน...")
    summaries = []
    for art in scraped_data:
        s = summarize_article_for_report(art, topic, max_attempts=max_attempts)
        if s:
            summaries.append({"title": art.get("title", ""), "content": s})
    print(f"  🗺️  map เสร็จ: {len(summaries)}/{len(scraped_data)} บทความสรุปสำเร็จ")
    if len(summaries) < min_articles:
        print(f"  ❌ map สำเร็จน้อยกว่า {min_articles} บทความ - ยกเลิก (รายงานจะบางเกินไป)")
        return ""

    def _reduce_once(t, items, label):
        for attempt in range(1, max_attempts + 1):
            print(f"    🔁 {label} attempt {attempt}/{max_attempts}...")
            t0 = time.time()
            try:
                out = _original_generate_trend_report(t, items)
            except Exception as e:
                out = ""
                print(f"      ❌ exception: {e}")
            elapsed = time.time() - t0
            if out:
                print(f"      ✅ {label} สำเร็จ ({elapsed:.0f}s)")
                return out
            print(f"      ❌ {label} ล้มเหลว/timeout ({elapsed:.0f}s)")
        return ""

    # 🆕 (2026-09-10) 2-level reduce ถ้า summary เยอะ - เจอจริงว่า Social 25 สรุป → reduce prompt
    # 27.6K → DeepSeek timeout ครบ 3 รอบ (News 7-9 สรุป = 12-14K ผ่าน) - แบ่งเป็น batch ละ 8 →
    # mini-report ต่อ batch → รวม mini-report เป็นรายงานสุดท้าย (แต่ละ call อยู่ในโซนปลอดภัย)
    BATCH = 8
    if len(summaries) <= BATCH:
        print(f"  🔗 reduce: สังเคราะห์รายงานจาก {len(summaries)} สรุป (level เดียว)...")
        return _reduce_once(topic, summaries, "reduce")

    n_batches = (len(summaries) + BATCH - 1) // BATCH
    print(f"  🔗 reduce 2 ระดับ: {len(summaries)} สรุป → {n_batches} batch (ละ ≤{BATCH}) → รวม...")
    partials = []
    for i in range(n_batches):
        chunk = summaries[i * BATCH:(i + 1) * BATCH]
        mini = _reduce_once(topic, chunk, f"batch {i + 1}/{n_batches}")
        if mini:
            partials.append({"title": f"Partial synthesis {i + 1}", "content": mini[:3000]})
    if not partials:
        print("  ❌ ไม่มี batch ไหนสำเร็จเลย - ยกเลิก")
        return ""
    if len(partials) == 1:
        return partials[0]["content"]
    print(f"  🔗 final reduce: รวม {len(partials)} partial report...")
    return _reduce_once(topic, partials, "final reduce")


def verify_report_against_source(report_text, scraped_data):
    """deterministic post-hoc verification - สแกนรายงานที่ LLM สร้าง หาคำ/วลีที่ดูเหมือนชื่อเฉพาะ
    (Title-Case 1-4 คำติดกัน) แล้วเช็คว่าปรากฏอยู่จริงในข้อมูลต้นทาง (scraped_data) แบบ verbatim ไหม -
    ไม่พึ่งพฤติกรรมโมเดลเลย ตรงปรัชญาเดียวกับที่โปรเจกต์นี้ใช้กับ investment_signal/E4 (โค้ดตัดสิน
    ไม่ใช่ LLM พูดเอง)

    ทำไมต้องมี: deepseek-v4-pro-0813 (ผ่าน NVIDIA NIM) ทดสอบแล้วว่าหลอนได้ (ดู use_deepseek_nvidia()
    docstring ด้านบน) เจ้าของงานขอให้หาวิธีแก้ (2026-09-09) - แก้ด้วยการตัดตัวอย่างออกจาก prompt เคยลอง
    แล้วและถูกยกเลิกไปแล้ว (Backlog ข้อ 19 - GPT-5.6-Luna ต้องการตัวอย่างเพื่อคุณภาพ, ห้ามแก้
    trend_final.py อยู่แล้วด้วย) จึงใช้ทางนี้แทน: ปล่อยให้โมเดลสร้างรายงานตามปกติ (prompt เดิมไม่แตะ
    เลย) แล้วตรวจสอบผลลัพธ์ย้อนหลังด้วยโค้ดแทน

    วิธีจัดการ false positive (สำคัญมาก - ทดสอบจริงแล้วว่าถ้าไม่กรองส่วนนี้ จะฟ้อง ~45 คำ/รายงาน ซึ่ง
    ส่วนใหญ่เป็นหัวข้อ/bold label ที่โมเดลสร้างเองตาม STYLE directive ไม่ใช่การหลอน):
    1. ตัดบรรทัด markdown heading (#, ##, ###) ออกก่อนสแกน - เป็นโครงสร้างที่ prompt สั่งเอง
    2. ตัดบรรทัดที่เป็น bold label ทั้งบรรทัด (เช่น "**Pillar 1: X**") ออก - โมเดลใช้เป็นหัวข้อย่อยเอง
       ตาม STYLE directive ("Strategic Pillars" ฯลฯ) ไม่ใช่ชื่อแบรนด์
    3. ข้าม single-word ที่เป็นคำศัพท์อังกฤษทั่วไป/คำเชื่อมต้นประโยค (stopword) - เกิดจาก sentence-initial
       capitalization ไม่ใช่ proper noun จริง
    4. ตัด possessive/plural suffix ('s, s) ก่อนเทียบกับ source - กัน false positive จาก morphological
       variant (เช่น "Ceramides" vs source's "ceramide-based")
    5. เช็ค negation context ระดับ "ประโยค" (ไม่ใช่ char-window ตายตัว - เจอจริงว่า trigger คำปฏิเสธ
       อาจอยู่ห่างเกิน 100 ตัวอักษรถ้าประโยคยกตัวอย่างหลายคำติดกัน เช่น "nor does it reference...
       like 'CeraVe' or 'La Roche-Posay'") - ถ้าทุกประโยคที่พูดถึงคำนี้มีคำปฏิเสธ ถือว่าปลอดภัย

    ทดสอบจริง (2026-09-09): รันกับรายงานจริงจาก deepseek-v4-pro-0813 (NVIDIA NIM) ที่ตอบถูก (ปฏิเสธใช้
    CeraVe/La Roche-Posay/One L'Oréal อย่างชัดเจน โดยอ้างถึงเพื่อบอกว่า "ไม่มีในข้อมูล") - ฟังก์ชันนี้
    ลดจาก 45 candidate (naive version ไม่กรอง) เหลือ ~7-10 และจัดหมวดถูกทั้ง 3 trap term ว่าเป็น
    "negated_safe" ไม่ใช่ "asserted" **ไม่ใช่ตัวกรองสมบูรณ์แบบ 100%** - ยังมี false positive เหลือ
    ประปราย (เช่น sentence-initial word ที่ไม่อยู่ใน stopword list, adjective form ที่ใกล้เคียงแต่ไม่
    เป๊ะกับ source เช่น "Southeast Asian" vs source's "Southeast Asia") **ต้องให้คนอ่าน asserted list
    (ปกติเหลือไม่กี่รายการ/รายงาน) ตัดสินใจสุดท้ายเอง แต่ลดงานจากอ่านทั้งรายงานเหลือแค่ดู list สั้นๆ**

    Returns: {"asserted": [...], "negated_safe": [...], "style_label_skipped": [...]}
        "asserted" = คำที่ไม่มีในข้อมูลต้นทาง และดูเหมือนถูกใช้เป็นข้อเท็จจริงจริง - ควรตรวจสอบก่อนเชื่อ
        "negated_safe" = คำที่ไม่มีในข้อมูลต้นทาง แต่โมเดลพูดถึงเพื่อบอกว่า "ไม่มี" (ปลอดภัย)
        "style_label_skipped" = 🆕 (2026-09-15) วลี Title-Case ที่ลงท้ายด้วยคำหมวดหมู่กว้างๆ (เช่น
        "...Delivery Systems", "...Ingredients") ตัดสินว่าเป็น concept label ที่โมเดลแต่งเอง ไม่ใช่การ
        อ้างข้อเท็จจริง - ไม่นับรวมใน MAX_ASSERTED_HALLUCINATIONS แต่ยังคืนค่าไว้ให้ตรวจสอบได้ถ้าสงสัย
    """
    stopwords_single = {
        "the", "this", "these", "those", "for", "and", "with", "from", "based",
        "data", "report", "trend", "trends", "market", "consumer", "consumers",
        "however", "therefore", "historically", "additionally", "moreover",
        "furthermore", "meanwhile", "consequently", "brand", "brands", "based",
        # 🆕 (2026-09-15) เพิ่มหลังสลับ report synthesis เป็น DeepSeek V3.2 (Bedrock) - DeepSeek ใช้คำ
        # เชื่อมต้นประโยคหลากหลายกว่าโมเดลที่ calibrate ฟังก์ชันนี้ไว้เดิม (2026-09-09) - เทสจริง 2 รอบ
        # (2026-09-15) เจอคำเหล่านี้ฟ้องซ้ำๆ ทั้งที่เป็นแค่คำทั่วไปที่ขึ้นต้นประโยค ไม่ใช่การหลอนเลย
        "demand", "desire", "driver", "examples", "frustration", "heightened", "sensitivity",
        "trending", "winning", "access", "concerns", "conversely", "correcting", "damage",
        "dedicated", "despite", "distrust", "information", "lack", "similarly", "success",
        "there", "compromise",
    }
    # 🆕 (2026-09-15) DeepSeek V3.2 เขียนวลี Title-Case แบบ "concept label" ฝังอยู่ในเนื้อความปกติบ่อยมาก
    # (เช่น "Advanced Delivery Systems", "Ingredient Transparency", "Tailored Solutions") ต่างจากโมเดล
    # เดิมที่ calibrate ฟังก์ชันนี้ไว้ - ไม่ใช่บรรทัด bold label เดี่ยวๆ ที่ filter เดิม (บรรทัด 1076)
    # จับได้ (นั่นจับได้แค่ทั้งบรรทัดเป็น **label** ล้วนๆ) เลยหลุดมาเป็น "asserted" เพิ่มจำนวนมาก ทั้งที่
    # ไม่ใช่การอ้างข้อเท็จจริง/ชื่อเฉพาะที่ต้องตรวจสอบ - ตรวจจากคำท้ายวลี: ถ้าเป็นคำหมวดหมู่กว้างๆ ทั่วไป
    # (ไม่ใช่ชื่อสาร/แบรนด์เฉพาะ) ให้ข้ามไปเป็น "style_label_skipped" แทน (ยังเห็นได้ ไม่ได้ซ่อนเงียบๆ)
    # ไม่แตะพวกคำลงท้ายที่อาจเป็นชื่อสารเคมี/ผลิตภัณฑ์เฉพาะจริง (เช่น -ide/-ate/-ol/-oside) เจตนา
    style_label_suffixes = {
        "science", "delivery", "mechanisms", "systems", "formulations", "actives", "analysis",
        "ingredients", "solutions", "strategy", "strategies", "innovation", "transparency",
        "literacy", "consciousness", "efficacy", "scrutiny", "cosmetics", "skincare", "points",
        "alternative", "alternatives", "treatment", "formats",
    }
    negation_markers = ["does not", "doesn't", "not contain", "no specific", "cannot be",
                         "not mention", "not reference", "absent", "not identified", "not named",
                         "nor does", "nor is", "nor are", "nor did", "no mention", "not include"]

    import re

    lines = report_text.split("\n")
    kept_lines = []
    for ln in lines:
        s = ln.strip()
        if re.match(r"^#+\s", s):
            continue
        if re.match(r"^\*\*[^*]+\*\*\.?$", s):
            continue
        kept_lines.append(ln)
    prose = "\n".join(kept_lines)

    candidates = set(re.findall(r"\b(?:[A-Z][a-zA-Z'&\-]+(?:\s+[A-Z][a-zA-Z'&\-]+){0,3})\b", prose))
    candidates = {c.strip() for c in candidates if c and c[0].isupper()}

    source_text = " ".join(
        (d.get("title", "") + " " + d.get("content", "")) for d in scraped_data
    ).lower()
    # เช็คบริบทระดับ "ประโยค" แทน char-window ตายตัว - เจอจริงว่า trigger คำปฏิเสธ (เช่น "nor does it
    # reference") อาจอยู่ห่างจากคำที่ถูกอ้างถึงเกิน 100 ตัวอักษรได้ ถ้าประโยคมีการยกตัวอย่างหลายคำติดกัน
    sentences = re.split(r"(?<=[.!?])\s+", prose)
    sentences_lower = [s.lower() for s in sentences]

    # 🆕 (2026-09-16) regex จับคำขึ้นต้นประโยคติดไปกับชื่อจริง เช่น "While Puig", "As ELC" (เจอจริงในรอบรัน News)
    # วลีรวมไม่มีในต้นทางจึงโดนฟ้องทั้งที่ชื่อมีจริง - ตัดคำขึ้นต้นออกก่อนเทียบ ไม่รวม "the" เพราะมีแบรนด์จริงที่
    # ขึ้นต้นด้วย The (เช่น The Ordinary) ถ้าตัดจะหลุดการตรวจ
    sentence_starters = {"while", "as", "with", "however", "although", "despite", "unlike", "meanwhile",
                         "similarly", "whereas", "after", "since", "because", "both", "its", "their"}

    asserted, negated_safe, style_label_skipped = [], [], []
    for c in candidates:
        cl = c.lower().strip().rstrip(".,;:")
        words = cl.split()
        if len(words) > 1 and words[0] in sentence_starters:
            cl = " ".join(words[1:])
        if len(cl) < 4:
            continue
        if " " not in cl and (cl in stopwords_single or cl.rstrip("s") in stopwords_single):
            continue
        cl_stem = re.sub(r"('s|s)$", "", cl)  # ตัด possessive/plural กันพลาดจาก morphological variant
        if cl in source_text or cl_stem in source_text:
            continue
        last_word = re.sub(r"[^a-z]", "", cl.split()[-1]) if " " in cl else ""
        if last_word in style_label_suffixes:
            style_label_skipped.append(c)
            continue
        matching_sentences = [s for s in sentences_lower if cl in s]
        if not matching_sentences:
            continue
        # ต้องถูกปฏิเสธ "ทุก" ประโยคที่พูดถึงคำนี้ ถึงจะถือว่าปลอดภัย - ถ้ามีประโยคไหนพูดถึงแบบไม่ปฏิเสธ
        # แม้แต่ประโยคเดียว ให้ฟ้อง (ระมัดระวังไว้ก่อน)
        if all(any(neg in s for neg in negation_markers) for s in matching_sentences):
            negated_safe.append(c)
        else:
            asserted.append(c)

    return {"asserted": sorted(set(asserted)), "negated_safe": sorted(set(negated_safe)),
            "style_label_skipped": sorted(set(style_label_skipped))}


# 🆕 (2026-09-12, audit M3) เกณฑ์ gate แบบ sanity guardrail เดียวกับ check_minimum_evidence - จับกรณี
# หลอนชัดเจน (จำนวน "asserted" มากเกินคนตรวจไหว - audit เจอจริง 184/98 คำ/รอบ) ไม่ใช่เกณฑ์ที่ calibrate
# อย่างเป็นทางการ
MAX_ASSERTED_HALLUCINATIONS = 30


def evidence_in_document(evidence, doc_text, min_chars=12):
    """🆕 (2026-09-15, audit M3 ฉบับเต็ม) เช็คแบบ deterministic ว่าประโยคหลักฐานที่ LLM ยกมามีอยู่จริงใน
    เอกสารต้นทางไหม - เทียบในภาษาเดิมของเอกสาร (หลักฐานไทยเทียบกับเอกสารไทย) จึงไม่ติดปัญหาข้ามภาษาแบบ
    ตัวเช็คเดิมที่เทียบ subject/object ภาษาอังกฤษกับข้อความไทย

    ยอมรับความต่างที่ไม่เปลี่ยนความหมาย: ตัวพิมพ์เล็ก/ใหญ่, ช่องว่าง/ขึ้นบรรทัด, เครื่องหมายคำพูดโค้ง/ตรง,
    ขีดยาว - และ "..." ในหลักฐาน (ทุกท่อนต้องมีอยู่จริง) หลักฐานสั้นกว่า min_chars ไม่ผ่าน (สั้นเกินจะเจอ
    ที่ไหนก็ได้)"""
    import re

    translation = str.maketrans({"“": "'", "”": "'", "„": "'", '"': "'", "‘": "'", "’": "'",
                                 "–": "-", "—": "-", "‐": "-", "‑": "-", "−": "-"})

    def _norm(text):
        return re.sub(r"\s+", " ", str(text).lower().translate(translation)).strip()

    doc = _norm(doc_text)
    fragments = [f.strip(" '.,;:") for f in re.split(r"\.\.\.|…", _norm(evidence))]
    fragments = [f for f in fragments if len(f) >= 4]
    if not fragments or sum(len(f) for f in fragments) < min_chars:
        return False
    return all(f in doc for f in fragments)


# "WHAT TO EXTRACT" จำเป็น: เวอร์ชันแรกที่มีแค่ "ไม่เกี่ยวข้องให้คืน list ว่าง" ทำให้ DeepSeek ตอบว่างเร็วๆ
# 6/7 ครั้งกับกระทู้ Pantip ที่ตรงหัวข้อชัดเจน (น่าจะเพราะเมนู/ปุ่มล็อกอินต้นหน้า) - เทสจริง 2026-09-15
_PER_DOC_TRIPLET_PROMPT = """You are a Strategic Beauty Intelligence Analyst mapping trends for 2026.

TASK:
Read ONE source document and extract structured knowledge as triplets (subject, relation, object).
Every triplet must be backed by a passage copied from that same document.

WHAT TO EXTRACT:
- Documents may be scientific papers, news articles, forum threads, Reddit posts, or video transcripts.
  Informal consumer text (reviews, questions, complaints, product recommendations) counts fully.
- Extract every relationship the document states about skincare, cosmetics, hair care or personal care:
  products, ingredients, benefits, skin/hair concerns, target users, and consumer preferences.
  When such content exists, aim for 5-15 triplets.
- Ignore website boilerplate: menus, login/cookie notices, navigation labels, member IDs, dates.
- Return an empty list ONLY if the document never mentions any beauty or personal care product,
  ingredient, benefit, or concern.

TERM RULES:
- subject, relation, object: English, lowercase, 1-4 words each.
- Normalize similar terms (e.g., "vitamin c" instead of "vit c serum"). Avoid vague terms ("good", "thing").

ENTITY TYPES (use only these): Ingredient, Benefit, Product_Type, Target_Audience, Trend_Vibe,
Longevity_Signal
- Subject -> usually Ingredient, Product_Type, or Trend_Vibe
- Object -> Benefit, Target_Audience, Trend_Vibe, or Longevity_Signal

RELATIONS (allowed only): "has_benefit", "contains", "targets", "drives", "associated_with",
"evolves_to", "preferred_by"

EVIDENCE RULES (most important):
- Every triplet MUST include "evidence": a passage of 5-25 words copied EXACTLY from the document,
  character for character. Do NOT translate, paraphrase, summarize, or fix typos.
- If the document is in Thai or another language, the evidence stays in that original language,
  while subject/relation/object are still written in English.
- Only extract what this document itself states.

OUTPUT: Return ONLY this JSON object, no other text:
{"triplets": [{"subject": "...", "relation": "...", "object": "...", "evidence": "..."}]}"""


def extract_triplets_per_document(scraped_data, max_workers=4, char_limit=8000):
    """🆕 (2026-09-15, audit M3 ฉบับเต็มตามที่ audit เสนอไว้ตั้งแต่แรก) สกัด triplet ทีละเอกสาร พร้อม
    ประโยคหลักฐานที่ยกมาตรงตัวจากเอกสารนั้น แล้วตรวจด้วย evidence_in_document() - เก็บเฉพาะ triplet ที่
    หลักฐานมีอยู่จริง

    แทนวิธีเดิม (สกัดจากรายงานที่ LLM รวมทุกเอกสารเป็นก้อนเดียว แล้วหา subject/object แบบตรงตัวใน
    เอกสาร) ที่ตัดทิ้ง 77-93% ทุกรอบ และเช็คเอกสารภาษาไทยไม่ได้เลย (สาย Social พังที่ triplets=3 < 5,
    2026-09-15)

    ข้อจำกัดที่รู้อยู่: ยืนยันได้แค่ว่าประโยคหลักฐานมีอยู่จริง ไม่ได้ยืนยันว่า triplet ตีความประโยคนั้นถูก

    Returns:
        (triplets, provenance) - triplets = [[s, r, o], ...] เฉพาะที่หลักฐานผ่าน (รูปแบบเดียวกับที่
        build_trend_graph() รับ), provenance = ทุก triplet ที่สกัดได้พร้อม doc_index/title/evidence/verified
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    if not scraped_data:
        return [], []

    token_lock = threading.Lock()

    def _extract_one(idx, doc):
        title = str(doc.get("title", ""))
        content = str(doc.get("content", ""))
        try:
            response = tf.client.chat.completions.create(
                model=tf.MODEL_NAME_META,
                messages=[{"role": "system", "content": _PER_DOC_TRIPLET_PROMPT},
                          {"role": "user", "content": f"TITLE: {title}\n\nDOCUMENT:\n{content[:char_limit]}"}],
                temperature=0, max_tokens=2500,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            print(f"     ❌ เอกสาร {idx + 1} ({title[:40]}): {e}")
            return []

        usage = getattr(response, "usage", None)
        if usage:
            with token_lock:
                tf.total_input_tokens += getattr(usage, "prompt_tokens", 0) or 0
                tf.total_output_tokens += getattr(usage, "completion_tokens", 0) or 0

        data = safe_json_parse(response.choices[0].message.content or "")
        items = data.get("triplets") if isinstance(data, dict) else None
        if not isinstance(items, list):
            print(f"     ⚠️ เอกสาร {idx + 1} ({title[:40]}): parse JSON ไม่ได้ - ข้ามเอกสารนี้")
            return []

        doc_text = f"{title} {content}"
        records = []
        for item in items:
            if not isinstance(item, dict):
                continue
            s, r, o = (str(item.get(k, "")).strip().lower() for k in ("subject", "relation", "object"))
            if not (s and r and o):
                continue
            evidence = str(item.get("evidence", "")).strip()
            records.append({"triplet": [s, r, o], "doc_index": idx, "title": title,
                            "source_region": doc.get("source_region", ""), "evidence": evidence,
                            "verified": evidence_in_document(evidence, doc_text)})
        return records

    print(f"     -> {len(scraped_data)} เอกสาร (เรียกพร้อมกัน {max_workers})")
    # เข้า use_bedrock() ครั้งเดียวรอบ thread pool - ถ้าเข้าในแต่ละ thread จะแย่งกันแพตช์ tf.client
    with use_bedrock():
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            per_doc = list(pool.map(lambda args: _extract_one(*args), enumerate(scraped_data)))

    provenance = [rec for recs in per_doc for rec in recs]
    triplets = [rec["triplet"] for rec in provenance if rec["verified"]]
    n_docs_with_triplets = sum(1 for recs in per_doc if recs)
    print(f"     ได้ {len(provenance)} triplets จาก {n_docs_with_triplets}/{len(scraped_data)} เอกสาร - "
          f"หลักฐานตรงต้นฉบับ {len(triplets)}, ตัด {len(provenance) - len(triplets)} "
          f"(ประโยคหลักฐานไม่มีในเอกสารจริง)")
    return triplets, provenance


# ต้องเก็บของเดิมไว้ก่อน monkey-patch ด้านล่าง ไม่งั้น fallback ใน safe_json_parse() จะเรียกตัวเองไม่รู้จบ
# (เจอจริง 2026-08-28 ตอนรัน News-Intl: "maximum recursion depth exceeded" ทุกครั้งที่ json.loads()
# ตรงๆ พัง เพราะ tf.safe_json_parse ถูก patch เป็นฟังก์ชันนี้เองไปแล้ว เรียก tf.safe_json_parse(content)
# ในบรรทัด fallback จึงกลายเป็นเรียกตัวเองซ้ำไม่มีที่สิ้นสุด - ไม่เคยโผล่มาก่อนเพราะ json.loads() ตรงๆ
# ผ่านทุกครั้งในการรันก่อนหน้านี้ พอเจอ response ที่ parse ตรงๆ ไม่ผ่านครั้งแรกถึงเจอบั๊กนี้)
_original_tf_safe_json_parse = tf.safe_json_parse
# เก็บ generate_trend_report_with_llm ตัวจริงไว้ก่อน patch - generate_trend_report_with_retry() ด้านบน
# เรียกตัวนี้ ไม่ใช่ tf.generate_trend_report_with_llm (กัน recursion เวลา runner patch ชื่อนั้น)
_original_generate_trend_report = tf.generate_trend_report_with_llm


def safe_json_parse(content):
    """เวอร์ชันที่แก้บั๊กแล้ว - ลอง json.loads() ตรงๆ ก่อนเสมอ

    ต้นตอ: tf.safe_json_parse ทำ content.replace('\\\\"', '"') แบบไม่มีเงื่อนไข (ตั้งใจแก้ปัญหา
    โมเดลเล็กที่ over-escape) แต่ไปทำลาย escaped quote ที่ถูกต้องตามหลัก JSON ด้วย เช่นเวลา LLM
    ตอบว่า "...a \\"Moisture Barrier\\"..." จะพังทันที - เจอจริงตอนรัน pilot อีคอมเมิร์ซต่างประเทศ
    (2026-08-27) ดู Backlog ข้อ 11

    🆕 (2026-09-01) เรียก strip_gemma_thought() ก่อนเสมอ - ไม่มีผลกับ provider อื่นที่ไม่มี <thought>
    เลย (คืนค่าเดิมตรงๆ) แต่ป้องกัน Gemma ไม่ให้ parse ผิดไปจับ JSON ร่างที่อยู่ในความคิดแทนคำตอบจริง
    (ดู use_gemma() + strip_gemma_thought() ด้านบนสำหรับเหตุผลเต็ม)
    """
    import json
    if not content or not isinstance(content, str):
        return None
    content = strip_gemma_thought(content).strip()
    try:
        return json.loads(content)
    except Exception:
        pass
    return _original_tf_safe_json_parse(content)  # fallback ของเดิม (ต้องเป็นตัวที่เก็บไว้ก่อน patch)


# Monkey-patch: ฟังก์ชันอื่นๆ ใน trend_final.py (extract_strategic_keywords, summarize_trend_clusters,
# categorize_to_pillars, extract_beauty_triplets ฯลฯ) เรียก safe_json_parse() แบบ bare name ภายใน
# ไฟล์ตัวเอง - ชื่อนี้ resolve จาก __globals__ ของโมดูล trend_final ตอนรันจริง ไม่ใช่จาก namespace
# ของสคริปต์ที่เรียกมันมา ดังนั้นแค่เรียกผ่าน tf.extract_strategic_keywords(...) เฉยๆ จะยังโดนบั๊ก
# เดิมอยู่ (ดู safe_json_parse ด้านบน) - patch ตรงนี้ทีเดียวทำให้ทุกฟังก์ชันในโมดูลได้ใช้เวอร์ชันที่
# แก้แล้วโดยอัตโนมัติ ปลอดภัยเพราะแค่ลอง json.loads() ก่อนเสมอ ไม่เปลี่ยนพฤติกรรมกรณีอื่นเลย
tf.safe_json_parse = safe_json_parse


SELECTION_CRITERIA_SHARED = (
    "- The item must be substantively about the topic itself, not an adjacent field that only "
    "mentions it in passing.\n"
    "- Do not select multiple items covering the same single event, announcement, or finding "
    "— pick the best one and move on."
)
SELECTION_CRITERIA_NEWS = (
    "- Prefer items reporting a specific development, product launch, brand move, or consumer "
    'behavior over broad "top trends" overview pieces that only skim many subjects.\n'
    "- When two items are similarly relevant, prefer the more recent."
)
SELECTION_CRITERIA_PAPER = (
    "- Prefer studies on the actual product category or its key ingredients / mechanisms over "
    "tangential cosmetic science.\n"
    "- A rigorous review or meta-analysis is as valuable as a primary study."
)


def select_top_news(topic, all_news, top_k=10, kind="news"):
    """เหมือน tf.select_top_10_news_with_llm() แต่แก้บั๊ก case-sensitivity ในตัวกรองคำหลัก +
    เพิ่มเกณฑ์การเลือกที่ชัดเจน (แยกตาม `kind`)

    **`kind` (2026-09-10):** prompt เดิมบอกแค่ "most relevant to the topic" คำเดียว โยนให้โมเดล
    ตีความเอง — เจอจริงว่าเลือกบทความนอกเรื่อง (เช่น "Future Food Trend Workshop" มาเป็นข่าวครีมอาบน้ำ)
    ตอนนี้ฉีดเกณฑ์เข้า prompt: SHARED (ทั้ง news/paper) + เฉพาะประเภท —
    - `kind="news"`: เน้นพัฒนาการ/สินค้า/แบรนด์เจาะจง มากกว่า "top trends" roundup, เอาข่าวใหม่กว่า
    - `kind="paper"`: เน้นงานที่ตรงหมวดสินค้า/ส่วนผสม/กลไก, review ที่ดี ≈ primary study
    ใช้ฟังก์ชันเดียว (แก้บั๊กที่เดียว) โครง JSON-format ร่วมกัน ไม่แยกเป็น 2 prompt เต็ม
    default `kind="news"` กัน call site เดิมที่ยังไม่ส่ง param

    **abstract snippet (2026-09-10):** ถ้า pool item มี `_abstract` (OpenAlex ใส่มาให้ใน pool แล้ว)
    → ใส่ ~280 ตัวอักษรแรกต่อท้าย title ในลิสต์ที่ส่งให้โมเดล + ให้ keyword pre-filter เช็ค abstract
    ด้วย (กัน paper ที่ abstract ตรงแต่ title ไม่มีคำหลักโดนตัดก่อน) + บอกโมเดลว่าบางชิ้นมีบางชิ้นไม่มี
    อย่าลงโทษชิ้นที่ข้อความน้อยกว่า - ScienceDaily/MDPI ยังตัดสินจาก title เหมือนเดิม (ไม่มี abstract
    ตอน fetch), ฝั่ง news ทุก item ไม่มี `_abstract` → พฤติกรรมเดิมไม่เปลี่ยน

    ต้นตอ (trend_final.py ~บรรทัด 372): 'all_news = [n for n in all_news if any(word in
    n["title"].lower() for word in topic.split())][:30]' - lowercase แค่ title ฝั่งเดียว แต่
    topic.split() ยังเป็นตัวพิมพ์ใหญ่ตามที่พิมพ์มาจริง (เช่น "Trend Body Wash Thailand 2030")
    ทำให้ "Trend" (T ใหญ่) เทียบกับ title ที่ lowercase ทั้งหมดไม่ตรงกันเลย - ถ้า pool > 30 รายการ
    (พบจริงตอนรัน pilot Phase 1 สาย Paper - pool 867 รายการ) ตัวกรองนี้จะเหลือ 0 รายการเสมอ แล้ว
    LLM ก็ไม่มีอะไรให้เลือก -> คืนค่าว่างทั้งฟังก์ชัน โดยไม่มี error ใดๆ เตือนเลย

    เจอจริง 2026-08-28 ตอนรัน Phase 1 - บั๊กนี้กระทบ pipeline หลักด้วย ไม่ใช่แค่ pilot นี้ เพราะ
    get_historical_news() ปกติดึงจาก RSS 14 แหล่ง + Google News หลายปีย้อนหลัง เกิน 30 รายการได้
    ง่ายมาก - ยังไม่ได้แก้ที่ต้นทาง (trend_final.py) ดู Backlog

    🌀 ชั้น LLM เลือก 8 อันดับสุดท้าย (ด้านล่าง) **บังคับใช้โมเดลเดียวกันเสมอ** ผ่าน `with use_bedrock()`
    ภายในฟังก์ชันเอง ไม่ว่าโค้ดที่เรียก select_top_news() จะอยู่ใน context ของโมเดลอะไรอยู่ก็ตาม
    - เหตุผลเดิม (ข้อ 22 ใน Backlog): ทดสอบ NVIDIA nemotron แล้วพัง (ตอบ chain-of-thought ปนใน content
    จน max_tokens ตัดก่อนถึง JSON), ทดสอบ Gemini แล้วพัง (thinking กินโควตา token ที่มองไม่เห็น ต้องแก้
    ด้วย reasoning_effort="none" แต่ Gemini free tier จำกัดแค่ 20 request/วัน/โมเดล ไม่พอใช้จริง), มีแค่
    Typhoon ที่ทดสอบ 5/5 ครั้งผ่านสะอาดทุกครั้ง (JSON ครบ ไม่มี reasoning token แอบกิน budget) - งานนี้
    เป็นแค่ "เลือก index จากลิสต์ที่ให้" ไม่ใช่งานสังเคราะห์อิสระแบบ generate_trend_report ที่ Typhoon
    เคยพัง (ข้อ 19) จึงไม่มีความเสี่ยงหลอนแบบนั้น

    🆕 (2026-09-15) เปลี่ยนจาก Typhoon -> AWS Bedrock แล้ว - เจ้าของงานสั่งเลิกใช้ Typhoon
    ทั้งหมด **ยังไม่เคยเทส DeepSeek กับ JSON-strict แบบนี้มาก่อน** ถ้าเจอปัญหา chain-of-thought ปน JSON
    แบบเดียวกับที่ NVIDIA nemotron เคยพัง ให้กลับมาอ่านหัวเหตุผลข้างบนก่อนตัดสินใจเปลี่ยนโมเดลจุดนี้
    """
    print(f"🧠 [RSS 3/5] คัดกรองข่าวที่เกี่ยวข้องที่สุด {top_k} อันดับจาก {len(all_news)} รายการ...")
    if len(all_news) <= top_k:
        return all_news

    if len(all_news) > 30:
        # 🆕 (2026-09-01, ข้อ 23 ใน Backlog) ตัดคำ "โครงร่างหัวข้อ" ที่กว้างเกินไปออกจากตัวกรอง -
        # เจอจริงตอนรัน News-Intl: topic = "Trend Body Wash Thailand 2030" ทำให้คำว่า "trend"
        # (substring match ติด "trends"/"Trends" ด้วย) ผ่านตัวกรองมาแทบทุกบทความความงาม แม้ไม่เกี่ยว
        # กับ body wash เลย (เช่น "Top 100 Cosmetics Trends", "Global Beauty Ingredient Trends 2026")
        # ผลคือ pool 30 รายการเจือจางจนของจริงเหลือไม่กี่ชิ้น (มีแค่ 2/8 ที่เจาะจง body wash จริง)
        # คำพวกนี้เป็น "โครงร่าง" ของหัวข้อทุกหัวข้อในโปรเจกต์นี้ (Trend + [สินค้า] + [ประเทศ] + [ปี])
        # ไม่ได้บอกความเจาะจงของสินค้าเลย - ตัดทิ้งแล้วเหลือแค่คำที่เจาะจงจริง (เช่น "body", "wash")
        _GENERIC_TOPIC_WORDS = {"trend", "trends", "the", "a", "an", "of", "in", "for"}
        topic_words_lower = [w.lower() for w in topic.split() if w.lower() not in _GENERIC_TOPIC_WORDS]
        # เช็คทั้ง title + abstract (ถ้ามี) - กัน paper ที่ abstract เกี่ยวมากแต่ title ไม่มีคำหลัก
        # โดนตัดทิ้งก่อน LLM เห็น (= เคส "Aigis Wash" จาก Phase 3 ที่ literal keyword พลาดแต่ความหมายตรง)
        filtered = [n for n in all_news if any(
            w in (n["title"] + " " + (n.get("_abstract") or "")).lower() for w in topic_words_lower
        )][:30]
        print(f"    -> หลังกรองคำหลัก (ตัดคำกว้างๆ ออกแล้ว: {topic_words_lower}): {len(filtered)} รายการ")
        all_news = filtered if filtered else all_news[:30]  # กันเคส 0 รายการซ้ำ - ใช้ 30 แรกแทน

    limited_news = all_news

    def _fmt_item(i, n):
        # ชื่อแหล่งข้างหน้า title - ให้โมเดลมี signal เรื่องประเภท/ความน่าเชื่อถือ (Mintel = market
        # research vs บล็อกรีวิว) + abstract snippet (~280 ตัวอักษร) ถ้ามี (OpenAlex ใส่ _abstract มา
        # ให้ใน pool แล้ว) - title งานวิจัยเป็นศัพท์เทคนิคแน่น บอกความเกี่ยวข้องจริงไม่ชัด abstract ช่วยได้มาก
        line = f"[{i}] ({n.get('source', '?')}) {n['title']}"
        snip = " ".join((n.get("_abstract") or "").split())
        if snip:
            line += f" — {snip[:280]}"
        return line

    news_text = "\n".join(_fmt_item(i, n) for i, n in enumerate(limited_news))
    _has_any_abstract = any((n.get("_abstract") or "").strip() for n in limited_news)

    _kind_criteria = SELECTION_CRITERIA_PAPER if kind == "paper" else SELECTION_CRITERIA_NEWS
    _item_word = "research items" if kind == "paper" else "news articles"
    _role = "research librarian" if kind == "paper" else "news editor"
    criteria_block = (
        f"Selection criteria, in priority order:\n{SELECTION_CRITERIA_SHARED}\n{_kind_criteria}"
    )
    _abstract_note = (
        "\nSome items include an abstract/summary snippet after the title; others show only a "
        "title. Judge each on the information available and do not penalize an item merely for "
        "having less text shown."
        if _has_any_abstract else ""
    )

    system_prompt = (
        f"You are a senior {_role} specializing in curation and filtering. "
        "Always reply in JSON format. Do not output any other text under any circumstances. "
        f"Task: Select the top {top_k} {_item_word} most relevant to the topic from the provided list.\n"
        f"{criteria_block}{_abstract_note}\n"
        'Reply ONLY in JSON format as {"top_indices": [...]}, where the numbers in top_indices '
        "are the indices of the selected items from the list above."
    )
    _line_fmt = "[index] (source) title — abstract snippet (snippet may be absent)" if _has_any_abstract \
        else "[index] (source) title"
    prompt = (
        f'Select the top {top_k} {_item_word} most relevant to the topic "{topic}" '
        f"from the following list (each line is: {_line_fmt}):\n{news_text}\n\n"
        f"{criteria_block}{_abstract_note}\n\n"
        'Strict output rules:\n- Reply as a JSON object ONLY.\n- Required format: {"top_indices": [...]}'
    )

    for attempt in range(3):
        try:
            # 🆕 (2026-09-15) เปลี่ยนจาก Typhoon (บังคับเพราะ NVIDIA NIM JSON เพี้ยน) -> AWS Bedrock
            # - เจ้าของงานสั่งเลิกใช้ Typhoon ทั้งหมด รวมจุด JSON-strict นี้ด้วย (ยืนยันแล้วหลัง
            # ถามเรื่อง trade-off เสี่ยง JSON พังซ้ำ) ยังไม่เคยเทส DeepSeek กับ JSON เข้มงวดแบบนี้มาก่อน -
            # ถ้าเจอปัญหา JSON parse พังซ้ำแบบที่เคยเจอกับ NVIDIA ให้ดู Backlog 2026-09-15 ก่อนตัดสินใจ
            with use_bedrock():
                response = tf.client.chat.completions.create(
                    model=tf.MODEL_NAME_META,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=500,
                    response_format={"type": "json_object"},
                )
            raw_content = (response.choices[0].message.content or "") if response and response.choices else ""
            data = safe_json_parse(raw_content)
            if data and isinstance(data, dict) and isinstance(data.get("top_indices"), list) and data["top_indices"]:
                indices = data["top_indices"]
                selected = [limited_news[i] for i in indices if isinstance(i, int) and i < len(limited_news)]
                if selected:
                    return selected[:top_k]
        except Exception as e:
            print(f"    ⚠️ select_top_news attempt {attempt + 1} failed: {e}")
        import time as _time
        _time.sleep(2)

    print("    ⚠️ เลือกด้วย LLM ไม่สำเร็จทุกรอบ - ใช้ 10 อันดับแรกจากลิสต์ที่กรองแล้วแทน")
    return limited_news[:top_k]


def scrape_article(url):
    """เหมือน tf.scrape_article_content() แต่แก้บั๊กที่ทำให้ Apify fallback ใช้งานไม่ได้เลย

    ต้นตอ (trend_final.py ~บรรทัด 519): 'run = client.actor(...).call(...)' แล้วอ่านผลด้วย
    'run["defaultDatasetId"]' - ใช้งานได้กับ apify-client รุ่นเก่าที่ .call() คืน dict แต่รุ่นที่
    ติดตั้งอยู่จริง (3.0.6) เปลี่ยน Run เป็น pydantic model แล้ว ไม่ใช่ dict อีกต่อไป จึง subscript
    ไม่ได้ -> ทุกครั้งที่ต้องพึ่ง Apify (เว็บบล็อก 403 เช่น MDPI) จะพังด้วย "'Run' object is not
    subscriptable" แม้ Apify จะ crawl สำเร็จจริงแล้วก็ตาม (เห็น log "Finished! X succeeded" แต่ code
    ดึงผลไม่ได้) - เจอจริง 2026-08-28 ตอนรัน Phase 1 สาย Paper (MDPI ต้องพึ่ง Apify ทุกลิงก์)

    แก้: ใช้ attribute แบบ snake_case ของ pydantic model (run.default_dataset_id) แทน dict access
    ยังไม่ได้แก้ที่ต้นทาง (trend_final.py) เพราะกระทบทุกจุดที่ scrape เว็บที่บล็อก 403 ทั้ง pipeline
    ไม่ใช่แค่ Phase 1 - ดู Backlog
    """
    import re as _re
    import time as _time

    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    def _decode_url(src_url, timeout=20):
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

        with ThreadPoolExecutor(max_workers=2) as executor:
            future = executor.submit(tf.gnewsdecoder, src_url)
            try:
                return future.result(timeout=timeout)
            except FuturesTimeoutError:
                future.cancel()
                raise TimeoutError(f"gnewsdecoder timed out after {timeout}s")

    def _scrape_with_apify(target_url):
        print(f"  🤖 [fixed] สลับไปใช้ Apify ดึงข้อมูลจากลิงก์: {target_url}")
        try:
            client = tf.ApifyClient(tf.APIFY_API_KEY)
            run_input = {
                "startUrls": [{"url": target_url}],
                "crawlerType": "playwright:adaptive",
                "includeUrlGlobs": [], "excludeUrlGlobs": [],
                "useSitemaps": False, "useLlmsTxt": False,
                "respectRobotsTxtFile": True,
                "proxyConfiguration": {"useApifyProxy": True},
                "initialCookies": [], "customHttpHeaders": {}, "signHttpRequests": False,
                "blockMedia": True,
                "clickElementsCssSelector": '[aria-expanded="false"]',
                "keepElementsCssSelector": "",
                "removeElementsCssSelector": (
                    "nav, footer, script, style, noscript, svg, img[src^='data:'],"
                    '[role="alert"], [role="banner"], [role="dialog"], [role="alertdialog"],'
                    '[role="region"][aria-label*="skip" i], [aria-modal="true"]'
                ),
                "storeSkippedUrls": False,
            }
            run = client.actor("apify/website-content-crawler").call(run_input=run_input)
            if run is None:
                print("  ❌ Apify run คืนค่า None (ล้มเหลว/ยกเลิก)")
                return ""

            dataset_id = run.default_dataset_id  # <- จุดที่แก้: attribute ไม่ใช่ dict key
            text_content = ""
            for item in client.dataset(dataset_id).iterate_items():
                if item.get("text"):
                    text_content += item["text"] + " "
            return _re.sub(r"\s+", " ", text_content).strip()
        except Exception as apify_e:
            print(f"  ❌ Apify ก็ดึงข้อมูลไม่ได้: {str(apify_e)[:200]}")
            return ""

    try:
        _time.sleep(5)
        try:
            _time.sleep(3)
            decoded = _decode_url(url, timeout=20)
        except Exception as e:
            print(f"  ⚠️ gnewsdecoder failed or timed out: {e}")
            decoded = {}

        real_url = decoded.get("decoded_url") if decoded.get("status") else url
        resp = tf.requests.get(real_url, headers=headers, timeout=15)

        if resp.status_code in (403, 400, 401, 429):
            print(f"  ⚠️ ถูกบล็อก {resp.status_code}. กำลังเรียกใช้ Apify...")
            apify_text = _scrape_with_apify(real_url)
            return (apify_text, real_url) if apify_text else ("", real_url)

        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.extract()
        text = _re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))
        return text, real_url

    except Exception as e:
        _es = str(e)
        # 🆕 (2026-09-11, Backlog B1) ครอบ connection-reset/aborted ด้วย ไม่ใช่แค่ 403 - เจอจริงทุกรอบ
        # News: intl scrape ~ครึ่งล้มด้วย "Connection aborted / RemoteDisconnected" แล้วถูกข้ามเงียบ
        # (Apify ใช้ proxy infra ของตัวเอง ผ่าน transient block / IP issue ได้)
        _retryable = ("403" in _es or "Connection aborted" in _es or "RemoteDisconnected" in _es
                       or "ConnectionError" in _es or "Connection reset" in _es
                       or "Max retries exceeded" in _es or "timed out" in _es.lower())
        if _retryable:
            print(f"  ⚠️ scrape ตรง fail ({_es[:70]}) - กำลังเรียกใช้ Apify...")
            fallback_url = real_url if "real_url" in locals() else url
            apify_text = _scrape_with_apify(fallback_url)
            return (apify_text, fallback_url) if apify_text else ("", fallback_url)
        print(f"  ❌ ข้ามลิงก์ (ดึงข้อมูลหรือถอดรหัสไม่ได้): {_es[:200]}")
        return "", url


def generate_trend_report(topic, scraped_data):
    """🆕 (2026-09-16) รายงานเทรนด์ด้วย prompt ที่ไม่มีตัวอย่างฝังและบังคับอ้างอิงแหล่ง - ใช้กับทุกสาย (Paper, Social, News)

    ประวัติ: เขียนครั้งแรก 2026-08-28 (ตัดตัวอย่าง 7 จุดใน prompt ของ trend_final.py:611-636 ที่ Typhoon/NVIDIA
    เอาไปแต่งเป็นข้อค้นพบ) แล้วเลิกใช้ 2026-08-31 เพราะตอนนั้นสรุปว่าต้นเหตุคือโมเดลไม่พอ (GPT-5.6-Luna ใช้
    prompt ต้นฉบับได้โดยไม่หลอน) - เหตุผลนั้นใช้ไม่ได้แล้วหลังย้ายมา GLM-5 บน Bedrock: RCA 2026-09-15 บนข้อมูล
    Social จริงพบว่า prompt ต้นฉบับยังดันให้แต่ง (PDRN จากตัวอย่าง, market share/กลยุทธ์แบรนด์ที่ข้อมูล Social
    ไม่มี, เดาชื่อสารจาก caption ถอดเสียงเพี้ยน, เติมข้อเท็จจริงจากความรู้โมเดล) - เจ้าของงานสั่งใช้ prompt นี้กับ
    สาย Social โดยไม่แตะ trend_final.py

    ต่างจาก prompt ต้นฉบับ: ไม่มีชื่อแบรนด์/สาร/สถิติตัวอย่างเลย, ห้ามเติมจากความรู้โมเดลแม้เป็นเรื่องจริง,
    ทุกข้ออ้างเจาะจงต้องอ้าง (Ref N), ห้ามเดาชื่อจากข้อความถอดเสียงอัตโนมัติ, ความเห็น/upvote ไม่ใช่สถิติตลาด,
    หัวข้อที่ไม่มีหลักฐานให้เขียนว่าไม่มีข้อมูล - โครงหัวข้อ 4 ส่วนเหมือนต้นฉบับ รายงานจึงหน้าตาเดิม
    """
    print("🧠 Synthesizing trend report (evidence-cited prompt, no embedded examples)...")

    combined_context = ""
    for idx, data in enumerate(scraped_data):
        combined_context += f"--- Reference Article {idx + 1} ---\n"
        combined_context += f"Title: {data.get('title', 'No Title')}\n"
        combined_context += f"Content: {data.get('content', '')}\n\n"

    system_prompt = """
    You are a Senior Market Intelligence & Strategy Analyst writing a trend report strictly from the raw data provided.

    CORE OPERATING DIRECTIVES:
    1. DATA-ONLY: Every brand, product, ingredient, number, and consumer claim must come from the Raw Data. Do not add anything from general knowledge - no extra brands, ingredients, regulatory facts, market sizes, market shares, growth rates, or demographics - even if you believe it is true.
    2. CITE: After every specific brand, product, ingredient, number, or consumer claim, cite its source as (Ref N) or (Ref N, M) using the Reference Article numbers. Cite only articles that actually contain it.
    3. NO GUESSING NAMES: Articles whose title is marked [automatic speech-to-text transcript] may contain misrecognized words. If a product or ingredient name there is garbled or unclear, describe it generically (for example "a brightening ingredient") instead of guessing the intended name.
    4. OPINIONS ARE NOT STATISTICS: Forum posts, Reddit comments, and video reviews are individual opinions. Upvote counts reflect agreement within one thread only; never turn them into market-wide figures.
    5. MISSING EVIDENCE: If a section below has no supporting evidence, write "Not covered in the collected data." for that section instead of filling it in.
    6. LANGUAGE: Professional English. When you translate a Thai term, keep the original Thai in parentheses.
    """

    user_prompt = f"""
    Write an "In-Depth Market Trend Analysis Report" on: "{topic}"

    Follow this Markdown structure. The headings and instructions describe categories of analysis only; they contain no facts about any market.

    # 📊 Deep-Dive Trend Analysis Report: {topic}

    ## 1. Executive Summary
    - Synthesize what the data shows, and the single most important opportunity the data directly supports.

    ## 2. Deep-Dive Market Trends & Consumer Insights
    - **Needs & Pain Points:** What consumers complain about, ask for, or say is missing.
    - **Trend Mechanisms:** Ingredients or product features that appear in the data, and why the data suggests they matter.

    ## 3. Market Drivers & Business Opportunities
    - **Impact Mechanisms:** Causes and effects that are both described in the data.
    - **Whitespace Analysis:** Unmet needs or underserved segments that the data itself points to.

    ## 4. Competitive Landscape & Brand Movements
    - **Tactical Analysis:** Brand strategies or positioning explicitly described in the data.
    - **Brand Proof Points:** Specific products or brands named in the data, with what the data says about them.

    Raw Data (References):
    {combined_context}
    """

    full_prompt = system_prompt + user_prompt
    try:
        max_tokens = tf.compute_max_tokens(full_prompt)
        response = tf.client.chat.completions.create(
            model=tf.MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        if hasattr(response, "usage") and response.usage:
            tf.total_input_tokens += getattr(response.usage, "prompt_tokens", 0)
            tf.total_output_tokens += getattr(response.usage, "completion_tokens", 0)

        content = response.choices[0].message.content
        if content is None:
            print("⚠️ LLM API returned an empty response (possible context limit or safety policy block).")
            return ""
        return content.strip()
    except Exception as e:
        print(f"❌ LLM Error during report generation: {e}")
        return ""


def extract_beauty_triplets(headlines, batch_size=10):
    r"""เหมือน tf.extract_beauty_triplets() แต่ strip <thought> ของ Gemma ออกก่อน parse เสมอ

    ต้นตอ (trend_final.py:1074): ฟังก์ชันนี้ไม่ได้ใช้ safe_json_parse เลย - มี regex parser ของตัวเอง
    (`re.search(r'(\[.*\])', raw_content, re.DOTALL)` แล้ว fallback เป็น `re.findall(...)` หา
    ทุก [...] ที่ดูเหมือน triplet ในข้อความทั้งก้อน) - ทดสอบจริงกับ Gemma (2026-09-01) แล้วพัง:
    regex ตัวแรก greedy match จาก "[" ตัวแรกในความคิด (<thought>) ไปจนถึง "]" ตัวสุดท้ายในคำตอบจริง
    ทำให้ json.loads() พัง แล้ว fallback regex ไปเจอ triplet ที่ Gemma พูดซ้ำหลายรอบระหว่างคิด (ร่าง คิด
    ทบทวน สรุป) เก็บมาด้วยทุกรอบ - ผลจริงที่เจอ: 6 triplet ที่ถูกต้อง ถูกดึงมาซ้ำ 6-7 รอบ (ได้ 38 แถว
    ทั้งที่ควรมีแค่ 6-7 แถว) แถมมี artifact แปลกๆ (['Subject','Relation','Object'] จาก system prompt's
    OUTPUT FORMAT ตัวอย่างเอง) ปนมาด้วย

    แก้: strip_gemma_thought(raw_content) ก่อนเข้า regex เดิมทุกจุด (ไม่กระทบ provider อื่นที่ไม่มี
    <thought> เลย เพราะ strip_gemma_thought คืนค่าเดิมตรงๆ ถ้าไม่เจอ tag)
    """
    if not headlines:
        return []
    if isinstance(headlines, str):
        headlines = [line.strip() for line in headlines.split("\n") if len(line.strip()) > 10]
    all_results = []
    print(f"    -> Example of headlines: {headlines[:10]}")
    print(f"    -> Size of headlines: {len(headlines)}")
    print(f"    -> Total Batch: {len(headlines) / batch_size}")

    system_prompt = """You are a Strategic Beauty Intelligence Analyst mapping trends for 2026.

    TASK:
    Extract structured knowledge as triplets in the format:
    ["Subject", "Relation", "Object"]

    STRICT OUTPUT RULES:
    - Return ONLY a valid JSON array.
    - NO explanations, NO extra text.
    - NO trailing commas.
    - Use double quotes ONLY.
    - Each triplet = exactly 3 strings.
    - Each string MUST be 1-4 words max.
    - Use lowercase only.

    CONSISTENCY RULES:
    - Avoid duplicates (exact or similar meaning).
    - Normalize similar terms (e.g., "vitamin c" instead of "vit c serum").
    - Keep terms concise and standardized.

    ENTITY TYPES (use only these):
    - Ingredient
    - Benefit
    - Product_Type
    - Target_Audience
    - Trend_Vibe
    - Longevity_Signal

    RELATION RULES (allowed relations only):
    - "has_benefit"
    - "contains"
    - "targets"
    - "drives"
    - "associated_with"
    - "evolves_to"
    - "preferred_by"

    MAPPING GUIDELINES:
    - Subject -> usually Ingredient, Product_Type, or Trend_Vibe
    - Object -> Benefit, Target_Audience, Trend_Vibe, or Longevity_Signal
    - Ensure logical relationships (no random pairing)

    QUALITY RULES:
    - Prioritize high-signal, trend-relevant concepts
    - Avoid vague terms like "good", "nice", "thing"
    - Keep semantic clarity

    OUTPUT FORMAT:
    [
    ["subject", "relation", "object"],
    ["subject", "relation", "object"]
    ]
    """

    import json
    import re
    import time as _time

    for i in range(0, len(headlines), batch_size):
        _time.sleep(2)
        batch = headlines[i:i + batch_size]
        print(f"Processing batch {i // batch_size + 1}...")

        user_prompt = f"Extract high-quality triplets from these headlines:\n{chr(10).join(batch)}"

        try:
            # 🆕 (2026-09-10) บังคับ Typhoon เสมอสำหรับขั้นนี้ - triplet JSON เพี้ยนกับ NVIDIA NIM
            # (nemotron super/ultra ทั้งคู่ต้อง "JSON recovery" 5/7 batch, deepseek ผ่าน NIM ช้า) - งาน
            # structured extraction ล้วน ไม่มีความเสี่ยงหลอนแบบ report generation (ข้อ 19) - Typhoon
            # ใช้ทำขั้นนี้ในรัน Social/Paper ก่อนหน้าสำเร็จมาแล้ว
            # 🆕 (2026-09-15) เปลี่ยนเป็น AWS Bedrock (คนละ infra กับ NVIDIA NIM ที่เจอปัญหา
            # เดิม) - เจ้าของงานสั่งเลิกใช้ Typhoon ทั้งหมด ยังไม่เคยเทส JSON reliability จุดนี้มาก่อน
            with use_bedrock():
                response = tf.client.chat.completions.create(
                    model=tf.MODEL_NAME_META,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0,
                    max_tokens=2000,
                )

            if hasattr(response, "usage") and response.usage:
                tf.total_input_tokens += getattr(response.usage, "prompt_tokens", 0)
                tf.total_output_tokens += getattr(response.usage, "completion_tokens", 0)

            raw_content = response.choices[0].message.content.strip()
            raw_content = strip_gemma_thought(raw_content)  # 🆕 บรรทัดเดียวที่ต่างจากต้นฉบับ

            match = re.search(r"(\[.*\])", raw_content, re.DOTALL)
            if match:
                json_str = match.group(1)
                json_str = re.sub(r",\s*\]", "]", json_str)
                json_str = json_str.replace("\n", " ").replace("\r", "")

                try:
                    batch_data = json.loads(json_str)
                    all_results.extend(batch_data)
                except json.JSONDecodeError:
                    print(f"⚠️ Batch {i // batch_size + 1}: Standard JSON failed, attempting recovery...")
                    sub_matches = re.findall(r'\[\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*"[^"]*"\s*\]', json_str)
                    if sub_matches:
                        for sub_match in sub_matches:
                            all_results.append(json.loads(sub_match))
                        print(f"✅ Recovered {len(sub_matches)} triplets from Batch {i // batch_size + 1}")
                    else:
                        print(f"❌ Batch {i // batch_size + 1}: Recovery failed.")
            else:
                print(f"⚠️ Batch {i // batch_size + 1}: No JSON array found.")

        except Exception as e:
            print(f"❌ Batch {i // batch_size + 1} fatal error: {e}")
            continue

    return all_results


def _normalize_entity(name):
    """🆕 (2026-09-12, audit M2) normalize entity ที่สะกดต่างกันเล็กน้อย (เช่น "ceramide"/"ceramides")
    ให้รวม node เดียวกันก่อนทำ community detection - heuristic เบาๆ ไม่พึ่ง NLP library ใหม่ (ไม่มี
    nltk/spacy ติดตั้งอยู่): lowercase + ตัด plural suffix แบบอนุรักษ์นิยม (ยกเว้นคำที่ลงท้าย
    ss/us/is/ous ที่มักไม่ใช่พหูพจน์จริง เช่น "gas", "virus", "analysis")"""
    s = str(name).strip().lower()
    if len(s) >= 4 and s.endswith("s") and not s.endswith(("ss", "us", "is", "ous")):
        s = s[:-1]
    return s


def build_trend_graph(triplets, n_consensus_runs=20, consensus_threshold=0.5, base_seed=42):
    """🆕 (2026-09-12, audit M2) เหมือน tf.build_trend_graph() แต่แก้ 2 จุดที่ทำให้คลัสเตอร์ไม่เสถียร:

    1. **Entity normalization** - เดิมใช้ entity string ดิบเป็น node ตรงๆ ทำให้ "ceramide"/"ceramides"
       กลายเป็นคนละ node ทั้งที่ควรนับรวมกัน - normalize ก่อนสร้าง node (ดู _normalize_entity ด้านบน)
       เก็บรูปแบบดั้งเดิมที่พบบ่อยสุดไว้แสดงผล (ไม่ใช้รูปแบบที่ normalize แล้วโชว์ตรงๆ เพราะอ่านไม่เป็น
       ธรรมชาติ)

    2. **Consensus clustering** - เดิมเรียก `nx_community.louvain_communities(G)` ไม่ fix seed เลย ทำให้
       รันซ้ำด้วย triplets ชุดเดียวกันเป๊ะได้คลัสเตอร์/ชื่อเทรนด์ไม่ซ้ำเดิมเลย (เทสจริง: รันสาย Paper ซ้ำ
       หัวข้อเดิม pool ขนาดเท่าเดิม (106) ชื่อเทรนด์ตรงกับรอบก่อน 0/5) - แก้ด้วยการรัน Louvain
       `n_consensus_runs` ครั้ง (default 20) ด้วย seed ต่างกัน นับว่าแต่ละคู่ node ที่มี edge ถึงกันอยู่
       กลุ่มเดียวกันกี่ครั้ง แล้วสร้าง "consensus graph" ที่เก็บเฉพาะคู่ที่อยู่กลุ่มเดียวกัน
       >= `consensus_threshold` (default 50%) ของรอบทั้งหมด - คลัสเตอร์สุดท้าย = connected component
       ของ consensus graph นี้ (node ที่จับกลุ่มไม่แน่นอนข้าม seed จะหลุดออกมาเป็น singleton แทนที่จะถูก
       บังคับรวมเข้ากลุ่มใดกลุ่มหนึ่งแบบสุ่ม)

    คืนค่ารูปแบบเดียวกับ tf.build_trend_graph() ทุกประการ (G, list ของ list คำ) - เรียกแทนที่
    `tf.build_trend_graph()` ได้ตรงๆ ไม่ต้องแก้โค้ดอื่นที่ใช้ผลลัพธ์
    """
    import networkx as nx
    from collections import defaultdict
    from networkx.algorithms import community as nx_community

    G = nx.Graph()
    display_counts = defaultdict(lambda: defaultdict(int))  # normalized -> {original_form: count}

    for triplet in triplets:
        if len(triplet) != 3:
            continue
        subj_raw, rel, obj_raw = triplet
        subj, obj = _normalize_entity(subj_raw), _normalize_entity(obj_raw)
        display_counts[subj][str(subj_raw).strip()] += 1
        display_counts[obj][str(obj_raw).strip()] += 1

        for node in [subj, obj]:
            if not G.has_node(node):
                G.add_node(node, count=1, label="Entity")
            else:
                G.nodes[node]['count'] += 1

        if G.has_edge(subj, obj):
            G[subj][obj]['weight'] += 1
        else:
            G.add_edge(subj, obj, relation=rel, weight=1)

    if len(G.nodes) == 0:
        return G, []

    co_occurrence = defaultdict(int)
    for i in range(n_consensus_runs):
        communities_i = nx_community.louvain_communities(G, seed=base_seed + i)
        node_to_comm = {}
        for ci, comm in enumerate(communities_i):
            for node in comm:
                node_to_comm[node] = ci
        for u, v in G.edges():
            if node_to_comm.get(u) == node_to_comm.get(v):
                co_occurrence[(u, v)] += 1

    consensus_G = nx.Graph()
    consensus_G.add_nodes_from(G.nodes())
    for (u, v), count in co_occurrence.items():
        if count / n_consensus_runs >= consensus_threshold:
            consensus_G.add_edge(u, v, weight=count / n_consensus_runs)

    communities = list(nx.connected_components(consensus_G))

    # แปลง node ที่ normalize แล้วกลับเป็นรูปแบบดั้งเดิมที่พบบ่อยสุด ก่อนคืนค่า (ให้อ่านเป็นธรรมชาติ
    # เหมือนเดิม - caller ทั้งหมดใช้ค่านี้แค่แสดงผล/ป้อน LLM ไม่ได้ผูกกับ node key ของ G โดยตรง)
    display_map = {norm: max(counts.items(), key=lambda kv: kv[1])[0] for norm, counts in display_counts.items()}
    communities_display = [[display_map.get(n, n) for n in comm] for comm in communities]

    return G, communities_display


LONGEVITY_WEIGHTS = {"D1": 12, "D2": 10, "D3": 11, "D4": 6, "D5": 6}
LONGEVITY_BANDS = [
    (90, "durable"),          # 🆕 (2026-09-11, §10.3) 85 -> 90: สายเดียว "durable" ไม่ได้จริง -
    (70, "likely_durable"),   #    single-stream สูงสุด = raw 35 -> 85 = "likely_durable"; "durable"
    (55, "leaning_durable"),  #    สงวนให้เฉพาะที่ cross-source ยืนยัน (D2 0->1 = +10 -> 95)
    (40, "undetermined"),
    (25, "leaning_fad"),
    (0, "likely_fad"),
]


def _longevity_band(score: int) -> str:
    """แถบคะแนนจาก LONGEVITY_BANDS - ใช้ร่วมกันทุกจุดที่คำนวณ/ปรับคะแนน longevity"""
    return next(name for floor, name in LONGEVITY_BANDS if score >= floor)


# 🆕 (2026-09-11, §10.2) Novelty / ingredient-maturity headwind - deterministic ไม่ยิง LLM
# actives ที่พิสูจน์มานาน (decades) = สัญญาณ "โครงสร้างจริง" ไม่ใช่ของใหม่ที่อาจดับ
_MATURE_ACTIVES = frozenset({
    "niacinamide", "retinol", "retinoid", "retinal", "retinaldehyde", "tretinoin", "adapalene",
    "vitamin c", "ascorbic", "ascorbyl", "hyaluronic", "sodium hyaluronate", "ceramide",
    "salicylic", "bha", "glycolic", "lactic", "mandelic", "aha", "pha", "benzoyl peroxide",
    "azelaic", "zinc", "zinc oxide", "titanium dioxide", "panthenol", "peptide", "collagen",
    "spf", "sunscreen", "uv filter", "avobenzone", "octocrylene", "tinosorb", "mexoryl",
    "urea", "glycerin", "squalane", "allantoin", "centella", "cica", "madecassoside", "aloe",
    "kojic", "arbutin", "tranexamic", "shea", "argan", "jojoba", "clay", "charcoal",
    "amino acid", "vitamin e", "vitamin b5", "caffeine", "green tea", "witch hazel",
})
# actives / เทคที่ยังใหม่/หลักฐานบาง (เข้าตลาด ~2021+) = ยังไม่พิสูจน์ว่าอยู่ยาว
_NOVEL_ACTIVES = frozenset({
    "pdrn", "polydeoxyribonucleotide", "polynucleotide", "salmon dna", "exosome",
    "growth factor", "epidermal growth factor", "egf", "postbiotic", "probiotic", "prebiotic",
    "lysate", "ferment filtrate", "spermidine", "nad", "nmn", "ectoin", "ectoine",
    "encapsulat", "n-capsule", "nanocapsule", "microbiome",  # microbiome-as-hero = ยังใหม่
    "copper tripeptide", "bioregulator", "stem cell", "pdt", "blue light",
})
_NOVELTY_NAME_SIGNALS = ("regenerativ", "innovation", "next-gen", "next gen", "breakthrough",
                         "encapsulat", "biotech", "microbiome-first")


def novelty_headwind(trend_name: str, key_ingredients) -> list:
    """คืน ["E"] ถ้าคลัสเตอร์พึ่ง active/เทคที่ยังใหม่เป็นแกนหลัก (มิฉะนั้น []) - ดู
    Longevity Score v2 §10.2. เกณฑ์ (อนุรักษนิยม - ยิงเมื่อชัดเท่านั้น):
      1) ชื่อเทรนด์มีคำ novel เอง (encapsulated / microbiome-first / PDRN ...) หรือคำบอกความใหม่
         (regenerative / innovation / biotech), **และ** ไม่มี mature active เด่นในชื่อ, หรือ
      2) นับ ingredient: novel >= 2 ตัว และ mature ไม่ได้มากกว่า novel เกิน 1 เท่า
    """
    name = (trend_name or "").lower()
    ings = [str(x).lower() for x in (key_ingredients or [])]
    blob = name + " || " + " , ".join(ings)

    novel_hits = sorted({t for t in _NOVEL_ACTIVES if t in blob})
    mature_hits = sorted({t for t in _MATURE_ACTIVES if t in blob})

    name_novel = any(t in name for t in _NOVEL_ACTIVES) or any(s in name for s in _NOVELTY_NAME_SIGNALS)
    name_has_mature_anchor = any(t in name for t in _MATURE_ACTIVES)

    if name_novel and not name_has_mature_anchor:
        return ["E"]
    if len(novel_hits) >= 2 and len(mature_hits) <= len(novel_hits) + 1:
        return ["E"]
    return []


def compute_longevity(payload: dict, cross_source_confirmed: bool = False) -> dict:
    """แปลง verdict ต่อมิติจาก LLM เป็นคะแนน 5-95 แบบ deterministic - ห้ามให้ LLM คิดเลขคะแนนเอง

    ดู Detail/05 งานที่ยังไม่ได้ทำ/Longevity Score v2 — เกณฑ์ตัดสินความยั่งยืนของเทรนด์.md §4 สำหรับ
    เหตุผลเต็ม (สรุปสั้น: v1 ขอเลข 0-100 จากโมเดลตรงๆ แล้วพบว่ากระจุกที่ 82/88 เกือบทุกคลัสเตอร์ -
    อาการ "score clustering" ที่รู้จักกันในงานวิจัย LLM-as-a-Judge - v2 ให้โมเดลตัดสินแค่ verdict
    3 ทาง (+1/0/-1) ต่อมิติ แล้วให้โค้ดคำนวณคะแนนแทน)

    payload: ค่าใน key "longevity" ที่ LLM ส่งกลับมา (dict มี D1-D5 + headwind)
    cross_source_confirmed: ต้องมาจาก code ที่รู้ข้อมูลข้ามสายจริง (เช่น rank_trends.py) ไม่ใช่ LLM
        เดา - ยังไม่มี caller ไหนส่งค่า True เข้ามาจริงในตอนนี้ (2026-09-08) เพราะ
        summarize_trend_clusters() วิเคราะห์ทีละสาย ไม่เห็นข้อมูลข้ามสาย ณ จุดที่เรียกฟังก์ชันนี้
    """
    dims = {k: payload[k] for k in LONGEVITY_WEIGHTS}
    if cross_source_confirmed:
        dims["D2"] = {**dims["D2"], "verdict": 1, "note": "forced by pipeline: cross-source"}

    raw = sum(LONGEVITY_WEIGHTS[k] * int(dims[k]["verdict"]) for k in LONGEVITY_WEIGHTS)
    n_headwind = len(set(payload.get("headwind", {}).get("types", [])))
    penalty = 0 if n_headwind == 0 else (-10 if n_headwind == 1 else -20)
    score = max(5, min(95, 50 + raw + penalty))

    coverage = sum(1 for k in LONGEVITY_WEIGHTS if (dims[k].get("evidence") or "").strip())
    band = _longevity_band(score)

    return {
        "score": score,
        "band": band,
        "evidence_coverage": coverage,
        "insufficient_evidence": coverage <= 2,
        "headwind_types": sorted(set(payload.get("headwind", {}).get("types", []))),
        "breakdown": {k: int(dims[k]["verdict"]) for k in LONGEVITY_WEIGHTS},
    }


def recompute_longevity_score(breakdown: dict, headwind_types: list, cross_source_confirmed: bool = False,
                              comparative_delta: int = 0) -> dict:
    """เหมือน compute_longevity() แต่รับ breakdown ที่คำนวณไว้แล้ว (dict {"D1": 1, "D2": 0, ...})
    แทนที่จะรับ payload ดิบจาก LLM (dict ที่มี evidence/verdict/note ต่อมิติ) - ใช้ตอน**คำนวณคะแนน
    ใหม่หลังรู้ข้อมูลข้ามสายแล้ว** (เช่น หลัง rank_trends.py's build_keyword_stream_index() ยืนยันว่า
    ธีมนี้เจอในสายอื่นจริง) โดยไม่ต้องเรียก LLM ซ้ำเลย เพราะ D1/D3/D4/D5 ไม่เปลี่ยนตามข้อมูลข้ามสาย

    ดู Detail/05 งานที่ยังไม่ได้ทำ/Longevity Score v2 — เกณฑ์ตัดสินความยั่งยืนของเทรนด์.md §2 (D2)
    - "cross_source_confirmed ต้องมาจาก code ที่รู้ข้อมูลข้ามสายจริง ไม่ใช่ LLM เดา"

    breakdown/headwind_types: มาจากคอลัมน์ "Longevity Breakdown"/"Longevity Headwind Types" ที่
    summarize_trend_clusters() บันทึกไว้ตอนคำนวณครั้งแรก (evidence_coverage ไม่เปลี่ยนตามการเรียกนี้
    เพราะ D2 ที่ถูก override ไม่ใช่มิติที่ "ไม่มีหลักฐาน" - โค้ดรู้แน่ชัดจากข้อมูลจริง ไม่ใช่การเดา)

    comparative_delta: 🆕 (2026-09-11, §10.1) ส่วนปรับจาก comparative pass (จัดอันดับสัมพัทธ์ในสาย) -
        มาจากคอลัมน์ "Longevity Comparative Delta" ที่ summarize_trend_clusters() บันทึกไว้ ต้องบวกกลับ
        ทุกครั้งที่ recompute เพราะเป็นส่วนที่ไม่ได้อยู่ใน breakdown/headwind
    """
    dims = dict(breakdown)
    if cross_source_confirmed:
        dims["D2"] = 1

    raw = sum(LONGEVITY_WEIGHTS[k] * int(dims[k]) for k in LONGEVITY_WEIGHTS)
    n_headwind = len(set(headwind_types))
    penalty = 0 if n_headwind == 0 else (-10 if n_headwind == 1 else -20)
    score = max(5, min(95, 50 + raw + penalty + int(comparative_delta or 0)))
    band = _longevity_band(score)

    return {"score": score, "band": band, "breakdown": dims}


def summarize_trend_clusters(clusters, triplets, top_n=10):
    """เหมือน tf.summarize_trend_clusters() แต่เพิ่ม max_tokens (ต้นฉบับไม่มีเลย)

    ⚠️ (2026-09-01, ข้อ 29 ใน Backlog) `triplets` ไม่ได้ถูกใช้จริงในต้นฉบับด้วยซ้ำ (เก็บไว้เผื่ออนาคต
    ตามที่เห็นใน signature เดิม) - คัดลอกพฤติกรรมเดิมมาเป๊ะ ไม่แก้ตรงนี้ เพราะอยู่นอกขอบเขตงานนี้

    ทำไมต้องมี max_tokens: ทุกจุดที่เรียก LLM ในฟังก์ชันนี้ (และ extract_beauty_triplets,
    extract_strategic_keywords) ไม่เคยกำหนด max_tokens เลยในต้นฉบับ - ปลอดภัยกับ GPT-5.6-Luna ที่ใช้
    อยู่ตอนนี้ (ไม่มีพฤติกรรม thinking ที่ควบคุมไม่ได้) แต่เป็นความเสี่ยงแฝงถ้าจะสลับโมเดลในอนาคต (พิสูจน์
    แล้วจริงกับ Gemma - ตอบยาวจน timeout/ไม่จบ) เพิ่ม cap ไว้ล่วงหน้าทุกจุดเป็นการป้องกันเชิงรุก

    🆕 (2026-09-08, Backlog ข้อ 32/33) `"score": 50` เดิม (ไม่มี rubric กำกับเลย) ถูกแทนที่ด้วย
    schema "longevity" 5 มิติ + headwind - ดูเหตุผลเต็มที่ Detail/05 งานที่ยังไม่ได้ทำ/Longevity
    Score v2 — เกณฑ์ตัดสินความยั่งยืนของเทรนด์.md - LLM ตอบแค่ verdict ต่อมิติ (+1/0/-1) ไม่ตอบ
    ตัวเลขคะแนนเอง แล้ว compute_longevity() ด้านบนคำนวณคะแนนจริงแบบ deterministic

    🆕 (2026-09-11, Backlog ข้อ 39) **บังคับ Typhoon json_object** สำหรับขั้นนี้ (เหมือน select_top_news)
    - เทส json_schema strict ทุกโมเดลแล้ว: มีแค่ nemotron-ultra-550b ที่บังคับ schema จริง แต่พอเจอ
      prompt เต็ม (rubric + calibration examples) ก็คืน control char / `{{` / ว่าง 3/3 (super/lightning/
      deepseek/gemini แย่กว่า) → pydantic/json_schema ไม่ช่วยกับ endpoint/โมเดลที่มี
    - Typhoon json_object จาก 2 รอบเต็มล่าสุด (Social/News) ได้ 4/5 และ 5/5 (ไม่ใช่ 0) - เร็ว 2-3s
    - ปัญหาที่เหลือแก้ด้วย post-processing: (1) ~1/5 unescaped quote → `safe_json_parse` (recovery) +
      strip control chars (2) ~ครึ่ง Typhoon เอา cluster_text มาใส่เป็น trend_name → detect
      (comma ≥3 / ยาว >70) แล้วยิง Typhoon สั้นๆ 1 ครั้ง ตั้งชื่อใหม่ 3-6 คำ
    - triplet/keyword ก็บังคับ Typhoon (json_object, เร็ว)
    """
    import pandas as pd

    summary_data = []
    if not clusters:
        return pd.DataFrame()

    sorted_clusters = sorted(clusters, key=len, reverse=True)
    limit = top_n if top_n is not None else len(sorted_clusters)

    print(f"กำลังวิเคราะห์ทั้งหมด {limit} กลุ่มเทรนด์ (Ingredient + Benefit)...")

    system_prompt = """You are a Strategic Market Researcher evaluating a beauty trend cluster.

STRICT RULES:
- For every dimension below, you MUST quote real text from the input data BEFORE giving a verdict.
  Never decide the verdict first.
- **Default every verdict to 0.** Move to +1 ONLY when the exact criterion is met by a specific,
  concrete quote - not by a plausible-sounding or generic statement. "Growing demand", "consumers
  want", "interest in wellness" are NOT evidence of anything - they are 0.
- Move to -1 when the negative criterion clearly applies.
- Do not use outside knowledge except for dimension H (headwind), where you must state where you
  know it from.
- Market-forecast numbers (CAGR, market size, target year) do NOT count as mechanism evidence.
- Skepticism is correct. A cluster where 4-5 dimensions are +1 is rare - it must be a textbook
  case with explicit mechanisms AND a stated permanent problem AND named cross-category use.

Score each of these 5 dimensions as one of three verdicts: positive / neutral / negative.
In the JSON output, encode these as the integers 1, 0, or -1. NEVER write a "+" sign before a
positive number (e.g. write 1, not +1) - a leading "+" is invalid JSON and will break parsing.

D1 Structural vs one-off event
   +1 = the text names a SPECIFIC ingredient mechanism, a SPECIFIC regulation, or a SPECIFIC
        documented shift in consumer values (with the shift described, not just asserted)
    0 = cannot tell, OR only market-outlook numbers, OR only general "demand is growing" language,
        OR the cluster is essentially one branded product / product line (e.g. named gloss, named
        serum), OR it is a retail/distribution/marketing tactic rather than a product trend
   -1 = tied to season/holiday, a single viral campaign, or celebrity/media push; or the cluster's
        own name cites a target year as its main justification (e.g. "...2030")

D2 Cross-category adaptability
   ** LEAVE THIS AT 0. ** You are looking at ONE cluster from ONE data stream - you cannot verify
   cross-category or cross-stream use. The pipeline sets this to +1 later if the keyword is
   independently confirmed in another stream.

D3 Timeless problem vs aesthetic novelty
   +1 = the text explicitly names an ever-present *health/functional* problem being solved
        (sensitive skin, acne, hair loss, body odor, sun damage, cost, convenience) - stated, not
        inferred
    0 = a mix, OR the "problem" is really a preference or experience (matte finish, glow, scent,
        texture feel, "sensory ritual", "premium feel", transparency/credibility, minimalism)
   -1 = driven mainly by scent/theme/fun/belonging/collectibility/aesthetic look/nostalgia

D4 Mechanism/evidence vs marketing language
   +1 = a concrete mechanism or a test result is stated in the text (e.g. "lipophilic acid
        penetrates pores", "ceramides repair the barrier", "in-vitro SPF tested")
    0 = ingredients are named but no mechanism or test is described; or only benefit claims
   -1 = vague claims with no mechanism, OR the claimed mechanism has been debunked

D5 Behavior-change friction
   +1 = drops into an existing habit with no routine change, no format change, no clear price jump,
        and the result is visible
    0 = requires some behavior adjustment, OR a new step/format, OR a higher price
   -1 = requires a significant change in usage/format/routine, a clearly higher price, or the
        result is not visible

H Headwind - list every type that applies (can be multiple, or empty []):
   A = another cluster in this same dataset directly contradicts this direction
   B = a regulator has banned/restricted/is reviewing this
   C = mainstream scientific consensus contradicts the claim
   D = an identifiable consumer anti-trend exists

Calibration examples (D2 is always 0 here - set by pipeline):

[HIGH] "Gentle Barrier-Friendly Cleansing"
D1=1 (text names the skin-barrier lipid mechanism explicitly) D2=0 D3=1 (text says "for sensitive,
reactive skin") D4=1 (text: "ceramides restore the lipid barrier") D5=1 (still a cleanser, same
step) H=[] -> high (single-stream ceiling)

[MID] "Skinification of Body Care"
D1=1 (text describes a documented shift: facial actives migrating to body) D2=0 D3=0 (the "problem"
is really a preference for elevated body care, not a stated permanent problem) D4=0 (ingredients
named, no mechanism quoted) D5=0 (adds a new step / higher price) H=[] -> middle

[MID] "Long-Wear Matte Makeup"
D1=0 (only "consumers want long wear") D2=0 D3=0 (matte finish is a preference, not a permanent
problem) D4=0 (no mechanism) D5=1 (same application habit) H=[] -> leaning-durable at best

[LOW] "Antibacterial Body Wash 2030"
D1=0 (only outlook numbers) D2=0 D3=0 D4=-1 (antibacterial efficacy is being questioned)
D5=0 H=[A,B] -> low

Return ONLY a single JSON object with this exact schema, no "score" field:
{
    "trend_name": "concise 3-6 word title, NOT a list of the input terms",
    "target": "...",
    "key_ingredients": ["...", "..."],
    "key_benefits": ["...", "..."],
    "outlook": "...",
    "reason_th": "...",
    "longevity": {
        "D1": {"evidence": "", "verdict": 0, "note": ""},
        "D2": {"evidence": "", "verdict": 0, "note": ""},
        "D3": {"evidence": "", "verdict": 0, "note": ""},
        "D4": {"evidence": "", "verdict": 0, "note": ""},
        "D5": {"evidence": "", "verdict": 0, "note": ""},
        "headwind": {"types": [], "evidence": ""}
    }
}
Keep every "evidence" quote SHORT (under 15 words) and replace any double-quote inside it with a
single quote so the JSON stays valid."""

    for i, cluster in enumerate(sorted_clusters[:limit]):
        cluster_text = ", ".join(cluster[:15])
        user_prompt = f"Analyze this beauty trend cluster: {cluster_text}"

        try:
            # 🆕 (2026-09-11, Backlog ข้อ 39) กลับมาใช้ Typhoon json_object - เทส json_schema strict
            # ทุกโมเดลแล้ว: มีแค่ ultra ที่บังคับ schema จริง แต่พอเจอ prompt เต็ม (rubric + calibration
            # examples) ก็คืน control char / `{{` / ว่าง 3/3 - Typhoon json_object จาก 2 รอบเต็มล่าสุด
            # ได้ 4/5 และ 5/5 (ไม่ใช่ 0) ปัญหาแค่ ~1/5 unescaped quote + ~ครึ่ง lazy-echo ชื่อ - แก้ด้วย
            # safe_json_parse (recovery) + control-char strip + lazy-name detect→rename
            import json
            import re

            # 🆕 (2026-09-15) เปลี่ยนจาก Typhoon -> AWS Bedrock - เจ้าของงานสั่งเลิกใช้
            # Typhoon ทั้งหมด แม้จุดนี้จะเป็น JSON-strict ที่เคยพังกับ NVIDIA NIM มาก่อนก็ตาม
            with use_bedrock():
                response = tf.client.chat.completions.create(
                    model=tf.MODEL_NAME_META,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0,
                    max_tokens=1500,
                    response_format={"type": "json_object"},
                )

            clean_res = response.choices[0].message.content.strip().replace("```json", "").replace("```", "")
            clean_res = strip_gemma_thought(clean_res)  # 🆕 no-op กับ provider อื่น (ดู use_gemma())
            clean_res = re.sub(r'([:\[,]\s*)\+(\d)', r'\1\2', clean_res)  # กัน "+1" ที่ไม่ใช่ JSON
            # 🆕 strip literal control chars (tab/newline ดิบ) ที่โผล่ใน string value - "Invalid
            # control character" ที่เจอกับ ultra/Typhoon บางครั้ง
            clean_res = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", clean_res)
            try:
                analysis = json.loads(clean_res)
            except json.JSONDecodeError:
                analysis = safe_json_parse(clean_res)  # มี recovery logic (unescaped quote ฯลฯ)
            if not analysis:
                raise ValueError("parse ไม่ได้แม้ผ่าน safe_json_parse")

            if analysis:
                # lazy-name fix: Typhoon บางครั้งเอา cluster_text มาใส่เป็น trend_name แทนชื่อสังเคราะห์
                _name = str(analysis.get("trend_name", "")).strip()
                if _name.count(",") >= 3 or len(_name) > 70 or not _name:
                    try:
                        with use_bedrock():  # 🆕 (2026-09-15) เปลี่ยนจาก Typhoon -> AWS Bedrock
                            _r = tf.client.chat.completions.create(
                                model=tf.MODEL_NAME_META,
                                messages=[{"role": "user", "content":
                                           f"Give a catchy 3-6 word English title for a beauty trend "
                                           f"about: {cluster_text}. Reply with ONLY the title."}],
                                temperature=0.2, max_tokens=30,
                            )
                        _new = (_r.choices[0].message.content or "").strip().strip('"').strip()
                        if _new and _new.count(",") < 2:
                            analysis["trend_name"] = _new
                            print(f"    ✏️  Cluster {i + 1}: rename lazy → {_new!r}")
                    except Exception:
                        pass

                longevity_payload = analysis.get("longevity")
                # 🆕 (2026-09-11, Backlog B4) บังคับ D2 verdict = 0 ที่ขั้นนี้เสมอ - LLM เห็นแค่คลัสเตอร์
                # เดียวจากสายเดียว ตัดสิน "cross-category adaptability" จริงไม่ได้ แต่ Typhoon มักตอบ +1
                # (+10 คะแนน ดันไป 95 หมด) - rank_trends.apply_cross_source_confirmation() จะ recompute
                # เป็น +1 ทีหลังเฉพาะคลัสเตอร์ที่คีย์เวิร์ดยืนยันในอีกสายจริง
                if isinstance(longevity_payload, dict) and isinstance(longevity_payload.get("D2"), dict):
                    longevity_payload["D2"] = {**longevity_payload["D2"], "verdict": 0,
                                                "note": "pipeline: cross-source ยังไม่ยืนยัน"}
                # 🆕 (2026-09-11, §10.2) novelty headwind - deterministic: ถ้าคลัสเตอร์พึ่ง active/เทค
                # ที่ยังใหม่ (PDRN/exosome/encapsulation/microbiome-as-hero ...) เป็นแกน -> headwind "E"
                _nov = novelty_headwind(analysis.get("trend_name", ""), analysis.get("key_ingredients"))
                if _nov and isinstance(longevity_payload, dict):
                    _hw = longevity_payload.setdefault("headwind", {})
                    _types = list(_hw.get("types") or [])
                    if "E" not in _types:
                        _types.append("E")
                        _hw["types"] = _types
                        _hw["evidence"] = ((_hw.get("evidence") or "")
                                           + " | pipeline: novel/unproven active as core").strip(" |")
                        print(f"    🧪 Cluster {i + 1}: novelty headwind (E) - {analysis.get('trend_name','')!r}")
                try:
                    longevity = compute_longevity(longevity_payload)
                except Exception as e:
                    print(f"⚠️ Cluster {i + 1}: ไม่มี/รูปแบบ 'longevity' ผิด ({e}) - ใช้ค่ากลางแทน")
                    longevity = {
                        "score": 50, "band": "undetermined", "evidence_coverage": 0,
                        "insufficient_evidence": True, "headwind_types": [], "breakdown": {},
                    }

                summary_data.append({
                    # 🆕 (2026-09-12, audit M4) ID คงที่ต่อคลัสเตอร์ภายในสาย/รอบนี้ - ใช้แก้ปัญหาชื่อ
                    # เทรนด์ชนกันข้ามสาย (เช่น "Barrier Repair Skincare" เจอทั้ง Paper กับ News) ที่ทำให้
                    # ข้อมูลหายเงียบๆ เมื่อ join ข้ามขั้นด้วยชื่อเทรนด์ตรงๆ - ใช้คู่กับชื่อสาย (ที่ caller
                    # รู้อยู่แล้ว) เป็น key แทนชื่อเทรนด์เปล่าๆ ในจุดที่ join ข้ามสาย
                    "Cluster ID": i,
                    "Rank": i + 1,
                    "Trend Name": analysis.get("trend_name", "Unknown Trend"),
                    "Key Ingredients": ", ".join(analysis.get("key_ingredients", [])),
                    "Key Benefits": ", ".join(analysis.get("key_benefits", [])),
                    "Members": cluster_text[:60] + "...",
                    # 🆕 (2026-09-01, ข้อ 30 ใน Backlog) ต้นฉบับตัด "Members" เหลือ preview 60
                    # ตัวอักษรแล้วทิ้งจำนวนจริงไปเลย - ไม่มีที่ไหนบันทึกขนาดคลัสเตอร์จริงไว้ใช้ต่อ
                    # (ต้องใช้เป็นส่วนหนึ่งของ Rank Score - ดู rank_trends.py) เพิ่มคอลัมน์นี้แยกไว้
                    "Cluster Size": len(cluster),
                    "Target": analysis.get("target", "General Audience"),
                    "Longevity Score": longevity["score"],
                    "Longevity Band": longevity["band"],
                    "Longevity Evidence Coverage": longevity["evidence_coverage"],
                    "Longevity Insufficient Evidence": longevity["insufficient_evidence"],
                    "Longevity Headwind Types": ", ".join(longevity["headwind_types"]),
                    # 🆕 (2026-09-08, Backlog ข้อ 33 "กลุ่ม B") เก็บ verdict ดิบต่อมิติไว้ (ไม่ใช่แค่
                    # คะแนนรวม) เพื่อให้ rank_trends.py คำนวณคะแนนใหม่ได้หลังรู้ว่าธีมนี้ยืนยันข้ามสาย
                    # จริงหรือไม่ (ผ่าน recompute_longevity_score() ด้านบน) โดยไม่ต้องเรียก LLM ซ้ำ
                    "Longevity Breakdown": longevity["breakdown"],
                    # 🆕 (2026-09-11, §10.1) ส่วนปรับจาก comparative pass - เติมหลังลูปจบ (ดู
                    # _comparative_longevity_pass) - เก็บแยกเพื่อบวกกลับตอน recompute cross-source
                    "Longevity Comparative Delta": 0,
                    "Outlook": analysis.get("outlook", "N/A"),
                    "Analysis (Thai)": analysis.get("reason_th", "-"),
                })

            if hasattr(response, "usage") and response.usage:
                tf.total_input_tokens += getattr(response.usage, "prompt_tokens", 0)
                tf.total_output_tokens += getattr(response.usage, "completion_tokens", 0)

        except Exception as e:
            print(f"⚠️ Cluster {i + 1} failed: {e}")
            continue

    summary_data = _comparative_longevity_pass(summary_data)
    return pd.DataFrame(summary_data)


_COMPARATIVE_TIER_DELTA = {"most": 0, "middle": -12, "least": -22}


def _comparative_longevity_pass(rows: list) -> list:
    """🆕 (2026-09-11, §10.1) Comparative pass - จัดอันดับ durability *สัมพัทธ์ในสายเดียว* แล้วปรับ
    คะแนน absolute ตาม tier. เหตุผล: LLM อ่อน (Typhoon) ตอบ "A ยั่งยืนกว่า B ไหม" ได้ดีกว่า "A เป็น
    8 หรือ 9" มาก + บังคับ spread เพื่อแก้อาการ 85 กระจุก (ดู Longevity Score v2 §6.3, §10.1)

    - ยิง Typhoon **ครั้งเดียว** ต่อสาย, forced strict ranking + tier (most ≤2 / least ≥1 / middle ที่เหลือ)
    - delta: most 0 / middle -12 / least -22 -> ปรับ "Longevity Score" + "Longevity Band" + เก็บ
      "Longevity Comparative Delta" ไว้บวกกลับตอน rank_trends recompute cross-source
    - ข้ามถ้าคลัสเตอร์ < 3 (เทียบไม่มีความหมาย) หรือ Typhoon จับคู่ชื่อไม่ได้ >40% (ถือว่าเชื่อไม่ได้)
    """
    import json
    import re

    if len(rows) < 3:
        return rows

    listing = "\n".join(
        f'[{n + 1}] "{r["Trend Name"]}" — {str(r.get("Outlook", ""))[:180]}'
        for n, r in enumerate(rows)
    )
    n = len(rows)
    n_most = 2 if n >= 4 else 1
    sys_p = (
        "You are ranking beauty-trend clusters by DURABILITY relative to each other - which is most "
        "likely to still be a meaningful market force in 5 years. You are NOT scoring them absolutely; "
        "you are ordering THIS specific set. A strict order is required - no ties.\n"
        f"Rank all {n} from 1 (most durable) to {n} (least). Then assign tiers: the top {n_most} = "
        '"most", the bottom 1 = "least", everyone else = "middle". Judge on: anchored to an '
        "ever-present functional problem vs a look/preference; built on a decades-proven mechanism vs "
        "a brand-new active; a broad category shift vs one product line or one marketing tactic.\n"
        'Return ONLY JSON: {"ranking": ["<exact trend name>", ... most-durable first], '
        '"tiers": {"<exact trend name>": "most|middle|least", ...}}'
    )
    try:
        with use_bedrock():  # 🆕 (2026-09-15) เปลี่ยนจาก Typhoon -> AWS Bedrock
            resp = tf.client.chat.completions.create(
                model=tf.MODEL_NAME_META,
                messages=[{"role": "system", "content": sys_p},
                          {"role": "user", "content": listing}],
                temperature=0, max_tokens=600,
                response_format={"type": "json_object"},
            )
        raw = resp.choices[0].message.content.strip().replace("```json", "").replace("```", "")
        raw = strip_gemma_thought(raw)
        raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", raw)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = safe_json_parse(raw) or {}
        tiers = parsed.get("tiers") or {}

        def _match(name):
            name_l = str(name).strip().lower()
            for r in rows:
                if r["Trend Name"].strip().lower() == name_l:
                    return r
            for r in rows:  # loose contains
                a, b = r["Trend Name"].strip().lower(), name_l
                if a and b and (a in b or b in a):
                    return r
            return None

        matched = {}
        for name, tier in tiers.items():
            r = _match(name)
            if r is not None and tier in _COMPARATIVE_TIER_DELTA:
                matched[id(r)] = (r, tier)
        if len(matched) < max(3, int(0.6 * len(rows))):
            print(f"    ⚠️ comparative pass: จับคู่ชื่อได้แค่ {len(matched)}/{len(rows)} - ข้าม (ไม่ปรับ)")
            return rows

        for r, tier in matched.values():
            delta = _COMPARATIVE_TIER_DELTA[tier]
            # gate: ปรับเฉพาะแถวที่เกาะเพดาน (>=70) - จุดประสงค์คือคลาย "85 กระจุก" ไม่ใช่ลงโทษซ้ำแถว
            # ที่รูบริกให้คะแนนต่ำอยู่แล้ว (มันถูกแยกออกจากกลุ่มด้วย verdict ของตัวเองแล้ว)
            if delta == 0 or int(r["Longevity Score"]) < 70:
                continue
            new_score = max(5, min(95, int(r["Longevity Score"]) + delta))
            r["Longevity Comparative Delta"] = delta
            r["Longevity Score"] = new_score
            r["Longevity Band"] = _longevity_band(new_score)
        spread = sorted({r["Longevity Score"] for r in rows})
        print(f"    🪜 comparative pass: tiers={[(r['Trend Name'][:28], t) for r, t in matched.values()]}")
        print(f"       -> Longevity spread: {spread}")
    except Exception as e:
        print(f"    ⚠️ comparative pass ล้มเหลว (ไม่กระทบผลหลัก): {e}")

    return rows


def extract_strategic_keywords(df_trends):
    """เหมือน tf.extract_strategic_keywords() แต่เพิ่ม max_tokens (ต้นฉบับไม่มีเลย - ดู docstring
    ของ summarize_trend_clusters() ด้านบนสำหรับเหตุผลเต็ม)

    หมายเหตุ: ยังไม่ได้แก้ข้อ 17 ใน Backlog (ไม่มีพารามิเตอร์รับหัวข้อโจทย์ ทำให้คีย์เวิร์ดสาย Paper
    เอนไปทางสกินแคร์ทั่วไป) - เจ้าของงานสั่งพักไว้ก่อนตอน Phase 1 ยังไม่ได้แก้ในรอบนี้เช่นกัน
    """
    import pandas as pd

    print("🔍 Extracting strategic keywords (Search, Hooks, Vibes, Product Search) from trends...")
    all_trend_keywords = []

    system_prompt = """You are a Google Search & SEO Specialist for the Beauty Industry.
    Your task is to generate high-impact, Google Trends-optimized keywords.

    STRICT OUTPUT RULES:
    - Each keyword MUST be 1-3 words ONLY.
    - NO full sentences.
    - NO punctuation except spaces.
    - NO stopwords like: "and", "that", "for", "with", "to".
    - ALL keywords must be UNIQUE (no duplicates across categories or within categories).
    - Use lowercase only.
    - Avoid repeating the same root word excessively (e.g., "serum", "vit c serum", "brightening serum" -> keep only the most valuable variations).

    CATEGORY RULES:
    1. Search_Terms:
    - Natural Google search queries
    - High intent, commonly searched
    - Example: "vit c serum", "acne gel"

    2. Product_Hooks:
    - Short marketing phrases
    - Emotional or benefit-driven
    - Example: "glass skin", "instant glow"

    3. Aesthetic_Vibes:
    - Beauty trends, styles, moods
    - Social media driven
    - Example: "clean girl", "dewy skin"

    4. Product_Search_Keywords:
    - Specific product types or formats
    - Must be purchasable items
    - Example: "gel moisturizer", "tone up cream"

    DEDUPLICATION LOGIC:
    - Remove exact duplicates
    - Remove near-duplicates with same meaning
    - Prefer the shortest, most popular version

    OUTPUT FORMAT:
    Return ONLY valid JSON:
    {
        "keywords": {
            "Search_Terms": [],
            "Product_Hooks": [],
            "Aesthetic_Vibes": [],
            "Product_Search_Keywords": []
        }
    }
    """

    for index, row in df_trends.iterrows():
        trend_name = row.get("Trend Name", f"Trend {index}")
        context_text = (f"Trend: {trend_name} | Ingredients: {row.get('Key Ingredients', '')} | "
                         f"Benefits: {row.get('Key Benefits', '')}")

        try:
            # 🆕 (2026-09-10) บังคับ Typhoon เสมอ - structured JSON เหมือน summarize_trend_clusters /
            # extract_beauty_triplets ที่เพิ่งบังคับ Typhoon เพราะ NVIDIA NIM ทำ JSON ไม่นิ่ง
            # 🆕 (2026-09-15) เปลี่ยนเป็น AWS Bedrock - เจ้าของงานสั่งเลิกใช้ Typhoon ทั้งหมด
            with use_bedrock():
                response = tf.client.chat.completions.create(
                    model=tf.MODEL_NAME_META,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Analyze this trend:\n{context_text}"},
                    ],
                    temperature=0.1,
                    max_tokens=800,  # 🆕 ต้นฉบับไม่มี - ดู docstring ของ summarize_trend_clusters()
                    # บอก shim ว่าต้องได้ JSON จะได้เรียกซ้ำเมื่อตอบมั่ว (เจอจริงที่จุดนี้ในรอบรัน 2026-09-15)
                    response_format={"type": "json_object"},
                )

            if hasattr(response, "usage") and response.usage:
                tf.total_input_tokens += getattr(response.usage, "prompt_tokens", 0)
                tf.total_output_tokens += getattr(response.usage, "completion_tokens", 0)

            data = safe_json_parse(response.choices[0].message.content)  # strip_gemma_thought อยู่ในนี้แล้ว

            if data and "keywords" in data:
                kw = data["keywords"]
                all_trend_keywords.append({
                    "Trend Name": trend_name,
                    "Search_Keywords": ", ".join(kw.get("Search_Terms", [])),
                    "Marketing_Hooks": ", ".join(kw.get("Product_Hooks", [])),
                    "Visual_Vibes": ", ".join(kw.get("Aesthetic_Vibes", [])),
                    "Product_Search_Keywords": ", ".join(kw.get("Product_Search_Keywords", [])),
                })
        except Exception as e:
            print(f"❌ Error at {trend_name}: {e}")

    return pd.DataFrame(all_trend_keywords)
