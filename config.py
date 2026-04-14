import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address

# Load `.env` from the project root (this file's directory), not the process cwd.
# Otherwise `uvicorn` started from another folder won't see GEMINI_* / DATABASE_URL.
_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")

_TRUTHY_BOOL = frozenset({"1", "true", "yes", "on"})
_FALSEY_BOOL = frozenset({"0", "false", "no", "off"})

def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    token = raw.strip().lower()
    if token in _TRUTHY_BOOL:
        return True
    if token in _FALSEY_BOOL:
        return False
    raise ValueError(
        f"Invalid boolean for environment variable {name!r}: {raw!r} "
        f"(use one of: {sorted(_TRUTHY_BOOL | _FALSEY_BOOL)})"
    )

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Add it to your .env file.")

def _strip_opt(name: str) -> Optional[str]:
    v = os.getenv(name)
    if v is None:
        return None
    s = v.strip()
    return s if s else None

def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    token = raw.strip()
    if not token:
        return default
    try:
        return int(token)
    except ValueError as exc:
        raise ValueError(f"Invalid integer for environment variable {name!r}: {raw!r}") from exc

GEMINI_API_KEY = _strip_opt("GEMINI_API_KEY")
GEMINI_API_URL = _strip_opt("GEMINI_API_URL")

RUN_MIGRATIONS_ON_STARTUP = _env_bool("RUN_MIGRATIONS_ON_STARTUP", True)

SMTP_HOST = _strip_opt("SMTP_HOST")
SMTP_PORT = _env_int("SMTP_PORT", 587)
SMTP_USER = _strip_opt("SMTP_USER")
SMTP_PASSWORD = _strip_opt("SMTP_PASSWORD")
SMTP_FROM_EMAIL = _strip_opt("SMTP_FROM_EMAIL")
SMTP_FROM_NAME = _strip_opt("SMTP_FROM_NAME")
SMTP_USE_TLS = _env_bool("SMTP_USE_TLS", True)
SMTP_USE_SSL = _env_bool("SMTP_USE_SSL", False)
SMTP_TIMEOUT_SECONDS = _env_int("SMTP_TIMEOUT_SECONDS", 20)

def is_smtp_outbound_configured() -> bool:
    """True when SMTP_HOST is set to a non-empty value."""
    return bool(SMTP_HOST)

def smtp_not_ready_reason() -> Optional[str]:
    """Explain why SMTP cannot send, or None if minimum settings are ready."""
    if not SMTP_HOST:
        return "SMTP_HOST is not set"
    if not SMTP_FROM_EMAIL:
        return "SMTP_FROM_EMAIL is not set"
    if SMTP_PORT <= 0:
        return "SMTP_PORT must be a positive integer"
    if SMTP_USE_SSL and SMTP_USE_TLS:
        return "SMTP_USE_SSL and SMTP_USE_TLS cannot both be true"
    return None

def is_smtp_ready_to_send() -> bool:
    return smtp_not_ready_reason() is None

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
_MIN_SECRET_LEN = 32
if (
    not JWT_SECRET_KEY
    or JWT_SECRET_KEY == "change-me-in-production"
    or len(JWT_SECRET_KEY) < _MIN_SECRET_LEN
):
    raise RuntimeError(
        f"JWT_SECRET_KEY is missing, insecure, or too short (min {_MIN_SECRET_LEN} chars). "
        'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
    )
limiter = Limiter(key_func=get_remote_address)

JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "2"))
JWT_REFRESH_TOKEN_EXPIRE_HOURS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_HOURS", "7"))
