# mcp_server/ — MCP server อ่านผลลัพธ์ของไปป์ไลน์

ร่างแรก: **อ่านอย่างเดียว** ให้ agent ถามผลรันที่มีอยู่แล้วได้ (เทรนด์ สินค้าที่จับคู่ได้ แบรนด์ อันดับรายปี รายงาน)
ไม่รันไปป์ไลน์ ไม่เรียก LLM / SerpAPI / NVIDIA จึงไม่เสียเงินและไม่แก้ไฟล์ใดๆ

| ไฟล์ | หน้าที่ |
|---|---|
| `queries.py` | ตรรกะอ่านไฟล์ผลลัพธ์ทั้งหมด เป็นฟังก์ชันล้วน ไม่ต้องมี MCP SDK ก็ใช้/เทสต์ได้ |
| `server.py` | ห่อฟังก์ชันใน `queries.py` เป็น MCP tool (stdio) |
| `tests/test_queries.py` | เทียบผลกับไฟล์จริงของรอบอ้างอิง |

## ติดตั้งและรัน

```powershell
pip install -r mcp_server/requirements.txt
python -m mcp_server.server          # รันจากโฟลเดอร์บนสุดของ repo
```

ตั้งค่าใน client (เช่น Claude Desktop / Claude Code) — `mcpServers`:

```json
{
  "mcpServers": {
    "trend-pipeline": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "D:\\path\\to\\Trend_analysis"
    }
  }
}
```

## เครื่องมือที่มี

| tool | คืออะไร |
|---|---|
| `list_runs` | รอบรันทั้งหมด เรียงใหม่ไปเก่า พร้อมหัวข้อและมีผลขั้นไหนแล้ว |
| `get_run_summary` | ภาพรวมรอบ: จำนวนเทรนด์ เทรนด์ที่ถูกคัดออกพร้อมเหตุผล แต่ละขั้นรันเมื่อไหร่ด้วยโมเดลอะไร |
| `list_trends` | เทรนด์ชุด Top N พร้อม Rank Score, Z_Delta, สถานะ, Longevity, จำนวนสินค้าที่จับคู่ได้ |
| `get_trend` | รายละเอียดเทรนด์เดียว: จุดเด่นจาก ⑪, คีย์เวิร์ด, ค่าพยากรณ์, สินค้าใกล้สุด 3 อันดับ |
| `get_top_products` | สินค้า Watsons ที่ใกล้เทรนด์ที่สุด พร้อมราคา ยอดขาย และเหตุผล |
| `list_brands` / `get_brand_coverage` | แบรนด์ที่เคยค้นในรอบนั้น และแบรนด์นั้นอยู่ตรงไหนของแต่ละเทรนด์ |
| `get_yearly_ranks` | อันดับความสนใจรายปีในชุด Top N (ชุดเดียวกับ bump chart) + อันดับของปีปัจจุบัน |
| `list_report_sections` / `get_report` | หัวข้อใน Master Report และดึงมาทีละหัวข้อ (ไฟล์เต็มยาวมาก) |
| `get_manifest` | manifest ของรอบ: โมเดลที่ใช้จริง เวลา และ hash ไฟล์ ใช้ตรวจย้อนหลัง |

ทุก tool รับ `run_id` ได้ ไม่ใส่ = รอบล่าสุด ชื่อเทรนด์และแบรนด์จับคู่แบบไม่สนตัวพิมพ์และใส่แค่บางส่วนได้
ถ้าหาไม่เจอจะคืน error พร้อมรายการตัวเลือกที่มีจริง

## กติกาที่ต้องรักษาไว้

- **ห้าม import `common.bootstrap`** — มันคำนวณ `OUTPUTS` ตอน import จาก env `TREND_RUN_ID` โปรเซสจึงผูกกับรอบเดียว
  ตลอด ซึ่งใช้กับ server ที่ต้องสลับรอบตามคำขอไม่ได้ (มีเทสต์คุมข้อนี้)
- **ห้าม print ลง stdout** ในโค้ดที่ tool เรียก เพราะ stdio server ใช้ stdout คุยกับ client — `get_yearly_ranks`
  เรียกฟังก์ชันของ `Plot_bump_chart.py` ที่ print อยู่ จึงเปลี่ยนปลายทาง stdout เป็น stderr ระหว่างเรียก
- **อ่านอย่างเดียว** ถ้าจะเพิ่ม tool ที่เขียนไฟล์หรือเสียเงิน ให้แยกเป็นกลุ่มต่างหากตามหัวข้อถัดไป

## เทสต์

```powershell
python -m pytest mcp_server/tests -q
```

เทียบกับไฟล์จริงของรอบ `beauty_and_personal_care_20260916_082438` เช่น สินค้าที่ tool คืนต้องตรงกับ
`phase3_scale_validation_nvidia_result.json` และตารางอันดับรายปีต้องตรงกับไฟล์ ranks ที่ bump chart บันทึกไว้
ถ้าเครื่องไหนไม่มีรอบนั้น เทสต์จะข้ามเอง

## ขั้นต่อไป (ยังไม่ได้ทำ)

กลุ่ม tool สั่งรัน ต้องเป็นแบบ **คืน job id ไม่รอผล** เพราะแต่ละขั้นใช้เวลาหลายนาทีถึงหลักชั่วโมง

- `start_pipeline(topic, years, top_n)` / `start_stage(run_id, stage)` / `start_brand_coverage(run_id, brand)`
- `get_job(job_id)` → สถานะ + log ท้ายๆ, `cancel_job(job_id)`

วิธีทำที่เข้ากับไปป์ไลน์ปัจจุบัน: ยิงเป็น subprocess แบบเดียวกับ `main.py` (ตั้ง env `TREND_RUN_ID` / `TREND_TOPIC` /
`TREND_YEARS` / `TREND_TOP_N` แล้วรันสคริปต์ของขั้นนั้น โดยตั้ง cwd เป็นโฟลเดอร์บนสุด) — `prompt_run_config()`
ข้ามการถามอัตโนมัติเมื่อมี env ครบอยู่แล้ว

การ์ดที่ต้องมีก่อนเปิดกลุ่มนี้: ล็อกให้รันงานหนักทีละงาน (cache สินค้าและโควตาเป็นของกลาง), เช็กโควตา SerpAPI ก่อน
เริ่ม ⑦, จำกัดค่า `top_n`, และให้ tool ที่เสียเงินต้องส่ง flag ยืนยันมาด้วย
