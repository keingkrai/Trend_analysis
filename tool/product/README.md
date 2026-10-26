# tool/product/

โค้ดจัดการแคตตาล็อกสินค้า + ไฟล์ข้อมูลที่ต้องมีในเครื่อง

## ไฟล์ข้อมูลที่ **ไม่ได้อยู่ใน repo** (ใหญ่เกิน 100MB ที่ GitHub รับ และเป็นข้อมูล Euromonitor / FDA / ที่ scrape จากร้านค้า) — วางไว้ในโฟลเดอร์นี้เอง

| ไฟล์ | ที่มา | ใช้ที่ |
|---|---|---|
| `konvy_product.xlsx` | scrape จาก Konvy | `build_konvy_catalog.py` → `konvy_product.csv` |
| `eveandboy.xlsx` | scrape จาก Eve and Boy | `build_eve_catalog.py` → `eveandboy_product.csv` |
| `market_product.csv` | `build_market_catalog.py --no-eve` (ตลาด = Konvy ล้วน) | ⑫ ⑬ ⑯ ⑰ รายงานทุกฉบับ |
| `euromonitor.xlsx` | Euromonitor (ข้อมูลมีลิขสิทธิ์) | ตัวเลขตลาดใน ⑲ รายงานส่วนแบ่งตลาด (`phase7_market_report/market_data.py`) |
| `FDA.xlsx` | ใบจดแจ้งเครื่องสำอาง อย. ไทย | ⑲ รายงานส่วนแบ่งตลาด (`market_data.py`) ; ไม่ได้ใช้จัดอันดับเทรนด์ (ทดสอบแล้วผลแย่ลง) |
| `euromonitor_category_map.csv`, `euromonitor_llm_labels.jsonl` | ตารางจับคู่หมวด + ผลที่ LLM จัดหมวดสินค้า (`classify_products_llm.py`) | `euromonitor_mapping.py` (ไม่มี = ใช้กฎสำรอง) |
| `market_product_pairs.csv`, `market_product_summary.json` | ผลพลอยได้จาก `build_market_catalog.py` (คู่สินค้าที่รวมกัน ไว้ตรวจ) | เทสต์ `test_market_catalog.py` |

เทสต์ที่ต้องใช้ไฟล์เหล่านี้จะ **ข้ามเอง** ถ้าไม่พบไฟล์ (`pytest.skip`) — clone ใหม่แล้วรัน `python -m pytest tool/tests -q` ได้เลย

## ไฟล์ที่อยู่ใน repo

| ไฟล์ | คืออะไร |
|---|---|
| `product_category.csv` | taxonomy หมวดสินค้า 4 ระดับ (L1-L4) ตาม Euromonitor |
| `euromonitor_mapping.py` | โหลดแคตตาล็อก + หมวด, กฎสำรองจัดหมวด |
| `classify_products_llm.py` | ให้ LLM จัดหมวดสินค้า (2 รอบ + กฎตัดสิน) |
| `build_konvy_catalog.py`, `build_eve_catalog.py`, `build_market_catalog.py` | สร้างแคตตาล็อกจาก xlsx ที่ scrape มา |
| `size_standardiser.py` | แปลงขนาดสินค้าเป็นหน่วยมาตรฐาน (ml / g / ชิ้น) |
| `watsons_product.csv` | แคตตาล็อก Watsons รุ่นเก่า (แทนด้วย Konvy ตั้งแต่ 2026-10-11) - เหลือไว้ให้สคริปต์ทดสอบ `validate_at_scale*.py` เท่านั้น |
