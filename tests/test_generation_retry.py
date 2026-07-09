"""Error-handling parity for knowledge/onboarding generation:
truncation -> 422, transient error -> one retry, provider error -> raised."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from onboarding.services import generation as G
from onboarding.services.generation import _raise_if_truncated, _generate_with_retry

class TestRaiseIfTruncated:
    def test_truncation_marker_maps_to_422(self):
        with pytest.raises(HTTPException) as ei:
            _raise_if_truncated(Exception("instructor: IncompleteOutputException hit"), "answer")
        assert ei.value.status_code == 422
        assert "cut off" in ei.value.detail

    def test_max_tokens_phrase_maps_to_422(self):
        with pytest.raises(HTTPException) as ei:
            _raise_if_truncated(
                Exception("stopped due to a max_tokens length limit"), "day content"
            )
        assert ei.value.status_code == 422

    def test_non_truncation_error_does_not_raise(self):
        # Returns None (no raise) so the caller can retry / map it.
        assert _raise_if_truncated(Exception("some unrelated error"), "answer") is None

class TestGenerateWithRetry:
    def test_retries_once_then_succeeds(self):
        calls = {"n": 0}

        def call():
            calls["n"] += 1
            if calls["n"] == 1:
                raise Exception("transient blip")
            return "ok"

        assert _generate_with_retry("openai", call, "answer") == "ok"
        assert calls["n"] == 2  # retried exactly once

    def test_returns_none_after_exhausting_retries(self):
        def call():
            raise Exception("still failing")

        assert _generate_with_retry("openai", call, "answer") is None

    def test_provider_error_is_raised_and_not_retried(self):
        calls = {"n": 0}

        def call():
            calls["n"] += 1
            raise Exception("429 quota exceeded")  # -> _raise_if_provider_error

        with pytest.raises(HTTPException) as ei:
            _generate_with_retry("gemini", call, "answer")
        assert ei.value.status_code == 429
        assert calls["n"] == 1  # raised immediately, no retry

    def test_truncation_is_raised_and_not_retried(self):
        calls = {"n": 0}

        def call():
            calls["n"] += 1
            raise Exception("IncompleteOutputException")

        with pytest.raises(HTTPException) as ei:
            _generate_with_retry("openai", call, "answer")
        assert ei.value.status_code == 422
        assert calls["n"] == 1  # a cut-off won't succeed on retry, so we don't retry

    def test_zero_attempts_returns_none(self):
        # Defensive post-loop fallback.
        assert _generate_with_retry("openai", lambda: "x", "answer", attempts=0) is None

class TestAnswerBlocksEndToEnd:
    """Prove the wiring: a real truncation/transient error inside the LLM call
    surfaces correctly through the actual knowledge-answer generator."""

    def _client(self, side_effect):
        c = MagicMock()
        c.chat.completions.create.side_effect = side_effect
        return c

    def test_truncation_surfaces_as_422(self):
        with (
            patch.object(
                G,
                "_build_client",
                return_value=self._client(Exception("IncompleteOutputException")),
            ),
            patch.object(G, "_token_kwargs", return_value={}),
        ):
            with pytest.raises(HTTPException) as ei:
                G.answer_blocks_from_context("q", "ctx", provider="openai", api_key="k", model="m")
        assert ei.value.status_code == 422

    def test_transient_then_success_retries_and_answers(self):
        block = MagicMock()
        block.model_dump.return_value = {"type": "paragraph", "content": "hi"}
        resp = MagicMock(blocks=[block], used_docs=True)
        calls = {"n": 0}

        def create(*a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise Exception("connection reset by peer - transient")
            return resp

        c = MagicMock()
        c.chat.completions.create.side_effect = create
        with (
            patch.object(G, "_build_client", return_value=c),
            patch.object(G, "_token_kwargs", return_value={}),
        ):
            out = G.answer_blocks_from_context(
                "q", "ctx", provider="openai", api_key="k", model="m"
            )
        assert calls["n"] == 2  # retried once
        assert out and out["blocks"][0]["content"] == "hi"

    def test_always_transient_returns_none(self):
        with (
            patch.object(G, "_build_client", return_value=self._client(Exception("still failing"))),
            patch.object(G, "_token_kwargs", return_value={}),
        ):
            out = G.answer_blocks_from_context(
                "q", "ctx", provider="openai", api_key="k", model="m"
            )
        assert out is None
