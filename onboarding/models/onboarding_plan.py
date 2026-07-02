from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func

class OnboardingPlan(SQLModel, table=True):
    __tablename__ = "onboarding_plans"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str
    role: str
    company: str = Field(default="Locus")
    status: str = Field(default="generated")  # generated | completed
    share_enabled: bool = Field(default=False)
    quiz_questions: Optional[str] = Field(default=None)  # JSON TEXT cache
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )
