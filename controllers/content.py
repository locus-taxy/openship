import time

from fastapi import HTTPException

from models.user import User
from schemas.skill import GenerateContentRequest, GenerateChapterContentRequest
from services.skill import get_syllabus_detail
from services.daily_task import (
    get_chapter_content,
    get_tasks_for_generating_newsletter,
    add_content_to_db,
    get_task_row,
)
from services.gemini import generate_newsletter_html


def generate_skill_content(user: User, payload: GenerateContentRequest):
    detail = get_syllabus_detail(payload.skill_id)
    if detail is None or detail["email"] != user.email:
        raise HTTPException(status_code=403, detail="Not your skill")

    tasks = get_tasks_for_generating_newsletter(payload.skill_id)
    for task in tasks:
        try:
            html = generate_newsletter_html(
                task_description=task['task'], task_title=task['topic'], skill=task['skill'],
            )
            add_content_to_db(newsletter=html, task_id=task['id'])
            time.sleep(5)
        except Exception as e:
            print(f"Content generation error for task {task['id']}: {e}")
            continue

    return {"status": "success", "message": f"Content generated for skill {payload.skill_id}"}


def generate_chapter(user: User, payload: GenerateChapterContentRequest):
    chapter = get_chapter_content(payload.task_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Task not found")

    detail = get_syllabus_detail(chapter["skill_id"])
    if detail is None or detail["email"] != user.email:
        raise HTTPException(status_code=403, detail="Not your task")

    row = get_task_row(payload.task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    html = generate_newsletter_html(
        task_description=row['task'], task_title=row['topic'], skill=row['skill'],
    )
    if not html:
        raise HTTPException(status_code=500, detail=f"Failed to generate content for task {payload.task_id}")

    add_content_to_db(newsletter=html, task_id=payload.task_id)
    return {"status": "success", "message": f"Content generated for task {payload.task_id}"}


def get_chapter(task_id: int, user: User):
    chapter = get_chapter_content(task_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail=f"Chapter {task_id} not found")

    detail = get_syllabus_detail(chapter["skill_id"])
    if detail is None or detail["email"] != user.email:
        raise HTTPException(status_code=403, detail="Not your chapter")
    return chapter
