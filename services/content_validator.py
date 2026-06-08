import logging
import re
from typing import Any, List

from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

MIN_WORDS = 80
LLM_JUDGE_PASS_SCORE = 7

# Patterns that indicate the AI left placeholder text instead of real content.
# "todo" uses \b word boundaries so it does not false-positive on "TodoMVC",
# "todo list" as a proper noun, or any word that merely contains "todo".
_PLACEHOLDER_RE = re.compile(
    # "todo:" catches developer annotation placeholders ("TODO: add content here",
    # "todo: fill in the blank") without false-positiving on "todo list" or
    # "Build a Todo App" which are legitimate content in any course.
    r"\btodo\s*:"
    r"|insert here"
    r"|lorem ipsum"
    r"|your content here"
    r"|add your code here"
    r"|write your code here"
    r"|fill in the blank"
    r"|your code goes here",
    re.IGNORECASE,
)

class HeuristicResult(BaseModel):
    passed: bool
    reason: str

class ContentValidationResult(BaseModel):
    valid: bool
    score: int
    issues: List[str]

    @field_validator("score")
    @classmethod
    def clamp_score(cls, v: int) -> int:
        return max(1, min(10, v))

def _extract_all_text(blocks: List[Any]) -> str:
    """Flatten all text content from blocks into a single lowercase string."""
    parts = []
    for b in blocks:
        if getattr(b, "content", None):
            parts.append(b.content)
        if getattr(b, "items", None):
            parts.extend(b.items)
        if getattr(b, "headers", None):
            parts.extend(b.headers)
        if getattr(b, "rows", None):
            for row in b.rows:
                parts.extend(str(cell) for cell in row)
    return " ".join(parts).lower()

def _blocks_to_text(blocks: List[Any]) -> str:
    """Convert blocks to a readable text representation for the LLM judge."""
    lines = []
    for b in blocks:
        # BlockType extends str so b.type == "code" works directly
        btype = getattr(b, "type", "")
        if btype == "heading":
            level = getattr(b, "level", 2)
            lines.append(f"[HEADING {level}] {getattr(b, 'content', '')}")
        elif btype in ("paragraph", "note", "quote"):
            lines.append(f"[{str(btype).upper()}] {getattr(b, 'content', '')}")
        elif btype == "code":
            lang = getattr(b, "language", "") or ""
            lines.append(f"[CODE {lang}]\n{getattr(b, 'content', '')}")
        elif btype in ("bullet_list", "numbered_list"):
            items = getattr(b, "items", []) or []
            items_str = "\n".join(f"- {item}" for item in items)
            lines.append(f"[LIST]\n{items_str}")
        elif btype == "table":
            headers = getattr(b, "headers", []) or []
            lines.append(f"[TABLE] Columns: {', '.join(headers)}")
        elif btype == "diagram":
            content = (getattr(b, "content", "") or "")[:100]
            lines.append(f"[DIAGRAM] {content}")
    return "\n\n".join(lines)

def validate_content_heuristics(blocks: List[Any], task_description: str) -> HeuristicResult:
    """Run cheap rule-based checks on generated chapter blocks.

    Returns HeuristicResult with passed=True if all checks pass,
    or passed=False with a reason describing the first failure found.
    No external calls — runs in microseconds.
    """
    all_text = _extract_all_text(blocks)
    word_count = len(all_text.split())
    logger.info("Heuristic check — blocks=%d word_count=%d", len(blocks), word_count)

    # 1. Minimum word count
    if word_count < MIN_WORDS:
        reason = f"Content too short: {word_count} words (minimum {MIN_WORDS})"
        logger.warning("Heuristic check 1 FAILED (word count): %s", reason)
        return HeuristicResult(passed=False, reason=reason)
    logger.info("Heuristic check 1 passed (word count: %d words)", word_count)

    # 2. Placeholder text detection
    match = _PLACEHOLDER_RE.search(all_text)
    if match:
        reason = f"Placeholder text detected: '{match.group()}'"
        logger.warning("Heuristic check 2 FAILED (placeholder): %s", reason)
        return HeuristicResult(passed=False, reason=reason)
    logger.info("Heuristic check 2 passed (no placeholder text)")

    # 3. At least one keyword from the task description appears in the content
    task_keywords = {w.lower() for w in task_description.split() if len(w) > 3}
    if task_keywords and not any(kw in all_text for kw in task_keywords):
        reason = "Content does not reference any keywords from the task description"
        logger.warning("Heuristic check 3 FAILED (topic relevance): %s", reason)
        return HeuristicResult(passed=False, reason=reason)
    logger.info("Heuristic check 3 passed (topic keywords present)")

    # 4. No exact duplicate content in prose blocks.
    # Headings are excluded — "Introduction", "Summary", "Example" legitimately
    # repeat as sub-headings across sections of the same chapter.
    # Only flag duplicates when the repeated content is substantive (> 30 chars)
    # to avoid false positives on short repeated labels like "Note:".
    prose_types = {"paragraph", "note", "quote"}
    prose_content = [
        b.content
        for b in blocks
        if getattr(b, "type", "") in prose_types
        and getattr(b, "content", None)
        and len(b.content) > 30
    ]
    if len(prose_content) != len(set(prose_content)):
        reason = "Duplicate block content detected"
        logger.warning("Heuristic check 4 FAILED (duplicates): %s", reason)
        return HeuristicResult(passed=False, reason=reason)
    logger.info("Heuristic check 4 passed (no duplicate prose blocks)")

    return HeuristicResult(passed=True, reason="")

def validate_content_with_llm(
    blocks: List[Any],
    task_description: str,
    skill: str,
    client: Any,
    model: str,
) -> ContentValidationResult:
    """Run LLM-as-judge validation on generated chapter blocks.

    Takes an already-built Instructor client to avoid circular imports with llm.py.
    Raises on client/network error — caller decides whether to treat that as a pass or fail.
    """
    logger.info(
        "LLM judge — sending %d block(s) to model=%s for review",
        len(blocks),
        model,
    )
    content_text = _blocks_to_text(blocks)

    response: ContentValidationResult = client.chat.completions.create(
        model=model,
        response_model=ContentValidationResult,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict content reviewer for an online learning platform. "
                    "Your job is to verify that a generated chapter actually teaches "
                    "the correct topic with accurate information."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Task: {task_description}\n"
                    f"Skill: {skill}\n\n"
                    "Review the chapter content below and return:\n"
                    "- valid: true only if score >= 7\n"
                    "- score: integer 1-10\n"
                    "- issues: list of specific problems (empty list if valid)\n\n"
                    "Mark invalid if any of the following are true:\n"
                    "- Content is off-topic or does not teach the stated task\n"
                    "- Examples or explanations contain factual errors or are wrong for the topic\n"
                    "- Explanations contain factual errors\n"
                    "- Content is generic filler not specific to this task\n\n"
                    f"Chapter content:\n{content_text}"
                ),
            },
        ],
        max_retries=1,
    )

    # Enforce our own threshold — LLM may mark valid=true with a low score
    response.valid = response.score >= LLM_JUDGE_PASS_SCORE
    if response.issues:
        logger.info(
            "LLM judge result — score=%d valid=%s issues=%s",
            response.score,
            response.valid,
            response.issues,
        )
    else:
        logger.info(
            "LLM judge result — score=%d valid=%s no issues",
            response.score,
            response.valid,
        )
    return response
