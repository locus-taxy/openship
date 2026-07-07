"""LLM generation for the onboarding / knowledge feature.

The onboarding-specific prompt calls live here; the shared multi-provider
plumbing (client building, token accounting, error handling) is imported from
the app's core services.llm.
"""

import logging
import re
from typing import List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator

from services.llm import (
    BlockType,
    ContentBlock,
    DEFAULT_MODELS,
    _build_client,
    _full_exc_msg,
    _raise_if_provider_error,
    _require_settings,
    _sanitize_json_escapes,
    _token_kwargs,
)
from onboarding.prompts import onboarding as onboarding_prompts
from onboarding.prompts import knowledge as knowledge_prompts

logger = logging.getLogger(__name__)

def _raise_if_truncated(exc: Exception, what: str) -> None:
    """Raise a specific 422 when the LLM response was cut off at its output-token
    limit (so the user gets an actionable "try again" rather than a generic 500) —
    mirrors the course-content generator."""
    msg = _full_exc_msg(exc)
    flat = msg.replace(" ", "").lower()
    low = msg.lower()
    if (
        "incompleteoutput" in flat
        or "due to a max_tokens length limit" in low
        or "finish_reason.max_tokens" in low
    ):
        raise HTTPException(
            status_code=422,
            detail=f"The {what} was too long and the response was cut off. "
            "Try again — it usually works on the next attempt.",
        )

def _generate_with_retry(provider: str, call, what: str, attempts: int = 2):
    """Run an instructor LLM call with one app-level retry and rich error mapping.

    `call` is a zero-arg function that makes the request and returns the parsed
    response. Provider errors (bad key / quota / overloaded / model access) and a
    truncated response raise a specific HTTPException; a transient error is retried
    once; anything still failing returns None (the caller maps that to its own
    message). Brings knowledge/onboarding to parity with course generation."""
    for attempt in range(attempts):
        try:
            return call()
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            _raise_if_provider_error(provider, e)  # 400 / 429 / 503 / model-access
            _raise_if_truncated(e, what)  # 422 cut-off
            if attempt < attempts - 1:
                logger.info(
                    "Retrying %s after a transient error [provider=%s]: %s",
                    what,
                    provider,
                    type(e).__name__,
                )
                continue
            logger.exception("%s failed [provider=%s]", what, provider)
            return None
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

    def _call():
        client = _build_client(provider, api_key)
        return client.chat.completions.create(
            model=model,
            response_model=GeneratedOnboardingPlan,
            messages=[
                {"role": "system", "content": onboarding_prompts.plan_system_prompt(role, company)},
                {
                    "role": "user",
                    "content": onboarding_prompts.plan_user_prompt(role, company, docs_text),
                },
            ],
            **_token_kwargs(provider, 4096),
            max_retries=1,
        )

    response = _generate_with_retry(provider, _call, what="onboarding plan")
    if response is None:
        return None
    if not response.days or len(response.days) != 7:
        logger.warning(
            "Onboarding plan generation returned %d days, expected 7 [provider=%s]",
            len(response.days) if response.days else 0,
            provider,
        )
        return None
    return [d.model_dump() for d in response.days]

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
    """Generate structured block content for a single onboarding day."""
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]

    max_tokens = 32768 if provider == "gemini" else 16384 if provider == "openai" else 8192

    def _call():
        client = _build_client(provider, api_key)
        return client.chat.completions.create(
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
            **_token_kwargs(provider, max_tokens),
            max_retries=1,
        )

    response = _generate_with_retry(provider, _call, what="day content")
    if response is None or not response.blocks:
        if response is not None:
            logger.warning(
                "Onboarding day content returned 0 blocks [provider=%s day=%d]", provider, day
            )
        return None
    return response

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
        # Extract the intended option letter robustly. A bare "b"/"B" is used as-is;
        # a phrase like "The correct answer is B" or "b) ..." yields the standalone
        # a/b/c/d token (word-boundary match, so the 'c' inside "correct" is ignored).
        # Falls back to "a" only when no valid option letter is present at all.
        s = (v or "").strip().lower()
        if s in ("a", "b", "c", "d"):
            return s
        m = re.search(r"\b([abcd])\b", s)
        return m.group(1) if m else "a"

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
    """Generate a final onboarding quiz grounded in company docs. Returns list of dicts or None."""
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]

    def _call():
        client = _build_client(provider, api_key)
        return client.chat.completions.create(
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

    response = _generate_with_retry(provider, _call, what="quiz")
    if response is None or not response.questions:
        if response is not None:
            logger.warning(
                "Onboarding quiz generation returned 0 questions [provider=%s]", provider
            )
        return None
    if len(response.questions) != num_questions:
        logger.warning(
            "Onboarding quiz returned %d questions, expected %d [provider=%s]",
            len(response.questions),
            num_questions,
            provider,
        )
        return None
    return [q.model_dump() for q in response.questions]

class KnowledgeBlocks(StructuredOnboardingDayContent):
    """A structured, block-based knowledge answer. Same block shape (and lenient
    JSON parsing / empty-block filtering) as onboarding day content, so the shared
    frontend BlockRenderer renders it identically. `used_docs` flags whether the
    answer is grounded in the company docs (vs a greeting / general knowledge)."""

    used_docs: bool = Field(
        default=True,
        description="True only if the answer is grounded in the provided company docs",
    )

def answer_blocks_from_context(
    question: str,
    context: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    history: Optional[List[dict]] = None,
) -> Optional[dict]:
    """Answer as structured content blocks — grounded in the docs when they cover
    it, otherwise conversationally / from general knowledge. Returns
    {"blocks": [...], "used_docs": bool} or None."""
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]
    max_tokens = 16384 if provider in ("gemini", "openai") else 8192

    messages = [{"role": "system", "content": knowledge_prompts.knowledge_blocks_system_prompt()}]
    for turn in history or []:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append(
        {
            "role": "user",
            "content": knowledge_prompts.knowledge_blocks_user_prompt(question, context),
        }
    )

    def _call():
        client = _build_client(provider, api_key)
        return client.chat.completions.create(
            model=model,
            response_model=KnowledgeBlocks,
            messages=messages,
            **_token_kwargs(provider, max_tokens),
            max_retries=1,
        )

    response = _generate_with_retry(provider, _call, what="answer")
    if response is None or not response.blocks:
        if response is not None:
            logger.warning("Knowledge blocks answer returned 0 blocks [provider=%s]", provider)
        return None
    return {
        "blocks": [b.model_dump() for b in response.blocks],
        "used_docs": bool(response.used_docs),
    }

class PeopleQuery(BaseModel):
    """Planner output: is this question about specific people's work/involvement, and
    if so, which people and in what mode (count/compare vs list/summarize)?"""

    intent: str = Field(
        default="other",
        description=(
            "'count' if comparing/counting specific named people (who did more, X or "
            "Y); 'list' if summarizing a person's work (what is X working on, all work "
            "of X, tell me about X); 'leaderboard' if an OPEN-ENDED ranking across "
            "everyone (who reported the most, top contributors, who has the most "
            "issues); 'other' for anything else."
        ),
    )
    people: List[str] = Field(
        default_factory=list,
        description="Person names asked about, exactly as written. Empty if none "
        "(leaderboard questions usually have no specific people).",
    )
    metric: str = Field(
        default="involved",
        description=(
            "For a 'leaderboard' only: rank by 'reported' (who filed/reported the "
            "most), 'assigned' (most assigned), 'authored' (most Confluence docs), or "
            "'involved' (overall / top contributors — the default)."
        ),
    )

def extract_people_query(
    question: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    history: Optional[List[dict]] = None,
) -> Optional[dict]:
    """Classify a question about people: intent ('count' | 'list' | 'other') and the
    people named. `history` (prior turns) lets it resolve pronouns ('his work' →
    the person discussed earlier). Returns {"intent", "people"} or None on failure."""
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]
    messages = [{"role": "system", "content": knowledge_prompts.people_query_system_prompt()}]
    for turn in history or []:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": question})

    def _call() -> PeopleQuery:
        client = _build_client(provider, api_key)
        return client.chat.completions.create(
            model=model,
            response_model=PeopleQuery,
            messages=messages,
            **_token_kwargs(provider, 512),
            max_retries=1,
        )

    response = _generate_with_retry(provider, _call, what="people-query extraction")
    if response is None:
        return None
    valid_intents = ("count", "list", "leaderboard", "other")
    intent = response.intent if response.intent in valid_intents else "other"
    people = [p.strip() for p in (response.people or []) if p and p.strip()]
    valid_metrics = ("assigned", "reported", "authored", "involved")
    metric = response.metric if response.metric in valid_metrics else "involved"
    return {"intent": intent, "people": people[:5], "metric": metric}

class KnowledgeAnswer(BaseModel):
    answer: str = Field(description="The answer, grounded only in the provided documentation")

def answer_from_context(
    question: str,
    context: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    history: Optional[List[dict]] = None,
) -> Optional[str]:
    """Answer a question grounded in retrieved documentation, optionally with prior
    conversation turns for follow-up context. `history` is a list of
    {"role": "user"|"assistant", "content": str}. Returns text or None."""
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]

    messages = [{"role": "system", "content": knowledge_prompts.knowledge_system_prompt()}]
    for turn in history or []:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append(
        {"role": "user", "content": knowledge_prompts.knowledge_user_prompt(question, context)}
    )

    def _call() -> KnowledgeAnswer:
        client = _build_client(provider, api_key)
        return client.chat.completions.create(
            model=model,
            response_model=KnowledgeAnswer,
            messages=messages,
            **_token_kwargs(provider, 2048),
            max_retries=1,
        )

    response = _generate_with_retry(provider, _call, what="answer")
    return response.answer if response is not None else None
