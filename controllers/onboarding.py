from schemas.onboarding import GenerateOnboardingRequest, SubmitQuizAttemptRequest
from services import onboarding as onboarding_service
from services import confluence as confluence_service
from services.llm import get_user_api_key, get_user_model, get_user_provider_name

def _company_id(user) -> int:
    return confluence_service.get_or_create_company_for_user(user).id

def list_plans(user):
    return onboarding_service.list_plans(user_id=str(user.id))

def toggle_share(plan_id: int, enable: bool, user):
    return onboarding_service.toggle_share(plan_id=plan_id, user_id=str(user.id), enable=enable)

def get_public_plan(plan_id: int):
    return onboarding_service.get_public_plan(plan_id=plan_id)

def generate_plan(payload: GenerateOnboardingRequest, user):
    provider = get_user_provider_name(user)
    api_key = get_user_api_key(user)
    model = get_user_model(user)
    return onboarding_service.generate_plan(
        user_id=str(user.id),
        role=payload.role,
        company=payload.company,
        provider=provider,
        api_key=api_key,
        model=model,
        company_id=_company_id(user),
    )

def get_plan(plan_id: int, user):
    return onboarding_service.get_plan(plan_id=plan_id, user_id=str(user.id))

def complete_day(plan_id: int, day_number: int, user):
    return onboarding_service.complete_day(
        plan_id=plan_id, day_number=day_number, user_id=str(user.id)
    )

def delete_plan(plan_id: int, user):
    return onboarding_service.delete_plan(plan_id=plan_id, user_id=str(user.id))

def get_day_content(plan_id: int, day_number: int, user, force: bool = False):
    provider = get_user_provider_name(user)
    api_key = get_user_api_key(user)
    model = get_user_model(user)
    return onboarding_service.get_day_content(
        plan_id=plan_id,
        day_number=day_number,
        user_id=str(user.id),
        provider=provider,
        api_key=api_key,
        model=model,
        company_id=_company_id(user),
        force=force,
    )

def get_quiz(plan_id: int, user):
    return onboarding_service.get_quiz(plan_id=plan_id, user_id=str(user.id))

def generate_quiz(plan_id: int, user):
    provider = get_user_provider_name(user)
    api_key = get_user_api_key(user)
    model = get_user_model(user)
    return onboarding_service.generate_quiz(
        plan_id=plan_id,
        user_id=str(user.id),
        provider=provider,
        api_key=api_key,
        model=model,
        company_id=_company_id(user),
    )

def submit_quiz_attempt(plan_id: int, payload: SubmitQuizAttemptRequest, user):
    return onboarding_service.save_quiz_attempt(
        plan_id=plan_id,
        user_id=str(user.id),
        answers=payload.answers,
    )
