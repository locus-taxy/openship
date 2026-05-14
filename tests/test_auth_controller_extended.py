from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from fastapi.responses import Response
from controllers.auth import refresh_access_token, list_models, verify_custom_model
from models.user import User

def _make_user(user_id=1, active=True):
    return User(
        id=user_id,
        email="test@example.com",
        name="Test",
        is_active=active,
        hashed_password="$2b$hash",
        llm_provider_id=1,
    )

class TestRefreshAccessTokenEdgeCases:
    def test_raises_401_when_token_type_is_not_refresh(self):
        response = MagicMock(spec=Response)
        with patch("controllers.auth.decode_token", return_value={"type": "access", "sub": "1"}):
            with pytest.raises(HTTPException) as exc:
                refresh_access_token("valid-token", response)
            assert exc.value.status_code == 401

    def test_raises_401_when_sub_is_missing(self):
        response = MagicMock(spec=Response)
        with patch("controllers.auth.decode_token", return_value={"type": "refresh"}):
            with pytest.raises(HTTPException) as exc:
                refresh_access_token("valid-token", response)
            assert exc.value.status_code == 401

    def test_raises_401_when_user_not_found(self):
        response = MagicMock(spec=Response)
        with (
            patch("controllers.auth.decode_token", return_value={"type": "refresh", "sub": "1"}),
            patch("controllers.auth.get_user_by_id", return_value=None),
        ):
            with pytest.raises(HTTPException) as exc:
                refresh_access_token("valid-token", response)
            assert exc.value.status_code == 401

    def test_raises_401_when_user_inactive(self):
        response = MagicMock(spec=Response)
        inactive_user = _make_user(active=False)
        with (
            patch("controllers.auth.decode_token", return_value={"type": "refresh", "sub": "1"}),
            patch("controllers.auth.get_user_by_id", return_value=inactive_user),
        ):
            with pytest.raises(HTTPException) as exc:
                refresh_access_token("valid-token", response)
            assert exc.value.status_code == 401

class TestListModels:
    def test_raises_400_when_provider_invalid(self):
        user = _make_user()
        with patch("controllers.auth._resolve_provider", return_value=None):
            with pytest.raises(HTTPException) as exc:
                list_models(user, "unknown-provider")
            assert exc.value.status_code == 400

    def test_returns_fallback_when_no_api_key(self):
        user = _make_user()
        provider_row = MagicMock()
        provider_row.id = 1
        with (
            patch("controllers.auth._resolve_provider", return_value=provider_row),
            patch("controllers.auth.get_provider_key", return_value=None),
        ):
            result = list_models(user, "gemini")
        assert result["source"] == "fallback"
        assert "models" in result

    def test_returns_live_models_when_api_key_exists(self):
        user = _make_user()
        provider_row = MagicMock()
        provider_row.id = 1
        with (
            patch("controllers.auth._resolve_provider", return_value=provider_row),
            patch("controllers.auth.get_provider_key", return_value="my-api-key"),
            patch("controllers.auth.fetch_provider_models", return_value=["gemini-flash"]),
        ):
            result = list_models(user, "gemini")
        assert result["source"] == "live"
        assert "gemini-flash" in result["models"]

class TestVerifyCustomModel:
    def test_raises_400_when_provider_invalid(self):
        user = _make_user()
        with patch("controllers.auth._resolve_provider", return_value=None):
            with pytest.raises(HTTPException) as exc:
                verify_custom_model(user, "unknown", "model-name")
            assert exc.value.status_code == 400

    def test_raises_400_when_no_api_key(self):
        user = _make_user()
        provider_row = MagicMock()
        provider_row.id = 1
        with (
            patch("controllers.auth._resolve_provider", return_value=provider_row),
            patch("controllers.auth.get_provider_key", return_value=None),
        ):
            with pytest.raises(HTTPException) as exc:
                verify_custom_model(user, "gemini", "gemini-flash")
            assert exc.value.status_code == 400

    def test_calls_verify_model_with_correct_args(self):
        user = _make_user()
        provider_row = MagicMock()
        provider_row.id = 1
        with (
            patch("controllers.auth._resolve_provider", return_value=provider_row),
            patch("controllers.auth.get_provider_key", return_value="key"),
            patch("controllers.auth.verify_model", return_value={"ok": True}) as mock_verify,
        ):
            result = verify_custom_model(user, "gemini", "  gemini-flash  ")
        mock_verify.assert_called_once_with("gemini", "key", "gemini-flash")
        assert result == {"ok": True}
