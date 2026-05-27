# Openship: The Open-Source AI Learning Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

## What Is Openship?

The internet is an ocean — vast, deep, and full of treasure. But oceans without a map and a vessel are just water. Most learners today are treading water: endless browser tabs, half-finished tutorials, YouTube rabbit holes, blog posts and scattered chats with LLMs that lead nowhere. The knowledge is out there, but there's no ship to carry you through it with purpose.

That's where **Openship** comes in.

Think of Openship as your personal vessel on the sea of learning. You choose the destination — the skill you want to master. You set the pace — how many days, how many hours. Openship then charts your course: a structured **Month → Week → Day** route through the waters, with AI-written lessons waiting at every waypoint. And unlike a static course, Openship watches how you're doing — and quietly adjusts the route as you sail.

Built by the team at **Locus**, Openship is a fully open-source, AI-powered personalized learning platform.

---

## Demo

https://github.com/user-attachments/assets/cd3fc567-a654-41c8-a33d-fb354fd51b38

---

## How it works

1. **Configure** — add your LLM provider API key (Anthropic, OpenAI, Google Gemini, or Mistral) in Settings
2. **Enroll** — choose a skill, set your duration and daily time commitment
3. **Generate** — your AI model creates a structured syllabus organized by month, week, and day; Week 1 is unlocked immediately with a pre-generated quiz
4. **Learn** — open any chapter, generate its content on demand, and mark days complete as you go
5. **Weekly quiz** — after finishing all chapters in a week, take an AI-generated quiz; your score determines how the next week is planned — weak topics get extra focus, forgotten ones get spaced repetition
6. **Adaptive next week** — the platform generates Week 2+ on demand, personalised using your quiz results and mastery data; the difficulty and topic mix shift based on what you actually know
7. **Final quiz** — once all weeks are complete, a final quiz draws from the topics you struggled with most across the whole course; pass it to reach 100%
8. **Track** — the analytics dashboard shows your overall progress across all courses

---

## Why Openship Stands Out

### 1. Bring Your Own AI — No Lock-in

Unlike most AI tools that hide their model and charge you a subscription, Openship lets you plug in your own API key for whichever provider you prefer. Switch from Claude to GPT to Gemini mid-journey if you want. You own your experience.

### 2. Structure That Actually Fits Your Life

No more "complete this 40-hour course at your own pace" ambiguity. You tell Openship how many days you have and how many hours per day — it builds a plan that respects your constraints. The curriculum isn't generic; it's shaped around your schedule.

### 3. Adaptive Learning That Gets Smarter As You Go

Openship uses three ML components working together to personalise your experience as you progress:

- **Bayesian Knowledge Tracing (BKT)** — tracks your per-topic mastery probability after every quiz answer. Topics where you score low are automatically woven into the next week's plan.
- **Forgetting Curve** — identifies topics you haven't seen recently and schedules them for spaced repetition before you forget them.
- **Thompson Sampling Bandit** — picks a content style for each week (`Visual-Heavy`, `Example-Heavy`, `Diagram-Heavy`, or `Story-Driven`) and updates its choice based on your quiz scores — if visual content correlated with better results, it learns to use it more.

The result: each week is a different plan, not a copy-paste of the template.

### 4. On-Demand Lessons, Not Static Content

Content isn't pre-written and locked. Each chapter is generated when you open it — meaning the AI writes specifically for that lesson in the context of your full syllabus. Code examples include syntax highlighting. Tables render cleanly. It reads like a textbook written for you, not for the median student.

### 5. Real Progress Tracking

Mark chapters complete, watch your progress bar move, check your analytics dashboard across all active courses. Completion rates, hours planned, tasks remaining — it's all there. This is the accountability layer that most self-study methods completely lack.

### 6. Share What You Build

Generated a great syllabus for learning Rust in 30 days or becoming a data analyst in 3 months? Share it publicly with one click. Other learners can view your syllabus without even needing an account.

### 7. Your API Keys Stay Yours

Openship stores LLM API keys with partial encryption — the key prefix is stored in plaintext while only the sensitive suffix is encrypted using a server-side Fernet key. A database breach alone isn't enough to reconstruct a full key. Security was a first-class consideration, not an afterthought.

---

## Who Should Use and Contribute to Openship?

**Learners** — anyone building a new skill on their own time. Developers switching stacks, students filling gaps, professionals upskilling, curious people with limited hours but real ambition.

**Developers** — the stack is approachable (FastAPI, React, TypeScript) and the project structure is clean. Whether you want to add a new LLM provider, improve the analytics dashboard, build better mobile UX, or add export features, there's meaningful work to do.

**Teams and educators** — Openship's architecture is designed to extend. A team learning infrastructure, a bootcamp building structured paths, an educator who wants to generate and share custom curricula — the foundation is already here.

---

## Why Star and Contribute?

Open source only works when people show up. Openship is early enough that individual contributions have outsized impact. Your PR doesn't get lost in a 500-issue backlog — it shapes the direction of the project.

Here's what's at stake if this grows:

- A free, self-hostable alternative to expensive e-learning subscriptions
- A platform that respects user privacy (your keys, your data, your server)
- A community-built learning engine that any AI provider can plug into
- A reference implementation of a clean FastAPI + React application with real ML components that developers can learn from

Starring the repo signals to other developers that this is worth their attention. Contributing — even one good PR — moves the project forward in a way that benefits every future learner.

---

## Get Started in Three Commands

```bash
git clone https://github.com/locus-taxy/openship.git
cd openship
make setup
```

Add your database URL and secrets to `.env`, run `make dev`, open your browser, add your LLM API key in Settings, and enroll in your first skill.

That's it.

---

## Features

### Core learning loop
- **Multi-provider LLM support** — bring your own API key for Anthropic (Claude), OpenAI (GPT), Google Gemini, or Mistral; switch providers and models at any time from the UI
- **Personalized syllabus generation** — AI produces a structured 3-level plan (month / week / day) tailored to the skill and your schedule
- **On-demand chapter content** — rich AI-written lessons generated per chapter with syntax-highlighted code blocks, diagrams, tables, bullet lists, and examples
- **Progressive week unlock** — only Week 1 is generated upfront; subsequent weeks are generated on demand after the previous week's quiz, personalised to your results

### Adaptive ML engine
- **Bayesian Knowledge Tracing** — per-topic mastery model updated after every quiz submission; weak topics fed into the next week's plan
- **Forgetting curve** — spaced repetition scheduling based on time since last exposure; forgotten topics resurface automatically
- **Thompson Sampling bandit** — picks a chapter content style per week (`Visual-Heavy`, `Example-Heavy`, `Diagram-Heavy`, `Story-Driven`) and updates from quiz feedback; exploits styles that correlate with better scores
- **Remediation planning** — quiz score below threshold triggers extra review days at the start of the next week, proportional to how many topics need reinforcement

### Quizzes
- **Weekly quizzes** — AI-generated 5-question quiz per week, covering that week's topics; unlocks the next week on completion
- **Final quiz** — personalised to the topics you struggled with most across the whole course; appears after all weeks complete; pass it to reach 100%
- **Quiz variant pools** — each question is generated in multiple variants; a different variant is sampled per attempt, so retakes feel fresh
- **Score history** — every attempt recorded with timestamp and score; best score tracked per quiz

### Progress and analytics
- **Progress tracking** — mark chapters complete; progress bar accounts for chapters and quiz pass
- **Analytics dashboard** — overview of all courses: completion rates, in-progress courses, hours planned, tasks remaining

### Other
- **Shareable syllabi** — generate a public link to share any syllabus with others (no account required to view)
- **Course management** — delete any enrolled course (removes all chapters, progress, quizzes, and attempts)
- **Resizable chapter sidebar** — collapsible and draggable sidebar with chapter tree navigation
- **JWT authentication** — cookie-based auth with access and refresh tokens, enforced globally via middleware
- **Fully responsive** — works on mobile, tablet, and desktop

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn |
| AI | Anthropic, OpenAI, Google Gemini, Mistral (via `instructor`) |
| ML | Bayesian Knowledge Tracing · Thompson Sampling · Ebbinghaus Forgetting Curve |
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
