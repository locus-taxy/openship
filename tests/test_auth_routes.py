from unittest.mock import patch, MagicMock
import pytest
from models.user import User
from services.password import hash_password

def _make_user(**kwargs):
    defaults = dict(
        id=1,
        email="test@example.com",
        name="Test User",
        is_active=True,
        hashed_password=hash_password("password123"),
        llm_provider_id=None,
    )
    defaults.update(kwargs)
    return User(**defaults)

class TestSignup:
    def test_signup_success(self, anon_client):
        with (
            patch("controllers.auth.get_user_by_email", return_value=None),
            patch("controllers.auth.create_user", return_value=_make_user()),
        ):
            response = anon_client.post(
                "/auth/signup",
                json={
                    "email": "new@example.com",
                    "name": "New User",
                    "password": "password123",
                },
            )
        assert response.status_code == 201
        assert response.json()["status"] == "success"

    def test_signup_duplicate_email_returns_409(self, anon_client):
        with patch("controllers.auth.get_user_by_email", return_value=_make_user()):
            response = anon_client.post(
                "/auth/signup",
                json={
                    "email": "test@example.com",
                    "name": "Test",
                    "password": "password123",
                },
            )
        assert response.status_code == 409

class TestLogin:
    def test_login_success_sets_cookies(self, anon_client):
        user = _make_user()
        with patch("controllers.auth.get_user_by_email", return_value=user):
            response = anon_client.post(
                "/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "password123",
                },
            )
        assert response.status_code == 200
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies

    def test_login_wrong_password_returns_401(self, anon_client):
        user = _make_user()
        with patch("controllers.auth.get_user_by_email", return_value=user):
            response = anon_client.post(
                "/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "wrongpassword",
                },
            )
        assert response.status_code == 401

    def test_login_unknown_email_returns_401(self, anon_client):
        with patch("controllers.auth.get_user_by_email", return_value=None):
            response = anon_client.post(
                "/auth/login",
                json={
                    "email": "nobody@example.com",
                    "password": "password123",
                },
            )
        assert response.status_code == 401

class TestLogout:
    def test_logout_clears_cookies(self, anon_client):
        response = anon_client.post("/auth/logout")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

class TestGetMe:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.get("/auth/me")
        assert response.status_code == 401

    def test_authenticated_returns_user_info(self, auth_client, test_user):
        response = auth_client.get("/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["id"] == test_user.id

class TestGetSettings:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.get("/auth/me/settings")
        assert response.status_code == 401

    def test_authenticated_returns_settings(self, auth_client, test_user):
        with (
            patch("controllers.auth.get_all_saved_provider_ids", return_value=set()),
            patch("controllers.auth.get_provider_by_id", return_value=None),
            patch("controllers.auth.get_provider_model", return_value=None),
            patch("controllers.auth.get_provider_by_name", return_value=None),
            patch("controllers.auth.get_currency_settings", return_value=("USD", 1.0)),
        ):
            response = auth_client.get("/auth/me/settings")
        assert response.status_code == 200
        data = response.json()
        assert "supported_providers" in data
        assert "provider_models" in data

class TestSaveSettings:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.put(
            "/auth/me/settings",
            json={
                "llm_provider": "gemini",
                "api_key": "test-key",
            },
        )
        assert response.status_code == 401

    def test_unsupported_provider_returns_400(self, auth_client, test_user):
        response = auth_client.put(
            "/auth/me/settings",
            json={
                "llm_provider": "unknown-provider",
                "api_key": "some-key",
            },
        )
        assert response.status_code == 400

    def test_valid_provider_returns_200(self, auth_client, test_user):
        mock_provider = MagicMock()
        mock_provider.id = 1
        mock_provider.name = "gemini"
        with (
            patch("controllers.auth.get_provider_by_name", return_value=mock_provider),
            patch("controllers.auth.update_llm_settings"),
            patch("controllers.auth.get_provider_key", return_value="test-key"),
        ):
            response = auth_client.put(
                "/auth/me/settings",
                json={
                    "llm_provider": "gemini",
                    "api_key": "test-api-key",
                },
            )
        assert response.status_code == 200

class TestRefreshToken:
    def test_no_refresh_token_returns_401(self, anon_client):
        response = anon_client.post("/auth/refresh")
        assert response.status_code == 401

    def test_valid_refresh_token_returns_200(self, anon_client, test_user):
        from services.jwt import create_refresh_token

        refresh_tok = create_refresh_token(test_user.id)
        with patch("controllers.auth.get_user_by_id", return_value=test_user):
            anon_client.cookies.set("refresh_token", refresh_tok)
            response = anon_client.post("/auth/refresh")
        assert response.status_code == 200
