from services import confluence as confluence_service

def connect(user):
    return confluence_service.start_connect(user)

def callback(code: str, state: str):
    return confluence_service.handle_callback(code, state)

def status(user):
    return confluence_service.get_status(user)

def ingest(user, background_tasks):
    return confluence_service.begin_ingest(user=user, background_tasks=background_tasks)

def ingest_status(job_id, user):
    return confluence_service.get_ingest_status(user, job_id)

def webhook(payload, secret):
    confluence_service.verify_webhook_secret(secret)
    return confluence_service.handle_webhook(payload)

def reconcile(user):
    company = confluence_service.get_or_create_company_for_user(user)
    return confluence_service.reconcile_company(company.id)
