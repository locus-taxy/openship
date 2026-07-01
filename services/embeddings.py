"""Embed text with Gemini (text-embedding-004), batched with backoff.

A single server-side key funds these calls (see config.GEMINI_EMBEDDING_API_KEY);
ingestion embeds thousands of chunks, so we batch and back off on rate limits.
Resumability lives in the ingestion job (which chunks are already embedded), not here.
"""

import logging
import time
from typing import List, Optional

from fastapi import HTTPException
from google import genai

import config

logger = logging.getLogger(__name__)

_MAX_RETRIES = 4
_BASE_DELAY_SECONDS = 2.0
_sleep = time.sleep  # module-level so tests can patch it

def _embed_batch(api_key: str, model: str, texts: List[str]) -> List[List[float]]:
    """One embedding API call for a batch of texts."""
    client = genai.Client(api_key=api_key)
    resp = client.models.embed_content(model=model, contents=texts)
    return [list(e.values) for e in resp.embeddings]

def _embed_with_backoff(api_key: str, model: str, batch: List[str]) -> List[List[float]]:
    delay = _BASE_DELAY_SECONDS
    for attempt in range(_MAX_RETRIES):
        try:
            return _embed_batch(api_key, model, batch)
        except Exception:
            if attempt == _MAX_RETRIES - 1:
                logger.exception("Embedding batch failed after %d attempts", _MAX_RETRIES)
                raise HTTPException(status_code=502, detail="Embedding request failed.")
            _sleep(delay)
            delay *= 2

def embed_texts(
    texts: List[str],
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    batch_size: Optional[int] = None,
) -> List[List[float]]:
    """Embed a list of texts, batching to respect rate limits. Returns one
    vector per input text, in order."""
    if not texts:
        return []
    api_key = api_key or config.GEMINI_EMBEDDING_API_KEY
    if not api_key:
        raise HTTPException(status_code=503, detail="Embeddings are not configured on this server.")
    model = model or config.EMBEDDING_MODEL
    batch_size = batch_size or config.EMBEDDING_BATCH_SIZE

    vectors: List[List[float]] = []
    for start in range(0, len(texts), batch_size):
        vectors.extend(_embed_with_backoff(api_key, model, texts[start : start + batch_size]))
    return vectors

def embed_query(
    text: str, *, api_key: Optional[str] = None, model: Optional[str] = None
) -> List[float]:
    """Embed a single query string for retrieval."""
    return embed_texts([text], api_key=api_key, model=model)[0]
