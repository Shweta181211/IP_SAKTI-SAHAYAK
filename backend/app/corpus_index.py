"""Corpus access: chunk lookup, the Chroma collection, and the BM25 index.

Everything here is loaded once per process and cached. The FastAPI lifespan hook
should call `warm_up()` at startup so the first user query does not pay the
model-load cost.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Chunk store
# --------------------------------------------------------------------------

@lru_cache(maxsize=1)
def all_chunks() -> list[dict[str, Any]]:
    return json.loads(settings.chunks_path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def chunks_by_id() -> dict[str, dict[str, Any]]:
    """All corpus chunks keyed by chunk_id. Loaded once, cached for the process."""
    return {c["chunk_id"]: c for c in all_chunks()}


def get_chunk(chunk_id: str) -> dict[str, Any] | None:
    """Return a chunk, or None if the id does not exist in the corpus.

    This is the primitive the anti-hallucination rule is built on: any citation
    the model produces must resolve through here or it is discarded.
    """
    return chunks_by_id().get(chunk_id)


def chunk_exists(chunk_id: str) -> bool:
    return chunk_id in chunks_by_id()


def excerpt(chunk_id: str, limit: int = 900) -> str:
    """Whitespace-normalised chunk text, truncated for prompt inclusion."""
    chunk = get_chunk(chunk_id)
    if chunk is None:
        return ""
    return " ".join(str(chunk["chunk_text"]).split())[:limit]


# --------------------------------------------------------------------------
# Lexical index (BM25)
# --------------------------------------------------------------------------

# Legal text lives or dies on tokens like "3(p)", "122-E", "Rule 41". A plain
# \w+ tokenizer shreds those into meaningless pieces, so we keep the compound
# form AND its parts - the compound gives precision, the parts give recall.
_TOKEN = re.compile(r"[a-z0-9]+(?:[-(][a-z0-9]+\)?)*")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _TOKEN.finditer(text.lower()):
        token = match.group(0)
        tokens.append(token)
        if not token.isalnum():
            tokens.extend(part for part in re.split(r"[-()]+", token) if part)
    return tokens


@lru_cache(maxsize=1)
def bm25_index():
    """BM25 over the same chunk set as the vector store, in the same order."""
    from rank_bm25 import BM25Okapi

    chunks = all_chunks()
    corpus = [tokenize(str(c["chunk_text"])) for c in chunks]
    logger.info("Building BM25 index over %d chunks", len(corpus))
    return BM25Okapi(corpus), [c["chunk_id"] for c in chunks]


# --------------------------------------------------------------------------
# Dense index (ChromaDB + sentence-transformers)
# --------------------------------------------------------------------------

@lru_cache(maxsize=1)
def collection():
    import chromadb

    if not settings.vector_db_dir.exists():
        raise RuntimeError(
            f"No vector DB at {settings.vector_db_dir}. "
            "Run: python pipeline/build_vector_db.py"
        )
    client = chromadb.PersistentClient(path=str(settings.vector_db_dir))
    return client.get_collection(settings.collection_name)


@lru_cache(maxsize=1)
def embedder():
    from sentence_transformers import SentenceTransformer

    logger.info("Loading embedding model %s", settings.embed_model)
    return SentenceTransformer(settings.embed_model)


def embed_query(text: str) -> list[list[float]]:
    """E5 was trained with an explicit query prefix.

    Omitting it does not error - it silently degrades ranking, which is worse.
    """
    prefixed = f"query: {text}" if "e5" in settings.embed_model.lower() else text
    return embedder().encode([prefixed], normalize_embeddings=True).tolist()


def warm_up() -> dict[str, Any]:
    """Load every index up front. Returns a small health summary."""
    chunk_count = len(all_chunks())
    col = collection()
    bm25_index()
    embedder()
    return {
        "chunks_in_json": chunk_count,
        "chunks_in_vector_db": col.count(),
        "collection": settings.collection_name,
        "embed_model": settings.embed_model,
    }
