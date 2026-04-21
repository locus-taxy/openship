"""
LLM service using Instructor for structured and free-text generation.

Supports: gemini, openai, anthropic, mistral
Each function accepts the user's chosen provider and API key.
If the provider or key is missing, raises HTTP 400 so the UI can
prompt the user to configure their settings.
"""

import hashlib
import logging
import time
from typing import Dict, List, Optional, Tuple

import instructor
from anthropic import Anthropic
from fastapi import HTTPException
from google import genai
from mistralai import Mistral
from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Supported providers ───────────────────────────────────────────────────────

SUPPORTED_PROVIDERS = {"gemini", "openai", "anthropic", "mistral"}

PROVIDER_LABELS = {
    "gemini": "Google Gemini",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "mistral": "Mistral",
}

# Default model per provider — sensible and cost-effective choices
DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash-lite",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "mistral": "mistral-small-latest",
}

# Available models per provider (first entry = default)
PROVIDER_MODELS = {
    "gemini": [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ],
    "openai": ["gpt-4o-mini", "gpt-4o"],
    "anthropic": ["claude-3-5-haiku-latest", "claude-3-5-sonnet-latest", "claude-3-opus-latest"],
    "mistral": ["mistral-small-latest", "mistral-large-latest"],
}

# ── Dynamic model list (cached 1 h per provider+key) ─────────────────────────

# Cache: { (provider, key_hash) -> (fetched_at_epoch, [model_ids]) }
_model_cache: Dict[Tuple[str, str], Tuple[float, List[str]]] = {}
_MODEL_CACHE_TTL = 3600  # 1 hour

# Keywords that indicate a model is NOT a text generation model
_SKIP_KEYWORDS = {
    "tts",
    "audio",
    "image",
    "embed",
    "vision",
    "video",
    "nano-banana",
    "lyria",
    "research",
    "live",
}

def _should_skip(model_id: str) -> bool:
    low = model_id.lower()
    return any(kw in low for kw in _SKIP_KEYWORDS)

def _key_hash(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]

def fetch_provider_models(provider: str, api_key: str) -> List[str]:
    """
    Fetch available text-generation models from the provider's API.
    Results are cached for 1 hour. Falls back to PROVIDER_MODELS on error.
    """
    cache_key = (provider, _key_hash(api_key))
    now = time.time()
    if cache_key in _model_cache:
        fetched_at, cached = _model_cache[cache_key]
        if now - fetched_at < _MODEL_CACHE_TTL:
            return cached

    try:
        models: List[str] = []

        if provider == "gemini":
            client = genai.Client(api_key=api_key)
            for m in client.models.list():
                name = m.name  # "models/gemini-2.5-flash"
                actions = getattr(m, "supported_actions", []) or []
                if "generateContent" not in actions:
                    continue
                model_id = name.split("/")[-1]  # strip "models/" prefix
                if not _should_skip(model_id):
                    models.append(model_id)

        elif provider == "openai":
            client = OpenAI(api_key=api_key)
            for m in client.models.list().data:
                mid = m.id
                # Only include chat-capable models (gpt-* and o-series)
                if (
                    mid.startswith("gpt-") or mid.startswith("o1") or mid.startswith("o3")
                ) and not _should_skip(mid):
                    models.append(mid)
            # Sort: newest first (alphabetically descending works well for gpt names)
            models.sort(reverse=True)

        elif provider == "anthropic":
            # Anthropic has no public list-models API — use curated fallback
            models = PROVIDER_MODELS["anthropic"]

        elif provider == "mistral":
            client = Mistral(api_key=api_key)
            result = client.models.list()
            for m in result.data or []:
                mid = m.id
                if not _should_skip(mid):
                    models.append(mid)
            models.sort()

        # Ensure the default is first
        default = DEFAULT_MODELS.get(provider)
        if default and default in models:
            models.remove(default)
            models.insert(0, default)
        elif default:
            models.insert(0, default)

        if models:
            _model_cache[cache_key] = (now, models)
            return models

    except Exception as e:
        logger.warning("Could not fetch model list [provider=%s]: %s", provider, e)

    # Fallback to hardcoded list
    return PROVIDER_MODELS.get(provider, [])

# ── Pydantic output schemas ───────────────────────────────────────────────────

class DailyPlan(BaseModel):
    day: int
    topic: str
    task: str

class Week(BaseModel):
    week: int
    title: str
    days_range: str
    daily_plan: List[DailyPlan]

class Month(BaseModel):
    month: int
    title: str
    goal: str
    weeks: List[Week]

class SyllabusResponse(BaseModel):
    months: List[Month]

class ChapterContent(BaseModel):
    html: str

# ── Internal helpers ──────────────────────────────────────────────────────────

def _norm(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = value.strip()
    return s if s else None

def _require_settings(provider: Optional[str], api_key: Optional[str]):
    """Raise HTTP 400 if provider or key are not configured."""
    p = _norm(provider)
    k = _norm(api_key)
    if not p or not k:
        raise HTTPException(
            status_code=400,
            detail="LLM provider and API key not set. Please configure them in Settings.",
        )
    if p not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported LLM provider '{p}'. Choose from: {', '.join(sorted(SUPPORTED_PROVIDERS))}.",
        )
    return p, k

def _raise_if_provider_error(provider: str, exc: Exception) -> None:
    """Convert common LLM API errors into meaningful HTTP exceptions."""
    msg = str(exc).lower()
    # "rate" alone is too broad — "generate" contains "rate" and would false-positive.
    # Match specific rate/quota patterns instead.
    if (
        "429" in msg
        or "resource_exhausted" in msg
        or "quota" in msg
        or "rate limit" in msg
        or "rate_limit" in msg
        or "too many requests" in msg
        or "insufficient_quota" in msg
    ):
        raise HTTPException(
            status_code=429,
            detail=f"Your {PROVIDER_LABELS.get(provider, provider)} quota is exhausted or rate-limited. "
            "Please wait a while or check your plan/billing.",
        )
    if (
        "401" in msg
        or "403" in msg
        or "api key not valid" in msg
        or ("invalid_argument" in msg and "key" in msg)
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {PROVIDER_LABELS.get(provider, provider)} API key. "
            "Please update it in Settings.",
        )

def _build_client(provider: str, api_key: str) -> instructor.Instructor:
    """Create an Instructor-patched client for the given provider."""
    if provider == "gemini":
        google_client = genai.Client(api_key=api_key)
        return instructor.from_genai(
            client=google_client, mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS
        )
    if provider == "openai":
        return instructor.from_openai(OpenAI(api_key=api_key))
    if provider == "anthropic":
        return instructor.from_anthropic(Anthropic(api_key=api_key))
    if provider == "mistral":
        return instructor.from_mistral(Mistral(api_key=api_key))
    raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

def _token_kwargs(provider: str, max_tokens: int) -> dict:
    """
    Gemini handles token limits internally — passing any token kwarg causes errors.
    All other providers use max_tokens.
    """
    if provider == "gemini":
        return {}
    return {"max_tokens": max_tokens}

# ── Model verification ────────────────────────────────────────────────────────

def verify_model(provider: str, api_key: str, model: str) -> dict:
    """
    Verify a model name by making a minimal test call.
    Returns {"ok": True} or {"ok": False, "reason": str}.
    """
    try:
        client = _build_client(provider, api_key)

        class _Ping(BaseModel):
            reply: str

        client.chat.completions.create(
            model=model,
            response_model=_Ping,
            messages=[{"role": "user", "content": "Reply with the word ok."}],
            **_token_kwargs(provider, 50),
            max_retries=0,
        )
        return {"ok": True}
    except HTTPException as e:
        return {"ok": False, "reason": e.detail}
    except Exception as e:
        msg = str(e)
        if (
            "not found" in msg.lower()
            or "404" in msg
            or "invalid" in msg.lower()
            or "does not exist" in msg.lower()
        ):
            return {
                "ok": False,
                "reason": f"Model '{model}' not found for {PROVIDER_LABELS.get(provider, provider)}.",
            }
        if "429" in msg or "quota" in msg.lower() or "resource_exhausted" in msg.lower():
            # Quota error means the model exists but can't be called right now — treat as valid
            return {"ok": True, "note": "Quota limit hit but model exists."}
        return {"ok": False, "reason": f"Could not verify model: {msg[:120]}"}

# ── User helpers ──────────────────────────────────────────────────────────────

def get_user_provider_name(user) -> Optional[str]:
    """Return the provider name string (e.g. 'gemini') for the user's active provider."""
    if not user.llm_provider_id:
        return None
    from services.user import get_provider_by_id

    provider = get_provider_by_id(user.llm_provider_id)
    return provider.name if provider else None

def get_user_api_key(user) -> Optional[str]:
    """Return the decrypted API key for the user's current provider."""
    if not user.llm_provider_id:
        return None
    from services.user import get_provider_key

    return get_provider_key(user.id, user.llm_provider_id)

def get_user_model(user) -> Optional[str]:
    """Return the user's chosen model, falling back to the provider default."""
    if not user.llm_provider_id:
        return None
    from services.user import get_provider_model, get_provider_by_id

    provider = get_provider_by_id(user.llm_provider_id)
    if not provider:
        return None
    model = get_provider_model(user.id, user.llm_provider_id)
    return model or DEFAULT_MODELS.get(provider.name)

# ── Public functions ──────────────────────────────────────────────────────────

def generate_syllabus_json(
    skill: str,
    days: int,
    hours: int,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[list]:
    """Generate a structured syllabus using Instructor. Returns list of month dicts or None."""
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]

    system_prompt = (
        "You are an expert curriculum designer and career mentor. "
        "Create an in-depth, structured learning roadmap for the requested skill. "
        f"The total duration must be exactly {days} days with {hours} hours per day. "
        "Ensure daily tasks are specific, actionable, and progressively build depth."
    )
    user_query = (
        f"Create a comprehensive learning syllabus to master '{skill}'. "
        f"The plan must span exactly {days} days with {hours} hours per day. "
        "Return the complete roadmap."
    )

    try:
        client = _build_client(provider, api_key)
        response: SyllabusResponse = client.chat.completions.create(
            model=model,
            response_model=SyllabusResponse,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
            **_token_kwargs(provider, 8192),
            max_retries=1,
        )
        # Convert Pydantic → plain dicts (matches existing controller expectations)
        return [m.model_dump() for m in response.months]
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_provider_error(provider, e)
        logger.error("Syllabus generation failed [provider=%s]: %s", provider, e)
        return None

def generate_chapter_html(
    task_description: str,
    task_title: str,
    skill: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[str]:
    """Generate chapter HTML content using Instructor. Returns HTML string or None."""
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]

    system_prompt = (
        "You are a senior technical educator and blog writer. "
        "Write a detailed, beginner-friendly blog explaining the concept or task described. "
        "Focus on practical explanation, step-by-step instructions, examples, and insights. "
        "Return the response as clean HTML content with no CSS or extra metadata. "
        "While taking examples, make them relevant to the given skill and industry."
    )
    user_prompt = (
        f"Write a detailed blog about: {task_title}\n"
        f"Skill: {skill}\n"
        f"Task description: {task_description}"
    )

    try:
        client = _build_client(provider, api_key)
        response: ChapterContent = client.chat.completions.create(
            model=model,
            response_model=ChapterContent,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **_token_kwargs(provider, 8192),
            max_retries=1,
        )
        return response.html
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_provider_error(provider, e)
        logger.error("Chapter generation failed [provider=%s]: %s", provider, e)
        return None
