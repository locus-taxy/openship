import math
from datetime import datetime, timezone
from typing import List
from sqlmodel import Session, select
from database import engine
from models.topic_knowledge import TopicKnowledge
from services.daily_task import get_canonical_topic_names

RETENTION_THRESHOLD = 0.70

def retention(days_elapsed: float, stability_days: float) -> float:
    """R(t) = e^(-t / S). Returns value between 0.0 and 1.0."""
    if stability_days <= 0:
        return 0.0
    return math.exp(-days_elapsed / stability_days)

def get_forgotten_topics(skill_id: int, user_id: int) -> List[str]:
    """Return canonical topics where retention has dropped below RETENTION_THRESHOLD.

    Only considers topics that were introduced as new content (is_remediation_day=False).
    This prevents phantom alias rows like "Reinforcing: Arrays" — created before the
    canonical-topic fix — from polluting future weeks' remediation lists.
    """
    canonical = get_canonical_topic_names(skill_id)
    if not canonical:
        return []

    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        rows = session.exec(
            select(TopicKnowledge).where(
                TopicKnowledge.skill_id == skill_id,
                TopicKnowledge.user_id == user_id,
                TopicKnowledge.last_studied_at.isnot(None),
                TopicKnowledge.topic.in_(canonical),
            )
        ).all()
    canonical_set = set(canonical)
    forgotten_with_scores: list = []
    for row in rows:
        if row.topic not in canonical_set:
            continue  # belt-and-suspenders: skip any phantom alias rows
        last = row.last_studied_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        days_elapsed = (now - last).total_seconds() / 86400
        r = retention(days_elapsed, row.stability_days)
        if r < RETENTION_THRESHOLD:
            forgotten_with_scores.append((r, row.topic))
    # Sort ascending by retention so the most-forgotten topics come first.
    # Callers that cap the list will then drop the least-forgotten topics.
    forgotten_with_scores.sort()
    return [topic for _, topic in forgotten_with_scores]
