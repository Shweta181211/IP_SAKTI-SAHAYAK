#!/usr/bin/env python3
"""Plain-language rendering and the next-steps block, tested without a model.

Both features are structured so their safety properties are decidable offline,
which is the point of testing them this way:

  * Plain mode is a REWRITE of a finished answer, not a second generation. The
    citation lists and the classification are copied in code and never pass
    through the model, so "the citations are identical between styles" is an
    equality assertion rather than a sample of model behaviour. The test stubs
    the model with a deliberately badly-behaved rewriter - one that tries to
    change citations, drop steps and invent a provision - and asserts that none
    of it gets through.

  * Next steps are validated exactly like reasoning steps: an id must appear in
    the SOURCE answer's own citations, and for a comparison it must belong to
    the side the step is attributed to. `_validate` is a pure function over a
    raw dict, so every way a step can be wrong is testable directly instead of
    waiting for a live model to produce one.

Run:
    .venv\\Scripts\\python.exe tests\\test_style_and_steps.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app import next_steps as ns_mod  # noqa: E402
from app import plain_language as pl_mod  # noqa: E402
from app.citations import build_citation  # noqa: E402
from app.corpus_index import all_chunks  # noqa: E402
from app.next_steps import _validate, next_steps_for_answer  # noqa: E402
from app.plain_language import apply_style, to_plain_language  # noqa: E402
from app.schemas import (  # noqa: E402
    AbstentionKind,
    Answer,
    ClassificationResult,
    Category,
    ReasoningStep,
    ResponseStyle,
)

results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append(("PASS" if ok else "FAIL", name, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{'  - ' + detail if detail else ''}")


def chunk_with(jurisdiction: str, needle: str) -> str:
    for chunk in all_chunks():
        if chunk.get("jurisdiction") == jurisdiction and needle.lower() in str(
            chunk.get("act_name", "")
        ).lower():
            return chunk["chunk_id"]
    raise AssertionError(f"no {jurisdiction} chunk for {needle!r}")


NAT_A = chunk_with("national", "patents act")
NAT_B = chunk_with("national", "About TKDL")
INT_A = chunk_with("international", "TRIPS")


def sample_answer() -> Answer:
    return Answer(
        question="Can a classical churna be patented?",
        jurisdiction="national",
        headline="A classical churna is not patentable under Section 3(p).",
        headline_citation_ids=[NAT_A],
        classification=ClassificationResult(
            category=Category.CLASSICAL_GENERIC, label="Classical / generic",
            rationale="from a First Schedule text",
        ),
        confidence=None,
        steps=[
            ReasoningStep(step=1, title="Classification",
                          content="The product is a classical formulation.",
                          citation_ids=[NAT_A]),
            ReasoningStep(step=2, title="Legal position",
                          content="Section 3(p) excludes traditional knowledge.",
                          citation_ids=[NAT_A]),
            ReasoningStep(step=3, title="Protection / action route",
                          content="TKDL is the defensive route.", citation_ids=[NAT_B]),
            ReasoningStep(step=4, title="Jurisdiction note",
                          content="Indian law only.", citation_ids=[]),
        ],
        citations=[c for c in (build_citation(NAT_A), build_citation(NAT_B)) if c],
    )


print("=" * 74)
print(" PLAIN LANGUAGE - same facts, same citations, different words")
print("=" * 74)

ORIGINAL = sample_answer()

# A deliberately badly-behaved rewriter: it renames steps, tries to attach its
# own citations, invents a provision the sources never mention, and drops a
# step. None of that may reach the reader.
def naughty_rewrite(prompt, **kwargs):
    return {
        "headline": "You cannot patent this recipe because it is already public knowledge.",
        "steps": [
            {"step": 1, "content": "Your product counts as a classical recipe.",
             "citation_ids": ["DOC999_chunk_001"]},
            {"step": 2, "content": "Section 3(d) also blocks it entirely."},
            # step 3 omitted on purpose
        ],
    }


pl_mod.complete_json = naughty_rewrite
PLAIN = to_plain_language(ORIGINAL)

record("style is marked as plain", PLAIN.response_style == "plain", PLAIN.response_style)
record("the headline is rewritten",
       PLAIN.headline != ORIGINAL.headline, (PLAIN.headline or "")[:66])
record("CITATIONS ARE IDENTICAL",
       [c.chunk_id for c in PLAIN.citations] == [c.chunk_id for c in ORIGINAL.citations],
       f"{[c.chunk_id for c in PLAIN.citations]}")
record("per-step citations are identical",
       [s.citation_ids for s in PLAIN.steps] == [s.citation_ids for s in ORIGINAL.steps])
record("the rewriter's own citation ids are ignored",
       "DOC999_chunk_001" not in {c for s in PLAIN.steps for c in s.citation_ids})
record("classification is unchanged",
       PLAIN.classification == ORIGINAL.classification)
record("step count and titles are unchanged",
       [(s.step, s.title) for s in PLAIN.steps] == [(s.step, s.title) for s in ORIGINAL.steps])
record("a step the rewriter dropped keeps its original wording",
       PLAIN.steps[2].content == ORIGINAL.steps[2].content, PLAIN.steps[2].content[:50])
record("a provision the step's sources lack is removed",
       "3(d)" not in PLAIN.steps[1].content, PLAIN.steps[1].content[:66])

# A failed rewrite must leave the legal answer intact, not a half-rewritten one.
def broken_rewrite(prompt, **kwargs):
    raise pl_mod.LLMUnavailable("no capacity")


pl_mod.complete_json = broken_rewrite
FALLBACK = to_plain_language(sample_answer())
record("an unavailable rewrite falls back to the legal wording",
       FALLBACK.headline == ORIGINAL.headline and FALLBACK.response_style == "legal",
       FALLBACK.response_style)

record("legal style is a no-op",
       apply_style(ORIGINAL, ResponseStyle.LEGAL) is ORIGINAL)

# An abstention has no trail to rewrite and is already plain.
ABSTAINED = Answer(question="q", abstained=True,
                   abstention_kind=AbstentionKind.OUT_OF_SCOPE,
                   abstention_message="Out of scope.")
record("an abstention is passed through, only re-labelled",
       to_plain_language(ABSTAINED).abstention_message == "Out of scope.")


print("\n" + "=" * 74)
print(" NEXT STEPS - advice-shaped text still has to be sourced")
print("=" * 74)

ALLOWED = {NAT_A: "national", NAT_B: "national", INT_A: "international"}

step, rejected = _validate(
    {"text": "Check whether the formulation is recorded in the TKDL.",
     "citation_ids": [NAT_B], "jurisdiction": "national"}, ALLOWED)
record("a sourced step survives", step is not None and step.citation_ids == [NAT_B])

step, rejected = _validate(
    {"text": "Just go and register it somewhere.", "citation_ids": [],
     "jurisdiction": "national"}, ALLOWED)
record("an unsourced step is dropped", step is None, (rejected or "")[:60])

step, rejected = _validate(
    {"text": "File under Rule 158-B.", "citation_ids": ["DOC999_chunk_001"],
     "jurisdiction": "national"}, ALLOWED)
record("a fabricated citation drops the step", step is None)

# The comparison case: a step attributed to India may not rest on treaty text.
step, rejected = _validate(
    {"text": "India requires you to disclose the source.", "citation_ids": [INT_A],
     "jurisdiction": "national"}, ALLOWED)
record("a national step citing an international source is dropped",
       step is None, (rejected or "")[:60])

step, rejected = _validate(
    {"text": "Disclose the source when filing internationally.", "citation_ids": [INT_A],
     "jurisdiction": "international"}, ALLOWED)
record("the same citation is fine on the international side",
       step is not None and step.jurisdiction == "international")

step, _ = _validate(
    {"text": "Rely on Section 3(d) to object.", "citation_ids": [NAT_B],
     "jurisdiction": "national"}, ALLOWED)
record("a provision the cited source lacks is stripped from a step",
       step is None or "3(d)" not in step.text,
       (step.text if step else "(step dropped)")[:60])

# Abstentions produce no advice at all.
record("an abstained answer yields no steps",
       next_steps_for_answer(ABSTAINED).applicable is False)

# "What is X" questions should be allowed to produce nothing.
def not_applicable(prompt, **kwargs):
    return {"applicable": False, "reason": "This explains a concept; there is nothing to do."}


ns_mod.complete_json = not_applicable
skipped = next_steps_for_answer(sample_answer())
record("the model may decline to suggest anything",
       skipped.applicable is False and bool(skipped.reason), skipped.reason or "")
record("  and it carries its own disclaimer",
       "not a legal determination" in skipped.disclaimer)

print("\n" + "=" * 74)
failed = [r for r in results if r[0] == "FAIL"]
print(f" {len(results) - len(failed)}/{len(results)} checks passed")
if failed:
    print("\n FAILURES:")
    for _, name, detail in failed:
        print(f"   - {name}: {detail}")
print("=" * 74 + "\n")
sys.exit(1 if failed else 0)
