import typing
import sys
sys.path.insert(0, '/app')
import fitz, pytesseract
from PIL import Image
import io, re

pdf_path = "/tmp/uploads/Radius. Add Apple system.pdf"
doc = fitz.open(pdf_path)
n = len(doc)
print(f"Total pages: {n}")

# Extract text from last 3 pages via OCR
last_pages_text = ""
for i in range(max(0, n-3), n):
    page = doc[i]
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    txt = pytesseract.image_to_string(img, config='--psm 6')
    print(f"\n--- PAGE {i+1} OCR (first 500 chars) ---")
    print(txt[:600])
    last_pages_text += f"\n[PAGE {i+1}]\n" + txt

print("\n\n=== SEARCHING KEY PATTERNS IN LAST 3 PAGES ===")
_FD = r'([0-9]{1,2}[-/\s](?:[0-9]{1,2}|[A-Za-z]{3,9})[-/\s][0-9]{2,4})'
patterns = {
    "expiry_date(Date of Expiry)": r'Date\s*of\s*Expiry\s*[:\-]\s*' + _FD,
    "expiry_date(valid up to)":    r'valid\s*up\s*to\s*' + _FD,
    "claim(on or before)":         r'on\s*or\s*before\s*(?:the\s*)?(?:\(date\)\s*)?' + _FD,
    "rfp_number":                  r'[Tt]ender\s*bearing\s*[Nn]o[.:\s]*([^\n,;]{5,40})',
    "applicant":                   r'Name\s*of\s*the\s*Contractor\s*[:\-]\s*([^\n]{5,60})',
}
for label, pat in patterns.items():
    for m in re.finditer(pat, last_pages_text, re.IGNORECASE):
        print(f"  [{label}] matched: {m.group(1)!r} (pos {m.start()})")
