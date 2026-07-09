from fastapi import APIRouter, Request

from onboarding.controllers import knowledge as knowledge_controller
from onboarding.schemas.knowledge import KnowledgeQueryRequest, ChatMessageRequest

router = APIRouter(tags=["knowledge"])

@router.post("/knowledge/query")
def query(payload: KnowledgeQueryRequest, request: Request):
    return knowledge_controller.query(payload, request.state.user)

@router.get("/knowledge/chats")
def list_chats(request: Request):
    return knowledge_controller.list_chats(request.state.user)

@router.post("/knowledge/chats")
def create_chat(request: Request):
    return knowledge_controller.create_chat(request.state.user)

@router.get("/knowledge/chats/{chat_id}")
def get_chat(chat_id: int, request: Request):
    return knowledge_controller.get_chat(chat_id, request.state.user)

@router.delete("/knowledge/chats/{chat_id}")
def delete_chat(chat_id: int, request: Request):
    return knowledge_controller.delete_chat(chat_id, request.state.user)

@router.post("/knowledge/chats/{chat_id}/messages")
def post_message(chat_id: int, payload: ChatMessageRequest, request: Request):
    return knowledge_controller.post_message(chat_id, payload, request.state.user)
