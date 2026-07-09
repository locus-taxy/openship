"""Tests for the chunker and the Gemini embedding service."""

from unittest.mock import patch

# ── chunking ──────────────────────────────────────────────────────────────────

class TestChunkText:
    def test_empty(self):
        from onboarding.services.chunking import chunk_text

        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_single_chunk(self):
        from onboarding.services.chunking import chunk_text

        assert chunk_text("hello world") == ["hello world"]

    def test_normalizes_whitespace(self):
        from onboarding.services.chunking import chunk_text

        assert chunk_text("hello   \n\n  world") == ["hello world"]

    def test_long_text_multiple_overlapping_chunks(self):
        from onboarding.services.chunking import chunk_text

        text = " ".join(f"word{i}" for i in range(4000))  # well over one chunk
        chunks = chunk_text(text, target_tokens=100, overlap_tokens=20)
        assert len(chunks) > 1
        # every chunk within the char budget (100 tokens * 4 chars, plus slack)
        assert all(len(c) <= 100 * 4 + 10 for c in chunks)
        # overlap: end of chunk 0 shares words with start of chunk 1
        assert chunks[0].split()[-1] in chunks[1]

    def test_estimate_tokens(self):
        from onboarding.services.chunking import estimate_tokens

        assert estimate_tokens("a" * 400) == 100
        assert estimate_tokens("") == 1

# ── embeddings ──────────────────────────────────────────────────────────────────

class _Vec:
    """Stands in for a fastembed output vector (a numpy array with .tolist())."""

    def __init__(self, values):
        self._values = values

    def tolist(self):
        return self._values

class _FakeModel:
    """Stands in for fastembed.TextEmbedding: .embed yields one vector per text."""

    def embed(self, texts):
        return iter([_Vec([float(i), float(i) + 0.5]) for i, _ in enumerate(texts)])

class TestEmbedTexts:
    def test_empty_returns_empty(self):
        from onboarding.services.embeddings import embed_texts

        assert embed_texts([]) == []

    def test_success(self):
        from onboarding.services import embeddings as E

        with patch.object(E, "_get_model", return_value=_FakeModel()):
            out = E.embed_texts(["a", "b"])
        assert out == [[0.0, 0.5], [1.0, 1.5]]

    def test_embed_query(self):
        from onboarding.services import embeddings as E

        with patch.object(E, "_get_model", return_value=_FakeModel()):
            assert E.embed_query("hi") == [0.0, 0.5]

class TestGetModel:
    def test_lazy_singleton(self):
        from onboarding.services import embeddings as E

        E._model = None
        sentinel = object()
        with patch("onboarding.services.embeddings.TextEmbedding", return_value=sentinel) as TE:
            first = E._get_model()
            second = E._get_model()
        assert first is sentinel and second is sentinel
        TE.assert_called_once()  # loaded once, then cached
        E._model = None  # reset so a real load isn't shadowed for other tests
