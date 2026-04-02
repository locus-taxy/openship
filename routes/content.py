from fastapi import APIRouter, Depends
from models.user import User
from schemas.skill import GenerateContentRequest, GenerateChapterContentRequest
from dependencies.auth import get_current_user
from controllers import content as content_controller

router = APIRouter(tags=["content"])

@router.post("/generate-content")
def generate_content(
    payload: GenerateContentRequest, current_user: User = Depends(get_current_user)
):
    return content_controller.generate_skill_content(payload)

@router.post("/generate-content/chapter")
def generate_chapter_content(
    payload: GenerateChapterContentRequest, current_user: User = Depends(get_current_user)
):
    return content_controller.generate_chapter(payload)

@router.get("/chapter/{task_id}")
def get_chapter(task_id: int, current_user: User = Depends(get_current_user)):
    return content_controller.get_chapter(task_id)
