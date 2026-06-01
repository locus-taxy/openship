from unittest.mock import MagicMock, patch
import pytest
from services.quiz import (
    all_chapters_complete,
    get_topics_for_skill,
    get_quiz_by_skill,
    get_quiz_with_questions,
    get_best_score,
    get_attempt_count,
    get_attempts_for_quiz,
)
from models.quiz import Quiz
from models.quiz_question import QuizQuestion
from models.quiz_attempt import QuizAttempt
from models.daily_task import DailyTask

def _patch_session(session_mock, module="services.quiz"):
    patcher = patch(f"{module}.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

class TestAllChaptersComplete:
    def test_returns_true_when_no_incomplete_tasks(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None  # no incomplete task found
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = all_chapters_complete(1)
            assert result is True
        finally:
            patcher.stop()

    def test_returns_false_when_incomplete_tasks_exist(self):
        incomplete_task = DailyTask(id=1, user_id="u", skill="Python", skill_id=1, completed=False)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = incomplete_task
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = all_chapters_complete(1)
            assert result is False
        finally:
            patcher.stop()

class TestGetTopicsForSkill:
    def test_returns_list_of_topic_strings(self):
        tasks = [
            MagicMock(topic="Variables"),
            MagicMock(topic="Loops"),
            MagicMock(topic="Functions"),
        ]
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = tasks
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_topics_for_skill(1)
            assert result == ["Variables", "Loops", "Functions"]
        finally:
            patcher.stop()

    def test_filters_out_none_topics(self):
        tasks = [MagicMock(topic="Variables"), MagicMock(topic=None)]
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = tasks
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_topics_for_skill(1)
            assert result == ["Variables"]
        finally:
            patcher.stop()

    def test_returns_empty_list_when_no_tasks(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_topics_for_skill(99)
            assert result == []
        finally:
            patcher.stop()

class TestGetQuizBySkill:
    def test_returns_quiz_when_found(self):
        quiz = Quiz(id=1, skill_id=1, difficulty="beginner", pass_score=60)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = quiz
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_quiz_by_skill(1)
            assert result is quiz
        finally:
            patcher.stop()

    def test_returns_none_when_not_found(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_quiz_by_skill(999)
            assert result is None
        finally:
            patcher.stop()

class TestGetQuizWithQuestions:
    def test_returns_none_and_empty_list_when_quiz_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            quiz, questions = get_quiz_with_questions(999)
            assert quiz is None
            assert questions == []
        finally:
            patcher.stop()

    def test_returns_quiz_and_questions(self):
        quiz = Quiz(id=1, skill_id=1, difficulty="beginner", pass_score=60)
        q1 = MagicMock(spec=QuizQuestion)
        q1.position = 1

        session = MagicMock()
        session.get.return_value = quiz
        exec_mock = MagicMock()
        exec_mock.all.return_value = [q1]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result_quiz, result_questions = get_quiz_with_questions(1)
            assert result_quiz is quiz
            assert len(result_questions) == 1
        finally:
            patcher.stop()

class TestGetBestScore:
    def test_returns_none_when_no_attempts(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_best_score(1, 1)
            assert result is None
        finally:
            patcher.stop()

    def test_returns_max_score(self):
        attempts = [MagicMock(score=60), MagicMock(score=80), MagicMock(score=70)]
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = attempts
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_best_score(1, 1)
            assert result == 80
        finally:
            patcher.stop()

class TestGetAttemptCount:
    def test_returns_zero_when_no_attempts(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_attempt_count(1, 1)
            assert result == 0
        finally:
            patcher.stop()

    def test_returns_correct_count(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [MagicMock(), MagicMock(), MagicMock()]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_attempt_count(1, 1)
            assert result == 3
        finally:
            patcher.stop()

class TestGetAttemptsForQuiz:
    def test_returns_attempts_list(self):
        attempts = [MagicMock(spec=QuizAttempt), MagicMock(spec=QuizAttempt)]
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = attempts
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_attempts_for_quiz(1, 1)
            assert len(result) == 2
        finally:
            patcher.stop()

    def test_returns_empty_list_when_none(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_attempts_for_quiz(999, 1)
            assert result == []
        finally:
            patcher.stop()
