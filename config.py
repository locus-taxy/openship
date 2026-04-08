import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

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

def is_smtp_outbound_configured() -> bool:
    """True when SMTP_HOST is set to a non-empty value (outbound email wired)."""
    host = os.getenv("SMTP_HOST")
    return bool(host and host.strip())

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Add it to your .env file.")

def _strip_opt(name: str) -> Optional[str]:
    v = os.getenv(name)
    if v is None:
        return None
    s = v.strip()
    return s if s else None

GEMINI_API_KEY = _strip_opt("GEMINI_API_KEY")
GEMINI_API_URL = _strip_opt("GEMINI_API_URL")

RUN_MIGRATIONS_ON_STARTUP = _env_bool("RUN_MIGRATIONS_ON_STARTUP", True)

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
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "2"))
JWT_REFRESH_TOKEN_EXPIRE_HOURS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_HOURS", "7"))

LINKIFYI_TOKEN = os.getenv("LINKIFYI_TOKEN")
LEXI_PASSWORD = os.getenv("LEXI_PASSWORD")
