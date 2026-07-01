"""add_document_pages_and_chunks

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a1b2
Create Date: 2026-07-01 02:00:00.000000

Adds the RAG knowledge base: document_pages (one row per Confluence page) and
document_chunks (embedded slices), plus chunk/embed progress on ingestion_jobs.

Requires the pgvector extension to be enabled once by a superuser:
    CREATE EXTENSION IF NOT EXISTS vector;
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 768

def upgrade() -> None:
    op.create_table(
        "document_pages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("confluence_page_id", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("space_key", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
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
            "company_id", "confluence_page_id", name="uq_document_pages_company_page"
        ),
    )
    op.create_index("ix_document_pages_company_id", "document_pages", ["company_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("page_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["document_pages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_chunks_company_id", "document_chunks", ["company_id"])
    op.create_index("ix_document_chunks_page_id", "document_chunks", ["page_id"])
    # Approximate-nearest-neighbour index for cosine distance.
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.add_column(
        "ingestion_jobs",
        sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("embedded_chunks", sa.Integer(), nullable=False, server_default="0"),
    )

def downgrade() -> None:
    op.drop_column("ingestion_jobs", "embedded_chunks")
    op.drop_column("ingestion_jobs", "total_chunks")
    op.drop_index("ix_document_chunks_embedding", table_name="document_chunks")
    op.drop_index("ix_document_chunks_page_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_company_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_document_pages_company_id", table_name="document_pages")
    op.drop_table("document_pages")
