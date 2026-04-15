# Openship

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

Openship is an AI-powered personalized learning platform. Give it a skill, your experience level, and how much time you have — it builds a structured Month → Week → Day curriculum and delivers daily AI-written lessons directly to your inbox.

---

## How it works

1. **Onboard** — provide your skill goal, experience level, and available time commitment
2. **Generate** — Gemini AI creates a structured Month → Week → Day syllabus tailored to you
3. **Learn** — receive a daily newsletter with AI-written, educator-style content for that day's topic

---

## Features

- **Personalized syllabus generation** — Google Gemini produces a structured 3-level plan (month / week / day) in JSON
- **Daily newsletter delivery** — AI-written lesson content sent to your inbox each day via SMTP
- **Background pre-generation** — content for upcoming days is generated ahead of time so delivery never blocks on the AI
- **Progress tracking** — per-skill task completion status persisted in the database
- **JWT authentication** — cookie-based auth with access and refresh tokens, enforced globally
- **Rate limiting** — slowapi-based rate limits protect all API endpoints

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn |
| AI | Google Gemini API (structured JSON output) |
| Database | PostgreSQL via SQLModel + Alembic |
| Frontend | React 18 + TypeScript + Vite |
| UI components | Radix UI + Tailwind CSS |
| Auth | JWT (httponly cookies) + bcrypt |
| Email | SMTP (configurable relay) |

---

## Getting Started

### Prerequisites

- Python 3.9+
- Node.js 18+ and npm
- PostgreSQL (or SQLite for local dev)

### Quick start

```bash
git clone https://github.com/locus-taxy/openship.git
cd openship
make setup          # creates .venv, installs deps, sets up Husky hooks
cp .env.example .env  # then fill in required values (see below)
make dev            # API on :3005, UI on :5173
```

For a full walkthrough including PostgreSQL setup, migrations, and troubleshooting see **[docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md)**.

---

## Environment Variables

Copy `.env.example` to `.env` and set at minimum:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | SQLAlchemy connection string — PostgreSQL or SQLite |
| `GEMINI_API_KEY` | Yes | Google Gemini API key |
| `JWT_SECRET_KEY` | Yes | Random string, minimum 32 characters |
| `RUN_MIGRATIONS_ON_STARTUP` | No | Run `alembic upgrade head` on startup (default: `true`) |
| `SENTRY_DSN` | No | Sentry DSN for error tracking |
| `SMTP_HOST` | No | SMTP relay host for newsletter delivery |
| `SMTP_PORT` | No | SMTP port (default: `587`) |
| `SMTP_FROM_EMAIL` | No | Sender address for outbound email |
| `SMTP_USER` | No | SMTP auth username |
| `SMTP_PASSWORD` | No | SMTP auth password |
| `SMTP_USE_TLS` | No | Enable STARTTLS (default: `true`) |

---

## API Reference

Full documentation: **[docs/api.md](docs/api.md)**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/signup` | Create an account |
| `POST` | `/auth/login` | Log in, receive access + refresh cookies |
| `POST` | `/auth/refresh` | Refresh an expired access token |
| `POST` | `/auth/logout` | Clear session cookies |
| `POST` | `/subscribe` | Register a skill to learn |
| `POST` | `/generate-syllabus` | Generate Month → Week → Day plan for a skill |
| `POST` | `/generate-content` | Pre-generate newsletter content for next 10 days |
| `POST` | `/issue-newsletters` | Send today's lesson to all active subscribers |

Interactive docs (Swagger UI) are available at `http://localhost:3005/docs` when running locally.

---

## Project Structure

```
openship/
├── controllers/     # HTTP-layer logic (auth, syllabus, content, newsletter)
├── services/        # Business logic and AI integration (Gemini, JWT, email)
├── models/          # SQLModel table definitions
├── schemas/         # Pydantic request/response schemas
├── routes/          # FastAPI router registration
├── middleware/       # Global auth middleware
├── alembic/         # Database migration scripts
├── docs/            # Local setup, API reference, architecture notes
├── ui/              # React + TypeScript frontend (Vite)
└── main.py          # Application entry point
```

---

## Contributing

Contributions are welcome. Please read **[CONTRIBUTING.md](CONTRIBUTING.md)** for:

- Development setup
- Code style (Black for Python, ESLint for TypeScript)
- Branch and commit conventions
- Pull request process

For bugs, use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).
For feature ideas, use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).

---

## Security

**Do not open public issues for security vulnerabilities.**

See **[SECURITY.md](SECURITY.md)** for the responsible disclosure policy and contact information.

---

## License

Openship is released under the [MIT License](LICENSE).

Third-party dependency attributions are listed in [NOTICE](NOTICE).
