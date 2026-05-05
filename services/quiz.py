from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from database import engine
from models.daily_task import DailyTask
from models.quiz import Quiz
from models.quiz_attempt import QuizAttempt
from models.quiz_question import QuizQuestion
from services.llm import GeneratedQuestion

PASS_SCORES = {
    "beginner": 60,
    "intermediate": 70,
    "advanced": 80,
}

NUM_QUESTIONS = {
    30: 10,
    60: 12,
    90: 15,
}

def get_num_questions(days: int) -> int:
    """Return question count based on course duration."""
    if days <= 30:
        return NUM_QUESTIONS[30]
    if days <= 60:
        return NUM_QUESTIONS[60]
    return NUM_QUESTIONS[90]

def all_chapters_complete(skill_id: int) -> bool:
    """Return True if every chapter for this skill is marked complete."""
    with Session(engine) as session:
        incomplete = session.exec(
            select(DailyTask).where(
                DailyTask.skill_id == skill_id,
                DailyTask.completed == False,
            )
        ).first()
        return incomplete is None

def get_topics_for_skill(skill_id: int) -> List[str]:
    """Return ordered list of topic strings for quiz prompt."""
    with Session(engine) as session:
        tasks = session.exec(
            select(DailyTask)
            .where(DailyTask.skill_id == skill_id)
            .order_by(DailyTask.month, DailyTask.week, DailyTask.day)
        ).all()
        return [t.topic for t in tasks if t.topic]

def get_quiz_by_skill(skill_id: int) -> Optional[Quiz]:
    """Return the Quiz for this skill, or None if not yet generated."""
    with Session(engine) as session:
        return session.exec(select(Quiz).where(Quiz.skill_id == skill_id)).first()

def create_quiz(skill_id: int, difficulty: str, questions: List[GeneratedQuestion]) -> Quiz:
    """
    Insert Quiz + QuizQuestion rows in a single transaction.
    Returns the created Quiz.
    """
    pass_score = PASS_SCORES.get(difficulty, 60)
    with Session(engine) as session:
        quiz = Quiz(skill_id=skill_id, difficulty=difficulty, pass_score=pass_score)
        session.add(quiz)
        session.flush()  # get quiz.id before inserting questions

        for i, q in enumerate(questions, start=1):
            # Build option lookup from the list
            opts = {o.label.upper(): o.text for o in q.options}
            question_row = QuizQuestion(
                quiz_id=quiz.id,
                position=i,
                question=q.question,
                option_a=opts.get("A", ""),
                option_b=opts.get("B", ""),
                option_c=opts.get("C", ""),
                option_d=opts.get("D", ""),
                correct_option=q.correct_option.upper(),
                explanation=q.explanation,
            )
            session.add(question_row)

        session.commit()
        session.refresh(quiz)
        return quiz

def get_quiz_with_questions(quiz_id: int) -> Tuple[Optional[Quiz], List[QuizQuestion]]:
    """Return (quiz, questions) ordered by position."""
    with Session(engine) as session:
        quiz = session.get(Quiz, quiz_id)
        if quiz is None:
            return None, []
        questions = session.exec(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz_id)
            .order_by(QuizQuestion.position)
        ).all()
        return quiz, list(questions)

def get_best_score(quiz_id: int, user_id: int) -> Optional[int]:
    """Return the highest score the user has achieved on this quiz."""
    with Session(engine) as session:
        attempts = session.exec(
            select(QuizAttempt).where(
                QuizAttempt.quiz_id == quiz_id,
                QuizAttempt.user_id == user_id,
            )
        ).all()
        if not attempts:
            return None
        return max(a.score for a in attempts)

def get_attempt_count(quiz_id: int, user_id: int) -> int:
    with Session(engine) as session:
        attempts = session.exec(
            select(QuizAttempt).where(
                QuizAttempt.quiz_id == quiz_id,
                QuizAttempt.user_id == user_id,
            )
        ).all()
        return len(attempts)

def record_attempt(
    quiz: Quiz, user_id: int, answers: Dict[int, str], questions: List[QuizQuestion]
) -> QuizAttempt:
    """
    Score the attempt, update quiz.status to 'passed' if passed, commit.
    Returns the saved QuizAttempt.
    """
    total = len(questions)
    correct = sum(1 for q in questions if answers.get(q.id, "").upper() == q.correct_option.upper())
    score = round((correct / total) * 100) if total else 0
    passed = score >= quiz.pass_score

    with Session(engine) as session:
        attempt = QuizAttempt(
            quiz_id=quiz.id,
            user_id=user_id,
            answers={str(k): v for k, v in answers.items()},
            score=score,
            passed=passed,
        )
        session.add(attempt)

        if passed:
            db_quiz = session.get(Quiz, quiz.id)
            db_quiz.status = "passed"
            session.add(db_quiz)

        session.commit()
        session.refresh(attempt)
        return attempt

def get_attempts_for_quiz(quiz_id: int, user_id: int) -> List[QuizAttempt]:
    """Return all attempts for this quiz by this user, newest first."""
    with Session(engine) as session:
        return list(
            session.exec(
                select(QuizAttempt)
                .where(
                    QuizAttempt.quiz_id == quiz_id,
                    QuizAttempt.user_id == user_id,
                )
                .order_by(QuizAttempt.created_at.desc())
            ).all()
        )
