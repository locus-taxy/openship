"""add source to ingestion_jobs (confluence | jira)

Lets a running/finished job say which product it ingested so the Connections UI
can label progress ("Ingesting Jira…") honestly.

Revision ID: onb_job_source
Revises: onb_doc_source
Create Date: 2026-07-03
"""

import sqlalchemy as sa
from alembic import op

revision = "onb_job_source"
down_revision = "onb_doc_source"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "ingestion_jobs",
        sa.Column("source", sa.String(length=32), nullable=False, server_default="confluence"),
    )

def downgrade():
    op.drop_column("ingestion_jobs", "source")
