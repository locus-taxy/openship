# Structured Chapter Content — Technical Design Document

---

## 1. Problem

The LLM returns a single raw HTML string for each chapter. We store it in the `newsletter` column and the frontend renders it with `dangerouslySetInnerHTML`. Code highlighting requires scanning the DOM after render with `querySelectorAll("pre")` — fragile and hard to maintain.

**Pain points:**

- Frontend has no idea what's inside the HTML blob — must guess by scanning the DOM
- LLM sometimes forgets `<pre><code>` — code renders as plain text
- No language info on code blocks — hljs guesses, often wrong
- No structure to search, index, or export
- Every rendering fix is a DOM hack in `useEffect`

---

## 2. Solution — Typed Content Blocks

Instead of one HTML string, the LLM returns a **list of typed blocks**. Each block has a known type and the frontend renders it with a dedicated component. No DOM scanning. No HTML parsing.

---

## 3. Block Types

| Type | Required Fields | Purpose |
|---|---|---|
| `heading` | `content`, `level` (1/2/3) | Section title |
| `paragraph` | `content` | Plain prose text |
| `code` | `content`, `language` | Code sample with syntax highlighting |
| `bullet_list` | `items` | Unordered list |
| `numbered_list` | `items` | Ordered step-by-step list |
| `table` | `headers`, `rows` | Comparison or structured data |
| `note` | `content` | Tip, warning, or callout box |
| `quote` | `content` | Memorable statement or blockquote |
| `divider` | — | Section separator |
| `diagram` | `content`, `format` (`"mermaid"`) | Flowchart, sequence diagram, pie chart, ER diagram |

---

## 4. Pydantic Schema — `services/llm.py`

### Before

```python
class ChapterContent(BaseModel):
    html: str
```

One field. LLM returns a raw HTML string. No structure, no validation.

### After

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
    type:     BlockType
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
        # so minor LLM omissions don't fail the whole chapter.
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

## 5. Database Changes — `models/daily_task.py`

### Before — `daily_tasks` table

| Column | Type | Notes |
|---|---|---|
| `id` | int | Primary key |
| `user_id` | str | Owner |
| `skill` | str | |
| `skill_id` | int | |
| `month` / `week` / `day` | int | Schedule position |
| `topic` | str | Chapter title |
| `task` | str | Task description |
| `hours` | int | Estimated hours |
| `newsletter` | text | **Raw HTML chapter content** |
| `completed` | bool | |
| `completed_at` | datetime | |

### After — `daily_tasks` table

| Column | Type | Notes |
|---|---|---|
| `id` | int | Primary key |
| `user_id` | str | Owner |
| `skill` | str | |
| `skill_id` | int | |
| `month` / `week` / `day` | int | Schedule position |
| `topic` | str | Chapter title |
| `task` | str | Task description |
| `hours` | int | Estimated hours |
| `newsletter` | text | Legacy raw HTML — kept for old chapters |
| `content_blocks` | text | **New — JSON array of typed content blocks** |
| `completed` | bool | |
| `completed_at` | datetime | |

Only one column added. `newsletter` is kept so old chapters continue to work without any migration.

### `content_blocks` format

Stored as a JSON string — a serialized `List[ContentBlock]`:

```json
[
  {"type": "heading", "content": "Rust Ownership", "level": 1, "language": null, ...},
  {"type": "code", "language": "rust", "content": "fn main() {\n    let x = 5;\n}", ...}
]
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

---

## 6. Backend Changes

### 6.1 LLM Service — `services/llm.py`

#### Before

```python
def generate_chapter_html(...) -> Optional[str]:
    response: ChapterContent = client.chat.completions.create(
        model=model,
        response_model=ChapterContent,   # ChapterContent(html: str)
        messages=[...],
    )
    return response.html                 # returns raw HTML string
```

#### After

```python
def generate_chapter_content(...) -> Optional[StructuredChapterContent]:
    response: StructuredChapterContent = client.chat.completions.create(
        model=model,
        response_model=StructuredChapterContent,   # validated typed blocks
        messages=[system_prompt, user_prompt],
        max_retries=1,                             # auto-retry on validation failure
    )
    return response
```

`generate_chapter_html()` is kept unchanged for the bulk/legacy generation path.

---

#### Gemini Adapter Patch (issue #69)

Instructor's `GENAI_STRUCTURED_OUTPUTS` mode has four problems with Gemini that required patching `generate_content` before each call:

| # | Problem | Root Cause | Fix |
|---|---|---|---|
| 1 | `TypeError: unexpected keyword argument 'max_tokens'` | Instructor forwards an OpenAI-style `max_tokens` kwarg; Gemini's SDK rejects it. Our error handler was misclassifying this TypeError as a truncation error. | `kwargs.pop("max_tokens", None)` |
| 2 | JSON truncated mid-response | Instructor never sets `max_output_tokens`, so Gemini uses its own low default | Inject `max_output_tokens=32768` when not set |
| 3 | Only `heading` and `paragraph` blocks generated | Instructor derives a schema from the Pydantic model and passes it as `response_schema`. Gemini uses **constrained decoding** at the token level — it ignores the prompt and picks the cheapest valid blocks since all `ContentBlock` fields are `Optional` | Set `response_schema=None` before the request reaches Gemini. Instructor still validates the JSON response via `model_validate_json` and retries on failure — same result, but the prompt now drives what gets generated |
| 4 | Thinking tokens waste output budget | Gemini 2.5 models run thinking by default; thinking tokens count against `max_output_tokens` with no quality benefit for structured JSON output | `thinking_budget=0` |

```python
def _patched_generate(*args, **kwargs):
    kwargs.pop("max_tokens", None)                          # fix 1

    config = kwargs.get("config")
    if config is not None:
        update = {}
        if getattr(config, "max_output_tokens", None) is None:
            update["max_output_tokens"] = 32768             # fix 2
        update["thinking_config"] = ThinkingConfig(thinking_budget=0)  # fix 4
        if getattr(config, "response_schema", None) is not None:
            update["response_schema"] = None                # fix 3
        if update:
            kwargs["config"] = config.model_copy(update=update)

    return _real_generate(*args, **kwargs)

google_client.models.generate_content = _patched_generate
return instructor.from_genai(client=google_client, mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS)
```

> **Why not `GENAI_TOOLS` mode?** Tried it. In tools mode, instructor passes the Pydantic model as a function/tool definition and Gemini responds with a function call (dict, not JSON text). Pydantic v2 then fails with `is_instance_of` errors because it receives plain strings for `BlockType` enum fields instead of enum instances. `GENAI_STRUCTURED_OUTPUTS` + `response_schema=None` is the correct approach.

---

### 6.2 Prompt — `prompts/chapter.py`

#### Before

```python
def system_prompt() -> str:
    return (
        "You are a senior technical educator and blog writer. "
        "Write a detailed, beginner-friendly blog explaining the concept or task described. "
        "Return the response as clean HTML content with no CSS or extra metadata."
    )
```

Free-form instruction. LLM returns HTML. No block structure enforced.

#### After

```python
def system_prompt() -> str:
    return (
        "You are a senior technical educator. "
        "Write a detailed, beginner-friendly chapter...\n\n"
        "CRITICAL OUTPUT RULES:\n\n"
        "Return a JSON object with a single key 'blocks' containing an array of block objects. "
        "Every block MUST have a 'type' field and the required fields for that type...\n\n"
        # Each block type listed with required fields + example JSON
        "Additional rules:\n"
        "- NEVER put code inside a paragraph block — always use a code block\n"
        "- For ANY chart, flowchart, sequence diagram, pie chart — ALWAYS use a 'diagram' block. NEVER a code block.\n"
        "- In mermaid diagram content: keep labels as short plain words only (3-6 words). "
        "  NEVER put SQL, code, parentheses, commas, asterisks, question marks, equals signs, or slashes in labels.\n"
        "- Write 8-14 blocks covering the topic thoroughly with real-world examples and working code\n"
        "- Every code block must be complete and runnable — no placeholders or pseudocode"
    )
```

The prompt is the single source of truth for content structure because `response_schema` is nulled out for Gemini. Other providers (OpenAI, Anthropic, Mistral) follow it via their own structured output mechanisms.

---

### 6.3 Data Service — `services/daily_task.py`

#### Before

```python
def get_chapter_content(task_id: int) -> Optional[Dict]:
    return {
        "newsletter": t.newsletter,      # only HTML column returned
        # no content_blocks
    }

def add_content_to_db(newsletter: str, task_id: int) -> bool:
    task.newsletter = _sanitize_html(newsletter)
    session.commit()
```

#### After

```python
def get_chapter_content(task_id: int) -> Optional[Dict]:
    return {
        "newsletter":     t.newsletter,       # legacy — kept for old chapters
        "content_blocks": t.content_blocks,   # new structured blocks
        "has_content":    t.content_blocks is not None or t.newsletter is not None,
    }

def add_blocks_to_db(blocks: list, task_id: int) -> bool:
    task.content_blocks = json.dumps([_sanitize_block(b.model_dump()) for b in blocks])
    session.commit()
```

`add_content_to_db()` is kept unchanged for the bulk/legacy path.

#### Mermaid Sanitization — `_clean_mermaid()`

LLMs frequently generate mermaid diagram syntax with characters that break the parser. Applied to every `diagram` block before writing to the database:

| Issue | Example | Fix |
|---|---|---|
| HTML entities | `List&lt;Book&gt;` | `html.unescape()` → `List<Book>` |
| Slashes in labels | `success/failure` | Replace `/` with space → `success failure` |
| Parentheses in labels | `verifyCredentials(user, pass)` | Strip `()` → `verifyCredentials user pass` |
| SQL/special chars | `SELECT * WHERE id=?` | Strip `*`, `?`, `=`, `,` etc. |

```python
def _clean_mermaid(content: str) -> str:
    content = unescape(content)
    def _clean_label(m):
        prefix, label = m.group(1), m.group(2)
        label = re.sub(r"[/|]", " ", label)
        label = re.sub(r"[()[\]{}<>*?=,;!@#$%^&+~`\"'\\]", "", label)
        label = re.sub(r"\s{2,}", " ", label).strip()
        return prefix + label
    content = re.sub(r"((?:-->>?|->>?|->)\s*[^:\n]+:\s*)(.+)", _clean_label, content)
    return content
```

---

### 6.4 Controller — `controllers/content.py`

#### Before

```python
def generate_chapter(payload, current_user):
    html = generate_chapter_html(task_description=..., task_title=..., skill=...)
    add_content_to_db(newsletter=html, task_id=payload.task_id)
```

#### After

```python
def generate_chapter(payload, current_user):
    result = generate_chapter_content(task_description=..., task_title=..., skill=...)
    add_blocks_to_db(blocks=result.blocks, task_id=payload.task_id)
```

---

## 7. API Response

`GET /chapter/{task_id}` now returns both columns. Frontend checks `content_blocks` first.

### New chapter (has blocks)

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

### Old chapter (legacy HTML)

```json
{
  "id": 7,
  "topic": "Variables in Python",
  "completed": true,
  "has_content": true,
  "content_blocks": null,
  "newsletter": "<h1>Variables in Python</h1><p>...</p>"
}
```

---

## 8. Frontend Changes — `ui/src/app/plugins/syllabi/detail.tsx`

### Before

```tsx
// Renders raw HTML — no block structure
<div
  ref={proseRef}
  dangerouslySetInnerHTML={{ __html: sanitizeHtml(content) }}
/>

// Then in useEffect — scans DOM to find code blocks and highlight them
proseRef.current.querySelectorAll("pre").forEach(pre => {
  hljs.highlightElement(pre.querySelector("code"))
})
```

### After

Each block from the database renders as a dedicated React component. No `dangerouslySetInnerHTML`, no DOM scanning.

```tsx
function BlockRenderer({ blocks }: { blocks: ContentBlock[] }) {
  return (
    <div className="space-y-4">
      {blocks.map((block, i) => <BlockItem key={i} block={block} />)}
    </div>
  )
}

function BlockItem({ block }: { block: ContentBlock }) {
  switch (block.type) {
    case "heading":       return <HeadingBlock ... />
    case "paragraph":     return <p>{block.content}</p>
    case "code":          return <CodeBlock code={block.content} language={block.language} />
    case "bullet_list":   return <ul>{block.items.map(item => <li>{item}</li>)}</ul>
    case "numbered_list": return <ol>{block.items.map(item => <li>{item}</li>)}</ol>
    case "table":         return <ContentTable headers={block.headers} rows={block.rows} />
    case "note":          return <NoteBlock content={block.content} />
    case "quote":         return <blockquote>{block.content}</blockquote>
    case "divider":       return <hr />
    case "diagram":       return <MermaidBlock code={block.content} />
    default:              return null
  }
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
          ref.current.innerHTML = `<pre ...>${code}</pre>`
      })

    return () => { cancelled = true }
  }, [code, id])

  return <div ref={ref} className="rounded-xl border border-border bg-muted/30 p-4 overflow-x-auto" />
}
```

> **Package:** `mermaid` npm v11.14.0
>
> **`innerHTML` note:** Used intentionally here — the SVG is produced by the mermaid library from our sanitized backend content, not from raw user input. This is not a `dangerouslySetInnerHTML` concern.

### Backward Compatibility

```tsx
const blocks = useMemo(() => {
  if (!chapter.content_blocks) return null
  try { return JSON.parse(chapter.content_blocks) }
  catch { return null }
}, [chapter.content_blocks])

// In JSX:
{blocks ? (
  <BlockRenderer blocks={blocks} />          // new path — typed blocks
) : content ? (
  <div dangerouslySetInnerHTML={{ __html: sanitizeHtml(content) }} />  // legacy path
) : null}
```

`dangerouslySetInnerHTML` now only appears on the legacy path for old HTML chapters. All newly generated chapters render as typed blocks.

---

## 9. Error Handling

| Scenario | Handling |
|---|---|
| LLM returns an unknown block type | Pydantic rejects — instructor retries once → returns `None` → HTTP 500 |
| LLM omits `language` on a code block | `model_validator` defaults to `""` — hljs auto-detects language on frontend |
| LLM omits `content` on a heading/paragraph | `model_validator` defaults to `""` — filtered out or rendered empty downstream |
| LLM generates invalid mermaid syntax | `_clean_mermaid()` sanitizes on save; `MermaidBlock` catches remaining errors and shows raw code as fallback |
| Gemini truncates the JSON response | `max_output_tokens=32768` injected via patch; if still truncated → HTTP 422 with user-friendly message |
| `content_blocks` JSON corrupted in DB | Frontend `try/catch` in `useMemo` falls back to `newsletter` HTML |
| Old chapter has no `content_blocks` | Frontend renders `newsletter` HTML (legacy path) — works indefinitely |

---

## 10. Migration Plan

| Phase | What | Status |
|---|---|---|
| **1** | Add `content_blocks` column via Alembic (nullable) | Done |
| **2** | New chapters write to `content_blocks`; old chapters untouched | Done |
| **3** | Frontend renders blocks if present, falls back to HTML | Done |
| **4** | Users regenerate old chapters on demand via Regenerate button | Ongoing |
| **5** | Drop `newsletter` column when usage is near zero | Future |

Old chapters continue to work via the HTML path indefinitely — no forced migration.

---

## 11. Files Changed

| File | What Changed |
|---|---|
| `models/daily_task.py` | Added `content_blocks: Optional[str]` column |
| `alembic/versions/` | New migration — `ADD COLUMN content_blocks TEXT` |
| `services/llm.py` | Added `BlockType`, `ContentBlock`, `StructuredChapterContent`; added `generate_chapter_content()`; Gemini adapter patch (issue #69) |
| `prompts/chapter.py` | Rewrote `system_prompt()` — explicit block definitions, diagram enforcement, mermaid label rules, 8-14 blocks requirement |
| `services/daily_task.py` | Added `add_blocks_to_db()`, `_clean_mermaid()`, `_sanitize_block()`; updated `get_chapter_content()` to return both columns |
| `controllers/content.py` | `generate_chapter()` uses `generate_chapter_content()` + `add_blocks_to_db()` |
| `ui/src/app/plugins/syllabi/detail.tsx` | Added `BlockRenderer`, `BlockItem`, `CodeBlock`, `MermaidBlock`; backward-compat fallback for legacy HTML |
| `ui/package.json` | Added `mermaid` npm dependency (v11.14.0) |
