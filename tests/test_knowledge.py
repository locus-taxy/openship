"""Tests for the freeform knowledge Q&A (RAG) endpoint."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

class TestKnowledgeService:
    def test_blank_question_400(self):
        from services.knowledge import query

        with pytest.raises(HTTPException) as exc:
            query(1, "   ", "openai", "k", None)
        assert exc.value.status_code == 400

    def test_no_chunks_404(self):
        from services.knowledge import query

        with patch("services.knowledge.retrieval_service.retrieve", return_value=[]):
            with pytest.raises(HTTPException) as exc:
                query(1, "how do we deploy?", "openai", "k", None)
            assert exc.value.status_code == 404

    def test_llm_fails_500(self):
        chunks = [{"content": "c", "title": "A", "page_id": "p1"}]
        with (
            patch("services.knowledge.retrieval_service.retrieve", return_value=chunks),
            patch("services.knowledge.llm_service.answer_from_context", return_value=None),
        ):
            from services.knowledge import query

            with pytest.raises(HTTPException) as exc:
                query(1, "q", "openai", "k", None)
            assert exc.value.status_code == 500

    def test_success_with_dedup_citations(self):
        chunks = [
            {"content": "c1", "title": "Arch", "page_id": "p1"},
            {"content": "c2", "title": "Arch", "page_id": "p1"},  # same page
            {"content": "c3", "title": "Setup", "page_id": "p2"},
        ]
        with (
            patch("services.knowledge.retrieval_service.retrieve", return_value=chunks),
            patch(
                "services.knowledge.llm_service.answer_from_context", return_value="Because Pulsar."
            ),
        ):
            from services.knowledge import query

            out = query(1, "why pulsar?", "openai", "k", None)
        assert out["answer"] == "Because Pulsar."
        assert out["citations"] == [
            {"title": "Arch", "page_id": "p1"},
            {"title": "Setup", "page_id": "p2"},
        ]

class TestAnswerFromContext:
    def test_success(self):
        from services.llm import answer_from_context

        resp = MagicMock()
        resp.answer = "The answer."
        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client") as build,
            patch("services.llm._token_kwargs", return_value={}),
        ):
            build.return_value.chat.completions.create.return_value = resp
            assert answer_from_context("q", "ctx", "openai", "k") == "The answer."

    def test_none_on_exception(self):
        from services.llm import answer_from_context

        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client", side_effect=Exception("boom")),
            patch("services.llm._raise_if_provider_error"),
        ):
            assert answer_from_context("q", "ctx", "openai", "k") is None

    def test_reraises_http(self):
        from services.llm import answer_from_context

        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client", side_effect=HTTPException(status_code=401)),
        ):
            with pytest.raises(HTTPException):
                answer_from_context("q", "ctx", "openai", "k")

class TestKnowledgePrompts:
    def test_system_prompt(self):
        from prompts.knowledge import knowledge_system_prompt

        assert "only" in knowledge_system_prompt().lower()

    def test_user_prompt_includes_question_and_context(self):
        from prompts.knowledge import knowledge_user_prompt

        out = knowledge_user_prompt("why pulsar?", "some docs")
        assert "why pulsar?" in out and "some docs" in out

class TestKnowledgeRoute:
    def test_unauthenticated(self, anon_client):
        assert anon_client.post("/knowledge/query", json={"question": "q"}).status_code == 401

    def test_success(self, auth_client):
        from models.company import Company

        with (
            patch(
                "controllers.knowledge.confluence_service.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch("controllers.knowledge.get_user_provider_name", return_value="openai"),
            patch("controllers.knowledge.get_user_api_key", return_value="k"),
            patch("controllers.knowledge.get_user_model", return_value=None),
            patch(
                "controllers.knowledge.knowledge_service.query",
                return_value={"answer": "A", "citations": []},
            ),
        ):
            resp = auth_client.post("/knowledge/query", json={"question": "why?"})
        assert resp.status_code == 200
        assert resp.json()["answer"] == "A"
