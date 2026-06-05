"""drop_quizzes_skill_id_unique

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-25

The original quizzes migration created a UNIQUE constraint on skill_id alone
(quizzes_skill_id_key). The adaptive-ML migration added the correct composite
UNIQUE(skill_id, week) but only dropped the ix_quizzes_skill_id index, leaving
the old single-column unique constraint intact. That constraint prevents adding
a second quiz (week 2, 3 ...) for a skill that already has a week-1 quiz.

This migration drops the stale constraint.
"""

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # IF EXISTS makes this safe for both existing installs (constraint still
    # present) and fresh installs that already dropped it via a corrected
    # a1b2c3d4e5f6.
    op.execute("ALTER TABLE quizzes DROP CONSTRAINT IF EXISTS quizzes_skill_id_key")

def downgrade() -> None:
    op.create_unique_constraint("quizzes_skill_id_key", "quizzes", ["skill_id"])
