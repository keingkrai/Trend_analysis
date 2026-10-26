# -*- coding: utf-8 -*-
"""
⑲ รายงานส่วนแบ่งตลาด — กราฟส่วนแบ่งรายปีของแบรนด์ในหน้าแบรนด์ (matplotlib -> SVG)

สไตล์เดียวกับกราฟของ ⑯ (phase6_pdf_report/charts.py): ซีรีส์เดียวสีน้ำเงิน ไม่มีกล่อง legend เส้นกริดจาง
สีกลางเสมอ - ไม่ใช้เขียว/แดงบอกขึ้นลง (รายงานไม่ตัดสินว่าแบรนด์ไหนชนะ/แพ้) ป้ายตัวเลขเฉพาะปีตั้งต้นกับปีล่าสุด
ปีที่แบรนด์ยังไม่มีชื่อในข้อมูล (None) ไม่วาด
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "phase6_pdf_report"))

from charts import GRID, SERIES, TEXT_SECONDARY, plt  # noqa: E402  (ตั้ง rcParams ฟอนต์ไทย/อังกฤษชุดเดียวกับ ⑯)

BASE_SHADE = "#efeeea"


def share_chart_svg(series, base_year, last_year, width_px=250, height_px=102, ylabel="%"):
    """{"2016": 1.0, ...} -> SVG string หรือ None (มีข้อมูลน้อยกว่า 2 ปี) - ขนาดตั้งต้นพอดีช่องกราฟของหน้าแบรนด์ 3 แบรนด์ต่อหน้า"""
    small = height_px < 150
    fs_label, fs_tick = (8, 7) if small else (9, 8)
    pts = sorted((int(y), v) for y, v in (series or {}).items() if v is not None)
    if len(pts) < 2:
        return None
    years, values = [p[0] for p in pts], [p[1] for p in pts]
    fig, ax = plt.subplots(figsize=(width_px / 96, height_px / 96), dpi=96)
    ax.axvspan(base_year - 0.5, last_year + 0.5, color=BASE_SHADE, zorder=0, lw=0)
    ax.plot(years, values, color=SERIES, lw=2, marker="o", ms=3.5, zorder=3)
    label_box = {"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.9}
    for y in (base_year, last_year):
        if y in years:
            v = values[years.index(y)]
            ax.scatter([y], [v], s=46, color=SERIES, edgecolors="white", linewidths=2, zorder=4)
            ax.annotate(f"{v:.1f}%", (y, v), xytext=(0, 5), textcoords="offset points", ha="center", va="bottom",
                        fontsize=fs_label, fontweight="bold", color=SERIES, bbox=label_box, zorder=5)
    ax.set_ylim(0, max(values) * (1.5 if small else 1.35))
    ax.set_xlim(min(years) - 0.5, max(years) + 0.5)
    ax.set_xticks(years)
    # กราฟย่อ (3 แบรนด์ต่อหน้า): ป้ายแค่ปีแรก / ปีตั้งต้น / ปีล่าสุด - ใส่ปีคู่ด้วยแล้ว "2018 2019" ชนกัน
    keep = {years[0], base_year, last_year}
    ax.set_xticklabels([str(y) if y in keep or (not small and y % 2 == 0) else "" for y in years])
    ax.set_ylabel(ylabel, fontsize=fs_tick, color=TEXT_SECONDARY)
    ax.tick_params(labelsize=fs_tick, length=0)
    ax.locator_params(axis="y", nbins=3 if small else 5)
    ax.grid(axis="y", color=GRID, lw=1)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    fig.tight_layout(pad=0.4)
    buf = io.StringIO()
    fig.savefig(buf, format="svg", transparent=True)
    plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.find("<svg"):]
