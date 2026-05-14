from unittest.mock import patch, MagicMock
import pytest
from fastapi import HTTPException
from controllers.syllabus import (
    list_syllabi,
    get_syllabus,
    delete_syllabus,
    toggle_share,
    get_public_syllabus,
    search,
)
from models.user import User

def _make_user(user_id=1):
    return User(
        id=user_id,
        email="test@example.com",
        name="Test",
        is_active=True,
        hashed_password="$2b$hash",
    )

def _sample_detail(user_id="1"):
    return {
        "_user_id": user_id,
        "skill_id": 1,
        "skill": "Python",
        "days": 30,
        "months": [],
    }

class TestListSyllabi:
    def test_calls_get_all_syllabi(self):
        user = _make_user()
        with patch("controllers.syllabus.get_all_syllabi", return_value=[]) as mock:
            result = list_syllabi(user)
        mock.assert_called_once_with(email="test@example.com")
        assert result == []

class TestGetSyllabus:
    def test_raises_404_when_not_found(self):
        user = _make_user()
        with patch("controllers.syllabus.get_syllabus_detail", return_value=None):
            with pytest.raises(HTTPException) as exc:
                get_syllabus(999, user)
            assert exc.value.status_code == 404

    def test_raises_403_when_not_owner(self):
        user = _make_user(user_id=1)
        detail = _sample_detail(user_id="999")
        with patch("controllers.syllabus.get_syllabus_detail", return_value=detail):
            with pytest.raises(HTTPException) as exc:
                get_syllabus(1, user)
            assert exc.value.status_code == 403

    def test_returns_detail_for_owner(self):
        user = _make_user(user_id=1)
        detail = _sample_detail(user_id="1")
        with patch("controllers.syllabus.get_syllabus_detail", return_value=detail):
            result = get_syllabus(1, user)
        assert result["skill"] == "Python"
        assert "_user_id" not in result

class TestDeleteSyllabus:
    def test_raises_404_when_not_found_or_not_owned(self):
        user = _make_user()
        with patch("controllers.syllabus.delete_skill", return_value=False):
            with pytest.raises(HTTPException) as exc:
                delete_syllabus(999, user)
            assert exc.value.status_code == 404

    def test_success_returns_status(self):
        user = _make_user()
        with patch("controllers.syllabus.delete_skill", return_value=True):
            result = delete_syllabus(1, user)
        assert result["status"] == "success"

class TestToggleShare:
    def test_raises_404_when_not_found(self):
        user = _make_user()
        with patch("controllers.syllabus.toggle_skill_share", return_value=None):
            with pytest.raises(HTTPException) as exc:
                toggle_share(999, True, user)
            assert exc.value.status_code == 404

    def test_enable_returns_share_enabled_true(self):
        user = _make_user()
        with patch("controllers.syllabus.toggle_skill_share", return_value=True):
            result = toggle_share(1, True, user)
        assert result["share_enabled"] is True

    def test_disable_returns_share_enabled_false(self):
        user = _make_user()
        with patch("controllers.syllabus.toggle_skill_share", return_value=False):
            result = toggle_share(1, False, user)
        assert result["share_enabled"] is False

class TestGetPublicSyllabus:
    def test_raises_404_when_not_found(self):
        with patch("controllers.syllabus.get_public_syllabus_detail", return_value=None):
            with pytest.raises(HTTPException) as exc:
                get_public_syllabus(999)
            assert exc.value.status_code == 404

    def test_returns_public_detail(self):
        detail = {"skill_id": 1, "skill": "Python", "share_enabled": True}
        with patch("controllers.syllabus.get_public_syllabus_detail", return_value=detail):
            result = get_public_syllabus(1)
        assert result["skill"] == "Python"

class TestSearch:
    def test_empty_query_returns_all_syllabi(self):
        user = _make_user()
        with patch("controllers.syllabus.get_all_syllabi", return_value=[]) as mock:
            result = search("", user)
        mock.assert_called_once()

    def test_whitespace_query_returns_all_syllabi(self):
        user = _make_user()
        with patch("controllers.syllabus.get_all_syllabi", return_value=[]) as mock:
            result = search("   ", user)
        mock.assert_called_once()

    def test_valid_query_calls_search_syllabi(self):
        user = _make_user()
        with patch("controllers.syllabus.search_syllabi", return_value=[]) as mock:
            result = search("python", user)
        mock.assert_called_once_with(email="test@example.com", query="python")
