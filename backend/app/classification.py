"""Formulation classification.

The problem statement requires the assistant to classify a product before it can
say anything useful about its IP or ABS posture - a classical formulation and a
new drug have opposite patent positions, so getting this wrong poisons the whole
answer.

Design notes:

* **No keyword matching.** There is no `if "churna" in question` anywhere here,
  and there must never be. The categories are decided by the model reading
  statutory definitions, so unseen phrasings and unseen products still work.

* **Definitions are quoted from our own corpus**, not written by us or recalled
  by the model. Each category is anchored to a real chunk_id, so the resulting
  classification can cite the provision that defines it.

* **Eight outcomes, not six.** See schemas.Category for why.
"""

from __future__ import annotations

import logging

from functools import lru_cache

from .corpus_index import all_chunks, chunk_exists, excerpt, get_chunk
from .llm import LLMUnavailable, complete_json
from .schemas import CATEGORY_LABELS, Category, ClassificationResult

logger = logging.getLogger(__name__)

# Category -> (act-name fragment, distinctive phrase from the defining provision).
#
# These used to be pinned chunk_ids. That was fragile: chunk_id embeds a
# positional doc_id, so re-running the ingestion pipeline renumbered documents
# and every anchor silently pointed at the wrong provision. Anchors are now
# resolved by CONTENT at load time, which survives any rebuild, and
# verify_anchors() still fails loudly if a provision genuinely disappears.
DEFINITION_ANCHORS: dict[Category, tuple[str, str]] = {
    Category.CLASSICAL_GENERIC: ("Drugs and Cosmetics Act", "authoritative books of"),
    Category.PATENT_PROPRIETARY: ("Drugs and Cosmetics Act", "patent or proprietary medicine"),
    Category.NEW_DRUG: ("Drugs and Cosmetics Rules", "new drug shall mean"),
    Category.PHYTOPHARMACEUTICAL: ("Drugs and Cosmetics Rules", "phytopharmaceutical drug"),
    Category.AYURVEDA_AAHAR: ("FSSAI", "Ayurveda Aahara"),
    Category.COSMETIC: ("Drugs and Cosmetics Act", "cleansing, beautifying"),
}


@lru_cache(maxsize=1)
def resolved_anchors() -> dict[Category, str]:
    """Find the chunk that defines each category, by searching the corpus.

    Picks the shortest matching chunk, which is reliably the definition itself
    rather than a long passage that merely mentions the phrase.
    """
    found: dict[Category, str] = {}
    for category, (act_fragment, phrase) in DEFINITION_ANCHORS.items():
        best: tuple[int, str] | None = None
        for chunk in all_chunks():
            if act_fragment.lower() not in str(chunk.get("act_name", "")).lower():
                continue
            text = " ".join(str(chunk["chunk_text"]).split())
            if phrase.lower() in text.lower():
                if best is None or len(text) < best[0]:
                    best = (len(text), chunk["chunk_id"])
        if best:
            found[category] = best[1]
    return found


def anchor_for(category: Category) -> str | None:
    return resolved_anchors().get(category)


def verify_anchors() -> list[str]:
    """Check every category still resolves to a real defining provision.

    Called at API startup so a corpus rebuild fails visibly instead of quietly
    quoting the wrong law.
    """
    resolved = resolved_anchors()
    problems: list[str] = []
    for category, (act_fragment, phrase) in DEFINITION_ANCHORS.items():
        chunk_id = resolved.get(category)
        if not chunk_id:
            problems.append(
                f"{category.value}: no chunk in '{act_fragment}' contains '{phrase}'"
            )
        elif get_chunk(chunk_id) is None:
            problems.append(f"{category.value}: resolved chunk {chunk_id} missing")
    return problems


def _definitions_block() -> str:
    """Render the statutory definitions the model classifies against."""
    parts = []
    for category, chunk_id in resolved_anchors().items():
        chunk = get_chunk(chunk_id)
        source = chunk["act_name"] if chunk else "unknown"
        parts.append(
            f"### {category.value}  ({CATEGORY_LABELS[category]})\n"
            f"Source: {source} [{chunk_id}]\n"
            f"{excerpt(chunk_id, 750)}"
        )
    return "\n\n".join(parts)


PROMPT_TEMPLATE = """You classify Ayurvedic products into Indian regulatory categories, \
so that IP and compliance guidance can be given correctly.

Below are the statutory definitions, quoted verbatim from Indian law. Classify using \
ONLY these definitions and the user's question. Do not rely on outside knowledge of \
Indian law.

{definitions}

## The eight possible outcomes

- `classical_generic` - formulation and method drawn from an authoritative First \
Schedule text.
- `patent_proprietary` - a formulation containing only ingredients referenced in \
authoritative texts, but the formulation itself is the manufacturer's own.
- `new_drug` - a non-classical drug requiring proof of safety and effectiveness.
- `phytopharmaceutical` - a purified, standardised plant fraction with defined markers.
- `ayurveda_aahar` - a food prepared per authoritative Ayurveda texts, not a medicine.
- `cosmetic` - applied externally for cleansing, beautifying or altering appearance, \
with no therapeutic claim.
- `not_applicable` - the question describes NO product at all. It asks about a \
procedure, a definition, or a legal concept in the abstract. Examples of the shape: \
"how do I register a geographical indication?", "what is access and benefit sharing?".
- `needs_clarification` - a product IS described, but the question omits the one fact \
that decides its category. Ask the single most decisive question, nothing more.

## How to decide (follow this order)

**Step 1 - Does the question describe, name or imply a specific product?**
Look for a thing someone makes, sells or owns: a formulation, a preparation, a recipe, \
an extract, a cream, a beverage, "my product", "our formulation".

**Step 2a - If YES, classify that product** into one of the six categories, or use \
`needs_clarification` if one missing fact would decide it. This holds *even when the \
question is about patents, IP, registration or enforcement*. Almost every question you \
receive will be an IP or regulatory question - that is the entire domain, so that fact \
tells you nothing about the category. A question that describes a product and asks \
whether it can be patented is still a classification question: the product's category \
is exactly what determines the patent answer.

**Step 2b - If NO product is described, return `not_applicable`.**

## Rules

1. `not_applicable` means "no product to classify", NOT "this is an IP question". Do \
not use it merely because the question mentions patents, GI, trade marks or ABS.
2. Use `needs_clarification` ONLY when the missing fact would change **the answer to the \
question the user actually asked** - not merely when the category is uncertain. Ask \
yourself: would the answer differ depending on which category this turns out to be? If the \
answer is the same either way, do NOT ask; pick the best-supported category, or \
`not_applicable` if the question is not about classification at all. Needless questions \
waste the user's time, and the problem statement asks for the *minimum* clarification.
   Many duties in this field apply to every Ayurvedic product alike, whatever its category - \
advertising restrictions, biodiversity access obligations, trade mark and copyright rules, \
labelling duties. When the question is about one of those, the category does not change the \
answer, so answer without asking. Category matters mainly for questions about patentability, \
the approval or licensing pathway, and what evidence of safety and efficacy is required.
3. `defining_source_id` must be one of the chunk ids shown above, or null. Never \
invent an id.
4. If the question is outside Ayurveda products, IP and regulation entirely, use \
`not_applicable` and say so in the rationale.

## Question

{question}

## Output

Return ONLY a JSON object, no markdown fence and no commentary:
{{"category": "<one of the eight values>",
  "answer_depends_on_category": <true or false>,
  "rationale": "<one or two sentences, grounded in the definitions above>",
  "defining_source_id": "<chunk id from above, or null>",
  "clarifying_question": "<only if category is needs_clarification, else null>"}}

`answer_depends_on_category` is a check on yourself: would the answer to THIS question actually change depending on which category the product turns out to be? Patentability, licensing pathway and safety-evidence requirements do depend on it. Advertising limits, biodiversity access duties, trade mark and copyright questions generally do not. Answer honestly - if it is false, you must not ask a clarifying question."""


def build_prompt(question: str) -> str:
    return PROMPT_TEMPLATE.format(definitions=_definitions_block(), question=question)


def classify(question: str) -> ClassificationResult:
    """Classify a user question into one of the eight outcomes.

    Never raises on a bad model response: an unparseable or invalid category
    degrades to needs_clarification, because a wrong confident category is more
    damaging here than an admission of uncertainty.
    """
    try:
        data = complete_json(build_prompt(question), max_tokens=600)
    except LLMUnavailable as exc:
        logger.error("Classification LLM call failed: %s", exc)
        return ClassificationResult(
            category=Category.NEEDS_CLARIFICATION,
            label=CATEGORY_LABELS[Category.NEEDS_CLARIFICATION],
            rationale="The classification service is temporarily unavailable.",
            clarifying_question="Please try again in a moment.",
        )

    try:
        category = Category(str(data.get("category", "")).strip())
    except ValueError:
        logger.warning("Model returned unknown category %r", data.get("category"))
        category = Category.NEEDS_CLARIFICATION

    # Structural guard against needless questions. Asking the user to classify
    # their product before answering "can I trademark the name?" wastes a turn,
    # because the trade mark answer is the same either way. Prompt instructions
    # alone did not hold this reliably, so the model has to declare the
    # dependency and we enforce it.
    if category is Category.NEEDS_CLARIFICATION and data.get(
        "answer_depends_on_category"
    ) is False:
        logger.info("Clarification suppressed: answer does not depend on category")
        category = Category.NOT_APPLICABLE

    # A source id is only kept if it genuinely exists in the corpus. This is the
    # same rule the answer citations follow: unverifiable means discarded.
    source_id = data.get("defining_source_id")
    source_id = str(source_id).strip() if source_id else None
    if source_id and not chunk_exists(source_id):
        logger.warning("Model cited non-existent chunk %r; dropping", source_id)
        source_id = None
    if source_id is None:
        source_id = anchor_for(category)

    chunk = get_chunk(source_id) if source_id else None

    clarifying = data.get("clarifying_question")
    if category is not Category.NEEDS_CLARIFICATION:
        clarifying = None
    elif not clarifying:
        clarifying = "Could you describe the product and how its formula was arrived at?"

    return ClassificationResult(
        category=category,
        label=CATEGORY_LABELS[category],
        rationale=str(data.get("rationale") or "").strip() or "No rationale returned.",
        defining_source_id=source_id,
        defining_source_name=chunk["act_name"] if chunk else None,
        clarifying_question=str(clarifying) if clarifying else None,
    )
