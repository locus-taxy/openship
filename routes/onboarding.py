from fastapi import APIRouter, Query, Request
from schemas.onboarding import GenerateOnboardingRequest, SubmitQuizAttemptRequest
from controllers import onboarding as onboarding_controller
from config import limiter

router = APIRouter(tags=["onboarding"])

@router.get("/onboarding")
def list_plans(request: Request):
    return onboarding_controller.list_plans(request.state.user)

@router.post("/onboarding/generate")
def generate_plan(payload: GenerateOnboardingRequest, request: Request):
    return onboarding_controller.generate_plan(payload, request.state.user)

@router.get("/public/onboarding/{plan_id}")
@limiter.limit("20/minute")
def get_public_plan(plan_id: int, request: Request):
    return onboarding_controller.get_public_plan(plan_id)

@router.patch("/onboarding/{plan_id}/share")
def toggle_share(plan_id: int, enable: bool = Query(...), request: Request = None):
    return onboarding_controller.toggle_share(plan_id, enable, request.state.user)

@router.delete("/onboarding/{plan_id}")
def delete_plan(plan_id: int, request: Request):
    return onboarding_controller.delete_plan(plan_id, request.state.user)

@router.get("/onboarding/{plan_id}")
def get_plan(plan_id: int, request: Request):
    return onboarding_controller.get_plan(plan_id, request.state.user)

@router.get("/onboarding/{plan_id}/day/{day_number}")
def get_day_content(plan_id: int, day_number: int, request: Request, force: bool = Query(False)):
    return onboarding_controller.get_day_content(
        plan_id, day_number, request.state.user, force=force
    )

@router.post("/onboarding/{plan_id}/day/{day_number}/complete")
def complete_day(plan_id: int, day_number: int, request: Request):
    return onboarding_controller.complete_day(plan_id, day_number, request.state.user)

@router.get("/onboarding/{plan_id}/quiz")
def get_quiz(plan_id: int, request: Request):
    return onboarding_controller.get_quiz(plan_id, request.state.user)

@router.post("/onboarding/{plan_id}/quiz/generate")
def generate_quiz(plan_id: int, request: Request):
    return onboarding_controller.generate_quiz(plan_id, request.state.user)

@router.post("/onboarding/{plan_id}/quiz/attempt")
def submit_quiz_attempt(plan_id: int, payload: SubmitQuizAttemptRequest, request: Request):
    return onboarding_controller.submit_quiz_attempt(plan_id, payload, request.state.user)
