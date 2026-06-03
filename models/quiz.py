from typing import Any, Optional
from datetime import datetime
from pydantic import model_validator
from sqlmodel import SQLModel, Field, Column, DateTime, func
from sqlalchemy import Integer, ForeignKey, UniqueConstraint

WEEKLY_PASS_SCORE = 60
FINAL_PASS_SCORE = 70

class Quiz(SQLModel, table=True):
    __tablename__ = "quizzes"
    __table_args__ = (UniqueConstraint("skill_id", "week", name="uq_quizzes_skill_week"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: int = Field(
        sa_column=Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    )
    week: int = Field(default=0)  # 0 = final quiz, 1..N = per-week quiz
    pass_score: int = Field(default=WEEKLY_PASS_SCORE)
    status: str = Field(default="available")  # available | passed
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )

    @model_validator(mode="before")
    @classmethod
    def _default_pass_score(cls, values: Any) -> Any:
        if isinstance(values, dict) and "pass_score" not in values:
            week = values.get("week", 0)
            values["pass_score"] = WEEKLY_PASS_SCORE if week else FINAL_PASS_SCORE
        return values
