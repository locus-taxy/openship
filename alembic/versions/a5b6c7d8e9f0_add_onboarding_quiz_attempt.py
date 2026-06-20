"""add_onboarding_quiz_attempt

Revision ID: a5b6c7d8e9f0
Revises: z4a5b6c7d8e9
Create Date: 2026-06-19 10:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, Sequence[str], None] = "z4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "onboarding_plans",
        sa.Column("quiz_questions", sa.Text(), nullable=True),
    )
    op.create_table(
        "onboarding_quiz_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("correct", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("answers", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["onboarding_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

def downgrade() -> None:
    op.drop_table("onboarding_quiz_attempts")
    op.drop_column("onboarding_plans", "quiz_questions")
