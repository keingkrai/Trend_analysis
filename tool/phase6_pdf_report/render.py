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

from i18n import STRINGS, date_long

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
    env.filters.update(signed=_signed, num=_num, thb=_thb, ddmmyyyy=_ddmmyyyy, date_long=_date_long)
    return env


def render_html(ctx, brand, charts, report_title, run_date, text_sources, generated_at=None, lang="en"):
    """ctx ต้องผ่าน i18n.localize(ctx, lang) มาแล้วสำหรับภาษาไทย (ข้อความ/ชุดคำตายตัวเป็นภาษานั้น)"""
    generated_at = generated_at or datetime.now()
    template = make_env(lang).get_template("report.html.j2")
    return template.render(ctx=ctx, brand=brand, charts=charts, report_title=report_title, run_date=run_date,
                           text_sources=text_sources, generated_at=generated_at, year=generated_at.year,
                           L=STRINGS[lang], lang=lang)


def render_brand_html(ctx, bctx, brand, charts, report_title, run_date, generated_at=None, lang="en"):
    """⑰ รายงานแบรนด์ - ctx = trend context ที่ localize แล้ว, bctx = brand context ของภาษาเดียวกัน
    (brand_data.build_brand_context + brand_i18n.apply_th สำหรับไทย)"""
    from brand_i18n import brand_strings

    generated_at = generated_at or datetime.now()
    template = make_env(lang).get_template("brand_report.html.j2")
    return template.render(ctx=ctx, b=bctx, brand=brand, charts=charts, report_title=report_title,
                           run_date=run_date, generated_at=generated_at, year=generated_at.year,
                           L=brand_strings(lang), lang=lang)


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
