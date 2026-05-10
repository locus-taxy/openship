"""add_currency_to_users

Revision ID: m1n2o3p4q5r6
Revises: l0m1n2o3p4q5
Create Date: 2026-05-06 10:01:00.000000

Adds display_currency and currency_exchange_rate to users.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "m1n2o3p4q5r6"
down_revision: Union[str, Sequence[str], None] = "l0m1n2o3p4q5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("display_currency", sa.String(8), nullable=True, server_default="USD"),
    )
    op.add_column(
        "users",
        sa.Column("currency_exchange_rate", sa.Float(), nullable=True, server_default="1.0"),
    )

def downgrade() -> None:
    op.drop_column("users", "currency_exchange_rate")
    op.drop_column("users", "display_currency")
