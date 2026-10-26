# tool/

โค้ดของไปป์ไลน์ทั้งหมด — วิธีติดตั้ง การใช้งาน และสถาปัตยกรรมอยู่ใน [README หลัก](../README.md)

โฟลเดอร์ `step1-5` เรียงตามลำดับที่ `main.py` รัน เลขในวงกลม ①-⑰ คือเลขขั้นของเอกสารออกแบบ

| โฟลเดอร์ | มีอะไร |
|---|---|
| `common/` | `bootstrap.py` (path, `.env`, `use_bedrock()`, ฟังก์ชันร่วม) และส่วนที่ใช้จริงของระบบรุ่นแรก (`trend_final_subset.py`, `trend_final_v2_subset.py`) |
| `phase2_three_streams/` | ①-⑤ หลักฐาน 3 สาย: `paper/` (+ `scrapers/` MDPI, PubMed Central), `social/`, `news/` และ `compare_all_streams.py` |
| `phase2_three_streams/` | ⑦ `fetch_trends_worldwide_serpapi.py`, ⑧-⑨ `run_category_aggregation.py` (+ `aggregate_forecast.py`), ⑥ `rank_trends.py`, ⑩ `cross_category_discovery.py` |
| `phase3_supply_layer/` | ⑪ `extract_trend_highlights.py`, ⑫ `validate_at_scale_nvidia.py`, ⑬ `run_brand_coverage.py` และ library ที่ใช้ร่วม (`match_supply.py`, `validate_at_scale.py`) |
| `phase5_report/` | ⑭-⑮ `run_stepic_report.py` — STEPIC → Master Report |
| `phase6_pdf_report/` | ⑯ `build_pdf_report.py` รายงานเทรนด์ และ ⑰ `build_brand_report.py` รายงานแบรนด์ x เทรนด์ - อังกฤษ + ไทย (Jinja2 → Playwright Chromium) |
| `product/` | `watsons_product.csv` — สินค้า Watsons 10,622 SKU / 695 แบรนด์ |
| `experiments/` | สคริปต์ทดลองและเทียบผลที่ `main.py` ไม่ได้เรียก (เทียบ baseline, lead-lag, DeepSeek, ชุดข้อมูลย่อย ฯลฯ) |
| `history/` | บันทึกการพัฒนาแต่ละเฟส ไม่ต้องรัน |
| `tests/` | `test_pure_functions.py`, `test_trend_final_subset.py`, `test_pdf_report.py`, `test_plot_trend_map.py` |

ชื่อไฟล์ผลลัพธ์ในโฟลเดอร์รอบ (`phase1_…`, `phase3_…`) ยังเป็นชื่อเดิม เพื่อให้รอบเก่าอ่านได้
