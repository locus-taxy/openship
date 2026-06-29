#!/bin/bash
# Ensures .env exists and that JWT_SECRET_KEY / LLM_ENCRYPTION_KEY are real
# random secrets. Safe to run repeatedly — existing real secrets are left alone.
# Used by `make docker-up` so a new user never has to generate secrets by hand.
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"
ENV_EXAMPLE="$ROOT/.env.example"

# 1. Create .env from the template on first run.
if [ ! -f "$ENV_FILE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo "Created .env from .env.example"
fi

# Placeholder values shipped in .env.example — treated as "not set yet".
JWT_PLACEHOLDER="your_secret_key_min_32_chars_here_generate_with_secrets"
ENC_PLACEHOLDER="your-generated-fernet-key-here"

# Read the current value of a key from .env (empty if missing).
current_value() {
    grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2-
}

# Set or replace a key in .env (portable sed for macOS + Linux).
set_value() {
    local key="$1" value="$2"
    if grep -qE "^$key=" "$ENV_FILE"; then
        sed -i.bak "s|^$key=.*|$key=$value|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
    else
        echo "$key=$value" >> "$ENV_FILE"
    fi
}

# 2. JWT secret — 32 random bytes as hex.
JWT_CURRENT="$(current_value JWT_SECRET_KEY)"
if [ -z "$JWT_CURRENT" ] || [ "$JWT_CURRENT" = "$JWT_PLACEHOLDER" ]; then
    set_value JWT_SECRET_KEY "$(openssl rand -hex 32)"
    echo "Generated JWT_SECRET_KEY"
fi

# 3. LLM encryption key — 32 random bytes, url-safe base64 (Fernet-compatible).
ENC_CURRENT="$(current_value LLM_ENCRYPTION_KEY)"
if [ -z "$ENC_CURRENT" ] || [ "$ENC_CURRENT" = "$ENC_PLACEHOLDER" ]; then
    set_value LLM_ENCRYPTION_KEY "$(openssl rand -base64 32 | tr '+/' '-_')"
    echo "Generated LLM_ENCRYPTION_KEY"
fi

echo "Secrets ready."
