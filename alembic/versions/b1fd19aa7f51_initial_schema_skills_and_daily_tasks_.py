"""initial schema - skills and daily_tasks tables

Revision ID: b1fd19aa7f51
Revises:
Create Date: 2026-03-31 13:05:21.557896

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b1fd19aa7f51"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.String, nullable=False),
        sa.Column("email", sa.String, nullable=False),
        sa.Column("skill", sa.String, nullable=False),
        sa.Column("days", sa.Integer, nullable=False, server_default="90"),
        sa.Column("hours", sa.Integer, nullable=False, server_default="1"),
        sa.Column("stop_sending", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_skills_email", "skills", ["email"])

    op.create_table(
        "daily_tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.String, nullable=False),
        sa.Column("skill", sa.String, nullable=False),
        sa.Column(
            "skill_id", sa.Integer, sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("month", sa.Integer, nullable=True),
        sa.Column("week", sa.Integer, nullable=True),
        sa.Column("day", sa.Integer, nullable=True),
        sa.Column("topic", sa.String, nullable=True),
        sa.Column("task", sa.String, nullable=True),
        sa.Column("hours", sa.Integer, nullable=True),
        sa.Column("newsletter", sa.String, nullable=True),
        sa.Column("completed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("stop_sending", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_daily_tasks_skill_id", "daily_tasks", ["skill_id"])


def downgrade() -> None:
    op.drop_index("ix_daily_tasks_skill_id", table_name="daily_tasks")
    op.drop_table("daily_tasks")
    op.drop_index("ix_skills_email", table_name="skills")
    op.drop_table("skills")
