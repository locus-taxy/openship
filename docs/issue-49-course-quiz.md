# Issue #49 — Course Quiz

## Overview

Add an AI-generated quiz at the end of every course. The quiz difficulty is set at
enrollment time (beginner / intermediate / advanced). A course cannot be marked
fully complete until the user passes the quiz.

---

## Requirements Summary

| # | Requirement | Status |
|---|-------------|--------|
| 1 | Difficulty collected during enrollment (beginner / intermediate / advanced) | ✅ |
| 2 | Quiz is auto-generated in the background when the syllabus is created | ✅ |
| 3 | AI generates questions based on the actual syllabus topics the user studied | ✅ |
| 4 | Quiz is multiple-choice (4 options per question) | ✅ |
| 5 | Pass threshold varies by difficulty (see below) | ✅ |
| 6 | Unlimited retries; each attempt is recorded; questions shuffled on retry | ✅ |
| 7 | Course is only marked **complete** after passing the quiz | ✅ |
| 8 | Quiz answers are never exposed in GET responses — only revealed after submission | ✅ |
| 9 | Final Quiz nav item only becomes visible after all chapters are complete | ✅ |

---

## Data Model

### 1. Alter `skills` table — add `quiz_difficulty`

**Existing columns**

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `id` | Integer PK | — | Auto-increment |
| `user_id` | String | — | FK to users (stored as str) |
| `email` | String | — | Indexed |
| `skill` | String | — | Skill name |
| `days` | Integer | `90` | Total plan duration |
| `hours` | Integer | `1` | Hours per day |
| `stop_sending` | Boolean | `false` | Soft-deactivate flag |
| `share_enabled` | Boolean | `false` | Public share toggle |
| `created_at` | DateTime | `now()` | Server default |
| `updated_at` | DateTime | `now()` | Auto-updated on change |

**New column**

| Column | Type | Default | Allowed values |
|--------|------|---------|----------------|
| `quiz_difficulty` | VARCHAR(20) | `"beginner"` | `"beginner"` · `"intermediate"` · `"advanced"` |

```sql
ALTER TABLE skills ADD COLUMN quiz_difficulty VARCHAR(20) DEFAULT 'beginner';
```

```python
# models/skill.py  (add field)
quiz_difficulty: str = Field(default="beginner")
```

### 2. New table — `quizzes`

One row per skill. Created automatically when the syllabus is generated.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `skill_id` | Integer FK → skills.id CASCADE | UNIQUE (one quiz per course) |
| `difficulty` | VARCHAR(20) | copied from skill at generation time |
| `pass_score` | Integer | percentage required to pass (60/70/80) |
| `status` | VARCHAR(20) | `available` · `passed` |
| `created_at` | DateTime | |
| `updated_at` | DateTime | |

```python
# models/quiz.py
class Quiz(SQLModel, table=True):
    __tablename__ = "quizzes"
    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: int = Field(foreign_key="skills.id", unique=True, index=True)
    difficulty: str = Field(default="beginner")
    pass_score: int  # 60 / 70 / 80
    status: str = Field(default="available")  # available | passed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### 3. New table — `quiz_questions`

One row per question. Generated in bulk when quiz is created.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `quiz_id` | Integer FK → quizzes.id CASCADE | indexed |
| `position` | Integer | ordering (1-based) |
| `question` | Text | question text |
| `option_a` | Text | |
| `option_b` | Text | |
| `option_c` | Text | |
| `option_d` | Text | |
| `correct_option` | VARCHAR(1) | `A` · `B` · `C` · `D` |
| `explanation` | Text | shown after submission |

```python
# models/quiz_question.py
class QuizQuestion(SQLModel, table=True):
    __tablename__ = "quiz_questions"
    id: Optional[int] = Field(default=None, primary_key=True)
    quiz_id: int = Field(foreign_key="quizzes.id", index=True)
    position: int
    question: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str     # never sent to frontend until after submission
    explanation: str
```

### 4. New table — `quiz_attempts`

One row per submission. Retries create new rows.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `quiz_id` | Integer FK → quizzes.id CASCADE | indexed |
| `user_id` | Integer FK → users.id CASCADE | indexed |
| `answers` | JSON | `{"1": "B", "2": "A", ...}` keyed by question id |
| `score` | Integer | percentage correct |
| `passed` | Boolean | score >= pass_score |
| `created_at` | DateTime | |

```python
# models/quiz_attempt.py
class QuizAttempt(SQLModel, table=True):
    __tablename__ = "quiz_attempts"
    id: Optional[int] = Field(default=None, primary_key=True)
    quiz_id: int = Field(foreign_key="quizzes.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    answers: dict = Field(default_factory=dict, sa_column=Column(JSON))
    score: int = 0
    passed: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

---

## Pass Score by Difficulty

| Difficulty | Pass Score |
|------------|-----------|
| `beginner` | 60% |
| `intermediate` | 70% |
| `advanced` | 80% |

---

## Number of Questions by Course Length

| Days | Questions |
|------|-----------|
| ≤ 30 | 10 |
| ≤ 60 | 12 |
| > 60 | 15 |

---

## API Routes

### Quiz routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/quiz/{skill_id}` | Required | Get quiz questions (no correct answers in response); returns 404 while still generating — poll with 2 s interval |
| `POST` | `/quiz/{skill_id}/submit` | Required | Submit answers; returns score + per-question result |
| `GET` | `/quiz/{skill_id}/attempts` | Required | List all past attempts for this quiz |
| `POST` | `/quiz/{skill_id}/generate` | Required | Manually trigger quiz generation (fallback only — normally auto-generated) |

### Modified routes

| Method | Path | Change |
|--------|------|--------|
| `POST` | `/subscribe` | Accepts `quiz_difficulty` field (default `"beginner"`) |
| `POST` | `/generate-syllabus` | Now also fires background thread to auto-generate quiz after saving syllabus |
| `GET` | `/syllabi` | Response includes `quiz_status` per course |
| `GET` | `/syllabi/search` | Response includes `quiz_status` per course (same as list) |
| `GET` | `/syllabi/{skill_id}` | Response includes `quiz_status` and `quiz_difficulty` |
| `DELETE` | `/syllabi/{skill_id}` | New — hard deletes course + all chapters, progress, quiz, attempts (CASCADE) |

---

## Auto-Generation Flow

Quiz generation is **automatic** — no user action required.

```
POST /generate-syllabus
  └─ store_syllabus_tasks()       ← saves months/weeks/chapters to DB
  └─ threading.Thread(daemon=True)
       └─ _auto_generate_quiz()
            ├─ guard: quiz already exists? → return early
            ├─ fetch all topic strings for skill
            ├─ compute num_questions from topic count
            ├─ call LLM generate_quiz()
            └─ quiz_service.create_quiz()  ← inserts Quiz + QuizQuestion rows
```

The background thread runs concurrently — `POST /generate-syllabus` returns
immediately to the client. The frontend polls `GET /quiz/{skill_id}` (every 2 s,
up to 20 attempts = 40 s) until the quiz is available.

`POST /quiz/{skill_id}/generate` still exists as a manual fallback if the
background thread failed, but it is not surfaced in the UI.

---

## Request / Response Schemas

### `POST /subscribe` (modified)

```python
# schemas/skill.py
class SubscribeRequest(BaseModel):
    skill: str
    days: int = Field(90, gt=0)
    hours: int = Field(1, gt=0)
    quiz_difficulty: Literal["beginner", "intermediate", "advanced"] = "beginner"
```

### `GET /quiz/{skill_id}` — response

```python
class QuizQuestionOut(BaseModel):
    id: int
    position: int
    question: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    # correct_option intentionally omitted

class QuizOut(BaseModel):
    quiz_id: int
    skill_id: int
    difficulty: str
    pass_score: int
    status: str          # "available" | "passed"
    questions: List[QuizQuestionOut]
    best_score: Optional[int]   # from past attempts; null if no attempts yet
    attempt_count: int
```

Returns `404` while the background quiz generation is still in progress — clients
should poll.

### `POST /quiz/{skill_id}/submit` — request + response

```python
class QuizSubmitRequest(BaseModel):
    answers: Dict[int, str]   # { question_id: "A" | "B" | "C" | "D" }

class QuizQuestionResult(BaseModel):
    question_id: int
    selected: str
    correct: str
    is_correct: bool
    explanation: str

class QuizSubmitResponse(BaseModel):
    attempt_id: int
    score: int               # percentage
    passed: bool
    pass_score: int
    results: List[QuizQuestionResult]
```

### `GET /quiz/{skill_id}/attempts` — response

```python
class QuizAttemptOut(BaseModel):
    attempt_id: int
    score: int
    passed: bool
    created_at: str

class QuizAttemptsResponse(BaseModel):
    quiz_id: int
    skill_id: int
    pass_score: int
    attempts: List[QuizAttemptOut]
```

---

## LLM Generation

### Pydantic output model

```python
# services/llm.py

class QuizOption(BaseModel):
    label: str   # "A", "B", "C", "D"
    text: str

class GeneratedQuestion(BaseModel):
    question: str
    options: List[QuizOption]    # exactly 4
    correct_option: str          # "A", "B", "C", or "D"
    explanation: str             # 1-2 sentence explanation shown after submission

class GeneratedQuiz(BaseModel):
    questions: List[GeneratedQuestion]
```

### `generate_quiz()` function signature

```python
def generate_quiz(
    skill: str,
    topics: List[str],       # list of all daily_task.topic values for this skill
    difficulty: str,
    num_questions: int,
    provider: str,
    api_key: str,
    model: str,
) -> GeneratedQuiz:
```

---

## Service Layer — `services/quiz.py`

```python
def get_quiz_by_skill(skill_id: int) -> Quiz | None
    # returns existing quiz or None if not yet generated

def get_topics_for_skill(skill_id: int) -> List[str]
    # returns all daily_task.topic strings for the skill (used as LLM input)

def get_num_questions(num_topics: int) -> int
    # maps topic count to question count (10 / 12 / 15)

def create_quiz(skill_id: int, difficulty: str, questions: List[GeneratedQuestion]) -> Quiz
    # inserts Quiz + QuizQuestion rows in a single transaction
    # raises IntegrityError (→ 409) if quiz already exists

def get_quiz_with_questions(skill_id: int) -> QuizOut | None
    # used for GET /quiz/{skill_id}; strips correct_option, attaches best_score + attempt_count

def submit_quiz(skill_id: int, answers: Dict[int, str], user_id: int) -> QuizSubmitResponse
    # scores the attempt, updates quiz.status to "passed" if score >= pass_score, commits
```

---

## Controller Layer — `controllers/quiz.py`

```python
def generate_quiz_for_skill(skill_id: int, current_user: User):
    # 1. Verify skill ownership
    # 2. Guard: quiz already exists → raise HTTP 409
    # 3. Fetch topics; raise 404 if none
    # 4. Get user LLM settings; raise 400 if not configured
    # 5. Call services.llm.generate_quiz()
    # 6. Call services.quiz.create_quiz()
    # Note: does NOT check whether all chapters are complete
    #       (chapter-completion gate is enforced in the UI, not the API)

def get_quiz(skill_id: int, current_user: User):
    # 1. Verify ownership
    # 2. Return quiz (404 if not generated yet — client polls)

def submit_quiz(skill_id: int, payload: QuizSubmitRequest, current_user: User):
    # 1. Verify ownership
    # 2. Fetch quiz (404 if missing)
    # 3. Score answers, record attempt

def get_attempts(skill_id: int, current_user: User):
    # 1. Verify ownership
    # 2. Return all past attempts ordered by created_at desc
```

---

## Progress & Completion Model

The quiz counts as one extra step in course progress:

```
totalSteps     = total_tasks + 1
completedSteps = completed_tasks + (quiz_status === "passed" ? 1 : 0)
progress%      = round(completedSteps / totalSteps * 100)
```

A course is **Completed** only when:
- All chapter tasks are marked complete, **and**
- The final quiz is passed

A course with all chapters done but quiz not passed shows **~95–99%** progress
(depending on task count), never 100%.

This logic is applied consistently in:
- `ui/src/app/plugins/syllabi/detail.tsx` — course detail progress bar
- `ui/src/app/plugins/syllabi/index.tsx` — courses list card progress + badge
- `ui/src/app/plugins/analytics/index.tsx` — dashboard ring + getStatus()

---

## Frontend Implementation

### Enrollment form (`enroll/index.tsx`)

- Added **Quiz Difficulty** picker (Beginner / Intermediate / Advanced), default Beginner
- Added **custom duration input** alongside the 30 / 60 / 90 day pills (for testing any duration)
- `quiz_difficulty` sent in the POST `/subscribe` payload
- Form card is hidden entirely when no LLM API key is configured

### Course detail (`syllabi/detail.tsx`)

- **Final Quiz nav item** is only rendered after `completedCount === totalCount && totalCount > 0` — hidden until all chapters are done
- Clicking "Final Quiz" in the nav sets `activeView = "quiz"` — the quiz renders in the **same right panel** as chapter content (no separate page/route)
- Progress formula uses `totalSteps = allTasks.length + 1`; passing the quiz moves progress from ~99% → 100%

### Quiz panel (`syllabi/quiz.tsx`) — `QuizPanel` component

Embedded in `detail.tsx`; not a separate route. States:

| State | UI |
|-------|----|
| `loading` | Spinner — polls `GET /quiz/{skill_id}` every 2 s (up to 20 attempts) until quiz is ready |
| `ready` | Stats grid (questions / pass score / attempts), best-score bar (after first attempt), Start / Retake button |
| `taking` | Scrollable question list with A–D option buttons, sticky progress header, Submit button |
| `submitted` | Sticky pass/fail score card with Quiz Overview + Retry buttons; per-question breakdown with correct answers and explanations |

**Retry** shuffles questions client-side: `[...quiz.questions].sort(() => Math.random() - 0.5)`.

**"Quiz Overview"** button in the submitted view calls `loadQuiz()` which resets to the `ready` state (does not navigate away from the course).

### Courses list (`syllabi/index.tsx`)

- `Syllabus` interface includes `quiz_status`
- `isCompleted` requires both all tasks done and `quiz_status === "passed"`
- Progress bar and percentage reflect quiz step
- Stats row (Completed / In Progress counts) use the same logic

### Dashboard (`analytics/index.tsx`)

- `getStatus()` requires `quiz_status === "passed"` for "completed"
- Per-course ring % includes quiz step
- Overall completion ring and "X of Y steps done" text include quiz steps across all courses

---

## Alembic Migrations

Three migration files (in linear chain order):

### 1. `add_quiz_difficulty_to_skills.py`
```python
op.add_column("skills", sa.Column("quiz_difficulty", sa.String(20), nullable=False, server_default="beginner"))
```

### 2. `create_quizzes_and_quiz_questions.py`
```python
op.create_table("quizzes", ...)
op.create_table("quiz_questions", ...)
```

### 3. `create_quiz_attempts.py`
```python
op.create_table("quiz_attempts", ...)
```

---

## Files Created / Modified

### New files
| File | Purpose |
|------|---------|
| `schemas/quiz.py` | All quiz request/response schemas |
| `models/quiz.py` | Quiz table |
| `models/quiz_question.py` | QuizQuestion table |
| `models/quiz_attempt.py` | QuizAttempt table |
| `services/quiz.py` | Quiz business logic |
| `controllers/quiz.py` | Quiz request handlers |
| `routes/quiz.py` | FastAPI router |
| `ui/src/app/plugins/syllabi/quiz.tsx` | `QuizPanel` component (embedded in detail, not a page) |
| `alembic/versions/*_add_quiz_difficulty_to_skills.py` | Migration |
| `alembic/versions/*_create_quizzes_and_questions.py` | Migration |
| `alembic/versions/*_create_quiz_attempts.py` | Migration |

### Modified files
| File | Change |
|------|--------|
| `models/skill.py` | Added `quiz_difficulty` field |
| `models/__init__.py` | Exports `Quiz`, `QuizQuestion`, `QuizAttempt` |
| `schemas/skill.py` | `quiz_difficulty: Literal[...]` added to `SubscribeRequest` |
| `services/skill.py` | `get_syllabus_detail()`, `get_all_syllabi()`, and `search_syllabi()` all LEFT JOIN quizzes and return `quiz_status` / `quiz_difficulty` |
| `services/llm.py` | Added `GeneratedQuestion`, `GeneratedQuiz`, `generate_quiz()` |
| `controllers/subscription.py` | Passes `quiz_difficulty` through to `create_skill()` |
| `controllers/syllabus.py` | Added `_auto_generate_quiz()` background function; fires daemon thread after `store_syllabus_tasks()`; added `delete_syllabus()` |
| `routes/syllabus.py` | Added `DELETE /syllabi/{skill_id}` |
| `routes/__init__.py` | Registers quiz router |
| `ui/src/app/plugins/enroll/index.tsx` | Difficulty picker, custom duration input, hide form when no API key |
| `ui/src/app/plugins/syllabi/detail.tsx` | Final Quiz nav gate, `activeView` state, `QuizPanel` in right panel, updated progress formula |
| `ui/src/app/plugins/syllabi/index.tsx` | `quiz_status` in interface, updated progress/completion logic |
| `ui/src/app/plugins/analytics/index.tsx` | Updated `getStatus()`, per-course ring %, overall ring % |

---

## Edge Cases

| Case | Handling |
|------|----------|
| Quiz not ready yet when user opens Final Quiz | Frontend polls `GET /quiz/{skill_id}` every 2 s (spinner shown); API returns 404 until ready |
| Background quiz generation fails | Logged server-side; user can trigger `POST /quiz/{skill_id}/generate` manually as fallback |
| Generate quiz twice | HTTP 409 "Quiz already exists" |
| Submit with missing question IDs | HTTP 422 validation error |
| LLM fails during quiz generation | Returns `None`; background thread logs warning and exits without saving partial data |
| User retries after passing | Allowed; new attempt recorded; `quiz.status` stays `"passed"` |
| Delete course | Hard delete via `DELETE /syllabi/{skill_id}`; CASCADE removes quiz, questions, attempts, tasks |

---

## Verification Checklist

- [x] `POST /subscribe` with `quiz_difficulty: "advanced"` → skill row has `quiz_difficulty = advanced`
- [x] `POST /generate-syllabus` → quiz auto-generated in background thread
- [x] `GET /quiz/{skill_id}` while generating → 404 (client polls)
- [x] `GET /quiz/{skill_id}` after generation → questions returned, no `correct_option` field
- [x] `POST /quiz/{skill_id}/submit` correct answers → score + explanations
- [x] Failing attempt → `quiz.status` stays `available`, retry works
- [x] Passing attempt → `quiz.status` = `passed`, progress = 100%
- [x] `POST /quiz/{skill_id}/generate` second time → 409
- [x] `GET /public/syllabi/{skill_id}` → no quiz data leaked
- [x] Courses page: all chapters done but quiz not passed → "In Progress" badge, < 100%
- [x] Courses page: all chapters done + quiz passed → "Completed" badge, 100%
- [x] Dashboard: same completion logic as courses page
- [x] `GET /syllabi` response includes `quiz_status` per course
- [x] `GET /syllabi/search` response includes `quiz_status` per course
- [x] `GET /syllabi/{skill_id}` response includes `quiz_status` and `quiz_difficulty`
- [x] Final Quiz nav item hidden until all chapters complete
- [x] Retry shuffles question order
- [x] "Quiz Overview" button in results returns to ready state (not chapter view)
- [x] `DELETE /syllabi/{skill_id}` removes course + quiz + attempts
