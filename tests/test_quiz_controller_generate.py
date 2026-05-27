from unittest.mock import patch, MagicMock
import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from controllers.quiz import (
    generate_quiz_for_skill,
    submit_quiz,
    reset_final_quiz,
    get_latest_attempt,
    get_weekly_latest_attempt,
)
from models.user import User
from models.skill import Skill
from models.quiz import Quiz
from models.quiz_question import QuizQuestion
from models.quiz_attempt import QuizAttempt

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
            mock_svc.get_quiz_by_week.return_value = MagicMock()  # already exists
            with pytest.raises(HTTPException) as exc:
                generate_quiz_for_skill(1, user)
            assert exc.value.status_code == 409

    def test_raises_400_when_no_topics(self):
        user = _make_user()
        skill = _make_skill()
        with (
            patch("controllers.quiz.Session") as mock_session_cls,
            patch("controllers.quiz.quiz_service") as mock_svc,
            patch("controllers.quiz.get_weak_topics", return_value=[]),
            patch("controllers.quiz.get_forgotten_topics", return_value=[]),
        ):
            session = MagicMock()
            session.get.return_value = skill
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_svc.get_quiz_by_week.return_value = None
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
            patch("controllers.quiz.get_weak_topics", return_value=["Loops"]),
            patch("controllers.quiz.get_forgotten_topics", return_value=[]),
            patch("controllers.quiz.generate_final_quiz", return_value=None),
            patch("controllers.quiz.get_user_provider_name", return_value="gemini"),
            patch("controllers.quiz.get_user_api_key", return_value="key"),
            patch("controllers.quiz.get_user_model", return_value="gemini-flash"),
        ):
            session = MagicMock()
            session.get.return_value = skill
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_svc.get_quiz_by_week.return_value = None
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
            patch("controllers.quiz.get_weak_topics", return_value=["Loops"]),
            patch("controllers.quiz.get_forgotten_topics", return_value=[]),
            patch("controllers.quiz.generate_final_quiz", return_value=generated),
            patch("controllers.quiz.get_user_provider_name", return_value="gemini"),
            patch("controllers.quiz.get_user_api_key", return_value="key"),
            patch("controllers.quiz.get_user_model", return_value="gemini-flash"),
        ):
            session = MagicMock()
            session.get.return_value = skill
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_svc.get_quiz_by_week.return_value = None
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
        created_quiz.week = 0
        created_quiz.status = "available"
        created_quiz.pass_score = 70
        with (
            patch("controllers.quiz.Session") as mock_session_cls,
            patch("controllers.quiz.quiz_service") as mock_svc,
            patch("controllers.quiz.get_weak_topics", return_value=["Loops"]),
            patch("controllers.quiz.get_forgotten_topics", return_value=[]),
            patch("controllers.quiz.generate_final_quiz", return_value=generated),
            patch("controllers.quiz.get_user_provider_name", return_value="gemini"),
            patch("controllers.quiz.get_user_api_key", return_value="key"),
            patch("controllers.quiz.get_user_model", return_value="gemini-flash"),
        ):
            session = MagicMock()
            session.get.return_value = skill
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_svc.get_quiz_by_week.return_value = None
            mock_svc.get_num_questions.return_value = 10
            mock_svc.create_quiz.return_value = created_quiz
            result = generate_quiz_for_skill(1, user)
        assert result.quiz_id == 42
        assert result.question_count == 2
        assert result.week == 0

def _patch_quiz_session(session_mock):
    patcher = patch("controllers.quiz.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

def _make_question(id=1, correct="A", topic="Variables"):
    q = MagicMock(spec=QuizQuestion)
    q.id = id
    q.position = id
    q.question = f"Q{id}"
    q.option_a = q.option_b = q.option_c = q.option_d = "opt"
    q.correct_option = correct
    q.explanation = "exp"
    q.topic = topic
    return q

class TestResetFinalQuiz:
    def test_raises_404_when_no_final_quiz(self):
        """reset_final_quiz raises 404 when delete_final_quiz returns False."""
        user = _make_user()
        skill = _make_skill()
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with patch("controllers.quiz.quiz_service.delete_final_quiz", return_value=False):
                with pytest.raises(HTTPException) as exc:
                    reset_final_quiz(1, current_user=user)
                assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_returns_success_when_quiz_deleted(self):
        """reset_final_quiz returns success dict when delete_final_quiz returns True."""
        user = _make_user()
        skill = _make_skill()
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with patch("controllers.quiz.quiz_service.delete_final_quiz", return_value=True):
                result = reset_final_quiz(1, current_user=user)
            assert result["status"] == "success"
        finally:
            patcher.stop()

class TestSubmitQuizBkt:
    def test_calls_bkt_update_when_questions_have_topics(self):
        """submit_quiz calls update_topic_knowledge when bkt_inputs is non-empty."""
        user = _make_user()
        skill = _make_skill()
        quiz = Quiz(id=5, skill_id=1, week=0, pass_score=70)
        quiz.status = "available"
        q1 = _make_question(id=1, correct="A", topic="Variables")
        attempt = MagicMock(spec=QuizAttempt)
        attempt.id = 30
        attempt.score = 80
        attempt.passed = True
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with (
                patch("controllers.quiz.quiz_service.get_quiz_by_week", return_value=quiz),
                patch(
                    "controllers.quiz.quiz_service.get_quiz_with_questions",
                    return_value=(quiz, [q1]),
                ),
                patch("controllers.quiz.quiz_service.record_attempt", return_value=attempt),
                patch("controllers.quiz.update_topic_knowledge") as mock_bkt,
            ):
                from schemas.quiz import QuizSubmitRequest

                payload = QuizSubmitRequest(answers={1: "A"})
                result = submit_quiz(1, payload=payload, current_user=user)
            mock_bkt.assert_called_once_with(1, user.id, [(q1.topic, 0, True)])
            assert result.score == 80
        finally:
            patcher.stop()

    def test_skips_bkt_update_when_no_topics(self):
        """submit_quiz does not call update_topic_knowledge when no questions have topics."""
        user = _make_user()
        skill = _make_skill()
        quiz = Quiz(id=6, skill_id=1, week=0, pass_score=70)
        quiz.status = "available"
        q1 = _make_question(id=1, correct="B", topic=None)
        attempt = MagicMock(spec=QuizAttempt)
        attempt.id = 31
        attempt.score = 50
        attempt.passed = False
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with (
                patch("controllers.quiz.quiz_service.get_quiz_by_week", return_value=quiz),
                patch(
                    "controllers.quiz.quiz_service.get_quiz_with_questions",
                    return_value=(quiz, [q1]),
                ),
                patch("controllers.quiz.quiz_service.record_attempt", return_value=attempt),
                patch("controllers.quiz.update_topic_knowledge") as mock_bkt,
            ):
                from schemas.quiz import QuizSubmitRequest

                payload = QuizSubmitRequest(answers={1: "B"})
                result = submit_quiz(1, payload=payload, current_user=user)
            mock_bkt.assert_not_called()
            assert result.passed is False
        finally:
            patcher.stop()

class TestGetLatestAttempt:
    def test_raises_404_when_no_attempt_data(self):
        user = _make_user()
        skill = _make_skill()
        quiz = Quiz(id=1, skill_id=1, week=0, pass_score=60)
        quiz.status = "available"
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with (
                patch("controllers.quiz.quiz_service.get_quiz_by_week", return_value=quiz),
                patch(
                    "controllers.quiz.quiz_service.get_latest_attempt_results", return_value=None
                ),
            ):
                with pytest.raises(HTTPException) as exc:
                    get_latest_attempt(skill_id=1, current_user=user)
                assert exc.value.status_code == 404
        finally:
            patcher.stop()

class TestGetWeeklyLatestAttempt:
    def test_raises_404_when_no_attempt_data(self):
        user = _make_user()
        skill = _make_skill()
        quiz = Quiz(id=2, skill_id=1, week=1, pass_score=60)
        quiz.status = "available"
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with (
                patch("controllers.quiz.quiz_service.get_quiz_by_week", return_value=quiz),
                patch(
                    "controllers.quiz.quiz_service.get_latest_attempt_results", return_value=None
                ),
            ):
                with pytest.raises(HTTPException) as exc:
                    get_weekly_latest_attempt(skill_id=1, week=1, current_user=user)
                assert exc.value.status_code == 404
        finally:
            patcher.stop()
