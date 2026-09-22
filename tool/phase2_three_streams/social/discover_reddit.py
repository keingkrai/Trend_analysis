# -*- coding: utf-8 -*-
"""
Discover Reddit — pilot agent หมวด "ชุมชนต่างประเทศ" สำหรับขยาย Step 1 เป็นหลายหมวดข้อมูล
(ดู Detail/05 งานที่ยังไม่ได้ทำ/ขยาย Step 1 เป็นหลายหมวดข้อมูล.md)

หมวดนี้เป็นแกน "ต่างประเทศ" ของฝั่งชุมชนอยู่แล้วโดยธรรมชาติ (เหมือน Pantip เป็นแกนไทยอยู่แล้ว)
ไม่ต้องแยกคู่ภาษาเอง — สร้างคำค้นเป็นภาษาอังกฤษเท่านั้น

=== เส้นทางที่ทดสอบมาก่อนจะได้เวอร์ชันนี้ (2026-08-27) ===
1. requests.get("https://www.reddit.com/search.json?q=...") ตรงๆ - HTTP 403 คืนหน้า HTML บล็อกกลับมา
   (ไม่ใช่ JSON) แม้ตั้ง User-Agent เป็น browser จริงก็ตาม
2. requests.get("https://old.reddit.com/search.json?q=...") - HTTP 200 แต่คืนหน้า "Welcome to Reddit"
   (หน้า login) แทน JSON จริง - endpoint .json แบบไม่ auth ใช้ไม่ได้แล้วกับทั้งสองโดเมน
3. plain Playwright เปิดหน้า https://www.reddit.com/search/ - โดนบล็อกทันที
   ("You've been blocked by network security")
4. cloakbrowser เปิดหน้าเดียวกัน - ผ่านได้จริงครั้งแรก (เห็นโพสต์จริงพร้อม subreddit/vote/comment
   ครบ) แต่พอลองซ้ำทันทีด้วย session ใหม่ล้วนๆ กลับโดน CAPTCHA "Prove your humanity" ทั้งสองรอบถัดมา -
   ไม่เสถียรพอสำหรับใช้จริง เลิกใช้แนวทาง scraping ทั้งหมด

=== การออกแบบตอนนี้ (v2 — official Reddit API) ===
เจ้าของงานเลือกใช้ Reddit API ทางการแทน (แก้ปัญหาความไม่เสถียรของ scraping ได้ตรงจุด) - ใช้ OAuth2
"client_credentials" grant (app-only, **ไม่ต้องมีบัญชี Reddit ล็อกอิน** แค่สมัคร app ที่
reddit.com/prefs/apps เลือกประเภท "script" แล้วเอา client_id + client_secret มาใส่ .env) แล้วเรียก
https://oauth.reddit.com/search ตรงๆ ได้ JSON ที่มีโครงสร้างเต็ม (title/subreddit/score/comment
count/เวลาโพสต์/เนื้อหา) ไม่ต้อง scrape/parse ข้อความดิบเหมือน Pantip/Reddit-v1/Watsons เลย

⚠️ ยังไม่ verify เงื่อนไข/โควตา/ขั้นตอนสมัครปัจจุบันสดๆ เพราะ WebSearch เสียตลอด (ใช้ความรู้เดิมตอนเขียน
โค้ดนี้) - ให้เจ้าของงาน cross-check ตอนสมัครจริงว่ายังตรงกับที่นี่ไหม โดยเฉพาะ rate limit (ที่รู้มาคือ
~100 คำขอ/นาทีต่อ OAuth client สำหรับ endpoint แบบนี้)

สถานะ: เขียนโค้ดเสร็จแล้ว แต่ยังไม่เคยรันจริงเลย (REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET ยังไม่มีใน .env
รอเจ้าของงานสมัคร Reddit app แล้วใส่เอง) - ต้องรันดูผลจริงก่อนเชื่อว่า output มีคุณภาพดีพอ เหมือนหมวดอื่น
"""
import json
import os
import sys
import time
from pathlib import Path

# --- หา PROJECT_ROOT อัตโนมัติ (ย้ายไฟล์ไปโฟลเดอร์ไหนก็ยังหาเจอ) ---
for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import PROJECT_ROOT, OUTPUTS, tf, safe_json_parse  # noqa: E402

# หายไปตอนย้ายไฟล์เข้า workspace/ (ของเดิมใน analysis/discover_reddit.py มีอยู่) - ไม่มีบรรทัดนี้
# จะพัง NameError ทันทีที่เรียก get_access_token()/search_reddit_query() เพราะใช้ requests.* ตรงๆ
import requests  # noqa: E402

# --- ⚙️ ตั้งค่าก่อนรัน ---
TOPIC = "Trend Body Wash Thailand 2030"
N_QUERIES = 4          # จำนวนคำค้นที่ให้ LLM แตกออกมา (เท่ากับหมวดอื่น)
POSTS_PER_QUERY = 8

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
# Reddit ขอให้ระบุ User-Agent ที่มีรูปแบบ "แพลตฟอร์ม:ชื่อแอป:เวอร์ชัน (by /u/username)" - แก้ได้ผ่าน
# REDDIT_USER_AGENT ใน .env ถ้าเจ้าของงานอยากใส่ /u/username จริงของตัวเอง แต่ไม่บังคับสำหรับ client_credentials
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "windows:exfac-trend-research:v0.1 (by /u/exfac_research)")

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
SEARCH_URL = "https://oauth.reddit.com/search"

# --- 1. แตกคำค้นภาษาอังกฤษจาก topic (LLM, ไม่แปลจากไทยตรงตัว) ---
SYSTEM_PROMPT_QUERIES = """You are a market researcher who understands how English-speaking Reddit
users actually search and discuss consumer products. Your job is to generate English search queries
that real Reddit users would type when discussing this topic.

Rules:
- Must be phrases a real Reddit user would type in the search box, NOT a literal translation of any
  Thai phrase - think in English from scratch.
- Short, 2-6 words, like a real search box query (not a full sentence).
- Cover different angles: product recommendations, skin problems, brand comparisons, opinions/complaints.

Answer JSON only: {"queries": ["query 1", "query 2", ...]}
"""


def generate_english_queries(topic, n):
    try:
        response = tf.client.chat.completions.create(
            model=tf.MODEL_NAME_META,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_QUERIES},
                {"role": "user", "content": f"Topic: '{topic}'\nGenerate {n} queries."},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        parsed = safe_json_parse(response.choices[0].message.content)
        return parsed.get("queries", []) if parsed else []
    except Exception as e:
        print(f"⚠️ Error generating queries: {e}")
        return []


# --- 2. ขอ OAuth token แล้วค้น Reddit ผ่าน API ทางการ (ไม่ scrape แล้ว) ---
_access_token = None
_token_expires_at = 0.0


def get_access_token():
    """client_credentials grant - ไม่ต้องมีบัญชี Reddit ล็อกอิน ใช้แค่ client_id/secret ของ app"""
    global _access_token, _token_expires_at
    if _access_token and time.time() < _token_expires_at - 30:
        return _access_token
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        raise RuntimeError("ไม่มี REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET ใน .env - สมัคร app ที่ reddit.com/prefs/apps ก่อน")
    resp = requests.post(
        TOKEN_URL,
        auth=requests.auth.HTTPBasicAuth(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": REDDIT_USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "access_token" not in payload:
        raise RuntimeError(f"ขอ token ไม่สำเร็จ: {payload}")
    _access_token = payload["access_token"]
    _token_expires_at = time.time() + payload.get("expires_in", 3600)
    return _access_token


# 🆕 (2026-09-15) ค้นเฉพาะ subreddit ด้านความงาม/ของใช้ส่วนตัว - เดิมค้นทั้ง Reddit แล้วเรียงตาม engagement
# ทำให้โพสต์ไวรัลนอกเรื่อง (r/movies, r/AIO, r/dating_advice) ติด 5 จาก 10 โพสต์ที่ส่งเข้ารายงาน - ทุกตัวในนี้
# ตรวจแล้วว่าเป็น public จริงผ่าน /r/{sub}/about (r/Sunscreen ตอบ 403 จึงไม่ใส่)
BEAUTY_SUBREDDITS = (
    "SkincareAddiction", "SkincareAddicts", "AsianBeauty", "MakeupAddiction", "SkincareAddictionLux",
    "30PlusSkinCare", "BeautyGuruChatter", "PaleMUA", "OliveMUA", "HaircareScience", "curlyhair",
    "FemaleHairAdvice", "malegrooming", "Fragrance", "tretinoin", "acne", "beauty",
)


def format_comment_tree(children, max_chars=2500, max_body_chars=300, max_replies=3):
    """แปลงคอมเมนต์ระดับบนของโพสต์ (children จาก /comments/{id}) + reply อันดับต้นของแต่ละอันเป็นข้อความ
    สั้น - ต้องเอา reply ด้วย เพราะกระทู้โหวตแบบ "Holy Grail Voting" คอมเมนต์ระดับบนเป็นแค่ชื่อหมวด
    ชื่อสินค้าจริงอยู่ใน reply - ข้าม "more"/AutoModerator/คอมเมนต์ที่ถูกลบ หยุดเมื่อยาวเกิน max_chars"""
    lines, used = [], 0

    def usable(child):
        d = child.get("data", {})
        body = (d.get("body") or "").strip()
        return (child.get("kind") == "t1" and body not in ("", "[deleted]", "[removed]")
                and d.get("author") != "AutoModerator")

    def line(d, indent):
        return f"{indent}- ({d.get('score', 0)}) {' '.join(d['body'].split())[:max_body_chars]}"

    for child in filter(usable, children):
        d = child["data"]
        replies = d.get("replies")
        reply_children = replies.get("data", {}).get("children", []) if isinstance(replies, dict) else []
        for text in [line(d, "")] + [line(r["data"], "  ") for r in filter(usable, reply_children)][:max_replies]:
            if used + len(text) > max_chars:
                return "\n".join(lines)
            lines.append(text)
            used += len(text)
    return "\n".join(lines)


def fetch_top_comments(post_id, limit=15, max_chars=2500):
    """🆕 (2026-09-15) ดึงคอมเมนต์อันดับต้น (ลึก 2 ชั้น) ของโพสต์ - เนื้อหาจริงของกระทู้ถาม/กระทู้โหวตอยู่ใน
    คอมเมนต์ เดิมเก็บแค่หัวข้อ+เนื้อโพสต์ LLM จึงตอบคำถามแทนจากความจำ (เช่นแต่ง "Hada Labo" ขึ้นมาจาก
    กระทู้ถาม j-beauty ที่ไม่มีคำตอบติดมาเลย)"""
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}", "User-Agent": REDDIT_USER_AGENT}
    resp = requests.get(f"https://oauth.reddit.com/comments/{post_id}", headers=headers,
                        params={"sort": "top", "limit": limit, "depth": 2, "raw_json": 1}, timeout=15)
    resp.raise_for_status()
    listing = resp.json()
    children = listing[1].get("data", {}).get("children", []) if isinstance(listing, list) and len(listing) > 1 else []
    return format_comment_tree(children, max_chars=max_chars)


def search_reddit_query(query, limit=POSTS_PER_QUERY, subreddits=None):
    """คืนค่า list ของ dict {"id", "title", "subreddit", "score", "num_comments", "created_utc",
    "selftext", "permalink"} - ดึงตรงจาก API ไม่ต้อง parse ข้อความดิบเหมือนหมวดอื่นเลย
    subreddits: ถ้าส่งมา ค้นเฉพาะใน subreddit เหล่านั้น (restrict_sr) แทนการค้นทั้ง Reddit"""
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}", "User-Agent": REDDIT_USER_AGENT}
    params = {"q": query, "limit": limit, "sort": "relevance", "type": "link", "raw_json": 1}
    url = SEARCH_URL
    if subreddits:
        url = f"https://oauth.reddit.com/r/{'+'.join(subreddits)}/search"
        params["restrict_sr"] = 1
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    posts = []
    for child in data.get("data", {}).get("children", []):
        d = child.get("data", {})
        posts.append({
            "id": d.get("id", ""),
            "title": d.get("title", ""),
            "subreddit": d.get("subreddit_name_prefixed", ""),
            "score": d.get("score", 0),
            "num_comments": d.get("num_comments", 0),
            "created_utc": d.get("created_utc"),
            "selftext": (d.get("selftext") or "")[:800],  # ตัดยาวเกินทิ้งกันข้อความบวมเกิน
            "permalink": "https://www.reddit.com" + d.get("permalink", ""),
        })
    return posts


def search_reddit(queries, subreddits=None):
    """คืนค่า list ของ dict {"query": ..., "posts": [...]} - ไม่ต้อง asyncio/browser แล้ว"""
    results = []
    for q in queries:
        print(f"=== ค้นหา: '{q}' บน Reddit (API) ===")
        try:
            posts = search_reddit_query(q, subreddits=subreddits)
            print(f"    เจอโพสต์ {len(posts)} รายการ")
            results.append({"query": q, "posts": posts})
        except Exception as e:
            print(f"    ⚠️ ค้นหา '{q}' ล้มเหลว: {e}")
            results.append({"query": q, "posts": []})
    return results


# --- 3. สรุปผลทั้งหมดเป็นสัญญาณเทรนด์ ---
SYSTEM_PROMPT_SUMMARY = """You are a trend analyst reading real Reddit posts returned from the
official Reddit Search API (structured data - each post has a title, subreddit, score/upvotes,
comment count, and a text excerpt if it's a text post). Summarize the signals found.

Important rule about numbers: each post's score/comment count belongs to that individual post only -
never sum them into an aggregate "trend strength" figure. Use "number of posts actually returned per
query" as the only basis for comparing how much discussion exists across different queries.

Answer in JSON: {"needs_and_pain_points": ["...", ...], "trend_signals": ["...", ...],
"notable_posts": [{"title": "...", "why_relevant": "..."}]}
Every conclusion must cite the actual content given - do not guess. If there isn't enough data, say so
briefly and honestly. Do not repeat the same point across different queries.
"""


def summarize_findings(topic, search_results):
    real_results = [r for r in search_results if r.get("posts")]
    if not real_results:
        return None
    blocks = []
    for r in real_results:
        lines = [f"--- Search results for '{r['query']}' | posts returned: {len(r['posts'])} ---"]
        for p in r["posts"]:
            snippet = f' | text: "{p["selftext"]}"' if p["selftext"] else ""
            lines.append(
                f'[{p["subreddit"]}] "{p["title"]}" | score: {p["score"]} | comments: {p["num_comments"]}{snippet}'
            )
        blocks.append("\n".join(lines))
    combined_text = "\n\n".join(blocks)
    user_prompt = f"Research topic: '{topic}'\n\n{combined_text}"
    try:
        response = tf.client.chat.completions.create(
            model=tf.MODEL_NAME_META,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_SUMMARY},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        return safe_json_parse(response.choices[0].message.content)
    except Exception as e:
        print(f"⚠️ Error summarizing: {e}")
        return None


# --- รัน pilot ---
if __name__ == "__main__":
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        print("❌ ไม่มี REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET ใน .env")
        print("   สมัครที่ https://www.reddit.com/prefs/apps -> create app -> เลือกประเภท 'script'")
        print("   แล้วใส่ REDDIT_CLIENT_ID=... และ REDDIT_CLIENT_SECRET=... ใน .env")
        raise SystemExit(1)

    print(f"หัวข้อ: {TOPIC}")
    queries = generate_english_queries(TOPIC, N_QUERIES)
    print(f"คำค้นที่สร้าง: {queries}")

    if not queries:
        print("❌ สร้างคำค้นไม่สำเร็จ หยุดทำงาน")
        raise SystemExit(1)

    search_results = search_reddit(queries)
    summary = summarize_findings(TOPIC, search_results)

    out_path = OUTPUTS / "reddit_discovery_pilot.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "topic": TOPIC,
            "queries": queries,
            "search_results": search_results,
            "summary": summary,
        }, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(json.dumps(summary, ensure_ascii=False, indent=2) if summary else "(ไม่มีผลสรุป - อาจไม่เจอโพสต์เลย)")
    print("=" * 80)
    print(f"\nSaved -> {out_path}")
