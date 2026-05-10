from fastapi import APIRouter, Request
from schemas.skill import GenerateContentRequest, GenerateChapterContentRequest
from controllers import content as content_controller
from controllers.content import CompleteChapterBody

router = APIRouter(tags=["content"])

@router.post("/generate-content")
def generate_content(payload: GenerateContentRequest, request: Request):
    return content_controller.generate_skill_content(payload, request.state.user)

@router.post("/generate-content/chapter")
def generate_chapter_content(payload: GenerateChapterContentRequest, request: Request):
    return content_controller.generate_chapter(payload, request.state.user)

@router.get("/chapter/{task_id}")
def get_chapter(task_id: int, request: Request):
    return content_controller.get_chapter(task_id, request.state.user)

@router.post("/chapter/{task_id}/complete")
def complete_chapter(task_id: int, body: CompleteChapterBody, request: Request):
    return content_controller.complete_chapter(task_id, request.state.user, body.local_date)

@router.get("/streak")
def get_streak(request: Request):
    return content_controller.get_streak(request.state.user)

@router.get("/analytics/cost")
def get_cost_analytics(request: Request):
    return content_controller.get_cost_analytics(request.state.user)
