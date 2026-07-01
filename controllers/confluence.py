from services import confluence as confluence_service
from services.llm import get_user_api_key, get_user_model, get_user_provider_name

def connect(user):
    return confluence_service.start_connect(user)

def callback(code: str, state: str):
    return confluence_service.handle_callback(code, state)

def status(user):
    return confluence_service.get_status(user)

def list_spaces(user):
    return confluence_service.list_spaces(user)

def ingest(payload, user, background_tasks):
    provider = get_user_provider_name(user)
    api_key = get_user_api_key(user)
    model = get_user_model(user)
    return confluence_service.begin_ingest(
        user=user,
        space_keys=payload.space_keys,
        provider=provider,
        api_key=api_key,
        model=model,
        background_tasks=background_tasks,
    )

def ingest_status(job_id, user):
    return confluence_service.get_ingest_status(user, job_id)

def get_candidates(user):
    return confluence_service.get_candidates(user)

def confirm_candidates(payload, user):
    return confluence_service.confirm_candidates(user, payload.page_ids)

def webhook(payload, secret):
    confluence_service.verify_webhook_secret(secret)
    return confluence_service.handle_webhook(payload)

def reconcile(user):
    company = confluence_service.get_or_create_company_for_user(user)
    return confluence_service.reconcile_company(company.id)

def gaps(user):
    return confluence_service.detect_gaps(user)
