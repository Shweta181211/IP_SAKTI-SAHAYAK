"""Say the same thing in words a non-lawyer can act on.

The requirement is exact: plain mode changes *how the answer is phrased* and
nothing else. Same retrieval, same citations, same classification - only the
sentences differ.

The obvious implementation is a style instruction on the main generation prompt.
That does not meet the requirement, and it fails quietly: the model would
re-choose its `citation_ids` on each run, so the legal and plain renderings
could cite different provisions and both would look fine in isolation. "The same
answer in plainer words" would then be a claim nobody could actually check.

So plain mode is a REWRITE of a finished answer. The model is given the answer's
prose and asked only to re-say it; the citation lists, the classification, the
confidence and the abstention state are copied across in code and never pass
through the model at all. That makes "the citations are identical" a property of
the data flow rather than of the model's good behaviour, and lets the test be an
equality assertion instead of a sample.

Cost: one extra call, and only when plain is asked for. The legal answer is
cached under its own key, so toggling styles on the same question does not
regenerate it.
"""

from __future__ import annotations

import logging

from .citations import strip_chunk_ids, strip_unsupported_provisions
from .llm import LLMUnavailable, complete_json
from .schemas import Answer, ReasoningStep, ResponseStyle

logger = logging.getLogger(__name__)


REPHRASE_PROMPT = """Rewrite a legal answer so that someone with no legal training can act on it.

You are NOT answering the question. You are re-saying an answer that has already been written, checked and sourced. Every fact must survive; only the words change.

## What to keep, exactly

- Every provision reference stays, in the same place: "Section 3(p)", "Rule 122-E", "Article 5.4". A reader needs to be able to point at the source card beside the sentence. Explain what the provision DOES, do not remove its number.
- Do not add a fact, a requirement, a deadline, a fee or a consequence that is not already in the text below. If it is not there, it does not go in.
- Do not soften a prohibition into a maybe, and do not harden a "may" into a "must". A rewrite that changes the legal position is worse than no rewrite.
- If a step says the evidence did not support something, keep saying that. Plain language does not mean confident language.

## What to change

- Lead with what it means for the reader. "You cannot patent this" before the reasoning for it.
- **Start each step with the consequence, never with the provision.** Write "You cannot patent this, because Section 3(p) treats a traditional formulation as not an invention" - NOT "Under Section 3(p) of the Patents Act, 1970, ...". The provision still appears in the sentence; it just stops being the first thing a non-lawyer has to read.
- Replace terms of art with what they mean, keeping the term once in brackets where a reader may meet it again: "prior art (knowledge that already exists publicly)".
- Short sentences. Address the reader as "you" where the original talks about "the applicant" or "the user".
- Keep each step to roughly the same length. This is a rewrite, not a summary and not an expansion.

## The answer to rewrite

HEADLINE: {headline}

{steps}

## Output

Return ONLY a JSON object with the same step numbers, no markdown fence and no commentary:
{{"headline": "<the headline, in plain words>",
  "steps": [{{"step": 1, "content": "..."}}, {{"step": 2, "content": "..."}}]}}"""


def _steps_block(answer: Answer) -> str:
    return "\n\n".join(
        f"STEP {step.step} ({step.title}): {step.content}"
        for step in answer.steps
        if step.content
    )


def to_plain_language(answer: Answer) -> Answer:
    """Return the same answer, rephrased. Citations are carried across untouched.

    Falls back to the original answer if the rewrite is unavailable or comes
    back malformed: a legal-language answer is a perfectly good answer, and it
    is certainly better than a half-rewritten one.
    """
    if answer.abstained or not answer.steps:
        # Abstention messages and small talk are already plain, and they carry
        # no reasoning trail to rewrite. Mark the style so the UI is honest
        # about which rendering the user is looking at.
        return answer.model_copy(update={"response_style": ResponseStyle.PLAIN.value})

    prompt = REPHRASE_PROMPT.format(
        headline=answer.headline or "(none)", steps=_steps_block(answer)
    )
    try:
        data = complete_json(prompt, max_tokens=1200)
    except LLMUnavailable as exc:
        logger.warning("Plain-language rewrite unavailable (%s); keeping legal wording", exc)
        return answer

    rewritten = {}
    for raw in data.get("steps") or []:
        try:
            number = int(raw.get("step", 0))
        except (TypeError, ValueError):
            continue
        text = strip_chunk_ids(str(raw.get("content") or "").strip())
        if text:
            rewritten[number] = text

    steps: list[ReasoningStep] = []
    for step in answer.steps:
        text = rewritten.get(step.step)
        if text:
            # The same provision guard as the main path: a rewrite that
            # introduces "Section 3(d)" into a step whose sources never
            # mentioned it is fabricated authority, however plainly it is put.
            text, dropped = strip_unsupported_provisions(text, step.citation_ids)
            if dropped:
                logger.warning("Plain rewrite invented %s in step %d; sentence removed",
                               dropped, step.step)
        # citation_ids, title, step number and the abstained flag are carried
        # from the original - the model never sees or supplies them.
        steps.append(
            ReasoningStep(
                step=step.step,
                title=step.title,
                content=text or step.content,
                citation_ids=step.citation_ids,
                abstained=step.abstained,
            )
        )

    headline = strip_chunk_ids(str(data.get("headline") or "").strip())
    if headline:
        headline, dropped = strip_unsupported_provisions(headline, answer.headline_citation_ids)
        if dropped:
            logger.warning("Plain rewrite invented %s in the headline; sentence removed", dropped)

    return answer.model_copy(
        update={
            "headline": headline or answer.headline,
            "steps": steps,
            "response_style": ResponseStyle.PLAIN.value,
        }
    )


def apply_style(answer: Answer, style: str | ResponseStyle) -> Answer:
    """Render an answer in the requested style. Legal is the answer as generated."""
    wanted = style.value if isinstance(style, ResponseStyle) else str(style)
    if wanted == ResponseStyle.PLAIN.value:
        return to_plain_language(answer)
    return answer
