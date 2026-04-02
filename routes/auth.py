from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Response

from models.user import User
from schemas.auth import SignupRequest, LoginRequest
from dependencies.auth import get_current_user
from controllers import auth as auth_controller

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/signup", status_code=201)
def signup(payload: SignupRequest):
    return auth_controller.signup_user(payload)

@router.post("/login")
def login(payload: LoginRequest, response: Response):
    return auth_controller.login_user(payload, response)

@router.post("/refresh")
def refresh(refresh_token: Optional[str] = Cookie(default=None)):
    return auth_controller.refresh_access_token(refresh_token)

@router.post("/logout")
def logout(response: Response):
    return auth_controller.logout_user(response)

@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return auth_controller.get_me(current_user)
