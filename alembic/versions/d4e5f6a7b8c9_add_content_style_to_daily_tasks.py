"""add_content_style_to_daily_tasks

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-26

Adds content_style (nullable text) to daily_tasks.
Stores which bandit arm style was used when generating the chapter
(balanced / example_heavy / theory_first / reinforcement).
"""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "daily_tasks",
        sa.Column("content_style", sa.Text(), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("daily_tasks", "content_style")
