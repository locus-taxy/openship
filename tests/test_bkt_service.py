"""Tests for services/bkt.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
from services.bkt import (
    MASTERY_THRESHOLD,
    _stability_from_p_known,
    _bkt_update,
    get_or_create_topic_knowledge,
    update_topic_knowledge,
    get_weak_topics,
)
from models.topic_knowledge import TopicKnowledge

class TestStabilityFromPKnown:
    def test_high_mastery_returns_21_days(self):
        assert _stability_from_p_known(MASTERY_THRESHOLD) == 21.0

    def test_above_0_70_returns_10_days(self):
        assert _stability_from_p_known(0.80) == 10.0

    def test_above_0_40_returns_5_days(self):
        assert _stability_from_p_known(0.50) == 5.0

    def test_below_0_40_returns_2_days(self):
        assert _stability_from_p_known(0.10) == 2.0

    def test_exactly_0_70_returns_10_days(self):
        assert _stability_from_p_known(0.70) == 10.0

    def test_exactly_0_40_returns_5_days(self):
        assert _stability_from_p_known(0.40) == 5.0

    def test_fallback_returns_2_days_when_map_exhausted(self):
        """Covers line 20 — fallback return 2.0 when no threshold matches."""
        import services.bkt as bkt_mod

        original = bkt_mod._STABILITY_MAP
        bkt_mod._STABILITY_MAP = ()  # empty map forces fallback
        try:
            result = _stability_from_p_known(0.5)
            assert result == 2.0
        finally:
            bkt_mod._STABILITY_MAP = original

class TestBktUpdate:
    def test_correct_answer_increases_p_known(self):
        p_before = 0.3
        p_after = _bkt_update(p_before, True, p_transit=0.10, p_guess=0.20, p_slip=0.10)
        assert p_after > p_before

    def test_incorrect_answer_decreases_or_holds_p_known(self):
        p_before = 0.8
        p_after = _bkt_update(p_before, False, p_transit=0.10, p_guess=0.20, p_slip=0.10)
        # p_known_given_obs will be low, but transit adds back some
        assert p_after < p_before

    def test_result_is_bounded_between_0_and_1(self):
        for correct in (True, False):
            result = _bkt_update(0.5, correct, 0.10, 0.20, 0.10)
            assert 0.0 <= result <= 1.0

    def test_zero_denominator_falls_back_to_p_known(self):
        # With p_guess=0 and p_known=0, denominator for correct branch = 0
        result = _bkt_update(0.0, True, p_transit=0.0, p_guess=0.0, p_slip=0.0)
        # numerator = 0 * (1-0) = 0; denominator = 0 * 1 + 1 * 0 = 0 → fallback to p_known=0
        # then + (1 - 0) * 0 = 0
        assert result == 0.0

class TestGetOrCreateTopicKnowledge:
    def _make_session(self, existing=None):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = existing
        session.exec.return_value = exec_mock
        return session

    def test_returns_existing_row_when_found(self):
        existing = TopicKnowledge(skill_id=1, user_id=1, topic="Loops", week=1)
        session = self._make_session(existing=existing)
        result = get_or_create_topic_knowledge(session, 1, 1, "Loops", 1)
        assert result is existing
        session.add.assert_not_called()

    def test_creates_new_row_when_not_found(self):
        session = self._make_session(existing=None)
        result = get_or_create_topic_knowledge(session, 1, 1, "Variables", 2)
        session.add.assert_called_once()
        assert result.topic == "Variables"
        assert result.week == 2

class TestUpdateTopicKnowledge:
    def _patch_session(self, session_mock):
        patcher = patch("services.bkt.Session")
        mock_cls = patcher.start()
        mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        return patcher

    def test_commits_after_all_updates(self):
        existing = TopicKnowledge(skill_id=1, user_id=1, topic="Loops", week=1, p_known=0.3)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = existing
        session.exec.return_value = exec_mock
        patcher = self._patch_session(session)
        try:
            update_topic_knowledge(1, 1, [("Loops", 1, True)])
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_increments_correct_on_correct_answer(self):
        existing = TopicKnowledge(
            skill_id=1, user_id=1, topic="Loops", week=1, correct=0, attempts=0
        )
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = existing
        session.exec.return_value = exec_mock
        patcher = self._patch_session(session)
        try:
            update_topic_knowledge(1, 1, [("Loops", 1, True)])
            assert existing.correct == 1
            assert existing.attempts == 1
        finally:
            patcher.stop()

    def test_does_not_increment_correct_on_wrong_answer(self):
        existing = TopicKnowledge(
            skill_id=1, user_id=1, topic="Loops", week=1, correct=0, attempts=0
        )
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = existing
        session.exec.return_value = exec_mock
        patcher = self._patch_session(session)
        try:
            update_topic_knowledge(1, 1, [("Loops", 1, False)])
            assert existing.correct == 0
            assert existing.attempts == 1
        finally:
            patcher.stop()

    def test_handles_empty_answers_list(self):
        session = MagicMock()
        patcher = self._patch_session(session)
        try:
            update_topic_knowledge(1, 1, [])
            session.commit.assert_called_once()
        finally:
            patcher.stop()

class TestGetWeakTopics:
    def _patch_session(self, session_mock):
        patcher = patch("services.bkt.Session")
        mock_cls = patcher.start()
        mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        return patcher

    def test_returns_topics_below_mastery_threshold_sorted_weakest_first(self):
        rows = [
            TopicKnowledge(skill_id=1, user_id=1, topic="Loops", week=1, p_known=0.50),
            TopicKnowledge(skill_id=1, user_id=1, topic="Variables", week=1, p_known=0.20),
        ]
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = rows
        session.exec.return_value = exec_mock
        patcher = self._patch_session(session)
        try:
            result = get_weak_topics(1, 1)
            assert result == ["Variables", "Loops"]  # weakest first
        finally:
            patcher.stop()

    def test_returns_empty_list_when_no_weak_topics(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = self._patch_session(session)
        try:
            result = get_weak_topics(1, 1)
            assert result == []
        finally:
            patcher.stop()
