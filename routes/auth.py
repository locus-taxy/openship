from typing import Optional
from fastapi import APIRouter, Cookie, Request, Response
from schemas.auth import SignupRequest, LoginRequest, SaveSettingsRequest
from controllers import auth as auth_controller

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/signup", status_code=201)
def signup(payload: SignupRequest):
    return auth_controller.signup_user(payload)

@router.post("/login")
def login(payload: LoginRequest, response: Response):
    return auth_controller.login_user(payload, response)

@router.post("/refresh")
def refresh(response: Response, refresh_token: Optional[str] = Cookie(default=None)):
    return auth_controller.refresh_access_token(refresh_token, response)

@router.post("/logout")
def logout(response: Response):
    return auth_controller.logout_user(response)

@router.get("/me")
def me(request: Request):
    return auth_controller.get_me(request.state.user)

@router.get("/me/settings")
def get_settings(request: Request):
    return auth_controller.get_settings(request.state.user)

@router.put("/me/settings")
def save_settings(payload: SaveSettingsRequest, request: Request):
    return auth_controller.save_settings(request.state.user, payload.gemini_api_key)
