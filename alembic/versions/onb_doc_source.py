"""add source to document_pages / document_chunks (confluence | jira)

Multi-source knowledge base: tag each document/chunk with where it came from so
retrieval can scope per feature (onboarding = confluence; chat = all sources).

Revision ID: onb_doc_source
Revises: onb_job_kind
Create Date: 2026-07-03
"""

import sqlalchemy as sa
from alembic import op

revision = "onb_doc_source"
down_revision = "onb_job_kind"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "document_pages",
        sa.Column("source", sa.String(length=32), nullable=False, server_default="confluence"),
    )
    op.add_column(
        "document_chunks",
        sa.Column("source", sa.String(length=32), nullable=False, server_default="confluence"),
    )
    op.create_index("ix_document_pages_source", "document_pages", ["source"])
    op.create_index("ix_document_chunks_source", "document_chunks", ["source"])
    # Widen the uniqueness key to include source (a Jira issue key and a Confluence
    # page id could otherwise theoretically collide within one company).
    op.drop_constraint("uq_document_pages_company_page", "document_pages", type_="unique")
    op.create_unique_constraint(
        "uq_document_pages_company_page",
        "document_pages",
        ["company_id", "source", "confluence_page_id"],
    )

def downgrade():
    op.drop_constraint("uq_document_pages_company_page", "document_pages", type_="unique")
    op.create_unique_constraint(
        "uq_document_pages_company_page", "document_pages", ["company_id", "confluence_page_id"]
    )
    op.drop_index("ix_document_chunks_source", table_name="document_chunks")
    op.drop_index("ix_document_pages_source", table_name="document_pages")
    op.drop_column("document_chunks", "source")
    op.drop_column("document_pages", "source")
