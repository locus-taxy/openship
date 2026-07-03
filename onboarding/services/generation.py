"""LLM generation for the onboarding / knowledge feature.

The onboarding-specific prompt calls live here; the shared multi-provider
plumbing (client building, token accounting, error handling) is imported from
the app's core services.llm.
"""

import logging
from typing import List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator

from services.llm import (
    BlockType,
    ContentBlock,
    DEFAULT_MODELS,
    _build_client,
    _raise_if_provider_error,
    _require_settings,
    _sanitize_json_escapes,
    _token_kwargs,
)
from onboarding.prompts import onboarding as onboarding_prompts
from onboarding.prompts import knowledge as knowledge_prompts

logger = logging.getLogger(__name__)

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
    """Generate structured block content for a single onboarding day."""
    provider, api_key = _require_settings(provider, api_key)
    model = model or DEFAULT_MODELS[provider]

    max_tokens = 32768 if provider == "gemini" else 16384 if provider == "openai" else 8192

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
            **_token_kwargs(provider, max_tokens),
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
    """Generate a final onboarding quiz grounded in company docs. Returns list of dicts or None."""
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

    try:
        client = _build_client(provider, api_key)
        response: KnowledgeBlocks = client.chat.completions.create(
            model=model,
            response_model=KnowledgeBlocks,
            messages=messages,
            **_token_kwargs(provider, max_tokens),
            max_retries=1,
        )
        if not response.blocks:
            logger.warning("Knowledge blocks answer returned 0 blocks [provider=%s]", provider)
            return None
        return {
            "blocks": [b.model_dump() for b in response.blocks],
            "used_docs": bool(response.used_docs),
        }
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_provider_error(provider, e)
        logger.exception("Knowledge blocks answer failed [provider=%s]", provider)
        return None

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

    try:
        client = _build_client(provider, api_key)
        response: KnowledgeAnswer = client.chat.completions.create(
            model=model,
            response_model=KnowledgeAnswer,
            messages=messages,
            **_token_kwargs(provider, 2048),
            max_retries=1,
        )
        return response.answer
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_provider_error(provider, e)
        logger.exception("Knowledge answer generation failed [provider=%s]", provider)
        return None
