# -*- coding: utf-8 -*-
"""
Phase 2 — ดึง Google Trends จริง (worldwide) ให้ Paper + Social ผ่าน SerpAPI โดยตรง

เปลี่ยนจาก trendspyg (fetch_trends_worldwide.py) มาที่นี่เพราะ trendspyg โดน Google บล็อก IP จริง
หลังผ่านไปแค่ 6/94 คำ (2026-09-09) - SerpAPI ใช้ proxy/infra ของตัวเอง ไม่ยิงตรงจาก IP เครื่องเรา
จึงไม่เจอปัญหาเดียวกัน

**เช็ค quota จริงแล้วก่อนรัน** (ผ่าน serpapi.com/account.json - ฟรี ไม่เสีย search):
Free Plan 250/เดือน, ใช้ไปแล้ว 152, เหลือ 98 - งานนี้ต้องการ 94 search พอดีๆ (buffer แค่ 4)

**ไม่ใช้ monthly_df_override** - เรียก forecast_trend() ตรงๆ ให้ใช้ serp_api() ภายในตัวเอง (โค้ดเดิมที่
ทดสอบผ่านแล้วจริง) แทนที่จะเขียน date-parsing logic ซ้ำเอง (parse_date_range ซับซ้อน เสี่ยง bug)

⚠️ **user_query ห้ามมีคำว่า "thailand"/"thai"/"ไทย" เด็ดขาด** - _infer_geo_from_query() จะเห็นคำพวกนี้
แล้วสลับไป geo="TH" ทันที (บล็อกเนื้อหาสากล ตรงข้ามกับที่ต้องการ) ใช้คำว่า "Global"/"Worldwide" แทน
"""
import json
import sys
import urllib.request
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import OUTPUTS, PROJECT_ROOT, prompt_run_config, use_bedrock

# 🆕 (2026-09-22) ส่วนที่ใช้จริงของ trend_final_v2.py คัดลอกตรงตัวไว้ใน main/ (common/trend_final_v2_subset.py)
from common import trend_final_v2_subset as tf2  # noqa: E402

OUTPUT_DIR = str(OUTPUTS / "serpapi_forecast_run")
# default - ผู้ใช้พิมพ์เองตอนรัน (prompt_run_config) - 🔒 คำ thailand/thai/ไทย จะถูกตัดออก + เติม
# "Global" นำหน้าอัตโนมัติ ก่อนส่งเข้า forecast_trend (กัน _infer_geo_from_query สลับไป geo=TH)
USER_QUERY = "Global Beauty and Personal Care Trends"


def _force_worldwide_query(raw_topic):
    """ตัดคำที่ทริกเกอร์ geo=TH (thailand/thai/ไทย) + เติม 'Global' นำหน้า - forecast รอบนี้ต้องการ
    Google Trends worldwide เสมอ (คีย์เวิร์ดจริงมาจากคลัสเตอร์ Paper+Social อยู่แล้ว ไม่ใช่จาก query นี้)"""
    import re as _re
    cleaned = _re.sub(r"\b(thailand|thai)\b", "", raw_topic, flags=_re.IGNORECASE)
    cleaned = cleaned.replace("ไทย", "")
    cleaned = _re.sub(r"\s{2,}", " ", cleaned).strip(" -,")
    # ตัด preposition ที่ค้างท้าย/หน้าหลังลบชื่อประเทศ (เช่น "clean beauty in" -> "clean beauty")
    cleaned = _re.sub(r"\s+\b(in|for|of|the|a|an)\s*$", "", cleaned, flags=_re.IGNORECASE).strip()
    cleaned = _re.sub(r"^(in|for|of)\b\s+", "", cleaned, flags=_re.IGNORECASE).strip()
    if not cleaned:
        cleaned = "Beauty and Personal Care Trends"
    if not cleaned.lower().startswith(("global", "worldwide")):
        cleaned = f"Global {cleaned}"
    return cleaned


def build_trend_keyword_mapping():
    mapping = {}
    for fname in ["phase1_paper_stream_result.json", "phase2_social_stream_result.json", "phase2_news_stream_result.json"]:
        with open(OUTPUTS / fname, encoding="utf-8") as f:
            data = json.load(f)
        for row in data["keywords"]:
            trend_name = row["Trend Name"]
            kws = [k.strip().lower() for k in str(row.get("Search_Keywords", "")).split(",") if k.strip()]
            if kws:
                mapping[trend_name] = kws
    return mapping


def check_quota():
    key = tf2.SERPAPI_KEY
    url = f"https://serpapi.com/account.json?api_key={key}"
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.load(r)
    left = data.get("plan_searches_left", data.get("total_searches_left"))
    print(f"  SerpAPI quota เหลือ: {left} search (แผน {data.get('plan_name')})")
    return left


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 2 — Google Trends จริง (worldwide) ให้ Paper + Social ผ่าน SerpAPI")
    print("=" * 70)

    _topic, horizon_months = prompt_run_config(default_topic=USER_QUERY, default_years=3,
                                                ask_years=True)
    user_query = _force_worldwide_query(_topic)
    if user_query != _topic:
        print(f"  🔒 ปรับ query เป็น worldwide: '{_topic}' -> '{user_query}'")
    assert "thailand" not in user_query.lower() and "thai" not in user_query.lower() \
        and "ไทย" not in user_query, "query ยังมีคำที่ทริกเกอร์ geo=TH - ห้ามรัน!"

    trend_keyword_mapping = build_trend_keyword_mapping()
    all_keywords = sorted(set(k for kws in trend_keyword_mapping.values() for k in kws))
    print(f"รวม {len(trend_keyword_mapping)} คลัสเตอร์จริง, {len(all_keywords)} คีย์เวิร์ดไม่ซ้ำ")

    quota_before = check_quota()
    if quota_before is not None and quota_before < len(all_keywords):
        print(f"❌ quota ไม่พอ ({quota_before} < {len(all_keywords)}) - หยุดก่อนเสียเงิน/โควตาฟรี")
        sys.exit(1)

    print(f"\nกำลังรัน forecast_trend() เต็มรูปแบบ (SerpAPI worldwide -> feature engineering -> "
          f"4 โมเดล -> ตัวกันโมเดลระเบิด -> E4 data quality)...")
    print(f"user_query = '{user_query}' (ไม่มีคำ Thailand -> geo จะเป็น worldwide) | "
          f"horizon = {horizon_months} เดือน ({horizon_months // 12} ปี)")

    # 🆕 (2026-09-16) forecast_trend() อยู่ใน trend_final_v2 ซึ่งมี client ของตัวเอง - use_bedrock() แบบปกติแพตช์แค่
    # trend_final (v1) ขั้นอธิบายผลพยากรณ์ (Step 6-7) ข้างในจึงยังยิง OpenRouter ที่เครดิตหมด (402 ทุกรอบ)
    with use_bedrock(module=tf2):
        cluster_names, df_results, master_report, llm_analysis = tf2.forecast_trend(
            OUTPUT_DIR, trend_keyword_mapping, user_query, horizon=horizon_months,
        )

    quota_after = check_quota()
    if quota_before is not None and quota_after is not None:
        print(f"ใช้ quota ไปจริง: {quota_before - quota_after} search")

    OUTPUTS.mkdir(exist_ok=True)
    result_path = OUTPUTS / "phase2_paper_social_z_delta_result.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump({
            "_note": "Z_Delta จริงตัวแรกของโปรเจกต์ v2 (worldwide, ผ่าน SerpAPI) - ดู Backlog",
            "master_report": master_report,
            # 🆕 (2026-09-16) เดิมไม่ได้เซฟ - ⑭-⑮ ใช้ใส่หัวข้อพยากรณ์ใน Master Report (None ถ้าขั้นนี้ล้มเหลว)
            "llm_forecast_analysis": llm_analysis,
        }, f, ensure_ascii=False, indent=2, default=str)

    print("\n" + "=" * 70)
    print("ผลลัพธ์ (เรียงตาม Z_Delta มากไปน้อย):")
    print("=" * 70)
    cols = ["cluster_id", "Cluster", "Model", "Status", "Current_Z", "Forecast_Avg_Z", "Z_Delta",
            "Peak_Month", "Keywords", "Context", "Data_Quality", "Pct_Months_With_Data"]
    for row in master_report:
        d = dict(zip(cols, row))
        print(f"\n🎯 {d['Cluster']} (id={d['cluster_id']})")
        print(f"   Status={d['Status']} | Z_Delta={d['Z_Delta']} | Model={d['Model']}")
        print(f"   Data_Quality={d['Data_Quality']} ({d['Pct_Months_With_Data']}% เดือนมีข้อมูลจริง)")

    print(f"\nบันทึกผลเต็มลง {result_path}")
