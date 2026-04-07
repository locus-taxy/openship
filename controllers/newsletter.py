from fastapi import HTTPException

from schemas.skill import SendChapterEmailRequest
from services.skill import get_syllabus_detail, get_email_id_from_skill_id
from services.daily_task import get_chapter_content, mark_task_completed
from services.newsletter import send_newsletter, issue_todays_newsletters

def send_chapter_email(payload: SendChapterEmailRequest):
    chapter = get_chapter_content(payload.task_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail=f"Chapter {payload.task_id} not found")
    if not chapter["newsletter"]:
        raise HTTPException(status_code=400, detail="No content generated for this chapter yet")

    email = get_email_id_from_skill_id(chapter["skill_id"])
    if not email:
        raise HTTPException(status_code=404, detail="Could not find email for this skill")

    title = f"Day {chapter['day']} - {chapter['skill']}: {chapter['topic']}"
    if not send_newsletter(email_to=email, title=title, content=chapter["newsletter"]):
        raise HTTPException(
            status_code=503,
            detail="Email delivery is not configured yet. SMTP will be wired in a future change.",
        )

    mark_task_completed(payload.task_id)
    return {"status": "success", "message": f"Email sent for Day {chapter['day']}"}

def issue_all_newsletters():
    try:
        issue_todays_newsletters()
        return {"status": "success", "message": "Today's newsletters issued successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
