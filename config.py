import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Add it to your .env file.")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_URL = os.getenv("GEMINI_API_URL")

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
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

LINKIFYI_TOKEN = os.getenv("LINKIFYI_TOKEN")
LEXI_PASSWORD = os.getenv("LEXI_PASSWORD")
