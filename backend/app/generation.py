"""Answer generation: the 4-step reasoning trail, with citations enforced.

The problem statement's grading criteria are answer accuracy, citation
correctness and safe abstention. Citation correctness is not something you can
ask a model for politely and hope; it has to be structurally impossible to get
wrong. So there are three layers:

1. **Grounded prompting** - the model sees only retrieved evidence and is told
   to cite by chunk id and to abstain when the evidence runs out.
2. **Post-generation validation** - every id it returns is checked against the
   ids actually retrieved for this question. An id that was not retrieved is
   *rejected*, not warned about, even if it happens to be a real chunk.
3. **Forced abstention** - a step that ends up with no valid citation has its
   content replaced. An unsourced legal assertion never reaches the user.

Rejected ids are reported in the response rather than silently dropped, because
a visible guard is more trustworthy than an invisible one.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from .citations import citations_for, strip_chunk_ids, validate_ids
from .conversation import EXAMPLE_QUESTIONS, conversational_reply
from .classification import classify
from .confidence import assess as assess_confidence
from .escalation import assess as assess_escalation
from .config import settings
from .llm import LLMUnavailable, complete_json
from .retrieval import RetrievalResult, expand_query, is_too_vague, retrieve
from .schemas import (
    CONFIDENCE_LABELS,
    STEP_TITLES,
    STEPS_REQUIRING_CITATION,
    AbstentionKind,
    Answer,
    Category,
    ClassificationResult,
    ReasoningStep,
)

logger = logging.getLogger(__name__)

CONTEXTUALISE_PROMPT = """Rewrite a follow-up message into a question that stands on its own.

A user is having a conversation about Indian law on Ayurveda. Their latest message may rely on what was said before - "what about trademarking it?", "and internationally?", "so how do I protect it then?". Retrieval sees only one question at a time, so such a message must be made self-contained first.

Rules:
- Carry forward the subject (the product, the formulation, the right being discussed).
- Keep the user's actual intent. Do not answer it, expand its scope, or add legal terms of art that the user did not imply.
- If the latest message is ALREADY self-contained, or changes the subject entirely, return it unchanged. Not every message is a follow-up.

Earlier questions in this conversation, oldest first:
{history}

Latest message: {question}

Return ONLY JSON: {{"standalone": "<the self-contained question>"}}"""


def contextualise(question: str, history: list[str]) -> str:
    """Resolve a follow-up into a standalone question.

    Returns the original question unchanged when there is no history, or when
    anything goes wrong - a degraded rewrite is worse than none.
    """
    if not history:
        return question

    numbered = "\n".join(f"{i}. {q}" for i, q in enumerate(history[-4:], 1))
    try:
        data = complete_json(
            CONTEXTUALISE_PROMPT.format(history=numbered, question=question),
            max_tokens=250,
        )
    except LLMUnavailable as exc:
        logger.warning("Contextualisation unavailable (%s); using question as typed", exc)
        return question

    standalone = str(data.get("standalone") or "").strip()
    # Guard against the model returning something empty or absurdly long.
    if not standalone or len(standalone) > 600:
        return question
    if standalone != question:
        logger.info("Follow-up resolved: %r -> %r", question[:60], standalone[:80])
    return standalone


# A small answer cache. Generation costs three sequential model round trips on a
# free endpoint, so a repeated question is 20 seconds of dead air for no new
# information. Bounded and in-process: it is a latency fix, not storage.
_CACHE: "OrderedDict[tuple[str, int], Answer]" = OrderedDict()
_CACHE_LOCK = threading.Lock()
CACHE_SIZE = 64


def _cache_key(question: str, top_k: int) -> tuple[str, int]:
    return (" ".join(question.lower().split()), top_k)


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()

ANSWER_PROMPT = """You are an assistant for Indian law on Ayurveda: intellectual property, \
drug regulation, biodiversity/ABS and pharmacopoeial standards. You give information, never \
legal advice.

Answer STRICTLY from the numbered evidence below. You have no other knowledge of the law. \
If the evidence does not support something, say so - do not fill the gap from memory.

## Evidence

{evidence}

## Product classification already determined

{classification}

## The user's question

{question}

## What to produce

A four-step reasoning trail. Each step is short - two to four sentences of plain language, \
no legal jargon left unexplained.

1. **Classification** - what kind of product or question this is, and why it matters here.
2. **Legal position** - what the law actually says, from the evidence.
3. **Protection / action route** - what the user can concretely do: which route, register, \
authority or defensive mechanism applies.
4. **Jurisdiction note** - state that this answers the position under **Indian law only**, \
and that international regimes are outside this corpus.

## Rules that are not negotiable

- `citation_ids` may contain ONLY ids that appear in the evidence above, exactly as written. \
Never invent an id. Never cite an id you were not shown.
- Every factual claim about the law must be backed by an id you cite on that step.
- If the evidence cannot support a step, set `"abstained": true`, leave `citation_ids` empty, \
and say plainly what is missing. This is a correct answer, not a failure.
- **If the question assumes something the evidence contradicts, correct the premise.** Say \
what the law actually provides and cite it. Do not accept a false premise to be agreeable.
- Steps 1-3 must cite. Step 4 is a statement about scope, so it needs no citation.
- `headline_citation_ids` must contain the id(s) the headline itself rests on. The headline is the one sentence the user reads first, so it is held to the same standard as a step: if no evidence directly supports it, return an empty list rather than citing something loosely related.
- When a piece of evidence carries a provision number, **name it in the sentence** ("under Section 3(p)...", "Rule 122-E provides..."). A reader should be able to see which provision a claim rests on without cross-referencing the source list.
- Do not recommend a lawyer as a substitute for answering; answer what the evidence supports.

## Output

Return ONLY a JSON object, no markdown fence and no commentary:
{{"headline": "<one sentence, max 25 words, answering the question directly>",
 "headline_citation_ids": ["<the id(s) that directly support the headline>"],
 "steps": [
  {{"step": 1, "content": "...", "citation_ids": ["..."], "abstained": false}},
  {{"step": 2, "content": "...", "citation_ids": ["..."], "abstained": false}},
  {{"step": 3, "content": "...", "citation_ids": ["..."], "abstained": false}},
  {{"step": 4, "content": "...", "citation_ids": [], "abstained": false}}
]}}"""


def _evidence_block(result: RetrievalResult, char_limit: int = 1100) -> str:
    parts = []
    for item in result.evidence:
        citation = item.citation
        source = citation.display if citation else item.metadata.get("act_name", "unknown")
        parts.append(f"[{item.chunk_id}] {source}\n{item.text[:char_limit]}")
    return "\n\n".join(parts)


def _classification_block(classification: ClassificationResult) -> str:
    if classification.category is Category.NOT_APPLICABLE:
        return (
            "This question does not concern classifying a specific product. Treat step 1 as "
            "an explanation of what kind of legal question this is instead."
        )
    return (
        f"Category: {classification.label}\n"
        f"Reason: {classification.rationale}\n"
        f"Defined by: {classification.defining_source_name or 'n/a'} "
        f"[{classification.defining_source_id or 'n/a'}]"
    )


def _abstention_answer(
    question: str, kind: AbstentionKind, message: str,
    classification: ClassificationResult | None = None,
    clarifying: str | None = None,
    resolved: str | None = None,
) -> Answer:
    # A refusal is where a human is most likely to be needed - but only for the
    # kinds that reflect a real legal need. escalation.py draws that line.
    escalate, escalation_reason = assess_escalation(True, kind, None)
    return Answer(
        question=question,
        resolved_question=resolved,
        classification=classification,
        abstained=True,
        abstention_kind=kind,
        abstention_message=message,
        clarifying_question=clarifying,
        escalate=escalate,
        escalation_reason=escalation_reason,
        disclaimer=settings.disclaimer,
    )


def _build_steps(raw_steps: list[dict], allowed_ids: list[str]) -> tuple[list[ReasoningStep], list[str]]:
    """Validate model output into steps, rejecting unverifiable citations."""
    by_number = {}
    for raw in raw_steps or []:
        try:
            number = int(raw.get("step", 0))
        except (TypeError, ValueError):
            continue
        if number in STEP_TITLES:
            by_number[number] = raw

    steps: list[ReasoningStep] = []
    all_rejected: list[str] = []

    for number, title in STEP_TITLES.items():
        raw = by_number.get(number, {})
        # Same display-only cleanup the comparison path has always had. Its
        # absence here was an inconsistency, not a decision.
        content = strip_chunk_ids(str(raw.get("content") or ""))
        kept, rejected = validate_ids(raw.get("citation_ids") or [], allowed_ids)
        all_rejected.extend(rejected)
        abstained = bool(raw.get("abstained")) or not content

        # The core rule: an assertion about the law without a surviving citation
        # does not get shown. Step 4 describes scope, so it is exempt.
        if number in STEPS_REQUIRING_CITATION and not kept:
            abstained = True
            content = (
                "The retrieved sources do not support a statement here, so this step is "
                "left unanswered rather than filled in without a citation."
            )

        steps.append(
            ReasoningStep(
                step=number, title=title, content=content,
                citation_ids=kept, abstained=abstained,
            )
        )
    return steps, all_rejected


def answer_question(
    question: str, top_k: int | None = None, history: list[str] | None = None
) -> Answer:
    """Classify, retrieve, generate and validate. The whole core loop."""
    top_k = top_k or settings.top_k

    # Small talk is answered directly. This runs before the vagueness guard,
    # which would otherwise tell someone who typed "hello" that their question
    # was too short to search on.
    small_talk = conversational_reply(question)
    if small_talk is not None:
        return Answer(
            question=question,
            abstained=False,
            abstention_kind=AbstentionKind.CONVERSATIONAL,
            abstention_message=small_talk,
            example_questions=list(EXAMPLE_QUESTIONS),
            disclaimer=settings.disclaimer,
        )

    # Resolve conversational shorthand before anything else: every stage below
    # assumes a question that stands on its own.
    asked = question
    question = contextualise(question, history or [])
    resolved = question if question != asked else None

    key = _cache_key(question, top_k)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            _CACHE.move_to_end(key)
            logger.info("Cache hit for %r", question[:60])
            return cached

    # Bail before spending any API call on a fragment.
    if is_too_vague(question):
        return _abstention_answer(
            asked, AbstentionKind.TOO_VAGUE,
            "That is too short for me to search on. Tell me what the product is, or "
            "which part of the law you are asking about.",
            resolved=resolved,
        )

    # Classification and query expansion both depend only on the question, so
    # running them concurrently removes a whole round trip from every request.
    # On a free model that is several seconds of visible demo latency.
    with ThreadPoolExecutor(max_workers=2) as pool:
        classification_future = pool.submit(classify, question)
        expansion_future = pool.submit(expand_query, question)
        classification = classification_future.result()
        expansion = expansion_future.result()

    # Scope and jurisdiction are settled BEFORE any clarifying question.
    # Order matters: asking "is your product classical or proprietary?" about a
    # question governed by US law wastes the user's turn on a question we were
    # never going to answer. Establish that we can answer at all, then refine.
    category = classification.category if classification.is_formulation else None
    result = retrieve(question, category=category, top_k=top_k, expansion=expansion)

    if not result.sufficient:
        return _abstention_answer(
            asked, result.abstention, result.reason,
            classification=classification, resolved=resolved,
        )

    # In scope, but the product's category is undetermined.
    #
    # This used to stop and ask, which made a real question a dead end - and on
    # a free model the classifier asks inconsistently, so the same question
    # would sometimes answer and sometimes stall. We have retrieved evidence at
    # this point, so the better behaviour is to answer what the evidence
    # supports, tell the model the category is unsettled so it can say where
    # that changes things, and carry the clarifying question alongside the
    # answer rather than instead of it.
    unresolved_category = classification.category is Category.NEEDS_CLARIFICATION

    classification_block = _classification_block(classification)
    if unresolved_category:
        classification_block = (
            "The product's regulatory category could NOT be determined from the question.\n"
            f"The open question is: {classification.clarifying_question}\n\n"
            "Answer what the evidence supports regardless of category, and where the answer "
            "WOULD differ by category, say so explicitly and briefly - name the categories "
            "and how each is treated. Do not pick one silently."
        )

    prompt = ANSWER_PROMPT.format(
        evidence=_evidence_block(result),
        classification=classification_block,
        question=question,
    )
    try:
        data = complete_json(prompt, max_tokens=settings.max_tokens)
    except LLMUnavailable as exc:
        # NOT no_evidence. The corpus may well cover this question perfectly
        # well - we simply could not reach the model. The UI renders
        # `no_evidence` as "nothing here covers that", which told users to
        # rephrase a question that was fine. GATE_UNAVAILABLE says "retry".
        logger.error("Generation failed: %s", exc)
        return _abstention_answer(
            asked, AbstentionKind.GATE_UNAVAILABLE,
            "The answering service is temporarily unavailable. Your question looks fine - "
            "please try it again in a moment.",
            classification=classification, resolved=resolved,
        )

    # The allowed set is "everything we actually showed the model". That includes
    # the classification's defining provision, which appears in the prompt - it
    # was previously rejected as unverifiable purely because it came from the
    # classifier rather than from retrieval.
    allowed = list(result.allowed_ids)
    if classification.defining_source_id and classification.defining_source_id not in allowed:
        allowed.append(classification.defining_source_id)

    steps, rejected = _build_steps(data.get("steps") or [], allowed)
    if rejected:
        logger.warning("Rejected %d unverifiable citation ids: %s", len(rejected), rejected)

    cited: list[str] = []
    for step in steps:
        for cid in step.citation_ids:
            if cid not in cited:
                cited.append(cid)

    # If nothing survived validation, we have no grounded answer to give.
    if not cited:
        return _abstention_answer(
            asked, AbstentionKind.NO_EVIDENCE,
            "I could not ground an answer to this in the corpus, so I am not going to "
            "offer one. Try asking about a specific provision, product type or process.",
            classification=classification, resolved=resolved,
        )

    headline = strip_chunk_ids(" ".join(str(data.get("headline") or "").split())) or None

    # The headline gets the same treatment as a step. It is the sentence users
    # actually read - often the only one - and it was previously the single
    # piece of model prose that reached them with no citation check at all.
    #
    # It is NOT dropped when unsupported: a correct one-line answer is still
    # useful, and the steps beneath it are individually sourced. What matters is
    # that it must not LOOK sourced when it is not, so the flag travels with it
    # and the UI marks it as a summary.
    headline_ids, headline_rejected = validate_ids(
        data.get("headline_citation_ids") or [], allowed
    )
    rejected.extend(headline_rejected)
    if headline and not headline_ids:
        logger.info("Headline carries no verified citation; marking it unsourced")

    # A headline may legitimately rest on a passage no step happened to cite.
    # Those ids still need citation cards, or the UI would point at a source it
    # never renders - the same dangling-reference bug `e2e_api.py` asserts
    # against for steps.
    for cid in headline_ids:
        if cid not in cited:
            cited.append(cid)

    # Scored after validation, from what actually survived - see confidence.py.
    confidence = assess_confidence(steps, cited, rejected, result)

    escalate, escalation_reason = assess_escalation(False, AbstentionKind.NONE, confidence.level)

    answer = Answer(
        question=asked,
        resolved_question=resolved,
        headline=headline,
        headline_citation_ids=headline_ids,
        headline_unsourced=bool(headline) and not headline_ids,
        search_degraded=result.degraded,
        degraded_reason=result.degraded_reason,
        confidence=confidence.level,
        confidence_label=CONFIDENCE_LABELS[confidence.level],
        confidence_score=confidence.score,
        confidence_reasons=confidence.reasons,
        # Surfaced with the answer, not instead of it.
        clarifying_question=classification.clarifying_question if unresolved_category else None,
        classification=classification,
        steps=steps,
        citations=citations_for(cited),
        rejected_citation_ids=rejected,
        escalate=escalate,
        escalation_reason=escalation_reason,
        disclaimer=settings.disclaimer,
    )
    with _CACHE_LOCK:
        _CACHE[key] = answer
        if len(_CACHE) > CACHE_SIZE:
            _CACHE.popitem(last=False)
    return answer
