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
            {"content": "c1", "title": "Arch", "page_id": "p1", "source": "confluence"},
            {
                "content": "c2",
                "title": "Arch",
                "page_id": "p1",
                "source": "confluence",
            },  # same page
            {"content": "c3", "title": "Setup", "page_id": "p2", "source": "jira"},
        ]
        with (
            patch("onboarding.services.knowledge.retrieval_service.retrieve", return_value=chunks),
            patch(
                "onboarding.services.knowledge.llm_service.answer_from_context",
                return_value="Because Pulsar.",
            ),
            patch(
                "onboarding.services.knowledge.confluence_service.get_site_url",
                return_value="https://acme.atlassian.net",
            ),
        ):
            from onboarding.services.knowledge import query

            out = query(1, "why pulsar?", "openai", "k", None)
        assert out["answer"] == "Because Pulsar."
        # Deduped per (source, page_id); each carries a deep link to its source.
        assert out["citations"] == [
            {
                "title": "Arch",
                "page_id": "p1",
                "source": "confluence",
                "url": "https://acme.atlassian.net/wiki/pages/viewpage.action?pageId=p1",
            },
            {
                "title": "Setup",
                "page_id": "p2",
                "source": "jira",
                "url": "https://acme.atlassian.net/browse/p2",
            },
        ]

class TestLinkScrub:
    def test_strips_hallucinated_markdown_link_keeps_label(self):
        from onboarding.services.knowledge import _scrub_text_links

        out = _scrub_text_links("See [AR-2847](https://jira.example.com/browse/AR-2847).", "ctx")
        assert out == "See AR-2847."

    def test_keeps_link_present_in_context(self):
        from onboarding.services.knowledge import _scrub_text_links

        ctx = "docs at https://real.internal/wiki/x are here"
        out = _scrub_text_links("[here](https://real.internal/wiki/x)", ctx)
        assert out == "[here](https://real.internal/wiki/x)"

    def test_removes_bare_fabricated_url(self):
        from onboarding.services.knowledge import _scrub_text_links

        out = _scrub_text_links("visit https://jira.example.com/browse/AR-1 now", "ctx")
        assert "example.com" not in out and "visit" in out and "now" in out

    def test_scrubs_blocks_content_items_and_tables(self):
        from onboarding.services.knowledge import _scrub_block_links

        blocks = [
            {"type": "paragraph", "content": "[X](https://fake.example.com/x)"},
            {"type": "bullet_list", "items": ["[Y](https://fake.example.com/y)", "plain"]},
            {"type": "table", "headers": ["H"], "rows": [["[Z](https://fake.example.com/z)"]]},
        ]
        out = _scrub_block_links(blocks, "no urls here")
        assert out[0]["content"] == "X"
        assert out[1]["items"] == ["Y", "plain"]
        assert out[2]["rows"] == [["Z"]]

class TestCitationFilter:
    def test_keeps_only_referenced_ids(self):
        from onboarding.services.knowledge import _filter_cited

        citations = [
            {"title": "T1", "page_id": "AR-2847", "source": "jira", "url": None},
            {"title": "T2", "page_id": "DSCO-4759", "source": "jira", "url": None},  # filler
        ]
        answer = "Sunadh requested write access on groundcover (AR-2847)."
        out = _filter_cited(citations, answer)
        assert [c["page_id"] for c in out] == ["AR-2847"]  # DSCO filler dropped

    def test_falls_back_to_all_when_none_referenced(self):
        from onboarding.services.knowledge import _filter_cited

        citations = [
            {"title": "Arch", "page_id": "12345", "source": "confluence", "url": None},
        ]
        # A paraphrased Confluence answer names no id → keep everything (never zero).
        out = _filter_cited(citations, "We deploy via the pipeline.")
        assert out == citations

class TestFormatAndSources:
    def test_format_context_tags_each_source(self):
        from onboarding.services.knowledge import _format_context

        out = _format_context(
            [
                {"content": "body1", "title": "Arch", "page_id": "p1", "source": "confluence"},
                {"content": "body2", "title": "Login bug", "page_id": "ENG-1", "source": "jira"},
            ]
        )
        assert "=== [Confluence] Arch ===" in out
        assert "=== [Jira issue ENG-1] Login bug ===" in out

    def test_chat_retrieves_both_sources(self):
        captured = {}

        def retrieve(company_id, question, k, sources=None):
            captured["sources"] = sources
            return [{"content": "c", "title": "A", "page_id": "p1", "source": "confluence"}]

        with (
            patch("onboarding.services.knowledge.retrieval_service.retrieve", side_effect=retrieve),
            patch(
                "onboarding.services.knowledge.llm_service.answer_from_context",
                return_value="ans",
            ),
            patch(
                "onboarding.services.knowledge.confluence_service.get_site_url", return_value=None
            ),
        ):
            from onboarding.services.knowledge import query

            query(1, "q", "openai", "k", None)
        assert captured["sources"] == ["confluence", "jira"]

class TestExtractPeopleQuery:
    def test_success(self):
        from onboarding.services.generation import extract_people_query

        resp = MagicMock()
        resp.intent = "count"
        resp.people = ["Sunadh", " Yogesh Kisslay ", ""]
        resp.metric = "involved"
        with (
            patch("onboarding.services.generation._require_settings", return_value=("openai", "k")),
            patch("onboarding.services.generation._build_client") as build,
            patch("onboarding.services.generation._token_kwargs", return_value={}),
        ):
            build.return_value.chat.completions.create.return_value = resp
            out = extract_people_query("who has more, Sunadh or Yogesh Kisslay?", "openai", "k")
        assert out == {
            "intent": "count",
            "people": ["Sunadh", "Yogesh Kisslay"],
            "metric": "involved",
        }

    def test_passes_history_for_pronoun_resolution(self):
        from onboarding.services.generation import extract_people_query

        resp = MagicMock()
        resp.intent = "list"
        resp.people = ["Yogesh Kisslay"]
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
            history = [{"role": "user", "content": "tell me about Yogesh Kisslay"}]
            out = extract_people_query("about his work", "openai", "k", history=history)
        assert out["people"] == ["Yogesh Kisslay"]
        # Prior turn is included so the planner can resolve "his".
        assert ("user", "tell me about Yogesh Kisslay") in [
            (m["role"], m["content"]) for m in captured["messages"]
        ]

    def test_unknown_intent_and_metric_normalized(self):
        from onboarding.services.generation import extract_people_query

        resp = MagicMock()
        resp.intent = "banana"
        resp.people = ["X"]
        resp.metric = "bogus"
        with (
            patch("onboarding.services.generation._require_settings", return_value=("openai", "k")),
            patch("onboarding.services.generation._build_client") as build,
            patch("onboarding.services.generation._token_kwargs", return_value={}),
        ):
            build.return_value.chat.completions.create.return_value = resp
            out = extract_people_query("q", "openai", "k")
        assert out["intent"] == "other" and out["metric"] == "involved"

    def test_leaderboard_intent_with_metric(self):
        from onboarding.services.generation import extract_people_query

        resp = MagicMock()
        resp.intent = "leaderboard"
        resp.people = []
        resp.metric = "reported"
        with (
            patch("onboarding.services.generation._require_settings", return_value=("openai", "k")),
            patch("onboarding.services.generation._build_client") as build,
            patch("onboarding.services.generation._token_kwargs", return_value={}),
        ):
            build.return_value.chat.completions.create.return_value = resp
            out = extract_people_query("who reported the most", "openai", "k")
        assert out == {"intent": "leaderboard", "people": [], "metric": "reported"}

    def test_none_on_exception(self):
        from onboarding.services.generation import extract_people_query

        with (
            patch("onboarding.services.generation._require_settings", return_value=("openai", "k")),
            patch("onboarding.services.generation._build_client", side_effect=Exception("boom")),
            patch("onboarding.services.generation._raise_if_provider_error"),
        ):
            assert extract_people_query("q", "openai", "k") is None

    def test_reraises_http(self):
        from onboarding.services.generation import extract_people_query

        with (
            patch("onboarding.services.generation._require_settings", return_value=("openai", "k")),
            patch(
                "onboarding.services.generation._build_client",
                side_effect=HTTPException(status_code=401),
            ),
        ):
            with pytest.raises(HTTPException):
                extract_people_query("q", "openai", "k")

class TestLooksLikePersonQuestion:
    def _names(self, full, words):
        return patch(
            "onboarding.services.knowledge.retrieval_service._known_names",
            return_value=(frozenset(full), frozenset(words)),
        )

    def test_count_cue(self):
        from onboarding.services.knowledge import _looks_like_person_question

        with self._names([], []):
            assert _looks_like_person_question(1, "who has more issues") is True

    def test_known_full_name(self):
        from onboarding.services.knowledge import _looks_like_person_question

        with self._names(["yogesh kisslay"], ["yogesh", "kisslay"]):
            assert _looks_like_person_question(1, "tell me about yogesh kisslay") is True

    def test_known_name_word(self):
        from onboarding.services.knowledge import _looks_like_person_question

        with self._names([], ["sunadh"]):
            assert _looks_like_person_question(1, "what is sunadh doing") is True

    def test_no_person_no_cue(self):
        from onboarding.services.knowledge import _looks_like_person_question

        with self._names(["yogesh kisslay"], ["yogesh", "kisslay"]):
            assert _looks_like_person_question(1, "how does deployment work") is False

    def test_pronoun_followup_with_person_in_history(self):
        from onboarding.services.knowledge import _looks_like_person_question

        history = [{"role": "user", "content": "tell me about Yogesh Kisslay"}]
        with self._names(["yogesh kisslay"], ["yogesh", "kisslay"]):
            assert _looks_like_person_question(1, "about his work", history) is True

    def test_pronoun_without_person_in_history(self):
        from onboarding.services.knowledge import _looks_like_person_question

        history = [{"role": "user", "content": "how does deployment work"}]
        with self._names(["yogesh kisslay"], ["yogesh", "kisslay"]):
            assert _looks_like_person_question(1, "how do they scale it", history) is False

class TestPersonAnswer:
    def _counts(self, m):
        def counts(company_id, name):
            inv = m.get(name, 0)
            return {"name": name, "assigned": 0, "reported": inv, "authored": 0, "involved": inv}

        return counts

    def test_gate_skips_non_person(self):
        from onboarding.services.knowledge import _maybe_person_answer

        with (
            patch("onboarding.services.knowledge._looks_like_person_question", return_value=False),
            patch("onboarding.services.knowledge.llm_service.extract_people_query") as ex,
        ):
            assert _maybe_person_answer(1, "how does auth work", "openai", "k", None) is None
            ex.assert_not_called()  # gate blocked the planner call

    def test_intent_other_falls_through(self):
        from onboarding.services.knowledge import _maybe_person_answer

        with (
            patch("onboarding.services.knowledge._looks_like_person_question", return_value=True),
            patch(
                "onboarding.services.knowledge.llm_service.extract_people_query",
                return_value={"intent": "other", "people": ["X"]},
            ),
        ):
            assert _maybe_person_answer(1, "what did X decide", "openai", "k", None) is None

    def test_planner_none_falls_through(self):
        from onboarding.services.knowledge import _maybe_person_answer

        with (
            patch("onboarding.services.knowledge._looks_like_person_question", return_value=True),
            patch(
                "onboarding.services.knowledge.llm_service.extract_people_query", return_value=None
            ),
        ):
            assert _maybe_person_answer(1, "who did the most", "openai", "k", None) is None

    def test_count_route(self):
        from onboarding.services.knowledge import _maybe_person_answer

        with (
            patch("onboarding.services.knowledge._looks_like_person_question", return_value=True),
            patch(
                "onboarding.services.knowledge.llm_service.extract_people_query",
                return_value={"intent": "count", "people": ["Sunadh", "Yogesh Kisslay"]},
            ),
            patch(
                "onboarding.services.knowledge.retrieval_service.count_involvement",
                side_effect=self._counts({"Sunadh": 15, "Yogesh Kisslay": 2}),
            ),
            patch(
                "onboarding.services.knowledge.retrieval_service.top_issues",
                return_value=[{"page_id": "AR-1", "title": "T", "source": "jira"}],
            ),
            patch(
                "onboarding.services.knowledge.confluence_service.get_site_url",
                return_value="https://acme.atlassian.net",
            ),
        ):
            out = _maybe_person_answer(1, "who did more, Sunadh or Yogesh Kisslay", "o", "k", None)
        assert "Sunadh is involved in the most" in out["blocks"][0]["content"]
        table = next(b for b in out["blocks"] if b["type"] == "table")
        assert table["rows"][0][0] == "Sunadh"

    def test_leaderboard_route_single_metric(self):
        from onboarding.services.knowledge import _maybe_person_answer

        with (
            patch("onboarding.services.knowledge._looks_like_person_question", return_value=True),
            patch(
                "onboarding.services.knowledge.llm_service.extract_people_query",
                return_value={"intent": "leaderboard", "people": [], "metric": "reported"},
            ),
            patch(
                "onboarding.services.knowledge.retrieval_service.leaderboard",
                return_value=[
                    {"name": "Suraj Nayak", "reported": 1715},
                    {"name": "Pulkeet Yadav", "reported": 1148},
                ],
            ),
        ):
            out = _maybe_person_answer(1, "who reported the most access requests", "o", "k", None)
        assert "Suraj Nayak leads" in out["blocks"][0]["content"]
        table = next(b for b in out["blocks"] if b["type"] == "table")
        assert table["rows"][0] == ["1", "Suraj Nayak", "1715"]

    def test_leaderboard_route_involved(self):
        from onboarding.services.knowledge import _maybe_person_answer

        board = [
            {
                "name": "Suraj Nayak",
                "assigned": 187,
                "reported": 1715,
                "authored": 0,
                "involved": 1902,
            }
        ]
        with (
            patch("onboarding.services.knowledge._looks_like_person_question", return_value=True),
            patch(
                "onboarding.services.knowledge.llm_service.extract_people_query",
                return_value={"intent": "leaderboard", "people": [], "metric": "involved"},
            ),
            patch(
                "onboarding.services.knowledge.retrieval_service.leaderboard", return_value=board
            ),
        ):
            out = _maybe_person_answer(1, "top contributors", "o", "k", None)
        table = next(b for b in out["blocks"] if b["type"] == "table")
        assert table["headers"] == ["#", "Person", "Total", "Assigned", "Reported", "Authored"]
        assert table["rows"][0] == ["1", "Suraj Nayak", "1902", "187", "1715", "0"]

    def test_leaderboard_empty_falls_through(self):
        from onboarding.services.knowledge import _maybe_person_answer

        with (
            patch("onboarding.services.knowledge._looks_like_person_question", return_value=True),
            patch(
                "onboarding.services.knowledge.llm_service.extract_people_query",
                return_value={"intent": "leaderboard", "people": [], "metric": "reported"},
            ),
            patch("onboarding.services.knowledge.retrieval_service.leaderboard", return_value=[]),
        ):
            assert _maybe_person_answer(1, "top contributors", "o", "k", None) is None

    def test_count_single_person(self):
        from onboarding.services.knowledge import _maybe_person_answer

        with (
            patch("onboarding.services.knowledge._looks_like_person_question", return_value=True),
            patch(
                "onboarding.services.knowledge.llm_service.extract_people_query",
                return_value={"intent": "count", "people": ["Sunadh"]},
            ),
            patch(
                "onboarding.services.knowledge.retrieval_service.count_involvement",
                side_effect=self._counts({"Sunadh": 15}),
            ),
            patch("onboarding.services.knowledge.retrieval_service.top_issues", return_value=[]),
            patch(
                "onboarding.services.knowledge.confluence_service.get_site_url", return_value=None
            ),
        ):
            out = _maybe_person_answer(1, "how many issues is Sunadh involved in", "o", "k", None)
        assert "Sunadh is involved in 15" in out["blocks"][0]["content"]

    def _list_data(self, jira, confluence):
        return {
            "jira": jira,
            "confluence": confluence,
            "jira_total": len(jira),
            "confluence_total": len(confluence),
        }

    def test_list_route_single_person_complete(self):
        from onboarding.services.knowledge import _maybe_person_answer

        data = self._list_data(
            jira=[
                {
                    "key": "AR-1",
                    "title": "Access",
                    "status": "Open",
                    "roles": ["reporter"],
                    "type": "Access Request",
                    "priority": "Low",
                },
            ],
            confluence=[
                {"page_id": "5910134900", "title": "#79 Content Validation", "roles": ["author"]},
                {"page_id": "5836177409", "title": "#62 Structured Blocks", "roles": ["author"]},
            ],
        )
        with (
            patch("onboarding.services.knowledge._looks_like_person_question", return_value=True),
            patch(
                "onboarding.services.knowledge.llm_service.extract_people_query",
                return_value={"intent": "list", "people": ["Yogesh Kisslay"]},
            ),
            patch(
                "onboarding.services.knowledge.retrieval_service.list_involvement",
                return_value=data,
            ),
            patch(
                "onboarding.services.knowledge.confluence_service.get_site_url",
                return_value="https://acme.atlassian.net",
            ),
        ):
            out = _maybe_person_answer(1, "give me all work of Yogesh Kisslay", "o", "k", None)
        # Both Confluence docs listed (including the one that was missing before).
        bullets = next(b for b in out["blocks"] if b["type"] == "bullet_list")["items"]
        joined = " ".join(bullets)
        assert "#79 Content Validation" in joined and "#62 Structured Blocks" in joined
        # Clickable Confluence link built.
        assert "atlassian.net/wiki/pages/viewpage.action?pageId=5836177409" in joined
        # Jira table present, and every item is a source.
        assert any(b["type"] == "table" for b in out["blocks"])
        cited = {(c["source"], c["page_id"]) for c in out["citations"]}
        assert ("confluence", "5836177409") in cited and ("jira", "AR-1") in cited

    def test_list_route_multi_person(self):
        from onboarding.services.knowledge import _maybe_person_answer

        def li(company_id, name, limit=40):
            if name == "Sunadh":
                return self._list_data(
                    [
                        {
                            "key": "AR-9",
                            "title": "S",
                            "status": "Open",
                            "roles": ["reporter"],
                            "type": "AR",
                            "priority": "Low",
                        }
                    ],
                    [],
                )
            return self._list_data([], [{"page_id": "99", "title": "Doc", "roles": ["author"]}])

        with (
            patch("onboarding.services.knowledge._looks_like_person_question", return_value=True),
            patch(
                "onboarding.services.knowledge.llm_service.extract_people_query",
                return_value={"intent": "list", "people": ["Sunadh", "Yogesh Kisslay"]},
            ),
            patch(
                "onboarding.services.knowledge.retrieval_service.list_involvement", side_effect=li
            ),
            patch(
                "onboarding.services.knowledge.confluence_service.get_site_url", return_value=None
            ),
        ):
            out = _maybe_person_answer(1, "tell me about Sunadh and Yogesh Kisslay", "o", "k", None)
        headings = [
            b["content"]
            for b in out["blocks"]
            if b.get("type") == "heading" and b.get("level") == 2
        ]
        assert headings == ["Sunadh — Work & Involvement", "Yogesh Kisslay — Work & Involvement"]
        assert any(b["type"] == "divider" for b in out["blocks"])  # separated

    def test_list_nobody_found_falls_through(self):
        from onboarding.services.knowledge import _maybe_person_answer

        with (
            patch("onboarding.services.knowledge._looks_like_person_question", return_value=True),
            patch(
                "onboarding.services.knowledge.llm_service.extract_people_query",
                return_value={"intent": "list", "people": ["Ghost"]},
            ),
            patch(
                "onboarding.services.knowledge.retrieval_service.list_involvement",
                return_value=self._list_data([], []),
            ),
            patch(
                "onboarding.services.knowledge.confluence_service.get_site_url", return_value=None
            ),
        ):
            assert _maybe_person_answer(1, "all work of Ghost", "o", "k", None) is None

    def test_count_nobody_found_falls_through(self):
        from onboarding.services.knowledge import _maybe_person_answer

        with (
            patch("onboarding.services.knowledge._looks_like_person_question", return_value=True),
            patch(
                "onboarding.services.knowledge.llm_service.extract_people_query",
                return_value={"intent": "count", "people": ["Ghost"]},
            ),
            patch(
                "onboarding.services.knowledge.retrieval_service.count_involvement",
                side_effect=self._counts({}),
            ),
        ):
            assert (
                _maybe_person_answer(1, "how many issues does Ghost have", "o", "k", None) is None
            )

    def test_tie(self):
        from onboarding.services.knowledge import _count_blocks

        blocks = _count_blocks(
            [
                {"name": "A", "assigned": 1, "reported": 1, "authored": 1, "involved": 3},
                {"name": "B", "assigned": 0, "reported": 3, "authored": 0, "involved": 3},
            ]
        )
        assert "tie" in blocks[0]["content"].lower()

    def test_answer_blocks_short_circuits_to_person(self):
        from onboarding.services.knowledge import _answer_blocks

        person = {"blocks": [{"type": "paragraph", "content": "X leads"}], "citations": []}
        with patch("onboarding.services.knowledge._maybe_person_answer", return_value=person):
            out = _answer_blocks(1, "who has more issues, X or Y", "openai", "k", None)
        assert out is person

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
        chunks = [{"content": "c", "title": "Arch", "page_id": "p1", "source": "confluence"}]
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
                patch(
                    "onboarding.services.knowledge.confluence_service.get_site_url",
                    return_value="https://acme.atlassian.net",
                ),
            ):
                from onboarding.services.knowledge import post_message

                out = post_message(1, 1, "1", "why pulsar?", "openai", "k", None)
            assert out["user"]["content"] == "why pulsar?"
            assert out["assistant"]["blocks"] == blocks
            assert out["assistant"]["content"] == "Because Pulsar."  # flattened for history
            assert out["assistant"]["citations"] == [
                {
                    "title": "Arch",
                    "page_id": "p1",
                    "source": "confluence",
                    "url": "https://acme.atlassian.net/wiki/pages/viewpage.action?pageId=p1",
                }
            ]
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
                patch(
                    "onboarding.services.knowledge.confluence_service.get_site_url",
                    return_value=None,
                ),
            ):
                from onboarding.services.knowledge import post_message

                out = post_message(1, 1, "1", "what about that?", "openai", "k", None)
            assert out["title"] == "Existing"  # not first → title unchanged
            # No site_url → citation still present, just without a deep link.
            assert out["assistant"]["citations"] == [
                {"title": "A", "page_id": "p1", "source": "confluence", "url": None}
            ]
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
