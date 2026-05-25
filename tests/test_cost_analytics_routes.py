"""Tests for new routes in routes/auth.py and routes/content.py."""

import pytest
from unittest.mock import patch

class TestAuthPricingRoutes:
    """Covers routes/auth.py lines 47-48, 51-56, 58-60, 62-64."""

    def test_get_model_pricing(self, auth_client):
        mock_result = {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "input_per_1m_usd": 0.15,
            "output_per_1m_usd": 0.6,
            "matched_model_id": "gpt-4o-mini",
            "found": True,
            "manual_input_per_1m_usd": None,
            "manual_output_per_1m_usd": None,
        }
        with patch("controllers.auth.get_model_pricing", return_value=mock_result) as mock_ctrl:
            resp = auth_client.get("/auth/me/pricing?provider=openai&model=gpt-4o-mini")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "openai"
        assert data["found"] is True

    def test_save_manual_pricing(self, auth_client):
        with patch("controllers.auth.save_manual_pricing", return_value={"status": "success"}):
            resp = auth_client.put(
                "/auth/me/pricing/manual",
                params={
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "input_per_1m_usd": 1.5,
                    "output_per_1m_usd": 3.0,
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_refresh_pricing_cache(self, auth_client):
        with patch(
            "controllers.auth.refresh_pricing_cache",
            return_value={
                "status": "success",
                "message": "Pricing cache cleared — next request will re-fetch",
            },
        ):
            resp = auth_client.post("/auth/me/pricing/refresh")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_save_currency(self, auth_client):
        with patch("controllers.auth.save_currency", return_value={"status": "success"}):
            resp = auth_client.patch(
                "/auth/me/settings/currency",
                json={"display_currency": "EUR", "currency_exchange_rate": 0.92},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

class TestContentCostRoutes:
    """Covers routes/content.py lines 28-38."""

    def test_get_chapter_cost(self, auth_client):
        mock_result = {
            "total_cost_usd": 0.01,
            "generation_count": 1,
            "logs": [],
            "total_cost_display": 0.01,
            "display_currency": "USD",
            "exchange_rate": 1.0,
        }
        with patch("controllers.content.get_chapter_cost_view", return_value=mock_result):
            resp = auth_client.get("/chapter/1/cost")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_cost_usd" in data

    def test_get_cost_analytics(self, auth_client):
        mock_result = {
            "total_input_tokens": 100,
            "total_output_tokens": 200,
            "total_cost_usd": 0.005,
            "total_cost_display": 0.005,
            "display_currency": "USD",
            "exchange_rate": 1.0,
        }
        with patch("controllers.content.get_cost_analytics", return_value=mock_result):
            resp = auth_client.get("/analytics/cost")
        assert resp.status_code == 200
        assert resp.json()["total_cost_usd"] == 0.005

    def test_get_user_usage_cost(self, auth_client):
        mock_result = {
            "total_cost_usd": 0.02,
            "total_input_tokens": 500,
            "total_output_tokens": 1000,
            "total_calls": 5,
            "by_type": {},
            "total_cost_display": 0.02,
            "display_currency": "USD",
            "exchange_rate": 1.0,
        }
        with patch("controllers.content.get_user_usage_cost_view", return_value=mock_result):
            resp = auth_client.get("/me/usage-cost")
        assert resp.status_code == 200
        assert resp.json()["total_calls"] == 5
