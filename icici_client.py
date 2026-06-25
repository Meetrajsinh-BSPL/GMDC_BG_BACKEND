from __future__ import annotations
"""Thin wrapper around the ICICI eBG API."""
import json
import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config
from crypto_utils import EncryptionHelper, decrypt_json_fields

logger = logging.getLogger(__name__)


def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[502, 503, 504],
        allowed_methods=frozenset(["POST"]),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


def query(plain_request: dict) -> dict:
    """Encrypt and POST a payload to ICICI. Returns a structured dict that the
    caller can turn into a Flask JSON response.
    """
    config.require_icici()

    session_key = EncryptionHelper.generate_aes_key()
    encrypted_request = {
        k: EncryptionHelper.encrypt_data_with_aes(v, session_key)
        for k, v in plain_request.items()
    }
    encrypted_session_key = EncryptionHelper.encrypt_session_key(
        session_key, config.ICICI_CERT_PEM
    )

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "apikey": config.ICICI_API_KEY,
        "X-Session-Key": encrypted_session_key,
    }
    url = config.ICICI_BASE_URL + config.ICICI_ENDPOINT

    try:
        resp = _session().post(
            url, headers=headers, json=encrypted_request,
            verify=True, timeout=config.ICICI_TIMEOUT_S,
        )
    except requests.RequestException as e:
        return {
            "ok": False, "status_code": None, "error": f"Request failed: {e}",
            "plain_request": plain_request, "encrypted_request": encrypted_request,
        }

    corr_id = resp.headers.get("x-correlation-id")

    raw_json = None
    try:
        raw_json = resp.json()
    except json.JSONDecodeError:
        pass

    decrypted = None
    if raw_json is not None:
        decrypted = decrypt_json_fields(raw_json, session_key)

    return {
        "ok": resp.status_code == 200,
        "status_code": resp.status_code,
        "correlation_id": corr_id,
        "headers": dict(resp.headers),
        "raw_response": raw_json,
        "raw_text": resp.text if raw_json is None else None,
        "decrypted": decrypted,
        "plain_request": plain_request,
        "encrypted_request": encrypted_request,
        "session_key_length": len(session_key),
        "encrypted_session_key_length": len(encrypted_session_key),
    }
