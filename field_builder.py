from __future__ import annotations
"""Build the final field dict.

Primary path: `cohere.command-a-vision` on page images.
Fallback path: legacy text-OCR + cohere.command-r pipeline for when vision
is unavailable or errors.
"""
import logging
import re

from cohere_client import extract_bg_fields as extract_text_based
from heuristics import extract_cover_table_cell, extract_fields
from normalizers import (
    dehyphenate,
    fix_bg_number,
    fix_common_ocr_confusions_identifier,
    fix_ifsc_code,
    is_valid_bg_number,
    normalize_amount_numeric,
    reconcile_bg_with_bank,
    to_dd_mm_yyyy,
)
from vision_extractor import extract_bg_fields_vision

logger = logging.getLogger(__name__)


def _post_process(fields: dict, full_text: str = "") -> dict:
    out = dict(fields)

    if out.get("amount_of_bg"):
        out["amount_of_bg"] = normalize_amount_numeric(out["amount_of_bg"])

    if out.get("ifs_code"):
        out["ifs_code"] = fix_ifsc_code(out["ifs_code"])

    if out.get("bank_guarantee_number"):
        bg = fix_bg_number(fix_common_ocr_confusions_identifier(out["bank_guarantee_number"]))
        if is_valid_bg_number(bg):
            out["bank_guarantee_number"] = bg
        else:
            out["bank_guarantee_number"] = ""

    if out.get("bank_guarantee_number") and out.get("bg_issuing_bank"):
        before = out["bank_guarantee_number"]
        after = reconcile_bg_with_bank(before, out["bg_issuing_bank"])
        if after != before:
            logger.info("BG# reconciled via bank pattern: %s -> %s", before, after)
            out["bank_guarantee_number"] = after

    if out.get("bg_issuing_bank"):
        out["bg_issuing_bank"] = (
            out["bg_issuing_bank"]
            .replace("1CICI", "ICICI")
            .replace("HDF0", "HDFC")
            .replace("SBl", "SBI")
        )

    for k in ("date_of_issue", "expiry_date", "claim_expiry_date"):
        if out.get(k):
            out[k] = to_dd_mm_yyyy(out[k])

    if not (out.get("in_favour_of") or "").strip() and full_text:
        if re.search(r"GMDC|Gujarat\s*Mineral", full_text, re.IGNORECASE):
            out["in_favour_of"] = "Gujarat Mineral Development Corporation Limited (GMDC)"

    for legacy in ("applicant_name", "applicant_address", "in_favour_address"):
        out.pop(legacy, None)

    return out


def build_merged_fields(pdf_bytes, full_text="", last_pages_text=""):
    vision = extract_bg_fields_vision(pdf_bytes)
    if vision.get("success"):
        merged = _post_process(vision["fields"], full_text=full_text)
        merged["_extraction_method"] = f"vision:{vision.get('pages_sent', 0)}p"
        return merged

    logger.warning("Vision extraction failed (%s) — falling back to text pipeline",
                   vision.get("error"))

    full_text = dehyphenate(full_text)
    last_pages_text = dehyphenate(last_pages_text)

    heur = extract_fields(full_text) if full_text else {}
    if last_pages_text:
        heur_last = extract_fields(last_pages_text)
        for k, v in heur_last.items():
            if v:
                heur[k] = v

    text_result = extract_text_based(full_text, last_pages_text) if full_text else {
        "success": False, "fields": {}
    }
    merged = dict(text_result.get("fields", {})) if text_result.get("success") else {}

    for k, v in heur.items():
        if not (merged.get(k) or "").strip():
            merged[k] = v

    cover_applicant = extract_cover_table_cell(full_text, "Name and Address of the Applicant") if full_text else ""
    applicant_name = (merged.pop("applicant_name", "") or "").strip()
    applicant_address = (merged.pop("applicant_address", "") or "").strip()
    if cover_applicant:
        merged["applicant"] = cover_applicant
    elif applicant_name or applicant_address:
        merged["applicant"] = f"{applicant_name} {applicant_address}".strip()

    ifo = (merged.get("in_favour_of") or "").strip()
    ifo_addr = (merged.pop("in_favour_address", "") or "").strip()
    if ifo or ifo_addr:
        merged["in_favour_of"] = f"{ifo} {ifo_addr}".strip()

    merged = _post_process(merged, full_text=full_text)
    merged["_extraction_method"] = "text_fallback"
    return merged
