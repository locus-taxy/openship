from fastapi import APIRouter, Request
from schemas.skill import SendChapterEmailRequest
from controllers import newsletter as newsletter_controller

router = APIRouter(tags=["newsletter"])

@router.post("/send-email/chapter")
def send_chapter_email(payload: SendChapterEmailRequest, request: Request):
    return newsletter_controller.send_chapter_email(payload, request.state.user)

@router.post("/issue-newsletters")
def issue_newsletters(request: Request):
    return newsletter_controller.issue_all_newsletters()
