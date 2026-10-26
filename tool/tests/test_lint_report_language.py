# -*- coding: utf-8 -*-
"""
เทสของตัวตรวจภาษารายงาน (🆕 2026-10-12 ขั้น E) - lint_report_language.py
ไม่ยิง API / ไม่ต้องมี PDF จริง (สร้างโฟลเดอร์รอบจำลองใน tmp_path)

รัน: pytest main/tool/tests/test_lint_report_language.py -v
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase6_pdf_report"))

import lint_report_language as lint  # noqa: E402

ALLOW = lint.BASE_ALLOW | {"mizumi", "tint"}


def _rules(findings):
    return {(f.rule, f.level) for f in findings}


# ---------------------------------------------------------------------------
# check_text
# ---------------------------------------------------------------------------
def test_banned_term_is_error_outside_appendix_but_ignored_in_appendix():
    text = "Growth is accelerating to 30% YoY with strong momentum"
    assert ("banned-term", lint.ERROR) in _rules(lint.check_text("s", "k", "en", text, ALLOW))
    assert not lint.check_text("s", "method_1", "en", text, ALLOW, appendix=True)


def test_pipeline_leak_is_error_even_in_appendix():
    for leak in ("ดูผลใน ⑬ ของรอบนี้", "run --category-fit-only first", "see run_brand_coverage.py", "ราคา None บาท", "{brand} is leading"):
        found = lint.check_text("s", "k", "th" if "ดู" in leak or "ราคา" in leak else "en", leak, ALLOW, appendix=True)
        assert ("pipeline-leak", lint.ERROR) in _rules(found), leak


def test_template_placeholders_are_fine_in_static_strings_only():
    text = "Top {n} products for {brand}"
    assert not lint.check_text("s", "k", "en", text, ALLOW, template=True)
    assert ("pipeline-leak", lint.ERROR) in _rules(lint.check_text("s", "k", "en", text, ALLOW))


def test_long_english_sentence_is_warning_and_short_ones_pass():
    short = "Each trend has its own page. Products are compared inside one category."
    assert not lint.check_text("s", "k", "en", short, ALLOW)
    long_text = " ".join(["word"] * (lint.EN_MAX_WORDS + 5)) + "."
    found = lint.check_text("s", "k", "en", long_text, ALLOW)
    assert ("long-sentence", lint.WARN) in _rules(found)
    # แบ่งเป็นสองประโยคแล้วผ่าน
    half = " ".join(["word"] * 20)
    assert not lint.check_text("s", "k", "en", f"{half}. {half}.", ALLOW)


def test_long_thai_run_without_spaces_is_warning():
    long_th = "ก" * (lint.TH_MAX_CLAUSE_CHARS + 10)
    assert ("long-sentence", lint.WARN) in _rules(lint.check_text("s", "k", "th", long_th, ALLOW))
    ok = " ".join(["ก" * 40] * 5)
    assert not lint.check_text("s", "k", "th", ok, ALLOW)


def test_english_general_words_in_thai_text_warn_but_names_and_ingredients_pass():
    # ชื่อ (ตัวใหญ่) / ตัวย่อ / ส่วนผสมในรายการ / ชื่อที่ส่งเข้า allowlist ของรอบ ไม่ถูกเตือน
    ok = "เซรั่ม Mizumi ผสม retinol และ niacinamide ค่า SPF50 สำหรับผิว Sensitive"
    assert not lint.check_text("s", "k", "th", ok, ALLOW)
    found = lint.check_text("s", "k", "th", "ผู้ใช้ต้องการ real-time guidance จากผลิตภัณฑ์", ALLOW)
    assert ("english-word", lint.WARN) in _rules(found)
    assert "guidance" in found[0].detail
    # ข้อความอังกฤษล้วนไม่ถูกตรวจกติกานี้
    assert not [f for f in lint.check_text("s", "k", "en", "Real-time guidance for skin", ALLOW) if f.rule == "english-word"]


def test_hyphenated_ingredient_with_single_letter_part_passes():
    assert not lint.check_text("s", "k", "th", "ใช้ dendritic poly-L-lysine ช่วยคงตัว", ALLOW)


def test_is_appendix_key_prefixes():
    for key in ("method_1", "m_title", "notes_1", "run_id", "how_to_use"):
        assert lint.is_appendix_key(key), key
    for key in ("cat_note", "headline", "briefing_text"):
        assert not lint.is_appendix_key(key), key


# ---------------------------------------------------------------------------
# แหล่งข้อความของรอบ
# ---------------------------------------------------------------------------
def _make_run(tmp_path, en_items=None, th_items=None, brand_reason=None):
    run = tmp_path / "beauty_run"
    run.mkdir()
    (run / lint.HIGHLIGHTS_FILE).write_text(json.dumps({"profiles": [{"trend": "Glow Trend", "key_ingredients": "retinol"}]}),
                                            encoding="utf-8")
    en = {"items": {"Glow Trend": {"output": {"headline": "Skin glows", "insight": "Strong momentum here"}},
                    "Old Trend": {"output": {"headline": "Old YoY text"}}} if en_items is None else en_items}
    (run / "phase6_report_enrichment.json").write_text(json.dumps(en), encoding="utf-8")
    th = {"items": th_items or {"Glow Trend": {"output": {"headline": "ผิวสว่างใส", "trend": "ใช้ SKU จำนวนมาก"}}}}
    (run / "phase6_report_enrichment_TH.json").write_text(json.dumps(th, ensure_ascii=False), encoding="utf-8")
    ctx = {"rows": [{"name": "Glow Trend", "products": [{"reason": brand_reason or "Matches the goal of fading spots"}]}]}
    (run / "phase6_brand_context_Mizumi.json").write_text(json.dumps(ctx), encoding="utf-8")
    return run


def test_run_texts_only_include_trends_of_the_run_and_flag_banned(tmp_path):
    run = _make_run(tmp_path)
    findings = lint.lint_run_texts(run)
    errors = [f for f in findings if f.level == lint.ERROR]
    # momentum (EN) + SKU (TH) ของเทรนด์ในรอบ; "Old Trend" ที่ค้างใน cache ไม่นับ
    assert {(f.lang, f.detail) for f in errors} == {("en", "momentum"), ("th", "SKU")}
    assert not any("Old" in f.where for f in findings)


def test_clean_run_has_no_findings(tmp_path):
    run = _make_run(tmp_path, en_items={"Glow Trend": {"output": {"headline": "Skin glows", "insight": "Steady demand"}}},
                    th_items={"Glow Trend": {"output": {"headline": "ผิวสว่างใส", "trend": "ใช้สินค้าจำนวนมาก"}}})
    assert lint.lint_run_texts(run) == []


def test_name_keys_are_exempt_in_report_blocks(tmp_path):
    th_items = {"Glow Trend": {"output": {"headline": "ผิวสว่างใส"}}}
    run = _make_run(tmp_path, en_items={"Glow Trend": {"output": {"headline": "ok"}}}, th_items=th_items)
    report = {"report": {"takeaway": {"output": {"mega_trend_name": "The Clinical Bio-Convergence guidance", "core_concept": "ปลอดภัย"}}}}
    (run / "phase6_report_enrichment_TH.json").write_text(
        json.dumps({"items": th_items, **report}, ensure_ascii=False), encoding="utf-8")
    assert lint.lint_run_texts(run) == []


def test_static_strings_have_no_errors():
    """ข้อความตายตัวทั้งหมดต้องผ่าน (ภาคผนวกได้รับยกเว้นคำต้องห้าม) - กันไม่ให้การแก้ภายหลังทำให้ศัพท์เทคนิคกลับมา"""
    errors = [f for f in lint.lint_static_strings() if f.level == lint.ERROR]
    assert not errors, [(f.source, f.where, f.detail) for f in errors]


def test_main_exit_code_and_report(tmp_path, capsys):
    run = _make_run(tmp_path)
    md = tmp_path / "lint.md"
    code = lint.main(["--root", str(tmp_path), "--run", run.name, "--no-pdf", "--no-static", "--md", str(md)])
    assert code == 1   # มี ERROR
    assert "momentum" in md.read_text(encoding="utf-8")
    parent = tmp_path / "clean_parent"
    parent.mkdir()
    clean = _make_run(parent, en_items={"Glow Trend": {"output": {"headline": "ok"}}},
                      th_items={"Glow Trend": {"output": {"headline": "ผิวสว่างใส"}}})
    assert lint.main(["--root", str(parent), "--run", clean.name, "--no-pdf", "--no-static"]) == 0


def test_pdf_name_filter_only_matches_pipeline_outputs():
    ok = ["phase6_trend_report.pdf", "phase6_trend_report_TH.pdf", "phase6_brand_report_Eucerin.pdf",
          "phase6_brand_report_Mizumi_TH.pdf", "phase6_brand_category_report_Srichand.pdf"]
    bad = ["phase6_trend_reportaa.pdf", "phase6_trend_reportdd.pdf", "phase6_growth_method.pdf", "phase6_trend_report_old.pdf"]
    assert all(lint.PIPELINE_PDF_RE.match(n) for n in ok)
    assert not any(lint.PIPELINE_PDF_RE.match(n) for n in bad)


def test_appendix_page_detection():
    assert lint.is_appendix_page("ภาคผนวก | วิธีการ\n1. การรวบรวมหลักฐาน")
    assert lint.is_appendix_page("Appendix | Methodology 1. Evidence")
    assert not lint.is_appendix_page("Trend 3 Glow ...\nAppendix is mentioned later")
