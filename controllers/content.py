import time
from datetime import date
from fastapi import HTTPException
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
    get_week_content_style,
    claim_week_style,
)
from services.llm import (
    generate_chapter_html,
    generate_chapter_content,
    get_user_api_key,
    get_user_model,
    get_user_provider_name,
)
from services.streak import record_activity, get_user_streak
from services.bandit import sample_style

class CompleteChapterBody(BaseModel):
    local_date: date

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
            html = generate_chapter_html(
                task_description=task["task"],
                task_title=task["topic"],
                skill=task["skill"],
                provider=get_user_provider_name(current_user),
                api_key=get_user_api_key(current_user),
                model=get_user_model(current_user),
            )
            if not html:
                print(f"Failed to generate content for task {task['id']}")
                failed_tasks.append(task["id"])
                continue
            if not add_content_to_db(newsletter=html, task_id=task["id"]):
                print(f"Failed to save content for task {task['id']}")
                failed_tasks.append(task["id"])
            time.sleep(5)
        except HTTPException:
            raise  # quota / auth errors surface immediately — stop the bulk loop
        except Exception as e:
            print(f"Content generation error for task {task['id']}: {e}")
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

    # Use the same style for every chapter in the same week so the bandit's
    # reward signal (weekly quiz score) can be attributed to a single style.
    # Sample a new style only for the first chapter of each week.
    week = chapter.get("week")
    style = (get_week_content_style(chapter["skill_id"], week) if week else None) or sample_style(
        chapter["skill_id"], current_user.id
    )

    # Commit the style immediately so concurrent chapter requests for the same
    # week see it and don't independently re-sample the bandit.
    if week:
        claim_week_style(payload.task_id, style)

    result = generate_chapter_content(
        task_description=chapter["task"],
        task_title=chapter["topic"],
        skill=chapter["skill"],
        provider=get_user_provider_name(current_user),
        api_key=get_user_api_key(current_user),
        model=get_user_model(current_user),
        style=style,
    )
    if not result:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate content for task {payload.task_id}"
        )

    if not add_blocks_to_db(blocks=result.blocks, task_id=payload.task_id, content_style=style):
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
