"""drop_quizzes_skill_id_unique

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r6
Create Date: 2026-05-25

The original quizzes migration created a UNIQUE constraint on skill_id alone
(quizzes_skill_id_key). The adaptive-ML migration added the correct composite
UNIQUE(skill_id, week) but only dropped the ix_quizzes_skill_id index, leaving
the old single-column unique constraint intact. That constraint prevents adding
a second quiz (week 2, 3 ...) for a skill that already has a week-1 quiz.

This migration drops the stale constraint.
"""

from alembic import op

revision: str = "n2o3p4q5r6s7"
down_revision = "m1n2o3p4q5r6"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # IF EXISTS makes this safe for both existing installs (constraint still
    # present) and fresh installs that already dropped it via a corrected
    # m1n2o3p4q5r6.
    op.execute("ALTER TABLE quizzes DROP CONSTRAINT IF EXISTS quizzes_skill_id_key")

def downgrade() -> None:
    op.create_unique_constraint("quizzes_skill_id_key", "quizzes", ["skill_id"])
