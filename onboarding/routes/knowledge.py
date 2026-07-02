from fastapi import APIRouter, Request

from onboarding.controllers import knowledge as knowledge_controller
from onboarding.schemas.knowledge import KnowledgeQueryRequest

router = APIRouter(tags=["knowledge"])

@router.post("/knowledge/query")
def query(payload: KnowledgeQueryRequest, request: Request):
    return knowledge_controller.query(payload, request.state.user)
