# -*- coding: utf-8 -*-
"""
⑯ PDF Report — รายงานเทรนด์ฉบับ PDF 2 ภาษา (อังกฤษ + ไทย, สไลด์ 16:9 ตามแบบรายงาน Trend Hunter) จากผลรัน 1 รอบ

อ่านผลที่มีอยู่แล้วในโฟลเดอร์รอบ (⑥ ⑦ ⑧-⑨ ⑪ ⑫ ⑭-⑮) มาจัดหน้าอย่างเดียว - ไม่เกี่ยวกับ ⑬ (การเทียบแบรนด์) เลย - ตัวเลขทุกตัวมาจากไฟล์ผลรัน
ส่วนที่เรียก LLM มีแค่งานภาษา (enrich.py) ซึ่ง cache ไว้แล้วไม่เรียกซ้ำ:
    อังกฤษ - เรียบเรียงจุดเด่นเทรนด์ (⑪ ที่เป็นภาษาไทย) เป็นภาษาอังกฤษ
    ไทย    - เขียนข้อความต่อเทรนด์เป็นภาษาไทย + แปลบทวิเคราะห์ภาษาอังกฤษ (Takeaway/STEPIC/Personas/...) และเหตุผลจับคู่สินค้า
ข้อความตายตัวของทั้ง 2 ภาษาอยู่ใน i18n.py (เทมเพลตเดียวกัน)

ผลลัพธ์ในโฟลเดอร์รอบ:
    phase6_trend_report.pdf              รายงานภาษาอังกฤษ
    phase6_trend_report_TH.pdf           รายงานภาษาไทย
    phase6_report_context.json           ข้อมูลทั้งหมดที่ใช้สร้างรายงาน ทั้ง 2 ภาษา (ไว้ตรวจย้อนหลัง/ดีบัก)
    phase6_report_enrichment.json        cache ข้อความภาษาอังกฤษจาก LLM
    phase6_report_enrichment_TH.json     cache ข้อความ/คำแปลภาษาไทยจาก LLM

Usage:
    python tool/step5_pdf/trend_report_pdf.py                  # ถามว่าจะใช้รอบไหน (Enter = ล่าสุด)
    python tool/step5_pdf/trend_report_pdf.py --run <ชื่อรอบ>
    python tool/step5_pdf/trend_report_pdf.py --run <ชื่อรอบ> --lang th   # เฉพาะฉบับภาษาไทย
    python tool/step5_pdf/trend_report_pdf.py --run <ชื่อรอบ> --no-llm    # ไม่เรียก LLM เลย
main.py เรียกขั้นนี้ให้เองท้ายไปป์ไลน์ โดยส่ง TREND_RUN_ID มาทาง env (ได้ทั้ง 2 ภาษา)
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL_DIR = HERE.parent
PROJECT_ROOT = TOOL_DIR.parent
OUTPUT_ROOT = PROJECT_ROOT / "output"
BRANDING_FILE = PROJECT_ROOT / "config" / "report_branding.json"
PRODUCT_CSV = TOOL_DIR / "product" / "watsons_product.csv"
IMAGE_CACHE = OUTPUT_ROOT / "_checkpoints" / "product_images"

PDF_FILES = {"en": "phase6_trend_report.pdf", "th": "phase6_trend_report_TH.pdf"}
CONTEXT_FILE = "phase6_report_context.json"
ENRICH_FILES = {"en": "phase6_report_enrichment.json", "th": "phase6_report_enrichment_TH.json"}
LANG_LABELS = {"en": "ภาษาอังกฤษ", "th": "ภาษาไทย"}

sys.path.insert(0, str(HERE))
from report_data import HIGHLIGHTS_FILE, build_context, read_json  # noqa: E402

DEFAULT_BRANDING = {"company_name": "S & J International Enterprises Public Company Limited", "logo_path": "tool/step5_pdf/assets/logo.png", "logo_for_dark_bg": True,
                    "prepared_by": "", "accent_color": "#E8611A"}


def list_runs():
    """รอบที่ทำรายงานได้ = มีผล ⑪ (ชุด Top N) - ข้ามโฟลเดอร์ขึ้นต้นด้วย "_" ตามกติกาใน output/README.md"""
    runs = [d for d in OUTPUT_ROOT.iterdir()
            if d.is_dir() and not d.name.startswith("_") and (d / HIGHLIGHTS_FILE).exists()] if OUTPUT_ROOT.exists() else []
    return sorted(runs, key=lambda d: (d / HIGHLIGHTS_FILE).stat().st_mtime, reverse=True)


def choose_run(run_name):
    """--run > TREND_RUN_ID (ตั้งโดย main.py) > ถามเลือก (Enter/ไม่มีคนตอบ = รอบล่าสุด)"""
    run_name = run_name or os.environ.get("TREND_RUN_ID")
    if run_name:
        # "_legacy_flat" = ชุดข้อมูลเก่าที่วางแบนๆ ที่ output/ ตรงๆ (sentinel เดียวกับ bootstrap.py / main.py โหมด 2)
        run_dir = OUTPUT_ROOT if run_name == "_legacy_flat" else OUTPUT_ROOT / run_name
        if not (run_dir / HIGHLIGHTS_FILE).exists():
            raise SystemExit(f"❌ รอบ '{run_name}' ไม่มี {HIGHLIGHTS_FILE} - ต้องรันไปป์ไลน์ถึง ⑪ ก่อน")
        return run_dir
    runs = list_runs()
    if not runs:
        raise SystemExit(f"❌ ไม่พบรอบที่มี {HIGHLIGHTS_FILE} ใน {OUTPUT_ROOT}")
    print("\nเลือกรอบรันที่จะทำรายงาน PDF:")
    for i, run in enumerate(runs, 1):
        print(f"  {i}. {run.name}{'  ← ล่าสุด' if i == 1 else ''}")
    try:
        raw = input(f"เลือกหมายเลข [1-{len(runs)}] (Enter = 1): ").strip()
    except (EOFError, OSError):
        raw = ""
    return runs[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= len(runs) else runs[0]


def load_branding():
    brand = {**DEFAULT_BRANDING, **{k: v for k, v in (read_json(BRANDING_FILE) or {}).items() if not k.startswith("_")}}
    from assets import file_data_uri
    logo_path = brand.get("logo_path")
    brand["logo"] = file_data_uri(PROJECT_ROOT / logo_path) if logo_path else None
    if logo_path and not brand["logo"]:
        print(f"  ⚠️ ไม่พบไฟล์โลโก้ {PROJECT_ROOT / logo_path} - ใช้ชื่อบริษัทแทน")
    return brand


def import_bootstrap():
    """import bootstrap หลังตั้ง TREND_RUN_ID แล้ว (OUTPUTS + manifest ผูกกับรอบที่เลือก) - พังก็ไปต่อได้
    แค่ไม่มี LLM และไม่บันทึก manifest (เช่น เครื่องที่ไม่มีคีย์ API ใน .env)"""
    sys.path.insert(0, str(TOOL_DIR))
    try:
        from common import bootstrap
        return bootstrap
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ import common.bootstrap ไม่ได้ ({type(e).__name__}: {str(e)[:150]}) - ข้ามส่วนที่ใช้ LLM")
        return None


def _fmt_counts(counts):
    return ", ".join(f"{n} {src}" for src, n in counts.items())


def make_llm_call(bs):
    """ฟังก์ชันเรียก LLM (โมเดลของ tf ปัจจุบัน - ใช้ภายใน `with bs.use_bedrock():`) ตอบเป็น JSON - ใช้ร่วมกับ ⑰"""
    def llm_call(system, user, max_tokens=900):
        response = bs.tf.client.chat.completions.create(
            model=bs.tf.MODEL_NAME_META,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0, max_tokens=max_tokens, response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    return llm_call


def enrich(ctx, run_dir, bs, langs, use_llm, refresh):
    """ข้อความจาก LLM ของทุกภาษาที่เลือก (ใช้ cache ก่อน) - เข้า Bedrock ครั้งเดียวทั้งหมด
    คืน {ภาษา: ข้อความสรุปแหล่งที่มา} ไว้พิมพ์ในหน้า Notes ของรายงานภาษานั้น"""
    from enrich import condense_report_texts, enrich_trends, translate_report_texts

    # cache ภาษาอังกฤษโหลดเสมอ - ผลย่อหน้า STEPIC/Signals (ภาษาอังกฤษ) เก็บในไฟล์นี้ และฉบับไทยแปลจากฉบับย่อนั้น
    caches = {lang: read_json(run_dir / ENRICH_FILES[lang]) or {} for lang in dict.fromkeys(["en", *langs])}
    sources = {}

    def run(llm_call, parse):
        condensed = condense_report_texts(ctx, caches["en"], llm_call=llm_call, parse=parse, refresh=refresh)
        print(f"  ย่อข้อความหน้า STEPIC / Signals: {_fmt_counts(condensed) or '-'}")
        for lang in langs:
            _, counts = enrich_trends(ctx["trends"], caches[lang], llm_call=llm_call, parse=parse,
                                      refresh=refresh, lang=lang)
            sources[lang] = _fmt_counts(counts)
            if lang == "th":
                ctx["th"], _, report_counts = translate_report_texts(ctx, caches["th"], llm_call=llm_call,
                                                                     parse=parse, refresh=refresh)
                sources[lang] = f"เทรนด์: {sources[lang]} · ข้อความระดับรายงาน: {_fmt_counts(report_counts) or '-'}"

    if not use_llm or bs is None:
        run(None, json.loads)
    else:
        try:
            with bs.use_bedrock():
                run(make_llm_call(bs), bs.safe_json_parse)
        except RuntimeError as e:  # ไม่มีคีย์ Bedrock - use_bedrock() โยนตอนเข้า context
            print(f"  ⚠️ ใช้ LLM ไม่ได้ ({str(e)[:150]}) - ใช้ cache/ข้อความสำรองแทน")
            run(None, json.loads)
    for lang, cache in caches.items():
        if cache.get("items") or cache.get("report") or cache.get("condensed"):
            with open(run_dir / ENRICH_FILES[lang], "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
    return sources


def main():
    parser = argparse.ArgumentParser(description="⑯ รายงานเทรนด์ PDF (อังกฤษ + ไทย) ของรอบรันที่เลือก")
    parser.add_argument("--run", default=None, help="ชื่อโฟลเดอร์รอบใน main/output (ไม่ใส่ = TREND_RUN_ID หรือถามเลือก)")
    parser.add_argument("--lang", choices=["both", "en", "th"], default="both", help="ภาษาที่จะสร้าง (ค่าเริ่มต้น: ทั้ง 2 ภาษา)")
    parser.add_argument("--title", default=None, help="ชื่อรายงานภาษาอังกฤษบนปก (ค่าเริ่มต้น: '<หัวข้อ> Trend Forecast')")
    parser.add_argument("--title-th", default=None, help="ชื่อรายงานภาษาไทยบนปก (ค่าเริ่มต้น: 'พยากรณ์เทรนด์ <หัวข้อ>')")
    parser.add_argument("--no-llm", action="store_true", help="ไม่เรียก LLM - ใช้ cache เดิมหรือข้อความสำรอง")
    parser.add_argument("--refresh-llm", action="store_true", help="เรียก LLM ใหม่ทุกเทรนด์ ไม่ใช้ cache")
    parser.add_argument("--keep-html", action="store_true", help="เก็บไฟล์ HTML ไว้ข้างๆ PDF (ดีบักหน้าตา)")
    args = parser.parse_args()
    langs = ["en", "th"] if args.lang == "both" else [args.lang]

    run_dir = choose_run(args.run)
    # ต้องตั้งก่อน import bootstrap (OUTPUTS + manifest ผูกกับค่านี้)
    os.environ["TREND_RUN_ID"] = "_legacy_flat" if run_dir == OUTPUT_ROOT else run_dir.name
    print("=" * 70)
    print(f"⑯ PDF Report — รอบ {run_dir.name}")
    print("=" * 70)

    bs = import_bootstrap()
    ctx, series = build_context(run_dir, catalog_path=PRODUCT_CSV)
    print(f"  โหลดข้อมูล {len(ctx['trends'])} เทรนด์"
          + (f" | ไม่มีข้อมูล: {', '.join(ctx['missing'])}" if ctx["missing"] else ""))

    sources = enrich(ctx, run_dir, bs, langs, use_llm=not args.no_llm, refresh=args.refresh_llm)
    for lang in langs:
        print(f"  ข้อความ{LANG_LABELS[lang]}: {sources[lang]}")

    with open(run_dir / CONTEXT_FILE, "w", encoding="utf-8") as f:
        json.dump(ctx, f, ensure_ascii=False, indent=2)

    from assets import attach_product_images, svg_data_uri
    from charts import BUMP_CHART_KEY, TREND_MAP_KEY, bump_chart_svg, forecast_chart_svg, trend_map_svg
    from i18n import localize
    from render import html_to_pdf, render_html

    n_ok, n_all = attach_product_images(ctx["trends"], IMAGE_CACHE)
    print(f"  รูปสินค้า {n_ok}/{n_all}")

    brand = load_branding()
    titles = {"en": args.title or f"{ctx['meta']['title']} Trend Forecast",
              "th": args.title_th or f"พยากรณ์เทรนด์ {ctx['meta']['title']}"}
    run_date = datetime.fromisoformat(ctx["meta"]["run_date"])
    saved = []
    for lang in langs:
        # กราฟวาดแยกต่อภาษา (ป้ายแกน/คำอธิบายในกราฟเป็นภาษานั้น)
        charts = {t["name"]: svg_data_uri(forecast_chart_svg(series.get(t["name"]), t, lang=lang))
                  for t in ctx["trends"]}
        charts[TREND_MAP_KEY] = svg_data_uri(trend_map_svg(ctx["trends"], lang=lang))
        charts[BUMP_CHART_KEY] = svg_data_uri(bump_chart_svg(series, ctx["trends"], lang=lang))

        html = render_html(localize(ctx, lang), brand, charts, titles[lang], run_date, sources[lang], lang=lang)
        pdf_path = run_dir / PDF_FILES[lang]
        if args.keep_html:
            pdf_path.with_suffix(".html").write_text(html, encoding="utf-8")
        overflow = html_to_pdf(html, pdf_path)
        for item in overflow:
            print(f"  ⚠️ [{lang}] ข้อความล้นกล่อง (ย่อฟอนต์ถึงขั้นต่ำแล้ว): {item}")
        saved.append(pdf_path)
    print()
    for pdf_path in saved:
        print(f"✅ บันทึกรายงานแล้ว: {pdf_path}")


if __name__ == "__main__":
    main()
