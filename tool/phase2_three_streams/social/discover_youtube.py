# -*- coding: utf-8 -*-
"""
Discover YouTube — หมวด "วิดีโอ" ของสาย Social (คู่กับ discover_pantip.py + discover_reddit.py)

สำเนา/ปรับจาก analysis/discover_youtube.py — เข้ากับโครง workspace/ (import tf ผ่าน bootstrap) และ
**แก้ age-blindness (2026-09-10, Backlog ข้อ 39 เฟส 0)** ที่เป็นเหตุผลถอด YouTube ออกจาก Workflow v2
ตอนแรก:
- `search_youtube()` ใส่ `publishedAfter` = now − 2 ปี ใน search.list → YouTube กรองคลิปเก่าให้ตั้งแต่
  ต้นทาง
- เก็บ `snippet.publishedAt` → ใส่ `published_at` ในผลลัพธ์ทุกคลิป
- กรอง `publishedAt` ซ้ำฝั่งเรา เผื่อ API คืนของเก่ากว่า cutoff (เคยเจอกับ Google News)

เครื่องมือ (ฟรีทั้งหมด): YouTube Data API v3 (YOUTUBE_API_KEY ใน .env) + youtube-transcript-api
(ดึง caption - **ทางหลัก**) + yt-dlp + faster-whisper (ถอดเสียง - **สำรอง**) + imageio-ffmpeg

🆕 (2026-09-10) `get_transcript()`: **transcript-api เป็นหลัก** (~1.5s/คลิป) → whisper สำรองเฉพาะ
คลิปที่ปิด caption และ ≤ 7 นาที - เจ้าของงานเลือกทางนี้หลังเห็นว่า transcript-api เร็วกว่า ~600 เท่า
คุณภาพต่างกันไม่มากสำหรับงานนี้ (ดู Backlog ข้อ 39) - social_stream ที่มี YouTube ช้าขึ้นแค่
~30 วินาที/รอบ (จากเดิมประเมิน ~90-135 นาที ถ้า whisper ล้วน)
"""
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

for _p in Path(__file__).resolve().parents:
    if (_p / "common" / "bootstrap.py").exists():
        sys.path.insert(0, str(_p))
        break
from common.bootstrap import PROJECT_ROOT, tf  # noqa: E402

import os  # noqa: E402
import requests  # noqa: E402

# --- ⚙️ ตั้งค่า ---
N_QUERIES = 3
MAX_VIDEOS_PER_QUERY = 3   # ~9 คลิป/รอบ (3 คำค้น x 3 คลิป)
MIN_DURATION_SEC = 120     # 🆕 ข้ามคลิปสั้นกว่า 2 นาที (Shorts/teaser - เนื้อหาบิวตี้ไทยตอนนี้เป็น
                           # Shorts เยอะมาก ~6-18 วิ ไม่มีบทพูดวิเคราะห์จริง ถอดเสียงได้ว่าง/เพลงล้วน)
MAX_DURATION_SEC = 900     # ตัดคลิปยาวเกิน 15 นาที กันต้นทุนถอดเสียง (ขยับจาก 600 - รีวิวเจาะลึกมักยาว)
WHISPER_MODEL_SIZE = "base"
YEARS_BACK = 2             # กรองคลิปเก่ากว่านี้ (เท่าสายอื่น) - ดู docstring

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


SYSTEM_PROMPT_QUERIES = """คุณคือนักวิจัยตลาดที่เชี่ยวชาญพฤติกรรมผู้บริโภคไทยบน YouTube
หน้าที่ของคุณคือสร้างคำค้นหาภาษาไทยที่คนไทยจริงๆ จะพิมพ์ค้นหาวิดีโอรีวิว/แนะนำสินค้าบน YouTube

กฎสำคัญ:
- ต้องเป็นคำค้นแบบที่คนไทยพิมพ์ค้นจริง ไม่ใช่การแปลคำภาษาอังกฤษตรงตัว
- สั้น กระชับ 2-5 คำ แบบที่คนพิมพ์ในกล่องค้นหาจริง
- ครอบคลุมมุมต่างกัน เช่น รีวิวสินค้า, แนะนำยี่ห้อ, เปรียบเทียบ

ตอบเป็น JSON เท่านั้น: {"queries": ["คำค้น 1", "คำค้น 2", ...]}
"""


def generate_thai_queries(topic, n=N_QUERIES):
    try:
        response = tf.client.chat.completions.create(
            model=tf.MODEL_NAME_META,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_QUERIES},
                {"role": "user", "content": f"หัวข้อ: '{topic}'\nสร้างคำค้น {n} คำ"},
            ],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        parsed = tf.safe_json_parse(response.choices[0].message.content)
        return parsed.get("queries", []) if parsed else []
    except Exception as e:
        print(f"⚠️ Error generating YouTube queries: {e}")
        return []


def parse_iso8601_duration(duration):
    """ISO 8601 duration (เช่น 'PT4M13S') -> วินาที"""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not m:
        return None
    h, mnt, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mnt * 60 + s


def search_youtube(query, max_results=MAX_VIDEOS_PER_QUERY, years_back=YEARS_BACK):
    published_after = (datetime.now(timezone.utc) - timedelta(days=365 * years_back)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "part": "snippet", "q": query, "type": "video", "maxResults": 50,  # ขอเยอะ เพราะกรอง
        "relevanceLanguage": "th", "regionCode": "TH", "key": YOUTUBE_API_KEY,  # ความยาว/อายุทิ้งเยอะ
        "publishedAfter": published_after, "videoDuration": "medium",  # medium = 4-20 นาที (เลี่ยง Shorts)
    }
    try:
        r = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=15)
        r.raise_for_status()
        items = r.json().get("items", [])
    except Exception as e:
        print(f"    ⚠️ YouTube search ล้มเหลวสำหรับ '{query}': {e}")
        return []

    video_ids = [it["id"]["videoId"] for it in items if it.get("id", {}).get("videoId")]
    if not video_ids:
        return []

    try:
        r2 = requests.get(YOUTUBE_VIDEOS_URL, params={
            "part": "contentDetails,snippet", "id": ",".join(video_ids), "key": YOUTUBE_API_KEY,
        }, timeout=15)
        r2.raise_for_status()
        detail_items = r2.json().get("items", [])
    except Exception as e:
        print(f"    ⚠️ YouTube videos.list ล้มเหลว: {e}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=365 * years_back)
    results = []
    for it in detail_items:
        duration_sec = parse_iso8601_duration(it["contentDetails"]["duration"])
        if duration_sec is None or not (MIN_DURATION_SEC <= duration_sec <= MAX_DURATION_SEC):
            continue
        sn = it["snippet"]
        published_at = sn.get("publishedAt", "")
        try:
            if published_at and datetime.fromisoformat(published_at.replace("Z", "+00:00")) < cutoff:
                continue
        except ValueError:
            pass
        results.append({
            "video_id": it["id"],
            "title": sn.get("title", ""),
            "description": sn.get("description", ""),
            "duration_sec": duration_sec,
            "published_at": published_at,
            "url": f"https://www.youtube.com/watch?v={it['id']}",
        })
        if len(results) >= max_results:
            break
    return results


WHISPER_FALLBACK_MAX_SEC = 420  # whisper fallback เฉพาะคลิป ≤ 7 นาที (ยาวกว่านี้ whisper บน CPU
                                # ช้าเกินคุ้ม - ข้ามคลิปนั้นไปเลย) - ดู get_transcript()


def _fetch_captions(video_id, languages=("th", "en")):
    """🆕 (2026-09-10) ดึง caption ผ่าน youtube-transcript-api - **ทางหลัก** (เร็ว ~1-2s/คลิป
    ไม่ต้อง download/whisper) รองรับทั้ง manual + auto-generated caption

    ทดสอบจริง: คลิปกันแดด 9.6/15 นาที → 7,380/15,024 ตัวอักษร ใน ~1.5s (whisper base ตัวเดียวกัน
    ใช้ 15+ นาที ยังไม่จบ) - auto-caption หยาบกว่า (ไม่มีวรรคตอน, ASR error บ้าง) แต่ชื่อสินค้า/
    แบรนด์/ความเห็นมาครบ พอสำหรับสกัดสัญญาณเทรนด์

    ⚠️ YouTube rate-limit ตาม IP ถ้ายิงเยอะ/เร็ว → error → fallback ไป whisper (get_transcript)

    คืน (text, is_generated) หรือ (None, None) ถ้าไม่มี caption / IP block / error
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None, None
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=list(languages))
        text = " ".join(s.text.strip() for s in fetched if s.text.strip())
        return (text or None), fetched.is_generated
    except Exception as e:
        print(f"    ⚠️ caption ไม่ได้ ({type(e).__name__}: {str(e)[:80]})")
        return None, None


_whisper_model = None


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        print(f"    กำลังโหลด Whisper model ({WHISPER_MODEL_SIZE})...")
        _whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return _whisper_model


def get_transcript(video):
    """🆕 (2026-09-10) transcript-api เป็นหลัก → whisper สำรอง (เฉพาะคลิปที่ปิด caption และ ≤ 7 นาที)

    เจ้าของงานเลือกทางนี้ (ตัวเลือก B) หลังเห็นว่า transcript-api เร็วกว่า whisper ~600 เท่า และ
    คุณภาพต่างกันไม่มากสำหรับงานสกัดสัญญาณเทรนด์ - ดู Backlog ข้อ 39

    คืน (text, source) - source คือ "manual_caption" | "auto_caption" | "whisper" - หรือ (None, None)
    🆕 (2026-09-15) คืน source ด้วย ให้ผู้เรียกบอก LLM ได้ว่าข้อความมาจากการถอดเสียงอัตโนมัติ ซึ่งชื่อสาร/
    แบรนด์เพี้ยนบ่อย (เจอจริง "pนtinol", "ไทอม" ที่ทำให้ LLM เดาชื่อสารในรายงาน)
    """
    text, is_generated = _fetch_captions(video["video_id"])
    # >= 500 ตัวอักษร ถึงจะถือว่า caption ใช้ได้จริง - เจอเคส caption ว่าง/พัง คืนมาแค่ 154 ตัวอักษร
    # สำหรับคลิป 6 นาที (auto-caption ล้มบางส่วน) → ต่ำกว่านี้ให้ตกไป whisper แทน
    if text and len(text) >= 500:
        source = "auto_caption" if is_generated else "manual_caption"
        print(f"    📝 [{source}] {video['title'][:45]} ({len(text)} ตัวอักษร)")
        return text, source
    if text:
        print(f"    ⚠️ caption สั้นผิดปกติ ({len(text)} ตัวอักษร) - ตกไป whisper")
    if video.get("duration_sec", 9999) > WHISPER_FALLBACK_MAX_SEC:
        print(f"    ⏭️  ข้าม (ไม่มี caption ใช้ได้ + ยาว {video.get('duration_sec')}s เกิน whisper fallback): "
              f"{video['title'][:45]}")
        return None, None
    print(f"    🎙️ [whisper fallback] {video['title'][:45]} (ไม่มี caption)...")
    text = download_and_transcribe(video)
    return (text, "whisper") if text else (None, None)


def download_and_transcribe(video):
    import yt_dlp
    import imageio_ffmpeg

    with tempfile.TemporaryDirectory() as tmpdir:
        out_template = str(Path(tmpdir) / "%(id)s.%(ext)s")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
            "quiet": True, "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video["url"]])
        except Exception as e:
            print(f"    ⚠️ ดาวน์โหลดล้มเหลว '{video['title'][:40]}': {e}")
            return None

        audio_files = list(Path(tmpdir).glob(f"{video['video_id']}.*"))
        if not audio_files:
            print(f"    ⚠️ ไม่พบไฟล์เสียง '{video['title'][:40]}'")
            return None

        try:
            model = get_whisper_model()
            segments, info = model.transcribe(str(audio_files[0]), language="th")
            return " ".join(seg.text.strip() for seg in segments)
        except Exception as e:
            print(f"    ⚠️ ถอดเสียงล้มเหลว '{video['title'][:40]}': {e}")
            return None
