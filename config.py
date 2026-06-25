from __future__ import annotations
"""Centralised configuration. All secrets and deployment-specific values come from env."""
import os
from pathlib import Path


def _require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(f"Required environment variable {name!r} is not set")
    return val


def _read_cert_pem() -> str:
    """Load the ICICI public certificate.

    Priority:
      1. ICICI_CERT_PEM_PATH (path to a PEM file)
      2. ICICI_CERT_PEM (inline PEM blob)
    """
    path = os.environ.get("ICICI_CERT_PEM_PATH", "").strip()
    if path:
        p = Path(path)
        if not p.is_file():
            raise RuntimeError(f"ICICI_CERT_PEM_PATH points to non-existent file: {path}")
        return p.read_text(encoding="utf-8")
    inline = os.environ.get("ICICI_CERT_PEM", "").strip()
    if inline:
        return inline
    raise RuntimeError(
        "ICICI certificate missing: set ICICI_CERT_PEM_PATH or ICICI_CERT_PEM"
    )


# ----- OCI / Cohere -----
OCI_CONFIG_FILE = os.environ.get("OCI_CONFIG_FILE", "~/.oci/config")
OCI_CONFIG_PROFILE = os.environ.get("OCI_CONFIG_PROFILE", "DEFAULT")
OCI_COMPARTMENT_ID = os.environ.get("OCI_COMPARTMENT_ID", "").strip()
OCI_GENAI_ENDPOINT = os.environ.get(
    "OCI_GENAI_ENDPOINT",
    "https://inference.generativeai.ap-hyderabad-1.oci.oraclecloud.com",
).strip()
OCI_MODEL_ID = os.environ.get("OCI_MODEL_ID", "").strip()
OCI_VISION_MODEL_ID = os.environ.get("OCI_VISION_MODEL_ID", "cohere.command-a-vision").strip()
VISION_MAX_PAGES = int(os.environ.get("VISION_MAX_PAGES", "6"))
VISION_PAGE_ZOOM = float(os.environ.get("VISION_PAGE_ZOOM", "2.0"))

# ----- ICICI -----
ICICI_API_KEY = os.environ.get("ICICI_API_KEY", "").strip()
ICICI_BASE_URL = os.environ.get("ICICI_BASE_URL", "https://igateway.icicibank.com").strip()
ICICI_ENDPOINT = os.environ.get(
    "ICICI_ENDPOINT", "/apibanking/live/corpapi/v2/eBG/fetchbg-issuance-amend"
).strip()
ICICI_CORP_ID = os.environ.get("ICICI_CORP_ID", "").strip()
ICICI_TIMEOUT_S = int(os.environ.get("ICICI_TIMEOUT_S", "30"))

try:
    ICICI_CERT_PEM = _read_cert_pem()
except RuntimeError:
    # Allow startup without ICICI cert for local extraction-only testing; endpoints that
    # need it will fail fast at call time.
    ICICI_CERT_PEM = ""

# ----- Flask -----
MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", str(32 * 1024 * 1024)))

_raw_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "*").strip()
if _raw_origins == "*" or not _raw_origins:
    CORS_ALLOWED_ORIGINS = "*"
else:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

API_KEY = os.environ.get("API_KEY", "").strip()  # optional shared-secret gate
ENV = os.environ.get("FLASK_ENV", "production").lower()
DEBUG_ENDPOINTS = os.environ.get("ENABLE_DEBUG_ENDPOINTS", "").lower() in {"1", "true", "yes"}

# ----- Extraction tuning -----
COHERE_MAX_INPUT_CHARS = int(os.environ.get("COHERE_MAX_INPUT_CHARS", "12000"))


def require_oci() -> None:
    if not OCI_COMPARTMENT_ID:
        raise RuntimeError("OCI_COMPARTMENT_ID is not set")
    if not OCI_MODEL_ID:
        raise RuntimeError("OCI_MODEL_ID is not set")


def require_icici() -> None:
    if not ICICI_API_KEY:
        raise RuntimeError("ICICI_API_KEY is not set")
    if not ICICI_CERT_PEM:
        raise RuntimeError("ICICI certificate not configured (ICICI_CERT_PEM[_PATH])")
    if not ICICI_CORP_ID:
        raise RuntimeError("ICICI_CORP_ID is not set")
