from fastapi import APIRouter
from schemas.skill import GenerateSyllabusRequest
from controllers import syllabus as syllabus_controller

router = APIRouter(tags=["syllabus"])


@router.get("/syllabi")
def list_syllabi():
    return syllabus_controller.list_syllabi()


@router.get("/syllabi/{skill_id}")
def get_syllabus(skill_id: int):
    return syllabus_controller.get_syllabus(skill_id)


@router.post("/generate-syllabus")
def generate_syllabus(payload: GenerateSyllabusRequest):
    return syllabus_controller.generate_syllabus(payload)
