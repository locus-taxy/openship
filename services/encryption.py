"""
Partial encryption for API keys using Fernet (AES-128-CBC).

Only the last 5 characters of the key are encrypted. The rest is stored as
plaintext. The stored value looks like:

    sk-abc123def456||ENC||<fernet_token_of_last_5_chars>

This means a database leak alone is not enough to reconstruct the key —
an attacker also needs LLM_ENCRYPTION_KEY from the server environment.

The LLM_ENCRYPTION_KEY environment variable is required and never touches
the database.

Backward compatibility:
- "prefix||ENC||<token>" — partial encryption (current format)
- "FULL:<token>"         — old full encryption (decrypted correctly, re-saved as partial on next write)
- no separator           — legacy plaintext (returned as-is)
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
    """
    Encrypt the last 5 characters of the API key with Fernet.
    Stored as 'prefix||ENC||<fernet_token>'.
    Keys shorter than 5 characters are encrypted in full (no plaintext prefix).
    """
    f = _get_fernet()
    if len(raw) <= 5:
        prefix, suffix = "", raw
    else:
        prefix, suffix = raw[:-5], raw[-5:]
    return prefix + _SEPARATOR + f.encrypt(suffix.encode()).decode()

def decrypt_api_key(stored: str) -> str:
    """
    Decrypt a stored API key. Handles all storage formats:
    - prefix||ENC||<token>  current partial-encryption format
    - FULL:<token>          old full-encryption format (backward compat)
    - plaintext             legacy unencrypted (returned as-is)
    """
    f = _get_fernet()
    if _SEPARATOR in stored:
        prefix, enc_suffix = stored.rsplit(_SEPARATOR, 1)
        suffix = f.decrypt(enc_suffix.encode()).decode()
        return prefix + suffix
    if stored.startswith(_FULL_PREFIX):
        # Old full-encryption format — decrypt the whole key
        return f.decrypt(stored[len(_FULL_PREFIX) :].encode()).decode()
    # Legacy plaintext — return as-is
    return stored
