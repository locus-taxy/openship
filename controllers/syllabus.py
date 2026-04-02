from fastapi import HTTPException
from models.user import User
from schemas.skill import GenerateSyllabusRequest
from services.skill import (
    get_skill,
    get_all_syllabi,
    get_syllabus_detail,
    get_skill_id_by_email_and_skill,
)
from services.gemini import generate_syllabus_json
from services.daily_task import store_syllabus_tasks

def list_syllabi(current_user: User):
    return get_all_syllabi(email=current_user.email)

def get_syllabus(skill_id: int):
    detail = get_syllabus_detail(skill_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Syllabus {skill_id} not found")
    return detail

def generate_syllabus(payload: GenerateSyllabusRequest, current_user: User):
    email = current_user.email
    skill = get_skill(email, payload.skill)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"No subscription found for '{payload.skill}'")

    skill_id = get_skill_id_by_email_and_skill(email, payload.skill)
    if skill_id is None:
        raise HTTPException(status_code=404, detail="Skill ID not found")

    syllabus_data = generate_syllabus_json(payload.skill, skill["days"], skill["hours"])
    if not syllabus_data:
        raise HTTPException(status_code=500, detail="Failed to generate syllabus")

    store_syllabus_tasks(
        str(current_user.id), payload.skill, syllabus_data, skill["hours"], skill_id
    )
    return {"status": "success", "message": f"Syllabus generated for '{payload.skill}'"}
