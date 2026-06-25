from __future__ import annotations
"""OCI Cohere client wrapper for BG field extraction and validation."""
import json
import logging
import re

import oci

import config

logger = logging.getLogger(__name__)

_client = None

EXPECTED_KEYS = [
    "amount_of_bg", "bank_address", "bank_guarantee_number", "bg_issuing_bank",
    "claim_expiry_date", "contract_value", "currency", "date_of_issue",
    "expiry_date", "ifs_code", "in_favour_of", "rfp_number",
    "rfp_purchase_order_subject", "subject",
]

SYSTEM_INSTRUCTIONS = """You are a highly accurate information extraction engine for Indian Bank Guarantees (BG).
You will be given raw text of a Bank Guarantee (possibly noisy OCR) and must extract ONLY
the following fields in **strict JSON**.

Return JSON with EXACTLY these keys:

{
  "amount_of_bg": "",
  "bank_address": "",
  "bank_guarantee_number": "",
  "bg_issuing_bank": "",
  "claim_expiry_date": "",
  "contract_value": "",
  "currency": "",
  "date_of_issue": "",
  "expiry_date": "",
  "ifs_code": "",
  "in_favour_of": "",
  "rfp_number": "",
  "rfp_purchase_order_subject": "",
  "subject": ""
}

DEFINITIONS & HINTS:

- "bank_guarantee_number": Look for "BANK GUARANTEE NO:", "BG No.", "Guarantee No.", etc.
  Alphanumeric identifier, letters + digits only, NO spaces, NO lowercase.
  Typical formats: "15300100017423", "1499NDDG00011624", "027GT02240530010", "167411LG001323".
  If truly unreadable, return empty string rather than garbage.
- "bg_issuing_bank": Bank name only, e.g. "Axis Bank Limited"
- "bank_address": Full branch address
- "amount_of_bg": Return ONLY the numeric part without currency or text.
- "currency": "INR", "USD", etc. For Rs./INR return "INR"
- "date_of_issue": Return in DD/MM/YYYY format.
- "expiry_date": The BG VALIDITY end date. Different from claim_expiry_date.
- "claim_expiry_date": Last date to lodge a claim (usually after expiry_date).
- "ifs_code": IFSC code if present
- "in_favour_of": Beneficiary name
- "rfp_number": RFP/tender number
- "rfp_purchase_order_subject": Brief RFP subject/title
- "subject": BG purpose
- "contract_value": Contract value if mentioned separately from BG amount

IMPORTANT:
1. Return ONLY a well-formed JSON object (no backticks, no comments, no explanation)
2. Use "" for any field not found. Do NOT invent values.
3. All 14 keys MUST exist.
4. Dates: DD/MM/YYYY. Amount: numeric only.
5. For GMDC documents, beneficiary is Gujarat Mineral Development Corporation.
6. OCR-CONFUSION RULE — critical for alphanumeric IDs (bank_guarantee_number, ifs_code,
   rfp_number): OCR often confuses the letter O with the digit 0, and the letters I/l with
   the digit 1. When a character sits BETWEEN two digits, prefer the DIGIT form (0, 1).
   When surrounded by letters, prefer the LETTER form (O, I). Indian BG numbers almost
   never contain the letter 'O'; treat any 'O' adjacent to a digit as '0'. Similarly treat
   adjacent 'I' or 'l' as '1'. Example fixes: "167411LG00I323" -> "167411LG001323",
   "O27GT02243400020" -> "027GT02243400020"."""


def _get_client():
    global _client
    if _client is None:
        config.require_oci()
        oci_config = oci.config.from_file(config.OCI_CONFIG_FILE, config.OCI_CONFIG_PROFILE)
        _client = oci.generative_ai_inference.GenerativeAiInferenceClient(
            config=oci_config,
            service_endpoint=config.OCI_GENAI_ENDPOINT,
            retry_strategy=oci.retry.NoneRetryStrategy(),
            timeout=(10, 240),
        )
        logger.info("OCI GenerativeAI client initialised")
    return _client


def _parse_json(text: str):
    text = text.strip()
    fence = re.search(r"```json(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    b_start = text.find("{")
    b_end = text.rfind("}")
    if b_start != -1 and b_end != -1 and b_end > b_start:
        text = text[b_start:b_end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Cohere JSON parse error: %s; text=%s", e, text[:500])
        return None


def extract_bg_fields(extracted_text: str, last_pages_text: str = "") -> dict:
    """Call Cohere and return ``{'success': bool, 'fields': {...}, 'error': ...}``."""
    if not extracted_text or not extracted_text.strip():
        return {"success": False, "fields": {}, "error": "No text extracted from PDF"}

    try:
        client = _get_client()
    except Exception as e:
        logger.error("OCI client init failed: %s", e)
        return {"success": False, "fields": {}, "error": f"OCI unavailable: {e}"}

    extraction_text = extracted_text
    if last_pages_text:
        extraction_text = (
            f"{last_pages_text}\n\n--- Full Document Context ---\n\n{extracted_text}"
        )
    extraction_text = extraction_text[: config.COHERE_MAX_INPUT_CHARS]

    user_message = (
        "Extract BG details from the following text and return JSON as per the schema.\n"
        "Pay special attention to amounts, dates, and bank details.\n\n"
        f"BG TEXT:\n{extraction_text}"
    )

    req = oci.generative_ai_inference.models.CohereChatRequest()
    req.message = user_message
    req.max_tokens = 1800
    req.temperature = 0.1
    req.frequency_penalty = 0.0
    req.top_p = 0.75
    req.preamble_override = SYSTEM_INSTRUCTIONS

    details = oci.generative_ai_inference.models.ChatDetails()
    details.serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(
        model_id=config.OCI_MODEL_ID
    )
    details.chat_request = req
    details.compartment_id = config.OCI_COMPARTMENT_ID

    try:
        response = client.chat(details)
    except Exception as e:
        logger.error("Cohere API call failed: %s", e)
        return {"success": False, "fields": {}, "error": f"Cohere call failed: {e}"}

    raw = getattr(response.data, "chat_response", None)
    generated = raw.text if raw and hasattr(raw, "text") else str(response.data)
    logger.info("Cohere raw response (first 500 chars): %s", generated[:500])

    parsed = _parse_json(generated)
    if parsed is None:
        return {"success": False, "fields": {}, "error": "JSON parse error"}

    for k in EXPECTED_KEYS:
        parsed.setdefault(k, "")

    return {"success": True, "fields": parsed, "error": None}


def validate_bg(document_text: str, api_data: str) -> float:
    """Return a 0..1 confidence score that the document matches the API data."""
    prompt = f"""You are an expert at verifying Indian Bank Guarantee documents.
Given the following document text and the following ICICI API data, rate from 0 to 1 how likely it is that the document and the API data refer to the same Bank Guarantee.
Reply ONLY with a decimal score between 0.0 and 1.0 (no extra text).

Document text:
{document_text[:4000]}

ICICI API data:
{api_data[:4000]}

Score:"""

    try:
        client = _get_client()
    except Exception:
        return 0.0

    req = oci.generative_ai_inference.models.CohereChatRequest()
    req.message = prompt
    req.max_tokens = 10
    req.temperature = 0

    details = oci.generative_ai_inference.models.ChatDetails()
    details.serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(
        model_id=config.OCI_MODEL_ID
    )
    details.chat_request = req
    details.compartment_id = config.OCI_COMPARTMENT_ID

    try:
        response = client.chat(details)
        text = response.data.chat_response.text.strip()
    except Exception as e:
        logger.error("Cohere validation call failed: %s", e)
        return 0.0

    matches = re.findall(r"\b(?:0(?:\.\d+)?|1(?:\.0+)?)\b", text)
    if not matches:
        return 0.0
    try:
        return max(0.0, min(1.0, float(matches[0])))
    except ValueError:
        return 0.0
