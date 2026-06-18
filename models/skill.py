from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func

class Skill(SQLModel, table=True):
    __tablename__ = "skills"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str
    email: str = Field(index=True)
    skill: str
    days: int = Field(default=90)
    hours: int = Field(default=1)
    stop_sending: bool = Field(default=False)
    share_enabled: bool = Field(default=False)
    generated_weeks: int = Field(default=0)
    total_weeks: int = Field(default=0)
    is_technical: Optional[bool] = Field(default=None)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )
