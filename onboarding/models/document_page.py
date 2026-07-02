from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func
from sqlalchemy import UniqueConstraint

class DocumentPage(SQLModel, table=True):
    """One Confluence page ingested into the knowledge base. Its text is split
    into DocumentChunk rows for embedding + retrieval."""

    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("company_id", "confluence_page_id", name="uq_document_pages_company_page"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    confluence_page_id: str = Field(max_length=255)
    version: Optional[int] = Field(default=None)  # skip re-embed if unchanged
    space_key: Optional[str] = Field(default=None, max_length=128)
    title: str = Field(max_length=512)
    content_text: Optional[str] = Field(default=None)  # cleaned page text
    is_active: bool = Field(default=True)  # false when archived/removed upstream
    last_synced_at: Optional[datetime] = Field(default=None)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )
