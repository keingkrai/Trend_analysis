# -*- coding: utf-8 -*-
"""
เทียบผล ⑫ สองชุด (ผลเดิม vs ผลที่รันบนตลาดใหม่) ต่อเทรนด์ - ใช้ดูผลของการเปลี่ยนแคตตาล็อก (เช่น Konvy -> Konvy + Eve and Boy)
ก่อนตัดสินใจรันรายงานจริง ไม่เรียก API ไม่แตะผลทั้งสองฝั่ง

เทียบอะไร:
  - หมวดหลักที่ LLM เลือก (main_category) เปลี่ยนไหม + จำนวนสินค้าที่เทียบ (n_products_compared)
  - Top 5 / Top 15 ซ้ำกันกี่ชิ้น, ชิ้นที่เข้ามาใหม่มาจากร้านไหน (Konvy / Eve and Boy จาก market_product.csv)
  - สินค้าของแต่ละช่วงราคาในคอลัมน์หมวดหลัก (ต่ำ/กลาง/สูง): ตัวเด่นของช่วงเปลี่ยนไหม + จำนวนสินค้าในช่วง (n_total)
ใช้: python tool/phase3_supply_layer/compare_supply_runs.py <โฟลเดอร์รอบเดิม> <โฟลเดอร์รอบใหม่> [--out ไฟล์.md]
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

TOOL_DIR = Path(__file__).resolve().parent.parent
RESULT_NAME = "phase3_scale_validation_nvidia_result.json"
MARKET_CSV = TOOL_DIR / "product" / "market_product.csv"


def _key(p):
    return (p.get("brand"), p.get("product_name"))


def load_results(run_dir):
    with open(Path(run_dir) / RESULT_NAME, encoding="utf-8") as f:
        return json.load(f)


def retailer_lookup(csv_path=MARKET_CSV):
    """{(brand, product_name): retailer} จากแคตตาล็อกตลาด; ไม่มีไฟล์ = {}"""
    p = Path(csv_path)
    if not p.exists():
        return {}
    df = pd.read_csv(p, encoding="utf-8-sig", low_memory=False, usecols=["brand", "product_name", "retailer"])
    return {(b, n): r for b, n, r in zip(df["brand"], df["product_name"], df["retailer"])}


def _main_column(r):
    cats = (r.get("by_category") or {}).get("categories") or []
    return cats[0] if cats else None


def compare_trend(old, new, shop_of):
    """ผลของเทรนด์เดียว (dict ของ ⑫) สองชุด -> dict สรุปความต่าง"""
    o5, n5 = [_key(m) for m in old["top_matches"][:5]], [_key(m) for m in new["top_matches"][:5]]
    o15, n15 = [_key(m) for m in old["top_matches"][:15]], [_key(m) for m in new["top_matches"][:15]]
    entered5 = [m for m in new["top_matches"][:5] if _key(m) not in set(o5)]
    out = {
        "trend": new["trend_name"],
        "main_old": (old.get("main_category") or {}).get("category"),
        "main_new": (new.get("main_category") or {}).get("category"),
        "n_old": old.get("n_products_compared"), "n_new": new.get("n_products_compared"),
        "same_top1": bool(o5 and n5 and o5[0] == n5[0]),
        "overlap5": len(set(o5) & set(n5)), "overlap15": len(set(o15) & set(n15)),
        "entered5": [(m["brand"], m["product_name"], shop_of.get(_key(m), "?"), m["similarity"]) for m in entered5],
        "new_top5_from_eve": sum(1 for m in new["top_matches"][:5] if shop_of.get(_key(m)) == "Eve and Boy"),
        "tiers": [],
    }
    co, cn = _main_column(old), _main_column(new)
    if co and cn and co["group"] == cn["group"]:
        for to, tn in zip(co.get("price_tiers") or [], cn.get("price_tiers") or []):
            po, pn = (to.get("product") or {}), (tn.get("product") or {})
            out["tiers"].append({"tier": tn["label"], "n_old": to.get("n_total"), "n_new": tn.get("n_total"),
                                 "best_old": (po.get("brand"), po.get("product_name")),
                                 "best_new": (pn.get("brand"), pn.get("product_name")),
                                 "best_new_shop": shop_of.get((pn.get("brand"), pn.get("product_name")), "?"),
                                 "same_best": _key(po) == _key(pn)})
    out["column_changed"] = bool(co and cn and co["group"] != cn["group"])
    return out


def compare_runs(old_dir, new_dir, shop_of=None):
    old, new = load_results(old_dir), load_results(new_dir)
    shop_of = retailer_lookup() if shop_of is None else shop_of
    rows = []
    for key, r_new in new["results"].items():
        r_old = old["results"].get(key)
        if r_old is None:
            continue
        rows.append(compare_trend(r_old, r_new, shop_of))
    meta = {"n_products_old": old.get("n_products_total"), "n_products_new": new.get("n_products_total")}
    return rows, meta


def render_markdown(rows, meta, old_name, new_name):
    L = [f"# เทียบ ⑫: {old_name} -> {new_name}", "",
         f"ตลาด (Beauty): {meta['n_products_old']} -> {meta['n_products_new']} SKU", "",
         "| เทรนด์ | หมวดหลัก | สินค้าที่เทียบ | Top1 เดิม | Top5 ซ้ำ | Top15 ซ้ำ | Top5 มาจาก Eve |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        main = r["main_old"] if r["main_old"] == r["main_new"] else f"{r['main_old']} → {r['main_new']}"
        L.append(f"| {r['trend']} | {main} | {r['n_old']} → {r['n_new']} | {'ใช่' if r['same_top1'] else 'เปลี่ยน'} | "
                 f"{r['overlap5']}/5 | {r['overlap15']}/15 | {r['new_top5_from_eve']} |")
    L += ["", "## สินค้าที่เข้า Top 5 ใหม่", ""]
    for r in rows:
        if r["entered5"]:
            L.append(f"**{r['trend']}**")
            for b, n, shop, sim in r["entered5"]:
                L.append(f"- {b} — {n} ({shop}, similarity {sim})")
            L.append("")
    L += ["## ตัวเด่นรายช่วงราคาในคอลัมน์หมวดหลัก", "", "| เทรนด์ | ช่วง | สินค้าในช่วง | ตัวเด่นเดิม | ตัวเด่นใหม่ |", "|---|---|---|---|---|"]
    for r in rows:
        for t in r["tiers"]:
            same = "(เหมือนเดิม)" if t["same_best"] else f"{t['best_new'][0]} — {t['best_new'][1]} [{t['best_new_shop']}]"
            L.append(f"| {r['trend']} | {t['tier']} | {t['n_old']} → {t['n_new']} | {t['best_old'][0]} — {t['best_old'][1]} | {same} |")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description="เทียบผล ⑫ สองรอบ")
    ap.add_argument("old_dir")
    ap.add_argument("new_dir")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    rows, meta = compare_runs(args.old_dir, args.new_dir)
    md = render_markdown(rows, meta, Path(args.old_dir).name, Path(args.new_dir).name)
    if args.out:
        args.out.write_text(md, encoding="utf-8")
        print(f"บันทึก {args.out}")
    print(md)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
