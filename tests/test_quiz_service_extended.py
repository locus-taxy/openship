from unittest.mock import MagicMock, patch
import pytest
from services.quiz import (
    all_chapters_complete,
    get_topics_for_skill,
    get_quiz_by_skill,
    get_quiz_with_questions,
    get_all_quiz_questions,
    get_best_score,
    get_attempt_count,
    get_attempts_for_quiz,
    clear_all_quizzes,
    delete_final_quiz,
    get_topic_week_map,
    get_latest_attempt_results,
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
        quiz = Quiz(id=1, skill_id=1, pass_score=60)
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
        quiz = Quiz(id=1, skill_id=1, pass_score=60)
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

class TestClearAllQuizzes:
    def test_deletes_all_quizzes_for_skill(self):
        quiz1 = MagicMock(spec=Quiz)
        quiz2 = MagicMock(spec=Quiz)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [quiz1, quiz2]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            clear_all_quizzes(skill_id=1)
            session.delete.assert_any_call(quiz1)
            session.delete.assert_any_call(quiz2)
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_commits_even_when_no_quizzes(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            clear_all_quizzes(skill_id=99)
            session.delete.assert_not_called()
            session.commit.assert_called_once()
        finally:
            patcher.stop()

class TestDeleteFinalQuiz:
    def test_returns_false_when_no_final_quiz(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = delete_final_quiz(skill_id=1)
            assert result is False
            session.delete.assert_not_called()
        finally:
            patcher.stop()

    def test_returns_true_and_deletes_when_quiz_found(self):
        quiz = MagicMock(spec=Quiz)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = quiz
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = delete_final_quiz(skill_id=1)
            assert result is True
            session.delete.assert_called_once_with(quiz)
            session.commit.assert_called_once()
        finally:
            patcher.stop()

class TestGetTopicWeekMap:
    def test_returns_mapping_for_matching_topics(self):
        task1 = MagicMock(spec=DailyTask)
        task1.topic = "Variables"
        task1.week = 1
        task2 = MagicMock(spec=DailyTask)
        task2.topic = "Loops"
        task2.week = 2
        task3 = MagicMock(spec=DailyTask)
        task3.topic = "Functions"
        task3.week = 3

        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [task1, task2, task3]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_topic_week_map(skill_id=1, topics=["Variables", "Loops"])
            assert result == {"Variables": 1, "Loops": 2}
        finally:
            patcher.stop()

    def test_returns_empty_when_no_tasks(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_topic_week_map(skill_id=1, topics=["Variables"])
            assert result == {}
        finally:
            patcher.stop()

class TestGetLatestAttemptResults:
    def _make_question(self, id=1, topic="Variables", correct="A"):
        q = MagicMock(spec=QuizQuestion)
        q.id = id
        q.position = id
        q.topic = topic
        q.correct_option = correct
        q.explanation = "exp"
        return q

    def test_returns_none_when_no_attempt(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_latest_attempt_results(quiz_id=1, user_id=1)
            assert result is None
        finally:
            patcher.stop()

    def test_returns_result_with_correct_answer(self):
        attempt = MagicMock(spec=QuizAttempt)
        attempt.id = 1
        attempt.score = 80
        attempt.passed = True
        attempt.answers = {"1": "A"}
        attempt.created_at = None

        quiz = MagicMock(spec=Quiz)
        quiz.pass_score = 60

        q = self._make_question(id=1, topic="Variables", correct="A")

        session = MagicMock()
        attempt_exec = MagicMock()
        attempt_exec.first.return_value = attempt
        questions_exec = MagicMock()
        questions_exec.all.return_value = [q]
        session.exec.side_effect = [attempt_exec, questions_exec]
        session.get.return_value = quiz
        patcher = _patch_session(session)
        try:
            result = get_latest_attempt_results(quiz_id=1, user_id=1)
            assert result is not None
            assert result["score"] == 80
            assert result["passed"] is True
            assert result["results"][0]["is_correct"] is True
            assert result["topic_scores"]["Variables"]["pct"] == 100
        finally:
            patcher.stop()

    def test_returns_result_with_wrong_answer(self):
        attempt = MagicMock(spec=QuizAttempt)
        attempt.id = 2
        attempt.score = 0
        attempt.passed = False
        attempt.answers = {"1": "B"}
        attempt.created_at = None

        quiz = MagicMock(spec=Quiz)
        quiz.pass_score = 60

        q = self._make_question(id=1, topic="Loops", correct="A")

        session = MagicMock()
        attempt_exec = MagicMock()
        attempt_exec.first.return_value = attempt
        questions_exec = MagicMock()
        questions_exec.all.return_value = [q]
        session.exec.side_effect = [attempt_exec, questions_exec]
        session.get.return_value = quiz
        patcher = _patch_session(session)
        try:
            result = get_latest_attempt_results(quiz_id=1, user_id=1)
            assert result["results"][0]["is_correct"] is False
            assert result["topic_scores"]["Loops"]["pct"] == 0
        finally:
            patcher.stop()

class TestGetAllQuizQuestions:
    def test_returns_all_questions_without_sampling(self):
        q1 = MagicMock(spec=QuizQuestion)
        q2 = MagicMock(spec=QuizQuestion)
        q1.pool_group = 1
        q2.pool_group = 1

        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = [q1, q2]
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_all_quiz_questions(quiz_id=1)
            assert result == [q1, q2]
        finally:
            patcher.stop()

class TestGetQuizWithQuestionsNoPool:
    def test_returns_quiz_and_questions_when_no_pool_groups(self):
        quiz = MagicMock(spec=Quiz)
        q1 = MagicMock(spec=QuizQuestion)
        q1.pool_group = None
        q2 = MagicMock(spec=QuizQuestion)
        q2.pool_group = None

        session = MagicMock()
        quiz_get = MagicMock()
        session.get.return_value = quiz
        questions_exec = MagicMock()
        questions_exec.all.return_value = [q1, q2]
        session.exec.return_value = questions_exec
        patcher = _patch_session(session)
        try:
            result_quiz, result_questions = get_quiz_with_questions(quiz_id=1)
            assert result_quiz is quiz
            assert result_questions == [q1, q2]
        finally:
            patcher.stop()
