# -*- coding: utf-8 -*-
"""
⑯/⑰/⑱ สร้างชื่อเทรนด์ที่แสดงในรายงาน (🆕 2026-10-08) -> <รอบ>/phase6_display_names.json (ดูเหตุผลใน display_names.py)

ชื่อในไปป์ไลน์มาจากคำสมาชิกของคลัสเตอร์ 15 คำเท่านั้น จึงเติมคำที่ข้อมูลไม่มี / ผิดเรื่อง / ผิดทิศได้ ที่นี่ให้ LLM เห็นข้อมูลมากขึ้น
(ทั้งหมดอยู่ในไฟล์ผลของแต่ละสายอยู่แล้ว ไม่ดึงข้อมูลใหม่): ประเภทแหล่งที่มา + คำสมาชิกครบทุกคำ + ชื่อบทความต้นทาง
- คลัสเตอร์สร้างคืนจาก triplet_provenance (เฉพาะ verified) ด้วย bootstrap.build_trend_graph เดิม (seed ตายตัว) แล้วจับคู่กับแถวเทรนด์
  ด้วยขนาด + คำในตัวอย่าง Members (ลำดับสมาชิกที่สร้างคืนอาจต่างจากเดิม) - จับคู่ไม่ได้ -> ใช้ตัวอย่าง Members 60 ตัวอักษรแทน
- กฎชื่อ (ผู้ใช้ 2026-10-08: "ชื่อเทรนด์ควรกว้างๆ ไม่เจาะจงหมวดหมู่ ให้คนอ่านไม่เข้าใจผิด"): บอกความต้องการ/พฤติกรรม/การเปลี่ยนแปลงของตลาด,
  ห้ามชื่อหมวด/ประเภทสินค้า (หมวดแสดงแยกในรายงาน), ห้ามแบรนด์และคำโฆษณา, ทิศทางต้องถูก, บอกถ้าเป็นข่าวบริษัท/งานวิจัยด้านสูตร,
  สะท้อนเรื่องที่แหล่งส่วนใหญ่พูด ไม่ใช่เรื่องรองของแหล่งเดียว, เล่าข่าวตามที่รายงานจริง (ทดสอบใน output/_experiments/llm_category/)

ชื่อที่ได้เป็น**ร่าง** (approved = false) รายงานยังไม่ใช้ - คนตรวจแล้ว: ชื่อใช้ได้ -> ตั้ง "approved": true / แก้ชื่อ -> เปลี่ยน "display"
แล้วตั้ง "source": "manual" (รันซ้ำจะไม่ทับ - --force ทับเฉพาะ source = llm) รอบแรก 2026-10-08 หลายชื่อกว้างเกิน/ผิดเรื่อง จึงต้องมีคนตรวจ
ใช้: python tool/phase6_pdf_report/build_display_names.py --run <รอบ> [--force]
แล้วสร้างรายงานใหม่ (build_pdf_report.py / build_brand_report.py / build_brand_category_report.py) - ไม่ต้องรันขั้นอื่น
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from display_names import DISPLAY_FILE  # noqa: E402

PROMPT_VERSION = "v1-2026-10-08"
STREAM_FILES = {"Paper": "phase1_paper_stream_result.json", "Social": "phase2_social_stream_result.json",
                "News": "phase2_news_stream_result.json"}
SOURCE_TYPE = {"Paper": "scientific papers and research articles",
               "News": "industry and business news articles",
               "Social": "consumer social media posts and reviews (Thai and international)"}
MAX_TITLES = 8

PROMPT = """You write the display name of a beauty and personal care trend for a market report. The goal is that readers are NOT misled.
The input gives the type of sources, the terms grouped together, and the titles of the source documents.

Write a broad name of 2-6 English words that:
1. describes the underlying consumer need, behaviour or market shift, broad enough to cover the whole group rather than one product or one article;
2. does NOT name a product category or product type (for example sunscreen, shampoo, serum, cream, concealer, blush, perfume, fragrance, hair care, skincare, make-up) - the report shows the category separately; consumer concerns such as acne, hair loss or sensitivity are allowed;
3. contains no brand or company names and no marketing or hype words (clinical, medical-grade, advanced, luxury, next-gen, revolutionary, editorial ...);
4. states the direction correctly (for example people rejecting a look is not a comeback of that look);
5. if the sources are about companies or the industry (acquisitions, expansions, licensing, sales targets) or about formulation research for manufacturers rather than shoppers, makes that clear;
6. reflects the theme shared by most of the terms and sources - not a side story that only one source mentions;
7. describes company or industry news exactly as reported (for example a company exploring a sale is not an acquisition).
Before answering, check your name against rule 2 and rewrite it if it contains a product category or product type word.

Return ONLY JSON: {"trend_name": "<name>", "basis": "<one short sentence on what the name rests on>"}"""


def cluster_inputs(result, bs):
    """ไฟล์ผล 1 สาย -> {ชื่อเทรนด์: {"terms", "titles", "cluster_ok"}} จากคลัสเตอร์ที่สร้างคืน + triplet_provenance"""
    prov = [t for t in result.get("triplet_provenance") or [] if t.get("verified")]
    _, clusters = bs.build_trend_graph([t["triplet"] for t in prov])
    clusters = [list(c) for c in clusters]
    out = {}
    for row in result.get("trends") or []:
        preview = [t.strip() for t in str(row.get("Members") or "").rstrip(".").split(",")][:-1]
        hits = [c for c in clusters if len(c) == row.get("Cluster Size") and all(t in c for t in preview)]
        if len(hits) == 1:
            terms = preview + [m for m in hits[0] if m not in preview]
            norm = {bs._normalize_entity(m) for m in terms}
            inner = [t for t in prov if bs._normalize_entity(t["triplet"][0]) in norm and bs._normalize_entity(t["triplet"][2]) in norm]
            edge = [t for t in prov if (bs._normalize_entity(t["triplet"][0]) in norm) != (bs._normalize_entity(t["triplet"][2]) in norm)]
            used = inner if len(inner) >= 5 else inner + edge
            titles = [t for t, _ in Counter(x.get("title") for x in used if x.get("title")).most_common(MAX_TITLES)]
            out[row["Trend Name"]] = {"terms": terms, "titles": titles, "cluster_ok": True}
        else:
            out[row["Trend Name"]] = {"terms": [str(row.get("Members") or "")], "titles": [], "cluster_ok": False}
    return out


def ask(bs, stream, info):
    user = (f"SOURCE TYPE: {SOURCE_TYPE[stream]}\n\nTERMS ({len(info['terms'])}): {', '.join(info['terms'])}\n\n"
            "SOURCE TITLES:\n" + ("\n".join(f"- {t}" for t in info["titles"]) or "- (not available)"))
    for attempt in range(5):
        try:
            r = bs.tf.client.chat.completions.create(
                model=bs.tf.MODEL_NAME_META, temperature=0, max_tokens=800, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": PROMPT}, {"role": "user", "content": user}])
            d = bs.safe_json_parse(r.choices[0].message.content) or {}
            if str(d.get("trend_name") or "").strip():
                return d["trend_name"].strip(), str(d.get("basis") or "").strip()
        except Exception as e:   # noqa: BLE001
            print(f"   ⚠️ {str(e)[:100]}", flush=True)
        time.sleep(3 * (attempt + 1))
    return None, None


def main():
    p = argparse.ArgumentParser(description="สร้างชื่อเทรนด์ที่แสดงในรายงาน (ไม่เปลี่ยนชื่อในไปป์ไลน์)")
    p.add_argument("--run", required=True, help="ชื่อโฟลเดอร์รอบใน main/output")
    p.add_argument("--force", action="store_true", help="ตั้งชื่อใหม่ทุกเทรนด์ที่ source = llm (ชื่อ manual / curated ไม่ถูกทับ)")
    args = p.parse_args()
    run_dir = HERE.parents[1] / "output" / args.run
    if not run_dir.is_dir():
        raise SystemExit(f"❌ ไม่พบรอบ {run_dir}")
    os.environ["TREND_RUN_ID"] = run_dir.name   # ต้องตั้งก่อน import bootstrap
    sys.path.insert(0, str(HERE.parent))
    from dotenv import load_dotenv
    import common.bootstrap as bs
    load_dotenv(dotenv_path=bs.PROJECT_ROOT / ".env", override=True)

    path = run_dir / DISPLAY_FILE
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    names = data.get("names") or {}
    todo = []
    for stream, fname in STREAM_FILES.items():
        if not (run_dir / fname).exists():
            continue
        result = json.loads((run_dir / fname).read_text(encoding="utf-8"))
        for trend, info in cluster_inputs(result, bs).items():
            key = f"{stream}::{trend}"
            old = names.get(key) or {}
            # ชื่อที่คนแก้/เกลาแล้ว (source ไม่ใช่ llm เช่น manual / curated) ไม่ทับเลย แม้ใช้ --force
            if old.get("source") not in (None, "llm") or (old.get("display") and not args.force):
                continue
            todo.append((key, stream, trend, info))
    print(f"{run_dir.name}: ตั้งชื่อ {len(todo)} เทรนด์ (มีอยู่แล้ว {len(names)})")
    with bs.use_bedrock():
        for key, stream, trend, info in todo:
            display, basis = ask(bs, stream, info)
            if not display:
                print(f"  ❌ {trend}: LLM ตอบไม่ได้ - คงชื่อเดิม")
                continue
            names[key] = {"display": display, "source": "llm", "approved": False, "basis": basis, "titles": info["titles"],
                          "n_terms": len(info["terms"]), "cluster_rebuilt": info["cluster_ok"]}
            print(f"  {trend}  ->  {display}")
    data = {"_note": "ชื่อเทรนด์ที่แสดงในรายงาน ⑯/⑰/⑱ (display_names.py) - ชื่อในไปป์ไลน์ไม่เปลี่ยน. ชื่อจาก LLM เป็นร่าง รายงานยังไม่ใช้ "
                     "จนกว่าจะตรวจ: ใช้ได้ -> approved = true / แก้ชื่อ -> เปลี่ยน display แล้วตั้ง source = manual "
                     "(build_display_names.py จะไม่ทับ) จากนั้นสร้างรายงานใหม่",
            "prompt_version": PROMPT_VERSION, "updated": datetime.now().isoformat(timespec="seconds"),
            "names": dict(sorted(names.items()))}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ บันทึก {path}")


if __name__ == "__main__":
    main()
