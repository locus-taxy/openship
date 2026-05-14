import time
import pytest
from fastapi import HTTPException
from services.jwt import create_access_token, create_refresh_token, decode_token

class TestCreateAccessToken:
    def test_returns_string(self):
        assert isinstance(create_access_token(1), str)

    def test_payload_sub_is_user_id(self):
        token = create_access_token(42)
        payload = decode_token(token)
        assert payload["sub"] == "42"

    def test_payload_type_is_access(self):
        token = create_access_token(1)
        payload = decode_token(token)
        assert payload["type"] == "access"

    def test_different_users_produce_different_tokens(self):
        assert create_access_token(1) != create_access_token(2)

class TestCreateRefreshToken:
    def test_returns_string(self):
        assert isinstance(create_refresh_token(1), str)

    def test_payload_type_is_refresh(self):
        token = create_refresh_token(1)
        payload = decode_token(token)
        assert payload["type"] == "refresh"

    def test_payload_sub_is_user_id(self):
        token = create_refresh_token(99)
        payload = decode_token(token)
        assert payload["sub"] == "99"

class TestDecodeToken:
    def test_valid_token_returns_payload(self):
        token = create_access_token(5)
        payload = decode_token(token)
        assert payload["sub"] == "5"

    def test_invalid_token_raises_401(self):
        with pytest.raises(HTTPException) as exc:
            decode_token("totally.invalid.token")
        assert exc.value.status_code == 401

    def test_malformed_token_raises_401(self):
        with pytest.raises(HTTPException) as exc:
            decode_token("not-a-jwt-at-all")
        assert exc.value.status_code == 401

    def test_tampered_token_raises_401(self):
        token = create_access_token(1)
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(HTTPException) as exc:
            decode_token(tampered)
        assert exc.value.status_code == 401

    def test_expired_token_raises_401_with_expired_detail(self):
        import jwt as pyjwt
        from datetime import datetime, timezone
        from config import JWT_SECRET_KEY, JWT_ALGORITHM

        expired_payload = {"sub": "1", "exp": datetime(2020, 1, 1, tzinfo=timezone.utc)}
        expired_token = pyjwt.encode(expired_payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        with pytest.raises(HTTPException) as exc:
            decode_token(expired_token)
        assert exc.value.status_code == 401
        assert "expired" in exc.value.detail.lower()
