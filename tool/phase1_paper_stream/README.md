# Phase 1 — แยกสาย Paper (นำร่อง)

**สถานะ:** ✅ **เสร็จแล้ว + ผ่านเกณฑ์** (2026-08-28)

## ไฟล์ในโฟลเดอร์นี้
| ไฟล์ | คืออะไร |
|---|---|
| `paper_stream.py` | ดึงเนื้อหา (ScienceDaily + MDPI) → scrape → สังเคราะห์รายงาน → สกัด triplet → Louvain clustering → ตั้งชื่อเทรนด์ |
| `compare_to_baseline.py` | เทียบคลัสเตอร์ที่ได้กับ baseline (run เต็ม pipeline เดิม) ด้วย keyword overlap แบบ deterministic |

## ทำไมเลือกสายนี้ก่อน
**ถูกที่สุด** — แหล่งมีอยู่แล้วใน `config/rss_feeds.json` กลุ่ม `Scientific_Papers` ไม่ต้องหาแหล่งใหม่ ไม่ต้องขอ API key

## ผลลัพธ์

รัน pipeline เต็ม: ScienceDaily RSS (15 รายการ, พบว่าเนื้อหาไม่ตรงหัวข้อจริง — ดูด้านล่าง) + MDPI ผ่าน Google News (locale อังกฤษ, 750-870 รายการต่อรอบ) → เลือก 10 บทความ → scrape ด้วย Apify (MDPI บล็อก 403 ทุกลิงก์) → ตัดความยาว → สังเคราะห์รายงาน → สกัด **135 triplets** → Louvain **38 กลุ่ม** → ตั้งชื่อเป็น **5 เทรนด์**:

1. Natural Oil-Control Anhydrous Lotion Bars
2. Evidence-Based Barrier-Friendly Cleansing
3. Thai Botanical Antioxidant Beauty
4. Waterless Beauty and Solid Cleansing
5. Biodegradable Bioactive Hydrogel Beauty

## เทียบกับ baseline

**เกณฑ์:** คลัสเตอร์จากสาย Paper ต่างจากคลัสเตอร์เดิมจริงไหม (baseline = ผลรัน pipeline เต็มแบบเดิม
ของหัวข้อเดียวกัน `memory/analysis_logs/trend_result_..._20260818_132149/`)

**ผล (`compare_to_baseline.py`, word-level Jaccard, ฟรี ไม่ใช้ LLM):**
```
Overlap เฉลี่ย: 0.066 | Overlap สูงสุด: 0.103
✅ ต่างจาก baseline ชัดเจน (overlap ต่ำมากทุกคู่) - สาย Paper ให้มุมที่ baseline ไม่เห็น
```

**✅ ผ่านเกณฑ์ที่ตั้งไว้ชัดเจน** — สาย Paper เน้นสูตรไร้น้ำ/anhydrous, ส่วนผสมทางเทคนิคเจาะจง
(starch rheology modifier, sodium cocoyl isethionate, hydrogel ย่อยสลายได้) ต่างจาก baseline ที่เน้น
ภาษาการตลาดแบบผู้บริโภค → **สมมติฐานหลักของ Workflow v2 ถูกต้อง เดินหน้า Phase 2 ได้**

## บั๊กที่เจอ+แก้ระหว่างทาง (4 จุด — ดูรายละเอียดเต็มใน Backlog ข้อ 13-15)

| # | บั๊ก | แก้ที่ |
|---|---|---|
| 1 | `select_top_10_news_with_llm` กรองคำหลัก case-sensitive ผิด → pool > 30 เหลือ 0 เสมอ | `common/bootstrap.py` → `select_top_news()` |
| 2 | `scrape_article_content` Apify fallback พัง (`'Run' object is not subscriptable`) — apify-client รุ่นใหม่เปลี่ยนเป็น pydantic model | `common/bootstrap.py` → `scrape_article()` |
| 3 | เนื้อหาเปเปอร์เต็มยาวเกิน prompt limit (10 บทความ = 1.39M ตัวอักษร) | ตัดที่ `CONTENT_CHAR_LIMIT = 8000` ต่อบทความใน `paper_stream.py` |
| 4 | `CACHE_FILE = "memory/scraped_cache.json"` เป็น relative path — เขียนผิดที่ถ้า cwd ไม่ใช่ root | ยังไม่ได้แก้ (แค่รู้ว่าต้องรันจาก root หรือ cwd เดียวกันเสมอ) |

**ข้อค้นพบสำคัญที่ไม่ใช่บั๊ก แต่กระทบการออกแบบ:** Google News locale `hl=th&gl=TH` (hardcode ทุกจุดใน
pipeline หลัก) **บล็อก MDPI จนเหลือ 0 ผลลัพธ์เสมอ** — เปลี่ยนเป็น `hl=en&gl=US` ด้วยคำค้นเดียวกันเป๊ะ
ได้ 100 ผลลัพธ์ตรงประเด็นทันที `paper_stream.py` แก้แล้วโดยใช้ locale อังกฤษเฉพาะสายนี้ (วรรณกรรม
วิชาการเป็นสากลโดยธรรมชาติ) — นี่คือหลักฐานจับต้องได้ของคำถามค้างข้อ 1 ใน `workspace/README.md`

**ข้อสังเกตเรื่อง noise:** ScienceDaily RSS ("Cosmetics News" ตามชื่อ feed) คืนข่าวสุขภาพทั่วไปที่ไม่
เกี่ยวกับเครื่องสำอางเลย (มะเร็ง การนอน สายตา) — เนื้อหาจริงไม่ตรงกับชื่อ feed ต้องพึ่ง MDPI เป็นหลัก
และคำค้นที่มีคำว่า "Thailand" ตรงๆ ดึงเปเปอร์ ethnobotany/พืชท้องถิ่นที่ไม่เกี่ยวกับ body wash เข้ามาปน
(~4/10 บทความในรอบแรก) — ยืนยันรูปแบบ "เทรนด์...+ปี/ประเทศ" ที่มักได้ noise ซึ่งเจอมาแล้วทั้งใน
Pantip/YouTube/Reddit

## ✅ เติมขั้นแตกคีย์เวิร์ดแล้ว (2026-08-28)

เพิ่ม `tf.extract_strategic_keywords(df_trends)` ต่อจากการตั้งชื่อคลัสเตอร์ — ปิดช่องว่างที่ค้างจากรอบแรก

**OpenRouter credit หมดระหว่างทาง** (เหลือ ~32-36 token) — สลับไปใช้ Typhoon แทนผ่าน `use_typhoon()`
context manager ใหม่ใน `common/bootstrap.py` (สลับ `tf.client`/`tf.MODEL_NAME_META` ชั่วคราว) รันสำเร็จ
ครบ 5 เทรนด์

**⚠️ พบข้อจำกัด:** `extract_strategic_keywords` ไม่รับพารามิเตอร์หัวข้อโจทย์เลย เห็นแค่
ingredients/benefits ต่อคลัสเตอร์ → คีย์เวิร์ดที่ได้เอนไปทางสกินแคร์/หน้าทั่วไป (เช่น "matte face bar",
"hydrogel mask sheet") แทนที่จะเป็นครีมอาบน้ำโดยเฉพาะ — ดู Backlog ข้อ 17 ก่อนเอาไปรวมกับสายอื่นใน
Phase 2

## ผลเต็ม
- [`../outputs/phase1_paper_stream_result.json`](../outputs/phase1_paper_stream_result.json)
- [`../outputs/phase1_vs_baseline_comparison.json`](../outputs/phase1_vs_baseline_comparison.json)
- คัดลอกไว้ที่ `Detail/_data/` ด้วยแล้ว
