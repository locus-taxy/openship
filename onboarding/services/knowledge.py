"""Section-aware RAG Q&A over the company knowledge base, plus persistent chats.

`query` is a one-shot Q&A. The chat_* functions add ChatGPT-style conversations:
persistent history per user, with prior turns fed back to the model for follow-ups.
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from database import engine
from onboarding.models.knowledge_chat import KnowledgeChat
from onboarding.models.knowledge_message import KnowledgeMessage
from onboarding.services import retrieval as retrieval_service
from onboarding.services import generation as llm_service
from onboarding.services import confluence as confluence_service

_RETRIEVE_K = 12
# How many prior messages (user + assistant) to feed back as follow-up context.
_HISTORY_MESSAGES = 12
# Retrieve across the whole knowledge base — both Confluence pages and Jira issues.
_CHAT_SOURCES = ["confluence", "jira"]

def _format_context(chunks: list) -> str:
    """Format retrieved chunks for the prompt, tagging each with its source so the
    model can attribute answers ('per Jira issue ENG-123', 'per Confluence')."""
    lines = []
    for c in chunks:
        source = c.get("source", "confluence")
        tag = f"Jira issue {c['page_id']}" if source == "jira" else "Confluence"
        lines.append(f"=== [{tag}] {c['title']} ===\n{c['content']}")
    return "\n\n".join(lines)

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BARE_URL_RE = re.compile(r"https?://[^\s)\]]+")

def _scrub_text_links(text: str, context: str) -> str:
    """Remove any URL the model produced that does NOT appear verbatim in the
    retrieved excerpts — the model tends to hallucinate plausible-looking links
    (e.g. jira.example.com). Markdown links keep their label (link stripped); bare
    fabricated URLs are dropped. Real doc URLs (present in context) survive."""

    def _md(m):
        label, url = m.group(1), m.group(2)
        return m.group(0) if url in context else label

    text = _MD_LINK_RE.sub(_md, text)
    text = _BARE_URL_RE.sub(lambda m: m.group(0) if m.group(0) in context else "", text)
    # Tidy up double spaces / dangling spaces left by a removed bare URL.
    return re.sub(r"[ \t]{2,}", " ", text).strip()

def _scrub_block_links(blocks: list, context: str) -> list:
    """Apply _scrub_text_links to every human-visible string in the block tree."""
    for b in blocks:
        if isinstance(b.get("content"), str):
            b["content"] = _scrub_text_links(b["content"], context)
        if isinstance(b.get("items"), list):
            b["items"] = [_scrub_text_links(str(i), context) for i in b["items"]]
        if isinstance(b.get("headers"), list):
            b["headers"] = [_scrub_text_links(str(h), context) for h in b["headers"]]
        if isinstance(b.get("rows"), list):
            b["rows"] = [
                [_scrub_text_links(str(c), context) for c in row] if isinstance(row, list) else row
                for row in b["rows"]
            ]
    return blocks

def _answer(company_id: int, question: str, provider, api_key, model, history=None) -> dict:
    """Retrieve relevant chunks and answer, with deduped citations. Shared by the
    one-shot query and the chat message path. Retrieves across all sources."""
    chunks = retrieval_service.retrieve(company_id, question, k=_RETRIEVE_K, sources=_CHAT_SOURCES)
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No documents are available yet. Connect Atlassian and ingest content first.",
        )
    context = _format_context(chunks)
    answer = llm_service.answer_from_context(
        question=question,
        context=context,
        provider=provider,
        api_key=api_key,
        model=model,
        history=history,
    )
    if not answer:
        raise HTTPException(status_code=500, detail="Failed to generate an answer.")
    answer = _scrub_text_links(answer, context)  # drop any hallucinated URLs
    site_url = confluence_service.get_site_url(company_id)
    citations = _filter_cited(_dedupe_citations(chunks, site_url), answer)
    return {"answer": answer, "citations": citations}

def query(
    company_id: int,
    question: str,
    provider: str,
    api_key: str,
    model: Optional[str],
) -> dict:
    """One-shot: retrieve relevant chunks and answer the question, with citations."""
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="Ask a question.")
    return _answer(company_id, question, provider, api_key, model)

def _citation_url(source: str, page_id: str, site_url: Optional[str]) -> Optional[str]:
    """Deep-link a citation back to the source: a Confluence page or a Jira issue."""
    if not site_url or not page_id:
        return None
    base = site_url.rstrip("/")
    if source == "jira":
        return f"{base}/browse/{page_id}"
    return f"{base}/wiki/pages/viewpage.action?pageId={page_id}"

def _dedupe_citations(chunks: list, site_url: Optional[str] = None) -> list:
    seen: set = set()
    citations = []
    for c in chunks:
        source = c.get("source", "confluence")
        key = (source, c["page_id"])
        if key not in seen:
            seen.add(key)
            citations.append(
                {
                    "title": c["title"],
                    "page_id": c["page_id"],
                    "source": source,
                    "url": _citation_url(source, c["page_id"], site_url),
                }
            )
    return citations

def _filter_cited(citations: list, answer_text: str) -> list:
    """Narrow sources to the ones the answer actually references — a chunk whose
    id/key (e.g. AR-2847) appears in the reply. Hybrid retrieval deliberately pulls
    in extra semantically-near chunks; without this, those unrelated items would be
    listed as 'Sources' even though the answer never used them.

    Falls back to the full list when the answer names none of them, so a genuinely
    doc-grounded reply never ends up with zero sources. A citation is 'referenced'
    if its id/key OR its title appears in the answer — Confluence page-ids are
    numeric and never show up in prose, so title-matching keeps those sources."""
    text = answer_text.lower()

    def _referenced(c: dict) -> bool:
        if str(c.get("page_id", "")).lower() in text:
            return True
        title = str(c.get("title", "")).strip().lower()
        return bool(title) and title in text

    cited = [c for c in citations if _referenced(c)]
    return cited or citations

def _blocks_to_text(blocks: list) -> str:
    """Flatten structured blocks to plain text — used as the assistant turn's text
    for conversation history and as a fallback. Keeps it lossy-but-useful."""
    parts = []
    for b in blocks:
        if b.get("content"):
            parts.append(str(b["content"]))
        elif b.get("items"):
            parts.append("\n".join(str(i) for i in b["items"]))
        elif b.get("headers"):
            parts.append(" | ".join(str(h) for h in b.get("headers", [])))
            for row in b.get("rows", []):
                parts.append(" | ".join(str(c) for c in row))
    # Empty on purpose (e.g. a divider-only answer): return "" rather than a sentinel
    # so it isn't fed back as poisoned history — the generator skips empty turns.
    return "\n\n".join(parts).strip()

# Cheap gate: only spend a planner LLM call when the question smells like a
# count/comparison. Normal questions skip this entirely.
_COUNT_CUES = re.compile(
    r"\b(how many|how much|number of|count|counts|compare|comparison|more|most|fewer|"
    r"less|least|vs|versus|who has|which of|involved in more|top|ranking|leaderboard|"
    r"who did|who wrote|who reported|who authored)\b",
    re.I,
)

def _count_blocks(stats: list) -> list:
    """Deterministic answer blocks from exact involvement counts (no LLM = no made-up
    numbers). One person → a sentence; multiple → a ranked comparison + table."""
    if len(stats) == 1:
        s = stats[0]
        return [
            {
                "type": "paragraph",
                "content": (
                    f"{s['name']} is involved in {s['involved']} item(s) — "
                    f"{s['assigned']} Jira issue(s) assigned, {s['reported']} reported, and "
                    f"{s['authored']} Confluence doc(s) authored."
                ),
            },
            {
                "type": "note",
                "content": "Counts cover the Jira issues and Confluence docs currently indexed.",
            },
        ]
    ranked = sorted(stats, key=lambda s: s["involved"], reverse=True)
    top = ranked[0]
    tie = len([s for s in ranked if s["involved"] == top["involved"]]) > 1
    lead = (
        "It's a tie — "
        + " and ".join(
            f"{s['name']} ({s['involved']})" for s in ranked if s["involved"] == top["involved"]
        )
        + " are involved in the same number of items."
        if tie
        else f"{top['name']} is involved in the most items ({top['involved']})."
    )
    return [
        {"type": "paragraph", "content": lead},
        {
            "type": "table",
            "headers": ["Person", "Involved", "Assigned", "Reported", "Authored"],
            "rows": [
                [
                    s["name"],
                    str(s["involved"]),
                    str(s["assigned"]),
                    str(s["reported"]),
                    str(s["authored"]),
                ]
                for s in ranked
            ],
        },
        {
            "type": "note",
            "content": (
                "'Involved' spans Jira (assignee/reporter) and Confluence "
                "(authored/edited), across the content currently indexed."
            ),
        },
    ]

_NAME_WORD_RE = re.compile(r"[a-z][a-z'\-]{2,}")
_PRONOUN_RE = re.compile(r"\b(he|him|his|she|her|hers|they|them|their|theirs)\b", re.I)
_ITEM_LIST_CAP = 40  # max items listed per source per person

def _mentions_known_person(text: str, full_names: frozenset, name_words: frozenset) -> bool:
    low = (text or "").lower()
    if any(fn in low for fn in full_names if " " in fn):
        return True
    return bool(set(_NAME_WORD_RE.findall(low)) & name_words)

def _looks_like_person_question(company_id, question: str, history=None) -> bool:
    """Cheap gate before spending a planner call: a count cue, a known person named
    in the question, OR a pronoun follow-up ('his work') when a person was discussed
    earlier. Uses the cached name set — no extra LLM/DB cost."""
    if _COUNT_CUES.search(question or ""):
        return True
    full_names, name_words = retrieval_service._known_names(company_id)
    if _mentions_known_person(question, full_names, name_words):
        return True
    # Follow-up: "about his work" / "what is he working on" referring back to a person.
    if _PRONOUN_RE.search(question or ""):
        recent = " ".join(t.get("content", "") for t in (history or [])[-6:])
        if _mentions_known_person(recent, full_names, name_words):
            return True
    return False

def _person_link(source: str, page_id: str, title: str, site_url) -> str:
    """A markdown link to an item (falls back to plain title if no site URL)."""
    url = _citation_url(source, page_id, site_url)
    label = f"{page_id} · {title}" if source == "jira" else title
    return f"[{label}]({url})" if url else label

def _person_blocks(name: str, data: dict, site_url) -> tuple:
    """Structured, complete work summary for one person (Confluence docs + Jira
    issues, each with role), plus citations. Deterministic — no LLM, no omissions."""
    conf, jira = data["confluence"], data["jira"]
    blocks: list = [{"type": "heading", "level": 2, "content": f"{name} — Work & Involvement"}]
    citations: list = []
    if not conf and not jira:
        blocks.append(
            {
                "type": "paragraph",
                "content": f"I found no indexed Jira issues or Confluence docs for {name}.",
            }
        )
        return blocks, citations

    if conf:
        blocks.append(
            {
                "type": "heading",
                "level": 3,
                "content": f"Confluence docs ({data['confluence_total']})",
            }
        )
        items = []
        for c in conf:
            items.append(
                _person_link("confluence", c["page_id"], c["title"], site_url)
                + f" — {'/'.join(c['roles'])}"
            )
            citations.append({"title": c["title"], "page_id": c["page_id"], "source": "confluence"})
        blocks.append({"type": "bullet_list", "items": items})

    if jira:
        blocks.append(
            {"type": "heading", "level": 3, "content": f"Jira issues ({data['jira_total']})"}
        )
        rows = []
        for j in jira:
            rows.append(
                [
                    _person_link("jira", j["key"], j["title"], site_url),
                    j["status"] or "-",
                    j["type"] or "-",
                    "/".join(j["roles"]),
                ]
            )
            citations.append({"title": j["title"], "page_id": j["key"], "source": "jira"})
        blocks.append(
            {"type": "table", "headers": ["Issue", "Status", "Type", "Role"], "rows": rows}
        )
    return blocks, citations

def _list_answer(company_id, people: list) -> Optional[dict]:
    """Complete per-person work listing (Jira + Confluence) from exact DB lookups.
    Handles one OR many people. None if nobody has any indexed work."""
    site_url = confluence_service.get_site_url(company_id)
    all_blocks: list = []
    all_citations: list = []
    any_found = False
    for i, person in enumerate(people):
        data = retrieval_service.list_involvement(company_id, person, limit=_ITEM_LIST_CAP)
        if data["confluence"] or data["jira"]:
            any_found = True
        blocks, citations = _person_blocks(person, data, site_url)
        all_blocks.extend(blocks)
        all_citations.extend(citations)
        if i < len(people) - 1:
            all_blocks.append({"type": "divider"})
    if not any_found:
        return None  # let normal RAG answer (e.g. general knowledge / "not in docs")
    return {"blocks": all_blocks, "citations": _dedupe_citations(all_citations, site_url)[:60]}

_METRIC_LABEL = {
    "assigned": "Jira issues assigned",
    "reported": "Jira issues reported",
    "authored": "Confluence docs authored",
    "involved": "overall involvement",
}

def _leaderboard_answer(company_id, metric: str) -> Optional[dict]:
    """Open-ended ranking across everyone (top contributors / who did the most)."""
    ranked = retrieval_service.leaderboard(company_id, metric, limit=10)
    if not ranked:
        return None
    label = _METRIC_LABEL.get(metric, "overall involvement")
    top = ranked[0]
    lead = f"Top {len(ranked)} by {label}: {top['name']} leads."
    if metric == "involved":
        headers = ["#", "Person", "Total", "Assigned", "Reported", "Authored"]
        rows = [
            [
                str(i),
                s["name"],
                str(s["involved"]),
                str(s["assigned"]),
                str(s["reported"]),
                str(s["authored"]),
            ]
            for i, s in enumerate(ranked, 1)
        ]
    else:
        headers = ["#", "Person", label.title()]
        rows = [[str(i), s["name"], str(s[metric])] for i, s in enumerate(ranked, 1)]
    return {
        "blocks": [
            {"type": "paragraph", "content": lead},
            {"type": "table", "headers": headers, "rows": rows},
            {
                "type": "note",
                "content": "Ranked across the Jira issues and Confluence docs currently indexed.",
            },
        ],
        "citations": [],
    }

def _count_answer(company_id, people: list) -> Optional[dict]:
    """Exact involvement counts + comparison (retrieval can't count a top-k sample)."""
    stats = [retrieval_service.count_involvement(company_id, p) for p in people]
    if not any(s["involved"] for s in stats):
        return None
    examples: list = []
    for person in people:
        examples.extend(retrieval_service.top_issues(company_id, person, limit=2))
    site_url = confluence_service.get_site_url(company_id)
    return {"blocks": _count_blocks(stats), "citations": _dedupe_citations(examples, site_url)}

def _maybe_person_answer(
    company_id, question, provider, api_key, model, history=None
) -> Optional[dict]:
    """Answer questions about specific people's work with exact DB lookups (complete
    lists / true counts) instead of top-k RAG. Handles single AND multiple people, and
    pronoun follow-ups ('his work') via `history`. Returns a blocks+citations dict, or
    None to fall through to normal RAG."""
    if not _looks_like_person_question(company_id, question, history):
        return None
    plan = llm_service.extract_people_query(question, provider, api_key, model, history=history)
    if not plan:
        return None
    intent = plan.get("intent")
    if intent == "leaderboard":  # open-ended ranking — no specific people needed
        return _leaderboard_answer(company_id, plan.get("metric", "involved"))
    if not plan.get("people") or intent == "other":
        return None
    if intent == "count":
        return _count_answer(company_id, plan["people"])
    return _list_answer(company_id, plan["people"])

def _answer_blocks(company_id, question, provider, api_key, model, history=None) -> dict:
    """Retrieve chunks and answer as structured content blocks, with citations.
    Retrieves across all sources (Confluence pages + Jira issues)."""
    # Questions about specific people's work ("all work of X", "tell me about X and
    # Y", "who did more", or a pronoun follow-up) need complete/exact DB lookups.
    person = _maybe_person_answer(company_id, question, provider, api_key, model, history=history)
    if person is not None:
        return person

    chunks = retrieval_service.retrieve(company_id, question, k=_RETRIEVE_K, sources=_CHAT_SOURCES)
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No documents are available yet. Connect Atlassian and ingest content first.",
        )
    context = _format_context(chunks)
    result = llm_service.answer_blocks_from_context(
        question=question,
        context=context,
        provider=provider,
        api_key=api_key,
        model=model,
        history=history,
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to generate an answer.")
    # Strip any URL the model invented (only URLs present in the excerpts survive).
    blocks = _scrub_block_links(result["blocks"], context)
    # Only surface source chips when the answer actually used the docs — greetings
    # and general-knowledge answers shouldn't show (irrelevant) retrieved sources.
    citations = []
    if result.get("used_docs"):
        site_url = confluence_service.get_site_url(company_id)
        # Narrow to the sources the answer actually references (drops hybrid filler).
        citations = _filter_cited(_dedupe_citations(chunks, site_url), _blocks_to_text(blocks))
    return {"blocks": blocks, "citations": citations}

# ── chats ──────────────────────────────────────────────────────────────────────

def _chat_dict(chat: KnowledgeChat) -> dict:
    return {
        "id": chat.id,
        "title": chat.title,
        "created_at": chat.created_at.isoformat() if chat.created_at else None,
        "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
    }

def _message_dict(msg: KnowledgeMessage) -> dict:
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "blocks": json.loads(msg.blocks) if msg.blocks else None,
        "citations": json.loads(msg.citations) if msg.citations else [],
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }

def _owned_chat(session: Session, chat_id: int, company_id: int, user_id: str) -> KnowledgeChat:
    chat = session.get(KnowledgeChat, chat_id)
    if chat is None or chat.company_id != company_id or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return chat

def list_chats(company_id: int, user_id: str) -> list:
    with Session(engine) as session:
        chats = session.exec(
            select(KnowledgeChat)
            .where(KnowledgeChat.company_id == company_id)
            .where(KnowledgeChat.user_id == user_id)
            .order_by(KnowledgeChat.updated_at.desc())
        ).all()
        return [_chat_dict(c) for c in chats]

def create_chat(company_id: int, user_id: str) -> dict:
    with Session(engine) as session:
        chat = KnowledgeChat(company_id=company_id, user_id=user_id, title="New chat")
        session.add(chat)
        session.commit()
        session.refresh(chat)
        return _chat_dict(chat)

def get_chat(chat_id: int, company_id: int, user_id: str) -> dict:
    with Session(engine) as session:
        chat = _owned_chat(session, chat_id, company_id, user_id)
        messages = session.exec(
            select(KnowledgeMessage)
            .where(KnowledgeMessage.chat_id == chat_id)
            .order_by(KnowledgeMessage.id)
        ).all()
        return {"chat": _chat_dict(chat), "messages": [_message_dict(m) for m in messages]}

def delete_chat(chat_id: int, company_id: int, user_id: str) -> dict:
    with Session(engine) as session:
        chat = _owned_chat(session, chat_id, company_id, user_id)
        session.delete(chat)
        session.commit()
        return {"deleted": True}

def post_message(
    chat_id: int,
    company_id: int,
    user_id: str,
    question: str,
    provider: str,
    api_key: str,
    model: Optional[str],
) -> dict:
    """Add a user turn, answer it (with prior turns as context), persist both, and
    return the two new messages."""
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="Ask a question.")
    question = question.strip()

    with Session(engine) as session:
        _owned_chat(session, chat_id, company_id, user_id)
        prior = session.exec(
            select(KnowledgeMessage)
            .where(KnowledgeMessage.chat_id == chat_id)
            .order_by(KnowledgeMessage.id)
        ).all()
        history = [{"role": m.role, "content": m.content} for m in prior][-_HISTORY_MESSAGES:]
        is_first = len(prior) == 0

    result = _answer_blocks(company_id, question, provider, api_key, model, history=history)

    with Session(engine) as session:
        chat = _owned_chat(session, chat_id, company_id, user_id)
        user_msg = KnowledgeMessage(chat_id=chat_id, role="user", content=question)
        assistant_msg = KnowledgeMessage(
            chat_id=chat_id,
            role="assistant",
            content=_blocks_to_text(result["blocks"]),
            blocks=json.dumps(result["blocks"]),
            citations=json.dumps(result["citations"]),
        )
        session.add(user_msg)
        session.add(assistant_msg)
        if is_first:
            chat.title = question[:80]
        chat.updated_at = datetime.now(timezone.utc)
        session.add(chat)
        session.commit()
        session.refresh(user_msg)
        session.refresh(assistant_msg)
        return {
            "user": _message_dict(user_msg),
            "assistant": _message_dict(assistant_msg),
            "title": chat.title,
        }
