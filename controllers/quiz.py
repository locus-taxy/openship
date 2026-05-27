import logging
import math
from typing import Optional

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.exc import IntegrityError

from models.quiz import Quiz
from models.skill import Skill
from models.user import User
from schemas.quiz import (
    QuizAttemptOut,
    QuizAttemptsResponse,
    QuizGenerateResponse,
    LatestAttemptResponse,
    QuizOut,
    QuizQuestionOut,
    QuizQuestionResult,
    QuizSubmitRequest,
    QuizSubmitResponse,
    TopicScore,
    WeeklyQuizSubmitResponse,
)
from services import quiz as quiz_service
from services.bkt import update_topic_knowledge, get_weak_topics, calc_remediation_days
from services.forgetting_curve import get_forgotten_topics
from services.bandit import sample_style, update_arm
from services.skill import unlock_next_week
from services.llm import (
    generate_weekly_quiz,
    generate_final_quiz,
    generate_week_plan,
    get_user_api_key,
    get_user_model,
    get_user_provider_name,
)
from services.daily_task import (
    delete_week_tasks,
    store_week_tasks,
    get_max_day_for_skill,
    get_week_content_style,
)
from database import engine
from sqlmodel import Session

logger = logging.getLogger(__name__)

def _get_owned_skill(skill_id: int, current_user: User) -> Skill:
    with Session(engine) as session:
        skill = session.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    if skill.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not own this skill")
    return skill

def _get_owned_quiz(skill_id: int, current_user: User, week: int = 0) -> Quiz:
    _get_owned_skill(skill_id, current_user)
    quiz = quiz_service.get_quiz_by_week(skill_id, week)
    if quiz is None:
        label = "final quiz" if week == 0 else f"week {week} quiz"
        raise HTTPException(
            status_code=404, detail=f"{label.capitalize()} not yet generated for this course"
        )
    return quiz

def _build_quiz_out(quiz: Quiz, skill_id: int, current_user: User) -> QuizOut:
    _, questions = quiz_service.get_quiz_with_questions(quiz.id)
    return QuizOut(
        quiz_id=quiz.id,
        skill_id=skill_id,
        week=quiz.week,
        pass_score=quiz.pass_score,
        status=quiz.status,
        questions=[
            QuizQuestionOut(
                id=q.id,
                position=q.position,
                question=q.question,
                option_a=q.option_a,
                option_b=q.option_b,
                option_c=q.option_c,
                option_d=q.option_d,
            )
            for q in questions
        ],
        best_score=quiz_service.get_best_score(quiz.id, current_user.id),
        attempt_count=quiz_service.get_attempt_count(quiz.id, current_user.id),
    )

# ── Background ML week generation ─────────────────────────────────────────────

def _generate_next_week(
    skill_id: int,
    skill_name: str,
    skill_days: int,
    skill_total_weeks: int,
    skill_hours: int,
    user_id_int: int,
    user_id_str: str,
    next_week: int,
    provider: str,
    api_key: str,
    model: str,
) -> None:
    """Generate ML-personalised tasks and pre-generate quiz for a newly unlocked week.
    Safe to run in a FastAPI BackgroundTask — uses only scalar args, no ORM objects."""
    try:
        weak = get_weak_topics(skill_id, user_id_int)
        forgotten = get_forgotten_topics(skill_id, user_id_int)
        days_in_week = max(1, math.ceil(skill_days / skill_total_weeks))
        start_day = get_max_day_for_skill(skill_id) + 1
        month = ((next_week - 1) // 4) + 1

        # Fetch previous week's quiz attempt to get targeted failed topics
        prev_quiz = quiz_service.get_quiz_by_week(skill_id, next_week - 1)
        score_for_remediation = 100
        remediation_topics: list = []
        if prev_quiz:
            prev_attempt = quiz_service.get_latest_attempt_results(prev_quiz.id, user_id_int)
            if prev_attempt:
                score_for_remediation = prev_attempt["score"]
                # Only remediate topics that actually failed in the last attempt
                # (not the full BKT history which can include many old topics)
                pass_threshold = prev_quiz.pass_score
                remediation_topics = [
                    t for t, s in prev_attempt["topic_scores"].items() if s["pct"] < pass_threshold
                ]

        # Fall back to top-3 BKT weak topics if no quiz attempt or all topics passed
        if not remediation_topics:
            remediation_topics = weak[:3]

        remediation = calc_remediation_days(score_for_remediation, days_in_week)

        delete_week_tasks(skill_id, next_week)
        daily_plan = generate_week_plan(
            skill=skill_name,
            week=next_week,
            total_weeks=skill_total_weeks,
            weak_topics=remediation_topics,
            forgotten_topics=forgotten,
            days_in_week=days_in_week,
            start_day=start_day,
            provider=provider,
            api_key=api_key,
            model=model,
            prev_score=score_for_remediation,
            remediation_days=remediation,
        )
        if not daily_plan:
            logger.warning(
                "Week %d plan returned None [skill=%d] — no tasks stored", next_week, skill_id
            )
            return

        store_week_tasks(
            user_id_str, skill_name, skill_id, next_week, month, daily_plan, skill_hours
        )

        next_topics = quiz_service.get_topics_for_week(skill_id, next_week)
        if next_topics and quiz_service.get_quiz_by_week(skill_id, next_week) is None:
            bg_pool_size = 1 if provider == "mistral" else 2
            generated = generate_weekly_quiz(
                skill=skill_name,
                week=next_week,
                topics=next_topics,
                num_questions=quiz_service.WEEKLY_QUIZ_QUESTIONS,
                provider=provider,
                api_key=api_key,
                model=model,
                pool_size=bg_pool_size,
            )
            if generated:
                num_unique = quiz_service.WEEKLY_QUIZ_QUESTIONS
                topic_map = {
                    i: next_topics[(i - 1) % len(next_topics)] for i in range(1, num_unique + 1)
                }
                quiz_service.create_quiz(
                    skill_id,
                    generated.questions,
                    week=next_week,
                    topic_map=topic_map,
                    pool_size=bg_pool_size,
                )
    except Exception as exc:
        logger.error(
            "Week %d ML generation failed [skill=%d]: %s", next_week, skill_id, exc, exc_info=True
        )

# ── Weekly quiz ────────────────────────────────────────────────────────────────

def generate_weekly_quiz_for_skill(
    skill_id: int, week: int, current_user: User
) -> QuizGenerateResponse:
    skill = _get_owned_skill(skill_id, current_user)

    if quiz_service.get_quiz_by_week(skill_id, week) is not None:
        raise HTTPException(status_code=409, detail=f"Week {week} quiz already generated")

    topics = quiz_service.get_topics_for_week(skill_id, week)
    if not topics:
        raise HTTPException(status_code=400, detail=f"No topics found for week {week}")

    provider = get_user_provider_name(current_user)
    api_key = get_user_api_key(current_user)
    model = get_user_model(current_user)

    pool_size = 1 if provider == "mistral" else 2
    generated = generate_weekly_quiz(
        skill=skill.skill,
        week=week,
        topics=topics,
        num_questions=quiz_service.WEEKLY_QUIZ_QUESTIONS,
        provider=provider,
        api_key=api_key,
        model=model,
        pool_size=pool_size,
    )
    if generated is None:
        raise HTTPException(
            status_code=502, detail="Weekly quiz generation failed. Please try again."
        )

    # Build topic_map: pool_group → topic (distribute topics evenly across unique questions)
    num_unique = quiz_service.WEEKLY_QUIZ_QUESTIONS
    topic_map = {i: topics[(i - 1) % len(topics)] for i in range(1, num_unique + 1)}

    try:
        quiz = quiz_service.create_quiz(
            skill_id=skill_id,
            questions=generated.questions,
            week=week,
            topic_map=topic_map,
            pool_size=pool_size,
        )
    except IntegrityError as err:
        raise HTTPException(status_code=409, detail=f"Week {week} quiz already generated") from err

    return QuizGenerateResponse(
        quiz_id=quiz.id,
        week=quiz.week,
        status=quiz.status,
        question_count=len(generated.questions),
        pass_score=quiz.pass_score,
    )

def get_weekly_quiz(skill_id: int, week: int, current_user: User) -> QuizOut:
    quiz = _get_owned_quiz(skill_id, current_user, week=week)
    return _build_quiz_out(quiz, skill_id, current_user)

def submit_weekly_quiz(
    skill_id: int,
    week: int,
    payload: QuizSubmitRequest,
    current_user: User,
    background_tasks: Optional[BackgroundTasks] = None,
) -> WeeklyQuizSubmitResponse:
    skill = _get_owned_skill(skill_id, current_user)
    quiz = _get_owned_quiz(skill_id, current_user, week=week)
    all_questions = quiz_service.get_all_quiz_questions(quiz.id)

    all_question_ids = {q.id for q in all_questions}
    for qid in payload.answers:
        if qid not in all_question_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Question ID {qid} does not belong to this quiz",
            )
    question_map = {q.id: q for q in all_questions}
    questions = [question_map[qid] for qid in payload.answers if qid in question_map]

    attempt = quiz_service.record_attempt(quiz, current_user.id, payload.answers, questions)

    # ── ML updates ────────────────────────────────────────────────────────────
    bkt_inputs = [
        (q.topic, week, payload.answers.get(q.id, "").upper() == q.correct_option.upper())
        for q in questions
        if q.topic
    ]
    if bkt_inputs:
        update_topic_knowledge(skill_id, current_user.id, bkt_inputs)

    prev_score = quiz_service.get_previous_best_score(skill_id, current_user.id, before_week=week)
    improved = prev_score is None or attempt.score > prev_score
    stored_style = get_week_content_style(skill_id, week)
    if stored_style:
        update_arm(skill_id, current_user.id, stored_style, improved)
    next_style = sample_style(skill_id, current_user.id)
    # ─────────────────────────────────────────────────────────────────────────

    # Unlock next week and schedule ML generation for it (progressive courses only)
    new_generated_weeks = unlock_next_week(skill_id, week)
    next_week = week + 1
    if new_generated_weeks == next_week and next_week <= skill.total_weeks:
        provider = get_user_provider_name(current_user)
        api_key = get_user_api_key(current_user)
        model = get_user_model(current_user)
        gen_kwargs = dict(
            skill_id=skill_id,
            skill_name=skill.skill,
            skill_days=skill.days,
            skill_total_weeks=skill.total_weeks,
            skill_hours=skill.hours,
            user_id_int=current_user.id,
            user_id_str=str(current_user.id),
            next_week=next_week,
            provider=provider,
            api_key=api_key,
            model=model,
        )
        if background_tasks is not None:
            background_tasks.add_task(_generate_next_week, **gen_kwargs)
        else:
            _generate_next_week(**gen_kwargs)

    results = [
        QuizQuestionResult(
            question_id=q.id,
            topic=q.topic,
            selected=payload.answers.get(q.id, ""),
            correct=q.correct_option,
            is_correct=payload.answers.get(q.id, "").upper() == q.correct_option.upper(),
            explanation=q.explanation,
        )
        for q in questions
    ]

    raw_topic_scores: dict = {}
    for q in questions:
        topic = q.topic or "General"
        ts = raw_topic_scores.setdefault(topic, {"correct": 0, "total": 0})
        ts["total"] += 1
        if payload.answers.get(q.id, "").upper() == q.correct_option.upper():
            ts["correct"] += 1
    for ts in raw_topic_scores.values():
        ts["pct"] = round(ts["correct"] / ts["total"] * 100) if ts["total"] else 0

    return WeeklyQuizSubmitResponse(
        attempt_id=attempt.id,
        score=attempt.score,
        passed=attempt.passed,
        pass_score=quiz.pass_score,
        results=results,
        topic_scores={t: TopicScore(**s) for t, s in raw_topic_scores.items()},
        next_week_style=next_style,
        next_week_unlocked=new_generated_weeks if new_generated_weeks == next_week else None,
    )

# ── Final quiz ─────────────────────────────────────────────────────────────────

def generate_quiz_for_skill(skill_id: int, current_user: User) -> QuizGenerateResponse:
    skill = _get_owned_skill(skill_id, current_user)

    if quiz_service.get_quiz_by_week(skill_id, 0) is not None:
        raise HTTPException(status_code=409, detail="Final quiz already generated for this course")

    weak = get_weak_topics(skill_id, current_user.id)
    forgotten = get_forgotten_topics(skill_id, current_user.id)

    # Fallback: if no ML data yet, use all course topics
    if not weak and not forgotten:
        weak = quiz_service.get_topics_for_skill(skill_id)
    if not weak and not forgotten:
        raise HTTPException(status_code=400, detail="No topics found for this skill")

    provider = get_user_provider_name(current_user)
    api_key = get_user_api_key(current_user)
    model = get_user_model(current_user)

    all_for_map = list(dict.fromkeys(weak + forgotten))
    topic_week_map = quiz_service.get_topic_week_map(skill_id, all_for_map)

    pool_size = 1 if provider == "mistral" else 2
    num_questions = quiz_service.get_num_questions(skill.days)
    generated = generate_final_quiz(
        skill=skill.skill,
        weak_topics=weak,
        forgotten_topics=forgotten,
        num_questions=num_questions,
        provider=provider,
        api_key=api_key,
        model=model,
        topic_week_map=topic_week_map or None,
        pool_size=pool_size,
    )
    if generated is None:
        raise HTTPException(
            status_code=502, detail="Final quiz generation failed. Please try again."
        )

    topic_map = (
        {i: all_for_map[(i - 1) % len(all_for_map)] for i in range(1, num_questions + 1)}
        if all_for_map
        else None
    )
    try:
        quiz = quiz_service.create_quiz(
            skill_id=skill_id,
            questions=generated.questions,
            week=0,
            topic_map=topic_map,
            pool_size=pool_size,
        )
    except IntegrityError as err:
        raise HTTPException(
            status_code=409, detail="Final quiz already generated for this course"
        ) from err

    return QuizGenerateResponse(
        quiz_id=quiz.id,
        week=quiz.week,
        status=quiz.status,
        question_count=len(generated.questions),
        pass_score=quiz.pass_score,
    )

def get_quiz(skill_id: int, current_user: User) -> QuizOut:
    quiz = _get_owned_quiz(skill_id, current_user, week=0)
    return _build_quiz_out(quiz, skill_id, current_user)

def submit_quiz(
    skill_id: int, payload: QuizSubmitRequest, current_user: User
) -> QuizSubmitResponse:
    quiz = _get_owned_quiz(skill_id, current_user, week=0)
    all_questions = quiz_service.get_all_quiz_questions(quiz.id)

    all_question_ids = {q.id for q in all_questions}
    for qid in payload.answers:
        if qid not in all_question_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Question ID {qid} does not belong to this quiz",
            )
    question_map = {q.id: q for q in all_questions}
    questions = [question_map[qid] for qid in payload.answers if qid in question_map]

    attempt = quiz_service.record_attempt(quiz, current_user.id, payload.answers, questions)

    bkt_inputs = [
        (q.topic, 0, payload.answers.get(q.id, "").upper() == q.correct_option.upper())
        for q in questions
        if q.topic
    ]
    if bkt_inputs:
        update_topic_knowledge(skill_id, current_user.id, bkt_inputs)

    results = [
        QuizQuestionResult(
            question_id=q.id,
            topic=q.topic,
            selected=payload.answers.get(q.id, ""),
            correct=q.correct_option,
            is_correct=payload.answers.get(q.id, "").upper() == q.correct_option.upper(),
            explanation=q.explanation,
        )
        for q in questions
    ]

    raw_topic_scores: dict = {}
    for q in questions:
        topic = q.topic or "General"
        ts = raw_topic_scores.setdefault(topic, {"correct": 0, "total": 0})
        ts["total"] += 1
        if payload.answers.get(q.id, "").upper() == q.correct_option.upper():
            ts["correct"] += 1
    for ts in raw_topic_scores.values():
        ts["pct"] = round(ts["correct"] / ts["total"] * 100) if ts["total"] else 0

    return QuizSubmitResponse(
        attempt_id=attempt.id,
        score=attempt.score,
        passed=attempt.passed,
        pass_score=quiz.pass_score,
        results=results,
        topic_scores={t: TopicScore(**s) for t, s in raw_topic_scores.items()},
    )

def get_attempts(skill_id: int, current_user: User) -> QuizAttemptsResponse:
    quiz = _get_owned_quiz(skill_id, current_user, week=0)
    attempts = quiz_service.get_attempts_for_quiz(quiz.id, current_user.id)

    return QuizAttemptsResponse(
        quiz_id=quiz.id,
        skill_id=skill_id,
        pass_score=quiz.pass_score,
        attempts=[
            QuizAttemptOut(
                attempt_id=a.id,
                score=a.score,
                passed=a.passed,
                created_at=a.created_at.isoformat() if a.created_at else None,
            )
            for a in attempts
        ],
    )

def get_latest_attempt(skill_id: int, current_user: User) -> LatestAttemptResponse:
    quiz = _get_owned_quiz(skill_id, current_user, week=0)
    data = quiz_service.get_latest_attempt_results(quiz.id, current_user.id)
    if data is None:
        raise HTTPException(status_code=404, detail="No attempts found for this quiz")
    return LatestAttemptResponse(
        **{k: v for k, v in data.items() if k != "topic_scores"},
        topic_scores={t: TopicScore(**s) for t, s in data["topic_scores"].items()},
    )

def get_weekly_latest_attempt(
    skill_id: int, week: int, current_user: User
) -> LatestAttemptResponse:
    quiz = _get_owned_quiz(skill_id, current_user, week=week)
    data = quiz_service.get_latest_attempt_results(quiz.id, current_user.id)
    if data is None:
        raise HTTPException(status_code=404, detail="No attempts found for this quiz")
    return LatestAttemptResponse(
        **{k: v for k, v in data.items() if k != "topic_scores"},
        topic_scores={t: TopicScore(**s) for t, s in data["topic_scores"].items()},
    )

def reset_final_quiz(skill_id: int, current_user: User):
    """Delete the final quiz so it can be regenerated with ML data."""
    _get_owned_skill(skill_id, current_user)
    deleted = quiz_service.delete_final_quiz(skill_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No final quiz found to reset")
    return {
        "status": "success",
        "message": "Final quiz reset. You can now regenerate it with ML data.",
    }
