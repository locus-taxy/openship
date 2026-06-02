import random
from typing import List, Optional
from sqlmodel import Session, select
from database import engine
from models.content_style_arms import ContentStyleArm, CONTENT_STYLES

def _beta_sample(alpha: float, beta: float) -> float:
    """Draw one sample from Beta(alpha, beta) using the gamma method."""
    x = random.gammavariate(alpha, 1.0)
    y = random.gammavariate(beta, 1.0)
    return x / (x + y) if (x + y) > 0 else 0.5

def _initialise_arms(session: Session, skill_id: int, user_id: int) -> List[ContentStyleArm]:
    """Insert the 4 arms at alpha=1, beta=1 if they don't exist yet."""
    arms = []
    for style in CONTENT_STYLES:
        existing = session.exec(
            select(ContentStyleArm).where(
                ContentStyleArm.skill_id == skill_id,
                ContentStyleArm.user_id == user_id,
                ContentStyleArm.style == style,
            )
        ).first()
        if existing is None:
            arm = ContentStyleArm(skill_id=skill_id, user_id=user_id, style=style)
            session.add(arm)
            arms.append(arm)
        else:
            arms.append(existing)
    session.flush()
    return arms

def sample_style(skill_id: int, user_id: int) -> str:
    """Thompson-sample all arms and return the winning style name."""
    with Session(engine) as session:
        arms = _initialise_arms(session, skill_id, user_id)
        session.commit()
        best_style = max(arms, key=lambda a: _beta_sample(a.alpha, a.beta)).style
    return best_style

def update_arm(skill_id: int, user_id: int, style: str, improved: bool) -> None:
    """Increment alpha (improved) or beta (not improved) for the given style."""
    with Session(engine) as session:
        arm = session.exec(
            select(ContentStyleArm).where(
                ContentStyleArm.skill_id == skill_id,
                ContentStyleArm.user_id == user_id,
                ContentStyleArm.style == style,
            )
        ).first()
        if arm is None:
            return
        if improved:
            arm.alpha += 1.0
        else:
            arm.beta += 1.0
        session.add(arm)
        session.commit()

def get_current_style(skill_id: int, user_id: int) -> Optional[str]:
    """Return the style with the highest alpha/(alpha+beta) ratio (exploitation only).
    Not used in production — available for analytics/display if needed in future."""
    with Session(engine) as session:
        arms = session.exec(
            select(ContentStyleArm).where(
                ContentStyleArm.skill_id == skill_id,
                ContentStyleArm.user_id == user_id,
            )
        ).all()
    if not arms:
        return "balanced"
    return max(arms, key=lambda a: a.alpha / (a.alpha + a.beta)).style
