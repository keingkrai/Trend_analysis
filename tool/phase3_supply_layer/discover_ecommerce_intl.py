# -*- coding: utf-8 -*-
"""
Discover Amazon/Sephora — pilot agent หมวด "อีคอมเมิร์ซต่างประเทศ" สำหรับขยาย Step 1 เป็นหลายหมวดข้อมูล
(ดู Detail/05 งานที่ยังไม่ได้ทำ/ขยาย Step 1 เป็นหลายหมวดข้อมูล.md)

คู่กับ discover_watsons_trend.py (ไทย) — เจ้าของงานต้องการทั้งไทยและต่างประเทศสำหรับหมวดอีคอมเมิร์ซ
(ตามหลักการ "ต้องแยก ค้นคนละภาษา/ภูมิภาค" ที่วางไว้ตั้งแต่ต้น ไม่แปลคำค้นไทย->อังกฤษตรงตัว)

=== เส้นทางที่ทดสอบมาก่อนจะได้เวอร์ชันนี้ (2026-08-27) ===
1. **Amazon.com (plain Playwright)** — ✅ ได้ผลจริงทันที ไม่ต้อง cloakbrowser เลย เห็นสินค้าเต็ม (ชื่อ/
   แบรนด์/ดาว/จำนวนรีวิว/"NNK+ bought in past month"/ราคา - ราคาขึ้นเป็น THB อัตโนมัติเพราะ IP ตรวจว่า
   ส่งของมาไทยได้) ไม่มี bot detection กันเลยสำหรับหน้าค้นหา (ต่างจาก Shopee ที่บล็อกสนิท)
2. **Sephora.com (plain Playwright)** — ❌ "Access Denied" ทันที (Akamai edge - errors.edgesuite.net)
3. **Sephora.com (cloakbrowser)** — ✅ ได้ผลจริง เห็นสินค้าเต็ม (แบรนด์/ชื่อ/จำนวนรีวิว/ราคา/badge "NEW")
   พร้อมของขวัญคล้าย Watsons: facet หมวด **"Clean at Sephora"** ที่เป็น trend tag จากผู้ค้าปลีกเอง
   (หน้าเว็บมีข้อความเตือนท้ายหน้าว่า "This site does not ship to your country" แต่ไม่ได้บล็อกเนื้อหา
   แสดงผลลัพธ์เต็มก่อนแล้วค่อยเตือนทีหลัง)

=== การออกแบบตอนนี้ ===
รวม 2 แพลตฟอร์มในสคริปต์เดียว เพราะเป็น "อีคอมเมิร์ซต่างประเทศ" หมวดเดียวกัน แค่มุมต่างกัน:
- **Amazon** = มวลรวม/แมส (marketplace ทั่วไป ครอบคลุมสินค้าทุกระดับราคา)
- **Sephora** = พรีเมียม/คิวเรตแล้ว (ผู้ค้าปลีกความงามเฉพาะทาง มี trend tag ของตัวเองเหมือน Watsons)

ทั้งคู่ใช้แนวทางเดียวกับ discover_watsons_trend.py: ดึงข้อความดิบเฉพาะช่วงผลค้นหา (ตัดแถบเมนู/footer
ทิ้งด้วย regex ขอบเขตคงที่) → ให้ LLM อ่านแล้วสรุปเป็นสัญญาณ แยก reported_total ออกมาเป็น metadata
เหมือนเดิม (ยอดจับคู่คำแบบหลวม ไม่ใช่ยอดที่ยืนยันว่าตรงประเด็น 100%)

สถานะ: ทดสอบ mechanism (ทั้งสองแพลตฟอร์มเข้าถึงได้จริง) แล้ว แต่ยังไม่เคยรัน end-to-end เต็มรูป
(สร้างคำค้น → ค้นจริงทั้งสองแพลตฟอร์ม → ให้ LLM สรุป) ควรรันดูผลจริงก่อนเชื่อว่า output มีคุณภาพดีพอ
"""
import asyncio
import json
import re
import sys
import urllib.parse
from pathlib import Path

# --- หา PROJECT_ROOT อัตโนมัติ (ย้ายไฟล์ไปโฟลเดอร์ไหนก็ยังหาเจอ) ---
for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import PROJECT_ROOT, OUTPUTS, tf, safe_json_parse  # noqa: E402




if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from cloakbrowser import launch_persistent_context_async  # noqa: E402

# --- ⚙️ ตั้งค่าก่อนรัน ---
TOPIC = "Trend Body Wash Thailand 2030"
N_QUERIES = 3           # ต่อแพลตฟอร์ม (รวม 2 แพลตฟอร์ม = 6 คำขอเว็บต่อรอบ)
PAGE_TIMEOUT_MS = 45000
WAIT_AFTER_LOAD_MS = 4000
SEPHORA_SESSION_DIR = PROJECT_ROOT / "sephora" / "browser_session"

# --- 1. แตกคำค้นภาษาอังกฤษจาก topic (LLM, ไม่แปลจากไทยตรงตัว) ---
SYSTEM_PROMPT_QUERIES = """You are a market researcher who understands how international (English-
speaking) online shoppers search for beauty/personal-care products on sites like Amazon and Sephora.
Generate English search queries that a real shopper would type in the search box.

Rules:
- Must be phrases a real shopper would type, NOT a literal translation of any Thai phrase - think in
  English from scratch.
- Short, 2-6 words, like a real e-commerce search box query (not a full sentence).
- Cover different angles: general product type, specific skin need, trending ingredient/feature.

Answer JSON only: {"queries": ["query 1", "query 2", ...]}
"""


def generate_english_queries(topic, n):
    try:
        response = tf.client.chat.completions.create(
            model=tf.MODEL_NAME_META,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_QUERIES},
                {"role": "user", "content": f"Topic: '{topic}'\nGenerate {n} queries."},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        parsed = safe_json_parse(response.choices[0].message.content)
        return parsed.get("queries", []) if parsed else []
    except Exception as e:
        print(f"⚠️ Error generating queries: {e}")
        return []


# --- 2a. ค้น Amazon ด้วย plain Playwright (ไม่มี bot detection กันหน้าค้นหา) ---
async def search_amazon_async(queries):
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        for q in queries:
            print(f"=== ค้นหา: '{q}' บน Amazon ===")
            url = "https://www.amazon.com/s?k=" + urllib.parse.quote(q)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                await page.wait_for_timeout(WAIT_AFTER_LOAD_MS)
                raw_text = await page.inner_text("body")

                # ผลน้อย (เช่น 20 รายการ) Amazon โชว์แค่ "20 results for..." ไม่มี "1-48 of" นำหน้า
                # ต่างจากผลเยอะที่โชว์ "1-48 of over 10,000 results for..." - regex ต้องรองรับทั้งคู่
                start_m = re.search(r"\n(?:[\d,\-]+ of (?:over )?)?[\d,]+ results for", raw_text)
                end_m = re.search(r"\nRelated searches\n", raw_text)
                clean_text = raw_text[start_m.start():end_m.start()] if (start_m and end_m) else raw_text[start_m.start():] if start_m else raw_text

                m = re.search(r"([\d,]+) results for", clean_text)
                reported_total = int(m.group(1).replace(",", "")) if m else None

                print(f"    เจอข้อความ {len(clean_text)} ตัวอักษร (Amazon รายงาน {reported_total if reported_total is not None else '?'} รายการ - อาจจับคำหลวม)")
                results.append({"platform": "Amazon", "query": q, "raw_text": clean_text, "reported_total": reported_total})
            except Exception as e:
                print(f"    ⚠️ ค้นหา '{q}' ล้มเหลว: {e}")
        await browser.close()
    return results


# --- 2b. ค้น Sephora ด้วย cloakbrowser (Akamai bot detection - plain Playwright โดน Access Denied) ---
async def search_sephora_async(queries):
    results = []
    context = await launch_persistent_context_async(str(SEPHORA_SESSION_DIR), headless=True)
    page = context.pages[0] if context.pages else await context.new_page()
    for q in queries:
        print(f"=== ค้นหา: '{q}' บน Sephora ===")
        url = "https://www.sephora.com/search?keyword=" + urllib.parse.quote(q)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
            await page.wait_for_timeout(WAIT_AFTER_LOAD_MS)
            raw_text = await page.inner_text("body")

            start_m = re.search(r"\n\d+ Results for", raw_text)
            clean_text = raw_text[start_m.start():] if start_m else raw_text

            m = re.search(r"\n(\d+) Results for", raw_text)
            reported_total = int(m.group(1)) if m else None

            print(f"    เจอข้อความ {len(clean_text)} ตัวอักษร (Sephora รายงาน {reported_total if reported_total is not None else '?'} รายการ - อาจจับคำหลวม)")
            results.append({"platform": "Sephora", "query": q, "raw_text": clean_text, "reported_total": reported_total})
        except Exception as e:
            print(f"    ⚠️ ค้นหา '{q}' ล้มเหลว: {e}")
    await context.close()
    return results


def search_ecommerce_intl(queries):
    async def _run():
        amazon = await search_amazon_async(queries)
        sephora = await search_sephora_async(queries)
        return amazon + sephora
    return asyncio.run(_run())


# --- 3. สรุปผลทั้งหมดเป็นสัญญาณเทรนด์ ---
SYSTEM_PROMPT_SUMMARY = """You are a trend analyst reading real search-result pages from two
international e-commerce sites - Amazon (mass-market general marketplace) and Sephora (curated,
premium beauty specialist retailer, which tags some products with its own "Clean at Sephora" trend
label). The raw text is unstructured (product names, brands, star ratings, review counts, "bought in
past month" social-proof figures, prices, badges like "NEW" all mixed together).

This is supply-side/market signal (what's actually being sold and how sellers position it), not
consumer discussion. Pay attention to differences between the mass-market Amazon results and the
curated Sephora results - they represent different market segments.

Important rule about numbers: each query has a "reported total" from the platform's own search count,
which may be a loose keyword match (not all results are necessarily relevant) - treat it only as a
rough supply-side signal, and say so explicitly if you cite it. Never treat review counts or "bought
in past month" figures as if they summed across products.

Answer in JSON: {"needs_and_pain_points": ["...", ...], "trend_signals": ["...", ...],
"notable_products": [{"title": "...", "platform": "Amazon|Sephora", "why_relevant": "..."}]}
Every conclusion must cite the actual content given - do not guess. If there isn't enough data, say so
briefly and honestly. Do not repeat the same point across different queries.
"""


def summarize_findings(topic, search_results):
    real_results = [r for r in search_results if r.get("raw_text")]
    if not real_results:
        return None
    blocks = []
    for r in real_results:
        reported = r.get("reported_total")
        reported_line = f" | reported total (loose match): {reported}" if reported is not None else ""
        blocks.append(
            f"--- {r['platform']} search results for '{r['query']}'{reported_line} ---\n"
            f"{r['raw_text'][:6000]}"
        )
    combined_text = "\n\n".join(blocks)
    user_prompt = f"Research topic: '{topic}'\n\n{combined_text}"
    try:
        response = tf.client.chat.completions.create(
            model=tf.MODEL_NAME_META,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_SUMMARY},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        return safe_json_parse(response.choices[0].message.content)
    except Exception as e:
        print(f"⚠️ Error summarizing: {e}")
        return None


# --- รัน pilot ---
if __name__ == "__main__":
    print(f"หัวข้อ: {TOPIC}")
    queries = generate_english_queries(TOPIC, N_QUERIES)
    print(f"คำค้นที่สร้าง: {queries}")

    if not queries:
        print("❌ สร้างคำค้นไม่สำเร็จ หยุดทำงาน")
        raise SystemExit(1)

    search_results = search_ecommerce_intl(queries)
    summary = summarize_findings(TOPIC, search_results)

    out_path = OUTPUTS / "ecommerce_intl_discovery_pilot.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "topic": TOPIC,
            "queries": queries,
            "search_results": search_results,
            "summary": summary,
        }, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(json.dumps(summary, ensure_ascii=False, indent=2) if summary else "(ไม่มีผลสรุป - อาจไม่เจอสินค้าเลย)")
    print("=" * 80)
    print(f"\nSaved -> {out_path}")
