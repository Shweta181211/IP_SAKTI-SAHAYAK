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
  * how SPECIFIC those citations are - a named section or rule, or just a page
  * how many distinct sources back the answer
  * whether dense and lexical retrieval independently agreed on the evidence
  * whether the model tried to cite anything that failed validation

Every component is observable in the response, so the score can be explained
rather than asserted - `reasons` carries that explanation to the UI.
"""

from __future__ import annotations

from dataclasses import dataclass

from .retrieval import RetrievalResult
from .schemas import Citation, ConfidenceLevel, ReasoningStep

# Weights sum to 1.0. Citation survival still leads, because it is the signal
# most directly tied to the thing we care about: a claim that could be sourced.
#
# SPECIFICITY is new, and it is the component the previous version was missing.
# Measured across sampled answers, an answer citing "Geographical Indications
# Act, Section 11" and one citing "Drugs and Cosmetics Rules 1945, provision not
# identified, p.1" scored identically - both had a surviving citation from one
# act, and nothing in the score could tell a pinpoint reference from a gesture
# at a page. That is exactly the discrimination a reader needs, so it now
# carries real weight.
#
# It became worth scoring only once citations.py could actually resolve
# provisions reliably: before that fix the D&C Rules named a provision on 11%
# of its chunks, so this component would have been measuring the extractor's
# blind spots rather than the answer's quality.
W_STEPS = 0.35
W_SPECIFICITY = 0.25
W_BREADTH = 0.20
W_AGREEMENT = 0.20

# A model that cited something unverifiable was guessing, even if other
# citations survived.
#
# This was multiplicative (x0.80), and it could not change the outcome in the
# case that mattered. Measured: the flagship answer scored a perfect 1.0, was
# multiplied to exactly 0.80 - still above HIGH_THRESHOLD - and a model that had
# just tried to cite a chunk it was never shown still produced a "Well
# supported" badge. Subtractive, per rejection, so it actually bites, and the
# level is capped outright as well: guessing at a source is a statement about
# the answer's reliability that no amount of other evidence cancels.
REJECTION_PENALTY_PER_ID = 0.15
MAX_REJECTION_PENALTY = 0.45

STRONG_THRESHOLD = 0.85
HIGH_THRESHOLD = 0.70
MODERATE_THRESHOLD = 0.45

# Four distinct provisions is the top of the breadth scale. Three saturated it:
# almost every answered question cites three provisions, so the component sat at
# 1.0 and stopped discriminating - the same way the agreement component once did.
BREADTH_TARGET = 4
# Agreement is measured over at most this many top evidence items.
AGREEMENT_WINDOW = 5
# A passage counts as "both retrievers agreed" only if BOTH ranked it this high
# among their own candidates. Mere presence in a 40-deep candidate list is not
# agreement - see the comment in assess().
AGREEMENT_RANK_CUTOFF = 12

# Weakest to strongest. Used to apply ceilings without hard-coding comparisons
# between enum members, which are strings and would compare alphabetically.
LEVEL_ORDER = [
    ConfidenceLevel.LIMITED,
    ConfidenceLevel.MODERATE,
    ConfidenceLevel.HIGH,
    ConfidenceLevel.STRONG,
]


@dataclass
class ConfidenceAssessment:
    level: ConfidenceLevel
    score: float
    reasons: list[str]


def assess(
    steps: list[ReasoningStep],
    citations: list[Citation],
    rejected_ids: list[str],
    result: RetrievalResult,
) -> ConfidenceAssessment:
    """Score how well-supported an answer is. Never raises.

    Takes the BUILT citations rather than bare chunk ids. Specificity and
    breadth both need to know whether a citation resolved to a named provision,
    and that is decided by citations.py when the citation is constructed - so
    passing the finished objects avoids resolving every chunk a second time and
    keeps this module free of any corpus lookup, which is also what makes it
    unit-testable without a vector database.
    """
    citation_ids = [c.chunk_id for c in citations]
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

    # 2. How many distinct PROVISIONS, not how many citations and not how many
    #    acts.
    #
    # This counted distinct act names, and that penalised correctly focused
    # answers. Measured: a Geographical Indication registration question cited
    # Sections 2, 3 and 11 of the GI Act 1999 - three pinpointed provisions of
    # exactly the statute that governs the question - and was capped to the
    # middle band for "resting on a single source". Meanwhile an answer citing
    # one page each of three unrelated documents scored full breadth.
    #
    # Three sections of the governing act ARE corroboration; the same page cited
    # by three steps is not. So the unit is the provision: (act, section), or
    # (act, chunk) where no provision could be resolved. Act diversity still
    # helps, because different acts necessarily give different provisions.
    provisions = set()
    acts = set()
    for citation in citations:
        acts.add(citation.act_name)
        provisions.add((citation.act_name, citation.section or citation.chunk_id))
    breadth_score = min(len(provisions), BREADTH_TARGET) / BREADTH_TARGET
    if len(provisions) >= BREADTH_TARGET:
        reasons.append(
            f"supported by {len(provisions)} distinct provisions"
            + (f" across {len(acts)} sources" if len(acts) > 1 else " of one source")
        )
    elif len(provisions) == 1:
        reasons.append("rests on a single provision")

    # 3. How specific are the citations - a pinpointed provision, or a page?
    #
    # `Citation.section` is only ever set when citations.py could verify the
    # provision against the chunk's own text or place it in the document's
    # provision sequence, so a non-null section is a checked fact rather than a
    # model claim. An answer that can say "Section 11" is anchored in a way one
    # that can only say "page 1" is not, and a reader can go and read it.
    specific = sum(1 for c in citations if c.section)
    specificity_score = specific / len(citations) if citations else 0.0
    if citations and specific == len(citations):
        reasons.append("every citation resolves to a named provision")
    elif specific:
        reasons.append(
            f"{specific} of {len(citations)} citations resolve to a named provision; "
            "the rest cite the source and page only"
        )
    elif citations:
        reasons.append(
            "no citation resolves to a named provision - each points at a document "
            "and page rather than a specific section or rule"
        )

    # 4. Did two independent retrieval methods agree on this evidence?
    #
    # This used to test `dense_rank is not None and lexical_rank is not None`,
    # i.e. "did each retriever see this chunk anywhere in its 40-deep candidate
    # list". Nearly everything that survives into the final top-12 satisfies
    # that, so the component was saturated: every answer measured in testing
    # emitted the identical reason "5 of the top 5 passages were found by both",
    # making a 0.25-weighted component a constant that could not discriminate.
    #
    # Requiring both retrievers to have ranked the passage highly makes it a
    # real signal again: corroboration means they independently agreed it was
    # among the best matches, not merely that neither excluded it.
    # Measured over the passages the answer ACTUALLY CITES, not the top of the
    # retrieved list. Scoring the whole retrieval let this component describe a
    # search rather than an answer: an answer where two of three steps abstained
    # still collected the full 0.25 because the retrievers had agreed about
    # passages nobody could cite. That is how the bottom bucket became
    # unreachable - the worst answer measured across ~50 in the evaluation
    # scored 0.50 with an unsourced headline and one sourced step out of three.
    cited_set = set(citation_ids)
    cited_evidence = [e for e in result.evidence if e.chunk_id in cited_set]
    # The fallback cannot normally trigger: an answer with nothing cited becomes
    # a NO_EVIDENCE abstention before it reaches here. It exists so a caller that
    # scores a partially-built answer degrades rather than divides by zero.
    window = (cited_evidence or result.evidence)[:AGREEMENT_WINDOW]
    both = sum(
        1 for e in window
        if e.dense_rank is not None and e.dense_rank < AGREEMENT_RANK_CUTOFF
        and e.lexical_rank is not None and e.lexical_rank < AGREEMENT_RANK_CUTOFF
    )
    agreement_score = both / len(window) if window else 0.0
    if both and window:
        reasons.append(
            f"{both} of the {len(window)} cited passages were independently ranked highly "
            "by both semantic and keyword search"
        )
    elif window:
        reasons.append("semantic and keyword search did not agree on any cited passage")

    score = (
        W_STEPS * steps_score
        + W_SPECIFICITY * specificity_score
        + W_BREADTH * breadth_score
        + W_AGREEMENT * agreement_score
    )

    if rejected_ids:
        penalty = min(len(rejected_ids) * REJECTION_PENALTY_PER_ID, MAX_REJECTION_PENALTY)
        score = max(0.0, score - penalty)
        reasons.append(
            f"{len(rejected_ids)} citation(s) the model produced could not be verified "
            "and were rejected"
        )

    # ---- level, then ceilings -------------------------------------------
    #
    # The arithmetic proposes a band; specific structural weaknesses cap it.
    # Ceilings rather than jumps: with four bands, each weakness should cost
    # what it is worth. The previous version sent every capped answer straight
    # to MODERATE, so an answer with three acts, four provision-specific
    # citations and one abstaining step landed in the same band as one resting
    # on a single unpinpointed page - which is the flattening this scoring was
    # supposed to cure.
    #
    # A reason is recorded only when a ceiling actually bites, so `reasons`
    # never lists a cap that changed nothing.
    level = (
        ConfidenceLevel.STRONG if score >= STRONG_THRESHOLD
        else ConfidenceLevel.HIGH if score >= HIGH_THRESHOLD
        else ConfidenceLevel.MODERATE if score >= MODERATE_THRESHOLD
        else ConfidenceLevel.LIMITED
    )

    ceilings: list[tuple[ConfidenceLevel, str]] = []

    # An answer whose substantive steps mostly could NOT be sourced is thin,
    # whatever the arithmetic says. Without this the bottom band depends on
    # several weighted components failing at once, and in ~50 measured answers
    # that never happened - the badge had two usable states rather than three,
    # and the one it never used was the warning.
    if substantive and cited_steps * 2 <= len(substantive):
        ceilings.append((
            ConfidenceLevel.LIMITED,
            f"capped: only {cited_steps} of {len(substantive)} reasoning steps could be "
            "sourced, so this answer is thinly supported whatever else held up",
        ))

    # Reaching for a source that does not exist is exactly the failure this
    # badge warns about, and no amount of other evidence cancels it.
    if rejected_ids:
        ceilings.append((
            ConfidenceLevel.MODERATE,
            "capped: the model cited at least one source that failed verification",
        ))

    # One provision cited by every step is not corroboration. Note this is
    # deliberately NOT "one act": see the breadth block above for why that
    # version punished an answer for citing the right statute three times.
    if len(provisions) < 2:
        ceilings.append((
            ConfidenceLevel.MODERATE,
            "capped: a single provision cannot make an answer well supported",
        ))

    # Nothing cited resolves to a provision. The answer may be perfectly sound,
    # but every reference points at a document and a page, so a reader cannot
    # check any single claim against a specific rule. This is precisely the
    # case that used to score the same as a pinpointed citation.
    if citations and specificity_score == 0.0:
        ceilings.append((
            ConfidenceLevel.MODERATE,
            "capped: no citation names a provision, so nothing here can be checked "
            "against a specific section or rule",
        ))

    # The top band is reserved for answers where EVERY citation names its
    # provision. This is the discrimination the whole recalibration is for: an
    # answer a reader can check line by line against named sections is not the
    # same as one where some references only reach a page, even when both are
    # broad and both survived validation.
    if specificity_score < 1.0:
        ceilings.append((
            ConfidenceLevel.HIGH,
            "capped: not every citation resolves to a named provision",
        ))

    # A step that had to abstain is the answer telling you it ran out of
    # support. An answer carrying a blank step should not be labelled "well
    # supported" however well the rest of it held together, so this caps to the
    # middle band rather than merely excluding the top one.
    if cited_steps < len(substantive):
        ceilings.append((
            ConfidenceLevel.MODERATE,
            "capped: a reasoning step could not be sourced, so this is not fully supported",
        ))

    for ceiling, reason in ceilings:
        if LEVEL_ORDER.index(level) > LEVEL_ORDER.index(ceiling):
            level = ceiling
            reasons.append(reason)

    return ConfidenceAssessment(level=level, score=round(score, 3), reasons=reasons)
