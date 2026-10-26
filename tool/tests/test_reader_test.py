# -*- coding: utf-8 -*-
"""
เทสของชุดทดสอบผู้อ่านจริง (🆕 2026-10-12 ขั้น E) - reader_test.py
ไม่ยิง API; ตรวจว่าคลังคำถามยังตรงกับตารางข้อความจริงของรายงาน และตัวตรวจคำตอบให้ผลถูกต้อง

รัน: pytest main/tool/tests/test_reader_test.py -v
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase6_pdf_report"))

import lint_report_language as lint  # noqa: E402
import reader_test as rt  # noqa: E402

ALL_IDS = [q["id"] for q in rt.QUESTIONS]


# ---------------------------------------------------------------------------
# คลังคำถาม
# ---------------------------------------------------------------------------
def test_question_ids_unique_and_prefix_matches_report():
    assert len(ALL_IDS) == len(set(ALL_IDS))
    for q in rt.QUESTIONS:
        assert q["id"][0] == rt.REPORT_PREFIX[q["report"]], q["id"]
    # ทุกรายงานมีคำถามอย่างน้อย 5 ข้อ
    for rep in rt.REPORT_PREFIX:
        assert len(rt.select_questions(rep)) >= 5, rep


@pytest.mark.parametrize("lang", ["th", "en"])
def test_every_question_has_four_options_and_correct_at_slot(lang):
    for q in rt.QUESTIONS:
        opts = rt.option_list(q, lang)
        assert [l for l, _ in opts] == list("abcd"), q["id"]
        texts = [t for _, t in opts]
        assert len(set(texts)) == 4, q["id"]
        assert dict(opts)[rt.answer_letter(q)] == q["correct"][lang]
    # คำตอบถูกกระจายหลายตำแหน่ง (ไม่ใช่ b ทุกข้อ)
    assert len({rt.answer_letter(q) for q in rt.QUESTIONS}) == 4


@pytest.mark.parametrize("lang", ["th", "en"])
def test_quoted_report_text_and_rewrite_keys_exist(lang):
    """ข้อความที่คำถามอ้าง/คีย์ที่ให้แก้ ต้องมีอยู่จริงในตารางข้อความ - กันเทสพังเงียบๆ เมื่อมีคนเปลี่ยนชื่อคีย์"""
    for q in rt.QUESTIONS:
        for name, (table, key, fmt) in (q.get("quotes") or {}).items():
            assert rt.text_of(table, key, lang, **fmt), (q["id"], name)
        assert rt.stem_text(q, lang)
        for ref in q["rewrite"]:
            assert rt.ref_text(rt.effective_ref(ref, lang), lang), (q["id"], ref)


def test_quote_in_stem_is_filled_with_real_report_wording():
    t3 = next(q for q in rt.QUESTIONS if q["id"] == "T3")
    assert "ตรงเทรนด์อันดับ 3 จากทั้งร้าน" in rt.stem_text(t3, "th")
    assert "#3 match in the whole store" in rt.stem_text(t3, "en")
    b2 = next(q for q in rt.QUESTIONS if q["id"] == "B2")
    assert "ติด 5% แรก (อันดับ 12)" in rt.stem_text(b2, "th")


def test_unit_price_wording_overrides_base_text():
    # รายงานปัจจุบันใช้ราคาต่อปริมาณ - คำถามต้องอ้างชื่อกลุ่มของชุดนั้น ไม่ใช่ “ราคาต่ำ”
    t5 = next(q for q in rt.QUESTIONS if q["id"] == "T5")
    assert "ราคาต่อปริมาณต่ำ" in rt.stem_text(t5, "th")
    assert rt.effective_ref("brand.vs_note", "th") == "unit.vs_note"
    assert rt.effective_ref("brand.pct_val", "th") == "brand.pct_val"


def test_reader_test_texts_follow_the_language_rules():
    """คำถาม/ตัวเลือกเองต้องเป็นภาษาง่าย - ไม่มีคำต้องห้าม (ใช้กติกาเดียวกับตัวตรวจภาษา)"""
    for q in rt.QUESTIONS:
        for lang in ("th", "en"):
            texts = [rt.stem_text(q, lang), q["correct"][lang]] + [w[lang] for w in q["wrong"]]
            for t in texts:
                found = lint.check_text("reader_test", q["id"], lang, t, lint.BASE_ALLOW, prose=False)
                assert not found, (q["id"], lang, [f.detail for f in found])


# ---------------------------------------------------------------------------
# เอกสาร
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("lang", ["th", "en"])
def test_sheet_has_no_answers_and_key_marks_correct(lang):
    sheet = rt.render_sheet(lang)
    key = rt.render_key(lang)
    assert "✅" not in sheet
    for q in rt.QUESTIONS:
        assert f"**{q['id']}." in sheet
    assert key.count("✅") == len(rt.QUESTIONS)
    assert rt.answers_template().strip().split(",")[:2] == ["reader_id", "role"]
    assert rt.answers_template().strip().split(",")[2:-1] == ALL_IDS


def test_report_filter_limits_questions():
    sheet = rt.render_sheet("th", "brand")
    assert "**B1." in sheet and "**T1." not in sheet and "**C1." not in sheet
    assert rt.answers_template("category").strip().split(",")[2:-1] == [q for q in ALL_IDS if q.startswith("C")]


# ---------------------------------------------------------------------------
# ตรวจคำตอบ
# ---------------------------------------------------------------------------
def _rows(per_reader):
    """per_reader = [{qid: letter}] -> rows ในรูปที่ read_answers คืน"""
    return [{"reader_id": f"r{i}", "role": "", "answers": a, "notes": ""} for i, a in enumerate(per_reader, 1)]


def _all_right():
    return {q["id"]: rt.answer_letter(q) for q in rt.QUESTIONS}


def test_score_all_correct_passes():
    res = rt.score(_rows([_all_right()] * 3))
    assert res["verdict"]["overall"] == 1.0 and res["verdict"]["pass"]
    assert res["failing"] == [] and res["rewrite_keys"] == []


def test_score_failing_question_lists_rewrite_keys_and_top_wrong_option():
    wrong = rt.answer_letter(rt.QUESTIONS[0])
    wrong = next(l for l in "abcd" if l != wrong)
    readers = []
    for i in range(4):
        a = _all_right()
        if i < 3:   # T1 ถูกแค่ 1 ใน 4 = 25%
            a["T1"] = wrong
        readers.append(a)
    res = rt.score(_rows(readers))
    assert [p["id"] for p in res["failing"]] == ["T1"]
    assert res["failing"][0]["top_wrong"]["letter"] == wrong and res["failing"][0]["top_wrong"]["count"] == 3
    assert "trend.t5_note" in res["rewrite_keys"]
    # ตอบถูกรวมยังเกิน 80% แต่มีข้อไม่ผ่าน -> ไม่ผ่าน
    assert res["verdict"]["overall_pass"] and not res["verdict"]["pass"]


def test_unsure_counts_as_not_correct_and_is_reported():
    a = _all_right()
    a["B3"] = rt.UNSURE
    res = rt.score(_rows([a, a, _all_right()]), "brand")
    b3 = next(p for p in res["questions"] if p["id"] == "B3")
    assert b3["right"] == 1 and b3["unsure"] == 2 and b3["top_wrong"] is None and not b3["pass"]


def test_too_few_readers_cannot_pass_and_missing_answers_not_counted():
    res = rt.score(_rows([_all_right(), _all_right()]))
    assert not res["verdict"]["enough_readers"] and not res["verdict"]["pass"]
    # ผู้อ่านไม่ตอบข้อหนึ่ง - นับเฉพาะคนที่ตอบ
    part = _all_right()
    del part["C5"]
    res = rt.score(_rows([part, _all_right(), _all_right()]))
    c5 = next(p for p in res["questions"] if p["id"] == "C5")
    assert c5["n"] == 2 and c5["pct"] == 1.0


def test_read_answers_csv_and_markdown_result(tmp_path):
    csv_path = tmp_path / "answers.csv"
    header = ",".join(["reader_id", "role"] + ALL_IDS + ["notes"])
    good = ",".join(["A", "การตลาด"] + [rt.answer_letter(q) for q in rt.QUESTIONS] + ["ข้อ T2 งง"])
    messy_answers = ["X", "", "A"] + ["a"] * (len(ALL_IDS) - 3)   # "X" และว่าง = ไม่ได้ตอบ; "A" ตัวใหญ่ใช้ได้
    messy = ",".join(["B", "ขาย"] + messy_answers + [""])
    csv_path.write_text("\n".join([header, good, messy, ",,,"]), encoding="utf-8-sig")
    rows = rt.read_answers(csv_path)
    assert [r["reader_id"] for r in rows] == ["A", "B"]     # แถวว่างข้าม
    assert rows[1]["answers"].get("T1") is None and rows[1]["answers"].get("T2") is None   # "X" และว่าง = ไม่ได้ตอบ
    assert rows[1]["answers"]["T3"] == "a"                  # ตัวใหญ่ → เล็ก
    text = rt.render_result(rt.score(rows), rows)
    assert "ผู้อ่าน 2 คน" in text and "ข้อ T2 งง" in text and "ยังไม่ผ่าน" in text


def test_cli_sheet_writes_three_files(tmp_path):
    assert rt.main(["sheet", "--lang", "th", "--out", str(tmp_path)]) == 0
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["reader_test_th_all_answers_template.csv", "reader_test_th_all_key.md", "reader_test_th_all_sheet.md"]
