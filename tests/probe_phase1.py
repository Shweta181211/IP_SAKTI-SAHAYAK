#!/usr/bin/env python3
"""Phase 1 verification: does the vector DB actually retrieve the right law?

Two jobs:
  1. Prove the Part F benchmark queries surface their expected statute.
  2. Measure the distance gap between in-corpus and out-of-corpus questions,
     which is what the Phase 3 abstention threshold gets calibrated against.

This is a verification script, not app code. It deliberately does no filtering,
no query rewriting and no keyword routing -- we want to see raw retrieval quality.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

# Legal PDFs carry private-use glyphs (bullets, ligatures) that crash the
# Windows cp1252 console. Never let a display codec abort a verification run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import chromadb
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from build_vector_db import COLLECTION_NAME, DEFAULT_MODEL  # noqa: E402

DB_DIR = ROOT / "data" / "vector_db"

# (label, query, expected_substring_in_act_name_or_None)
# `expected` is a soft assertion: it reports whether the right *source* ranked
# in the top 5, not whether a specific chunk did.
BENCHMARKS = [
    ("F1 official churna",   "Can a classical churna from a First Schedule text be patented?", "patents act"),
    ("F2 GI registration",   "How do I register a Geographical Indication for an Ayurvedic product?", "Geographical Indications"),
    ("F3 ABS / NBA",         "What is Access and Benefit Sharing and when do I need NBA approval?", "Biological Diversity"),
    ("F4 new extract",       "Is my new herbal extract formulation patentable?", None),
    ("F5 phytopharma",       "What counts as a phytopharmaceutical under Indian law?", "Drugs and Cosmetics"),
]

# Unrehearsed. Mix of in-scope-but-not-given, oddly phrased, and out-of-corpus.
OFF_SCRIPT = [
    ("in-scope, unseen",     "Can I trademark the name Chyawanprash?", "Trade Marks"),
    ("oddly phrased",        "my grandmother's herbal oil recipe - can a company steal it and patent it?", None),
    ("adjacent regime",      "Do I need a licence to manufacture an ayurvedic syrup for sale?", None),
    ("OUT: international",   "How do I file a PCT application in Japan?", None),
    ("OUT: off-domain",      "What is the best marketing strategy for my ayurvedic startup?", None),
    ("OUT: nonsense",        "purple bicycle quarterly tax rebate", None),
]

# Chunks we know contain the Section 3(p) traditional-knowledge patent bar.
SECTION_3P_CHUNKS = {"DOC014_chunk_011", "DOC019_chunk_112"}


def embed_query(model, model_name: str, text: str):
    """E5 requires the 'query: ' prefix; omitting it silently degrades ranking."""
    prefixed = f"query: {text}" if "e5" in model_name.lower() else text
    return model.encode([prefixed], normalize_embeddings=True).tolist()


def probe(collection, model, model_name: str, query: str, top_k: int = 5):
    res = collection.query(
        query_embeddings=embed_query(model, model_name, query),
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    return [
        {"id": res["ids"][0][i], "meta": res["metadatas"][0][i],
         "dist": res["distances"][0][i], "text": res["documents"][0][i]}
        for i in range(len(res["ids"][0]))
    ]


def show(label: str, query: str, hits: list[dict], expected: str | None) -> float:
    print(f"\n{'=' * 78}\n{label}\n  Q: {query}")
    if not hits:
        print("  (no results)")
        return 1.0
    for rank, h in enumerate(hits, 1):
        m = h["meta"]
        print(f"  {rank}. d={h['dist']:.4f}  {m['act_name']}  (p{m['page_number']}, {m['act_subtype']})")
        print(f"      {h['id']}  {' '.join(h['text'].split())[:130]}...")
    if expected:
        got = any(expected.lower() in h["meta"]["act_name"].lower() for h in hits)
        print(f"  -> expected source '{expected}' in top 5: {'YES' if got else 'NO  <-- CHECK'}")
    return hits[0]["dist"]


def main() -> int:
    if not DB_DIR.exists():
        print(f"No vector DB at {DB_DIR}. Run: python pipeline/build_vector_db.py")
        return 1

    collection = chromadb.PersistentClient(path=str(DB_DIR)).get_collection(COLLECTION_NAME)
    print(f"Collection '{COLLECTION_NAME}': {collection.count()} chunks")
    model = SentenceTransformer(DEFAULT_MODEL)
    print(f"Model: {DEFAULT_MODEL}")

    print(f"\n\n{'#' * 78}\n# PART F BENCHMARKS\n{'#' * 78}")
    in_corpus = []
    for label, q, exp in BENCHMARKS:
        in_corpus.append(show(label, q, probe(collection, model, DEFAULT_MODEL, q), exp))

    print(f"\n\n{'#' * 78}\n# OFF-SCRIPT / EDGE CASES\n{'#' * 78}")
    out_corpus = []
    for label, q, exp in OFF_SCRIPT:
        d = show(label, q, probe(collection, model, DEFAULT_MODEL, q), exp)
        (out_corpus if label.startswith("OUT:") else in_corpus).append(d)

    # Targeted check: the official benchmark depends on Section 3(p) being findable.
    print(f"\n\n{'#' * 78}\n# SECTION 3(p) TARGETED CHECK\n{'#' * 78}")
    q3p = "invention which is traditional knowledge or aggregation of known properties is not patentable"
    hits = probe(collection, model, DEFAULT_MODEL, q3p, top_k=10)
    show("Section 3(p) direct probe", q3p, hits[:5], "patents act")
    found = SECTION_3P_CHUNKS & {h["id"] for h in hits}
    print(f"  -> known 3(p) chunks in top 10: {sorted(found) if found else 'NONE  <-- CHECK'}")

    print(f"\n\n{'#' * 78}\n# ABSTENTION THRESHOLD CALIBRATION\n{'#' * 78}")
    print(f"  in-corpus  top-1 distances: min={min(in_corpus):.4f} "
          f"median={statistics.median(in_corpus):.4f} max={max(in_corpus):.4f}  (n={len(in_corpus)})")
    print(f"  OUT-of-corpus top-1 distances: min={min(out_corpus):.4f} "
          f"median={statistics.median(out_corpus):.4f} max={max(out_corpus):.4f}  (n={len(out_corpus)})")
    gap = min(out_corpus) - max(in_corpus)
    print(f"  separation between worst in-corpus and best out-of-corpus: {gap:+.4f}")
    print("  -> a clean positive gap means a distance cutoff alone can drive abstention;")
    print("     a negative gap means Phase 3 needs the hybrid/BM25 signal to separate them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
