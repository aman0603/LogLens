"""Cloud embedding client backed by Gemini (OpenAI-compatible endpoint).

Replaces the local sentence-transformers model with a single ``embed`` /
``embed_batch`` interface so services share one thin client.
"""

import os
from typing import List

try:
    from openai import OpenAI

    _HAVE_OPENAI = True
except ImportError:
    _HAVE_OPENAI = False

DEFAULT_MODEL = "text-embedding-004"
EMBEDDING_DIM = 768

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not _HAVE_OPENAI:
        raise RuntimeError("openai package is required for cloud embeddings")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY env var is required for cloud embeddings")
    base_url = os.getenv(
        "EMBEDDING_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    _client = OpenAI(api_key=api_key, base_url=base_url)
    return _client


def embed(text: str, model: str = DEFAULT_MODEL) -> List[float]:
    """Return the embedding vector for a single text."""
    client = _get_client()
    resp = client.embeddings.create(input=text, model=model)
    return resp.data[0].embedding


def embed_batch(texts: List[str], model: str = DEFAULT_MODEL) -> List[List[float]]:
    """Return embedding vectors for a list of texts."""
    client = _get_client()
    resp = client.embeddings.create(input=texts, model=model)
    return [item.embedding for item in resp.data]
