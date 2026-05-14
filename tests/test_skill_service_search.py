from unittest.mock import MagicMock, patch
import pytest
from services.skill import search_syllabi

def _patch_session(session_mock):
    patcher = patch("services.skill.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

class TestSearchSyllabi:
    def test_returns_empty_when_no_matches(self):
        session = MagicMock()
        # skill_matches returns empty, task_rows returns empty
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = search_syllabi(email="test@example.com", query="xyz")
            assert result == []
        finally:
            patcher.stop()

    def test_returns_matching_skills(self):
        from models.skill import Skill
        from models.quiz import Quiz

        session = MagicMock()
        skill_row = (1, "user-1", "test@example.com", "Python", 30, 2, None, 5, 3, "not_generated")

        # First exec: skill id matches (Skill.id query)
        # Second exec: task rows (DailyTask query - returns empty)
        # Third exec: aggregated skill rows
        skill_ids_exec = MagicMock()
        skill_ids_exec.all.return_value = [1]  # skill_matches

        task_exec = MagicMock()
        task_exec.all.return_value = []  # task_rows

        agg_exec = MagicMock()
        agg_exec.all.return_value = [skill_row]  # final aggregation

        session.exec.side_effect = [skill_ids_exec, task_exec, agg_exec]
        patcher = _patch_session(session)
        try:
            result = search_syllabi(email="test@example.com", query="Python")
            assert len(result) == 1
            assert result[0]["skill"] == "Python"
        finally:
            patcher.stop()

    def test_returns_task_matches(self):
        from models.daily_task import DailyTask

        session = MagicMock()

        task = MagicMock(spec=DailyTask)
        task.skill_id = 1
        task.id = 10
        task.day = 1
        task.topic = "Variables"
        task.task = "Learn vars"

        skill_row = (1, "user-1", "test@example.com", "Python", 30, 2, None, 5, 3, "not_generated")

        skill_ids_exec = MagicMock()
        skill_ids_exec.all.return_value = []  # no direct skill name matches

        task_exec = MagicMock()
        task_exec.all.return_value = [task]  # topic match

        agg_exec = MagicMock()
        agg_exec.all.return_value = [skill_row]

        session.exec.side_effect = [skill_ids_exec, task_exec, agg_exec]
        patcher = _patch_session(session)
        try:
            result = search_syllabi(email="test@example.com", query="Variables")
            assert len(result) == 1
            assert result[0]["skill"] == "Python"
            assert len(result[0]["matching_chapters"]) == 1
        finally:
            patcher.stop()
