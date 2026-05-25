from typing import Optional
from fastapi import APIRouter, Cookie, Request, Response
from schemas.auth import SignupRequest, LoginRequest, SaveSettingsRequest, SaveCurrencyRequest
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
    return auth_controller.save_settings(
        request.state.user, payload.llm_provider, payload.api_key, payload.llm_model
    )

@router.get("/me/models")
def list_models(provider: str, request: Request):
    return auth_controller.list_models(request.state.user, provider)

@router.post("/me/models/verify")
def verify_model(provider: str, model: str, request: Request):
    return auth_controller.verify_custom_model(request.state.user, provider, model)

@router.get("/me/pricing")
def get_model_pricing(provider: str, model: str, request: Request):
    return auth_controller.get_model_pricing(provider, model, request.state.user)

@router.put("/me/pricing/manual")
def save_manual_pricing(
    provider: str, model: str, input_per_1m_usd: float, output_per_1m_usd: float, request: Request
):
    return auth_controller.save_manual_pricing(
        request.state.user, provider, model, input_per_1m_usd, output_per_1m_usd
    )

@router.post("/me/pricing/refresh")
def refresh_pricing(request: Request):
    return auth_controller.refresh_pricing_cache()

@router.patch("/me/settings/currency")
def save_currency(payload: SaveCurrencyRequest, request: Request):
    return auth_controller.save_currency(request.state.user, payload)
