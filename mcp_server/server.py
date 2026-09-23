# -*- coding: utf-8 -*-
"""MCP server (stdio) สำหรับอ่านผลลัพธ์ของ Trend Pipeline v2

ร่างแรกมีเฉพาะ **เครื่องมืออ่าน** เท่านั้น - ไม่รันไปป์ไลน์ ไม่เรียก LLM/SerpAPI/NVIDIA จึงไม่เสียเงินและไม่แก้ไฟล์
ตรรกะการอ่านอยู่ใน `queries.py` (ฟังก์ชันล้วน เทสต์ได้โดยไม่ต้องติดตั้ง MCP SDK) ไฟล์นี้เป็นแค่ตัวห่อเป็น tool

รัน:  python -m mcp_server.server        (จากโฟลเดอร์บนสุดของ repo)
ติดตั้ง:  pip install -r mcp_server/requirements.txt

⚠️ stdio server ใช้ stdout คุยกับ client ห้าม print อะไรลง stdout ในโค้ดที่ tool เรียก (queries.py จัดการให้แล้ว)
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import queries

mcp = FastMCP("trend-pipeline")


@mcp.tool()
def list_runs() -> list[dict]:
    """รายชื่อรอบรันทั้งหมด เรียงจากใหม่ไปเก่า พร้อมหัวข้อ จำนวนเทรนด์ที่คัดไว้ และมีผลขั้นไหนแล้วบ้าง"""
    return queries.list_runs()


@mcp.tool()
def get_run_summary(run_id: str | None = None) -> dict:
    """ภาพรวมของรอบหนึ่ง: หัวข้อ จำนวนเทรนด์ เทรนด์ที่ถูกคัดออกพร้อมเหตุผล และแต่ละขั้นรันเมื่อไหร่ด้วยโมเดลอะไร
    (ไม่ระบุ run_id = รอบล่าสุด)"""
    return queries.get_run_summary(run_id)


@mcp.tool()
def list_trends(run_id: str | None = None) -> list[dict]:
    """เทรนด์ชุดที่ไปป์ไลน์คัดไว้ (Top N) พร้อม Rank Score, Z_Delta, สถานะการเติบโต, คะแนน Longevity
    และจำนวนสินค้าที่จับคู่ได้ - เรียงตามอันดับที่แสดงผล (top_rank)"""
    return queries.list_trends(run_id)


@mcp.tool()
def get_trend(trend: str, run_id: str | None = None) -> dict:
    """รายละเอียดเทรนด์เดียว: จุดเด่นเชิงแนวคิดจากขั้น ⑪ (attribute / functional / psychosocial / job-to-be-done /
    point of difference), ค่าพยากรณ์, คีย์เวิร์ดที่ใช้ค้น Google Trends และสินค้าที่ใกล้ที่สุด 3 อันดับ"""
    return queries.get_trend(trend, run_id)


@mcp.tool()
def get_top_products(trend: str, run_id: str | None = None, limit: int = 5) -> dict:
    """สินค้าใน Watsons ที่ใกล้เคียงเทรนด์นี้ที่สุด พร้อมราคา ยอดขาย และเหตุผลสั้นๆ (มีเฉพาะ 5 อันดับแรก)

    ค่า similarity ใช้เรียงลำดับเท่านั้น ยังไม่มีเกณฑ์ตัดสินว่า "ใช่/ไม่ใช่" และยังไม่เคยวัดความแม่นเทียบกับคนตรวจ
    ให้ถือเป็นรายชื่อตัวเลือกสำหรับคนตรวจต่อ"""
    return queries.get_top_products(trend, run_id, limit)


@mcp.tool()
def list_brands(run_id: str | None = None) -> list[str]:
    """แบรนด์ที่เคยค้นหาในรอบนี้ (ผลของขั้น ⑬)"""
    return queries.list_brands(run_id)


@mcp.tool()
def get_brand_coverage(brand: str, run_id: str | None = None, limit: int = 5) -> dict:
    """แบรนด์ที่ระบุมีสินค้าใกล้แต่ละเทรนด์แค่ไหน พร้อมอันดับเทียบสินค้าทั้งตลาด (rank_vs_market จาก 10,622 ชิ้น)"""
    return queries.get_brand_coverage(brand, run_id, limit)


@mcp.tool()
def get_yearly_ranks(run_id: str | None = None) -> dict:
    """อันดับความสนใจรายปีของเทรนด์ในชุด Top N (ชุดเดียวกับ bump chart) และอันดับของปีปัจจุบัน"""
    return queries.get_yearly_ranks(run_id)


@mcp.tool()
def list_report_sections(run_id: str | None = None) -> list[str]:
    """หัวข้อทั้งหมดใน Master Report ของรอบนี้ (ใช้เลือกก่อนเรียก get_report ทีละหัวข้อ ไฟล์เต็มยาวมาก)"""
    return queries.list_report_sections(run_id)


@mcp.tool()
def get_report(run_id: str | None = None, section: str | None = None) -> dict:
    """Master Report ทั้งฉบับ หรือเฉพาะหัวข้อที่ระบุ เช่น "Executive Summary" หรือชื่อเทรนด์"""
    return queries.get_report(run_id, section)


@mcp.tool()
def get_manifest(run_id: str | None = None) -> dict:
    """manifest ของรอบ: โมเดลที่ใช้จริงในแต่ละขั้น เวลา และ hash ของไฟล์ input/output (ใช้ตรวจย้อนหลัง)"""
    return queries.get_manifest(run_id)


if __name__ == "__main__":
    mcp.run()
