# Phase 0 — เก็บกวาดก่อน

**สถานะ:** ✅ **แก้เสร็จ + ทดสอบผ่านแล้ว** (2026-08-28) — ผลลัพธ์คือ `trend_final_v2.py` ที่ root
**ไฟล์ถาวรคู่ขนานกับ `trend_final.py` เดิม ไม่มีแผน promote ทับ root เด็ดขาด** (ตัดสินใจ 2026-08-31
ดู Backlog ข้อ 27 — `trend_final.py` ห้ามแตะตลอดไป ไม่มีข้อยกเว้น)

## ไฟล์ในโฟลเดอร์นี้
| ไฟล์ | คืออะไร |
|---|---|
| `../../trend_final_v2.py` (root) | เวอร์ชันที่แก้แล้ว (2,932 บรรทัด ลดจาก 2,968) — ย้ายมาจากที่นี่แล้ว 2026-08-31 |
| `patch.py` | สคริปต์ที่ใช้แก้ตอนสร้างครั้งแรก — รันซ้ำได้ถ้าต้องสร้าง `trend_final_v2.py` ใหม่จาก `trend_final.py` ต้นฉบับ |
| `verify.py` | ชุดทดสอบ 19 ข้อ **ไม่ยิง API เลย** — `python verify.py` (path ชี้ไป `trend_final_v2.py` ที่ root แล้ว) |

## สิ่งที่แก้ (6 จุด)

### 1. ตัดฟีเจอร์ตาย `news_relevance_count` + `news_momentum`
หลักฐาน: feature importance = **0.0000 เป๊ะทั้ง RandomForest และ XGBoost ทุก cutoff**
(`Detail/_data/feature_importance_noarima.csv`) แต่เป็นต้นทุนใหญ่สุดใน pipeline

| จุดที่แก้ | ทำอะไร |
|---|---|
| B. `feature_cols` (~2085) | ตัด 2 ฟีเจอร์ออก เหลือ 6 ตัว |
| C. recursive forecast (~1934) | ตัด key ที่อ้างคอลัมน์ที่ถูกลบ (ไม่งั้น KeyError) |
| D. `create_features` (~1847) | ตัดการสร้างฟีเจอร์ — พ่วง `new_product_mentions` ที่เป็นโค้ดตายไปด้วย |
| E. บล็อก NEWS PROCESSING (~2065) | **ตัวกินต้นทุนจริง** — ยิง Google News + LLM 1 ครั้งต่อทุกคู่ (คลัสเตอร์ × เดือน) |
| F. `filter_relevant_news_llm` + `search_news` | ตายตามบล็อก E (verify ด้วย grep แล้วไม่มีที่อื่นเรียก) |

**ต้นตอที่น่าจะทำให้ฟีเจอร์ตาย:** ค้นข่าวด้วย "ชื่อคลัสเตอร์" ที่ยาวและเป็นภาษาการตลาด
ย้อนหลังถึงปี 2004 ซึ่งแทบไม่มีข่าวตรงเลย ค่าจึงเป็น 0 เกือบทั้งตาราง

### 2. แก้บั๊ก `safe_json_parse` (จุด A, ~บรรทัด 186)
เดิมกระโดดไปทำ `content.replace('\"', '"')` ทันทีโดยไม่ลอง parse ก่อน — ตั้งใจแก้ปัญหา
โมเดลเล็กที่ over-escape แต่ไปทำลาย escaped quote ที่**ถูกต้องอยู่แล้ว**ด้วย
เจอจริงตอนรัน pilot อีคอมเมิร์ซต่างประเทศ ทำให้สรุปผลหายทั้งรอบ

**ทางแก้:** ลอง `json.loads()` ตรงๆ ก่อนเสมอ ตัวซ่อมเดิมเก็บไว้เป็น fallback — ไม่ลดความสามารถเดิม

## ผลทดสอบ (`python verify.py`)
```
[1] safe_json_parse ........... PASS 10/10   (2 เคสที่เคยพัง + 8 เคสเดิมไม่ regress)
[2] modeling path ............. PASS  9/9    (create_features + run_all_models 48 เดือน)
✅ ผ่านทุกข้อ
```
ยืนยันเพิ่ม: `tree_features = [c for c in feature_cols if c in df_group.columns]` เป็น derived
จาก `feature_cols` จึงสอดคล้องกันอัตโนมัติ ไม่มี hardcode ค้าง

## ⚠️ ข้อควรรู้
`trend_final_v2.py` โหลด `.env` และ `config/` จาก **โฟลเดอร์ของตัวเอง**
(`_TOOLS_DIR = Path(__file__).resolve().parent`) และ `sys.exit(1)` เงียบๆ ถ้าไม่เจอ `TAVILY_API_KEY`
→ ตอนอยู่ใน `workspace/phase0_cleanup/` รันตรงๆ ไม่ได้ (ไม่เจอ `.env`) ตอนนี้ย้ายไป root แล้วเจอ `.env`
ตรงๆ ไม่ต้องยัด env มือเหมือนตอนอยู่ใน workspace (นี่เป็นลักษณะเดิมของไฟล์ ไม่ใช่ผลจากการแก้ครั้งนี้)

## เกณฑ์วัดว่าสำเร็จ
- [x] compile ผ่าน
- [x] ไม่มีอ้างอิงถึงฟีเจอร์ที่ตัดหลงเหลือ (เหลือแค่ในคอมเมนต์)
- [x] `safe_json_parse` แก้แล้วและไม่ regress
- [x] modeling path รันได้ ผลพยากรณ์ไม่ระเบิด/ไม่ NaN
- [ ] **รันเต็ม pipeline จริงเทียบผลกับ `trend_final.py` เดิม** ← ยังต้องทำเพื่อยืนยันว่า `trend_final_v2.py` ใช้แทนได้จริงในงานจริง (แต่จะไม่เอาไปทับ `trend_final.py` แน่นอน)
- [ ] ยืนยันว่าเวลารันลดลงจริง
