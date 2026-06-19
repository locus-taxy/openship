"""add_is_technical_to_skills

Revision ID: x2y3z4a5b6c7
Revises: w1x2y3z4a5b6
Create Date: 2026-06-18 00:00:00.000000

Stores the result of a lightweight LLM domain classification so chapter
generation can apply the correct prompt rules for technical vs non-technical skills.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "x2y3z4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "w1x2y3z4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "skills",
        sa.Column("is_technical", sa.Boolean(), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("skills", "is_technical")
