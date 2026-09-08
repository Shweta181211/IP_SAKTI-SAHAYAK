"""Export readiness — the India-side and target-market position, side by side.

This is the same machinery as everything else in this app, pointed at a
different question. It reuses `classify`, `retrieve` (including its relevance
gate), `validate_ids`, the provision-support check and `confidence.assess`. That
is not tidiness for its own sake: a parallel implementation would drift out of
step with fixes made elsewhere, and the guarantees this project actually sells -
no fabricated authority, honest abstention, jurisdictions never conflated - live
in those functions.

Three rules shape the whole module.

**Nothing about a target country is hardcoded.** There is no table of supported
markets and no pre-written paragraph per country. The target country is free
text; whatever the report says about it comes from retrieving against the
international corpus at request time and citing what came back. A country the
corpus does not reach produces a section that says so.

**Status is derived, not asserted.** The model proposes a status for each item,
but `_settle_status` overrides it: an item whose citations do not survive
validation becomes NOT_COVERED whatever the model claimed, and no item can be
VERIFIED without a surviving citation. This is the same shape as
`generation._build_steps` replacing the content of an uncited step - a claim
with nothing behind it does not get to look established.

**The two sides never share evidence.** India-side items may cite only national
chunks and target-market items only international ones, checked per item the way
`jurisdiction_compare._validate_point` checks per point. A prompt asking for
separation is a request; a validator that drops the item is a guarantee.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from .citations import (
    citations_for,
    normalise_institutions,
    strip_chunk_ids,
    strip_unsupported_provisions,
    validate_ids,
)
from .classification import classify
from .graph import attach_links as attach_graph_links
from .confidence import assess as assess_confidence
from .config import settings
from .corpus_index import get_chunk
from .escalation import assess as assess_escalation
from .llm import LLMUnavailable, complete_json
from .retrieval import RetrievalResult, retrieve
from .schemas import (
    CONFIDENCE_LABELS,
    AbstentionKind,
    Category,
    ClassificationResult,
    ExportReadinessReport,
    ExportReadinessRequest,
    NextStep,
    ReadinessItem,
    ReadinessSection,
    ReadinessStatus,
    ReasoningStep,
)

logger = logging.getLogger(__name__)


READINESS_PROMPT = """You are preparing an **export readiness** view for an Ayurvedic product. \
You give information, never legal advice, and you answer STRICTLY from the numbered evidence \
below. You have no other knowledge of the law.

There are two separate bodies of evidence and they must never be mixed.

## INDIAN evidence (national law)

{national_evidence}

## INTERNATIONAL evidence (treaties and regional instruments)

{international_evidence}

## The product

{product}

## Target export market

{target_country}

## What to produce

**India-side items** - what Indian law requires before this product can be made, protected and \
shipped. Cover, where the Indian evidence supports it: the regulatory/licensing pathway, \
intellectual-property considerations (patent, trade mark, GI as relevant), access-and-benefit-\
sharing or biodiversity duties, and any labelling or advertising constraint. Cite ONLY ids from \
the INDIAN evidence.

**Target-market items** - what the international evidence says bears on placing this product in \
the named market. Cite ONLY ids from the INTERNATIONAL evidence.

**This is the part to get right.** The international corpus holds treaties and regional \
instruments. It does NOT hold most countries' domestic marketing-authorisation law.

An instrument reaches the named market when the market falls within the instrument's OWN stated \
scope - a regional instrument binding a bloc reaches the states in that bloc, and a treaty binds \
its contracting parties. It does not have to name the country to govern it, and you may use \
ordinary knowledge of which bloc or treaty a country belongs to in order to decide that. What \
you may NOT do is take the legal requirement from anywhere but the evidence.

If nothing in the evidence reaches the market on that test, return an EMPTY `target_items` list \
and say why in `target_note`. Do not substitute an instrument that has nothing to do with the \
market, and do not write generic export advice. An honest gap is the correct output and it is \
what this tool is for.

Each item carries a `status`, and you must choose it from what the evidence actually shows:

- `verified` - the evidence states the requirement and what satisfies it, with nothing left open.
- `needs_verification` - the evidence establishes that the requirement applies but not that this \
product meets it, or it points to a step the user must still take.
- `blocker` - the evidence shows something that would BAR this route as described (a statutory \
exclusion, a prohibition, a claim that may not be made).

`status_reason` is one short clause saying why that status and not another.

`target_framing` is how the target market's own instruments frame this KIND of product, if the \
international evidence says. Return null if it does not - never infer it.

`action_plan` is an ordered list of concrete next steps. Each names the `jurisdiction` it \
follows from ("india" or "international") and cites from that side only. Steps are actions: \
"File Form 24 with the State Licensing Authority", not "Understand that licensing applies".

## Rules that are not negotiable

- `citation_ids` may contain ONLY ids from the evidence above, exactly as written, from the \
correct side. Never invent one, and never cite an Indian id on a target-market item.
- Every factual claim must be backed by an id you cite on that item.
- Name provision numbers inline where the evidence gives them ("under Rule 157...").
- Never write a chunk id such as DOC003_chunk_234 in prose.
- Do not state a bare guarantee of approval or refusal. This is a readiness view assembled from \
documents, not a regulatory decision.

## Output

Return ONLY a JSON object, no markdown fence and no commentary:
{{"target_framing": "<one sentence, or null>",
 "target_framing_citation_ids": ["<international ids>"],
 "target_note": "<why the target market is not covered, or null if it is>",
 "india_items": [
   {{"title": "...", "detail": "...", "status": "verified|needs_verification|blocker",
     "status_reason": "...", "citation_ids": ["<indian ids>"]}}
 ],
 "target_items": [
   {{"title": "...", "detail": "...", "status": "verified|needs_verification|blocker",
     "status_reason": "...", "citation_ids": ["<international ids>"]}}
 ],
 "action_plan": [
   {{"text": "...", "jurisdiction": "india|international", "citation_ids": ["..."]}}
 ]}}"""


def _describe(request: ExportReadinessRequest) -> str:
    """The form, as one product description the rest of the pipeline can read.

    Assembled from what the user typed and nothing else. The claims flag is
    stated as a fact about the product rather than mapped to a regime, because
    choosing the regime is the classifier's job and the retriever's - deciding
    it here from a checkbox would be exactly the keyword special-casing the
    generalisation requirement rules out.
    """
    parts = [request.product.strip()]
    if request.ingredients.strip():
        parts.append(f"Key ingredients: {request.ingredients.strip()}.")
    parts.append(
        "Health or medical claims are made for this product."
        if request.health_claims
        else "No health or medical claims are made for this product."
    )
    return " ".join(p for p in parts if p)


def _india_question(description: str, target: str) -> str:
    return (
        f"{description} What does Indian law require before this product can be "
        f"manufactured, protected and exported to {target}? Cover the regulatory "
        f"pathway, intellectual property, access and benefit sharing, and labelling "
        f"or advertising duties."
    )


def _target_question(description: str, target: str) -> str:
    return (
        f"{description} What do the international instruments require for placing "
        f"this product on the market in {target}, including any regulatory pathway, "
        f"ingredient or claim restriction, labelling duty and intellectual property "
        f"protection available there?"
    )


def _evidence_block(result: RetrievalResult | None, char_limit: int = 1000) -> str:
    if result is None or not result.evidence:
        return "(nothing retrieved)"
    parts = []
    for item in result.evidence:
        meta = item.metadata or {}
        text = " ".join(str(item.text).split())[:char_limit]
        parts.append(f"[{item.chunk_id}] {meta.get('act_name', 'Unknown source')}\n{text}")
    return "\n\n".join(parts)


def _side_of(chunk_id: str) -> str | None:
    """Which corpus a chunk belongs to, read from the chunk itself."""
    chunk = get_chunk(chunk_id)
    if chunk is None:
        return None
    return str(chunk.get("jurisdiction") or "")


def _settle_status(claimed: str, kept_ids: list[str]) -> tuple[ReadinessStatus, str]:
    """Decide the status from what survived, not from what was claimed.

    The model proposes; validation disposes. An item whose citations did not
    survive has nothing behind it, and a checklist line that looks established
    on the strength of an unverifiable reference is worse than an admitted gap -
    it is the same failure the citation guard exists to prevent, wearing a tick
    instead of a sentence.
    """
    if not kept_ids:
        return (
            ReadinessStatus.NOT_COVERED,
            "no source in this corpus could be verified for this item",
        )
    try:
        status = ReadinessStatus(str(claimed).strip().lower())
    except ValueError:
        return (
            ReadinessStatus.NEEDS_VERIFICATION,
            "the status returned was not one this report recognises",
        )
    if status is ReadinessStatus.NOT_COVERED:
        # Claiming "not covered" while citing surviving evidence is incoherent;
        # the evidence is there, so the honest floor is "confirm it".
        return ReadinessStatus.NEEDS_VERIFICATION, "sources were found for this item"
    return status, ""


def _build_items(
    raw_items: object, allowed_ids: list[str], side: str
) -> tuple[list[ReadinessItem], list[str]]:
    """Validate raw items for one side. Returns (items, rejected ids)."""
    items: list[ReadinessItem] = []
    rejected: list[str] = []
    if not isinstance(raw_items, list):
        return items, rejected

    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        title = normalise_institutions(strip_chunk_ids(str(raw.get("title") or "").strip()))
        detail = normalise_institutions(strip_chunk_ids(str(raw.get("detail") or "").strip()))
        if not title:
            continue

        kept, bad = validate_ids(raw.get("citation_ids") or [], allowed_ids)
        rejected.extend(bad)
        # Separation enforced per item, not per prompt: an id that resolves to
        # the other corpus is dropped even though it is a real, retrieved chunk.
        cross = [cid for cid in kept if _side_of(cid) != side]
        if cross:
            logger.warning("Dropping %s citation(s) from the wrong corpus: %s", side, cross)
            kept = [cid for cid in kept if cid not in cross]

        # A provision the evidence does not contain is fabricated authority here
        # exactly as it is in a reasoning step.
        detail, _removed = strip_unsupported_provisions(detail, allowed_ids)

        status, forced_reason = _settle_status(raw.get("status"), kept)
        reason = forced_reason or normalise_institutions(
            strip_chunk_ids(str(raw.get("status_reason") or "").strip())
        )
        if status is ReadinessStatus.NOT_COVERED and not detail:
            detail = "The corpus does not contain a source that settles this."

        items.append(
            ReadinessItem(
                title=title, detail=detail, status=status,
                status_reason=reason, citation_ids=kept,
            )
        )
    return items, rejected


def _build_action_plan(
    raw_steps: object, national_ids: list[str], international_ids: list[str]
) -> tuple[list[NextStep], list[str]]:
    steps: list[NextStep] = []
    rejected: list[str] = []
    if not isinstance(raw_steps, list):
        return steps, rejected

    for raw in raw_steps:
        if not isinstance(raw, dict):
            continue
        text = normalise_institutions(strip_chunk_ids(str(raw.get("text") or "").strip()))
        if not text:
            continue
        side = "international" if str(raw.get("jurisdiction")) == "international" else "national"
        allowed = international_ids if side == "international" else national_ids
        kept, bad = validate_ids(raw.get("citation_ids") or [], allowed)
        rejected.extend(bad)
        kept = [cid for cid in kept if _side_of(cid) == side]
        steps.append(NextStep(text=text, citation_ids=kept, jurisdiction=side))
    return steps, rejected


def _abstained(
    request: ExportReadinessRequest,
    kind: AbstentionKind,
    message: str,
    classification: ClassificationResult | None = None,
) -> ExportReadinessReport:
    escalate, reason = assess_escalation(True, kind, None)
    return ExportReadinessReport(
        product=request.product,
        target_country=request.target_country,
        classification=classification,
        abstained=True,
        abstention_kind=kind,
        abstention_message=message,
        escalate=escalate,
        escalation_reason=reason,
        disclaimer=ExportReadinessReport.model_fields["disclaimer"].default,
    )


def build_report(request: ExportReadinessRequest) -> ExportReadinessReport:
    """Classify, retrieve both sides, generate one report, validate everything."""
    description = _describe(request)
    top_k = settings.top_k

    # Classification and both retrievals depend only on the description, so they
    # run concurrently - the same trick generation.py uses to take a whole round
    # trip out of every request.
    with ThreadPoolExecutor(max_workers=3) as pool:
        classification_future = pool.submit(classify, description)
        national_future = pool.submit(
            retrieve, _india_question(description, request.target_country),
            None, top_k, "national",
        )
        international_future = pool.submit(
            retrieve, _target_question(description, request.target_country),
            None, top_k, "international",
        )
        classification = classification_future.result()
        national = national_future.result()
        international = international_future.result()

    # The user may pin the category; otherwise the classifier's stands. Either
    # way it is the existing six-category classifier, not a second one.
    if request.category is not None:
        classification = classification.model_copy(update={"category": request.category})

    # India-side is the spine of this report. If the national corpus cannot
    # reach the product at all, there is no report to give.
    if not national.sufficient:
        return _abstained(request, national.abstention, national.reason, classification)

    national_ids = list(national.allowed_ids)
    international_ids = list(international.allowed_ids) if international.sufficient else []

    prompt = READINESS_PROMPT.format(
        national_evidence=_evidence_block(national),
        international_evidence=(
            _evidence_block(international) if international.sufficient
            else "(the international corpus does not reach this market for this product)"
        ),
        product=description,
        target_country=request.target_country,
    )
    try:
        data = complete_json(prompt, max_tokens=3000)
    except LLMUnavailable as exc:
        logger.error("Export readiness generation failed: %s", exc)
        return _abstained(
            request, AbstentionKind.GATE_UNAVAILABLE,
            "The readiness service is temporarily unavailable. Your details look fine - "
            "please try again in a moment.",
            classification,
        )

    india_items, rejected = _build_items(data.get("india_items"), national_ids, "national")
    target_items, target_rejected = _build_items(
        data.get("target_items"), international_ids, "international"
    )
    rejected.extend(target_rejected)

    plan, plan_rejected = _build_action_plan(
        data.get("action_plan"), national_ids, international_ids
    )
    rejected.extend(plan_rejected)

    framing = normalise_institutions(
        strip_chunk_ids(str(data.get("target_framing") or "").strip())
    ) or None
    framing_ids, framing_rejected = validate_ids(
        data.get("target_framing_citation_ids") or [], international_ids
    )
    rejected.extend(framing_rejected)
    framing_ids = [cid for cid in framing_ids if _side_of(cid) == "international"]
    if framing and not framing_ids:
        # An unsourced framing sentence about a foreign market is precisely the
        # invention this feature must not produce.
        framing = None

    # Coverage is decided by what actually came back, never by a list of
    # supported countries.
    covered = bool(target_items)
    uncovered_reason = None
    if not covered:
        note = strip_chunk_ids(str(data.get("target_note") or "").strip())
        uncovered_reason = note or (
            international.reason if not international.sufficient else ""
        ) or (
            "The international corpus holds treaties and regional instruments, and none of "
            "them settles what this market requires for this product. Nothing is stated here "
            "rather than guessing at it."
        )

    india_section = ReadinessSection(
        jurisdiction="national",
        heading="India-side requirements",
        covered=bool(india_items),
        uncovered_reason=(
            None if india_items
            else "No Indian requirement could be grounded in a cited source for this product."
        ),
        items=india_items,
    )
    target_section = ReadinessSection(
        jurisdiction="international",
        heading=f"Target market — {request.target_country}",
        covered=covered,
        uncovered_reason=uncovered_reason,
        items=target_items,
    )

    cited: list[str] = []
    for group in (india_items, target_items):
        for item in group:
            for cid in item.citation_ids:
                if cid not in cited:
                    cited.append(cid)
    for cid in framing_ids:
        if cid not in cited:
            cited.append(cid)
    for step in plan:
        for cid in step.citation_ids:
            if cid not in cited:
                cited.append(cid)

    if not cited:
        return _abstained(
            request, AbstentionKind.NO_EVIDENCE,
            "I could not ground a readiness view for this product in the corpus, so I am "
            "not going to offer one.",
            classification,
        )

    built = attach_graph_links(citations_for(cited))

    # Scored with the same function every answer uses. The India-side items
    # stand in for reasoning steps: each is a claim that either kept a citation
    # or did not, which is exactly what that scorer reads.
    scored_steps = [
        ReasoningStep(
            step=min(i + 1, 3), title=item.title, content=item.detail,
            citation_ids=item.citation_ids,
            abstained=item.status is ReadinessStatus.NOT_COVERED,
        )
        for i, item in enumerate(india_items[:3])
    ]
    confidence = assess_confidence(scored_steps, built, rejected, national)
    escalate, escalation_reason = assess_escalation(
        False, AbstentionKind.NONE, confidence.level
    )

    return ExportReadinessReport(
        product=request.product,
        target_country=request.target_country,
        classification=classification,
        target_framing=framing,
        target_framing_citation_ids=framing_ids,
        india=india_section,
        target=target_section,
        action_plan=plan,
        citations=built,
        rejected_citation_ids=rejected,
        confidence=confidence.level,
        confidence_label=CONFIDENCE_LABELS[confidence.level],
        confidence_score=confidence.score,
        confidence_reasons=confidence.reasons,
        escalate=escalate,
        escalation_reason=escalation_reason,
    )
