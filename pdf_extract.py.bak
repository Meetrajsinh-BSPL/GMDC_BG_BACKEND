from __future__ import annotations
"""PDF text extraction cascade: pdfplumber -> PyMuPDF -> pypdf -> OCR."""
import io
import logging
import os
import re

import fitz  # PyMuPDF

from normalizers import normalize_spaces

logger = logging.getLogger(__name__)


def _looks_like_images_only(s: str) -> bool:
    if not s:
        return False
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if not lines:
        return False
    return all(ln.startswith("<image:") and ln.endswith(">") for ln in lines)


def _contains_real_text(s: str) -> bool:
    if _looks_like_images_only(s):
        return False
    return bool(re.search(r"[A-Za-z0-9]{3,}", s))


def _ocr_pages(pdf_bytes: bytes, zoom: int = 2) -> list[str]:
    """OCR every page. Returns list of per-page text (may be empty strings)."""
    try:
        import pytesseract  # type: ignore
        from PIL import Image, ImageFilter, ImageOps  # type: ignore
    except ImportError as e:
        logger.warning("OCR deps unavailable: %s", e)
        return []

    tess_cmd = os.environ.get("TESSERACT_CMD")
    if tess_cmd:
        pytesseract.pytesseract.tesseract_cmd = tess_cmd

    chunks: list[str] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        logger.info("OCR: processing %d pages at %dx zoom", len(doc), zoom)
        for i, page in enumerate(doc):
            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                img = ImageOps.grayscale(img)
                img = img.filter(ImageFilter.MedianFilter(size=3))
                img = img.point(lambda p: 0 if p < 180 else 255)
                text = pytesseract.image_to_string(img, lang="eng", config="--oem 3 --psm 6")
                chunks.append(text or "")
            except Exception as e:
                logger.warning("OCR failed on page %d: %s", i + 1, e)
                chunks.append("")
    return chunks


def _pymupdf_text(pdf_bytes: bytes) -> list[str]:
    chunks: list[str] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            t = page.get_text("text") or ""
            if not t.strip():
                try:
                    blocks = page.get_text("blocks") or []
                    t = "\n".join(
                        b[4] for b in blocks
                        if isinstance(b, (list, tuple)) and len(b) > 4 and isinstance(b[4], str)
                    ).strip()
                except Exception:
                    t = ""
            if not t.strip():
                try:
                    d = page.get_text("dict") or {}
                    t = "\n".join(
                        s.get("text", "")
                        for b in d.get("blocks", [])
                        for ln in b.get("lines", [])
                        for s in ln.get("spans", [])
                    ).strip()
                except Exception:
                    t = ""
            chunks.append(t)
    return chunks


def _pdfplumber_text(pdf_bytes: bytes) -> list[str]:
    import pdfplumber  # type: ignore

    chunks: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return chunks


def _pypdf_text(pdf_bytes: bytes) -> list[str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        from PyPDF2 import PdfReader  # type: ignore
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return [(p.extract_text() or "") for p in reader.pages]


def extract_text_from_pdf(pdf_bytes: bytes) -> tuple[str, str]:
    """Return ``(full_text, last_pages_text)``.

    Tries pdfplumber, PyMuPDF, pypdf, then OCR, and stops at the first one that
    produces something resembling real text.
    """
    extractors = [
        ("pdfplumber", _pdfplumber_text),
        ("PyMuPDF", _pymupdf_text),
        ("pypdf", _pypdf_text),
    ]
    for name, fn in extractors:
        try:
            chunks = fn(pdf_bytes)
        except Exception as e:
            logger.warning("%s extraction failed: %s", name, e)
            continue
        if not chunks:
            continue
        combined = normalize_spaces("\n".join(chunks))
        if combined and _contains_real_text(combined):
            logger.info("%s extracted %d chars from %d pages", name, len(combined), len(chunks))
            last = normalize_spaces("\n".join(chunks[-3:]))
            return combined, last

    try:
        ocr_chunks = _ocr_pages(pdf_bytes, zoom=2)
    except Exception as e:
        logger.warning("OCR extraction failed: %s", e)
        ocr_chunks = []
    if ocr_chunks:
        combined = normalize_spaces("\n".join(ocr_chunks))
        if combined:
            logger.info("OCR extracted %d chars from %d pages", len(combined), len(ocr_chunks))
            last = normalize_spaces("\n".join(ocr_chunks[-3:]))
            return combined, last

    return "", ""


def ocr_first_pages_highres(pdf_bytes: bytes, n_pages: int = 2) -> str:
    """High-zoom OCR of first N pages (for BG-number retry).

    Runs two passes per page and concatenates both outputs so that downstream
    regex sees as many candidate strings as possible:
      (a) default PSM 6 (assume uniform block of text)
      (b) PSM 7 (single line) + charset whitelist (A-Z0-9/-) to aggressively
          collapse O↔0 / I↔1 confusion on label lines like "BG No.: ...".
    """
    try:
        import pytesseract  # type: ignore
        from PIL import Image, ImageFilter, ImageOps  # type: ignore
    except ImportError:
        return ""
    chunks: list[str] = []
    whitelist_cfg = (
        "--oem 3 --psm 6 "
        "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/-"
    )
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for i in range(min(len(doc), n_pages)):
                pix = doc[i].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                img = ImageOps.grayscale(img)
                img = img.filter(ImageFilter.MedianFilter(size=3))
                img = img.point(lambda p: 0 if p < 180 else 255)
                try:
                    t1 = pytesseract.image_to_string(
                        img, lang="eng", config="--oem 3 --psm 6"
                    ) or ""
                except Exception:
                    t1 = ""
                try:
                    t2 = pytesseract.image_to_string(
                        img, lang="eng", config=whitelist_cfg
                    ) or ""
                except Exception:
                    t2 = ""
                chunks.append(t1)
                if t2.strip():
                    chunks.append(t2)
    except Exception as e:
        logger.warning("High-res OCR retry failed: %s", e)
        return ""
    return "\n".join(chunks)
