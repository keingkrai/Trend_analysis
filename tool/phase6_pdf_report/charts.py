# -*- coding: utf-8 -*-
"""
⑯ PDF Report — กราฟพยากรณ์ต่อเทรนด์ (matplotlib -> SVG)

ส่งออกเป็น SVG (เวกเตอร์ + ข้อความยังเป็นตัวอักษร) ไม่ใช่ PNG - คมทุกระดับซูมใน PDF และใช้ฟอนต์เดียวกับหน้ารายงาน
กราฟแท่ง Momentum ของหน้า Market Overview ทำเป็น HTML/CSS ในเทมเพลตเลย (ไม่ต้องใช้ matplotlib)

สี/เส้นตาม dataviz skill: ซีรีส์เดียว = ไม่มีกล่อง legend (ป้ายกำกับตรงเส้นแทน), เส้น 2px, จุดปลาย >= 8px พร้อมวงขาว,
เส้นกริดบาง 1px สีจาง, ข้อความใช้สีข้อความ ไม่ใช้สีของซีรีส์
"""
import colorsys
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
FORECAST_BAND = "#f3f2ef"
HISTORY_FROM = "2021-01-01"  # ย้อนหลังแค่ ~5 ปี - ข้อมูล Google Trends ตั้งแต่ 2004 บีบช่วงพยากรณ์จนอ่านไม่ออก

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
    "en": {"now": "Now", "forecast_avg": "Forecast avg", "forecast": "Forecast", "y_forecast": "Search interest (z-score)",
           "map_x": "Z_Delta - forecast growth (higher = faster expected growth)", "map_y": "Sources confirming the trend",
           "zone_tl": "Multiple sources\n(momentum fading)", "zone_tr": "Multiple sources\n& growing",
           "zone_bl": "Single source\n& flat", "zone_br": "Growing,\nsingle source",
           "bump_y": "Rank within top {n} (1 = highest interest)", "na": "n/a"},
    "th": {"now": "ปัจจุบัน", "forecast_avg": "ค่าเฉลี่ยพยากรณ์", "forecast": "ช่วงพยากรณ์",
           "y_forecast": "ความสนใจการค้นหา (z-score)",
           "map_x": "Z_Delta - การเติบโตที่พยากรณ์ (ยิ่งสูง = คาดว่าโตเร็วกว่า)", "map_y": "จำนวนแหล่งที่ยืนยันเทรนด์",
           "zone_tl": "หลายแหล่ง\n(แรงส่งเริ่มแผ่ว)", "zone_tr": "หลายแหล่ง\nและกำลังโต",
           "zone_bl": "แหล่งเดียว\nและทรงตัว", "zone_br": "กำลังโต\nแต่แหล่งเดียว",
           "bump_y": "อันดับใน {n} อันดับต้น (1 = สนใจสูงสุด)", "na": "ไม่มีข้อมูล"},
}


def _fmt(v, lang="en"):
    return f"{v:+.2f}" if v is not None else CHART_TEXT[lang]["na"]


def forecast_chart_svg(series, trend, width_px=540, height_px=218, lang="en"):
    """กราฟ z-score ย้อนหลัง (เส้นทึบ) + ช่วงพยากรณ์ (เส้นประบนพื้นเทา) + ระดับ "ตอนนี้" กับ "ค่าเฉลี่ยที่พยากรณ์"
    ซึ่งผลต่างของสองค่านี้คือ Z_Delta ที่ใช้จัดอันดับ - คืน SVG string หรือ None ถ้าไม่มีข้อมูล"""
    if series is None or series.empty:
        return None
    df = series[series["Date"] >= pd.Timestamp(HISTORY_FROM)]
    hist = df[df["Type"] == "Fit"]
    fc = df[df["Type"] == "Forecast"]
    if hist.empty or fc.empty:
        return None
    txt = CHART_TEXT[lang]
    # ต่อเส้นพยากรณ์จากจุดสุดท้ายของช่วงย้อนหลัง ไม่ให้มีช่องว่างระหว่างสองเส้น
    fc_line = pd.concat([hist.tail(1), fc])

    fig, ax = plt.subplots(figsize=(width_px / 96, height_px / 96), dpi=96)
    ax.axvspan(fc["Date"].min(), fc["Date"].max(), color=FORECAST_BAND, zorder=0, lw=0)
    ax.plot(hist["Date"], hist["z_score"], color=SERIES, lw=2, solid_capstyle="round", zorder=3)
    ax.plot(fc_line["Date"], fc_line["z_score"], color=SERIES, lw=2, ls=(0, (3, 2)), zorder=3)

    current = trend.get("current_z")
    avg = trend.get("forecast_avg_z")
    last = hist.iloc[-1]
    # ป้ายวางบนกล่องพื้นทึบ กันเส้นกราฟวิ่งทับตัวหนังสือ (ป้าย "Now" อยู่ซ้ายจุด ไม่ใช่ใต้จุด - ใต้จุดชนป้ายแกน X)
    label_box = {"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.9}
    ax.scatter([last["Date"]], [last["z_score"]], s=42, color=SERIES, edgecolors="white", linewidths=2, zorder=4)
    ax.annotate(f"{txt['now']} {_fmt(current, lang)}", (last["Date"], last["z_score"]), xytext=(-8, 0),
                textcoords="offset points", ha="right", va="center", fontsize=8, color=TEXT_PRIMARY,
                bbox=label_box, zorder=5)
    if avg is not None:
        ax.hlines(avg, fc["Date"].min(), fc["Date"].max(), colors=TEXT_SECONDARY, lw=1, zorder=2)
        ax.annotate(f"{txt['forecast_avg']} {_fmt(avg, lang)}", (fc["Date"].max(), avg), xytext=(0, 7),
                    textcoords="offset points", ha="right", va="bottom", fontsize=8, color=TEXT_PRIMARY,
                    bbox={**label_box, "fc": FORECAST_BAND}, zorder=5)
    ax.text(fc["Date"].min(), 1.0, f"  {txt['forecast']}", transform=ax.get_xaxis_transform(), va="top",
            fontsize=8, color=TEXT_SECONDARY)

    ax.set_ylabel(txt["y_forecast"], fontsize=8)
    ax.tick_params(labelsize=8, length=0)
    ax.grid(axis="y", color=GRID, lw=1)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.margins(x=0.01)
    fig.tight_layout(pad=0.4)

    buf = io.StringIO()
    fig.savefig(buf, format="svg", transparent=True)
    plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.find("<svg"):]  # ตัด XML prolog/DOCTYPE ออก - ฝังเป็น data URI ได้เลย


# ============================================================================
# แผนที่เทรนด์: Z_Delta (โตแค่ไหน) x Stream_Count (ยืนยันกี่สาย) - ตัวเดียวกับ Plot_trend_map.py แต่เป็นอังกฤษ + SVG
# (ไม่ import Plot_trend_map.py: สคริปต์นั้นอยู่นอก tool/ และผูกกับ Plot_bump_chart) - ไม่บอกว่าสายไหน มีแค่จำนวนสาย
# ============================================================================
TREND_MAP_KEY = "__trend_map__"  # คีย์ใน dict charts ที่ส่งให้เทมเพลต (ชื่อเทรนด์ไม่มีทางซ้ำ)
_LABEL_OFFSETS = [(0, 14), (0, -18), (12, 6), (-12, 6), (14, -12), (-14, -12), (0, 32), (0, -36),
                  (24, 20), (-24, 20), (24, -24), (-24, -24), (0, 50), (0, -54), (40, 8), (-40, 8)]


def _label_shade(rgb):
    """เฉดเข้มของสีจุดเดียวกัน ใช้เป็นสีชื่อ - สีดิบของ tab20 บางตัวอ่อนเกินอ่านบนพื้นขาว"""
    h, _, s = colorsys.rgb_to_hls(*rgb)
    return colorsys.hls_to_rgb(h, 0.32, max(s, 0.5))


def _dot_text_color(rgb):
    return "white" if 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2] < 0.55 else "#1a1a1a"


def _spread_same_y(pts, band=0.9, max_spacing=0.13):
    """Stream_Count เป็นจำนวนเต็มไม่กี่ค่า จุดส่วนใหญ่กองที่ Y เดียวกัน - กระจายแนวตั้งเฉพาะในกลุ่ม Y เท่ากัน
    (X ไม่ถูกแก้ เพราะเป็นค่าจริง)"""
    lanes = {}
    for p in pts:
        lanes.setdefault(p["y"], []).append(p)
    for group in lanes.values():
        group.sort(key=lambda p: p["x"])
        n = len(group)
        spacing = min(max_spacing, band / (n - 1)) if n > 1 else 0
        for i, p in enumerate(group):
            p["yp"] = p["y"] + (i - (n - 1) / 2) * spacing


def _declump(ax, fig, pts):
    """ผลักจุดที่ทับกันให้ห่างตามรัศมีจริงของจุด (พิกเซล) - เรียกหลัง tight_layout เสมอ ไม่งั้นกรอบแกนขยับแล้วระยะเพี้ยน"""
    fig.canvas.draw()
    ppp = fig.dpi / 72.0
    rad = np.array([(p["size"] / np.pi) ** 0.5 * ppp for p in pts])
    px = np.array([ax.transData.transform((p["x"], p["yp"])) for p in pts], dtype=float)
    for _ in range(200):
        moved = False
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                need = rad[i] + rad[j] + 5.0
                d = px[j] - px[i]
                dist = float(np.hypot(*d))
                if dist < need:
                    moved = True
                    u = d / dist if dist > 1e-6 else np.array([1.0, 0.0])
                    px[i] -= u * (need - dist) / 2
                    px[j] += u * (need - dist) / 2
        if not moved:
            break
    for p, (x, y) in zip(pts, ax.transData.inverted().transform(px)):
        p["xp"], p["yp"] = float(x), float(y)


def _draw_points_and_labels(ax, fig, pts):
    """จุด + เลขอันดับในจุด + ชื่อเทรนด์สีเดียวกับจุด (ไม่มีเส้นโยง) - ป้ายเลี่ยงทั้งป้ายอื่นและวงกลมของทุกจุด"""
    renderer = fig.canvas.get_renderer()
    ax_bb = ax.get_window_extent(renderer=renderer)
    ppp = fig.dpi / 72.0
    placed = []
    for p in pts:
        r = (p["size"] / np.pi) ** 0.5 * ppp
        cx, cy = ax.transData.transform((p["xp"], p["yp"]))
        placed.append(matplotlib.transforms.Bbox([[cx - r, cy - r], [cx + r, cy + r]]))
    for p in pts:
        ax.scatter(p["xp"], p["yp"], s=p["size"], color=p["color"], edgecolors="white", linewidths=1.2, zorder=3)
        ax.annotate(str(p["rank"]), (p["xp"], p["yp"]), ha="center", va="center", fontsize=7, fontweight="bold",
                    color=_dot_text_color(p["color"]), zorder=4)
    for p in sorted(pts, key=lambda p: p["rank"]):
        name = p["name"] if len(p["name"]) <= 34 else p["name"][:33] + "…"
        label = f"#{p['rank']} {name}"
        color = _label_shade(p["color"])
        best = None
        for dx, dy in _LABEL_OFFSETS:
            ha = "center" if dx == 0 else ("left" if dx > 0 else "right")
            t = ax.annotate(label, (p["xp"], p["yp"]), xytext=(dx, dy), textcoords="offset points",
                            ha=ha, va="center", fontsize=8, color=color, zorder=5)
            bb = t.get_window_extent(renderer=renderer).expanded(1.04, 1.2)
            inside = ax_bb.x0 <= bb.x0 and bb.x1 <= ax_bb.x1 and ax_bb.y0 <= bb.y0 and bb.y1 <= ax_bb.y1
            overlap = any(not (bb.x1 < o.x0 or bb.x0 > o.x1 or bb.y1 < o.y0 or bb.y0 > o.y1) for o in placed)
            if inside and not overlap:
                best = (t, bb)
                break
            t.remove()
        if best is None:  # ไม่มีที่ว่างพอ - วางข้างบนขวาแบบเดิม ยอมทับดีกว่าไม่มีชื่อ
            t = ax.annotate(label, (p["xp"], p["yp"]), xytext=(28, 28), textcoords="offset points",
                            ha="left", va="center", fontsize=8, color=color, zorder=5)
            best = (t, t.get_window_extent(renderer=renderer))
        placed.append(best[1])


def trend_map_svg(trends, width_px=912, height_px=372, lang="en"):
    """X = Z_Delta, Y = Stream_Count (คีย์เวิร์ดของเทรนด์เจอซ้ำในกี่สาย) ของเทรนด์ Top N - แบ่ง 4 โซนที่ Z_Delta=0 กับ
    Stream_Count=1.5 (เริ่มได้โบนัส Rank Score ขั้น 6 ตั้งแต่ 2 สายขึ้นไป) คืน SVG string หรือ None ถ้าไม่มีข้อมูล
    แต่ละเทรนด์มีสีตามอันดับ (คงที่) ขนาดจุดตามขนาดคลัสเตอร์ (Cluster_Size)"""
    palette = plt.cm.tab20.colors
    pts = []
    for t in trends:
        z, sc = t.get("z_delta"), t.get("stream_count")
        if not isinstance(z, (int, float)) or not isinstance(sc, (int, float)):
            continue
        pts.append({"rank": t["rank"], "name": t["name"], "x": float(z), "y": float(sc),
                    "size": 45 + 9 * (t.get("cluster_size") or 5), "color": palette[(t["rank"] - 1) % len(palette)]})
    if not pts:
        return None

    fig, ax = plt.subplots(figsize=(width_px / 96, height_px / 96), dpi=96)
    xs = [p["x"] for p in pts]
    ax.set_xlim(min(0.05, min(xs) - 0.08), max(xs) + 0.12)
    ax.set_yticks(sorted({p["y"] for p in pts}))
    _spread_same_y(pts)
    for p in pts:
        p["xp"] = p["x"]
    ax.set_ylim(min(p["yp"] for p in pts) - 0.6, max(p["yp"] for p in pts) + 0.6)
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    if xlim[0] < 0 < xlim[1]:
        ax.axvspan(0, xlim[1], color=FORECAST_BAND, zorder=0, lw=0)
        ax.axvline(0, color=GRID, lw=1, ls="--", zorder=1)
    if ylim[0] < 1.5 < ylim[1]:
        ax.axhline(1.5, color=GRID, lw=1, ls="--", zorder=1)

    txt = CHART_TEXT[lang]
    ax.set_xlabel(txt["map_x"], fontsize=8)
    ax.set_ylabel(txt["map_y"], fontsize=8)
    ax.tick_params(labelsize=8, length=0)
    ax.grid(color=GRID, lw=1)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout(pad=0.5)  # ก่อน _declump เสมอ - หลังจากนี้กรอบแกนต้องไม่ขยับอีก
    _declump(ax, fig, pts)
    _draw_points_and_labels(ax, fig, pts)

    zone = {"fontsize": 8, "style": "italic", "color": "#898781", "transform": ax.transAxes}
    ax.text(0.008, 0.985, txt["zone_tl"], ha="left", va="top", **zone)
    ax.text(0.992, 0.985, txt["zone_tr"], ha="right", va="top", **zone)
    ax.text(0.008, 0.015, txt["zone_bl"], ha="left", va="bottom", **zone)
    ax.text(0.992, 0.015, txt["zone_br"], ha="right", va="bottom", **zone)

    buf = io.StringIO()
    fig.savefig(buf, format="svg", transparent=True)
    plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.find("<svg"):]


# ============================================================================
# Bump chart: อันดับของแต่ละเทรนด์ในแต่ละปี (เทียบกันเองใน Top N) - ตรรกะอันดับเดียวกับ Plot_bump_chart.py
# (ค่าเฉลี่ย z-score รายปีของโมเดลที่ถูกเลือก ไม่นับ Holdout, จัดอันดับ 1 = สูงสุด, method="first" ให้ 1..N ครบทุกปี)
# แต่เป็นอังกฤษ + SVG สีตามอันดับรายงานเดียวกับหน้า Trend Map
# ============================================================================
BUMP_CHART_KEY = "__bump_chart__"  # คีย์ใน dict charts ที่ส่งให้เทมเพลต
BUMP_START_YEAR = 2023             # ตรงกับ START_YEAR ใน Plot_bump_chart.py


def yearly_ranks(series, start_year=BUMP_START_YEAR):
    """{ชื่อเทรนด์: DataFrame(Date, z_score, Type)} -> DataFrame ดัชนี=ปี คอลัมน์=ชื่อเทรนด์ ค่า=อันดับ 1..N ภายในกลุ่มนี้
    คอลัมน์เรียงตามชื่อ (เหมือน pivot ใน Plot_bump_chart) เพื่อให้กรณี z-score เท่ากันตัดสินเหมือนกันทุกประการ"""
    yearly = {name: df.groupby(df["Date"].dt.year)["z_score"].mean() for name, df in series.items() if not df.empty}
    if not yearly:
        return pd.DataFrame()
    pivot = pd.DataFrame(yearly).sort_index(axis=1)
    pivot = pivot[pivot.index >= start_year]
    return pivot.rank(axis=1, ascending=False, method="first", na_option="bottom").astype(int)


def bump_chart_svg(series, trends, width_px=912, height_px=372, lang="en"):
    """เส้นอันดับรายปีของเทรนด์ Top N (1 = สนใจสูงสุดในปีนั้น) ป้ายชื่อที่ปลายเส้นปีสุดท้าย - คืน SVG string หรือ None
    ถ้ามีข้อมูลไม่ถึง 2 ปี"""
    ranks = yearly_ranks({t["name"]: series[t["name"]] for t in trends if t["name"] in (series or {})})
    if ranks.empty or len(ranks.index) < 2:
        return None
    palette = plt.cm.tab20.colors
    report_rank = {t["name"]: t["rank"] for t in trends}

    fig, ax = plt.subplots(figsize=(width_px / 96, height_px / 96), dpi=96)
    x = list(range(len(ranks.index)))
    for name in sorted(ranks.columns, key=lambda n: report_rank[n]):
        color = palette[(report_rank[name] - 1) % len(palette)]
        y = ranks[name].values
        ax.plot(x, y, color=color, lw=2, marker="o", markersize=6, markeredgecolor="white", markeredgewidth=1.2,
                solid_capstyle="round", zorder=3)
        short = name if len(name) <= 34 else name[:33] + "…"
        ax.annotate(f"#{report_rank[name]} {short}", (x[-1], y[-1]), xytext=(9, 0), textcoords="offset points",
                    va="center", fontsize=8, color=_label_shade(color), zorder=5)
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in ranks.index])
    ax.set_yticks(range(1, int(ranks.values.max()) + 1))
    ax.invert_yaxis()
    ax.set_xlim(-0.3, x[-1] + 2.5)  # ที่ว่างทางขวาให้ป้ายชื่อที่ยื่นออกจากจุดสุดท้าย
    ax.set_ylabel(CHART_TEXT[lang]["bump_y"].format(n=len(ranks.columns)), fontsize=8)
    ax.tick_params(labelsize=8, length=0)
    ax.grid(axis="y", color=GRID, lw=1)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    fig.tight_layout(pad=0.5)

    buf = io.StringIO()
    fig.savefig(buf, format="svg", transparent=True)
    plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.find("<svg"):]


# ============================================================================
# ⑰ รายงานแบรนด์: Trend Fit Matrix - แรงส่งของเทรนด์ (Z_Delta) x อันดับของสินค้าที่ใกล้ที่สุดของแบรนด์ในตลาด
# สีจุดตามอันดับเทรนด์ (palette เดียวกับ Trend Map ในรายงานเทรนด์ - เทรนด์เดียวกันสีเดียวกันทั้ง 2 รายงาน)
# ============================================================================
FIT_MATRIX_KEY = "__fit_matrix__"
BUILD_SHADE = "#fbeee6"  # พื้นช่อง "สร้างใหม่" (โอกาส) - accent อ่อนมาก ไม่ใช่สีซีรีส์


def trend_color(rank):
    """(สีพื้น, สีตัวเลข) ประจำเทรนด์ตามอันดับ - palette เดียวกับจุดในกราฟ ใช้ทำรายการชื่อเทรนด์ข้างกราฟให้สีตรงกัน"""
    from matplotlib.colors import to_hex

    rgb = plt.cm.tab20.colors[(rank - 1) % 20]
    return to_hex(rgb), _dot_text_color(rgb)


def fit_matrix_svg(rows, split, boundary, thresholds, n_market, labels, width_px=640, height_px=372):
    """rows: brand_data.build_brand_context()["rows"] / split: เส้นแบ่งแรงส่ง / boundary: อันดับที่ใช้แบ่ง "พร้อม" กับ
    "ยังไม่พร้อม" (เกณฑ์ของระดับพร้อมสูงสุด) / labels: ข้อความแกน/ช่อง/ระดับของภาษานั้น (brand_i18n)
    แกน Y เป็น log และกลับด้าน (อันดับ 1 อยู่บน) - แบรนด์ที่ไม่มีสินค้าเลยวางไว้ล่างสุดที่อันดับ = จำนวน SKU ทั้งตลาด
    คืน SVG string หรือ None ถ้าไม่มีเทรนด์ที่ตรวจแล้ว"""
    from matplotlib import ticker

    palette = plt.cm.tab20.colors
    n_market = n_market or 10000
    ranks = [r["best_rank"] for r in rows if r.get("checked") and isinstance(r.get("best_rank"), (int, float))]
    # ขอบล่างตามข้อมูลจริง (ไม่ยืดถึงจำนวน SKU ทั้งตลาดเสมอ - แบรนด์ที่อันดับดีสุดแค่หลักร้อยจะเหลือที่ว่างครึ่งกราฟ)
    # แต่ต่ำกว่าเกณฑ์ "ตามหลัง" อย่างน้อย 4 เท่าเสมอ ให้เห็นช่อง "ช่องว่าง" - เทรนด์ที่แบรนด์ไม่มีสินค้าเลยวางไว้แถวล่างสุด
    y_bottom = min(n_market * 1.6, max([thresholds["behind"] * 4] + [r * 2.5 for r in ranks]))
    pts = []
    for r in rows:
        if not r.get("checked") or not isinstance(r.get("z_delta"), (int, float)):
            continue
        rank = r["best_rank"] if isinstance(r.get("best_rank"), (int, float)) else y_bottom / 1.6
        pts.append({"rank": r["rank"], "name": r["name"], "x": float(r["z_delta"]), "y": float(rank),
                    "yp": float(rank), "size": 170, "color": palette[(r["rank"] - 1) % len(palette)]})
    if not pts:
        return None

    fig, ax = plt.subplots(figsize=(width_px / 96, height_px / 96), dpi=96)
    ax.set_yscale("log")
    xs = [p["x"] for p in pts]
    x0, x1 = min(xs + [split]) - 0.12, max(xs + [split]) + 0.12
    y_top = 0.7
    ax.set_xlim(x0, x1)
    ax.set_ylim(y_bottom, y_top)  # กลับด้าน: อันดับ 1 อยู่บนสุด
    ax.fill_between([split, x1], boundary, y_bottom, color=BUILD_SHADE, zorder=0, lw=0)
    ax.axvline(split, color=TEXT_SECONDARY, lw=1, zorder=1)
    ax.axhline(boundary, color=TEXT_SECONDARY, lw=1, zorder=1)
    for level in ("leading", "competitive", "behind"):
        y = thresholds[level]
        if y != boundary:
            ax.axhline(y, color=GRID, lw=1, zorder=1)
        ax.text(1.005, y, f"{labels['levels'][level]} ≤{y}", transform=ax.get_yaxis_transform(), va="center",
                ha="left", fontsize=7.5, color=TEXT_SECONDARY)
    ax.text(1.005, (thresholds["behind"] * y_bottom) ** 0.5, labels["levels"]["gap"], transform=ax.get_yaxis_transform(),
            va="center", ha="left", fontsize=7.5, color=TEXT_SECONDARY)

    ax.set_yticks([t for t in (1, 10, 100, 1000, 10000) if t <= y_bottom])
    ax.get_yaxis().set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.yaxis.set_minor_locator(ticker.NullLocator())
    ax.set_xlabel(labels["x"], fontsize=8)
    ax.set_ylabel(labels["y"], fontsize=8)
    ax.tick_params(labelsize=8, length=0)
    ax.grid(axis="x", color=GRID, lw=1)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout(pad=0.5, rect=(0, 0, 0.86, 1))  # ที่ว่างทางขวาให้ป้ายระดับ - ก่อน _declump เสมอ
    _declump(ax, fig, pts)
    # จุดมีแค่เลขอันดับ ชื่อเทรนด์อยู่ในรายการข้างกราฟ (brand_report.html.j2) - รอบ 082438 ของ Mizumi ป้ายชื่อบนกราฟ
    # ชนกันเมื่อหลายเทรนด์อยู่อันดับใกล้กัน (แกน log บีบช่วงหลักร้อยให้แคบ) รายการข้างกราฟไม่มีวันชนกัน
    for p in pts:
        ax.scatter(p["xp"], p["yp"], s=p["size"], color=p["color"], edgecolors="white", linewidths=1.2, zorder=3)
        ax.annotate(str(p["rank"]), (p["xp"], p["yp"]), ha="center", va="center", fontsize=7.5, fontweight="bold",
                    color=_dot_text_color(p["color"]), zorder=4)

    quad = {"fontsize": 9, "fontweight": "bold", "color": "#898781", "transform": ax.transAxes}
    ax.text(0.99, 0.985, labels["defend"], ha="right", va="top", **quad)
    ax.text(0.99, 0.015, labels["build"], ha="right", va="bottom", **{**quad, "color": "#b54a1c"})
    ax.text(0.01, 0.985, labels["maintain"], ha="left", va="top", **quad)
    ax.text(0.01, 0.015, labels["monitor"], ha="left", va="bottom", **quad)

    buf = io.StringIO()
    fig.savefig(buf, format="svg", transparent=True)
    plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.find("<svg"):]
