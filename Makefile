# Openship — one-command local setup and dev (see docs/LOCAL_SETUP.md)
PYTHON ?= python3
VENV := .venv
PIP := $(VENV)/bin/pip
ROOT := $(abspath .)

.PHONY: help setup dev run-api run-ui format format-check install db-up db-down

help:
	@echo "Openship Makefile"
	@echo "  make setup       Start the DB (Docker), create venv, install Python + UI deps, seed .env, migrate"
	@echo "  make dev         Start the DB, then API and UI in separate Terminal windows"
	@echo "  make run-api     FastAPI only (reload)"
	@echo "  make run-ui      Vite dev server only"
	@echo "  make db-up       Start the PostgreSQL + pgvector database (Docker)"
	@echo "  make db-down     Stop the database (data is preserved)"
	@echo "  make format      Run Black + single-blank-line pass via pre-commit (may run twice)"
	@echo "  make format-check  CI-style: fail if Python formatting is not clean"
	@echo "  make install     Alias for setup"

install: setup

setup:
	@chmod +x "$(ROOT)/scripts/setup.sh"
	@bash "$(ROOT)/scripts/setup.sh"

# Start/stop the local database (Postgres + pgvector) via Docker.
db-up:
	docker compose -f "$(ROOT)/docker-compose.yml" up -d db

db-down:
	docker compose -f "$(ROOT)/docker-compose.yml" down

dev: # macOS only — uses osascript to open Terminal windows; on Linux use make run-api and make run-ui in separate shells
	@echo "Ensuring the database is up..."
	@docker compose -f "$(ROOT)/docker-compose.yml" up -d db 2>/dev/null || echo "(skipping Docker DB — using a local PostgreSQL)"
	@echo "Opening API terminal..."
	@osascript -e 'tell application "Terminal" to do script "echo \"=== Openship API ===\"; cd \"$(ROOT)\" && $(VENV)/bin/uvicorn main:app --reload --host 0.0.0.0 --port 3005"'
	@echo "Waiting for API on :3005..."
	@i=0; while [ $$i -lt 120 ]; do \
		if curl -sf "http://127.0.0.1:3005/openapi.json" >/dev/null 2>&1; then \
			echo "API is ready."; break; \
		fi; \
		sleep 0.5; \
		i=$$((i + 1)); \
	done
	@curl -sf "http://127.0.0.1:3005/openapi.json" >/dev/null || { echo "API did not become ready on :3005"; exit 1; }
	@echo "Opening UI terminal..."
	@osascript -e 'tell application "Terminal" to do script "echo \"=== Openship UI ===\"; cd \"$(ROOT)/ui\" && npm run dev"'
	@echo "Done — API on :3005, UI on :5173. Close the Terminal windows to stop."

run-api:
	cd "$(ROOT)" && $(VENV)/bin/uvicorn main:app --reload --host 0.0.0.0 --port 3005

run-ui:
	cd "$(ROOT)/ui" && npm run dev

# Black may rewrite files on first run; pre-commit then exits 1 — run twice so a clean tree exits 0.
format:
	cd "$(ROOT)" && $(VENV)/bin/pre-commit run --all-files || $(VENV)/bin/pre-commit run --all-files

format-check:
	cd "$(ROOT)" && $(VENV)/bin/pre-commit run --all-files
