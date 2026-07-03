"""Tests for the freeform knowledge Q&A (RAG) endpoint + persistent chats."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from onboarding.models.knowledge_chat import KnowledgeChat
from onboarding.models.knowledge_message import KnowledgeMessage

def _patch_chat_session(session):
    """Patch onboarding.services.knowledge.Session to yield `session` as a context
    manager. Returns the patcher (call .stop() when done)."""
    patcher = patch("onboarding.services.knowledge.Session")
    cls = patcher.start()
    cls.return_value.__enter__ = MagicMock(return_value=session)
    cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

class TestKnowledgeService:
    def test_blank_question_400(self):
        from onboarding.services.knowledge import query

        with pytest.raises(HTTPException) as exc:
            query(1, "   ", "openai", "k", None)
        assert exc.value.status_code == 400

    def test_no_chunks_404(self):
        from onboarding.services.knowledge import query

        with patch("onboarding.services.knowledge.retrieval_service.retrieve", return_value=[]):
            with pytest.raises(HTTPException) as exc:
                query(1, "how do we deploy?", "openai", "k", None)
            assert exc.value.status_code == 404

    def test_llm_fails_500(self):
        chunks = [{"content": "c", "title": "A", "page_id": "p1"}]
        with (
            patch("onboarding.services.knowledge.retrieval_service.retrieve", return_value=chunks),
            patch(
                "onboarding.services.knowledge.llm_service.answer_from_context", return_value=None
            ),
        ):
            from onboarding.services.knowledge import query

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
            patch("onboarding.services.knowledge.retrieval_service.retrieve", return_value=chunks),
            patch(
                "onboarding.services.knowledge.llm_service.answer_from_context",
                return_value="Because Pulsar.",
            ),
        ):
            from onboarding.services.knowledge import query

            out = query(1, "why pulsar?", "openai", "k", None)
        assert out["answer"] == "Because Pulsar."
        assert out["citations"] == [
            {"title": "Arch", "page_id": "p1"},
            {"title": "Setup", "page_id": "p2"},
        ]

class TestAnswerFromContext:
    def test_success(self):
        from onboarding.services.generation import answer_from_context

        resp = MagicMock()
        resp.answer = "The answer."
        with (
            patch("onboarding.services.generation._require_settings", return_value=("openai", "k")),
            patch("onboarding.services.generation._build_client") as build,
            patch("onboarding.services.generation._token_kwargs", return_value={}),
        ):
            build.return_value.chat.completions.create.return_value = resp
            assert answer_from_context("q", "ctx", "openai", "k") == "The answer."

    def test_none_on_exception(self):
        from onboarding.services.generation import answer_from_context

        with (
            patch("onboarding.services.generation._require_settings", return_value=("openai", "k")),
            patch("onboarding.services.generation._build_client", side_effect=Exception("boom")),
            patch("onboarding.services.generation._raise_if_provider_error"),
        ):
            assert answer_from_context("q", "ctx", "openai", "k") is None

    def test_reraises_http(self):
        from onboarding.services.generation import answer_from_context

        with (
            patch("onboarding.services.generation._require_settings", return_value=("openai", "k")),
            patch(
                "onboarding.services.generation._build_client",
                side_effect=HTTPException(status_code=401),
            ),
        ):
            with pytest.raises(HTTPException):
                answer_from_context("q", "ctx", "openai", "k")

    def test_includes_history_turns(self):
        from onboarding.services.generation import answer_from_context

        resp = MagicMock()
        resp.answer = "ok"
        captured = {}

        def create(**kwargs):
            captured["messages"] = kwargs["messages"]
            return resp

        with (
            patch("onboarding.services.generation._require_settings", return_value=("openai", "k")),
            patch("onboarding.services.generation._build_client") as build,
            patch("onboarding.services.generation._token_kwargs", return_value={}),
        ):
            build.return_value.chat.completions.create.side_effect = create
            history = [
                {"role": "user", "content": "prior q"},
                {"role": "assistant", "content": "prior a"},
                {"role": "system", "content": "ignored"},  # bad role — filtered
                {"role": "user", "content": ""},  # empty — filtered
            ]
            answer_from_context("q", "ctx", "openai", "k", history=history)

        roles = [(m["role"], m["content"]) for m in captured["messages"]]
        assert ("user", "prior q") in roles and ("assistant", "prior a") in roles
        assert ("system", "ignored") not in roles  # only the real system prompt is system
        assert roles[0][0] == "system"  # system prompt first
        assert roles[-1][0] == "user"  # current question last

class TestAnswerBlocksFromContext:
    def test_success_returns_block_dicts(self):
        from onboarding.services.generation import answer_blocks_from_context

        block = MagicMock()
        block.model_dump.return_value = {"type": "paragraph", "content": "Answer."}
        resp = MagicMock()
        resp.blocks = [block]
        resp.used_docs = True
        with (
            patch("onboarding.services.generation._require_settings", return_value=("openai", "k")),
            patch("onboarding.services.generation._build_client") as build,
            patch("onboarding.services.generation._token_kwargs", return_value={}),
        ):
            build.return_value.chat.completions.create.return_value = resp
            out = answer_blocks_from_context("q", "ctx", "openai", "k")
        assert out == {"blocks": [{"type": "paragraph", "content": "Answer."}], "used_docs": True}

    def test_none_when_no_blocks(self):
        from onboarding.services.generation import answer_blocks_from_context

        resp = MagicMock()
        resp.blocks = []
        with (
            patch("onboarding.services.generation._require_settings", return_value=("openai", "k")),
            patch("onboarding.services.generation._build_client") as build,
            patch("onboarding.services.generation._token_kwargs", return_value={}),
        ):
            build.return_value.chat.completions.create.return_value = resp
            assert answer_blocks_from_context("q", "ctx", "openai", "k") is None

    def test_none_on_exception(self):
        from onboarding.services.generation import answer_blocks_from_context

        with (
            patch("onboarding.services.generation._require_settings", return_value=("openai", "k")),
            patch("onboarding.services.generation._build_client", side_effect=Exception("boom")),
            patch("onboarding.services.generation._raise_if_provider_error"),
        ):
            assert answer_blocks_from_context("q", "ctx", "openai", "k") is None

    def test_reraises_http(self):
        from onboarding.services.generation import answer_blocks_from_context

        with (
            patch("onboarding.services.generation._require_settings", return_value=("openai", "k")),
            patch(
                "onboarding.services.generation._build_client",
                side_effect=HTTPException(status_code=401),
            ),
        ):
            with pytest.raises(HTTPException):
                answer_blocks_from_context("q", "ctx", "openai", "k")

    def test_includes_history(self):
        from onboarding.services.generation import answer_blocks_from_context

        block = MagicMock()
        block.model_dump.return_value = {"type": "paragraph", "content": "a"}
        resp = MagicMock()
        resp.blocks = [block]
        captured = {}

        def create(**kwargs):
            captured["messages"] = kwargs["messages"]
            return resp

        with (
            patch("onboarding.services.generation._require_settings", return_value=("openai", "k")),
            patch("onboarding.services.generation._build_client") as build,
            patch("onboarding.services.generation._token_kwargs", return_value={}),
        ):
            build.return_value.chat.completions.create.side_effect = create
            answer_blocks_from_context(
                "q", "ctx", "openai", "k", history=[{"role": "user", "content": "prior"}]
            )
        assert ("user", "prior") in [(m["role"], m["content"]) for m in captured["messages"]]

class TestKnowledgeChats:
    def _chat(self, **kw):
        d = dict(id=1, company_id=1, user_id="1", title="New chat")
        d.update(kw)
        return KnowledgeChat(**d)

    def test_create_chat(self):
        session = MagicMock()
        patcher = _patch_chat_session(session)
        try:
            from onboarding.services.knowledge import create_chat

            out = create_chat(1, "1")
            assert out["title"] == "New chat"
            session.add.assert_called_once()
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_list_chats(self):
        session = MagicMock()
        session.exec.return_value.all.return_value = [self._chat(id=3, title="Deploys")]
        patcher = _patch_chat_session(session)
        try:
            from onboarding.services.knowledge import list_chats

            out = list_chats(1, "1")
            assert out == [{"id": 3, "title": "Deploys", "created_at": None, "updated_at": None}]
        finally:
            patcher.stop()

    def test_get_chat_returns_messages(self):
        session = MagicMock()
        session.get.return_value = self._chat()
        session.exec.return_value.all.return_value = [
            KnowledgeMessage(id=1, chat_id=1, role="user", content="hi"),
            KnowledgeMessage(
                id=2,
                chat_id=1,
                role="assistant",
                content="hey",
                citations='[{"title":"A","page_id":"p1"}]',
            ),
        ]
        patcher = _patch_chat_session(session)
        try:
            from onboarding.services.knowledge import get_chat

            out = get_chat(1, 1, "1")
            assert out["chat"]["id"] == 1
            assert out["messages"][0]["content"] == "hi"
            assert out["messages"][1]["citations"] == [{"title": "A", "page_id": "p1"}]
        finally:
            patcher.stop()

    def test_get_chat_not_owned_404(self):
        session = MagicMock()
        session.get.return_value = self._chat(company_id=999)
        patcher = _patch_chat_session(session)
        try:
            from onboarding.services.knowledge import get_chat

            with pytest.raises(HTTPException) as exc:
                get_chat(1, 1, "1")
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_get_chat_missing_404(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_chat_session(session)
        try:
            from onboarding.services.knowledge import get_chat

            with pytest.raises(HTTPException) as exc:
                get_chat(1, 1, "1")
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_delete_chat(self):
        session = MagicMock()
        session.get.return_value = self._chat()
        patcher = _patch_chat_session(session)
        try:
            from onboarding.services.knowledge import delete_chat

            assert delete_chat(1, 1, "1") == {"deleted": True}
            session.delete.assert_called_once()
        finally:
            patcher.stop()

    def test_post_message_blank_400(self):
        from onboarding.services.knowledge import post_message

        with pytest.raises(HTTPException) as exc:
            post_message(1, 1, "1", "  ", "openai", "k", None)
        assert exc.value.status_code == 400

    def test_post_message_first_sets_title(self):
        session = MagicMock()
        session.get.return_value = self._chat()
        session.exec.return_value.all.return_value = []  # no prior → first message
        chunks = [{"content": "c", "title": "Arch", "page_id": "p1"}]
        blocks = [{"type": "paragraph", "content": "Because Pulsar."}]
        patcher = _patch_chat_session(session)
        try:
            with (
                patch(
                    "onboarding.services.knowledge.retrieval_service.retrieve",
                    return_value=chunks,
                ),
                patch(
                    "onboarding.services.knowledge.llm_service.answer_blocks_from_context",
                    return_value={"blocks": blocks, "used_docs": True},
                ),
            ):
                from onboarding.services.knowledge import post_message

                out = post_message(1, 1, "1", "why pulsar?", "openai", "k", None)
            assert out["user"]["content"] == "why pulsar?"
            assert out["assistant"]["blocks"] == blocks
            assert out["assistant"]["content"] == "Because Pulsar."  # flattened for history
            assert out["assistant"]["citations"] == [{"title": "Arch", "page_id": "p1"}]
            assert out["title"] == "why pulsar?"
        finally:
            patcher.stop()

    def test_post_message_greeting_omits_sources(self):
        session = MagicMock()
        session.get.return_value = self._chat()
        session.exec.return_value.all.return_value = []
        patcher = _patch_chat_session(session)
        try:
            with (
                patch(
                    "onboarding.services.knowledge.retrieval_service.retrieve",
                    return_value=[{"content": "c", "title": "Arch", "page_id": "p1"}],
                ),
                patch(
                    "onboarding.services.knowledge.llm_service.answer_blocks_from_context",
                    return_value={
                        "blocks": [{"type": "paragraph", "content": "Hi! How can I help?"}],
                        "used_docs": False,
                    },
                ),
            ):
                from onboarding.services.knowledge import post_message

                out = post_message(1, 1, "1", "hi", "openai", "k", None)
            assert out["assistant"]["citations"] == []  # not doc-grounded → no sources
        finally:
            patcher.stop()

    def test_post_message_uses_prior_history(self):
        session = MagicMock()
        session.get.return_value = self._chat(title="Existing")
        session.exec.return_value.all.return_value = [
            KnowledgeMessage(id=1, chat_id=1, role="user", content="earlier"),
            KnowledgeMessage(id=2, chat_id=1, role="assistant", content="answer"),
        ]
        captured = {}

        def answer(**kwargs):
            captured["history"] = kwargs.get("history")
            return {
                "blocks": [{"type": "paragraph", "content": "follow-up answer"}],
                "used_docs": True,
            }

        patcher = _patch_chat_session(session)
        try:
            with (
                patch(
                    "onboarding.services.knowledge.retrieval_service.retrieve",
                    return_value=[{"content": "c", "title": "A", "page_id": "p1"}],
                ),
                patch(
                    "onboarding.services.knowledge.llm_service.answer_blocks_from_context",
                    side_effect=answer,
                ),
            ):
                from onboarding.services.knowledge import post_message

                out = post_message(1, 1, "1", "what about that?", "openai", "k", None)
            assert out["title"] == "Existing"  # not first → title unchanged
            assert captured["history"] == [
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "answer"},
            ]
        finally:
            patcher.stop()

    def test_answer_blocks_no_chunks_404(self):
        with patch("onboarding.services.knowledge.retrieval_service.retrieve", return_value=[]):
            from onboarding.services.knowledge import _answer_blocks

            with pytest.raises(HTTPException) as exc:
                _answer_blocks(1, "q", "openai", "k", None)
            assert exc.value.status_code == 404

    def test_answer_blocks_llm_none_500(self):
        with (
            patch(
                "onboarding.services.knowledge.retrieval_service.retrieve",
                return_value=[{"content": "c", "title": "A", "page_id": "p1"}],
            ),
            patch(
                "onboarding.services.knowledge.llm_service.answer_blocks_from_context",
                return_value=None,
            ),
        ):
            from onboarding.services.knowledge import _answer_blocks

            with pytest.raises(HTTPException) as exc:
                _answer_blocks(1, "q", "openai", "k", None)
            assert exc.value.status_code == 500

    def test_blocks_to_text_flattens_all_shapes(self):
        from onboarding.services.knowledge import _blocks_to_text

        text = _blocks_to_text(
            [
                {"type": "heading", "content": "Title"},
                {"type": "bullet_list", "items": ["one", "two"]},
                {"type": "table", "headers": ["A", "B"], "rows": [["1", "2"]]},
                {"type": "divider"},  # nothing to add
            ]
        )
        assert "Title" in text and "one" in text and "A | B" in text and "1 | 2" in text

    def test_blocks_to_text_empty_is_blank(self):
        from onboarding.services.knowledge import _blocks_to_text

        assert _blocks_to_text([{"type": "divider"}]) == ""

class TestKnowledgePrompts:
    def test_system_prompt(self):
        from onboarding.prompts.knowledge import knowledge_system_prompt

        assert "only" in knowledge_system_prompt().lower()

    def test_user_prompt_includes_question_and_context(self):
        from onboarding.prompts.knowledge import knowledge_user_prompt

        out = knowledge_user_prompt("why pulsar?", "some docs")
        assert "why pulsar?" in out and "some docs" in out

    def test_blocks_system_prompt_mentions_blocks(self):
        from onboarding.prompts.knowledge import knowledge_blocks_system_prompt

        out = knowledge_blocks_system_prompt().lower()
        assert "blocks" in out and "diagram" in out

    def test_blocks_user_prompt_includes_question_and_context(self):
        from onboarding.prompts.knowledge import knowledge_blocks_user_prompt

        out = knowledge_blocks_user_prompt("why pulsar?", "some docs")
        assert "why pulsar?" in out and "some docs" in out

class TestKnowledgeRoute:
    def test_unauthenticated(self, anon_client):
        assert anon_client.post("/knowledge/query", json={"question": "q"}).status_code == 401

    def test_success(self, auth_client):
        from onboarding.models.company import Company

        with (
            patch(
                "onboarding.controllers.knowledge.confluence_service.get_or_create_company_for_user",
                return_value=Company(id=1, name="a", domain="a"),
            ),
            patch("onboarding.controllers.knowledge.get_user_provider_name", return_value="openai"),
            patch("onboarding.controllers.knowledge.get_user_api_key", return_value="k"),
            patch("onboarding.controllers.knowledge.get_user_model", return_value=None),
            patch(
                "onboarding.controllers.knowledge.knowledge_service.query",
                return_value={"answer": "A", "citations": []},
            ),
        ):
            resp = auth_client.post("/knowledge/query", json={"question": "why?"})
        assert resp.status_code == 200
        assert resp.json()["answer"] == "A"

class TestKnowledgeChatRoutes:
    def _company(self):
        from onboarding.models.company import Company

        return Company(id=1, name="a", domain="a")

    def test_list_chats(self, auth_client):
        with (
            patch(
                "onboarding.controllers.knowledge.confluence_service.get_or_create_company_for_user",
                return_value=self._company(),
            ),
            patch(
                "onboarding.controllers.knowledge.knowledge_service.list_chats",
                return_value=[{"id": 1, "title": "t", "created_at": None, "updated_at": None}],
            ),
        ):
            resp = auth_client.get("/knowledge/chats")
        assert resp.status_code == 200 and resp.json()[0]["id"] == 1

    def test_create_chat(self, auth_client):
        with (
            patch(
                "onboarding.controllers.knowledge.confluence_service.get_or_create_company_for_user",
                return_value=self._company(),
            ),
            patch(
                "onboarding.controllers.knowledge.knowledge_service.create_chat",
                return_value={"id": 5, "title": "New chat"},
            ),
        ):
            resp = auth_client.post("/knowledge/chats")
        assert resp.status_code == 200 and resp.json()["id"] == 5

    def test_get_chat(self, auth_client):
        with (
            patch(
                "onboarding.controllers.knowledge.confluence_service.get_or_create_company_for_user",
                return_value=self._company(),
            ),
            patch(
                "onboarding.controllers.knowledge.knowledge_service.get_chat",
                return_value={"chat": {"id": 5}, "messages": []},
            ),
        ):
            resp = auth_client.get("/knowledge/chats/5")
        assert resp.status_code == 200 and resp.json()["chat"]["id"] == 5

    def test_delete_chat(self, auth_client):
        with (
            patch(
                "onboarding.controllers.knowledge.confluence_service.get_or_create_company_for_user",
                return_value=self._company(),
            ),
            patch(
                "onboarding.controllers.knowledge.knowledge_service.delete_chat",
                return_value={"deleted": True},
            ),
        ):
            resp = auth_client.delete("/knowledge/chats/5")
        assert resp.status_code == 200 and resp.json()["deleted"] is True

    def test_post_message(self, auth_client):
        with (
            patch(
                "onboarding.controllers.knowledge.confluence_service.get_or_create_company_for_user",
                return_value=self._company(),
            ),
            patch("onboarding.controllers.knowledge.get_user_provider_name", return_value="openai"),
            patch("onboarding.controllers.knowledge.get_user_api_key", return_value="k"),
            patch("onboarding.controllers.knowledge.get_user_model", return_value=None),
            patch(
                "onboarding.controllers.knowledge.knowledge_service.post_message",
                return_value={
                    "user": {"content": "q"},
                    "assistant": {"content": "a"},
                    "title": "q",
                },
            ),
        ):
            resp = auth_client.post("/knowledge/chats/5/messages", json={"question": "q"})
        assert resp.status_code == 200 and resp.json()["assistant"]["content"] == "a"

    def test_post_message_unauthenticated(self, anon_client):
        assert (
            anon_client.post("/knowledge/chats/5/messages", json={"question": "q"}).status_code
            == 401
        )
