# Openship — one-command local setup and dev (see docs/LOCAL_SETUP.md)
PYTHON ?= python3
VENV := .venv
PIP := $(VENV)/bin/pip
ROOT := $(abspath .)

.PHONY: help setup dev run-api run-ui format format-check install

help:
	@echo "Openship Makefile"
	@echo "  make setup       Create venv, install Python + UI deps, configure Husky + pre-commit, seed .env"
	@echo "  make dev         Run API (port 3005) and UI (5173) in parallel; opens browser for UI"
	@echo "  make run-api     FastAPI only (reload)"
	@echo "  make run-ui      Vite dev server only"
	@echo "  make format      Run Black + single-blank-line pass via pre-commit (may run twice)"
	@echo "  make format-check  CI-style: fail if Python formatting is not clean"
	@echo "  make install     Alias for setup"

install: setup

setup:
	@if [ ! -f "$(ROOT)/.env" ]; then \
		cp "$(ROOT)/.env.example" "$(ROOT)/.env"; \
		echo "Created .env from .env.example — edit DATABASE_URL, GEMINI_*, etc."; \
	fi
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r "$(ROOT)/requirements.txt" -r "$(ROOT)/requirements-dev.txt"
	cd "$(ROOT)/ui" && npm install
	@if [ -d "$(ROOT)/.git" ]; then \
		cd "$(ROOT)" && npm install; \
		echo "Husky: git hooks path configured by npm prepare (run from a git clone)."; \
	else \
		echo "Skipping root npm install (no .git). Clone the repo for Husky pre-commit hooks."; \
	fi
	@echo ""
	@echo "Setup complete. Next: edit .env if needed, then: make dev"

dev:
	@$(MAKE) -j2 run-api run-ui

run-api:
	cd "$(ROOT)" && $(VENV)/bin/uvicorn main:app --reload --host 0.0.0.0 --port 3005

run-ui:
	cd "$(ROOT)/ui" && npm run dev

# Black may rewrite files on first run; pre-commit then exits 1 — run twice so a clean tree exits 0.
format:
	cd "$(ROOT)" && $(VENV)/bin/pre-commit run --all-files || $(VENV)/bin/pre-commit run --all-files

format-check:
	cd "$(ROOT)" && $(VENV)/bin/pre-commit run --all-files
