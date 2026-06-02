from unittest.mock import MagicMock, patch
import pytest
from services.skill import (
    get_syllabus_detail,
    get_all_syllabi,
    get_list_of_skill_ids,
    get_email_id_from_skill_id,
    get_skill_id_by_email_and_skill,
    get_public_syllabus_detail,
    update_skill_weeks,
    unlock_next_week,
)
from models.skill import Skill
from models.daily_task import DailyTask
from models.quiz import Quiz

def _patch_session(session_mock):
    patcher = patch("services.skill.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

class TestGetSyllabusDetail:
    def test_returns_none_when_skill_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            result = get_syllabus_detail(999)
            assert result is None
        finally:
            patcher.stop()

    def test_returns_structured_detail_for_valid_skill(self):
        skill = Skill(
            id=1,
            user_id="user-1",
            email="test@example.com",
            skill="Python",
            days=30,
            hours=2,
        )
        # Task in month 1, week 1, day 1
        task = DailyTask(
            id=10,
            user_id="user-1",
            skill="Python",
            skill_id=1,
            month=1,
            week=1,
            day=1,
            topic="Variables",
            task="Learn variables",
            hours=2,
            completed=False,
            newsletter=None,
            content_blocks=None,
        )
        session = MagicMock()
        session.get.return_value = skill
        # exec calls: (1) final quiz → .first() = None
        #             (2) weekly quizzes → .all() = []
        #             (3) daily tasks → .all() = [task]
        exec_mock = MagicMock()
        exec_mock.first.side_effect = [None]
        exec_mock.all.side_effect = [[], [task]]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_syllabus_detail(1)
            assert result is not None
            assert result["skill"] == "Python"
            assert "_user_id" in result
            assert "months" in result
            assert result["weekly_quiz_statuses"] == {}
        finally:
            patcher.stop()

class TestGetAllSyllabi:
    def test_returns_list_of_skill_dicts(self):
        session = MagicMock()
        # Simulate a row tuple: id, user_id, email, skill, days, hours, created_at,
        # total_tasks, completed_tasks, quiz_status, total_weeks, weekly_quizzes_passed
        row = (1, "user-1", "test@example.com", "Python", 30, 2, None, 5, 3, "not_generated", 4, 1)
        exec_mock = MagicMock()
        exec_mock.all.return_value = [row]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_all_syllabi(email="test@example.com")
            assert len(result) == 1
            assert result[0]["skill"] == "Python"
            assert result[0]["total_tasks"] == 5
            assert result[0]["completed_tasks"] == 3
            assert result[0]["total_weeks"] == 4
            assert result[0]["weekly_quizzes_passed"] == 1
        finally:
            patcher.stop()

    def test_returns_empty_list_when_none(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_all_syllabi(email="none@example.com")
            assert result == []
        finally:
            patcher.stop()

class TestGetListOfSkillIds:
    def test_returns_list_of_ids(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [1, 2, 3]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_list_of_skill_ids()
            assert result == [1, 2, 3]
        finally:
            patcher.stop()

class TestGetEmailIdFromSkillId:
    def test_returns_email_when_found(self):
        skill = Skill(id=1, user_id="u1", email="test@example.com", skill="Python")
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_session(session)
        try:
            result = get_email_id_from_skill_id(1)
            assert result == "test@example.com"
        finally:
            patcher.stop()

    def test_returns_none_when_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            result = get_email_id_from_skill_id(999)
            assert result is None
        finally:
            patcher.stop()

class TestGetSkillIdByEmailAndSkill:
    def test_returns_id_when_found(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = 42
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_skill_id_by_email_and_skill("test@example.com", "Python")
            assert result == 42
        finally:
            patcher.stop()

    def test_returns_none_when_not_found(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_skill_id_by_email_and_skill("test@example.com", "Rust")
            assert result is None
        finally:
            patcher.stop()

class TestGetPublicSyllabusDetail:
    def test_returns_none_when_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            result = get_public_syllabus_detail(999)
            assert result is None
        finally:
            patcher.stop()

    def test_returns_none_when_share_not_enabled(self):
        skill = Skill(
            id=1,
            user_id="u1",
            email="test@example.com",
            skill="Python",
            days=30,
            hours=2,
            share_enabled=False,
        )
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_session(session)
        try:
            result = get_public_syllabus_detail(1)
            assert result is None
        finally:
            patcher.stop()

    def test_returns_detail_when_share_enabled(self):
        skill = Skill(
            id=1,
            user_id="u1",
            email="test@example.com",
            skill="Python",
            days=30,
            hours=2,
            share_enabled=True,
        )
        session = MagicMock()
        session.get.return_value = skill
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_public_syllabus_detail(1)
            assert result is not None
            assert result["skill"] == "Python"
            assert "email" not in result
            assert "_user_id" not in result
        finally:
            patcher.stop()

class TestUpdateSkillWeeks:
    def test_updates_generated_and_total_weeks_when_skill_found(self):
        skill = Skill(
            id=1,
            user_id="u1",
            email="test@example.com",
            skill="Python",
            days=28,
            hours=2,
        )
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_session(session)
        try:
            update_skill_weeks(skill_id=1, generated_weeks=2, total_weeks=4)
            assert skill.generated_weeks == 2
            assert skill.total_weeks == 4
            session.add.assert_called_once_with(skill)
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_does_nothing_when_skill_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            update_skill_weeks(skill_id=999, generated_weeks=1, total_weeks=4)
            session.add.assert_not_called()
            session.commit.assert_not_called()
        finally:
            patcher.stop()

class TestUnlockNextWeek:
    def test_increments_generated_weeks_when_conditions_met(self):
        skill = Skill(
            id=1,
            user_id="u1",
            email="test@example.com",
            skill="Python",
            days=28,
            hours=2,
        )
        skill.total_weeks = 4
        skill.generated_weeks = 1
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_session(session)
        try:
            result = unlock_next_week(skill_id=1, completed_week=1)
            assert result == 2
            assert skill.generated_weeks == 2
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_returns_current_generated_weeks_when_not_matching(self):
        """No increment when generated_weeks != completed_week."""
        skill = Skill(
            id=1,
            user_id="u1",
            email="test@example.com",
            skill="Python",
            days=28,
            hours=2,
        )
        skill.total_weeks = 4
        skill.generated_weeks = 3  # already ahead
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_session(session)
        try:
            result = unlock_next_week(skill_id=1, completed_week=1)
            assert result == 3
            session.commit.assert_not_called()
        finally:
            patcher.stop()

    def test_returns_zero_when_skill_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            result = unlock_next_week(skill_id=999, completed_week=1)
            assert result == 0
        finally:
            patcher.stop()

    def test_does_not_increment_when_total_weeks_zero(self):
        """No-op for non-progressive courses (total_weeks == 0)."""
        skill = Skill(
            id=1,
            user_id="u1",
            email="test@example.com",
            skill="Python",
            days=28,
            hours=2,
        )
        skill.total_weeks = 0
        skill.generated_weeks = 1
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_session(session)
        try:
            result = unlock_next_week(skill_id=1, completed_week=1)
            assert result == 1
            session.commit.assert_not_called()
        finally:
            patcher.stop()
