"""add_pricing_to_user_api_keys

Revision ID: l0m1n2o3p4q5
Revises: k9l0m1n2o3p4
Create Date: 2026-05-06 10:00:00.000000

Adds input_price_per_m_usd and output_price_per_m_usd to user_api_keys.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "l0m1n2o3p4q5"
down_revision: Union[str, Sequence[str], None] = "k9l0m1n2o3p4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("user_api_keys", sa.Column("input_price_per_m_usd", sa.Float(), nullable=True))
    op.add_column("user_api_keys", sa.Column("output_price_per_m_usd", sa.Float(), nullable=True))

def downgrade() -> None:
    op.drop_column("user_api_keys", "output_price_per_m_usd")
    op.drop_column("user_api_keys", "input_price_per_m_usd")
