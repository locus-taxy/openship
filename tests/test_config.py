import os
from unittest.mock import patch
import pytest

class TestSmtpNotReadyReason:
    def test_returns_none_when_all_set(self):
        from config import smtp_not_ready_reason

        with (
            patch("config.SMTP_HOST", "smtp.example.com"),
            patch("config.SMTP_FROM_EMAIL", "noreply@example.com"),
            patch("config.SMTP_PORT", 587),
            patch("config.SMTP_USE_SSL", False),
            patch("config.SMTP_USE_TLS", True),
        ):
            assert smtp_not_ready_reason() is None

    def test_returns_reason_when_no_host(self):
        from config import smtp_not_ready_reason

        with patch("config.SMTP_HOST", None):
            reason = smtp_not_ready_reason()
        assert reason is not None
        assert "SMTP_HOST" in reason

    def test_returns_reason_when_no_from_email(self):
        from config import smtp_not_ready_reason

        with patch("config.SMTP_HOST", "smtp.example.com"), patch("config.SMTP_FROM_EMAIL", None):
            reason = smtp_not_ready_reason()
        assert reason is not None
        assert "SMTP_FROM_EMAIL" in reason

    def test_returns_reason_when_port_zero(self):
        from config import smtp_not_ready_reason

        with (
            patch("config.SMTP_HOST", "smtp.example.com"),
            patch("config.SMTP_FROM_EMAIL", "noreply@example.com"),
            patch("config.SMTP_PORT", 0),
        ):
            reason = smtp_not_ready_reason()
        assert reason is not None
        assert "SMTP_PORT" in reason

    def test_returns_reason_when_ssl_and_tls_both_true(self):
        from config import smtp_not_ready_reason

        with (
            patch("config.SMTP_HOST", "smtp.example.com"),
            patch("config.SMTP_FROM_EMAIL", "noreply@example.com"),
            patch("config.SMTP_PORT", 587),
            patch("config.SMTP_USE_SSL", True),
            patch("config.SMTP_USE_TLS", True),
        ):
            reason = smtp_not_ready_reason()
        assert reason is not None
        assert "SSL" in reason or "TLS" in reason

class TestIsSmtpReadyToSend:
    def test_returns_true_when_ready(self):
        from config import is_smtp_ready_to_send

        with patch("config.smtp_not_ready_reason", return_value=None):
            assert is_smtp_ready_to_send() is True

    def test_returns_false_when_not_ready(self):
        from config import is_smtp_ready_to_send

        with patch("config.smtp_not_ready_reason", return_value="missing host"):
            assert is_smtp_ready_to_send() is False
