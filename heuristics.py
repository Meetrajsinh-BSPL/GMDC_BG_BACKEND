from __future__ import annotations
"""Regex-based heuristic field extraction from BG text."""
import re

from normalizers import (
    dehyphenate,
    fix_bg_number,
    fix_common_ocr_confusions_identifier,
    fix_ifsc_code,
    normalize_spaces,
)

# Flexible date token matching numeric (01-06-2030) and month-name (01-JUN-2030) forms.
FLEX_DATE = r"([0-9]{1,2}[-/\s](?:[0-9]{1,2}|[A-Za-z]{3,9})[-/\s,]+[0-9]{2,4})"

# BG-number allowed characters. Pipe is included because PyMuPDF sometimes renders I as |.
_BG_CHARS = r"[A-Z0-9/|\-]"
_SEP = r"[:\s.+]*"


def extract_cover_table_cell(text: str, label: str) -> str:
    """Extract a value from markdown-pipe-table cells: | Label | Value |."""
    if not text:
        return ""
    m = re.search(
        rf"\|\s*{re.escape(label)}\s*\|\s*([^\|]+?)\s*\|", text, flags=re.IGNORECASE
    )
    return normalize_spaces(m.group(1)) if m else ""


def extract_fields(text: str) -> dict:
    text = dehyphenate(text)
    fields: dict = {}

    def grab(pattern, key, flags=re.IGNORECASE, group=1, post=None):
        if fields.get(key):
            return
        m = re.search(pattern, text, flags)
        if not m:
            return
        val = m.group(group).strip()
        if post:
            val = post(val)
        if val:
            fields[key] = val

    # ---- BG number ----
    bg_patterns = [
        r"BANK\s*GUARANTEE\s*NO" + _SEP + r"(" + _BG_CHARS + r"+)",
        r"BG\s*No" + _SEP + r"(" + _BG_CHARS + r"+)",
        r"Guarantee\s*No(?:\.|\s*:|\s*\.)?" + _SEP + r"(" + _BG_CHARS + r"+)",
        r"Guarantee\s*Number" + _SEP + r"(" + _BG_CHARS + r"+)",
        r"Bank\s*Guarantee\s*Number" + _SEP + r"(" + _BG_CHARS + r"+)",
        r"(?:letter\s+of\s+)?guarantee\s+no" + _SEP + r"(" + _BG_CHARS + r"+)",
    ]
    for pat in bg_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            fields["bank_guarantee_number"] = fix_bg_number(m.group(1).strip())
            break

    # ---- Dates ----
    date_issue_pats = [
        r"(?:ISSUANCE|BG\s*Issue)\s*DATE?[:\s]*" + FLEX_DATE,
        r"Issue\s*[Dd]ate\s*[:\-]\s*" + FLEX_DATE,
        r"DT[:\s]*([0-9]{1,2}[/.][0-9]{1,2}[/.][0-9]{2,4})",
        r"Date\s*[:\-]\s*([0-9]{1,2}[/.][0-9]{1,2}[/.][0-9]{2,4})",
        r"Place\s*(?:and|&)\s*Date\s*[:\-]\s*[A-Za-z,.\s]*?" + FLEX_DATE,
        r"Dated?\s*[:\-]\s*" + FLEX_DATE,
    ]
    for pat in date_issue_pats:
        grab(pat, "date_of_issue")

    expiry_pats = [
        r"Date\s*of\s*Expiry\s*[:\-]\s*" + FLEX_DATE,
        r"BG\s*Expiry\s*Date[:\s]*" + FLEX_DATE,
        r"Stated\s*Expiry\s*[Dd]ate[\s:]*" + FLEX_DATE,
        r"valid\s*up\s*to\s*" + FLEX_DATE,
        r"Valid\s*(?:till|until|upto|up\s*to)[:\s]*" + FLEX_DATE,
    ]
    for pat in expiry_pats:
        grab(pat, "expiry_date")
    if not fields.get("expiry_date"):
        m = re.search(
            r"for\s*the\s*period\s*" + FLEX_DATE + r"\s*(?:to|-|till)\s*" + FLEX_DATE,
            text, re.IGNORECASE,
        )
        if m:
            fields["expiry_date"] = m.group(2).strip()

    claim_pats = [
        r"Claim\s*Expiry\s*Date[:\s]*" + FLEX_DATE,
        r"Stated\s*Claim\s*(?:Expiry|Rap?ry)\s*[Dd]a(?:te|le)[\s:]*" + FLEX_DATE,
        r"on\s*or\s*before\s*(?:the\s*)?(?:\(date\)\s*)?" + FLEX_DATE,
    ]
    for pat in claim_pats:
        grab(pat, "claim_expiry_date")

    # ---- IFSC ----
    m = re.search(r"\b([A-Za-z]{4}0[A-Za-z0-9]{6})\b", text)
    if m:
        fields["ifs_code"] = fix_ifsc_code(m.group(1))
    else:
        grab(r"IFSC[:\s]*([A-Z]{4}0[0-9A-Z]{6})", "ifs_code", post=fix_ifsc_code)

    # ---- Amount ----
    grab(r"(?:BG\s*Amount|Bank\s*Guarantee\s*Amount)[:\s]*([^\n]+)", "amount_of_bg")
    grab(r"(?:Rs\.?|INR)\s*[:.]?\s*([0-9,]+(?:\.[0-9]{2})?)", "amount_of_bg")
    grab(
        r"amount\s*(?:of|is)?[:\s]*(?:Rs\.?|INR)?\s*([0-9,]+(?:\.[0-9]{2})?)",
        "amount_of_bg",
    )

    # ---- Beneficiary ----
    grab(r"Name\s*of\s*the\s*Beneficiary[:\s-]*([^\n]+)", "in_favour_of")
    if not fields.get("in_favour_of"):
        grab(
            r"To,\s*([\s\S]{0,200})Subject:", "in_favour_of",
            post=lambda s: s.splitlines()[0].strip() if s.strip() else s,
        )

    # ---- Applicant ----
    grab(r"Name\s*of\s*the\s*Contractor\s*[:\-]\s*(?:M/s\.?\s*)?([^\n]+)", "applicant_name")
    grab(r"Applicant\s*[Nn]ame[:\s-]*([^\n]+)", "applicant_name")
    grab(
        r"M/s[\.\s]+([A-Z][A-Za-z0-9 &./,()-]{3,}(?:PVT[\s.]*LTD|PRIVATE\s+LIMITED|LLP|LIMITED))",
        "applicant_name",
    )

    # ---- Bank ----
    grab(r"Name\s*of\s*the\s*Bank\s*[:\-]\s*([^\n]+)", "bg_issuing_bank")
    grab(r"Issuing\s*Bank.*?:\s*([^\n]+)", "bg_issuing_bank")
    grab(
        r"((?:Yes|ICICI|HDFC|Axis|State Bank of India|SBI|Union Bank|Punjab National|"
        r"Kotak|Canara)\s+Bank\s*(?:Limited|Ltd\.?)?)",
        "bg_issuing_bank",
    )

    # ---- RFP / PO ----
    grab(
        r"Tender\s*bearing\s*No\.?\s*([A-Z0-9/._-]+)", "rfp_number",
        post=fix_common_ocr_confusions_identifier,
    )
    grab(
        r"(?:RFP|Tender)\s*No[:\s-]*([A-Z0-9/._-]+)", "rfp_number",
        post=fix_common_ocr_confusions_identifier,
    )
    grab(
        r"(?:P\.?O\.?\s*No|Purchase\s*Order\s*No)[:\s-]*([A-Z0-9/._-]+)",
        "rfp_number", post=fix_common_ocr_confusions_identifier,
    )

    # ---- Subject ----
    grab(r"Subject\s*[:\-]\s*([^\n]+)", "rfp_purchase_order_subject")
    grab(r"BANK\s*GUARANTEE\s*FOR\s*([^\n]+)", "subject")

    return fields
