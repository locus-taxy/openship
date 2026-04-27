# Issue #49 — Course Quiz

## Overview

Add an AI-generated quiz at the end of every course. The quiz difficulty is set at
enrollment time (beginner / intermediate / advanced). A course cannot be marked
fully complete until the user passes the quiz.

---

## Requirements Summary

| # | Requirement |
|---|-------------|
| 1 | Difficulty collected during enrollment (beginner / intermediate / advanced) |
| 2 | Quiz is the last "chapter" — appears after all daily tasks are complete |
| 3 | AI generates questions based on the actual syllabus topics the user studied |
| 4 | Quiz is multiple-choice (4 options per question) |
| 5 | Pass threshold varies by difficulty (see below) |
| 6 | Unlimited retries; each attempt is recorded |
| 7 | Course is only marked **complete** after passing the quiz |
| 8 | Quiz answers are never exposed in GET responses — only revealed after submission |

---

## Data Model

### 1. Alter `skills` table — add `quiz_difficulty`

```sql
ALTER TABLE skills ADD COLUMN quiz_difficulty VARCHAR(20) DEFAULT 'beginner';
```

Allowed values: `"beginner"` | `"intermediate"` | `"advanced"`

```python
# models/skill.py  (add field)
quiz_difficulty: str = Field(default="beginner")
```

### 2. New table — `quizzes`

One row per skill. Created lazily when the quiz is first generated.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `skill_id` | Integer FK → skills.id CASCADE | UNIQUE (one quiz per course) |
| `difficulty` | VARCHAR(20) | copied from skill at generation time |
| `pass_score` | Integer | percentage required to pass (60/70/80) |
| `status` | VARCHAR(20) | `pending` · `available` · `passed` · `failed` |
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
    status: str = Field(default="pending")  # pending | available | passed | failed
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
| 30 | 10 |
| 60 | 12 |
| 90 | 15 |

---

## API Routes

### New routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/quiz/{skill_id}/generate` | Required | Generate quiz (called once when all chapters complete) |
| `GET` | `/quiz/{skill_id}` | Required | Get quiz questions (no correct answers in response) |
| `POST` | `/quiz/{skill_id}/submit` | Required | Submit answers; returns score + per-question result |
| `GET` | `/quiz/{skill_id}/attempts` | Required | List all past attempts for this quiz |

### Modified routes

| Method | Path | Change |
|--------|------|--------|
| `POST` | `/subscribe` | Accept `quiz_difficulty` field (default `"beginner"`) |
| `GET` | `/syllabi/{skill_id}` | Response includes `quiz_status` and `quiz_difficulty` |
| `GET` | `/syllabi` | Response includes `quiz_status` per course (for analytics + syllabi list) |
| `POST` | `/chapter/{task_id}/complete` | No change in logic — chapter-level completion is unchanged |

---

## Request / Response Schemas

### `POST /subscribe` (modified)

```python
# schemas/skill.py
from typing import Literal

class SubscribeRequest(BaseModel):
    skill: str
    days: int = Field(90, gt=0)
    hours: int = Field(1, gt=0)
    quiz_difficulty: Literal["beginner", "intermediate", "advanced"] = "beginner"  # NEW
```

> Uses `Literal` type (Pydantic v2 style, already used in the codebase) instead of
> a `@validator` — FastAPI will auto-validate and return 422 on invalid values.

### `POST /quiz/{skill_id}/generate` — response

```python
class QuizGenerateResponse(BaseModel):
    quiz_id: int
    status: str          # "available"
    question_count: int
    pass_score: int
```

### `GET /syllabi/{skill_id}` (modified response)

`services/skill.py::get_syllabus_detail()` needs a LEFT JOIN on `quizzes` to add:

```python
# added to the returned dict
"quiz_difficulty": skill_row.quiz_difficulty,
"quiz_status": quiz_row.status if quiz_row else "not_generated",
# "not_generated" | "available" | "passed" | "failed"
```

### `GET /syllabi` (modified response)

`services/skill.py::get_all_syllabi()` needs a LEFT JOIN on `quizzes` to add per course:

```python
"quiz_status": quiz_row.status if quiz_row else "not_generated",
```

Analytics `getStatus()` in `ui/src/app/plugins/analytics/index.tsx` currently treats
`completed_tasks / total_tasks === 100%` as "completed". This must be updated:

```typescript
// BEFORE
function getStatus(completed: number, total: number) {
    const pct = (completed / total) * 100
    if (pct === 100) return "completed"
    ...
}

// AFTER — quiz_status must also be "passed" for a course to show as complete
function getStatus(completed: number, total: number, quizStatus: string) {
    if (total === 0) return "no-syllabus"
    const pct = (completed / total) * 100
    if (pct === 100 && quizStatus === "passed") return "completed"
    if (pct > 0 || quizStatus !== "not_generated") return "in-progress"
    return "not-started"
}
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
    status: str
    questions: List[QuizQuestionOut]
    best_score: Optional[int]     # from past attempts
    attempt_count: int
```

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

---

## LLM Generation

### New Pydantic output model

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

### System prompt

```
You are an expert educator creating a {difficulty}-level quiz for a student who
has just completed a {num_questions}-chapter {skill} course.

The course covered these topics (in order):
{topics_numbered_list}

Generate exactly {num_questions} multiple-choice questions:
- Each question must have exactly 4 options labeled A, B, C, D
- Questions should test understanding across the breadth of the course topics
- Difficulty: {difficulty} — {"recall and basic understanding" if beginner,
  "application and problem-solving" if intermediate,
  "analysis, edge cases, and trade-offs" if advanced}
- Vary question types: definitions, code reasoning, best-practice selection,
  debugging concepts, comparisons
- The explanation should clarify why the correct answer is right and the main
  distractors are wrong (1-2 sentences)
```

---

## Service Layer

### `services/quiz.py` (new file)

```python
def get_or_create_quiz(skill_id: int) -> Quiz | None
    # returns existing quiz or None if not yet generated

def create_quiz(skill_id: int, difficulty: str, questions: List[GeneratedQuestion]) -> Quiz
    # inserts Quiz + QuizQuestion rows in a single transaction
    # sets pass_score based on difficulty constant

def get_quiz_with_questions(quiz_id: int) -> tuple[Quiz, List[QuizQuestion]]
    # used for GET /quiz/{skill_id}

def record_attempt(quiz: Quiz, user_id: int, answers: Dict[int, str]) -> QuizAttempt
    # scores the attempt, sets quiz.status to "passed" if passed, commits

def get_best_score(quiz_id: int, user_id: int) -> Optional[int]
    # returns highest score across all attempts

def all_chapters_complete(skill_id: int) -> bool
    # SELECT COUNT(*) WHERE skill_id=X AND completed=False == 0
```

---

## Controller Layer

### `controllers/quiz.py` (new file)

```python
def generate_quiz(skill_id: int, current_user: User) -> QuizGenerateResponse:
    # 1. Verify skill ownership (403 if not owner)
    # 2. Check all chapters complete — raise HTTP 400 if not
    # 3. Check quiz doesn't already exist — raise HTTP 409 if it does
    # 4. Fetch topics from daily_tasks
    # 5. Get user LLM settings; raise HTTP 400 if not configured
    # 6. Call services.llm.generate_quiz()
    # 7. Call services.quiz.create_quiz()
    # 8. Return QuizGenerateResponse

def get_quiz(skill_id: int, current_user: User) -> QuizOut:
    # 1. Verify ownership
    # 2. Fetch quiz (404 if not generated yet)
    # 3. Strip correct_option from questions
    # 4. Attach best_score and attempt_count

def submit_quiz(skill_id: int, payload: QuizSubmitRequest, current_user: User) -> QuizSubmitResponse:
    # 1. Verify ownership
    # 2. Fetch quiz (404 if missing)
    # 3. Validate all question IDs belong to this quiz
    # 4. Score answers
    # 5. services.quiz.record_attempt()
    # 6. Return full per-question breakdown with correct answers + explanations
```

---

## Route Registration

```python
# routes/quiz.py (new file)
router = APIRouter(prefix="/quiz", tags=["quiz"])

@router.post("/{skill_id}/generate")
def generate_quiz(skill_id: int, request: Request):
    return quiz_controller.generate_quiz(skill_id, request.state.user)

@router.get("/{skill_id}")
def get_quiz(skill_id: int, request: Request):
    return quiz_controller.get_quiz(skill_id, request.state.user)

@router.post("/{skill_id}/submit")
def submit_quiz(skill_id: int, payload: QuizSubmitRequest, request: Request):
    return quiz_controller.submit_quiz(skill_id, payload, request.state.user)

@router.get("/{skill_id}/attempts")
def get_attempts(skill_id: int, request: Request):
    return quiz_controller.get_attempts(skill_id, request.state.user)
```

Register in `main.py`:
```python
from routes.quiz import router as quiz_router
app.include_router(quiz_router, prefix="/py")
```

---

## Frontend Changes

### 1. Enrollment form — add difficulty picker

New step in `ui/src/app/plugins/enroll/index.tsx`:

```
Difficulty Level
[ Beginner ]  [ Intermediate ]  [ Advanced ]
```

- Default: `Beginner`
- Add `quiz_difficulty` to the POST payload

### 2. Syllabus detail — quiz entry point

In `ui/src/app/plugins/syllabi/detail.tsx`, after all chapters are complete:

- Replace "all done" empty state with a **"Take Quiz"** button in the chapter nav footer
- The "Take Quiz" button is disabled until all chapters are marked complete
- Clicking it:
  - If quiz not yet generated → calls `POST /quiz/{skill_id}/generate` first
  - Then navigates to `/syllabi/{skill_id}/quiz`

**Progress display**: course progress bar stays at 99% until quiz is passed — jumps to 100% on pass.

### 3. New quiz page — `/syllabi/{skill_id}/quiz`

New file: `ui/src/app/plugins/syllabi/quiz.tsx`

**States**:

| State | UI |
|-------|----|
| Loading | Spinner |
| Ready | Question list with radio buttons, Submit button |
| Submitted (pass) | Green result card, score, per-question breakdown with explanations, "Back to Course" button |
| Submitted (fail) | Red result card, score, per-question breakdown, "Retry Quiz" button |
| Already passed | Show best score, "View Result" or "Back to Course" |

**Question rendering**:
```
Q1. What is the time complexity of binary search?
  ○ A. O(n)
  ○ B. O(log n)   ← user selects
  ○ C. O(n²)
  ○ D. O(1)
```

After submission, each question shows:
- Green checkmark (correct) or red X (wrong)
- The correct option highlighted
- Explanation text

**Retry**: clears selected answers, re-fetches questions, posts a new attempt.

### 4. Route registration in React Router

```tsx
// In App.tsx or routes config
<Route path="/syllabi/:skillId/quiz" element={<QuizPage />} />
```

### 5. Nav / progress — course status

`GET /syllabi/{skill_id}` response should include `quiz_status` so the sidebar can show:
- Chapters complete, quiz pending → "Take Quiz" CTA
- Quiz passed → progress 100%

---

## Alembic Migrations

Three new migration files (in order):

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

## Public Syllabus (no auth)

`GET /public/syllabi/{skill_id}` — currently shows syllabus tree. No quiz info
should be exposed in the public view. This route requires no change.

---

## Auth Middleware — no change needed

The new `/quiz/` routes are under the authenticated prefix. The only change
needed in `middleware/auth.py` is confirming `/quiz/` is NOT in `PUBLIC_EXACT`
or `PUBLIC_PREFIXES` — which is already the case (no action needed).

---

## Edge Cases

| Case | Handling |
|------|----------|
| Generate quiz before all chapters done | HTTP 400 "Complete all chapters before taking the quiz" |
| Generate quiz twice | HTTP 409 "Quiz already generated for this course" |
| Submit with missing question IDs | HTTP 422 validation error |
| Submit with question IDs from different quiz | HTTP 400 "Invalid question IDs" |
| LLM fails during quiz generation | HTTP 502; no partial quiz saved (transaction rollback) |
| User retries after passing | Allowed; attempt recorded; `passed` status stays |
| 0 chapters (edge) | Cannot subscribe with 0 days — guarded at enrollment |

---

## Files to Create / Modify

### New files
| File | Purpose |
|------|---------|
| `models/quiz.py` | Quiz table |
| `models/quiz_question.py` | QuizQuestion table |
| `models/quiz_attempt.py` | QuizAttempt table |
| `services/quiz.py` | Quiz business logic |
| `controllers/quiz.py` | Quiz request handlers |
| `routes/quiz.py` | FastAPI router |
| `ui/src/app/plugins/syllabi/quiz.tsx` | Quiz page component |
| `alembic/versions/xxx_add_quiz_difficulty_to_skills.py` | Migration |
| `alembic/versions/xxx_create_quizzes_and_questions.py` | Migration |
| `alembic/versions/xxx_create_quiz_attempts.py` | Migration |

### Modified files
| File | Change |
|------|--------|
| `models/skill.py` | Add `quiz_difficulty` field |
| `models/__init__.py` | Export `Quiz`, `QuizQuestion`, `QuizAttempt` |
| `schemas/skill.py` | Add `quiz_difficulty: Literal[...]` to `SubscribeRequest` |
| `services/skill.py` | `create_skill()` accepts `quiz_difficulty`; `get_syllabus_detail()` and `get_all_syllabi()` LEFT JOIN quizzes, return `quiz_status` / `quiz_difficulty` |
| `services/llm.py` | Add `GeneratedQuestion`, `GeneratedQuiz`, `generate_quiz()` |
| `controllers/subscription.py` | Pass `quiz_difficulty` through to `create_skill()` |
| `main.py` | Register quiz router |
| `ui/src/app/plugins/enroll/index.tsx` | Add difficulty picker |
| `ui/src/app/plugins/syllabi/detail.tsx` | Add "Take Quiz" CTA, update progress logic |
| `ui/src/app/plugins/analytics/index.tsx` | Update `getStatus()` to require `quiz_status === "passed"` for "completed" |
| `ui/src/App.tsx` | Add `/syllabi/:skillId/quiz` route |

---

## Verification Checklist

- [ ] `POST /subscribe` with `quiz_difficulty: "advanced"` → skill row has `quiz_difficulty = advanced`
- [ ] `POST /quiz/{skill_id}/generate` before all chapters complete → 400
- [ ] `POST /quiz/{skill_id}/generate` after all chapters complete → 200, questions created
- [ ] `GET /quiz/{skill_id}` → questions returned, no `correct_option` field
- [ ] `POST /quiz/{skill_id}/submit` correct answers → score + explanations
- [ ] Failing attempt → `quiz.status` stays `available`, retry works
- [ ] Passing attempt → `quiz.status` = `passed`, progress = 100%
- [ ] `POST /quiz/{skill_id}/generate` second time → 409
- [ ] `GET /public/syllabi/{skill_id}` → no quiz data leaked
- [ ] Analytics: all chapters done but quiz not passed → status "in-progress", not "completed"
- [ ] Analytics: all chapters done + quiz passed → status "completed", progress 100%
- [ ] `GET /syllabi` response includes `quiz_status` per course
- [ ] `GET /syllabi/{skill_id}` response includes `quiz_status` and `quiz_difficulty`
