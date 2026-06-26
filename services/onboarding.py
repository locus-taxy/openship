import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from database import engine
from models.onboarding_plan import OnboardingPlan
from models.onboarding_day import OnboardingDay
from models.onboarding_quiz_attempt import OnboardingQuizAttempt
from services import llm as llm_service
from prompts import onboarding as onboarding_prompts

logger = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).parent.parent / "test_data" / "locus_onboarding_docs"

# File number prefixes (NN_) that are relevant to each role keyword.
# Common docs (architecture, setup, prerequisites) are always included.
_COMMON_DOC_PREFIXES: frozenset[str] = frozenset({"03", "04", "05", "07"})

_ROLE_DOC_PREFIXES: dict[str, frozenset[str]] = {
    "backend": frozenset({"01", "08", "11", "16", "17", "18"}),
    "software": frozenset({"01", "08", "11", "16", "17", "18"}),
    "devops": frozenset({"09", "10", "12"}),
    "sre": frozenset({"09", "10", "12"}),
    "platform": frozenset({"09", "10", "12"}),
    "infrastructure": frozenset({"09", "10", "12"}),
    "sdet": frozenset({"06", "13", "14"}),
    "qa": frozenset({"06", "13", "14"}),
    "quality": frozenset({"06", "13", "14"}),
    "test": frozenset({"06", "13", "14"}),
    "automation": frozenset({"06", "13", "14"}),
    "product": frozenset({"15", "12"}),
    "solutions": frozenset({"15", "12"}),
    "manager": frozenset({"15", "12"}),
}

def _select_doc_prefixes(role: str) -> Optional[set[str]]:
    """Return file-number prefixes to include for this role, or None to load all docs."""
    role_lower = role.lower()
    extra: set[str] = set()
    matched = False
    for keyword, prefixes in _ROLE_DOC_PREFIXES.items():
        if keyword in role_lower:
            extra |= prefixes
            matched = True
    if not matched:
        return None  # unknown role → include everything
    return set(_COMMON_DOC_PREFIXES) | extra

def _load_docs(role: str = "") -> str:
    """Read role-relevant .md docs from the docs directory and concatenate them."""
    if not DOCS_DIR.exists():
        raise HTTPException(status_code=500, detail="Onboarding documents not found.")

    allowed = _select_doc_prefixes(role) if role else None

    parts = []
    for path in sorted(DOCS_DIR.glob("*.md"), key=lambda p: p.name):
        if allowed is not None:
            file_prefix = path.name.split("_")[0]
            if file_prefix not in allowed:
                continue
        parts.append(f"=== {path.stem} ===\n{path.read_text()}")

    if not parts:
        raise HTTPException(status_code=500, detail="No onboarding documents found.")
    return "\n\n".join(parts)

def generate_plan(
    user_id: str, role: str, company: str, provider: str, api_key: str, model: Optional[str]
) -> dict:
    docs_text = _load_docs(role)

    days_data = llm_service.generate_onboarding_plan(
        role=role,
        company=company,
        docs_text=docs_text,
        provider=provider,
        api_key=api_key,
        model=model,
    )
    if not days_data:
        raise HTTPException(status_code=500, detail="Failed to generate onboarding plan.")

    with Session(engine) as session:
        plan = OnboardingPlan(user_id=user_id, role=role, company=company, status="generated")
        session.add(plan)
        session.flush()

        days = []
        for d in days_data:
            day = OnboardingDay(
                plan_id=plan.id,
                day=d["day"],
                topic=d["topic"],
                task=d["task"],
            )
            session.add(day)
            days.append(day)

        session.commit()
        session.refresh(plan)
        for day in days:
            session.refresh(day)

        return {
            "plan": plan.model_dump(),
            "days": [d.model_dump() for d in days],
        }

def get_plan(plan_id: int, user_id: str) -> dict:
    with Session(engine) as session:
        plan = session.get(OnboardingPlan, plan_id)
        if not plan or plan.user_id != user_id:
            raise HTTPException(status_code=404, detail="Onboarding plan not found.")
        days = session.exec(
            select(OnboardingDay)
            .where(OnboardingDay.plan_id == plan_id)
            .order_by(OnboardingDay.day)
        ).all()
        return {"plan": plan.model_dump(), "days": [d.model_dump() for d in days]}

def get_day_content(
    plan_id: int,
    day_number: int,
    user_id: str,
    provider: str,
    api_key: str,
    model: Optional[str],
    force: bool = False,
) -> dict:
    with Session(engine) as session:
        plan = session.get(OnboardingPlan, plan_id)
        if not plan or plan.user_id != user_id:
            raise HTTPException(status_code=404, detail="Onboarding plan not found.")

        day = session.exec(
            select(OnboardingDay)
            .where(OnboardingDay.plan_id == plan_id)
            .where(OnboardingDay.day == day_number)
        ).first()
        if not day:
            raise HTTPException(status_code=404, detail=f"Day {day_number} not found.")

        # Return cached content if already generated (unless force regenerate)
        if day.content_blocks and not force:
            return {"day": day.model_dump()}

        docs_text = _load_docs(plan.role)

        content = llm_service.generate_onboarding_day_content(
            role=plan.role,
            company=plan.company,
            day=day.day,
            topic=day.topic,
            task=day.task,
            docs_text=docs_text,
            provider=provider,
            api_key=api_key,
            model=model,
        )
        if not content:
            raise HTTPException(status_code=500, detail="Failed to generate day content.")

        day.content_blocks = json.dumps([b.model_dump() for b in content.blocks])
        session.add(day)
        session.commit()
        session.refresh(day)
        return {"day": day.model_dump()}

def list_plans(user_id: str) -> list:
    with Session(engine) as session:
        plans = session.exec(
            select(OnboardingPlan)
            .where(OnboardingPlan.user_id == user_id)
            .order_by(OnboardingPlan.created_at.desc())
        ).all()
        result = []
        for plan in plans:
            days = session.exec(
                select(OnboardingDay)
                .where(OnboardingDay.plan_id == plan.id)
                .order_by(OnboardingDay.day)
            ).all()
            completed = sum(1 for d in days if d.completed)
            result.append(
                {**plan.model_dump(), "total_days": len(days), "completed_days": completed}
            )
        return result

def toggle_share(plan_id: int, user_id: str, enable: bool) -> dict:
    with Session(engine) as session:
        plan = session.get(OnboardingPlan, plan_id)
        if not plan or plan.user_id != user_id:
            raise HTTPException(status_code=404, detail="Onboarding plan not found.")
        plan.share_enabled = enable
        session.add(plan)
        session.commit()
        session.refresh(plan)
        return plan.model_dump()

def get_public_plan(plan_id: int) -> dict:
    with Session(engine) as session:
        plan = session.get(OnboardingPlan, plan_id)
        if not plan or not plan.share_enabled:
            raise HTTPException(status_code=404, detail="Onboarding plan not found or not public.")
        days = session.exec(
            select(OnboardingDay)
            .where(OnboardingDay.plan_id == plan_id)
            .order_by(OnboardingDay.day)
        ).all()
        return {"plan": plan.model_dump(), "days": [d.model_dump() for d in days]}

def complete_day(plan_id: int, day_number: int, user_id: str) -> dict:
    with Session(engine) as session:
        plan = session.get(OnboardingPlan, plan_id)
        if not plan or plan.user_id != user_id:
            raise HTTPException(status_code=404, detail="Onboarding plan not found.")
        day = session.exec(
            select(OnboardingDay)
            .where(OnboardingDay.plan_id == plan_id)
            .where(OnboardingDay.day == day_number)
        ).first()
        if not day:
            raise HTTPException(status_code=404, detail=f"Day {day_number} not found.")
        day.completed = True
        session.add(day)
        session.commit()
        session.refresh(day)
        return {"day": day.model_dump()}

def get_final_quiz(
    plan_id: int, user_id: str, provider: str, api_key: str, model: Optional[str]
) -> dict:
    with Session(engine) as session:
        plan = session.get(OnboardingPlan, plan_id)
        if not plan or plan.user_id != user_id:
            raise HTTPException(status_code=404, detail="Onboarding plan not found.")

        # Return cached questions if already generated
        if plan.quiz_questions:
            attempts = session.exec(
                select(OnboardingQuizAttempt)
                .where(OnboardingQuizAttempt.plan_id == plan_id)
                .where(OnboardingQuizAttempt.user_id == user_id)
                .order_by(OnboardingQuizAttempt.created_at.desc())
            ).all()
            return {
                "questions": json.loads(plan.quiz_questions),
                "attempts": [a.model_dump() for a in attempts],
            }

        days = session.exec(
            select(OnboardingDay)
            .where(OnboardingDay.plan_id == plan_id)
            .order_by(OnboardingDay.day)
        ).all()
        topics = [d.topic for d in days]

    docs_text = _load_docs(plan.role)

    questions = llm_service.generate_onboarding_quiz(
        role=plan.role,
        company=plan.company,
        topics=topics,
        docs_text=docs_text,
        num_questions=10,
        provider=provider,
        api_key=api_key,
        model=model,
    )
    if not questions:
        raise HTTPException(status_code=500, detail="Failed to generate final quiz.")

    with Session(engine) as session:
        plan = session.get(OnboardingPlan, plan_id)
        plan.quiz_questions = json.dumps(questions)
        session.add(plan)
        session.commit()

    return {"questions": questions, "attempts": []}

def get_quiz(plan_id: int, user_id: str) -> dict:
    """Return cached quiz + attempts. Raises 404 if quiz not generated yet."""
    with Session(engine) as session:
        plan = session.get(OnboardingPlan, plan_id)
        if not plan or plan.user_id != user_id:
            raise HTTPException(status_code=404, detail="Onboarding plan not found.")
        if not plan.quiz_questions:
            raise HTTPException(status_code=404, detail="Quiz not yet generated.")
        attempts = session.exec(
            select(OnboardingQuizAttempt)
            .where(OnboardingQuizAttempt.plan_id == plan_id)
            .where(OnboardingQuizAttempt.user_id == user_id)
            .order_by(OnboardingQuizAttempt.created_at.desc())
        ).all()
        return {
            "questions": json.loads(plan.quiz_questions),
            "attempts": [a.model_dump() for a in attempts],
        }

def generate_quiz(
    plan_id: int, user_id: str, provider: str, api_key: str, model: Optional[str]
) -> dict:
    """Generate quiz questions. Returns 409 if already generated."""
    with Session(engine) as session:
        plan = session.get(OnboardingPlan, plan_id)
        if not plan or plan.user_id != user_id:
            raise HTTPException(status_code=404, detail="Onboarding plan not found.")
        if plan.quiz_questions:
            raise HTTPException(status_code=409, detail="Quiz already generated.")
        days = session.exec(
            select(OnboardingDay)
            .where(OnboardingDay.plan_id == plan_id)
            .order_by(OnboardingDay.day)
        ).all()
        topics = [d.topic for d in days]

    docs_text = _load_docs(plan.role)
    questions = llm_service.generate_onboarding_quiz(
        role=plan.role,
        company=plan.company,
        topics=topics,
        docs_text=docs_text,
        num_questions=10,
        provider=provider,
        api_key=api_key,
        model=model,
    )
    if not questions:
        raise HTTPException(status_code=500, detail="Failed to generate final quiz.")

    with Session(engine) as session:
        plan = session.get(OnboardingPlan, plan_id)
        plan.quiz_questions = json.dumps(questions)
        session.add(plan)
        session.commit()

    return {"questions": questions, "attempts": []}

def save_quiz_attempt(plan_id: int, user_id: str, answers: dict) -> dict:
    with Session(engine) as session:
        plan = session.get(OnboardingPlan, plan_id)
        if not plan or plan.user_id != user_id:
            raise HTTPException(status_code=404, detail="Onboarding plan not found.")
        if not plan.quiz_questions:
            raise HTTPException(status_code=400, detail="Quiz not yet generated for this plan.")

        questions = json.loads(plan.quiz_questions)
        correct = 0
        for i, q in enumerate(questions):
            correct_key = q.get("correct_answer", "a")
            if answers.get(str(i)) == correct_key:
                correct += 1

        total = len(questions)
        score = round((correct / total) * 100) if total else 0

        attempt = OnboardingQuizAttempt(
            plan_id=plan_id,
            user_id=user_id,
            score=score,
            correct=correct,
            total=total,
            answers=json.dumps(answers),
        )
        session.add(attempt)
        session.commit()
        session.refresh(attempt)
        return {"attempt": attempt.model_dump(), "score": score, "correct": correct, "total": total}

def delete_plan(plan_id: int, user_id: str) -> dict:
    with Session(engine) as session:
        plan = session.get(OnboardingPlan, plan_id)
        if not plan or plan.user_id != user_id:
            raise HTTPException(status_code=404, detail="Onboarding plan not found.")
        session.delete(plan)
        session.commit()
        return {"deleted": True}
