# -*- coding: utf-8 -*-
"""ส่วนที่ไปป์ไลน์ v2 ใช้จริงจาก `trend_final.py` - คัดลอกตรงตัว ไม่ได้เขียนใหม่

ทำไมมีไฟล์นี้ (2026-09-22): ให้ทุกอย่างที่ `main/` ต้องใช้อยู่ใน `main/` เอง โดยไม่ย้ายหรือแก้ `trend_final.py`
ต้นฉบับ (ต้นฉบับไม่ถูกแก้ - ย้ายไปเก็บที่ `_archive/root_legacy_20260922/` แล้ว) - ใช้ผ่านชื่อ `tf` ใน `common/bootstrap.py`

วิธีคัด: เริ่มจากชื่อที่โค้ดใน `main/` เรียกผ่าน `tf.xxx` จริง (ไล่ด้วย AST ไม่นับ docstring) แล้วไล่ต่อว่า
statement นั้นใช้ชื่ออะไรในไฟล์เดียวกันอีก จนครบ - ทุกบล็อกมีป้าย `# [trend_final.py Lก-Lข]` บอกบรรทัดต้นฉบับ
และเรียงตามลำดับเดิมในไฟล์ต้นฉบับ

ต่างจากต้นฉบับ (ตั้งใจ):
- บล็อกที่มีป้าย "⚠️ แก้จากต้นฉบับ" - `_TOOLS_DIR` ชี้ `main/` แทนโฟลเดอร์ของไฟล์นี้
- ไม่คัดมา: `if not TAVILY_API_KEY: sys.exit(1)` (Tavily ไม่มีฟังก์ชันไหนในไฟล์นี้ใช้) และ `if __name__ == "__main__"`

ตรวจสอบ: `tool/tests/test_trend_final_subset.py` - (1) ไม่มีชื่อ global ที่หานิยามไม่เจอ (2) ถ้าพบต้นฉบับ (root หรือ
_archive/root_legacy_20260922/) จะเทียบทุกบล็อกว่ายังตรงตัวอักษร (บล็อกที่มีป้าย ⚠️ ข้ามได้) และเทียบผลของฟังก์ชันกับต้นฉบับ
ถ้าจะแก้บล็อกไหนโดยตั้งใจ ให้ใส่ "⚠️ แก้จากต้นฉบับ: <เหตุผล>" ในป้ายของบล็อกนั้น
"""
# [trend_final.py L1-L1]
import os


# [trend_final.py L3-L3]
import json


# [trend_final.py L6-L6]
from pathlib import Path


# [trend_final.py L7-L7]
from openai import OpenAI


# [trend_final.py L14-L14]
from apify_client import ApifyClient


# [trend_final.py L15-L15]
import re


# [trend_final.py L16-L16]
import requests


# [trend_final.py L30-L30]
from googlenewsdecoder import gnewsdecoder


# [trend_final.py L31-L31]
import requests


# [trend_final.py L35-L35]
from dotenv import load_dotenv


# [trend_final.py L46-L46] ⚠️ แก้จากต้นฉบับ: ต้นฉบับชี้โฟลเดอร์ของไฟล์ตัวเอง (root) - ย้ายฐานมาที่ main/ ให้ .env และ config/ อยู่ใน main/
_TOOLS_DIR = Path(__file__).resolve().parents[2]  # = main/ -> .env อยู่ที่ main/.env, config อยู่ที่ main/config/


# [trend_final.py L47-L47]
_API_DIR = _TOOLS_DIR


# [trend_final.py L50-L50]
env_path = _API_DIR / ".env"


# [trend_final.py L51-L51]
load_dotenv(dotenv_path=env_path)


# [trend_final.py L64-L64]
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


# [trend_final.py L66-L66]
MODEL_NAME = os.getenv("MODEL_NAME")


# [trend_final.py L70-L70]
MODEL_NAME_META = os.getenv("MODEL_NAME_META")


# [trend_final.py L71-L71]
APIFY_API_KEY = os.getenv("APIFY_API_KEY")


# [trend_final.py L72-L72]
MODEL_CONTEXT_LIMIT = 230000 


# [trend_final.py L73-L73]
SAFE_MAX_TOKENS = 16000 


# [trend_final.py L77-L80]
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)


# [trend_final.py L82-L82]
total_input_tokens = 0


# [trend_final.py L83-L83]
total_output_tokens = 0


# [trend_final.py L85-L85]
CACHE_FILE = "memory/scraped_cache.json"


# [trend_final.py L86-L86]
os.makedirs("memory", exist_ok=True)


# [trend_final.py L88-L97]
def load_scrape_cache() -> dict:
    """Load previously scraped articles from the local JSON cache."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"  [CACHE] Warning: Could not read cache file: {e}")
            return {}
    return {}


# [trend_final.py L99-L105]
def save_scrape_cache(cache_data: dict):
    """Save newly scraped articles back to the local JSON cache."""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"  [CACHE] Error saving cache: {e}")


# [trend_final.py L140-L140]
url_cache = load_scrape_cache()


# [trend_final.py L142-L152]
def compute_max_tokens(prompt: str):
    estimated_prompt_tokens = int(len(prompt) * 1.3)

    if estimated_prompt_tokens > MODEL_CONTEXT_LIMIT:
        raise ValueError(
            f"Prompt too large ({estimated_prompt_tokens}). Truncate input before calling LLM."
        )

    remaining = MODEL_CONTEXT_LIMIT - estimated_prompt_tokens
    print(f"[DEBUG] compute_max_tokens_impl: estimated_prompt_tokens={estimated_prompt_tokens}, remaining={remaining}")
    return max(6000, min(remaining, SAFE_MAX_TOKENS))


# [trend_final.py L154-L173]
def clean_json_string(raw_text):
    if not raw_text:
        return ""
    
    clean_text = raw_text.strip()
    # ลบแท็ก ```json และ ``` ออก
    if clean_text.startswith("```json"):
        clean_text = clean_text[7:]
    elif clean_text.startswith("```"):
        clean_text = clean_text[3:]
        
    if clean_text.endswith("```"):
        clean_text = clean_text[:-3]
        
    # ใช้ Regex ช่วยหาเฉพาะส่วนที่เป็น [...] หรือ {...} ในกรณีที่ AI พูดอารัมภบท
    match = re.search(r'(\{.*\}|\[.*\])', clean_text.strip(), re.DOTALL)
    if match:
        return match.group(0)
        
    return clean_text.strip()


# [trend_final.py L175-L290]
def safe_json_parse(content: str):
    """
    Robust JSON parser for LLM responses.
    Handles Llama 3 over-escaping, code fences, Python literals, and trailing commas.
    Dynamically supports both JSON Objects {} and Arrays [].
    """
    if not content or not isinstance(content, str):
        print("⚠️ Empty or invalid response from AI.")
        return None

    content = content.strip()

    # 1️⃣ FIX: Remove over-escaped quotes generated by smaller models like Llama 3
    content = content.replace('\\"', '"')

    # 2️⃣ Remove markdown code fences
    if content.startswith("```"):
        content = re.sub(r"```json|```", "", content).strip()

    # 3️⃣ Normalize common LLM JSON mistakes
    content = content.replace("None", "null")
    content = content.replace("True", "true")
    content = content.replace("False", "false")
    # Remove trailing commas right before closing braces/brackets
    content = re.sub(r",\s*([}\]])", r"\1", content)

    # ➕ Special case: some models return Python set-like syntax {"a","b"}
    # which is invalid JSON.  Convert to JSON array automatically.
    if content.startswith("{") and content.endswith("}") and ":" not in content:
        inner = content[1:-1].strip()
        # split on commas while respecting quoted strings
        items = re.split(r"\s*,\s*", inner)
        cleaned_items = []
        for itm in items:
            itm = itm.strip()
            if not itm:
                continue
            # ensure double quotes
            if itm.startswith("'") and itm.endswith("'"):
                itm = '"' + itm[1:-1] + '"'
            elif itm.startswith('{') or itm.endswith('}'):
                # just in case nested braces remain
                itm = itm.strip('{}')
            cleaned_items.append(itm)
        try:
            content = "[" + ",".join(cleaned_items) + "]"
        except Exception:
            pass

    # ➕➕ Additional pass: convert set-like elements embedded within arrays
    # e.g. [{"a"}, {"b"}] or [{'x'}] into ["a","b"].
    # This is a common response format from some LLMs that produced
    # an array of single-item sets.  We replace any `{value}` where value
    # contains no colon to a quoted string, which preserves legitimate
    # objects/dicts with colon separators.  This runs globally on the
    # content string prior to attempting JSON loads below.
    def _replace_inner_set(match):
        inner_val = match.group(1).strip()
        # already quoted?
        if (inner_val.startswith('"') and inner_val.endswith('"')) or (
            inner_val.startswith("'") and inner_val.endswith("'")
        ):
            return inner_val
        return '"' + inner_val + '"'

    content = re.sub(r"\{\s*([^:{}]+?)\s*\}", _replace_inner_set, content)

    # 4️⃣ Try direct load
    try:
        return json.loads(clean_json_string(content))
    except json.JSONDecodeError:
        pass

    # 5️⃣ Extract JSON object OR array dynamically (handles conversational wrapper text)
    match = re.search(r"(\{.*?\}|\[.*?\])", content, re.DOTALL)
    if match:
        extracted = match.group(1)
        try:
            return json.loads(clean_json_string(extracted))
        except json.JSONDecodeError:
            content = extracted # Proceed to balancing with the extracted text

    # 6️⃣ Brace & Bracket balancing repair
    open_braces = content.count("{")
    close_braces = content.count("}")
    if open_braces > close_braces:
        content += "}" * (open_braces - close_braces)

    open_brackets = content.count("[")
    close_brackets = content.count("]")
    if open_brackets > close_brackets:
        content += "]" * (open_brackets - close_brackets)

    try:
        return json.loads(clean_json_string(content))
    except json.JSONDecodeError:
        pass

    # 7️⃣ Final fallback: extract largest JSON-like Object or Array
    possible_json = re.findall(r"\{.*\}", content, re.DOTALL)
    for candidate in possible_json:
        try:
            return json.loads(clean_json_string(candidate))
        except:
            continue
            
    possible_array = re.findall(r"\[.*\]", content, re.DOTALL)
    for candidate in possible_array:
        try:
            return json.loads(clean_json_string(candidate))
        except:
            continue

    print("❌ JSON unrecoverable. Preview:")
    print(content[:500])
    return None


# [trend_final.py L584-L663]
def generate_trend_report_with_llm(topic: str, scraped_data: list) -> str:
    global total_input_tokens, total_output_tokens
    print(f"🧠 [RSS 5/5] Synthesizing data to generate an in-depth Trend Report...")
    
    # 1. Prepare the context with Titles, Sources, URLs, and Content in English
    combined_context = ""
    for idx, data in enumerate(scraped_data):
        combined_context += f"--- Reference Article {idx+1} ---\n"
        combined_context += f"Title: {data.get('title', 'No Title')}\n"
        combined_context += f"Content: {data.get('content', '')}\n\n"

    # ==============================
    # 2. SYSTEM PROMPT (Translated to English)
    # ==============================
    system_prompt = """
    You are a Senior Market Intelligence & Strategy Analyst. Your goal is to transform raw search data into a high-level Strategic Trend Report.

    CORE OPERATING DIRECTIVES:
    1. DATA-ONLY MODE: Base every insight, percentage, and brand mention EXCLUSIVELY on the provided Raw Data. If the data isn't there, do not mention it.
    2. THE "WHY" & "HOW" FOCUS: For every trend identified (e.g., JK Beauty or Amino Science), explain the underlying mechanism (e.g., consumer need for 'mass-prestige' or technical cross-over from food science).
    3. LANGUAGE: The output MUST be 100% Professional English. 
    4. STYLE: Use formal business terminology. Use terms like 'Market Disruption,' 'Consumer Pain Points,' and 'Strategic Pillars.'
    """
    
    # ==============================
    # 3. USER PROMPT (Translated to English)
    # ==============================
    user_prompt = f"""
    Write a comprehensive "In-Depth Market Trend Analysis Report" on: "{topic}"

    Please follow this strict Markdown structure:

    # 📊 Deep-Dive Trend Analysis Report: {topic}

    ## 1. Executive Summary
    - Provide a high-level synthesis of the market state. 
    - Highlight the single most critical opportunity (e.g., expansion into the 50 million-strong Thai middle class by 2030).

    ## 2. Deep-Dive Market Trends & Consumer Insights
    - **Needs & Pain Points:** Detail what consumers are missing (e.g., trust in ingredients or access to J-Beauty/K-Beauty trends).
    - **Trend Mechanisms:** Identify top ingredients (e.g., Amino Acids, PDRN) and explain why they are trending based on the provided text.

    ## 3. Market Drivers & Business Opportunities
    - **Impact Mechanisms:** How do external factors (e.g., post-COVID health focus) translate into specific product sales (e.g., growth in Dermocosmetics)?
    - **Whitespace Analysis:** Identify gaps where mainstream brands (the "Top 5") have less than 10% market share, creating room for new entrants.

    ## 4. Competitive Landscape & Brand Movements
    - **Tactical Analysis:** Compare strategies like 'One L'Oréal' (Omnichannel + AI) vs. 'found & found' (JK Beauty Mass Retail).
    - **Brand Proof Points:** List specific products (e.g., CeraVe, La Roche-Posay refillables) mentioned in the data.

    Raw Data (References):
    {combined_context}
    """
    
    full_prompt = system_prompt + user_prompt
    
    try:
        max_tokens = compute_max_tokens(full_prompt)
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1, 
            max_tokens=max_tokens
        )
        if hasattr(response, 'usage') and response.usage:
            total_input_tokens += getattr(response.usage, 'prompt_tokens', 0)
            total_output_tokens += getattr(response.usage, 'completion_tokens', 0)
            
        content = response.choices[0].message.content
        if content is None:
            print("⚠️ LLM API returned an empty response (possible context limit or safety policy block).")
            return ""
            
        return content.strip()
    except Exception as e:
        print(f"❌ LLM Error during report generation: {e}")
        return ""


# [trend_final.py L665-L704]
def load_feed_config():
    """อ่านรายการแหล่งข่าวจาก config/rss_feeds.json - แก้แหล่งได้โดยไม่ต้องแตะโค้ด
    ถ้าไฟล์หาย/พัง จะ fallback ไปใช้ค่า default ที่ฝังไว้ในโค้ด เพื่อไม่ให้ pipeline ล้มทั้งรอบ"""
    default_groups = {
        "Scientific_Papers": ["https://www.sciencedaily.com/rss/health_medicine/cosmetics.xml"],
        "B2B_Industry": [
            "https://www.globalcosmeticsnews.com/feed/",
            "https://www.glossy.co/beauty/feed/",
            "https://theindustry.beauty/feed/",
            "https://www.trendhunter.com/rss/category/Cosmetics-and-Beauty-Trends",
            "https://britishbeautycouncil.com/feed/",
            "https://cosmeticsbusiness.com/rss",
            "https://www.premiumbeautynews.com/spip.php?page=backend&lang=en",
        ],
        "B2C_Review": [
            "https://makeupandbeautyblog.com/feed/",
            "https://phyrra.net/feed",
            "https://thedermreview.com/feed/",
        ],
        "Market": [
            "https://www.mintel.com/insights/beauty-and-personal-care/feed/",
            "https://baramizilab.co.th/trend-reports/feed/",
            "https://brandinside.asia/feed/",
        ],
    }
    default_domains = ["vogue.co.th", "ellethailand.com", "wongnai.com", "lemon8-app.com",
                       "thestandard.co", "tiktok.com", "brandinside.asia", "mdpi.com"]

    cfg_path = _TOOLS_DIR / "config" / "rss_feeds.json"
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        groups = {k: v for k, v in (cfg.get("rss_groups") or {}).items() if v}
        domains = cfg.get("google_news_domains") or []
        if not groups:
            raise ValueError("rss_groups ว่างเปล่า")
        return groups, (domains or default_domains)
    except Exception as e:
        print(f"  ⚠️ อ่าน {cfg_path} ไม่ได้ ({e}) - ใช้รายการแหล่งข่าว default ในโค้ดแทน")
        return default_groups, default_domains


# [trend_final.py L831-L866]
def process_and_clean_content(raw_text: str) -> str:
    """ฟังก์ชันตัวช่วยล้างขยะ (HTML/เว้นวรรค) จากข้อมูลที่ Tavily กวาดมาได้"""
    if not raw_text or not isinstance(raw_text, str):
        return ""
    lines = raw_text.splitlines()
    cleaned_lines = []
    headline_removed = False
    inside_html_headline = False

    for line in lines:
        stripped = line.strip()
        if not stripped: continue
        if not headline_removed and re.match(r'^#{1,6}\s+', stripped):
            headline_removed = True
            continue
        if not headline_removed and re.match(r'^<h[1-6][^>]*>', stripped, re.IGNORECASE):
            headline_removed = True
            if not re.search(r'</h[1-6]>', stripped, re.IGNORECASE): inside_html_headline = True
            continue
        if inside_html_headline:
            if re.search(r'</h[1-6]>', stripped, re.IGNORECASE): inside_html_headline = False
            continue
        if re.match(r'^[\|\-+=•—–]{3,}$', stripped): continue
        if re.match(r'^\[.*\]:\s*https?://', stripped): continue
        if re.match(r'^(read more|source|references?|page\s+\d+|copyright|©)', stripped, re.IGNORECASE): continue
        cleaned_lines.append(stripped)

    filtered_text = " ".join(cleaned_lines)
    normalized = re.sub(r"\s+", " ", filtered_text)
    normalized = re.sub(r"[^\w\s\u0E00-\u0E7F]", " ", normalized)
    normalized = normalized.strip()

    if len(normalized) < 50:
        fallback = re.sub(r"\s+", " ", raw_text).strip()
        return fallback[:2000]
    return normalized


# [trend_final.py L2203-L2203]
import os
