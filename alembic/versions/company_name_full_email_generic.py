"""use full email as display name for generic-email companies

Revision ID: company_name_full_email
Revises: ingest_single_flight
Create Date: 2026-07-07 00:00:00.000000

Personal / generic-email companies (keyed by the FULL email) previously stored only
the local part as their display name ("yogeshkont48445"). Backfill those to the full
email so the label is unambiguous. Generic-email companies are exactly the rows whose
domain (the unique key) contains '@'; corporate companies keyed by a bare domain are
untouched.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "company_name_full_email"
down_revision: Union[str, Sequence[str], None] = "ingest_single_flight"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("UPDATE companies SET name = domain WHERE domain LIKE '%@%'")

def downgrade() -> None:
    # Restore the local part (text before '@') for generic-email companies.
    op.execute("UPDATE companies SET name = split_part(domain, '@', 1) WHERE domain LIKE '%@%'")
