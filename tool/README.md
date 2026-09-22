# tool/

โค้ดของไปป์ไลน์ทั้งหมด — วิธีติดตั้ง การใช้งาน และสถาปัตยกรรมอยู่ใน [README หลัก](../README.md)

| โฟลเดอร์ | มีอะไร |
|---|---|
| `common/` | `bootstrap.py` (path, `.env`, `use_bedrock()`, ฟังก์ชันร่วม) และส่วนที่ใช้จริงของระบบรุ่นแรก (`trend_final_subset.py`, `trend_final_v2_subset.py`) |
| `phase1_paper_stream/` | ①-⑤ สาย Paper (+ `scrapers/` MDPI, PubMed Central) |
| `phase2_three_streams/` | ①-⑤ สาย Social / News, ⑦ พยากรณ์, ⑧-⑨ สรุประดับหมวด, ⑥ Rank Score, ⑩ รอบค้นพบเพิ่ม |
| `phase3_supply_layer/` | ⑪ จุดเด่น + Top N, ⑫ จับคู่สินค้า, ⑬ ค้นหาแบรนด์ |
| `phase5_report/` | ⑭-⑮ STEPIC → Master Report |
| `product/` | `watsons_product.csv` — สินค้า Watsons 10,622 SKU / 695 แบรนด์ |
| `tests/` | `test_pure_functions.py`, `test_trend_final_subset.py` |
| `phase0_cleanup/`, `phase4_discovery_round/` | บันทึกเก่า ไม่ต้องรัน |

ชื่อโฟลเดอร์ `phase0-5` คือลำดับที่เขียนโค้ด ไม่ตรงกับเลขขั้น ①-⑮ — ลำดับที่รันจริงดูตารางใน [README หลัก](../README.md#ลำดับที่รันจริง)
