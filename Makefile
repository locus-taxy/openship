# Openship — one-command local setup and dev (see docs/LOCAL_SETUP.md)
PYTHON ?= python3
VENV := .venv
PIP := $(VENV)/bin/pip
ROOT := $(abspath .)

.PHONY: help setup full-setup dev run-api run-ui format format-check install sandbox-build sandbox-rebuild

help:
	@echo "Openship Makefile"
	@echo "  make setup           Create venv, install Python + UI deps, configure Husky + pre-commit, seed .env
  make full-setup      Same as setup, then builds the Docker sandbox image (all languages ready to go)"
	@echo "  make dev             Start API and UI in separate Terminal windows"
	@echo "  make run-api         FastAPI only (reload)"
	@echo "  make run-ui          Vite dev server only"
	@echo "  make sandbox-build   Build the Docker sandbox image (all 41 language runtimes)"
	@echo "  make sandbox-rebuild Rebuild the sandbox image from scratch (no cache)"
	@echo "  make format          Run Black + single-blank-line pass via pre-commit (may run twice)"
	@echo "  make format-check    CI-style: fail if Python formatting is not clean"
	@echo "  make install         Alias for setup"

install: setup

full-setup:
	@$(MAKE) setup
	@$(MAKE) sandbox-build
	@echo ""
	@echo "All done! Set SANDBOX_USE_DOCKER=true in .env, then run 'make dev'."

setup:
	@chmod +x "$(ROOT)/scripts/setup.sh"
	@bash "$(ROOT)/scripts/setup.sh"

dev: # macOS only — uses osascript to open Terminal windows; on Linux use make run-api and make run-ui in separate shells
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

sandbox-build:
	@echo "Building openship-sandbox Docker image (this takes a few minutes on first run)..."
	docker build -t openship-sandbox "$(ROOT)/sandbox"
	@echo "Done — sandbox image built. Set SANDBOX_USE_DOCKER=true in .env to activate."

sandbox-rebuild:
	@echo "Rebuilding openship-sandbox Docker image from scratch..."
	docker build --no-cache -t openship-sandbox "$(ROOT)/sandbox"
	@echo "Done."
