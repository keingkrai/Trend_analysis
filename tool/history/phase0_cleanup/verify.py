# -*- coding: utf-8 -*-
"""Phase 0 verification — ทดสอบว่าแก้แล้วยังทำงานถูก ไม่ยิง API เลย"""
import io
import sys
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(r"D:\Users\keingkrai_b\Desktop\Trend")
# 2026-08-31: ย้ายออกจาก workspace/phase0_cleanup/ ไปเป็น trend_final_v2.py ที่ root แล้ว - เป็นไฟล์
# ถาวรคู่ขนานกับ trend_final.py (ไม่ใช่สำเนาชั่วคราวรอ promote ทับ root อีกต่อไป ตามที่เจ้าของงาน
# ยืนยันชัดเจนว่าห้ามแตะ trend_final.py เด็ดขาด) ดู Backlog ข้อ 27
NEW = ROOT / "trend_final_v2.py"

# trend_final_v2.py โหลด .env จากโฟลเดอร์ตัวเอง (Path(__file__).parent) - อยู่ที่ root แล้วเจอ .env
# ตรงๆ ไม่ต้องยัด env มือแบบตอนที่ยังอยู่ใน workspace/ (ลึกกว่า root 1 ชั้น)

spec = importlib.util.spec_from_file_location("tf_new", NEW)
tf = importlib.util.module_from_spec(spec)
sys.modules["tf_new"] = tf
spec.loader.exec_module(tf)

import numpy as np
import pandas as pd

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + detail) if detail else ""))
    if not cond:
        fails.append(name)


# ══ TEST 1: safe_json_parse ═══════════════════════════════════════════════
print("\n[1] safe_json_parse — เคสที่เคยพัง + เคสเดิมต้องไม่ regress")
p = tf.safe_json_parse

r = p('{"why": "brand pushes \\"Moisture Barrier\\" hard"}')
check("escaped quote ในค่า string", r == {"why": 'brand pushes "Moisture Barrier" hard'}, str(r))

r = p('{"a": "\\"K-Beauty\\"", "b": "\\"Clean\\" at Sephora"}')
check("escaped quote หลายจุด", r == {"a": '"K-Beauty"', "b": '"Clean" at Sephora'}, str(r))

check("JSON ปกติ", p('{"a": 1}') == {"a": 1})
check("array", p("[1, 2, 3]") == [1, 2, 3])
check("code fence", p('```json\n{"a": 1}\n```') == {"a": 1})
check("trailing comma", p('{"a": 1,}') == {"a": 1})
check("over-escape จริง (Llama 3)", p('{\\"a\\": 1}') == {"a": 1})
check("None/True/False", p('{"a": None, "b": True}') == {"a": None, "b": True})
check("ข้อความว่าง", p("") is None)
check("ไม่ใช่ string", p(None) is None)

# ══ TEST 2: modeling path ไม่มีคอลัมน์ข่าวแล้วยังรันได้ ═════════════════════
print("\n[2] modeling path — ดึงฟังก์ชันซ้อนออกมารันบนข้อมูลสังเคราะห์")

LINES = io.open(NEW, encoding="utf-8").read().split("\n")


def grab(fname):
    """ดึงเฉพาะตัวฟังก์ชันซ้อนที่ต้องการ (indent 4 ระดับ) แล้ว dedent

    สไลซ์กว้างกว่านี้จะติดโค้ดของ forecast_trend เองที่มี return ลอยอยู่ -> SyntaxError
    """
    head = "    def " + fname + "("
    start = next(i for i, l in enumerate(LINES) if l.startswith(head))
    end = next(i for i in range(start + 1, len(LINES))
               if LINES[i].startswith("    def ")
               or (LINES[i].strip() and not LINES[i].startswith("    ")))
    return "\n".join(l[4:] if l.startswith("    ") else l for l in LINES[start:end])


block = "\n\n".join(grab(f) for f in ("create_features", "get_rolling_z_score", "run_all_models"))

# ใช้ globals ของ trend_final เองเป็นฐาน จะได้ resolve import ทุกตัวตรงตามที่โมดูลใช้จริง
ns = dict(vars(tf))
ns["pd"], ns["np"] = pd, np
exec(compile(block, "<nested>", "exec"), ns)
check("exec ฟังก์ชันซ้อนได้",
      all(f in ns for f in ("create_features", "get_rolling_z_score", "run_all_models")))

# ข้อมูลสังเคราะห์: 60 เดือน 2 คีย์เวิร์ด มีทั้งเทรนด์ขาขึ้นและฤดูกาล
rng = np.random.default_rng(42)
rows = []
dates = pd.date_range("2020-01-01", periods=60, freq="MS")
for kw_cid in ["niacinamide_0", "ceramide_1"]:
    base = np.linspace(20, 60, 60) + 10 * np.sin(np.arange(60) * 2 * np.pi / 12)
    for d, v in zip(dates, base + rng.normal(0, 3, 60)):
        rows.append({"kw_cluster_id": kw_cid, "start_date": d, "search_avg": max(v, 0),
                     "cluster_id": int(kw_cid[-1]), "cluster_name": "Test Cluster " + kw_cid[-1]})
df = pd.DataFrame(rows)
df["z_score"] = df.groupby("kw_cluster_id")["search_avg"].transform(ns["get_rolling_z_score"])

feat = ns["create_features"](df, target_col="z_score", group_col="kw_cluster_id")
check("create_features รันผ่าน", not feat.empty, str(len(feat)) + " แถว")

leftover = [c for c in feat.columns if "news" in c or "product_mention" in c]
check("ไม่มีคอลัมน์ข่าวหลงเหลือ", not leftover, str(leftover) if leftover else "ไม่มี")

FEATURE_COLS = ["lag_1", "lag_3", "lag_12", "rolling_mean_3m", "z_volatility_3m", "z_velocity"]
check("ฟีเจอร์ที่ต้องใช้ครบ 6 ตัว", all(c in feat.columns for c in FEATURE_COLS))

res = ns["run_all_models"](feat[feat.kw_cluster_id == "niacinamide_0"].copy(),
                           FEATURE_COLS, horizon=48, group_col="kw_cluster_id")
check("run_all_models รันผ่าน (recursive 48 เดือน)", not res.empty, str(len(res)) + " แถว")

if not res.empty:
    fc = res[res["Type"] == "Forecast"]["z_score"]
    check("มีผลพยากรณ์ออกมา", len(fc) > 0, str(len(fc)) + " จุด")
    check("ไม่มี NaN/inf", bool(np.isfinite(fc).all()))
    check("ไม่ระเบิด (|z| < 20)", bool(fc.abs().max() < 20), "max |z| = %.2f" % fc.abs().max())
    check("มีหลายโมเดลแข่งกัน", res["Model"].nunique() >= 3, str(sorted(res["Model"].unique())))

print("\n" + "=" * 60)
if fails:
    print("❌ ไม่ผ่าน %d ข้อ: %s" % (len(fails), fails))
    sys.exit(1)
print("✅ ผ่านทุกข้อ — Phase 0 แก้แล้วทำงานถูกต้อง (ไม่ได้ยิง API เลย)")
