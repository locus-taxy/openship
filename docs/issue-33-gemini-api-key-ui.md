# Issue #33 — Gemini API Key Management via UI

## Overview

Today, the Gemini API key is configured server-side in the `.env` file and is shared across all users. We want to move this to a per-user model where each user provides and manages their own Gemini API key through the UI.

---

## Problem Statement

The current setup has two key limitations:

1. **Not multi-tenant** — all users share a single API key, meaning all AI generation costs are billed to one account with no way to track or attribute usage per user.
2. **No user control** — if the shared key is missing, expired, or over quota, every user is blocked. Users have no way to self-serve.

---

## Proposed Solution

Each user will store their own Gemini API key in the database. The key will be used exclusively for that user's generate calls. If a user has not set a key, they will be prompted to add one via a Settings panel before they can generate content.

The server-side `.env` `GEMINI_API_KEY` will be deprecated — all users, including developers, will set their key through the UI.

---

## Scope of Changes

### Database

| Change | Detail |
|---|---|
| New column | `gemini_api_key VARCHAR(512) NULL` on the `users` table |
| Migration | Additive Alembic migration — nullable column, no downtime, fully reversible |
| Storage | Plain text at this stage (encryption at rest is listed as a future improvement) |

### Backend

| File | Change |
|---|---|
| `models/user.py` | Add `gemini_api_key: Optional[str]` field |
| `services/gemini.py` | Remove `.env` fallback. Both generate functions accept `user_api_key`. Return `HTTP 400` if key is missing |
| `services/user.py` | Add `update_gemini_api_key(user_id, api_key)` |
| `controllers/auth.py` | Add `get_settings()` and `save_settings()` |
| `controllers/syllabus.py` | Pass `current_user.gemini_api_key` to generate call |
| `controllers/content.py` | Pass `current_user.gemini_api_key` to both generate calls |
| `routes/auth.py` | Two new protected endpoints (see below) |
| `schemas/auth.py` | Add `SaveSettingsRequest` |

### New API Endpoints

Both endpoints are protected by the existing `AuthMiddleware`.

#### `GET /auth/me/settings`
Returns whether the user has a key configured. The key value is never sent to the client.

```json
{ "has_gemini_api_key": true }
```

#### `PUT /auth/me/settings`
Save or remove the user's Gemini API key.

```json
// Save
{ "gemini_api_key": "AIzaSy..." }

// Remove
{ "gemini_api_key": null }
```

```json
// Response
{ "status": "success", "has_gemini_api_key": true }
```

### Frontend

| File | Change |
|---|---|
| `services/index.ts` | Add `putRequest` helper |
| `store/index.tsx` | Add `settingsOpen` flag to Zustand store so any component can open the Settings dialog |
| `components/nav-user.tsx` | Add gear icon (⚙) next to theme toggle in sidebar footer → opens Settings dialog |
| `plugins/syllabi/index.tsx` | Catch `HTTP 400` on generate → show toast with "Open Settings" action |
| `plugins/syllabi/detail.tsx` | Catch `HTTP 400` on generate → show toast with "Open Settings" action |

#### Settings Dialog

- Opened via the gear icon in the sidebar footer
- Shows a **green status card** when a key is set, **amber** when not
- Password-style input with show/hide toggle
- Remove key option
- Link to Google AI Studio for users who need to create a key

#### Toast with Action

When a user attempts to generate content without a key, instead of a generic error they see:

> **Gemini API key not set**
> Add your API key in Settings to generate content.
> `[Open Settings]`

Clicking **Open Settings** opens the dialog inline — no page navigation needed.

---

## User Flow

### First-time setup
1. User signs up and logs in
2. User navigates to a course and clicks Generate Syllabus or Generate Content
3. Toast appears: *"Gemini API key not set"* with an **Open Settings** button
4. User clicks Open Settings → pastes their key from Google AI Studio → Save
5. Generation proceeds normally

### Updating or removing the key
1. Click the gear icon (⚙) in the sidebar footer
2. Current status is shown (green = key is set)
3. Enter a new key and Save to replace, or click the X to remove

---

## What Is Not Changing

- `GEMINI_API_URL` remains server-side in `.env` (non-secret endpoint URL)
- Auth flow, JWT tokens, cookies — no changes
- All existing routes and business logic — no changes
- All other `.env` variables — no changes

---

## Security

| Concern | How it's handled |
|---|---|
| Key never exposed to client | `GET /auth/me/settings` returns only `has_gemini_api_key: bool` |
| Key scoped per user | Each user's key is only used for their own requests |
| Endpoint access | Both settings endpoints are behind `AuthMiddleware` |
| Encryption at rest | Not in this iteration — listed as a follow-up |

---

## Deployment Steps

1. Run `alembic upgrade head` on the server — adds the nullable column with no downtime
2. Remove `GEMINI_API_KEY` from server `.env`
3. Each user sets their own key via Settings on next login

---

## Future Improvements

- **Encryption at rest** — encrypt the stored API key using `cryptography.fernet` before saving to the database
- **Key validation on save** — make a lightweight test call to Gemini on save to verify the key is valid before storing
- **Admin fallback key** — optionally allow an admin-configured default key for users who haven't set their own
