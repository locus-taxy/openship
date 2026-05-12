from unittest.mock import MagicMock, patch
import pytest
from services.skill import (
    get_syllabus_detail,
    get_all_syllabi,
    get_list_of_skill_ids,
    get_email_id_from_skill_id,
    get_skill_id_by_email_and_skill,
    get_public_syllabus_detail,
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
            quiz_difficulty="beginner",
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
        exec_mock = MagicMock()
        # First exec call = quiz; second = tasks
        exec_mock.first.side_effect = [None, None]  # no quiz, then tasks iteration
        exec_mock.all.return_value = [task]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_syllabus_detail(1)
            assert result is not None
            assert result["skill"] == "Python"
            assert "_user_id" in result
            assert "months" in result
        finally:
            patcher.stop()

class TestGetAllSyllabi:
    def test_returns_list_of_skill_dicts(self):
        session = MagicMock()
        # Simulate a row tuple
        row = (1, "user-1", "test@example.com", "Python", 30, 2, None, 5, 3, "not_generated")
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
