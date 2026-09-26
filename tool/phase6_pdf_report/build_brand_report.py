# -*- coding: utf-8 -*-
"""
⑰ Brand × Trend Fit Report — รายงาน PDF 1 ไฟล์ต่อ 1 แบรนด์ลูกค้า (อังกฤษ + ไทย) แยกจากรายงานเทรนด์ (⑯)

อ่านผล ⑬ ของแบรนด์ (phase3_brand_coverage_<แบรนด์>.json) + ข้อมูลเทรนด์ชุดเดียวกับรายงานเทรนด์ของรอบนั้น แล้วจัดหน้า:
ปก → สรุปผู้บริหาร → Trend Fit Matrix → ตารางภาพรวม → เทรนด์ละ 1 หน้า (สินค้าของแบรนด์ 3 อันดับแรก เทียบเจ้าตลาด)
→ โอกาสพัฒนาสินค้า → ภาคผนวก - ระดับความพร้อมคำนวณจากอันดับจริงในตลาดตามเกณฑ์ใน config/brand_report.json
(ไม่ใช้ tier ของ ⑬ - ดูเหตุผลใน brand_data.py)

LLM: แปลเหตุผลจับคู่สินค้าของแบรนด์ (ภาษาอังกฤษจาก ⑬) เป็นไทยเท่านั้น (cache ต่อแบรนด์) - ข้อความเทรนด์ใช้ cache ของ
รายงานเทรนด์ (⑯) ถ้ายังไม่เคยสร้างรายงานเทรนด์ของรอบนี้จะสร้างข้อความเทรนด์ให้ก่อน (ใช้ cache เดียวกัน)

ผลลัพธ์ในโฟลเดอร์รอบ (ต่อแบรนด์):
    phase6_brand_report_<แบรนด์>.pdf              ภาษาอังกฤษ
    phase6_brand_report_<แบรนด์>_TH.pdf           ภาษาไทย
    phase6_brand_context_<แบรนด์>.json            ข้อมูลที่ใช้สร้างรายงาน (ไว้ตรวจย้อนหลัง)
    phase6_brand_enrichment_<แบรนด์>_TH.json      cache คำแปลเหตุผลจับคู่สินค้า

Usage:
    python tool/phase6_pdf_report/build_brand_report.py --run <ชื่อรอบ> --brand Mizumi
    python tool/phase6_pdf_report/build_brand_report.py --run <ชื่อรอบ> --brand Mizumi --brand Eucerin
    python tool/phase6_pdf_report/build_brand_report.py --run <ชื่อรอบ>          # ทุกแบรนด์ที่มีผล ⑬ ในรอบนั้น
main.py เรียกให้เองหลัง ⑬ ของแต่ละแบรนด์ (ทั้งโหมด 1 และโหมด 2) โดยส่ง TREND_RUN_ID ทาง env + --brand
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

import build_pdf_report as trend_report  # noqa: E402  (ตัวเลือกรอบ/branding/bootstrap/ข้อความเทรนด์ ใช้ร่วมกับ ⑯)
from brand_data import (build_brand_context, brand_reason_groups, find_coverage_file,  # noqa: E402
                        list_coverage_files, load_catalog, load_config, safe_file_part)
from report_data import build_context, read_json  # noqa: E402

CONFIG_FILE = trend_report.PROJECT_ROOT / "config" / "brand_report.json"
LANG_SUFFIX = {"en": "", "th": "_TH"}


def translate_reasons(bctx_en, run_dir, bs, use_llm, refresh):
    """เหตุผลจับคู่สินค้าของแบรนด์ -> ภาษาไทย (cache ต่อแบรนด์) คืน ({ชื่อเทรนด์: [คำแปล]}, สรุปจำนวน)"""
    from enrich import translate_items_th

    path = run_dir / f"phase6_brand_enrichment_{safe_file_part(bctx_en['brand'])}_TH.json"
    cache = read_json(path) or {}
    groups = brand_reason_groups(bctx_en)
    kwargs = {"refresh": refresh, "label": "เหตุผลจับคู่สินค้า"}
    if use_llm and bs is not None:
        try:
            with bs.use_bedrock():
                translations, cache, counts = translate_items_th(groups, cache, llm_call=trend_report.make_llm_call(bs),
                                                                 parse=bs.safe_json_parse, **kwargs)
        except RuntimeError as e:  # ไม่มีคีย์ Bedrock
            print(f"  ⚠️ ใช้ LLM ไม่ได้ ({str(e)[:150]}) - ใช้ cache/ภาษาอังกฤษแทน")
            translations, cache, counts = translate_items_th(groups, cache, **kwargs)
    else:
        translations, cache, counts = translate_items_th(groups, cache, **kwargs)
    if cache.get("items"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    return translations, counts


def attach_images(bctx):
    """รูปสินค้าของแบรนด์และสินค้าเจ้าตลาด (cache เดียวกับรายงานเทรนด์) -> p["image"] = data URI หรือ None"""
    from assets import fetch_image

    items = [p for r in bctx["rows"] for p in r["products"] + ([r["leader"]] if r.get("leader") else [])]
    urls = sorted({p["image_url"] for p in items if p.get("image_url")})
    with ThreadPoolExecutor(max_workers=8) as pool:
        uris = dict(zip(urls, pool.map(lambda u: fetch_image(u, trend_report.IMAGE_CACHE), urls)))
    for p in items:
        p["image"] = uris.get(p.get("image_url"))


def _for_json(bctx):
    """brand context สำหรับบันทึก: แทน dict เทรนด์เต็ม (ซ้ำกับ phase6_report_context.json) ด้วยชื่อเทรนด์"""
    out = dict(bctx)
    out["rows"] = [{**{k: v for k, v in r.items() if k != "trend"}, "trend": r["name"]} for r in bctx["rows"]]
    return out


def build_one(coverage_path, run_dir, ctx, catalog, cfg, style, langs, bs, args):
    from assets import svg_data_uri
    from brand_i18n import apply_th, brand_strings
    from charts import FIT_MATRIX_KEY, fit_matrix_svg, trend_color
    from i18n import localize
    from render import html_to_pdf, render_brand_html

    coverage = read_json(coverage_path) or {}
    bctx_en = build_brand_context(ctx, coverage, catalog, cfg)
    brand = bctx_en["brand"]
    safe = safe_file_part(brand)
    print(f"\n▶ {brand}: {bctx_en['n_checked']}/{len(bctx_en['rows'])} เทรนด์ | "
          + ", ".join(f"{lv} {n}" for lv, n in bctx_en["counts"].items()))
    if bctx_en["missing_trends"]:
        print(f"  ⚠️ ผล ⑬ ของ {brand} ไม่มี {len(bctx_en['missing_trends'])} เทรนด์ของรอบนี้ - รันค้นหาแบรนด์ใหม่เพื่อให้ครบ")

    translations = {}
    if "th" in langs:
        translations, counts = translate_reasons(bctx_en, run_dir, bs, not args.no_llm, args.refresh_llm)
        print(f"  คำแปลเหตุผลจับคู่สินค้า: {trend_report._fmt_counts(counts) or '-'}")
    with open(run_dir / f"phase6_brand_context_{safe}.json", "w", encoding="utf-8") as f:
        json.dump({**_for_json(bctx_en), "reasons_th": translations}, f, ensure_ascii=False, indent=2)

    thresholds = cfg["fit_rank_thresholds"]
    boundary = max(thresholds[lv] for lv in cfg["strong_fit_levels"] if lv in thresholds)
    run_date = datetime.fromisoformat(ctx["meta"]["run_date"])
    saved = []
    for lang in langs:
        L = brand_strings(lang)
        lctx = localize(ctx, lang)
        b = build_brand_context(lctx, coverage, catalog, cfg)
        if lang == "th":
            b = apply_th(b, translations)
        attach_images(b)
        for r in b["rows"]:  # สีประจำเทรนด์ของรายการข้างกราฟ ให้ตรงกับจุดในกราฟ
            r["color"], r["color_text"] = trend_color(r["rank"])
        labels ={"x": L["matrix_x"], "y": L["matrix_y"], "levels": {lv: L[lv] for lv in thresholds} | {"gap": L["gap"]},
                  **{q: L[q] for q in ("defend", "build", "maintain", "monitor")}}
        charts = {FIT_MATRIX_KEY: svg_data_uri(fit_matrix_svg(b["rows"], b["momentum_split"], boundary, thresholds,
                                                               b["n_market"], labels))}
        title = L["cover_title"].format(brand=brand, title=ctx["meta"]["title"])
        html = render_brand_html(lctx, b, style, charts, title, run_date, lang=lang)
        pdf_path = run_dir / f"phase6_brand_report_{safe}{LANG_SUFFIX[lang]}.pdf"
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
    parser = argparse.ArgumentParser(description="⑰ รายงานแบรนด์ x เทรนด์ PDF (อังกฤษ + ไทย) ต่อแบรนด์")
    parser.add_argument("--run", default=None, help="ชื่อโฟลเดอร์รอบใน main/output (ไม่ใส่ = TREND_RUN_ID หรือถามเลือก)")
    parser.add_argument("--brand", action="append", default=None,
                        help="ชื่อแบรนด์ (ใส่ซ้ำได้หลายแบรนด์) - ไม่ใส่ = ทุกแบรนด์ที่มีผล ⑬ ในรอบนั้น")
    parser.add_argument("--lang", choices=["both", "en", "th"], default="both", help="ภาษาที่จะสร้าง (ค่าเริ่มต้น: ทั้ง 2 ภาษา)")
    parser.add_argument("--no-llm", action="store_true", help="ไม่เรียก LLM - ใช้ cache เดิมหรือภาษาอังกฤษต้นฉบับ")
    parser.add_argument("--refresh-llm", action="store_true", help="แปลเหตุผลจับคู่สินค้าใหม่ ไม่ใช้ cache")
    parser.add_argument("--keep-html", action="store_true", help="เก็บไฟล์ HTML ไว้ข้างๆ PDF (ดีบักหน้าตา)")
    args = parser.parse_args()
    langs = ["en", "th"] if args.lang == "both" else [args.lang]

    run_dir = trend_report.choose_run(args.run)
    os.environ["TREND_RUN_ID"] = "_legacy_flat" if run_dir == trend_report.OUTPUT_ROOT else run_dir.name
    print("=" * 70)
    print(f"⑰ Brand × Trend Fit Report — รอบ {run_dir.name}")
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
    catalog = load_catalog(trend_report.PRODUCT_CSV)
    cfg = load_config(CONFIG_FILE)
    style = trend_report.load_branding()

    saved = []
    for path in targets:
        saved += build_one(path, run_dir, ctx, catalog, cfg, style, langs, bs, args)
    print()
    for pdf_path in saved:
        print(f"✅ บันทึกรายงานแล้ว: {pdf_path}")
    if len(saved) < len(targets) * len(langs):
        sys.exit(1)


if __name__ == "__main__":
    main()
