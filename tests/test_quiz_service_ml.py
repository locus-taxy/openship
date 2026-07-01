"""Tests for new ML-related quiz service functions."""

from unittest.mock import MagicMock, patch
import pytest
from services.quiz import (
    all_weeks_complete,
    get_topics_for_week,
    get_quiz_by_week,
    get_previous_best_score,
)
from models.quiz import Quiz
from models.daily_task import DailyTask

def _patch_session(session_mock):
    patcher = patch("services.quiz.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

class TestAllWeeksComplete:
    def test_returns_true_when_no_incomplete_tasks_in_week(self):
        # New impl: first exec checks any_task (must return non-None), second checks incomplete
        any_task = DailyTask(id=1, user_id="u", skill="Python", skill_id=1, completed=True)
        exec_any = MagicMock()
        exec_any.first.return_value = any_task
        exec_incomplete = MagicMock()
        exec_incomplete.first.return_value = None  # no incomplete tasks
        session = MagicMock()
        session.exec.side_effect = [exec_any, exec_incomplete]
        patcher = _patch_session(session)
        try:
            result = all_weeks_complete(1, week=2)
            assert result is True
        finally:
            patcher.stop()

    def test_returns_false_when_no_tasks_exist(self):
        # New impl: returns False when no tasks exist for the week
        exec_any = MagicMock()
        exec_any.first.return_value = None  # no tasks at all
        session = MagicMock()
        session.exec.return_value = exec_any
        patcher = _patch_session(session)
        try:
            result = all_weeks_complete(1, week=2)
            assert result is False
        finally:
            patcher.stop()

    def test_returns_false_when_incomplete_task_exists_in_week(self):
        any_task = DailyTask(id=1, user_id="u", skill="Python", skill_id=1, completed=True)
        incomplete_task = DailyTask(id=5, user_id="u", skill="Python", skill_id=1, completed=False)
        exec_any = MagicMock()
        exec_any.first.return_value = any_task
        exec_incomplete = MagicMock()
        exec_incomplete.first.return_value = incomplete_task
        session = MagicMock()
        session.exec.side_effect = [exec_any, exec_incomplete]
        patcher = _patch_session(session)
        try:
            result = all_weeks_complete(1, week=2)
            assert result is False
        finally:
            patcher.stop()

class TestGetTopicsForWeek:
    """get_topics_for_week returns canonical remediation topics + new-day topics."""

    def _run(self, tasks, canonical=None):
        """Helper: patch both session (new-day DailyTask query) and canonical lookup."""
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = tasks
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        with patch("services.quiz.get_canonical_topics_for_week", return_value=canonical or []):
            try:
                return get_topics_for_week(1, week=1)
            finally:
                patcher.stop()

    def test_returns_new_topics_when_no_remediation(self):
        tasks = [MagicMock(topic="Variables"), MagicMock(topic="Loops")]
        result = self._run(tasks)
        assert result == ["Variables", "Loops"]

    def test_deduplicates_new_topics(self):
        tasks = [MagicMock(topic="Variables"), MagicMock(topic="Variables")]
        result = self._run(tasks)
        assert result == ["Variables"]

    def test_canonical_topics_come_first(self):
        tasks = [MagicMock(topic="Functions")]
        result = self._run(tasks, canonical=["Arrays", "Recursion"])
        assert result == ["Arrays", "Recursion", "Functions"]

    def test_canonical_topic_not_duplicated_by_new_day(self):
        # A new-day chapter happens to be named the same as a canonical topic
        tasks = [MagicMock(topic="Arrays"), MagicMock(topic="Functions")]
        result = self._run(tasks, canonical=["Arrays"])
        assert result == ["Arrays", "Functions"]

    def test_filters_out_none_topics(self):
        tasks = [MagicMock(topic="Functions"), MagicMock(topic=None)]
        result = self._run(tasks)
        assert result == ["Functions"]

    def test_returns_empty_when_no_tasks_and_no_canonical(self):
        result = self._run([])
        assert result == []

    def test_returns_only_canonical_when_all_days_are_remediation(self):
        # All DailyTask rows are remediation days → session returns empty for non-remediation query
        result = self._run([], canonical=["Arrays", "Loops"])
        assert result == ["Arrays", "Loops"]

class TestGetQuizByWeek:
    def test_returns_quiz_when_found(self):
        quiz = Quiz(id=5, skill_id=1, week=2, pass_score=60)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = quiz
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_quiz_by_week(1, week=2)
            assert result is quiz
        finally:
            patcher.stop()

    def test_returns_none_when_not_found(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_quiz_by_week(1, week=99)
            assert result is None
        finally:
            patcher.stop()

class TestGetPreviousBestScore:
    def test_returns_none_when_no_previous_quiz(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_previous_best_score(1, user_id=1, before_week=1)
            assert result is None
        finally:
            patcher.stop()

    def test_returns_best_score_from_previous_week_quiz(self):
        prev_quiz = Quiz(id=3, skill_id=1, week=1, pass_score=60)
        prev_quiz.id = 3
        session = MagicMock()
        exec_mock = MagicMock()

        call_count = [0]

        def exec_side_effect(stmt):
            em = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                em.first.return_value = prev_quiz  # get_quiz_by_week call
            else:
                em.all.return_value = [MagicMock(score=75), MagicMock(score=85)]  # get_best_score
            return em

        session.exec.side_effect = exec_side_effect
        patcher = _patch_session(session)
        try:
            result = get_previous_best_score(1, user_id=1, before_week=2)
            assert result == 85
        finally:
            patcher.stop()
