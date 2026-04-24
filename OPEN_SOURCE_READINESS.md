# Open Source Readiness Analysis — Openship

**Assessment Date:** April 2026
**Overall Readiness:** Not ready — critical issues must be resolved before making this repository public.

---

## Critical Issues (Must Fix Before Going Public)

### 1. Exposed API Key in `.env`

A real Google Gemini API key is present in the `.env` file:

```
GEMINI_API_KEY=
```

The `.env` file is correctly excluded from git tracking, so this key has not been committed to history. However, if the repository is made public before this is addressed and the file is accidentally included or the key is reused elsewhere, it would be immediately exploitable.

**Action:**
- Revoke this key immediately in Google Cloud Console regardless.
- Generate a new key and keep it only in your local `.env`.
- Never reuse this key anywhere.

---

### 2. Cookie `secure` Flag Hardcoded to `False`

In `controllers/auth.py` (lines 27, 36, 47), all auth cookies are set with `secure=False`:

```python
response.set_cookie(
    key=ACCESS_COOKIE,
    value=access_token,
    httponly=True,
    samesite="lax",
    secure=False,   # transmits over plain HTTP
    ...
)
```

In production, this means session tokens will be sent over unencrypted HTTP, making them interceptable. This should be environment-aware.

**Action:** Change to `secure=not DEBUG` or read a `COOKIE_SECURE` environment variable.

---

### 3. CORS Origins Hardcoded to Localhost

In `main.py` (lines 36–45), CORS is configured with hardcoded local development URLs:

```python
allow_origins=[
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]
```

Production deployments will have CORS blocked with no way to configure it without editing source code.

**Action:** Read allowed origins from an environment variable (e.g., `ALLOWED_ORIGINS=https://app.openship.io`).

---

## High Priority (Required for a Healthy Open Source Project)

### 4. No `CONTRIBUTING.md`

Contributors have no guidance on:
- How to set up the development environment (currently scattered in docs/LOCAL_SETUP.md)
- Code style requirements (Black, ESLint)
- How to submit a pull request
- Branch naming or commit message conventions
- Whether tests are required before merging

Without this file, contributions will be inconsistent and maintainers will spend time on back-and-forth that should be covered in documentation.

---

### 5. No `SECURITY.md`

There is no policy for how users should report security vulnerabilities. If someone finds a security issue in Openship, there is currently no safe channel to disclose it privately — they would either have to open a public GitHub issue (dangerous) or have no path at all.

**Must include:**
- Contact method for private disclosure (e.g., a dedicated email)
- Response time commitment
- Scope of what qualifies as a security issue
- What reporters can expect (acknowledgement, CVE credit, etc.)

---

### 6. No `CODE_OF_CONDUCT.md`

Open source projects without a code of conduct tend to attract fewer contributors, especially from underrepresented groups. It also leaves maintainers with no documented basis for removing bad actors from the community.

**Action:** Adopt the [Contributor Covenant v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/) — it is the standard for most open source projects and requires only minimal customization (adding a contact email).

---

### 7. No GitHub Issue or Pull Request Templates

There is no `.github/` directory. Without templates:
- Bug reports come in without reproduction steps, environment info, or logs
- Feature requests have no structure
- Pull requests arrive without context on what was changed or why
- Maintainers spend significant time asking for basic information

**Files to create:**
```
.github/
  ISSUE_TEMPLATE/
    bug_report.md
    feature_request.md
  PULL_REQUEST_TEMPLATE.md
```

---

### 8. No CI/CD Pipeline

There are no GitHub Actions workflows. This means:
- Code can be merged without passing lint or type checks
- No automated validation that the application even starts
- No protection against regressions
- Contributors have no automated feedback on their PRs

**Minimum workflows to add:**
- **Backend lint + format check** — run Black in check mode, any linting
- **Frontend lint + type check** — ESLint, `tsc --noEmit`
- **Dependency security scan** — e.g., `pip audit`, `npm audit`
- **Basic smoke test** — verify the app starts without errors

---

### 9. No Tests

There are zero test files in the project — no unit tests, integration tests, or end-to-end tests for either the backend or frontend.

**Impact:**
- Contributors cannot verify their changes don't break existing behavior
- Every PR merge is a bet that nothing regressed
- Refactoring is high-risk
- Open source contributors are unlikely to add tests if none exist to follow as examples

**Target before first public release:**
- Backend: pytest covering auth flows, core controllers, and service layer
- Frontend: Vitest covering key components and state logic

---

## Medium Priority (Before Announcing / Seeking Contributors)

### 10. No Docker Support

There is no `Dockerfile` or `docker-compose.yml`. Setting up the project requires:
- Python 3.9+, a virtual environment, and all pip packages
- Node.js and npm for the UI
- PostgreSQL (or SQLite for dev)
- Manually configuring `.env`

This is a high barrier for casual contributors. Docker would let anyone run the full stack with a single command.

**Files to add:**
```
Dockerfile              (multi-stage: backend)
docker-compose.yml      (API + UI + PostgreSQL together)
.dockerignore
```

---

### 11. README Needs Strengthening

The current README is a reasonable start, but for an open source project it should also include:

- **Badges** — build status, license, last commit — these signal an active, maintained project at a glance
- **A link to CONTRIBUTING.md** — how to get involved
- **A link to SECURITY.md** — how to report issues privately
- **Screenshots or a short demo GIF** — visual projects benefit enormously from showing what they do
- **Explicit license mention with link** — currently the LICENSE file exists but isn't referenced in the README

---

### 12. No `CHANGELOG.md`

Users and contributors should be able to see what changed between versions. A changelog is especially important for:
- People evaluating whether to upgrade
- Tracking breaking changes
- Communicating intent behind releases

Follow [Keep a Changelog](https://keepachangelog.com) format.

---

### 13. No Production Deployment Guide

The docs cover local development well (`docs/LOCAL_SETUP.md`) but there is no documentation on how to deploy Openship in production. Potential users need guidance on:

- Setting `secure=True` cookies in production
- Configuring CORS for a real domain
- Using PostgreSQL instead of SQLite
- Setting a strong `JWT_SECRET_KEY`
- TLS/SSL termination
- Recommended hosting approaches (VPS, managed PaaS, containers)
- Environment variable checklist before going live

Without this, users will deploy insecurely or give up.

---

### 14. `ui/README.md` Is a Vite Template Placeholder

The `ui/README.md` is the default Vite scaffold README and contains no information about Openship's UI. It should be replaced or removed.

---

## Low Priority (Polish Before Growth)

### 15. No Dependabot or Automated Dependency Updates

Dependencies will drift out of date and accumulate known vulnerabilities with no automated tracking. Adding Dependabot (via `.github/dependabot.yml`) keeps dependencies fresh with minimal maintainer effort.

---

### 16. `version` Field in UI `package.json` Is `0.0.0`

Stale placeholder. Should be updated to reflect actual project versioning once a release strategy is in place.

---

### 17. API `version` Set to `"2.0"` in `main.py` With No v1 Context

The FastAPI app declares `version="2.0"`. There's no changelog entry or migration guide explaining what changed from v1, which will confuse anyone reading the API docs. Either start at `1.0` or document what this means.

---

## What Is Already in Good Shape

The following are well-implemented and do not need attention before open sourcing:

- **MIT License** — correct, complete, at the root
- **NOTICE file** — all third-party dependency attributions included
- **`.gitignore`** — properly excludes `.env`, `*.db`, `node_modules`, `.venv`
- **Git history** — no secrets have ever been committed
- **Environment configuration** — all secrets loaded from environment, not hardcoded in source
- **`.env.example`** — present with placeholder values, safe to commit
- **Code architecture** — clean separation of controllers, services, models, schemas, routes
- **Auth implementation** — JWT with httponly cookies, refresh tokens, global middleware
- **Rate limiting** — slowapi integrated at application level
- **Pre-commit hooks** — Black formatter enforced via Husky + pre-commit
- **Makefile** — clear setup and development commands
- **Technical documentation** — `docs/LOCAL_SETUP.md`, `docs/api.md` are solid

---

## Prioritized Action Checklist

### Block on these before making the repo public

- [ ] Revoke the exposed Gemini API key in Google Cloud Console
- [ ] Make cookie `secure` flag environment-aware
- [ ] Make CORS origins configurable via environment variable
- [ ] Create `SECURITY.md` with a private disclosure contact
- [ ] Create `CONTRIBUTING.md`
- [ ] Add `CODE_OF_CONDUCT.md` (Contributor Covenant v2.1)
- [ ] Create `.github/ISSUE_TEMPLATE/bug_report.md`
- [ ] Create `.github/ISSUE_TEMPLATE/feature_request.md`
- [ ] Create `.github/PULL_REQUEST_TEMPLATE.md`
- [ ] Add at least one CI workflow (lint + format check is sufficient to start)

### Complete before announcing or seeking contributors

- [ ] Add a baseline test suite for the backend (auth + core controllers)
- [ ] Add `Dockerfile` and `docker-compose.yml`
- [ ] Create a production deployment guide
- [ ] Add GitHub badges to README (build, license)
- [ ] Add links to CONTRIBUTING and SECURITY in README
- [ ] Replace `ui/README.md` placeholder content
- [ ] Add `CHANGELOG.md`
- [ ] Configure Dependabot for both npm and pip

### Nice to have before 1.0

- [ ] Frontend test suite (Vitest)
- [ ] CodeQL security scanning in CI
- [ ] OpenAPI/Swagger customization with example payloads
- [ ] Architecture overview document
- [ ] Troubleshooting guide
