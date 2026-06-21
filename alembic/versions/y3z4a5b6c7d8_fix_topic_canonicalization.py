"""fix_topic_canonicalization

Revision ID: y3z4a5b6c7d8
Revises: x2y3z4a5b6c7
Create Date: 2026-06-20 00:00:00.000000

Two schema changes that together prevent phantom LLM-generated topic names
(e.g. "Reinforcing: Arrays") from polluting BKT state and the forgetting curve:

1. daily_tasks.is_remediation_day — flags chapters that are review/reinforcement
   days so their LLM-generated topic names are excluded from canonical topic lists.

2. week_remediation_topics — stores the canonical weak/forgotten topic names used
   when planning each ML-generated week so quiz questions can tag answers against
   the original topic, not the alias name the LLM chose for the chapter.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "y3z4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "x2y3z4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "daily_tasks",
        sa.Column("is_remediation_day", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "week_remediation_topics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "skill_id", sa.Integer(), sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(255), nullable=False),
        sa.Column("topic_type", sa.String(16), nullable=False),
        sa.UniqueConstraint(
            "skill_id", "week", "topic", name="uq_week_remediation_skill_week_topic"
        ),
        sa.CheckConstraint(
            "topic_type IN ('weak', 'forgotten')", name="ck_week_remediation_topic_type"
        ),
    )
    op.create_index("ix_week_remediation_topics_skill_id", "week_remediation_topics", ["skill_id"])

def downgrade() -> None:
    op.drop_index("ix_week_remediation_topics_skill_id", table_name="week_remediation_topics")
    op.drop_table("week_remediation_topics")
    op.drop_column("daily_tasks", "is_remediation_day")
