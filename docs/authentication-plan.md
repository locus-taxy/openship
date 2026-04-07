# Authentication Implementation Plan — Openship

**Author:** Yogesh K  
**Date:** March 31, 2026  
**Status:** Implemented  

---

## 1. Current State

Openship currently has **no authentication**. All 9 API endpoints are publicly accessible without any
identity verification.

### Current Problems

| Problem | Impact |
|---------|--------|
| **No user identity** | `user_id` is a random UUID generated at subscription time. There is no login, no signup, no concept of "who is this person." |
| **No route protection** | Any person or bot can call any endpoint — including `/issue-newsletters` (sends emails to ALL subscribers) and `/generate-content` (consumes Gemini API credits). |
| **Email passed in every request** | `/subscribe` and `/generate-syllabus` require the user to manually pass their email. No session awareness. |
| **Frontend auth is fake** | `ProtectedRoute` component always renders children (no guard). Credentials dialog sets a hardcoded `sampleToken` cookie. `/auth/check-token-expiry` and `/auth/logout` are called by the UI but have no backend implementation. |
| **Linkifyi token in env** | A single shared `LINKIFYI_TOKEN` is used for all email sends. No per-user authorization. |

### Security Risks

- **Unauthorized email sending** — Anyone can trigger mass emails via `POST /issue-newsletters`
- **API abuse** — Gemini API calls cost money; no rate limiting or auth means unlimited abuse
- **Data exposure** — `GET /syllabi` returns ALL users' subscriptions to anyone who calls it
- **No audit trail** — No way to know who performed which action

---

## 2. Proposed Solution: JWT Authentication

### Why JWT (JSON Web Tokens)

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **Session-based (cookies)** | Simple, server controls invalidation | Requires server-side session storage, harder to scale | Not preferred for API-first app |
| **JWT (access + refresh tokens)** | Stateless, scalable, FastAPI has built-in support, works well with SPAs | Token revocation requires extra logic | **Recommended** |
| **OAuth2 (Google/GitHub login)** | No password management, trusted providers | Adds external dependency, more complex setup | Phase 2 enhancement |
| **API Keys** | Simple for service-to-service | Not suitable for end-user authentication | Not suitable |

### Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React)                         │
│                                                                  │
│  Signup ──► POST /auth/signup ──► User created (no tokens)       │
│  Login  ──► POST /auth/login  ──► Both tokens set as httpOnly    │
│             cookies by the server                                │
│  Refresh ─► POST /auth/refresh ──► Browser sends cookies auto    │
│  Logout ──► POST /auth/logout ──► Both cookies cleared           │
│                                                                  │
│  No Authorization header — cookies are sent automatically        │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                        BACKEND (FastAPI)                          │
│                                                                  │
│  /auth/signup    — Create user, hash password, return user info  │
│  /auth/login     — Verify password, set access + refresh tokens   │
│                    as httpOnly cookies                            │
│  /auth/refresh   — Read refresh cookie, validate token,          │
│                    verify user exists & is active, set new        │
│                    access token cookie                            │
│  /auth/logout    — Delete both token cookies                     │
│  /auth/me        — Return current user profile                   │
│                                                                  │
│  All other routes: Depends(get_current_user)                     │
│  ──► Decode JWT ──► Fetch user from DB ──► Inject into handler   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. New API Endpoints

### POST /auth/signup

Create a new user account.

**Request Body:**

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `email` | string | yes | Valid email format, unique |
| `name` | string | yes | 2–100 characters |
| `password` | string | yes | Minimum 8 characters |

**Response (201):**

```json
{
  "status": "success",
  "message": "Account created",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "name": "Yogesh",
    "is_active": true
  }
}
```

> **Note:** Signup does NOT return tokens. The user must log in separately after creating an account.

**Error Responses:**

| Status | Reason |
|--------|--------|
| `409` | Email already registered |
| `422` | Validation error (short password, invalid email, etc.) |

**Implementation Notes:**
- Password hashed with `bcrypt` (via `passlib`) before storage. Plain text password is NEVER stored.

---

### POST /auth/login

Authenticate an existing user.

**Request Body:**

| Field | Type | Required |
|-------|------|----------|
| `email` | string | yes |
| `password` | string | yes |

**Response (200):**

```json
{
  "user": {
    "id": 1,
    "email": "user@example.com",
    "name": "Yogesh",
    "is_active": true
  }
}
```

> **Note:** Neither token appears in the response body. Both the `access_token` and `refresh_token` are set as **httpOnly cookies** by the server. The browser stores and sends them automatically.

**Error Responses:**

| Status | Reason |
|--------|--------|
| `401` | Invalid email or password |

---

### POST /auth/refresh

Get a new access token using the refresh token stored in the httpOnly cookie.

**Request Body:** None — the refresh token is read from the `refresh_token` httpOnly cookie sent automatically by the browser.

**Response (200):**

```json
{
  "status": "refreshed"
}
```

> **Note:** The new access token is set as an httpOnly cookie by the server. It does NOT appear in the response body.

**Error Responses:**

| Status | Reason |
|--------|--------|
| `401` | No refresh token cookie present |
| `401` | Refresh token expired or invalid |
| `401` | Invalid token type (not a refresh token) |
| `401` | Invalid token payload (missing `sub` claim) |
| `401` | User not found or inactive |

**Implementation Notes:**
- After decoding the token, the server verifies the user still exists and `is_active` is `True` before issuing a new access token cookie.

---

### GET /auth/me

Return the currently authenticated user's profile.

**Headers:** None — the `access_token` httpOnly cookie is sent automatically by the browser.

**Response (200):**

```json
{
  "id": 1,
  "email": "user@example.com",
  "name": "Yogesh",
  "is_active": true
}
```

---

### POST /auth/logout

Clear the refresh token cookie, ending the user's session.

**Request Body:** None

**Response (200):**

```json
{
  "status": "success",
  "message": "Logged out"
}
```

**Implementation Notes:**
- Deletes both `access_token` and `refresh_token` httpOnly cookies. The frontend also clears the user state.

---

## 4. Changes to Existing Endpoints

Every existing endpoint will require authentication. The logged-in user is injected automatically —
no more passing `email` in request bodies.

| Endpoint | Current | After Auth |
|----------|---------|------------|
| `POST /subscribe` | Body: `{ email, skill, days, hours }` | Body: `{ skill, days, hours }` — email comes from the authenticated user |
| `GET /syllabi` | Returns ALL users' subscriptions | Returns ONLY the authenticated user's subscriptions |
| `GET /syllabi/{skill_id}` | Anyone can view any syllabus | Only the owner can view their syllabus (403 otherwise) |
| `POST /generate-syllabus` | Body: `{ email, skill }` | Body: `{ skill }` — email from auth user |
| `POST /generate-content` | Body: `{ skill_id }` | Same body, but verified that `skill_id` belongs to the authenticated user |
| `POST /generate-content/chapter` | Body: `{ task_id }` | Same body, verified ownership |
| `GET /chapter/{task_id}` | Anyone can read any chapter | Only owner can access |
| `POST /send-email/chapter` | Body: `{ task_id }` | Verified ownership, email sent to authenticated user's email |
| `POST /issue-newsletters` | Anyone can trigger | **Admin-only** endpoint (future: role-based access) |

### How Route Protection Works (FastAPI)

```python
# dependencies/auth.py
from typing import Optional
from fastapi import Cookie, HTTPException
from models.user import User
from services.jwt import decode_token
from services.user import get_user_by_id

def get_current_user(access_token: Optional[str] = Cookie(default=None)) -> User:
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_token(access_token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = get_user_by_id(int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user

# Usage in any route:
@router.get("/syllabi")
def list_syllabi(current_user: User = Depends(get_current_user)):
    return syllabus_controller.list_syllabi(current_user)
```

---

## 5. Token Strategy

| Token | Lifetime | Storage | Purpose |
|-------|----------|---------|---------|
| **Access Token** | 2 minutes (configurable via `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`) | httpOnly cookie (`access_token`, `SameSite=Lax`, path=`/`) | Sent automatically with every request; used by `get_current_user` to identify the user |
| **Refresh Token** | 7 hours (configurable via `JWT_REFRESH_TOKEN_EXPIRE_HOURS`) | httpOnly cookie (`refresh_token`, `SameSite=Lax`, path=`/`) | Used only by `/auth/refresh` to issue a new access token cookie |

### Why This Approach

- **Both tokens in httpOnly cookies** — JavaScript cannot access them (XSS-safe). The browser sends them automatically on every request.
- **No `Authorization` header** — The frontend never touches the tokens. No request interceptor needed for attaching headers.
- **No localStorage for tokens** — localStorage is vulnerable to XSS attacks. Neither token is stored in localStorage or in-memory JavaScript state.
- **SameSite=Lax** — Prevents CSRF attacks. Cookies are NOT sent on cross-origin POST requests (e.g., from `evil.com`). Only sent on same-site navigations and requests.
- **Cookie path is `/`** — The Vite dev proxy remaps `/py/auth/*` to `/auth/*`, and path-restricted cookies don't work across proxies.

---

## 6. Password Security

| Aspect | Implementation |
|--------|---------------|
| **Hashing algorithm** | bcrypt (via `passlib[bcrypt]`) |
| **Salt** | Auto-generated per password (built into bcrypt) |
| **Minimum length** | 8 characters (enforced by Pydantic validator) |
| **Plain text** | NEVER stored, NEVER logged |
| **Verification** | `CryptContext.verify(plain, hashed)` via `passlib` — constant-time comparison |

---

## 7. Frontend Changes

### New Pages

| Page | Route | Purpose |
|------|-------|---------|
| **Signup** | `/signup` | Registration form (name, email, password) |
| **Login** | `/login` | Login form (email, password) — replaces current non-functional login |

### Auth State (Zustand Store)

```typescript
interface AuthState {
  user: UserInfo | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  initialized: boolean;
  sessionExpired: boolean;

  signup: (name: string, email: string, password: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: (reason?: "session_expired") => void;
  initAuth: () => Promise<void>;
  refreshAccessToken: () => Promise<void>;
  clearSessionExpired: () => void;
}
```

- `initAuth()` is called once on app load (inside the `Layout` component). It calls `POST /auth/refresh` (the browser sends cookies automatically), then fetches `/auth/me` to populate the store.
- `refreshAccessToken()` is used by the Axios response interceptor to silently refresh expired access tokens. It only calls `POST /auth/refresh` — no token is returned or stored in JS.
- No `accessToken` in the store — tokens are fully managed by httpOnly cookies.
- A guard (`if (get().initialized || get().isLoading) return`) prevents duplicate `initAuth` calls (e.g., from React StrictMode).

### Axios Interceptor

```typescript
// No request interceptor needed — cookies are sent automatically by the browser.

// Response interceptor — on 401, refresh the access token cookie and retry
// Uses a queue to prevent multiple concurrent refresh calls
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && !error.config._retry) {
      error.config._retry = true;
      try {
        await useAuthStore.getState().refreshAccessToken();
        return api.request(error.config); // retry — browser now sends new cookie
      } catch {
        useAuthStore.getState().logout("session_expired");
        return Promise.reject(error);
      }
    }
    return Promise.reject(error);
  }
);
```

### Route Protection

The `Layout` component acts as the main authentication gate. Unauthenticated users are redirected to `/login`:

```typescript
export default function Layout() {
  const { initialized, isAuthenticated, initAuth } = useAuthStore();
  useEffect(() => { initAuth(); }, []);

  if (!initialized) return <LoadingSpinner />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;

  return (
    <SidebarProvider>
      {/* ... app shell with sidebar, nav, and <Outlet /> */}
    </SidebarProvider>
  );
}
```

`/login` and `/signup` are separate top-level routes (not nested under `Layout`), so they render independently with their own dark background and white card UI.

### UI Changes to Existing Forms

- **Subscribe page** — Removed email field. Skill, days, hours only. Email comes from auth.
- **Generate Syllabus page** — Removed email field. Show only the user's own skills in dropdown.
- **Sidebar user section** — Displays real user email from auth state. Shows logout button.
- **Logout** — Clears user state immediately, then calls `POST /auth/logout` (fire-and-forget) to delete both token cookies, and navigates to `/login`.
- **Login page** (`/login`) — White card on dark background with email/password fields and password visibility toggle.
- **Signup page** (`/signup`) — White card on dark background with name/email/password/confirm-password fields and visibility toggles.
- **StrictMode guards** — `useRef` guards added to `useEffect` hooks in data-fetching pages to prevent duplicate API calls in development.

---

## 8. New Dependencies

### Backend (Python)

| Package | Purpose |
|---------|---------|
| `passlib[bcrypt]` | Password hashing |
| `bcrypt<5` | Bcrypt backend (pinned for passlib compatibility) |
| `PyJWT` | JWT token creation and verification |
| `python-multipart` | Required by FastAPI for form/cookie parsing |

### Frontend (npm)

No new dependencies needed — Axios interceptors and Zustand are already in place.

---

## 9. Environment Variables

**New variables required:**

| Variable | Purpose | Example |
|----------|---------|---------|
| `JWT_SECRET_KEY` | Secret for signing JWT tokens | `openssl rand -hex 32` (64-char hex string) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `2` |
| `JWT_REFRESH_TOKEN_EXPIRE_HOURS` | Refresh token lifetime | `7` |

---

## 10. Implementation Timeline

| Phase | Task | Estimated Time |
|-------|------|---------------|
| **Phase 1** | PostgreSQL + SQLModel + Alembic setup, `User` model, initial migration | 1 day |
| **Phase 2** | Auth endpoints (`/auth/signup`, `/auth/login`, `/auth/refresh`, `/auth/me`) | 1 day |
| **Phase 3** | Protect all existing endpoints with `Depends(get_current_user)`, update request models | 1 day |
| **Phase 4** | Frontend — Signup/Login pages, Zustand auth store, Axios interceptors, route guards | 1–2 days |
| **Phase 5** | Remove old SQLite code, update `.env.example`, update docs, testing | 1 day |
| **Total** | | **5–6 days** |

---

## 11. Security Checklist

| Item | Status |
|------|--------|
| Passwords hashed with bcrypt | Done |
| JWT tokens with expiration | Done |
| Both tokens in httpOnly cookies | Done |
| No tokens in localStorage or JS memory | Done |
| Route-level ownership checks (user can only access own data) | Done |
| User existence & active check on token refresh | Done |
| Defensive `sub` claim validation | Done |
| CORS configuration | Done |
| Input validation (Pydantic) | Done |
| Rate limiting on `/auth/login` (prevent brute force) | Phase 2 |
| HTTPS in production | Deployment concern |

---

## 12. Future Enhancements (Out of Scope for Now)

| Feature | Description |
|---------|-------------|
| **OAuth2 social login** | "Sign in with Google" — eliminates password management |
| **Role-based access** | Admin role for `/issue-newsletters` and user management |
| **Email verification** | Verify email ownership before allowing subscriptions |
| **Password reset** | Forgot password flow with email link |
| **Token blacklist** | Redis-based blacklist for immediate token revocation on logout |
| **Rate limiting** | Prevent API abuse (e.g., `slowapi` middleware) |
