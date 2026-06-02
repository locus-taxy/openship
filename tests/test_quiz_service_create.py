from unittest.mock import MagicMock, patch
import pytest
from services.quiz import create_quiz
from models.quiz import Quiz, WEEKLY_PASS_SCORE, FINAL_PASS_SCORE
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
    def test_creates_weekly_quiz_with_questions(self):
        session = MagicMock()
        quiz_holder = []

        def on_add(obj):
            if isinstance(obj, Quiz) and not quiz_holder:
                obj.id = 1
                quiz_holder.append(obj)

        session.add.side_effect = on_add
        questions = [_make_question(), _make_question("What is PEP?", "B")]
        patcher = _patch_session(session)
        try:
            create_quiz(1, questions, week=1)
            assert session.commit.called
            assert session.refresh.called
        finally:
            patcher.stop()

    def test_weekly_quiz_uses_weekly_pass_score(self):
        session = MagicMock()

        def on_add(obj):
            if hasattr(obj, "pass_score") and not hasattr(obj, "quiz_id"):
                obj.id = 1

        session.add.side_effect = on_add
        patcher = _patch_session(session)
        try:
            create_quiz(1, [_make_question()], week=1)
            added_calls = session.add.call_args_list
            quiz_call = added_calls[0][0][0]
            assert quiz_call.pass_score == WEEKLY_PASS_SCORE
        finally:
            patcher.stop()

    def test_final_quiz_uses_final_pass_score(self):
        session = MagicMock()

        def on_add(obj):
            if hasattr(obj, "pass_score") and not hasattr(obj, "quiz_id"):
                obj.id = 1

        session.add.side_effect = on_add
        patcher = _patch_session(session)
        try:
            create_quiz(1, [_make_question()], week=0)
            added_calls = session.add.call_args_list
            quiz_call = added_calls[0][0][0]
            assert quiz_call.pass_score == FINAL_PASS_SCORE
        finally:
            patcher.stop()

    def test_adds_one_question_row_per_generated_question(self):
        session = MagicMock()

        def on_add(obj):
            if hasattr(obj, "pass_score") and not hasattr(obj, "quiz_id"):
                obj.id = 1

        session.add.side_effect = on_add
        questions = [_make_question(), _make_question("Q2?", "C"), _make_question("Q3?", "D")]
        patcher = _patch_session(session)
        try:
            create_quiz(1, questions, week=1)
            # 1 Quiz + 3 QuizQuestion = 4 add calls
            assert session.add.call_count == 4
        finally:
            patcher.stop()

    def test_handles_empty_questions_list(self):
        session = MagicMock()

        def on_add(obj):
            if hasattr(obj, "pass_score") and not hasattr(obj, "quiz_id"):
                obj.id = 1

        session.add.side_effect = on_add
        patcher = _patch_session(session)
        try:
            create_quiz(1, [], week=0)
            # Only 1 add call for Quiz itself
            assert session.add.call_count == 1
            assert session.commit.called
        finally:
            patcher.stop()

    def test_topic_map_assigns_topic_to_questions(self):
        session = MagicMock()

        def on_add(obj):
            if hasattr(obj, "pass_score") and not hasattr(obj, "quiz_id"):
                obj.id = 1

        session.add.side_effect = on_add
        patcher = _patch_session(session)
        try:
            topic_map = {1: "Variables", 2: "Loops"}
            create_quiz(
                1, [_make_question(), _make_question("Q2?", "B")], week=1, topic_map=topic_map
            )
            add_calls = session.add.call_args_list
            # index 1 = first question row
            q1 = add_calls[1][0][0]
            assert q1.topic == "Variables"
            q2 = add_calls[2][0][0]
            assert q2.topic == "Loops"
        finally:
            patcher.stop()
