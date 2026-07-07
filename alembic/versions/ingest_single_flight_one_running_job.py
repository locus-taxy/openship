"""one running ingestion job per company (single-flight)

Revision ID: ingest_single_flight
Revises: adaptive_topic_canon
Create Date: 2026-07-07 00:00:00.000000

begin_ingest / begin_reconcile check `_running_job()` and then `_create_job()` in
SEPARATE sessions, so two concurrent requests could both pass the check and each
create a 'running' job. Enforce the intended invariant — at most ONE running job
per company — with a PARTIAL unique index; the callers catch the resulting
IntegrityError and return the job that won the race.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ingest_single_flight"
down_revision: Union[str, Sequence[str], None] = "adaptive_topic_canon"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = "uq_ingestion_jobs_one_running_per_company"

def upgrade() -> None:
    # Any pre-existing 'running' rows are orphaned across this deploy (jobs run
    # in-process), so demote them first — mirrors the startup reaper and guarantees
    # the partial unique index can be built even if duplicates exist. Runs once.
    op.execute(
        "UPDATE ingestion_jobs SET status = 'failed', phase = 'failed' " "WHERE status = 'running'"
    )
    op.create_index(
        _INDEX,
        "ingestion_jobs",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )

def downgrade() -> None:
    op.drop_index(_INDEX, table_name="ingestion_jobs")
