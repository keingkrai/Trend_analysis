# -*- coding: utf-8 -*-
"""
Bump chart อันดับเทรนด์ตามช่วงเวลา + ตารางอันดับเป็น Excel

แยกออกมาจาก trend.ipynb (เซลล์ Config → Load & prepare data → คำนวณ ranks → Export ตารางอันดับ → Plot bump chart)
ให้รันจาก command line ได้โดยไม่ต้องเปิด Jupyter - ตรรกะเหมือนใน notebook ทุกขั้น (ไม่รวมส่วน Export PDF และ
Exfac Brand Coverage Matrix)

วิธีใช้ (รันจากที่ไหนก็ได้ สคริปต์เดินขึ้นไปหาโฟลเดอร์โปรเจกต์ที่มี trend_final.py เอง):
    python Plot_bump_chart.py                  (จากโฟลเดอร์ main) - ขึ้นรายชื่อรอบรันให้เลือก (Enter = ล่าสุด)
    python Plot_bump_chart.py --run <ชื่อโฟลเดอร์รอบ>   - ระบุรอบตรงๆ ไม่ต้องถาม

🆕 (2026-09-16) ตอนเริ่มถามว่าจะทำกับรอบรันไหน (เฉพาะโฟลเดอร์ใน main/output/ ที่มีผลพยากรณ์ step5c) แล้ว
บันทึกผลลงโฟลเดอร์รอบนั้นเลย ตามที่เจ้าของงานขอ (เดิมใช้รอบที่ตั้งไว้ตายตัวใน CONFIG และบันทึกลง outputs/ ที่ root):
    - main/output/<รอบ>/step5c_df_cluster_forecast_ranks_<วันเวลา>.xlsx  (ตารางอันดับ)
    - main/output/<รอบ>/trend_bump_chart.png                            (กราฟ - เขียนทับไฟล์เดิมของรอบนั้น)

ค่าอื่นแก้ในส่วน CONFIG ด้านล่างเหมือนเซลล์ Config ของ notebook

ต่างจาก notebook: ไม่มี plt.show() (บันทึกไฟล์อย่างเดียว), บันทึกตารางอันดับก่อนวาดกราฟ, 🆕 (2026-09-16) Excel
มีชีตเดียว (อันดับชุดเดียวกับกราฟ) และคอลัมน์ period เป็นป้ายอ่านง่าย ("2023" แทน 2023-01-01 00:00:00)

⚠️ ช่วงเวลาสุดท้ายอาจไม่เต็มช่วง - ผลพยากรณ์ไปสิ้นสุดตามขอบฟ้าที่ตั้งตอนรัน (รอบ 082438 ถึง ส.ค. 2029 ปี 2029 จึงเฉลี่ย
จาก 8 เดือน) ถ้าอยากได้เฉพาะปีเต็ม ตั้ง END_YEAR เป็นปีก่อนหน้า
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # ไม่เปิดหน้าต่างกราฟ - บันทึกเป็นไฟล์อย่างเดียว
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

# ============================================================================
# CONFIG (เหมือนเซลล์ Config ใน trend.ipynb)
# ============================================================================
# รอบรันเลือกตอนเริ่ม (ดู choose_run_folder) - ไม่ต้องตั้งตรงนี้แล้ว
OUTPUT_ROOT_PARTS = ("output",)                 # ที่เก็บรอบรันทั้งหมด (ต่อจากโฟลเดอร์ main/)
FORECAST_SUBDIR = "serpapi_forecast_run"        # โฟลเดอร์ผลพยากรณ์ของ ⑦ ภายในแต่ละรอบ
FORECAST_FILE = "step5c_df_cluster_forecast.xlsx"

# จำนวนเทรนด์ในกราฟ/Excel - None = ใช้ค่าเดียวกับที่ไปป์ไลน์รอบนั้นคัดไว้ (อ่าน top_n จากผล ⑪ ถ้าไม่มีใช้ 10)
# ใส่ตัวเลขเพื่อกำหนดเอง - ไม่ว่าแบบไหน เทรนด์ที่ได้เป็นชุดเดียวกับรายงานเสมอ (ชุดที่ ⑪ คัดด้วย Rank Score ของ ⑥)
TOP_N_HIGHLIGHT = None
AGG_FREQ = "Y"  # "Y" | "Q" | "M"

# กำหนดช่วงปีที่จะแสดงในกราฟ - ใส่ None เพื่อไม่จำกัด (แสดงทุกช่วงที่มีข้อมูล)
START_YEAR = 2023
END_YEAR = None

# False = ตัดเส้นเทา (คลัสเตอร์ที่ไม่ติด TOP_N_HIGHLIGHT) ออกจากกราฟไปเลย ไม่ใช่แค่จางลง
SHOW_OTHERS = False

# True  = จัดอันดับใหม่โดยเทียบกันเองเฉพาะเทรนด์ในกราฟ ในทุกช่วงเวลา (ทุกปีเป็น 1..N เสมอ)
# False = อันดับจริงเทียบกับทุกคลัสเตอร์ (ปีเก่าอาจเห็นเลขเกิน N เพราะตอนนั้นเทรนด์ยังไม่ติดกลุ่มบน)
# ค่านี้ใช้กับทั้งกราฟและไฟล์ Excel (อันดับในกราฟเรียงตามระดับ z-score ของแต่ละช่วงเวลาเหมือนเดิม)
RANK_WITHIN_TOP_N = True

CHART_TITLE = "Beauty and Personal Care 2029"

# Cove categorical palette (fixed order, never cycled) - ใช้จนกว่าจะหมด slot ค่อยตกไป slot ถัดไป
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948",
           "#8b5e3c", "#a0527a"]  # +2 สี (น้ำตาล, ม่วงอมชมพู) ต่อจาก Cove palette เดิม 8 สี
MUTED = "#b4b2a9"


# ============================================================================
# ขั้นตอน
# ============================================================================
def find_project_root():
    """หาโฟลเดอร์ main/ (โฟลเดอร์ที่มี tool/common/bootstrap.py) - เริ่มจากตำแหน่งไฟล์สคริปต์นี้ก่อน แล้วค่อยลอง
    จากโฟลเดอร์ที่รันคำสั่ง - 🆕 (2026-09-22) เดิมหาโฟลเดอร์ที่มี trend_final.py (root นอก main/) ตอนนี้ทุกอย่าง
    ที่ใช้อยู่ใน main/ แล้ว"""
    for start in (Path(__file__).resolve().parent, Path.cwd().resolve()):
        for candidate in (start, *start.parents):
            if (candidate / "tool" / "common" / "bootstrap.py").exists():
                return candidate
    raise RuntimeError("หาโฟลเดอร์ main/ ไม่เจอ - วางสคริปต์นี้ไว้ในโฟลเดอร์ main/ (ที่มี tool/) "
                       "หรือรันจากโฟลเดอร์ main/")


def list_run_folders(output_root):
    """รอบรันที่พลอตได้ = โฟลเดอร์ใน output/ ที่มี serpapi_forecast_run/step5c_df_cluster_forecast.xlsx (ข้าม
    โฟลเดอร์ขึ้นต้นด้วย "_" ซึ่งไม่ใช่ผลรัน ตามกติกาใน output/README.md) เรียงจากพยากรณ์ล่าสุดไปเก่าสุด"""
    runs = [d for d in output_root.iterdir()
            if d.is_dir() and not d.name.startswith("_") and (d / FORECAST_SUBDIR / FORECAST_FILE).exists()]
    return sorted(runs, key=lambda d: (d / FORECAST_SUBDIR / FORECAST_FILE).stat().st_mtime, reverse=True)


def describe_run(run):
    """ข้อความสั้นๆ ของรอบรันสำหรับเมนู: หัวข้อจริง (จากผลสาย Paper) + จำนวน Top N ที่ ⑪ คัดไว้ถ้ามี"""
    parts = []
    try:
        with open(run / "phase1_paper_stream_result.json", encoding="utf-8") as f:
            topic = (json.load(f).get("topic") or "").strip()
        if topic:
            parts.append(topic)
    except (FileNotFoundError, ValueError):
        pass
    try:
        with open(run / "phase3_trend_highlights_result.json", encoding="utf-8") as f:
            top_n = json.load(f).get("top_n")
        parts.append(f"Top {top_n}" if top_n else "ยังไม่มีชุด Top N จาก ⑪")
    except (FileNotFoundError, ValueError):
        parts.append("ยังไม่มีผล ⑪")
    return " | ".join(parts)


def choose_run_folder(output_root, run_name=None):
    """เลือกรอบรัน - ส่ง run_name มา (จาก --run) ใช้ตัวนั้นเลย / ไม่ส่ง = ขึ้นรายชื่อให้เลือกเป็นหมายเลข
    (Enter = รอบล่าสุด, ถ้ารันแบบไม่มีคนตอบ เช่น stdin ปิด ก็ใช้รอบล่าสุด)"""
    runs = list_run_folders(output_root)
    if not runs:
        raise SystemExit(f"❌ ไม่พบรอบรันที่มี {FORECAST_SUBDIR}/{FORECAST_FILE} ใน {output_root}")
    if run_name:
        chosen = next((r for r in runs if r.name == run_name), None)
        if chosen is None:
            raise SystemExit(f"❌ ไม่พบรอบ '{run_name}' ที่พลอตได้ - รอบที่มี: {[r.name for r in runs]}")
        return chosen

    print("\nเลือกรอบรันที่จะทำ bump chart:")
    for i, run in enumerate(runs, 1):
        latest = "  ← ล่าสุด" if i == 1 else ""
        print(f"  {i}. {run.name}  ({describe_run(run)}){latest}")
    while True:
        try:
            raw = input(f"เลือกหมายเลข [1-{len(runs)}] (Enter = 1): ").strip()
        except (EOFError, OSError):
            raw = ""
        if not raw:
            return runs[0]
        if raw.isdigit() and 1 <= int(raw) <= len(runs):
            return runs[int(raw) - 1]
        print(f"  ⚠️ '{raw}' ไม่ใช่หมายเลขในรายการ ลองใหม่")


def setup_thai_font():
    """ตั้ง font ที่รองรับภาษาไทยให้ matplotlib (ฟอนต์ default ไม่มี glyph ไทย จะขึ้นเป็นกล่องเปล่า)"""
    available = {f.name for f in fm.fontManager.ttflist}
    for name in ["Tahoma", "Leelawadee UI", "Angsana New"]:
        if name in available:
            plt.rcParams["font.family"] = name
            return


def resolve_top_n(run_dir, top_n):
    """None = ใช้จำนวนที่ไปป์ไลน์รอบนั้นคัดไว้ (top_n ในผล ⑪) ถ้าไม่มีใช้ 10 - ตรวจไม่ให้เกินจำนวนสีที่มี"""
    if top_n is None:
        highlights_file = run_dir.parent / "phase3_trend_highlights_result.json"
        try:
            with open(highlights_file, encoding="utf-8") as f:
                recorded = json.load(f).get("top_n")
        except (FileNotFoundError, ValueError):
            recorded = None
        if recorded:
            top_n = int(recorded)
            print(f"TOP_N_HIGHLIGHT = {top_n} (ตามที่ไปป์ไลน์รอบนี้คัดไว้ใน {highlights_file.name})")
        else:
            top_n = 10
            print("TOP_N_HIGHLIGHT = 10 (รอบนี้ไม่มีค่า top_n บันทึกไว้ เช่น รันก่อนมีระบบ Top N - ใช้ค่าเริ่มต้น)")
    if top_n > len(PALETTE):
        raise ValueError(f"TOP_N_HIGHLIGHT ({top_n}) เกินจำนวนสีที่มี ({len(PALETTE)}) ลดลงหรือเพิ่มสีใน PALETTE")
    if RANK_WITHIN_TOP_N and SHOW_OTHERS:
        raise ValueError("RANK_WITHIN_TOP_N=True ใช้คู่กับ SHOW_OTHERS=True ไม่ได้ (เส้นเทาไม่มีอันดับภายในกลุ่ม "
                         "Top N ให้วาด) - ปิดตัวใดตัวหนึ่ง")
    return top_n


def load_forecast(run_dir):
    """โหลดผลพยากรณ์ step5c แล้วเก็บเฉพาะแถวของโมเดลที่ถูกเลือกเป็น best_model ของแต่ละคลัสเตอร์"""
    if not run_dir.exists():
        raise FileNotFoundError(f"ไม่พบโฟลเดอร์ผลพยากรณ์ {run_dir}")
    matches = sorted(run_dir.glob(FORECAST_FILE))
    if not matches:
        raise FileNotFoundError(f"ไม่พบ {FORECAST_FILE} ใน {run_dir}")
    df = pd.read_excel(matches[0])
    df["Date"] = pd.to_datetime(df["Date"])
    df = df[df["Model"] == df["best_model"]].copy()
    print(f"โหลด {len(df):,} แถว, {df['cluster_name'].nunique()} คลัสเตอร์, "
          f"ช่วงวันที่ {df['Date'].min().date()} ถึง {df['Date'].max().date()}")
    return df


def compute_ranks(df):
    """รวม z-score เฉลี่ยตามช่วงเวลา แล้วจัดอันดับในแต่ละช่วง (rank 1 = z-score สูงสุด) + กรองช่วงปี"""
    freq_code = {"Y": "Y", "Q": "Q", "M": "M"}[AGG_FREQ]
    # 🆕 (2026-09-16) ไม่นับแถว Holdout - เป็นค่าที่โมเดลทำนายเดือนท้ายของข้อมูลจริงไว้วัดความแม่นตอนเลือกโมเดล
    # เดือนเดียวกันมีแถว Fit อยู่แล้ว ถ้านับด้วยเดือนพวกนั้นจะถูกเฉลี่ยซ้ำ 2 ครั้ง (เจอจริงรอบ 082438: ปี 2026 มี
    # Fit เดือน 1-8 + Holdout เดือน 3-8 + Forecast เดือน 9-12 ทำให้อันดับปี 2026 เพี้ยน 3 ช่อง)
    df = df[df["Type"] != "Holdout"].copy()
    df["period"] = df["Date"].dt.to_period(freq_code).dt.to_timestamp()

    agg = df.groupby(["cluster_name", "period"], as_index=False)["z_score"].mean()
    pivot = agg.pivot(index="period", columns="cluster_name", values="z_score")
    ranks = (
        pivot.rank(axis=1, ascending=False, method="first", na_option="bottom")
        .fillna(len(pivot.columns) + 1)
        .astype(int)
    )
    # กรองช่วงปี (rank คำนวณแยกต่อช่วงเวลาอยู่แล้ว การตัดแถวออกไม่กระทบอันดับของแถวที่เหลือ)
    if START_YEAR is not None:
        ranks = ranks[ranks.index.year >= START_YEAR]
    if END_YEAR is not None:
        ranks = ranks[ranks.index.year <= END_YEAR]
    if ranks.empty:
        raise ValueError("ไม่มีข้อมูลอยู่ในช่วง START_YEAR–END_YEAR ที่กำหนด ลองขยายช่วงดู")
    return ranks


def select_highlight(ranks, run_dir, top_n):
    """เลือกชุดเทรนด์ให้ตรงกับรายงาน - ลำดับที่ใช้:
      1) ชุดที่ ⑪ คัดไว้ (Top N ตาม Rank Score ของ ⑥ ที่จับคู่สินค้าได้)
      2) ไม่มีผล ⑪ แบบใหม่ -> Top N ตาม Rank Score ของ ⑥ ตรงๆ
      3) ไม่มีทั้งคู่ -> อันดับของช่วงเวลาล่าสุด (อาจไม่ตรงกับรายงาน - มีคำเตือน)
    คืน list ชื่อเทรนด์ เรียงตามอันดับของช่วงล่าสุด (ใช้เป็นลำดับสีและลำดับคอลัมน์)"""
    final_period_rank = ranks.iloc[-1].sort_values()
    highlights_file = run_dir.parent / "phase3_trend_highlights_result.json"
    rank_file = run_dir.parent / "phase2_rank_score_final_mode_result.json"

    selected_names, source = None, None
    if highlights_file.exists():
        with open(highlights_file, encoding="utf-8") as f:
            selected = json.load(f).get("selected_trends")
        if selected:
            if top_n > len(selected):
                print(f"⚠️ ⑪ คัดไว้ {len(selected)} เทรนด์ น้อยกว่า TOP_N_HIGHLIGHT={top_n} - ใช้ {len(selected)} ตัว "
                      "(อยากได้มากกว่านี้ให้รันไปป์ไลน์ด้วย --top-n ที่มากขึ้น)")
            selected_names = [s["trend"] for s in selected[:top_n]]
            source = f"ชุดที่ ⑪ คัดไว้ ({highlights_file.name})"
    if selected_names is None and rank_file.exists():
        with open(rank_file, encoding="utf-8") as f:
            rank_rows = sorted(json.load(f), key=lambda r: r["Overall Rank"])
        selected_names = [r["Trend Name"] for r in rank_rows[:top_n]]
        source = f"Rank Score ของ ⑥ ({rank_file.name}) - รอบนี้ไม่มีชุดจาก ⑪"

    if selected_names is None:
        print(f"⚠️ ไม่พบผล ⑪/⑥ - ใช้ {top_n} อันดับแรกของช่วงเวลาล่าสุดแทน (อาจไม่ตรงกับชุดในรายงาน)")
        return list(final_period_rank.index[:top_n])

    missing = [t for t in selected_names if t not in ranks.columns]
    if missing:
        raise ValueError(f"เทรนด์ที่คัดไว้ไม่มีในข้อมูลพยากรณ์ของ RUN_DIR: {missing} - "
                         "RUN_DIR กับผล ⑥/⑪ มาจากคนละรอบหรือเปล่า")
    highlight = [name for name in final_period_rank.index if name in selected_names]
    print(f"ชุดเทรนด์: {len(highlight)} ตัวจาก{source}")
    return highlight


def compute_plot_ranks(ranks, highlight):
    """อันดับที่ใช้วาดและบันทึก: RANK_WITHIN_TOP_N=True -> เทียบกันเองเฉพาะ highlight ทุกช่วงเวลา (ได้ 1..N ครบ)
    / False -> อันดับจริงเทียบกับทุกคลัสเตอร์ - จัดอันดับจากอันดับจริงได้ตรงๆ เพราะลำดับภายในกลุ่มย่อยไม่เปลี่ยน"""
    if RANK_WITHIN_TOP_N:
        return ranks[highlight].rank(axis=1, method="first").astype(int)
    return ranks


def period_label(ts):
    """ป้ายช่วงเวลาให้อ่านตรงความหมาย (ใช้ทั้งแกนกราฟและคอลัมน์ period ใน Excel): รายปี "2023", รายไตรมาส
    "2023-Q1", รายเดือน "2023-01" - เดิม Excel เก็บเป็นวันที่เต็ม 2023-01-01 00:00:00 ทั้งที่แถวนั้นคือทั้งปี"""
    if AGG_FREQ == "Y":
        return ts.strftime("%Y")
    if AGG_FREQ == "Q":
        return f"{ts.year}-Q{ts.quarter}"
    return ts.strftime("%Y-%m")


def save_ranks_excel(ranks, plot_ranks, highlight, outputs_dir):
    """ชีตเดียว = อันดับชุดเดียวกับที่กราฟวาด (ตาม RANK_WITHIN_TOP_N) - 🆕 (2026-09-16) ตัดชีตอันดับจริงจากทุก
    คลัสเตอร์ออกตามที่เจ้าของงานขอ"""
    ranks_top = plot_ranks[highlight].copy()
    ranks_top.index = pd.Index([period_label(d) for d in ranks_top.index], name="period")
    sheet = f"อันดับภายใน Top {len(highlight)}" if RANK_WITHIN_TOP_N else f"อันดับจริง (จาก {ranks.shape[1]})"
    path = outputs_dir / f"step5c_df_cluster_forecast_ranks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        ranks_top.to_excel(writer, sheet_name=sheet)
    print(f"บันทึกตารางอันดับ {ranks_top.shape[1]} เทรนด์ x {ranks_top.shape[0]} ช่วงเวลา "
          f"({sheet}, {ranks_top.index[0]}-{ranks_top.index[-1]}, ค่า {ranks_top.values.min()}-{ranks_top.values.max()}) "
          f"-> {path}")
    return path


def plot_bump_chart(ranks, plot_ranks, highlight, outputs_dir):
    """วาด bump chart แล้วบันทึกเป็น trend_bump_chart.png (เขียนทับไฟล์เดิม)"""
    color_map = {name: PALETTE[i] for i, name in enumerate(highlight)}

    fig, ax = plt.subplots(figsize=(12, 7))
    x = range(len(ranks.index))
    xticklabels = [period_label(d) for d in ranks.index]

    # วาดเส้นเทาก่อน (ถ้าเปิดไว้) ให้อยู่ซ้อนล่างสุด เส้นเด่นวาดทีหลังสุดจะได้อยู่บนสุด (เด่นชัด)
    if SHOW_OTHERS:
        for name in ranks.columns:
            if name in highlight:
                continue
            ax.plot(x, ranks[name].values, marker="o", markersize=5, linewidth=1.5,
                    color=MUTED, alpha=0.55, zorder=1)

    for name in highlight:
        y = plot_ranks[name].values
        color = color_map[name]
        ax.plot(x, y, marker="o", markersize=8, linewidth=2.5, color=color, zorder=3, label=name)
        ax.annotate(name, xy=(x[-1], y[-1]), xytext=(10, 0), textcoords="offset points",
                    va="center", fontsize=10, fontweight="bold", color=color)

    ax.set_xticks(list(x))
    ax.set_xticklabels(xticklabels)
    # แกน Y ใช้ช่วง rank เท่าที่เส้นที่วาดจริงครอบคลุมถึง (กันเผื่อเส้นเด่นเคยตกไปอันดับท้ายๆ ในบางช่วง)
    visible_cols = highlight if not SHOW_OTHERS else list(ranks.columns)
    y_max = int(plot_ranks[visible_cols].values.max())
    ax.set_yticks(range(1, y_max + 1))
    ax.invert_yaxis()
    ax.set_ylabel(f"Ranking (within top {len(highlight)})" if RANK_WITHIN_TOP_N else "Ranking")
    ax.set_title(CHART_TITLE, fontweight="bold")
    ax.grid(axis="y", color="#e1e0d9", linewidth=1, zorder=0)
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)

    # กันพื้นที่ทางขวาไว้สำหรับ label ที่ยื่นออกมานอกแกนจากจุดสุดท้าย
    ax.set_xlim(x[0] - 0.3, x[-1] + 2.6)

    plt.tight_layout()
    path = outputs_dir / "trend_bump_chart.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"บันทึกภาพแล้วที่ {path}")
    return path


def main(run_name=None, outputs_dir=None):
    """run_name: ชื่อโฟลเดอร์รอบ (None = ถามตอนเริ่ม) / outputs_dir: ที่บันทึกผล (None = โฟลเดอร์รอบที่เลือก)"""
    project_root = find_project_root()
    print(f"PROJECT_ROOT = {project_root}")
    run_folder = choose_run_folder(project_root.joinpath(*OUTPUT_ROOT_PARTS), run_name)
    print(f"▶ รอบรัน: {run_folder.name}")
    outputs_dir = Path(outputs_dir) if outputs_dir else run_folder
    outputs_dir.mkdir(parents=True, exist_ok=True)
    run_dir = run_folder / FORECAST_SUBDIR

    setup_thai_font()
    top_n = resolve_top_n(run_dir, TOP_N_HIGHLIGHT)
    df = load_forecast(run_dir)
    ranks = compute_ranks(df)
    highlight = select_highlight(ranks, run_dir, top_n)
    plot_ranks = compute_plot_ranks(ranks, highlight)
    ranks_path = save_ranks_excel(ranks, plot_ranks, highlight, outputs_dir)
    chart_path = plot_bump_chart(ranks, plot_ranks, highlight, outputs_dir)
    return ranks_path, chart_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bump chart อันดับเทรนด์ + ตารางอันดับ Excel ของรอบรันที่เลือก")
    parser.add_argument("--run", default=None, help="ชื่อโฟลเดอร์รอบใน main/output (ไม่ใส่ = ขึ้นรายชื่อให้เลือก)")
    try:
        main(run_name=parser.parse_args().run)
    except (FileNotFoundError, ValueError) as e:
        # ข้อมูล/ค่าตั้งไม่ถูกต้อง (เช่น ไฟล์ของรอบนั้นมาจากคนละรอบกัน) - แจ้งสั้นๆ แทน traceback ยาว ยังไม่ได้บันทึกไฟล์ใดๆ
        raise SystemExit(f"❌ ทำ bump chart ไม่ได้: {e}")
