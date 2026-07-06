from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    name: str = Field(max_length=100)
    hashed_password: str
    is_active: bool = Field(default=True)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )
    # FK to llm_providers.id — tracks which provider the user currently has active
    llm_provider_id: Optional[int] = Field(default=None, foreign_key="llm_providers.id")
    # FK to companies.id — the user's org, resolved from email at signup. Read-only in
    # the UI (want a real company → sign up with its email domain).
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id", index=True)
    display_currency: Optional[str] = Field(default="USD", max_length=8)
    currency_exchange_rate: Optional[float] = Field(default=1.0)
