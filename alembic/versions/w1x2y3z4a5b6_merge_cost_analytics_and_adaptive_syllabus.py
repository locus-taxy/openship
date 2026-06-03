"""merge cost analytics and adaptive syllabus branches

Revision ID: w1x2y3z4a5b6
Revises: v0w1x2y3z4a5, d4e5f6a7b8c9
Create Date: 2026-06-03

Merge point for:
  - cost-analytics branch (ends at v0w1x2y3z4a5: pricing_snapshots + pricing_id)
  - adaptive-syllabus branch (ends at d4e5f6a7b8c9: content_style on daily_tasks)
"""

from alembic import op

revision = "w1x2y3z4a5b6"
down_revision = ("v0w1x2y3z4a5", "d4e5f6a7b8c9")
branch_labels = None
depends_on = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
