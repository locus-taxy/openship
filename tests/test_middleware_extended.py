import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi import HTTPException

def _make_app_with_auth():
    from middleware.auth import AuthMiddleware

    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/protected")
    def protected():
        return {"status": "ok"}

    @app.options("/protected")
    def preflight():
        return {}

    return app

class TestAuthMiddlewareDispatch:
    def test_options_request_passes_through(self):
        app = _make_app_with_auth()
        client = TestClient(app, raise_server_exceptions=False)
        with patch("middleware.auth.get_user_by_id"):
            response = client.options("/protected")
        assert response.status_code != 401

    def test_invalid_token_returns_401(self):
        app = _make_app_with_auth()
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("access_token", "bad.jwt.token")
        response = client.get("/protected")
        assert response.status_code == 401

    def test_wrong_token_type_returns_401(self):
        from services.jwt import create_refresh_token

        app = _make_app_with_auth()
        client = TestClient(app, raise_server_exceptions=False)
        token = create_refresh_token(1)
        with patch("middleware.auth.get_user_by_id"):
            client.cookies.set("access_token", token)
            response = client.get("/protected")
        assert response.status_code == 401

    def test_user_not_found_returns_401(self):
        from services.jwt import create_access_token

        app = _make_app_with_auth()
        client = TestClient(app, raise_server_exceptions=False)
        token = create_access_token(9999)
        with patch("middleware.auth.get_user_by_id", return_value=None):
            client.cookies.set("access_token", token)
            response = client.get("/protected")
        assert response.status_code == 401

    def test_inactive_user_returns_401(self):
        from services.jwt import create_access_token
        from models.user import User

        app = _make_app_with_auth()
        client = TestClient(app, raise_server_exceptions=False)
        token = create_access_token(1)
        inactive = User(
            id=1,
            email="x@x.com",
            name="X",
            is_active=False,
            hashed_password="hash",
            llm_provider_id=None,
        )
        with patch("middleware.auth.get_user_by_id", return_value=inactive):
            client.cookies.set("access_token", token)
            response = client.get("/protected")
        assert response.status_code == 401
