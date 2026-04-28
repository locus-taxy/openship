from fastapi import APIRouter, Request

import controllers.quiz as quiz_controller
from schemas.quiz import QuizSubmitRequest

router = APIRouter(prefix="/quiz", tags=["quiz"])

@router.post("/{skill_id}/generate")
def generate_quiz(skill_id: int, request: Request):
    return quiz_controller.generate_quiz_for_skill(skill_id, request.state.user)

@router.get("/{skill_id}")
def get_quiz(skill_id: int, request: Request):
    return quiz_controller.get_quiz(skill_id, request.state.user)

@router.post("/{skill_id}/submit")
def submit_quiz(skill_id: int, payload: QuizSubmitRequest, request: Request):
    return quiz_controller.submit_quiz(skill_id, payload, request.state.user)

@router.get("/{skill_id}/attempts")
def get_attempts(skill_id: int, request: Request):
    return quiz_controller.get_attempts(skill_id, request.state.user)
