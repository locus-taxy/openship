import time
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional

from config import (
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_TIMEOUT_SECONDS,
    SMTP_USE_SSL,
    SMTP_USE_TLS,
    SMTP_USER,
    is_smtp_outbound_configured,
    is_smtp_ready_to_send,
    smtp_not_ready_reason,
)
from services.skill import get_list_of_skill_ids, get_email_id_from_skill_id
from services.daily_task import get_tasks_based_on_skill_id, mark_task_completed

def send_newsletter(
    email_to: str,
    title: str,
    content: str,
    token: Optional[str] = None,
    *,
    treat_disabled_smtp_as_done: bool = False,
) -> bool:
    """Send one newsletter email.

    When ``SMTP_HOST`` is unset, outbound email is disabled. Manual/API calls get
    ``False`` (callers may return 503). Scheduled jobs may pass
    ``treat_disabled_smtp_as_done=True`` so tasks are marked complete without sending.
    """
    if not is_smtp_outbound_configured():
        suffix = (
            " Scheduled job advancing task without send."
            if treat_disabled_smtp_as_done
            else " Manual send rejected until SMTP is configured."
        )
        print(f"Newsletter skipped (SMTP_HOST not set); subject={title!r}.{suffix}")
        return treat_disabled_smtp_as_done

    if not is_smtp_ready_to_send():
        print(
            "Newsletter not sent (SMTP configuration incomplete); "
            f"subject={title!r} reason={smtp_not_ready_reason()!r}"
        )
        return False

    if bool(SMTP_USER) != bool(SMTP_PASSWORD):
        print(
            "Newsletter not sent (SMTP auth configuration incomplete); "
            f"subject={title!r} reason={'both SMTP_USER and SMTP_PASSWORD are required for auth'}"
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = formataddr((SMTP_FROM_NAME or "", SMTP_FROM_EMAIL or ""))
    msg["To"] = email_to
    msg.set_content("Your email client does not support HTML content.")
    msg.add_alternative(content, subtype="html")

    recipient_hint = _recipient_hint(email_to)
    try:
        if SMTP_USE_SSL:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as server:
                _smtp_send_message(server, msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as server:
                if SMTP_USE_TLS:
                    server.starttls(context=ssl.create_default_context())
                _smtp_send_message(server, msg)
        print(f"Newsletter sent successfully; subject={title!r} to={recipient_hint!r}")
        return True
    except (smtplib.SMTPException, OSError) as exc:
        print(
            "Newsletter send failed; "
            f"subject={title!r} to={recipient_hint!r} error_type={exc.__class__.__name__}"
        )
        return False

def issue_todays_newsletters():
    valid_skill_ids = _get_valid_skill_ids()

    for skill_id in valid_skill_ids:
        time.sleep(5)
        tasks = get_tasks_based_on_skill_id(skill_id)
        if not tasks:
            continue

        for t in tasks:
            title = f"Day {t['day']} - {t['skill']}: {t['topic']}"
            blog_html = t["newsletter"]
            if blog_html is None:
                print(f"No newsletter for skill_id: {skill_id} | task: {t['id']}")
                continue

            email_id = get_email_id_from_skill_id(t["skill_id"])
            if not email_id:
                print(f"No email found for skill_id {t['skill_id']} — skipping task {t['id']}")
                continue
            if send_newsletter(
                email_to=email_id,
                title=title,
                content=blog_html,
                treat_disabled_smtp_as_done=True,
            ):
                mark_task_completed(t["id"])

    return True

def _get_valid_skill_ids():
    skill_ids = get_list_of_skill_ids()
    valid = []
    for skill_id in skill_ids:
        tasks = get_tasks_based_on_skill_id(skill_id)
        if tasks:
            valid.append(skill_id)
    return valid

def _smtp_send_message(server: smtplib.SMTP, msg: EmailMessage) -> None:
    if SMTP_USER and SMTP_PASSWORD:
        server.login(SMTP_USER, SMTP_PASSWORD)
    server.send_message(msg)

def _recipient_hint(email: str) -> str:
    if "@" not in email:
        return "[invalid]"
    return "@" + email.split("@", 1)[1]
