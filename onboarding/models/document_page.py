from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

class DocumentPage(SQLModel, table=True):
    """One ingested document (a Confluence page or a Jira issue). Its text is split
    into DocumentChunk rows for embedding + retrieval. `source` says where it came
    from; `confluence_page_id`/`space_key` hold the source's id/container (page id +
    space for Confluence; issue key + project key for Jira)."""

    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "source", "confluence_page_id", name="uq_document_pages_company_page"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    source: str = Field(default="confluence", max_length=32, index=True)  # confluence | jira
    confluence_page_id: str = Field(max_length=255)
    version: Optional[int] = Field(default=None)  # skip re-embed if unchanged
    space_key: Optional[str] = Field(default=None, max_length=128)
    title: str = Field(max_length=512)
    content_text: Optional[str] = Field(default=None)  # cleaned page text
    # Structured Jira fields (null for Confluence) — power exact person lookups and
    # counts without parsing them back out of the flattened text.
    assignee: Optional[str] = Field(default=None, max_length=255, index=True)
    reporter: Optional[str] = Field(default=None, max_length=255, index=True)
    status: Optional[str] = Field(default=None, max_length=128)
    # Source-specific extras that don't warrant their own column — Jira: issue_type,
    # priority, labels, created/updated, resolution, status_category; Confluence:
    # author, last_editor, breadcrumb (folder path), labels, updated, type. Adding a
    # new field here never needs a migration.
    meta: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
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
