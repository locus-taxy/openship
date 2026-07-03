"""
Confluence integration for the RAG knowledge base.

- Connect: three-legged Atlassian OAuth 2.0; one app, company-level encrypted
  tokens with auto-refresh.
- Ingest: fetch every page from every space, upsert into document_pages, chunk,
  embed, and store document_chunks. Resumable background job.
- Freshness: webhooks re-embed changed pages; a reconciler catches misses.

Reads go through the Confluence search API (works with classic OAuth scopes).
"""

import hmac
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import urlencode

import httpx
import jwt as pyjwt
from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError

import config
from config import JWT_SECRET_KEY, JWT_ALGORITHM
from database import engine
from onboarding.models.company import Company
from onboarding.models.confluence_connection import ConfluenceConnection
from onboarding.models.document_page import DocumentPage
from onboarding.models.document_chunk import DocumentChunk
from onboarding.models.ingestion_job import IngestionJob
from services.encryption import encrypt_secret, decrypt_secret
from services.user import get_user_by_id
from onboarding.services import embeddings as embedding_service
from onboarding.services.chunking import chunk_text, estimate_tokens

logger = logging.getLogger(__name__)

_AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
_HTTP_TIMEOUT = 15
# The read phase makes hundreds of sequential calls over several minutes; retry
# transient network errors / 5xx so one blip doesn't fail the whole ingest.
_HTTP_MAX_ATTEMPTS = 4
_HTTP_RETRY_BACKOFF = 2.0
_HTTP_RETRY_STATUSES = frozenset({429, 502, 503, 504})
_sleep = time.sleep  # module-level so tests can patch it
_STATE_EXPIRE_MINUTES = 15
_STATE_TYPE = "confluence_oauth"
_TOKEN_SKEW_SECONDS = 60
_PAGE_SEARCH_LIMIT = 100
# Chunks are embedded in cross-page batches of ~this size; one big embed call is
# far faster than one call per page (most pages hold only a few chunks).
_EMBED_BATCH_SIZE = 256

# ── OAuth / state helpers ──────────────────────────────────────────────────────

def require_confluence_oauth() -> None:
    if not config.is_confluence_oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Confluence integration is not configured on this server.",
        )

def _utcnow() -> datetime:
    """Naive UTC 'now'. Our datetime columns are `timestamp without time zone`; if
    the DB session tz isn't UTC, storing an aware-UTC value gets shifted and stripped
    to local wall-time, which then reads back mis-interpreted as UTC (breaks token
    expiry math). Storing naive UTC round-trips correctly regardless of session tz."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _domain_from_email(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower()

# Free/public email providers. Users on these must NOT be pooled into a shared
# company by domain (two strangers @gmail.com are not one org), so we block them
# from connecting Confluence. Any real corporate domain is allowed automatically.
_GENERIC_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "yahoo.com",
        "ymail.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "gmx.com",
        "zoho.com",
        "mail.com",
        "yandex.com",
        "pm.me",
    }
)

def _require_company_email(user) -> None:
    """Reject personal/free email domains from connecting — they'd pool unrelated
    users into one shared company and leak documents across them."""
    if _domain_from_email(user.email) in _GENERIC_EMAIL_DOMAINS:
        raise HTTPException(
            status_code=403,
            detail="Please connect with your company email, not a personal email address.",
        )

def _create_state(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=_STATE_EXPIRE_MINUTES)
    return pyjwt.encode(
        {"sub": str(user_id), "type": _STATE_TYPE, "exp": expire},
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )

def _decode_state(state: str) -> int:
    try:
        payload = pyjwt.decode(state, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")
    if payload.get("type") != _STATE_TYPE:
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")
    return int(payload["sub"])

# ── company resolution ───────────────────────────────────────────────────────

def get_or_create_company_for_user(user) -> Company:
    """Map a user to their company by email domain, creating it if needed."""
    domain = _domain_from_email(user.email)
    with Session(engine) as session:
        company = session.exec(select(Company).where(Company.domain == domain)).first()
        if company:
            return company
        company = Company(name=domain, domain=domain)
        session.add(company)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return session.exec(select(Company).where(Company.domain == domain)).first()
        session.refresh(company)
        return company

def _get_connection(company_id: int) -> Optional[ConfluenceConnection]:
    with Session(engine) as session:
        return session.exec(
            select(ConfluenceConnection).where(ConfluenceConnection.company_id == company_id)
        ).first()

def _require_ready_connection(company_id: int) -> ConfluenceConnection:
    conn = _get_connection(company_id)
    if conn is None or conn.status != "ready" or not conn.access_token:
        raise HTTPException(status_code=409, detail="Confluence is not connected for your company.")
    return conn

# ── Atlassian OAuth HTTP ───────────────────────────────────────────────────────

def _exchange_code(code: str) -> dict:
    resp = httpx.post(
        _TOKEN_URL,
        json={
            "grant_type": "authorization_code",
            "client_id": config.ATLASSIAN_CLIENT_ID,
            "client_secret": config.ATLASSIAN_CLIENT_SECRET,
            "code": code,
            "redirect_uri": config.ATLASSIAN_REDIRECT_URI,
        },
        timeout=_HTTP_TIMEOUT,
    )
    if resp.status_code != 200:
        logger.warning("Atlassian token exchange failed: %s", resp.status_code)
        raise HTTPException(status_code=502, detail="Failed to exchange OAuth code with Atlassian.")
    return resp.json()

def _fetch_accessible_resources(access_token: str) -> list:
    resp = httpx.get(
        _RESOURCES_URL,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        timeout=_HTTP_TIMEOUT,
    )
    if resp.status_code != 200:
        logger.warning("Atlassian accessible-resources failed: %s", resp.status_code)
        raise HTTPException(status_code=502, detail="Failed to read Atlassian sites.")
    return resp.json()

def _upsert_connection(
    company_id: int,
    user_id: int,
    cloud_id: str,
    site_url: Optional[str],
    access_token: str,
    refresh_token: Optional[str],
    token_expires_at: datetime,
) -> None:
    with Session(engine) as session:
        conn = session.exec(
            select(ConfluenceConnection).where(ConfluenceConnection.company_id == company_id)
        ).first()
        if conn is None:
            conn = ConfluenceConnection(company_id=company_id)
        conn.cloud_id = cloud_id
        conn.site_url = site_url
        conn.access_token = encrypt_secret(access_token)
        conn.refresh_token = encrypt_secret(refresh_token) if refresh_token else None
        conn.token_expires_at = token_expires_at
        conn.connected_by_user_id = user_id
        conn.status = "ready"
        session.add(conn)
        session.commit()

def start_connect(user) -> dict:
    """Return the Atlassian authorize URL the browser should redirect to."""
    require_confluence_oauth()
    _require_company_email(user)
    state = _create_state(int(user.id))
    params = {
        "audience": "api.atlassian.com",
        "client_id": config.ATLASSIAN_CLIENT_ID,
        "scope": config.ATLASSIAN_OAUTH_SCOPES,
        "redirect_uri": config.ATLASSIAN_REDIRECT_URI,
        "state": state,
        "response_type": "code",
        "prompt": "consent",
    }
    return {"authorize_url": f"{_AUTHORIZE_URL}?{urlencode(params)}"}

def handle_callback(code: str, state: str) -> str:
    """Complete the OAuth flow. Returns the URL to redirect the browser to."""
    require_confluence_oauth()
    user_id = _decode_state(state)
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Unknown user for OAuth state.")

    company = get_or_create_company_for_user(user)
    tokens = _exchange_code(code)
    access_token = tokens.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="Atlassian did not return an access token.")

    resources = _fetch_accessible_resources(access_token)
    if not resources:
        raise HTTPException(
            status_code=400,
            detail="No accessible Confluence sites for this Atlassian account.",
        )
    site = resources[0]
    expires_at = _utcnow() + timedelta(seconds=int(tokens.get("expires_in", 3600)))
    _upsert_connection(
        company_id=company.id,
        user_id=user_id,
        cloud_id=site.get("id"),
        site_url=site.get("url"),
        access_token=access_token,
        refresh_token=tokens.get("refresh_token"),
        token_expires_at=expires_at,
    )
    return config.CONFLUENCE_POST_CONNECT_REDIRECT

def _counts(company_id: int):
    with Session(engine) as session:
        pages = session.exec(
            select(func.count(DocumentPage.id))
            .where(DocumentPage.company_id == company_id)
            .where(DocumentPage.is_active == True)  # noqa: E712
        ).one()
        chunks = session.exec(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.company_id == company_id)
        ).one()
    return int(pages), int(chunks)

def _running_job_progress(company_id: int) -> Optional[dict]:
    """Progress of the company's in-flight ingest, or None. Lets the UI resume
    the live progress view after a page refresh (the job is company-wide, not
    tied to one browser session)."""
    job = _running_job(company_id)
    return _job_progress(job) if job is not None else None

def _last_result_progress(company_id: int) -> Optional[dict]:
    """The most recent finished job's result, shown once so a sync/ingest that
    completed while the user was away still surfaces its outcome."""
    job = _latest_finished_job(company_id)
    return _job_progress(job) if job is not None else None

def get_status(user) -> dict:
    """Report whether this user's company is connected, and how much is indexed."""
    company = get_or_create_company_for_user(user)
    conn = _get_connection(company.id)
    if conn is None or conn.status != "ready":
        return {
            "connected": False,
            "status": conn.status if conn else None,
            "site_url": None,
            "page_count": 0,
            "chunk_count": 0,
            "ingest": None,
        }
    page_count, chunk_count = _counts(company.id)
    running = _running_job_progress(company.id)
    return {
        "connected": True,
        "status": conn.status,
        "site_url": conn.site_url,
        "page_count": page_count,
        "chunk_count": chunk_count,
        "ingest": running,
        # Only surface a finished-job result when nothing is currently running.
        "last_result": None if running else _last_result_progress(company.id),
    }

# ── Confluence REST client ─────────────────────────────────────────────────────

def _api_root(cloud_id: str) -> str:
    return f"https://api.atlassian.com/ex/confluence/{cloud_id}"

def _is_token_expired(expires_at: Optional[datetime]) -> bool:
    if expires_at is None:
        return True
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return now >= (expires_at - timedelta(seconds=_TOKEN_SKEW_SECONDS))

def _mark_status(company_id: int, status: str) -> None:
    with Session(engine) as session:
        conn = session.exec(
            select(ConfluenceConnection).where(ConfluenceConnection.company_id == company_id)
        ).first()
        if conn is not None:
            conn.status = status
            session.add(conn)
            session.commit()

def _refresh_access_token(conn: ConfluenceConnection) -> str:
    """Exchange the stored refresh token for a fresh access token, persisting both."""
    if not conn.refresh_token:
        raise HTTPException(status_code=401, detail="Confluence needs to be reconnected.")
    resp = httpx.post(
        _TOKEN_URL,
        json={
            "grant_type": "refresh_token",
            "client_id": config.ATLASSIAN_CLIENT_ID,
            "client_secret": config.ATLASSIAN_CLIENT_SECRET,
            "refresh_token": decrypt_secret(conn.refresh_token),
        },
        timeout=_HTTP_TIMEOUT,
    )
    if resp.status_code != 200:
        _mark_status(conn.company_id, "error")
        raise HTTPException(status_code=401, detail="Confluence session expired; please reconnect.")
    data = resp.json()
    new_access = data["access_token"]
    new_refresh = data.get("refresh_token") or decrypt_secret(conn.refresh_token)
    expires_at = _utcnow() + timedelta(seconds=int(data.get("expires_in", 3600)))
    with Session(engine) as session:
        db = session.exec(
            select(ConfluenceConnection).where(ConfluenceConnection.company_id == conn.company_id)
        ).first()
        if db is not None:
            db.access_token = encrypt_secret(new_access)
            db.refresh_token = encrypt_secret(new_refresh)
            db.token_expires_at = expires_at
            session.add(db)
            session.commit()
    return new_access

def _get_valid_token(conn: ConfluenceConnection) -> str:
    """Return a usable access token, refreshing it first if it has expired."""
    if not _is_token_expired(conn.token_expires_at) and conn.access_token:
        return decrypt_secret(conn.access_token)
    return _refresh_access_token(conn)

def _read_get(url: str, headers: dict) -> httpx.Response:
    """GET with retries on transient network errors and retryable 5xx/429, so a
    single blip during the long read phase doesn't fail the whole ingest."""
    last_exc: Optional[Exception] = None
    resp: Optional[httpx.Response] = None
    for attempt in range(_HTTP_MAX_ATTEMPTS):
        try:
            resp = httpx.get(url, headers=headers, timeout=_HTTP_TIMEOUT)
        except httpx.HTTPError as exc:  # timeouts, SSL/handshake, connection resets
            last_exc = exc
            resp = None
        else:
            if resp.status_code not in _HTTP_RETRY_STATUSES:
                return resp
            last_exc = None
        if attempt < _HTTP_MAX_ATTEMPTS - 1:
            _sleep(_HTTP_RETRY_BACKOFF * (2**attempt))
    if resp is not None:
        return resp  # a retryable status that never cleared; caller maps to 502
    raise HTTPException(status_code=502, detail=f"Confluence request failed: {last_exc}")

def _fetch_spaces(cloud_id: str, token: str) -> list:
    """List all spaces via search (cql=type=space). Personal (~) spaces skipped."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    query = urlencode({"cql": "type=space", "limit": 250})
    url = f"{_api_root(cloud_id)}/wiki/rest/api/search?{query}"
    results: list = []
    for _ in range(50):  # safety cap on pages
        resp = _read_get(url, headers)
        if resp.status_code in (401, 403):
            raise HTTPException(
                status_code=401, detail="Confluence session expired; please reconnect."
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to list Confluence spaces.")
        data = resp.json()
        for item in data.get("results", []):
            space = item.get("space")
            if space and not str(space.get("key", "")).startswith("~"):
                results.append(space)
        nxt = (data.get("_links") or {}).get("next")
        if not nxt:
            break
        url = f"{_api_root(cloud_id)}/wiki{nxt}"
    return results

_TAG_RE = re.compile(r"<[^>]+>")

def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html or "")
    return re.sub(r"\s+", " ", text).strip()

def _search_pages(cloud_id: str, token: str, space_key: str) -> list:
    """List pages in a space via CQL search, expanding body/version/space so we
    get full page text in one call. Follows pagination."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    cql = f'space="{space_key}" and type=page'
    query = urlencode(
        {"cql": cql, "limit": _PAGE_SEARCH_LIMIT, "expand": "body.storage,version,space"}
    )
    url = f"{_api_root(cloud_id)}/wiki/rest/api/content/search?{query}"
    results: list = []
    for _ in range(200):  # safety cap
        resp = _read_get(url, headers)
        if resp.status_code in (401, 403):
            # Auth failure is global (e.g. token expired mid-run) — surface it so the
            # job fails loudly instead of silently skipping every space as "empty".
            raise HTTPException(
                status_code=401, detail="Confluence session expired; please reconnect."
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to search Confluence pages.")
        data = resp.json()
        results.extend(data.get("results", []))
        nxt = (data.get("_links") or {}).get("next")
        if not nxt:
            break
        url = f"{_api_root(cloud_id)}/wiki{nxt}"
    return results

def _fetch_single_page(cloud_id: str, token: str, page_id: str) -> Optional[dict]:
    """Fetch one page (with body/version/space) via search, or None."""
    # Confluence content ids are numeric; reject anything else so a webhook
    # payload can't inject into the CQL query.
    if not str(page_id).isdigit():
        return None
    query = urlencode({"cql": f"id={page_id}", "expand": "body.storage,version,space", "limit": 1})
    url = f"{_api_root(cloud_id)}/wiki/rest/api/content/search?{query}"
    resp = _read_get(url, {"Authorization": f"Bearer {token}", "Accept": "application/json"})
    if resp.status_code != 200:
        return None
    results = resp.json().get("results", [])
    return results[0] if results else None

def _page_fields(page: dict):
    """Extract (page_id, version, space_key, title, full_text) from a search result."""
    page_id = str(page.get("id"))
    version = (page.get("version") or {}).get("number")
    space = page.get("space")
    space_key = space.get("key") if isinstance(space, dict) else None
    title = (page.get("title") or "Untitled")[:512]
    body = (((page.get("body") or {}).get("storage") or {}).get("value")) or ""
    return page_id, version, space_key, title, _strip_html(body)

# ── knowledge base persistence ─────────────────────────────────────────────────

def _page_chunk_count(page_db_id: int) -> int:
    with Session(engine) as session:
        return int(
            session.exec(
                select(func.count(DocumentChunk.id)).where(DocumentChunk.page_id == page_db_id)
            ).one()
        )

def _upsert_page(company_id: int, page: dict):
    """Insert/update a document_pages row. Returns (page_db_id, changed, text)."""
    page_id, version, space_key, title, text = _page_fields(page)
    with Session(engine) as session:
        row = session.exec(
            select(DocumentPage)
            .where(DocumentPage.company_id == company_id)
            .where(DocumentPage.confluence_page_id == page_id)
        ).first()
        changed = False
        if row is None:
            row = DocumentPage(company_id=company_id, confluence_page_id=page_id)
            changed = True
        elif row.version != version or not row.is_active:
            changed = True
        row.version = version
        row.space_key = space_key
        row.title = title
        row.content_text = text
        row.is_active = True
        row.last_synced_at = _utcnow()
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id, changed, text

def _delete_chunks(page_db_id: int) -> None:
    with Session(engine) as session:
        for chunk in session.exec(
            select(DocumentChunk).where(DocumentChunk.page_id == page_db_id)
        ).all():
            session.delete(chunk)
        session.commit()

def _store_chunks(
    company_id: int, page_db_id: int, chunks: List[str], vectors: List[List[float]]
) -> None:
    with Session(engine) as session:
        for i, (content, vector) in enumerate(zip(chunks, vectors)):
            session.add(
                DocumentChunk(
                    company_id=company_id,
                    page_id=page_db_id,
                    chunk_index=i,
                    content=content,
                    embedding=vector,
                    token_count=estimate_tokens(content),
                )
            )
        session.commit()

def _embed_page(company_id: int, page_db_id: int, text: str) -> int:
    """Chunk, embed, and (re)store a page's chunks. Returns chunk count."""
    chunks = chunk_text(text)
    if not chunks:
        _delete_chunks(page_db_id)
        return 0
    vectors = embedding_service.embed_texts(chunks)
    _delete_chunks(page_db_id)
    _store_chunks(company_id, page_db_id, chunks, vectors)
    return len(chunks)

# ── ingestion job ────────────────────────────────────────────────────────────

def _create_job(company_id: int, kind: str = "ingest") -> int:
    with Session(engine) as session:
        job = IngestionJob(company_id=company_id, status="running", kind=kind)
        session.add(job)
        session.commit()
        session.refresh(job)
        return job.id

def _update_job(
    job_id: int,
    *,
    phase: Optional[str] = None,
    total_spaces: Optional[int] = None,
    processed_spaces: Optional[int] = None,
    total_pages: Optional[int] = None,
    processed_pages: Optional[int] = None,
    total_chunks: Optional[int] = None,
    embedded_chunks: Optional[int] = None,
    status: Optional[str] = None,
    error: Optional[str] = None,
    completed: bool = False,
) -> None:
    with Session(engine) as session:
        job = session.get(IngestionJob, job_id)
        if job is None:
            return
        if phase is not None:
            job.phase = phase
        if total_spaces is not None:
            job.total_spaces = total_spaces
        if processed_spaces is not None:
            job.processed_spaces = processed_spaces
        if total_pages is not None:
            job.total_pages = total_pages
        if processed_pages is not None:
            job.processed_pages = processed_pages
        if total_chunks is not None:
            job.total_chunks = total_chunks
        if embedded_chunks is not None:
            job.embedded_chunks = embedded_chunks
        if status is not None:
            job.status = status
        if error is not None:
            job.error = error
        if completed:
            job.completed_at = _utcnow()
        session.add(job)
        session.commit()

def _running_job(company_id: int) -> Optional[IngestionJob]:
    with Session(engine) as session:
        return session.exec(
            select(IngestionJob)
            .where(IngestionJob.company_id == company_id)
            .where(IngestionJob.status == "running")
            .order_by(IngestionJob.id.desc())
        ).first()

def reap_running_jobs() -> int:
    """Mark any lingering 'running' jobs as failed. Called on app startup: these
    jobs run as in-process background tasks, so a process restart leaves any
    in-flight job orphaned as 'running' forever — which would block all future
    ingests/reconciles. Returns how many were reaped."""
    with Session(engine) as session:
        stuck = session.exec(select(IngestionJob).where(IngestionJob.status == "running")).all()
        for job in stuck:
            job.status = "failed"
            job.phase = "failed"
            job.error = "Interrupted by a server restart. Please run it again."
            job.completed_at = _utcnow()
            session.add(job)
        session.commit()
        return len(stuck)

def _latest_finished_job(company_id: int) -> Optional[IngestionJob]:
    """Most recent completed/failed job — lets the UI show the result of a job
    that finished while the user was away (not just running ones)."""
    with Session(engine) as session:
        return session.exec(
            select(IngestionJob)
            .where(IngestionJob.company_id == company_id)
            .where(IngestionJob.status != "running")
            .order_by(IngestionJob.id.desc())
        ).first()

def begin_ingest(user, background_tasks) -> dict:
    """Validate, create a job, and schedule a full ingest in the background.
    If an ingest is already running for the company, return it instead of
    starting a second (avoids duplicate work and token-refresh races)."""
    company = get_or_create_company_for_user(user)
    _require_ready_connection(company.id)
    existing = _running_job(company.id)
    if existing is not None:
        # A job (of either kind) is already running — return it with its true kind
        # so the UI labels progress honestly instead of assuming an ingest.
        return {"job_id": existing.id, "status": "running", "kind": existing.kind}
    job_id = _create_job(company.id)
    background_tasks.add_task(_run_ingest, company.id, job_id)
    return {"job_id": job_id, "status": "running", "kind": "ingest"}

def _flush_embed_batch(company_id: int, buffer: list) -> int:
    """Embed a buffer of (page_db_id, chunks) in ONE batched call, then store each
    page's chunks. Batching across pages is far faster than one call per page.
    Returns the number of chunks embedded."""
    texts = [chunk for _, chunks in buffer for chunk in chunks]
    vectors = embedding_service.embed_texts(texts)
    offset = 0
    for page_db_id, chunks in buffer:
        n = len(chunks)
        _delete_chunks(page_db_id)
        _store_chunks(company_id, page_db_id, chunks, vectors[offset : offset + n])
        offset += n
    return len(texts)

def _run_ingest(company_id: int, job_id: int) -> None:
    """Background worker, in three visible phases: reading (fetch every page from
    every space) → indexing (upsert pages) → embedding (batch-embed their chunks).

    Robustness: a failure confined to one space / page / embed-batch is logged and
    SKIPPED (counted, surfaced as a note, retried on the next ingest) rather than
    aborting the whole run. Only whole-run problems — no connection, an expired
    session, or nothing embedding at all — fail the job. Resumable: a page is
    (re)embedded only when new, changed, or missing chunks."""
    try:
        conn = _get_connection(company_id)
        if conn is None or not conn.access_token:
            raise HTTPException(status_code=409, detail="Confluence is not connected.")
        token = _get_valid_token(conn)

        # Phase 1 — reading: fetch every page from every space. A space that keeps
        # failing (after retries) is skipped so it can't sink the whole read.
        spaces = _fetch_spaces(conn.cloud_id, token)
        _update_job(job_id, phase="reading", total_spaces=len(spaces), processed_spaces=0)
        raw_pages: list = []
        skipped_spaces = 0
        for i, space in enumerate(spaces, start=1):
            key = space.get("key")
            if key:
                try:
                    raw_pages.extend(_search_pages(conn.cloud_id, token, key))
                except HTTPException as exc:
                    if exc.status_code == 401:
                        raise  # auth is global — fail the whole job, don't fake success
                    logger.warning("Ingest %s: skipping space %s (%s)", job_id, key, exc.detail)
                    skipped_spaces += 1
                except Exception as exc:
                    logger.warning("Ingest %s: skipping space %s (%s)", job_id, key, exc)
                    skipped_spaces += 1
            _update_job(job_id, processed_spaces=i, total_pages=len(raw_pages))

        # Phase 2 — indexing: upsert pages, deciding which need (re)embedding.
        _update_job(job_id, phase="indexing", total_pages=len(raw_pages), processed_pages=0)
        to_embed: list = []  # (page_db_id, text)
        processed = 0
        skipped_pages = 0
        for page in raw_pages:
            if page.get("id"):  # skip malformed results with no id (don't key on "None")
                try:
                    page_db_id, changed, text = _upsert_page(company_id, page)
                    if text and (changed or _page_chunk_count(page_db_id) == 0):
                        to_embed.append((page_db_id, text))
                except Exception as exc:
                    logger.warning("Ingest %s: skipping page (%s)", job_id, exc)
                    skipped_pages += 1
            processed += 1
            _update_job(job_id, processed_pages=processed)

        # Phase 3 — embedding: chunk each page, then embed in cross-page batches.
        # A batch that fails is skipped (its pages keep 0 chunks → retried next run).
        planned = [(pid, chunk_text(text)) for pid, text in to_embed]
        planned = [(pid, chunks) for pid, chunks in planned if chunks]
        total_chunks = sum(len(c) for _, c in planned)
        _update_job(job_id, phase="embedding", total_chunks=total_chunks, embedded_chunks=0)

        embedded = 0
        failed_chunks = 0
        buffer: list = []
        buffered_chunks = 0
        for page_db_id, chunks in planned:
            buffer.append((page_db_id, chunks))
            buffered_chunks += len(chunks)
            if buffered_chunks >= _EMBED_BATCH_SIZE:
                embedded, failed_chunks = _flush_and_track(
                    company_id, job_id, buffer, embedded, failed_chunks
                )
                buffer, buffered_chunks = [], 0
        if buffer:
            embedded, failed_chunks = _flush_and_track(
                company_id, job_id, buffer, embedded, failed_chunks
            )

        # If there was work to embed but nothing landed, embedding is broken — fail.
        if total_chunks and embedded == 0:
            raise HTTPException(status_code=502, detail="Embedding failed for every page.")

        parts = []
        if skipped_spaces:
            parts.append(f"{skipped_spaces} space(s) skipped")
        if skipped_pages:
            parts.append(f"{skipped_pages} page(s) skipped")
        if failed_chunks:
            parts.append(f"{failed_chunks} chunk(s) failed")
        note = ("; ".join(parts) + " — re-ingest to retry.") if parts else None
        _update_job(job_id, status="done", phase="done", error=note, completed=True)
    except Exception as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        logger.exception("Ingestion job %s failed", job_id)
        if isinstance(exc, HTTPException) and exc.status_code == 401:
            _mark_status(company_id, "error")  # surface the Reconnect state in the UI
        _update_job(job_id, status="failed", phase="failed", error=str(detail), completed=True)

def _flush_and_track(company_id, job_id, buffer, embedded, failed_chunks):
    """Flush an embed batch, updating progress. On failure, log and count the
    batch's chunks as failed instead of raising. Returns (embedded, failed_chunks)."""
    try:
        embedded += _flush_embed_batch(company_id, buffer)
        _update_job(job_id, embedded_chunks=embedded)
    except Exception as exc:
        logger.warning("Ingest %s: embed batch failed (%s)", job_id, exc)
        failed_chunks += sum(len(chunks) for _, chunks in buffer)
    return embedded, failed_chunks

def _job_progress(job: IngestionJob) -> dict:
    """Serialise a job's staged progress for the UI."""
    return {
        "job_id": job.id,
        "status": job.status,
        "kind": job.kind,
        "phase": job.phase,
        "total_spaces": job.total_spaces,
        "processed_spaces": job.processed_spaces,
        "total_pages": job.total_pages,
        "processed_pages": job.processed_pages,
        "total_chunks": job.total_chunks,
        "embedded_chunks": job.embedded_chunks,
        "error": job.error,
    }

def get_ingest_status(user, job_id: int) -> dict:
    """Report progress for one ingestion job (company-scoped)."""
    company = get_or_create_company_for_user(user)
    with Session(engine) as session:
        job = session.get(IngestionJob, job_id)
        if job is None or job.company_id != company.id:
            raise HTTPException(status_code=404, detail="Ingestion job not found.")
        return _job_progress(job)

# ── webhooks (freshness) ────────────────────────────────────────────────────────

def verify_webhook_secret(provided: Optional[str]) -> None:
    expected = config.CONFLUENCE_WEBHOOK_SECRET
    if not expected:
        raise HTTPException(status_code=503, detail="Confluence webhooks are not configured.")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook secret.")

def _pages_by_page_id(page_id: str, company_id: Optional[int] = None) -> list:
    with Session(engine) as session:
        stmt = select(DocumentPage).where(DocumentPage.confluence_page_id == page_id)
        if company_id is not None:
            stmt = stmt.where(DocumentPage.company_id == company_id)
        return session.exec(stmt).all()

def _connection_by_cloud_id(cloud_id: str) -> Optional[ConfluenceConnection]:
    with Session(engine) as session:
        return session.exec(
            select(ConfluenceConnection).where(ConfluenceConnection.cloud_id == cloud_id)
        ).first()

def _deactivate_pages(page_id: str, company_id: Optional[int] = None) -> int:
    with Session(engine) as session:
        stmt = select(DocumentPage).where(DocumentPage.confluence_page_id == page_id)
        if company_id is not None:
            stmt = stmt.where(DocumentPage.company_id == company_id)
        pages = session.exec(stmt).all()
        for page in pages:
            page.is_active = False
            session.add(page)
        session.commit()
        return len(pages)

def _reindex_page(company_id: int, cloud_id: str, token: str, page_id: str) -> bool:
    """Fetch one page, upsert it, and re-embed. Returns False if unreadable."""
    page = _fetch_single_page(cloud_id, token, page_id)
    if page is None:
        return False
    page_db_id, _changed, text = _upsert_page(company_id, page)
    if text:
        _embed_page(company_id, page_db_id, text)
    return True

def _handle_page_updated(page_id: str, company_id: Optional[int] = None) -> dict:
    pages = _pages_by_page_id(page_id, company_id)
    if not pages:
        return {"status": "ignored"}
    for page in pages:
        conn = _get_connection(page.company_id)
        if conn is not None and conn.access_token:
            token = _get_valid_token(conn)
            _reindex_page(page.company_id, conn.cloud_id, token, page_id)
    return {"status": "updated"}

def _handle_page_removed(page_id: str, company_id: Optional[int] = None) -> dict:
    count = _deactivate_pages(page_id, company_id)
    return {"status": "removed" if count else "ignored"}

def _handle_page_created(payload: dict) -> dict:
    page_min = payload.get("page") or {}
    page_id = str(page_min.get("id")) if page_min.get("id") is not None else None
    cloud_id = payload.get("cloudId") or payload.get("cloud_id")
    if not page_id or not cloud_id:
        return {"status": "ignored"}
    conn = _connection_by_cloud_id(cloud_id)
    if conn is None or not conn.access_token:
        return {"status": "ignored"}
    token = _get_valid_token(conn)
    if _reindex_page(conn.company_id, conn.cloud_id, token, page_id):
        return {"status": "added"}
    return {"status": "ignored"}

def handle_webhook(payload: dict) -> dict:
    """Handle a Confluence webhook, never raising: a failure here (e.g. the embed
    model can't load) must not 500 the endpoint, or Atlassian will retry-storm it.
    Returns a status dict; the reconciler catches anything missed."""
    try:
        return _dispatch_webhook(payload)
    except Exception:
        logger.exception("Confluence webhook handling failed")
        return {"status": "error"}

def _dispatch_webhook(payload: dict) -> dict:
    """Dispatch a Confluence webhook. Create resolves the company by cloud id;
    update/remove scope to that company too (when a cloud id is present) so a
    webhook for one tenant can't touch another tenant's page that happens to
    share the same Confluence page id."""
    event = (payload.get("event") or payload.get("webhookEvent") or "").lower()
    page = payload.get("page") or {}
    page_id = str(page.get("id")) if page.get("id") is not None else None

    company_id: Optional[int] = None
    cloud_id = payload.get("cloudId") or payload.get("cloud_id")
    if cloud_id:
        conn = _connection_by_cloud_id(cloud_id)
        if conn is None:  # a cloud site we don't have a connection for
            return {"status": "ignored"}
        company_id = conn.company_id

    if "creat" in event:
        return _handle_page_created(payload)
    if "remov" in event or "trash" in event or "delet" in event:
        if page_id:
            return _handle_page_removed(page_id, company_id)
        return {"status": "ignored"}
    if "updat" in event:
        if page_id:
            return _handle_page_updated(page_id, company_id)
        return {"status": "ignored"}
    return {"status": "ignored"}

# ── reconciliation ─────────────────────────────────────────────────────────────

def begin_reconcile(user, background_tasks) -> dict:
    """Schedule a background reconcile (re-scan every space to fix deletions /
    restores). Returns the running job if one is already in flight."""
    company = get_or_create_company_for_user(user)
    _require_ready_connection(company.id)
    existing = _running_job(company.id)
    if existing is not None:
        return {"job_id": existing.id, "status": "running", "kind": existing.kind}
    job_id = _create_job(company.id, kind="reconcile")
    background_tasks.add_task(_run_reconcile, company.id, job_id)
    return {"job_id": job_id, "status": "running", "kind": "reconcile"}

def _run_reconcile(company_id: int, job_id: int) -> None:
    """Background worker: re-list every space (with progress), then deactivate
    pages that vanished upstream and reactivate ones that reappeared. A space that
    fails after retries is skipped rather than failing the whole sync."""
    try:
        conn = _get_connection(company_id)
        if conn is None or not conn.access_token:
            raise HTTPException(status_code=409, detail="Confluence is not connected.")
        token = _get_valid_token(conn)

        # Phase 1 — reading: gather the set of pages that still exist upstream.
        spaces = _fetch_spaces(conn.cloud_id, token)
        _update_job(job_id, phase="reading", total_spaces=len(spaces), processed_spaces=0)
        live_ids: set = set()
        skipped_spaces = 0
        for i, space in enumerate(spaces, start=1):
            key = space.get("key")
            if key:
                try:
                    for page in _search_pages(conn.cloud_id, token, key):
                        live_ids.add(str(page.get("id")))
                except HTTPException as exc:
                    if exc.status_code == 401:
                        raise  # auth is global — fail loudly rather than deactivate everything
                    logger.warning("Reconcile %s: skipping space %s (%s)", job_id, key, exc.detail)
                    skipped_spaces += 1
                except Exception as exc:
                    logger.warning("Reconcile %s: skipping space %s (%s)", job_id, key, exc)
                    skipped_spaces += 1
            _update_job(job_id, processed_spaces=i)

        # Phase 2 — reconciling: flip is_active based on presence upstream.
        _update_job(job_id, phase="reconciling")
        deactivated = reactivated = 0
        with Session(engine) as session:
            pages = session.exec(
                select(DocumentPage).where(DocumentPage.company_id == company_id)
            ).all()
            for page in pages:
                present = page.confluence_page_id in live_ids
                if not present and page.is_active:
                    page.is_active = False
                    session.add(page)
                    deactivated += 1
                elif present and not page.is_active:
                    page.is_active = True
                    session.add(page)
                    reactivated += 1
            session.commit()

        if deactivated == 0 and reactivated == 0 and not skipped_spaces:
            note = "Already up to date — no changes."
        else:
            note = f"{deactivated} removed, {reactivated} restored"
            if skipped_spaces:
                note += f"; {skipped_spaces} space(s) skipped"
        _update_job(job_id, status="done", phase="done", error=note, completed=True)
    except Exception as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        logger.exception("Reconcile job %s failed", job_id)
        if isinstance(exc, HTTPException) and exc.status_code == 401:
            _mark_status(company_id, "error")  # surface the Reconnect state in the UI
        _update_job(job_id, status="failed", phase="failed", error=str(detail), completed=True)
