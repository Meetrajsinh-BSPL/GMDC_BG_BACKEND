import typing
import sys
sys.path.insert(0, '/app')
import fitz, pytesseract
from PIL import Image
import io, re

pdf_path = "/tmp/uploads/Radius. Add Apple system.pdf"
doc = fitz.open(pdf_path)

# Full page 5 text
page = doc[4]
mat = fitz.Matrix(2.0, 2.0)
pix = page.get_pixmap(matrix=mat)
img = Image.open(io.BytesIO(pix.tobytes("png")))
txt = pytesseract.image_to_string(img, config='--psm 6')
print("=== FULL PAGE 5 OCR ===")
print(txt)
print("\n\n=== SEARCHING IN PAGE 5 ===")
_FD = r'([0-9]{1,2}[-/\s](?:[0-9]{1,2}|[A-Za-z]{3,9})[-/\s][0-9]{2,4})'
for pat, label in [
    (r'on\s*or\s*before\s*(?:the\s*)?(?:\(date\)\s*)?' + _FD, "on_or_before"),
    (r'valid\s*up\s*to\s*' + _FD, "valid_up_to"),
    (r'31.{0,3}JUL', "31-JUL raw"),
    (r'31', "31"),
]:
    for m in re.finditer(pat, txt, re.IGNORECASE):
        print(f"  [{label}] -> {m.group()!r}")
