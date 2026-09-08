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
    # The user asked us to forecast their own case or to recommend whether to
    # bring one. Distinct from out_of_scope on purpose: the SUBJECT is squarely
    # in scope - the Patents Act does govern infringement suits - so refusing it
    # as "off-topic" is both wrong and unhelpful. What we cannot do is apply the
    # law to facts we cannot see. This is also the clearest case in the whole
    # system for handing someone to a person, so it escalates.
    LEGAL_ADVICE = "legal_advice"


class ResponseStyle(str, Enum):
    """How an answer is phrased. Never what it says or what it cites.

    `plain` is applied as a REPHRASING of a finished legal answer, not as a
    different generation. That is a deliberate design choice: if style were a
    prompt instruction on the main call, the model would re-choose its citations
    each time and the two styles could legitimately cite different provisions -
    at which point "the same answer in plainer words" would be a claim we could
    not actually make. Rewriting a finished answer means the citation list and
    the classification are carried across UNCHANGED by construction rather than
    by hope, and the test for that is an equality check rather than a sample.
    """

    LEGAL = "legal"
    PLAIN = "plain"


class ConfidenceLevel(str, Enum):
    """How well the cited sources support an answer.

    Deliberately coarse buckets, not a percentage: a two-decimal number implies
    a precision this cannot have. See confidence.py for why the score is built
    on citation survival and specificity rather than vector distance.

    Four buckets rather than three. With three, the top one had to cover
    everything from "three acts agree and each names its provision" to "two
    steps cited the same page of one document", and measurement showed the
    middle bucket swallowing most real answers. STRONG separates an answer
    whose sources are broad AND provision-specific from one that is merely
    adequately sourced.

    This is an ordinal scale and nothing more. It is NOT calibrated against
    labelled outcomes, and it says nothing about whether the law was applied
    correctly - only about how well the answer is anchored in what was cited.
    """

    STRONG = "strong"
    HIGH = "high"
    MODERATE = "moderate"
    LIMITED = "limited"


# Phrased as statements about the EVIDENCE, never about correctness or legal
# certainty. "Confident" would be a claim about the outcome; these are claims
# about how much the cited sources carry.
CONFIDENCE_LABELS: dict[ConfidenceLevel, str] = {
    ConfidenceLevel.STRONG: "Strongly supported",
    ConfidenceLevel.HIGH: "Well supported",
    ConfidenceLevel.MODERATE: "Some support",
    ConfidenceLevel.LIMITED: "Thin evidence",
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


class TraceStep(BaseModel):
    """One stage of the pipeline that ran to produce an answer.

    Recorded so the orchestration is inspectable rather than asserted. A reader
    who wants to know whether this is "just ChatGPT" can read the stages, their
    timings and what each one decided.
    """

    stage: str
    #: "ok", "skipped" or "degraded" - a stage that failed soft still ran.
    status: str = "ok"
    ms: int = 0
    #: What this stage actually decided, in a few words. Facts, not narration.
    detail: str = ""


class RelatedProvision(BaseModel):
    """A provision that a cited passage points at, resolved to a real chunk.

    Derived from the passage's own text by `graph.py`, never from a model. It
    adds no claim to the answer - it is navigation, so that "subject to rule 21"
    stops being a dead end for the reader.
    """

    chunk_id: str
    act_name: str
    #: The reference as the citing passage words it, e.g. "Rule 21".
    provision: str
    page: int | None = None
    excerpt: str
    #: "outbound" - this citation points at it; "inbound" - it points at this
    #: citation. Shown to the reader, because the two mean different things.
    direction: str = "outbound"


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
    #: Provisions this passage cross-references, from the provision graph.
    #: Display only; populated after validation, and empty when nothing resolves.
    related: list[RelatedProvision] = Field(default_factory=list)

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


class TakeawayIntent(str, Enum):
    """What the question is actually asking for, which decides the vocabulary.

    Determined by the model as part of generation, never by scanning the
    question for words - a keyword rule like `if "patent" in question` is
    exactly what the generalisation requirement rules out, and it would put a
    patent label on "how do I stop someone patenting my formulation?".
    """

    PATENT = "patent"
    GI = "gi"
    ABS = "abs"
    TKDL = "tkdl"
    OTHER = "other"


# The permitted labels, per intent. This is a closed vocabulary and it is the
# mechanism by which a bare "yes, patentable" is made impossible rather than
# merely discouraged: the model picks a label, the label is checked against this
# table, and anything outside it becomes REQUIRES_VERIFICATION.
#
# Every label is hedged on purpose. This banner is a preliminary orientation
# produced by a document search, not a legal opinion, and a categorical
# yes/no would be read as the latter however much small print sits beneath it.
REQUIRES_VERIFICATION = "Requires verification"
INSUFFICIENT_INFORMATION = "Insufficient information"

TAKEAWAY_LABELS: dict[TakeawayIntent, tuple[str, ...]] = {
    TakeawayIntent.PATENT: (
        "Potentially patentable",
        "Likely excluded",
        REQUIRES_VERIFICATION,
        INSUFFICIENT_INFORMATION,
    ),
    TakeawayIntent.GI: (
        "GI route may be relevant",
        "Unlikely to qualify",
        REQUIRES_VERIFICATION,
    ),
    TakeawayIntent.ABS: (
        "ABS/NBA requirements may apply",
        "Unlikely to apply",
        REQUIRES_VERIFICATION,
    ),
    TakeawayIntent.TKDL: (
        "High prior-art risk",
        "Low apparent prior-art risk",
        REQUIRES_VERIFICATION,
    ),
    # A question that fits none of the above still gets an honest orientation
    # rather than a label borrowed from a regime it does not belong to.
    TakeawayIntent.OTHER: (REQUIRES_VERIFICATION, INSUFFICIENT_INFORMATION),
}


class Takeaway(BaseModel):
    """A one-line orientation above the reasoning trail.

    Shown only when there is something to assess. A definitional or procedural
    question - "what is a GI tag?" - gets no banner, because there is no matter
    to take a view on and a label would invent one.

    `reason` is held to the same citation standard as a step: it carries its
    own ids, they are validated against the retrieved evidence, and when none
    survive the banner says so rather than looking sourced. That is the lesson
    of the headline defect - any new prose channel to the user needs its own
    validation, or it becomes the hole in the guard.
    """

    intent: TakeawayIntent
    label: str = Field(description="One of TAKEAWAY_LABELS for this intent")
    reason: str = Field(description="One plain-language sentence, never a bare yes/no")
    citation_ids: list[str] = Field(default_factory=list)
    unsourced: bool = False


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
    # Which phrasing this was rendered in. The citations and the
    # classification are identical across styles by construction - only the
    # prose differs - so this is a display fact, not a provenance one.
    response_style: str = "legal"
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
    #: One-line orientation above the trail. None for definitional or
    #: procedural questions, and for every abstention.
    takeaway: Takeaway | None = None
    #: The pipeline stages that ran, in order, with timings.
    trace: list[TraceStep] = Field(default_factory=list)
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

    # Provision references ("Section 3(e)") the model wrote into prose that no
    # retrieved chunk contains. The sentence carrying them is removed before the
    # answer ships. Surfaced for the same reason as rejected ids: a guard you
    # can see is worth more than one you cannot, and this one catches the
    # failure that looks MOST authoritative - a real-sounding section number
    # sitting beside perfectly valid citations.
    unsupported_provisions: list[str] = Field(default_factory=list)

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
    # Phrasing only. Applied as a rephrasing pass over the finished answer, so
    # asking the same question in both styles costs one extra call rather than a
    # second full generation - and cannot change what was cited.
    response_style: ResponseStyle = ResponseStyle.LEGAL
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
    # Per-jurisdiction chunk counts. The India/International toggle is only
    # honest if you can see that both sides actually hold documents.
    chunks_by_jurisdiction: dict[str, int] = Field(default_factory=dict)
    collection: str
    embed_model: str
    generation_model: str
    # Every (provider, model) that could serve a request right now, best
    # first. Surfaced because "which model answered" stopped being a single
    # value once the chain spanned three independent accounts - and when a
    # provider is capped, seeing the fallback engage is how you tell a
    # degraded system from a broken one.
    llm_chain: list[str] = Field(default_factory=list)
    anchor_problems: list[str] = Field(default_factory=list)
    # Shape of the provision graph, plus anything wrong with it. Reported for
    # the same reason as anchor_problems: the graph resolves chunk ids, so a
    # corpus rebuild that renumbers them must be visible at startup rather than
    # discovered as dead links in a citation card.
    graph: dict = Field(default_factory=dict)
    graph_problems: list[str] = Field(default_factory=list)
    # Aggregate of the local audit trail, so auditability is demonstrable rather
    # than asserted. Counts only - never question text.
    audit: dict = Field(default_factory=dict)



class AuditTrail(BaseModel):
    """The system's record of its own behaviour, served for inspection.

    Two claims the problem statement asks for pull against each other -
    auditability wants a record, data protection wants none - so both are shown
    at once: the operational rows, and the count of rows that kept a question
    (zero unless somebody opted in). `redacted_fields` names what was removed on
    the way out, because a redaction nobody can see is indistinguishable from a
    field that was never collected.
    """

    summary: dict = Field(default_factory=dict)
    entries: list[dict] = Field(default_factory=list)
    redacted_fields: list[str] = Field(default_factory=list)
    retention: str = ""


class JurisdictionPoint(BaseModel):
    """One similarity or difference between the two legal systems.

    The shape is the safeguard. A free-text paragraph comparing two
    jurisdictions is one careless sentence away from "the law requires X",
    leaving a reader unable to tell which system requires it - which is the
    conflation the problem statement forbids. So a point cannot be expressed
    without saying, per side, what that side holds and which of ITS OWN
    citations says so. There is no field in which a blended claim can live.
    """

    kind: str = Field(description='"similarity" or "difference"')
    summary: str = Field(description="One sentence naming what is being compared")

    national_claim: str | None = Field(
        default=None, description="What the Indian answer established, in its own terms"
    )
    national_citation_ids: list[str] = Field(default_factory=list)

    international_claim: str | None = Field(
        default=None, description="What the international answer established"
    )
    international_citation_ids: list[str] = Field(default_factory=list)


class JurisdictionComparison(BaseModel):
    """Two independently generated answers, plus a comparison of them.

    `national` and `international` are complete Answers produced by separate
    retrieval and generation passes over separate corpora - not one answer
    relabelled, and not one jurisdiction's chunks reused for the other. They are
    carried whole so the UI can render each with its own citations and the user
    can read either on its own.

    The comparison is a THIRD call that sees only those two finished answers. It
    may restate and contrast them; it may not introduce law of its own, and
    every claim it makes is validated back to the citations of the side it is
    attributed to.
    """

    question: str
    national: Answer
    international: Answer
    points: list[JurisdictionPoint] = Field(default_factory=list)

    # Points the synthesis produced that failed validation - a claim citing the
    # wrong jurisdiction's sources, or citing something neither answer used.
    # Surfaced rather than swallowed, like rejected_citation_ids: a guard you
    # can see is worth more than one you cannot.
    rejected_points: list[str] = Field(default_factory=list)

    synthesis_unavailable: bool = False
    synthesis_message: str | None = None

    disclaimer: str = (
        "This is information, not legal advice. It cites primary legal sources "
        "but is not a substitute for a qualified IP practitioner."
    )


class NextStep(BaseModel):
    """One practical thing the user could do next.

    Citations are required for the same reason every other claim needs them: a
    step like "apply for a licence under Rule 158-B" is a statement about the
    law wearing the clothes of advice, and it is the most advice-like text this
    product produces. `jurisdiction` records which corpus it came from, so a
    step drawn from treaty text can never be read as an Indian requirement.
    """

    text: str
    citation_ids: list[str] = Field(default_factory=list)
    jurisdiction: str = Field(
        default="national", description='"national" or "international"'
    )


class NextSteps(BaseModel):
    """The optional "what this means next" block.

    Deliberately skippable. Not every question earns one: "what is a GI tag?"
    is answered by the answer, and appending three imperatives to it would be
    padding that trains people to stop reading. `applicable` is the model's
    judgement on whether the question was actually asking what to DO.
    """

    applicable: bool = True
    steps: list[NextStep] = Field(default_factory=list)
    # Why no steps, when there are none. Shown instead of an empty section.
    reason: str | None = None
    unavailable: bool = False
    # Steps that named a source the source answer never cited. Surfaced like
    # rejected_citation_ids: this section is the most advice-like text here, so
    # its guard should be the most visible.
    rejected: list[str] = Field(default_factory=list)
    # Repeated ON this block, not only at the foot of the page. This is the
    # section a reader is most likely to act on directly.
    disclaimer: str = (
        "General guidance based only on the sources cited above - not a legal "
        "determination, and not a substitute for a qualified IP practitioner."
    )


class NextStepsRequest(BaseModel):
    """Body for POST /next-steps.

    Takes an answer the client already has rather than a question, because this
    step must NOT retrieve. Re-retrieving would let it introduce provisions the
    answer never established, which is the one thing a "what to do next" section
    must not do. Opt-in by construction: nothing calls this unless asked.
    """

    answer: Answer | None = None
    comparison: JurisdictionComparison | None = None
    style: ResponseStyle = ResponseStyle.LEGAL


class CompareJurisdictionsRequest(BaseModel):
    """Body for POST /compare-jurisdictions.

    Opt-in by construction: this endpoint costs three generation passes, so
    nothing calls it unless the user asked for a comparison.
    """

    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=2, max_length=MAX_QUESTION_CHARS)
    ]
    top_k: int = Field(default=12, ge=1, le=20)
    log_consent: bool = False
    # Answers the client already has on screen. When both are supplied the
    # server skips generation entirely and only runs the synthesis - which is
    # what makes "ask nationally, then reveal the international view, then
    # compare" cost one call rather than nine, and guarantees the comparison
    # describes exactly the two answers the reader is looking at rather than
    # two freshly generated ones that might differ.
    national: Answer | None = None
    international: Answer | None = None


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

# ---------------------------------------------------------------------------
# Export readiness
# ---------------------------------------------------------------------------


class ReadinessStatus(str, Enum):
    """What was actually found for one checklist item.

    Derived, never assigned by rule. A status is only as good as the evidence
    behind it, so `NOT_COVERED` is not a failure mode here - it is the honest
    answer whenever the corpus does not reach an item, and it is what the code
    forces when no citation survives validation.
    """

    VERIFIED = "verified"
    NEEDS_VERIFICATION = "needs_verification"
    BLOCKER = "blocker"
    NOT_COVERED = "not_covered"


class ReadinessItem(BaseModel):
    """One line of the readiness checklist."""

    title: str = Field(description="The requirement, in a few words")
    detail: str = Field(description="What the sources actually say about it")
    status: ReadinessStatus
    #: Why this status and not another - shown next to the icon so the state is
    #: interrogable rather than decorative.
    status_reason: str = ""
    citation_ids: list[str] = Field(default_factory=list)


class ReadinessSection(BaseModel):
    """One side of the report. Kept apart so the two are never conflated."""

    #: "national" or "international" - which corpus every item here came from.
    jurisdiction: str
    heading: str
    #: Set when the corpus does not reach this side at all. The section then
    #: carries no items, and says so, rather than degrading into generic advice.
    covered: bool = True
    uncovered_reason: str | None = None
    items: list[ReadinessItem] = Field(default_factory=list)


class ExportReadinessRequest(BaseModel):
    """The short form behind the report."""

    product: str = Field(min_length=2, max_length=MAX_QUESTION_CHARS)
    ingredients: str = Field(default="", max_length=MAX_QUESTION_CHARS)
    #: Optional. Left unset, the existing classifier infers it from `product`.
    category: Category | None = None
    health_claims: bool = False
    target_country: str = Field(min_length=2, max_length=120)
    log_consent: bool = False
    style: ResponseStyle = ResponseStyle.LEGAL


class ExportReadinessReport(BaseModel):
    """India-side and target-market readiness, each grounded in its own corpus."""

    product: str
    target_country: str
    classification: ClassificationResult | None = None
    #: How the target market frames this kind of product, when the international
    #: corpus actually says. None when it does not - never inferred.
    target_framing: str | None = None
    target_framing_citation_ids: list[str] = Field(default_factory=list)

    india: ReadinessSection | None = None
    target: ReadinessSection | None = None

    #: Ordered next steps. May draw on both sides; each carries its own
    #: jurisdiction so a treaty-derived step can never read as an Indian duty.
    action_plan: list[NextStep] = Field(default_factory=list)

    citations: list[Citation] = Field(default_factory=list)
    rejected_citation_ids: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel | None = None
    confidence_label: str | None = None
    confidence_score: float | None = None
    confidence_reasons: list[str] = Field(default_factory=list)

    abstained: bool = False
    abstention_kind: AbstentionKind = AbstentionKind.NONE
    abstention_message: str | None = None
    escalate: bool = False
    escalation_reason: str | None = None

    disclaimer: str = (
        "This is information, not legal advice. It is a preliminary readiness view "
        "assembled from cited sources, not a regulatory clearance. Verify every "
        "requirement with the competent authority before exporting."
    )
