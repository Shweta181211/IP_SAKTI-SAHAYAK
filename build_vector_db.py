#!/usr/bin/env python3
"""Embed RAG chunks and persist them in a local ChromaDB collection."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

COLLECTION_NAME = "ip_sakti_corpus"
# bge-m3 is the preferred model. E5 base is used here by default because its
# download/runtime footprint is much more practical on a laptop while still
# supporting English, Hindi, and many other languages.
DEFAULT_MODEL = "intfloat/multilingual-e5-base"


def metadata_for(chunk: dict) -> dict:
    """Keep Chroma-compatible scalar metadata; text and ID are stored separately."""
    keys = ("doc_id", "file_name", "folder", "act_name", "regime_type", "act_subtype",
            "jurisdiction", "year", "section_or_clause", "page_number", "token_count")
    metadata = {key: chunk.get(key) if chunk.get(key) is not None else "" for key in keys}
    # Chroma accepts primitive types only. page_number/token_count are safe ints.
    return metadata


def embedding_inputs(texts: list[str], model_name: str) -> list[str]:
    """E5 was trained with explicit passage/query prefixes; passages use this one."""
    return [f"passage: {text}" for text in texts] if "e5" in model_name.lower() else texts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # The repository ships the extracted corpus at the project root.  Keeping
    # this default aligned with the documented quick-start means a newcomer
    # can run `python build_vector_db.py` without first discovering a stale
    # pipeline-output path from an earlier project layout.
    parser.add_argument("--chunks", type=Path, default=Path("all_chunks.json"))
    parser.add_argument("--db-dir", type=Path, default=Path("vector_db"))
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Hugging Face SentenceTransformer model")
    parser.add_argument("--batch-size", type=int, default=48)
    parser.add_argument("--rebuild", action="store_true", help="Delete and recreate an existing database")
    args = parser.parse_args()

    if not args.chunks.is_file():
        parser.error(
            f"Chunks file not found: {args.chunks}. "
            "Expected all_chunks.json in the repository root; run "
            "build_chunks.py first only if you intentionally replaced the corpus."
        )
    chunks = json.loads(args.chunks.read_text(encoding="utf-8"))
    valid = [chunk for chunk in chunks if str(chunk.get("chunk_text", "")).strip() and len(str(chunk["chunk_text"]).split()) >= 3]
    skipped = len(chunks) - len(valid)
    if skipped:
        print(f"WARNING: skipped {skipped} empty/very short chunks.")

    # Do not silently re-embed thousands of chunks. --rebuild is deliberate.
    if args.db_dir.exists() and args.rebuild:
        shutil.rmtree(args.db_dir)
        print(f"Removed existing database: {args.db_dir}")
    client = chromadb.PersistentClient(path=str(args.db_dir))
    existing = client.get_or_create_collection(COLLECTION_NAME, metadata={"model_name": args.model})
    if existing.count() > 0:
        print(f"Database already contains {existing.count()} chunks at {args.db_dir}. Use --rebuild to regenerate it.")
        return 0

    print(f"Loading multilingual model: {args.model}")
    model = SentenceTransformer(args.model)
    start = time.perf_counter()
    total = len(valid)
    for start_index in range(0, total, args.batch_size):
        batch = valid[start_index:start_index + args.batch_size]
        texts = [str(item["chunk_text"]) for item in batch]
        # normalize_embeddings=True gives cosine similarity through L2 distance.
        embeddings = model.encode(embedding_inputs(texts, args.model), batch_size=args.batch_size,
                                  normalize_embeddings=True, show_progress_bar=False).tolist()
        existing.add(ids=[item["chunk_id"] for item in batch], documents=texts,
                     embeddings=embeddings, metadatas=[metadata_for(item) for item in batch])
        print(f"Embedded {min(start_index + len(batch), total)}/{total} chunks")

    elapsed = time.perf_counter() - start
    size_mb = sum(path.stat().st_size for path in args.db_dir.rglob("*") if path.is_file()) / 1024**2
    print(f"\nDone: {existing.count()} chunks embedded in {elapsed:.1f}s")
    print(f"Collection: {COLLECTION_NAME} | model: {args.model} | disk: {size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
