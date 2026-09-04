"""Pydantic contracts shared by the backend and (from Phase 6) the frontend.

Treat these as the API surface. Changing a field name here changes the UI.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


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
    classification: ClassificationResult | None = None
    steps: list[ReasoningStep] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)

    abstained: bool = False
    abstention_kind: AbstentionKind = AbstentionKind.NONE
    abstention_message: str | None = None
    clarifying_question: str | None = None

    # Citation ids the model produced that failed validation. Surfaced rather
    # than swallowed: it is evidence the guard is doing its job.
    rejected_citation_ids: list[str] = Field(default_factory=list)

    disclaimer: str = (
        "This is information, not legal advice. It cites primary legal sources "
        "but is not a substitute for a qualified IP practitioner."
    )


class QueryRequest(BaseModel):
    """Body for POST /query and POST /classify."""

    question: str = Field(min_length=1, max_length=2000)
    # Earlier questions in this conversation, oldest first. The API stays
    # stateless - the client owns the transcript - but a follow-up like "what
    # about trademarking it?" is meaningless alone, so the server rewrites it
    # into a standalone question before retrieving. See generation.contextualize.
    history: list[str] = Field(default_factory=list, max_length=8)
    # Present and validated from day one so the frontend toggle is real plumbing.
    # Only "india" is served today; "international" returns a clear 501-style
    # abstention rather than pretending, because the corpus has no treaty texts.
    jurisdiction: str = Field(default="india", pattern="^(india|international)$")
    top_k: int = Field(default=12, ge=1, le=20)


class HealthResponse(BaseModel):
    status: str
    chunks_in_json: int
    chunks_in_vector_db: int
    collection: str
    embed_model: str
    generation_model: str
    anchor_problems: list[str] = Field(default_factory=list)
