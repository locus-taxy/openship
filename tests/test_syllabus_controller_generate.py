from unittest.mock import patch
import pytest
from fastapi import HTTPException
from controllers.syllabus import generate_syllabus
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
    d = {"days": 30, "hours": 2}
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
            patch("controllers.syllabus.clear_syllabus_tasks"),
            patch("controllers.syllabus.clear_all_quizzes"),
            patch("controllers.syllabus.update_skill_weeks"),
            patch("controllers.syllabus.get_topics_for_week", return_value=[]),
        ):
            with pytest.raises(HTTPException) as exc:
                generate_syllabus(GenerateSyllabusRequest(skill="Python"), user)
            assert exc.value.status_code == 500

    def test_success_returns_ok(self):
        user = _make_user()
        syllabus_data = [{"month": 1, "weeks": []}]
        with (
            patch("controllers.syllabus.get_skill", return_value=_make_skill()),
            patch("controllers.syllabus.get_skill_id_by_email_and_skill", return_value=1),
            patch("controllers.syllabus.generate_syllabus_json", return_value=syllabus_data),
            patch("controllers.syllabus.store_syllabus_tasks", return_value=True),
            patch("controllers.syllabus.get_user_provider_name", return_value="gemini"),
            patch("controllers.syllabus.get_user_api_key", return_value="key"),
            patch("controllers.syllabus.get_user_model", return_value="gemini-flash"),
            patch("controllers.syllabus.clear_syllabus_tasks"),
            patch("controllers.syllabus.clear_all_quizzes"),
            patch("controllers.syllabus.update_skill_weeks"),
            patch("controllers.syllabus.get_topics_for_week", return_value=[]),
        ):
            result = generate_syllabus(GenerateSyllabusRequest(skill="Python"), user)
        assert result["status"] == "success"

    def test_success_without_provider_still_returns_ok(self):
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
            patch("controllers.syllabus.clear_syllabus_tasks"),
            patch("controllers.syllabus.clear_all_quizzes"),
            patch("controllers.syllabus.update_skill_weeks"),
            patch("controllers.syllabus.get_topics_for_week", return_value=[]),
        ):
            result = generate_syllabus(GenerateSyllabusRequest(skill="Python"), user)
        assert result["status"] == "success"

    def test_success_pregenerates_week1_quiz_when_topics_exist(self):
        """Covers lines 133-149: pre-generate week1 quiz path."""
        from unittest.mock import MagicMock

        user = _make_user()
        syllabus_data = [{"month": 1, "weeks": [{"week": 1, "daily_plan": []}]}]
        generated_quiz = MagicMock()
        generated_quiz.questions = [MagicMock()]
        with (
            patch("controllers.syllabus.get_skill", return_value=_make_skill()),
            patch("controllers.syllabus.get_skill_id_by_email_and_skill", return_value=1),
            patch("controllers.syllabus.generate_syllabus_json", return_value=syllabus_data),
            patch("controllers.syllabus.store_syllabus_tasks", return_value=True),
            patch("controllers.syllabus.get_user_provider_name", return_value="gemini"),
            patch("controllers.syllabus.get_user_api_key", return_value="key"),
            patch("controllers.syllabus.get_user_model", return_value="gemini-flash"),
            patch("controllers.syllabus.clear_syllabus_tasks"),
            patch("controllers.syllabus.clear_all_quizzes"),
            patch("controllers.syllabus.update_skill_weeks"),
            patch("controllers.syllabus.get_topics_for_week", return_value=["Variables", "Loops"]),
            patch("controllers.syllabus.generate_weekly_quiz", return_value=generated_quiz),
            patch("controllers.syllabus.create_quiz") as mock_create,
        ):
            result = generate_syllabus(GenerateSyllabusRequest(skill="Python"), user)
        assert result["status"] == "success"
        mock_create.assert_called_once()

    def test_success_when_week1_quiz_generate_returns_none(self):
        """Covers lines 142-147: generate_weekly_quiz returns None so create_quiz is skipped."""
        user = _make_user()
        syllabus_data = [{"month": 1, "weeks": []}]
        with (
            patch("controllers.syllabus.get_skill", return_value=_make_skill()),
            patch("controllers.syllabus.get_skill_id_by_email_and_skill", return_value=1),
            patch("controllers.syllabus.generate_syllabus_json", return_value=syllabus_data),
            patch("controllers.syllabus.store_syllabus_tasks", return_value=True),
            patch("controllers.syllabus.get_user_provider_name", return_value="gemini"),
            patch("controllers.syllabus.get_user_api_key", return_value="key"),
            patch("controllers.syllabus.get_user_model", return_value="gemini-flash"),
            patch("controllers.syllabus.clear_syllabus_tasks"),
            patch("controllers.syllabus.clear_all_quizzes"),
            patch("controllers.syllabus.update_skill_weeks"),
            patch("controllers.syllabus.get_topics_for_week", return_value=["Variables"]),
            patch("controllers.syllabus.generate_weekly_quiz", return_value=None),
            patch("controllers.syllabus.create_quiz") as mock_create,
        ):
            result = generate_syllabus(GenerateSyllabusRequest(skill="Python"), user)
        assert result["status"] == "success"
        mock_create.assert_not_called()

    def test_success_stores_is_technical_when_classified(self):
        """Covers line 140: update_skill_is_technical is called when domain classification succeeds."""
        user = _make_user()
        syllabus_data = [{"month": 1, "weeks": []}]
        with (
            patch("controllers.syllabus.get_skill", return_value=_make_skill()),
            patch("controllers.syllabus.get_skill_id_by_email_and_skill", return_value=1),
            patch("controllers.syllabus.generate_syllabus_json", return_value=syllabus_data),
            patch("controllers.syllabus.store_syllabus_tasks", return_value=True),
            patch("controllers.syllabus.get_user_provider_name", return_value="gemini"),
            patch("controllers.syllabus.get_user_api_key", return_value="key"),
            patch("controllers.syllabus.get_user_model", return_value="gemini-flash"),
            patch("controllers.syllabus.clear_syllabus_tasks"),
            patch("controllers.syllabus.clear_all_quizzes"),
            patch("controllers.syllabus.update_skill_weeks"),
            patch("controllers.syllabus.get_topics_for_week", return_value=[]),
            patch("controllers.syllabus.classify_skill_domain", return_value=True),
            patch("controllers.syllabus.update_skill_is_technical") as mock_update,
        ):
            result = generate_syllabus(GenerateSyllabusRequest(skill="Python"), user)
        assert result["status"] == "success"
        mock_update.assert_called_once_with(1, True)

    def test_success_when_week1_quiz_generation_raises(self):
        """Covers line 148-149: exception during quiz pre-generation is non-fatal."""
        user = _make_user()
        syllabus_data = [{"month": 1, "weeks": []}]
        with (
            patch("controllers.syllabus.get_skill", return_value=_make_skill()),
            patch("controllers.syllabus.get_skill_id_by_email_and_skill", return_value=1),
            patch("controllers.syllabus.generate_syllabus_json", return_value=syllabus_data),
            patch("controllers.syllabus.store_syllabus_tasks", return_value=True),
            patch("controllers.syllabus.get_user_provider_name", return_value="gemini"),
            patch("controllers.syllabus.get_user_api_key", return_value="key"),
            patch("controllers.syllabus.get_user_model", return_value="gemini-flash"),
            patch("controllers.syllabus.clear_syllabus_tasks"),
            patch("controllers.syllabus.clear_all_quizzes"),
            patch("controllers.syllabus.update_skill_weeks"),
            patch("controllers.syllabus.get_topics_for_week", side_effect=RuntimeError("db error")),
        ):
            result = generate_syllabus(GenerateSyllabusRequest(skill="Python"), user)
        assert result["status"] == "success"
