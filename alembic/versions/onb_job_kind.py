"""add kind to ingestion_jobs (ingest | reconcile)

Reconcile now runs as a tracked background job reusing ingestion_jobs; `kind`
distinguishes it from a full ingest so the UI can label progress correctly.

Revision ID: onb_job_kind
Revises: onb_knowledge_msg_blocks
Create Date: 2026-07-03
"""

import sqlalchemy as sa
from alembic import op

revision = "onb_job_kind"
down_revision = "onb_knowledge_msg_blocks"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "ingestion_jobs",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="ingest"),
    )

def downgrade():
    op.drop_column("ingestion_jobs", "kind")
