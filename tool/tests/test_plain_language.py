# -*- coding: utf-8 -*-
"""
เทสของภาษาง่ายในข้อความที่ LLM เขียน (🆕 2026-10-12 ขั้น D) - plain_text.py + พรอมต์/ตัวตรวจใน enrich.py
ไม่ยิง API (llm_call ปลอม)

รัน: pytest main/tool/tests/test_plain_language.py -v
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase6_pdf_report"))

import enrich  # noqa: E402
from plain_text import (PLAIN_RULES_EN, PLAIN_RULES_TH, cleanup_deep, find_banned, plain_cleanup)  # noqa: E402


# ---------------------------------------------------------------------------
# plain_text
# ---------------------------------------------------------------------------
def test_plain_cleanup_en_replaces_jargon_and_keeps_case_and_numbers():
    assert plain_cleanup("Aligns with the trend's job-to-be-done of fading spots", "en") == \
        "Aligns with the trend's goal of fading spots"
    assert plain_cleanup("Job to be done: calm skin", "en") == "Goal: calm skin"          # ต้นประโยคคงตัวพิมพ์ใหญ่
    assert plain_cleanup("27,216 SKUs; one SKU", "en") == "27,216 products; one product"
    assert plain_cleanup("A language model ranks the point of difference by similarity", "en") == \
        "An AI ranks the key difference by match"
    assert plain_cleanup("an SKU and a language model", "en") == "a product and an AI"
    # ไม่แตะตัวเลข/สัญลักษณ์/ชื่อ
    assert plain_cleanup("Expected +26% by year 2 (SPF50+, PDRN)", "en") == "Expected +26% by year 2 (SPF50+, PDRN)"
    assert plain_cleanup(None, "en") is None and plain_cleanup("", "th") == ""


def test_plain_cleanup_th_replaces_jargon():
    assert plain_cleanup("ใช้โมเดลภาษาเทียบสินค้า 27,216 SKU", "th") == "ใช้ AI เทียบสินค้า 27,216 ชิ้น"
    assert plain_cleanup("Job to be done ของเทรนด์", "th") == "สิ่งที่ผู้บริโภคต้องการให้สำเร็จ ของเทรนด์"


def test_find_banned_and_cleanup_deep():
    assert find_banned("Growth is accelerating to 30% YoY with strong momentum", "en") == ["accelerating to", "YoY", "momentum"]
    assert find_banned("ใช้โมเดลภาษา และ SKU", "th") == ["โมเดลภาษา", "SKU"]
    assert find_banned("A clear, short sentence about acne patches.", "en") == []
    out = cleanup_deep({"a": ["language model", {"b": "SKU"}], "n": 3}, "en")
    assert out == {"a": ["AI", {"b": "product"}], "n": 3}


def test_prompts_carry_plain_rules_and_versions_were_bumped():
    for prompt in (enrich.SYSTEM_PROMPT, enrich.SYSTEM_PROMPT_CONDENSE, enrich.SYSTEM_PROMPT_LADDER, enrich.SYSTEM_PROMPT_PLAIN_EN):
        assert "Plain-language rules" in prompt and "YoY" in prompt and "language model" in prompt   # กติกา + รายการคำต้องห้ามอยู่ในพรอมต์
    for prompt in (enrich.SYSTEM_PROMPT_TH, enrich.SYSTEM_PROMPT_TH_TRANSLATE):
        assert "Plain-language rules for the Thai copy" in prompt and "โมเดลภาษา" in prompt and "transliterate" in prompt
    assert "accelerating to" in PLAIN_RULES_EN and "เร่งตัวเป็น" in PLAIN_RULES_TH
    assert "plain" in enrich.SYSTEM_PROMPT_TH_TRANSLATE.lower() and "word for word" in enrich.SYSTEM_PROMPT_TH_TRANSLATE
    assert min(enrich.PROMPT_VERSION, enrich.PROMPT_VERSION_TH, enrich.PROMPT_VERSION_CONDENSE, enrich.PROMPT_VERSION_LADDER) >= 2


def test_validators_apply_plain_cleanup():
    en = {"headline": "A language model finds SKUs", "trend": "t", "insight": "i", "workshop_question": "How can your brand win?"}
    assert enrich.validate(en)["headline"] == "An AI finds products"
    th_payload = {"context_en": {"target_consumer": ""}, "product_match_reasons_en": ["x"]}
    th = {"headline": "ใช้โมเดลภาษา", "trend": "เทรนด์", "insight": "ข้อมูล", "workshop_question": "แบรนด์ของคุณ?", "target": "",
          "product_reasons": ["ตรงกับเทรนด์ 12 SKU"]}
    out = enrich.validate_th(th, th_payload)
    assert out["headline"] == "ใช้ AI" and out["product_reasons"] == ["ตรงกับเทรนด์ 12 ชิ้น"]
    assert enrich.validate_same_shape({"a": "x"}, {"a": "ใช้โมเดลภาษา"}) == {"a": "ใช้ AI"}


# ---------------------------------------------------------------------------
# plain_report_texts_en (takeaway / market / personas ฉบับอังกฤษเป็นภาษาง่าย)
# ---------------------------------------------------------------------------
def _ctx():
    return {"takeaway": {"mega_trend_name": "The Clinical Bio-Convergence", "macro_direction": "Leveraging multi-modal convergence.",
                         "key_opportunity": "Optimise dermal barrier outcomes."},
            "overview": {"market": {"summary": "The market is accelerating towards clinical efficacy."}},
            "personas": [{"name": "The Evidence-First Curator", "description": "Seeks validated outcomes.",
                          "value_driver": "Proof", "channel_preference": "Dermatologist channels"}],
            "stepic": [{"headline": "H", "body": "B"}], "signals": [{"signal": "s", "implication": "i"}]}


def test_plain_report_texts_en_rewrites_caches_and_keeps_names():
    ctx, cache, seen = _ctx(), {}, []

    def llm(system, user, max_tokens=900):
        assert "Plain-language rules" in system
        payload = json.loads(user)
        seen.append(sorted(payload))
        text = json.dumps(payload, ensure_ascii=False)
        text = (text.replace("Leveraging multi-modal convergence.", "Combining several technologies.")
                .replace("Optimise dermal barrier outcomes.", "Make the skin barrier stronger.")
                .replace("accelerating towards clinical efficacy", "moving towards products that prove results")
                .replace("Seeks validated outcomes.", "Wants products with proven results.")
                .replace("The Clinical Bio-Convergence", "RENAMED").replace("The Evidence-First Curator", "RENAMED"))
        return text

    counts = enrich.plain_report_texts_en(ctx, cache, llm_call=llm, log=lambda *_: None)
    assert counts == {"llm": 3}
    assert ctx["takeaway"]["macro_direction"] == "Combining several technologies."
    assert ctx["takeaway"]["mega_trend_name"] == "The Clinical Bio-Convergence"          # ชื่อเรียกคงเดิมแม้ LLM เปลี่ยน
    assert ctx["overview"]["market"]["summary"] == "The market is moving towards products that prove results."
    assert ctx["personas"][0]["description"] == "Wants products with proven results."
    assert ctx["personas"][0]["name"] == "The Evidence-First Curator"
    assert all("stepic" not in keys and "signals" not in keys for keys in seen)          # ไม่ส่ง stepic/signals ซ้ำ (ย่อแล้วใน condense)
    assert "plain_en" in cache and set(cache["plain_en"]) == {"takeaway", "market", "personas"}

    # รอบที่สอง: ไม่มี LLM ใช้ cache ได้
    ctx2 = _ctx()
    counts2 = enrich.plain_report_texts_en(ctx2, cache, llm_call=None, log=lambda *_: None)
    assert counts2 == {"llm (cached)": 3}
    assert ctx2["takeaway"]["macro_direction"] == "Combining several technologies."


def test_plain_report_texts_en_rejects_thai_and_bloat_and_keeps_original():
    ctx, cache = _ctx(), {}

    def llm(system, user, max_tokens=900):
        payload = json.loads(user)
        if "summary" in payload:
            payload["summary"] = "ตลาดกำลังเติบโต"                                       # มีภาษาไทย -> ไม่รับ
        if "items" in payload:
            payload["items"][0]["description"] = " ".join(["word"] * 80)                # ยาวเกินกำหนด -> ไม่รับ
        return json.dumps(payload, ensure_ascii=False)

    counts = enrich.plain_report_texts_en(ctx, cache, llm_call=llm, log=lambda *_: None)
    assert counts == {"llm": 1, "original (fallback)": 2}                                # เหลือเฉพาะ takeaway ที่ผ่าน
    assert ctx["overview"]["market"]["summary"] == "The market is accelerating towards clinical efficacy."
    assert ctx["personas"][0]["description"] == "Seeks validated outcomes."
    # ไม่มี LLM และไม่มี cache = ข้อความเดิมทั้งหมด
    ctx3 = _ctx()
    assert enrich.plain_report_texts_en(ctx3, {}, llm_call=None, log=lambda *_: None) == {"original (fallback)": 3}
    assert ctx3 == _ctx()
