from unittest.mock import MagicMock, patch
import pytest
from services.skill import (
    skill_exists,
    create_skill,
    get_skill,
    delete_skill,
    get_syllabus_detail,
    toggle_skill_share,
)
from models.skill import Skill

def _patch_session(session_mock):
    patcher = patch("services.skill.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

class TestSkillExists:
    def test_returns_true_when_found(self):
        skill = Skill(id=1, email="test@example.com", skill="Python")
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = skill
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = skill_exists("test@example.com", "Python")
            assert result is True
        finally:
            patcher.stop()

    def test_returns_false_when_not_found(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = skill_exists("test@example.com", "Rust")
            assert result is False
        finally:
            patcher.stop()

class TestCreateSkill:
    def test_normalizes_invalid_difficulty_to_beginner(self):
        session = MagicMock()
        patcher = _patch_session(session)
        try:
            create_skill("u1", "test@example.com", "Python", 30, 2, quiz_difficulty="invalid")
            added = session.add.call_args[0][0]
            assert added.quiz_difficulty == "beginner"
        finally:
            patcher.stop()

    def test_valid_difficulty_preserved(self):
        session = MagicMock()
        patcher = _patch_session(session)
        try:
            create_skill("u1", "test@example.com", "Python", 30, 2, quiz_difficulty="advanced")
            added = session.add.call_args[0][0]
            assert added.quiz_difficulty == "advanced"
        finally:
            patcher.stop()

    def test_returns_none_on_db_error(self):
        session = MagicMock()
        session.commit.side_effect = Exception("DB error")
        patcher = _patch_session(session)
        try:
            result = create_skill("u1", "test@example.com", "Python", 30, 2)
            assert result is None
        finally:
            patcher.stop()

class TestGetSkill:
    def test_returns_dict_when_found(self):
        skill = Skill(
            id=1,
            email="test@example.com",
            skill="Python",
            days=30,
            hours=2,
            quiz_difficulty="beginner",
        )
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = skill
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_skill("test@example.com", "Python")
            assert result is not None
            assert result["days"] == 30
        finally:
            patcher.stop()

    def test_returns_none_when_not_found(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_skill("test@example.com", "Rust")
            assert result is None
        finally:
            patcher.stop()

class TestDeleteSkill:
    def test_returns_false_when_skill_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            result = delete_skill(999, "user-1")
            assert result is False
        finally:
            patcher.stop()

    def test_returns_false_when_not_owner(self):
        skill = Skill(id=1, user_id="user-2", email="other@example.com", skill="Python")
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_session(session)
        try:
            result = delete_skill(1, "user-1")
            assert result is False
        finally:
            patcher.stop()

    def test_returns_true_for_owner(self):
        skill = Skill(id=1, user_id="user-1", email="test@example.com", skill="Python")
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_session(session)
        try:
            result = delete_skill(1, "user-1")
            assert result is True
            session.delete.assert_called_once_with(skill)
        finally:
            patcher.stop()

class TestToggleSkillShare:
    def test_returns_none_when_skill_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            result = toggle_skill_share(999, True, "user-1")
            assert result is None
        finally:
            patcher.stop()

    def test_returns_none_when_not_owner(self):
        skill = Skill(id=1, user_id="user-2", email="other@example.com", skill="Python")
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_session(session)
        try:
            result = toggle_skill_share(1, True, "user-1")
            assert result is None
        finally:
            patcher.stop()

    def test_enables_share(self):
        skill = Skill(
            id=1, user_id="user-1", email="test@example.com", skill="Python", share_enabled=False
        )
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_session(session)
        try:
            result = toggle_skill_share(1, True, "user-1")
            assert result is True
        finally:
            patcher.stop()

    def test_disables_share(self):
        skill = Skill(
            id=1, user_id="user-1", email="test@example.com", skill="Python", share_enabled=True
        )
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_session(session)
        try:
            result = toggle_skill_share(1, False, "user-1")
            assert result is False
        finally:
            patcher.stop()
