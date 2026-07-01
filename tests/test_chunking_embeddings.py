"""Tests for the chunker and the Gemini embedding service."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

# ── chunking ──────────────────────────────────────────────────────────────────

class TestChunkText:
    def test_empty(self):
        from services.chunking import chunk_text

        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_single_chunk(self):
        from services.chunking import chunk_text

        assert chunk_text("hello world") == ["hello world"]

    def test_normalizes_whitespace(self):
        from services.chunking import chunk_text

        assert chunk_text("hello   \n\n  world") == ["hello world"]

    def test_long_text_multiple_overlapping_chunks(self):
        from services.chunking import chunk_text

        text = " ".join(f"word{i}" for i in range(4000))  # well over one chunk
        chunks = chunk_text(text, target_tokens=100, overlap_tokens=20)
        assert len(chunks) > 1
        # every chunk within the char budget (100 tokens * 4 chars, plus slack)
        assert all(len(c) <= 100 * 4 + 10 for c in chunks)
        # overlap: end of chunk 0 shares words with start of chunk 1
        assert chunks[0].split()[-1] in chunks[1]

    def test_estimate_tokens(self):
        from services.chunking import estimate_tokens

        assert estimate_tokens("a" * 400) == 100
        assert estimate_tokens("") == 1

# ── embeddings ──────────────────────────────────────────────────────────────────

class TestEmbedTexts:
    def test_empty_returns_empty(self):
        from services.embeddings import embed_texts

        assert embed_texts([]) == []

    def test_not_configured_503(self):
        from services.embeddings import embed_texts

        with patch("config.GEMINI_EMBEDDING_API_KEY", None):
            with pytest.raises(HTTPException) as exc:
                embed_texts(["hi"])
            assert exc.value.status_code == 503

    def test_success(self):
        from services.embeddings import embed_texts

        with patch("services.embeddings._embed_batch", return_value=[[0.1, 0.2], [0.3, 0.4]]):
            out = embed_texts(["a", "b"], api_key="k")
        assert out == [[0.1, 0.2], [0.3, 0.4]]

    def test_batches(self):
        from services.embeddings import embed_texts

        calls = []

        def fake(api_key, model, batch):
            calls.append(len(batch))
            return [[0.0] for _ in batch]

        with patch("services.embeddings._embed_batch", side_effect=fake):
            out = embed_texts([f"t{i}" for i in range(250)], api_key="k", batch_size=100)
        assert len(out) == 250
        assert calls == [100, 100, 50]

    def test_backoff_then_success(self):
        from services.embeddings import embed_texts

        attempts = {"n": 0}

        def flaky(api_key, model, batch):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("429")
            return [[1.0] for _ in batch]

        with (
            patch("services.embeddings._embed_batch", side_effect=flaky),
            patch("services.embeddings._sleep"),
        ):
            out = embed_texts(["a"], api_key="k")
        assert out == [[1.0]]
        assert attempts["n"] == 2

    def test_backoff_exhausted_502(self):
        from services.embeddings import embed_texts

        with (
            patch("services.embeddings._embed_batch", side_effect=RuntimeError("boom")),
            patch("services.embeddings._sleep"),
        ):
            with pytest.raises(HTTPException) as exc:
                embed_texts(["a"], api_key="k")
            assert exc.value.status_code == 502

    def test_embed_query(self):
        from services.embeddings import embed_query

        with patch("services.embeddings._embed_batch", return_value=[[0.5, 0.6]]):
            assert embed_query("hi", api_key="k") == [0.5, 0.6]

class TestEmbedBatch:
    def test_calls_genai_client(self):
        from services.embeddings import _embed_batch

        class _Emb:
            def __init__(self, v):
                self.values = v

        class _Resp:
            embeddings = [_Emb([0.1, 0.2]), _Emb([0.3, 0.4])]

        with patch("services.embeddings.genai.Client") as Client:
            Client.return_value.models.embed_content.return_value = _Resp()
            out = _embed_batch("k", "text-embedding-004", ["a", "b"])
        assert out == [[0.1, 0.2], [0.3, 0.4]]
