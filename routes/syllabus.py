from fastapi import APIRouter, Depends
from models.user import User
from schemas.skill import GenerateSyllabusRequest
from dependencies.auth import get_current_user
from controllers import syllabus as syllabus_controller

router = APIRouter(tags=["syllabus"])

@router.get("/syllabi")
def list_syllabi(current_user: User = Depends(get_current_user)):
    return syllabus_controller.list_syllabi(current_user)

@router.get("/syllabi/{skill_id}")
def get_syllabus(skill_id: int, current_user: User = Depends(get_current_user)):
    return syllabus_controller.get_syllabus(skill_id)

@router.post("/generate-syllabus")
def generate_syllabus(
    payload: GenerateSyllabusRequest, current_user: User = Depends(get_current_user)
):
    return syllabus_controller.generate_syllabus(payload, current_user)
