import logging
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from database import engine
from models.pricing_snapshot import PricingSnapshot

logger = logging.getLogger(__name__)

def create_pricing_snapshot(
    provider: str,
    model: str,
    input_per_1m_usd: float,
    output_per_1m_usd: float,
    source: str,
) -> Optional[int]:
    try:
        with Session(engine) as session:
            snapshot = PricingSnapshot(
                provider=provider,
                model=model,
                input_per_1m_usd=input_per_1m_usd,
                output_per_1m_usd=output_per_1m_usd,
                source=source,
            )
            session.add(snapshot)
            session.commit()
            session.refresh(snapshot)
            return snapshot.id
    except SQLAlchemyError as e:
        logger.warning("Failed to create pricing_snapshot: %s", e)
        return None
