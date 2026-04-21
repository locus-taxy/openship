# Feature Proposal — Multi-LLM Support
**Issue:** #40 | **Status:** In Progress

---

## Problem

Openship is locked to a single LLM provider (Google Gemini) using one shared API key stored on the server. This means:
- All users share the same quota — one user can exhaust it for everyone
- If Gemini is down, generation is unavailable for all users
- Users with OpenAI, Anthropic, or Mistral accounts cannot use those providers

---

## Solution

Allow each user to bring their own API key from any supported LLM provider and choose their preferred model. All generation runs under the user's own credentials. The server will hold no global LLM key.

**Supported providers:** Google Gemini, OpenAI, Anthropic, Mistral

---

## Technology: Instructor Library

We use the **Instructor** library (v1.15.1 — `pip install instructor`) to call LLMs and get back structured, validated Pydantic objects instead of raw text strings.

**Why Instructor over calling provider SDKs directly?**
- Without Instructor, parsing LLM JSON responses is fragile — the model can return malformed output, wrong field names, or missing fields, and you have to handle every case manually
- Instructor wraps the provider client, enforces the response shape via a Pydantic model, and automatically retries if the output is malformed
- It provides one unified interface for all providers — only the client setup changes; every generation call looks identical regardless of whether it hits Gemini, OpenAI, Anthropic, or Mistral

**Docs:** https://python.useinstructor.com/ | **Providers page:** https://python.useinstructor.com/providers/

---

## Schema Changes

### New `llm_providers` table (lookup table)

A dedicated table that holds all supported LLM providers. This is the single source of truth for provider information — other tables reference it by integer ID.

| Column | Type | Purpose |
|---|---|---|
| `id` | Integer | Primary key — auto-generated, used as FK everywhere |
| `name` | VARCHAR(50) | Internal identifier: `gemini`, `openai`, `anthropic`, `mistral` |
| `label` | VARCHAR(100) | Display name shown in the UI: `Google Gemini`, `OpenAI`, etc. |

Seeded on first migration:

| id | name | label |
|---|---|---|
| 1 | gemini | Google Gemini |
| 2 | openai | OpenAI |
| 3 | anthropic | Anthropic |
| 4 | mistral | Mistral |

To add a new provider in the future, insert one row — no code change needed.

---

### `users` table

Current fields (unchanged):

| Column | Type | Purpose |
|---|---|---|
| `id` | Integer | Primary key |
| `email` | VARCHAR(255) | Unique login email |
| `name` | VARCHAR(100) | Display name |
| `hashed_password` | Text | Bcrypt-hashed password |
| `is_active` | Boolean | Account status |
| `created_at` | DateTime | Account creation timestamp |
| `updated_at` | DateTime | Last update timestamp |

One new column being added:

| Column | Type | Default | Purpose |
|---|---|---|---|
| `llm_provider_id` | Integer (FK) | NULL | Points to `llm_providers.id` — tracks which provider the user currently has active. NULL means not configured yet. |

### New `user_api_keys` table

API keys and model choices are stored in a dedicated table, not on the users table. This keeps the users table clean and allows one row per provider per user.

| Column | Type | Purpose |
|---|---|---|
| `id` | Integer | Primary key |
| `user_id` | Integer (FK) | Foreign key → `users.id` |
| `llm_provider_id` | Integer (FK) | Foreign key → `llm_providers.id` |
| `llm_model` | VARCHAR(100) | The model chosen for this provider, e.g. `gpt-4o`, `gemini-2.5-flash-lite`. NULL = use provider default. |
| `api_key` | VARCHAR(1024) | Partially encrypted API key (see API Key Storage section) |
| `created_at` | DateTime | When this key was first saved |
| `updated_at` | DateTime | When this key was last updated |

A user can have up to 4 rows in this table — one per provider. Switching providers does not delete other rows, so users can switch back without re-entering keys. The `llm_provider_id` column on the `users` table tracks which row is currently active.

**Migration files:**
- `alembic/versions/e3f4g5h6i7j8_*` — creates `user_api_keys` table
- `alembic/versions/f4g5h6i7j8k9_*` — creates `llm_providers` table, seeds 4 providers, migrates `llm_provider` VARCHAR columns to integer FK columns on both `users` and `user_api_keys`

---

## API Key Storage

API keys cannot be hashed (like passwords) because hashing is one-way — we would never be able to recover the original key to send to the provider's API.

Instead we use **partial encryption**: only the last 5 characters of the key are encrypted using AES-128-CBC (Python `cryptography.Fernet`). The rest of the key is stored as plaintext. The stored value in the database looks like:

```
sk-abc123def456||ENC||<fernet_token_of_last_5_chars>
```

**Why AES-128 and not AES-256?**
Fernet (the encryption library we use) uses AES-128-CBC with HMAC-SHA256. AES-128 is still considered secure by NIST and has not been broken. We chose Fernet because it is a well-audited, simple, and hard-to-misuse implementation. Upgrading to AES-256 is a future option if required by compliance.

**Why encrypt only the last 5 characters?**
If an attacker gets the database, they can read most of the key but the last 5 characters are an encrypted Fernet token — the full stored string cannot be used directly as an API key. If they try to decrypt the whole stored value using common tools, they fail because only the suffix was encrypted. To recover the real key they need to know the exact split strategy AND have `LLM_ENCRYPTION_KEY` from the server environment.

**Where the encryption key is stored:** In the server's `.env` file as `LLM_ENCRYPTION_KEY`. It never touches the database. An attacker needs both the database AND the server environment to recover any API key.

**`.env.example` entry:**
```
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
LLM_ENCRYPTION_KEY=your-generated-fernet-key-here
```

**Key rotation strategy (if `LLM_ENCRYPTION_KEY` is compromised):**
1. Generate a new Fernet key
2. Run a one-time script: decrypt every `api_key` in `user_api_keys` using the old key, re-encrypt with the new key, save
3. Update `LLM_ENCRYPTION_KEY` in the server environment and restart

The actual API key is never returned to the frontend after saving — the API only returns a boolean (key saved: yes/no). Only a masked placeholder (`••••••••`) is shown in the UI.

**Known gap:** Rate limiting on the key-save and model-verify endpoints is not yet implemented. This will be added as a follow-up to prevent brute-force or abuse of those endpoints.

---

## API Endpoints

All endpoints require a valid session cookie. Auth is enforced by global middleware.

---

### `GET /auth/me/settings`

Returns the user's current LLM configuration. This is called on page load to populate the UI.

**Request:** No body, no query params.

**Response (200):**
```json
{
  "llm_provider": "gemini",
  "llm_model": "gemini-2.5-flash-lite",
  "provider_keys": {
    "anthropic": false,
    "gemini": true,
    "mistral": false,
    "openai": false
  },
  "supported_providers": [
    { "id": 3, "value": "anthropic", "label": "Anthropic" },
    { "id": 1, "value": "gemini",    "label": "Google Gemini" },
    { "id": 4, "value": "mistral",   "label": "Mistral" },
    { "id": 2, "value": "openai",    "label": "OpenAI" }
  ],
  "provider_models": {
    "gemini": ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"],
    "openai": ["gpt-4o-mini", "gpt-4o"],
    "anthropic": ["claude-3-5-haiku-latest", "claude-3-5-sonnet-latest"],
    "mistral": ["mistral-small-latest", "mistral-large-latest"]
  }
}
```

`provider_keys` tells the UI which providers have a key saved — the actual key is never returned. If `llm_provider` is `null`, the user has not configured a provider yet.

**Error responses:** 401 if not logged in.

---

### `PUT /auth/me/settings`

Saves the user's provider selection, API key, and model choice.

**Request body:**
```json
{
  "llm_provider": "openai",
  "api_key": "sk-...",
  "llm_model": "gpt-4o"
}
```

All three fields are optional:
- Send `api_key` with a value → save/update the key for that provider
- Send `api_key: ""` (empty string) → **delete** the saved key for that provider
- Omit `api_key` (send `null`) → leave the existing key untouched
- Send only `llm_model` → update just the model choice

**Response (200):**
```json
{
  "status": "success",
  "llm_provider": "openai",
  "llm_model": "gpt-4o",
  "has_key": true
}
```

**Error responses:**

| Status | Detail | Cause |
|---|---|---|
| 400 | `"Unsupported provider 'xyz'..."` | Provider not in supported list |
| 401 | `"Not authenticated"` | No valid session |

---

### `GET /auth/me/models?provider=openai`

Returns the list of available text-generation models for the given provider. If the user has a key saved for that provider, the list is fetched live from the provider's API and cached for 1 hour. If no key is saved, returns a hardcoded fallback list.

**Query param:** `provider` — one of `gemini`, `openai`, `anthropic`, `mistral`

**Response (200):**
```json
{
  "provider": "openai",
  "models": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "o1", "o3-mini"],
  "source": "live"
}
```

`source` is either `"live"` (fetched from provider API, cached) or `"fallback"` (hardcoded defaults, no key saved).

**How models are filtered:** Any model whose ID contains these keywords is excluded: `tts`, `audio`, `image`, `embed`, `vision`, `video`, `lyria`, `research`, `live`, `nano-banana`. The last one (`nano-banana`) is the internal codename of an experimental Gemini model that is not suitable for text generation — it is filtered out by name. For OpenAI, only `gpt-*`, `o1`, and `o3` series models are included since OpenAI's list endpoint returns many non-chat models.

**Error responses:**

| Status | Detail | Cause |
|---|---|---|
| 400 | `"Unsupported provider 'xyz'."` | Invalid provider value |
| 401 | `"Not authenticated"` | No valid session |

---

### `POST /auth/me/models/verify?provider=openai&model=gpt-4o`

Verifies a custom model ID by making a real minimal test call to the provider. Returns whether the model is valid and usable with the user's saved key.

**Query params:** `provider`, `model`

**Response (200 — model valid):**
```json
{ "ok": true }
```

**Response (200 — model invalid):**
```json
{ "ok": false, "reason": "Model 'gpt-99' not found for OpenAI." }
```

**Response (200 — quota hit but model exists):**
```json
{ "ok": true, "note": "Quota limit hit but model exists." }
```

**Error responses:**

| Status | Detail | Cause |
|---|---|---|
| 400 | `"No API key saved for this provider."` | User has no key for this provider |
| 400 | `"Unsupported provider 'xyz'."` | Invalid provider value |
| 401 | `"Not authenticated"` | No valid session |

---

## Error Handling — What Users See

| Scenario | HTTP Status | What the UI shows |
|---|---|---|
| No provider or key configured | 400 | Toast: "LLM not configured — Add your provider and API key in Settings." + **Open Settings** button |
| API key revoked or expired | 400 | Toast: "Invalid API key — Please update it in Settings." |
| Provider quota exhausted | 429 | Toast: "Quota exceeded — wait or check your billing." |
| Provider is down / unreachable | 500 | Toast: "Failed to generate — try again later." |
| Custom model ID not found | — | Inline error under verify input: "Model 'xyz' not found for OpenAI." |
| Model verify passes but quota hit | — | Inline success: "Model exists (quota limit hit but it's valid)." |

---

## Migration & Rollout Plan

**Database migrations run in order:**

`e3f4g5h6i7j8_*`:
- Creates `user_api_keys` table with VARCHAR `llm_provider` column
- Migrates any existing per-provider key columns from `users` into `user_api_keys`
- Drops old key columns from `users`

`f4g5h6i7j8k9_*`:
- Creates `llm_providers` lookup table and seeds 4 providers
- Adds `llm_provider_id` integer FK columns to both `users` and `user_api_keys`
- Populates FK columns from existing VARCHAR values
- Drops the VARCHAR `llm_provider` columns from both tables

**Impact on existing users:**
All existing users will have `llm_provider_id = NULL` and no rows in `user_api_keys` after migration. This means:
- If they try to generate a syllabus or chapter, they get a 400: "LLM provider and API key not set"
- The UI will show a toast with an **Open Settings** button directing them to configure their own key
- No generation will silently fall back to the old shared key

**Removing the global key:**
`GEMINI_API_KEY` will be removed from `config.py` and `.env.example`. Any server currently running with this key will need to remove it from the environment before deploying this change. There is no backward compatibility — this is an intentional breaking change for server operators. Users are unaffected since they configure their own keys through the UI.

---

## What We Are Building

### 1. Per-user LLM configuration (Database)
Create a new `llm_providers` lookup table (seeded with the 4 supported providers), add one new column (`llm_provider_id` integer FK) to the `users` table, and create a new `user_api_keys` table that stores each user's API key and model choice per provider — one row per provider per user.

### 2. Unified LLM service (Backend)
A single service (`services/llm.py`) that handles syllabus and chapter generation across all providers using the Instructor library — which enforces structured, validated output from any LLM via Pydantic models.

### 3. API Key Management UI (Frontend)
A dialog accessible from the sidebar where users can:
- Add their API key for any provider
- Update a saved key (opens an input field to replace it)
- Delete a saved key (two-step confirmation — click Delete, then confirm)
- Select a model from a live-fetched dropdown (shows spinner while loading)
- Enter and verify a custom model ID that is not in the list

The actual API key is never shown or returned to the frontend after saving — only a masked placeholder (`••••••••`) is displayed.

### 4. Dynamic Model Switching (Frontend)

When a user selects a different provider, the frontend immediately calls `GET /auth/me/models` for that provider. The model dropdown is populated with the results. The full flow:

```
User selects "OpenAI" from provider dropdown
  → Frontend calls GET /auth/me/models?provider=openai
  → Backend checks 1-hour cache; if expired, calls OpenAI's list API
  → Returns filtered list of text-generation models
  → Model dropdown is populated with live results
  → User picks "gpt-4o" and saves
  → PUT /auth/me/settings  { llm_provider: "openai", llm_model: "gpt-4o" }
  → All future generation calls use this user's openai_key and gpt-4o
```

### 5. Inline LLM Switcher (`llm-bar.tsx`)

Two compact dropdowns shown at the top of the syllabi list and syllabus detail pages:

```
[✓ Google Gemini ▾]   [gemini-2.5-flash-lite ▾]
```

- Providers that have a key saved show a checkmark
- Providers without a saved key show a settings icon — clicking them opens the full settings dialog instead of switching
- If no provider is selected, the provider pill shows **"Set provider"** in amber — clicking it opens the provider dropdown
- If a provider is selected but has no key saved, a **"Add API key →"** link appears next to the pill — clicking it opens the settings dialog
- Changes are saved immediately via `PUT /auth/me/settings` — no separate Save button

---

## Key Design Decisions

| Decision | Reason |
|---|---|
| `llm_providers` lookup table with auto-increment integer ID | Integer FKs are faster to join/index than VARCHAR; adding a new provider requires only one DB insert, no code change |
| Separate `user_api_keys` table, one row per provider | Switching providers does not erase other saved keys; users table stays clean |
| `llm_provider_id` integer FK on `users` | Acts as a pointer to the currently active provider — avoids needing an `is_active` flag on each key row; faster joins than string comparison |
| Model list fetched live from provider API | New models appear automatically without any code changes |
| Model list cached for 1 hour in memory | Avoids hitting the provider API on every request |
| API keys never returned to the frontend | Security — only a yes/no flag is sent to the client |
| Custom model verification via real test call | Lets users use any model, including ones released after this feature ships |
| Partial encryption (last 5 chars) | DB leak alone is not enough to reconstruct the key — attacker also needs server env |

---

## Testing Strategy

| Area | Approach |
|---|---|
| `services/encryption.py` | Unit tests: encrypt then decrypt returns original; legacy plaintext passes through unchanged; short keys (≤5 chars) handled via FULL: prefix |
| `services/user.py` | Unit tests: upsert creates row when none exists, updates when row exists, deletes when `api_key=""` |
| `GET /auth/me/models` | Integration test per provider: mock the provider list API, assert filtering removes non-text models |
| `POST /auth/me/models/verify` | Integration test: mock provider returning 404 → `ok: false`; mock quota error → `ok: true` |
| Provider generation | Each provider tested with a real minimal call in a local dev environment — not mocked in CI (would require live keys) |
| Migration | Test on a copy of production DB before deploying — verify all existing user rows migrate correctly and old columns are dropped |

---

## Files to Create / Modify

| File | Action |
|---|---|
| `services/llm.py` | Create — Instructor client setup for all 4 providers, `generate_syllabus_json`, `generate_chapter_html`, model listing, model verification |
| `services/encryption.py` | Create — `encrypt_api_key` (encrypt last 5 chars), `decrypt_api_key` (reverse), legacy plaintext passthrough |
| `models/llm_provider.py` | Create — SQLModel definition for `llm_providers` lookup table |
| `models/user.py` | Modify — replace `llm_provider VARCHAR` with `llm_provider_id Integer FK → llm_providers.id` |
| `models/user_api_key.py` | Create — SQLModel definition for `user_api_keys` table with `llm_provider_id` integer FK |
| `services/user.py` | Modify — all queries use `llm_provider_id`; added `get_provider_by_name`, `get_provider_by_id` helpers |
| `controllers/auth.py` | Modify — resolves provider name → ID via `_resolve_provider()`; `get_settings`, `save_settings`, `list_models`, `verify_custom_model` all use integer IDs internally |
| `routes/auth.py` | Modify — 4 new routes: `GET /me/settings`, `PUT /me/settings`, `GET /me/models`, `POST /me/models/verify` |
| `controllers/syllabus.py` | Modify — pass `get_user_api_key(user)` and `get_user_model(user)` into `generate_syllabus_json` instead of the old shared key |
| `controllers/content.py` | Modify — same pattern: pass user's own key and model into `generate_chapter_html` for both single-chapter and bulk generation |
| `config.py` + `.env.example` | Modify — remove `GEMINI_API_KEY`, add `LLM_ENCRYPTION_KEY` with generation instructions |
| `requirements.txt` | Modify — add `cryptography` package for Fernet encryption |
| `database.py` | Modify — import `LlmProvider`, `User`, `UserApiKey` so SQLModel registers all tables at startup |
| `alembic/versions/e3f4g5h6i7j8_*` | Create — creates `user_api_keys` with VARCHAR `llm_provider`, migrates data from old columns |
| `alembic/versions/f4g5h6i7j8k9_*` | Create — creates `llm_providers`, seeds 4 providers, migrates VARCHAR → integer FK on both tables |
| `ui/src/components/nav-user.tsx` | Modify — full settings dialog with per-provider key add/update/delete, live model dropdown, custom model verify |
| `ui/src/components/llm-bar.tsx` | Create — inline provider + model switcher; shows "Set provider" pill (amber) when no provider selected, "Add API key →" link when provider set but no key saved |
| `ui/src/app/plugins/syllabi/index.tsx` + `detail.tsx` | Modify — add `<LlmBar />` in page header; handle 429 toast alongside 400 |
