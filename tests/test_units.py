#!/usr/bin/env python3
"""Unit tests for the modules that had no test coverage at all.

`comparison.py`, `confidence.py` and `conversation.py` were added after the
benchmark and e2e suites were written, and nothing referenced them - so the
reassuring "94/94, 24/24" numbers said nothing about three of twelve backend
modules, including the two most recently added. See COMPARISON_REPORT.md §6.9.

These are deliberately unit tests with no network: confidence scoring, the
small-talk matcher, request validation and the comparison assembler are all
pure logic, and testing them through a live LLM would be slow, flaky and would
burn the free-tier daily allowance. The live paths stay covered by e2e_api.py.

Run:
    .venv\\Scripts\\python.exe tests\\test_units.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pydantic import ValidationError  # noqa: E402

from app import audit  # noqa: E402
from app.citations import strip_chunk_ids  # noqa: E402
from app.confidence import assess  # noqa: E402
from app.conversation import EXAMPLE_QUESTIONS, conversational_reply  # noqa: E402
from app.escalation import assess as assess_escalation  # noqa: E402
from app.ratelimit import RateLimiter  # noqa: E402
from app.retrieval import Evidence, Expansion, RetrievalResult  # noqa: E402
from app.schemas import (  # noqa: E402
    AbstentionKind,
    Answer,
    HISTORY_TURNS,
    MAX_QUESTION_CHARS,
    CompareRequest,
    ConfidenceLevel,
    QueryRequest,
    ReasoningStep,
)

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))
    print(f"  [{PASS if ok else FAIL}] {name}{'  - ' + detail if detail else ''}")


def section(title: str) -> None:
    print("\n" + "=" * 74)
    print(f" {title}")
    print("=" * 74)


# --------------------------------------------------------------------------
# Helpers to build a plausible RetrievalResult without touching the corpus
# --------------------------------------------------------------------------

def evidence(chunk_id: str, act: str, dense: int | None, lexical: int | None) -> Evidence:
    return Evidence(
        chunk_id=chunk_id, text="...", score=0.1,
        dense_rank=dense, lexical_rank=lexical, metadata={"act_name": act},
    )


def result_of(items: list[Evidence]) -> RetrievalResult:
    return RetrievalResult(items, True, "ok", 0.30, 20.0)


def steps(cited: int) -> list[ReasoningStep]:
    """Four steps, the first `cited` of the substantive ones carrying a citation."""
    out = []
    for n in (1, 2, 3):
        has = n <= cited
        out.append(ReasoningStep(
            step=n, title=f"s{n}", content="text",
            citation_ids=[f"DOC001_chunk_00{n}"] if has else [],
            abstained=not has,
        ))
    out.append(ReasoningStep(step=4, title="s4", content="scope", citation_ids=[]))
    return out


# --------------------------------------------------------------------------
section("CONFIDENCE - the badge must discriminate, and must not flatter")
# --------------------------------------------------------------------------

strong = result_of([
    evidence("DOC001_chunk_001", "Patents Act", 0, 1),
    evidence("DOC002_chunk_002", "D&C Rules", 1, 0),
    evidence("DOC003_chunk_003", "BD Act", 2, 3),
    evidence("DOC004_chunk_004", "GI Act", 3, 2),
    evidence("DOC005_chunk_005", "Copyright Act", 4, 4),
])
cited_ids = [f"DOC00{i}_chunk_00{i}" for i in (1, 2, 3)]

best = assess(steps(3), cited_ids, [], strong)
record("fully cited, 3 sources, both retrievers agree -> high",
       best.level is ConfidenceLevel.HIGH, f"{best.level.value} {best.score}")

# The case that motivated the change: a perfect answer that also produced an
# unverifiable citation used to keep its "Well supported" badge.
with_rejection = assess(steps(3), cited_ids, ["DOC999_chunk_999"], strong)
record("a rejected citation drops it below high",
       with_rejection.level is not ConfidenceLevel.HIGH,
       f"{with_rejection.level.value} {with_rejection.score}")
record("rejected-citation cap is explained in the reasons",
       any("failed verification" in r for r in with_rejection.reasons))
record("rejection penalty is subtractive, not a x0.8 nudge",
       with_rejection.score < best.score - 0.1,
       f"{best.score} -> {with_rejection.score}")

# Agreement must mean "both ranked it highly", not "neither excluded it".
weak_agreement = result_of([
    evidence("DOC001_chunk_001", "Patents Act", 0, 39),
    evidence("DOC002_chunk_002", "D&C Rules", 1, 38),
    evidence("DOC003_chunk_003", "BD Act", 2, 37),
    evidence("DOC004_chunk_004", "GI Act", 3, 36),
    evidence("DOC005_chunk_005", "Copyright Act", 4, 35),
])
weak = assess(steps(3), cited_ids, [], weak_agreement)
record("deep-but-present lexical ranks no longer count as agreement",
       weak.score < best.score, f"{best.score} -> {weak.score}")

single = result_of([evidence("DOC001_chunk_001", "Patents Act", 0, 0)])
capped = assess(steps(3), ["DOC001_chunk_001"], [], single)
record("a single source can never be high",
       capped.level is not ConfidenceLevel.HIGH, capped.level.value)

nothing = assess(steps(0), [], [], strong)
record("no step could be sourced -> limited",
       nothing.level is ConfidenceLevel.LIMITED, f"{nothing.level.value} {nothing.score}")

record("assess never raises on empty evidence",
       assess([], [], [], result_of([])).level is ConfidenceLevel.LIMITED)
record("score stays within 0..1",
       all(0.0 <= a.score <= 1.0 for a in (best, with_rejection, weak, capped, nothing)))


# --------------------------------------------------------------------------
section("CONVERSATION - small talk answered, real questions untouched")
# --------------------------------------------------------------------------

for greeting in ("hello", "Hi!", "  hey  ", "namaste", "Good morning", "नमस्ते"):
    record(f"greeting: {greeting!r}", conversational_reply(greeting) is not None)

for capability in ("what can you do", "who are you?", "How can you help", "help"):
    record(f"capability: {capability!r}", conversational_reply(capability) is not None)

for thanks in ("thanks", "thank you", "ok"):
    record(f"thanks: {thanks!r}", conversational_reply(thanks) is not None)

# The patterns anchor to the WHOLE message, so anything with real content must
# fall through to retrieval - this is what keeps "help" from swallowing
# "help me register a GI".
REAL_QUESTIONS = [
    "Can a classical churna be patented?",
    "help me register a GI for turmeric",
    "hello, can I patent my ashwagandha formulation?",
    "what can you do about Section 3(p)?",
    "thanks - now what about trademarking it?",
]
for question in REAL_QUESTIONS:
    record(f"falls through: {question[:44]!r}", conversational_reply(question) is None)

record("example questions are offered after small talk", len(EXAMPLE_QUESTIONS) >= 3)


# --------------------------------------------------------------------------
section("REQUEST VALIDATION - history truncates, never rejects")
# --------------------------------------------------------------------------

long_history = [f"question {i}" for i in range(20)]
request = QueryRequest(question="Can a churna be patented?", history=long_history)
record("20 turns of history are accepted, not 422'd", True)
record(f"history truncated to the last {HISTORY_TURNS}",
       len(request.history) == HISTORY_TURNS, f"{len(request.history)} kept")
record("the most RECENT turns are the ones kept",
       request.history[-1] == "question 19")

oversized = QueryRequest(question="ok question here", history=["x" * 9000])
record("an oversized history entry is truncated, not rejected",
       len(oversized.history[0]) == MAX_QUESTION_CHARS, f"{len(oversized.history[0])} chars")

record("blank history entries are dropped",
       QueryRequest(question="a real question", history=["", "   ", "real"]).history == ["real"])

for bad, label in [("", "empty question"), ("   ", "whitespace-only question"), ("a", "1 char")]:
    try:
        QueryRequest(question=bad)
        record(f"rejects {label}", False, "accepted")
    except ValidationError:
        record(f"rejects {label}", True)

try:
    CompareRequest(product="ab")
    record("compare rejects a 2-char product", False, "accepted")
except ValidationError:
    record("compare rejects a 2-char product", True)

record("compare accepts a real product description",
       CompareRequest(product="An ashwagandha churna standardised for withanolides").product.startswith("An ash"))


# --------------------------------------------------------------------------
section("CHUNK IDS NEVER REACH THE READER")
# The guard was `DOC\d{3}_chunk_\d{3}` and lived only in comparison.py, so any
# other shape half-matched and the reasoning steps had no guard at all.
for raw, must_not_contain in [
    ("Under DOC003_chunk_234 the rule applies.", "DOC003_chunk_234"),
    ("See [DOC020_chunk_116] for detail.", "DOC020_chunk_116"),
    ("Two digits: DOC3_chunk_45 here.", "DOC3_chunk_45"),
    ("Four digits: DOC003_chunk_1234 here.", "DOC003_chunk_1234"),
    ("Lowercase doc012_chunk_007 too.", "doc012_chunk_007"),
]:
    cleaned = strip_chunk_ids(raw)
    record(f"strips {must_not_contain}", "_chunk_" not in cleaned, cleaned[:56])

record("prose without ids is left alone",
       strip_chunk_ids("Rule 122-E applies here.") == "Rule 122-E applies here.")
record("punctuation survives the removal",
       strip_chunk_ids("Applies (DOC003_chunk_023).").endswith("."))


section("EXPANSION - failure is visible, not silent")
record("a healthy expansion reports ok", Expansion(["a", "b"]).ok is True)
failed = Expansion(["only the question"], ok=False, reason="upstream down")
record("a failed expansion reports not-ok", failed.ok is False)
record("a failed expansion still yields a usable query", failed.queries == ["only the question"])
record("a failed expansion carries a user-facing reason", bool(failed.reason))
record("RetrievalResult defaults to not-degraded", result_of([]).degraded is False)


# --------------------------------------------------------------------------
section("RATE LIMITING - protects the shared upstream quota")
# --------------------------------------------------------------------------

limiter = RateLimiter(limit=3, window=60.0)
record("requests under the limit are allowed",
       all(limiter.check("1.2.3.4")[0] for _ in range(3)))
allowed, retry_after = limiter.check("1.2.3.4")
record("the request over the limit is refused", allowed is False)
record("a retry-after is supplied", retry_after > 0, f"{retry_after}s")
record("a different client is unaffected", limiter.check("5.6.7.8")[0] is True)
limiter.reset()
record("reset clears the buckets", limiter.check("1.2.3.4")[0] is True)


# --------------------------------------------------------------------------
section("ESCALATION - offered for a real need, withheld otherwise")
# --------------------------------------------------------------------------

# Offered: a genuine legal need this system structurally cannot meet.
for kind in (AbstentionKind.FOREIGN_JURISDICTION, AbstentionKind.NO_EVIDENCE):
    offer, why = assess_escalation(True, kind, None)
    record(f"offers a human on {kind.value}", offer and bool(why))

# Withheld: the user has not asked a legal question yet, or nothing a person
# could fix went wrong. These negatives are the whole point — an offer on every
# refusal is noise people learn to ignore.
for kind in (AbstentionKind.TOO_VAGUE, AbstentionKind.OUT_OF_SCOPE,
             AbstentionKind.GATE_UNAVAILABLE, AbstentionKind.CONVERSATIONAL):
    offer, _ = assess_escalation(True, kind, None)
    record(f"does NOT offer a human on {kind.value}", not offer)

offer, why = assess_escalation(False, AbstentionKind.NONE, ConfidenceLevel.LIMITED)
record("offers a human on a thinly supported answer", offer and bool(why))
for level in (ConfidenceLevel.HIGH, ConfidenceLevel.MODERATE):
    offer, _ = assess_escalation(False, AbstentionKind.NONE, level)
    record(f"does NOT offer a human on a {level.value}-confidence answer", not offer)


# --------------------------------------------------------------------------
section("AUDIT - auditable without retaining what people asked")
# --------------------------------------------------------------------------

QUESTION = "Can a classical churna from a First Schedule text be patented?"
sample = Answer(question=QUESTION, headline="No.")

# Capture entries instead of touching the real log file.
written: list[dict] = []
original_write = audit._write
audit._write = written.append  # type: ignore[assignment]

audit.log_answer(QUESTION, sample, consent=False, elapsed_s=1.5)
entry = written[-1]
record("an entry is written even without consent", bool(entry))
record("the question TEXT is absent without consent", "question" not in entry)
record("a fingerprint is recorded instead", bool(entry.get("question_id")))
record("what the system decided is recorded",
       "abstained" in entry and "abstention_kind" in entry)
record("citation counts are recorded",
       "citations" in entry and "rejected_citations" in entry)
record("timing and model are recorded",
       entry.get("elapsed_s") == 1.5 and bool(entry.get("model")))

audit.log_answer(QUESTION, sample, consent=True)
record("the question text IS stored with consent", written[-1].get("question") == QUESTION)

record("the fingerprint ignores case and whitespace",
       audit._fingerprint("  Can A  CHURNA?  ") == audit._fingerprint("can a churna?"))
record("different questions fingerprint differently",
       audit._fingerprint("a question") != audit._fingerprint("another question"))


def _boom(_entry: dict) -> None:
    raise OSError("disk full")


# An audit failure must never break an answer - the whole module is best-effort.
audit._write = _boom  # type: ignore[assignment]
try:
    audit.log_answer(QUESTION, sample, consent=True)
    record("a failing audit write does not raise", True)
except Exception as exc:  # noqa: BLE001
    record("a failing audit write does not raise", False, type(exc).__name__)
audit._write = original_write  # type: ignore[assignment]


# --------------------------------------------------------------------------
print("\n" + "=" * 74)
failed_checks = [r for r in results if r[0] == FAIL]
print(f" {len(results) - len(failed_checks)}/{len(results)} checks passed")
if failed_checks:
    print("\n FAILURES:")
    for _, name, detail in failed_checks:
        print(f"   - {name}: {detail}")
print("=" * 74 + "\n")

sys.exit(1 if failed_checks else 0)
