# API Reference

Base URL: `http://localhost:3005`

All endpoints (except `/auth/signup`, `/auth/login`, `/auth/refresh`, and `/public/*`) require a valid JWT access token in the `Authorization: Bearer <token>` header.

---

## Authentication

### POST /auth/signup

Create a new account.

**Request Body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | yes | User's email address |
| `password` | string | yes | Password |
| `name` | string | yes | Display name |

**Response** `201`
```json
{ "status": "success", "message": "Account created" }
```

| Status | Reason |
|--------|--------|
| `409` | Email already registered |

---

### POST /auth/login

Log in and receive tokens.

**Request Body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | yes | — |
| `password` | string | yes | — |

**Response**
```json
{ "access_token": "<jwt>", "token_type": "bearer" }
```
A `refresh_token` cookie is also set (HttpOnly).

| Status | Reason |
|--------|--------|
| `401` | Invalid credentials |

---

### POST /auth/refresh

Exchange the `refresh_token` cookie for a new access token.

**Response**
```json
{ "access_token": "<jwt>", "token_type": "bearer" }
```

| Status | Reason |
|--------|--------|
| `401` | Missing or expired refresh token |

---

### POST /auth/logout

Clear the `refresh_token` cookie.

**Response** `200`
```json
{ "status": "success" }
```

---

### GET /auth/me

Return the current user's profile.

**Response**
```json
{ "id": "...", "email": "user@example.com", "name": "Yogesh" }
```

---

### GET /auth/me/settings

Return the user's LLM provider configuration.

**Response**
```json
{
  "llm_provider": "openai",
  "llm_model": "gpt-4o-mini",
  "provider_keys": {
    "openai": true,
    "anthropic": false,
    "gemini": false,
    "mistral": false
  }
}
```

---

### PUT /auth/me/settings

Save LLM provider, API key, and model.

**Request Body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `llm_provider` | string | yes | e.g. `"openai"`, `"anthropic"`, `"gemini"`, `"mistral"` |
| `api_key` | string | yes | Provider API key |
| `llm_model` | string | no | Model name (leave blank for default) |

**Response**
```json
{ "status": "success" }
```

---

### GET /auth/me/models?provider=<name>

List available models for the given provider (uses the stored API key).

**Response**
```json
{ "models": ["gpt-4o", "gpt-4o-mini", ...] }
```

---

### POST /auth/me/models/verify?provider=<name>&model=<name>

Verify that a custom model name is callable.

**Response**
```json
{ "valid": true }
```

---

## Enrollment

### POST /subscribe

Enroll the authenticated user in a skill (creates the subscription record). Must be called before generating a syllabus.

**Request Body**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `skill` | string | yes | — | Skill name (e.g. `"Python"`) |
| `days` | integer | no | `90` | Total learning plan duration in days |
| `hours` | integer | no | `1` | Hours per day the user will study |
| `quiz_difficulty` | string | no | `"beginner"` | Quiz difficulty: `"beginner"`, `"intermediate"`, or `"advanced"` |

**Response**
```json
{ "status": "success", "message": "Subscribed to 'Python'" }
```

| Status | Reason |
|--------|--------|
| `409` | Already enrolled in this skill |

---

## Syllabi (Courses)

### GET /syllabi

List all courses for the authenticated user (with progress counts and quiz status).

**Response**
```json
[
  {
    "skill_id": 42,
    "skill": "Python",
    "days": 30,
    "hours": 1,
    "created_at": "2025-01-01 10:00:00",
    "total_tasks": 30,
    "completed_tasks": 15,
    "quiz_status": "available"
  }
]
```

`quiz_status` values: `"not_generated"` | `"available"` | `"passed"`

---

### GET /syllabi/search?q=<query>

Search courses and chapter topics/content.

Same response shape as `GET /syllabi`, with an additional `matching_chapters` array per result:
```json
"matching_chapters": [
  { "id": 5, "day": 3, "topic": "Functions", "task": "..." }
]
```

---

### GET /syllabi/{skill_id}

Get full syllabus detail (all months → weeks → chapters) for a course.

**Response**
```json
{
  "skill_id": 42,
  "skill": "Python",
  "days": 30,
  "hours": 1,
  "share_enabled": false,
  "quiz_difficulty": "beginner",
  "quiz_status": "available",
  "created_at": "...",
  "months": [
    {
      "month": 1,
      "weeks": [
        {
          "week": 1,
          "tasks": [
            {
              "id": 1,
              "day": 1,
              "topic": "Introduction",
              "task": "...",
              "completed": false,
              "newsletter": null
            }
          ]
        }
      ]
    }
  ]
}
```

| Status | Reason |
|--------|--------|
| `403` | Course belongs to a different user |
| `404` | Course not found |

---

### DELETE /syllabi/{skill_id}

Permanently delete a course and all related data (chapters, progress, quiz, attempts).

**Response**
```json
{ "status": "success" }
```

| Status | Reason |
|--------|--------|
| `404` | Course not found or not owned by you |

---

### PATCH /syllabi/{skill_id}/share?enable=<bool>

Enable or disable public sharing for a course.

**Response**
```json
{ "skill_id": 42, "share_enabled": true }
```

---

### POST /generate-syllabus

Generate the full Month → Week → Day syllabus for an enrolled skill using the user's configured LLM. Also triggers quiz generation in a background thread automatically.

**Request Body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `skill` | string | yes | Must match an enrolled skill name |

**Response**
```json
{ "status": "success", "message": "Syllabus generated for 'Python'" }
```

| Status | Reason |
|--------|--------|
| `404` | No enrollment found for this skill |
| `500` | LLM failed or returned unexpected format |

> The quiz is generated automatically in the background after the syllabus is saved. No separate quiz generation call is needed.

---

### GET /public/syllabi/{skill_id}

Retrieve a shared course (no auth required). Returns `404` if the course does not exist or sharing is disabled.

Rate limited to **10 requests/minute**.

---

## Content (Chapters)

### POST /generate-content

Generate AI chapter content for the next 10 pending days of a course.

**Request Body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `skill` | string | yes | Enrolled skill name |

**Response**
```json
{ "status": "success", "message": "Content generated" }
```

---

### POST /generate-content/chapter

Generate AI content for a single specific chapter.

**Request Body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `skill` | string | yes | Enrolled skill name |
| `task_id` | integer | yes | Chapter task ID |

**Response**
```json
{ "status": "success" }
```

---

### GET /chapter/{task_id}

Get a single chapter's content and completion status.

**Response**
```json
{
  "id": 1,
  "day": 1,
  "topic": "Introduction",
  "task": "...",
  "newsletter": "<html content>",
  "completed": false
}
```

| Status | Reason |
|--------|--------|
| `403` | Chapter belongs to a different user |
| `404` | Chapter not found |

---

### POST /chapter/{task_id}/complete

Mark a chapter as complete.

**Request Body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `local_date` | string | no | ISO date string from the client (for streak tracking) |

**Response**
```json
{ "status": "success" }
```

---

### GET /streak

Get the current user's learning streak stats.

**Response**
```json
{
  "current_streak": 3,
  "longest_streak": 7,
  "last_completed_date": "2025-01-10"
}
```

---

## Quiz

Quizzes are **auto-generated** in the background when a syllabus is created via `POST /generate-syllabus`. The quiz becomes available shortly after (typically within 10–30 seconds depending on LLM speed). The Final Quiz is only shown in the UI after all chapters are completed.

### GET /quiz/{skill_id}

Get the quiz for a course (questions, status, best score, attempt count).

**Response**
```json
{
  "quiz_id": 1,
  "skill_id": 42,
  "difficulty": "beginner",
  "pass_score": 60,
  "status": "available",
  "questions": [
    {
      "id": 1,
      "position": 1,
      "question": "What is a Python list?",
      "option_a": "...",
      "option_b": "...",
      "option_c": "...",
      "option_d": "..."
    }
  ],
  "best_score": null,
  "attempt_count": 0
}
```

`status` values: `"available"` | `"passed"`

| Status | Reason |
|--------|--------|
| `403` | Course belongs to a different user |
| `404` | Quiz not yet generated (still in background, poll again) |

---

### POST /quiz/{skill_id}/submit

Submit answers and receive a scored result.

**Request Body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `answers` | object | yes | Map of `question_id → selected_option` (e.g. `{"1": "A", "2": "C"}`) |

**Response**
```json
{
  "attempt_id": 7,
  "score": 70,
  "passed": true,
  "pass_score": 60,
  "results": [
    {
      "question_id": 1,
      "selected": "A",
      "correct": "A",
      "is_correct": true,
      "explanation": "..."
    }
  ]
}
```

| Status | Reason |
|--------|--------|
| `404` | Quiz not found for this course |

---

### GET /quiz/{skill_id}/attempts

List all past quiz attempts for a course.

**Response**
```json
[
  {
    "attempt_id": 7,
    "score": 70,
    "passed": true,
    "created_at": "2025-01-10T12:00:00"
  }
]
```

---

### POST /quiz/{skill_id}/generate

Manually trigger quiz generation for a course (only needed if auto-generation failed).

**Response**
```json
{ "status": "success", "message": "Quiz generated" }
```

| Status | Reason |
|--------|--------|
| `403` | Course belongs to a different user |
| `404` | Course not found |
| `409` | Quiz already exists for this course |

---

## Newsletter

### POST /send-email/chapter

Send the chapter email for a specific task to the user.

**Request Body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `skill` | string | yes | Enrolled skill name |
| `task_id` | integer | yes | Chapter task ID |

**Response**
```json
{ "status": "success" }
```

---

### POST /issue-newsletters

Send today's chapter email to all active subscribers (intended for cron job use).

**Response**
```json
{ "status": "success", "message": "Today's newsletters issued successfully" }
```

---

## Progress & Completion Model

A course is considered **Completed** only when:
1. All chapter tasks are marked complete, **and**
2. The final quiz is passed (score ≥ pass_score)

Progress percentage is calculated as:

```text
totalSteps     = total_tasks + 1         (quiz counts as 1 extra step)
completedSteps = completed_tasks + (quiz_passed ? 1 : 0)
progress%      = round(completedSteps / totalSteps * 100)
```

This means a course with all chapters done but quiz not passed will show **~95–99%** (depending on number of tasks), not 100%.

---

## Typical Flow

```text
1. POST /auth/signup              — create account
2. POST /auth/login               — get access token
3. PUT  /auth/me/settings         — configure LLM provider + API key
4. POST /subscribe                — enroll in a skill (days, hours, quiz_difficulty)
5. POST /generate-syllabus        — generate the course plan
                                    └─ quiz auto-generated in background
6. POST /generate-content/chapter — generate AI content for a chapter
7. POST /chapter/{id}/complete    — mark chapter complete (repeat for each chapter)
8. GET  /quiz/{skill_id}          — fetch quiz (poll if still generating)
9. POST /quiz/{skill_id}/submit   — submit answers → course marked Completed if passed
```
