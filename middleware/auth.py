"""
Global auth middleware.

Every request is authenticated by default. To make a route public, add it to
PUBLIC_EXACT (exact method + path match) or PUBLIC_PREFIXES (path prefix match).
"""

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from services.jwt import decode_token
from services.user import get_user_by_id

# Exact (METHOD, path) pairs that bypass auth.
PUBLIC_EXACT: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/auth/signup"),
        ("POST", "/auth/login"),
        ("POST", "/auth/refresh"),
        ("POST", "/auth/logout"),
        ("GET", "/docs"),
        ("GET", "/openapi.json"),
        ("GET", "/redoc"),
    }
)

# Path prefixes that bypass auth regardless of method.
PUBLIC_PREFIXES: tuple[str, ...] = ("/public/",)

def _is_public(method: str, path: str) -> bool:
    if (method.upper(), path) in PUBLIC_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Always pass OPTIONS through — handled by CORSMiddleware.
        if request.method == "OPTIONS":
            return await call_next(request)

        if _is_public(request.method, request.url.path):
            return await call_next(request)

        token = request.cookies.get("access_token")
        if not token:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

        try:
            payload = decode_token(token)
        except HTTPException as e:
            return JSONResponse(status_code=401, content={"detail": e.detail})

        if payload.get("type") != "access":
            return JSONResponse(status_code=401, content={"detail": "Invalid token type"})

        user_id = payload.get("sub")
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return JSONResponse(status_code=401, content={"detail": "Invalid token payload"})

        user = await run_in_threadpool(get_user_by_id, user_id)
        if user is None or not user.is_active:
            return JSONResponse(status_code=401, content={"detail": "User not found or inactive"})

        request.state.user = user
        return await call_next(request)
