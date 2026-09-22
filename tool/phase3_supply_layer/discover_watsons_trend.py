# -*- coding: utf-8 -*-
"""
Discover Watsons — pilot agent หมวด "อีคอมเมิร์ซไทย" สำหรับขยาย Step 1 เป็นหลายหมวดข้อมูล
(ดู Detail/05 งานที่ยังไม่ได้ทำ/ขยาย Step 1 เป็นหลายหมวดข้อมูล.md)

ต่างจาก Pantip/Reddit/YouTube ตรงที่นี่คือสัญญาณฝั่ง "อุปทาน/การตลาดจริง" (มีสินค้าอะไรขายอยู่ ราคา
เท่าไหร่ โปรอะไร รีวิวกี่รอบ) ไม่ใช่การพูดคุยของผู้บริโภค (demand-side) เหมือน 3 หมวดก่อนหน้า

=== เส้นทางที่ทดสอบมาก่อนจะได้เวอร์ชันนี้ (2026-08-27) ===
1. Shopee TH (plain Playwright) - หน้าว่างเปล่า (LEN 0) โหลดไม่ขึ้นเลย
2. Shopee TH (cloakbrowser) - ยังว่างอยู่ดี (LEN 20 มีแค่ "Skip to main content") - เนื้อหาจริงถูกกันไว้
   หนักกว่า Reddit/Watsons มาก ไม่ลองต่อ (Shopee ขึ้นชื่อเรื่อง anti-bot หนักที่สุดในกลุ่มที่ทดสอบมา)
3. Watsons (cloakbrowser, URL pattern เดียวกับ data_prep/scrape_watsons.py ที่ใช้งานได้จริงอยู่แล้ว) -
   ✅ ได้ผลจริง เห็นรายการสินค้าเต็ม (ชื่อ/แบรนด์/ราคา/โปรโมชัน/จำนวนรีวิว) และเจอของขวัญที่ไม่คาดคิด:
   Watsons มี filter facet ชื่อ "Latest Trends" ที่ระบุ K-Beauty / J-Beauty / Clean Beauty เอง -
   เป็น trend taxonomy ที่ผู้ค้าปลีกจัดหมวดให้เองเลย ไม่ต้องให้ LLM เดา

=== การออกแบบตอนนี้ ===
ใช้ cloakbrowser เหมือน data_prep/scrape_watsons.py (Watsons มี Akamai bot detection แบบเดียวกับ
Reddit ไม่ใช่ Pantip) เปิดหน้าค้นหา → ดึงข้อความดิบเฉพาะช่วง "filter facets + รายการสินค้า" (ตัดแถบเมนู
บนสุดกับ footer ทิ้งด้วย regex ขอบเขตคงที่) → ให้ LLM อ่านแล้วสรุปเป็นสัญญาณ

หมายเหตุเรื่องตัวเลข: หน้าค้นหาโชว์ "NNN Search Results for" ซึ่งเป็นยอดรวมทุก SKU ที่ Watsons จับคู่คำ
(อาจหลวม จับคำบางส่วนได้สินค้าที่ไม่เกี่ยวจริงปนมา) - แยกออกมาเป็น reported_total เหมือน Pantip กันความ
สับสน แต่ต่างจาก Pantip ตรงที่ตัวเลขนี้เป็นสัญญาณอุปทานที่มีความหมายจริง (มีสินค้าตอบโจทย์ในตลาดกี่ตัว -
วิธีคิดแบบเดียวกับ analysis/market_gap_check.py) ไม่ใช่ยอดที่ไม่มีความหมายเหมือนพบกระทู้ที่ Pantip อ้าง

สถานะ: ทดสอบ mechanism (cloakbrowser เข้าถึงได้จริง เห็นสินค้า+facet เต็ม) แล้ว แต่ยังไม่เคยรัน
end-to-end เต็มรูป (สร้างคำค้น → ค้นจริง → ให้ LLM สรุป) ควรรันดูผลจริงก่อนเชื่อว่า output มีคุณภาพดีพอ
ยังทดสอบแค่ฝั่งไทย (Watsons) - ฝั่งต่างประเทศยังไม่ได้เลือกแพลตฟอร์ม/ทดสอบเลย
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
N_QUERIES = 4          # จำนวนคำค้นที่ให้ LLM แตกออกมา (เท่ากับหมวดอื่น)
PAGE_TIMEOUT_MS = 45000
WAIT_AFTER_LOAD_MS = 5000
SESSION_DIR = PROJECT_ROOT / "watsons" / "browser_session"  # ใช้โฟลเดอร์เดียวกับ scrape_watsons.py ได้

# --- 1. แตกคำค้นภาษาไทยจาก topic (LLM, สำหรับพิมพ์ค้นในเว็บ Watsons จริง) ---
SYSTEM_PROMPT_QUERIES = """คุณคือนักวิจัยตลาดที่เชี่ยวชาญพฤติกรรมผู้บริโภคไทยบนเว็บอีคอมเมิร์ซ (Watsons)
หน้าที่ของคุณคือสร้างคำค้นหาภาษาไทยที่คนไทยจริงๆ จะพิมพ์ค้นหาสินค้าบน Watsons เวลาช้อปปิ้งเรื่องนี้

กฎสำคัญ:
- ต้องเป็นคำค้นแบบที่คนไทยพิมพ์ค้นหาสินค้าจริง ไม่ใช่การแปลคำภาษาอังกฤษตรงตัว
- สั้น กระชับ 1-4 คำ แบบที่คนพิมพ์ในกล่องค้นหาอีคอมเมิร์ซจริง (ไม่ใช่ประโยคเต็ม)
- ครอบคลุมมุมต่างกัน เช่น ประเภทสินค้าทั่วไป, ปัญหาผิว/ความต้องการเฉพาะ, คุณสมบัติที่กำลังนิยม

ตอบเป็น JSON เท่านั้น: {"queries": ["คำค้น 1", "คำค้น 2", ...]}
"""


def generate_thai_queries(topic, n):
    try:
        response = tf.client.chat.completions.create(
            model=tf.MODEL_NAME_META,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_QUERIES},
                {"role": "user", "content": f"หัวข้อ: '{topic}'\nสร้างคำค้น {n} คำ"},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        parsed = safe_json_parse(response.choices[0].message.content)
        return parsed.get("queries", []) if parsed else []
    except Exception as e:
        print(f"⚠️ Error generating queries: {e}")
        return []


# --- 2. ค้น Watsons ด้วย cloakbrowser (Akamai bot detection - เหมือน scrape_watsons.py) ---
async def search_watsons_async(queries):
    """คืนค่า list ของ dict {"query": ..., "raw_text": ..., "reported_total": int|None}"""
    results = []
    context = await launch_persistent_context_async(str(SESSION_DIR), headless=True)
    page = context.pages[0] if context.pages else await context.new_page()
    for q in queries:
        print(f"=== ค้นหา: '{q}' บน Watsons ===")
        url = "https://www.watsons.co.th/en/search?text=" + urllib.parse.quote(q, safe=":")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
            await page.wait_for_timeout(WAIT_AFTER_LOAD_MS)
            raw_text = await page.inner_text("body")

            # ตัดแถบเมนู/แบนเนอร์บนสุดกับ footer ทิ้ง เหลือแค่ filter facets + รายการสินค้าจริง
            start_m = re.search(r"\n[\d,]+ Search Results for", raw_text)
            end_m = re.search(r"\nView by \d+ items per page", raw_text)
            clean_text = raw_text[start_m.start():end_m.start()] if (start_m and end_m) else raw_text

            m = re.search(r"([\d,]+) Search Results for", clean_text)
            reported_total = int(m.group(1).replace(",", "")) if m else None

            print(f"    เจอข้อความ {len(clean_text)} ตัวอักษร "
                  f"(Watsons รายงานว่าจับคู่ได้ทั้งหมด {reported_total if reported_total is not None else '?'} รายการ - อาจจับคำหลวม)")
            results.append({"query": q, "raw_text": clean_text, "reported_total": reported_total})
        except Exception as e:
            print(f"    ⚠️ ค้นหา '{q}' ล้มเหลว: {e}")
    await context.close()
    return results


def search_watsons(queries):
    return asyncio.run(search_watsons_async(queries))


# --- 3. สรุปผลทั้งหมดเป็นสัญญาณเทรนด์ ---
SYSTEM_PROMPT_SUMMARY = """คุณคือนักวิเคราะห์เทรนด์ตลาดที่อ่านหน้าผลค้นหาของ Watsons (ผู้ค้าปลีกสุขภาพ/
ความงามรายใหญ่ในไทย) จริง - ข้อความดิบมีทั้ง filter facet (หมวดหมู่/แบรนด์/ราคา/โปรโมชัน/ขนาด/
"Latest Trends" ที่ Watsons จัดหมวดเทรนด์เองเช่น K-Beauty, J-Beauty, Clean Beauty) และรายการสินค้าจริง
(ชื่อ/แบรนด์/ราคา/โปร/จำนวนรีวิวในวงเล็บ) ปนกัน แล้วสรุปสัญญาณตลาดที่พบ

นี่คือสัญญาณฝั่ง "อุปทาน/การตลาดจริง" (มีของขายจริง ราคาเท่าไหร่ ผู้ขายวางตำแหน่งสินค้ายังไง) ไม่ใช่การ
พูดคุยของผู้บริโภคเหมือนแหล่งอื่น - เน้นวิเคราะห์แบรนด์/คุณสมบัติที่ถูกเน้นขาย ระดับราคา และหมวดเทรนด์ที่
Watsons ติดป้ายเอง

กฎสำคัญเรื่องตัวเลข: แต่ละคำค้นมี "จำนวนสินค้าที่อ่านจริง" (นับจากรายการสินค้าที่แสดงจริงในหน้าแรก) กับ
"ยอดรวมที่ Watsons รายงาน" (อาจจับคำหลวม มีสินค้าที่ไม่เกี่ยวจริงปนมาได้) กำกับไว้ - ใช้ยอดรวมได้เป็น
สัญญาณอุปทานคร่าวๆ (แตกต่างจาก Pantip ตรงที่นี่คือแคตตาล็อกจริงนับได้ ไม่ใช่ยอดกระทู้ที่ไม่ผ่านการกรอง)
แต่ต้องระบุด้วยว่าเป็นยอดจับคู่คำแบบหลวม ไม่ใช่ยอดที่ยืนยันว่าตรงประเด็น 100%

ตอบเป็น JSON: {"needs_and_pain_points": ["...", ...], "trend_signals": ["...", ...],
"notable_products": [{"title": "...", "why_relevant": "..."}]}
ทุกข้อสรุปต้องอ้างอิงเนื้อหาจริงที่ให้มา ห้ามเดาเอง ถ้าข้อมูลไม่พอให้สรุปสั้นๆ ตามจริง อย่าสรุปซ้ำกัน
ระหว่างคำค้นต่างๆ ถ้าเป็นประเด็นเดียวกัน
"""


def summarize_findings(topic, search_results):
    real_results = [r for r in search_results if r.get("raw_text")]
    if not real_results:
        return None
    blocks = []
    for r in real_results:
        reported = r.get("reported_total")
        reported_line = f" | ยอดรวมที่ Watsons รายงาน (จับคำหลวม): {reported}" if reported is not None else ""
        blocks.append(
            f"--- ผลค้นหาคำว่า '{r['query']}'{reported_line} ---\n"
            f"{r['raw_text'][:6000]}"
        )
    combined_text = "\n\n".join(blocks)
    user_prompt = f"หัวข้อที่กำลังวิจัย: '{topic}'\n\n{combined_text}"
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
    queries = generate_thai_queries(TOPIC, N_QUERIES)
    print(f"คำค้นที่สร้าง: {queries}")

    if not queries:
        print("❌ สร้างคำค้นไม่สำเร็จ หยุดทำงาน")
        raise SystemExit(1)

    search_results = search_watsons(queries)
    summary = summarize_findings(TOPIC, search_results)

    out_path = OUTPUTS / "watsons_trend_discovery_pilot.json"
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
