import logging

from fastapi import HTTPException

from schemas.skill import GenerateSyllabusRequest
from services.skill import (
    get_skill,
    get_all_syllabi,
    get_syllabus_detail,
    get_skill_id_by_email_and_skill,
)
from services.gemini import generate_syllabus_json
from services.daily_task import store_syllabus_tasks

logger = logging.getLogger(__name__)

def list_syllabi():
    return get_all_syllabi()

def get_syllabus(skill_id: int):
    detail = get_syllabus_detail(skill_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Syllabus {skill_id} not found")
    return detail

def generate_syllabus(payload: GenerateSyllabusRequest):
    skill = get_skill(payload.email, payload.skill)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"No subscription found for '{payload.skill}'")

    skill_id = get_skill_id_by_email_and_skill(payload.email, payload.skill)
    if skill_id is None:
        raise HTTPException(status_code=404, detail="Skill ID not found")

    syllabus_data = generate_syllabus_json(payload.skill, skill["days"], skill["hours"])
    if syllabus_data is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate syllabus (Gemini returned no data). "
            "Confirm .env is beside config.py and restart the API; check uvicorn logs.",
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
        skill["user_id"], payload.skill, syllabus_data, skill["hours"], skill_id
    ):
        raise HTTPException(
            status_code=500,
            detail="Syllabus was generated but could not be saved to the database",
        )
    return {"status": "success", "message": f"Syllabus generated for '{payload.skill}'"}
