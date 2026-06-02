import random
from typing import Any, Dict, List, Optional, Tuple

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
    """Return True only if tasks exist for this week and all are complete."""
    with Session(engine) as session:
        any_task = session.exec(
            select(DailyTask).where(DailyTask.skill_id == skill_id, DailyTask.week == week)
        ).first()
        if any_task is None:
            return False
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

def get_topic_week_map(skill_id: int, topics: List[str]) -> Dict[str, int]:
    """Return {topic: earliest_week} for the given topic names."""
    topic_set = set(topics)
    with Session(engine) as session:
        tasks = session.exec(
            select(DailyTask).where(DailyTask.skill_id == skill_id).order_by(DailyTask.week)
        ).all()
    result: Dict[str, int] = {}
    for t in tasks:
        if t.topic and t.topic in topic_set and t.week and t.topic not in result:
            result[t.topic] = t.week
    return result

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
    pool_size: int = 1,
) -> Quiz:
    """Insert Quiz + QuizQuestion rows. week=0 is the final quiz, week>=1 is weekly.

    When pool_size > 1 the LLM generated pool_size variants per unique question.
    Every pool_size consecutive questions receive the same pool_group so that
    get_quiz_with_questions can sample one variant per group.
    topic_map keys are pool-group numbers (1-indexed), not raw position numbers.
    """
    pass_score = FINAL_PASS_SCORE if week == 0 else WEEKLY_PASS_SCORE
    with Session(engine) as session:
        quiz = Quiz(skill_id=skill_id, week=week, pass_score=pass_score)
        session.add(quiz)
        session.flush()

        for i, q in enumerate(questions, start=1):
            opts = {o.label.upper(): o.text for o in q.options}
            group = (i - 1) // pool_size + 1  # 1-based pool group
            topic = topic_map.get(group) if topic_map else None
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
                pool_group=group if pool_size > 1 else None,
            )
            session.add(question_row)

        session.commit()
        session.refresh(quiz)
        return quiz

def get_all_quiz_questions(quiz_id: int) -> List[QuizQuestion]:
    """Return every question for a quiz without sampling pool groups."""
    with Session(engine) as session:
        return list(
            session.exec(
                select(QuizQuestion)
                .where(QuizQuestion.quiz_id == quiz_id)
                .order_by(QuizQuestion.position)
            ).all()
        )

def get_quiz_with_questions(quiz_id: int) -> Tuple[Optional[Quiz], List[QuizQuestion]]:
    with Session(engine) as session:
        quiz = session.get(Quiz, quiz_id)
        if quiz is None:
            return None, []
        all_questions = session.exec(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz_id)
            .order_by(QuizQuestion.position)
        ).all()

    # If pool groups exist, sample exactly one question per group
    has_pools = any(q.pool_group is not None for q in all_questions)
    if not has_pools:
        return quiz, list(all_questions)

    groups: Dict[int, List[QuizQuestion]] = {}
    for q in all_questions:
        groups.setdefault(q.pool_group, []).append(q)  # type: ignore[arg-type]
    sampled = [random.choice(variants) for _, variants in sorted(groups.items())]
    return quiz, sampled

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

def get_latest_attempt_results(quiz_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Return the most recent attempt with per-question results and per-topic score breakdown."""
    with Session(engine) as session:
        attempt = session.exec(
            select(QuizAttempt)
            .where(QuizAttempt.quiz_id == quiz_id, QuizAttempt.user_id == user_id)
            .order_by(QuizAttempt.created_at.desc())
        ).first()
        if attempt is None:
            return None

        quiz = session.get(Quiz, quiz_id)
        questions = session.exec(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz_id)
            .order_by(QuizQuestion.position)
        ).all()

        results = []
        served_ids = {int(k) for k in attempt.answers}
        topic_scores: Dict[str, Dict[str, int]] = {}
        for q in questions:
            if q.pool_group is not None and q.id not in served_ids:
                continue
            selected = attempt.answers.get(str(q.id), "")
            is_correct = bool(selected) and selected.upper() == q.correct_option.upper()
            topic = q.topic or "General"
            results.append(
                {
                    "question_id": q.id,
                    "topic": topic,
                    "selected": selected,
                    "correct": q.correct_option,
                    "is_correct": is_correct,
                    "explanation": q.explanation,
                }
            )
            ts = topic_scores.setdefault(topic, {"correct": 0, "total": 0})
            ts["total"] += 1
            if is_correct:
                ts["correct"] += 1

        for ts in topic_scores.values():
            ts["pct"] = round(ts["correct"] / ts["total"] * 100) if ts["total"] else 0

        return {
            "attempt_id": attempt.id,
            "score": attempt.score,
            "passed": attempt.passed,
            "pass_score": quiz.pass_score if quiz else 0,
            "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
            "results": results,
            "topic_scores": topic_scores,
        }

def get_previous_best_score(skill_id: int, user_id: int, before_week: int) -> Optional[int]:
    """Return best score from the weekly quiz immediately before the given week."""
    prev_quiz = get_quiz_by_week(skill_id, before_week - 1)
    if prev_quiz is None:
        return None
    return get_best_score(prev_quiz.id, user_id)
