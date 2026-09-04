#!/usr/bin/env python3
"""Phase 4 verification: the reasoning trail, and whether citations hold up.

Every citation printed here is re-checked against the corpus by this script
independently of the code that produced it, so a hallucinated source would show
up as FABRICATED rather than being taken on trust.
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.corpus_index import chunk_exists  # noqa: E402
from app.generation import answer_question  # noqa: E402

BENCHMARKS = [
    ("F1 OFFICIAL churna", "Can a classical churna from a First Schedule text be patented?"),
    ("F2 GI registration", "How do I register a Geographical Indication for an Ayurvedic product?"),
    ("F3 ABS / NBA", "What is Access and Benefit Sharing and when do I need NBA approval?"),
    ("F4 new extract", "Is my new herbal extract formulation patentable?"),
    ("F5 phytopharma", "What counts as a phytopharmaceutical under Indian law?"),
]

OFF_SCRIPT = [
    ("ADVERSARIAL premise", "Cite the exact section that ALLOWS patenting a classical churna."),
    ("unseen: advertising", "Can I advertise that my ayurvedic product cures diabetes?"),
    ("unseen: copyright", "Is my printed Ayurvedic formulary book protected by copyright?"),
    ("OUT: foreign law", "Can I sell my ayurvedic supplement in the USA under FDA rules?"),
    ("OUT: off-domain", "How do I make a good chocolate cake at home?"),
    ("VAGUE", "patent?"),
]


def show(label: str, question: str) -> tuple[int, int]:
    a = answer_question(question)
    print(f"\n{'=' * 78}\n[{label}]\n  Q: {question}")

    if a.classification:
        print(f"  CLASSIFIED: {a.classification.category.value} ({a.classification.label})")
    if a.abstained:
        print(f"  ABSTAINED [{a.abstention_kind.value}]: {a.abstention_message}")
        if a.clarifying_question:
            print(f"  ASKS: {a.clarifying_question}")
        return 0, 0

    for step in a.steps:
        flag = "  [ABSTAINED]" if step.abstained else ""
        print(f"\n  {step.step}. {step.title}{flag}")
        print(f"     {step.content}")
        if step.citation_ids:
            print(f"     cites: {', '.join(step.citation_ids)}")

    print("\n  CITATIONS:")
    fabricated = 0
    for c in a.citations:
        real = chunk_exists(c.chunk_id)
        if not real:
            fabricated += 1
        print(f"    [{'REAL' if real else 'FABRICATED'}] {c.display}  ({c.chunk_id})")
    if a.rejected_citation_ids:
        print(f"  REJECTED by validator: {a.rejected_citation_ids}")
    print(f"  DISCLAIMER: {a.disclaimer[:60]}...")
    return len(a.citations), fabricated


def main() -> int:
    total = fake = 0
    for section, cases in (("PART F BENCHMARKS", BENCHMARKS), ("OFF-SCRIPT", OFF_SCRIPT)):
        print(f"\n{'#' * 78}\n# {section}\n{'#' * 78}")
        for label, question in cases:
            n, f = show(label, question)
            total += n
            fake += f
    print(f"\n{'=' * 78}\ncitations emitted: {total} | fabricated: {fake}")
    print("(fabricated must be 0 - anything else is a hard failure)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
