# -*- coding: utf-8 -*-
"""
⑰ หน้าที่ 3 ของเทรนด์ — แผนที่ "ความใกล้เทรนด์ x ยอดขาย" (🆕 2026-10-21 เจ้าของงานสั่ง; 🆕 ในวันเดียวกันเปลี่ยนกลุ่มเทียบเป็นหมวด L2 อย่างเดียว
แล้วเอาแถบ "ไม่มีข้อมูลยอดขาย" และตัวเลขจำนวนในช่องออก)

1 กราฟต่อ 1 เทรนด์ แกน x = อันดับความใกล้เทรนด์ของสินค้าในหมวด L2 แบ่งเป็น 4 ช่องกว้างเท่ากันตามเส้นเกรด (top 1/5/20% ของหมวด ยิ่งขวายิ่งใกล้)
แกน y = เปอร์เซ็นไทล์ยอดขาย Konvy เทียบสินค้าในหมวดเดียวกัน แบ่งเป็น 3 แถวตามเส้นขายดี/ขายช้า (บน = ขายดี) พื้นช่อง = เกรดสุดท้ายหลังยอดขายปรับ
(brand_data.adjust_level) - ช่องไม่มีตัวเลขจำนวน แสดงแต่จุดสินค้าของแบรนด์ (สินค้าที่ไม่มีข้อมูลยอดขายถูกวางไว้แถวปานกลางตั้งแต่ชั้นข้อมูล)

โมดูลนี้เป็นฟังก์ชันล้วน (ไม่แตะไฟล์/เครือข่าย): brand_category_data._fit_sales_map สร้างข้อมูลจุด -> render_svg() วาดเป็น SVG
(เทมเพลตเรียกผ่านตัวแปรโกลบอล fitmap_svg ของ render.make_env) ข้อความในกราฟมาจากชุดข้อความ fm_* ของ brand_i18n (ส่ง L เข้ามา)
ตำแหน่งจุดในช่องเป็นค่าประมาณ (จุดที่ทับกันถูกเขี่ยออกจากกันเล็กน้อย) - เส้นแบ่งช่องเท่านั้นที่เป็นเส้นตัดจริง
"""
import math
from html import escape

from brand_data import FIT_LEVELS, adjust_level

ROW_ORDER = ("strong", "steady", "slow")
COL = {"below_average": 0, "average": 1, "good": 2, "excellent": 3}   # ซ้ายไปขวา = ใกล้เทรนด์ขึ้น
FIT_COLOR = {"excellent": "#1c5cab", "good": "#3987e5", "average": "#86b6ef", "below_average": "#b4b2a9"}
FIT_TINT = {"excellent": "rgba(28,92,171,.24)", "good": "rgba(57,135,229,.17)", "average": "rgba(134,182,239,.24)",
            "below_average": "#f1f0ed"}


class Geo:
    """ขนาดของกราฟ: w กว้างรวม, gl ช่องว่างซ้ายสำหรับชื่อแถว, hdr ความสูงหัวคอลัมน์, row_h ความสูงแต่ละแถว, cap_h ที่เว้นท้ายกราฟสำหรับชื่อแกน x,
    dot / hl รัศมีจุดทั่วไป / จุดไฮไลต์, css = คลาสเสริมของ <svg>"""

    def __init__(self, w, gl, hdr, row_h, cap_h, dot, hl, css=""):
        self.w, self.gl, self.hdr, self.dot, self.hl, self.css = w, gl, hdr, dot, hl, css
        self.pw = w - gl - 2
        self.cw = self.pw / 4
        self.row_y, y = {}, hdr
        for r in ROW_ORDER:
            self.row_y[r] = (y, y + row_h[r])
            y += row_h[r]
        self.plot_bottom = y
        self.h = y + cap_h

    def cell_box(self, state, fit):
        """ขอบของช่อง (x0, x1, y0, y1) ที่จุดต้องอยู่ข้างใน (เว้นขอบ 2px)"""
        x0 = self.gl + COL[fit] * self.cw
        y0, y1 = self.row_y[state]
        return x0 + 2, x0 + self.cw - 2, y0 + 2, y1 - 2


BIG = Geo(560, 66, 32, {"strong": 88, "steady": 104, "slow": 64}, 24, 4.8, 8.4, css="fm-big")


def _spread(dots):
    """เขี่ยจุดที่ทับกันออกเล็กน้อย จุดไม่หลุดออกนอกช่องของตัวเอง"""
    for _ in range(80):
        moved = False
        for i, a in enumerate(dots):
            for b in dots[i + 1:]:
                dx, dy = b["x"] - a["x"], b["y"] - a["y"]
                dist = math.hypot(dx, dy) or 0.01
                need = a["r"] + b["r"] + 0.6
                if dist >= need:
                    continue
                push = (need - dist) / 2
                ux, uy = (dx / dist, dy / dist) if dist >= 0.02 else (1.0, 0.0)
                a["x"] -= ux * push
                a["y"] -= uy * push
                b["x"] += ux * push
                b["y"] += uy * push
                moved = True
        for a in dots:
            x0, x1, y0, y1 = a["box"]
            a["x"] = min(max(a["x"], x0 + a["r"]), x1 - a["r"])
            a["y"] = min(max(a["y"], y0 + a["r"]), y1 - a["r"])
        if not moved:
            break


def render_svg(m, L, geo=BIG):
    """ข้อมูลกราฟ (brand_category_data._fit_sales_map) + ข้อความของภาษานั้น (L) -> สตริง SVG"""
    fit_cut, scfg = m["cuts"], m["sales"]
    dots = []
    for d in m["dots"]:
        y0, y1 = geo.row_y[d["state"]]
        dots.append({**d, "x": geo.gl + COL[d["fit"]] * geo.cw + 3 + d["fx"] * (geo.cw - 6), "y": y1 - 3 - d["fy"] * (y1 - y0 - 6),
                     "r": geo.hl if d.get("letter") else geo.dot, "box": geo.cell_box(d["state"], d["fit"])})
    _spread(dots)

    sub = {"excellent": L["fm_x_first"].format(p=fit_cut["excellent"]),
           "good": L["fm_x_mid"].format(a=fit_cut["excellent"], b=fit_cut["good"]),
           "average": L["fm_x_mid"].format(a=fit_cut["good"], b=fit_cut["average"]),
           "below_average": L["fm_x_last"].format(p=fit_cut["average"])}
    row_sub = {"strong": L["fm_y_strong_sub"].format(p=scfg["strong_top_pct"]), "steady": L["fm_y_steady_sub"],
               "slow": L["fm_y_slow_sub"].format(p=scfg["slow_bottom_pct"])}
    cls = ("fm-svg " + geo.css).strip()
    svg = [f'<svg class="{cls}" viewBox="0 0 {geo.w} {geo.h}" width="{geo.w}" height="{geo.h}" xmlns="http://www.w3.org/2000/svg">']
    for fit in FIT_LEVELS:   # หัวคอลัมน์: ชื่อระดับ + ช่วง % พร้อมแถบสีของระดับ
        x0 = geo.gl + COL[fit] * geo.cw
        svg.append(f'<rect x="{x0 + 1}" y="{geo.hdr - 4}" width="{geo.cw - 2}" height="3" fill="{FIT_COLOR[fit]}"/>')
        svg.append(f'<text x="{x0 + 4}" y="13" class="ch">{escape(L[fit])}</text>')
        svg.append(f'<text x="{x0 + 4}" y="25" class="cs">{escape(sub[fit])}</text>')
    for row in ROW_ORDER:
        y0, y1 = geo.row_y[row]
        for fit in FIT_LEVELS:
            x0 = geo.gl + COL[fit] * geo.cw
            svg.append(f'<rect x="{x0 + 1}" y="{y0 + 1}" width="{geo.cw - 2}" height="{y1 - y0 - 2}" fill="{FIT_TINT[adjust_level(fit, row)]}"/>')
        ym = (y0 + y1) / 2
        svg.append(f'<text x="{geo.gl - 5}" y="{ym - 1}" class="rl" text-anchor="end">{escape(L["fm_y_" + row])}</text>')
        svg.append(f'<text x="{geo.gl - 5}" y="{ym + 10.5}" class="rs" text-anchor="end">{escape(row_sub[row])}</text>')
    svg.append(f'<text x="{geo.gl + geo.pw / 2}" y="{geo.h - 8}" class="ax" text-anchor="middle">{escape(L["fm_axis_x"])}</text>')
    for i, part in enumerate((L["fm_axis_y"].split("|") + [""])[:2]):   # ชื่อแกน y 2 บรรทัดที่มุมซ้ายบน (ไม่หมุน - ภาษาไทยหมุนแล้วอ่านยาก)
        svg.append(f'<text x="2" y="{13 + 12 * i}" class="ax">{escape(part)}</text>')
    # จุดทั่วไปก่อน แล้วจุดที่ไฮไลต์ (A/B/C) ไว้บนสุด
    for d in sorted(dots, key=lambda q: q.get("letter") is not None):
        cx, cy, r = f'{d["x"]:.1f}', f'{d["y"]:.1f}', d["r"]
        if d.get("letter"):
            svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" class="dm" stroke="#ffffff" stroke-width="1.4"/>')
            svg.append(f'<text x="{cx}" y="{d["y"] + 3.6:.1f}" class="dl" text-anchor="middle">{d["letter"]}</text>')
        else:
            svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" class="dm" fill-opacity=".82" stroke="#ffffff" stroke-width=".8"/>')
    svg.append("</svg>")
    return "\n".join(svg)
