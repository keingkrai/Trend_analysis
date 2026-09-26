# -*- coding: utf-8 -*-
"""แผนที่เทรนด์ (scatter 2 มิติ) ของรอบรันที่เลือก - เทรนด์ที่ถูกคัดเข้า Top N แล้วเท่านั้น (ไม่โชว์จุดจางของ
เทรนด์ที่ถูกตัดออก) วางตามแกน Z_Delta (อัตราการเติบโตที่พยากรณ์) กับ Stream_Count (คีย์เวิร์ดซ้ำกี่สาย - ตัวที่
ทำให้ได้โบนัส Rank Score ขั้น 6) แบ่ง 4 โซนตามเส้น Z_Delta=0 และ Stream_Count=1.5

แต่ละเทรนด์มีสีของตัวเอง (คงที่ตาม top_rank) ทั้งจุดและชื่อ ไม่มีเส้นโยงจากจุดไปชื่อ - สีที่ตรงกันบอกอยู่แล้วว่า
ชื่อไหนเป็นของจุดไหน

Usage:
    python Plot_trend_map.py                     # ถามว่าจะใช้รอบไหน
    python Plot_trend_map.py --run <ชื่อรอบ>
"""
import argparse
import colorsys
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # ไม่เปิดหน้าต่างกราฟ - บันทึกเป็นไฟล์อย่างเดียว
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# ใช้ตัวหา root/เลือกรอบ/ตั้งฟอนต์ไทยของ Plot_bump_chart.py ตรงๆ (ของเดิมที่พิสูจน์แล้ว ไม่เขียนซ้ำ)
from Plot_bump_chart import choose_run_folder, find_project_root, setup_thai_font  # noqa: E402

RANK_FILE = "phase2_rank_score_final_mode_result.json"
LONGEVITY_FILE = "phase2_longevity_cross_source_result.json"
HIGHLIGHTS_FILE = "phase3_trend_highlights_result.json"
FORECAST_FILE = "phase2_paper_social_z_delta_result.json"
MASTER_REPORT_COLS = ["cluster_id", "trend", "model", "status", "current_z", "forecast_avg_z", "z_delta",
                      "peak_month", "keywords", "context", "data_quality", "pct_months_with_data"]

# สีต่อเทรนด์ (ให้แต่ละเทรนด์มีสีของตัวเอง คงที่ทุกครั้งที่วาด อิง overall_rank ไม่ใช่ตำแหน่งในลิสต์)
# ⚠️ ในสแกตเตอร์ที่จุดไหนก็อยู่ติดจุดไหนก็ได้ (ไม่ใช่แท่ง/เส้นที่มีแค่เพื่อนบ้านติดกัน) ไม่มีชุดสีไหนรับประกันว่า
# แยกออกจากกันได้ชัดสำหรับตาบอดสีเกิน ~3 สีพร้อมกัน (ดู dataviz skill: palette.md ระบุสแกตเตอร์รับได้แค่ 3 สี
# ที่ผ่านเกณฑ์ all-pairs) - ที่นี่ยอมรับข้อจำกัดนี้เพราะทุกจุดมีชื่อเทรนด์+เลขอันดับกำกับอยู่แล้วเสมอ (สีเป็นแค่
# ตัวช่วยแยกด้วยตา ไม่ใช่ช่องทางบอกตัวตนเดียว) ใช้ tab20 ของ matplotlib (20 สี ออกแบบมาให้แยกกันด้วยตาได้มาก
# หมวดหมู่กว่าชุด 8 สีของ design system ที่เผื่อไว้สำหรับกราฟแท่ง/เส้นเท่านั้น)
_PALETTE = list(plt.cm.tab20.colors)


def _assign_colors(points):
    for p in points:
        p["color"] = _PALETTE[(p["overall_rank"] - 1) % len(_PALETTE)]


# ตำแหน่งป้ายที่ลองไล่หา (ระยะพิกเซลจากจุด) - อันแรกที่ไม่ทับป้ายอื่น/ไม่ล้นขอบกราฟจะถูกเลือก
_LABEL_OFFSETS = [(0, 18), (0, -22), (16, 8), (-16, 8), (18, -16), (-18, -16), (0, 40), (0, -46),
                  (30, 26), (-30, 26), (30, -30), (-30, -30), (0, 62), (0, -70), (48, 10), (-48, 10)]


def _marker_size(p):
    """ขนาดจุด (หน่วย points^2 ของ matplotlib scatter) - โตตาม cluster_size ใช้ค่าเดียวกันทั้งตอนวาดจุดจริง
    และตอนคำนวณระยะกันชนใน _declump (สองที่ต้องตรงกันเป๊ะ ไม่งั้นจุดใหญ่จะทับกันหลัง declump)"""
    return 70 + p["cluster_size"] * 22


def _readable_text_color(rgb, alpha, bg=(1.0, 1.0, 1.0)):
    """เลขอันดับสีขาว/เข้มในตัวจุด ต้องอ่านออกไม่ว่าจุดนั้นจะเป็นสีอะไรจาก _PALETTE และจางแค่ไหน (alpha ของเทรนด์
    ที่ไม่ถูกคัดทำให้สีที่ตาเห็นจริงอ่อนกว่าสีดิบมาก) - ผสมสีจุดกับพื้นหลังตาม alpha ก่อน แล้วค่อยวัดความสว่าง"""
    blended = tuple(alpha * c + (1 - alpha) * b for c, b in zip(rgb, bg))
    luminance = 0.299 * blended[0] + 0.587 * blended[1] + 0.114 * blended[2]
    return "white" if luminance < 0.55 else "#1a1a1a"


def _label_color(rgb, selected):
    """สีชื่อเทรนด์ - ให้เป็นเฉดเดียวกับจุดของมันเอง (hue เดียวกับ _PALETTE) แต่ปรับความสว่าง/อิ่มตัวเอง เพราะ
    บางสีใน tab20 เป็นพาสเทลอ่อนมาก เอาไปใช้เป็นสีตัวหนังสือบนพื้นขาวตรงๆ จะอ่านไม่ออก - เทรนด์ที่ถูกคัดใช้เฉด
    เข้ม/อิ่มตัวให้อ่านชัดเป็นหลัก เทรนด์ที่ถูกตัดออกใช้เฉดอ่อนกว่า (น้ำหนักสายตาใกล้เคียงสีเทาเดิม "#8d8b84"
    ที่เคยใช้ ยังดูรองจากของที่ถูกคัดอยู่)"""
    h, _, s = colorsys.rgb_to_hls(*rgb)
    if selected:
        return colorsys.hls_to_rgb(h, 0.32, max(s, 0.5))
    return colorsys.hls_to_rgb(h, 0.55, min(max(s, 0.25), 0.4))


def _read_json(path, default=None):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_trend_data(run_dir):
    """ค่าที่ใช้วาดกราฟของทุกเทรนด์ในรอบนี้ (ทั้ง 15 ตัวก่อนคัด) - 1 dict ต่อเทรนด์

    ต้องมีผล ⑥ (Rank Score) อย่างน้อย - ⑦ (current_z/forecast_avg_z), ⑪ (Top N ที่คัดแล้ว) และ Longevity
    เป็นส่วนเสริม ถ้าไฟล์ไหนไม่มีจะได้ค่า None ในฟิลด์นั้นแทน ไม่ทำให้ทั้งฟังก์ชันพัง (รอบเก่าบางรอบอาจไม่มี
    ผลลัพธ์ครบทุกขั้น)
    """
    rank_rows = _read_json(run_dir / RANK_FILE)
    if rank_rows is None:
        raise FileNotFoundError(f"ไม่พบ {RANK_FILE} ใน {run_dir} - ต้องรัน ⑥ (rank_trends.py) ก่อน")

    forecast = _read_json(run_dir / FORECAST_FILE, {}) or {}
    forecast_rows = {}
    for row in forecast.get("master_report") or []:
        d = dict(zip(MASTER_REPORT_COLS, row))
        forecast_rows[d["trend"]] = d

    longevity = _read_json(run_dir / LONGEVITY_FILE, {}) or {}
    longevity_rows = {(stream, r["Trend Name"]): r for stream, rows in longevity.items() for r in rows}

    highlights = _read_json(run_dir / HIGHLIGHTS_FILE, {}) or {}
    selected = {t["trend"]: t["top_rank"] for t in highlights.get("selected_trends", [])}
    excluded = {t["trend"]: t["reason"] for t in highlights.get("excluded_trends", [])}

    points = []
    for r in rank_rows:
        name, stream = r["Trend Name"], r["Stream"]
        fc = forecast_rows.get(name, {})
        lg = longevity_rows.get((stream, name), {})
        points.append({
            "name": name, "stream": stream,
            "overall_rank": r["Overall Rank"], "top_rank": selected.get(name),
            "selected": name in selected, "excluded_reason": excluded.get(name),
            "z_delta": r["Z_Delta"], "stream_count": r["Stream_Count"],
            "cluster_size": r["Cluster_Size"], "rank_score": r["Rank Score"],
            "current_z": fc.get("current_z"), "forecast_avg_z": fc.get("forecast_avg_z"),
            "longevity_score": lg.get("Longevity Score"), "longevity_band": lg.get("Longevity Band"),
        })
    _assign_colors(points)
    return points


def _declump(ax, fig, points):
    """ผลักจุดที่อยู่ใกล้กันมาก (ระยะพิกเซล < รัศมีจุดทั้งคู่รวมกัน + ช่องว่าง) ให้ห่างกันเล็กน้อย แล้วคืนพิกัด
    (x_plot, y_plot) ต่อจุด - ค่า x/y จริงใน point ไม่ถูกแก้ ใช้แค่ตำแหน่งแสดงผลเท่านั้น

    ระยะกันชนต้องคำนวณจากรัศมีจุดจริงของแต่ละคู่ (ไม่ใช่ค่าคงที่) เพราะขนาดจุดแปรตาม cluster_size - จุดใหญ่
    ต้องการช่องว่างมากกว่าจุดเล็ก ไม่งั้นจุดที่คลัสเตอร์ใหญ่จะยังทับกันอยู่แม้ "ถูกผลักแล้ว" (เจอบั๊กนี้จริงตอน
    เทรนด์ cluster_size=25 ทับกับตัวข้างๆ ทั้งที่ผ่าน declump ด้วยระยะคงที่ 36px ไปแล้ว)
    """
    fig.canvas.draw()
    px_per_pt = fig.dpi / 72.0
    radius = np.array([(_marker_size(p) / np.pi) ** 0.5 * px_per_pt for p in points])
    # เริ่มจาก x_plot/y_plot เดิมถ้ามีอยู่แล้ว (เช่น ผ่าน _lane_jitter มาก่อน) ไม่งั้นเริ่มจากค่าจริง x/y
    px = np.array([ax.transData.transform((p.get("x_plot", p["x"]), p.get("y_plot", p["y"])))
                   for p in points], dtype=float)
    for _ in range(200):
        moved = False
        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                min_dist = radius[i] + radius[j] + 8.0
                d = px[j] - px[i]
                dist = float(np.hypot(*d))
                if dist < min_dist:
                    moved = True
                    u = d / dist if dist > 1e-6 else np.array([1.0, 0.0])
                    push = (min_dist - dist) / 2
                    px[i] -= u * push
                    px[j] += u * push
        if not moved:
            break
    plotted = ax.transData.inverted().transform(px)
    for p, (x_plot, y_plot) in zip(points, plotted):
        p["x_plot"], p["y_plot"] = float(x_plot), float(y_plot)


def _place_labels(ax, fig, points):
    """จุด = วงกลมสีทึบ/จาง มีเลขอันดับสีขาวตรงกลาง + ป้ายชื่อเทรนด์เลี่ยงการทับกัน (ไม่มีเส้นโยง - สีป้ายชื่อ
    เป็นเฉดเดียวกับจุดของมันเองอยู่แล้ว (_label_color) จึงบอกได้เองว่าป้ายไหนเป็นของจุดไหน) - ต้องเรียก
    _declump(ax, fig, points) ก่อน"""
    renderer = fig.canvas.get_renderer()
    ax_bb = ax.get_window_extent(renderer=renderer)
    px_per_pt = fig.dpi / 72.0
    placed = []  # กันชนของป้ายชื่อ - ต้องมี "วงกลมของทุกจุด" ตั้งแต่แรก ไม่งั้นป้ายของจุดหนึ่งไปทับวงกลมของ
    # อีกจุดได้ (เจอบั๊กนี้จริง: จุดทุกจุดไม่เคยทับกันเอง เพราะ _declump ตรวจแล้ว แต่ "ป้ายชื่อ" ของจุดหนึ่ง
    # ไปวางทับ "วงกลม" ของอีกจุดที่อยู่ใกล้ๆ เพราะโค้ดเดิมกันแค่ป้ายชนป้าย ไม่ได้กันป้ายชนวงกลม)
    for p in points:
        radius = (_marker_size(p) / np.pi) ** 0.5 * px_per_pt
        cx, cy = ax.transData.transform((p["x_plot"], p["y_plot"]))
        placed.append(matplotlib.transforms.Bbox([[cx - radius, cy - radius], [cx + radius, cy + radius]]))

    for p in points:
        alpha = 0.95 if p["selected"] else 0.32
        ax.scatter(p["x_plot"], p["y_plot"], s=_marker_size(p), color=p["color"], alpha=alpha,
                   edgecolors="white", linewidths=1.3, zorder=3)
        ax.annotate(str(p["top_rank"] or p["overall_rank"]), (p["x_plot"], p["y_plot"]),
                    ha="center", va="center", fontsize=8.5, fontweight="bold",
                    color=_readable_text_color(p["color"], alpha), zorder=4)
    for p in sorted(points, key=lambda p: (not p["selected"], p["top_rank"] or p["overall_rank"])):
        short = p["name"] if len(p["name"]) <= 32 else p["name"][:31] + "…"
        if p["selected"]:
            label = f"#{p['top_rank']} {short}"
        elif p["excluded_reason"]:
            label = f"{short} (คัดออก)"
        else:
            label = short
        color = _label_color(p["color"], p["selected"])
        best = None
        for dx, dy in _LABEL_OFFSETS:
            ha = "center" if dx == 0 else ("left" if dx > 0 else "right")
            t = ax.annotate(label, (p["x_plot"], p["y_plot"]), xytext=(dx, dy), textcoords="offset points",
                            ha=ha, va="center", fontsize=8.7 if p["selected"] else 8.2, color=color, zorder=5)
            bb = t.get_window_extent(renderer=renderer).expanded(1.04, 1.18)
            inside = ax_bb.x0 <= bb.x0 and bb.x1 <= ax_bb.x1 and ax_bb.y0 <= bb.y0 and bb.y1 <= ax_bb.y1
            overlap = any(not (bb.x1 < o.x0 or bb.x0 > o.x1 or bb.y1 < o.y0 or bb.y0 > o.y1) for o in placed)
            if inside and not overlap:
                best = (t, bb)
                break
            t.remove()
        if best is None:
            t = ax.annotate(label, (p["x_plot"], p["y_plot"]), xytext=(34, 34), textcoords="offset points",
                            ha="left", va="center", fontsize=8.2, color=color, zorder=5)
            best = (t, t.get_window_extent(renderer=renderer))
        placed.append(best[1])


def _setup_layout(ax, fig, title, xlabel, ylabel):
    """ตั้ง title/label + เรียก tight_layout() **ก่อน**เรียก _declump/_place_labels เสมอ - tight_layout()
    ปรับขนาด/ตำแหน่งกรอบแกน (ax) ให้พอดีกับ title/label ซึ่งถ้าไปเรียกทีหลัง (หลังคำนวณตำแหน่งจุดเป็นพิกเซล
    ไปแล้ว) กรอบแกนจะขยับ ทำให้ระยะที่ _declump ดันจุดให้ห่างกันไว้คลาดเคลื่อนจากที่ตั้งใจ (เจอบั๊กนี้จริง -
    จุดที่ดันห่างกันแล้วกลับมาทับกันในภาพที่บันทึกจริง)"""
    ax.set_xlabel(xlabel, fontsize=10.5)
    ax.set_ylabel(ylabel, fontsize=10.5)
    ax.set_title(title, fontsize=12.5, pad=14)
    fig.tight_layout()


def _cosmetics(ax):
    """ส่วนที่ไม่กระทบขนาด/ตำแหน่งกรอบแกน (เรียกตอนไหนก็ได้ ไม่ต้องเรียกก่อน _declump)"""
    ax.grid(alpha=0.22, zorder=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _lane_jitter(points, band=0.9, max_spacing=0.13):
    """กระจายแนวตั้งเฉพาะภายในกลุ่มที่มีค่า Y เท่ากันเป๊ะ (ใช้กับแกนที่เป็นจำนวนเต็มน้อยค่า เช่น Stream_Count
    ที่มักมีแค่ 1-2 - จุดส่วนใหญ่กองอยู่ Y เดียวกัน) แกน X **ไม่ถูกแก้เลย** เพราะมีความหมายเชิงปริมาณจริง
    ต่างจาก _declump ที่ทั่วไปกว่าแต่จะขยับ X ด้วยถ้าจำเป็น ซึ่งไม่เหมาะกับกรณีนี้ที่ Y มีแค่ไม่กี่ค่าให้กระจาย"""
    from collections import defaultdict
    lanes = defaultdict(list)
    for p in points:
        lanes[p["y"]].append(p)
    for group in lanes.values():
        group.sort(key=lambda p: p["x"])
        n = len(group)
        spacing = min(max_spacing, band / (n - 1)) if n > 1 else 0
        for i, p in enumerate(group):
            p["x_plot"] = p["x"]
            p["y_plot"] = p["y"] + (i - (n - 1) / 2) * spacing


def plot_top10_zdelta_streamcount(points, run_name, outputs_dir):
    """X = Z_Delta, Y = Stream_Count - ตัวที่ทำให้ Rank Score ได้โบนัส +10%/ช่องทางเพิ่ม (ขั้น 6)
    รับเฉพาะเทรนด์ที่ถูกคัดเข้า Top N แล้ว (points ต้อง filter selected มาก่อนเรียกฟังก์ชันนี้)"""
    for p in points:
        p["x"], p["y"] = p["z_delta"], p["stream_count"]

    fig, ax = plt.subplots(figsize=(12.5, 8.5), dpi=150)
    xs = [p["x"] for p in points]
    ax.set_xlim(min(0.05, min(xs) - 0.08), max(xs) + 0.12)
    ax.set_yticks(sorted({p["y"] for p in points}))

    _lane_jitter(points)                    # กระจายตามความหมาย (Stream_Count จริง) ก่อน
    # ตั้ง ylim ให้กว้างพอไว้ก่อนครั้งเดียว (ไม่ปรับซ้ำหลัง _declump) เพราะ _declump คำนวณระยะพิกเซลจาก
    # ylim ตอนนั้น - ถ้าไปขยาย ylim อีกทีหลังคำนวณเสร็จ ระยะที่ดันไว้จะแคบลงกว่าที่ตั้งใจ (สัดส่วนพิกเซล/
    # หน่วยข้อมูลเปลี่ยน) จุดจะกลับมาใกล้ชิดกว่าที่ควร
    ax.set_ylim(min(p["y_plot"] for p in points) - 0.6, max(p["y_plot"] for p in points) + 0.6)

    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    y_div = 1.5  # เส้นแบ่ง Stream_Count=1 (ยังไม่ได้โบนัส) กับ >=2 (เริ่มได้โบนัส +10%/ช่องทาง ขั้น 6)
    if xlim[0] < 0 < xlim[1]:
        ax.axvspan(0, xlim[1], color="#fdf3ec", zorder=0)
    ax.axvline(0, color="#c9c7c0", lw=1, ls="--", zorder=1)
    if ylim[0] < y_div < ylim[1]:
        ax.axhline(y_div, color="#c9c7c0", lw=1, ls="--", zorder=1)

    _setup_layout(ax, fig,
                 f"{len(points)} เทรนด์ — Z_Delta vs Stream_Count\n"
                 f"รอบ {run_name}",
                 "Z_Delta — อัตราการเติบโตที่พยากรณ์",
                 "Stream_Count — จำนวนช่องทางที่เจอคีย์เวิร์ดของเทรนด์นี้ซ้ำกัน")
    _declump(ax, fig, points)               # แล้วดันเพิ่มเฉพาะคู่ที่จุดยังทับกันจริง (ตามขนาดจุดจริง)
    _place_labels(ax, fig, points)

    qs = dict(fontsize=10, style="italic", color="#8d8b84")
    ax.text(xlim[0] + 0.02, ylim[1] - 0.03, "หลายช่องทาง\n(แต่ไม่โตแล้ว)", ha="left", va="top", **qs)
    ax.text(xlim[1] - 0.02, ylim[1] - 0.03, "หลายช่องทาง\n(และกำลังโต)", ha="right", va="top", **qs)
    ax.text(xlim[0] + 0.02, ylim[0] + 0.02, "ช่องทางเดียวและนิ่ง\n(ไม่มีอะไรเกิด)", ha="left", va="bottom", **qs)
    ax.text(xlim[1] - 0.02, ylim[0] + 0.02, "โตเดี่ยว\n(ยังไม่มีช่องทางอื่น)", ha="right", va="bottom", **qs)
    _cosmetics(ax)
    out = outputs_dir / "trend_top10_zdelta_streamcount.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def main(run_name=None, outputs_dir=None):
    """run_name: ชื่อโฟลเดอร์รอบ (None = ถามตอนเริ่ม) / outputs_dir: ที่บันทึกผล (None = โฟลเดอร์รอบที่เลือก)"""
    project_root = find_project_root()
    print(f"PROJECT_ROOT = {project_root}")
    run_folder = choose_run_folder(project_root / "output", run_name)
    print(f"▶ รอบรัน: {run_folder.name}")
    outputs_dir = Path(outputs_dir) if outputs_dir else run_folder
    outputs_dir.mkdir(parents=True, exist_ok=True)

    setup_thai_font()
    points = load_trend_data(run_folder)
    points = [p for p in points if p["selected"]]
    if not points:
        raise ValueError(f"รอบ {run_folder.name} ไม่มีเทรนด์ที่ถูกคัดเข้า Top N เลย "
                         f"(ไม่พบ {HIGHLIGHTS_FILE} หรือไฟล์ว่าง)")
    print(f"โหลด {len(points)} เทรนด์ (ถูกคัดเข้า Top N ทั้งหมด)")

    out = plot_top10_zdelta_streamcount(points, run_folder.name, outputs_dir)
    print(f"บันทึกแล้ว: {out}")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="แผนที่เทรนด์ (scatter 2 มิติ) Z_Delta vs Stream_Count ของ Top N ที่คัดแล้ว")
    parser.add_argument("--run", default=None, help="ชื่อโฟลเดอร์รอบใน main/output (ไม่ใส่ = ขึ้นรายชื่อให้เลือก)")
    args = parser.parse_args()
    try:
        main(run_name=args.run)
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(f"❌ วาดแผนที่เทรนด์ไม่ได้: {e}")
