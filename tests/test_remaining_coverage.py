"""
Targeted tests for remaining uncovered lines across config, content controller,
service helpers, and route handlers.
"""

import os
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

# ── config._env_bool branches ─────────────────────────────────────────────────

class TestEnvBoolBranches:
    def test_truthy_value_returns_true(self):
        from config import _env_bool

        with patch.dict(os.environ, {"TEST_BOOL_VAR": "true"}):
            assert _env_bool("TEST_BOOL_VAR", False) is True

    def test_truthy_one_returns_true(self):
        from config import _env_bool

        with patch.dict(os.environ, {"TEST_BOOL_VAR": "1"}):
            assert _env_bool("TEST_BOOL_VAR", False) is True

    def test_falsey_value_returns_false(self):
        from config import _env_bool

        with patch.dict(os.environ, {"TEST_BOOL_VAR": "false"}):
            assert _env_bool("TEST_BOOL_VAR", True) is False

    def test_falsey_zero_returns_false(self):
        from config import _env_bool

        with patch.dict(os.environ, {"TEST_BOOL_VAR": "0"}):
            assert _env_bool("TEST_BOOL_VAR", True) is False

    def test_invalid_value_raises_value_error(self):
        from config import _env_bool

        with patch.dict(os.environ, {"TEST_BOOL_VAR": "maybe"}):
            with pytest.raises(ValueError, match="Invalid boolean"):
                _env_bool("TEST_BOOL_VAR", True)

    def test_missing_var_returns_default(self):
        from config import _env_bool

        env = {k: v for k, v in os.environ.items() if k != "TEST_BOOL_MISSING"}
        with patch.dict(os.environ, env, clear=True):
            assert _env_bool("TEST_BOOL_MISSING", True) is True

class TestEnvIntBranches:
    def test_missing_var_returns_default(self):
        from config import _env_int

        env = {k: v for k, v in os.environ.items() if k != "TEST_INT_MISSING"}
        with patch.dict(os.environ, env, clear=True):
            assert _env_int("TEST_INT_MISSING", 42) == 42

    def test_empty_string_returns_default(self):
        from config import _env_int

        with patch.dict(os.environ, {"TEST_INT_VAR": "   "}):
            assert _env_int("TEST_INT_VAR", 99) == 99

    def test_valid_int_returns_value(self):
        from config import _env_int

        with patch.dict(os.environ, {"TEST_INT_VAR": "123"}):
            assert _env_int("TEST_INT_VAR", 0) == 123

    def test_invalid_int_raises_value_error(self):
        from config import _env_int

        with patch.dict(os.environ, {"TEST_INT_VAR": "not-a-number"}):
            with pytest.raises(ValueError, match="Invalid integer"):
                _env_int("TEST_INT_VAR", 0)

# ── controllers/content.py remaining error paths ─────────────────────────────

class TestGenerateSkillContentInnerErrors:
    def _base_patches(self, user, tasks):
        detail = {"_user_id": "1", "skill_id": 1, "skill": "Python", "months": []}
        return [
            patch("controllers.content.get_syllabus_detail", return_value=detail),
            patch("controllers.content.get_tasks_for_generating_newsletter", return_value=tasks),
            patch("controllers.content.get_user_provider_name", return_value="gemini"),
            patch("controllers.content.get_user_api_key", return_value="key"),
            patch("controllers.content.get_user_model", return_value="gemini-flash"),
        ]

    def test_add_content_fails_adds_to_failed(self):
        from controllers.content import generate_skill_content
        from schemas.skill import GenerateContentRequest
        from models.user import User

        user = User(
            id=1,
            email="test@example.com",
            name="Test",
            is_active=True,
            hashed_password="hash",
            llm_provider_id=1,
        )
        tasks = [{"id": 1, "topic": "Vars", "task": "Learn", "skill": "Python"}]

        with (
            patch(
                "controllers.content.get_syllabus_detail",
                return_value={"_user_id": "1", "skill_id": 1, "skill": "Python", "months": []},
            ),
            patch("controllers.content.get_tasks_for_generating_newsletter", return_value=tasks),
            patch("controllers.content.generate_chapter_html", return_value="<p>html</p>"),
            patch("controllers.content.add_content_to_db", return_value=False),
            patch("controllers.content.get_user_provider_name", return_value="gemini"),
            patch("controllers.content.get_user_api_key", return_value="key"),
            patch("controllers.content.get_user_model", return_value="gemini-flash"),
            patch("controllers.content.time"),
        ):
            result = generate_skill_content(GenerateContentRequest(skill_id=1), user)
        assert result["status"] == "partial"
        assert 1 in result["failed_task_ids"]

    def test_reraises_http_exception_from_inner_loop(self):
        from controllers.content import generate_skill_content
        from schemas.skill import GenerateContentRequest
        from models.user import User

        user = User(
            id=1,
            email="test@example.com",
            name="Test",
            is_active=True,
            hashed_password="hash",
            llm_provider_id=1,
        )
        tasks = [{"id": 1, "topic": "Vars", "task": "Learn", "skill": "Python"}]

        with (
            patch(
                "controllers.content.get_syllabus_detail",
                return_value={"_user_id": "1", "skill_id": 1, "skill": "Python", "months": []},
            ),
            patch("controllers.content.get_tasks_for_generating_newsletter", return_value=tasks),
            patch(
                "controllers.content.generate_chapter_html",
                side_effect=HTTPException(status_code=429, detail="quota"),
            ),
            patch("controllers.content.get_user_provider_name", return_value="gemini"),
            patch("controllers.content.get_user_api_key", return_value="key"),
            patch("controllers.content.get_user_model", return_value="gemini-flash"),
        ):
            with pytest.raises(HTTPException) as exc:
                generate_skill_content(GenerateContentRequest(skill_id=1), user)
            assert exc.value.status_code == 429

    def test_generic_exception_adds_to_failed_continues(self):
        from controllers.content import generate_skill_content
        from schemas.skill import GenerateContentRequest
        from models.user import User

        user = User(
            id=1,
            email="test@example.com",
            name="Test",
            is_active=True,
            hashed_password="hash",
            llm_provider_id=1,
        )
        tasks = [
            {"id": 1, "topic": "Vars", "task": "Learn", "skill": "Python"},
            {"id": 2, "topic": "Loops", "task": "Learn", "skill": "Python"},
        ]

        call_count = [0]

        def flaky_generate(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("unexpected error")
            return "<p>html</p>"

        with (
            patch(
                "controllers.content.get_syllabus_detail",
                return_value={"_user_id": "1", "skill_id": 1, "skill": "Python", "months": []},
            ),
            patch("controllers.content.get_tasks_for_generating_newsletter", return_value=tasks),
            patch("controllers.content.generate_chapter_html", side_effect=flaky_generate),
            patch("controllers.content.add_content_to_db", return_value=True),
            patch("controllers.content.get_user_provider_name", return_value="gemini"),
            patch("controllers.content.get_user_api_key", return_value="key"),
            patch("controllers.content.get_user_model", return_value="gemini-flash"),
            patch("controllers.content.time"),
        ):
            result = generate_skill_content(GenerateContentRequest(skill_id=1), user)
        # task 1 fails, task 2 succeeds → partial
        assert result["status"] == "partial"
        assert 1 in result["failed_task_ids"]
        assert 2 not in result["failed_task_ids"]

# ── services/skill.py get_public_syllabus_detail with tasks ──────────────────

class TestGetPublicSyllabusDetailWithTasks:
    def test_returns_structured_months_when_tasks_exist(self):
        from services.skill import get_public_syllabus_detail
        from models.skill import Skill
        from models.daily_task import DailyTask

        skill = Skill(
            id=1,
            user_id="u1",
            email="test@example.com",
            skill="Python",
            days=30,
            hours=2,
            share_enabled=True,
        )
        task = DailyTask(
            id=10,
            user_id="u1",
            skill="Python",
            skill_id=1,
            month=1,
            week=1,
            day=1,
            topic="Variables",
            task="Learn",
            hours=2,
            completed=False,
            newsletter=None,
            content_blocks=None,
        )

        session = MagicMock()
        session.get.return_value = skill
        exec_mock = MagicMock()
        exec_mock.all.return_value = [task]
        session.exec.return_value = exec_mock

        patcher = patch("services.skill.Session")
        mock_cls = patcher.start()
        mock_cls.return_value.__enter__ = MagicMock(return_value=session)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        try:
            result = get_public_syllabus_detail(1)
            assert result is not None
            assert result["skill"] == "Python"
            months = result["months"]
            assert len(months) == 1
            assert months[0]["month"] == 1
        finally:
            patcher.stop()

# ── services/llm.py generate_chapter_content with exception cause ─────────────

class TestGenerateChapterContentWithCause:
    def test_logs_cause_when_exception_has_context(self):
        from services.llm import generate_chapter_content

        inner = RuntimeError("inner network timeout")
        outer = RuntimeError("outer wrapper error")
        outer.__cause__ = inner

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = outer
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_chapter_content("desc", "title", "Python", "openai", "key", "gpt-4o")
        assert result is None

# ── services/llm.py generate_quiz returns None on empty response ──────────────

class TestGenerateQuizEmptyResponse:
    def test_returns_none_when_response_has_no_questions(self):
        from services.llm import generate_quiz

        mock_response = MagicMock()
        mock_response.questions = []  # empty — triggers the mismatch check
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_quiz(
                "Python", ["Vars"], "beginner", 10, "gemini", "key", "gemini-flash"
            )
        assert result is None

# ── services/newsletter.py issue_todays_newsletters skill-with-no-tasks skip ──

class TestIssueNewsletterskillNoTasks:
    def test_skips_skill_when_get_tasks_returns_empty_in_loop(self):
        from services.newsletter import issue_todays_newsletters

        # _get_valid_skill_ids internally calls get_tasks_based_on_skill_id once per skill
        # issue_todays_newsletters calls it again in the loop
        # Simulate: one skill_id found, but the LOOP call returns empty list
        with (
            patch("services.newsletter.get_list_of_skill_ids", return_value=[1]),
            patch("services.newsletter.get_tasks_based_on_skill_id", side_effect=[[{"id": 1}], []]),
            patch("services.newsletter.time"),
        ):
            result = issue_todays_newsletters()
        assert result is True

# ── middleware invalid sub (non-int) returns 401 ─────────────────────────────

class TestMiddlewareInvalidSub:
    def test_non_integer_sub_returns_401(self):
        from middleware.auth import AuthMiddleware
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.add_middleware(AuthMiddleware)

        @app.get("/private")
        def private():
            return {"ok": True}

        # Build a token where sub is not a number
        import jwt as pyjwt
        from config import JWT_SECRET_KEY, JWT_ALGORITHM

        bad_token = pyjwt.encode(
            {"sub": "not-a-number", "type": "access"},
            JWT_SECRET_KEY,
            algorithm=JWT_ALGORITHM,
        )
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("access_token", bad_token)
        with patch("middleware.auth.get_user_by_id"):
            response = client.get("/private")
        assert response.status_code == 401
