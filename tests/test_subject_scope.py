#!/usr/bin/env python3
"""Answers must be about the subject the user raised, not the loudest regime.

TEST_RESULTS.md tests 6 and 7. Both classified correctly and then answered the
wrong question:

    "I've made a neem-based face cream for external use only."
      -> cosmetic, and then three steps of Section 3(p) patent law. The user
         said nothing about patents. Step 1 even contradicted the `cosmetic`
         badge printed above it.

    "I'm launching a turmeric-based health drink as a food supplement."
      -> ayurveda_aahar, and then a headline about turmeric not being patentable.

The cause was NOT generation. It was `expand_query`, which turned a neutral
product description into three patent queries:

    "patentability of neem based formulations under traditional knowledge"
    "patent eligibility of cosmetic preparations derived from medicinal plants"

Retrieval then correctly returned patent law, and generation correctly answered
about patents. Every stage downstream was faithful to a question the user never
asked. Patent vocabulary is the densest in this corpus, so it wins any ambiguous
rewrite unless the prompt says otherwise.

The positive controls are the point of this suite. A question that IS about
patenting must still expand toward patentability - the flagship benchmark
depends on exactly that - and a naming question must still reach trade mark law.
A fix that merely suppressed patent vocabulary everywhere would break the demo.

Run (needs a working generation model configured):
    .venv\\Scripts\\python.exe tests\\test_subject_scope.py [trials]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.generation import answer_question, clear_cache  # noqa: E402

TRIALS = int(sys.argv[1]) if len(sys.argv) > 1 else 2

# Wording that only appears when the answer has gone to patent law.
PATENT_MARKERS = ("3(p)", "3(d)", "3(e)", "patentab", "not an invention",
                  "patent office", "traditional knowledge digital library")

# (label, question, expected category, must the answer be patent-framed?,
#  a word the on-regime answer should contain)
CASES = [
    ("T7 cosmetic", "I've made a neem-based face cream for external use only.",
     "cosmetic", False, "cosmetic"),
    ("T6 aahar", "I'm launching a turmeric-based health drink as a food supplement, "
     "not a medicine.", "ayurveda_aahar", False, "food"),
    # POSITIVE CONTROLS - these must stay patent-framed / on their own regime.
    ("flagship", "Can a classical churna from a First Schedule text be patented?",
     "classical_generic", True, "patent"),
    ("naming", "Can I trademark the name of my Ayurvedic product?",
     None, False, "trade mark"),
]

results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append(("PASS" if ok else "FAIL", name, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{'  - ' + detail if detail else ''}")


print("=" * 74)
print(" SUBJECT SCOPE - answer the question that was asked")
print("=" * 74)
print(f" {TRIALS} trials per case\n")

for label, question, expect_cat, expect_patent, on_regime_word in CASES:
    cats, patent_framed, on_regime = [], 0, 0
    for _ in range(TRIALS):
        clear_cache()
        answer = answer_question(question, top_k=12)
        cats.append(answer.classification.category.value if answer.classification else None)
        steps = {s.step: s for s in answer.steps}
        surface = ((answer.headline or "") + " " +
                   (steps[2].content if 2 in steps else "")).lower()
        acts = " ".join(c.act_name for c in answer.citations).lower()
        patent_framed += any(m in surface for m in PATENT_MARKERS)
        on_regime += (on_regime_word in surface or on_regime_word in acts)

    if expect_cat:
        record(f"{label}: classified {expect_cat} every trial",
               all(c == expect_cat for c in cats), f"{cats}")
    if expect_patent:
        record(f"{label}: stays patent-framed (positive control)",
               patent_framed == TRIALS, f"{patent_framed}/{TRIALS}")
    else:
        record(f"{label}: headline and legal position are NOT patent-framed",
               patent_framed == 0, f"patent-framed in {patent_framed}/{TRIALS}")
    record(f"{label}: answers on its own regime ({on_regime_word!r})",
           on_regime == TRIALS, f"{on_regime}/{TRIALS}")

print("\n" + "=" * 74)
failed = [r for r in results if r[0] == "FAIL"]
print(f" {len(results) - len(failed)}/{len(results)} checks passed")
if failed:
    print("\n FAILURES:")
    for _, name, detail in failed:
        print(f"   - {name}: {detail}")
print("=" * 74 + "\n")
sys.exit(1 if failed else 0)
