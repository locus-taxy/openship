from unittest.mock import MagicMock, patch
import pytest
from services.quiz import get_num_questions, record_attempt
from models.quiz import Quiz, WEEKLY_PASS_SCORE, FINAL_PASS_SCORE
from models.quiz_question import QuizQuestion

class TestGetNumQuestions:
    def test_30_days_returns_10(self):
        assert get_num_questions(30) == 10

    def test_less_than_30_days_returns_10(self):
        assert get_num_questions(15) == 10
        assert get_num_questions(1) == 10

    def test_31_days_returns_12(self):
        assert get_num_questions(31) == 12

    def test_60_days_returns_12(self):
        assert get_num_questions(60) == 12

    def test_61_days_returns_15(self):
        assert get_num_questions(61) == 15

    def test_90_days_returns_15(self):
        assert get_num_questions(90) == 15

    def test_large_days_returns_15(self):
        assert get_num_questions(180) == 15

class TestPassScores:
    def test_weekly_pass_score_is_60(self):
        assert WEEKLY_PASS_SCORE == 60

    def test_final_pass_score_is_70(self):
        assert FINAL_PASS_SCORE == 70

class TestRecordAttempt:
    def _make_questions(self, correct_options):
        questions = []
        for i, opt in enumerate(correct_options):
            q = MagicMock(spec=QuizQuestion)
            q.id = i + 1
            q.correct_option = opt
            questions.append(q)
        return questions

    def _make_quiz(self, pass_score=60):
        quiz = MagicMock(spec=Quiz)
        quiz.id = 1
        quiz.pass_score = pass_score
        return quiz

    @patch("services.quiz.Session")
    def test_all_correct_score_100(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = session
        mock_session_cls.return_value.__exit__.return_value = False
        session.get.return_value = self._make_quiz()

        questions = self._make_questions(["A", "B", "C"])
        answers = {1: "A", 2: "B", 3: "C"}
        quiz = self._make_quiz(pass_score=60)

        attempt = record_attempt(quiz, 1, answers, questions)
        assert attempt.score == 100

    @patch("services.quiz.Session")
    def test_all_wrong_score_0(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = session
        mock_session_cls.return_value.__exit__.return_value = False
        session.get.return_value = self._make_quiz()

        questions = self._make_questions(["A", "B", "C"])
        answers = {1: "D", 2: "D", 3: "D"}
        quiz = self._make_quiz(pass_score=60)

        attempt = record_attempt(quiz, 1, answers, questions)
        assert attempt.score == 0

    @patch("services.quiz.Session")
    def test_half_correct_score_50(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = session
        mock_session_cls.return_value.__exit__.return_value = False
        session.get.return_value = self._make_quiz()

        questions = self._make_questions(["A", "B"])
        answers = {1: "A", 2: "D"}
        quiz = self._make_quiz(pass_score=60)

        attempt = record_attempt(quiz, 1, answers, questions)
        assert attempt.score == 50

    @patch("services.quiz.Session")
    def test_passing_score_sets_passed_true(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = session
        mock_session_cls.return_value.__exit__.return_value = False
        session.get.return_value = self._make_quiz(pass_score=60)

        questions = self._make_questions(["A", "B", "C", "D"])
        answers = {1: "A", 2: "B", 3: "C", 4: "D"}
        quiz = self._make_quiz(pass_score=60)

        attempt = record_attempt(quiz, 1, answers, questions)
        assert attempt.passed is True

    @patch("services.quiz.Session")
    def test_failing_score_sets_passed_false(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = session
        mock_session_cls.return_value.__exit__.return_value = False
        session.get.return_value = self._make_quiz(pass_score=70)

        questions = self._make_questions(["A", "B", "C"])
        answers = {1: "A", 2: "D", 3: "D"}  # 1/3 = 33%
        quiz = self._make_quiz(pass_score=70)

        attempt = record_attempt(quiz, 1, answers, questions)
        assert attempt.passed is False

    @patch("services.quiz.Session")
    def test_answers_are_case_insensitive(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = session
        mock_session_cls.return_value.__exit__.return_value = False
        session.get.return_value = self._make_quiz()

        questions = self._make_questions(["A"])
        answers = {1: "a"}  # lowercase
        quiz = self._make_quiz(pass_score=60)

        attempt = record_attempt(quiz, 1, answers, questions)
        assert attempt.score == 100

    @patch("services.quiz.Session")
    def test_empty_questions_score_0(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = session
        mock_session_cls.return_value.__exit__.return_value = False

        quiz = self._make_quiz(pass_score=60)
        attempt = record_attempt(quiz, 1, {}, [])
        assert attempt.score == 0
