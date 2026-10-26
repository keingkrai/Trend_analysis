# -*- coding: utf-8 -*-
"""
⑲ รายงานส่วนแบ่งตลาด — ชั้นข้อมูล (Phase 0): โหลด Euromonitor + อย. เป็นตารางยาว (tidy) ที่ทุกขั้นของรายงานใช้ร่วมกัน

แหล่ง:
    tool/product/euromonitor.xlsx  Euromonitor Thailand Beauty and Personal Care (edition 2026) - มีแค่หมวดระดับ 0-1
                                   (14 หมวด รวม Premium/Mass = L2 ของเรา) ขนาดตลาด 2011-2025 + คาด 2026-2030,
                                   ส่วนแบ่งแบรนด์ 2016-2025 (~95 แบรนด์ต่อหมวด ที่เหลือรวมเป็น "Others")
    tool/product/FDA.xlsx          ใบจดแจ้งเครื่องสำอาง อย. 2021-01 ถึง 2026-08 (รวมที่สิ้นอายุ/ยกเลิก จึงไม่มี survivorship)

ตัวเลือกที่ตั้งใจ:
- ส่วนแบ่งแบรนด์ใช้ sheet "Brand Share GBNL" (ชื่อแบรนด์สากล ย้อนประวัติตามเจ้าของล่าสุด) - การเปลี่ยนเจ้าของ/ผู้จัดจำหน่าย
  จึงไม่ทำให้ส่วนแบ่งกระโดด
- มูลค่า = Retail Value RSP ล้านบาท ทั้งราคาปัจจุบัน (value) และราคาคงที่ปี 2025 (value_real - การเติบโตที่ตัดเงินเฟ้อแล้ว)
- ช่องทางขาย: sheet ซ้ำทั้งต้นไม้ 2 ชุดต่อหมวด (ค่าเท่ากัน) เก็บชุดแรก + ติดป้าย is_leaf = ช่องทางที่ไม่มีช่องทางย่อยที่มีข้อมูล
  (ใบรวมกันได้ 100% ไม่นับซ้ำแม่-ลูก)
- หมวดของ อย. (Category2 - ผู้จัดหมวดไม่ทราบที่มา ไม่ใช่ของเรา) แปลงเป็นหมวด Euromonitor ได้ 5 หมวด
  (Facial/Eye Make-Up -> Colour Cosmetics, "Uncertain" 21% และหมวดอื่น = None)

ไฟล์ต้นทางใหญ่ (Euromonitor ~15 วินาทีเฉพาะ sheet ที่ใช้, อย. ~2.5 นาที) - cache ตารางที่จัดแล้วเป็น parquet ใน
output/_checkpoints/market_*.parquet ผูกกับขนาด + เวลาแก้ไขของไฟล์ต้นทาง (เปลี่ยนไฟล์ = โหลดใหม่เอง)
"""
import re
import unicodedata
from pathlib import Path

import pandas as pd

TOOL_DIR = Path(__file__).resolve().parents[1]
PRODUCT_DIR = TOOL_DIR / "product"
CHECKPOINTS = TOOL_DIR.parent / "output" / "_checkpoints"
EURO_FILE = PRODUCT_DIR / "euromonitor.xlsx"
FDA_FILE = PRODUCT_DIR / "FDA.xlsx"

EURO_SHEETS = {"market": "Market Sizes", "brand": "Brand Share GBNL", "channel": "Channel", "premium": "Premium vs Mass"}
NOMINAL = "Historic Current Prices, Forecast Current Prices"
REAL = "Historic Constant 2025 Prices, Forecast Constant 2025 Prices"
TOTAL_CATEGORY = "Beauty and Personal Care"
PRODUCT_CATEGORIES = ["Baby and Child-specific Products", "Bath and Shower", "Colour Cosmetics", "Deodorants",
                      "Depilatories", "Fragrances", "Hair Care", "Men's Grooming", "Oral Care", "Skin Care", "Sun Care"]
AGGREGATE_BRANDS = ("Total", "Others", "Private Label")   # แถวรวม ไม่ใช่แบรนด์ที่มีชื่อ

FDA_COLUMNS = {"วันที่อนุญาต": "approved", "ชื่อการค้า": "brand_th", "ชื่อการค้า (อังกฤษ)": "brand_en",
               "ประเภทการจดแจ้ง": "kind", "ชื่อผู้ประกอบการ": "company", "สถานะการจดแจ้ง": "status",
               "Category2": "fda_category2", "Category3": "fda_category3"}
FDA_CATEGORY_MAP = {"Skincare": "Skin Care", "Suncare": "Sun Care", "Bath and Shower": "Bath and Shower",
                    "Hair Care": "Hair Care", "Facial Make-Up": "Colour Cosmetics", "Eye Make-Up": "Colour Cosmetics"}
FDA_ORIGIN = {"ผลิต": "local", "ผลิตแบบแบ่งบรรจุ": "local", "นำเข้า": "import"}


# ---------------------------------------------------------------------------
# ฟังก์ชันล้วน (เทสได้ด้วยข้อมูลปลอม)
# ---------------------------------------------------------------------------

def brand_key_text(name):
    """ชื่อแบรนด์ตัวใหญ่ ตัดเครื่องหมายเสียงของอักษรละติน (L'Oréal -> L'OREAL) ยังมีช่องว่าง/เครื่องหมายอยู่"""
    if not isinstance(name, str):
        return ""
    return "".join(ch for ch in unicodedata.normalize("NFKD", name) if not "̀" <= ch <= "ͯ").upper()


def brand_key(name):
    """ชื่อแบรนด์ -> คีย์เทียบข้ามแหล่ง: brand_key_text แล้วเหลือแค่ตัวอักษร/ตัวเลข
    (La Roche-Posay = LA ROCHE POSAY, L'Oréal = LOREAL, Pond's = PONDS) - อักษรไทยคงไว้ตามเดิม"""
    return re.sub(r"[^0-9A-Zก-๛]", "", brand_key_text(name))


def _clean(raw):
    """ตัดแถวว่าง/แถวลิขสิทธิ์ท้าย sheet (Country ว่าง) + ตัดช่องว่างที่ Euromonitor ใช้ย่อหน้าชื่อหมวด/ช่องทาง"""
    df = raw[raw["Country"].notna()].copy()
    for col in ("Category", "Subcategory", "Outlet"):
        if col in df:
            df[col] = df[col].astype(str).str.strip()
    return df


def _wide_years(df):
    """คอลัมน์ปีแบบกว้าง "2016 (%)" -> {ชื่อคอลัมน์: 2016}"""
    return {c: int(str(c)[:4]) for c in df.columns if re.fullmatch(r"\d{4} \(%\)", str(c))}


def tidy_market_sizes(raw):
    """Market Sizes -> category, year, value (ล้านบาท ราคาปัจจุบัน), value_real (ราคาคงที่ 2025), edition"""
    df = _clean(raw)
    df = df[(df["Data Type"] == "Retail Value RSP") & (df["Unit"] == "THB million")]
    keys = ["Category", "Year"]
    nominal = df[df["Current/Constant"] == NOMINAL][keys + ["Actual", "Edition"]].rename(columns={"Actual": "value"})
    real = df[df["Current/Constant"] == REAL][keys + ["Actual"]].rename(columns={"Actual": "value_real"})
    out = nominal.merge(real, on=keys, how="left").rename(columns={"Category": "category", "Year": "year",
                                                                    "Edition": "edition"})
    out["year"] = out["year"].astype(int)
    out["edition"] = out["edition"].astype(int)
    if out.duplicated(["category", "year"]).any():
        raise ValueError("Market Sizes: มีหมวด-ปีซ้ำหลังกรอง RSP/THB - รูปแบบไฟล์เปลี่ยน?")
    return out.sort_values(["category", "year"]).reset_index(drop=True)


def tidy_brand_shares(raw):
    """Brand Share (GBNL) -> category, brand, owner, year, share (%), value (ล้านบาท), is_named
    แบรนด์เดียวกันที่มีหลายแถวในหมวด-ปีเดียวกัน (ไม่ควรเกิดใน GBNL) รวมกัน"""
    df = _clean(raw)
    df = df[df["Unit"] == "THB million"]
    df = df.rename(columns={"Category": "category", "Global Brand Name": "brand", "Global Brand Owner": "owner",
                            "Year": "year", "Percent": "share", "Actual": "value"})
    df["year"] = df["year"].astype(int)
    total = lambda s: s.sum(min_count=1)   # noqa: E731 - ปีที่ไม่ได้ติดตามคงเป็น NaN ไม่กลายเป็น 0
    out = (df.groupby(["category", "brand", "year"], as_index=False)
             .agg(owner=("owner", "first"), share=("share", total), value=("value", total)))
    out["is_named"] = ~out["brand"].isin(AGGREGATE_BRANDS)
    return out


def mark_leaves(levels, has_data):
    """ช่องทางที่ไม่มีลูก (ระดับลึกกว่าที่ตามมาติดกัน) ที่มีข้อมูล = ใบ - ใบรวมกันได้ 100% ไม่นับซ้ำแม่-ลูก"""
    leaves = []
    for i, level in enumerate(levels):
        j, child_has_data = i + 1, False
        while j < len(levels) and levels[j] > level:
            child_has_data = child_has_data or has_data[j]
            j += 1
        leaves.append(bool(has_data[i]) and not child_has_data)
    return leaves


def tidy_channel(raw):
    """Channel (ปีเป็นคอลัมน์) -> category, outlet, level, order, is_leaf, year, share (% ของมูลค่าหมวด)"""
    df = _clean(raw)
    df = df[df["Data Type"] == "Retail Value RSP"]
    years = _wide_years(df)
    df = df.drop_duplicates(["Category", "Outlet"], keep="first").copy()   # ต้นไม้ชุดที่ 2 ค่าเท่ากัน
    df["level"] = df["Outlet Hierarchy"].astype(int)
    df["order"] = df.groupby("Category").cumcount()
    df["has_data"] = df[list(years)].notna().any(axis=1)
    df["is_leaf"] = False
    for _, idx in df.groupby("Category").groups.items():
        part = df.loc[idx].sort_values("order")
        df.loc[part.index, "is_leaf"] = mark_leaves(part["level"].tolist(), part["has_data"].tolist())
    long = df.melt(id_vars=["Category", "Outlet", "level", "order", "is_leaf"], value_vars=list(years),
                   var_name="col", value_name="share")
    long["year"] = long["col"].map(years)
    long = long.rename(columns={"Category": "category", "Outlet": "outlet"}).drop(columns="col")
    return long.sort_values(["category", "order", "year"]).reset_index(drop=True)


def tidy_premium_mass(raw):
    """Premium vs Mass (ปีเป็นคอลัมน์ ถึงปีคาดการณ์) -> category, measure (Premium/Mass/Total), year, share"""
    df = _clean(raw)
    df = df[df["Data Type"] == "Retail Value RSP"]
    years = _wide_years(df)
    long = df.melt(id_vars=["Category", "Measure"], value_vars=list(years), var_name="col", value_name="share")
    long["year"] = long["col"].map(years)
    long = long.rename(columns={"Category": "category", "Measure": "measure"}).drop(columns="col")
    return long.drop_duplicates(["category", "measure", "year"]).reset_index(drop=True)


def tidy_fda(raw):
    """ใบจดแจ้ง อย. -> year/month (แปลง พ.ศ. แล้ว), brand (ชื่ออังกฤษ ว่าง/"-" ใช้ชื่อไทย), brand_key, category
    (หมวด Euromonitor หรือ None), origin (local/import) + คอลัมน์ต้นทางที่ใช้ - แถวที่อ่านวันที่ไม่ได้ถูกตัดออก"""
    df = raw[list(FDA_COLUMNS)].rename(columns=FDA_COLUMNS).copy()
    parts = df["approved"].astype(str).str.extract(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})")
    df["year"] = pd.to_numeric(parts[2], errors="coerce") - 543
    df["month"] = pd.to_numeric(parts[1], errors="coerce")
    df = df.dropna(subset=["year", "month"])
    df["year"] = df["year"].astype(int)
    df["month"] = df["month"].astype(int)
    en = df["brand_en"].fillna("").astype(str).str.strip()
    th = df["brand_th"].fillna("").astype(str).str.strip()
    df["brand"] = en.where(~en.isin(["", "-"]), th)
    df["brand_key"] = df["brand"].map(brand_key)
    df["category"] = df["fda_category2"].map(FDA_CATEGORY_MAP)
    df["origin"] = df["kind"].map(FDA_ORIGIN)
    df["brand_th"] = th   # ชื่อการค้าภาษาไทย - ใช้เป็นคำค้นข่าวไทย (มิสทีน, กิฟฟารีน)
    keep = ["year", "month", "brand", "brand_th", "brand_key", "category", "origin", "company", "status",
            "fda_category2", "fda_category3"]
    return df[keep].reset_index(drop=True)


# ---------------------------------------------------------------------------
# โหลด + cache
# ---------------------------------------------------------------------------

CACHE_VERSION = 2   # เพิ่มเมื่อคอลัมน์ของตารางที่ cache เปลี่ยน (2 = อย. มี brand_th) - cache เก่าจะถูกสร้างใหม่เอง


def _signature(src):
    st = Path(src).stat()
    return f"v{CACHE_VERSION}:{st.st_size}:{int(st.st_mtime)}"


def _read_cache(name, src):
    path = CHECKPOINTS / f"market_{name}.parquet"
    sig = path.with_suffix(".sig")
    if path.exists() and sig.exists() and sig.read_text(encoding="utf-8") == _signature(src):
        return pd.read_parquet(path)
    return None


def _write_cache(name, src, df):
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    path = CHECKPOINTS / f"market_{name}.parquet"
    df.to_parquet(path, index=False)
    path.with_suffix(".sig").write_text(_signature(src), encoding="utf-8")


def load_euromonitor(src=EURO_FILE):
    """{"market", "brand", "channel", "premium"} -> DataFrame (cache ไม่ตรงแม้ตารางเดียว = อ่าน workbook ครั้งเดียวสร้างใหม่ทั้งชุด)"""
    cached = {name: _read_cache(name, src) for name in EURO_SHEETS}
    if all(df is not None for df in cached.values()):
        return cached
    print(f"  โหลด {Path(src).name} (ครั้งแรกหลังไฟล์เปลี่ยน ~15 วินาที) ...", flush=True)
    xl = pd.ExcelFile(src, engine="openpyxl")
    raw = {name: xl.parse(sheet, header=1) for name, sheet in EURO_SHEETS.items()}
    tidy = {"market": tidy_market_sizes(raw["market"]), "brand": tidy_brand_shares(raw["brand"]),
            "channel": tidy_channel(raw["channel"]), "premium": tidy_premium_mass(raw["premium"])}
    for name, df in tidy.items():
        _write_cache(name, src, df)
    return tidy


def load_fda(src=FDA_FILE):
    """ใบจดแจ้ง อย. แบบจัดแล้ว (cache ไม่ตรง = อ่าน Excel ใหม่ ~2.5 นาที)"""
    df = _read_cache("fda", src)
    if df is None:
        print(f"  โหลด {Path(src).name} (ครั้งแรกหลังไฟล์เปลี่ยน ~2.5 นาที) ...", flush=True)
        df = tidy_fda(pd.read_excel(src, dtype=str))
        _write_cache("fda", src, df)
    return df


def thai_brand_names(fda):
    """brand_key -> ชื่อการค้าภาษาไทยที่ใช้บ่อยที่สุดใน อย. (เฉพาะชื่อที่มีอักษรไทย)"""
    d = fda[fda["brand_th"].str.contains(r"[ก-๛]", regex=True, na=False) & (fda["brand_key"] != "")]
    return d.groupby("brand_key")["brand_th"].agg(lambda s: s.value_counts().index[0])


def source_info():
    """ชื่อไฟล์ + signature ของแหล่งข้อมูล (บันทึกลงผล ไว้ตรวจย้อนว่าใช้ไฟล์ชุดไหน)"""
    return {path.name: _signature(path) for path in (EURO_FILE, FDA_FILE) if path.exists()}
