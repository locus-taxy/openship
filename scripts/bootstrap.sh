#!/usr/bin/env bash
# One-shot bootstrap: install Docker if missing, then start the full openship stack.
# Usage: make bootstrap   (or: bash scripts/bootstrap.sh)
#
# - Linux: installs Docker Engine via the official get.docker.com script (uses sudo).
# - macOS: installs Docker Desktop via Homebrew, then launches it (you accept the
#          license once in the GUI).
# - Windows: not supported here — install Docker Desktop manually, then run `make docker-up`.
#
# Already have Docker? This just waits for the daemon and runs the stack — nothing is reinstalled.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OS="$(uname -s)"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!  \033[0m %s\n' "$1"; }
die()  { printf '\033[1;31mx  \033[0m %s\n' "$1" >&2; exit 1; }

# Wait until the Docker daemon answers (bounded). Returns 0 if up, 1 if it timed out.
wait_for_daemon() {
    local tries="${1:-60}"
    for _ in $(seq 1 "$tries"); do
        if docker info >/dev/null 2>&1; then return 0; fi
        sleep 2
    done
    return 1
}

install_docker_linux() {
    say "Installing Docker Engine (official get.docker.com script — needs sudo)…"
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sudo sh /tmp/get-docker.sh
    rm -f /tmp/get-docker.sh
    # Start the daemon and let the current user run docker without sudo.
    sudo systemctl enable --now docker 2>/dev/null || sudo service docker start 2>/dev/null || true
    sudo usermod -aG docker "$USER" 2>/dev/null || true
    warn "Added you to the 'docker' group — a re-login may be needed for non-sudo access."
}

install_docker_macos() {
    if ! command -v brew >/dev/null 2>&1; then
        die "Homebrew not found. Install Docker Desktop manually from
   https://www.docker.com/products/docker-desktop/  then re-run: make docker-up"
    fi
    say "Installing Docker Desktop via Homebrew…"
    brew install --cask docker
    say "Launching Docker Desktop — accept the license/terms in the window if prompted…"
    open -a Docker || open -a "Docker Desktop" || true
}

# ── 1. Ensure Docker is installed ─────────────────────────────────────────────
if command -v docker >/dev/null 2>&1; then
    say "Docker is already installed."
else
    case "$OS" in
        Linux)  install_docker_linux ;;
        Darwin) install_docker_macos ;;
        *)      die "Unsupported OS '$OS'. Install Docker Desktop manually, then run: make docker-up" ;;
    esac
fi

# ── 2. Ensure the daemon is running ───────────────────────────────────────────
if ! docker info >/dev/null 2>&1; then
    if [ "$OS" = "Darwin" ]; then
        say "Waiting for Docker Desktop to start (open it if it hasn't launched)…"
        open -a Docker 2>/dev/null || true
    else
        say "Starting the Docker daemon…"
        sudo systemctl start docker 2>/dev/null || sudo service docker start 2>/dev/null || true
    fi
    wait_for_daemon 90 || die "Docker daemon did not become ready. Start Docker, then run: make docker-up"
fi
say "Docker daemon is up."

# ── 3. Start the stack ────────────────────────────────────────────────────────
say "Starting openship…"
cd "$ROOT"
make docker-up

say "Done. Open http://localhost in your browser."
