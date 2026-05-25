from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from services.llm import (
    _should_skip,
    _key_hash,
    _norm,
    _full_exc_msg,
    _raise_if_provider_error,
    _require_settings,
    fetch_provider_models,
    generate_syllabus_json,
    generate_quiz,
    generate_chapter_content,
    generate_chapter_html,
    verify_model,
    PROVIDER_MODELS,
    DEFAULT_MODELS,
)

class TestShouldSkip:
    def test_skips_embedding_models(self):
        assert _should_skip("text-embedding-ada-002") is True

    def test_skips_vision_models(self):
        assert _should_skip("gemini-pro-vision") is True

    def test_skips_tts_models(self):
        assert _should_skip("tts-1") is True

    def test_skips_image_models(self):
        assert _should_skip("gemini-image-gen") is True

    def test_does_not_skip_valid_model(self):
        assert _should_skip("gemini-2.5-flash") is False

    def test_does_not_skip_gpt4(self):
        assert _should_skip("gpt-4o") is False

class TestKeyHash:
    def test_returns_16_char_hex(self):
        result = _key_hash("my-api-key")
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_different_keys_produce_different_hashes(self):
        assert _key_hash("key-1") != _key_hash("key-2")

    def test_same_key_produces_same_hash(self):
        assert _key_hash("stable-key") == _key_hash("stable-key")

class TestNorm:
    def test_returns_none_for_none(self):
        assert _norm(None) is None

    def test_strips_whitespace(self):
        assert _norm("  hello  ") == "hello"

    def test_returns_none_for_blank_string(self):
        assert _norm("   ") is None

    def test_returns_value_unchanged(self):
        assert _norm("gemini") == "gemini"

class TestFullExcMsg:
    def test_includes_exception_message(self):
        exc = ValueError("something went wrong")
        result = _full_exc_msg(exc)
        assert "something went wrong" in result

    def test_follows_cause_chain(self):
        inner = ValueError("inner error")
        outer = RuntimeError("outer error")
        outer.__cause__ = inner
        result = _full_exc_msg(outer)
        assert "outer error" in result
        assert "inner error" in result

    def test_handles_circular_reference(self):
        exc = ValueError("circular")
        exc.__cause__ = exc
        result = _full_exc_msg(exc)
        assert "circular" in result

class TestRaiseIfProviderError:
    def test_raises_429_on_quota_error(self):
        exc = Exception("429 quota exceeded")
        with pytest.raises(HTTPException) as ei:
            _raise_if_provider_error("gemini", exc)
        assert ei.value.status_code == 429

    def test_raises_429_on_resource_exhausted(self):
        exc = Exception("resource_exhausted: rate limit")
        with pytest.raises(HTTPException) as ei:
            _raise_if_provider_error("gemini", exc)
        assert ei.value.status_code == 429

    def test_raises_429_on_too_many_requests(self):
        exc = Exception("too many requests sent")
        with pytest.raises(HTTPException) as ei:
            _raise_if_provider_error("openai", exc)
        assert ei.value.status_code == 429

    def test_raises_400_on_invalid_api_key(self):
        exc = Exception("401 unauthorized: api key not valid")
        with pytest.raises(HTTPException) as ei:
            _raise_if_provider_error("gemini", exc)
        assert ei.value.status_code == 400

    def test_raises_400_on_403_auth_error(self):
        exc = Exception("403 forbidden")
        with pytest.raises(HTTPException) as ei:
            _raise_if_provider_error("openai", exc)
        assert ei.value.status_code == 400

    def test_does_not_raise_on_generic_error(self):
        exc = Exception("some random internal error")
        _raise_if_provider_error("gemini", exc)  # should not raise

class TestRequireSettings:
    def test_raises_400_when_provider_missing(self):
        with pytest.raises(HTTPException) as ei:
            _require_settings(None, "api-key")
        assert ei.value.status_code == 400

    def test_raises_400_when_api_key_missing(self):
        with pytest.raises(HTTPException) as ei:
            _require_settings("gemini", None)
        assert ei.value.status_code == 400

    def test_raises_400_on_unsupported_provider(self):
        with pytest.raises(HTTPException) as ei:
            _require_settings("unknown-provider", "key")
        assert ei.value.status_code == 400

    def test_returns_normalized_values(self):
        p, k = _require_settings("  gemini  ", "  my-key  ")
        assert p == "gemini"
        assert k == "my-key"

class TestFetchProviderModels:
    def test_returns_fallback_on_exception(self):
        with patch("services.llm.genai") as mock_genai:
            mock_genai.Client.side_effect = Exception("network error")
            result = fetch_provider_models("gemini", "bad-key")
        assert result == PROVIDER_MODELS.get("gemini", [])

    def test_returns_fallback_for_anthropic(self):
        result = fetch_provider_models("anthropic", "key")
        assert result == PROVIDER_MODELS["anthropic"]

    def test_gemini_filters_and_returns_models(self):
        mock_model = MagicMock()
        mock_model.name = "models/gemini-2.5-flash"
        mock_model.supported_actions = ["generateContent"]
        mock_client = MagicMock()
        mock_client.models.list.return_value = [mock_model]
        with patch("services.llm.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = fetch_provider_models("gemini", "test-key-" + "x" * 20)
        assert "gemini-2.5-flash" in result

    def test_openai_filters_gpt_models(self):
        mock_m1 = MagicMock()
        mock_m1.id = "gpt-4o"
        mock_m2 = MagicMock()
        mock_m2.id = "whisper-1"  # should be filtered
        mock_client = MagicMock()
        mock_client.models.list.return_value.data = [mock_m1, mock_m2]
        with patch("services.llm.OpenAI") as mock_openai_cls:
            mock_openai_cls.return_value = mock_client
            result = fetch_provider_models("openai", "test-key-" + "x" * 20)
        assert "gpt-4o" in result
        assert "whisper-1" not in result

    def test_uses_cache_on_second_call(self):
        import services.llm as llm_mod

        cache_key = ("gemini", _key_hash("cached-key"))
        import time

        llm_mod._model_cache[cache_key] = (time.time(), ["gemini-cached-model"])
        result = fetch_provider_models("gemini", "cached-key")
        assert result == ["gemini-cached-model"]
        del llm_mod._model_cache[cache_key]

class TestGenerateSyllabusJson:
    def test_raises_400_when_no_settings(self):
        with pytest.raises(HTTPException) as ei:
            generate_syllabus_json("Python", 30, 2, provider=None, api_key=None)
        assert ei.value.status_code == 400

    def test_returns_list_on_success(self):
        mock_month = MagicMock()
        mock_month.model_dump.return_value = {"month": 1, "weeks": []}
        mock_response = MagicMock()
        mock_response.months = [mock_month]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_syllabus_json("Python", 30, 2, "gemini", "key", "gemini-flash")
        assert result == [{"month": 1, "weeks": []}]

    def test_returns_none_on_generic_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("network error")
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_syllabus_json("Python", 30, 2, "gemini", "key", "gemini-flash")
        assert result is None

    def test_reraises_http_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = HTTPException(
            status_code=429, detail="quota"
        )
        with patch("services.llm._build_client", return_value=mock_client):
            with pytest.raises(HTTPException) as ei:
                generate_syllabus_json("Python", 30, 2, "gemini", "key", "gemini-flash")
        assert ei.value.status_code == 429

    def test_raises_429_on_quota_error_in_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("429 rate_limit exceeded")
        with patch("services.llm._build_client", return_value=mock_client):
            with pytest.raises(HTTPException) as ei:
                generate_syllabus_json("Python", 30, 2, "gemini", "key", "gemini-flash")
        assert ei.value.status_code == 429

class TestGenerateQuiz:
    def test_raises_400_when_no_settings(self):
        with pytest.raises(HTTPException) as ei:
            generate_quiz("Python", [], "beginner", 10, provider=None, api_key=None)
        assert ei.value.status_code == 400

    def test_returns_generated_quiz_on_success(self):
        mock_response = MagicMock()
        mock_response.questions = [MagicMock()] * 10
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_quiz(
                "Python", ["Vars", "Loops"], "beginner", 10, "gemini", "key", "gemini-flash"
            )
        assert result is mock_response

    def test_returns_none_when_question_count_mismatch(self):
        mock_response = MagicMock()
        mock_response.questions = [MagicMock()] * 5  # expected 10
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_quiz(
                "Python", ["Vars"], "beginner", 10, "gemini", "key", "gemini-flash"
            )
        assert result is None

    def test_returns_none_on_generic_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("timeout")
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_quiz(
                "Python", ["Vars"], "beginner", 10, "gemini", "key", "gemini-flash"
            )
        assert result is None

    def test_normalizes_invalid_difficulty(self):
        mock_response = MagicMock()
        mock_response.questions = [MagicMock()] * 10
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_quiz(
                "Python", ["Vars"], "invalid-level", 10, "gemini", "key", "gemini-flash"
            )
        assert result is mock_response

class TestGenerateChapterContent:
    def test_raises_400_when_no_settings(self):
        with pytest.raises(HTTPException) as ei:
            generate_chapter_content("desc", "title", "Python", provider=None, api_key=None)
        assert ei.value.status_code == 400

    def test_returns_content_on_success(self):
        mock_response = MagicMock()
        mock_raw = MagicMock()
        mock_client = MagicMock()
        mock_client.chat.completions.create_with_completion.return_value = (mock_response, mock_raw)
        with (
            patch("services.llm._build_client", return_value=mock_client),
            patch("services.llm.extract_token_counts", return_value=(100, 200)),
        ):
            result, inp, out = generate_chapter_content(
                "Learn vars", "Variables", "Python", "gemini", "key", "gemini-flash"
            )
        assert result is mock_response
        assert inp == 100
        assert out == 200

    def test_returns_none_on_generic_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create_with_completion.side_effect = Exception(
            "network failure"
        )
        with patch("services.llm._build_client", return_value=mock_client):
            result, inp, out = generate_chapter_content(
                "desc", "title", "Python", "openai", "key", "gpt-4o"
            )
        assert result is None
        assert inp is None
        assert out is None

    def test_raises_422_on_truncation_error(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create_with_completion.side_effect = Exception(
            "incompleteoutput due to a max_tokens length limit"
        )
        with patch("services.llm._build_client", return_value=mock_client):
            with pytest.raises(HTTPException) as ei:
                generate_chapter_content("desc", "title", "Python", "openai", "key", "gpt-4o")
        assert ei.value.status_code == 422

    def test_reraises_http_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create_with_completion.side_effect = HTTPException(
            status_code=429, detail="quota"
        )
        with patch("services.llm._build_client", return_value=mock_client):
            with pytest.raises(HTTPException) as ei:
                generate_chapter_content("desc", "title", "Python", "gemini", "key", "gemini-flash")
        assert ei.value.status_code == 429

class TestGenerateChapterHtml:
    def test_raises_400_when_no_settings(self):
        with pytest.raises(HTTPException) as ei:
            generate_chapter_html("desc", "title", "Python", provider=None, api_key=None)
        assert ei.value.status_code == 400

    def test_returns_html_on_success(self):
        mock_response = MagicMock()
        mock_response.html = "<p>Hello</p>"
        mock_raw = MagicMock()
        mock_client = MagicMock()
        mock_client.chat.completions.create_with_completion.return_value = (mock_response, mock_raw)
        with (
            patch("services.llm._build_client", return_value=mock_client),
            patch("services.llm.extract_token_counts", return_value=(50, 100)),
        ):
            html, inp, out = generate_chapter_html(
                "Learn vars", "Variables", "Python", "gemini", "key", "gemini-flash"
            )
        assert html == "<p>Hello</p>"
        assert inp == 50
        assert out == 100

    def test_returns_none_on_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create_with_completion.side_effect = Exception("server error")
        with patch("services.llm._build_client", return_value=mock_client):
            html, inp, out = generate_chapter_html(
                "desc", "title", "Python", "anthropic", "key", "claude-opus-4-7"
            )
        assert html is None
        assert inp is None
        assert out is None

class TestVerifyModel:
    def test_returns_ok_true_on_success(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock()
        with patch("services.llm._build_client", return_value=mock_client):
            result = verify_model("gemini", "key", "gemini-flash")
        assert result == {"ok": True}

    def test_returns_ok_false_when_model_not_found(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("model not found 404")
        with patch("services.llm._build_client", return_value=mock_client):
            result = verify_model("gemini", "key", "bad-model")
        assert result["ok"] is False
        assert "reason" in result

    def test_returns_ok_true_on_quota_error(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("429 quota exhausted")
        with patch("services.llm._build_client", return_value=mock_client):
            result = verify_model("gemini", "key", "gemini-flash")
        assert result["ok"] is True
        assert "note" in result

    def test_returns_ok_false_on_generic_error(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("some random error")
        with patch("services.llm._build_client", return_value=mock_client):
            result = verify_model("gemini", "key", "gemini-flash")
        assert result["ok"] is False

    def test_returns_ok_false_on_http_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = HTTPException(
            status_code=400, detail="invalid key"
        )
        with patch("services.llm._build_client", return_value=mock_client):
            result = verify_model("gemini", "key", "gemini-flash")
        assert result["ok"] is False
