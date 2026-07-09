"""Tests for the Confluence integration (connect + RAG ingest + webhooks)."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

import config
from onboarding.models.company import Company
from onboarding.models.confluence_connection import ConfluenceConnection
from onboarding.models.document_page import DocumentPage
from onboarding.models.ingestion_job import IngestionJob

# ── helpers ──────────────────────────────────────────────────────────────────

def _user(uid=1, email="dev@locus.sh"):
    u = MagicMock()
    u.id = uid
    u.email = email
    return u

def _resp(status, payload):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    return r

def _conn(**kw):
    defaults = dict(id=1, company_id=1, status="ready", cloud_id="c1", access_token="enc")
    defaults.update(kw)
    return ConfluenceConnection(**defaults)

def _patch_session(target="onboarding.services.confluence.Session"):
    patcher = patch(target)
    mock_cls = patcher.start()
    session_mock = MagicMock()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher, session_mock

def _page(pid="p1", version=1, space="ENG", title="Arch", body="<p>hello world</p>"):
    return {
        "id": pid,
        "version": {"number": version},
        "space": {"key": space},
        "title": title,
        "body": {"storage": {"value": body}},
    }

# ── OAuth config helper ─────────────────────────────────────────────────────────

class TestOauthConfigured:
    def test_all_set_true(self):
        with (
            patch("config.ATLASSIAN_CLIENT_ID", "cid"),
            patch("config.ATLASSIAN_CLIENT_SECRET", "secret"),
            patch("config.ATLASSIAN_REDIRECT_URI", "https://app/cb"),
        ):
            assert config.is_confluence_oauth_configured() is True

    def test_missing_secret_false(self):
        with (
            patch("config.ATLASSIAN_CLIENT_ID", "cid"),
            patch("config.ATLASSIAN_CLIENT_SECRET", None),
            patch("config.ATLASSIAN_REDIRECT_URI", "https://app/cb"),
        ):
            assert config.is_confluence_oauth_configured() is False

# ── pure helpers ────────────────────────────────────────────────────────────────

class TestHelpers:
    def test_domain_from_email(self):
        from onboarding.services.confluence import _domain_from_email

        assert _domain_from_email("Dev@Locus.SH") == "locus.sh"

    def test_state_roundtrip(self):
        from onboarding.services.confluence import _create_state, _decode_state

        assert _decode_state(_create_state(7)) == 7

    def test_decode_state_garbage(self):
        from onboarding.services.confluence import _decode_state

        with pytest.raises(HTTPException) as exc:
            _decode_state("nope")
        assert exc.value.status_code == 400

    def test_decode_state_wrong_type(self):
        import jwt as pyjwt
        from config import JWT_SECRET_KEY, JWT_ALGORITHM
        from onboarding.services.confluence import _decode_state

        tok = pyjwt.encode({"sub": "1", "type": "access"}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        with pytest.raises(HTTPException) as exc:
            _decode_state(tok)
        assert exc.value.status_code == 400

    def test_strip_html(self):
        from onboarding.services.confluence import _strip_html

        assert _strip_html("<p>Hi <b>there</b></p>") == "Hi there"

    def test_page_fields(self):
        from onboarding.services.confluence import _page_fields

        pid, version, space_key, title, text = _page_fields(_page())
        assert (pid, version, space_key, title) == ("p1", 1, "ENG", "Arch")
        assert text == "hello world"

# ── company resolution ───────────────────────────────────────────────────────

class TestCompanyResolution:
    # Company resolution moved to services.company (see tests/test_company.py). These
    # confluence-level tests only cover the connection lookup now.
    def test_get_connection(self):
        conn = _conn()
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = conn
            from onboarding.services.confluence import _get_connection

            assert _get_connection(1) is conn
        finally:
            patcher.stop()

    def test_require_ready_ok(self):
        with patch("onboarding.services.confluence._get_connection", return_value=_conn()):
            from onboarding.services.confluence import _require_ready_connection

            assert _require_ready_connection(1).status == "ready"

    def test_require_ready_409(self):
        with patch("onboarding.services.confluence._get_connection", return_value=None):
            from onboarding.services.confluence import _require_ready_connection

            with pytest.raises(HTTPException) as exc:
                _require_ready_connection(1)
            assert exc.value.status_code == 409

# ── OAuth HTTP + connect/callback ────────────────────────────────────────────────

class TestOAuthHttp:
    def test_exchange_code_success(self):
        from onboarding.services.confluence import _exchange_code

        with patch(
            "onboarding.services.confluence.httpx.post",
            return_value=_resp(200, {"access_token": "AT"}),
        ):
            assert _exchange_code("code")["access_token"] == "AT"

    def test_exchange_code_failure(self):
        from onboarding.services.confluence import _exchange_code

        with patch("onboarding.services.confluence.httpx.post", return_value=_resp(400, {})):
            with pytest.raises(HTTPException) as exc:
                _exchange_code("code")
            assert exc.value.status_code == 502

    def test_fetch_resources_success(self):
        from onboarding.services.confluence import _fetch_accessible_resources

        with patch(
            "onboarding.services.confluence.httpx.get", return_value=_resp(200, [{"id": "c1"}])
        ):
            assert _fetch_accessible_resources("AT")[0]["id"] == "c1"

    def test_fetch_resources_failure(self):
        from onboarding.services.confluence import _fetch_accessible_resources

        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(401, {})):
            with pytest.raises(HTTPException) as exc:
                _fetch_accessible_resources("AT")
            assert exc.value.status_code == 502

    def test_fetch_atlassian_email_lowercased(self):
        from onboarding.services.confluence import _fetch_atlassian_email

        with patch(
            "onboarding.services.confluence.httpx.get",
            return_value=_resp(200, {"email": "Dev@Locus.SH", "account_id": "a1"}),
        ):
            assert _fetch_atlassian_email("AT") == "dev@locus.sh"

    def test_fetch_atlassian_email_none_on_failure(self):
        from onboarding.services.confluence import _fetch_atlassian_email

        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(403, {})):
            assert _fetch_atlassian_email("AT") is None

    def test_fetch_atlassian_email_none_when_absent(self):
        from onboarding.services.confluence import _fetch_atlassian_email

        with patch(
            "onboarding.services.confluence.httpx.get",
            return_value=_resp(200, {"account_id": "a1"}),
        ):
            assert _fetch_atlassian_email("AT") is None

    def test_upsert_connection_new(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = None
            from onboarding.services.confluence import _upsert_connection

            _upsert_connection(1, 1, "c1", "https://s", "AT", "RT", datetime.now(timezone.utc))
            session.add.assert_called_once()
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_upsert_connection_existing_no_refresh(self):
        conn = _conn(status="pending")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = conn
            from onboarding.services.confluence import _upsert_connection

            _upsert_connection(1, 1, "c1", None, "AT", None, datetime.now(timezone.utc))
            assert conn.refresh_token is None
            assert conn.status == "ready"
        finally:
            patcher.stop()

class TestStartConnect:
    def test_not_configured_503(self):
        from onboarding.services.confluence import start_connect

        with patch("config.is_confluence_oauth_configured", return_value=False):
            with pytest.raises(HTTPException) as exc:
                start_connect(_user())
            assert exc.value.status_code == 503

    def test_configured(self):
        from onboarding.services.confluence import start_connect

        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("config.ATLASSIAN_CLIENT_ID", "cid"),
            patch("config.ATLASSIAN_REDIRECT_URI", "https://app/cb"),
            patch("config.ATLASSIAN_OAUTH_SCOPES", "scopeA"),
        ):
            out = start_connect(_user())
        assert "client_id=cid" in out["authorize_url"]

    def test_allows_generic_email(self):
        # Personal emails are no longer blocked — they get their own solo org.
        from onboarding.services.confluence import start_connect

        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("config.ATLASSIAN_CLIENT_ID", "cid"),
            patch("config.ATLASSIAN_REDIRECT_URI", "https://app/cb"),
            patch("config.ATLASSIAN_OAUTH_SCOPES", "scopeA"),
        ):
            out = start_connect(_user(email="someone@gmail.com"))
        assert "authorize_url" in out

class TestHandleCallback:
    def _state(self, uid=1):
        from onboarding.services.confluence import _create_state

        return _create_state(uid)

    def test_success(self):
        company = Company(id=5, name="locus.sh", domain="locus.sh")
        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("onboarding.services.confluence.get_user_by_id", return_value=_user()),
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=company,
            ),
            patch(
                "onboarding.services.confluence._exchange_code",
                return_value={"access_token": "AT", "expires_in": 3600},
            ),
            patch(
                "onboarding.services.confluence._fetch_atlassian_email",
                return_value="dev@locus.sh",  # matches the Openship user
            ),
            patch(
                "onboarding.services.confluence._fetch_accessible_resources",
                return_value=[{"id": "c1", "url": "https://x"}],
            ),
            patch("onboarding.services.confluence._upsert_connection") as up,
        ):
            from onboarding.services.confluence import handle_callback

            assert handle_callback("code", self._state()) == config.CONFLUENCE_POST_CONNECT_REDIRECT
            up.assert_called_once()

    def test_rejects_mismatched_atlassian_account(self):
        # Signed into Atlassian as a personal account → 403, no connection made.
        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("onboarding.services.confluence.get_user_by_id", return_value=_user()),
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=Company(id=5, name="locus.sh", domain="locus.sh"),
            ),
            patch(
                "onboarding.services.confluence._exchange_code",
                return_value={"access_token": "AT", "expires_in": 3600},
            ),
            patch(
                "onboarding.services.confluence._fetch_atlassian_email",
                return_value="someone@gmail.com",
            ),
            patch("onboarding.services.confluence._upsert_connection") as up,
        ):
            from onboarding.services.confluence import handle_callback

            with pytest.raises(HTTPException) as exc:
                handle_callback("code", self._state())
            assert exc.value.status_code == 403
            up.assert_not_called()

    def test_rejects_when_email_unverifiable(self):
        # /me didn't return an email → fail closed (don't connect).
        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("onboarding.services.confluence.get_user_by_id", return_value=_user()),
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=Company(id=5, name="locus.sh", domain="locus.sh"),
            ),
            patch(
                "onboarding.services.confluence._exchange_code",
                return_value={"access_token": "AT", "expires_in": 3600},
            ),
            patch("onboarding.services.confluence._fetch_atlassian_email", return_value=None),
            patch("onboarding.services.confluence._upsert_connection") as up,
        ):
            from onboarding.services.confluence import handle_callback

            with pytest.raises(HTTPException) as exc:
                handle_callback("code", self._state())
            assert exc.value.status_code == 403
            up.assert_not_called()

    def test_not_configured(self):
        from onboarding.services.confluence import handle_callback

        with patch("config.is_confluence_oauth_configured", return_value=False):
            with pytest.raises(HTTPException) as exc:
                handle_callback("c", "s")
            assert exc.value.status_code == 503

    def test_unknown_user(self):
        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("onboarding.services.confluence.get_user_by_id", return_value=None),
        ):
            from onboarding.services.confluence import handle_callback

            with pytest.raises(HTTPException) as exc:
                handle_callback("c", self._state(9))
            assert exc.value.status_code == 400

    def test_no_access_token(self):
        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("onboarding.services.confluence.get_user_by_id", return_value=_user()),
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch("onboarding.services.confluence._exchange_code", return_value={}),
        ):
            from onboarding.services.confluence import handle_callback

            with pytest.raises(HTTPException) as exc:
                handle_callback("c", self._state())
            assert exc.value.status_code == 502

    def test_no_resources(self):
        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("onboarding.services.confluence.get_user_by_id", return_value=_user()),
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch(
                "onboarding.services.confluence._exchange_code", return_value={"access_token": "AT"}
            ),
            patch(
                "onboarding.services.confluence._fetch_atlassian_email", return_value="dev@locus.sh"
            ),
            patch("onboarding.services.confluence._fetch_accessible_resources", return_value=[]),
        ):
            from onboarding.services.confluence import handle_callback

            with pytest.raises(HTTPException) as exc:
                handle_callback("c", self._state())
            assert exc.value.status_code == 400

# ── status ────────────────────────────────────────────────────────────────────

class TestGetStatus:
    def _company(self):
        return Company(id=1, name="locus.sh", domain="locus.sh")

    def test_not_connected(self):
        with (
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=self._company(),
            ),
            patch("onboarding.services.confluence._get_connection", return_value=None),
        ):
            from onboarding.services.confluence import get_status

            s = get_status(_user())
            assert s["connected"] is False and s["page_count"] == 0

    def test_ready_with_counts(self):
        with (
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=self._company(),
            ),
            patch(
                "onboarding.services.confluence._get_connection",
                return_value=_conn(site_url="https://x"),
            ),
            patch("onboarding.services.confluence._counts", return_value=(12, 340)),
            patch("onboarding.services.confluence._running_job", return_value=None),
            patch("onboarding.services.confluence._latest_finished_job", return_value=None),
        ):
            from onboarding.services.confluence import get_status

            s = get_status(_user())
            assert s["connected"] is True
            assert s["page_count"] == 12 and s["chunk_count"] == 340
            assert s["ingest"] is None and s["last_result"] is None

    def test_ready_reports_last_result(self):
        with (
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=self._company(),
            ),
            patch(
                "onboarding.services.confluence._get_connection",
                return_value=_conn(site_url="https://x"),
            ),
            patch("onboarding.services.confluence._counts", return_value=(12, 340)),
            patch("onboarding.services.confluence._running_job", return_value=None),
            patch(
                "onboarding.services.confluence._latest_finished_job",
                return_value=IngestionJob(
                    id=7,
                    company_id=1,
                    kind="reconcile",
                    status="done",
                    error="0 removed, 0 restored",
                ),
            ),
        ):
            from onboarding.services.confluence import get_status

            s = get_status(_user())
            assert s["ingest"] is None
            assert s["last_result"]["job_id"] == 7 and s["last_result"]["kind"] == "reconcile"

    def test_ready_reports_running_ingest(self):
        with (
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=self._company(),
            ),
            patch(
                "onboarding.services.confluence._get_connection",
                return_value=_conn(site_url="https://x"),
            ),
            patch("onboarding.services.confluence._counts", return_value=(12, 340)),
            patch(
                "onboarding.services.confluence._running_job",
                return_value=IngestionJob(
                    id=9,
                    company_id=1,
                    status="running",
                    total_pages=100,
                    processed_pages=40,
                    total_chunks=200,
                    embedded_chunks=50,
                ),
            ),
        ):
            from onboarding.services.confluence import get_status

            s = get_status(_user())
            assert s["ingest"]["job_id"] == 9 and s["ingest"]["embedded_chunks"] == 50

class TestGetSiteUrl:
    def test_returns_site_url(self):
        with patch(
            "onboarding.services.confluence._get_connection",
            return_value=_conn(site_url="https://acme.atlassian.net"),
        ):
            from onboarding.services.confluence import get_site_url

            assert get_site_url(1) == "https://acme.atlassian.net"

    def test_none_when_no_connection(self):
        with patch("onboarding.services.confluence._get_connection", return_value=None):
            from onboarding.services.confluence import get_site_url

            assert get_site_url(1) is None

class TestConnectionsStatus:
    def _company(self):
        return Company(id=1, name="locus.sh", domain="locus.sh")

    def test_not_connected(self):
        with (
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=self._company(),
            ),
            patch("onboarding.services.confluence._get_connection", return_value=None),
        ):
            from onboarding.services.confluence import get_connections_status

            s = get_connections_status(_user())
            assert s["connected"] is False
            assert s["sources"]["confluence"] == {"page_count": 0, "chunk_count": 0}
            assert s["sources"]["jira"] == {"page_count": 0, "chunk_count": 0}
            assert s["ingest"] is None and s["last_result"] is None

    def test_connected_per_source_counts(self):
        def counts(company_id, source=None):
            return {"confluence": (10, 200), "jira": (5, 60)}[source]

        with (
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=self._company(),
            ),
            patch(
                "onboarding.services.confluence._get_connection",
                return_value=_conn(site_url="https://x"),
            ),
            patch("onboarding.services.confluence._counts", side_effect=counts),
            patch("onboarding.services.confluence._running_job", return_value=None),
            patch("onboarding.services.confluence._latest_finished_job", return_value=None),
        ):
            from onboarding.services.confluence import get_connections_status

            s = get_connections_status(_user())
            assert s["connected"] is True
            assert s["sources"]["confluence"] == {"page_count": 10, "chunk_count": 200}
            assert s["sources"]["jira"] == {"page_count": 5, "chunk_count": 60}

# ── token freshness / refresh ────────────────────────────────────────────────────

class TestToken:
    def test_expired_none(self):
        from onboarding.services.confluence import _is_token_expired

        assert _is_token_expired(None) is True

    def test_not_expired_future(self):
        from onboarding.services.confluence import _is_token_expired

        assert _is_token_expired(datetime.now(timezone.utc) + timedelta(hours=1)) is False

    def test_expired_past_naive(self):
        from onboarding.services.confluence import _is_token_expired

        assert _is_token_expired(datetime.utcnow() - timedelta(hours=1)) is True

    def test_get_valid_uses_existing(self):
        from services.encryption import encrypt_secret
        from onboarding.services.confluence import _get_valid_token

        conn = _conn(
            access_token=encrypt_secret("LIVE"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert _get_valid_token(conn) == "LIVE"

    def test_get_valid_refreshes(self):
        from onboarding.services.confluence import _get_valid_token

        conn = _conn(access_token="e", token_expires_at=None)
        with patch(
            "onboarding.services.confluence._refresh_access_token", return_value="FRESH"
        ) as ref:
            assert _get_valid_token(conn) == "FRESH"
            ref.assert_called_once()

    def test_refresh_no_token_401(self):
        from onboarding.services.confluence import _refresh_access_token

        with pytest.raises(HTTPException) as exc:
            _refresh_access_token(_conn(refresh_token=None))
        assert exc.value.status_code == 401

    def test_refresh_failure_marks_error(self):
        from services.encryption import encrypt_secret
        from onboarding.services.confluence import _refresh_access_token

        conn = _conn(refresh_token=encrypt_secret("RT"))
        with (
            patch("onboarding.services.confluence.httpx.post", return_value=_resp(400, {})),
            patch("onboarding.services.confluence._mark_status") as mark,
        ):
            with pytest.raises(HTTPException) as exc:
                _refresh_access_token(conn)
            assert exc.value.status_code == 401
            mark.assert_called_once_with(1, "error")

    def test_refresh_success_persists(self):
        from services.encryption import encrypt_secret
        from onboarding.services.confluence import _refresh_access_token

        conn = _conn(refresh_token=encrypt_secret("RT"))
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = conn
            with patch(
                "onboarding.services.confluence.httpx.post",
                return_value=_resp(200, {"access_token": "NEW", "expires_in": 3600}),
            ):
                assert _refresh_access_token(conn) == "NEW"
                session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_mark_status_present(self):
        conn = _conn()
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = conn
            from onboarding.services.confluence import _mark_status

            _mark_status(1, "error")
            assert conn.status == "error"
        finally:
            patcher.stop()

    def test_mark_status_absent(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = None
            from onboarding.services.confluence import _mark_status

            _mark_status(1, "error")
            session.commit.assert_not_called()
        finally:
            patcher.stop()

# ── REST client: spaces / pages ──────────────────────────────────────────────────

class TestReadGet:
    def test_retries_then_succeeds(self):
        import httpx
        from onboarding.services.confluence import _read_get

        ok = _resp(200, {"results": []})
        with (
            patch(
                "onboarding.services.confluence.httpx.get",
                side_effect=[httpx.ConnectTimeout("boom"), ok],
            ),
            patch("onboarding.services.confluence._sleep") as slept,
        ):
            assert _read_get("http://x", {}) is ok
            slept.assert_called_once()

    def test_retries_on_retryable_status(self):
        from onboarding.services.confluence import _read_get

        ok = _resp(200, {})
        with (
            patch("onboarding.services.confluence.httpx.get", side_effect=[_resp(503, {}), ok]),
            patch("onboarding.services.confluence._sleep"),
        ):
            assert _read_get("http://x", {}) is ok

    def test_exhausted_network_error_raises_502(self):
        import httpx
        from onboarding.services.confluence import _read_get

        with (
            patch(
                "onboarding.services.confluence.httpx.get",
                side_effect=httpx.ConnectError("down"),
            ),
            patch("onboarding.services.confluence._sleep"),
        ):
            with pytest.raises(HTTPException) as exc:
                _read_get("http://x", {})
            assert exc.value.status_code == 502

    def test_exhausted_retryable_status_returns_last_response(self):
        from onboarding.services.confluence import _read_get

        with (
            patch("onboarding.services.confluence.httpx.get", return_value=_resp(503, {})),
            patch("onboarding.services.confluence._sleep"),
        ):
            assert _read_get("http://x", {}).status_code == 503

    def test_honors_retry_after_header_on_429(self):
        from onboarding.services.confluence import _read_get

        r429 = MagicMock(status_code=429, headers={"Retry-After": "7"})
        ok = _resp(200, {})
        with (
            patch("onboarding.services.confluence.httpx.get", side_effect=[r429, ok]),
            patch("onboarding.services.confluence._sleep") as slept,
        ):
            assert _read_get("http://x", {}) is ok
            slept.assert_called_once_with(7.0)

class TestCurrentToken:
    def test_reloads_connection_for_fresh_token(self):
        from onboarding.services.confluence import _current_token

        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()) as gc,
            patch("onboarding.services.confluence._get_valid_token", return_value="tok") as gv,
        ):
            assert _current_token(1, _conn()) == "tok"
            gc.assert_called_once_with(1)
            gv.assert_called_once()

    def test_falls_back_to_passed_connection_when_reload_none(self):
        from onboarding.services.confluence import _current_token

        fallback = _conn()
        with (
            patch("onboarding.services.confluence._get_connection", return_value=None),
            patch("onboarding.services.confluence._get_valid_token", return_value="tok") as gv,
        ):
            assert _current_token(1, fallback) == "tok"
            gv.assert_called_once_with(fallback)

class TestRetryDelay:
    def test_retry_after_seconds_parses_valid(self):
        from onboarding.services.confluence import _retry_after_seconds

        assert _retry_after_seconds(MagicMock(headers={"Retry-After": "5"})) == 5.0

    def test_retry_after_seconds_none_when_missing_invalid_or_negative(self):
        from onboarding.services.confluence import _retry_after_seconds

        assert _retry_after_seconds(MagicMock(headers={})) is None  # missing → TypeError
        assert (
            _retry_after_seconds(MagicMock(headers={"Retry-After": "soon"})) is None
        )  # ValueError
        assert _retry_after_seconds(MagicMock(headers={"Retry-After": "-1"})) is None  # negative

    def test_retry_delay_falls_back_to_backoff(self):
        from onboarding.services.confluence import _retry_delay, _HTTP_RETRY_BACKOFF

        assert _retry_delay(MagicMock(headers={}), 0) == _HTTP_RETRY_BACKOFF
        assert _retry_delay(None, 1) == _HTTP_RETRY_BACKOFF * 2  # no response → backoff

    def test_retry_delay_honors_and_clamps_retry_after(self):
        from onboarding.services.confluence import _retry_delay, _HTTP_RETRY_MAX_SLEEP

        assert _retry_delay(MagicMock(headers={"Retry-After": "3"}), 5) == 3.0
        assert _retry_delay(MagicMock(headers={"Retry-After": "99999"}), 0) == _HTTP_RETRY_MAX_SLEEP

class TestFetchSpaces:
    def test_single(self):
        from onboarding.services.confluence import _fetch_spaces

        with patch(
            "onboarding.services.confluence.httpx.get",
            return_value=_resp(200, {"results": [{"space": {"key": "ENG"}}]}),
        ):
            assert _fetch_spaces("c1", "t")[0]["key"] == "ENG"

    def test_skips_personal(self):
        from onboarding.services.confluence import _fetch_spaces

        payload = {
            "results": [{"space": {"key": "ENG"}}, {"space": {"key": "~123"}}, {"title": "x"}]
        }
        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(200, payload)):
            assert [s["key"] for s in _fetch_spaces("c1", "t")] == ["ENG"]

    def test_paginates(self):
        from onboarding.services.confluence import _fetch_spaces

        p1 = _resp(
            200, {"results": [{"space": {"key": "A"}}], "_links": {"next": "/rest/api/search?c=1"}}
        )
        p2 = _resp(200, {"results": [{"space": {"key": "B"}}], "_links": {}})
        with patch("onboarding.services.confluence.httpx.get", side_effect=[p1, p2]):
            assert [s["key"] for s in _fetch_spaces("c1", "t")] == ["A", "B"]

    def test_failure(self):
        from onboarding.services.confluence import _fetch_spaces

        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(500, {})):
            with pytest.raises(HTTPException) as exc:
                _fetch_spaces("c1", "t")
            assert exc.value.status_code == 502

    def test_auth_failure_raises_401(self):
        from onboarding.services.confluence import _fetch_spaces

        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(401, {})):
            with pytest.raises(HTTPException) as exc:
                _fetch_spaces("c1", "t")
            assert exc.value.status_code == 401

class TestSearchPages:
    def test_single(self):
        from onboarding.services.confluence import _search_pages

        with patch(
            "onboarding.services.confluence.httpx.get",
            return_value=_resp(200, {"results": [_page()]}),
        ):
            assert _search_pages("c1", "t", "ENG")[0]["id"] == "p1"

    def test_paginates(self):
        from onboarding.services.confluence import _search_pages

        p1 = _resp(
            200, {"results": [_page("p1")], "_links": {"next": "/rest/api/content/search?c=1"}}
        )
        p2 = _resp(200, {"results": [_page("p2")], "_links": {}})
        with patch("onboarding.services.confluence.httpx.get", side_effect=[p1, p2]):
            assert [p["id"] for p in _search_pages("c1", "t", "ENG")] == ["p1", "p2"]

    def test_failure(self):
        from onboarding.services.confluence import _search_pages

        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(500, {})):
            with pytest.raises(HTTPException) as exc:
                _search_pages("c1", "t", "ENG")
            assert exc.value.status_code == 502

    def test_auth_failure_raises_401(self):
        from onboarding.services.confluence import _search_pages

        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(401, {})):
            with pytest.raises(HTTPException) as exc:
                _search_pages("c1", "t", "ENG")
            assert exc.value.status_code == 401

class TestFetchSinglePage:
    def test_found(self):
        from onboarding.services.confluence import _fetch_single_page

        with patch(
            "onboarding.services.confluence.httpx.get",
            return_value=_resp(200, {"results": [_page()]}),
        ):
            assert _fetch_single_page("c1", "t", "123")["id"] == "p1"

    def test_no_results(self):
        from onboarding.services.confluence import _fetch_single_page

        with patch(
            "onboarding.services.confluence.httpx.get", return_value=_resp(200, {"results": []})
        ):
            assert _fetch_single_page("c1", "t", "123") is None

    def test_failure(self):
        from onboarding.services.confluence import _fetch_single_page

        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(404, {})):
            assert _fetch_single_page("c1", "t", "123") is None

    def test_rejects_non_numeric_page_id(self):
        # A webhook-supplied page id must not be interpolated into CQL.
        from onboarding.services.confluence import _fetch_single_page

        with patch("onboarding.services.confluence.httpx.get") as get:
            assert _fetch_single_page("c1", "t", '1" or type=page') is None
            get.assert_not_called()

# ── Jira client ───────────────────────────────────────────────────────────────

def _issue(
    key="ENG-1",
    summary="Fix bug",
    project="ENG",
    description=None,
    comments=None,
    assignee=None,
    reporter=None,
    status=None,
):
    fields = {"summary": summary, "project": {"key": project}}
    if description is not None:
        fields["description"] = description
    if comments is not None:
        fields["comment"] = {"comments": comments}
    if assignee is not None:
        fields["assignee"] = {"displayName": assignee}
    if reporter is not None:
        fields["reporter"] = {"displayName": reporter}
    if status is not None:
        fields["status"] = {"name": status}
    return {"key": key, "fields": fields}

def _adf(text):
    """Minimal ADF doc wrapping a single text node."""
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }

class TestValidateSource:
    def test_ok(self):
        from onboarding.services.confluence import _validate_source

        assert _validate_source("jira") == "jira"

    def test_rejects_unknown(self):
        from onboarding.services.confluence import _validate_source

        with pytest.raises(HTTPException) as exc:
            _validate_source("slack")
        assert exc.value.status_code == 400

class TestSourceReaders:
    def test_confluence(self):
        from onboarding.services.confluence import (
            _source_readers,
            _fetch_spaces,
            _search_pages,
        )

        assert _source_readers("confluence") == (_fetch_spaces, _search_pages)

    def test_jira(self):
        from onboarding.services.confluence import (
            _source_readers,
            _fetch_projects,
            _search_issues,
        )

        assert _source_readers("jira") == (_fetch_projects, _search_issues)

class TestFetchProjects:
    def test_single(self):
        from onboarding.services.confluence import _fetch_projects

        with patch(
            "onboarding.services.confluence.httpx.get",
            return_value=_resp(200, {"values": [{"key": "ENG"}, {"id": "x"}], "isLast": True}),
        ):
            assert [p["key"] for p in _fetch_projects("c1", "t")] == ["ENG"]

    def test_paginates(self):
        from onboarding.services.confluence import _fetch_projects

        p1 = _resp(200, {"values": [{"key": "A"}], "isLast": False})
        p2 = _resp(200, {"values": [{"key": "B"}], "isLast": True})
        with patch("onboarding.services.confluence.httpx.get", side_effect=[p1, p2]):
            assert [p["key"] for p in _fetch_projects("c1", "t")] == ["A", "B"]

    def test_stops_on_empty(self):
        from onboarding.services.confluence import _fetch_projects

        with patch(
            "onboarding.services.confluence.httpx.get",
            return_value=_resp(200, {"values": []}),
        ):
            assert _fetch_projects("c1", "t") == []

    def test_auth_failure_raises_401(self):
        from onboarding.services.confluence import _fetch_projects

        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(403, {})):
            with pytest.raises(HTTPException) as exc:
                _fetch_projects("c1", "t")
            assert exc.value.status_code == 401

    def test_failure(self):
        from onboarding.services.confluence import _fetch_projects

        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(500, {})):
            with pytest.raises(HTTPException) as exc:
                _fetch_projects("c1", "t")
            assert exc.value.status_code == 502

class TestAdfToText:
    def test_none(self):
        from onboarding.services.confluence import _adf_to_text

        assert _adf_to_text(None) == ""

    def test_scalar(self):
        from onboarding.services.confluence import _adf_to_text

        assert _adf_to_text(5) == ""

    def test_nested(self):
        from onboarding.services.confluence import _adf_to_text

        assert _adf_to_text(_adf("hello there")) == "hello there"

class TestJiraIssueText:
    def test_assembles_key_summary_description_comments(self):
        from onboarding.services.confluence import _jira_issue_text

        fields = {
            "summary": "Login broken",
            "description": _adf("cannot sign in"),
            "comment": {
                "comments": [{"body": _adf("still failing"), "author": {"displayName": "Ana"}}]
            },
        }
        text = _jira_issue_text("ENG-1", fields)
        assert "Issue ENG-1" in text
        assert "Login broken" in text and "cannot sign in" in text
        assert "Ana: still failing" in text  # comment author prefixed

    def test_includes_people_status_and_labels(self):
        from onboarding.services.confluence import _jira_issue_text

        fields = {
            "summary": "Ship feature",
            "status": {"name": "In Progress"},
            "issuetype": {"name": "Task"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "Sunadh Kumar"},
            "reporter": {"displayName": "Yogesh"},
            "labels": ["backend", "urgent"],
        }
        text = _jira_issue_text("AR-2847", fields)
        assert "Assignee: Sunadh Kumar" in text
        assert "Reporter: Yogesh" in text
        assert "Status: In Progress" in text and "Type: Task" in text and "Priority: High" in text
        assert "Labels: backend, urgent" in text

    def test_empty(self):
        from onboarding.services.confluence import _jira_issue_text

        assert _jira_issue_text(None, {}) == ""

class TestNormalizeIssue:
    def test_shape(self):
        from onboarding.services.confluence import _normalize_issue

        issue = _issue(
            description=_adf("body text"),
            assignee="Sunadh P",
            reporter="Yogesh Kisslay",
            status="In Progress",
        )
        # Enrich with fields that flow into meta.
        issue["fields"].update(
            {
                "issuetype": {"name": "Bug"},
                "priority": {"name": "High"},
                "labels": ["backend"],
                "created": "2026-01-01T00:00:00.000+0000",
                "updated": "2026-02-01T00:00:00.000+0000",
                "resolution": {"name": "Done"},
                "status": {"name": "In Progress", "statusCategory": {"name": "In Progress"}},
            }
        )
        out = _normalize_issue(issue)
        assert out["id"] == "ENG-1"
        assert out["version"] is None
        assert out["space"]["key"] == "ENG"
        assert out["title"] == "Fix bug"
        assert "body text" in out["body"]["storage"]["value"]
        # Structured fields persisted to DocumentPage.
        assert out["assignee"] == "Sunadh P"
        assert out["reporter"] == "Yogesh Kisslay"
        assert out["status"] == "In Progress"
        # meta carries the future-proof extras.
        assert out["meta"]["issue_type"] == "Bug"
        assert out["meta"]["priority"] == "High"
        assert out["meta"]["labels"] == ["backend"]
        assert out["meta"]["resolution"] == "Done"
        assert out["meta"]["status_category"] == "In Progress"
        assert out["meta"]["created"].startswith("2026-01-01")

    def test_structured_fields_default_none(self):
        from onboarding.services.confluence import _normalize_issue

        out = _normalize_issue(_issue())
        assert out["assignee"] is None and out["reporter"] is None and out["status"] is None

    def test_falls_back_to_key_when_no_summary(self):
        from onboarding.services.confluence import _normalize_issue

        out = _normalize_issue({"key": "ENG-9", "fields": {"summary": None}})
        assert out["title"] == "ENG-9"

class TestConfluenceMeta:
    def test_extracts_author_breadcrumb_labels(self):
        from onboarding.services.confluence import _confluence_meta

        page = {
            "type": "page",
            "version": {"number": 3, "when": "2026-03-01T00:00:00Z", "by": {"displayName": "Ana"}},
            "history": {"createdBy": {"displayName": "Prajwal H N"}},
            "ancestors": [{"title": "PLUG"}, {"title": "Documentation"}],
            "metadata": {"labels": {"results": [{"name": "deploy"}, {"name": "infra"}]}},
        }
        meta = _confluence_meta(page)
        assert meta["type"] == "page"
        assert meta["author"] == "Prajwal H N"
        assert meta["last_editor"] == "Ana"
        assert meta["breadcrumb"] == ["PLUG", "Documentation"]
        assert meta["labels"] == ["deploy", "infra"]
        assert meta["updated"] == "2026-03-01T00:00:00Z"

    def test_blogpost_type_and_sparse(self):
        from onboarding.services.confluence import _confluence_meta

        assert _confluence_meta({"type": "blogpost"}) == {"type": "blogpost"}

    def test_empty_page_defaults_to_page_type(self):
        from onboarding.services.confluence import _confluence_meta

        assert _confluence_meta({}) == {"type": "page"}

class TestConfluenceTextPrefix:
    def test_all_fields(self):
        from onboarding.services.confluence import _confluence_text_prefix

        p = _confluence_text_prefix(
            {
                "author": "Yogesh Kisslay",
                "last_editor": "Ana",
                "breadcrumb": ["PLUG", "Docs"],
                "labels": ["infra"],
            }
        )
        assert "Author: Yogesh Kisslay" in p
        assert "Last edited by: Ana" in p
        assert "Path: PLUG > Docs" in p
        assert "Labels: infra" in p

    def test_editor_same_as_author_is_skipped(self):
        from onboarding.services.confluence import _confluence_text_prefix

        p = _confluence_text_prefix({"author": "A", "last_editor": "A"})
        assert "Author: A" in p and "Last edited by" not in p

    def test_empty(self):
        from onboarding.services.confluence import _confluence_text_prefix

        assert _confluence_text_prefix(None) == "" and _confluence_text_prefix({}) == ""

class TestSearchIssues:
    def test_single(self):
        from onboarding.services.confluence import _search_issues

        payload = {"issues": [_issue()], "isLast": True}
        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(200, payload)):
            out = _search_issues("c1", "t", "ENG")
        assert out[0]["id"] == "ENG-1" and out[0]["space"]["key"] == "ENG"

    def test_paginates_by_token(self):
        from onboarding.services.confluence import _search_issues

        p1 = _resp(200, {"issues": [_issue("ENG-1")], "nextPageToken": "tok2", "isLast": False})
        p2 = _resp(200, {"issues": [_issue("ENG-2")], "isLast": True})
        with patch("onboarding.services.confluence.httpx.get", side_effect=[p1, p2]) as get:
            assert [i["id"] for i in _search_issues("c1", "t", "ENG")] == ["ENG-1", "ENG-2"]
        # Second call must carry the pagination token from the first page.
        assert "nextPageToken=tok2" in get.call_args_list[1].args[0]

    def test_stops_when_no_token(self):
        from onboarding.services.confluence import _search_issues

        # No isLast flag and no nextPageToken → single page, then stop.
        payload = {"issues": [_issue("ENG-1")]}
        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(200, payload)):
            assert [i["id"] for i in _search_issues("c1", "t", "ENG")] == ["ENG-1"]

    def test_skips_keyless(self):
        from onboarding.services.confluence import _search_issues

        payload = {"issues": [{"fields": {}}], "isLast": True}
        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(200, payload)):
            assert _search_issues("c1", "t", "ENG") == []

    def test_auth_failure_raises_401(self):
        from onboarding.services.confluence import _search_issues

        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(401, {})):
            with pytest.raises(HTTPException) as exc:
                _search_issues("c1", "t", "ENG")
            assert exc.value.status_code == 401

    def test_failure(self):
        from onboarding.services.confluence import _search_issues

        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(500, {})):
            with pytest.raises(HTTPException) as exc:
                _search_issues("c1", "t", "ENG")
            assert exc.value.status_code == 502

# ── knowledge base persistence ──────────────────────────────────────────────────

class TestPersistence:
    def test_page_chunk_count(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.one.return_value = 3
            from onboarding.services.confluence import _page_chunk_count

            assert _page_chunk_count(1) == 3
        finally:
            patcher.stop()

    def test_upsert_page_new(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = None
            session.refresh.side_effect = lambda row: setattr(row, "id", 9)
            from onboarding.services.confluence import _upsert_page

            pid, changed, text = _upsert_page(1, _page())
            assert changed is True and text == "hello world"
            assert pid == 9
        finally:
            patcher.stop()

    def test_upsert_page_confluence_embeds_author(self):
        # A Confluence page with an author gets "Author: ..." prepended to its text,
        # so authorship becomes searchable like Jira's "Assignee:".
        page = _page(pid="p9", body="<p>hello</p>")
        page["history"] = {"createdBy": {"displayName": "Yogesh Kisslay"}}
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = None
            session.refresh.side_effect = lambda row: setattr(row, "id", 9)
            from onboarding.services.confluence import _upsert_page

            _, _, text = _upsert_page(1, page, source="confluence")
            assert text.startswith("Author: Yogesh Kisslay")
            assert "hello" in text
        finally:
            patcher.stop()

    def test_upsert_page_unchanged(self):
        existing = DocumentPage(
            id=5,
            company_id=1,
            confluence_page_id="p1",
            title="Arch",
            version=1,
            is_active=True,
            content_text="hello world",  # matches _page()'s stripped body → no re-embed
        )
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = existing
            session.refresh.side_effect = lambda row: None
            from onboarding.services.confluence import _upsert_page

            pid, changed, text = _upsert_page(1, _page(version=1))
            assert changed is False and pid == 5
        finally:
            patcher.stop()

    def test_upsert_page_changed_version(self):
        existing = DocumentPage(
            id=5, company_id=1, confluence_page_id="p1", title="Arch", version=1, is_active=True
        )
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = existing
            session.refresh.side_effect = lambda row: None
            from onboarding.services.confluence import _upsert_page

            _, changed, _t = _upsert_page(1, _page(version=2))
            assert changed is True
        finally:
            patcher.stop()

    def test_upsert_page_changed_content_same_version(self):
        # Same version but different text (the Jira edit case: version is None on
        # both sides, so content comparison is what flags a re-embed).
        existing = DocumentPage(
            id=5,
            company_id=1,
            source="jira",
            confluence_page_id="ENG-1",
            title="Old",
            version=None,
            is_active=True,
            content_text="old text",
        )
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = existing
            session.refresh.side_effect = lambda row: None
            from onboarding.services.confluence import _upsert_page

            _, changed, _t = _upsert_page(
                1, _page(version=None, body="<p>new text</p>"), source="jira"
            )
            assert changed is True
        finally:
            patcher.stop()

    def test_delete_chunks(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = [MagicMock(), MagicMock()]
            from onboarding.services.confluence import _delete_chunks

            _delete_chunks(1)
            assert session.delete.call_count == 2
        finally:
            patcher.stop()

    def test_store_chunks(self):
        patcher, session = _patch_session()
        try:
            from onboarding.services.confluence import _store_chunks

            _store_chunks(1, 2, ["a", "b"], [[0.1], [0.2]])
            assert session.add.call_count == 2
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_embed_page_with_chunks(self):
        with (
            patch("onboarding.services.confluence.chunk_text", return_value=["a", "b"]),
            patch(
                "onboarding.services.confluence.embedding_service.embed_texts",
                return_value=[[0.1], [0.2]],
            ),
            patch("onboarding.services.confluence._delete_chunks") as dele,
            patch("onboarding.services.confluence._store_chunks") as store,
        ):
            from onboarding.services.confluence import _embed_page

            assert _embed_page(1, 2, "text") == 2
            dele.assert_called_once()
            store.assert_called_once()

    def test_embed_page_no_chunks(self):
        with (
            patch("onboarding.services.confluence.chunk_text", return_value=[]),
            patch("onboarding.services.confluence._delete_chunks") as dele,
        ):
            from onboarding.services.confluence import _embed_page

            assert _embed_page(1, 2, "") == 0
            dele.assert_called_once()

    def test_counts(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.one.side_effect = [12, 340]
            from onboarding.services.confluence import _counts

            assert _counts(1) == (12, 340)
        finally:
            patcher.stop()

    def test_counts_scoped_to_source(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.one.side_effect = [3, 40]
            from onboarding.services.confluence import _counts

            assert _counts(1, source="jira") == (3, 40)
        finally:
            patcher.stop()

# ── ingestion job ────────────────────────────────────────────────────────────────

class TestIngestionJob:
    def test_create_job(self):
        patcher, session = _patch_session()
        try:
            session.refresh.side_effect = lambda job: setattr(job, "id", 7)
            from onboarding.services.confluence import _create_job

            assert _create_job(1) == 7
        finally:
            patcher.stop()

    def test_reap_running_jobs(self):
        stuck = IngestionJob(id=1, company_id=1, status="running")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = [stuck]
            from onboarding.services.confluence import reap_running_jobs

            assert reap_running_jobs() == 1
            assert stuck.status == "failed" and stuck.phase == "failed"
        finally:
            patcher.stop()

    def test_update_job(self):
        job = IngestionJob(id=1, company_id=1, status="running")
        patcher, session = _patch_session()
        try:
            session.get.return_value = job
            from onboarding.services.confluence import _update_job

            _update_job(
                1,
                phase="embedding",
                total_spaces=3,
                processed_spaces=2,
                total_pages=5,
                processed_pages=5,
                total_chunks=10,
                embedded_chunks=10,
                status="done",
                error="e",
                completed=True,
            )
            assert job.status == "done" and job.total_chunks == 10 and job.error == "e"
            assert job.phase == "embedding" and job.total_spaces == 3 and job.processed_spaces == 2
            assert job.completed_at is not None
        finally:
            patcher.stop()

    def test_update_job_missing(self):
        patcher, session = _patch_session()
        try:
            session.get.return_value = None
            from onboarding.services.confluence import _update_job

            _update_job(9, status="x")
            session.commit.assert_not_called()
        finally:
            patcher.stop()

class TestBeginIngest:
    def test_not_connected(self):
        with (
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch(
                "onboarding.services.confluence._require_ready_connection",
                side_effect=HTTPException(status_code=409, detail="x"),
            ),
        ):
            from onboarding.services.confluence import begin_ingest

            with pytest.raises(HTTPException) as exc:
                begin_ingest(_user(), MagicMock())
            assert exc.value.status_code == 409

    def test_schedules(self):
        bg = MagicMock()
        with (
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch("onboarding.services.confluence._require_ready_connection", return_value=_conn()),
            patch("onboarding.services.confluence._running_job", return_value=None),
            patch("onboarding.services.confluence._create_job", return_value=7),
        ):
            from onboarding.services.confluence import begin_ingest, _run_ingest

            assert begin_ingest(_user(), bg) == {
                "job_id": 7,
                "status": "running",
                "kind": "ingest",
                "source": "confluence",
            }
            bg.add_task.assert_called_once_with(_run_ingest, 1, 7, "confluence")

    def test_returns_existing_running_job(self):
        bg = MagicMock()
        with (
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch("onboarding.services.confluence._require_ready_connection", return_value=_conn()),
            patch(
                "onboarding.services.confluence._running_job",
                return_value=IngestionJob(
                    id=42, company_id=1, status="running", kind="ingest", source="confluence"
                ),
            ),
            patch("onboarding.services.confluence._create_job") as create,
        ):
            from onboarding.services.confluence import begin_ingest

            assert begin_ingest(_user(), bg) == {
                "job_id": 42,
                "status": "running",
                "kind": "ingest",
                "source": "confluence",
            }
            create.assert_not_called()
            bg.add_task.assert_not_called()

    def test_create_race_returns_winning_job(self):
        # Two concurrent requests both pass the _running_job check; the DB partial
        # unique index rejects the second _create_job with IntegrityError, and we
        # return the job that won instead of starting a duplicate.
        bg = MagicMock()
        winner = IngestionJob(
            id=99, company_id=1, status="running", kind="ingest", source="confluence"
        )
        with (
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch("onboarding.services.confluence._require_ready_connection", return_value=_conn()),
            # first call (pre-check) sees nothing; second (in except) sees the winner
            patch("onboarding.services.confluence._running_job", side_effect=[None, winner]),
            patch(
                "onboarding.services.confluence._create_job",
                side_effect=IntegrityError("insert", {}, Exception()),
            ),
        ):
            from onboarding.services.confluence import begin_ingest

            assert begin_ingest(_user(), bg) == {
                "job_id": 99,
                "status": "running",
                "kind": "ingest",
                "source": "confluence",
            }
            bg.add_task.assert_not_called()

    def test_running_job_query(self):
        job = IngestionJob(id=5, company_id=1, status="running")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = job
            from onboarding.services.confluence import _running_job

            assert _running_job(1) is job
        finally:
            patcher.stop()

    def test_latest_finished_job_query(self):
        job = IngestionJob(id=5, company_id=1, status="done")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = job
            from onboarding.services.confluence import _latest_finished_job

            assert _latest_finished_job(1) is job
        finally:
            patcher.stop()

class TestRunIngest:
    @pytest.fixture(autouse=True)
    def _neutralize_db_helpers(self):
        # These existing tests mock every collaborator but run against no real DB, so
        # neutralize the two DB-touching helpers added for cancel + deletion sweep:
        # never cancelled, sweep is a no-op. Sweep + cancel behavior is covered in
        # TestIngestSweep / TestCancelIngest below with proper session mocks.
        with (
            patch("onboarding.services.confluence._is_cancelled", return_value=False),
            patch("onboarding.services.confluence._sweep_deleted", return_value=0),
        ):
            yield

    def test_success(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch(
                "onboarding.services.confluence._fetch_spaces", return_value=[{"key": "ENG"}, {}]
            ),
            patch("onboarding.services.confluence._search_pages", return_value=[_page("p1")]),
            patch(
                "onboarding.services.confluence._upsert_page",
                return_value=(1, True, "hello world text"),
            ),
            patch("onboarding.services.confluence._page_chunk_count", return_value=0),
            patch("onboarding.services.confluence.chunk_text", return_value=["c1", "c2"]),
            patch(
                "onboarding.services.confluence.embedding_service.embed_texts",
                return_value=[[0.1], [0.2]],
            ),
            patch("onboarding.services.confluence._delete_chunks"),
            patch("onboarding.services.confluence._store_chunks") as store,
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            store.assert_called_once()
            assert any(c.kwargs.get("status") == "done" for c in upd.call_args_list)

    def test_skips_unchanged_with_chunks(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "ENG"}]),
            patch("onboarding.services.confluence._search_pages", return_value=[_page("p1")]),
            patch("onboarding.services.confluence._upsert_page", return_value=(1, False, "text")),
            patch("onboarding.services.confluence._page_chunk_count", return_value=3),
            patch("onboarding.services.confluence.embedding_service.embed_texts") as embed,
            patch("onboarding.services.confluence._update_job"),
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            embed.assert_not_called()

    def test_embed_skips_page_that_chunks_to_nothing(self):
        # A page flagged for embedding whose text chunks to [] is skipped (no embed,
        # not counted as failed) — the whole run still completes "done".
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "ENG"}]),
            patch("onboarding.services.confluence._search_pages", return_value=[_page("p1")]),
            patch("onboarding.services.confluence._upsert_page", return_value=(1, True, "text")),
            patch("onboarding.services.confluence._page_chunk_count", return_value=0),
            patch("onboarding.services.confluence.chunk_text", return_value=[]),
            patch("onboarding.services.confluence.embedding_service.embed_texts") as embed,
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            embed.assert_not_called()
            assert any(c.kwargs.get("status") == "done" for c in upd.call_args_list)

    def test_no_connection_failed(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=None),
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
        assert upd.call_args_list[-1].kwargs.get("status") == "failed"

    def test_search_failure_failed(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch(
                "onboarding.services.confluence._fetch_spaces",
                side_effect=HTTPException(status_code=502, detail="boom"),
            ),
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
        last = upd.call_args_list[-1].kwargs
        assert last.get("status") == "failed" and "boom" in (last.get("error") or "")

    def test_skips_page_without_id(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "ENG"}]),
            patch(
                "onboarding.services.confluence._search_pages",
                return_value=[{"no": "id"}, _page("100")],
            ),
            patch(
                "onboarding.services.confluence._upsert_page", return_value=(1, True, "text")
            ) as ups,
            patch("onboarding.services.confluence._page_chunk_count", return_value=0),
            patch("onboarding.services.confluence.chunk_text", return_value=["c1"]),
            patch(
                "onboarding.services.confluence.embedding_service.embed_texts", return_value=[[0.1]]
            ),
            patch("onboarding.services.confluence._delete_chunks"),
            patch("onboarding.services.confluence._store_chunks"),
            patch("onboarding.services.confluence._update_job"),
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            ups.assert_called_once()  # only the page that has an id is upserted

    def test_jira_ingest_refreshes_name_cache(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._fetch_projects", return_value=[{"key": "AR"}]),
            patch(
                "onboarding.services.confluence._search_issues",
                return_value=[{"id": "AR-1", "assignee": "Sunadh P"}],
            ),
            patch("onboarding.services.confluence._upsert_page", return_value=(1, True, "text")),
            patch("onboarding.services.confluence._page_chunk_count", return_value=0),
            patch("onboarding.services.confluence.chunk_text", return_value=["c1"]),
            patch(
                "onboarding.services.confluence.embedding_service.embed_texts", return_value=[[0.1]]
            ),
            patch("onboarding.services.confluence._delete_chunks"),
            patch("onboarding.services.confluence._store_chunks"),
            patch("onboarding.services.confluence._update_job"),
            patch("onboarding.services.confluence.retrieval_service.refresh_names") as refresh,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7, source="jira")
            refresh.assert_called_once_with(1)

    def test_confluence_ingest_does_not_refresh_names(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "ENG"}]),
            patch("onboarding.services.confluence._search_pages", return_value=[_page("100")]),
            patch("onboarding.services.confluence._upsert_page", return_value=(1, True, "text")),
            patch("onboarding.services.confluence._page_chunk_count", return_value=0),
            patch("onboarding.services.confluence.chunk_text", return_value=["c1"]),
            patch(
                "onboarding.services.confluence.embedding_service.embed_texts", return_value=[[0.1]]
            ),
            patch("onboarding.services.confluence._delete_chunks"),
            patch("onboarding.services.confluence._store_chunks"),
            patch("onboarding.services.confluence._update_job"),
            patch("onboarding.services.confluence.retrieval_service.refresh_names") as refresh,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7, source="confluence")
            refresh.assert_not_called()  # names come from Jira only

    def test_embed_failure_marks_failed(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "ENG"}]),
            patch("onboarding.services.confluence._search_pages", return_value=[_page("100")]),
            patch("onboarding.services.confluence._upsert_page", return_value=(1, True, "text")),
            patch("onboarding.services.confluence._page_chunk_count", return_value=0),
            patch("onboarding.services.confluence.chunk_text", return_value=["c1"]),
            patch(
                "onboarding.services.confluence.embedding_service.embed_texts",
                side_effect=RuntimeError("model down"),
            ),
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            last = upd.call_args_list[-1].kwargs
            assert last.get("status") == "failed" and last.get("phase") == "failed"

    def test_skips_space_on_generic_error(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch(
                "onboarding.services.confluence._fetch_spaces",
                return_value=[{"key": "A"}, {"key": "B"}],
            ),
            patch(
                "onboarding.services.confluence._search_pages",
                side_effect=[RuntimeError("blip"), [_page("100")]],
            ),
            patch("onboarding.services.confluence._upsert_page", return_value=(1, True, "text")),
            patch("onboarding.services.confluence._page_chunk_count", return_value=0),
            patch("onboarding.services.confluence.chunk_text", return_value=["c1"]),
            patch(
                "onboarding.services.confluence.embedding_service.embed_texts", return_value=[[0.1]]
            ),
            patch("onboarding.services.confluence._delete_chunks"),
            patch("onboarding.services.confluence._store_chunks"),
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            done = [c for c in upd.call_args_list if c.kwargs.get("status") == "done"]
            assert done and "space(s) skipped" in (done[-1].kwargs.get("error") or "")

    def test_auth_failure_fails_job_not_silent_skip(self):
        # A 401 mid-read (token died) must fail the job, not skip every space and
        # report a green "done" with an empty index.
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch(
                "onboarding.services.confluence._fetch_spaces",
                return_value=[{"key": "A"}, {"key": "B"}],
            ),
            patch(
                "onboarding.services.confluence._search_pages",
                side_effect=HTTPException(status_code=401, detail="expired"),
            ),
            patch("onboarding.services.confluence._mark_status") as mark,
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            assert upd.call_args_list[-1].kwargs.get("status") == "failed"
            mark.assert_called_once_with(1, "error")

    def test_batches_embeds_across_pages(self):
        # With a batch size of 1 chunk, each page's chunk triggers its own flush —
        # verifies cross-page batching stores each page and reports embedded counts.
        with (
            patch("onboarding.services.confluence._EMBED_BATCH_SIZE", 1),
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "ENG"}]),
            patch(
                "onboarding.services.confluence._search_pages",
                return_value=[_page("100"), _page("200")],
            ),
            patch(
                "onboarding.services.confluence._upsert_page",
                side_effect=[(1, True, "one"), (2, True, "two")],
            ),
            patch("onboarding.services.confluence._page_chunk_count", return_value=0),
            patch("onboarding.services.confluence.chunk_text", return_value=["c1"]),
            patch(
                "onboarding.services.confluence.embedding_service.embed_texts", return_value=[[0.1]]
            ) as embed,
            patch("onboarding.services.confluence._delete_chunks"),
            patch("onboarding.services.confluence._store_chunks") as store,
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            assert embed.call_count == 2  # one batch per page (batch size 1)
            assert store.call_count == 2
            assert any(c.kwargs.get("status") == "done" for c in upd.call_args_list)

    def test_space_read_failure_is_skipped_not_fatal(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch(
                "onboarding.services.confluence._fetch_spaces",
                return_value=[{"key": "A"}, {"key": "B"}],
            ),
            patch(
                "onboarding.services.confluence._search_pages",
                side_effect=[HTTPException(status_code=502, detail="blip"), [_page("100")]],
            ),
            patch("onboarding.services.confluence._upsert_page", return_value=(1, True, "text")),
            patch("onboarding.services.confluence._page_chunk_count", return_value=0),
            patch("onboarding.services.confluence.chunk_text", return_value=["c1"]),
            patch(
                "onboarding.services.confluence.embedding_service.embed_texts", return_value=[[0.1]]
            ),
            patch("onboarding.services.confluence._delete_chunks"),
            patch("onboarding.services.confluence._store_chunks"),
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            done = [c for c in upd.call_args_list if c.kwargs.get("status") == "done"]
            assert done and "space" in (done[-1].kwargs.get("error") or "")

    def test_page_index_failure_is_skipped_not_fatal(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "A"}]),
            patch(
                "onboarding.services.confluence._search_pages",
                return_value=[_page("100"), _page("200")],
            ),
            patch(
                "onboarding.services.confluence._upsert_page",
                side_effect=[RuntimeError("db blip"), (2, True, "text")],
            ),
            patch("onboarding.services.confluence._page_chunk_count", return_value=0),
            patch("onboarding.services.confluence.chunk_text", return_value=["c1"]),
            patch(
                "onboarding.services.confluence.embedding_service.embed_texts", return_value=[[0.1]]
            ),
            patch("onboarding.services.confluence._delete_chunks"),
            patch("onboarding.services.confluence._store_chunks"),
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            done = [c for c in upd.call_args_list if c.kwargs.get("status") == "done"]
            assert done and "page" in (done[-1].kwargs.get("error") or "")

    def test_partial_embed_batch_is_skipped_not_fatal(self):
        with (
            patch("onboarding.services.confluence._EMBED_BATCH_SIZE", 1),
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "A"}]),
            patch(
                "onboarding.services.confluence._search_pages",
                return_value=[_page("100"), _page("200")],
            ),
            patch(
                "onboarding.services.confluence._upsert_page",
                side_effect=[(1, True, "one"), (2, True, "two")],
            ),
            patch("onboarding.services.confluence._page_chunk_count", return_value=0),
            patch("onboarding.services.confluence.chunk_text", return_value=["c1"]),
            patch(
                "onboarding.services.confluence.embedding_service.embed_texts",
                side_effect=[RuntimeError("blip"), [[0.1]]],
            ),
            patch("onboarding.services.confluence._delete_chunks"),
            patch("onboarding.services.confluence._store_chunks") as store,
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            store.assert_called_once()  # only the batch that embedded is stored
            done = [c for c in upd.call_args_list if c.kwargs.get("status") == "done"]
            assert done and "chunk" in (done[-1].kwargs.get("error") or "")

class TestSweepDeleted:
    def _pg(self, pid, space="ENG", active=True):
        p = MagicMock()
        p.confluence_page_id = pid
        p.space_key = space
        p.is_active = active
        return p

    def test_deactivates_page_missing_upstream(self):
        seen, gone = self._pg("p1"), self._pg("p2")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = [seen, gone]
            from onboarding.services.confluence import _sweep_deleted

            n = _sweep_deleted(1, "confluence", live_ids={"p1"}, skipped_keys=set())
            assert n == 1
            assert seen.is_active is True
            assert gone.is_active is False
        finally:
            patcher.stop()

    def test_protects_pages_in_skipped_container(self):
        gone = self._pg("p2", space="OPS")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = [gone]
            from onboarding.services.confluence import _sweep_deleted

            # OPS failed to read this run — a transient error must not look like a delete.
            n = _sweep_deleted(1, "confluence", live_ids=set(), skipped_keys={"OPS"})
            assert n == 0
            assert gone.is_active is True
        finally:
            patcher.stop()

class TestIsCancelled:
    def test_true_when_status_cancelled(self):
        job = MagicMock()
        job.status = "cancelled"
        patcher, session = _patch_session()
        try:
            session.get.return_value = job
            from onboarding.services.confluence import _is_cancelled

            assert _is_cancelled(7) is True
        finally:
            patcher.stop()

    def test_false_when_running_or_missing(self):
        patcher, session = _patch_session()
        try:
            from onboarding.services.confluence import _is_cancelled

            session.get.return_value = None
            assert _is_cancelled(7) is False
            job = MagicMock()
            job.status = "running"
            session.get.return_value = job
            assert _is_cancelled(7) is False
        finally:
            patcher.stop()

class TestIngestSweep:
    def test_sweep_called_after_full_read(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._update_job"),
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "ENG"}]),
            patch("onboarding.services.confluence._search_pages", return_value=[_page("p1")]),
            patch("onboarding.services.confluence._upsert_page", return_value=(1, True, "text")),
            patch("onboarding.services.confluence._page_chunk_count", return_value=0),
            patch("onboarding.services.confluence.chunk_text", return_value=["c1"]),
            patch(
                "onboarding.services.confluence.embedding_service.embed_texts",
                return_value=[[0.1]],
            ),
            patch("onboarding.services.confluence._delete_chunks"),
            patch("onboarding.services.confluence._store_chunks"),
            patch("onboarding.services.confluence._is_cancelled", return_value=False),
            patch("onboarding.services.confluence._sweep_deleted", return_value=0) as sweep,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            sweep.assert_called_once()
            # signature: (company_id, source, live_ids, skipped_keys)
            args = sweep.call_args.args
            assert "p1" in args[2]
            assert args[3] == set()

    def test_sweep_skipped_when_container_read_fails(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._update_job"),
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "ENG"}]),
            patch(
                "onboarding.services.confluence._search_pages",
                side_effect=RuntimeError("boom"),
            ),
            patch("onboarding.services.confluence._is_cancelled", return_value=False),
            patch("onboarding.services.confluence._sweep_deleted", return_value=0) as sweep,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            sweep.assert_not_called()  # the only container was skipped — nothing reliably read

    def test_cancel_before_read_skips_sweep(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "ENG"}]),
            patch("onboarding.services.confluence._search_pages", return_value=[_page("p1")]),
            patch("onboarding.services.confluence._update_job") as upd,
            patch("onboarding.services.confluence._is_cancelled", return_value=True),
            patch("onboarding.services.confluence._sweep_deleted", return_value=0) as sweep,
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            sweep.assert_not_called()
            assert any(c.kwargs.get("status") == "cancelled" for c in upd.call_args_list)

    def test_cancel_during_embedding_stops_and_skips_store(self):
        # Not cancelled during the read (sweep runs), then cancelled at the first embed
        # batch — it must stop without storing that batch and mark the job cancelled.
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._update_job") as upd,
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "ENG"}]),
            patch("onboarding.services.confluence._search_pages", return_value=[_page("p1")]),
            patch("onboarding.services.confluence._upsert_page", return_value=(1, True, "text")),
            patch("onboarding.services.confluence._page_chunk_count", return_value=0),
            patch("onboarding.services.confluence.chunk_text", return_value=["c1"]),
            patch("onboarding.services.confluence._delete_chunks"),
            patch("onboarding.services.confluence._store_chunks") as store,
            patch("onboarding.services.confluence._EMBED_BATCH_SIZE", 1),
            patch("onboarding.services.confluence._is_cancelled", side_effect=[False, True]),
            patch("onboarding.services.confluence._sweep_deleted", return_value=0),
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            store.assert_not_called()
            assert any(c.kwargs.get("status") == "cancelled" for c in upd.call_args_list)

    def test_done_note_reports_removed_count(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._update_job") as upd,
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "ENG"}]),
            patch("onboarding.services.confluence._search_pages", return_value=[_page("p1")]),
            patch("onboarding.services.confluence._upsert_page", return_value=(1, True, "text")),
            patch("onboarding.services.confluence._page_chunk_count", return_value=0),
            patch("onboarding.services.confluence.chunk_text", return_value=["c1"]),
            patch(
                "onboarding.services.confluence.embedding_service.embed_texts",
                return_value=[[0.1]],
            ),
            patch("onboarding.services.confluence._delete_chunks"),
            patch("onboarding.services.confluence._store_chunks"),
            patch("onboarding.services.confluence._is_cancelled", return_value=False),
            patch("onboarding.services.confluence._sweep_deleted", return_value=3),
        ):
            from onboarding.services.confluence import _run_ingest

            _run_ingest(1, 7)
            done = [c for c in upd.call_args_list if c.kwargs.get("status") == "done"]
            assert done and "3 removed" in (done[-1].kwargs.get("error") or "")

class TestCancelIngest:
    def _job(self, company_id=1, status="running"):
        j = MagicMock()
        j.id = 7
        j.company_id = company_id
        j.status = status
        j.kind = "ingest"
        j.source = "confluence"
        j.phase = "reading"
        j.total_spaces = j.processed_spaces = 0
        j.total_pages = j.processed_pages = 0
        j.total_chunks = j.embedded_chunks = 0
        j.error = None
        return j

    def test_cancels_running_job(self):
        company = MagicMock()
        company.id = 1
        job = self._job()
        patcher, session = _patch_session()
        try:
            session.get.return_value = job
            with patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=company,
            ):
                from onboarding.services.confluence import cancel_ingest

                result = cancel_ingest(user=MagicMock(), job_id=7)
            assert job.status == "cancelled"
            assert result["status"] == "cancelled"
        finally:
            patcher.stop()

    def test_wrong_company_404(self):
        company = MagicMock()
        company.id = 1
        job = self._job(company_id=2)
        patcher, session = _patch_session()
        try:
            session.get.return_value = job
            with patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=company,
            ):
                from onboarding.services.confluence import cancel_ingest

                with pytest.raises(HTTPException) as ei:
                    cancel_ingest(user=MagicMock(), job_id=7)
                assert ei.value.status_code == 404
        finally:
            patcher.stop()

    def test_idempotent_on_finished_job(self):
        company = MagicMock()
        company.id = 1
        job = self._job(status="done")
        patcher, session = _patch_session()
        try:
            session.get.return_value = job
            with patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=company,
            ):
                from onboarding.services.confluence import cancel_ingest

                result = cancel_ingest(user=MagicMock(), job_id=7)
            assert job.status == "done"  # a finished job is left unchanged
            assert result["status"] == "done"
        finally:
            patcher.stop()

class TestIngestStatus:
    def test_found(self):
        job = IngestionJob(
            id=7,
            company_id=1,
            status="running",
            total_pages=10,
            processed_pages=4,
            total_chunks=20,
            embedded_chunks=8,
        )
        with patch(
            "onboarding.services.confluence.get_or_create_company_for_user",
            return_value=Company(id=1, name="a", domain="a"),
        ):
            patcher, session = _patch_session()
            try:
                session.get.return_value = job
                from onboarding.services.confluence import get_ingest_status

                out = get_ingest_status(_user(), 7)
                assert out["embedded_chunks"] == 8 and out["status"] == "running"
            finally:
                patcher.stop()

    def test_wrong_company(self):
        job = IngestionJob(id=7, company_id=999, status="running")
        with patch(
            "onboarding.services.confluence.get_or_create_company_for_user",
            return_value=Company(id=1, name="a", domain="a"),
        ):
            patcher, session = _patch_session()
            try:
                session.get.return_value = job
                from onboarding.services.confluence import get_ingest_status

                with pytest.raises(HTTPException) as exc:
                    get_ingest_status(_user(), 7)
                assert exc.value.status_code == 404
            finally:
                patcher.stop()

# ── webhooks ──────────────────────────────────────────────────────────────────

class TestWebhookSecret:
    def test_not_configured(self):
        from onboarding.services.confluence import verify_webhook_secret

        with patch("config.CONFLUENCE_WEBHOOK_SECRET", None):
            with pytest.raises(HTTPException) as exc:
                verify_webhook_secret("x")
            assert exc.value.status_code == 503

    def test_mismatch(self):
        from onboarding.services.confluence import verify_webhook_secret

        with patch("config.CONFLUENCE_WEBHOOK_SECRET", "right"):
            with pytest.raises(HTTPException) as exc:
                verify_webhook_secret("wrong")
            assert exc.value.status_code == 401

    def test_ok(self):
        from onboarding.services.confluence import verify_webhook_secret

        with patch("config.CONFLUENCE_WEBHOOK_SECRET", "right"):
            verify_webhook_secret("right")

class TestWebhookHelpers:
    def test_pages_by_page_id(self):
        page = DocumentPage(id=1, company_id=1, confluence_page_id="p1", title="t")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = [page]
            from onboarding.services.confluence import _pages_by_page_id

            assert _pages_by_page_id("p1") == [page]
        finally:
            patcher.stop()

    def test_pages_by_page_id_scoped_to_company(self):
        page = DocumentPage(id=1, company_id=42, confluence_page_id="p1", title="t")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = [page]
            from onboarding.services.confluence import _pages_by_page_id

            assert _pages_by_page_id("p1", 42) == [page]
        finally:
            patcher.stop()

    def test_connection_by_cloud_id(self):
        conn = _conn()
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = conn
            from onboarding.services.confluence import _connection_by_cloud_id

            assert _connection_by_cloud_id("c1") is conn
        finally:
            patcher.stop()

    def test_deactivate_pages(self):
        page = DocumentPage(id=1, company_id=1, confluence_page_id="p1", title="t", is_active=True)
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = [page]
            from onboarding.services.confluence import _deactivate_pages

            assert _deactivate_pages("p1") == 1
            assert page.is_active is False
        finally:
            patcher.stop()

    def test_deactivate_pages_scoped_to_company(self):
        page = DocumentPage(id=1, company_id=42, confluence_page_id="p1", title="t", is_active=True)
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = [page]
            from onboarding.services.confluence import _deactivate_pages

            assert _deactivate_pages("p1", 42) == 1
            assert page.is_active is False
        finally:
            patcher.stop()

    def test_deactivate_pages_scoped_to_source(self):
        page = DocumentPage(
            id=1, company_id=42, source="jira", confluence_page_id="AR-1", title="t", is_active=True
        )
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = [page]
            from onboarding.services.confluence import _deactivate_pages

            assert _deactivate_pages("AR-1", 42, source="jira") == 1
            assert page.is_active is False
        finally:
            patcher.stop()

    def test_reindex_page_found(self):
        with (
            patch("onboarding.services.confluence._fetch_single_page", return_value=_page()),
            patch("onboarding.services.confluence._upsert_page", return_value=(1, True, "text")),
            patch("onboarding.services.confluence._embed_page") as embed,
        ):
            from onboarding.services.confluence import _reindex_page

            assert _reindex_page(1, "c1", "t", "p1") is True
            embed.assert_called_once()

    def test_reindex_page_unreadable(self):
        with patch("onboarding.services.confluence._fetch_single_page", return_value=None):
            from onboarding.services.confluence import _reindex_page

            assert _reindex_page(1, "c1", "t", "p1") is False

class TestHandleWebhook:
    def test_unknown_ignored(self):
        from onboarding.services.confluence import handle_webhook

        assert handle_webhook({"event": "label_added"})["status"] == "ignored"

    def test_never_raises_on_internal_error(self):
        # A failure (e.g. embed model can't load) must return, not 500-storm Atlassian.
        from onboarding.services.confluence import handle_webhook

        with patch(
            "onboarding.services.confluence._connection_by_cloud_id",
            side_effect=RuntimeError("model down"),
        ):
            assert handle_webhook({"event": "page_created", "cloudId": "c1"})["status"] == "error"

    def test_updated_no_page(self):
        from onboarding.services.confluence import handle_webhook

        assert handle_webhook({"event": "page_updated"})["status"] == "ignored"

    def test_removed_no_page(self):
        from onboarding.services.confluence import handle_webhook

        assert handle_webhook({"event": "page_removed"})["status"] == "ignored"

    def test_updated_dispatch(self):
        from onboarding.services.confluence import handle_webhook

        with patch(
            "onboarding.services.confluence._handle_page_updated",
            return_value={"status": "updated"},
        ) as h:
            handle_webhook({"event": "page_updated", "page": {"id": "p1"}})
            h.assert_called_once_with("p1", None)

    def test_removed_dispatch(self):
        from onboarding.services.confluence import handle_webhook

        with patch(
            "onboarding.services.confluence._handle_page_removed",
            return_value={"status": "removed"},
        ) as h:
            handle_webhook({"event": "page_trashed", "page": {"id": "p1"}})
            h.assert_called_once_with("p1", None)

    def test_created_dispatch(self):
        from onboarding.services.confluence import handle_webhook

        with (
            patch(
                "onboarding.services.confluence._connection_by_cloud_id",
                return_value=_conn(company_id=1),
            ),
            patch(
                "onboarding.services.confluence._handle_page_created",
                return_value={"status": "added"},
            ) as h,
        ):
            handle_webhook({"event": "page_created", "page": {"id": "p1"}, "cloudId": "c1"})
            h.assert_called_once()

    def test_update_scoped_to_company_by_cloud_id(self):
        from onboarding.services.confluence import handle_webhook

        with (
            patch(
                "onboarding.services.confluence._connection_by_cloud_id",
                return_value=_conn(company_id=42),
            ),
            patch(
                "onboarding.services.confluence._handle_page_updated",
                return_value={"status": "updated"},
            ) as h,
        ):
            handle_webhook({"event": "page_updated", "page": {"id": "p1"}, "cloudId": "c1"})
            h.assert_called_once_with("p1", 42)

    def test_remove_scoped_to_company_by_cloud_id(self):
        from onboarding.services.confluence import handle_webhook

        with (
            patch(
                "onboarding.services.confluence._connection_by_cloud_id",
                return_value=_conn(company_id=42),
            ),
            patch(
                "onboarding.services.confluence._handle_page_removed",
                return_value={"status": "removed"},
            ) as h,
        ):
            handle_webhook({"event": "page_removed", "page": {"id": "p1"}, "cloudId": "c1"})
            h.assert_called_once_with("p1", 42)

    def test_unknown_cloud_id_ignored(self):
        from onboarding.services.confluence import handle_webhook

        with patch("onboarding.services.confluence._connection_by_cloud_id", return_value=None):
            out = handle_webhook({"event": "page_updated", "page": {"id": "p1"}, "cloudId": "nope"})
            assert out["status"] == "ignored"

class TestJiraWebhookSecret:
    def test_not_configured(self):
        from onboarding.services.confluence import verify_jira_webhook_secret

        with patch("config.JIRA_WEBHOOK_SECRET", None):
            with pytest.raises(HTTPException) as exc:
                verify_jira_webhook_secret("x")
            assert exc.value.status_code == 503

    def test_mismatch(self):
        from onboarding.services.confluence import verify_jira_webhook_secret

        with patch("config.JIRA_WEBHOOK_SECRET", "right"):
            with pytest.raises(HTTPException) as exc:
                verify_jira_webhook_secret("wrong")
            assert exc.value.status_code == 401

    def test_ok(self):
        from onboarding.services.confluence import verify_jira_webhook_secret

        with patch("config.JIRA_WEBHOOK_SECRET", "right"):
            verify_jira_webhook_secret("right")

class TestFetchSingleIssue:
    def test_valid_key_returns_normalized(self):
        from onboarding.services.confluence import _fetch_single_issue

        with patch(
            "onboarding.services.confluence.httpx.get",
            return_value=_resp(200, {"issues": [_issue("AR-9", assignee="Sunadh P")]}),
        ):
            out = _fetch_single_issue("c1", "t", "AR-9")
        assert out["id"] == "AR-9" and out["assignee"] == "Sunadh P"

    def test_invalid_key_rejected(self):
        # An injection-y key must not reach the API.
        from onboarding.services.confluence import _fetch_single_issue

        with patch("onboarding.services.confluence.httpx.get") as get:
            assert _fetch_single_issue("c1", "t", 'AR-1" OR key="X') is None
            get.assert_not_called()

    def test_no_results(self):
        from onboarding.services.confluence import _fetch_single_issue

        with patch(
            "onboarding.services.confluence.httpx.get", return_value=_resp(200, {"issues": []})
        ):
            assert _fetch_single_issue("c1", "t", "AR-9") is None

    def test_failure(self):
        from onboarding.services.confluence import _fetch_single_issue

        with patch("onboarding.services.confluence.httpx.get", return_value=_resp(500, {})):
            assert _fetch_single_issue("c1", "t", "AR-9") is None

class TestResolveJiraConnection:
    def test_by_cloud_id(self):
        from onboarding.services.confluence import _resolve_jira_connection

        with patch(
            "onboarding.services.confluence._connection_by_cloud_id", return_value=_conn()
        ) as by_cloud:
            _resolve_jira_connection({"cloudId": "c1", "issue": {"key": "AR-1"}})
            by_cloud.assert_called_once_with("c1")

    def test_by_site_url_from_self(self):
        from onboarding.services.confluence import _resolve_jira_connection

        with patch(
            "onboarding.services.confluence._connection_by_site_url", return_value=_conn()
        ) as by_site:
            _resolve_jira_connection(
                {"issue": {"key": "AR-1", "self": "https://acme.atlassian.net/rest/api/2/issue/1"}}
            )
            by_site.assert_called_once_with("https://acme.atlassian.net")

    def test_none_when_unresolvable(self):
        from onboarding.services.confluence import _resolve_jira_connection

        assert _resolve_jira_connection({"issue": {"key": "AR-1"}}) is None

class TestReindexIssue:
    def test_found(self):
        with (
            patch(
                "onboarding.services.confluence._fetch_single_issue",
                return_value={"id": "AR-1"},
            ),
            patch("onboarding.services.confluence._upsert_page", return_value=(1, True, "text")),
            patch("onboarding.services.confluence._embed_page") as emb,
        ):
            from onboarding.services.confluence import _reindex_issue

            assert _reindex_issue(1, "c1", "t", "AR-1") is True
            emb.assert_called_once()

    def test_unreadable(self):
        with patch("onboarding.services.confluence._fetch_single_issue", return_value=None):
            from onboarding.services.confluence import _reindex_issue

            assert _reindex_issue(1, "c1", "t", "AR-1") is False

class TestJiraWebhookDispatch:
    def test_created_reindexes(self):
        with (
            patch("onboarding.services.confluence._resolve_jira_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._reindex_issue", return_value=True) as re_ix,
        ):
            from onboarding.services.confluence import handle_jira_webhook

            out = handle_jira_webhook(
                {"webhookEvent": "jira:issue_created", "issue": {"key": "AR-1"}}
            )
            assert out["status"] == "updated"
            re_ix.assert_called_once_with(1, "c1", "t", "AR-1")

    def test_deleted_deactivates(self):
        with (
            patch(
                "onboarding.services.confluence._resolve_jira_connection",
                return_value=_conn(company_id=42),
            ),
            patch("onboarding.services.confluence._deactivate_pages", return_value=1) as deact,
        ):
            from onboarding.services.confluence import handle_jira_webhook

            out = handle_jira_webhook(
                {"webhookEvent": "jira:issue_deleted", "issue": {"key": "AR-1"}}
            )
            assert out["status"] == "removed"
            deact.assert_called_once_with("AR-1", 42, source="jira")

    def test_reindex_unreadable_ignored(self):
        with (
            patch("onboarding.services.confluence._resolve_jira_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._reindex_issue", return_value=False),
        ):
            from onboarding.services.confluence import handle_jira_webhook

            out = handle_jira_webhook(
                {"webhookEvent": "jira:issue_created", "issue": {"key": "AR-1"}}
            )
            assert out["status"] == "ignored"

    def test_no_key_ignored(self):
        from onboarding.services.confluence import handle_jira_webhook

        assert handle_jira_webhook({"webhookEvent": "jira:issue_updated"})["status"] == "ignored"

    def test_unknown_connection_ignored(self):
        with patch("onboarding.services.confluence._resolve_jira_connection", return_value=None):
            from onboarding.services.confluence import handle_jira_webhook

            out = handle_jira_webhook(
                {"webhookEvent": "jira:issue_updated", "issue": {"key": "AR-1"}}
            )
            assert out["status"] == "ignored"

    def test_unhandled_event_ignored(self):
        with patch("onboarding.services.confluence._resolve_jira_connection", return_value=_conn()):
            from onboarding.services.confluence import handle_jira_webhook

            out = handle_jira_webhook({"webhookEvent": "worklog_updated", "issue": {"key": "AR-1"}})
            assert out["status"] == "ignored"

    def test_never_raises(self):
        # A failure inside dispatch is swallowed (won't 500 → Atlassian won't retry-storm).
        with patch(
            "onboarding.services.confluence._resolve_jira_connection",
            side_effect=RuntimeError("boom"),
        ):
            from onboarding.services.confluence import handle_jira_webhook

            out = handle_jira_webhook(
                {"webhookEvent": "jira:issue_updated", "issue": {"key": "AR-1"}}
            )
            assert out["status"] == "error"

class TestConnectionBySiteUrl:
    def test_strips_trailing_slash(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = _conn()
            from onboarding.services.confluence import _connection_by_site_url

            assert _connection_by_site_url("https://acme.atlassian.net/") is not None
        finally:
            patcher.stop()

    def test_empty_returns_none(self):
        from onboarding.services.confluence import _connection_by_site_url

        assert _connection_by_site_url("") is None

class TestHandlePageUpdated:
    def test_no_pages(self):
        with patch("onboarding.services.confluence._pages_by_page_id", return_value=[]):
            from onboarding.services.confluence import _handle_page_updated

            assert _handle_page_updated("p1")["status"] == "ignored"

    def test_reindexes(self):
        page = DocumentPage(id=1, company_id=1, confluence_page_id="p1", title="t")
        with (
            patch("onboarding.services.confluence._pages_by_page_id", return_value=[page]),
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._reindex_page") as reindex,
        ):
            from onboarding.services.confluence import _handle_page_updated

            assert _handle_page_updated("p1")["status"] == "updated"
            reindex.assert_called_once()

    def test_skips_without_connection(self):
        page = DocumentPage(id=1, company_id=1, confluence_page_id="p1", title="t")
        with (
            patch("onboarding.services.confluence._pages_by_page_id", return_value=[page]),
            patch("onboarding.services.confluence._get_connection", return_value=None),
            patch("onboarding.services.confluence._reindex_page") as reindex,
        ):
            from onboarding.services.confluence import _handle_page_updated

            assert _handle_page_updated("p1")["status"] == "updated"
            reindex.assert_not_called()

class TestHandlePageRemoved:
    def test_removed(self):
        with patch("onboarding.services.confluence._deactivate_pages", return_value=2):
            from onboarding.services.confluence import _handle_page_removed

            assert _handle_page_removed("p1")["status"] == "removed"

    def test_ignored(self):
        with patch("onboarding.services.confluence._deactivate_pages", return_value=0):
            from onboarding.services.confluence import _handle_page_removed

            assert _handle_page_removed("p1")["status"] == "ignored"

class TestHandlePageCreated:
    def _payload(self):
        return {"event": "page_created", "page": {"id": "p9"}, "cloudId": "c1"}

    def test_missing_cloud(self):
        from onboarding.services.confluence import _handle_page_created

        assert _handle_page_created({"page": {"id": "p9"}})["status"] == "ignored"

    def test_no_connection(self):
        with patch("onboarding.services.confluence._connection_by_cloud_id", return_value=None):
            from onboarding.services.confluence import _handle_page_created

            assert _handle_page_created(self._payload())["status"] == "ignored"

    def test_added(self):
        with (
            patch("onboarding.services.confluence._connection_by_cloud_id", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._reindex_page", return_value=True),
        ):
            from onboarding.services.confluence import _handle_page_created

            assert _handle_page_created(self._payload())["status"] == "added"

    def test_unreadable_ignored(self):
        with (
            patch("onboarding.services.confluence._connection_by_cloud_id", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._reindex_page", return_value=False),
        ):
            from onboarding.services.confluence import _handle_page_created

            assert _handle_page_created(self._payload())["status"] == "ignored"

# ── reconcile ────────────────────────────────────────────────────────────────────

class TestReconcile:
    def test_begin_reconcile_schedules(self):
        bg = MagicMock()
        with (
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch("onboarding.services.confluence._require_ready_connection", return_value=_conn()),
            patch("onboarding.services.confluence._running_job", return_value=None),
            patch("onboarding.services.confluence._create_job", return_value=9),
        ):
            from onboarding.services.confluence import begin_reconcile, _run_reconcile

            assert begin_reconcile(_user(), bg) == {
                "job_id": 9,
                "status": "running",
                "kind": "reconcile",
                "source": "confluence",
            }
            bg.add_task.assert_called_once_with(_run_reconcile, 1, 9, "confluence")

    def test_begin_reconcile_returns_existing(self):
        bg = MagicMock()
        with (
            patch(
                "onboarding.services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch("onboarding.services.confluence._require_ready_connection", return_value=_conn()),
            patch(
                "onboarding.services.confluence._running_job",
                return_value=IngestionJob(
                    id=42, company_id=1, status="running", kind="ingest", source="confluence"
                ),
            ),
            patch("onboarding.services.confluence._create_job") as create,
        ):
            from onboarding.services.confluence import begin_reconcile

            assert begin_reconcile(_user(), bg) == {
                "job_id": 42,
                "status": "running",
                "kind": "ingest",
                "source": "confluence",
            }
            create.assert_not_called()
            bg.add_task.assert_not_called()

    def test_run_reconcile_no_connection_failed(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=None),
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            from onboarding.services.confluence import _run_reconcile

            _run_reconcile(1, 9)
        assert upd.call_args_list[-1].kwargs.get("status") == "failed"

    def test_run_reconcile_skips_space_on_generic_error(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch(
                "onboarding.services.confluence._fetch_spaces",
                return_value=[{"key": "A"}, {"key": "B"}],
            ),
            patch(
                "onboarding.services.confluence._search_pages",
                side_effect=[RuntimeError("blip"), [_page("p1")]],
            ),
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            patcher, session = _patch_session()
            try:
                session.exec.return_value.all.return_value = []
                from onboarding.services.confluence import _run_reconcile

                _run_reconcile(1, 9)
                done = [c for c in upd.call_args_list if c.kwargs.get("status") == "done"]
                assert done and "space(s) skipped" in (done[-1].kwargs.get("error") or "")
            finally:
                patcher.stop()

    def test_run_reconcile_auth_failure_fails_not_deactivate_all(self):
        # A 401 mid-read must fail the job — otherwise 0 live pages would deactivate
        # the entire knowledge base.
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "A"}]),
            patch(
                "onboarding.services.confluence._search_pages",
                side_effect=HTTPException(status_code=401, detail="expired"),
            ),
            patch("onboarding.services.confluence._mark_status"),
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            from onboarding.services.confluence import _run_reconcile

            _run_reconcile(1, 9)
            assert upd.call_args_list[-1].kwargs.get("status") == "failed"

    def test_run_reconcile_deactivates_and_reactivates(self):
        gone = DocumentPage(
            id=1, company_id=1, confluence_page_id="gone", title="t", is_active=True
        )
        back = DocumentPage(id=2, company_id=1, confluence_page_id="p1", title="t", is_active=False)
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "ENG"}]),
            patch("onboarding.services.confluence._search_pages", return_value=[_page("p1")]),
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            patcher, session = _patch_session()
            try:
                session.exec.return_value.all.return_value = [gone, back]
                from onboarding.services.confluence import _run_reconcile

                _run_reconcile(1, 9)
                assert gone.is_active is False and back.is_active is True
                done = [c for c in upd.call_args_list if c.kwargs.get("status") == "done"]
                assert done and "1 removed, 1 restored" in (done[-1].kwargs.get("error") or "")
            finally:
                patcher.stop()

    def test_run_reconcile_no_changes_note(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch("onboarding.services.confluence._fetch_spaces", return_value=[{"key": "ENG"}]),
            patch("onboarding.services.confluence._search_pages", return_value=[_page("p1")]),
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            patcher, session = _patch_session()
            try:
                session.exec.return_value.all.return_value = []  # no stored pages → no changes
                from onboarding.services.confluence import _run_reconcile

                _run_reconcile(1, 9)
                done = [c for c in upd.call_args_list if c.kwargs.get("status") == "done"]
                assert done and "up to date" in (done[-1].kwargs.get("error") or "").lower()
            finally:
                patcher.stop()

    def test_run_reconcile_skips_failed_space(self):
        with (
            patch("onboarding.services.confluence._get_connection", return_value=_conn()),
            patch("onboarding.services.confluence._get_valid_token", return_value="t"),
            patch(
                "onboarding.services.confluence._fetch_spaces",
                return_value=[{"key": "A"}, {"key": "B"}],
            ),
            patch(
                "onboarding.services.confluence._search_pages",
                side_effect=[HTTPException(status_code=502, detail="blip"), [_page("p1")]],
            ),
            patch("onboarding.services.confluence._update_job") as upd,
        ):
            patcher, session = _patch_session()
            try:
                session.exec.return_value.all.return_value = []
                from onboarding.services.confluence import _run_reconcile

                _run_reconcile(1, 9)
                done = [c for c in upd.call_args_list if c.kwargs.get("status") == "done"]
                assert done and "1 space(s) skipped" in (done[-1].kwargs.get("error") or "")
            finally:
                patcher.stop()

# ── routes ──────────────────────────────────────────────────────────────────────

class TestRoutes:
    def test_connect_unauth(self, anon_client):
        assert anon_client.post("/confluence/connect").status_code == 401

    def test_connect(self, auth_client):
        with patch(
            "onboarding.controllers.confluence.confluence_service.start_connect",
            return_value={"authorize_url": "https://a"},
        ):
            assert auth_client.post("/confluence/connect").status_code == 200

    def test_status(self, auth_client):
        with patch(
            "onboarding.controllers.confluence.confluence_service.get_status",
            return_value={"connected": True},
        ):
            assert auth_client.get("/confluence/status").json()["connected"] is True

    def test_callback_redirects(self, anon_client):
        with patch(
            "onboarding.controllers.confluence.confluence_service.handle_callback",
            return_value="/onboarding?connected=1",
        ):
            r = anon_client.get("/confluence/callback?code=c&state=s", follow_redirects=False)
        assert r.status_code in (302, 307)

    def test_ingest_unauth(self, anon_client):
        assert anon_client.post("/confluence/ingest").status_code == 401

    def test_ingest(self, auth_client):
        with patch(
            "onboarding.controllers.confluence.confluence_service.begin_ingest",
            return_value={"job_id": 1, "status": "running"},
        ):
            assert auth_client.post("/confluence/ingest").json()["status"] == "running"

    def test_ingest_jira_source(self, auth_client):
        with patch(
            "onboarding.controllers.confluence.confluence_service.begin_ingest",
            return_value={"job_id": 1, "status": "running", "source": "jira"},
        ) as begin:
            r = auth_client.post("/confluence/ingest?source=jira")
        assert r.json()["source"] == "jira"
        assert begin.call_args.kwargs["source"] == "jira"

    def test_connections_status(self, auth_client):
        with patch(
            "onboarding.controllers.confluence.confluence_service.get_connections_status",
            return_value={"connected": True, "sources": {}},
        ):
            assert auth_client.get("/connections/status").json()["connected"] is True

    def test_ingest_status(self, auth_client):
        with patch(
            "onboarding.controllers.confluence.confluence_service.get_ingest_status",
            return_value={"status": "done"},
        ):
            assert auth_client.get("/confluence/ingest/1").json()["status"] == "done"

    def test_cancel_ingest_route(self, auth_client):
        with patch(
            "onboarding.controllers.confluence.confluence_service.cancel_ingest",
            return_value={"status": "cancelled"},
        ) as svc:
            r = auth_client.post("/confluence/ingest/7/cancel")
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"
        assert svc.call_args.args[1] == 7  # (user, job_id)

    def test_reconcile(self, auth_client):
        with patch(
            "onboarding.controllers.confluence.confluence_service.begin_reconcile",
            return_value={"job_id": 9, "status": "running"},
        ):
            assert auth_client.post("/confluence/reconcile").json()["job_id"] == 9

    def test_reconcile_jira_source(self, auth_client):
        with patch(
            "onboarding.controllers.confluence.confluence_service.begin_reconcile",
            return_value={"job_id": 9, "status": "running", "source": "jira"},
        ) as begin:
            r = auth_client.post("/confluence/reconcile?source=jira")
        assert r.json()["source"] == "jira"
        assert begin.call_args.kwargs["source"] == "jira"

    def test_webhook_missing_secret(self, anon_client):
        with patch("config.CONFLUENCE_WEBHOOK_SECRET", "right"):
            assert (
                anon_client.post("/webhooks/confluence", json={"event": "page_updated"}).status_code
                == 401
            )

    def test_webhook_ok(self, anon_client):
        with (
            patch("config.CONFLUENCE_WEBHOOK_SECRET", "right"),
            patch(
                "onboarding.controllers.confluence.confluence_service.handle_webhook",
                return_value={"status": "ok"},
            ) as handle,
        ):
            r = anon_client.post(
                "/webhooks/confluence",
                json={"event": "page_updated", "page": {"id": "p1"}},
                headers={"X-Webhook-Secret": "right"},
            )
        # Acknowledged instantly; processing runs as a background task.
        assert r.status_code == 200 and r.json()["status"] == "accepted"
        handle.assert_called_once()

    def test_webhook_query_secret(self, anon_client):
        with (
            patch("config.CONFLUENCE_WEBHOOK_SECRET", "right"),
            patch(
                "onboarding.controllers.confluence.confluence_service.handle_webhook",
                return_value={"status": "ok"},
            ),
        ):
            r = anon_client.post(
                "/webhooks/confluence?secret=right",
                json={"event": "page_removed", "page": {"id": "p1"}},
            )
        assert r.status_code == 200

    def test_jira_webhook_missing_secret(self, anon_client):
        with patch("config.JIRA_WEBHOOK_SECRET", "right"):
            r = anon_client.post("/webhooks/jira", json={"webhookEvent": "jira:issue_updated"})
            assert r.status_code == 401

    def test_jira_webhook_ok(self, anon_client):
        with (
            patch("config.JIRA_WEBHOOK_SECRET", "right"),
            patch(
                "onboarding.controllers.confluence.confluence_service.handle_jira_webhook",
                return_value={"status": "updated"},
            ) as handle,
        ):
            r = anon_client.post(
                "/webhooks/jira?secret=right",
                json={"webhookEvent": "jira:issue_updated", "issue": {"key": "AR-1"}},
            )
        # Acknowledged instantly; the reindex runs as a background task.
        assert r.status_code == 200 and r.json()["status"] == "accepted"
        handle.assert_called_once()
