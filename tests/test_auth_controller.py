from unittest.mock import patch, MagicMock
import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from controllers.auth import (
    signup_user,
    login_user,
    logout_user,
    refresh_access_token,
    get_me,
    _resolve_provider,
    _user_dict,
    save_settings,
    list_models,
)
from schemas.auth import SignupRequest, LoginRequest
from models.user import User
from services.password import hash_password

def _make_user(**kwargs):
    defaults = dict(
        id=1,
        email="test@example.com",
        name="Test",
        is_active=True,
        hashed_password=hash_password("password123"),
    )
    defaults.update(kwargs)
    return User(**defaults)

class TestUserDict:
    def test_returns_correct_fields(self):
        user = _make_user()
        d = _user_dict(user)
        assert d["id"] == 1
        assert d["email"] == "test@example.com"
        assert d["name"] == "Test"
        assert d["is_active"] is True

    def test_no_password_in_dict(self):
        user = _make_user()
        d = _user_dict(user)
        assert "hashed_password" not in d
        assert "password" not in d

class TestSignupUser:
    def test_raises_409_on_duplicate_email(self):
        with patch("controllers.auth.get_user_by_email", return_value=_make_user()):
            with pytest.raises(HTTPException) as exc:
                signup_user(
                    SignupRequest(
                        email="test@example.com", name="Test User", password="password123"
                    )
                )
            assert exc.value.status_code == 409

    def test_success_returns_user_dict(self):
        new_user = _make_user()
        with (
            patch("controllers.auth.get_user_by_email", return_value=None),
            patch("controllers.auth.create_user", return_value=new_user),
        ):
            result = signup_user(
                SignupRequest(email="new@example.com", name="New User", password="password123")
            )
        assert result["status"] == "success"
        assert result["user"]["email"] == "test@example.com"

class TestLoginUser:
    def test_raises_401_on_unknown_email(self):
        response = MagicMock()
        with patch("controllers.auth.get_user_by_email", return_value=None):
            with pytest.raises(HTTPException) as exc:
                login_user(LoginRequest(email="nobody@example.com", password="pass"), response)
            assert exc.value.status_code == 401

    def test_raises_401_on_wrong_password(self):
        user = _make_user()
        response = MagicMock()
        with patch("controllers.auth.get_user_by_email", return_value=user):
            with pytest.raises(HTTPException) as exc:
                login_user(LoginRequest(email="test@example.com", password="wrong"), response)
            assert exc.value.status_code == 401

    def test_success_sets_cookies_and_returns_user(self):
        user = _make_user()
        response = MagicMock()
        with patch("controllers.auth.get_user_by_email", return_value=user):
            result = login_user(
                LoginRequest(email="test@example.com", password="password123"), response
            )
        assert "user" in result
        response.set_cookie.assert_called()

class TestLogoutUser:
    def test_clears_cookies(self):
        response = MagicMock()
        result = logout_user(response)
        assert result["status"] == "success"
        assert response.delete_cookie.call_count == 2

class TestRefreshToken:
    def test_raises_401_with_no_token(self):
        response = MagicMock()
        with pytest.raises(HTTPException) as exc:
            refresh_access_token(None, response)
        assert exc.value.status_code == 401

    def test_raises_401_with_invalid_token(self):
        response = MagicMock()
        with pytest.raises(HTTPException) as exc:
            refresh_access_token("not-a-real-token", response)
        assert exc.value.status_code == 401

    def test_success_sets_new_access_cookie(self):
        from services.jwt import create_refresh_token

        user = _make_user()
        token = create_refresh_token(user.id)
        response = MagicMock()
        with patch("controllers.auth.get_user_by_id", return_value=user):
            result = refresh_access_token(token, response)
        assert result["status"] == "refreshed"
        response.set_cookie.assert_called()

class TestGetMe:
    def test_returns_user_dict(self):
        user = _make_user()
        result = get_me(user)
        assert result["email"] == "test@example.com"

class TestResolveProvider:
    def test_returns_none_for_empty_name(self):
        assert _resolve_provider(None) is None

    def test_raises_400_for_unsupported_provider(self):
        with pytest.raises(HTTPException) as exc:
            _resolve_provider("fakeprovider")
        assert exc.value.status_code == 400

    def test_raises_400_when_not_in_db(self):
        with patch("controllers.auth.get_provider_by_name", return_value=None):
            with pytest.raises(HTTPException) as exc:
                _resolve_provider("gemini")
            assert exc.value.status_code == 400

    def test_returns_provider_when_found(self):
        mock_provider = MagicMock()
        mock_provider.name = "gemini"
        with patch("controllers.auth.get_provider_by_name", return_value=mock_provider):
            result = _resolve_provider("gemini")
        assert result is mock_provider

class TestListModels:
    def test_returns_fallback_when_no_api_key(self):
        user = _make_user()
        mock_provider = MagicMock()
        mock_provider.id = 1
        mock_provider.name = "gemini"
        with (
            patch("controllers.auth.get_provider_by_name", return_value=mock_provider),
            patch("controllers.auth.get_provider_key", return_value=None),
        ):
            result = list_models(user, "gemini")
        assert result["source"] == "fallback"
        assert len(result["models"]) > 0
