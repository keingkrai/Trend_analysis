# -*- coding: utf-8 -*-
"""
Phase 4 — ⑭ STEPIC → ⑮ Report (2026-09-11)
ดู Detail/05 งานที่ยังไม่ได้ทำ/Workflow v2 — แยกสายแล้วรวม.md ส่วน "⑭ STEPIC → ⑮ Report"
("วิเคราะห์แรงขับ 6 ด้าน... แล้วประกอบเป็นรายงานฉบับสมบูรณ์ — เหมือนเดิมทุกประการ")

**⑬ (จับคู่สินค้า EXFAC) ข้ามไปก่อนตามที่เจ้าของงานสั่ง** ("เอา 13 ออกเดะเราคุยกันอีกที") - ส่วน
"Market Evidence" ในรายงานจึงใช้ผลจับคู่ ⑫ (Watsons 10,622 SKU จริง) แทนที่ catalog EXFAC โดยตรง

ใช้ฟังก์ชันเดิมจาก trend_final_v2.py **ตรงๆ ไม่แก้โค้ดในไฟล์นั้นเลย** (ตามหลักการ "จัดระเบียบใหม่ ใช้
ของเดิมที่พิสูจน์แล้ว"): analyze_trend() (STEPIC 6 มิติ) + integrate_stepic() (สังเคราะห์รวม) +
generate_master_markdown_report() (ประกอบรายงาน) — แค่ป้อน input ที่มาจากสถาปัตยกรรม 3 สาย v2 แทน
input เดิมที่มาจาก pipeline สายเดียวแบบเก่า:

| Input เดิมของ trend_final_v2.py | แทนที่ด้วย (v2, ข้อมูลจริงจากรอบนี้) |
|---|---|
| `trend_report` (รายงานสายเดียว) | รายงาน 3 สาย (Paper+Social+News) ต่อกัน |
| `master_report` (forecast คลัสเตอร์เดียว) | `phase2_paper_social_z_delta_result.json` (14 คลัสเตอร์จริง, Z_Delta จริง) |
| `strategix_context` (Strategic Pillar mapping) | สรุปคลัสเตอร์จริง 15 ตัว (ingredients/benefits/Z_Delta/Longevity/market coverage) - ไม่ผ่านระบบ Pillar เดิม (คนละ abstraction กับ v2) |
| `product_context`/`product_results` (Exfac pillar match) | ผล ⑫ (`phase3_scale_validation_nvidia_result.json`) - Watsons จริง 10,622 SKU |
| `llm_forecast_analysis` (Step 6-7 narrator) | คีย์ `llm_forecast_analysis` ใน `phase2_paper_social_z_delta_result.json` (🆕 2026-09-16 - เดิม None
  เพราะ Step 6-7 ใน ⑦ พังด้วย OpenRouter 402 และไม่ได้เซฟ) - ถ้าไฟล์รุ่นเก่าไม่มีคีย์นี้ ส่วน "Quantitative Cluster
  Forecasts" จะว่างเปล่า ไม่ crash (ฟังก์ชันเดิม handle None อยู่แล้ว) |

**Typhoon patch ในสคริปต์นี้เอง (ไม่แก้ bootstrap.py):** `analyze_trend()`/`integrate_stepic()` อ่าน
`client`/`MODEL_NAME` เป็น **module-level global ของ `trend_final_v2.py` เอง** (คนละตัวแปรกับที่
`common.bootstrap.use_typhoon()` แพตช์ - ตัวนั้นแพตช์ `trend_final.py` (v1) ที่ `tf` ใน bootstrap ชี้ไป)
เลยต้องมี context manager แยกต่างหากที่แพตช์ `trend_final_v2.client`/`.MODEL_NAME` โดยเฉพาะ - เขียนไว้
ในสคริปต์นี้เท่านั้น (ขอบเขตแคบ ไม่กระทบโค้ดอื่น)
"""
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import OUTPUTS, PROJECT_ROOT, prompt_run_config, record_model_used  # noqa: E402

# 🆕 (2026-09-22) ส่วนที่ใช้จริงของ trend_final_v2.py คัดลอกตรงตัวไว้ใน main/ (common/trend_final_v2_subset.py)
from common import trend_final_v2_subset as tf2  # noqa: E402

from openai import OpenAI  # noqa: E402

# 🆕 (2026-09-12, audit m1) เดิม hardcode ค่านี้ตรงๆ ไม่เคยอ่าน TREND_TOPIC เลย - ถ้าผู้ใช้ตั้งหัวข้ออื่นตอน
# เริ่ม main.py (เช่น "Global Body Wash Trends") รายงาน STEPIC/Master Report (⑭-⑮) จะยังโชว์หัวข้อเดิมนี้
# ทั้งที่ข้อมูลทั้งหมดที่วิเคราะห์จริงเป็นหัวข้อที่ผู้ใช้เลือก - ใช้ prompt_run_config() แบบเดียวกับสาย
# Paper/Social/News (ดู TOPIC ใน paper_stream.py) เพื่ออ่าน TREND_TOPIC ก่อน ตกมาที่ default นี้ถ้าไม่มี
DEFAULT_USER_QUERY = "Global beauty and personal care trends"
REPORT_CHAR_LIMIT = 8000  # ต่อสาย - เหตุผลเดียวกับ CONTENT_CHAR_LIMIT ที่ใช้ทุกจุดในโปรเจกต์นี้
STREAM_FILES = {
    "Paper": "phase1_paper_stream_result.json",
    "Social": "phase2_social_stream_result.json",
    "News": "phase2_news_stream_result.json",
}


@contextmanager
def use_typhoon_v2():
    """เหมือน common.bootstrap.use_typhoon() ทุกประการ แต่แพตช์ trend_final_v2 (tf2) แทน trend_final
    (v1) - จำเป็นเพราะ analyze_trend()/integrate_stepic() อยู่ใน v2 อ่าน client/MODEL_NAME ของตัวเอง
    ไม่ใช่ตัวที่ bootstrap.use_typhoon() แพตช์

    🆕 (2026-09-15) ไม่ใช่ default ของขั้นนี้แล้ว (ดู use_bedrock_v2() ด้านล่าง) - เก็บฟังก์ชันนี้ไว้เป็น
    ตัวเลือกสำรองที่ยังใช้งานได้จริง เหมือนหลักการที่ bootstrap.py เก็บ use_nvidia()/use_gemini()/
    use_gemma() ไว้ทั้งที่ไม่ใช่ default ของจุดไหนแล้วก็ตาม"""
    base_url = "https://api.opentyphoon.ai/v1"
    model = "typhoon-v2.5-30b-a3b-instruct"
    api_key = os.getenv("TYPHOON_API_KEY")
    if not api_key:
        raise RuntimeError("ไม่มี TYPHOON_API_KEY ใน .env")
    orig_client, orig_model = tf2.client, tf2.MODEL_NAME
    print(f"  🌀 [v2] สลับไปใช้ Typhoon ชั่วคราว (model={model})")
    record_model_used(model)  # 🆕 (2026-09-12, audit C5) - manifest ของขั้นนี้ต้องรู้ว่าเผลอใช้ fallback
    tf2.client = OpenAI(base_url=base_url, api_key=api_key)
    tf2.MODEL_NAME = model
    try:
        yield
    finally:
        tf2.client, tf2.MODEL_NAME = orig_client, orig_model
        print("  🌀 [v2] สลับกลับเป็น OpenRouter แล้ว")


@contextmanager
def use_bedrock_v2(model_id=None, region=None):
    """เหมือน common.bootstrap.use_bedrock() ทุกประการ แต่แพตช์ trend_final_v2 (tf2) แทน trend_final (v1)
    - เหตุผลเดียวกับ use_typhoon_v2() ด้านบน: analyze_trend()/integrate_stepic() อ่าน client/MODEL_NAME
    เป็น module-level global ของ tf2 เอง คนละตัวกับที่ bootstrap.use_bedrock() แพตช์ (ไม่แก้ bootstrap.py
    เอง - ขอบเขตแคบ เหมือนหลักการเดียวกับ use_typhoon_v2() ด้านบน)

    🆕 (2026-09-15) ใช้โมเดลหลัก/สำรองเดียวกับ bootstrap.use_bedrock() (MODEL_ID/FALLBACK_MODEL_ID) - เดิม
    ตั้ง Mistral Large 3 แยกไว้สำหรับขั้นนี้ แต่เทสเขียนรายงานจริง (10 เปเปอร์เดียวกัน prompt เดียวกัน) Mistral
    Large 3 โดนตัวตรวจคำหลอนฟ้องมากที่สุด (74 และ 52 คำ) ส่วน GLM-5 ต่ำสุด (22 และ 22 คำ)"""
    import boto3
    from common.bootstrap import _BedrockClientShim, use_bedrock

    mid = model_id or use_bedrock.MODEL_ID
    reg = region or os.getenv("AWS_REGION") or "us-east-1"
    bearer_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    if bearer_token:
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = bearer_token
        bedrock_client = boto3.client("bedrock-runtime", region_name=reg)
    elif access_key and secret_key:
        bedrock_client = boto3.client("bedrock-runtime", region_name=reg,
                                       aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    else:
        raise RuntimeError(
            "ยังไม่มีคีย์ AWS Bedrock ใน .env - เติม AWS_BEARER_TOKEN_BEDROCK (คีย์ ABSK) ก่อนใช้ "
            "use_bedrock_v2()"
        )

    orig_client, orig_model = tf2.client, tf2.MODEL_NAME
    print(f"  🟧 [v2] สลับไปใช้ AWS Bedrock ชั่วคราว (model={mid}, region={reg})")
    record_model_used(mid)
    tf2.client = _BedrockClientShim(bedrock_client, mid, use_bedrock.FALLBACK_MODEL_ID)
    tf2.MODEL_NAME = mid
    try:
        yield
    finally:
        tf2.client, tf2.MODEL_NAME = orig_client, orig_model
        print("  🟧 [v2] สลับกลับเป็นโมเดลเดิมแล้ว")


def load_streams():
    streams = {}
    for stream, fname in STREAM_FILES.items():
        fp = OUTPUTS / fname
        if fp.exists():
            with open(fp, encoding="utf-8") as f:
                streams[stream] = json.load(f)
    return streams


def build_merged_trend_report(streams):
    """แทนที่ `trend_report` สายเดียวเดิม - ต่อรายงาน 3 สาย (ตัดคนละ REPORT_CHAR_LIMIT ตัวอักษร กัน
    prompt ระเบิดเหมือนที่ paper_stream.py ทำกับเนื้อหาเปเปอร์ยาวๆ)"""
    parts = []
    for stream, data in streams.items():
        text = data.get("report") or data.get("paper_report") or ""
        if not text:
            continue
        parts.append(f"=== {stream.upper()} STREAM REPORT ===\n{text[:REPORT_CHAR_LIMIT]}")
    return "\n\n".join(parts)


def load_cross_source_longevity():
    """🆕 (2026-09-12, audit M1) rank_trends.py คำนวณ Longevity ที่แก้ D2 (cross-source confirmation)
    แล้วเซฟไว้ที่ phase2_longevity_cross_source_result.json - ไฟล์ stream ดิบ
    (phase1_paper_stream_result.json ฯลฯ) ที่ load_streams() อ่านไม่มีการแก้นี้ (rank_trends.py คำนวณ
    DataFrame ในหน่วยความจำ ไม่เขียนทับไฟล์ stream เดิม) ต้องโหลดมา override เอง มิฉะนั้น D2/Longevity
    Score ที่แก้แล้วจะไม่ไหลไปถึงรายงานสุดท้ายเลย ทั้งที่คำนวณถูกแล้วตั้งแต่ขั้น ⑥

    Returns:
        dict {(stream, trend_name): {"Longevity Score":..., "Longevity Band":...}} หรือ {} ถ้ายังไม่มี
        ไฟล์ (เช่น ยังไม่ได้รัน rank_trends.py รอบนี้ - ไม่ error แค่ใช้ค่าจากไฟล์ stream ดิบแทน)
    """
    path = OUTPUTS / "phase2_longevity_cross_source_result.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    lookup = {}
    for stream, rows in data.items():
        for row in rows:
            name = row.get("Trend Name")
            if name:
                lookup[(stream, name)] = row
    return lookup


def load_selected_trends():
    """🆕 (2026-09-16) ชุด Top N ที่ ⑪ คัดไว้ด้วย Rank Score ของ ⑥ (bootstrap.select_top_trends) - อ่านจากไฟล์
    ของ ⑪ ไม่คัดใหม่เอง รายงานจึงได้ชุดเดียวกับ ⑪-⑫ เป๊ะแม้ TREND_TOP_N ตอนรันขั้นนี้จะต่างไป

    คืน list เรียงตามอันดับ [{"overall_rank", "stream", "trend", ...}] หรือ None ถ้าเป็นรอบเก่าที่ ⑪ ยังไม่ได้
    บันทึกค่านี้ (รายงานใช้ทุกเทรนด์เหมือนเดิม ไม่ error)"""
    fp = OUTPUTS / "phase3_trend_highlights_result.json"
    if not fp.exists():
        return None
    with open(fp, encoding="utf-8") as f:
        return json.load(f).get("selected_trends")


def load_current_year_interest_ranks(selected):
    """🆕 (2026-09-16) อันดับความสนใจ "ปีปัจจุบัน" ภายในชุด Top N - เจ้าของงานขอให้รายงานแสดงอันดับของปีนี้แทน
    อันดับการเติบโต (Rank Score) และเรียงหัวข้อ 3-4 ตามอันดับนี้ (แบบ A)

    คำนวณแบบเดียวกับ bump chart ทุกขั้น (main/Plot_bump_chart.py และ trend.ipynb) ให้เลขในรายงานตรงกับกราฟ:
    step5c เฉพาะโมเดล best_model, ตัดแถว Holdout (ซ้อนเดือนเดียวกับ Fit), เฉลี่ย z-score รายปี, จัดอันดับเทียบทุก
    คลัสเตอร์ แล้วจัดอันดับใหม่ภายในชุด Top N (1..N)

    "ปีปัจจุบัน" = ปีของเดือนล่าสุดที่เป็นข้อมูลจริง (Type = Fit) ในผลพยากรณ์ของรอบนั้น ไม่ใช่วันที่ตอนสร้างรายงาน
    (สร้างรายงานของรอบเดิมซ้ำปีหน้าก็ได้เลขเดิม) - ค่าของปีนั้น = ข้อมูลจริงถึงเดือนล่าสุด + ค่าพยากรณ์เดือนที่เหลือ

    คืน (year, {trend_name: rank}) หรือ (None, {}) ถ้าไม่มีไฟล์พยากรณ์/ข้อมูลไม่ครบ (รายงานถอยไปแสดงอันดับ Top N)"""
    import pandas as pd

    fp = OUTPUTS / "serpapi_forecast_run" / "step5c_df_cluster_forecast.xlsx"
    if not selected or not fp.exists():
        return None, {}
    df = pd.read_excel(fp)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df[df["Model"] == df["best_model"]]
    fit = df[df["Type"] == "Fit"]
    if fit.empty:
        return None, {}
    year = int(fit["Date"].max().year)
    df = df[df["Type"] != "Holdout"].copy()
    df["period"] = df["Date"].dt.to_period("Y").dt.to_timestamp()
    pivot = (df.groupby(["cluster_name", "period"], as_index=False)["z_score"].mean()
             .pivot(index="period", columns="cluster_name", values="z_score"))
    ranks = (pivot.rank(axis=1, ascending=False, method="first", na_option="bottom")
             .fillna(len(pivot.columns) + 1).astype(int))
    names = [s["trend"] for s in selected]
    missing = [n for n in names if n not in ranks.columns]
    if missing or year not in set(ranks.index.year):
        print(f"  ⚠️ คำนวณอันดับความสนใจปี {year} ไม่ได้ (ไม่พบในผลพยากรณ์: {missing}) - ใช้อันดับ Top N แทน")
        return None, {}
    # ลำดับคอลัมน์เดียวกับกราฟ (เรียงตามอันดับช่วงล่าสุด) - มีผลเฉพาะกรณีอันดับเสมอกัน ให้ตัดสินเหมือนกราฟ
    ordered = [n for n in ranks.iloc[-1].sort_values().index if n in names]
    row = ranks.loc[ranks.index.year == year, ordered].rank(axis=1, method="first").astype(int).iloc[0]
    return year, {n: int(row[n]) for n in ordered}


def build_strategix_context(streams, selected=None, year_ranks=None, year=None):
    """แทนที่ Strategic Pillar mapping เดิม (คนละ abstraction กับ v2 - ไม่มี "Pillar" ในสถาปัตยกรรมนี้)
    - สรุปคลัสเตอร์จริงพร้อมส่วนผสม/ประโยชน์/กลุ่มเป้าหมาย/Longevity

    🆕 (2026-09-16) selected: ชุด Top N จาก load_selected_trends() - ใช้เฉพาะเทรนด์ในชุดนั้น / None = ทุกเทรนด์
    ตามลำดับสายเหมือนเดิม
    🆕 (2026-09-16, แบบ A ที่เจ้าของงานเลือก) year_ranks/year จาก load_current_year_interest_ranks(): แสดง
    "อันดับความสนใจปี X: #k" (ตัดคำว่า "ใน Top N" ออกตามที่เจ้าของงานขอ) เรียงบล็อกตามอันดับนี้ และใส่ประโยคใต้หัวข้อว่าคัดจากอัตราการเติบโต - ถ้าไม่มี
    (รอบเก่า/ไม่มีไฟล์พยากรณ์) แสดงอันดับ Top N จาก Rank Score แทน
    🆕 (2026-09-16) ตัดบรรทัด "Market signal" ออก (เจ้าของงานขอ) - เป็นการเทียบสัมพัทธ์ที่ยังไม่มีเกณฑ์ยืนยัน และเลข
    อันดับในบรรทัดนั้นชวนสับสนกับอันดับเทรนด์ ข้อมูลสินค้ายังอยู่ครบในหัวข้อ 5"""
    longevity_override = load_cross_source_longevity()
    pairs = [(stream, t) for stream, data in streams.items() for t in data.get("trends", [])]
    lines = ["# Top Trend Clusters (Paper + Social + News)\n"]
    rank_line = {}
    if selected is not None:
        by_key = {(stream, t.get("Trend Name")): (stream, t) for stream, t in pairs}
        pairs = [by_key[(s["stream"], s["trend"])] for s in selected if (s["stream"], s["trend"]) in by_key]
        if year_ranks:
            pairs.sort(key=lambda pair: year_ranks.get(pair[1].get("Trend Name"), len(pairs) + 1))
            lines.append(f"> คัด {len(pairs)} เทรนด์จากอัตราการเติบโต (Rank Score) เรียงตามความสนใจปี {year}\n")
            rank_line = {(stream, t.get("Trend Name")):
                         f"- อันดับความสนใจปี {year}: #{year_ranks[t.get('Trend Name')]}"
                         for stream, t in pairs if t.get("Trend Name") in year_ranks}
        else:
            rank_line = {(s["stream"], s["trend"]):
                         f"- Trend Rank (Top {len(selected)}): #{s.get('top_rank', s['overall_rank'])}"
                         for s in selected}
    for stream, t in pairs:
        name = t.get("Trend Name", "")
        # 🆕 (2026-09-12, audit M1) ใช้ Longevity ที่แก้ D2 แล้วถ้ามี ไม่งั้น fallback ไปค่าดิบเดิม
        lv = longevity_override.get((stream, name), t)
        lines.append(f"## {name}  [{stream}]")
        if (stream, name) in rank_line:
            lines.append(rank_line[(stream, name)])
        lines.append(f"- Key Ingredients: {t.get('Key Ingredients', '')}")
        lines.append(f"- Key Benefits: {t.get('Key Benefits', '')}")
        lines.append(f"- Target: {t.get('Target', '')}")
        lines.append(f"- Longevity: {lv.get('Longevity Score')} ({lv.get('Longevity Band')})\n")
    return "\n".join(lines)


def load_master_report_json(selected=None):
    """แทนที่ master_report สายเดียวเดิม - ใช้ Z_Delta จริงจาก ⑦

    🆕 (2026-09-16) selected: ชุด Top N จาก load_selected_trends() - ถ้าส่งมา ส่งเข้า STEPIC เฉพาะคลัสเตอร์ใน
    ชุดนั้น (ชื่อคลัสเตอร์ใน master_report = ชื่อเทรนด์ เพราะ ⑦ ใช้ชื่อเทรนด์เป็น key)"""
    fp = OUTPUTS / "phase2_paper_social_z_delta_result.json"
    if not fp.exists():
        return "[]"
    with open(fp, encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("master_report") or []
    if selected is not None:
        names = {s["trend"] for s in selected}
        rows = [row for row in rows if row[1] in names]
    return json.dumps(rows, ensure_ascii=False)


def load_llm_forecast_analysis(selected=None, sort_rank=None):
    """🆕 (2026-09-16) ผลตีความพยากรณ์ Step 6-7 จาก ⑦ (market_overview + cluster_analysis) - คืน None ถ้าไฟล์
    เป็นรุ่นเก่าที่ยังไม่ได้เซฟค่านี้ หรือ Step 6-7 ล้มเหลวในรอบนั้น (รายงานยังออกได้ แค่หัวข้อพยากรณ์ว่าง)

    selected: ชุด Top N - ถ้าส่งมา cluster_analysis เหลือเฉพาะชุดนั้น เรียงตาม sort_rank (ไม่ส่ง = อันดับ Top N) (market_overview คงเดิม
    เพราะ ⑦ เขียนไว้ก่อน ⑥ จะคัด จึงเป็นภาพรวมของทุกคลัสเตอร์ที่พยากรณ์)"""
    fp = OUTPUTS / "phase2_paper_social_z_delta_result.json"
    if not fp.exists():
        return None
    with open(fp, encoding="utf-8") as f:
        analysis = json.load(f).get("llm_forecast_analysis")
    if analysis and selected is not None:
        # 🆕 (2026-09-16) sort_rank = {ชื่อเทรนด์: อันดับ} ที่หัวข้อ 3 ใช้ (อันดับความสนใจปีปัจจุบัน) ให้หัวข้อ 4 เรียงตรงกัน
        rank_by_name = sort_rank or {s["trend"]: s.get("top_rank", s["overall_rank"]) for s in selected}
        kept = [c for c in analysis.get("cluster_analysis") or [] if c.get("cluster_name") in rank_by_name]
        analysis["cluster_analysis"] = sorted(kept, key=lambda c: rank_by_name[c["cluster_name"]])
    return analysis


def load_supply_layer_results():
    """ผล ⑫ (Watsons 10,622 SKU จริง) - ใช้แทน product_context/product_results ที่เดิมมาจาก Exfac
    pillar match (⑬ ข้ามไปก่อนตามที่สั่ง) คืน (product_context_str, product_results_list, coverage_by_name)"""
    fp = OUTPUTS / "phase3_scale_validation_nvidia_result.json"
    if not fp.exists():
        return "No supply-layer data available.", [], {}

    with open(fp, encoding="utf-8") as f:
        data = json.load(f)
    results = data.get("results") or {}

    # 🆕 (2026-09-12, audit M6) เดิม "percentile" เทียบ max similarity ของเทรนด์กันเองใน n เทรนด์ (ตอนนี้
    # คือ 14) แล้วตัดเป็น SATURATED/GAP/MODERATE - บั๊ก: percentile แบบนี้เป็น RELATIVE RANK ล้วนๆ บังคับ
    # ให้ ~1/3 ได้ SATURATED และ ~1/3 ได้ GAP เสมอไม่ว่าค่าจริงจะเป็นเท่าไหร่ (ค่า max similarity จริงที่
    # เจอมีแค่ 0.20-0.49 - ไม่มีเทรนด์ไหน "อิ่มตัว" จริงในความหมายที่คำนั้นควรสื่อเลย) - ยังไม่มีเกณฑ์
    # absolute ที่ calibrate ด้วย label จากคนจริง (รอ M6 ส่วน calibration) จึงตัดคำ SATURATED/GAP/MODERATE
    # ที่ให้ความมั่นใจเกินจริงออกไปก่อน เหลือแค่ rank สัมพัทธ์ + ค่า similarity จริงให้คนอ่านตัดสินเอง
    # 🆕 (2026-09-12, audit M4) key ของ `results` เป็น "stream::trend" แล้ว (กันชื่อเทรนด์ชนกันข้ามสาย
    # เงียบๆ) - ใช้ key นี้เป็น key ภายในของ coverage_by_name เหมือนเดิม แต่แสดงผล/ส่งต่อด้วยชื่อเทรนด์
    # ล้วนจาก r["trend_name"] แทน key ผสม
    ranked = sorted(results.items(), key=lambda kv: kv[1]["similarity_stats"]["max"], reverse=True)
    n = len(ranked)
    coverage_by_name = {
        key: {"rank": i + 1, "n_trends": n, "max_similarity": r["similarity_stats"]["max"]}
        for i, (key, r) in enumerate(ranked)
    }

    context_lines, product_rows = [], []
    for key, r in results.items():
        name = r.get("trend_name", key)
        cov = coverage_by_name[key]
        top1 = r["top_matches"][0]
        # 🆕 (2026-09-14, แก้ตามที่เจ้าของงานสั่ง) top1 อาจมี match_reason - LLM ให้แค่คำอธิบาย ไม่ตัดสิน
        # verdict แล้ว (similarity ยังเป็นตัวจัดอันดับ/ตัดสินหลักอยู่เหมือนเดิม - ดู
        # validate_at_scale_nvidia.py's generate_match_reason()) - ใส่ต่อท้ายถ้ามี ไม่มีก็ไม่พังเพราะ
        # ไฟล์ผลลัพธ์ที่รันก่อนแก้ฟีเจอร์นี้ (2026-09-11) จะไม่มี key นี้เลย (.get คืน None พอดี)
        reason_suffix = f" — {top1['match_reason']}" if top1.get("match_reason") else ""
        context_lines.append(
            f"- Trend '{name}' [{r['stream']}]: max similarity {cov['max_similarity']:.3f} "
            f"(rank {cov['rank']}/{cov['n_trends']} เทียบกับเทรนด์อื่นในรอบนี้ - ยังไม่มีเกณฑ์ absolute "
            f"ที่ calibrate แล้วว่าค่านี้ถือว่า 'มีของเข้าเทรนด์จริง' หรือไม่), "
            f"top real match: {top1['brand']} - {top1['product_name']} "
            f"(similarity={top1['similarity']}){reason_suffix}"
        )
        for m in r["top_matches"][:5]:
            # 🆕 (2026-09-12, audit M6) เดิม hardcode "" เสมอ ทั้งที่มีข้อมูลจริงจาก ⑫ แล้ว
            # (validate_at_scale_nvidia.py เก็บ sale_price_thb/sold_count ไว้ให้แล้ว)
            price = m.get("sale_price_thb")
            sold = m.get("sold_count")
            product_rows.append({
                "Pillar": name,  # ใช้ชื่อเทรนด์แทน Pillar (v2 ไม่มีระบบ Pillar)
                "Key_Trends": name,
                "Brand": m["brand"], "Product Name": m["product_name"],
                "Sale Price (฿)": price if price is not None else "",
                "Sold": sold if sold is not None else "",
                # 🆕 (2026-09-14) คำอธิบายว่าสินค้านี้เกี่ยวกับเทรนด์ยังไง (ไม่มี verdict ตัดสิน - similarity
                # ยังเป็นตัวจัดอันดับหลักเหมือนเดิม) - "-" ถ้าไม่มี (เกิน top 5 ที่ถาม LLM จริง หรือรันด้วย
                # ผลลัพธ์เก่าก่อนมีฟีเจอร์นี้)
                "Why It Fits": m.get("match_reason") or "-",
            })
    return "\n".join(context_lines), product_rows, coverage_by_name


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 4 ⑭-⑮ — STEPIC Analysis -> Master Report (⑬ ข้ามไปก่อน)")
    print("=" * 70)

    USER_QUERY, _ = prompt_run_config(default_topic=DEFAULT_USER_QUERY, ask_years=False)

    streams = load_streams()
    if not streams:
        print("❌ ไม่มีผลลัพธ์สายไหนเลย")
        sys.exit(1)
    print(f"โหลด {len(streams)} สาย: {list(streams.keys())}")

    product_context_str, product_results, coverage_by_name = load_supply_layer_results()
    print(f"⑫ supply-layer: {len(product_results)} product rows (จาก {len(coverage_by_name)} เทรนด์)")

    # 🆕 (2026-09-16) ชุด Top N เดียวกับ ⑪-⑫ (คัดด้วย Rank Score ของ ⑥) - หัวข้อ 3-4 ของรายงานและข้อมูลที่ส่ง
    # เข้า STEPIC ใช้เฉพาะชุดนี้ ส่วนหัวข้อ 5 มาจาก ⑫ ซึ่งเป็นชุดนี้อยู่แล้ว
    selected_trends = load_selected_trends()
    if selected_trends is not None:
        print(f"ใช้ Top {len(selected_trends)} เทรนด์ตามที่ ⑪ คัดไว้: "
              + ", ".join(f"#{s['overall_rank']} {s['trend']}" for s in selected_trends))
    else:
        print("⚠️ ผล ⑪ ไม่มี selected_trends (รอบเก่า) - รายงานใช้ทุกเทรนด์เหมือนเดิม")

    # 🆕 (2026-09-16, แบบ A) อันดับความสนใจปีปัจจุบัน (ตรงกับ bump chart) - หัวข้อ 3, 4, 5 เรียงตามอันดับนี้
    current_year, year_ranks = load_current_year_interest_ranks(selected_trends)
    if year_ranks:
        print(f"เรียงรายงานตามอันดับความสนใจปี {current_year}: "
              + ", ".join(f"#{r} {n}" for n, r in sorted(year_ranks.items(), key=lambda kv: kv[1])))
        product_results = sorted(product_results, key=lambda p: year_ranks.get(p["Key_Trends"], len(year_ranks) + 1))

    final_trend_report = build_merged_trend_report(streams)
    strategix_context = build_strategix_context(streams, selected_trends, year_ranks, current_year)
    master_report_str = load_master_report_json(selected_trends)
    llm_forecast_analysis = load_llm_forecast_analysis(selected_trends, year_ranks or None)
    if llm_forecast_analysis:
        print(f"⑦ Step 6-7 forecast analysis: {len(llm_forecast_analysis.get('cluster_analysis') or [])} คลัสเตอร์")
    else:
        print("⚠️ ไม่มีผล Step 6-7 จาก ⑦ (ไฟล์รุ่นเก่า หรือขั้นนั้นล้มเหลว) - หัวข้อพยากรณ์ในรายงานจะว่าง")

    print(f"\n🧠 [Step 9a] STEPIC 6 มิติ (Society/Technology/Environment/Policy/Industry/Creativity)...")
    with use_bedrock_v2():
        stepic_raw_analysis = tf2.analyze_trend(final_trend_report, master_report_str, USER_QUERY,
                                                product_context_str)

    print(f"\n🧠 [Step 9b] สังเคราะห์รวม (integrate_stepic)...")
    with use_bedrock_v2():
        final_stepic_insight = tf2.integrate_stepic(stepic_raw_analysis, USER_QUERY)

    print(f"\n📄 [Step 10] ประกอบ Master Report...")
    master_markdown = tf2.generate_master_markdown_report(
        user_query=USER_QUERY,
        final_trend_report=final_trend_report,
        strategix_context=strategix_context,
        llm_forecast_analysis=llm_forecast_analysis,
        product_results=product_results,
        final_stepic_insight=final_stepic_insight,
        stepic_raw_analysis=stepic_raw_analysis,
        master_report_dict=None,
    )

    out_dir = OUTPUTS
    with open(out_dir / "phase4_stepic_raw_analysis.json", "w", encoding="utf-8") as f:
        json.dump(stepic_raw_analysis, f, ensure_ascii=False, indent=2)
    with open(out_dir / "phase4_stepic_final_insight.json", "w", encoding="utf-8") as f:
        json.dump(final_stepic_insight, f, ensure_ascii=False, indent=2)
    report_path = out_dir / "phase4_master_trend_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(master_markdown)

    print("\n" + "=" * 70)
    print("STEPIC สรุป (final_stepic_insight):")
    print("=" * 70)
    for k, v in (final_stepic_insight or {}).items():
        print(f"  {k}: {str(v)[:150]}")

    print(f"\n✅ Saved -> {report_path}")
    print(f"✅ Saved -> {out_dir / 'phase4_stepic_raw_analysis.json'}")
    print(f"✅ Saved -> {out_dir / 'phase4_stepic_final_insight.json'}")
