# Challenge: First-Time Ingestion of a Large Atlassian Tenant

**Component:** Openship Knowledge Platform · `onboarding/services/confluence.py`

This is the hardest problem we hit building the knowledge platform: **ingesting a company's
entire Atlassian workspace for the first time**, at real scale, over an API that actively
pushes back. It reads like a normal "loop over projects and save them" task - and it is,
until the tenant is big enough that every hidden assumption breaks at once.

---

## TL;DR

- **Scale:** ~**133,000 Jira issues** across **58 projects** (one project alone, `ES`, had
  **101,384**) plus ~11,000 Confluence pages.
- **Symptom:** a full ingest "succeeded" but only **11 of 58 projects** actually landed.
  Whole projects - and the people in them - were silently missing from search.
- **Root causes (four, discovered one at a time):** a removed Jira endpoint, **rate-limiting
  that dropped entire projects**, an **OAuth token that expired mid-run**, and **memory** that
  would have blown up once we stopped dropping projects.
- **Outcome:** all **133,568 issues across all 51 non-empty projects** ingested, with a reader
  that survives throttling, token expiry, and 100k-issue projects - and is resumable if
  anything still slips.

---

## The setup

Ingestion is a background job: for each project, page through its issues (100 at a time),
normalize each, upsert it into `document_pages`, then chunk + embed into `document_chunks`
(local `fastembed`, no external API). On a small workspace this is boring and works.

The trouble is that a large tenant turns "loop and save" into a **multi-hour, tens-of-
thousands-of-requests** operation against an API with per-app rate limits and ~1-hour access
tokens. Every one of those facts became a bug.

---

## Symptom: "done" but mostly empty

The first real ingest finished as **`done`** - but with a quiet note: *"45 space(s) skipped -
re-ingest to retry."* Only **11 projects** had data. A concrete example surfaced it: a user
asked for a teammate's work and got nothing, even though that teammate (assignee of
`ES-102188`, "Implement SSO in datasmith") was clearly active in Jira. The Engineering Scrum
(`ES`) project - 101k issues - was **entirely absent** from our database.

So the job wasn't failing loudly; it was **succeeding while dropping 78% of the projects.**

---

## Root cause #1 - the Jira search endpoint we used was removed

Atlassian retired the legacy `POST /rest/api/3/search` (offset/`startAt` paging). Calls
returned errors, and every project looked "empty."

**Fix:** move to the **enhanced JQL search** - `GET /rest/api/3/search/jql` with
**token-based pagination** (`nextPageToken`), stopping on `isLast`. This is the current,
supported path and pages cleanly through arbitrarily large projects.

---

## Root cause #2 - rate-limiting dropped *whole projects*

This was the real culprit behind the 45 skips. Two weaknesses compounded:

1. **The retry gave up too easily.** On HTTP **429** ("slow down"), the client retried only
   ~4 times with a fixed 2/4/8s backoff (~14s total) and **ignored Atlassian's `Retry-After`
   header** - the server was literally telling us how long to wait, and we weren't listening.
2. **The fetch was all-or-nothing per project.** `_search_issues` accumulated an entire
   project's pages in memory and returned only at the very end. So if page 50 of a project
   got rate-limited past our few retries, the exception propagated and the **whole project was
   discarded - including the 5,000 issues already fetched.**

Together: during a multi-hour bulk read, sustained 429s would outlast our ~14s of patience,
and each affected project vanished wholesale. Large and late-processed projects (like `ES`)
were the most likely to lose.

**Fix - be a patient, obedient API citizen:**
- **Honor `Retry-After`.** On 429/503, parse the server's requested wait and actually wait it
  (clamped to a sane max of **5 minutes**), instead of a fixed short backoff.
- **Retry more.** Bump attempts from 4 → **10**, so a throttle window gets ridden out rather
  than triggering a skip.
- A project that *still* fails after all that is **skipped, counted, and surfaced** in the
  job note - never fatal - and a later run recovers it.

```python
# the core of it (onboarding/services/confluence.py)
def _retry_after_seconds(resp):        # obey the server's own instruction
    secs = float(resp.headers.get("Retry-After"))
    return secs if secs >= 0 else None

def _retry_delay(resp, attempt):
    server = _retry_after_seconds(resp)
    delay = server if server is not None else _HTTP_RETRY_BACKOFF * (2 ** attempt)
    return min(delay, _HTTP_RETRY_MAX_SLEEP)   # cap a single wait at 5 min
```

---

## Root cause #3 - the OAuth token expired mid-run

With the throttling fixed, the ingest got much further… then died at project ~51 with a
**401**. Atlassian access tokens live ~**1 hour**; a full 133k-issue read takes longer than
that. But the job fetched the token **once at the start** and reused it for the entire run -
so it was **guaranteed to expire partway through** every large ingest. (A user's Atlassian
session dropping mid-run triggered the same failure sooner.)

The first patch refreshed the token *between projects*, but with only a 60-second "about to
expire" margin - so a project that *started* with ~2 minutes of token life left could read
**past** expiry mid-project before the refresh ever triggered.

**Fix - keep the session fresh, with real headroom:**
- Before **each project**, re-read the connection and refresh the token if it's within
  **5 minutes** of expiring (`_TOKEN_SKEW_SECONDS = 300`). Re-reading picks up the refreshed
  expiry so we don't repeatedly refresh a stale in-memory value, and it also picks up a token
  written by a user's reconnect.
- Refresh tokens rotate, and the new one is persisted - so the run stays logged in across the
  full multi-hour read. Applied to **both** ingest and reconcile, for **both** Confluence and
  Jira (they share the reader).

---

## Root cause #4 - memory (the trap the fix exposed)

Ironically, fixing #2 and #3 *created* a new risk. The original job read **every** item from
**every** project into one big `raw_pages` list before indexing - fine when 45 projects were
being dropped and only ~13k issues survived. But now that **nothing** was dropped, the job
would try to hold all **133k issues (plus their chunks) in memory at once** and fall over.

**Fix - stream, don't hoard:**
- **Process one project at a time**: fetch it, upsert its issues, keep only the ids/text of
  pages that need embedding, then **drop that project before reading the next**. Peak memory
  is bounded by the *largest single project*, not the whole tenant.
- **Chunk inside the embed loop**, in ~256-chunk batches - never materialize every chunk of
  the corpus simultaneously.
- Lift a latent **100k-issue-per-project cap** (the pagination safety bound was 1,000 pages ×
  100 = 100,000 - and `ES` has 101,384, so it would have been silently truncated).

A bonus fell out of this ordering: because the structured fields (`assignee`/`reporter`/
`status`) are written during the **read** phase, **people-analytics is correct the moment
reading finishes - long before the hours-long embedding completes.**

---

## Results

| | Before | After |
|---|---|---|
| Jira projects ingested | 11 / 58 | **51 / 58** (the other 7 are genuinely empty) |
| Jira issues | ~13,000 | **133,568** |
| Largest project (`ES`) | missing | **101,390 issues** |
| Failure mode on a big run | drops ~45 projects, or dies on 401 | completes; survives throttling + token expiry |
| Peak memory | grows with the whole tenant | bounded by one project |

---

## Principles that generalized

1. **Obey the server.** `Retry-After` exists for a reason; honoring it turns "drop the
   project" into "wait and succeed."
2. **Fail per-item, not per-batch.** All-or-nothing fetching means one bad page can erase
   thousands of good rows. Isolate and count failures; make the run resumable.
3. **Long-lived jobs must refresh short-lived credentials** - with headroom, not at the last
   second.
4. **Stream at the granularity of your largest unit of work**, or memory scales with the
   whole dataset instead of the biggest single piece.
5. **Separate the "facts" from the "expensive derived data."** Metadata (who did what) is
   cheap and immediately useful; embeddings are slow and can lag behind - so commit facts
   first and let embeddings catch up.
6. **Back off globally, not just per request.** When an API asks for a long cooldown, the
   right response is to wait it out, not to retry harder.
