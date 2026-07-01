import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address

# Load `.env` from the project root (this file's directory), not the process cwd.
# Otherwise `uvicorn` started from another folder won't see DATABASE_URL etc.
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

LLM_ENCRYPTION_KEY = _strip_opt("LLM_ENCRYPTION_KEY")

JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "2"))
JWT_REFRESH_TOKEN_EXPIRE_HOURS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_HOURS", "7"))

# ── Atlassian / Confluence OAuth (optional) ─────────────────────────────────
# Three-legged OAuth 2.0 for connecting a company's Confluence. All optional so
# the server runs without them; the connect flow returns 503 until configured.
ATLASSIAN_CLIENT_ID = _strip_opt("ATLASSIAN_CLIENT_ID")
ATLASSIAN_CLIENT_SECRET = _strip_opt("ATLASSIAN_CLIENT_SECRET")
ATLASSIAN_REDIRECT_URI = _strip_opt("ATLASSIAN_REDIRECT_URI")

# Read-only Confluence scopes plus offline_access (needed for a refresh token).
_DEFAULT_ATLASSIAN_SCOPES = (
    "offline_access "
    "read:confluence-space.summary "
    "read:confluence-content.summary "
    "read:confluence-content.all "
    "search:confluence"
)
ATLASSIAN_OAUTH_SCOPES = _strip_opt("ATLASSIAN_OAUTH_SCOPES") or _DEFAULT_ATLASSIAN_SCOPES

# Where to send the browser after a successful connect.
CONFLUENCE_POST_CONNECT_REDIRECT = (
    _strip_opt("CONFLUENCE_POST_CONNECT_REDIRECT") or "/onboarding?connected=1"
)

# Shared secret for authenticating incoming Confluence webhooks.
CONFLUENCE_WEBHOOK_SECRET = _strip_opt("CONFLUENCE_WEBHOOK_SECRET")

def is_confluence_oauth_configured() -> bool:
    """True when the Atlassian client id, secret, and redirect URI are all set."""
    return bool(ATLASSIAN_CLIENT_ID and ATLASSIAN_CLIENT_SECRET and ATLASSIAN_REDIRECT_URI)
