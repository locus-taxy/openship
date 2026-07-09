# Openship: The Open-Source AI Learning & Knowledge Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

## What Is Openship?

Openship is a fully open-source, AI platform built by the team at **Locus**, with two pillars:

1. **Adaptive learning** - you pick a skill and set how many days and hours per day you can commit. Openship generates a structured **Month / Week / Day** curriculum, writes AI lessons for each chapter on demand, and runs weekly quizzes to track your mastery. Each new week is generated based on your quiz results, so the plan adapts to what you actually know rather than following a fixed template.

2. **Company knowledge platform** - connect your **Atlassian** workspace once and Openship ingests your **Confluence** pages and **Jira** issues into a single AI-searchable knowledge base (RAG). It powers company **Onboarding** plans and a **Knowledge chat** that answers from your own docs - with source-linked citations and people-analytics ("who's working on what").

---

## Demo





https://github.com/user-attachments/assets/5583c075-7c33-48ad-8706-26d4b3acafea








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
- **Learning streaks** - daily activity streak tracking per user
- **Resizable chapter sidebar** - collapsible and draggable sidebar with chapter tree navigation
- **JWT authentication** - cookie-based auth with access and refresh tokens, enforced globally via middleware
- **Fully responsive** - works on mobile, tablet, and desktop

---

## Company Knowledge Platform (Confluence + Jira)

Connect your Atlassian workspace once and Openship ingests your **Confluence** pages and **Jira** issues into a single searchable, AI-queryable knowledge base. Three surfaces share one connection, one ingestion pipeline, and one set of tables.

### Connections - one Atlassian OAuth, two products
- **Single OAuth 2.0 (3LO) connection** grants both Confluence and Jira; company-level encrypted tokens with auto-refresh
- **Whole-workspace RAG ingestion** - read every page/issue → chunk → embed → store as pgvector vectors, with a live progress UI (reading → scanning → embedding)
- **Local embeddings** via `fastembed` (`BAAI/bge-small-en-v1.5`, 384-dim) - **no API key, no quota, no per-token cost**; runs on CPU inside the backend
- **Resilient at scale** (proven on a **133k-issue** tenant) - honors Atlassian rate limits (`Retry-After`), refreshes the OAuth token mid-run, and streams per project so memory stays bounded; resumable and idempotent
- **One-click Sync** - a single **Sync** does everything in one read: adds new items, updates changed ones, and removes items deleted upstream (and restores reappearing ones). A running sync can be **cancelled** cleanly - partial progress is saved and resumable
- **Freshness** - Confluence + Jira **webhooks** re-embed changed items instantly, between full syncs
- **Multi-tenant** - every doc is company-scoped; a connector identity check ensures you connect with your own company's Atlassian account

### Onboarding - role-based, grounded in your docs
- Generate a **7-day onboarding plan** for a role, grounded only in the company's Confluence
- **On-demand per-day content** (headings, code, tables, mermaid diagrams) plus an end-of-onboarding **quiz**; shareable public view

### Knowledge chat - ask across Confluence + Jira
- ChatGPT-style, multi-turn, persistent chat that answers **only** from your indexed docs, with **source-linked citations** (deep links to the Jira issue / Confluence page)
- **Hybrid retrieval** - semantic (pgvector cosine) **+** lexical word/phrase matching, so literal things like names and issue keys (`AR-2847`) are found, not just paraphrases; full-name phrase matching keeps "Yogesh Kisslay" from colliding with a different "Yogesh"
- **People analytics** - "what is X working on", "who reported the most", "who did more, X or Y" answered from **exact database lookups** (counts, complete lists, leaderboards), with strict Jira role discipline (assignee vs reporter vs commenter)
- **Anti-hallucination** - strict grounding, and any URL the model invents that isn't in the retrieved source is stripped

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn |
| AI | Anthropic, OpenAI, Google Gemini, Mistral (via `instructor`) |
| ML | Bayesian Knowledge Tracing, Thompson Sampling, Ebbinghaus Forgetting Curve |
| Knowledge / RAG | pgvector, `fastembed` local embeddings (`BAAI/bge-small-en-v1.5`, 384-dim) |
| Integrations | Atlassian OAuth 2.0 (Confluence + Jira), webhooks |
| Database | PostgreSQL, SQLModel ORM, Alembic migrations |
| Frontend | React 18 + TypeScript + Vite |
| UI Components | shadcn/ui, Radix UI, Tailwind CSS |
| State | Zustand |
| Auth | JWT (httponly cookies) + bcrypt |
| Routing | React Router v6 |

---

## Getting Started

Only the **database** runs in Docker (PostgreSQL + pgvector). The API (FastAPI) and UI (React/Vite) run directly on your machine. LLM API keys are added later in the UI - never in `.env`.

### macOS

**Install first:** [Git](https://git-scm.com), [Homebrew](https://brew.sh), and [Docker Desktop](https://www.docker.com/products/docker-desktop/) (installed and running). Python and Node are auto-installed via Homebrew if missing.

**Automatic (recommended):**

```bash
git clone https://github.com/locus-taxy/openship.git
cd openship
make setup     # starts the DB, installs deps, writes .env, runs migrations
make dev       # starts API (:3005) + UI (:5173) in two terminals
```

Then open http://localhost:5173, sign up, and add your LLM API key in Settings.

**Manual (no Docker):** use a Postgres that has **pgvector** - the simplest is [Postgres.app](https://postgresapp.com) (it bundles pgvector).

```bash
createdb openship
# Create .env in the repo root (see Environment Variables below):
#   DATABASE_URL=postgresql+psycopg2://<user>@localhost:5432/openship
#   JWT_SECRET_KEY=<32+ random chars>
#   LLM_ENCRYPTION_KEY=<python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())">
#   RUN_MIGRATIONS_ON_STARTUP=true
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt -r requirements-test.txt
cd ui && npm install && cd ..
.venv/bin/alembic upgrade head
# run in two shells:
.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 3005
cd ui && npm run dev
```

### Windows

**Install first:** [Git](https://git-scm.com/download/win) and [Docker Desktop](https://www.docker.com/products/docker-desktop/) (installed and running). Python and Node are auto-installed via **winget** (built into Windows 10/11).

**Automatic (recommended):**

```powershell
git clone https://github.com/locus-taxy/openship.git
cd openship
scripts\setup.cmd    # starts the DB, installs deps, writes .env, runs migrations
scripts\dev.cmd      # starts API (:3005) + UI (:5173)
```

(You can also double-click `scripts\setup.cmd` then `scripts\dev.cmd` in File Explorer.)

**Manual:** on Windows the database uses **Docker** (there is no Postgres.app):

```powershell
docker compose up -d db
# Create .env in the repo root:
#   DATABASE_URL=postgresql+psycopg2://openship:openship@localhost:5432/openship
#   JWT_SECRET_KEY=<32+ random chars>
#   LLM_ENCRYPTION_KEY=<a Fernet key>
#   RUN_MIGRATIONS_ON_STARTUP=true
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt -r requirements-dev.txt -r requirements-test.txt
cd ui; npm install; cd ..
.venv\Scripts\alembic.exe upgrade head
# run in two shells:
.venv\Scripts\uvicorn.exe main:app --reload --host 0.0.0.0 --port 3005
cd ui; npm run dev
```

Full walkthrough + troubleshooting: **[docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md)**.

### Available commands

| Command | Description |
|---------|-------------|
| `make setup` (macOS) / `scripts\setup.cmd` (Windows) | One-time: start DB, venv + deps, `.env`, migrations |
| `make dev` (macOS) / `scripts\dev.cmd` (Windows) | Start the DB, then API + UI |
| `make run-api` | FastAPI only, hot reload on `:3005` |
| `make run-ui` | Vite dev server only on `:5173` |
| `make db-up` / `make db-down` | Start / stop the PostgreSQL + pgvector container (Docker) |
| `make format` | Auto-format Python with Black via pre-commit |
| `make format-check` | CI-style format check |
| `make install` | Alias for `make setup` |

---

## Environment Variables

`make setup` / `scripts\setup.cmd` generate `.env` automatically. For a manual setup, create `.env` yourself with at least:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | SQLAlchemy connection string (PostgreSQL) |
| `JWT_SECRET_KEY` | Yes | Random string, minimum 32 characters |
| `LLM_ENCRYPTION_KEY` | Yes | Fernet key for encrypting stored API keys. Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `RUN_MIGRATIONS_ON_STARTUP` | No | Run `alembic upgrade head` on startup (default: `true`) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | Access token lifetime (default: `2`) |
| `JWT_REFRESH_TOKEN_EXPIRE_HOURS` | No | Refresh token lifetime (default: `7`) |
| `ATLASSIAN_CLIENT_ID` / `ATLASSIAN_CLIENT_SECRET` / `ATLASSIAN_REDIRECT_URI` | For Connections | Atlassian OAuth app credentials - required to connect Confluence/Jira |
| `ATLASSIAN_OAUTH_SCOPES` | No | Override the default Confluence + Jira read scopes (`offline_access`, `read:me`) |
| `EMBEDDING_MODEL` | No | Local embedding model (default: `BAAI/bge-small-en-v1.5`, 384-dim) |
| `CONFLUENCE_WEBHOOK_SECRET` / `JIRA_WEBHOOK_SECRET` | No | Enable the respective webhook endpoints for instant freshness |

> **Atlassian connections** are optional - the learning platform works without them. Set the `ATLASSIAN_*` vars only if you want the Confluence/Jira knowledge platform. Embeddings run locally, so **no embedding API key is ever needed.**

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
