import logging
import threading

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
)
from services.llm import (
    generate_syllabus_json,
    generate_quiz,
    get_user_api_key,
    get_user_model,
    get_user_provider_name,
)
from services.daily_task import store_syllabus_tasks
from services import quiz as quiz_service

logger = logging.getLogger(__name__)

def _auto_generate_quiz(
    skill_id: int,
    skill_name: str,
    difficulty: str,
    days: int,
    provider: str,
    api_key: str,
    model: str,
):
    """Background thread: generate and store quiz immediately after syllabus creation."""
    try:
        if quiz_service.get_quiz_by_skill(skill_id) is not None:
            return  # already exists (shouldn't happen, but guard anyway)

        topics = quiz_service.get_topics_for_skill(skill_id)
        if not topics:
            logger.warning("Auto-quiz skipped for skill %s: no topics found", skill_id)
            return

        num_questions = quiz_service.get_num_questions(days)
        generated = generate_quiz(
            skill=skill_name,
            topics=topics,
            difficulty=difficulty,
            num_questions=num_questions,
            provider=provider,
            api_key=api_key,
            model=model,
        )
        if generated is None:
            logger.warning("Auto-quiz generation returned None for skill %s", skill_id)
            return

        quiz_service.create_quiz(skill_id, difficulty, generated.questions)
        logger.info(
            "Auto-quiz created for skill %s (%d questions)", skill_id, len(generated.questions)
        )
    except Exception as e:
        logger.error("Auto-quiz generation failed for skill %s: %s", skill_id, e)

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

    syllabus_data = generate_syllabus_json(
        payload.skill,
        skill["days"],
        skill["hours"],
        provider=get_user_provider_name(current_user),
        api_key=get_user_api_key(current_user),
        model=get_user_model(current_user),
    )
    if syllabus_data is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate syllabus. Check server logs for details.",
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

    if not store_syllabus_tasks(
        str(current_user.id), payload.skill, syllabus_data, skill["hours"], skill_id
    ):
        raise HTTPException(
            status_code=500,
            detail="Syllabus was generated but could not be saved to the database",
        )

    # Kick off quiz generation in the background so the user isn't blocked
    provider = get_user_provider_name(current_user)
    api_key = get_user_api_key(current_user)
    model = get_user_model(current_user)
    if provider and api_key:
        difficulty = skill.get("quiz_difficulty", "beginner")
        threading.Thread(
            target=_auto_generate_quiz,
            args=(skill_id, payload.skill, difficulty, skill["days"], provider, api_key, model),
        ).start()

    return {"status": "success", "message": f"Syllabus generated for '{payload.skill}'"}
