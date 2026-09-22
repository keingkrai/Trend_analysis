# -*- coding: utf-8 -*-
"""
Phase 2 — เทียบคลัสเตอร์สาย Social กับสาย Paper (Phase 1) และ baseline (pipeline เดิม)

เกณฑ์วัดว่าสำเร็จตาม Phase 2 README: "3 หมวดให้ผลต่างกันจริงไหม? ถ้าเห็นตรงกันหมดทุกเทรนด์ = แยกไปก็
เท่านั้น" - ใช้ตรรกะเดียวกับ phase1_paper_stream/compare_to_baseline.py (word-level Jaccard, ฟรี
ไม่ใช้ LLM)
"""
import csv
import json
import re
import sys
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import PROJECT_ROOT, OUTPUTS  # noqa: E402

BASELINE_CSV = (PROJECT_ROOT / "memory" / "analysis_logs" /
                 "trend_result_Trend_Body_Wash_Thailand_2030_20260818_132149" /
                 "step3_kg_strategic_keywords.csv")
SOCIAL_JSON = OUTPUTS / "phase2_social_stream_result.json"
PAPER_JSON = OUTPUTS / "phase1_paper_stream_result.json"

STOPWORDS = {"and", "or", "for", "with", "the", "a", "an", "of", "to", "in", "on", "body", "skin"}


def tokenize(text):
    words = re.findall(r"[a-zA-Zก-๙]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_stream(path, fields=("Key Ingredients", "Key Benefits")):
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for t in data["trends"]:
        text = " ".join(str(t.get(f, "")) for f in ("Trend Name",) + fields)
        out.append({"name": t["Trend Name"], "tokens": tokenize(text)})
    return out


def load_baseline():
    out = []
    with open(BASELINE_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            text = " ".join(str(row.get(c, "")) for c in
                             ["Trend Name", "Search_Keywords", "Marketing_Hooks",
                              "Visual_Vibes", "Product_Search_Keywords"])
            out.append({"name": row["Trend Name"], "tokens": tokenize(text)})
    return out


def compare(set_a, set_b, label):
    print(f"=== {label} ===")
    rows, scores = [], []
    for a in set_a:
        best_score, best_name = 0.0, None
        for b in set_b:
            s = jaccard(a["tokens"], b["tokens"])
            if s > best_score:
                best_score, best_name = s, b["name"]
        scores.append(best_score)
        rows.append({"from": a["name"], "best_match": best_name, "score": round(best_score, 3)})
        print(f"  {a['name'][:50]:50s} -> {(best_name or '-')[:40]:40s} ({best_score:.3f})")
    avg = sum(scores) / len(scores) if scores else 0.0
    mx = max(scores) if scores else 0.0
    print(f"  เฉลี่ย: {avg:.3f}, สูงสุด: {mx:.3f}\n")
    return {"rows": rows, "avg": avg, "max": mx}


if __name__ == "__main__":
    for p in (SOCIAL_JSON, PAPER_JSON, BASELINE_CSV):
        if not Path(p).exists():
            print(f"❌ ไม่เจอ {p}")
            raise SystemExit(1)

    social = load_stream(SOCIAL_JSON)
    paper = load_stream(PAPER_JSON)
    baseline = load_baseline()
    print(f"Social: {len(social)} คลัสเตอร์ | Paper: {len(paper)} คลัสเตอร์ | Baseline: {len(baseline)} คลัสเตอร์\n")

    r1 = compare(social, paper, "Social vs Paper")
    r2 = compare(social, baseline, "Social vs Baseline")

    verdict = "✅ ต่างกันชัดเจนทั้งคู่" if max(r1["max"], r2["max"]) < 0.2 else "🟡 มีความคล้ายบางส่วน"
    print(f"ข้อสรุป: {verdict}")

    out_path = OUTPUTS / "phase2_social_vs_others_comparison.json"
    out_path.write_text(json.dumps({
        "social_vs_paper": r1, "social_vs_baseline": r2, "verdict": verdict,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved -> {out_path}")
