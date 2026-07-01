# Confluence Knowledge Platform (RAG): Design

**Status:** Plan · **Component:** Openship · knowledge/onboarding · **Owner:** Yogesh K

This is the plan for a Confluence-backed knowledge platform: ingest a company's entire
Confluence once, store it as a searchable vector knowledge base, and serve many
**sections** (Onboarding, Company Info, …) via RAG. Onboarding is the first section.

---

## The idea

A company's knowledge lives in Confluence. Instead of hand-picking a few onboarding
docs, we ingest **everything once**, turn it into a searchable knowledge base, and let
people ask about anything. Different **sections** (Onboarding, About the Company, …)
are just different views over the same base: a retrieval filter plus a prompt.

The engine is **RAG** (Retrieval-Augmented Generation):

1. **Ingest** every page from every space.
2. **Chunk** each page into small pieces and **embed** each chunk into a vector.
3. **Store** vectors in Postgres (pgvector).
4. On a question, **embed** the question, **retrieve** the most similar chunks, and
   **feed only those** to the LLM to generate the answer.

We never send the whole corpus to the LLM. Retrieval narrows thousands of pages down to
the handful that matter, so it scales and stays cheap.

---

## How it works, end to end

```
Connect Confluence
  → Ingest ALL pages  → chunk → embed → store vectors (pgvector)
                                                   │
  Ask (any section) → embed question → nearest-k chunks (± section filter)
                                                   → LLM → answer
                                                   ↑
                              Webhooks re-embed changed pages (freshness)
```

Onboarding is one section built on top of this: the structured 7-day plan, day content,
and quiz are generated from **retrieved** chunks, and there's also a freeform
"ask about onboarding" box.

---

## 1 · Chosen stack

| Concern | Choice | Why |
|---|---|---|
| Vector store | **pgvector** (Postgres extension) | No new infra; you already run Postgres; scales to millions of chunks |
| Embeddings | **Gemini `text-embedding-004`** (system key) | Strong, cheap, already using Gemini; ingestion-safe with batching + backoff |
| LLM (generation) | **Per-user** saved key (as today) | Answers use the user's provider; only embeddings are system-funded |
| Ingestion scope | **All spaces, all pages** | Ingest everything; relevance is decided at query time by retrieval |
| Sections | **Filter + prompt** over one store | Flexible, scalable; start with Onboarding |
| Onboarding output | **Structured plan/quiz + freeform Q&A** | Keep the existing flow, add ask-anything |

**Key split:** the **LLM stays per-user**; **embeddings are a company-wide system job**
funded by a single server-configured key (like the Atlassian creds in `.env`).

---

## 2 · Architecture

```
┌─ Company ─────────────────────────────────────────────┐
│  Confluence: spaces · pages · search API · webhooks    │
└───────────────────────────┬───────────────────────────┘
                            ▼
┌─ Ingestion layer ─────────────────────────────────────┐
│  OAuth + tokens · fetch all pages · chunk              │
│  embed (Gemini, batched + throttled + resumable)       │
│  webhook receiver · reconciler                         │
└───────────────────────────┬───────────────────────────┘
                            ▼
┌─ Knowledge base (pgvector) ───────────────────────────┐
│  document_pages (one row / page, per company)          │
│  document_chunks (many / page, each with an embedding) │
└───────────────────────────┬───────────────────────────┘
                            ▼
┌─ Retrieval + sections ────────────────────────────────┐
│  embed query → nearest-k (± section/space filter)      │
│  section = retrieval filter + prompt template          │
└───────────────────────────┬───────────────────────────┘
                            ▼
┌─ Sections (UI) ───────────────────────────────────────┐
│  Onboarding: 7-day plan · day content · quiz · Q&A     │
│  Company Info · (future sections) · ask anything       │
└────────────────────────────────────────────────────────┘
```

Everything above the knowledge base is tenant-scoped by `company_id`.

---

## 3 · Connecting Confluence

We register one Atlassian OAuth 2.0 app. A company connects once (the first employee to
open the platform); everyone else reuses that connection. Tokens are stored at the
**company** level, encrypted, and auto-refreshed.

Note on the Confluence API: we read through the **search API** (`content/search` with
`expand=body.storage,version,...`), which works with classic OAuth scopes. (The v1
`/space` and `/content/{id}` collection endpoints are unavailable and the v2 API requires
granular scopes, so search is the reliable path.)

---

## 4 · Ingestion: all docs, once

We ingest every space and every page (personal `~` spaces excluded); relevance is decided
later by semantic search, not upfront.

```
1. List all spaces (search cql=type=space)
2. For each space: page through all pages (content/search, body expanded)
3. Upsert each page into document_pages (skip-if-unchanged by version)
4. Chunk each new/changed page (~800 tokens, ~100 overlap)
5. Embed chunks in batches → store in document_chunks
```

Runs as a **resumable background job** tracked in `ingestion_jobs` (progress + cursor).
Add-only and idempotent: re-running skips pages whose version is unchanged.

### Embedding at scale without blowing the free tier

Embedding "all docs" is thousands of calls, so ingestion is built to stay under limits:

- **Batch** many chunks per embedding request.
- **Throttle** to respect the requests-per-minute cap (token-bucket / pacing).
- **Exponential backoff + retry** on `429`.
- **Two-pass + resumable:** store chunk *text* first, embed in a second pass; on a limit
  or crash, resume from the last embedded chunk instead of restarting.
- **Fallback:** if the free tier is still too tight for a first full ingest, a local
  open-source embedder (sentence-transformers) has no API limit. Same interface, swap the
  provider.

---

## 5 · Chunking

A **chunk** is a small slice of a page (~800 tokens) with a little overlap (~100 tokens)
so meaning that straddles a boundary isn't lost. Each chunk is embedded separately and
stored with its page's metadata (page id, space, title). Chunking gives:

- **Precision:** retrieve the exact paragraph, not a 10-page doc.
- **Clean vectors:** one topic per vector instead of a blurry page average.
- **Context fit:** feed the LLM a few on-target chunks, not whole pages.

---

## 6 · Vector store & retrieval (pgvector)

`document_chunks` holds the text + its embedding. Retrieval is a nearest-neighbour query:

```sql
SELECT content, page_id
FROM document_chunks
WHERE company_id = :company            -- tenant isolation
  -- (optional section/space filter here)
ORDER BY embedding <=> :query_embedding  -- <=> = vector distance
LIMIT :k;
```

An HNSW index on `embedding` keeps this fast at scale. The retrieved chunks (plus their
source page links) are what we hand to the LLM.

---

## 7 · Sections

A **section** is a retrieval filter + a prompt template over the same store:

| Section | Retrieval | Prompt |
|---|---|---|
| Onboarding | semantic match to the day's topic (optionally scoped to eng spaces) | "structure this into onboarding content…" |
| Company Info | semantic match to the question | "answer factually about the company…" |
| (future) | … | … |

Sections are query-time views, so adding one is a filter + a prompt, not a re-ingest.
We can attach per-page `section_tags` later (by space/label or a cheap classifier) if we
want hard scoping, but it isn't required to start.

---

## 8 · Onboarding section (built first)

Both outputs, both RAG-sourced:

- **Structured:** the 7-day plan, day content, and final quiz. Generation retrieves the
  relevant chunks per topic/role and structures them (reuses the current plan/day/quiz UI).
- **Freeform Q&A:** an "ask about onboarding" box: retrieve → answer with citations.

Role filtering rides on retrieval: a Backend vs DevOps plan pulls different chunks because
the query embeddings differ.

---

## 9 · Freshness & correctness

- **Webhooks** (`page_created` / `updated` / `removed`): re-chunk and **re-embed** just the
  changed page; deactivate removed pages so their chunks stop being retrieved.
- **Reconciler:** periodic full re-list to catch missed webhooks (deactivate vanished
  pages, re-embed changed ones).

---

## 10 · Data model

All tables are tenant-scoped by `company_id`.

### `companies`

| Column | Notes |
|---|---|
| `id` | Primary key |
| `name` | Company name |
| `domain` | Email domain (e.g. `locus.sh`); maps an employee to their company/tenant |
| `created_at` / `updated_at` | Timestamps |

### `confluence_connections` (the token store)

One row per company; tokens are **encrypted at rest** (Fernet, via `encrypt_secret`).

| Column | Notes |
|---|---|
| `id` | Primary key |
| `company_id` | One connection per company (unique) |
| `site_url` | The Atlassian site (e.g. `https://locussh.atlassian.net`) |
| `cloud_id` | Site cloud id; used in every Confluence API call |
| `access_token` | **Encrypted**. Short-lived (~1h) |
| `refresh_token` | **Encrypted**. Rotating; the new one is persisted on every refresh |
| `token_expires_at` | Drives proactive refresh (with a 60s skew) |
| `webhook_id` | Registered webhook handle |
| `status` | `pending` / `syncing` / `ready` / `error` |
| `connected_by_user_id` | Audit only (who connected); not an ownership grant |

### `document_pages` (one row per Confluence page)

| Column | Notes |
|---|---|
| `id` | Primary key |
| `company_id` | Tenant isolation |
| `confluence_page_id` | Dedup key (unique per company) |
| `version` | Detect changes; skip re-embed if unchanged |
| `space_key` · `title` | Provenance / display |
| `section_tags` | JSON, optional (for hard section scoping later) |
| `is_active` | False when archived/removed upstream |
| `last_synced_at` | Timestamp |

### `document_chunks` (many rows per page)

| Column | Notes |
|---|---|
| `id` | Primary key |
| `company_id` | Tenant isolation |
| `page_id` | FK → document_pages |
| `chunk_index` | Order within the page |
| `content` | The chunk text |
| `embedding` | `vector(768)` (Gemini text-embedding-004) |
| `token_count` | For budgeting |

**`ingestion_jobs`:** `id` · `company_id` · `total_pages` / `processed_pages` · `total_chunks` / `embedded_chunks` · `status` · `error` · `created_at` / `completed_at`

**`onboarding_plans` / `onboarding_days` / `onboarding_quiz` / `quiz_attempts`:** hold the generated plan, day content, and quiz for the Onboarding section; content is generated from retrieved chunks.

---

## 11 · API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/confluence/connect` | Begin OAuth |
| GET | `/confluence/callback` | Store encrypted tokens |
| GET | `/confluence/status` | Connected? indexed doc/chunk counts |
| POST | `/confluence/ingest` | Start full ingest (async) |
| GET | `/confluence/ingest/{job_id}` | Ingest progress |
| POST | `/webhooks/confluence` | created / updated / removed |
| POST | `/knowledge/query` | Section-aware RAG query → answer + citations |
| POST | `/onboarding/generate` | Role-based plan (RAG-sourced) |
| GET | `/onboarding/{id}/day/{n}` | Day content (RAG-sourced) |
| GET/POST | `/onboarding/{id}/quiz` | Quiz (RAG-sourced) |

---

## 12 · Security & tenancy

- **Token encryption:** access/refresh tokens encrypted at rest.
- **Tenant isolation:** every page/chunk query scoped by `company_id`.
- **Embeddings key:** a single server-side key funds ingestion; never a user's key.
- **Webhook authenticity:** shared-secret verification.
- **Least privilege:** read-only Confluence scopes.

---

## 13 · Phased rollout

| Phase | Ships |
|---|---|
| 1 · Connect | OAuth, company-level encrypted tokens, `/status` (done) |
| 2 · Ingest-all | Fetch every page → `document_pages`; resumable job + progress |
| 3 · Embed | pgvector, chunking, batched/throttled embeddings → `document_chunks` |
| 4 · Retrieve | `/knowledge/query`: embed → nearest-k → LLM answer with citations |
| 5 · Onboarding | Plan/day/quiz + freeform Q&A sourced from retrieval |
| 6 · Freshness | Webhooks re-embed changed pages; reconciler |

---

## 14 · Components we'll build

| Component | What it does |
|---|---|
| Confluence connection | One OAuth 2.0 app; company-level connection, `connect` / `callback` / `status` |
| Token store | Company-level tokens, encrypted at rest (Fernet), auto-refreshed; rotating refresh token persisted on every refresh |
| Company resolution | Map an employee to their company/tenant by email domain |
| Confluence client | Read spaces and page bodies via the search API (classic scopes) |
| Ingestion job | Fetch every page from every space (personal `~` spaces excluded); resumable background job with progress |
| Chunker | Split pages into ~800-token chunks with overlap |
| Embedding service | Gemini `text-embedding-004`, batched + throttled + resumable to stay within the free tier |
| Vector store | pgvector: `document_pages` + `document_chunks` with an HNSW index |
| Retriever | Embed the query, return nearest-k chunks (± section/space filter) |
| Section registry | Each section = a retrieval filter + a prompt template |
| Knowledge query API | `/knowledge/query`: section-aware RAG answer with citations |
| Onboarding | Structured plan/day/quiz + freeform Q&A, both RAG-sourced |
| Freshness | Webhooks (re-embed changed pages) + a reconciler |
| UI | Connect, ingest progress, ask-anything, onboarding views |

---

## 15 · Future work

- Per-page `section_tags` via cheap classifier for hard section scoping.
- Re-ranking retrieved chunks (cross-encoder) for higher answer precision.
- More sources behind the same chunker/embedder (Notion, Drive, GitHub wikis).
- More sections (Company Info, Policies, Product) once Onboarding is solid.
- Hybrid search (keyword + vector) for exact-term queries.
