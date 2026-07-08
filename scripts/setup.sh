#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv"

BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
RESET="\033[0m"

info()    { echo -e "${CYAN}${BOLD}[setup]${RESET} $*"; }
success() { echo -e "${GREEN}${BOLD}[✓]${RESET} $*"; }
warn()    { echo -e "${YELLOW}${BOLD}[!]${RESET} $*"; }
error()   { echo -e "${RED}${BOLD}[✗]${RESET} $*"; exit 1; }

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║     Openship Interactive Setup       ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════╝${RESET}"
echo ""

# ── Step 0: Python 3.14 ────────────────────────────────────────────────────
info "Step 1/6 — Python version"

PYTHON_BIN=""
for candidate in python3.14 python3.13 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        ver=$("$candidate" -c "import sys; print(sys.version_info[:2])")
        if [ "$ver" = "(3, 14)" ] || [ "$ver" = "(3, 13)" ]; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    warn "Python 3.13+ not found."
    if command -v brew >/dev/null 2>&1; then
        echo -ne "${BOLD}Install Python 3.14 via Homebrew?${RESET} [Y/n]: "
        read -r ans
        lower_ans=$(printf '%s' "$ans" | tr '[:upper:]' '[:lower:]')
        if [ "$lower_ans" != "n" ]; then
            brew install python@3.14
            PYTHON_BIN="$(brew --prefix)/bin/python3.14"
            success "Python 3.14 installed."
        else
            error "Python 3.13 or 3.14 is required. Install it manually and re-run."
        fi
    else
        error "Python 3.13+ required. Download from https://www.python.org/downloads/"
    fi
else
    success "Python found: $($PYTHON_BIN --version)"
fi

# ── Step 1: Database (Docker + pgvector) ─────────────────────────────────────
info "Step 2/6 — Database"

DB_HOST="localhost"
DB_PORT="5432"
DB_NAME="openship"
DB_USER="openship"
DB_PASS="openship"
DB_EXISTS=false

# Docker is a required prerequisite (we do NOT auto-install it).
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    error "Docker is required. Install Docker Desktop, start it, then re-run 'make setup'.
       Download: https://www.docker.com/products/docker-desktop/"
fi

# If Docker is installed but not running, try to start it, then wait briefly.
if ! docker info >/dev/null 2>&1; then
    info "Docker isn't running — trying to start Docker Desktop..."
    open -a Docker 2>/dev/null || true
    i=0
    until docker info >/dev/null 2>&1; do
        i=$((i + 1))
        [ "$i" -gt 60 ] && error "Docker Desktop isn't running. Start it, then re-run 'make setup'."
        sleep 2
    done
fi

info "Starting PostgreSQL + pgvector via Docker..."
docker compose -f "$ROOT/docker-compose.yml" up -d db
info "Waiting for the database to accept connections..."
i=0
until docker compose -f "$ROOT/docker-compose.yml" exec -T db pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; do
    i=$((i + 1))
    [ "$i" -gt 60 ] && error "Database did not become ready in time."
    sleep 1
done
success "Database ready (Postgres 16 + pgvector) on ${DB_HOST}:${DB_PORT}."
DATABASE_URL="postgresql+psycopg2://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
[ -f "$ROOT/.env" ] && DB_EXISTS=true  # preserve existing secrets on a re-run

# ── Steps 3 & 4: Secrets + .env ─────────────────────────────────────────────
if [ "$DB_EXISTS" = true ] && [ -f "$ROOT/.env" ]; then
    info "Step 3/6 — Skipping secrets & .env (database and .env already exist)"
else
    echo ""
    info "Step 3/6 — Generating secrets"

    JWT_SECRET=$("$PYTHON_BIN" -c "import secrets; print(secrets.token_hex(32))")
    success "JWT secret key auto-generated."

    LLM_ENCRYPTION_KEY=$("$PYTHON_BIN" -c "
try:
    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())
except ImportError:
    import secrets, base64
    print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
")
    success "LLM encryption key auto-generated."

    echo ""
    info "Step 4/6 — Writing .env"

    cat > "$ROOT/.env" <<EOF
DATABASE_URL=${DATABASE_URL}

LLM_ENCRYPTION_KEY=${LLM_ENCRYPTION_KEY}

RUN_MIGRATIONS_ON_STARTUP=true

JWT_SECRET_KEY=${JWT_SECRET}
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=2
JWT_REFRESH_TOKEN_EXPIRE_HOURS=7

SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_FROM_NAME=Openship
SMTP_USE_TLS=true
SMTP_USE_SSL=false
SMTP_TIMEOUT_SECONDS=20
EOF

    chmod 600 "$ROOT/.env"
    success ".env written."
fi

# ── Step 5: Install deps + run migrations ───────────────────────────────────
echo ""
info "Step 5/6 — Installing dependencies & running migrations"

"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$ROOT/requirements.txt" -r "$ROOT/requirements-dev.txt" -r "$ROOT/requirements-test.txt" -q
success "Python dependencies installed."

info "Pre-downloading the local embedding model (one-time, ~a few hundred MB)..."
if "$VENV/bin/python" "$ROOT/scripts/warm_embeddings.py"; then
    success "Embedding model ready — first ingest won't wait on a download."
else
    warn "Could not pre-download the embedding model; it will download on first ingest instead."
fi

if ! command -v npm >/dev/null 2>&1; then
    warn "Node.js not found (needed for the UI)."
    if command -v brew >/dev/null 2>&1; then
        info "Installing Node.js..."
        brew install node >/dev/null 2>&1 \
            && success "Node.js installed." \
            || error "Failed to install Node.js. Install it from https://nodejs.org and re-run."
    else
        error "Node.js is required for the UI. Install it from https://nodejs.org and re-run."
    fi
fi

cd "$ROOT/ui" && npm install --silent
success "Node dependencies installed."

if [ -d "$ROOT/.git" ]; then
    cd "$ROOT" && npm install --silent
fi

info "Step 6/6 — Running database migrations..."

# The Docker database is always a clean, known Postgres, so we migrate straight to
# head. The first migration enables pgvector automatically (CREATE EXTENSION).
cd "$ROOT" && "$VENV/bin/alembic" upgrade head
success "Migrations applied."

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║        Setup complete!               ║${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""
echo -e "  Run ${BOLD}make dev${RESET} to start the app."
echo ""
