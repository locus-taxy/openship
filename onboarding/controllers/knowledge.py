from onboarding.services import knowledge as knowledge_service
from onboarding.services import confluence as confluence_service
from services.llm import get_user_api_key, get_user_model, get_user_provider_name

def query(payload, user):
    company = confluence_service.get_or_create_company_for_user(user)
    return knowledge_service.query(
        company_id=company.id,
        question=payload.question,
        provider=get_user_provider_name(user),
        api_key=get_user_api_key(user),
        model=get_user_model(user),
    )
