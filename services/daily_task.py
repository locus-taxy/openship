import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlmodel import Session, select
from sqlalchemy import delete as sa_delete, update as sa_update
import bleach
from database import engine
from models.daily_task import DailyTask

logger = logging.getLogger(__name__)

# Tags and attributes produced by Gemini newsletter HTML that we want to keep.
# Everything else (script, iframe, object, event handlers, javascript: URLs) is stripped.
_ALLOWED_TAGS = [
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "br",
    "hr",
    "ul",
    "ol",
    "li",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "s",
    "code",
    "pre",
    "blockquote",
    "a",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "div",
    "span",
]
_ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "th": ["scope"],
    "td": ["colspan", "rowspan"],
}
_ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

def _sanitize_html(raw: str) -> str:
    """Strip scripts, event handlers, and dangerous URLs from Gemini-generated HTML."""
    return bleach.clean(
        raw,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )

def get_chapter_content(task_id: int) -> Optional[Dict[str, Any]]:
    with Session(engine) as session:
        t = session.get(DailyTask, task_id)
        if t is None:
            return None
        return {
            "id": t.id,
            "_user_id": t.user_id,  # internal only — stripped before returning to UI
            "skill": t.skill,
            "skill_id": t.skill_id,
            "topic": t.topic,
            "task": t.task,
            "day": t.day,
            "week": t.week,
            "hours": t.hours,
            "completed": t.completed,
            "newsletter": t.newsletter,
            "input_tokens": t.input_tokens,
            "output_tokens": t.output_tokens,
            "generation_cost_usd": t.generation_cost_usd,
            "content_blocks": t.content_blocks,
            "content_style": t.content_style,
            "has_content": bool(t.content_blocks) or bool(t.newsletter),
        }

def get_tasks_based_on_skill_id(skill_id: int) -> List[Dict[str, Any]]:
    with Session(engine) as session:
        statement = (
            select(DailyTask)
            .where(DailyTask.skill_id == skill_id, DailyTask.completed == False)
            .order_by(DailyTask.day)
            .limit(1)
        )
        tasks = session.exec(statement).all()
        return [
            {
                "id": t.id,
                "skill": t.skill,
                "topic": t.topic,
                "task": t.task,
                "hours": t.hours,
                "day": t.day,
                "newsletter": t.newsletter,
                "skill_id": t.skill_id,
            }
            for t in tasks
        ]

def get_tasks_for_generating_newsletter(skill_id: int) -> List[Dict[str, Any]]:
    with Session(engine) as session:
        statement = (
            select(DailyTask)
            .where(
                DailyTask.skill_id == skill_id,
                DailyTask.completed == False,
                DailyTask.newsletter == None,
                DailyTask.content_blocks == None,
            )
            .order_by(DailyTask.day)
            .limit(90)
        )
        tasks = session.exec(statement).all()
        return [
            {
                "id": t.id,
                "skill": t.skill,
                "topic": t.topic,
                "task": t.task,
                "hours": t.hours,
                "day": t.day,
            }
            for t in tasks
        ]

def get_max_day_for_skill(skill_id: int) -> int:
    """Return the highest day number stored for a skill (0 if no tasks exist yet)."""
    with Session(engine) as session:
        from sqlalchemy import func

        result = session.exec(
            select(func.max(DailyTask.day)).where(DailyTask.skill_id == skill_id)
        ).first()
        return result or 0

def get_max_day_for_week(skill_id: int, week: int) -> int:
    """Return the highest day number stored for a specific week (0 if no tasks exist).

    Used by _generate_next_week to find the true start_day for the next week,
    which may differ from arithmetic when the initial LLM syllabus gave a week
    more or fewer days than days_in_week.
    """
    with Session(engine) as session:
        from sqlalchemy import func

        result = session.exec(
            select(func.max(DailyTask.day)).where(
                DailyTask.skill_id == skill_id,
                DailyTask.week == week,
            )
        ).first()
        return result or 0

def get_week_content_style(skill_id: int, week: int) -> Optional[str]:
    """Return the content_style already used for any chapter in this week, or None if none set yet."""
    with Session(engine) as session:
        task = session.exec(
            select(DailyTask).where(
                DailyTask.skill_id == skill_id,
                DailyTask.week == week,
                DailyTask.content_style.isnot(None),
            )
        ).first()
        return task.content_style if task else None

def add_content_to_db(
    newsletter: str,
    task_id: int,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    generation_cost_usd: Optional[float] = None,
    pricing_id: Optional[int] = None,
) -> bool:
    try:
        with Session(engine) as session:
            task = session.get(DailyTask, task_id)
            if task is None:
                return False
            if any(
                v is not None and v < 0 for v in (input_tokens, output_tokens, generation_cost_usd)
            ):
                return False
            task.newsletter = _sanitize_html(newsletter)
            if input_tokens is not None:
                task.input_tokens = input_tokens
            if output_tokens is not None:
                task.output_tokens = output_tokens
            if generation_cost_usd is not None:
                task.generation_cost_usd = generation_cost_usd
            if pricing_id is not None:
                task.pricing_id = pricing_id
            session.add(task)
            session.commit()
            return True
    except Exception as e:
        logger.error("Error in add_content_to_db: %s", e)
        return False

def _clean_mermaid(content: str) -> str:
    """
    Fix common LLM-generated mermaid syntax issues that cause parse failures.
    - Unescape HTML entities (&lt; → <)
    - In sequence diagram message labels (after the arrow+colon), replace
      special characters that break mermaid's parser with safe alternatives.
    """
    import re
    from html import unescape

    content = unescape(content)

    # Characters that break mermaid's sequence-diagram label parser.
    # Replace / with a space (so "success/failure" → "success failure"),
    # then strip remaining punctuation mermaid can't handle.
    _REPLACE_WITH_SPACE = re.compile(r"[/|]")
    _STRIP_CHARS = re.compile(r"[()[\]{}<>*?=,;!@#$%^&+~`\"'\\]")

    def _clean_label(m: re.Match) -> str:
        prefix = m.group(1)  # e.g. "A->>B: "
        label = m.group(2)
        label = _REPLACE_WITH_SPACE.sub(" ", label)
        label = _STRIP_CHARS.sub("", label)
        label = re.sub(r"\s{2,}", " ", label).strip()
        return prefix + label

    # Match any mermaid sequence diagram arrow line and clean its label.
    content = re.sub(
        r"((?:-->>?|->>?|->)\s*[^:\n]+:\s*)(.+)",
        _clean_label,
        content,
    )
    return content

def claim_week_style(task_id: int, style: str) -> None:
    """Lock content_style for the whole week atomically before the LLM call.
    A single UPDATE ensures only the first concurrent caller wins."""
    try:
        with Session(engine) as session:
            task = session.get(DailyTask, task_id)
            if task is None or task.week is None:
                return
            session.exec(
                sa_update(DailyTask)
                .where(
                    DailyTask.skill_id == task.skill_id,
                    DailyTask.week == task.week,
                    DailyTask.content_style == None,  # noqa: E711
                )
                .values(content_style=style)
            )
            session.commit()
    except Exception as e:
        logger.error("Error in claim_week_style: %s", e)

def _sanitize_block(block_dict: dict) -> dict:
    if block_dict.get("type") == "diagram" and block_dict.get("content"):
        block_dict["content"] = _clean_mermaid(block_dict["content"])
    return block_dict

def add_blocks_to_db(
    blocks: list,
    task_id: int,
    pricing_id: Optional[int] = None,
    content_style: Optional[str] = None,
) -> bool:
    try:
        with Session(engine) as session:
            task = session.get(DailyTask, task_id)
            if task is None:
                return False
            sanitized = [_sanitize_block(b.model_dump()) for b in blocks]
            if not sanitized:
                return True
            task.content_blocks = json.dumps(sanitized)
            if pricing_id is not None:
                task.pricing_id = pricing_id
            if content_style:
                task.content_style = content_style
            session.add(task)
            session.commit()
            return True
    except Exception as e:
        logger.error("Error in add_blocks_to_db: %s", e)
        return False

def mark_task_completed(task_id: int) -> bool:
    try:
        with Session(engine) as session:
            task = session.get(DailyTask, task_id)
            if task is None:
                return False
            if not task.completed:  # idempotent — stamp only once
                task.completed = True
                task.completed_at = datetime.now(timezone.utc)
                session.add(task)
                session.commit()
            return True
    except Exception as e:
        logger.error("Error marking task completed: %s", e)
        return False

def get_total_cost_for_user(user_id: str) -> Dict[str, Any]:
    """Aggregate token counts and USD cost across all tasks for a user."""
    with Session(engine) as session:
        tasks = session.exec(select(DailyTask).where(DailyTask.user_id == user_id)).all()
        return {
            "total_input_tokens": sum(t.input_tokens or 0 for t in tasks),
            "total_output_tokens": sum(t.output_tokens or 0 for t in tasks),
            "total_cost_usd": sum(t.generation_cost_usd or 0.0 for t in tasks),
        }

def get_cost_summary_for_skill(skill_id: int) -> Dict[str, Any]:
    """Aggregate token counts and USD cost for all tasks in a skill."""
    with Session(engine) as session:
        tasks = session.exec(select(DailyTask).where(DailyTask.skill_id == skill_id)).all()
        return {
            "total_input_tokens": sum(t.input_tokens or 0 for t in tasks),
            "total_output_tokens": sum(t.output_tokens or 0 for t in tasks),
            "total_cost_usd": sum(t.generation_cost_usd or 0.0 for t in tasks),
        }

def clear_syllabus_tasks(skill_id: int) -> None:
    """Delete all DailyTask rows for a skill before re-generating."""
    with Session(engine) as session:
        session.exec(sa_delete(DailyTask).where(DailyTask.skill_id == skill_id))
        session.commit()

def store_syllabus_tasks(
    user_id: str,
    skill: str,
    syllabus_data: list,
    hours: int,
    skill_id: int,
    only_week: Optional[int] = None,
) -> bool:
    """Store DailyTask rows from a syllabus JSON. Pass only_week to store a single week only.

    Week numbers are stored as globally sequential integers (1, 2, 3, …) across all months,
    regardless of the per-month week numbers the LLM returns.
    """
    try:
        with Session(engine) as session:
            global_week = 0
            for month_obj in syllabus_data:
                month = month_obj.get("month")
                for week_obj in month_obj.get("weeks", []):
                    global_week += 1
                    week = global_week
                    if only_week is not None and week != only_week:
                        continue
                    for day_obj in week_obj.get("daily_plan", []):
                        task = DailyTask(
                            user_id=user_id,
                            skill=skill,
                            skill_id=skill_id,
                            month=month,
                            week=week,
                            day=day_obj.get("day"),
                            topic=day_obj.get("topic"),
                            task=day_obj.get("task"),
                            hours=hours,
                        )
                        session.add(task)
            session.commit()
            return True
    except Exception as e:
        logger.error("Error storing syllabus tasks: %s", e)
        return False

def delete_week_tasks(skill_id: int, week: int) -> None:
    """Delete all DailyTask rows for a specific week (used before ML regeneration)."""
    with Session(engine) as session:
        session.exec(
            sa_delete(DailyTask).where(DailyTask.skill_id == skill_id, DailyTask.week == week)
        )
        session.commit()

def get_canonical_topic_names(skill_id: int) -> List[str]:
    """Return deduplicated topic names from non-remediation days (original canonical topics).

    Order-preserving deduplication — the same topic may appear on multiple weeks
    (review without remediation flag) so we return each name only once.
    """
    with Session(engine) as session:
        tasks = session.exec(
            select(DailyTask)
            .where(
                DailyTask.skill_id == skill_id,
                DailyTask.is_remediation_day == False,  # noqa: E712
            )
            .order_by(DailyTask.week, DailyTask.day)
        ).all()
        return list(dict.fromkeys(t.topic for t in tasks if t.topic))

def store_week_tasks(
    user_id: str,
    skill: str,
    skill_id: int,
    week: int,
    month: int,
    daily_plan: list,
    hours: int,
    remediation_days: int = 0,
) -> bool:
    """Store ML-generated DailyTask rows for a specific week.

    remediation_days: number of leading days in the plan that are remediation/review days.
    The first remediation_days day objects are flagged with is_remediation_day=True so
    their LLM-generated names are excluded from canonical topic tracking.
    """
    try:
        with Session(engine) as session:
            # Sort by day number first — the LLM may return days out of order.
            # is_remediation_day is flagged by list position (not absolute day number)
            # because day numbers are global across the whole syllabus (week 2 may
            # start at day 6+). After sorting, the first remediation_days entries are
            # remediation days as instructed in the syllabus prompt.
            ordered_plan = sorted(daily_plan, key=lambda d: d.get("day") or 0)
            for i, day_obj in enumerate(ordered_plan):
                is_remediation = remediation_days > 0 and i < remediation_days
                task = DailyTask(
                    user_id=user_id,
                    skill=skill,
                    skill_id=skill_id,
                    month=month,
                    week=week,
                    day=day_obj.get("day"),
                    topic=day_obj.get("topic"),
                    task=day_obj.get("task"),
                    hours=hours,
                    is_remediation_day=is_remediation,
                )
                session.add(task)
            session.commit()
            return True
    except Exception as e:
        logger.error("Error storing week tasks: %s", e)
        return False
