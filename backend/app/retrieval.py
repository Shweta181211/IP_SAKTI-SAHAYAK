"""Hybrid retrieval: dense vectors + BM25, fused with Reciprocal Rank Fusion.

Why hybrid, concretely. Phase 1 measured dense-only retrieval on this corpus and
found that querying with Section 3(p)'s own near-verbatim text still ranked
Sections 3(o), 3(c), 3(l), 3(e) and 3(f) above it - the Patents Act exclusion
clauses are near-identical in phrasing, so embeddings cannot separate them. The
literal token "3(p)" can. Dense retrieval finds the right *topic*; lexical
retrieval finds the right *provision*. We need both.

Abstention also comes from here. Phase 1 showed a distance cutoff cannot do it:
in-corpus and out-of-corpus top-1 distances overlap (worst in-corpus 0.3598 vs
best out-of-corpus 0.2713), and "purple bicycle quarterly tax rebate" scored
better than several genuine questions. Lexical overlap separates them where
distance does not, so the evidence signal below is built on both.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .citations import build_citation
from .corpus_index import bm25_index, collection, embed_query, get_chunk, tokenize
from .schemas import AbstentionKind, Category, Citation

logger = logging.getLogger(__name__)

# Standard RRF constant. Damps the influence of any single ranker's top hit so
# one confident-but-wrong list cannot dominate the fusion.
RRF_K = 60

# How deep each retriever goes before fusion. Wider than the final top_k so a
# result ranked mediocre by one method can still be rescued by the other.
CANDIDATE_DEPTH = 40

# Categories bias retrieval toward the regimes that actually govern them. This
# is a soft score nudge derived from the *classification result*, never from
# scanning the query for keywords - a hard filter would break unseen questions.
CATEGORY_REGIME_HINTS: dict[Category, tuple[str, ...]] = {
    Category.CLASSICAL_GENERIC: ("traditional_knowledge", "patent"),
    Category.PATENT_PROPRIETARY: ("patent", "drug_regulatory"),
    Category.NEW_DRUG: ("drug_regulatory", "patent"),
    Category.PHYTOPHARMACEUTICAL: ("drug_regulatory",),
    Category.AYURVEDA_AAHAR: ("food_regulatory",),
    Category.COSMETIC: ("drug_regulatory",),
}
# Measured at 0.15 and it pushed the decisive Section 3(p) chunk DOWN a rank on
# the official benchmark, with no observed gain elsewhere. Plumbing kept, boost
# off: an unmeasured tuning knob that hurts the one query we care most about is
# not worth carrying. Raise only with evidence.
REGIME_BOOST = 0.0


# Deliberately tiny: only words so common they carry no topic. Anything longer
# starts silently discarding legal vocabulary.
_STOPWORDS = frozenset("""a an the is are was were be been being do does did can could
may might shall should will would i we you he she it they me my our your this that these
those of in on at to for with by from about into over under and or but if then than as
what which who whom whose when where why how not no need want help please tell explain""".split())

MIN_CONTENT_WORDS = 3


def content_words(question: str) -> list[str]:
    """Topic-bearing words. Unicode-aware, so Hindi and other scripts count."""
    return [w for w in re.findall(r"\w{2,}", question.lower(), re.UNICODE)
            if w not in _STOPWORDS]


def is_too_vague(question: str) -> bool:
    """Cheap deterministic guard for fragments that cannot be retrieved against.

    "patent?", "ayurveda" and "help with my product" all previously sailed
    through and were handed near-arbitrary evidence. Running before any LLM call
    also keeps us inside free-tier request limits.
    """
    return len(content_words(question)) < MIN_CONTENT_WORDS


@dataclass
class Evidence:
    """One retrieved chunk, with everything generation and the UI both need."""

    chunk_id: str
    text: str
    score: float
    dense_rank: int | None = None
    lexical_rank: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def citation(self) -> Citation | None:
        return build_citation(self.chunk_id)


@dataclass
class RetrievalResult:
    evidence: list[Evidence]
    sufficient: bool
    reason: str
    dense_best_distance: float | None
    lexical_best_score: float | None
    abstention: AbstentionKind = AbstentionKind.NONE
    # Carried through from Expansion so the caller can surface it on the answer
    # without needing to know how retrieval was assembled.
    degraded: bool = False
    degraded_reason: str | None = None

    @property
    def allowed_ids(self) -> list[str]:
        """The only chunk ids a generated answer may cite."""
        return [e.chunk_id for e in self.evidence]


EXPANSION_PROMPT = """Rewrite a user's question into search queries phrased the way an Indian statute or rule would phrase it.

Users ask in everyday words ("can my churna be patented?"). Legislation uses different vocabulary for the same idea ("invention which in effect is traditional knowledge or an aggregation of known properties"). Searching the user's words alone therefore misses the governing provision.

Produce 3 short queries using the statutory concepts and terms of art the question implicates. Do not answer the question. Do not invent section numbers.

QUESTION: {question}

Return ONLY JSON: {{"queries": ["...", "...", "..."]}}"""


@dataclass
class Expansion:
    """Query formulations, plus whether producing them actually worked.

    The `ok` flag is the point of this type. Expansion used to fail soft and
    return `[question]`, indistinguishable from a question that simply needed no
    rephrasing - so a rate-limited request quietly searched with half the recall
    it was designed for.

    That is not a cosmetic degradation. Measured on the official benchmark with
    expansion disabled, `DOC020_chunk_116` - the Section 3(p) chunk the whole
    flagship answer rests on - does not appear in the top 12 at all; retrieval
    returns patent-office *procedure* instead. The system still answered, with
    real citations and a confident badge, from the wrong provisions.

    The relevance gate already fails closed for exactly this reason. Expansion
    stays soft, because unlike the jurisdiction check its absence degrades
    recall rather than correctness - but it must be *visible*, so the caller can
    tell the user the search was narrowed.
    """

    queries: list[str]
    ok: bool = True
    reason: str | None = None


def expand_query(question: str) -> Expansion:
    """Restate the question in statutory vocabulary to bridge the wording gap.

    Returns the original question first, then any expansions, and reports
    whether the expansion step succeeded.
    """
    from .llm import LLMUnavailable, complete_json

    try:
        data = complete_json(EXPANSION_PROMPT.format(question=question), max_tokens=300)
    except LLMUnavailable as exc:
        logger.warning("Query expansion unavailable (%s); searching on the question alone", exc)
        return Expansion(
            queries=[question],
            ok=False,
            reason=(
                "The search-expansion step was temporarily unavailable, so this answer was "
                "found using your wording alone. Statutory wording often differs from "
                "everyday wording, so a more directly applicable provision may exist. "
                "Please re-ask in a moment to get the full search."
            ),
        )

    queries = [question]
    for item in (data.get("queries") or [])[:3]:
        text = str(item).strip()
        if text and text.lower() != question.lower():
            queries.append(text)
    return Expansion(queries=queries)


def _dense_candidates(question: str, jurisdiction: str) -> list[tuple[str, float]]:
    result = collection().query(
        query_embeddings=embed_query(question),
        n_results=CANDIDATE_DEPTH,
        where={"jurisdiction": jurisdiction},
        include=["distances"],
    )
    return list(zip(result["ids"][0], result["distances"][0]))


def _lexical_candidates(question: str) -> list[tuple[str, float]]:
    bm25, ids = bm25_index()
    scores = bm25.get_scores(tokenize(question))
    ranked = sorted(zip(ids, scores), key=lambda pair: pair[1], reverse=True)
    return ranked[:CANDIDATE_DEPTH]


def retrieve(
    question: str,
    category: Category | None = None,
    top_k: int = 8,
    jurisdiction: str = "national",
    use_llm_gate: bool = True,
    expand: bool = True,
    expansion: Expansion | None = None,
) -> RetrievalResult:
    """Retrieve evidence for a question, and judge whether it is enough."""
    # Cheapest guard first: a fragment cannot be retrieved against, and bailing
    # here costs no API calls.
    if is_too_vague(question):
        return RetrievalResult(
            [], False,
            "That is too short for me to search on. Tell me what the product is, or "
            "which part of the law you are asking about.",
            None, None, AbstentionKind.TOO_VAGUE,
        )

    dense: list[tuple[str, float]] = []
    lexical: list[tuple[str, float]] = []

    # Callers may pass precomputed expansions (see generation.py, which runs
    # expansion concurrently with classification to save a round trip).
    if expansion is None:
        expansion = expand_query(question) if expand else Expansion([question])
    queries = expansion.queries
    if len(queries) > 1:
        logger.info("Expanded query into %d formulations", len(queries))

    # Every formulation contributes its own ranked list; RRF fuses them all.
    # A provision the user's own wording missed can still surface through the
    # statutory rephrasing, which is the entire point of the expansion.
    dense_rank: dict[str, int] = {}
    lexical_rank: dict[str, int] = {}
    fused: dict[str, float] = {}

    # queries[0] IS the user's question, so searching it separately for the
    # threshold reading and then again inside the loop ran one redundant
    # sentence-transformer encode and one redundant BM25 scan on every request.
    # Compute each formulation once and reuse the first for the thresholds.
    for position, q in enumerate(queries):
        dense_hits = _dense_candidates(q, jurisdiction)
        lexical_hits = _lexical_candidates(q)
        if position == 0:
            dense, lexical = dense_hits, lexical_hits

        for rank, (cid, _) in enumerate(dense_hits):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
            dense_rank[cid] = min(dense_rank.get(cid, rank), rank)
        for rank, (cid, _) in enumerate(lexical_hits):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
            lexical_rank[cid] = min(lexical_rank.get(cid, rank), rank)

    hints = CATEGORY_REGIME_HINTS.get(category, ()) if category else ()
    if hints:
        for cid in list(fused):
            chunk = get_chunk(cid)
            if chunk and chunk.get("act_subtype") in hints:
                fused[cid] *= 1 + REGIME_BOOST

    ordered = sorted(fused.items(), key=lambda pair: pair[1], reverse=True)[:top_k]

    evidence = []
    for cid, score in ordered:
        chunk = get_chunk(cid)
        if chunk is None:
            continue  # vector store and chunk file disagree; trust the chunk file
        evidence.append(
            Evidence(
                chunk_id=cid,
                text=" ".join(str(chunk["chunk_text"]).split()),
                score=score,
                dense_rank=dense_rank.get(cid),
                lexical_rank=lexical_rank.get(cid),
                metadata={k: chunk.get(k) for k in
                          ("act_name", "act_subtype", "regime_type", "page_number")},
            )
        )

    dense_best = dense[0][1] if dense else None
    lexical_best = lexical[0][1] if lexical else None
    sufficient, reason, kind = assess_sufficiency(
        question, dense_best, lexical_best, evidence, use_llm_gate=use_llm_gate
    )
    return RetrievalResult(
        evidence, sufficient, reason, dense_best, lexical_best, kind,
        degraded=not expansion.ok, degraded_reason=expansion.reason,
    )


# Measured in tests/probe_phase3.py. Both signals were tested as abstention
# thresholds and both FAILED, which is why the LLM gate below exists:
#
#   dense distance  in-corpus 0.2469-0.3598 | out-of-corpus 0.3696-0.3951
#   BM25 score      in-corpus 11.21 -31.16  | out-of-corpus 11.95 -26.29
#
# BM25 overlaps badly - "marketing strategy for my ayurvedic startup" scores
# 26.29 because "ayurvedic" is a high-value corpus term, beating several genuine
# questions. Distance separates on this sample by only 0.01, far too thin to
# trust. So thresholds are used only as a loose outer bound and a fast path;
# the real decision is a relevance judgement made with the evidence in view.
MAX_DENSE_DISTANCE = 0.45
CONFIDENT_DISTANCE = 0.30

RELEVANCE_PROMPT = """Screen a user's question against a legal corpus, on two dimensions.

The corpus contains ONLY **Indian** law on Ayurveda: intellectual property (patents, GI, trade marks, copyright, designs, plant varieties), drug and cosmetic regulation, biodiversity/ABS, and pharmacopoeial standards. It holds **no** foreign law and no international treaty texts.

**1. Jurisdiction.** Which legal system would actually answer this question?
- "india" - governed by Indian law. This is the default: a question with no country mentioned is an Indian question.
- "foreign" - governed by another country's law or by a foreign regulator (for example selling into the USA under FDA rules, or filing in the Japanese patent office). Answering these from Indian statutes would be wrong, so they must be refused.
- "international" - governed by a treaty or multi-country system (PCT, Madrid, Nagoya, TRIPS, WIPO). We hold only India's own implementing law, not the treaties themselves.
- "none" - not a legal question at all (a recipe, business advice, small talk). Jurisdiction does not apply.

**2. Subject matter.** Do the passages bear on the question at all? This is a scope check, not a completeness check: answer true if any provision is relevant even partially, since a later stage refuses any claim it cannot cite. Answer false only when the question falls outside the corpus's subject matter entirely.

**Passages that CONTRADICT the question are relevant.** A question can assume something the law does not provide - "cite the section that ALLOWS patenting a classical formulation", "which rule exempts me from NBA approval". The correct response is to state what the law actually says and cite it, so `relevant` is **true** whenever the passages settle the point, including when they settle it against the questioner. "There is no such provision, and here is the one that governs instead" is an answer, not a refusal. Answering false here would abstain on precisely the questions where correcting the user matters most.

QUESTION: {question}

PASSAGES:
{passages}

Return ONLY JSON:
{{"jurisdiction": "india" or "foreign" or "international",
  "relevant": true or false,
  "reason": "<one short sentence>"}}"""



def llm_relevance_gate(
    question: str, evidence: list[Evidence]
) -> tuple[bool, str, AbstentionKind]:
    """Screen for subject matter AND jurisdiction before anything is answered.

    Fails CLOSED on error, deliberately.

    The earlier behaviour let questions through when the gate was unavailable,
    on the reasoning that citation validation downstream still prevents
    fabrication. That is true but insufficient: citation validation cannot tell
    that a question was about US law. During an outage the system would have
    answered a foreign-jurisdiction question from Indian statutes, confidently
    and with real citations - the single worst failure this tool can produce.

    An honest "I could not verify this is in scope" is a worse demo and a better
    legal tool. The user is told the check failed and can retry.
    """
    from .llm import LLMUnavailable, complete_json

    passages = "\n\n".join(
        f"[{i}] {e.metadata.get('act_name', '?')}: {e.text[:900]}"
        for i, e in enumerate(evidence[:6], 1)
    )
    try:
        data = complete_json(
            RELEVANCE_PROMPT.format(question=question, passages=passages), max_tokens=250
        )
    except LLMUnavailable as exc:
        logger.error("Relevance gate unavailable (%s); refusing rather than guessing", exc)
        return False, (
            "I could not run the scope and jurisdiction check for this question, so I am "
            "not going to answer it. This check is what stops the assistant answering a "
            "question about another country's law from Indian sources. Please try again "
            "in a moment."
        ), AbstentionKind.GATE_UNAVAILABLE

    reason = str(data.get("reason") or "").strip()
    jurisdiction = str(data.get("jurisdiction") or "india").strip().lower()
    relevant = bool(data.get("relevant"))

    # Jurisdiction is decided first, but only for questions that are legal at
    # all. "none" is what keeps a chocolate-cake question from being told it is
    # "governed by another country's law", while still letting a US regulatory
    # question be refused for the right reason rather than as mere off-topic.
    if jurisdiction == "foreign":
        return False, (
            "This question is governed by another country's law. This corpus covers "
            "Indian law only, so answering it from these sources would be misleading."
        ), AbstentionKind.FOREIGN_JURISDICTION
    if jurisdiction == "international":
        return False, (
            "This question turns on an international treaty or filing system. The corpus "
            "currently holds Indian law only - international coverage is a later phase. "
            "Ask about the Indian position and I can answer that."
        ), AbstentionKind.FOREIGN_JURISDICTION

    if not relevant:
        return False, reason or (
            "The corpus does not cover this question. It holds Indian law on Ayurveda "
            "IP, drug regulation, biodiversity/ABS and pharmacopoeial standards."
        ), AbstentionKind.OUT_OF_SCOPE

    return True, reason or "Evidence addresses the question.", AbstentionKind.NONE


def assess_sufficiency(
    question: str,
    dense_best: float | None,
    lexical_best: float | None,
    evidence: list[Evidence],
    use_llm_gate: bool = True,
) -> tuple[bool, str, AbstentionKind]:
    """Decide whether retrieved evidence can support any answer at all."""
    if not evidence:
        return False, "No provisions were retrieved for this question.", AbstentionKind.NO_EVIDENCE

    if dense_best is not None and dense_best > MAX_DENSE_DISTANCE:
        return False, ("No sufficiently related provision was found in the corpus."),               AbstentionKind.OUT_OF_SCOPE

    if not use_llm_gate:
        return True, "Evidence retrieved (relevance gate disabled).", AbstentionKind.NONE

    # NOTE: there is deliberately no "confident distance" fast path any more.
    # Skipping the gate on a tight match also skipped the jurisdiction check,
    # and the USA/FDA question scored 0.2980 - comfortably inside any fast path
    # we would have set. Jurisdiction has to be checked on every question.
    return llm_relevance_gate(question, evidence)
