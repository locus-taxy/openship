from unittest.mock import patch
import pytest
from fastapi import HTTPException
from controllers.subscription import subscribe_to_skill
from schemas.skill import SubscribeRequest
from models.user import User

def _make_user():
    return User(
        id=1,
        email="test@example.com",
        name="Test",
        is_active=True,
        hashed_password="$2b$hash",
        llm_provider_id=1,
    )

class TestSubscribeToSkill:
    def test_raises_409_when_already_subscribed(self):
        user = _make_user()
        with patch("controllers.subscription.skill_exists", return_value=True):
            with pytest.raises(HTTPException) as exc:
                subscribe_to_skill(
                    SubscribeRequest(skill="Python", days=30, hours=2, quiz_difficulty="beginner"),
                    user,
                )
            assert exc.value.status_code == 409

    def test_raises_500_when_create_fails(self):
        user = _make_user()
        with (
            patch("controllers.subscription.skill_exists", return_value=False),
            patch("controllers.subscription.create_skill", return_value=None),
        ):
            with pytest.raises(HTTPException) as exc:
                subscribe_to_skill(
                    SubscribeRequest(skill="Python", days=30, hours=2, quiz_difficulty="beginner"),
                    user,
                )
            assert exc.value.status_code == 500

    def test_success_returns_status(self):
        user = _make_user()
        with (
            patch("controllers.subscription.skill_exists", return_value=False),
            patch("controllers.subscription.create_skill", return_value=42),
        ):
            result = subscribe_to_skill(
                SubscribeRequest(skill="Python", days=30, hours=2, quiz_difficulty="beginner"),
                user,
            )
        assert result["status"] == "success"
        assert "Python" in result["message"]
