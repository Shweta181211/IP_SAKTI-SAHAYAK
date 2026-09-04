#!/usr/bin/env python3
"""Phase 2 verification: does classification generalise beyond the benchmarks?

Runs the Part F queries plus unrehearsed edge cases. Prints what the classifier
decided and why, so correctness can be judged by eye rather than asserted.
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.classification import classify, verify_anchors  # noqa: E402

# (label, question, expected_category or None if judgement call)
BENCHMARKS = [
    ("F1 official churna", "Can a classical churna from a First Schedule text be patented?", "classical_generic"),
    ("F2 GI registration", "How do I register a Geographical Indication for an Ayurvedic product?", "not_applicable"),
    ("F3 ABS / NBA", "What is Access and Benefit Sharing and when do I need NBA approval?", "not_applicable"),
    ("F4 new extract", "Is my new herbal extract formulation patentable?", None),
    ("F5 phytopharma", "What counts as a phytopharmaceutical under Indian law?", None),
]

OFF_SCRIPT = [
    ("ambiguous product", "I make a herbal juice. What licence do I need?", None),
    ("oddly phrased", "my grandmother's herbal oil recipe - can a company steal it and patent it?", None),
    ("clearly cosmetic", "We sell a turmeric face cream that only claims to brighten skin tone.", "cosmetic"),
    ("food not medicine", "We make an Ayurvedic herbal tea sold as a wellness beverage, no disease claims.", None),
    ("multi-category", "Our product is a classical chyawanprash but we added a new patented extract.", None),
    ("out of domain", "What is the best marketing strategy for my ayurvedic startup?", "not_applicable"),
    ("nonsense", "purple bicycle quarterly tax rebate", "not_applicable"),
]


def run(section: str, cases: list[tuple[str, str, str | None]]) -> tuple[int, int]:
    print(f"\n{'#' * 78}\n# {section}\n{'#' * 78}")
    hits = checked = 0
    for label, question, expected in cases:
        r = classify(question)
        print(f"\n[{label}]")
        print(f"  Q: {question}")
        print(f"  -> {r.category.value}  ({r.label})")
        print(f"     rationale: {r.rationale}")
        if r.defining_source_id:
            print(f"     defined by: {r.defining_source_name} [{r.defining_source_id}]")
        if r.clarifying_question:
            print(f"     asks: {r.clarifying_question}")
        if expected:
            checked += 1
            ok = r.category.value == expected
            hits += ok
            print(f"     expected {expected}: {'MATCH' if ok else 'MISMATCH <-- REVIEW'}")
    return hits, checked


def main() -> int:
    problems = verify_anchors()
    print("anchor integrity:", "OK" if not problems else problems)
    h1, c1 = run("PART F BENCHMARKS", BENCHMARKS)
    h2, c2 = run("OFF-SCRIPT / EDGE CASES", OFF_SCRIPT)
    print(f"\n{'=' * 78}\nasserted cases matched: {h1 + h2}/{c1 + c2} "
          f"(the rest are judgement calls, printed for review)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
