"""Confidence scoring — built on what survived, not on vector distance.

The obvious implementation is a similarity threshold, and it does not work on
this corpus. Measured in Phase 1 and again in Phase 3:

    dense distance   in-corpus 0.2469-0.3598 | out-of-corpus 0.3696-0.3951
    BM25 score       in-corpus 11.21 -31.16  | out-of-corpus 11.95 -26.29

Both ranges overlap. "purple bicycle quarterly tax rebate" scores closer than
several genuine benchmark questions, and a distance-based indicator elsewhere in
this project's history rated a US/FDA question **high** confidence while
answering it from Indian food law. A confidence badge that is wrong in the
dangerous direction is worse than no badge, because it invites trust.

So confidence here is computed from evidence that the answer actually held
together, all of it downstream of validation:

  * how many of the three substantive steps kept a citation after validation
  * how many distinct sources back the answer
  * whether dense and lexical retrieval independently agreed on the evidence
  * whether the model tried to cite anything that failed validation

Every component is observable in the response, so the score can be explained
rather than asserted - `reasons` carries that explanation to the UI.
"""

from __future__ import annotations

from dataclasses import dataclass

from .retrieval import RetrievalResult
from .schemas import ConfidenceLevel, ReasoningStep

# Weights sum to 1.0. Citation survival dominates because it is the signal most
# directly tied to the thing we care about: a claim that could be sourced.
W_STEPS = 0.45
W_BREADTH = 0.30
W_AGREEMENT = 0.25

# A model that cited something unverifiable was guessing, even if other
# citations survived. Multiplicative so it damps an otherwise good score.
REJECTION_PENALTY = 0.80

HIGH_THRESHOLD = 0.75
MODERATE_THRESHOLD = 0.45

# Three distinct sources is "well supported"; beyond that adds little.
BREADTH_TARGET = 3
# Agreement is measured over at most this many top evidence items.
AGREEMENT_WINDOW = 5


@dataclass
class ConfidenceAssessment:
    level: ConfidenceLevel
    score: float
    reasons: list[str]


def assess(
    steps: list[ReasoningStep],
    citation_ids: list[str],
    rejected_ids: list[str],
    result: RetrievalResult,
) -> ConfidenceAssessment:
    """Score how well-supported an answer is. Never raises."""
    reasons: list[str] = []

    # 1. Did the substantive steps keep a citation through validation?
    substantive = [s for s in steps if s.step in (1, 2, 3)]
    cited_steps = sum(1 for s in substantive if s.citation_ids and not s.abstained)
    steps_score = cited_steps / len(substantive) if substantive else 0.0
    if cited_steps == len(substantive) and substantive:
        reasons.append("every reasoning step is backed by a cited provision")
    elif cited_steps:
        reasons.append(
            f"{cited_steps} of {len(substantive)} reasoning steps could be sourced; "
            "the rest were left unanswered rather than asserted"
        )
    else:
        reasons.append("no reasoning step could be backed by a citation")

    # 2. How many distinct sources, not just how many citations?
    acts = set()
    for chunk_id in citation_ids:
        for item in result.evidence:
            if item.chunk_id == chunk_id:
                acts.add(str(item.metadata.get("act_name", chunk_id)))
                break
    breadth_score = min(len(acts), BREADTH_TARGET) / BREADTH_TARGET
    if len(acts) >= BREADTH_TARGET:
        reasons.append(f"supported by {len(acts)} independent sources")
    elif len(acts) == 1:
        reasons.append("rests on a single source")

    # 3. Did two independent retrieval methods agree on this evidence?
    window = result.evidence[:AGREEMENT_WINDOW]
    both = sum(1 for e in window if e.dense_rank is not None and e.lexical_rank is not None)
    agreement_score = both / len(window) if window else 0.0
    if both and window:
        reasons.append(
            f"{both} of the top {len(window)} passages were found by both semantic "
            "and keyword search"
        )
    elif window:
        reasons.append("semantic and keyword search did not agree on any top passage")

    score = (
        W_STEPS * steps_score
        + W_BREADTH * breadth_score
        + W_AGREEMENT * agreement_score
    )

    if rejected_ids:
        score *= REJECTION_PENALTY
        reasons.append(
            f"{len(rejected_ids)} citation(s) the model produced could not be verified "
            "and were rejected"
        )

    if score >= HIGH_THRESHOLD and len(acts) < 2:
        # Full step coverage and tight retrieval agreement can push a
        # single-source answer over the line. One act corroborating itself is
        # not "well supported", however cleanly the steps were cited - so this
        # is capped rather than scored down, to keep the reason honest.
        level = ConfidenceLevel.MODERATE
        reasons.append("capped: a single source cannot make an answer well supported")
    elif score >= HIGH_THRESHOLD:
        level = ConfidenceLevel.HIGH
    elif score >= MODERATE_THRESHOLD:
        level = ConfidenceLevel.MODERATE
    else:
        level = ConfidenceLevel.LIMITED

    return ConfidenceAssessment(level=level, score=round(score, 3), reasons=reasons)
