"""add structured jira fields (assignee / reporter / status) to document_pages

Storing these per issue (instead of parsing them out of the flattened text) powers
exact person lookups and involvement counts for the knowledge chat.

Revision ID: onb_jira_fields
Revises: onb_job_source
Create Date: 2026-07-04
"""

import sqlalchemy as sa
from alembic import op

revision = "onb_jira_fields"
down_revision = "onb_job_source"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("document_pages", sa.Column("assignee", sa.String(length=255), nullable=True))
    op.add_column("document_pages", sa.Column("reporter", sa.String(length=255), nullable=True))
    op.add_column("document_pages", sa.Column("status", sa.String(length=128), nullable=True))
    op.create_index("ix_document_pages_assignee", "document_pages", ["assignee"])
    op.create_index("ix_document_pages_reporter", "document_pages", ["reporter"])

def downgrade():
    op.drop_index("ix_document_pages_reporter", table_name="document_pages")
    op.drop_index("ix_document_pages_assignee", table_name="document_pages")
    op.drop_column("document_pages", "status")
    op.drop_column("document_pages", "reporter")
    op.drop_column("document_pages", "assignee")
