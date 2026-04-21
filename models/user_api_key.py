from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func

class UserApiKey(SQLModel, table=True):
    __tablename__ = "user_api_keys"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    llm_provider_id: int = Field(foreign_key="llm_providers.id", index=True)
    llm_model: Optional[str] = Field(default=None, max_length=100)
    api_key: str = Field(max_length=1024)  # partially encrypted — see services/encryption.py
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )
