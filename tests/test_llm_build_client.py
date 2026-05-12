from unittest.mock import MagicMock, patch, call
import pytest
from fastapi import HTTPException
from services.llm import (
    _build_client,
    fetch_provider_models,
    ContentBlock,
    BlockType,
    QuizOption,
    GeneratedQuestion,
    StructuredChapterContent,
)

class TestBuildClientProviders:
    def test_build_openai_client(self):
        mock_openai = MagicMock()
        with (
            patch("services.llm.OpenAI", return_value=mock_openai),
            patch("services.llm.instructor") as mock_instructor,
        ):
            mock_instructor.from_openai.return_value = MagicMock()
            _build_client("openai", "key")
            mock_instructor.from_openai.assert_called_once_with(mock_openai)

    def test_build_anthropic_client(self):
        mock_anthropic = MagicMock()
        with (
            patch("services.llm.Anthropic", return_value=mock_anthropic),
            patch("services.llm.instructor") as mock_instructor,
        ):
            mock_instructor.from_anthropic.return_value = MagicMock()
            _build_client("anthropic", "key")
            mock_instructor.from_anthropic.assert_called_once_with(mock_anthropic)

    def test_build_mistral_client(self):
        mock_mistral = MagicMock()
        with (
            patch("services.llm.Mistral", return_value=mock_mistral),
            patch("services.llm.instructor") as mock_instructor,
        ):
            mock_instructor.from_mistral.return_value = MagicMock()
            _build_client("mistral", "key")
            mock_instructor.from_mistral.assert_called_once_with(mock_mistral)

    def test_raises_400_for_unknown_provider(self):
        with pytest.raises(HTTPException) as ei:
            _build_client("unknown-provider", "key")
        assert ei.value.status_code == 400

class TestFetchProviderModelsMistral:
    def test_mistral_returns_filtered_models(self):
        mock_m1 = MagicMock()
        mock_m1.id = "mistral-large-latest"
        mock_m2 = MagicMock()
        mock_m2.id = "mistral-embed"  # has "embed" → should be skipped
        mock_result = MagicMock()
        mock_result.data = [mock_m1, mock_m2]
        mock_client = MagicMock()
        mock_client.models.list.return_value = mock_result
        with patch("services.llm.Mistral", return_value=mock_client):
            result = fetch_provider_models("mistral", "test-key-" + "z" * 20)
        assert "mistral-large-latest" in result
        assert "mistral-embed" not in result

    def test_gemini_skips_model_without_generate_content_action(self):
        mock_model = MagicMock()
        mock_model.name = "models/gemini-embedding"
        mock_model.supported_actions = ["embedContent"]  # no generateContent
        mock_client = MagicMock()
        mock_client.models.list.return_value = [mock_model]
        with patch("services.llm.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = fetch_provider_models("gemini", "test-key-skip-" + "x" * 20)
        assert "gemini-embedding" not in result

class TestContentBlockValidatorBranches:
    def test_heading_with_explicit_content_and_level(self):
        b = ContentBlock(type=BlockType.HEADING, content="Title", level=3)
        assert b.level == 3
        assert b.content == "Title"

    def test_heading_no_content_defaults_empty_string(self):
        b = ContentBlock(type=BlockType.HEADING, content="", level=None)
        assert b.content == ""
        assert b.level == 2

    def test_table_with_headers_pads_short_rows(self):
        b = ContentBlock(
            type=BlockType.TABLE,
            headers=["A", "B", "C"],
            rows=[["x", "y"]],  # only 2 cols, needs padding to 3
        )
        assert b.rows[0] == ["x", "y", ""]

    def test_table_with_no_headers_defaults_empty(self):
        b = ContentBlock(type=BlockType.TABLE, headers=None, rows=None)
        assert b.headers == []
        assert b.rows == []

    def test_diagram_sets_format_to_mermaid(self):
        b = ContentBlock(type=BlockType.DIAGRAM, content="graph LR; A-->B")
        assert b.format == "mermaid"

    def test_diagram_with_no_content(self):
        b = ContentBlock(type=BlockType.DIAGRAM, content="")
        assert b.format == "mermaid"
        assert b.content == ""

class TestQuizOptionValidation:
    def test_raises_on_invalid_label(self):
        with pytest.raises(Exception):
            QuizOption(label="E", text="Invalid option")

    def test_raises_on_empty_text(self):
        with pytest.raises(Exception):
            QuizOption(label="A", text="   ")

    def test_normalizes_label_to_uppercase(self):
        opt = QuizOption(label="a", text="Option A")
        assert opt.label == "A"

class TestGeneratedQuestionValidation:
    def _make_opts(self):
        return [
            QuizOption(label="A", text="Option A"),
            QuizOption(label="B", text="Option B"),
            QuizOption(label="C", text="Option C"),
            QuizOption(label="D", text="Option D"),
        ]

    def test_raises_when_fewer_than_4_options(self):
        opts = self._make_opts()[:3]
        with pytest.raises(Exception):
            GeneratedQuestion(question="Q?", options=opts, correct_option="A", explanation="exp")

    def test_raises_when_duplicate_labels(self):
        opts = [
            QuizOption(label="A", text="Option A"),
            QuizOption(label="A", text="Option A2"),
            QuizOption(label="C", text="Option C"),
            QuizOption(label="D", text="Option D"),
        ]
        with pytest.raises(Exception):
            GeneratedQuestion(question="Q?", options=opts, correct_option="A", explanation="exp")

class TestStructuredChapterContentValidation:
    def test_raises_when_all_blocks_empty(self):
        with pytest.raises(Exception):
            StructuredChapterContent(
                blocks=[
                    ContentBlock(type=BlockType.PARAGRAPH, content=""),
                ]
            )

    def test_filters_out_empty_blocks_keeps_useful_ones(self):
        blocks = [
            ContentBlock(type=BlockType.PARAGRAPH, content=""),
            ContentBlock(type=BlockType.PARAGRAPH, content="Real content here"),
        ]
        scc = StructuredChapterContent(blocks=blocks)
        assert len(scc.blocks) == 1
        assert scc.blocks[0].content == "Real content here"

class TestUserServiceModelUpdate:
    def test_updates_model_for_existing_key_record(self):
        from unittest.mock import MagicMock, patch
        from services.user import update_llm_settings
        from models.user import User
        from models.user_api_key import UserApiKey

        user = User(
            id=1,
            email="test@example.com",
            name="Test",
            is_active=True,
            hashed_password="$2b$hash",
            llm_provider_id=1,
        )
        existing_record = MagicMock(spec=UserApiKey)
        existing_record.api_key = None
        existing_record.llm_model = None

        session = MagicMock()
        session.get.return_value = user

        exec_mock = MagicMock()
        exec_mock.first.return_value = existing_record
        session.exec.return_value = exec_mock

        patcher = patch("services.user.Session")
        mock_cls = patcher.start()
        mock_cls.return_value.__enter__ = MagicMock(return_value=session)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        try:
            update_llm_settings(1, 2, None, model="gemini-2.5-flash")
            assert user.llm_provider_id == 2
            assert existing_record.llm_model == "gemini-2.5-flash"
            session.commit.assert_called_once()
        finally:
            patcher.stop()

class TestNewsletterHelpers:
    def test_recipient_hint_returns_invalid_for_bad_email(self):
        from services.newsletter import _recipient_hint

        assert _recipient_hint("not-an-email") == "[invalid]"

    def test_recipient_hint_returns_domain_part(self):
        from services.newsletter import _recipient_hint

        assert _recipient_hint("user@example.com") == "@example.com"
