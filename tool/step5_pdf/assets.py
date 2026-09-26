# -*- coding: utf-8 -*-
"""
⑯ PDF Report — รูปภาพที่ฝังในรายงาน (รูปสินค้า Watsons, โลโก้, กราฟ SVG)

ทุกรูปฝังเป็น data URI ใน HTML ก้อนเดียว - Chromium พิมพ์ PDF ได้โดยไม่ต้องเปิดไฟล์ในเครื่อง (file://) และไม่ต้องมี
เซิร์ฟเวอร์ รูปสินค้าย่อเหลือด้านยาว 480px ก่อนฝัง (ต้นฉบับ ~140KB/รูป x 50 รูป ทำให้ PDF ใหญ่เกินจำเป็น)

รูปสินค้าเก็บ cache ไว้ที่ output/_checkpoints/product_images/ (ข้ามรอบได้ - รูปของ SKU เดิมไม่ขึ้นกับหัวข้อ)
โหลดไม่ได้ (ไม่มีเน็ต/ลิงก์ตาย) -> คืน None แล้วเทมเพลตแสดงกล่องชื่อสินค้าแทน ไม่ทำให้รายงานพัง
"""
import base64
import hashlib
import io
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image

MAX_SIDE = 480
TIMEOUT = 20


def data_uri(raw, mime):
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def svg_data_uri(svg):
    return data_uri(svg.encode("utf-8"), "image/svg+xml") if svg else None


def file_data_uri(path):
    """ไฟล์ในเครื่อง (โลโก้) -> data URI, ไม่มีไฟล์ -> None"""
    path = Path(path) if path else None
    if not path or not path.is_file():
        return None
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if path.suffix.lower() == ".svg":
        mime = "image/svg+xml"
    return data_uri(path.read_bytes(), mime)


def _to_jpeg(raw):
    """ย่อรูปแล้วแปลงเป็น JPEG พื้นขาว (PNG โปร่งใสของ Watsons จะกลายเป็นพื้นดำถ้าแปลงตรงๆ)"""
    img = Image.open(io.BytesIO(raw))
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img, mask=img.getchannel("A"))
        img = bg
    else:
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85, optimize=True)
    return out.getvalue()


def fetch_image(url, cache_dir):
    """URL รูปสินค้า -> data URI (ใช้ cache ถ้ามี) หรือ None ถ้าโหลด/อ่านรูปไม่ได้"""
    if not url:
        return None
    cache_dir = Path(cache_dir)
    cache_path = cache_dir / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}.jpg"
    if cache_path.exists():
        return data_uri(cache_path.read_bytes(), "image/jpeg")
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        jpeg = _to_jpeg(resp.content)
    except Exception:  # noqa: BLE001 - รูปเดียวพังไม่ควรหยุดรายงาน
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(jpeg)
    return data_uri(jpeg, "image/jpeg")


def attach_product_images(trends, cache_dir, max_workers=8, log=print):
    """เติม product["image"] (data URI หรือ None) ให้ทุกสินค้าของทุกเทรนด์ - โหลดพร้อมกันหลายรูป"""
    products = [p for t in trends for p in t.get("products", [])]
    urls = sorted({p["image_url"] for p in products if p.get("image_url")})
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        uris = dict(zip(urls, pool.map(lambda u: fetch_image(u, cache_dir), urls)))
    for p in products:
        p["image"] = uris.get(p.get("image_url"))
    n_ok = sum(1 for u in uris.values() if u)
    if n_ok < len(urls):
        log(f"  ⚠️ โหลดรูปสินค้าได้ {n_ok}/{len(urls)} รูป - ที่เหลือแสดงเป็นกล่องชื่อสินค้าแทน")
    return n_ok, len(urls)
