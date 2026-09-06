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

# Repo root is the parent of pipeline/, so defaults resolve from any cwd.
ROOT = Path(__file__).resolve().parent.parent

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
    parser.add_argument("--chunks", type=Path, default=ROOT / "data" / "chunks" / "all_chunks.json")
    parser.add_argument("--db-dir", type=Path, default=ROOT / "data" / "vector_db")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Hugging Face SentenceTransformer model")
    parser.add_argument("--batch-size", type=int, default=48)
    parser.add_argument("--rebuild", action="store_true", help="Delete and recreate an existing database")
    # Embed at most N chunks, then exit cleanly. Combined with the resume
    # logic above this makes the build survive a machine that cannot hold the
    # model and a long-lived process at once: a shell loop calls this
    # repeatedly, and every invocation starts fresh, does a slice of the work
    # and releases all of its memory on exit. Slower per chunk (the model is
    # reloaded each time) and far more likely to finish.
    parser.add_argument("--limit", type=int, default=0,
                        help="Embed at most this many chunks, then exit (0 = all)")
    args = parser.parse_args()

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
    # Resume rather than refuse. Embedding this corpus takes ~30 minutes of CPU,
    # and a machine that runs out of memory half way through used to leave a
    # partial database that was worse than useless: inconsistent with
    # all_chunks.json, and only recoverable by starting again from zero.
    #
    # So an existing database is treated as progress, not as an obstacle. Only
    # the chunks it does not already hold are embedded, which makes the build
    # interruptible and restartable. --rebuild still forces a clean wipe when
    # the chunk ids themselves have changed.
    already = set()
    if existing.count() > 0:
        already = set(existing.get(include=[])["ids"])
        remaining = [c for c in valid if c["chunk_id"] not in already]
        if not remaining:
            print(f"Database already holds all {len(valid)} chunks at {args.db_dir}. "
                  "Nothing to do; use --rebuild to regenerate from scratch.")
            return 0
        print(f"Resuming: {len(already)} of {len(valid)} chunks already embedded, "
              f"{len(remaining)} to go.")
        valid = remaining

    if args.limit and len(valid) > args.limit:
        print(f"Limiting this pass to {args.limit} chunks.")
        valid = valid[:args.limit]

    try:
        import torch
        torch.set_num_threads(1)
    except Exception:
        pass
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
