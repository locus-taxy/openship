import math
from typing import Optional, Tuple

from sqlmodel import Session, select

from database import engine
from models.user_model_price import UserModelPrice

def get_user_model_price(user_id: int, provider: str, model: str) -> Optional[Tuple[float, float]]:
    with Session(engine) as session:
        row = session.exec(
            select(UserModelPrice).where(
                UserModelPrice.user_id == user_id,
                UserModelPrice.provider == provider,
                UserModelPrice.model == model,
            )
        ).first()
        if row:
            return row.input_per_1m_usd, row.output_per_1m_usd
    return None

def save_user_model_price(
    user_id: int,
    provider: str,
    model: str,
    input_per_1m_usd: float,
    output_per_1m_usd: float,
) -> None:
    if not (math.isfinite(input_per_1m_usd) and math.isfinite(output_per_1m_usd)):
        raise ValueError("Model prices must be finite numbers")
    if input_per_1m_usd < 0 or output_per_1m_usd < 0:
        raise ValueError("Model prices must be non-negative")
    with Session(engine) as session:
        row = session.exec(
            select(UserModelPrice).where(
                UserModelPrice.user_id == user_id,
                UserModelPrice.provider == provider,
                UserModelPrice.model == model,
            )
        ).first()
        if row:
            row.input_per_1m_usd = input_per_1m_usd
            row.output_per_1m_usd = output_per_1m_usd
        else:
            row = UserModelPrice(
                user_id=user_id,
                provider=provider,
                model=model,
                input_per_1m_usd=input_per_1m_usd,
                output_per_1m_usd=output_per_1m_usd,
            )
        session.add(row)
        session.commit()
