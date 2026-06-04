# Tech Doc — Adaptive Syllabus Generation (Issue #60)

> **SUPERSEDED** — This was the initial design proposal. The implemented approach uses proper ML algorithms (BKT, Ebbinghaus Forgetting Curve, Thompson Sampling Bandit) instead of the simple mastery score described here. See [`issue-60-ml-approach.md`](issue-60-ml-approach.md) for the current, accurate documentation.

## Goal

- Keep the existing **full-course quiz** exactly as it is today
- Add a **lightweight per-week quiz** after each week
- Analyse which questions the user got wrong → identify weak topics
- Use that weakness data to generate the **next week's content** with targeted reinforcement
- No external ML library needed — the intelligence lives in the LLM prompt + a simple mastery
  scoring system backed by the existing quiz infrastructure

---

## Core Idea: Topic Mastery Scoring

Every quiz question is tied to a topic (the `DailyTask.topic` for that week). When the user
answers a question wrong, the topic it belongs to gets a lower mastery score. When the next
week is generated, we pass that mastery data into the LLM prompt so it knows which areas need
more attention.

```
User takes week 1 quiz
  ├─ Q1 (Variables)     → correct   → mastery["Variables"]     = 100
  ├─ Q2 (Loops)         → wrong     → mastery["Loops"]         = 40
  ├─ Q3 (Loops)         → wrong     → mastery["Loops"]         = 20   ← two wrongs
  └─ Q4 (Functions)     → correct   → mastery["Functions"]     = 100

Generate week 2 content
  └─ prompt includes: "Weak areas from last week: Loops (20% mastery).
                       Reinforce these before introducing new topics."
```

This is simple, explainable, and leverages the LLM we already have — no external ML model
or training pipeline needed.

---

## Adaptive Learning Technique: Mastery-Based LLM Prompting

### Why not classic ML (KNN, SVM, Decision Trees)?
- We have too little data per user to train a meaningful model
- We already have an LLM that can reason about pedagogy
- Passing structured performance data into the prompt achieves the same adaptation with zero
  training overhead

### Why not Deep Knowledge Tracing (DKT) or IRT?
- Requires significant historical data across many users to calibrate
- Overkill for the per-user adaptation we need here
- Can be added later as a v2 if we accumulate enough data

### What we do instead: **Prompt-Augmented Mastery Tracking**
A lightweight version of Bayesian Knowledge Tracing implemented as a scoring formula:

```
mastery_score = (correct_answers / total_answers) * 100

Where each question has a weight:
  - First attempt at a topic: full weight
  - Repeated wrong answers on same topic: score decays faster (×0.7 per extra wrong)
```

Scores are stored in a new `TopicMastery` table and fed directly into the LLM generation prompt.

---

## New Data Model: `TopicMastery`

```python
class TopicMastery(SQLModel, table=True):
    __tablename__ = "topic_masteries"

    id: Optional[int]         # PK
    skill_id: int             # FK → skills.id CASCADE
    user_id: int              # FK → users.id CASCADE
    topic: str                # exact value of DailyTask.topic
    week: int                 # which week this topic belongs to
    correct: int = 0          # total correct answers on questions mapped to this topic
    incorrect: int = 0        # total wrong answers
    mastery_score: float = 0  # computed: (correct / (correct + incorrect)) * 100
```

**Unique constraint:** `(skill_id, user_id, topic)`

This table is updated every time a per-week quiz is submitted.

---

## `QuizQuestion` — add `topic` column

The current `QuizQuestion` has no link back to the topic it tests. We need to add:

```python
topic: Optional[str]  # copied from DailyTask.topic at quiz generation time
```

When `_auto_generate_quiz_for_week()` creates questions, it maps each question to the topic
from the DailyTask that generated it. This is what lets us update `TopicMastery` correctly
after submission.

---

## `Quiz` model — add `week` column

```python
week: int  # 0 = full-course quiz (existing behaviour), 1..N = per-week quiz
```

**Unique constraint changes from** `UNIQUE(skill_id)` **to** `UNIQUE(skill_id, week)`.

The full-course quiz gets `week = 0` (both existing and new quizzes). Per-week quizzes get
`week = 1`, `week = 2`, etc.

---

## `Skill` model — track generation progress

```python
generated_weeks: int = 0   # how many weeks have been generated
total_weeks: int = 0        # ceil(days / 7), set on first generation
```

---

## Full Flow

```
WEEK 1
───────
POST /generate-syllabus
  └─ first call → generate week 1 tasks only (7 DailyTask rows, week=1)
  └─ set skill.total_weeks = ceil(days/7), skill.generated_weeks = 1
  └─ background: auto-generate per-week quiz for week 1
                 (5 questions, topics from week 1 tasks, quiz.week = 1)

User studies week 1, marks tasks complete

Frontend shows "Take Week 1 Quiz" button

POST /quiz/{skill_id}/submit  (week=1 in body)
  └─ score calculated
  └─ TopicMastery updated per question:
       correct answer   → topic.correct++, recalculate mastery_score
       wrong answer     → topic.incorrect++, apply decay, recalculate mastery_score
  └─ background: generate week 2 content
       LLM prompt includes weak topics (mastery_score < 60)


WEEK 2
───────
POST /generate-syllabus  (called automatically from background, or user triggers)
  └─ fetch weak_topics = TopicMastery where skill_id=X, mastery_score < 60
  └─ call generate_week_syllabus_json(week=2, weak_topics=weak_topics)
  └─ LLM prompt: "Week 2 of {skill}. Weak areas from week 1: {weak_topics}.
                  Start week 2 by briefly revisiting these before new content."
  └─ skill.generated_weeks = 2
  └─ background: auto-generate per-week quiz for week 2

... repeat until skill.generated_weeks == skill.total_weeks


FULL COURSE (unchanged)
────────────────────────
POST /quiz/{skill_id}/generate  (existing endpoint, untouched)
  └─ generates full-course quiz as today (all topics, quiz.week = 0)
  └─ no adaptive logic, no TopicMastery involvement
```

---

## Gating Logic

```
Can generate week 1?
  → always yes (no prior quiz needed)

Can generate week N (N > 1)?
  → quiz for week N-1 exists
  AND at least one attempt has been submitted for that quiz

The user does NOT need to pass — just submit.
The weak topics from the attempt drive the adaptation.
If weak topics changed since the last attempt → regenerate week N content.
If no new weak topics since last attempt → keep already-generated content.
```

The background thread triggered by `submit_quiz()` owns this logic — not the generate
endpoint itself.

---

## Mastery Score Formula

```python
def compute_mastery(correct: int, incorrect: int) -> float:
    total = correct + incorrect
    if total == 0:
        return 0.0
    base = (correct / total) * 100
    # Penalise repeated wrong answers more aggressively
    decay = 0.7 ** max(0, incorrect - 1)
    return round(base * decay, 1)
```

| correct | incorrect | mastery |
|---------|-----------|---------|
| 2 | 0 | 100.0 |
| 1 | 1 | 50.0 |
| 1 | 2 | 35.0 |
| 0 | 2 | 0.0 |

Topics with `mastery_score < 60` are flagged as **weak** and passed to the next week's prompt.

---

## LLM Prompt Strategy

### New function: `prompts/syllabus.py` → `week_user_prompt()`

```python
def week_user_prompt(
    skill: str,
    week_number: int,
    hours: int,
    weak_topics: list[str],   # topics with mastery < 60
) -> str:
    if not weak_topics:
        return f"Generate week {week_number} content for {skill}. ..."
    topics_str = ", ".join(weak_topics)
    return (
        f"Generate week {week_number} content for {skill}. "
        f"The learner struggled with: {topics_str} in the previous week. "
        f"Begin the week with short reinforcement tasks for these topics "
        f"before introducing new material. Keep it to {hours} hour(s) per day."
    )
```

The LLM does the pedagogy — we just tell it the facts.

---

## Per-Week Quiz: Size and Scope

| Course length | Full-course quiz (today) | Per-week quiz (new) |
|---|---|---|
| ≤ 30 days | 10 questions | 5 questions |
| ≤ 60 days | 12 questions | 5 questions |
| 90+ days | 15 questions | 5 questions |

Per-week quiz is always 5 questions — short enough that users actually take it.
Each question is tagged with the topic it tests (`QuizQuestion.topic`).

---

## Service Changes

### `services/quiz.py`

```python
# New
def get_topics_for_week(skill_id: int, week: int) -> list[str]: ...
def create_week_quiz(skill_id: int, week: int, difficulty: str, questions: list) -> Quiz: ...
def update_topic_mastery(skill_id: int, user_id: int, questions: list, answers: dict): ...
def get_weak_topics(skill_id: int, user_id: int, threshold: float = 60.0) -> list[str]: ...

# Changed
def create_quiz(...)  → accepts week: int = 0 (default keeps existing behaviour)
```

### `services/skill.py`

```python
# New
def increment_generated_weeks(skill_id: int) -> int: ...
def get_generation_progress(skill_id: int) -> dict: ...
```

---

## API Changes

### New endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/syllabi/{skill_id}/progress` | Returns `generated_weeks`, `total_weeks`, current week quiz status |

### Changed endpoints

| Endpoint | Change |
|---|---|
| `POST /generate-syllabus` | Generates one week at a time instead of full plan |
| `GET /quiz/{skill_id}` | Add `week` query param (default `0` = full course) |
| `POST /quiz/{skill_id}/submit` | Add `week` in request body; triggers mastery update + next week generation |

### Unchanged endpoints

`POST /quiz/{skill_id}/generate` — full-course quiz generation, completely untouched.

---

## Files to Change

| File | What changes |
|---|---|
| `models/skill.py` | Add `generated_weeks`, `total_weeks` |
| `models/quiz.py` | Add `week`, change unique constraint |
| `models/quiz_question.py` | Add `topic` |
| `models/topic_mastery.py` | **New file** |
| `services/llm.py` | Add `generate_week_syllabus_json()` |
| `services/quiz.py` | Add week-scoped functions + mastery update |
| `services/skill.py` | Add progress tracking functions |
| `controllers/syllabus.py` | Rewrite `generate_syllabus()` for week-by-week |
| `controllers/quiz.py` | Add mastery update + next-week trigger in `submit_quiz()` |
| `routes/syllabus.py` | Add `/progress` endpoint |
| `routes/quiz.py` | Add `week` param |
| `prompts/syllabus.py` | Add `week_system_prompt()`, `week_user_prompt()` |
| `alembic/versions/` | Migration for all schema changes |

---

## Migration Plan

1. Add `generated_weeks = 0`, `total_weeks = 0` to `skills`
2. Backfill existing skills: `total_weeks = ceil(days/7)`, `generated_weeks = total_weeks`
   (they already have all weeks generated — mark them as complete)
3. Add `week INT DEFAULT 0` to `quizzes`
4. Drop `UNIQUE(skill_id)` on `quizzes`, add `UNIQUE(skill_id, week)`
5. Add `topic TEXT NULL` to `quiz_questions`
6. Create `topic_masteries` table
7. Existing data is fully backwards compatible — full-course quizzes get `week = 0`

---

## Decisions

1. **Quiz is mandatory before next week is generated.**
   The next week's content will not be generated until the user submits the current week's
   quiz. This ensures the mastery data always exists before the LLM prompt is built.

2. **Multiple quiz attempts — regenerate only on new weak topics.**
   If the user retakes a week's quiz and fails again, we compare the new weak topics against
   the ones from the previous attempt. Only if there are **new** weak topics do we regenerate
   the next week's content with the updated prompt. If the same topics fail again with no new
   additions, we do not regenerate — the already-generated week 2 content stands.

   ```
   Attempt 1 weak topics: [Loops]           → generate week 2 with Loops reinforcement
   Attempt 2 weak topics: [Loops, Functions] → Functions is new → regenerate week 2
   Attempt 3 weak topics: [Loops, Functions] → no new topics   → do nothing
   ```

3. **Week definition — already resolved by the existing data model.**
   A "week" is the set of `DailyTask` rows sharing the same `week` value (e.g. all tasks
   where `week = 1`). For a 90-day plan this means 13 weeks. The per-week quiz fires after
   all tasks in that `week` bucket exist — no calendar dependency.

4. **Next week generation is fully automatic.**
   As soon as the user submits the week quiz, a background thread fires to generate the
   next week's content (same pattern as today's `_auto_generate_quiz` thread). The user
   gets their quiz result immediately; the next week's tasks appear in the background.
