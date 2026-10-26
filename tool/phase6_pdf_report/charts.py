# -*- coding: utf-8 -*-
"""
⑯ PDF Report — กราฟพยากรณ์ต่อเทรนด์ (matplotlib -> SVG)

ส่งออกเป็น SVG (เวกเตอร์ + ข้อความยังเป็นตัวอักษร) ไม่ใช่ PNG - คมทุกระดับซูมใน PDF และใช้ฟอนต์เดียวกับหน้ารายงาน
กราฟแท่ง Momentum ของหน้า Market Overview ทำเป็น HTML/CSS ในเทมเพลตเลย (ไม่ต้องใช้ matplotlib)

สี/เส้นตาม dataviz skill: ซีรีส์เดียว = ไม่มีกล่อง legend (ป้ายกำกับตรงเส้นแทน), เส้น 2px, จุดปลาย >= 8px พร้อมวงขาว,
เส้นกริดบาง 1px สีจาง, ข้อความใช้สีข้อความ ไม่ใช้สีของซีรีส์
"""
import io

import matplotlib

matplotlib.use("Agg")  # ไม่เปิดหน้าต่างกราฟ
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SERIES = "#2a78d6"       # categorical slot 1 (blue) ของ palette อ้างอิงใน dataviz skill
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e1e0d9"
PREV_SHADE, PREV_INK = "#efeeea", "#6b6a66"     # 12 เดือนก่อนหน้า (เทียบ)
LAST_SHADE, LAST_INK = "#e1ecfa", "#1c5cab"     # 12 เดือนล่าสุด

plt.rcParams.update({
    # Leelawadee UI เป็นฟอนต์สำรองของอักษรไทย (ฉบับภาษาไทย) - matplotlib ไล่หา glyph ตามลำดับรายการนี้
    "font.family": ["Segoe UI", "Calibri", "Leelawadee UI", "Tahoma", "DejaVu Sans"],
    "svg.fonttype": "none",  # เก็บข้อความเป็นตัวอักษรใน SVG ให้เบราว์เซอร์วาดด้วยฟอนต์ระบบ
    "axes.edgecolor": GRID,
    "axes.labelcolor": TEXT_SECONDARY,
    "xtick.color": TEXT_SECONDARY,
    "ytick.color": TEXT_SECONDARY,
})


# ข้อความในกราฟต่อภาษา (ชื่อเทรนด์คงเป็นภาษาอังกฤษทั้ง 2 ฉบับ - ดู i18n.py)
CHART_TEXT = {
    "en": {"y_index": "Search interest (0-100)", "prev12": "Previous year", "last12": "Last 12 months",
           "year_n": "Year {n}", "avg": "avg {v}", "na": "n/a"},
    "th": {"y_index": "ความสนใจการค้นหา (0-100)", "prev12": "ปีก่อนหน้า", "last12": "12 เดือนล่าสุด",
           "year_n": "ปีที่ {n}", "avg": "เฉลี่ย {v}", "na": "ไม่มีข้อมูล"},
}
FC_SHADE, FC_INK = "#fbe6d8", "#b54a1c"          # ส่วนคาดการณ์ (แถบ 80% + เส้นระดับที่คาด)
SHOW_HISTORY_MONTHS = 36                          # ย้อนหลัง 3 ปี + คาดการณ์ 5 ปี (🆕 2026-10-02 เดิม 3 ปี) ช่วงละ 12 เดือนยังพอใส่ป้าย
# 🆕 (2026-10-02) แถบ 80% ของปีไกลกว้างมาก (ปีที่ 5 ขอบบน +131%) - แกนตั้งอิงข้อมูลจริง/ระดับที่คาด ไม่อิงขอบแถบ ส่วนเกินถูกตัด
# ที่ขอบบน (ไม่งั้นกราฟอดีตถูกบีบจนแบน) ป้าย % อยู่เหนือเส้นระดับที่คาดแทนเหนือแถบ
Y_HEADROOM = 1.45


YOY_BAR, YOY_INK = "#d3d1c7", "#6b6a66"          # แท่ง YoY + ตัวเลขใต้แกน (สีเทา = เทียบปีก่อนหน้า) - คู่กับ legend ในหน้าเทรนด์


def growth_chart_svg(cagr, yoy, width_px=536, height_px=188, lang="en"):
    """🆕 (2026-10-19) กราฟพยากรณ์ในหน้ารายเทรนด์ (แบบ E ที่เจ้าของงานเลือก แทนกราฟประวัติ + แถบ 80% - history_chart_svg ยังใช้ในหน้าวิธีการ):
    เส้นสีน้ำเงิน = อัตราเติบโตเฉลี่ยต่อปีแบบทบต้น (CAGR) ของปีที่ 1-5 เทียบ 12 เดือนล่าสุด (ตัวเลขเหนือจุด)
    แท่งเทา = % เปลี่ยนเทียบปีก่อนหน้า (YoY) ของแต่ละปี (ตัวเลขใต้แกนบรรทัดที่ 2) - ปีที่ 1 เทียบ 12 เดือนล่าสุด จึงเท่ากับ CAGR
    cagr / yoy = list ต่อปี (None = ไม่มีค่า) · คืน SVG string หรือ None ถ้าไม่มีค่า CAGR สักปี
    ตัวหนังสือในกราฟไม่ใช้คำศัพท์ - legend ในหน้า (HTML) อธิบายด้วยสีน้ำเงิน/เทา"""
    if not cagr or not any(v is not None for v in cagr):
        return None
    txt = CHART_TEXT[lang]
    n = len(cagr)
    xs = np.arange(1, n + 1)
    yoy = (list(yoy or []) + [None] * n)[:n]
    values = [v for v in list(cagr) + yoy if v is not None]
    lo, hi = min(0.0, min(values)), max(values)
    span = (hi - lo) or 1.0

    fig, ax = plt.subplots(figsize=(width_px / 96, height_px / 96), dpi=96)
    label_box = {"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.9}
    for x, v in zip(xs, yoy):
        if v is not None:
            ax.bar(x, v, width=0.46, color=YOY_BAR, zorder=2, lw=0)
    pts = [(x, v) for x, v in zip(xs, cagr) if v is not None]
    ax.plot([p[0] for p in pts], [p[1] for p in pts], color=SERIES, lw=2, solid_capstyle="round", zorder=4)
    ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=40, color=SERIES, edgecolors="white", linewidths=1.5, zorder=5)
    for x, v in pts:
        ax.annotate(f"{v:+.0f}%", (x, v), xytext=(0, 7), textcoords="offset points", ha="center", va="bottom",
                    fontsize=9, fontweight="bold", color=LAST_INK, bbox=label_box, zorder=6)
    if lo < 0:
        ax.axhline(0, color="#b4b2a9", lw=1, zorder=3)

    ax.set_ylim(lo - (span * 0.04 if lo < 0 else 0), hi + span * 0.22)
    ax.set_xlim(0.45, n + 0.55)
    ax.set_xticks([])
    ax.tick_params(axis="y", labelsize=8, length=0)
    ax.yaxis.set_major_formatter(lambda v, _pos: f"{v:.0f}%")
    ax.grid(axis="y", color=GRID, lw=1)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    for x, v in zip(xs, yoy):       # แถวใต้แกน: ชื่อปี + ตัวเลข YoY สีเทา (ตรงกับสีแท่ง)
        ax.text(x, -0.05, txt["year_n"].format(n=int(x)), transform=ax.get_xaxis_transform(), ha="center", va="top",
                fontsize=8.5, fontweight="bold", color=TEXT_SECONDARY)
        ax.text(x, -0.17, f"{v:+.0f}%" if v is not None else txt["na"], transform=ax.get_xaxis_transform(), ha="center",
                va="top", fontsize=9, color=YOY_INK)
    fig.subplots_adjust(left=0.075, right=0.99, top=0.96, bottom=0.25)

    buf = io.StringIO()
    fig.savefig(buf, format="svg", transparent=True)
    plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.find("<svg"):]


def history_chart_svg(history, width_px=536, height_px=188, lang="en"):
    """🆕 (2026-09-30 แทนกราฟพยากรณ์ z-score ของ ⑦) ดัชนีการค้นหาจริงรายเดือนของเทรนด์ (ค่าเฉลี่ยคีย์เวิร์ด ผล ⑥ growth)
    ย้อนหลัง 3 ปี แรเงาปีก่อนหน้ากับ 12 เดือนล่าสุดพร้อมเส้นค่าเฉลี่ย แล้วต่อด้วยส่วนคาดการณ์ทุกปีที่มี (5 ปี) (ถ้ามี
    history["forecast"] จาก growth_score.expected_levels): เส้นประ = ค่ารายเดือนที่คาด (ระดับรายปี x จังหวะฤดูกาล),
    เส้นทึบสั้น = ค่าเฉลี่ยรายปีที่คาด, แถบ = ช่วงที่ครอบคลุมค่าเฉลี่ยรายปีจริง 80% ใน backtest, ป้าย % = เทียบค่าเฉลี่ย
    12 เดือนล่าสุด
    history = {"months": ["2021-09", ...], "values": [...], "forecast": {...} | None}
    คืน SVG string หรือ None ถ้าข้อมูลไม่ถึง 24 เดือน"""
    if not history or len(history.get("values") or []) < 24:
        return None
    txt = CHART_TEXT[lang]
    dates = pd.to_datetime([f"{m}-01" for m in history["months"]])
    values = np.asarray(history["values"], dtype=float)
    prev, last = values[-24:-12], values[-12:]
    fc = history.get("forecast") or {}
    shown = slice(-SHOW_HISTORY_MONTHS, None)

    fig, ax = plt.subplots(figsize=(width_px / 96, height_px / 96), dpi=96)
    half = np.timedelta64(15, "D")
    label_box = {"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.9}

    def header(start, end, label, ink):
        ax.text(start + (end - start) / 2, 0.985, label, transform=ax.get_xaxis_transform(), ha="center", va="top",
                fontsize=7.5, fontweight="bold", color=ink)

    for window, win_dates, shade, ink, label in ((prev, dates[-24:-12], PREV_SHADE, PREV_INK, txt["prev12"]),
                                                 (last, dates[-12:], LAST_SHADE, LAST_INK, txt["last12"])):
        start, end = win_dates[0] - half, win_dates[-1] + half
        ax.axvspan(start, end, color=shade, zorder=0, lw=0)
        header(start, end, label, ink)
        ax.hlines(window.mean(), start, end, colors=ink, lw=2.5, zorder=4)
        ax.annotate(txt["avg"].format(v=f"{window.mean():.0f}"), (start + (end - start) / 2, window.mean()),
                    xytext=(0, 4), textcoords="offset points", ha="center", va="bottom", fontsize=8.5,
                    fontweight="bold", color=ink, bbox=label_box, zorder=5)
    ax.plot(dates[shown], values[shown], color=SERIES, lw=2, solid_capstyle="round", zorder=3)
    ax.scatter([dates[-1]], [values[-1]], s=42, color=SERIES, edgecolors="white", linewidths=2, zorder=4)

    x_end = dates[-1] + np.timedelta64(60, "D")
    top = values[shown].max()
    for i, level in enumerate(fc.get("levels") or []):
        first = dates[-1] + pd.DateOffset(months=12 * i + 1)
        start, end = first - half, first + pd.DateOffset(months=11) + half
        low, high, pct = fc["low"][i], fc["high"][i], fc["change_pct"][i]
        ax.fill_between([start, end], [low, low], [high, high], color=FC_SHADE, zorder=1, lw=0)
        ax.hlines(level, start, end, colors=FC_INK, lw=2.5, zorder=4)
        header(start, end, txt["year_n"].format(n=i + 1), FC_INK)
        if pct is not None and pct > -100:
            # 🆕 (2026-10-14) ตัวเลขเหนือแท่ง = CAGR (เฉลี่ยต่อปีแบบทบต้นนับจาก 12 เดือนล่าสุดถึงปีที่ i + 1) ไม่ใช่ % สะสม
            pct = ((1 + pct / 100) ** (1 / (i + 1)) - 1) * 100
            ax.annotate(f"{pct:+.0f}%", (start + (end - start) / 2, level), xytext=(0, 4), textcoords="offset points",
                        ha="center", va="bottom", fontsize=8.5, fontweight="bold", color=FC_INK, bbox=label_box, zorder=5)
        x_end, top = end, max(top, level)
    monthly = fc.get("monthly") or {}
    if monthly.get("values"):
        # เส้นคลื่นรายเดือนต่อจากจุดข้อมูลจริงล่าสุด (แบบเดียวกับเส้นพยากรณ์เดิม - เส้นประ)
        fc_dates = [dates[-1]] + list(pd.to_datetime([f"{m}-01" for m in monthly["months"]]))
        fc_values = [values[-1]] + list(monthly["values"])
        ax.plot(fc_dates, fc_values, color=FC_INK, lw=1.5, ls=(0, (3, 2)), zorder=3)
        top = max(top, max(monthly["values"]))

    ax.set_ylim(bottom=0, top=max(top * Y_HEADROOM, 1))
    ax.set_xlim(dates[shown][0] - half, x_end)
    ax.set_ylabel(txt["y_index"], fontsize=8)
    ax.tick_params(labelsize=8, length=0)
    ax.grid(axis="y", color=GRID, lw=1)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    fig.tight_layout(pad=0.4)

    buf = io.StringIO()
    fig.savefig(buf, format="svg", transparent=True)
    plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.find("<svg"):]  # ตัด XML prolog/DOCTYPE ออก - ฝังเป็น data URI ได้เลย
