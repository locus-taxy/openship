from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func
from sqlalchemy import Integer, ForeignKey

class Quiz(SQLModel, table=True):
    __tablename__ = "quizzes"

    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("skills.id", ondelete="CASCADE"), unique=True, index=True
        )
    )
    difficulty: str = Field(default="beginner")
    pass_score: int  # 60 / 70 / 80
    status: str = Field(default="available")  # available | passed
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )
