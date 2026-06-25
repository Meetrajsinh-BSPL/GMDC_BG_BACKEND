from __future__ import annotations
"""Vision-based BG field extraction via OCI GenAI `cohere.command-a-vision`.

Renders the first N pages of the PDF to PNG and sends them as a multimodal
chat message to the vision model, asking for strict JSON.

Falls back to the text-based pipeline if the vision model errors or returns
unparseable output — see `field_builder.build_merged_fields`.
"""
import base64
import io
import json
import logging
import re

import fitz  # PyMuPDF
import oci
from PIL import Image

import config

logger = logging.getLogger(__name__)

_client = None

EXPECTED_KEYS = [
    "amount_of_bg", "bank_address", "bank_guarantee_number", "bg_issuing_bank",
    "claim_expiry_date", "contract_value", "currency", "date_of_issue",
    "expiry_date", "ifs_code", "in_favour_of", "rfp_number",
    "rfp_purchase_order_subject", "subject", "applicant",
]

SYSTEM_INSTRUCTIONS = """You are a highly accurate information extraction engine for Indian Bank Guarantee (BG) documents.
You will be shown page images of a Bank Guarantee PDF. Extract the following fields and return STRICT JSON.

Return JSON with EXACTLY these 15 keys (all strings, empty string if not present):

{
  "amount_of_bg": "",
  "applicant": "",
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

DEFINITIONS:
- bank_guarantee_number: The unique BG identifier near labels like "BANK GUARANTEE NO", "BG No", "Guarantee No". Uppercase alphanumeric, NO spaces.
- bg_issuing_bank: Name of the issuing bank, e.g. "ICICI Bank Limited", "State Bank of India".
- bank_address: Full branch address of the issuing bank.
- amount_of_bg: numeric value only (no currency, no commas). e.g. "2050000" or "2050000.00".
- currency: 3-letter code. "INR" for Rs/INR/Rupees.
- date_of_issue: DD/MM/YYYY.
- expiry_date: Validity end date of the BG (DD/MM/YYYY).
- claim_expiry_date: Last date to lodge a claim (DD/MM/YYYY), usually after expiry_date. Empty if the document only has a single validity date.
- ifs_code: IFSC of the issuing bank branch (4 letters + "0" + 6 alphanumerics).
- applicant: Name + address of the applicant / borrower (the party obtaining the BG).
- in_favour_of: Beneficiary name (usually "Gujarat Mineral Development Corporation Limited / GMDC").
- rfp_number: Tender / RFP / Purchase order number cited in the BG.
- rfp_purchase_order_subject: Short subject / title of the underlying RFP or contract.
- subject: Purpose of the BG (e.g. "Performance Security", "Earnest Money Deposit").
- contract_value: Underlying contract value if stated separately from the BG amount.

RULES:
1. Return ONLY the JSON object — no prose, no backticks, no explanation.
2. Read digits and letters very carefully. These documents are often OCR-hostile:
   - A character that sits BETWEEN two digits is almost always a DIGIT, not a letter.
     So treat "O" between digits as "0", and "I"/"l" between digits as "1".
   - Indian BG numbers almost NEVER contain the letter "O" — prefer "0".
   - Distinguish "5" vs "S", "8" vs "B", "2" vs "Z", "6" vs "G" by looking at the full pattern
     of surrounding characters.
3. If a field is genuinely not present, use "".
4. All 15 keys must be present in the output.
"""


def _get_client():
    global _client
    if _client is None:
        config.require_oci()
        oci_config = oci.config.from_file(config.OCI_CONFIG_FILE, config.OCI_CONFIG_PROFILE)
        _client = oci.generative_ai_inference.GenerativeAiInferenceClient(
            config=oci_config,
            service_endpoint=config.OCI_GENAI_ENDPOINT,
            retry_strategy=oci.retry.NoneRetryStrategy(),
            timeout=(10, 300),
        )
        logger.info("OCI GenerativeAI (vision) client initialised")
    return _client


def _render_pages(pdf_bytes: bytes, max_pages: int, zoom: float) -> list[bytes]:
    """Render first/last pages to PNG. Returns list of PNG bytes."""
    out: list[bytes] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        total = len(doc)
        # prefer first max_pages; most BG key fields sit on page 1 + cover letter
        indices = list(range(min(total, max_pages)))
        for i in indices:
            page = doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            png = pix.tobytes("png")
            # cap each image to ~1.2 MB by re-encoding if too big
            if len(png) > 1_200_000:
                img = Image.open(io.BytesIO(png)).convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85, optimize=True)
                png = buf.getvalue()
            out.append(png)
    return out


def _parse_json(text: str):
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    b_start = text.find("{")
    b_end = text.rfind("}")
    if b_start != -1 and b_end > b_start:
        text = text[b_start : b_end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Vision JSON parse error: %s; text=%s", e, text[:500])
        return None


def _build_message(images: list[bytes]):
    """Build a GenericChatRequest USER message with text + image parts."""
    models = oci.generative_ai_inference.models
    content_parts: list = [models.TextContent(text=(
        "Extract BG details from these page images. Return JSON per the schema. "
        "Be extremely careful with digits vs letters on the BG number and IFSC."
    ))]
    for png in images:
        b64 = base64.b64encode(png).decode("ascii")
        img_url = models.ImageUrl(url=f"data:image/png;base64,{b64}")
        content_parts.append(models.ImageContent(image_url=img_url))
    msg = models.Message(role="USER", content=content_parts)
    return msg


def extract_bg_fields_vision(pdf_bytes: bytes) -> dict:
    """Call `cohere.command-a-vision` on rendered pages. Returns
    ``{'success': bool, 'fields': {...}, 'error': str|None, 'pages_sent': int}``."""
    try:
        images = _render_pages(pdf_bytes, config.VISION_MAX_PAGES, config.VISION_PAGE_ZOOM)
    except Exception as e:
        logger.exception("PDF render to images failed")
        return {"success": False, "fields": {}, "error": f"render failed: {e}", "pages_sent": 0}

    if not images:
        return {"success": False, "fields": {}, "error": "no pages rendered", "pages_sent": 0}

    try:
        client = _get_client()
    except Exception as e:
        logger.error("OCI client init failed: %s", e)
        return {"success": False, "fields": {}, "error": f"OCI unavailable: {e}", "pages_sent": 0}

    models = oci.generative_ai_inference.models
    req = models.GenericChatRequest()
    req.api_format = models.BaseChatRequest.API_FORMAT_GENERIC
    req.messages = [
        models.Message(
            role="SYSTEM",
            content=[models.TextContent(text=SYSTEM_INSTRUCTIONS)],
        ),
        _build_message(images),
    ]
    req.max_tokens = 2000
    req.temperature = 0.1
    req.top_p = 0.9
    req.is_stream = False

    details = models.ChatDetails()
    details.serving_mode = models.OnDemandServingMode(model_id=config.OCI_VISION_MODEL_ID)
    details.chat_request = req
    details.compartment_id = config.OCI_COMPARTMENT_ID

    try:
        response = client.chat(details)
    except Exception as e:
        logger.error("Vision chat call failed: %s", e)
        return {"success": False, "fields": {}, "error": f"vision call failed: {e}", "pages_sent": len(images)}

    # GenericChatResponse exposes choices -> message -> content[] -> TextContent.text
    try:
        choices = response.data.chat_response.choices
        text_parts: list[str] = []
        for ch in choices:
            for c in ch.message.content:
                t = getattr(c, "text", None)
                if t:
                    text_parts.append(t)
        generated = "\n".join(text_parts).strip()
    except Exception as e:
        logger.error("Unexpected vision response shape: %s", e)
        return {"success": False, "fields": {}, "error": f"bad response: {e}", "pages_sent": len(images)}

    logger.info("Vision raw response (first 500 chars): %s", generated[:500])

    parsed = _parse_json(generated)
    if parsed is None:
        return {"success": False, "fields": {}, "error": "JSON parse error", "pages_sent": len(images)}

    for k in EXPECTED_KEYS:
        parsed.setdefault(k, "")

    return {"success": True, "fields": parsed, "error": None, "pages_sent": len(images)}
