"""Tests for services/pricing.py — covers all previously uncovered lines."""

import pytest
from unittest.mock import MagicMock, patch
import services.pricing as pricing_module

def _reset_cache():
    """Reset module-level cache between tests."""
    pricing_module._cache = None

class TestGetModels:
    def setup_method(self):
        _reset_cache()

    def test_fetches_from_api_and_caches(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"models": [{"model_id": "m1"}]}
        with patch("services.pricing.httpx.get", return_value=mock_resp) as mock_get:
            result = pricing_module._get_models()
            assert result == [{"model_id": "m1"}]
            # Second call should not hit HTTP
            result2 = pricing_module._get_models()
            mock_get.assert_called_once()

    def test_returns_cached_value_on_second_call(self):
        pricing_module._cache = [{"model_id": "cached"}]
        with patch("services.pricing.httpx.get") as mock_get:
            result = pricing_module._get_models()
            mock_get.assert_not_called()
            assert result == [{"model_id": "cached"}]

    def test_falls_back_to_empty_list_on_error(self):
        with patch("services.pricing.httpx.get", side_effect=Exception("timeout")):
            result = pricing_module._get_models()
            assert result == []

    def test_logs_warning_on_fetch_failure(self, caplog):
        import logging

        with patch("services.pricing.httpx.get", side_effect=Exception("net err")):
            with caplog.at_level(logging.WARNING, logger="services.pricing"):
                pricing_module._get_models()
        assert any("falling back" in r.message for r in caplog.records)

class TestPickPrice:
    def test_returns_standard_tier_price(self):
        entry = {
            "pricing": [
                {
                    "platform": "openai",
                    "modality": "text",
                    "tier": "standard",
                    "input_per_1m_tokens": 2.5,
                    "output_per_1m_tokens": 10.0,
                },
            ]
        }
        inp, out = pricing_module._pick_price(entry, "openai")
        assert inp == 2.5
        assert out == 10.0

    def test_returns_non_standard_tier_when_no_standard(self):
        entry = {
            "pricing": [
                {
                    "platform": "openai",
                    "modality": "text",
                    "tier": "batch",
                    "input_per_1m_tokens": 1.0,
                    "output_per_1m_tokens": 5.0,
                },
            ]
        }
        inp, out = pricing_module._pick_price(entry, "openai")
        assert inp == 1.0

    def test_falls_back_to_fallback_platform(self):
        entry = {
            "pricing": [
                {
                    "platform": "openrouter",
                    "modality": "text",
                    "tier": "standard",
                    "input_per_1m_tokens": 3.0,
                    "output_per_1m_tokens": 12.0,
                },
            ]
        }
        inp, out = pricing_module._pick_price(entry, "openai")
        assert inp == 3.0

    def test_returns_none_none_when_no_prices(self):
        entry = {"pricing": []}
        inp, out = pricing_module._pick_price(entry, "openai")
        assert inp is None
        assert out is None

    def test_skips_wrong_modality(self):
        entry = {
            "pricing": [
                {
                    "platform": "openai",
                    "modality": "image",
                    "tier": "standard",
                    "input_per_1m_tokens": 9.0,
                    "output_per_1m_tokens": 9.0,
                },
            ]
        }
        inp, out = pricing_module._pick_price(entry, "openai")
        assert inp is None

class TestResolve:
    def setup_method(self):
        _reset_cache()

    def test_unknown_provider_returns_none_triple(self):
        pricing_module._cache = []
        inp, out, matched = pricing_module._resolve("unknown_provider", "some-model")
        assert inp is None
        assert out is None
        assert matched is None

    def test_exact_match_on_model_id(self):
        pricing_module._cache = [
            {
                "provider": "openai",
                "model_id": "gpt-4o",
                "aliases": {},
                "pricing": [
                    {
                        "platform": "openai",
                        "modality": "text",
                        "tier": "standard",
                        "input_per_1m_tokens": 2.5,
                        "output_per_1m_tokens": 10.0,
                    }
                ],
            }
        ]
        inp, out, matched = pricing_module._resolve("openai", "gpt-4o")
        assert inp == 2.5
        assert matched == "gpt-4o"

    def test_exact_match_on_platform_alias(self):
        pricing_module._cache = [
            {
                "provider": "google",
                "model_id": "gemini-2.5-flash",
                "aliases": {"google_ai_studio": "gemini-2.5-flash-alias"},
                "pricing": [
                    {
                        "platform": "google_ai_studio",
                        "modality": "text",
                        "tier": "standard",
                        "input_per_1m_tokens": 0.3,
                        "output_per_1m_tokens": 2.5,
                    }
                ],
            }
        ]
        inp, out, matched = pricing_module._resolve("gemini", "gemini-2.5-flash-alias")
        assert inp == 0.3

    def test_forward_prefix_match(self):
        pricing_module._cache = [
            {
                "provider": "google",
                "model_id": "gemini-2.5-pro",
                "aliases": {},
                "pricing": [
                    {
                        "platform": "google_ai_studio",
                        "modality": "text",
                        "tier": "standard",
                        "input_per_1m_tokens": 1.25,
                        "output_per_1m_tokens": 10.0,
                    }
                ],
            }
        ]
        inp, out, matched = pricing_module._resolve("gemini", "gemini-2.5-pro-preview-05-06")
        assert inp == 1.25
        assert matched == "gemini-2.5-pro"

    def test_reverse_prefix_match_for_latest(self):
        pricing_module._cache = [
            {
                "provider": "anthropic",
                "model_id": "claude-3-5-haiku-20241022",
                "aliases": {},
                "pricing": [
                    {
                        "platform": "anthropic",
                        "modality": "text",
                        "tier": "standard",
                        "input_per_1m_tokens": 0.8,
                        "output_per_1m_tokens": 4.0,
                    }
                ],
            }
        ]
        inp, out, matched = pricing_module._resolve("anthropic", "claude-3-5-haiku-latest")
        assert inp == 0.8
        assert matched == "claude-3-5-haiku-20241022"

    def test_falls_back_to_hardcoded(self):
        pricing_module._cache = []
        inp, out, matched = pricing_module._resolve("gemini", "gemini-2.5-flash")
        assert inp == 0.30
        assert out == 2.5
        assert matched == "gemini-2.5-flash"

    def test_returns_none_when_not_in_hardcoded(self):
        pricing_module._cache = []
        inp, out, matched = pricing_module._resolve("openai", "gpt-9999-unknown")
        assert inp is None
        assert out is None
        assert matched is None

class TestLookupModelPrice:
    def setup_method(self):
        _reset_cache()
        pricing_module._cache = []

    def test_returns_tuple_for_hardcoded_model(self):
        inp, out = pricing_module.lookup_model_price("openai", "gpt-4o-mini")
        assert inp == 0.15
        assert out == 0.6

    def test_returns_none_none_for_unknown(self):
        inp, out = pricing_module.lookup_model_price("openai", "gpt-does-not-exist")
        assert inp is None
        assert out is None

class TestLookupModelInfo:
    def setup_method(self):
        _reset_cache()
        pricing_module._cache = []

    def test_found_true_for_hardcoded_model(self):
        info = pricing_module.lookup_model_info("anthropic", "claude-3-5-haiku-latest")
        assert info["found"] is True
        assert info["input_per_1m_usd"] == 0.80
        assert info["matched_model_id"] == "claude-3-5-haiku-latest"

    def test_found_false_for_unknown_model(self):
        info = pricing_module.lookup_model_info("anthropic", "claude-unknown-model")
        assert info["found"] is False
        assert info["input_per_1m_usd"] is None

    @pytest.mark.parametrize(
        "model,expected_input",
        [
            ("claude-haiku-4-5-20251001", 0.80),
            ("claude-sonnet-4-6", 3.00),
            ("claude-opus-4-7", 15.0),
        ],
    )
    def test_found_true_for_claude4_models(self, model, expected_input):
        info = pricing_module.lookup_model_info("anthropic", model)
        assert info["found"] is True
        assert info["input_per_1m_usd"] == expected_input
        assert info["matched_model_id"] == model

class TestInvalidateCache:
    def test_sets_cache_to_none(self):
        pricing_module._cache = [{"model_id": "existing"}]
        pricing_module.invalidate_cache()
        assert pricing_module._cache is None
