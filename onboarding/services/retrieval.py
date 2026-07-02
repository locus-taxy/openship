"""Semantic retrieval over the company knowledge base (pgvector)."""

import logging
from typing import List

from sqlmodel import Session, select

from database import engine
from onboarding.models.document_chunk import DocumentChunk
from onboarding.models.document_page import DocumentPage
from onboarding.services import embeddings as embedding_service

logger = logging.getLogger(__name__)

_DEFAULT_K = 12

def retrieve(company_id: int, query: str, k: int = _DEFAULT_K) -> List[dict]:
    """Return the k most semantically similar active chunks for a query,
    each as {title, content, page_id}."""
    query_vector = embedding_service.embed_query(query)
    with Session(engine) as session:
        rows = session.exec(
            select(DocumentChunk.content, DocumentPage.title, DocumentPage.confluence_page_id)
            .join(DocumentPage, DocumentChunk.page_id == DocumentPage.id)
            .where(DocumentChunk.company_id == company_id)
            .where(DocumentPage.is_active == True)  # noqa: E712
            .order_by(DocumentChunk.embedding.cosine_distance(query_vector))
            .limit(k)
        ).all()
    return [{"content": content, "title": title, "page_id": pid} for content, title, pid in rows]

def retrieve_context(company_id: int, query: str, k: int = _DEFAULT_K) -> str:
    """Retrieve and format chunks as a single context string for a prompt."""
    chunks = retrieve(company_id, query, k)
    return "\n\n".join(f"=== {c['title']} ===\n{c['content']}" for c in chunks)
