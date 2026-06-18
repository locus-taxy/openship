"""Tests for services/content_validator.py — heuristics and LLM judge."""

import pytest
from unittest.mock import MagicMock
from pydantic import ValidationError

from services.content_validator import (
    HeuristicResult,
    ContentValidationResult,
    validate_content_heuristics,
    validate_content_with_llm,
    _extract_all_text,
    _blocks_to_text,
    MIN_WORDS,
    LLM_JUDGE_PASS_SCORE,
    _PLACEHOLDER_RE,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_block(
    btype, content=None, items=None, headers=None, rows=None, language=None, level=None
):
    b = MagicMock()
    b.type = btype
    b.content = content
    b.items = items
    b.headers = headers
    b.rows = rows
    b.language = language
    b.level = level
    return b

def _good_blocks(word_count=100, with_code=True):
    """Return a list of blocks that pass all heuristic checks."""
    words = " ".join(["arrays"] * word_count)
    blocks = [_make_block("heading", content="Arrays and Strings", level=1)]
    blocks.append(_make_block("paragraph", content=words))
    if with_code:
        blocks.append(_make_block("code", content="int arr[] = {1, 2, 3};", language="cpp"))
    return blocks

# ── HeuristicResult ───────────────────────────────────────────────────────────

class TestHeuristicResult:
    def test_passed_true(self):
        r = HeuristicResult(passed=True, reason="")
        assert r.passed is True

    def test_passed_false_with_reason(self):
        r = HeuristicResult(passed=False, reason="too short")
        assert r.passed is False
        assert r.reason == "too short"

# ── ContentValidationResult ───────────────────────────────────────────────────

class TestContentValidationResult:
    def test_score_clamped_above_10(self):
        r = ContentValidationResult(valid=True, score=15, issues=[])
        assert r.score == 10

    def test_score_clamped_below_1(self):
        r = ContentValidationResult(valid=False, score=0, issues=["bad"])
        assert r.score == 1

    def test_score_in_range_unchanged(self):
        r = ContentValidationResult(valid=True, score=8, issues=[])
        assert r.score == 8

    def test_valid_false_with_issues(self):
        r = ContentValidationResult(valid=False, score=4, issues=["off-topic", "wrong code"])
        assert r.valid is False
        assert len(r.issues) == 2

# ── _extract_all_text ─────────────────────────────────────────────────────────

class TestExtractAllText:
    def test_extracts_content(self):
        b = _make_block("paragraph", content="Hello World")
        assert "hello world" in _extract_all_text([b])

    def test_extracts_items(self):
        b = _make_block("bullet_list", items=["First", "Second"])
        text = _extract_all_text([b])
        assert "first" in text and "second" in text

    def test_extracts_headers(self):
        b = _make_block("table", headers=["Name", "Value"], rows=[["x", "1"]])
        text = _extract_all_text([b])
        assert "name" in text and "value" in text

    def test_extracts_rows(self):
        b = _make_block("table", headers=["Col"], rows=[["cell_data"]])
        assert "cell_data" in _extract_all_text([b])

    def test_empty_blocks(self):
        b = _make_block("divider")
        assert _extract_all_text([b]) == ""

# ── _blocks_to_text ───────────────────────────────────────────────────────────

class TestBlocksToText:
    def test_heading(self):
        b = _make_block("heading", content="Title", level=1)
        assert "[HEADING 1] Title" in _blocks_to_text([b])

    def test_paragraph(self):
        b = _make_block("paragraph", content="Some text")
        assert "[PARAGRAPH] Some text" in _blocks_to_text([b])

    def test_code_block(self):
        b = _make_block("code", content="int x = 0;", language="cpp")
        result = _blocks_to_text([b])
        assert "[CODE cpp]" in result
        assert "int x = 0;" in result

    def test_list_block(self):
        b = _make_block("bullet_list", items=["A", "B"])
        result = _blocks_to_text([b])
        assert "[LIST]" in result
        assert "- A" in result

    def test_table_block(self):
        b = _make_block("table", headers=["Col1", "Col2"])
        result = _blocks_to_text([b])
        assert "[TABLE]" in result
        assert "Col1" in result

    def test_diagram_block(self):
        b = _make_block("diagram", content="graph TD\n  A --> B")
        result = _blocks_to_text([b])
        assert "[DIAGRAM]" in result

    def test_note_and_quote(self):
        note = _make_block("note", content="Important note")
        quote = _make_block("quote", content="Famous quote")
        result = _blocks_to_text([note, quote])
        assert "[NOTE]" in result
        assert "[QUOTE]" in result

# ── validate_content_heuristics ───────────────────────────────────────────────

class TestValidateContentHeuristics:
    def test_passes_good_content(self):
        blocks = _good_blocks()
        result = validate_content_heuristics(blocks, "Learn about arrays in C++")
        assert result.passed is True
        assert result.reason == ""

    def test_fails_when_too_short(self):
        blocks = [_make_block("paragraph", content="short text")]
        result = validate_content_heuristics(blocks, "Arrays in C++")
        assert result.passed is False
        assert "too short" in result.reason
        assert str(MIN_WORDS) in result.reason

    def test_fails_on_placeholder_todo_annotation(self):
        # "todo:" (with colon) is the developer annotation pattern — always a placeholder.
        words = " ".join(["arrays"] * 100)
        for text in ["TODO: add more content here", "todo: fill in later", "Todo:placeholder"]:
            blocks = [
                _make_block("paragraph", content=words),
                _make_block("paragraph", content=text),
            ]
            result = validate_content_heuristics(blocks, "Arrays")
            assert result.passed is False, f"Expected failure for: {text!r}"
            assert "todo" in result.reason.lower()

    def test_todo_without_colon_does_not_trigger_placeholder_check(self):
        # "todo list", "TodoMVC", "Build a Todo App" are legitimate in any course.
        words = " ".join(["productivity"] * 80)
        for text in [
            "A todo list helps you stay organised and focused",
            "TodoMVC is a benchmark project for JavaScript frameworks",
            "Build a simple Todo App as your first React project",
        ]:
            blocks = [
                _make_block("paragraph", content=words),
                _make_block("paragraph", content=text),
            ]
            result = validate_content_heuristics(blocks, "productivity")
            assert result.passed is True, f"False positive for: {text!r}"

    def test_fails_on_placeholder_lorem_ipsum(self):
        words = " ".join(["arrays"] * 100)
        blocks = [
            _make_block("paragraph", content=words),
            _make_block("paragraph", content="lorem ipsum dolor sit amet"),
        ]
        result = validate_content_heuristics(blocks, "Arrays")
        assert result.passed is False
        assert "lorem ipsum" in result.reason

    def test_fill_in_alone_does_not_fail(self):
        # "fill in" is common in natural prose — only "fill in the blank" is banned
        words = " ".join(["swift"] * 100)
        blocks = [
            _make_block("paragraph", content=words),
            _make_block("paragraph", content="This method fills in the cell data automatically"),
        ]
        result = validate_content_heuristics(blocks, "swift")
        assert result.passed is True

    def test_fill_in_the_blank_fails(self):
        words = " ".join(["arrays"] * 100)
        blocks = [
            _make_block("paragraph", content=words),
            _make_block("paragraph", content="fill in the blank with the correct answer"),
        ]
        result = validate_content_heuristics(blocks, "arrays")
        assert result.passed is False

    def test_coming_soon_does_not_fail(self):
        # "coming soon" appears in legit tech docs ("new API coming soon in Swift 6")
        words = " ".join(["swift"] * 100)
        blocks = [
            _make_block("paragraph", content=words),
            _make_block("paragraph", content="This feature is coming soon in Swift 6"),
        ]
        result = validate_content_heuristics(blocks, "swift")
        assert result.passed is True

    def test_code_block_content_not_checked_for_syntax(self):
        # Code blocks are never inspected for syntax — any content is fine.
        # The LLM judge (layer 2) is responsible for code quality evaluation.
        words = " ".join(["arrays"] * 100)
        for content in [
            "just plain prose in a code block",
            "docker run hello-world",
            "FROM ubuntu:22.04",
            "kubectl get pods",
            "$ ls -la",
            "apiVersion: apps/v1",
            "mix ingredients well",  # non-tech course
        ]:
            blocks = [
                _make_block("paragraph", content=words),
                _make_block("code", content=content),
            ]
            result = validate_content_heuristics(blocks, "arrays")
            assert result.passed is True, f"Failed unexpectedly for code content: {content!r}"

    def test_fails_when_no_topic_keyword_in_content(self):
        # Content has enough words but none match the task keywords
        words = " ".join(["banana"] * 100)
        blocks = [_make_block("paragraph", content=words)]
        result = validate_content_heuristics(blocks, "Learn about arrays and pointers")
        assert result.passed is False
        assert "keyword" in result.reason.lower()

    def test_passes_when_short_task_words_ignored(self):
        # Words <= 3 chars are ignored from task keywords
        words = " ".join(["text"] * 100)
        blocks = [_make_block("paragraph", content=words)]
        # "in" and "C++" are short — no valid keyword to check against
        result = validate_content_heuristics(blocks, "in C++")
        assert result.passed is True

    def test_fails_on_duplicate_prose_content(self):
        same = "This is the exact same paragraph content repeated here verbatim."
        words = " ".join(["arrays"] * 100)
        blocks = [
            _make_block("paragraph", content=words),
            _make_block("paragraph", content=same),
            _make_block("paragraph", content=same),
        ]
        result = validate_content_heuristics(blocks, "arrays")
        assert result.passed is False
        assert "duplicate" in result.reason.lower()

    def test_repeated_short_heading_does_not_fail(self):
        # "Introduction", "Example", "Summary" can appear as headings in multiple
        # sections — this must not be flagged as duplicate content.
        words = " ".join(["arrays"] * 100)
        blocks = [
            _make_block("paragraph", content=words),
            _make_block("heading", content="Introduction", level=2),
            _make_block("heading", content="Introduction", level=2),
            _make_block("heading", content="Example", level=3),
            _make_block("heading", content="Example", level=3),
        ]
        result = validate_content_heuristics(blocks, "arrays")
        assert result.passed is True

    def test_repeated_short_prose_does_not_fail(self):
        # Short prose blocks (≤ 30 chars) like "Note:" or "See above." can repeat
        # without being flagged — only substantive content is checked.
        words = " ".join(["arrays"] * 100)
        blocks = [
            _make_block("paragraph", content=words),
            _make_block("note", content="See previous section."),
            _make_block("note", content="See previous section."),
        ]
        result = validate_content_heuristics(blocks, "arrays")
        assert result.passed is True

    def test_code_block_with_empty_content_not_flagged(self):
        # Empty code blocks are filtered upstream; if one slips through, skip the check
        words = " ".join(["arrays"] * 100)
        blocks = [
            _make_block("paragraph", content=words),
            _make_block("code", content=""),
        ]
        result = validate_content_heuristics(blocks, "arrays")
        assert result.passed is True

    def test_placeholder_word_alone_does_not_fail(self):
        # "placeholder" is a real Swift/SwiftUI technical term — not a banned string
        words = " ".join(["swift"] * 100)
        blocks = [
            _make_block("paragraph", content=words),
            _make_block("paragraph", content="Use the placeholder modifier on TextField"),
        ]
        result = validate_content_heuristics(blocks, "swift introduction")
        assert result.passed is True

class TestTopicKeywordParam:
    """Check 3 uses topic when provided instead of task_description."""

    def _recursion_blocks(self):
        words = " ".join(["recursion"] * 50 + ["function", "call", "stack", "base", "case"] * 10)
        return [_make_block("paragraph", content=words)]

    def test_action_task_fails_without_topic(self):
        # Task description has instruction words + resource names that never appear in content.
        # Without a topic, check 3 extracts "geeksforgeeks", "oracle", etc. → fails.
        blocks = self._recursion_blocks()
        result = validate_content_heuristics(
            blocks,
            "Read about recursion from a reliable source (e.g., GeeksforGeeks or Oracle docs). "
            "Write a 200-word summary explaining recursion in your own words.",
        )
        assert result.passed is False
        assert "keyword" in result.reason.lower()

    def test_action_task_passes_with_topic(self):
        # Same content + same task description, but topic="What is Recursion?" is supplied.
        # Check 3 now extracts only "recursion" from the topic → matched in content → passes.
        blocks = self._recursion_blocks()
        result = validate_content_heuristics(
            blocks,
            "Read about recursion from a reliable source (e.g., GeeksforGeeks or Oracle docs). "
            "Write a 200-word summary explaining recursion in your own words.",
            topic="What is Recursion?",
        )
        assert result.passed is True

    def test_topic_keywords_used_not_task_keywords(self):
        # Content contains topic words ("call", "stack") but NOT task description words.
        # Verifies that only the topic is checked when topic is provided.
        words = " ".join(["call"] * 50 + ["stack"] * 50)
        blocks = [_make_block("paragraph", content=words)]
        result = validate_content_heuristics(
            blocks,
            "Implement a linked list traversal algorithm with time complexity analysis",
            topic="Understanding the Call Stack",
        )
        assert result.passed is True

    def test_topic_punctuation_stripped(self):
        # "What is Recursion?" — the "?" must be stripped so the keyword is "recursion"
        # not "recursion?" (which would never match via word-boundary search).
        words = " ".join(["recursion"] * 100)
        blocks = [_make_block("paragraph", content=words)]
        result = validate_content_heuristics(blocks, "irrelevant task", topic="What is Recursion?")
        assert result.passed is True

    def test_topic_none_falls_back_to_task_description(self):
        # When topic is omitted the old behaviour is preserved — task_description is used.
        # "arrays in C++" → only keyword is "arrays" (≤3-char tokens filtered); content matches.
        words = " ".join(["arrays"] * 100)
        blocks = [_make_block("paragraph", content=words)]
        result = validate_content_heuristics(blocks, "arrays in C++")
        assert result.passed is True

    def test_topic_with_no_usable_keywords_falls_back_to_task_description(self):
        # topic="The" → 3 chars → filtered → task_keywords empty → fallback to task_description.
        # task_description "Learn about arrays" → "learn"/"about" are stopwords → only "arrays"
        # extracted → required=1 → content matches → passes.
        words = " ".join(["arrays"] * 100)
        blocks = [_make_block("paragraph", content=words)]
        result = validate_content_heuristics(blocks, "Learn about arrays", topic="The")
        assert result.passed is True

# ── validate_content_with_llm ─────────────────────────────────────────────────

class TestValidateContentWithLlm:
    def _make_client(self, valid, score, issues):
        mock_result = ContentValidationResult(valid=valid, score=score, issues=issues)
        client = MagicMock()
        client.chat.completions.create.return_value = mock_result
        return client

    def test_returns_valid_when_score_high(self):
        client = self._make_client(valid=True, score=9, issues=[])
        blocks = _good_blocks()
        result = validate_content_with_llm(blocks, "Arrays in C++", "C++", client, "gemini-flash")
        assert result.valid is True
        assert result.score == 9

    def test_returns_invalid_when_score_low(self):
        client = self._make_client(valid=True, score=4, issues=["off-topic"])
        blocks = _good_blocks()
        result = validate_content_with_llm(blocks, "Arrays in C++", "C++", client, "gemini-flash")
        # valid is overridden to False because score < LLM_JUDGE_PASS_SCORE
        assert result.valid is False

    def test_valid_overridden_by_score_threshold(self):
        # LLM says valid=true but score is 6 (below threshold 7)
        client = self._make_client(valid=True, score=6, issues=[])
        blocks = _good_blocks()
        result = validate_content_with_llm(blocks, "task", "Python", client, "model")
        assert result.valid is False

    def test_passes_correct_messages_to_client(self):
        client = self._make_client(valid=True, score=8, issues=[])
        blocks = _good_blocks()
        validate_content_with_llm(blocks, "Learn arrays", "C++", client, "my-model")
        call_kwargs = client.chat.completions.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert any("Learn arrays" in m["content"] for m in messages)
        assert any("C++" in m["content"] for m in messages)

    def test_passes_model_to_client(self):
        client = self._make_client(valid=True, score=8, issues=[])
        blocks = _good_blocks()
        validate_content_with_llm(blocks, "task", "Python", client, "specific-model")
        call_kwargs = client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "specific-model"

    def test_propagates_client_exception(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("API down")
        blocks = _good_blocks()
        with pytest.raises(RuntimeError, match="API down"):
            validate_content_with_llm(blocks, "task", "Python", client, "model")
