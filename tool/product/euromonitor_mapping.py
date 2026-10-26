# -*- coding: utf-8 -*-
"""
จัดสินค้าเข้า taxonomy 4 ระดับใน product_category.csv (Industry > Category > Sub-category > Segment ตามแบบ Euromonitor)
แคตตาล็อกตั้งแต่ 2026-10-11 = Konvy (konvy_product.csv) - เดิม Watsons; ข้อมูลตัวเลขในหัวข้อ "ข้อมูลที่ต้องรู้" ด้านล่างเป็นของ Watsons
(Konvy: Segment ของแถวความงาม 27,098 แถวตรงกับ Level 4 ของไฟล์นี้ 100% และ path 4 ระดับครบอยู่ใน taxonomy ทุกแถว)
- ไม่เรียก API/LLM ผลคงที่ทุกครั้งที่รัน
- product_category.csv คือแหล่งความจริงเดียว: อ่านตอนรัน และตรวจว่าทุกชื่อ Segment ที่กฎอ้างถึงมีอยู่ในไฟล์จริง (พิมพ์ผิด = error ตอน import)

ข้อมูลที่ต้องรู้ก่อนแก้กฎ
1) Segment ของ Watsons (9,690 จาก 10,622 แถว) ตรงกับ Level 4 ของไฟล์นี้ 100% -> ใช้เป็นฐาน
2) Level 4 ซ้ำใต้หลาย parent 28 ค่า (เช่น "Products For Shaving" อยู่ทั้ง Men's Grooming และ Depilatories, "Cream" อยู่ใต้ Premium และ
   Mass Basic Moisturisers) -> resolve() ตัดสิน Level 2/3 จากชื่อสินค้า (เพศ ฯลฯ) ส่วน Premium/Mass ข้อมูลไม่มีให้แยก
   จึงเว้น Level 3 ว่าง (EM_L3 = "") ไม่เดา
3) ป้าย Watsons (Category/Segment/Product_Type และข้อความ enrichment) เสียบางแถว เช่น ผ้าอนามัย Sofy ติดป้าย Men's Shaving,
   น้ำหอมติดป้าย Lipstick และกลุ่ม "Other Skin Cleansing" เป็นถังรวมของที่ไม่เข้าหมวด -> ให้ชื่อสินค้า/Product_Type ตรวจก่อนเชื่อป้าย

ลำดับ (ชนะตัวแรก)
  1. RULES_PRODUCT   Product_Type/ชื่อ ชี้ชนิดสินค้าชัด (ของนอกความงาม เครื่องมือ ผ้าอนามัย ฯลฯ) -> Level 4 ตรงๆ
  2. RULES_BEAUTY    ชนิดสินค้าความงามที่ชัด (กันแดด สบู่ น้ำหอม ฯลฯ) - ถ้า Segment ของ Watsons อยู่ Level 2 เดียวกันให้เก็บ Segment ไว้ (ละเอียดกว่า)
  3. Segment ของ Watsons (ถ้าเป็นถังรวมให้ refine ด้วย Product_Type)
  4. Sub_category / Category ของ Watsons (เมื่อไม่มี Segment)
  5. NAME_HINTS      คำในชื่อสินค้าที่ชี้ Level 2 ต่างจากป้าย -> เชื่อชื่อ (ป้ายเสีย)
  6. ไม่เข้ากฎ -> Unmapped

ผลต่อแถว: EM_L1..EM_L4, EM_Group (ระดับที่ใช้จัดกลุ่มในรายงาน = GROUP_LEVEL), EM_status (mapped|unmapped), EM_source, EM_confidence
"""
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
TAXONOMY_PATH = HERE / "product_category.csv"
# แคตตาล็อกสินค้า = market_product.csv จาก build_market_catalog.py (ตัด stock<=0 / เลนส์แล้ว) - ตั้งแต่ 2026-10-19 สร้างด้วย --no-eve = Konvy ล้วน
# (ช่วง 2026-10-15..19 เป็นตลาดรวม Konvy + Eve and Boy; Eve ไม่มียอดขาย จึงถอดออก - ไฟล์รวมเดิมสำรองที่ output/_backups/konvy_only_sales_20261019/catalog/)
# Konvy ล้วน (ตั้งแต่ 2026-10-11, เดิม watsons_product.csv) = konvy_product.csv จาก build_konvy_catalog.py - จะย้อนกลับให้เปลี่ยนบรรทัดนี้
# และ PRODUCT_CSV ใน phase6_pdf_report/build_pdf_report.py ให้ตรงกัน (tests/test_market_catalog.py ตรวจว่าตรงกัน)
CSV_PATH = HERE / "market_product.csv"
MAP_PATH = HERE / "euromonitor_category_map.csv"
LLM_LABELS_PATH = HERE / "euromonitor_llm_labels.jsonl"   # ผลที่ LLM จัดหมวด (classify_products_llm.py) - ตัวหลักเมื่อมี; กฎในไฟล์นี้เป็นตัวสำรอง
GROUP_LEVEL = "L2"   # EM_Group = ระดับนี้ (L1..L4) - รายงานเลือกระดับแสดงผลที่นี่ที่เดียว (เจ้าของงานเลือก L2 2026-10-01)
BEAUTY = "Beauty and Personal Care"
BEAUTY_L1 = BEAUTY   # load_catalog() กรองเอาเฉพาะ L1 นี้
UNMAPPED = "Unmapped"


# ---------------------------------------------------------------- taxonomy ------------------------------------------
def load_taxonomy(path=TAXONOMY_PATH):
    t = pd.read_csv(path, encoding="utf-8-sig").iloc[:, :4]
    t.columns = ["L1", "L2", "L3", "L4"]
    for c in t.columns:
        t[c] = t[c].astype(str).str.strip()
    return [tuple(r) for r in t.drop_duplicates().itertuples(index=False, name=None)]


PATHS = load_taxonomy()                 # [(L1, L2, L3, L4)] ตามลำดับในไฟล์
PATH_BY_ID = {i: p for i, p in enumerate(PATHS, start=1)}   # รหัสที่ส่งให้ LLM เลือก (1..N ตามลำดับในไฟล์)
BY_L4 = defaultdict(list)
for _p in PATHS:
    BY_L4[_p[3]].append(_p)

L2_NAMES = {_p[1] for _p in PATHS}   # ชื่อ Level 2 ทั้งหมดของ taxonomy
TIER = re.compile(r"^(Premium|Mass) ")
MEN = re.compile(r"\bmen\b|men's|\bmale\b|for him|\bhomme\b|\bboys?\b|gentlemen|ผู้ชาย")
WOMEN = re.compile(r"\bwomen\b|women's|ladies|\blady\b|\bfemale\b|venus|\bfemme\b|for her|ผู้หญิง")

# L4 ที่อยู่ใต้ Level 2 หลายที่ -> Level 2 ตั้งต้น (ถ้าไม่มีสัญญาณเพศ)
DEFAULT_L2 = {"Other Hair Care": "Hair Care", "Products With Antiperspirant Activity": "Deodorants",
              "Personal Set /kits": BEAUTY, "Mass Fragrances": "Fragrances", "Premium Fragrances": "Fragrances"}
# L4 ที่ Level 3 ต้องดูจากข้อความ: L4 -> [(regex บนข้อความ, L3)] + ค่าตั้งต้น (ตัวสุดท้าย regex=None)
L3_BY_TEXT = {
    "B&C Toiletries": [(r"wipe", "Baby Wipes"), (None, "Baby and Child-specific Toiletries")],
    "Colour Cosmetics Set": [(None, "Colour Cosmetics Sets/Kits")],
    "Deodorant Pumps": [(r"spray", "Deodorant Sprays"), (None, "Deodorant Pumps")],
    "Other Lip Products": [(r"liner|pencil", "Lip Liner/Pencil"), (None, "Lip Products")],
    "Other Oral Hygiene Products": [(r"floss|interdental", "Dental Floss"), (r"denture", "Denture Care"), (None, "Oral Care")],
    "Other Tooth Care Products": [(r"electric.*(head|refill)|(head|refill).*electric", "Electric Toothbrush Replacement Heads"),
                                  (r"electric", "Electric Toothbrush Units"), (r"battery", "Battery Toothbrush Units"),
                                  (r"manual", "Manual Toothbrushes"), (None, "Toothbrushes")],
    "General Body Moisturizer": [(None, "Body Care")],
    "Men's Skincare": [(None, "Men's Skin Care")],
    "Other Facial Make-Up": [(None, "Facial Make-Up")],
    "Sun Protection": [(None, "Sun Protection")],
}


def resolve(l4, text="", l2=None):
    """L4 -> (L1, L2, L3, L4) ตัดสิน Level 2/3 เมื่อ L4 อยู่ใต้หลาย parent จากเพศ/คำในชื่อ; Premium/Mass แยกไม่ได้ -> L3 = ''"""
    cands = BY_L4[l4]
    if l2:
        cands = [p for p in cands if p[1] == l2] or cands
    if len({p[1] for p in cands}) > 1:   # คนละ Level 2
        men, women = bool(MEN.search(text)), bool(WOMEN.search(text))
        if l4 in ("Products For Shaving", "Pre- / After-Shaving Products"):
            want = "Depilatories" if women and not men else "Men's Grooming"
        elif l4 == "Products With Antiperspirant Activity":
            want = "Men's Grooming" if men and not women else "Deodorants"
        elif l4 == "Other Hair Care":
            want = "Men's Grooming" if men and not women else "Hair Care"
        else:
            want = DEFAULT_L2.get(l4, cands[0][1])
        cands = [p for p in cands if p[1] == want] or cands
    if len(cands) == 1:
        return cands[0]
    l3s = [p[2] for p in cands]
    if l4 in ("Premium Fragrances", "Mass Fragrances"):   # เพศของน้ำหอม: ไม่มีสัญญาณ -> L3 กลาง (ชื่อเดียวกับ L4)
        tier = l4.split()[0]
        men, women = bool(MEN.search(text)), bool(WOMEN.search(text))
        if men != women:
            pick = f"{tier} {'Men' if men else 'Women'}'s Fragrances"
            if pick in l3s:
                return next(p for p in cands if p[2] == pick)
    for pattern, l3 in L3_BY_TEXT.get(l4, []):
        if (pattern is None or re.search(pattern, text)) and l3 in l3s:
            return next(p for p in cands if p[2] == l3)
    if all(TIER.match(x) for x in l3s) and len({TIER.sub("", x) for x in l3s}) == 1:
        return (cands[0][0], cands[0][1], "", l4)    # Premium/Mass ต่างกันอย่างเดียว -> ข้อมูลไม่พอ ไม่เดา
    same = [p for p in cands if p[2] == l4]
    return (same or cands)[0]


# ---------------------------------------------------------------- กฎ -----------------------------------------------
def _c(pattern):
    return re.compile(pattern) if pattern else None


# (ชื่อกฎ, regex บน Product_Type, regex บนชื่อสินค้า, L4) - ชื่อสินค้าใช้เสริมเพราะ Product_Type เสียบางแถว
# 1) ชนิดสินค้าที่ชัด: ใช้กับทุกแถว
RULES_PRODUCT = [
    # --- สุขภาพ / ตา
    ("lens_solution", r"lens solution|multi-?purpose solution|lens (cleaning|care)|lens drops", r"contact lens (care|solution)|lens solution|aosept", "Contact Lens Solution"),
    ("eye_drops", r"eye drops?", r"eye drops?", "Eye Drops"),
    ("lens_daily", r"(daily|1[- ]?day|one ?day).*lens", r"(daily|1[- ]?day|one ?day).*(lens|[-−]\d\.\d\d\b)", "Daily Disposable Contact Lens"),
    ("lens", r"contact lens|\blenses\b|color lens|soft lens", r"contact ?lens|[-−]\d\.\d\d\b.*(\(\d+ ?pcs?|monthly|month\b)", "Monthly Contact Lens"),
    # --- ผ้าอนามัยและของใช้ส่วนตัว (อยู่ใต้ Bath and Shower > Intimate Hygiene)
    ("period_panties", r"period (panty|panties|pants)|sanitary (underwear|pants)", r"period (panty|panties|pants)", "Period Panties"),
    ("menstrual_cup", r"menstrual (cup|disc)", r"menstrual (cup|disc)", "Menstrual Cups & Discs"),
    ("tampon", r"tampon", r"tampon", "Tampons"),
    ("intimate_wash", r"intimate (cleans|wash|care|wipe)|feminine (cleans|wash|wipe)|lady wipe|feminine hygiene",
     r"lady wipe|intimate (wash|cleans)|feminine wash|saugella", "Intimate Wash & Wipes"),
    ("sanitary", r"sanitary|napkin|pant[iy] ?liners?|breathable liners|panty pad", r"sanitary|napkin|pant[iy] ?liners?|corn pad|panty pad|\bsofy\b|laurier|kotex|ผ้าอนามัย", "Sanitary Pads & Liners"),
    ("adult_diaper", r"adult diaper|incontinence", r"adult diaper|lifree", "Adult Incontinence"),
    ("baby_diaper", r"^(baby )?(diapers?|nappies)( pants)?$|diaper pants|nappy pants", r"baby diaper|diaper pants", "Baby Diapers"),
    ("condom", r"condom", r"condom|durex|okamoto", "Condoms"),
    ("lubricant", r"lubricant|lube", r"lubricant", "Lubricants"),
    # --- ของใช้ในบ้าน
    ("laundry", r"laundry|detergent", r"laundry|detergent", "Laundry Detergent"),
    ("fabric_softener", r"fabric (softener|spray|freshener)|softener", r"fabric softener|fabric freshener", "Fabric Softener & Freshener"),
    ("stain", r"stain remover|(?<!hair )bleach", r"stain remover", "Stain Remover & Bleach"),
    ("floor_cleaner", r"floor cleaner|multi-surface|surface cleaner|kitchen cleaner|toilet (bowl|cleaner)|bathroom cleaner|glass cleaner", r"floor cleaner|multi-surface", "Floor & Surface Cleaner"),
    ("dishwash", r"dish ?wash", r"dish ?wash", "Dishwashing Liquid"),
    ("sponge_cloth", r"^cloths?$|^sponges?$|scrub sponge|scouring|scrubbing net|scrubber", r"scrub sponge|scotch.?brite", "Sponges, Cloths & Scrubbers"),
    ("mop", r"\bmop\b|cleaning (tool|brush)", None, "Mops & Cleaning Tools"),
    ("air_freshener", r"air freshener|room spray|toilet deodori[sz]er|car freshener", r"air freshener", "Air Freshener & Deodorizer"),
    ("diffuser", r"diffuser|scented candle", None, "Room Diffuser & Scented Candles"),
    ("garbage_bag", r"garbage bag|trash bag", r"garbage bag", "Garbage Bags"),
    ("produce_wash", r"fruit (and|&) vegetable|vegetable wash", None, "Fruit & Vegetable Wash"),
    ("insect", r"insect|mosquito", r"insect repel|mosquito", "Insect Repellent & Insecticide"),
    ("tissue", r"facial tissues?|tissues?$|tissue paper", r"facial tissue|box tissues?", "Facial Tissue"),
    ("shower_filter", r"shower filter|shower head", r"shower filter", "Bathroom Accessories & Fittings"),
    # --- เสื้อผ้า
    ("bra", r"\bbras?\b|bra straps|nipple cover|silicone bra|adhesive bra", r"\bbra\b|nipple cover", "Bras & Bra Accessories"),
    ("underwear", r"underwear|panty|panties|briefs?|boxer|thong|bikini (underwear|brief|panty)|^bikini$", r"underwear|\bbriefs?\b", "Underwear & Panties"),
    ("shapewear", r"shapewear|tank top|crop(ped)? top|bodysuit|t-?shirt|\bshirt\b|sweatpants|jacket|\bshorts?\b|cropped", r"shapewear|t-shirt|\bsports? short", "Shapewear & Tops"),
    ("socks", r"\bsocks?\b|stocking|hosiery", None, "Socks & Hosiery"),
    ("slippers", r"slipper|sandal|footwear", None, "Slippers & Footwear"),
    # --- เครื่องประดับ / ของใช้ทั่วไป
    ("earring", r"earring", r"earring", "Earrings"),
    ("necklace", r"necklace|pendant", None, "Necklaces & Pendants"),
    ("bracelet", r"bracelet|anklet", None, "Bracelets & Anklets"),
    ("keychain", r"keychain|key ring", r"^[^(]*keychain", "Character & Anime Merchandise"),
    ("coin_bag", r"coin (bag|purse)|wallet|cardholder", r"coin bag", "Wallets, Purses & Cardholders"),
    ("bag", r"string bag|decorative bag|handbag|\btote\b", None, "Handbags & Totes"),
    ("decor", r"decorative (card|item)|stationery", None, "Gadgets, Stationery & Lifestyle Items"),
    ("sunglasses", r"sunglass", None, "Sunglasses"),
    ("reading_glasses", r"reading glass|blue[- ]light", None, "Blue-Light & Reading Glasses"),
    ("umbrella", r"umbrella", None, "Umbrellas"),
    ("voucher", r"voucher|gift card|e-?coupon", None, "Gift Vouchers"),
    ("figurine", r"figurine|art toy|blind box", None, "Collectible Figurines & Art Toys"),
    ("camera", r"instant camera|digital camera", r"instant camera", "Instant Camera"),
    ("film", r"instant film|photo paper", r"instant film", "Instant Film"),
    # --- ที่เป่าผม/ไดร์/หนีบ (เครื่องใช้ไฟฟ้า) ก่อนแปรง/หวี
    ("lash_curler", r"eyelash curler|lash curler", r"eyelash curler", "Eyelash Curlers"),
    ("hair_styling_tool", r"hair dryer|hairdryer|straightener|curling iron|hot air styler|hair styler|flat iron|crimper|blow dryer|cordless hair curler|hair curler \(electric\)", r"hair dryer|curling iron|straightener", "Hair Styling Tools"),
    ("heatless_curler", r"heatless|hair roller|sticky patch curler|curler clip", None, "Heatless Hair Curlers"),
    ("epilator", r"epilator|hair removal device|\bipl\b", r"epilator", "Epilators & Hair Removal Devices"),
    ("shaver_trimmer", r"electric (shaver|razor|trimmer)|trimmer|shaver", r"trimmer|electric shaver", "Electric Shavers & Trimmers"),
    ("massager", r"massag(er|ing device)|beauty device|cleansing device|skincare device|facial (treatment |toning )?device|led (mask|device)|microcurrent|sonic (face|facial)", r"\bcbg devices?\b", "Massagers & Beauty Devices"),
    # --- อุปกรณ์สุขภาพ
    ("thermometer", r"thermometer", r"thermometer", "Thermometers"),
    ("nebulizer", r"nebuli[sz]er", r"nebuli[sz]er", "Nebulizers"),
    ("test_kit", r"test kit|rapid test|antigen", r"test kit|antigen", "Rapid Test Kits"),
    ("braces", r"\bbrace|\bsupport(er)?s?$", None, "Supports & Braces"),
    ("ear_plugs", r"ear ?plugs?|sleep aid", None, "Ear Plugs & Sleep Aids"),
    ("pain_patch", r"pain relief|medicated (plaster|patch)|plaster(?! mask)", r"plaster|pain relief|thermaplast|therma plast", "Pain Relief Patch & Plaster"),
    ("balm_rub", r"analgesic|vapor rub|muscle (rub|balm)", None, "Analgesic Balm & Rub"),
    ("cooling_patch", r"cooling patch|fever (cooling|patch)", None, "Fever Cooling Patch"),
    ("bandage", r"bandage|wound|first aid", r"bandage", "Bandage & Wound Care"),
    ("hot_cold_pack", r"cold and hot pack|hot (and|&) cold|ice pack|heat pack", None, "Hot & Cold Pack"),
    ("disinfectant", r"disinfectant|^alcohol(?!-free)", None, "Alcohol & Disinfectants"),
    ("nasal", r"nasal|congestion|inhaler", r"nasal|inhaler", "Nasal Spray & Congestion Relief"),
    ("lozenge", r"lozenge|throat", None, "Lozenges & Throat Care"),
    ("protective_mask", r"surgical|medical (face )?mask|protective mask|kf94|\bn95\b|respirator|หน้ากากอนามัย", r"medical face mask|surgical mask|3d (fit )?mask|kf94|n95|หน้ากากอนามัย", "Face Masks (Surgical & Protective)"),
    # --- เครื่องมือแต่งหน้า (L1 ยังเป็น Beauty and Personal Care ใน taxonomy)
    ("brush_set", r"(?<!tooth)brush set", r"(?<!tooth)brush set", "Makeup Brush Sets"),
    ("brush_eye", r"(eye ?shadow|eyebrow|brow|eye ?liner|lip|smudge|concealer|eye) brush", None, "Makeup Brushes (Eyes & Lips)"),
    ("brush_face", r"(?<!tooth)(?<!hair)(?<!hair )(?<!interdental )(?<!scalp )(?<!body )brush$|(blush|powder|foundation|contour|kabuki|face|cheek) brush|makeup brush", None, "Makeup Brushes (Face)"),
    ("makeup_sponge", r"makeup sponge|beauty blender|blending sponge|cosmetic sponge|latex sponge|\bblender\b", None, "Makeup Sponges & Blenders"),
    ("body_puff", r"body puff|bath (mitt|glove|sponge)|shower puff|loofah|exfoliating (mitt|glove)", None, "Body Puff & Bath Mitt"),
    ("facial_puff", r"facial puffs?|cleansing puffs?", None, "Facial Skincare Tools"),
    ("powder_puff", r"\bpuffs?\b|powder puff|cushion puff", None, "Powder Puffs"),
    ("lash_applicator", r"(eye)?lash applicator", None, "False Eyelash Applicators"),
    ("tweezers", r"tweezer|brow (razor|scissor|stencil|tool)|eyebrow (razor|scissor)", None, "Tweezers & Brow Tools"),
    ("sharpener", r"sharpener", None, "Cosmetic Sharpeners"),
    ("mixing_palette", r"spatula|mixing palette", None, "Makeup Spatulas & Mixing Palettes"),
    ("lash_glue", r"(eye)?lash (glue|adhesive)", r"(eye)?lash (glue|adhesive)", "False Eyelash Adhesive / Glue"),
    ("blotting", r"blotting|oil[- ](absorbing|removing|control)? ?(sheet|film|paper)", r"oil removing sheet|กระดาษซับมัน", "Oil Blotting Papers"),
    ("eyelid_tape", r"double eyelid|eyelid (tape|sticker)", r"double eyelid", "Double Eyelid Tape"),
    ("false_lashes", r"false eyelash|false lash|pre-applied lash|lash extension|^lashes$|eyelashes$", r"false eyelash|false lashes", "False Eyelashes"),
    ("mirror", r"mirror", None, "Makeup Mirrors (Lighted/Magnifying)"),
    ("brush_cleaner", r"brush clean", None, "Liquid Brush Cleaners & Sprays"),
    ("organizer", r"organi[sz]er|display case|cosmetic case|makeup storage", None, "Cosmetic Organizers & Display Cases"),
    ("makeup_bag", r"makeup (bag|pouch)|cosmetic (bag|pouch)|train case", None, "Makeup Bags, Pouches & Train Cases"),
    # --- เครื่องประดับผม / เครื่องมือความงามอื่น
    ("scalp_tool", r"scalp (massager|brush|washer)", None, "Scalp Massager & Hair Washer"),
    ("hair_brush", r"hair ?brush|hair comb|compact comb|detangling comb|\bcomb\b", r"hair ?brush", "Hair Brush & Comb"),
    ("hair_clip", r"hair clip|hairpin|bobby pin|barrette", None, "Hair Clip"),
    ("hair_claw", r"hair claw|claw clip", None, "Hair Claw"),
    ("hair_tie", r"hair tie|hair band|elastic band|scrunchie", None, "Hair Tie / Scrunchie"),
    ("headband", r"headband", None, "Headband"),
    ("hair_towel", r"hair (towel|wrap|turban)|shower cap", None, "Hair Towels & Wraps"),
    ("facial_tool", r"facial (roller|tool|steamer)|gua sha|jade roller|derma roller", None, "Facial Skincare Tools"),
    ("manicure_tool", r"nail (file|clipper|cutter|buffer)|manicure|pedicure|callus", None, "Manicure, Pedicure & Foot Tools"),
    ("travel_bottle", r"travel (bottle|container)|empty (bottle|jar)|spray bottle", None, "Travel Bottles & Containers"),
    ("cotton", r"cotton (pads?|buds?|balls?|swabs?)|cleansing cotton", None, "Cotton Pads & Buds"),
    ("baby_wipes", r"baby wipes?", r"baby wipes?", "B&C Toiletries"),
    ("wet_wipes", r"^wet wipes?$", None, "Wet Wipes"),
]

# 2) ชนิดสินค้าความงามที่ชัด - เก็บ Segment ของ Watsons ไว้ถ้าอยู่ Level 2 เดียวกัน (ละเอียดกว่า เช่นมี Premium/Mass)
# (ชื่อกฎ, regex Product_Type, regex ชื่อสินค้า, L4 หรือ ฟังก์ชัน(text)->L4)
RULES_BEAUTY = [
    ("makeup_remover", r"makeup remover|make-up remover|mascara remover", r"(makeup|make-up|mascara|eye) remover", lambda t: "Eye & Lip Makeup Removers" if re.search(r"eye|lip|mascara", t) else "Make-up Remover"),
    ("cleansing_oil", r"cleansing oil", None, "Cleansing Oil"),
    ("cleansing_water", r"^(?!.*(shampoo|hair)).*(micellar|cleansing water)", None, "Cleansing Water"),
    ("cleansing_balm", r"cleansing (balm|cream)", None, "Cleansing Balm & Cream"),
    ("sun", r"sunscreen|sunblock|sun protection|sun (cream|gel|milk|spray|stick)|\buv (gel|milk|cream|essence)", r"sunscreen|sunblock",
     lambda t: "Body Sunscreen" if "body" in t else "Face Sunscreen"),
    ("after_sun", r"after ?sun", r"after ?sun", "After Sun"),
    ("body_wash", r"body (cleansing|bath|wash)|shower (gel|cream)|shower foam", None, "Body Wash/Shower Gel"),
    ("liquid_soap", r"liquid soap|hand wash|hand soap", None, "Liquid Soap"),
    ("bar_soap", r"^(bar )?soap|whipped soap|cleansing soap|herbal soap", None, "Bar Soap"),
    ("body_scrub", r"body scrub|(sugar|salt|oil) scrub|sugar oil scrub", None, "Body Scrub"),
    ("bath_additive", r"bath (bomb|gel|foam|salt)|bubble bath", None, "Bath Additives"),
    ("hand_sanitizer", r"hand sanitizer", None, "Hand Sanitizers"),
    ("body_powder", r"talcum|body powder", None, "Body Powder"),
    ("body_mist", r"body mist|fragrance mist|(hair|body)\W+(and\W+)?(hair|body) mist", r"(hair|body)\W+(and\W+)?(hair|body) mist", "Body Mists & Splashes"),
    ("perfume", r"^(?!.*(lotion|shampoo|treatment|conditioner|shower|cream|soap|body wash|scrub|hair|serum|oil)).*(perfume|cologne|eau de|\bedp\b|\bedt\b)", r"eau de (parfum|parfume|toilette|cologne)|\bedp\b|\bedt\b", "Hydroalcoholic Perfumes"),
    ("deo_roll", r"(deodorant|anti-?perspirant|underarm|armpit).*roll-?on|roll-?on (deodorant|anti)|^roll-?on$", r"(deodorant|antiperspirant).*roll-?on|roll-?on.*(deodorant|antiperspirant)|โรลออน", "Deodorant Roll-on"),
    ("deo_stick", r"deodorant stick", None, "Deodorant Sticks"),
    ("deo_spray", r"deodorant (body )?spray|anti-?perspirant (body )?spray", None, "Deodorant Powder & Spray"),
    ("deo_cream", r"deodorant cream|underarm cream", None, "Deodorant Cream"),
    ("antiperspirant", r"deodorant|antiperspirant", r"antiperspirant", "Products With Antiperspirant Activity"),
    ("toothpaste", r"toothpaste", r"toothpaste|ยาสีฟัน", "Toothpaste"),
    ("mouthwash", r"mouth ?wash|dental rinse", r"mouthwash|น้ำยาบ้วนปาก", "Mouthwashes /Dental Rinses"),
    ("breath_spray", r"mouth ?spray|breath spray", None, "Breath Spray"),
    ("toothbrush", r"toothbrush|tooth brush", r"toothbrush|แปรงสีฟัน", "Toothbrushes"),
    ("floss", r"dental floss|interdental|floss", None, "Dental Floss & Interdental"),
    ("denture", r"denture", None, "Denture Care"),
    ("tongue", r"tongue clean", None, "Tongue Cleaners"),
    ("depilatory", r"hair remov|depilat|wax strip|waxing", r"hair remov", "Chemical Depilatories"),
    ("razor", r"razor|\bblades?\b|disposable shaver", r"razor|\bblades?\b", "Products For Shaving"),
    ("aftershave", r"after[- ]?shave", r"after[- ]?shave", "Aftershave Lotions & Splashes"),
    ("shaving_cream", r"shaving (cream|foam|gel)|shave gel", r"shaving (cream|foam|gel)", lambda t: "Pre- / After-Shaving Products" if (WOMEN.search(t) and not MEN.search(t)) else "Men's Shaving"),
]

NOT_NAME = {"perfume": r"lotion|cream|shampoo|shower|treatment|serum"}   # ชื่อเป็นสินค้าอื่นที่มีกลิ่นน้ำหอม -> ข้ามกฎ
NO_KEEP_SEGMENT = {"liquid_soap", "body_scrub"}   # Watsons จัดน้ำยาล้างมือเป็น "Hand Sanitizers" - กฎละเอียดกว่า

# 3) ถังรวมของ Watsons ที่ต้อง refine ด้วย Product_Type: {L4 ถังรวม: [(regex Product_Type/ชื่อ, L4)]}
REFINE = {
    "Other Skin Cleansing": [(r"face mask|facial mask", "Face Mask"), (r"sheet mask", "Sheet Mask"), (r"body scrub", "Body Scrub"),
                             (r"shower|body wash", "Body Wash/Shower Gel"), (r"soap", "Bar Soap"), (r"wet wipes?", "Wet Wipes")],
}
for _l4 in ("Other Hair And Scalp Care And Cleansing Products", "Other Hair Care", "Other Hair And Scalp Products", "Hair Accessories",
            "Other Hair Styling Products", "Conditioner and Treatment"):
    REFINE[_l4] = [(r"dry shampoo", "Dry Shampoo"), (r"shampoo", "Shampoo"), (r"conditioner", "Conditioner"),
                   (r"hair (serum|oil)|serum|oil", "Hair Oil & Serum"), (r"mask|treatment|keratin", "Hair Masks & Treatments"),
                   (r"spray|mousse|gel|styling", "Hair Gel, Mousse & Hairspray"), (r"wax|pomade|clay", "Pomade, Wax & Clay"),
                   (r"tonic|scalp", "Scalp And Hair Roots Care Products"), (r"hair (loss|fall)|regrowth", "Hair Loss Treatments"),
                   (r"dye|colou?r|bleach", "Hair Dye & Bleach")]

# 4) Sub_category / Category ของ Watsons -> L4 ตั้งต้น เมื่อไม่มี Segment
FALLBACK_SUB = {
    "Baby Hair Care": "B&C Hair Care", "Baby Skincare": "B&C Skin Care", "Baby Treatments": "Medicated B&C Products",
    "Collagen": "Collagen Capsule/Tablet", "Hair Growth Supplement": "Hair Growth Capsule", "Fiber": "Fiber Supplement Powder",
    "Probiotics": "Probiotic Capsule", "Other Food Supplement": "Other Food Supplement Products", "Fish Oil / Omega-3": "Fish Oil Softgel",
    "Herbal Supplement": "Herbal Extract Capsule", "Weight Management": "Weight Management Supplement", "Protein": "Protein Powder",
    "Vitamins": "Other Vitamin Supplement", "Minerals": "Other Mineral Supplement", "Multivitamin & Multimineral": "Multivitamin Tablet",
    "Fine Fragrance": "Hydroalcoholic Perfumes", "Eye Makeup": "Other Eye Make-Up Products", "Lip Makeup": "Other Lip Products",
    "Skin Makeup": "Other Facial Make-Up", "Makeup Sets": "Colour Cosmetics Set", "Nail Care": "Nail Care Products",
    "Deodorants": "Products With Antiperspirant Activity", "Oral Care": "Other Oral Hygiene Products", "Hair Removal": "Other Body Hair Removal Products",
    "Shaving": "Men's Shaving", "Acne Treatment": "Acne Gels & Cream", "Body Care": "General Body Moisturizer",
    "Body Moisture": "Body Balm & Cream & Lotion", "Body Sunscreen": "Body Sunscreen", "Face Sunscreen": "Face Sunscreen",
    "Eye Contour Care": "Eye Contour Care", "Face Cleansing": "Facial Cleanser", "Face Mask": "Face Mask", "Face Moisture": "Cream",
    "Face Toner and Essence": "Toners", "Facial Care": "Facial Care", "Lip Care": "Lip Care", "Skin Lightening": "Skin Lightening",
    "Skincare Set": "Gift Sets & Value Sets", "Personal Sets": "Personal Set /kits", "Hair Care": "Other Hair Care",
}
FALLBACK_CATEGORY = {
    "Baby Care": "B&C Toiletries", "Beauty Supplements": "Other Food Supplement Products", "Digestive Health": "Other Food Supplement Products",
    "General Health Supplements": "Other Food Supplement Products", "Sports & Protein Nutrition": "Protein Powder",
    "Vitamins & Minerals": "Other Vitamin Supplement", "Fragrances": "Hydroalcoholic Perfumes", "Hair Care": "Other Hair Care",
    "Makeup": "Other Make-Up Products", "Nail Care": "Nail Care Products", "Skincare": "Other Skincare",
    "Hygiene & Bath": "Other Skin Cleansing", "Men's Grooming": "Men's Skincare", "Sets & Kits": "Personal Set /kits",
}

# 5) คำในชื่อสินค้าที่ชี้ Level 2 ชัด - ใช้ตรวจป้าย Watsons (override เมื่อ Level 2 ต่างจากป้าย) เรียงลำดับสำคัญก่อน
# ตัดชื่อที่ขนาด/SPF/ปริมาณ: ส่วนหลังนั้นมักเป็นเฉดสี ("... SPF50 10ml. Natural Blush") ไม่ใช่ชนิดสินค้า
NAME_CUT = re.compile(r"\bspf ?\d|\bpa\+|\d+(\.\d+)?\s?(ml|g|gm|oz|l|pcs|pc|sheets?|pads?|capsules?)\b|\d+['’]s\b|\d+x\d+")
NAME_HINTS = [
    # สินค้าเด็กมาก่อนทุกหมวด - "Baby Bright" เป็นชื่อแบรนด์เครื่องสำอาง ไม่นับ
    ("baby_child", r"\bkids?\b|\bchild(ren)?\b|\binfant\b|\bbaby (shampoo|lotion|oil|wash|bath|cream|wipes?|massage)", "B&C Toiletries"),   # "Baby Powder" ไม่นับ: เป็นชื่อกลิ่น/เฉดสีบ่อย
    ("oral", r"toothpaste|toothbrush|mouth ?wash|dental floss|ยาสีฟัน|แปรงสีฟัน|น้ำยาบ้วนปาก", "Toothpaste"),
    ("deodorant", r"roll-?on|antiperspirant|deodorant (spray|stick|cream|roll)|โรลออน", "Deodorant Roll-on"),
    ("depilatory", r"hair remov|depilat|epilator|wax strip", "Chemical Depilatories"),
    ("hair", r"shampoo|(?<!skin )(?<!lip )(?<!face )conditioner|hair (mask|treatment|serum|oil|dye|colou?r|wax|spray|tonic|perfume|mist|mascara|coat|vitamin)|hair (\w+ ){1,2}(serum|tonic|treatment|mask|oil)|\bhair\b[^.]{0,40}\bspray\b|scalp (\w+ )?(serum|tonic|treatment|care|scrub)|dandruff|แชมพู|ครีมนวด|ย้อมผม|ทรีทเมนท์ผม|เส้นผม|บำรุงผม", "Shampoo"),
    # แผ่นสกินแคร์ (ป้ายเสียเป็น Foundation ฯลฯ): คำสกินแคร์นำหน้าคำว่า pad
    ("skin_pad", r"\b(toner|cleansing|acne|retinol|exfoliating|essence|treatment|calm(ing)?|serum|clarifying|pore|peeling)\b[^.]{0,25}\bpads?\b", "Toner Pad"),
    ("fragrance", r"\bedp\b|\bedt\b|eau de|perfume|cologne|น้ำหอม", "Hydroalcoholic Perfumes"),
    # อาบน้ำมาก่อน colour/skin_clean: "Peony Blush Shower Cream" ไม่ใช่บลัช, "Body Cleansing Milk" ไม่ใช่โฟมล้างหน้า
    ("bath", r"body wash|shower (gel|cream)|bath (bomb|gel|foam|salt)|body cleansing|ครีมอาบน้ำ", "Body Wash/Shower Gel"),
    ("colour", r"lipstick|fou?n?dation|\bprimer\b|powder pact|\b[bc]c (cream|powder|cushion)|cover powder|\bpalette\b|(?<!hair )mascara|eye ?liner|eye ?shadow|\bblush|concealer|bronzer|highlighter|loose powder|pressed powder|face powder|nail polish|lip (tint|gloss|stain|mousse|oil)|eyebrow (pencil|gel)|brow (pencil|gel)|eyelash|cushion|ลิปสติก|รองพื้น|มาสคาร่า|อายแชโดว์|บลัช", "Other Facial Make-Up"),
    ("skin_clean", r"micellar|cleansing (pad|water|oil|balm|gel|foam|milk)|\bcleanser\b|face wash|facial wash|foaming wash|make-?up remover|sheet mask|lip (serum|mask|treatment|care|scrub)", "Facial Cleanser"),
    ("bath_soap", r"\bsoap\b|สบู่", "Bar Soap"),   # ซอฟต์: ไม่ดึงสบู่ล้างหน้าที่ Watsons จัดเป็น Skin Care ไปหมวดอาบน้ำ
    ("body_lotion", r"body (lotion|cream|butter)|perfume lotion|โลชั่นน้ำหอม", "Body Balm & Cream & Lotion"),   # "Perfume Body Lotion" เป็นโลชั่น ไม่ใช่น้ำหอม
    ("sun", r"sunscreen|sun screen|sun stick|sunblock|ครีมกันแดด", "Face Sunscreen"),
]
SOFT_HINTS = {"bath_soap"}
HINT_NOT = {"fragrance": r"lotion|cream|shampoo|shower|treatment|conditioner|serum|body wash|gel wash|โลชั่น"}   # "Treatment Rich Perfume" = ทรีทเมนต์
# _pt_only_contradicted ใช้เฉพาะ hint เหล่านี้ (ชี้หมวดชัดและแทบไม่กำกวม) - colour/sun/skin_clean/bath ไม่ใช้: "Foundation Brush",
# "Sun Cool Loose Powder", "Denture Cleanser" มีคำสินค้าอีกหมวดอยู่ในชื่อโดยชอบธรรม
STRONG_CONTRA = {"hair", "oral", "skin_pad", "deodorant", "depilatory"}
WEAK_NAME_HINTS = [   # ใช้เฉพาะแถวที่ไม่มีป้ายหมวดและไม่เข้ากฎอื่นเลย
    ("skin", r"serum|toner|cream|\bmask\b|essence|moistur|lotion|cleanser|cleansing|jelly pad|\bpads?\b|\bgel\b|\boil\b|balm|\blip\b", "Other Skincare"),
]
# L4 ของ NAME_HINTS ที่ใช้เพียงเพื่อรู้ Level 2 - "colour" ใช้ L4 ละเอียดจากตารางนี้เมื่อต้อง override
COLOUR_L4 = [(r"powder pact|\b[bc]c (cream|powder|cushion)", "BB/CC Creams"), (r"lipstick|ลิปสติก", "Lipstick"), (r"lip gloss", "Lip Gloss"),
             (r"lip (tint|stain|mousse)", "Lip Stain & Tint"), (r"lip oil", "Lip Oil & Color Balm"), (r"mascara|มาสคาร่า", "Mascara"),
             (r"eye ?liner", "Eye Liner"), (r"blush|bronzer|highlighter|cheek|บลัช", "Blusher/Bronzer/Highlighter"),
             (r"face palette", "Other Facial Make-Up"), (r"eye ?shadow|\bpalette\b|อายแชโดว์", "Eye Shadow"), (r"eyebrow|brow", "Eyebrows"),
             (r"concealer", "Concealer"), (r"\bprimer\b", "Face Primer"), (r"fou?n?dation|cushion|รองพื้น", "Foundation/Concealer"),
             (r"\btint\b", "Lip Stain & Tint"), (r"powder", "Powder"), (r"nail polish", "Nail Polish"), (r"eyelash", "False Eyelashes")]
HAIR_L4 = [(r"dry shampoo", "Dry Shampoo"), (r"shampoo|แชมพู", "Shampoo"), (r"conditioner|ครีมนวด", "Conditioner"),
           (r"dandruff", "Antidandruff Products"), (r"scalp", "Scalp And Hair Roots Care Products"),
           (r"serum|oil", "Hair Oil & Serum"), (r"mask|treatment|coat|vitamin|ทรีทเมนท์", "Hair Masks & Treatments"), (r"tonic", "Scalp And Hair Roots Care Products"),
           (r"dye|colou?r|ย้อม", "Hair Dye & Bleach"), (r"wax", "Pomade, Wax & Clay"), (r"spray|mist|perfume", "Hair Gel, Mousse & Hairspray")]

SKIN_L4 = [(r"lip (serum|mask|treatment|care|scrub)", "Lip Care"), (r"micellar|cleansing water", "Cleansing Water"),
           (r"cleansing oil", "Cleansing Oil"), (r"cleansing balm|cleansing cream", "Cleansing Balm & Cream"),
           (r"make-?up remover", "Make-up Remover"), (r"sheet mask", "Sheet Mask"),
           (r"cleansing|cleanser|face wash|facial wash|foaming wash", "Facial Cleanser")]
BABY_L4 = [(r"shampoo|hair", "B&C Hair Care"), (r"lotion|cream|oil|powder|mask|serum", "B&C Skin Care"), (r"sun", "B&C Sun Care")]
HINT_L4 = {"colour": COLOUR_L4, "hair": HAIR_L4, "skin_clean": SKIN_L4, "baby_child": BABY_L4}   # ชนิดสินค้าละเอียดของแต่ละ hint


def _hint_l4(source, l4, core):
    return next((t for p, t in HINT_L4.get(source, []) if rx(p).search(core)), l4)


_COMPILED = {}


def rx(pattern):
    if pattern not in _COMPILED:
        _COMPILED[pattern] = re.compile(pattern)
    return _COMPILED[pattern]


def _validate():
    """ทุก L4 ที่กฎอ้างถึงต้องมีใน product_category.csv"""
    used = {r[3] for r in RULES_PRODUCT}
    used |= {r[3] for r in RULES_BEAUTY if isinstance(r[3], str)}
    used |= {l4 for pairs in REFINE.values() for _, l4 in pairs} | set(REFINE)
    used |= set(FALLBACK_SUB.values()) | set(FALLBACK_CATEGORY.values()) | {h[2] for h in NAME_HINTS + WEAK_NAME_HINTS}
    used |= {l4 for _, l4 in COLOUR_L4 + HAIR_L4 + SKIN_L4 + BABY_L4}
    missing = sorted(u for u in used if u not in BY_L4)
    if missing:
        raise KeyError(f"L4 ที่กฎอ้างถึงแต่ไม่มีใน {TAXONOMY_PATH.name}: {missing}")
    for l4, pairs in L3_BY_TEXT.items():
        l3s = {p[2] for p in BY_L4[l4]}
        bad = [l3 for _, l3 in pairs if l3 not in l3s]
        if bad:
            raise KeyError(f"L3_BY_TEXT[{l4!r}] อ้าง L3 ที่ไม่มีใต้ L4 นี้ใน {TAXONOMY_PATH.name}: {bad}")


_validate()


# ---------------------------------------------------------------- classify -----------------------------------------
def _s(v):
    return v.strip() if isinstance(v, str) and v.strip() else ""


def _result(path, status, source, conf):
    l1, l2, l3, l4 = path
    group = path[int(GROUP_LEVEL[1]) - 1] or l2   # L3 ว่าง (Premium/Mass แยกไม่ได้) -> ใช้ L2 แทน
    return {"EM_L1": l1, "EM_L2": l2, "EM_L3": l3, "EM_L4": l4, "EM_Group": group,
            "EM_status": status, "EM_source": source, "EM_confidence": conf}


def _unmapped(source):
    return {"EM_L1": "", "EM_L2": "", "EM_L3": "", "EM_L4": "", "EM_Group": UNMAPPED, "EM_status": "unmapped",
            "EM_source": source, "EM_confidence": "low"}


def _hit(pt, name, pt_re, nm_re):
    return bool((pt and pt_re and rx(pt_re).search(pt)) or (nm_re and rx(nm_re).search(name)))


def _refine(l4, pt, name):
    for pattern, target in REFINE.get(l4, []):
        if rx(pattern).search(pt or name):
            return target
    return l4


def _name_hint(name, weak=False):
    cut = NAME_CUT.search(name)
    core = name[:cut.start()] if cut and cut.start() > 3 else name
    for source, pattern, l4 in (WEAK_NAME_HINTS if weak else NAME_HINTS):
        if rx(pattern).search(core):
            if source in HINT_NOT and rx(HINT_NOT[source]).search(core):
                continue
            if source == "bath_soap" and "brow" in core:   # "Brow Fix Soap" = สบู่เซ็ตคิ้ว
                continue
            return source, l4, core
    return None


def _pt_only_contradicted(name, pt_re, nm_re, path):
    """กฎจับได้จาก Product_Type อย่างเดียว (ชื่อไม่เข้ากฎ) แต่ชื่อสินค้าชี้หมวด Level 2 อื่นชัดเจน -> Product_Type เสีย ข้ามกฎนี้
    (เช่น "Bualuang Hair Coat ... บำรุงเส้นผม" ที่ Product_Type = Mouthwash, "Hair It Heat Sun Protection Spray" = Sunscreen)"""
    support = rx(nm_re) if nm_re else rx(pt_re)   # ชื่อมีคำของกฎนี้เองไหม (กฎที่ไม่มี regex ชื่อ ใช้ regex Product_Type ค้นในชื่อ)
    if support.search(name):
        return False
    hint = _name_hint(name)
    return bool(hint) and hint[0] in STRONG_CONTRA and resolve(hint[1], name)[1] != path[1]


def classify_labels(row):
    pt, name = _s(row.get("Product_Type")).lower(), _s(row.get("product_name")).lower()
    cat, sub, seg = _s(row.get("Category")), _s(row.get("Sub_category")), _s(row.get("Segment"))
    text = f"{pt} {name}"
    baby = cat == "Baby Care" or seg.startswith("B&C") or seg.startswith("Medicated B&C") or seg.startswith("Nappy")
    # แคตตาล็อกที่ป้าย Category เป็นชื่อ Level 2 ของ taxonomy อยู่แล้ว (Konvy) -> ใช้ตัดสินเมื่อ L4 อยู่ใต้หลาย parent (เช่น
    # "Products For Shaving" ของมีดโกนผู้หญิงที่ชื่อไม่บอกเพศ) - ป้ายอื่นที่ไม่ใช่ชื่อ L2 ไม่มีผล
    own_l2 = cat if cat in L2_NAMES else None

    # 1) ชนิดสินค้าชัด (ใช้กับทุกแถว)
    for source, pt_re, nm_re, l4 in RULES_PRODUCT:
        if _hit(pt, name, pt_re, nm_re):
            path = resolve(l4, text, own_l2)
            if _pt_only_contradicted(name, pt_re, nm_re, path):
                continue
            return _result(path, "mapped", f"rule:{source}", "high" if pt and pt_re and rx(pt_re).search(pt) else "medium")

    # 2) ชนิดสินค้าความงาม (ข้ามแถวสินค้าเด็ก - สบู่/กันแดดเด็กยังเป็นหมวดเด็ก)
    seg_path = resolve(seg, text, own_l2) if seg in BY_L4 else None
    if not baby:
        for source, pt_re, nm_re, target in RULES_BEAUTY:
            if _hit(pt, name, pt_re, nm_re) and not (source in NOT_NAME and rx(NOT_NAME[source]).search(name)):
                l4 = target(text) if callable(target) else target
                path = resolve(l4, text, own_l2)
                if _pt_only_contradicted(name, pt_re, nm_re, path):
                    continue
                if seg_path and seg_path[1] == path[1] and not seg.startswith("Other ") and source not in NO_KEEP_SEGMENT:
                    return _result(seg_path, "mapped", f"rule:{source}+segment", "high")   # Segment ละเอียดกว่า (เช่นมี Premium/Mass)
                return _result(path, "mapped", f"rule:{source}", "medium")

    # 3) Segment ของ Watsons
    if seg_path:
        refined = _refine(seg, pt, name)
        if refined != seg:
            return _result(resolve(refined, text), "mapped", f"segment_refined:{seg}", "medium")
        return _result(seg_path, "mapped", "segment", "high")
    # 4) Sub_category / Category
    if sub in FALLBACK_SUB:
        return _result(resolve(FALLBACK_SUB[sub], text), "mapped", "watsons_sub_category", "medium")
    pt_hint = _name_hint(pt) if pt else None   # Product_Type เป็นชนิดสินค้าสั้นๆ ("foundation", "conditioner") - ดีกว่าเดาจาก Category
    if pt_hint:
        source, l4, core = pt_hint
        return _result(resolve(_hint_l4(source, l4, core), text), "mapped", f"product_type_hint:{source}", "medium")
    if cat in FALLBACK_CATEGORY:
        return _result(resolve(FALLBACK_CATEGORY[cat], text), "mapped", "watsons_category", "low")
    return _unmapped("no_label")


def classify_row(row):
    """ผลจากป้าย Watsons ตรวจทานด้วยชื่อสินค้า: ชื่อชี้ Level 2 ชัดและต่างจากป้าย -> เชื่อชื่อ (ป้ายบางแถวเสีย)
    ไม่แตะแถวที่ติดกฎชนิดสินค้า (rule:) หรือเป็นสินค้าเด็ก"""
    base = classify_labels(row)
    name = _s(row.get("product_name")).lower()
    if base["EM_source"].startswith("rule:") or base["EM_L2"] == "Baby and Child-specific Products":
        return base
    pt = _s(row.get("Product_Type")).lower()
    hint = _name_hint(name) or (_name_hint(pt) if pt else None)   # ชื่อไม่มีคำชี้หมวด -> ลอง Product_Type
    if hint:
        h_source, h_l4, core = hint
        h_l4 = _hint_l4(h_source, h_l4, core)
        h_path = resolve(h_l4, f"{_s(row.get('Product_Type')).lower()} {name}")
        if h_source in SOFT_HINTS and base["EM_L2"] == "Skin Care":
            return base
        colour_l3_conflict = (h_source == "colour" and base["EM_L2"] == "Colour Cosmetics" and h_path[1] == "Colour Cosmetics"
                              and h_path[2] != base["EM_L3"])   # ชนิดสินค้าในชื่อไม่ตรงป้ายแม้ L2 เดียวกัน (Eyeshadow Palette ป้าย Lip Tint)
        if h_path[1] != base["EM_L2"] or colour_l3_conflict:
            was = base["EM_source"] if base["EM_status"] == "mapped" else "unmapped"
            return _result(h_path, "mapped", f"name_{h_source}(was:{was})", "medium")
        return base
    if base["EM_status"] == "unmapped":
        weak = _name_hint(name, weak=True)
        if weak:
            return _result(resolve(weak[1], name), "mapped", f"name_weak_{weak[0]}", "low")
    return base


def add_euromonitor_columns(df):
    """คืน DataFrame ใหม่ (index เดิม) เพิ่มคอลัมน์ EM_* - ไม่แก้ df ที่ส่งเข้ามา"""
    res = pd.DataFrame([classify_row(r) for r in df.to_dict("records")], index=df.index)
    return pd.concat([df, res], axis=1)


_CLASSIFY_COLS = ["Industry", "Category", "Sub_category", "Segment", "Product_Type", "product_name"]
_CONF = {3: "high", 2: "medium", 1: "low"}


def product_key(row):
    """รหัสสินค้าสำหรับผล LLM: hash(brand | ชื่อ | Product_Type) - ไม่ผูกกับเลขแถว (ไฟล์ถูกเรียงใหม่/เพิ่มแถวได้)"""
    raw = "|".join(_s(row.get(c)) for c in ("brand", "product_name", "Product_Type"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def load_llm_labels(path=LLM_LABELS_PATH, prompt=None):
    """{product_key: {variant: (path_id, confidence)}} จาก JSONL (บรรทัดหลังชนะ) - variant = "hints" | "nohints"
    (LLM จัดสินค้า 2 รอบ: ส่ง/ไม่ส่งคำใบ้ Product_Type+Segment ของ Watsons) - ไม่มีไฟล์ = {}
    prompt: ถ้าระบุ นับเฉพาะบรรทัดของ prompt เวอร์ชันนั้น (ใช้ตอนรันต่อ)"""
    labels = {}
    if Path(path).exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    if prompt is not None and r.get("prompt") != prompt:
                        continue
                    labels.setdefault(r["key"], {})[r.get("variant", "hints")] = (int(r["path_id"]), int(r.get("conf", 0)))
    return labels


def pick_label(votes, rule_l2):
    """ผล LLM 2 รอบ + หมวดจากกฎ -> (path_id, EM_confidence, EM_source) หรือ None ถ้า LLM ไม่ได้ path ที่ใช้ได้เลย
    - 2 รอบตรงกันที่ L2 -> ใช้ (path ที่ละเอียดต่างกันใต้ L2 เดียวกัน เลือกรอบที่มั่นใจกว่า เท่ากัน -> รอบที่ส่งคำใบ้)
    - ไม่ตรงกัน -> เลือกรอบที่ L2 ตรงกับกฎ (คำใบ้ Product_Type ที่เสียทำให้ LLM หลงได้ เช่น "Perfume Body Lotion" ที่ป้าย Perfume;
      ในทางกลับกันกฎก็หลงป้ายเสียได้ - สองฝั่งผิดคนละแบบ จึงใช้อีกฝั่งมาตัดสิน)
    - ไม่ตรงกันทั้งสามฝ่าย -> รอบที่ส่งคำใบ้ ความมั่นใจต่ำ
    - มีรอบเดียว -> ใช้รอบนั้น"""
    ok = {v: t for v, t in votes.items() if t[0] in PATH_BY_ID}
    h, n = ok.get("hints"), ok.get("nohints")
    if h and n:
        ph, pn = PATH_BY_ID[h[0]], PATH_BY_ID[n[0]]
        if ph[1] == pn[1]:
            pick = h if h[1] >= n[1] else n
            return pick[0], ("high" if min(h[1], n[1]) >= 2 else "medium"), "llm"
        if pn[1] == rule_l2:
            return n[0], "medium", "llm(no-hints)+rules"
        if ph[1] == rule_l2:
            return h[0], "medium", "llm(hints)+rules"
        return h[0], "low", "llm(hints,disputed)"
    one = h or n
    if one:
        return one[0], _CONF.get(one[1], "low"), "llm(single)"
    return None


def apply_llm_labels(df, labels):
    """ทับผลจากกฎด้วยผล LLM (ตาม pick_label) - เก็บผลของกฎไว้ใน EM_rule_L2 / EM_rule_L4 ไว้เทียบความสอดคล้อง
    แถวที่ LLM ไม่มีผลที่ใช้ได้ (ไม่มีในไฟล์ หรือตอบ 0 = ไม่เข้าหมวดไหน) -> คงผลจากกฎ คืน DataFrame ใหม่"""
    out = df.copy()
    out["EM_rule_L2"], out["EM_rule_L4"] = out["EM_L2"], out["EM_L4"]
    level = int(GROUP_LEVEL[1]) - 1
    cols = {c: out[c].tolist() for c in ("EM_L1", "EM_L2", "EM_L3", "EM_L4", "EM_Group", "EM_status", "EM_source", "EM_confidence")}
    for n, rec in enumerate(out.to_dict("records")):
        votes = labels.get(product_key(rec))
        picked = pick_label(votes, rec["EM_rule_L2"]) if votes else None
        if not picked:
            continue
        pid, conf, source = picked
        path = PATH_BY_ID[pid]
        for c, v in zip(("EM_L1", "EM_L2", "EM_L3", "EM_L4"), path):
            cols[c][n] = v
        cols["EM_Group"][n] = path[level] or path[1]
        cols["EM_status"][n], cols["EM_source"][n], cols["EM_confidence"][n] = "mapped", source, conf
    for c, v in cols.items():
        out[c] = v
    return out


def load_catalog(csv_path=CSV_PATH, beauty_only=True, usecols=None, use_llm=True, labels=None):
    """โหลดแคตตาล็อก Watsons + คอลัมน์ EM_* (หมวดตาม product_category.csv) - จุดโหลดเดียวที่ ⑫ ⑬ และรายงานใช้ร่วมกัน
    หมวด: ผล LLM (euromonitor_llm_labels.jsonl) เป็นหลัก; แถวที่ไม่มีผล LLM ใช้กฎ (add_euromonitor_columns) เป็นตัวสำรอง;
    use_llm=False = กฎล้วน (ใช้ในเทสต์); labels = ส่งผล LLM เข้ามาตรงๆ แทนการอ่านไฟล์ (เทสต์)
    beauty_only=True (ค่าตั้งต้น): เก็บเฉพาะ EM_L1 == Beauty and Personal Care ตามที่เจ้าของงานกำหนด (2026-10-01) -
    สินค้านอกกลุ่ม (อาหารเสริม คอนแทคเลนส์ ของใช้ในบ้าน ฯลฯ) ไม่เข้าการจับคู่เทรนด์/การแสดงหมวด
    index ของ DataFrame คงเลขแถวเดิมของไฟล์ (กรองด้วย mask ไม่ reset) - cache embedding ผูกกับ hash เนื้อหาอยู่แล้ว
    จึงไม่ต้อง embed ใหม่ไม่ว่ากรองหรือไม่
    usecols: ระบุคอลัมน์ที่ต้องการ (เพิ่มคอลัมน์ที่ใช้จัดหมวดให้เองอัตโนมัติ); None = ทุกคอลัมน์"""
    if usecols is not None:
        usecols = list(dict.fromkeys(list(usecols) + _CLASSIFY_COLS + ["brand"]))
    df = pd.read_csv(csv_path, encoding="utf-8-sig", low_memory=False, usecols=usecols)
    df = add_euromonitor_columns(df)
    if use_llm:
        labels = load_llm_labels() if labels is None else labels
        if labels:
            df = apply_llm_labels(df, labels)
        else:
            print(f"⚠️ ไม่พบผล LLM ({LLM_LABELS_PATH.name}) - ใช้หมวดจากกฎแทน (รัน classify_products_llm.py --run)")
    return df[df["EM_L1"] == BEAUTY_L1] if beauty_only else df


def main():
    out = load_catalog(beauty_only=False)
    cols = ["product_code", "brand", "product_name", "Category", "Sub_category", "Segment", "Product_Type",
            "EM_L1", "EM_L2", "EM_L3", "EM_L4", "EM_Group", "EM_status", "EM_source", "EM_confidence"]
    cols += [c for c in ("EM_rule_L2", "EM_rule_L4") if c in out.columns]
    out.index.name = "row_id"
    out[cols].to_csv(MAP_PATH, encoding="utf-8-sig")
    print(f"บันทึก {MAP_PATH.name} ({len(out)} แถว)")
    for col in ("EM_status", "EM_source", "EM_L1", "EM_L2", "EM_confidence"):
        print()
        print(out[col].str.replace(r"\(was:.*\)", "", regex=True).value_counts().head(45).to_string())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
