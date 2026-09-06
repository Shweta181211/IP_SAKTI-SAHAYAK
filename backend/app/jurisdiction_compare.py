"""Compare the Indian position with the international one, without blending them.

The problem statement requires national and international answer-sets to be
"visibly separate" and "never conflated". A comparison feature is where that is
hardest to hold: the whole point is to talk about both at once, and the natural
way to write that sentence - "the law requires disclosure of source" - is
already a conflation, because it does not say whose law.

Three defences, in order of how much they actually protect:

1. **Two independent passes.** National and international answers come from
   separate retrieval over separate corpora and separate generation calls. No
   chunk from one jurisdiction is ever in the other's prompt, so neither answer
   can cite across the line. They run concurrently because they share nothing.

2. **A shape that cannot express a blended claim.** The synthesis returns
   `JurisdictionPoint`s with a claim and citations PER SIDE. There is no field
   for an unattributed statement of law, so the model cannot write one without
   choosing a side, and choosing a side means citing that side's sources.

3. **Validation against the source answers.** Every citation on a point must
   appear in the corresponding answer AND belong to that jurisdiction. A point
   that cites across, or cites something neither answer used, is dropped and
   reported. This is the same rule as `validate_ids`, applied to a step that
   never touches retrieval.

The synthesis call sees ONLY the two finished answers - never the corpus, never
retrieval. It cannot introduce law because it is not shown any.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from .citations import strip_chunk_ids, strip_unsupported_provisions
from .config import settings
from .corpus_index import get_chunk
from .generation import answer_question
from .llm import LLMUnavailable, complete_json
from .schemas import Answer, JurisdictionComparison, JurisdictionPoint

logger = logging.getLogger(__name__)


SYNTHESIS_PROMPT = """Two independent answers to the same question are given below: one from **Indian domestic law**, one from **international instruments**. They were produced separately, from separate sources.

Your job is to compare them. You have NO other knowledge and NO access to the law itself - only these two answers. Do not add a legal claim that is not already stated in one of them.

## The question

{question}

## ANSWER A - Indian law (national)

{national}

Citations available for side A (use these ids and no others for national claims):
{national_ids}

## ANSWER B - international instruments

{international}

Citations available for side B (use these ids and no others for international claims):
{international_ids}

## What to produce

Between two and four points that would actually help someone who has read both. Prefer points that change what a person would DO.

Each point names one side's position and the other's, separately:

- `kind`: "similarity" when both systems point the same way, "difference" when they diverge.
- `summary`: one sentence naming the issue being compared. **Do not state law here** - it belongs in the per-side claims, where it can be attributed.
- `national_claim` + `national_citation_ids`: what ANSWER A established, and the id(s) from side A that support it.
- `international_claim` + `international_citation_ids`: the same for ANSWER B.

## Rules that are not negotiable

- **Never write a claim that does not say whose law it is.** "Disclosure of source is required" is wrong; "India requires ..." and "the GRATK Treaty requires ..." are right. That is the entire purpose of this feature.
- A national claim may cite ONLY side A ids; an international claim may cite ONLY side B ids. Crossing them is the failure this is built to prevent.
- Only restate what the two answers say. If one answer abstained or found nothing, say so plainly as that side's claim and leave its citation list empty - do not fill the gap from memory.
- If a side genuinely has nothing to say on a point, leave that side's claim null rather than inventing a counterpart.
- Do not repeat a provision number that does not appear in the answer you are attributing it to.

## Output

Return ONLY a JSON object, no markdown fence and no commentary:
{{"points": [
  {{"kind": "difference",
    "summary": "...",
    "national_claim": "...", "national_citation_ids": ["..."],
    "international_claim": "...", "international_citation_ids": ["..."]}}
]}}"""


def _answer_block(answer: Answer) -> str:
    """Render one finished answer as the only evidence the synthesis may use."""
    if answer.abstained:
        return (
            f"[This side did not answer: {answer.abstention_kind.value}]\n"
            f"{answer.abstention_message or ''}"
        )
    lines = [f"Headline: {answer.headline or '(none)'}"]
    if answer.classification:
        lines.append(f"Classification: {answer.classification.label}")
    for step in answer.steps:
        if step.content:
            marker = " [unsourced]" if step.abstained else ""
            lines.append(f"{step.title}{marker}: {step.content}")
    return "\n".join(lines)


def _citation_lines(answer: Answer) -> str:
    if not answer.citations:
        return "(none - this side produced no citations)"
    return "\n".join(f"[{c.chunk_id}] {c.display}" for c in answer.citations)


def _validate_point(
    raw: dict,
    national: Answer,
    international: Answer,
) -> tuple[JurisdictionPoint | None, str | None]:
    """Keep a point only if each side's claim is sourced from its own corpus."""
    national_allowed = {c.chunk_id for c in national.citations}
    international_allowed = {c.chunk_id for c in international.citations}

    def keep(ids, allowed, want_jurisdiction) -> tuple[list[str], list[str]]:
        good, bad = [], []
        for cid in ids or []:
            chunk = get_chunk(str(cid))
            if (
                str(cid) in allowed
                and chunk is not None
                and chunk.get("jurisdiction") == want_jurisdiction
            ):
                good.append(str(cid))
            else:
                bad.append(str(cid))
        return good, bad

    summary = strip_chunk_ids(str(raw.get("summary") or "").strip())
    if not summary:
        return None, "point had no summary"

    nat_ids, nat_bad = keep(raw.get("national_citation_ids"), national_allowed, "national")
    int_ids, int_bad = keep(
        raw.get("international_citation_ids"), international_allowed, "international"
    )

    nat_claim = strip_chunk_ids(str(raw.get("national_claim") or "").strip()) or None
    int_claim = strip_chunk_ids(str(raw.get("international_claim") or "").strip()) or None

    # A provision named in a claim must appear in that side's own cited chunks -
    # the same rule the main answer path applies, so the synthesis cannot
    # introduce "Section 3(p)" into a side whose sources never mention it.
    if nat_claim:
        nat_claim, nat_dropped = strip_unsupported_provisions(nat_claim, nat_ids)
        nat_bad.extend(nat_dropped)
    if int_claim:
        int_claim, int_dropped = strip_unsupported_provisions(int_claim, int_ids)
        int_bad.extend(int_dropped)

    # A claim with no surviving citation is an assertion this step is not
    # entitled to make. Drop the CLAIM, not the whole point: the other side may
    # still be perfectly well sourced and worth showing.
    if nat_claim and not nat_ids and not national.abstained:
        nat_bad.append(f"unsourced national claim: {nat_claim[:60]}")
        nat_claim = None
    if int_claim and not int_ids and not international.abstained:
        int_bad.append(f"unsourced international claim: {int_claim[:60]}")
        int_claim = None

    if not nat_claim and not int_claim:
        return None, f"both sides unsourced for {summary[:60]!r}"

    kind = str(raw.get("kind") or "").strip().lower()
    point = JurisdictionPoint(
        kind="similarity" if kind.startswith("sim") else "difference",
        summary=summary,
        national_claim=nat_claim,
        national_citation_ids=nat_ids,
        international_claim=int_claim,
        international_citation_ids=int_ids,
    )
    rejected = "; ".join(nat_bad + int_bad) or None
    return point, rejected


def compare_jurisdictions(
    question: str,
    top_k: int | None = None,
    national: Answer | None = None,
    international: Answer | None = None,
) -> JurisdictionComparison:
    """Compare the two jurisdictions, generating only the sides not supplied.

    The reading flow is progressive: a question is answered nationally, the user
    reveals the international position if they want it, and only then asks for a
    comparison. By that point both answers already exist on screen, so both are
    passed in here and this becomes a SINGLE synthesis call rather than nine.

    Passing them in is also more correct than regenerating: the comparison then
    describes exactly the two answers the reader is looking at, instead of two
    fresh ones that free-model variance could make subtly different.
    """
    top_k = top_k or settings.top_k

    missing = [j for j, a in (("national", national), ("international", international))
               if a is None]
    if missing:
        # Whatever was not supplied is generated now. Independent and
        # concurrent: the two share no state and no evidence. Each is separately
        # cached by generation._cache_key, which includes the jurisdiction.
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                j: pool.submit(answer_question, question, top_k=top_k, jurisdiction=j)
                for j in missing
            }
            if "national" in futures:
                national = futures["national"].result()
            if "international" in futures:
                international = futures["international"].result()

    assert national is not None and international is not None

    result = JurisdictionComparison(
        question=question, national=national, international=international
    )

    # Nothing to compare if neither side produced an answer. Both are still
    # returned so the user can read why each declined.
    if national.abstained and international.abstained:
        result.synthesis_unavailable = True
        result.synthesis_message = (
            "Neither corpus produced an answer to compare. Each side's reason is shown "
            "above."
        )
        return result

    prompt = SYNTHESIS_PROMPT.format(
        question=question,
        national=_answer_block(national),
        international=_answer_block(international),
        national_ids=_citation_lines(national),
        international_ids=_citation_lines(international),
    )

    try:
        # The one call in the system routed to the strongest available model.
        # Everything else is a judgement about one corpus; this one holds two
        # apart, and conflating them is the failure the problem statement names
        # explicitly. The trade is a slower call on a step the user asked for
        # deliberately - see the note in config.strong_model.
        # 1200 was too tight and failed in the worst way available: the model
        # emitted `{"points": [` and was cut off, so complete_json could not
        # parse it and a healthy provider reported the whole synthesis as
        # unavailable. This output is several points wide, each carrying prose
        # for BOTH sides plus two citation-id arrays, so it is far larger than
        # any other JSON reply in the system. Measured: gpt-oss-120b returns
        # clean, naturally-terminated JSON on a small task at 1200 - the ceiling
        # was the real prompt's output size, not the model.
        data = complete_json(prompt, max_tokens=3000, strong=True)
    except LLMUnavailable as exc:
        logger.warning("Jurisdiction synthesis unavailable: %s", exc)
        result.synthesis_unavailable = True
        result.synthesis_message = (
            "Both answers are shown, but the comparison step could not run just now. "
            "They are complete and independently cited; only the summary is missing."
        )
        return result

    for raw in (data.get("points") or [])[:5]:
        if not isinstance(raw, dict):
            continue
        point, rejected = _validate_point(raw, national, international)
        if point is not None:
            result.points.append(point)
        if rejected:
            result.rejected_points.append(rejected)

    if not result.points:
        result.synthesis_unavailable = True
        result.synthesis_message = (
            "No comparison point survived validation against the two answers, so none "
            "is shown. Both answers below stand on their own."
        )
    if result.rejected_points:
        logger.warning("Dropped %d unsourced comparison point(s): %s",
                       len(result.rejected_points), result.rejected_points)
    return result
