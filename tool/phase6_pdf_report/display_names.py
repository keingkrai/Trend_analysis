# -*- coding: utf-8 -*-
"""
⑯/⑰/⑱ ชื่อเทรนด์ที่แสดงในรายงาน (🆕 2026-10-08) - แยกจากชื่อในไปป์ไลน์

ที่มา: DA ทักว่าชื่อเทรนด์ทำให้คนอ่านเข้าใจผิดได้ (เช่น "Editorial Nostalgia Blush" มาจากบทความเรื่องกระแสไม่ทาบลัช,
"Clinical Dermatology Hair Care" มาจากข่าวแผนธุรกิจของบริษัทเดียว) เพราะขั้นตั้งชื่อ (bootstrap.summarize_trend_clusters) เห็นแค่
คำสมาชิกของคลัสเตอร์ 15 คำ ผู้ใช้เลือก (2026-10-08): เปลี่ยน**แค่ชื่อที่แสดงในรายงาน** ให้กว้าง ไม่ผูกหมวดสินค้า (หมวดแสดงแยก)
ชื่อในไปป์ไลน์ไม่เปลี่ยน เพราะใช้สร้างคีย์เวิร์ด Google Trends / เป็นตัวระบุเทรนด์ข้ามขั้น / เป็นคีย์ของ cache ข้อความ LLM

ไฟล์ต่อรอบ phase6_display_names.json (ร่างจาก build_display_names.py แล้วคนตรวจ - ดู _note ในไฟล์)
  {"names": {"สาย::ชื่อเดิม": {"display": "...", "source": "llm" | "manual", "approved": true | false, ...}}}
รายงานใช้เฉพาะชื่อที่ **ผ่านการตรวจ** (source = manual หรือ approved = true) - ชื่อที่ LLM ร่างอย่างเดียวยังไม่ใช้ เพราะรอบแรก
(2026-10-08) หลายชื่อกว้างจนไม่บอกอะไร / ผิดเรื่อง (สองคลัสเตอร์ที่ใช้บทความร่วมกันได้ชื่อเดียวกัน) / เทรนด์เดียวกันต่างรอบได้ชื่อต่างกัน
ไม่มีไฟล์ / ไม่มีชื่อที่ผ่านการตรวจของเทรนด์ไหน -> ใช้ชื่อเดิม

ฟังก์ชันล้วน ไม่ import bootstrap ไม่เรียก API (เทสได้ด้วยข้อมูลปลอม)
"""
import json
import re
from pathlib import Path

DISPLAY_FILE = "phase6_display_names.json"
# คีย์ที่เป็นตัวระบุ/ค่าที่ไม่ใช่ข้อความ - ไม่แทนชื่อในค่าของคีย์เหล่านี้
SKIP_KEYS = frozenset({"name", "key", "stream", "display_name", "image", "image_url", "product_url", "url", "input_hash"})


def load_display_names(run_dir):
    """{"สาย::ชื่อเดิม": ชื่อที่แสดง} ของรอบ เฉพาะชื่อที่ผ่านการตรวจ (source = manual หรือ approved = true) - ไม่มีไฟล์ -> {}"""
    path = Path(run_dir) / DISPLAY_FILE
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: str(v.get("display") or "").strip() for k, v in (data.get("names") or {}).items()
            if str(v.get("display") or "").strip() and (v.get("source") == "manual" or v.get("approved") is True)}


def _replace_all(obj, patterns):
    """แทนชื่อเดิมด้วยชื่อที่แสดงในทุกข้อความ (ไม่สนตัวพิมพ์) ยกเว้นค่าของ SKIP_KEYS - คืน**สำเนาใหม่** ไม่แก้ของเดิม
    (ข้อความใน ctx บางส่วนชี้ไปที่ object เดียวกับ cache ข้อความ LLM - แก้ในตัวแล้วถ้ามีขั้นไหนบันทึก cache ทีหลัง ชื่อที่แสดงจะติดไปในไฟล์ผล)"""
    if isinstance(obj, str):
        for pat, new in patterns:
            obj = pat.sub(new, obj)
        return obj
    if isinstance(obj, list):
        return [_replace_all(v, patterns) for v in obj]
    if isinstance(obj, dict):
        return {k: (v if k in SKIP_KEYS else _replace_all(v, patterns)) for k, v in obj.items()}
    return obj


def apply_display_names(ctx, names):
    """ctx ของ report_data.build_context (หลังเติมข้อความ LLM แล้ว ทั้ง 2 ภาษา) <- ชื่อที่แสดง - แก้ ctx (ค่าระดับบนถูกแทนด้วยสำเนาใหม่)
    - เทรนด์ในหน้ารายละเอียด (ctx["trends"]) และแถวหน้า Top 5 / ภาพรวม (ctx["growth"]) ได้ช่อง display_name (ไม่มี = ชื่อเดิม)
    - ข้อความที่ LLM เขียนไว้ซึ่งเอ่ยชื่อเดิม ถูกแทนด้วยชื่อที่แสดง (name / key ยังเป็นชื่อเดิม - ใช้จับคู่ข้ามไฟล์และ cache)
    ใช้เฉพาะตอนพิมพ์รายงาน - ไม่แตะไฟล์ผลหรือ cache ของขั้นใดเลย / คืนจำนวนเทรนด์ที่ได้ชื่อใหม่"""
    by_key = {t["key"]: t for t in ctx.get("trends") or []}
    growth = ctx.get("growth") or {}
    rows = list(growth.get("all") or []) + [x for side in ("short", "long") for x in (growth.get("top5") or {}).get(side) or []]
    rows += list((growth.get("cagr_view") or {}).get("all") or [])   # 🆕 (2026-10-14) หน้าภาคผนวก CAGR ใช้ชื่อที่แสดงเดียวกับหน้าภาพรวม
    rows += list((growth.get("yoy_view") or {}).get("all") or [])    # และหน้าภาคผนวก YoY
    rows += list((growth.get("combined_view") or {}).get("all") or [])   # 🆕 (2026-10-19) หน้ารวม CAGR + YoY
    rows += list((growth.get("scatter_view") or {}).get("key") or [])    # และรายชื่อเทรนด์ใต้กราฟจุด
    old_to_new = {}
    for item in list(by_key.values()) + rows:
        new = names.get(item.get("key"))
        item["display_name"] = new or item.get("name")
        if new and item.get("name") and new != item["name"]:
            old_to_new[item["name"]] = new
    patterns = [(re.compile(re.escape(old), re.IGNORECASE), new.replace("\\", "\\\\"))
                for old, new in sorted(old_to_new.items(), key=lambda kv: -len(kv[0]))]
    if patterns:
        for k in list(ctx):
            if k not in SKIP_KEYS:
                ctx[k] = _replace_all(ctx[k], patterns)
    return sum(1 for t in by_key.values() if t["display_name"] != t["name"])
