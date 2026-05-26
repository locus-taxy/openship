"""fix_user_model_prices_user_id_type

Revision ID: s7t8u9v0w1x2
Revises: r6s7t8u9v0w1
Create Date: 2026-05-26 00:00:00.000000

The user_model_prices table was created with user_id as VARCHAR (from an
earlier SQLModel create_all call using user_id: str).  The migration
q5r6s7t8u9v0 intended it to be INTEGER with a FK to users.id, but the
table already existed so the fix never landed.  This migration corrects it.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s7t8u9v0w1x2"
down_revision: Union[str, Sequence[str], None] = "r6s7t8u9v0w1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()

    # Skip if column is already INTEGER (idempotent for fresh DBs).
    result = conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'user_model_prices' AND column_name = 'user_id'"
        )
    ).fetchone()
    if result is None or result[0] == "integer":
        return

    # Drop the index that covers user_id (required before type change).
    op.drop_index("ix_user_model_prices_user_id", table_name="user_model_prices")

    # Drop the unique constraint (covers user_id; must be dropped before alter).
    op.drop_constraint("uq_user_model_price", "user_model_prices", type_="unique")

    # Cast the column to INTEGER.  Any existing rows with non-numeric user_id
    # would fail here — that's intentional; bad data should surface early.
    op.alter_column(
        "user_model_prices",
        "user_id",
        existing_type=sa.String(),
        type_=sa.Integer(),
        postgresql_using="user_id::integer",
    )

    # Restore the index and unique constraint.
    op.create_index("ix_user_model_prices_user_id", "user_model_prices", ["user_id"])
    op.create_unique_constraint(
        "uq_user_model_price", "user_model_prices", ["user_id", "provider", "model"]
    )

    # Add the foreign key to users.id if not already present.
    existing_fks = conn.execute(
        sa.text(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_name = 'user_model_prices' AND constraint_type = 'FOREIGN KEY'"
        )
    ).fetchall()
    fk_names = {row[0] for row in existing_fks}
    if not any("user" in n for n in fk_names):
        op.create_foreign_key(
            None, "user_model_prices", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

def downgrade() -> None:
    # Reverse: drop FK, cast back to VARCHAR, restore index and unique constraint.
    conn = op.get_bind()
    fk_rows = conn.execute(
        sa.text(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_name = 'user_model_prices' AND constraint_type = 'FOREIGN KEY'"
        )
    ).fetchall()
    for row in fk_rows:
        op.drop_constraint(row[0], "user_model_prices", type_="foreignkey")

    op.drop_index("ix_user_model_prices_user_id", table_name="user_model_prices")
    op.drop_constraint("uq_user_model_price", "user_model_prices", type_="unique")

    op.alter_column(
        "user_model_prices",
        "user_id",
        existing_type=sa.Integer(),
        type_=sa.String(),
        postgresql_using="user_id::text",
    )

    op.create_index("ix_user_model_prices_user_id", "user_model_prices", ["user_id"])
    op.create_unique_constraint(
        "uq_user_model_price", "user_model_prices", ["user_id", "provider", "model"]
    )
