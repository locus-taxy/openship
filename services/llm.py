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
from typing import Any, Dict, List, Optional, Tuple

import instructor
from prompts import chapter as chapter_prompts
from prompts import onboarding as onboarding_prompts
from prompts import quiz as quiz_prompts
from prompts import syllabus as syllabus_prompts
from anthropic import Anthropic
from fastapi import HTTPException
from google import genai
from mistralai import Mistral
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator, model_validator

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
    "anthropic": "claude-haiku-4-5-20251001",
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
    "anthropic": [
        "claude-haiku-4-5-20251001",
        "claude-sonnet-4-6",
        "claude-opus-4-7",
        "claude-3-5-haiku-latest",
        "claude-3-5-sonnet-latest",
        "claude-3-opus-latest",
    ],
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
    day: int = Field(description="Day number within the week")
    topic: str = Field(description="Topic to study on this day")
    task: str = Field(description="Specific actionable task to complete")

class Week(BaseModel):
    week: int = Field(description="Week number within the month")
    title: str = Field(description="Theme or focus of this week")
    days_range: str = Field(description="Day range covered, e.g. 'Days 1-7'")
    daily_plan: List[DailyPlan] = Field(description="One entry per study day this week")

class Month(BaseModel):
    month: int = Field(description="Month number, starting from 1")
    title: str = Field(description="Theme or focus of this month")
    goal: str = Field(description="What the learner will achieve by end of month")
    weeks: List[Week] = Field(description="Weekly breakdown for this month")

class SyllabusResponse(BaseModel):
    months: List[Month] = Field(description="Complete month-by-month syllabus")

class SkillDomainClassification(BaseModel):
    is_technical: bool = Field(
        description="True if the skill involves coding, software, data science, maths, or engineering; False otherwise"
    )

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

    @model_validator(mode="before")
    @classmethod
    def strip_key_whitespace(cls, values):
        if isinstance(values, dict):
            return {k.strip(): v for k, v in values.items()}
        return values

    @field_validator("rows", mode="before")
    @classmethod
    def coerce_rows(cls, v):
        if not isinstance(v, list):
            return v
        fixed = []
        for row in v:
            if isinstance(row, dict):
                # Gemini sometimes wraps rows as {"content": [...]} instead of plain lists
                row = row.get("content") or (list(row.values())[0] if row else [])
            if isinstance(row, list):
                fixed.append([str(cell) for cell in row])
        return fixed

    @field_validator("level")
    @classmethod
    def level_must_be_valid(cls, v):
        if v is not None:
            return max(1, min(3, v))
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
            self.format = "mermaid"  # only supported format; reject anything else
        return self

_VALID_SIMPLE_ESCAPES = frozenset('"\\/bfnrt')
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

def _sanitize_json_escapes(s: str) -> str:
    """Escape any backslash sequences that are invalid in JSON.

    LLMs embedding code examples often emit raw C/C++/Rust escape sequences
    (e.g. \\s, \\0, \\uint32_t, \\unicode) inside JSON string values. This
    walks the string character-by-character and doubles any backslash that
    doesn't start a valid JSON escape, making the payload parseable without
    altering legitimate escape sequences.
    """
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        # Lone trailing backslash — double it
        if i + 1 >= n:
            out.append("\\\\")
            i += 1
            continue
        nxt = s[i + 1]
        if nxt in _VALID_SIMPLE_ESCAPES:
            out.append(c)
            out.append(nxt)
            i += 2
        elif nxt == "u":
            hex4 = s[i + 2 : i + 6]
            if len(hex4) == 4 and all(h in _HEX_CHARS for h in hex4):
                out.append(c)
                out.append(nxt)
                out.extend(hex4)
                i += 6
            else:
                # Invalid \uXXX or \unicode — escape the backslash only
                out.append("\\\\")
                i += 1
        else:
            # Any other invalid escape — escape the backslash only
            out.append("\\\\")
            i += 1
    return "".join(out)

class StructuredChapterContent(BaseModel):
    blocks: List[ContentBlock]

    @classmethod
    def model_validate_json(cls, json_data, *, strict=None, context=None):
        if isinstance(json_data, (bytes, bytearray)):
            json_data = json_data.decode("utf-8", errors="replace")
        if isinstance(json_data, str):
            json_data = _sanitize_json_escapes(json_data)
        return super().model_validate_json(json_data, strict=strict, context=context)

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

class GeneratedDayPlan(BaseModel):
    day: int
    topic: str
    task: str

class GeneratedWeekPlan(BaseModel):
    days: List[GeneratedDayPlan]

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
    """Collect messages across the full exception graph (both __cause__ and __context__)."""
    parts = []
    stack = [exc]
    seen: set = set()
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        parts.append(str(current).lower())
        cause = getattr(current, "__cause__", None)
        context = getattr(current, "__context__", None)
        if cause is not None:
            stack.append(cause)
        if context is not None:
            stack.append(context)
    return " ".join(parts)

def _get_status_code(exc: Exception) -> Optional[int]:
    """Walk the full exception graph (both __cause__ and __context__) and return
    the first HTTP status_code found. Anthropic and OpenAI SDK exceptions carry it
    as an attribute; exploring both branches avoids missing it when __cause__ and
    __context__ point to different exceptions."""
    stack = [exc]
    seen: set = set()
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        sc = getattr(current, "status_code", None)
        if isinstance(sc, int):
            return sc
        cause = getattr(current, "__cause__", None)
        context = getattr(current, "__context__", None)
        if cause is not None:
            stack.append(cause)
        if context is not None:
            stack.append(context)
    return None

def _raise_if_provider_error(provider: str, exc: Exception) -> None:
    """Convert common LLM API errors into meaningful HTTP exceptions."""
    msg = _full_exc_msg(exc)
    status_code = _get_status_code(exc)
    label = PROVIDER_LABELS.get(provider, provider)

    # Model overloaded / service unavailable
    if (
        status_code == 503
        or "503" in msg
        or "unavailable" in msg.lower()
        or "overloaded" in msg.lower()
        or "high demand" in msg.lower()
    ):
        raise HTTPException(
            status_code=503,
            detail=f"The {label} model is currently overloaded. Please try again in a moment or switch to a different model.",
        )

    # Rate limit / quota — string matching covers Gemini "resource_exhausted"
    # which doesn't carry a status_code attribute.
    if (
        status_code == 429
        or "429" in msg
        or "resource_exhausted" in msg
        or "quota" in msg
        or "rate limit" in msg
        or "rate_limit" in msg
        or "too many requests" in msg
        or "insufficient_quota" in msg
    ):
        raise HTTPException(
            status_code=429,
            detail=f"Your {label} quota is exhausted or rate-limited. "
            "Please wait a while or check your plan/billing.",
        )

    # Model not found — status_code 404 is the reliable signal;
    # string patterns cover providers that don't set status_code.
    if (
        status_code == 404
        or "model_not_found" in msg
        or "not_found_error" in msg
        or ("model" in msg and "not found" in msg)
        or ("model" in msg and "does not exist" in msg)
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Your {label} API key does not have access to the selected model. "
            "Please choose a different model in Settings.",
        )

    # Billing / insufficient credits (403 with credit keywords)
    if status_code == 403 and (
        "credit" in msg or "billing" in msg or "payment" in msg or "funds" in msg
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Your {label} account has insufficient credits. "
            "Please add credits to your account and try again.",
        )

    # Invalid API key — 401, bare 403, or provider-specific key-error strings
    if (
        status_code in (401, 403)
        or "401" in msg
        or "403" in msg
        or "api key not valid" in msg
        or ("invalid_argument" in msg and "key" in msg)
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {label} API key. " "Please update it in Settings.",
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
        # Fix: patch generate_content to inject max_output_tokens=32768 and
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
                # Disable thinking — no quality benefit for structured JSON output.
                from google.genai import types as _gtypes

                update["thinking_config"] = _gtypes.ThinkingConfig(thinking_budget=0)
                # Drop response_schema so Gemini generates JSON from the prompt
                # rather than from the schema.  With response_schema set, the model
                # ignores prompt instructions (code blocks, diagrams, etc.) and picks
                # only the easiest block types.  instructor still validates the output
                # against our Pydantic model via model_validate_json — same result,
                # but the prompt now drives WHAT gets generated.
                # Pair with response_mime_type so Gemini emits raw JSON instead of
                # markdown-wrapped JSON (```json...```) which breaks model_validate_json.
                if getattr(config, "response_schema", None) is not None:
                    update["response_schema"] = None
                    update["response_mime_type"] = "application/json"
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
        return instructor.from_mistral(Mistral(api_key=api_key, timeout_ms=90000))
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

# ── Token extraction ──────────────────────────────────────────────────────────

def extract_token_counts(
    raw_response: Any, provider_name: str
) -> Tuple[Optional[int], Optional[int]]:
    """
    Extract (input_tokens, output_tokens) from a raw provider API response.
    Returns (None, None) if unavailable or extraction fails — never raises.
    """
    if raw_response is None:
        return None, None
    try:
        if provider_name == "anthropic":
            usage = getattr(raw_response, "usage", None)
            return getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None)
        if provider_name in ("openai", "mistral"):
            usage = getattr(raw_response, "usage", None)
            return getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)
        if provider_name == "gemini":
            meta = getattr(raw_response, "usage_metadata", None)
            return (
                getattr(meta, "prompt_token_count", None),
                getattr(meta, "candidates_token_count", None),
            )
    except Exception as e:
        logger.warning("Token extraction failed [provider=%s]: %s", provider_name, e)
    return None, None

# ── Public functions ──────────────────────────────────────────────────────────

def classify_skill_domain(
    skill: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[bool]:
    """Return True if the skill is technical, False if non-technical, None on failure.

    Uses a tiny token budget (128 tokens) since only a boolean answer is needed.
    Called once at course creation; result is stored on the Skill row.
    """
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]
    try:
        client = _build_client(provider, api_key)
        response: SkillDomainClassification = client.chat.completions.create(
            model=model,
            response_model=SkillDomainClassification,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a domain classifier. Given a skill name, decide whether it is "
                        "technical (requires coding, programming, software development, data science, "
                        "mathematics, or engineering) or non-technical (business, communication, arts, "
                        "languages, psychology, management, sports, cooking, etc.). "
                        "Respond with is_technical: true or false."
                    ),
                },
                {"role": "user", "content": f"Skill: {skill}"},
            ],
            **_token_kwargs(provider, 128),
            max_retries=1,
        )
        logger.info(
            "Skill domain classified [skill=%r is_technical=%s provider=%s]",
            skill,
            response.is_technical,
            provider,
        )
        return response.is_technical
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(
            "Skill domain classification failed (non-fatal) [skill=%r provider=%s]: %s",
            skill,
            provider,
            e,
        )
        return None

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
        cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
        logger.error(
            "Syllabus generation error [provider=%s cause=%s]",
            provider,
            type(cause).__name__ if cause else "none",
            exc_info=True,
        )
        _raise_if_provider_error(provider, e)
        logger.exception(
            "Syllabus generation failed [provider=%s model=%s]: %s", provider, model, e
        )
        return None

def generate_weekly_quiz(
    skill: str,
    week: int,
    topics: List[str],
    num_questions: int,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    pool_size: int = 1,
) -> Optional[GeneratedQuiz]:
    """Generate a per-week quiz. Returns GeneratedQuiz or None.

    pool_size > 1 generates pool_size variants per unique question (num_questions * pool_size total).
    """
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]
    total_questions = num_questions * pool_size

    try:
        client = _build_client(provider, api_key)
        response: GeneratedQuiz = client.chat.completions.create(
            model=model,
            response_model=GeneratedQuiz,
            messages=[
                {
                    "role": "system",
                    "content": quiz_prompts.weekly_system_prompt(skill, week, len(topics)),
                },
                {
                    "role": "user",
                    "content": quiz_prompts.weekly_user_prompt(topics, total_questions),
                },
            ],
            **_token_kwargs(provider, 8192),
            max_retries=1,
        )
        if not response.questions:
            logger.warning("Weekly quiz generation returned 0 questions [provider=%s]", provider)
            return None
        if len(response.questions) != total_questions:
            logger.warning(
                "Weekly quiz generation returned %d questions, expected %d — using partial result [provider=%s]",
                len(response.questions),
                total_questions,
                provider,
            )
        return response
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_provider_error(provider, e)
        logger.exception("Weekly quiz generation failed [provider=%s]", provider)
        return None

def generate_final_quiz(
    skill: str,
    weak_topics: List[str],
    forgotten_topics: List[str],
    num_questions: int,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    topic_week_map: Optional[dict] = None,
    pool_size: int = 1,
) -> Optional[GeneratedQuiz]:
    """Generate the ML-personalised final quiz. Returns GeneratedQuiz or None.

    pool_size > 1 generates pool_size variants per unique question (num_questions * pool_size total).
    """
    all_topics = list(dict.fromkeys(weak_topics + forgotten_topics))
    if not all_topics:
        return None

    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]
    total_questions = num_questions * pool_size

    try:
        client = _build_client(provider, api_key)
        response: GeneratedQuiz = client.chat.completions.create(
            model=model,
            response_model=GeneratedQuiz,
            messages=[
                {
                    "role": "system",
                    "content": quiz_prompts.final_system_prompt(skill, len(all_topics)),
                },
                {
                    "role": "user",
                    "content": quiz_prompts.final_user_prompt(
                        weak_topics,
                        forgotten_topics,
                        total_questions,
                        topic_week_map=topic_week_map,
                    ),
                },
            ],
            **_token_kwargs(provider, 8192),
            max_retries=1,
        )
        if not response.questions:
            logger.warning("Final quiz generation returned 0 questions [provider=%s]", provider)
            return None
        if len(response.questions) != total_questions:
            logger.warning(
                "Final quiz generation returned %d questions, expected %d — using partial result [provider=%s]",
                len(response.questions),
                total_questions,
                provider,
            )
        return response
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_provider_error(provider, e)
        logger.exception("Final quiz generation failed [provider=%s]", provider)
        return None

def generate_chapter_content(
    task_description: str,
    task_title: str,
    skill: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    style: Optional[str] = None,
    is_technical: Optional[bool] = None,
) -> Tuple[Optional[StructuredChapterContent], Optional[int], Optional[int]]:
    """Generate structured chapter content using Instructor.

    Runs up to 2 generation attempts. After each successful generation,
    content is validated in two layers:
      1. Heuristic pre-filter (word count, placeholder text, code syntax, topic keywords)
      2. LLM-as-judge (relevance and factual correctness scored 1-10, pass >= 7)

    Returns (StructuredChapterContent, input_tokens, output_tokens) on success,
    (None, None, None) after two consecutive failures.
    """
    from services.content_validator import validate_content_heuristics, validate_content_with_llm

    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]

    # Gemini 2.5 models run thinking by default; thinking tokens count against
    # max_output_tokens.  _build_client patches generate_content to inject
    # max_output_tokens=32768 and disable thinking so the full budget goes to
    # content (issue #69).  OpenAI caps at 16384; Mistral/Anthropic at 8192.
    chapter_max_tokens = 32768 if provider == "gemini" else 16384 if provider == "openai" else 8192

    logger.info(
        "Chapter generation started [topic=%r skill=%r provider=%s model=%s style=%s]",
        task_title,
        skill,
        provider,
        model,
        style or "balanced",
    )

    for attempt in range(2):
        # ── Generation ────────────────────────────────────────────────────────
        logger.info(
            "Attempt %d/2 — calling LLM [provider=%s model=%s]",
            attempt + 1,
            provider,
            model,
        )
        try:
            client = _build_client(provider, api_key)
            response, raw = client.chat.completions.create_with_completion(
                model=model,
                response_model=StructuredChapterContent,
                messages=[
                    {
                        "role": "system",
                        "content": chapter_prompts.system_prompt(
                            concise=provider == "mistral", style=style, is_technical=is_technical
                        ),
                    },
                    {
                        "role": "user",
                        "content": chapter_prompts.user_prompt(task_title, skill, task_description),
                    },
                ],
                **_token_kwargs(provider, chapter_max_tokens),
                max_retries=1,
            )
            input_tokens, output_tokens = extract_token_counts(raw, provider)
            logger.info(
                "LLM returned %d block(s) [attempt=%d topic=%r]",
                len(response.blocks),
                attempt + 1,
                task_title,
            )
        except HTTPException:
            raise
        except Exception as e:
            full_msg = _full_exc_msg(e)
            cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
            logger.error(
                "Chapter generation error [attempt=%d provider=%s type=%s]: %s%s",
                attempt + 1,
                provider,
                type(e).__name__,
                str(e)[:800],
                f" - caused by [{type(cause).__name__}]: {str(cause)[:400]}" if cause else "",
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
            if attempt == 0:
                logger.info("Retrying after generation error...")
                continue
            logger.error(
                "Chapter generation failed on all attempts [topic=%r skill=%r provider=%s]",
                task_title,
                skill,
                provider,
            )
            return None, None, None

        # ── Layer 1: Heuristic validation ─────────────────────────────────────
        logger.info("Running heuristic validation [attempt=%d]", attempt + 1)
        heuristic = validate_content_heuristics(response.blocks, task_description, topic=task_title)
        if not heuristic.passed:
            logger.warning(
                "Heuristic validation FAILED [attempt=%d]: %s",
                attempt + 1,
                heuristic.reason,
            )
            if attempt == 0:
                logger.info("Retrying after heuristic failure...")
                continue
            logger.error(
                "Heuristic validation failed on all attempts [topic=%r reason=%s]",
                task_title,
                heuristic.reason,
            )
            return None, None, None
        logger.info("Heuristic validation PASSED [attempt=%d]", attempt + 1)

        # ── Hard gate: reject code blocks for non-technical skills ────────────
        if is_technical is False:
            has_code = any(getattr(b, "type", "") == "code" for b in response.blocks)
            if has_code:
                logger.warning(
                    "Non-technical chapter contains code block(s) [attempt=%d] — rejecting",
                    attempt + 1,
                )
                if attempt == 0:
                    logger.info("Retrying after non-technical code block rejection...")
                    continue
                return None, None, None

        # ── Layer 2: LLM-as-judge validation ──────────────────────────────────
        logger.info(
            "Running LLM judge [attempt=%d model=%s]",
            attempt + 1,
            model,
        )
        try:
            validation = validate_content_with_llm(
                blocks=response.blocks,
                task_description=task_description,
                skill=skill,
                client=client,
                model=model,
            )
            logger.info(
                "LLM judge returned score=%d valid=%s [attempt=%d]",
                validation.score,
                validation.valid,
                attempt + 1,
            )
            if not validation.valid:
                issues_str = (
                    "; ".join(validation.issues) if validation.issues else "score below threshold"
                )
                logger.warning(
                    "LLM judge FAILED [attempt=%d score=%d]: %s",
                    attempt + 1,
                    validation.score,
                    issues_str,
                )
                if attempt == 0:
                    logger.info("Retrying after LLM judge failure...")
                    continue
                # Both attempts failed the LLM judge, but both passed the heuristic
                # checks (word count, no placeholders, on-topic, no duplicates).
                # The judge is a quality signal, not a hard gate — content that is
                # structurally sound should always reach the user. Log a warning and
                # pass through rather than blocking with a blank chapter.
                logger.warning(
                    "LLM judge failed on both attempts [topic=%r score=%d issues=%s] — "
                    "content passed heuristics; passing through to avoid blank chapter",
                    task_title,
                    validation.score,
                    issues_str,
                )
            else:
                logger.info("LLM judge PASSED [attempt=%d score=%d]", attempt + 1, validation.score)
        except Exception as judge_exc:
            # Judge failure (e.g. API error) does not block valid content —
            # we log and pass through rather than reject good chapters.
            logger.warning(
                "LLM judge raised exception [attempt=%d type=%s]: %s — passing content through",
                attempt + 1,
                type(judge_exc).__name__,
                judge_exc,
            )

        logger.info(
            "Chapter generation complete [topic=%r skill=%r blocks=%d attempt=%d]",
            task_title,
            skill,
            len(response.blocks),
            attempt + 1,
        )
        return response, input_tokens, output_tokens

    logger.error(
        "Chapter generation failed after all attempts [topic=%r skill=%r provider=%s]",
        task_title,
        skill,
        provider,
    )
    return None, None, None

def generate_chapter_html(
    task_description: str,
    task_title: str,
    skill: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """
    Generate chapter HTML content using Instructor.
    Returns (html, input_tokens, output_tokens).
    html is None on failure; token counts are None if unavailable.
    """
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]

    try:
        client = _build_client(provider, api_key)
        response, raw = client.chat.completions.create_with_completion(
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
        input_tokens, output_tokens = extract_token_counts(raw, provider)
        return response.html, input_tokens, output_tokens
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_provider_error(provider, e)
        logger.exception("Chapter (html) generation failed [provider=%s]", provider)
        return None, None, None

def generate_week_plan(
    skill: str,
    week: int,
    total_weeks: int,
    weak_topics: List[str],
    forgotten_topics: List[str],
    days_in_week: int,
    start_day: int,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    prev_score: int = 100,
    remediation_days: int = 0,
) -> Optional[List[dict]]:
    """Generate ML-personalised daily plan for a specific week. Returns list of day dicts or None."""
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]
    try:
        client = _build_client(provider, api_key)
        response: GeneratedWeekPlan = client.chat.completions.create(
            model=model,
            response_model=GeneratedWeekPlan,
            messages=[
                {
                    "role": "system",
                    "content": syllabus_prompts.week_plan_system_prompt(
                        skill, week, total_weeks, days_in_week
                    ),
                },
                {
                    "role": "user",
                    "content": syllabus_prompts.week_plan_user_prompt(
                        week,
                        start_day,
                        days_in_week,
                        weak_topics,
                        forgotten_topics,
                        prev_score=prev_score,
                        remediation_days=remediation_days,
                    ),
                },
            ],
            **_token_kwargs(provider, 4096),
            max_retries=1,
        )
        if not response.days:
            return None
        day_numbers = [d.day for d in response.days]
        if (
            len(day_numbers) != days_in_week
            or len(set(day_numbers)) != days_in_week
            or min(day_numbers) != start_day
            or max(day_numbers) != start_day + days_in_week - 1
        ):
            logger.warning(
                "generate_week_plan: malformed days [got=%s expected=%d..%d]",
                sorted(day_numbers),
                start_day,
                start_day + days_in_week - 1,
            )
            return None
        return [d.model_dump() for d in response.days]
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_provider_error(provider, e)
        logger.exception("Week plan generation failed [provider=%s]", provider)
        return None

class OnboardingDayPlan(BaseModel):
    day: int = Field(description="Day number, 1 through 7")
    topic: str = Field(description="Short topic title for this day")
    task: str = Field(description="What the new joiner should read, explore, or do on this day")

class GeneratedOnboardingPlan(BaseModel):
    days: List[OnboardingDayPlan] = Field(description="Exactly 7 days of onboarding")

def generate_onboarding_plan(
    role: str,
    company: str,
    docs_text: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[List[dict]]:
    """Generate a 7-day onboarding plan from company docs. Returns list of day dicts or None."""
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]

    try:
        client = _build_client(provider, api_key)
        response: GeneratedOnboardingPlan = client.chat.completions.create(
            model=model,
            response_model=GeneratedOnboardingPlan,
            messages=[
                {"role": "system", "content": onboarding_prompts.plan_system_prompt(role)},
                {
                    "role": "user",
                    "content": onboarding_prompts.plan_user_prompt(role, company, docs_text),
                },
            ],
            **_token_kwargs(provider, 4096),
            max_retries=1,
        )
        if not response.days or len(response.days) != 7:
            logger.warning(
                "Onboarding plan generation returned %d days, expected 7 [provider=%s]",
                len(response.days) if response.days else 0,
                provider,
            )
            return None
        return [d.model_dump() for d in response.days]
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_provider_error(provider, e)
        logger.exception("Onboarding plan generation failed [provider=%s]", provider)
        return None

class StructuredOnboardingDayContent(BaseModel):
    blocks: List[ContentBlock]

    @classmethod
    def model_validate_json(cls, json_data, *, strict=None, context=None):
        if isinstance(json_data, (bytes, bytearray)):
            json_data = json_data.decode("utf-8", errors="replace")
        if isinstance(json_data, str):
            json_data = _sanitize_json_escapes(json_data)
        return super().model_validate_json(json_data, strict=strict, context=context)

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

def generate_onboarding_day_content(
    role: str,
    company: str,
    day: int,
    topic: str,
    task: str,
    docs_text: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[StructuredOnboardingDayContent]:
    """Generate structured block content for a single onboarding day using the onboarding-specific prompts."""
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]

    chapter_max_tokens = 32768 if provider == "gemini" else 16384 if provider == "openai" else 8192

    try:
        client = _build_client(provider, api_key)
        response: StructuredOnboardingDayContent = client.chat.completions.create(
            model=model,
            response_model=StructuredOnboardingDayContent,
            messages=[
                {
                    "role": "system",
                    "content": onboarding_prompts.day_content_system_prompt(role, company),
                },
                {
                    "role": "user",
                    "content": onboarding_prompts.day_content_user_prompt(
                        day, topic, task, company, docs_text
                    ),
                },
            ],
            **_token_kwargs(provider, chapter_max_tokens),
            max_retries=1,
        )
        if not response.blocks:
            logger.warning(
                "Onboarding day content returned 0 blocks [provider=%s day=%d]", provider, day
            )
            return None
        return response
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_provider_error(provider, e)
        logger.exception(
            "Onboarding day content generation failed [provider=%s day=%d]", provider, day
        )
        return None

class OnboardingQuestion(BaseModel):
    question: str = Field(description="The question text")
    option_a: str = Field(description="Option A text")
    option_b: str = Field(description="Option B text")
    option_c: str = Field(description="Option C text")
    option_d: str = Field(description="Option D text")
    correct_answer: str = Field(description="Correct option: a, b, c, or d (lowercase)")
    explanation: str = Field(
        description="Why the correct answer is right, citing the actual design rationale"
    )

    @field_validator("correct_answer")
    @classmethod
    def normalize_correct_answer(cls, v: str) -> str:
        return v.strip().lower()[0] if v.strip() else "a"

class GeneratedOnboardingQuiz(BaseModel):
    questions: List[OnboardingQuestion] = Field(description="Exactly 10 quiz questions")

def generate_onboarding_quiz(
    role: str,
    company: str,
    topics: List[str],
    docs_text: str,
    num_questions: int = 10,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[List[dict]]:
    """Generate a final onboarding quiz grounded in company docs. Returns list of question dicts or None."""
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]

    try:
        client = _build_client(provider, api_key)
        response: GeneratedOnboardingQuiz = client.chat.completions.create(
            model=model,
            response_model=GeneratedOnboardingQuiz,
            messages=[
                {"role": "system", "content": onboarding_prompts.quiz_system_prompt(role, company)},
                {
                    "role": "user",
                    "content": onboarding_prompts.quiz_user_prompt(
                        company, topics, num_questions, docs_text
                    ),
                },
            ],
            **_token_kwargs(provider, 8192),
            max_retries=1,
        )
        if not response.questions:
            logger.warning(
                "Onboarding quiz generation returned 0 questions [provider=%s]", provider
            )
            return None
        return [q.model_dump() for q in response.questions]
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_provider_error(provider, e)
        logger.exception("Onboarding quiz generation failed [provider=%s]", provider)
        return None

class OnboardingDocClassification(BaseModel):
    is_relevant: bool = Field(
        description="True if the page helps onboard a new engineer (product, architecture, codebase, setup, process)"
    )
    role_tags: List[str] = Field(
        default_factory=list,
        description='Roles it helps: subset of ["backend","devops","sdet","qa","product","general"]',
    )
    confidence: float = Field(description="Confidence from 0.0 to 1.0")

def classify_onboarding_doc(
    title: str,
    content_excerpt: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[dict]:
    """Classify whether a Confluence page is onboarding-relevant. Returns a dict
    {is_relevant, role_tags, confidence} or None on failure."""
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]

    try:
        client = _build_client(provider, api_key)
        response: OnboardingDocClassification = client.chat.completions.create(
            model=model,
            response_model=OnboardingDocClassification,
            messages=[
                {"role": "system", "content": onboarding_prompts.classify_system_prompt()},
                {
                    "role": "user",
                    "content": onboarding_prompts.classify_user_prompt(title, content_excerpt),
                },
            ],
            **_token_kwargs(provider, 512),
            max_retries=1,
        )
        return response.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_provider_error(provider, e)
        logger.exception("Onboarding doc classification failed [provider=%s]", provider)
        return None
