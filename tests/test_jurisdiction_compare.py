#!/usr/bin/env python3
"""The comparison step must never blend the two jurisdictions.

`compare_jurisdictions` is the highest-risk feature in the product: its whole
purpose is to talk about both legal systems at once, and the natural English
sentence - "the law requires disclosure of source" - is already a conflation,
because it does not say whose law.

Three defences exist (see jurisdiction_compare.py). The first two are structural
and need no test: separate corpora cannot cross-contaminate, and the response
shape has no field for an unattributed claim. This suite tests the third -
validation of what the synthesis actually produced - because that is the one
that has to catch a model behaving badly.

Everything here is deterministic and offline. `_validate_point` takes the two
finished answers and a raw dict, so the guard can be tested with hand-built
adversarial input instead of hoping a live model happens to misbehave during a
run. That matters under free-tier rate limits, where a live test is as likely to
measure capacity as behaviour.

Run:
    .venv\\Scripts\\python.exe tests\\test_jurisdiction_compare.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.citations import build_citation  # noqa: E402
from app.corpus_index import all_chunks  # noqa: E402
from app.jurisdiction_compare import _validate_point  # noqa: E402
from app.schemas import AbstentionKind, Answer  # noqa: E402

results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append(("PASS" if ok else "FAIL", name, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{'  - ' + detail if detail else ''}")


# Real chunk ids, resolved by content rather than hardcoded (CLAUDE.md 6g).
def first_chunk(jurisdiction: str, needle: str = "") -> str:
    for chunk in all_chunks():
        if chunk.get("jurisdiction") == jurisdiction and (
            not needle or needle.lower() in str(chunk.get("act_name", "")).lower()
        ):
            return chunk["chunk_id"]
    raise AssertionError(f"no {jurisdiction} chunk matching {needle!r}")


NAT_ID = first_chunk("national", "patents act")
INT_ID = first_chunk("international", "TRIPS")


def answer(jurisdiction: str, chunk_id: str, abstained: bool = False) -> Answer:
    citation = build_citation(chunk_id)
    return Answer(
        question="Q",
        jurisdiction=jurisdiction,
        citations=[citation] if citation and not abstained else [],
        abstained=abstained,
        abstention_kind=AbstentionKind.NO_EVIDENCE if abstained else AbstentionKind.NONE,
    )


NATIONAL = answer("national", NAT_ID)
INTERNATIONAL = answer("international", INT_ID)

print("=" * 74)
print(" JURISDICTION COMPARISON - the synthesis may not conflate or invent")
print("=" * 74)
print(f" national id {NAT_ID} · international id {INT_ID}\n")

# ---------------------------------------------------------------- happy path
point, rejected = _validate_point(
    {
        "kind": "difference",
        "summary": "How each system treats traditional knowledge in patents",
        "national_claim": "India excludes it from patentability outright.",
        "national_citation_ids": [NAT_ID],
        "international_claim": "TRIPS leaves the exclusion to each member state.",
        "international_citation_ids": [INT_ID],
    },
    NATIONAL, INTERNATIONAL,
)
record("a correctly attributed point survives", point is not None)
record("  it keeps both sides' citations",
       bool(point) and point.national_citation_ids == [NAT_ID]
       and point.international_citation_ids == [INT_ID])
record("  nothing is rejected", not rejected, rejected or "")

# ------------------------------------------------- the conflation this prevents
# The failure mode: a national claim citing an INTERNATIONAL source, which is
# how "India requires X" ends up resting on a treaty.
point, rejected = _validate_point(
    {
        "kind": "difference",
        "summary": "Disclosure of source",
        "national_claim": "India requires disclosure of the source of the resource.",
        "national_citation_ids": [INT_ID],          # <- wrong jurisdiction
        "international_claim": "The treaty requires disclosure.",
        "international_citation_ids": [INT_ID],
    },
    NATIONAL, INTERNATIONAL,
)
record("a national claim citing an INTERNATIONAL source is stripped",
       point is not None and not point.national_citation_ids
       and point.national_claim is None,
       f"national_claim={getattr(point, 'national_claim', None)!r}")
record("  the surviving international side is kept",
       bool(point) and point.international_citation_ids == [INT_ID])
record("  the cross-citation is reported", bool(rejected), (rejected or "")[:70])

# And the mirror image.
point, rejected = _validate_point(
    {
        "kind": "similarity",
        "summary": "Both address genetic resources",
        "national_claim": "India addresses it.",
        "national_citation_ids": [NAT_ID],
        "international_claim": "The treaties address it.",
        "international_citation_ids": [NAT_ID],     # <- wrong jurisdiction
    },
    NATIONAL, INTERNATIONAL,
)
record("an international claim citing a NATIONAL source is stripped",
       point is not None and not point.international_citation_ids
       and point.international_claim is None)

# ------------------------------------------------------- invented citations
point, rejected = _validate_point(
    {
        "kind": "difference",
        "summary": "Something",
        "national_claim": "India says so.",
        "national_citation_ids": ["DOC999_chunk_999"],
        "international_claim": None,
        "international_citation_ids": [],
    },
    NATIONAL, INTERNATIONAL,
)
record("a fabricated chunk id is rejected and takes its claim with it",
       point is None, "point dropped" if point is None else "point survived")

# ------------------------------------------------ unsourced claim, both sides
point, rejected = _validate_point(
    {
        "kind": "similarity",
        "summary": "Both are broadly similar",
        "national_claim": "They are similar.",
        "national_citation_ids": [],
        "international_claim": "Yes, similar.",
        "international_citation_ids": [],
    },
    NATIONAL, INTERNATIONAL,
)
record("a point with no citations on either side is dropped entirely",
       point is None)

# ------------------------------------------- provisions invented in synthesis
# Section 3(p) is Indian. Attributing it to the INTERNATIONAL side, whose cited
# chunk does not contain it, is the fabricated-authority failure applied to this
# step - the same rule the main answer path enforces.
point, rejected = _validate_point(
    {
        "kind": "difference",
        "summary": "Patent exclusions",
        "national_claim": "India excludes traditional knowledge.",
        "national_citation_ids": [NAT_ID],
        "international_claim": "Under Section 3(p) the treaty excludes it too.",
        "international_citation_ids": [INT_ID],
    },
    NATIONAL, INTERNATIONAL,
)
carried = (point.international_claim or "") if point else ""
record("a provision the cited side does not contain is removed",
       "3(p)" not in carried, carried[:70] or "(claim removed)")

# --------------------------------------------------- one side legitimately silent
point, rejected = _validate_point(
    {
        "kind": "difference",
        "summary": "Only India has a licensing pathway here",
        "national_claim": "India provides a licensing route.",
        "national_citation_ids": [NAT_ID],
        "international_claim": None,
        "international_citation_ids": [],
    },
    NATIONAL, INTERNATIONAL,
)
record("a point with only one side is allowed when the other is silent",
       point is not None and point.national_claim is not None
       and point.international_claim is None)

# An abstaining side may be described without citations - that IS the finding.
ABSTAINED = answer("international", INT_ID, abstained=True)
point, _ = _validate_point(
    {
        "kind": "difference",
        "summary": "The treaties were silent",
        "national_claim": "India provides a route.",
        "national_citation_ids": [NAT_ID],
        "international_claim": "The international corpus produced no answer here.",
        "international_citation_ids": [],
    },
    NATIONAL, ABSTAINED,
)
record("an abstaining side can be reported without citations",
       point is not None and point.international_claim is not None)

print("\n" + "=" * 74)
failed = [r for r in results if r[0] == "FAIL"]
print(f" {len(results) - len(failed)}/{len(results)} checks passed")
if failed:
    print("\n FAILURES:")
    for _, name, detail in failed:
        print(f"   - {name}: {detail}")
print("=" * 74 + "\n")
sys.exit(1 if failed else 0)
