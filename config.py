import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load `.env` from the project root (this file's directory), not the process cwd.
# Otherwise `uvicorn` started from another folder won't see GEMINI_* / DATABASE_URL.
_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


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
