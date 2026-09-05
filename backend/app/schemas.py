"""Pydantic contracts shared by the backend and (from Phase 6) the frontend.

Treat these as the API surface. Changing a field name here changes the UI.
"""

from __future__ import annotations

from enum import Enum

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator


# Input bounds, shared by the request models and their validators.
# History entries are user text heading for an LLM prompt, exactly like
# `question`, so they get the same per-item ceiling.
MAX_QUESTION_CHARS = 2000
HISTORY_TURNS = 8


class Category(str, Enum):
    """The six regulatory categories from the problem statement, plus two
    escape hatches.

    The escape hatches are not padding. Many in-scope questions describe no
    formulation at all ("how do I register a GI?", "what is ABS?"), and forcing
    those into one of the six would produce a confident wrong answer. And when a
    formulation IS implied but underdetermined, the PS explicitly asks for the
    minimum clarifying question rather than a guess.
    """

    CLASSICAL_GENERIC = "classical_generic"
    PATENT_PROPRIETARY = "patent_proprietary"
    NEW_DRUG = "new_drug"
    PHYTOPHARMACEUTICAL = "phytopharmaceutical"
    AYURVEDA_AAHAR = "ayurveda_aahar"
    COSMETIC = "cosmetic"
    NOT_APPLICABLE = "not_applicable"
    NEEDS_CLARIFICATION = "needs_clarification"


# Human-facing labels. The UI should render these, never the raw enum value.
CATEGORY_LABELS: dict[Category, str] = {
    Category.CLASSICAL_GENERIC: "Classical / generic Ayurvedic medicine",
    Category.PATENT_PROPRIETARY: "Patent or proprietary Ayurvedic medicine",
    Category.NEW_DRUG: "New / non-classical drug",
    Category.PHYTOPHARMACEUTICAL: "Phytopharmaceutical drug",
    Category.AYURVEDA_AAHAR: "Ayurveda Aahara / nutraceutical",
    Category.COSMETIC: "Cosmetic",
    Category.NOT_APPLICABLE: "Not a formulation-classification question",
    Category.NEEDS_CLARIFICATION: "Needs clarification",
}


class AbstentionKind(str, Enum):
    """Why the system declined to answer.

    The PS grades "safe abstention on out-of-scope or uncertain queries", and
    these reasons are not interchangeable: a foreign-jurisdiction question is a
    scope boundary we can state precisely, while a vague one just needs the user
    to say more. The UI should treat them differently.
    """

    NONE = "none"
    NO_EVIDENCE = "no_evidence"
    TOO_VAGUE = "too_vague"
    FOREIGN_JURISDICTION = "foreign_jurisdiction"
    OUT_OF_SCOPE = "out_of_scope"
    # The safety check itself could not run (LLM outage or rate limit).
    # Distinct from the others: the user should retry, not rephrase.
    GATE_UNAVAILABLE = "gate_unavailable"
    # Small talk answered without retrieval. Not a refusal - the UI should
    # render it as a plain reply, with no "not answered" framing.
    CONVERSATIONAL = "conversational"


class ConfidenceLevel(str, Enum):
    """How well-supported an answer is.

    Deliberately three coarse buckets, not a percentage: a two-decimal number
    implies a precision this cannot have. See confidence.py for why the score
    is built on citation survival rather than vector distance.
    """

    HIGH = "high"
    MODERATE = "moderate"
    LIMITED = "limited"


CONFIDENCE_LABELS: dict[ConfidenceLevel, str] = {
    ConfidenceLevel.HIGH: "Well supported",
    ConfidenceLevel.MODERATE: "Partly supported",
    ConfidenceLevel.LIMITED: "Thinly supported",
}


class CategoryContrast(BaseModel):
    """One category's position in a side-by-side comparison.

    The problem statement's central point is that the SAME product has opposite
    IP postures depending on its regulatory category. Answering one category at
    a time hides that; this shows it.
    """

    category: Category
    label: str
    posture: str = Field(description="What this category means for the product, 2-3 sentences")
    patentable: str = Field(description="Short verdict on patentability under this category")
    citation_ids: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    """A verified pointer into the corpus.

    Every field is derived from a real chunk. `section` is extracted from the
    chunk's own text and confirmed present there - it is never taken from the
    `section_or_clause` metadata field, which frequently contains footnote text
    rather than a heading.
    """

    chunk_id: str
    act_name: str
    section: str | None = Field(default=None, description="Verified provision reference")
    page: int | None = None
    source_file: str | None = None
    regime: str | None = None
    excerpt: str = Field(description="Verbatim corpus text, for the citation card")

    @property
    def display(self) -> str:
        """What the UI shows as the citation line."""
        parts = [self.act_name]
        if self.section:
            parts.append(self.section)
        if self.page:
            parts.append(f"p. {self.page}")
        return ", ".join(parts)


class ClassificationResult(BaseModel):
    """Output of the formulation classifier.

    `defining_source_id` is a real chunk_id from the corpus - the provision that
    defines the chosen category. It is validated against the corpus before this
    object is returned, so it can never name a source that does not exist.
    """

    category: Category
    label: str = Field(description="Human-readable category name")
    rationale: str = Field(description="Why this category, in one or two sentences")
    defining_source_id: str | None = Field(
        default=None, description="chunk_id of the provision defining this category"
    )
    defining_source_name: str | None = Field(
        default=None, description="Display name of that source, e.g. the act name"
    )
    clarifying_question: str | None = Field(
        default=None,
        description="Set only when category is needs_clarification: the single "
        "most decisive question to ask the user",
    )

    @property
    def is_formulation(self) -> bool:
        """True when an actual regulatory category was determined."""
        return self.category not in (
            Category.NOT_APPLICABLE,
            Category.NEEDS_CLARIFICATION,
        )


# The four steps are fixed by the problem statement's core loop. Step 4 is a
# statement about the *scope* of our corpus rather than a claim about law, so it
# is the only step permitted to carry no citation.
STEP_TITLES: dict[int, str] = {
    1: "Classification",
    2: "Legal position",
    3: "Protection / action route",
    4: "Jurisdiction note",
}
STEPS_REQUIRING_CITATION = (1, 2, 3)


class ReasoningStep(BaseModel):
    """One step of the reasoning trail.

    `abstained` is not a failure state to hide - it is the system declining to
    assert something it cannot cite, which the PS grades explicitly.
    """

    step: int
    title: str
    content: str
    citation_ids: list[str] = Field(default_factory=list)
    abstained: bool = False


class Answer(BaseModel):
    """The full response. This is the contract the frontend renders."""

    question: str
    # The standalone question actually used, once conversation context was
    # resolved. Differs from `question` only for follow-ups; the UI shows it so
    # the user can see how their shorthand was interpreted.
    resolved_question: str | None = None
    jurisdiction: str = "india"
    # A single-sentence direct answer. Most users want the conclusion first and
    # the reasoning underneath, not four paragraphs to read before they know
    # whether the answer was yes or no.
    headline: str | None = None
    # Citations backing the headline specifically. The headline is the sentence
    # users actually read, and it used to be the ONE piece of model prose that
    # bypassed the citation guard entirely - steps get their content replaced
    # when nothing survives validation, the headline was passed through verbatim.
    # It is now validated on the same allowed set as the steps.
    headline_citation_ids: list[str] = Field(default_factory=list)
    # True when the headline could not be tied to any verified source. The UI
    # marks it as an unsourced summary rather than dropping it, because a
    # correct one-line answer is still useful - it just must not LOOK sourced.
    headline_unsourced: bool = False
    confidence: ConfidenceLevel | None = None
    confidence_label: str | None = None
    confidence_score: float | None = None
    confidence_reasons: list[str] = Field(default_factory=list)
    classification: ClassificationResult | None = None
    steps: list[ReasoningStep] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)

    abstained: bool = False
    abstention_kind: AbstentionKind = AbstentionKind.NONE
    abstention_message: str | None = None
    clarifying_question: str | None = None

    # Suggested follow-ups, offered after small talk so a new user has somewhere
    # to start. Empty for substantive answers.
    example_questions: list[str] = Field(default_factory=list)

    # Citation ids the model produced that failed validation. Surfaced rather
    # than swallowed: it is evidence the guard is doing its job.
    rejected_citation_ids: list[str] = Field(default_factory=list)

    # Set when a supporting step ran in a degraded mode - today, when query
    # expansion could not run. Expansion is what bridges "can my churna be
    # patented?" to the statute's own wording, and without it the flagship
    # benchmark does not retrieve Section 3(p) at all. It used to fail silently,
    # so a rate-limited request answered from the wrong provisions while looking
    # completely normal. Now it is visible in the response and on screen.
    search_degraded: bool = False
    degraded_reason: str | None = None

    # A path to a human IP facilitator, offered only when the user has a real
    # legal need this system cannot meet - see escalation.py for why the
    # negative cases (too_vague, out_of_scope, gate_unavailable) matter as much
    # as the positive ones. An offer on every answer is noise people learn to
    # ignore.
    escalate: bool = False
    escalation_reason: str | None = None

    disclaimer: str = (
        "This is information, not legal advice. It cites primary legal sources "
        "but is not a substitute for a qualified IP practitioner."
    )


class QueryRequest(BaseModel):
    """Body for POST /query and POST /classify."""

    # StringConstraints, not Field(strip_whitespace=...) - the latter is not a
    # Pydantic v2 field kwarg and is silently ignored, which is why "   " was
    # still returning HTTP 200. Stripping happens before min_length is applied,
    # so a whitespace-only question is now rejected at the API boundary.
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=2, max_length=MAX_QUESTION_CHARS)
    ]
    # Earlier questions in this conversation, oldest first. The API stays
    # stateless - the client owns the transcript - but a follow-up like "what
    # about trademarking it?" is meaningless alone, so the server rewrites it
    # into a standalone question before retrieving. See generation.contextualise.
    #
    # This was `max_length=8`, which REJECTED a longer transcript with a 422.
    # The client sends every prior turn, so any session that ran past eight
    # questions - or resumed a stored one - started failing outright, showing
    # the user a raw Pydantic validation string. Surplus history is not a client
    # error: it is context we simply do not need. So it is truncated instead.
    history: list[str] = Field(default_factory=list)
    # Present and validated from day one so the frontend toggle is real plumbing.
    # Only "india" is served today; "international" returns a clear 501-style
    # abstention rather than pretending, because the corpus has no treaty texts.
    jurisdiction: str = Field(default="india", pattern="^(india|international)$")
    top_k: int = Field(default=12, ge=1, le=20)
    # Consent to retain the QUESTION TEXT in the audit log. Defaults to False:
    # the operational record that makes the system auditable carries no user
    # content at all, so keeping the text is a separate choice the user makes,
    # not a side effect of asking. See audit.py.
    log_consent: bool = False

    @field_validator("history")
    @classmethod
    def _bound_history(cls, value: list[str]) -> list[str]:
        """Keep the most recent turns, and bound each one, without rejecting.

        Two separate limits, for two separate reasons:

        * `HISTORY_TURNS` - only the last few turns carry usable context, and
          the contextualisation prompt already reads just the final four. Older
          turns cost prompt tokens and add stale subject matter.
        * `MAX_QUESTION_CHARS` - each entry is user-controlled text that lands
          in an LLM prompt. The `question` field has always been capped; history
          entries were not capped at all, so a client could send unbounded text
          through the same path.

        Blank entries are dropped: they contribute nothing and would waste a
        numbered slot in the prompt.
        """
        cleaned = [" ".join(str(item).split())[:MAX_QUESTION_CHARS] for item in value]
        return [item for item in cleaned if item][-HISTORY_TURNS:]


class HealthResponse(BaseModel):
    status: str
    chunks_in_json: int
    chunks_in_vector_db: int
    collection: str
    embed_model: str
    generation_model: str
    anchor_problems: list[str] = Field(default_factory=list)
    # Aggregate of the local audit trail, so auditability is demonstrable rather
    # than asserted. Counts only - never question text.
    audit: dict = Field(default_factory=dict)


class CompareRequest(BaseModel):
    """Body for POST /compare."""

    product: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)
    ]
    log_consent: bool = False


class ComparisonResult(BaseModel):
    """Side-by-side regulatory postures for one product."""

    product: str
    contrasts: list[CategoryContrast] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    abstained: bool = False
    abstention_message: str | None = None
    # Same meaning as on Answer. Carried here too because a guard that exists on
    # one path and not the other is how inconsistencies become bugs - the raw
    # chunk-id stripping lived only in comparison.py for exactly that reason.
    search_degraded: bool = False
    degraded_reason: str | None = None
    disclaimer: str = (
        "This is information, not legal advice. It cites primary legal sources "
        "but is not a substitute for a qualified IP practitioner."
    )
