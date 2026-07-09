from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func

class Company(SQLModel, table=True):
    __tablename__ = "companies"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=255)
    # The isolation key mapping a user to their company. For a corporate email it's the
    # domain (e.g. "locus.sh") — teammates share one company. For a personal/generic
    # email it's the FULL email (e.g. "alice@gmail.com") — a private one-person org, so
    # unrelated personal users are never pooled together.
    domain: str = Field(unique=True, index=True, max_length=255)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )
