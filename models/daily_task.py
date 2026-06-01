from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func
from sqlalchemy import Integer, ForeignKey, Text

class DailyTask(SQLModel, table=True):
    __tablename__ = "daily_tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str
    skill: str
    skill_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), index=True),
    )
    month: Optional[int] = None
    week: Optional[int] = None
    day: Optional[int] = None
    topic: Optional[str] = None
    task: Optional[str] = None
    hours: Optional[int] = None
    newsletter: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    content_blocks: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    input_tokens: Optional[int] = Field(default=None)
    output_tokens: Optional[int] = Field(default=None)
    generation_cost_usd: Optional[float] = Field(default=None)
    completed: bool = Field(default=False)
    stop_sending: bool = Field(default=False)
    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, nullable=True),
    )
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )
