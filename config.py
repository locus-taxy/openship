import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Add it to your .env file.")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_URL = os.getenv("GEMINI_API_URL")

LINKIFYI_TOKEN = os.getenv("LINKIFYI_TOKEN")
LEXI_PASSWORD = os.getenv("LEXI_PASSWORD")
