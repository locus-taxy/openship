from unittest.mock import MagicMock, patch
import pytest
from services.daily_task import (
    get_tasks_based_on_skill_id,
    get_tasks_for_generating_newsletter,
    store_syllabus_tasks,
    clear_syllabus_tasks,
    delete_week_tasks,
    store_week_tasks,
    get_max_day_for_skill,
    get_week_content_style,
    claim_week_style,
    add_blocks_to_db,
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

class TestGetMaxDayForSkill:
    def test_returns_max_day_when_tasks_exist(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = 14
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_max_day_for_skill(1)
            assert result == 14
        finally:
            patcher.stop()

    def test_returns_zero_when_no_tasks(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_max_day_for_skill(999)
            assert result == 0
        finally:
            patcher.stop()

class TestGetWeekContentStyle:
    def test_returns_style_when_task_has_one(self):
        task = _make_task(content_style="visual_heavy")
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = task
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_week_content_style(1, week=1)
            assert result == "visual_heavy"
        finally:
            patcher.stop()

    def test_returns_none_when_no_task_with_style(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_week_content_style(1, week=1)
            assert result is None
        finally:
            patcher.stop()

class TestClaimWeekStyle:
    def test_writes_style_when_task_has_none(self):
        # New impl: issues a batch UPDATE via session.exec + commit (not add)
        task = _make_task(content_style=None, week=1)
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session(session)
        try:
            claim_week_style(task_id=1, style="example_heavy")
            session.exec.assert_called_once()
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_skips_write_when_task_week_is_none(self):
        # New impl: returns early when task.week is None (cannot scope the UPDATE)
        task = _make_task(content_style=None)  # week defaults to None
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session(session)
        try:
            claim_week_style(task_id=1, style="new_style")
            session.exec.assert_not_called()
            session.commit.assert_not_called()
        finally:
            patcher.stop()

    def test_skips_write_when_task_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            claim_week_style(task_id=999, style="visual_heavy")
            session.exec.assert_not_called()
        finally:
            patcher.stop()

    def test_logs_error_on_exception(self):
        session = MagicMock()
        session.get.side_effect = Exception("DB error")
        patcher = _patch_session(session)
        try:
            claim_week_style(task_id=1, style="any_style")
        finally:
            patcher.stop()

class TestAddBlocksToDbContentStyle:
    def test_sets_content_style_when_provided(self):
        task = _make_task()
        block = MagicMock()
        block.model_dump.return_value = {"type": "paragraph", "content": "hello"}
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session(session)
        try:
            result = add_blocks_to_db([block], task_id=1, content_style="visual_heavy")
            assert result is True
            assert task.content_style == "visual_heavy"
        finally:
            patcher.stop()
