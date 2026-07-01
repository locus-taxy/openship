"""Tests for the Confluence integration (Phase 1: connection)."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

import config
from models.company import Company
from models.confluence_connection import ConfluenceConnection

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

def _patch_session(target="services.confluence.Session"):
    patcher = patch(target)
    mock_cls = patcher.start()
    session_mock = MagicMock()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher, session_mock

# ── encryption helpers ───────────────────────────────────────────────────────

class TestSecretEncryption:
    def test_roundtrip(self):
        from services.encryption import encrypt_secret, decrypt_secret

        enc = encrypt_secret("super-secret-oauth-token")
        assert enc != "super-secret-oauth-token"
        assert decrypt_secret(enc) == "super-secret-oauth-token"

# ── config helper ─────────────────────────────────────────────────────────────

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

# ── service: pure helpers ─────────────────────────────────────────────────────

class TestConfluenceHelpers:
    def test_domain_from_email_lowercased(self):
        from services.confluence import _domain_from_email

        assert _domain_from_email("Dev@Locus.SH") == "locus.sh"

    def test_state_roundtrip(self):
        from services.confluence import _create_state, _decode_state

        assert _decode_state(_create_state(7)) == 7

    def test_decode_state_garbage(self):
        from services.confluence import _decode_state

        with pytest.raises(HTTPException) as exc:
            _decode_state("not-a-token")
        assert exc.value.status_code == 400

    def test_decode_state_wrong_type(self):
        import jwt as pyjwt
        from config import JWT_SECRET_KEY, JWT_ALGORITHM
        from services.confluence import _decode_state

        tok = pyjwt.encode({"sub": "1", "type": "access"}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        with pytest.raises(HTTPException) as exc:
            _decode_state(tok)
        assert exc.value.status_code == 400

# ── service: company resolution ───────────────────────────────────────────────

class TestCompanyResolution:
    def test_existing_company_returned(self):
        existing = Company(id=1, name="locus.sh", domain="locus.sh")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = existing
            from services.confluence import get_or_create_company_for_user

            assert get_or_create_company_for_user(_user()) is existing
            session.commit.assert_not_called()
        finally:
            patcher.stop()

    def test_new_company_created(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = None
            from services.confluence import get_or_create_company_for_user

            company = get_or_create_company_for_user(_user(email="x@acme.io"))
            assert company.domain == "acme.io"
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_race_falls_back_to_existing(self):
        winner = Company(id=2, name="acme.io", domain="acme.io")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.side_effect = [None, winner]
            session.commit.side_effect = IntegrityError("x", "y", "z")
            from services.confluence import get_or_create_company_for_user

            assert get_or_create_company_for_user(_user(email="x@acme.io")) is winner
            session.rollback.assert_called_once()
        finally:
            patcher.stop()

    def test_get_connection(self):
        conn = ConfluenceConnection(id=1, company_id=1, status="ready")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = conn
            from services.confluence import _get_connection

            assert _get_connection(1) is conn
        finally:
            patcher.stop()

# ── service: Atlassian HTTP ────────────────────────────────────────────────────

class TestAtlassianHttp:
    def test_exchange_code_success(self):
        from services.confluence import _exchange_code

        with patch(
            "services.confluence.httpx.post",
            return_value=_resp(
                200, {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600}
            ),
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

        with patch(
            "services.confluence.httpx.get",
            return_value=_resp(200, [{"id": "cloud1", "url": "https://x.atlassian.net"}]),
        ):
            res = _fetch_accessible_resources("AT")
            assert res[0]["id"] == "cloud1"

    def test_fetch_resources_failure(self):
        from services.confluence import _fetch_accessible_resources

        with patch("services.confluence.httpx.get", return_value=_resp(401, {})):
            with pytest.raises(HTTPException) as exc:
                _fetch_accessible_resources("AT")
            assert exc.value.status_code == 502

# ── service: persistence ───────────────────────────────────────────────────────

class TestUpsertConnection:
    def test_creates_new(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = None
            from services.confluence import _upsert_connection

            _upsert_connection(
                1, 1, "cloud", "https://site", "AT", "RT", datetime.now(timezone.utc)
            )
            session.add.assert_called_once()
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_updates_existing_without_refresh(self):
        conn = ConfluenceConnection(id=1, company_id=1, status="pending")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = conn
            from services.confluence import _upsert_connection

            _upsert_connection(1, 1, "cloud", None, "AT", None, datetime.now(timezone.utc))
            assert conn.refresh_token is None
            assert conn.status == "ready"
        finally:
            patcher.stop()

# ── service: start_connect ─────────────────────────────────────────────────────

class TestStartConnect:
    def test_not_configured_503(self):
        from services.confluence import start_connect

        with patch("config.is_confluence_oauth_configured", return_value=False):
            with pytest.raises(HTTPException) as exc:
                start_connect(_user())
            assert exc.value.status_code == 503

    def test_configured_returns_url(self):
        from services.confluence import start_connect

        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("config.ATLASSIAN_CLIENT_ID", "cid"),
            patch("config.ATLASSIAN_REDIRECT_URI", "https://app/cb"),
            patch("config.ATLASSIAN_OAUTH_SCOPES", "scopeA"),
        ):
            out = start_connect(_user())
            assert "authorize_url" in out
            assert "client_id=cid" in out["authorize_url"]
            assert "scopeA" in out["authorize_url"]

# ── service: handle_callback ────────────────────────────────────────────────────

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
                return_value={"access_token": "AT", "refresh_token": "RT", "expires_in": 3600},
            ),
            patch(
                "services.confluence._fetch_accessible_resources",
                return_value=[{"id": "cloud1", "url": "https://x.atlassian.net"}],
            ),
            patch("services.confluence._upsert_connection") as up,
        ):
            from services.confluence import handle_callback

            redirect = handle_callback("code", self._state())
            assert redirect == config.CONFLUENCE_POST_CONNECT_REDIRECT
            up.assert_called_once()

    def test_not_configured_503(self):
        from services.confluence import handle_callback

        with patch("config.is_confluence_oauth_configured", return_value=False):
            with pytest.raises(HTTPException) as exc:
                handle_callback("code", "state")
            assert exc.value.status_code == 503

    def test_unknown_user_400(self):
        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("services.confluence.get_user_by_id", return_value=None),
        ):
            from services.confluence import handle_callback

            with pytest.raises(HTTPException) as exc:
                handle_callback("code", self._state(99))
            assert exc.value.status_code == 400

    def test_no_access_token_502(self):
        company = Company(id=5, name="locus.sh", domain="locus.sh")
        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("services.confluence.get_user_by_id", return_value=_user()),
            patch("services.confluence.get_or_create_company_for_user", return_value=company),
            patch("services.confluence._exchange_code", return_value={}),
        ):
            from services.confluence import handle_callback

            with pytest.raises(HTTPException) as exc:
                handle_callback("code", self._state())
            assert exc.value.status_code == 502

    def test_no_resources_400(self):
        company = Company(id=5, name="locus.sh", domain="locus.sh")
        with (
            patch("config.is_confluence_oauth_configured", return_value=True),
            patch("services.confluence.get_user_by_id", return_value=_user()),
            patch("services.confluence.get_or_create_company_for_user", return_value=company),
            patch("services.confluence._exchange_code", return_value={"access_token": "AT"}),
            patch("services.confluence._fetch_accessible_resources", return_value=[]),
        ):
            from services.confluence import handle_callback

            with pytest.raises(HTTPException) as exc:
                handle_callback("code", self._state())
            assert exc.value.status_code == 400

# ── service: get_status ─────────────────────────────────────────────────────────

class TestGetStatus:
    def _company(self):
        return Company(id=1, name="locus.sh", domain="locus.sh")

    def test_no_connection(self):
        with (
            patch(
                "services.confluence.get_or_create_company_for_user", return_value=self._company()
            ),
            patch("services.confluence._get_connection", return_value=None),
        ):
            from services.confluence import get_status

            s = get_status(_user())
            assert s["connected"] is False
            assert s["status"] is None

    def test_connection_not_ready(self):
        conn = ConfluenceConnection(id=1, company_id=1, status="pending")
        with (
            patch(
                "services.confluence.get_or_create_company_for_user", return_value=self._company()
            ),
            patch("services.confluence._get_connection", return_value=conn),
        ):
            from services.confluence import get_status

            s = get_status(_user())
            assert s["connected"] is False
            assert s["status"] == "pending"

    def test_ready_no_spaces(self):
        conn = ConfluenceConnection(
            id=1, company_id=1, status="ready", site_url="https://x.atlassian.net", space_keys=None
        )
        with (
            patch(
                "services.confluence.get_or_create_company_for_user", return_value=self._company()
            ),
            patch("services.confluence._get_connection", return_value=conn),
            patch("services.confluence._approved_doc_count", return_value=0),
        ):
            from services.confluence import get_status

            s = get_status(_user())
            assert s["connected"] is True
            assert s["space_count"] == 0
            assert s["doc_count"] == 0
            assert s["site_url"] == "https://x.atlassian.net"

    def test_ready_with_spaces(self):
        conn = ConfluenceConnection(
            id=1, company_id=1, status="ready", space_keys=json.dumps(["ENG", "PLAT"])
        )
        with (
            patch(
                "services.confluence.get_or_create_company_for_user", return_value=self._company()
            ),
            patch("services.confluence._get_connection", return_value=conn),
            patch("services.confluence._approved_doc_count", return_value=5),
        ):
            from services.confluence import get_status

            s = get_status(_user())
            assert s["space_count"] == 2
            assert s["doc_count"] == 5

    def test_approved_doc_count(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = [1, 2, 3]
            from services.confluence import _approved_doc_count

            assert _approved_doc_count(1) == 3
        finally:
            patcher.stop()

# ── routes ──────────────────────────────────────────────────────────────────────

class TestConfluenceRoutes:
    def test_connect_unauthenticated(self, anon_client):
        assert anon_client.post("/confluence/connect").status_code == 401

    def test_connect_success(self, auth_client):
        with patch(
            "controllers.confluence.confluence_service.start_connect",
            return_value={"authorize_url": "https://auth.atlassian.com/authorize?x=1"},
        ):
            resp = auth_client.post("/confluence/connect")
        assert resp.status_code == 200
        assert resp.json()["authorize_url"].startswith("https://auth.atlassian.com")

    def test_status_unauthenticated(self, anon_client):
        assert anon_client.get("/confluence/status").status_code == 401

    def test_status_success(self, auth_client):
        with patch(
            "controllers.confluence.confluence_service.get_status",
            return_value={
                "connected": True,
                "status": "ready",
                "site_url": "https://x",
                "space_count": 0,
            },
        ):
            resp = auth_client.get("/confluence/status")
        assert resp.status_code == 200
        assert resp.json()["connected"] is True

    def test_callback_redirects(self, anon_client):
        with patch(
            "controllers.confluence.confluence_service.handle_callback",
            return_value="/onboarding?connected=1",
        ):
            resp = anon_client.get(
                "/confluence/callback?code=abc&state=xyz", follow_redirects=False
            )
        assert resp.status_code in (302, 307)
        assert resp.headers["location"] == "/onboarding?connected=1"

    def test_callback_missing_params(self, anon_client):
        # No code/state → FastAPI validation error, still public (not 401).
        assert anon_client.get("/confluence/callback").status_code == 422

    def test_spaces_unauthenticated(self, anon_client):
        assert anon_client.get("/confluence/spaces").status_code == 401

    def test_spaces_success(self, auth_client):
        with patch(
            "controllers.confluence.confluence_service.list_spaces",
            return_value={
                "spaces": [{"key": "ENG", "name": "Engineering", "id": "1", "suggested": True}]
            },
        ):
            resp = auth_client.get("/confluence/spaces")
        assert resp.status_code == 200
        assert resp.json()["spaces"][0]["key"] == "ENG"

# ── REST client: token freshness ────────────────────────────────────────────────

class TestTokenFreshness:
    def test_expired_when_none(self):
        from services.confluence import _is_token_expired

        assert _is_token_expired(None) is True

    def test_not_expired_future(self):
        from services.confluence import _is_token_expired

        future = datetime.now(timezone.utc) + timedelta(hours=1)
        assert _is_token_expired(future) is False

    def test_expired_past_naive(self):
        from services.confluence import _is_token_expired

        past = datetime.utcnow() - timedelta(hours=1)  # naive
        assert _is_token_expired(past) is True

    def test_get_valid_token_uses_existing(self):
        from services.encryption import encrypt_secret
        from services.confluence import _get_valid_token

        conn = ConfluenceConnection(
            id=1,
            company_id=1,
            access_token=encrypt_secret("LIVE-TOKEN"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert _get_valid_token(conn) == "LIVE-TOKEN"

    def test_get_valid_token_refreshes_when_expired(self):
        from services.confluence import _get_valid_token

        conn = ConfluenceConnection(id=1, company_id=1, access_token="enc", token_expires_at=None)
        with patch("services.confluence._refresh_access_token", return_value="FRESH") as ref:
            assert _get_valid_token(conn) == "FRESH"
            ref.assert_called_once()

class TestRefreshAccessToken:
    def test_no_refresh_token_401(self):
        from services.confluence import _refresh_access_token

        conn = ConfluenceConnection(id=1, company_id=1, refresh_token=None)
        with pytest.raises(HTTPException) as exc:
            _refresh_access_token(conn)
        assert exc.value.status_code == 401

    def test_failure_marks_error_and_401(self):
        from services.encryption import encrypt_secret
        from services.confluence import _refresh_access_token

        conn = ConfluenceConnection(id=1, company_id=1, refresh_token=encrypt_secret("RT"))
        with (
            patch("services.confluence.httpx.post", return_value=_resp(400, {})),
            patch("services.confluence._mark_status") as mark,
        ):
            with pytest.raises(HTTPException) as exc:
                _refresh_access_token(conn)
            assert exc.value.status_code == 401
            mark.assert_called_once_with(1, "error")

    def test_success_persists_and_returns(self):
        from services.encryption import encrypt_secret
        from services.confluence import _refresh_access_token

        conn = ConfluenceConnection(id=1, company_id=1, refresh_token=encrypt_secret("RT"))
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = conn
            with patch(
                "services.confluence.httpx.post",
                return_value=_resp(
                    200, {"access_token": "NEW", "refresh_token": "NEWRT", "expires_in": 3600}
                ),
            ):
                assert _refresh_access_token(conn) == "NEW"
                session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_success_keeps_old_refresh_when_absent(self):
        from services.encryption import encrypt_secret
        from services.confluence import _refresh_access_token

        conn = ConfluenceConnection(id=1, company_id=1, refresh_token=encrypt_secret("RT"))
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = None  # nothing to persist branch
            with patch(
                "services.confluence.httpx.post",
                return_value=_resp(200, {"access_token": "NEW", "expires_in": 3600}),
            ):
                assert _refresh_access_token(conn) == "NEW"
        finally:
            patcher.stop()

class TestMarkStatus:
    def test_updates_when_present(self):
        conn = ConfluenceConnection(id=1, company_id=1, status="ready")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = conn
            from services.confluence import _mark_status

            _mark_status(1, "error")
            assert conn.status == "error"
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_noop_when_absent(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = None
            from services.confluence import _mark_status

            _mark_status(1, "error")
            session.commit.assert_not_called()
        finally:
            patcher.stop()

# ── REST client: fetch spaces ────────────────────────────────────────────────────

class TestFetchSpaces:
    def test_single_page(self):
        from services.confluence import _fetch_spaces

        with patch(
            "services.confluence.httpx.get",
            return_value=_resp(
                200, {"results": [{"space": {"key": "ENG", "name": "Engineering"}}]}
            ),
        ):
            spaces = _fetch_spaces("cloud1", "tok")
            assert len(spaces) == 1
            assert spaces[0]["key"] == "ENG"

    def test_skips_results_without_space(self):
        from services.confluence import _fetch_spaces

        with patch(
            "services.confluence.httpx.get",
            return_value=_resp(200, {"results": [{"title": "no space here"}]}),
        ):
            assert _fetch_spaces("cloud1", "tok") == []

    def test_skips_personal_spaces(self):
        from services.confluence import _fetch_spaces

        with patch(
            "services.confluence.httpx.get",
            return_value=_resp(
                200,
                {
                    "results": [
                        {"space": {"key": "ENG", "name": "Engineering"}},
                        {"space": {"key": "~712020abc", "name": "Someone"}},
                    ]
                },
            ),
        ):
            spaces = _fetch_spaces("cloud1", "tok")
            assert [s["key"] for s in spaces] == ["ENG"]

    def test_follows_next_cursor(self):
        from services.confluence import _fetch_spaces

        page1 = _resp(
            200,
            {"results": [{"space": {"key": "A"}}], "_links": {"next": "/rest/api/search?cursor=x"}},
        )
        page2 = _resp(200, {"results": [{"space": {"key": "B"}}], "_links": {}})
        with patch("services.confluence.httpx.get", side_effect=[page1, page2]):
            spaces = _fetch_spaces("cloud1", "tok")
            assert [s["key"] for s in spaces] == ["A", "B"]

    def test_failure_502(self):
        from services.confluence import _fetch_spaces

        with patch("services.confluence.httpx.get", return_value=_resp(403, {})):
            with pytest.raises(HTTPException) as exc:
                _fetch_spaces("cloud1", "tok")
            assert exc.value.status_code == 502

class TestSuggestedSpace:
    def test_matches_keyword(self):
        from services.confluence import _is_suggested_space

        assert _is_suggested_space("Platform Engineering", "PLAT") is True

    def test_no_match(self):
        from services.confluence import _is_suggested_space

        assert _is_suggested_space("Human Resources", "HR") is False

class TestListSpaces:
    def test_not_connected_409(self):
        with (
            patch(
                "services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="locus.sh", domain="locus.sh"),
            ),
            patch("services.confluence._get_connection", return_value=None),
        ):
            from services.confluence import list_spaces

            with pytest.raises(HTTPException) as exc:
                list_spaces(_user())
            assert exc.value.status_code == 409

    def test_success_flags_suggested(self):
        conn = ConfluenceConnection(
            id=1, company_id=1, status="ready", cloud_id="cloud1", access_token="enc"
        )
        raw = [
            {"key": "ENG", "name": "Engineering", "id": 1},
            {"key": "HR", "name": "Human Resources", "id": 2},
        ]
        with (
            patch(
                "services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="locus.sh", domain="locus.sh"),
            ),
            patch("services.confluence._get_connection", return_value=conn),
            patch("services.confluence._get_valid_token", return_value="tok"),
            patch("services.confluence._fetch_spaces", return_value=raw),
        ):
            from services.confluence import list_spaces

            out = list_spaces(_user())
            by_key = {s["key"]: s for s in out["spaces"]}
            assert by_key["ENG"]["suggested"] is True
            assert by_key["HR"]["suggested"] is False

# ── LLM classifier ──────────────────────────────────────────────────────────────

class TestClassifyOnboardingDoc:
    def test_success(self):
        from services.llm import classify_onboarding_doc

        resp = MagicMock()
        resp.model_dump.return_value = {
            "is_relevant": True,
            "role_tags": ["backend"],
            "confidence": 0.9,
        }
        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client") as build,
            patch("services.llm._token_kwargs", return_value={}),
        ):
            build.return_value.chat.completions.create.return_value = resp
            out = classify_onboarding_doc("Architecture", "excerpt", "openai", "k")
        assert out["is_relevant"] is True
        assert out["role_tags"] == ["backend"]

    def test_none_on_generic_exception(self):
        from services.llm import classify_onboarding_doc

        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client", side_effect=Exception("boom")),
            patch("services.llm._raise_if_provider_error"),
        ):
            assert classify_onboarding_doc("t", "x", "openai", "k") is None

    def test_reraises_http_exception(self):
        from services.llm import classify_onboarding_doc

        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client", side_effect=HTTPException(status_code=401)),
        ):
            with pytest.raises(HTTPException) as exc:
                classify_onboarding_doc("t", "x", "openai", "k")
            assert exc.value.status_code == 401

# ── funnel: helpers ───────────────────────────────────────────────────────────

class TestFunnelHelpers:
    def test_strip_html(self):
        from services.confluence import _strip_html

        assert _strip_html("<p>Hi <b>there</b></p>") == "Hi there"

    def test_page_labels(self):
        from services.confluence import _page_labels

        page = {"metadata": {"labels": {"results": [{"name": "onboarding"}, {"name": "eng"}]}}}
        assert _page_labels(page) == ["onboarding", "eng"]

    def test_page_labels_missing(self):
        from services.confluence import _page_labels

        assert _page_labels({}) == []

    def test_cheap_shortlist_keeps_matches(self):
        from services.confluence import _cheap_shortlist

        pages = [
            {"title": "Setup Guide", "id": 1},
            {"title": "Lunch menu", "id": 2},
        ]
        out = _cheap_shortlist(pages)
        assert [p["id"] for p in out] == [1]

    def test_cheap_shortlist_falls_back_to_all(self):
        from services.confluence import _cheap_shortlist

        pages = [{"title": "Xyz", "id": 1}, {"title": "Qpr", "id": 2}]
        assert len(_cheap_shortlist(pages)) == 2

    def test_require_ready_connection_ok(self):
        conn = ConfluenceConnection(id=1, company_id=1, status="ready", access_token="enc")
        with patch("services.confluence._get_connection", return_value=conn):
            from services.confluence import _require_ready_connection

            assert _require_ready_connection(1) is conn

    def test_require_ready_connection_409(self):
        with patch("services.confluence._get_connection", return_value=None):
            from services.confluence import _require_ready_connection

            with pytest.raises(HTTPException) as exc:
                _require_ready_connection(1)
            assert exc.value.status_code == 409

class TestSearchPages:
    def test_success(self):
        from services.confluence import _search_pages

        with patch(
            "services.confluence.httpx.get", return_value=_resp(200, {"results": [{"id": 1}]})
        ):
            assert _search_pages("cloud1", "tok", "ENG") == [{"id": 1}]

    def test_failure_502(self):
        from services.confluence import _search_pages

        with patch("services.confluence.httpx.get", return_value=_resp(500, {})):
            with pytest.raises(HTTPException) as exc:
                _search_pages("cloud1", "tok", "ENG")
            assert exc.value.status_code == 502

class TestExcerptFromPage:
    def test_extracts_version_and_text(self):
        from services.confluence import _excerpt_from_page

        page = {"version": {"number": 4}, "body": {"storage": {"value": "<p>Hi <b>there</b></p>"}}}
        version, text = _excerpt_from_page(page)
        assert version == 4
        assert text == "Hi there"

    def test_empty_page(self):
        from services.confluence import _excerpt_from_page

        assert _excerpt_from_page({}) == (None, "")

class TestFetchPageExcerpt:
    def test_success(self):
        from services.confluence import _fetch_page_excerpt

        payload = {
            "results": [
                {
                    "version": {"number": 3},
                    "body": {"storage": {"value": "<p>Hello <b>world</b></p>"}},
                }
            ]
        }
        with patch("services.confluence.httpx.get", return_value=_resp(200, payload)):
            version, text = _fetch_page_excerpt("cloud1", "tok", "p1")
        assert version == 3
        assert text == "Hello world"

    def test_no_results_returns_empty(self):
        from services.confluence import _fetch_page_excerpt

        with patch("services.confluence.httpx.get", return_value=_resp(200, {"results": []})):
            assert _fetch_page_excerpt("cloud1", "tok", "p1") == (None, "")

    def test_unreadable_returns_empty(self):
        from services.confluence import _fetch_page_excerpt

        with patch("services.confluence.httpx.get", return_value=_resp(404, {})):
            version, text = _fetch_page_excerpt("cloud1", "tok", "p1")
        assert version is None
        assert text == ""

class TestJobAndCandidatePersistence:
    def test_existing_page_ids(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = ["p1", "p2"]
            from services.confluence import _existing_page_ids

            assert _existing_page_ids(1) == {"p1", "p2"}
        finally:
            patcher.stop()

    def test_create_job_returns_id(self):
        patcher, session = _patch_session()
        try:
            session.refresh.side_effect = lambda job: setattr(job, "id", 5)
            from services.confluence import _create_job

            assert _create_job(1) == 5
        finally:
            patcher.stop()

    def test_update_job_updates(self):
        from models.ingestion_job import IngestionJob

        job = IngestionJob(id=1, company_id=1, status="running")
        patcher, session = _patch_session()
        try:
            session.get.return_value = job
            from services.confluence import _update_job

            _update_job(1, total=3, processed=3, status="failed", error="boom", completed=True)
            assert job.status == "failed"
            assert job.total_pages == 3
            assert job.error == "boom"
            assert job.completed_at is not None
        finally:
            patcher.stop()

    def test_update_job_missing_noop(self):
        patcher, session = _patch_session()
        try:
            session.get.return_value = None
            from services.confluence import _update_job

            _update_job(99, status="failed")
            session.commit.assert_not_called()
        finally:
            patcher.stop()

    def test_store_candidate(self):
        patcher, session = _patch_session()
        try:
            from services.confluence import _store_candidate

            _store_candidate(
                1,
                "p1",
                {"title": "Arch", "spaceKey": "ENG"},
                2,
                "text",
                {"role_tags": ["backend"], "confidence": 0.8},
            )
            session.add.assert_called_once()
            session.commit.assert_called_once()
        finally:
            patcher.stop()

# ── funnel: begin_ingest (schedule) ─────────────────────────────────────────────

class TestBeginIngest:
    def test_empty_spaces_400(self):
        from services.confluence import begin_ingest

        with pytest.raises(HTTPException) as exc:
            begin_ingest(_user(), [], "openai", "k", None, MagicMock())
        assert exc.value.status_code == 400

    def test_not_connected_409(self):
        with (
            patch(
                "services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch(
                "services.confluence._require_ready_connection",
                side_effect=HTTPException(status_code=409, detail="nope"),
            ),
        ):
            from services.confluence import begin_ingest

            with pytest.raises(HTTPException) as exc:
                begin_ingest(_user(), ["ENG"], "openai", "k", None, MagicMock())
            assert exc.value.status_code == 409

    def test_schedules_and_returns_running(self):
        bg = MagicMock()
        conn = ConfluenceConnection(
            id=1, company_id=1, status="ready", cloud_id="c", access_token="e"
        )
        with (
            patch(
                "services.confluence.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch("services.confluence._require_ready_connection", return_value=conn),
            patch("services.confluence._add_connected_spaces"),
            patch("services.confluence._create_job", return_value=7),
        ):
            from services.confluence import begin_ingest

            out = begin_ingest(_user(), ["ENG"], "openai", "k", None, bg)
        assert out == {"job_id": 7, "status": "running"}
        bg.add_task.assert_called_once()

# ── funnel: _run_ingest (worker) ─────────────────────────────────────────────────

class TestRunIngest:
    def _conn(self):
        return ConfluenceConnection(
            id=1, company_id=1, status="ready", cloud_id="cloud1", access_token="enc"
        )

    def test_success_stores_relevant(self):
        pages = [{"id": "p1", "title": "Architecture Guide"}, {"id": "p2", "title": "Setup"}]
        with (
            patch("services.confluence._get_connection", return_value=self._conn()),
            patch("services.confluence._get_valid_token", return_value="tok"),
            patch("services.confluence._search_pages", return_value=pages),
            patch("services.confluence._existing_page_ids", return_value=set()),
            patch("services.confluence._fetch_page_excerpt", return_value=(1, "excerpt")),
            patch(
                "services.confluence.llm_service.classify_onboarding_doc",
                return_value={"is_relevant": True, "role_tags": ["backend"], "confidence": 0.9},
            ),
            patch("services.confluence._store_candidate") as store,
            patch("services.confluence._update_job") as upd,
        ):
            from services.confluence import _run_ingest

            _run_ingest(1, ["ENG"], "openai", "k", None, 7)
        assert store.call_count == 2
        assert any(c.kwargs.get("status") == "done" for c in upd.call_args_list)

    def test_skips_existing_and_irrelevant(self):
        pages = [{"id": "p1", "title": "Setup"}, {"id": "p2", "title": "Setup"}]
        with (
            patch("services.confluence._get_connection", return_value=self._conn()),
            patch("services.confluence._get_valid_token", return_value="tok"),
            patch("services.confluence._search_pages", return_value=pages),
            patch("services.confluence._existing_page_ids", return_value={"p1"}),
            patch("services.confluence._fetch_page_excerpt", return_value=(1, "x")),
            patch(
                "services.confluence.llm_service.classify_onboarding_doc",
                return_value={"is_relevant": False},
            ),
            patch("services.confluence._store_candidate") as store,
            patch("services.confluence._update_job"),
        ):
            from services.confluence import _run_ingest

            _run_ingest(1, ["ENG"], "openai", "k", None, 7)
        store.assert_not_called()

    def test_no_connection_marks_failed(self):
        with (
            patch("services.confluence._get_connection", return_value=None),
            patch("services.confluence._update_job") as upd,
        ):
            from services.confluence import _run_ingest

            _run_ingest(1, ["ENG"], "openai", "k", None, 7)
        assert upd.call_args_list[-1].kwargs.get("status") == "failed"

    def test_search_failure_marks_failed(self):
        with (
            patch("services.confluence._get_connection", return_value=self._conn()),
            patch("services.confluence._get_valid_token", return_value="tok"),
            patch(
                "services.confluence._search_pages",
                side_effect=HTTPException(status_code=502, detail="boom"),
            ),
            patch("services.confluence._update_job") as upd,
        ):
            from services.confluence import _run_ingest

            _run_ingest(1, ["ENG"], "openai", "k", None, 7)
        last = upd.call_args_list[-1].kwargs
        assert last.get("status") == "failed"
        assert "boom" in (last.get("error") or "")

class TestIngestStatus:
    def test_found(self):
        from models.ingestion_job import IngestionJob

        job = IngestionJob(id=7, company_id=1, status="running", total_pages=10, processed_pages=4)
        with patch(
            "services.confluence.get_or_create_company_for_user",
            return_value=Company(id=1, name="a", domain="a"),
        ):
            patcher, session = _patch_session()
            try:
                session.get.return_value = job
                from services.confluence import get_ingest_status

                out = get_ingest_status(_user(), 7)
                assert out["processed_pages"] == 4
                assert out["status"] == "running"
            finally:
                patcher.stop()

    def test_wrong_company_404(self):
        from models.ingestion_job import IngestionJob

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

# ── funnel: candidates ─────────────────────────────────────────────────────────

class TestCandidates:
    def test_candidate_dump(self):
        from models.onboarding_doc import OnboardingDoc
        from services.confluence import _candidate_dump

        doc = OnboardingDoc(
            id=3,
            company_id=1,
            confluence_page_id="p1",
            title="Arch",
            space_key="ENG",
            role_tags=json.dumps(["backend"]),
            confidence=0.8,
        )
        out = _candidate_dump(doc)
        assert out["page_id"] == "p1"
        assert out["role_tags"] == ["backend"]

    def test_get_candidates(self):
        from models.onboarding_doc import OnboardingDoc

        doc = OnboardingDoc(id=1, company_id=1, confluence_page_id="p1", title="Arch")
        with patch(
            "services.confluence.get_or_create_company_for_user",
            return_value=Company(id=1, name="a", domain="a"),
        ):
            patcher, session = _patch_session()
            try:
                session.exec.return_value.all.return_value = [doc]
                from services.confluence import get_candidates

                out = get_candidates(_user())
                assert len(out["candidates"]) == 1
            finally:
                patcher.stop()

    def test_confirm_empty_400(self):
        from services.confluence import confirm_candidates

        with pytest.raises(HTTPException) as exc:
            confirm_candidates(_user(), [])
        assert exc.value.status_code == 400

    def test_confirm_approves(self):
        from models.onboarding_doc import OnboardingDoc

        docs = [
            OnboardingDoc(id=1, company_id=1, confluence_page_id="p1", title="A", approved=False),
            OnboardingDoc(id=2, company_id=1, confluence_page_id="p2", title="B", approved=False),
        ]
        with patch(
            "services.confluence.get_or_create_company_for_user",
            return_value=Company(id=1, name="a", domain="a"),
        ):
            patcher, session = _patch_session()
            try:
                session.exec.return_value.all.return_value = docs
                from services.confluence import confirm_candidates

                out = confirm_candidates(_user(), ["p1", "p2"])
                assert out["approved"] == 2
                assert all(d.approved for d in docs)
            finally:
                patcher.stop()

# ── funnel: routes ─────────────────────────────────────────────────────────────

class TestFunnelRoutes:
    def test_ingest_unauthenticated(self, anon_client):
        assert (
            anon_client.post("/confluence/ingest", json={"space_keys": ["ENG"]}).status_code == 401
        )

    def test_ingest_success(self, auth_client):
        with (
            patch("controllers.confluence.get_user_provider_name", return_value="openai"),
            patch("controllers.confluence.get_user_api_key", return_value="k"),
            patch("controllers.confluence.get_user_model", return_value=None),
            patch(
                "controllers.confluence.confluence_service.begin_ingest",
                return_value={"job_id": 1, "status": "running"},
            ),
        ):
            resp = auth_client.post("/confluence/ingest", json={"space_keys": ["ENG"]})
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_ingest_status_unauthenticated(self, anon_client):
        assert anon_client.get("/confluence/ingest/1").status_code == 401

    def test_ingest_status_success(self, auth_client):
        with patch(
            "controllers.confluence.confluence_service.get_ingest_status",
            return_value={
                "job_id": 1,
                "status": "done",
                "total_pages": 5,
                "processed_pages": 5,
                "error": None,
            },
        ):
            resp = auth_client.get("/confluence/ingest/1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "done"

    def test_candidates_get(self, auth_client):
        with patch(
            "controllers.confluence.confluence_service.get_candidates",
            return_value={"candidates": []},
        ):
            resp = auth_client.get("/confluence/candidates")
        assert resp.status_code == 200
        assert resp.json() == {"candidates": []}

    def test_candidates_confirm(self, auth_client):
        with patch(
            "controllers.confluence.confluence_service.confirm_candidates",
            return_value={"approved": 2},
        ):
            resp = auth_client.patch("/confluence/candidates", json={"page_ids": ["p1", "p2"]})
        assert resp.status_code == 200
        assert resp.json()["approved"] == 2

# ── webhooks ──────────────────────────────────────────────────────────────────

class TestVerifyWebhookSecret:
    def test_not_configured_503(self):
        from services.confluence import verify_webhook_secret

        with patch("config.CONFLUENCE_WEBHOOK_SECRET", None):
            with pytest.raises(HTTPException) as exc:
                verify_webhook_secret("anything")
            assert exc.value.status_code == 503

    def test_mismatch_401(self):
        from services.confluence import verify_webhook_secret

        with patch("config.CONFLUENCE_WEBHOOK_SECRET", "right"):
            with pytest.raises(HTTPException) as exc:
                verify_webhook_secret("wrong")
            assert exc.value.status_code == 401

    def test_ok(self):
        from services.confluence import verify_webhook_secret

        with patch("config.CONFLUENCE_WEBHOOK_SECRET", "right"):
            verify_webhook_secret("right")  # no raise

class TestWebhookHelpers:
    def test_docs_by_page_id(self):
        from models.onboarding_doc import OnboardingDoc

        doc = OnboardingDoc(id=1, company_id=1, confluence_page_id="p1", title="t")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = [doc]
            from services.confluence import _docs_by_page_id

            assert _docs_by_page_id("p1") == [doc]
        finally:
            patcher.stop()

    def test_connection_by_cloud_id(self):
        conn = ConfluenceConnection(id=1, company_id=1, cloud_id="c1")
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = conn
            from services.confluence import _connection_by_cloud_id

            assert _connection_by_cloud_id("c1") is conn
        finally:
            patcher.stop()

    def test_update_doc_content(self):
        from models.onboarding_doc import OnboardingDoc

        doc = OnboardingDoc(id=1, company_id=1, confluence_page_id="p1", title="t", is_active=False)
        patcher, session = _patch_session()
        try:
            session.get.return_value = doc
            from services.confluence import _update_doc_content

            _update_doc_content(1, 5, "new text")
            assert doc.confluence_version == 5
            assert doc.content_markdown == "new text"
            assert doc.is_active is True
        finally:
            patcher.stop()

    def test_update_doc_content_missing_noop(self):
        patcher, session = _patch_session()
        try:
            session.get.return_value = None
            from services.confluence import _update_doc_content

            _update_doc_content(99, 1, "x")
            session.commit.assert_not_called()
        finally:
            patcher.stop()

    def test_deactivate_docs(self):
        from models.onboarding_doc import OnboardingDoc

        docs = [
            OnboardingDoc(id=1, company_id=1, confluence_page_id="p1", title="t", is_active=True)
        ]
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = docs
            from services.confluence import _deactivate_docs

            assert _deactivate_docs("p1") == 1
            assert docs[0].is_active is False
        finally:
            patcher.stop()

    def test_admin_creds_none_user(self):
        from services.confluence import _admin_llm_creds

        assert _admin_llm_creds(None) is None

    def test_admin_creds_user_missing(self):
        from services.confluence import _admin_llm_creds

        with patch("services.confluence.get_user_by_id", return_value=None):
            assert _admin_llm_creds(7) is None

    def test_admin_creds_success(self):
        from services.confluence import _admin_llm_creds

        with (
            patch("services.confluence.get_user_by_id", return_value=_user()),
            patch("services.confluence.get_user_provider_name", return_value="openai"),
            patch("services.confluence.get_user_api_key", return_value="k"),
            patch("services.confluence.get_user_model", return_value=None),
        ):
            assert _admin_llm_creds(7) == ("openai", "k", None)

    def test_admin_creds_raises_returns_none(self):
        from services.confluence import _admin_llm_creds

        with (
            patch("services.confluence.get_user_by_id", return_value=_user()),
            patch(
                "services.confluence.get_user_provider_name",
                side_effect=HTTPException(status_code=400),
            ),
        ):
            assert _admin_llm_creds(7) is None

class TestHandleWebhook:
    def test_unknown_event_ignored(self):
        from services.confluence import handle_webhook

        assert handle_webhook({"event": "label_added"})["status"] == "ignored"

    def test_updated_no_page_ignored(self):
        from services.confluence import handle_webhook

        assert handle_webhook({"event": "page_updated"})["status"] == "ignored"

    def test_removed_no_page_ignored(self):
        from services.confluence import handle_webhook

        assert handle_webhook({"event": "page_removed"})["status"] == "ignored"

    def test_removed_dispatch(self):
        from services.confluence import handle_webhook

        with patch(
            "services.confluence._handle_page_removed", return_value={"status": "removed"}
        ) as h:
            out = handle_webhook({"event": "page_removed", "page": {"id": "p1"}})
            assert out["status"] == "removed"
            h.assert_called_once_with("p1")

    def test_updated_dispatch(self):
        from services.confluence import handle_webhook

        with patch(
            "services.confluence._handle_page_updated", return_value={"status": "updated"}
        ) as h:
            handle_webhook({"event": "page_updated", "page": {"id": "p1"}})
            h.assert_called_once_with("p1")

    def test_created_dispatch(self):
        from services.confluence import handle_webhook

        with patch(
            "services.confluence._handle_page_created", return_value={"status": "added"}
        ) as h:
            handle_webhook({"event": "page_created", "page": {"id": "p1"}, "cloudId": "c1"})
            h.assert_called_once()

class TestHandlePageUpdated:
    def test_no_docs_ignored(self):
        from services.confluence import _handle_page_updated

        with patch("services.confluence._docs_by_page_id", return_value=[]):
            assert _handle_page_updated("p1")["status"] == "ignored"

    def test_updates_tracked_doc(self):
        from models.onboarding_doc import OnboardingDoc

        doc = OnboardingDoc(id=1, company_id=1, confluence_page_id="p1", title="t")
        conn = ConfluenceConnection(
            id=1, company_id=1, status="ready", cloud_id="c", access_token="e"
        )
        with (
            patch("services.confluence._docs_by_page_id", return_value=[doc]),
            patch("services.confluence._get_connection", return_value=conn),
            patch("services.confluence._get_valid_token", return_value="tok"),
            patch("services.confluence._fetch_page_excerpt", return_value=(3, "text")),
            patch("services.confluence._update_doc_content") as upd,
        ):
            from services.confluence import _handle_page_updated

            assert _handle_page_updated("p1")["status"] == "updated"
            upd.assert_called_once()

    def test_skips_doc_without_connection(self):
        from models.onboarding_doc import OnboardingDoc

        doc = OnboardingDoc(id=1, company_id=1, confluence_page_id="p1", title="t")
        with (
            patch("services.confluence._docs_by_page_id", return_value=[doc]),
            patch("services.confluence._get_connection", return_value=None),
            patch("services.confluence._update_doc_content") as upd,
        ):
            from services.confluence import _handle_page_updated

            assert _handle_page_updated("p1")["status"] == "updated"
            upd.assert_not_called()

class TestHandlePageRemoved:
    def test_removed(self):
        from services.confluence import _handle_page_removed

        with patch("services.confluence._deactivate_docs", return_value=2):
            assert _handle_page_removed("p1")["status"] == "removed"

    def test_untracked_ignored(self):
        from services.confluence import _handle_page_removed

        with patch("services.confluence._deactivate_docs", return_value=0):
            assert _handle_page_removed("p1")["status"] == "ignored"

class TestHandlePageCreated:
    def _payload(self):
        return {"event": "page_created", "page": {"id": "p9", "title": "New Doc"}, "cloudId": "c1"}

    def test_missing_cloud_id_ignored(self):
        from services.confluence import _handle_page_created

        assert _handle_page_created({"page": {"id": "p9"}})["status"] == "ignored"

    def test_no_connection_ignored(self):
        from services.confluence import _handle_page_created

        with patch("services.confluence._connection_by_cloud_id", return_value=None):
            assert _handle_page_created(self._payload())["status"] == "ignored"

    def test_existing_skipped(self):
        conn = ConfluenceConnection(
            id=1, company_id=1, cloud_id="c1", access_token="e", connected_by_user_id=7
        )
        with (
            patch("services.confluence._connection_by_cloud_id", return_value=conn),
            patch("services.confluence._existing_page_ids", return_value={"p9"}),
        ):
            from services.confluence import _handle_page_created

            assert _handle_page_created(self._payload())["status"] == "exists"

    def test_no_creds_skipped(self):
        conn = ConfluenceConnection(
            id=1, company_id=1, cloud_id="c1", access_token="e", connected_by_user_id=7
        )
        with (
            patch("services.confluence._connection_by_cloud_id", return_value=conn),
            patch("services.confluence._existing_page_ids", return_value=set()),
            patch("services.confluence._admin_llm_creds", return_value=None),
        ):
            from services.confluence import _handle_page_created

            assert _handle_page_created(self._payload())["status"] == "skipped_no_creds"

    def test_relevant_added(self):
        conn = ConfluenceConnection(
            id=1, company_id=1, cloud_id="c1", access_token="e", connected_by_user_id=7
        )
        with (
            patch("services.confluence._connection_by_cloud_id", return_value=conn),
            patch("services.confluence._existing_page_ids", return_value=set()),
            patch("services.confluence._admin_llm_creds", return_value=("openai", "k", None)),
            patch("services.confluence._get_valid_token", return_value="tok"),
            patch("services.confluence._fetch_page_excerpt", return_value=(1, "text")),
            patch(
                "services.confluence.llm_service.classify_onboarding_doc",
                return_value={"is_relevant": True, "role_tags": ["backend"], "confidence": 0.9},
            ),
            patch("services.confluence._store_candidate") as store,
        ):
            from services.confluence import _handle_page_created

            assert _handle_page_created(self._payload())["status"] == "added"
            store.assert_called_once()

    def test_not_relevant(self):
        conn = ConfluenceConnection(
            id=1, company_id=1, cloud_id="c1", access_token="e", connected_by_user_id=7
        )
        with (
            patch("services.confluence._connection_by_cloud_id", return_value=conn),
            patch("services.confluence._existing_page_ids", return_value=set()),
            patch("services.confluence._admin_llm_creds", return_value=("openai", "k", None)),
            patch("services.confluence._get_valid_token", return_value="tok"),
            patch("services.confluence._fetch_page_excerpt", return_value=(1, "text")),
            patch(
                "services.confluence.llm_service.classify_onboarding_doc",
                return_value={"is_relevant": False},
            ),
            patch("services.confluence._store_candidate") as store,
        ):
            from services.confluence import _handle_page_created

            assert _handle_page_created(self._payload())["status"] == "not_relevant"
            store.assert_not_called()

class TestWebhookRoute:
    def test_missing_secret_401(self, anon_client):
        with patch("config.CONFLUENCE_WEBHOOK_SECRET", "right"):
            resp = anon_client.post("/webhooks/confluence", json={"event": "page_updated"})
        assert resp.status_code == 401

    def test_success_with_header(self, anon_client):
        with (
            patch("config.CONFLUENCE_WEBHOOK_SECRET", "right"),
            patch(
                "controllers.confluence.confluence_service.handle_webhook",
                return_value={"status": "ok"},
            ),
        ):
            resp = anon_client.post(
                "/webhooks/confluence",
                json={"event": "page_updated", "page": {"id": "p1"}},
                headers={"X-Webhook-Secret": "right"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_success_with_query_secret(self, anon_client):
        with (
            patch("config.CONFLUENCE_WEBHOOK_SECRET", "right"),
            patch(
                "controllers.confluence.confluence_service.handle_webhook",
                return_value={"status": "ok"},
            ),
        ):
            resp = anon_client.post(
                "/webhooks/confluence?secret=right",
                json={"event": "page_removed", "page": {"id": "p1"}},
            )
        assert resp.status_code == 200

# ── reconciliation & gap detection ──────────────────────────────────────────────

class TestKeywordMatchPages:
    def test_matches_only(self):
        from services.confluence import _keyword_match_pages

        pages = [{"title": "Setup Guide", "id": 1}, {"title": "Lunch", "id": 2}]
        assert [p["id"] for p in _keyword_match_pages(pages)] == [1]

    def test_empty_when_none(self):
        from services.confluence import _keyword_match_pages

        assert _keyword_match_pages([{"title": "Xyz", "id": 1}]) == []

class TestAddConnectedSpaces:
    def test_merges_union(self):
        conn = ConfluenceConnection(id=1, company_id=1, space_keys=json.dumps(["ENG"]))
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = conn
            from services.confluence import _add_connected_spaces

            _add_connected_spaces(1, ["PLAT", "ENG"])
            assert sorted(json.loads(conn.space_keys)) == ["ENG", "PLAT"]
        finally:
            patcher.stop()

    def test_no_connection_noop(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.first.return_value = None
            from services.confluence import _add_connected_spaces

            _add_connected_spaces(1, ["ENG"])
            session.commit.assert_not_called()
        finally:
            patcher.stop()

class TestReconcileCompany:
    def test_not_connected_409(self):
        with patch("services.confluence._get_connection", return_value=None):
            from services.confluence import reconcile_company

            with pytest.raises(HTTPException) as exc:
                reconcile_company(1)
            assert exc.value.status_code == 409

    def test_no_spaces_noop(self):
        conn = ConfluenceConnection(
            id=1, company_id=1, status="ready", access_token="e", space_keys=None
        )
        with patch("services.confluence._get_connection", return_value=conn):
            from services.confluence import reconcile_company

            assert reconcile_company(1) == {"deactivated": 0, "reactivated": 0}

    def test_deactivates_and_reactivates(self):
        from models.onboarding_doc import OnboardingDoc

        conn = ConfluenceConnection(
            id=1,
            company_id=1,
            status="ready",
            cloud_id="c",
            access_token="e",
            space_keys=json.dumps(["ENG"]),
        )
        vanished = OnboardingDoc(
            id=1, company_id=1, confluence_page_id="gone", title="t", is_active=True
        )
        returned = OnboardingDoc(
            id=2, company_id=1, confluence_page_id="p1", title="t", is_active=False
        )
        with (
            patch("services.confluence._get_connection", return_value=conn),
            patch("services.confluence._get_valid_token", return_value="tok"),
            patch("services.confluence._search_pages", return_value=[{"id": "p1"}]),
        ):
            patcher, session = _patch_session()
            try:
                session.exec.return_value.all.return_value = [vanished, returned]
                from services.confluence import reconcile_company

                out = reconcile_company(1)
                assert out == {"deactivated": 1, "reactivated": 1}
                assert vanished.is_active is False
                assert returned.is_active is True
            finally:
                patcher.stop()

class TestDetectGaps:
    def test_flags_unconnected_spaces(self):
        company = Company(id=1, name="a", domain="a")
        conn = ConfluenceConnection(
            id=1,
            company_id=1,
            status="ready",
            cloud_id="c",
            access_token="e",
            space_keys=json.dumps(["ENG"]),
        )
        spaces = [{"key": "ENG", "name": "Engineering"}, {"key": "HR", "name": "Human Resources"}]
        with (
            patch("services.confluence.get_or_create_company_for_user", return_value=company),
            patch("services.confluence._require_ready_connection", return_value=conn),
            patch("services.confluence._get_valid_token", return_value="tok"),
            patch("services.confluence._fetch_spaces", return_value=spaces),
            patch(
                "services.confluence._search_pages",
                return_value=[{"title": "Setup Guide", "id": 9}],
            ),
        ):
            from services.confluence import detect_gaps

            out = detect_gaps(_user())
            assert out["total"] == 1
            assert out["gaps"][0]["space_key"] == "HR"

class TestReconcileGapsRoutes:
    def test_reconcile_unauthenticated(self, anon_client):
        assert anon_client.post("/confluence/reconcile").status_code == 401

    def test_reconcile_success(self, auth_client):
        with (
            patch(
                "controllers.confluence.confluence_service.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch(
                "controllers.confluence.confluence_service.reconcile_company",
                return_value={"deactivated": 2, "reactivated": 0},
            ),
        ):
            resp = auth_client.post("/confluence/reconcile")
        assert resp.status_code == 200
        assert resp.json()["deactivated"] == 2

    def test_gaps_unauthenticated(self, anon_client):
        assert anon_client.get("/confluence/gaps").status_code == 401

    def test_gaps_success(self, auth_client):
        with patch(
            "controllers.confluence.confluence_service.detect_gaps",
            return_value={"gaps": [], "total": 0},
        ):
            resp = auth_client.get("/confluence/gaps")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
