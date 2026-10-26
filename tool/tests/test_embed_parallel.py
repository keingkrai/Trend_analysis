# -*- coding: utf-8 -*-
"""
เทส embed_all_products() แบบยิงขนาน (validate_at_scale_nvidia.py, 2026-10-11) - ไม่เรียก API: get_embedding ถูกแทนด้วยตัวปลอม
และ checkpoint เขียนลงโฟลเดอร์ชั่วคราว

รัน: pytest main/tool/tests/test_embed_parallel.py -v
"""
import pickle
import sys
import threading
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

TOOL_DIR = Path(__file__).resolve().parent.parent
for _p in (TOOL_DIR, TOOL_DIR / "phase3_supply_layer", TOOL_DIR.parent):
    sys.path.insert(0, str(_p))

import validate_at_scale_nvidia as vsn  # noqa: E402


def _df(names):
    return pd.DataFrame({"product_name": names}, index=[10 + i for i in range(len(names))])   # index ไม่ใช่ 0..n (เหมือน load_catalog ที่กรองแถว)


@pytest.fixture
def fake(monkeypatch, tmp_path):
    """แทน get_embedding ด้วยเวกเตอร์ที่คำนวณจากข้อความ + นับครั้งที่เรียก (ปลอดภัยต่อ thread)"""
    calls, lock = [], threading.Lock()
    monkeypatch.setattr(vsn, "CHECKPOINT_PATH", tmp_path / "ckpt.pkl")
    state = {"fail": set()}

    def get_embedding(text, input_type, max_retries=5):
        with lock:
            calls.append((text, input_type))
        if any(bad in text for bad in state["fail"]):
            raise RuntimeError("fake embedding failure")
        return np.array([float(len(text)), float(sum(map(ord, text)) % 97)])

    monkeypatch.setattr(vsn, "get_embedding", get_embedding)
    return type("Fake", (), {"calls": calls, "state": state, "path": tmp_path / "ckpt.pkl"})


def test_embeds_every_row_in_parallel_and_keys_the_result_by_df_index(fake):
    df = _df([f"product {i}" for i in range(40)])
    out = vsn.embed_all_products(df, workers=4)
    assert list(out) == list(df.index) and len(fake.calls) == 40
    assert all(t == "passage" for _, t in fake.calls)
    for idx in df.index:   # เวกเตอร์ของแถวนั้นมาจากข้อความของแถวนั้นจริง (ไม่สลับแถวตอนขนาน)
        assert out[idx][0] == float(len(vsn.build_product_text(df.loc[idx])))
    assert len(pickle.loads(fake.path.read_bytes())) == 40


def test_identical_content_is_embedded_once(fake):
    df = _df(["same", "other", "same", "same"])
    out = vsn.embed_all_products(df, workers=3)
    assert len(fake.calls) == 2
    assert np.array_equal(out[10], out[12]) and np.array_equal(out[10], out[13])


def test_second_run_uses_the_cache_and_only_new_rows_are_embedded(fake):
    vsn.embed_all_products(_df(["a", "b", "c"]), workers=2)
    fake.calls.clear()
    vsn.embed_all_products(_df(["a", "b", "c"]), workers=2)
    assert fake.calls == []                                   # ครบแล้ว ไม่ยิงเลย
    out = vsn.embed_all_products(_df(["c", "d", "a"]), workers=2)   # เรียงใหม่ + แถวใหม่ 1 ชิ้น
    assert [t for t, _ in fake.calls] == ["d"] and len(out) == 3


def test_failed_items_are_reported_but_successes_are_saved(fake):
    fake.state["fail"] = {"BAD"}
    df = _df(["good 1", "BAD 1", "good 2", "BAD 2", "good 3"])
    with pytest.raises(RuntimeError, match="2/5"):
        vsn.embed_all_products(df, workers=2)
    saved = pickle.loads(fake.path.read_bytes())
    assert len(saved) == 3                                    # 3 ชิ้นที่สำเร็จอยู่ใน checkpoint แล้ว
    fake.state["fail"] = set()
    fake.calls.clear()
    out = vsn.embed_all_products(df, workers=2)               # รันซ้ำ: ทำเฉพาะ 2 ชิ้นที่ค้าง
    assert sorted(t for t, _ in fake.calls) == ["BAD 1", "BAD 2"] and len(out) == 5


def test_aborts_after_too_many_failures_without_trying_everything(fake, monkeypatch):
    monkeypatch.setattr(vsn, "EMBED_MAX_FAILURES", 3)
    fake.state["fail"] = {"item"}
    with pytest.raises(RuntimeError, match="หยุดก่อน"):
        vsn.embed_all_products(_df([f"item {i}" for i in range(200)]), workers=2)
    assert len(fake.calls) < 200                              # ไม่ยิงจนครบทั้งแคตตาล็อก


def test_checkpoint_is_written_atomically_and_leaves_no_temp_file(fake):
    vsn.save_checkpoint({"h": np.array([1.0, 2.0])})
    assert fake.path.exists() and not fake.path.with_name(fake.path.name + ".tmp").exists()
    assert list(pickle.loads(fake.path.read_bytes())) == ["h"]
