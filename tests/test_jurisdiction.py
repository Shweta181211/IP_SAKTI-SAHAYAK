#!/usr/bin/env python3
"""Category 7: the two corpora must be visibly separate and never conflated.

The problem statement requires national and international answer-sets to be
"visibly separate" and "never conflated". Until `03_international/` was ingested
that was trivially true - there was only one corpus, and the International
toggle returned a fixed abstention. With 825 treaty chunks live it becomes a
property that has to be enforced and tested.

The enforcement point is the EVIDENCE SET, not the wording. Once a chunk from
the wrong legal system is in the prompt, no amount of careful phrasing
downstream keeps it out of the answer - so these tests assert on citations,
which are the thing a judge can check, rather than on prose.

Two bugs this suite exists to catch, both found while wiring the toggle:

  * `_lexical_candidates` had NO jurisdiction filter. The dense half of the
    hybrid filtered and the lexical half did not, so an international question
    would have had Indian statutes fused straight into its evidence. Invisible
    while the international corpus was empty; a citation-integrity failure the
    moment it was not.
  * The classifier's `defining_source_id` is a chunk of the Indian Drugs and
    Cosmetics Act, and it is appended to the allowed-citation set. Correct for a
    national answer; conflation in an international one.

Run (needs a working generation model and a rebuilt index):
    .venv\\Scripts\\python.exe tests\\test_jurisdiction.py [trials]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.corpus_index import all_chunks, get_chunk  # noqa: E402
from app.generation import answer_question, clear_cache  # noqa: E402
from app.retrieval import Expansion, retrieve  # noqa: E402

TRIALS = int(sys.argv[1]) if len(sys.argv) > 1 else 1

FLAGSHIP = "Can a classical churna from a First Schedule text be patented?"

results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append(("PASS" if ok else "FAIL", name, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{'  - ' + detail if detail else ''}")


def jurisdictions_of(chunk_ids) -> set[str]:
    return {
        str((get_chunk(cid) or {}).get("jurisdiction", "?")) for cid in chunk_ids
    }


print("=" * 74)
print(" JURISDICTION SEPARATION - Category 7")
print("=" * 74)

# ---------------------------------------------------------------- corpus
counts: dict[str, int] = {}
for chunk in all_chunks():
    key = str(chunk.get("jurisdiction"))
    counts[key] = counts.get(key, 0) + 1
print(f" corpus: {counts}\n")

record("international corpus is populated", counts.get("international", 0) > 0,
       f"{counts.get('international', 0)} chunks")
record("national corpus is intact", counts.get("national", 0) == 2457,
       f"{counts.get('national', 0)} chunks")

# ---------------------------------------------------- retrieval separation
# The cheap, deterministic half: no model involved, so a failure here is a code
# bug rather than model variance.
for jurisdiction in ("national", "international"):
    # A fixed expansion keeps this half deterministic: the question is
    # searched verbatim, so a failure is a filtering bug and not the model
    # having rephrased the query differently on this run.
    result = retrieve(FLAGSHIP, top_k=12, use_llm_gate=False,
                      jurisdiction=jurisdiction, expansion=Expansion([FLAGSHIP]))
    got = jurisdictions_of(e.chunk_id for e in result.evidence)
    record(f"retrieval in {jurisdiction} mode returns ONLY {jurisdiction} chunks",
           got == {jurisdiction}, f"saw {got or 'nothing'}")
    record(f"  {jurisdiction} retrieval is non-empty", bool(result.evidence),
           f"{len(result.evidence)} chunks")

# --------------------------------------------------------- answer separation
for jurisdiction in ("national", "international"):
    for _ in range(TRIALS):
        label = f"{jurisdiction} answer"
        # `gate_unavailable` is not a verdict about behaviour - it means no
        # provider could be reached. Every free tier here is rate-limited, and
        # this suite spends eight model calls, so hitting it says nothing about
        # jurisdiction separation. Retry it; report it as SKIPPED rather than
        # FAILED if capacity never comes back, so a real conflation bug is never
        # hidden behind an infrastructure failure and vice versa.
        for attempt in range(4):
            clear_cache()
            answer = answer_question(FLAGSHIP, top_k=12, jurisdiction=jurisdiction)
            if answer.abstention_kind.value != "gate_unavailable":
                break
            if attempt < 3:
                print(f"        (provider unavailable, retrying in 20s"
                      f" - attempt {attempt + 2}/4)")
                time.sleep(20)
        cited = [c.chunk_id for c in answer.citations]
        got = jurisdictions_of(cited)
        if answer.abstention_kind.value == "gate_unavailable":
            print(f"  [SKIP] {label}: no provider reachable after 4 attempts "
                  "- capacity, not behaviour")
            continue
        if answer.abstained:
            record(f"{label}: answered rather than abstaining", False,
                   f"{answer.abstention_kind.value}: {(answer.abstention_message or '')[:70]}")
            continue
        record(f"{label}: every citation is {jurisdiction}",
               got == {jurisdiction}, f"saw {got}")
        record(f"{label}: declares its own jurisdiction",
               answer.jurisdiction == jurisdiction, answer.jurisdiction)
        acts = sorted({c.act_name for c in answer.citations})
        print(f"        sources: {acts}")
        print(f"        headline: {(answer.headline or '')[:100]}")

print("\n" + "=" * 74)
failed = [r for r in results if r[0] == "FAIL"]
print(f" {len(results) - len(failed)}/{len(results)} checks passed")
if failed:
    print("\n FAILURES:")
    for _, name, detail in failed:
        print(f"   - {name}: {detail}")
print("=" * 74 + "\n")
sys.exit(1 if failed else 0)
