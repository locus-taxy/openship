"""drop_onboarding_docs

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-07-01 03:00:00.000000

The old approve/confirm doc store is replaced by document_pages + document_chunks.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.drop_index("ix_onboarding_docs_company_id", table_name="onboarding_docs")
    op.drop_table("onboarding_docs")

def downgrade() -> None:
    op.create_table(
        "onboarding_docs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("confluence_page_id", sa.String(length=255), nullable=False),
        sa.Column("confluence_version", sa.Integer(), nullable=True),
        sa.Column("space_key", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=True),
        sa.Column("role_tags", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "confluence_page_id", name="uq_onboarding_docs_company_page"
        ),
    )
    op.create_index("ix_onboarding_docs_company_id", "onboarding_docs", ["company_id"])
