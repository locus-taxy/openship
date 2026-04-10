from fastapi import APIRouter, Depends, Query, Request
from models.user import User
from schemas.skill import GenerateSyllabusRequest
from dependencies.auth import get_current_user
from controllers import syllabus as syllabus_controller
from limiter import limiter

router = APIRouter(tags=["syllabus"])

@router.get("/syllabi")
def list_syllabi(current_user: User = Depends(get_current_user)):
    return syllabus_controller.list_syllabi(current_user)

@router.get("/syllabi/search")
def search_syllabi(
    q: str = Query("", description="Keyword to search"),
    current_user: User = Depends(get_current_user),
):
    return syllabus_controller.search(q, current_user)

@router.get("/syllabi/{skill_id}")
def get_syllabus(skill_id: int, current_user: User = Depends(get_current_user)):
    return syllabus_controller.get_syllabus(skill_id, current_user)

@router.patch("/syllabi/{skill_id}/share")
def toggle_share(skill_id: int, enable: bool, current_user: User = Depends(get_current_user)):
    return syllabus_controller.toggle_share(skill_id, enable, current_user)

@router.post("/generate-syllabus")
def generate_syllabus(
    payload: GenerateSyllabusRequest, current_user: User = Depends(get_current_user)
):
    return syllabus_controller.generate_syllabus(payload, current_user)

@router.get("/public/syllabi/{skill_id}")
@limiter.limit("30/minute")
def get_public_syllabus(skill_id: int, request: Request):
    return syllabus_controller.get_public_syllabus(skill_id)
