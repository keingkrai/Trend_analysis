# -*- coding: utf-8 -*-
"""
รวมแคตตาล็อก Konvy + Eve and Boy เป็น "แคตตาล็อกตลาด" ไฟล์เดียว (market_product.csv) - schema เดียวกับ konvy_product.csv
จึงอ่านผ่าน euromonitor_mapping.load_catalog() เดิมได้ - euromonitor_mapping.CSV_PATH ชี้มาที่ไฟล์นี้ตั้งแต่ 2026-10-15

กฎ (เจ้าของงานเลือก 2026-10-15):
  1. ตัดแถว stock <= 0 ทั้งสองร้าน (สินค้าที่ซื้อไม่ได้ไม่ควรถูกแนะนำ/ใช้เป็นหลักฐานตลาด) - ตัดก่อนรวมซ้ำ
     สินค้าที่หมดร้านหนึ่งแต่มีอีกร้าน จึงยังอยู่ (แถวของร้านที่มีของ); --keep-oos-brands ยกเว้นแบรนด์ (เช่น แบรนด์ลูกค้า)
  2. ตัดคอนแทคเลนส์ที่ติดป้ายผิดเป็นเครื่องสำอาง (is_lens จาก build_eve_catalog.py)
  3. สินค้าเดียวกันสองร้าน -> เหลือแถวเดียว เก็บแถว Konvy (มี sold/rating/size_std จากผู้ให้ข้อมูล) แล้วจดว่าขายที่ Eve ด้วย
     (also_on, eve_price, eve_url) - "สินค้าเดียวกัน" = แบรนด์เดียวกัน (ตามตาราง config/brand_aliases.json) + คำในชื่อเหมือนกันทุกคำ
     (เลขเฉดนับเป็นคำ) + ขนาดรวม (size_std) เท่ากัน + ราคาห่างกันไม่เกิน 3 เท่า; ขนาดใช้ไม่ได้ = ไม่รวม
     หลักการ: ไม่แน่ใจ = ไม่รวม (ซ้ำเหลือไว้ดีกว่ารวมเฉดต่างกันผิด); ไม่ทำ fuzzy match เพราะเฉด/สีต่างกันแต่ชื่อเกือบเหมือนกัน
  4. ชื่อแบรนด์ของ Eve ที่ตรงกับ Konvy (ตัวพิมพ์/alias) ใช้การสะกดของ Konvy เพื่อให้รายงานรวมแบรนด์เดียวกันไว้ด้วยกัน
     (ชื่อเดิมอยู่ใน brand_listing)
  5. คอลัมน์ `ingredients` ของ Eve (รายการ INCI ดิบ) เปลี่ยนเป็น `ingredients_raw` เพื่อให้ embed ด้วย Ingredient_Functions เหมือน Konvy
     (ข้อความ embed รูปแบบเดียวกันทั้งตลาด)

ผลลัพธ์: market_product.csv, market_product_pairs.csv (คู่ที่รวม - ไว้ตรวจ), market_product_summary.json
ใช้: python tool/product/build_market_catalog.py [--keep-oos-brands "Eucerin,MizuMi"] [--no-stock-filter]
     ตลาด Konvy ล้วน (ทดลอง 2026-10-19): ... --no-eve --out <ไฟล์อื่น>.csv
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

TOOL_DIR = Path(__file__).resolve().parent.parent
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

from product import size_standardiser as ss  # noqa: E402

HERE = Path(__file__).resolve().parent
KONVY_CSV = HERE / "konvy_product.csv"
EVE_CSV = HERE / "eveandboy_product.csv"
OUT_CSV = HERE / "market_product.csv"
PAIRS_CSV = HERE / "market_product_pairs.csv"
SUMMARY_JSON = HERE / "market_product_summary.json"
ALIASES_JSON = TOOL_DIR.parent / "config" / "brand_aliases.json"

KONVY, EVE = "Konvy", "Eve and Boy"
MAX_PRICE_RATIO = 3.0
_STOP = {"and", "the", "for", "with", "of", "in", "by", "x", "new", "pcs", "pc"}
_NON_WORD_RE = re.compile(r"[^\w฀-๿]+")


def norm_brand(s):
    """ชื่อแบรนด์ -> คีย์เทียบ: ตัวพิมพ์เล็ก ตัดทุกอย่างที่ไม่ใช่ตัวอักษร/ตัวเลข"""
    return re.sub(r"[^0-9a-z฀-๿]", "", str(s if s is not None else "").lower())


def load_aliases(path=ALIASES_JSON):
    """{คีย์ชื่อที่ร้านอื่นเขียน: ชื่อแบรนด์ตามที่ Konvy เขียน}; ไม่มีไฟล์ = {}"""
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8")).get("aliases", {})
    return {norm_brand(alias): canon for canon, aliases in data.items() for alias in aliases}


def spelling_by_key(brands):
    """รายชื่อแบรนด์ (Series ของแถว) -> {คีย์: การสะกดที่พบบ่อยที่สุด}"""
    counts = pd.Series(list(brands)).dropna().astype(str).value_counts()
    out = {}
    for name, _ in counts.items():          # เรียงจากมากไปน้อย -> ตัวแรกที่เจอชนะ
        out.setdefault(norm_brand(name), name)
    return out


def name_tokens(name, brand_names=()):
    """ชื่อสินค้า -> frozenset คำที่ใช้เทียบ: ตัดนิพจน์ขนาด (30ml, 4g, [1 Pair]) / ชื่อแบรนด์ / stopword แล้ว
    เลขเฉดคงไว้ (ตัดศูนย์นำหน้า "02" = "2") เพื่อไม่ให้เฉดต่างกันถูกรวม; "SPF50+ PA++++" = "spf50 pa" """
    s = ss._SIZE_RE.sub(" ", str(name if name is not None else "").lower())
    s = s.replace("+", "")
    drop = set(_STOP)
    for b in brand_names:
        drop.update(w for w in _NON_WORD_RE.split(str(b).lower()) if w)
    out = set()
    for w in _NON_WORD_RE.split(s):
        if not w or w in drop:
            continue
        if w.isdigit():
            w = w.lstrip("0") or "0"
        out.add(w)
    return frozenset(out)


def _size_key(size_std, flag):
    if flag not in ss.USABLE_FLAGS or pd.isna(size_std):
        return None
    return round(float(size_std), 2)


def dedup_key(brand_key, name, brand_names, size_std, unit_std, flag):
    """คีย์สินค้าเดียวกันข้ามร้าน; None = ขนาดใช้ไม่ได้/ชื่อว่าง -> ไม่เอาไปรวม"""
    size = _size_key(size_std, flag)
    toks = name_tokens(name, brand_names)
    if size is None or not toks or not brand_key:
        return None
    return (brand_key, toks, size, unit_std if isinstance(unit_std, str) else "")


def _in_stock(df):
    return pd.to_numeric(df["stock"], errors="coerce").fillna(0) > 0


def merge_catalogs(konvy, eve, aliases=None, keep_oos_brands=(), stock_filter=True, include_eve=True):
    """(konvy df, eve df จาก eveandboy_product.csv) -> (merged df, pairs df, summary dict); ไม่แก้ input
    🆕 (2026-10-19) include_eve=False = ตลาด Konvy ล้วน: ทิ้งแถว Eve ทั้งหมดแต่ใช้กฎเดียวกัน (ตัดแถวไม่มีป้าย Industry / สต็อกหมด ยกเว้น
    keep_oos_brands) และได้คอลัมน์ชุดเดียวกับตลาดรวม จึงอ่านผ่าน load_catalog() เดิมได้ - embedding cache ใช้ต่อได้ (ผูกกับเนื้อหาสินค้า)"""
    aliases = load_aliases() if aliases is None else aliases
    keep_keys = {norm_brand(b) for b in keep_oos_brands}
    summary = {"konvy_rows_in": int(len(konvy)), "eve_rows_in": int(len(eve)), "stock_filter": bool(stock_filter),
               "keep_oos_brands": sorted(keep_oos_brands), "include_eve": bool(include_eve)}
    if not include_eve:
        eve = eve.iloc[0:0]

    k = konvy.copy()
    e = eve.copy()
    k["retailer"] = KONVY
    e["retailer"] = EVE

    # 1) ชื่อแบรนด์ของ Eve -> การสะกดของ Konvy (ตัวพิมพ์/alias); เก็บชื่อเดิมไว้
    spell = spelling_by_key(k["brand"])
    e["brand_listing"] = e["brand"]

    def canon(b):
        key = norm_brand(b)
        if key in aliases:
            return aliases[key]
        return spell.get(key, b)
    e["brand"] = [canon(b) for b in e["brand"]]

    # 2) ตัดแถวที่ไม่มีป้าย Industry เลย (จัดหมวดไม่ได้ เช่น "Miscellaneous Cartridges") + เลนส์ + stock
    for df, name in ((k, "konvy"), (e, "eve")):
        unlabelled = df["Industry"].isna() | (df["Industry"].astype(str).str.strip() == "")
        summary[f"{name}_unlabelled_dropped"] = int(unlabelled.sum())
        if name == "konvy":
            k = k[~unlabelled]
        else:
            e = e[~unlabelled]
    if "is_lens" in e.columns:
        lens = e["is_lens"].fillna(False).astype(bool)
        summary["eve_lens_dropped"] = int(lens.sum())
        e = e[~lens]
    if stock_filter:
        for df, name in ((k, "konvy"), (e, "eve")):
            keep = _in_stock(df) | df["brand"].map(lambda b: norm_brand(b) in keep_keys)
            summary[f"{name}_oos_dropped"] = int((~keep).sum())
            if name == "konvy":
                k = k[keep]
            else:
                e = e[keep]

    # 3) สินค้าเดียวกัน -> เหลือแถว Konvy
    def keys(df):
        out = []
        for b, bl, n, s, u, f in zip(df["brand"], df.get("brand_listing", df["brand"]), df["product_name"], df["size_std"],
                                     df["unit_std"], df["size_flag"]):
            out.append(dedup_key(norm_brand(b), n, (b, bl), s, u, f))
        return out
    k_keys = keys(k)
    e_keys = keys(e)
    index = {}
    for pos, key in enumerate(k_keys):
        if key is not None:
            index.setdefault(key, []).append(pos)

    k_price = pd.to_numeric(k["sale_price_thb"], errors="coerce").tolist()
    e_price = pd.to_numeric(e["sale_price_thb"], errors="coerce").tolist()
    drop_e, pairs = set(), []
    k_extra = {}
    for epos, key in enumerate(e_keys):
        if key is None or key not in index:
            continue
        for kpos in index[key]:
            kp, ep = k_price[kpos], e_price[epos]
            if kp and ep and kp > 0 and ep > 0 and max(kp, ep) / min(kp, ep) > MAX_PRICE_RATIO:
                continue
            drop_e.add(epos)
            if kpos not in k_extra:
                row = e.iloc[epos]
                k_extra[kpos] = {"also_on": EVE, "eve_price": ep, "eve_url": row.get("product_url"),
                                 "eve_product_id": row.get("product_id")}
            pairs.append({"brand": k.iloc[kpos]["brand"], "konvy_name": k.iloc[kpos]["product_name"],
                          "eve_name": e.iloc[epos]["product_name"], "size_std": key[2], "konvy_price": kp, "eve_price": ep})
            break
    summary["duplicates_merged"] = len(drop_e)
    e = e.iloc[[i for i in range(len(e)) if i not in drop_e]]
    for col in ("also_on", "eve_price", "eve_url", "eve_product_id"):
        k[col] = None
    for kpos, vals in k_extra.items():
        for col, v in vals.items():
            k.iloc[kpos, k.columns.get_loc(col)] = v

    # 4) ส่วนผสมดิบของ Eve ไม่เข้า embed (ใช้ Ingredient_Functions เหมือน Konvy)
    if "ingredients" in e.columns:
        e = e.rename(columns={"ingredients": "ingredients_raw"})
    if "ingredients" in k.columns:
        k = k.rename(columns={"ingredients": "ingredients_raw"})

    merged = pd.concat([k, e], ignore_index=True, sort=False)
    # product_id ต้องไม่ซ้ำข้ามร้าน (ใช้เป็นกุญแจใน brand_data / report_data)
    merged["product_id"] = merged["product_id"].astype(str)
    if merged["product_id"].duplicated().any():
        dup = merged["product_id"].duplicated(keep=False)
        merged.loc[dup & (merged["retailer"] == EVE), "product_id"] = "EVE-" + merged.loc[dup & (merged["retailer"] == EVE), "product_id"]
    summary.update({
        "rows_out": int(len(merged)), "konvy_rows_out": int((merged["retailer"] == KONVY).sum()),
        "eve_rows_out": int((merged["retailer"] == EVE).sum()), "konvy_rows_also_on_eve": int(len(k_extra)),
        "brands_out": int(merged["brand"].nunique()),
    })
    return merged, pd.DataFrame(pairs), summary


def main():
    ap = argparse.ArgumentParser(description="รวม konvy_product.csv + eveandboy_product.csv -> market_product.csv")
    ap.add_argument("--konvy", type=Path, default=KONVY_CSV)
    ap.add_argument("--eve", type=Path, default=EVE_CSV)
    ap.add_argument("--out", type=Path, default=OUT_CSV)
    ap.add_argument("--keep-oos-brands", default="", help="แบรนด์ที่ไม่ตัดแถวสต็อกหมด คั่นด้วยจุลภาค (เช่น แบรนด์ลูกค้า)")
    ap.add_argument("--no-stock-filter", action="store_true", help="ไม่ตัดแถว stock<=0")
    ap.add_argument("--no-eve", action="store_true",
                    help="ตลาด Konvy ล้วน (ไม่รวมแถว Eve) - ใช้คู่กับ --out ไปไฟล์อื่น; ไฟล์คู่ (_pairs / _summary) เขียนข้าง --out")
    args = ap.parse_args()

    print("อ่านแคตตาล็อก ...")
    konvy = pd.read_csv(args.konvy, encoding="utf-8-sig", low_memory=False)
    # --no-eve: อ่านแค่หัวตาราง Eve (ไม่มีแถว) เพื่อให้ผลมีคอลัมน์ครบเท่าตลาดรวม
    eve = pd.read_csv(args.eve, encoding="utf-8-sig", low_memory=False, nrows=0 if args.no_eve else None)
    keep = [b.strip() for b in args.keep_oos_brands.split(",") if b.strip()]
    merged, pairs, summary = merge_catalogs(konvy, eve, keep_oos_brands=keep, stock_filter=not args.no_stock_filter,
                                            include_eve=not args.no_eve)
    # ไฟล์คู่ไปข้าง --out เสมอเมื่อไม่ใช่ที่อยู่ปกติ - ทดลองไฟล์อื่นต้องไม่ทับ market_product_pairs.csv / market_product_summary.json จริง
    pairs_path, summary_path = (PAIRS_CSV, SUMMARY_JSON) if args.out == OUT_CSV else (
        args.out.with_name(args.out.stem + "_pairs.csv"), args.out.with_name(args.out.stem + "_summary.json"))
    merged.to_csv(args.out, index=False, encoding="utf-8-sig")
    pairs.to_csv(pairs_path, index=False, encoding="utf-8-sig")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"บันทึก {args.out.name}: {len(merged)} แถว")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
