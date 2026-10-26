# -*- coding: utf-8 -*-
"""
SerpAPI หลายคีย์ — อ่านคีย์ทั้งหมดจาก SERPAPI_KEY ใน main/.env แล้วสลับไปคีย์ถัดไปเมื่อคีย์ปัจจุบันโควตาหมด (🆕 2026-10-12)

รูปแบบ SERPAPI_KEY ที่อ่านได้:
    SERPAPI_KEY=abc                      คีย์เดียว (แบบเดิม)
    SERPAPI_KEY=abc,def                  คั่นด้วยจุลภาค
    SERPAPI_KEY=["abc", "def"]           JSON บรรทัดเดียว
    SERPAPI_KEY=[                        JSON หลายบรรทัด (แบบที่เจ้าของงานใช้) - python-dotenv อ่านแบบนี้ไม่ได้ (ได้แค่ "[")
    "abc",                               จึงอ่านบล็อกนี้จากไฟล์ .env เอง (บรรทัดที่ขึ้นต้นด้วย # ไม่นับ)
    "def"
    ]

สลับคีย์เมื่อ: ผลมี "error" ที่บอกว่าโควตาหมด/เกินลิมิต/คีย์ใช้ไม่ได้ (should_rotate) - error อื่น (เช่น ไม่มีผลค้นหา) ส่งกลับตามเดิม
คีย์หมดทุกตัว: คืน {"error": "... run out of searches ..."} - โค้ดเดิมของ ⑦ เห็นคำนี้แล้วสลับไป pytrends เหมือนตอนโควตาหมด
ล็อกแสดงคีย์แบบปิดบัง (4 ตัวแรก…4 ตัวท้าย) เสมอ

ใช้:
    from common.serpapi_keys import POOL
    POOL.search({"engine": "google", "q": "..."})      # api_key ใส่ให้เอง
    POOL.refresh_quota()                               # เช็คโควตาทุกคีย์ (account.json ฟรี ไม่เสีย search) + ข้ามคีย์ที่หมด
⑦ ใช้ผ่าน trend_final_v2_subset (GoogleSearch ในไฟล์นั้นชี้มาที่ RotatingGoogleSearch ของไฟล์นี้)
"""
import json
import os
import re
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"   # main/.env
ENV_NAME = "SERPAPI_KEY"
ROTATE_MARKERS = ("run out of searches", "out of searches", "searches for the month", "quota", "exceeded",
                  "limit", "invalid api key", "api key is invalid", "account is disabled", "suspended")


def mask(key):
    """คีย์สำหรับพิมพ์ล็อก: 4 ตัวแรก…4 ตัวท้าย"""
    return f"{key[:4]}…{key[-4:]}" if key and len(key) > 8 else "****"


def parse_keys(text):
    """ข้อความค่าของ SERPAPI_KEY -> รายการคีย์ (ตัดช่องว่าง/เครื่องหมายคำพูด/ตัวซ้ำ เรียงตามเดิม)"""
    if not text:
        return []
    text = text.strip()
    if text.startswith("["):
        try:
            items = json.loads(re.sub(r",\s*]", "]", text))   # ยอมให้มีจุลภาคเกินท้ายรายการ
        except json.JSONDecodeError:
            items = re.findall(r"[\"']([^\"']+)[\"']", text)
    else:
        items = re.split(r"[,\s]+", text)
    keys = []
    for k in items:
        k = str(k).strip().strip("\"'")
        if k and k not in keys:
            keys.append(k)
    return keys


def read_env_block(env_path=ENV_PATH, name=ENV_NAME):
    """ค่าดิบของ name จากไฟล์ .env (รองรับรายการ [...] หลายบรรทัด) - บรรทัดที่ comment ไว้ไม่นับ, ไม่เจอ = None"""
    path = Path(env_path)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"(?m)^[ \t]*{name}[ \t]*=[ \t]*(\[[^\]]*\])", text)
    if m:
        return m.group(1)
    m = re.search(rf"(?m)^[ \t]*{name}[ \t]*=[ \t]*(.+)$", text)
    return m.group(1).strip() if m else None


def load_keys(env_path=ENV_PATH, name=ENV_NAME):
    """คีย์ทั้งหมด: ค่าจาก environment ถ้าอ่านครบ ไม่งั้น (ไม่มี / รายการหลายบรรทัดที่ dotenv ตัดเหลือ "[") อ่านจากไฟล์ .env"""
    value = (os.environ.get(name) or "").strip()
    if not value or (value.startswith("[") and not value.endswith("]")):
        value = read_env_block(env_path, name) or ""
    return parse_keys(value)


def should_rotate(error_message):
    """error ของ SerpAPI แบบนี้ = คีย์นี้ใช้ต่อไม่ได้ (โควตาหมด/เกินลิมิต/คีย์ผิด) ให้เปลี่ยนคีย์"""
    msg = str(error_message).lower()
    return any(marker in msg for marker in ROTATE_MARKERS)


REQUEST_TIMEOUT = 60   # วินาที


def _real_google_search(params, timeout=REQUEST_TIMEOUT, attempts=2):
    """ค้นจริง 1 ครั้ง (ลองใหม่เมื่อเน็ต/เซิร์ฟเวอร์ขัดข้อง) - ล้มทุกครั้ง = {"error": "... try again later"}
    (ผู้เรียกถือว่าเป็น error ชั่วคราว ไม่ cache และไม่เปลี่ยนคีย์)
    ทำไมต้องตั้ง timeout เอง: serpapi.GoogleSearch ตั้ง timeout=60000 (ตั้งใจเป็นมิลลิวินาที แต่ requests ตีความเป็นวินาที
    = รอได้ ~16 ชั่วโมง) - เจอจริง 2026-10-12: คำค้นข่าวค้างกว่า 17 นาทีโดยไม่มีผลออกมาเลย"""
    import requests
    from serpapi import GoogleSearch
    last = None
    for _ in range(attempts):
        search = GoogleSearch(params)
        search.timeout = timeout
        try:
            return search.get_dict()
        except requests.exceptions.RequestException as e:
            last = e
    return {"error": f"SerpAPI request failed ({type(last).__name__}) - try again later"}


def _account_info(key, timeout=15):
    with urllib.request.urlopen(f"https://serpapi.com/account.json?api_key={key}", timeout=timeout) as r:
        return json.load(r)


class SerpApiKeyPool:
    """คีย์หลายตัวเรียงตามลำดับใน .env - ใช้ตัวปัจจุบันจนกว่าจะหมด แล้วไปตัวถัดไป (ไม่วนกลับไปตัวที่หมดแล้ว)"""

    def __init__(self, keys=None, loader=load_keys, client=_real_google_search, account=_account_info):
        self._keys = list(keys) if keys is not None else None
        self._loader, self._client, self._account = loader, client, account
        self.index = 0
        self.exhausted = set()

    @property
    def keys(self):
        if self._keys is None:          # อ่านตอนใช้ครั้งแรก (หลัง load_dotenv ของโมดูลที่เรียกแล้ว)
            self._keys = self._loader()
        return self._keys

    @property
    def current(self):
        while self.index < len(self.keys) and self.keys[self.index] in self.exhausted:
            self.index += 1
        return self.keys[self.index] if self.index < len(self.keys) else None

    def rotate(self, reason=""):
        """ทิ้งคีย์ปัจจุบัน ไปตัวถัดไป - คืนคีย์ใหม่ (None = หมดทุกตัว)"""
        old = self.current
        if old is None:
            return None
        self.exhausted.add(old)
        new = self.current
        left = len(self.keys) - len(self.exhausted)
        print(f"  🔁 SerpAPI คีย์ {mask(old)} ใช้ต่อไม่ได้ ({str(reason)[:80]}) -> "
              + (f"เปลี่ยนเป็น {mask(new)} (เหลือ {left} คีย์)" if new else "หมดทุกคีย์แล้ว"))
        return new

    def search(self, params):
        """ค้นด้วยคีย์ปัจจุบัน (api_key ใน params ถูกแทนที่) โควตาหมด -> เปลี่ยนคีย์แล้วลองใหม่ จนสำเร็จหรือหมดทุกคีย์"""
        while True:
            key = self.current
            if key is None:
                return {"error": f"SerpAPI: all {len(self.keys)} keys have run out of searches or are unusable"}
            result = self._client({**params, "api_key": key})
            if isinstance(result, dict) and "error" in result and should_rotate(result["error"]):
                self.rotate(result["error"])
                continue
            return result

    def refresh_quota(self):
        """โควตาที่เหลือของทุกคีย์ (account.json ไม่เสีย search) - คีย์ที่เหลือ 0 หรือเช็คไม่ได้เพราะคีย์ผิด ถูกข้าม
        คืน (รวมที่เหลือ, {"#ลำดับ คีย์ปิดบัง": ที่เหลือ หรือ None ถ้าเช็คไม่ได้})"""
        total, per_key = 0, {}
        for i, key in enumerate(self.keys, 1):
            label = f"#{i} {mask(key)}"
            if key in self.exhausted:
                per_key[label] = 0
                continue
            try:
                info = self._account(key)
            except Exception as e:             # เน็ต/เซิร์ฟเวอร์มีปัญหา - ยังไม่ทิ้งคีย์ ให้ search ตัดสินเอง
                per_key[label] = None
                print(f"  ⚠️ เช็คโควตาคีย์ {label} ไม่ได้: {e}")
                continue
            if "error" in info:
                per_key[label] = 0
                self.exhausted.add(key)
                continue
            left = info.get("total_searches_left", info.get("plan_searches_left")) or 0
            per_key[label] = left
            total += left
            if left <= 0:
                self.exhausted.add(key)
        return total, per_key


class RotatingGoogleSearch:
    """ใช้แทน serpapi.GoogleSearch ได้ตรงตัว (GoogleSearch(params).get_dict()) แต่ใช้คีย์จาก POOL และเปลี่ยนคีย์เองเมื่อหมด"""

    def __init__(self, params_dict):
        self.params_dict = dict(params_dict)

    def get_dict(self):
        return POOL.search(self.params_dict)


POOL = SerpApiKeyPool()
