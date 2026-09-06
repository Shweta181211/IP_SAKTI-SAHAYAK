"""What this means next: practical guidance, drawn only from what was answered.

This is the most advice-like text the product produces, and therefore the part
most likely to be read as a legal determination and acted on. Three constraints
follow from that, and they are the whole design:

1. **No retrieval.** This step is given the finished answer and nothing else. It
   cannot introduce a provision the answer never established, because it is
   never shown the corpus. A "next steps" block that quietly went and found new
   law would be the single easiest place in this system to smuggle in an
   unsourced obligation.

2. **Every step cites.** "Apply for a licence under Rule 158-B" is a statement
   about the law wearing the clothes of advice. It is validated exactly like a
   reasoning step: the id must appear in the source answer's own citations, and
   a step that loses all of its citations is dropped rather than softened.

3. **It is allowed to say nothing.** Not every question earns a next-steps
   block. "What is a GI tag?" is answered by the answer; appending three
   imperatives to it is padding, and padding is how readers learn to skip a
   section. The model returns `applicable: false` with a reason, and the UI
   shows nothing.

For a jurisdiction comparison each step also records WHICH corpus it came from,
so a step derived from treaty text can never read as an Indian requirement -
the same separation rule the comparison itself is built on.
"""

from __future__ import annotations

import logging
import re

from .citations import strip_chunk_ids, strip_unsupported_provisions
from .corpus_index import get_chunk
from .llm import LLMUnavailable, complete_json
from .schemas import Answer, JurisdictionComparison, NextStep, NextSteps, ResponseStyle

logger = logging.getLogger(__name__)


NEXT_STEPS_PROMPT = """Someone has just been given the answer below. Decide whether there is anything practical they should do next, and if so, say what.

You have NO access to the law. You have only this answer. Everything you write must already be established in it.

## The answer they received

{answer}

## Sources that answer cited (use these ids and no others)

{citations}

## First decide: does this question deserve next steps at all?

Set `applicable` to false when the person asked what something IS rather than what to DO. "What is a geographical indication?", "what is the TKDL?" are answered by the answer itself; a list of imperatives after them is padding, and padding teaches people to skip this section.

Set it to true when the person described a product, a plan or a situation of their own - patenting a formulation, launching a supplement, registering a name, exporting - because then there is a real next move.

When false, give a one-line `reason` and no steps.

## If there are steps

Two to four, ordered by what to do first. Each step:

- is something the person can actually DO - check a register, file a form, obtain a licence, gather a document, get advice on a specific point;
- **opens with the verb they act on**: Check, File, Apply, Obtain, Gather, Search, Register, Consult, Prepare, Contact. Never "Recognise that", "Understand that", "Note that", "Be aware that" or "Consider that" - those restate the answer the person has just finished reading, and a step nobody can perform is not a step. It will be discarded;
- rests on what the answer established, and cites the id(s) that establish it;
- names the authority, register or form where the answer named one;
- does not invent a deadline, a fee, an office or a consequence that the answer did not state.

Where the answer said something was NOT possible, the useful step is the alternative it pointed to - not a restatement of the refusal.

{jurisdiction_note}

## Output

Return ONLY a JSON object, no markdown fence and no commentary:
{{"applicable": true,
  "reason": null,
  "steps": [{{"text": "...", "citation_ids": ["..."], "jurisdiction": "national"}}]}}"""

_SINGLE_JURISDICTION_NOTE = """Set `jurisdiction` to "{jurisdiction}" on every step: that is the only corpus this answer came from."""

_COMPARISON_NOTE = """This answer compared two legal systems. Set `jurisdiction` to "national" on a step that follows from the Indian position and "international" on a step that follows from the international instruments, and cite only that side's ids. A step that mixes the two is the failure this feature must not produce - if something applies under both, make it two steps."""


def _answer_text(answer: Answer) -> str:
    if answer.abstained:
        return f"[No answer was given: {answer.abstention_message or answer.abstention_kind.value}]"
    lines = [f"Headline: {answer.headline or '(none)'}"]
    if answer.classification:
        lines.append(f"Classified as: {answer.classification.label}")
    for step in answer.steps:
        if step.content:
            lines.append(f"{step.title}: {step.content}")
    return "\n".join(lines)


def _citation_lines(answers: list[Answer]) -> str:
    seen: dict[str, str] = {}
    for answer in answers:
        for citation in answer.citations:
            seen.setdefault(citation.chunk_id, citation.display)
    if not seen:
        return "(none)"
    return "\n".join(f"[{cid}] {display}" for cid, display in seen.items())


# A step must tell someone to DO something.
#
# Measured on the flagship: the model returned "Recognize that the classical
# churna ... cannot receive patent protection", which is the answer restated as
# an imperative - exactly what NEXT_STEPS_PROMPT already forbids in as many
# words ("not a restatement of the refusal"). The prompt is right; the free
# model under-follows it. So the rule is enforced HERE as well, where it holds
# whatever model answered and survives a provider failover.
#
# Matched only at the START of a step, which is what lets "Consider filing an
# application" through while stopping "Consider that the application will fail".
_NON_ACTION_OPENERS = re.compile(
    r"^\s*(?:please\s+)?(?:"
    r"recogni[sz]e|understand|acknowledge|reali[sz]e|note|remember|know|"
    r"be\s+aware|bear\s+in\s+mind|keep\s+in\s+mind|it\s+is\s+important|"
    r"consider\s+that"
    r")\b",
    re.I,
)


def _validate(raw: dict, allowed: dict[str, str]) -> tuple[NextStep | None, str | None]:
    """Keep a step only if what it tells someone to do is sourced.

    `allowed` maps an allowed chunk id to the jurisdiction it belongs to, so a
    step cannot cite across corpora in the comparison case.
    """
    text = strip_chunk_ids(str(raw.get("text") or "").strip())
    if not text:
        return None, "step had no text"

    if _NON_ACTION_OPENERS.match(text):
        return None, f"not an action, dropped: {text[:70]}"

    wanted = str(raw.get("jurisdiction") or "national").strip().lower()
    if wanted not in ("national", "international"):
        wanted = "national"

    kept, bad = [], []
    for cid in raw.get("citation_ids") or []:
        cid = str(cid)
        if allowed.get(cid) == wanted and get_chunk(cid) is not None:
            kept.append(cid)
        else:
            bad.append(cid)

    if not kept:
        return None, f"unsourced step dropped: {text[:70]}"

    text, dropped = strip_unsupported_provisions(text, kept)
    if dropped:
        bad.extend(dropped)
    if not text:
        return None, f"step was left empty after removing {dropped}"

    return NextStep(text=text, citation_ids=kept, jurisdiction=wanted), (
        "; ".join(bad) if bad else None
    )


def _synthesise(answer_text: str, answers: list[Answer], allowed: dict[str, str],
                jurisdiction_note: str) -> NextSteps:
    prompt = NEXT_STEPS_PROMPT.format(
        answer=answer_text,
        citations=_citation_lines(answers),
        jurisdiction_note=jurisdiction_note,
    )
    try:
        data = complete_json(prompt, max_tokens=900)
    except LLMUnavailable as exc:
        logger.warning("Next steps unavailable: %s", exc)
        return NextSteps(
            applicable=False,
            unavailable=True,
            reason="The suggestions step could not run just now. The answer above is complete.",
        )

    if not bool(data.get("applicable", True)):
        return NextSteps(
            applicable=False,
            reason=strip_chunk_ids(str(data.get("reason") or "").strip())
            or "This question is answered by the answer itself.",
        )

    result = NextSteps(applicable=True)
    for raw in (data.get("steps") or [])[:5]:
        if not isinstance(raw, dict):
            continue
        step, rejected = _validate(raw, allowed)
        if step is not None:
            result.steps.append(step)
        if rejected:
            result.rejected.append(rejected)

    if not result.steps:
        result.applicable = False
        result.reason = (
            "No suggestion survived checking against the sources above, so none is shown."
        )
    if result.rejected:
        logger.warning("Dropped %d unsourced next step(s): %s",
                       len(result.rejected), result.rejected)
    return result


def next_steps_for_answer(answer: Answer, style: str = ResponseStyle.LEGAL.value) -> NextSteps:
    """Practical follow-ups for a single answer."""
    if answer.abstained:
        return NextSteps(
            applicable=False,
            reason="There is no answer to build suggestions on.",
        )
    allowed = {
        c.chunk_id: str((get_chunk(c.chunk_id) or {}).get("jurisdiction", "national"))
        for c in answer.citations
    }
    jurisdiction = "international" if answer.jurisdiction == "international" else "national"
    return _synthesise(
        _answer_text(answer), [answer], allowed,
        _SINGLE_JURISDICTION_NOTE.format(jurisdiction=jurisdiction),
    )


def next_steps_for_comparison(
    comparison: JurisdictionComparison, style: str = ResponseStyle.LEGAL.value
) -> NextSteps:
    """Practical follow-ups drawn from both jurisdictions, each labelled."""
    sides = [comparison.national, comparison.international]
    if all(a.abstained for a in sides):
        return NextSteps(applicable=False, reason="Neither side produced an answer.")

    allowed = {}
    for answer in sides:
        for citation in answer.citations:
            allowed[citation.chunk_id] = str(
                (get_chunk(citation.chunk_id) or {}).get("jurisdiction", "national")
            )

    text = (
        "=== INDIAN LAW ===\n"
        + _answer_text(comparison.national)
        + "\n\n=== INTERNATIONAL INSTRUMENTS ===\n"
        + _answer_text(comparison.international)
    )
    if comparison.points:
        text += "\n\n=== HOW THEY COMPARE ===\n" + "\n".join(
            f"- ({p.kind}) {p.summary}"
            f"{' | India: ' + p.national_claim if p.national_claim else ''}"
            f"{' | International: ' + p.international_claim if p.international_claim else ''}"
            for p in comparison.points
        )
    return _synthesise(text, sides, allowed, _COMPARISON_NOTE)
