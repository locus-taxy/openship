# Openship — local setup guide

This guide replaces manual copy-paste setup. **Use the Makefile** so backend, frontend, and Git hooks are configured the same way for everyone.

## Prerequisites

- **Python 3.9+** (`python3` on PATH)
- **Node.js 18+** and **npm** (for the UI and Husky)
- **Git** (clone the repo; Husky configures hooks from the project root)
- **PostgreSQL** (or another DB supported by SQLAlchemy) if you are not using the default from `.env.example`

## One-time setup

From the repository root:

```bash
make setup
```

This does the following automatically:

1. Creates `.env` from `.env.example` if `.env` is missing (then edit secrets and `DATABASE_URL`).
2. Creates a Python virtual environment at `.venv` and installs **runtime** deps (`requirements.txt`) and **dev** deps (`requirements-dev.txt`, including Black and pre-commit).
3. Runs **`npm install`** in `ui/` for the Vite/React frontend.
4. Runs **`npm install`** at the repo root so **Husky** runs its `prepare` script and wires Git to use `.husky/` as the hooks directory.

After `make setup`, open `.env` and set at least:

- `DATABASE_URL` — PostgreSQL (or your chosen database) connection string
- `GEMINI_API_KEY` — Google Gemini

Outbound email is not configured in this branch (SMTP will be added later); no email-service API keys are required in `.env`.

If you use PostgreSQL 15+ and migrations fail on the `public` schema, see [postgres-public-schema.md](./postgres-public-schema.md).

## Run API and frontend together

```bash
make dev
```

This starts the **API first** (so Alembic migrations and the app are ready), **waits until** `http://127.0.0.1:3005` responds, then starts the UI:

- **API:** FastAPI with Uvicorn on **http://127.0.0.1:3005** (with reload)
- **UI:** Vite dev server (default **http://127.0.0.1:5173**)

### Run services separately

```bash
make run-api   # backend only
make run-ui    # frontend only
```

## Migrations

If `RUN_MIGRATIONS_ON_STARTUP` is `true` in `.env` (default in `.env.example`), the API runs `alembic upgrade head` once on startup. You can also run migrations manually:

```bash
.venv/bin/python run_migrations.py
```

## Python formatting and pre-commit

Formatting is enforced **before each commit**:

1. **Husky** runs `.husky/pre-commit` when you `git commit`.
2. That script runs **`pre-commit`**, which applies the hooks in `.pre-commit-config.yaml` (currently **Black**, aligned with `pyproject.toml`).

You need **`make setup`** first so `.venv/bin/pre-commit` exists. If you skip root `npm install` (e.g. no `.git` directory), hooks are not configured; clone the repo and run `make setup` for the full flow.

To format the whole tree without committing:

```bash
make format
```

For CI or a strict check (fails if anything is not Black-clean, without the second pass):

```bash
make format-check
```

## Makefile reference

| Target        | Purpose                                      |
| ------------- | -------------------------------------------- |
| `make help`   | Short usage summary                          |
| `make setup`  | Venv, Python deps, UI deps, Husky            |
| `make install`| Same as `make setup`                         |
| `make dev`    | API first (wait for :3005), then Vite UI     |
| `make run-api`| Backend only                                 |
| `make run-ui` | Frontend only                                |
| `make format` | Black via pre-commit (all files)             |
| `make format-check` | Black check; exit non-zero if dirty    |

## Troubleshooting

- **`openship: missing .venv/bin/pre-commit`** — Run `make setup` from the repo root.
- **Husky did not run** — Ensure you cloned with Git and that `npm install` ran at the repo root (part of `make setup`).
- **Port in use** — Change the Uvicorn port in `Makefile` (`run-api`) or the Vite config in `ui/` if 3005 / 5173 conflict with other apps.
- **`permission denied for schema public` (Alembic)** — PostgreSQL 15+ limits `public`; grant `USAGE, CREATE` to your app user. See [postgres-public-schema.md](./postgres-public-schema.md).
- **`email-validator is not installed` / `ImportError` on auth routes** — Run `pip install -r requirements.txt` (includes `email-validator` for Pydantic `EmailStr`).
