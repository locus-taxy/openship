"""Tests for new controller functions in controllers/auth.py and controllers/content.py."""

import math
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from models.user import User

def _make_user(**kwargs):
    defaults = dict(
        id=1,
        email="test@example.com",
        name="Test",
        is_active=True,
        hashed_password="$2b$hash",
        llm_provider_id=None,
        display_currency=None,
        currency_exchange_rate=None,
    )
    defaults.update(kwargs)
    return User(**defaults)

# ── controllers/auth.py ───────────────────────────────────────────────────────

class TestGetModelPricing:
    def test_returns_pricing_info_with_no_manual_override(self):
        from controllers.auth import get_model_pricing

        user = _make_user()
        mock_info = {
            "input_per_1m_usd": 0.15,
            "output_per_1m_usd": 0.6,
            "matched_model_id": "gpt-4o-mini",
            "found": True,
        }
        with patch("controllers.auth.lookup_model_info", return_value=mock_info):
            with patch("controllers.auth.get_user_model_price", return_value=None):
                result = get_model_pricing("openai", "gpt-4o-mini", user)

        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o-mini"
        assert result["found"] is True
        assert result["manual_input_per_1m_usd"] is None
        assert result["manual_output_per_1m_usd"] is None

    def test_returns_manual_override_when_present(self):
        from controllers.auth import get_model_pricing

        user = _make_user()
        mock_info = {
            "input_per_1m_usd": None,
            "output_per_1m_usd": None,
            "matched_model_id": None,
            "found": False,
        }
        with patch("controllers.auth.lookup_model_info", return_value=mock_info):
            with patch("controllers.auth.get_user_model_price", return_value=(9.0, 27.0)):
                result = get_model_pricing("openai", "some-custom-model", user)

        assert result["manual_input_per_1m_usd"] == 9.0
        assert result["manual_output_per_1m_usd"] == 27.0

class TestSaveManualPricing:
    def test_saves_valid_prices(self):
        from controllers.auth import save_manual_pricing

        user = _make_user()
        with patch("controllers.auth.save_user_model_price") as mock_save:
            result = save_manual_pricing(user, "openai", "gpt-4o-mini", 1.0, 2.0)
        mock_save.assert_called_once_with(1, "openai", "gpt-4o-mini", 1.0, 2.0)
        assert result == {"status": "success"}

    def test_raises_422_for_negative_input(self):
        from controllers.auth import save_manual_pricing

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            save_manual_pricing(user, "openai", "gpt-4o-mini", -1.0, 2.0)
        assert exc_info.value.status_code == 422

    def test_raises_422_for_negative_output(self):
        from controllers.auth import save_manual_pricing

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            save_manual_pricing(user, "openai", "gpt-4o-mini", 1.0, -0.5)
        assert exc_info.value.status_code == 422

    def test_raises_422_for_infinite_price(self):
        from controllers.auth import save_manual_pricing

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            save_manual_pricing(user, "openai", "gpt-4o-mini", math.inf, 2.0)
        assert exc_info.value.status_code == 422

    def test_raises_422_for_nan_price(self):
        from controllers.auth import save_manual_pricing

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            save_manual_pricing(user, "openai", "gpt-4o-mini", math.nan, 2.0)
        assert exc_info.value.status_code == 422

class TestRefreshPricingCache:
    def test_invalidates_cache_and_returns_success(self):
        from controllers.auth import refresh_pricing_cache

        with patch("controllers.auth.invalidate_pricing_cache") as mock_inv:
            result = refresh_pricing_cache()
        mock_inv.assert_called_once()
        assert result["status"] == "success"

class TestSaveCurrency:
    def test_saves_currency_settings(self):
        from controllers.auth import save_currency

        user = _make_user()
        payload = MagicMock()
        payload.display_currency = "EUR"
        payload.currency_exchange_rate = 0.92

        with patch("controllers.auth.update_currency_settings") as mock_update:
            result = save_currency(user, payload)
        mock_update.assert_called_once_with(1, "EUR", 0.92)
        assert result == {"status": "success"}

# ── controllers/content.py ────────────────────────────────────────────────────

class TestGetChapterCostView:
    def test_returns_cost_data_with_currency(self):
        from controllers.content import get_chapter_cost_view

        user = _make_user()
        chapter = {"_user_id": "1", "id": 5, "topic": "Python"}
        cost_data = {"total_cost_usd": 0.01, "generation_count": 2, "logs": []}

        with patch("controllers.content.get_chapter_content", return_value=chapter):
            with patch("controllers.content.get_chapter_cost", return_value=cost_data):
                with patch("controllers.content.get_currency_settings", return_value=("EUR", 0.9)):
                    result = get_chapter_cost_view(task_id=5, current_user=user)

        assert result["total_cost_usd"] == 0.01
        assert result["display_currency"] == "EUR"
        assert result["exchange_rate"] == 0.9
        assert result["total_cost_display"] == pytest.approx(0.009, abs=1e-4)

    def test_raises_404_when_chapter_not_found(self):
        from controllers.content import get_chapter_cost_view

        user = _make_user()
        with patch("controllers.content.get_chapter_content", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                get_chapter_cost_view(task_id=999, current_user=user)
        assert exc_info.value.status_code == 404

    def test_raises_403_when_different_owner(self):
        from controllers.content import get_chapter_cost_view

        user = _make_user(id=1)
        chapter = {"_user_id": "99", "id": 5, "topic": "T"}
        with patch("controllers.content.get_chapter_content", return_value=chapter):
            with pytest.raises(HTTPException) as exc_info:
                get_chapter_cost_view(task_id=5, current_user=user)
        assert exc_info.value.status_code == 403

class TestGetUserUsageCostView:
    def test_returns_usage_data_with_currency(self):
        from controllers.content import get_user_usage_cost_view

        user = _make_user()
        usage_data = {
            "total_cost_usd": 0.05,
            "total_input_tokens": 1000,
            "total_output_tokens": 2000,
            "total_calls": 10,
            "by_type": {},
        }
        with patch("controllers.content.get_user_usage_cost", return_value=usage_data):
            with patch("controllers.content.get_currency_settings", return_value=("USD", 1.0)):
                result = get_user_usage_cost_view(current_user=user)

        assert result["total_cost_usd"] == 0.05
        assert result["display_currency"] == "USD"
        assert result["total_cost_display"] == pytest.approx(0.05, abs=1e-4)

class TestGetCostAnalytics:
    def test_returns_summary_with_currency_conversion(self):
        from controllers.content import get_cost_analytics

        user = _make_user()
        summary = {
            "total_input_tokens": 500,
            "total_output_tokens": 1000,
            "total_cost_usd": 0.1,
        }
        with patch("controllers.content.get_user_usage_cost", return_value=summary):
            with patch("controllers.content.get_currency_settings", return_value=("INR", 83.0)):
                result = get_cost_analytics(current_user=user)

        assert result["total_cost_usd"] == 0.1
        assert result["display_currency"] == "INR"
        assert result["exchange_rate"] == 83.0
        assert result["total_cost_display"] == pytest.approx(8.3, abs=1e-2)

class TestResolvePriceHelper:
    def test_returns_auto_price_when_available(self):
        from controllers.content import _resolve_price

        user = _make_user()
        with patch("controllers.content.lookup_model_price", return_value=(1.0, 2.0)):
            inp, out = _resolve_price(user, "openai", "gpt-4o-mini")
        assert inp == 1.0
        assert out == 2.0

    def test_falls_back_to_manual_price_when_auto_is_none(self):
        from controllers.content import _resolve_price

        user = _make_user()
        with patch("controllers.content.lookup_model_price", return_value=(None, None)):
            with patch("controllers.content.get_user_model_price", return_value=(9.0, 18.0)):
                inp, out = _resolve_price(user, "openai", "custom-model")
        assert inp == 9.0
        assert out == 18.0

    def test_returns_none_when_no_price_available(self):
        from controllers.content import _resolve_price

        user = _make_user()
        with patch("controllers.content.lookup_model_price", return_value=(None, None)):
            with patch("controllers.content.get_user_model_price", return_value=None):
                inp, out = _resolve_price(user, "openai", "unknown-model")
        assert inp is None
        assert out is None

class TestGenerateSkillContentCoveragePaths:
    def _make_user(self):
        return User(
            id=1,
            email="test@example.com",
            name="Test",
            is_active=True,
            hashed_password="$2b$hash",
            llm_provider_id=1,
        )

    def test_empty_html_adds_to_failed_tasks(self):
        from controllers.content import generate_skill_content
        from schemas.skill import GenerateContentRequest

        user = self._make_user()
        detail = {"_user_id": "1", "skill_id": 1, "skill": "Python", "months": []}
        tasks = [{"id": 1, "topic": "Vars", "task": "Learn", "skill": "Python"}]
        with (
            patch("controllers.content.get_syllabus_detail", return_value=detail),
            patch("controllers.content.get_tasks_for_generating_newsletter", return_value=tasks),
            patch("controllers.content.generate_chapter_html", return_value=("", None, None)),
            patch("controllers.content.get_user_provider_name", return_value="gemini"),
            patch("controllers.content.get_user_api_key", return_value="key"),
            patch("controllers.content.get_user_model", return_value="gemini-flash"),
        ):
            result = generate_skill_content(GenerateContentRequest(skill_id=1), user)
        assert result["status"] == "partial"
        assert 1 in result["failed_task_ids"]

    def test_tokens_present_triggers_pricing_in_skill_loop(self):
        from controllers.content import generate_skill_content
        from schemas.skill import GenerateContentRequest

        user = self._make_user()
        detail = {"_user_id": "1", "skill_id": 1, "skill": "Python", "months": []}
        tasks = [{"id": 1, "topic": "Vars", "task": "Learn", "skill": "Python"}]
        with (
            patch("controllers.content.get_syllabus_detail", return_value=detail),
            patch("controllers.content.get_tasks_for_generating_newsletter", return_value=tasks),
            patch(
                "controllers.content.generate_chapter_html", return_value=("<p>html</p>", 100, 50)
            ),
            patch("controllers.content.get_user_provider_name", return_value="gemini"),
            patch("controllers.content.get_user_api_key", return_value="key"),
            patch("controllers.content.get_user_model", return_value="gemini-flash"),
            patch("controllers.content.lookup_model_price", return_value=(1.0, 2.0)),
            patch("controllers.content.get_user_model_price", return_value=None),
            patch("controllers.content.compute_generation_cost_usd", return_value=0.0002),
            patch("controllers.content.log_llm_usage"),
            patch("controllers.content.add_content_to_db", return_value=True),
            patch("controllers.content.time"),
        ):
            result = generate_skill_content(GenerateContentRequest(skill_id=1), user)
        assert result["status"] == "success"

class TestGenerateChapterCoveragePaths:
    def _make_user(self):
        return User(
            id=1,
            email="test@example.com",
            name="Test",
            is_active=True,
            hashed_password="$2b$hash",
            llm_provider_id=1,
        )

    def _make_chapter(self, user_id="1"):
        return {
            "_user_id": user_id,
            "id": 1,
            "skill": "Python",
            "topic": "Vars",
            "task": "Learn vars",
        }

    def test_none_result_raises_500(self):
        from controllers.content import generate_chapter
        from schemas.skill import GenerateChapterContentRequest

        user = self._make_user()
        chapter = self._make_chapter()
        with (
            patch("controllers.content.get_chapter_content", return_value=chapter),
            patch("controllers.content.generate_chapter_content", return_value=None),
            patch("controllers.content.get_user_provider_name", return_value="gemini"),
            patch("controllers.content.get_user_api_key", return_value="key"),
            patch("controllers.content.get_user_model", return_value="gemini-flash"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                generate_chapter(GenerateChapterContentRequest(task_id=1), user)
        assert exc_info.value.status_code == 500

    def test_tokens_present_triggers_pricing(self):
        from controllers.content import generate_chapter
        from schemas.skill import GenerateChapterContentRequest

        user = self._make_user()
        chapter = self._make_chapter()
        mock_result = MagicMock()
        mock_result.blocks = []
        with (
            patch("controllers.content.get_chapter_content", return_value=chapter),
            patch(
                "controllers.content.generate_chapter_content",
                return_value=(mock_result, 200, 100),
            ),
            patch("controllers.content.get_user_provider_name", return_value="gemini"),
            patch("controllers.content.get_user_api_key", return_value="key"),
            patch("controllers.content.get_user_model", return_value="gemini-flash"),
            patch("controllers.content.lookup_model_price", return_value=(1.0, 2.0)),
            patch("controllers.content.get_user_model_price", return_value=None),
            patch("controllers.content.compute_generation_cost_usd", return_value=0.0005),
            patch("controllers.content.log_llm_usage"),
            patch("controllers.content.add_blocks_to_db", return_value=True),
        ):
            result = generate_chapter(GenerateChapterContentRequest(task_id=1), user)
        assert result["status"] == "success"
