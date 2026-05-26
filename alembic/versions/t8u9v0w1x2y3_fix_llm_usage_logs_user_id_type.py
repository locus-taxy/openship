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

    existing_fks = conn.execute(
        sa.text(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_name = 'llm_usage_logs' AND constraint_type = 'FOREIGN KEY'"
        )
    ).fetchall()
    fk_names = {row[0] for row in existing_fks}
    if not any("user" in n for n in fk_names):
        op.create_foreign_key(
            None, "llm_usage_logs", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

def downgrade() -> None:
    conn = op.get_bind()
    fk_rows = conn.execute(
        sa.text(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_name = 'llm_usage_logs' AND constraint_type = 'FOREIGN KEY'"
        )
    ).fetchall()
    for row in fk_rows:
        op.drop_constraint(row[0], "llm_usage_logs", type_="foreignkey")

    op.drop_index("ix_llm_usage_logs_user_id", table_name="llm_usage_logs")

    op.alter_column(
        "llm_usage_logs",
        "user_id",
        existing_type=sa.Integer(),
        type_=sa.String(),
        postgresql_using="user_id::text",
    )

    op.create_index("ix_llm_usage_logs_user_id", "llm_usage_logs", ["user_id"])
