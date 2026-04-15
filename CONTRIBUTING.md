# Contributing to Openship

Thank you for your interest in contributing. This document covers everything you need to get started — from reporting bugs to submitting pull requests.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Ways to Contribute](#ways-to-contribute)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Pull Request Process](#pull-request-process)
- [Code Style](#code-style)
- [Commit Messages](#commit-messages)

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating you agree to uphold it. Report unacceptable behavior to the maintainers via the contact listed in that document.

---

## Ways to Contribute

- **Bug reports** — open an issue using the bug report template
- **Feature requests** — open an issue using the feature request template
- **Documentation** — fix typos, improve clarity, add examples
- **Code** — fix a bug or implement a requested feature
- **Triage** — help reproduce issues and confirm bug reports

If you are unsure whether something is a good fit, open a discussion issue first before investing time in an implementation.

---

## Reporting Bugs

> **Security vulnerabilities** must not be reported as public issues. See [SECURITY.md](SECURITY.md).

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md) and include:

- A clear title and description of the problem
- Steps to reproduce (minimal, exact commands or UI actions)
- What you expected to happen and what actually happened
- Your environment: OS, Python version, Node version, database type
- Relevant logs or error output (redact any secrets before pasting)

---

## Suggesting Features

Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md). Describe:

- The problem you are trying to solve (not just the solution)
- How you envision it working
- Any alternatives you considered

Features that align with the project's core purpose (personalized AI-driven learning, newsletter delivery, syllabus management) are most likely to be accepted.

---

## Development Setup

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.9+ |
| Node.js | 18+ |
| npm | 9+ |
| Git | any recent |
| PostgreSQL | 13+ (or SQLite for dev) |

### One-time setup

```bash
git clone https://github.com/locus-taxy/openship.git
cd openship
make setup
```

`make setup` creates the Python virtual environment, installs all dependencies (runtime and dev), installs UI packages, and wires up Husky pre-commit hooks.

After setup, copy `.env.example` to `.env` and fill in the required values:

```bash
cp .env.example .env
```

Required variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | SQLAlchemy connection string (PostgreSQL or SQLite) |
| `GEMINI_API_KEY` | Google Gemini API key |
| `JWT_SECRET_KEY` | Random string, minimum 32 characters |

### Running locally

```bash
make dev        # starts API on :3005 and UI on :5173
make run-api    # backend only
make run-ui     # frontend only
```

Full setup details are in [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md).

---

## Making Changes

1. **Fork** the repository and create a branch from `main`.

   ```bash
   git checkout -b fix/your-bug-description
   # or
   git checkout -b feat/your-feature-name
   ```

2. **Make your changes.** Keep the scope focused — one logical change per pull request.

3. **Test your changes manually** before opening a PR. Automated tests are being added; in the meantime, verify the affected flows work end to end.

4. **Format your code.** The pre-commit hook runs Black automatically on `git commit`. You can also run it manually:

   ```bash
   make format        # formats all Python files
   make format-check  # fails if anything is not Black-clean (used in CI)
   ```

   For frontend changes, run ESLint:

   ```bash
   cd ui && npm run lint
   ```

5. **Commit and push** your branch.

6. **Open a pull request** against `main`.

---

## Pull Request Process

- Fill in the [pull request template](.github/PULL_REQUEST_TEMPLATE.md) completely.
- Link any related issues using `Fixes #123` or `Closes #123` in the description.
- Keep PRs small and focused. Large PRs are harder to review and slower to merge.
- A maintainer will review your PR. Expect feedback; iteration is normal.
- Once approved, a maintainer will merge it.

---

## Code Style

### Python

- Formatted with **Black** (line length 100, enforced by pre-commit hook)
- Type hints are encouraged on new functions
- Follow the existing file structure: controllers handle HTTP concerns, services contain business logic, models define the schema

### TypeScript / React

- Linted with **ESLint** (config in `ui/`)
- Prefer functional components and hooks
- Keep components focused; split large components into smaller ones

### General

- Prefer clarity over cleverness
- Add comments only where the logic is not self-evident
- Do not add features, abstractions, or error handling beyond what the change requires

---

## Commit Messages

Use short, imperative-mood subject lines (under 72 characters):

```
fix: handle missing SMTP_HOST gracefully
feat: add skill deletion endpoint
docs: clarify DATABASE_URL format in README
refactor: extract token refresh logic into service
```

Prefix with one of: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

For non-trivial changes, add a body explaining *why*, not just what:

```
fix: set cookie secure flag from environment

The secure flag was hardcoded to False, which caused session tokens to
be sent over plain HTTP in production deployments. Read COOKIE_SECURE
from the environment so production instances can enforce HTTPS.
```
