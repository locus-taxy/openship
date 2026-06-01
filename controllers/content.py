import logging
import time
from datetime import date
from fastapi import HTTPException

logger = logging.getLogger(__name__)
from pydantic import BaseModel
from models.user import User
from schemas.skill import GenerateContentRequest, GenerateChapterContentRequest
from services.skill import get_syllabus_detail
from services.daily_task import (
    get_chapter_content,
    get_tasks_for_generating_newsletter,
    add_content_to_db,
    add_blocks_to_db,
    mark_task_completed,
)
from services.llm import (
    generate_chapter_html,
    generate_chapter_content,
    get_user_api_key,
    get_user_model,
    get_user_provider_name,
)
from services.streak import record_activity, get_user_streak
from services.user import compute_generation_cost_usd, get_currency_settings
from services.pricing import lookup_model_price
from services.usage_log import log_llm_usage, get_chapter_cost, get_user_usage_cost
from services.user_pricing import get_user_model_price

class CompleteChapterBody(BaseModel):
    local_date: date

def _resolve_price(user: User, provider: str, model: str):
    """Return (input_per_1m, output_per_1m) using auto-pricing first, manual override second."""
    inp, out = lookup_model_price(provider, model)
    if inp is None or out is None:
        manual = get_user_model_price(user.id, provider, model)
        if manual:
            inp, out = manual
    return inp, out

def _check_skill_ownership(detail: dict, current_user: User):
    if detail.pop("_user_id") != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not own this skill")

def _check_task_ownership(chapter: dict, current_user: User):
    if chapter.pop("_user_id") != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not own this task")

def generate_skill_content(payload: GenerateContentRequest, current_user: User):
    detail = get_syllabus_detail(payload.skill_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    _check_skill_ownership(detail, current_user)

    tasks = get_tasks_for_generating_newsletter(payload.skill_id)
    failed_tasks = []
    for task in tasks:
        try:
            _html_result = generate_chapter_html(
                task_description=task["task"],
                task_title=task["topic"],
                skill=task["skill"],
                provider=get_user_provider_name(current_user),
                api_key=get_user_api_key(current_user),
                model=get_user_model(current_user),
            )
            if not _html_result or len(_html_result) != 3:
                print(f"Failed to generate content for task {task['id']}")
                failed_tasks.append(task["id"])
                continue
            html, input_tokens, output_tokens = _html_result
            if not html:
                print(f"Failed to generate content for task {task['id']}")
                failed_tasks.append(task["id"])
                continue
            provider_name = get_user_provider_name(current_user)
            model_name = get_user_model(current_user)
            cost_usd = None
            if input_tokens is not None:
                inp_price, out_price = _resolve_price(
                    current_user, provider_name or "", model_name or ""
                )
                cost_usd = compute_generation_cost_usd(
                    input_tokens, output_tokens, inp_price, out_price
                )
            log_llm_usage(
                user_id=current_user.id,
                call_type="chapter",
                provider=provider_name or "",
                model=model_name or "",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                ref_id=task["id"],
            )
            if not add_content_to_db(
                newsletter=html,
                task_id=task["id"],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                generation_cost_usd=cost_usd,
            ):
                logger.error("Failed to save content for task %s", task["id"])
                failed_tasks.append(task["id"])
            time.sleep(5)
        except HTTPException:
            raise  # quota / auth errors surface immediately — stop the bulk loop
        except Exception as e:
            logger.error("Content generation error for task %s: %s", task["id"], e)
            failed_tasks.append(task["id"])
            continue

    if failed_tasks:
        return {
            "status": "partial",
            "message": f"Content generated for skill {payload.skill_id} with {len(failed_tasks)} failure(s)",
            "failed_task_ids": failed_tasks,
        }
    return {"status": "success", "message": f"Content generated for skill {payload.skill_id}"}

def generate_chapter(payload: GenerateChapterContentRequest, current_user: User):
    chapter = get_chapter_content(payload.task_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _check_task_ownership(chapter, current_user)

    provider_name = get_user_provider_name(current_user)
    model_name = get_user_model(current_user)

    _content_result = generate_chapter_content(
        task_description=chapter["task"],
        task_title=chapter["topic"],
        skill=chapter["skill"],
        provider=provider_name,
        api_key=get_user_api_key(current_user),
        model=model_name,
    )
    if not _content_result or not isinstance(_content_result, tuple) or len(_content_result) != 3:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate content for task {payload.task_id}"
        )
    result, input_tokens, output_tokens = _content_result
    if not result:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate content for task {payload.task_id}"
        )

    cost_usd = None
    if input_tokens is not None:
        inp_price, out_price = _resolve_price(current_user, provider_name or "", model_name or "")
        cost_usd = compute_generation_cost_usd(input_tokens, output_tokens, inp_price, out_price)

    log_llm_usage(
        user_id=current_user.id,
        call_type="chapter",
        provider=provider_name or "",
        model=model_name or "",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        ref_id=payload.task_id,
    )

    if not add_blocks_to_db(blocks=result.blocks, task_id=payload.task_id):
        raise HTTPException(
            status_code=500, detail=f"Failed to save content for task {payload.task_id}"
        )

    return {"status": "success", "message": f"Content generated for task {payload.task_id}"}

def get_chapter(task_id: int, current_user: User):
    chapter = get_chapter_content(task_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail=f"Chapter {task_id} not found")
    _check_task_ownership(chapter, current_user)
    return chapter

def complete_chapter(task_id: int, current_user: User, local_date: date):
    chapter = get_chapter_content(task_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail=f"Chapter {task_id} not found")
    _check_task_ownership(chapter, current_user)
    if not mark_task_completed(task_id):
        print(f"Failed to mark task {task_id} as completed in DB")
        raise HTTPException(status_code=500, detail="Failed to mark chapter as completed")
    record_activity(str(current_user.id), local_date)
    return {"status": "success"}

def get_streak(current_user: User):
    return get_user_streak(str(current_user.id))

def get_cost_analytics(current_user: User):
    # Use llm_usage_logs (the authoritative source) rather than the denormalised
    # token columns on daily_tasks, which only reflect the first generation pass
    # and miss re-generations, quiz calls, etc.
    summary = get_user_usage_cost(current_user.id)
    currency, rate = get_currency_settings(current_user.id)
    return {
        **summary,
        "total_cost_display": round(summary["total_cost_usd"] * rate, 4),
        "display_currency": currency,
        "exchange_rate": rate,
    }

def get_chapter_cost_view(task_id: int, current_user: User):
    chapter = get_chapter_content(task_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail=f"Chapter {task_id} not found")
    _check_task_ownership(chapter, current_user)
    data = get_chapter_cost(task_id)
    currency, rate = get_currency_settings(current_user.id)
    return {
        **data,
        "total_cost_display": round(data["total_cost_usd"] * rate, 4),
        "display_currency": currency,
        "exchange_rate": rate,
    }

def get_user_usage_cost_view(current_user: User):
    data = get_user_usage_cost(current_user.id)
    currency, rate = get_currency_settings(current_user.id)
    return {
        **data,
        "total_cost_display": round(data["total_cost_usd"] * rate, 4),
        "display_currency": currency,
        "exchange_rate": rate,
    }
