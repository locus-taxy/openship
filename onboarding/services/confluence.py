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
from urllib.parse import urlencode, urlparse

import httpx
import jwt as pyjwt
from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

import config
from config import JWT_SECRET_KEY, JWT_ALGORITHM
from database import engine
from onboarding.models.confluence_connection import ConfluenceConnection
from onboarding.models.document_page import DocumentPage
from onboarding.models.document_chunk import DocumentChunk
from onboarding.models.ingestion_job import IngestionJob
from services.encryption import encrypt_secret, decrypt_secret
from services.user import get_user_by_id
from services.company import (  # noqa: F401 (re-exported for back-compat + tests)
    _GENERIC_EMAIL_DOMAINS,
    _domain_from_email,
    _company_key_and_name,
    get_or_create_company_for_user,
)
from onboarding.services import embeddings as embedding_service
from onboarding.services import retrieval as retrieval_service
from onboarding.services.chunking import chunk_text, estimate_tokens

logger = logging.getLogger(__name__)

_AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
_ME_URL = "https://api.atlassian.com/me"
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

# Knowledge-base sources, all reached through the one shared Atlassian connection.
_SOURCES = ("confluence", "jira")

def _validate_source(source: str) -> str:
    if source not in _SOURCES:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}.")
    return source

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

def _get_connection(company_id: int) -> Optional[ConfluenceConnection]:
    with Session(engine) as session:
        return session.exec(
            select(ConfluenceConnection).where(ConfluenceConnection.company_id == company_id)
        ).first()

def get_site_url(company_id: int) -> Optional[str]:
    """The company's Atlassian site URL (e.g. https://acme.atlassian.net), used to
    build deep links back to Confluence pages / Jira issues in chat citations."""
    conn = _get_connection(company_id)
    return conn.site_url if conn else None

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

def _fetch_atlassian_email(access_token: str) -> Optional[str]:
    """Email of the Atlassian account that authorized (via the identity API), lowercased.
    Used to enforce that you connect with the SAME account as your Openship login."""
    resp = httpx.get(
        _ME_URL,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        timeout=_HTTP_TIMEOUT,
    )
    if resp.status_code != 200:
        logger.warning("Atlassian /me failed: %s", resp.status_code)
        return None
    email = (resp.json() or {}).get("email")
    return email.strip().lower() if email else None

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

    # The Atlassian account that authorized must be the SAME identity as the Openship
    # login — otherwise someone signed into a personal Atlassian in their browser would
    # bind their personal Confluence/Jira as the whole company's knowledge base.
    atlassian_email = _fetch_atlassian_email(access_token)
    if atlassian_email != user.email.strip().lower():
        raise HTTPException(
            status_code=403,
            detail=(
                f"Connect with your Openship account's Atlassian ({user.email}). You "
                f"authorized as {atlassian_email or 'an unverifiable account'} — sign out "
                "of Atlassian (or use a fresh window), sign in with your company account, "
                "and try again."
            ),
        )

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

def _counts(company_id: int, source: Optional[str] = None):
    with Session(engine) as session:
        pages_stmt = (
            select(func.count(DocumentPage.id))
            .where(DocumentPage.company_id == company_id)
            .where(DocumentPage.is_active == True)  # noqa: E712
        )
        chunks_stmt = select(func.count(DocumentChunk.id)).where(
            DocumentChunk.company_id == company_id
        )
        if source is not None:
            pages_stmt = pages_stmt.where(DocumentPage.source == source)
            chunks_stmt = chunks_stmt.where(DocumentChunk.source == source)
        pages = session.exec(pages_stmt).one()
        chunks = session.exec(chunks_stmt).one()
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

def get_connections_status(user) -> dict:
    """Status for the Connections page: the one shared Atlassian connection plus
    per-source indexed counts (Confluence + Jira) and any in-flight job."""
    company = get_or_create_company_for_user(user)
    conn = _get_connection(company.id)
    connected = conn is not None and conn.status == "ready"
    sources = {}
    for src in _SOURCES:
        pages, chunks = _counts(company.id, source=src) if connected else (0, 0)
        sources[src] = {"page_count": pages, "chunk_count": chunks}
    running = _running_job_progress(company.id) if connected else None
    return {
        "connected": connected,
        "status": conn.status if conn else None,
        "site_url": conn.site_url if conn else None,
        "sources": sources,
        "ingest": running,
        "last_result": (
            None if running else (_last_result_progress(company.id) if connected else None)
        ),
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

# What to expand on a Confluence search: page body, version (last editor + when),
# space, history (creator), ancestors (folder breadcrumb), and labels.
_CONTENT_EXPAND = "body.storage,version,space,history,ancestors,metadata.labels"

def _search_pages(cloud_id: str, token: str, space_key: str) -> list:
    """List pages AND blog posts in a space via CQL search, expanding body/version/
    space/history/ancestors/labels so we get full text + metadata in one call.
    Follows pagination."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    cql = f'space="{space_key}" and type in (page,blogpost)'
    query = urlencode({"cql": cql, "limit": _PAGE_SEARCH_LIMIT, "expand": _CONTENT_EXPAND})
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
    query = urlencode({"cql": f"id={page_id}", "expand": _CONTENT_EXPAND, "limit": 1})
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

def _confluence_meta(page: dict) -> Optional[dict]:
    """Pull author, last editor, breadcrumb (folder path), labels, updated time, and
    type from an expanded Confluence search result into a meta dict."""
    version = page.get("version") or {}
    history = page.get("history") or {}
    ancestors = page.get("ancestors") or []
    labels = (((page.get("metadata") or {}).get("labels") or {}).get("results")) or []
    meta = {
        "type": page.get("type") or "page",  # page | blogpost
        "author": (history.get("createdBy") or {}).get("displayName"),
        "last_editor": (version.get("by") or {}).get("displayName"),
        "breadcrumb": [a.get("title") for a in ancestors if a.get("title")] or None,
        "labels": [x.get("name") for x in labels if x.get("name")] or None,
        "updated": version.get("when"),
    }
    return {k: v for k, v in meta.items() if v} or None

def _confluence_text_prefix(meta: Optional[dict]) -> str:
    """A leading line embedding author / last-editor / path / labels into the page's
    searchable text, so 'docs by Yogesh Kisslay' and his Confluence work match the
    same way Jira 'Assignee: X' does. Returns '' when there's nothing to add."""
    if not meta:
        return ""
    parts = []
    author = meta.get("author")
    editor = meta.get("last_editor")
    if author:
        parts.append(f"Author: {author}")
    if editor and editor != author:
        parts.append(f"Last edited by: {editor}")
    if meta.get("breadcrumb"):
        parts.append("Path: " + " > ".join(meta["breadcrumb"]))
    if meta.get("labels"):
        parts.append("Labels: " + ", ".join(meta["labels"]))
    return (" | ".join(parts) + "\n") if parts else ""

# ── Jira REST client (shares the Atlassian OAuth connection) ─────────────────────

_JIRA_ISSUE_SEARCH_LIMIT = 100

def _jira_api_root(cloud_id: str) -> str:
    return f"https://api.atlassian.com/ex/jira/{cloud_id}"

def _fetch_projects(cloud_id: str, token: str) -> list:
    """List all Jira projects via the paginated project search. Returned dicts use
    the "key" field so the ingest read loop can treat them like Confluence spaces."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    start = 0
    results: list = []
    for _ in range(200):  # safety cap on pages
        query = urlencode({"startAt": start, "maxResults": 50})
        url = f"{_jira_api_root(cloud_id)}/rest/api/3/project/search?{query}"
        resp = _read_get(url, headers)
        if resp.status_code in (401, 403):
            raise HTTPException(status_code=401, detail="Jira session expired; please reconnect.")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to list Jira projects.")
        data = resp.json()
        for proj in data.get("values", []):
            if proj.get("key"):
                results.append({"key": proj["key"]})
        if data.get("isLast") or not data.get("values"):
            break
        start += len(data.get("values", []))
    return results

def _adf_to_text(node) -> str:
    """Flatten an Atlassian Document Format node tree to plain text. Jira v3 returns
    descriptions/comments as ADF (nested JSON), not HTML."""
    if node is None:
        return ""
    if isinstance(node, list):
        return " ".join(_adf_to_text(n) for n in node)
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return str(node.get("text", ""))
    return _adf_to_text(node.get("content"))

def _person_name(field) -> Optional[str]:
    """Display name from a Jira user field (assignee/reporter/comment author)."""
    if isinstance(field, dict):
        return field.get("displayName") or field.get("name") or field.get("emailAddress")
    return None

def _named(field) -> Optional[str]:
    """`name` from a Jira named field (status/issuetype/priority)."""
    return field.get("name") if isinstance(field, dict) else None

def _jira_issue_text(key: Optional[str], fields: dict) -> str:
    """Assemble a searchable blob from an issue: key, summary, the people involved
    (assignee/reporter), status/type/priority/labels, description, and comments.

    The people + status fields are the whole point of enrichment — 'what is X
    working on' only matches if the assignee's name is actually in the embedded
    text, which the bare summary/description does not contain."""
    parts = []
    if key:
        parts.append(f"Issue {key}")
    summary = fields.get("summary")
    if summary:
        parts.append(str(summary))

    meta = []
    for label, value in (
        ("Status", _named(fields.get("status"))),
        ("Type", _named(fields.get("issuetype"))),
        ("Priority", _named(fields.get("priority"))),
        ("Assignee", _person_name(fields.get("assignee"))),
        ("Reporter", _person_name(fields.get("reporter"))),
    ):
        if value:
            meta.append(f"{label}: {value}")
    labels = fields.get("labels") or []
    if labels:
        meta.append("Labels: " + ", ".join(str(x) for x in labels))
    if meta:
        parts.append(" | ".join(meta))

    description = _adf_to_text(fields.get("description"))
    if description:
        parts.append(description)
    for c in (fields.get("comment") or {}).get("comments") or []:
        body = _adf_to_text(c.get("body"))
        if body:
            author = _person_name(c.get("author"))
            parts.append(f"{author}: {body}" if author else body)
    return re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()

def _normalize_issue(issue: dict) -> dict:
    """Shape a Jira issue like a Confluence search result so _page_fields / the
    ingest write path can handle both uniformly. version stays None: Jira edits are
    detected by comparing extracted text in _upsert_page (issues have no int version)."""
    fields = issue.get("fields") or {}
    project = fields.get("project") or {}
    key = issue.get("key")
    summary = fields.get("summary") or key or "Untitled"
    status_category = ((fields.get("status") or {}).get("statusCategory") or {}).get("name")
    meta = {
        "issue_type": _named(fields.get("issuetype")),
        "priority": _named(fields.get("priority")),
        "labels": fields.get("labels") or None,
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "resolution": _named(fields.get("resolution")),
        "status_category": status_category,  # To Do | In Progress | Done
        "project": project.get("key"),
    }
    return {
        "id": key,
        "version": None,
        "space": {"key": project.get("key")},
        "title": str(summary)[:512],
        # Reuse the storage/value shape; text is already plain so it survives _strip_html.
        "body": {"storage": {"value": _jira_issue_text(key, fields)}},
        # Structured fields persisted to DocumentPage for exact person lookups/counts.
        "assignee": _person_name(fields.get("assignee")),
        "reporter": _person_name(fields.get("reporter")),
        "status": _named(fields.get("status")),
        "meta": {k: v for k, v in meta.items() if v},  # drop empty keys
    }

def _search_issues(cloud_id: str, token: str, project_key: str) -> list:
    """List issues in a project via the enhanced JQL search, pulling
    summary/description/comments. Returns normalized dicts (see _normalize_issue).

    Uses /rest/api/3/search/jql with token-based pagination (nextPageToken): the
    legacy /rest/api/3/search (startAt/total) was removed by Atlassian, so the old
    offset paging no longer works."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    # project_key comes from Jira's own project list (alphanumeric); quote it in JQL.
    jql = f'project="{project_key}" ORDER BY created ASC'
    next_token: Optional[str] = None
    results: list = []
    for _ in range(1000):  # safety cap
        params = {
            "jql": jql,
            "maxResults": _JIRA_ISSUE_SEARCH_LIMIT,
            "fields": (
                "summary,description,comment,project,assignee,reporter,status,"
                "issuetype,priority,labels,created,updated,resolution"
            ),
        }
        if next_token:
            params["nextPageToken"] = next_token
        url = f"{_jira_api_root(cloud_id)}/rest/api/3/search/jql?{urlencode(params)}"
        resp = _read_get(url, headers)
        if resp.status_code in (401, 403):
            raise HTTPException(status_code=401, detail="Jira session expired; please reconnect.")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to search Jira issues.")
        data = resp.json()
        for issue in data.get("issues", []):
            if issue.get("key"):
                results.append(_normalize_issue(issue))
        # Enhanced search paginates by token: stop when it says it's the last page
        # or hands back no further token.
        next_token = data.get("nextPageToken")
        if data.get("isLast") or not next_token:
            break
    return results

_ISSUE_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]+-\d+$")

def _fetch_single_issue(cloud_id: str, token: str, issue_key: str) -> Optional[dict]:
    """Fetch one Jira issue by key (for webhooks), normalized like _search_issues, or
    None. The key is validated so a webhook payload can't inject into the JQL."""
    if not issue_key or not _ISSUE_KEY_RE.match(str(issue_key)):
        return None
    params = urlencode(
        {
            "jql": f'key="{issue_key}"',
            "maxResults": 1,
            "fields": (
                "summary,description,comment,project,assignee,reporter,status,"
                "issuetype,priority,labels,created,updated,resolution"
            ),
        }
    )
    url = f"{_jira_api_root(cloud_id)}/rest/api/3/search/jql?{params}"
    resp = _read_get(url, {"Authorization": f"Bearer {token}", "Accept": "application/json"})
    if resp.status_code != 200:
        return None
    issues = resp.json().get("issues", [])
    return _normalize_issue(issues[0]) if issues else None

# ── knowledge base persistence ─────────────────────────────────────────────────

def _page_chunk_count(page_db_id: int) -> int:
    with Session(engine) as session:
        return int(
            session.exec(
                select(func.count(DocumentChunk.id)).where(DocumentChunk.page_id == page_db_id)
            ).one()
        )

def _upsert_page(company_id: int, page: dict, source: str = "confluence"):
    """Insert/update a document_pages row. Returns (page_db_id, changed, text)."""
    page_id, version, space_key, title, text = _page_fields(page)
    # Source-specific extras: Jira ships "meta" in its normalized dict; Confluence
    # pages carry the raw expanded fields, so derive it here.
    meta = page.get("meta") if source == "jira" else _confluence_meta(page)
    # For Confluence, prepend author/path/labels into the searchable text so authorship
    # ("docs by X") matches the same way Jira "Assignee: X" does.
    if source == "confluence":
        prefix = _confluence_text_prefix(meta)
        if prefix:
            text = f"{prefix}{text}" if text else prefix.strip()
    with Session(engine) as session:
        row = session.exec(
            select(DocumentPage)
            .where(DocumentPage.company_id == company_id)
            .where(DocumentPage.source == source)
            .where(DocumentPage.confluence_page_id == page_id)
        ).first()
        changed = False
        if row is None:
            row = DocumentPage(company_id=company_id, source=source, confluence_page_id=page_id)
            changed = True
        # Re-embed when the version bumped, the row was inactive, or the extracted
        # text actually differs. The content check is what catches Jira edits, whose
        # normalized "version" is None on both sides (see _search_issues).
        elif row.version != version or not row.is_active or row.content_text != text:
            changed = True
        row.version = version
        row.space_key = space_key
        row.title = title
        row.content_text = text
        # Structured Jira fields (absent for Confluence pages → left as None).
        row.assignee = page.get("assignee")
        row.reporter = page.get("reporter")
        row.status = page.get("status")
        row.meta = meta
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
    company_id: int,
    page_db_id: int,
    chunks: List[str],
    vectors: List[List[float]],
    source: str = "confluence",
) -> None:
    with Session(engine) as session:
        for i, (content, vector) in enumerate(zip(chunks, vectors)):
            session.add(
                DocumentChunk(
                    company_id=company_id,
                    page_id=page_db_id,
                    source=source,
                    chunk_index=i,
                    content=content,
                    embedding=vector,
                    token_count=estimate_tokens(content),
                )
            )
        session.commit()

def _embed_page(company_id: int, page_db_id: int, text: str, source: str = "confluence") -> int:
    """Chunk, embed, and (re)store a page's chunks. Returns chunk count."""
    chunks = chunk_text(text)
    if not chunks:
        _delete_chunks(page_db_id)
        return 0
    vectors = embedding_service.embed_texts(chunks)
    _delete_chunks(page_db_id)
    _store_chunks(company_id, page_db_id, chunks, vectors, source=source)
    return len(chunks)

# ── ingestion job ────────────────────────────────────────────────────────────

def _create_job(company_id: int, kind: str = "ingest", source: str = "confluence") -> int:
    with Session(engine) as session:
        job = IngestionJob(company_id=company_id, status="running", kind=kind, source=source)
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

def begin_ingest(user, background_tasks, source: str = "confluence") -> dict:
    """Validate, create a job, and schedule a full ingest in the background.
    If a job is already running for the company, return it instead of starting a
    second (avoids duplicate work and token-refresh races). `source` picks which
    product to ingest (confluence pages or jira issues)."""
    source = _validate_source(source)
    company = get_or_create_company_for_user(user)
    _require_ready_connection(company.id)
    existing = _running_job(company.id)
    if existing is not None:
        # A job (of any kind/source) is already running — return it with its true
        # kind/source so the UI labels progress honestly.
        return {
            "job_id": existing.id,
            "status": "running",
            "kind": existing.kind,
            "source": existing.source,
        }
    job_id = _create_job(company.id, source=source)
    background_tasks.add_task(_run_ingest, company.id, job_id, source)
    return {"job_id": job_id, "status": "running", "kind": "ingest", "source": source}

def _flush_embed_batch(company_id: int, buffer: list, source: str = "confluence") -> int:
    """Embed a buffer of (page_db_id, chunks) in ONE batched call, then store each
    page's chunks. Batching across pages is far faster than one call per page.
    Returns the number of chunks embedded."""
    texts = [chunk for _, chunks in buffer for chunk in chunks]
    vectors = embedding_service.embed_texts(texts)
    offset = 0
    for page_db_id, chunks in buffer:
        n = len(chunks)
        _delete_chunks(page_db_id)
        _store_chunks(company_id, page_db_id, chunks, vectors[offset : offset + n], source=source)
        offset += n
    return len(texts)

# Per-source read adapters: (list containers, list items in a container). Both
# products share one Atlassian OAuth connection, so ingest differs only in the
# read functions — the chunk/embed/store write path is identical.
def _source_readers(source: str):
    if source == "jira":
        return _fetch_projects, _search_issues
    return _fetch_spaces, _search_pages

def _run_ingest(company_id: int, job_id: int, source: str = "confluence") -> None:
    """Background worker, in three visible phases: reading (fetch every page/issue
    from every space/project) → indexing (upsert pages) → embedding (batch-embed
    their chunks). `source` selects the read adapter (Confluence pages or Jira
    issues); the write path is identical.

    Robustness: a failure confined to one space / page / embed-batch is logged and
    SKIPPED (counted, surfaced as a note, retried on the next ingest) rather than
    aborting the whole run. Only whole-run problems — no connection, an expired
    session, or nothing embedding at all — fail the job. Resumable: a page is
    (re)embedded only when new, changed, or missing chunks."""
    try:
        conn = _get_connection(company_id)
        if conn is None or not conn.access_token:
            raise HTTPException(status_code=409, detail="Atlassian is not connected.")
        token = _get_valid_token(conn)
        list_containers, list_items = _source_readers(source)

        # Phase 1 — reading: fetch every item from every container. A container that
        # keeps failing (after retries) is skipped so it can't sink the whole read.
        spaces = list_containers(conn.cloud_id, token)
        _update_job(job_id, phase="reading", total_spaces=len(spaces), processed_spaces=0)
        raw_pages: list = []
        skipped_spaces = 0
        for i, space in enumerate(spaces, start=1):
            key = space.get("key")
            if key:
                try:
                    raw_pages.extend(list_items(conn.cloud_id, token, key))
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
                    page_db_id, changed, text = _upsert_page(company_id, page, source=source)
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
                    company_id, job_id, buffer, embedded, failed_chunks, source=source
                )
                buffer, buffered_chunks = [], 0
        if buffer:
            embedded, failed_chunks = _flush_and_track(
                company_id, job_id, buffer, embedded, failed_chunks, source=source
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
        if source == "jira":
            # New assignees/reporters just landed — drop the cached name set so the
            # chat recognizes them immediately (no TTL wait).
            retrieval_service.refresh_names(company_id)
    except Exception as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        logger.exception("Ingestion job %s failed", job_id)
        if isinstance(exc, HTTPException) and exc.status_code == 401:
            _mark_status(company_id, "error")  # surface the Reconnect state in the UI
        _update_job(job_id, status="failed", phase="failed", error=str(detail), completed=True)

def _flush_and_track(company_id, job_id, buffer, embedded, failed_chunks, source="confluence"):
    """Flush an embed batch, updating progress. On failure, log and count the
    batch's chunks as failed instead of raising. Returns (embedded, failed_chunks)."""
    try:
        embedded += _flush_embed_batch(company_id, buffer, source=source)
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
        "source": job.source,
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

def verify_jira_webhook_secret(provided: Optional[str]) -> None:
    expected = config.JIRA_WEBHOOK_SECRET
    if not expected:
        raise HTTPException(status_code=503, detail="Jira webhooks are not configured.")
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

def _connection_by_site_url(site_url: str) -> Optional[ConfluenceConnection]:
    """Resolve a connection by its Atlassian site URL — Jira webhooks carry the site
    (in issue.self) rather than a cloud id."""
    if not site_url:
        return None
    base = site_url.rstrip("/")
    with Session(engine) as session:
        return session.exec(
            select(ConfluenceConnection).where(ConfluenceConnection.site_url == base)
        ).first()

def _deactivate_pages(
    page_id: str, company_id: Optional[int] = None, source: Optional[str] = None
) -> int:
    with Session(engine) as session:
        stmt = select(DocumentPage).where(DocumentPage.confluence_page_id == page_id)
        if company_id is not None:
            stmt = stmt.where(DocumentPage.company_id == company_id)
        if source is not None:
            stmt = stmt.where(DocumentPage.source == source)
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

# ── Jira webhooks ────────────────────────────────────────────────────────────────

def _reindex_issue(company_id: int, cloud_id: str, token: str, issue_key: str) -> bool:
    """Fetch one Jira issue, upsert it, and re-embed. Returns False if unreadable."""
    issue = _fetch_single_issue(cloud_id, token, issue_key)
    if issue is None:
        return False
    page_db_id, _changed, text = _upsert_page(company_id, issue, source="jira")
    if text:
        _embed_page(company_id, page_db_id, text, source="jira")
    return True

def _resolve_jira_connection(payload: dict) -> Optional[ConfluenceConnection]:
    """Find the connection a Jira webhook belongs to — by cloud id if present, else by
    the site URL embedded in issue.self (scopes the event to the right tenant)."""
    cloud_id = payload.get("cloudId") or payload.get("cloud_id")
    if cloud_id:
        return _connection_by_cloud_id(cloud_id)
    self_url = ((payload.get("issue") or {}).get("self")) or ""
    if self_url:
        parsed = urlparse(self_url)
        if parsed.scheme and parsed.netloc:
            return _connection_by_site_url(f"{parsed.scheme}://{parsed.netloc}")
    return None

def handle_jira_webhook(payload: dict) -> dict:
    """Handle a Jira webhook, never raising (so Atlassian doesn't retry-storm). The
    reconciler catches anything missed."""
    try:
        return _dispatch_jira_webhook(payload)
    except Exception:
        logger.exception("Jira webhook handling failed")
        return {"status": "error"}

def _dispatch_jira_webhook(payload: dict) -> dict:
    """Dispatch a Jira webhook: created/updated → re-embed the issue; deleted →
    deactivate it. Scoped to the connection's company by cloud id / site URL."""
    event = (payload.get("webhookEvent") or payload.get("event") or "").lower()
    issue = payload.get("issue") or {}
    issue_key = issue.get("key")
    if not issue_key:
        return {"status": "ignored"}

    # Only act on issue lifecycle events — match precisely so 'worklog_updated' etc.
    # don't trip the 'updat' substring.
    if (
        "issue_deleted" not in event
        and "issue_created" not in event
        and "issue_updated" not in event
    ):
        return {"status": "ignored"}

    conn = _resolve_jira_connection(payload)
    if conn is None or not conn.access_token:
        return {"status": "ignored"}

    if "issue_deleted" in event:
        count = _deactivate_pages(str(issue_key), conn.company_id, source="jira")
        return {"status": "removed" if count else "ignored"}
    token = _get_valid_token(conn)
    if _reindex_issue(conn.company_id, conn.cloud_id, token, str(issue_key)):
        return {"status": "updated"}
    return {"status": "ignored"}

# ── reconciliation ─────────────────────────────────────────────────────────────

def begin_reconcile(user, background_tasks, source: str = "confluence") -> dict:
    """Schedule a background reconcile (re-scan every space/project to fix deletions
    / restores). Returns the running job if one is already in flight."""
    source = _validate_source(source)
    company = get_or_create_company_for_user(user)
    _require_ready_connection(company.id)
    existing = _running_job(company.id)
    if existing is not None:
        return {
            "job_id": existing.id,
            "status": "running",
            "kind": existing.kind,
            "source": existing.source,
        }
    job_id = _create_job(company.id, kind="reconcile", source=source)
    background_tasks.add_task(_run_reconcile, company.id, job_id, source)
    return {"job_id": job_id, "status": "running", "kind": "reconcile", "source": source}

def _run_reconcile(company_id: int, job_id: int, source: str = "confluence") -> None:
    """Background worker: re-list every space/project (with progress), then
    deactivate pages that vanished upstream and reactivate ones that reappeared. A
    container that fails after retries is skipped rather than failing the whole sync.
    Scoped to `source` so a Confluence reconcile never touches Jira docs (or vice
    versa)."""
    try:
        conn = _get_connection(company_id)
        if conn is None or not conn.access_token:
            raise HTTPException(status_code=409, detail="Atlassian is not connected.")
        token = _get_valid_token(conn)
        list_containers, list_items = _source_readers(source)

        # Phase 1 — reading: gather the set of ids that still exist upstream.
        spaces = list_containers(conn.cloud_id, token)
        _update_job(job_id, phase="reading", total_spaces=len(spaces), processed_spaces=0)
        live_ids: set = set()
        skipped_spaces = 0
        for i, space in enumerate(spaces, start=1):
            key = space.get("key")
            if key:
                try:
                    for page in list_items(conn.cloud_id, token, key):
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

        # Phase 2 — reconciling: flip is_active based on presence upstream. Scoped to
        # this source so the other source's docs aren't mass-deactivated.
        _update_job(job_id, phase="reconciling")
        deactivated = reactivated = 0
        with Session(engine) as session:
            pages = session.exec(
                select(DocumentPage)
                .where(DocumentPage.company_id == company_id)
                .where(DocumentPage.source == source)
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
