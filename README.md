# Openship

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

Openship is an AI-powered personalized learning platform. Pick a skill and your time commitment — it builds a structured **Month → Week → Day** curriculum, generates AI-written lessons for each chapter, and caps every course with an AI-generated final quiz to validate what you've learned.

---

## Demo



https://github.com/user-attachments/assets/cd3fc567-a654-41c8-a33d-fb354fd51b38



---

## How it works

1. **Configure** — add your LLM provider API key (Anthropic, OpenAI, Google Gemini, or Mistral) in Settings
2. **Enroll** — choose a skill, set your duration, daily time commitment, and quiz difficulty
3. **Generate** — your AI model creates a structured syllabus organized by month, week, and day — and auto-generates a final quiz in the background
4. **Learn** — open any chapter, generate its content on demand, and mark days complete as you go
5. **Quiz** — once all chapters are done, take the AI-generated final quiz; pass it to reach 100% completion
6. **Track** — the analytics dashboard shows your overall progress across all courses

---

## Features

- **Multi-provider LLM support** — bring your own API key for Anthropic (Claude), OpenAI (GPT), Google Gemini, or Mistral; switch providers and models at any time from the UI
- **Personalized syllabus generation** — AI produces a structured 3-level plan (month / week / day) tailored to the skill and your schedule
- **On-demand chapter content** — rich AI-written lessons generated per chapter with syntax-highlighted code blocks, tables, and examples
- **AI-generated final quiz** — automatically created in the background when a course is generated; multiple-choice questions drawn from the actual topics you studied; difficulty set at enrollment (beginner / intermediate / advanced)
- **Quiz gating** — Final Quiz appears only after all chapters are complete; passing it brings the course to 100%
- **Unlimited quiz retries** — questions are shuffled on each retry; every attempt is recorded with score history
- **Progress tracking** — mark chapters complete; progress bar accounts for both chapters and quiz pass; analytics update in real time
- **Analytics dashboard** — overview of all courses: completion rates, in-progress courses, hours planned, tasks remaining
- **Course management** — delete any enrolled course (removes all chapters, progress, quiz, and attempts)
- **Shareable syllabi** — generate a public link to share any syllabus with others
- **Resizable chapter sidebar** — collapsible and draggable sidebar with chapter tree navigation
- **JWT authentication** — cookie-based auth with access and refresh tokens, enforced globally via middleware
- **Fully responsive** — works on mobile, tablet, and desktop

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn |
| AI | Anthropic, OpenAI, Google Gemini, Mistral (via `instructor`) |
| Database | PostgreSQL · SQLModel ORM · Alembic migrations |
| Frontend | React 18 + TypeScript + Vite |
| UI Components | shadcn/ui · Radix UI · Tailwind CSS |
| State | Zustand |
| Auth | JWT (httponly cookies) + bcrypt |
| Routing | React Router v6 |

---

## Getting Started

### Prerequisites

- Python 3.9+ (`python3` on PATH)
- Node.js 18+ and npm
- Git
- PostgreSQL

### Quick start

```bash
git clone https://github.com/locus-taxy/openship.git
cd openship
make setup
```

`make setup` runs `scripts/setup.sh` which:
1. Creates `.env` from `.env.example` if one doesn't exist
2. Creates a Python virtual environment at `.venv` and installs all deps
3. Runs `npm install` in `ui/` for the frontend
4. Configures Husky git hooks (requires a git clone)

Then edit `.env` with your database URL and secrets (see [Environment Variables](#environment-variables)), and start:

```bash
make dev
```

> **macOS** — `make dev` opens two separate Terminal windows (API on `:3005`, UI on `:5173`) using `osascript`. It waits for the API to be ready before launching the UI.
>
> **Linux** — run `make run-api` and `make run-ui` in two separate shells instead.

For a full walkthrough including PostgreSQL setup and troubleshooting see **[docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md)**.

### Available commands

| Command | Description |
|---------|-------------|
| `make setup` | One-time setup: venv, deps, `.env`, Husky hooks |
| `make dev` | Start API + UI (macOS — opens two Terminal windows) |
| `make run-api` | FastAPI only, with hot reload on `:3005` |
| `make run-ui` | Vite dev server only on `:5173` |
| `make format` | Auto-format Python with Black via pre-commit |
| `make format-check` | CI-style format check — fails if not clean |
| `make install` | Alias for `make setup` |

---

## Environment Variables

Copy `.env.example` to `.env` and set at minimum:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | SQLAlchemy connection string (PostgreSQL) |
| `JWT_SECRET_KEY` | Yes | Random string, minimum 32 characters |
| `LLM_ENCRYPTION_KEY` | Yes | Fernet key for encrypting stored API keys — generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `RUN_MIGRATIONS_ON_STARTUP` | No | Run `alembic upgrade head` on startup (default: `true`) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | Access token lifetime (default: `2`) |
| `JWT_REFRESH_TOKEN_EXPIRE_HOURS` | No | Refresh token lifetime (default: `7`) |

> **LLM API keys** are not stored in `.env`. Users add their own API key per provider through the Settings panel in the UI after logging in. Keys are partially encrypted at rest: the key prefix is stored in plaintext while only the last 5 characters are encrypted using `LLM_ENCRYPTION_KEY` (Fernet/AES-128-CBC). A database leak alone is not sufficient to reconstruct a key — the server-side `LLM_ENCRYPTION_KEY` is also required.

---

## API Reference

Interactive docs (Swagger UI) are available at `http://localhost:3005/docs` when running locally.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/signup` | Create an account |
| `POST` | `/auth/login` | Log in, receive access + refresh cookies |
| `POST` | `/auth/refresh` | Refresh an expired access token |
| `POST` | `/auth/logout` | Clear session cookies |
| `GET` | `/auth/me` | Get current user profile |
| `GET` | `/auth/me/settings` | Get LLM provider and model settings |
| `PUT` | `/auth/me/settings` | Update provider, model, or API key |
| `GET` | `/auth/me/models` | List available models for a provider |
| `POST` | `/auth/me/models/verify` | Verify a provider/model/API key combination |
| `POST` | `/subscribe` | Enroll in a skill (`quiz_difficulty` included) |
| `GET` | `/syllabi` | List all courses (includes `quiz_status` per course) |
| `GET` | `/syllabi/search` | Search courses and chapters (includes `quiz_status`) |
| `GET` | `/syllabi/{skill_id}` | Get course with full chapter tree + quiz status |
| `DELETE` | `/syllabi/{skill_id}` | Delete a course and all its data |
| `POST` | `/generate-syllabus` | Generate syllabus + auto-trigger quiz generation |
| `PATCH` | `/syllabi/{skill_id}/share` | Enable / disable public sharing |
| `POST` | `/generate-content/chapter` | Generate content for a chapter |
| `GET` | `/chapter/{task_id}` | Get generated chapter content |
| `POST` | `/chapter/{task_id}/complete` | Mark a chapter as complete |
| `GET` | `/quiz/{skill_id}` | Get quiz questions (poll until ready; 404 while generating) |
| `POST` | `/quiz/{skill_id}/submit` | Submit answers; returns score + per-question breakdown |
| `GET` | `/quiz/{skill_id}/attempts` | List all past quiz attempts |
| `POST` | `/quiz/{skill_id}/generate` | Manually trigger quiz generation (fallback only) |
| `GET` | `/public/syllabi/{skill_id}` | View a publicly shared syllabus (no auth) |

---

## Project Structure

```text
openship/
├── controllers/          # Request handling logic (auth, syllabus, content)
├── services/             # Business logic (LLM routing, encryption, JWT)
├── models/               # SQLModel table definitions
├── schemas/              # Pydantic request/response schemas
├── routes/               # FastAPI router registration
├── middleware/            # Global auth middleware
├── alembic/              # Database migration scripts
├── scripts/              # setup.sh and formatting helpers
├── docs/                 # Local setup guide, architecture notes
├── ui/                   # React + TypeScript frontend (Vite)
│   └── src/
│       ├── app/plugins/  # Page-level components (enroll, syllabi, analytics)
│       ├── components/   # Shared UI (sidebar, llm-bar, settings dialog)
│       └── store/        # Zustand global state
└── main.py               # Application entry point
```

---

## Contributing

Contributions are welcome. Please read **[CONTRIBUTING.md](CONTRIBUTING.md)** for:

- Development setup
- Code style (Black for Python, ESLint for TypeScript)
- Branch and commit conventions
- Pull request process

---

## Security

**Do not open public issues for security vulnerabilities.**

See **[SECURITY.md](SECURITY.md)** for the responsible disclosure policy and contact information.

---

## License

Openship is released under the [MIT License](LICENSE).

Third-party dependency attributions are listed in [NOTICE](NOTICE).
