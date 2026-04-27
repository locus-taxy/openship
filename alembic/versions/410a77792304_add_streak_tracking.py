"""add streak tracking

Revision ID: 410a77792304
Revises: a3f2c1d8e905
Create Date: 2026-04-23 06:43:07.533651

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "410a77792304"
down_revision: Union[str, Sequence[str], None] = "a3f2c1d8e905"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "daily_tasks", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "user_streaks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("current_streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column("longest_streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_activity_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_streaks_user_id", "user_streaks", ["user_id"], unique=True)

def downgrade() -> None:
    op.drop_index("ix_user_streaks_user_id", table_name="user_streaks")
    op.drop_table("user_streaks")
    op.drop_column("daily_tasks", "completed_at")
