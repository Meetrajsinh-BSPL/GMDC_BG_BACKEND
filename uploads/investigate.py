import typing
#!/usr/bin/env python3
"""Investigate the 6 flagged documents: extract their OCR text and look for the missing fields."""
import sys, re, io, json
sys.path.insert(0, '/app')
import fitz, pytesseract
from PIL import Image, ImageOps, ImageFilter

PROBLEM_FILES = [
    ("/tmp/uploads/../2023.05.29_PBG_aXYKno_DPR_Kutch.pdf",        "BAD BG# LEG LI 16741322"),
    ("/tmp/uploads/../2023.10.30_PBG_GRC_EC&FC_BTW.pdf",            "BAD BG# DUS PH TAR..."),
    ("/tmp/uploads/../2023.09.13_PBG_BNB_Land and R&R_BRP.pdf",     "MISSING claim_expiry_date"),
    ("/tmp/uploads/../2023.10.01_PBG_aXYKno_DPR_South Gujarat.pdf", "MISSING date_of_issue"),
    ("/tmp/uploads/../2023.10.30_PBG_GRC_EC&FC_BTW.pdf",            "MISSING claim_expiry_date"),
    ("/tmp/uploads/../2025.03.17_PBG_Extension of BG GMDC-Pkg-2-30.09.2025.pdf", "MISSING doi+beneficiary"),
]

# Dedup
seen = set()
uniq = []
for p, desc in PROBLEM_FILES:
    if p not in seen:
        seen.add(p)
        uniq.append((p, desc))

for pdf_path, issue in uniq:
    import os
    # Resolve relative paths
    actual = pdf_path.replace("/tmp/uploads/../", "/aidata/gmdc_bg_api/")
    if not os.path.exists(actual):
        print(f"\n{'='*80}\nFILE NOT FOUND: {actual}\n")
        continue
    
    print(f"\n{'='*80}")
    print(f"FILE: {os.path.basename(actual)}")
    print(f"ISSUE: {issue}")
    print(f"{'='*80}")
    
    with open(actual, "rb") as f:
        data = f.read()
    
    doc = fitz.open(stream=data, filetype="pdf")
    n = len(doc)
    
    # Try text extraction first
    text_chunks = []
    for page in doc:
        t = page.get_text("text") or ""
        text_chunks.append(t)
    
    combined = "\n".join(text_chunks)
    has_text = bool(re.search(r'[A-Za-z0-9]{3,}', combined)) and not all(
        ln.startswith("<image:") for ln in combined.strip().splitlines() if ln.strip()
    )
    
    if has_text and len(combined.strip()) > 100:
        print(f"  Extraction: PyMuPDF text layer ({len(combined)} chars, {n} pages)")
        # Show last 3 pages
        last3 = "\n".join(text_chunks[-3:])
        # Search for key patterns
        for label, pat in [
            ("BG Number", r'(?:BG\s*No|Bank\s*Guarantee\s*No|Guarantee\s*No)[:\s.]*([^\n]{5,30})'),
            ("Date of Issue", r'(?:Date|DT|Issue\s*Date|Issuance\s*Date)[:\s]*([0-9]{1,2}[./\-][0-9]{1,2}[./\-][0-9]{2,4})'),
            ("Expiry", r'(?:valid\s*(?:up\s*to|till|until)|expiry\s*date|Date\s*of\s*Expiry)[:\s]*([^\n]{5,20})'),
            ("Claim/on or before", r'on\s*or\s*before[^0-9]*([0-9]{1,2}[./\-][0-9]{1,2}[./\-][0-9]{2,4})'),
            ("Beneficiary", r'(?:in\s*favour\s*of|beneficiary|Name\s*of\s*the\s*Beneficiary)[:\s]*([^\n]{5,80})'),
        ]:
            m = re.search(pat, combined, re.IGNORECASE)
            if m:
                print(f"  {label}: {m.group(1).strip()!r}")
            else:
                m2 = re.search(pat, last3, re.IGNORECASE)
                if m2:
                    print(f"  {label} (last3): {m2.group(1).strip()!r}")
                else:
                    print(f"  {label}: NOT FOUND")
        # Print first 600 chars of text  
        print(f"  --- FIRST 600 chars ---")
        print(f"  {combined[:600]}")
    else:
        print(f"  Extraction: OCR needed ({n} pages)")
        ocr_chunks = []
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            img = ImageOps.grayscale(img)
            img = img.filter(ImageFilter.MedianFilter(size=3))
            img = img.point(lambda p: 0 if p < 180 else 255)
            t = pytesseract.image_to_string(img, lang="eng", config="--oem 3 --psm 6")
            ocr_chunks.append(t or "")
        
        combined = "\n".join(ocr_chunks)
        last3 = "\n".join(ocr_chunks[-3:])
        
        for label, pat in [
            ("BG Number", r'(?:BG\s*No|Bank\s*Guarantee\s*No|Guarantee\s*No)[:\s.]*([^\n]{5,30})'),
            ("Date of Issue", r'(?:Date|DT|Issue\s*Date|Issuance\s*Date)[:\s]*([^\n]{5,30})'),
            ("Expiry", r'(?:valid\s*(?:up\s*to|till|until)|expiry\s*date|Date\s*of\s*Expiry)[:\s]*([^\n]{5,20})'),
            ("Claim/on or before", r'on\s*or\s*before[^\n]{0,50}'),
            ("Beneficiary", r'(?:in\s*favour\s*of|beneficiary|Name\s*of\s*the\s*Beneficiary)[:\s]*([^\n]{5,80})'),
        ]:
            for m in re.finditer(pat, combined, re.IGNORECASE):
                raw = m.group(0).strip()[:80]
                print(f"  {label}: {raw!r}")
                break
            else:
                print(f"  {label}: NOT FOUND")
        
        print(f"  --- LAST PAGE OCR (first 800 chars) ---")
        print(f"  {ocr_chunks[-1][:800]}")
    
    doc.close()
