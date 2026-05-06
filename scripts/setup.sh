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
info "Step 0/5 — Python version"

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

# ── Step 1: PostgreSQL ──────────────────────────────────────────────────────
info "Step 1/6 — PostgreSQL"

if ! command -v psql >/dev/null 2>&1; then
    warn "PostgreSQL not found."
    if command -v brew >/dev/null 2>&1; then
        echo -ne "${BOLD}Install PostgreSQL 14 via Homebrew?${RESET} [Y/n]: "
        read -r ans
        lower_ans=$(printf '%s' "$ans" | tr '[:upper:]' '[:lower:]')
        if [ "$lower_ans" != "n" ]; then
            brew install postgresql@14
            brew services start postgresql@14
            export PATH="$(brew --prefix postgresql@14)/bin:$PATH"
            success "PostgreSQL installed and started."
        else
            error "PostgreSQL is required. Install it manually and re-run setup."
        fi
    else
        error "Homebrew not found. Install PostgreSQL from https://www.postgresql.org/download/ then re-run."
    fi
else
    success "PostgreSQL found: $(psql --version)"
    if ! pg_isready -q 2>/dev/null; then
        warn "PostgreSQL is not running. Starting..."
        brew services start postgresql@14 2>/dev/null || warn "Could not auto-start. Start PostgreSQL manually if DB connection fails."
    fi
fi

# ── Step 2: Database setup ──────────────────────────────────────────────────
DB_HOST="localhost"
DB_PORT="5432"
DB_USER="$(whoami)"

DB_EXISTS=false

# If 'openship' already exists, skip all prompts and leave .env untouched
if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -lqt 2>/dev/null | cut -d'|' -f1 | grep -qw "openship"; then
    DB_NAME="openship"
    DB_EXISTS=true
    success "Database 'openship' already exists — skipping database setup."
else
    echo ""
    echo -e "${BOLD} Database setup${RESET}"
    echo -ne " Enter Database name: "
    read -r DB_NAME
    DB_NAME="${DB_NAME:-openship}"

    echo -ne " Enter Database user: "
    read -r input_user
    DB_USER="${input_user:-$(whoami)}"

    echo -ne " Enter Database password (leave blank for none): "
    read -rs DB_PASS
    echo ""

    if [ -n "$DB_PASS" ]; then
        export PGPASSWORD="$DB_PASS"
    fi

    info "Creating database '$DB_NAME'..."
    if createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"; then
        success "Database '$DB_NAME' created."
    else
        error "Failed to create database. Check your PostgreSQL connection."
    fi

    if [ -n "$DB_PASS" ]; then
        ENCODED_PASS=$("$PYTHON_BIN" -c "import sys, urllib.parse; print(urllib.parse.quote(sys.stdin.read().rstrip('\n'), safe=''))" <<< "$DB_PASS")
        DATABASE_URL="postgresql+psycopg2://${DB_USER}:${ENCODED_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
    else
        DATABASE_URL="postgresql+psycopg2://${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
    fi
fi

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
"$VENV/bin/pip" install -r "$ROOT/requirements.txt" -r "$ROOT/requirements-dev.txt" -q
success "Python dependencies installed."

cd "$ROOT/ui" && npm install --silent
success "Node dependencies installed."

if [ -d "$ROOT/.git" ]; then
    cd "$ROOT" && npm install --silent
fi

info "Step 6/6 — Running database migrations..."

# If the DB points to a revision this branch doesn't know about, stamp it to
# the latest known revision so upgrade head can proceed cleanly.
CURRENT_REV=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -t -c "SELECT version_num FROM alembic_version LIMIT 1;" 2>/dev/null | tr -d ' \n')

if [ -n "$CURRENT_REV" ]; then
    cd "$ROOT"
    if ! "$VENV/bin/alembic" history 2>/dev/null | grep -q "$CURRENT_REV"; then
        HEADS_OUTPUT=$("$VENV/bin/alembic" heads 2>/dev/null)
        HEADS_COUNT=$(printf '%s\n' "$HEADS_OUTPUT" | grep -c .)
        if [ "$HEADS_COUNT" -ne 1 ]; then
            error "Expected exactly 1 alembic head but found $HEADS_COUNT — merge heads before resyncing."
        fi
        HEAD_REV=$(printf '%s' "$HEADS_OUTPUT" | awk '{print $1}')
        # Validate HEAD_REV is safe to use in SQL (alphanumeric only — no quotes or special chars)
        if ! printf '%s' "$HEAD_REV" | grep -qE '^[a-z0-9]{1,64}$'; then
            error "Unexpected alembic revision format '$HEAD_REV' — aborting resync."
        fi
        warn "DB revision '$CURRENT_REV' not found in migration chain."
        warn "This will overwrite alembic_version from '$CURRENT_REV' to '$HEAD_REV'."
        warn "Only proceed if you are sure the DB schema matches the current codebase."
        echo -ne "${BOLD}Resync alembic_version to '$HEAD_REV'?${RESET} [y/N]: "
        read -r resync_ans
        lower_resync=$(printf '%s' "$resync_ans" | tr '[:upper:]' '[:lower:]')
        if [ "$lower_resync" = "y" ]; then
            psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
                -c "UPDATE alembic_version SET version_num = '${HEAD_REV}';" >/dev/null
            success "Resynced to revision '$HEAD_REV'."
        else
            error "Aborting — resolve the migration mismatch manually and re-run."
        fi
    fi
fi

cd "$ROOT" && "$VENV/bin/alembic" upgrade head
success "Migrations applied."

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║        Setup complete!               ║${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""
echo -e "  Run ${BOLD}make dev${RESET} to start the app."
echo ""
