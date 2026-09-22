# -*- coding: utf-8 -*-
"""
Phase 3 — ทดสอบเกณฑ์ความสำเร็จที่ตั้งไว้เอง: "ทำให้ over-match ที่เจอใน Step 8 ลดลงไหม"

ดู Detail/05 งานที่ยังไม่ได้ทำ/Workflow v2 — แยกสายแล้วรวม.md ("Phase 3 — วัดผล") และ
Detail/04 การตรวจสอบและผลลัพธ์/ช่องว่างตลาด.md (เคสประวัติศาสตร์ที่ใช้ทดสอบที่นี่)

**ไม่ต้องยิง LLM ใหม่เลย ไม่ติดเครดิต OpenRouter** - ใช้ Gemini embedding เดิม (เหมือน
match_supply.py) ทดสอบย้อนกลับกับเคส over-match จริงที่เคยเจอมาแล้วในโปรเจกต์

**🆕 (2026-09-09) สลับฐานข้อมูลสินค้าจาก `database/product_fda.parquet` (1,774 SKU, 9 คอลัมน์) เป็น
`workspace/product/watsons_product.csv` (10,622 SKU จริง, 50 คอลัมน์ - มี 85% ของสินค้าเดิมอยู่ในนี้
แล้ว ถือเป็นชุดข้อมูลที่ครอบคลุมกว่าเดิม) ตามที่เจ้าของงานตัดสินใจ - ใช้ฟิลด์เชิงความหมายที่ลึกกว่าเดิม
มาก (Key_Benefits, Primary_Use_Case, Product_Insights) แทนที่จะมีแค่ Product Name+Content+Ingredients
ตื้นๆ แบบเดิม**

## เคสที่ใช้ทดสอบ (ทั้งหมดเป็นข้อมูลจริงจาก workspace/product/watsons_product.csv)

เทรนด์: "Trusted Natural Dermocosmetic Body Cleansing for Sensitive Skin" (จาก
step3_kg_strategic_keywords.csv ของการรันจริง 2026-08-18 - เทรนด์ที่ Step 8 over-match รุนแรงที่สุด
ในโปรเจกต์นี้ 209/521 สินค้าคะแนนเท่ากันเป๊ะ, 208/209 ไม่มี keyword ตรงกันเลยสักคำ)

1. **True positive ที่ควรได้คะแนนสูง:** Eucerin pH5 Sensitive Skin Wash Lotion - literal keyword
   matching ก็เจอตัวนี้อยู่แล้ว (เป็น 1 ใน 3 ตัวที่ยืนยันจริง) - ใช้เป็น sanity check ว่า embedding
   ไม่ทำให้ของที่เคยถูกอยู่แล้วกลายเป็นผิด
2. **False positive ที่ควรได้คะแนนต่ำ:** Veet Pure Hair Removal Cream - นี่คือตัวอย่างจริงที่ถูกยกมา
   ในเอกสาร [[ช่องว่างตลาด]] ว่า Step 8 (จับคู่ด้วยคลัสเตอร์แท็ก ไม่ใช่ keyword ตรงๆ) จับคู่กับเทรนด์นี้
   ผิดพลาดจริง - ครีมกำจัดขน ไม่เกี่ยวกับการทำความสะอาดผิวแพ้ง่ายเลย - embedding ควรให้คะแนนต่ำกว่า
   Eucerin อย่างชัดเจน
3. **Missed match ที่ literal keyword หาไม่เจอ แต่ควรจับคู่ได้ทางความหมาย:** Aigis Wash Intensive
   Care Moisture - มี **6 ชนิด Ceramide** (EOP/NS/NG/NP/AS/AP) + peptide ลดอาการคัน สำหรับ "dry to
   very dry, flaky skin" - ตรงกับ functional_consequence ของเทรนด์นี้ทุกประการ **แต่ไม่มีคำว่า
   sensitive/ceramide/gentle/dermo ในชื่อสินค้าเลย** จึงหลุดจาก literal keyword matching เดิมแน่นอน
   (ดู 208/209 ไม่มี keyword ตรงกันใน [[ช่องว่างตลาด]]) - นี่คือเคสที่พิสูจน์ว่า embedding ทำสิ่งที่
   keyword matching ทำไม่ได้จริง ไม่ใช่แค่ทฤษฎี

**เกณฑ์ผ่าน:** embedding ต้องเรียงลำดับถูก: Eucerin ≈ Aigis > Veet (ทั้งคู่ควรสูงกว่า Veet ชัดเจน)
และควรได้เห็นว่า Aigis (ที่ literal keyword พลาด) มีคะแนนใกล้เคียงกับ Eucerin (ที่ literal keyword เจอ)
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import PROJECT_ROOT, TOOL_DIR
from match_supply import build_trend_matchable_text, get_embedding, cosine_similarity

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)
from openai import OpenAI

client = OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                 api_key=os.getenv("GEMINI_KEY"))

# เทรนด์จริงจาก step3_kg_strategic_keywords.csv (การรันจริง 2026-08-18) - ทำ 6-มิติแบบเดียวกับที่ทำ
# กับ Phase 1 (manual, จากข้อมูลจริง ไม่ใช่ LLM output จริง - ยังต้องทดสอบผ่าน ⑪ อีกทีในอนาคต)
TREND_PROFILE = {
    "trend": "Trusted Natural Dermocosmetic Body Cleansing for Sensitive Skin",
    "attribute": "ceramide, colloidal oatmeal, panthenol, fragrance-free formulation, dermocosmetic-grade actives",
    "functional_consequence": "ปกป้อง/ซ่อมแซมเกราะผิว ให้ความชุ่มชื้นลึก บรรเทาการระคายเคือง ทำความสะอาดโดยไม่ทำให้ผิวแห้งตึง",
    "psychosocial_consequence": "รู้สึกไว้ใจได้เพราะแพทย์ผิวหนังแนะนำ รู้สึกสงบผ่อนคลายจากการดูแลผิวอย่างพิถีพิถัน",
    "job_to_be_done": "ทำความสะอาดผิวแพ้ง่าย/ผิวแห้งทุกวันโดยไม่กระตุ้นการระคายเคือง พร้อมรู้สึกเหมือนได้รับการดูแลระดับ dermocosmetic",
    "point_of_difference": "ใช้ส่วนผสม dermocosmetic ที่มีหลักฐาน (ceramide, colloidal oatmeal, panthenol) เน้นความบริสุทธิ์/hypoallergenic ไม่ใช่แค่สบู่ทำความสะอาดทั่วไป",
    "point_of_parity": "ต้องทำความสะอาดผิวได้จริงเหมือนผลิตภัณฑ์อาบน้ำทั่วไป",
}


def build_product_text(row):
    """🆕 (2026-09-09) รวมฟิลด์เชิงความหมายจาก watsons_product.csv (50 คอลัมน์) แทนที่ Product
    Name+Content+Ingredients ตื้นๆ แบบเดิมจาก product_fda.parquet - Key_Benefits/Primary_Use_Case/
    Product_Insights ดูผ่านการวิเคราะห์มาแล้ว (null rate ต่ำมาก 0.5-2%) ให้เนื้อหาที่มีความหมายกว่า
    ชื่อสินค้า+ส่วนผสมดิบๆ มาก"""
    parts = [
        str(row.get("product_name", "")),
        str(row.get("Key_Benefits", "")),
        str(row.get("Primary_Use_Case", "")),
        str(row.get("Product_Insights", ""))[:500],
        str(row.get("ingredients", ""))[:300],
    ]
    return " ".join(p for p in parts if p and p.lower() != "nan")


if __name__ == "__main__":
    df = pd.read_csv(TOOL_DIR / "product" / "watsons_product.csv", low_memory=False)

    cases = {
        "Eucerin pH5 Sensitive Skin Wash Lotion (true positive - keyword เจอเดิมอยู่แล้ว)":
            df[df["product_name"].astype(str).str.contains("Eucerin pH5 Sensitive Skin Wash", case=False, na=False)].iloc[0],
        "Aigis Wash Intensive Care Moisture (missed by keyword - ทดสอบว่า embedding จับได้ไหม)":
            df[df["product_name"].astype(str).str.contains("Aigis Wash Intensive", case=False, na=False)].iloc[0],
        "Veet Pure Hair Removal Cream 25G (known false positive จาก Step 8 เดิม)":
            df[df["product_name"].astype(str).str.contains(r"Veet Pure Hair Removal Cream Gentle Formula 25", case=False, na=False, regex=True)].iloc[0],
    }

    print("กำลัง embed trend profile...")
    trend_text = build_trend_matchable_text(TREND_PROFILE)
    trend_vec = get_embedding(trend_text, client)

    print("=" * 70)
    print(f"เทรนด์: {TREND_PROFILE['trend']}")
    print("=" * 70)

    results = []
    for label, row in cases.items():
        product_vec = get_embedding(build_product_text(row), client)
        sim = cosine_similarity(trend_vec, product_vec)
        results.append((label, row["product_name"], sim))

    results.sort(key=lambda x: x[2], reverse=True)
    print()
    for label, name, sim in results:
        print(f"[{sim:.4f}] {name}")
        print(f"          ({label})")
        print()

    print("=" * 70)
    eucerin_sim = next(s for l, n, s in results if "Eucerin" in n)
    aigis_sim = next(s for l, n, s in results if "Aigis" in n)
    veet_sim = next(s for l, n, s in results if "Veet" in n)

    print("ตรวจเกณฑ์ผ่าน:")
    print(f"  Eucerin ({eucerin_sim:.4f}) > Veet ({veet_sim:.4f})? {'✅' if eucerin_sim > veet_sim else '❌'}")
    print(f"  Aigis ({aigis_sim:.4f}) > Veet ({veet_sim:.4f})? {'✅' if aigis_sim > veet_sim else '❌'}")
    print(f"  Aigis ใกล้เคียง Eucerin ไหม (ห่างกัน <0.05)? "
          f"{'✅' if abs(aigis_sim - eucerin_sim) < 0.05 else f'⚠️ ห่างกัน {abs(aigis_sim - eucerin_sim):.4f}'}")
