"""unique_constraint_user_api_keys

Revision ID: g5h6i7j8k9l0
Revises: f4g5h6i7j8k9
Create Date: 2026-04-21 12:00:00.000000

Adds a unique constraint on (user_id, llm_provider_id) in user_api_keys
to prevent duplicate rows per user+provider.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "g5h6i7j8k9l0"
down_revision: Union[str, Sequence[str], None] = "f4g5h6i7j8k9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_unique_constraint(
        "uq_user_api_keys_user_provider",
        "user_api_keys",
        ["user_id", "llm_provider_id"],
    )

def downgrade() -> None:
    op.drop_constraint(
        "uq_user_api_keys_user_provider",
        "user_api_keys",
        type_="unique",
    )
