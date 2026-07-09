"""shrink document_chunks.embedding from 768 to 384 dims

Embeddings moved from Gemini (768-dim) to a local fastembed model
(BAAI/bge-small-en-v1.5, 384-dim). The column has no stored vectors yet, so we
just retype it and rebuild the HNSW index. Existing pages re-embed on next ingest.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-01
"""

from alembic import op

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(384)")
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(768)")
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
