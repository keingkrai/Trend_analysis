# -*- coding: utf-8 -*-
"""
ให้ LLM จัดสินค้าทุกชิ้นในแคตตาล็อก (Konvy ตั้งแต่ 2026-10-11 เดิม Watsons) เข้า path ของ product_category.csv (Industry > Category > Sub-category > Segment)

ทำไม LLM แทนกฎ (เจ้าของงานสั่ง 2026-10-01): กฎใน euromonitor_mapping.py ต้องไล่แก้ทีละกรณี (ผ้าอนามัยติดป้ายโกนหนวด, สีผมติดป้าย
อาหารเสริม ฯลฯ) และวัดได้ว่ายังผิดราว 2-4% แบบหางยาว LLM อ่านชื่อสินค้าเป็นภาษาธรรมชาติได้เลย - กฎยังอยู่เป็นตัวสำรองเมื่อ LLM ตอบไม่ครบ
และเป็นตัวเทียบความสอดคล้อง (EM_rule_*)

วิธีทำ
  - ส่งสินค้าครั้งละ BATCH_SIZE ชิ้น + รายการ path ทั้งหมดที่มีรหัสเลข ให้เลือก "รหัส" (ไม่ให้พิมพ์ชื่อ - กันสะกดผิด/คิดหมวดเอง)
  - ชื่อสินค้าคือหลักฐานหลัก; Product_Type/Segment ของแคตตาล็อกส่งไปเป็นคำใบ้ที่ "เสียได้" (พบว่าผิดบางแถว) - ตัวเลือก use_hints
  - ตอบกลับเป็น [[เลขสินค้า, รหัส path, ความมั่นใจ 1-3], ...]; ตรวจรหัสกับไฟล์จริงทุกตัว ตอบไม่ครบ -> ถามซ้ำเฉพาะที่ขาด
  - บันทึกต่อท้ายไฟล์ euromonitor_llm_labels.jsonl ทุกชุด (ขัดจังหวะแล้วรันต่อได้) key = hash(brand|ชื่อ|Product_Type)

ใช้: python tool/product/classify_products_llm.py --run --variant hints      # รอบที่ 1 (ส่งคำใบ้ของแคตตาล็อก)
     python tool/product/classify_products_llm.py --run --variant nohints    # รอบที่ 2 (ไม่ส่งคำใบ้) - 2 รอบนี้ใช้ตัดสินกัน (pick_label)
     python tool/product/classify_products_llm.py --status         # สรุปว่าจัดไปแล้วกี่ชิ้น
"""
import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
TOOL_DIR = HERE.parent
PROJECT_ROOT = TOOL_DIR.parent
sys.path.insert(0, str(TOOL_DIR))
from product import euromonitor_mapping as em  # noqa: E402

LABELS_PATH = HERE / "euromonitor_llm_labels.jsonl"
PROMPT_VERSION = "v3-2026-10-11"   # v3: เปลี่ยนชื่อร้านใน prompt เป็น Konvy (ข้ามแถวที่ไม่ใช่ความงามที่ฝั่งรัน ไม่เปลี่ยนคำตอบ); v2: ชุด/เซ็ตจัดตามสินค้าหลัก + ป้าย B&C ของ Watsons = สินค้าเด็ก (v1 ปล่อยชุดแชมพูเข้า Personal Set /kits และสินค้าเด็กหลุดไป Bath and Shower)
DEFAULT_MODEL = "zai.glm-5"
BATCH_SIZE = 25
MAX_NAME_CHARS = 150

# id (เลข 1..N ตามลำดับในไฟล์) <-> path
PATH_BY_ID = em.PATH_BY_ID

SYSTEM_PROMPT = """You classify retail products sold at Konvy, a Thai online beauty retailer (beauty, personal care, health, household, accessories) into ONE category path from the closed list below. Answer with the numeric id of the best path.

Rules
- The product NAME is the authority (names may mix English and Thai). "retailer_type" and "retailer_segment" are labels from the retailer's own data and are WRONG for a notable share of rows (for example sanitary pads labelled 'Shaving Cream', contact lenses labelled 'Moisturizing Cream', hair colour labelled as a supplement). Use them only to disambiguate when the name is unclear; ignore them when they contradict the name.
- Pick the most specific path that fits. Products that are not beauty/personal care (supplements, contact lenses, laundry, apparel, jewelry, devices ...) belong in their own non-beauty paths in the list - never force them into a beauty path.
- The same segment name appears under several parents. Choose the parent that matches the product: men's vs women's (men's razors and shaving -> Men's Grooming; women's razors and hair removal -> Depilatories), premium vs mass (Premium = prestige / dermatology-clinic / luxury brands and clearly higher prices; Mass = drugstore and value brands; if unsure choose Mass).
- Kids' and baby products go to the Baby and Child-specific path. Sets/kits go to the matching Sets/Kits path of their own category when it exists.
- Bundles and sets (names with 'Set', '+', 'Free ...', 'x2', 'Value Pack', 'Duo'): classify by the MAIN product - e.g. 'Shampoo 380 ml + Treatment Mask' is Hair Care, 'Sunscreen 50 ml Free Cleansing Gel' is Sun Care. Use a Sets/Kits path ('Personal Set /kits', 'Gift Sets & Value Sets', ...) only when the set clearly mixes several different categories and no single product is the main one.
- Baby and child: a retailer_segment that begins with 'B&C', 'Medicated B&C' or 'Nappy' means the retailer itself classes the product as baby/child-specific - follow it (baby shower milk, baby bath, baby lotion, baby wipes belong to the Baby and Child-specific path) unless the name clearly shows an adult product (the brand 'Baby Bright' is adult makeup; 'Smooth E Babyface' is an adult face cleanser).
- If nothing in the list fits at all, answer id 0 for that product.

Return ONLY JSON in this exact shape, one entry per product number, no commentary:
{"r": [[<product number>, <path id>, <confidence 1-3>], ...]}
confidence: 3 = sure, 2 = likely, 1 = guess.

CATEGORY PATHS (id | Level1 > Level2 > Level3 > Level4)
"""


def paths_table():
    return "\n".join(f"{i} | {' > '.join(p)}" for i, p in PATH_BY_ID.items())


SYSTEM_PROMPT_FULL = SYSTEM_PROMPT + paths_table()


def _clean(v, limit=None):
    s = v.strip() if isinstance(v, str) else ""
    s = re.sub(r"\s+", " ", s)
    return s[:limit] if limit else s


def product_key(row):
    return em.product_key(row)


def user_prompt(batch, use_hints=True):
    lines = []
    for n, row in enumerate(batch, start=1):
        parts = [f'brand="{_clean(row.get("brand"))}"', f'name="{_clean(row.get("product_name"), MAX_NAME_CHARS)}"']
        if use_hints:
            parts.append(f'retailer_type="{_clean(row.get("Product_Type"), 60)}"')
            parts.append(f'retailer_segment="{_clean(row.get("Segment"), 60)}"')
        price = row.get("sale_price_thb")
        if isinstance(price, str) and price.strip():
            parts.append(f"price_thb={price.replace(',', '').split('.')[0]}")
        elif isinstance(price, (int, float)) and not pd.isna(price):
            parts.append(f"price_thb={int(price)}")
        lines.append(f"{n}. " + " | ".join(parts))
    return "Classify these products:\n" + "\n".join(lines)


_TRIPLE = re.compile(r"\[\s*(\d+)\s*,\s*(\d+)\s*,\s*([123])\s*\]")


def parse_answer(text, n_items):
    """-> {เลขสินค้า: (path id, confidence)} เฉพาะที่ตรวจผ่าน (เลขสินค้า 1..n, path id 0..N) - ไม่เชื่อรูปแบบ JSON อย่างเดียว"""
    out = {}
    for n, pid, conf in _TRIPLE.findall(text or ""):
        n, pid, conf = int(n), int(pid), int(conf)
        if 1 <= n <= n_items and (pid == 0 or pid in PATH_BY_ID):
            out.setdefault(n, (pid, conf))
    return out


def classify_batch(client, model, batch, use_hints=True, max_rounds=3, log=print):
    """-> ({index ใน batch (0-based): (path id, conf)}, จำนวนครั้งที่เรียก) ถามซ้ำเฉพาะที่ยังขาด"""
    answers, calls = {}, 0
    for _ in range(max_rounds):
        missing = [i for i in range(len(batch)) if i not in answers]
        if not missing:
            break
        sub = [batch[i] for i in missing]
        try:
            resp = client.chat.completions.create(
                model=model, temperature=0, max_tokens=1500, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": SYSTEM_PROMPT_FULL},
                          {"role": "user", "content": user_prompt(sub, use_hints)}])
            calls += 1
            parsed = parse_answer(resp.choices[0].message.content, len(sub))
        except Exception as e:   # noqa: BLE001 - เครือข่าย/throttle: ลองรอบถัดไป
            log(f"    ⚠️ เรียก LLM ล้มเหลว: {str(e)[:120]}")
            time.sleep(5)
            continue
        for j, val in parsed.items():
            answers[missing[j - 1]] = val
    return answers, calls


def classify_rows(rows, model=DEFAULT_MODEL, workers=6, use_hints=True, on_batch=None, log=print):
    """rows: list ของ dict สินค้า -> {product_key: (path id, conf)} ใช้ได้ทั้งรันจริงและเทสเทียบโมเดล (ไม่เขียนไฟล์เอง)"""
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)
    from common.bootstrap import use_bedrock

    batches = [rows[i:i + BATCH_SIZE] for i in range(0, len(rows), BATCH_SIZE)]
    results, lock, done = {}, threading.Lock(), [0]
    t0 = time.time()
    with use_bedrock(model_id=model) as client:
        def work(batch):
            ans, calls = classify_batch(client, model, batch, use_hints, log=log)
            return batch, ans, calls

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(work, b) for b in batches]
            for fut in as_completed(futures):
                batch, ans, calls = fut.result()
                with lock:
                    for i, (pid, conf) in ans.items():
                        results[product_key(batch[i])] = (pid, conf)
                    done[0] += 1
                    if on_batch:
                        on_batch(batch, ans)
                    if done[0] % 10 == 0 or done[0] == len(batches):
                        log(f"  [{done[0]}/{len(batches)}] ชุด · จัดแล้ว {len(results)}/{len(rows)} ชิ้น · {time.time() - t0:.0f}s")
    return results


def append_labels(batch, answers, model, variant):
    """เขียนต่อท้าย JSONL หลังจบแต่ละชุด (เรียกจาก on_batch ใต้ lock)"""
    with open(LABELS_PATH, "a", encoding="utf-8") as f:
        for i, (pid, conf) in answers.items():
            row = batch[i]
            f.write(json.dumps({"key": product_key(row), "path_id": pid, "conf": conf, "model": model,
                                "variant": variant, "prompt": PROMPT_VERSION, "brand": _clean(row.get("brand")),
                                "product_name": _clean(row.get("product_name"), 200)}, ensure_ascii=False) + "\n")


def beauty_candidates(df):
    """แถวที่ต้องให้ LLM จัด: ตัดแถวที่ทั้งป้าย Industry ของแคตตาล็อกและกฎเห็นตรงกันว่าไม่ใช่ความงาม (Konvy มีสินค้านอกความงาม ~17%:
    เสื้อผ้า อุปกรณ์ไฟฟ้า ของเล่น อาหารเสริม ฯลฯ - load_catalog() กรองทิ้งอยู่แล้ว ไม่คุ้มค่า LLM) - แถวที่สองฝั่งเห็นไม่ตรงกันยังถูกส่ง
    ผลของแถวที่ข้ามยังมาจากกฎตามเดิม; ไม่มีคอลัมน์ Industry = ส่งทุกแถว"""
    if "Industry" not in df.columns:
        return df
    non_beauty_label = df["Industry"].astype(str).str.strip().ne(em.BEAUTY)
    non_beauty_rule = em.add_euromonitor_columns(df)["EM_L1"].ne(em.BEAUTY)
    return df[~(non_beauty_label & non_beauty_rule)]


def run(model=DEFAULT_MODEL, workers=6, limit=None, variant="hints", include_all=False):
    use_hints = variant == "hints"
    df = pd.read_csv(em.CSV_PATH, encoding="utf-8-sig", low_memory=False)
    if not include_all:
        n_all = len(df)
        df = beauty_candidates(df)
        print(f"ข้ามแถวที่ไม่ใช่ความงามทั้งป้ายและกฎ {n_all - len(df)} แถว (ใช้ --all เพื่อจัดทุกแถว)")
    rows = df.to_dict("records")
    done_keys = {k for k, v in em.load_llm_labels(path=LABELS_PATH, prompt=PROMPT_VERSION).items() if variant in v}   # ผลของ prompt เวอร์ชันเก่าไม่นับว่าจัดแล้ว
    seen, todo = set(), []
    for r in rows:   # ชื่อ+แบรนด์+ชนิดซ้ำ -> ใช้ผลเดียวกัน
        k = product_key(r)
        if k in done_keys or k in seen:
            continue
        seen.add(k)
        todo.append(r)
    if limit:
        todo = todo[:limit]
    print(f"[{variant}] สินค้าทั้งหมด {len(rows)} แถว · จัดไปแล้ว {len(done_keys)} · ที่ต้องจัด {len(todo)} ชิ้น · โมเดล {model} · {workers} workers")
    if not todo:
        return
    results = classify_rows(todo, model, workers, use_hints, on_batch=lambda b, a: append_labels(b, a, model, variant))
    print(f"เสร็จ: ได้คำตอบ {len(results)}/{len(todo)} ชิ้น -> {LABELS_PATH.name}")
    if len(results) < len(todo):
        print(f"⚠️ ยังไม่ครบ {len(todo) - len(results)} ชิ้น - รันคำสั่งเดิมอีกครั้งเพื่อจัดส่วนที่เหลือ")


def status():
    labels = em.load_llm_labels(path=LABELS_PATH)
    df = pd.read_csv(em.CSV_PATH, encoding="utf-8-sig", low_memory=False, usecols=["brand", "product_name", "Product_Type"])
    keys = {product_key(r) for r in df.to_dict("records")}
    got = sum(1 for k in keys if k in labels)
    print(f"สินค้าไม่ซ้ำ {len(keys)} · มีผล LLM {got}")
    for variant in ("hints", "nohints"):
        n = sum(1 for k in keys if variant in labels.get(k, {}))
        z = sum(1 for k in keys if variant in labels.get(k, {}) and labels[k][variant][0] == 0)
        print(f"  รอบ {variant}: {n} ชิ้น (ตอบ 0 = ไม่เข้าหมวดไหน {z})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="ให้ LLM จัดสินค้า (แคตตาล็อก Konvy) เข้า path ของ product_category.csv")
    ap.add_argument("--run", action="store_true", help="จัดสินค้าที่ยังไม่มีผล (รันต่อจากเดิมได้)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--all", action="store_true",
                    help="จัดทุกแถวของแคตตาล็อก (ค่าตั้งต้นข้ามแถวที่ป้าย Industry และกฎเห็นตรงกันว่าไม่ใช่ความงาม - ถูกกรองทิ้งใน load_catalog อยู่แล้ว)")
    ap.add_argument("--variant", choices=("hints", "nohints"), default="hints",
                    help="hints = ส่ง Product_Type/Segment ของแคตตาล็อกเป็นคำใบ้ (เสียได้) / nohints = ส่งแค่แบรนด์+ชื่อ+ราคา")
    a = ap.parse_args()
    if a.status:
        status()
    elif a.run:
        run(a.model, a.workers, a.limit, a.variant, include_all=a.all)
    else:
        ap.print_help()
