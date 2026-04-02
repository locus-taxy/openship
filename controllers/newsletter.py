from fastapi import HTTPException

from schemas.skill import SendChapterEmailRequest
from services.skill import get_syllabus_detail, get_email_id_from_skill_id
from services.daily_task import get_chapter_content, mark_task_completed
from services.newsletter import send_newsletter, issue_todays_newsletters
from services.refresh_token import get_new_jwt_token

def send_chapter_email(payload: SendChapterEmailRequest):
    chapter = get_chapter_content(payload.task_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail=f"Chapter {payload.task_id} not found")
    if not chapter["newsletter"]:
        raise HTTPException(status_code=400, detail="No content generated for this chapter yet")

    email = get_email_id_from_skill_id(chapter["skill_id"])
    if not email:
        raise HTTPException(status_code=404, detail="Could not find email for this skill")

    token = get_new_jwt_token()
    if not token:
        raise HTTPException(
            status_code=503, detail="Failed to obtain Linkifyi token — try again later"
        )

    title = f"Day {chapter['day']} - {chapter['skill']}: {chapter['topic']}"
    try:
        send_newsletter(email_to=email, title=title, content=chapter["newsletter"], token=token)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to send email: {e}") from e

    mark_task_completed(payload.task_id)
    return {"status": "success", "message": f"Email sent for Day {chapter['day']}"}

def issue_all_newsletters():
    try:
        issue_todays_newsletters()
        return {"status": "success", "message": "Today's newsletters issued successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
