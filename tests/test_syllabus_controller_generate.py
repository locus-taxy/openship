from unittest.mock import patch, MagicMock
import pytest
from fastapi import HTTPException
from controllers.syllabus import generate_syllabus, _auto_generate_quiz
from schemas.skill import GenerateSyllabusRequest
from models.user import User

def _make_user(user_id=1):
    return User(
        id=user_id,
        email="test@example.com",
        name="Test",
        is_active=True,
        hashed_password="$2b$hash",
        llm_provider_id=1,
    )

def _make_skill(**kwargs):
    d = {"days": 30, "hours": 2, "quiz_difficulty": "beginner"}
    d.update(kwargs)
    return d

class TestGenerateSyllabus:
    def test_raises_404_when_no_subscription(self):
        user = _make_user()
        with patch("controllers.syllabus.get_skill", return_value=None):
            with pytest.raises(HTTPException) as exc:
                generate_syllabus(GenerateSyllabusRequest(skill="Python"), user)
            assert exc.value.status_code == 404

    def test_raises_404_when_skill_id_not_found(self):
        user = _make_user()
        with (
            patch("controllers.syllabus.get_skill", return_value=_make_skill()),
            patch("controllers.syllabus.get_skill_id_by_email_and_skill", return_value=None),
        ):
            with pytest.raises(HTTPException) as exc:
                generate_syllabus(GenerateSyllabusRequest(skill="Python"), user)
            assert exc.value.status_code == 404

    def test_raises_500_when_llm_returns_none(self):
        user = _make_user()
        with (
            patch("controllers.syllabus.get_skill", return_value=_make_skill()),
            patch("controllers.syllabus.get_skill_id_by_email_and_skill", return_value=1),
            patch("controllers.syllabus.generate_syllabus_json", return_value=None),
            patch("controllers.syllabus.get_user_provider_name", return_value="gemini"),
            patch("controllers.syllabus.get_user_api_key", return_value="key"),
            patch("controllers.syllabus.get_user_model", return_value="gemini-flash"),
        ):
            with pytest.raises(HTTPException) as exc:
                generate_syllabus(GenerateSyllabusRequest(skill="Python"), user)
            assert exc.value.status_code == 500

    def test_raises_500_when_llm_returns_wrong_type(self):
        user = _make_user()
        with (
            patch("controllers.syllabus.get_skill", return_value=_make_skill()),
            patch("controllers.syllabus.get_skill_id_by_email_and_skill", return_value=1),
            patch("controllers.syllabus.generate_syllabus_json", return_value="not a list"),
            patch("controllers.syllabus.get_user_provider_name", return_value="gemini"),
            patch("controllers.syllabus.get_user_api_key", return_value="key"),
            patch("controllers.syllabus.get_user_model", return_value="gemini-flash"),
        ):
            with pytest.raises(HTTPException) as exc:
                generate_syllabus(GenerateSyllabusRequest(skill="Python"), user)
            assert exc.value.status_code == 500

    def test_raises_500_when_llm_returns_empty_list(self):
        user = _make_user()
        with (
            patch("controllers.syllabus.get_skill", return_value=_make_skill()),
            patch("controllers.syllabus.get_skill_id_by_email_and_skill", return_value=1),
            patch("controllers.syllabus.generate_syllabus_json", return_value=[]),
            patch("controllers.syllabus.get_user_provider_name", return_value="gemini"),
            patch("controllers.syllabus.get_user_api_key", return_value="key"),
            patch("controllers.syllabus.get_user_model", return_value="gemini-flash"),
        ):
            with pytest.raises(HTTPException) as exc:
                generate_syllabus(GenerateSyllabusRequest(skill="Python"), user)
            assert exc.value.status_code == 500

    def test_raises_500_when_store_fails(self):
        user = _make_user()
        syllabus_data = [{"month": 1, "weeks": []}]
        with (
            patch("controllers.syllabus.get_skill", return_value=_make_skill()),
            patch("controllers.syllabus.get_skill_id_by_email_and_skill", return_value=1),
            patch("controllers.syllabus.generate_syllabus_json", return_value=syllabus_data),
            patch("controllers.syllabus.store_syllabus_tasks", return_value=False),
            patch("controllers.syllabus.get_user_provider_name", return_value="gemini"),
            patch("controllers.syllabus.get_user_api_key", return_value="key"),
            patch("controllers.syllabus.get_user_model", return_value="gemini-flash"),
        ):
            with pytest.raises(HTTPException) as exc:
                generate_syllabus(GenerateSyllabusRequest(skill="Python"), user)
            assert exc.value.status_code == 500

    def test_success_without_provider_skips_thread(self):
        user = _make_user()
        syllabus_data = [{"month": 1, "weeks": []}]
        with (
            patch("controllers.syllabus.get_skill", return_value=_make_skill()),
            patch("controllers.syllabus.get_skill_id_by_email_and_skill", return_value=1),
            patch("controllers.syllabus.generate_syllabus_json", return_value=syllabus_data),
            patch("controllers.syllabus.store_syllabus_tasks", return_value=True),
            patch("controllers.syllabus.get_user_provider_name", return_value=None),
            patch("controllers.syllabus.get_user_api_key", return_value=None),
            patch("controllers.syllabus.get_user_model", return_value=None),
            patch("controllers.syllabus.threading") as mock_threading,
        ):
            result = generate_syllabus(GenerateSyllabusRequest(skill="Python"), user)
        assert result["status"] == "success"
        mock_threading.Thread.assert_not_called()

    def test_success_with_provider_starts_quiz_thread(self):
        user = _make_user()
        syllabus_data = [{"month": 1, "weeks": []}]
        with (
            patch("controllers.syllabus.get_skill", return_value=_make_skill()),
            patch("controllers.syllabus.get_skill_id_by_email_and_skill", return_value=1),
            patch("controllers.syllabus.generate_syllabus_json", return_value=syllabus_data),
            patch("controllers.syllabus.store_syllabus_tasks", return_value=True),
            patch("controllers.syllabus.get_user_provider_name", return_value="gemini"),
            patch("controllers.syllabus.get_user_api_key", return_value="api-key"),
            patch("controllers.syllabus.get_user_model", return_value="gemini-flash"),
            patch("controllers.syllabus.threading") as mock_threading,
        ):
            result = generate_syllabus(GenerateSyllabusRequest(skill="Python"), user)
        assert result["status"] == "success"
        mock_threading.Thread.assert_called_once()
        mock_threading.Thread.return_value.start.assert_called_once()

class TestAutoGenerateQuiz:
    def test_returns_early_when_quiz_already_exists(self):
        existing_quiz = MagicMock()
        with patch("controllers.syllabus.quiz_service") as mock_svc:
            mock_svc.get_quiz_by_skill.return_value = existing_quiz
            _auto_generate_quiz(1, "Python", "beginner", 30, "gemini", "key", "model")
            mock_svc.create_quiz.assert_not_called()

    def test_returns_early_when_no_topics(self):
        with patch("controllers.syllabus.quiz_service") as mock_svc:
            mock_svc.get_quiz_by_skill.return_value = None
            mock_svc.get_topics_for_skill.return_value = []
            _auto_generate_quiz(1, "Python", "beginner", 30, "gemini", "key", "model")
            mock_svc.create_quiz.assert_not_called()

    def test_returns_early_when_llm_returns_none(self):
        with (
            patch("controllers.syllabus.quiz_service") as mock_svc,
            patch("controllers.syllabus.generate_quiz", return_value=None),
        ):
            mock_svc.get_quiz_by_skill.return_value = None
            mock_svc.get_topics_for_skill.return_value = ["Variables", "Loops"]
            mock_svc.get_num_questions.return_value = 10
            _auto_generate_quiz(1, "Python", "beginner", 30, "gemini", "key", "model")
            mock_svc.create_quiz.assert_not_called()

    def test_creates_quiz_on_success(self):
        generated = MagicMock()
        generated.questions = [MagicMock(), MagicMock()]
        with (
            patch("controllers.syllabus.quiz_service") as mock_svc,
            patch("controllers.syllabus.generate_quiz", return_value=generated),
        ):
            mock_svc.get_quiz_by_skill.return_value = None
            mock_svc.get_topics_for_skill.return_value = ["Variables", "Loops"]
            mock_svc.get_num_questions.return_value = 10
            _auto_generate_quiz(1, "Python", "beginner", 30, "gemini", "key", "model")
            mock_svc.create_quiz.assert_called_once_with(1, "beginner", generated.questions)

    def test_handles_exception_without_raising(self):
        with patch("controllers.syllabus.quiz_service") as mock_svc:
            mock_svc.get_quiz_by_skill.side_effect = RuntimeError("DB down")
            # Should not raise
            _auto_generate_quiz(1, "Python", "beginner", 30, "gemini", "key", "model")
