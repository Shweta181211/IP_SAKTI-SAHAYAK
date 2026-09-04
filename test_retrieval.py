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
# common Hindi legal terms. It is deliberately visible and easy to extend --
# add a new mapping here rather than hiding it in a model. Grouped by regime
# so the corpus's actual sections (IP statutes, biodiversity/ABS, drug &
# cosmetic regulation, formulation categories) all get Hindi coverage, not
# just the two or three terms a demo query happens to use.
HINDI_LEGAL_TERMS = {
    # --- Patents ---
    "पेटेंट": "patent", "आविष्कार": "invention", "आविष्कारशील कदम": "inventive step",
    "नवीनता": "novelty", "पूर्व कला": "prior art", "पेटेंट आवेदन": "patent application",
    "विशिष्टता": "specification", "दावा": "claim", "पेटेंट योग्यता": "patentability",
    "पेटेंट उल्लंघन": "patent infringement",
    # --- Trademarks ---
    "ट्रेडमार्क": "trademark trade mark", "व्यापार चिह्न": "trade mark",
    "पंजीकरण": "registration", "नवीनीकरण": "renewal", "विरोध": "opposition",
    # --- Geographical Indications ---
    "भौगोलिक संकेत": "geographical indication GI", "जीआई": "geographical indication GI",
    # --- Copyright / Designs / Plant Variety ---
    "कॉपीराइट": "copyright", "प्रतिलिप्याधिकार": "copyright", "डिज़ाइन": "design",
    "पादप किस्म": "plant variety", "किसान अधिकार": "farmers rights",
    # --- Traditional knowledge / biodiversity / ABS ---
    "पारंपरिक ज्ञान": "traditional knowledge", "जैव विविधता": "biological diversity",
    "जैविक संसाधन": "biological resource", "आनुवंशिक संसाधन": "genetic resource",
    "राष्ट्रीय जैव विविधता प्राधिकरण": "National Biodiversity Authority NBA",
    "राज्य जैव विविधता बोर्ड": "State Biodiversity Board",
    "पहुँच एवं लाभ साझाकरण": "access and benefit sharing ABS",
    "लाभ साझाकरण": "benefit sharing", "जैव-चोरी": "biopiracy", "जैव चोरी": "biopiracy",
    "निर्यात": "export", "खेती": "cultivation", "जंगली संग्रहण": "wild collection",
    "टीकेडीएल": "TKDL Traditional Knowledge Digital Library",
    # --- Drugs, cosmetics, food ---
    "औषधि": "drug medicine", "दवा": "drug medicine", "सौंदर्य प्रसाधन": "cosmetic",
    "लाइसेंस": "licence license", "अनुज्ञप्ति": "licence",
    "शास्त्रीय": "classical", "स्वामित्व": "proprietary", "मालिकाना": "proprietary",
    "क्लिनिकल परीक्षण": "clinical trial", "सुरक्षा": "safety", "प्रभावशीलता": "efficacy",
    "खाद्य": "food", "स्वास्थ्य दावा": "health claim", "लेबलिंग": "labelling",
    # --- General procedural terms ---
    "आवेदन": "application", "प्रमाणपत्र": "certificate", "अनुमति": "approval permission",
    "उल्लंघन": "infringement", "आयुर्वेदिक": "Ayurvedic", "उत्पाद": "product",
}


def query_input(query: str, model_name: str) -> str:
    expansion = " ".join(english for hindi, english in HINDI_LEGAL_TERMS.items() if hindi in query)
    enriched = f"{query} {expansion}".strip()
    return f"query: {enriched}" if "e5" in model_name.lower() else enriched


# Domain terms (English and Hindi) that route a query to the right
# act_subtype when the caller hasn't already narrowed it via the formulation
# category. Order matters only in that the first match wins; keep entries
# specific enough that they rarely collide.
_SUBTYPE_ROUTING_TERMS: list[tuple[tuple[str, ...], str]] = [
    (("trademark", "trade mark", "ट्रेडमार्क", "व्यापार चिह्न"), "trademark"),
    (("geographical indication", " gi ", "gi registration", "भौगोलिक संकेत", "जीआई"), "geographical_indication"),
    (("copyright", "कॉपीराइट", "प्रतिलिप्याधिकार"), "copyright"),
    (("plant variety", "farmers right", "पादप किस्म", "किसान अधिकार"), "plant_varieties"),
    (("design registration", "industrial design", "डिज़ाइन"), "design"),
    (("tkdl", "traditional knowledge", "पारंपरिक ज्ञान", "टीकेडीएल"), "traditional_knowledge"),
    (("nba", "biodiversity", "biological resource", "access and benefit", "abs ",
      "जैव विविधता", "जैविक संसाधन", "आनुवंशिक संसाधन", "पहुँच एवं लाभ साझाकरण"), "biodiversity_abs"),
    (("patent", "पेटेंट"), "patent"),
]


def _route_act_subtype(query: str) -> str | None:
    lowered = f" {query.lower()} "
    for terms, subtype in _SUBTYPE_ROUTING_TERMS:
        if any(term in lowered or term in query for term in terms):
            return subtype
    return None


def search(collection, model, model_name: str, query: str, regime_type: str | None = None,
           jurisdiction: str | None = None, act_subtype: str | None = None, top_k: int = 5) -> list[dict]:
    """Reusable semantic search with optional Chroma metadata filters."""
    # A clear domain term can route retrieval to its legal source without
    # replacing semantic ranking inside that source. This is especially useful
    # when a Hindi query targets English-language legislation.
    if act_subtype is None:
        act_subtype = _route_act_subtype(query)
    filters = {key: value for key, value in {"regime_type": regime_type, "jurisdiction": jurisdiction,
                                              "act_subtype": act_subtype}.items() if value}
    where = None if not filters else filters if len(filters) == 1 else {
        "$and": [{key: value} for key, value in filters.items()]
    }
    embedding = model.encode([query_input(query, model_name)], normalize_embeddings=True).tolist()
    result = collection.query(query_embeddings=embedding, n_results=top_k,
                              where=where, include=["documents", "metadatas", "distances"])
    raw = [{"chunk_id": result["ids"][0][i], "text": result["documents"][0][i],
            "metadata": result["metadatas"][0][i], "distance": result["distances"][0][i]}
           for i in range(len(result["ids"][0]))]
    return _dedupe(raw)


def _dedupe(results: list[dict]) -> list[dict]:
    """Drop near-duplicate chunks (same Act + section + page) so the top-k
    isn't padded with repeats of the same clause, which was crowding out
    genuinely different sources in the citation list."""
    seen = set()
    deduped = []
    for item in results:
        meta = item["metadata"]
        key = (meta.get("act_name"), meta.get("section_or_clause"), meta.get("page_number"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


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
    parser.add_argument("--db-dir", type=Path, default=Path("vector_db"))
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
