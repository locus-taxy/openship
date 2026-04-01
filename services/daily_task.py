from typing import Optional, List, Dict, Any
from sqlmodel import Session, select

from database import engine
from models.daily_task import DailyTask


def get_chapter_content(task_id: int) -> Optional[Dict[str, Any]]:
    with Session(engine) as session:
        t = session.get(DailyTask, task_id)
        if t is None:
            return None
        return {
            "id": t.id, "skill": t.skill, "skill_id": t.skill_id,
            "topic": t.topic, "task": t.task, "day": t.day,
            "hours": t.hours, "completed": t.completed, "newsletter": t.newsletter,
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
                "id": t.id, "skill": t.skill, "topic": t.topic,
                "task": t.task, "hours": t.hours, "day": t.day,
                "newsletter": t.newsletter, "skill_id": t.skill_id,
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
                "id": t.id, "skill": t.skill, "topic": t.topic,
                "task": t.task, "hours": t.hours, "day": t.day,
            }
            for t in tasks
        ]


def add_content_to_db(newsletter: str, task_id: int) -> bool:
    try:
        with Session(engine) as session:
            task = session.get(DailyTask, task_id)
            if task is None:
                return False
            task.newsletter = newsletter
            session.add(task)
            session.commit()
            return True
    except Exception as e:
        print(f"Error in add_content_to_db: {e}")
        return False


def mark_task_completed(task_id: int) -> bool:
    try:
        with Session(engine) as session:
            task = session.get(DailyTask, task_id)
            if task is None:
                return False
            task.completed = True
            session.add(task)
            session.commit()
            return True
    except Exception as e:
        print(f"Error marking task completed: {e}")
        return False


def store_syllabus_tasks(user_id: str, skill: str, syllabus_data: list, hours: int, skill_id: int):
    with Session(engine) as session:
        for month_obj in syllabus_data:
            month = month_obj.get("month")
            for week_obj in month_obj.get("weeks", []):
                week = week_obj.get("week")
                for day_obj in week_obj.get("daily_plan", []):
                    task = DailyTask(
                        user_id=user_id, skill=skill, skill_id=skill_id,
                        month=month, week=week,
                        day=day_obj.get("day"), topic=day_obj.get("topic"),
                        task=day_obj.get("task"), hours=hours,
                    )
                    session.add(task)
        session.commit()


def get_task_row(task_id: int) -> Optional[Dict[str, Any]]:
    with Session(engine) as session:
        t = session.get(DailyTask, task_id)
        if t is None:
            return None
        return {"id": t.id, "skill": t.skill, "topic": t.topic, "task": t.task, "hours": t.hours}
