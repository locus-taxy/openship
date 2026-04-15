"""add_gemini_api_key_to_users

Revision ID: b94d7cc53099
Revises: a3f2c1d8e905
Create Date: 2026-04-15 12:11:53.293424

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b94d7cc53099"
down_revision: Union[str, Sequence[str], None] = "a3f2c1d8e905"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("users", sa.Column("gemini_api_key", sa.String(length=512), nullable=True))

def downgrade() -> None:
    op.drop_column("users", "gemini_api_key")
