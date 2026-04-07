# Openship

Openship is an AI-powered personalized learning platform that generates a custom curriculum for any skill and delivers daily learning content directly to your inbox.

## How it works

1. **Onboard** — provide your skill goal, experience level, and available time commitment
2. **Generate** — Gemini AI creates a structured Month → Week → Day learning syllabus tailored to you
3. **Learn** — receive a daily newsletter with AI-written, beginner-friendly content for that day's topic

## Features

- Personalized syllabus generation using Google Gemini (structured 3-level hierarchy: month/week/day)
- Automated daily newsletter delivery via email
- Content generation with HTML-formatted, educator-style writing
- Progress tracking per skill with task completion status
- Background content pre-generation for upcoming days

## Tech Stack

- **FastAPI** — async REST API backend
- **Google Gemini API** — syllabus and content generation (structured JSON output)
- **PostgreSQL** (or SQLAlchemy-supported DB) — user, skill, and task storage

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/onboard-user` | Register a user and kick off syllabus + content generation |
| `POST` | `/issue-newsletters` | Send today's learning content to all active users |
| `POST` | `/generate-content` | Pre-generate content for newsletter |

## Getting Started

Use the **Makefile** for setup, hooks, and running API + UI together. Full steps: [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md).

```bash
make setup   # venv, Python + UI deps, Husky (pre-commit → Black on commit)
make dev     # API first (wait until :3005 is up), then Vite UI
```

Manual alternative: install `requirements.txt` and `requirements-dev.txt`, copy `.env.example` to `.env`, then `uvicorn main:app --reload --port 3005` from the project root (with venv activated).

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | SQLAlchemy URL (required); PostgreSQL example in `.env.example` |
| `RUN_MIGRATIONS_ON_STARTUP` | If `true` (default), runs `alembic upgrade head` before serving |
| `GEMINI_API_KEY` | Google Gemini API key |
| `SENTRY_DSN` | (Optional) Sentry DSN for error tracking |

Outbound email uses SMTP in a planned follow-up; there are no third-party email API env vars in this branch.
