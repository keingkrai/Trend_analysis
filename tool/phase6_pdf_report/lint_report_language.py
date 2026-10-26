# -*- coding: utf-8 -*-
"""
สคริปต์ตรวจภาษาของรายงาน ⑯/⑰/⑱ (🆕 2026-10-12 ขั้น E ของแผนภาษาง่าย)

ตรวจ 3 แหล่ง (ไม่เรียก API/LLM):
  1) ข้อความตายตัวทั้งหมด (i18n.STRINGS / BRAND_STRINGS / CATEGORY_STRINGS / UNIT_STRINGS ทั้ง EN/TH)
  2) ข้อความที่ LLM เขียนของรอบ (cache ⑯ EN/TH, ⑰ แปลเหตุผล, เหตุผลจับคู่ EN) - เฉพาะเทรนด์ที่อยู่ในรอบนี้ (ข้ามรายการค้างใน cache)
  3) PDF ที่สร้างแล้ว (phase6_*.pdf) - คำต้องห้าม/ศัพท์ pipeline/ตัวแทนค่าที่ไม่ถูกแทน ({n}, None, nan) ในหน้านอกภาคผนวก

กติกา (ชุดเดียวกับที่ใช้ตอนเขียน - plain_text.py):
  ERROR  คำต้องห้ามนอกภาคผนวก (YoY, SKU, โมเดลภาษา, similarity ...) / ศัพท์ pipeline หลุด (⑬, --category-fit-only, *.py, Run ID)
         / ตัวแทนค่าไม่ถูกแทน ({n}) หรือ None/nan ในข้อความที่ผู้อ่านเห็น
  WARN   ประโยคยาว (EN > 35 คำ / ไทยท่อนไม่เว้นวรรคยาวเกิน 110 ตัวอักษร) / คำอังกฤษทั่วไป (ตัวพิมพ์เล็ก ไม่ใช่ชื่อสินค้า/ส่วนผสมที่รู้จัก)
         ในข้อความไทย - "คำทั่วไปให้เป็นไทย คงอังกฤษเฉพาะชื่อ"
ภาคผนวก (คีย์ method_*/m_*/notes_* ฯลฯ และหน้า "ภาคผนวก"/"Appendix") ใช้ศัพท์เทคนิคได้ - ข้ามกติกาคำต้องห้าม

รัน:  python tool/phase6_pdf_report/lint_report_language.py                 # ทุกรอบใน output/ (ไม่รวมโฟลเดอร์ขึ้นต้น _)
      python tool/phase6_pdf_report/lint_report_language.py --run <รอบ> --md lint.md
      เงื่อนไขจบ: มี ERROR = exit 1 (--strict นับ WARN ด้วย)
"""
import argparse
import json
import re
import sys
from collections import Counter, namedtuple
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from plain_text import _BANNED, find_banned  # noqa: E402

OUTPUT_ROOT = HERE.parents[1] / "output"
HIGHLIGHTS_FILE = "phase3_trend_highlights_result.json"

# PDF ที่ pipeline สร้าง: ⑯ trend_report, ⑰ brand_report_<แบรนด์>, ⑱ brand_category_report_<แบรนด์> (+ _TH) - growth_method เป็นเอกสารวิธีการ (เทคนิคโดยเจตนา) จึงไม่ตรวจ
PIPELINE_PDF_RE = re.compile(r"^phase6_(trend_report|brand_report_[^_.]+|brand_category_report_[^_.]+)(_TH)?\.pdf$")

ERROR, WARN = "ERROR", "WARN"
Finding = namedtuple("Finding", "source where lang rule level detail excerpt")

EN_MAX_WORDS = 35            # ประโยคภาษาอังกฤษยาวสุด (คำ)
TH_MAX_CLAUSE_CHARS = 110    # ไทยไม่เว้นวรรคระหว่างคำ - ท่อนที่คั่นด้วยช่องว่างยาวเกินนี้ถือว่าอ่านยาก
MAX_EXCERPT = 140

# ข้อความตายตัวที่เป็นภาคผนวก (อธิบายวิธีการ - ใช้ศัพท์เทคนิคได้)
APPENDIX_PREFIXES = ("method_", "m_", "notes_", "run_", "how_to_use", "data_", "report_copy", "language_models", "report_generated",
                     "forecast_window", "topic", "cat_data")

# ศัพท์ pipeline/ภายในที่ผู้อ่านไม่ควรเห็นเลยแม้ในภาคผนวก (ไม่รวม run_id ที่เป็นค่าข้อมูล)
LEAK_PATTERNS = [r"[⑩-⑳]", r"--[a-z][a-z0-9]*(?:-[a-z0-9]+)+", r"\b[a-z_0-9]+\.py\b", r"run_brand_coverage|validate_at_scale|category_fit",
                  r"\bTREND_[A-Z_]+\b", r"\bphase\d_\w+", r"\{[a-z_0-9]+\}", r"\bNone\b", r"\bnan\b"]
_LEAK_RE = [re.compile(p) for p in LEAK_PATTERNS]

# ตัวอักษรอังกฤษตัวพิมพ์เล็ก >= 4 ตัว = "คำทั่วไป" ที่ควรเป็นไทย (ชื่อ/ตัวย่อขึ้นต้นตัวใหญ่ไม่นับ) - ยกเว้นคำที่รู้จักด้านล่าง + ชื่อจากข้อมูลของรอบ
BASE_ALLOW = {
    # ส่วนผสม/มาตรฐาน/หน่วยที่คงอังกฤษได้
    "retinol", "retinoid", "tretinoin", "adapalene", "tazarotene", "trifarotene", "niacinamide", "ceramide", "ceramides", "peptide",
    "peptides", "collagen", "hyaluronic", "salicylic", "glycolic", "lactic", "azelaic", "vitamin", "panthenol", "centella", "cica",
    "madecassoside", "squalane", "ectoin", "bakuchiol", "minoxidil", "benzoyl", "peroxide", "sunscreen", "serum", "toner", "essence",
    "dendrimer", "dendrimers", "nades", "pdrn", "spf", "uva", "uvb", "iso", "pcs", "mini", "konvy", "google", "trends", "stepic",
    "excellent", "good", "average", "below", "dermatology", "dermocosmetics", "makeup", "skincare", "haircare", "retinoids",
    "dendritic", "poly", "lysine", "esters", "citric", "acid", "acids", "aha", "bha", "pha", "emulsion", "emulsions", "barrier",
    "hair", "skin", "care", "clinical", "protocols", "protocol",
    "hydroxy", "polyglycerol", "partial", "glycerides", "fatty", "glycerin", "glycerol", "titanium", "dioxide", "zinc", "oxide",
    "palmitoleic", "macadamia", "buckthorn", "pulp", "silicone", "silicones", "surfactants", "nanocarriers", "nanoemulsions",
    "nanoemulsion", "liposomes", "liposome", "niacinamide", "hyaluronate", "allantoin", "propolis", "probiotic", "probiotics",
    "prebiotic", "prebiotics", "postbiotic", "postbiotics", "biotin", "caffeine", "keratin", "silk", "jojoba", "shea", "argan",
}
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’\-]{3,}")
_THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
_PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}")


# ----------------------------------------------------------------------------- ตัวตรวจต่อข้อความ
def is_appendix_key(key):
    return str(key).startswith(APPENDIX_PREFIXES)


def _excerpt(text):
    text = " ".join(str(text).split())
    return text if len(text) <= MAX_EXCERPT else text[: MAX_EXCERPT - 1] + "…"


def long_sentences(text, lang):
    """ข้อความ -> [(ส่วนที่ยาวเกิน, ขนาด)] - EN: ประโยค (จบด้วย . ! ?) เกิน EN_MAX_WORDS คำ; ไทย: ท่อนที่คั่นด้วยช่องว่างยาวเกิน TH_MAX_CLAUSE_CHARS"""
    text = _PLACEHOLDER_RE.sub("x", str(text))
    out = []
    if lang == "en":
        for sent in re.split(r"(?<=[.!?])\s+", text):
            n = len(sent.split())
            if n > EN_MAX_WORDS:
                out.append((sent, n))
    else:
        for clause in re.split(r"[\s·|]+", text):
            thai = len(_THAI_RE.findall(clause))
            if thai > TH_MAX_CLAUSE_CHARS:
                out.append((clause, thai))
    return out


def english_words_in_thai(text, allow):
    """คำอังกฤษตัวพิมพ์เล็กยาว >= 4 ตัวในข้อความไทยที่ไม่อยู่ในรายการอนุญาต (ไม่ซ้ำ)"""
    if not _THAI_RE.search(text):
        return []
    found = []
    for m in _WORD_RE.finditer(_PLACEHOLDER_RE.sub(" ", text)):
        w = m.group(0)
        if w[0].isupper() or w.isupper():
            continue   # ชื่อ/ตัวย่อ
        key = w.lower().strip("-'’")
        parts = [p for p in re.split(r"[-']", key) if len(p) > 1]
        if key in allow or all(p in allow for p in parts):
            continue
        if key not in found:
            found.append(key)
    return found


def check_text(source, where, lang, text, allow, appendix=False, prose=True, template=False):
    """ข้อความ 1 ชิ้น -> [Finding] ตามกติกา (appendix=True ข้ามคำต้องห้ามและความยาว แต่ยังตรวจศัพท์ pipeline หลุด;
    template=True = ข้อความตายตัวที่มี {ตัวแทนค่า} ได้ตามปกติ - ตัดตัวแทนค่าออกก่อนตรวจ)"""
    if not isinstance(text, str) or not text.strip():
        return []
    findings = []
    shown = text
    if template:
        text = _PLACEHOLDER_RE.sub("x", text)

    def add(rule, level, detail):
        findings.append(Finding(source, where, lang, rule, level, detail, _excerpt(shown)))

    leaks = [m.group(0) for rx in _LEAK_RE for m in rx.finditer(text)]
    if leaks:
        add("pipeline-leak", ERROR, ", ".join(dict.fromkeys(leaks)))
    if appendix:
        return findings
    banned = find_banned(text, lang)
    if banned:
        add("banned-term", ERROR, ", ".join(banned))
    if prose:
        for sent, n in long_sentences(text, lang):
            add("long-sentence", WARN, f"{n} {'คำ' if lang == 'en' else 'ตัวอักษรไทยติดกัน'}: {_excerpt(sent)[:60]}")
        if lang == "th":
            words = english_words_in_thai(text, allow)
            if words:
                add("english-word", WARN, ", ".join(words[:8]))
    return findings


# ----------------------------------------------------------------------------- 1) ข้อความตายตัว
def lint_static_strings(allow=None):
    import brand_category_i18n
    import brand_i18n
    import i18n
    import unit_i18n

    allow = BASE_ALLOW if allow is None else allow
    tables = (("i18n.STRINGS", i18n.STRINGS), ("brand_i18n.BRAND_STRINGS", brand_i18n.BRAND_STRINGS),
              ("brand_category_i18n.CATEGORY_STRINGS", brand_category_i18n.CATEGORY_STRINGS),
              ("unit_i18n.UNIT_STRINGS", unit_i18n.UNIT_STRINGS))
    out = []
    for name, table in tables:
        for lang in ("en", "th"):
            for key, text in (table.get(lang) or {}).items():
                out += check_text(name, f"{key}", lang, text, allow, appendix=is_appendix_key(key), template=True)
    return out


# ----------------------------------------------------------------------------- 2) ข้อความที่ LLM เขียนของรอบ
def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _tokens(texts):
    return {w.lower().strip("-'’") for t in texts if isinstance(t, str) for w in _WORD_RE.findall(t)}


def run_allowlist(run_dir):
    """ชื่อที่รู้จักของรอบ: เทรนด์ + แบรนด์ + ชื่อสินค้าใน ⑫/⑬ -> ชุดคำตัวพิมพ์เล็ก (รวมกับ BASE_ALLOW)"""
    names = []
    hl = _read_json(run_dir / HIGHLIGHTS_FILE) or {}
    for p in (hl.get("profiles") or []):
        names += [p.get("trend", ""), p.get("key_ingredients", ""), p.get("target", "")]
    match = _read_json(run_dir / "phase3_scale_validation_nvidia_result.json") or {}
    for r in (match.get("results") or {}).values():
        for m in r.get("top_matches") or []:
            names += [m.get("product_name", ""), m.get("brand", "")]
        for c in (r.get("by_category") or {}).get("categories") or []:
            names += [c.get("group", ""), c.get("subgroup") or ""]
            for p in (c.get("products") or []) + [t.get("product") or {} for t in c.get("price_tiers") or []]:
                names += [p.get("product_name", ""), p.get("brand", "")]
    for path in run_dir.glob("phase3_brand_coverage_*.json"):
        d = _read_json(path) or {}
        names.append(d.get("brand", ""))
        for v in (d.get("coverage") or {}).values():
            names += [v.get("brand_best_product", ""), v.get("market_best_product", "")]
            names += [m.get("product_name", "") for m in v.get("brand_top_matches") or []]
    return BASE_ALLOW | _tokens(names)


def _trend_names(run_dir):
    hl = _read_json(run_dir / HIGHLIGHTS_FILE) or {}
    return {p.get("trend") for p in (hl.get("profiles") or [])}


def collect_run_texts(run_dir):
    """ข้อความที่ LLM เขียนของรอบ -> [(แหล่ง, ตำแหน่ง, ภาษา, ข้อความ)] เฉพาะเทรนด์ของรอบนี้"""
    out = []
    trends = _trend_names(run_dir)
    en = _read_json(run_dir / "phase6_report_enrichment.json") or {}
    th = _read_json(run_dir / "phase6_report_enrichment_TH.json") or {}

    def add(source, where, lang, text):
        if isinstance(text, str) and text.strip():
            out.append((source, where, lang, text))

    def block(source, base, lang, obj):
        if isinstance(obj, str):
            add(source, base, lang, obj)
        elif isinstance(obj, list):
            for i, x in enumerate(obj):
                block(source, f"{base}[{i}]", lang, x)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("name", "mega_trend_name"):   # ชื่อเรียก - อังกฤษได้
                    continue
                block(source, f"{base}.{k}", lang, v)

    for name, item in (en.get("items") or {}).items():
        if not trends or name in trends:
            block("enrichment.json", f"items[{name}]", "en", (item or {}).get("output"))
    for section in ("condensed", "plain_en"):
        for name, item in (en.get(section) or {}).items():
            block("enrichment.json", f"{section}.{name}", "en", (item or {}).get("output"))
    for name, item in (en.get("ladder") or {}).items():
        if not trends or name in trends:
            out_ = (item or {}).get("output") or {}
            block("enrichment.json", f"ladder[{name}].en", "en", out_.get("en"))
            block("enrichment_TH.json", f"ladder[{name}].th", "th", out_.get("th"))
    for name, item in (th.get("items") or {}).items():
        if not trends or name in trends:
            block("enrichment_TH.json", f"items[{name}]", "th", (item or {}).get("output"))
    for name, item in (th.get("report") or {}).items():
        block("enrichment_TH.json", f"report.{name}", "th", (item or {}).get("output"))

    for path in sorted(run_dir.glob("phase6_brand_enrichment_*_TH.json")):
        brand = path.stem.replace("phase6_brand_enrichment_", "").replace("_TH", "")
        names = set()
        for ctx_path in run_dir.glob("phase6_brand_context_*.json"):
            if ctx_path.stem.lower().endswith(brand.lower()):
                names = {r.get("name") for r in (_read_json(ctx_path) or {}).get("rows", [])}
        for name, item in ((_read_json(path) or {}).get("items") or {}).items():
            if not names or name in names:
                block(path.name, f"items[{name}]", "th", (item or {}).get("output"))
    for path in sorted(run_dir.glob("phase6_brand_context_*.json")):
        for row in (_read_json(path) or {}).get("rows", []):
            for i, p in enumerate(row.get("products") or []):
                add(path.name, f"rows[{row.get('name')}].products[{i}].reason", "en", p.get("reason"))
    return out


def lint_run_texts(run_dir):
    allow = run_allowlist(run_dir)
    out = []
    for source, where, lang, text in collect_run_texts(run_dir):
        out += check_text(source, where, lang, text, allow)
    return out


# ----------------------------------------------------------------------------- 3) PDF ที่สร้างแล้ว
def _pdf_pages(path):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        try:
            from pypdf import PdfReader
        except ImportError:
            return None
        return [(p.extract_text() or "") for p in PdfReader(str(path)).pages]
    pdf = pdfium.PdfDocument(str(path))
    return [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]


COMPARISON_TERMS_RE = re.compile(r"\b(CAGR|YoY)\b")


def is_appendix_page(text):
    """หน้าภาคผนวก (หัวขึ้นต้น ภาคผนวก/Appendix) + 🆕 (2026-10-14) หน้าเทียบมุมมอง CAGR / YoY ที่เจ้าของงานให้อยู่ต่อจากหน้าภาพรวม
    (ชื่อหน้ามีคำว่า CAGR หรือ YoY) - ใช้ศัพท์เหล่านี้ได้ตามที่ขอ"""
    head = " ".join(text.split())[:60]
    return head.startswith("ภาคผนวก") or head.startswith("Appendix") or bool(COMPARISON_TERMS_RE.search(head))


_ASCII_BANNED = {lang: [re.compile(p, re.I) for p in pats if p.isascii() and "\\u" not in p] for lang, pats in _BANNED.items()}


def _keyword_phrases(run_dir):
    """คีย์เวิร์ดที่ค้น Google Trends จริงของรอบ (แสดงเป็นชิป "คีย์เวิร์ดที่ติดตาม") - เป็นข้อมูลไม่ใช่ข้อความที่เขียน ไม่ตรวจคำต้องห้าม
    (เช่น "holistic health" ที่เป็นคำค้นจริง)"""
    ctx = _read_json(run_dir / "phase6_report_context.json") or {}
    words = {k.strip() for t in ctx.get("trends") or [] for k in (t.get("keywords") or []) if isinstance(k, str) and k.strip()}
    return sorted(words, key=len, reverse=True)


def lint_pdfs(run_dir):
    """PDF ของรอบ -> [Finding] (หน้านอกภาคผนวก: คำต้องห้ามที่เป็นอักษรละติน + ศัพท์ pipeline/ตัวแทนค่าที่ไม่ถูกแทน)
    ชั้นข้อความไทยของ PDF มีสระ/วรรณยุกต์ซ้ำจึงตรวจเฉพาะคำละติน - คำไทยตรวจที่แหล่งข้อความ (ข้อ 1-2)"""
    out = []
    keywords = _keyword_phrases(run_dir)
    for path in sorted(run_dir.glob("phase6_*.pdf")):
        if not PIPELINE_PDF_RE.match(path.name):
            continue   # ไฟล์ที่คัดลอก/ตั้งชื่อเองไม่ใช่ผลของ pipeline
        pages = _pdf_pages(path)
        if pages is None:
            return out + [Finding(path.name, "-", "-", "no-pdf-reader", WARN, "ไม่มี pypdfium2/pypdf - ข้ามการตรวจ PDF", "")]
        lang = "th" if path.stem.endswith("_TH") else "en"
        for i, text in enumerate(pages, 1):
            appendix = is_appendix_page(text)
            hits = [m.group(0) for rx in _LEAK_RE for m in rx.finditer(text)]
            # "None"/"nan" ซ้ำกับชื่อสินค้าได้ยาก - ยอมรับตามที่พบ; ตัวแทนค่า {x} และศัพท์ pipeline ผิดเสมอ
            if hits:
                out.append(Finding(path.name, f"หน้า {i}", lang, "pipeline-leak", ERROR, ", ".join(dict.fromkeys(hits)), ""))
            if appendix:
                continue
            scan = text
            for kw in keywords:   # ตัดคีย์เวิร์ดที่ค้นจริงออกก่อนตรวจคำต้องห้าม (ข้อมูล ไม่ใช่ข้อความเขียน)
                scan = re.sub(re.escape(kw), " ", scan, flags=re.I)
            banned = [m.group(0) for rx in _ASCII_BANNED[lang] for m in rx.finditer(scan)]
            if banned:
                out.append(Finding(path.name, f"หน้า {i}", lang, "banned-term", ERROR, ", ".join(dict.fromkeys(banned)), ""))
    return out


# ----------------------------------------------------------------------------- สรุป/รายงาน
def list_runs(root=OUTPUT_ROOT):
    return sorted(d for d in Path(root).iterdir()
                  if d.is_dir() and not d.name.startswith("_") and (d / HIGHLIGHTS_FILE).exists())


def summarize(findings):
    c = Counter((f.level, f.rule) for f in findings)
    return {"ERROR": sum(n for (lv, _), n in c.items() if lv == ERROR), "WARN": sum(n for (lv, _), n in c.items() if lv == WARN),
            "by_rule": {f"{lv}:{rule}": n for (lv, rule), n in sorted(c.items())}}


def render_markdown(results):
    """results = {ชื่อรอบ หรือ "ข้อความตายตัว": [Finding]} -> markdown"""
    lines = ["# ผลตรวจภาษารายงาน ⑯/⑰/⑱", ""]
    lines += ["| แหล่ง | ERROR | WARN | แยกตามกติกา |", "|---|---:|---:|---|"]
    for name, items in results.items():
        s = summarize(items)
        rules = ", ".join(f"{k} {v}" for k, v in s["by_rule"].items()) or "-"
        lines.append(f"| {name} | {s['ERROR']} | {s['WARN']} | {rules} |")
    for name, items in results.items():
        if not items:
            continue
        lines += ["", f"## {name}", "", "| ระดับ | กติกา | ไฟล์/คีย์ | ภาษา | รายละเอียด | ข้อความ |", "|---|---|---|---|---|---|"]
        for f in sorted(items, key=lambda x: (x.level != ERROR, x.rule, x.source, x.where)):
            cell = lambda s: str(s).replace("|", "\\|").replace("\n", " ")   # noqa: E731
            lines.append(f"| {f.level} | {f.rule} | {cell(f.source)} · {cell(f.where)} | {f.lang} | {cell(f.detail)} | {cell(f.excerpt)} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="ตรวจภาษาของรายงาน ⑯/⑰/⑱ (ข้อความตายตัว + ข้อความ LLM + PDF)")
    parser.add_argument("--run", action="append", default=None, help="ชื่อรอบ (ซ้ำได้) - ไม่ใส่ = ทุกรอบใน output/")
    parser.add_argument("--no-pdf", action="store_true", help="ไม่ตรวจ PDF (เร็วขึ้น)")
    parser.add_argument("--no-static", action="store_true", help="ไม่ตรวจข้อความตายตัว")
    parser.add_argument("--md", default=None, help="เขียนผลเป็น markdown ไปที่ไฟล์นี้")
    parser.add_argument("--json", default=None, help="เขียนผลเป็น JSON ไปที่ไฟล์นี้")
    parser.add_argument("--strict", action="store_true", help="นับ WARN เป็นไม่ผ่านด้วย (exit 1)")
    parser.add_argument("--root", default=str(OUTPUT_ROOT), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    root = Path(args.root)
    runs = [root / r for r in args.run] if args.run else list_runs(root)
    results = {}
    if not args.no_static:
        results["ข้อความตายตัว"] = lint_static_strings()
    for run_dir in runs:
        items = lint_run_texts(run_dir)
        if not args.no_pdf:
            items += lint_pdfs(run_dir)
        results[run_dir.name] = items

    for name, items in results.items():
        s = summarize(items)
        print(f"{name}: ERROR {s['ERROR']} · WARN {s['WARN']}" + (f"  ({', '.join(f'{k} {v}' for k, v in s['by_rule'].items())})" if items else ""))
        for f in [x for x in items if x.level == ERROR][:12]:
            print(f"   ERROR [{f.rule}] {f.source} · {f.where} ({f.lang}): {f.detail}")
    if args.md:
        Path(args.md).write_text(render_markdown(results), encoding="utf-8")
        print("เขียน", args.md)
    if args.json:
        Path(args.json).write_text(json.dumps({k: [f._asdict() for f in v] for k, v in results.items()}, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    total = {lv: sum(summarize(v)[lv] for v in results.values()) for lv in (ERROR, WARN)}
    print(f"รวม: ERROR {total[ERROR]} · WARN {total[WARN]}")
    return 1 if total[ERROR] or (args.strict and total[WARN]) else 0


if __name__ == "__main__":
    sys.exit(main())
