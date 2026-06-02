"""add_pool_group_to_quiz_questions

Revision ID: o3p4q5r6s7t8
Revises: n2o3p4q5r6s7
Create Date: 2026-05-26

Adds pool_group (nullable int) to quiz_questions.
Questions sharing the same pool_group within a quiz are variants of each other;
get_quiz_with_questions samples exactly one per pool_group so each attempt
presents a fresh variant instead of the same question.
"""

from alembic import op
import sqlalchemy as sa

revision = "o3p4q5r6s7t8"
down_revision = "n2o3p4q5r6s7"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "quiz_questions",
        sa.Column("pool_group", sa.Integer(), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("quiz_questions", "pool_group")
