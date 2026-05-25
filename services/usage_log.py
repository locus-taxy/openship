from typing import Any, Dict, Optional
from sqlmodel import Session, select, func, col
from database import engine
from models.llm_usage_log import LlmUsageLog

def log_llm_usage(
    user_id: str,
    call_type: str,
    provider: str,
    model: str,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    cost_usd: Optional[float],
    ref_id: Optional[int] = None,
) -> None:
    try:
        with Session(engine) as session:
            row = LlmUsageLog(
                user_id=user_id,
                call_type=call_type,
                ref_id=ref_id,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
            )
            session.add(row)
            session.commit()
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("Failed to write llm_usage_log: %s", e)

def get_chapter_cost(task_id: int) -> Dict[str, Any]:
    with Session(engine) as session:
        rows = session.exec(
            select(LlmUsageLog).where(
                LlmUsageLog.call_type == "chapter",
                LlmUsageLog.ref_id == task_id,
            )
        ).all()
        total = sum(r.cost_usd or 0.0 for r in rows)
        return {
            "total_cost_usd": round(total, 6),
            "generation_count": len(rows),
            "logs": [
                {
                    "provider": r.provider,
                    "model": r.model,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "cost_usd": r.cost_usd,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        }

def get_user_usage_cost(user_id: str) -> Dict[str, Any]:
    with Session(engine) as session:
        rows = session.exec(select(LlmUsageLog).where(LlmUsageLog.user_id == user_id)).all()

        total_cost = sum(r.cost_usd or 0.0 for r in rows)
        total_input = sum(r.input_tokens or 0 for r in rows)
        total_output = sum(r.output_tokens or 0 for r in rows)

        by_type: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            entry = by_type.setdefault(r.call_type, {"calls": 0, "cost_usd": 0.0})
            entry["calls"] += 1
            entry["cost_usd"] = round(entry["cost_usd"] + (r.cost_usd or 0.0), 6)

        return {
            "total_cost_usd": round(total_cost, 6),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_calls": len(rows),
            "by_type": by_type,
        }
