import json
from unittest.mock import MagicMock, patch, call
import pytest
from services.daily_task import (
    get_chapter_content,
    add_blocks_to_db,
    add_content_to_db,
    mark_task_completed,
    get_tasks_based_on_skill_id,
    get_tasks_for_generating_newsletter,
)
from models.daily_task import DailyTask

def _patch_session(module_path, session_mock):
    patcher = patch(module_path)
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

class TestGetChapterContent:
    def test_returns_none_when_task_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = get_chapter_content(999)
            assert result is None
        finally:
            patcher.stop()

    def test_returns_dict_when_found(self):
        task = DailyTask(
            id=1,
            user_id="user-1",
            skill="Python",
            skill_id=10,
            topic="Variables",
            task="Learn variables",
            day=1,
            hours=2,
            completed=False,
            newsletter=None,
            content_blocks=None,
        )
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = get_chapter_content(1)
            assert result is not None
            assert result["id"] == 1
            assert result["skill"] == "Python"
        finally:
            patcher.stop()

    def test_has_content_false_when_both_none(self):
        task = DailyTask(
            id=1,
            user_id="u",
            skill="Python",
            skill_id=1,
            newsletter=None,
            content_blocks=None,
        )
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = get_chapter_content(1)
            assert result["has_content"] is False
        finally:
            patcher.stop()

    def test_has_content_true_when_newsletter_set(self):
        task = DailyTask(
            id=1,
            user_id="u",
            skill="Python",
            skill_id=1,
            newsletter="<p>content</p>",
            content_blocks=None,
        )
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = get_chapter_content(1)
            assert result["has_content"] is True
        finally:
            patcher.stop()

    def test_has_content_true_when_content_blocks_set(self):
        task = DailyTask(
            id=1,
            user_id="u",
            skill="Python",
            skill_id=1,
            newsletter=None,
            content_blocks='[{"type":"paragraph","content":"hi"}]',
        )
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = get_chapter_content(1)
            assert result["has_content"] is True
        finally:
            patcher.stop()

    def test_has_content_false_when_content_blocks_empty_string(self):
        task = DailyTask(
            id=1,
            user_id="u",
            skill="Python",
            skill_id=1,
            newsletter=None,
            content_blocks="",
        )
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = get_chapter_content(1)
            assert result["has_content"] is False
        finally:
            patcher.stop()

class TestAddBlocksToDb:
    def test_returns_true_for_empty_blocks_without_db_write(self):
        session = MagicMock()
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = add_blocks_to_db([], task_id=1)
            assert result is True
            session.add.assert_not_called()
        finally:
            patcher.stop()

    def test_returns_false_when_task_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            block = MagicMock()
            block.model_dump.return_value = {"type": "paragraph", "content": "hello"}
            result = add_blocks_to_db([block], task_id=999)
            assert result is False
        finally:
            patcher.stop()

    def test_stores_json_when_blocks_present(self):
        task = DailyTask(id=1, user_id="u", skill="Python", skill_id=1)
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            block = MagicMock()
            block.model_dump.return_value = {"type": "paragraph", "content": "hello"}
            result = add_blocks_to_db([block], task_id=1)
            assert result is True
            stored = json.loads(task.content_blocks)
            assert stored[0]["type"] == "paragraph"
        finally:
            patcher.stop()

class TestMarkTaskCompleted:
    def test_returns_false_when_task_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = mark_task_completed(999)
            assert result is False
        finally:
            patcher.stop()

    def test_marks_task_completed(self):
        task = DailyTask(id=1, user_id="u", skill="Python", skill_id=1, completed=False)
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = mark_task_completed(1)
            assert result is True
            assert task.completed is True
        finally:
            patcher.stop()

    def test_idempotent_when_already_completed(self):
        task = DailyTask(id=1, user_id="u", skill="Python", skill_id=1, completed=True)
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = mark_task_completed(1)
            assert result is True
        finally:
            patcher.stop()

class TestAddContentToDb:
    def test_returns_false_when_task_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = add_content_to_db("<p>html</p>", task_id=999)
            assert result is False
        finally:
            patcher.stop()

    def test_sanitizes_and_stores_html(self):
        task = DailyTask(id=1, user_id="u", skill="Python", skill_id=1)
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = add_content_to_db("<p>Safe</p><script>evil()</script>", task_id=1)
            assert result is True
            assert "<script>" not in task.newsletter
            assert "<p>" in task.newsletter
        finally:
            patcher.stop()
