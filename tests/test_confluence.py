"""Tests for the Confluence integration (connect + RAG ingest + webhooks)."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

import config
from models.company import Company
from models.confluence_connection import ConfluenceConnection
from models.document_page import DocumentPage
from models.ingestion_job import IngestionJob

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

def _patch_session(target="services.confluence.Session"):
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
        from services.confluence import _domain_from_email

        assert _domain_from_email("Dev@Locus.SH") == "locus.sh"

    def test_state_roundtrip(self):
        from services.confluence import _create_state, _decode_state

        assert _decode_state(_create_state(7)) == 7

    def test_decode_state_garbage(self):
        from services.confluence import _decode_state

        with pytest.raises(HTTPException) as exc:
            _decode_state("nope")
        assert exc.value.status_code == 400

    def test_decode_state_wrong_type(self):
        import jwt as pyjwt
        from config import JWT_SECRET_KEY, JWT_ALGORITHM
        from services.confluence import _decode_state

        tok = pyjwt.encode({"sub": "1", "type": "access"}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        with pytest.raises(HTTPException) as exc:
            _decode_state(tok)
        assert exc.value.status_code == 400

    def test_strip_html(self):
        from services.confluence import _strip_html

        assert _strip_html("<p>Hi <b>there</b></p>") == "Hi there"

    def test_page_fields(self):
        from services.confluence import _page_fields

        pid, version, space_key, title, text = _page_fields(_page())
        assert (pid, version, space_key, title) == ("p1", 1, "ENG", "Arch")
        assert text == "hello world"

# ── company resolution ───────────────────────────────────────────────────────

class TestCompanyResolution:
    def test_existing(self):
        existing = Company(id=1, name="locus.sh", domain="locus.sh")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = existing
            from services.confluence import get_or_create_company_for_user

            assert get_or_create_company_for_user(_user()) is existing
            session.commit.assert_not_called()
        finally:
            patcher.stop()

    def test_new(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = None
            from services.confluence import get_or_create_company_for_user

            assert get_or_create_company_for_user(_user(email="x@acme.io")).domain == "acme.io"
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_race(self):
        winner = Company(id=2, name="acme.io", domain="acme.io")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.side_effect = [None, winner]
            session.commit.side_effect = IntegrityError("x", "y", "z")
            from services.confluence import get_or_create_company_for_user

            assert get_or_create_company_for_user(_user(email="x@acme.io")) is winner
        finally:
            patcher.stop()

    def test_get_connection(self):
        conn = _conn()
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = conn
            from services.confluence import _get_connection

            assert _get_connection(1) is conn
        finally:
            patcher.stop()

    def test_require_ready_ok(self):
        with patch("services.confluence._get_connection", return_value=_conn()):
            from services.confluence import _require_ready_connection

            assert _require_ready_connection(1).status == "ready"

    def test_require_ready_409(self):
        with patch("services.confluence._get_connection", return_value=None):
            from services.confluence import _require_ready_connection

            with pytest.raises(HTTPException) as exc:
                _require_ready_connection(1)
            assert exc.value.status_code == 409

# ── embedding key resolution ─────────────────────────────────────────────────────

class TestEmbeddingKey:
    def test_prefers_user_gemini_key(self):
        with (
            patch(
                "services.confluence._get_connection", return_value=_conn(connected_by_user_id=7)
            ),
            patch("services.confluence.get_user_by_id", return_value=_user()),
            patch("services.confluence.get_user_gemini_key", return_value="userkey"),
        ):
            from services.confluence import resolve_embedding_key

            assert resolve_embedding_key(1) == "userkey"

    def test_falls_back_to_system_key(self):
        with (
            patch(
                "services.confluence._get_connection", return_value=_conn(connected_by_user_id=7)
            ),
            patch("services.confluence.get_user_by_id", return_value=_user()),
            patch("services.confluence.get_user_gemini_key", return_value=None),
            patch("config.GEMINI_EMBEDDING_API_KEY", "syskey"),
        ):
            from services.confluence import resolve_embedding_key

            assert resolve_embedding_key(1) == "syskey"

    def test_no_connection_uses_system_key(self):
        with (
            patch("services.confluence._get_connection", return_value=None),
            patch("config.GEMINI_EMBEDDING_API_KEY", "syskey"),
        ):
            from services.confluence import resolve_embedding_key

            assert resolve_embedding_key(1) == "syskey"

class TestGetUserGeminiKey:
    def test_returns_key(self):
        provider = MagicMock()
        provider.id = 3
        with (
            patch("services.user.get_provider_by_name", return_value=provider),
            patch("services.user.get_provider_key", return_value="gk"),
        ):
            from services.llm import get_user_gemini_key

            assert get_user_gemini_key(_user()) == "gk"

    def test_no_provider(self):
        with patch("services.user.get_provider_by_name", return_value=None):
            from services.llm import get_user_gemini_key

            assert get_user_gemini_key(_user()) is None

# ── OAuth HTTP + connect/callback ────────────────────────────────────────────────

class TestOAuthHttp:
    def test_exchange_code_success(self):
        from services.confluence import _exchange_code

        with patch(
            "services.confluence.httpx.post", return_value=_resp(200, {"access_token": "AT"})
        ):
            assert _exchange_code("code")["access_token"] == "AT"

    def test_exchange_code_failure(self):
        from services.confluence import _exchange_code

        with patch("services.confluence.httpx.post", return_value=_resp(400, {})):
            with pytest.raises(HTTPException) as exc:
                _exchange_code("code")
            assert exc.value.status_code == 502

    def test_fetch_resources_success(self):
        from services.confluence import _fetch_accessible_resources

        with patch("services.confluence.httpx.get", return_value=_resp(200, [{"id": "c1"}])):
            assert _fetch_accessible_resources("AT")[0]["id"] == "c1"

    def test_fetch_resources_failure(self):
        from services.confluence import _fetch_accessible_resources

        with patch("services.confluence.httpx.get", return_value=_resp(401, {})):
            with pytest.raises(HTTPException) as exc:
                _fetch_accessible_resources("AT")
            assert exc.value.status_code == 502

    def test_upsert_connection_new(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = None
            from services.confluence import _upsert_connection

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
            from services.confluence import _upsert_connection

            _upsert_connection(1, 1, "c1", None, "AT", None, datetime.now(timezone.utc))
            assert conn.refresh_token is None
            assert conn.status == "ready"
        finally:
            patcher.stop()

class TestStartConnect:
    def test_not_configured_503(self):
        from services.confluence import start_connect

        with patch("config.is_confluence_oauth_configured", return_value=False):
            with pytest.raises(HTTPException) as exc:
                start_connect(_user())
            assert exc.value.status_code == 503

    def test_configured(self):
        from services.confluence import start_connect

        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("config.ATLASSIAN_CLIENT_ID", "cid"),
            patch("config.ATLASSIAN_REDIRECT_URI", "https://app/cb"),
            patch("config.ATLASSIAN_OAUTH_SCOPES", "scopeA"),
        ):
            out = start_connect(_user())
        assert "client_id=cid" in out["authorize_url"]

class TestHandleCallback:
    def _state(self, uid=1):
        from services.confluence import _create_state

        return _create_state(uid)

    def test_success(self):
        company = Company(id=5, name="locus.sh", domain="locus.sh")
        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("services.confluence.get_user_by_id", return_value=_user()),
            patch("services.confluence.get_or_create_company_for_user", return_value=company),
            patch(
                "services.confluence._exchange_code",
                return_value={"access_token": "AT", "expires_in": 3600},
            ),
            patch(
                "services.confluence._fetch_accessible_resources",
                return_value=[{"id": "c1", "url": "https://x"}],
            ),
            patch("services.confluence._upsert_connection") as up,
        ):
            from services.confluence import handle_callback

            assert handle_callback("code", self._state()) == config.CONFLUENCE_POST_CONNECT_REDIRECT
            up.assert_called_once()

    def test_not_configured(self):
        from services.confluence import handle_callback

        with patch("config.is_confluence_oauth_configured", return_value=False):
            with pytest.raises(HTTPException) as exc:
                handle_callback("c", "s")
            assert exc.value.status_code == 503

    def test_unknown_user(self):
        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("services.confluence.get_user_by_id", return_value=None),
        ):
            from services.confluence import handle_callback

            with pytest.raises(HTTPException) as exc:
                handle_callback("c", self._state(9))
            assert exc.value.status_code == 400

    def test_no_access_token(self):
        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("services.confluence.get_user_by_id", return_value=_user()),
            patch(
                "services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch("services.confluence._exchange_code", return_value={}),
        ):
            from services.confluence import handle_callback

            with pytest.raises(HTTPException) as exc:
                handle_callback("c", self._state())
            assert exc.value.status_code == 502

    def test_no_resources(self):
        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("services.confluence.get_user_by_id", return_value=_user()),
            patch(
                "services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch("services.confluence._exchange_code", return_value={"access_token": "AT"}),
            patch("services.confluence._fetch_accessible_resources", return_value=[]),
        ):
            from services.confluence import handle_callback

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
                "services.confluence.get_or_create_company_for_user", return_value=self._company()
            ),
            patch("services.confluence._get_connection", return_value=None),
        ):
            from services.confluence import get_status

            s = get_status(_user())
            assert s["connected"] is False and s["page_count"] == 0

    def test_ready_with_counts(self):
        with (
            patch(
                "services.confluence.get_or_create_company_for_user", return_value=self._company()
            ),
            patch("services.confluence._get_connection", return_value=_conn(site_url="https://x")),
            patch("services.confluence._counts", return_value=(12, 340)),
        ):
            from services.confluence import get_status

            s = get_status(_user())
            assert s["connected"] is True
            assert s["page_count"] == 12 and s["chunk_count"] == 340

# ── token freshness / refresh ────────────────────────────────────────────────────

class TestToken:
    def test_expired_none(self):
        from services.confluence import _is_token_expired

        assert _is_token_expired(None) is True

    def test_not_expired_future(self):
        from services.confluence import _is_token_expired

        assert _is_token_expired(datetime.now(timezone.utc) + timedelta(hours=1)) is False

    def test_expired_past_naive(self):
        from services.confluence import _is_token_expired

        assert _is_token_expired(datetime.utcnow() - timedelta(hours=1)) is True

    def test_get_valid_uses_existing(self):
        from services.encryption import encrypt_secret
        from services.confluence import _get_valid_token

        conn = _conn(
            access_token=encrypt_secret("LIVE"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert _get_valid_token(conn) == "LIVE"

    def test_get_valid_refreshes(self):
        from services.confluence import _get_valid_token

        conn = _conn(access_token="e", token_expires_at=None)
        with patch("services.confluence._refresh_access_token", return_value="FRESH") as ref:
            assert _get_valid_token(conn) == "FRESH"
            ref.assert_called_once()

    def test_refresh_no_token_401(self):
        from services.confluence import _refresh_access_token

        with pytest.raises(HTTPException) as exc:
            _refresh_access_token(_conn(refresh_token=None))
        assert exc.value.status_code == 401

    def test_refresh_failure_marks_error(self):
        from services.encryption import encrypt_secret
        from services.confluence import _refresh_access_token

        conn = _conn(refresh_token=encrypt_secret("RT"))
        with (
            patch("services.confluence.httpx.post", return_value=_resp(400, {})),
            patch("services.confluence._mark_status") as mark,
        ):
            with pytest.raises(HTTPException) as exc:
                _refresh_access_token(conn)
            assert exc.value.status_code == 401
            mark.assert_called_once_with(1, "error")

    def test_refresh_success_persists(self):
        from services.encryption import encrypt_secret
        from services.confluence import _refresh_access_token

        conn = _conn(refresh_token=encrypt_secret("RT"))
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = conn
            with patch(
                "services.confluence.httpx.post",
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
            from services.confluence import _mark_status

            _mark_status(1, "error")
            assert conn.status == "error"
        finally:
            patcher.stop()

    def test_mark_status_absent(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = None
            from services.confluence import _mark_status

            _mark_status(1, "error")
            session.commit.assert_not_called()
        finally:
            patcher.stop()

# ── REST client: spaces / pages ──────────────────────────────────────────────────

class TestFetchSpaces:
    def test_single(self):
        from services.confluence import _fetch_spaces

        with patch(
            "services.confluence.httpx.get",
            return_value=_resp(200, {"results": [{"space": {"key": "ENG"}}]}),
        ):
            assert _fetch_spaces("c1", "t")[0]["key"] == "ENG"

    def test_skips_personal(self):
        from services.confluence import _fetch_spaces

        payload = {
            "results": [{"space": {"key": "ENG"}}, {"space": {"key": "~123"}}, {"title": "x"}]
        }
        with patch("services.confluence.httpx.get", return_value=_resp(200, payload)):
            assert [s["key"] for s in _fetch_spaces("c1", "t")] == ["ENG"]

    def test_paginates(self):
        from services.confluence import _fetch_spaces

        p1 = _resp(
            200, {"results": [{"space": {"key": "A"}}], "_links": {"next": "/rest/api/search?c=1"}}
        )
        p2 = _resp(200, {"results": [{"space": {"key": "B"}}], "_links": {}})
        with patch("services.confluence.httpx.get", side_effect=[p1, p2]):
            assert [s["key"] for s in _fetch_spaces("c1", "t")] == ["A", "B"]

    def test_failure(self):
        from services.confluence import _fetch_spaces

        with patch("services.confluence.httpx.get", return_value=_resp(403, {})):
            with pytest.raises(HTTPException) as exc:
                _fetch_spaces("c1", "t")
            assert exc.value.status_code == 502

class TestSearchPages:
    def test_single(self):
        from services.confluence import _search_pages

        with patch(
            "services.confluence.httpx.get", return_value=_resp(200, {"results": [_page()]})
        ):
            assert _search_pages("c1", "t", "ENG")[0]["id"] == "p1"

    def test_paginates(self):
        from services.confluence import _search_pages

        p1 = _resp(
            200, {"results": [_page("p1")], "_links": {"next": "/rest/api/content/search?c=1"}}
        )
        p2 = _resp(200, {"results": [_page("p2")], "_links": {}})
        with patch("services.confluence.httpx.get", side_effect=[p1, p2]):
            assert [p["id"] for p in _search_pages("c1", "t", "ENG")] == ["p1", "p2"]

    def test_failure(self):
        from services.confluence import _search_pages

        with patch("services.confluence.httpx.get", return_value=_resp(500, {})):
            with pytest.raises(HTTPException) as exc:
                _search_pages("c1", "t", "ENG")
            assert exc.value.status_code == 502

class TestFetchSinglePage:
    def test_found(self):
        from services.confluence import _fetch_single_page

        with patch(
            "services.confluence.httpx.get", return_value=_resp(200, {"results": [_page()]})
        ):
            assert _fetch_single_page("c1", "t", "p1")["id"] == "p1"

    def test_no_results(self):
        from services.confluence import _fetch_single_page

        with patch("services.confluence.httpx.get", return_value=_resp(200, {"results": []})):
            assert _fetch_single_page("c1", "t", "p1") is None

    def test_failure(self):
        from services.confluence import _fetch_single_page

        with patch("services.confluence.httpx.get", return_value=_resp(404, {})):
            assert _fetch_single_page("c1", "t", "p1") is None

# ── knowledge base persistence ──────────────────────────────────────────────────

class TestPersistence:
    def test_page_chunk_count(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.one.return_value = 3
            from services.confluence import _page_chunk_count

            assert _page_chunk_count(1) == 3
        finally:
            patcher.stop()

    def test_upsert_page_new(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = None
            session.refresh.side_effect = lambda row: setattr(row, "id", 9)
            from services.confluence import _upsert_page

            pid, changed, text = _upsert_page(1, _page())
            assert changed is True and text == "hello world"
            assert pid == 9
        finally:
            patcher.stop()

    def test_upsert_page_unchanged(self):
        existing = DocumentPage(
            id=5, company_id=1, confluence_page_id="p1", title="Arch", version=1, is_active=True
        )
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = existing
            session.refresh.side_effect = lambda row: None
            from services.confluence import _upsert_page

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
            from services.confluence import _upsert_page

            _, changed, _t = _upsert_page(1, _page(version=2))
            assert changed is True
        finally:
            patcher.stop()

    def test_delete_chunks(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = [MagicMock(), MagicMock()]
            from services.confluence import _delete_chunks

            _delete_chunks(1)
            assert session.delete.call_count == 2
        finally:
            patcher.stop()

    def test_store_chunks(self):
        patcher, session = _patch_session()
        try:
            from services.confluence import _store_chunks

            _store_chunks(1, 2, ["a", "b"], [[0.1], [0.2]])
            assert session.add.call_count == 2
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_embed_page_with_chunks(self):
        with (
            patch("services.confluence.chunk_text", return_value=["a", "b"]),
            patch("services.confluence.embedding_service.embed_texts", return_value=[[0.1], [0.2]]),
            patch("services.confluence._delete_chunks") as dele,
            patch("services.confluence._store_chunks") as store,
        ):
            from services.confluence import _embed_page

            assert _embed_page(1, 2, "text", "gk") == 2
            dele.assert_called_once()
            store.assert_called_once()

    def test_embed_page_no_chunks(self):
        with (
            patch("services.confluence.chunk_text", return_value=[]),
            patch("services.confluence._delete_chunks") as dele,
        ):
            from services.confluence import _embed_page

            assert _embed_page(1, 2, "", "gk") == 0
            dele.assert_called_once()

    def test_counts(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.one.side_effect = [12, 340]
            from services.confluence import _counts

            assert _counts(1) == (12, 340)
        finally:
            patcher.stop()

# ── ingestion job ────────────────────────────────────────────────────────────────

class TestIngestionJob:
    def test_create_job(self):
        patcher, session = _patch_session()
        try:
            session.refresh.side_effect = lambda job: setattr(job, "id", 7)
            from services.confluence import _create_job

            assert _create_job(1) == 7
        finally:
            patcher.stop()

    def test_update_job(self):
        job = IngestionJob(id=1, company_id=1, status="running")
        patcher, session = _patch_session()
        try:
            session.get.return_value = job
            from services.confluence import _update_job

            _update_job(
                1,
                total_pages=5,
                processed_pages=5,
                total_chunks=10,
                embedded_chunks=10,
                status="done",
                error="e",
                completed=True,
            )
            assert job.status == "done" and job.total_chunks == 10 and job.error == "e"
            assert job.completed_at is not None
        finally:
            patcher.stop()

    def test_update_job_missing(self):
        patcher, session = _patch_session()
        try:
            session.get.return_value = None
            from services.confluence import _update_job

            _update_job(9, status="x")
            session.commit.assert_not_called()
        finally:
            patcher.stop()

class TestBeginIngest:
    def test_not_connected(self):
        with (
            patch(
                "services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch(
                "services.confluence._require_ready_connection",
                side_effect=HTTPException(status_code=409, detail="x"),
            ),
        ):
            from services.confluence import begin_ingest

            with pytest.raises(HTTPException) as exc:
                begin_ingest(_user(), MagicMock())
            assert exc.value.status_code == 409

    def test_embeddings_not_configured(self):
        with (
            patch(
                "services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch("services.confluence._require_ready_connection", return_value=_conn()),
            patch("services.confluence.resolve_embedding_key", return_value=None),
        ):
            from services.confluence import begin_ingest

            with pytest.raises(HTTPException) as exc:
                begin_ingest(_user(), MagicMock())
            assert exc.value.status_code == 503

    def test_schedules(self):
        bg = MagicMock()
        with (
            patch(
                "services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch("services.confluence._require_ready_connection", return_value=_conn()),
            patch("services.confluence.resolve_embedding_key", return_value="gk"),
            patch("services.confluence._create_job", return_value=7),
        ):
            from services.confluence import begin_ingest

            assert begin_ingest(_user(), bg) == {"job_id": 7, "status": "running"}
            bg.add_task.assert_called_once()

class TestRunIngest:
    def test_success(self):
        with (
            patch("services.confluence._get_connection", return_value=_conn()),
            patch("services.confluence._get_valid_token", return_value="t"),
            patch("services.confluence._fetch_spaces", return_value=[{"key": "ENG"}, {}]),
            patch("services.confluence._search_pages", return_value=[_page("p1")]),
            patch("services.confluence._upsert_page", return_value=(1, True, "hello world text")),
            patch("services.confluence._page_chunk_count", return_value=0),
            patch("services.confluence.chunk_text", return_value=["c1", "c2"]),
            patch("services.confluence.embedding_service.embed_texts", return_value=[[0.1], [0.2]]),
            patch("services.confluence._delete_chunks"),
            patch("services.confluence._store_chunks") as store,
            patch("services.confluence._update_job") as upd,
        ):
            from services.confluence import _run_ingest

            _run_ingest(1, 7, "gk")
            store.assert_called_once()
            assert any(c.kwargs.get("status") == "done" for c in upd.call_args_list)

    def test_skips_unchanged_with_chunks(self):
        with (
            patch("services.confluence._get_connection", return_value=_conn()),
            patch("services.confluence._get_valid_token", return_value="t"),
            patch("services.confluence._fetch_spaces", return_value=[{"key": "ENG"}]),
            patch("services.confluence._search_pages", return_value=[_page("p1")]),
            patch("services.confluence._upsert_page", return_value=(1, False, "text")),
            patch("services.confluence._page_chunk_count", return_value=3),
            patch("services.confluence.embedding_service.embed_texts") as embed,
            patch("services.confluence._update_job"),
        ):
            from services.confluence import _run_ingest

            _run_ingest(1, 7, "gk")
            embed.assert_not_called()

    def test_no_connection_failed(self):
        with (
            patch("services.confluence._get_connection", return_value=None),
            patch("services.confluence._update_job") as upd,
        ):
            from services.confluence import _run_ingest

            _run_ingest(1, 7, "gk")
        assert upd.call_args_list[-1].kwargs.get("status") == "failed"

    def test_search_failure_failed(self):
        with (
            patch("services.confluence._get_connection", return_value=_conn()),
            patch("services.confluence._get_valid_token", return_value="t"),
            patch(
                "services.confluence._fetch_spaces",
                side_effect=HTTPException(status_code=502, detail="boom"),
            ),
            patch("services.confluence._update_job") as upd,
        ):
            from services.confluence import _run_ingest

            _run_ingest(1, 7, "gk")
        last = upd.call_args_list[-1].kwargs
        assert last.get("status") == "failed" and "boom" in (last.get("error") or "")

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
            "services.confluence.get_or_create_company_for_user",
            return_value=Company(id=1, name="a", domain="a"),
        ):
            patcher, session = _patch_session()
            try:
                session.get.return_value = job
                from services.confluence import get_ingest_status

                out = get_ingest_status(_user(), 7)
                assert out["embedded_chunks"] == 8 and out["status"] == "running"
            finally:
                patcher.stop()

    def test_wrong_company(self):
        job = IngestionJob(id=7, company_id=999, status="running")
        with patch(
            "services.confluence.get_or_create_company_for_user",
            return_value=Company(id=1, name="a", domain="a"),
        ):
            patcher, session = _patch_session()
            try:
                session.get.return_value = job
                from services.confluence import get_ingest_status

                with pytest.raises(HTTPException) as exc:
                    get_ingest_status(_user(), 7)
                assert exc.value.status_code == 404
            finally:
                patcher.stop()

# ── webhooks ──────────────────────────────────────────────────────────────────

class TestWebhookSecret:
    def test_not_configured(self):
        from services.confluence import verify_webhook_secret

        with patch("config.CONFLUENCE_WEBHOOK_SECRET", None):
            with pytest.raises(HTTPException) as exc:
                verify_webhook_secret("x")
            assert exc.value.status_code == 503

    def test_mismatch(self):
        from services.confluence import verify_webhook_secret

        with patch("config.CONFLUENCE_WEBHOOK_SECRET", "right"):
            with pytest.raises(HTTPException) as exc:
                verify_webhook_secret("wrong")
            assert exc.value.status_code == 401

    def test_ok(self):
        from services.confluence import verify_webhook_secret

        with patch("config.CONFLUENCE_WEBHOOK_SECRET", "right"):
            verify_webhook_secret("right")

class TestWebhookHelpers:
    def test_pages_by_page_id(self):
        page = DocumentPage(id=1, company_id=1, confluence_page_id="p1", title="t")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = [page]
            from services.confluence import _pages_by_page_id

            assert _pages_by_page_id("p1") == [page]
        finally:
            patcher.stop()

    def test_connection_by_cloud_id(self):
        conn = _conn()
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = conn
            from services.confluence import _connection_by_cloud_id

            assert _connection_by_cloud_id("c1") is conn
        finally:
            patcher.stop()

    def test_deactivate_pages(self):
        page = DocumentPage(id=1, company_id=1, confluence_page_id="p1", title="t", is_active=True)
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = [page]
            from services.confluence import _deactivate_pages

            assert _deactivate_pages("p1") == 1
            assert page.is_active is False
        finally:
            patcher.stop()

    def test_reindex_page_found(self):
        with (
            patch("services.confluence._fetch_single_page", return_value=_page()),
            patch("services.confluence._upsert_page", return_value=(1, True, "text")),
            patch("services.confluence.resolve_embedding_key", return_value="gk"),
            patch("services.confluence._embed_page") as embed,
        ):
            from services.confluence import _reindex_page

            assert _reindex_page(1, "c1", "t", "p1") is True
            embed.assert_called_once()

    def test_reindex_page_unreadable(self):
        with patch("services.confluence._fetch_single_page", return_value=None):
            from services.confluence import _reindex_page

            assert _reindex_page(1, "c1", "t", "p1") is False

class TestHandleWebhook:
    def test_unknown_ignored(self):
        from services.confluence import handle_webhook

        assert handle_webhook({"event": "label_added"})["status"] == "ignored"

    def test_updated_no_page(self):
        from services.confluence import handle_webhook

        assert handle_webhook({"event": "page_updated"})["status"] == "ignored"

    def test_removed_no_page(self):
        from services.confluence import handle_webhook

        assert handle_webhook({"event": "page_removed"})["status"] == "ignored"

    def test_updated_dispatch(self):
        from services.confluence import handle_webhook

        with patch(
            "services.confluence._handle_page_updated", return_value={"status": "updated"}
        ) as h:
            handle_webhook({"event": "page_updated", "page": {"id": "p1"}})
            h.assert_called_once_with("p1")

    def test_removed_dispatch(self):
        from services.confluence import handle_webhook

        with patch(
            "services.confluence._handle_page_removed", return_value={"status": "removed"}
        ) as h:
            handle_webhook({"event": "page_trashed", "page": {"id": "p1"}})
            h.assert_called_once_with("p1")

    def test_created_dispatch(self):
        from services.confluence import handle_webhook

        with patch(
            "services.confluence._handle_page_created", return_value={"status": "added"}
        ) as h:
            handle_webhook({"event": "page_created", "page": {"id": "p1"}, "cloudId": "c1"})
            h.assert_called_once()

class TestHandlePageUpdated:
    def test_no_pages(self):
        with patch("services.confluence._pages_by_page_id", return_value=[]):
            from services.confluence import _handle_page_updated

            assert _handle_page_updated("p1")["status"] == "ignored"

    def test_reindexes(self):
        page = DocumentPage(id=1, company_id=1, confluence_page_id="p1", title="t")
        with (
            patch("services.confluence._pages_by_page_id", return_value=[page]),
            patch("services.confluence._get_connection", return_value=_conn()),
            patch("services.confluence._get_valid_token", return_value="t"),
            patch("services.confluence._reindex_page") as reindex,
        ):
            from services.confluence import _handle_page_updated

            assert _handle_page_updated("p1")["status"] == "updated"
            reindex.assert_called_once()

    def test_skips_without_connection(self):
        page = DocumentPage(id=1, company_id=1, confluence_page_id="p1", title="t")
        with (
            patch("services.confluence._pages_by_page_id", return_value=[page]),
            patch("services.confluence._get_connection", return_value=None),
            patch("services.confluence._reindex_page") as reindex,
        ):
            from services.confluence import _handle_page_updated

            assert _handle_page_updated("p1")["status"] == "updated"
            reindex.assert_not_called()

class TestHandlePageRemoved:
    def test_removed(self):
        with patch("services.confluence._deactivate_pages", return_value=2):
            from services.confluence import _handle_page_removed

            assert _handle_page_removed("p1")["status"] == "removed"

    def test_ignored(self):
        with patch("services.confluence._deactivate_pages", return_value=0):
            from services.confluence import _handle_page_removed

            assert _handle_page_removed("p1")["status"] == "ignored"

class TestHandlePageCreated:
    def _payload(self):
        return {"event": "page_created", "page": {"id": "p9"}, "cloudId": "c1"}

    def test_missing_cloud(self):
        from services.confluence import _handle_page_created

        assert _handle_page_created({"page": {"id": "p9"}})["status"] == "ignored"

    def test_no_connection(self):
        with patch("services.confluence._connection_by_cloud_id", return_value=None):
            from services.confluence import _handle_page_created

            assert _handle_page_created(self._payload())["status"] == "ignored"

    def test_added(self):
        with (
            patch("services.confluence._connection_by_cloud_id", return_value=_conn()),
            patch("services.confluence._get_valid_token", return_value="t"),
            patch("services.confluence._reindex_page", return_value=True),
        ):
            from services.confluence import _handle_page_created

            assert _handle_page_created(self._payload())["status"] == "added"

    def test_unreadable_ignored(self):
        with (
            patch("services.confluence._connection_by_cloud_id", return_value=_conn()),
            patch("services.confluence._get_valid_token", return_value="t"),
            patch("services.confluence._reindex_page", return_value=False),
        ):
            from services.confluence import _handle_page_created

            assert _handle_page_created(self._payload())["status"] == "ignored"

# ── reconcile ────────────────────────────────────────────────────────────────────

class TestReconcile:
    def test_not_connected(self):
        with patch("services.confluence._get_connection", return_value=None):
            from services.confluence import reconcile_company

            with pytest.raises(HTTPException) as exc:
                reconcile_company(1)
            assert exc.value.status_code == 409

    def test_deactivates_and_reactivates(self):
        gone = DocumentPage(
            id=1, company_id=1, confluence_page_id="gone", title="t", is_active=True
        )
        back = DocumentPage(id=2, company_id=1, confluence_page_id="p1", title="t", is_active=False)
        with (
            patch("services.confluence._get_connection", return_value=_conn()),
            patch("services.confluence._get_valid_token", return_value="t"),
            patch("services.confluence._fetch_spaces", return_value=[{"key": "ENG"}]),
            patch("services.confluence._search_pages", return_value=[_page("p1")]),
        ):
            patcher, session = _patch_session()
            try:
                session.exec.return_value.all.return_value = [gone, back]
                from services.confluence import reconcile_company

                assert reconcile_company(1) == {"deactivated": 1, "reactivated": 1}
                assert gone.is_active is False and back.is_active is True
            finally:
                patcher.stop()

# ── routes ──────────────────────────────────────────────────────────────────────

class TestRoutes:
    def test_connect_unauth(self, anon_client):
        assert anon_client.post("/confluence/connect").status_code == 401

    def test_connect(self, auth_client):
        with patch(
            "controllers.confluence.confluence_service.start_connect",
            return_value={"authorize_url": "https://a"},
        ):
            assert auth_client.post("/confluence/connect").status_code == 200

    def test_status(self, auth_client):
        with patch(
            "controllers.confluence.confluence_service.get_status", return_value={"connected": True}
        ):
            assert auth_client.get("/confluence/status").json()["connected"] is True

    def test_callback_redirects(self, anon_client):
        with patch(
            "controllers.confluence.confluence_service.handle_callback",
            return_value="/onboarding?connected=1",
        ):
            r = anon_client.get("/confluence/callback?code=c&state=s", follow_redirects=False)
        assert r.status_code in (302, 307)

    def test_ingest_unauth(self, anon_client):
        assert anon_client.post("/confluence/ingest").status_code == 401

    def test_ingest(self, auth_client):
        with patch(
            "controllers.confluence.confluence_service.begin_ingest",
            return_value={"job_id": 1, "status": "running"},
        ):
            assert auth_client.post("/confluence/ingest").json()["status"] == "running"

    def test_ingest_status(self, auth_client):
        with patch(
            "controllers.confluence.confluence_service.get_ingest_status",
            return_value={"status": "done"},
        ):
            assert auth_client.get("/confluence/ingest/1").json()["status"] == "done"

    def test_reconcile(self, auth_client):
        with (
            patch(
                "controllers.confluence.confluence_service.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch(
                "controllers.confluence.confluence_service.reconcile_company",
                return_value={"deactivated": 1, "reactivated": 0},
            ),
        ):
            assert auth_client.post("/confluence/reconcile").json()["deactivated"] == 1

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
                "controllers.confluence.confluence_service.handle_webhook",
                return_value={"status": "ok"},
            ),
        ):
            r = anon_client.post(
                "/webhooks/confluence",
                json={"event": "page_updated", "page": {"id": "p1"}},
                headers={"X-Webhook-Secret": "right"},
            )
        assert r.status_code == 200

    def test_webhook_query_secret(self, anon_client):
        with (
            patch("config.CONFLUENCE_WEBHOOK_SECRET", "right"),
            patch(
                "controllers.confluence.confluence_service.handle_webhook",
                return_value={"status": "ok"},
            ),
        ):
            r = anon_client.post(
                "/webhooks/confluence?secret=right",
                json={"event": "page_removed", "page": {"id": "p1"}},
            )
        assert r.status_code == 200
