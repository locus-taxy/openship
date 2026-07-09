from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func

class OnboardingQuizAttempt(SQLModel, table=True):
    __tablename__ = "onboarding_quiz_attempts"

    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="onboarding_plans.id", ondelete="CASCADE")
    user_id: str
    score: int  # 0–100
    correct: int
    total: int
    answers: Optional[str] = Field(default=None)  # JSON: {"0": "a", "1": "b", ...}
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
