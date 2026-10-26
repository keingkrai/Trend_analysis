# -*- coding: utf-8 -*-
"""
⑫ แผนที่ตลาดระดับหมวด L2 — ข้อมูลให้รายงาน ⑯ (หน้าสินค้าของเทรนด์) และ ⑰ (หน้าที่ 3 ของเทรนด์) เทียบ "ความใกล้เทรนด์ x ยอดขาย" โดยใช้หมวดระดับ 2
อย่างเดียวเป็นกลุ่มเทียบ (🆕 2026-10-21 เจ้าของงานสั่ง - ไม่แยกชนิดสินค้า L4 และไม่แยกช่วงราคาต่อปริมาณ)

เก็บเป็นไฟล์เดียวต่อรอบ phase3_l2_market_map.json.gz (บีบอัด) ในโฟลเดอร์รอบ:
  "products": ตารางสินค้าของหมวดหลักที่เทรนด์ใช้ (ครั้งเดียวต่อสินค้า - ยอดขายไม่ขึ้นกับเทรนด์) แถวละ COLUMNS
              ยอดขาย = sales_level.market_sales(rows, None) = เทียบทุกสินค้าในหมวด L2 เดียวกัน (ไม่ผ่านช่วงราคา)
  "trends":   {คีย์เทรนด์: {"trend_name", "stream", "category", "order": [เลขแถวในตารางสินค้า เรียงจากใกล้เทรนด์ที่สุด]}}
              อันดับในหมวด = ตำแหน่งใน order + 1
รายงานคิดเกรด/ช่อง/จำนวนเองตอนสร้างรายงาน (phase6_pdf_report/l2_map.py - เส้นตัดอยู่ที่ config/brand_report.json) จึงปรับเส้นตัดได้โดยไม่รัน ⑫ ใหม่

ฟังก์ชันล้วน (ไม่เรียก API) - ผู้เรียก (validate_at_scale_nvidia.py) ส่งสินค้าที่คิดความใกล้แล้วมาให้
"""
import gzip
import json

from sales_level import market_sales

MAP_FILE = "phase3_l2_market_map.json.gz"
COLUMNS = ("brand", "product_name", "group", "sale_price_thb", "size", "unit_label",
           "sales_pct", "sales_basis", "soldout", "zero", "sold", "reviews")


def _num(v):
    try:
        return None if v is None or v != v else float(v)
    except (TypeError, ValueError):
        return None


def _price(v):
    try:
        return None if v is None or v != v else float(str(v).replace(",", ""))   # ราคาในแคตตาล็อกเป็นสตริงมีจุลภาค ("1,790.00")
    except (TypeError, ValueError):
        return None


def build_table(df, groups, tier_recs, wanted):
    """สินค้าในหมวดที่ wanted (ชุดชื่อหมวด L2) -> (table, index_by_idx)
    table = แถวละ COLUMNS; index_by_idx = {แถวใน df: เลขแถวในตาราง}; tier_recs (unit_price_tiers.tier_records หรือ None) ให้ขนาด/หน่วย"""
    sub = df[groups.isin(wanted)]
    rows = [{"group": groups[idx], "sale_price_thb": _price(r.get("sale_price_thb")), "sold_count": _num(r.get("sold_count")),
             "stock": _num(r.get("stock")), "review_count": _num(r.get("review_count"))}
            for idx, r in sub.iterrows()]
    sales = market_sales(rows, None)   # tier_key None = เทียบทั้งหมวด L2 (ไม่แบ่งช่วงราคา)
    table, index_by_idx = [], {}
    for (idx, r), row, sa in zip(sub.iterrows(), rows, sales):
        rec = (tier_recs or {}).get(idx) if tier_recs is not None else None
        size = _num((rec or {}).get("size"))
        pct = sa.get("pct")
        index_by_idx[idx] = len(table)
        table.append([r["brand"], r["product_name"], row["group"], row["sale_price_thb"],
                      None if size is None else round(size, 2), (rec or {}).get("unit_label"),
                      None if pct is None else round(float(pct), 4), sa.get("basis") or "none",
                      int(bool(sa.get("soldout"))), int(bool(sa.get("zero"))),
                      None if sa.get("sold") is None else int(sa["sold"]), None if sa.get("reviews") is None else int(sa["reviews"])])
    return table, index_by_idx


def trend_entry(scored, main_category, index_by_idx, stream, trend_name):
    """สินค้าทุกชิ้นของเทรนด์ (scored เรียงจากใกล้เทรนด์ที่สุด มี _idx) -> เลขแถวในตารางสินค้าของสินค้าในหมวดหลัก เรียงตามความใกล้"""
    return {"trend_name": trend_name, "stream": stream, "category": main_category,
            "order": [index_by_idx[s["_idx"]] for s in scored if s["group"] == main_category and s["_idx"] in index_by_idx]}


def write_map(path, n_products_total, table, trends):
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump({"_note": "⑫ แผนที่ตลาดระดับหมวด L2 - ดู l2_market_map.py", "n_products_total": n_products_total,
                   "columns": list(COLUMNS), "products": table, "trends": trends}, f, ensure_ascii=False, separators=(",", ":"))


def read_map(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)
