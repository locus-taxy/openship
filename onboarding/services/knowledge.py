"""Section-aware RAG Q&A over the company knowledge base, plus persistent chats.

`query` is a one-shot Q&A. The chat_* functions add ChatGPT-style conversations:
persistent history per user, with prior turns fed back to the model for follow-ups.
"""

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from database import engine
from onboarding.models.knowledge_chat import KnowledgeChat
from onboarding.models.knowledge_message import KnowledgeMessage
from onboarding.services import retrieval as retrieval_service
from onboarding.services import generation as llm_service

_RETRIEVE_K = 8
# How many prior messages (user + assistant) to feed back as follow-up context.
_HISTORY_MESSAGES = 12

def _answer(company_id: int, question: str, provider, api_key, model, history=None) -> dict:
    """Retrieve relevant chunks and answer, with deduped citations. Shared by the
    one-shot query and the chat message path."""
    chunks = retrieval_service.retrieve(company_id, question, k=_RETRIEVE_K)
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No documents are available yet. Connect Confluence and ingest docs first.",
        )
    context = "\n\n".join(f"=== {c['title']} ===\n{c['content']}" for c in chunks)
    answer = llm_service.answer_from_context(
        question=question,
        context=context,
        provider=provider,
        api_key=api_key,
        model=model,
        history=history,
    )
    if not answer:
        raise HTTPException(status_code=500, detail="Failed to generate an answer.")
    return {"answer": answer, "citations": _dedupe_citations(chunks)}

def query(
    company_id: int,
    question: str,
    provider: str,
    api_key: str,
    model: Optional[str],
) -> dict:
    """One-shot: retrieve relevant chunks and answer the question, with citations."""
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="Ask a question.")
    return _answer(company_id, question, provider, api_key, model)

def _dedupe_citations(chunks: list) -> list:
    seen: set = set()
    citations = []
    for c in chunks:
        if c["page_id"] not in seen:
            seen.add(c["page_id"])
            citations.append({"title": c["title"], "page_id": c["page_id"]})
    return citations

def _blocks_to_text(blocks: list) -> str:
    """Flatten structured blocks to plain text — used as the assistant turn's text
    for conversation history and as a fallback. Keeps it lossy-but-useful."""
    parts = []
    for b in blocks:
        if b.get("content"):
            parts.append(str(b["content"]))
        elif b.get("items"):
            parts.append("\n".join(str(i) for i in b["items"]))
        elif b.get("headers"):
            parts.append(" | ".join(str(h) for h in b.get("headers", [])))
            for row in b.get("rows", []):
                parts.append(" | ".join(str(c) for c in row))
    # Empty on purpose (e.g. a divider-only answer): return "" rather than a sentinel
    # so it isn't fed back as poisoned history — the generator skips empty turns.
    return "\n\n".join(parts).strip()

def _answer_blocks(company_id, question, provider, api_key, model, history=None) -> dict:
    """Retrieve chunks and answer as structured content blocks, with citations."""
    chunks = retrieval_service.retrieve(company_id, question, k=_RETRIEVE_K)
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No documents are available yet. Connect Confluence and ingest docs first.",
        )
    context = "\n\n".join(f"=== {c['title']} ===\n{c['content']}" for c in chunks)
    result = llm_service.answer_blocks_from_context(
        question=question,
        context=context,
        provider=provider,
        api_key=api_key,
        model=model,
        history=history,
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to generate an answer.")
    # Only surface source chips when the answer actually used the docs — greetings
    # and general-knowledge answers shouldn't show (irrelevant) retrieved sources.
    citations = _dedupe_citations(chunks) if result.get("used_docs") else []
    return {"blocks": result["blocks"], "citations": citations}

# ── chats ──────────────────────────────────────────────────────────────────────

def _chat_dict(chat: KnowledgeChat) -> dict:
    return {
        "id": chat.id,
        "title": chat.title,
        "created_at": chat.created_at.isoformat() if chat.created_at else None,
        "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
    }

def _message_dict(msg: KnowledgeMessage) -> dict:
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "blocks": json.loads(msg.blocks) if msg.blocks else None,
        "citations": json.loads(msg.citations) if msg.citations else [],
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }

def _owned_chat(session: Session, chat_id: int, company_id: int, user_id: str) -> KnowledgeChat:
    chat = session.get(KnowledgeChat, chat_id)
    if chat is None or chat.company_id != company_id or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return chat

def list_chats(company_id: int, user_id: str) -> list:
    with Session(engine) as session:
        chats = session.exec(
            select(KnowledgeChat)
            .where(KnowledgeChat.company_id == company_id)
            .where(KnowledgeChat.user_id == user_id)
            .order_by(KnowledgeChat.updated_at.desc())
        ).all()
        return [_chat_dict(c) for c in chats]

def create_chat(company_id: int, user_id: str) -> dict:
    with Session(engine) as session:
        chat = KnowledgeChat(company_id=company_id, user_id=user_id, title="New chat")
        session.add(chat)
        session.commit()
        session.refresh(chat)
        return _chat_dict(chat)

def get_chat(chat_id: int, company_id: int, user_id: str) -> dict:
    with Session(engine) as session:
        chat = _owned_chat(session, chat_id, company_id, user_id)
        messages = session.exec(
            select(KnowledgeMessage)
            .where(KnowledgeMessage.chat_id == chat_id)
            .order_by(KnowledgeMessage.id)
        ).all()
        return {"chat": _chat_dict(chat), "messages": [_message_dict(m) for m in messages]}

def delete_chat(chat_id: int, company_id: int, user_id: str) -> dict:
    with Session(engine) as session:
        chat = _owned_chat(session, chat_id, company_id, user_id)
        session.delete(chat)
        session.commit()
        return {"deleted": True}

def post_message(
    chat_id: int,
    company_id: int,
    user_id: str,
    question: str,
    provider: str,
    api_key: str,
    model: Optional[str],
) -> dict:
    """Add a user turn, answer it (with prior turns as context), persist both, and
    return the two new messages."""
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="Ask a question.")
    question = question.strip()

    with Session(engine) as session:
        _owned_chat(session, chat_id, company_id, user_id)
        prior = session.exec(
            select(KnowledgeMessage)
            .where(KnowledgeMessage.chat_id == chat_id)
            .order_by(KnowledgeMessage.id)
        ).all()
        history = [{"role": m.role, "content": m.content} for m in prior][-_HISTORY_MESSAGES:]
        is_first = len(prior) == 0

    result = _answer_blocks(company_id, question, provider, api_key, model, history=history)

    with Session(engine) as session:
        chat = _owned_chat(session, chat_id, company_id, user_id)
        user_msg = KnowledgeMessage(chat_id=chat_id, role="user", content=question)
        assistant_msg = KnowledgeMessage(
            chat_id=chat_id,
            role="assistant",
            content=_blocks_to_text(result["blocks"]),
            blocks=json.dumps(result["blocks"]),
            citations=json.dumps(result["citations"]),
        )
        session.add(user_msg)
        session.add(assistant_msg)
        if is_first:
            chat.title = question[:80]
        chat.updated_at = datetime.now(timezone.utc)
        session.add(chat)
        session.commit()
        session.refresh(user_msg)
        session.refresh(assistant_msg)
        return {
            "user": _message_dict(user_msg),
            "assistant": _message_dict(assistant_msg),
            "title": chat.title,
        }
