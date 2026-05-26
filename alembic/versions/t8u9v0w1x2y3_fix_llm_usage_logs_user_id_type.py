"""fix_llm_usage_logs_user_id_type

Revision ID: t8u9v0w1x2y3
Revises: s7t8u9v0w1x2
Create Date: 2026-05-26 00:01:00.000000

llm_usage_logs.user_id was created as character varying (the table was
created via SQLModel create_all when user_id was typed as str).  The model
now uses user_id: int with a FK to users.id, but SQLAlchemy binds the WHERE
parameter as INTEGER which PostgreSQL rejects against a varchar column.
This migration casts the column to INTEGER and adds the FK.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t8u9v0w1x2y3"
down_revision: Union[str, Sequence[str], None] = "s7t8u9v0w1x2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()

    result = conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'llm_usage_logs' AND column_name = 'user_id'"
        )
    ).fetchone()
    if result is None or result[0] == "integer":
        return

    op.drop_index("ix_llm_usage_logs_user_id", table_name="llm_usage_logs")

    op.alter_column(
        "llm_usage_logs",
        "user_id",
        existing_type=sa.String(),
        type_=sa.Integer(),
        postgresql_using="user_id::integer",
    )

    op.create_index("ix_llm_usage_logs_user_id", "llm_usage_logs", ["user_id"])

    fk_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON kcu.constraint_name = tc.constraint_name "
            "  AND kcu.table_name = tc.table_name "
            "JOIN information_schema.referential_constraints rc "
            "  ON rc.constraint_name = tc.constraint_name "
            "JOIN information_schema.key_column_usage ccu "
            "  ON ccu.constraint_name = rc.unique_constraint_name "
            "WHERE tc.table_name = 'llm_usage_logs' "
            "  AND tc.constraint_type = 'FOREIGN KEY' "
            "  AND kcu.column_name = 'user_id' "
            "  AND ccu.table_name = 'users' "
            "  AND ccu.column_name = 'id'"
        )
    ).fetchone()
    if not fk_exists:
        op.create_foreign_key(
            None, "llm_usage_logs", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

def downgrade() -> None:
    conn = op.get_bind()
    fk_row = conn.execute(
        sa.text(
            "SELECT tc.constraint_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON kcu.constraint_name = tc.constraint_name "
            "  AND kcu.table_name = tc.table_name "
            "JOIN information_schema.referential_constraints rc "
            "  ON rc.constraint_name = tc.constraint_name "
            "JOIN information_schema.key_column_usage ccu "
            "  ON ccu.constraint_name = rc.unique_constraint_name "
            "WHERE tc.table_name = 'llm_usage_logs' "
            "  AND tc.constraint_type = 'FOREIGN KEY' "
            "  AND kcu.column_name = 'user_id' "
            "  AND ccu.table_name = 'users' "
            "  AND ccu.column_name = 'id'"
        )
    ).fetchone()
    if fk_row:
        op.drop_constraint(fk_row[0], "llm_usage_logs", type_="foreignkey")

    op.drop_index("ix_llm_usage_logs_user_id", table_name="llm_usage_logs")

    op.alter_column(
        "llm_usage_logs",
        "user_id",
        existing_type=sa.Integer(),
        type_=sa.String(),
        postgresql_using="user_id::text",
    )

    op.create_index("ix_llm_usage_logs_user_id", "llm_usage_logs", ["user_id"])
