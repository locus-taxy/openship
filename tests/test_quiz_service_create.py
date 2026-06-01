from unittest.mock import MagicMock, patch
import pytest
from services.quiz import create_quiz
from services.llm import GeneratedQuestion, QuizOption

def _make_question(q="What is Python?", correct="A"):
    return GeneratedQuestion(
        question=q,
        options=[
            QuizOption(label="A", text="A language"),
            QuizOption(label="B", text="A snake"),
            QuizOption(label="C", text="A film"),
            QuizOption(label="D", text="A number"),
        ],
        correct_option=correct,
        explanation="Python is a programming language.",
    )

def _patch_session(session_mock):
    patcher = patch("services.quiz.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

class TestCreateQuiz:
    def test_creates_quiz_with_questions(self):
        session = MagicMock()
        quiz_holder = []

        def on_add(obj):
            if hasattr(obj, "difficulty") and not quiz_holder:
                obj.id = 1
                quiz_holder.append(obj)

        def on_flush():
            pass  # id already set by on_add

        session.add.side_effect = on_add
        session.flush.side_effect = on_flush

        questions = [_make_question(), _make_question("What is PEP?", "B")]
        patcher = _patch_session(session)
        try:
            result = create_quiz(1, "beginner", questions)
            assert session.commit.called
            assert session.refresh.called
        finally:
            patcher.stop()

    def test_sets_correct_pass_score_for_beginner(self):
        from services.quiz import PASS_SCORES

        session = MagicMock()

        def on_add(obj):
            if hasattr(obj, "difficulty"):
                obj.id = 1

        session.add.side_effect = on_add
        patcher = _patch_session(session)
        try:
            create_quiz(1, "beginner", [_make_question()])
            # The Quiz was constructed with pass_score from PASS_SCORES
            added_calls = session.add.call_args_list
            quiz_call = added_calls[0][0][0]
            assert quiz_call.pass_score == PASS_SCORES.get("beginner", 60)
        finally:
            patcher.stop()

    def test_adds_one_question_row_per_generated_question(self):
        session = MagicMock()

        def on_add(obj):
            if hasattr(obj, "difficulty"):
                obj.id = 1

        session.add.side_effect = on_add
        questions = [_make_question(), _make_question("Q2?", "C"), _make_question("Q3?", "D")]
        patcher = _patch_session(session)
        try:
            create_quiz(1, "intermediate", questions)
            # 1 Quiz + 3 QuizQuestion = 4 add calls
            assert session.add.call_count == 4
        finally:
            patcher.stop()

    def test_handles_empty_questions_list(self):
        session = MagicMock()

        def on_add(obj):
            if hasattr(obj, "difficulty"):
                obj.id = 1

        session.add.side_effect = on_add
        patcher = _patch_session(session)
        try:
            create_quiz(1, "advanced", [])
            # Only 1 add call for Quiz itself
            assert session.add.call_count == 1
            assert session.commit.called
        finally:
            patcher.stop()
