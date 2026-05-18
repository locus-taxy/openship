# Tech Doc — Adaptive Syllabus Generation (Issue #60)

## Problem

Right now the entire syllabus (all months, all weeks) is generated in one shot when the user
clicks Generate. A quiz is also auto-generated immediately in the background, covering all topics
at once. There is no connection between what the user actually learned and what comes next.

**Requested flow:**
> Generate 1st week syllabus → provide a quiz after week 1 → assess ability → generate next
> week's syllabus based on the result

---

## Current Flow (what exists today)

```
User triggers POST /generate-syllabus
  └─ generate_syllabus_json()  ← full syllabus (all weeks) in one LLM call
  └─ store_syllabus_tasks()    ← saves every DailyTask row
  └─ _auto_generate_quiz()     ← background thread, quiz covers ALL topics
```

**Relevant code:**
- `controllers/syllabus.py` → `generate_syllabus()`  
- `services/quiz.py` → `get_topics_for_skill()` pulls all DailyTask topics for quiz  
- `models/quiz.py` → `Quiz.skill_id` has `unique=True` (one quiz per skill, ever)

---

## Proposed Flow

```
Week 1
  POST /generate-syllabus
    └─ generate week 1 tasks only (7 days)
    └─ store DailyTask rows for week=1

  User completes week 1 tasks
    └─ frontend polls or user manually triggers
    └─ quiz unlocked for week 1 topics only

  User takes quiz (week 1)
    └─ POST /quiz/{skill_id}/submit
    └─ score recorded

Week 2
  Score passed  →  generate week 2 at same difficulty
  Score failed  →  generate week 2 with reinforcement prompt (slower pace, revisit weak areas)

  Repeat until all weeks are generated
```

---

## DB Changes Required

### 1. `Skill` model — add two columns

| Column | Type | Default | Purpose |
|---|---|---|---|
| `generated_weeks` | `int` | `0` | How many weeks have been generated so far |
| `total_weeks` | `int` | `null` | Set on first generation — total number of weeks in the plan |

`total_weeks` is derived from `days ÷ 7` (rounded up) and stored once so the frontend knows
how far along generation is without recomputing.

**No other Skill columns change.** `quiz_difficulty` stays as the user's chosen baseline.

---

### 2. `Quiz` model — support per-week quizzes

**Current constraint:** `skill_id UNIQUE` → one quiz per skill  
**New constraint:** `(skill_id, week) UNIQUE` → one quiz per skill per week

| Column | Type | Default | Purpose |
|---|---|---|---|
| `week` | `int` | — | Which week this quiz covers (1, 2, 3 …) |

The existing `difficulty`, `pass_score`, `status` columns stay unchanged.

---

### 3. No changes to `DailyTask`, `QuizQuestion`, `QuizAttempt`

`DailyTask` already has a `week` field — that's what gets used to scope per-week tasks
and quiz topics. No schema change needed there.

---

## Service / Controller Changes

### `services/llm.py` — new function

```python
def generate_week_syllabus_json(
    skill: str,
    week_number: int,
    total_weeks: int,
    hours: int,
    difficulty: str,
    previous_score: int | None,   # None on week 1, 0–100 on week 2+
    provider: str,
    api_key: str,
    model: str,
) -> list | None:
    ...
```

The `previous_score` is passed into the prompt so the LLM can adjust:
- `None` → normal week 1 intro prompt  
- `>= pass_score` → continue at same pace  
- `< pass_score` → reinforcement prompt (revisit weak areas, slower pace)

The function returns a flat list of 7 day-objects (same shape as today's per-week slice).

---

### `services/quiz.py` — scoped topic fetch

```python
def get_topics_for_week(skill_id: int, week: int) -> list[str]:
    # SELECT topic FROM daily_tasks WHERE skill_id=? AND week=? ORDER BY day
```

Replaces `get_topics_for_skill()` for the adaptive path.

---

### `services/skill.py` — update progress

```python
def increment_generated_weeks(skill_id: int) -> int:
    # UPDATE skills SET generated_weeks = generated_weeks + 1
    # Returns new value
```

---

### `controllers/syllabus.py` — changed `generate_syllabus()`

Current: generates full syllabus in one call.  
New: checks `skill.generated_weeks`:
- `== 0` → generate week 1, set `total_weeks`, increment `generated_weeks` to 1
- `> 0` → generate next week (needs quiz pass for the previous week first — see gating below)

After each week is stored: kick off quiz generation for that week in the background
(same pattern as today's `_auto_generate_quiz`, but scoped to the week's topics).

---

### `controllers/quiz.py` — trigger next week on quiz pass

In `submit_quiz()`, after `record_attempt()`:
```python
if attempt.passed:
    # kick off next week generation in background thread
    _generate_next_week_async(skill_id, current_user, attempt.score)
```

This keeps the submit response fast — the user gets their result immediately and week 2
tasks appear in the background, same as today's syllabus generation pattern.

---

## API Changes

### Changed endpoints

| Endpoint | Change |
|---|---|
| `POST /generate-syllabus` | Now generates **one week at a time**, not the full plan |
| `GET /quiz/{skill_id}` | Now requires a `week` query param: `/quiz/{skill_id}?week=1` |
| `POST /quiz/{skill_id}/submit` | Now requires `week` in the request body |
| `GET /quiz/{skill_id}/attempts` | Now requires `week` query param |

### New endpoint

```
GET /syllabi/{skill_id}/progress
```

Returns:
```json
{
  "skill_id": 1,
  "total_weeks": 12,
  "generated_weeks": 3,
  "current_week_quiz_status": "available | passed | not_generated"
}
```

The frontend uses this to show a progress bar and decide whether to show "Take Quiz" or
"Next week generating…".

---

## Gating Logic

```
Can generate next week?
  → generated_weeks > 0
  AND quiz for current week exists
  AND quiz for current week is "passed"

Week 1 can always be generated (no prior quiz needed).
```

This is enforced in `controllers/syllabus.py::generate_syllabus()` before calling the LLM.

---

## LLM Prompt Changes

Two new prompt functions in `prompts/syllabus.py`:

**`week_system_prompt(week_number, total_weeks, hours)`**  
Tells the LLM it is generating only one week, where that week sits in the overall plan, and
how many hours per day are available.

**`week_user_prompt(skill, week_number, difficulty, previous_score)`**  
- If `previous_score is None`: "Generate an introductory week 1 for {skill}"
- If `previous_score >= pass_score`: "The learner scored {score}% last week. Continue at the same pace."
- If `previous_score < pass_score`: "The learner scored {score}% last week. Slow down, reinforce fundamentals before moving on."

---

## Migration Plan

1. Add `generated_weeks` and `total_weeks` columns to `skills` — default `0` / `null`
2. Backfill existing skills: set `generated_weeks = total_weeks = ceil(days / 7)` (they already
   have all weeks generated)
3. Drop `UNIQUE(skill_id)` on `quizzes`, add `UNIQUE(skill_id, week)`, add `week` column
4. Backfill existing quizzes: set `week = 0` (meaning "covers all weeks" — legacy)

Existing users are unaffected. The new adaptive path only activates for new syllabi generated
after this change.

---

## Files to Change

| File | Change |
|---|---|
| `models/skill.py` | Add `generated_weeks`, `total_weeks` |
| `models/quiz.py` | Add `week`, change unique constraint |
| `services/llm.py` | Add `generate_week_syllabus_json()` |
| `services/quiz.py` | Add `get_topics_for_week()`, update `create_quiz()` to accept `week` |
| `services/skill.py` | Add `increment_generated_weeks()`, `get_progress()` |
| `controllers/syllabus.py` | Rewrite `generate_syllabus()` for week-by-week logic |
| `controllers/quiz.py` | Add next-week trigger in `submit_quiz()` |
| `routes/syllabus.py` | Add `GET /syllabi/{skill_id}/progress` |
| `routes/quiz.py` | Add `week` param to quiz routes |
| `prompts/syllabus.py` | Add `week_system_prompt()`, `week_user_prompt()` |
| `alembic/versions/` | New migration for schema changes |

---

## Open Questions

1. **Manual advance** — should the user be able to skip the quiz and force-generate the next
   week anyway? Or is passing the quiz always required?

2. **Quiz retry limit** — if the user fails 3 times, do we still block week 2, or generate
   it anyway with the reinforcement prompt?

3. **Week definition** — currently `days ÷ 7` rounded up. For a 90-day plan that's 13 weeks.
   Should we cap it (e.g., max 4 weeks per month) to match the existing month/week structure?

4. **Backwards compatibility** — existing syllabi have `week` set in DailyTask but `generated_weeks = 0`
   after backfill. Should the frontend show them in the old "full view" or the new week-by-week view?
