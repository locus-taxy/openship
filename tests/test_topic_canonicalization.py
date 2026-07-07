"""Tests for topic canonicalization: week_remediation service, build_topic_map,
get_canonical_topic_names, and store_week_tasks remediation_days flag."""

from unittest.mock import MagicMock, call, patch

import pytest

from services.quiz import build_topic_map
from services.week_remediation import get_canonical_topics_for_week, store_remediation_topics

# ── build_topic_map ───────────────────────────────────────────────────────────

class TestBuildTopicMap:
    def test_empty_topics_returns_empty(self):
        assert build_topic_map([], 5) == {}

    def test_single_topic_fills_all_slots(self):
        result = build_topic_map(["Arrays"], 3)
        assert result == {1: "Arrays", 2: "Arrays", 3: "Arrays"}

    def test_equal_topics_and_questions_one_each(self):
        result = build_topic_map(["A", "B", "C"], 3)
        assert result == {1: "A", 2: "B", 3: "C"}

    def test_every_topic_gets_at_least_one_slot(self):
        topics = ["Arrays", "Recursion", "Trees"]
        result = build_topic_map(topics, 5)
        assigned = list(result.values())
        for t in topics:
            assert t in assigned, f"{t} has no slot"

    def test_extra_slots_distributed_round_robin(self):
        topics = ["A", "B"]
        result = build_topic_map(topics, 5)
        assert len(result) == 5
        values = list(result.values())
        assert values.count("A") >= 1
        assert values.count("B") >= 1

    def test_num_questions_less_than_topics_raises(self):
        """Caller must pass num_questions >= len(topics) — enforced with ValueError."""
        import pytest

        topics = ["A", "B", "C"]
        with pytest.raises(ValueError, match="num_questions"):
            build_topic_map(topics, 2)

    def test_map_keys_are_one_indexed(self):
        result = build_topic_map(["X", "Y"], 4)
        assert set(result.keys()) == {1, 2, 3, 4}

# ── store_remediation_topics ──────────────────────────────────────────────────

class TestStoreRemediationTopics:
    def _patch_session(self, session_mock):
        patcher = patch("services.week_remediation.Session")
        mock_cls = patcher.start()
        mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        return patcher

    def test_adds_weak_and_forgotten_rows(self):
        session = MagicMock()
        session.exec.return_value = MagicMock()
        patcher = self._patch_session(session)
        with patch("services.week_remediation.sa_delete"):
            try:
                store_remediation_topics(1, 2, ["Arrays"], ["Recursion"])
                added_topics = [c.args[0].topic for c in session.add.call_args_list]
                added_types = [c.args[0].topic_type for c in session.add.call_args_list]
                assert "Arrays" in added_topics
                assert "Recursion" in added_topics
                assert "weak" in added_types
                assert "forgotten" in added_types
                session.commit.assert_called_once()
            finally:
                patcher.stop()

    def test_no_rows_when_both_lists_empty(self):
        session = MagicMock()
        session.exec.return_value = MagicMock()
        patcher = self._patch_session(session)
        with patch("services.week_remediation.sa_delete"):
            try:
                store_remediation_topics(1, 2, [], [])
                session.add.assert_not_called()
                session.commit.assert_called_once()
            finally:
                patcher.stop()

    def test_silently_logs_on_exception(self):
        session = MagicMock()
        session.exec.side_effect = RuntimeError("db error")
        patcher = self._patch_session(session)
        with patch("services.week_remediation.sa_delete"):
            try:
                # Should not raise
                store_remediation_topics(1, 2, ["X"], [])
            finally:
                patcher.stop()

# ── get_canonical_topics_for_week ─────────────────────────────────────────────

class TestGetCanonicalTopicsForWeek:
    def _patch_session(self, rows):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = rows
        session.exec.return_value = exec_mock
        patcher = patch("services.week_remediation.Session")
        mock_cls = patcher.start()
        mock_cls.return_value.__enter__ = MagicMock(return_value=session)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        return patcher

    def _row(self, topic, topic_type):
        r = MagicMock()
        r.topic = topic
        r.topic_type = topic_type
        return r

    def test_returns_weak_topics_before_forgotten(self):
        rows = [self._row("Arrays", "weak"), self._row("Recursion", "forgotten")]
        patcher = self._patch_session(rows)
        try:
            result = get_canonical_topics_for_week(1, 2)
            assert result == ["Arrays", "Recursion"]
        finally:
            patcher.stop()

    def test_deduplicates_across_types(self):
        rows = [self._row("Arrays", "weak"), self._row("Arrays", "forgotten")]
        patcher = self._patch_session(rows)
        try:
            result = get_canonical_topics_for_week(1, 2)
            assert result == ["Arrays"]
        finally:
            patcher.stop()

    def test_returns_empty_when_no_rows(self):
        patcher = self._patch_session([])
        try:
            result = get_canonical_topics_for_week(1, 2)
            assert result == []
        finally:
            patcher.stop()

# ── store_week_tasks remediation_days flag ────────────────────────────────────

class TestStoreWeekTasksRemediationFlag:
    def _patch_session(self, session_mock):
        patcher = patch("services.daily_task.Session")
        mock_cls = patcher.start()
        mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        return patcher

    def _run(self, daily_plan, remediation_days=0):
        from services.daily_task import store_week_tasks

        session = MagicMock()
        patcher = self._patch_session(session)
        try:
            store_week_tasks(
                "u1", "Python", 1, 2, 1, daily_plan, 1, remediation_days=remediation_days
            )
            return [c.args[0] for c in session.add.call_args_list]
        finally:
            patcher.stop()

    def test_all_days_non_remediation_by_default(self):
        plan = [{"day": 1, "topic": "A", "task": "t"}, {"day": 2, "topic": "B", "task": "t"}]
        tasks = self._run(plan)
        assert all(not t.is_remediation_day for t in tasks)

    def test_first_n_days_flagged_as_remediation(self):
        plan = [
            {"day": 1, "topic": "Reinforcing: Arrays", "task": "t"},
            {"day": 2, "topic": "Reinforcing: Loops", "task": "t"},
            {"day": 3, "topic": "Trees", "task": "t"},
        ]
        tasks = self._run(plan, remediation_days=2)
        assert tasks[0].is_remediation_day is True
        assert tasks[1].is_remediation_day is True
        assert tasks[2].is_remediation_day is False

    def test_zero_remediation_days_none_flagged(self):
        plan = [{"day": 1, "topic": "A", "task": "t"}, {"day": 2, "topic": "B", "task": "t"}]
        tasks = self._run(plan, remediation_days=0)
        assert all(not t.is_remediation_day for t in tasks)
