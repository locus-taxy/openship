import smtplib
from unittest.mock import MagicMock, patch, call
import pytest
from services.newsletter import send_newsletter, issue_todays_newsletters

class TestSendNewsletterSmtpNotConfigured:
    def test_disabled_smtp_manual_returns_false(self):
        with patch("services.newsletter.is_smtp_outbound_configured", return_value=False):
            result = send_newsletter("a@b.com", "Title", "<p>body</p>")
        assert result is False

    def test_disabled_smtp_scheduled_returns_true(self):
        with patch("services.newsletter.is_smtp_outbound_configured", return_value=False):
            result = send_newsletter(
                "a@b.com", "Title", "<p>body</p>", treat_disabled_smtp_as_done=True
            )
        assert result is True

class TestSendNewsletterSmtpIncomplete:
    def test_smtp_not_ready_returns_false(self):
        with (
            patch("services.newsletter.is_smtp_outbound_configured", return_value=True),
            patch("services.newsletter.is_smtp_ready_to_send", return_value=False),
            patch("services.newsletter.smtp_not_ready_reason", return_value="missing port"),
        ):
            result = send_newsletter("a@b.com", "Title", "<p>body</p>")
        assert result is False

    def test_auth_mismatch_user_only_returns_false(self):
        with (
            patch("services.newsletter.is_smtp_outbound_configured", return_value=True),
            patch("services.newsletter.is_smtp_ready_to_send", return_value=True),
            patch("services.newsletter.SMTP_USER", "user@example.com"),
            patch("services.newsletter.SMTP_PASSWORD", ""),
        ):
            result = send_newsletter("a@b.com", "Title", "<p>body</p>")
        assert result is False

    def test_auth_mismatch_password_only_returns_false(self):
        with (
            patch("services.newsletter.is_smtp_outbound_configured", return_value=True),
            patch("services.newsletter.is_smtp_ready_to_send", return_value=True),
            patch("services.newsletter.SMTP_USER", ""),
            patch("services.newsletter.SMTP_PASSWORD", "secret"),
        ):
            result = send_newsletter("a@b.com", "Title", "<p>body</p>")
        assert result is False

class TestSendNewsletterSuccess:
    def _base_patches(self):
        return [
            patch("services.newsletter.is_smtp_outbound_configured", return_value=True),
            patch("services.newsletter.is_smtp_ready_to_send", return_value=True),
            patch("services.newsletter.SMTP_USER", ""),
            patch("services.newsletter.SMTP_PASSWORD", ""),
            patch("services.newsletter.SMTP_HOST", "smtp.example.com"),
            patch("services.newsletter.SMTP_PORT", 587),
        ]

    def test_plain_smtp_success(self):
        mock_server = MagicMock()
        with (
            patch("services.newsletter.is_smtp_outbound_configured", return_value=True),
            patch("services.newsletter.is_smtp_ready_to_send", return_value=True),
            patch("services.newsletter.SMTP_USER", ""),
            patch("services.newsletter.SMTP_PASSWORD", ""),
            patch("services.newsletter.SMTP_HOST", "smtp.example.com"),
            patch("services.newsletter.SMTP_PORT", 587),
            patch("services.newsletter.SMTP_USE_SSL", False),
            patch("services.newsletter.SMTP_USE_TLS", False),
            patch("smtplib.SMTP") as mock_smtp_cls,
        ):
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            result = send_newsletter("a@b.com", "Title", "<p>body</p>")
        assert result is True

    def test_ssl_smtp_success(self):
        mock_server = MagicMock()
        with (
            patch("services.newsletter.is_smtp_outbound_configured", return_value=True),
            patch("services.newsletter.is_smtp_ready_to_send", return_value=True),
            patch("services.newsletter.SMTP_USER", ""),
            patch("services.newsletter.SMTP_PASSWORD", ""),
            patch("services.newsletter.SMTP_HOST", "smtp.example.com"),
            patch("services.newsletter.SMTP_PORT", 465),
            patch("services.newsletter.SMTP_USE_SSL", True),
            patch("smtplib.SMTP_SSL") as mock_ssl_cls,
        ):
            mock_ssl_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_ssl_cls.return_value.__exit__ = MagicMock(return_value=False)
            result = send_newsletter("a@b.com", "Title", "<p>body</p>")
        assert result is True

    def test_tls_smtp_success(self):
        mock_server = MagicMock()
        with (
            patch("services.newsletter.is_smtp_outbound_configured", return_value=True),
            patch("services.newsletter.is_smtp_ready_to_send", return_value=True),
            patch("services.newsletter.SMTP_USER", ""),
            patch("services.newsletter.SMTP_PASSWORD", ""),
            patch("services.newsletter.SMTP_HOST", "smtp.example.com"),
            patch("services.newsletter.SMTP_PORT", 587),
            patch("services.newsletter.SMTP_USE_SSL", False),
            patch("services.newsletter.SMTP_USE_TLS", True),
            patch("smtplib.SMTP") as mock_smtp_cls,
        ):
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            result = send_newsletter("a@b.com", "Title", "<p>body</p>")
        assert result is True

    def test_smtp_with_auth(self):
        mock_server = MagicMock()
        with (
            patch("services.newsletter.is_smtp_outbound_configured", return_value=True),
            patch("services.newsletter.is_smtp_ready_to_send", return_value=True),
            patch("services.newsletter.SMTP_USER", "user@example.com"),
            patch("services.newsletter.SMTP_PASSWORD", "secret"),
            patch("services.newsletter.SMTP_HOST", "smtp.example.com"),
            patch("services.newsletter.SMTP_PORT", 587),
            patch("services.newsletter.SMTP_USE_SSL", False),
            patch("services.newsletter.SMTP_USE_TLS", False),
            patch("smtplib.SMTP") as mock_smtp_cls,
        ):
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            result = send_newsletter("a@b.com", "Title", "<p>body</p>")
        assert result is True
        mock_server.login.assert_called_once_with("user@example.com", "secret")

    def test_smtp_exception_returns_false(self):
        with (
            patch("services.newsletter.is_smtp_outbound_configured", return_value=True),
            patch("services.newsletter.is_smtp_ready_to_send", return_value=True),
            patch("services.newsletter.SMTP_USER", ""),
            patch("services.newsletter.SMTP_PASSWORD", ""),
            patch("services.newsletter.SMTP_HOST", "smtp.example.com"),
            patch("services.newsletter.SMTP_PORT", 587),
            patch("services.newsletter.SMTP_USE_SSL", False),
            patch("services.newsletter.SMTP_USE_TLS", False),
            patch("smtplib.SMTP", side_effect=smtplib.SMTPException("connection refused")),
        ):
            result = send_newsletter("a@b.com", "Title", "<p>body</p>")
        assert result is False

    def test_os_error_returns_false(self):
        with (
            patch("services.newsletter.is_smtp_outbound_configured", return_value=True),
            patch("services.newsletter.is_smtp_ready_to_send", return_value=True),
            patch("services.newsletter.SMTP_USER", ""),
            patch("services.newsletter.SMTP_PASSWORD", ""),
            patch("services.newsletter.SMTP_HOST", "smtp.example.com"),
            patch("services.newsletter.SMTP_PORT", 587),
            patch("services.newsletter.SMTP_USE_SSL", False),
            patch("services.newsletter.SMTP_USE_TLS", False),
            patch("smtplib.SMTP", side_effect=OSError("network unreachable")),
        ):
            result = send_newsletter("a@b.com", "Title", "<p>body</p>")
        assert result is False

class TestIssueTodaysNewsletters:
    def test_no_skill_ids_returns_true(self):
        with (
            patch("services.newsletter.get_list_of_skill_ids", return_value=[]),
            patch("services.newsletter.get_tasks_based_on_skill_id", return_value=[]),
        ):
            result = issue_todays_newsletters()
        assert result is True

    def test_skips_skill_with_no_tasks(self):
        with (
            patch("services.newsletter.get_list_of_skill_ids", return_value=[1]),
            patch("services.newsletter.get_tasks_based_on_skill_id", return_value=[]),
            patch("services.newsletter.time") as mock_time,
        ):
            result = issue_todays_newsletters()
        assert result is True

    def test_skips_task_with_no_newsletter(self):
        task = {
            "id": 1,
            "day": 1,
            "skill": "Python",
            "topic": "Vars",
            "skill_id": 1,
            "newsletter": None,
        }
        with (
            patch("services.newsletter.get_list_of_skill_ids", return_value=[1]),
            patch("services.newsletter.get_tasks_based_on_skill_id", side_effect=[[task], [task]]),
            patch("services.newsletter.time"),
        ):
            result = issue_todays_newsletters()
        assert result is True

    def test_skips_task_with_no_email(self):
        task = {
            "id": 1,
            "day": 1,
            "skill": "Python",
            "topic": "Vars",
            "skill_id": 1,
            "newsletter": "<p>content</p>",
        }
        with (
            patch("services.newsletter.get_list_of_skill_ids", return_value=[1]),
            patch("services.newsletter.get_tasks_based_on_skill_id", side_effect=[[task], [task]]),
            patch("services.newsletter.get_email_id_from_skill_id", return_value=None),
            patch("services.newsletter.time"),
        ):
            result = issue_todays_newsletters()
        assert result is True

    def test_marks_task_complete_when_send_succeeds(self):
        task = {
            "id": 5,
            "day": 1,
            "skill": "Python",
            "topic": "Vars",
            "skill_id": 1,
            "newsletter": "<p>content</p>",
        }
        with (
            patch("services.newsletter.get_list_of_skill_ids", return_value=[1]),
            patch("services.newsletter.get_tasks_based_on_skill_id", side_effect=[[task], [task]]),
            patch(
                "services.newsletter.get_email_id_from_skill_id", return_value="user@example.com"
            ),
            patch("services.newsletter.send_newsletter", return_value=True),
            patch("services.newsletter.mark_task_completed") as mock_complete,
            patch("services.newsletter.time"),
        ):
            result = issue_todays_newsletters()
        assert result is True
        mock_complete.assert_called_once_with(5)

    def test_does_not_mark_complete_when_send_fails(self):
        task = {
            "id": 5,
            "day": 1,
            "skill": "Python",
            "topic": "Vars",
            "skill_id": 1,
            "newsletter": "<p>content</p>",
        }
        with (
            patch("services.newsletter.get_list_of_skill_ids", return_value=[1]),
            patch("services.newsletter.get_tasks_based_on_skill_id", side_effect=[[task], [task]]),
            patch(
                "services.newsletter.get_email_id_from_skill_id", return_value="user@example.com"
            ),
            patch("services.newsletter.send_newsletter", return_value=False),
            patch("services.newsletter.mark_task_completed") as mock_complete,
            patch("services.newsletter.time"),
        ):
            result = issue_todays_newsletters()
        assert result is True
        mock_complete.assert_not_called()
