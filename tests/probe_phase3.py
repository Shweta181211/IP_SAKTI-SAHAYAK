#!/usr/bin/env python3
"""Phase 3 verification: hybrid retrieval, citations, and the abstention gate.

Prints measured signals rather than assertions, so the thresholds in
retrieval.py can be justified from data instead of taste.
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.retrieval import retrieve  # noqa: E402
from app.schemas import Category  # noqa: E402

IN_CORPUS = [
    ("F1 official churna", "Can a classical churna from a First Schedule text be patented?", Category.CLASSICAL_GENERIC),
    ("F2 GI registration", "How do I register a Geographical Indication for an Ayurvedic product?", None),
    ("F3 ABS / NBA", "What is Access and Benefit Sharing and when do I need NBA approval?", None),
    ("F4 new extract", "Is my new herbal extract formulation patentable?", None),
    ("F5 phytopharma", "What counts as a phytopharmaceutical under Indian law?", None),
    ("unseen: trademark", "Can I trademark the name Chyawanprash?", None),
    ("unseen: licence", "Do I need a licence to manufacture an ayurvedic syrup for sale?", None),
    ("unseen: TK theft", "my grandmother's herbal oil recipe - can a company steal it and patent it?", None),
]

OUT_OF_CORPUS = [
    ("OUT: marketing", "What is the best marketing strategy for my ayurvedic startup?"),
    ("OUT: nonsense", "purple bicycle quarterly tax rebate"),
    ("OUT: cooking", "How do I make a good chocolate cake at home?"),
    ("OUT: unrelated law", "What is the penalty for speeding on a national highway?"),
]


def show(label: str, question: str, category=None) -> tuple[float, float, bool]:
    r = retrieve(question, category=category, top_k=5)
    print(f"\n{'=' * 76}\n{label}\n  Q: {question}")
    print(f"  dense_best_distance={r.dense_best_distance:.4f}  "
          f"lexical_best={r.lexical_best_score:.2f}  sufficient={r.sufficient}")
    if not r.sufficient:
        print(f"  ABSTAIN: {r.reason}")
    for i, e in enumerate(r.evidence[:4], 1):
        c = e.citation
        print(f"   {i}. rrf={e.score:.4f} dense#{e.dense_rank} lex#{e.lexical_rank}")
        print(f"      CITE: {c.display if c else '(unresolvable)'}")
        print(f"      {e.text[:110]}...")
    return r.dense_best_distance, r.lexical_best_score, r.sufficient


def main() -> int:
    print("#" * 76 + "\n# IN-CORPUS\n" + "#" * 76)
    in_stats = [show(l, q, c) for l, q, c in IN_CORPUS]

    print("\n" + "#" * 76 + "\n# OUT-OF-CORPUS (must abstain)\n" + "#" * 76)
    out_stats = [show(l, q) for l, q in OUT_OF_CORPUS]

    print("\n" + "#" * 76 + "\n# THRESHOLD CALIBRATION\n" + "#" * 76)
    for name, stats in (("in-corpus", in_stats), ("out-of-corpus", out_stats)):
        lex = [s[1] for s in stats]
        den = [s[0] for s in stats]
        print(f"  {name:14s} lexical: min={min(lex):6.2f} max={max(lex):6.2f} | "
              f"distance: min={min(den):.4f} max={max(den):.4f}")
    lex_gap = min(s[1] for s in in_stats) - max(s[1] for s in out_stats)
    print(f"  lexical separation (worst in-corpus - best out-of-corpus): {lex_gap:+.2f}")

    correct = sum(1 for s in in_stats if s[2]) + sum(1 for s in out_stats if not s[2])
    print(f"\n  abstention decisions correct: {correct}/{len(in_stats) + len(out_stats)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
