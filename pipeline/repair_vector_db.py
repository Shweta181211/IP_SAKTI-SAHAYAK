#!/usr/bin/env python3
"""Bring the vector DB back in step with all_chunks.json without a full re-embed.

Why this exists
---------------
Adding two PDFs to 03_international shifted `doc_id` for every document that
sorts after them, so 576 ids in the database no longer exist, 200 ids now name
a *different* passage, and 668 new ids have never been embedded. A `--rebuild`
would be correct but re-embeds all 3,275 chunks (~35 min, and it was OOM-killed
three times on this machine).

An embedding is a pure function of the chunk text, so a chunk whose text is
byte-identical does not need re-encoding merely because its neighbours were
renumbered. This script therefore does the minimum that is provably equivalent:

  1. delete ids that are no longer in the corpus
  2. re-embed ids whose stored text no longer matches the corpus
  3. embed ids that are new
  4. refresh metadata wherever it drifted (cheap - no encoding)

and then verifies the whole collection against all_chunks.json, so the outcome
is checked rather than assumed.

Run it in slices with --limit if memory is tight; it is restartable.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import chromadb

ROOT = Path(__file__).resolve().parent.parent
COLLECTION_NAME = "ip_sakti_corpus"
DEFAULT_MODEL = "intfloat/multilingual-e5-base"
MIN_WORDS = 3


def metadata_for(chunk: dict) -> dict:
    """Identical to build_vector_db.metadata_for - keep the two in step."""
    keys = ("doc_id", "file_name", "folder", "act_name", "regime_type", "act_subtype",
            "jurisdiction", "year", "section_or_clause", "page_number", "token_count")
    return {key: chunk.get(key) if chunk.get(key) is not None else "" for key in keys}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=ROOT / "data" / "chunks" / "all_chunks.json")
    parser.add_argument("--db-dir", type=Path, default=ROOT / "data" / "vector_db")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="Embed at most this many chunks this pass.")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    chunks = json.loads(args.chunks.read_text(encoding="utf-8"))
    wanted = {c["chunk_id"]: c for c in chunks if len(str(c["chunk_text"]).split()) >= MIN_WORDS}

    client = chromadb.PersistentClient(path=str(args.db_dir))
    col = client.get_or_create_collection(COLLECTION_NAME, metadata={"model_name": args.model})

    stored = col.get(include=["documents", "metadatas"])
    stale, redo, meta_fix = [], [], []
    for cid, doc, meta in zip(stored["ids"], stored["documents"], stored["metadatas"]):
        want = wanted.get(cid)
        if want is None:
            stale.append(cid)
        elif str(doc).strip() != str(want["chunk_text"]).strip():
            redo.append(cid)
        elif dict(meta) != metadata_for(want):
            meta_fix.append(cid)
    missing = [cid for cid in wanted if cid not in set(stored["ids"])]

    print(f"corpus chunks      : {len(wanted)}")
    print(f"in database        : {len(stored['ids'])}")
    print(f"  delete (stale)   : {len(stale)}")
    print(f"  re-embed (text)  : {len(redo)}")
    print(f"  metadata refresh : {len(meta_fix)}")
    print(f"  embed (new)      : {len(missing)}")

    if args.verify_only:
        return verify(col, wanted)

    if stale:
        for i in range(0, len(stale), 500):
            col.delete(ids=stale[i:i + 500])
        print(f"deleted {len(stale)} stale ids")

    if meta_fix:
        for i in range(0, len(meta_fix), 500):
            batch = meta_fix[i:i + 500]
            col.update(ids=batch, metadatas=[metadata_for(wanted[c]) for c in batch])
        print(f"refreshed metadata on {len(meta_fix)} ids")

    todo = redo + missing
    if args.limit and len(todo) > args.limit:
        todo = todo[:args.limit]
        print(f"limiting this pass to {len(todo)} chunks")

    if todo:
        # Pinned to one thread by default because a full 3,275-chunk pass was
        # OOM-killed three times on this machine. A short top-up pass has room
        # for more, so the ceiling is an env var rather than a constant.
        try:
            import os
            import torch
            torch.set_num_threads(int(os.environ.get("EMBED_THREADS", "1")))
        except Exception:
            pass
        from sentence_transformers import SentenceTransformer

        print(f"loading {args.model}")
        model = SentenceTransformer(args.model)
        prefix = "passage: " if "e5" in args.model.lower() else ""
        start = time.perf_counter()
        for i in range(0, len(todo), args.batch_size):
            batch = [wanted[c] for c in todo[i:i + args.batch_size]]
            texts = [str(c["chunk_text"]) for c in batch]
            vectors = model.encode([prefix + t for t in texts], batch_size=args.batch_size,
                                   normalize_embeddings=True, show_progress_bar=False).tolist()
            col.upsert(ids=[c["chunk_id"] for c in batch], documents=texts,
                       embeddings=vectors, metadatas=[metadata_for(c) for c in batch])
            print(f"embedded {min(i + len(batch), len(todo))}/{len(todo)}", flush=True)
        print(f"embedding pass took {time.perf_counter() - start:.1f}s")

    return verify(col, wanted)


def verify(col, wanted: dict) -> int:
    """Every id, every passage and every metadata field, checked against the corpus."""
    stored = col.get(include=["documents", "metadatas"])
    ids = set(stored["ids"])
    problems = []
    if ids != set(wanted):
        problems.append(f"id set differs: {len(set(wanted) - ids)} missing, {len(ids - set(wanted))} extra")
    for cid, doc, meta in zip(stored["ids"], stored["documents"], stored["metadatas"]):
        want = wanted.get(cid)
        if want is None:
            continue
        if str(doc).strip() != str(want["chunk_text"]).strip():
            problems.append(f"{cid}: text mismatch")
        elif dict(meta) != metadata_for(want):
            problems.append(f"{cid}: metadata mismatch")

    print("\nVERIFY")
    print(f"  collection count : {col.count()}")
    if problems:
        print(f"  PROBLEMS         : {len(problems)}")
        for p in problems[:10]:
            print(f"    - {p}")
        return 1
    by_j: dict[str, int] = {}
    for meta in stored["metadatas"]:
        by_j[meta.get("jurisdiction", "?")] = by_j.get(meta.get("jurisdiction", "?"), 0) + 1
    print(f"  by jurisdiction  : {by_j}")
    print("  every id, passage and metadata field matches all_chunks.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
