# -*- coding: utf-8 -*-
"""ส่วนที่ไปป์ไลน์ v2 ใช้จริงจาก `trend_final_v2.py` - คัดลอกตรงตัว ไม่ได้เขียนใหม่

ทำไมมีไฟล์นี้ (2026-09-22): ให้ทุกอย่างที่ `main/` ต้องใช้อยู่ใน `main/` เอง โดยไม่ย้ายหรือแก้ `trend_final_v2.py`
ต้นฉบับ (ต้นฉบับไม่ถูกแก้ - ย้ายไปเก็บที่ `_archive/root_legacy_20260922/` แล้ว) - ใช้ผ่านชื่อ `tf2` (`from common import trend_final_v2_subset as tf2`)

วิธีคัด: เริ่มจากชื่อที่โค้ดใน `main/` เรียกผ่าน `tf2.xxx` จริง (ไล่ด้วย AST ไม่นับ docstring) แล้วไล่ต่อว่า
statement นั้นใช้ชื่ออะไรในไฟล์เดียวกันอีก จนครบ - ทุกบล็อกมีป้าย `# [trend_final_v2.py Lก-Lข]` บอกบรรทัดต้นฉบับ
และเรียงตามลำดับเดิมในไฟล์ต้นฉบับ

ต่างจากต้นฉบับ (ตั้งใจ):
- บล็อกที่มีป้าย "⚠️ แก้จากต้นฉบับ" - `_TOOLS_DIR` ชี้ `main/` แทนโฟลเดอร์ของไฟล์นี้
- ไม่คัดมา: `if not TAVILY_API_KEY: sys.exit(1)` (Tavily ไม่มีฟังก์ชันไหนในไฟล์นี้ใช้) และ `if __name__ == "__main__"`

ตรวจสอบ: `tool/tests/test_trend_final_subset.py` - (1) ไม่มีชื่อ global ที่หานิยามไม่เจอ (2) ถ้าพบต้นฉบับ (root หรือ
_archive/root_legacy_20260922/) จะเทียบทุกบล็อกว่ายังตรงตัวอักษร (บล็อกที่มีป้าย ⚠️ ข้ามได้) และเทียบผลของฟังก์ชันกับต้นฉบับ
ถ้าจะแก้บล็อกไหนโดยตั้งใจ ให้ใส่ "⚠️ แก้จากต้นฉบับ: <เหตุผล>" ในป้ายของบล็อกนั้น
"""
# [trend_final_v2.py L1-L1]
import os


# [trend_final_v2.py L3-L3]
import json


# [trend_final_v2.py L4-L4]
import time


# [trend_final_v2.py L5-L5]
from datetime import datetime


# [trend_final_v2.py L6-L6]
from pathlib import Path


# [trend_final_v2.py L7-L7]
from openai import OpenAI


# [trend_final_v2.py L8-L8]
import pandas as pd


# [trend_final_v2.py L10-L10]
import numpy as np


# [trend_final_v2.py L15-L15]
import re


# [trend_final_v2.py L19-L19]
from datetime import datetime, timedelta


# [trend_final_v2.py L21-L21]
import xgboost as xgb


# [trend_final_v2.py L22-L22]
from sklearn.linear_model import LinearRegression


# [trend_final_v2.py L23-L23]
from sklearn.ensemble import RandomForestRegressor


# [trend_final_v2.py L24-L24]
from statsmodels.tsa.holtwinters import ExponentialSmoothing


# [trend_final_v2.py L25-L25]
from sklearn.metrics import mean_squared_error


# [trend_final_v2.py L32-L32]
from serpapi import GoogleSearch


# [trend_final_v2.py L35-L35]
from dotenv import load_dotenv


# [trend_final_v2.py L41-L41]
import pandas as pd


# [trend_final_v2.py L42-L42]
from typing import List, Union


# [trend_final_v2.py L43-L43]
from pydantic import BaseModel, Field, ValidationError


# [trend_final_v2.py L46-L46] ⚠️ แก้จากต้นฉบับ: ต้นฉบับชี้โฟลเดอร์ของไฟล์ตัวเอง (root) - ย้ายฐานมาที่ main/ ให้ .env และ config/ อยู่ใน main/
_TOOLS_DIR = Path(__file__).resolve().parents[2]  # = main/ -> .env อยู่ที่ main/.env, config อยู่ที่ main/config/


# [trend_final_v2.py L47-L47]
_API_DIR = _TOOLS_DIR


# [trend_final_v2.py L50-L50]
env_path = _API_DIR / ".env"


# [trend_final_v2.py L51-L51]
load_dotenv(dotenv_path=env_path)


# [trend_final_v2.py L64-L64]
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


# [trend_final_v2.py L65-L65]
SERPAPI_KEY = os.getenv("SERPAPI_KEY")


# [trend_final_v2.py L66-L66]
MODEL_NAME = os.getenv("MODEL_NAME")


# [trend_final_v2.py L69-L69]
MODEL_NAME_META = os.getenv("MODEL_NAME_META")


# [trend_final_v2.py L71-L71]
MODEL_CONTEXT_LIMIT = 230000 


# [trend_final_v2.py L72-L72]
SAFE_MAX_TOKENS = 16000 


# [trend_final_v2.py L76-L79]
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)


# [trend_final_v2.py L81-L81]
total_input_tokens = 0


# [trend_final_v2.py L82-L82]
total_output_tokens = 0


# [trend_final_v2.py L85-L85]
os.makedirs("memory", exist_ok=True)


# [trend_final_v2.py L141-L151]
def compute_max_tokens(prompt: str):
    estimated_prompt_tokens = int(len(prompt) * 1.3)

    if estimated_prompt_tokens > MODEL_CONTEXT_LIMIT:
        raise ValueError(
            f"Prompt too large ({estimated_prompt_tokens}). Truncate input before calling LLM."
        )

    remaining = MODEL_CONTEXT_LIMIT - estimated_prompt_tokens
    print(f"[DEBUG] compute_max_tokens_impl: estimated_prompt_tokens={estimated_prompt_tokens}, remaining={remaining}")
    return max(6000, min(remaining, SAFE_MAX_TOKENS))


# [trend_final_v2.py L153-L172]
def clean_json_string(raw_text):
    if not raw_text:
        return ""
    
    clean_text = raw_text.strip()
    # ลบแท็ก ```json และ ``` ออก
    if clean_text.startswith("```json"):
        clean_text = clean_text[7:]
    elif clean_text.startswith("```"):
        clean_text = clean_text[3:]
        
    if clean_text.endswith("```"):
        clean_text = clean_text[:-3]
        
    # ใช้ Regex ช่วยหาเฉพาะส่วนที่เป็น [...] หรือ {...} ในกรณีที่ AI พูดอารัมภบท
    match = re.search(r'(\{.*\}|\[.*\])', clean_text.strip(), re.DOTALL)
    if match:
        return match.group(0)
        
    return clean_text.strip()


# [trend_final_v2.py L174-L301]
def safe_json_parse(content: str):
    """
    Robust JSON parser for LLM responses.
    Handles Llama 3 over-escaping, code fences, Python literals, and trailing commas.
    Dynamically supports both JSON Objects {} and Arrays [].
    """
    if not content or not isinstance(content, str):
        print("⚠️ Empty or invalid response from AI.")
        return None

    content = content.strip()

    # 0️⃣ FIX (Phase 0, 2026-08-28): ลอง parse ตรงๆ ก่อนเสมอ
    # เดิมโค้ดกระโดดไปทำ .replace() ทันทีโดยไม่ลองก่อน ซึ่งตั้งใจแก้ปัญหาโมเดลเล็ก
    # (Llama 3) ที่ over-escape แต่มันไปทำลาย escaped quote ที่ถูกต้องอยู่แล้วด้วย
    # เช่นเวลา LLM ตอบคำที่มีเครื่องหมายคำพูดซ้อนในค่า string ซึ่งถูกตามหลัก JSON ทุกประการ กลับพัง
    # ทันที - เจอจริงตอนรัน pilot อีคอมเมิร์ซต่างประเทศ (2026-08-27) ทำให้สรุปผลหายทั้งรอบ
    # ทางแก้: JSON ที่ถูกอยู่แล้วต้องผ่านตั้งแต่ด่านแรก ส่วนตัวซ่อมด้านล่างเก็บไว้เป็น fallback
    # สำหรับกรณี over-escape จริงเหมือนเดิม ไม่ได้ลดความสามารถเดิมลงเลย
    try:
        return json.loads(content)
    except Exception:
        pass

    # 1️⃣ FIX: Remove over-escaped quotes generated by smaller models like Llama 3
    content = content.replace('\\"', '"')

    # 2️⃣ Remove markdown code fences
    if content.startswith("```"):
        content = re.sub(r"```json|```", "", content).strip()

    # 3️⃣ Normalize common LLM JSON mistakes
    content = content.replace("None", "null")
    content = content.replace("True", "true")
    content = content.replace("False", "false")
    # Remove trailing commas right before closing braces/brackets
    content = re.sub(r",\s*([}\]])", r"\1", content)

    # ➕ Special case: some models return Python set-like syntax {"a","b"}
    # which is invalid JSON.  Convert to JSON array automatically.
    if content.startswith("{") and content.endswith("}") and ":" not in content:
        inner = content[1:-1].strip()
        # split on commas while respecting quoted strings
        items = re.split(r"\s*,\s*", inner)
        cleaned_items = []
        for itm in items:
            itm = itm.strip()
            if not itm:
                continue
            # ensure double quotes
            if itm.startswith("'") and itm.endswith("'"):
                itm = '"' + itm[1:-1] + '"'
            elif itm.startswith('{') or itm.endswith('}'):
                # just in case nested braces remain
                itm = itm.strip('{}')
            cleaned_items.append(itm)
        try:
            content = "[" + ",".join(cleaned_items) + "]"
        except Exception:
            pass

    # ➕➕ Additional pass: convert set-like elements embedded within arrays
    # e.g. [{"a"}, {"b"}] or [{'x'}] into ["a","b"].
    # This is a common response format from some LLMs that produced
    # an array of single-item sets.  We replace any `{value}` where value
    # contains no colon to a quoted string, which preserves legitimate
    # objects/dicts with colon separators.  This runs globally on the
    # content string prior to attempting JSON loads below.
    def _replace_inner_set(match):
        inner_val = match.group(1).strip()
        # already quoted?
        if (inner_val.startswith('"') and inner_val.endswith('"')) or (
            inner_val.startswith("'") and inner_val.endswith("'")
        ):
            return inner_val
        return '"' + inner_val + '"'

    content = re.sub(r"\{\s*([^:{}]+?)\s*\}", _replace_inner_set, content)

    # 4️⃣ Try direct load
    try:
        return json.loads(clean_json_string(content))
    except json.JSONDecodeError:
        pass

    # 5️⃣ Extract JSON object OR array dynamically (handles conversational wrapper text)
    match = re.search(r"(\{.*?\}|\[.*?\])", content, re.DOTALL)
    if match:
        extracted = match.group(1)
        try:
            return json.loads(clean_json_string(extracted))
        except json.JSONDecodeError:
            content = extracted # Proceed to balancing with the extracted text

    # 6️⃣ Brace & Bracket balancing repair
    open_braces = content.count("{")
    close_braces = content.count("}")
    if open_braces > close_braces:
        content += "}" * (open_braces - close_braces)

    open_brackets = content.count("[")
    close_brackets = content.count("]")
    if open_brackets > close_brackets:
        content += "]" * (open_brackets - close_brackets)

    try:
        return json.loads(clean_json_string(content))
    except json.JSONDecodeError:
        pass

    # 7️⃣ Final fallback: extract largest JSON-like Object or Array
    possible_json = re.findall(r"\{.*\}", content, re.DOTALL)
    for candidate in possible_json:
        try:
            return json.loads(clean_json_string(candidate))
        except:
            continue
            
    possible_array = re.findall(r"\[.*\]", content, re.DOTALL)
    for candidate in possible_array:
        try:
            return json.loads(clean_json_string(candidate))
        except:
            continue

    print("❌ JSON unrecoverable. Preview:")
    print(content[:500])
    return None


# [trend_final_v2.py L1418-L1555]
def analyze_trend(trend_report, master_report, user_query, product_context):
    global total_input_tokens, total_output_tokens
    trend_report = re.split(r'##\s*5\.\s*แหล่งข้อมูลอ้างอิงทั้งหมด', trend_report)[0].strip()

    MASTER_SYSTEM_PROMPT = f"""
    Act as a 'Trend Analysis' expert.

    Your primary goal is to identify, analyze, and explain current and emerging trends 
    across sectors using the STEPIC framework 
    (Society, Technology, Environment, Politics, Industry, Creativity).

    Focus trend: {user_query}

    Rules:
    - Be analytical, professional, and objective.
    - Use data-driven reasoning.
    - concept: Core societal shift behind this trend
    - information: Key insights, statistics, behavioral patterns
    - persona: 2-3 emerging consumer personas (name + short description)
    - proof_point: Data, reports, statistics, market signals
    - example_products_or_brands: Specific brands or products representing this societal shift
    - Provide proof points (Google Trends, UN, research reports, statistics, and more).
    - Avoid speculation unless clearly labeled as projection.
    - Keep explanations concise but insight-rich.
    - Always structure logically.
    - Output JSON only.
    """

    step_prompts = {
        "society": """
        Provide:
        - concept
        - key_drivers
        - behavioral_shift
        - current_status
        - projected_impact
        - proof_point
        - example_products_or_brands
        """,
        "technology": """
        Provide:
        - core_technology
        - innovation_driver
        - adoption_stage
        - commercialization_signal
        - projected_growth
        - proof_point
        - example_products_or_brands
        """,
        "environment": """
        Provide:
        - environmental_factor
        - ESG_driver
        - regulatory_pressure
        - sustainability_opportunity
        - risk_factor
        - proof_point
        - example_products_or_brands
        """,
        "policy": """
        Provide:
        - regulatory_trend
        - government_role
        - legal_barrier_or_support
        - geopolitical_factor
        - business_impact
        - proof_point
        """,
        "industry": """
        Provide:
        - market_structure
        - competitive_landscape
        - growth_rate_estimate
        - key_players
        - strategic_positioning
        - investment_signal
        - proof_point
        """,
        "creativity": """
        Provide:
        - brand_expression
        - product_innovation
        - consumer_emotional_trigger
        - differentiation_strategy
        - example_products_or_brands
        - proof_point
        """
    }

    final_result = {}

    for step_name, instruction in step_prompts.items():
        full_prompt = f"""
        Analyze this trend in the {step_name.upper()} dimension.

        {instruction}

        Trend Report:
        {trend_report}
        
        Trend forecasting from time series of related word in trend report and Goole Trend:
        {master_report}

        Real Market Product Data matching this trend (Use these to inform 'example_products_or_brands'):
        {product_context}

        Return VALID JSON only.
        """
        prompt = MASTER_SYSTEM_PROMPT + full_prompt
        max_token_para = compute_max_tokens(prompt)
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": MASTER_SYSTEM_PROMPT},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0.1,
                max_tokens=max_token_para
            )
            if hasattr(response, 'usage') and response.usage:
                total_input_tokens += getattr(response.usage, 'prompt_tokens', 0)
                total_output_tokens += getattr(response.usage, 'completion_tokens', 0)
            
            content = safe_json_parse(response.choices[0].message.content)
            
            if not content:
                print(f"   ⚠️ Warning: AI returned empty content for '{step_name}'. Skipping.")
                final_result[step_name] = {"error": "No response from AI"}
                continue

            final_result[step_name] = content

        except Exception as e:
            print(f"   ❌ Error in {step_name}: {e}")
            final_result[step_name] = {}

    return final_result


# [trend_final_v2.py L1557-L1620]
def integrate_stepic(final_result: dict, user_query: str):
    global total_input_tokens, total_output_tokens
    
    if not final_result:
        print("❌ No STEPIC result provided.")
        return {}

    MASTER_SYSTEM_PROMPT = f"""
    You are a Senior Strategic Foresight Analyst.

    Focus trend: {user_query}

    Your job:
    Synthesize cross-dimensional insights.
    Identify convergence patterns across STEPIC.

    Return VALID JSON only.
    No markdown.
    """

    integration_prompt = f"""
    Based on this STEPIC analysis:

    {json.dumps(final_result, ensure_ascii=False)}

    Provide:

    - mega_trend_name
    - macro_direction
    - core_concept
    - 3_month_projection
    - emerging_personas (2-3 structured personas)
    - cross_dimensional_signals
    - key_risk
    - key_opportunity

    Return VALID JSON only.
    """
    full_prompt = MASTER_SYSTEM_PROMPT + integration_prompt
    max_token_para = compute_max_tokens(full_prompt)
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": MASTER_SYSTEM_PROMPT},
                {"role": "user", "content": integration_prompt}
            ],
            temperature=0.1,
            max_tokens=max_token_para
        )
        if hasattr(response, 'usage') and response.usage:
            total_input_tokens += getattr(response.usage, 'prompt_tokens', 0)
            total_output_tokens += getattr(response.usage, 'completion_tokens', 0)
            
        raw = response.choices[0].message.content
        parsed = safe_json_parse(raw)

        if not isinstance(parsed, dict):
            print("⚠️ Invalid integration JSON")
            return {"error": "Invalid JSON"}
        return parsed
    except Exception as e:
        print(f"❌ Integration error: {e}")
        return {"error": str(e)}


# [trend_final_v2.py L1622-L1647]
def compute_investment_signal(z_delta):
    """คำนวณ investment_signal ด้วยกฎตายตัวจาก Z_Delta แทนให้ LLM ตัดสินใจอิสระ (2026-08-20)

    เดิมให้ LLM ตัดสิน investment_signal เองอิสระในตัว JSON เดียวกับ trend_stage - พิสูจน์แล้วด้วย
    walk-forward validation (n=186/186, batch=10 เท่า production จริง) ว่าแม่นแค่ 40.9% แย่กว่าตัวเลข
    ดิบ (63.4%) และ trend_stage (65.6%) มาก เอนเอียงไปทาง "Monitor" หนัก (48% ของคำตอบ) โดยจุดที่
    ตัวเลขดิบทายถูกแต่ LLM ทำให้ผิดมี 57 จุด เทียบกับกรณีตรงข้ามแค่ 15 จุด (ดู Detail/04
    การตรวจสอบและผลลัพธ์/Evaluation Phase — ค่าที่ควรมี.md)

    threshold 0.2/-0.2 เดียวกับ bucket3()/classify() ที่ใช้วัด accuracy ทั้งโปรเจกต์ (Up/Down/Flat)
    ทำให้ investment_signal ตัวนี้แม่นเท่ากับ accuracy ของตัวเลขดิบที่ verify แล้วโดยตรง (63.4%)
    LLM ยังทำหน้าที่อธิบายเหตุผล (driver_explanation) เหมือนเดิม แค่ไม่ได้ตัดสินค่านี้เองอีกต่อไป

    มีขอบกันค่าดิบผิดปกติ (RAW_VALUE_BOUND) เพราะทดสอบกับข้อมูลจริงพบว่าถ้าไม่กัน คลัสเตอร์ที่มี
    Z_Delta ระเบิดจากบั๊กเก่า (เช่น 1,126,551.54 ก่อนแก้ตัวกันโมเดลระเบิด - ดู Detail/03
    ปัญหาที่พบและแก้ไข/ตัวกันโมเดลระเบิด.md) จะได้ "Invest Now" ทันทีอย่างมั่นใจผิดๆ ทั้งที่ LLM แบบเดิม
    ยังจับความผิดปกตินี้ได้เองและลดเป็น "Monitor" - กฎตายตัวไม่มีสามัญสำนึกแบบนั้น จึงต้องกันไว้เอง
    """
    RAW_VALUE_BOUND = 20.0  # ตรงกับขอบที่ใช้ใน run_exfac_trend_match.py - z-score จริงไม่ควรเกินนี้
    if z_delta is None or abs(z_delta) > RAW_VALUE_BOUND:
        return "Monitor"
    if z_delta > 0.2:
        return "Invest Now"
    if z_delta < -0.2:
        return "Wait"
    return "Monitor"


# [trend_final_v2.py L1653-L1665]
class ClusterAnalysis(BaseModel):
    cluster_id: Union[int, str] = "N/A"
    cluster_name: str = "Unknown Cluster"
    keywords: List[str] = Field(default_factory=list)
    trend_stage: str = "N/A"
    primary_driver: str = "N/A"
    confidence_level: str = "N/A"
    driver_explanation: str = "N/A"
    consumer_intent_signal: str = "N/A"
    estimated_duration: str = "N/A"
    risk_scenario_if_forecast_fails: str = "N/A"
    executive_summary: str = "N/A"
    investment_signal: str = "N/A"


# [trend_final_v2.py L1668-L1673]
class MarketOverview(BaseModel):
    query: str = "N/A"
    current_trend_strength: str = "N/A"
    estimated_trend_duration: str = "N/A"
    overall_direction: str = "N/A"
    summary: str = "N/A"


# [trend_final_v2.py L1676-L1678]
class ForecastAnalysis(BaseModel):
    market_overview: MarketOverview = Field(default_factory=MarketOverview)
    cluster_analysis: List[ClusterAnalysis] = Field(default_factory=list)


# [trend_final_v2.py L1684-L1684]
_pytrends_client = None


# [trend_final_v2.py L1685-L1685]
_pytrends_blocked = False  # ตั้งเป็น True ทันทีที่ Google ตอบ 429 - เลิกยิงซ้ำ กันโดนบล็อกหนักขึ้นและเสียเวลาฟรี


# [trend_final_v2.py L1686-L1686]
_pytrends_last_call_ts = 0.0


# [trend_final_v2.py L1687-L1687]
PYTRENDS_MIN_INTERVAL_SEC = 1.5  # หน่วงระหว่างคำขอแต่ละครั้ง ลดโอกาสโดน rate limit ตั้งแต่ต้น


# [trend_final_v2.py L1690-L1701]
def _get_pytrends_client():
    global _pytrends_client
    if _pytrends_client is None:
        from pytrends.request import TrendReq
        # หมายเหตุ: ตั้งใจ "ไม่" ส่ง retries/backoff_factor ให้ TrendReq ที่นี่ - pytrends 4.9.2
        # ที่ลงอยู่ตอนนี้ยังสร้าง urllib3.Retry(method_whitelist=...) ภายในเวลามีการตั้งค่า
        # retries/backoff_factor (ดู pytrends/request.py:124-128) ซึ่ง urllib3>=2.0 เอา
        # method_whitelist ออกไปแล้ว (เปลี่ยนเป็น allowed_methods) ทำให้พัง
        # TypeError ทุกครั้งที่เรียก - ป้องกัน rate limit ด้วย PYTRENDS_MIN_INTERVAL_SEC +
        # _pytrends_blocked circuit breaker ด้านล่างแทน ไม่ต้องพึ่ง retry ภายในของ pytrends
        _pytrends_client = TrendReq(hl="en-US", tz=420)
    return _pytrends_client


# [trend_final_v2.py L1704-L1743]
def _pytrends_interest_over_time(word, timeframe="today 5-y", geo=""):
    """ดึง Google Trends ผ่าน pytrends แล้วแปลงผลให้อยู่ในรูปแบบเดียวกับ
    interest_over_time ของ SerpAPI (มี timeline_data) เพื่อให้ timeseries_to_df()
    ที่มีอยู่แล้วใช้งานต่อได้เลยโดยไม่ต้องแก้โค้ดจุดอื่น
    geo="" = ทั้งโลก, geo="TH" = เฉพาะไทย (ส่งต่อให้ pytrends ตรงๆ)"""
    global _pytrends_blocked, _pytrends_last_call_ts

    if _pytrends_blocked:
        return None

    # หน่วงเวลาให้ห่างจากคำขอก่อนหน้าอย่างน้อย PYTRENDS_MIN_INTERVAL_SEC
    elapsed = time.time() - _pytrends_last_call_ts
    if elapsed < PYTRENDS_MIN_INTERVAL_SEC:
        time.sleep(PYTRENDS_MIN_INTERVAL_SEC - elapsed)

    try:
        pt = _get_pytrends_client()
        pt.build_payload([word], timeframe=timeframe, geo=geo)
        df = pt.interest_over_time()
        _pytrends_last_call_ts = time.time()
        if df is None or df.empty or word not in df.columns:
            return None
        timeline_data = []
        for dt, row in df.iterrows():
            timeline_data.append({
                "date": dt.strftime("%b %d, %Y"),
                "timestamp": str(int(dt.timestamp())),
                "values": [{"extracted_value": int(row[word])}],
                "partial_data": bool(row.get("isPartial", False)),
            })
        return {"timeline_data": timeline_data}
    except Exception as e:
        _pytrends_last_call_ts = time.time()
        err_str = str(e)
        if "429" in err_str:
            _pytrends_blocked = True
            print(f"  🚫 [pytrends fallback] โดน Google บล็อก (429) ตอนดึง '{word}' — หยุดใช้ pytrends ต่อสำหรับรอบนี้ทั้งหมด (กันโดนบล็อกหนักขึ้น)")
        else:
            print(f"  ⚠️ [pytrends fallback] ดึงข้อมูล '{word}' ไม่สำเร็จ: {e}")
        return None


# [trend_final_v2.py L1746-L1754]
def _infer_geo_from_query(query: str) -> str:
    """เดาขอบเขตประเทศจากข้อความ query แบบง่ายๆ (ยังไม่มีช่องให้ตั้งค่า geo แยก - ใช้ query ที่มีอยู่แล้วแทน):
    เจอคำว่า Thailand/Thai/ไทย ใน query -> จำกัด Google Trends เฉพาะไทย (geo="TH")
    ไม่เจอ -> ปล่อยทั้งโลก (geo="") เหมือนพฤติกรรมเดิมของระบบก่อนแก้จุดนี้
    หมายเหตุ: รองรับแค่ 2 ทาง (ไทย/โลก) เท่านั้น query ที่พูดถึงประเทศอื่นจะถูกจัดเป็น "ทั้งโลก" ไปด้วย"""
    q = (query or "").lower()
    if "thailand" in q or "thai" in q or "ไทย" in (query or ""):
        return "TH"
    return ""


# [trend_final_v2.py L1757-L1783]
def _data_quality_label(pct_nonzero_mean):
    """E4 (2026-09-09, Backlog ข้อ 7/E4 ใน Evaluation Phase) - แปลง % เดือนที่มีข้อมูลจริงเฉลี่ยของ
    คลัสเตอร์ เป็นป้าย 3 ระดับ

    เกณฑ์นี้อิงจากข้อมูลจริงที่วัดได้ในโปรเจกต์ (ไม่ใช่เลขเดา) - ดู Detail/02 แหล่งข้อมูล/Google
    Trends และ Geo.md: คำหางยาวอังกฤษ = 0%, คำสั้นทั่วไป = 66-80%, เฉลี่ยรวม 123 คีย์เวิร์ดจริง = 12.2%
    และเทียบ 2 คลัสเตอร์จริงจากรัน 2026-08-18 โดยตรง (memory/analysis_logs/.../step5a_monthly_
    trends.xlsx): คลัสเตอร์ที่ระเบิดจริง ("Transparent Charcoal Probiotic Body Care", Z_Delta
    1,126,551.54) มีค่าเฉลี่ยแค่ 1.32% ส่วนคลัสเตอร์ที่นิ่งปกติ ("Trusted Natural Dermocosmetic...",
    Z_Delta 2.82 ปกติ) มีค่าเฉลี่ย 4.18% - สูงกว่ากันชัดเจนราว 3 เท่า แม้ทั้งคู่จะ "บาง" เทียบกับคำสั้น
    ทั่วไปก็ตาม

    ⚠️ ยังเป็นเกณฑ์เบื้องต้นจากการเทียบแค่ 2 เคสจริง (ไม่ใช่ calibrate อย่างเป็นทางการ) - ปรับได้ถ้าเจอ
    ข้อมูลเพิ่มในอนาคต (ดูแนวทางเดียวกับ Longevity Score v2 ข้อ 9 ที่ยอมรับตรงๆ ว่าน้ำหนักยังไม่ fit
    จากข้อมูลขนาดใหญ่พอ)

    🆕 (2026-09-12, audit C3) ขยับ threshold "thin" จาก <3% เป็น <15% - หลักฐานใหม่ (รอบรัน 2026-09-11)
    เจอ "Novel Cosmetic Actives" (3.39%, เพิ่งพ้นเกณฑ์เดิมแค่นิดเดียว) ได้ Z_Delta +2.2 ขึ้นอันดับ 1 ทั้งที่
    รูปแบบข้อมูลเหมือนเคส "ระเบิด" ที่ใช้ calibrate เกณฑ์เดิมทุกประการ (แทบเป็นศูนย์ตลอดแล้วโผล่มาทีเดียว)
    - เลือก 15% เป็นจุดกึ่งกลาง (ไม่ใช่ 30% ตามที่มีคนเสนอ เพราะยังไม่ผ่านการ calibrate เป็นทางการ จะตัด
    คีย์เวิร์ดออกเยอะเกินไปโดยไม่มีหลักฐานรองรับเพิ่ม) แก้เฉพาะจุดตัด "thin" เท่านั้น ไม่แตะ "rich" (20%)
    """
    if pct_nonzero_mean < 15:
        return "thin"
    if pct_nonzero_mean < 20:
        return "adequate"
    return "rich"


# [trend_final_v2.py L1786-L1811]
def compute_data_quality_by_cluster(monthly_merged):
    """E4 - คำนวณ "% เดือนที่มีข้อมูลจริง" ต่อคีย์เวิร์ด แล้วเฉลี่ยขึ้นเป็นระดับคลัสเตอร์

    monthly_merged: DataFrame ที่มีคอลัมน์ Keyword, cluster_id, search_avg (ก่อนตัด zero-noise ยาวด้วย
    remove_long_zero_noise ในฟังก์ชัน forecast_trend() - ตั้งใจใช้ก่อนตัดเสมอ เพราะการตัด zero-run ยาว
    ทำให้ % ที่คำนวณได้ดูดีเกินจริง ซ่อนความบางของข้อมูลจริงไป)

    เฉลี่ย (mean) ข้ามคีย์เวิร์ดในคลัสเตอร์ ไม่ใช่ min - เพราะ 1 คีย์เวิร์ดที่ 0% ปนอยู่ใน 20 คำไม่ควร
    ทำให้ทั้งคลัสเตอร์ดูแย่เท่ากับคลัสเตอร์ที่มีแค่ 2-3 คำแล้วทุกคำ 0% หมด - แต่เก็บ min ไว้เป็นค่าที่สอง
    เผื่ออยากรู้คำที่แย่สุดในคลัสเตอร์ด้วย

    Returns:
        DataFrame คอลัมน์ cluster_id, pct_nonzero_mean, pct_nonzero_min, n_keywords, Data_Quality
    """
    per_kw = monthly_merged.groupby(["cluster_id", "Keyword"], as_index=False).agg(
        pct_nonzero=("search_avg", lambda s: (s != 0).mean() * 100),
    )
    agg = per_kw.groupby("cluster_id", as_index=False).agg(
        pct_nonzero_mean=("pct_nonzero", "mean"),
        pct_nonzero_min=("pct_nonzero", "min"),
        n_keywords=("pct_nonzero", "size"),
    )
    agg["pct_nonzero_mean"] = agg["pct_nonzero_mean"].round(2)
    agg["pct_nonzero_min"] = agg["pct_nonzero_min"].round(2)
    agg["Data_Quality"] = agg["pct_nonzero_mean"].apply(_data_quality_label)
    return agg


# [trend_final_v2.py L1814-L2326]
def forecast_trend(output_dir, trend_keyword_mapping, user_query, monthly_df_override=None,
                    horizon=36):
    """
    🆕 (2026-09-10) horizon: จำนวนเดือนที่พยากรณ์ล่วงหน้า (default 36 = 3 ปี) - เดิม hardcode 36 ในตัว
    ตอนนี้รับเป็น param เพื่อให้ผู้ใช้เลือกตอนรัน (prompt_run_config ถามเป็น "ปี" แล้วคูณ 12) - แค่
    เปลี่ยนตัวเลขก้าว recursive forecast ไม่ได้แตะ logic (ตัวกันโมเดลระเบิด/Holdout RMSE ไม่กระทบ)

    🆕 (2026-09-09) monthly_df_override: DataFrame ทางเลือก (คอลัมน์ Keyword/start_date/search_avg -
    รูปแบบเดียวกับที่ขั้น "DATA PREPARATION" ปกติสร้างจาก serp_api()) - ถ้าส่งมา จะ**ข้าม**การยิง
    SerpAPI ไปเลย ใช้ข้อมูลนี้แทน แล้วเดินขั้นตอนที่เหลือทั้งหมด (zero-noise trim, feature engineering,
    4 โมเดลพยากรณ์ recursive + ตัวกันโมเดลระเบิด, เลือกโมเดลด้วย Holdout RMSE, E4 data quality,
    generate_master_trend_report) เหมือนเดิมทุกประการ - ใช้ตอนอยาก swap แหล่งข้อมูล Google Trends
    (เช่น trendspyg แทน SerpAPI - ดู tool/phase2_three_streams/fetch_trends_worldwide.py - เดิมชื่อ
    workspace/, เปลี่ยนเป็น tool/ แล้ว) โดยไม่
    ต้องเขียน pipeline การพยากรณ์ทั้งหมดซ้ำ (ของเดิมทดสอบผ่านแล้วจริง อย่าเสี่ยง duplicate logic)
    """
    global total_input_tokens, total_output_tokens
    os.makedirs(output_dir, exist_ok=True)
    
    def safe_json_parse(content: str):
        if not content: return None
        content = content.strip()
        match = re.search(r"(\{.*\}|\[.*\])", content, re.DOTALL)
        if match:
            try: return json.loads(match.group(1))
            except: return None
        return None

    def serp_api(keywords, dtype, geo=""):
        all_results = {}
        serpapi_quota_exhausted = False
        for word in keywords:
            interest_data = None

            if not serpapi_quota_exhausted:
                try:
                    params = {"engine": "google_trends", "q": word, "date": "all", "tz": "420", "data_type": dtype, "api_key": SERPAPI_KEY}
                    if geo:
                        params["geo"] = geo
                    search = GoogleSearch(params)
                    results = search.get_dict()
                    if "error" in results:
                        err_msg = str(results["error"])
                        print(f"  ⚠️ SerpAPI error for '{word}': {err_msg}")
                        if any(kw in err_msg.lower() for kw in ["run out of searches", "quota", "exceeded", "limit"]):
                            serpapi_quota_exhausted = True
                            print("  🔁 SerpAPI ดูเหมือนโควตาหมด — สลับไปใช้ pytrends (fallback ฟรี) สำหรับคีย์เวิร์ดที่เหลือ")
                    elif dtype == 'TIMESERIES' and results.get("interest_over_time"):
                        interest_data = results.get("interest_over_time")
                except Exception as e:
                    print(f"  ⚠️ SerpAPI request ล้มเหลวสำหรับ '{word}': {e}")

            if interest_data is None and dtype == 'TIMESERIES':
                fallback_data = _pytrends_interest_over_time(word, geo=geo)
                if fallback_data:
                    print(f"  ✅ [pytrends] ได้ข้อมูลสำรองสำหรับ '{word}'")
                    interest_data = fallback_data

            if interest_data:
                all_results[word] = interest_data
        return all_results
        
    def timeseries_to_df(data):
        rows = []
        for keyword, content in data.items():
            if content and 'timeline_data' in content:
                for entry in content['timeline_data']:
                    for val in entry.get('values', []):
                        rows.append({'Keyword': keyword, 'Date': entry.get('date'), 'Timestamp': entry.get('timestamp'), 'Interest Value': val.get('extracted_value'), 'Is Partial': entry.get('partial_data', False)})
        return pd.DataFrame(rows)

    def parse_date_range(label: str):
        if pd.isna(label): return pd.Series({"start_date": pd.NaT, "end_date": pd.NaT})
        s = str(label).replace("\u2009", " ").strip()
        sep = "–" if "–" in s else "-" if "-" in s else None
        try:
            if sep:
                left, right = s.split(sep, 1)
                left, right = left.strip(), right.strip()
                m_year = re.search(r"(\d{4})", right)
                year = m_year.group(1) if m_year else str(datetime.now().year)
                end_str = f"{right.replace(year, '').strip()} {year}" if re.search(r"[A-Za-z]", right.replace(year, "").strip()) else f"{re.search(r'[A-Za-z]+', left).group(0) if re.search(r'[A-Za-z]+', left) else 'Jan'} {right.replace(year, '').strip()} {year}"
                start_str = left if re.search(r"\d{4}", left) else f"{left} {year}"
                return pd.Series({"start_date": pd.to_datetime(start_str), "end_date": pd.to_datetime(end_str)})
            return pd.Series({"start_date": pd.to_datetime(s), "end_date": pd.to_datetime(s)})
        except: return pd.Series({"start_date": pd.NaT, "end_date": pd.NaT})
    
    def remove_long_zero_noise(df, zero_threshold, group_col):
        df = df.sort_values([group_col, "start_date"]).copy()
        def process_cluster(g):
            g = g.copy()
            g["is_zero"] = g["search_avg"] == 0
            g["zero_group"] = (g["is_zero"] != g["is_zero"].shift()).cumsum()
            rows_to_keep = []
            for _, sub in g.groupby("zero_group"):
                if sub["is_zero"].iloc[0]:
                    if len(sub) > zero_threshold: rows_to_keep.append(sub.tail(zero_threshold))
                    else: rows_to_keep.append(sub)
                else: rows_to_keep.append(sub)
            if not rows_to_keep: return pd.DataFrame()
            return pd.concat(rows_to_keep).drop(columns=["is_zero", "zero_group"])
        
        results = [process_cluster(group) for _, group in df.groupby(group_col)]
        return pd.concat(results, ignore_index=True) if results else pd.DataFrame(columns=df.columns)

    # Phase 0 (2026-08-28): ตัด filter_relevant_news_llm() + search_news() ออก
    # ทั้งคู่ถูกเรียกจากบล็อก NEWS PROCESSING ที่ถูกตัดไปเท่านั้น จึงกลายเป็นโค้ดตายทันที
    # (verify ด้วย grep แล้วว่าไม่มีที่อื่นเรียกใช้)

    def get_month_bounds(date_obj): return date_obj.strftime('%Y-%m-%d'), (date_obj + pd.offsets.MonthEnd(0)).strftime('%Y-%m-%d')
 
    def create_features(df, target_col='z_score', group_col='kw_cluster_id'):
        df = df.copy().sort_values([group_col, 'start_date'])
        for l in [1, 3, 12]: df[f'lag_{l}'] = df.groupby(group_col)[target_col].shift(l)
        df['rolling_mean_3m'] = (df.groupby(group_col)[target_col].shift(1).groupby(df[group_col]).rolling(3).mean().reset_index(level=0, drop=True))
        df['z_volatility_3m'] = (df.groupby(group_col)[target_col].shift(1).groupby(df[group_col]).rolling(3).std().reset_index(level=0, drop=True))
        df['z_velocity'] = df['lag_1'] - df['lag_3']
        search_vol = (df.groupby(group_col)['search_avg'].shift(1).groupby(df[group_col]).rolling(3).std().reset_index(level=0, drop=True))
        df['is_stable'] = (df['z_volatility_3m'] < 0.5).astype(int)
        df['is_search_stable'] = (search_vol < search_vol.median()).astype(int)
        df['month'] = df['start_date'].dt.month
        df['month_sin'], df['month_cos'] = np.sin(2 * np.pi * df['month'] / 12), np.cos(2 * np.pi * df['month'] / 12)
        df['is_summer'] = df['month'].isin([6,7,8]).astype(int)
        # Phase 0 (2026-08-28): ตัดการสร้าง news_relevance_count/news_momentum ออก (ฟีเจอร์ตาย 0.0%)
        # 'new_product_mentions' ถูกตัดไปพร้อมกันเพราะไม่เคยถูกเซ็ตค่าจากที่ไหนเลย และไม่เคยอยู่ใน
        # feature_cols - เป็นโค้ดตายที่หลงเหลือมา (verify ด้วย grep แล้วว่าอ้างถึงแค่บรรทัดนี้จุดเดียว)
        return df.fillna(0)

    def get_rolling_z_score(x):
        return ((x - x.rolling(window=12, min_periods=4).mean()) / x.rolling(window=12, min_periods=4).std(ddof=1)).replace([np.inf, -np.inf], 0).fillna(0)
    
    def run_all_models(df_group, feature_cols, target_col='z_score', horizon=36, group_col='kw_cluster_id', holdout=6):
        df_group = df_group.sort_values('start_date').copy()
        n_rows = len(df_group)
        if n_rows < 8: return pd.DataFrame()

        entity_id = df_group[group_col].iloc[0]
        last_date = df_group['start_date'].max()
        future_dates = pd.date_range(start=last_date + pd.offsets.MonthBegin(1), periods=horizon, freq='MS')
        tree_features = [c for c in feature_cols if c in df_group.columns]
        results_list = []

        # กันข้อมูล `holdout` เดือนสุดท้ายไว้เป็นชุดทดสอบที่โมเดลไม่เคยเห็นตอนเทรน (out-of-sample)
        # ใช้เลือกโมเดลที่ดีที่สุดแทนการวัดด้วย in-sample RMSE (ซึ่งทำให้โมเดลที่ overfit เก่ง
        # เช่น XGBoost ชนะทุกครั้งเพราะ "จำ" ข้อมูลเทรนได้แม่นเกินจริง ไม่ได้แปลว่าพยากรณ์อนาคตแม่น)
        can_holdout = n_rows >= holdout + 8
        train_df = df_group.iloc[:-holdout] if can_holdout else df_group
        test_df = df_group.iloc[-holdout:] if can_holdout else df_group.iloc[0:0]

        def add_results(model_name, dates, values, result_type):
            for d, v in zip(dates, values):
                results_list.append({group_col: entity_id, 'Model': model_name, 'Date': d, 'z_score': v, 'Type': result_type})

        # --- ตัวกันโมเดลพยากรณ์ระเบิด (พบจริงในรอบ 2026-08-18: LinearRegression พยากรณ์ 48 เดือน
        #     แบบ recursive แล้วความคลาดเคลื่อนถูกป้อนกลับเป็น lag ของเดือนถัดไปทบต้นไปเรื่อยๆ จนค่า
        #     ระเบิดจาก 0.21 เป็น 1,126,551 - มากกว่าจริง 5 ล้านเท่า ทั้งที่ RMSE ช่วง Holdout 6 เดือน
        #     ดูปกติดี เพราะการระเบิดยังไม่ทันแสดงตัวในช่วงสั้นๆ นั้น)
        #     ขอบเขตอ้างอิงจากข้อมูลจริงของคีย์เวิร์ดนี้เอง (ไม่ใช้เลขตายตัว) กันตัดเทรนด์ที่แรงจริงทิ้งผิดๆ
        hist_span = max(float(df_group[target_col].max() - df_group[target_col].min()), 1.0)
        stability_bound = max(15.0, 20.0 * hist_span)

        def _forecast_is_stable(forecast_vals):
            arr = np.asarray(list(forecast_vals), dtype=float)
            if arr.size == 0 or not np.all(np.isfinite(arr)):
                return False
            return bool(np.all(np.abs(arr) <= stability_bound))

        def _warn_unstable(model_name):
            print(f"    ⚠️ [{entity_id}] {model_name} พยากรณ์ไม่เสถียร (เกินขอบเขต ±{stability_bound:.1f}) "
                  f"- ตัดออกจากการแข่งขันเลือกโมเดลรอบนี้")

        # --- Statistical models: fit เต็มข้อมูลไว้ทำ Fit(in-sample)+Forecast(อนาคต) สำหรับรายงาน
        #     แล้วเทรนซ้ำเฉพาะ train_df เพื่อทำนายช่วง holdout แบบไม่เคยเห็นมาก่อน ไว้ใช้เลือกโมเดล ---
        # หมายเหตุ: เดิมมี Prophet + ARIMA อยู่ตรงนี้ด้วย - ตัดออกแล้ว (2026-08-19)
        # Prophet: backtest ย้อนหลัง 31 คีย์เวิร์ดพบว่าไม่เคยถูกเลือกเป็นโมเดลชนะเลยสักครั้ง (0/31)
        #   น่าจะเพราะข้อมูลความสนใจรายเดือนของส่วนผสม/สินค้าไม่มีฤดูกาลชัดแบบที่ Prophet ถนัด
        #   (ออกแบบมาสำหรับ daily/weekly ที่มีวันหยุด)
        # ARIMA: ตัดออกหลัง walk-forward validation (6 cutoff x 31 คำ = 186 จุด) พบว่าถูกเลือกบ่อย
        #   เป็นอันดับ 2 (47/186 ครั้ง) แต่แม่นจริงแค่ 23.4% - แย่กว่า LightGBM ที่ตัดไปก่อนหน้า (20%)
        #   ARIMA(1,1,0) ไม่มีองค์ประกอบฤดูกาล พยากรณ์ยาวมักแบนราบเข้าหาค่าคงที่ ตามการเปลี่ยนแปลง
        #   จริงที่ผันผวนไม่ทัน (ดู Detail/_data/walkforward_results.csv)
        try:
            hw_model = ExponentialSmoothing(df_group[target_col].values, trend='add', seasonal='add', seasonal_periods=12, initialization_method="estimated").fit()
            hw_fc = hw_model.forecast(horizon)
            if _forecast_is_stable(hw_fc):
                add_results('Holt-Winters', df_group['start_date'], hw_model.fittedvalues, 'Fit')
                add_results('Holt-Winters', future_dates, hw_fc, 'Forecast')
                if can_holdout:
                    hw_ho = ExponentialSmoothing(train_df[target_col].values, trend='add', seasonal='add', seasonal_periods=12, initialization_method="estimated").fit()
                    add_results('Holt-Winters', test_df['start_date'], hw_ho.forecast(holdout), 'Holdout')
            else:
                _warn_unstable('Holt-Winters')
        except Exception: pass

        def _recursive_forecast(model, seed_df):
            """พยากรณ์ต่อจาก seed_df ไปข้างหน้า horizon เดือน แบบ recursive (ป้อนค่าที่ทำนายได้กลับเป็น lag ของก้าวถัดไป)"""
            forecast_vals = []
            curr_df = seed_df.copy()
            for step in range(horizon):
                next_dt = future_dates[step]
                def get_lag(offset): return curr_df[target_col].iloc[-offset] if len(curr_df) >= offset else 0
                current_vol = curr_df[target_col].iloc[-3:].std() if len(curr_df) >= 3 else curr_df[target_col].std()

                row_dict = {
                    'lag_1': get_lag(1), 'lag_3': get_lag(3), 'lag_12': get_lag(12),
                    'rolling_mean_3m': curr_df[target_col].iloc[-3:].mean() if len(curr_df) >= 3 else curr_df[target_col].mean(),
                    'z_volatility_3m': current_vol, 'z_velocity': get_lag(1) - get_lag(3),
                    'month_sin': np.sin(2*np.pi*next_dt.month/12), 'month_cos': np.cos(2*np.pi*next_dt.month/12),
                    'is_summer': int(next_dt.month in [6,7,8]), 'is_stable': int(current_vol < 0.5)
                }
                pred = model.predict(pd.DataFrame([row_dict])[tree_features])[0]
                forecast_vals.append(pred)
                new_row = curr_df.iloc[-1:].copy()
                new_row['start_date'] = next_dt
                new_row[target_col] = pred
                curr_df = pd.concat([curr_df, new_row], ignore_index=True)
            return forecast_vals

        # หมายเหตุ: เดิมมี LightGBM อยู่ในนี้ด้วย - ตัดออกแล้ว (2026-08-19) เพราะ backtest ย้อนหลัง 31
        # คีย์เวิร์ดพบว่าถูกเลือกเป็นโมเดลชนะบ่อย (5/31) แต่พอทายจริงแม่นแค่ 20% (มักทายค่าใกล้ 0.00
        # เมื่อข้อมูลเทรนน้อย - โครงสร้าง leaf-wise ของ LightGBM overfit ง่ายกว่า XGBoost บนข้อมูล
        # ~36 แถวแบบนี้) อันตรายกว่าไม่มีเพราะมันแย่งตำแหน่งผู้ชนะจากโมเดลอื่นที่อาจแม่นกว่า
        model_specs = {
            'RandomForest': lambda: RandomForestRegressor(n_estimators=200, random_state=42),
            'LinearRegression': lambda: LinearRegression(),
            'XGBoost': lambda: xgb.XGBRegressor(n_estimators=200, learning_rate=0.05, random_state=42),
        }
        for name, make_model in model_specs.items():
            try:
                model_full = make_model()
                model_full.fit(df_group[tree_features], df_group[target_col])
                fit_vals = model_full.predict(df_group[tree_features])
                fc_vals = _recursive_forecast(model_full, df_group)

                if not _forecast_is_stable(fc_vals):
                    # จุดที่พบปัญหาจริง: LinearRegression ป้อนค่าที่ทำนายได้กลับเป็น lag ของเดือนถัดไป
                    # 48 รอบติดต่อกัน (recursive) ความคลาดเคลื่อนเล็กๆ จึงถูกขยายทบต้นจนระเบิดได้
                    # (โมเดล tree-based ไม่ค่อยเจอปัญหานี้ เพราะค่าที่ทำนายถูกจำกัดด้วยค่าที่เคยเห็นตอนเทรน)
                    _warn_unstable(name)
                    continue

                add_results(name, df_group['start_date'], fit_vals, 'Fit')
                add_results(name, future_dates, fc_vals, 'Forecast')

                if can_holdout:
                    # เทรนซ้ำด้วย train_df เท่านั้น (ไม่เห็นช่วง holdout) แล้วทำนายตรงๆ ด้วย feature ของ
                    # test_df ที่คำนวณจากประวัติจริงอยู่แล้ว (ไม่ใช่ recursive) นี่คือค่าที่วัด RMSE แบบ
                    # out-of-sample จริงๆ ไม่ใช่ค่าที่โมเดลเคยเห็นตอนเทรนแบบ 'Fit' ด้านบน
                    model_ho = make_model()
                    model_ho.fit(train_df[tree_features], train_df[target_col])
                    holdout_preds = model_ho.predict(test_df[tree_features])
                    add_results(name, test_df['start_date'], holdout_preds, 'Holdout')
            except Exception: pass
        return pd.DataFrame(results_list)

    def generate_master_trend_report(results_df, meta_df, quality_df=None):
        # 🆕 (2026-09-09, E4) quality_df: output ของ compute_data_quality_by_cluster() ด้านบน (module
        # level) - คอลัมน์ cluster_id, pct_nonzero_mean, pct_nonzero_min, Data_Quality - ถ้าไม่ส่งมา
        # (None) ใช้ค่า "unknown" แทน ไม่ error (backward compatible กับ caller เก่าที่ยังไม่ส่งมา)
        report_data = []
        for cluster_id in results_df['cluster_id'].dropna().unique():
            cluster_res = results_df[results_df['cluster_id'] == cluster_id].copy()
            if cluster_res.empty: continue

            target_model = cluster_res['best_model'].iloc[0] if 'best_model' in cluster_res.columns else cluster_res[cluster_res['Type'] == 'Forecast'].groupby('Model')['z_score'].mean().idxmax()
            model_data = cluster_res[cluster_res['Model'] == target_model]

            meta = meta_df[meta_df['cluster_id'] == cluster_id]
            display_name = meta['cluster_name'].iloc[0] if not meta.empty else f"Cluster {cluster_id}"
            keywords_str = ", ".join(meta['Keyword'].dropna().unique()) if not meta.empty else ""

            history = model_data[model_data['Type'] == 'Fit'].sort_values('Date').dropna(subset=['z_score'])
            forecast = model_data[model_data['Type'] == 'Forecast'].sort_values('Date').dropna(subset=['z_score'])
            if forecast.empty: continue

            current_z = history['z_score'].iloc[-1] if not history.empty else 0
            forecast_avg_z = forecast['z_score'].mean()
            z_delta = forecast_avg_z - current_z

            status = "Major Breakout" if z_delta > 0.8 else "Rising" if z_delta > 0.2 else "Fading" if z_delta < -0.2 else "Stable"
            peak_idx = forecast['z_score'].idxmax()

            quality_row = quality_df[quality_df['cluster_id'] == cluster_id] if quality_df is not None else None
            if quality_row is not None and not quality_row.empty:
                data_quality = quality_row['Data_Quality'].iloc[0]
                pct_months_with_data = float(quality_row['pct_nonzero_mean'].iloc[0])
            else:
                data_quality, pct_months_with_data = "unknown", None

            report_data.append({
                'cluster_id': cluster_id, 'Cluster': display_name, 'Model': target_model, 'Status': status,
                'Current_Z': round(float(current_z), 2), 'Forecast_Avg_Z': round(float(forecast_avg_z), 2),
                'Z_Delta': round(float(z_delta), 2), 'Peak_Month': pd.to_datetime(forecast.loc[peak_idx, 'Date']).strftime('%b %Y'),
                'Keywords': keywords_str,
                'Context': {'Holt-Winters': 'Trend and short seasonality', 'RandomForest': 'Complex Patterns', 'XGBoost': 'Gradient Boosting', 'LinearRegression': 'Trend Baselines'}.get(target_model, 'Best model'),
                'Data_Quality': data_quality, 'Pct_Months_With_Data': pct_months_with_data,
            })
        return pd.DataFrame(report_data).sort_values(by='Z_Delta', ascending=False).reset_index(drop=True)

    def generate_explainable_llm_prompt(master_report, user_query, current_time):
        cluster_inputs = []
        for row in master_report:
            # 🆕 (2026-09-09, E4) เพิ่ม data_quality/pct_months_with_data ต่อท้าย 10 ฟิลด์เดิม - ต้องแก้
            # unpacking ตรงนี้ด้วยเสมอเวลาเพิ่มคอลัมน์ใหม่ใน generate_master_trend_report() เพราะ
            # master_report เป็น list-of-lists ตำแหน่ง (positional) ไม่ใช่ dict - ไม่แก้จะ error
            # "too many values to unpack" ทันทีที่ Google Trends credit กลับมาแล้วเรียกจริง
            (cluster_id, cluster_name, model, status, current_z, forecast_avg_z, z_delta, peak_month,
             keywords, context, data_quality, pct_months_with_data) = row
            cluster_inputs.append({
                "cluster_id": cluster_id, "cluster_name": cluster_name, "status": status,
                "current_z": current_z, "forecast_avg_z": forecast_avg_z, "z_delta": z_delta,
                "peak_month": peak_month, "keywords": keywords.split(", "), # User specifically requested keywords
                "model_used": model, "model_context": context,
                # 🆕 (2026-09-09, E4) ให้ LLM เห็นว่าตัวเลขข้างบนยืนอยู่บนข้อมูลหนา/บางแค่ไหน ก่อนตัดสิน
                # confidence_level/driver_explanation - ดู Detail/04.../Evaluation Phase — ค่าที่ควรมี.md
                "data_quality": data_quality, "pct_months_with_real_data": pct_months_with_data,
            })
        # หมายเหตุ: เดิมให้ LLM ตัดสิน investment_signal เองในนี้ด้วย - ตัดออกแล้ว (2026-08-20) เพราะ
        # walk-forward validation (n=186) พิสูจน์ว่าแม่นแค่ 40.9% แย่กว่าคำนวณจาก Z_Delta ตรงๆ (63.4%)
        # ดู compute_investment_signal() - ค่านี้ถูกคำนวณแทนหลัง parse ผล LLM แล้วเสมอ ไม่ขอจาก LLM อีก
        system_prompt = """You are a Quantitative Trend Intelligence Analyst. Respond ONLY with valid JSON, no extra text, no markdown code fences, following this exact OUTPUT FORMAT:
        { "market_overview": { "query": "<user_query>", "current_trend_strength": "Weak | Moderate | Strong", "estimated_trend_duration": "Short-term | Medium-term | Long-term", "overall_direction": "Strengthening | Stable | Weakening", "summary": "<max 3 sentences>" },
        "cluster_analysis": [ { "cluster_id": "<id>", "cluster_name": "<name>", "keywords": ["<kw1>"], "trend_stage": "Emerging | Growing | Peaking | Declining | Stable", "primary_driver": "Organic Seasonality | External Shock | Structural Growth | Mixed/Uncertain", "confidence_level": "High | Medium | Low", "driver_explanation": "<data-grounded reasoning>", "consumer_intent_signal": "<what consumers seek>", "estimated_duration": "Short-term | Medium-term | Long-term", "risk_scenario_if_forecast_fails": "<downside case>", "executive_summary": "<max 2 sentences>" } ] }

        IMPORTANT — each cluster's input includes "data_quality" (thin | adequate | rich) and
        "pct_months_with_real_data" (% of months with non-zero Google Trends data behind this
        cluster's Z_Delta). A cluster with data_quality="thin" NEVER earns confidence_level="High",
        no matter how extreme its z_delta looks — an extreme number built on thin data is a sign of
        model instability, not a strong trend. Mention the data thinness explicitly in
        driver_explanation whenever data_quality is "thin"."""
        return {"system_prompt": system_prompt, "user_prompt": f"Analyze the structured cluster trend data in relation to the query '{user_query}' at time '{current_time}'. DATA:\n{json.dumps(cluster_inputs, indent=2)}"}

    # --- 1. DATA PREPARATION ---
    # 🆕 FIX (2026-09-09): master_list มาจาก trend_keyword_mapping ล้วนๆ ไม่เกี่ยวกับว่าใช้ SerpAPI
    # หรือ override - ต้องคำนวณแบบไม่มีเงื่อนไข ไม่งั้น return ท้ายฟังก์ชัน (บรรทัดท้ายสุด) จะ
    # UnboundLocalError ทันทีที่ใช้ monthly_df_override (เจอจริงตอนรัน fetch_trends_worldwide.py)
    master_list = list(set([str(k).strip().lower() for kws in trend_keyword_mapping.values() for k in kws if k]))
    if monthly_df_override is not None:
        print("    -> [Step 5-7] ใช้ monthly_df_override ที่ส่งมา (ข้าม SerpAPI ไปเลย)")
        monthly_df = monthly_df_override.copy()
        monthly_df["Keyword"] = monthly_df["Keyword"].astype(str).str.strip().str.lower()
    else:
        geo = _infer_geo_from_query(user_query)
        print(f"    -> [Step 5-7] ขอบเขต Google Trends ที่ตรวจจับจาก query: {'ไทย (geo=TH)' if geo else 'ทั้งโลก (Worldwide)'}")
        df_timeseries = timeseries_to_df(serp_api(master_list, "TIMESERIES", geo=geo))

        if df_timeseries.empty: return list(trend_keyword_mapping.keys()), pd.DataFrame(), [], {"error": "No Google Trends data found."}

        # ตัดเดือนที่ Google Trends ยังเก็บข้อมูลไม่ครบ (partial_data=True) ทิ้งก่อนคำนวณ - ไม่งั้นเดือนล่าสุด
        # (มักเป็นเดือนปัจจุบันที่ยังไม่จบเดือน) จะโชว์ค่าต่ำผิดปกติ กลายเป็น "ปัจจุบันทรุดหนัก" ปลอมๆ
        if 'Is Partial' in df_timeseries.columns:
            n_before = len(df_timeseries)
            df_timeseries = df_timeseries[~df_timeseries['Is Partial'].fillna(False).astype(bool)]
            n_dropped = n_before - len(df_timeseries)
            if n_dropped:
                print(f"    -> ตัดข้อมูล Google Trends ที่ยังไม่ครบเดือนออก {n_dropped} จุด (กันเดือนล่าสุดดูทรุดปลอมๆ)")

        df_timeseries['Timestamp'] = pd.to_datetime(pd.to_numeric(df_timeseries['Timestamp'], errors='coerce'), unit='s').dropna()
        df_timeseries[["start_date", "end_date"]] = df_timeseries["Date"].apply(parse_date_range)
        df_timeseries['start_date'] = df_timeseries['start_date'].dt.to_period('M').dt.to_timestamp()
        monthly_df = df_timeseries.groupby(["Keyword", "start_date"], as_index=False).agg(search_avg=("Interest Value", "mean"))
        monthly_df["Keyword"] = monthly_df["Keyword"].astype(str).str.strip().str.lower()

    if monthly_df.empty:
        return list(trend_keyword_mapping.keys()), pd.DataFrame(), [], {"error": "No Google Trends data found."}

    excel_path_step5a = f"{output_dir}/step5a_monthly_trends.xlsx"
    monthly_df.to_excel(excel_path_step5a, index=False)
    print(f"    ✅ Successfully saved monthly trends to {excel_path_step5a}")

    mapping_list = [{'Keyword': str(kw).strip().lower(), 'cluster_id': i, 'cluster_name': c_name} for i, (c_name, kws) in enumerate(trend_keyword_mapping.items()) for kw in kws]
    mapping_df = pd.DataFrame(mapping_list)
    monthly_merged = monthly_df.merge(mapping_df, on='Keyword', how='inner')

    # FIX: Group by Composite ID to avoid duplicated keywords getting mixed arrays
    monthly_merged['kw_cluster_id'] = monthly_merged['Keyword'] + "_" + monthly_merged['cluster_id'].astype(str)
    df_keyword_trim = remove_long_zero_noise(monthly_merged, 30, group_col="kw_cluster_id")

    # --- 3. (ว่าง) เดิมเป็นบล็อก NEWS PROCESSING ที่ยิง Google News + LLM หลายร้อยครั้งต่อรอบ
    #     (1 ครั้งต่อทุกคู่ คลัสเตอร์ x เดือน) เพื่อสร้างฟีเจอร์ news_relevance_count
    #     ตัดทิ้งทั้งก้อนใน Phase 0 (2026-08-28) เพราะ feature importance = 0.0000 เป๊ะทุก cutoff
    #     ทั้ง RandomForest และ XGBoost - จ่ายแพงที่สุดแต่โมเดลไม่ได้ใช้เลยแม้แต่นิดเดียว
    #     ต้นตอที่น่าจะทำให้ฟีเจอร์ตาย: ค้นข่าวด้วย "ชื่อคลัสเตอร์" ที่ยาวและเป็นภาษาการตลาด
    #     ย้อนหลังไปถึงปี 2004 ซึ่งแทบไม่มีข่าวตรงเลย ค่าจึงเป็น 0 เกือบทั้งตาราง

    # --- 4. FEATURE GEN & MODELING (AT COMPOSITE LEVEL) ---
    df_keyword_trim['z_score'] = df_keyword_trim.groupby('kw_cluster_id')['search_avg'].transform(get_rolling_z_score)
    df_keyword_processed = create_features(df_keyword_trim, target_col='z_score', group_col='kw_cluster_id')

    excel_path_step5b = f"{output_dir}/step5b_df_keyword_processed.xlsx"
    df_keyword_processed.to_excel(excel_path_step5b, index=False)
    print(f"    ✅ Successfully saved df_keyword_processed to {excel_path_step5b}")

    all_comparisons = []
    # Phase 0 (2026-08-28): ตัด 'news_relevance_count', 'news_momentum' ออก
    # feature importance = 0.0000 เป๊ะทั้ง RandomForest และ XGBoost ทุก cutoff (ดู
    # Detail/_data/feature_importance_noarima.csv) แต่เป็นต้นทุนใหญ่สุดใน pipeline
    # เพราะต้องยิง Google News + LLM 1 ครั้งต่อทุกคู่ (คลัสเตอร์ x เดือน) หลายร้อยคู่ต่อรอบ
    feature_cols = ['lag_1', 'lag_3', 'lag_12', 'rolling_mean_3m', 'z_volatility_3m', 'z_velocity']
    for kw_cid in df_keyword_processed['kw_cluster_id'].unique():
        kw_df = df_keyword_processed[df_keyword_processed['kw_cluster_id'] == kw_cid].sort_values('start_date')
        if len(kw_df) >= 8:
            # 🆕 (2026-09-10) horizon รับจาก param ของ forecast_trend (default 36 = 3 ปี) - ผู้ใช้เลือก
            # ตอนรันได้ เดิม (2026-09-09) hardcode 36 หลังเปลี่ยนจาก 48 - แค่ตัวเลขก้าว recursive
            # forecast ไม่แตะ logic (ตัวกันโมเดลระเบิด/Holdout RMSE ไม่กระทบ)
            res_df = run_all_models(kw_df, feature_cols, horizon=horizon, group_col='kw_cluster_id')
            if not res_df.empty: all_comparisons.append(res_df)

    if not all_comparisons: return list(trend_keyword_mapping.keys()), pd.DataFrame(), [], None
        
    df_all_results_kw = pd.concat(all_comparisons)
    df_all_results_kw['Date'] = pd.to_datetime(df_all_results_kw['Date'])

    # --- 5. AGGREGATE BACK TO CLUSTER LEVEL (เฉลี่ย ไม่ใช่บวกรวม Z-scores) ---
    # เดิมใช้ .sum() รวมคะแนนของคีย์เวิร์ดทั้งหมดในคลัสเตอร์ (มักมี ~18 คำ) ทำให้ผลรวมทะลุเกณฑ์ตัดสิน
    # (0.8/0.2/-0.2 ใน generate_master_trend_report ที่ออกแบบไว้สำหรับ z ตัวเดียว) แทบทุกคลัสเตอร์เสมอ
    # ไม่ว่าเทรนด์จะแรงจริงหรือไม่ - เปลี่ยนเป็น .mean() เพื่อให้กลับมาอยู่ในสเกลเดียวกับเกณฑ์ตัดสิน
    kw_cluster_map = df_keyword_processed[['kw_cluster_id', 'cluster_id', 'cluster_name']].drop_duplicates()
    df_all_results_kw = df_all_results_kw.merge(kw_cluster_map, on='kw_cluster_id', how='left')
    df_cluster_forecast = df_all_results_kw.groupby(['cluster_id', 'cluster_name', 'Model', 'Date', 'Type'], as_index=False)['z_score'].mean()

    actual_df = df_keyword_processed.groupby(['cluster_id', 'start_date'], as_index=False)['z_score'].mean().rename(columns={'start_date': 'Date', 'z_score': 'actual'})

    def _select_best_model(df_forecast, actual):
        """🆕 (2026-09-12, C1 audit finding) เดิมแข่งขันเลือก 1 ใน 4 โมเดลด้วย RMSE บนชุด Holdout (แค่ 6
        จุดข้อมูล - ตัวอย่างเล็กมาก, evaluate แบบ 1-step ป้อน lag จริง) แต่การพยากรณ์จริงที่ deploy เป็น
        recursive หลายก้าว (ป้อนค่าที่ทำนายได้กลับเป็น lag ก้าวถัดไป) - คนละงานกัน (ดู Detail/05
        งานที่ยังไม่ได้ทำ/แผนแก้ Data Science Audit.md ข้อ C1) ทดลองจริงด้วย
        evaluate_forecast_vs_baseline.py (rolling-origin backtest แบบ recursive ที่ h=3/6/12 เดือน บน
        ข้อมูลจริง 127 อนุกรมคีย์เวิร์ด + 14 คลัสเตอร์) พบว่า **RandomForest ตัวเดียวคงที่ทุกคลัสเตอร์
        ชนะ persistence baseline ชัดเจนที่ h=3/12 (11/14, 11/14 คลัสเตอร์) และไม่แพ้ที่ h=6 (7/14)** -
        ดีกว่า/สม่ำเสมอกว่าระบบแข่งขันเดิมที่แม้แต่ audit เองก็พบว่าไม่ชนะ baseline อย่างมีนัยสำคัญ - เลิก
        แข่งขัน ใช้ RandomForest เสมอ ยกเว้นคลัสเตอร์ที่ RandomForest ถูกตัวกันโมเดลระเบิด
        (_forecast_is_stable) ตัดออกไปจริง (ไม่มี 'Forecast' row เลย - เกิดยากมากเพราะโมเดล tree-based
        ไม่ค่อยเจอปัญหาค่าระเบิดแบบ LinearRegression) ถึง fallback ไปโมเดลอื่นที่มี Forecast จริง เลือก
        ด้วย Fit RMSE ต่ำสุด (คงตรรกะ fallback แบบเดิมไว้เฉพาะกรณีขอบนี้)"""
        PREFERRED_MODEL = "RandomForest"

        def _rmse_by(type_name, models=None):
            d = df_forecast[df_forecast['Type'] == type_name]
            if models is not None:
                d = d[d['Model'].isin(models)]
            d = d.merge(actual, on=['cluster_id', 'Date'], how='left').dropna(subset=['actual'])
            if d.empty:
                return pd.DataFrame(columns=['cluster_id', 'Model', 'RMSE'])
            return d.groupby(['cluster_id', 'Model']).apply(
                lambda g: np.sqrt(mean_squared_error(g['actual'], g['z_score'])), include_groups=False
            ).reset_index(name='RMSE')

        forecast_models_by_cluster = (
            df_forecast[df_forecast['Type'] == 'Forecast'].groupby('cluster_id')['Model'].apply(set)
        )

        rows = []
        for cid in df_forecast['cluster_id'].unique():
            available = forecast_models_by_cluster.get(cid, set())
            if PREFERRED_MODEL in available:
                rows.append({'cluster_id': cid, 'best_model': PREFERRED_MODEL})
            elif available:
                print(f"    ⚠️ คลัสเตอร์ {cid}: {PREFERRED_MODEL} ไม่เสถียร (ตัวกันโมเดลระเบิดตัดออก) "
                      f"-> fallback ไปโมเดลอื่นที่มี Forecast จริง เลือกด้วย Fit RMSE")
                fit_rmse = _rmse_by('Fit', models=available)
                fit_rmse = fit_rmse[fit_rmse['cluster_id'] == cid]
                if not fit_rmse.empty:
                    rows.append({'cluster_id': cid, 'best_model': fit_rmse.loc[fit_rmse['RMSE'].idxmin(), 'Model']})
                else:
                    rows.append({'cluster_id': cid, 'best_model': sorted(available)[0]})
            else:
                print(f"    ⚠️ คลัสเตอร์ {cid}: ไม่มีโมเดลไหนพยากรณ์ได้เสถียรเลย - ไม่มี best_model")
        return pd.DataFrame(rows)

    df_cluster_forecast = df_cluster_forecast.merge(_select_best_model(df_cluster_forecast, actual_df), on='cluster_id', how='left')
    
    excel_path_step5c = f"{output_dir}/step5c_df_cluster_forecast.xlsx"
    df_cluster_forecast.to_excel(excel_path_step5c, index=False)
    print(f"    ✅ Successfully saved df_cluster_forecast to {excel_path_step5c}")

    mapping_unique = mapping_df.drop_duplicates(subset=['Keyword', 'cluster_id']).copy()
    # 🆕 (2026-09-09, E4) ใช้ monthly_merged (ก่อนตัด zero-noise ยาว) ไม่ใช่ df_keyword_trim (หลังตัด) -
    # ดูเหตุผลเต็มใน docstring ของ compute_data_quality_by_cluster() ด้านบน (module level)
    quality_df = compute_data_quality_by_cluster(monthly_merged)
    master_report = generate_master_trend_report(df_cluster_forecast, mapping_unique, quality_df).values.tolist()
    
    analyze = None
    try:
        full_prompt = generate_explainable_llm_prompt(master_report, user_query, str(datetime.now().date()))
        response = client.chat.completions.create(model=MODEL_NAME, messages=[{"role": "system", "content": full_prompt["system_prompt"]}, {"role": "user", "content": full_prompt["user_prompt"]}], temperature=0, max_tokens=compute_max_tokens(full_prompt["system_prompt"] + full_prompt["user_prompt"]), response_format={"type": "json_object"})
        raw_content = response.choices[0].message.content
        parsed_dict = safe_json_parse(raw_content)

        if parsed_dict is None:
            print(f"❌ [Step 6-7] LLM ไม่ได้ตอบ JSON ที่ดึงออกมาได้เลย (ดู {len(raw_content or '')} ตัวอักษรแรก): {str(raw_content)[:300]!r}")
        else:
            try:
                analyze = ForecastAnalysis.model_validate(parsed_dict).model_dump()
                # แทนที่ investment_signal ของ LLM (ถ้ามีหลุดมา) ด้วยค่าคำนวณจาก Z_Delta เสมอ - ดู
                # compute_investment_signal() ไม่ใช่แค่ไม่ขอจาก LLM แต่บังคับ overwrite กันเผื่อ LLM ไม่ทำตามคำสั่ง
                row_by_cluster = {str(row[0]): row for row in master_report}
                for c in analyze.get("cluster_analysis", []):
                    row = row_by_cluster.get(str(c.get("cluster_id")))
                    c["investment_signal"] = compute_investment_signal(row[6] if row else None)
                    if row:
                        # 🆕 (2026-09-16) ชื่อ/คีย์เวิร์ดเป็นสำเนาของ input - เขียนทับด้วยค่าจริงเหมือน investment_signal
                        # เพราะ GLM-5 ตัดคีย์เวิร์ดเหลือ 4-5 คำจาก 8-15 คำที่ใช้พยากรณ์จริงใน 14/15 คลัสเตอร์ (ไม่ได้
                        # แต่งคำใหม่) ทำให้ "Forecast Keywords" ใน Master Report แสดงไม่ครบ
                        c["cluster_name"] = row[1]
                        c["keywords"] = [k for k in str(row[8]).split(", ") if k]
            except ValidationError as ve:
                print(f"❌ [Step 6-7] JSON ตอบกลับมาแต่ไม่ตรง schema ที่คาดไว้:\n{ve}")
    except Exception as e:
        print(f"❌ [Step 6-7] LLM call ล้มเหลว: {e}")

    return list(master_list), df_cluster_forecast, master_report, analyze


# [trend_final_v2.py L2328-L2328]
import pandas as pd


# [trend_final_v2.py L2329-L2329]
import os


# [trend_final_v2.py L2477-L2661]
def generate_master_markdown_report(user_query, final_trend_report, strategix_context, llm_forecast_analysis, product_results, final_stepic_insight, stepic_raw_analysis=None, master_report_dict=None):
    print(f"📄 Generating Master Trend Forecast Report for: {user_query}")
    
    md = [f"# 🌟 Master Trend Forecast Report: {user_query}\n"]
    md.append(f"**Generated on:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    md.append("---\n")

    # --- 1. EXECUTIVE SUMMARY (From STEPIC Integration & Forecast) ---
    md.append("## 1. Executive Summary\n")
    
    if final_stepic_insight and isinstance(final_stepic_insight, dict):
        md.append(f"- **Mega Trend Name:** {final_stepic_insight.get('mega_trend_name', 'N/A')}")
        md.append(f"- **Macro Direction:** {final_stepic_insight.get('macro_direction', 'N/A')}")
        md.append(f"- **Core Concept:** {final_stepic_insight.get('core_concept', 'N/A')}\n")

        personas = final_stepic_insight.get('emerging_personas', [])
        if personas:
            md.append("**Emerging Personas:**")
            if isinstance(personas, list):
                for p in personas:
                    if isinstance(p, dict):
                        # 🆕 (2026-09-11) LLM ตอบ field ชื่อ persona ไม่คงที่ (description/profile/summary/
                        # bio ต่างกันไปตาม provider) - เจอครั้งแรกตอนรันจริง (Typhoon ตอบ "profile")
                        # ก่อนหน้านี้ไม่เคยมีข้อมูลจริงมาทดสอบ code path นี้เลย (ติดเครดิต OpenRouter
                        # ตลอด) ลองไล่ทุก key ที่เจอมา ไม่เจอเลยค่อย fallback เป็นทั้ง dict
                        desc = next((p[k] for k in ("description", "profile", "summary", "bio") if p.get(k)),
                                   "")
                        md.append(f"  - **{p.get('name', 'Persona')}**: {desc or p}")
                    else:
                        md.append(f"  - {p}")
            else:
                md.append(f"  - {personas}")
            md.append("\n")

    if llm_forecast_analysis and isinstance(llm_forecast_analysis, dict) and "market_overview" in llm_forecast_analysis:
        mo = llm_forecast_analysis["market_overview"]
        md.append(f"**Market Overview:** {mo.get('summary', 'N/A')}")
        md.append(f"- **Trend Strength:** {mo.get('current_trend_strength', 'N/A')}")
        md.append(f"- **Direction:** {mo.get('overall_direction', 'N/A')}")
        md.append(f"- **Estimated Duration:** {mo.get('estimated_trend_duration', 'N/A')}\n")

    md.append("---\n")

    # --- 2. MACRO-ENVIRONMENTAL (STEPIC) ANALYSIS ---
    md.append("## 2. Macro-Environmental (STEPIC) Analysis\n")
    if stepic_raw_analysis and isinstance(stepic_raw_analysis, dict):
        
        soc = stepic_raw_analysis.get('society', {})
        if soc:
            md.append("### 🌐 Society")
            md.append(f"- **Concept:** {soc.get('concept', 'N/A')}")
            md.append(f"- **Behavioral Shift:** {soc.get('behavioral_shift', 'N/A')}")
            md.append(f"- **Projected Impact:** {soc.get('projected_impact', 'N/A')}\n")

        tech = stepic_raw_analysis.get('technology', {})
        if tech:
            md.append("### 💻 Technology")
            md.append(f"- **Core Technology:** {tech.get('core_technology', 'N/A')}")
            md.append(f"- **Innovation Driver:** {tech.get('innovation_driver', 'N/A')}")
            md.append(f"- **Adoption Stage:** {tech.get('adoption_stage', 'N/A')}\n")

        env = stepic_raw_analysis.get('environment', {})
        if env:
            md.append("### 🌱 Environment")
            md.append(f"- **Environmental Factor:** {env.get('environmental_factor', 'N/A')}")
            md.append(f"- **Sustainability Opportunity:** {env.get('sustainability_opportunity', 'N/A')}")
            md.append(f"- **ESG Driver:** {env.get('ESG_driver', 'N/A')}\n")

        pol = stepic_raw_analysis.get('policy', {})
        if pol:
            md.append("### ⚖️ Policy")
            md.append(f"- **Regulatory Trend:** {pol.get('regulatory_trend', 'N/A')}")
            md.append(f"- **Business Impact:** {pol.get('business_impact', 'N/A')}\n")

        ind = stepic_raw_analysis.get('industry', {})
        if ind:
            md.append("### 🏢 Industry")
            md.append(f"- **Market Structure:** {ind.get('market_structure', 'N/A')}")
            md.append(f"- **Strategic Positioning:** {ind.get('strategic_positioning', 'N/A')}")
            md.append(f"- **Investment Signal:** {ind.get('investment_signal', 'N/A')}\n")

        crea = stepic_raw_analysis.get('creativity', {})
        if crea:
            md.append("### 🎨 Creativity")
            md.append(f"- **Product Innovation:** {crea.get('product_innovation', 'N/A')}")
            md.append(f"- **Consumer Emotional Trigger:** {crea.get('consumer_emotional_trigger', 'N/A')}")
            md.append(f"- **Brand Expression:** {crea.get('brand_expression', 'N/A')}\n")
    else:
        md.append("No detailed STEPIC analysis available.\n")

    md.append("---\n")

    # --- 3. STRATEGIC PILLARS (From Knowledge Graph) ---
    md.append("## 3. Strategic Pillars & Execution\n")
    if strategix_context:
        cleaned_context = re.sub(r'^# .*\n', '', strategix_context).strip()
        md.append(cleaned_context + "\n")
    else:
        md.append("No strategic context available.\n")
    
    md.append("---\n")

    # --- 4. QUANTITATIVE FORECAST ANALYSIS ---
    md.append("## 4. Quantitative Cluster Forecasts\n")
    
    # --- NEW: Build a lookup mapping for keywords from master_report_dict ---
    cluster_keyword_map = {}
    if master_report_dict and "forecast_data" in master_report_dict:
        for cluster_data in master_report_dict["forecast_data"].get("clusters", []):
            c_name = cluster_data.get("Cluster")
            c_keys = cluster_data.get("Top Keywords", "N/A")
            if c_name:
                cluster_keyword_map[c_name] = c_keys
    # ------------------------------------------------------------------------

    if llm_forecast_analysis and isinstance(llm_forecast_analysis, dict) and "cluster_analysis" in llm_forecast_analysis:
        clusters = llm_forecast_analysis["cluster_analysis"]
        for c in clusters:
            c_name = c.get('cluster_name', 'Unknown Cluster')
            md.append(f"### {c_name}")
            
            # Fetch from our lookup map, fallback to LLM dict if necessary
            keywords_str = cluster_keyword_map.get(c_name, "N/A")
            if keywords_str == "N/A":
                keywords = c.get('keywords', [])
                keywords_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
            
            md.append(f"- **Forecast Keywords:** {keywords_str}")
            md.append(f"- **Trend Stage:** {c.get('trend_stage', 'N/A')}")
            md.append(f"- **Primary Driver:** {c.get('primary_driver', 'N/A')}")
            md.append(f"- **Investment Signal:** {c.get('investment_signal', 'N/A')}")
            md.append(f"- **Summary:** {c.get('executive_summary', 'N/A')}")
            md.append(f"- **Consumer Intent Signal:** {c.get('consumer_intent_signal', 'N/A')}\n")
    else:
        md.append("No cluster forecast data available.\n")

    md.append("---\n")

    # --- 5. MARKET EVIDENCE (Products Grouped By Pillar) ---
    md.append("## 5. Market Evidence: Matched Products\n")
    if product_results and isinstance(product_results, list):
        products_by_pillar = {}
        for p in product_results:
            pillar = str(p.get('Pillar', 'Uncategorized'))
            if pillar not in products_by_pillar:
                products_by_pillar[pillar] = []
            products_by_pillar[pillar].append(p)
            
        for pillar_name, products in products_by_pillar.items():
            md.append(f"### {pillar_name}")
            # คอลัมน์ FDA Status ถูกตัดออกแล้ว (Watsons ไม่มีข้อมูลสถานะ อย. ทำให้ช่องนี้ว่างทุกแถว)
            # ใส่ Sold แทน เพราะเป็นข้อมูลที่ Watsons มีจริงและช่วยดูขนาดของสินค้าที่แมตช์ได้
            # 🆕 (2026-09-14) เพิ่มคอลัมน์ "Why It Fits" - เหตุผลจาก LLM ว่าทำไมสินค้านี้เข้ากับเทรนด์
            # (Match/Partial/No-match + ประโยคสั้นๆ, ดู validate_at_scale_nvidia.py's
            # generate_match_reason()) - เดิมมีแต่ตาราง 5 คอลัมน์ ไม่มีคำอธิบายการจับคู่เลย
            md.append("| Brand | Product Name | Key Trends | Price (฿) | Sold | Why It Fits |")
            md.append("|---|---|---|---|---|---|")

            for p in products[:10]:
                brand = str(p.get('Brand', '-')).replace('|', '&#124;')
                name = str(p.get('Product Name', '-')).replace('|', '&#124;')
                trends = str(p.get('Key_Trends', '-')).replace('|', '&#124;')
                price = str(p.get('Sale Price (฿)', '-')).replace('|', '&#124;')
                sold = str(p.get('Sold', '-') or '-').replace('|', '&#124;')
                fit = str(p.get('Why It Fits', '-') or '-').replace('|', '&#124;')
                md.append(f"| {brand} | {name} | {trends} | {price} | {sold} | {fit} |")
            
            if len(products) > 10:
                md.append(f"\n*(Showing top 10 out of {len(products)} matched products for this pillar. See JSON export for full list.)*\n")
            md.append("\n")
    else:
        md.append("No specific product matches found in the database.\n")

    md.append("---\n")

    # --- 6. DEEP-DIVE RAW REPORT ---
    md.append("## 6. Appendix: Deep-Dive Raw Trend Analysis\n")
    if final_trend_report:
        md.append("<details><summary>Click to expand full raw analysis</summary>\n\n")
        md.append(final_trend_report)
        md.append("\n</details>\n")
    else:
        md.append("No raw trend report available.\n")

    return "\n".join(md)
