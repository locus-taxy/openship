from typing import Optional

# Each entry is injected into the prompt as a MANDATORY STRUCTURAL RULE section,
# placed after the block-type definitions so it takes precedence.
# Instructions are prescriptive (ordering, counts, patterns) not just descriptive.
_STYLE_RULES = {
    "example_heavy": (
        "MANDATORY STYLE RULES — EXAMPLE-HEAVY (must be followed exactly):\n"
        "1. After every section heading (level 2 or 3), the VERY NEXT block MUST be a concrete example — either a 'code' block (for technical/programming topics) or a 'bullet_list' or 'numbered_list' showing a worked example (for non-technical topics). Never lead with a paragraph.\n"
        "2. The paragraph explaining the example always comes AFTER the example block, not before.\n"
        "3. Include at least 4 example blocks (code, worked examples, or step-by-step demonstrations) in total across the chapter.\n"
        "4. When introducing a new concept, always open with a concrete demonstration that shows it in action, then explain what it demonstrates and why it works that way.\n"
        "5. Use real-world analogies inside paragraphs (e.g. 'think of a variable like a labelled box').\n"
        "6. Demonstration blocks must make up more than half of all non-heading, non-divider blocks."
    ),
    "theory_first": (
        "MANDATORY STYLE RULES — THEORY-FIRST (must be followed exactly):\n"
        "1. After every section heading (level 2 or 3), the VERY NEXT block MUST be a 'paragraph' containing a precise formal definition of the concept — never an example or demonstration block first.\n"
        "2. Examples or demonstrations may only appear AFTER the concept has been fully explained in at least one paragraph.\n"
        "3. Each major concept must follow this exact pattern: heading → paragraph (definition) → paragraph (deeper explanation or why it matters) → example or demonstration (illustration only).\n"
        "4. Include at least one 'table' block that compares related concepts, terms, or terminology variants side by side.\n"
        "5. Definitions must be precise and complete — a reader should be able to understand the concept from the paragraph alone without looking at any example."
    ),
    "reinforcement": (
        "MANDATORY STYLE RULES — REINFORCEMENT (must be followed exactly):\n"
        "1. After every major section (before a new level-2 heading), add a 'note' block that summarises the single most important thing just explained. Minimum 2 'note' blocks in the chapter.\n"
        "2. Include exactly one 'quote' block containing a memorable rule-of-thumb or principle related to the topic.\n"
        "3. Include a 'bullet_list' block mid-chapter (not just at the end) that recaps what has been covered so far — this appears after the 2nd or 3rd section.\n"
        "4. The single most important concept in the chapter must appear TWICE: once explained in a paragraph and once demonstrated with a concrete example or illustration, using different wording each time.\n"
        "5. Paragraphs should be shorter (2-3 sentences) and more frequent — break explanations into smaller digestible chunks rather than one long paragraph."
    ),
    "balanced": (
        "MANDATORY STYLE RULES — BALANCED (must be followed exactly):\n"
        "1. Alternate between explanation and demonstration: each concept follows the pattern heading → paragraph (explain) → example or demonstration block (show it in action).\n"
        "2. Explanation blocks (paragraphs) and demonstration blocks (code, lists, or worked examples) must appear in roughly equal numbers — neither dominates.\n"
        "3. Include at least one 'note' block highlighting a common mistake or important caveat.\n"
        "4. After every demonstration block, include a paragraph that explains what was shown and why it works that way."
    ),
}

def system_prompt(concise: bool = False, style: Optional[str] = None) -> str:
    """Prompt for structured block-based chapter generation (new path).

    concise=True is used for providers with tight output token limits (e.g. Mistral Small).
    It targets fewer blocks and shorter paragraphs to stay within the 8 k token cap.
    style: one of 'balanced', 'example_heavy', 'theory_first', 'reinforcement' (or None = balanced).
    """
    block_count = "8-11" if concise else "8-14"
    depth_instruction = (
        "Be thorough but concise: keep paragraphs to 3-4 sentences and examples focused."
        if concise
        else "Explain concepts in depth with real-world examples, step-by-step walkthroughs, and concrete demonstrations suited to the topic."
    )
    # Style rules go AFTER block definitions so they are the last thing the LLM reads
    # before generating — maximises compliance.
    style_rules = _STYLE_RULES.get(style or "balanced", _STYLE_RULES["balanced"])
    return (
        "You are a senior educator and expert in the subject being taught. "
        "Write a beginner-friendly chapter explaining the concept or task described.\n\n"
        "CRITICAL OUTPUT RULES — you MUST follow these exactly or your response will be rejected:\n\n"
        "Return a JSON object with a single key 'blocks' containing an array of block objects. "
        "Every block object MUST have a 'type' field and the corresponding required fields listed below. "
        "NEVER leave required fields as null or empty — always provide real content.\n\n"
        "Block types and their REQUIRED fields:\n\n"
        "1. heading  — REQUIRED: 'content' (non-empty string with the section title), 'level' (1=main title, 2=section, 3=sub-section)\n"
        '   Example: {"type": "heading", "content": "Introduction to Variables", "level": 1}\n\n'
        "2. paragraph — REQUIRED: 'content' (non-empty string with prose explanation)\n"
        '   Example: {"type": "paragraph", "content": "A variable is a named storage location..."}\n\n'
        "3. code — REQUIRED: 'content' (the raw code or command, no markdown fences), 'language' (e.g. 'python', 'javascript', 'bash', 'sql', 'dockerfile', 'yaml', 'text'). WARNING: NEVER use this for diagrams or charts — use the diagram block instead.\n"
        '   Example: {"type": "code", "language": "python", "content": "x = 10\\nprint(x)"}\n\n'
        "4. bullet_list — REQUIRED: 'items' (non-empty array of strings)\n"
        '   Example: {"type": "bullet_list", "items": ["First point", "Second point"]}\n\n'
        "5. numbered_list — REQUIRED: 'items' (non-empty array of strings in order)\n"
        '   Example: {"type": "numbered_list", "items": ["Step one", "Step two"]}\n\n'
        "6. table — REQUIRED: 'headers' (non-empty array of column names), 'rows' (non-empty 2D array, each row has same length as headers)\n"
        '   Example: {"type": "table", "headers": ["Term", "Meaning"], "rows": [["API", "Application Programming Interface"]]}\n\n'
        "7. note — REQUIRED: 'content' (non-empty string with the tip, warning, or callout)\n"
        '   Example: {"type": "note", "content": "Always close your database connections."}\n\n'
        "8. quote — REQUIRED: 'content' (non-empty string with the memorable statement)\n"
        '   Example: {"type": "quote", "content": "Clean code always looks like it was written by someone who cares."}\n\n'
        "9. divider — No additional fields needed.\n"
        '   Example: {"type": "divider"}\n\n'
        "10. diagram — REQUIRED: 'content' (valid Mermaid diagram syntax), 'format' must be 'mermaid'. Use this for ALL charts, flowcharts, pie charts, sequence diagrams, timelines, and relationship diagrams — NEVER a code block.\n"
        '    Example (flowchart): {"type": "diagram", "format": "mermaid", "content": "graph TD\\n  A[Start] --> B[End]"}\n'
        '    Example (pie chart): {"type": "diagram", "format": "mermaid", "content": "pie title Market Share\\n  \\"Apple\\" : 40\\n  \\"Samsung\\" : 30\\n  \\"Others\\" : 30"}\n\n'
        "Additional rules:\n"
        "- NEVER put code inside a paragraph block — always use a code block\n"
        "- NEVER omit the 'content' field for heading, paragraph, code, note, quote, or diagram blocks\n"
        "- NEVER omit the 'items' field for bullet_list or numbered_list blocks\n"
        "- For ANY chart, flowchart, sequence diagram, pie chart, timeline, or relationship diagram — ALWAYS use a 'diagram' block with format 'mermaid'. NEVER use a code block for diagrams.\n"
        "- In mermaid diagram content: (a) node labels inside [], (), {} must be plain words — NO colons, slashes, ampersands, or special characters; (b) edge labels go BEFORE the destination node: WRONG 'A --> B[Node] |label|', RIGHT 'A -->|label| B[Node]'; (c) every [ must have a matching ]. Example of correct syntax: 'A[Start] -->|goes to| B[End]'.\n"
        "- Make all examples relevant to the given skill and topic\n"
        f"- Write {block_count} blocks covering the topic. {depth_instruction}\n"
        "- Every code block must be complete and accurate — no placeholders or pseudocode\n"
        "- ALWAYS end the chapter with these two blocks in order: "
        "(1) a 'heading' block with level=2 and content='Key Takeaways', "
        "(2) a 'bullet_list' block with 4-6 concise points summarising what the reader learned\n\n"
        f"{style_rules}"
    )

def system_prompt_html() -> str:
    """Prompt for legacy HTML chapter generation (bulk path)."""
    return (
        "You are a senior educator, expert in the subject being taught, and skilled blog writer. "
        "Write a detailed, beginner-friendly blog explaining the concept or task described. "
        "Focus on practical explanation, step-by-step instructions, examples, and insights. "
        "Return the response as clean HTML content with no CSS or extra metadata. "
        "While taking examples, make them relevant to the given skill and industry."
    )

def user_prompt(task_title: str, skill: str, task_description: str) -> str:
    return (
        f"Write a detailed chapter about: {task_title}\n"
        f"Skill: {skill}\n"
        f"Task description: {task_description}"
    )
