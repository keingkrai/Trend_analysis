# -*- coding: utf-8 -*-
"""
⑲ รายงานส่วนแบ่งตลาด — Phase 5: สร้าง PDF อังกฤษ + ไทย จากผล Phase 1-4 (ไม่เรียก LLM / API)

ใช้ระบบ PDF ชุดเดียวกับ ⑯/⑰/⑱ (phase6_pdf_report): HTML (Jinja2) -> PDF (Playwright Chromium) 16:9, branding
จาก config/report_branding.json, style.css + brand.css + market.css - ข้อมูลหน้ารายงานมาจาก market_report_data.py

ก่อนพิมพ์ตรวจภาษา (ข้อความตายตัวทั้ง 2 ภาษา + คำอธิบายทุกข้อที่จะแสดง): กติกาของ lint_report_language.py (คำต้องห้าม /
ศัพท์ pipeline หลุด / ประโยคยาว / คำอังกฤษทั่วไปในข้อความไทย) + คำว่าชนะ/แพ้ (เฉพาะรายงานนี้ - หน้าวิธีการที่อธิบายกติกานี้ยกเว้น)
มี ERROR = ไม่สร้าง PDF (--force สร้างทั้งที่มี)

ผลลัพธ์ในโฟลเดอร์รอบ:
    phase7_market_report.pdf / phase7_market_report_TH.pdf
    phase7_market_report_context.json      ข้อมูลที่ใช้ทำรายงานทั้ง 2 ภาษา (ไว้ตรวจย้อนหลัง)

Usage:
    python tool/phase7_market_report/build_market_report.py                     # รอบ market_share_* ล่าสุด ทั้ง 2 ภาษา
    python tool/phase7_market_report/build_market_report.py --run <รอบ> --lang th --keep-html
"""
import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PHASE6 = HERE.parent / "phase6_pdf_report"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PHASE6))

from market_facts import OUTPUT_ROOT  # noqa: E402
from market_i18n import MONTHS_TH, STRINGS  # noqa: E402
from market_questions import latest_run  # noqa: E402
from market_report_data import build_context, euromonitor_extracted, read_inputs  # noqa: E402
from market_synthesis import FINDINGS_FILE  # noqa: E402

PDF_FILES = {"en": "phase7_market_report.pdf", "th": "phase7_market_report_TH.pdf"}
CONTEXT_FILE = "phase7_market_report_context.json"
TEMPLATE_DIR = HERE / "templates"
JUDGEMENT = {"en": re.compile(r"\b(win|wins|won|winner|winners|winning|lose|loses|lost|loser|losers|losing)\b", re.I),
             "th": re.compile(r"ชนะ|แพ้")}


def month_year(ym, lang):
    """[2026, 8] -> "Aug 2026" / "ส.ค. 2026" """
    if not ym:
        return ""
    y, m = int(ym[0]), int(ym[1])
    return f"{MONTHS_TH[m - 1]} {y}" if lang == "th" else date(y, m, 1).strftime("%b %Y")


# ---------------------------------------------------------------------------
# ตรวจภาษา
# ---------------------------------------------------------------------------

def lint(contexts):
    """[(ระดับ, ภาษา, ที่, รายละเอียด)] - ERROR ทำให้ไม่สร้าง PDF"""
    from lint_report_language import BASE_ALLOW, ERROR, check_text
    out = []
    brands = {w.lower() for c in contexts.values() for p in c["brand_pages"] for w in re.split(r"\W+", p["brand"]) if w}
    allow = BASE_ALLOW | brands | {"online", "premium", "mass", "google", "news", "euromonitor"}
    for lang, c in contexts.items():
        for key, text in STRINGS[lang].items():
            appendix = key.startswith(("m_", "final_"))
            for f in check_text("strings", key, lang, text, allow, appendix=appendix, template=True):
                out.append((f.level, lang, f"L.{key}", f"{f.rule}: {f.detail}"))
            if not appendix and JUDGEMENT[lang].search(text):
                out.append((ERROR, lang, f"L.{key}", "winner/loser wording"))
        shown = [(f"factor {p['id']}", f["text"]) for p in c["factor_pages"] for f in p["findings"]]
        shown += [(f"brand {p['brand']}", f["text"]) for p in c["brand_pages"] for f in p["findings"]]
        shown += [("summary", msg) for msg in c["messages"]]
        for where, text in shown:
            for f in check_text("findings", where, lang, text, allow):
                out.append((f.level, lang, where, f"{f.rule}: {f.detail}"))
            if JUDGEMENT[lang].search(text):
                out.append((ERROR, lang, where, "winner/loser wording"))
    return out


# ---------------------------------------------------------------------------
# สร้าง
# ---------------------------------------------------------------------------

def make_env():
    from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape
    env = Environment(loader=ChoiceLoader([FileSystemLoader(str(TEMPLATE_DIR)), FileSystemLoader(str(PHASE6 / "templates"))]),
                      autoescape=select_autoescape(["html", "j2"]))
    env.filters["ddmmyyyy"] = lambda d: d.strftime("%d.%m.%Y") if isinstance(d, (date, datetime)) else ""
    return env


def brand_charts(c):
    from assets import svg_data_uri
    from market_charts import share_chart_svg
    m = c["meta"]
    return {p["brand"]: svg_data_uri(share_chart_svg(p["series"], m["y0"], m["y1"])) for p in c["brand_pages"]}


def render(c, brand, charts, run_date, env=None):
    env = env or make_env()
    fda = c["meta"]["fda"]
    return env.get_template("market_report.html.j2").render(
        c=c, L=c["L"], brand=brand, charts=charts, run_date=run_date, year=run_date.year,
        fda_from=month_year(fda.get("first"), c["lang"]), fda_to=month_year(fda.get("complete_through"), c["lang"]))


def main():
    parser = argparse.ArgumentParser(description="⑲ รายงานส่วนแบ่งตลาด PDF (อังกฤษ + ไทย)")
    parser.add_argument("--run", default=None, help="ชื่อโฟลเดอร์ใน main/output (ไม่ใส่ = market_share_* ล่าสุด)")
    parser.add_argument("--lang", choices=["both", "en", "th"], default="both")
    parser.add_argument("--keep-html", action="store_true", help="เก็บไฟล์ HTML ไว้ข้าง PDF (ดีบักหน้าตา)")
    parser.add_argument("--force", action="store_true", help="สร้าง PDF แม้ตรวจภาษาเจอ ERROR")
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    run_dir = OUTPUT_ROOT / args.run if args.run else latest_run()
    if not run_dir or not (run_dir / FINDINGS_FILE).exists():
        sys.exit(f"❌ ไม่มี {FINDINGS_FILE} - รัน market_synthesis.py ก่อน")
    langs = ["en", "th"] if args.lang == "both" else [args.lang]

    import build_pdf_report as trend_report      # branding ชุดเดียวกับ ⑯/⑰/⑱
    from render import html_to_pdf
    brand = trend_report.load_branding()
    inputs = read_inputs(run_dir)
    extracted = euromonitor_extracted()
    contexts = {lang: build_context(inputs, lang, brand["company_name"], extracted) for lang in langs}

    issues = lint(contexts)
    errors = [i for i in issues if i[0] == "ERROR"]
    for level, lang, where, detail in issues:
        print(f"  {'❌' if level == 'ERROR' else '⚠️'} [{lang}] {where}: {detail}")
    if errors and not args.force:
        sys.exit(f"❌ ตรวจภาษาเจอ ERROR {len(errors)} รายการ - แก้แล้วรันใหม่ (หรือ --force)")

    (run_dir / CONTEXT_FILE).write_text(json.dumps({lang: {k: v for k, v in c.items() if k != "L"}
                                                    for lang, c in contexts.items()}, ensure_ascii=False, indent=1,
                                                   default=str), encoding="utf-8")
    run_date = datetime.now()
    env = make_env()
    for lang, c in contexts.items():
        html = render(c, brand, brand_charts(c), run_date, env)
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
        n_pages = html.count('<section class="page')
        print(f"✅ [{lang}] {pdf_path} ({n_pages} หน้า, แหล่งอ้างอิง {len(c['sources'])})")


if __name__ == "__main__":
    main()
