from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from database import engine
from models.daily_task import DailyTask
from models.quiz import Quiz, WEEKLY_PASS_SCORE, FINAL_PASS_SCORE
from models.quiz_attempt import QuizAttempt
from models.quiz_question import QuizQuestion
from services.llm import GeneratedQuestion

NUM_QUESTIONS = {
    30: 10,
    60: 12,
    90: 15,
}
WEEKLY_QUIZ_QUESTIONS = 5

def get_num_questions(days: int) -> int:
    if days <= 30:
        return NUM_QUESTIONS[30]
    if days <= 60:
        return NUM_QUESTIONS[60]
    return NUM_QUESTIONS[90]

def all_weeks_complete(skill_id: int, week: int) -> bool:
    """Return True if every chapter for this skill in the given week is marked complete."""
    with Session(engine) as session:
        incomplete = session.exec(
            select(DailyTask).where(
                DailyTask.skill_id == skill_id,
                DailyTask.week == week,
                DailyTask.completed == False,
            )
        ).first()
        return incomplete is None

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
    """Return ordered list of topic strings across the whole course."""
    with Session(engine) as session:
        tasks = session.exec(
            select(DailyTask)
            .where(DailyTask.skill_id == skill_id)
            .order_by(DailyTask.month, DailyTask.week, DailyTask.day)
        ).all()
        return [t.topic for t in tasks if t.topic]

def get_topics_for_week(skill_id: int, week: int) -> List[str]:
    """Return deduplicated ordered topics for a specific week."""
    with Session(engine) as session:
        tasks = session.exec(
            select(DailyTask)
            .where(DailyTask.skill_id == skill_id, DailyTask.week == week)
            .order_by(DailyTask.day)
        ).all()
        seen = set()
        topics = []
        for t in tasks:
            if t.topic and t.topic not in seen:
                seen.add(t.topic)
                topics.append(t.topic)
        return topics

def get_quiz_by_skill(skill_id: int) -> Optional[Quiz]:
    """Return the final quiz (week=0) for this skill, or None."""
    with Session(engine) as session:
        return session.exec(select(Quiz).where(Quiz.skill_id == skill_id, Quiz.week == 0)).first()

def get_quiz_by_week(skill_id: int, week: int) -> Optional[Quiz]:
    """Return the quiz for a specific week, or None."""
    with Session(engine) as session:
        return session.exec(
            select(Quiz).where(Quiz.skill_id == skill_id, Quiz.week == week)
        ).first()

def create_quiz(
    skill_id: int,
    questions: List[GeneratedQuestion],
    week: int = 0,
    topic_map: Optional[Dict[int, str]] = None,
) -> Quiz:
    """Insert Quiz + QuizQuestion rows. week=0 is the final quiz, week>=1 is weekly."""
    pass_score = FINAL_PASS_SCORE if week == 0 else WEEKLY_PASS_SCORE
    with Session(engine) as session:
        quiz = Quiz(skill_id=skill_id, week=week, pass_score=pass_score)
        session.add(quiz)
        session.flush()

        for i, q in enumerate(questions, start=1):
            opts = {o.label.upper(): o.text for o in q.options}
            topic = topic_map.get(i) if topic_map else None
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
                topic=topic,
            )
            session.add(question_row)

        session.commit()
        session.refresh(quiz)
        return quiz

def get_quiz_with_questions(quiz_id: int) -> Tuple[Optional[Quiz], List[QuizQuestion]]:
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

def clear_all_quizzes(skill_id: int) -> None:
    """Delete all quizzes (weekly + final) for a skill. Used when re-generating the syllabus."""
    with Session(engine) as session:
        quizzes = session.exec(select(Quiz).where(Quiz.skill_id == skill_id)).all()
        for q in quizzes:
            session.delete(q)
        session.commit()

def delete_final_quiz(skill_id: int) -> bool:
    """Delete only the final quiz (week=0) so it can be regenerated with ML data."""
    with Session(engine) as session:
        quiz = session.exec(select(Quiz).where(Quiz.skill_id == skill_id, Quiz.week == 0)).first()
        if quiz is None:
            return False
        session.delete(quiz)
        session.commit()
        return True

def get_previous_best_score(skill_id: int, user_id: int, before_week: int) -> Optional[int]:
    """Return best score from the weekly quiz immediately before the given week."""
    prev_quiz = get_quiz_by_week(skill_id, before_week - 1)
    if prev_quiz is None:
        return None
    return get_best_score(prev_quiz.id, user_id)
