#!/usr/bin/env python3
"""Regression suite for the relevance gate's scope judgement.

TEST_RESULTS.md recorded the worst behaviour found in the evaluation: mid-way
through a session the assistant refused

    "Can I trademark the name of my Ayurvedic product?"
        -> "trademark law ... is not covered by the provided corpus"
    "Can I copyright the text of my Ayurvedic formulation booklet?"
        -> "the provided corpus contains no provisions regarding copyright law"

Both statements are false: the corpus holds 118 Trade Marks Act 1999 chunks and
102 Copyright Act 1957 chunks, and the same questions answered correctly when
asked on their own.

The report attributed this to conversation history steering the gate. **That was
wrong, and this suite exists partly to keep it from being believed again.**
History reaches only contextualise(); the gate never sees it. Measured over four
trials per arm, history made no difference at all:

    trademark, standalone      3 refused / 1 answered
    trademark, 6-turn history  2 refused / 2 answered
    copyright, standalone      1 refused / 3 answered
    copyright, 6-turn history  0 refused / 4 answered

The real causes were three, all in what the gate could see:

  1. The distance outer bound was computed on the user's raw wording rather than
     on the formulations that actually retrieved the evidence. "What is ABS?"
     scored 0.454 against MAX_DENSE_DISTANCE = 0.45 and was refused before the
     gate ran, while all twelve retrieved chunks were the Biological Diversity
     Act and the ABS Guidelines.
  2. The gate read only the first six passages. The Trade Marks Act chunks rank
     6th and 8th for the trademark question - "Ayurvedic product" pulls the
     949-chunk Drugs and Cosmetics Rules above them - so the gate was shown five
     drug-regulation passages and asked whether trade marks were in scope.
  3. The gate never saw the query expansions, so it judged wording that had
     retrieved nothing: "What is ABS?" against passages that only ever say
     "Access and Benefit Sharing".

Because the underlying behaviour is a model judgement, each case runs several
times and is scored on the whole set - a suite that passes on one lucky sample
is what let this ship in the first place.

Run (needs a working generation model configured):
    .venv\\Scripts\\python.exe tests\\test_gate_scope.py
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.corpus_index import get_chunk  # noqa: E402
from app.generation import contextualise  # noqa: E402
from app.retrieval import (  # noqa: E402
    _scope_message,
    expand_query,
    retrieve,
)

TRIALS = 3

# A long, topic-hopping session, like the 12-question run in TEST_RESULTS.md.
# The trademark and copyright questions are asked from INSIDE it.
SESSION = [
    "What is the Traditional Knowledge Digital Library?",
    "How does the Patents Act treat traditional knowledge?",
    "What is a Geographical Indication?",
    "Do I need NBA approval to file a patent using Indian biodiversity?",
    "What is a classical Ayurvedic formulation under the Drugs and Cosmetics Act?",
    "What licence do I need to manufacture an Ayurvedic medicine?",
    "What labelling rules apply to Ayurvedic medicines?",
    "What are the data requirements for a phytopharmaceutical drug?",
    "Is a plant variety protectable in India?",
    "What does the Drugs and Magic Remedies Act prohibit?",
]

# question -> the act_subtypes that genuinely govern it, any one of which counts
# as the governing law having been retrieved.
#
# The trademark question accepts GI Act chunks as well as Trade Marks Act ones,
# and that is not a loosened bar: GI Act ss.25-26 are *about* trade marks -
# prohibiting registration of a geographical indication as one, and protecting
# prior good-faith marks that contain one. For "can I trademark the name of my
# Ayurvedic product", where the name is very often a place, they are as
# on-point as s.9. Scoring only act_subtype == "trademark" marked a correct,
# well-grounded answer as a miss.
IN_SCOPE = [
    ("Can I trademark the name of my Ayurvedic product?",
     {"trademark", "geographical_indication"}),
    ("Can I copyright the text of my Ayurvedic formulation booklet?", {"copyright"}),
    ("What is ABS?", {"biodiversity_abs"}),
    ("What is a Geographical Indication?", {"geographical_indication"}),
]

# Must STILL be refused: the fix must not turn the gate into a rubber stamp.
OUT_OF_SCOPE = [
    ("How do I bake a good chocolate cake?", "off-topic"),
    ("Can I sell my Ayurvedic product in the United States? What does the FDA require?",
     "foreign jurisdiction"),
]

results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append(("PASS" if ok else "FAIL", name, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{'  - ' + detail if detail else ''}")


def gate(question: str, history: list[str]):
    """One full pass of the path under test, cache-free."""
    resolved = contextualise(question, history)
    expansion = expand_query(resolved)
    return resolved, retrieve(resolved, top_k=12, use_llm_gate=True, expansion=expansion)


print("=" * 74)
print(" GATE SCOPE - in-scope law must never be declared missing")
print("=" * 74)
print(f" session length: {len(SESSION)} prior turns, {TRIALS} trials per case\n")

for question, subtypes in IN_SCOPE:
    verdicts = collections.Counter()
    false_claims: list[str] = []
    saw_governing = 0
    for _ in range(TRIALS):
        _resolved, result = gate(question, SESSION)
        verdicts["answered" if result.sufficient else result.abstention.value] += 1
        if any((get_chunk(e.chunk_id) or {}).get("act_subtype") in subtypes
               for e in result.evidence):
            saw_governing += 1
        if not result.sufficient and _scope_message(result.reason) != result.reason:
            false_claims.append(result.reason)

    answered = verdicts["answered"]
    record(f"in-session, answered every trial: {question!r}",
           answered == TRIALS, f"{dict(verdicts)}")
    record(f"  governing law ({'/'.join(sorted(subtypes))}) retrieved every trial",
           saw_governing == TRIALS, f"{saw_governing}/{TRIALS}")
    record("  no refusal claimed our holdings lack this law",
           not false_claims, "; ".join(false_claims)[:160])

print()
for question, why in OUT_OF_SCOPE:
    verdicts = collections.Counter()
    for _ in range(TRIALS):
        _resolved, result = gate(question, SESSION)
        verdicts["answered" if result.sufficient else result.abstention.value] += 1
    record(f"still refused ({why}): {question[:52]!r}",
           verdicts["answered"] == 0, f"{dict(verdicts)}")

print()
# History must not change the scope verdict. This is the claim the report got
# wrong; assert it rather than leaving it to memory.
for question, _subtype in IN_SCOPE[:2]:
    with_history = sum(gate(question, SESSION)[1].sufficient for _ in range(TRIALS))
    standalone = sum(gate(question, [])[1].sufficient for _ in range(TRIALS))
    record(f"history does not change the verdict: {question[:44]!r}",
           with_history == standalone == TRIALS,
           f"with history {with_history}/{TRIALS}, standalone {standalone}/{TRIALS}")

print("\n" + "=" * 74)
failed = [r for r in results if r[0] == "FAIL"]
print(f" {len(results) - len(failed)}/{len(results)} checks passed")
if failed:
    print("\n FAILURES:")
    for _, name, detail in failed:
        print(f"   - {name}: {detail}")
print("=" * 74 + "\n")
sys.exit(1 if failed else 0)
