from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import UniqueConstraint

class UserModelPrice(SQLModel, table=True):
    __tablename__ = "user_model_prices"
    __table_args__ = (UniqueConstraint("user_id", "provider", "model", name="uq_user_model_price"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    provider: str
    model: str
    input_per_1m_usd: float
    output_per_1m_usd: float
