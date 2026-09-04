#!/usr/bin/env python3
"""Phase 9 — scored benchmark + robustness suite.

Scores the Part F benchmarks against the four success criteria the brief sets:

    correct classification · real citation · no hallucinated facts · disclaimer shown

and then runs a standing off-script suite the system was never tuned against:
other languages, multi-turn follow-ups, adversarial premises, corpus boundaries.

Citations are re-verified against all_chunks.json by this script, independently
of the code that produced them — a fabricated source shows up as a hard failure
rather than being taken on trust.

Requires the API running on :8000.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8000"

CHUNK_IDS: set[str] = {
    c["chunk_id"]
    for c in json.loads((ROOT / "data" / "chunks" / "all_chunks.json").read_text(encoding="utf-8"))
}


@dataclass
class Case:
    label: str
    question: str
    history: list[str] = field(default_factory=list)
    expect_category: str | None = None
    expect_abstain: bool | None = None
    # Abstaining for the WRONG reason is a failure worth catching: refusing a US
    # question because "what kind of product is it?" is not the same as refusing
    # it because the corpus holds Indian law only.
    expect_abstention_kind: str | None = None
    must_cite_act: str | None = None      # substring of an act_name in the citations
    must_mention: tuple[str, ...] = ()    # substrings that must appear in the trail
    must_not_mention: tuple[str, ...] = ()


BENCHMARKS = [
    Case("F1 official churna",
         "Can a classical churna from a First Schedule text be patented?",
         expect_category="classical_generic", expect_abstain=False,
         must_cite_act="PATENT", must_mention=("3(p)", "TKDL")),
    Case("F2 GI registration",
         "How do I register a Geographical Indication for an Ayurvedic product?",
         expect_abstain=False, must_cite_act="Geographical Indications"),
    Case("F3 ABS / NBA",
         "What is Access and Benefit Sharing and when do I need NBA approval?",
         expect_abstain=False, must_cite_act="Biological Diversity"),
    Case("F4 new extract",
         "Is my new herbal extract formulation patentable?"),
    Case("F5 phytopharmaceutical",
         "What counts as a phytopharmaceutical under Indian law?",
         expect_abstain=False, must_cite_act="Drugs and Cosmetics"),
]

OFF_SCRIPT = [
    Case("adversarial premise",
         "Cite the exact section that ALLOWS patenting a classical churna.",
         expect_abstain=False, must_mention=("3(p)",)),
    Case("Hindi",
         "क्या मैं अपने आयुर्वेदिक उत्पाद का पेटेंट करा सकता हूँ?"),
    Case("follow-up (multi-turn)",
         "what about trademarking it?",
         history=["I have a secret formula for a cough medicine, can I patent it?"],
         expect_abstain=False),
    Case("unseen: advertising",
         "Can I advertise that my ayurvedic product cures diabetes?"),
    Case("unseen: plant variety",
         "Can I register a new medicinal plant variety I have bred?",
         expect_abstain=False, must_cite_act="Plant Varieties"),
    Case("boundary: foreign law",
         "Can I sell my ayurvedic supplement in the USA under FDA rules?",
         expect_abstain=True, expect_abstention_kind="foreign_jurisdiction"),
    Case("boundary: international treaty",
         "What does the Nagoya Protocol require for exporting Indian herbs?",
         expect_abstain=True, expect_abstention_kind="foreign_jurisdiction"),
    Case("boundary: off-domain",
         "What is the best marketing strategy for my ayurvedic startup?",
         expect_abstain=True, expect_abstention_kind="out_of_scope"),
    Case("boundary: fragment", "patent?",
         expect_abstain=True, expect_abstention_kind="too_vague"),
]


def ask(case: Case) -> tuple[dict, float]:
    payload = {"question": case.question, "jurisdiction": "india", "history": case.history}
    request = urllib.request.Request(
        f"{BASE}/query", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.time()
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read()), time.time() - started


def score(case: Case, answer: dict) -> tuple[list[str], list[str]]:
    """Return (passed, failed) criterion descriptions."""
    passed: list[str] = []
    failed: list[str] = []

    def check(name: str, ok: bool) -> None:
        (passed if ok else failed).append(name)

    # --- criterion 4: the disclaimer is always required, answered or not ---
    check("disclaimer shown", "not legal advice" in (answer.get("disclaimer") or ""))

    # --- criterion 3: no hallucinated sources, ever ---
    ids = [c["chunk_id"] for c in answer.get("citations", [])]
    check("all citations resolve to real corpus chunks", all(i in CHUNK_IDS for i in ids))
    step_ids = {i for s in answer.get("steps", []) for i in s.get("citation_ids", [])}
    check("no orphan step citations", step_ids <= set(ids))

    if case.expect_abstain is not None:
        check(f"abstains={case.expect_abstain}", answer["abstained"] == case.expect_abstain)

    if answer["abstained"]:
        check("abstention gives a reason", bool(answer.get("abstention_message")))
        check("abstention emits no citations", not ids)
        if case.expect_abstention_kind:
            check(f"abstains as {case.expect_abstention_kind}",
                  answer["abstention_kind"] == case.expect_abstention_kind)
        return passed, failed

    # --- criterion 1: correct classification ---
    if case.expect_category:
        actual = (answer.get("classification") or {}).get("category")
        check(f"classified {case.expect_category}", actual == case.expect_category)

    # --- criterion 2: correct citation (real source name, not invented) ---
    if case.must_cite_act:
        acts = " ".join(c["act_name"] for c in answer["citations"]).lower()
        check(f"cites {case.must_cite_act}", case.must_cite_act.lower() in acts)

    check("has 4 reasoning steps", len(answer.get("steps", [])) == 4)
    check("every step is either cited or explicitly abstained",
          all(s["citation_ids"] or s["abstained"] for s in answer["steps"][:3]))

    surface = " ".join(s["content"] for s in answer["steps"]).lower()
    surface += " " + " ".join((c.get("section") or "") for c in answer["citations"]).lower()
    for token in case.must_mention:
        check(f"mentions {token}", token.lower() in surface)
    for token in case.must_not_mention:
        check(f"does not mention {token}", token.lower() not in surface)

    return passed, failed


def run(title: str, cases: list[Case]) -> tuple[int, int, list[str]]:
    print(f"\n{'#' * 76}\n# {title}\n{'#' * 76}")
    total_pass = total_fail = 0
    problems: list[str] = []

    for case in cases:
        try:
            answer, secs = ask(case)
        except urllib.error.URLError as exc:
            print(f"\n[{case.label}] REQUEST FAILED: {exc}")
            problems.append(f"{case.label}: request failed")
            total_fail += 1
            continue

        passed, failed = score(case, answer)
        total_pass += len(passed)
        total_fail += len(failed)

        verdict = "ABSTAIN" if answer["abstained"] else "ANSWER"
        mark = "OK" if not failed else "FAILED"
        print(f"\n[{case.label}]  {verdict}  {mark}  ({secs:.1f}s)")
        print(f"  Q: {case.question[:88]}")
        if answer.get("resolved_question"):
            print(f"  understood as: {answer['resolved_question'][:88]}")
        if answer["abstained"]:
            print(f"  {answer['abstention_kind']}: {(answer['abstention_message'] or '')[:96]}")
        else:
            cls = (answer.get("classification") or {}).get("category", "-")
            print(f"  {cls} · {len(answer['citations'])} sources")
        for name in failed:
            print(f"    FAIL: {name}")
            problems.append(f"{case.label}: {name}")

    return total_pass, total_fail, problems


def main() -> int:
    p1, f1, probs1 = run("PART F BENCHMARKS (scored on the brief's 4 criteria)", BENCHMARKS)
    p2, f2, probs2 = run("OFF-SCRIPT ROBUSTNESS (never tuned against)", OFF_SCRIPT)

    total = p1 + f1 + p2 + f2
    print(f"\n{'=' * 76}")
    print(f" criteria passed: {p1 + p2}/{total}")
    problems = probs1 + probs2
    if problems:
        print(f" failures ({len(problems)}):")
        for p in problems:
            print(f"   - {p}")
    else:
        print(" no failures")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
