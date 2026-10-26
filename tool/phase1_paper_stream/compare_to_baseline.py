# -*- coding: utf-8 -*-
"""
Phase 1 — เทียบคลัสเตอร์สาย Paper กับ baseline (ที่มาจากการเทข่าวทุกแหล่งรวมกันแบบเดิม)

เกณฑ์วัดว่าสำเร็จตาม Phase 1 README: "คลัสเตอร์จากสาย Paper ต่างจากคลัสเตอร์เดิมจริงไหม"
ถ้าออกมาเหมือนเดิมเป๊ะ = การแยกสายไม่ได้ประโยชน์ → หยุด ไม่ต้องไป Phase 2

วิธีวัด: keyword overlap แบบ deterministic (word-level Jaccard) ระหว่างคลัสเตอร์สาย Paper กับ
คลัสเตอร์ baseline แต่ละคู่ - ฟรี ไม่ใช้ LLM (แนวทางเดียวกับ market_gap_check.py ก่อนหน้านี้ใน
โปรเจกต์) ตามด้วยสรุปเชิงคุณภาพแบบสั้นๆ

baseline มาจาก: memory/analysis_logs/trend_result_Trend_Body_Wash_Thailand_2030_20260818_132149/
(ผลรันเต็ม pipeline ล่าสุดของหัวข้อเดียวกัน - ใช้ของที่มีอยู่แล้วแทนรันใหม่ทั้ง pipeline ซึ่งแพงกว่ามาก)
"""
import json
import re
import sys
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import PROJECT_ROOT, OUTPUTS  # noqa: E402

import pandas as pd  # noqa: E402

BASELINE_CSV = (PROJECT_ROOT / "memory" / "analysis_logs" /
                 "trend_result_Trend_Body_Wash_Thailand_2030_20260818_132149" /
                 "step3_kg_strategic_keywords.csv")
PHASE1_RESULT = OUTPUTS / "phase1_paper_stream_result.json"

STOPWORDS = {"and", "or", "for", "with", "the", "a", "an", "of", "to", "in", "on", "body", "skin"}


def tokenize(text):
    """แยกคำ ตัด stopword ทั่วไปที่ไม่ช่วยแยกแยะ (body/skin ปรากฏแทบทุกคลัสเตอร์อยู่แล้วเพราะเป็น
    หัวข้อหลัก ถ้าไม่ตัดจะพองคะแนน overlap เทียมๆ ทุกคู่)"""
    words = re.findall(r"[a-zA-Zก-๙]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def load_baseline():
    df = pd.read_csv(BASELINE_CSV)
    clusters = []
    for _, row in df.iterrows():
        text = " ".join(str(row.get(c, "")) for c in
                         ["Search_Keywords", "Marketing_Hooks", "Visual_Vibes", "Product_Search_Keywords"])
        clusters.append({"name": row["Trend Name"], "tokens": tokenize(text)})
    return clusters


def load_paper_clusters():
    data = json.loads(PHASE1_RESULT.read_text(encoding="utf-8"))
    clusters = []
    for t in data["trends"]:
        text = " ".join(str(t.get(c, "")) for c in
                         ["Trend Name", "Key Ingredients", "Key Benefits", "Members"])
        clusters.append({"name": t["Trend Name"], "tokens": tokenize(text),
                          "target": t.get("Target", ""), "outlook": t.get("Outlook", "")})
    return clusters


if __name__ == "__main__":
    if not PHASE1_RESULT.exists():
        print(f"❌ ยังไม่มีผล Phase 1 ที่ {PHASE1_RESULT} - รัน paper_stream.py ก่อน")
        raise SystemExit(1)
    if not BASELINE_CSV.exists():
        print(f"❌ ไม่เจอ baseline ที่ {BASELINE_CSV}")
        raise SystemExit(1)

    baseline = load_baseline()
    paper = load_paper_clusters()

    print(f"Baseline: {len(baseline)} คลัสเตอร์ (จาก run เต็ม pipeline เดิม)")
    print(f"Paper stream: {len(paper)} คลัสเตอร์ (จากสาย Paper อย่างเดียว)")
    print()

    rows = []
    for p in paper:
        best_score, best_name = 0.0, None
        for b in baseline:
            s = jaccard(p["tokens"], b["tokens"])
            if s > best_score:
                best_score, best_name = s, b["name"]
        rows.append({"Paper Cluster": p["name"], "Best Match (Baseline)": best_name,
                      "Overlap Score": round(best_score, 3)})

    df_out = pd.DataFrame(rows).sort_values("Overlap Score", ascending=False)
    print(df_out.to_string(index=False))
    print()

    avg = df_out["Overlap Score"].mean()
    max_score = df_out["Overlap Score"].max()
    print(f"Overlap เฉลี่ย: {avg:.3f} | Overlap สูงสุด: {max_score:.3f}")
    print()
    if max_score < 0.15:
        verdict = "✅ ต่างจาก baseline ชัดเจน (overlap ต่ำมากทุกคู่) - สาย Paper ให้มุมที่ baseline ไม่เห็น"
    elif max_score < 0.35:
        verdict = "🟡 ต่างจาก baseline พอสมควร (overlap ปานกลาง) - มีทั้งส่วนที่ทับและไม่ทับ"
    else:
        verdict = "🔴 ใกล้เคียง baseline มาก (overlap สูง) - การแยกสายอาจไม่ได้ประโยชน์เพิ่มมากนัก"
    print(f"ข้อสรุป (deterministic): {verdict}")

    out_path = OUTPUTS / "phase1_vs_baseline_comparison.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"baseline_n": len(baseline), "paper_n": len(paper),
                    "comparison": rows, "avg_overlap": avg, "max_overlap": max_score,
                    "verdict": verdict,
                    "baseline_names": [b["name"] for b in baseline],
                    "paper_names": [p["name"] for p in paper]}, f, ensure_ascii=False, indent=2)
    print(f"\nSaved -> {out_path}")
