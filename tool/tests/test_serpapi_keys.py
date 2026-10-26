# -*- coding: utf-8 -*-
"""
Unit test ของ common/serpapi_keys.py (🆕 2026-10-12: SERPAPI_KEY หลายคีย์ + เปลี่ยนคีย์เมื่อโควตาหมด)
คีย์/ผลค้นหาปลอมทั้งหมด ไม่ยิง SerpAPI จริง

รัน: pytest main/tool/tests/test_serpapi_keys.py -v
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import serpapi_keys as sk  # noqa: E402

MULTILINE_ENV = '''OPENROUTER_API_KEY=x
# SERPAPI_KEY=old-commented-key-000
SERPAPI_KEY=[
"aaaa1111aaaa1111",
"bbbb2222bbbb2222",
"cccc3333cccc3333"
]

APIFY_API_KEY=y
'''


@pytest.mark.parametrize("text,expected", [
    ("abc123", ["abc123"]),
    ("abc, def", ["abc", "def"]),
    ('["abc", "def"]', ["abc", "def"]),
    ('[\n"abc",\n"def", \n]', ["abc", "def"]),          # จุลภาคเกินท้ายรายการ
    ('["abc", "abc", "def"]', ["abc", "def"]),          # ตัดตัวซ้ำ
    ("", []), (None, []),
])
def test_parse_keys(text, expected):
    assert sk.parse_keys(text) == expected


def test_read_env_block_multiline_ignores_commented_line(tmp_path):
    env = tmp_path / ".env"
    env.write_text(MULTILINE_ENV, encoding="utf-8")
    assert sk.parse_keys(sk.read_env_block(env)) == ["aaaa1111aaaa1111", "bbbb2222bbbb2222", "cccc3333cccc3333"]


def test_read_env_block_single_line(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# SERPAPI_KEY=zzz\nSERPAPI_KEY=single-key-1234\n", encoding="utf-8")
    assert sk.read_env_block(env) == "single-key-1234"


def test_load_keys_falls_back_to_file_when_dotenv_cut_the_list(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(MULTILINE_ENV, encoding="utf-8")
    monkeypatch.setenv("SERPAPI_KEY", "[")              # สิ่งที่ python-dotenv ได้จากรายการหลายบรรทัด
    assert len(sk.load_keys(env)) == 3
    monkeypatch.setenv("SERPAPI_KEY", "only-env-key-99")
    assert sk.load_keys(env) == ["only-env-key-99"]


@pytest.mark.parametrize("msg,rotate", [
    ("Your account has run out of searches.", True),
    ("Your searches for the month are exhausted. You can upgrade plans.", True),
    ("Invalid API key. Your API key should be here: https://serpapi.com/manage-api-key", True),
    ("Google Trends hasn't returned any results for this query.", False),
])
def test_should_rotate(msg, rotate):
    assert sk.should_rotate(msg) is rotate


def _fake_client(responses):
    """คีย์ -> ผลที่ได้ (เก็บลำดับคีย์ที่ถูกใช้ไว้ใน calls)"""
    calls = []

    def client(params):
        calls.append(params["api_key"])
        return responses[params["api_key"]]
    return client, calls


def test_search_rotates_on_quota_error_and_keeps_new_key():
    client, calls = _fake_client({"k1": {"error": "Your account has run out of searches."},
                                  "k2": {"interest_over_time": {"timeline_data": []}}})
    pool = sk.SerpApiKeyPool(["k1", "k2"], client=client)
    assert "interest_over_time" in pool.search({"engine": "google_trends", "q": "x", "api_key": "stale"})
    assert calls == ["k1", "k2"] and pool.current == "k2"
    pool.search({"q": "y"})
    assert calls[-1] == "k2"                            # ไม่กลับไปลองคีย์ที่หมดแล้ว


def test_search_passes_through_non_quota_error():
    client, calls = _fake_client({"k1": {"error": "Google Trends hasn't returned any results for this query."}})
    pool = sk.SerpApiKeyPool(["k1", "k2"], client=client)
    assert pool.search({"q": "x"})["error"].startswith("Google Trends")
    assert calls == ["k1"] and pool.current == "k1"


def test_search_all_keys_exhausted_returns_error_old_code_understands():
    client, _ = _fake_client({"k1": {"error": "run out of searches"}, "k2": {"error": "Invalid API key."}})
    pool = sk.SerpApiKeyPool(["k1", "k2"], client=client)
    err = pool.search({"q": "x"})["error"]
    # ⑦ (trend_final_v2_subset.serp_api) สลับไป pytrends เมื่อเจอคำใดคำหนึ่งนี้
    assert any(kw in err.lower() for kw in ["run out of searches", "quota", "exceeded", "limit"])
    assert pool.current is None


def test_refresh_quota_skips_empty_and_invalid_keys():
    info = {"k1": {"total_searches_left": 0}, "k2": {"error": "Invalid API key."},
            "k3": {"total_searches_left": 40}, "k4": {"plan_searches_left": 10}}

    def account(key):
        if key == "k5":
            raise OSError("network down")
        return info[key]
    pool = sk.SerpApiKeyPool(["k1", "k2", "k3", "k4", "k5"], account=account)
    total, per_key = pool.refresh_quota()
    assert total == 50
    assert list(per_key.values()) == [0, 0, 40, 10, None]
    assert pool.current == "k3"                          # ข้าม k1 (หมด) และ k2 (คีย์ผิด)
    assert "k5" not in pool.exhausted                     # เช็คไม่ได้ != หมด


def test_rotating_google_search_uses_module_pool(monkeypatch):
    client, calls = _fake_client({"k9": {"ok": True}})
    monkeypatch.setattr(sk, "POOL", sk.SerpApiKeyPool(["k9"], client=client))
    assert sk.RotatingGoogleSearch({"q": "x", "api_key": "ignored"}).get_dict() == {"ok": True}
    assert calls == ["k9"]


def test_real_search_sets_timeout_and_reports_network_failure_as_transient(monkeypatch):
    import requests
    import serpapi
    seen = []

    class Hanging:
        def __init__(self, params):
            self.timeout = 60000                  # ค่าเริ่มต้นของ library (= ~16 ชั่วโมงใน requests)

        def get_dict(self):
            seen.append(self.timeout)
            raise requests.exceptions.ReadTimeout("read timed out")

    monkeypatch.setattr(serpapi, "GoogleSearch", Hanging)
    result = sk._real_google_search({"q": "x"}, timeout=5, attempts=2)
    assert seen == [5, 5]                          # ใช้ timeout ของเรา + ลองใหม่ 1 ครั้ง
    assert "try again later" in result["error"] and not sk.should_rotate(result["error"])   # ไม่เปลี่ยนคีย์


def test_mask_never_shows_full_key():
    assert sk.mask("4bb0123456789abc6ec6") == "4bb0…6ec6"
    assert sk.mask("short") == "****"
