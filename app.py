from __future__ import annotations
"""Flask application: BG Processor API."""
import logging
from datetime import datetime
from functools import wraps

from flasgger import Swagger
from flask import Flask, jsonify, request
from flask_cors import CORS

import config
from crypto_utils import EncryptionHelper
from field_builder import build_merged_fields
from icici_client import query as icici_query
from pdf_extract import extract_text_from_pdf
from validation import (
    amount_matches,
    bank_name_matches,
    date_matches,
    flatten_json_text,
    id_matches,
    loose_contains,
    subject_matches,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _require_api_key(fn):
    """No-op if API_KEY is unset; otherwise enforce matching X-API-Key header."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if config.API_KEY:
            supplied = request.headers.get("X-API-Key", "").strip()
            if supplied != config.API_KEY:
                return jsonify({"error": "Unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


def _validate_pdf_upload():
    """Returns (pdf_bytes, None) on success or (None, (response, status)) on error."""
    if "file" not in request.files:
        return None, (jsonify({
            "error": "No file uploaded",
            "message": "Expected multipart/form-data with file",
        }), 400)
    file = request.files["file"]
    if file.filename == "":
        return None, (jsonify({"error": "No file selected"}), 400)
    if not file.filename.lower().endswith(".pdf"):
        return None, (jsonify({"error": "Only PDF files are allowed"}), 400)
    pdf_bytes = file.read()
    if not pdf_bytes.startswith(b"%PDF-"):
        return None, (jsonify({
            "error": "Uploaded file is not a valid PDF (missing %PDF- header)"
        }), 400)
    return pdf_bytes, None


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

    CORS(
        app,
        resources={r"/*": {
            "origins": config.CORS_ALLOWED_ORIGINS,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "Accept", "X-API-Key"],
        }},
    )

    app.config["SWAGGER"] = {
        "title": "BG Processor API",
        "uiversion": 3,
        "specs_route": "/apidocs/",
    }
    Swagger(app, template={
        "swagger": "2.0",
        "info": {
            "title": "BG Processor API",
            "description": "Extract Bank Guarantee fields from PDFs and validate against ICICI",
            "version": "4.0.0",
        },
        "basePath": "/",
        "schemes": ["https", "http"],
        "definitions": {
            "ExtractBGFieldsResponse": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "extraction_method": {"type": "string"},
                    "fields": {
                        "type": "object",
                        "properties": {
                            "applicant": {"type": "string"},
                            "in_favour_of": {"type": "string"},
                            "bg_issuing_bank": {"type": "string"},
                            "bank_address": {"type": "string"},
                            "ifs_code": {"type": "string"},
                            "bank_guarantee_number": {"type": "string"},
                            "date_of_issue": {"type": "string"},
                            "expiry_date": {"type": "string"},
                            "claim_expiry_date": {"type": "string"},
                            "currency": {"type": "string"},
                            "amount_of_bg": {"type": "string"},
                            "contract_value": {"type": "string"},
                            "rfp_number": {"type": "string"},
                            "rfp_purchase_order_subject": {"type": "string"},
                            "subject": {"type": "string"},
                        },
                    },
                    "extracted_text_preview": {"type": "string"},
                },
            },
            "ErrorResponse": {
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "message": {"type": "string"},
                },
            },
            "ICICIQuerySuccess": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "correlation_id": {"type": "string"},
                    "data": {"type": "object"},
                },
            },
        },
    })

    @app.errorhandler(413)
    def _too_large(_e):
        return jsonify({
            "error": "File too large",
            "max_bytes": config.MAX_CONTENT_LENGTH,
        }), 413

    @app.route("/health", methods=["GET"])
    def health_check():
        """Health Check
        ---
        tags: [System]
        responses:
          200:
            description: OK
        """
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "BG Processor API",
        })

    @app.route("/extract-bg-fields", methods=["POST", "OPTIONS"])
    @_require_api_key
    def extract_bg_fields_route():
        """Extract BG Fields
        ---
        tags: [BG Extraction]
        consumes: [multipart/form-data]
        parameters:
          - in: formData
            name: file
            type: file
            required: true
        responses:
          200:
            description: Extracted fields
            schema:
              $ref: '#/definitions/ExtractBGFieldsResponse'
          400:
            description: Bad request
            schema:
              $ref: '#/definitions/ErrorResponse'
          422:
            description: No extractable text
            schema:
              $ref: '#/definitions/ErrorResponse'
        """
        if request.method == "OPTIONS":
            return "", 200
        pdf_bytes, err = _validate_pdf_upload()
        if err:
            return err
        logger.info("Uploaded PDF size: %d bytes", len(pdf_bytes))

        # Best-effort text extraction (used only as fallback + preview).
        try:
            full_text, last_pages_text = extract_text_from_pdf(pdf_bytes)
        except Exception as e:
            logger.warning("Text extraction failed (non-fatal): %s", e)
            full_text, last_pages_text = "", ""

        try:
            merged = build_merged_fields(pdf_bytes, full_text, last_pages_text)
        except Exception as e:
            logger.exception("Field extraction failed")
            return jsonify({"error": f"Field extraction failed: {e}"}), 500

        method = merged.pop("_extraction_method", "vision")
        return jsonify({
            "success": True,
            "extraction_method": method,
            "fields": merged,
            "extracted_text_preview": full_text[:1000],
        })

    @app.route("/query-icici", methods=["POST", "OPTIONS"])
    @_require_api_key
    def query_icici_route():
        """Query ICICI eBG Issuance/Amend
        ---
        tags: [ICICI]
        consumes: [application/json]
        parameters:
          - in: body
            name: body
            required: true
            schema:
              type: object
              required: [corpId, fromDate, toDate, attachmentRequired]
              properties:
                corpId: {type: string}
                referenceNumber: {type: string}
                fromDate: {type: string}
                toDate: {type: string}
                attachmentRequired: {type: string, enum: [Y, N]}
        responses:
          200: {description: Success, schema: {$ref: '#/definitions/ICICIQuerySuccess'}}
          400: {description: Bad request, schema: {$ref: '#/definitions/ErrorResponse'}}
        """
        if request.method == "OPTIONS":
            return "", 200

        data = request.get_json(silent=True) or {}
        required = ["corpId", "fromDate", "toDate", "attachmentRequired"]
        for field in required:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        plain_request = {
            "corpId": data["corpId"],
            "referenceNumber": data.get("referenceNumber", ""),
            "fromDate": data["fromDate"],
            "toDate": data["toDate"],
            "attachmentRequired": data["attachmentRequired"],
        }

        try:
            result = icici_query(plain_request)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500
        except Exception as e:
            logger.exception("ICICI query failed")
            return jsonify({"error": str(e)}), 500

        body = {
            "status": "success" if result["ok"] else "error",
            "status_code": result["status_code"],
            "correlation_id": result["correlation_id"],
            "data": result["decrypted"],
            "raw_response": result["raw_response"],
            "request_details": {
                "plain_request": result["plain_request"],
                "request_format": "corpId|referenceNumber|fromDate|toDate|attachmentRequired",
            },
        }
        if not result["ok"]:
            body["message"] = result.get("error") or result.get("raw_text") or "ICICI returned non-200"
        status = 200 if result["ok"] else (result["status_code"] or 500)
        return jsonify(body), status

    @app.route("/validate-upload", methods=["POST", "OPTIONS"])
    @_require_api_key
    def validate_upload_route():
        """End-to-End: Upload PDF, Extract, Query ICICI, Validate
        ---
        tags: [End-to-End]
        consumes: [multipart/form-data]
        parameters:
          - in: formData
            name: file
            type: file
            required: true
        responses:
          200: {description: Validation results}
          400: {description: Bad request}
          422: {description: No extractable text or missing BG number}
        """
        if request.method == "OPTIONS":
            return "", 200

        pdf_bytes, err = _validate_pdf_upload()
        if err:
            return err
        logger.info("Uploaded PDF size: %d bytes", len(pdf_bytes))

        try:
            full_text, last_pages_text = extract_text_from_pdf(pdf_bytes)
        except Exception as e:
            logger.warning("Text extraction failed (non-fatal): %s", e)
            full_text, last_pages_text = "", ""

        merged = build_merged_fields(pdf_bytes, full_text, last_pages_text)
        method = merged.pop("_extraction_method", "vision")

        bg_number = (merged.get("bank_guarantee_number") or "").strip()
        if not bg_number:
            return jsonify({
                "error": "Unable to determine Bank Guarantee Number from the document.",
                "message": "bank_guarantee_number is required as referenceNumber for ICICI query.",
                "extracted_fields": merged,
            }), 422

        plain_request = {
            "corpId": config.ICICI_CORP_ID,
            "referenceNumber": bg_number,
            "fromDate": "",
            "toDate": "",
            "attachmentRequired": "Y",
        }

        try:
            result = icici_query(plain_request)
        except RuntimeError as e:
            return jsonify({"error": str(e), "extracted_fields": merged}), 500

        if not result["ok"]:
            return jsonify({
                "error": "ICICI API returned non-200",
                "status_code": result["status_code"],
                "icici_correlation_id": result["correlation_id"],
                "raw_response": result["raw_response"],
                "decrypted_error": result["decrypted"],
                "icici_request": plain_request,
                "extracted_fields": merged,
            }), result["status_code"] or 500

        decrypted = result["decrypted"]
        api_text = flatten_json_text(decrypted)

        validation_results: dict[str, int] = {}
        matched, total = 0, 0
        for field, value in merged.items():
            if not isinstance(value, str) or not value.strip():
                continue
            total += 1
            v = value.strip()
            if field == "amount_of_bg":
                r = amount_matches(v, api_text)
            elif field in ("date_of_issue", "claim_expiry_date", "expiry_date"):
                r = date_matches(v, api_text)
            elif field in ("bank_guarantee_number", "rfp_number", "ifs_code"):
                r = id_matches(v, api_text)
            elif field == "bg_issuing_bank":
                r = bank_name_matches(v, decrypted, api_text)
            elif field == "subject":
                r = subject_matches(v, api_text)
            else:
                r = 1 if loose_contains(v, api_text) else 0
            validation_results[field] = r
            matched += r

        return jsonify({
            "success": True,
            "extraction_method": method,
            "fields": merged,
            "icici_request": plain_request,
            "icici_correlation_id": result["correlation_id"],
            "validation_results": validation_results,
            "matched_count": matched,
            "total_fields": total,
            "bankapi_data": decrypted,
        })

    if config.DEBUG_ENDPOINTS:
        @app.route("/test-encryption", methods=["GET"])
        def test_encryption_route():
            """Debug: AES round-trip test (disable in production)."""
            session_key = EncryptionHelper.generate_aes_key()
            test_data = "GUJARATM31122012|REF123|01-01-2020|01-01-2022|Y"
            encrypted = EncryptionHelper.encrypt_data_with_aes(test_data, session_key)
            decrypted = EncryptionHelper.decrypt_response_data(encrypted, session_key)
            return jsonify({
                "encryption_test": "PASSED" if test_data == decrypted else "FAILED",
                "session_key_length": len(session_key),
                "iv_length": 16,
            })

    return app


app = create_app()


if __name__ == "__main__":
    # Development only. Production should use gunicorn (see Dockerfile).
    app.run(host="0.0.0.0", port=5000, debug=False)
