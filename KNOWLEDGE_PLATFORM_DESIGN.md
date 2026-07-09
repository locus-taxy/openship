# Openship Knowledge Platform - Design

**Status:** Shipped  ·  **Component:** Openship (`onboarding/` package)  ·  **Owner:** Yogesh Kisslay

---

## 1. Overview

The Knowledge Platform turns a company's **Atlassian workspace** into a private, AI-searchable
knowledge base. A company connects once, and Openship reads **all of its Confluence pages and
Jira issues** into one indexed store. That single store then powers three product surfaces:

| Surface | What it does | Source |
|---|---|---|
| **Connections** | Connect Atlassian and index Confluence + Jira into the knowledge base | Confluence + Jira |
| **Onboarding** | Generate a role-based 7-day onboarding plan, day-by-day content, and a quiz | Confluence only |
| **Knowledge** | A chat assistant that answers questions from the company's own docs, with citations and people-analytics | Confluence + Jira |

Onboarding and Knowledge are simply **two different readers of the same indexed base** - they
differ only in which sources they read and how they prompt the model. Everything else - the
connection, the ingestion pipeline, the database tables - is shared.

### The engine: Retrieval-Augmented Generation (RAG)

We never send an entire company's documentation to the AI model. Instead:

```
   Ingest each page/issue  →  split into small chunks  →  turn each chunk into a vector
                                                                        │
   Ask a question  →  turn the question into a vector  →  find the nearest chunks
                                                                        │
                              feed only those few chunks to the LLM  →  grounded answer
```

Retrieval narrows tens of thousands of documents down to the handful that actually matter for a
given question. This keeps answers grounded in real company content, keeps cost low, and scales
to very large workspaces.

---

## 2. How we connect (Atlassian)

### One OAuth connection, both products

A single **Atlassian OAuth 2.0 (3-legged) app** grants read access to **both** Confluence and
Jira. We store the resulting tokens **once per company** (encrypted), and both products are read
using the same credentials - they differ only in the API base URL:

- Confluence: `https://api.atlassian.com/ex/confluence/{cloud_id}`
- Jira: `https://api.atlassian.com/ex/jira/{cloud_id}`

Tokens are **encrypted at rest** and **auto-refresh** (Atlassian access tokens live ~1 hour; a
long-lived refresh token is used to mint new ones). All timestamps are stored in UTC.

### Which company a user belongs to

Every user is mapped to exactly one company, decided from their email at sign-up:

- **Corporate email** (e.g. `dev@acme.com`) → the company is keyed by the **domain** (`acme.com`),
  so all teammates share one knowledge base.
- **Personal / generic email** (e.g. `@gmail.com`) → the user becomes a **private one-person
  organisation**, keyed by the **full email address** (so two unrelated personal users never
  pool into the same base).

The company is stored on the user record and shown (read-only) in **Settings → Account**. Because
docs are indexed per company, a **new teammate automatically shares the existing connection** -
no reconnection needed.

### Connecting safely (identity check)

When a user connects, we verify - via Atlassian's identity API - that the **Atlassian account
they authorised with matches their Openship login email**. This prevents a user who happens to be
signed into a *personal* Atlassian account in their browser from accidentally binding their
personal workspace as the whole company's knowledge base. A mismatch is rejected.

---

## 3. Ingestion - how data comes in

Ingestion runs as a **background job** with a live, staged progress bar
(**Reading → Scanning → Embedding**).

### What we read

| Source | Container | Item read |
|---|---|---|
| **Confluence** | Space (personal `~` spaces skipped) | Every page **and** blog post |
| **Jira** | Project | Every issue (summary, description, comments, and fields) |

All reads go through Atlassian's **search APIs**, which work with standard read scopes. For Jira
we use the current enhanced JQL search with token-based pagination. Jira descriptions/comments
arrive as Atlassian's structured "ADF" format, which we flatten to plain text.

### The pipeline

For each item we:

1. **Read** it from Atlassian, with enough detail to get its full text **and** its metadata in
   one call.
2. **Normalise & store** it as one row in `document_pages` - the title, the cleaned full text,
   and structured fields (for Jira: assignee, reporter, status, project, priority, etc.).
3. **Chunk** the text into ~800-token slices and **embed** each slice into a vector, stored in
   `document_chunks`.

Because the structured people-fields are written in step 2 (the *read* phase), **"who did what"
analytics is complete as soon as reading finishes - before the slower embedding step even runs.**

### Built to survive a large, first-time ingest

Reading an entire large workspace is a multi-hour operation across tens of thousands of requests,
so the pipeline is deliberately resilient:

- **Respects rate limits.** When Atlassian asks us to slow down, we wait exactly as long as it
  tells us to (and retry patiently) rather than giving up and dropping a project.
- **Keeps the session alive.** The access token is refreshed *before every project* (with a
  safety margin), so a run that lasts longer than a token's ~1-hour lifetime never dies midway.
- **Bounded memory.** We process **one project/space at a time** and release it before the next,
  so memory stays flat regardless of workspace size (one project can hold 100k+ issues).
- **Resumable & idempotent.** Re-running adds new items, updates changed ones, **removes ones
  deleted upstream**, and **only re-embeds what actually changed** - so repeat runs are cheap and
  safe. A container that fails is skipped, counted, and surfaced ("N skipped - re-ingest to
  retry"), never fatal.
- **Cancellable.** A long sync can be stopped from the UI; the worker exits cleanly between
  projects/embed-batches. Partial progress is saved (resumable), and a cancelled/partial run
  never runs the deletion sweep - so an interrupted read can't wrongly delete anything.

### Keeping the base fresh

| Mechanism | How it works |
|---|---|
| **Webhooks** | Atlassian notifies us when a page/issue is created, updated, or deleted; we re-embed or deactivate just that item, near-instantly. Secret-authenticated and scoped to the right company. |
| **Sync (full re-scan)** | A full ingest doubles as the reconcile: in one read it upserts current items and, on a **complete** pass, deactivates any that vanished upstream (and reactivates restored ones) - the reliable baseline that catches anything a webhook missed. Guarded so a partial/cancelled read never deletes, and a container that failed to read is left untouched. |

---

## 4. Data model

### 4.1 Before this work

Openship already had the **learning-platform** schema: `users`, `skills`, `daily_tasks`,
`quizzes`, `quiz_questions`, `quiz_attempts`, `user_streaks`, `topic_knowledge` (mastery),
`llm_provider`, `user_api_keys`, `user_model_prices`, `llm_usage_logs`, `pricing_snapshots`, and
`content_style_arms`. None of these were about company documents.

### 4.2 What we changed on an existing table

| Table | Change |
|---|---|
| `users` | Added **`company_id`** (foreign key → `companies`), set at sign-up. This links each existing user to their company so the knowledge base can be shared per organisation. |

That is the **only** change to a pre-existing table - the knowledge platform is otherwise entirely
new tables, so it sits alongside the learning platform without disturbing it.

### 4.3 What we created (new tables)

| Table | Purpose | Notable columns |
|---|---|---|
| **`companies`** | One row per organisation (the multi-tenant boundary) | `name`, `domain` (or full email for personal orgs) |
| **`confluence_connections`** | The shared Atlassian connection for a company | `cloud_id`, `site_url`, encrypted `access_token` / `refresh_token`, `token_expires_at`, `status` |
| **`document_pages`** | One row per ingested item (a Confluence page/blog **or** a Jira issue) | `source` (`confluence`\|`jira`), `confluence_page_id` (page id or issue key), `space_key` (space/project), `title`, `content_text`, `version`, **`assignee` / `reporter` / `status`** (structured Jira fields), **`meta`** (JSONB), `is_active` |
| **`document_chunks`** | One row per ~800-token slice of a page | `content`, **`embedding`** (pgvector, 384-dim, HNSW cosine index), `token_count`, `chunk_index`, `source` |
| **`ingestion_jobs`** | Drives the live progress UI | `kind`, `source`, `phase`, page/chunk counters, `status` (`running`\|`done`\|`failed`\|`cancelled`), `error` |
| **`knowledge_chats`** | A persistent chat conversation | per user + company |
| **`knowledge_messages`** | One message in a chat | `content`, `blocks` (JSON), `citations` (JSON) |
| **`onboarding_plans`** | A generated 7-day onboarding plan | role, share flag |
| **`onboarding_days`** | One day of a plan | topic, task, `content_blocks` (JSON) |
| **`onboarding_quiz_attempts`** | An onboarding quiz attempt | score, `answers` (JSON) |

**Two design choices worth calling out:**

- **`document_pages` holds both products in one table.** A `source` column distinguishes
  Confluence from Jira, so retrieval can scope to one or both. Structured Jira people-fields
  (`assignee`/`reporter`/`status`) are **first-class indexed columns** for exact analytics, while
  everything source-specific and rarely-queried (labels, priority, breadcrumb, author, etc.) lives
  in a **`meta` JSONB** column - so new fields need no schema migration.
- **Vectors live in `document_chunks`** using PostgreSQL's `pgvector` extension (384 dimensions,
  HNSW cosine index) - no separate vector database is required.

### 4.4 How the model matured (before → after)

The schema was refined as the feature grew:

| Earlier | Now | Why |
|---|---|---|
| A single "onboarding docs" table | Split into `document_pages` + `document_chunks` | Clean separation of *source document* from its *embeddable slices* |
| 768-dimension vectors | **384-dimension** vectors | Switched to a smaller, faster local model; keeps the index compact at scale |
| Confluence only | `source` column added; Jira added | One pipeline, two products |
| Fixed columns only | Added a **`meta` JSONB** column + structured Jira `assignee`/`reporter`/`status` | Exact people-analytics without a migration for every new field |

---

## 5. Embeddings (turning text into vectors)

- Embeddings run **locally** inside the backend using a small open model
  (`BAAI/bge-small-en-v1.5`, 384-dim). **No API key, no quota, no per-token cost, no external
  calls** - it runs on CPU.
- The model is downloaded once and cached; it is shared by all users of a deployment.
- **Important split:** embedding is a company-wide, keyless local job; the **answer LLM stays
  per-user** (each user brings their own provider API key). So indexing costs nothing, and
  answering uses the asker's own model.

---

## 6. Onboarding

Grounded **only in Confluence** (an onboarding plan wants topical breadth, not literal keyword
hits, so it leans on semantic search).

1. **Plan.** Given a role, we retrieve a broad set of relevant docs and ask the model to produce a
   **7-day plan** - a topic and a task for each day.
2. **Day content.** When a day is opened, we retrieve docs focused on that day's topic and generate
   rich content - headings, code blocks, tables, and diagrams - rendered by the shared block
   renderer.
3. **Quiz.** A short multiple-choice quiz is generated over the plan's topics; attempts are saved.

Plans can be shared via a public read-only link. If the knowledge base isn't ready yet, the UI
guides the user to **Connections** first.

---

## 7. Knowledge chat & retrieval techniques

The Knowledge chat is a multi-turn, persistent assistant that answers **only** from the company's
Confluence + Jira. Its quality comes from the retrieval layer.

### 7.1 Hybrid retrieval (semantic + lexical)

Pure semantic search understands *meaning* but is weak on *exact tokens* like names and issue
keys. So every query runs **two searches in parallel** and merges them:

- **Semantic** - nearest chunks by vector similarity (good for concepts and paraphrases).
- **Lexical** - exact word/phrase matching on the text (good for names, issue keys like `AR-2847`).

Results are merged and **de-duplicated by page**, so the top results are distinct documents.

### 7.2 Name-aware matching

- **Full-name phrases are matched whole.** Asking about "Yogesh Kisslay" will not surface a
  different "Yogesh" - the complete name is required.
- **Known-people awareness.** We keep a per-company list of real people (from Jira
  assignees/reporters and Confluence authors), so even a **lowercase** name ("what is sunadh
  working on") is recognised as a person.
- **Whole-word matching** avoids false hits - "raj" never matches "Nataraj", "ana" never matches
  "management".

### 7.3 Adaptive semantic/keyword balance

A query that names a specific person or issue key leans on **keyword** matching; a conceptual
question ("how do we deploy") leans on **semantic** matching. The blend adapts per query.

### 7.4 People analytics - exact answers from the database

Retrieval can only return a *sample* of matching chunks - it cannot *count* or *list everything*.
So questions about people are answered by **exact database queries** instead:

| Question type | Example | Answer |
|---|---|---|
| **List** | "what is X working on", "all of X's work", "tell me about X and Y" | The complete list of that person's Jira issues + Confluence docs, each with their **role**, as clickable links |
| **Count / compare** | "how many issues did X report", "who did more, X or Y" | Exact per-role counts and a comparison |
| **Leaderboard** | "who reported the most", "top contributors" | A ranking across everyone, by the requested metric |

Roles are kept strictly distinct: **Assignee** = doing the work, **Reporter** = filed it, comment
author = commented. "Involvement" means actually holding one of these roles - not merely being
mentioned in text - so common-word names never over-count.

### 7.5 Grounding & anti-hallucination

- The model answers **only** from the retrieved excerpts; if something isn't covered, it says so.
- Every answer carries **source-linked citations** - deep links to the exact Jira issue or
  Confluence page.
- Any URL the model tries to invent that is **not** present in the retrieved sources is
  automatically stripped, so answers never contain fabricated links.

---

## 8. Security & multi-tenancy

- **Tenant isolation** - every query is scoped to the user's `company_id`; one company can never
  read another's documents. Webhooks are scoped to the owning company too.
- **Connector identity check** - you can only connect with your own company's Atlassian account
  (see §2).
- **Encryption** - OAuth tokens are encrypted at rest; webhooks are authenticated with a
  shared secret using a constant-time comparison.
- **Key separation** - embeddings need no secret (local); the answer LLM uses each user's own key.
- **No fabricated content** - strict grounding, stripped invented links, and deterministic
  database answers for people-questions (never model-guessed numbers).

---

## 9. API surface

All routes are served under `/py/…`.

- **Connections** - connect, OAuth callback, connection status, start ingest (per source), poll
  ingest progress, cancel a running ingest, and the Confluence/Jira webhook receivers.
- **Knowledge** - one-shot query, plus full chat CRUD (create, list, get, delete, post message).
- **Onboarding** - generate/list/get a plan, fetch day content, generate/submit the quiz, share,
  and the public read-only view.

The UI exposes three pages: **Connections** (connect + a single per-source **Sync** with staged
progress and a **Cancel** control), **Knowledge** (full-screen chat with history, a provider
switcher, and richly formatted answers with source chips), and **Onboarding** (plans, day view,
quiz).

---

## 10. Configuration

| Setting | Purpose |
|---|---|
| `ATLASSIAN_CLIENT_ID` / `ATLASSIAN_CLIENT_SECRET` / `ATLASSIAN_REDIRECT_URI` | Atlassian OAuth app - required to connect |
| `ATLASSIAN_OAUTH_SCOPES` | Confluence + Jira read scopes (+ `offline_access`, `read:me`) |
| `EMBEDDING_MODEL` | Local embedding model (default `BAAI/bge-small-en-v1.5`, 384-dim) |
| `CONFLUENCE_WEBHOOK_SECRET` / `JIRA_WEBHOOK_SECRET` | Enable the respective webhook endpoints |

The database schema is managed by Alembic migrations; embeddings run locally with no external
dependency.
