# tool/

โค้ดของไปป์ไลน์ทั้งหมด — วิธีติดตั้ง การใช้งาน และสถาปัตยกรรมอยู่ใน [README หลัก](../README.md)

| โฟลเดอร์ | มีอะไร |
|---|---|
| `common/` | `bootstrap.py` (path, `.env`, `use_bedrock()`, ฟังก์ชันร่วม), `streams.py` (รายชื่อสาย ①-⑤ ที่เดียว), `evidence_gate.py` (ตรวจข้อความที่ AI เขียนกับคำค้นจริง), `match_quality.py` (ธง "ไม่มีสินค้าที่ใกล้พอ" + ฐานข้อความจับคู่), `trend_analysis.py`, `horizons.py`, `serpapi_keys.py` และส่วนที่ใช้จริงของระบบรุ่นแรก (`trend_final_subset.py`, `trend_final_v2_subset.py`) |
| `phase9_search_stream/` | **①-⑤ สาย Search (Google Trends คำค้นกำลังขึ้นรายหมวด)** — สายปัจจุบัน ใช้แทน 3 สายเดิมตั้งแต่ 2026-10-27, ดู [README](phase9_search_stream/README.md) |
| `phase1_paper_stream/` | ①-⑤ สาย Paper (+ `scrapers/` MDPI, PubMed Central) — สายเดิม ไม่รันแล้ว (เก็บไว้ให้รอบเก่า) |
| `phase2_three_streams/` | ⑦ พยากรณ์, ⑧-⑨ สรุประดับหมวด, ⑥ Rank Score (คะแนนการเติบโต), ⑩ รอบค้นพบเพิ่ม และสาย Social / News เดิม (ไม่รันแล้ว) |
| `phase3_supply_layer/` | ⑪ จุดเด่น + Top N (`highlight_evidence.py` ตรวจหลักฐานของสาย Search), ⑫ จับคู่สินค้า (`match_supply.py`, `trend_category.py`, `l2_market_map.py`), ⑬ ค้นหาแบรนด์ |
| `phase5_report/` | ⑭-⑮ STEPIC → Master Report (`stepic_evidence.py` สำหรับสาย Search) |
| `phase6_pdf_report/` | ⑯ รายงานเทรนด์ PDF (รวมส่วนเจาะรายหมวดของ Google: `category_dive.py`, `dive_text.py`) และ ⑰ รายงานแบรนด์ x เทรนด์ PDF - อังกฤษ + ไทย (Jinja2 → Playwright Chromium) |
| `phase7_market_report/` | ⑲ รายงานภาพรวม/ส่วนแบ่งตลาด PDF - อังกฤษ + ไทย (Euromonitor + อย. + ข่าว) |
| `phase8_llm_export/` | ⑳ ส่งออกผลของรอบให้ LLM ใช้ต่อ (brief ต่อลูกค้า + ตารางรวมลูกค้า/เทรนด์ CSV + SQLite) - อ่านไฟล์ของรอบอย่างเดียว ไม่เรียก API |
| `product/` | โค้ดสร้างแคตตาล็อกสินค้า (`build_konvy_catalog.py`, `build_eve_catalog.py`, `build_market_catalog.py`), จัดหมวด (`euromonitor_mapping.py`, `classify_products_llm.py`) และ `product_category.csv` (taxonomy 4 ระดับของ Euromonitor) ; **ไฟล์ข้อมูลใหญ่ไม่อยู่ใน repo** — ดู [product/README.md](product/README.md) |
| `tests/` | เทสต์ทั้งหมดของโปรเจกต์ (pytest) — `python -m pytest tool/tests -q` จากโฟลเดอร์บนสุด ไม่เรียก API ; เทสที่ต้องใช้ไฟล์ข้อมูลใน `product/` ข้ามเองถ้าไม่มีไฟล์ |
| `phase4_discovery_round/` | มีแค่ README (โค้ดของ ⑩ อยู่ใน `phase2_three_streams/`) |

เลขโฟลเดอร์ `phase1-9` คือลำดับที่เขียนโค้ด ไม่ตรงกับเลขขั้น ①-⑳ — ลำดับที่รันจริงดูตารางใน [README หลัก](../README.md#ลำดับที่รันจริง)
