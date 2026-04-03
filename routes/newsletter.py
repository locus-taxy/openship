from fastapi import APIRouter, Depends
from models.user import User
from schemas.skill import SendChapterEmailRequest
from dependencies.auth import get_current_user
from controllers import newsletter as newsletter_controller

router = APIRouter(tags=["newsletter"])

@router.post("/send-email/chapter")
def send_chapter_email(
    payload: SendChapterEmailRequest, current_user: User = Depends(get_current_user)
):
    return newsletter_controller.send_chapter_email(payload, current_user)

@router.post("/issue-newsletters")
def issue_newsletters(current_user: User = Depends(get_current_user)):
    return newsletter_controller.issue_all_newsletters()
