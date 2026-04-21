"""user_api_keys_table

Revision ID: e3f4g5h6i7j8
Revises: d2e3f4a5b6c7
Create Date: 2026-04-17 10:00:00.000000

Creates the user_api_keys table and migrates existing per-provider key columns
from users into it. Existing keys are migrated as plaintext (they predate
encryption). The decrypt_api_key() helper handles legacy plaintext values.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = "e3f4g5h6i7j8"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Create the new user_api_keys table
    op.create_table(
        "user_api_keys",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("llm_provider", sa.String(length=50), nullable=False),
        sa.Column("llm_model", sa.String(length=100), nullable=True),
        sa.Column("api_key", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_user_api_keys_user_id", "user_api_keys", ["user_id"])

    # Migrate existing per-provider key columns from users → user_api_keys.
    # `col` is a column name from a hardcoded list — not user input — so
    # f-string interpolation is safe here. `provider` is bound as a parameter.
    conn = op.get_bind()
    for provider, col in [
        ("gemini", "gemini_key"),
        ("openai", "openai_key"),
        ("anthropic", "anthropic_key"),
        ("mistral", "mistral_key"),
    ]:
        conn.execute(
            text(
                "INSERT INTO user_api_keys (user_id, llm_provider, llm_model, api_key) "
                f"SELECT id, :provider, llm_model, {col} "
                f"FROM users WHERE {col} IS NOT NULL"
            ),
            {"provider": provider},
        )

    # Drop the now-redundant columns from users
    op.drop_column("users", "gemini_key")
    op.drop_column("users", "openai_key")
    op.drop_column("users", "anthropic_key")
    op.drop_column("users", "mistral_key")
    op.drop_column("users", "llm_model")

def downgrade() -> None:
    op.add_column("users", sa.Column("gemini_key", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("openai_key", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("anthropic_key", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("mistral_key", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("llm_model", sa.String(length=100), nullable=True))

    # `col` is from a hardcoded list; `provider` is bound as a parameter.
    conn = op.get_bind()
    for provider, col in [
        ("gemini", "gemini_key"),
        ("openai", "openai_key"),
        ("anthropic", "anthropic_key"),
        ("mistral", "mistral_key"),
    ]:
        conn.execute(
            text(
                f"UPDATE users SET {col} = ("
                f"SELECT api_key FROM user_api_keys "
                f"WHERE user_api_keys.user_id = users.id AND user_api_keys.llm_provider = :provider"
                f") WHERE EXISTS ("
                f"SELECT 1 FROM user_api_keys "
                f"WHERE user_api_keys.user_id = users.id AND user_api_keys.llm_provider = :provider"
                f")"
            ),
            {"provider": provider},
        )

    op.drop_index("ix_user_api_keys_user_id", "user_api_keys")
    op.drop_table("user_api_keys")
