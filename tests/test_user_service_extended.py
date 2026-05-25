from unittest.mock import MagicMock, patch
import pytest
from services.user import (
    get_provider_by_name,
    get_provider_by_id,
    get_provider_model,
    update_llm_settings,
    get_provider_pricing,
    update_llm_pricing,
    update_currency_settings,
    get_currency_settings,
    compute_generation_cost_usd,
)
from models.user import User
from models.llm_provider import LlmProvider
from models.user_api_key import UserApiKey

def _patch_session(session_mock):
    patcher = patch("services.user.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

def _make_user(provider_id=None):
    return User(
        id=1,
        email="test@example.com",
        name="Test",
        is_active=True,
        hashed_password="$2b$hash",
        llm_provider_id=provider_id,
    )

class TestGetProviderByName:
    def test_returns_provider_when_found(self):
        provider = LlmProvider(id=1, name="gemini", label="Google Gemini")
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = provider
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_provider_by_name("gemini")
            assert result is provider
        finally:
            patcher.stop()

    def test_returns_none_when_not_found(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_provider_by_name("unknown")
            assert result is None
        finally:
            patcher.stop()

class TestGetProviderById:
    def test_returns_provider_when_found(self):
        provider = LlmProvider(id=1, name="gemini", label="Google Gemini")
        session = MagicMock()
        session.get.return_value = provider
        patcher = _patch_session(session)
        try:
            result = get_provider_by_id(1)
            assert result is provider
        finally:
            patcher.stop()

    def test_returns_none_when_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            result = get_provider_by_id(999)
            assert result is None
        finally:
            patcher.stop()

class TestGetProviderModel:
    def test_returns_model_when_record_found(self):
        record = MagicMock(spec=UserApiKey)
        record.llm_model = "gemini-2.5-flash"
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = record
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_provider_model(1, 1)
            assert result == "gemini-2.5-flash"
        finally:
            patcher.stop()

    def test_returns_none_when_no_record(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_provider_model(1, 99)
            assert result is None
        finally:
            patcher.stop()

class TestUpdateLlmSettings:
    def test_does_nothing_when_user_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            update_llm_settings(999, 1, "api-key")
            session.commit.assert_not_called()
        finally:
            patcher.stop()

    def test_creates_new_api_key_record(self):
        user = _make_user()
        session = MagicMock()
        session.get.return_value = user
        exec_mock = MagicMock()
        exec_mock.first.return_value = None  # no existing record
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            update_llm_settings(1, 1, "new-api-key-12345")
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_updates_existing_api_key_record(self):
        user = _make_user()
        existing_record = MagicMock(spec=UserApiKey)
        existing_record.api_key = "old-encrypted-key"
        existing_record.llm_model = None
        session = MagicMock()
        session.get.return_value = user
        exec_mock = MagicMock()
        exec_mock.first.return_value = existing_record
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            update_llm_settings(1, 1, "new-api-key-12345", model="gemini-2.5-flash")
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_empty_api_key_deletes_record(self):
        user = _make_user(provider_id=1)
        existing_record = MagicMock(spec=UserApiKey)
        session = MagicMock()
        session.get.return_value = user
        exec_mock = MagicMock()
        exec_mock.first.return_value = existing_record
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            update_llm_settings(1, 1, "")  # empty = delete
            session.delete.assert_called_once_with(existing_record)
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_no_api_key_change_updates_active_provider(self):
        user = _make_user()
        session = MagicMock()
        session.get.return_value = user
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            update_llm_settings(1, 2, None)  # switch provider only
            assert user.llm_provider_id == 2
            session.commit.assert_called_once()
        finally:
            patcher.stop()

class TestGetProviderPricing:
    def test_returns_pricing_when_record_found(self):
        record = MagicMock(spec=UserApiKey)
        record.input_per_1m_usd = 1.5
        record.output_per_1m_usd = 3.0
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = record
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_provider_pricing(1, 1)
            assert result == (1.5, 3.0)
        finally:
            patcher.stop()

    def test_returns_none_none_when_no_record(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_provider_pricing(1, 99)
            assert result == (None, None)
        finally:
            patcher.stop()

class TestUpdateLlmPricing:
    def test_updates_pricing_when_record_found(self):
        record = MagicMock(spec=UserApiKey)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = record
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            update_llm_pricing(1, 1, 2.5, 10.0)
            assert record.input_per_1m_usd == 2.5
            assert record.output_per_1m_usd == 10.0
            session.add.assert_called_once_with(record)
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_does_nothing_when_record_not_found(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            update_llm_pricing(1, 99, 2.5, 10.0)
            session.add.assert_not_called()
            session.commit.assert_not_called()
        finally:
            patcher.stop()

class TestUpdateCurrencySettings:
    def test_saves_currency_settings(self):
        user = _make_user()
        session = MagicMock()
        session.get.return_value = user
        patcher = _patch_session(session)
        try:
            update_currency_settings(1, "EUR", 0.92)
            assert user.display_currency == "EUR"
            assert user.currency_exchange_rate == 0.92
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_raises_on_non_positive_rate(self):
        with pytest.raises(ValueError, match="positive"):
            update_currency_settings(1, "EUR", 0.0)

    def test_raises_on_negative_rate(self):
        with pytest.raises(ValueError):
            update_currency_settings(1, "EUR", -1.0)

    def test_does_nothing_when_user_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            update_currency_settings(999, "EUR", 1.0)
            session.commit.assert_not_called()
        finally:
            patcher.stop()

    def test_truncates_currency_code_to_8_chars(self):
        user = _make_user()
        session = MagicMock()
        session.get.return_value = user
        patcher = _patch_session(session)
        try:
            update_currency_settings(1, "toolongcurrency", 1.0)
            assert len(user.display_currency) <= 8
        finally:
            patcher.stop()

class TestGetCurrencySettings:
    def test_returns_stored_values(self):
        user = _make_user()
        user.display_currency = "GBP"
        user.currency_exchange_rate = 0.78
        session = MagicMock()
        session.get.return_value = user
        patcher = _patch_session(session)
        try:
            currency, rate = get_currency_settings(1)
            assert currency == "GBP"
            assert rate == 0.78
        finally:
            patcher.stop()

    def test_returns_usd_defaults_when_user_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            currency, rate = get_currency_settings(999)
            assert currency == "USD"
            assert rate == 1.0
        finally:
            patcher.stop()

    def test_returns_usd_defaults_when_fields_none(self):
        user = _make_user()
        user.display_currency = None
        user.currency_exchange_rate = None
        session = MagicMock()
        session.get.return_value = user
        patcher = _patch_session(session)
        try:
            currency, rate = get_currency_settings(1)
            assert currency == "USD"
            assert rate == 1.0
        finally:
            patcher.stop()

class TestComputeGenerationCostUsd:
    def test_returns_correct_cost(self):
        result = compute_generation_cost_usd(1000, 500, 2.0, 10.0)
        # (1000 * 2.0 + 500 * 10.0) / 1_000_000 = 0.007
        assert result == pytest.approx(0.007)

    def test_returns_none_when_any_value_is_none(self):
        assert compute_generation_cost_usd(None, 500, 2.0, 10.0) is None
        assert compute_generation_cost_usd(1000, None, 2.0, 10.0) is None
        assert compute_generation_cost_usd(1000, 500, None, 10.0) is None
        assert compute_generation_cost_usd(1000, 500, 2.0, None) is None

    def test_returns_none_when_negative_token_count(self):
        assert compute_generation_cost_usd(-1, 500, 2.0, 10.0) is None

    def test_returns_none_when_negative_price(self):
        assert compute_generation_cost_usd(1000, 500, -2.0, 10.0) is None

    def test_zero_tokens_returns_zero_cost(self):
        assert compute_generation_cost_usd(0, 0, 2.0, 10.0) == 0.0
