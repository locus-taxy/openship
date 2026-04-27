"""merge streak and multi-llm migration branches

Revision ID: bc8a8a18c75c
Revises: h6i7j8k9l0m1, 410a77792304
Create Date: 2026-04-27 11:14:44.499773

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "bc8a8a18c75c"
down_revision: Union[str, Sequence[str], None] = ("h6i7j8k9l0m1", "410a77792304")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    pass

def downgrade() -> None:
    """Downgrade schema."""
    pass
