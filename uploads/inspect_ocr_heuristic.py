import typing
import sys, re, io, os
sys.path.insert(0, '/app')

import fitz, pytesseract
from PIL import Image, ImageOps, ImageFilter

with open("/tmp/uploads/Radius. Add Apple system.pdf", "rb") as f:
    data = f.read()

doc = fitz.open(stream=data, filetype="pdf")
ocr_chunks = []
print(f"Extracting {len(doc)} pages with APP's OCR settings (--oem 3 --psm 4)...")
for i, page in enumerate(doc):
    pix = page.get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False)
    img_bytes = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_bytes))
    img = ImageOps.grayscale(img)
    img = img.filter(ImageFilter.MedianFilter(size=3))
    img = img.point(lambda p: 0 if p < 180 else 255)
    ocr_text = pytesseract.image_to_string(img, lang="eng", config="--oem 3 --psm 4")
    ocr_chunks.append(ocr_text or "")
    print(f"\n--- PAGE {i+1} ({len(ocr_text)} chars) ---")
    print(ocr_text[:400])
doc.close()

full_text = "\n".join(ocr_chunks)
last_pages_text = "\n".join(ocr_chunks[-3:])

print("\n\n=== SEARCHING HEURISTIC PATTERNS IN FULL TEXT ===")
_FD = r'([0-9]{1,2}[-/\s](?:[0-9]{1,2}|[A-Za-z]{3,9})[-/\s][0-9]{2,4})'
_months_map = {'jan':'01','feb':'02','mar':'03','apr':'04','may':'05','jun':'06',
               'jul':'07','aug':'08','sep':'09','oct':'10','nov':'11','dec':'12'}

def _to_dd_mm_yyyy(date_str):
    if not date_str: return date_str
    date_str = date_str.strip()
    m = re.match(r"(\d{1,2})[-/\s]([A-Za-z]{3,9})[-/\s,]+(\d{4})", date_str)
    if m:
        dd, mon, yyyy = m.group(1), m.group(2), m.group(3)
        mm = _months_map.get(mon[:3].lower())
        if mm: return f"{int(dd):02d}/{mm}/{yyyy}"
    m = re.match(r"(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})", date_str)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{int(dd):02d}/{int(mm):02d}/{yyyy}"
    return date_str

patterns_to_test = [
    ("expiry/Date of Expiry",  r'Date\s*of\s*Expiry\s*[:\-]\s*' + _FD, full_text),
    ("expiry/valid up to",     r'valid\s*up\s*to\s*' + _FD, full_text),
    ("claim/on or before",     r'on\s*or\s*before\s*(?:the\s*)?(?:\(date\)\s*)?' + _FD, full_text),
    ("date_of_issue/ISSUANCE", r'(?:ISSUANCE|BG\s*Issue)\s*DATE?[:\s]*' + _FD, full_text),
    ("rfp_number/tender",      r'Tender\s*bearing\s*No\.?\s*([A-Z0-9/._-]+)', full_text),
]
for label, pat, text in patterns_to_test:
    found = list(re.finditer(pat, text, re.IGNORECASE))
    if found:
        for m in found:
            raw = m.group(1).strip()
            norm = _to_dd_mm_yyyy(raw) if re.match(r'\d', raw) else raw
            print(f"  [FOUND] {label}: raw={raw!r} -> {norm!r}")
    else:
        print(f"  [MISS]  {label}: no match")

print("\n\n=== SCANNING FOR '31' OCCURRENCES IN FULL TEXT ===")
for m in re.finditer(r'31.{0,20}', full_text):
    print(f"  ...{m.group()!r}...")
