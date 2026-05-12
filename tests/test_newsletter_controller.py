from unittest.mock import patch, MagicMock
import pytest
from fastapi import HTTPException
from controllers.newsletter import send_chapter_email, issue_all_newsletters
from schemas.skill import SendChapterEmailRequest
from models.user import User

def _make_user(user_id=1):
    return User(
        id=user_id,
        email="test@example.com",
        name="Test",
        is_active=True,
        hashed_password="$2b$hash",
        llm_provider_id=1,
    )

def _make_chapter(**kwargs):
    d = {
        "_user_id": "1",
        "skill_id": 1,
        "skill": "Python",
        "topic": "Variables",
        "day": 1,
        "newsletter": "<p>content</p>",
    }
    d.update(kwargs)
    return d

class TestSendChapterEmail:
    def test_raises_404_when_chapter_not_found(self):
        user = _make_user()
        with patch("controllers.newsletter.get_chapter_content", return_value=None):
            with pytest.raises(HTTPException) as exc:
                send_chapter_email(SendChapterEmailRequest(task_id=999), user)
            assert exc.value.status_code == 404

    def test_raises_403_when_not_owner(self):
        user = _make_user(user_id=1)
        chapter = _make_chapter(**{"_user_id": "999"})
        with patch("controllers.newsletter.get_chapter_content", return_value=chapter):
            with pytest.raises(HTTPException) as exc:
                send_chapter_email(SendChapterEmailRequest(task_id=1), user)
            assert exc.value.status_code == 403

    def test_raises_400_when_no_newsletter_content(self):
        user = _make_user()
        chapter = _make_chapter(newsletter=None)
        with patch("controllers.newsletter.get_chapter_content", return_value=chapter):
            with pytest.raises(HTTPException) as exc:
                send_chapter_email(SendChapterEmailRequest(task_id=1), user)
            assert exc.value.status_code == 400

    def test_raises_503_when_smtp_not_configured(self):
        user = _make_user()
        chapter = _make_chapter()
        with (
            patch("controllers.newsletter.get_chapter_content", return_value=chapter),
            patch("controllers.newsletter.is_smtp_outbound_configured", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc:
                send_chapter_email(SendChapterEmailRequest(task_id=1), user)
            assert exc.value.status_code == 503

    def test_raises_503_when_smtp_not_ready(self):
        user = _make_user()
        chapter = _make_chapter()
        with (
            patch("controllers.newsletter.get_chapter_content", return_value=chapter),
            patch("controllers.newsletter.is_smtp_outbound_configured", return_value=True),
            patch("controllers.newsletter.is_smtp_ready_to_send", return_value=False),
            patch("controllers.newsletter.smtp_not_ready_reason", return_value="missing port"),
        ):
            with pytest.raises(HTTPException) as exc:
                send_chapter_email(SendChapterEmailRequest(task_id=1), user)
            assert exc.value.status_code == 503

    def test_raises_404_when_no_email_for_skill(self):
        user = _make_user()
        chapter = _make_chapter()
        with (
            patch("controllers.newsletter.get_chapter_content", return_value=chapter),
            patch("controllers.newsletter.is_smtp_outbound_configured", return_value=True),
            patch("controllers.newsletter.is_smtp_ready_to_send", return_value=True),
            patch("controllers.newsletter.get_email_id_from_skill_id", return_value=None),
        ):
            with pytest.raises(HTTPException) as exc:
                send_chapter_email(SendChapterEmailRequest(task_id=1), user)
            assert exc.value.status_code == 404

    def test_raises_503_when_send_fails(self):
        user = _make_user()
        chapter = _make_chapter()
        with (
            patch("controllers.newsletter.get_chapter_content", return_value=chapter),
            patch("controllers.newsletter.is_smtp_outbound_configured", return_value=True),
            patch("controllers.newsletter.is_smtp_ready_to_send", return_value=True),
            patch(
                "controllers.newsletter.get_email_id_from_skill_id", return_value="u@example.com"
            ),
            patch("controllers.newsletter.send_newsletter", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc:
                send_chapter_email(SendChapterEmailRequest(task_id=1), user)
            assert exc.value.status_code == 503

    def test_success_returns_status_and_marks_complete(self):
        user = _make_user()
        chapter = _make_chapter()
        with (
            patch("controllers.newsletter.get_chapter_content", return_value=chapter),
            patch("controllers.newsletter.is_smtp_outbound_configured", return_value=True),
            patch("controllers.newsletter.is_smtp_ready_to_send", return_value=True),
            patch(
                "controllers.newsletter.get_email_id_from_skill_id", return_value="u@example.com"
            ),
            patch("controllers.newsletter.send_newsletter", return_value=True),
            patch("controllers.newsletter.mark_task_completed") as mock_mark,
        ):
            result = send_chapter_email(SendChapterEmailRequest(task_id=1), user)
        assert result["status"] == "success"
        mock_mark.assert_called_once_with(1)

class TestIssueAllNewsletters:
    def test_success_returns_status(self):
        with patch("controllers.newsletter.issue_todays_newsletters"):
            result = issue_all_newsletters()
        assert result["status"] == "success"

    def test_raises_500_on_exception(self):
        with patch(
            "controllers.newsletter.issue_todays_newsletters", side_effect=RuntimeError("smtp down")
        ):
            with pytest.raises(HTTPException) as exc:
                issue_all_newsletters()
            assert exc.value.status_code == 500
            assert "smtp down" in exc.value.detail
