from typing import Optional
from fastapi import HTTPException, Response
from config import JWT_ACCESS_TOKEN_EXPIRE_MINUTES, JWT_REFRESH_TOKEN_EXPIRE_HOURS
from models.user import User
from schemas.auth import SignupRequest, LoginRequest
from services.user import get_user_by_id, get_user_by_email, create_user, update_gemini_api_key
from services.password import verify_password
from services.jwt import create_access_token, create_refresh_token, decode_token

REFRESH_COOKIE = "refresh_token"
ACCESS_COOKIE = "access_token"
COOKIE_PATH = "/"

def _user_dict(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "is_active": user.is_active}

def _set_tokens(response: Response, user_id: int):
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=access_token,
        httponly=True,
        samesite="lax",
        max_age=JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path=COOKIE_PATH,
        secure=False,
    )
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        samesite="lax",
        max_age=JWT_REFRESH_TOKEN_EXPIRE_HOURS * 3600,
        path=COOKIE_PATH,
        secure=False,
    )

def _set_access_cookie(response: Response, token: str):
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path=COOKIE_PATH,
        secure=False,
    )

def signup_user(payload: SignupRequest):
    existing = get_user_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = create_user(email=payload.email, name=payload.name, password=payload.password)
    return {"status": "success", "message": "Account created", "user": _user_dict(user)}

def login_user(payload: LoginRequest, response: Response):
    user = get_user_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    _set_tokens(response, user.id)
    return {"user": _user_dict(user)}

def refresh_access_token(refresh_token: Optional[str], response: Response):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")
    token_payload = decode_token(refresh_token)
    if token_payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    sub = token_payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = get_user_by_id(int(sub))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    _set_access_cookie(response, create_access_token(user.id))
    return {"status": "refreshed"}

def logout_user(response: Response):
    response.delete_cookie(key=ACCESS_COOKIE, path=COOKIE_PATH)
    response.delete_cookie(key=REFRESH_COOKIE, path=COOKIE_PATH)
    return {"status": "success", "message": "Logged out"}

def get_me(current_user: User):
    return _user_dict(current_user)

def get_settings(current_user: User):
    has_key = bool(current_user.gemini_api_key and current_user.gemini_api_key.strip())
    return {"has_gemini_api_key": has_key}

def save_settings(current_user: User, gemini_api_key: Optional[str]):
    key = gemini_api_key.strip() if gemini_api_key else None
    update_gemini_api_key(current_user.id, key)
    return {"status": "success", "has_gemini_api_key": bool(key)}
