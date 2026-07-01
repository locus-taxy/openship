"""
Confluence integration — Phase 1: connection.

Three-legged Atlassian OAuth 2.0. We register one OAuth app; every company
authorizes it and we store that company's tokens (encrypted, company-level).

Flow:
  start_connect  → build the Atlassian authorize URL (state = signed user id)
  handle_callback → exchange code for tokens, resolve the company, store them
  get_status     → is this company connected and ready?
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import urlencode

import httpx
import jwt as pyjwt
from fastapi import HTTPException
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError

import config
from config import JWT_SECRET_KEY, JWT_ALGORITHM
from database import engine
from models.company import Company
from models.confluence_connection import ConfluenceConnection
from models.onboarding_doc import OnboardingDoc
from models.ingestion_job import IngestionJob
from services.encryption import encrypt_secret, decrypt_secret
from services.user import get_user_by_id
from services import llm as llm_service
from services.llm import get_user_api_key, get_user_model, get_user_provider_name

logger = logging.getLogger(__name__)

_AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
_HTTP_TIMEOUT = 15
_STATE_EXPIRE_MINUTES = 15
_STATE_TYPE = "confluence_oauth"

# ── helpers ────────────────────────────────────────────────────────────────

def require_confluence_oauth() -> None:
    if not config.is_confluence_oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Confluence integration is not configured on this server.",
        )

def _domain_from_email(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower()

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
            # Another request created it concurrently — fetch the winner.
            session.rollback()
            return session.exec(select(Company).where(Company.domain == domain)).first()
        session.refresh(company)
        return company

def _get_connection(company_id: int) -> Optional[ConfluenceConnection]:
    with Session(engine) as session:
        return session.exec(
            select(ConfluenceConnection).where(ConfluenceConnection.company_id == company_id)
        ).first()

# ── Atlassian HTTP ───────────────────────────────────────────────────────────

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

# ── public API ───────────────────────────────────────────────────────────────

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

    resources = _fetch_accessible_resources(access_token)
    if not resources:
        raise HTTPException(
            status_code=400,
            detail="No accessible Confluence sites for this Atlassian account.",
        )
    site = resources[0]
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
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

def _approved_doc_count(company_id: int) -> int:
    with Session(engine) as session:
        rows = session.exec(
            select(OnboardingDoc.id)
            .where(OnboardingDoc.company_id == company_id)
            .where(OnboardingDoc.approved == True)  # noqa: E712
            .where(OnboardingDoc.is_active == True)  # noqa: E712
        ).all()
        return len(rows)

def get_status(user) -> dict:
    """Report whether this user's company has a ready Confluence connection."""
    company = get_or_create_company_for_user(user)
    conn = _get_connection(company.id)
    if conn is None or conn.status != "ready":
        return {
            "connected": False,
            "status": conn.status if conn else None,
            "site_url": None,
            "space_count": 0,
            "doc_count": 0,
        }
    space_keys = json.loads(conn.space_keys) if conn.space_keys else []
    return {
        "connected": True,
        "status": conn.status,
        "site_url": conn.site_url,
        "space_count": len(space_keys),
        "doc_count": _approved_doc_count(company.id),
    }

# ── Confluence REST client ─────────────────────────────────────────────────────

_TOKEN_SKEW_SECONDS = 60
# Spaces whose name/key hint at engineering docs are pre-selected for the admin.
# Substring match on "<name> <key>" (lowercased). Over-selection is harmless —
# the admin unchecks and the LLM filters page content later — so we lean broad,
# avoiding only fragments that live inside common non-eng words
# (e.g. "git" in "digital", "swe" in "answered").
_SPACE_KEYWORDS = (
    # core engineering
    "eng",
    "engineering",
    "software",
    "developer",
    "development",
    "dev",
    "tech",
    "technology",
    "technical",
    "coding",
    "code",
    "programming",
    # platform / infra / ops
    "platform",
    "infra",
    "infrastructure",
    "sre",
    "devops",
    "devsecops",
    "operations",
    "cloud",
    "kubernetes",
    "docker",
    "network",
    "networking",
    "systems",
    "system",
    # backend / frontend / services
    "backend",
    "frontend",
    "fullstack",
    "full-stack",
    "server",
    "api",
    "microservice",
    "services",
    # data / ml
    "data",
    "database",
    "analytics",
    "machine learning",
    "data science",
    "datascience",
    # quality / testing
    "qa",
    "quality",
    "sdet",
    "test",
    "testing",
    "automation",
    # security
    "security",
    "appsec",
    "infosec",
    "cybersecurity",
    # mobile
    "mobile",
    "android",
    "ios",
    # docs / onboarding / knowledge
    "onboard",
    "onboarding",
    "getting started",
    "wiki",
    "docs",
    "documentation",
    "handbook",
    "playbook",
    "runbook",
    "guide",
    "knowledge",
    # architecture / design
    "architecture",
    "design",
    "system design",
    "rfc",
    "adr",
    "hld",
    "lld",
    "blueprint",
    # product / delivery
    "product",
    "delivery",
    "release",
    # repos / source
    "repo",
    "repository",
    "github",
    "gitlab",
    "monorepo",
    # eng org units
    "squad",
    "guild",
    "tribe",
)

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
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(data.get("expires_in", 3600)))
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

def _fetch_spaces(cloud_id: str, token: str) -> list:
    """List all spaces in the connected site. The v1 /space collection endpoint
    is retired, so we use search (cql=type=space), which works with the classic
    search:confluence scope. Follows pagination links."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    query = urlencode({"cql": "type=space", "limit": 250})
    url = f"{_api_root(cloud_id)}/wiki/rest/api/search?{query}"
    results: list = []
    for _ in range(20):  # safety cap on pages
        resp = httpx.get(url, headers=headers, timeout=_HTTP_TIMEOUT)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to list Confluence spaces.")
        data = resp.json()
        for item in data.get("results", []):
            space = item.get("space")
            # Skip personal spaces (keys start with "~") — never onboarding docs.
            if space and not str(space.get("key", "")).startswith("~"):
                results.append(space)
        nxt = (data.get("_links") or {}).get("next")
        if not nxt:
            break
        url = f"{_api_root(cloud_id)}/wiki{nxt}"
    return results

def _is_suggested_space(name: str, key: str) -> bool:
    blob = f"{name} {key}".lower()
    return any(keyword in blob for keyword in _SPACE_KEYWORDS)

def list_spaces(user) -> dict:
    """List the company's Confluence spaces, pre-selecting likely eng/onboarding ones."""
    company = get_or_create_company_for_user(user)
    conn = _get_connection(company.id)
    if conn is None or conn.status != "ready" or not conn.access_token:
        raise HTTPException(status_code=409, detail="Confluence is not connected for your company.")
    token = _get_valid_token(conn)
    raw = _fetch_spaces(conn.cloud_id, token)
    spaces = [
        {
            "key": s.get("key"),
            "name": s.get("name"),
            "id": str(s.get("id")) if s.get("id") is not None else None,
            "suggested": _is_suggested_space(s.get("name", "") or "", s.get("key", "") or ""),
        }
        for s in raw
    ]
    return {"spaces": spaces}

# ── ingestion funnel ───────────────────────────────────────────────────────────

_CONTENT_EXCERPT_CHARS = 4000
_PAGE_SEARCH_LIMIT = 100
# Title/label hints used by the cheap pre-LLM filter.
_DOC_KEYWORDS = (
    "onboard",
    "architecture",
    "setup",
    "getting started",
    "guide",
    "overview",
    "service",
    "platform",
    "deployment",
    "runbook",
    "design",
    "infra",
    "api",
    "repo",
    "developer",
    "engineering",
    "workflow",
    "process",
)

_TAG_RE = re.compile(r"<[^>]+>")

def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html or "")
    return re.sub(r"\s+", " ", text).strip()

def _require_ready_connection(company_id: int) -> ConfluenceConnection:
    conn = _get_connection(company_id)
    if conn is None or conn.status != "ready" or not conn.access_token:
        raise HTTPException(status_code=409, detail="Confluence is not connected for your company.")
    return conn

def _search_pages(cloud_id: str, token: str, space_key: str) -> list:
    """List pages in a space via CQL search, expanding body/version/labels so
    classification needs no extra per-page call. Cheap: one page of up to 100."""
    cql = f'space="{space_key}" and type=page'
    query = urlencode(
        {
            "cql": cql,
            "limit": _PAGE_SEARCH_LIMIT,
            "expand": "body.storage,version,metadata.labels,space",
        }
    )
    url = f"{_api_root(cloud_id)}/wiki/rest/api/content/search?{query}"
    resp = httpx.get(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=_HTTP_TIMEOUT,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to search Confluence pages.")
    return resp.json().get("results", [])

def _page_labels(page: dict) -> List[str]:
    labels = (((page.get("metadata") or {}).get("labels") or {}).get("results")) or []
    return [lbl.get("name", "") for lbl in labels]

def _keyword_match_pages(pages: list) -> list:
    """Pages whose title/labels hint at engineering docs (strict, no fallback)."""
    matched = []
    for page in pages:
        blob = (page.get("title", "") + " " + " ".join(_page_labels(page))).lower()
        if any(keyword in blob for keyword in _DOC_KEYWORDS):
            matched.append(page)
    return matched

def _cheap_shortlist(pages: list) -> list:
    """Keep keyword-matching pages. If none match (e.g. a deliberately-picked
    space with terse titles), keep all rather than dropping the whole space."""
    matched = _keyword_match_pages(pages)
    return matched if matched else list(pages)

def _excerpt_from_page(page: dict):
    """Extract (version, text-excerpt) from a content-search result that was
    expanded with body.storage and version."""
    version = (page.get("version") or {}).get("number")
    body = (((page.get("body") or {}).get("storage") or {}).get("value")) or ""
    return version, _strip_html(body)[:_CONTENT_EXCERPT_CHARS]

def _fetch_page_excerpt(cloud_id: str, token: str, page_id: str):
    """Return (version, text-excerpt) for a single page, or (None, '') if
    unreadable. The v1 /content/{id} endpoint is retired, so we fetch via
    search (cql=id=...) which works with the classic search scope."""
    query = urlencode({"cql": f"id={page_id}", "expand": "body.storage,version", "limit": 1})
    url = f"{_api_root(cloud_id)}/wiki/rest/api/content/search?{query}"
    resp = httpx.get(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=_HTTP_TIMEOUT,
    )
    if resp.status_code != 200:
        return None, ""
    results = resp.json().get("results", [])
    if not results:
        return None, ""
    return _excerpt_from_page(results[0])

def _existing_page_ids(company_id: int) -> set:
    with Session(engine) as session:
        rows = session.exec(
            select(OnboardingDoc.confluence_page_id).where(OnboardingDoc.company_id == company_id)
        ).all()
        return set(rows)

def _create_job(company_id: int) -> int:
    with Session(engine) as session:
        job = IngestionJob(company_id=company_id, status="running")
        session.add(job)
        session.commit()
        session.refresh(job)
        return job.id

def _update_job(
    job_id: int,
    *,
    total: Optional[int] = None,
    processed: Optional[int] = None,
    status: Optional[str] = None,
    error: Optional[str] = None,
    completed: bool = False,
) -> None:
    with Session(engine) as session:
        job = session.get(IngestionJob, job_id)
        if job is None:
            return
        if total is not None:
            job.total_pages = total
        if processed is not None:
            job.processed_pages = processed
        if status is not None:
            job.status = status
        if error is not None:
            job.error = error
        if completed:
            job.completed_at = datetime.now(timezone.utc)
        session.add(job)
        session.commit()

def _store_candidate(
    company_id: int, page_id: str, page: dict, version, excerpt: str, classification: dict
) -> None:
    with Session(engine) as session:
        doc = OnboardingDoc(
            company_id=company_id,
            confluence_page_id=page_id,
            confluence_version=version,
            space_key=(
                (page.get("space") or {}).get("key")
                if isinstance(page.get("space"), dict)
                else page.get("spaceKey")
            ),
            title=page.get("title", "") or "Untitled",
            content_markdown=excerpt or None,
            role_tags=json.dumps(classification.get("role_tags") or []),
            confidence=classification.get("confidence"),
            approved=False,
            is_active=True,
            last_synced_at=datetime.now(timezone.utc),
        )
        session.add(doc)
        session.commit()

def _add_connected_spaces(company_id: int, space_keys: List[str]) -> None:
    """Remember which spaces a company has ingested (union), so the reconciler
    and gap detector know what's in scope."""
    with Session(engine) as session:
        conn = session.exec(
            select(ConfluenceConnection).where(ConfluenceConnection.company_id == company_id)
        ).first()
        if conn is None:
            return
        existing = json.loads(conn.space_keys) if conn.space_keys else []
        conn.space_keys = json.dumps(sorted(set(existing) | set(space_keys)))
        session.add(conn)
        session.commit()

def begin_ingest(
    user, space_keys: List[str], provider: str, api_key: str, model: Optional[str], background_tasks
) -> dict:
    """Validate, create a job row, and schedule the ingestion to run in the
    background. Returns immediately so the UI can poll get_ingest_status."""
    if not space_keys:
        raise HTTPException(status_code=400, detail="Select at least one space to ingest.")
    company = get_or_create_company_for_user(user)
    _require_ready_connection(company.id)  # raises 409 if not connected
    _add_connected_spaces(company.id, space_keys)
    job_id = _create_job(company.id)
    background_tasks.add_task(_run_ingest, company.id, space_keys, provider, api_key, model, job_id)
    return {"job_id": job_id, "status": "running"}

def _run_ingest(
    company_id: int,
    space_keys: List[str],
    provider: str,
    api_key: str,
    model: Optional[str],
    job_id: int,
) -> None:
    """Background worker: search → cheap filter → classify → store candidates.
    Add-only (pages already stored are skipped). Updates the job as it goes;
    exceptions are recorded on the job rather than raised (background context)."""
    try:
        conn = _get_connection(company_id)
        if conn is None or not conn.access_token:
            raise HTTPException(status_code=409, detail="Confluence is not connected.")
        token = _get_valid_token(conn)

        pages: list = []
        for space_key in space_keys:
            pages.extend(_search_pages(conn.cloud_id, token, space_key))
        shortlist = _cheap_shortlist(pages)
        _update_job(job_id, total=len(shortlist), processed=0)

        existing = _existing_page_ids(company_id)
        processed = 0
        for page in shortlist:
            page_id = str(page.get("id"))
            processed += 1
            if page_id not in existing:
                version, excerpt = _excerpt_from_page(page)
                result = llm_service.classify_onboarding_doc(
                    title=page.get("title", "") or "",
                    content_excerpt=excerpt,
                    provider=provider,
                    api_key=api_key,
                    model=model,
                )
                if result and result.get("is_relevant"):
                    _store_candidate(company_id, page_id, page, version, excerpt, result)
            _update_job(job_id, processed=processed)
        _update_job(job_id, status="done", completed=True)
    except Exception as exc:  # background task — record failure, never propagate
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        logger.exception("Ingestion job %s failed", job_id)
        _update_job(job_id, status="failed", error=str(detail), completed=True)

def get_ingest_status(user, job_id: int) -> dict:
    """Report progress for one ingestion job (company-scoped)."""
    company = get_or_create_company_for_user(user)
    with Session(engine) as session:
        job = session.get(IngestionJob, job_id)
        if job is None or job.company_id != company.id:
            raise HTTPException(status_code=404, detail="Ingestion job not found.")
        return {
            "job_id": job.id,
            "status": job.status,
            "total_pages": job.total_pages,
            "processed_pages": job.processed_pages,
            "error": job.error,
        }

def _candidate_dump(doc: OnboardingDoc) -> dict:
    return {
        "id": doc.id,
        "page_id": doc.confluence_page_id,
        "title": doc.title,
        "space_key": doc.space_key,
        "role_tags": json.loads(doc.role_tags) if doc.role_tags else [],
        "confidence": doc.confidence,
    }

def get_candidates(user) -> dict:
    """Return the pending (unapproved) ingested docs for review."""
    company = get_or_create_company_for_user(user)
    with Session(engine) as session:
        docs = session.exec(
            select(OnboardingDoc)
            .where(OnboardingDoc.company_id == company.id)
            .where(OnboardingDoc.approved == False)  # noqa: E712
            .where(OnboardingDoc.is_active == True)  # noqa: E712
            .order_by(OnboardingDoc.confidence.desc())
        ).all()
        return {"candidates": [_candidate_dump(d) for d in docs]}

def confirm_candidates(user, page_ids: List[str]) -> dict:
    """Approve the selected candidate pages. Add-only: this never deletes docs,
    so a careless selection can't wipe the company's onboarding set."""
    if not page_ids:
        raise HTTPException(status_code=400, detail="Select at least one document to confirm.")
    company = get_or_create_company_for_user(user)
    with Session(engine) as session:
        docs = session.exec(
            select(OnboardingDoc)
            .where(OnboardingDoc.company_id == company.id)
            .where(OnboardingDoc.confluence_page_id.in_(page_ids))
            .where(OnboardingDoc.approved == False)  # noqa: E712
        ).all()
        for doc in docs:
            doc.approved = True
            session.add(doc)
        session.commit()
        return {"approved": len(docs)}

# ── webhooks (freshness) ────────────────────────────────────────────────────────

def verify_webhook_secret(provided: Optional[str]) -> None:
    expected = config.CONFLUENCE_WEBHOOK_SECRET
    if not expected:
        raise HTTPException(status_code=503, detail="Confluence webhooks are not configured.")
    if not provided or provided != expected:
        raise HTTPException(status_code=401, detail="Invalid webhook secret.")

def _docs_by_page_id(page_id: str) -> list:
    with Session(engine) as session:
        return session.exec(
            select(OnboardingDoc).where(OnboardingDoc.confluence_page_id == page_id)
        ).all()

def _connection_by_cloud_id(cloud_id: str) -> Optional[ConfluenceConnection]:
    with Session(engine) as session:
        return session.exec(
            select(ConfluenceConnection).where(ConfluenceConnection.cloud_id == cloud_id)
        ).first()

def _update_doc_content(doc_id: int, version, excerpt: str) -> None:
    with Session(engine) as session:
        doc = session.get(OnboardingDoc, doc_id)
        if doc is None:
            return
        if version is not None:
            doc.confluence_version = version
        if excerpt:
            doc.content_markdown = excerpt
        doc.is_active = True
        doc.last_synced_at = datetime.now(timezone.utc)
        session.add(doc)
        session.commit()

def _deactivate_docs(page_id: str) -> int:
    with Session(engine) as session:
        docs = session.exec(
            select(OnboardingDoc).where(OnboardingDoc.confluence_page_id == page_id)
        ).all()
        for doc in docs:
            doc.is_active = False
            session.add(doc)
        session.commit()
        return len(docs)

def _admin_llm_creds(user_id: Optional[int]):
    """Return (provider, api_key, model) for the user who connected, or None."""
    if not user_id:
        return None
    user = get_user_by_id(user_id)
    if user is None:
        return None
    try:
        return (
            get_user_provider_name(user),
            get_user_api_key(user),
            get_user_model(user),
        )
    except Exception:
        return None

def _handle_page_updated(page_id: str) -> dict:
    docs = _docs_by_page_id(page_id)
    if not docs:
        return {"status": "ignored"}
    for doc in docs:
        conn = _get_connection(doc.company_id)
        if conn is not None and conn.access_token:
            token = _get_valid_token(conn)
            version, excerpt = _fetch_page_excerpt(conn.cloud_id, token, page_id)
            _update_doc_content(doc.id, version, excerpt)
    return {"status": "updated"}

def _handle_page_removed(page_id: str) -> dict:
    count = _deactivate_docs(page_id)
    return {"status": "removed" if count else "ignored"}

def _handle_page_created(payload: dict) -> dict:
    page = payload.get("page") or {}
    page_id = str(page.get("id")) if page.get("id") is not None else None
    cloud_id = payload.get("cloudId") or payload.get("cloud_id")
    if not page_id or not cloud_id:
        return {"status": "ignored"}
    conn = _connection_by_cloud_id(cloud_id)
    if conn is None or not conn.access_token:
        return {"status": "ignored"}
    if page_id in _existing_page_ids(conn.company_id):
        return {"status": "exists"}
    creds = _admin_llm_creds(conn.connected_by_user_id)
    if creds is None:
        return {"status": "skipped_no_creds"}
    provider, api_key, model = creds
    token = _get_valid_token(conn)
    version, excerpt = _fetch_page_excerpt(conn.cloud_id, token, page_id)
    result = llm_service.classify_onboarding_doc(
        title=page.get("title", "") or "",
        content_excerpt=excerpt,
        provider=provider,
        api_key=api_key,
        model=model,
    )
    if result and result.get("is_relevant"):
        _store_candidate(conn.company_id, page_id, page, version, excerpt, result)
        return {"status": "added"}
    return {"status": "not_relevant"}

def handle_webhook(payload: dict) -> dict:
    """Dispatch a Confluence webhook. Updates/removals match by page id (globally
    unique); creations resolve the company by cloud id then classify."""
    event = (payload.get("event") or payload.get("webhookEvent") or "").lower()
    page = payload.get("page") or {}
    page_id = str(page.get("id")) if page.get("id") is not None else None

    if "creat" in event:
        return _handle_page_created(payload)
    if "remov" in event or "trash" in event or "delet" in event:
        if page_id:
            return _handle_page_removed(page_id)
        return {"status": "ignored"}
    if "updat" in event:
        if page_id:
            return _handle_page_updated(page_id)
        return {"status": "ignored"}
    return {"status": "ignored"}

# ── reconciliation & gap detection (correctness) ────────────────────────────────

def reconcile_company(company_id: int) -> dict:
    """Re-list the connected spaces and sync activation state: deactivate docs
    whose page has vanished upstream, reactivate ones that reappeared. The slow
    path that catches anything missed webhooks dropped."""
    conn = _get_connection(company_id)
    if conn is None or conn.status != "ready" or not conn.access_token:
        raise HTTPException(status_code=409, detail="Confluence is not connected for your company.")
    spaces = json.loads(conn.space_keys) if conn.space_keys else []
    if not spaces:
        return {"deactivated": 0, "reactivated": 0}
    token = _get_valid_token(conn)

    live_ids: set = set()
    for space_key in spaces:
        for page in _search_pages(conn.cloud_id, token, space_key):
            live_ids.add(str(page.get("id")))

    deactivated = reactivated = 0
    with Session(engine) as session:
        docs = session.exec(
            select(OnboardingDoc).where(OnboardingDoc.company_id == company_id)
        ).all()
        for doc in docs:
            present = doc.confluence_page_id in live_ids
            if not present and doc.is_active:
                doc.is_active = False
                session.add(doc)
                deactivated += 1
            elif present and not doc.is_active:
                doc.is_active = True
                session.add(doc)
                reactivated += 1
        session.commit()
    return {"deactivated": deactivated, "reactivated": reactivated}

def detect_gaps(user) -> dict:
    """Scan spaces the company hasn't connected and flag onboarding-looking pages
    they may be missing."""
    company = get_or_create_company_for_user(user)
    conn = _require_ready_connection(company.id)
    token = _get_valid_token(conn)
    connected = set(json.loads(conn.space_keys) if conn.space_keys else [])

    gaps = []
    for space in _fetch_spaces(conn.cloud_id, token):
        key = space.get("key")
        if not key or key in connected:
            continue
        likely = _keyword_match_pages(_search_pages(conn.cloud_id, token, key))
        if likely:
            gaps.append({"space_key": key, "name": space.get("name"), "likely_docs": len(likely)})
    return {"gaps": gaps, "total": sum(g["likely_docs"] for g in gaps)}
