import typing
import sys, re, io
sys.path.insert(0, '/app')
import fitz, pytesseract
from PIL import Image, ImageOps, ImageFilter

with open("/tmp/uploads/Radius. Add Apple system.pdf", "rb") as f:
    data = f.read()

doc = fitz.open(stream=data, filetype="pdf")
ocr_chunks = []
for i, page in enumerate(doc):
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    img_bytes = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_bytes))
    img = ImageOps.grayscale(img)
    img = img.filter(ImageFilter.MedianFilter(size=3))
    img = img.point(lambda p: 0 if p < 180 else 255)
    ocr_text = pytesseract.image_to_string(img, lang="eng", config="--oem 3 --psm 6")
    ocr_chunks.append(ocr_text or "")

doc.close()

full_text = "\n".join(ocr_chunks)
last_pages_text = "\n".join(ocr_chunks[-3:])

# Apply de-hyphenation (same as app)
def _dehyph(t):
    return re.sub(r'(-)\s*\n\s*([A-Za-z0-9])', lambda m: m.group(1) + m.group(2), t)

full_text = _dehyph(full_text)
last_pages_text = _dehyph(last_pages_text)

# Build extraction text same way as app
extraction_text = f"{last_pages_text}\n\n--- Full Document Context ---\n\n{full_text}"

print(f"full_text length: {len(full_text)}")
print(f"last_pages_text length: {len(last_pages_text)}")
print(f"combined extraction_text length: {len(extraction_text)}")
print(f"text window sent to Cohere (6500 chars): {len(extraction_text[:6500])}")
print()

# Check if 31-JUL appears
print("=== Searching for 31-JUL in text window ===")
window = extraction_text[:6500]
if '31-JUL' in window or '31/07' in window:
    idx = window.find('31-JUL')
    if idx == -1: idx = window.find('31/07')
    print(f"FOUND at idx {idx}:")
    print(repr(window[max(0,idx-100):idx+100]))
else:
    print("NOT FOUND in 6500-char window")
    # Check if it's in full text
    if '31-JUL' in extraction_text:
        idx = extraction_text.find('31-JUL')
        print(f"BUT found at idx {idx} in full text (beyond 6500 window)")
        print(repr(extraction_text[max(0,idx-100):idx+100]))
    else:
        print("NOT FOUND anywhere — check raw page 5:")
        print(repr(ocr_chunks[4][:800]))

print()
print("=== Last 200 chars of the 6500-char window ===")
print(repr(window[-200:]))
