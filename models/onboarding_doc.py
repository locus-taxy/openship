from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func
from sqlalchemy import UniqueConstraint

class OnboardingDoc(SQLModel, table=True):
    """A Confluence page ingested for a company. Feeds plan/quiz generation
    only when approved AND active."""

    __tablename__ = "onboarding_docs"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "confluence_page_id", name="uq_onboarding_docs_company_page"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    confluence_page_id: str = Field(max_length=255)
    confluence_version: Optional[int] = Field(default=None)
    space_key: Optional[str] = Field(default=None, max_length=128)
    title: str = Field(max_length=512)
    content_markdown: Optional[str] = Field(default=None)
    role_tags: Optional[str] = Field(default=None)  # JSON TEXT, e.g. ["backend"]
    confidence: Optional[float] = Field(default=None)  # classifier score (Phase 2b)
    approved: bool = Field(default=False)  # admin confirmed (Phase 2b)
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
