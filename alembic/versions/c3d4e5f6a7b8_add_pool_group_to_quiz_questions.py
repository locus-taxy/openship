"""add_pool_group_to_quiz_questions

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-26

Adds pool_group (nullable int) to quiz_questions.
Questions sharing the same pool_group within a quiz are variants of each other;
get_quiz_with_questions samples exactly one per pool_group so each attempt
presents a fresh variant instead of the same question.
"""

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "quiz_questions",
        sa.Column("pool_group", sa.Integer(), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("quiz_questions", "pool_group")
