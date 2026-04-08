import time
from typing import Optional

from config import is_smtp_outbound_configured
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

    # SMTP configured but transport not implemented in this branch
    print(f"Newsletter not sent (SMTP transport not implemented); subject={title!r}")
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
