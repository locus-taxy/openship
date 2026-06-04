import math
from datetime import datetime, timezone
from typing import List
from sqlmodel import Session, select
from database import engine
from models.topic_knowledge import TopicKnowledge

RETENTION_THRESHOLD = 0.70

def retention(days_elapsed: float, stability_days: float) -> float:
    """R(t) = e^(-t / S). Returns value between 0.0 and 1.0."""
    if stability_days <= 0:
        return 0.0
    return math.exp(-days_elapsed / stability_days)

def get_forgotten_topics(skill_id: int, user_id: int) -> List[str]:
    """Return topics where retention has dropped below RETENTION_THRESHOLD."""
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        rows = session.exec(
            select(TopicKnowledge).where(
                TopicKnowledge.skill_id == skill_id,
                TopicKnowledge.user_id == user_id,
                TopicKnowledge.last_studied_at.isnot(None),
            )
        ).all()
    forgotten = []
    for row in rows:
        last = row.last_studied_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        days_elapsed = (now - last).total_seconds() / 86400
        r = retention(days_elapsed, row.stability_days)
        if r < RETENTION_THRESHOLD:
            forgotten.append(row.topic)
    return forgotten
