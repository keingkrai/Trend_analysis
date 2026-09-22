# -*- coding: utf-8 -*-
"""ตรวจว่า common/trend_final_subset.py และ common/trend_final_v2_subset.py (ส่วนที่คัดมาไว้ใน main/)
ใช้แทน trend_final.py / trend_final_v2.py ต้นฉบับได้เหมือนเดิม

- ไม่ต้องมีต้นฉบับ: import ได้, ไม่มีชื่อ global ที่หานิยามไม่เจอ (ตรวจระดับ bytecode ทุกฟังก์ชัน รวมกิ่งที่ไม่ค่อย
  ได้รัน), ส่วนที่ต่างจากต้นฉบับมีแค่บล็อกที่ติดป้าย ⚠️
- ต้องมีต้นฉบับ (หาที่ root ของโปรเจกต์ก่อน แล้วค่อยหาใน _archive/root_legacy_20260922/ ที่ย้ายไปเก็บเมื่อ
  2026-09-22 - ข้ามเองถ้าไม่มีทั้งคู่ เช่นหลัง clone): ทุกบล็อกตรงต้นฉบับทุกตัวอักษร และผลของฟังก์ชันเท่ากับ
  ต้นฉบับ (ใช้ client ปลอม ไม่เรียก LLM จริง)
- forecast_trend กับข้อมูล Google Trends จริงของรอบที่เก็บไว้ ใช้เวลา ~15 นาที - รันเมื่อตั้ง TREND_SUBSET_FULL=1
"""
import builtins
import dis
import importlib.util
import inspect
import json
import os
import re
import sys
import types
from pathlib import Path

import pytest

TOOL_DIR = Path(__file__).resolve().parents[1]
MAIN_DIR = TOOL_DIR.parent
COMMON = TOOL_DIR / "common"
# ที่ที่อาจมีต้นฉบับ (ตามลำดับ) - ย้ายจาก root ไปเก็บใน _archive/ เมื่อ 2026-09-22
ORIG_CANDIDATES = [MAIN_DIR.parent, MAIN_DIR.parent / "_archive" / "root_legacy_20260922"]
PAIRS = {"v1": ("trend_final_subset.py", "trend_final.py"),
         "v2": ("trend_final_v2_subset.py", "trend_final_v2.py")}
MARK = re.compile(r"^# \[(?P<src>[\w.]+) L(?P<a>\d+)-L(?P<b>\d+)\](?P<rest>.*)$")
REFERENCE_RUN = MAIN_DIR / "output" / "beauty_and_personal_care_20260916_082438"


def _original_path(tag):
    for d in ORIG_CANDIDATES:
        if (d / PAIRS[tag][1]).exists():
            return d / PAIRS[tag][1]
    return None


def _has_original(tag):
    return _original_path(tag) is not None


def _requires(tag):
    return pytest.mark.skipif(not _has_original(tag), reason=f"ไม่พบต้นฉบับ {PAIRS[tag][1]}")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _parse_blocks(path):
    blocks, cur = [], None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = MARK.match(line)
        if m:
            cur = {"src": m["src"], "a": int(m["a"]), "b": int(m["b"]), "deviated": "⚠️" in m["rest"], "lines": []}
            blocks.append(cur)
        elif cur is not None:
            cur["lines"].append(line)
    for b in blocks:
        while b["lines"] and not b["lines"][-1].strip():
            b["lines"].pop()
    return blocks


def _unresolved_globals(path, mod):
    """ชื่อ global ที่โค้ดในไฟล์อ้างถึงแต่ไม่มีนิยามในโมดูล (ไล่ทุก code object รวมฟังก์ชันซ้อน/คลาส)"""
    code = compile(Path(path).read_text(encoding="utf-8"), str(path), "exec")
    missing = {}

    def walk(co, qual):
        is_func = bool(co.co_flags & inspect.CO_OPTIMIZED)
        stores = {i.argval for i in dis.get_instructions(co) if i.opname in ("STORE_NAME", "STORE_GLOBAL")}
        for ins in dis.get_instructions(co):
            wanted = ins.opname == "LOAD_GLOBAL" if is_func else (qual != "<module>" and ins.opname == "LOAD_NAME")
            if wanted and ins.argval not in stores and ins.argval not in mod.__dict__ \
                    and not hasattr(builtins, ins.argval):
                missing.setdefault(ins.argval, set()).add(qual)
        for c in co.co_consts:
            if isinstance(c, types.CodeType):
                walk(c, c.co_qualname)

    walk(code, "<module>")
    return missing


@pytest.fixture(scope="module")
def mods(tmp_path_factory):
    """โหลดไฟล์ย่อยและต้นฉบับแบบสดๆ (ชื่อโมดูลไม่ชนกับที่ bootstrap โหลด) - cwd ชั่วคราว กันไปสร้าง memory/"""
    old_cwd = os.getcwd()
    os.chdir(tmp_path_factory.mktemp("cwd"))
    try:
        out = {}
        for tag, (sub, org) in PAIRS.items():
            out[f"sub_{tag}"] = _load(f"_subset_{tag}", COMMON / sub)
            if _has_original(tag):
                out[f"org_{tag}"] = _load(f"_original_{tag}", _original_path(tag))
        yield out
    finally:
        os.chdir(old_cwd)


class FakeClient:
    """แทน OpenAI/Bedrock client - จดทุกคำขอไว้ และตอบข้อความเดิมทุกครั้ง"""

    def __init__(self, content):
        self.content, self.calls = content, []
        self.chat = self.completions = self

    def create(self, **kw):
        self.calls.append(kw)
        msg = types.SimpleNamespace(content=self.content)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)],
                                     usage=types.SimpleNamespace(prompt_tokens=3, completion_tokens=2))


def _call(f, *a, **kw):
    try:
        return ("ok", f(*a, **kw))
    except Exception as e:  # ผลที่เป็น error ก็ต้องเหมือนกัน
        return ("err", type(e).__name__, str(e))


# ---------------------------------------------------------------------------------------------
# ไม่ต้องมีต้นฉบับ
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("tag", PAIRS)
def test_subset_has_no_unresolved_globals(tag, mods):
    assert _unresolved_globals(COMMON / PAIRS[tag][0], mods[f"sub_{tag}"]) == {}


@pytest.mark.parametrize("tag", PAIRS)
def test_only_tools_dir_is_changed_and_points_to_main(tag, mods):
    blocks = _parse_blocks(COMMON / PAIRS[tag][0])
    assert blocks and all(b["src"] == PAIRS[tag][1] for b in blocks)
    starts = [b["a"] for b in blocks]
    assert starts == sorted(starts), "บล็อกต้องเรียงตามลำดับเดิมในต้นฉบับ"
    deviated = [b for b in blocks if b["deviated"]]
    assert [b["lines"][0].split("=")[0].strip() for b in deviated] == ["_TOOLS_DIR"]
    sub = mods[f"sub_{tag}"]
    assert Path(sub._TOOLS_DIR) == MAIN_DIR
    assert Path(sub.env_path) == MAIN_DIR / ".env"


def test_bootstrap_uses_subsets_inside_main():
    from common import bootstrap
    assert Path(bootstrap.tf.__file__).resolve() == (COMMON / "trend_final_subset.py").resolve()
    assert bootstrap.PROJECT_ROOT == MAIN_DIR
    assert (MAIN_DIR / "config" / "rss_feeds.json").exists()


# ---------------------------------------------------------------------------------------------
# ต้องมีต้นฉบับ: ตรงตัวอักษร + ผลเท่ากัน
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("tag", PAIRS)
def test_blocks_match_original_verbatim(tag):
    if not _has_original(tag):
        pytest.skip(f"ไม่พบต้นฉบับ {PAIRS[tag][1]}")
    orig = _original_path(tag).read_text(encoding="utf-8").splitlines()
    for b in _parse_blocks(COMMON / PAIRS[tag][0]):
        if b["deviated"]:
            continue
        assert b["lines"] == orig[b["a"] - 1:b["b"]], f"บล็อก L{b['a']}-L{b['b']} ไม่ตรงต้นฉบับแล้ว"


JSON_CASES = ['{"a": 1}', '```json\n{"a": [1, 2]}\n```', 'ก่อน {"k": "v"} หลัง', '{"a": "he said \\"hi\\""}',
              '{"a": 1,}', "{'a': 1}", '[1, 2, 3]', '', 'not json', '{"n": {"x": null, "y": true}}',
              '{"a": +1}', '<think>คิด</think>{"a": 2}', '{"a": "บรรทัด1\nบรรทัด2"}', '{"a": [1, 2', None, 42]
TEXT_CASES = ["", None, "Home\nLogin\nMenu\n\nNiacinamide  reduces   dark spots.\n\n\n<div>ceramide</div>",
              "a" * 5000, "สวัสดี\t\tครีมกันแดด   SPF50\r\n\r\nCookie policy"]
PROMPTS = ["", "x" * 100, "ข้อความ" * 3000, "y" * 400000]


@pytest.mark.parametrize("tag", PAIRS)
def test_shared_helpers_match(tag, mods):
    if not _has_original(tag):
        pytest.skip("ไม่มีต้นฉบับ")
    s, o = mods[f"sub_{tag}"], mods[f"org_{tag}"]
    for case in JSON_CASES:
        assert _call(s.safe_json_parse, case) == _call(o.safe_json_parse, case), case
        assert _call(s.clean_json_string, case) == _call(o.clean_json_string, case), case
    for p in PROMPTS:
        assert _call(s.compute_max_tokens, p) == _call(o.compute_max_tokens, p)


@_requires("v1")
def test_v1_text_cache_and_feed_config_match(mods, tmp_path, monkeypatch):
    s, o = mods["sub_v1"], mods["org_v1"]
    for t in TEXT_CASES:
        assert _call(s.process_and_clean_content, t) == _call(o.process_and_clean_content, t)
    # ต้นฉบับอ่าน config/ ข้างไฟล์ตัวเอง ส่วนไฟล์ย่อยอ่าน main/config/ - ต้องได้รายการแหล่งข่าวเดียวกัน
    assert s.load_feed_config() == o.load_feed_config()
    data = {"https://x": {"title": "ครีม", "cleaned_text": "ข้อความ"}}
    for name, m in (("s", s), ("o", o)):
        d = tmp_path / name
        (d / "memory").mkdir(parents=True)
        monkeypatch.chdir(d)
        m.save_scrape_cache(data)
        assert m.load_scrape_cache() == data
    assert (tmp_path / "s/memory/scraped_cache.json").read_bytes() == \
        (tmp_path / "o/memory/scraped_cache.json").read_bytes()


@_requires("v1")
def test_v1_trend_report_prompt_and_result_match(mods):
    scraped = [{"title": f"บทความ {i}", "source": "Test", "link": f"https://e/{i}", "content": "ceramide " * 50}
               for i in range(3)]
    results = []
    for m in (mods["sub_v1"], mods["org_v1"]):
        m.client = FakeClient("# Report\n- ceramide (Ref 1)")
        results.append((_call(m.generate_trend_report_with_llm, "body care", scraped), m.client.calls))
    assert results[0] == results[1]


@_requires("v2")
def test_v2_rules_and_schemas_match(mods):
    import pandas as pd
    s, o = mods["sub_v2"], mods["org_v2"]
    for z in [None, -3, -0.81, -0.2, 0, 0.19, 0.2, 0.5, 0.8, 0.81, 2.5]:
        assert _call(s.compute_investment_signal, z) == _call(o.compute_investment_signal, z)
    for pct in [0, 10, 29.9, 30, 59.9, 60, 100, None]:
        assert _call(s._data_quality_label, pct) == _call(o._data_quality_label, pct)
    for q in ["Beauty in Thailand 2030", "global skincare", "ไทย ครีม", "Thai body wash", ""]:
        assert _call(s._infer_geo_from_query, q) == _call(o._infer_geo_from_query, q)
    mm = pd.DataFrame({"Keyword": ["a", "a", "b", "b", "c"], "cluster_id": [0, 0, 0, 0, 1],
                       "search_avg": [0, 5, 3, 0, 0]})
    rs, ro = _call(s.compute_data_quality_by_cluster, mm), _call(o.compute_data_quality_by_cluster, mm)
    assert rs[0] == ro[0] == "ok"
    pd.testing.assert_frame_equal(rs[1], ro[1])
    for cls in ("ClusterAnalysis", "MarketOverview", "ForecastAnalysis"):
        assert getattr(s, cls).model_json_schema() == getattr(o, cls).model_json_schema()


@_requires("v2")
def test_v2_stepic_and_report_match_on_reference_run(mods):
    """ใช้ผล STEPIC จริงที่ LLM ตอบไว้ในรอบอ้างอิง ป้อนเข้า analyze_trend/integrate_stepic (client ปลอม) และ
    generate_master_markdown_report - ทั้งผลลัพธ์และ prompt ที่ส่งออกไปต้องเหมือนต้นฉบับ"""
    if not (REFERENCE_RUN / "phase4_stepic_raw_analysis.json").exists():
        pytest.skip("ไม่มีรอบอ้างอิง")
    raw = json.loads((REFERENCE_RUN / "phase4_stepic_raw_analysis.json").read_text(encoding="utf-8"))
    insight = json.loads((REFERENCE_RUN / "phase4_stepic_final_insight.json").read_text(encoding="utf-8"))
    zd = json.loads((REFERENCE_RUN / "phase2_paper_social_z_delta_result.json").read_text(encoding="utf-8"))
    products = [{"Pillar": "p", "Key_Trends": "t", "Brand": "b", "Product Name": "n", "Sale Price (฿)": 1,
                 "Sold": 2, "Why It Fits": "-"}]
    out = []
    for m in (mods["sub_v2"], mods["org_v2"]):
        m.client = FakeClient(json.dumps(insight, ensure_ascii=False))
        a = _call(m.analyze_trend, "## 1. Summary\nceramide (Ref 1)", json.dumps(zd["master_report"][:3]),
                  "Global Beauty", "product context")
        b = _call(m.integrate_stepic, raw, "Global Beauty")
        c = _call(m.generate_master_markdown_report, "Global Beauty", "trend report", "context",
                  zd.get("llm_forecast_analysis"), products, insight, raw, None)
        calls = sorted(json.dumps(k, ensure_ascii=False, sort_keys=True, default=str) for k in m.client.calls)
        out.append((a, b, c, calls))
    assert out[0][2][0] == "ok"
    assert out[0] == out[1]


@_requires("v2")
@pytest.mark.skipif(os.getenv("TREND_SUBSET_FULL") != "1", reason="ช้า (~15 นาที) - ตั้ง TREND_SUBSET_FULL=1 เพื่อรัน")
def test_v2_forecast_matches_on_real_monthly_data(mods, tmp_path, monkeypatch):
    import pandas as pd
    monthly_path = REFERENCE_RUN / "serpapi_forecast_run" / "step5a_monthly_trends.xlsx"
    if not monthly_path.exists():
        pytest.skip("ไม่มีข้อมูลรายเดือนของรอบอ้างอิง")
    mapping = {}
    for fn in ["phase1_paper_stream_result.json", "phase2_social_stream_result.json", "phase2_news_stream_result.json"]:
        for row in json.loads((REFERENCE_RUN / fn).read_text(encoding="utf-8"))["keywords"]:
            kws = [k.strip().lower() for k in str(row.get("Search_Keywords", "")).split(",") if k.strip()]
            if kws:
                mapping[row["Trend Name"]] = kws
    monthly = pd.read_excel(monthly_path)
    canned = json.dumps({"market_overview": {"query": "q"},
                         "cluster_analysis": [{"cluster_id": i} for i in range(len(mapping))]})
    monkeypatch.chdir(tmp_path)
    res = {}
    for name in ("sub_v2", "org_v2"):
        m = mods[name]
        m.client = FakeClient(canned)
        out_dir = tmp_path / name
        out_dir.mkdir()
        res[name] = (m.forecast_trend(str(out_dir), mapping, "Global Beauty and Personal Care Trends",
                                      monthly_df_override=monthly, horizon=36), m.client.calls, out_dir)
    (rs, cs, ds), (ro, co, do) = res["sub_v2"], res["org_v2"]
    assert sorted(rs[0]) == sorted(ro[0])
    pd.testing.assert_frame_equal(rs[1], ro[1])
    assert rs[2] == ro[2] and rs[3] == ro[3]
    assert [c["messages"] for c in cs] == [c["messages"] for c in co]
    for f in ("step5a_monthly_trends.xlsx", "step5b_df_keyword_processed.xlsx", "step5c_df_cluster_forecast.xlsx"):
        pd.testing.assert_frame_equal(pd.read_excel(ds / f), pd.read_excel(do / f))
