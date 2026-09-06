#!/usr/bin/env python3
"""The official benchmark, run cold several times, scored on what must not vary.

TEST_RESULTS.md test 21: two cold runs of the flagship gave different action
routes from the same retrieved chunk - one named TKDL as the defensive route,
the other said "the evidence does not provide a protection route" - even though
DOC020_chunk_116, cited in both, contains the sentence about the Examiner
consulting TKDL. For the single question the demo turns on, that is the
difference between the answer that wins the room and one that shrugs.

Two prompt changes address it, both in generation.ANSWER_PROMPT:

  * Step 3 must re-read the evidence for a named register, registry, database,
    authority or defensive mechanism BEFORE writing that no route exists. "No
    route" was being used to restate step 2's prohibition.
  * The relevance-ordering rule from CLAUDE.md 6f was restored. It had been
    lost in a later rewrite, and its absence showed: the decisive Section 3(p)
    chunk was cited in only 3 of 5 cold runs before it went back in, 5 of 6
    after.

The third check here is the one that matters most and was never asserted
anywhere: **a provision named in prose must appear in a chunk cited on that
step.** validate_ids() proves a citation id is real and was retrieved; nothing
proved that "under Section 3(p)" was backed by a chunk that actually contains
Section 3(p). Retrieval puts that chunk at rank 1-4 most runs but was measured
once at rank 23, outside top_k - and on such a run the model can still write
"Section 3(p)" while citing the Drugs and Cosmetics Rules, which do not contain
it. That is the "no fabricated authority" line in CLAUDE.md 1.2.

Run (needs a working generation model configured):
    .venv\\Scripts\\python.exe tests\\test_flagship.py [trials]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.corpus_index import get_chunk  # noqa: E402
from app.generation import answer_question, clear_cache  # noqa: E402

FLAGSHIP = "Can a classical churna from a First Schedule text be patented?"
TRIALS = int(sys.argv[1]) if len(sys.argv) > 1 else 5

TKDL_TERMS = ("tkdl", "traditional knowledge digital library")

# "Section 3(p)", "Rule 122-E", "section 11(2)(a)". Captures the number itself so
# it can be looked for in the cited chunk's own text.
_PROVISION = re.compile(
    r"\b(?:section|sections|rule|rules|regulation|regulations)\s+"
    r"(\d+[A-Za-z]*(?:\s*[-‐-―]\s*[A-Za-z0-9]+)?(?:\s*\([^)]{1,8}\))*)",
    re.IGNORECASE,
)

results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append(("PASS" if ok else "FAIL", name, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{'  - ' + detail if detail else ''}")


def normalise(token: str) -> str:
    """'122 - E' and '122-E' are the same provision; so are case variants."""
    return re.sub(r"[\s‐-―-]", "", token).lower()


def unsupported_provisions(step, citations_by_id) -> list[str]:
    """Provisions named in this step's prose that no chunk it cites contains."""
    cited_text = " ".join(
        (get_chunk(cid) or {}).get("chunk_text", "") for cid in step.citation_ids
    )
    haystack = normalise(cited_text)
    missing = []
    for match in _PROVISION.finditer(step.content or ""):
        token = match.group(1)
        if normalise(token) not in haystack:
            missing.append(match.group(0))
    return missing


print("=" * 74)
print(f" FLAGSHIP - {TRIALS} cold runs of the official benchmark")
print("=" * 74)
print(f" Q: {FLAGSHIP}\n")

tkdl_hits = 0
classical_hits = 0
provision_problems: list[str] = []
answered = 0

for trial in range(1, TRIALS + 1):
    clear_cache()  # every trial is a real generation, never a cache replay
    answer = answer_question(FLAGSHIP, top_k=12)
    steps = {s.step: s for s in answer.steps}
    citations_by_id = {c.chunk_id: c for c in answer.citations}

    answered += not answer.abstained
    classical_hits += bool(
        answer.classification and answer.classification.category.value == "classical_generic"
    )
    step3 = steps.get(3)
    route = (step3.content if step3 else "").lower()
    tkdl_hits += any(term in route for term in TKDL_TERMS)

    for number, step in sorted(steps.items()):
        for bad in unsupported_provisions(step, citations_by_id):
            provision_problems.append(f"trial {trial} step {number}: {bad!r} not in cited chunks")

    print(f"  trial {trial}: cat="
          f"{answer.classification.category.value if answer.classification else None} "
          f"conf={answer.confidence.value if answer.confidence else None} "
          f"cites={len(answer.citations)} "
          f"TKDL_in_route={any(t in route for t in TKDL_TERMS)}")

print()
record("answered every cold run", answered == TRIALS, f"{answered}/{TRIALS}")
record("classified classical_generic every run", classical_hits == TRIALS,
       f"{classical_hits}/{TRIALS}")
record("named TKDL as the action route every run", tkdl_hits == TRIALS,
       f"{tkdl_hits}/{TRIALS}")
record("every provision named in prose appears in a chunk cited on that step",
       not provision_problems, "; ".join(provision_problems[:4]))

print("\n" + "=" * 74)
failed = [r for r in results if r[0] == "FAIL"]
print(f" {len(results) - len(failed)}/{len(results)} checks passed")
if failed:
    print("\n FAILURES:")
    for _, name, detail in failed:
        print(f"   - {name}: {detail}")
print("=" * 74 + "\n")
sys.exit(1 if failed else 0)
