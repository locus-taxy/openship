from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint, CheckConstraint

class WeekRemediationTopic(SQLModel, table=True):
    __tablename__ = "week_remediation_topics"
    __table_args__ = (
        UniqueConstraint("skill_id", "week", "topic", name="uq_week_remediation_skill_week_topic"),
        CheckConstraint(
            "topic_type IN ('weak', 'forgotten')", name="ck_week_remediation_topic_type"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    week: int
    topic: str = Field(max_length=255)
    topic_type: str = Field(max_length=16)  # "weak" or "forgotten"
