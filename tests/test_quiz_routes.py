from unittest.mock import patch, MagicMock
import pytest
from models.skill import Skill
from models.quiz import Quiz
from models.quiz_attempt import QuizAttempt
from models.quiz_question import QuizQuestion

def _make_skill(user_id="1", days=30):
    return Skill(
        id=1,
        user_id=user_id,
        email="test@example.com",
        skill="Python",
        days=days,
        hours=2,
    )

def _make_quiz(quiz_id=1, skill_id=1, week=0, pass_score=60, status="available"):
    q = Quiz(id=quiz_id, skill_id=skill_id, week=week, pass_score=pass_score)
    q.status = status
    return q

def _make_question(id=1, correct="A"):
    q = MagicMock(spec=QuizQuestion)
    q.id = id
    q.position = id
    q.question = f"Question {id}"
    q.option_a = "Option A"
    q.option_b = "Option B"
    q.option_c = "Option C"
    q.option_d = "Option D"
    q.correct_option = correct
    q.explanation = "Explanation"
    q.topic = None
    return q

def _patch_quiz_session(session_mock):
    patcher = patch("controllers.quiz.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

class TestGetQuiz:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.get("/quiz/1")
        assert response.status_code == 401

    def test_skill_not_found_returns_404(self, auth_client, test_user):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_quiz_session(session)
        try:
            response = auth_client.get("/quiz/999")
        finally:
            patcher.stop()
        assert response.status_code == 404

    def test_not_owner_returns_403(self, auth_client, test_user):
        skill = _make_skill(user_id="999")
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            response = auth_client.get("/quiz/1")
        finally:
            patcher.stop()
        assert response.status_code == 403

    def test_quiz_not_generated_returns_404(self, auth_client, test_user):
        skill = _make_skill(user_id=str(test_user.id))
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with patch("controllers.quiz.quiz_service.get_quiz_by_week", return_value=None):
                response = auth_client.get("/quiz/1")
        finally:
            patcher.stop()
        assert response.status_code == 404

    def test_owner_with_quiz_returns_200(self, auth_client, test_user):
        skill = _make_skill(user_id=str(test_user.id))
        quiz = _make_quiz()
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
                response = auth_client.get("/quiz/1")
        finally:
            patcher.stop()
        assert response.status_code == 200
        data = response.json()
        assert data["quiz_id"] == 1
        assert "questions" in data

class TestSubmitQuiz:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.post("/quiz/1/submit", json={"answers": {}})
        assert response.status_code == 401

    def test_submit_correct_answers_returns_score(self, auth_client, test_user):
        skill = _make_skill(user_id=str(test_user.id))
        quiz = _make_quiz(pass_score=60)
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
            ):
                response = auth_client.post("/quiz/1/submit", json={"answers": {"1": "A"}})
        finally:
            patcher.stop()
        assert response.status_code == 200
        assert response.json()["score"] == 100
        assert response.json()["passed"] is True

    def test_invalid_question_id_returns_400(self, auth_client, test_user):
        skill = _make_skill(user_id=str(test_user.id))
        quiz = _make_quiz()
        q1 = _make_question(id=1, correct="A")

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
            ):
                response = auth_client.post("/quiz/1/submit", json={"answers": {"999": "A"}})
        finally:
            patcher.stop()
        assert response.status_code == 400

class TestGetAttempts:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.get("/quiz/1/attempts")
        assert response.status_code == 401

    def test_owner_returns_attempts(self, auth_client, test_user):
        skill = _make_skill(user_id=str(test_user.id))
        quiz = _make_quiz()
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with (
                patch("controllers.quiz.quiz_service.get_quiz_by_week", return_value=quiz),
                patch("controllers.quiz.quiz_service.get_attempts_for_quiz", return_value=[]),
            ):
                response = auth_client.get("/quiz/1/attempts")
        finally:
            patcher.stop()
        assert response.status_code == 200
        assert response.json()["quiz_id"] == 1
        assert response.json()["attempts"] == []

class TestGenerateQuiz:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.post("/quiz/1/generate")
        assert response.status_code == 401

    def test_skill_not_found_returns_404(self, auth_client, test_user):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_quiz_session(session)
        try:
            response = auth_client.post("/quiz/999/generate")
        finally:
            patcher.stop()
        assert response.status_code == 404

    def test_quiz_already_exists_returns_409(self, auth_client, test_user):
        skill = _make_skill(user_id=str(test_user.id))
        existing_quiz = _make_quiz()
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with patch(
                "controllers.quiz.quiz_service.get_quiz_by_week", return_value=existing_quiz
            ):
                response = auth_client.post("/quiz/1/generate")
        finally:
            patcher.stop()
        assert response.status_code == 409

    def test_no_topics_returns_400(self, auth_client, test_user):
        skill = _make_skill(user_id=str(test_user.id))
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with (
                patch("controllers.quiz.quiz_service.get_quiz_by_week", return_value=None),
                patch("controllers.quiz.get_weak_topics", return_value=[]),
                patch("controllers.quiz.get_forgotten_topics", return_value=[]),
                patch("controllers.quiz.quiz_service.get_topics_for_skill", return_value=[]),
            ):
                response = auth_client.post("/quiz/1/generate")
        finally:
            patcher.stop()
        assert response.status_code == 400

class TestResetFinalQuizRoute:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.delete("/quiz/1/final")
        assert response.status_code == 401

    def test_reset_final_quiz_not_found_returns_404(self, auth_client, test_user):
        skill = _make_skill(user_id=str(test_user.id))
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with patch("controllers.quiz.quiz_service.delete_final_quiz", return_value=False):
                response = auth_client.delete("/quiz/1/final")
        finally:
            patcher.stop()
        assert response.status_code == 404

    def test_reset_final_quiz_success_returns_200(self, auth_client, test_user):
        skill = _make_skill(user_id=str(test_user.id))
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with patch("controllers.quiz.quiz_service.delete_final_quiz", return_value=True):
                response = auth_client.delete("/quiz/1/final")
        finally:
            patcher.stop()
        assert response.status_code == 200
        assert response.json()["status"] == "success"
