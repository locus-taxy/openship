from fastapi import APIRouter, BackgroundTasks, Request

import controllers.quiz as quiz_controller
from schemas.quiz import QuizSubmitRequest

router = APIRouter(prefix="/quiz", tags=["quiz"])

# ── Weekly quiz routes ─────────────────────────────────────────────────────────

@router.post("/{skill_id}/week/{week}/generate")
def generate_weekly_quiz(skill_id: int, week: int, request: Request):
    return quiz_controller.generate_weekly_quiz_for_skill(skill_id, week, request.state.user)

@router.get("/{skill_id}/week/{week}")
def get_weekly_quiz(skill_id: int, week: int, request: Request):
    return quiz_controller.get_weekly_quiz(skill_id, week, request.state.user)

@router.post("/{skill_id}/week/{week}/submit")
def submit_weekly_quiz(
    skill_id: int,
    week: int,
    payload: QuizSubmitRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    return quiz_controller.submit_weekly_quiz(
        skill_id, week, payload, request.state.user, background_tasks
    )

# ── Final quiz routes ──────────────────────────────────────────────────────────

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

@router.get("/{skill_id}/attempts/latest")
def get_latest_attempt(skill_id: int, request: Request):
    return quiz_controller.get_latest_attempt(skill_id, request.state.user)

@router.get("/{skill_id}/week/{week}/attempts/latest")
def get_weekly_latest_attempt(skill_id: int, week: int, request: Request):
    return quiz_controller.get_weekly_latest_attempt(skill_id, week, request.state.user)

@router.delete("/{skill_id}/final")
def reset_final_quiz(skill_id: int, request: Request):
    return quiz_controller.reset_final_quiz(skill_id, request.state.user)
