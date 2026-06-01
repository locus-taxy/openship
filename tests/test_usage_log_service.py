"""Tests for services/usage_log.py — covers all previously uncovered lines."""

from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest

def _patch_session(session_mock):
    patcher = patch("services.usage_log.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

def _make_log_row(**kwargs):
    from models.llm_usage_log import LlmUsageLog

    defaults = dict(
        user_id=1,
        call_type="chapter",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=100,
        output_tokens=200,
        cost_usd=0.001,
        ref_id=None,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
    )
    defaults.update(kwargs)
    return LlmUsageLog(**defaults)

class TestLogLlmUsage:
    def test_inserts_row_and_commits(self):
        from services.usage_log import log_llm_usage

        session = MagicMock()
        patcher = _patch_session(session)
        try:
            log_llm_usage(
                user_id=1,
                call_type="chapter",
                provider="openai",
                model="gpt-4o-mini",
                input_tokens=100,
                output_tokens=200,
                cost_usd=0.001,
                ref_id=42,
            )
            session.add.assert_called_once()
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_swallows_sqlalchemy_error(self):
        from services.usage_log import log_llm_usage
        from sqlalchemy.exc import SQLAlchemyError

        session = MagicMock()
        session.commit.side_effect = SQLAlchemyError("db down")
        patcher = _patch_session(session)
        try:
            # Should not raise
            log_llm_usage(1, "chapter", "openai", "gpt-4o-mini", 10, 20, 0.001)
        finally:
            patcher.stop()

    def test_logs_warning_on_error(self, caplog):
        from services.usage_log import log_llm_usage
        from sqlalchemy.exc import SQLAlchemyError
        import logging

        session = MagicMock()
        session.commit.side_effect = SQLAlchemyError("boom")
        patcher = _patch_session(session)
        try:
            with caplog.at_level(logging.WARNING, logger="services.usage_log"):
                log_llm_usage(1, "chapter", "openai", "gpt-4o-mini", 10, 20, 0.001)
            assert any("Failed" in r.message for r in caplog.records)
        finally:
            patcher.stop()

class TestGetChapterCost:
    def test_aggregates_costs_for_chapter(self):
        from services.usage_log import get_chapter_cost

        row1 = _make_log_row(cost_usd=0.01)
        row2 = _make_log_row(cost_usd=0.02)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [row1, row2]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_chapter_cost(task_id=5)
            assert result["total_cost_usd"] == pytest.approx(0.03, abs=1e-6)
            assert result["generation_count"] == 2
            assert len(result["logs"]) == 2
        finally:
            patcher.stop()

    def test_returns_zero_when_no_rows(self):
        from services.usage_log import get_chapter_cost

        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_chapter_cost(task_id=99)
            assert result["total_cost_usd"] == 0.0
            assert result["generation_count"] == 0
            assert result["logs"] == []
        finally:
            patcher.stop()

    def test_log_entry_has_expected_keys(self):
        from services.usage_log import get_chapter_cost

        row = _make_log_row(cost_usd=0.005)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [row]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_chapter_cost(task_id=1)
            log = result["logs"][0]
            assert "provider" in log
            assert "model" in log
            assert "input_tokens" in log
            assert "output_tokens" in log
            assert "cost_usd" in log
            assert "created_at" in log
        finally:
            patcher.stop()

    def test_handles_none_cost(self):
        from services.usage_log import get_chapter_cost

        row = _make_log_row(cost_usd=None)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [row]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_chapter_cost(task_id=1)
            assert result["total_cost_usd"] == 0.0
        finally:
            patcher.stop()

class TestGetUserUsageCost:
    def test_aggregates_all_fields(self):
        from services.usage_log import get_user_usage_cost

        row1 = _make_log_row(
            call_type="chapter", input_tokens=100, output_tokens=200, cost_usd=0.01
        )
        row2 = _make_log_row(call_type="quiz", input_tokens=50, output_tokens=100, cost_usd=0.005)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [row1, row2]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_user_usage_cost(user_id=1)
            assert result["total_calls"] == 2
            assert result["total_input_tokens"] == 150
            assert result["total_output_tokens"] == 300
            assert result["total_cost_usd"] == pytest.approx(0.015, abs=1e-6)
            assert "chapter" in result["by_type"]
            assert "quiz" in result["by_type"]
            assert result["by_type"]["chapter"]["calls"] == 1
            assert result["by_type"]["quiz"]["calls"] == 1
        finally:
            patcher.stop()

    def test_empty_logs_returns_zeros(self):
        from services.usage_log import get_user_usage_cost

        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_user_usage_cost(user_id=999)
            assert result["total_calls"] == 0
            assert result["total_cost_usd"] == 0.0
            assert result["by_type"] == {}
        finally:
            patcher.stop()

    def test_handles_none_tokens(self):
        from services.usage_log import get_user_usage_cost

        row = _make_log_row(input_tokens=None, output_tokens=None, cost_usd=None)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [row]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_user_usage_cost(user_id=1)
            assert result["total_input_tokens"] == 0
            assert result["total_output_tokens"] == 0
            assert result["total_cost_usd"] == 0.0
        finally:
            patcher.stop()
