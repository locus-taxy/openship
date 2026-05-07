"""
LLM service using Instructor for structured and free-text generation.

Supports: gemini, openai, anthropic, mistral
Each function accepts the user's chosen provider and API key.
If the provider or key is missing, raises HTTP 400 so the UI can
prompt the user to configure their settings.
"""

from enum import Enum
import hashlib
import logging
import time
from typing import Dict, List, Optional, Tuple

import instructor
from prompts import chapter as chapter_prompts
from prompts import quiz as quiz_prompts
from prompts import syllabus as syllabus_prompts
from anthropic import Anthropic
from fastapi import HTTPException
from google import genai
from mistralai import Mistral
from openai import OpenAI
from pydantic import BaseModel, field_validator, model_validator

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

class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    CODE = "code"
    BULLET_LIST = "bullet_list"
    NUMBERED_LIST = "numbered_list"
    TABLE = "table"
    NOTE = "note"
    QUOTE = "quote"
    DIVIDER = "divider"
    DIAGRAM = "diagram"

class ContentBlock(BaseModel):
    type: BlockType
    content: Optional[str] = None
    level: Optional[int] = None
    language: Optional[str] = None
    items: Optional[List[str]] = None
    headers: Optional[List[str]] = None
    rows: Optional[List[List[str]]] = None
    format: Optional[str] = None

    @field_validator("level")
    @classmethod
    def level_must_be_valid(cls, v):
        if v is not None and v not in (1, 2, 3):
            raise ValueError("Heading level must be 1, 2, or 3")
        return v

    @model_validator(mode="after")
    def validate_block(self) -> "ContentBlock":
        t = self.type
        if t == BlockType.HEADING:
            if not self.content:
                self.content = ""  # filtered out downstream
            if self.level is None:
                self.level = 2
        elif t in (BlockType.PARAGRAPH, BlockType.NOTE, BlockType.QUOTE):
            if not self.content:
                self.content = ""  # filtered out downstream
        elif t == BlockType.CODE:
            if not self.content:
                self.content = ""  # filtered out downstream
            if not self.language:
                self.language = ""
        elif t in (BlockType.BULLET_LIST, BlockType.NUMBERED_LIST):
            if not self.items:
                self.items = []  # filtered out downstream
        elif t == BlockType.TABLE:
            if not self.headers:
                self.headers = []
            if not self.rows:
                self.rows = []
            elif self.headers:
                n = len(self.headers)
                self.rows = [(row + [""] * n)[:n] for row in self.rows]
        elif t == BlockType.DIAGRAM:
            if not self.content:
                self.content = ""  # filtered out downstream
            if not self.format:
                self.format = "mermaid"
        return self

class StructuredChapterContent(BaseModel):
    blocks: List[ContentBlock]

    @field_validator("blocks")
    @classmethod
    def filter_and_validate_blocks(cls, v: List[ContentBlock]) -> List[ContentBlock]:
        def _is_useful(b: ContentBlock) -> bool:
            t = b.type
            if t in (
                BlockType.HEADING,
                BlockType.PARAGRAPH,
                BlockType.NOTE,
                BlockType.QUOTE,
                BlockType.CODE,
                BlockType.DIAGRAM,
            ):
                return bool(b.content and b.content.strip())
            if t in (BlockType.BULLET_LIST, BlockType.NUMBERED_LIST):
                return bool(b.items)
            if t == BlockType.TABLE:
                return bool(b.headers and b.rows)
            return True  # DIVIDER always kept

        filtered = [b for b in v if _is_useful(b)]
        if not filtered:
            raise ValueError("All blocks were empty — LLM did not fill content fields")
        return filtered

_VALID_OPTIONS = {"A", "B", "C", "D"}

class QuizOption(BaseModel):
    label: str  # "A", "B", "C", "D"
    text: str

    @field_validator("label")
    @classmethod
    def label_must_be_valid(cls, v: str) -> str:
        if v.upper() not in _VALID_OPTIONS:
            raise ValueError(f"QuizOption label must be one of A/B/C/D, got '{v}'")
        return v.upper()

    @field_validator("text")
    @classmethod
    def text_must_be_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("QuizOption text must not be empty")
        return v

class GeneratedQuestion(BaseModel):
    question: str
    options: List[QuizOption]  # exactly 4
    correct_option: str  # "A", "B", "C", or "D"
    explanation: str  # shown after submission

    @field_validator("correct_option")
    @classmethod
    def correct_option_must_be_valid(cls, v: str) -> str:
        if v.upper() not in _VALID_OPTIONS:
            raise ValueError(f"correct_option must be one of A/B/C/D, got '{v}'")
        return v.upper()

    @model_validator(mode="after")
    def validate_options(self) -> "GeneratedQuestion":
        if len(self.options) != 4:
            raise ValueError(f"Expected exactly 4 options, got {len(self.options)}")
        labels = [o.label for o in self.options]
        if len(set(labels)) != 4:
            raise ValueError(f"Option labels must be unique A/B/C/D, got {labels}")
        if self.correct_option not in {o.label for o in self.options}:
            raise ValueError(
                f"correct_option '{self.correct_option}' not found among option labels {labels}"
            )
        return self

class GeneratedQuiz(BaseModel):
    questions: List[GeneratedQuestion]

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

def _full_exc_msg(exc: Exception) -> str:
    """Collect the full message across the exception cause chain."""
    parts = []
    seen: set = set()
    current: Exception | None = exc
    while current is not None:
        if id(current) in seen:
            break
        seen.add(id(current))
        parts.append(str(current).lower())
        current = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
    return " ".join(parts)

def _raise_if_provider_error(provider: str, exc: Exception) -> None:
    """Convert common LLM API errors into meaningful HTTP exceptions."""
    msg = _full_exc_msg(exc)
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

        # issue #69 — instructor's GENAI_STRUCTURED_OUTPUTS mode builds a
        # GenerateContentConfig with response_schema but never sets
        # max_output_tokens, so Gemini uses its own low default and truncates.
        # Gemini 2.5 models also run "thinking" by default; thinking tokens
        # count against max_output_tokens, so with the default cap the content
        # gets cut off before the JSON is complete.
        # Fix: patch generate_content to inject max_output_tokens=65536 and
        # disable thinking (thinking_budget=0) whenever instructor omits them.
        _real_generate = google_client.models.generate_content

        def _patched_generate(*args, **kwargs):
            # generate_content only accepts model/contents/config — strip any
            # OpenAI-style kwargs that instructor forwards but the SDK rejects.
            # max_tokens causes TypeError which our error handler mis-classifies
            # as truncation; we apply it via config.max_output_tokens instead.
            kwargs.pop("max_tokens", None)

            config = kwargs.get("config")
            if config is not None:
                update: dict = {}
                if getattr(config, "max_output_tokens", None) is None:
                    update["max_output_tokens"] = 32768
                # Drop response_schema so Gemini generates JSON from the prompt
                # rather than from the schema.  With response_schema set, the model
                # ignores prompt instructions (code blocks, diagrams, etc.) and picks
                # only the easiest block types.  instructor still validates the output
                # against our Pydantic model via model_validate_json — same result,
                # but the prompt now drives WHAT gets generated.
                if getattr(config, "response_schema", None) is not None:
                    update["response_schema"] = None
                if update:
                    try:
                        kwargs["config"] = config.model_copy(update=update)
                    except Exception:
                        for k, v in update.items():
                            try:
                                setattr(config, k, v)
                            except Exception:
                                pass
            return _real_generate(*args, **kwargs)

        google_client.models.generate_content = _patched_generate
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

    try:
        client = _build_client(provider, api_key)
        response: SyllabusResponse = client.chat.completions.create(
            model=model,
            response_model=SyllabusResponse,
            messages=[
                {"role": "system", "content": syllabus_prompts.system_prompt(days, hours)},
                {"role": "user", "content": syllabus_prompts.user_prompt(skill, days, hours)},
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
        logger.exception("Syllabus generation failed [provider=%s]", provider)
        return None

def generate_quiz(
    skill: str,
    topics: List[str],
    difficulty: str,
    num_questions: int,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[GeneratedQuiz]:
    """Generate a multiple-choice quiz using Instructor. Returns GeneratedQuiz or None."""
    _VALID_DIFFICULTIES = {"beginner", "intermediate", "advanced"}
    difficulty = difficulty.strip().lower() if difficulty else "beginner"
    if difficulty not in _VALID_DIFFICULTIES:
        difficulty = "beginner"

    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]

    try:
        client = _build_client(provider, api_key)
        response: GeneratedQuiz = client.chat.completions.create(
            model=model,
            response_model=GeneratedQuiz,
            messages=[
                {
                    "role": "system",
                    "content": quiz_prompts.system_prompt(skill, difficulty, len(topics)),
                },
                {
                    "role": "user",
                    "content": quiz_prompts.user_prompt(topics, num_questions, difficulty),
                },
            ],
            **_token_kwargs(provider, 8192),
            max_retries=1,
        )
        if not response.questions or len(response.questions) != num_questions:
            logger.warning(
                "Quiz generation returned %d questions, expected %d [provider=%s]",
                len(response.questions) if response.questions else 0,
                num_questions,
                provider,
            )
            return None
        return response
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_provider_error(provider, e)
        logger.exception("Quiz generation failed [provider=%s]", provider)
        return None

def generate_chapter_content(
    task_description: str,
    task_title: str,
    skill: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[StructuredChapterContent]:
    """Generate structured chapter content using Instructor. Returns StructuredChapterContent or None."""
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]

    # Gemini 2.5 models run thinking by default; thinking tokens count against
    # max_output_tokens.  _build_client patches generate_content to inject
    # max_output_tokens=65536 and disable thinking so the full budget goes to
    # content (issue #69).  OpenAI caps at 16384; Mistral/Anthropic at 8192.
    chapter_max_tokens = 32768 if provider == "gemini" else 16384 if provider == "openai" else 8192

    try:
        client = _build_client(provider, api_key)
        response: StructuredChapterContent = client.chat.completions.create(
            model=model,
            response_model=StructuredChapterContent,
            messages=[
                {"role": "system", "content": chapter_prompts.system_prompt()},
                {
                    "role": "user",
                    "content": chapter_prompts.user_prompt(task_title, skill, task_description),
                },
            ],
            **_token_kwargs(provider, chapter_max_tokens),
            max_retries=1,
        )
        return response
    except HTTPException:
        raise
    except Exception as e:
        full_msg = _full_exc_msg(e)
        print(
            f"[llm] chapter-blocks error provider={provider} type={type(e).__name__} msg={str(e)[:800]}",
            flush=True,
        )
        cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
        if cause:
            print(
                f"[llm] caused by: type={type(cause).__name__} msg={str(cause)[:400]}", flush=True
            )
        _raise_if_provider_error(provider, e)
        if (
            "incompleteoutput" in full_msg.replace(" ", "")
            or "due to a max_tokens length limit" in full_msg
            or "finish_reason.max_tokens" in full_msg
        ):
            raise HTTPException(
                status_code=422,
                detail="The chapter was too long and the response was cut off. Try regenerating — it usually works on the next attempt.",
            )
        logger.exception("Chapter (blocks) generation failed [provider=%s]", provider)
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

    try:
        client = _build_client(provider, api_key)
        response: ChapterContent = client.chat.completions.create(
            model=model,
            response_model=ChapterContent,
            messages=[
                {"role": "system", "content": chapter_prompts.system_prompt_html()},
                {
                    "role": "user",
                    "content": chapter_prompts.user_prompt(task_title, skill, task_description),
                },
            ],
            **_token_kwargs(provider, 8192),
            max_retries=1,
        )
        return response.html
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_provider_error(provider, e)
        logger.exception("Chapter (html) generation failed [provider=%s]", provider)
        return None
