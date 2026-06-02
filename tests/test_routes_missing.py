"""Route integration tests for previously uncovered handlers."""

from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

def _make_auth_client(app, user):
    from services.jwt import create_access_token

    token = create_access_token(user.id)
    with patch("middleware.auth.get_user_by_id", return_value=user):
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("access_token", token)
        return client

def _make_user():
    from models.user import User

    return User(
        id=1,
        email="test@example.com",
        name="Test",
        is_active=True,
        hashed_password="$2b$hash",
        llm_provider_id=1,
    )

class TestNewsletterRoutes:
    def test_post_send_chapter_email(self, app, auth_client):
        with patch("controllers.newsletter.get_chapter_content", return_value=None):
            resp = auth_client.post("/send-email/chapter", json={"task_id": 999})
        assert resp.status_code == 404

    def test_post_issue_newsletters(self, app, auth_client):
        with patch("controllers.newsletter.issue_todays_newsletters"):
            resp = auth_client.post("/issue-newsletters")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

class TestSubscriptionRoute:
    def test_post_subscribe(self, app, auth_client):
        with (
            patch("controllers.subscription.skill_exists", return_value=False),
            patch("controllers.subscription.create_skill", return_value=1),
        ):
            resp = auth_client.post(
                "/subscribe",
                json={"skill": "Python", "days": 30, "hours": 2},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

class TestContentRouteGenerateContent:
    def test_post_generate_content(self, app, auth_client):
        detail = {"_user_id": "1", "skill_id": 1, "skill": "Python", "months": []}
        with (
            patch("controllers.content.get_syllabus_detail", return_value=detail),
            patch("controllers.content.get_tasks_for_generating_newsletter", return_value=[]),
        ):
            resp = auth_client.post("/generate-content", json={"skill_id": 1})
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

class TestSyllabusRouteGenerateSyllabus:
    def test_post_generate_syllabus(self, app, auth_client):
        with patch("controllers.syllabus.get_skill", return_value=None):
            resp = auth_client.post("/generate-syllabus", json={"skill": "Python"})
        assert resp.status_code == 404

class TestAuthRoutesModels:
    def test_get_me_models_invalid_provider(self, app, auth_client):
        with patch("controllers.auth._resolve_provider", return_value=None):
            resp = auth_client.get("/auth/me/models?provider=unknown")
        assert resp.status_code == 400

    def test_post_verify_model_invalid_provider(self, app, auth_client):
        with patch("controllers.auth._resolve_provider", return_value=None):
            resp = auth_client.post("/auth/me/models/verify?provider=unknown&model=test")
        assert resp.status_code == 400
