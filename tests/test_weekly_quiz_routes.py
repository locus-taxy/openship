"""Route-level tests for the weekly quiz endpoints."""

from unittest.mock import patch, MagicMock
import pytest
from models.skill import Skill
from models.quiz import Quiz
from models.quiz_question import QuizQuestion

def _make_skill(user_id="1"):
    return Skill(id=1, user_id=user_id, email="test@example.com", skill="Python", days=30, hours=2)

def _make_quiz(week=1, pass_score=60):
    q = Quiz(id=1, skill_id=1, week=week, pass_score=pass_score)
    q.status = "available"
    return q

def _make_question(id=1, correct="A"):
    q = MagicMock(spec=QuizQuestion)
    q.id = id
    q.position = id
    q.question = f"Q{id}"
    q.option_a = q.option_b = q.option_c = q.option_d = "opt"
    q.correct_option = correct
    q.explanation = "exp"
    q.topic = "Variables"
    return q

def _patch_quiz_session(session_mock):
    patcher = patch("controllers.quiz.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

class TestGenerateWeeklyQuizRoute:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.post("/quiz/1/week/1/generate")
        assert response.status_code == 401

    def test_success_returns_200(self, auth_client, test_user):
        skill = _make_skill(user_id=str(test_user.id))
        generated = MagicMock()
        generated.questions = [MagicMock(), MagicMock()]
        created_quiz = MagicMock()
        created_quiz.id = 5
        created_quiz.week = 1
        created_quiz.status = "available"
        created_quiz.pass_score = 60
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with (
                patch("controllers.quiz.quiz_service.get_quiz_by_week", return_value=None),
                patch(
                    "controllers.quiz.quiz_service.get_topics_for_week", return_value=["Variables"]
                ),
                patch("controllers.quiz.generate_weekly_quiz", return_value=generated),
                patch("controllers.quiz.get_user_provider_name", return_value="gemini"),
                patch("controllers.quiz.get_user_api_key", return_value="key"),
                patch("controllers.quiz.get_user_model", return_value="gemini-flash"),
                patch("controllers.quiz.quiz_service.create_quiz", return_value=created_quiz),
            ):
                response = auth_client.post("/quiz/1/week/1/generate")
        finally:
            patcher.stop()
        assert response.status_code == 200
        data = response.json()
        assert data["week"] == 1
        assert data["question_count"] == 2

class TestGetWeeklyQuizRoute:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.get("/quiz/1/week/1")
        assert response.status_code == 401

    def test_returns_200_with_quiz_data(self, auth_client, test_user):
        skill = _make_skill(user_id=str(test_user.id))
        quiz = _make_quiz(week=1)
        questions = [_make_question(id=1)]
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with (
                patch("controllers.quiz.quiz_service.get_quiz_by_week", return_value=quiz),
                patch(
                    "controllers.quiz.quiz_service.get_quiz_with_questions",
                    return_value=(quiz, questions),
                ),
                patch("controllers.quiz.quiz_service.get_best_score", return_value=None),
                patch("controllers.quiz.quiz_service.get_attempt_count", return_value=0),
            ):
                response = auth_client.get("/quiz/1/week/1")
        finally:
            patcher.stop()
        assert response.status_code == 200
        data = response.json()
        assert data["week"] == 1
        assert "questions" in data

class TestSubmitWeeklyQuizRoute:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.post("/quiz/1/week/1/submit", json={"answers": {}})
        assert response.status_code == 401

    def test_correct_answer_returns_200(self, auth_client, test_user):
        from models.quiz_attempt import QuizAttempt

        skill = _make_skill(user_id=str(test_user.id))
        quiz = _make_quiz(week=1)
        q1 = _make_question(id=1, correct="A")
        attempt = MagicMock(spec=QuizAttempt)
        attempt.id = 1
        attempt.score = 100
        attempt.passed = True
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with (
                patch("controllers.quiz.quiz_service.get_quiz_by_week", return_value=quiz),
                patch(
                    "controllers.quiz.quiz_service.get_all_quiz_questions",
                    return_value=[q1],
                ),
                patch("controllers.quiz.quiz_service.record_attempt", return_value=attempt),
                patch("controllers.quiz.update_topic_knowledge"),
                patch("controllers.quiz.quiz_service.get_previous_best_score", return_value=None),
                patch("controllers.quiz.get_week_content_style", return_value="balanced"),
                patch("controllers.quiz.sample_style", return_value="balanced"),
                patch("controllers.quiz.update_arm"),
                patch("controllers.quiz.unlock_next_week", return_value=(0, False)),
                patch("controllers.quiz.quiz_service.get_topics_for_week", return_value=[]),
            ):
                response = auth_client.post("/quiz/1/week/1/submit", json={"answers": {"1": "A"}})
        finally:
            patcher.stop()
        assert response.status_code == 200
        data = response.json()
        assert data["score"] == 100
        assert data["passed"] is True
        assert "next_week_style" in data
