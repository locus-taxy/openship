from fastapi import HTTPException
from config import is_smtp_outbound_configured
from models.user import User
from schemas.skill import SendChapterEmailRequest
from services.skill import get_syllabus_detail, get_email_id_from_skill_id
from services.daily_task import get_chapter_content, mark_task_completed
from services.newsletter import send_newsletter, issue_todays_newsletters

def send_chapter_email(payload: SendChapterEmailRequest, current_user: User):
    chapter = get_chapter_content(payload.task_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail=f"Chapter {payload.task_id} not found")
    if chapter["user_id"] != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not own this task")
    if not chapter["newsletter"]:
        raise HTTPException(status_code=400, detail="No content generated for this chapter yet")

    if not is_smtp_outbound_configured():
        raise HTTPException(
            status_code=503,
            detail="Email delivery is not configured (set SMTP_HOST and related SMTP settings).",
        )

    email = get_email_id_from_skill_id(chapter["skill_id"])
    if not email:
        raise HTTPException(status_code=404, detail="Could not find email for this skill")

    title = f"Day {chapter['day']} - {chapter['skill']}: {chapter['topic']}"
    if not send_newsletter(email_to=email, title=title, content=chapter["newsletter"]):
        raise HTTPException(
            status_code=503,
            detail=(
                "Email was not sent (SMTP transport is not implemented in this branch, "
                "or delivery failed)."
            ),
        )

    mark_task_completed(payload.task_id)
    return {"status": "success", "message": f"Email sent for Day {chapter['day']}"}

def issue_all_newsletters():
    try:
        issue_todays_newsletters()
        return {"status": "success", "message": "Today's newsletters issued successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
