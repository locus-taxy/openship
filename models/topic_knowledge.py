from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func
from sqlalchemy import Integer, ForeignKey, UniqueConstraint

class TopicKnowledge(SQLModel, table=True):
    __tablename__ = "topic_knowledge"
    __table_args__ = (
        UniqueConstraint(
            "skill_id", "user_id", "topic", name="uq_topic_knowledge_skill_user_topic"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: int = Field(
        sa_column=Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    )
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    )
    topic: str = Field(max_length=255)
    week: int  # which week this topic was first introduced
    p_known: float = Field(default=0.10)  # BKT mastery score
    attempts: int = Field(default=0)
    correct: int = Field(default=0)
    p_transit: float = Field(default=0.10)  # learn rate
    p_guess: float = Field(default=0.20)
    p_slip: float = Field(default=0.10)
    last_studied_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, nullable=True),
    )
    stability_days: float = Field(default=5.0)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )
