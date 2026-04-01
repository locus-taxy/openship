from fastapi import HTTPException

from models.user import User
from schemas.skill import SendChapterEmailRequest
from services.skill import get_syllabus_detail
from services.daily_task import get_chapter_content, mark_task_completed
from services.newsletter import send_newsletter, issue_todays_newsletters
from services.refresh_token import get_new_jwt_token


def send_chapter_email(user: User, payload: SendChapterEmailRequest):
    chapter = get_chapter_content(payload.task_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail=f"Chapter {payload.task_id} not found")
    if not chapter["newsletter"]:
        raise HTTPException(status_code=400, detail="No content generated for this chapter yet")

    detail = get_syllabus_detail(chapter["skill_id"])
    if detail is None or detail["email"] != user.email:
        raise HTTPException(status_code=403, detail="Not your chapter")

    token = get_new_jwt_token()
    title = f"Day {chapter['day']} - {chapter['skill']}: {chapter['topic']}"
    send_newsletter(email_to=user.email, title=title, content=chapter["newsletter"], token=token)
    mark_task_completed(payload.task_id)

    return {"status": "success", "message": f"Email sent for Day {chapter['day']}"}


def issue_all_newsletters():
    try:
        issue_todays_newsletters()
        return {"status": "success", "message": "Today's newsletters issued successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
