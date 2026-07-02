from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func
from sqlalchemy import UniqueConstraint

class ConfluenceConnection(SQLModel, table=True):
    """One Confluence connection per company. Tokens are encrypted at rest
    (see services/encryption.py:encrypt_secret)."""

    __tablename__ = "confluence_connections"
    __table_args__ = (UniqueConstraint("company_id", name="uq_confluence_connections_company"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    site_url: Optional[str] = Field(default=None, max_length=512)
    cloud_id: Optional[str] = Field(default=None, max_length=255)
    access_token: Optional[str] = Field(default=None)  # encrypted
    refresh_token: Optional[str] = Field(default=None)  # encrypted
    token_expires_at: Optional[datetime] = Field(default=None)
    webhook_id: Optional[str] = Field(default=None, max_length=255)
    # pending | syncing | ready | error
    status: str = Field(default="pending", max_length=32)
    # Audit only — records who connected; not an ownership grant.
    connected_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )
