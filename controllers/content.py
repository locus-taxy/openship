import time
from fastapi import HTTPException
from models.user import User
from schemas.skill import GenerateContentRequest, GenerateChapterContentRequest
from services.skill import get_syllabus_detail
from services.daily_task import (
    get_chapter_content,
    get_tasks_for_generating_newsletter,
    add_content_to_db,
    mark_task_completed,
)
from services.gemini import generate_newsletter_html

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
            html = generate_newsletter_html(
                task_description=task["task"],
                task_title=task["topic"],
                skill=task["skill"],
            )
            if not html:
                print(f"Failed to generate content for task {task['id']}")
                failed_tasks.append(task["id"])
                continue
            if not add_content_to_db(newsletter=html, task_id=task["id"]):
                print(f"Failed to save content for task {task['id']}")
                failed_tasks.append(task["id"])
            time.sleep(5)
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

    html = generate_newsletter_html(
        task_description=chapter["task"],
        task_title=chapter["topic"],
        skill=chapter["skill"],
    )
    if not html:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate content for task {payload.task_id}"
        )

    if not add_content_to_db(newsletter=html, task_id=payload.task_id):
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

def complete_chapter(task_id: int, current_user: User):
    chapter = get_chapter_content(task_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail=f"Chapter {task_id} not found")
    _check_task_ownership(chapter, current_user)
    mark_task_completed(task_id)
    return {"status": "success"}
