# -*- coding: utf-8 -*-
"""
⑱ Brand × Category × Price-Tier Report — รายงาน PDF 1 ไฟล์ต่อ 1 แบรนด์ลูกค้า (อังกฤษ + ไทย) คู่กับรายงานแบรนด์ ⑰
(รันลูกค้า 1 ครั้งจึงได้ 2 รายงาน: ⑰ เทียบกับตลาดทั้งร้าน / ⑱ เทียบในหมวดของเทรนด์ แล้วแบ่งตามช่วงราคาของแบรนด์)

อ่านผล ⑬ ของแบรนด์ (phase3_brand_coverage_<แบรนด์>.json ช่อง price_tiers - สร้างโดย run_brand_coverage.py ตามหลักใน
phase3_supply_layer/price_tiers.py) + ข้อมูลเทรนด์ชุดเดียวกับรายงานเทรนด์ของรอบนั้น แล้วจัดหน้า:
ปก → สรุปผู้บริหาร → ตารางภาพรวม (เทรนด์ → หมวดหลัก → อันดับในหมวด/ในแต่ละระดับราคา) → เทรนด์ละ 1 หน้า
(3 ระดับราคาของแบรนด์: top 5 ของหมวด∩ระดับราคา + สินค้าที่ดีที่สุดของแบรนด์พร้อมอันดับ) → ภาคผนวก

ไม่เรียก LLM สำหรับเนื้อหาของรายงานนี้ (ไม่มีเหตุผลจับคู่ให้แปล) - LLM ใช้แค่สร้าง/ใช้ cache ข้อความเทรนด์ของ ⑯ เหมือน ⑰
ผลเก่าที่ยังไม่มี price_tiers: เติมด้วย `python tool/phase3_supply_layer/run_brand_coverage.py --tiers-only` ก่อน (หน้าเทรนด์นั้นขึ้นข้อความแจ้ง)

ผลลัพธ์ในโฟลเดอร์รอบ (ต่อแบรนด์):
    phase6_brand_category_report_<แบรนด์>.pdf         ภาษาอังกฤษ
    phase6_brand_category_report_<แบรนด์>_TH.pdf      ภาษาไทย
    phase6_brand_category_context_<แบรนด์>.json       ข้อมูลที่ใช้สร้างรายงาน (ไว้ตรวจย้อนหลัง)

Usage:
    python tool/phase6_pdf_report/build_brand_category_report.py --run <ชื่อรอบ> --brand Mizumi
    python tool/phase6_pdf_report/build_brand_category_report.py --run <ชื่อรอบ>          # ทุกแบรนด์ที่มีผล ⑬ ในรอบนั้น
main.py เรียกให้เองต่อจาก ⑰ ของแต่ละแบรนด์ (ทั้งโหมด 1 และโหมด 2) โดยส่ง TREND_RUN_ID ทาง env + --brand
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_pdf_report as trend_report  # noqa: E402  (ตัวเลือกรอบ/branding/bootstrap/ข้อความเทรนด์ ใช้ร่วมกับ ⑯ และ ⑰)
from brand_category_data import (apply_th, build_category_context, find_coverage_file,  # noqa: E402
                                 image_items, list_coverage_files, load_catalog, load_config, safe_file_part)
from report_data import build_context, product_trends, read_json  # noqa: E402

LANG_SUFFIX = {"en": "", "th": "_TH"}


def attach_images(bctx):
    """รูปสินค้าของแบรนด์ (cache เดียวกับรายงานเทรนด์) -> p["image"] = data URI หรือ None"""
    from assets import fetch_image

    items = image_items(bctx)
    urls = sorted({p["image_url"] for p in items if p.get("image_url")})
    with ThreadPoolExecutor(max_workers=8) as pool:
        uris = dict(zip(urls, pool.map(lambda u: fetch_image(u, trend_report.IMAGE_CACHE), urls)))
    for p in items:
        p["image"] = uris.get(p.get("image_url"))


def _for_json(bctx):
    """category context สำหรับบันทึก: แทน dict เทรนด์เต็ม (ซ้ำกับ phase6_report_context.json) ด้วยชื่อเทรนด์"""
    out = dict(bctx)
    out["rows"] = [{**{k: v for k, v in r.items() if k != "trend"}, "trend": r["name"]} for r in bctx["rows"]]
    return out


CONFIG_FILE = trend_report.PROJECT_ROOT / "config" / "brand_report.json"   # เกณฑ์เกรดชุดเดียวกับ ⑰


def build_one(coverage_path, run_dir, ctx, catalog, style, langs, args, cfg=None):
    from brand_category_i18n import category_strings
    from i18n import localize
    from render import html_to_pdf, render_brand_category_html

    coverage = read_json(coverage_path) or {}
    b_en = build_category_context(ctx, coverage, catalog, cfg)
    brand = b_en["brand"]
    safe = safe_file_part(brand)
    print(f"\n▶ {brand}: เทียบตามหมวด/ช่วงราคาได้ {b_en['n_ok']}/{len(b_en['rows'])} เทรนด์ ({b_en['n_pages']} หน้าหมวด) "
          f"(ตรวจแล้วแต่ไม่มีสินค้าในหมวดของเทรนด์ {len(b_en['highlights']['no_brand'])})")
    if b_en["missing_tiers"]:
        print(f"  ⚠️ ผล ⑬ ของ {brand} ไม่มี category_fit {len(b_en['missing_tiers'])} เทรนด์ - รัน "
              f"run_brand_coverage.py --category-fit-only --brand {brand} (หรือรันค้นหาแบรนด์ใหม่) แล้วสร้างรายงานซ้ำ")
    with open(run_dir / f"phase6_brand_category_context_{safe}.json", "w", encoding="utf-8") as f:
        json.dump(_for_json(b_en), f, ensure_ascii=False, indent=2)

    run_date = datetime.fromisoformat(ctx["meta"]["run_date"])
    saved = []
    for lang in langs:
        L = category_strings(lang)
        lctx = localize(ctx, lang)
        b = build_category_context(lctx, coverage, catalog, cfg)
        if lang == "th":
            b = apply_th(b)
        attach_images(b)
        title = L["cat_cover_title"].format(brand=brand, title=ctx["meta"]["title"])
        html = render_brand_category_html(lctx, b, style, {}, title, run_date, lang=lang)
        pdf_path = run_dir / f"phase6_brand_category_report_{safe}{LANG_SUFFIX[lang]}.pdf"
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
    return saved


def main():
    parser = argparse.ArgumentParser(description="⑱ รายงานหมวด x ระดับราคา PDF (อังกฤษ + ไทย) ต่อแบรนด์")
    parser.add_argument("--run", default=None, help="ชื่อโฟลเดอร์รอบใน main/output (ไม่ใส่ = TREND_RUN_ID หรือถามเลือก)")
    parser.add_argument("--brand", action="append", default=None,
                        help="ชื่อแบรนด์ (ใส่ซ้ำได้หลายแบรนด์) - ไม่ใส่ = ทุกแบรนด์ที่มีผล ⑬ ในรอบนั้น")
    parser.add_argument("--lang", choices=["both", "en", "th"], default="both", help="ภาษาที่จะสร้าง (ค่าเริ่มต้น: ทั้ง 2 ภาษา)")
    parser.add_argument("--no-llm", action="store_true", help="ไม่เรียก LLM - ใช้ cache ข้อความเทรนด์เดิม")
    parser.add_argument("--keep-html", action="store_true", help="เก็บไฟล์ HTML ไว้ข้างๆ PDF (ดีบักหน้าตา)")
    args = parser.parse_args()
    langs = ["en", "th"] if args.lang == "both" else [args.lang]

    run_dir = trend_report.choose_run(args.run)
    os.environ["TREND_RUN_ID"] = "_legacy_flat" if run_dir == trend_report.OUTPUT_ROOT else run_dir.name
    print("=" * 70)
    print(f"⑱ Brand × Category × Price-Tier Report — รอบ {run_dir.name}")
    print("=" * 70)

    if args.brand:
        targets = []
        for name in args.brand:
            path = find_coverage_file(run_dir, name)
            if path is None:
                print(f"❌ ไม่พบผลค้นหาแบรนด์ (⑬) ของ '{name}' ในรอบนี้ - รันค้นหาแบรนด์ก่อน")
            else:
                targets.append(path)
    else:
        targets = list_coverage_files(run_dir)
    if not targets:
        raise SystemExit("❌ ไม่มีแบรนด์ให้ทำรายงาน")

    bs = trend_report.import_bootstrap()
    ctx, _series = build_context(run_dir, catalog_path=trend_report.PRODUCT_CSV)
    # ข้อความเทรนด์ 2 ภาษา: ใช้ cache ของรายงานเทรนด์ (⑯) - ไม่มีค่อยเรียก LLM (ครั้งเดียวต่อรอบ ใช้ร่วมทุกแบรนด์)
    trend_report.enrich(ctx, run_dir, bs, ["en", "th"], use_llm=not args.no_llm, refresh=False)
    # 🆕 (2026-10-08) ชื่อที่แสดงในรายงาน (build_display_names.py) - ชุดเดียวกับรายงานเทรนด์ ⑯
    from display_names import apply_display_names, load_display_names
    apply_display_names(ctx, load_display_names(run_dir))
    ctx = product_trends(ctx)   # 🆕 (2026-10-14) ไม่รวมหน้าเทรนด์ที่ไม่พบสินค้าในตลาดของ ⑯
    catalog = load_catalog(trend_report.PRODUCT_CSV)
    style = trend_report.load_branding()
    cfg = load_config(CONFIG_FILE)

    saved = []
    for path in targets:
        saved += build_one(path, run_dir, ctx, catalog, style, langs, args, cfg)
    print()
    for pdf_path in saved:
        print(f"✅ บันทึกรายงานแล้ว: {pdf_path}")
    if len(saved) < len(targets) * len(langs):
        sys.exit(1)


if __name__ == "__main__":
    main()
