"""create_user_model_prices

Revision ID: q5r6s7t8u9v0
Revises: p4q5r6s7t8u9
Create Date: 2026-05-22 00:30:00.000000

Per-model manual price overrides set by the user when auto-pricing is unavailable.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "q5r6s7t8u9v0"
down_revision: Union[str, Sequence[str], None] = "p4q5r6s7t8u9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "user_model_prices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_per_1m_usd", sa.Float(), nullable=False),
        sa.Column("output_per_1m_usd", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", "model", name="uq_user_model_price"),
    )
    op.create_index("ix_user_model_prices_user_id", "user_model_prices", ["user_id"])

def downgrade() -> None:
    op.drop_index("ix_user_model_prices_user_id", table_name="user_model_prices")
    op.drop_table("user_model_prices")
