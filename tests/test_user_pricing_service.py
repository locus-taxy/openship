"""Tests for services/user_pricing.py — covers all previously uncovered lines."""

from unittest.mock import MagicMock, patch
import pytest

def _patch_session(session_mock):
    patcher = patch("services.user_pricing.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

def _make_row(input_per_1m_usd=1.0, output_per_1m_usd=2.0):
    from models.user_model_price import UserModelPrice

    return UserModelPrice(
        user_id=1,
        provider="openai",
        model="gpt-4o-mini",
        input_per_1m_usd=input_per_1m_usd,
        output_per_1m_usd=output_per_1m_usd,
    )

class TestGetUserModelPrice:
    def test_returns_tuple_when_row_exists(self):
        from services.user_pricing import get_user_model_price

        row = _make_row(1.5, 3.0)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = row
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_user_model_price(1, "openai", "gpt-4o-mini")
            assert result == (1.5, 3.0)
        finally:
            patcher.stop()

    def test_returns_none_when_no_row(self):
        from services.user_pricing import get_user_model_price

        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_user_model_price(1, "openai", "gpt-9999")
            assert result is None
        finally:
            patcher.stop()

class TestSaveUserModelPrice:
    def test_inserts_new_row_when_not_exists(self):
        from services.user_pricing import save_user_model_price

        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None  # No existing row
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            save_user_model_price(1, "openai", "gpt-4o-mini", 1.0, 2.0)
            session.add.assert_called_once()
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_updates_existing_row(self):
        from services.user_pricing import save_user_model_price

        existing = _make_row(0.5, 1.0)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = existing
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            save_user_model_price(1, "openai", "gpt-4o-mini", 2.5, 5.0)
            assert existing.input_per_1m_usd == 2.5
            assert existing.output_per_1m_usd == 5.0
            session.add.assert_called_once()
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_raises_on_negative_input_price(self):
        from services.user_pricing import save_user_model_price

        with pytest.raises(ValueError, match="non-negative"):
            save_user_model_price(1, "openai", "gpt-4o-mini", -1.0, 2.0)

    def test_raises_on_negative_output_price(self):
        from services.user_pricing import save_user_model_price

        with pytest.raises(ValueError, match="non-negative"):
            save_user_model_price(1, "openai", "gpt-4o-mini", 1.0, -0.01)

    def test_zero_prices_are_accepted(self):
        from services.user_pricing import save_user_model_price

        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            # Should not raise
            save_user_model_price(1, "openai", "gpt-4o-mini", 0.0, 0.0)
            session.commit.assert_called_once()
        finally:
            patcher.stop()
