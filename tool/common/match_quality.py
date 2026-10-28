# -*- coding: utf-8 -*-
"""
🆕 (2026-10-28) ผลจับคู่สินค้า (⑫) ของเทรนด์นี้ "ใกล้พอจะแสดงไหม" - ฟังก์ชันล้วน ไม่เรียก API

ดูจากตัวเลขของรอบ 164405 + รอบเก่า 3 รอบ: ค่าความคล้ายสูงสุดตัวเดียวแยกผลที่ใช้ได้ออกจากผลที่ใช้ไม่ได้ไม่ได้
(Long-Wear 0.18 ได้คุชชั่น/อายแชโดว์ที่ใช้ได้ แต่ Body Contouring 0.23 ได้แชมพูผมร่วง) ตัวที่แยกได้คือ
"สินค้า 5 อันดับแรกของทั้งร้านอยู่ในหมวดหลักของเทรนด์กี่ชิ้น": เทรนด์ที่ใช้ได้ทุกตัวอยู่ในหมวดอย่างน้อย 2 จาก 5 (ต่ำสุดที่เจอ 2/5),
ที่ใช้ไม่ได้อยู่ 0-1 จาก 5 - คือสินค้าที่ใกล้เทรนด์ที่สุดในร้านไม่ได้อยู่ในหมวดที่รายงานใช้จัดอันดับ จึงจัดอันดับในหมวดนั้นแล้วไม่สะท้อนเทรนด์
"""

import os

TOP_N = 5
MIN_IN_MAIN = 2


def match_basis(trend_profile):
    """🆕 (2026-10-28) ฐานของข้อความจับคู่สินค้าของเทรนด์: "need" = เทรนด์สาย Search ที่มี beauty_need (ความต้องการความงามที่ AI อนุมานจาก ①-⑤ - ใช้เป็นข้อความหลัก)
    / "evidence" = ข้อความจากคำค้นที่ผ่านเกต ⑪ อย่างเดียว (รอบ 3 สายเดิม หรือตั้ง TREND_MATCH_BASIS=evidence = วิธีเดิมก่อน 2026-10-28: เทรนด์ที่คำค้นไม่ใช่เรื่องความงาม
    เช่น มาราธอน/ยาลดน้ำหนัก ได้สินค้าที่ไม่เกี่ยวเลย)"""
    need = (trend_profile or {}).get("beauty_need")
    if isinstance(need, dict) and (need.get("product_keywords") or need.get("key_benefits")) \
            and os.environ.get("TREND_MATCH_BASIS", "need").strip().lower() != "evidence":
        return "need"
    return "evidence"


def need_text(trend_profile):
    """🆕(2026-10-28) ข้อความ "ความต้องการความงามที่ AI อนุมาน" ของเทรนด์ = ชนิดสินค้า + ประโยชน์ (ว่างถ้าไม่มี beauty_need)"""
    need = (trend_profile or {}).get("beauty_need") or {}
    products = ", ".join(str(p) for p in need.get("product_keywords") or [] if p)
    return ". ".join(x for x in (products, str(need.get("key_benefits") or "").strip()) if x)


def category_agreement(top_groups, main_category):
    """กลุ่มสินค้า (หมวด L2) ของสินค้าที่ใกล้เทรนด์ที่สุด เรียงจากใกล้สุด + หมวดหลักของเทรนด์ ->
    {"category", "top_n", "in_main", "min_required", "ok"} หรือ None ถ้าไม่มีข้อมูลพอตัดสิน (ไม่มีหมวดหลัก / ไม่มีสินค้า)"""
    groups = list(top_groups or [])[:TOP_N]
    if not main_category or not groups:
        return None
    in_main = sum(1 for g in groups if g == main_category)
    need = min(MIN_IN_MAIN, len(groups))
    return {"category": main_category, "top_n": len(groups), "in_main": in_main, "min_required": need, "ok": in_main >= need}


def result_agreement(result):
    """1 เทรนด์ใน phase3_scale_validation_nvidia_result.json ("results"[key]) -> category_agreement ของมัน
    (ใช้ได้กับผลของรอบเก่าด้วย - อ่านแค่ top_matches กับ main_category ที่ ⑫ เก็บไว้แล้ว)"""
    result = result or {}
    main = result.get("main_category")
    main = main.get("category") if isinstance(main, dict) else main
    top = result.get("top_matches") or []
    return category_agreement([m.get("group") or m.get("category") for m in top], main)


def no_close_product(result):
    """True = สินค้าที่ใกล้เทรนด์ที่สุดส่วนใหญ่ไม่อยู่ในหมวดหลัก (ตัดสินไม่ได้ = False - ไม่ซ่อนอะไรเมื่อไม่รู้)"""
    ag = result_agreement(result)
    return bool(ag) and not ag["ok"]
