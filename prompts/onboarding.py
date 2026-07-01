_BLOCK_TYPES_GUIDE = """
AVAILABLE BLOCK TYPES — use only these:
  heading      → {type:"heading", level:1|2|3, content:"..."}
  paragraph    → {type:"paragraph", content:"..."}
  bullet_list  → {type:"bullet_list", items:["...", "..."]}
  numbered_list→ {type:"numbered_list", items:["...", "..."]}
  code         → {type:"code", language:"bash|java|yaml|json|...", content:"..."}
  table        → {type:"table", headers:["Col1","Col2"], rows:[["v1","v2"],...]}
  note         → {type:"note", content:"..."} — use for important callouts/warnings
  quote        → {type:"quote", content:"..."} — use for direct quotes from docs
  divider      → {type:"divider"}
  diagram      → {type:"diagram", content:"<mermaid syntax>"} — only for architecture flows

INLINE FORMATTING inside content/items/cells:
  **bold**, `code`, [link text](https://full-url)
  → When the source document contains a URL or repo link, ALWAYS render it as a markdown link.
  → Never silently drop URLs — surface every relevant link you find in the documents.
"""

def plan_system_prompt(role: str) -> str:
    return f"""You are an expert engineering onboarding designer. Your job is to read {role} at a technology company and produce a strict 7-day onboarding plan.

OUTPUT FORMAT — return a JSON object with EXACTLY this structure, no extra keys:
{{"days": [{{"day": 1, "topic": "Short topic title", "task": "What to read, explore, or do"}}, ... 7 items]}}

HARD RULES:
- Output EXACTLY 7 days, numbered 1 through 7. No more, no less.
- Each day must have:
    topic: a short, specific title (5-10 words max) referencing real company concepts from the docs
    task:  1-3 concrete sentences describing what to read, explore, or do — mention specific repos, services, or tools by name where relevant

DAY STRUCTURE GUIDELINES for a {role}:
  Day 1 — Company & product orientation: what Locus does, what products exist (Taxy vs Encore), the domain (logistics/supply chain), key customers
  Day 2 — Platform architecture: multi-tenancy model, schema-driven design, event-driven patterns, layer architecture, the WHY behind each decision
  Day 3 — Core platform internals: workflow engine (Zeebe/Camunda BPMN), authorization (OPA), database design (per-tenant schemas, JSONB), message broker (Pulsar)
  Day 4 — Key repositories: clone and explore the main repos, understand module structure, how to run locally, key entry points
  Day 5 — Role-specific deep dive: the services, APIs, and subsystems most relevant to {role}
  Day 6 — Integrations and operations: external integrations, monitoring, infrastructure, dev workflows
  Day 7 — Consolidation and self-assessment: review all concepts, draw the architecture yourself, prepare questions for your team

QUALITY CHECKS before responding:
- Topics must reference real Locus concepts (Encore, Taxy, Zeebe, OPA, Pulsar, etc.) — not generic phrases like "Learn the codebase"
- Tasks must name specific artifacts: repo names, service names, document sections
- Day 7 must be a consolidation/review day, not new content"""

def plan_user_prompt(role: str, company: str, docs_text: str) -> str:
    return f"""Company: {company}
Role: {role}

--- COMPANY DOCUMENTS ---
{docs_text}
--- END DOCUMENTS ---

Using only the information in the documents above, generate a 7-day onboarding plan for a new {role} at {company}.
Reference actual repo names, service names, architecture patterns, and tool names found in the documents.
Do NOT invent things not mentioned in the documents."""

def day_content_system_prompt(role: str, company: str) -> str:
    return (
        f"You are writing onboarding content for a new {role} at {company}. "
        f"Everything must be grounded in the company documents provided — no generic advice, no invented details.\n\n"
        "YOUR GOAL: By the end of reading this day, the new joiner understands:\n"
        "  1. WHAT the thing is (definition, scope)\n"
        "  2. WHY it was designed this way (cite the actual reason from the docs)\n"
        "  3. HOW it works (mechanics, flow)\n"
        "  4. WHERE to find it (repo names, links, tools — as clickable markdown links)\n\n"
        "LINK RELEVANCE RULE:\n"
        "  - Only include URLs, repo links, and tool links that are DIRECTLY relevant to this day's specific topic and task\n"
        "  - Do NOT surface links from other days' topics just because they appear somewhere in the docs\n"
        "  - Format as markdown links inside content/items/cells: [label](https://full-url)\n"
        "  - End with a 'Key Links & Resources' table listing only the links/repos relevant to TODAY's topic\n"
        "  - Never mention a repo name without linking it if a URL is available for that repo\n\n"
        "CRITICAL OUTPUT RULES — you MUST follow these exactly or your response will be rejected:\n\n"
        "Return a JSON object with a single key 'blocks' containing an array of block objects. "
        "Every block object MUST have a 'type' field and the corresponding required fields listed below. "
        "NEVER leave required fields as null or empty — always provide real content.\n\n"
        "Block types and their REQUIRED fields:\n\n"
        "1. heading  — REQUIRED: 'content' (non-empty string), 'level' (1=main title, 2=section, 3=sub-section)\n"
        '   Example: {"type": "heading", "content": "Multi-Tenant Architecture", "level": 2}\n\n'
        "2. paragraph — REQUIRED: 'content' (non-empty prose; use [label](url) for inline links)\n"
        '   Example: {"type": "paragraph", "content": "Locus serves hundreds of enterprise customers..."}\n\n'
        "3. code — REQUIRED: 'content' (raw code/command, no markdown fences), 'language' (e.g. 'bash', 'java', 'yaml', 'json', 'shell')\n"
        '   Example: {"type": "code", "language": "bash", "content": "gh repo clone locus-taxy/encore"}\n\n'
        "4. bullet_list — REQUIRED: 'items' (non-empty array of strings; use [label](url) for links inside items)\n"
        '   Example: {"type": "bullet_list", "items": ["[encore](https://github.com/locus-taxy/encore) — Core Platform API"]}\n\n'
        "5. numbered_list — REQUIRED: 'items' (non-empty array of strings in order)\n"
        '   Example: {"type": "numbered_list", "items": ["Step one: clone the repo", "Step two: run setup"]}\n\n'
        "6. table — REQUIRED: 'headers' (non-empty array of column names), 'rows' (non-empty 2D array, each row same length as headers; use [label](url) inside cells)\n"
        '   Example: {"type": "table", "headers": ["Repo", "Purpose", "Link"], "rows": [["encore", "Core Platform", "[github](https://github.com/locus-taxy/encore)"]]}\n\n'
        "7. note — REQUIRED: 'content' (non-empty string with tip, warning, or important callout)\n"
        '   Example: {"type": "note", "content": "encore-commons must be published locally before other services pick up changes."}\n\n'
        "8. quote — REQUIRED: 'content' (non-empty memorable statement from the docs)\n"
        '   Example: {"type": "quote", "content": "Without multi-tenancy, each customer would need separate infrastructure."}\n\n'
        "9. divider — No additional fields needed.\n"
        '   Example: {"type": "divider"}\n\n'
        "10. diagram — REQUIRED: 'content' (valid Mermaid syntax), 'format' must be 'mermaid'. Use for architecture flows and request flows — NEVER a code block.\n"
        "    Only use these Mermaid types: graph, sequenceDiagram, classDiagram, stateDiagram, gantt, pie, erDiagram.\n"
        "    In mermaid: node labels inside [] must be plain words — no colons, slashes, or special chars; edge labels go BEFORE destination: A -->|label| B[Node]\n"
        '    Example: {"type": "diagram", "format": "mermaid", "content": "graph TD\\n  A[Client] --> B[APISIX Gateway] --> C[encore API]"}\n\n'
        "Additional rules:\n"
        "- NEVER put code inside a paragraph — always use a code block\n"
        "- NEVER omit 'content' for heading/paragraph/code/note/quote/diagram blocks\n"
        "- NEVER omit 'items' for bullet_list/numbered_list blocks\n"
        "- Architecture days (Day 2, 3) MUST include at least one diagram block\n"
        "- Setup days (Day 4) MUST include code blocks with the actual commands from the documents\n"
        "- Write 10-14 blocks covering the topic in depth\n"
        "- ALWAYS end with: (1) heading level=2 content='Key Links & Resources', "
        "(2) table block with columns [Name, Description, Link] listing repos/tools/URLs relevant to TODAY's topic only\n"
        f"- Every fact must come from the {company} documents — never invent\n"
    )

def day_content_user_prompt(day: int, topic: str, task: str, company: str, docs_text: str) -> str:
    return (
        f"Day {day} of {company} onboarding.\n"
        f"Topic: {topic}\n"
        f"Task: {task}\n\n"
        f"--- COMPANY DOCUMENTS ---\n"
        f"{docs_text}\n"
        f"--- END DOCUMENTS ---\n\n"
        f"Write comprehensive Day {day} onboarding content grounded entirely in the documents above.\n\n"
        f"MUST DO:\n"
        f"1. Include only URLs and repo links from the documents that are directly relevant to Day {day}'s topic: {topic}\n"
        f"2. Explain the WHY behind every architectural decision (the documents state the reason — use it)\n"
        f"3. Include a 'Key Links & Resources' table at the end — only links/repos relevant to today's topic\n"
        f"4. Name specific repos, services, tools from the documents — never refer to them generically\n"
        f"5. Day 2-3: include a diagram block for architecture flows\n"
        f"6. Day 4+: include code blocks with actual commands from the documents\n"
        f"7. Output valid JSON blocks only — no prose outside the blocks array"
    )

def quiz_system_prompt(role: str, company: str) -> str:
    return f"""You are writing a 10-question multiple-choice final quiz for a new {role} who has completed 7 days of onboarding at {company}.

OUTPUT FORMAT — return a JSON object with EXACTLY this structure, no extra keys:
{{"questions": [{{"question": "...", "option_a": "...", "option_b": "...", "option_c": "...", "option_d": "...", "correct_answer": "a", "explanation": "..."}}, ... 10 items]}}

QUESTION QUALITY RULES:
  - Every question must test understanding of {company}-specific knowledge, not generic tech knowledge
  - Questions must be answerable from the onboarding documents — no trivia or speculation
  - At least 3 questions on architecture decisions and WHY (e.g., "Why does Locus use Pulsar over Kafka?")
  - At least 2 questions on specific repos or services
  - At least 2 questions on the platform's core design patterns (multi-tenancy, schema-driven, BPMN)
  - Distractors (wrong options) must be plausible — not obviously silly
  - Each question must have exactly 4 options (a, b, c, d) and exactly one correct answer
  - Include a 1-2 sentence explanation for why the correct answer is right (referencing the actual design rationale)"""

def quiz_user_prompt(company: str, topics: list[str], num_questions: int, docs_text: str) -> str:
    topics_str = "\n".join(f"  - {t}" for t in topics)
    return f"""Company: {company}

Topics covered during the 7-day onboarding:
{topics_str}

--- COMPANY DOCUMENTS ---
{docs_text}
--- END DOCUMENTS ---

Generate {num_questions} multiple-choice quiz questions that test a new joiner's real understanding of {company}'s product, architecture, and engineering decisions.

For each question include:
  - question: the question text
  - option_a, option_b, option_c, option_d: the four choices
  - correct_answer: "a", "b", "c", or "d"
  - explanation: why the correct answer is right, citing the actual design rationale from the docs

Make questions that a new joiner who carefully read the documents would get right, but a generic engineer who never read them would likely get wrong."""

def classify_system_prompt() -> str:
    return """You decide whether a company wiki page is useful for onboarding a new engineer.

A page is RELEVANT if it helps a new technical hire understand the company's
product, architecture, codebase, platform, tooling, setup, or engineering process.
A page is NOT relevant if it is HR policy, sales/marketing, meeting notes, personal
pages, or unrelated administrative content.

Return:
  - is_relevant: true or false
  - role_tags: which engineering roles it helps, a subset of
      ["backend", "devops", "sdet", "qa", "product", "general"];
      use ["general"] if it applies broadly; empty list if not relevant
  - confidence: your confidence from 0.0 to 1.0

Judge only from the title and excerpt provided. Do not invent."""

def classify_user_prompt(title: str, excerpt: str) -> str:
    body = excerpt.strip() or "(no readable body)"
    return f"""Page title: {title}

Excerpt:
{body}

Is this page useful for onboarding a new engineer?"""
