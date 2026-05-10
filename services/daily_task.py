from typing import Optional, List, Dict, Any
from sqlmodel import Session, select
import bleach
from database import engine
from models.daily_task import DailyTask

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
            "hours": t.hours,
            "completed": t.completed,
            "newsletter": t.newsletter,
            "input_tokens": t.input_tokens,
            "output_tokens": t.output_tokens,
            "generation_cost_usd": t.generation_cost_usd,
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

def add_content_to_db(
    newsletter: str,
    task_id: int,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    generation_cost_usd: Optional[float] = None,
) -> bool:
    try:
        with Session(engine) as session:
            task = session.get(DailyTask, task_id)
            if task is None:
                return False
            task.newsletter = _sanitize_html(newsletter)
            if input_tokens is not None:
                task.input_tokens = input_tokens
            if output_tokens is not None:
                task.output_tokens = output_tokens
            if generation_cost_usd is not None:
                task.generation_cost_usd = generation_cost_usd
            session.add(task)
            session.commit()
            return True
    except Exception as e:
        print(f"Error in add_content_to_db: {e}")
        return False

def mark_task_completed(task_id: int) -> bool:
    try:
        from datetime import datetime, timezone

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
        print(f"Error marking task completed: {e}")
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

def store_syllabus_tasks(
    user_id: str, skill: str, syllabus_data: list, hours: int, skill_id: int
) -> bool:
    try:
        with Session(engine) as session:
            for month_obj in syllabus_data:
                month = month_obj.get("month")
                for week_obj in month_obj.get("weeks", []):
                    week = week_obj.get("week")
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
        print(f"Error storing syllabus tasks: {e}")
        return False
