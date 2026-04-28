from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from models.quiz import Quiz
from models.skill import Skill
from models.user import User
from schemas.quiz import (
    QuizAttemptOut,
    QuizAttemptsResponse,
    QuizGenerateResponse,
    QuizOut,
    QuizQuestionOut,
    QuizQuestionResult,
    QuizSubmitRequest,
    QuizSubmitResponse,
)
from services import quiz as quiz_service
from services.llm import (
    generate_quiz,
    get_user_api_key,
    get_user_model,
    get_user_provider_name,
)
from database import engine
from sqlmodel import Session

def _get_owned_skill(skill_id: int, current_user: User) -> Skill:
    with Session(engine) as session:
        skill = session.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    if skill.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not own this skill")
    return skill

def _get_owned_quiz(skill_id: int, current_user: User) -> Quiz:
    _get_owned_skill(skill_id, current_user)
    quiz = quiz_service.get_quiz_by_skill(skill_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not yet generated for this course")
    return quiz

def generate_quiz_for_skill(skill_id: int, current_user: User) -> QuizGenerateResponse:
    skill = _get_owned_skill(skill_id, current_user)

    # Guard: quiz already exists
    if quiz_service.get_quiz_by_skill(skill_id) is not None:
        raise HTTPException(status_code=409, detail="Quiz already generated for this course")

    # Collect topics
    topics = quiz_service.get_topics_for_skill(skill_id)
    if not topics:
        raise HTTPException(status_code=400, detail="No topics found for this skill")

    # LLM settings
    provider = get_user_provider_name(current_user)
    api_key = get_user_api_key(current_user)
    model = get_user_model(current_user)

    num_questions = quiz_service.get_num_questions(skill.days)
    difficulty = skill.quiz_difficulty

    generated = generate_quiz(
        skill=skill.skill,
        topics=topics,
        difficulty=difficulty,
        num_questions=num_questions,
        provider=provider,
        api_key=api_key,
        model=model,
    )
    if generated is None:
        raise HTTPException(status_code=502, detail="Quiz generation failed. Please try again.")

    try:
        quiz = quiz_service.create_quiz(skill_id, difficulty, generated.questions)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Quiz already generated for this course")

    return QuizGenerateResponse(
        quiz_id=quiz.id,
        status=quiz.status,
        question_count=len(generated.questions),
        pass_score=quiz.pass_score,
    )

def get_quiz(skill_id: int, current_user: User) -> QuizOut:
    quiz = _get_owned_quiz(skill_id, current_user)
    _, questions = quiz_service.get_quiz_with_questions(quiz.id)

    questions_out = [
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
    ]

    return QuizOut(
        quiz_id=quiz.id,
        skill_id=skill_id,
        difficulty=quiz.difficulty,
        pass_score=quiz.pass_score,
        status=quiz.status,
        questions=questions_out,
        best_score=quiz_service.get_best_score(quiz.id, current_user.id),
        attempt_count=quiz_service.get_attempt_count(quiz.id, current_user.id),
    )

def submit_quiz(
    skill_id: int, payload: QuizSubmitRequest, current_user: User
) -> QuizSubmitResponse:
    quiz = _get_owned_quiz(skill_id, current_user)
    _, questions = quiz_service.get_quiz_with_questions(quiz.id)

    question_ids = {q.id for q in questions}
    for qid in payload.answers:
        if qid not in question_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Question ID {qid} does not belong to this quiz",
            )

    attempt = quiz_service.record_attempt(quiz, current_user.id, payload.answers, questions)

    results = [
        QuizQuestionResult(
            question_id=q.id,
            selected=payload.answers.get(q.id, ""),
            correct=q.correct_option,
            is_correct=payload.answers.get(q.id, "").upper() == q.correct_option.upper(),
            explanation=q.explanation,
        )
        for q in questions
    ]

    return QuizSubmitResponse(
        attempt_id=attempt.id,
        score=attempt.score,
        passed=attempt.passed,
        pass_score=quiz.pass_score,
        results=results,
    )

def get_attempts(skill_id: int, current_user: User) -> QuizAttemptsResponse:
    quiz = _get_owned_quiz(skill_id, current_user)
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
                created_at=str(a.created_at),
            )
            for a in attempts
        ],
    )
