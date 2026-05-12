from services.daily_task import _clean_mermaid, _sanitize_block

class TestCleanMermaid:
    def test_unescapes_html_entities(self):
        content = "graph TD\n  A[&lt;Book&gt;] --> B[End]"
        result = _clean_mermaid(content)
        assert "<Book>" in result
        assert "&lt;" not in result

    def test_replaces_slash_with_space_in_sequence_label(self):
        content = "sequenceDiagram\n  A->>B: success/failure"
        result = _clean_mermaid(content)
        assert "success failure" in result
        assert "success/failure" not in result

    def test_replaces_pipe_with_space_in_sequence_label(self):
        content = "sequenceDiagram\n  A->>B: read|write"
        result = _clean_mermaid(content)
        assert "/" not in result.split("A->>B:")[-1]

    def test_strips_parentheses_from_sequence_label(self):
        content = "sequenceDiagram\n  A->>B: call(func)"
        result = _clean_mermaid(content)
        label = result.split("A->>B:")[-1]
        assert "(" not in label and ")" not in label

    def test_strips_asterisk_from_sequence_label(self):
        content = "sequenceDiagram\n  A->>B: SELECT * FROM users"
        result = _clean_mermaid(content)
        label = result.split("A->>B:")[-1]
        assert "*" not in label

    def test_strips_equals_from_sequence_label(self):
        content = "sequenceDiagram\n  A->>B: id = 1"
        result = _clean_mermaid(content)
        label = result.split("A->>B:")[-1]
        assert "=" not in label

    def test_collapses_multiple_spaces(self):
        content = "sequenceDiagram\n  A->>B: a  b   c"
        result = _clean_mermaid(content)
        assert "  " not in result.split("A->>B:")[-1]

    def test_non_sequence_content_unchanged(self):
        content = "graph TD\n  A[Start] --> B[End]"
        result = _clean_mermaid(content)
        assert result == content

    def test_empty_string_returns_empty(self):
        assert _clean_mermaid("") == ""

    def test_dotted_arrow_sequence_label_cleaned(self):
        content = "sequenceDiagram\n  A-->>B: query(id=1)"
        result = _clean_mermaid(content)
        label = result.split("A-->>B:")[-1]
        assert "(" not in label and "=" not in label

class TestSanitizeBlock:
    def test_diagram_block_has_mermaid_cleaned(self):
        block = {
            "type": "diagram",
            "format": "mermaid",
            "content": "sequenceDiagram\n  A->>B: call(func)",
        }
        result = _sanitize_block(block)
        assert "(" not in result["content"]

    def test_non_diagram_block_unchanged(self):
        block = {"type": "paragraph", "content": "Hello (world)"}
        result = _sanitize_block(block)
        assert result["content"] == "Hello (world)"

    def test_diagram_without_content_unchanged(self):
        block = {"type": "diagram", "format": "mermaid", "content": ""}
        result = _sanitize_block(block)
        assert result["content"] == ""
