# Openship: The Open-Source AI Learning Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

## What Is Openship?

Openship is a fully open-source, AI-powered learning platform built by the team at **Locus**.

You pick a skill and set how many days and hours per day you can commit. Openship generates a structured **Month / Week / Day** curriculum, writes AI lessons for each chapter on demand, and runs weekly quizzes to track your mastery. Each new week is generated based on your quiz results, so the plan adapts to what you actually know rather than following a fixed template.

---

## Demo





https://github.com/user-attachments/assets/c4f19506-851a-422c-bc63-a0e2252c8e78





---

## How it works

1. **Configure** - add your LLM provider API key (Anthropic, OpenAI, Google Gemini, or Mistral) in Settings
2. **Enroll** - choose a skill, set your duration and daily time commitment
3. **Generate** - your AI model creates a structured syllabus organized by month, week, and day; Week 1 is unlocked immediately with a pre-generated quiz
4. **Learn** - open any chapter, generate its content on demand, and mark days complete as you go
5. **Weekly quiz** - after finishing all chapters in a week, take an AI-generated quiz; your score determines how the next week is planned: weak topics get extra focus, forgotten ones get spaced repetition
6. **Adaptive next week** - the platform generates the next week on demand, personalized using your quiz results and mastery data
7. **Final quiz** - once all weeks are complete, a final quiz covers the topics you struggled with most; pass it to reach 100%
8. **Track** - the analytics dashboard shows your overall progress across all courses

---

## Key Features

### 1. Bring Your Own AI

Plug in your own API key for Anthropic, OpenAI, Google Gemini, or Mistral. Switch providers at any time. No subscriptions, no lock-in.

### 2. Adaptive ML Engine

Three components work together to personalize each week:

- **Bayesian Knowledge Tracing (BKT)** - tracks per-topic mastery after every quiz answer; low-scoring topics are automatically included in the next week's plan
- **Forgetting Curve** - identifies topics not seen recently and schedules them for spaced repetition
- **Thompson Sampling Bandit** - selects a content style per week (`Visual-Heavy`, `Example-Heavy`, `Diagram-Heavy`, or `Story-Driven`) and updates based on quiz scores

### 3. On-Demand Chapter Content

Each chapter is generated when you open it, not pre-written. Content includes syntax-highlighted code, diagrams, tables, and examples written specifically for that lesson in the context of your full syllabus.

### 4. Progress Tracking

Mark chapters complete, track quiz scores, and monitor all active courses from the analytics dashboard.

### 5. Shareable Syllabi

Share any syllabus publicly with one link. No account required to view.

### 6. Secure API Key Storage

LLM API keys are partially encrypted at rest: the prefix is stored in plaintext, the sensitive suffix is encrypted with a server-side Fernet key. A database breach alone is not enough to reconstruct a key.

---

## Features

### Core learning loop
- **Multi-provider LLM support** - Anthropic (Claude), OpenAI (GPT), Google Gemini, Mistral; switch providers and models from the UI
- **Personalized syllabus generation** - AI produces a structured month / week / day plan tailored to the skill and your schedule
- **On-demand chapter content** - AI-written lessons generated per chapter with code blocks, diagrams, tables, and examples
- **Progressive week unlock** - only Week 1 is generated upfront; subsequent weeks are generated after the previous week's quiz, personalized to your results

### Adaptive ML engine
- **Bayesian Knowledge Tracing** - per-topic mastery model updated after every quiz submission; weak topics fed into the next week's plan
- **Forgetting curve** - spaced repetition scheduling based on time since last exposure; forgotten topics resurface automatically
- **Thompson Sampling bandit** - picks a chapter content style per week and updates from quiz feedback
- **Remediation planning** - low quiz score triggers extra review days at the start of the next week

### Quizzes
- **Weekly quizzes** - AI-generated 5-question quiz per week covering that week's topics; unlocks the next week on completion
- **Final quiz** - personalized to the topics you struggled with most; appears after all weeks are complete; pass it to reach 100%
- **Quiz variant pools** - each question is generated in multiple variants; a different variant is sampled per attempt so retakes feel fresh
- **Score history** - every attempt recorded with timestamp and score; best score tracked per quiz

### Progress and analytics
- **Progress tracking** - mark chapters complete; progress bar accounts for chapters and final quiz pass (weekly quizzes excluded from progress denominator)
- **Analytics dashboard** - overview of all courses: completion rates, hours planned, tasks remaining

### LLM cost analytics
- **Per-generation cost logging** - every LLM call (chapter, syllabus, quiz) is logged to `llm_usage_logs` with input/output token counts, provider, model, and computed `cost_usd`
- **Immutable pricing snapshots** - the exact input/output price per million tokens used at generation time is frozen in a `pricing_snapshots` row and linked to each chapter via `daily_tasks.pricing_id`; historical costs stay accurate even after pricing changes
- **Chapter cost badge** - the chapter view shows a live cost badge (e.g. `₹0.0042 · 2×`) that accumulates across regenerations and converts to the user's chosen display currency
- **Manual pricing overrides** - when a model is not listed on ai-model-pricing.com, users can enter $/1M input and output prices directly in settings; stored in `user_model_prices` and used as a fallback
- **Auto-fetched pricing** - prices are fetched from ai-model-pricing.com with three-tier model matching (exact → forward-prefix → reverse-prefix); cache is held for the lifetime of the server process
- **Refresh Prices button** - clears the in-memory price cache so prices are re-fetched on the next pricing lookup
- **Currency settings** - display currency and exchange rate configurable per user; all stored values remain in USD

### Other
- **Shareable syllabi** - public link to share any syllabus (no account required to view)
- **Course management** - delete any enrolled course (removes all chapters, progress, quizzes, and attempts)
- **Resizable chapter sidebar** - collapsible and draggable sidebar with chapter tree navigation
- **JWT authentication** - cookie-based auth with access and refresh tokens, enforced globally via middleware
- **Fully responsive** - works on mobile, tablet, and desktop

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn |
| AI | Anthropic, OpenAI, Google Gemini, Mistral (via `instructor`) |
| ML | Bayesian Knowledge Tracing, Thompson Sampling, Ebbinghaus Forgetting Curve |
| Database | PostgreSQL, SQLModel ORM, Alembic migrations |
| Frontend | React 18 + TypeScript + Vite |
| UI Components | shadcn/ui, Radix UI, Tailwind CSS |
| State | Zustand |
| Auth | JWT (httponly cookies) + bcrypt |
| Routing | React Router v6 |

---

## Getting Started

### Option 1: Docker (recommended — no local tooling required)

```bash
git clone https://github.com/locus-taxy/openship.git
cd openship
make bootstrap
```

`make bootstrap` installs Docker if it's missing (official installer on Linux, Homebrew
on macOS), waits for the daemon, then starts the whole stack. It also auto-creates `.env`
and generates the required secrets (`JWT_SECRET_KEY`, `LLM_ENCRYPTION_KEY`) — you never edit a config file.

> **macOS note:** if Docker Desktop gets installed, launch it once to accept the license, then re-run `make bootstrap`.
> **Already have Docker?** Use `make docker-up` directly — same result, skips the install check.

Open [http://localhost](http://localhost) in your browser.

> The first build downloads 60+ language runtimes (~5-8 GB) and takes 10-15 minutes. Subsequent starts are fast.

Other Docker commands:

```bash
make docker-up     # start (assumes Docker is already installed)
make docker-logs   # stream logs from all services
make docker-down   # stop the stack
make docker-reset  # wipe all data and rebuild from scratch
```

---

### Option 2: Local development

**Prerequisites:** Python 3.13+, Node.js 18+, PostgreSQL, Git

```bash
git clone https://github.com/locus-taxy/openship.git
cd openship
make setup
```

`make setup` runs `scripts/setup.sh` which:
1. Creates `.env` from `.env.example` if one does not exist
2. Creates a Python virtual environment at `.venv` and installs all deps
3. Runs `npm install` in `ui/` for the frontend
4. Configures Husky git hooks (requires a git clone)

Edit `.env` with your database URL and secrets (see [Environment Variables](#environment-variables)), then start:

```bash
make dev
```

> **macOS** - `make dev` opens two separate Terminal windows (API on `:3005`, UI on `:5173`). It waits for the API to be ready before launching the UI.
>
> **Linux** - run `make run-api` and `make run-ui` in two separate shells instead.

For a full walkthrough including PostgreSQL setup and troubleshooting see **[docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md)**.

### Available commands

| Command | Description |
|---------|-------------|
| `make setup` | One-time setup: venv, deps, `.env`, Husky hooks |
| `make dev` | Start API + UI (macOS) |
| `make run-api` | FastAPI only, with hot reload on `:3005` |
| `make run-ui` | Vite dev server only on `:5173` |
| `make format` | Auto-format Python with Black via pre-commit |
| `make format-check` | CI-style format check |
| `make install` | Alias for `make setup` |

---

## Environment Variables

Copy `.env.example` to `.env` and set at minimum:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | SQLAlchemy connection string (PostgreSQL) |
| `JWT_SECRET_KEY` | Yes | Random string, minimum 32 characters |
| `LLM_ENCRYPTION_KEY` | Yes | Fernet key for encrypting stored API keys. Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `RUN_MIGRATIONS_ON_STARTUP` | No | Run `alembic upgrade head` on startup (default: `true`) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | Access token lifetime (default: `2`) |
| `JWT_REFRESH_TOKEN_EXPIRE_HOURS` | No | Refresh token lifetime (default: `7`) |

> **LLM API keys** are not stored in `.env`. Users add their own key per provider through the Settings panel in the UI. Keys are partially encrypted at rest using `LLM_ENCRYPTION_KEY` (Fernet/AES-128-CBC). A database leak alone is not sufficient to reconstruct a key.

---

## API Reference

Interactive docs (Swagger UI) are available at `http://localhost:3005/docs` when running locally.

---

## Contributing

Contributions are welcome. Please read **[CONTRIBUTING.md](CONTRIBUTING.md)** for:

- Development setup
- Code style (Black for Python, ESLint for TypeScript)
- Branch and commit conventions
- Pull request process

---

## Security

Do not open public issues for security vulnerabilities.

See **[SECURITY.md](SECURITY.md)** for the responsible disclosure policy and contact information.

---

## License

Openship is released under the [MIT License](LICENSE).

Third-party dependency attributions are listed in [NOTICE](NOTICE).
