# -*- coding: utf-8 -*-
"""สาย Search ส่วนดึงข้อมูล: คำค้นที่กำลังขึ้น (rising) + ยอดนิยม (top) ของแต่ละหมวด Google Trends ไม่ใส่คำค้น ระบุแค่หมวด
ช่วง 12 เดือนล่าสุด (date=today 12-m, tz=420) | 1 หมวด x 1 พื้นที่ = 1 search ของ SerpAPI
cache รายเดือน: _checkpoints/search_rising/<YYYY-MM>/<พื้นที่>_<หมวด>.json - รอบอื่นในเดือนเดียวกันใช้ซ้ำ ไม่เสียโควตา
ย้ายจากการทดลอง output/_experiments/open_talk_20261027/fetch_rising.py (2026-10-27)"""
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from common.serpapi_keys import SerpApiKeyPool, mask, should_rotate

HERE = Path(__file__).resolve().parent
CATEGORY_TREE = HERE / "gt_categories.json"   # รายการหมวดของ Google Trends (ดึงจาก trends.google.com/trends/api/explore/pickers/category)
DATE_RANGE = "today 12-m"
TZ = "420"
THROTTLE_PAUSE = 1800  # คีย์ที่ติดจำกัด 250 search/ชั่วโมง พักกี่วินาทีก่อนลองใหม่
WORKERS = 2


class ThrottleAwarePool(SerpApiKeyPool):
    """เหมือน POOL แต่ (1) ปลอดภัยเมื่อเรียกหลาย thread (เปลี่ยนคีย์ครั้งเดียวต่อคีย์) (2) คีย์ที่ติดจำกัดต่อชั่วโมง
    ("throttled ... per hour" - ไม่เข้า should_rotate) พักไว้ชั่วคราวแล้วลองคีย์ถัดไป ไม่ทิ้งถาวร ทุกคีย์ติด = รอ"""

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self.paused = {}

    def search(self, params):
        while True:
            with self._lock:
                usable = [k for k in self.keys if k not in self.exhausted]
                if not usable:
                    return {"error": "SerpAPI: all keys have run out of searches or are unusable"}
                ready = [k for k in usable if self.paused.get(k, 0) <= time.time()]
                key = ready[0] if ready else None
                wait = 0 if key else min(self.paused[k] for k in usable) - time.time()
            if key is None:
                print(f"  ⏳ ทุกคีย์ติดจำกัดต่อชั่วโมง รอ {max(wait, 60) / 60:.0f} นาที", flush=True)
                time.sleep(max(wait, 60))
                continue
            result = self._client({**params, "api_key": key})
            err = str(result.get("error", "")) if isinstance(result, dict) else ""
            if "throttled" in err.lower() or "per hour" in err.lower():
                with self._lock:
                    if self.paused.get(key, 0) <= time.time():
                        self.paused[key] = time.time() + THROTTLE_PAUSE
                        print(f"  ⏳ คีย์ {mask(key)} ติดจำกัดต่อชั่วโมง พัก {THROTTLE_PAUSE // 60} นาที", flush=True)
                continue
            if err and should_rotate(err):
                with self._lock:
                    if key not in self.exhausted:
                        self.exhausted.add(key)
                        print(f"  🔁 คีย์ {mask(key)} ใช้ต่อไม่ได้ ({err[:60]})", flush=True)
                continue
            return result


def load_categories():
    """[{cat_id, level, l1, l2}] หมวดระดับ 1-2 - รหัสที่ซ้ำ (เช่น 66 Pets & Animals อยู่ใต้ Hobbies ด้วย) นับเป็นระดับที่ต่ำกว่าก่อน"""
    root = json.loads(CATEGORY_TREE.read_text(encoding="utf-8"))
    rows = []
    for top in root["children"]:
        rows.append({"cat_id": top["id"], "level": 1, "l1": top["name"], "l2": None})
        for sub in top.get("children", []):
            rows.append({"cat_id": sub["id"], "level": 2, "l1": top["name"], "l2": sub["name"]})
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r["level"]):
        if r["cat_id"] not in seen:
            seen.add(r["cat_id"])
            out.append(r)
    return out


def norm(q):
    """Google เว้นวรรคคำไทยตามการตัดคำ ("ทรง ผม ชาย 2026") - รวมกลับเป็นคำเดียวกันก่อนนับซ้ำ"""
    q = re.sub(r"\s+", " ", str(q).strip().lower())
    return re.sub(r"(?<=[฀-๿]) (?=[฀-๿])", "", q)


def cache_dir(checkpoints, month=None):
    return Path(checkpoints) / "search_rising" / (month or date.today().strftime("%Y-%m"))


def plan_jobs(cats, geos_deep, geos_top):
    """(พื้นที่, หมวด) ที่ต้องดึง: geos_deep = ทุกหมวดระดับ 1-2 / geos_top = เฉพาะหมวดใหญ่ระดับ 1"""
    jobs = [(g, c["cat_id"]) for g in geos_deep for c in cats]
    jobs += [(g, c["cat_id"]) for g in geos_top if g not in geos_deep for c in cats if c["level"] == 1]
    return jobs


def fetch_one(pool, folder, geo, cat_id):
    f = folder / f"{geo}_{cat_id}.json"
    if f.exists():
        return True
    params = {"engine": "google_trends", "cat": str(cat_id), "date": DATE_RANGE, "tz": TZ, "data_type": "RELATED_QUERIES"}
    if geo != "WW":
        params["geo"] = geo
    res = pool.search(params)
    if "error" in res:
        err = str(res["error"])
        if "hasn't returned any results" in err or "no results" in err.lower():
            out = {"rising": [], "top": [], "_note": err}
        else:
            print(f"  ❌ {geo} {cat_id}: {err[:100]}", flush=True)
            return False
    else:
        rq = res.get("related_queries", {}) or {}
        out = {"rising": rq.get("rising", []), "top": rq.get("top", [])}
    folder.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return True


def fetch_all(jobs, folder, reserve):
    """ดึงงานที่ยังไม่มีใน cache - หยุดก่อนเริ่มถ้ายิงครบแล้วโควตาจะเหลือต่ำกว่า reserve (เผื่อ ⑦) คืน (จำนวนที่ยิง, งานที่พลาด)"""
    todo = [j for j in jobs if not (folder / f"{j[0]}_{j[1]}.json").exists()]
    if not todo:
        print(f"  ใช้ cache ของเดือนนี้ครบ {len(jobs)} รายการ ({folder}) - ไม่เสียโควตา", flush=True)
        return 0, []
    pool = ThrottleAwarePool()
    left, _ = pool.refresh_quota()
    print(f"  ต้องดึง {len(todo)} จาก {len(jobs)} รายการ | โควตา SerpAPI เหลือ {left}", flush=True)
    if left - len(todo) < reserve:
        raise SystemExit(f"❌ หยุด: ดึงครบแล้วโควตาจะเหลือ {left - len(todo)} ต่ำกว่าที่ต้องเผื่อให้ ⑦ ({reserve})")
    failed, done = [], [0]

    def run(job):
        if not fetch_one(pool, folder, *job):
            failed.append(job)
        done[0] += 1
        if done[0] % 50 == 0:
            print(f"  ... {done[0]}/{len(todo)}", flush=True)

    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(run, todo))
    left2, _ = pool.refresh_quota()
    print(f"  ดึงแล้ว {len(todo) - len(failed)} | พลาด {len(failed)} | โควตาเหลือ {left2}", flush=True)
    return len(todo), failed


def load_rows(jobs, folder, cats):
    """แถวคำค้นที่กำลังขึ้นทุกแถวของงานที่มีใน cache: {geo, cat_id, level, l1, l2, query, query_norm, value, extracted_value}"""
    meta = {c["cat_id"]: c for c in cats}
    rows = []
    for geo, cat_id in jobs:
        f = folder / f"{geo}_{cat_id}.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        m = meta[cat_id]
        for it in data.get("rising", []):
            if it.get("query"):
                rows.append({"geo": geo, "cat_id": cat_id, "level": m["level"], "l1": m["l1"], "l2": m["l2"],
                             "query": it["query"], "query_norm": norm(it["query"]), "value": str(it.get("value") or ""),
                             "extracted_value": it.get("extracted_value") or 0})
    return rows
