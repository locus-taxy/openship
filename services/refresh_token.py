import jwt
import requests
from datetime import datetime, timezone
from dotenv import set_key
from config import LINKIFYI_TOKEN, LEXI_PASSWORD

ENV_PATH = "../.env"
TOKEN_KEY = "LINKIFYI_TOKEN"
TOKEN_REFRESH_URL = "https://app.linkifyi.com/auth/login"
API_REFRESH_PAYLOAD = {
    "username": "lexi",
    "password": LEXI_PASSWORD,
}

def is_jwt_expired(token: str) -> bool:
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        exp_timestamp = decoded.get("exp")
        if not exp_timestamp:
            return True

        exp_time = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
        return exp_time < datetime.now(timezone.utc)

    except jwt.DecodeError:
        print("Invalid JWT token format.")
        return True

def get_new_jwt_token() -> str:
    try:
        response = requests.post(TOKEN_REFRESH_URL, json=API_REFRESH_PAYLOAD)
        response.raise_for_status()
        data = response.json()

        return data.get("message")
    except requests.exceptions.RequestException as e:
        print(f"Token refresh failed: {e}")
        return None

def update_env_token(new_token: str):
    """Update the .env file with the new token."""
    set_key(ENV_PATH, TOKEN_KEY, new_token)
    print("✅ JWT token updated in .env file.")

def verify_token():
    token = LINKIFYI_TOKEN

    if not token:
        print("⚠️ No token found in .env file. Fetching new one...")
        new_token = get_new_jwt_token()
        update_env_token(new_token)
        return

    if is_jwt_expired(token):
        print("🔄 JWT expired. Refreshing...")
        new_token = get_new_jwt_token()
        update_env_token(new_token)
    else:
        print("✅ JWT token is valid.")
