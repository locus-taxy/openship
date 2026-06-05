"""rename_pricing_cols_in_user_api_keys

Revision ID: r6s7t8u9v0w1
Revises: q5r6s7t8u9v0
Create Date: 2026-05-25 00:00:00.000000

Renames input_price_per_m_usd -> input_per_1m_usd and
output_price_per_m_usd -> output_per_1m_usd in user_api_keys,
for databases that ran the l0m1n2o3p4q5 migration before the
column names were standardised. Databases already on the new
names are unaffected (the migration inspects before acting).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r6s7t8u9v0w1"
down_revision: Union[str, Sequence[str], None] = "q5r6s7t8u9v0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("user_api_keys")}
    if "input_price_per_m_usd" in cols:
        op.alter_column(
            "user_api_keys", "input_price_per_m_usd", new_column_name="input_per_1m_usd"
        )
    if "output_price_per_m_usd" in cols:
        op.alter_column(
            "user_api_keys", "output_price_per_m_usd", new_column_name="output_per_1m_usd"
        )

def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("user_api_keys")}
    if "input_per_1m_usd" in cols:
        op.alter_column(
            "user_api_keys", "input_per_1m_usd", new_column_name="input_price_per_m_usd"
        )
    if "output_per_1m_usd" in cols:
        op.alter_column(
            "user_api_keys", "output_per_1m_usd", new_column_name="output_price_per_m_usd"
        )
