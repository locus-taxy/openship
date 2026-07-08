# Openship — local setup

Only the **database** runs in Docker (Postgres + pgvector). The API and UI run locally.

---

## Mac

### Automatic

Install first: **Git**, **Homebrew**, **Docker Desktop** (running).

```bash
git clone <repo-url>
cd openship
make setup     # one-time: DB + deps + migrations
make dev       # start API (:3005) + UI (:5173)
```

Other commands: `make run-api`, `make run-ui`, `make db-up`, `make db-down`.

### Manual

**1. Start the database.** Install and open **Postgres.app** — it includes pgvector and runs PostgreSQL on `localhost:5432`.

**2. Create a database:**

```bash
createdb your_db_name
```

**3. Create `.env`** in the repo root, using your Postgres user/password:

```bash
DATABASE_URL=postgresql+psycopg2://your_user:your_password@localhost:5432/your_db_name
RUN_MIGRATIONS_ON_STARTUP=true
JWT_SECRET_KEY=<32+ random chars>
LLM_ENCRYPTION_KEY=<python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())">
```

> Postgres.app's default user is your Mac username with **no password**, so it's often just:
> `postgresql+psycopg2://your_user@localhost:5432/your_db_name`

**4. Open the openship project and install, migrate, and run:**

```bash
cd openship
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt -r requirements-test.txt
cd ui && npm install && cd ..
.venv/bin/alembic upgrade head

# run (two terminals):
.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 3005
cd ui && npm run dev
```

**Prefer Docker for the database instead of Postgres.app?** Run `docker compose up -d db`. It creates Postgres + pgvector with a **default config** (user `openship`, password `openship`, db `openship`), so your `DATABASE_URL` is:

```bash
DATABASE_URL=postgresql+psycopg2://openship:openship@localhost:5432/openship
```

---

## Windows

Uses **Docker** for the database (both ways).

### Automatic

**Install first:**

| Prerequisite | Get it |
| --- | --- |
| **Git** | https://git-scm.com/download/win |
| **Docker Desktop** (installed and running) | https://www.docker.com/products/docker-desktop/ |

Python and Node are auto-installed via **winget** (built into Windows 10/11) if missing.

```powershell
git clone <repo-url>
cd openship
scripts\setup.cmd    # one-time: DB + deps + migrations
scripts\dev.cmd      # start API (:3005) + UI (:5173)
```

(You can also just double-click `scripts\setup.cmd` then `scripts\dev.cmd` in File Explorer.)

### Manual

```powershell
docker compose up -d db      # Postgres + pgvector

# .env in repo root (same keys as Mac, DATABASE_URL uses the Docker DB):
#   DATABASE_URL=postgresql+psycopg2://openship:openship@localhost:5432/openship
#   RUN_MIGRATIONS_ON_STARTUP=true
#   JWT_SECRET_KEY=<32+ random chars>
#   LLM_ENCRYPTION_KEY=<a Fernet key>

python -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt -r requirements-dev.txt -r requirements-test.txt
cd ui; npm install; cd ..
.venv\Scripts\alembic.exe upgrade head

# run (two terminals):
.venv\Scripts\uvicorn.exe main:app --reload --host 0.0.0.0 --port 3005
cd ui; npm run dev
```

---

## Troubleshooting

- **"Docker is required / not running"** — Install/start Docker Desktop, then re-run.
- **Port 5432 in use** — Another Postgres is running on it; stop it first.
- **Ports 3005 / 5173 in use** — Change them in `Makefile` (`run-api`) or `ui/vite.config.ts`.
