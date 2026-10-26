# -*- coding: utf-8 -*-
"""
ตัวทำขนาดสินค้าให้เป็นมาตรฐานเดียว (size_std / unit_std / dimension_orig / pack_mult / size_flag)

ทำไมต้องมี: konvy_product.xlsx มาพร้อมคอลัมน์ 5 ตัวนี้ที่ผู้ให้ข้อมูลคำนวณจาก raw_product_size ("30ml x 2pcs", "40ml + 40g") แต่
eveandboy.xlsx ไม่มี และ raw_product_size ของ Eve เป็นแค่ product_size+size_unit ที่ประกอบกลับ ("30 ml") ไม่มีข้อมูลแพ็ก/เซ็ต
-> ใช้ชื่อสินค้า (product_name) + product_size/size_unit/product_pieces ตัดสินแทน

ความหมายของผลลัพธ์ (ตรงกับของ Konvy เพื่อให้ unit_price_tiers.py ใช้ได้เลย):
  size_std       ขนาดรวมที่คูณแพ็ก/รวมเซ็ตแล้ว (g หรือ ml เป็นหน่วยเดียวกัน, count = ชิ้น; 1 Pair = 2 ชิ้น)
  unit_std       "g·ml" | "ชิ้น" | None
  dimension_orig mass | volume | count | mixed | None
  pack_mult      จำนวนแพ็กที่คูณ (None = ไม่ได้คูณ/ไม่รู้)
  size_flag      ok | bundle_summed (ใช้ได้) | pieces_unverified | bundle_unresolved | not_a_quantity | free_item | ambiguous_x | no_size (ใช้ไม่ได้)

หลักการ: "ไม่แน่ใจ = ไม่ให้ขนาด" - unit_price_tiers ใช้เฉพาะ ok / bundle_summed; แถวอื่นถูกเทียบด้วยราคาขายภายในชนิดสินค้าเดียวกัน
ฟังก์ชันล้วน ไม่เรียก API ทดสอบกับไฟล์ Konvy จริงได้ (tests/test_size_standardiser.py)
"""
import math
import re

import pandas as pd

USABLE_FLAGS = ("ok", "bundle_summed")     # ตรงกับ unit_price_tiers.USABLE_FLAGS
SIZE_COLUMNS = ("size_std", "unit_std", "dimension_orig", "pack_mult", "size_flag")
UNIT_GML = "g·ml"
UNIT_COUNT = "ชิ้น"

# หน่วย -> (มิติ, ตัวคูณเข้า g/ml/ชิ้น); มิติ "other" = ไม่ใช่ปริมาณสินค้า (mg, m, cm ...)
_UNITS = {
    "g": ("mass", 1.0), "gm": ("mass", 1.0), "gms": ("mass", 1.0), "gram": ("mass", 1.0), "grams": ("mass", 1.0), "กรัม": ("mass", 1.0),
    "kg": ("mass", 1000.0),
    "ml": ("volume", 1.0), "cc": ("volume", 1.0), "l": ("volume", 1000.0), "ltr": ("volume", 1000.0),
    "oz": ("volume", 29.574), "floz": ("volume", 29.574),
    "pcs": ("count", 1.0), "pc": ("count", 1.0), "pieces": ("count", 1.0), "piece": ("count", 1.0), "ชิ้น": ("count", 1.0),
    "sheets": ("count", 1.0), "sheet": ("count", 1.0), "capsules": ("count", 1.0), "capsule": ("count", 1.0), "caps": ("count", 1.0),
    "tablets": ("count", 1.0), "tablet": ("count", 1.0), "softgels": ("count", 1.0), "sachets": ("count", 1.0), "sachet": ("count", 1.0),
    "sac": ("count", 1.0), "pads": ("count", 1.0), "pad": ("count", 1.0), "patches": ("count", 1.0), "dots": ("count", 1.0),
    "tips": ("count", 1.0), "rows": ("count", 1.0), "sets": ("count", 1.0), "packs": ("count", 1.0), "pack": ("count", 1.0),
    "boxes": ("count", 1.0), "rolls": ("count", 1.0), "plasters": ("count", 1.0), "buds": ("count", 1.0), "ct": ("count", 1.0),
    "ea": ("count", 1.0),
    "pairs": ("count", 2.0), "pair": ("count", 2.0),
    "mg": ("other", 1.0), "m": ("other", 1.0), "cm": ("other", 1.0), "mm": ("other", 1.0), "inch": ("other", 1.0),
    "meters": ("other", 1.0), "meter": ("other", 1.0),
}

_NUM = r"(\d+(?:[.,]\d+)?)"
_UNIT_RE = (r"(fl\.?\s?oz|kg|mg|gms?|grams?|g|กรัม|ml|cc|ltr|l|oz|pcs?|pieces?|ชิ้น|sheets?|pairs?|capsules?|caps|tablets?|sachets?|"
            r"pads?|patches|ct|cm|mm|m)")
_SIZE_RE = re.compile(rf"(?<![\w.]){_NUM}\s*{_UNIT_RE}(?![a-zA-Z])", re.I)
_PACK_AFTER_RE = re.compile(rf"(?<![\w.]){_NUM}\s*{_UNIT_RE}\s*[x×*]\s*(\d{{1,3}})(?![\d.]|\s*(?:ml|g)\b)", re.I)   # 25ml x 3 / 280 Sheets x 5pcs
_PACK_BEFORE_RE = re.compile(rf"(?<![\w.])(\d{{1,3}})\s*(?:pcs?|pieces?|ชิ้น|sheets?|tubes?|bottles?|sachets?)?\s*[x×*]\s*{_NUM}\s*{_UNIT_RE}(?![a-zA-Z])", re.I)  # 2 x 30ml / 3pcs x 10g
_FREE_RE = re.compile(r"\b(?:free|gift)\b|แถม|ฟรี", re.I)     # ของแถมท้ายชื่อ ("30ml + Free! Cleanser [3ml x 3pcs]") ไม่นับเป็นขนาดสินค้า
_SET_RE = re.compile(r"\b(?:set|kit|duo|trio|bundle|value pack|twin pack)\b|เซ็ต|เซต|แพ็คคู่|แพ็กคู่|แพ็ค\s?\d|แพ็ก\s?\d|ยกกล่อง|ซื้อ\s?\d\s?แถม|buy\s?\d\s?get", re.I)
_SHADE_RE = re.compile(r"#\S+|\bno\.?\s?\d+\S*", re.I)         # รหัสเฉด "#01" "No.5" - ตัวเลขนี้ไม่ใช่ขนาด
_AMBIG_X_RE = re.compile(rf"(?<![\w.]){_NUM}\s*{_UNIT_RE}\s*[x×*]\s*{_NUM}\s*{_UNIT_RE}(?![a-zA-Z])", re.I)   # 0.1g x 0.35ml


def _unit_key(unit):
    return re.sub(r"[\s.]", "", str(unit)).lower()


def _unit_info(unit):
    """หน่วยดิบ -> (มิติ, ตัวคูณ) หรือ None ถ้าไม่รู้จัก/ว่าง"""
    if unit is None or (isinstance(unit, float) and math.isnan(unit)):
        return None
    return _UNITS.get(_unit_key(unit))


def _to_float(v):
    if v is None:
        return None
    try:
        f = float(str(v).replace(",", ""))
    except ValueError:
        return None
    return None if math.isnan(f) else f


def _terms(name):
    """[(ค่า, มิติ, ตัวคูณ, เริ่ม, จบ)] ของทุกนิพจน์ขนาดในชื่อ (g/ml/ชิ้น/...) เรียงตามตำแหน่ง"""
    out = []
    for m in _SIZE_RE.finditer(str(name or "")):
        info = _UNITS.get(_unit_key(m.group(2)))
        val = _to_float(m.group(1).replace(",", "."))
        if info is None or val is None:
            continue
        out.append((val, info[0], info[1], m.start(), m.end()))
    return out


def _close(a, b, tol=0.01):
    return a is not None and b is not None and b != 0 and abs(a - b) / abs(b) <= tol


def _result(size_std=None, unit_std=None, dimension=None, pack_mult=None, flag=None):
    return {"size_std": float("nan") if size_std is None else float(size_std), "unit_std": unit_std, "dimension_orig": dimension,
            "pack_mult": float("nan") if pack_mult is None else float(pack_mult), "size_flag": flag}


def _bundle_chains(name, terms):
    """กลุ่มนิพจน์ขนาดที่เชื่อมด้วย + / & (ไม่มีตัวเลขคั่น) เช่น "Shampoo 40ml + Treatment 40g" -> [[t1, t2]]"""
    chains, cur = [], []
    text = str(name or "")
    for t in terms:
        if cur:
            gap = text[cur[-1][4]:t[3]]
            if re.search(r"[+&]", gap) and not re.search(r"\d", _SHADE_RE.sub(" ", gap)) and len(gap) <= 60:
                cur.append(t)
                continue
            chains.append(cur)
        cur = [t]
    if cur:
        chains.append(cur)
    return [c for c in chains if len(c) >= 2]


def standardise_size(name, size, unit, pieces=None):
    """(ชื่อสินค้า, product_size, size_unit, product_pieces) -> {size_std, unit_std, dimension_orig, pack_mult, size_flag}"""
    info = _unit_info(unit)
    s = _to_float(size)
    if info is None or s is None or s <= 0:
        return _result(flag="no_size")
    dim, factor = info
    if dim == "other":
        return _result(flag="not_a_quantity")
    base = s * factor
    unit_std = UNIT_COUNT if dim == "count" else UNIT_GML
    pcs = _to_float(pieces)
    text = str(name or "")

    # ของแถม: ตัดชื่อตั้งแต่คำว่า free/แถม เป็นต้นไป ถ้าก่อนหน้านั้นมีขนาดของสินค้าหลักแล้ว (ผู้ให้ข้อมูล Konvy รวมของแถมเข้า
    # size_std แต่ราคาที่จ่ายคือสินค้าหลัก - หน่วยราคาจึงใช้เฉพาะส่วนที่จ่ายจริง)
    m_free = _FREE_RE.search(text)
    if m_free and m_free.start() > 0 and _SIZE_RE.search(text[:m_free.start()]):
        text = text[:m_free.start()]
    terms = _terms(text)

    # "0.1g x 0.35ml" - ไม่รู้ว่าคูณหรือเป็นสองส่วน
    for m in _AMBIG_X_RE.finditer(text):
        a, b = _unit_info(m.group(2)), _unit_info(m.group(4))
        if a and b and a[0] in ("mass", "volume") and b[0] in ("mass", "volume") and a[0] != b[0]:
            return _result(flag="ambiguous_x")

    # เซ็ตที่เขียนขนาดต่อกันด้วย + (ผู้ขายใส่ product_size เป็นพจน์แรกหรือเป็นผลรวมแล้ว)
    chains = _bundle_chains(text, terms)
    for chain in chains:
        if any(t[1] == "other" for t in chain):
            continue
        first_ok = chain[0][1] == dim and _close(chain[0][0] * chain[0][2], base)
        total = sum(t[0] * t[2] for t in chain)
        if not (first_ok or _close(total, base)):
            continue
        dims = {t[1] for t in chain}
        if "count" in dims and len(dims) > 1:
            return _result(dimension=None, flag="bundle_unresolved")
        dimension = "count" if dims == {"count"} else ("mixed" if len(dims) > 1 else dims.pop())
        return _result(total, UNIT_COUNT if dimension == "count" else UNIT_GML, dimension, None, "bundle_summed")

    # แพ็กคูณ: "[25ml x 3pcs]" "[280 Sheets x 5pcs]" "2 x 30ml"
    for m in _PACK_AFTER_RE.finditer(text):
        v, u, n = _to_float(m.group(1).replace(",", ".")), _unit_info(m.group(2)), int(m.group(3))
        if u is None or u[0] != dim or n < 2:
            continue
        if _close(v * u[1], base):
            return _result(base * n, unit_std, dim, n, "ok")
        if _close(v * u[1] * n, base):          # product_size เป็นยอดรวมแล้ว
            return _result(base, unit_std, dim, n, "ok")
    for m in _PACK_BEFORE_RE.finditer(text):
        n, v, u = int(m.group(1)), _to_float(m.group(2).replace(",", ".")), _unit_info(m.group(3))
        if u is None or u[0] != dim or n < 2:
            continue
        if _close(v * u[1], base):
            return _result(base * n, unit_std, dim, n, "ok")
        if _close(v * u[1] * n, base):
            return _result(base, unit_std, dim, n, "ok")

    # product_pieces > 1 โดยไม่มีหลักฐานแพ็กในชื่อ -> ไม่รู้ว่าขนาดนี้ต่อชิ้นหรือรวม (มักเป็นเลขเฉดหลุดมา)
    if pcs is not None and pcs > 1 and not (dim == "count" and _close(pcs, base)):
        # จำนวนชิ้นเขียนในชื่อตรงกับ pieces ("120g [80 Pads]") = ขนาดเป็นของทั้งแพ็กอยู่แล้ว
        if not any(t[1] == "count" and _close(t[0], pcs) for t in terms):
            return _result(base, unit_std, dim, 1, "pieces_unverified")
    # ชื่อบอกว่าเป็นเซ็ต/แพ็คคู่ แต่ขนาดมีค่าเดียวและไม่รู้ว่ารวมทั้งเซ็ตหรือชิ้นแรก -> หน่วยราคาไม่น่าเชื่อ
    if _SET_RE.search(text):
        return _result(base, unit_std, dim, 1, "bundle_unresolved")
    return _result(base, unit_std, dim, 1, "ok")


def add_size_columns(df, name_col="product_name", size_col="product_size", unit_col="size_unit", pieces_col="product_pieces"):
    """คืน DataFrame ใหม่ (index เดิม) เพิ่มคอลัมน์ size_std/unit_std/dimension_orig/pack_mult/size_flag"""
    pieces = df[pieces_col] if pieces_col in df.columns else [None] * len(df)
    rows = [standardise_size(n, s, u, p) for n, s, u, p in zip(df[name_col], df[size_col], df[unit_col], pieces)]
    res = pd.DataFrame(rows, index=df.index, columns=list(SIZE_COLUMNS))
    out = df.drop(columns=[c for c in SIZE_COLUMNS if c in df.columns]).copy()
    return pd.concat([out, res], axis=1)
