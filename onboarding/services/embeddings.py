"""Embed text locally with a small ONNX sentence-transformer (fastembed).

Runs on CPU with no API key and no network at inference time — the model is
downloaded once on first use and cached on disk. Vectors are
config.EMBEDDING_DIMENSIONS wide to match the document_chunks pgvector column.
Resumability lives in the ingestion job (which chunks are already embedded),
not here.
"""

import logging
from typing import List, Optional

from fastembed import TextEmbedding

import config

logger = logging.getLogger(__name__)

_model: Optional[TextEmbedding] = None

def _get_model() -> TextEmbedding:
    """Lazily load and cache the embedding model (first call downloads it)."""
    global _model
    if _model is None:
        logger.info("Loading embedding model %s", config.EMBEDDING_MODEL)
        _model = TextEmbedding(model_name=config.EMBEDDING_MODEL)
    return _model

def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts. Returns one vector per input text, in order."""
    if not texts:
        return []
    return [vector.tolist() for vector in _get_model().embed(texts)]

def embed_query(text: str) -> List[float]:
    """Embed a single query string for retrieval."""
    return embed_texts([text])[0]
