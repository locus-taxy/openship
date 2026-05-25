from unittest.mock import MagicMock, patch
import pytest
from services.daily_task import (
    get_tasks_based_on_skill_id,
    get_tasks_for_generating_newsletter,
    store_syllabus_tasks,
    clear_syllabus_tasks,
    delete_week_tasks,
    store_week_tasks,
)
from models.daily_task import DailyTask

def _patch_session(session_mock):
    patcher = patch("services.daily_task.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

def _make_task(**kwargs):
    defaults = dict(
        id=1,
        user_id="u1",
        skill="Python",
        skill_id=1,
        topic="Variables",
        task="Learn variables",
        hours=2,
        day=1,
        newsletter=None,
        content_blocks=None,
        completed=False,
    )
    defaults.update(kwargs)
    return DailyTask(**defaults)

class TestGetTasksBasedOnSkillId:
    def test_returns_list_of_task_dicts(self):
        task = _make_task()
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [task]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_tasks_based_on_skill_id(1)
            assert len(result) == 1
            assert result[0]["skill"] == "Python"
            assert result[0]["topic"] == "Variables"
        finally:
            patcher.stop()

    def test_returns_empty_list_when_no_tasks(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_tasks_based_on_skill_id(999)
            assert result == []
        finally:
            patcher.stop()

class TestGetTasksForGeneratingNewsletter:
    def test_returns_tasks_without_content(self):
        task = _make_task(newsletter=None, content_blocks=None)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [task]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_tasks_for_generating_newsletter(1)
            assert len(result) == 1
            assert "id" in result[0]
            assert "topic" in result[0]
        finally:
            patcher.stop()

    def test_returns_empty_list_when_all_have_content(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_tasks_for_generating_newsletter(1)
            assert result == []
        finally:
            patcher.stop()

class TestStoreSyllabusTasks:
    def test_stores_all_tasks_and_returns_true(self):
        session = MagicMock()
        patcher = _patch_session(session)
        try:
            syllabus_data = [
                {
                    "month": 1,
                    "weeks": [
                        {
                            "week": 1,
                            "daily_plan": [
                                {"day": 1, "topic": "Variables", "task": "Learn variables"},
                                {"day": 2, "topic": "Loops", "task": "Learn loops"},
                            ],
                        }
                    ],
                }
            ]
            result = store_syllabus_tasks("user-1", "Python", syllabus_data, hours=2, skill_id=1)
            assert result is True
            assert session.add.call_count == 2
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_returns_false_on_db_error(self):
        session = MagicMock()
        session.commit.side_effect = Exception("DB error")
        patcher = _patch_session(session)
        try:
            result = store_syllabus_tasks(
                "u1",
                "Python",
                [
                    {
                        "month": 1,
                        "weeks": [
                            {"week": 1, "daily_plan": [{"day": 1, "topic": "T", "task": "T"}]}
                        ],
                    }
                ],
                hours=2,
                skill_id=1,
            )
            assert result is False
        finally:
            patcher.stop()

    def test_handles_empty_syllabus_data(self):
        session = MagicMock()
        patcher = _patch_session(session)
        try:
            result = store_syllabus_tasks("u1", "Python", [], hours=2, skill_id=1)
            assert result is True
            session.add.assert_not_called()
        finally:
            patcher.stop()

    def test_only_week_filter_skips_other_weeks(self):
        """Covers line 240 — only_week skips weeks that don't match."""
        session = MagicMock()
        patcher = _patch_session(session)
        try:
            syllabus_data = [
                {
                    "month": 1,
                    "weeks": [
                        {"week": 1, "daily_plan": [{"day": 1, "topic": "T1", "task": "Task1"}]},
                        {"week": 2, "daily_plan": [{"day": 8, "topic": "T2", "task": "Task2"}]},
                    ],
                }
            ]
            result = store_syllabus_tasks(
                "u1", "Python", syllabus_data, hours=2, skill_id=1, only_week=1
            )
            assert result is True
            # Only week 1's task should be added
            assert session.add.call_count == 1
        finally:
            patcher.stop()

class TestClearSyllabusTasks:
    def test_executes_and_commits(self):
        """Covers lines 218-222 — clear_syllabus_tasks deletes all rows and commits."""
        session = MagicMock()
        patcher = _patch_session(session)
        try:
            clear_syllabus_tasks(skill_id=1)
            session.exec.assert_called_once()
            session.commit.assert_called_once()
        finally:
            patcher.stop()

class TestDeleteWeekTasks:
    def test_executes_delete_and_commits(self):
        """Covers lines 262-268 — delete_week_tasks deletes rows for a specific week."""
        session = MagicMock()
        patcher = _patch_session(session)
        try:
            delete_week_tasks(skill_id=1, week=2)
            session.exec.assert_called_once()
            session.commit.assert_called_once()
        finally:
            patcher.stop()

class TestStoreWeekTasks:
    def test_stores_tasks_and_returns_true(self):
        """Covers lines 280-296 — store_week_tasks persists daily plan rows."""
        session = MagicMock()
        patcher = _patch_session(session)
        try:
            daily_plan = [
                {"day": 8, "topic": "Classes", "task": "Learn OOP"},
                {"day": 9, "topic": "Inheritance", "task": "Learn inheritance"},
            ]
            result = store_week_tasks(
                "u1", "Python", 1, week=2, month=1, daily_plan=daily_plan, hours=2
            )
            assert result is True
            assert session.add.call_count == 2
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_returns_false_on_db_error(self):
        """Covers lines 297-299 — exception during store returns False."""
        session = MagicMock()
        session.commit.side_effect = Exception("DB failure")
        patcher = _patch_session(session)
        try:
            result = store_week_tasks(
                "u1",
                "Python",
                1,
                week=2,
                month=1,
                daily_plan=[{"day": 8, "topic": "T", "task": "T"}],
                hours=2,
            )
            assert result is False
        finally:
            patcher.stop()

    def test_returns_true_for_empty_daily_plan(self):
        """Empty daily plan still commits and returns True."""
        session = MagicMock()
        patcher = _patch_session(session)
        try:
            result = store_week_tasks("u1", "Python", 1, week=2, month=1, daily_plan=[], hours=2)
            assert result is True
            session.add.assert_not_called()
        finally:
            patcher.stop()
