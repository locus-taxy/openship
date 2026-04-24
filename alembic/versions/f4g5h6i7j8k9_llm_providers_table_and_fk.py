"""llm_providers_table_and_fk

Revision ID: f4g5h6i7j8k9
Revises: e3f4g5h6i7j8
Create Date: 2026-04-21 10:00:00.000000

Creates the llm_providers lookup table, seeds the 4 supported providers,
then migrates users.llm_provider (VARCHAR) and user_api_keys.llm_provider (VARCHAR)
to integer FK columns pointing at llm_providers.id.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = "f4g5h6i7j8k9"
down_revision: Union[str, Sequence[str], None] = "e3f4g5h6i7j8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROVIDERS = [
    ("gemini", "Google Gemini"),
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
    ("mistral", "Mistral"),
]

def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create llm_providers lookup table
    op.create_table(
        "llm_providers",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # 2. Seed the 4 providers
    for name, label in PROVIDERS:
        conn.execute(
            text("INSERT INTO llm_providers (name, label) VALUES (:name, :label)"),
            {"name": name, "label": label},
        )

    # 3. Add new integer FK columns (nullable during migration)
    op.add_column("users", sa.Column("llm_provider_id", sa.Integer(), nullable=True))
    op.add_column("user_api_keys", sa.Column("llm_provider_id", sa.Integer(), nullable=True))

    # 4. Populate FK columns from existing VARCHAR columns
    for name, _ in PROVIDERS:
        conn.execute(
            text(
                "UPDATE users SET llm_provider_id = (SELECT id FROM llm_providers WHERE name = :name) "
                "WHERE llm_provider = :name"
            ),
            {"name": name},
        )
        conn.execute(
            text(
                "UPDATE user_api_keys SET llm_provider_id = (SELECT id FROM llm_providers WHERE name = :name) "
                "WHERE llm_provider = :name"
            ),
            {"name": name},
        )

    # 5. Add FK constraints
    op.create_foreign_key(
        "fk_users_llm_provider", "users", "llm_providers", ["llm_provider_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_user_api_keys_llm_provider",
        "user_api_keys",
        "llm_providers",
        ["llm_provider_id"],
        ["id"],
    )

    # 6. Drop old VARCHAR columns
    op.drop_column("users", "llm_provider")
    op.drop_column("user_api_keys", "llm_provider")

def downgrade() -> None:
    conn = op.get_bind()

    op.add_column("users", sa.Column("llm_provider", sa.String(length=50), nullable=True))
    op.add_column("user_api_keys", sa.Column("llm_provider", sa.String(length=50), nullable=True))

    # Restore VARCHAR values from the lookup table
    conn.execute(
        text(
            "UPDATE users SET llm_provider = lp.name "
            "FROM llm_providers lp WHERE lp.id = users.llm_provider_id"
        )
    )
    conn.execute(
        text(
            "UPDATE user_api_keys SET llm_provider = lp.name "
            "FROM llm_providers lp WHERE lp.id = user_api_keys.llm_provider_id"
        )
    )

    op.drop_constraint("fk_users_llm_provider", "users", type_="foreignkey")
    op.drop_constraint("fk_user_api_keys_llm_provider", "user_api_keys", type_="foreignkey")
    op.drop_column("users", "llm_provider_id")
    op.drop_column("user_api_keys", "llm_provider_id")
    op.drop_table("llm_providers")
