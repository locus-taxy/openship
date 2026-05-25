from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

class UserModelPrice(SQLModel, table=True):
    __tablename__ = "user_model_prices"
    __table_args__ = (UniqueConstraint("user_id", "provider", "model", name="uq_user_model_price"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    provider: str
    model: str
    input_per_1m_usd: float
    output_per_1m_usd: float
