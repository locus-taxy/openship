import time
import requests

from config import LINKIFYI_TOKEN
from services.skill import get_list_of_skill_ids, get_email_id_from_skill_id
from services.daily_task import get_tasks_based_on_skill_id, mark_task_completed
from services.refresh_token import get_new_jwt_token


def send_newsletter(email_to: str, title: str, content: str, token: str = None):
    effective_token = token or LINKIFYI_TOKEN
    url = "https://app.linkifyi.com/api/lexi/send-newsletter"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {effective_token}",
        "Cookie": f"TOKEN={effective_token}",
    }
    payload = {
        "emailTo": email_to,
        "templateId": "e545f7f9-5acc-47d4-9642-d5bcba6b22d4",
        "subject": title,
        "variables": {
            "6ee3029f-5e1e-4a77-ae2f-a2d9285f7b7a": title,
            "8a0194f8-4cb0-4655-b534-68c13b72100c": content,
        },
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        print(f"Newsletter sent to {email_to}: {title}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Failed to send newsletter to {email_to}: {e}")
        raise


def issue_todays_newsletters():
    token = get_new_jwt_token()
    valid_skill_ids = _get_valid_skill_ids()

    for skill_id in valid_skill_ids:
        time.sleep(5)
        tasks = get_tasks_based_on_skill_id(skill_id)
        if not tasks:
            continue

        for i, t in enumerate(tasks, 1):
            title = f"Day {t['day']} - {t['skill']}: {t['topic']}"
            blog_html = t['newsletter']
            if blog_html is None:
                print(f"No newsletter for skill_id: {skill_id} | task: {t['id']}")
                continue

            email_id = get_email_id_from_skill_id(t['skill_id'])
            try:
                send_newsletter(email_to=email_id, title=title, content=blog_html, token=token)
                mark_task_completed(t['id'])
            except requests.exceptions.RequestException:
                print(f"Skipping task {t['id']} — will retry next run")

    return True


def _get_valid_skill_ids():
    skill_ids = get_list_of_skill_ids()
    valid = []
    for skill_id in skill_ids:
        tasks = get_tasks_based_on_skill_id(skill_id)
        if tasks:
            valid.append(skill_id)
    return valid
