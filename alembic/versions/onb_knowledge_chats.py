"""add knowledge_chats + knowledge_messages for the chat UI

Persistent Q&A conversations over the company knowledge base (history sidebar,
multi-turn context). Messages cascade-delete with their chat.

Revision ID: onb_knowledge_chats
Revises: onb_drop_space_keys
Create Date: 2026-07-03
"""

import sqlalchemy as sa
from alembic import op

revision = "onb_knowledge_chats"
down_revision = "onb_drop_space_keys"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "knowledge_chats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False, server_default="New chat"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_chats_company_id", "knowledge_chats", ["company_id"])
    op.create_index("ix_knowledge_chats_user_id", "knowledge_chats", ["user_id"])

    op.create_table(
        "knowledge_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "chat_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_chats.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_messages_chat_id", "knowledge_messages", ["chat_id"])

def downgrade():
    op.drop_index("ix_knowledge_messages_chat_id", table_name="knowledge_messages")
    op.drop_table("knowledge_messages")
    op.drop_index("ix_knowledge_chats_user_id", table_name="knowledge_chats")
    op.drop_index("ix_knowledge_chats_company_id", table_name="knowledge_chats")
    op.drop_table("knowledge_chats")
