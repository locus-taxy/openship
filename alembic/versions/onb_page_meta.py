"""add JSONB meta column to document_pages (source-specific extras)

A catch-all for per-source metadata (Jira: type/priority/labels/dates/resolution;
Confluence: author/breadcrumb/labels/updated) so new fields never need a migration.

Revision ID: onb_page_meta
Revises: onb_jira_fields
Create Date: 2026-07-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "onb_page_meta"
down_revision = "onb_jira_fields"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("document_pages", sa.Column("meta", JSONB(), nullable=True))

def downgrade():
    op.drop_column("document_pages", "meta")
