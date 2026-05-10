"""add_cost_tracking_to_daily_tasks

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r6
Create Date: 2026-05-06 10:02:00.000000

Adds input_tokens, output_tokens, generation_cost_usd to daily_tasks.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "n2o3p4q5r6s7"
down_revision: Union[str, Sequence[str], None] = "m1n2o3p4q5r6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("daily_tasks", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("daily_tasks", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("daily_tasks", sa.Column("generation_cost_usd", sa.Float(), nullable=True))

def downgrade() -> None:
    op.drop_column("daily_tasks", "generation_cost_usd")
    op.drop_column("daily_tasks", "output_tokens")
    op.drop_column("daily_tasks", "input_tokens")
