"""add updated_at to users table

Revision ID: 8cdc61e32195
Revises: 1ce8af32f6cb
Create Date: 2026-04-07 11:02:06.805559

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "8cdc61e32195"
down_revision: Union[str, Sequence[str], None] = "1ce8af32f6cb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("users", "updated_at")
