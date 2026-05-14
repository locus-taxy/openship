from unittest.mock import patch, MagicMock
from datetime import date
import pytest
from fastapi import HTTPException
from controllers.content import (
    generate_skill_content,
    generate_chapter,
    get_chapter,
    complete_chapter,
    get_streak,
)
from schemas.skill import GenerateContentRequest, GenerateChapterContentRequest
from models.user import User

def _make_user(user_id=1):
    return User(
        id=user_id,
        email="test@example.com",
        name="Test",
        is_active=True,
        hashed_password="$2b$hash",
        llm_provider_id=1,
    )

def _make_chapter(user_id="1", **kwargs):
    d = {
        "id": 1,
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
        "has_content": False,
    }
    d.update(kwargs)
    return d

class TestGetChapter:
    def test_raises_404_when_not_found(self):
        user = _make_user()
        with patch("controllers.content.get_chapter_content", return_value=None):
            with pytest.raises(HTTPException) as exc:
                get_chapter(999, user)
            assert exc.value.status_code == 404

    def test_raises_403_when_not_owner(self):
        user = _make_user(user_id=1)
        chapter = _make_chapter(user_id="999")
        with patch("controllers.content.get_chapter_content", return_value=chapter):
            with pytest.raises(HTTPException) as exc:
                get_chapter(1, user)
            assert exc.value.status_code == 403

    def test_returns_chapter_for_owner(self):
        user = _make_user()
        chapter = _make_chapter(user_id="1")
        with patch("controllers.content.get_chapter_content", return_value=chapter):
            result = get_chapter(1, user)
        assert result["skill"] == "Python"

class TestGenerateSkillContent:
    def test_raises_404_when_skill_not_found(self):
        user = _make_user()
        with patch("controllers.content.get_syllabus_detail", return_value=None):
            with pytest.raises(HTTPException) as exc:
                generate_skill_content(GenerateContentRequest(skill_id=999), user)
            assert exc.value.status_code == 404

    def test_raises_403_when_not_owner(self):
        user = _make_user(user_id=1)
        detail = {"_user_id": "999", "skill_id": 1, "skill": "Python", "months": []}
        with patch("controllers.content.get_syllabus_detail", return_value=detail):
            with pytest.raises(HTTPException) as exc:
                generate_skill_content(GenerateContentRequest(skill_id=1), user)
            assert exc.value.status_code == 403

    def test_success_with_no_tasks(self):
        user = _make_user()
        detail = {"_user_id": "1", "skill_id": 1, "skill": "Python", "months": []}
        with (
            patch("controllers.content.get_syllabus_detail", return_value=detail),
            patch("controllers.content.get_tasks_for_generating_newsletter", return_value=[]),
        ):
            result = generate_skill_content(GenerateContentRequest(skill_id=1), user)
        assert result["status"] == "success"

    def test_partial_success_when_some_tasks_fail(self):
        user = _make_user()
        detail = {"_user_id": "1", "skill_id": 1, "skill": "Python", "months": []}
        tasks = [{"id": 1, "topic": "Vars", "task": "Learn", "skill": "Python"}]
        with (
            patch("controllers.content.get_syllabus_detail", return_value=detail),
            patch("controllers.content.get_tasks_for_generating_newsletter", return_value=tasks),
            patch("controllers.content.generate_chapter_html", return_value=None),
            patch("controllers.content.get_user_provider_name", return_value="gemini"),
            patch("controllers.content.get_user_api_key", return_value="key"),
            patch("controllers.content.get_user_model", return_value="gemini-flash"),
        ):
            result = generate_skill_content(GenerateContentRequest(skill_id=1), user)
        assert result["status"] == "partial"
        assert 1 in result["failed_task_ids"]

class TestGenerateChapter:
    def test_raises_404_when_not_found(self):
        user = _make_user()
        with patch("controllers.content.get_chapter_content", return_value=None):
            with pytest.raises(HTTPException) as exc:
                generate_chapter(GenerateChapterContentRequest(task_id=999), user)
            assert exc.value.status_code == 404

    def test_raises_403_when_not_owner(self):
        user = _make_user()
        chapter = _make_chapter(user_id="999")
        with patch("controllers.content.get_chapter_content", return_value=chapter):
            with pytest.raises(HTTPException) as exc:
                generate_chapter(GenerateChapterContentRequest(task_id=1), user)
            assert exc.value.status_code == 403

    def test_raises_500_when_save_fails(self):
        user = _make_user()
        chapter = _make_chapter(user_id="1")
        mock_result = MagicMock()
        mock_result.blocks = []
        with (
            patch("controllers.content.get_chapter_content", return_value=chapter),
            patch("controllers.content.generate_chapter_content", return_value=mock_result),
            patch("controllers.content.add_blocks_to_db", return_value=False),
            patch("controllers.content.get_user_provider_name", return_value="gemini"),
            patch("controllers.content.get_user_api_key", return_value="key"),
            patch("controllers.content.get_user_model", return_value="gemini-flash"),
        ):
            with pytest.raises(HTTPException) as exc:
                generate_chapter(GenerateChapterContentRequest(task_id=1), user)
            assert exc.value.status_code == 500

class TestCompleteChapter:
    def test_raises_500_when_mark_fails(self):
        user = _make_user()
        chapter = _make_chapter(user_id="1")
        with (
            patch("controllers.content.get_chapter_content", return_value=chapter),
            patch("controllers.content.mark_task_completed", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc:
                complete_chapter(1, user, date.today())
            assert exc.value.status_code == 500

    def test_success_calls_record_activity(self):
        user = _make_user()
        chapter = _make_chapter(user_id="1")
        with (
            patch("controllers.content.get_chapter_content", return_value=chapter),
            patch("controllers.content.mark_task_completed", return_value=True),
            patch("controllers.content.record_activity") as mock_record,
        ):
            result = complete_chapter(1, user, date.today())
        assert result["status"] == "success"
        mock_record.assert_called_once()

class TestGetStreak:
    def test_returns_streak_data(self):
        user = _make_user()
        streak = {"current_streak": 5, "longest_streak": 10, "last_activity_date": None}
        with patch("controllers.content.get_user_streak", return_value=streak):
            result = get_streak(user)
        assert result["current_streak"] == 5
