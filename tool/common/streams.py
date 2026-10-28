# -*- coding: utf-8 -*-
"""รายชื่อสายหลักฐาน (①-⑤) ที่เดียวของทั้งไปป์ไลน์ - ขั้นหลังทุกขั้นอ่านจากที่นี่แทนการเขียนรายชื่อซ้ำในแต่ละไฟล์

🆕 (2026-10-27) รอบใหม่ใช้สาย "Search" (คำค้นที่กำลังขึ้นรายหมวดของ Google Trends, tool/phase9_search_stream/) แทน 3 สายเดิม
Paper / Social / News ตามที่เจ้าของงานสั่ง - 3 สายเดิมยังอยู่ในรายการเพื่อให้รอบเก่าสร้างรายงานใหม่ได้เหมือนเดิม
แต่ละรอบใช้เฉพาะสายที่มีไฟล์ผลอยู่จริงในโฟลเดอร์รอบ (present_streams) - ไม่มีไฟล์ = ไม่ใช่สายของรอบนั้น ไม่ใช่ error
ลำดับ: 3 สายเดิมก่อน (ผลของรอบเก่าเรียงเหมือนเดิมทุกตัวอักษร) แล้วตามด้วย Search"""
from pathlib import Path

STREAM_FILES = {
    "Paper": "phase1_paper_stream_result.json",
    "Social": "phase2_social_stream_result.json",
    "News": "phase2_news_stream_result.json",
    "Search": "phase2_search_stream_result.json",
}
LEGACY_STREAMS = ("Paper", "Social", "News")   # สายเดิม (รอบก่อน 2026-10-27) - main.py ไม่รันแล้ว
SEARCH_STREAM = "Search"


def present_streams(run_dir):
    """{ชื่อสาย: path} เฉพาะสายที่มีไฟล์ผลในโฟลเดอร์รอบ เรียงตาม STREAM_FILES"""
    run_dir = Path(run_dir)
    return {name: run_dir / fname for name, fname in STREAM_FILES.items() if (run_dir / fname).exists()}
