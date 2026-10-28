# -*- coding: utf-8 -*-
"""
Phase 3 — ⑪ จับคู่จุดเด่น: สกัด "จุดเด่นเชิงแนวคิด" ผ่าน LLM จริงครั้งแรก (2026-09-11)
ดู Detail/05 งานที่ยังไม่ได้ทำ/เกณฑ์สกัดจุดเด่นเทรนด์สำหรับจับคู่สินค้า.md (เกณฑ์ 6 มิติ + prompt
template เต็ม) และ Detail/05 งานที่ยังไม่ได้ทำ/Workflow v2 — แยกสายแล้วรวม.md ส่วน "⑪ จับคู่จุดเด่น"

จนถึงตอนนี้ `match_supply.py`'s TREND_PROFILES ทั้งหมดเป็นของที่ทำ **manual** (ไม่ผ่าน LLM จริงสักตัว)
สคริปต์นี้คือตัวที่เติมช่องว่างนั้น - ใช้ Typhoon (ไม่ต้องรอเครดิต OpenRouter เหมือนที่อื่นในโปรเจกต์นี้)
กับ **15 คลัสเตอร์จริง** จาก 3 สาย (Paper/Social/News) ที่รันจริงในรอบนี้ - ไม่ใช่ตัวอย่าง manual อีกแล้ว

ใช้ prompt template จากเอกสารเกณฑ์ตรงๆ (ไม่แก้คำ) - input ต่อคลัสเตอร์คือ Trend Name + Key Ingredients
+ Key Benefits + Target ที่มีอยู่แล้วในผลลัพธ์แต่ละสาย (ไม่ต้องยิง LLM อ่านบทความดิบซ้ำ)
"""
import json
import os
import sys
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import (OUTPUTS, GROWTH_LINE, LONG_YEAR, SHORT_YEAR, TOP_K_PER_HORIZON, tf, use_bedrock,  # noqa: E402
                              safe_json_parse, get_top_n_trends, load_ranked_trends, collect_detail_and_top_k,
                              refresh_source_dir)
from match_supply import build_trend_matchable_text  # noqa: E402  (ตัวตรวจเดียวกับที่ ⑫ ใช้ตอน embed)

# 🆕 (2026-09-16) ค่าที่ trend_type ตอบได้ (ต้องตรงกับพรอมต์ด้านล่างทุกตัวอักษร ไม่นับช่องว่าง) - นับเข้า Top N
# เฉพาะ "สินค้า" ดูเหตุผลใน Detail/05 งานที่ยังไม่ได้ทำ/เกณฑ์สกัดจุดเด่นเทรนด์สำหรับจับคู่สินค้า.md
TREND_TYPE_PRODUCT = "สินค้า"
TREND_TYPE_CHANNEL = "ช่องทาง/พฤติกรรมการซื้อ"
TREND_TYPES = (TREND_TYPE_PRODUCT, TREND_TYPE_CHANNEL)
# เหตุผลที่ไม่นับเข้า Top N (บันทึกใน excluded_trends / checked_trends) - 🆕 (2026-10-07) โหมดอัปเดตใช้จับคู่ผลตัดสินของรอบเดิม
REASON_CHANNEL = "เทรนด์ประเภทช่องทาง/พฤติกรรมการซื้อ - ไม่มีคุณสมบัติสินค้าให้จับคู่"
REASON_NO_TEXT = "ข้อมูลไม่พอทุกช่องที่ใช้จับคู่สินค้า"
NO_INFO = "ข้อมูลไม่พอ"
PROFILE_FIELDS = ("attribute", "functional_consequence", "psychosocial_consequence", "job_to_be_done",
                  "point_of_difference", "point_of_parity")

# 🆕 (2026-10-27) รายชื่อสายที่เดียว (common/streams.py) - รอบใหม่ = สาย Search (Google Trends), รอบเก่า = Paper/Social/News
from common.streams import SEARCH_STREAM, STREAM_FILES, present_streams  # noqa: E402
# 🆕 (2026-10-27) เทรนด์ของสาย Search: ⑪ อ่านคำค้นจริงและตรวจหลักฐานด้วยโค้ด - ดู highlight_evidence.py
import highlight_evidence as he  # noqa: E402

# คัดลอกมาจาก Detail/05 งานที่ยังไม่ได้ทำ/เกณฑ์สกัดจุดเด่นเทรนด์สำหรับจับคู่สินค้า.md ตรงๆ ไม่แก้คำ
SYSTEM_PROMPT = """คุณคือนักวิเคราะห์กลยุทธ์แบรนด์ (Brand Strategist) หน้าที่ของคุณคือแปลงข้อมูลดิบของเทรนด์
(ส่วนผสม/ประโยชน์/กลุ่มเป้าหมาย) ให้กลายเป็น "จุดเด่นเชิงแนวคิด" ที่ใช้จับคู่กับสินค้าจริงได้แม่นกว่า
การเทียบคำตรงตัว โดยใช้หลัก Means-End Chain (Gutman 1982), Jobs to Be Done (Christensen) และ
Points-of-Parity/Points-of-Difference (Keller)

วิเคราะห์ตาม 6 มิตินี้ ห้ามเดาเกินข้อมูลที่ให้มา ถ้าข้อมูลไม่พอสำหรับมิติไหนให้ระบุว่า "ข้อมูลไม่พอ":

1. attribute — คุณสมบัติ/ส่วนผสม/เทคโนโลยีที่สังเกตได้ตรงๆ จากข้อมูล
2. functional_consequence — คุณสมบัตินั้นแก้ปัญหา/ให้ผลลัพธ์อะไรจริงๆ ในการใช้งาน
3. psychosocial_consequence — ผลลัพธ์นั้นทำให้ผู้บริโภครู้สึก/ถูกมองยังไง
   (อนุมานได้จาก target audience ที่ให้มาเท่านั้น ห้ามเดาเกินข้อมูล)
4. job_to_be_done — ผู้บริโภค "จ้าง" สินค้านี้มาทำอะไร ในสถานการณ์/บริบทไหน
5. point_of_difference — สิ่งที่ต่างจากสินค้าทั่วไปในหมวดเดียวกันจริงๆ (ไม่ใช่สิ่งที่ทุกตัวมี)
6. point_of_parity — มาตรฐานพื้นฐานที่สินค้าในหมวดนี้ต้องมีอยู่แล้ว (ระบุแยกไว้ ไม่ใช่จุดเด่น)

กฎสำคัญ: มิติ 2, 3, 4, 5 คือสิ่งที่จะเอาไปใช้จับคู่กับสินค้าจริง ต้องเขียนให้เป็นแนวคิด/ประโยชน์
ไม่ใช่ชื่อส่วนผสม — เช่น เขียนว่า "ลดการระคายเคือง" ไม่ใช่ "มี ceramide"

ก่อนวิเคราะห์ 6 มิติ ให้ระบุประเภทเทรนด์ (trend_type) ก่อน ตอบได้แค่ 2 ค่านี้เท่านั้น:
- "สินค้า" — เทรนด์พูดถึงตัวสินค้า: คุณสมบัติ ส่วนผสม สูตร เทคโนโลยี ประโยชน์ ความปลอดภัย หรือปัญหา/ความต้องการ
  ที่สินค้าเข้าไปแก้ (รวมถึงเทรนด์ที่บอกแค่กลุ่มผู้ใช้กับปัญหาที่ต้องการแก้ เช่น ผิวบอบบางช่วงตั้งครรภ์)
- "ช่องทาง/พฤติกรรมการซื้อ" — เทรนด์พูดถึงวิธีขาย/วิธีซื้อ แพลตฟอร์ม การตลาด ราคา/โปรโมชัน หรือพฤติกรรม
  การช้อปปิ้ง โดยไม่ได้บอกว่าตัวสินค้าต้องมีคุณสมบัติหรือประโยชน์อะไร
ถ้าเป็น "ช่องทาง/พฤติกรรมการซื้อ" ให้ระบุมิติ 2, 3, 4, 5 ว่า "ข้อมูลไม่พอ" ทั้งหมด — ห้ามเขียนประโยชน์ของ
ช่องทางขายแทนประโยชน์ของสินค้า เพราะจะถูกเอาไปจับคู่กับสินค้าจริงผิดๆ

ตอบเป็น JSON เท่านั้น:
{
  "trend": "<ชื่อเทรนด์>",
  "trend_type": "สินค้า | ช่องทาง/พฤติกรรมการซื้อ",
  "attribute": "...",
  "functional_consequence": "...",
  "psychosocial_consequence": "...",
  "job_to_be_done": "...",
  "point_of_difference": "...",
  "point_of_parity": "..."
}"""


def load_all_clusters():
    """คลัสเตอร์ทั้งหมดจาก 3 สาย (สายละ 5 = 15) พร้อม stream tag - ยังไม่ได้คัด Top N (ดู __main__)
    🆕 (2026-10-28) สาย Search: ใส่คีย์เวิร์ดชนิดสินค้าของเทรนด์ ("Product Keywords" จากรายการ keywords ของ ①-⑤) ไว้ในคลัสเตอร์ด้วย - ใช้ทำ beauty_need"""
    clusters = []
    for stream, fp in present_streams(OUTPUTS).items():
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        products = {k.get("Trend Name"): k.get("Product_Search_Keywords") for k in data.get("keywords") or [] if isinstance(k, dict)} \
            if stream == SEARCH_STREAM else {}
        for row in data.get("trends", []):
            extra = {"Product Keywords": products[row.get("Trend Name")]} if products.get(row.get("Trend Name")) else {}
            clusters.append({"stream": stream, **row, **extra})
    return clusters


# ต้องตรงกับ OUTPUT_DIR ของ ⑦ (fetch_trends_worldwide_serpapi.py) และชื่อไฟล์ที่ trend_final_v2.forecast_trend() เขียน
FORECAST_DIR_NAME = "serpapi_forecast_run"
FORECAST_FILE = "step5c_df_cluster_forecast.xlsx"


def export_top_n_forecast(selected, forecast_dir):
    """🆕 (2026-09-16) สำเนาผลพยากรณ์ของ ⑦ เฉพาะเทรนด์ในชุด Top N ที่เพิ่งคัด -> step5c_df_cluster_forecast_top{N}.xlsx
    (เจ้าของงานขอไว้แนบรายงาน) คอลัมน์/ชื่อชีต/ลำดับแถวเหมือนต้นฉบับทุกอย่าง แค่กรองแถว - ต้นฉบับที่มีครบทุก
    คลัสเตอร์ไม่ถูกแตะ (notebook ใช้คำนวณอันดับจริงเทียบทุกคลัสเตอร์)

    ชื่อไฟล์ตามจำนวนที่คัดได้จริง (ปกติ = N ที่ตั้ง, ถ้าเทรนด์ที่จับคู่สินค้าได้มีไม่ถึง N ชื่อจะบอกจำนวนจริง) - สำเนา
    _top* ตัวอื่นในโฟลเดอร์เดียวกัน (จากการรัน ⑪ รอบก่อนด้วย N อื่น) ถูกลบหลังเขียนไฟล์ใหม่สำเร็จ เพราะไม่ตรงกับ
    ชุดปัจจุบันแล้ว ปล่อยไว้จะหยิบผิดไปแนบรายงานได้

    คืน path ที่เขียน หรือ None ถ้าไม่มีไฟล์ต้นฉบับ (ไม่ทำให้ ⑪ ล้ม - งานหลักของขั้นนี้คือจุดเด่นเทรนด์)"""
    import pandas as pd

    forecast_dir = Path(forecast_dir)
    src = forecast_dir / FORECAST_FILE
    if not src.exists():
        print(f"  ⚠️ ไม่พบ {src} - ข้ามการทำสำเนาผลพยากรณ์ Top N")
        return None
    names = [s["trend"] for s in selected]
    dst = forecast_dir / f"step5c_df_cluster_forecast_top{len(names)}.xlsx"
    with pd.ExcelFile(src) as xl:
        sheet = xl.sheet_names[0]
        df = xl.parse(sheet)
    top = df[df["cluster_name"].isin(names)]
    missing = sorted(set(names) - set(top["cluster_name"]))
    if missing:
        print(f"  ⚠️ ไม่พบในผลพยากรณ์ของ ⑦: {missing} - ⑦ กับ ⑪ มาจากคนละรอบหรือเปล่า")
    top.to_excel(dst, sheet_name=sheet, index=False)
    for old in forecast_dir.glob("step5c_df_cluster_forecast_top*.xlsx"):
        if old.name != dst.name:
            old.unlink()
            print(f"  🗑️ ลบสำเนา Top N เก่าที่ไม่ตรงชุดปัจจุบัน: {old.name}")
    print(f"  💾 สำเนาผลพยากรณ์เฉพาะ Top {len(names)}: {dst.name} "
          f"({top['cluster_name'].nunique()} คลัสเตอร์, {len(top):,} แถว)")
    return dst


HIGHLIGHTS_FILE = "phase3_trend_highlights_result.json"


def load_reusable_profiles(source_dir, include_stubs=True):
    """🆕 (2026-10-07) โหมดอัปเดตรอบเดิม: ผลตัดสินที่ ⑪ ของรอบต้นทางทำไว้แล้ว -> {(stream, trend): profile}
    ข้อมูลเทรนด์เป็นสำเนาของรอบต้นทางทุกตัวอักษร จึงใช้ซ้ำแทนเรียก LLM ใหม่ (⑫ ได้สินค้าชุดเดิม รายงานต่างแค่ส่วนที่มาจาก
    Google Trends และ LLM ตอบต่างไม่ทำให้เทรนด์หลุด/เข้า Top N เอง):
      - จับคู่ได้ = profile เดิม (profiles + extra_profiles)
      - จับคู่ไม่ได้ (รอบต้นทางไม่ได้เก็บ profile) = profile แทนที่ให้ exclusion_reason ได้เหตุผลเดิม: ประเภทช่องทาง หรือ
        "ข้อมูลไม่พอ" ทุกช่อง - เหตุผลอื่นที่ไม่รู้จัก ไม่ใช้ซ้ำ (เรียก LLM)
    เทรนด์ที่รอบต้นทางไม่เคยตรวจยังเรียก LLM ตามปกติ / source_dir None หรือไม่มีไฟล์ = {}"""
    path = source_dir / HIGHLIGHTS_FILE if source_dir else None
    if not path or not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    reusable = {(p.get("stream"), p["trend"]): p
                for p in (data.get("profiles") or []) + (data.get("extra_profiles") or [])}
    stub_type = {REASON_CHANNEL: TREND_TYPE_CHANNEL, REASON_NO_TEXT: TREND_TYPE_PRODUCT}
    for e in ((data.get("checked_trends") or []) + (data.get("excluded_trends") or [])) if include_stubs else []:
        key = (e.get("stream"), e.get("trend"))
        if key not in reusable and not e.get("matchable") and e.get("reason") in stub_type:
            reusable[key] = {"trend": e["trend"], "stream": e["stream"], "trend_type": stub_type[e["reason"]],
                             **{field: NO_INFO for field in PROFILE_FIELDS}}
    return reusable


def extract_highlight_search(cluster):
    """🆕 (2026-10-27) เทรนด์ของสาย Search: LLM อ่านคำค้นจริง (ชุดหลักฐาน) เขียนทีละมิติพร้อมข้อความที่คัดลอก - โค้ดตรวจ (highlight_evidence.gate_profile)
    ถามซ้ำได้ 3 ครั้งถ้าคำตอบ parse ไม่ได้ (ไม่ใช่การตัดสินว่าข้อมูลไม่พอ) - ล้มทุกครั้ง = ValueError (⑪ รายงานเป็น failed ไม่ปล่อยผ่านเงียบๆ)"""
    user_content = he.build_user_content(cluster)
    for _attempt in range(3):
        with use_bedrock():
            response = tf.client.chat.completions.create(
                model=tf.MODEL_NAME_META,
                messages=[{"role": "system", "content": he.SYSTEM_PROMPT_SEARCH}, {"role": "user", "content": user_content}],
                temperature=0, max_tokens=1600, response_format={"type": "json_object"},
            )
        parsed = safe_json_parse(response.choices[0].message.content)
        if he.parse_usable(parsed):
            profile = he.gate_profile(parsed, user_content)
            if profile["_audit"]:
                print(f"   🔎 เกตตัดมิติ: " + ", ".join(f"{k} ({v})" for k, v in profile["_audit"].items()))
            return profile
        print("   ⚠️ คำตอบ LLM ใช้ไม่ได้ - ถามใหม่")
    raise ValueError("คำตอบของ LLM ใช้ไม่ได้ครบ 3 ครั้ง")


def extract_highlight(cluster):
    """ยิง Typhoon 1 ครั้งต่อคลัสเตอร์ - เหมือน pattern เดิมทุกจุดในโปรเจกต์นี้ (json_object)"""
    if cluster.get("stream") == SEARCH_STREAM:
        return extract_highlight_search(cluster)
    user_content = (
        f"เทรนด์: {cluster.get('Trend Name', '')}\n"
        f"ส่วนผสม/คุณสมบัติหลัก: {cluster.get('Key Ingredients', '')}\n"
        f"ประโยชน์หลัก: {cluster.get('Key Benefits', '')}\n"
        f"กลุ่มเป้าหมาย: {cluster.get('Target', '')}\n"
        f"บริบทเพิ่มเติม: {str(cluster.get('Outlook', ''))[:300]}"
    )
    with use_bedrock():  # 🆕 (2026-09-15) เปลี่ยนจาก Typhoon -> AWS Bedrock
        response = tf.client.chat.completions.create(
            model=tf.MODEL_NAME_META,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0, max_tokens=900,
            response_format={"type": "json_object"},
        )
    parsed = safe_json_parse(response.choices[0].message.content)
    return parsed


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 3 ⑪ — สกัดจุดเด่นเทรนด์ผ่าน LLM (AWS Bedrock) - เทรนด์เหนือค่ากลางตลาดตาม Rank Score ของ ⑥ "
          "ที่มีข้อมูลให้จับคู่สินค้า")
    print("=" * 70)

    all_clusters = load_all_clusters()
    print(f"โหลด {len(all_clusters)} คลัสเตอร์จาก 3 สาย")
    if not all_clusters:
        print("❌ ไม่มีคลัสเตอร์เลย - ต้องรัน 3 สายก่อน")
        sys.exit(1)

    # 🆕 (2026-09-16) เดินตามอันดับ Rank Score ของ ⑥ ทีละเทรนด์ จนได้ N ตัวที่มีข้อมูลให้จับคู่สินค้า - ตัวที่ ⑪
    # ระบุว่า "ข้อมูลไม่พอ" ครบทุกช่องที่ใช้จับคู่ (เช่น เทรนด์เชิงช่องทางขาย) ไม่นับเข้า Top N แล้วเลื่อนอันดับ
    # ถัดไปขึ้นมาแทน (เจ้าของงานเลือก) - ⑫ ⑬ รายงาน และ trend.ipynb อ่านชุดที่บันทึกในไฟล์นี้ต่อ จึงได้ชุดเดียวกัน
    top_n = get_top_n_trends()
    ranked = load_ranked_trends()
    cluster_by_key = {(c["stream"], c.get("Trend Name")): c for c in all_clusters}
    not_found = [f"[{r['stream']}] {r['trend']}" for r in ranked if (r["stream"], r["trend"]) not in cluster_by_key]
    if not_found:
        # ⑥ กับไฟล์สายมาจากคนละรอบ (ชื่อเทรนด์ไม่ตรงกัน) - หยุดดีกว่าได้จุดเด่นไม่ครบโดยไม่รู้ตัว
        print(f"❌ หาเทรนด์จากผล ⑥ ไม่เจอในไฟล์สาย: {not_found} - ⑥ กับ ①-⑤ มาจากคนละรอบหรือเปล่า")
        sys.exit(1)
    # 🆕 (2026-09-30) หน้ารายละเอียดเฉพาะเทรนด์ที่คะแนนการเติบโตปีที่ 1 ถึงค่ากลางตลาด + ตัดสินเพิ่มเฉพาะเทรนด์ที่ต้องใช้
    # ในหน้า Top 5 ระยะสั้น/ระยะยาว (ดู bootstrap.collect_detail_and_top_k)
    print(f"ไล่ตามอันดับ Rank Score (⑥) เฉพาะเทรนด์ที่คะแนนปีที่ {SHORT_YEAR} ถึง {GROWTH_LINE} จนได้ {top_n} เทรนด์ที่มีข้อมูลให้"
          f"จับคู่สินค้า แล้วตัดสินเพิ่มจนรู้ Top {TOP_K_PER_HORIZON} ที่จับคู่ได้ของปีที่ {SHORT_YEAR} และปีที่ {LONG_YEAR}")
    # 🆕 (2026-10-07) โหมดอัปเดตรอบเดิม - ใช้จุดเด่นของรอบต้นทางซ้ำ (ดู load_reusable_profiles)
    source_dir = refresh_source_dir()
    # 🆕 (2026-10-28) TREND_REUSE_PROFILES=1: ใช้โปรไฟล์ที่ ⑪ เขียนไว้แล้วในรอบนี้ซ้ำ (ไม่เรียก LLM ใหม่ - LLM ตอบต่างทุกครั้ง) เฉพาะที่มีข้อมูลจริง ส่วนตัวที่เคยถูกตัด
    # (โปรไฟล์ว่าง) เรียก LLM ใหม่ - ใช้ตอนเปลี่ยนฐานจับคู่เป็นความต้องการที่ AI อนุมาน (match_supply.match_basis) แล้วต้องเลือก Top N ใหม่
    own_reuse = os.environ.get("TREND_REUSE_PROFILES") == "1" and not source_dir
    reusable = load_reusable_profiles(source_dir) if source_dir else (load_reusable_profiles(OUTPUTS, include_stubs=False) if own_reuse else {})
    reuse_name = source_dir.name if source_dir else ("รอบนี้" if own_reuse else None)
    n_reused = 0
    if source_dir:
        print(f"โหมดอัปเดตรอบเดิม: ใช้ผล ⑪ เดิมของรอบ {source_dir.name} ได้ {len(reusable)} เทรนด์ (จุดเด่น + ผลตัดสินว่าจับคู่ได้ไหม - ตัวอื่นเรียก LLM ตามปกติ)")
    elif own_reuse:
        print(f"TREND_REUSE_PROFILES=1: ใช้โปรไฟล์ ⑪ ที่มีข้อมูลของรอบนี้ซ้ำ {len(reusable)} เทรนด์ (ไม่เรียก LLM) - ตัวอื่นเรียก LLM ตามปกติ")

    def make_profile(item):
        global n_reused
        cluster = cluster_by_key[(item["stream"], item["trend"])]
        print()
        print(f"[อันดับ {item['overall_rank']}] {item['stream']} — {item['trend']}  "
              f"(Rank Score={item['rank_score']}, ปีที่ {SHORT_YEAR}={item.get('growth_short')}, "
              f"ปีที่ {LONG_YEAR}={item.get('growth_long')})")
        reused = reusable.get((item["stream"], item["trend"]))
        if reused:
            n_reused += 1
            print(f"   ↺ ใช้ผล ⑪ เดิมจาก{'รอบ ' if source_dir else ''}{reuse_name} (ไม่เรียก LLM)")
            profile = {**reused, "stream": item["stream"], "trend": item["trend"]}
            need = he.beauty_need(cluster) if item["stream"] == SEARCH_STREAM else None
            if need:
                profile["beauty_need"] = need
            return profile
        try:
            profile = extract_highlight(cluster)
            if not profile or not profile.get("functional_consequence"):
                raise ValueError(f"parse ไม่ได้ หรือไม่มี functional_consequence: {profile!r}")
            trend_type = str(profile.get("trend_type") or "").replace(" ", "")
            if trend_type not in TREND_TYPES:
                raise ValueError(f"trend_type ไม่ใช่ค่าที่กำหนด ({' / '.join(TREND_TYPES)}): "
                                 f"{profile.get('trend_type')!r}")
            profile["trend_type"] = trend_type
        except Exception as e:
            print(f"   ❌ ล้มเหลว: {e}")
            raise
        profile["stream"] = item["stream"]
        # ใช้ชื่อเทรนด์จริงเสมอ (ไม่ใช้ชื่อที่ LLM คัดลอกกลับมา) - ⑫ และรายงานจับคู่ข้ามไฟล์ด้วยชื่อนี้
        profile["trend"] = item["trend"]
        need = he.beauty_need(cluster) if item["stream"] == SEARCH_STREAM else None
        if need:   # 🆕 (2026-10-28) ความต้องการความงามที่ AI อนุมานจาก ①-⑤ - ⑫ ใช้เป็นข้อความหลักจับคู่สินค้า (match_supply.match_basis) รายงานติดป้ายว่าอนุมาน
            profile["beauty_need"] = need
        print(f"   ประเภท: {profile['trend_type']}")
        print(f"   functional: {profile.get('functional_consequence', '')[:80]}")
        print(f"   job_to_be_done: {profile.get('job_to_be_done', '')[:80]}")
        return profile

    def exclusion_reason(profile):
        if profile["trend_type"] == TREND_TYPE_CHANNEL:
            reason = REASON_CHANNEL
        elif not build_trend_matchable_text(profile).strip():
            reason = REASON_NO_TEXT
        else:
            reason = None
        print("   ✅ จับคู่สินค้าได้" if reason is None else f"   ⏭️ จับคู่สินค้าไม่ได้: {reason}")
        return reason

    picked = collect_detail_and_top_k(ranked, make_profile, exclusion_reason, top_n)
    selected, profiles, excluded, failed = picked["selected"], picked["profiles"], picked["excluded"], picked["failed"]

    print()
    print("=" * 70)
    print(f"สรุป: หน้ารายละเอียด {len(selected)}/{top_n} เทรนด์ - อันดับที่ใช้แสดงผลเป็น 1-{len(selected)} "
          f"(อันดับเดิมจาก ⑥: {', '.join(str(s['overall_rank']) for s in selected)})")
    if source_dir:
        print(f"   ใช้ผล ⑪ เดิมจากรอบ {source_dir.name}: {n_reused} เทรนด์ (ไม่เรียก LLM)")
    if picked["extra_profiles"]:
        print(f"   จับคู่ได้แต่อยู่ใต้เส้น (ใช้ในหน้า Top 5 เท่านั้น) {len(picked['extra_profiles'])}: "
              + ", ".join(p["trend"] for p in picked["extra_profiles"]))
    if excluded:
        print(f"   จับคู่สินค้าไม่ได้ {len(excluded)}: "
              + ", ".join(f"#{x['overall_rank']} {x['trend']}" for x in excluded))
    if failed:
        print(f"   ❌ ล้มเหลวทางเทคนิค {len(failed)}: " + ", ".join(f"#{x['overall_rank']} {x['trend']}" for x in failed))
    if len(selected) < top_n and not failed:
        print(f"   ℹ️ เทรนด์เหนือเส้นที่จับคู่สินค้าได้มี {len(selected)} ตัว (ไม่ถึง {top_n}) - ใช้เท่าที่มี")

    out_path = OUTPUTS / HIGHLIGHTS_FILE
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "_note": "⑪ จุดเด่นเทรนด์ผ่าน LLM - แทนที่ match_supply.py's TREND_PROFILES ที่เคยทำ manual ทั้งหมด",
            "profiles": profiles, "failed": [x["trend"] for x in failed],
            # 🆕 (2026-09-16) ชุด Top N (Rank Score ของ ⑥ + มีข้อมูลให้จับคู่) - รายงานและ notebook อ่านตรงนี้
            # 🆕 (2026-09-30) Top N = เฉพาะเทรนด์เหนือค่ากลางตลาด (growth_line) ไม่เกิน N ตัว
            "top_n": len(selected), "requested_top_n": top_n, "n_trends_total": len(all_clusters),
            "growth_line": GROWTH_LINE,
            "selected_trends": selected, "excluded_trends": excluded,
            "failed_trends": failed,
            # 🆕 (2026-09-30) ผลตัดสินทุกเทรนด์ที่ตรวจแล้ว (รวมตัวที่ตรวจเพิ่มเพื่อหน้า Top 5) - รายงาน ⑯ ใช้เลือก Top 5
            # ระยะสั้น/ระยะยาวจากทุกเทรนด์ที่จับคู่ได้ / extra_profiles ไม่ส่งต่อให้ ⑫ ⑬ (อ่านแค่ profiles)
            "checked_trends": picked["checked"], "extra_profiles": picked["extra_profiles"],
            # 🆕 (2026-10-07) โหมดอัปเดตรอบเดิม: รอบต้นทาง + จำนวนเทรนด์ที่ใช้ผลเดิม (รวมตัวที่จับคู่ไม่ได้) (None = รันปกติ)
            "reused_from": source_dir.name if source_dir else None, "n_reused_profiles": n_reused,
            "reused_own_profiles": own_reuse,
        }, f, ensure_ascii=False, indent=2)
    print(f"✅ Saved -> {out_path}")

    # 🆕 (2026-09-16) สำเนา step5c เฉพาะ Top N ไว้แนบรายงาน - ทำเฉพาะตอนไม่มีตัวล้มเหลว (ถ้ามี ชุดนี้ยังไม่ควรใช้)
    if not failed:
        export_top_n_forecast(selected, OUTPUTS / FORECAST_DIR_NAME)

    if failed:
        # ถ้าปล่อยผ่าน ชุด Top N จะเปลี่ยนเพราะ error ชั่วคราว ไม่ใช่เพราะข้อมูล - หยุดให้รันขั้นนี้ใหม่
        print("❌ มีเทรนด์ที่เรียก LLM ไม่สำเร็จ - รัน ⑪ ใหม่อีกครั้ง (ชุด Top N ที่บันทึกไว้รอบนี้ยังไม่ควรใช้)")
        sys.exit(1)
