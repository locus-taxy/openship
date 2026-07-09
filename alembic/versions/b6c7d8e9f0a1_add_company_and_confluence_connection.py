"""add_company_and_confluence_connection

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-06-30 00:00:00.000000

Creates companies and confluence_connections tables for the Confluence
integration layer (Phase 1: connection).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, Sequence[str], None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_companies_domain", "companies", ["domain"], unique=True)

    op.create_table(
        "confluence_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("site_url", sa.String(length=512), nullable=True),
        sa.Column("cloud_id", sa.String(length=255), nullable=True),
        sa.Column("space_keys", sa.Text(), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("webhook_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("connected_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["connected_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_confluence_connections_company"),
    )
    op.create_index(
        "ix_confluence_connections_company_id",
        "confluence_connections",
        ["company_id"],
    )

def downgrade() -> None:
    op.drop_index("ix_confluence_connections_company_id", table_name="confluence_connections")
    op.drop_table("confluence_connections")
    op.drop_index("ix_companies_domain", table_name="companies")
    op.drop_table("companies")
