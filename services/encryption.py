"""
Partial encryption for API keys.

Strategy: store the first part of the key as plaintext, encrypt only the last
5 characters with Fernet (AES-128). The stored value looks like:

    sk-abc123def456||ENC||<fernet_token_of_last_5_chars>

An attacker who gets the database row sees most of the key but the last
characters are an encrypted Fernet token — the raw string cannot be used as
an API key. Decryption requires the LLM_ENCRYPTION_KEY from the server
environment, which never touches the database.

For very short keys (≤5 chars), the entire key is encrypted with a FULL: prefix.

Legacy plaintext values (stored before this encryption was introduced) are
returned as-is — the separator is not present so they pass through unchanged.
"""

import os
from typing import Optional
from cryptography.fernet import Fernet

_SUFFIX_LEN = 5
_SEPARATOR = "||ENC||"
_FULL_PREFIX = "FULL:"

_fernet: Optional[Fernet] = None

def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        raw = os.environ.get("LLM_ENCRYPTION_KEY", "").strip()
        if not raw:
            raise RuntimeError(
                "LLM_ENCRYPTION_KEY is not set. "
                'Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        _fernet = Fernet(raw.encode())
    return _fernet

def encrypt_api_key(raw: str) -> str:
    """Encrypt the last 5 characters of the key; store the rest as plaintext."""
    f = _get_fernet()
    if len(raw) <= _SUFFIX_LEN:
        return _FULL_PREFIX + f.encrypt(raw.encode()).decode()
    prefix = raw[:-_SUFFIX_LEN]
    encrypted_suffix = f.encrypt(raw[-_SUFFIX_LEN:].encode()).decode()
    return prefix + _SEPARATOR + encrypted_suffix

def decrypt_api_key(stored: str) -> str:
    """Decrypt a key stored by encrypt_api_key. Returns plaintext legacy keys unchanged."""
    f = _get_fernet()
    if stored.startswith(_FULL_PREFIX):
        return f.decrypt(stored[len(_FULL_PREFIX) :].encode()).decode()
    if _SEPARATOR not in stored:
        # Legacy plaintext key stored before encryption was introduced — return as-is
        return stored
    prefix, enc_suffix = stored.rsplit(_SEPARATOR, 1)
    suffix = f.decrypt(enc_suffix.encode()).decode()
    return prefix + suffix
