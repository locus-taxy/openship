"""add_content_blocks_to_daily_tasks

Revision ID: o3p4q5r6s7t8
Revises: n2o3p4q5r6s7
Create Date: 2026-05-21 23:00:00.000000

Adds content_blocks column to daily_tasks for structured chapter content.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "o3p4q5r6s7t8"
down_revision: Union[str, Sequence[str], None] = "n2o3p4q5r6s7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("daily_tasks", sa.Column("content_blocks", sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column("daily_tasks", "content_blocks")
