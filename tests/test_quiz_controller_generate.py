from unittest.mock import patch, MagicMock
import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from controllers.quiz import generate_quiz_for_skill
from models.user import User
from models.skill import Skill

def _make_user(user_id=1):
    return User(
        id=user_id,
        email="test@example.com",
        name="Test",
        is_active=True,
        hashed_password="$2b$hash",
        llm_provider_id=1,
    )

def _make_skill(skill_id=1, user_id="1", days=30):
    return Skill(
        id=skill_id,
        user_id=user_id,
        email="test@example.com",
        skill="Python",
        days=days,
        hours=2,
        quiz_difficulty="beginner",
    )

class TestGenerateQuizForSkill:
    def test_raises_409_when_quiz_already_exists(self):
        user = _make_user()
        skill = _make_skill()
        with (
            patch("controllers.quiz.Session") as mock_session_cls,
            patch("controllers.quiz.quiz_service") as mock_svc,
        ):
            session = MagicMock()
            session.get.return_value = skill
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_svc.get_quiz_by_skill.return_value = MagicMock()  # already exists
            with pytest.raises(HTTPException) as exc:
                generate_quiz_for_skill(1, user)
            assert exc.value.status_code == 409

    def test_raises_400_when_no_topics(self):
        user = _make_user()
        skill = _make_skill()
        with (
            patch("controllers.quiz.Session") as mock_session_cls,
            patch("controllers.quiz.quiz_service") as mock_svc,
        ):
            session = MagicMock()
            session.get.return_value = skill
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_svc.get_quiz_by_skill.return_value = None
            mock_svc.get_topics_for_skill.return_value = []
            with pytest.raises(HTTPException) as exc:
                generate_quiz_for_skill(1, user)
            assert exc.value.status_code == 400

    def test_raises_502_when_llm_returns_none(self):
        user = _make_user()
        skill = _make_skill()
        with (
            patch("controllers.quiz.Session") as mock_session_cls,
            patch("controllers.quiz.quiz_service") as mock_svc,
            patch("controllers.quiz.generate_quiz", return_value=None),
            patch("controllers.quiz.get_user_provider_name", return_value="gemini"),
            patch("controllers.quiz.get_user_api_key", return_value="key"),
            patch("controllers.quiz.get_user_model", return_value="gemini-flash"),
        ):
            session = MagicMock()
            session.get.return_value = skill
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_svc.get_quiz_by_skill.return_value = None
            mock_svc.get_topics_for_skill.return_value = ["Variables", "Loops"]
            mock_svc.get_num_questions.return_value = 10
            with pytest.raises(HTTPException) as exc:
                generate_quiz_for_skill(1, user)
            assert exc.value.status_code == 502

    def test_raises_409_on_integrity_error(self):
        user = _make_user()
        skill = _make_skill()
        generated = MagicMock()
        generated.questions = [MagicMock()]
        with (
            patch("controllers.quiz.Session") as mock_session_cls,
            patch("controllers.quiz.quiz_service") as mock_svc,
            patch("controllers.quiz.generate_quiz", return_value=generated),
            patch("controllers.quiz.get_user_provider_name", return_value="gemini"),
            patch("controllers.quiz.get_user_api_key", return_value="key"),
            patch("controllers.quiz.get_user_model", return_value="gemini-flash"),
        ):
            session = MagicMock()
            session.get.return_value = skill
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_svc.get_quiz_by_skill.return_value = None
            mock_svc.get_topics_for_skill.return_value = ["Variables"]
            mock_svc.get_num_questions.return_value = 10
            mock_svc.create_quiz.side_effect = IntegrityError("", {}, Exception())
            with pytest.raises(HTTPException) as exc:
                generate_quiz_for_skill(1, user)
            assert exc.value.status_code == 409

    def test_success_returns_quiz_generate_response(self):
        user = _make_user()
        skill = _make_skill()
        generated = MagicMock()
        generated.questions = [MagicMock(), MagicMock()]
        created_quiz = MagicMock()
        created_quiz.id = 42
        created_quiz.status = "available"
        with (
            patch("controllers.quiz.Session") as mock_session_cls,
            patch("controllers.quiz.quiz_service") as mock_svc,
            patch("controllers.quiz.generate_quiz", return_value=generated),
            patch("controllers.quiz.get_user_provider_name", return_value="gemini"),
            patch("controllers.quiz.get_user_api_key", return_value="key"),
            patch("controllers.quiz.get_user_model", return_value="gemini-flash"),
        ):
            session = MagicMock()
            session.get.return_value = skill
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_svc.get_quiz_by_skill.return_value = None
            mock_svc.get_topics_for_skill.return_value = ["Variables", "Loops"]
            mock_svc.get_num_questions.return_value = 10
            mock_svc.create_quiz.return_value = created_quiz
            result = generate_quiz_for_skill(1, user)
        assert result.quiz_id == 42
        assert result.question_count == 2
