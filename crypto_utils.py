from __future__ import annotations
"""AES-CBC + RSA PKCS#1 v1.5 helpers used to talk to the ICICI API.

Padding choice (PKCS1v15) is dictated by the ICICI spec.
"""
import base64
import logging
import secrets

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.x509 import load_pem_x509_certificate

logger = logging.getLogger(__name__)


class EncryptionHelper:
    @staticmethod
    def generate_aes_key() -> bytes:
        return secrets.token_bytes(32)

    @staticmethod
    def generate_iv() -> bytes:
        return secrets.token_bytes(16)

    @staticmethod
    def encrypt_data_with_aes(data, key: bytes) -> str:
        """AES-256-CBC encrypt with a fresh random IV per call; IV is prepended to ciphertext."""
        if data is None:
            return data
        if not isinstance(data, str):
            data = str(data)
        iv = EncryptionHelper.generate_iv()
        data_bytes = data.encode("utf-8")
        padder = padding.PKCS7(128).padder()
        padded = padder.update(data_bytes) + padder.finalize()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(padded) + encryptor.finalize()
        return base64.b64encode(iv + encrypted).decode("utf-8")

    @staticmethod
    def encrypt_session_key(session_key: bytes, cert_pem: str) -> str:
        cert = load_pem_x509_certificate(cert_pem.encode("utf-8"), backend=default_backend())
        public_key = cert.public_key()
        encrypted_key = public_key.encrypt(session_key, asym_padding.PKCS1v15())
        return base64.b64encode(encrypted_key).decode("utf-8")

    @staticmethod
    def decrypt_response_data(encrypted_data: str, session_key: bytes) -> str:
        """Decrypt a single AES-CBC field. Returns plaintext, or raises on malformed input."""
        if not encrypted_data:
            return encrypted_data
        raw = base64.b64decode(encrypted_data)
        if len(raw) < 32 or (len(raw) - 16) % 16 != 0:
            # Not an ICICI-format blob; treat as plaintext passthrough.
            return encrypted_data
        iv, cipher_text = raw[:16], raw[16:]
        cipher = Cipher(algorithms.AES(session_key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded = decryptor.update(cipher_text) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plain = unpadder.update(padded) + unpadder.finalize()
        return plain.decode("utf-8")


def decrypt_json_fields(obj, session_key: bytes):
    """Recursively attempt to decrypt every string leaf. Fall back to original on failure."""
    if isinstance(obj, dict):
        return {k: decrypt_json_fields(v, session_key) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decrypt_json_fields(item, session_key) for item in obj]
    if isinstance(obj, str) and obj:
        try:
            return EncryptionHelper.decrypt_response_data(obj, session_key)
        except Exception as exc:
            logger.debug("Field not AES-decryptable, keeping as-is: %s", exc)
            return obj
    return obj
