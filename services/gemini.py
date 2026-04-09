import json
import time
import requests
from config import GEMINI_API_KEY, GEMINI_API_URL

def _extract_text(result: dict):
    """Extract the final text from a Gemini response, skipping any 'thought' parts."""
    try:
        parts = result["candidates"][0]["content"]["parts"]
        for part in reversed(parts):
            if part.get("thought"):
                continue
            if "text" in part:
                return part["text"]
    except (KeyError, IndexError):
        pass
    return None

SYLLABUS_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "month": {"type": "INTEGER", "description": "The month number (1, 2, 3, etc.)."},
            "title": {
                "type": "STRING",
                "description": "A descriptive title for the month's learning phase.",
            },
            "goal": {"type": "STRING", "description": "The main learning goal for this month."},
            "weeks": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "week": {
                            "type": "INTEGER",
                            "description": "The week number within the total duration.",
                        },
                        "title": {
                            "type": "STRING",
                            "description": "A title summarizing the week's topics.",
                        },
                        "days_range": {
                            "type": "STRING",
                            "description": "The range of days covered in this week.",
                        },
                        "daily_plan": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "day": {
                                        "type": "INTEGER",
                                        "description": "The day number in the overall plan.",
                                    },
                                    "topic": {
                                        "type": "STRING",
                                        "description": "The main topic for this day.",
                                    },
                                    "task": {
                                        "type": "STRING",
                                        "description": "A specific learning task for the day.",
                                    },
                                },
                                "propertyOrdering": ["day", "topic", "task"],
                            },
                        },
                    },
                    "propertyOrdering": ["week", "title", "days_range", "daily_plan"],
                },
            },
        },
        "propertyOrdering": ["month", "title", "goal", "weeks"],
    },
}

def generate_syllabus_json(skill: str, days: int, hours: int):
    """Call Gemini API to produce a structured syllabus. Returns parsed JSON list or None."""
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY is missing.")
        return None
    if not GEMINI_API_URL:
        print("ERROR: GEMINI_API_URL is missing.")
        return None

    system_prompt = (
        "You are an expert curriculum designer and career mentor. "
        "Your task is to create an in-depth, structured learning roadmap for the requested skill. "
        "The plan must strictly adhere to the provided JSON schema. "
        "The total duration must match the requested number of days. "
        "Ensure the daily tasks are specific, actionable, and cover the necessary depth."
    )
    user_query = (
        f"Create a comprehensive learning syllabus to master the skill '{skill}'. "
        f"The total plan must span exactly {days} days, with {hours} hours per day. "
        "Please generate the complete roadmap using the required JSON schema."
    )
    payload = {
        "contents": [{"parts": [{"text": user_query}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": SYLLABUS_SCHEMA,
        },
    }

    max_retries = 3
    delay = 2
    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=(10, 120),
            )
            response.raise_for_status()
            result = response.json()

            text = _extract_text(result)
            if text:
                return json.loads(text)
            print("Gemini returned unexpected structure.")
            return None
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            print(f"Attempt {attempt + 1} failed: HTTP {status}")
            if status == 429:
                print("Rate limited by Gemini API — try again in a few minutes.")
                return None
            if 400 <= status < 500:
                print(f"Client error {status} — not retrying.")
                return None
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2
            else:
                return None
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2
            else:
                return None
        except json.JSONDecodeError:
            print("Failed to decode JSON from Gemini response.")
            return None

def generate_newsletter_html(task_description: str, task_title: str, skill: str):
    """Call Gemini API to produce newsletter HTML for a single task. Returns HTML string or None."""
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY is missing.")
        return None
    if not GEMINI_API_URL:
        print("ERROR: GEMINI_API_URL is missing.")
        return None

    system_prompt = (
        "You are a senior technical educator and blog writer. "
        "Write a detailed, beginner-friendly blog explaining the concept or task described. "
        "Focus on practical explanation, step-by-step instructions, examples, and insights. "
        "Return the response as clean HTML content no css (no extra headers or metadata). "
        "This HTML content is sent via email, so do not create anything that is malicious, "
        "keep HTML to standard gmail format. "
        "While taking examples, take examples relevant to the industry or skill that is given."
    )
    user_prompt = (
        f"Write a detailed blog about the following title: {task_title} "
        f"for skill {skill} for task:\n\n{task_description}"
    )
    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
    }

    try:
        response = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            data=json.dumps(payload),
            timeout=(10, 120),
        )
        response.raise_for_status()
        result = response.json()
        text = _extract_text(result)
        if text:
            return text
        print("Unexpected Gemini API response structure.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Gemini newsletter API call failed: {e}")
        return None
    except json.JSONDecodeError:
        print("Failed to decode JSON from Gemini newsletter response.")
        return None
