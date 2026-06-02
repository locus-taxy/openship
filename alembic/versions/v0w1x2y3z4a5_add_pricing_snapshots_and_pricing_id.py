"""add_pricing_snapshots_and_pricing_id

Revision ID: v0w1x2y3z4a5
Revises: u9v0w1x2y3z4
Create Date: 2026-06-02 00:01:00.000000

Creates the pricing_snapshots table (immutable, insert-only rows that freeze
the price in effect at generation time) and adds pricing_id FK to daily_tasks.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v0w1x2y3z4a5"
down_revision: Union[str, Sequence[str], None] = "u9v0w1x2y3z4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "pricing_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_per_1m_usd", sa.Float(), nullable=False),
        sa.Column("output_per_1m_usd", sa.Float(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "daily_tasks",
        sa.Column("pricing_id", sa.Integer(), sa.ForeignKey("pricing_snapshots.id"), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("daily_tasks", "pricing_id")
    op.drop_table("pricing_snapshots")
