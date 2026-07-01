"""Section-aware RAG Q&A over the company knowledge base."""

from typing import Optional

from fastapi import HTTPException

from services import retrieval as retrieval_service
from services import llm as llm_service

_RETRIEVE_K = 8

def query(
    company_id: int,
    question: str,
    provider: str,
    api_key: str,
    model: Optional[str],
) -> dict:
    """Retrieve relevant chunks and answer the question, with citations."""
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="Ask a question.")
    chunks = retrieval_service.retrieve(company_id, question, k=_RETRIEVE_K)
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No documents are available yet. Connect Confluence and ingest docs first.",
        )
    context = "\n\n".join(f"=== {c['title']} ===\n{c['content']}" for c in chunks)
    answer = llm_service.answer_from_context(
        question=question, context=context, provider=provider, api_key=api_key, model=model
    )
    if not answer:
        raise HTTPException(status_code=500, detail="Failed to generate an answer.")

    seen: set = set()
    citations = []
    for c in chunks:
        key = c["page_id"]
        if key not in seen:
            seen.add(key)
            citations.append({"title": c["title"], "page_id": c["page_id"]})
    return {"answer": answer, "citations": citations}
