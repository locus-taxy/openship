"""add phase + space counters to ingestion_jobs

Adds staged-progress columns so the UI can show reading / indexing / embedding
progress distinctly (previously it was blind during the multi-minute read phase).

Revision ID: onb_ingest_phase_spaces
Revises: f3a4b5c6d7e8
Create Date: 2026-07-02
"""

import sqlalchemy as sa
from alembic import op

revision = "onb_ingest_phase_spaces"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("ingestion_jobs", sa.Column("phase", sa.String(length=32), nullable=True))
    op.add_column(
        "ingestion_jobs",
        sa.Column("total_spaces", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("processed_spaces", sa.Integer(), nullable=False, server_default="0"),
    )

def downgrade():
    op.drop_column("ingestion_jobs", "processed_spaces")
    op.drop_column("ingestion_jobs", "total_spaces")
    op.drop_column("ingestion_jobs", "phase")
