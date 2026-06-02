"""Tests for services/forgetting_curve.py."""

import math
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest
from services.forgetting_curve import (
    RETENTION_THRESHOLD,
    retention,
    get_forgotten_topics,
)
from models.topic_knowledge import TopicKnowledge

class TestRetention:
    def test_returns_zero_when_stability_is_zero(self):
        assert retention(5.0, 0.0) == 0.0

    def test_returns_zero_when_stability_is_negative(self):
        assert retention(5.0, -1.0) == 0.0

    def test_returns_1_when_days_elapsed_is_0(self):
        assert retention(0.0, 10.0) == pytest.approx(1.0)

    def test_decays_exponentially(self):
        r1 = retention(5.0, 10.0)
        r2 = retention(10.0, 10.0)
        assert r1 > r2
        assert r1 == pytest.approx(math.exp(-0.5))
        assert r2 == pytest.approx(math.exp(-1.0))

    def test_threshold_crossover(self):
        # At stability=10, retention drops below 0.70 after ~3.57 days
        r_before = retention(3.0, 10.0)
        r_after = retention(4.0, 10.0)
        assert r_before > RETENTION_THRESHOLD
        assert r_after < RETENTION_THRESHOLD

class TestGetForgottenTopics:
    def _patch_session(self, session_mock):
        patcher = patch("services.forgetting_curve.Session")
        mock_cls = patcher.start()
        mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        return patcher

    def test_returns_forgotten_topic_when_retention_below_threshold(self):
        now = datetime.now(timezone.utc)
        old_date = now - timedelta(days=30)
        row = TopicKnowledge(
            skill_id=1,
            user_id=1,
            topic="Variables",
            week=1,
            stability_days=5.0,
            last_studied_at=old_date,
        )
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [row]
        session.exec.return_value = exec_mock
        patcher = self._patch_session(session)
        try:
            result = get_forgotten_topics(1, 1)
            assert "Variables" in result
        finally:
            patcher.stop()

    def test_does_not_return_recent_topic(self):
        now = datetime.now(timezone.utc)
        recent = now - timedelta(hours=1)
        row = TopicKnowledge(
            skill_id=1,
            user_id=1,
            topic="Loops",
            week=1,
            stability_days=21.0,
            last_studied_at=recent,
        )
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [row]
        session.exec.return_value = exec_mock
        patcher = self._patch_session(session)
        try:
            result = get_forgotten_topics(1, 1)
            assert "Loops" not in result
        finally:
            patcher.stop()

    def test_handles_naive_datetime_by_assuming_utc(self):
        now = datetime.now(timezone.utc)
        old_naive = datetime.utcnow() - timedelta(days=30)  # naive, no tzinfo
        row = TopicKnowledge(
            skill_id=1,
            user_id=1,
            topic="Functions",
            week=1,
            stability_days=5.0,
            last_studied_at=old_naive,
        )
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [row]
        session.exec.return_value = exec_mock
        patcher = self._patch_session(session)
        try:
            result = get_forgotten_topics(1, 1)
            assert "Functions" in result
        finally:
            patcher.stop()

    def test_returns_empty_when_no_topics(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = self._patch_session(session)
        try:
            result = get_forgotten_topics(1, 1)
            assert result == []
        finally:
            patcher.stop()
