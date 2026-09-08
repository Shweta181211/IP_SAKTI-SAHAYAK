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
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from .citations import (
    citations_for,
    normalise_institutions,
    strip_chunk_ids,
    strip_unsupported_provisions,
    validate_ids,
)
from .conversation import EXAMPLE_QUESTIONS, conversational_reply
from .classification import classify
from .graph import attach_links as attach_graph_links
from .confidence import assess as assess_confidence
from .escalation import assess as assess_escalation
from .config import active_model, settings
from .llm import LLMUnavailable, complete_json
from .retrieval import RetrievalResult, expand_query, is_too_vague, retrieve
from .schemas import (
    REQUIRES_VERIFICATION,
    TAKEAWAY_LABELS,
    Takeaway,
    TakeawayIntent,
    TraceStep,
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


def _cache_key(question: str, top_k: int, jurisdiction: str) -> tuple[str, int, str]:
    """Cache identity for an answer.

    `jurisdiction` is part of the key, and leaving it out was a real bug: the
    same question asked nationally and then internationally returned the FIRST
    answer both times, so the International toggle would have looked like it was
    working while silently serving Indian law under an international label -
    exactly the conflation the problem statement forbids. The jurisdiction
    suites did not catch it because they clear the cache between runs; the
    comparison feature, which asks both within one request, would have.
    """
    return (" ".join(question.lower().split()), top_k, jurisdiction)


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()

# The corpus that answers changes with the toggle, and step 4 is a statement
# ABOUT that corpus - hard-coding "Indian law only" there made it false in
# international mode, which is exactly the conflation the problem statement
# forbids. Both the framing and the jurisdiction note are parameters.
NATIONAL_FRAMING = """You are an assistant for **Indian** law on Ayurveda: intellectual property, drug regulation, biodiversity/ABS and pharmacopoeial standards. Every passage below is Indian law."""

INTERNATIONAL_FRAMING = """You are an assistant for the **international** instruments bearing on Ayurveda and traditional knowledge: the WTO TRIPS Agreement, the Convention on Biological Diversity and its Nagoya Protocol, and WIPO treaties (GRATK, PCT, Madrid, Hague, Budapest). Every passage below is international instrument text, NOT Indian law.

You have no Indian statute in front of you. Do not state the Indian position, do not name Indian provisions such as Section 3(p) of the Patents Act, and do not say what India specifically requires - even if you happen to know it. Where the honest answer is that these instruments set a framework each state implements in its own law, say exactly that."""

NATIONAL_JURISDICTION_STEP = """state that this answers the position under **Indian law only**, and that the international instruments are a separate corpus the user can switch to"""

INTERNATIONAL_JURISDICTION_STEP = """state that this answers the position under the **international instruments only**, that such instruments bind states rather than applying to a product directly, and that the Indian domestic position is a separate corpus the user can switch to"""

ANSWER_PROMPT = """{framing} You give information, never \
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
2. **Legal position** - what the law actually says about **this** question, from the \
evidence. The classification above names the regime that governs this product; where the user \
has not raised some other issue, that regime's requirements ARE the legal position. Do not \
switch to patentability unless the user asked about patents or protection - a person who says \
"I have made a face cream" is asking what rules apply to selling it, not whether neem is an \
invention.
   **Where the question DOES ask about patenting, protection or IP, order this step so the \
protection position comes first.** Open with whether the product can or cannot be protected and \
under which provision, and only then give any licensing, manufacturing, approval or evidence \
requirements. Those requirements are real and belong in the answer, but they are not the answer \
to "can I patent this?" - a reader who asked about protection and is given three sentences of \
drug-licensing procedure before anything about patentability has not been answered. This is an \
ordering rule, not a filter: nothing is dropped, it is sequenced so the question asked is \
answered first.
3. **Protection / action route** - what the user can concretely do: which route, register, \
authority or defensive mechanism applies. **Before writing that no route exists, re-read the \
evidence for one.** If any passage names a register, registry, database, authority or defensive \
mechanism, name it and say how it applies here. "The evidence provides no route" is correct only \
when the evidence genuinely names none; it is not a way to restate step 2. A bar on one route \
usually implies that a different one is the answer - that different route is what this step is \
for.
4. **Jurisdiction note** - {jurisdiction_step}.

## Getting these three things right

These are errors this assistant has actually made. They are corrections of substance, not style.

- **TKDL is a defensive prior-art resource. It confers no rights whatsoever.** The Traditional Knowledge Digital Library exists so that patent examiners can FIND documented traditional knowledge and REFUSE applications that claim it. Never write that it "protects", "grants protection", "gives international protection", "registers" a formulation, or that someone should file with it to secure rights. Asked what protection it provides, the accurate answer is that it provides none directly - it makes prior art findable so that others cannot validly patent it.

- **There is no institution called the "International Patent Office".** Name a real body when the evidence names one - WIPO, the EPO, the USPTO, the Indian Patent Office - or write "patent offices in other countries" generically. Some source text in this corpus uses the phrase loosely; do not reproduce it in your own words.

- **Section 3(p) is not a blanket bar on everything Ayurvedic.** It bars an invention that IS traditional knowledge, or an aggregation or duplication of known properties of traditionally known components. Three situations are different in law, and you must say which one applies:
  (a) traditional INGREDIENTS used in a genuinely new formulation or process that the applicant devised - **not automatically barred by 3(p)**. It is assessed on its own novelty and inventive step, and against the other exclusions such as 3(d) and 3(e), like any other application.
  (b) a formulation documented in a classical or authoritative text - this is what 3(p) actually bars.
  (c) a new technical process or invention that merely USES traditional-knowledge-derived material - assessed on its own novelty and inventive step, separately from the traditional knowledge it draws on.
  Using a traditional plant does not by itself make an invention traditional knowledge. Do not conclude that no patent route is available merely because an ingredient is traditional; say which of (a), (b) or (c) this is and reason from there.


## The takeaway line

Above the four steps sits a one-line orientation. Produce it as `takeaway`, or return `"takeaway": null`.

**Return null** when there is nothing to take a view on: a definitional or procedural question ("what is a geographical indication?", "how do I register a GI?", "what is TKDL?") describes no matter to assess, and a verdict on it would be invented. Return a takeaway only when the user has put a product, formulation, process or situation forward for assessment.

`intent` says which question is being answered, and fixes the vocabulary you may use:

- `patent` - can this be protected / patented? Labels: "Potentially patentable", "Likely excluded", "Requires verification", "Insufficient information".
- `gi` - is a geographical indication available here? Labels: "GI route may be relevant", "Unlikely to qualify", "Requires verification".
- `abs` - are access-and-benefit-sharing or NBA duties engaged? Labels: "ABS/NBA requirements may apply", "Unlikely to apply", "Requires verification".
- `tkdl` - is there documented traditional knowledge that would bar or defeat a claim? Labels: "High prior-art risk", "Low apparent prior-art risk", "Requires verification".
- `other` - anything else. Labels: "Requires verification", "Insufficient information".

Use `label` EXACTLY as written above. Choose the intent the user actually asked about, not the one the evidence happens to be richest in.

**Never state a bare yes or no**, in the label or in the reason. This line is a preliminary orientation from a document search, not a legal conclusion, and it is read by people who will act on it. Write "Likely excluded", never "No, you cannot patent this". `reason` is ONE plain sentence saying why, in ordinary words, and `citation_ids` carries the evidence it rests on - held to the same standard as a step, so cite what you actually relied on or leave it empty.


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
- The evidence is ordered by relevance, most relevant first. Where several provisions are \
near-identical - statutory exclusion clauses usually are, because they sit in one list and share \
their phrasing - cite the one that applies **directly** to this question, not a more general \
neighbour that merely reads similarly.
- Do not recommend a lawyer as a substitute for answering; answer what the evidence supports.

## Output

Return ONLY a JSON object, no markdown fence and no commentary:
{{"takeaway": {{"intent": "<patent|gi|abs|tkdl|other>", "label": "<exactly one of the labels listed for that intent>", "reason": "<one plain sentence, never a bare yes or no>", "citation_ids": ["..."]}},
 "headline": "<one sentence, max 25 words, answering the question the user actually asked - on the subject they raised, not a different regime>",
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
    trace: list[TraceStep] | None = None,
) -> Answer:
    """Build a refusal.

    The trace belongs here as much as on an answer - arguably more. A refusal is
    the hardest thing to take on trust, and the stages show that the scope gate
    RAN and decided, rather than the model simply declining.
    """
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
        trace=trace or [],
    )


def _build_steps(
    raw_steps: list[dict], allowed_ids: list[str]
) -> tuple[list[ReasoningStep], list[str], list[str]]:
    """Validate model output into steps, rejecting unverifiable citations.

    Returns (steps, rejected citation ids, provisions named without support).
    """
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
    all_unsupported: list[str] = []

    for number, title in STEP_TITLES.items():
        raw = by_number.get(number, {})
        # Same display-only cleanup the comparison path has always had. Its
        # absence here was an inconsistency, not a decision.
        content = strip_chunk_ids(str(raw.get("content") or ""))
        # An institution that does not exist is fabricated authority of the same
        # kind as a fabricated section number - and this phrase is in the corpus
        # itself, so the prompt rule alone does not hold it. See
        # citations.normalise_institutions.
        content = normalise_institutions(content)
        # A section number the evidence does not contain is fabricated authority,
        # however valid the citation ids beside it happen to be. Drop the
        # sentence rather than let it stand looking sourced.
        content, unsupported = strip_unsupported_provisions(content, allowed_ids)
        all_unsupported.extend(unsupported)
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
    return steps, all_rejected, all_unsupported


def _build_takeaway(
    raw: object, allowed_ids: list[str]
) -> tuple[Takeaway | None, list[str]]:
    """Validate the model's takeaway into a safe one, or None.

    Returns (takeaway, rejected citation ids).

    Two things are enforced here rather than asked for in the prompt:

    * **The label must come from the closed vocabulary for its intent.**
      Anything else - a label borrowed from another regime, an invented one, or
      the bare "Yes, patentable" this banner exists to prevent - is replaced
      with "Requires verification". A hedge is always a safe thing to say; a
      categorical verdict is not, so the failure direction is deliberate.
    * **The reason is citation-checked like a step.** It names provisions as
      readily as any other prose, and it is the first line the reader sees. The
      headline defect was precisely a user-facing sentence with no validation of
      its own, and adding a second one unguarded would repeat it.
    """
    if not isinstance(raw, dict):
        return None, []

    reason = normalise_institutions(strip_chunk_ids(str(raw.get("reason") or "").strip()))
    if not reason:
        return None, []

    try:
        intent = TakeawayIntent(str(raw.get("intent") or "").strip().lower())
    except ValueError:
        intent = TakeawayIntent.OTHER

    permitted = TAKEAWAY_LABELS[intent]
    label = str(raw.get("label") or "").strip()
    if label not in permitted:
        logger.info(
            "Takeaway label %r is not permitted for intent %s; using %r",
            label, intent.value, REQUIRES_VERIFICATION,
        )
        label = REQUIRES_VERIFICATION

    # A provision the evidence does not contain is fabricated authority here
    # just as it is in a step. The whole sentence goes if it carries one, and
    # with the sentence gone there is no reason left to show.
    reason, _removed = strip_unsupported_provisions(reason, allowed_ids)
    if not reason.strip():
        return None, []

    kept, rejected = validate_ids(raw.get("citation_ids") or [], allowed_ids)
    return (
        Takeaway(
            intent=intent, label=label, reason=reason,
            citation_ids=kept, unsourced=not kept,
        ),
        rejected,
    )


class _Trace:
    """Collects the stages that ran, so orchestration can be shown not claimed.

    Deliberately records what each stage DECIDED, not that it happened - "12
    passages, in scope" is worth reading; "retrieval: ok" is not. Timings are
    wall-clock and include provider latency, which is the honest number: on a
    free endpoint that is where nearly all of it goes.
    """

    def __init__(self) -> None:
        self.steps: list[TraceStep] = []
        self._mark = time.time()

    def step(self, stage: str, detail: str = "", status: str = "ok") -> None:
        now = time.time()
        self.steps.append(
            TraceStep(
                stage=stage,
                status=status,
                ms=int((now - self._mark) * 1000),
                detail=detail,
            )
        )
        self._mark = now


def answer_question(
    question: str,
    top_k: int | None = None,
    history: list[str] | None = None,
    jurisdiction: str = "national",
) -> Answer:
    """Classify, retrieve, generate and validate. The whole core loop.

    `jurisdiction` selects which corpus answers, and the two are kept strictly
    apart: retrieval filters both its dense and lexical halves on it, and the
    classification anchor is withheld outside the national corpus (see below).
    The problem statement requires the two answer-sets to be "visibly separate"
    and "never conflated", and the enforcement point is the evidence set - once
    a chunk from the wrong system is in the prompt, no amount of careful wording
    downstream keeps it out of the answer.
    """
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

    key = _cache_key(question, top_k, jurisdiction)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            _CACHE.move_to_end(key)
            logger.info("Cache hit for %r", question[:60])
            return cached

    trace = _Trace()

    # Bail before spending any API call on a fragment.
    if is_too_vague(question):
        # Recorded as a stage so the refusal explains itself: this one is
        # deterministic and costs nothing, which is exactly what a reader
        # wondering "did it even try?" needs to see.
        trace.step(
            "Screen the question",
            "below the content-word minimum - no model was called",
            status="skipped",
        )
        return _abstention_answer(
            asked, AbstentionKind.TOO_VAGUE,
            "That is too short for me to search on. Tell me what the product is, or "
            "which part of the law you are asking about.",
            resolved=resolved, trace=trace.steps,
        )

    # Classification and query expansion both depend only on the question, so
    # running them concurrently removes a whole round trip from every request.
    # On a free model that is several seconds of visible demo latency.
    with ThreadPoolExecutor(max_workers=2) as pool:
        classification_future = pool.submit(classify, question)
        expansion_future = pool.submit(expand_query, question, jurisdiction)
        classification = classification_future.result()
        expansion = expansion_future.result()
    trace.step(
        "Classify formulation · expand query",
        f"{classification.category.value} · {len(expansion.queries)} search formulation"
        f"{'' if len(expansion.queries) == 1 else 's'}",
        status="ok" if expansion.ok else "degraded",
    )

    # Scope and jurisdiction are settled BEFORE any clarifying question.
    # Order matters: asking "is your product classical or proprietary?" about a
    # question governed by US law wastes the user's turn on a question we were
    # never going to answer. Establish that we can answer at all, then refine.
    category = classification.category if classification.is_formulation else None
    result = retrieve(question, category=category, top_k=top_k, expansion=expansion,
                      jurisdiction=jurisdiction)
    trace.step(
        "Retrieve · scope and jurisdiction gate",
        f"{len(result.evidence)} passages · "
        + ("in scope" if result.sufficient else f"refused: {result.abstention.value}"),
        status="ok" if result.sufficient else "skipped",
    )

    if not result.sufficient:
        return _abstention_answer(
            asked, result.abstention, result.reason,
            classification=classification, resolved=resolved, trace=trace.steps,
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

    international = jurisdiction == "international"
    prompt = ANSWER_PROMPT.format(
        framing=INTERNATIONAL_FRAMING if international else NATIONAL_FRAMING,
        jurisdiction_step=(INTERNATIONAL_JURISDICTION_STEP if international
                           else NATIONAL_JURISDICTION_STEP),
        evidence=_evidence_block(result),
        classification=classification_block,
        question=question,
    )
    try:
        data = complete_json(prompt, max_tokens=settings.max_tokens)
        trace.step("Generate the four-step trail", f"{active_model()}")
    except LLMUnavailable as exc:
        # NOT no_evidence. The corpus may well cover this question perfectly
        # well - we simply could not reach the model. The UI renders
        # `no_evidence` as "nothing here covers that", which told users to
        # rephrase a question that was fine. GATE_UNAVAILABLE says "retry".
        logger.error("Generation failed: %s", exc)
        trace.step("Generate the four-step trail", "no provider answered", status="failed")
        return _abstention_answer(
            asked, AbstentionKind.GATE_UNAVAILABLE,
            "The answering service is temporarily unavailable. Your question looks fine - "
            "please try it again in a moment.",
            classification=classification, resolved=resolved, trace=trace.steps,
        )

    # The allowed set is "everything we actually showed the model". That includes
    # the classification's defining provision, which appears in the prompt - it
    # was previously rejected as unverifiable purely because it came from the
    # classifier rather than from retrieval.
    allowed = list(result.allowed_ids)
    # The classifier's defining source is a chunk of the INDIAN Drugs and
    # Cosmetics Act - that is what the six categories are defined by. Adding it
    # to the allowed set is right for a national answer and is conflation in an
    # international one: it would let a treaty answer cite Indian statute as
    # authority. The category is still used to steer retrieval; only its source
    # chunk is withheld.
    if (
        jurisdiction == "national"
        and classification.defining_source_id
        and classification.defining_source_id not in allowed
    ):
        allowed.append(classification.defining_source_id)

    steps, rejected, unsupported_provisions = _build_steps(data.get("steps") or [], allowed)
    _cited_steps = sum(1 for st in steps if st.citation_ids and not st.abstained)
    trace.step(
        "Validate every citation",
        f"{_cited_steps} of 3 steps sourced · {len(rejected)} citation"
        f"{'' if len(rejected) == 1 else 's'} rejected · "
        f"{len(unsupported_provisions)} unsupported provision"
        f"{'' if len(unsupported_provisions) == 1 else 's'} removed",
    )
    if rejected:
        logger.warning("Rejected %d unverifiable citation ids: %s", len(rejected), rejected)
    if unsupported_provisions:
        logger.warning(
            "Removed %d provision reference(s) no retrieved chunk contains: %s",
            len(unsupported_provisions), unsupported_provisions,
        )

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
            classification=classification, resolved=resolved, trace=trace.steps,
        )

    takeaway, takeaway_rejected = _build_takeaway(data.get("takeaway"), allowed)
    rejected.extend(takeaway_rejected)

    headline = normalise_institutions(
        strip_chunk_ids(" ".join(str(data.get("headline") or "").split()))
    ) or None
    # The headline names provisions as readily as a step does, and it is the one
    # sentence most people read. Same rule: a section number the evidence does
    # not contain does not ship.
    if headline:
        headline, headline_unsupported = strip_unsupported_provisions(headline, allowed)
        unsupported_provisions.extend(headline_unsupported)
        headline = headline or None

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
    # Same for the takeaway: a source marker the rail never renders is the
    # dangling-reference bug e2e_api.py asserts against.
    if takeaway:
        for cid in takeaway.citation_ids:
            if cid not in cited:
                cited.append(cid)

    # Built once, here, because confidence now scores citation specificity and
    # therefore needs the resolved provisions - not just the ids.
    # Each citation also carries the provisions its own text points at, so a
    # rule that says "subject to rule 21" stops being a dead end. Display
    # only - it adds no claim to the answer.
    built_citations = attach_graph_links(citations_for(cited))
    # Scored after validation, from what actually survived - see confidence.py.
    confidence = assess_confidence(steps, built_citations, rejected, result)
    trace.step(
        "Score evidence support",
        f"{CONFIDENCE_LABELS[confidence.level]} · {len(built_citations)} citation"
        f"{'' if len(built_citations) == 1 else 's'}",
    )

    escalate, escalation_reason = assess_escalation(False, AbstentionKind.NONE, confidence.level)

    answer = Answer(
        question=asked,
        resolved_question=resolved,
        jurisdiction=jurisdiction,
        headline=headline,
        headline_citation_ids=headline_ids,
        headline_unsourced=bool(headline) and not headline_ids,
        takeaway=takeaway,
        search_degraded=result.degraded,
        degraded_reason=result.degraded_reason,
        confidence=confidence.level,
        confidence_label=CONFIDENCE_LABELS[confidence.level],
        confidence_score=confidence.score,
        confidence_reasons=confidence.reasons,
        trace=trace.steps,
        # Surfaced with the answer, not instead of it.
        clarifying_question=classification.clarifying_question if unresolved_category else None,
        classification=classification,
        steps=steps,
        citations=built_citations,
        rejected_citation_ids=rejected,
        unsupported_provisions=unsupported_provisions,
        escalate=escalate,
        escalation_reason=escalation_reason,
        disclaimer=settings.disclaimer,
    )
    with _CACHE_LOCK:
        _CACHE[key] = answer
        if len(_CACHE) > CACHE_SIZE:
            _CACHE.popitem(last=False)
    return answer
