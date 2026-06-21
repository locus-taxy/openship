import logging

from fastapi import HTTPException
from models.user import User
from schemas.skill import GenerateSyllabusRequest
from services.skill import (
    get_skill,
    get_all_syllabi,
    get_syllabus_detail,
    get_skill_id_by_email_and_skill,
    search_syllabi,
    get_public_syllabus_detail,
    toggle_skill_share,
    delete_skill,
    update_skill_weeks,
    update_skill_is_technical,
)
from services.llm import (
    generate_syllabus_json,
    generate_weekly_quiz,
    get_user_api_key,
    get_user_model,
    get_user_provider_name,
    classify_skill_domain,
)
from services.daily_task import store_syllabus_tasks, clear_syllabus_tasks
from services.quiz import (
    get_topics_for_week,
    create_quiz,
    clear_all_quizzes,
    build_topic_map,
)
from services.week_remediation import clear_remediation_topics

logger = logging.getLogger(__name__)

def list_syllabi(current_user: User):
    return get_all_syllabi(email=current_user.email)

def search(query: str, current_user: User):
    if not query or not query.strip():
        return get_all_syllabi(email=current_user.email)
    return search_syllabi(email=current_user.email, query=query.strip())

def get_syllabus(skill_id: int, current_user: User):
    detail = get_syllabus_detail(skill_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Syllabus {skill_id} not found")
    if detail.pop("_user_id") != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not own this skill")
    return detail

def get_public_syllabus(skill_id: int):
    detail = get_public_syllabus_detail(skill_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Syllabus {skill_id} not found or not shared")
    return detail

def delete_syllabus(skill_id: int, current_user: User):
    success = delete_skill(skill_id, str(current_user.id))
    if not success:
        raise HTTPException(status_code=404, detail="Course not found or not owned by you")
    return {"status": "success"}

def toggle_share(skill_id: int, enable: bool, current_user: User):
    result = toggle_skill_share(skill_id, enable, str(current_user.id))
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"Syllabus {skill_id} not found or not owned by you"
        )
    return {"skill_id": skill_id, "share_enabled": result}

def generate_syllabus(payload: GenerateSyllabusRequest, current_user: User):
    email = current_user.email
    skill = get_skill(email, payload.skill)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"No subscription found for '{payload.skill}'")

    skill_id = get_skill_id_by_email_and_skill(email, payload.skill)
    if skill_id is None:
        raise HTTPException(status_code=404, detail="Skill ID not found")

    provider = get_user_provider_name(current_user)
    api_key = get_user_api_key(current_user)
    model = get_user_model(current_user)

    syllabus_data = generate_syllabus_json(
        payload.skill,
        skill["days"],
        skill["hours"],
        provider=provider,
        api_key=api_key,
        model=model,
    )
    if not isinstance(syllabus_data, (list, tuple)):
        logger.warning(
            "Unexpected syllabus type from LLM: %s (expected a list of months).",
            type(syllabus_data).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="LLM returned syllabus data in an unexpected format. Try again.",
        )
    syllabus_data = list(syllabus_data)
    if len(syllabus_data) == 0:
        raise HTTPException(
            status_code=500,
            detail="LLM returned an empty syllabus. Try again or shorten the plan (days).",
        )

    # Clear old tasks and quizzes before storing new ones (prevents duplicates on re-generate).
    # NOTE: these three calls are NOT atomic — if store_syllabus_tasks fails the DB is left empty.
    # Making them transactional requires all three service functions to share a single Session,
    # which is a larger refactor. Risk is low in practice (store failure would be a DB error after
    # a successful LLM call) and the user can simply regenerate to recover.
    clear_syllabus_tasks(skill_id)
    clear_all_quizzes(skill_id)
    clear_remediation_topics(skill_id)

    if not store_syllabus_tasks(
        str(current_user.id),
        payload.skill,
        syllabus_data,
        skill["hours"],
        skill_id,
        only_week=1,
    ):
        raise HTTPException(
            status_code=500,
            detail="Syllabus was generated but could not be saved to the database",
        )

    # Count total weeks across all months and set progressive unlock tracking
    total_weeks = sum(len(month.get("weeks", [])) for month in syllabus_data)
    update_skill_weeks(skill_id, generated_weeks=1, total_weeks=total_weeks)

    # Classify skill domain (technical vs non-technical) so chapter prompts can be tailored.
    # Non-fatal: if classification fails the course still works, just without domain-specific rules.
    try:
        is_technical = classify_skill_domain(
            skill=payload.skill,
            provider=provider,
            api_key=api_key,
            model=model,
        )
        if is_technical is not None:
            update_skill_is_technical(skill_id, is_technical)
    except Exception as exc:
        logger.warning("Domain classification failed (non-fatal): %s", exc)

    # Pre-generate Week 1 quiz so it's ready when the user completes all Week 1 chapters
    pool_size = 1 if provider == "mistral" else 2
    try:
        week1_topics = get_topics_for_week(skill_id, 1)
        if week1_topics:
            num_unique = len(week1_topics)
            generated = generate_weekly_quiz(
                skill=payload.skill,
                week=1,
                topics=week1_topics,
                num_questions=num_unique,
                provider=provider,
                api_key=api_key,
                model=model,
                pool_size=pool_size,
            )
            if generated:
                topic_map = build_topic_map(week1_topics, num_unique)
                create_quiz(
                    skill_id, generated.questions, week=1, topic_map=topic_map, pool_size=pool_size
                )
    except Exception as exc:
        logger.warning("Week 1 quiz pre-generation failed (non-fatal): %s", exc)

    return {"status": "success", "message": f"Syllabus generated for '{payload.skill}'"}
