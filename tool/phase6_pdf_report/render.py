# -*- coding: utf-8 -*-
"""
⑯ PDF Report — HTML (Jinja2) -> PDF (Playwright Chromium)

ทำไม Chromium: จัดวางข้อความได้ถูกทุกภาษา (ฉบับภาษาไทย + ชื่อแบรนด์/สินค้าที่มีอักษรไทย) และรองรับ CSS เต็มรูปแบบ -
ReportLab วางสระ/วรรณยุกต์ไทยเพี้ยน ส่วน WeasyPrint ใช้ไม่ได้บนเครื่องนี้ (ไม่มี GTK) และ Playwright + Chromium
ติดตั้งอยู่แล้วสำหรับ scraper MDPI จึงไม่ต้องลงอะไรเพิ่ม

เทมเพลตเดียวใช้ทั้ง 2 ภาษา - ข้อความตายตัวมาจาก i18n.STRINGS[lang] (ส่งเข้าเทมเพลตชื่อ L)
"""
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from i18n import STRINGS, date_long, source_doc_groups, source_rows
from unit_i18n import with_unit_strings
from common.horizons import LONG_YEAR, SHORT_YEAR   # i18n เพิ่ม tool/ เข้า sys.path ให้แล้ว

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
PAGE_WIDTH, PAGE_HEIGHT = "10in", "5.625in"  # 16:9 เท่าไฟล์ตัวอย่าง (720 x 405 pt)


def _ddmmyyyy(d):
    return d.strftime("%d.%m.%Y") if isinstance(d, datetime) else ""


def make_env(lang="en"):
    L = STRINGS[lang]

    def _signed(v, dp=2):
        return f"{v:+.{dp}f}" if isinstance(v, (int, float)) else L["na"]

    def _num(v, dp=2):
        return f"{v:,.{dp}f}" if isinstance(v, (int, float)) else L["na"]

    def _thb(v):
        return L["thb"].format(v=f"{v:,.0f}") if isinstance(v, (int, float)) else L["price_na"]

    def _date_long(d, with_time=False):
        return date_long(d, lang, with_time) if isinstance(d, datetime) else ""

    # Undefined ปกติ (ไม่ใช่ StrictUndefined) - ผลรอบเก่าบางรอบไม่มีบางช่อง เทมเพลตใช้ `or L.na` รับมือเอง
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)),
                      autoescape=select_autoescape(["html", "j2"]))
    def _unit_num(v):
        """฿ ต่อหน่วย: 2 หลักที่มีความหมาย - >= 100 ไม่มีทศนิยม, >= 10 หนึ่งตำแหน่ง, ต่ำกว่านั้นสองตำแหน่ง"""
        return f"{v:,.0f}" if v >= 100 else (f"{v:.1f}" if v >= 10 else f"{v:.2f}")

    def _unit_name(label):
        return L.get("unit_" + str(label), "") if label else ""

    def _ulabel(p):
        """🆕 (2026-10-12) สินค้า -> "30 ml · THB 8.6/ml · trial size" (ช่วงราคาต่อปริมาณ) - ไม่มีข้อมูลขนาด = ข้อความว่าง"""
        if not isinstance(p, dict):
            return ""
        unit, parts = _unit_name(p.get("unit_label")), []
        size, up = p.get("size"), p.get("unit_price")
        if unit and isinstance(size, (int, float)) and size > 0:
            parts.append(f"{round(size, 1):g} {unit}")
        if unit and isinstance(up, (int, float)) and up > 0:
            parts.append(f"{L['thb'].format(v=_unit_num(up))}/{unit}")
        if p.get("is_mini") and parts:
            parts.append(L.get("mini", ""))
        return " · ".join(x for x in parts if x)

    def _urange(t):
        """🆕 ช่วงราคาต่อปริมาณของ 1 ช่วง (ต่ำ "ไม่เกิน x" / กลาง "x-y" / สูง "ตั้งแต่ y" ต่อ มล.|ก.|ชิ้น) - ไม่มีตัวเลข = ข้อความว่าง"""
        if not isinstance(t, dict) or not isinstance(t.get("unit_to"), (int, float))                 or not isinstance(t.get("unit_from"), (int, float)):
            return ""
        u = "/" + _unit_name(t.get("unit_label"))
        lo, hi = _unit_num(t["unit_from"]), _unit_num(t["unit_to"])
        # 🆕 (2026-10-12) คำพูดแทนสัญลักษณ์ ≤ ≥ (u_upto / u_from ใน i18n.STRINGS): "ไม่เกิน 9.97 บาท/มล." / "up to THB 9.97/ml"
        if t.get("label") == "low":
            return L["u_upto"].format(v=f"{L['thb'].format(v=hi)}{u}")
        if t.get("label") == "high":
            return L["u_from"].format(v=f"{L['thb'].format(v=lo)}{u}")
        return f"{L['thb'].format(v=lo + '-' + hi)}{u}"

    def _uprice(p):
        """ราคาต่อหน่วยแบบสั้น "3.59" (ไม่มีสกุลเงิน/หน่วย - ใช้คู่กับราคาในบรรทัดเดียวกัน) ไม่มีข้อมูล = ข้อความว่าง"""
        up = p.get("unit_price") if isinstance(p, dict) else None
        return _unit_num(up) if isinstance(up, (int, float)) and up > 0 else ""

    def _uspan(u):
        """🆕 (2026-10-14) ช่วง ฿/หน่วยที่สินค้า 80% ของกลุ่มอยู่ (brand_category_data.group_ranges) -> "0.42-8.58 บาท/มล." ไม่มีข้อมูล = ว่าง"""
        if not isinstance(u, dict) or not isinstance(u.get("p10"), (int, float)) or not isinstance(u.get("p90"), (int, float)):
            return ""
        lo, hi = _unit_num(u["p10"]), _unit_num(u["p90"])
        return f"{L['thb'].format(v=lo if lo == hi else lo + '-' + hi)}/{_unit_name(u.get('unit_label'))}"

    def _uper(p):
        """🆕 (2026-10-14) สินค้า -> ราคา/ปริมาตร "THB 3.64/ml" (บาทต่อ ml/g/ชิ้น ของชิ้นนั้น) - ไม่มีข้อมูลหน่วย = ว่าง"""
        up = p.get("unit_price") if isinstance(p, dict) else None
        unit = _unit_name(p.get("unit_label")) if isinstance(p, dict) else ""
        if not (isinstance(up, (int, float)) and up > 0 and unit):
            return ""
        return f"{L['thb'].format(v=_unit_num(up))}/{unit}"

    env.filters.update(signed=_signed, num=_num, thb=_thb, ddmmyyyy=_ddmmyyyy, date_long=_date_long,
                       ulabel=_ulabel, urange=_urange, uprice=_uprice, uspan=_uspan, uper=_uper)
    # 🆕 (2026-10-19) ปีระยะสั้น/ระยะยาวของรอบที่ไม่มีผลการเติบโต (ctx.growth = None) - ค่าจาก common/horizons.py ที่เดียว
    env.globals.update(SHORT_YEAR=SHORT_YEAR, LONG_YEAR=LONG_YEAR)

    def _fitmap_svg(m, strings):
        """🆕 (2026-10-21) กราฟ "ความใกล้เทรนด์ x ยอดขาย" ของหมวด L2 ของเทรนด์ (⑰ หน้าที่ 3 ของเทรนด์) - strings = L ของเทมเพลต (มีชุดข้อความ fm_*)"""
        from fit_sales_map import render_svg

        return Markup(render_svg(m, strings)) if m else Markup("")

    env.globals["fitmap_svg"] = _fitmap_svg
    return env


def render_html(ctx, brand, charts, report_title, run_date, text_sources, generated_at=None, lang="en"):
    """ctx ต้องผ่าน i18n.localize(ctx, lang) มาแล้วสำหรับภาษาไทย (ข้อความ/ชุดคำตายตัวเป็นภาษานั้น)"""
    generated_at = generated_at or datetime.now()
    template = make_env(lang).get_template("report.html.j2")
    # 🆕 (2026-10-12) รอบที่แบ่งช่วงด้วยราคาต่อปริมาณ (⑫ tier_basis) -> ข้อความช่วงราคา/วิธีการเป็นชุด unit_i18n
    tier_basis = ((ctx or {}).get("meta") or {}).get("tier_basis")
    return template.render(ctx=ctx, brand=brand, charts=charts, report_title=report_title, run_date=run_date,
                           text_sources=text_sources, generated_at=generated_at, year=generated_at.year,
                           source_rows=source_rows((ctx or {}).get("meta"), lang),   # 🆕 2026-10-14 กล่องแหล่งที่มาของข้อมูล
                           source_docs=source_doc_groups((ctx or {}).get("meta"), lang),   # 🆕 หน้ารายการแหล่งข้อมูล (หัวข้อ + URL)
                           L=with_unit_strings(STRINGS[lang], lang, tier_basis), lang=lang)


def render_brand_html(ctx, bctx, brand, charts, report_title, run_date, generated_at=None, lang="en", cat=None):
    """⑰ รายงานแบรนด์ - ctx = trend context ที่ localize แล้ว, bctx = brand context ของภาษาเดียวกัน
    (brand_data.build_brand_context + brand_i18n.apply_th สำหรับไทย)
    🆕 (2026-10-14) cat = category context ของภาษาเดียวกัน (brand_category_data.build_category_context [+ apply_th]) - หน้าสินค้าต่อเทรนด์
    (3 กลุ่มราคาต่อปริมาณ: top 5 + สินค้าที่ดีที่สุดของแบรนด์) ที่รวมมาจาก ⑱; ไม่ส่ง = ไม่มีหน้านั้น"""
    from brand_category_i18n import trend_page_strings
    from brand_i18n import brand_strings, with_l2_strings

    generated_at = generated_at or datetime.now()
    template = make_env(lang).get_template("brand_report.html.j2")
    cat_rows = {r["rank"]: r for r in (cat or {}).get("rows") or []}
    strings = {**brand_strings(lang), **trend_page_strings(lang)}
    # 🆕 (2026-10-21) เกรดเทียบในหมวด L2 อย่างเดียว (group_basis "l2") -> ข้อความที่พูดถึงกลุ่มราคา/ชนิดสินค้าเปลี่ยนเป็น "หมวด" (ทับชุดช่วงราคาต่อปริมาณอีกชั้น)
    return template.render(ctx=ctx, b=bctx, cat=cat or {}, cat_rows=cat_rows, brand=brand, charts=charts, report_title=report_title,
                           run_date=run_date, generated_at=generated_at, year=generated_at.year,
                           L=with_l2_strings(with_unit_strings(strings, lang, (bctx or {}).get("tier_basis")), lang, (bctx or {}).get("group_basis")),
                           lang=lang)


def render_brand_category_html(ctx, bctx, brand, charts, report_title, run_date, generated_at=None, lang="en"):
    """⑱ รายงานหมวด x ระดับราคา - ctx = trend context ที่ localize แล้ว, bctx = category context ของภาษาเดียวกัน
    (brand_category_data.build_category_context + apply_th สำหรับไทย)"""
    from brand_category_i18n import category_strings

    generated_at = generated_at or datetime.now()
    template = make_env(lang).get_template("brand_category_report.html.j2")
    return template.render(ctx=ctx, b=bctx, brand=brand, charts=charts, report_title=report_title,
                           run_date=run_date, generated_at=generated_at, year=generated_at.year,
                           L=with_unit_strings(category_strings(lang), lang, (bctx or {}).get("tier_basis")), lang=lang)


def html_to_pdf(html, pdf_path):
    """พิมพ์ HTML เป็น PDF - คืนรายชื่อกล่องข้อความที่ยังล้นแม้ย่อฟอนต์ถึงขั้นต่ำแล้ว (ให้ผู้เรียกเตือน)"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 960, "height": 540})
            page.set_content(html, wait_until="load")
            page.emulate_media(media="print")
            overflow = page.evaluate("window.fitAll()")
            page.pdf(path=str(pdf_path), width=PAGE_WIDTH, height=PAGE_HEIGHT, print_background=True,
                     margin={"top": "0", "right": "0", "bottom": "0", "left": "0"}, prefer_css_page_size=True)
        finally:
            browser.close()
    return overflow
