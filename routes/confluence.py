from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, Query, Request
from fastapi.responses import RedirectResponse

from controllers import confluence as confluence_controller
from schemas.confluence import ConfirmCandidatesRequest, IngestRequest

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

@router.get("/confluence/spaces")
def spaces(request: Request):
    return confluence_controller.list_spaces(request.state.user)

@router.post("/confluence/ingest")
def ingest(payload: IngestRequest, request: Request, background_tasks: BackgroundTasks):
    return confluence_controller.ingest(payload, request.state.user, background_tasks)

@router.get("/confluence/ingest/{job_id}")
def ingest_status(job_id: int, request: Request):
    return confluence_controller.ingest_status(job_id, request.state.user)

@router.get("/confluence/candidates")
def candidates(request: Request):
    return confluence_controller.get_candidates(request.state.user)

@router.patch("/confluence/candidates")
def confirm_candidates(payload: ConfirmCandidatesRequest, request: Request):
    return confluence_controller.confirm_candidates(payload, request.state.user)

@router.post("/webhooks/confluence")
def webhook(
    payload: dict, request: Request, x_webhook_secret: Optional[str] = Header(default=None)
):
    secret = x_webhook_secret or request.query_params.get("secret")
    return confluence_controller.webhook(payload, secret)

@router.post("/confluence/reconcile")
def reconcile(request: Request):
    return confluence_controller.reconcile(request.state.user)

@router.get("/confluence/gaps")
def gaps(request: Request):
    return confluence_controller.gaps(request.state.user)
