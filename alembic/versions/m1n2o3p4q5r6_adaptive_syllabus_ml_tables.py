"""adaptive syllabus ml tables

Revision ID: m1n2o3p4q5r6
Revises: l0m1n2o3p4q5
Create Date: 2026-05-21

Changes:
  - skills: remove quiz_difficulty, add generated_weeks, total_weeks
  - quizzes: remove difficulty, add week, replace UNIQUE(skill_id) with UNIQUE(skill_id, week)
  - quiz_questions: add topic column
  - new table: topic_knowledge
  - new table: content_style_arms
"""

from alembic import op
import sqlalchemy as sa

revision = "m1n2o3p4q5r6"
down_revision = "l0m1n2o3p4q5"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # ── skills ────────────────────────────────────────────────────────────────
    op.drop_column("skills", "quiz_difficulty")
    op.add_column(
        "skills", sa.Column("generated_weeks", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "skills", sa.Column("total_weeks", sa.Integer(), nullable=False, server_default="0")
    )

    # ── quizzes ───────────────────────────────────────────────────────────────
    # Drop the old unique index on skill_id alone
    op.drop_index("ix_quizzes_skill_id", table_name="quizzes")
    op.drop_column("quizzes", "difficulty")
    op.add_column("quizzes", sa.Column("week", sa.Integer(), nullable=False, server_default="0"))
    # Recreate skill_id as a plain indexed column (non-unique), then add composite unique
    op.create_index("ix_quizzes_skill_id", "quizzes", ["skill_id"])
    op.create_unique_constraint("uq_quizzes_skill_week", "quizzes", ["skill_id", "week"])

    # ── quiz_questions ────────────────────────────────────────────────────────
    op.add_column("quiz_questions", sa.Column("topic", sa.String(255), nullable=True))

    # ── topic_knowledge ───────────────────────────────────────────────────────
    op.create_table(
        "topic_knowledge",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "skill_id", sa.Integer(), sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("topic", sa.String(255), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("p_known", sa.Float(), nullable=False, server_default="0.1"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("p_transit", sa.Float(), nullable=False, server_default="0.1"),
        sa.Column("p_guess", sa.Float(), nullable=False, server_default="0.2"),
        sa.Column("p_slip", sa.Float(), nullable=False, server_default="0.1"),
        sa.Column("last_studied_at", sa.DateTime(), nullable=True),
        sa.Column("stability_days", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()
        ),
    )
    op.create_index("ix_topic_knowledge_skill_id", "topic_knowledge", ["skill_id"])
    op.create_index("ix_topic_knowledge_user_id", "topic_knowledge", ["user_id"])
    op.create_unique_constraint(
        "uq_topic_knowledge_skill_user_topic",
        "topic_knowledge",
        ["skill_id", "user_id", "topic"],
    )

    # ── content_style_arms ────────────────────────────────────────────────────
    op.create_table(
        "content_style_arms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "skill_id", sa.Integer(), sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("style", sa.String(50), nullable=False),
        sa.Column("alpha", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("beta", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()
        ),
    )
    op.create_index("ix_content_style_arms_skill_id", "content_style_arms", ["skill_id"])
    op.create_index("ix_content_style_arms_user_id", "content_style_arms", ["user_id"])
    op.create_unique_constraint(
        "uq_content_style_arms_skill_user_style",
        "content_style_arms",
        ["skill_id", "user_id", "style"],
    )

def downgrade() -> None:
    op.drop_table("content_style_arms")
    op.drop_table("topic_knowledge")

    op.drop_column("quiz_questions", "topic")

    op.drop_constraint("uq_quizzes_skill_week", "quizzes", type_="unique")
    op.drop_index("ix_quizzes_skill_id", table_name="quizzes")
    op.drop_column("quizzes", "week")
    op.add_column(
        "quizzes", sa.Column("difficulty", sa.String(), nullable=False, server_default="beginner")
    )
    op.create_index("ix_quizzes_skill_id", "quizzes", ["skill_id"], unique=True)

    op.drop_column("skills", "total_weeks")
    op.drop_column("skills", "generated_weeks")
    op.add_column(
        "skills",
        sa.Column("quiz_difficulty", sa.String(), nullable=False, server_default="beginner"),
    )
