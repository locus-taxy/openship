"""Tests for weekly quiz controller functions (generate, get, submit)."""

from unittest.mock import patch, MagicMock
import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from controllers.quiz import (
    generate_weekly_quiz_for_skill,
    get_weekly_quiz,
    submit_weekly_quiz,
    _generate_next_week,
)
from schemas.quiz import QuizSubmitRequest
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

def _make_skill(skill_id=1, user_id="1"):
    return Skill(
        id=skill_id, user_id=user_id, email="test@example.com", skill="Python", days=30, hours=2
    )

def _make_quiz(id=1, week=1, pass_score=60):
    q = Quiz(id=id, skill_id=1, week=week, pass_score=pass_score)
    q.status = "available"
    return q

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

def _patch_quiz_session(session_mock):
    patcher = patch("controllers.quiz.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

class TestGenerateWeeklyQuizForSkill:
    def test_raises_404_when_skill_not_found(self):
        user = _make_user()
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_quiz_session(session)
        try:
            with pytest.raises(HTTPException) as exc:
                generate_weekly_quiz_for_skill(999, week=1, current_user=user)
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_raises_403_when_not_owner(self):
        user = _make_user()
        skill = _make_skill(user_id="999")
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with pytest.raises(HTTPException) as exc:
                generate_weekly_quiz_for_skill(1, week=1, current_user=user)
            assert exc.value.status_code == 403
        finally:
            patcher.stop()

    def test_raises_409_when_quiz_already_exists(self):
        user = _make_user()
        skill = _make_skill(user_id="1")
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with patch(
                "controllers.quiz.quiz_service.get_quiz_by_week", return_value=_make_quiz(week=1)
            ):
                with pytest.raises(HTTPException) as exc:
                    generate_weekly_quiz_for_skill(1, week=1, current_user=user)
                assert exc.value.status_code == 409
        finally:
            patcher.stop()

    def test_raises_400_when_no_topics(self):
        user = _make_user()
        skill = _make_skill(user_id="1")
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with (
                patch("controllers.quiz.quiz_service.get_quiz_by_week", return_value=None),
                patch("controllers.quiz.quiz_service.get_topics_for_week", return_value=[]),
            ):
                with pytest.raises(HTTPException) as exc:
                    generate_weekly_quiz_for_skill(1, week=1, current_user=user)
                assert exc.value.status_code == 400
        finally:
            patcher.stop()

    def test_raises_502_when_llm_returns_none(self):
        user = _make_user()
        skill = _make_skill(user_id="1")
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with (
                patch("controllers.quiz.quiz_service.get_quiz_by_week", return_value=None),
                patch(
                    "controllers.quiz.quiz_service.get_topics_for_week", return_value=["Variables"]
                ),
                patch("controllers.quiz.generate_weekly_quiz", return_value=None),
                patch("controllers.quiz.get_user_provider_name", return_value="gemini"),
                patch("controllers.quiz.get_user_api_key", return_value="key"),
                patch("controllers.quiz.get_user_model", return_value="gemini-flash"),
            ):
                with pytest.raises(HTTPException) as exc:
                    generate_weekly_quiz_for_skill(1, week=1, current_user=user)
                assert exc.value.status_code == 502
        finally:
            patcher.stop()

    def test_raises_409_on_integrity_error(self):
        user = _make_user()
        skill = _make_skill(user_id="1")
        generated = MagicMock()
        generated.questions = [MagicMock()]
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
                patch(
                    "controllers.quiz.quiz_service.create_quiz",
                    side_effect=IntegrityError("", {}, Exception()),
                ),
            ):
                with pytest.raises(HTTPException) as exc:
                    generate_weekly_quiz_for_skill(1, week=1, current_user=user)
                assert exc.value.status_code == 409
        finally:
            patcher.stop()

    def test_success_returns_quiz_generate_response(self):
        user = _make_user()
        skill = _make_skill(user_id="1")
        generated = MagicMock()
        generated.questions = [MagicMock(), MagicMock()]
        created_quiz = MagicMock()
        created_quiz.id = 7
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
                    "controllers.quiz.quiz_service.get_topics_for_week",
                    return_value=["Variables", "Loops"],
                ),
                patch("controllers.quiz.generate_weekly_quiz", return_value=generated),
                patch("controllers.quiz.get_user_provider_name", return_value="gemini"),
                patch("controllers.quiz.get_user_api_key", return_value="key"),
                patch("controllers.quiz.get_user_model", return_value="gemini-flash"),
                patch("controllers.quiz.quiz_service.create_quiz", return_value=created_quiz),
            ):
                result = generate_weekly_quiz_for_skill(1, week=1, current_user=user)
            assert result.quiz_id == 7
            assert result.week == 1
            assert result.question_count == 2
        finally:
            patcher.stop()

class TestGetWeeklyQuiz:
    def test_raises_404_when_quiz_not_found(self):
        user = _make_user()
        skill = _make_skill(user_id="1")
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        try:
            with patch("controllers.quiz.quiz_service.get_quiz_by_week", return_value=None):
                with pytest.raises(HTTPException) as exc:
                    get_weekly_quiz(1, week=1, current_user=user)
                assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_returns_quiz_out_on_success(self):
        user = _make_user()
        skill = _make_skill(user_id="1")
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
                result = get_weekly_quiz(1, week=1, current_user=user)
            assert result.week == 1
            assert len(result.questions) == 1
        finally:
            patcher.stop()

class TestSubmitWeeklyQuiz:
    def test_raises_400_on_invalid_question_id(self):
        user = _make_user()
        skill = _make_skill(user_id="1")
        quiz = _make_quiz(week=1)
        q1 = _make_question(id=1)
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
                payload = QuizSubmitRequest(answers={999: "A"})
                with pytest.raises(HTTPException) as exc:
                    submit_weekly_quiz(1, week=1, payload=payload, current_user=user)
                assert exc.value.status_code == 400
        finally:
            patcher.stop()

    def test_success_returns_weekly_submit_response(self):
        user = _make_user()
        skill = _make_skill(user_id="1")
        quiz = _make_quiz(week=1)
        q1 = _make_question(id=1, correct="A", topic="Variables")
        attempt = MagicMock(spec=QuizAttempt)
        attempt.id = 10
        attempt.score = 80
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
                payload = QuizSubmitRequest(answers={1: "A"})
                result = submit_weekly_quiz(1, week=1, payload=payload, current_user=user)
            assert result.score == 80
            assert result.passed is True
            assert result.next_week_style == "balanced"
        finally:
            patcher.stop()

    def test_skips_bkt_update_when_no_topics(self):
        user = _make_user()
        skill = _make_skill(user_id="1")
        quiz = _make_quiz(week=1)
        q1 = _make_question(id=1, correct="A", topic=None)  # no topic
        attempt = MagicMock(spec=QuizAttempt)
        attempt.id = 11
        attempt.score = 60
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
                patch("controllers.quiz.update_topic_knowledge") as mock_bkt,
                patch("controllers.quiz.quiz_service.get_previous_best_score", return_value=50),
                patch("controllers.quiz.get_week_content_style", return_value="theory_first"),
                patch("controllers.quiz.sample_style", return_value="theory_first"),
                patch("controllers.quiz.update_arm"),
                patch("controllers.quiz.unlock_next_week", return_value=(0, False)),
                patch("controllers.quiz.quiz_service.get_topics_for_week", return_value=[]),
            ):
                payload = QuizSubmitRequest(answers={1: "A"})
                result = submit_weekly_quiz(1, week=1, payload=payload, current_user=user)
            mock_bkt.assert_not_called()
            assert result.next_week_style == "theory_first"
        finally:
            patcher.stop()

    def test_triggers_ml_generation_via_background_tasks(self):
        """When new_generated_weeks == next_week and background_tasks is provided, add_task is called."""
        user = _make_user()
        skill = _make_skill(user_id="1")
        skill.total_weeks = 4
        quiz = _make_quiz(week=1)
        q1 = _make_question(id=1, correct="A", topic="Variables")
        attempt = MagicMock(spec=QuizAttempt)
        attempt.id = 20
        attempt.score = 85
        attempt.passed = True
        session = MagicMock()
        session.get.return_value = skill
        patcher = _patch_quiz_session(session)
        background_tasks = MagicMock()
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
                patch(
                    "controllers.quiz.unlock_next_week", return_value=(2, True)
                ),  # week+1=2 newly unlocked
                patch("controllers.quiz.get_user_provider_name", return_value="gemini"),
                patch("controllers.quiz.get_user_api_key", return_value="key"),
                patch("controllers.quiz.get_user_model", return_value="gemini-flash"),
                patch("controllers.quiz.quiz_service.get_topics_for_week", return_value=[]),
            ):
                payload = QuizSubmitRequest(answers={1: "A"})
                result = submit_weekly_quiz(
                    1,
                    week=1,
                    payload=payload,
                    current_user=user,
                    background_tasks=background_tasks,
                )
            background_tasks.add_task.assert_called_once()
            assert result.next_week_unlocked == 2
        finally:
            patcher.stop()

    def test_triggers_ml_generation_directly_when_no_background_tasks(self):
        """When new_generated_weeks == next_week and background_tasks is None, _generate_next_week called."""
        user = _make_user()
        skill = _make_skill(user_id="1")
        skill.total_weeks = 4
        quiz = _make_quiz(week=1)
        q1 = _make_question(id=1, correct="A", topic="Loops")
        attempt = MagicMock(spec=QuizAttempt)
        attempt.id = 21
        attempt.score = 75
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
                patch("controllers.quiz.unlock_next_week", return_value=(2, True)),
                patch("controllers.quiz.get_user_provider_name", return_value="gemini"),
                patch("controllers.quiz.get_user_api_key", return_value="key"),
                patch("controllers.quiz.get_user_model", return_value="gemini-flash"),
                patch("controllers.quiz.quiz_service.get_topics_for_week", return_value=[]),
                patch("controllers.quiz._generate_next_week") as mock_gen,
            ):
                payload = QuizSubmitRequest(answers={1: "A"})
                submit_weekly_quiz(
                    1, week=1, payload=payload, current_user=user, background_tasks=None
                )
            mock_gen.assert_called_once()
        finally:
            patcher.stop()

class TestGenerateNextWeek:
    def _base_kwargs(self):
        return dict(
            skill_id=1,
            skill_name="Python",
            skill_days=28,
            skill_total_weeks=4,
            skill_hours=2,
            user_id_int=1,
            user_id_str="1",
            next_week=2,
            provider="gemini",
            api_key="key",
            model="gemini-flash",
        )

    def _prev_quiz_mock(self):
        """A mock quiz object for the previous week."""
        q = MagicMock()
        q.id = 99
        q.pass_score = 60
        return q

    def _patch_get_quiz_by_week(self, prev_quiz, next_week_quiz):
        """get_quiz_by_week is called twice: prev-week lookup then next-week existence check."""
        return patch(
            "controllers.quiz.quiz_service.get_quiz_by_week",
            side_effect=[prev_quiz, next_week_quiz],
        )

    def test_returns_none_when_daily_plan_is_none(self):
        """When generate_week_plan returns None, logs warning and returns early."""
        attempt = {"score": 80, "topic_scores": {"Loops": {"pct": 100}}}
        with (
            patch("controllers.quiz.get_weak_topics", return_value=[]),
            patch("controllers.quiz.get_forgotten_topics", return_value=[]),
            self._patch_get_quiz_by_week(self._prev_quiz_mock(), None),
            patch("controllers.quiz.quiz_service.get_latest_attempt_results", return_value=attempt),
            patch("controllers.quiz.calc_remediation_days", return_value=0),
            patch("controllers.quiz.get_max_day_for_week", return_value=7),
            patch("controllers.quiz.delete_week_tasks"),
            patch("controllers.quiz.generate_week_plan", return_value=None),
        ):
            result = _generate_next_week(**self._base_kwargs())
        assert result is None

    def test_stores_tasks_and_creates_quiz_when_topics_exist(self):
        """Full success path with a failed topic → targeted remediation."""
        daily_plan = [{"day": 8, "topic": "Classes", "task": "Learn OOP"}]
        generated_quiz = MagicMock()
        generated_quiz.questions = [MagicMock()]
        attempt = {"score": 40, "topic_scores": {"Variables": {"pct": 0}, "Loops": {"pct": 100}}}
        with (
            patch("controllers.quiz.get_weak_topics", return_value=["Variables"]),
            patch("controllers.quiz.get_forgotten_topics", return_value=[]),
            self._patch_get_quiz_by_week(self._prev_quiz_mock(), None),
            patch("controllers.quiz.quiz_service.get_latest_attempt_results", return_value=attempt),
            patch("controllers.quiz.calc_remediation_days", return_value=2),
            patch("controllers.quiz.get_max_day_for_week", return_value=7),
            patch("controllers.quiz.delete_week_tasks"),
            patch("controllers.quiz.generate_week_plan", return_value=daily_plan),
            patch("controllers.quiz.store_week_tasks"),
            patch("controllers.quiz.quiz_service.get_topics_for_week", return_value=["Classes"]),
            patch("controllers.quiz.generate_weekly_quiz", return_value=generated_quiz),
            patch("controllers.quiz.quiz_service.create_quiz") as mock_create,
        ):
            _generate_next_week(**self._base_kwargs())
        mock_create.assert_called_once()

    def test_skips_quiz_creation_when_quiz_already_exists(self):
        """If quiz already exists for next_week, does not call create_quiz."""
        daily_plan = [{"day": 8, "topic": "Classes", "task": "Learn OOP"}]
        existing_quiz = MagicMock()
        existing_quiz.id = 77
        existing_quiz.pass_score = 60
        attempt = {"score": 100, "topic_scores": {}}
        with (
            patch("controllers.quiz.get_weak_topics", return_value=[]),
            patch("controllers.quiz.get_forgotten_topics", return_value=[]),
            # first call returns prev-week quiz, second call returns the existing next-week quiz
            patch(
                "controllers.quiz.quiz_service.get_quiz_by_week",
                side_effect=[self._prev_quiz_mock(), existing_quiz],
            ),
            patch("controllers.quiz.quiz_service.get_latest_attempt_results", return_value=attempt),
            patch("controllers.quiz.calc_remediation_days", return_value=0),
            patch("controllers.quiz.get_max_day_for_week", return_value=7),
            patch("controllers.quiz.delete_week_tasks"),
            patch("controllers.quiz.generate_week_plan", return_value=daily_plan),
            patch("controllers.quiz.store_week_tasks", return_value=True),
            patch("controllers.quiz.quiz_service.get_topics_for_week", return_value=["Classes"]),
            patch("controllers.quiz.quiz_service.create_quiz") as mock_create,
        ):
            _generate_next_week(**self._base_kwargs())
        mock_create.assert_not_called()

    def test_falls_back_to_bkt_weak_topics_when_no_prev_quiz(self):
        """When there is no previous quiz at all, falls back to top-3 BKT weak topics."""
        daily_plan = [{"day": 8, "topic": "Classes", "task": "Learn OOP"}]
        with (
            patch("controllers.quiz.get_weak_topics", return_value=["A", "B", "C", "D"]),
            patch("controllers.quiz.get_forgotten_topics", return_value=[]),
            patch("controllers.quiz.quiz_service.get_quiz_by_week", return_value=None),
            patch("controllers.quiz.calc_remediation_days", return_value=0),
            patch("controllers.quiz.get_max_day_for_week", return_value=7),
            patch("controllers.quiz.delete_week_tasks"),
            patch("controllers.quiz.generate_week_plan", return_value=daily_plan) as mock_plan,
            patch("controllers.quiz.store_week_tasks"),
            patch("controllers.quiz.quiz_service.get_topics_for_week", return_value=[]),
        ):
            _generate_next_week(**self._base_kwargs())
        # weak_topics passed should be capped at top 3
        call_kwargs = mock_plan.call_args.kwargs
        assert call_kwargs["weak_topics"] == ["A", "B", "C"]

    def test_skips_quiz_generation_when_store_week_tasks_fails(self):
        """When store_week_tasks returns False, logs error and returns without creating quiz."""
        daily_plan = [{"day": 8, "topic": "Classes", "task": "Learn OOP"}]
        attempt = {"score": 80, "topic_scores": {"Loops": {"pct": 100}}}
        with (
            patch("controllers.quiz.get_weak_topics", return_value=[]),
            patch("controllers.quiz.get_forgotten_topics", return_value=[]),
            self._patch_get_quiz_by_week(self._prev_quiz_mock(), None),
            patch("controllers.quiz.quiz_service.get_latest_attempt_results", return_value=attempt),
            patch("controllers.quiz.calc_remediation_days", return_value=0),
            patch("controllers.quiz.get_max_day_for_week", return_value=7),
            patch("controllers.quiz.delete_week_tasks"),
            patch("controllers.quiz.generate_week_plan", return_value=daily_plan),
            patch("controllers.quiz.store_week_tasks", return_value=False),
            patch("controllers.quiz.quiz_service.create_quiz") as mock_create,
        ):
            _generate_next_week(**self._base_kwargs())
        mock_create.assert_not_called()

    def test_logs_error_on_exception(self):
        """Any exception in the body is caught and logged (does not propagate)."""
        with (patch("controllers.quiz.get_weak_topics", side_effect=RuntimeError("db down")),):
            # Should not raise
            _generate_next_week(**self._base_kwargs())
