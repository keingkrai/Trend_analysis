# -*- coding: utf-8 -*-
"""
Phase 3 — ⑫ ชั้นอุปทาน: จับคู่ "จุดเด่นเทรนด์" (⑪) กับข้อมูลตลาดจริงจาก Watsons/Amazon/Sephora

ดู Detail/05 งานที่ยังไม่ได้ทำ/Workflow v2 — แยกสายแล้วรวม.md ส่วน "⑫ ชั้นอุปทาน" และ
Detail/05 งานที่ยังไม่ได้ทำ/เกณฑ์สกัดจุดเด่นเทรนด์สำหรับจับคู่สินค้า.md (เกณฑ์ 6 มิติที่ใช้ที่นี่)

ตอบคำถาม: "เทรนด์นี้ตลาดมีของขายแล้วแค่ไหน" → เทรนด์กำลังโต + ตลาดยังไม่มีของ = โอกาส

## กลไกจับคู่ที่ใช้: semantic embedding similarity (ตามที่เอกสารเกณฑ์แนะนำไว้)

เหตุผลที่ไม่ใช้ LLM ตัดสินทีละคู่ตรงๆ: เสี่ยง over-match ซ้ำแบบ Step 8 เดิม/`market_gap_check.py`
(ดู docstring ของ [[เกณฑ์สกัดจุดเด่นเทรนด์สำหรับจับคู่สินค้า]]) — embedding similarity ให้ตัวเลข
(cosine similarity) ที่ตั้ง threshold ได้ชัดเจนกว่า

**🆕 พบว่ามี embedding API ใช้ได้แล้วจริง โดยไม่ต้องรอ OpenRouter credit:** `GEMINI_KEY` ที่มีอยู่แล้ว
(ใช้กับ `use_gemini()`/`use_gemma()`) รองรับ `gemini-embedding-001` ผ่าน endpoint OpenAI-compatible
เดียวกัน — ทดสอบยิงจริงแล้ว (2026-09-07) ได้ vector 3072 มิติ **นี่คือจุดเดียวใน Phase 3 ทั้งหมดที่
ทดสอบจริงได้วันนี้เลย ไม่ต้องรอเครดิต OpenRouter** เหมือนงานอื่นๆ ในโปรเจกต์

## กฎการจับคู่ (ตามเอกสารเกณฑ์ 6 มิติ)

**ใช้ได้:** functional_consequence, psychosocial_consequence, job_to_be_done, point_of_difference
**ห้ามใช้:** attribute (จุดที่เคยพังมาแล้ว 2 รอบ — Step 8 เดิม + market_gap_check.py),
point_of_parity (สินค้าทุกตัวในหมวดมีเหมือนกัน ใช้จับคู่แล้ว over-match ทันที)
"""
import numpy as np


def build_trend_matchable_text(trend_profile):
    """รวม 4 มิติที่อนุญาตให้ใช้จับคู่ (ไม่รวม attribute/point_of_parity) เป็นข้อความเดียวสำหรับ embed

    trend_profile: dict ตาม schema ใน เกณฑ์สกัดจุดเด่นเทรนด์สำหรับจับคู่สินค้า.md
        {trend, attribute, functional_consequence, psychosocial_consequence, job_to_be_done,
         point_of_difference, point_of_parity}
    """
    parts = [
        trend_profile.get("functional_consequence", ""),
        trend_profile.get("psychosocial_consequence", ""),
        trend_profile.get("job_to_be_done", ""),
        trend_profile.get("point_of_difference", ""),
    ]
    return " ".join(p for p in parts if p and p != "ข้อมูลไม่พอ")


_LOGISTICS_NOISE_MARKERS = (
    "does not ship", "ship to", "shipping", "delivery to", "not available in",
    "access may be", "access to the", "eligible-order threshold",
)


def _is_logistics_noise(text):
    """คัดกรองประโยคที่พูดถึง "ส่งของได้ไหม/เข้าถึงได้ไหม" ออก - ไม่ใช่คุณลักษณะ/ประโยชน์/ตำแหน่งสินค้า
    เลยแม้แต่น้อย จึงไม่ควรเข้าไปอยู่ในกลุ่มที่ใช้จับคู่กับจุดเด่นเทรนด์ตั้งแต่แรก (ไม่ว่าจะจับคู่กับ
    เทรนด์ไหนก็ตาม) - ดู docstring ของ load_market_bullets() ด้านล่างสำหรับที่มาของปัญหานี้
    """
    t = text.lower()
    return any(marker in t for marker in _LOGISTICS_NOISE_MARKERS)


def load_market_bullets(pilot_json):
    """ดึงประโยคบรรยายตลาดจาก pilot output (discover_watsons_trend.py/discover_ecommerce_intl.py)

    โครงสร้างจริงที่ pilot คืนมา (ตรวจสอบจากไฟล์จริงแล้ว 2026-09-07): ไม่ใช่แคตตาล็อกสินค้าเป็นแถวๆ
    แบบ database/exfac_products.parquet - เป็น**บทสรุปเชิงบรรยายตลาด** (needs_and_pain_points +
    trend_signals เป็น list ของประโยค) เพราะงั้นการจับคู่ที่นี่คือ "เทรนด์ vs สิ่งที่ตลาดคุยถึงอยู่แล้ว"
    ไม่ใช่ "เทรนด์ vs สินค้าแต่ละ SKU" (นั่นคือหน้าที่ของ ⑬ จับคู่สินค้า EXFAC ที่ใช้แคตตาล็อกจริงต่างหาก)

    🆕 (2026-09-07, ข้อ 31 ใน Backlog) กรอง**ประโยคเรื่อง logistics/การส่งของ** ออกด้วย - เจอ
    false-positive จริง: "Thai Botanical Antioxidant Beauty" ไปแมตช์กับประโยค "Thailand access may
    be a practical pain point... does not ship to..." เพราะคำว่า "Thailand" ตรงกันโดยบังเอิญ ไม่ใช่
    ความหมายเชิงเนื้อหาจริง (สารสกัดพืชไทย vs ปัญหาส่งของข้ามประเทศ) - ตรวจสอบครบทั้ง 27 ประโยคจริง
    (15 ไทย + 12 ต่างประเทศ) แล้วพบว่ามีแค่ **1 ประโยคเดียว** ที่เป็นปัญหานี้ ไม่ใช่ปัญหาทั้งชุดข้อมูล -
    กรองด้วย keyword list เฉพาะกลุ่ม "พูดถึงการส่งของ/เข้าถึงได้ไหม" (ไม่ใช่กรองคำว่า "Thailand" ทิ้งตรงๆ
    เพราะ "ความเป็นไทย" เป็นจุดเด่นจริงของเทรนด์นี้ฝั่ง trend profile เอง - จะกรองคำว่า Thailand ทิ้งทั้ง
    สองฝั่งจะทำลายสัญญาณจริงไปด้วย) - ประโยคที่กล่าวถึง "Thailand" ในบริบทอื่น (เช่น
    "97 loose-match results for 'best body wash Thailand'") **ไม่ถูกกรองออก** เพราะไม่ใช่ logistics
    noise แต่เป็นข้อมูลปริมาณการค้นหาที่ยังมีประโยชน์จริง
    """
    summary = pilot_json.get("summary", {})
    bullets = []
    n_filtered = 0
    for field in ("needs_and_pain_points", "trend_signals"):
        for text in summary.get(field, []):
            if _is_logistics_noise(text):
                n_filtered += 1
                continue
            bullets.append({"text": text, "field": field})
    if n_filtered:
        print(f"    (กรอง logistics noise ออก {n_filtered} ประโยค)")
    return bullets


def get_embedding(text, client, model="gemini-embedding-001"):
    """ห่อ Gemini embedding API (ใช้ GEMINI_KEY เดิม ไม่ต้องรอ OpenRouter credit)"""
    resp = client.embeddings.create(model=model, input=[text])
    return np.array(resp.data[0].embedding)


def cosine_similarity(a, b):
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0


def embed_market_bullets(market_bullets, client):
    """embed ประโยคตลาดทั้งหมดไว้ล่วงหน้าครั้งเดียว - คืน list เดิมพร้อมคีย์ "vector" เพิ่มเข้าไป

    🆕 (2026-09-07) แยกออกมาจาก compute_market_coverage() เพราะเจอจริงว่าโค้ดเดิม embed ประโยคตลาด
    ชุดเดียวกันซ้ำทุกครั้งที่เทียบกับเทรนด์ใหม่ (5 เทรนด์ x 27 ประโยค = 135 call ทั้งที่ประโยคตลาดมีแค่
    27 ประโยคไม่เปลี่ยนเลย) ทำให้ชน **free-tier quota ของ Gemini embedding: 100 request/นาที**
    (`embed_content_free_tier_requests` - คนละโควตากับ chat model ที่เจอมาก่อนหน้านี้ทั้งหมด) -
    แก้โดย embed ประโยคตลาดครั้งเดียวก่อน แล้วเทียบกับทุกเทรนด์ซ้ำได้โดยไม่ต้อง call API ซ้ำเลย
    ลดจาก 135 เหลือ ~32 call รวม (27 ประโยคตลาด + 5 เทรนด์) สำหรับเทียบ 5 เทรนด์เต็ม
    """
    embedded = []
    for bullet in market_bullets:
        vec = get_embedding(bullet["text"], client)
        embedded.append({**bullet, "vector": vec})
    return embedded


def compute_market_coverage(trend_profile, market_bullets_embedded, client, top_k=3):
    """คำนวณว่าตลาด (จาก pilot data) คุยถึงจุดเด่นของเทรนด์นี้มากแค่ไหนแล้ว

    market_bullets_embedded: output ของ embed_market_bullets() (ต้อง embed ไว้ล่วงหน้าแล้ว - ดู
    เหตุผลใน docstring ของฟังก์ชันนั้น)

    Returns:
        dict {coverage_score, top_matches, n_bullets_compared}
        coverage_score: ค่าเฉลี่ยของ top_k similarity ที่สูงสุด (0-1) - สูง = ตลาดคุยถึงแล้วเยอะ
        (อิ่มตัว), ต่ำ = ตลาดยังไม่มีใครพูดถึงจุดเด่นนี้ (ช่องว่าง/โอกาส)
    """
    trend_text = build_trend_matchable_text(trend_profile)
    trend_vec = get_embedding(trend_text, client)

    scored = []
    for bullet in market_bullets_embedded:
        sim = cosine_similarity(trend_vec, bullet["vector"])
        scored.append({"similarity": round(sim, 4), "field": bullet["field"], "text": bullet["text"]})

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    top_matches = scored[:top_k]
    coverage_score = (sum(m["similarity"] for m in top_matches) / len(top_matches)) if top_matches else 0.0

    return {
        "coverage_score": round(coverage_score, 4),
        "top_matches": top_matches,
        "n_bullets_compared": len(market_bullets_embedded),
    }


def percentile_rank(score, all_scores):
    """เปอร์เซ็นต์ของคะแนนในชุดที่ <= คะแนนนี้ (0-100) - ใช้แทน absolute threshold

    ⚠️ ข้อจำกัดสำคัญที่ต้องรู้เสมอ: นี่คือ percentile **สัมพัทธ์กับชุดเทรนด์ที่ส่งเข้ามาพร้อมกันตอนนี้
    เท่านั้น** ถ้าเพิ่มเทรนด์ใหม่เข้ามาทีหลัง (เช่น จาก News-Intl/Thai) percentile ของเทรนด์เดิมทุกตัว
    จะเปลี่ยนไปด้วยทันที - ต่างจาก absolute threshold ที่ตัดสินแยกอิสระต่อเทรนด์ ไม่กระทบกัน
    เป็น trade-off ที่ตั้งใจรับ: ยอมให้ผลไม่เสถียรข้ามรอบ แลกกับคำตอบที่สะท้อนข้อมูลจริงที่มีอยู่ตอนนี้
    แทนเลขเดา (0.75) ที่พิสูจน์แล้วว่าผิดจริง (ดู Backlog ข้อ 31 - ค่าจริงทั้งหมดอยู่แค่ 0.61-0.69
    ไม่มีจุดไหนถึง 0.75 เลยสักจุด ทำให้ทุกเทรนด์ตกกลุ่มเดียวกันหมด)
    """
    n = len(all_scores)
    if n <= 1:
        return 50.0
    rank = sum(1 for s in all_scores if s <= score)
    return round(rank / n * 100, 1)


def _tier_label(pct):
    """แบ่ง percentile เป็น 3 ระดับ (tertile) - สูง/กลาง/ต่ำเทียบกับเทรนด์อื่นในชุดเดียวกัน"""
    if pct >= 67:
        return "สูง (ค่อนข้างอิ่มตัวเทียบกับเทรนด์อื่นที่ทดสอบพร้อมกัน)"
    if pct <= 33:
        return "ต่ำ (ช่องว่างเทียบกับเทรนด์อื่นที่ทดสอบพร้อมกัน)"
    return "ปานกลาง"


def assess_opportunity(trend_name, coverage_th, all_th_scores, z_delta=None):
    """แปลผล coverage score เป็นข้อสรุปโอกาสทางธุรกิจ - ใช้ percentile เทียบกับเทรนด์อื่นแทน absolute
    threshold (เดิมใช้ 0.75 ตายตัว พิสูจน์แล้วว่าผิด - ดู docstring ของ percentile_rank() ด้านบน)

    ตรรกะตามที่ระบุไว้ใน Workflow v2: "เทรนด์กำลังโต + ตลาดยังไม่มีของ = โอกาส"

    🆕 (2026-09-09) ตัดการเทียบ "ไทย vs ต่างประเทศ" (Amazon/Sephora) ออกทั้งหมด ตามที่เจ้าของงานตัดสินใจ
    - เดิม assess_opportunity() รับ coverage_intl/all_intl_scores ด้วย ทำ 4-quadrant เทียบตลาดไทยกับ
    ตลาดต่างประเทศ (เช่น "หน้าต่างโอกาส" = ต่างประเทศคุยเยอะแต่ไทยยังไม่มี) - ตอนนี้ประเมินแค่ตลาดไทย
    อย่างเดียว เทียบ percentile กับเทรนด์อื่นในชุดเดียวกันเท่านั้น (ไม่มีมิติ "มาจากต่างประเทศไหม" อีก
    ต่อไป) - `discover_ecommerce_intl.py`/`ecommerce_intl_discovery_pilot.json` ยังเก็บไว้เป็นข้อมูล
    ที่มีอยู่แล้ว (ไม่ลบ) แต่ไม่ได้ใช้ในการวิเคราะห์นี้อีกต่อไป

    Args:
        all_th_scores: coverage score ของ**ทุกเทรนด์**ในชุดที่ทดสอบพร้อมกัน (รวมเทรนด์นี้ด้วย) ใช้
            คำนวณ percentile - ต้องส่งมาจากรอบเดียวกันเสมอ อย่าผสมข้ามรอบทดสอบ
    """
    pct_th = percentile_rank(coverage_th, all_th_scores)
    tier_th = _tier_label(pct_th)

    if pct_th <= 33:
        gap_type = "🎯 ช่องว่างตลาดไทย — ตลาดไทยพูดถึงจุดเด่นนี้น้อยกว่าเทรนด์อื่นที่ทดสอบพร้อมกัน (โอกาส)"
    elif pct_th >= 67:
        gap_type = "⚠️ อิ่มตัวในตลาดไทย — ตลาดไทยพูดถึงจุดเด่นนี้เยอะกว่าเทรนด์อื่น ต้องหา point_of_difference ที่ชัดกว่า"
    else:
        gap_type = "◽ ปานกลาง — ไม่โดดเด่นทั้งสองทาง เทียบกับเทรนด์อื่นที่ทดสอบพร้อมกัน"

    return {
        "trend": trend_name,
        "percentile_th": pct_th,
        "tier_th": tier_th,
        "gap_assessment": gap_type,
        "z_delta_available": z_delta is not None, "z_delta": z_delta,
    }


# 5 trend profile รวม 2 ตัวเดิมจาก เกณฑ์สกัดจุดเด่นเทรนด์สำหรับจับคู่สินค้า.md + 3 ตัวใหม่ที่ทำ
# manual เพิ่มตอนนี้ (2026-09-07) จากข้อมูลจริงใน phase1_paper_stream_result.json (Key Ingredients/
# Key Benefits/Target/Outlook/Analysis) - ทำตามกฎเดียวกันทุกประการ (ห้ามเดาเกินข้อมูลที่ให้มา
# โดยเฉพาะ psychosocial_consequence ที่เสี่ยงตีความเกินสุด)
#
# 🆕 (2026-09-09) ย้ายจากในบล็อก __main__ มาไว้ระดับโมดูล เพื่อให้ import ใช้ซ้ำได้จากสคริปต์อื่น
# (validate_at_scale.py - ทดสอบสเกลใหญ่กับ 1,774 SKU จริง) โดยไม่ต้อง copy-paste ซ้ำ
TREND_PROFILES = [
        {
            "trend": "Waterless Beauty and Solid Cleansing",
            "attribute": "รูปแบบ solid/bar, สารทำความสะอาด syndet, kaolin clay, น้ำมันพืช",
            "functional_consequence": "ทำความสะอาดได้โดยไม่ต้องมีน้ำเป็นตัวพา, บรรจุภัณฑ์เล็ก/เบาลง, พกพาผ่านด่านตรวจสัมภาระเหลวได้",
            "psychosocial_consequence": "รู้สึกเป็นผู้บริโภคที่มีความรับผิดชอบต่อสิ่งแวดล้อม, รู้สึกฉลาด/มีประสิทธิภาพเวลาเดินทาง",
            "job_to_be_done": "ทำความสะอาดร่างกายตอนเดินทางโดยไม่ต้องกังวลเรื่องของเหลวหก/กฎสัมภาระ พร้อมลดผลกระทบสิ่งแวดล้อม",
            "point_of_difference": "ไม่ใช้น้ำเป็นส่วนประกอบหลักเลย ไม่มีความเสี่ยงหกระหว่างเดินทาง",
            "point_of_parity": "ต้องทำความสะอาดผิวได้จริง ต้องมีฟองพอสมควร",
        },
        {
            "trend": "Evidence-Based Barrier-Friendly Cleansing",
            "attribute": "ระบบสารทำความสะอาดอ่อนโยน, ceramides, panthenol, betaine, มีข้อมูลทดสอบรองรับ",
            "functional_consequence": "ระคายเคืองน้อยลง, ผิวไม่แห้งตึงหลังล้าง, ใช้ได้ทุกวันโดยไม่สะสมความเสียหายต่อเกราะผิว",
            "psychosocial_consequence": "รู้สึกอุ่นใจ/เชื่อถือได้เพราะมีหลักฐานรองรับ ไม่ใช่แค่คำโฆษณาลอยๆ",
            "job_to_be_done": "ทำความสะอาดทุกวันโดยไม่กระตุ้นการระคายเคืองหรือทำร้ายผิวที่บอบบางอยู่แล้ว",
            "point_of_difference": "สื่อสารด้วยข้อมูลการทดสอบจริง ผสานส่วนผสมดูแลเกราะผิวเข้ากับการทำความสะอาด",
            "point_of_parity": "ต้องทำความสะอาดได้ ต้องไม่ระคายเคืองเห็นชัด",
        },
        {
            "trend": "Natural Oil-Control Anhydrous Lotion Bars",
            "attribute": "Starch (tapioca/corn), silica, plant-derived emollients, natural waxes, รูปแบบ lotion bar แบบไม่มีน้ำ",
            "functional_consequence": "ดูดซับความมันส่วนเกิน ลดความเหนอะหนะ ทาง่ายขึ้น ควบคุมความหนืด ผิวสัมผัสแห้งไม่มัน (dry-touch)",
            "psychosocial_consequence": "รู้สึกว่าใช้ผลิตภัณฑ์ธรรมชาติที่ให้ผลลัพธ์คุมมันได้จริง ไม่ต้องพึ่งสารเคมีหนัก",
            "job_to_be_done": "บำรุงผิวแบบให้ความชุ่มชื้นโดยไม่ทิ้งความมันเยิ้ม เหมาะกับสภาพอากาศร้อนชื้นหรือผิวมัน พกพาสะดวกไม่ต้องพึ่งน้ำ",
            "point_of_difference": "ใช้ starch-based rheology modifier แทนสารสังเคราะห์ทั่วไป แก้ปัญหาความเหนอะหนะที่ lotion bar ทั่วไปมักเจอ",
            "point_of_parity": "ต้องให้ความชุ่มชื้น/บำรุงผิวได้เหมือนมอยส์เจอไรเซอร์ทั่วไป",
        },
        {
            "trend": "Thai Botanical Antioxidant Beauty",
            "attribute": "Siam violet pearl, Apigenin 7-O-glucoside, สารสกัดพืชไทย, Thai natural actives",
            "functional_consequence": "ต้านอนุมูลอิสระ ชะลอวัย ปกป้องผิวจากมลภาวะ/สิ่งแวดล้อม ทำความสะอาดอย่างอ่อนโยน",
            "psychosocial_consequence": "รู้สึกภูมิใจ/เชื่อมโยงกับความเป็นไทย ได้ใช้ของแท้ที่มีที่มาชัดเจนน่าเชื่อถือ",
            "job_to_be_done": "ใช้ผลิตภัณฑ์ที่ผสานภูมิปัญญา/วัตถุดิบไทยเข้ากับหลักฐานวิทยาศาสตร์ เพื่อดูแลผิวจากอนุมูลอิสระและวัยที่เพิ่มขึ้น",
            "point_of_difference": "มีที่มาจากพืชไทยเฉพาะถิ่น (Siam violet ฯลฯ) ไม่ใช่สารสกัดทั่วไปที่หาได้จากทุกที่ ผสานเรื่องราวแหล่งกำเนิดกับหลักฐานวิทยาศาสตร์",
            "point_of_parity": "ต้องให้ผลลัพธ์ต้านอนุมูลอิสระ/ชะลอวัยได้จริงเหมือนผลิตภัณฑ์แอนตี้ออกซิแดนท์ทั่วไป",
        },
        {
            "trend": "Biodegradable Bioactive Hydrogel Beauty",
            "attribute": "Alginate, cellulose/bacterial cellulose, chitosan, hyaluronic acid, plant polysaccharides, รูปแบบ hydrogel",
            "functional_consequence": "ให้ความชุ่มชื้นลึกและกักเก็บความชุ่มชื้น เข้ากันได้ดีกับผิวแพ้ง่าย ควบคุมการปลดปล่อยสารออกฤทธิ์ได้ ย่อยสลายได้ตามธรรมชาติ",
            "psychosocial_consequence": "รู้สึกว่าเลือกใช้ผลิตภัณฑ์ที่รับผิดชอบต่อสิ่งแวดล้อมและปลอดภัยต่อผิวตัวเองไปพร้อมกัน",
            "job_to_be_done": "ใช้เป็นระบบนำส่งสารบำรุง (มาส์ก/แผ่นแปะ/เซรั่ม) ที่ให้ความชุ่มชื้นเข้มข้นสำหรับผิวแพ้ง่าย โดยไม่ทิ้งขยะที่ย่อยสลายยาก",
            "point_of_difference": "ใช้วัสดุชีวภาพย่อยสลายได้แทน synthetic polymer ทั่วไป ให้ทั้งความเข้ากันได้ทางชีวภาพและควบคุมการปลดปล่อยสารได้ ใช้ได้หลายรูปแบบผลิตภัณฑ์",
            "point_of_parity": "ต้องให้ความชุ่มชื้น/บำรุงผิวได้เหมือน hydrogel หรือมาส์กทั่วไป",
        },
    ]


if __name__ == "__main__":
    # ทดสอบจริงด้วย: (1) 5 trend profile ข้างบน (2) ข้อมูลตลาดจริงจาก pilot Watsons + Amazon/Sephora
    # (3) embedding จริงผ่าน Gemini - ทดสอบได้ครบวันนี้ ไม่ติดเครดิต OpenRouter
    import os
    import sys
    import json
    from pathlib import Path
    from dotenv import load_dotenv

    for _p in Path(__file__).resolve().parents:
        if (_p / "common" / "bootstrap.py").exists():
            sys.path.insert(0, str(_p))
            break
    from common.bootstrap import PROJECT_ROOT

    load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)
    from openai import OpenAI
    client = OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                     api_key=os.getenv("GEMINI_KEY"))

    # 🆕 (2026-09-09) ตัด Amazon/Sephora (ตลาดต่างประเทศ) ออกทั้งหมดตามที่เจ้าของงานตัดสินใจ - ประเมิน
    # แค่ตลาดไทย (Watsons) อย่างเดียว ไม่มีการเทียบ "ไทย vs ต่างประเทศ" อีกต่อไป (ดู docstring ของ
    # assess_opportunity() ด้านบน) - `discover_ecommerce_intl.py`/`ecommerce_intl_discovery_pilot.json`
    # ยังเก็บไว้เป็นข้อมูลที่มีอยู่แล้ว แค่ไม่ใช้ในการวิเคราะห์นี้อีกต่อไป
    OUTPUTS_ROOT = PROJECT_ROOT / "outputs"
    with open(OUTPUTS_ROOT / "watsons_trend_discovery_pilot.json", encoding="utf-8") as f:
        watsons = json.load(f)

    market_th = load_market_bullets(watsons)
    print(f"ตลาดไทย (Watsons): {len(market_th)} ประโยค")

    # 🆕 embed ประโยคตลาดล่วงหน้าครั้งเดียว ก่อนวนเทียบกับทุกเทรนด์ (ดู docstring ของ
    # embed_market_bullets() - แก้ปัญหาชนโควตา embedding 100 request/นาทีของ Gemini)
    print("กำลัง embed ประโยคตลาด (ครั้งเดียว ใช้ซ้ำได้กับทุกเทรนด์)...")
    market_th_embedded = embed_market_bullets(market_th, client)
    print("เสร็จแล้ว\n")

    # 🆕 (2026-09-07) ต้องคำนวณ coverage score ของ**ทุกเทรนด์ก่อน**แล้วค่อยทำ percentile - ไม่งั้นจะ
    # ไม่มีชุดข้อมูลให้เทียบ (ดู docstring ของ percentile_rank() ทำไมถึงต้องเป็นแบบนี้)
    all_results = []
    for profile in TREND_PROFILES:
        result_th = compute_market_coverage(profile, market_th_embedded, client)
        all_results.append({"trend": profile["trend"], "result_th": result_th})

    all_th_scores = [r["result_th"]["coverage_score"] for r in all_results]

    for r in all_results:
        print("=" * 70)
        print(f"เทรนด์: {r['trend']}")
        print("=" * 70)

        result_th = r["result_th"]
        print(f"\n🇹🇭 Coverage (ไทย/Watsons): {result_th['coverage_score']}")
        for m in result_th["top_matches"]:
            print(f"   [{m['similarity']:.3f}] {m['text'][:90]}...")

        assessment = assess_opportunity(r["trend"], result_th["coverage_score"], all_th_scores)
        print(f"\n📊 Percentile: ไทย={assessment['percentile_th']}% ({assessment['tier_th']})")
        print(f"   สรุป: {assessment['gap_assessment']}")
        print()
