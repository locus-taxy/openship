from fastapi import APIRouter

from schemas.skill import GenerateContentRequest, GenerateChapterContentRequest
from controllers import content as content_controller

router = APIRouter(tags=["content"])


@router.post("/generate-content")
def generate_content(payload: GenerateContentRequest):
    return content_controller.generate_skill_content(payload)


@router.post("/generate-content/chapter")
def generate_chapter_content(payload: GenerateChapterContentRequest):
    return content_controller.generate_chapter(payload)


@router.get("/chapter/{task_id}")
def get_chapter(task_id: int):
    return content_controller.get_chapter(task_id)
