from datetime import date, datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import DateTime, Date

class UserStreak(SQLModel, table=True):
    __tablename__ = "user_streaks"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, unique=True)
    current_streak: int = Field(default=0)
    longest_streak: int = Field(default=0)
    last_activity_date: Optional[date] = Field(default=None, sa_column=Column(Date, nullable=True))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime, nullable=True))
