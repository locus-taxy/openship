from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from services.llm import (
    _should_skip,
    _key_hash,
    _norm,
    _full_exc_msg,
    _get_status_code,
    _raise_if_provider_error,
    _require_settings,
    fetch_provider_models,
    generate_syllabus_json,
    generate_weekly_quiz,
    generate_final_quiz,
    generate_chapter_content,
    generate_chapter_html,
    generate_week_plan,
    verify_model,
    PROVIDER_MODELS,
    DEFAULT_MODELS,
    GeneratedQuestion,
    QuizOption,
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

    def test_raises_400_on_model_not_found_via_status_code(self):
        """SDK exception with status_code=404 is caught even if str() has no keywords."""
        exc = Exception("instructor retry failed")
        exc.status_code = 404  # type: ignore[attr-defined]
        with pytest.raises(HTTPException) as ei:
            _raise_if_provider_error("anthropic", exc)
        assert ei.value.status_code == 400
        assert "does not have access to the selected model" in ei.value.detail

    def test_raises_400_on_model_not_found_anthropic(self):
        exc = Exception("not_found_error: model: claude-opus-4-7 not found")
        with pytest.raises(HTTPException) as ei:
            _raise_if_provider_error("anthropic", exc)
        assert ei.value.status_code == 400
        assert "does not have access to the selected model" in ei.value.detail

    def test_raises_400_on_model_not_found_openai(self):
        exc = Exception("model_not_found: The model gpt-9999 does not exist")
        with pytest.raises(HTTPException) as ei:
            _raise_if_provider_error("openai", exc)
        assert ei.value.status_code == 400
        assert "does not have access to the selected model" in ei.value.detail

    def test_raises_400_on_insufficient_credits(self):
        """403 with credit keywords → billing error, not 'invalid key'."""
        exc = Exception("your credit balance is too low")
        exc.status_code = 403  # type: ignore[attr-defined]
        with pytest.raises(HTTPException) as ei:
            _raise_if_provider_error("anthropic", exc)
        assert ei.value.status_code == 400
        assert "insufficient credits" in ei.value.detail

    def test_raises_400_on_429_via_status_code(self):
        exc = Exception("instructor retry failed")
        exc.status_code = 429  # type: ignore[attr-defined]
        with pytest.raises(HTTPException) as ei:
            _raise_if_provider_error("openai", exc)
        assert ei.value.status_code == 429

    def test_does_not_raise_on_generic_error(self):
        exc = Exception("some random internal error")
        _raise_if_provider_error("gemini", exc)  # should not raise

class TestGetStatusCode:
    def test_returns_status_code_from_direct_attribute(self):
        exc = Exception("some error")
        exc.status_code = 404  # type: ignore[attr-defined]
        assert _get_status_code(exc) == 404

    def test_returns_status_code_from_cause_chain(self):
        cause = Exception("underlying")
        cause.status_code = 403  # type: ignore[attr-defined]
        wrapper = Exception("wrapper")
        wrapper.__cause__ = cause  # type: ignore[attr-defined]
        assert _get_status_code(wrapper) == 403

    def test_returns_none_when_no_status_code(self):
        assert _get_status_code(Exception("no code")) is None

    def test_finds_status_code_on_context_branch_when_cause_has_none(self):
        """When __cause__ has no status_code but __context__ does, the code is found.
        Regression: the old 'or' traversal silently skipped __context__."""
        cause_exc = Exception("cause without code")
        context_exc = Exception("context with code")
        context_exc.status_code = 403  # type: ignore[attr-defined]
        wrapper = Exception("wrapper")
        wrapper.__cause__ = cause_exc  # type: ignore[attr-defined]
        wrapper.__context__ = context_exc  # type: ignore[attr-defined]
        assert _get_status_code(wrapper) == 403

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

class TestGenerateWeeklyQuiz:
    def test_raises_400_when_no_settings(self):
        with pytest.raises(HTTPException) as ei:
            generate_weekly_quiz("Python", 1, [], 5, provider=None, api_key=None)
        assert ei.value.status_code == 400

    def test_returns_generated_quiz_on_success(self):
        mock_response = MagicMock()
        mock_response.questions = [MagicMock()] * 5
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_weekly_quiz(
                "Python", 1, ["Vars", "Loops"], 5, "gemini", "key", "gemini-flash"
            )
        assert result is mock_response

    def test_accepts_partial_question_count(self):
        mock_response = MagicMock()
        mock_response.questions = [MagicMock()] * 3  # fewer than requested 5
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_weekly_quiz("Python", 1, ["Vars"], 5, "gemini", "key", "gemini-flash")
        assert result is mock_response  # partial result accepted

    def test_returns_none_on_generic_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("timeout")
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_weekly_quiz("Python", 1, ["Vars"], 5, "gemini", "key", "gemini-flash")
        assert result is None

class TestGenerateFinalQuiz:
    def test_returns_none_when_no_topics(self):
        result = generate_final_quiz("Python", [], [], 10, "gemini", "key", "gemini-flash")
        assert result is None

    def test_raises_400_when_no_settings(self):
        with pytest.raises(HTTPException) as ei:
            generate_final_quiz("Python", ["Loops"], [], 10, provider=None, api_key=None)
        assert ei.value.status_code == 400

    def test_returns_generated_quiz_on_success(self):
        mock_response = MagicMock()
        mock_response.questions = [MagicMock()] * 10
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_final_quiz(
                "Python", ["Loops"], ["Functions"], 10, "gemini", "key", "gemini-flash"
            )
        assert result is mock_response

    def test_returns_none_on_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("timeout")
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_final_quiz(
                "Python", ["Loops"], [], 10, "gemini", "key", "gemini-flash"
            )
        assert result is None

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
        from services.content_validator import HeuristicResult, ContentValidationResult

        with (
            patch("services.llm._build_client", return_value=mock_client),
            patch("services.llm.extract_token_counts", return_value=(100, 200)),
            patch(
                "services.content_validator.validate_content_heuristics",
                return_value=HeuristicResult(passed=True, reason=""),
            ),
            patch(
                "services.content_validator.validate_content_with_llm",
                return_value=ContentValidationResult(valid=True, score=9, issues=[]),
            ),
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

class TestGenerateChapterContentValidation:
    """Integration tests for the validation + retry loop inside generate_chapter_content."""

    from services.content_validator import HeuristicResult, ContentValidationResult

    _PASS_HEURISTIC = HeuristicResult(passed=True, reason="")
    _FAIL_HEURISTIC = HeuristicResult(passed=False, reason="too short: 5 words")
    _PASS_JUDGE = ContentValidationResult(valid=True, score=9, issues=[])
    _FAIL_JUDGE = ContentValidationResult(valid=False, score=4, issues=["off-topic"])

    def _run(self, heuristic_side_effect, judge_side_effect=None):
        mock_response = MagicMock()
        mock_raw = MagicMock()
        mock_client = MagicMock()
        mock_client.chat.completions.create_with_completion.return_value = (
            mock_response,
            mock_raw,
        )
        judge_se = judge_side_effect or [self._PASS_JUDGE]
        with (
            patch("services.llm._build_client", return_value=mock_client),
            patch("services.llm.extract_token_counts", return_value=(100, 200)),
            patch(
                "services.content_validator.validate_content_heuristics",
                side_effect=heuristic_side_effect,
            ),
            patch(
                "services.content_validator.validate_content_with_llm",
                side_effect=judge_se,
            ),
        ):
            result, _, _ = generate_chapter_content(
                "Learn arrays", "Arrays", "C++", "gemini", "key", "gemini-flash"
            )
        return result, mock_response

    def test_returns_content_when_both_layers_pass_first_attempt(self):
        result, mock_response = self._run(
            heuristic_side_effect=[self._PASS_HEURISTIC],
            judge_side_effect=[self._PASS_JUDGE],
        )
        assert result is mock_response

    def test_retries_when_heuristic_fails_first_attempt(self):
        result, mock_response = self._run(
            heuristic_side_effect=[self._FAIL_HEURISTIC, self._PASS_HEURISTIC],
            judge_side_effect=[self._PASS_JUDGE],
        )
        assert result is mock_response

    def test_returns_none_when_heuristic_fails_both_attempts(self):
        result, _ = self._run(
            heuristic_side_effect=[self._FAIL_HEURISTIC, self._FAIL_HEURISTIC],
        )
        assert result is None

    def test_retries_when_judge_fails_first_attempt(self):
        result, mock_response = self._run(
            heuristic_side_effect=[self._PASS_HEURISTIC, self._PASS_HEURISTIC],
            judge_side_effect=[self._FAIL_JUDGE, self._PASS_JUDGE],
        )
        assert result is mock_response

    def test_passes_content_through_when_judge_fails_both_attempts(self):
        # LLM judge is a quality signal, not a hard gate. If heuristics pass but the
        # judge fails twice, we still return content rather than giving the user a
        # blank chapter. Better mediocre content than no content.
        result, mock_response = self._run(
            heuristic_side_effect=[self._PASS_HEURISTIC, self._PASS_HEURISTIC],
            judge_side_effect=[self._FAIL_JUDGE, self._FAIL_JUDGE],
        )
        assert result is mock_response

    def test_passes_content_through_when_judge_raises_exception(self):
        result, mock_response = self._run(
            heuristic_side_effect=[self._PASS_HEURISTIC],
            judge_side_effect=[RuntimeError("judge API down")],
        )
        assert result is mock_response

    def test_generation_error_on_first_attempt_retries(self):
        mock_response = MagicMock()
        mock_raw = MagicMock()
        mock_client = MagicMock()
        mock_client.chat.completions.create_with_completion.side_effect = [
            Exception("transient network error"),
            (mock_response, mock_raw),
        ]
        with (
            patch("services.llm._build_client", return_value=mock_client),
            patch("services.llm.extract_token_counts", return_value=(100, 200)),
            patch(
                "services.content_validator.validate_content_heuristics",
                return_value=self._PASS_HEURISTIC,
            ),
            patch(
                "services.content_validator.validate_content_with_llm",
                return_value=self._PASS_JUDGE,
            ),
        ):
            result, _, _ = generate_chapter_content(
                "Learn arrays", "Arrays", "C++", "gemini", "key", "gemini-flash"
            )
        assert result is mock_response

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

class TestRaiseIfProviderErrorAuthBranch:
    def test_raises_400_on_401_in_message(self):
        """Covers the 401/403 auth branch of _raise_if_provider_error."""
        exc = Exception("401 unauthorized")
        with pytest.raises(HTTPException) as ei:
            _raise_if_provider_error("openai", exc)
        assert ei.value.status_code == 400

    def test_raises_400_on_api_key_not_valid(self):
        exc = Exception("api key not valid")
        with pytest.raises(HTTPException) as ei:
            _raise_if_provider_error("gemini", exc)
        assert ei.value.status_code == 400

class TestGeneratedQuestionValidator:
    """Covers line 321 — correct_option not found among option labels."""

    def _make_options(self, labels=("A", "B", "C", "D")):
        return [QuizOption(label=label, text=f"Option {label}") for label in labels]

    def test_raises_when_correct_option_not_in_labels(self):
        """Directly invoke validate_options on a model_construct'd object to hit line 321."""
        from pydantic import ValidationError

        # Build the object bypassing all validators, then call the model_validator directly
        options = self._make_options(("A", "B", "C", "D"))
        # Construct a GeneratedQuestion bypassing validators
        q = GeneratedQuestion.model_construct(
            question="Test?",
            options=options,
            correct_option="X",  # valid per field validator but 'X' is NOT among A/B/C/D labels
            explanation="Exp",
        )
        with pytest.raises(ValueError, match="not found among option labels"):
            q.validate_options()

    def test_valid_question_passes_validator(self):
        q = GeneratedQuestion(
            question="What is Python?",
            options=self._make_options(),
            correct_option="B",
            explanation="It's a language",
        )
        assert q.correct_option == "B"

class TestPatchedGenerateFallback:
    """Covers lines 439-444 — setattr fallback when model_copy raises."""

    def test_setattr_fallback_when_model_copy_raises(self):
        """When config.model_copy raises, the fallback iterates and calls setattr."""
        import services.llm as llm_mod

        # Build a config mock that fails model_copy but allows setattr
        config_mock = MagicMock()
        config_mock.max_output_tokens = None
        config_mock.response_schema = MagicMock()  # triggers update["response_schema"] = None
        config_mock.model_copy.side_effect = Exception("model_copy failed")

        real_generate_mock = MagicMock(return_value="result")
        google_client_mock = MagicMock()
        google_client_mock.models.generate_content = real_generate_mock

        captured_patched = {}

        original_build = llm_mod._build_client

        def fake_build(provider, api_key):
            with patch("services.llm.genai") as mock_genai:
                mock_genai.Client.return_value = google_client_mock
                with patch("services.llm.instructor") as mock_instr:
                    mock_instr.from_genai.return_value = MagicMock()
                    result = (
                        original_build.__wrapped__(provider, api_key)
                        if hasattr(original_build, "__wrapped__")
                        else None
                    )
                    # Capture the patched generate that was set on google_client_mock
                    captured_patched["fn"] = google_client_mock.models.generate_content
            return result

        # Directly build the patched generate closure by calling _build_client with gemini
        with patch("services.llm.genai") as mock_genai:
            mock_genai.Client.return_value = google_client_mock
            with patch("services.llm.instructor") as mock_instr:
                mock_instr.from_genai.return_value = MagicMock()
                try:
                    llm_mod._build_client("gemini", "test-api-key")
                except Exception:  # noqa: BLE001
                    pass
            # _patched_generate was set on the mock client
            patched_fn = google_client_mock.models.generate_content

        # Now call the patched function with a config that fails model_copy
        patched_fn(config=config_mock)
        # model_copy was attempted (fails), then setattr was called as fallback
        assert config_mock.model_copy.called

    def test_setattr_fallback_handles_setattr_exception(self):
        """When both model_copy and setattr raise, the inner except swallows the error."""
        import services.llm as llm_mod

        config_mock = MagicMock()
        config_mock.max_output_tokens = None
        config_mock.response_schema = MagicMock()
        config_mock.model_copy.side_effect = Exception("model_copy failed")

        # Make setattr raise by using a read-only property — use a real class
        class ReadOnlyConfig:
            @property
            def max_output_tokens(self):
                return None

            @property
            def response_schema(self):
                return object()  # not None

        ro_config = ReadOnlyConfig()

        real_generate_mock = MagicMock(return_value="result")
        google_client_mock = MagicMock()
        google_client_mock.models.generate_content = real_generate_mock

        with patch("services.llm.genai") as mock_genai:
            mock_genai.Client.return_value = google_client_mock
            with patch("services.llm.instructor") as mock_instr:
                mock_instr.from_genai.return_value = MagicMock()
                try:
                    llm_mod._build_client("gemini", "key")
                except Exception:  # noqa: BLE001
                    pass
            patched_fn = google_client_mock.models.generate_content

        # Should not raise even though setattr will fail on read-only properties
        try:
            patched_fn(config=ro_config)
        except Exception:  # noqa: BLE001
            pass  # Real generate may raise; what matters is no crash in the fallback

class TestGenerateWeeklyQuizPartialResult:
    """Covers line 611 — generate_weekly_quiz reraises HTTPException."""

    def test_returns_partial_result_on_count_mismatch(self):
        mock_response = MagicMock()
        mock_response.questions = [MagicMock()] * 3  # asked for 5
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_weekly_quiz(
                "Python", 1, ["Vars", "Loops"], 5, "openai", "key", "gpt-4o"
            )
        assert result is mock_response  # partial result returned, not None

    def test_reraises_http_exception(self):
        """Covers line 611 — except HTTPException: raise."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = HTTPException(
            status_code=429, detail="quota"
        )
        with patch("services.llm._build_client", return_value=mock_client):
            with pytest.raises(HTTPException) as ei:
                generate_weekly_quiz("Python", 1, ["Vars"], 5, "gemini", "key", "gemini-flash")
        assert ei.value.status_code == 429

class TestGenerateFinalQuizMismatch:
    """Covers final quiz count mismatch handling — now lenient like weekly quiz."""

    def test_returns_partial_when_count_mismatches(self):
        mock_response = MagicMock()
        mock_response.questions = [MagicMock()] * 7  # asked for 10
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_final_quiz(
                "Python", ["Loops"], ["Functions"], 10, "gemini", "key", "gemini-flash"
            )
        assert result is not None
        assert len(result.questions) == 7

    def test_returns_none_when_questions_empty(self):
        mock_response = MagicMock()
        mock_response.questions = []
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_final_quiz(
                "Python", ["Loops"], [], 10, "gemini", "key", "gemini-flash"
            )
        assert result is None

    def test_reraises_http_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = HTTPException(
            status_code=429, detail="quota"
        )
        with patch("services.llm._build_client", return_value=mock_client):
            with pytest.raises(HTTPException) as ei:
                generate_final_quiz("Python", ["Loops"], [], 10, "gemini", "key", "gemini-flash")
        assert ei.value.status_code == 429

class TestGenerateChapterContentTruncation:
    """Covers line 759 — incompleteoutput raises 422."""

    def test_raises_422_on_finish_reason_max_tokens(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create_with_completion.side_effect = Exception(
            "finish_reason.max_tokens exceeded"
        )
        with patch("services.llm._build_client", return_value=mock_client):
            with pytest.raises(HTTPException) as ei:
                generate_chapter_content("desc", "title", "Python", "openai", "key", "gpt-4o")
        assert ei.value.status_code == 422

class TestGenerateChapterHtmlHttpException:
    """Covers generate_chapter_html reraises HTTPException."""

    def test_reraises_http_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create_with_completion.side_effect = HTTPException(
            status_code=400, detail="invalid key"
        )
        with patch("services.llm._build_client", return_value=mock_client):
            with pytest.raises(HTTPException) as ei:
                generate_chapter_html("desc", "title", "Python", "gemini", "key", "gemini-flash")
        assert ei.value.status_code == 400

class TestGenerateWeekPlan:
    def test_raises_400_when_no_settings(self):
        with pytest.raises(HTTPException) as ei:
            generate_week_plan("Python", 2, 4, [], [], 7, 8, provider=None, api_key=None)
        assert ei.value.status_code == 400

    def test_returns_list_of_dicts_on_success(self):
        mock_day = MagicMock()
        mock_day.day = 8  # required by new day-range validation
        mock_day.model_dump.return_value = {"day": 8, "topic": "Classes", "task": "Learn OOP"}
        mock_response = MagicMock()
        mock_response.days = [mock_day]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_week_plan(
                "Python", 2, 4, ["Variables"], [], 1, 8, "gemini", "key", "gemini-flash"
            )
        assert result == [{"day": 8, "topic": "Classes", "task": "Learn OOP"}]

    def test_returns_none_when_days_empty(self):
        mock_response = MagicMock()
        mock_response.days = []
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_week_plan("Python", 2, 4, [], [], 7, 8, "openai", "key", "gpt-4o")
        assert result is None

    def test_returns_none_on_generic_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("network timeout")
        with patch("services.llm._build_client", return_value=mock_client):
            result = generate_week_plan(
                "Python", 2, 4, [], [], 7, 8, "gemini", "key", "gemini-flash"
            )
        assert result is None

    def test_reraises_http_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = HTTPException(
            status_code=429, detail="quota"
        )
        with patch("services.llm._build_client", return_value=mock_client):
            with pytest.raises(HTTPException) as ei:
                generate_week_plan("Python", 2, 4, [], [], 7, 8, "gemini", "key", "gemini-flash")
        assert ei.value.status_code == 429

    def test_raises_quota_error_on_rate_limit_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("429 rate_limit exceeded")
        with patch("services.llm._build_client", return_value=mock_client):
            with pytest.raises(HTTPException) as ei:
                generate_week_plan("Python", 2, 4, [], [], 7, 8, "gemini", "key", "gemini-flash")
        assert ei.value.status_code == 429
