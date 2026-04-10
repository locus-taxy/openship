from typing import Optional, List, Dict, Any
from sqlmodel import Session, select
from sqlalchemy import func, case
from database import engine
from models.skill import Skill
from models.daily_task import DailyTask

def skill_exists(email: str, skill: str) -> bool:
    with Session(engine) as session:
        statement = select(Skill).where(Skill.email == email, Skill.skill == skill)
        return session.exec(statement).first() is not None

def create_skill(user_id: str, email: str, skill: str, days: int, hours: int) -> Optional[int]:
    try:
        with Session(engine) as session:
            db_skill = Skill(user_id=user_id, email=email, skill=skill, days=days, hours=hours)
            session.add(db_skill)
            session.commit()
            session.refresh(db_skill)
            return db_skill.id
    except Exception as e:
        print(f"[DB ERROR] create_skill failed: {e}")
        return None

def get_skill(email: str, skill: str) -> Optional[Dict[str, Any]]:
    with Session(engine) as session:
        statement = select(Skill).where(Skill.email == email, Skill.skill == skill)
        result = session.exec(statement).first()
        if result is None:
            return None
        return {"user_id": result.user_id, "days": result.days, "hours": result.hours}

def get_syllabus_detail(skill_id: int) -> Optional[Dict[str, Any]]:
    with Session(engine) as session:
        skill_row = session.get(Skill, skill_id)
        if skill_row is None:
            return None

        statement = (
            select(DailyTask)
            .where(DailyTask.skill_id == skill_id)
            .order_by(DailyTask.month, DailyTask.week, DailyTask.day)
        )
        tasks = session.exec(statement).all()

        months: dict = {}
        for t in tasks:
            m = months.setdefault(t.month, {})
            w = m.setdefault(t.week, [])
            w.append(
                {
                    "id": t.id,
                    "day": t.day,
                    "topic": t.topic,
                    "task": t.task,
                    "hours": t.hours,
                    "completed": t.completed,
                    "has_content": t.newsletter is not None,
                }
            )

        return {
            "skill_id": skill_row.id,
            "user_id": skill_row.user_id,
            "email": skill_row.email,
            "skill": skill_row.skill,
            "days": skill_row.days,
            "hours": skill_row.hours,
            "share_enabled": skill_row.share_enabled,
            "created_at": str(skill_row.created_at) if skill_row.created_at else None,
            "months": [
                {
                    "month": m,
                    "weeks": [
                        {"week": w, "tasks": tasks_list} for w, tasks_list in sorted(weeks.items())
                    ],
                }
                for m, weeks in sorted(months.items())
            ],
        }

def get_all_syllabi(email: Optional[str] = None) -> List[Dict[str, Any]]:
    with Session(engine) as session:
        completed_expr = func.coalesce(func.sum(case((DailyTask.completed == True, 1), else_=0)), 0)
        statement = (
            select(
                Skill.id,
                Skill.user_id,
                Skill.email,
                Skill.skill,
                Skill.days,
                Skill.hours,
                Skill.created_at,
                func.count(DailyTask.id).label("total_tasks"),
                completed_expr.label("completed_tasks"),
            )
            .outerjoin(DailyTask, DailyTask.skill_id == Skill.id)
            .where(Skill.stop_sending == False)
        )
        if email is not None:
            statement = statement.where(Skill.email == email)
        statement = statement.group_by(Skill.id).order_by(Skill.created_at.desc())
        rows = session.exec(statement).all()
        return [
            {
                "skill_id": row[0],
                "user_id": row[1],
                "email": row[2],
                "skill": row[3],
                "days": row[4],
                "hours": row[5],
                "created_at": str(row[6]) if row[6] else None,
                "total_tasks": row[7] or 0,
                "completed_tasks": int(row[8] or 0),
            }
            for row in rows
        ]

def get_list_of_skill_ids() -> List[int]:
    with Session(engine) as session:
        statement = select(Skill.id).where(Skill.stop_sending == False)
        return list(session.exec(statement).all())

def get_email_id_from_skill_id(skill_id: int) -> Optional[str]:
    with Session(engine) as session:
        skill = session.get(Skill, skill_id)
        return skill.email if skill else None

def get_skill_id_by_email_and_skill(email: str, skill: str) -> Optional[int]:
    with Session(engine) as session:
        statement = select(Skill.id).where(Skill.email == email, Skill.skill == skill)
        return session.exec(statement).first()

def search_syllabi(email: str, query: str) -> List[Dict[str, Any]]:
    q = f"%{query}%"
    with Session(engine) as session:
        matching_skill_ids = set()

        skill_matches = session.exec(
            select(Skill.id).where(
                Skill.email == email, Skill.skill.ilike(q), Skill.stop_sending == False
            )
        ).all()
        matching_skill_ids.update(skill_matches)

        user_skill_ids = select(Skill.id).where(Skill.email == email, Skill.stop_sending == False)
        topic_match = DailyTask.topic.ilike(q)
        content_match = (DailyTask.newsletter != None) & (DailyTask.newsletter.ilike(q))
        task_rows = session.exec(
            select(DailyTask).where(
                DailyTask.skill_id.in_(user_skill_ids),
                topic_match | content_match,
            )
        ).all()

        task_skill_ids = {t.skill_id for t in task_rows}
        matching_skill_ids.update(task_skill_ids)

        if not matching_skill_ids:
            return []

        completed_expr = func.coalesce(func.sum(case((DailyTask.completed == True, 1), else_=0)), 0)
        statement = (
            select(
                Skill.id,
                Skill.user_id,
                Skill.email,
                Skill.skill,
                Skill.days,
                Skill.hours,
                Skill.created_at,
                func.count(DailyTask.id).label("total_tasks"),
                completed_expr.label("completed_tasks"),
            )
            .outerjoin(DailyTask, DailyTask.skill_id == Skill.id)
            .where(Skill.id.in_(matching_skill_ids))
            .group_by(Skill.id)
            .order_by(Skill.created_at.desc())
        )
        rows = session.exec(statement).all()

        matching_tasks_by_skill: Dict[int, List[Dict[str, Any]]] = {}
        for t in task_rows:
            matching_tasks_by_skill.setdefault(t.skill_id, []).append(
                {
                    "id": t.id,
                    "day": t.day,
                    "topic": t.topic,
                    "task": t.task,
                }
            )

        return [
            {
                "skill_id": row[0],
                "user_id": row[1],
                "email": row[2],
                "skill": row[3],
                "days": row[4],
                "hours": row[5],
                "created_at": str(row[6]) if row[6] else None,
                "total_tasks": row[7] or 0,
                "completed_tasks": int(row[8] or 0),
                "matching_chapters": matching_tasks_by_skill.get(row[0], []),
            }
            for row in rows
        ]

def get_public_syllabus_detail(skill_id: int) -> Optional[Dict[str, Any]]:
    """Return sanitized public syllabus data (no email/user_id) only when share_enabled."""
    with Session(engine) as session:
        skill_row = session.get(Skill, skill_id)
        if skill_row is None or not skill_row.share_enabled:
            return None

        statement = (
            select(DailyTask)
            .where(DailyTask.skill_id == skill_id)
            .order_by(DailyTask.month, DailyTask.week, DailyTask.day)
        )
        tasks = session.exec(statement).all()

        months: dict = {}
        for t in tasks:
            m = months.setdefault(t.month, {})
            w = m.setdefault(t.week, [])
            w.append(
                {
                    "id": t.id,
                    "day": t.day,
                    "topic": t.topic,
                    "task": t.task,
                    "hours": t.hours,
                    "newsletter": t.newsletter,
                }
            )

        return {
            "skill_id": skill_row.id,
            "skill": skill_row.skill,
            "days": skill_row.days,
            "hours": skill_row.hours,
            "created_at": str(skill_row.created_at) if skill_row.created_at else None,
            "months": [
                {
                    "month": m,
                    "weeks": [
                        {"week": w, "tasks": tasks_list} for w, tasks_list in sorted(weeks.items())
                    ],
                }
                for m, weeks in sorted(months.items())
            ],
        }

def toggle_skill_share(skill_id: int, enable: bool, user_id: str) -> Optional[bool]:
    """Set share_enabled on a skill. Returns new value, or None if not found / not owner."""
    with Session(engine) as session:
        skill_row = session.get(Skill, skill_id)
        if skill_row is None or skill_row.user_id != user_id:
            return None
        skill_row.share_enabled = enable
        session.add(skill_row)
        session.commit()
        session.refresh(skill_row)
        return skill_row.share_enabled
