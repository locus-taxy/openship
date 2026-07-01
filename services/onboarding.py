import json
import logging
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from database import engine
from models.onboarding_plan import OnboardingPlan
from models.onboarding_day import OnboardingDay
from models.onboarding_quiz_attempt import OnboardingQuizAttempt
from models.onboarding_doc import OnboardingDoc
from services import llm as llm_service
from prompts import onboarding as onboarding_prompts

logger = logging.getLogger(__name__)

# Map free-text role strings (e.g. "Backend Engineer") to a doc role tag.
# Ordered most-specific first so "DevOps Engineer" resolves to devops, not backend.
_ROLE_TAG_KEYWORDS = [
    ("devops", "devops"),
    ("sre", "devops"),
    ("platform", "devops"),
    ("infrastructure", "devops"),
    ("infra", "devops"),
    ("sdet", "sdet"),
    ("automation", "sdet"),
    ("test", "sdet"),
    ("qa", "qa"),
    ("quality", "qa"),
    ("product", "product"),
    ("solutions", "product"),
    ("manager", "product"),
    ("backend", "backend"),
    ("software", "backend"),
]

def _role_tag(role: str) -> Optional[str]:
    """Map a free-text role to a doc role tag, or None if nothing matches."""
    role_lower = (role or "").lower()
    for keyword, tag in _ROLE_TAG_KEYWORDS:
        if keyword in role_lower:
            return tag
    return None

def _doc_has_tag(doc: OnboardingDoc, tag: str) -> bool:
    tags = json.loads(doc.role_tags) if doc.role_tags else []
    return tag in tags or "general" in tags

def _load_docs(company_id: int, role: str = "") -> str:
    """Concatenate the company's approved, active onboarding docs, preferring
    ones tagged for this role (falling back to all approved docs if none match)."""
    with Session(engine) as session:
        docs = session.exec(
            select(OnboardingDoc)
            .where(OnboardingDoc.company_id == company_id)
            .where(OnboardingDoc.approved == True)  # noqa: E712
            .where(OnboardingDoc.is_active == True)  # noqa: E712
            .order_by(OnboardingDoc.confidence.desc())
        ).all()
    if not docs:
        raise HTTPException(
            status_code=404,
            detail="No onboarding documents are available yet. Connect Confluence and ingest docs first.",
        )
    wanted = _role_tag(role)
    if wanted:
        filtered = [d for d in docs if _doc_has_tag(d, wanted)]
        if filtered:
            docs = filtered
    parts = [f"=== {d.title} ===\n{d.content_markdown or ''}" for d in docs]
    return "\n\n".join(parts)

def generate_plan(
    user_id: str,
    role: str,
    company: str,
    provider: str,
    api_key: str,
    model: Optional[str],
    company_id: int,
) -> dict:
    docs_text = _load_docs(company_id, role)

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
    company_id: int,
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

        docs_text = _load_docs(company_id, plan.role)

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
    plan_id: int, user_id: str, provider: str, api_key: str, model: Optional[str], company_id: int
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

    docs_text = _load_docs(company_id, plan.role)
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
