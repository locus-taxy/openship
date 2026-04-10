"""add share_enabled to skills

Revision ID: a3f2c1d8e905
Revises: 952f9adaefa6
Create Date: 2026-04-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a3f2c1d8e905"
down_revision: Union[str, Sequence[str], None] = "952f9adaefa6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "skills",
        sa.Column(
            "share_enabled",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
    )

def downgrade() -> None:
    op.drop_column("skills", "share_enabled")
