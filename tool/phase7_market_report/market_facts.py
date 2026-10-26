# -*- coding: utf-8 -*-
"""
⑲ รายงานส่วนแบ่งตลาด — Phase 1: คำนวณข้อเท็จจริงจาก Euromonitor + อย. (โค้ดล้วน ไม่เรียก LLM/API)

ตัวเลขทุกตัวในรายงานมาจากไฟล์นี้ - ขั้นต่อไป (ตั้งคำถาม / ค้นเว็บ / LLM สรุป) ใช้ข้อเท็จจริงที่นี่เป็นฐาน LLM ไม่คิดเลขเอง

ต่อหมวด (ทั้งตลาด + 11 หมวดสินค้า):
    brands   แบรนด์ใหญ่เรียงตามส่วนแบ่งปีล่าสุด, ส่วนแบ่ง Others / Private Label / top 5 รายปี, แบรนด์ที่เพิ่งมีชื่อในข้อมูล,
             movers (เปลี่ยนมากที่สุดทั้งขึ้นและลง - ใช้ภายในระบบเลือกเรื่องที่จะค้น ไม่แสดงเป็นอันดับ)
    channel  ช่องทางขายระดับใบ (รวมกันได้ 100%) ส่วนแบ่งปีตั้งต้น -> ปีล่าสุด
    premium  สัดส่วน premium รายปีถึงปีคาดการณ์ (มีแค่ 8 หมวด)
    fda      ใบจดแจ้งต่อปี (เฉพาะปีที่ครบ 12 เดือน + ปีล่าสุดเทียบเดือนเดียวกันของปีก่อน), สัดส่วนนำเข้า,
             สัดส่วนของแบรนด์ที่ Euromonitor ไม่ได้ติดตาม, แบรนด์ใหม่ (มีแค่ 5 หมวดที่แปลงหมวด อย. ได้ + ทั้งตลาด)
ปัจจัย (factors) = การเปลี่ยนแปลงระดับหมวดที่เกินเกณฑ์ใน config/market_report.json - ชนิดที่วัดจากข้อมูลได้:
    channel_shift / concentration / premium_shift / launch_activity
    (ชนิดที่ต้องมีหลักฐานจากเว็บ เช่น การวางตำแหน่งเวชสำอาง การตลาด การขยายจุดขาย เติมใน Phase 2-3)

รายงานไม่ตัดสินว่าแบรนด์ไหนชนะ/แพ้ (เจ้าของงานขอ 2026-10-12) - ไฟล์นี้จึงเรียงแบรนด์ตามขนาดส่วนแบ่ง ไม่ใช่ตามการเปลี่ยนแปลง

ผลลัพธ์:
    output/<รอบ>/phase7_market_facts.json

Usage:
    python tool/phase7_market_report/market_facts.py                  # รอบใหม่ output/market_share_<วันเวลา>/
    python tool/phase7_market_report/market_facts.py --run <ชื่อรอบ>   # เขียนทับข้อเท็จจริงของรอบเดิม
    python tool/phase7_market_report/market_facts.py --no-fda         # ไม่ใช้ข้อมูล อย. (ไม่ต้องรอโหลด ~2.5 นาทีครั้งแรก)
"""
import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from market_data import (AGGREGATE_BRANDS, FDA_CATEGORY_MAP, PRODUCT_CATEGORIES, TOTAL_CATEGORY,  # noqa: E402
                         brand_key, brand_key_text, load_euromonitor, load_fda, source_info, thai_brand_names)

PROJECT_ROOT = HERE.parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "output"
CONFIG_PATH = PROJECT_ROOT / "config" / "market_report.json"
FACTS_FILE = "phase7_market_facts.json"
SEGMENTS = ("Premium Beauty and Personal Care", "Mass Beauty and Personal Care")
ECOMMERCE = "Retail E-Commerce"
DEFAULTS = {"base_year": 2019, "last_year": None, "forecast_year": 2030, "top_brands": 10, "mover_min_share": 0.5,
            "movers_per_category": 6, "channel_min_change_pp": 1.0, "concentration_min_change_pp": 1.0,
            "premium_min_change_pp": 1.0, "launch_min_change_pct": 10, "fda_new_brand_from": 2022,
            "fda_top_new_brands": 10}


def load_config(path=CONFIG_PATH):
    cfg = dict(DEFAULTS)
    if Path(path).exists():
        cfg.update({k: v for k, v in json.loads(Path(path).read_text(encoding="utf-8")).items()
                    if not k.startswith("_")})
    return cfg


# ---------------------------------------------------------------------------
# ตัวช่วยตัวเลข
# ---------------------------------------------------------------------------

def _num(x, nd=2):
    """ตัวเลขสำหรับ JSON: NaN/None -> None, numpy -> float ปัดทศนิยม"""
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) else round(x, nd)


def cagr(v0, v1, years):
    """อัตราโตเฉลี่ยต่อปี (%) - ค่าไม่ครบ/ไม่เป็นบวก = None"""
    if v0 is None or v1 is None or years <= 0 or v0 <= 0 or v1 < 0:
        return None
    return ((v1 / v0) ** (1 / years) - 1) * 100


def _at(series, year):
    """ค่าของปีจาก Series ที่ index เป็นปี - ไม่มี/NaN = None"""
    if year not in series.index:
        return None
    v = series.loc[year]
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


def _yearly(series, nd=2):
    return {str(int(y)): _num(v, nd) for y, v in series.items()}


# ---------------------------------------------------------------------------
# ขนาดตลาด
# ---------------------------------------------------------------------------

def size_facts(market, category, base, last, horizon):
    """มูลค่า (ล้านบาท) ปีตั้งต้น/ล่าสุด/คาดการณ์ + อัตราโตเฉลี่ยต่อปี (ราคาปัจจุบัน / ตัดเงินเฟ้อ / ช่วงคาดการณ์)"""
    s = market[market["category"] == category].set_index("year")
    if s.empty:
        return None
    total = market[market["category"] == TOTAL_CATEGORY].set_index("year")["value"]
    v, real = s["value"], s["value_real"]
    last_total = _at(total, last)
    return {
        "value": {str(y): _num(_at(v, y), 0) for y in (base, last, horizon)},
        "series": _yearly(v, 1),
        "cagr_hist": _num(cagr(_at(v, base), _at(v, last), last - base)),
        "cagr_hist_real": _num(cagr(_at(real, base), _at(real, last), last - base)),
        "cagr_forecast": _num(cagr(_at(v, last), _at(v, horizon), horizon - last)),
        "share_of_total": _num(_at(v, last) / last_total * 100 if last_total and _at(v, last) else None),
    }


# ---------------------------------------------------------------------------
# ส่วนแบ่งแบรนด์
# ---------------------------------------------------------------------------

def brand_tiers(brand, year):
    """แบรนด์ -> "premium" / "mass" / "both" จากการมีส่วนแบ่งในหมวดรวม Premium / Mass ของ Euromonitor ปีนั้น"""
    d = brand[(brand["year"] == year) & (brand["share"] > 0) & brand["category"].isin(SEGMENTS)]
    prem = set(d.loc[d["category"] == SEGMENTS[0], "brand"])
    mass = set(d.loc[d["category"] == SEGMENTS[1], "brand"])
    return {b: ("both" if b in prem and b in mass else "premium" if b in prem else "mass") for b in prem | mass}


NAME_STOPWORDS = {"THE", "AND", "FOR", "MEN", "WOMEN", "BABY", "KIDS", "PARIS", "BEAUTY"}


def _name_words(name):
    """คำหลักของชื่อแบรนด์ (ตัดเครื่องหมายเสียงละติน, ตัวใหญ่, ยาว >= 3, ไม่ใช่คำทั่วไป) - Johnson's -> {JOHNSONS}"""
    words = re.split(r"\s+", re.sub(r"[^0-9A-Z\s]", "", brand_key_text(name)))
    return {w for w in words if len(w) >= 3 and w not in NAME_STOPWORDS}


def merged_into(named, owners, brand, last_seen, min_ratio=0.5):
    """แบรนด์ที่หายไปหลังปี last_seen ถูกรวมเข้าแบรนด์ไหน = แบรนด์ของเจ้าของเดียวกันที่มีคำหลักในชื่อร่วมกัน และส่วนแบ่งปีถัดไป
    เพิ่ม >= min_ratio x ส่วนแบ่งสุดท้ายของแบรนด์ที่หาย (Johnson's -> Johnson's Baby, The History of Whoo -> The Whoo)
    ต้องมีชื่อร่วมเพราะบริษัทใหญ่มีหลายแบรนด์ที่โตเองในปีเดียวกันได้ (L'Oréal Men Expert ไม่ได้ไปอยู่ใน La Roche-Posay)
    ไม่เข้าเงื่อนไข = None คือ Euromonitor เลิกแยก"""
    nxt = last_seen + 1
    if nxt not in named.columns or last_seen not in named.columns:
        return None
    lost = named.at[brand, last_seen]
    words = _name_words(brand)
    same_owner = [o for o in named.index
                  if o != brand and owners.get(o) == owners.get(brand) and words & _name_words(o)]
    if not same_owner:
        return None
    jump = (named.loc[same_owner, nxt].fillna(0) - named.loc[same_owner, last_seen].fillna(0))
    return jump.idxmax() if jump.max() >= lost * min_ratio else None


def brand_facts(brand, category, base, last, cfg, tiers=None):
    """แบรนด์ใหญ่ (เรียงตามส่วนแบ่งปีล่าสุด), ความกระจุกตัว, แบรนด์ที่เพิ่งมีชื่อ, movers ของหมวด"""
    tiers = tiers or {}
    d = brand[brand["category"] == category]
    piv = d.pivot_table(index="brand", columns="year", values="share", aggfunc="first")   # "sum" เปลี่ยน NaN เป็น 0
    owners = d.groupby("brand")["owner"].first()
    named = piv.loc[[b for b in piv.index if b not in AGGREGATE_BRANDS]]
    s_base = named[base].fillna(0) if base in named else named[last] * 0
    s_last = named[last].fillna(0)
    s_prev = named[last - 1].fillna(0) if last - 1 in named else s_last * 0

    # แบรนด์ที่หายจากรายชื่อ (มีส่วนแบ่งปีตั้งต้น ไม่มีปีล่าสุด) มี 2 แบบ:
    #   merged_into = แบรนด์ของเจ้าของเดียวกันที่รับส่วนแบ่งไป (Johnson's -> Johnson's Baby 2023, The History of Whoo -> The Whoo)
    #   None        = Euromonitor เลิกแยก ส่วนแบ่งไปรวมใน Others (Others เพิ่มโดยตลาดไม่ได้กระจายตัวจริง เช่น Fragrances 2023)
    dropped = []
    for b in s_base[(s_base > 0) & (s_last == 0)].sort_values(ascending=False).index:
        seen = int(named.loc[b][named.loc[b] > 0].index.max())
        dropped.append({"brand": b, "share_base": _num(s_base[b]), "last_year_seen": seen,
                        "merged_into": merged_into(named, owners, b, seen)})
    absorbed = {}
    for x in dropped:
        if x["merged_into"]:
            absorbed.setdefault(x["merged_into"], []).append(x["brand"])

    def comparable(s):
        """ส่วนแบ่งปีก่อนหน้าแบบเทียบกันได้: แบรนด์ที่รับการรวมนับส่วนแบ่งของแบรนด์ที่รวมเข้ามาด้วย"""
        s = s.copy()
        for target, sources in absorbed.items():
            s[target] += s[sources].sum()
        return s

    c_base, c_prev = comparable(s_base), comparable(s_prev)

    def entry(b):
        e = {"brand": b, "owner": owners.get(b), "tier": tiers.get(b),
             "share_base": _num(c_base[b]), "share_last": _num(s_last[b]),
             "change_pp": _num(s_last[b] - c_base[b]), "change_pp_1y": _num(s_last[b] - c_prev[b])}
        if b in absorbed:
            e["absorbed"] = absorbed[b]   # share_base / change_pp รวมแบรนด์เหล่านี้แล้ว
        return e

    top = [{**entry(b), "rank": i + 1, "series": _yearly(named.loc[b])}
           for i, b in enumerate(s_last[s_last > 0].sort_values(ascending=False).head(cfg["top_brands"]).index)]
    new = [{**entry(b), "first_year": int(named.loc[b][named.loc[b] > 0].index.min())}
           for b in s_last[(c_base == 0) & (s_last > 0)].sort_values(ascending=False).index]
    still_listed = ~((s_base > 0) & (s_last == 0))   # แบรนด์ที่หายจากรายชื่อไม่ใช่การเปลี่ยนแปลงจริง
    eligible = named.index[((c_base.combine(s_last, max) >= cfg["mover_min_share"]) & still_listed).to_numpy()]
    moves = (s_last - c_base).loc[eligible]
    movers = [{**entry(b), "series": _yearly(named.loc[b])}   # series = ส่วนแบ่งรายปี (กราฟหน้าแบรนด์ของรายงาน)
              for b in moves.abs().sort_values(ascending=False).head(cfg["movers_per_category"]).index]

    def agg(name):
        return _yearly(piv.loc[name]) if name in piv.index else None

    top5 = {str(int(y)): _num(named[y].nlargest(5).sum()) for y in named.columns}
    return {
        "top": top, "new_brands": new, "dropped_brands": dropped, "movers": movers,
        "others": agg("Others"), "private_label": agg("Private Label"), "top5": top5,
        "n_named": {str(int(y)): int((named[y] > 0).sum()) for y in named.columns},
    }


# ---------------------------------------------------------------------------
# ช่องทางขาย / premium
# ---------------------------------------------------------------------------

def channel_facts(channel, category, base, last):
    """ช่องทางระดับใบของหมวด: ส่วนแบ่งปีตั้งต้น -> ล่าสุด เรียงตามขนาดการเปลี่ยนแปลง + ส่วนแบ่ง e-commerce รายปี"""
    d = channel[channel["category"] == category]
    if d.empty:
        return None
    leaves = d[d["is_leaf"]].pivot_table(index="outlet", columns="year", values="share").fillna(0)
    rows = [{"outlet": o, "share_base": _num(leaves.at[o, base]), "share_last": _num(leaves.at[o, last]),
             "change_pp": _num(leaves.at[o, last] - leaves.at[o, base])} for o in leaves.index]
    rows.sort(key=lambda r: abs(r["change_pp"] or 0), reverse=True)
    ecom = d[d["outlet"] == ECOMMERCE].set_index("year")["share"]
    return {"leaves": rows, "ecommerce": _yearly(ecom) if not ecom.empty else None}


def premium_facts(premium, category, base, last, horizon):
    """สัดส่วน premium ของหมวด (% ของมูลค่า) รายปีถึงปีคาดการณ์ - หมวดที่ Euromonitor ไม่แยก = None"""
    s = premium[(premium["category"] == category) & (premium["measure"] == "Premium")].set_index("year")["share"]
    if s.dropna().empty:
        return None
    b, l, h = _at(s, base), _at(s, last), _at(s, horizon)
    return {"series": _yearly(s), "share_base": _num(b), "share_last": _num(l), "share_forecast": _num(h),
            "change_pp": _num(l - b if l is not None and b is not None else None)}


# ---------------------------------------------------------------------------
# อย.
# ---------------------------------------------------------------------------

def fda_complete_through(fda, min_ratio=0.5):
    """(ปี, เดือน) สุดท้ายที่ข้อมูลครบ = เดือนล่าสุดที่จำนวนใบจดแจ้ง >= min_ratio x ค่ากลางรายเดือน
    (เดือนท้ายไฟล์ที่เพิ่งเริ่มเก็บ เช่น 2026-09 มี 2 ใบ ไม่นับ)"""
    monthly = fda.groupby(["year", "month"]).size().sort_index()
    ok = monthly[monthly >= monthly.median() * min_ratio]
    return tuple(int(x) for x in ok.index.max())


def fda_facts(d, through, first_year, euro_keys, cfg):
    """ใบจดแจ้งของกลุ่มที่ส่งมา (หมวดเดียวหรือทั้งตลาด) - ปีเต็มเท่านั้น + ปีล่าสุดที่ยังไม่ครบเทียบเดือนเดียวกันของปีก่อน"""
    t_year, t_month = through
    d = d[(d["year"] < t_year) | ((d["year"] == t_year) & (d["month"] <= t_month))]
    full = [y for y in sorted(d["year"].unique()) if y < t_year or t_month == 12]
    fy = d[d["year"].isin(full)]
    by_year = fy.groupby("year").size()
    out = {
        "by_year": {str(int(y)): int(n) for y, n in by_year.items()},
        "import_share": _yearly(fy.groupby("year")["origin"].apply(lambda s: (s == "import").mean() * 100), 1),
        "untracked_share": _yearly(fy.groupby("year")["brand_key"].apply(lambda s: (~s.isin(euro_keys)).mean() * 100), 1),
        "change_pct": None, "partial_year": None,
    }
    if len(full) >= 2 and by_year.iloc[0] > 0:
        out["change_pct"] = _num((by_year.iloc[-1] / by_year.iloc[0] - 1) * 100, 1)
        out["change_years"] = [int(full[0]), int(full[-1])]
    if t_month < 12:
        cur = int((d["year"] == t_year).sum())
        prev = int(((d["year"] == t_year - 1) & (d["month"] <= t_month)).sum())
        out["partial_year"] = {"year": t_year, "through_month": t_month, "n": cur, "n_prev_same_months": prev,
                               "change_pct": _num((cur / prev - 1) * 100 if prev else None, 1)}
    fyear = d["brand_key"].map(first_year)
    new = d[(fyear >= cfg["fda_new_brand_from"]) & (d["brand_key"] != "")]
    out["new_brands_by_year"] = {str(int(y)): int(n) for y, n in
                                 new[new["year"].isin(full)].assign(fy=fyear).groupby("fy")["brand_key"].nunique().items()
                                 if y in full}
    counts = new.groupby("brand_key").agg(brand=("brand", "first"), n=("brand", "size")).sort_values("n", ascending=False)
    out["top_new_brands"] = [{"brand": r.brand, "first_year": int(first_year[k]), "n": int(r.n),
                              "tracked_by_euromonitor": k in euro_keys}
                             for k, r in counts.head(cfg["fda_top_new_brands"]).iterrows()]
    return out


def fda_trajectory(key, fda_by_key_year, full_years):
    """ใบจดแจ้งต่อปี (ทุกหมวด อย.) ของแบรนด์ที่จับคู่ชื่อได้ - ไม่เจอใน อย. = None"""
    if key not in fda_by_key_year.index.get_level_values(0):
        return None
    s = fda_by_key_year.loc[key]
    return {str(y): int(s.get(y, 0)) for y in full_years}


# ---------------------------------------------------------------------------
# ปัจจัยของหมวด
# ---------------------------------------------------------------------------

def category_factors(category, c, cfg):
    """การเปลี่ยนแปลงของหมวดที่เกินเกณฑ์ -> รายการปัจจัย (ชนิดที่วัดจากข้อมูล) พร้อมแบรนด์ที่จะตรวจต่อด้วยการค้นเว็บ
    candidate_brands ไม่ได้แปลว่าแบรนด์นั้นได้/เสียจากปัจจัย - แค่เป็นแบรนด์ที่ส่วนแบ่งเปลี่ยนมากและต้องหาหลักฐานต่อ"""
    out = []
    movers = [m["brand"] for m in c["brands"]["movers"]]
    ch = c.get("channel")
    if ch:
        moved = [r for r in ch["leaves"] if abs(r["change_pp"] or 0) >= cfg["channel_min_change_pp"]]
        if moved:
            out.append({"type": "channel_shift", "category": category, "changes": moved,
                        "candidate_brands": movers, "needs_web": True})
    b = c["brands"]
    others = b["others"] or {}
    o_base, o_last = others.get(str(cfg["_base"])), others.get(str(cfg["_last"]))
    o_change = None if o_base is None or o_last is None else round(o_last - o_base, 2)
    new = [n for n in b["new_brands"] if (n["share_last"] or 0) >= cfg["mover_min_share"]]
    # ส่วนที่ Others เพิ่มเพราะ Euromonitor เลิกแยกแบรนด์ (ประมาณด้วยส่วนแบ่งปีตั้งต้นของแบรนด์นั้น) ไม่นับเป็นการกระจายตัว
    # แบรนด์ที่รวมเข้าแบรนด์อื่นของเจ้าของเดียวกันไม่เกี่ยวกับ Others จึงไม่หัก
    to_others = [d for d in b["dropped_brands"] if not d.get("merged_into")]
    dropped_share = round(sum(d["share_base"] or 0 for d in to_others), 2)
    o_real = None if o_change is None else round(o_change - dropped_share, 2)
    if (o_real is not None and abs(o_real) >= cfg["concentration_min_change_pp"]) or new:
        out.append({"type": "concentration", "category": category,
                    "others_base": o_base, "others_last": o_last, "others_change_pp": o_change,
                    "dropped_share_base": dropped_share, "others_change_excl_dropped_pp": o_real,
                    "dropped_brands": [d["brand"] for d in to_others],
                    "top5_base": b["top5"].get(str(cfg["_base"])), "top5_last": b["top5"].get(str(cfg["_last"])),
                    "new_brands": [n["brand"] for n in new], "candidate_brands": [n["brand"] for n in new],
                    "needs_web": True})
    p = c.get("premium")
    if p and p["change_pp"] is not None and abs(p["change_pp"]) >= cfg["premium_min_change_pp"]:
        out.append({"type": "premium_shift", "category": category, "share_base": p["share_base"],
                    "share_last": p["share_last"], "change_pp": p["change_pp"], "share_forecast": p["share_forecast"],
                    "candidate_brands": movers, "needs_web": True})
    f = c.get("fda")
    if f and f["change_pct"] is not None and abs(f["change_pct"]) >= cfg["launch_min_change_pct"]:
        out.append({"type": "launch_activity", "category": category, "change_years": f["change_years"],
                    "change_pct": f["change_pct"], "by_year": f["by_year"], "partial_year": f["partial_year"],
                    "candidate_brands": [n["brand"] for n in f["top_new_brands"][:5]], "needs_web": False})
    return out


# ---------------------------------------------------------------------------
# รวม
# ---------------------------------------------------------------------------

def build_facts(euro, fda, cfg):
    market, brand, channel, premium = euro["market"], euro["brand"], euro["channel"], euro["premium"]
    last = int(cfg["last_year"] or brand["year"].max())
    base, horizon = int(cfg["base_year"]), int(cfg["forecast_year"])
    cfg = {**cfg, "_base": base, "_last": last}
    tiers = brand_tiers(brand, last)
    euro_keys = {brand_key(b) for b in brand.loc[brand["is_named"], "brand"].unique()}

    meta = {"edition": int(market["edition"].iloc[0]), "base_year": base, "last_year": last, "forecast_year": horizon,
            "generated_at": datetime.now().isoformat(timespec="seconds"), "sources": source_info(),
            "config": {k: v for k, v in cfg.items() if not k.startswith("_")}}
    if fda is not None:
        through = fda_complete_through(fda)
        first_year = fda.groupby("brand_key")["year"].min()
        full_years = [y for y in sorted(fda["year"].unique()) if y < through[0] or through[1] == 12]
        by_key_year = fda.groupby(["brand_key", "year"]).size()
        names_th = thai_brand_names(fda)
        meta["fda"] = {"first": [int(fda["year"].min()), int(fda[fda["year"] == fda["year"].min()]["month"].min())],
                       "complete_through": list(through), "full_years": [int(y) for y in full_years],
                       "rows": int(len(fda)), "mapped_categories": sorted(set(FDA_CATEGORY_MAP.values()))}

    sizes = {cat: size_facts(market, cat, base, last, horizon)
             for cat in [TOTAL_CATEGORY, *PRODUCT_CATEGORIES, *SEGMENTS]}
    categories = {}
    for cat in [TOTAL_CATEGORY, *PRODUCT_CATEGORIES]:
        c = {"brands": brand_facts(brand, cat, base, last, cfg, tiers),
             "channel": channel_facts(channel, cat, base, last),
             "premium": premium_facts(premium, cat, base, last, horizon), "fda": None}
        if fda is not None:
            if cat == TOTAL_CATEGORY or cat in FDA_CATEGORY_MAP.values():
                part = fda if cat == TOTAL_CATEGORY else fda[fda["category"] == cat]
                c["fda"] = fda_facts(part, through, first_year, euro_keys, cfg)
            for m in c["brands"]["movers"] + c["brands"]["new_brands"]:
                key = brand_key(m["brand"])
                m["fda_by_year"] = fda_trajectory(key, by_key_year, full_years)
                m["fda_first_year"] = int(first_year[key]) if key in first_year.index else None
                m["name_th"] = names_th.get(key)   # ชื่อการค้าไทยใน อย. (คำค้นข่าวไทย)
        categories[cat] = c

    # ปัจจัยเรียง: ทั้งตลาดก่อน แล้วหมวดใหญ่ -> เล็ก (ภายในหมวดตามลำดับใน category_factors)
    order = sorted(PRODUCT_CATEGORIES, key=lambda k: -(sizes[k]["value"][str(last)] or 0))
    factors = [f for cat in [TOTAL_CATEGORY, *order] for f in category_factors(cat, categories[cat], cfg)]
    return {"meta": meta, "market": sizes, "categories": categories, "factors": factors}


def print_summary(facts):
    m, last, base = facts["meta"], facts["meta"]["last_year"], facts["meta"]["base_year"]
    print(f"\nEuromonitor edition {m['edition']} | ส่วนแบ่ง {base} -> {last} | คาดการณ์ถึง {m['forecast_year']}")
    if m.get("fda"):
        print(f"อย.: {m['fda']['rows']:,} ใบ ครบถึง {m['fda']['complete_through'][0]}-{m['fda']['complete_through'][1]:02d}"
              f" (ปีเต็ม {m['fda']['full_years'][0]}-{m['fda']['full_years'][-1]})")
    print(f"\n{'หมวด':34s} {'มูลค่า ' + str(last):>12s} {'โต/ปี':>7s} {'คาด/ปี':>7s}  Others {base}->{last}  e-com {base}->{last}")
    for cat, c in facts["categories"].items():
        s = facts["market"][cat]
        o, e = c["brands"]["others"] or {}, (c["channel"] or {}).get("ecommerce") or {}
        print(f"{cat:34s} {s['value'][str(last)] or 0:>12,.0f} {s['cagr_hist'] or 0:>6.1f}% {s['cagr_forecast'] or 0:>6.1f}%"
              f"  {o.get(str(base)) or 0:5.1f} -> {o.get(str(last)) or 0:5.1f}   {e.get(str(base)) or 0:5.1f} -> {e.get(str(last)) or 0:5.1f}")
    counts = {}
    for f in facts["factors"]:
        counts[f["type"]] = counts.get(f["type"], 0) + 1
    print(f"\nปัจจัยที่เกินเกณฑ์: {len(facts['factors'])} ({', '.join(f'{k} {v}' for k, v in counts.items())})")


def main():
    parser = argparse.ArgumentParser(description="⑲ ข้อเท็จจริงส่วนแบ่งตลาด (Euromonitor + อย.)")
    parser.add_argument("--run", default=None, help="ชื่อโฟลเดอร์ใน main/output (ไม่ใส่ = สร้างใหม่ market_share_<วันเวลา>)")
    parser.add_argument("--no-fda", action="store_true", help="ไม่ใช้ข้อมูล อย.")
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    run_dir = OUTPUT_ROOT / (args.run or f"market_share_{datetime.now():%Y%m%d_%H%M%S}")
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    euro = load_euromonitor()
    fda = None if args.no_fda else load_fda()
    facts = build_facts(euro, fda, cfg)
    out = run_dir / FACTS_FILE
    out.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    print_summary(facts)
    print(f"\n✅ {out}")


if __name__ == "__main__":
    main()
