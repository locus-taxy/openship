import json
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
            "content_blocks": t.content_blocks,
            "has_content": t.content_blocks is not None or t.newsletter is not None,
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

def add_content_to_db(newsletter: str, task_id: int) -> bool:
    try:
        with Session(engine) as session:
            task = session.get(DailyTask, task_id)
            if task is None:
                return False
            task.newsletter = _sanitize_html(newsletter)
            session.add(task)
            session.commit()
            return True
    except Exception as e:
        print(f"Error in add_content_to_db: {e}")
        return False

def _clean_mermaid(content: str) -> str:
    """
    Fix common LLM-generated mermaid syntax issues that cause parse failures.
    - Unescape HTML entities (&lt; → <)
    - Strip parentheses and slashes from sequence-diagram message labels
      because mermaid's parser rejects them in that position.
    """
    import re
    from html import unescape

    content = unescape(content)

    # For sequence diagram message lines (arrows like ->>, -->, -->>)
    # strip ( ) and / from the label part (everything after the last colon).
    def _clean_label(m: re.Match) -> str:
        prefix = m.group(1)  # "A->>B: "
        label = m.group(2)
        label = re.sub(r"[()\/]", "", label)
        label = re.sub(r"\s{2,}", " ", label).strip()
        return prefix + label

    content = re.sub(
        r"((?:->+|-->>?)\s*[^:\n]+:\s*)(.+)",
        _clean_label,
        content,
    )
    return content

def _sanitize_block(block_dict: dict) -> dict:
    if block_dict.get("type") == "diagram" and block_dict.get("content"):
        block_dict["content"] = _clean_mermaid(block_dict["content"])
    return block_dict

def add_blocks_to_db(blocks: list, task_id: int) -> bool:
    try:
        with Session(engine) as session:
            task = session.get(DailyTask, task_id)
            if task is None:
                return False
            task.content_blocks = json.dumps([_sanitize_block(b.model_dump()) for b in blocks])
            session.add(task)
            session.commit()
            return True
    except Exception as e:
        print(f"Error in add_blocks_to_db: {e}")
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
