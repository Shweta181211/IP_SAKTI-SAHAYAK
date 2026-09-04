"""Side-by-side category comparison.

The problem statement's central insight is that the same product has *opposite*
IP postures depending on which regulatory category it falls into: a classical
formulation faces the Section 3(p) bar and is defended through TKDL, while a new
drug has genuine patent potential but must generate clinical evidence.

Answering one category at a time makes that point slowly. Showing the contrast
in one view makes it obvious.

Cost note: the naive implementation runs the whole pipeline once per category -
roughly nine model calls. This instead retrieves ONCE against the product
description and asks for the contrast in a single generation call, so a
comparison costs about the same as an ordinary question. That matters on a
free-tier endpoint.

Citations are validated exactly as they are for a normal answer: an id that was
not in the retrieved evidence is rejected, not shown.
"""

from __future__ import annotations

import logging
import re

from .citations import citations_for, validate_ids
from .config import settings
from .llm import LLMUnavailable, complete_json
from .retrieval import expand_query, is_too_vague, retrieve
from .schemas import (
    CATEGORY_LABELS,
    CategoryContrast,
    Category,
    ComparisonResult,
)

logger = logging.getLogger(__name__)

_CHUNK_ID = re.compile(r"DOC\d{3}_chunk_\d{3}")

# The four categories whose IP posture genuinely differs. Cosmetic and
# Ayurveda-Aahar are excluded: they are not drugs, so a patentability contrast
# between them is not the interesting comparison and would pad the view.
COMPARED = (
    Category.CLASSICAL_GENERIC,
    Category.PATENT_PROPRIETARY,
    Category.NEW_DRUG,
    Category.PHYTOPHARMACEUTICAL,
)

COMPARE_PROMPT = """A user described a product. Show how its legal position CHANGES depending \
on which Indian regulatory category it falls into.

This is the heart of the matter: the same preparation faces completely different intellectual \
property rules depending on how it is classified.

Answer STRICTLY from the numbered evidence below. You have no other knowledge of the law. \
Where the evidence does not cover a category, say so plainly in that category's entry rather \
than filling the gap from memory.

## Evidence

{evidence}

## The product

{product}

## Categories to compare

{categories}

## Rules

- `citation_ids` may contain ONLY ids from the evidence above, exactly as written. Never \
invent one.
- `patentable` is a SHORT verdict, at most 12 words - e.g. "No - barred as traditional \
knowledge", "Possible, with inventive step".
- `posture` is 2-3 sentences: what this category means for protecting and commercialising \
the product, and what it requires.
- Name provision numbers inline where the evidence gives them ("under Section 3(a)...").
- **Never write a chunk id such as DOC003_chunk_234 in the prose.** Ids belong only in `citation_ids`; the interface renders them as source cards. Refer to sources by their act and section instead.
- Be concrete about the DIFFERENCE. The value here is the contrast, not four \
interchangeable paragraphs.

## Output

Return ONLY a JSON object, no markdown fence and no commentary:
{{"contrasts": [
  {{"category": "<category id>", "patentable": "<short verdict>",
    "posture": "<2-3 sentences>", "citation_ids": ["..."]}}
]}}"""


def compare_categories(product: str, top_k: int | None = None) -> ComparisonResult:
    """Retrieve once, then contrast the regulatory categories in one call."""
    top_k = top_k or settings.top_k

    if is_too_vague(product):
        return ComparisonResult(
            product=product,
            abstained=True,
            abstention_message=(
                "Describe the product in a little more detail - what it is, and how its "
                "formula was arrived at - and I can show how the categories differ for it."
            ),
            disclaimer=settings.disclaimer,
        )

    # A comparison is inherently about patentability and regulatory pathway, so
    # bias the search toward the provisions that decide those, using the product
    # description the user actually gave.
    queries = expand_query(product)
    result = retrieve(product, top_k=top_k, queries=queries)

    if not result.sufficient:
        return ComparisonResult(
            product=product,
            abstained=True,
            abstention_message=result.reason,
            disclaimer=settings.disclaimer,
        )

    evidence = "\n\n".join(
        f"[{item.chunk_id}] {(item.citation.display if item.citation else '')}\n{item.text[:1000]}"
        for item in result.evidence
    )
    categories = "\n".join(
        f"- `{c.value}` - {CATEGORY_LABELS[c]}" for c in COMPARED
    )

    try:
        data = complete_json(
            COMPARE_PROMPT.format(evidence=evidence, product=product, categories=categories),
            max_tokens=1800,
        )
    except LLMUnavailable as exc:
        logger.error("Comparison generation failed: %s", exc)
        return ComparisonResult(
            product=product,
            abstained=True,
            abstention_message="The comparison service is temporarily unavailable. Please try again.",
            disclaimer=settings.disclaimer,
        )

    by_category = {}
    for raw in data.get("contrasts") or []:
        try:
            category = Category(str(raw.get("category", "")).strip())
        except ValueError:
            continue
        if category in COMPARED:
            by_category[category] = raw

    contrasts: list[CategoryContrast] = []
    all_cited: list[str] = []
    for category in COMPARED:
        raw = by_category.get(category, {})
        kept, rejected = validate_ids(raw.get("citation_ids") or [], result.allowed_ids)
        if rejected:
            logger.warning("Comparison rejected unverifiable ids: %s", rejected)
        # Models mention ids in prose despite being told not to; the citation
        # cards already carry them, and "DOC003_chunk_234 shows..." is noise.
        posture = _CHUNK_ID.sub("the cited source", str(raw.get("posture") or "")).strip()
        posture = re.sub(r"\s{2,}", " ", posture)
        if not posture:
            posture = "The retrieved sources do not say enough about this category to compare it."
            kept = []
        contrasts.append(
            CategoryContrast(
                category=category,
                label=CATEGORY_LABELS[category],
                posture=posture,
                patentable=str(raw.get("patentable") or "Not stated in the evidence").strip(),
                citation_ids=kept,
            )
        )
        all_cited.extend(c for c in kept if c not in all_cited)

    return ComparisonResult(
        product=product,
        contrasts=contrasts,
        citations=citations_for(all_cited),
        disclaimer=settings.disclaimer,
    )
