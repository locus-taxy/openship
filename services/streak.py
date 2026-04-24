from datetime import date, datetime, timezone, timedelta
from typing import Dict, Any
from sqlmodel import Session, select
from database import engine
from models.streak import UserStreak

def record_activity(user_id: str, activity_date: date) -> UserStreak:
    with Session(engine) as session:
        streak = session.exec(select(UserStreak).where(UserStreak.user_id == user_id)).first()
        if not streak:
            streak = UserStreak(user_id=user_id)
            session.add(streak)
            session.flush()

        if streak.last_activity_date == activity_date:
            return streak  # already counted today

        yesterday = activity_date - timedelta(days=1)
        if streak.last_activity_date is None:
            streak.current_streak = 1
        elif streak.last_activity_date == yesterday:
            streak.current_streak += 1
        else:
            streak.current_streak = 1  # gap — reset

        streak.last_activity_date = activity_date
        if streak.current_streak > streak.longest_streak:
            streak.longest_streak = streak.current_streak
        streak.updated_at = datetime.now(timezone.utc)

        session.add(streak)
        session.commit()
        session.refresh(streak)
        return streak

def get_user_streak(user_id: str) -> Dict[str, Any]:
    with Session(engine) as session:
        streak = session.exec(select(UserStreak).where(UserStreak.user_id == user_id)).first()
        if not streak:
            return {"current_streak": 0, "longest_streak": 0, "last_activity_date": None}
        return {
            "current_streak": streak.current_streak,
            "longest_streak": streak.longest_streak,
            "last_activity_date": streak.last_activity_date,
        }
