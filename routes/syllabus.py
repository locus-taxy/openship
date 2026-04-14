from fastapi import APIRouter, Query, Request
from schemas.skill import GenerateSyllabusRequest
from controllers import syllabus as syllabus_controller
from config import limiter

router = APIRouter(tags=["syllabus"])

@router.get("/syllabi")
def list_syllabi(request: Request):
    return syllabus_controller.list_syllabi(request.state.user)

@router.get("/syllabi/search")
def search_syllabi(request: Request, q: str = Query("", description="Keyword to search")):
    return syllabus_controller.search(q, request.state.user)

@router.get("/syllabi/{skill_id}")
def get_syllabus(skill_id: int, request: Request):
    return syllabus_controller.get_syllabus(skill_id, request.state.user)

@router.patch("/syllabi/{skill_id}/share")
def toggle_share(skill_id: int, enable: bool, request: Request):
    return syllabus_controller.toggle_share(skill_id, enable, request.state.user)

@router.post("/generate-syllabus")
def generate_syllabus(payload: GenerateSyllabusRequest, request: Request):
    return syllabus_controller.generate_syllabus(payload, request.state.user)

@router.get("/public/syllabi/{skill_id}")
@limiter.limit("10/minute")
def get_public_syllabus(skill_id: int, request: Request):
    return syllabus_controller.get_public_syllabus(skill_id)
