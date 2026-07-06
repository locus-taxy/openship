# Openship Knowledge Platform — Design

**Status:** Implemented · **Component:** Openship · `onboarding/` package · **Owner:** Yogesh K

One platform, three surfaces:

1. **Connections** — connect a company's **Atlassian** workspace (one OAuth) and ingest
   **Confluence** pages and **Jira** issues into a single searchable knowledge base.
2. **Onboarding** — generate role-based 7-day onboarding plans, per-day content, and a
   quiz, grounded in the company's **Confluence** docs.
3. **Knowledge** — a ChatGPT-style chat that answers from the company's **Confluence +
   Jira**, with people-analytics (who works on what, counts, leaderboards).

The engine is **RAG** (Retrieval-Augmented Generation): ingest everything once → chunk →
embed → store vectors in Postgres (pgvector) → on a question, embed it, retrieve the
nearest chunks, and feed only those to the LLM. We never send the whole corpus to the
model; retrieval narrows tens of thousands of items down to the handful that matter.

> **Why one doc:** all three surfaces share the same connection, ingestion, tables, and
> retrieval. Onboarding and Knowledge are just different *consumers* of the shared base
> (a source filter + a prompt). Documenting the foundation once avoids drift.

---

## Contents

- [Architecture](#architecture)
- [Part A — Connections & Ingestion (shared)](#part-a--connections--ingestion-shared)
- [Part B — Data model](#part-b--data-model)
- [Part C — Embeddings](#part-c--embeddings)
- [Part D — Retrieval (hybrid + name-aware)](#part-d--retrieval-hybrid--name-aware)
- [Part E — Knowledge chat](#part-e--knowledge-chat)
- [Part F — People questions (count / list / leaderboard)](#part-f--people-questions-count--list--leaderboard)
- [Part G — Onboarding](#part-g--onboarding)
- [Security & multi-tenancy](#security--multi-tenancy)
- [API surface](#api-surface)
- [Configuration](#configuration)

---

## Architecture

```
                         ┌──────────────────────── Atlassian (one OAuth 2.0 app) ───────────────────────┐
                         │   Confluence (pages + blog posts + live docs)   ·   Jira (projects + issues)  │
                         └───────────────────────────────┬──────────────────────────────────────────────┘
                                                          │  read APIs (company-level encrypted tokens)
                        Ingest job (background, resumable, per source)
                                   read → chunk → embed → store
                                                          ▼
                    ┌─────────────────────────── Postgres ───────────────────────────┐
                    │  document_pages (1 row / page|issue, + structured meta)         │
                    │  document_chunks (vector(384), pgvector HNSW cosine index)      │
                    └───────────────────────────────┬─────────────────────────────────┘
                                                     │
             ┌───────────────────────────────────────┼───────────────────────────────────────┐
             ▼                                                                                 ▼
   ONBOARDING (Confluence only)                                              KNOWLEDGE chat (Confluence + Jira)
   role → retrieve → LLM → 7-day plan,                                       question → route:
   per-day content, quiz                                                       • RAG (concept/general) → LLM answer
                                                                               • people path → exact DB (list/count/leaderboard)
```

Freshness: Confluence **webhooks** re-embed changed pages; a **reconcile** job re-scans a
source to catch deletions/restores. Both run as the same kind of background job as ingest.

---

## Part A — Connections & Ingestion (shared)

### A.1 One Atlassian connection, two products

A single Atlassian OAuth 2.0 (3LO) app grants access to **both** Confluence and Jira. We
store **company-level** encrypted tokens once; Confluence and Jira reads reuse the same
`cloud_id` and access token, differing only in the API base:

- Confluence: `https://api.atlassian.com/ex/confluence/{cloud_id}`
- Jira: `https://api.atlassian.com/ex/jira/{cloud_id}`

Scopes (`config.ATLASSIAN_OAUTH_SCOPES`): read-only Confluence + Jira plus
`offline_access` (for a refresh token). Tokens auto-refresh (rotating refresh tokens);
timestamps are stored as **naive UTC** to avoid a DB-session-timezone bug that made valid
tokens look expired.

**Company resolution** (`services/company.py`): a user's company is keyed by their email
— the **domain** for corporate addresses (teammates share one org) or the **full email**
for personal/generic addresses (a private one-person org; the local part alone would
collide — `john@gmail` vs `john@yahoo`). Resolved at **signup** and stored on
`users.company_id` (read-only, shown in Settings → Account; "want a real company → sign up
with its domain"). The connection and all ingested docs are keyed by `company_id`, so
every employee of a company shares one indexed knowledge base — and a **new teammate rides
the existing connection** with no reconnect needed.

### A.2 What we ingest

| Source | Container | Item | Notes |
|---|---|---|---|
| **Confluence** | space (non-personal) | page **and blog post** | Live Docs are `type=page` → captured. Personal (`~`) spaces skipped. |
| **Jira** | project | issue | via the enhanced JQL search (`/rest/api/3/search/jql`, `nextPageToken` paging) |

Reads go through the **search APIs** (work with classic OAuth scopes; the retired v1
GET-by-id and the removed legacy Jira `/search` are avoided). Each item is fetched with
enough expansion to get full text **and metadata** in one call.

### A.3 The ingest job (3 phases, resumable)

`_run_ingest(company_id, job_id, source)` is a background task driven by an
`ingestion_jobs` row (drives the live progress UI):

1. **reading** — list every container, fetch every item. A container that keeps failing
   (after retries) is *skipped and counted*, not fatal.
2. **indexing** — upsert each item into `document_pages`; decide which need (re)embedding
   (new, changed text, or missing chunks). **Resumable**: a page already embedded and
   unchanged is skipped.
3. **embedding** — chunk each to-embed page, embed in **cross-page batches** (~256
   chunks/call — far faster than per-page), store `document_chunks`.

Robustness: only whole-run problems fail the job (no connection, expired session, nothing
embedding at all). Auth 401 mid-run fails loudly (so reconcile can't silently deactivate
the whole base). Orphaned "running" jobs from a process restart are reaped on startup
(`reap_running_jobs`).

**Change detection** (`_upsert_page`): re-embed when the version bumped, the row was
inactive, **or the extracted text differs**. The text check is what catches Jira edits
(their normalized "version" is `None`), so incremental re-ingests are cheap.

### A.4 Freshness

Two independent mechanisms; **reconcile is the reliable baseline, webhooks are an
optimization** on top.

**Reconcile** (`begin_reconcile`, background job, **per source**) re-lists a source and
flips `is_active` for pages that vanished/reappeared upstream. Source-scoped so a
Confluence reconcile never touches Jira docs. Always available — no external setup.

**Webhooks** — the *receiving* side is implemented for **both** sources
(secret-authenticated, tenant-scoped). The endpoint **verifies the secret synchronously**
(bad secret → 401), then **acknowledges instantly** (`200 {"status":"accepted"}`) and does
the fetch+embed in a **`BackgroundTasks`** job — so a burst of webhooks (bulk edit/move)
can't block web workers. The handler never raises. No queue infra: single-item processing
is sub-second (local embeddings), and **reconcile is the durability backstop** for any
dropped event. Add a real durable queue only if you hit high sustained volume or need
at-least-once delivery guarantees.

| | Endpoint | Secret (config) | Events → action |
|---|---|---|---|
| Confluence | `POST /py/webhooks/confluence` | `CONFLUENCE_WEBHOOK_SECRET` | created/updated → re-embed page · removed → deactivate |
| Jira | `POST /py/webhooks/jira` | `JIRA_WEBHOOK_SECRET` | `issue_created`/`issue_updated` → re-embed issue (`_reindex_issue`) · `issue_deleted` → deactivate |

Tenant resolution: Confluence by `cloudId` in the payload; Jira by `cloudId` **or** the
site URL parsed from `issue.self` (matched to the connection's `site_url`). Set the secret
env var to enable an endpoint; unset → the endpoint returns 503 and you rely on reconcile.

> **What "just add config" covers.** Setting the secret makes our endpoint *ready to
> receive*. Atlassian still has to be told to *send* events to it — a one-time
> registration we can't do from config alone (OAuth 3LO apps have no auto-registration):
> - **Jira Cloud:** Settings → System → **WebHooks** → add
>   `https://your-host/py/webhooks/jira?secret=<JIRA_WEBHOOK_SECRET>`, events *Issue
>   created/updated/deleted*.
> - **Confluence Cloud:** no simple admin webhook UI — use an **Automation** rule
>   ("page created/updated → Send web request" to
>   `https://your-host/py/webhooks/confluence?secret=<…>`) or a Connect/Forge app.
>
> The secret may be passed as `?secret=` or the `X-Webhook-Secret` header.

---

## Part B — Data model

All tables are `company_id`-scoped. Packaged under `onboarding/models/`.

### `companies`
One row per company (resolved by email domain).

### `confluence_connections`
The shared Atlassian connection: `cloud_id`, `site_url`, encrypted `access_token` /
`refresh_token`, `token_expires_at` (naive UTC), `status` (`ready` | `error`). Named
"confluence" for history; it powers Jira too.

### `document_pages` — one row per ingested item (Confluence page/blog OR Jira issue)
| Column | Purpose |
|---|---|
| `source` | `confluence` \| `jira` (indexed) — scopes retrieval per feature |
| `confluence_page_id` | source id: Confluence page id **or** Jira issue key |
| `space_key` | Confluence space **or** Jira project key |
| `title`, `content_text` | title + cleaned full text (what gets chunked/embedded) |
| `version` | change-detection (Confluence version number; `None` for Jira) |
| `assignee`, `reporter`, `status` | **structured Jira fields** (indexed) — exact person lookups/counts |
| `meta` (JSONB) | source-specific extras, **no migration needed for new keys**: Jira → `issue_type, priority, labels, created, updated, resolution, status_category, project`; Confluence → `author, last_editor, breadcrumb, labels, updated, type` |
| `is_active` | false when archived/removed upstream |
| unique | `(company_id, source, confluence_page_id)` |

For **Confluence**, `content_text` is prefixed with `Author: … | Last edited by: … | Path:
breadcrumb | Labels: …` so authorship is searchable the same way Jira `Assignee:` is.
For **Jira**, `content_text` embeds `Issue KEY · summary · Status/Type/Priority/Assignee/
Reporter/Labels · description · comments (author-prefixed)`.

### `document_chunks` — one row per ~800-token slice
`content`, `embedding vector(384)` (pgvector, **HNSW cosine** index), `token_count`,
`chunk_index`, `source`. `EMBEDDING_DIM = 384` must match the model + config.

### `ingestion_jobs` — drives the progress UI
`kind` (`ingest` | `reconcile`), `source`, `phase`, `total/processed_spaces`,
`total/processed_pages`, `total/embedded_chunks`, `status`, `error`.

### `knowledge_chats` / `knowledge_messages` — persistent chat
Per-user chats; assistant messages store structured `blocks` (JSON) + `citations` (JSON) +
a flattened `content` (for history / follow-ups).

### `onboarding_plans` / `onboarding_days` / `onboarding_quiz_attempts`
The generated 7-day plan, per-day block content, and quiz attempts.

---

## Part C — Embeddings

- **Local** via `fastembed` — model **`BAAI/bge-small-en-v1.5`**, **384-dim**. No API key,
  no quota, no per-token cost. Model is a lazy singleton, cached on disk; a
  `scripts/warm_embeddings.py` pre-download is wired into `setup.sh`.
- `embed_texts(list)` (ingest, batched) and `embed_query(str)` (retrieval).
- **Key split:** embeddings are a company-wide, system-funded **local** job; the
  **answer LLM stays per-user** (their saved provider key).

*Why a 384-dim small model:* fast, scalable to hundreds of thousands of chunks, and
retrieval quality is dominated by the hybrid layer below, not by embedding size.

---

## Part D — Retrieval (hybrid + name-aware)

`onboarding/services/retrieval.py`. Pure semantic search is great at *meaning* but bad at
*literal tokens* (names, issue keys). So retrieval is **hybrid**:

```
query ─┬─ semantic:  ORDER BY embedding <=> query_vec      (pgvector cosine)
       └─ lexical:   word/phrase match on chunk content    (ranked by weighted hits)
                     → merge (dedup by PAGE) → top-k
```

**Query classification** (`_query_terms`) splits a query into weighted terms and labels it:

- **Issue keys** (`AR-2847`) and **multi-word full names** (`Yogesh Kisslay`) → **phrase
  weight** (2×), so a full-name match outranks a coincidental first-name hit. When a full
  name is present, the lexical filter **requires the whole phrase** — a different "Yogesh"
  is excluded entirely. Capitalized adjacency detects names even with trailing lowercase
  words ("Yogesh Kisslay create").
- **Known-name awareness:** a cached per-company set of real people (from Jira
  `assignee/reporter` + Confluence `author/editor`) lets **lowercase** names ("what is
  sunadh working on") be recognized as entities too. Cache is TTL-refreshed and
  **cleared instantly after a Jira ingest** (`refresh_names`).
- **Adaptive semantic ratio:** an *entity* query (name/key) is keyword-heavy (k−3 / 3); a
  *concept* query ("how do we deploy") is balanced (k/2 each) so synonyms/paraphrases get
  in.
- **Scope:** `sources=["confluence"]` for onboarding; `None` (both) for chat.
- **Dedup by page**, not chunk, so k slots cover k distinct documents.

---

## Part E — Knowledge chat

`onboarding/services/knowledge.py`. Multi-turn, persistent, structured.

**Answer path (`_answer_blocks`):**
1. **People-question path first** (Part F) — if the question is about specific people /
   counts / leaderboards, answer from exact DB lookups (retrieval can only *sample*).
2. Otherwise **RAG**: retrieve across both sources → format context tagged by source
   (`[Confluence]` / `[Jira issue KEY]`) → LLM answers as **typed content blocks** (same
   `BlockRenderer` as onboarding: headings, code, tables, mermaid).

**Grounding & honesty (prompt-enforced):**
- Answer only from the excerpts; if not covered, say so (strict). General/technical
  questions get a clearly-labeled general answer; company-specific "who/what/status"
  questions never guess.
- **Jira role discipline:** `Assignee` = doing the work, `Reporter` = filed it, comment
  author = commented — never conflated; the right verb is used per role.

**Link & citation safety:**
- **Hallucinated-URL scrub** (`_scrub_block_links`): any URL the model emits that is **not
  present in the retrieved excerpts** is stripped (markdown keeps its label). Kills
  `jira.example.com`-style fabrications.
- **Citations** carry `source` + a **deep link** (`/browse/KEY` for Jira,
  `/wiki/pages/viewpage.action?pageId=…` for Confluence), gated by `used_docs`, deduped,
  and filtered to what the answer actually references (by id **or title**, so numeric
  Confluence ids aren't dropped).

---

## Part F — People questions (count / list / leaderboard)

Retrieval returns a **top-k sample** — it cannot enumerate or count. So questions about
people are routed to **exact DB lookups**.

**Cheap gate → planner → route:**
- **Gate** (`_looks_like_person_question`, no LLM): fires on a count/rank cue, a known
  person named in the question, or a **pronoun follow-up** ("about *his* work") when a
  person was named earlier in the chat.
- **Planner** (one small LLM call, `extract_people_query`, **history-aware** so it resolves
  "he/his" → the person discussed): returns `intent` + `people` (+ `metric`).

| Intent | Trigger | Answer (deterministic — numbers/lists straight from DB) |
|---|---|---|
| **list** | "what is X working on", "all work of X", "tell me about X and Y", "what do you think of X" | Complete per-person work: Confluence docs + Jira issues, each with **role**, as clickable links. One section per person. |
| **count** | "who did more, X or Y", "how many issues did X report" | Exact per-role counts (assigned/reported/authored/involved) + comparison table. |
| **leaderboard** | "who reported the most", "top contributors" | `GROUP BY` ranking across everyone, by metric (reported/assigned/authored/involved). Bot/placeholder names filtered. |
| **other** | topic that merely mentions a person ("what did X decide about auth") | Falls through to RAG. |

**Precision — word-boundary matching:** person matching uses **whole-word** regex
(`~*` `\y…\y` in SQL, `\b` in Python), not substring. Prevents "ana" matching
"management"/"Diana" and "raj" matching "Nataraj". Regex-injection-safe (`re.escape`).

**"Involved" = holding a role** (assignee/reporter/author/editor) — *not* a mere text
mention — so common-word names (Mark, Will) don't over-count, and "involvement" means
actual work. Handles single & multiple people; lowercase & full names; deactivated real
users (matched by plain name).

---

## Part G — Onboarding

`onboarding/services/onboarding.py` + `generation.py`. Grounded **only in Confluence**
(`sources=["confluence"]`, pure semantic — a plan wants topical breadth, not literal hits).

- **Plan:** `role` → broad landscape retrieval → LLM → 7 days (topic + task each).
- **Day content:** focused retrieval (role + topic + task) → LLM → typed content blocks
  (rendered by the shared `BlockRenderer`: headings, code, tables, mermaid diagrams).
- **Quiz:** retrieval over the plan's topics → 10 MCQs; attempts persisted.
- Share toggle + public read-only view. Force-regenerate supported.

The UI shows a readiness banner pointing to **Connections** when the KB isn't ready.

---

## Security & multi-tenancy

- **Tenant isolation:** every query is `company_id`-scoped; webhooks scope to the
  connection's company so one tenant's page id can't touch another's.
- **Company email only:** personal email domains are blocked from connecting.
- **Connector identity check:** on OAuth callback we call Atlassian's `/me` (`read:me`
  scope) and require the authorizing Atlassian account's email to **equal the Openship
  login email** — otherwise a user signed into a *personal* Atlassian in their browser
  could bind their personal Confluence/Jira as the whole company's KB. Mismatch or
  unverifiable email → 403, no connection (fail-closed).
- **Secrets:** OAuth tokens encrypted at rest (`services/encryption.py`); webhook
  shared-secret via constant-time compare; embeddings need no secret.
- **LLM keys** stay per-user; only the (local, keyless) embedding job is company-wide.
- **No fabricated links/facts:** URL scrub + strict grounding + deterministic
  people-answers (DB numbers, never LLM-invented).

---

## API surface

Routes under `onboarding/routes/` (mounted at `/py/...`):

- **Connections/Atlassian:** `POST /confluence/connect`, `GET /confluence/callback`,
  `GET /connections/status`, `POST /confluence/ingest?source=`,
  `GET /confluence/ingest/{job_id}`, `POST /confluence/reconcile?source=`,
  `POST /webhooks/confluence`, `POST /webhooks/jira`.
- **Knowledge:** `POST /knowledge/query` (one-shot) + chat CRUD
  (`create/list/get/delete/post_message`).
- **Onboarding:** plan generate/list/get, day content, quiz get/generate, share, public.

UI: **Connections** page (connect + per-source ingest/sync with staged progress),
**Knowledge** full-screen chat (history sidebar, provider switcher, block-rendered
answers with source chips), **Onboarding** (plans, day view, quiz).

---

## Configuration

| Setting | Default / note |
|---|---|
| `ATLASSIAN_CLIENT_ID/SECRET/REDIRECT_URI` | OAuth app (required to connect) |
| `ATLASSIAN_OAUTH_SCOPES` | Confluence + Jira read scopes + `offline_access` |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` (384-dim); keep in sync with `EMBEDDING_DIM` |
| `CONFLUENCE_WEBHOOK_SECRET` | enables the Confluence webhook endpoint |
| `JIRA_WEBHOOK_SECRET` | enables the Jira webhook endpoint |
| `CONFLUENCE_POST_CONNECT_REDIRECT` | where to land after connect |

**Migrations** (Alembic, `onb_*` ids): document_pages/chunks, `source` column,
`ingestion_jobs.source`, Jira `assignee/reporter/status` columns, `meta` JSONB.

**Tests:** full suite green at ~99% total; the `onboarding/` services
(confluence/retrieval/knowledge/generation) at 100%.
