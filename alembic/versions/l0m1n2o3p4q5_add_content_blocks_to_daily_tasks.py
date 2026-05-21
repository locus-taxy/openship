"""add_content_blocks_to_daily_tasks

Revision ID: l0m1n2o3p4q5
Revises: k9l0m1n2o3p4
Create Date: 2026-05-06 10:00:00.000000

Adds content_blocks column to daily_tasks for structured chapter content.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "l0m1n2o3p4q5"
down_revision: Union[str, Sequence[str], None] = "k9l0m1n2o3p4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("daily_tasks", sa.Column("content_blocks", sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column("daily_tasks", "content_blocks")
