# -*- coding: utf-8 -*-
"""
⑲ รายงานส่วนแบ่งตลาด — รายการปัจจัยแบบชุดปิด (closed list) ที่ใช้ทั้งระบบ

ทำไมต้องปิด: LLM (Phase 4) จัดหลักฐานจากเว็บเข้าได้แค่ปัจจัยในรายการนี้ - เจอเรื่องนอกรายการให้ใส่ "other" แล้วคนตรวจ
(ไม่ให้ LLM ตั้งชื่อปัจจัยเอง ซึ่งจะได้ชื่อไม่ซ้ำกันทุกรอบ รวมเป็นหน้าภาพรวมไม่ได้) และรายงานใช้ป้ายชื่อชุดเดียวกัน

source:
    data = วัดจาก Euromonitor / อย. ได้ตรงๆ (market_facts.category_factors) - เว็บใช้หาคำอธิบายเพิ่มเท่านั้น
    web  = มีได้แค่หลักฐานจากเว็บ (ข้อมูลไม่มีมิติแบรนด์ x เรื่องนี้ เช่น Euromonitor ไม่มีช่องทางขายรายแบรนด์)

คำในป้าย/คำอธิบายเป็นกลาง ไม่บอกว่าแบรนด์ไหนชนะหรือแพ้ (เจ้าของงานขอ 2026-10-12)
"""

FACTORS = {
    # ---- วัดจากข้อมูล ----
    "channel_shift": {
        "source": "data",
        "label_en": "Sales channels moving", "label_th": "ช่องทางขายที่เปลี่ยนไป",
        "description": "Share of category sales moving between channels: online shops, direct selling, department "
                       "stores, pharmacies, beauty stores, salons, supermarkets, convenience stores.",
    },
    "concentration": {
        "source": "data",
        "label_en": "Smaller and newer brands", "label_th": "แบรนด์เล็กและแบรนด์ใหม่",
        "description": "Share held by brands outside the large, long-tracked brands rising or falling; new brands "
                       "entering the market.",
    },
    "premium_shift": {
        "source": "data",
        "label_en": "Premium vs mass", "label_th": "สินค้าพรีเมียมกับสินค้าทั่วไป",
        "description": "Share of premium-priced products in the category rising or falling.",
    },
    "launch_activity": {
        "source": "data",
        "label_en": "New product launches", "label_th": "การออกสินค้าใหม่",
        "description": "Number of new product notifications at the Thai FDA, and the share that is imported.",
    },
    # ---- มีแค่หลักฐานจากเว็บ ----
    "positioning": {
        "source": "web",
        "label_en": "Brand positioning", "label_th": "จุดยืนของแบรนด์",
        "description": "How the brand presents itself and is seen: dermatologist or clinical skin care, natural, "
                       "Korean or Japanese beauty, halal, value-for-money, luxury.",
    },
    "marketing": {
        "source": "web",
        "label_en": "Marketing and communication", "label_th": "การตลาดและการสื่อสาร",
        "description": "Advertising, brand ambassadors and celebrities, influencers and live selling, social media "
                       "content, sponsorships.",
    },
    "distribution": {
        "source": "web",
        "label_en": "Where the brand is sold", "label_th": "จุดขายของแบรนด์",
        "description": "The brand opening or leaving sales points: official online stores, pharmacies, Watsons or "
                       "Boots, convenience stores, own shops, direct-selling networks, export to or from Thailand.",
    },
    "pricing": {
        "source": "web",
        "label_en": "Price and promotions", "label_th": "ราคาและโปรโมชัน",
        "description": "Price changes, discounts, smaller pack sizes, sachets, bundles, mega-sale campaigns.",
    },
    "product": {
        "source": "web",
        "label_en": "Products and innovation", "label_th": "สินค้าและนวัตกรรม",
        "description": "New ranges, a best-selling hero product, new ingredients or claims, reformulation.",
    },
    "business_change": {
        "source": "web",
        "label_en": "Company changes", "label_th": "การเปลี่ยนแปลงของบริษัท",
        "description": "Change of owner or distributor, mergers, restructuring, change of business model, "
                       "exiting a market or category.",
    },
    "reputation": {
        "source": "web",
        "label_en": "Trust and reputation", "label_th": "ความเชื่อมั่นและชื่อเสียง",
        "description": "Product recalls, regulator warnings, safety concerns, awards, consumer trust.",
    },
    "consumer_shift": {
        "source": "web",
        "label_en": "Shoppers' habits", "label_th": "พฤติกรรมผู้ซื้อ",
        "description": "Changes in what or how shoppers buy: ingredient awareness, preference for local or imported "
                       "brands, buying online, spending power, tourism.",
    },
    "other": {
        "source": "web",
        "label_en": "Other (for review)", "label_th": "อื่นๆ (รอตรวจ)",
        "description": "Evidence that does not fit any factor above. Not shown in the report until a person reviews it.",
    },
}

DATA_FACTORS = [k for k, v in FACTORS.items() if v["source"] == "data"]
WEB_FACTORS = [k for k, v in FACTORS.items() if v["source"] == "web"]
