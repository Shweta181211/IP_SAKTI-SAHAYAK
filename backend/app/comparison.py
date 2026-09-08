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

from .citations import (
    citations_for,
    normalise_institutions,
    strip_chunk_ids,
    validate_ids,
)
from .config import settings
from .llm import LLMUnavailable, complete_json
from .retrieval import Expansion, expand_query, is_too_vague, retrieve
from .schemas import (
    CATEGORY_LABELS,
    CategoryContrast,
    Category,
    ComparisonResult,
)

logger = logging.getLogger(__name__)

# NOTE: the pattern below uses regex word boundaries. They were committed as literal 0x08
# BACKSPACE bytes, which look identical in every rendering of this file and
# made the pattern unmatchable - so this stripper silently did nothing and
# raw chunk ids could reach the comparison cards. tests/test_units.py now
# sweeps every backend module for control characters so it cannot recur.
# NOTE: those are \b word boundaries. They were committed as literal 0x08
# BACKSPACE bytes, which render identically in every editor and made the
# pattern unmatchable - so this stripper silently did nothing and raw chunk
# ids could reach the comparison cards. test_units.py now sweeps every
# backend module for control characters so it cannot recur.
_CHUNK_ID = re.compile(r"\bDOC\d{3}_chunk_\d{3}\b")

# The four categories whose IP posture genuinely differs. Cosmetic and
# Ayurveda-Aahar are excluded: they are not drugs, so a patentability contrast
# between them is not the interesting comparison and would pad the view.
COMPARED = (
    Category.CLASSICAL_GENERIC,
    Category.PATENT_PROPRIETARY,
    Category.NEW_DRUG,
    Category.PHYTOPHARMACEUTICAL,
)

# One statutory probe per category being compared.
#
# Anchored to the fixed COMPARED set above - a structural property of this
# feature, which always contrasts the same four regimes - and NOT to anything
# scanned out of the user's wording, so this does not reintroduce the keyword
# special-casing 5 rules out.
#
# Why they are needed. `expand_query` restates the PRODUCT, and a product
# description expands into product vocabulary. Measured on "ashwagandha root
# extract capsule standardised to 5% withanolides": all twelve retrieved chunks
# came from the Drugs and Cosmetics Rules 1945, `patentable` read "Not covered
# in evidence" for all four categories, and new_drug and phytopharmaceutical
# retrieved nothing at all. The one contrast this module exists to draw - a
# classical formulation barred by 3(p) against a new drug with a real pathway -
# was the single thing it could not show. The module docstring and the comment
# at the retrieval call both claimed this bias already existed. Neither did.
CATEGORY_PROBES: dict[Category, str] = {
    Category.CLASSICAL_GENERIC: (
        "invention which in effect is traditional knowledge or an aggregation or "
        "duplication of known properties of traditionally known components is not "
        "an invention"
    ),
    Category.PATENT_PROPRIETARY: (
        "patent or proprietary medicine under section 3(h) formulated with "
        "ingredients of the authoritative books, conditions of manufacturing licence"
    ),
    Category.NEW_DRUG: (
        "new drug permission under rule 122-E and the clinical data required "
        "before it may be manufactured or marketed"
    ),
    Category.PHYTOPHARMACEUTICAL: (
        "phytopharmaceutical drug as a purified fraction with defined bio-active "
        "markers and the Schedule Y data requirements for it"
    ),
}


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
- **Section 3(p) is not a blanket bar on everything Ayurvedic.** It bars an invention that IS \
traditional knowledge or an aggregation of known properties of traditionally known components. A \
traditional INGREDIENT used in a genuinely new formulation or process is not automatically caught \
by it - that is assessed on novelty and inventive step like any other application. Reserve the 3(p) \
verdict for a formulation actually documented in a classical or authoritative text; this contrast is \
worthless if every category comes back barred because the product is herbal.
- **TKDL confers no rights.** It is a defensive prior-art database that patent examiners search in \
order to REFUSE wrongful applications. Never present it as a protection or registration route a user \
can file with.
- **There is no "International Patent Office".** Name a real body the evidence names, or write \
"patent offices in other countries".
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
    # A wider evidence set than a single question gets, because this one prompt
    # must cover four regimes rather than answer one question.
    top_k = top_k or settings.compare_top_k

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
    expansion = expand_query(product)
    # RRF fuses each formulation's ranked list independently, so a probe that
    # finds nothing relevant costs a rank slot rather than displacing a good hit
    # from the product's own formulations.
    expansion = Expansion(
        queries=[*expansion.queries, *CATEGORY_PROBES.values()],
        ok=expansion.ok,
        reason=expansion.reason,
    )
    result = retrieve(product, top_k=top_k, expansion=expansion)

    if not result.sufficient:
        return ComparisonResult(
            product=product,
            abstained=True,
            abstention_message=result.reason,
            disclaimer=settings.disclaimer,
        )

    # RRF rewards CONSENSUS across formulations, which is the opposite of what
    # a comparison needs. The product's own vocabulary appears in every ranked
    # list and accumulates score, while the provision that governs exactly one
    # category appears in a single list and is out-scored by it. Measured after
    # merely adding the probes to the fused query set: `patentable` filled in
    # for classical_generic and patent_proprietary, but new_drug and
    # phytopharmaceutical still retrieved nothing - Schedule Y's
    # phytopharmaceutical chunks never entered the top 24, despite being the
    # only chunks in the corpus that use the word.
    #
    # So each category also gets a small RESERVED allocation from its own probe.
    # This costs no LLM call: the gate has already run on the product retrieval
    # above and settled scope, and a fixed probe needs no expansion. One gated
    # retrieval and one generation call, as the module docstring promises.
    evidence_items = list(result.evidence)
    seen = {item.chunk_id for item in evidence_items}
    for probe in CATEGORY_PROBES.values():
        probe_result = retrieve(
            probe, top_k=settings.compare_probe_slots,
            use_llm_gate=False, expand=False,
        )
        for item in probe_result.evidence:
            if item.chunk_id not in seen:
                seen.add(item.chunk_id)
                evidence_items.append(item)

    allowed_ids = [item.chunk_id for item in evidence_items]

    evidence = "\n\n".join(
        f"[{item.chunk_id}] {(item.citation.display if item.citation else '')}\n{item.text[:1000]}"
        for item in evidence_items
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
        kept, rejected = validate_ids(raw.get("citation_ids") or [], allowed_ids)
        if rejected:
            logger.warning("Comparison rejected unverifiable ids: %s", rejected)
        # Models mention ids in prose despite being told not to; the citation
        # cards already carry them, and "DOC003_chunk_234 shows..." is noise.
        posture = normalise_institutions(strip_chunk_ids(str(raw.get("posture") or "")))
        if not posture:
            posture = "The retrieved sources do not say enough about this category to compare it."
            kept = []
        contrasts.append(
            CategoryContrast(
                category=category,
                label=CATEGORY_LABELS[category],
                posture=posture,
                patentable=normalise_institutions(
                    str(raw.get("patentable") or "Not stated in the evidence").strip()
                ),
                citation_ids=kept,
            )
        )
        all_cited.extend(c for c in kept if c not in all_cited)

    return ComparisonResult(
        product=product,
        contrasts=contrasts,
        citations=citations_for(all_cited),
        search_degraded=result.degraded,
        degraded_reason=result.degraded_reason,
        disclaimer=settings.disclaimer,
    )
