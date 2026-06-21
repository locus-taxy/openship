import logging
from typing import List
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, select
from database import engine
from models.week_remediation_topic import WeekRemediationTopic

logger = logging.getLogger(__name__)

def store_remediation_topics(
    skill_id: int,
    week: int,
    weak_topics: List[str],
    forgotten_topics: List[str],
) -> None:
    """Persist the canonical weak/forgotten topic names used when planning a week.

    These become the source of truth for quiz question topic tagging for remediation
    days, so BKT scores always accumulate on the original topic, not on whatever
    LLM-generated day name the syllabus produced (e.g. "Reinforcing: Arrays").
    """
    try:
        # Deduplicate: a topic may appear in both lists when it failed the quiz AND is
        # forgotten. Inserting the same topic twice would violate the unique constraint.
        weak_set = set(weak_topics)
        unique_forgotten = [t for t in forgotten_topics if t not in weak_set]

        with Session(engine) as session:
            session.exec(
                sa_delete(WeekRemediationTopic).where(
                    WeekRemediationTopic.skill_id == skill_id,
                    WeekRemediationTopic.week == week,
                )
            )
            for topic in weak_topics:
                session.add(
                    WeekRemediationTopic(
                        skill_id=skill_id, week=week, topic=topic, topic_type="weak"
                    )
                )
            for topic in unique_forgotten:
                session.add(
                    WeekRemediationTopic(
                        skill_id=skill_id, week=week, topic=topic, topic_type="forgotten"
                    )
                )
            session.commit()
    except Exception as exc:
        logger.error("Error storing remediation topics [skill=%d week=%d]: %s", skill_id, week, exc)

def clear_remediation_topics(skill_id: int) -> None:
    """Delete all WeekRemediationTopic rows for a skill (used when re-generating the syllabus)."""
    try:
        with Session(engine) as session:
            session.exec(
                sa_delete(WeekRemediationTopic).where(WeekRemediationTopic.skill_id == skill_id)
            )
            session.commit()
    except Exception as exc:
        logger.error("Error clearing remediation topics [skill=%d]: %s", skill_id, exc)

def get_canonical_topics_for_week(skill_id: int, week: int) -> List[str]:
    """Return canonical topic names stored for a week's remediation (order: weak then forgotten)."""
    with Session(engine) as session:
        rows = session.exec(
            select(WeekRemediationTopic)
            .where(
                WeekRemediationTopic.skill_id == skill_id,
                WeekRemediationTopic.week == week,
            )
            .order_by(WeekRemediationTopic.id)
        ).all()
    weak = [r.topic for r in rows if r.topic_type == "weak"]
    forgotten = [r.topic for r in rows if r.topic_type == "forgotten"]
    seen: set = set()
    result: List[str] = []
    for t in weak + forgotten:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result
