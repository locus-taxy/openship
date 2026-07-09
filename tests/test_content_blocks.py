import pytest
from pydantic import ValidationError
from services.llm import BlockType, ContentBlock, StructuredChapterContent

def make_block(**kwargs):
    return ContentBlock(**kwargs)

class TestContentBlockTypeCoercion:
    """Out-of-vocabulary block types from the LLM must be coerced, not crash the
    whole response. Valid types must pass through untouched."""

    def test_list_item_becomes_bullet_with_content_moved_to_items(self):
        b = ContentBlock.model_validate({"type": "list_item", "content": "Do the thing"})
        assert b.type == BlockType.BULLET_LIST
        assert b.items == ["Do the thing"]
        assert b.content is None

    def test_unknown_type_falls_back_to_paragraph(self):
        b = ContentBlock.model_validate({"type": "weird_thing", "content": "hello"})
        assert b.type == BlockType.PARAGRAPH
        assert b.content == "hello"

    def test_common_aliases_map_to_valid_types(self):
        assert (
            ContentBlock.model_validate({"type": "ordered_list", "items": ["a"]}).type
            == BlockType.NUMBERED_LIST
        )
        assert (
            ContentBlock.model_validate({"type": "text", "content": "x"}).type
            == BlockType.PARAGRAPH
        )
        assert (
            ContentBlock.model_validate({"type": "header", "content": "x"}).type
            == BlockType.HEADING
        )
        assert (
            ContentBlock.model_validate({"type": "mermaid", "content": "graph TD"}).type
            == BlockType.DIAGRAM
        )

    def test_valid_types_are_untouched(self):
        # A well-formed bullet_list keeps its items and gains no content shuffling.
        b = ContentBlock.model_validate({"type": "bullet_list", "items": ["a", "b"]})
        assert b.type == BlockType.BULLET_LIST and b.items == ["a", "b"]
        # A valid paragraph is unchanged.
        p = ContentBlock.model_validate({"type": "paragraph", "content": "hi"})
        assert p.type == BlockType.PARAGRAPH and p.content == "hi"

class TestContentBlockHeading:
    def test_valid_heading(self):
        b = make_block(type="heading", content="My Title", level=1)
        assert b.type == BlockType.HEADING
        assert b.content == "My Title"
        assert b.level == 1

    def test_heading_defaults_level_to_2(self):
        b = make_block(type="heading", content="Title")
        assert b.level == 2

    def test_heading_empty_content_becomes_empty_string(self):
        b = make_block(type="heading", content="")
        assert b.content == ""

class TestContentBlockParagraph:
    def test_valid_paragraph(self):
        b = make_block(type="paragraph", content="Some text here.")
        assert b.type == BlockType.PARAGRAPH
        assert b.content == "Some text here."

class TestContentBlockCode:
    def test_valid_code_block(self):
        b = make_block(type="code", content="print('hello')", language="python")
        assert b.type == BlockType.CODE
        assert b.language == "python"

    def test_code_defaults_language_to_empty_string(self):
        b = make_block(type="code", content="some code")
        assert b.language == ""

class TestContentBlockBulletList:
    def test_valid_bullet_list(self):
        b = make_block(type="bullet_list", items=["Item 1", "Item 2"])
        assert b.type == BlockType.BULLET_LIST
        assert b.items == ["Item 1", "Item 2"]

    def test_empty_items_becomes_empty_list(self):
        b = make_block(type="bullet_list", items=[])
        assert b.items == []

class TestContentBlockNumberedList:
    def test_valid_numbered_list(self):
        b = make_block(type="numbered_list", items=["Step 1", "Step 2"])
        assert b.items == ["Step 1", "Step 2"]

class TestContentBlockTable:
    def test_valid_table(self):
        b = make_block(
            type="table",
            headers=["Name", "Age"],
            rows=[["Alice", "30"], ["Bob", "25"]],
        )
        assert b.headers == ["Name", "Age"]
        assert len(b.rows) == 2

    def test_table_rows_truncated_to_header_length(self):
        b = make_block(
            type="table",
            headers=["A", "B"],
            rows=[["x", "y", "extra"]],
        )
        assert len(b.rows[0]) == 2

    def test_table_short_rows_padded_with_empty_strings(self):
        b = make_block(
            type="table",
            headers=["A", "B", "C"],
            rows=[["x"]],
        )
        assert b.rows[0] == ["x", "", ""]

class TestContentBlockDiagram:
    def test_valid_diagram(self):
        b = make_block(type="diagram", content="graph TD\n  A-->B", format="mermaid")
        assert b.type == BlockType.DIAGRAM
        assert b.format == "mermaid"

    def test_diagram_always_sets_mermaid_format(self):
        b = make_block(type="diagram", content="graph TD\n  A-->B", format="plantuml")
        assert b.format == "mermaid"

    def test_diagram_without_format_defaults_to_mermaid(self):
        b = make_block(type="diagram", content="graph TD\n  A-->B")
        assert b.format == "mermaid"

    def test_diagram_empty_content_stored(self):
        b = make_block(type="diagram", content="")
        assert b.content == ""

class TestContentBlockNote:
    def test_valid_note(self):
        b = make_block(type="note", content="Important tip here.")
        assert b.type == BlockType.NOTE

class TestContentBlockQuote:
    def test_valid_quote(self):
        b = make_block(
            type="quote",
            content="Clean code always looks like it was written by someone who cares.",
        )
        assert b.type == BlockType.QUOTE

class TestContentBlockDivider:
    def test_valid_divider(self):
        b = make_block(type="divider")
        assert b.type == BlockType.DIVIDER

class TestStructuredChapterContent:
    def test_valid_blocks_kept(self):
        chapter = StructuredChapterContent(
            blocks=[
                {"type": "heading", "content": "Title", "level": 1},
                {"type": "paragraph", "content": "Some explanation."},
            ]
        )
        assert len(chapter.blocks) == 2

    def test_empty_heading_content_filtered_out(self):
        chapter = StructuredChapterContent(
            blocks=[
                {"type": "heading", "content": "", "level": 1},
                {"type": "paragraph", "content": "Keep this."},
            ]
        )
        assert all(b.type != BlockType.HEADING for b in chapter.blocks)

    def test_empty_paragraph_content_filtered_out(self):
        chapter = StructuredChapterContent(
            blocks=[
                {"type": "paragraph", "content": ""},
                {"type": "paragraph", "content": "Keep this."},
            ]
        )
        assert len(chapter.blocks) == 1

    def test_divider_always_kept(self):
        chapter = StructuredChapterContent(blocks=[{"type": "divider"}])
        assert len(chapter.blocks) == 1

    def test_table_with_no_headers_filtered(self):
        chapter = StructuredChapterContent(
            blocks=[
                {"type": "table", "headers": [], "rows": []},
                {"type": "paragraph", "content": "Keep this."},
            ]
        )
        assert all(b.type != BlockType.TABLE for b in chapter.blocks)

    def test_diagram_with_empty_content_filtered(self):
        chapter = StructuredChapterContent(
            blocks=[
                {"type": "diagram", "content": "", "format": "mermaid"},
                {"type": "paragraph", "content": "Keep this."},
            ]
        )
        assert all(b.type != BlockType.DIAGRAM for b in chapter.blocks)

    def test_bullet_list_with_no_items_filtered(self):
        chapter = StructuredChapterContent(
            blocks=[
                {"type": "bullet_list", "items": []},
                {"type": "paragraph", "content": "Keep this."},
            ]
        )
        assert all(b.type != BlockType.BULLET_LIST for b in chapter.blocks)
