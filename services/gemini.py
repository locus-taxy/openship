import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit

import requests
from dotenv import dotenv_values

_JSON_HEADERS = {"Content-Type": "application/json"}
# Repo root (parent of `services/`)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

def _norm_env_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = value.strip()
    return s if s else None

def _fresh_gemini_creds() -> Tuple[Optional[str], Optional[str]]:
    """Re-read `.env` each call so uvicorn reload / IDE cwd cannot serve stale empty keys.

    Process environment overrides ``.env`` (non-empty ``GEMINI_*`` wins).
    """
    env_path = _PROJECT_ROOT / ".env"
    values = dotenv_values(env_path) if env_path.is_file() else {}
    key = _norm_env_str(os.getenv("GEMINI_API_KEY")) or _norm_env_str(values.get("GEMINI_API_KEY"))
    url = _norm_env_str(os.getenv("GEMINI_API_URL")) or _norm_env_str(values.get("GEMINI_API_URL"))
    return (key, url)

def _gemini_url_for_logs(gemini_url: str) -> str:
    """Log-safe Gemini base URL (no query string / API key)."""
    parts = urlsplit(gemini_url)
    if parts.scheme or parts.netloc:
        path = parts.path or ""
        return f"{parts.scheme}://{parts.netloc}{path}".rstrip("/") or gemini_url
    return gemini_url.split("?", 1)[0]

def _request_exc_message(exc: BaseException) -> str:
    return f"{type(exc).__name__}: request failed (details omitted to avoid leaking secrets)"

def _response_text_fingerprint(text: Optional[str]) -> Tuple[int, str]:
    """Length and short SHA-256 prefix of body text for logs (no raw content)."""
    raw = (text or "").encode("utf-8", errors="replace")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return len(raw), digest

def _format_http_response_audit(response: requests.Response) -> str:
    """Non-sensitive metadata for failed HTTP responses (no raw body)."""
    n, fp = _response_text_fingerprint(response.text)
    ct = (response.headers.get("Content-Type") or "").split(";")[0].strip()
    parts = [
        f"status={response.status_code}",
        f"body_len={n}",
        f"body_sha256_16={fp}",
    ]
    if ct:
        parts.append(f"content_type={ct!r}")
    return " ".join(parts)

def _extract_text(result: dict):
    """Extract text from Gemini response. Prefer non-thought parts; fall back to any text (thinking models)."""
    try:
        parts = result["candidates"][0]["content"]["parts"]
        preferred = []
        fallback = []
        for part in parts:
            if not isinstance(part, dict) or "text" not in part:
                continue
            t = part["text"]
            fallback.append(t)
            if not part.get("thought"):
                preferred.append(t)
        if preferred:
            return "".join(preferred)
        if fallback:
            return "".join(fallback)
    except (KeyError, IndexError, TypeError):
        pass
    return None

def _log_gemini_failure(
    context: str, result: Optional[Dict[str, Any]], response: Optional[requests.Response] = None
) -> None:
    """Print why a Gemini call produced no usable text (no raw response bodies)."""
    if response is not None and not response.ok:
        print(f"{context}: HTTP error {_format_http_response_audit(response)}")
        return
    if not result:
        print(f"{context}: empty JSON body")
        return
    if result.get("promptFeedback"):
        print(f"{context}: promptFeedback={result.get('promptFeedback')}")
    cands = result.get("candidates")
    if not cands:
        print(f"{context}: no candidates; top-level keys={list(result.keys())}")
        return
    c0 = cands[0]
    fr = c0.get("finishReason")
    if fr and fr != "STOP":
        print(f"{context}: finishReason={fr}")
    if "content" not in c0:
        print(f"{context}: candidate has no content; keys={list(c0.keys())}")

def _parse_syllabus_json_text(text: str):
    """Parse model JSON; tolerate optional ``` fences around the payload."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    return json.loads(raw)

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
    gemini_key, gemini_url = _fresh_gemini_creds()
    if not gemini_key:
        print("ERROR: GEMINI_API_KEY is missing (check .env next to config.py).")
        return None
    if not gemini_url:
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
                f"{gemini_url}?key={gemini_key}",
                headers=_JSON_HEADERS,
                data=json.dumps(payload),
                timeout=(10, 300),
            )
            response.raise_for_status()
            result = response.json()

            text = _extract_text(result)
            if text:
                try:
                    return _parse_syllabus_json_text(text)
                except json.JSONDecodeError as exc:
                    n, fp = _response_text_fingerprint(text)
                    print(
                        f"Syllabus JSON parse error: {exc}; "
                        f"extracted_text_len={n} extracted_text_sha256_16={fp}"
                    )
                    return None
            _log_gemini_failure("generate_syllabus_json", result, response)
            return None
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            print(f"Attempt {attempt + 1} failed: HTTP {status}")
            if e.response is not None:
                _log_gemini_failure("generate_syllabus_json (HTTPError)", None, e.response)
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
            print(
                f"Attempt {attempt + 1} failed: {_request_exc_message(e)} "
                f"(endpoint={_gemini_url_for_logs(gemini_url)})"
            )
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
    gemini_key, gemini_url = _fresh_gemini_creds()
    if not gemini_key:
        print("ERROR: GEMINI_API_KEY is missing (check .env next to config.py).")
        return None
    if not gemini_url:
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
            f"{gemini_url}?key={gemini_key}",
            headers=_JSON_HEADERS,
            data=json.dumps(payload),
            timeout=(10, 300),
        )
        response.raise_for_status()
        result = response.json()
        text = _extract_text(result)
        if text:
            return text
        _log_gemini_failure("generate_newsletter_html", result, response)
        return None
    except requests.exceptions.HTTPError as e:
        if e.response is not None:
            _log_gemini_failure("generate_newsletter_html (HTTPError)", None, e.response)
        print(
            f"Gemini newsletter API call failed: {type(e).__name__} "
            f"(endpoint={_gemini_url_for_logs(gemini_url)})"
        )
        return None
    except requests.exceptions.RequestException as e:
        print(
            f"Gemini newsletter API call failed: {_request_exc_message(e)} "
            f"(endpoint={_gemini_url_for_logs(gemini_url)})"
        )
        return None
    except json.JSONDecodeError:
        print("Failed to decode JSON from Gemini newsletter response.")
        return None
