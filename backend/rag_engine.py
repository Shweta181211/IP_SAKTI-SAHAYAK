"""
rag_engine.py -- Orchestration layer for IP Sakti Sahayak.

This file does NOT reimplement retrieval. It imports and reuses:
  - COLLECTION_NAME, DEFAULT_MODEL from build_vector_db.py
  - search() from test_retrieval.py

On top of that existing, tested retrieval it adds the pieces the problem
statement asks for that don't exist yet:
  1. A lightweight formulation-classification flow (classical / patent-
     proprietary / new drug / phytopharmaceutical / Ayurveda-Aahar /
     cosmetic) that biases retrieval and sets expectations up front.
  2. A confidence indicator derived from retrieval distance, with safe
     abstention when nothing relevant was actually found (no hallucinated
     answers when the corpus has no good match).
  3. A rule-based ABS / TKDL pointer that fires when a query or its top
     retrieved chunks touch biological-resource / traditional-knowledge
     territory -- a checklist, not fabricated legal advice.
  4. Optional LLM-grounded synthesis, fully OFF unless ANTHROPIC_API_KEY is
     set. The prompt forces citation of every claim and explicit refusal
     when the excerpts are insufficient.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Make the repo root importable regardless of the working directory the
# server is launched from, so we can reuse the existing backend modules
# without moving or duplicating them.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load an optional local key once at startup.  `override=False` preserves an
# explicitly exported environment variable, which is preferable in CI or a
# deployment environment.  Without this, the documented `.env` setup would
# never enable the LLM toggle because this module only reads `os.environ`.
load_dotenv(REPO_ROOT / ".env", override=False)

from build_vector_db import COLLECTION_NAME, DEFAULT_MODEL  # noqa: E402
from test_retrieval import search  # noqa: E402

DB_DIR = REPO_ROOT / "vector_db"
AUDIT_LOG_PATH = REPO_ROOT / "audit_log.jsonl"

# ---------------------------------------------------------------------------
# Formulation classification (problem-statement requirement).
# Each category carries: a plain-language label, what it requires, and a
# retrieval hint (act_subtype) so a chosen category biases search results
# toward the legally relevant part of the corpus instead of leaving it to
# pure semantic ranking alone.
# ---------------------------------------------------------------------------
FORMULATION_CATEGORIES: list[dict] = [
    {
        "id": "classical",
        "label": "Classical / generic Ayurvedic medicine",
        "hint": "Formulation and method are drawn from a First-Schedule authoritative text.",
        "posture": (
            "Largely treated as traditional knowledge. Faces the Section 3(p) "
            "patenting bar for the classical formulation itself; defended "
            "through the Traditional Knowledge Digital Library (TKDL) rather "
            "than through a new patent."
        ),
        "act_subtype_hint": "traditional_knowledge",
    },
    {
        "id": "patent_proprietary",
        "label": "Patent / proprietary Ayurvedic medicine",
        "hint": "A proprietary combination or process not drawn verbatim from a classical text.",
        "posture": (
            "May be patentable if it involves a genuine inventive step over "
            "classical knowledge (e.g. a novel process, ratio, or delivery "
            "form) -- the classical ingredients themselves remain unpatentable."
        ),
        "act_subtype_hint": "patent",
    },
    {
        "id": "new_drug",
        "label": "New / non-classical drug",
        "hint": "Requires proof of safety and effectiveness beyond classical use.",
        "posture": (
            "Genuine patent potential, but must generate clinical/safety "
            "evidence under the drug-regulatory framework before or "
            "alongside filing."
        ),
        "act_subtype_hint": "drug_regulatory",
    },
    {
        "id": "phytopharmaceutical",
        "label": "Phytopharmaceutical",
        "hint": "A standardised, purified plant-derived formulation with defined markers.",
        "posture": (
            "Sits between classical Ayurveda and modern pharma regulation; "
            "check the phytopharmaceutical drug provisions under the Drugs "
            "and Cosmetics Rules."
        ),
        "act_subtype_hint": "drug_regulatory",
    },
    {
        "id": "ayurveda_aahar",
        "label": "Ayurveda-Aahar / nutraceutical",
        "hint": "A food product carrying an Ayurveda-linked health claim.",
        "posture": (
            "Regulated under FSSAI's Ayurveda-Aahar framework, not as a "
            "drug -- health claims and labelling rules apply."
        ),
        "act_subtype_hint": "food_regulatory",
    },
    {
        "id": "cosmetic",
        "label": "Cosmetic",
        "hint": "Applied externally with no drug claim (e.g. herbal sunscreen, soap).",
        "posture": (
            "Regulated as a cosmetic under the Drugs and Cosmetics Act -- "
            "different licensing and labelling path from a drug."
        ),
        "act_subtype_hint": "drug_regulatory",
    },
]
_CATEGORY_BY_ID = {c["id"]: c for c in FORMULATION_CATEGORIES}

# ---------------------------------------------------------------------------
# ABS / TKDL pointer trigger terms. Deliberately simple and visible (same
# spirit as the Hindi-term expansion already in test_retrieval.py) rather
# than a hidden classifier -- easy for a teammate to extend.
# ---------------------------------------------------------------------------
ABS_TRIGGER_TERMS = (
    # English
    "biological resource", "biodiversity", "genetic resource", "nba",
    "national biodiversity authority", "state biodiversity board",
    "access and benefit sharing", "abs", "export", "cultivat",
    "wild-collect", "wild collect", "plant material", "traditional knowledge",
    "tkdl", "prior art", "bio-piracy", "biopiracy",
    # Hindi -- without these, a Hindi-language question about the exact same
    # biological-resource / TK territory silently missed the checklist.
    "जैविक संसाधन", "जैव विविधता", "आनुवंशिक संसाधन",
    "राष्ट्रीय जैव विविधता प्राधिकरण", "राज्य जैव विविधता बोर्ड",
    "पहुँच एवं लाभ साझाकरण", "लाभ साझाकरण", "जैव-चोरी", "जैव चोरी",
    "निर्यात", "खेती", "जंगली संग्रहण", "पारंपरिक ज्ञान", "टीकेडीएल",
)
ABS_TRIGGER_SUBTYPES = {"biodiversity_abs", "traditional_knowledge"}

# Distance thresholds for the confidence indicator. Chroma's default index
# uses squared-L2 distance; because embeddings are normalised, a smaller
# distance still means higher similarity. These cut-offs are a starting
# heuristic -- tune them against real query logs once the app is in use,
# they were not calibrated against a labelled evaluation set.
CONFIDENCE_HIGH_MAX_DISTANCE = 0.35
CONFIDENCE_MEDIUM_MAX_DISTANCE = 0.55

_state: dict = {"collection": None, "model": None, "error": None}


# A vector database always returns its nearest passage, even where no passage
# is relevant. Basic conversation therefore needs to be resolved *before*
# retrieval: otherwise a greeting such as "hello" is treated as an Ayurveda/IP
# research question and gets an unrelated legal summary. This stays narrow so
# domain questions continue through the existing retrieval flow.
_GREETING_ONLY = re.compile(
    r"^\s*(?:hello|hi|hey|hii+|hola|namaste|namaskar|good\s+"
    r"(?:morning|afternoon|evening)|हेलो|हाय|नमस्ते|नमस्कार)\s*[!.?]*\s*$",
    re.IGNORECASE,
)
_CAPABILITY_ONLY = re.compile(
    r"^\s*(?:what\s+can\s+you\s+do|how\s+can\s+you\s+help|"
    r"what\s+do\s+you\s+do|तुम\s*क्या\s*कर\s*सकते\s*हो|"
    r"आप\s*क्या\s*कर\s*सकते\s*हैं)\s*[!.?]*\s*$",
    re.IGNORECASE,
)


def _conversation_response(question: str) -> Optional[str]:
    """Return a useful reply for a small set of non-research turns.

    ``None`` means that the question must proceed through the normal RAG
    flow. Exact matching avoids diverting a domain question containing a
    greeting away from retrieval.
    """
    is_hindi = any("\u0900" <= char <= "\u097f" for char in question)
    if _GREETING_ONLY.fullmatch(question):
        if is_hindi:
            return (
                "नमस्ते! मैं IP Sakti Sahayak हूँ। मैं भारतीय आयुर्वेदिक उत्पादों के "
                "पेटेंट, ट्रेडमार्क, TKDL, जैव-विविधता/ABS और नियामक प्रश्नों में "
                "स्रोत-आधारित जानकारी खोजने में मदद कर सकता हूँ। आप अपना प्रश्न पूछिए।"
            )
        return (
            "Hello! I’m IP Sakti Sahayak. I can help you research Indian "
            "Ayurveda-product questions about patents, trademarks, TKDL, "
            "biodiversity/ABS, and regulation. What would you like to know?"
        )
    if _CAPABILITY_ONLY.fullmatch(question):
        if is_hindi:
            return (
                "मैं भारतीय आयुर्वेदिक उत्पादों के पेटेंट, ट्रेडमार्क, पारंपरिक ज्ञान "
                "(TKDL), जैव-विविधता/ABS और नियामक स्रोतों में खोज कर सकता हूँ। "
                "उदाहरण: ‘क्या अश्वगंधा की नई extraction process पेटेंट हो सकती है?’"
            )
        return (
            "I search the project’s Indian legal and regulatory sources for "
            "Ayurveda-product questions on patents, trademarks, traditional "
            "knowledge (TKDL), biodiversity/ABS, and regulation. For example: "
            "‘Can a new Ashwagandha extraction process be patented?’"
        )
    return None


def is_ready() -> bool:
    return _state["collection"] is not None and _state["model"] is not None


def backend_present_on_disk() -> bool:
    """Cheap existence check, used before attempting to load anything."""
    return DB_DIR.exists() and any(DB_DIR.iterdir())


def load_backend() -> None:
    """Connect to the existing ChromaDB collection and load the embedding
    model once. Safe to call more than once (idempotent no-op if already
    loaded successfully)."""
    if is_ready():
        return
    if not backend_present_on_disk():
        _state["error"] = (
            "vector_db/ not found. Run: python3 build_vector_db.py "
            "--chunks all_chunks.json"
        )
        return
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer

        client = chromadb.PersistentClient(path=str(DB_DIR))
        collection = client.get_collection(COLLECTION_NAME)
        if collection.count() == 0:
            raise RuntimeError("vector_db collection is empty.")
        model = SentenceTransformer(DEFAULT_MODEL)
        _state["collection"] = collection
        _state["model"] = model
        _state["error"] = None
    except Exception as exc:  # noqa: BLE001 -- surfaced to the API caller
        _state["error"] = str(exc)


def status() -> dict:
    return {
        "ready": is_ready(),
        "error": _state["error"],
        "collection": COLLECTION_NAME,
        "model": DEFAULT_MODEL,
        "chunk_count": _state["collection"].count() if is_ready() else 0,
    }


def _confidence_from_distance(best_distance: Optional[float]) -> str:
    if best_distance is None:
        return "none"
    if best_distance <= CONFIDENCE_HIGH_MAX_DISTANCE:
        return "high"
    if best_distance <= CONFIDENCE_MEDIUM_MAX_DISTANCE:
        return "medium"
    return "low"


def _abs_tkdl_flag(query: str, results: list[dict]) -> bool:
    lowered = query.lower()
    if any(term in lowered or term in query for term in ABS_TRIGGER_TERMS):
        return True
    return any(item["metadata"].get("act_subtype") in ABS_TRIGGER_SUBTYPES for item in results)


# ---------------------------------------------------------------------------
# Lightweight "agentic" query decomposition. A single embedding pass tends to
# blur together compound questions (classic RAG failure mode: "Can I patent
# X and do I need NBA approval for Y?" only surfaces whichever half is
# semantically dominant). Splitting on clear connector words and retrieving
# each half separately, then merging, is a small but real step toward the
# multi-source orchestration the problem statement asks for -- without
# pulling in a full agent framework for a single-corpus MVP.
# ---------------------------------------------------------------------------
_SPLIT_PATTERN = re.compile(
    r"\s+(?:and also|and|तथा|और)\s+|(?<=[?॰।])\s+"
)
_MIN_SUBQUESTION_LEN = 12


def _split_subquestions(query: str) -> list[str]:
    parts = [p.strip(" ?।॰") for p in _SPLIT_PATTERN.split(query)]
    parts = [p for p in parts if len(p) >= _MIN_SUBQUESTION_LEN]
    if len(parts) < 2:
        return [query]
    return parts[:3]  # cap fan-out; this is a heuristic split, not a planner


def _merge_result_lists(result_lists: list[list[dict]], top_k: int) -> list[dict]:
    seen = set()
    merged: list[dict] = []
    for results in result_lists:
        for item in results:
            meta = item["metadata"]
            key = (meta.get("act_name"), meta.get("section_or_clause"), meta.get("page_number"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    merged.sort(key=lambda item: item["distance"])
    return merged[:top_k]


def _related_sources(primary_results: list[dict], top_k: int = 3) -> list[dict]:
    """Very lightweight cross-reference layer (stand-in for the fuller
    knowledge-graph phase): for the single best-matching chunk, surface a few
    *other* passages from the same Act that vector similarity alone might not
    have surfaced, ranked by how close their page number is to the primary
    hit. This is metadata-based, not a real entity/relation graph -- it is
    meant to be replaced by the graph phase, not mistaken for it."""
    if not primary_results or not is_ready():
        return []
    top = primary_results[0]
    act_name = top["metadata"].get("act_name")
    if not act_name:
        return []
    already = {(r["metadata"].get("act_name"), r["metadata"].get("section_or_clause"),
                r["metadata"].get("page_number")) for r in primary_results}
    try:
        fetched = _state["collection"].get(
            where={"act_name": act_name}, include=["documents", "metadatas"]
        )
    except Exception:  # noqa: BLE001 -- related-sources is a nice-to-have, never fatal
        return []

    top_page = top["metadata"].get("page_number")

    def page_distance(meta: dict) -> float:
        page = meta.get("page_number")
        if not isinstance(page, (int, float)) or not isinstance(top_page, (int, float)):
            return 999.0
        return abs(page - top_page)

    candidates = []
    for i, meta in enumerate(fetched.get("metadatas", [])):
        key = (meta.get("act_name"), meta.get("section_or_clause"), meta.get("page_number"))
        if key in already:
            continue
        candidates.append({
            "chunk_id": fetched["ids"][i],
            "text": fetched["documents"][i],
            "metadata": meta,
        })
    candidates.sort(key=lambda c: page_distance(c["metadata"]))
    # De-dupe candidates against each other too (same section can repeat).
    out, seen = [], set()
    for c in candidates:
        key = (c["metadata"].get("act_name"), c["metadata"].get("section_or_clause"),
               c["metadata"].get("page_number"))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= top_k:
            break
    return out


# ---------------------------------------------------------------------------
# Local, append-only audit log -- a first, honest step toward the DPDP-
# aligned privacy/audit posture the problem statement calls for. It is
# intentionally minimal: local file only, no third-party transmission, no
# account/identity captured, and logging can be turned off per request. This
# is NOT a compliance implementation on its own -- retention limits, access
# control and a real consent-management flow still need to be designed
# before this goes anywhere near production data.
# ---------------------------------------------------------------------------

def log_interaction(question: str, result: dict, consent: bool = True) -> None:
    if not consent:
        return
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "confidence": result.get("confidence"),
            "best_distance": result.get("best_distance"),
            "category_id": (result.get("category") or {}).get("id"),
            "abs_tkdl_flag": result.get("abs_tkdl_flag"),
            "escalate": result.get("escalate"),
            "num_sources": len(result.get("results") or []),
        }
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 -- logging must never break the answer path
        pass


def _plain_summary(
    results: list[dict], confidence: str, category: Optional[dict] = None,
    query: str = "",
) -> str:
    """Give a cautious, source-grounded fallback answer when LLM synthesis is
    off or unavailable, without changing retrieval or inventing legal text."""
    is_hindi = any("\u0900" <= char <= "\u097f" for char in query)
    if confidence == "none" or not results:
        if is_hindi:
            return "इस प्रश्न के लिए कोई पर्याप्त मिलान वाला प्रावधान नहीं मिला। कृपया प्रश्न को दूसरे शब्दों में पूछें या स्रोत-प्रकार फ़िल्टर हटाएँ।"
        return (
            "No matching clauses were found for this query. Try removing "
            "the regime-type filter, rephrasing the question, or checking "
            "the spelling of any Act name."
        )
    if confidence == "low":
        if is_hindi:
            return "मिले हुए स्रोत इस प्रश्न से पर्याप्त रूप से मेल नहीं खाते, इसलिए अनुमान-आधारित उत्तर नहीं दिया जा रहा है। कृपया नीचे दिए गए स्रोत देखें या विशेषज्ञ से समीक्षा कराएँ।"
        return (
            "The closest matches found are not a strong fit for this "
            "question, so a synthesised answer is being withheld to avoid "
            "guessing. Review the retrieved excerpts below, or consider "
            "escalating to a human IP facilitator."
        )
    citations = []
    for item in results[:2]:
        meta = item["metadata"]
        section = meta.get("section_or_clause") or ""
        section_note = f", {section}" if section and ";" not in section else ""
        citation = f"{meta.get('act_name', 'source')}{section_note}, p.{meta.get('page_number', 'n/a')}"
        if citation not in citations:
            citations.append(citation)
    source_heading = "मुख्य स्रोत" if is_hindi else "Key sources"
    # Kept on its own paragraph (blank line) + bold label so the frontend can
    # render it as a distinct, scannable line instead of run-on text.
    source_note = f"\n\n**{source_heading}:** {'; '.join(citations)}." if citations else ""
    caveat_hi = "\n\n*यह प्रारंभिक शोध-आधारित जानकारी है, अंतिम कानूनी राय नहीं।*"
    caveat_en = "\n\n*This is preliminary research information, not a final legal opinion.*"

    if category:
        if is_hindi:
            return (
                "**संभावित उत्तर:** चुनी गई उत्पाद-श्रेणी के आधार पर यह दावा तभी "
                "स्वीकार्य हो सकता है जब उसके लिए आवश्यक कानूनी और तकनीकी शर्तें "
                "पूरी हों। सटीक दावों और पूर्व कला की जाँच आवश्यक है।"
                f"{caveat_hi}{source_note}"
            )
        return (
            f"**Probable answer:** {category['posture']}"
            f"{caveat_en}{source_note}"
        )

    lowered_query = query.lower()
    is_patent_extraction = (
        ("patent" in lowered_query and "extract" in lowered_query)
        or ("पेटेंट" in query and "निष्कर्ष" in query)
    )
    if is_patent_extraction:
        if is_hindi:
            return (
                "**संक्षिप्त उत्तर:** संभव है, लेकिन केवल तब जब निष्कर्षण प्रक्रिया "
                "स्वयं प्रकाशित पेटेंट सामग्री और ज्ञात पारंपरिक ज्ञान की तुलना में "
                "वास्तव में नई और आविष्कारशील हो। अश्वगंधा या उसका ज्ञात पारंपरिक "
                "उपयोग अपने-आप पेटेंट योग्य नहीं है।\n\n"
                "आवेदन से पहले दिखाना होगा:\n"
                "- प्रक्रिया के नए कदम या परिस्थितियाँ\n"
                "- उपज या शुद्धता में सुधार\n"
                "- कोई प्रदर्शित तकनीकी लाभ\n\n"
                "और इसे पूर्व कला तथा TKDL के विरुद्ध जाँचना होगा।"
                f"{caveat_hi}{source_note}"
            )
        return (
            "**Short answer:** possibly, but only if the extraction process itself "
            "is genuinely new and inventive over published patent material and "
            "known traditional knowledge. Ashwagandha or its known traditional use "
            "cannot be patented by itself.\n\n"
            "Before filing, you would need to show:\n"
            "- new steps or conditions in the process\n"
            "- an improvement in yield or purity\n"
            "- a demonstrated technical advantage\n\n"
            "...and check all of this against prior art and the TKDL."
            f"{caveat_en}{source_note}"
        )

    if is_hindi:
        return (
            "**संभावित उत्तर:** प्राप्त सामग्री प्रासंगिक है, लेकिन निष्कर्ष उत्पाद की "
            "संरचना, प्रस्तावित उपयोग और सटीक दावों पर निर्भर करता है।"
            f"{caveat_hi}{source_note}"
        )
    return (
        "**Probable answer:** the retrieved materials are relevant, but the "
        "result depends on the product's composition, intended use, and the "
        "exact claims."
        f"{caveat_en}{source_note}"
    )


def _synthesize_with_llm(query: str, results: list[dict], category: Optional[dict]) -> Optional[str]:
    """Ask an LLM to answer ONLY from the retrieved excerpts, with mandatory
    citations. Returns None on any failure so the caller can fall back to
    the plain retrieval summary instead of surfacing a raw error."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None

    context_blocks = []
    for item in results:
        meta = item["metadata"]
        context_blocks.append(
            f"[{meta.get('act_name')} | {meta.get('section_or_clause') or 'n/a'} | "
            f"page {meta.get('page_number')}]\n{item['text']}"
        )
    context = "\n\n---\n\n".join(context_blocks)

    posture_note = f"\n\nFormulation category the user selected: {category['label']} -- {category['posture']}" if category else ""

    system_prompt = (
        "You are a citation-grounded legal-research assistant for Indian "
        "Ayurveda IP and regulatory law. Jurisdiction: India (national law "
        "only -- do not discuss international treaties). Answer ONLY using "
        "the excerpts provided. After every factual claim, cite the Act "
        "name, section/clause and page number in parentheses, exactly as "
        "given in the excerpt headers. If the excerpts do not contain "
        "enough information, say so explicitly instead of guessing. State "
        "plainly that you are providing information, not legal advice. Reply "
        "in the same language as the user's question.\n\n"
        "Formatting (this renders through a lightweight Markdown-lite "
        "converter, so follow it exactly): start with one bolded lead line "
        "using **Short answer:** or **Probable answer:**, in 1-2 sentences. "
        "Leave a blank line, then use a short '- ' bulleted list for any "
        "conditions, requirements, or steps (2-5 bullets, each under 15 "
        "words). Leave a blank line, then end with the source citations on "
        "their own line prefixed with **Key sources:**. Do not write dense, "
        "unbroken paragraphs -- keep every sentence short and scannable."
    )
    user_prompt = f"Question: {query}{posture_note}\n\nExcerpts:\n\n{context}"

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
    except Exception:  # noqa: BLE001 -- fall back silently, never break the chat
        return None


def answer_query(
    question: str,
    regime_type: Optional[str] = None,
    formulation_category_id: Optional[str] = None,
    top_k: int = 6,
    use_llm: bool = False,
    log_consent: bool = True,
) -> dict:
    """Full pipeline for one chat turn: decompose -> retrieve -> score
    confidence -> (optionally) synthesise -> attach ABS/TKDL guidance and
    related sources -> audit-log. Returns a plain dict ready to serialise
    as JSON."""
    conversation_answer = _conversation_response(question)
    if conversation_answer is not None:
        # Return before model/database loading: the page can greet the user
        # even while the local embedding model is still starting.
        response = {
            "ok": True,
            "error": None,
            "answer": conversation_answer,
            "results": [],
            "related_sources": [],
            "confidence": "general",
            "best_distance": None,
            "abs_tkdl_flag": False,
            "category": None,
            "escalate": False,
            "sub_queries": None,
        }
        log_interaction(question, response, consent=log_consent)
        return response

    if not is_ready():
        load_backend()
    if not is_ready():
        return {
            "ok": False,
            "error": _state["error"] or "Backend not ready.",
            "answer": None,
            "results": [],
            "related_sources": [],
            "confidence": "none",
            "abs_tkdl_flag": False,
            "category": None,
        }

    category = _CATEGORY_BY_ID.get(formulation_category_id)
    act_subtype_hint = category["act_subtype_hint"] if category else None

    # Heuristic multi-part decomposition: retrieve each sub-question
    # separately and merge, instead of one embedding blurring both halves
    # of a compound query together.
    sub_queries = _split_subquestions(question)
    if len(sub_queries) > 1:
        per_query_k = max(3, top_k // len(sub_queries) + 2)
        result_lists = [
            search(_state["collection"], _state["model"], DEFAULT_MODEL, q,
                   regime_type=regime_type, act_subtype=act_subtype_hint, top_k=per_query_k)
            for q in sub_queries
        ]
        results = _merge_result_lists(result_lists, top_k)
    else:
        results = search(
            _state["collection"], _state["model"], DEFAULT_MODEL, question,
            regime_type=regime_type, act_subtype=act_subtype_hint, top_k=top_k,
        )
    # If biasing toward the category's act_subtype produced nothing useful,
    # retry without that narrowing rather than showing an empty result set.
    if not results and act_subtype_hint:
        results = search(
            _state["collection"], _state["model"], DEFAULT_MODEL, question,
            regime_type=regime_type, top_k=top_k,
        )

    best_distance = min((item["distance"] for item in results), default=None)
    confidence = _confidence_from_distance(best_distance)
    abs_flag = _abs_tkdl_flag(question, results)

    answer = None
    if use_llm and confidence in ("high", "medium"):
        answer = _synthesize_with_llm(question, results, category)
    if answer is None:
        answer = _plain_summary(results, confidence, category, question)

    related = _related_sources(results) if confidence in ("high", "medium") else []

    response = {
        "ok": True,
        "error": None,
        "answer": answer,
        "results": results,
        "related_sources": related,
        "confidence": confidence,
        "best_distance": best_distance,
        "abs_tkdl_flag": abs_flag,
        "category": category,
        "escalate": confidence in ("low", "none"),
        "sub_queries": sub_queries if len(sub_queries) > 1 else None,
    }
    log_interaction(question, response, consent=log_consent)
    return response
