# Confluence-Powered Onboarding: Design

**Status:** Draft for review · **Component:** Openship · onboarding · **Owner:** Yogesh K

---

## The idea

New hires don't lack documentation; they lack a **path through it**. The docs already live in Confluence (architecture, setup, repos, platform internals), but a joiner has no idea what to read, in what order, or what's relevant to their role.

We build an onboarding system that:

1. **Connects** to a company's Confluence,
2. **Finds** the onboarding-relevant docs,
3. **Generates** a structured, role-specific 7-day plan (day content plus a final quiz) from those docs, and
4. **Keeps itself fresh** as the docs change.

The whole product is grounded in the company's *real* documentation. The LLM never invents; it only reads what we pulled (this is RAG: retrieve first, then generate).

---

## How it works, end to end

```
Connect Confluence  →  Ingest the right docs  →  Employee picks a role  →  Plan + content + quiz
       (once)              (funnel + confirm)         (any time)              (generated from docs)
                                                                                      ↑
                                                            Webhooks keep docs fresh ─┘
```

---

## 1 · Delivery model: integration layer

The core question is *where our code runs and who sets it up*. Three shapes exist:

| Model | Our code runs… | Company connects by… | Build cost |
|---|---|---|---|
| **Integration layer** *(chosen)* | On our servers; we call Confluence's API | Clicking "Connect", logging in, approving | Low-Medium |
| Package / SDK | On the company's servers | Their engineers install & run our library | Medium |
| Marketplace app (Forge) | Inside their Confluence | An admin installs it from the Atlassian Marketplace | High |

**Decision:** integration layer. Lowest friction (a non-technical person just clicks "Allow"), all logic centralized so we ship and fix fast. The Forge app is a deliberate later graduation (§12), not a starting point.

---

## 2 · Architecture

Three layers. Confluence is a pure data source. Our integration layer owns connection, pull, classification, and freshness. The onboarding engine consumes stored docs and never touches Confluence.

```
┌─ Company ─────────────────────────────────────────────┐
│  Confluence: spaces · pages · REST API · webhooks      │
└───────────────────────────┬───────────────────────────┘
                            ▼
┌─ Integration layer (new) ─────────────────────────────┐
│  OAuth + token store · Connector (REST client)         │
│  Ingestion funnel · LLM classifier                     │
│  Webhook receiver · Daily reconciler                   │
└───────────────────────────┬───────────────────────────┘
                            ▼
┌─ Onboarding engine (new) ─────────────────────────────┐
│  onboarding_docs (source of truth, per company)        │
│  Plan generator · Day-content generator · Quiz gen     │
│  Employee UI: plan · content · progress · quiz         │
└────────────────────────────────────────────────────────┘
```

**Boundary that keeps it clean:** the onboarding engine only ever reads from `onboarding_docs`, scoped by company and role. Everything that talks to Confluence stays in the integration layer.

---

## 3 · Connecting Confluence

We register **one** Atlassian OAuth 2.0 app. Every company uses it and gets its own token. The user creates nothing in Atlassian; they only approve access.

```
Connect → Authorize on Atlassian → Exchange code for tokens → Store encrypted (company-level)
```

**Who connects:** the first employee from a company does the setup; everyone after reuses the result and never sees the connect screen.

**Why the token lives on the company, not the person:** a personal token dies when that employee leaves, which would silently break sync for the whole company. Company-level storage means *any* employee can re-approve and refresh it.

> **Limitation (v1):** three-legged OAuth only sees what the authorizing user sees, and big enterprises gate third-party access behind an admin. Fine for smaller teams now; the durable fix is the Forge app (§12).

---

## 4 · First-time ingestion: the funnel

A company's Confluence can hold thousands of pages, mostly irrelevant. We never LLM-scan everything (slow, costly, noisy). We **narrow cheaply, then judge with the LLM, then let a human confirm:**

| Step | What | Tool |
|---|---|---|
| 1 · Pick spaces | Human selects spaces with eng/onboarding docs, so thousands of pages become hundreds | REST API |
| 2 · Cheap filter | Shortlist by label, title pattern, page location, so hundreds become dozens | REST API · CQL |
| 3 · Classify | LLM judges only the shortlist: relevant? which role? Dozens of calls, not thousands | LLM |
| 4 · Confirm | Human sees picks **pre-checked**, unchecks junk or adds misses, confirms | Openship UI |

**Fetching is always an API job, never the LLM, never MCP.** An LLM can't reach Confluence; it only reasons over text we already pulled, and only at step 3. MCP (a wrapper for an AI agent that decides what to fetch on the fly) is the wrong tool for a fixed pipeline.

**Confirm is add-only:** it can add docs but never delete docs already saved for the company. So a careless employee can't wipe the set. Re-running ingestion is always safe; pages already stored are skipped, never duplicated.

Key API calls: `GET /wiki/api/v2/spaces`, `GET /wiki/api/v2/spaces/{id}/pages`, `GET /wiki/api/v2/pages/{id}?body-format=storage`, plus CQL search for filters.

---

## 5 · Coverage: the one real risk

The funnel's weak point is **under-selection**: if the first person misses a space, its docs are invisible and no one notices (over-selecting is harmless; the LLM drops junk). Four layers make under-selection rare and recoverable:

1. **Editable, never one-shot:** the space list is a company setting anyone can expand anytime; adding a space ingests only that space (skip-if-exists).
2. **Visible to everyone:** every employee sees a quiet line, *"Connected to: Engineering, Platform. Missing something? Add more spaces."* The crowd self-corrects.
3. **Smart defaults:** the space picker pre-ranks and pre-checks likely spaces (onboarding labels, eng-ish titles, recent activity), so the human corrects a good guess.
4. **Gap detector:** a periodic cheap scan of *unconnected* spaces flags onboarding-looking pages, *"12 likely pages found in HR, QA. Include them?"*

Principle: **never let a one-time human choice become a permanent blind spot.**

---

## 6 · Generating the onboarding

Once docs are stored, generation reads them filtered by `company_id` + role:

- **Plan:** a 7-day structure (topics + tasks), grounded only in that company's docs for that role.
- **Day content:** for each day, rich explanatory content (what / why / how / where), generated on demand and cached.
- **Quiz:** a final multiple-choice quiz from the same docs; validates the joiner actually understood, not just read.

All three are RAG: the docs are the source of truth, the LLM only summarizes and structures them. Role filtering means a Backend Engineer and a DevOps Engineer get genuinely different plans from the same doc set.

---

## 7 · Keeping docs fresh

Webhooks alone are never enough (dropped on restarts, blips, throttling). So a **fast path** reacts instantly, and a **slow path** guarantees correctness.

**Fast: webhooks**

| Event | We… |
|---|---|
| `page_updated` | If tracked, re-fetch body, update row + version. Else ignore. |
| `page_created` | Fetch it, LLM relevance check. If relevant, auto-add with role tags + notify. Else ignore. |
| `page_removed` / archived | Mark our copy inactive so it stops feeding plans. |

**Slow: daily reconciler.** Re-list connected spaces, diff against our DB: backfill missed webhooks, deactivate vanished pages, re-check ambiguous changes. Webhooks make us *fast*; reconciliation makes us *correct*.

---

## 8 · Data model

All tables are scoped by `company_id` for tenant isolation. The first three power the integration layer; the rest hold generated onboarding content.

### `companies`

| Column | Notes |
|---|---|
| `id` | Primary key |
| `name` | Company name |
| `domain` | e.g. `locus.sh`; maps an employee to their company |
| `created_at` | Timestamp |

### `confluence_connections`

| Column | Notes |
|---|---|
| `id` | Primary key |
| `company_id` | One connection per company |
| `site_url` | Their Atlassian site |
| `space_keys` | JSON list of connected spaces; editable, additive |
| `access_token` | **Encrypted** at rest |
| `refresh_token` | **Encrypted** at rest |
| `webhook_id` | Registered webhook handle |
| `status` | `pending` / `syncing` / `ready` / `error` |
| `connected_by_user_id` | Audit only, not an ownership grant |

### `onboarding_docs`

| Column | Notes |
|---|---|
| `id` | Primary key |
| `company_id` | Tenant isolation |
| `confluence_page_id` | Dedup key for skip-if-exists |
| `confluence_version` | Detects real changes on update |
| `title` | Page title |
| `content_markdown` | Cleaned page body |
| `role_tags` | JSON, e.g. `["backend", "devops"]` |
| `is_active` | `false` when archived/removed upstream |
| `last_synced_at` | Timestamp |

### `onboarding_plans`

| Column | Notes |
|---|---|
| `id` | Primary key |
| `company_id` | Tenant isolation |
| `user_id` | The employee |
| `role` | Role the plan was generated for |
| `status` | Plan status |
| `created_at` | Timestamp |

### `onboarding_days`

| Column | Notes |
|---|---|
| `id` | Primary key |
| `plan_id` | Parent plan |
| `day` | Day number (1–7) |
| `topic` | Short day title |
| `task` | What to read / explore / do |
| `content_blocks` | JSON, generated content (cached) |
| `completed` | Progress flag |

### `onboarding_quiz` / `quiz_attempts`

| Table | Holds |
|---|---|
| `onboarding_quiz` | The generated questions for a plan |
| `quiz_attempts` | Each attempt with its score, per user |

### `ingestion_jobs`

| Column | Notes |
|---|---|
| `id` | Primary key |
| `company_id` | Tenant isolation |
| `total_pages` / `processed_pages` | Drives the progress bar |
| `status` | `running` / `done` / `failed` |
| `created_at` / `completed_at` | Timestamps |

---

## 9 · API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/confluence/connect` | Begin OAuth; redirect to Atlassian |
| GET | `/confluence/callback` | Exchange code, store encrypted tokens |
| GET | `/confluence/status` | Is this company connected & ready? |
| GET | `/confluence/spaces` | List spaces with smart-default pre-selection |
| POST | `/confluence/ingest` | Run the funnel over chosen spaces (async) |
| GET | `/confluence/candidates` | Classified shortlist for confirm screen |
| PATCH | `/confluence/candidates` | Confirm (add-only) → write to `onboarding_docs` |
| POST | `/webhooks/confluence` | Receive created / updated / removed events |
| POST | `/onboarding/generate` | Generate a role-based plan for an employee |
| GET | `/onboarding/{id}/day/{n}` | Get (or generate + cache) a day's content |
| GET/POST | `/onboarding/{id}/quiz` | Fetch or generate the final quiz |

---

## 10 · Security & tenancy

- **Token encryption:** access/refresh tokens encrypted at rest (reuse the existing key-encryption service).
- **Tenant isolation:** every doc query scoped by `company_id`; an employee only ever reaches their own company's docs.
- **Company identity:** employees map to a company by email domain in v1 (simple, correct for most B2B); multi-domain/contractors deferred.
- **Webhook authenticity:** incoming webhooks verified (signature/secret) so forged calls can't inject docs.
- **Least privilege:** OAuth requests read-only scopes; we never write to a customer's Confluence.

---

## 11 · Phased rollout

Each phase is independently shippable.

| Phase | Ships |
|---|---|
| 1 · Connect | OAuth app, connect flow, encrypted company-level tokens, `/status` |
| 2 · Ingest | Space picker + smart defaults, cheap filter, LLM classify, confirm screen, async job |
| 3 · Generate | Store docs → plan + day content + quiz generation, employee UI. Feature end-to-end |
| 4 · Freshness | Register webhooks; handle created / updated / removed |
| 5 · Correctness | Daily reconciler + background gap detector |

---

## 12 · Future work

- **Forge / Marketplace app:** admin-installed at site level, app-scoped tokens that survive employee churn, native webhooks, Marketplace discoverability. Can coexist with the integration layer.
- **Vector search:** for large doc sets, replace whole-document prompting with embeddings + semantic retrieval.
- **More sources:** the same funnel + freshness pattern generalizes to Notion, Google Drive, GitHub wikis behind a common connector interface.
- **Real RBAC:** a proper org-admin role to gate connection and space edits, replacing the v1 "first connector + add-only" model.
