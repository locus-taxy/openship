# Issue #79 - Content Validation

## Problem

The current pipeline generates chapter content from an LLM and stores it directly after passing structural checks (correct JSON shape, non-empty blocks). There is no check that the content is actually:

- **Relevant** to the chapter topic and task description
- **Factually correct** (explanations are accurate for the subject)
- **Substantive** (not placeholder text, not too short, not off-topic filler)

Structural validation ensures the JSON parses and the block types are valid. Content validation ensures what is _inside_ those blocks is actually useful and correct.

---

## Goal

Catch bad LLM output before it reaches the database and the user, by running two layers of validation after every chapter generation:

1. **Heuristic pre-filter** — cheap rule-based checks that catch obviously bad output instantly (no API call, no cost).
2. **LLM-as-judge** — a second LLM call that reads the chapter content and the original task description, then decides whether the content is relevant and accurate.

If either layer fails, the system retries generation once. If it still fails, it returns a 500 error with the specific reason logged, instead of silently saving bad content.

---

## What "Heuristic" Means

A heuristic is a simple hand-written rule based on common sense — no math, no ML model, no training data. Examples:

- "If the text contains `todo:` or `lorem ipsum` — bad output"
- "If total word count across all blocks is under 80 — too short"
- "If the same paragraph appears twice — the LLM got stuck in a loop"

Heuristics are free to run and take microseconds. They are not smart — they only catch obvious failures. That is why they are used as a cheap pre-filter before the more expensive LLM judge call.

---

## Validation Pipeline

```
generate_chapter_content()  ->  StructuredChapterContent (blocks)
              |
  -- Layer 1: Heuristic Pre-filter -----------------------------
  |  validate_content_heuristics(blocks, task_description)
  |
  |  Checks (in order, stops at first failure):
  |  1. Total word count across all blocks >= MIN_WORDS (80)
  |  2. No placeholder strings detected via regex:
  |       "todo:" / "insert here" / "lorem ipsum" /
  |       "your content here" / "add your code here" /
  |       "write your code here" / "fill in the blank" /
  |       "your code goes here"
  |     Note: "todo" alone is NOT flagged — only "todo:" with a colon,
  |     so "Build a Todo App" or "todo list" are legitimate content.
  |  3. At least min(2, n_keywords) distinct keywords from the task
  |     description appear in the content using whole-word matching
  |     (regex word boundaries — "data" does not satisfy "database").
  |     Stopwords and pedagogical framing words ("learn", "intro",
  |     "introduction", "basics", "overview", "guide", etc.) are
  |     excluded from keyword extraction so they do not dilute the
  |     topic signal.
  |  4. No prose block (paragraph, note, quote, >30 chars) is an
  |     exact duplicate of another prose block
  |     (headings excluded — "Introduction" legitimately repeats)
  |
  |  Result: HeuristicResult { passed: bool, reason: str }
  |
  |  If failed -> retry generation immediately (no judge call wasted)
  --------------------------------------------------------------
              |
              | (heuristics pass)
  -- Layer 2: LLM-as-Judge ------------------------------------
  |  validate_content_with_llm(blocks, task_description, skill,
  |                            client, model)
  |
  |  client is a pre-built Instructor client (passed in from the
  |  caller to avoid circular imports). Uses whatever model the
  |  user already has configured.
  |
  |    System: "You are a strict content reviewer for an online
  |             learning platform. Your job is to verify that a
  |             generated chapter actually teaches the correct
  |             topic with accurate information."
  |
  |    User:   "Task: {task_description}
  |             Skill: {skill}
  |
  |             Review the chapter content below and return:
  |             - valid: true only if score >= 7
  |             - score: integer 1-10
  |             - issues: list of specific problems (empty if valid)
  |
  |             Mark invalid if any of the following are true:
  |             - Content is off-topic or does not teach the stated task
  |             - Examples or explanations contain factual errors or
  |               are wrong for the topic
  |             - Content is generic filler not specific to this task"
  |
  |  Response schema (Pydantic):
  |    class ContentValidationResult(BaseModel):
  |        valid: bool
  |        score: int   # clamped 1-10 by field_validator
  |        issues: List[str]
  |
  |  Score is also clamped server-side (1–10) regardless of what
  |  the LLM returns. valid is re-derived from score >= 7 after the
  |  response arrives, so the LLM cannot override the threshold.
  |
  |  If valid=false -> retry generation once
  --------------------------------------------------------------
              |
              | (judge passes)
  add_blocks_to_db()  ->  saved
```

---

## Retry Logic

```
Attempt 1:
  generate -> heuristics -> judge -> pass -> save
           -> fail (generate error)  -> retry
           -> pass -> judge fail     -> retry

Attempt 2 (retry):
  generate -> heuristics -> judge -> pass -> save
                                   -> fail -> 500 error (log reason)
```

Maximum: **2 generation attempts** per chapter request. The validation failure reason is always logged so it is visible in server logs.

---

## Constants

```python
MIN_WORDS = 80          # minimum total words across all blocks
LLM_JUDGE_PASS_SCORE = 7   # score >= 7 -> valid
```

Placeholder detection uses a compiled regex (`_PLACEHOLDER_RE`) rather than a plain list so that word-boundary rules can be applied per-pattern (e.g. `\btodo\s*:` avoids false positives on "Todo App").

---

## Implementation Plan

### New file: `services/content_validator.py`

Contains two functions:

**`validate_content_heuristics(blocks, task_description) -> HeuristicResult`**
- Pure Python, no external calls
- Returns `HeuristicResult(passed=bool, reason=str)`

**`validate_content_with_llm(blocks, task_description, skill, client, model) -> ContentValidationResult`**
- Takes an already-built Instructor client (passed in from the caller to avoid circular imports)
- Uses Instructor to get a structured `ContentValidationResult` response
- Uses the same model the user configured
- `max_retries=1` on the Instructor call itself

### Changes to `services/llm.py`

`generate_chapter_content()` currently returns `StructuredChapterContent | None`.

It will be updated to:
1. Generate content (existing)
2. Run heuristics — if fail, retry once
3. Run LLM judge on the result that passed heuristics — if fail, retry once
4. Return `StructuredChapterContent` on success, `None` on final failure

The retry loop lives inside `generate_chapter_content` so the controller stays unchanged.

### New Pydantic schemas (in `services/content_validator.py`)

```python
class HeuristicResult(BaseModel):
    passed: bool
    reason: str

class ContentValidationResult(BaseModel):
    valid: bool
    score: int          # clamped 1-10 by field_validator
    issues: List[str]   # empty list if valid
```

---

## Domain Compatibility

The validation layer works for **any course topic** — programming, cooking, history, design, etc.

- Heuristic checks are text-based only; they do not require code blocks or code-like syntax.
- The LLM judge prompt is phrased in terms of topic accuracy ("wrong for the topic"), not language correctness ("wrong for the language").
- The duplicate-block check only looks at prose blocks, so a chapter with no code at all passes equally well.

---

## What Changes for the User

- Chapter generation may take slightly longer (1–3 s extra for the judge call).
- Chapters that would previously save bad/irrelevant content now return an error and the user sees the existing "Failed to generate content" message.
- No UI changes needed — the error handling path already existed.

---

## What Does NOT Change

- Quiz validation — out of scope for this issue.
- Syllabus generation — out of scope.
- The retry UX in the frontend — already handles 500 errors.

---

## Testing

- Unit tests for each heuristic check individually (`tests/test_content_validator.py`)
- Unit tests for `ContentValidationResult` score clamping and `valid` re-derivation
- Mock tests for `validate_content_with_llm`
- Integration tests for the retry loop in `generate_chapter_content` (`tests/test_llm_service_extended.py`)
- Coverage enforced at 99% via pre-commit hook
