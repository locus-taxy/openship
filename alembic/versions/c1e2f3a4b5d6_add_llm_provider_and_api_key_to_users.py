"""add_llm_provider_and_api_key_to_users

Revision ID: c1e2f3a4b5d6
Revises: b94d7cc53099
Create Date: 2026-04-15 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c1e2f3a4b5d6"
down_revision: Union[str, Sequence[str], None] = "a3f2c1d8e905"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("users", sa.Column("llm_provider", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("llm_api_key", sa.String(length=512), nullable=True))

def downgrade() -> None:
    op.drop_column("users", "llm_api_key")
    op.drop_column("users", "llm_provider")
