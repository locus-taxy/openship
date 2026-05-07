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
| `diagram` | Mermaid diagram — flow, sequence, ER, etc. |

---

## 4. Pydantic Schema — Before vs After

### Before (current) — `services/llm.py`

```python
class ChapterContent(BaseModel):
    html: str
```

One field. LLM returns a raw HTML string. No structure.

---

### After (new) — `services/llm.py`

```python
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, field_validator, model_validator


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

    content:  Optional[str]         = None  # heading, paragraph, code, note, quote, diagram
    level:    Optional[int]         = None  # heading only — 1, 2, or 3
    language: Optional[str]         = None  # code only — e.g. "python", "rust"
    items:    Optional[List[str]]   = None  # bullet_list, numbered_list
    headers:  Optional[List[str]]   = None  # table only
    rows:     Optional[List[List[str]]] = None  # table only
    format:   Optional[str]         = None  # diagram only — always "mermaid"

    @field_validator("level")
    @classmethod
    def level_must_be_valid(cls, v):
        if v is not None and v not in (1, 2, 3):
            raise ValueError("Heading level must be 1, 2, or 3")
        return v

    @model_validator(mode="after")
    def validate_block(self) -> "ContentBlock":
        t = self.type
        if t == BlockType.HEADING:
            if not self.content:
                raise ValueError("heading block requires content")
            if self.level is None:
                self.level = 2
        elif t in (BlockType.PARAGRAPH, BlockType.NOTE, BlockType.QUOTE):
            if not self.content:
                raise ValueError(f"{t} block requires content")
        elif t == BlockType.CODE:
            if not self.content:
                raise ValueError("code block requires content")
            if not self.language:
                self.language = ""  # hljs auto-detects as fallback
        elif t in (BlockType.BULLET_LIST, BlockType.NUMBERED_LIST):
            if not self.items:
                raise ValueError(f"{t} block requires at least one item")
        elif t == BlockType.TABLE:
            if not self.headers or not self.rows:
                raise ValueError("table block requires headers and rows")
            for i, row in enumerate(self.rows):
                if len(row) != len(self.headers):
                    raise ValueError(f"Table row {i} has {len(row)} cells, expected {len(self.headers)}")
        elif t == BlockType.DIAGRAM:
            if not self.content:
                raise ValueError("diagram block requires content")
            if not self.format:
                self.format = "mermaid"
        return self


class ChapterContent(BaseModel):
    blocks: List[ContentBlock]

    @field_validator("blocks")
    @classmethod
    def blocks_must_not_be_empty(cls, v):
        if not v:
            raise ValueError("Chapter must have at least one block")
        return v
```

---

## 5. Database Changes

### Before — `models/daily_task.py`

```python
class DailyTask(SQLModel, table=True):
    __tablename__ = "daily_tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str
    skill: str
    skill_id: Optional[int] = ...
    month: Optional[int] = None
    week: Optional[int] = None
    day: Optional[int] = None
    topic: Optional[str] = None
    task: Optional[str] = None
    hours: Optional[int] = None
    newsletter: Optional[str] = None     # ← raw HTML stored here
    completed: bool = Field(default=False)
    ...
```

### After — `models/daily_task.py`

Add one new field. Keep `newsletter` for backward compatibility.

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

`content_blocks` stores the entire blocks list as a single JSON string, e.g.:

```json
"[{\"type\":\"heading\",\"content\":\"Rust Ownership\",\"level\":1}, {\"type\":\"code\",\"language\":\"rust\",\"content\":\"fn main() {...}\"}]"
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
def generate_chapter_content(...) -> Optional[ChapterContent]:
    response: ChapterContent = client.chat.completions.create(
        model=model,
        response_model=ChapterContent,   # ChapterContent(blocks: List[ContentBlock])
        messages=[...],
        max_retries=2,                   # extra retry — structured output is harder
    )
    return response                      # returns ChapterContent with validated blocks
```

Keep `generate_chapter_html()` during the transition so old bulk-generation still works.

---

### 6.2 Prompt — `prompts/chapter.py`

#### Before

```python
def system_prompt() -> str:
    return (
        "You are a senior technical educator and blog writer. "
        "Write a detailed, beginner-friendly blog explaining the concept or task described. "
        "Focus on practical explanation, step-by-step instructions, examples, and insights. "
        "Return the response as clean HTML content with no CSS or extra metadata. "
        "While taking examples, make them relevant to the given skill and industry."
    )
```

#### After

```python
def system_prompt() -> str:
    return (
        "You are a senior technical educator. "
        "Write a detailed, beginner-friendly chapter explaining the concept or task described. "
        "Return the response as a structured list of typed content blocks. "
        "Rules:\n"
        "- Use 'heading' blocks for section titles (level 1 for main title, 2 for sections, 3 for sub-sections)\n"
        "- Use 'paragraph' blocks for prose explanations\n"
        "- Use 'code' blocks for ALL code samples — always set the language field to the programming language name (e.g. 'python', 'javascript', 'rust', 'bash', 'sql')\n"
        "- Use 'bullet_list' or 'numbered_list' blocks for lists of items\n"
        "- Use 'table' blocks for comparisons and structured data\n"
        "- Use 'note' blocks for tips, warnings, or important callouts\n"
        "- Use 'quote' blocks for memorable statements\n"
        "- Use 'divider' blocks to separate major sections\n"
        "- Use 'diagram' blocks (format: mermaid) for flows, sequences, or architectures\n"
        "- Never put code inside a paragraph block — always use a code block\n"
        "- Code content must be raw code only — no markdown fences, no HTML\n"
        "- Make examples relevant to the given skill and industry"
    )
```

**How `language` gets included — three layers:**

1. **Prompt** — explicitly tells the LLM to set `language` to the programming language name (e.g. `"python"`, `"rust"`, `"bash"`)
2. **Instructor + schema** — the LLM must return a structured JSON matching `ContentBlock`. The `language` field is part of that schema, so the LLM is forced to fill it in as part of the structured output
3. **Fallback** — if the LLM still omits it, `model_validator` defaults `language` to `""` and hljs auto-detects the language on the frontend

---

### 6.3 Data Service — `services/daily_task.py`

#### Before

```python
def get_chapter_content(task_id: int) -> Optional[Dict[str, Any]]:
    with Session(engine) as session:
        t = session.get(DailyTask, task_id)
        if t is None:
            return None
        return {
            ...
            "newsletter": t.newsletter,      # only this column returned
        }

def add_content_to_db(newsletter: str, task_id: int) -> bool:
    task.newsletter = _sanitize_html(newsletter)   # sanitize then save HTML
    session.commit()
```

#### After

```python
def get_chapter_content(task_id: int) -> Optional[Dict[str, Any]]:
    with Session(engine) as session:
        t = session.get(DailyTask, task_id)
        if t is None:
            return None
        return {
            ...
            "newsletter":     t.newsletter,       # legacy — kept for old chapters
            "content_blocks": t.content_blocks,   # new structured content
            "has_content":    t.content_blocks is not None or t.newsletter is not None,
        }

def add_blocks_to_db(blocks: list, task_id: int) -> bool:
    import json
    task.content_blocks = json.dumps([b.model_dump() for b in blocks])
    session.commit()
```

---

### 6.4 Controller — `controllers/content.py`

#### Before

```python
def generate_chapter(payload, current_user):
    html = generate_chapter_html(
        task_description=chapter["task"],
        task_title=chapter["topic"],
        skill=chapter["skill"],
        ...
    )
    add_content_to_db(newsletter=html, task_id=payload.task_id)
```

#### After

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

`GET /chapter/{task_id}` will now return both columns. Frontend checks `content_blocks` first:

```json
{
  "id": 42,
  "topic": "Rust Ownership",
  "task": "Understand how ownership works",
  "day": 3,
  "hours": 2,
  "completed": false,
  "has_content": true,
  "content_blocks": "[{\"type\":\"heading\",\"content\":\"Rust Ownership\",\"level\":1}, ...]",
  "newsletter": null
}
```

Old chapters: `content_blocks` is null, `newsletter` has the HTML. Frontend falls back automatically.

---

## 8. Frontend Changes — `ui/src/app/plugins/syllabi/detail.tsx`

### TypeScript Types

```typescript
type BlockType =
  | "heading" | "paragraph" | "code"
  | "bullet_list" | "numbered_list"
  | "table" | "note" | "quote" | "divider"
  | "diagram"

interface ContentBlock {
  type: BlockType
  content?: string
  level?: number      // heading only
  language?: string   // code only
  items?: string[]    // list types only
  headers?: string[]  // table only
  rows?: string[][]   // table only
  format?: string     // diagram only — "mermaid"
}
```

### Block Renderer

```tsx
function BlockRenderer({ blocks }: { blocks: ContentBlock[] }) {
  return (
    <div className="space-y-4">
      {blocks.map((block, i) => <Block key={i} block={block} />)}
    </div>
  )
}

function Block({ block }: { block: ContentBlock }) {
  switch (block.type) {
    case "heading":      return <Heading level={block.level ?? 2}>{block.content!}</Heading>
    case "paragraph":    return <p className="text-zinc-600 leading-7">{block.content}</p>
    case "code":         return <CodeBlock code={block.content!} language={block.language ?? ""} />
    case "bullet_list":  return <ul className="list-disc pl-5 space-y-1">{block.items!.map((item, i) => <li key={i}>{item}</li>)}</ul>
    case "numbered_list":return <ol className="list-decimal pl-5 space-y-1">{block.items!.map((item, i) => <li key={i}>{item}</li>)}</ol>
    case "table":        return <ContentTable headers={block.headers!} rows={block.rows!} />
    case "note":         return <Callout>{block.content}</Callout>
    case "quote":        return <blockquote className="border-l-4 border-primary/40 pl-4 italic">{block.content}</blockquote>
    case "divider":      return <hr className="border-border my-2" />
    case "diagram":      return <MermaidBlock code={block.content!} />
    default:             return null
  }
}
```

### CodeBlock Component (no DOM scanning — receives code and language directly)

```tsx
function CodeBlock({ code, language }: { code: string; language: string }) {
  const ref = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!ref.current) return
    ref.current.textContent = code
    if (language) {
      ref.current.innerHTML = hljs.highlight(code, { language }).value
    } else {
      hljs.highlightElement(ref.current)
    }
  }, [code, language])

  const lines = code.split("\n")
  if (lines[lines.length - 1] === "") lines.pop()

  return (
    <div className="rounded-xl border border-white/10 bg-[#282c34] text-sm overflow-hidden">
      <div className="flex overflow-x-auto">
        <div className="flex flex-col shrink-0 select-none text-right px-3 py-4
                        text-[#636d83] text-xs leading-[1.6] border-r border-white/[0.08]">
          {lines.map((_, i) => <span key={i}>{i + 1}</span>)}
        </div>
        <div className="flex-1 overflow-x-auto px-5 py-4">
          <code ref={ref} className="font-mono text-xs leading-[1.6] whitespace-pre block" />
        </div>
      </div>
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
    mermaid.render(`mermaid-${id}`, code)
      .then(({ svg }) => { if (ref.current) ref.current.innerHTML = svg })
      .catch(() => {
        // Fallback: show raw code if Mermaid fails to parse
        if (ref.current)
          ref.current.innerHTML = `<pre class="text-xs text-muted-foreground whitespace-pre-wrap">${code}</pre>`
      })
  }, [code, id])

  return <div ref={ref} className="rounded-xl border border-border bg-muted/30 p-4 overflow-x-auto" />
}
```

> **Dependency:** `npm install mermaid` in `ui/`

### Backward Compatibility

```tsx
const blocks: ContentBlock[] | null = useMemo(() => {
  if (!chapter.content_blocks) return null
  try { return JSON.parse(chapter.content_blocks) }
  catch { return null }
}, [chapter.content_blocks])

// In JSX:
{blocks ? (
  <BlockRenderer blocks={blocks} />
) : content ? (
  // Legacy path — old HTML chapters
  <div ref={proseRef} dangerouslySetInnerHTML={{ __html: sanitizeHtml(content) }} />
) : null}
```

The `useEffect` that scans `<pre>` tags only runs on the legacy path.

---

## 9. Error Handling

| Scenario | Handling |
|---|---|
| LLM returns wrong block type | Pydantic rejects — `generate_chapter_content` returns None → HTTP 500 |
| LLM forgets `language` on code block | `model_validator` defaults to `""` → hljs auto-detects |
| LLM returns mismatched table rows | `model_validator` rejects — Instructor retries (max 2 times) |
| `content_blocks` JSON corrupted in DB | Frontend `try/catch` falls back to `newsletter` HTML |
| Old chapter has no `content_blocks` | Frontend renders `newsletter` HTML (legacy path) |
| LLM produces invalid Mermaid syntax | `MermaidBlock` catches error and shows raw code as plain text |

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

## 11. Files to Change

| File | Change |
|---|---|
| `models/daily_task.py` | Add `content_blocks: Optional[str]` field |
| `alembic/versions/` | New migration — add `content_blocks` column |
| `services/llm.py` | Add `BlockType`, `ContentBlock`, new `ChapterContent`; add `generate_chapter_content()` |
| `prompts/chapter.py` | Update `system_prompt()` to instruct block-based output |
| `services/daily_task.py` | Add `add_blocks_to_db()`, update `get_chapter_content()` to return both columns |
| `controllers/content.py` | Use `generate_chapter_content()` + `add_blocks_to_db()` |
| `ui/src/app/plugins/syllabi/detail.tsx` | Add `BlockRenderer`, `Block`, `CodeBlock`, `MermaidBlock`; backward-compat fallback |
| `ui/package.json` | Add `mermaid` npm dependency |
