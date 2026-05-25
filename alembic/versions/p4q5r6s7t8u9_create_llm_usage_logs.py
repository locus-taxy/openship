"""create_llm_usage_logs

Revision ID: p4q5r6s7t8u9
Revises: o3p4q5r6s7t8
Create Date: 2026-05-21 23:30:00.000000

Append-only log of every LLM call made during chapter/syllabus/quiz generation.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "p4q5r6s7t8u9"
down_revision: Union[str, Sequence[str], None] = "o3p4q5r6s7t8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "llm_usage_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("call_type", sa.String(), nullable=False),
        sa.Column("ref_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_usage_logs_user_id", "llm_usage_logs", ["user_id"])

def downgrade() -> None:
    op.drop_index("ix_llm_usage_logs_user_id", table_name="llm_usage_logs")
    op.drop_table("llm_usage_logs")
