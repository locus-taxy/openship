from unittest.mock import MagicMock, patch
import pytest
from services.user import (
    get_user_by_id,
    get_user_by_email,
    create_user,
    get_provider_key,
    get_all_saved_provider_ids,
    update_llm_settings,
)
from services.encryption import encrypt_api_key
from models.user import User
from models.user_api_key import UserApiKey

def _patch_session(session_mock):
    patcher = patch("services.user.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

class TestGetUserById:
    def test_returns_user_when_found(self):
        user = User(id=1, email="test@example.com", name="Test", hashed_password="$2b$hash")
        session = MagicMock()
        session.get.return_value = user
        patcher = _patch_session(session)
        try:
            result = get_user_by_id(1)
            assert result is user
        finally:
            patcher.stop()

    def test_returns_none_when_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            result = get_user_by_id(999)
            assert result is None
        finally:
            patcher.stop()

class TestGetUserByEmail:
    def test_returns_user_when_found(self):
        user = User(id=1, email="test@example.com", name="Test", hashed_password="$2b$hash")
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = user
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_user_by_email("test@example.com")
            assert result is user
        finally:
            patcher.stop()

    def test_returns_none_when_not_found(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_user_by_email("missing@example.com")
            assert result is None
        finally:
            patcher.stop()

class TestCreateUser:
    def test_hashes_password(self):
        session = MagicMock()
        patcher = _patch_session(session)
        try:
            with patch("services.user.get_or_create_company", return_value=MagicMock(id=1)):
                create_user("new@example.com", "New User", "plainpassword")
            added = session.add.call_args[0][0]
            assert added.hashed_password != "plainpassword"
            assert added.hashed_password.startswith("$2b$")
        finally:
            patcher.stop()

    def test_sets_email_name_and_company(self):
        session = MagicMock()
        patcher = _patch_session(session)
        try:
            with patch("services.user.get_or_create_company", return_value=MagicMock(id=42)):
                create_user("new@example.com", "New User", "pass")
            added = session.add.call_args[0][0]
            assert added.email == "new@example.com"
            assert added.name == "New User"
            assert added.company_id == 42  # linked at signup
        finally:
            patcher.stop()

class TestGetProviderKey:
    def test_returns_none_when_no_record(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_provider_key(1, 2)
            assert result is None
        finally:
            patcher.stop()

    def test_decrypts_stored_key(self):
        raw_key = "sk-test-api-key-12345"
        encrypted = encrypt_api_key(raw_key)
        record = MagicMock(spec=UserApiKey)
        record.api_key = encrypted

        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = record
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_provider_key(1, 1)
            assert result == raw_key
        finally:
            patcher.stop()

class TestGetAllSavedProviderIds:
    def test_returns_set_of_provider_ids(self):
        records = [MagicMock(llm_provider_id=1), MagicMock(llm_provider_id=2)]
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = records
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_all_saved_provider_ids(1)
            assert result == {1, 2}
        finally:
            patcher.stop()

    def test_returns_empty_set_when_no_keys(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_all_saved_provider_ids(1)
            assert result == set()
        finally:
            patcher.stop()
