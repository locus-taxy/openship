from onboarding.services import confluence as confluence_service

def connect(user):
    return confluence_service.start_connect(user)

def callback(code: str, state: str):
    return confluence_service.handle_callback(code, state)

def status(user):
    return confluence_service.get_status(user)

def connections_status(user):
    return confluence_service.get_connections_status(user)

def ingest(user, background_tasks, source="confluence"):
    return confluence_service.begin_ingest(
        user=user, background_tasks=background_tasks, source=source
    )

def ingest_status(job_id, user):
    return confluence_service.get_ingest_status(user, job_id)

def webhook(payload, secret, background_tasks):
    # Verify synchronously (bad secret → 401 now), then acknowledge instantly and do the
    # fetch+embed in the background so a burst of webhooks can't block web workers.
    confluence_service.verify_webhook_secret(secret)
    background_tasks.add_task(confluence_service.handle_webhook, payload)
    return {"status": "accepted"}

def jira_webhook(payload, secret, background_tasks):
    confluence_service.verify_jira_webhook_secret(secret)
    background_tasks.add_task(confluence_service.handle_jira_webhook, payload)
    return {"status": "accepted"}

def reconcile(user, background_tasks, source="confluence"):
    return confluence_service.begin_reconcile(
        user=user, background_tasks=background_tasks, source=source
    )
