"""per_provider_keys_and_model_selection

Revision ID: d2e3f4a5b6c7
Revises: c1e2f3a4b5d6
Create Date: 2026-04-15 20:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1e2f3a4b5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Add per-provider key columns
    op.add_column("users", sa.Column("gemini_key", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("openai_key", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("anthropic_key", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("mistral_key", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("llm_model", sa.String(length=100), nullable=True))

    # Migrate existing llm_api_key into the right per-provider column
    conn = op.get_bind()
    conn.execute(
        text(
            "UPDATE users SET gemini_key = llm_api_key "
            "WHERE llm_provider = 'gemini' AND llm_api_key IS NOT NULL"
        )
    )
    conn.execute(
        text(
            "UPDATE users SET openai_key = llm_api_key "
            "WHERE llm_provider = 'openai' AND llm_api_key IS NOT NULL"
        )
    )
    conn.execute(
        text(
            "UPDATE users SET anthropic_key = llm_api_key "
            "WHERE llm_provider = 'anthropic' AND llm_api_key IS NOT NULL"
        )
    )
    conn.execute(
        text(
            "UPDATE users SET mistral_key = llm_api_key "
            "WHERE llm_provider = 'mistral' AND llm_api_key IS NOT NULL"
        )
    )

    # Drop old columns (llm_api_key replaced by per-provider columns;
    # gemini_api_key was a leftover from a prior migration on another branch)
    op.drop_column("users", "llm_api_key")

    # gemini_api_key may or may not exist depending on local DB state
    conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS gemini_api_key"))

def downgrade() -> None:
    op.add_column("users", sa.Column("llm_api_key", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("gemini_api_key", sa.String(length=512), nullable=True))

    conn = op.get_bind()
    conn.execute(
        text(
            "UPDATE users SET llm_api_key = CASE llm_provider "
            "WHEN 'gemini' THEN gemini_key "
            "WHEN 'openai' THEN openai_key "
            "WHEN 'anthropic' THEN anthropic_key "
            "WHEN 'mistral' THEN mistral_key "
            "END WHERE llm_provider IS NOT NULL"
        )
    )

    op.drop_column("users", "llm_model")
    op.drop_column("users", "mistral_key")
    op.drop_column("users", "anthropic_key")
    op.drop_column("users", "openai_key")
    op.drop_column("users", "gemini_key")
