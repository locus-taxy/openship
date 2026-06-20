"""add_onboarding_tables

Revision ID: y3z4a5b6c7d8
Revises: x2y3z4a5b6c7
Create Date: 2026-06-19 00:00:00.000000

Creates onboarding_plans and onboarding_days tables for the onboarding prototype.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "y3z4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "x2y3z4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "onboarding_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("company", sa.String(), nullable=False, server_default="Locus"),
        sa.Column("status", sa.String(), nullable=False, server_default="generated"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "onboarding_days",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("content_blocks", sa.Text(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["onboarding_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_onboarding_days_plan_id", "onboarding_days", ["plan_id"])

def downgrade() -> None:
    op.drop_index("ix_onboarding_days_plan_id", table_name="onboarding_days")
    op.drop_table("onboarding_days")
    op.drop_table("onboarding_plans")
