"""Tests for semantic retrieval over the knowledge base."""

from unittest.mock import MagicMock, patch

def _patch_session(target="onboarding.services.retrieval.Session"):
    patcher = patch(target)
    mock_cls = patcher.start()
    session_mock = MagicMock()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher, session_mock

class TestRetrieve:
    def test_returns_chunks(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = [
                ("chunk one", "Arch", "p1"),
                ("chunk two", "Setup", "p2"),
            ]
            with patch(
                "onboarding.services.retrieval.embedding_service.embed_query",
                return_value=[0.1, 0.2],
            ):
                from onboarding.services.retrieval import retrieve

                out = retrieve(1, "how do we deploy?", k=5)
            assert out == [
                {"content": "chunk one", "title": "Arch", "page_id": "p1"},
                {"content": "chunk two", "title": "Setup", "page_id": "p2"},
            ]
        finally:
            patcher.stop()

    def test_empty(self):
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.return_value = []
            with patch(
                "onboarding.services.retrieval.embedding_service.embed_query", return_value=[0.1]
            ):
                from onboarding.services.retrieval import retrieve

                assert retrieve(1, "q") == []
        finally:
            patcher.stop()

class TestRetrieveContext:
    def test_formats(self):
        with patch(
            "onboarding.services.retrieval.retrieve",
            return_value=[
                {"content": "c1", "title": "A", "page_id": "p1"},
                {"content": "c2", "title": "B", "page_id": "p2"},
            ],
        ):
            from onboarding.services.retrieval import retrieve_context

            ctx = retrieve_context(1, "q")
        assert "=== A ===\nc1" in ctx and "=== B ===\nc2" in ctx

    def test_empty(self):
        with patch("onboarding.services.retrieval.retrieve", return_value=[]):
            from onboarding.services.retrieval import retrieve_context

            assert retrieve_context(1, "q") == ""
