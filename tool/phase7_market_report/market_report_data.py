# -*- coding: utf-8 -*-
"""
⑲ รายงานส่วนแบ่งตลาด — Phase 5: รวมข้อมูลของรายงาน PDF จากผล Phase 1-4 (โค้ดล้วน ไม่เรียก LLM)

ตัวเลขทุกตัวมาจาก phase7_market_facts.json / คำอธิบายทุกข้อมาจาก phase7_market_findings.json (ผ่านการตรวจแล้ว)
หน้ารายงาน:
    ปก -> สรุป (ตัวเลขหลัก + ประเด็นสำคัญจากข้อมูล) -> มูลค่าตลาดแยกหมวด -> ภาพรวมปัจจัย (แบบ A: ปัจจัย / สิ่งที่เห็น /
    แบรนด์ A-Z / จำนวนแหล่ง) -> รายละเอียดปัจจัย (2 คอลัมน์ต่อหน้า จัดตามความสูงเนื้อหา plan_columns) ->
    รายละเอียดแบรนด์ (3 แบรนด์ต่อหน้า) -> วิธีการ (รวมการเปลี่ยนแปลงที่ยังไม่พบคำอธิบาย) ->
    แหล่งข้อมูล (มีลิงก์) -> แหล่งข้อมูลและลิขสิทธิ์ (อ้างอิง Euromonitor - เจ้าของงานขอไว้หน้าสุดท้าย)
กติกา: ไม่บอกว่าแบรนด์ไหนชนะ/แพ้ - แบรนด์เรียงตามตัวอักษร (ภาพรวม) หรือตามลำดับคำถาม (= ขนาดหมวด) ไม่เรียงตามการเปลี่ยนแปลง
เลือก finding ที่แสดง: direct ก่อน แล้วตามจำนวนแหล่งที่อ้าง (มากก่อน) - หน้าปัจจัยแสดงคำถามระดับตลาดก่อนแบรนด์
เลขอ้างอิง [n] เรียงตามลำดับที่ปรากฏในรายงานครั้งแรก
"""
import json
import math
from datetime import date
from pathlib import Path

from factors import DATA_FACTORS, FACTORS
from market_data import TOTAL_CATEGORY
from market_facts import FACTS_FILE
from market_i18n import OUTLET_LABELS, STRINGS, date_text
from market_questions import ECOMMERCE, OUTLET_TERMS, QUESTIONS_FILE
from market_search import EVIDENCE_FILE
from market_synthesis import FINDINGS_FILE, parse_date

# 🆕 (2026-10-12) รายงาน 40 -> 20 หน้า (เจ้าของงานขอ): 3 แบรนด์ต่อหน้า / แหล่งข้อมูล 3 คอลัมน์ - แสดงเฉพาะข้อที่
# หนักแน่นที่สุด (direct ก่อน แหล่งมากก่อน) พร้อมบอก "แสดง k จาก n ข้อ" - ทุกข้ออยู่ครบใน phase7_market_findings.json
# 🆕 (2026-10-14) หน้า "รายละเอียดแต่ละปัจจัย" ว่างเกือบครึ่งหน้า (ปัจจัยที่มี 1-3 ข้อกินทั้งคอลัมน์) -> จัดเป็นคอลัมน์ตามเนื้อหาจริง:
# ปัจจัยที่เนื้อหาน้อยอยู่คอลัมน์เดียวกัน ปัจจัยที่มีข้อมากแสดงเพิ่มจนเต็มคอลัมน์ (plan_columns)
FACTOR_MIN_FINDINGS = 2      # ข้อขั้นต่ำต่อปัจจัย (ถ้ามี) - ที่เหลือเติมข้อ direct แล้วข้อพื้นหลัง จนเต็มคอลัมน์
FACTOR_WANT_FINDINGS = 4     # ปัจจัยที่มีข้อ direct มาก ควรได้อย่างน้อยเท่านี้ - ถ้าถูกบีบต่ำกว่าจะมีค่าปรับในการจัดคอลัมน์
SQUEEZE_PENALTY = 12000      # ค่าปรับต่อข้อที่ขาด (กำลังสอง) เทียบกับช่องว่างท้ายคอลัมน์ (px กำลังสอง)
BRAND_PAGE_FINDINGS = 3      # finding ต่อแบรนด์
SOURCES_PER_PAGE = 48
HIDDEN_FACTORS = ("other",)  # "อื่นๆ" รอคนตรวจ - ไม่แสดง (factors.py)

# ความสูงคอลัมน์ในหน้า 540px: บน 72 / ล่าง 30 (market.css .fx2) เผื่อ 2px
COLUMN_PX = 436
BLOCK_GAP_PX = 16             # ช่องไฟระหว่างปัจจัยในคอลัมน์เดียวกัน (market.css .fcol gap)
# ค่าประมาณจากการวัดการพิมพ์จริง (Chromium, ฟอนต์รายงาน, คอลัมน์กว้าง 443px) - ใช้แค่ตัดสินใจก่อนพิมพ์
# ส่วนที่ประมาณพลาด fitAll() ย่อฟอนต์ของคอลัมน์ให้พอดี / มีเตือนถ้ายังล้น
_EST = {
    "th": {"fd_cpl": 100, "fd_line": 16.0, "fd_base": 24.0, "data_cpl": 80, "foot_cpl": 115},
    "en": {"fd_cpl": 90, "fd_line": 14.5, "fd_base": 23.5, "data_cpl": 70, "foot_cpl": 100},
}
_HEAD_PX, _GAP_PX, _DATA_BASE_PX, _DATA_LINE_PX, _MUTED_PX, _FOOT_LINE_PX = 24, 6, 12, 16.7, 22, 12.8
_CITE_CHARS = 8               # " [12, 13]"


def read_inputs(run_dir):
    run_dir = Path(run_dir)

    def load(name):
        return json.loads((run_dir / name).read_text(encoding="utf-8"))
    return {"facts": load(FACTS_FILE), "questions": load(QUESTIONS_FILE)["questions"],
            "findings": load(FINDINGS_FILE), "evidence": load(EVIDENCE_FILE)["questions"]}


# ---------------------------------------------------------------------------
# ตัวช่วยตัวเลข
# ---------------------------------------------------------------------------

def pct(v, dp=1):
    return "-" if v is None else f"{v:.{dp}f}%"


def bn(v, L):
    """ล้านบาท -> "THB 269.7 bn" / "269.7 พันล้านบาท" """
    return L["na"] if v is None else L["thb_bn"].format(v=f"{v / 1000:,.1f}")


def finding_order(f):
    """direct ก่อน แล้วแหล่งที่อ้างมากก่อน (เสถียร - ไม่เรียงตามชื่อแบรนด์หรือการเปลี่ยนแปลง)"""
    return (f["relevance"] != "direct", -len(f["evidence"]))


# ---------------------------------------------------------------------------
# อ้างอิง
# ---------------------------------------------------------------------------

class Citations:
    """rid -> เลข [n] ตามลำดับที่ใช้ครั้งแรก + รายการแหล่ง (หัวข้อ / โดเมน / วันที่ / ลิงก์ / ข่าวหรือเว็บ)"""

    def __init__(self, evidence):
        self.items = {r["rid"]: r for q in evidence for r in q["results"]}
        self.numbers, self.order = {}, []

    def cite(self, rids):
        out = []
        for rid in rids:
            if rid not in self.items:
                continue
            if rid not in self.numbers:
                self.numbers[rid] = len(self.order) + 1
                self.order.append(rid)
            out.append(self.numbers[rid])
        return sorted(set(out))

    def sources(self, lang):
        L = STRINGS[lang]
        rows = []
        for rid in self.order:
            r = self.items[rid]
            d = parse_date(r.get("page_date")) or parse_date(r.get("serp_date"))
            rows.append({"n": self.numbers[rid], "title": r.get("title") or r["domain"], "domain": r["domain"],
                         "url": r["link"], "date": date_text(d, lang),
                         "kind": L["src_news"] if r.get("kind") == "news" else L["src_web"]})
        return rows


# ---------------------------------------------------------------------------
# ส่วนต่างๆ ของรายงาน
# ---------------------------------------------------------------------------

def _total(facts):
    return facts["categories"][TOTAL_CATEGORY]


def kpis(facts, findings, lang):
    L, m = STRINGS[lang], facts["meta"]
    y0, y1, y2 = m["base_year"], m["last_year"], m["forecast_year"]
    size = facts["market"][TOTAL_CATEGORY]
    ecom = _total(facts)["channel"]["ecommerce"]
    others = _total(facts)["brands"]["others"]
    fda = _total(facts).get("fda") or {}
    imp = fda.get("import_share") or {}
    fy = sorted(imp, key=int)
    out = {
        "market": {"value": bn(size["value"][str(y1)], L),
                   "sub": L["kpi_market_sub"].format(g=pct(size["cagr_hist"]), y0=y0, f=pct(size["cagr_forecast"]), y2=y2)},
        "online": {"a": pct(ecom.get(str(y0))), "b": pct(ecom.get(str(y1)))},
        "others": {"a": pct(others.get(str(y0))), "b": pct(others.get(str(y1)))},
        "imports": ({"a": pct(imp[fy[0]]), "b": pct(imp[fy[-1]]), "y0": fy[0], "y1": fy[-1]} if fy else None),
    }
    status = findings["meta"]["status"]
    messages = [
        L["msg_market"].format(v=out["market"]["value"], y1=y1, g=pct(size["cagr_hist"]), y0=y0,
                               f=pct(size["cagr_forecast"]), y2=y2),
        L["msg_online"].format(a=out["online"]["a"], b=out["online"]["b"], y0=y0, y1=y1),
        L["msg_others"].format(a=out["others"]["a"], b=out["others"]["b"], y0=y0, y1=y1),
    ]
    if out["imports"]:
        messages.append(L["msg_imports"].format(a=out["imports"]["a"], b=out["imports"]["b"], y0=fy[0], y1=fy[-1]))
    messages.append(L["msg_evidence"].format(n=status.get("ok", 0), k=sum(status.values())))
    return out, messages


def market_rows(facts, lang):
    """หมวดสินค้าเรียงตามมูลค่าปีล่าสุด + ความกว้างแถบ (% ของหมวดใหญ่สุด)"""
    L, last = STRINGS[lang], str(facts["meta"]["last_year"])
    rows = [(c, facts["market"][c]) for c in facts["categories"] if c != TOTAL_CATEGORY]
    rows.sort(key=lambda cv: -(cv[1]["value"][last] or 0))
    top = rows[0][1]["value"][last] or 1
    return [{"name": c, "value": bn(s["value"][last], L), "share": pct(s["share_of_total"]),
             "growth": pct(s["cagr_hist"]), "forecast": pct(s["cagr_forecast"]),
             "bar": round(100 * (s["value"][last] or 0) / top, 1)} for c, s in rows]


def data_lines(factor, facts, questions, lang):
    """ตัวเลขจากข้อมูลยอดขาย/อย. ของปัจจัยที่วัดได้ (ปัจจัยเว็บ = [])"""
    L, m = STRINGS[lang], facts["meta"]
    y0, y1 = str(m["base_year"]), str(m["last_year"])
    total = _total(facts)
    labels = OUTLET_LABELS[lang]
    if factor == "channel_shift":
        ecom = total["channel"]["ecommerce"]
        lines = [L["line_online"].format(a=pct(ecom.get(y0)), b=pct(ecom.get(y1)))]
        for r in total["channel"]["leaves"]:
            if r["outlet"] != ECOMMERCE and r["outlet"] in OUTLET_TERMS and abs(r["change_pp"] or 0) >= 1:
                lines.append(L["line_outlet"].format(outlet=labels.get(r["outlet"], r["outlet"]),
                                                     a=pct(r["share_base"]), b=pct(r["share_last"])))
        return lines[:4]
    if factor == "concentration":
        o = total["brands"]["others"]
        lines = [L["line_others"].format(a=pct(o.get(y0)), b=pct(o.get(y1)))]
        for q in questions:
            if q["topic"].startswith("concentration:"):
                f = q["facts"]
                lines.append(L["line_others_cat"].format(category=q["categories"][0], a=pct(f["others_base"]),
                                                         b=pct(f["others_last"])))
        return lines[:5]
    if factor == "premium_shift":
        return [L["line_premium"].format(category=q["categories"][0], a=pct(q["facts"]["share_base"]),
                                         b=pct(q["facts"]["share_last"]))
                for q in questions if q["topic"].startswith("premium:")]
    if factor == "launch_activity":
        fda = total.get("fda") or {}
        by, imp = fda.get("by_year") or {}, fda.get("import_share") or {}
        if not by:
            return []
        ys = sorted(by, key=int)
        lines = [L["line_fda"].format(n0=by[ys[0]], y0=ys[0], n1=by[ys[-1]], y1=ys[-1])]
        if imp:
            lines.append(L["line_fda_import"].format(a=pct(imp[ys[0]]), b=pct(imp[ys[-1]])))
        return lines
    return []


def subject_of(q, lang):
    """ป้ายเรื่องของคำถาม: แบรนด์ / ช่องทางขาย (ชื่อสำหรับผู้อ่าน) / หมวด"""
    if q.get("brand"):
        return q["brand"]
    if q["topic"] in OUTLET_TERMS:
        return OUTLET_LABELS[lang].get(q["topic"], q["topic"])
    return ", ".join(q.get("categories") or [])


def _finding_view(f, q, cites, lang):
    """finding -> ข้อความที่แสดง + ป้ายเรื่อง + เลขอ้างอิง"""
    return {"text": f["statement_" + lang], "subject": subject_of(q, lang), "relevance": f["relevance"],
            "cites": cites.cite(f["evidence"])}


def plan_columns(blocks, capacity=COLUMN_PX, gap=BLOCK_GAP_PX):
    """จัดปัจจัยลงคอลัมน์ตามความสูงจริงของเนื้อหา -> [[(ลำดับบล็อก, จำนวนข้อที่แสดง), ...], ...] ต่อคอลัมน์

    blocks[i] = {"fixed": px (หัว + กล่องตัวเลข + ท้าย), "costs": [px ต่อข้อ ตามลำดับที่แสดง], "min_k": int, "grow": int}
      min_k = ข้อที่ต้องมี / grow = จำนวนข้อ direct (เติมก่อน) - หลังจากนั้นถ้าคอลัมน์ยังว่างจึงเติมข้อพื้นหลัง
    ลำดับปัจจัยคงเดิม ไม่ตัดปัจจัยข้ามคอลัมน์ - 2 คอลัมน์ = 1 หน้า:
    1) หาจำนวนคอลัมน์ขั้นต่ำที่ใส่ปัจจัยครบด้วยข้อขั้นต่ำ -> จำนวนหน้าน้อยที่สุด (ปัดเป็นคู่ ไม่ให้หน้าสุดท้ายเหลือคอลัมน์เดียว)
       หรือเพิ่มอีก 1 หน้าถ้าต้นทุนรวมต่ำกว่า
    2) แบ่งเป็นจำนวนคอลัมน์นั้นแบบที่ช่องว่างท้ายคอลัมน์รวมกำลังสองน้อยที่สุด (คอลัมน์เต็มสม่ำเสมอ ไม่มีคอลัมน์โล่งคอลัมน์เดียว)
       โดยเติมข้อที่เหลือ (เฉพาะ direct) ให้ปัจจัยที่แสดงน้อยที่สุดก่อน จนคอลัมน์เต็ม - ปัจจัยที่มีข้อมากแต่ถูกบีบให้เหลือ
       น้อยกว่า FACTOR_WANT_FINDINGS โดนค่าปรับ (ไม่ให้ปัจจัยสำคัญเหลือ 2 ข้อเพื่อเอาไปเติมคอลัมน์ข้างเคียงเท่านั้น)
    """
    n = len(blocks)
    if n == 0:
        return []

    def height(b, k):
        return b["fixed"] + sum(b["costs"][:k])

    cache = {}

    def column(a, z):
        """คอลัมน์ที่เป็นปัจจัย a..z-1 -> (ต้นทุน, [ข้อที่แสดงของแต่ละปัจจัย]) / None = ใส่ข้อขั้นต่ำไม่พอ"""
        if (a, z) in cache:
            return cache[(a, z)]
        idx = list(range(a, z))
        ks = {i: blocks[i]["min_k"] for i in idx}
        used = sum(height(blocks[i], ks[i]) for i in idx) + gap * (len(idx) - 1)
        if len(idx) > 1 and used > capacity:
            cache[(a, z)] = None
            return None
        # เติมข้อ direct ก่อน แล้วถ้าคอลัมน์ยังมีที่ เติมข้อพื้นหลัง (มีป้าย "ข้อมูลพื้นหลัง" กำกับ) แทนที่จะปล่อยว่าง
        for limit in ("grow", "all"):
            while True:
                for i in sorted(idx, key=lambda j: (ks[j], -(len(blocks[j]["costs"]) - ks[j]), j)):
                    b = blocks[i]
                    top = b["grow"] if limit == "grow" else len(b["costs"])
                    if ks[i] < top and used + b["costs"][ks[i]] <= capacity:
                        used += b["costs"][ks[i]]
                        ks[i] += 1
                        break
                else:
                    break
        unmet = sum(max(0, min(blocks[i]["grow"], FACTOR_WANT_FINDINGS) - ks[i]) ** 2 for i in idx)
        cache[(a, z)] = (max(0.0, capacity - used) ** 2 + SQUEEZE_PENALTY * unmet, [ks[i] for i in idx])
        return cache[(a, z)]

    INF = float("inf")
    # best[c][j] = (ต้นทุน, ตำแหน่งตัด) แบ่งปัจจัย 0..j-1 เป็น c คอลัมน์
    best = [[(INF, None)] * (n + 1) for _ in range(n + 1)]
    best[0][0] = (0.0, None)
    for c in range(1, n + 1):
        for j in range(c, n + 1):
            for a in range(c - 1, j):
                col = column(a, j)
                if col is None or best[c - 1][a][0] == INF:
                    continue
                cost = best[c - 1][a][0] + col[0]
                if cost < best[c][j][0]:
                    best[c][j] = (cost, a)
    fewest = next(c for c in range(1, n + 1) if best[c][n][0] < INF)
    even = min(n, fewest + fewest % 2)
    # จำนวนหน้าน้อยที่สุด หรือเพิ่มอีก 1 หน้าถ้าช่วยให้ไม่ต้องบีบปัจจัยสำคัญ (เทียบด้วยต้นทุนเดียวกัน)
    target = min((c for c in (even, min(n, even + 2)) if best[c][n][0] < INF), key=lambda c: (best[c][n][0], c))

    cuts, j = [], n
    for c in range(target, 0, -1):
        a = best[c][j][1]
        cuts.append((a, j))
        j = a
    plan = []
    for a, z in reversed(cuts):
        plan.append(list(zip(range(a, z), column(a, z)[1])))
    return plan


def _factor_block(p, ordered, facts, questions):
    """ปัจจัย 1 ปัจจัย -> บล็อกสำหรับ plan_columns (ความสูงประมาณเป็น px ที่ 11px ของหน้า)

    ใช้ค่าที่สูงกว่าของ 2 ภาษา -> ทั้งอังกฤษและไทยได้การจัดคอลัมน์และข้อที่แสดงชุดเดียวกัน (เลขอ้างอิงตรงกัน)"""
    block = {"fixed": 0.0, "costs": [0.0] * len(ordered)}
    for lang in STRINGS:
        L, e = STRINGS[lang], _EST[lang]
        lines = data_lines(p["id"], facts, questions, lang)
        # ปัจจัยจากข่าว/เว็บไม่มีกล่องตัวเลข (ป้ายข้างชื่อปัจจัยบอกแหล่งอยู่แล้ว) - ไม่เปลืองที่ซ้ำทุกปัจจัย
        data_h = (_GAP_PX + _DATA_BASE_PX + _DATA_LINE_PX *
                  sum(max(1, math.ceil(len(s) / e["data_cpl"])) for s in lines)) if lines else 0
        foot = (L["related_brands"].format(brands=", ".join(p["brands"])) if p["brands"] else "")
        if len(ordered) > FACTOR_MIN_FINDINGS:
            foot += " · " + L["shown_of"].format(k=FACTOR_MIN_FINDINGS, n=len(ordered))      # ประมาณความยาวบรรทัดท้าย
        foot_h = (_GAP_PX + _FOOT_LINE_PX * math.ceil(len(foot) / e["foot_cpl"])) if foot else 0
        block["fixed"] = max(block["fixed"], _HEAD_PX + data_h + _GAP_PX + foot_h + (0 if ordered else _MUTED_PX))
        for j, (q, f) in enumerate(ordered):
            chars = len(f["statement_" + lang]) + _CITE_CHARS + 0.9 * len(subject_of(q, lang)) + 4
            block["costs"][j] = max(block["costs"][j],
                                    e["fd_base"] + max(1, math.ceil(chars / e["fd_cpl"])) * e["fd_line"])
    direct = sum(1 for _, f in ordered if f["relevance"] == "direct")
    min_k = min(FACTOR_MIN_FINDINGS, len(ordered))
    return {**block, "min_k": min_k, "grow": max(min_k, direct)}


def build_context(inputs, lang, company, extracted):
    """ข้อมูลทั้งรายงานของภาษาหนึ่ง (Citations ใหม่ต่อภาษา - เลขอ้างอิงตรงกันทั้ง 2 ภาษาเพราะลำดับหน้าเหมือนกัน)"""
    facts, questions, findings = inputs["facts"], inputs["questions"], inputs["findings"]
    L, m = STRINGS[lang], facts["meta"]
    y0, y1, y2 = m["base_year"], m["last_year"], m["forecast_year"]
    results = findings["results"]
    by_q = {q["id"]: q for q in questions}
    cites = Citations(inputs["evidence"])
    kpi, messages = kpis(facts, findings, lang)

    # ---- หน้าปัจจัย (ลำดับ: ปัจจัยข้อมูลก่อน แล้วปัจจัยเว็บตามจำนวน finding - ไม่ได้เรียงแบรนด์) ----
    per_factor = {}
    for qid, r in results.items():
        for f in r["findings"]:
            per_factor.setdefault(f["factor"], []).append((by_q[qid], f))
    shown = [k for k in DATA_FACTORS if k in per_factor or data_lines(k, facts, questions, lang)]
    shown += sorted((k for k in per_factor if k not in DATA_FACTORS and k not in HIDDEN_FACTORS),
                    key=lambda k: (-len(per_factor[k]), list(FACTORS).index(k)))
    # ข้อที่หนักแน่น (direct) ก่อนข้อพื้นหลัง แล้วคำถามระดับตลาดก่อนแบรนด์ แล้วแหล่งมากก่อน
    def factor_order(qf):
        return (qf[1]["relevance"] != "direct", qf[0]["level"] == "brand", -len(qf[1]["evidence"]))

    factor_pages, ordered_of = [], []
    for k in shown:
        agg = findings["by_factor"].get(k, {})
        factor_pages.append({
            "id": k, "label": FACTORS[k]["label_" + lang], "source": FACTORS[k]["source"],
            "data_lines": data_lines(k, facts, questions, lang), "findings": [], "shown_of": "",
            "brands": agg.get("brands", []), "n_sources": agg.get("n_sources", 0),
        })
        ordered_of.append(sorted(per_factor.get(k, []), key=factor_order))

    # จัดลงคอลัมน์ก่อน แล้วค่อยให้เลขอ้างอิงตามลำดับที่ปรากฏ (คอลัมน์ซ้ายก่อนขวา บนลงล่าง)
    plan = plan_columns([_factor_block(p, o, facts, questions) for p, o in zip(factor_pages, ordered_of)])
    factor_columns = []
    for col in plan:
        column = []
        for i, k_show in col:
            p, ordered = factor_pages[i], ordered_of[i]
            p["findings"] = [_finding_view(f, q, cites, lang) for q, f in ordered[:k_show]]
            p["shown_of"] = L["shown_of"].format(k=k_show, n=len(ordered)) if len(ordered) > k_show else ""
            column.append(p)
        factor_columns.append(column)

    # ---- ภาพรวม (แบบ A) - "สิ่งที่เห็น": ปัจจัยข้อมูล = ตัวเลข / ปัจจัยเว็บ = finding direct แรกของหน้าปัจจัย
    # (ไม่มี direct = บอกว่ามีแค่ข้อมูลพื้นหลัง - ทดลองจริง: ข่าวร้านค้าอเมริกาถอดแป้งเด็กขึ้นหน้าภาพรวมของตลาดไทย) ----
    def seen(p):
        if p["data_lines"]:
            return p["data_lines"][:2]
        direct = [f["text"] for f in p["findings"] if f["relevance"] == "direct"]
        return direct[:1] or ([L["only_background"]] if p["findings"] else [])

    overview = [{"label": p["label"], "tag": L["data_tag"] if p["source"] == "data" else L["web_tag"],
                 "seen": seen(p), "brands": p["brands"], "n_sources": p["n_sources"]} for p in factor_pages]

    # ---- หน้าแบรนด์ (ตามลำดับคำถาม = หมวดใหญ่ก่อน) ----
    brand_pages, missing = [], []
    for q in questions:
        r = results.get(q["id"])
        if not r:
            continue
        if not r["findings"]:
            missing.append({"subject": subject_of(q, lang), "question": q["question_" + lang]})
            continue
        if q["level"] != "brand":
            continue
        fx = q["facts"]
        rows = []
        for row in fx["by_category"]:
            key = "share_change" if row["share_base"] else "share_change_new"
            rows.append(L[key].format(category=row["category"], a=pct(row["share_base"]), b=pct(row["share_last"]),
                                      y0=y0, y1=y1))
        main = max(fx["by_category"], key=lambda row: abs(row["change_pp"] or 0))
        movers = facts["categories"][main["category"]]["brands"]["movers"]
        series = next((mv.get("series") for mv in movers if mv["brand"] == q["brand"]), None)
        absorbed = [a for row in fx["by_category"] for a in (row.get("absorbed") or [])]
        fda = fx.get("fda_by_year") or {}
        ordered = sorted(r["findings"], key=finding_order)
        shown_f = ordered[:BRAND_PAGE_FINDINGS]
        brand_pages.append({
            "brand": q["brand"], "owner": fx.get("owner"), "tier": L.get("tier_" + str(fx.get("tier")), L["na"]),
            "rows": rows, "main_category": main["category"], "series": series,
            "absorbed": L["absorbed"].format(names=", ".join(absorbed)) if absorbed else "",
            "fda": L["fda_line"].format(series=" · ".join(f"{y}: {n}" for y, n in fda.items())) if fda else "",
            "findings": [_finding_view(f, q, cites, lang) for f in shown_f],
            "shown_of": L["shown_of"].format(k=len(shown_f), n=len(ordered)) if len(ordered) > len(shown_f) else "",
        })

    sources = cites.sources(lang)
    return {
        "lang": lang, "L": L, "company": company,
        "meta": {"y0": y0, "y1": y1, "y2": y2, "edition": m["edition"], "fda": m.get("fda") or {},
                 "extracted": date_text(extracted, lang)},
        "kpi": kpi, "messages": messages, "market_rows": market_rows(facts, lang), "overview": overview,
        "factor_pages": factor_pages, "factor_columns": factor_columns, "brand_pages": brand_pages, "missing": missing,
        "sources": sources, "source_pages": [sources[i:i + SOURCES_PER_PAGE] for i in range(0, len(sources), SOURCES_PER_PAGE)],
    }


def euromonitor_extracted(run_dir=None, default=None):
    """วันที่ดึงข้อมูล Euromonitor (ปกของไฟล์: "Monday, October 12, 2026") - อ่านไม่ได้ = default"""
    try:
        import openpyxl
        from market_data import EURO_FILE
        from datetime import datetime
        wb = openpyxl.load_workbook(EURO_FILE, read_only=True)
        for row in wb["Cover Sheet"].iter_rows(values_only=True):
            for cell in row:
                if isinstance(cell, str) and "," in cell and cell.split(",")[0] in (
                        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"):
                    return datetime.strptime(cell.split("|")[0].strip(), "%A, %B %d, %Y").date()
    except Exception:  # noqa: BLE001 - ไม่มีวันที่ก็ยังทำรายงานได้
        pass
    return default or date.today()
