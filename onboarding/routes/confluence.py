from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, Query, Request
from fastapi.responses import RedirectResponse

from onboarding.controllers import confluence as confluence_controller

router = APIRouter(tags=["confluence"])

@router.post("/confluence/connect")
def connect(request: Request):
    return confluence_controller.connect(request.state.user)

@router.get("/confluence/callback")
def callback(code: str = Query(...), state: str = Query(...)):
    redirect_url = confluence_controller.callback(code, state)
    return RedirectResponse(url=redirect_url)

@router.get("/confluence/status")
def status(request: Request):
    return confluence_controller.status(request.state.user)

@router.get("/connections/status")
def connections_status(request: Request):
    return confluence_controller.connections_status(request.state.user)

@router.post("/confluence/ingest")
def ingest(
    request: Request, background_tasks: BackgroundTasks, source: str = Query(default="confluence")
):
    return confluence_controller.ingest(request.state.user, background_tasks, source)

@router.get("/confluence/ingest/{job_id}")
def ingest_status(job_id: int, request: Request):
    return confluence_controller.ingest_status(job_id, request.state.user)

@router.post("/webhooks/confluence")
def webhook(
    payload: dict,
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: Optional[str] = Header(default=None),
):
    secret = x_webhook_secret or request.query_params.get("secret")
    return confluence_controller.webhook(payload, secret, background_tasks)

@router.post("/webhooks/jira")
def jira_webhook(
    payload: dict,
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: Optional[str] = Header(default=None),
):
    secret = x_webhook_secret or request.query_params.get("secret")
    return confluence_controller.jira_webhook(payload, secret, background_tasks)

@router.post("/confluence/reconcile")
def reconcile(
    request: Request, background_tasks: BackgroundTasks, source: str = Query(default="confluence")
):
    return confluence_controller.reconcile(request.state.user, background_tasks, source)
