# -*- coding: utf-8 -*-
"""
Phase 2 — เทียบคลัสเตอร์ 3 สาย (Paper, Social, News) แบบ pairwise

เกณฑ์วัดว่าสำเร็จตาม Phase 2 README: "แต่ละสายให้ผลต่างกันจริงไหม? ถ้าเห็นตรงกันหมดทุกเทรนด์ = แยกไปก็
เท่านั้น" - word-level Jaccard, ฟรี ไม่ใช้ LLM
"""
import json
import re
import sys
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import OUTPUTS  # noqa: E402

STOPWORDS = {"and", "or", "for", "with", "the", "a", "an", "of", "to", "in", "on", "body", "skin"}

# ชื่อสาย -> (ไฟล์จริง, ไฟล์ mockup สำรอง)  [mockup=None: ต้องมีไฟล์จริงเท่านั้น]
STREAMS = {
    "Paper": (OUTPUTS / "phase1_paper_stream_result.json", None),
    "Social": (OUTPUTS / "phase2_social_stream_result.json", None),
    "News": (OUTPUTS / "phase2_news_stream_result.json", None),
}


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
    return out, bool(data.get("_mockup"))


def resolve_streams():
    """เลือกไฟล์จริงถ้ามี ไม่งั้น fallback ไป mockup พร้อมพิมพ์เตือน"""
    resolved = {}
    any_mockup = False
    for name, (real_path, mock_path) in STREAMS.items():
        if real_path.exists():
            resolved[name] = real_path
            print(f"  ✅ {name}: ใช้ผลจริง -> {real_path.name}")
        elif mock_path and mock_path.exists():
            resolved[name] = mock_path
            any_mockup = True
            print(f"  🎭 {name}: ไม่มีผลจริง ใช้ MOCKUP แทน -> {mock_path.name}")
        else:
            print(f"  ❌ {name}: ไม่เจอทั้งไฟล์จริงและ mockup")
            return None, any_mockup
    return resolved, any_mockup


def compare(set_a, name_a, set_b, name_b):
    label = f"{name_a} vs {name_b}"
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
        print(f"  {a['name'][:45]:45s} -> {(best_name or '-')[:40]:40s} ({best_score:.3f})")
    avg = sum(scores) / len(scores) if scores else 0.0
    mx = max(scores) if scores else 0.0
    print(f"  เฉลี่ย: {avg:.3f}, สูงสุด: {mx:.3f}\n")
    return {"pair": label, "rows": rows, "avg": round(avg, 3), "max": round(mx, 3)}


if __name__ == "__main__":
    print("กำลังหาไฟล์ผลลัพธ์ของแต่ละสาย...")
    resolved, any_mockup = resolve_streams()
    if resolved is None:
        raise SystemExit(1)
    print()

    loaded = {}
    mockup_flags = {}
    for name, path in resolved.items():
        loaded[name], mockup_flags[name] = load_stream(path)
        print(f"{name}: {len(loaded[name])} คลัสเตอร์" + ("  🎭 MOCKUP" if mockup_flags[name] else ""))
    print()

    names = list(loaded.keys())
    results = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            results.append(compare(loaded[a], a, loaded[b], b))

    overall_max = max(r["max"] for r in results)
    verdict = "✅ ต่างกันชัดเจนทุกคู่" if overall_max < 0.2 else "🟡 มีความคล้ายบางส่วนในบางคู่"
    if any_mockup:
        verdict = "🎭 (มีข้อมูล mockup ปนอยู่ - ผลนี้ใช้ทดสอบโค้ดเท่านั้น ไม่ใช่ข้อสรุปจริง) " + verdict
    print(f"ข้อสรุป: {verdict}")

    out_path = OUTPUTS / ("phase2_all_streams_comparison_MOCKUP.json" if any_mockup
                           else "phase2_all_streams_comparison.json")
    out_path.write_text(json.dumps({
        "_contains_mockup_data": any_mockup,
        "streams_used": {name: str(path.name) for name, path in resolved.items()},
        "comparisons": results,
        "overall_max_overlap": overall_max,
        "verdict": verdict,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved -> {out_path}")
