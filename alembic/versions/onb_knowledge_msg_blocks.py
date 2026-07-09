"""add blocks column to knowledge_messages

Assistant turns are structured content blocks (same shape as onboarding day
content) so answers render richly. `content` keeps a plain-text flattening for
conversation history + fallback.

Revision ID: onb_knowledge_msg_blocks
Revises: onb_knowledge_chats
Create Date: 2026-07-03
"""

import sqlalchemy as sa
from alembic import op

revision = "onb_knowledge_msg_blocks"
down_revision = "onb_knowledge_chats"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("knowledge_messages", sa.Column("blocks", sa.Text(), nullable=True))

def downgrade():
    op.drop_column("knowledge_messages", "blocks")
