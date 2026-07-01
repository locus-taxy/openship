from fastapi import APIRouter, Request

from controllers import knowledge as knowledge_controller
from schemas.knowledge import KnowledgeQueryRequest

router = APIRouter(tags=["knowledge"])

@router.post("/knowledge/query")
def query(payload: KnowledgeQueryRequest, request: Request):
    return knowledge_controller.query(payload, request.state.user)
