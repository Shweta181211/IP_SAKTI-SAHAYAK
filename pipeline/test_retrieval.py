#!/usr/bin/env python3
"""Run multilingual semantic-search sanity checks against the local ChromaDB."""

from __future__ import annotations

import argparse
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from build_vector_db import COLLECTION_NAME, DEFAULT_MODEL

TEST_QUERIES = [
    "Can I patent a new extraction process for Ashwagandha?",
    "Do I need NBA approval to export a herbal cosmetic made from Indian plants?",
    "What protects a traditional Ayurvedic formulation from being patented by someone else?",
    "Is a herbal sunscreen classified as a cosmetic or an Ayurvedic drug in India?",
    "मुझे अपने आयुर्वेदिक उत्पाद का ट्रेडमार्क कैसे कराना है?",
]

# Lightweight query expansion helps English-language legislation respond to
# common Hindi legal terms. It is deliberately visible and easy to extend.
HINDI_LEGAL_TERMS = {
    "ट्रेडमार्क": "trademark trade mark", "पेटेंट": "patent", "आयुर्वेदिक": "Ayurvedic",
    "पारंपरिक ज्ञान": "traditional knowledge", "जैव विविधता": "biological diversity",
}


def query_input(query: str, model_name: str) -> str:
    expansion = " ".join(english for hindi, english in HINDI_LEGAL_TERMS.items() if hindi in query)
    enriched = f"{query} {expansion}".strip()
    return f"query: {enriched}" if "e5" in model_name.lower() else enriched


def search(collection, model, model_name: str, query: str, regime_type: str | None = None,
           jurisdiction: str | None = None, act_subtype: str | None = None, top_k: int = 5) -> list[dict]:
    """Reusable semantic search with optional Chroma metadata filters."""
    # A clear domain term can route retrieval to its legal source without
    # replacing semantic ranking inside that source. This is especially useful
    # when a Hindi query targets English-language legislation.
    if act_subtype is None and ("ट्रेडमार्क" in query or "trademark" in query.lower() or "trade mark" in query.lower()):
        act_subtype = "trademark"
    filters = {key: value for key, value in {"regime_type": regime_type, "jurisdiction": jurisdiction,
                                              "act_subtype": act_subtype}.items() if value}
    where = None if not filters else filters if len(filters) == 1 else {
        "$and": [{key: value} for key, value in filters.items()]
    }
    embedding = model.encode([query_input(query, model_name)], normalize_embeddings=True).tolist()
    result = collection.query(query_embeddings=embedding, n_results=top_k,
                              where=where, include=["documents", "metadatas", "distances"])
    return [{"chunk_id": result["ids"][0][i], "text": result["documents"][0][i],
             "metadata": result["metadatas"][0][i], "distance": result["distances"][0][i]}
            for i in range(len(result["ids"][0]))]


def print_results(label: str, results: list[dict]) -> None:
    print(f"\n{label}")
    for rank, item in enumerate(results, 1):
        meta = item["metadata"]
        preview = " ".join(item["text"].split())[:150]
        print(f"{rank}. {item['chunk_id']} | distance={item['distance']:.4f}")
        print(f"   {meta['act_name']} | {meta.get('section_or_clause') or 'No detected section'} | {meta['regime_type']}")
        print(f"   {preview}...")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-dir", type=Path, default=Path(__file__).resolve().parent.parent / "data" / "vector_db")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    collection = chromadb.PersistentClient(path=str(args.db_dir)).get_collection(COLLECTION_NAME)
    print(f"Loaded {collection.count()} chunks. Model: {args.model}")
    # The model was downloaded during ingestion. Local-only loading avoids an
    # unnecessary network request every time a teammate runs a retrieval test.
    model = SentenceTransformer(args.model, local_files_only=True)
    for query in TEST_QUERIES:
        print_results(f"QUERY: {query}", search(collection, model, args.model, query))
    # Demonstrates metadata-constrained hybrid retrieval for a patent question.
    print_results("FILTERED DEMO (regime_type=ip_statute)", search(
        collection, model, args.model, TEST_QUERIES[0], regime_type="ip_statute"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
