from datetime import date
from unittest.mock import patch, MagicMock
import pytest

def _make_chapter(task_id=1, user_id="1", has_content=False):
    return {
        "id": task_id,
        "_user_id": user_id,
        "skill": "Python",
        "skill_id": 1,
        "topic": "Variables",
        "task": "Learn variables",
        "day": 1,
        "hours": 2,
        "completed": False,
        "newsletter": None,
        "content_blocks": None,
        "has_content": has_content,
    }

class TestGetChapter:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.get("/chapter/1")
        assert response.status_code == 401

    def test_not_found_returns_404(self, auth_client, test_user):
        with patch("controllers.content.get_chapter_content", return_value=None):
            response = auth_client.get("/chapter/999")
        assert response.status_code == 404

    def test_not_owner_returns_403(self, auth_client, test_user):
        chapter = _make_chapter(user_id="999")
        with patch("controllers.content.get_chapter_content", return_value=chapter):
            response = auth_client.get("/chapter/1")
        assert response.status_code == 403

    def test_owner_returns_200(self, auth_client, test_user):
        chapter = _make_chapter(user_id=str(test_user.id))
        with patch("controllers.content.get_chapter_content", return_value=chapter):
            response = auth_client.get("/chapter/1")
        assert response.status_code == 200
        assert response.json()["skill"] == "Python"

class TestCompleteChapter:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.post("/chapter/1/complete", json={"local_date": str(date.today())})
        assert response.status_code == 401

    def test_not_found_returns_404(self, auth_client, test_user):
        with patch("controllers.content.get_chapter_content", return_value=None):
            response = auth_client.post(
                "/chapter/999/complete", json={"local_date": str(date.today())}
            )
        assert response.status_code == 404

    def test_not_owner_returns_403(self, auth_client, test_user):
        chapter = _make_chapter(user_id="999")
        with patch("controllers.content.get_chapter_content", return_value=chapter):
            response = auth_client.post(
                "/chapter/1/complete", json={"local_date": str(date.today())}
            )
        assert response.status_code == 403

    def test_mark_complete_success(self, auth_client, test_user):
        chapter = _make_chapter(user_id=str(test_user.id))
        with (
            patch("controllers.content.get_chapter_content", return_value=chapter),
            patch("controllers.content.mark_task_completed", return_value=True),
            patch("controllers.content.record_activity"),
        ):
            response = auth_client.post(
                "/chapter/1/complete",
                json={"local_date": str(date.today())},
            )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_db_failure_returns_500(self, auth_client, test_user):
        chapter = _make_chapter(user_id=str(test_user.id))
        with (
            patch("controllers.content.get_chapter_content", return_value=chapter),
            patch("controllers.content.mark_task_completed", return_value=False),
        ):
            response = auth_client.post(
                "/chapter/1/complete",
                json={"local_date": str(date.today())},
            )
        assert response.status_code == 500

class TestGenerateChapter:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.post("/generate-content/chapter", json={"task_id": 1})
        assert response.status_code == 401

    def test_not_found_returns_404(self, auth_client, test_user):
        with patch("controllers.content.get_chapter_content", return_value=None):
            response = auth_client.post("/generate-content/chapter", json={"task_id": 999})
        assert response.status_code == 404

    def test_not_owner_returns_403(self, auth_client, test_user):
        chapter = _make_chapter(user_id="999")
        with patch("controllers.content.get_chapter_content", return_value=chapter):
            response = auth_client.post("/generate-content/chapter", json={"task_id": 1})
        assert response.status_code == 403

    def test_llm_failure_returns_503(self, auth_client, test_user):
        chapter = _make_chapter(user_id=str(test_user.id))
        with (
            patch("controllers.content.get_chapter_content", return_value=chapter),
            patch("controllers.content.get_skill_is_technical", return_value=None),
            patch("controllers.content.sample_style", return_value="balanced"),
            patch("controllers.content.generate_chapter_content", return_value=(None, None, None)),
            patch("controllers.content.get_user_provider_name", return_value="gemini"),
            patch("controllers.content.get_user_api_key", return_value="key"),
            patch("controllers.content.get_user_model", return_value="gemini-flash"),
        ):
            response = auth_client.post("/generate-content/chapter", json={"task_id": 1})
        assert response.status_code == 503

    def test_success_returns_200(self, auth_client, test_user):
        chapter = _make_chapter(user_id=str(test_user.id))
        mock_result = MagicMock()
        mock_result.blocks = []
        with (
            patch("controllers.content.get_chapter_content", return_value=chapter),
            patch("controllers.content.get_skill_is_technical", return_value=None),
            patch("controllers.content.sample_style", return_value="balanced"),
            patch(
                "controllers.content.generate_chapter_content",
                return_value=(mock_result, None, None),
            ),
            patch("controllers.content.add_blocks_to_db", return_value=True),
            patch("controllers.content.get_user_provider_name", return_value="gemini"),
            patch("controllers.content.get_user_api_key", return_value="key"),
            patch("controllers.content.get_user_model", return_value="gemini-flash"),
            patch("controllers.content.log_llm_usage"),
        ):
            response = auth_client.post("/generate-content/chapter", json={"task_id": 1})
        assert response.status_code == 200
        assert response.json()["status"] == "success"

class TestGetStreak:
    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.get("/streak")
        assert response.status_code == 401

    def test_authenticated_returns_streak_data(self, auth_client, test_user):
        streak_data = {"current_streak": 3, "longest_streak": 10, "last_activity_date": None}
        with patch("controllers.content.get_user_streak", return_value=streak_data):
            response = auth_client.get("/streak")
        assert response.status_code == 200
        assert response.json()["current_streak"] == 3
