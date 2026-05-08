# Structured Chapter Content — Technical Design Document

## 1. Current State & Problems

Right now, the LLM returns a single raw HTML string for each chapter. We store that in the `newsletter` column and the frontend renders it with `dangerouslySetInnerHTML`. To apply code highlighting, the frontend scans the DOM after render using `querySelectorAll("pre")` — fragile and hard to maintain.

**Problems:**

- Frontend has no idea what's inside the HTML blob — must guess by scanning DOM
- LLM sometimes forgets to wrap code in `<pre><code>` — renders as plain text
- No language info on code blocks — hljs guesses, often wrong
- No structure to search, index, or export
- Any rendering fix requires a DOM hack in `useEffect`

---

## 2. Proposed Solution — Typed Content Blocks

Instead of one HTML string, the LLM returns a **list of typed blocks**. Each block has a known type and the frontend renders each type with a dedicated component. No DOM scanning. No HTML parsing.

---

## 3. Block Types

| Type | Purpose |
|---|---|
| `heading` | Section title — level 1, 2, or 3 |
| `paragraph` | Plain prose text |
| `code` | Code sample with language specified |
| `bullet_list` | Unordered list of items |
| `numbered_list` | Ordered list of items |
| `table` | Comparison table with headers and rows |
| `note` | Callout box — tip, warning, or info |
| `quote` | Memorable statement or blockquote |
| `divider` | Section separator |
| `diagram` | Mermaid diagram — flow, sequence, ER, pie chart, etc. |

---

## 4. Pydantic Schema — `services/llm.py`

```python
class BlockType(str, Enum):
    HEADING       = "heading"
    PARAGRAPH     = "paragraph"
    CODE          = "code"
    BULLET_LIST   = "bullet_list"
    NUMBERED_LIST = "numbered_list"
    TABLE         = "table"
    NOTE          = "note"
    QUOTE         = "quote"
    DIVIDER       = "divider"
    DIAGRAM       = "diagram"


class ContentBlock(BaseModel):
    type: BlockType

    content:  Optional[str]              = None  # heading, paragraph, code, note, quote, diagram
    level:    Optional[int]              = None  # heading only — 1, 2, or 3
    language: Optional[str]              = None  # code only — e.g. "python", "rust"
    items:    Optional[List[str]]        = None  # bullet_list, numbered_list
    headers:  Optional[List[str]]        = None  # table only
    rows:     Optional[List[List[str]]]  = None  # table only
    format:   Optional[str]              = None  # diagram only — always "mermaid"

    @field_validator("level")
    @classmethod
    def level_must_be_valid(cls, v):
        if v is not None and v not in (1, 2, 3):
            raise ValueError("Heading level must be 1, 2, or 3")
        return v

    @model_validator(mode="after")
    def validate_block(self) -> "ContentBlock":
        # Sets safe defaults for missing optional fields rather than raising,
        # so minor LLM omissions don't break the whole chapter.
        t = self.type
        if t == BlockType.HEADING:
            if not self.content: self.content = ""
            if self.level is None: self.level = 2
        elif t in (BlockType.PARAGRAPH, BlockType.NOTE, BlockType.QUOTE):
            if not self.content: self.content = ""
        elif t == BlockType.CODE:
            if not self.content: self.content = ""
            if not self.language: self.language = ""  # hljs auto-detects as fallback
        elif t in (BlockType.BULLET_LIST, BlockType.NUMBERED_LIST):
            if not self.items: self.items = []
        elif t == BlockType.TABLE:
            if not self.headers: self.headers = []
            if not self.rows: self.rows = []
        return self


class StructuredChapterContent(BaseModel):
    blocks: List[ContentBlock]
```

---

## 5. Database Changes

### `models/daily_task.py`

Added one new column. `newsletter` kept for backward compatibility.

```python
newsletter:     Optional[str] = None   # legacy HTML — kept for old chapters
content_blocks: Optional[str] = None   # new: JSON string of List[ContentBlock]
```

### Alembic Migration

```python
def upgrade():
    op.add_column(
        "daily_tasks",
        sa.Column("content_blocks", sa.Text(), nullable=True)
    )

def downgrade():
    op.drop_column("daily_tasks", "content_blocks")
```

`content_blocks` stores the entire blocks list as a single JSON string.

---

## 6. Backend Changes

### 6.1 LLM Service — `services/llm.py`

New function alongside the existing `generate_chapter_html()` (kept for bulk/legacy path):

```python
def generate_chapter_content(...) -> Optional[StructuredChapterContent]:
    response: StructuredChapterContent = client.chat.completions.create(
        model=model,
        response_model=StructuredChapterContent,
        messages=[system_prompt, user_prompt],
        max_retries=1,
    )
    return response
```

#### Gemini-specific adapter patch (issue #69)

Instructor's `GENAI_STRUCTURED_OUTPUTS` mode has three problems with Gemini that required a low-level patch on `generate_content`:

1. **`max_tokens` kwarg** — instructor forwards it as a top-level kwarg but Gemini's SDK rejects it with a `TypeError`. Our error handler was misclassifying this as a truncation error. Fix: `kwargs.pop("max_tokens", None)`.

2. **No `max_output_tokens`** — instructor never sets it, so Gemini uses its own low default and truncates the JSON. Fix: inject `max_output_tokens=32768` when not set.

3. **`response_schema` overrides prompt** — instructor derives a JSON schema from the Pydantic model and passes it to Gemini as `response_schema`. When set, Gemini uses constrained decoding at the token level and ignores prompt instructions — picking only the easiest valid block types (`heading`, `paragraph`) since all `ContentBlock` fields are `Optional`. Fix: null out `response_schema` before the request reaches Gemini. Instructor still validates the JSON response against the Pydantic model via `model_validate_json` and retries on failure — same end result, but the prompt now drives *what* gets generated.

4. **Thinking tokens** — Gemini 2.5 models run thinking by default, consuming `max_output_tokens` budget on non-content tokens. Fix: `thinking_budget=0`.

```python
def _patched_generate(*args, **kwargs):
    kwargs.pop("max_tokens", None)

    config = kwargs.get("config")
    if config is not None:
        update = {}
        if getattr(config, "max_output_tokens", None) is None:
            update["max_output_tokens"] = 32768
        update["thinking_config"] = ThinkingConfig(thinking_budget=0)
        if getattr(config, "response_schema", None) is not None:
            update["response_schema"] = None
        if update:
            kwargs["config"] = config.model_copy(update=update)

    return _real_generate(*args, **kwargs)

google_client.models.generate_content = _patched_generate
return instructor.from_genai(client=google_client, mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS)
```

> **Why not `GENAI_TOOLS` mode?** Tried it — instructor passes the Pydantic model as a function/tool definition in that mode, so Gemini responds with a function call (dict), not JSON text. Pydantic v2 then fails with `is_instance_of` errors because it receives plain strings for `BlockType` fields instead of enum instances. `GENAI_STRUCTURED_OUTPUTS` + `response_schema=None` is the correct approach.

---

### 6.2 Prompt — `prompts/chapter.py`

The prompt defines each block type explicitly with examples, since Gemini (without `response_schema`) relies entirely on the prompt for structure:

```python
def system_prompt() -> str:
    return (
        "You are a senior technical educator. "
        "Write a detailed, beginner-friendly chapter...\n\n"
        "CRITICAL OUTPUT RULES:\n\n"
        "Return a JSON object with a single key 'blocks' containing an array of block objects.\n\n"
        # ... each block type defined with required fields and example JSON ...
        "Additional rules:\n"
        "- NEVER put code inside a paragraph block — always use a code block\n"
        "- For ANY chart, flowchart, sequence diagram, pie chart — ALWAYS use a 'diagram' block. NEVER a code block.\n"
        "- In mermaid diagram content: keep labels as short plain words only. NEVER put SQL, parentheses, commas, asterisks, question marks, equals signs, or slashes inside labels.\n"
        "- Write 8-14 blocks covering the topic thoroughly with real-world examples and working code\n"
        "- Every code block must be complete and runnable — no placeholders or pseudocode"
    )
```

---

### 6.3 Data Service — `services/daily_task.py`

#### Mermaid sanitization before saving

LLMs sometimes generate mermaid syntax with characters that break the mermaid parser. Applied to every `diagram` block before writing to DB:

```python
def _clean_mermaid(content: str) -> str:
    content = unescape(content)           # &lt; → <, &gt; → >, etc.

    # In sequence diagram message labels: replace / with space,
    # strip remaining parser-breaking chars (*, ?, =, commas, parens, etc.)
    def _clean_label(m):
        prefix, label = m.group(1), m.group(2)
        label = re.sub(r"[/|]", " ", label)
        label = re.sub(r"[()[\]{}<>*?=,;!@#$%^&+~`\"'\\]", "", label)
        label = re.sub(r"\s{2,}", " ", label).strip()
        return prefix + label

    content = re.sub(r"((?:-->>?|->>?|->)\s*[^:\n]+:\s*)(.+)", _clean_label, content)
    return content
```

#### New functions

```python
def add_blocks_to_db(blocks: list, task_id: int) -> bool:
    task.content_blocks = json.dumps([_sanitize_block(b.model_dump()) for b in blocks])
    session.commit()
```

`get_chapter_content()` now returns both `newsletter` and `content_blocks`, plus `has_content`.

---

### 6.4 Controller — `controllers/content.py`

```python
def generate_chapter(payload, current_user):
    result = generate_chapter_content(
        task_description=chapter["task"],
        task_title=chapter["topic"],
        skill=chapter["skill"],
        ...
    )
    add_blocks_to_db(blocks=result.blocks, task_id=payload.task_id)
```

---

## 7. API Response

`GET /chapter/{task_id}` returns both columns. Frontend checks `content_blocks` first:

```json
{
  "id": 42,
  "topic": "Rust Ownership",
  "completed": false,
  "has_content": true,
  "content_blocks": "[{\"type\":\"heading\",\"content\":\"Rust Ownership\",\"level\":1}, ...]",
  "newsletter": null
}
```

Old chapters: `content_blocks` is null, `newsletter` has the HTML. Frontend falls back automatically.

---

## 8. Frontend Changes — `ui/src/app/plugins/syllabi/detail.tsx`

### Block Renderer

Each block from the database renders as a dedicated React component — no `dangerouslySetInnerHTML`, no DOM scanning.

```tsx
function BlockRenderer({ blocks }: { blocks: ContentBlock[] }) {
  return (
    <div className="space-y-4">
      {blocks.map((block, i) => <BlockItem key={i} block={block} />)}
    </div>
  )
}
```

### MermaidBlock Component

```tsx
import mermaid from "mermaid"
mermaid.initialize({ startOnLoad: false, theme: "dark" })

function MermaidBlock({ code }: { code: string }) {
  const id = useId()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return
    let cancelled = false
    const renderId = `mermaid-${id.replace(/[^a-zA-Z0-9]/g, "")}`

    mermaid.render(renderId, code)
      .then(({ svg }) => {
        if (!cancelled && ref.current) ref.current.innerHTML = svg
      })
      .catch(() => {
        // Fallback: show raw mermaid syntax if parse fails
        if (!cancelled && ref.current)
          ref.current.innerHTML = `<pre class="text-xs text-muted-foreground whitespace-pre-wrap p-4">${code}</pre>`
      })

    return () => { cancelled = true }
  }, [code, id])

  return <div ref={ref} className="rounded-xl border border-border bg-muted/30 p-4 overflow-x-auto" />
}
```

> **Package:** `mermaid` npm v11.14.0
> **Note:** `innerHTML` is used here intentionally — the SVG is generated by the mermaid library from our sanitized backend content, not from raw user input.

### Backward Compatibility

```tsx
{blocks ? (
  <BlockRenderer blocks={blocks} />
) : content ? (
  // Legacy path — old HTML chapters only
  <div ref={proseRef} dangerouslySetInnerHTML={{ __html: sanitizeHtml(content) }} />
) : null}
```

`dangerouslySetInnerHTML` now only appears on the legacy newsletter path. All new chapters render as typed blocks.

---

## 9. Error Handling

| Scenario | Handling |
|---|---|
| LLM returns wrong block type | Pydantic rejects — instructor retries (max 1 time) → returns None → HTTP 500 |
| LLM forgets `language` on code block | `model_validator` defaults to `""` → hljs auto-detects on frontend |
| LLM returns mismatched table rows | `model_validator` softly defaults — does not raise |
| `content_blocks` JSON corrupted in DB | Frontend `try/catch` falls back to `newsletter` HTML |
| Old chapter has no `content_blocks` | Frontend renders `newsletter` HTML (legacy path) |
| LLM produces invalid Mermaid syntax | Backend `_clean_mermaid()` sanitizes before save; `MermaidBlock` catches remaining errors and shows raw code |
| Gemini truncates JSON | `max_output_tokens=32768` injected via patch — raises HTTP 422 if still truncated |

---

## 10. Migration Plan

| Phase | What |
|---|---|
| **1** | Add `content_blocks` column via Alembic (nullable) |
| **2** | New chapters write to `content_blocks`; old chapters untouched |
| **3** | Frontend renders blocks if present, falls back to HTML |
| **4** | Users regenerate old chapters on demand via Regenerate button |
| **5** | Drop `newsletter` column far in the future when near zero usage |

Old chapters continue to work via the HTML path indefinitely — no forced migration.

---

## 11. Files Changed

| File | Change |
|---|---|
| `models/daily_task.py` | Added `content_blocks: Optional[str]` field |
| `alembic/versions/` | New migration — add `content_blocks` column |
| `services/llm.py` | Added `BlockType`, `ContentBlock`, `StructuredChapterContent`; added `generate_chapter_content()`; Gemini adapter patch (issue #69) |
| `prompts/chapter.py` | New `system_prompt()` with explicit block definitions, diagram rules, mermaid label rules |
| `services/daily_task.py` | Added `add_blocks_to_db()`, `_clean_mermaid()`, `_sanitize_block()`; updated `get_chapter_content()` |
| `controllers/content.py` | `generate_chapter()` uses `generate_chapter_content()` + `add_blocks_to_db()` |
| `ui/src/app/plugins/syllabi/detail.tsx` | Added `BlockRenderer`, `BlockItem`, `CodeBlock`, `MermaidBlock`; backward-compat fallback |
| `ui/package.json` | Added `mermaid` npm dependency (v11.14.0) |
