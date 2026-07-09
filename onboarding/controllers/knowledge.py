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

def list_chats(user):
    company = confluence_service.get_or_create_company_for_user(user)
    return knowledge_service.list_chats(company.id, str(user.id))

def create_chat(user):
    company = confluence_service.get_or_create_company_for_user(user)
    return knowledge_service.create_chat(company.id, str(user.id))

def get_chat(chat_id, user):
    company = confluence_service.get_or_create_company_for_user(user)
    return knowledge_service.get_chat(chat_id, company.id, str(user.id))

def delete_chat(chat_id, user):
    company = confluence_service.get_or_create_company_for_user(user)
    return knowledge_service.delete_chat(chat_id, company.id, str(user.id))

def post_message(chat_id, payload, user):
    company = confluence_service.get_or_create_company_for_user(user)
    return knowledge_service.post_message(
        chat_id=chat_id,
        company_id=company.id,
        user_id=str(user.id),
        question=payload.question,
        provider=get_user_provider_name(user),
        api_key=get_user_api_key(user),
        model=get_user_model(user),
    )
