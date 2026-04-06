from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func
from sqlalchemy import Integer, ForeignKey


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
    newsletter: Optional[str] = None
    completed: bool = Field(default=False)
    stop_sending: bool = Field(default=False)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
