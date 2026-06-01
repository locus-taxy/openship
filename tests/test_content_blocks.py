import pytest
from pydantic import ValidationError
from services.llm import BlockType, ContentBlock, StructuredChapterContent

def make_block(**kwargs):
    return ContentBlock(**kwargs)

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
