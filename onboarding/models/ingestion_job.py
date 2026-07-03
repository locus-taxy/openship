from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func

class IngestionJob(SQLModel, table=True):
    """Tracks one first-time ingestion run for a company (drives the progress bar)."""

    __tablename__ = "ingestion_jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    kind: str = Field(default="ingest", max_length=16)  # ingest | reconcile
    # Sub-stage within a running job, drives the UI's staged progress:
    # reading (fetching spaces/pages) | indexing (upserting pages) | embedding | done | failed
    phase: Optional[str] = Field(default=None, max_length=32)
    total_spaces: int = Field(default=0)
    processed_spaces: int = Field(default=0)
    total_pages: int = Field(default=0)
    processed_pages: int = Field(default=0)
    total_chunks: int = Field(default=0)
    embedded_chunks: int = Field(default=0)
    status: str = Field(default="running", max_length=32)  # running | done | failed
    error: Optional[str] = Field(default=None)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    completed_at: Optional[datetime] = Field(default=None)
