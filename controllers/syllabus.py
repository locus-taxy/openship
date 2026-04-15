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
)
from services.gemini import generate_syllabus_json
from services.daily_task import store_syllabus_tasks

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
        payload.skill, skill["days"], skill["hours"], user_api_key=current_user.gemini_api_key
    )
    if syllabus_data is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate syllabus (Gemini returned no data). Check uvicorn logs.",
        )
    if not isinstance(syllabus_data, (list, tuple)):
        logger.warning(
            "Unexpected syllabus JSON type from Gemini: %s (expected a list of months).",
            type(syllabus_data).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Gemini returned syllabus data in an unexpected format (expected a JSON array). "
            "Check uvicorn logs or try again.",
        )
    syllabus_data = list(syllabus_data)
    if len(syllabus_data) == 0:
        raise HTTPException(
            status_code=500,
            detail="Gemini returned an empty syllabus. Try again or shorten the plan (days).",
        )

    if not store_syllabus_tasks(
        str(current_user.id), payload.skill, syllabus_data, skill["hours"], skill_id
    ):
        raise HTTPException(
            status_code=500,
            detail="Syllabus was generated but could not be saved to the database",
        )
    return {"status": "success", "message": f"Syllabus generated for '{payload.skill}'"}
