"""add_onboarding_docs_and_ingestion_jobs

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-06-30 01:00:00.000000

Creates onboarding_docs and ingestion_jobs for the Confluence ingestion
funnel (Phase 2).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
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

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("total_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_jobs_company_id", "ingestion_jobs", ["company_id"])

def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_company_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_index("ix_onboarding_docs_company_id", table_name="onboarding_docs")
    op.drop_table("onboarding_docs")
