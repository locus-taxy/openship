"""drop the unused space_keys column from confluence_connections

Leftover from the pre-pivot design where the user hand-picked spaces to ingest.
Since ingestion now covers every space automatically, the column is never read
or written. Per-page space is tracked on document_pages.space_key instead.

Revision ID: onb_drop_space_keys
Revises: onb_ingest_phase_spaces
Create Date: 2026-07-02
"""

import sqlalchemy as sa
from alembic import op

revision = "onb_drop_space_keys"
down_revision = "onb_ingest_phase_spaces"
branch_labels = None
depends_on = None

def upgrade():
    op.drop_column("confluence_connections", "space_keys")

def downgrade():
    op.add_column(
        "confluence_connections",
        sa.Column("space_keys", sa.Text(), nullable=True),
    )
