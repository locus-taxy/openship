"""add_prices_to_llm_usage_logs

Revision ID: u9v0w1x2y3z4
Revises: t8u9v0w1x2y3
Create Date: 2026-06-02 00:00:00.000000

Store the per-million-token prices that were in effect at generation time,
so cost calculations can be audited even after prices change.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u9v0w1x2y3z4"
down_revision: Union[str, Sequence[str], None] = "t8u9v0w1x2y3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "llm_usage_logs",
        sa.Column("input_price_per_1m_usd", sa.Float(), nullable=True),
    )
    op.add_column(
        "llm_usage_logs",
        sa.Column("output_price_per_1m_usd", sa.Float(), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("llm_usage_logs", "output_price_per_1m_usd")
    op.drop_column("llm_usage_logs", "input_price_per_1m_usd")
