"""add_quiz_difficulty_to_skills

Revision ID: i7j8k9l0m1n2
Revises: h6i7j8k9l0m1
Create Date: 2026-04-28 10:00:00.000000

Adds quiz_difficulty column to the skills table.
Default is 'beginner' for all existing courses.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "i7j8k9l0m1n2"
down_revision: Union[str, Sequence[str], None] = "bc8a8a18c75c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "skills",
        sa.Column(
            "quiz_difficulty",
            sa.String(20),
            nullable=False,
            server_default="beginner",
        ),
    )

def downgrade() -> None:
    op.drop_column("skills", "quiz_difficulty")
