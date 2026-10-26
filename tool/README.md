# tool/

โค้ดของไปป์ไลน์ทั้งหมด — วิธีติดตั้ง การใช้งาน และสถาปัตยกรรมอยู่ใน [README หลัก](../README.md)

| โฟลเดอร์ | มีอะไร |
|---|---|
| `common/` | `bootstrap.py` (path, `.env`, `use_bedrock()`, ฟังก์ชันร่วม) และส่วนที่ใช้จริงของระบบรุ่นแรก (`trend_final_subset.py`, `trend_final_v2_subset.py`) |
| `phase1_paper_stream/` | ①-⑤ สาย Paper (+ `scrapers/` MDPI, PubMed Central) |
| `phase2_three_streams/` | ①-⑤ สาย Social / News, ⑦ พยากรณ์, ⑧-⑨ สรุประดับหมวด, ⑥ Rank Score, ⑩ รอบค้นพบเพิ่ม |
| `phase3_supply_layer/` | ⑪ จุดเด่น + Top N, ⑫ จับคู่สินค้า, ⑬ ค้นหาแบรนด์ |
| `phase5_report/` | ⑭-⑮ STEPIC → Master Report |
| `phase6_pdf_report/` | ⑯ รายงานเทรนด์ PDF และ ⑰ รายงานแบรนด์ x เทรนด์ PDF - อังกฤษ + ไทย (Jinja2 → Playwright Chromium) |
| `phase7_market_report/` | ⑲ รายงานภาพรวม/ส่วนแบ่งตลาด PDF - อังกฤษ + ไทย (Euromonitor + อย. + ข่าว) |
| `phase8_llm_export/` | ⑳ ส่งออกผลของรอบให้ LLM ใช้ต่อ (brief ต่อลูกค้า + ตารางรวมลูกค้า/เทรนด์ CSV + SQLite) - อ่านไฟล์ของรอบอย่างเดียว ไม่เรียก API |
| `product/` | โค้ดสร้างแคตตาล็อกสินค้า (`build_konvy_catalog.py`, `build_eve_catalog.py`, `build_market_catalog.py`), จัดหมวด (`euromonitor_mapping.py`, `classify_products_llm.py`) และ `product_category.csv` (taxonomy 4 ระดับของ Euromonitor) ; **ไฟล์ข้อมูลใหญ่ไม่อยู่ใน repo** — ดู [product/README.md](product/README.md) |
| `tests/` | เทสต์ทั้งหมดของโปรเจกต์ (pytest) — `python -m pytest tool/tests -q` จากโฟลเดอร์บนสุด ไม่เรียก API ; เทสที่ต้องใช้ไฟล์ข้อมูลใน `product/` ข้ามเองถ้าไม่มีไฟล์ |
| `phase4_discovery_round/` | มีแค่ README (โค้ดของ ⑩ อยู่ใน `phase2_three_streams/`) |

ชื่อโฟลเดอร์ `phase0-5` คือลำดับที่เขียนโค้ด ไม่ตรงกับเลขขั้น ①-⑮ — ลำดับที่รันจริงดูตารางใน [README หลัก](../README.md#ลำดับที่รันจริง)
