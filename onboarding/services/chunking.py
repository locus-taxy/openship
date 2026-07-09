"""Split page text into overlapping chunks for embedding + retrieval."""

import re

# Rough chars-per-token for English prose; used to size chunks without a tokenizer.
_CHARS_PER_TOKEN = 4
_TARGET_TOKENS = 800
_OVERLAP_TOKENS = 100

def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)

def chunk_text(
    text: str,
    target_tokens: int = _TARGET_TOKENS,
    overlap_tokens: int = _OVERLAP_TOKENS,
) -> list[str]:
    """Return overlapping chunks of roughly `target_tokens` each, breaking on
    whitespace so words aren't split. Empty/short text yields 0 or 1 chunk."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    max_chars = target_tokens * _CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * _CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + max_chars
        if end < len(text):
            space = text.rfind(" ", start, end)
            if space > start:
                end = space
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap_chars)
    return chunks
