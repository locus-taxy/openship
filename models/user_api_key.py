from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func
from sqlalchemy import UniqueConstraint

class UserApiKey(SQLModel, table=True):
    __tablename__ = "user_api_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "llm_provider_id", name="uq_user_api_keys_user_provider"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    llm_provider_id: int = Field(foreign_key="llm_providers.id", index=True)
    llm_model: Optional[str] = Field(default=None, max_length=100)
    api_key: str = Field(max_length=1024)  # partially encrypted — see services/encryption.py
    input_price_per_m_usd: Optional[float] = Field(default=None)
    output_price_per_m_usd: Optional[float] = Field(default=None)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )
