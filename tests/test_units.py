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
from app.citations import (  # noqa: E402
    provision_support,
    strip_chunk_ids,
    strip_unsupported_provisions,
)
from app.confidence import assess  # noqa: E402
from app.corpus_index import all_chunks  # noqa: E402
from app.comparison import _CHUNK_ID as _COMPARISON_CHUNK_ID  # noqa: E402
from app.conversation import EXAMPLE_QUESTIONS, conversational_reply  # noqa: E402
from app.escalation import assess as assess_escalation  # noqa: E402
from app.ratelimit import RateLimiter  # noqa: E402
from app.retrieval import (  # noqa: E402
    Evidence,
    Expansion,
    RetrievalResult,
    is_question_form,
    is_too_vague,
)
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
section("VAGUENESS GUARD - short questions pass, fragments still refused")

# The bug: a word count refused real questions. TEST_RESULTS.md recorded both of
# these being told "that is too short for me to search on", on both models,
# deterministically - they are the first things a judge types.
MUST_ANSWER = [
    "What is a Geographical Indication?",
    "What is ABS?",
    # Same shape, other regimes - the fix must not be special-cased to two strings.
    "What is TKDL?",
    "What is a churna?",
    "Is a churna patentable?",
    "Do I need NBA approval?",
    "Can I patent Ashwagandha?",
    "What does Rule 158-B require?",
    # A wh-word that does not open the sentence, with an explicit question mark.
    "GI tag - what is it?",
    # Hindi: the deferred multilingual phase must not regress on day one.
    "जीआई टैग क्या है?",
]

# These sailed through the ORIGINAL guard's intent and must keep being refused:
# a fragment cannot be retrieved against, and refusing costs no API call.
MUST_REFUSE = [
    "help",
    "?",
    "tell me about law",
    "patent?",           # punctuation on a keyword is not a question
    "ayurveda",
    "help with my product",
    "please explain",
    "",
    "   ",
    "the",
    # Asks something, but names nothing to search for. contextualise() resolves
    # this into a standalone question BEFORE the guard runs; if that fails there
    # is genuinely nothing here.
    "Why not?",
]

for _q in MUST_ANSWER:
    record(f"answerable: {_q!r}", not is_too_vague(_q))

for _q in MUST_REFUSE:
    record(f"still refused: {_q!r}", is_too_vague(_q))

# The guard must stay free of network and corpus state - it runs before any API
# call precisely to save one, and comparison.py calls it on a bare product name.
record("guard is pure (no corpus load needed)",
       is_too_vague("x") is True and is_too_vague("What is ABS?") is False)

# Question-form detection is the discriminator; test it directly so a future
# change to the word counts cannot silently break the reasoning behind them.
record("question form: leading wh-word", is_question_form("What is ABS?"))
record("question form: subject-auxiliary inversion", is_question_form("Is a churna patentable?"))
record("question form: trailing ? alone is NOT a question", not is_question_form("patent?"))
record("question form: imperative is not a question", not is_question_form("tell me about law"))

# A three-content-word question is unaffected by any of this - the previous
# behaviour for ordinary questions must be untouched.
record("long questions unaffected",
       not is_too_vague("Can a classical churna from a First Schedule text be patented?"))


section("PROVISION GUARD - a section number the evidence lacks does not ship")

# Chunk ids are resolved by CONTENT, never hardcoded - CLAUDE.md 6g, after a
# corpus rebuild renumbered every document and invalidated pinned ids. Writing
# "DOC003_chunk_167" into this file is how the first draft of this test failed:
# that id carried Rule 122-E before the rebuild and carries nothing now.
#
# The pair below is the whole test: one chunk that contains Section 3(p) and
# NOT 3(e), and one that contains 3(e).
def _shortest_chunk_with(*needles: str, absent: str = "") -> str:
    """The shortest chunk containing every needle, and not `absent`."""
    best_id, best_len = None, 10**9
    for chunk in all_chunks():
        text = chunk.get("chunk_text", "")
        if all(n in text for n in needles) and (not absent or absent not in text):
            if len(text) < best_len:
                best_id, best_len = chunk["chunk_id"], len(text)
    assert best_id, f"no chunk contains {needles!r}"
    return best_id


_MANUAL_3P = _shortest_chunk_with("3(p)", "traditional knowledge", absent="3(e)")
_MANUAL_3E = _shortest_chunk_with("3(e)")
_RULE_122E = _shortest_chunk_with("122-E")

_supported, _unsupported = provision_support(
    "Under Section 3(p) an invention which is traditional knowledge is not patentable.",
    [_MANUAL_3P],
)
record("a provision the cited chunk contains is supported",
       _supported and not _unsupported, f"{_supported} / {_unsupported}")

_supported, _unsupported = provision_support(
    "Under Section 3(e), a mere admixture is not patentable.", [_MANUAL_3P]
)
record("a provision the cited chunk lacks is unsupported",
       _unsupported and not _supported, f"{_supported} / {_unsupported}")

_supported, _unsupported = provision_support(
    "Under Section 3(e), a mere admixture is not patentable.", [_MANUAL_3E]
)
record("the same provision IS supported by the chunk that carries it",
       _supported and not _unsupported, f"{_supported} / {_unsupported}")

# This is the exact shape measured on the flagship: one good sentence, one
# fabricated. Only the fabricated sentence may be removed.
_text = (
    "Under Section 3(p) of the Patents Act, traditional knowledge is not an invention. "
    "Additionally, under Section 3(e), a mere admixture is not patentable. "
    "The Examiner consults the TKDL."
)
_clean, _removed = strip_unsupported_provisions(_text, [_MANUAL_3P])
record("the fabricated sentence is removed", "3(e)" not in _clean, _clean[:70])
record("the supported sentence survives", "Section 3(p)" in _clean)
record("the unrelated sentence survives", "TKDL" in _clean)
record("what was removed is reported", _removed == ["Section 3(e)"], f"{_removed}")

# Prose with no provision references must come back untouched, byte for byte.
_plain = "The Traditional Knowledge Digital Library is used by examiners as prior art."
record("prose naming no provision is unchanged",
       strip_unsupported_provisions(_plain, [_MANUAL_3P]) == (_plain, []))

# Rule/Regulation forms and hyphen variants, since the corpus writes "122-E".
record("Rule form is recognised",
       provision_support("Rule 122-E applies.", [])[1] == ["Rule 122-E"])
record("hyphen spacing does not matter",
       provision_support("Rule 122 - E provides.", [_RULE_122E])[0] != [],
       f"resolved {_RULE_122E}")

# Empty evidence must not crash, and must treat everything as unsupported.
record("empty evidence marks provisions unsupported",
       provision_support("Section 3(p) applies.", [])[1] == ["Section 3(p)"])
record("empty text is handled", strip_unsupported_provisions("", []) == ("", []))


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
section("CONFIDENCE REACHABILITY - the bottom bucket must be reachable")


def _ev(chunk_id, act, dense, lexical):
    return Evidence(chunk_id=chunk_id, text="t", score=1.0,
                    dense_rank=dense, lexical_rank=lexical,
                    metadata={"act_name": act})


def _result(evidence):
    return RetrievalResult(evidence, True, "", 0.30, 20.0)


def _step(number, cited, abstained=False):
    return ReasoningStep(step=number, title=str(number), content="c",
                         citation_ids=cited, abstained=abstained)


# The exact shape measured in TEST_RESULTS.md as the WORST answer of ~50: an
# unsourced headline, one of three substantive steps sourced, resting on a
# single act - and retrieval agreement so good it scored 0.50 and was labelled
# "Partly supported". This is the case the bottom bucket exists for.
_weak = assess(
    steps=[_step(1, ["a1"]), _step(2, [], abstained=True), _step(3, [], abstained=True)],
    citation_ids=["a1"],
    rejected_ids=[],
    result=_result([_ev("a1", "D&C Rules", 0, 0), _ev("a2", "D&C Rules", 1, 1),
                    _ev("a3", "D&C Rules", 2, 2), _ev("a4", "D&C Rules", 3, 3),
                    _ev("a5", "D&C Rules", 4, 4)]),
)
record("1 of 3 steps sourced, single act -> limited",
       _weak.level is ConfidenceLevel.LIMITED, f"{_weak.level.value} {_weak.score}")
record("the cap explains itself",
       any("only 1 of 3" in r for r in _weak.reasons),
       "; ".join(_weak.reasons)[:110])

# 2 of 3 sourced is NOT thin - the cap must not swallow ordinary answers.
_ok = assess(
    steps=[_step(1, ["a1"]), _step(2, ["a2"]), _step(3, [], abstained=True)],
    citation_ids=["a1", "a2"],
    rejected_ids=[],
    result=_result([_ev("a1", "Patents Act", 0, 0), _ev("a2", "Manual", 1, 1)]),
)
record("2 of 3 steps sourced is not capped to limited",
       _ok.level is not ConfidenceLevel.LIMITED, f"{_ok.level.value} {_ok.score}")
record("...but an abstaining step also cannot be 'well supported'",
       _ok.level is ConfidenceLevel.MODERATE, f"{_ok.level.value} {_ok.score}")

# Agreement is now scored over CITED passages. An answer citing one poorly
# corroborated chunk must not inherit the agreement of four it never cited.
_uncorroborated = assess(
    steps=[_step(1, ["a1"]), _step(2, ["a1"]), _step(3, ["a1"])],
    citation_ids=["a1"],
    rejected_ids=[],
    result=_result([
        _ev("a1", "D&C Rules", 0, 99),          # cited, but lexical never ranked it
        _ev("a2", "Patents Act", 1, 1),         # not cited - must not count
        _ev("a3", "Manual", 2, 2),              # not cited - must not count
    ]),
)
record("agreement counts only cited passages",
       _uncorroborated.score < 0.75,
       f"{_uncorroborated.level.value} {_uncorroborated.score}")
record("agreement reason talks about cited passages",
       any("cited passage" in r for r in _uncorroborated.reasons),
       "; ".join(_uncorroborated.reasons)[:110])

# And the top of the range must still be reachable, or the badge is just as
# useless in the other direction.
_strong = assess(
    steps=[_step(1, ["a1"]), _step(2, ["a2"]), _step(3, ["a3"])],
    citation_ids=["a1", "a2", "a3"],
    rejected_ids=[],
    result=_result([_ev("a1", "Patents Act", 0, 0), _ev("a2", "Manual", 1, 1),
                    _ev("a3", "About TKDL", 2, 2)]),
)
record("a fully sourced, corroborated, multi-source answer is still high",
       _strong.level is ConfidenceLevel.HIGH, f"{_strong.level.value} {_strong.score}")

record("all three levels are reachable",
       {_weak.level, _ok.level, _strong.level} == {
           ConfidenceLevel.LIMITED, ConfidenceLevel.MODERATE, ConfidenceLevel.HIGH},
       f"{_weak.level.value}/{_ok.level.value}/{_strong.level.value}")


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
section("PROSE CLEANUP - no placeholders, no control characters")

# TEST_RESULTS.md called this "model chatter". It was not: strip_chunk_ids
# SUBSTITUTED the phrase "the cited source" for any id the model wrote inline,
# which is why it always landed exactly where a citation marker would and why it
# appeared on both models. These are the real observed strings.
for _bad in [
    "identity, morphological description, habitat and collection details DOC003_chunk_807.",
    "excipient rules under Rules 168-169 DOC003_chunk_256, DOC003_chunk_257.",
    "into five international languages (DOC024_chunk_003) including English.",
    "Details the cited source, the cited source.",
    "As per the cited source, traditional knowledge is not patentable.",
]:
    _clean = strip_chunk_ids(_bad)
    record(f"no placeholder survives: {_bad[:44]!r}",
           "cited source" not in _clean.lower() and "DOC0" not in _clean, _clean[:60])

# The committed code replaced " ." with a literal SOH byte (0x01) instead of a
# backreference, so a tidied sentence lost its full stop and gained an invisible
# control character. Assert the whole class, not just that one byte.
_control_free = strip_chunk_ids(
    "Requirements include habitat and collection details DOC003_chunk_807."
)
record("punctuation survives the tidy-up", _control_free.endswith("details."), _control_free)
record("no control characters in cleaned prose",
       not any(ord(ch) < 32 and ch not in "\\n\\t" for ch in _control_free))

# A leading id used to take the sentence's capital with it.
record("a stripped leading id restores the capital",
       strip_chunk_ids("DOC020_chunk_116 states that this is barred.")
       .startswith("States that"))

# Prose with nothing to strip must be returned untouched.
_intact = "A clean sentence, with punctuation; it should survive intact."
record("clean prose is unchanged", strip_chunk_ids(_intact) == _intact)
record("empty input is handled", strip_chunk_ids("") == "")


section("SOURCE HYGIENE - no invisible control characters in backend code")

# Two real bugs in this repo were literal control bytes sitting where an escape
# sequence was meant to be, and both were invisible in every rendering of the
# file - they only showed up when the bytes were read:
#
#   citations.py   re.sub(r"\s+([,.;:])", "\x01", ...)   should have been r"\1"
#                  -> tidying " ." DELETED the full stop and inserted a SOH byte
#   comparison.py  re.compile(r"\x08DOC\d{3}_chunk_\d{3}\x08")  should have been \b
#                  -> the pattern could never match, so the chunk-id stripper
#                     that CLAUDE.md 6i describes was silently inert for months
#
# Both were committed. A one-line sweep catches the whole class, and costs
# nothing, so it runs every time.
_ctrl_offenders = []
for _path in sorted((ROOT / "backend" / "app").glob("*.py")):
    _text = _path.read_text(encoding="utf-8")
    for _i, _ch in enumerate(_text):
        if ord(_ch) < 32 and _ch not in "\n\t":
            _ctrl_offenders.append(f"{_path.name}:{_i} {hex(ord(_ch))}")

record("no control characters in any backend module",
       not _ctrl_offenders, "; ".join(_ctrl_offenders[:5]))

# And the specific stripper that was dead: prove it actually strips.
_stripped = _COMPARISON_CHUNK_ID.sub("", "The posture per DOC020_chunk_116 is barred.")
record("comparison chunk-id stripper is live (was an unmatchable pattern)",
       "DOC020_chunk_116" not in _stripped, _stripped.strip()[:60])


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
