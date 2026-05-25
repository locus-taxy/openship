from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func
from sqlalchemy import Index, Integer

class LlmUsageLog(SQLModel, table=True):
    __tablename__ = "llm_usage_logs"
    __table_args__ = (Index("ix_llm_usage_logs_user_id", "user_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str
    call_type: str  # "chapter", "syllabus", "quiz"
    ref_id: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    provider: str
    model: str
    input_tokens: Optional[int] = Field(default=None)
    output_tokens: Optional[int] = Field(default=None)
    cost_usd: Optional[float] = Field(default=None)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
