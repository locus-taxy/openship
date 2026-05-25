from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func
from sqlalchemy import Integer, ForeignKey, UniqueConstraint

CONTENT_STYLES = ("balanced", "example_heavy", "theory_first", "reinforcement")

class ContentStyleArm(SQLModel, table=True):
    __tablename__ = "content_style_arms"
    __table_args__ = (
        UniqueConstraint(
            "skill_id", "user_id", "style", name="uq_content_style_arms_skill_user_style"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: int = Field(
        sa_column=Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    )
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    )
    style: str = Field(max_length=50)  # one of CONTENT_STYLES
    alpha: float = Field(default=1.0)  # wins + 1
    beta: float = Field(default=1.0)  # losses + 1
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )
