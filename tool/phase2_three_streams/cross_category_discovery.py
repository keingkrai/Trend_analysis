# -*- coding: utf-8 -*-
"""
Phase 2 — ⑩ รอบค้นพบเพิ่ม (ทางเลือก, เปิด/ปิดได้) (2026-09-11)
ดู Detail/05 งานที่ยังไม่ได้ทำ/Workflow v2 — แยกสายแล้วรวม.md ส่วน "⑩ 🔦 รอบค้นพบเพิ่ม"

แนวคิด: LLM อ่านผล 3 สายพร้อมกัน มองหา "เทรนด์ข้ามหมวด" ที่ไม่มีสายไหนเห็นชัดเดี่ยวๆ (เช่น ข่าวพูดเรื่อง
regulation, Social พูดเรื่องอาการผิว, Paper พูดเรื่องกลไก - 3 อย่างอาจเป็นเรื่องเดียวกันที่ไม่มีใครเห็น
ครบ) แล้วเสนอคีย์เวิร์ดใหม่ (ต้องไม่ซ้ำกับ 124 คำที่ยิง SerpAPI ไปแล้วในขั้น ⑦) → ยิง Google Trends
เฉพาะคำใหม่ (ผ่าน forecast_trend() เดิม ไม่เขียน fetch ใหม่) → ผลจริงเป็นตัวตัดสินว่า LLM มองเห็นของจริง
หรือมองเห็นแพตเทิร์นที่ไม่มีอยู่จริง (ดู docstring ของเอกสารต้นทาง)

**กฎสำคัญที่ยึดตามเอกสาร:** ให้ LLM ทำแค่ "สังเคราะห์ความหมาย + เสนอคีย์เวิร์ด" (งานที่พิสูจน์แล้วว่า
LLM ทำได้ดีในไปป์ไลน์นี้ - เหมือน summarize_trend_clusters/extract_strategic_keywords) **ห้ามให้ LLM
ตัดสินว่าเทรนด์แรงแค่ไหน** - ปล่อยให้ Google Trends จริง + forecast_trend() (Z_Delta กฎตายตัว) ตอบแทน
"""
import json
import sys
import urllib.request
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import OUTPUTS, PROJECT_ROOT, tf, use_bedrock, safe_json_parse, prompt_run_config  # noqa: E402

# 🆕 (2026-09-22) ส่วนที่ใช้จริงของ trend_final_v2.py คัดลอกตรงตัวไว้ใน main/ (common/trend_final_v2_subset.py)
from common import trend_final_v2_subset as tf2  # noqa: E402

from fetch_trends_worldwide_serpapi import (  # noqa: E402
    build_trend_keyword_mapping, check_quota, _force_worldwide_query,
)

OUTPUT_DIR = str(OUTPUTS / "serpapi_discovery_run")
STREAM_FILES = {
    "Paper": "phase1_paper_stream_result.json",
    "Social": "phase2_social_stream_result.json",
    "News": "phase2_news_stream_result.json",
}

SYSTEM_PROMPT = """You are a cross-category trend analyst for beauty & personal care. You will see up
to 15 trend clusters, each already discovered independently within ONE of three data streams:
Paper (scientific literature), Social (Pantip/Reddit/YouTube consumer chatter), News (trade press).

Your job: find CROSS-CATEGORY themes that NO SINGLE stream shows clearly on its own, but that emerge
when you connect signals ACROSS at least 2 different streams. Example of the pattern to look for:
News names a regulation/ingredient controversy + Social names a skin symptom + Paper names a
mechanism - these 3 fragments may describe ONE underlying theme none of the 3 clusters state alone.

STRICT RULES:
- A theme MUST cite evidence from at least 2 different streams by name (Paper/Social/News) with a
  short quote/reference to which cluster it comes from. If you cannot find 2+ streams supporting it,
  do not propose it.
- Do NOT invent facts not present in the clusters shown to you.
- Do NOT rate/score how strong or promising a theme is - your only job is to name it and give
  candidate search keywords. A separate deterministic step (real Google Trends data) will judge
  strength, not you.
- Give 2-4 short (1-4 word) candidate search keywords per theme - phrases someone would actually type
  into Google, not sentences.
- Propose at most 3 themes. If you truly see nothing solid, return an empty list - do not force it.

Return ONLY JSON: {"themes": [{"name": "...", "streams_combined": ["Paper","News"],
"rationale": "...", "keywords": ["...", "..."]}]}"""


def load_cluster_summaries():
    """15 คลัสเตอร์ (5 x 3 สาย) แบบย่อ - Trend Name/Ingredients/Benefits/Target/Outlook ต่อคลัสเตอร์"""
    lines = []
    for stream, fname in STREAM_FILES.items():
        fp = OUTPUTS / fname
        if not fp.exists():
            continue
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        for row in data.get("trends", []):
            lines.append(
                f"[{stream}] \"{row.get('Trend Name', '')}\" - ingredients: "
                f"{row.get('Key Ingredients', '')} | benefits: {row.get('Key Benefits', '')} | "
                f"target: {row.get('Target', '')} | outlook: {str(row.get('Outlook', ''))[:200]}"
            )
    return "\n".join(lines)


def propose_cross_category_themes(cluster_text):
    """ยิง Typhoon 1 ครั้ง (json_object) ให้เสนอธีมข้ามหมวด - เหมือน pattern เดิมทุกจุดในโปรเจกต์นี้"""
    with use_bedrock():  # 🆕 (2026-09-15) เปลี่ยนจาก Typhoon -> AWS Bedrock
        response = tf.client.chat.completions.create(
            model=tf.MODEL_NAME_META,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": cluster_text},
            ],
            temperature=0.2, max_tokens=1200,
            response_format={"type": "json_object"},
        )
    parsed = safe_json_parse(response.choices[0].message.content)
    return (parsed or {}).get("themes", [])


def filter_new_keywords(themes, existing_keywords_lower):
    """ตัดคีย์เวิร์ดที่ซ้ำกับ 124 คำที่ยิง SerpAPI ไปแล้วในขั้น ⑦ ออก (case-insensitive) - ธีมที่เหลือ
    คีย์เวิร์ดใหม่ 0 ตัว (ซ้ำหมด) จะถูกข้ามทั้งธีม เพราะไม่มีอะไรให้ตรวจสอบเพิ่ม"""
    kept = []
    for th in themes:
        name = str(th.get("name", "")).strip()
        streams = th.get("streams_combined") or []
        kws = [str(k).strip().lower() for k in (th.get("keywords") or []) if str(k).strip()]
        new_kws = [k for k in dict.fromkeys(kws) if k not in existing_keywords_lower]
        if not name or len(streams) < 2 or not new_kws:
            print(f"  ⏭️  ข้ามธีม {name!r} - streams={streams}, คีย์เวิร์ดใหม่={len(new_kws)} (ไม่ผ่านเกณฑ์)")
            continue
        kept.append({"name": name, "streams_combined": streams,
                     "rationale": th.get("rationale", ""), "keywords": new_kws})
    return kept


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 2 ⑩ — รอบค้นพบเพิ่ม (LLM สังเคราะห์ข้ามหมวด -> ตรวจด้วย Google Trends จริง)")
    print("=" * 70)

    cluster_text = load_cluster_summaries()
    n_clusters = cluster_text.count("[Paper]") + cluster_text.count("[Social]") + cluster_text.count("[News]")
    if n_clusters == 0:
        print("❌ ไม่มีผลลัพธ์ของสายไหนเลย - ต้องรัน 3 สายก่อน")
        sys.exit(1)
    print(f"โหลด {n_clusters} คลัสเตอร์จาก 3 สาย")

    existing_mapping = build_trend_keyword_mapping()
    existing_keywords_lower = {k.lower() for kws in existing_mapping.values() for k in kws}
    print(f"คีย์เวิร์ดที่ยิง SerpAPI ไปแล้วในขั้น ⑦: {len(existing_keywords_lower)} คำ (จะไม่นับซ้ำ)")

    print("\n🧠 ให้ Typhoon เสนอธีมข้ามหมวด...")
    raw_themes = propose_cross_category_themes(cluster_text)
    print(f"   LLM เสนอมา {len(raw_themes)} ธีม (ก่อนกรอง)")

    themes = filter_new_keywords(raw_themes, existing_keywords_lower)
    if not themes:
        print("\n(ไม่มีธีมไหนผ่านเกณฑ์ - LLM ไม่เห็นอะไรที่มีหลักฐาน 2+ สายรองรับ หรือคีย์เวิร์ดซ้ำของเดิมหมด)")
        print("นี่คือผลลัพธ์ที่ถูกต้องได้เหมือนกัน - ไม่ใช่ทุกรอบต้องเจอธีมใหม่")
        sys.exit(0)

    print(f"\n✅ {len(themes)} ธีมผ่านเกณฑ์ (มีหลักฐาน 2+ สาย + คีย์เวิร์ดใหม่จริง):")
    all_new_keywords = []
    theme_mapping = {}
    for th in themes:
        print(f"  🔦 {th['name']}  [{', '.join(th['streams_combined'])}]")
        print(f"     เหตุผล: {th['rationale']}")
        print(f"     คีย์เวิร์ดใหม่: {th['keywords']}")
        theme_mapping[th["name"]] = th["keywords"]
        all_new_keywords.extend(th["keywords"])
    all_new_keywords = list(dict.fromkeys(all_new_keywords))

    quota = check_quota()
    if quota is not None and quota < len(all_new_keywords):
        print(f"\n❌ quota ไม่พอ ({quota} < {len(all_new_keywords)} คำใหม่) - หยุดก่อนเสียเงิน/โควตาฟรี")
        sys.exit(1)

    # 🆕 (2026-09-12, audit m1) เดิม ask_years=False - horizon_months ล็อกที่ default_years*12=36 เดือน
    # เสมอ ไม่สนใจ TREND_YEARS ที่ main.py ถามผู้ใช้ตอนเริ่ม (⑦ ใช้ ask_years=True อยู่แล้ว - ⑩ ควรตรงกัน
    # เพราะเรียก forecast_trend() แบบเดียวกัน เอาไปพยากรณ์คำใหม่ที่เจอจากรอบค้นพบนี้)
    topic, horizon_months = prompt_run_config(default_topic="beauty and personal care", default_years=3,
                                               ask_years=True)
    user_query = _force_worldwide_query(topic)
    print(f"\nกำลังยิง Google Trends เฉพาะ {len(all_new_keywords)} คำใหม่ (worldwide) แล้วพยากรณ์...")
    # 🆕 (2026-09-16) แพตช์ tf2 ด้วย - Step 6-7 ข้างใน forecast_trend() เคยยิง OpenRouter (402) เพราะ
    # use_bedrock() ปกติแพตช์แค่ trend_final v1 (ดู fetch_trends_worldwide_serpapi.py จุดเดียวกัน)
    with use_bedrock(module=tf2):
        cluster_names, df_results, master_report, _ = tf2.forecast_trend(
            OUTPUT_DIR, theme_mapping, user_query, horizon=horizon_months,
        )

    quota_after = check_quota()
    if quota is not None and quota_after is not None:
        print(f"ใช้ quota ไปจริง: {quota - quota_after} search")

    print("\n" + "=" * 70)
    print("ผลตรวจสอบ - Google Trends จริงยืนยันธีมที่ LLM เสนอไหม")
    print("=" * 70)
    verdicts = []
    for row in master_report:
        cluster_id, name, model, status, cur_z, fc_z, z_delta, peak, kws, ctx, quality, pct = row
        insufficient = quality == "insufficient" or pct is None or pct < 5
        verdict = ("❌ ข้อมูลไม่พอจะตัดสิน (Google Trends แทบไม่มีคนค้นคำพวกนี้ - LLM อาจเห็นแพตเทิร์นที่ไม่มีอยู่จริง)"
                   if insufficient else
                   f"✅ ยืนยันด้วยข้อมูลจริง (Data_Quality={quality}, {pct}% เดือนมีข้อมูล)")
        print(f"\n🔦 {name}")
        print(f"   Status={status} | Z_Delta={z_delta} | Model={model}")
        print(f"   {verdict}")
        verdicts.append({"theme": name, "z_delta": z_delta, "status": status,
                         "data_quality": quality, "pct_months_with_data": pct, "verdict": verdict})

    out_path = OUTPUTS / "phase2_cross_category_discovery_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "_note": "⑩ รอบค้นพบเพิ่ม (optional) - ธีมข้ามหมวดที่ LLM เสนอ + ผลตรวจด้วย Google Trends จริง",
            "themes_proposed": raw_themes, "themes_kept_after_filter": themes,
            "master_report": master_report, "verdicts": verdicts,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ Saved -> {out_path}")
