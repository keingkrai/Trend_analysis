# -*- coding: utf-8 -*-
"""
Discover Pantip — pilot agent หมวด "ชุมชนไทย" สำหรับขยาย Step 1 เป็นหลายหมวดข้อมูล
(ดู Detail/05 งานที่ยังไม่ได้ทำ/ขยาย Step 1 เป็นหลายหมวดข้อมูล.md)

หมวดนี้ถูกเลือกเป็น pilot ตัวแรกเพราะ:
- Pantip เป็นเว็บสาธารณะ ไม่มี API gate เหมือน Instagram/TikTok
- เป็นแกน "ไทย" ของฝั่งชุมชนอยู่แล้วโดยธรรมชาติ ไม่ต้องแยกคู่ภาษาเอง

=== เส้นทางที่ทดสอบมาก่อนจะได้เวอร์ชันนี้ (2026-08-20) ===
1. ลองใช้ SerpAPI engine="google" ค้น site:pantip.com ก่อน - ใช้งานได้แต่เจ้าของงานใช้ SerpAPI
   แผนฟรี (โควตาจำกัด แชร์กับ Google Trends ที่ใช้อยู่แล้ว) จึงหาทางอื่นที่ไม่กินโควตานี้แทน
2. ทดสอบ requests.get() ตรงๆ (ไม่มี browser) - ได้ HTTP 200 และเจอคำค้นในหน้า HTML จริง แต่พิสูจน์แล้ว
   ว่าเจอแค่ในส่วนหัว "พบ N กระทู้" เท่านั้น - เนื้อหากระทู้จริงโหลดทีหลังผ่าน JavaScript (Pantip เป็น
   Next.js app) requests.get() เฉยๆ จึงไม่พอ
3. ลองดักจับ response ของ POST /api/search-service/search/query ตรงๆ ผ่าน Playwright response
   listener - ได้ {"success":true,"data":[]} ว่างเปล่า ทั้งที่หน้าเว็บ render เนื้อหาเต็มจริง (ยังไม่ทราบ
   สาเหตุแน่ชัด อาจต้องมี header/timing เพิ่มเติมที่ยังไม่รู้) - เลิกพึ่ง API นี้ตรงๆ
4. ทดสอบอ่านจาก DOM ที่ render จริงด้วย plain Playwright (ไม่ใช่ cloakbrowser) - ได้ผลจริง อ่านเนื้อหา
   กระทู้ได้ครบ (page.inner_text("body")) และดึงลิงก์กระทู้จริงได้ (a[href*="pantip.com/topic"])
   ยืนยันว่า Pantip ไม่มี bot detection แบบ Akamai เหมือน Watsons (ดู scrape_watsons.py ที่ต้องใช้
   cloakbrowser เพราะ Watsons บล็อก Playwright ธรรมดา) - plain Playwright พอสำหรับ Pantip

=== การออกแบบตอนนี้ ===
ใช้ plain Playwright render หน้า → ดึงข้อความดิบ (inner_text) + ลิงก์กระทู้จริง → ให้ LLM อ่านข้อความ
ดิบที่ยังไม่มีโครงสร้างชัดเจน (หัวข้อ/ผู้เขียน/วันที่/เนื้อหา ปนกันเป็นข้อความต่อเนื่อง) แล้วแยกเป็น
สัญญาณเทรนด์ที่มีโครงสร้าง - เลือกวิธีนี้แทนการเขียน CSS selector เจาะจงทุกฟิลด์ เพราะ class name ของ
Pantip อาจเปลี่ยนได้ทุกเมื่อ (ทดสอบแล้วว่า selector อย่าง "pt-content-list-suggest > div" ไม่ตรงกับ
โครงจริง) ในขณะที่ inner_text (ข้อความล้วน) มีโอกาสเปลี่ยนโครงสร้างน้อยกว่า และ LLM ถนัดแยกข้อความ
ปนกันแบบนี้อยู่แล้ว (ใช้วิธีเดียวกับที่ trend_final.py ใช้แยกข้อมูลจากข่าวที่ไม่มีโครงสร้างชัดเจน)

สถานะ: ทดสอบ mechanism (Playwright เข้าถึงได้จริง) แล้ว แต่ยังไม่เคยรัน end-to-end เต็มรูป
(สร้างคำค้น → ค้นจริง → ให้ LLM สรุป) ควรรันดูผลจริงก่อนเชื่อว่า output มีคุณภาพดีพอ
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

# หายไปตอนย้ายไฟล์เข้า workspace/ (ของเดิมใน analysis/discover_pantip.py มีอยู่) - ไม่มีบรรทัดนี้
# จะพัง NameError ทันทีที่เรียก search_pantip_async() เพราะโค้ดข้างล่างใช้ async_playwright() ตรงๆ
from playwright.async_api import async_playwright  # noqa: E402

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# --- ⚙️ ตั้งค่าก่อนรัน ---
TOPIC = "Trend Body Wash Thailand 2030"
N_QUERIES = 4          # จำนวนคำค้นที่ให้ LLM แตกออกมา (เท่ากับ generate_rss_queries_with_llm เดิม)
PAGE_TIMEOUT_MS = 30000
WAIT_AFTER_LOAD_MS = 3000  # กันเผื่อเนื้อหาโหลดช้ากว่า networkidle เล็กน้อย

# --- 1. แตกคำค้นภาษาไทยจาก topic (LLM, ไม่แปลจากอังกฤษตรงตัว) ---
SYSTEM_PROMPT_QUERIES = """คุณคือนักวิจัยตลาดที่เชี่ยวชาญพฤติกรรมผู้บริโภคไทยบนเว็บบอร์ด Pantip
หน้าที่ของคุณคือสร้างคำค้นหาภาษาไทยที่คนไทยจริงๆ จะพิมพ์ค้นบน Pantip เวลาคุยเรื่องนี้

กฎสำคัญ:
- ต้องเป็นคำค้นแบบที่คนไทยพิมพ์ค้นจริง ไม่ใช่การแปลคำภาษาอังกฤษตรงตัว
- สั้น กระชับ 2-5 คำ แบบที่คนพิมพ์ในกล่องค้นหาจริง (ไม่ใช่ประโยคเต็ม)
- ครอบคลุมมุมต่างกัน เช่น รีวิวสินค้า, ปัญหาผิว/ผม, ถามความเห็น, เปรียบเทียบยี่ห้อ

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


# --- 2. ค้น Pantip ด้วย plain Playwright (ไม่ต้อง cloakbrowser - ดู docstring ด้านบน) ---
async def search_pantip_async(queries):
    """คืนค่า list ของ dict {"query": ..., "raw_text": ..., "topic_links": [...], "reported_total": int|None}

    หมายเหตุ (2026-08-20 หลัง audit รอบแรก): Pantip แสดงหัวบรรทัด "พบ N กระทู้" ซึ่งเป็นยอดรวม
    ทั้งเว็บแบบไม่กรองความเกี่ยวข้อง - รอบแรกปล่อยให้ปนอยู่ในข้อความดิบ ทำให้ LLM หยิบมาเทียบราวกับ
    เป็นสัญญาณความถี่จริง (เช่น "คำค้น A พบ 31 กระทู้ มากกว่าคำค้น B ที่ 15 กระทู้") ทั้งที่เราอ่านจริง
    แค่ ~10 กระทู้/คำค้นเท่านั้น (จำกัดด้วย pagination หน้าแรก) - แก้โดยดึงตัวเลขนี้ออกมาเป็น field
    แยกต่างหาก (reported_total) แล้วตัดประโยคนี้ออกจาก raw_text ที่จะส่งให้ LLM วิเคราะห์ กันปนกัน
    """
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        for q in queries:
            print(f"=== ค้นหา: '{q}' บน Pantip ===")
            url = "https://pantip.com/search?q=" + urllib.parse.quote(q)
            try:
                await page.goto(url, wait_until="networkidle", timeout=PAGE_TIMEOUT_MS)
                await page.wait_for_timeout(WAIT_AFTER_LOAD_MS)
                raw_text = await page.inner_text("body")
                links = await page.eval_on_selector_all(
                    "a[href*='pantip.com/topic']", "els => els.map(e => e.href)"
                )
                # ตัดซ้ำ + ตัด anchor เฉพาะคอมเมนต์ทิ้ง เหลือแค่ topic id หลัก
                unique_links = sorted(set(l.split("/comment")[0] for l in links))

                # แยกยอดรวมที่ Pantip อ้าง ("พบ 9,248 กระทู้") ออกมาเป็น metadata และตัดออกจากข้อความดิบ
                m = re.search(r"พบ\s*([\d,]+)\s*กระทู้", raw_text)
                reported_total = int(m.group(1).replace(",", "")) if m else None
                clean_text = re.sub(r"ผลการค้นหา\s*\"[^\"]*\"\s*\(พบ\s*[\d,]+\s*กระทู้\)", "", raw_text)

                print(f"    เจอข้อความ {len(clean_text)} ตัวอักษร, {len(unique_links)} ลิงก์กระทู้ "
                      f"(Pantip อ้างว่ามีทั้งหมด {reported_total if reported_total is not None else '?'} กระทู้ - ยังไม่กรอง)")
                results.append({
                    "query": q, "raw_text": clean_text, "topic_links": unique_links,
                    "reported_total": reported_total,
                })
            except Exception as e:
                print(f"    ⚠️ ค้นหา '{q}' ล้มเหลว: {e}")
        await browser.close()
    return results


def search_pantip(queries):
    return asyncio.run(search_pantip_async(queries))


def clean_pantip_query(query):
    """🆕 (2026-09-15) ตัดคำว่า pantip/พันทิป ออกจากคำค้น - LLM ชอบเติมคำนี้ (เช่น "ผมร่วง ศีรษะล้าน pantip")
    แต่เราค้นในเว็บ Pantip อยู่แล้ว คำนี้ทำให้ค้นไม่เจอกระทู้เลย (เจอจริง 2 จาก 4 คำค้น รอบ 2026-09-15)"""
    return " ".join(re.sub(r"pantip|พันทิป", " ", query, flags=re.IGNORECASE).split())


def extract_search_results_text(raw_text):
    """🆕 (2026-09-15) เหลือเฉพาะรายการกระทู้ ตัดเมนูเว็บด้านบน (ถึง "รูปแบบการแสดง:") และตัวกรองห้อง/ลิงก์
    ท้ายหน้า (ตั้งแต่ "tune") ออก - เดิมส่งทั้งหน้าเข้ารายงาน มี checkbox ชื่อห้องเป็นสิบบรรทัดปน
    ถ้าหาตัวคั่นไม่เจอ (เว็บเปลี่ยนหน้าตา) คืนข้อความเดิมทั้งหมด ไม่ตัดทิ้งเนื้อหา"""
    header = raw_text.find("รูปแบบการแสดง:")
    start = raw_text.find("\n", header) + 1 if header >= 0 else 0
    end = raw_text.find("\ntune\n", start)
    return raw_text[start:end if end >= 0 else len(raw_text)].strip()


# --- 3. สรุปผลทั้งหมดเป็นสัญญาณเทรนด์ (โครงคล้าย step1_final_trend_report.md) ---
SYSTEM_PROMPT_SUMMARY = """คุณคือนักวิเคราะห์เทรนด์ตลาดที่อ่านหน้าผลค้นหา Pantip จริง (ข้อความดิบที่ยัง
ไม่แยกโครงสร้าง มีทั้งหัวข้อกระทู้/ชื่อผู้เขียน/วันที่/เนื้อหา/คอมเมนต์ปนกัน) แล้วสรุปสัญญาณที่พบ

กฎสำคัญเรื่องตัวเลข (อ่านก่อนตอบ):
- แต่ละคำค้นจะมี "จำนวนกระทู้ที่อ่านจริง" กำกับไว้ (ปกติ ~10 กระทู้ต่อคำค้น จำกัดด้วยหน้าแรกของผลค้นหา)
  ใช้แค่ตัวเลขนี้เท่านั้นเป็นฐานของการสรุป/เปรียบเทียบความถี่ระหว่างคำค้น
- ถ้ามี "ยอดรวมที่ Pantip อ้าง" กำกับมาด้วย (ยอดทั้งเว็บ ไม่ผ่านการกรองความเกี่ยวข้อง) **ห้ามใช้ตัวเลขนี้
  เปรียบเทียบความถี่หรืออ้างเป็นสัญญาณเทรนด์เด็ดขาด** เพราะไม่ได้สะท้อนว่ากระทู้เหล่านั้นเกี่ยวข้องจริง
  หรือเราได้อ่านเนื้อหาจริงเลย ถ้าจะพูดถึงต้องระบุชัดว่า "Pantip รายงานยอดรวมทั้งเว็บ (ไม่ผ่านการกรอง)"
  แยกจากการวิเคราะห์เนื้อหาจริงเสมอ

ตอบเป็น JSON: {"needs_and_pain_points": ["...", ...], "trend_signals": ["...", ...],
"notable_threads": [{"title": "...", "why_relevant": "..."}]}
ทุกข้อสรุปต้องอ้างอิงเนื้อหาจริงที่ให้มา ห้ามเดาเอง ถ้าข้อมูลไม่พอให้สรุปสั้นๆ ตามจริง อย่าสรุปซ้ำกัน
ระหว่างคำค้นต่างๆ ถ้าเป็นประเด็นเดียวกัน
"""


def summarize_findings(topic, search_results):
    real_results = [r for r in search_results if r.get("raw_text")]
    if not real_results:
        return None
    blocks = []
    for r in real_results:
        n_read = len(r.get("topic_links", []))
        reported = r.get("reported_total")
        reported_line = f" | ยอดรวมที่ Pantip อ้าง (ไม่ผ่านการกรอง ห้ามใช้เทียบความถี่): {reported}" if reported is not None else ""
        blocks.append(
            f"--- ผลค้นหาคำว่า '{r['query']}' | จำนวนกระทู้ที่อ่านจริง: {n_read}{reported_line} ---\n"
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

    search_results = search_pantip(queries)
    summary = summarize_findings(TOPIC, search_results)

    out_path = OUTPUTS / "pantip_discovery_pilot.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "topic": TOPIC,
            "queries": queries,
            "search_results": search_results,
            "summary": summary,
        }, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(json.dumps(summary, ensure_ascii=False, indent=2) if summary else "(ไม่มีผลสรุป - อาจไม่เจอกระทู้เลย)")
    print("=" * 80)
    print(f"\nSaved -> {out_path}")
