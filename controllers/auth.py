from typing import Optional
from fastapi import HTTPException, Response
from config import JWT_ACCESS_TOKEN_EXPIRE_MINUTES, JWT_REFRESH_TOKEN_EXPIRE_HOURS
from models.user import User
from schemas.auth import SignupRequest, LoginRequest
from services.llm import (
    PROVIDER_LABELS,
    PROVIDER_MODELS,
    SUPPORTED_PROVIDERS,
    DEFAULT_MODELS,
    fetch_provider_models,
    verify_model,
)
from services.user import (
    get_user_by_id,
    get_user_by_email,
    create_user,
    update_llm_settings,
    get_provider_key,
    get_provider_model,
    get_provider_by_name,
    get_provider_by_id,
    get_all_saved_provider_ids,
)
from services.password import verify_password
from services.jwt import create_access_token, create_refresh_token, decode_token

REFRESH_COOKIE = "refresh_token"
ACCESS_COOKIE = "access_token"
COOKIE_PATH = "/"

def _resolve_provider(name: Optional[str]):
    """Given a provider name string, return the LlmProvider row or raise 400."""
    if not name:
        return None
    if name not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider '{name}'. Choose from: {', '.join(sorted(SUPPORTED_PROVIDERS))}.",
        )
    provider = get_provider_by_name(name)
    if not provider:
        raise HTTPException(status_code=400, detail=f"Provider '{name}' not found in database.")
    return provider

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
    # Resolve active provider name from ID
    active_provider = (
        get_provider_by_id(current_user.llm_provider_id) if current_user.llm_provider_id else None
    )
    active_name = active_provider.name if active_provider else None

    saved_ids = get_all_saved_provider_ids(current_user.id)
    active_model = (
        get_provider_model(current_user.id, current_user.llm_provider_id)
        if current_user.llm_provider_id
        else None
    )

    # Fetch all provider rows once — reused for both provider_keys and supported_providers
    all_provider_rows = {p: get_provider_by_name(p) for p in sorted(SUPPORTED_PROVIDERS)}
    supported_providers = [
        {"id": row.id if row else None, "value": p, "label": PROVIDER_LABELS[p]}
        for p, row in all_provider_rows.items()
    ]
    # Reuse rows for provider_keys too
    provider_keys = {
        p: (row.id in saved_ids if row else False) for p, row in all_provider_rows.items()
    }

    return {
        "llm_provider": active_name,
        "llm_model": active_model or DEFAULT_MODELS.get(active_name or ""),
        "provider_keys": provider_keys,
        "supported_providers": supported_providers,
        "provider_models": PROVIDER_MODELS,
    }

def save_settings(
    current_user: User,
    provider: Optional[str],
    api_key: Optional[str],
    model: Optional[str],
):
    p = provider.strip() if provider else None
    k = api_key.strip() if api_key is not None else None
    m = model.strip() if model else None

    provider_row = _resolve_provider(p)
    provider_id = provider_row.id if provider_row else None

    update_llm_settings(current_user.id, provider_id, k, m)

    has_key = bool(get_provider_key(current_user.id, provider_id) if provider_id else None)
    return {
        "status": "success",
        "llm_provider": p,
        "llm_model": m or DEFAULT_MODELS.get(p or ""),
        "has_key": has_key,
    }

def list_models(current_user: User, provider: str):
    """Return available models for the given provider using the user's stored key."""
    provider_row = _resolve_provider(provider)
    if not provider_row:
        raise HTTPException(status_code=400, detail="Invalid or missing provider.")
    api_key = get_provider_key(current_user.id, provider_row.id)
    if not api_key:
        return {
            "provider": provider,
            "models": PROVIDER_MODELS.get(provider, []),
            "source": "fallback",
        }
    models = fetch_provider_models(provider, api_key)
    return {"provider": provider, "models": models, "source": "live"}

def verify_custom_model(current_user: User, provider: str, model: str):
    provider_row = _resolve_provider(provider)
    if not provider_row:
        raise HTTPException(status_code=400, detail="Invalid or missing provider.")
    api_key = get_provider_key(current_user.id, provider_row.id)
    if not api_key:
        raise HTTPException(
            status_code=400, detail="No API key saved for this provider. Add a key first."
        )
    return verify_model(provider, api_key, model.strip())
