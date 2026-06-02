from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel, func

class PricingSnapshot(SQLModel, table=True):
    __tablename__ = "pricing_snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str
    model: str
    input_per_1m_usd: float
    output_per_1m_usd: float
    source: str  # "auto" or "manual"
    created_at: datetime = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
