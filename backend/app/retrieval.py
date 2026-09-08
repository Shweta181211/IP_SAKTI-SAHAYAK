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

# Words that OPEN a question. This is the discriminator that a bare word count
# is not: "What is ABS?" and "patent?" carry the same single content word, and
# only one of them is a question somebody can be answered.
#
# Auxiliaries are included because subject-auxiliary inversion is how English
# asks a yes/no question - "Is a churna patentable?", "Do I need NBA approval?".
_INTERROGATIVE_OPENERS = frozenset("""what which who whom whose when where why how
is are was were do does did can could may might shall should will would must
has have had am
क्या कैसे कब कहाँ कहां क्यों कौन किस""".split())

# The wh-subset, for a question that does not START with one: "GI tag - what is
# it?". Auxiliaries are deliberately excluded here, or a trailing "?" would let
# "patent?" back in through any stray "is" elsewhere in the fragment.
_WH_WORDS = frozenset("""what which who whom whose when where why how
क्या कैसे कब कहाँ कहां क्यों कौन किस""".split())


# Python's `re` counts letters and digits as \w but NOT the combining marks that
# attach to them (Unicode categories Mn/Mc), so an Indic word comes apart:
# "क्या" tokenises as ['क', 'य'] because the virama and the matra between them
# are treated as separators. Every piece is then one character long and dropped
# by the two-character minimum below, so a Hindi question measured as having
# ZERO content words and was refused as too vague - silently, and regardless of
# what it asked. Letting marks attach to their letters fixes that.
#
# English is unaffected: its tokens carry no marks, so "at least two letters or
# digits" is the same test it always was.
_COMBINING_MARKS = (
    "̀-ͯ"  # Latin/Greek/Cyrillic diacritics
    "҃-҉"
    "֑-ׇֽֿׁׂׅׄ"  # Hebrew
    "ؐ-ًؚ-ٰٟۖ-ۜ"  # Arabic
    "ऀ-ःऺ-ॏ॑-ॗॢॣ"  # Devanagari
    "ঁ-ঃ়-্"  # Bengali
    "ਁ-ਃ਼-ੑ"  # Gurmukhi
    "ଁ-ଃ଼-ୗ"  # Odia
    "ஂா-்"  # Tamil
    "ఀ-ఄా-ౖ"  # Telugu
    "ಁ-ಃ಼-್"  # Kannada
    "ഀ-ഃ഻-്"  # Malayalam
)
_WORD_RE = re.compile(rf"[\w{_COMBINING_MARKS}]+", re.UNICODE)


def content_words(question: str) -> list[str]:
    """Topic-bearing words. Unicode-aware, so Hindi and other scripts count.

    A token needs two actual letters or digits to count; the marks ride along
    with the letter they belong to rather than splitting it.
    """
    words = []
    for token in _WORD_RE.findall(question.lower()):
        if sum(ch.isalnum() for ch in token) >= 2 and token not in _STOPWORDS:
            words.append(token)
    return words


def is_question_form(question: str) -> bool:
    """True when the text is shaped like a question, not a bare fragment.

    Two forms count, and a trailing "?" alone deliberately does not: "patent?"
    is punctuation on a keyword, not an enquiry.
    """
    words = re.findall(r"\w+", question.lower(), re.UNICODE)
    if not words:
        return False
    if words[0] in _INTERROGATIVE_OPENERS:
        return True
    return question.rstrip().endswith("?") and any(w in _WH_WORDS for w in words)


def is_too_vague(question: str) -> bool:
    """Cheap deterministic guard for fragments that cannot be retrieved against.

    Running before any LLM call also keeps us inside free-tier request limits.

    The rule this replaced was "fewer than 3 content words", and it refused
    real questions: "What is a Geographical Indication?" survives stop-word
    removal as ['geographical', 'indication'] and "What is ABS?" as ['abs'], so
    both were told to rephrase. Those are among the first things anyone types.

    **Corpus frequency was measured as an alternative discriminator and does not
    work.** The idea was that a specific term is a rare one, but "abs" appears in
    2 of 2,457 chunks (0.08%) and so does "something" - the corpus spells ABS out
    as "Access and Benefit Sharing", so the acronym is as rare as a filler word.
    Rarity cannot tell a precise question from an empty one.

    Sentence form can. What separates the questions that must pass from the
    fragments that must not is whether anything was actually *asked*:

        "What is a Geographical Indication?"  what + 2 content words  -> ask
        "What is ABS?"                        what + 1 content word   -> ask
        "patent?"                             no question frame       -> fragment
        "ayurveda"                            no question frame       -> fragment
        "help with my product"                no question frame       -> fragment
        "tell me about law"                   imperative, not a query -> fragment
        "Why not?"                            asks, but names nothing -> fragment

    So: nothing topic-bearing at all is always too vague (there is nothing to
    search for, whatever the grammar). Three or more content words is never too
    vague, as before. In between - the short, specific question - it comes down
    to whether the user asked something.

    Note the last line above: "Why not?" still refuses here, and should. Turning
    an elliptical follow-up into a standalone question is contextualise()'s job,
    and this guard runs after it precisely so a resolved follow-up is judged on
    its resolved wording.
    """
    content = content_words(question)
    if not content:
        return True
    if len(content) >= MIN_CONTENT_WORDS:
        return False
    return not is_question_form(question)


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


EXPANSION_PROMPT = """Rewrite a user's message into search queries phrased the way an Indian statute or rule would phrase it.

Users write in everyday words ("can my churna be patented?"). Legislation uses different vocabulary for the same idea ("invention which in effect is traditional knowledge or an aggregation of known properties"). Searching the user's words alone therefore misses the governing provision.

**Translate the vocabulary. Never change the question.** Keep the legal issue the user actually raised: asked about patenting, expand toward patentability; about a product name, toward trade marks; about selling or making it, toward licensing, standards and labelling.

**If the message raises no legal issue at all** - many are simply a description of a product - then the question is "what regime governs this product, and what does it require of me?". Expand toward classification, licensing, standards and labelling for that kind of product.

In that case especially, **do not reach for patentability.** It is one regime among many, its vocabulary is the densest in this corpus, and importing it uninvited turns "I have made a neem face cream" into an answer about traditional-knowledge patent exclusions - which is not what was asked and buries the rules that actually apply.

Produce 3 short queries using the statutory concepts and terms of art the message genuinely implicates. Do not answer it. Do not invent section numbers.

MESSAGE: {question}

Return ONLY JSON: {{"queries": ["...", "...", "..."]}}"""


INTL_EXPANSION_PROMPT = """Rewrite a user's message into search queries phrased the way an international treaty or WIPO filing system would phrase it.

Users write in everyday words ("how do I protect my herbal extract abroad?"). The instruments use their own vocabulary: PCT international application and national phase, Madrid Protocol designation, Hague international registration, Nagoya access and benefit-sharing on mutually agreed terms, TRIPS patentable subject matter, GRATK disclosure of the source of genetic resources and associated traditional knowledge.

**Translate the vocabulary. Never change the question.** Keep the legal issue the user actually raised.

**If the message raises no legal issue at all** - many are simply a description of a product - the question is "what do these instruments require of something like this?". Expand toward disclosure obligations, benefit-sharing, and the routes for protecting or registering across borders.

Produce 3 short queries using the treaty concepts the message genuinely implicates. Do not answer it. Do not invent article numbers that were not implied.

MESSAGE: {question}

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


def expand_query(question: str, jurisdiction: str = "national") -> Expansion:
    """Restate the question in statutory vocabulary to bridge the wording gap.

    Returns the original question first, then any expansions, and reports
    whether the expansion step succeeded.
    """
    from .llm import LLMUnavailable, complete_json

    try:
        prompt = (INTL_EXPANSION_PROMPT if jurisdiction == "international"
                  else EXPANSION_PROMPT)
        data = complete_json(prompt.format(question=question), max_tokens=300)
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


def _lexical_candidates(question: str, jurisdiction: str) -> list[tuple[str, float]]:
    """Lexical half of the hybrid, scoped to one jurisdiction.

    The jurisdiction argument is not optional and has no default on purpose:
    the dense half has always filtered, and a lexical half that quietly did not
    is how Indian statutes would end up inside an international answer.
    """
    bm25, ids = bm25_index(jurisdiction)
    if bm25 is None:
        return []
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
        expansion = (expand_query(question, jurisdiction) if expand
                     else Expansion([question]))
    queries = expansion.queries
    if len(queries) > 1:
        logger.info("Expanded query into %d formulations", len(queries))

    # Every formulation contributes its own ranked list; RRF fuses them all.
    # A provision the user's own wording missed can still surface through the
    # statutory rephrasing, which is the entire point of the expansion.
    dense_rank: dict[str, int] = {}
    lexical_rank: dict[str, int] = {}
    fused: dict[str, float] = {}

    # The threshold readings must describe the search that ACTUALLY produced the
    # evidence, which is every formulation fused - not the user's raw wording.
    #
    # They used to be taken from queries[0] alone, and that silently broke short
    # questions whose whole point is that the user's wording is not the corpus's.
    # Measured: "What is ABS?" scores 0.454 on its own wording, one thousandth
    # past MAX_DENSE_DISTANCE, so assess_sufficiency refused it with "no
    # sufficiently related provision was found in the corpus" - while all twelve
    # retrieved chunks were the Biological Diversity Act and the ABS Guidelines.
    # The expansion "Access and benefit sharing" matched at rank 0. Judging the
    # discarded formulation and ignoring the one that worked is backwards.
    for position, q in enumerate(queries):
        dense_hits = _dense_candidates(q, jurisdiction)
        lexical_hits = _lexical_candidates(q, jurisdiction)
        if dense_hits and (not dense or dense_hits[0][1] < dense[0][1]):
            dense = dense_hits
        if lexical_hits and (not lexical or lexical_hits[0][1] > lexical[0][1]):
            lexical = lexical_hits

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
        question, dense_best, lexical_best, evidence,
        use_llm_gate=use_llm_gate, formulations=queries, jurisdiction=jurisdiction,
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

# How many retrieved passages the relevance gate reads. This is the FULL default
# top_k, not a sample: see llm_relevance_gate for the measurement that forced it
# up from 6. Section 6c raised the per-passage window from 320 to 900 characters
# for the same class of reason - a gate that cannot see the governing provision
# refuses things it should allow.
GATE_PASSAGE_WINDOW = 12

# Wording the gate must never put in front of a user. The prompt now forbids
# claims about what the corpus holds, because the model can only see a handful
# of retrieved passages and cannot know. This is the backstop for when it says
# so anyway: measured, it told users "trademark law is not covered by the
# provided corpus" and "the provided corpus contains no provisions regarding
# copyright law" while holding 118 Trade Marks Act and 102 Copyright Act chunks.
#
# A false statement about our own holdings is worse than a vague one: the user
# goes away believing the tool cannot help, and the claim is checkable.
# Deliberately a containment test, not an attempt to parse the negation. A
# reason that genuinely describes the QUESTION - "this is about baking a cake",
# "this asks me to predict the outcome of a lawsuit" - never needs to mention
# our holdings at all. So any mention of them is the tell, whichever way round
# the sentence is turned, and there is no grammar left to get wrong.
_CORPUS_REFERENCES = (
    "corpus",
    "these sources",
    "our sources",
    "the provided source",
    "the provided document",
    "the provided passage",
    "the passages provided",
    "the available source",
    "the database",
)

_SCOPE_FALLBACK = (
    "This question falls outside what these sources can settle. They cover Indian law "
    "on Ayurveda: IP, drug and food regulation, biodiversity and ABS, and "
    "pharmacopoeial standards."
)


def _scope_message(reason: str) -> str:
    """The out-of-scope message, with claims about our own holdings filtered out.

    The gate sees a dozen retrieved passages. It is in no position to say what
    the corpus contains, and when it tried it was wrong in the most damaging
    direction - telling users we hold no trade mark or copyright law while
    holding 118 Trade Marks Act and 102 Copyright Act chunks. Keep its
    reasoning when it describes the question; drop it when it describes us.
    """
    if not reason:
        return _SCOPE_FALLBACK
    lowered = reason.lower()
    if any(term in lowered for term in _CORPUS_REFERENCES):
        logger.warning(
            "Gate reason made a claim about our holdings; substituting: %r", reason
        )
        return _SCOPE_FALLBACK
    return reason


# The corpus this gate is screening against changes with the toggle, so its
# description and its jurisdiction rules are parameters rather than prose. The
# national wording asserted "no international treaty texts", which was true
# until 03_international/ was ingested and would now refuse every treaty
# question the corpus can actually answer.
NATIONAL_SCOPE = """The corpus being searched contains ONLY **Indian** law on Ayurveda: intellectual property (patents, GI, trade marks, copyright, designs, plant varieties), drug and cosmetic regulation, biodiversity/ABS, and pharmacopoeial standards. A separate international corpus exists but is NOT what you are screening against here."""

NATIONAL_JURISDICTION_RULES = """- "india" - governed by Indian law. This is the default: a question with no country mentioned is an Indian question.
- "foreign" - governed by another country's law or by a foreign regulator (for example selling into the USA under FDA rules, or filing in the Japanese patent office). Answering these from Indian statutes would be wrong, so they must be refused.
- "international" - governed by a treaty or multi-country system (PCT, Madrid, Nagoya, TRIPS, WIPO). Those instruments are held in a different corpus, so refuse here and the user can switch.
- "none" - not a legal question at all (a recipe, business advice, small talk). Jurisdiction does not apply."""

INTERNATIONAL_SCOPE = """The corpus being searched contains ONLY **international** instruments: the WTO TRIPS Agreement, the Convention on Biological Diversity and its Nagoya Protocol, WIPO treaties (GRATK, PCT, Madrid, Hague, Budapest) and one foreign regulator's guidance. It holds **no** Indian statute. The user has deliberately asked for the international position, so treaty coverage is what you are screening for."""

INTERNATIONAL_JURISDICTION_RULES = """- "international" - governed by a treaty or multi-country system. This is the DEFAULT here: the user switched to the international corpus on purpose, so a question about patents, trade marks, designs, biodiversity or traditional knowledge is in scope.
- "india" - the question can ONLY be answered by reading Indian domestic law, and the instruments above have nothing to say about it: the wording of a specific Indian provision, an FSSAI licence form, which Indian authority to file with. Say "india" so the user can be sent back to the national corpus.

  Be strict about this: a user who describes their product in Indian terms ("a classical churna from a First Schedule text", "an Ayurvedic proprietary medicine") is describing WHAT they have, not asking what an Indian statute says. If the underlying question - can this be patented, must benefits be shared, can this name be registered - is one these instruments address, that is "international" and you should answer it. The user switched to this corpus deliberately; do not send them back for naming their own product.
- "foreign" - asks about one named country's domestic law that is not covered by the instruments above.
- "none" - not a legal question at all (a recipe, business advice, small talk)."""

RELEVANCE_PROMPT = """Screen a user's question against a legal corpus, on two dimensions.

{corpus_scope}

**1. Jurisdiction.** Which legal system would actually answer this question?
{jurisdiction_rules}

**2. Subject matter.** Do the passages bear on the question at all? This is a scope check, not a completeness check: answer true if any provision is relevant even partially, since a later stage refuses any claim it cannot cite. Answer false only when the question falls outside the corpus's subject matter entirely.

**The passages are a search result, not an inventory of the corpus.** They are the handful of chunks that ranked highest for this one question, drawn from thousands. A body of law being absent from them is NOT evidence that the corpus lacks it - a question about trade marks can easily retrieve mostly drug-regulation passages, because the product words in the question outweigh the legal ones. The corpus's coverage is the list above and that list is authoritative. Judge whether the QUESTION falls inside that subject matter; never conclude from these passages that the corpus does not contain an area of law it says it contains. If the question is in scope but the passages are a poor match, that is still `relevant: true` - the later citation stage refuses anything it cannot source.

**Judge the question as it was searched.** The "SEARCHED AS" lines below are how the question was restated for retrieval, and they are what actually found these passages. Use them to read the question: an acronym or shorthand the user typed ("ABS") may only appear in the passages spelled out ("Access and Benefit Sharing"). They are search vocabulary, not a restatement you may answer instead.

**But the SUBJECT MATTER is the user's question, never the rewrites.** A rewrite is generated to find passages, and it can restate a question that has nothing to do with law in legal words - measured: "what is the best marketing strategy for my ayurvedic startup?" was searched as "compliance standards for advertising and claims of ayurvedic drugs", and the passages that came back were, of course, drug regulation. If the user asked for something this corpus does not do - a marketing plan, a pricing decision, where to find a supplier, how to run a business - it is out of scope however legal the rewrites and the passages look. Ask what the USER wanted to know, and set `jurisdiction` to "none" when the answer is not a legal question at all.

**Passages that CONTRADICT the question are relevant.** A question can assume something the law does not provide - "cite the section that ALLOWS patenting a classical formulation", "which rule exempts me from NBA approval". The correct response is to state what the law actually says and cite it, so `relevant` is **true** whenever the passages settle the point, including when they settle it against the questioner. "There is no such provision, and here is the one that governs instead" is an answer, not a refusal. Answering false here would abstain on precisely the questions where correcting the user matters most.

**3. Advice on the user's own dispute.** Is the user asking you to forecast how their particular case will come out, or to recommend what legal action they should take? Set `personal_advice` true for:
- predicting an outcome - "will I win", "what are my chances in court", "do I have a strong case", "will they succeed against me";
- recommending whether to act - "should I sue them", "should I settle", "is it worth taking them to court".

This is about LEGAL action. A question that is not about law at all - a marketing plan, a pricing decision, where to find a supplier - is not `personal_advice`; set `jurisdiction` to "none" for those instead. Refusing a business question as though it were a lawsuit tells the user the wrong thing about why we cannot help.

Set it **false** for questions about what the law says, however close to a dispute they sit: "what remedies does the Patents Act give for infringement", "what defences are available to an infringement claim", "which court hears patent suits", "what is the limitation period", "what counts as infringement". Stating the law is information and we answer it; forecasting a case applies the law to facts we cannot see, and only a practitioner with the file can do that. Someone in the middle of a dispute is perfectly entitled to ask the first kind of question.

QUESTION: {question}
SEARCHED AS:
{formulations}

PASSAGES:
{passages}

Return ONLY JSON:
{{"jurisdiction": "india" or "foreign" or "international",
  "relevant": true or false,
  "personal_advice": true or false,
  "reason": "<one short sentence about the QUESTION and these passages. Never state what the corpus does or does not contain.>"}}"""



def llm_relevance_gate(
    question: str,
    evidence: list[Evidence],
    formulations: list[str] | None = None,
    jurisdiction: str = "national",
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

    # Every retrieved passage, not the first six. Measured on "Can I trademark
    # the name of my Ayurvedic product?": the Trade Marks Act chunks land at
    # ranks 6 and 8, because "Ayurvedic product" pulls the 949-chunk Drugs and
    # Cosmetics Rules up the list. A six-passage window therefore showed the
    # gate five drug-regulation passages and asked whether the corpus covers
    # trade marks - and it answered, reasonably but wrongly, that it does not.
    # The governing statute has to be inside the window the gate reads.
    passages = "\n\n".join(
        f"[{i}] {e.metadata.get('act_name', '?')}: {e.text[:900]}"
        for i, e in enumerate(evidence[:GATE_PASSAGE_WINDOW], 1)
    )
    # How the question was restated for retrieval. Without this the gate judges
    # wording that never retrieved anything: "What is ABS?" against passages
    # that only ever say "Access and Benefit Sharing".
    searched_as = "\n".join(f"- {q}" for q in (formulations or [question]))
    try:
        data = complete_json(
            RELEVANCE_PROMPT.format(
                question=question,
                formulations=searched_as,
                passages=passages,
                corpus_scope=(INTERNATIONAL_SCOPE if jurisdiction == "international"
                              else NATIONAL_SCOPE),
                jurisdiction_rules=(INTERNATIONAL_JURISDICTION_RULES
                                    if jurisdiction == "international"
                                    else NATIONAL_JURISDICTION_RULES),
            ),
            # Raised from 250: this prompt gained the corpus-scope block, the
            # jurisdiction rules and the SEARCHED AS lines, and models answer a
            # longer prompt with a longer `reason`. Measured: replies were being
            # cut off mid-string, so complete_json could not parse them and a
            # perfectly healthy provider produced gate_unavailable.
            max_tokens=400,
        )
    except LLMUnavailable as exc:
        logger.error("Relevance gate unavailable (%s); refusing rather than guessing", exc)
        return False, (
            "I could not run the scope and jurisdiction check for this question, so I am "
            "not going to answer it. This check is what stops the assistant answering a "
            "question about another country's law from Indian sources. Please try again "
            "in a moment."
        ), AbstentionKind.GATE_UNAVAILABLE

    searching_international = jurisdiction == "international"
    reason = str(data.get("reason") or "").strip()
    verdict = str(data.get("jurisdiction")
                  or ("international" if searching_international else "india")).strip().lower()
    relevant = bool(data.get("relevant"))
    personal_advice = bool(data.get("personal_advice"))

    # Jurisdiction is decided first, but only for questions that are legal at
    # all. "none" is what keeps a chocolate-cake question from being told it is
    # "governed by another country's law", while still letting a US regulatory
    # question be refused for the right reason rather than as mere off-topic.
    # Which verdict means "wrong corpus" depends on which corpus is loaded.
    # Refusing an international question is right when searching Indian statute
    # and wrong when searching the treaties themselves.
    if searching_international:
        if verdict == "india":
            return False, (
                "This asks specifically about Indian domestic law, which is not in the "
                "international corpus. Switch to India and I can answer it from the "
                "Indian statutes."
            ), AbstentionKind.FOREIGN_JURISDICTION
        if verdict == "foreign":
            return False, (
                "This turns on one country's own domestic law, which the international "
                "instruments here do not cover."
            ), AbstentionKind.FOREIGN_JURISDICTION
    else:
        if verdict == "foreign":
            return False, (
                "This question is governed by another country's law. This corpus covers "
                "Indian law only, so answering it from these sources would be misleading."
            ), AbstentionKind.FOREIGN_JURISDICTION
        if verdict == "international":
            return False, (
                "This question turns on an international treaty or filing system. Switch "
                "the jurisdiction toggle to International and I can answer it from the "
                "treaty texts."
            ), AbstentionKind.FOREIGN_JURISDICTION

    # Checked before subject matter, because a question like "will I win my
    # patent suit?" IS on-subject - the Patents Act governs infringement - and
    # would otherwise sail through as relevant. It is the one refusal the
    # evaluation caught the system getting wrong in the dangerous direction:
    # measured on gemini-3.5-flash-lite it answered with litigation procedure
    # and told the user "You may initiate a suit for infringement in a court not
    # inferior to a District Court under Section 104". Every sentence was
    # sourced, and it was still advice on a live dispute.
    #
    # Asking the model this EXPLICITLY is what makes the behaviour survive a
    # model swap. Nothing previously asked it: minimax happened to refuse via
    # `relevant: false` and gemini happened not to, and neither was following an
    # instruction. An unasked question has no defined answer.
    # "none" means this is not a legal question at all - a recipe, a business
    # plan, small talk. It has to be handled BEFORE the advice check, or a
    # question like "what is the best marketing strategy for my startup?" gets
    # refused as if the user had asked about a lawsuit: true that we will not
    # answer it, wrong about why, and the wrong thing to tell them.
    if verdict == "none":
        return False, _scope_message(reason), AbstentionKind.OUT_OF_SCOPE

    if personal_advice:
        return False, (
            "I can tell you what the law says, but not how your own case will turn out or "
            "whether to bring one - that means applying the law to facts and evidence I "
            "cannot see. Ask what the law provides on infringement, remedies, defences or "
            "procedure and I will answer that with citations."
        ), AbstentionKind.LEGAL_ADVICE

    if not relevant:
        return False, _scope_message(reason), AbstentionKind.OUT_OF_SCOPE

    return True, reason or "Evidence addresses the question.", AbstentionKind.NONE


def assess_sufficiency(
    question: str,
    dense_best: float | None,
    lexical_best: float | None,
    evidence: list[Evidence],
    use_llm_gate: bool = True,
    formulations: list[str] | None = None,
    jurisdiction: str = "national",
) -> tuple[bool, str, AbstentionKind]:
    """Decide whether retrieved evidence can support any answer at all."""
    if not evidence:
        return False, "No provisions were retrieved for this question.", AbstentionKind.NO_EVIDENCE

    if dense_best is not None and dense_best > MAX_DENSE_DISTANCE:
        # Phrased about the SEARCH, not the corpus. The old wording - "no
        # sufficiently related provision was found in the corpus" - told the
        # user a fact about our holdings that this check cannot establish: it
        # only knows that nothing matched closely, which is as easily a wording
        # mismatch as an absence.
        return False, ("Nothing in the search came back closely enough related to answer "
                       "this. Try naming the statute, the right, or the product."),               AbstentionKind.OUT_OF_SCOPE

    if not use_llm_gate:
        return True, "Evidence retrieved (relevance gate disabled).", AbstentionKind.NONE

    # NOTE: there is deliberately no "confident distance" fast path any more.
    # Skipping the gate on a tight match also skipped the jurisdiction check,
    # and the USA/FDA question scored 0.2980 - comfortably inside any fast path
    # we would have set. Jurisdiction has to be checked on every question.
    return llm_relevance_gate(question, evidence, formulations, jurisdiction)
