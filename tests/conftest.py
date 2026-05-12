import os
import secrets

from cryptography.fernet import Fernet

# Must be set BEFORE any project imports — config.py raises RuntimeError on missing vars.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
os.environ.setdefault("JWT_SECRET_KEY", secrets.token_hex(32))
os.environ.setdefault("LLM_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("RUN_MIGRATIONS_ON_STARTUP", "false")
os.environ.setdefault("SMTP_HOST", "")

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

@pytest.fixture(scope="session")
def test_user():
    from models.user import User

    return User(
        id=1,
        email="test@example.com",
        name="Test User",
        is_active=True,
        hashed_password="$2b$12$placeholder",
        llm_provider_id=None,
    )

@pytest.fixture(scope="session")
def app():
    from main import app as _app

    return _app

@pytest.fixture
def auth_client(app, test_user):
    """TestClient with valid JWT cookie and mocked DB user lookup."""
    from services.jwt import create_access_token

    token = create_access_token(test_user.id)
    with patch("middleware.auth.get_user_by_id", return_value=test_user):
        with TestClient(app, raise_server_exceptions=False) as client:
            client.cookies.set("access_token", token)
            yield client

@pytest.fixture
def anon_client(app):
    """TestClient with no auth cookie."""
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

def make_mock_session(get_return=None, exec_first=None, exec_all=None):
    """Helper to build a mock SQLModel session."""
    session = MagicMock()
    session.get.return_value = get_return
    mock_exec = MagicMock()
    mock_exec.first.return_value = exec_first
    mock_exec.all.return_value = exec_all if exec_all is not None else []
    session.exec.return_value = mock_exec
    return session
