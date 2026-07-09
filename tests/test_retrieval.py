"""Tests for hybrid retrieval (semantic + lexical) over the knowledge base."""

from unittest.mock import MagicMock, patch

import pytest

@pytest.fixture(autouse=True)
def _seed_name_cache():
    # retrieve() calls _known_names(company_id); seed an empty cache (far-future TTL)
    # so it doesn't consume from the mocked Session in the retrieve tests.
    from onboarding.services import retrieval as r

    r._NAME_CACHE[1] = (float("inf"), frozenset(), frozenset())
    yield
    r._NAME_CACHE.clear()

def _patch_session(target="onboarding.services.retrieval.Session"):
    patcher = patch(target)
    mock_cls = patcher.start()
    session_mock = MagicMock()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher, session_mock

def _result(rows):
    """A mock query result whose .all() yields `rows`."""
    r = MagicMock()
    r.all.return_value = rows
    return r

def _embed():
    return patch(
        "onboarding.services.retrieval.embedding_service.embed_query", return_value=[0.1, 0.2]
    )

class TestQueryTerms:
    def test_full_name_becomes_weighted_phrase(self):
        from onboarding.services.retrieval import _query_terms

        terms, is_entity, name_phrases = _query_terms("what is Yogesh Kisslay working on")
        # The full name is matched as one weighted phrase (weight 2) so it outranks a
        # coincidental first-name hit; single tokens are kept (weight 1) for recall.
        assert ("Yogesh Kisslay", 2) in terms
        assert ("Yogesh", 1) in terms and ("Kisslay", 1) in terms
        assert is_entity is True  # capitalized proper noun → entity query
        assert name_phrases == ["Yogesh Kisslay"]  # full-name filter target

    def test_name_isolated_from_trailing_lowercase(self):
        from onboarding.services.retrieval import _query_terms

        # "create" trailing the name must NOT disqualify the full-name phrase.
        _, is_entity, name_phrases = _query_terms("what docs did Yogesh Kisslay create")
        assert name_phrases == ["Yogesh Kisslay"]
        assert is_entity is True

    def test_known_full_name_matched_with_words_around(self):
        from onboarding.services.retrieval import _query_terms

        # Lowercase full name embedded mid-sentence → still required as a phrase.
        _, _, name_phrases = _query_terms(
            "which docs did yogesh kisslay create last month",
            full_names=frozenset({"yogesh kisslay"}),
        )
        assert name_phrases == ["yogesh kisslay"]

    def test_issue_key_is_weighted_entity(self):
        from onboarding.services.retrieval import _query_terms

        terms, is_entity, name_phrases = _query_terms("status of AR-2847 please")
        assert ("AR-2847", 2) in terms
        assert is_entity is True and name_phrases == []

    def test_concept_query_is_not_entity(self):
        from onboarding.services.retrieval import _query_terms

        terms, is_entity, name_phrases = _query_terms("what is our deployment process")
        texts = [t for t, _ in terms]
        assert "deployment" in texts and "process" in texts
        assert "deployment process" in texts  # consecutive words → phrase too
        assert is_entity is False  # no proper noun / key → concept query
        assert name_phrases == []  # lowercase phrase is NOT treated as a name

    def test_all_stopwords_gives_nothing(self):
        from onboarding.services.retrieval import _query_terms

        terms, is_entity, name_phrases = _query_terms("what is it about")
        assert terms == [] and is_entity is False and name_phrases == []

    def test_lowercase_known_name_is_entity(self):
        from onboarding.services.retrieval import _query_terms

        # "sunadh" lowercase, but it's a known name word → entity, keyword-heavy.
        terms, is_entity, name_phrases = _query_terms(
            "what is sunadh working on", name_words=frozenset({"sunadh", "p"})
        )
        assert is_entity is True

    def test_lowercase_full_name_becomes_name_phrase(self):
        from onboarding.services.retrieval import _query_terms

        # "yogesh kisslay" lowercase matches a known full name → required phrase.
        terms, is_entity, name_phrases = _query_terms(
            "what is yogesh kisslay working on",
            name_words=frozenset({"yogesh", "kisslay"}),
            full_names=frozenset({"yogesh kisslay"}),
        )
        assert name_phrases == ["yogesh kisslay"]
        assert is_entity is True

    def test_unknown_lowercase_stays_concept(self):
        from onboarding.services.retrieval import _query_terms

        # No known-name match → still a concept query (not falsely promoted).
        _, is_entity, name_phrases = _query_terms(
            "deployment process", name_words=frozenset({"sunadh"}), full_names=frozenset()
        )
        assert is_entity is False and name_phrases == []

    def test_caps_number_of_terms(self):
        from onboarding.services.retrieval import _query_terms, _MAX_TERMS

        terms, _, _ = _query_terms("Alpha Bravo Charlie Delta Echo Foxtrot Golf Hotel India")
        assert len(terms) <= _MAX_TERMS

def _one(value):
    m = MagicMock()
    m.one.return_value = value
    return m

class TestNameMatching:
    def test_name_regex_has_word_boundaries(self):
        from onboarding.services.retrieval import _name_regex

        assert _name_regex("Ana") == r"\yAna\y"

    def test_word_in_whole_word_only(self):
        from onboarding.services.retrieval import _word_in

        assert _word_in("Ana", "Ana Smith") is True
        assert _word_in("Ana", "Diana Prince") is False  # not a substring match
        assert _word_in("raj", "Nataraj M C") is False  # 'raj' inside 'Nataraj' — no
        assert _word_in("Sunadh P", "Sunadh P") is True
        assert _word_in("X", None) is False

class TestCounts:
    def test_count_involvement_by_role(self):
        patcher, session = _patch_session()
        try:
            # four COUNT queries: assigned, reported, authored, involved
            session.exec.side_effect = [_one(2), _one(15), _one(9), _one(20)]
            from onboarding.services.retrieval import count_involvement

            out = count_involvement(1, "Sunadh")
            assert out == {
                "name": "Sunadh",
                "assigned": 2,
                "reported": 15,
                "authored": 9,
                "involved": 20,
            }
        finally:
            patcher.stop()

    def test_list_involvement_classifies_roles(self):
        patcher, session = _patch_session()
        try:
            # (source, page_id, title, status, assignee, reporter, meta)
            rows = [
                (
                    "jira",
                    "AR-1",
                    "Access",
                    "Open",
                    "Someone Else",
                    "Sunadh P",
                    {"issue_type": "AR"},
                ),
                ("jira", "AR-2", "Bug", "Closed", "Sunadh P", None, {"issue_type": "Bug"}),
                ("jira", "AR-3", "Note", "Open", None, None, {}),  # mentioned only
                ("confluence", "99", "Design", None, None, None, {"author": "Sunadh P"}),
                ("confluence", "88", "Edited", None, None, None, {"last_editor": "Sunadh P"}),
                ("confluence", "77", "Seen", None, None, None, {"author": "Other"}),  # mentioned
            ]
            session.exec.return_value.all.return_value = rows
            from onboarding.services.retrieval import list_involvement

            out = list_involvement(1, "Sunadh P")
            assert out["jira_total"] == 3 and out["confluence_total"] == 3
            jira = {j["key"]: j["roles"] for j in out["jira"]}
            assert jira["AR-1"] == ["reporter"]
            assert jira["AR-2"] == ["assignee"]
            assert jira["AR-3"] == ["mentioned"]
            conf = {c["page_id"]: c["roles"] for c in out["confluence"]}
            assert conf["99"] == ["author"]
            assert conf["88"] == ["editor"]
            assert conf["77"] == ["mentioned"]
        finally:
            patcher.stop()

    def test_leaderboard_single_metric_filters_bots(self):
        patcher, session = _patch_session()
        try:
            # (name, count) grouped, most first; a bot placeholder is filtered out.
            session.exec.return_value.all.return_value = [
                ("Automation for Jira", 999),  # dropped
                ("Suraj Nayak", 1715),
                (None, 5),  # null dropped
                ("Pulkeet Yadav", 1148),
            ]
            from onboarding.services.retrieval import leaderboard

            out = leaderboard(1, "reported", limit=5)
            assert out == [
                {"name": "Suraj Nayak", "reported": 1715},
                {"name": "Pulkeet Yadav", "reported": 1148},
            ]
        finally:
            patcher.stop()

    def test_leaderboard_involved_merges_roles(self):
        patcher, session = _patch_session()
        try:
            # three GROUP BYs: assignees, reporters, authors
            session.exec.side_effect = [
                _result([("Arun Iyer", 10), ("Nataraj M C", 100)]),  # assigned
                _result([("Arun Iyer", 20)]),  # reported
                _result([("Arun Iyer", 5), ("Prajwal H N", 50)]),  # authored
            ]
            from onboarding.services.retrieval import leaderboard

            out = leaderboard(1, "involved", limit=3)
            top = out[0]
            assert top["name"] == "Nataraj M C" and top["involved"] == 100
            arun = next(r for r in out if r["name"] == "Arun Iyer")
            assert arun["involved"] == 35 and arun["assigned"] == 10 and arun["authored"] == 5
        finally:
            patcher.stop()

    def test_leaderboard_assigned_and_authored(self):
        from onboarding.services.retrieval import leaderboard

        for metric in ("assigned", "authored"):
            patcher, session = _patch_session()
            try:
                session.exec.return_value.all.return_value = [("Nataraj M C", 42)]
                out = leaderboard(1, metric, limit=5)
                assert out == [{"name": "Nataraj M C", metric: 42}]
            finally:
                patcher.stop()

    def test_leaderboard_invalid_metric_defaults_involved(self):
        patcher, session = _patch_session()
        try:
            session.exec.side_effect = [_result([("A", 1)]), _result([]), _result([])]
            from onboarding.services.retrieval import leaderboard

            out = leaderboard(1, "bogus", limit=3)
            assert out[0]["name"] == "A" and "involved" in out[0]
        finally:
            patcher.stop()

    def test_top_issues_cross_source(self):
        patcher, session = _patch_session()
        try:
            jira = MagicMock(confluence_page_id="AR-1", title="Access", source="jira")
            conf = MagicMock(confluence_page_id="123", title="Design", source="confluence")
            session.exec.return_value.all.return_value = [jira, conf]
            from onboarding.services.retrieval import top_issues

            out = top_issues(1, "Sunadh", limit=3)
            assert out == [
                {"page_id": "AR-1", "title": "Access", "source": "jira"},
                {"page_id": "123", "title": "Design", "source": "confluence"},
            ]
        finally:
            patcher.stop()

class TestKnownNames:
    def test_load_builds_full_and_word_sets(self):
        patcher, session = _patch_session()
        try:
            # Four distinct queries: assignees, reporters, Confluence authors, editors.
            session.exec.side_effect = [
                _result(["Sunadh P", None, "Yogesh Kisslay"]),  # assignees
                _result(["Nataraj M C"]),  # reporters
                _result(["Prajwal H N"]),  # confluence authors
                _result(["Okky Angga"]),  # confluence editors
            ]
            from onboarding.services.retrieval import _load_known_names

            full, words = _load_known_names(1)
            assert "yogesh kisslay" in full and "sunadh p" in full
            assert "sunadh" in words and "kisslay" in words and "nataraj" in words
            assert "prajwal" in words and "okky" in words  # Confluence authors included
            assert "c" not in words  # single-char token dropped
        finally:
            patcher.stop()

    def test_cache_reuses_within_ttl(self):
        from onboarding.services import retrieval as r

        r._NAME_CACHE.clear()
        with patch.object(
            r, "_load_known_names", return_value=(frozenset({"a"}), frozenset({"a"}))
        ) as load:
            r._known_names(7)
            r._known_names(7)
        assert load.call_count == 1  # second call served from cache
        r._NAME_CACHE.clear()

    def test_cache_swallows_errors(self):
        from onboarding.services import retrieval as r

        r._NAME_CACHE.clear()
        with patch.object(r, "_load_known_names", side_effect=Exception("db down")):
            full, words = r._known_names(9)
        assert full == frozenset() and words == frozenset()
        r._NAME_CACHE.clear()

    def test_refresh_names_evicts_company(self):
        from onboarding.services import retrieval as r

        r._NAME_CACHE[5] = (float("inf"), frozenset({"a"}), frozenset({"a"}))
        r._NAME_CACHE[6] = (float("inf"), frozenset({"b"}), frozenset({"b"}))
        r.refresh_names(5)
        assert 5 not in r._NAME_CACHE  # evicted
        assert 6 in r._NAME_CACHE  # other company untouched (per-company cache)
        r._NAME_CACHE.clear()

class TestRetrieve:
    def test_pure_semantic_when_no_keywords(self):
        # A query of only stopwords → no lexical pass, single query.
        patcher, session = _patch_session()
        try:
            session.exec.side_effect = [_result([("c", "T", "p1", "confluence")])]
            with _embed():
                from onboarding.services.retrieval import retrieve

                out = retrieve(1, "what is it about", k=5)
            assert session.exec.call_count == 1  # no lexical query
            assert out == [{"content": "c", "title": "T", "page_id": "p1", "source": "confluence"}]
        finally:
            patcher.stop()

    def test_hybrid_puts_lexical_matches_first(self):
        patcher, session = _patch_session()
        try:
            vector = [("vec", "V", "pv", "confluence")]
            lexical = [("lex", "L", "pl", "jira")]
            session.exec.side_effect = [_result(vector), _result(lexical)]
            with _embed():
                from onboarding.services.retrieval import retrieve

                out = retrieve(1, "what is Sunadh working on", k=5)
            assert session.exec.call_count == 2  # vector + lexical
            # Lexical (literal name match) ranked ahead of the semantic-only hit.
            assert [c["page_id"] for c in out] == ["pl", "pv"]
        finally:
            patcher.stop()

    def test_full_name_query_runs_phrase_filter(self):
        # Full-name query → lexical filter requires the whole name (name_phrases branch).
        patcher, session = _patch_session()
        try:
            lexical = [("lex", "L", "AR-1", "jira")]
            vector = [("vec", "V", "p2", "confluence")]
            session.exec.side_effect = [_result(vector), _result(lexical)]
            with _embed():
                from onboarding.services.retrieval import retrieve

                out = retrieve(1, "what is Yogesh Kisslay working on", k=12)
            assert session.exec.call_count == 2
            assert [c["page_id"] for c in out] == ["AR-1", "p2"]
        finally:
            patcher.stop()

    def test_hybrid_false_skips_lexical(self):
        patcher, session = _patch_session()
        try:
            session.exec.side_effect = [_result([("c", "T", "p1", "confluence")])]
            with _embed():
                from onboarding.services.retrieval import retrieve

                retrieve(1, "what is Sunadh working on", k=5, hybrid=False)
            assert session.exec.call_count == 1  # lexical suppressed
        finally:
            patcher.stop()

    def test_dedupes_across_lexical_and_vector(self):
        patcher, session = _patch_session()
        try:
            shared = ("dup", "D", "pd", "jira")
            session.exec.side_effect = [
                _result([shared, ("vec", "V", "pv", "confluence")]),  # vector
                _result([shared]),  # lexical — same chunk
            ]
            with _embed():
                from onboarding.services.retrieval import retrieve

                out = retrieve(1, "Sunadh", k=5)
            assert [c["page_id"] for c in out] == ["pd", "pv"]  # dup appears once
        finally:
            patcher.stop()

    def test_caps_at_k(self):
        patcher, session = _patch_session()
        try:
            vector = [(f"v{i}", "V", f"pv{i}", "confluence") for i in range(5)]
            lexical = [(f"l{i}", "L", f"pl{i}", "jira") for i in range(5)]
            session.exec.side_effect = [_result(vector), _result(lexical)]
            with _embed():
                from onboarding.services.retrieval import retrieve

                out = retrieve(1, "Sunadh", k=2)
            assert len(out) == 2  # capped
        finally:
            patcher.stop()

    def test_lexical_take_reserves_semantic_slots(self):
        # With k=8, lexical takes max(3, k-3)=5 rows, leaving ~3 for semantic fill.
        patcher, session = _patch_session()
        try:
            vector = [(f"v{i}", "V", f"pv{i}", "confluence") for i in range(8)]
            lexical = [(f"l{i}", "L", f"pl{i}", "jira") for i in range(8)]
            session.exec.side_effect = [_result(vector), _result(lexical)]
            with _embed():
                from onboarding.services.retrieval import retrieve

                out = retrieve(1, "Sunadh", k=8)
            ids = [c["page_id"] for c in out]
            assert ids[:5] == ["pl0", "pl1", "pl2", "pl3", "pl4"]  # 5 lexical first
            assert "pv0" in ids  # then a few semantic fill the rest
            assert len(out) == 8
        finally:
            patcher.stop()

    def test_concept_query_keeps_more_semantic(self):
        # A concept query (no proper noun / key) is balanced: k=12 -> 6 keyword / 6 semantic.
        patcher, session = _patch_session()
        try:
            vector = [(f"v{i}", "V", f"pv{i}", "confluence") for i in range(12)]
            lexical = [(f"l{i}", "L", f"pl{i}", "confluence") for i in range(12)]
            session.exec.side_effect = [_result(vector), _result(lexical)]
            with _embed():
                from onboarding.services.retrieval import retrieve

                out = retrieve(1, "what is our deployment process", k=12)
            ids = [c["page_id"] for c in out]
            assert ids[:6] == [f"pl{i}" for i in range(6)]  # only 6 lexical (balanced)
            assert ids[6:] == [f"pv{i}" for i in range(6)]  # 6 semantic
        finally:
            patcher.stop()

    def test_empty(self):
        patcher, session = _patch_session()
        try:
            session.exec.side_effect = [_result([])]
            with _embed():
                from onboarding.services.retrieval import retrieve

                assert retrieve(1, "what is it") == []
        finally:
            patcher.stop()

    def test_sources_filter_applied(self):
        patcher, session = _patch_session()
        try:
            session.exec.side_effect = [_result([("c", "T", "p1", "confluence")])]
            with _embed():
                from onboarding.services.retrieval import retrieve

                out = retrieve(1, "what is it", sources=["confluence"])
            assert out == [{"content": "c", "title": "T", "page_id": "p1", "source": "confluence"}]
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

    def test_passes_hybrid_flag(self):
        with patch("onboarding.services.retrieval.retrieve", return_value=[]) as retr:
            from onboarding.services.retrieval import retrieve_context

            assert retrieve_context(1, "q", sources=["confluence"], hybrid=False) == ""
            assert retr.call_args.kwargs["hybrid"] is False
