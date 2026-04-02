from typing import Optional

from fastapi import HTTPException, Response

from config import JWT_REFRESH_TOKEN_EXPIRE_DAYS
from models.user import User
from schemas.auth import SignupRequest, LoginRequest, LoginResponse
from services.user import get_user_by_email, create_user
from services.password import verify_password
from services.jwt import create_access_token, create_refresh_token, decode_token

COOKIE_KEY = "refresh_token"

def _user_dict(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "is_active": user.is_active}

def _set_refresh_cookie(response: Response, token: str):
    response.set_cookie(
        key=COOKIE_KEY,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",
        secure=False,  # set True in production with HTTPS
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

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    _set_refresh_cookie(response, refresh_token)
    return LoginResponse(user=_user_dict(user), access_token=access_token)

def refresh_access_token(refresh_token: Optional[str]):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")

    token_payload = decode_token(refresh_token)
    if token_payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = int(token_payload.get("sub"))
    access_token = create_access_token(user_id)
    return {"access_token": access_token, "token_type": "bearer"}

def logout_user(response: Response):
    response.delete_cookie(key=COOKIE_KEY, path="/")
    return {"status": "success", "message": "Logged out"}

def get_me(current_user: User):
    return _user_dict(current_user)
