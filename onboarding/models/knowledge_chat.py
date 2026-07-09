from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func

class KnowledgeChat(SQLModel, table=True):
    """A single Q&A conversation over the company knowledge base (one per user,
    company-scoped). Messages hang off it; ordered by created_at."""

    __tablename__ = "knowledge_chats"

    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    user_id: str = Field(index=True)
    title: str = Field(default="New chat", max_length=200)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )
