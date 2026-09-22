# -*- coding: utf-8 -*-
"""
Phase 2 — รัน Step 6-7 (การตีความ LLM ของ Z_Delta) ผ่าน NVIDIA NIM's deepseek-v4-pro-0813 แทน
OpenRouter (ที่ล้มเหลวด้วย 402 credit หมดตอนรันจริงครั้งก่อน)

**ไม่ยิง SerpAPI ใหม่เลย** - โหลด monthly_df จริงที่ fetch_trends_worldwide_serpapi.py ดึงมาแล้วจาก
step5a_monthly_trends.xlsx (94 คีย์เวิร์ดจริง, ใช้ quota ไปแล้ว 94/98 - เหลือแค่ 4 ไม่พอ fetch ใหม่) มา
เป็น monthly_df_override แทน แล้วรัน forecast_trend() ซ้ำ (feature engineering + modeling ทำใหม่ได้ฟรี
เพราะเป็น local compute ล้วนๆ) แต่คราวนี้ patch tf2.client/tf2.MODEL_NAME ให้ชี้ไป NVIDIA NIM ก่อน

**สมอค test:** deepseek-v4-pro-0813 ทดสอบ JSON compliance แล้ว (2026-09-09) - ตอบ JSON สะอาด
finish_reason=stop ไม่มี <thought> รั่วไหลใน content เหมือน Gemma/Gemini - แต่ **ช้ามาก (~66s สำหรับ
prompt เล็กๆ)** อาจเป็นเพราะ reasoning ฝั่งเซิร์ฟเวอร์ที่ไม่โชว์ใน content (คล้าย OpenAI o1-style) หรือ
คิวของ NVIDIA NIM community tier - ยอมรับได้เพราะเรียกแค่ครั้งเดียว ไม่ใช่ยิงซ้ำหลายรอบ
"""
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import OUTPUTS, PROJECT_ROOT

# 🆕 (2026-09-22) ส่วนที่ใช้จริงของ trend_final_v2.py คัดลอกตรงตัวไว้ใน main/ (common/trend_final_v2_subset.py)
from common import trend_final_v2_subset as tf2  # noqa: E402

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)
import os  # noqa: E402
from openai import OpenAI  # noqa: E402

RUN_DIR = OUTPUTS / "serpapi_forecast_run"
OUTPUT_DIR = str(OUTPUTS / "serpapi_forecast_run_deepseek")
USER_QUERY = "Global Body Wash Beauty Trends 2030"  # ห้ามมีคำ thailand/thai/ไทย - ดูสคริปต์เดิม

# 🆕 patch tf2.client/tf2.MODEL_NAME/tf2.MODEL_NAME_META ให้ชี้ไป NVIDIA NIM's deepseek-v4-pro-0813
# แทน OpenRouter - เฉพาะสำหรับสคริปต์นี้ (ไม่ได้แก้ trend_final_v2.py เอง)
_original_client = tf2.client
_original_model_name = tf2.MODEL_NAME
_original_model_name_meta = tf2.MODEL_NAME_META

tf2.client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.getenv("NVIDIA_API"))
tf2.MODEL_NAME = "deepseek-ai/deepseek-v4-pro-0813"
tf2.MODEL_NAME_META = "deepseek-ai/deepseek-v4-pro-0813"

try:
    trend_keyword_mapping = None
    import json
    mapping = {}
    for fname in ["phase1_paper_stream_result.json", "phase2_social_stream_result.json", "phase2_news_stream_result.json"]:
        with open(OUTPUTS / fname, encoding="utf-8") as f:
            data = json.load(f)
        for row in data["keywords"]:
            trend_name = row["Trend Name"]
            kws = [k.strip().lower() for k in str(row.get("Search_Keywords", "")).split(",") if k.strip()]
            if kws:
                mapping[trend_name] = kws
    trend_keyword_mapping = mapping

    monthly_df = pd.read_excel(RUN_DIR / "step5a_monthly_trends.xlsx")
    print(f"โหลด monthly_df จริงที่ fetch มาแล้ว: {len(monthly_df)} แถว (ไม่ยิง SerpAPI ใหม่เลย)")

    print("กำลังรัน forecast_trend() ซ้ำ (modeling local ฟรี) + Step 6-7 ผ่าน deepseek-v4-pro-0813...")
    print("⚠️ อาจใช้เวลานาน (ทดสอบพบ ~66s สำหรับ prompt เล็ก - prompt จริงใหญ่กว่ามาก อาจหลายนาที)")

    cluster_names, df_results, master_report, llm_analysis = tf2.forecast_trend(
        OUTPUT_DIR, trend_keyword_mapping, USER_QUERY, monthly_df_override=monthly_df,
    )

    print("\n" + "=" * 70)
    if llm_analysis and isinstance(llm_analysis, dict) and "error" not in llm_analysis:
        print("✅ Step 6-7 สำเร็จ! ผลการตีความจาก deepseek-v4-pro-0813:")
        import json as _json
        print(_json.dumps(llm_analysis, ensure_ascii=False, indent=2)[:3000])

        result_path = OUTPUTS / "phase2_paper_social_llm_analysis_deepseek.json"
        with open(result_path, "w", encoding="utf-8") as f:
            _json.dump(llm_analysis, f, ensure_ascii=False, indent=2)
        print(f"\nบันทึกผลเต็มลง {result_path}")
    else:
        print(f"❌ Step 6-7 ยังล้มเหลว: {llm_analysis}")
finally:
    # คืนค่าเดิมเสมอ แม้ error - กัน module state เพี้ยนถ้าสคริปต์อื่น import tf2 ต่อในโปรเซสเดียวกัน
    tf2.client = _original_client
    tf2.MODEL_NAME = _original_model_name
    tf2.MODEL_NAME_META = _original_model_name_meta
