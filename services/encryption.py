"""
Full encryption for API keys using Fernet (AES-128-CBC).

The entire API key is encrypted and stored as a Fernet token prefixed with "FULL:".
The LLM_ENCRYPTION_KEY environment variable is required and never touches the database.

Backward compatibility:
- "FULL:<token>"        — fully encrypted (current format)
- "prefix||ENC||<token>" — legacy partial encryption (decrypted correctly, re-saved as full on next write)
- no separator          — legacy plaintext (returned as-is)
"""

import os
from typing import Optional
from cryptography.fernet import Fernet

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
    """Encrypt the full API key with Fernet. Stored as 'FULL:<fernet_token>'."""
    f = _get_fernet()
    return _FULL_PREFIX + f.encrypt(raw.encode()).decode()

def decrypt_api_key(stored: str) -> str:
    """
    Decrypt a stored API key. Handles all storage formats:
    - FULL:<token>          current full-encryption format
    - prefix||ENC||<token>  legacy partial encryption
    - plaintext             legacy unencrypted
    """
    f = _get_fernet()
    if stored.startswith(_FULL_PREFIX):
        return f.decrypt(stored[len(_FULL_PREFIX) :].encode()).decode()
    if _SEPARATOR in stored:
        # Legacy partial encryption — decrypt the suffix and reconstruct
        prefix, enc_suffix = stored.rsplit(_SEPARATOR, 1)
        suffix = f.decrypt(enc_suffix.encode()).decode()
        return prefix + suffix
    # Legacy plaintext — return as-is
    return stored
