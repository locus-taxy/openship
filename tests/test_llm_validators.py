"""Tests for uncovered branches in services/llm.py validators and _build_client."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from services.llm import (
    ContentBlock,
    BlockType,
    QuizOption,
    GeneratedQuestion,
    StructuredChapterContent,
    _build_client,
    generate_chapter_html,
    generate_weekly_quiz,
)

class TestContentBlockLevelValidator:
    def test_invalid_level_raises(self):
        with pytest.raises(Exception):
            ContentBlock(type=BlockType.HEADING, content="Title", level=4)

    def test_note_block_with_empty_content(self):
        b = ContentBlock(type=BlockType.NOTE, content="")
        assert b.content == ""

    def test_quote_block_with_empty_content(self):
        b = ContentBlock(type=BlockType.QUOTE, content="")
        assert b.content == ""

    def test_bullet_list_with_no_items_defaults(self):
        b = ContentBlock(type=BlockType.BULLET_LIST, items=None)
        assert b.items == []

    def test_numbered_list_with_no_items_defaults(self):
        b = ContentBlock(type=BlockType.NUMBERED_LIST, items=None)
        assert b.items == []

class TestQuizOptionInvalidLabel:
    def test_invalid_correct_option_raises(self):
        opts = [
            QuizOption(label="A", text="a"),
            QuizOption(label="B", text="b"),
            QuizOption(label="C", text="c"),
            QuizOption(label="D", text="d"),
        ]
        with pytest.raises(Exception):
            GeneratedQuestion(
                question="Q?",
                options=opts,
                correct_option="E",  # invalid
                explanation="exp",
            )

    def test_duplicate_labels_raises(self):
        opts = [
            QuizOption(label="A", text="a"),
            QuizOption(label="A", text="a2"),
            QuizOption(label="C", text="c"),
            QuizOption(label="D", text="d"),
        ]
        with pytest.raises(Exception):
            GeneratedQuestion(
                question="Q?",
                options=opts,
                correct_option="A",
                explanation="exp",
            )

class TestBuildClientGeminiPatching:
    """Verify the _patched_generate closure logic is exercised."""

    def test_gemini_client_patches_generate_content(self):
        mock_google_client = MagicMock()
        real_generate = MagicMock(return_value="result")
        mock_google_client.models.generate_content = real_generate

        with (
            patch("services.llm.genai") as mock_genai,
            patch("services.llm.instructor") as mock_instructor,
        ):
            mock_genai.Client.return_value = mock_google_client
            mock_instructor.from_genai.return_value = MagicMock()
            mock_instructor.Mode.GENAI_STRUCTURED_OUTPUTS = "genai_structured"

            _build_client("gemini", "fake-api-key")

            # After _build_client, models.generate_content is now the patched version
            patched_fn = mock_google_client.models.generate_content
            assert patched_fn is not real_generate

    def test_patched_generate_calls_real_generate_without_config(self):
        mock_google_client = MagicMock()
        real_generate = MagicMock(return_value="ok")
        mock_google_client.models.generate_content = real_generate

        with (
            patch("services.llm.genai") as mock_genai,
            patch("services.llm.instructor") as mock_instructor,
        ):
            mock_genai.Client.return_value = mock_google_client
            mock_instructor.from_genai.return_value = MagicMock()
            mock_instructor.Mode.GENAI_STRUCTURED_OUTPUTS = "genai_structured"

            _build_client("gemini", "fake-api-key")
            patched = mock_google_client.models.generate_content

            # Call with no config — should delegate to real_generate
            patched(model="gemini-flash", contents="hello")
            real_generate.assert_called_once()

    def test_patched_generate_strips_max_tokens_kwarg(self):
        mock_google_client = MagicMock()
        captured_kwargs = {}

        def real_generate(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return "ok"

        mock_google_client.models.generate_content = real_generate

        with (
            patch("services.llm.genai") as mock_genai,
            patch("services.llm.instructor") as mock_instructor,
        ):
            mock_genai.Client.return_value = mock_google_client
            mock_instructor.from_genai.return_value = MagicMock()
            mock_instructor.Mode.GENAI_STRUCTURED_OUTPUTS = "genai_structured"

            _build_client("gemini", "fake-api-key")
            patched = mock_google_client.models.generate_content

            patched(model="gemini-flash", max_tokens=1000, config=None)
            assert "max_tokens" not in captured_kwargs

    def test_patched_generate_injects_max_output_tokens_via_config(self):
        mock_google_client = MagicMock()
        captured_kwargs = {}

        def real_generate(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return "ok"

        mock_google_client.models.generate_content = real_generate
        mock_config = MagicMock()
        mock_config.max_output_tokens = None
        mock_config.response_schema = None
        updated_config = MagicMock()
        mock_config.model_copy.return_value = updated_config

        with (
            patch("services.llm.genai") as mock_genai,
            patch("services.llm.instructor") as mock_instructor,
        ):
            mock_genai.Client.return_value = mock_google_client
            from unittest.mock import MagicMock as MM

            thinking_config = MM()
            mock_genai.types = MM()
            # Patch google.genai types inside the closure
            with patch("google.genai.types.ThinkingConfig", return_value=thinking_config):
                mock_instructor.from_genai.return_value = MagicMock()
                mock_instructor.Mode.GENAI_STRUCTURED_OUTPUTS = "genai_structured"
                _build_client("gemini", "fake-api-key")
                patched = mock_google_client.models.generate_content
                patched(model="gemini-flash", config=mock_config)
            # model_copy should have been called to update config
            mock_config.model_copy.assert_called_once()

class TestGenerateQuizQuotaError:
    def test_raises_429_on_quota_error_from_generate(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("rate_limit exceeded")
        with patch("services.llm._build_client", return_value=mock_client):
            with pytest.raises(HTTPException) as ei:
                generate_weekly_quiz("Python", 1, ["Vars"], 5, "gemini", "key", "gemini-flash")
        assert ei.value.status_code == 429

class TestGenerateChapterHtmlQuotaError:
    def test_raises_429_on_quota_error(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("429 quota")
        with patch("services.llm._build_client", return_value=mock_client):
            with pytest.raises(HTTPException) as ei:
                generate_chapter_html("desc", "title", "Python", "gemini", "key", "gemini-flash")
        assert ei.value.status_code == 429
