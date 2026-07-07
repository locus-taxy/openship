"""Retrieval over the company knowledge base (pgvector), with an optional lexical
boost so literal terms — people's names, Jira issue keys — aren't lost by pure
semantic search."""

import logging
import re
import time
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import case, func, or_
from sqlmodel import Session, select

from database import engine
from onboarding.models.document_chunk import DocumentChunk
from onboarding.models.document_page import DocumentPage
from onboarding.services import embeddings as embedding_service

logger = logging.getLogger(__name__)

_DEFAULT_K = 12

# Cache of known people per company (from Jira assignee/reporter) so a LOWERCASE name
# in a query — "what is sunadh working on" — is still recognized as a person. Refreshed
# lazily on a TTL (names change only on re-ingest).
_NAME_CACHE: dict = {}
_NAME_TTL_SECONDS = 600

def _load_known_names(company_id: int) -> Tuple[frozenset, frozenset]:
    """(full_names_lower, name_words_lower) from Jira assignee/reporter columns AND
    Confluence authors/editors (meta) — so both Jira people and doc authors are
    recognized, even when typed lowercase."""
    with Session(engine) as session:

        def _distinct(column, *conds):
            stmt = (
                select(column).where(DocumentPage.company_id == company_id).where(*conds).distinct()
            )
            return session.exec(stmt).all()

        names = (
            _distinct(DocumentPage.assignee, DocumentPage.assignee.is_not(None))
            + _distinct(DocumentPage.reporter, DocumentPage.reporter.is_not(None))
            + _distinct(
                DocumentPage.meta["author"].astext,
                DocumentPage.source == "confluence",
                DocumentPage.meta.is_not(None),
            )
            + _distinct(
                DocumentPage.meta["last_editor"].astext,
                DocumentPage.source == "confluence",
                DocumentPage.meta.is_not(None),
            )
        )
    full: set = set()
    words: set = set()
    for name in names:
        low = (name or "").strip().lower()
        if not low:
            continue
        full.add(low)
        for w in low.split():
            if len(w) >= 3:
                words.add(w)
    return frozenset(full), frozenset(words)

def _known_names(company_id: int) -> Tuple[frozenset, frozenset]:
    """Cached known-name sets for a company (TTL-refreshed). Keyed by company_id, so
    each company has its own set and never sees another's names."""
    cached = _NAME_CACHE.get(company_id)
    now = time.time()
    if cached and cached[0] > now:
        return cached[1], cached[2]
    try:
        full, words = _load_known_names(company_id)
    except Exception:  # never let a name-cache hiccup break retrieval
        full, words = frozenset(), frozenset()
    _NAME_CACHE[company_id] = (now + _NAME_TTL_SECONDS, full, words)
    return full, words

def refresh_names(company_id: int) -> None:
    """Drop a company's cached name set so the next lookup reloads it. Called right
    after a Jira ingest so newly-added assignees/reporters are recognized instantly
    instead of after the TTL."""
    _NAME_CACHE.pop(company_id, None)

# Words too common to be useful as a lexical filter (question words, filler). A
# keyword search on these would match half the corpus, so we drop them and keep
# the distinctive tokens (names, product terms, issue keys). They also act as
# phrase boundaries, so "Yogesh Kisslay working on" yields the phrase "Yogesh
# Kisslay", not "Yogesh Kisslay working on".
_STOPWORDS = frozenset(
    """
    a an the and or of to in on for with is are was were be been being do does did done
    what who whom whose where when why how which that this these those there here
    i me my we our us you your he she it they them his her their its one
    can could will would shall should may might must have has had get got give given
    show list find tell about into from by at as up out over under again more most least
    working work worked assigned task tasks issue issues bug bugs ticket tickets status
    currently now please help me doing involved make made want need using use also still
    vs versus than then so such very just only own same other another both each every
    any some all none no not few many much several currently kindly regarding related
    know let anyone someone somebody people person thing things stuff detail details
    info information update updates working currently ongoing recent recently latest
    """.split()
)

# A Jira-style issue key, e.g. AR-2847 — always worth a literal match.
_ISSUE_KEY_RE = re.compile(r"[A-Za-z]{2,}-\d+")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]+")
_MAX_TERMS = 8
_PHRASE_WEIGHT = 2  # a full-phrase / issue-key hit counts double a single-word hit
_TOKEN_WEIGHT = 1

def _query_terms(
    query: str,
    name_words: frozenset = frozenset(),
    full_names: frozenset = frozenset(),
):
    """Break a query into weighted literal-match terms and classify it.

    Returns (terms, is_entity_query, name_phrases):
    - `terms`: list of (text, weight). Issue keys (AR-2847) and multi-word phrases
      ("Yogesh Kisslay") get the higher PHRASE weight, so a chunk with the FULL
      phrase outranks one sharing a single word (a different "Yogesh"); individual
      distinctive words get the lower TOKEN weight (kept for recall/ranking).
    - `is_entity_query`: True when the query names something specific — an issue key,
      a capitalized proper noun, or a KNOWN person name (even lowercase, via the
      `name_words`/`full_names` sets) — so the caller leans on keyword matches; a
      plain concept question ("what is our deploy process") is False → lean semantic.
    - `name_phrases`: phrases that are full names. When present the caller REQUIRES
      the whole phrase, so a coincidental first-name match (another "Yogesh") is
      excluded. Detected by capitalization OR by matching a known full name."""
    keys = _ISSUE_KEY_RE.findall(query)
    without_keys = _ISSUE_KEY_RE.sub(" ", query)

    tokens: List[str] = []
    phrases: List[str] = []  # consecutive non-stopword words (concept phrase weighting)
    name_phrases: List[str] = []  # phrases that are a full name
    run: List[str] = []
    cap_run: List[str] = []  # consecutive CAPITALIZED words — a proper-noun (full name)
    has_proper_noun = False

    def _close_run():
        if len(run) >= 2:
            phrases.append(" ".join(run))

    def _close_cap():
        # A capitalized adjacency of 2+ words is a full name — e.g. "Yogesh Kisslay".
        # Tracked separately from `run` so a trailing lowercase word ("... create")
        # doesn't swallow / disqualify the name.
        if len(cap_run) >= 2:
            name_phrases.append(" ".join(cap_run))

    for tok in _WORD_RE.findall(without_keys):
        if tok.lower() in _STOPWORDS:
            _close_run()
            _close_cap()
            run, cap_run = [], []
            continue
        tokens.append(tok)
        run.append(tok)
        if tok[0].isupper():
            has_proper_noun = True
            cap_run.append(tok)
        else:
            _close_cap()
            cap_run = []
    _close_run()
    _close_cap()

    # Known-name detection (handles LOWERCASE names). A token that is a known name
    # word makes this an entity query; a known FULL name appearing anywhere in the
    # query becomes a required name_phrase (so "yogesh kisslay" excludes other
    # Yogeshes), even lowercase and even with words around it.
    has_known_name = any(t.lower() in name_words for t in tokens)
    if full_names:
        q_low = query.lower()
        existing = {p.lower() for p in name_phrases}
        for fn in full_names:
            if fn not in existing and " " in fn and fn in q_low:
                name_phrases.append(fn)
                existing.add(fn)

    terms: List[tuple] = []
    seen: set = set()

    def _add(text: str, weight: int):
        low = text.lower()
        if low not in seen:
            seen.add(low)
            terms.append((text, weight))

    for key in keys:
        _add(key, _PHRASE_WEIGHT)
    for phrase in phrases:
        _add(phrase, _PHRASE_WEIGHT)
    for token in tokens:
        _add(token, _TOKEN_WEIGHT)

    is_entity_query = bool(keys) or has_proper_noun or has_known_name
    return terms[:_MAX_TERMS], is_entity_query, name_phrases

def _base_select(company_id: int, sources: Optional[Sequence[str]]):
    stmt = (
        select(
            DocumentChunk.content,
            DocumentPage.title,
            DocumentPage.confluence_page_id,
            DocumentChunk.source,
        )
        .join(DocumentPage, DocumentChunk.page_id == DocumentPage.id)
        .where(DocumentChunk.company_id == company_id)
        .where(DocumentPage.is_active == True)  # noqa: E712
    )
    if sources:
        stmt = stmt.where(DocumentChunk.source.in_(list(sources)))
    return stmt

def retrieve(
    company_id: int,
    query: str,
    k: int = _DEFAULT_K,
    sources: Optional[Sequence[str]] = None,
    hybrid: bool = True,
) -> List[dict]:
    """Return up to k active chunks for a query, each as
    {title, content, page_id, source}. `sources` scopes to specific knowledge
    sources (e.g. ["confluence"] for onboarding); None = all sources (chat).

    When `hybrid` is on, a literal keyword search runs alongside the semantic one.
    Multi-word phrases ("Yogesh Kisslay") are matched WHOLE and weighted above single
    words, so the full-name person outranks a coincidental first-name match. How much
    the two searches contribute adapts to the query: an entity query (a name or issue
    key) leans on keyword matches; a plain concept query leans on semantic ones."""
    query_vector = embedding_service.embed_query(query)
    distance = DocumentChunk.embedding.cosine_distance(query_vector)

    if hybrid:
        full_names, name_words = _known_names(company_id)
        terms, is_entity_query, name_phrases = _query_terms(query, name_words, full_names)
    else:
        terms, is_entity_query, name_phrases = [], False, []

    with Session(engine) as session:
        # Exact KNN when a `sources` filter is set. The pgvector HNSW index returns
        # the GLOBAL nearest chunks and only THEN applies the source filter — so a
        # source that's sparse near the query (e.g. Confluence for a Jira-heavy topic
        # like RBAC/audit) can be filtered down to ZERO even though relevant docs
        # exist. Turning off index SCANS makes Postgres rank by distance within the
        # filtered rows, always returning that source's true nearest. We deliberately
        # leave bitmapscan ON so the btree filter on (company_id, source) is still
        # used to select the small candidate set — only the ANN ordering index is
        # bypassed, not the filter indexes. Unfiltered chat keeps the ANN index.
        if sources:
            conn = session.connection()
            conn.exec_driver_sql("SET LOCAL enable_indexscan = OFF")
        base = _base_select(company_id, sources)
        vector_rows = session.exec(base.order_by(distance).limit(k)).all()

        lexical_rows: list = []
        if terms:
            # A chunk is a candidate if it matches the filter. For a FULL-NAME query
            # ("Yogesh Kisslay") we require the whole name, so a different "Yogesh"
            # never qualifies. Otherwise a chunk matching ANY term qualifies (recall).
            if name_phrases:
                filter_clauses = [DocumentChunk.content.ilike(f"%{p}%") for p in name_phrases]
            else:
                filter_clauses = [DocumentChunk.content.ilike(f"%{t}%") for t, _ in terms]
            # Rank still uses ALL weighted terms (whole-phrase hit counts double a
            # single word); tie-break by semantic closeness.
            score = None
            for text, weight in terms:
                contribution = case((DocumentChunk.content.ilike(f"%{text}%"), weight), else_=0)
                score = contribution if score is None else score + contribution
            lexical_rows = session.exec(
                base.where(or_(*filter_clauses)).order_by(score.desc(), distance).limit(k)
            ).all()

    result = _merge(lexical_rows, vector_rows, k, is_entity_query)
    logger.info(
        "retrieve: sources=%s hybrid=%s k=%d -> %d chunk(s) [vector=%d lexical=%d] q=%r",
        list(sources) if sources else "all",
        hybrid,
        k,
        len(result),
        len(vector_rows),
        len(lexical_rows),
        (query[:80] + "…") if len(query) > 80 else query,
    )
    return result

def _merge(lexical_rows: list, vector_rows: list, k: int, is_entity_query: bool) -> List[dict]:
    """Lexical (literal) matches first, then semantic, deduped and capped at k. The
    lexical share adapts to the query:
    - entity query (name / issue key): keyword-heavy — its literal matches ARE the
      answer, and pure-semantic neighbours are mostly unrelated filler (other
      people's issues) that cause misattribution, so keep only a small semantic net.
    - concept query: balanced — keep more semantic so synonym/paraphrase docs (which
      literal search can't catch) get in."""
    if not lexical_rows:
        lex_take = 0
    elif is_entity_query:
        lex_take = max(3, k - 3)  # e.g. k=12 -> 9 keyword / 3 semantic
    else:
        lex_take = max(2, k // 2)  # e.g. k=12 -> 6 keyword / 6 semantic
    ordered = list(lexical_rows[:lex_take]) + list(vector_rows)
    out: List[dict] = []
    seen: set = set()
    for content, title, pid, source in ordered:
        # Dedupe by PAGE, not chunk — two chunks of the same page shouldn't both eat
        # a slot; keep the first (highest-ranked) so k slots cover k distinct docs.
        key = (source, pid)
        if key in seen:
            continue
        seen.add(key)
        out.append({"content": content, "title": title, "page_id": pid, "source": source})
        if len(out) >= k:
            break
    return out

def retrieve_context(
    company_id: int,
    query: str,
    k: int = _DEFAULT_K,
    sources: Optional[Sequence[str]] = None,
    hybrid: bool = True,
) -> str:
    """Retrieve and format chunks as a single context string for a prompt."""
    chunks = retrieve(company_id, query, k, sources=sources, hybrid=hybrid)
    return "\n\n".join(f"=== {c['title']} ===\n{c['content']}" for c in chunks)

# ── exact involvement counts (for "how many / who did more" questions) ───────────
# Retrieval returns a top-k sample and can't count totals; these run real COUNTs
# over the whole knowledge base (Jira issues + Confluence docs) for true numbers.

def _name_regex(name: str) -> str:
    r"""A WORD-BOUNDARY (\y) Postgres regex for a person's name, so 'Ana' matches
    'Ana Smith' but not 'Diana'/'management', and 'raj' doesn't match 'Nataraj'.
    Substring matching (%name%) over-matches badly on short/partial names."""
    return r"\y" + re.escape(name) + r"\y"

def _name_match(column, name: str):
    """Case-insensitive, word-boundary match of `name` within a column."""
    return column.op("~*")(_name_regex(name))

def _involved_clause(name: str):
    """A person is 'involved' in a page by holding a ROLE on it: Jira assignee/
    reporter or Confluence author/editor. We deliberately do NOT count mere text
    mentions — being named in someone else's comment isn't 'their work', and matching
    free text over-counts common-word names (Mark, Will, Rose, …)."""
    return or_(
        _name_match(DocumentPage.assignee, name),
        _name_match(DocumentPage.reporter, name),
        _name_match(DocumentPage.meta["author"].astext, name),
        _name_match(DocumentPage.meta["last_editor"].astext, name),
    )

def count_involvement(company_id: int, name: str) -> dict:
    """Exact counts for a person by role across the whole knowledge base: assigned +
    reported (Jira), authored (Confluence docs written/edited), and involved (any of
    those, or named in the text). Uses word-boundary matching to avoid over-counting."""
    with Session(engine) as session:

        def _count(condition, source: Optional[str] = None):
            stmt = (
                select(func.count(DocumentPage.id))
                .where(DocumentPage.company_id == company_id)
                .where(DocumentPage.is_active == True)  # noqa: E712
                .where(condition)
            )
            if source:
                stmt = stmt.where(DocumentPage.source == source)
            return int(session.exec(stmt).one())

        assigned = _count(_name_match(DocumentPage.assignee, name), source="jira")
        reported = _count(_name_match(DocumentPage.reporter, name), source="jira")
        authored = _count(
            or_(
                _name_match(DocumentPage.meta["author"].astext, name),
                _name_match(DocumentPage.meta["last_editor"].astext, name),
            ),
            source="confluence",
        )
        involved = _count(_involved_clause(name))
    return {
        "name": name,
        "assigned": assigned,
        "reported": reported,
        "authored": authored,
        "involved": involved,
    }

_LEADERBOARD_METRICS = ("assigned", "reported", "authored", "involved")
# Non-human placeholders/bots to keep out of "top contributors" rankings.
_NON_PERSON_NAMES = ("former user", "(deleted)", "unknown user", "automation for jira", "anonymous")

def _is_real_person(name: str) -> bool:
    low = (name or "").lower()
    return bool(low) and not any(x in low for x in _NON_PERSON_NAMES)

def _group_counts(session, company_id: int, column, source: Optional[str]):
    """(name, count) grouped by a name column, most first. Skips null / non-human names."""
    stmt = (
        select(column, func.count(DocumentPage.id))
        .where(DocumentPage.company_id == company_id)
        .where(DocumentPage.is_active == True)  # noqa: E712
        .where(column.is_not(None))
    )
    if source:
        stmt = stmt.where(DocumentPage.source == source)
    stmt = stmt.group_by(column).order_by(func.count(DocumentPage.id).desc())
    return [(name, int(c)) for name, c in session.exec(stmt).all() if _is_real_person(name)]

def leaderboard(company_id: int, metric: str = "involved", limit: int = 10) -> list:
    """Open-ended ranking: the top people by a metric — 'assigned'/'reported' (Jira),
    'authored' (Confluence), or 'involved' (sum of role-holdings across both). Answers
    'who reported the most', 'top contributors', etc. Returns ranked dicts."""
    if metric not in _LEADERBOARD_METRICS:
        metric = "involved"
    with Session(engine) as session:
        if metric == "assigned":
            rows = _group_counts(session, company_id, DocumentPage.assignee, "jira")
            return [{"name": n, "assigned": c} for n, c in rows[:limit]]
        if metric == "reported":
            rows = _group_counts(session, company_id, DocumentPage.reporter, "jira")
            return [{"name": n, "reported": c} for n, c in rows[:limit]]
        if metric == "authored":
            rows = _group_counts(
                session, company_id, DocumentPage.meta["author"].astext, "confluence"
            )
            return [{"name": n, "authored": c} for n, c in rows[:limit]]
        # involved: merge role-holdings per person (a "contribution score").
        scores: dict = {}

        def _acc(rows, key):
            for name, c in rows:
                scores.setdefault(name, {"assigned": 0, "reported": 0, "authored": 0})[key] = c

        _acc(_group_counts(session, company_id, DocumentPage.assignee, "jira"), "assigned")
        _acc(_group_counts(session, company_id, DocumentPage.reporter, "jira"), "reported")
        _acc(
            _group_counts(session, company_id, DocumentPage.meta["author"].astext, "confluence"),
            "authored",
        )
    ranked = sorted(scores.items(), key=lambda kv: sum(kv[1].values()), reverse=True)[:limit]
    return [{"name": n, **v, "involved": sum(v.values())} for n, v in ranked]

def top_issues(company_id: int, name: str, limit: int = 3) -> List[dict]:
    """A few example items a person is involved in (Jira issues + Confluence docs),
    for citation chips."""
    with Session(engine) as session:
        rows = session.exec(
            select(DocumentPage)
            .where(DocumentPage.company_id == company_id)
            .where(DocumentPage.is_active == True)  # noqa: E712
            .where(_involved_clause(name))
            .order_by(DocumentPage.id.desc())
            .limit(limit)
        ).all()
    return [{"page_id": r.confluence_page_id, "title": r.title, "source": r.source} for r in rows]

def _word_in(name: str, text: Optional[str]) -> bool:
    """Whole-word, case-insensitive membership (Python side, for role classification)."""
    return (
        bool(text) and re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE) is not None
    )

def list_involvement(company_id: int, name: str, limit: int = 40) -> dict:
    """Every Jira issue + Confluence doc a person is involved in, with their role per
    item — the COMPLETE list (not a top-k sample) for 'give me all work of X'.
    Returns {"jira": [...], "confluence": [...], "jira_total", "confluence_total"}."""
    with Session(engine) as session:
        rows = session.exec(
            select(
                DocumentPage.source,
                DocumentPage.confluence_page_id,
                DocumentPage.title,
                DocumentPage.status,
                DocumentPage.assignee,
                DocumentPage.reporter,
                DocumentPage.meta,
            )
            .where(DocumentPage.company_id == company_id)
            .where(DocumentPage.is_active == True)  # noqa: E712
            .where(_involved_clause(name))
            .order_by(DocumentPage.id.desc())
        ).all()

    jira: List[dict] = []
    confluence: List[dict] = []
    for source, page_id, title, status, assignee, reporter, meta in rows:
        meta = meta or {}
        if source == "jira":
            roles = []
            if _word_in(name, assignee):
                roles.append("assignee")
            if _word_in(name, reporter):
                roles.append("reporter")
            if not roles:
                roles.append("mentioned")
            jira.append(
                {
                    "key": page_id,
                    "title": title,
                    "status": status,
                    "roles": roles,
                    "type": meta.get("issue_type"),
                    "priority": meta.get("priority"),
                }
            )
        else:
            roles = []
            if _word_in(name, meta.get("author")):
                roles.append("author")
            if _word_in(name, meta.get("last_editor")):
                roles.append("editor")
            if not roles:
                roles.append("mentioned")
            confluence.append({"page_id": page_id, "title": title, "roles": roles})

    return {
        "jira": jira[:limit],
        "confluence": confluence[:limit],
        "jira_total": len(jira),
        "confluence_total": len(confluence),
    }
