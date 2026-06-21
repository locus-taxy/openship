from datetime import datetime, timezone
from typing import List, Tuple
from sqlmodel import Session, select
from database import engine
from models.topic_knowledge import TopicKnowledge
from services.daily_task import get_canonical_topic_names

MASTERY_THRESHOLD = 0.95

_STABILITY_MAP = (
    (MASTERY_THRESHOLD, 21.0),
    (0.70, 10.0),
    (0.40, 5.0),
    (0.0, 2.0),
)

def _stability_from_p_known(p_known: float) -> float:
    for threshold, days in _STABILITY_MAP:
        if p_known >= threshold:
            return days
    return 2.0

def _bkt_update(
    p_known: float, correct: bool, p_transit: float, p_guess: float, p_slip: float
) -> float:
    if correct:
        numerator = p_known * (1 - p_slip)
        denominator = numerator + (1 - p_known) * p_guess
    else:
        numerator = p_known * p_slip
        denominator = numerator + (1 - p_known) * (1 - p_guess)
    p_known_given_obs = numerator / denominator if denominator else p_known
    return p_known_given_obs + (1 - p_known_given_obs) * p_transit

def get_or_create_topic_knowledge(
    session: Session, skill_id: int, user_id: int, topic: str, week: int
) -> TopicKnowledge:
    row = session.exec(
        select(TopicKnowledge).where(
            TopicKnowledge.skill_id == skill_id,
            TopicKnowledge.user_id == user_id,
            TopicKnowledge.topic == topic,
        )
    ).first()
    if row is None:
        row = TopicKnowledge(
            skill_id=skill_id,
            user_id=user_id,
            topic=topic,
            week=week,
        )
        session.add(row)
        session.flush()
    return row

def update_topic_knowledge(
    skill_id: int,
    user_id: int,
    answers: List[Tuple[str, int, bool]],  # (topic, week, is_correct)
) -> None:
    """Update BKT state for each (topic, is_correct) pair in one transaction."""
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        for topic, week, is_correct in answers:
            row = get_or_create_topic_knowledge(session, skill_id, user_id, topic, week)
            row.p_known = _bkt_update(
                row.p_known, is_correct, row.p_transit, row.p_guess, row.p_slip
            )
            row.attempts += 1
            if is_correct:
                row.correct += 1
            row.last_studied_at = now
            row.stability_days = _stability_from_p_known(row.p_known)
            session.add(row)
        session.commit()

def get_weak_topics(skill_id: int, user_id: int) -> List[str]:
    """Return canonical topics where p_known < MASTERY_THRESHOLD, ordered weakest first.

    Filters to canonical topics only (from non-remediation DailyTask rows) so that
    pre-fix phantom alias rows like "Reinforcing: Arrays" are never surfaced.
    """
    canonical = get_canonical_topic_names(skill_id)
    if not canonical:
        return []
    canonical_set = set(canonical)
    with Session(engine) as session:
        rows = session.exec(
            select(TopicKnowledge).where(
                TopicKnowledge.skill_id == skill_id,
                TopicKnowledge.user_id == user_id,
                TopicKnowledge.p_known < MASTERY_THRESHOLD,
                TopicKnowledge.topic.in_(canonical),
            )
        ).all()
    return [r.topic for r in sorted(rows, key=lambda r: r.p_known) if r.topic in canonical_set]

def calc_remediation_days(prev_score: int, days_in_week: int) -> int:
    """Return how many days of next week to dedicate to remediation based on quiz score.

    Score 0–39%  → heavy remediation (60% of days, min 1)
    Score 40–69% → moderate remediation (30% of days, min 1)
    Score 70–99% → light touch (1 day)
    Score 100%   → no remediation
    Always leaves at least 1 day for new topics.
    """
    if prev_score >= 100:
        return 0
    if prev_score >= 70:
        remediation = 1
    elif prev_score >= 40:
        remediation = max(1, round(days_in_week * 0.30))
    else:
        remediation = max(1, round(days_in_week * 0.60))
    # Never consume all days — reserve at least one for new topics
    return min(remediation, days_in_week - 1)
