# Test Results — 6 September 2026 (post-fix re-run)

Automated execution of `MANUAL_TEST_CHECKLIST.md` (Categories 1–7, tests 1–23) plus the two
system-level checks from `COMPARISON_REPORT.md` §6.1 and §6.2, run against the system
**after** the fixes recorded in `CLAUDE.md` §6k.

The earlier two-model evaluation is preserved as `TEST_RESULTS_PREVIOUS.md`. Its findings
are what §6k fixed — and three of its diagnoses were wrong, which §6k corrects.

**How this was run.** `tests/run_checklist.py` calls the real HTTP API directly —
`POST /query` on `http://127.0.0.1:8000`, no browser, no mocks. Conversation tests send
`history` exactly as `App.tsx` builds it (`resolved_question ?? question` of each prior
answer turn, oldest first). Backend restarted cold beforehand, answer cache empty, rate
limiter disabled as the project's own suites do. Every raw response is in
**`TEST_RESULTS_RAW_V2.json`** (40 HTTP interactions).

| | |
|---|---|
| generation model | `gemini-3.5-flash-lite`, fallback `gemini-3.1-flash-lite` |
| provider config | now in `.env` — a plain `uvicorn` picks it up, no shell exports needed |
| health at start | `status: ok`, 2457 chunks in JSON, 2450 embedded, `anchor_problems: []` |
| citations emitted | **120, independently re-verified, 0 fabricated** |

**Latency in this run is not representative.** Queries took 63–90 s because the suite fires
continuously into Gemini's free per-minute cap and every call backs off. Measured
single-question latency on the same build is **~5–7 s**. See Capacity below.

---

## Summary

- **Total: 25** (23 checklist tests + 2 system checks)
- **Passed: 22 · Failed: 0 · Partial: 1 · Not conclusive: 1 · Not applicable: 1**

### Critical failures (Category 1, 3 or 4)

**None.** Category 1 lands, all four Category 3 questions answer from the right statutes,
and all four Category 4 abstentions are correct — including test 14, the one regression in
the previous run.

### Verdict table (▲ = changed since the previous run)

| # | Test | Verdict | |
|---|---|---|---|
| 1 | Classical churna / 3(p) / TKDL | **PASS** | ▲ was PARTIAL — TKDL not named |
| 2 | Classify: classical/generic | **PASS** | |
| 3 | Classify: patent/proprietary | **PASS** | |
| 4 | Classify: new/non-classical drug | **PASS** | ▲ was FAIL on MiniMax |
| 5 | Classify: phytopharmaceutical | **PASS** | |
| 6 | Classify: Ayurveda-Aahar | **PASS** | ▲ was PARTIAL — led with patent law |
| 7 | Classify: cosmetic | **PASS** | ▲ was PARTIAL — answered entirely on 3(p) |
| 8 | ABS / NBA approval | **PASS** | |
| 9 | GI registration | **PASS** | |
| 10 | TKDL explanation | **PASS** | |
| 11 | Trademark vs GI | **PASS** | |
| 12 | US / FDA — foreign jurisdiction | **PASS** | |
| 13 | Chocolate cake — out of domain | **PASS** | |
| 14 | "Will I win my lawsuit?" | **PASS** | ▲ was PARTIAL / regression |
| 15 | Greeting / empty message | **PASS** | |
| 16 | Follow-up carries subject | **PASS** | |
| 17 | Elliptical follow-up ("Why not?") | **PASS** | ▲ was FAIL on MiniMax |
| 18 | 12 questions in one session (§6.2) | **PASS** | ▲ was PARTIAL — 3 wrong refusals |
| 19 | Citation integrity | **PASS** | |
| 20 | Confidence on a weak answer | **PASS** | the checklist item is unusable as written — see below |
| 21 | Same question twice, fresh sessions | **NOT CONCLUSIVE** | upstream daily quota |
| 22 | International toggle | **NOT APPLICABLE** | corpus phase deferred |
| 23 | Disabled toggle communicates itself | **PARTIAL** | frontend, unchanged |
| §6.1 | Path traversal | **PASS** | |
| §6.2 | 9th-question 422 | **PASS** | |

### What changed, one line each

- **All six Category 2 classifications are correct AND answered on the right regime.** Test 7
  now gives cosmetic licensing under D&C s.18 instead of three steps of patent law.
- **The 12-question session answers all twelve.** The trademark and copyright questions that
  were refused with a false claim about our holdings now cite the Trade Marks Act and the
  Copyright Act.
- **Outcome-prediction is refused on any model**, with `escalate: true`.
- **The provision guard fired live**, removing three fabricated section references that
  would previously have shipped looking sourced.
- **Confidence discriminates**: 18 `high` / 12 `moderate`, against 13/2 before.

---

## Detailed results

### Category 1 — Official Benchmark

#### Test 1 — "Can a classical churna from a First Schedule text be patented?"

**PASS.** All three required elements: `classical_generic`, Section 3(p), TKDL as the route.

```json
{"http_status":200,"classification":{"category":"classical_generic"},
 "headline":"A classical churna described in authoritative Ayurvedic books is not patentable as it constitutes traditional knowledge.",
 "confidence":"high","confidence_score":0.938,
 "confidence_reasons":["every reasoning step is backed by a cited provision",
                       "supported by 4 independent sources",
                       "3 of the 4 cited passages were independently ranked highly by both semantic and keyword search"],
 "abstained":false,"rejected_citation_ids":[],"unsupported_provisions":[],
 "citations":["The Drugs and Cosmetics Rules 1945","Ayurvedic Formulary of India (AFI)",
              "MANUAL OF PATENT OFFICE PRACTICE, Sections 3(o), 3(p)","About TKDL"]}
```

**The four steps in plain language:**

| step | what it said | does it do its job? |
|---|---|---|
| 1 Classification | "A classical churna — an Ayurvedic drug made to a formula in an authoritative First Schedule book — and that matters because such formulations are traditional medicinal knowledge." | **Yes.** Classifies, says why the category is decisive, stops short of the conclusion. |
| 2 Legal position | "Under Section 3(p) of the Patents Act 1970, an invention that is in effect traditional knowledge, or an aggregation or duplication of known properties of a traditionally known component, is not an invention." | **Yes.** Law only, provision named inline. |
| 3 Action route | "To prevent misappropriation of such traditional knowledge India uses the TKDL, a database that serves as a defensive mechanism." | **Yes** — a named mechanism, not a restatement of the bar. This is the step that failed before. |
| 4 Jurisdiction | "Indian law only; international regimes outside this corpus." | **Yes.** |

**Consistency:** step 3 follows from step 2 — the bar is established, then the defensive
route that exists because of it. No contradiction.

#### Test 1 follow-up — "What about internationally?"

**PASS, with a behaviour change you should decide on deliberately.** This previously
abstained `foreign_jurisdiction`. It now answers — but **never states foreign law**.

```json
{"resolved_question":"Can a classical churna from a First Schedule text be patented internationally?",
 "abstained":false,"confidence":"high","confidence_score":0.85,
 "headline":"Classical Ayurvedic formulations are protected from misappropriation through the Traditional Knowledge Digital Library, which prevents the grant of patents based on prior art.",
 "citations":["The Drugs and Cosmetics Rules 1945","Ayurvedic Formulary of India (AFI)",
              "MANUAL OF PATENT OFFICE PRACTICE, Section 4","MANUAL OF PATENT OFFICE PRACTICE",
              "About TKDL","TKDL Access Policy"]}
```

Step 2 is explicitly *"Under Indian law…"* (novelty and prior art). Step 3 is TKDL's real,
documented role **at international patent offices**, which Indian sources do describe. Step 4
says *"international patent regimes and the specific laws of other countries are outside the
scope of this evidence."*

So it answers what our sources genuinely can say and disclaims the rest, rather than refusing
outright. That is arguably the better answer — and it is the **only Category 1 behaviour the
§6k gate widening changed**. Treated in full under International-Scope Detection Cases.

---

### Category 2 — the six classification categories

All six correct, and — the half that failed before — each answered on **its own regime**.

| # | Question | Category | Legal position is about | Confidence |
|---|---|---|---|---|
| 2 | grandmother's classical churna | `classical_generic` | Patents Act s.3(p), TKDL | high 0.875 |
| 3 | proprietary tonic | `patent_proprietary` | D&C Rules **r.161 labelling**, manufacturing licence | moderate 0.75 |
| 4 | new compound with trial data | `new_drug` | **Rule 122-D, Form 44**, Schedule Y data | moderate 0.75 |
| 5 | standardised single-plant extract | `phytopharmaceutical` | taxonomical identity, habitat, extraction and quality data | moderate 0.717 |
| 6 | turmeric health drink | `ayurveda_aahar` | **FSSAI Ayurveda Aahara Regs 2022, Regs 3 & 13** | moderate 0.55 |
| 7 | neem face cream | `cosmetic` | **D&C Act 1940 s.18**, manufacturing licence | high 0.75 |

**Test 7 in full, because it was the worst case before:**

```json
{"classification":{"category":"cosmetic"},
 "headline":"Your neem-based face cream is classified as a cosmetic and must comply with the Drugs and Cosmetics Act, 1940 and its Rules.",
 "confidence":"high","confidence_score":0.75,
 "citations":["Drugs and Cosmetics Act, 1940, Section 3","Drugs and Cosmetics Act, 1940, Section 18",
              "The Drugs and Cosmetics Rules 1945","Drugs and Cosmetics Act, 1940"]}
```

1. **Classification** — "A cosmetic, because it is applied to the body for beautifying or altering appearance." *Now agrees with the badge above it; previously step 1 contradicted it.*
2. **Legal position** — "Under Section 18 of the D&C Act 1940 it is prohibited to manufacture for sale or sell a cosmetic that is not of standard quality, is misbranded, adulterated or spurious." *The right regime.*
3. **Action route** — "Obtain a licence from the licensing authority; the application requires premises, staff and testing details." *Concrete, and distinct from step 2.*
4. **Jurisdiction** — standard scope note.

**Section 3(p) appears nowhere** — exactly what the checklist asked for.

Test 6 likewise: Regulation 3 (Schedule B categories; no added vitamins, minerals or amino
acids) and Regulation 13 (the "AYURVEDA AAHARA" label and logo) — the rules that actually
govern a food supplement.

---

### Category 3 — general / procedural questions

All four correctly `not_applicable` (no product to classify) and answered from the right
statutes.

| # | Question | Cited | Confidence |
|---|---|---|---|
| 8 | ABS / NBA approval | BD Act s.21, BD Rules 2024 rr.13 & 26, **Form 1 / Form 2 on the NBA portal** | high 0.817 |
| 9 | GI registration | GI Act ss.2, 3, 11; Kandhamal Haladi | high 0.9 |
| 10 | What is TKDL | About TKDL, TKDL Access Agreement & Policy, Manual ss.3(o)/3(p) | **high 1.0** |
| 11 | Trademark vs GI | **Trade Marks Act s.9** *and* the GI Act, cited separately | high 0.9 |

Test 10 explicitly does **not** claim to search TKDL's database — it describes examiners
using it, which is the required abstention behaviour. Test 11 cites the two statutes
separately, which was the checklist's actual requirement.

---

### Category 4 — safe abstention

| # | Question | Kind | Escalates | Citations |
|---|---|---|---|---|
| 12 | "Can I sell in the United States? What does the FDA require?" | `foreign_jurisdiction` | **yes** | 0 |
| 13 | "How do I bake a good chocolate cake?" | `out_of_scope` | no | 0 |
| 14 | "Will I win my patent infringement lawsuit?" | **`legal_advice`** | **yes** | 0 |
| 15 | "hi" | `conversational` (a reply, not a refusal) | no | 0 |
| 15 | `""` and `"   "` | HTTP 422, structured JSON | — | — |

**Test 14 is the fix that mattered most.** It previously answered with litigation procedure —
*"You may initiate a suit for infringement in a court not inferior to a District Court under
Section 104"* — and offered no escalation. Now:

> "I can tell you what the law says, but not how your own case will turn out or whether to
> bring one — that means applying the law to facts and evidence I cannot see. Ask what the
> law provides on infringement, remedies, defences or procedure and I will answer that with
> citations."

…with `escalate: true` and a reason pointing to a practitioner.
`tests/test_legal_advice.py` holds this on **two different models** (15/15 each) and asserts
that four *informational* questions — remedies, defences, forum, what counts as infringement
— are **still answered**. The system must not start flinching at the word "infringement".

Test 13's reason is correctly about the question rather than our holdings: *"a request for a
culinary recipe, which falls outside the scope of legal regulation of Ayurveda, drugs, or
food safety standards."*

---

### Category 5 — conversation

**Test 16 — PASS.** "What if I want to patent the plant itself instead?" resolved to
*"…the Ashwagandha plant itself instead of the extraction process"* without the user
re-naming it, and answered with Section 3(j) plus the Protection of Plant Varieties and
Farmers' Rights Act — exactly the exclusion the checklist predicted.

**Test 17 — PASS** (was FAIL). *"Why not?"* resolved to *"Why can I not patent a neem-based
face cream for external use?"* and produced a full cited answer, `high` 0.833. Patent framing
is correct **here** because turn 1 asked "Can I patent it?" — while the same product with no
such question (test 7) gets cosmetic regulation instead. That contrast is the Phase 5 fix
working in both directions rather than suppressing patent vocabulary globally.

**Test 18 — PASS.** Twelve questions in one session, history growing to 10 turns.

| # | Question | Result |
|---|---|---|
| 1 | What is the TKDL? | answered, high, 4 cites |
| 2 | How does the Patents Act treat traditional knowledge? | answered, high, 2 cites |
| 3 | What is a Geographical Indication? | **answered**, high, 4 cites — was `too_vague` |
| 4 | NBA approval to file a patent? | answered, moderate, 3 cites |
| 5 | Classical formulation under the D&C Act? | answered, moderate, 4 cites |
| 6 | Licence to manufacture an Ayurvedic medicine? | answered, moderate, 4 cites |
| **7** | **Can I trademark the name of my product?** | **answered** — Trade Marks Act ss.2, 9, 70 |
| 8 | Labelling rules for Ayurvedic medicines? | answered, high, 4 cites |
| **9** | **Can I copyright my formulation booklet?** | **answered** — Copyright Act cited |
| 10 | Phytopharmaceutical data requirements? | answered `phytopharmaceutical`, 7 cites |
| 11 | Is a plant variety protectable in India? | answered, moderate, 5 cites |
| 12 | What does the Drugs and Magic Remedies Act prohibit? | answered, moderate, 5 cites |

**No 422 anywhere** (§6.2 fixed) and **no refusals at all** — the previous run refused three
of the twelve, two with a false statement about our holdings. Those two:

```json
// Q7 - previously: "trademark law ... is not covered by the provided corpus"
{"headline":"You may register a trademark for your Ayurvedic product provided it is distinctive and does not fall under specific grounds for refusal.",
 "confidence":"moderate","confidence_score":0.633,
 "citations":["Trade Marks Act 1999, Section 2","Trade Marks Act 1999, Section 9","Trade Marks Act 1999, Section 70"]}
```

**Q9 is answered but thin, and that is worth stating plainly.** It says *"The provided
evidence does not contain information regarding the copyrighting of Ayurvedic formulation
booklets"* — retrieval returned Copyright Act passages on translation licensing and term
rather than s.13. That statement is about the **evidence**, which is accurate and permitted;
it is not the false claim about the corpus that the guard was built for. But the answer is
not useful. Asked standalone the same question reaches s.13(1)(a) (recorded in §6k). This is
retrieval variance, not a scope failure.

---

### Category 6 — citation and confidence integrity

**Test 19 — PASS.** All **120 citations** re-verified against `all_chunks.json`,
independently of the code that produced them:

```
citations checked: 120 across 38 responses
responses with integrity problems: 0
```

Four properties per citation: the chunk id exists in the corpus; the excerpt is a verbatim
substring of that chunk; any section shown on the card occurs in the chunk text; every
`citation_id` referenced by a step or the headline resolves to a card.
`rejected_citation_ids` was empty on every response.

**The provision guard fired live — three times, new since the last run:**

| test | removed | why |
|---|---|---|
| 16a | `Section 1(2)(1)(j)`, `Section 1(2)(1)(ac)` | named in prose, present in no retrieved chunk |
| 18-03 | `Section 2(1)(e)` | same |

Those sentences would previously have shipped beside perfectly valid citations, looking
sourced. This is `no fabricated authority` being enforced rather than asserted.

**One side effect to record honestly.** Removing the sentence in test 18-03 left the next one
without its antecedent — step 2 reads *"This applies where a specific quality, reputation, or
characteristic of the goods is essentially attributable to that geographical origin."*, where
"this" referred to the deleted definition. Removing the sentence is still right (the
alternative is shipping a fabricated provision) but the seam is visible. Worth a follow-up:
either re-generate the step or drop the dependent sentence too.

**Test 20 — PASS on behaviour; the checklist item cannot test what it intends.** The question
(TRIPS Art 27.3(b), "a very specific international treaty detail") is **correctly refused** as
`foreign_jurisdiction` — and a refusal carries no confidence badge, so this question can never
exercise calibration while the jurisdiction gate works.

What the run does show:

```
confidence across 30 substantive answers:  18 high  ·  12 moderate  ·  0 limited
previous run, same suite:                  13 high  ·   2 moderate  ·  0 limited
```

40% moderate against 13%, with the low end at **0.55** (test 6) — the badge now
discriminates rather than flattering. `LIMITED` is proven reachable by construction
(`tests/test_units.py`: one of three steps sourced on a single act → `limited`) and did not
fire live because no answer here was that thin. **Suggested rewording of the checklist item:**
use an *in-scope* question with known-thin evidence — e.g. the statutory definition of
"phytopharmaceutical", which `CLAUDE.md` §6b records as missing from the corpus.

**Test 21 — NOT CONCLUSIVE.** Run 1 (`T21a`) returned in **0.01 s**: a cache hit of test 1 in
the same process, so not an independent generation. Run 2 needed a cold restart, and both
attempts hit Gemini's **daily** quota:

```
429 RESOURCE_EXHAUSTED ... PerDay   ->   abstention_kind: gate_unavailable   (fail-closed, correct)
```

The system behaved correctly — it refused rather than answering unguarded — but the test needs
upstream capacity that no longer exists today. To complete it: restart, ask the flagship,
restart, ask again, diff classification and citation ids. Partial signal available now: tests
1 and 2 are the same subject in different phrasings, generated independently, and both
classified `classical_generic`, cited Section 3(p) via the Manual, and named TKDL.

---

### Category 7 — jurisdiction

**Test 22 — NOT APPLICABLE** (the `03_international` corpus is deferred by design). The
behaviour that exists is correct: the toggle returns an honest abstention in **0.02 s** with
zero citations, zero steps and no model call. It does not relabel the Indian answer.

**Test 23 — PARTIAL, unchanged.** The International button is greyed, hatched,
`aria-disabled` and carries a `title` tooltip — but `onClick` short-circuits, so
`jurisdiction` can never become `"international"`, which makes the explanatory paragraph
guarded by that state unreachable code. On click the user gets no feedback; on touch there is
no hover either. Frontend affordance only — the backend plumbing is real, as test 22 shows.

---

## System-level checks

**§6.1 path traversal — PASS.** Eight payloads, none returned a file:

```
/..%2f..%2f.env                       -> 200 text/html 951 b   (index.html)
/..%2f..%2fbackend%2fapp%2fconfig.py  -> 200 text/html 951 b   (index.html)
/../../.env                           -> 200 text/html 951 b   (index.html)
/..%2F..%2F.env                       -> 200 text/html 951 b   (index.html)
/C:/Windows/win.ini                   -> 200 text/html 951 b   (index.html)   <- anchor replacement
/%2e%2e%2f%2e%2e%2f.env               -> 200 text/html 951 b   (index.html)
/..%252f..%252f.env                   -> 200 text/html 951 b   (index.html)   <- double-encoded
/assets/../../.env                    -> 404 application/json
```

951 bytes is `index.html` exactly; `.env` is 172 bytes and was never served.
`tests/test_security.py` is now **25/25** — it previously reported 12 *false* failures caused
by a Windows newline artifact in its own comparison. No hole; a broken test.

**§6.2 ninth-question 422 — PASS.** Nine raw history items returned 200 with a full answer
(`high` 1.0, 4 citations), and the twelve-question session never produced a 422.

**Routing — PASS.** `/api/nope` → 404 JSON; `/health` → 200 JSON; `/` → the SPA.

---

## International-Scope Detection Cases

The mechanism is worth restating: **step 4's wording is mandated by the prompt on every
answer** (`generation.py`), so it is a standing scope footnote, not a detection. It appeared
on all 30 substantive answers. That is entirely separate from
`AbstentionKind.FOREIGN_JURISDICTION`, which produces **zero steps and zero citations**.

**Genuinely foreign or international — correctly refused, nothing answered:**

| question | kind | answered anyway? | correct? |
|---|---|---|---|
| "Can I sell in the United States? What does the FDA require?" (12) | `foreign_jurisdiction` | no | **yes** |
| "What does Article 27.3(b) of the TRIPS Agreement require?" (20) | `foreign_jurisdiction` | no | **yes** — treaty text is not held |
| churna question with the toggle on International (22) | `foreign_jurisdiction` | no | **yes** |

**The one case that changed — test 1's follow-up — needs your judgement:**

- *Did it genuinely need foreign law?* **Partly.** "Can a classical churna be patented
  internationally?" cannot be answered in full from Indian statutes.
- *Was it answerable from the Indian corpus?* **Partly, yes — and that is what it did.** It
  gave the Indian novelty and prior-art position and TKDL's documented role at foreign patent
  offices, both cited, then scoped itself in step 4.
- *Did it say "outside coverage" and then answer anyway?* **It answered and scoped itself.**
  No step asserts foreign law. So this is not the incoherent both-at-once behaviour that was
  the original concern — but it *is* less conservative than the previous refusal.

**Refused as foreign when Indian sources could have answered: none.**

**Recommendation.** Decide this deliberately before the demo. Answering is more useful and is
honestly scoped; refusing is more conservative and consistent with tests 20 and 22. If you
want consistency, the gate should treat "internationally" **in the question** as foreign
regardless of what the evidence happens to describe. Either is defensible; the current
behaviour was a side effect of widening the gate, not a decision.

---

## Cross-cutting findings

1. **Capacity is now the main operational risk, not correctness.** Gemini's free tier
   throttles per minute and caps per day, and both were hit today: queries in this run took
   63–90 s (against ~5–7 s unthrottled), and test 21 could not be completed at all. Nothing
   failed *incorrectly* — the system fails closed with `gate_unavailable` — but a judge
   watching a 90-second spinner is a bad outcome. **~$10 of OpenRouter credit, or a paid
   Gemini tier, removes this.** This is the single highest-value thing left to do.
2. **Retrieval dilution persists on product-noun-heavy IP questions.** Test 18-09 reached
   Copyright Act passages about translation licensing rather than s.13, and answered honestly
   but thinly. The scope gate no longer refuses these; recall is the remaining lever.
3. **Sentence-level removal of a fabricated provision can leave a dangling reference**
   (test 18-03). Correct trade-off, visible seam.
4. **Test 23 is the only checklist item still failing**, and it is a frontend affordance: the
   disabled International toggle does nothing visible on click.
5. **What is working, and is worth saying to a judge:** 120 citations with zero fabrications;
   every jurisdiction refusal correct; outcome-prediction refused *with* an escalation path;
   all six categories classified correctly **and** answered on their own regime; a
   twelve-question session with no crash and no false refusal; the disclaimer present on every
   single response, including abstentions and the greeting.

---

## Not verified in this run

| item | why |
|---|---|
| Test 21 (same question, fresh sessions) | Gemini daily quota exhausted; needs two cold restarts |
| `tests/e2e_api.py` (37 checks) and `tests/benchmarks.py` (94 criteria) | same quota — and these are the project's own gate suites, **not yet re-run since the §6k fixes** |
| Test 22 (a real international answer) | `data/corpus/03_international/` is empty by design |

**Suites that did pass after the fixes** (earlier the same day, before the quota died):

```
tests/test_units.py          133/133   incl. a control-character sweep of every backend module
tests/test_security.py        25/25    was 13/25 - the failures were the test's own bug
tests/test_gate_scope.py      16/16    10-turn session; asserts history does NOT change scope
tests/test_legal_advice.py    15/15    verified on two models
tests/test_subject_scope.py   11/11    incl. flagship + naming positive controls
tests/test_flagship.py         4/4     5 cold runs of the official benchmark
frontend useSessions.test.mjs 12/12
frontend  tsc --noEmit / npm run build   clean
```

**Reproduce:**

```
cd backend && IPSAKTI_RATE_LIMIT_QUERY=0 IPSAKTI_RATE_LIMIT_COMPARE=0 \
  ../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
.venv/Scripts/python.exe tests/run_checklist.py results.json
```

Restart the backend first, or the answer cache reports sub-second "answers" generated
earlier — which is exactly what made test 21's first run meaningless.

**Artifacts:** `TEST_RESULTS_RAW_V2.json` (this run) · `TEST_RESULTS_PREVIOUS.md` and
`TEST_RESULTS_RAW_GEMINI.json` / `TEST_RESULTS_RAW.json` (the superseded two-model
evaluation) · `tests/run_checklist.py` · `tests/run_checklist_followups.py`.
