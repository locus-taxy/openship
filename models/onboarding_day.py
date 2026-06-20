from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func
from sqlalchemy import Integer, ForeignKey, Text

class OnboardingDay(SQLModel, table=True):
    __tablename__ = "onboarding_days"

    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(
        sa_column=Column(Integer, ForeignKey("onboarding_plans.id", ondelete="CASCADE"), index=True)
    )
    day: int  # 1–7
    topic: str
    task: str  # brief description of what to cover
    content_blocks: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )  # JSON
    completed: bool = Field(default=False)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )
