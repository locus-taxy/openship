"""create_quizzes_and_questions

Revision ID: j8k9l0m1n2o3
Revises: i7j8k9l0m1n2
Create Date: 2026-04-28 10:01:00.000000

Creates the quizzes and quiz_questions tables.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "j8k9l0m1n2o3"
down_revision: Union[str, Sequence[str], None] = "i7j8k9l0m1n2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "quizzes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("difficulty", sa.String(20), nullable=False, server_default="beginner"),
        sa.Column("pass_score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="available"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_id"),
        sa.CheckConstraint(
            "difficulty IN ('beginner', 'intermediate', 'advanced')",
            name="ck_quizzes_difficulty",
        ),
        sa.CheckConstraint(
            "status IN ('available', 'passed')",
            name="ck_quizzes_status",
        ),
        sa.CheckConstraint(
            "pass_score >= 0 AND pass_score <= 100",
            name="ck_quizzes_pass_score",
        ),
    )
    op.create_index("ix_quizzes_skill_id", "quizzes", ["skill_id"])

    op.create_table(
        "quiz_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quiz_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("option_a", sa.Text(), nullable=False),
        sa.Column("option_b", sa.Text(), nullable=False),
        sa.Column("option_c", sa.Text(), nullable=False),
        sa.Column("option_d", sa.Text(), nullable=False),
        sa.Column("correct_option", sa.String(1), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "correct_option IN ('A', 'B', 'C', 'D')",
            name="ck_quiz_questions_correct_option",
        ),
    )
    op.create_index("ix_quiz_questions_quiz_id", "quiz_questions", ["quiz_id"])

def downgrade() -> None:
    op.drop_index("ix_quiz_questions_quiz_id", table_name="quiz_questions")
    op.drop_table("quiz_questions")
    op.drop_index("ix_quizzes_skill_id", table_name="quizzes")
    op.drop_table("quizzes")
