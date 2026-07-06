from typing import Any, Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func
from pgvector.sqlalchemy import Vector

# Embedding output dimension. Must match config.EMBEDDING_DIMENSIONS and the
# fastembed model (BAAI/bge-small-en-v1.5 → 384).
EMBEDDING_DIM = 384

class DocumentChunk(SQLModel, table=True):
    """A ~800-token slice of a page, with its embedding for semantic search.
    Text is stored on first pass; `embedding` is filled in a second pass so
    ingestion is resumable."""

    __tablename__ = "document_chunks"

    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    page_id: int = Field(foreign_key="document_pages.id", index=True)
    source: str = Field(default="confluence", max_length=32, index=True)  # confluence | jira
    chunk_index: int = Field(default=0)
    content: str
    embedding: Optional[Any] = Field(default=None, sa_column=Column(Vector(EMBEDDING_DIM)))
    token_count: Optional[int] = Field(default=None)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
