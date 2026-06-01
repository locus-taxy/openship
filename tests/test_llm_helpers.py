from unittest.mock import patch, MagicMock
from models.user import User
from services.llm import (
    get_user_provider_name,
    get_user_api_key,
    get_user_model,
    DEFAULT_MODELS,
    SUPPORTED_PROVIDERS,
    PROVIDER_MODELS,
    PROVIDER_LABELS,
)

def _make_user(provider_id=None):
    return User(
        id=1,
        email="test@example.com",
        name="Test",
        is_active=True,
        hashed_password="$2b$hash",
        llm_provider_id=provider_id,
    )

class TestGetUserProviderName:
    def test_returns_none_when_no_provider_set(self):
        user = _make_user(provider_id=None)
        assert get_user_provider_name(user) is None

    def test_returns_provider_name_when_set(self):
        user = _make_user(provider_id=1)
        mock_provider = MagicMock()
        mock_provider.name = "gemini"
        # lazy import inside function — patch at the source module
        with patch("services.user.get_provider_by_id", return_value=mock_provider):
            result = get_user_provider_name(user)
        assert result == "gemini"

    def test_returns_none_when_provider_not_in_db(self):
        user = _make_user(provider_id=99)
        with patch("services.user.get_provider_by_id", return_value=None):
            result = get_user_provider_name(user)
        assert result is None

class TestGetUserApiKey:
    def test_returns_none_when_no_provider(self):
        user = _make_user(provider_id=None)
        assert get_user_api_key(user) is None

    def test_returns_decrypted_key_when_provider_set(self):
        user = _make_user(provider_id=1)
        with patch("services.user.get_provider_key", return_value="decrypted-key"):
            result = get_user_api_key(user)
        assert result == "decrypted-key"

    def test_returns_none_when_no_key_saved(self):
        user = _make_user(provider_id=1)
        with patch("services.user.get_provider_key", return_value=None):
            result = get_user_api_key(user)
        assert result is None

class TestGetUserModel:
    def test_returns_none_when_no_provider(self):
        user = _make_user(provider_id=None)
        assert get_user_model(user) is None

    def test_returns_saved_model_when_set(self):
        user = _make_user(provider_id=1)
        mock_provider = MagicMock()
        mock_provider.name = "gemini"
        with (
            patch("services.user.get_provider_by_id", return_value=mock_provider),
            patch("services.user.get_provider_model", return_value="gemini-2.5-flash"),
        ):
            result = get_user_model(user)
        assert result == "gemini-2.5-flash"

    def test_falls_back_to_default_when_no_model_saved(self):
        user = _make_user(provider_id=1)
        mock_provider = MagicMock()
        mock_provider.name = "gemini"
        with (
            patch("services.user.get_provider_by_id", return_value=mock_provider),
            patch("services.user.get_provider_model", return_value=None),
        ):
            result = get_user_model(user)
        assert result == DEFAULT_MODELS["gemini"]

    def test_returns_none_when_provider_not_in_db(self):
        user = _make_user(provider_id=99)
        with patch("services.user.get_provider_by_id", return_value=None):
            result = get_user_model(user)
        assert result is None

class TestConstants:
    def test_supported_providers_has_four(self):
        assert len(SUPPORTED_PROVIDERS) == 4
        assert "gemini" in SUPPORTED_PROVIDERS
        assert "openai" in SUPPORTED_PROVIDERS
        assert "anthropic" in SUPPORTED_PROVIDERS
        assert "mistral" in SUPPORTED_PROVIDERS

    def test_default_models_has_all_providers(self):
        for provider in SUPPORTED_PROVIDERS:
            assert provider in DEFAULT_MODELS

    def test_provider_labels_has_all_providers(self):
        for provider in SUPPORTED_PROVIDERS:
            assert provider in PROVIDER_LABELS

    def test_provider_models_has_all_providers(self):
        for provider in SUPPORTED_PROVIDERS:
            assert provider in PROVIDER_MODELS
            assert len(PROVIDER_MODELS[provider]) > 0
