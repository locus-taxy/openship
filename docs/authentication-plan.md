# Authentication Implementation Plan — Openship

**Author:** Yogesh K  
**Date:** March 31, 2026  
**Status:** Proposal  

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
│  Signup ──► POST /auth/signup ──► Store tokens in memory         │
│  Login  ──► POST /auth/login  ──► Attach token to every request  │
│  Refresh ─► POST /auth/refresh ──► Get new access token          │
│                                                                  │
│  Axios Interceptor: Authorization: Bearer <access_token>         │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                        BACKEND (FastAPI)                          │
│                                                                  │
│  /auth/signup    — Create user, hash password, return tokens     │
│  /auth/login     — Verify password, return tokens                │
│  /auth/refresh   — Validate refresh token, return new access     │
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
  "user": {
    "id": 1,
    "email": "user@example.com",
    "name": "Yogesh"
  },
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**Error Responses:**

| Status | Reason |
|--------|--------|
| `409` | Email already registered |
| `422` | Validation error (short password, invalid email, etc.) |

**Implementation Notes:**
- Password hashed with `bcrypt` (via `passlib`) before storage. Plain text password is NEVER stored.
- `access_token` expires in **30 minutes**.
- `refresh_token` expires in **7 days**.

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
    "name": "Yogesh"
  },
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**Error Responses:**

| Status | Reason |
|--------|--------|
| `401` | Invalid email or password |

---

### POST /auth/refresh

Get a new access token using a valid refresh token.

**Request Body:**

| Field | Type | Required |
|-------|------|----------|
| `refresh_token` | string | yes |

**Response (200):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**Error Responses:**

| Status | Reason |
|--------|--------|
| `401` | Refresh token expired or invalid |

---

### GET /auth/me

Return the currently authenticated user's profile.

**Headers:** `Authorization: Bearer <access_token>`

**Response (200):**

```json
{
  "id": 1,
  "email": "user@example.com",
  "name": "Yogesh",
  "is_active": true,
  "created_at": "2026-03-31T10:00:00Z"
}
```

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
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session)
) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id: int = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# Usage in any endpoint:
@app.get("/syllabi")
async def list_syllabi(current_user: User = Depends(get_current_user)):
    # current_user is guaranteed to be a valid, authenticated user
    return await get_user_syllabi(current_user.id)
```

---

## 5. Token Strategy

| Token | Lifetime | Storage (Frontend) | Purpose |
|-------|----------|-------------------|---------|
| **Access Token** | 30 minutes | In-memory (React state / Zustand) | Sent with every API request |
| **Refresh Token** | 7 days | HttpOnly cookie (secure, SameSite=Strict) | Used only to get new access tokens |

### Why This Split

- **Access tokens are short-lived** — If stolen, they expire quickly. Stored only in memory (lost on page refresh, which triggers a refresh flow).
- **Refresh tokens in HttpOnly cookies** — JavaScript cannot access them (XSS-safe). Sent automatically by the browser only to `/auth/refresh`.
- **No localStorage for tokens** — localStorage is vulnerable to XSS attacks.

---

## 6. Password Security

| Aspect | Implementation |
|--------|---------------|
| **Hashing algorithm** | bcrypt (via `passlib[bcrypt]`) |
| **Salt** | Auto-generated per password (built into bcrypt) |
| **Minimum length** | 8 characters (enforced by Pydantic validator) |
| **Plain text** | NEVER stored, NEVER logged |
| **Verification** | `passlib.hash.bcrypt.verify(plain, hashed)` — constant-time comparison |

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
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshToken: () => Promise<void>;
}
```

### Axios Interceptor

```typescript
// Automatically attach token to every request
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Automatically refresh on 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      await useAuthStore.getState().refreshToken();
      return api.request(error.config); // Retry original request
    }
    return Promise.reject(error);
  }
);
```

### Route Protection

The current `ProtectedRoute` (which does nothing) will be replaced:

```typescript
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return children;
}
```

### UI Changes to Existing Forms

- **Subscribe page** — Remove email field. Skill, days, hours only. Email comes from auth.
- **Generate Syllabus page** — Remove email field. Show only the user's own skills in dropdown.
- **Sidebar user section** — Display real user name/email from auth state instead of hardcoded "shadcn / m@example.com".
- **Logout** — Clear auth state + call `POST /auth/logout` (optional server-side token blacklist).

---

## 8. New Dependencies

### Backend (Python)

| Package | Purpose |
|---------|---------|
| `passlib[bcrypt]` | Password hashing |
| `python-jose[cryptography]` | JWT token creation and verification |

### Frontend (npm)

No new dependencies needed — Axios interceptors and Zustand are already in place.

---

## 9. Environment Variables

**New variables required:**

| Variable | Purpose | Example |
|----------|---------|---------|
| `JWT_SECRET_KEY` | Secret for signing JWT tokens | `openssl rand -hex 32` (64-char hex string) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `30` |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime | `7` |

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
| Passwords hashed with bcrypt | Planned |
| JWT tokens with expiration | Planned |
| Refresh tokens in HttpOnly cookies | Planned |
| No tokens in localStorage | Planned |
| Route-level ownership checks (user can only access own data) | Planned |
| Rate limiting on `/auth/login` (prevent brute force) | Phase 2 |
| CORS configuration | Phase 2 |
| Input validation (Pydantic) | Already exists |
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
