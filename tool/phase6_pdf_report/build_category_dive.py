# -*- coding: utf-8 -*-
"""
⑯ Category Deep-Dive — เล่มเจาะรายหมวดของ Google แบบแยกเล่ม (อังกฤษ + ไทย) ของรอบสาย Search

🆕 (2026-10-28) เนื้อหาเดียวกันนี้อยู่ใน "ส่วนที่ 2" ของรายงานเทรนด์ ⑯ (build_pdf_report.py) แล้ว - main.py ไม่เรียกสคริปต์นี้แล้ว
สคริปต์นี้ยังสร้างเล่มแยกเฉพาะส่วนนี้ได้ (มีปก + หน้าภาพรวม + หน้าวิธีอ่านของตัวเอง ใช้หน้ารายหมวดชุดเดียวกัน _dive_pages.j2)

รายงานหลักรวมเทรนด์ที่คัดจากทุกหมวดของ Google ไว้ด้วยกัน - ส่วนนี้เปิดทีละหมวด: ในหมวดนั้นคนค้นอะไรที่กำลังขึ้น
(หัวข้อย่อยที่ ① จัดไว้) หัวข้อไหนโยงเข้าสินค้าความงาม และหัวข้อไหนเป็นที่มาของเทรนด์ในรายงานหลัก
ข้อมูลมาจาก search_stream_work/ ของรอบ (ไม่รัน ①-⑫ ใหม่ ไม่ใช้ SerpAPI) - LLM ใช้แค่เขียนประโยคอธิบายหัวข้อ 2 ภาษา (โค้ดตรวจกับคำค้นจริงทุกประโยค
ดู category_dive.py) และ cache ไว้ที่ phase6_report_enrichment.json คีย์ "dive"

ผลลัพธ์ในโฟลเดอร์รอบ:
    phase6_category_dive.pdf              ภาษาอังกฤษ
    phase6_category_dive_TH.pdf           ภาษาไทย
    phase6_category_dive_context.json     ข้อมูลที่ใช้สร้างเล่ม (ไว้ตรวจย้อนหลัง)

Usage:
    python tool/phase6_pdf_report/build_category_dive.py --run <ชื่อรอบ>
    python tool/phase6_pdf_report/build_category_dive.py --run <ชื่อรอบ> --no-llm      # ไม่เรียก LLM - ใช้ cache เดิม หัวข้อที่ไม่มี cache แสดงเฉพาะตัวอย่างคำค้น
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_pdf_report as trend_report  # noqa: E402  (ตัวเลือกรอบ/branding/bootstrap/LLM ใช้ร่วมกับ ⑯)
from report_data import build_context, read_json  # noqa: E402

PDF_FILES = {"en": "phase6_category_dive.pdf", "th": "phase6_category_dive_TH.pdf"}
CONTEXT_FILE = "phase6_category_dive_context.json"


def place_text(codes, lang):
    """["TH", "WW"] -> "Thailand and worldwide" / "ไทยและทั่วโลก" (ข้อความตายตัวจากข้อมูล ไม่ผ่าน LLM)"""
    from common.evidence_gate import place_phrase
    from i18n import PLACE_NAMES

    if lang == "en":
        return place_phrase(codes)
    names = [PLACE_NAMES.get(p, (p, p))[1] for p in codes or []]
    return (", ".join(names[:-1]) + "และ" + names[-1]) if len(names) > 1 else (names[0] if names else "")


def describe(dive, run_dir, bs, use_llm, refresh):
    """ประโยคอธิบายหัวข้อ (ใช้ cache ก่อน) - เข้า Bedrock ครั้งเดียว คืนสรุปจำนวนต่อแหล่ง"""
    from dive_text import describe_dive

    path = run_dir / trend_report.ENRICH_FILES["en"]
    cache = read_json(path) or {}
    if not use_llm or bs is None:
        counts = describe_dive(dive, cache, llm_call=None, refresh=False)
    else:
        try:
            with bs.use_bedrock():
                counts = describe_dive(dive, cache, llm_call=trend_report.make_llm_call(bs), parse=bs.safe_json_parse, refresh=refresh)
        except RuntimeError as e:  # ไม่มีคีย์ Bedrock - use_bedrock() โยนตอนเข้า context
            print(f"  ⚠️ ใช้ LLM ไม่ได้ ({str(e)[:150]}) - ใช้ cache/ตัวอย่างคำค้นแทน")
            counts = describe_dive(dive, cache, llm_call=None, refresh=False)
    if cache.get("dive"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    return counts


def main():
    parser = argparse.ArgumentParser(description="⑯ เล่มเจาะรายหมวดของ Google PDF (อังกฤษ + ไทย) ของรอบรันที่เลือก")
    parser.add_argument("--run", default=None, help="ชื่อโฟลเดอร์รอบใน main/output (ไม่ใส่ = TREND_RUN_ID หรือถามเลือก)")
    parser.add_argument("--lang", choices=["both", "en", "th"], default="both", help="ภาษาที่จะสร้าง (ค่าเริ่มต้น: ทั้ง 2 ภาษา)")
    parser.add_argument("--no-llm", action="store_true", help="ไม่เรียก LLM - ใช้ cache เดิมหรือตัวอย่างคำค้น")
    parser.add_argument("--refresh-llm", action="store_true", help="เรียก LLM ใหม่ทุกหัวข้อ ไม่ใช้ cache")
    parser.add_argument("--keep-html", action="store_true", help="เก็บไฟล์ HTML ไว้ข้างๆ PDF (ดีบักหน้าตา)")
    args = parser.parse_args()
    langs = ["en", "th"] if args.lang == "both" else [args.lang]

    run_dir = trend_report.choose_run(args.run)
    os.environ["TREND_RUN_ID"] = "_legacy_flat" if run_dir == trend_report.OUTPUT_ROOT else run_dir.name
    print("=" * 70)
    print(f"⑯ Category Deep-Dive — รอบ {run_dir.name}")
    print("=" * 70)

    bs = trend_report.import_bootstrap()
    ctx, _history = build_context(run_dir, catalog_path=trend_report.PRODUCT_CSV)
    from display_names import apply_display_names, load_display_names   # ชื่อเทรนด์ที่แสดงในรายงานหลัก (ป้าย "ในรายงานหลัก: #n ชื่อ")
    apply_display_names(ctx, load_display_names(run_dir))
    from category_dive import for_lang, load_dive, paginate

    dive = load_dive(run_dir, [{"name": t["name"], "display_name": t.get("display_name"), "rank": t.get("rank")} for t in ctx["trends"]])
    if dive is None:
        raise SystemExit("❌ รอบนี้ไม่ใช่รอบสาย Search หรือไม่มีไฟล์ search_stream_work/ - ทำเล่มเจาะรายหมวดไม่ได้")
    print(f"  {dive['n_categories']} หมวด · {dive['n_topics']} หัวข้อ · โยงถึงความงาม {dive['n_linked_topics']} หัวข้อ "
          f"({dive['n_linked_searches']:,} จาก {dive['n_searches']:,} คำค้น = {dive['linked_pct']}%) · หน้ารายหมวด {len(paginate(dive))} หน้า")

    counts = describe(dive, run_dir, bs, use_llm=not args.no_llm, refresh=args.refresh_llm)
    print("  ประโยคอธิบายหัวข้อ: " + (", ".join(f"{n} {src}" for src, n in counts.items()) or "-"))
    with open(run_dir / CONTEXT_FILE, "w", encoding="utf-8") as f:
        json.dump(dive, f, ensure_ascii=False, indent=2)

    from dive_i18n import dive_strings
    from render import html_to_pdf, render_dive_html

    brand = trend_report.load_branding()
    run_date = datetime.fromisoformat(ctx["meta"]["run_date"])
    saved = []
    for lang in langs:
        dv = for_lang(dive, lang, place_text(dive["places"], lang))
        title = dive_strings(lang)["dv_cover_title"].format(title=ctx["meta"]["title"])
        html = render_dive_html(ctx, dv, brand, title, run_date, lang=lang)
        pdf_path = run_dir / PDF_FILES[lang]
        if args.keep_html:
            pdf_path.with_suffix(".html").write_text(html, encoding="utf-8")
        try:
            overflow = html_to_pdf(html, pdf_path)
        except PermissionError:
            print(f"  ❌ เขียน {pdf_path.name} ไม่ได้ - ไฟล์เปิดค้างอยู่ในโปรแกรมอ่าน PDF ปิดไฟล์แล้วรันใหม่")
            continue
        for item in overflow:
            print(f"  ⚠️ [{lang}] ข้อความล้นกล่อง (ย่อฟอนต์ถึงขั้นต่ำแล้ว): {item}")
        saved.append(pdf_path)
    print()
    for pdf_path in saved:
        print(f"✅ บันทึกเล่มแล้ว: {pdf_path}")
    if len(saved) < len(langs):
        sys.exit(1)


if __name__ == "__main__":
    main()
