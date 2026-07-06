import json
import logging
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from database import engine
from onboarding.models.onboarding_plan import OnboardingPlan
from onboarding.models.onboarding_day import OnboardingDay
from onboarding.models.onboarding_quiz_attempt import OnboardingQuizAttempt
from onboarding.services import generation as llm_service
from onboarding.services import retrieval as retrieval_service
from onboarding.prompts import onboarding as onboarding_prompts

logger = logging.getLogger(__name__)

# Chunks to retrieve as grounding. Planning/quiz sweep broadly across the
# company's docs; a single day pulls a tighter, more focused set for its topic.
_PLAN_RETRIEVE_K = 30
_DAY_RETRIEVE_K = 20

# Broad seed used when planning the whole onboarding (no single topic yet).
_LANDSCAPE_SEED = "architecture setup codebase systems services workflows processes conventions"

def _load_docs(
    company_id: int,
    role: str = "",
    topic: str = "",
    task: str = "",
    k: Optional[int] = None,
) -> str:
    """Retrieve the most relevant knowledge-base chunks as grounding context.

    With a `topic` (generating one day / a quiz over known topics) the query is
    tight — role + topic + task — for precise grounding. Without one (planning
    the 7 days) it sweeps the company's doc landscape for breadth."""
    if topic:
        query = " ".join(p for p in [role, topic, task] if p)
        k = k or _DAY_RETRIEVE_K
    else:
        query = " ".join(p for p in [role, _LANDSCAPE_SEED] if p)
        k = k or _PLAN_RETRIEVE_K
    # Onboarding grounds only in Confluence docs (Jira issues are noise for a plan),
    # and stays purely semantic — a plan wants broad topical coverage, not literal
    # keyword hits, so the lexical boost (great for chat lookups) is off here.
    context = retrieval_service.retrieve_context(
        company_id, query, k=k, sources=["confluence"], hybrid=False
    )
    if not context.strip():
        raise HTTPException(
            status_code=404,
            detail="No onboarding documents are available yet. Connect Confluence and ingest docs first.",
        )
    return context

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

        docs_text = _load_docs(company_id, plan.role, topic=day.topic, task=day.task)

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

    # Ground the quiz in the exact topics the plan covered (broad sweep).
    docs_text = _load_docs(company_id, plan.role, topic=", ".join(topics), k=_PLAN_RETRIEVE_K)
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
