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
    get_total_cost_for_user,
    get_cost_summary_for_skill,
    get_max_day_for_week,
    get_canonical_topic_names,
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

    def test_stores_pricing_id_when_provided(self):
        task = DailyTask(id=1, user_id="u", skill="Python", skill_id=1)
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            block = MagicMock()
            block.model_dump.return_value = {"type": "paragraph", "content": "hi"}
            result = add_blocks_to_db([block], task_id=1, pricing_id=5)
            assert result is True
            assert task.pricing_id == 5
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

    def test_returns_false_on_negative_input_tokens(self):
        task = DailyTask(id=1, user_id="u", skill="Python", skill_id=1)
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = add_content_to_db("<p>html</p>", task_id=1, input_tokens=-1)
            assert result is False
        finally:
            patcher.stop()

    def test_returns_false_on_negative_output_tokens(self):
        task = DailyTask(id=1, user_id="u", skill="Python", skill_id=1)
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = add_content_to_db("<p>html</p>", task_id=1, output_tokens=-5)
            assert result is False
        finally:
            patcher.stop()

    def test_returns_false_on_negative_cost(self):
        task = DailyTask(id=1, user_id="u", skill="Python", skill_id=1)
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = add_content_to_db("<p>html</p>", task_id=1, generation_cost_usd=-0.01)
            assert result is False
        finally:
            patcher.stop()

    def test_stores_optional_fields_when_provided(self):
        task = DailyTask(id=1, user_id="u", skill="Python", skill_id=1)
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = add_content_to_db(
                "<p>html</p>",
                task_id=1,
                input_tokens=100,
                output_tokens=200,
                generation_cost_usd=0.001,
            )
            assert result is True
            assert task.input_tokens == 100
            assert task.output_tokens == 200
            assert task.generation_cost_usd == 0.001
        finally:
            patcher.stop()

    def test_stores_pricing_id_when_provided(self):
        task = DailyTask(id=1, user_id="u", skill="Python", skill_id=1)
        session = MagicMock()
        session.get.return_value = task
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = add_content_to_db("<p>html</p>", task_id=1, pricing_id=7)
            assert result is True
            assert task.pricing_id == 7
        finally:
            patcher.stop()

class TestGetTotalCostForUser:
    def _make_task(self, input_tokens, output_tokens, cost_usd):
        t = DailyTask(id=1, user_id="u1", skill="Python", skill_id=1)
        t.input_tokens = input_tokens
        t.output_tokens = output_tokens
        t.generation_cost_usd = cost_usd
        return t

    def test_aggregates_costs_across_all_tasks(self):
        task1 = self._make_task(100, 200, 0.01)
        task2 = self._make_task(50, 100, 0.005)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [task1, task2]
        session.exec.return_value = exec_mock
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = get_total_cost_for_user("u1")
            assert result["total_input_tokens"] == 150
            assert result["total_output_tokens"] == 300
            assert result["total_cost_usd"] == pytest.approx(0.015)
        finally:
            patcher.stop()

    def test_returns_zeros_when_no_tasks(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = get_total_cost_for_user("unknown-user")
            assert result["total_input_tokens"] == 0
            assert result["total_output_tokens"] == 0
            assert result["total_cost_usd"] == 0.0
        finally:
            patcher.stop()

    def test_handles_none_values(self):
        task = self._make_task(None, None, None)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [task]
        session.exec.return_value = exec_mock
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = get_total_cost_for_user("u1")
            assert result["total_input_tokens"] == 0
            assert result["total_cost_usd"] == 0.0
        finally:
            patcher.stop()

class TestGetCostSummaryForSkill:
    def _make_task(self, input_tokens, output_tokens, cost_usd):
        t = DailyTask(id=1, user_id="u1", skill="Python", skill_id=5)
        t.input_tokens = input_tokens
        t.output_tokens = output_tokens
        t.generation_cost_usd = cost_usd
        return t

    def test_aggregates_costs_for_skill(self):
        task = self._make_task(200, 400, 0.02)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [task]
        session.exec.return_value = exec_mock
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = get_cost_summary_for_skill(5)
            assert result["total_input_tokens"] == 200
            assert result["total_output_tokens"] == 400
            assert result["total_cost_usd"] == pytest.approx(0.02)
        finally:
            patcher.stop()

    def test_returns_zeros_for_empty_skill(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = get_cost_summary_for_skill(999)
            assert result["total_cost_usd"] == 0.0
        finally:
            patcher.stop()

class TestGetMaxDayForWeek:
    def test_returns_max_day_when_tasks_exist(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = 14
        session.exec.return_value = exec_mock
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = get_max_day_for_week(skill_id=1, week=2)
            assert result == 14
        finally:
            patcher.stop()

    def test_returns_zero_when_no_tasks(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = get_max_day_for_week(skill_id=1, week=99)
            assert result == 0
        finally:
            patcher.stop()

class TestGetCanonicalTopicNames:
    def test_returns_ordered_deduplicated_topics(self):
        t1 = DailyTask(id=1, user_id="u", skill="Python", skill_id=1, topic="Arrays")
        t2 = DailyTask(id=2, user_id="u", skill="Python", skill_id=1, topic="Loops")
        t3 = DailyTask(id=3, user_id="u", skill="Python", skill_id=1, topic="Arrays")
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [t1, t2, t3]
        session.exec.return_value = exec_mock
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = get_canonical_topic_names(skill_id=1)
            assert result == ["Arrays", "Loops"]
        finally:
            patcher.stop()

    def test_returns_empty_when_no_tasks(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session("services.daily_task.Session", session)
        try:
            result = get_canonical_topic_names(skill_id=99)
            assert result == []
        finally:
            patcher.stop()
