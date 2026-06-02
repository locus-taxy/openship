from unittest.mock import patch, MagicMock
import pytest

def _sample_syllabus(skill_id=1, user_id="1"):
    return {
        "skill_id": skill_id,
        "_user_id": user_id,
        "skill": "Python",
        "days": 30,
        "hours": 2,
        "quiz_status": "not_generated",
        "weekly_quiz_statuses": {},
        "share_enabled": False,
        "created_at": "2024-01-01",
        "months": [],
    }

class TestListSyllabi:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.get("/syllabi")
        assert response.status_code == 401

    def test_authenticated_returns_list(self, auth_client, test_user):
        with patch("controllers.syllabus.get_all_syllabi", return_value=[]):
            response = auth_client.get("/syllabi")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

class TestGetSyllabus:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.get("/syllabi/1")
        assert response.status_code == 401

    def test_not_found_returns_404(self, auth_client, test_user):
        with patch("controllers.syllabus.get_syllabus_detail", return_value=None):
            response = auth_client.get("/syllabi/999")
        assert response.status_code == 404

    def test_not_owner_returns_403(self, auth_client, test_user):
        detail = _sample_syllabus(user_id="999")  # different user
        with patch("controllers.syllabus.get_syllabus_detail", return_value=detail):
            response = auth_client.get("/syllabi/1")
        assert response.status_code == 403

    def test_owner_returns_200(self, auth_client, test_user):
        detail = _sample_syllabus(user_id=str(test_user.id))
        with patch("controllers.syllabus.get_syllabus_detail", return_value=detail):
            response = auth_client.get("/syllabi/1")
        assert response.status_code == 200

class TestDeleteSyllabus:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.delete("/syllabi/1")
        assert response.status_code == 401

    def test_not_found_returns_404(self, auth_client, test_user):
        with patch("controllers.syllabus.delete_skill", return_value=False):
            response = auth_client.delete("/syllabi/999")
        assert response.status_code == 404

    def test_success_returns_200(self, auth_client, test_user):
        with patch("controllers.syllabus.delete_skill", return_value=True):
            response = auth_client.delete("/syllabi/1")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

class TestToggleShare:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.patch("/syllabi/1/share?enable=true")
        assert response.status_code == 401

    def test_not_found_returns_404(self, auth_client, test_user):
        with patch("controllers.syllabus.toggle_skill_share", return_value=None):
            response = auth_client.patch("/syllabi/999/share?enable=true")
        assert response.status_code == 404

    def test_enable_share_returns_200(self, auth_client, test_user):
        with patch("controllers.syllabus.toggle_skill_share", return_value=True):
            response = auth_client.patch("/syllabi/1/share?enable=true")
        assert response.status_code == 200
        assert response.json()["share_enabled"] is True

class TestSearchSyllabi:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.get("/syllabi/search?q=python")
        assert response.status_code == 401

    def test_empty_query_returns_all_syllabi(self, auth_client, test_user):
        with patch("controllers.syllabus.get_all_syllabi", return_value=[]) as mock_all:
            response = auth_client.get("/syllabi/search?q=")
        assert response.status_code == 200
        mock_all.assert_called_once()

    def test_with_query_calls_search(self, auth_client, test_user):
        with patch("controllers.syllabus.search_syllabi", return_value=[]) as mock_search:
            response = auth_client.get("/syllabi/search?q=python")
        assert response.status_code == 200
        mock_search.assert_called_once()

class TestPublicSyllabus:
    def test_not_found_returns_404(self, anon_client):
        with patch("controllers.syllabus.get_public_syllabus_detail", return_value=None):
            response = anon_client.get("/public/syllabi/999")
        assert response.status_code == 404

    def test_found_returns_200_no_auth_needed(self, anon_client):
        detail = {
            "skill_id": 1,
            "skill": "Python",
            "days": 30,
            "share_enabled": True,
            "months": [],
        }
        with patch("controllers.syllabus.get_public_syllabus_detail", return_value=detail):
            response = anon_client.get("/public/syllabi/1")
        assert response.status_code == 200
