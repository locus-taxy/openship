"""add_share_enabled_to_onboarding_plans

Revision ID: z4a5b6c7d8e9
Revises: y3z4a5b6c7d8
Create Date: 2026-06-19 01:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "y3z4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "onboarding_plans",
        sa.Column("share_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

def downgrade() -> None:
    op.drop_column("onboarding_plans", "share_enabled")
