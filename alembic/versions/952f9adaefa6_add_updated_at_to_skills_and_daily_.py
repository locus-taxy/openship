"""add updated_at to skills and daily_tasks tables

Revision ID: 952f9adaefa6
Revises: 8cdc61e32195
Create Date: 2026-04-07 11:03:31.856759

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "952f9adaefa6"
down_revision: Union[str, Sequence[str], None] = "8cdc61e32195"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "daily_tasks",
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
    )
    op.add_column(
        "skills",
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("skills", "updated_at")
    op.drop_column("daily_tasks", "updated_at")
