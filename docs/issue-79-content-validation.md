# Issue #79 - Content Validation

## Problem

The current pipeline generates chapter content from an LLM and stores it directly after passing structural checks (correct JSON shape, non-empty blocks). There is no check that the content is actually:

- **Relevant** to the chapter topic and task description
- **Factually correct** (code examples compile, explanations are accurate)
- **Substantive** (not placeholder text, not too short, not off-topic filler)

Structural validation ensures the JSON parses and the block types are valid. Content validation ensures what is _inside_ those blocks is actually useful and correct.

---

## Goal

Catch bad LLM output before it reaches the database and the user, by running two layers of validation after every chapter generation:

1. **Heuristic pre-filter** - cheap rule-based checks that catch obviously bad output instantly (no API call, no cost).
2. **LLM-as-judge** - a second LLM call that reads the chapter content and the original task description, then decides whether the content is relevant and factually sound.

If either layer fails, the system retries generation once. If it still fails, it returns a 500 error with the specific reason logged, instead of silently saving bad content.

---

## What "Heuristic" Means

A heuristic is a simple hand-written rule based on common sense - no math, no ML model, no training data. Examples:

- "If the text contains `TODO` or `insert here` - bad output"
- "If total word count across all blocks is under 80 - too short"
- "If a CODE block has no `{`, `;`, `(`, or `->` - probably not real code"

Heuristics are free to run and take microseconds. They are not smart - they only catch obvious failures. That is why they are used as a cheap pre-filter before the more expensive LLM judge call.

---

## Validation Pipeline

```
generate_chapter_content()  ->  StructuredChapterContent (blocks)
              |
  -- Layer 1: Heuristic Pre-filter -----------------------------
  |  validate_content_heuristics(blocks, task_description)
  |
  |  Checks:
  |  - Total word count across all blocks >= MIN_WORDS (80)
  |  - No placeholder strings ("TODO", "insert here", "example text",
  |    "coming soon", "fill in", "placeholder")
  |  - CODE blocks contain at least one code-like character
  |    ({, ;, (, ), ->, =>, :, def , fn , func )
  |  - At least one block mentions a keyword from the task description
  |    (basic topic relevance signal)
  |  - No block is an exact duplicate of another block
  |
  |  Result: HeuristicResult { passed: bool, reason: str }
  |
  |  If failed -> retry generation immediately (no judge call wasted)
  --------------------------------------------------------------
              |
              | (heuristics pass)
  -- Layer 2: LLM-as-Judge ------------------------------------
  |  validate_content_with_llm(blocks, task_description, skill,
  |                            provider, api_key, model)
  |
  |  Sends to the same provider the user already has configured:
  |
  |    System: "You are a strict content reviewer for an online
  |             learning platform."
  |
  |    User:   "Task: {task_description}
  |             Skill: {skill}
  |
  |             Below is the generated chapter content.
  |             Review it and return a JSON object:
  |             {
  |               valid: bool,
  |               score: int (1-10),
  |               issues: [str]   // list of specific problems, empty if valid
  |             }
  |
  |             Rules:
  |             - valid=true only if score >= 7
  |             - Mark invalid if content is off-topic
  |             - Mark invalid if code examples are wrong for the language
  |             - Mark invalid if explanations are factually incorrect
  |             - Mark invalid if content is generic filler not specific
  |               to the task
  |             - issues must list each specific problem found"
  |
  |  Response schema (Pydantic):
  |    class ContentValidationResult(BaseModel):
  |        valid: bool
  |        score: int  (1-10)
  |        issues: List[str]
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
                         -> fail -> retry

Attempt 2 (retry):
  generate -> heuristics -> judge -> pass -> save
                         -> fail -> 500 error (log reason)
```

Maximum: **2 generation attempts** per chapter request. The validation failure reason is always logged so it is visible in server logs.

---

## Implementation Plan

### New file: `services/content_validator.py`

Contains two functions:

**`validate_content_heuristics(blocks, task_description) -> HeuristicResult`**
- Pure Python, no external calls
- Returns `HeuristicResult(passed=bool, reason=str)`

**`validate_content_with_llm(blocks, task_description, skill, provider, api_key, model) -> ContentValidationResult`**
- Calls the user's already-configured provider via `_build_client`
- Uses Instructor to get a structured `ContentValidationResult` response
- Uses the same model the user configured
- `max_retries=1` on the Instructor call itself

### Changes to `services/llm.py`

`generate_chapter_content()` currently returns `StructuredChapterContent | None`.

It will be updated to:
1. Generate content (existing)
2. Run heuristics - if fail, retry once
3. Run LLM judge on the result that passed heuristics - if fail, retry once
4. Return `StructuredChapterContent` on success, `None` on final failure

The retry loop lives inside `generate_chapter_content` so the controller stays unchanged.

### New Pydantic schemas (in `services/content_validator.py`)

```python
class HeuristicResult(BaseModel):
    passed: bool
    reason: str

class ContentValidationResult(BaseModel):
    valid: bool
    score: int          # 1-10
    issues: List[str]   # empty list if valid
```

### Constants

```python
MIN_WORDS = 80                     # minimum total words across all blocks
PLACEHOLDER_STRINGS = [            # triggers instant heuristic fail
    "todo", "insert here", "example text",
    "coming soon", "fill in", "placeholder",
    "lorem ipsum", "your content here",
]
CODE_SIGNALS = [                   # at least one required in CODE blocks
    "{", ";", "()", "->", "=>", ":", "def ", "fn ", "func ", "class ",
]
LLM_JUDGE_PASS_SCORE = 7          # score >= 7 -> valid
```

---

## What Changes for the User

- Chapter generation may take slightly longer (1-3s extra for the judge call)
- Chapters that would previously save bad/irrelevant content now return an error and the user sees the existing "Failed to generate content" message
- No UI changes needed - the error handling path already exists

---

## What Does NOT Change

- Quiz validation - out of scope for this issue
- Syllabus generation - out of scope
- The retry UX in the frontend - already handles 500 errors

---

## Testing Plan

- Unit tests for all heuristic checks (each rule tested individually)
- Unit tests for `ContentValidationResult` schema validation
- Mock tests for `validate_content_with_llm` (mock the LLM call)
- Integration test in `generate_chapter_content`: verify that a chapter that fails validation triggers a retry, and that two consecutive failures return `None`
- Coverage must stay at 99%
