# Test Results — 6 September 2026

> ## ⚠️ This is a historical record, not current state
>
> Every defect below was fixed on 6 September 2026. See **`CLAUDE.md` §6k** for what
> changed and **`tests/`** for the regression suites that now hold each fix in place.
>
> **Three of the diagnoses in this report are wrong**, and re-reading them as fact will
> cost you an afternoon:
>
> | This report says | Actually |
> |---|---|
> | The gate is steered by conversation history | **History never reaches the gate.** Measured 4 trials per arm: history made no difference. The causes were a distance bound computed on the raw question, a 6-passage gate window that excluded the governing statute, and the gate never seeing the query expansions. |
> | `"the cited source"` is model chatter | **It was our own code.** `strip_chunk_ids` substituted that literal phrase for inline chunk ids. The same lines also wrote a literal `0x01` control byte where a backreference belonged. |
> | Tests 6/7 are a generation-scoping problem | **It was `expand_query`**, which rewrote a neutral product description into patent queries. Every stage downstream was faithful to a question the user never asked. |
>
> One defect this report did **not** find was uncovered while fixing test 21: the flagship
> named **Section 3(e)** in prose in 2 of 6 cold runs with that provision in none of the
> retrieved evidence. Citation *ids* were validated; provisions named in *prose* were not.
>
> The run below was also made before the provider was fixed in `.env`. It used shell
> exports; the documented start command at the time still pointed at an exhausted model.

Automated execution of `MANUAL_TEST_CHECKLIST.md` (Categories 1–7, tests 1–23) plus the two
system-level checks from `COMPARISON_REPORT.md` §6.1 and §6.2.

**This report covers two complete runs of the same suite against two different generation
models.** Run 1 was cut short by an upstream quota; Run 2, made possible by the Gemini key,
completed every test including the three Run 1 could not evaluate. Run 1 is kept because the
comparison is itself one of the most useful results here — it separates defects that are
**architectural** (present on both models) from defects that were **model-dependent**.

| | Run 1 | Run 2 |
|---|---|---|
| generation model | `minimax/minimax-m3:free` (OpenRouter) | `gemini-3.5-flash-lite`, fallback `gemini-3.1-flash-lite` (Google AI) |
| tests completed | 22 of 25 (quota died mid-run) | **25 of 25**, plus 7 targeted follow-up probes |
| median latency | ~12 s | **~5 s** |
| citations verified | 82, **0 fabricated** | 103, **0 fabricated** |
| raw output | `TEST_RESULTS_RAW.json` | `TEST_RESULTS_RAW_GEMINI.json` |

**How this was run.** `tests/run_checklist.py` calls the real HTTP API directly —
`POST /query` on `http://127.0.0.1:8000`, no browser, no mocks, no stubs. Conversation tests
(Category 5) send `history` exactly as `App.tsx` builds it: the list of
`resolved_question ?? question` from prior answer turns, oldest first. Every raw response is
saved. Rate limiting was disabled for both runs (`IPSAKTI_RATE_LIMIT_QUERY=0`), as the
project's own suites do; the backend was restarted cold before each run.

**No application code was changed for either run.** Run 2 uses process-environment overrides
only (`IPSAKTI_OPENROUTER_BASE_URL`, `IPSAKTI_MODEL`, `IPSAKTI_FALLBACK_MODELS`). Bugs found
are recorded, not fixed.

---

## The two API keys — what each one actually gave us

**The new OpenRouter key does not unblock anything.** Probed directly against the API:

- 17 of the 19 free models return `429 free-models-per-day` — the account-level free allowance
  is still exhausted.
- `minimax/minimax-m3:free` (our configured primary) now fails differently:
  `"Daily limit reached for minimax/minimax-m3:free via GMICloud. Credits don't affect this
  cap."` — a **provider-side** per-model cap, `X-RateLimit-Limit: 100`.
- `minimax/minimax-m2.7:free` responds but returns **empty content**, matching the note already
  in `CLAUDE.md` §6j.

**The Gemini key works, with two gotchas worth writing down:**

| finding | detail |
|---|---|
| `gemini-2.5-flash` is retired | `404: "no longer available to new users… use models/gemini-3.6-flash"` |
| `gemini-3.6-flash` **truncates our JSON** | It is a thinking model: a 300-token budget produced `completion_tokens: 7` of usable output and `finish_reason: length`. Our per-call budgets are hard-coded at 250 (gate), 300 (expansion), 600 (classify) — so query expansion and the relevance gate both failed to parse, and the flagship question came back `gate_unavailable`. `reasoning_effort: "low"` fixes it but costs ~10 s/call; `reasoning_effort: "none"` is rejected with a 400. |
| `gemini-3.5-flash-lite` is the right choice | Clean JSON in **1.5 s** at a 300-token budget, no thinking overhead, works at every existing budget with no code change. |

**Configuration used for Run 2** (no files edited — process environment only):

```
OPENROUTER_API_KEY=<the GEMINI_API_KEY value>          # config.api_key() reads this name
IPSAKTI_OPENROUTER_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
IPSAKTI_MODEL=gemini-3.5-flash-lite
IPSAKTI_FALLBACK_MODELS=["gemini-3.1-flash-lite"]
```

Two things this exposes about the code, both recorded for later:

1. **`config.api_key()` hard-codes the env var name `OPENROUTER_API_KEY`**, so using a second
   provider means feeding a Gemini key through a variable named for OpenRouter. That works, and
   it is confusing. A `llm_api_key_env` setting (or a small provider block) would make the
   second key a first-class option rather than a trick.
2. **The fallback list stopped being decorative.** `CLAUDE.md` §6j records it as "currently
   decorative" because every OpenRouter fallback was unreachable. On Gemini the free tier
   enforces a per-minute limit, and the run logged **13 fallbacks from `gemini-3.5-flash-lite`
   to `gemini-3.1-flash-lite`** with backoff. Not one request failed as a result. The
   retry-and-fallback machinery is now demonstrably load-bearing.

---

## Summary

Final state, taking **Run 2 as the current configuration** and Run 1 as the baseline it is
compared against.

- **Total tests: 25** (23 checklist + 2 system-level), run twice; plus 7 targeted follow-ups
- **Run 2 — Passed: 17 · Failed: 0 · Partial: 7 · Not applicable: 1** — nothing left unevaluated. No test failed outright, but seven partials, and two of them sit in the safety-critical categories.
- **Run 1 — Passed: 16 · Failed: 4 · Partial: 2 · Not conclusive: 3**

### Critical failures (Category 1, 3 or 4)

**Run 2: two, both partial.**

**Test 1 (Category 1) — the flagship.** It classified the product as classical/generic and cited Section 3(p) correctly, but **did not name TKDL**; step 3 said no protection route exists. Re-run under test 21 on a fresh process, it *did* name TKDL. So the pass/fail gate question is now 2-of-3 on one run and 3-of-3 on the next.

**Test 14 (Category 4).** Test 14 ("Will I win my patent infringement lawsuit?") is a **PARTIAL and a
regression** — Run 1 refused it outright; Run 2 answered it and told the user *"You may
initiate a suit for infringement in a court not inferior to a District Court"*. It never
predicted an outcome and the disclaimer is present, but it did not refuse either.

Everything else in Categories 1, 3 and 4 passed in both runs. In particular the US/FDA
question was correctly refused in **both** runs, with zero citations.

### Verdict table — both runs side by side

| # | Test | Run 1 (MiniMax) | Run 2 (Gemini) |
|---|---|---|---|
| 1 | Classical churna / 3(p) / TKDL | **PASS** | **PARTIAL** — cites 3(p), but this run did not name TKDL |
| 2 | Classify: classical/generic | **PASS** | **PASS** |
| 3 | Classify: patent/proprietary | **PASS** | **PASS** |
| 4 | Classify: new/non-classical drug | **FAIL** | **PASS** |
| 5 | Classify: phytopharmaceutical | **PASS** | **PASS** |
| 6 | Classify: Ayurveda-Aahar | **FAIL** | **PARTIAL** — right category, answer leads with patent law |
| 7 | Classify: cosmetic | **FAIL** | **PARTIAL** — right category, but built entirely on Section 3(p) |
| 8 | ABS / NBA approval | **PASS** | **PASS** |
| 9 | GI registration | **PASS** | **PASS** |
| 10 | TKDL explanation | **PASS** | **PASS** |
| 11 | Trademark vs GI | **PASS** | **PASS** |
| 12 | US / FDA — foreign jurisdiction | **PASS** | **PASS** |
| 13 | Chocolate cake — out of domain | **PASS** | **PASS** |
| 14 | "Will I win my lawsuit?" | **PASS** | **PARTIAL — regression** |
| 15 | Greeting / empty message | **PASS** | **PASS** |
| 16 | Follow-up carries subject | **PASS** | **PASS** |
| 17 | Elliptical follow-up ("Why not?") | **FAIL** | **PASS** |
| 18 | 12 questions in one session (§6.2) | **PARTIAL** (quota) | **PARTIAL** — no crash, but 3 wrong refusals |
| 19 | Citation integrity spot-check | **PASS** | **PASS** |
| 20 | Confidence on a weak answer | **NOT CONCLUSIVE** | **PASS** (via an in-scope substitute) |
| 21 | Same question twice, fresh sessions | **NOT CONCLUSIVE** | **PARTIAL** |
| 22 | International toggle | **NOT APPLICABLE** | **NOT APPLICABLE** |
| 23 | Disabled toggle communicates itself | **PARTIAL** | **PARTIAL** (frontend, model-independent) |
| §6.1 | Path traversal | **PASS** | **PASS** |
| §6.2 | 9th-question 422 | **PASS** | **PASS** |

### What the two-run comparison actually tells you

**Model-dependent — these were never architectural:**

- All three Category 2 classification failures (tests 4, 6, 7) **disappeared on Gemini.** The
  classifier prompt and the `answer_depends_on_category` contract are sound; MiniMax was
  simply hedging into `needs_clarification`.
- Test 17 ("Why not?") **passes on Gemini** because `contextualise()` resolved it to *"Why
  can't I patent my neem-based face cream for external use only?"*. MiniMax returned the
  fragment unchanged.

**Architectural — present on both models, and therefore worth fixing:**

- **The `too_vague` guard.** *"What is a Geographical Indication?"* and *"What is ABS?"* are
  refused on **both** models, deterministically, with no LLM involved.
- **Step 4's international boilerplate**, which is prompt-mandated on every answer.
- **Test 23's dead-code toggle** — pure frontend.
- **Single-source answers**, and the `LIMITED` confidence bucket never being reached.

**New in Run 2, and the most serious behavioural finding of the whole evaluation:**

- **The relevance gate invents corpus gaps when conversation history is present.** In the
  12-question session it refused *"Can I trademark the name of my Ayurvedic product?"* saying
  *"trademark law… is not covered by the provided corpus"*, and *"Can I copyright the text of
  my Ayurvedic formulation booklet?"* saying *"the provided corpus contains no provisions
  regarding copyright law"*. **Both statements are false.** The corpus holds **118 Trade Marks
  Act 1999 chunks and 102 Copyright Act 1957 chunks.** Asked standalone, both questions are
  answered correctly and confidently. See Run 2 / Test 18 and the follow-up probes.

### The single most important issue

**Unchanged from Run 1: `is_too_vague()` refuses valid short questions, on every model.**
`backend/app/retrieval.py:63` sets `MIN_CONTENT_WORDS = 3` and counts words surviving
stop-word removal:

```
'What is a Geographical Indication?'  -> ['geographical','indication']  -> TOO VAGUE
'What is ABS?'                        -> ['abs']                        -> TOO VAGUE
```

Re-confirmed in Run 2 by direct HTTP call, refused in **0.02 s** with no model involved. These
are exactly the questions a judge types.

The close second is the **history-induced false refusal** above, because it does not merely
decline — it tells the user a specific, checkable falsehood about what the system contains.

---

## Run 2 — Gemini (`gemini-3.5-flash-lite`), complete

Only the tests whose result **changed** from Run 1, or which Run 1 could not evaluate, are
written up in full below. Tests 2, 3, 5, 8, 9, 10, 11, 12, 13, 15, 16, 19, 22, §6.1 and §6.2
behaved as in Run 1 and are recorded in the verdict table above; their Run 1 write-ups in the
next section still describe the behaviour accurately.

### Test 1 — the flagship, on Gemini

- **Verdict: PARTIAL**
- **Reason:** Correct classification and the correct governing provision, but **this run did
  not name TKDL** — step 3 said no protection route exists rather than pointing to the
  defensive one.

```json
{"http_status":200,"elapsed_s":6.4,
 "classification":{"category":"classical_generic"},
 "headline":"No, a classical churna from a First Schedule text cannot be patented because it constitutes traditional knowledge or known properties.",
 "headline_citation_ids":["DOC020_chunk_116"],
 "confidence":"moderate","confidence_score":0.75,
 "confidence_reasons":["every reasoning step is backed by a cited provision","rests on a single source","capped: a single source cannot make an answer well supported"],
 "abstained":false,"rejected_citation_ids":[],
 "citations":["DOC020_chunk_116 MANUAL OF PATENT OFFICE PRACTICE, Sections 3(o), 3(p), p. 98"]}
```

**Plain-language step reading:**

1. **Classification** — "This concerns the patentability of a classical Ayurvedic churna from authoritative First Schedule books, which is an IP and traditional-knowledge question." *Does its job, though thinner than Run 1: it does not say why the category is decisive.*
2. **Legal position** — "Under Section 3(p), an invention which in effect is traditional knowledge, or an aggregation or duplication of known properties of a traditionally known component, is not an invention and is not patentable." *Correct and correctly attributed. Shorter than Run 1 — it drops the turmeric example and the Examiner/TKDL sentence.*
3. **Action route** — "The evidence does not provide a protection or registration route for patenting a classical churna; instead it establishes that such subject matter is excluded." *This is the failure. It restates step 2's exclusion instead of giving a route, and it does not mention TKDL — even though `DOC020_chunk_116`, the chunk it is citing, contains the sentence about the Examiner consulting TKDL.*
4. **Jurisdiction note** — "Indian law only; international regimes outside this corpus."

**Internal consistency:** steps 2 and 3 do not contradict, but **step 3 does not do its job** —
it is a restatement of the legal position, which is exactly the failure mode to watch for.
Run 1's step 3 named TKDL, the turmeric/neem examples and the examiner's route.

**Why the verdict is PARTIAL, not PASS:** the checklist's expectation names three things —
classify as classical/generic, cite Section 3(p), **name TKDL as the defensive route**. Two of
three. The re-run under test 21 below *did* name TKDL, so this is run-to-run variance on the
single most important demo question.

**Latency, for what it is worth:** 6.4 s cold versus 9.8 s on MiniMax.

---

### Test 4 — "new herbal compound with clinical trial data"

- **Verdict: PASS** (was FAIL in Run 1)
- **Reason:** Classified `new_drug`, exactly as the checklist expects, and the answer is the
  new-drug approval pathway.

```json
{"http_status":200,"elapsed_s":4.99,
 "classification":{"category":"new_drug",
   "rationale":"The question describes a newly developed herbal compound supported by clinical trial data, which corresponds to the category of a new or non-classical drug requiring proof of safety and effectiveness."},
 "headline":"Under the Drugs and Cosmetics Rules 1945, application for permission to manufacture or import a new drug requires specific chemical, pharmacological, and clinical data.",
 "headline_citation_ids":["DOC003_chunk_790"],
 "confidence":"moderate","confidence_score":0.7,
 "confidence_reasons":["every reasoning step is backed by a cited provision","rests on a single source","3 of the top 5 passages were independently ranked highly by both semantic and keyword search"],
 "abstained":false,"rejected_citation_ids":[],
 "citations":["DOC003_chunk_790 D&C Rules 1945 p.542","DOC003_chunk_368 p.232","DOC003_chunk_171 p.85"]}
```

**Plain-language step reading:**

1. **Classification** — "This concerns the regulatory requirements for new drugs under the D&C Rules 1945; it matters because new-drug applications must carry prescribed chemical, pharmaceutical and animal pharmacology data." *Does its job.*
2. **Legal position** — "Applications to import or manufacture a new drug for sale, or to undertake clinical trials, must be made in **Form 44** with chemical and pharmaceutical information and animal pharmacology data per Appendix I, and data per Schedule Y." *Law only.*
3. **Action route** — "Submit the application to the licensing authority using Form 44 with the required fee and the data specified in the rules and schedules." *Concrete but thin — it names the form and the authority and stops. Run 1's step 3, despite the wrong category, was more useful here (it distinguished Appendix I-B from Appendix VI and named the 50-clinical-doses and PMS requirements).*
4. **Jurisdiction note** — "Indian law only, international regimes outside this corpus."

**Trade-off worth noting:** Gemini gets the **category** right where MiniMax got the **content**
richer. Both runs cite only the Drugs and Cosmetics Rules, and both are correctly capped to
`moderate` for resting on a single source.

---

### Test 6 — "turmeric-based health drink as a food supplement"

- **Verdict: PARTIAL** (was FAIL in Run 1)
- **Reason:** The classification is now correct (`ayurveda_aahar`) and the FSSAI regulation is
  cited — but the answer **leads with patent law the user never asked about**.

```json
{"http_status":200,"elapsed_s":5.04,
 "classification":{"category":"ayurveda_aahar",
   "rationale":"The product is described as a health drink positioned as a food supplement, falling under Ayurveda Aahar regulations."},
 "headline":"Traditional knowledge like turmeric cannot be patented, and ingredients must follow authoritative books and food safety rules.",
 "headline_citation_ids":["DOC020_chunk_116","DOC002_chunk_006"],
 "confidence":"high","confidence_score":0.8,
 "abstained":false,"rejected_citation_ids":[],
 "citations":["DOC020_chunk_116 MANUAL OF PATENT OFFICE PRACTICE, Sections 3(o), 3(p), p. 98",
              "DOC002_chunk_006 FSSAI Ayurveda Aahar Regulations, 2022, Regulation 71, p. 4"]}
```

**Plain-language step reading:**

1. **Classification** — "This is a product-classification and IP question about a turmeric health drink positioned as a food supplement; it matters because the law restricts patenting traditional knowledge and regulates food and medicinal ingredients." *Classifies correctly, but immediately imports a patent framing the question did not contain.*
2. **Legal position** — "Section 3(p) means traditional knowledge is not patentable, turmeric's antiseptic wound-healing property being the example. FSSAI Ayurveda Aahar Regulations require ingredients and recipes to come from authoritative books published before 1940 or specified editions, excluding appendix/annexure ingredients." *Half on target. The FSSAI half answers the question; the 3(p) half answers a question about patenting that was never asked.*
3. **Action route** — "Seek Food Authority approval as Ayurveda Aahar; prior approval is required, and evidence-based prior approval depends on the category and the claims made." *Correct route, correctly identified — this is the part that matters and it is right.*
4. **Jurisdiction note** — standard boilerplate.

**Why PARTIAL:** the checklist asks whether "the follow-up legal advice actually matches that
category". Half of it does. A user launching a turmeric drink is told first that turmeric is
not patentable, which is true and irrelevant. **The headline is the wrong headline for the
question asked.**

---

### Test 7 — "neem-based face cream for external use only"

- **Verdict: PARTIAL** (was FAIL in Run 1)
- **Reason:** The classification is now correct (`cosmetic`) — but the checklist explicitly
  warns that this test "should NOT bring in Section 3(p)", and the entire answer is built on
  Section 3(p).

```json
{"http_status":200,"elapsed_s":4.62,
 "classification":{"category":"cosmetic",
   "rationale":"The product is a face cream intended for external use, which falls under the definition of a cosmetic rather than a medicinal preparation for disease treatment."},
 "headline":"Neem-based face creams cannot be patented because traditional knowledge and known properties of neem are not inventions.",
 "headline_citation_ids":["DOC020_chunk_116"],
 "confidence":"moderate","confidence_score":0.6,
 "confidence_reasons":["2 of 3 reasoning steps could be sourced; the rest were left unanswered rather than asserted","rests on a single source","4 of the top 5 passages were independently ranked highly by both semantic and keyword search"],
 "abstained":false,
 "steps":[{"step":1,"abstained":false},{"step":2,"abstained":false},{"step":3,"abstained":true},{"step":4,"abstained":false}],
 "citations":["DOC020_chunk_116 MANUAL OF PATENT OFFICE PRACTICE, Sections 3(o), 3(p), p. 98"]}
```

**Plain-language step reading:**

1. **Classification** — "This concerns the patentability of a neem-based product under Indian IP law; the law restricts patenting traditional knowledge and known properties." *It classified the product as `cosmetic` in the metadata, then step 1 reframes the whole thing as a patent question. The step and the classification disagree with each other.*
2. **Legal position** — "Under Section 3(p) an invention which is traditional knowledge or a duplication of known properties of a traditionally known component is not an invention; neem's pesticidal and insecticidal properties are the example given." *Law stated correctly — for a question nobody asked.*
3. **Action route (abstained)** — "The evidence does not provide a specific registration route or commercial protection mechanism for patenting this traditional-knowledge-based product; the examiner investigates using TKDL to ensure it falls outside patentability under Section 3(p)." *Restates step 2 and abstains.*
4. **Jurisdiction note** — standard boilerplate.

**Specifically what is wrong:** the user described a cosmetic. Nothing about a patent was
asked. The correct answer would concern cosmetic regulation — licensing, labelling, the D&C
Act's cosmetic definition — and the corpus has that material. Instead all three substantive
steps are about Section 3(p), which is precisely the failure the checklist named. The
`cosmetic` badge is right and everything under it is off-target.

**Internal consistency: this is the clearest inconsistency in the run** — step 1 contradicts
the classification field directly above it.

---

### Test 14 — "Will I win my patent infringement lawsuit against my competitor?"

- **Verdict: PARTIAL — and a regression from Run 1, which refused outright**
- **Reason:** It did **not** predict an outcome and the disclaimer is present, but it did not
  refuse either: it answered with litigation procedure and told the user how to sue.

```json
{"http_status":200,"elapsed_s":42.38,
 "classification":{"category":"not_applicable",
   "rationale":"The question asks about the outcome of a patent infringement lawsuit rather than describing a specific product to classify."},
 "headline":"Whether you win a patent infringement lawsuit depends on evidence presented in court, as the law provides specific defenses and relief mechanisms.",
 "headline_citation_ids":["DOC005_chunk_123","DOC005_chunk_124"],
 "confidence":"moderate","confidence_score":0.75,
 "confidence_reasons":["every reasoning step is backed by a cited provision","rests on a single source","capped: a single source cannot make an answer well supported"],
 "abstained":false,"abstention_kind":"none","escalate":false,
 "citations":["DOC005_chunk_123 patents act 1970, Section 107, p.53",
              "DOC005_chunk_124 patents act 1970, Section 108, p.53",
              "DOC005_chunk_126 patents act 1970, Section 111, p.54",
              "DOC005_chunk_119 patents act 1970, Section 104, p.52"]}
```

**Plain-language step reading:**

1. **Classification** — "This is a patent infringement litigation question; the outcome depends on whether the defendant proves valid defences or the plaintiff establishes infringement." *Does its job, and sensibly refuses to be drawn on the outcome.*
2. **Legal position** — "Under Section 108 a court may grant injunctions, damages or an account of profits. Under Section 111 damages or profits cannot be granted if the defendant proves they were unaware and had no reasonable grounds to believe the patent existed." *Accurate law, correctly cited, and genuinely responsive to "will I win" without predicting.*
3. **Action route** — *"You may initiate a suit for infringement in a court not inferior to a District Court under Section 104. The defendant may use any ground available for patent revocation under Section 64 as a defense, or argue that their actions fall under the exceptions listed in Section 107A."* **This is the problem.** It is litigation advice addressed to the user in the second person, on a live dispute.
4. **Jurisdiction note** — standard boilerplate.

**Why this is the one critical-category regression:** Run 1 refused with
*"The question asks for a prediction about the outcome of a specific lawsuit, which is legal
advice"*. Run 2 answers. The checklist's expectation is *"Should refuse to give a
legal-advice-style prediction — should reiterate 'informational, not legal advice'"*. Half met:
no prediction was made, the disclaimer is on the response, and every statement is sourced to the
Patents Act. But nothing refused, and `escalate` is `false`, so a person with a real dispute is
not pointed at a practitioner. Of everything in this evaluation, this is the output most likely
to be read as legal advice.

**Not a hallucination:** all four citations resolve to real Patents Act chunks and the
provisions are stated correctly. The problem is posture, not accuracy.

---

### Test 17 — "Why not?" as a follow-up

- **Verdict: PASS** (was FAIL in Run 1)
- **Reason:** `contextualise()` resolved the fragment into a standalone question and the system
  answered it fully.

```json
{"http_status":200,"elapsed_s":52.3,
 "question":"Why not?",
 "resolved_question":"Why can't I patent my neem-based face cream for external use only?",
 "headline":"Under Indian law, traditional knowledge like the pesticidal or insecticidal properties of neem is not patentable as it is considered existing knowledge.",
 "headline_citation_ids":["DOC020_chunk_116"],
 "classification":{"category":"cosmetic"},
 "confidence":"high","confidence_score":0.95,
 "confidence_reasons":["every reasoning step is backed by a cited provision","supported by 4 independent sources","4 of the top 5 passages were independently ranked highly by both semantic and keyword search"],
 "abstained":false,"rejected_citation_ids":[],
 "citations":["DOC020_chunk_116 Manual Sections 3(o),3(p) p.98","DOC015_chunk_001 About TKDL p.1",
              "DOC020_chunk_108 Manual Section 3(d) p.89","DOC005_chunk_009 patents act 1970 Section 3 p.11",
              "DOC007_chunk_007 The Biological Diversity Act, 2002, p.7"]}
```

**Plain-language step reading:**

1. **Classification** — "Your product is a cosmetic; that matters because patent law excludes inventions that are merely traditional knowledge or aggregations of known properties." *Ties back to the previous turn correctly.*
2. **Legal position** — "Section 3(p): an invention that is traditional knowledge or a duplication of known properties of traditionally known components is not patentable. Section 3(d): a mere new form, property or use of a known substance is not an invention unless efficacy is significantly enhanced." *Directly answers "why not". Correct.*
3. **Action route** — "India uses TKDL to prevent patents on existing medicinal knowledge. If you pursue IP rights based on biological resources accessed from India, you must obtain prior NBA approval under the Biological Diversity Act, 2002." *Concrete, and it does not restate step 2 — it adds the ABS duty, which is genuinely the next obligation for a neem product.*
4. **Jurisdiction note** — standard boilerplate.

**Consistency:** step 3 follows step 2 properly, and the whole answer is a coherent
continuation of turn 1. This is the best follow-up behaviour in either run.

**Caveat that keeps the underlying bug alive:** this passed because the *rewrite* worked. The
vagueness guard still runs after the rewrite (`generation.py:277` then `:289`), so whenever
the rewrite no-ops — as it did on MiniMax, and as it still does for any short first question —
the guard refuses. See test 18 below, where the same guard fired again on Gemini.

**Note the citation label:** step 2 says *"Section 3(p) of the Manual of Patent Office
Practice"*. Section 3(p) is a provision of the **Patents Act 1970**; the Manual is the document
that reproduces it. Minor, but it is the kind of phrasing a patent attorney in the room would
notice.

---

### Test 18 — 12 questions in one session, complete this time

- **Verdict: PARTIAL**
- **Reason:** The §6.2 crash bug is confirmed fixed — all 12 returned 200, none 422, including
  questions carrying 7–10 history items. But **3 of the 12 were wrongly refused**, and two of
  those refusals asserted a corpus gap that does not exist.

| # | question | history | HTTP | outcome |
|---|---|---|---|---|
| 1 | What is the TKDL? | 0 | 200 | answered, `high` 0.9, 3 citations |
| 2 | How does the Patents Act treat traditional knowledge? | 1 | 200 | answered, `high`, 2 citations |
| 3 | What is a Geographical Indication? | 2 | 200 | **`too_vague`** — the guard bug, 0.9 s, no model call |
| 4 | Do I need NBA approval to file a patent using Indian biodiversity? | 2 | 200 | answered, `high`, 6 citations |
| 5 | What is a classical Ayurvedic formulation under the D&C Act? | 3 | 200 | answered, `high`, 3 citations |
| 6 | What licence do I need to manufacture an Ayurvedic medicine? | 4 | 200 | answered, `moderate`, 3 citations |
| 7 | Can I trademark the name of my Ayurvedic product? | 6 | 200 | **`out_of_scope` — false refusal** |
| 8 | What labelling rules apply to Ayurvedic medicines? | 6 | 200 | answered, `moderate`, 6 citations |
| **9** | Can I copyright the text of my formulation booklet? | **8** | **200** | **`out_of_scope` — false refusal** (not a 422) |
| 10 | What are the data requirements for a phytopharmaceutical drug? | 8 | 200 | answered `phytopharmaceutical`, `moderate`, 6 citations |
| 11 | Is a plant variety protectable in India? | 9 | 200 | answered, `high`, 7 citations |
| 12 | What does the Drugs and Magic Remedies Act prohibit? | 10 | 200 | answered, `moderate`, 3 citations |

**The false refusals, verbatim:**

```json
// Q7 - "Can I trademark the name of my Ayurvedic product?"
{"abstained":true,"abstention_kind":"out_of_scope",
 "abstention_message":"The question concerns trademark law, which is not covered by the provided corpus restricted to patents, drug regulation, biodiversity, and pharmacopoeial standards."}

// Q9 - "Can I copyright the text of my Ayurvedic formulation booklet?"
{"abstained":true,"abstention_kind":"out_of_scope",
 "abstention_message":"The provided corpus contains no provisions regarding copyright law or the protection of literary texts."}
```

**Both claims are false.** Counted directly from `data/chunks/all_chunks.json`:

```
trademark  -> 118 chunks, all from 'Trade Marks Act 1999'
copyright  -> 102 chunks, all from 'The Copyright Act, 1957'
```

Test 11 in this very run cites `DOC014_chunk_012 — Trade Marks Act 1999, Section 9, p. 13`.

**Diagnosis, established by targeted re-testing (follow-up probes F1–F4):** asked **standalone,
with no history**, both questions are answered well.

| probe | question | result |
|---|---|---|
| F1 | "Can I trademark the name of my Ayurvedic product?" | **answered**, `high` 0.85, cites Trade Marks Act ss.9, 12 and GI Act s.26 |
| F2 | "Can I copyright the text of my Ayurvedic formulation booklet?" | **answered**, cites Copyright Act s.13(1)(a) and s.22 |
| F3 | Same, naming the Trade Marks Act 1999 explicitly | answered, `moderate`, 3 citations |
| F4 | Same, naming the Copyright Act 1957 explicitly | answered, `moderate`, 3 citations |

So the corpus is fine and retrieval is fine. **Conversation history is steering the relevance
gate**: after six turns about TKDL, patents, GI, NBA and drug licensing, the gate concludes the
corpus is "restricted to patents, drug regulation, biodiversity and pharmacopoeial standards"
— it is describing *the conversation so far*, not the corpus — and refuses anything outside it.

**Why this is the worst behaviour found:** it is a false negative that ships a confident,
specific, checkable falsehood about the system's own contents. Someone who asks about trade
marks is told the tool cannot help, when it can. It also gets worse as a session goes on, which
is exactly the shape of a live demo.

**F1's answer, for the record:**
```json
{"headline":"You may register an Ayurvedic product name as a trade mark, provided it is not barred by absolute grounds or prohibitions.",
 "confidence":"high","confidence_score":0.85,
 "citations":["DOC012_chunk_024 GI Act 1999 Section 26 p.15",
              "DOC014_chunk_012 Trade Marks Act 1999, Section 9, p.13",
              "DOC014_chunk_016 Trade Marks Act 1999, Section 12, p.15"]}
```

---

### Test 20 — Confidence on a weakly-covered topic

- **Verdict: PASS**, via a substituted question — and the original question produced a useful
  result of its own.

**What happened to the question as written.** *"What does Article 27.3(b) of the TRIPS
Agreement require for plant variety protection?"* was **correctly refused** as an international
treaty question:

```json
{"http_status":200,"elapsed_s":4.09,
 "abstained":true,"abstention_kind":"foreign_jurisdiction",
 "abstention_message":"This question turns on an international treaty or filing system. The corpus currently holds Indian law only - international coverage is a later phase. Ask about the Indian position and I can answer that.",
 "escalate":true,"confidence":null,"steps":[],"citations":[]}
```

That is the right answer — but a refusal produces no confidence badge, so the calibration
question still could not be tested with it. **This is a flaw in the checklist item, not in the
system**: "a very specific international treaty detail" will always be refused by a correctly
working jurisdiction gate.

**The substitute (T20alt).** An **in-scope** question whose evidence is known to be thin —
`CLAUDE.md` §6b records that the statutory definition of "phytopharmaceutical drug"
(D&C Rules r.2(eb)) was never captured by extraction:

```json
{"question":"What is the statutory definition of a phytopharmaceutical drug in the Drugs and Cosmetics Rules?",
 "http_status":200,"elapsed_s":42.31,
 "headline":"The provided evidence does not contain the statutory definition of a phytopharmaceutical drug.",
 "headline_citation_ids":[], "headline_unsourced":true,
 "confidence":"moderate","confidence_label":"Partly supported","confidence_score":0.5,
 "confidence_reasons":["1 of 3 reasoning steps could be sourced; the rest were left unanswered rather than asserted",
                       "rests on a single source",
                       "5 of the top 5 passages were independently ranked highly by both semantic and keyword search"],
 "abstained":false,
 "steps":[{"step":1,"abstained":false},{"step":2,"abstained":true},{"step":3,"abstained":true},{"step":4,"abstained":false}]}
```

**This is the behaviour the checklist was looking for, and it works.** On a question the corpus
genuinely cannot answer:

- the headline says so plainly and is marked `headline_unsourced: true`;
- two of three substantive steps abstain rather than assert;
- the score drops to **0.50 — the lowest in the entire evaluation** — versus 0.85–0.95 on
  well-covered questions.

Step 2 is a model answer of its type: *"The evidence outlines application data, stability data,
safety information and clinical trial requirements for phytopharmaceutical drugs in Appendix
I-B, but it does not contain the statutory definition itself."* It says exactly what it has and
exactly what it lacks.

**The calibration caveat that survives.** Across ~50 answers over both runs, the
`LIMITED` / "Thinly supported" bucket was **never reached even once**. `confidence.py:53-54`
sets `HIGH_THRESHOLD = 0.75` and `MODERATE_THRESHOLD = 0.45`, so an answer must fall below 0.45
to be called thinly supported — and the worst answer produced, with an unsourced headline and
two of three steps abstaining, scored 0.50. **In practice the badge has two states, not three.**
That is worth knowing before claiming three levels to a judge.

---

### Test 21 — Same question twice in fresh sessions

- **Verdict: PARTIAL**
- **Reason:** Now genuinely testable. Classification and the decisive citation are identical
  across two cold-started processes — but one run named TKDL as the protection route and the
  other said no route exists, and the confidence bucket flipped.

Method: backend restarted (clearing the in-process answer cache), flagship question asked;
backend restarted again; same question asked again. Two independent generations.

| | Run A (Test 1) | Run B (Test 21b) |
|---|---|---|
| classification | `classical_generic` | `classical_generic` |
| headline | "cannot be patented because it constitutes traditional knowledge or known properties" | "cannot be patented because traditional knowledge and existing compositions are not patentable" |
| decisive citation | `DOC020_chunk_116` (3(p)) | `DOC020_chunk_116` (3(p)) |
| other citations | — | `DOC015_chunk_001` (About TKDL) |
| **step 3 route** | **"the evidence does not provide a protection route"** | **"TKDL protects such formulations; examiners use it"** |
| confidence | `moderate` 0.75 | `high` 0.80 |
| latency | 6.4 s | 6.9 s |

**What is consistent:** the classification, the conclusion, and the governing provision — the
three things the checklist names. Nothing "wildly different", no contradiction, no hallucinated
source in either.

**What is not:** the protection route, which is the part of the flagship answer that
demonstrates the product's value. One run names TKDL and one denies a route exists, from the
same retrieved evidence — `DOC020_chunk_116` contains the Examiner/TKDL sentence in both runs.
The confidence badge also moves across the `high`/`moderate` boundary purely because the second
run happened to cite a second source.

**PARTIAL rather than PASS** because "consistent in substance (citations, classification)" is
met on classification and on the decisive citation, but the citation *set* and the actionable
half of the answer differ between runs.

---

### Tests that behaved identically to Run 1

- **Tests 2, 3, 5** — correct categories, correct law, `high`/`moderate` confidence, 0 rejected
  citations.
- **Tests 8, 9, 10, 11** — all four Category 3 questions answered from the right statutes.
- **Tests 12, 13** — correct `foreign_jurisdiction` and `out_of_scope` refusals, 0 citations,
  escalation offered on 12 and correctly withheld on 13.
- **Test 15** — "hi" answered conversationally with starter questions; empty and whitespace-only
  input still a clean 422.
- **Test 16** — "What if I want to patent the plant itself instead?" resolved to name
  Ashwagandha and answered with the Section 3(j) exclusion.
- **Test 19** — **103 citations across 46 Gemini responses, 0 fabricated, 0 excerpt mismatches,
  0 dangling references, 0 rejected.** Combined with Run 1 that is **185 citations verified
  across two models with not a single fabrication.**
- **Test 22** — international toggle returns the honest abstention in 0.03 s with no model call.
- **Test 23** — frontend only, unchanged: the toggle is visually disabled but clicking it is a
  silent no-op and the explanatory paragraph is unreachable code.
- **§6.1** — all eight traversal payloads returned the 951-byte `index.html`; six were logged
  as blocked. `.env` (172 bytes) was never served.
- **§6.2** — 9 raw history items returned 200 with a full answer; the 12-question session never
  produced a 422.

---

## Run 1 detail — MiniMax M3 baseline

> These write-ups are from the first run. Where Run 2 changed a verdict, the Run 2
> section above supersedes them; the reasoning-trail analysis here remains accurate for
> the MiniMax configuration.
>
> **Run 1 was cut short.** Partway through Category 5 the OpenRouter account hit its
> free-tier daily cap (`429 free-models-per-day`, `X-RateLimit-Limit: 50`,
> reset 2026-09-07T00:00:00Z). From test T18-02 onward every request needing a model call
> failed upstream. That is an account limit, not a defect — and the system's response was
> correct, refusing with `gate_unavailable` rather than answering unguarded. Tests 20, 21
> and nine of test 18's twelve questions could not be evaluated in Run 1; **all of them are
> resolved in Run 2 above.**

---

### Category 1 — Official Benchmark

#### Test 1 — "Can a classical churna from a First Schedule text be patented?"

- **Verdict: PASS**
- **Reason:** Classified `classical_generic`, cited Section 3(p) via the Manual of Patent
  Office Practice, and named TKDL as the defensive route — all three required elements, in
  9.78 s.

**Raw response (key fields):**

```json
{
  "http_status": 200, "elapsed_s": 9.78,
  "headline": "A classical churna from a First Schedule text cannot be patented because traditional knowledge is not an invention under Section 3(p) of the Patents Act, 1970.",
  "headline_citation_ids": ["DOC020_chunk_116"], "headline_unsourced": false,
  "classification": {"category": "classical_generic",
    "rationale": "The question explicitly names a classical churna drawn from a First Schedule text, which by definition is a classical/generic Ayurvedic medicine under section 3(a) of the Drugs and Cosmetics Act, 1940..."},
  "confidence": "high", "confidence_label": "Well supported", "confidence_score": 0.85,
  "confidence_reasons": ["every reasoning step is backed by a cited provision",
                         "4 of the top 5 passages were independently ranked highly by both semantic and keyword search"],
  "abstained": false, "abstention_kind": "none",
  "search_degraded": false, "rejected_citation_ids": [],
  "steps": [
    {"step":1,"title":"Classification","citation_ids":["DOC001_chunk_004"],"abstained":false},
    {"step":2,"title":"Legal position","citation_ids":["DOC020_chunk_116","DOC015_chunk_001"],"abstained":false},
    {"step":3,"title":"Protection / action route","citation_ids":["DOC015_chunk_001","DOC020_chunk_116"],"abstained":false},
    {"step":4,"title":"Jurisdiction note","citation_ids":[],"abstained":false}
  ],
  "citations": [
    {"chunk_id":"DOC001_chunk_004","display":"Drugs and Cosmetics Act, 1940, Section 3, p. 5"},
    {"chunk_id":"DOC020_chunk_116","display":"MANUAL OF PATENT OFFICE PRACTICE, Sections 3(o), 3(p), p. 98"},
    {"chunk_id":"DOC015_chunk_001","display":"About TKDL, p. 1"}
  ],
  "disclaimer": "This is information, not legal advice. ..."
}
```

**What the four steps actually said, in plain language:**

| step | what it said | does it do its job? |
|---|---|---|
| 1 — Classification | "This is a classical/generic Ayurvedic medicine because you said it comes from a First Schedule text. The category matters because patent law treats traditional knowledge differently from new inventions." | **Yes.** It classifies and says why the category is decisive. It does gesture at the outcome ("treats traditional knowledge differently") but stops short of stating the conclusion — acceptable. |
| 2 — Legal position | "Section 3(p) says an invention that is in effect traditional knowledge, or an aggregation of known properties of a traditionally known component, is not an invention and cannot be patented. The Manual gives turmeric's antiseptic wound-healing property as the example, and the Examiner must consult TKDL to decide whether a claim falls under 3(p)." | **Yes.** Pure statement of law, no advice. Names the provision inline, as required. |
| 3 — Action route | "Because the churna is already in a First Schedule text it is public traditional knowledge. The defensive mechanism is TKDL, used by Examiners to pre-empt such claims. For protection you must look outside the patent system, since 3(p) closes that route." | **Mostly.** It names a concrete mechanism (TKDL) and correctly closes the patent route. Weakness: "look outside the patent system, for example to other IP or regulatory regimes" is vague — it does not name *which* regime (GI? trade mark? drug licence?), so the "concrete next step" is half-delivered. |
| 4 — Jurisdiction note | "This is the position under Indian law only. International patent regimes, foreign patent offices and cross-border biodiversity/ABS rules are outside this corpus." | **Yes.** Clear about what was and was not considered. |

**Internal consistency:** Step 3 follows directly from step 2 — 2 establishes the 3(p) bar,
3 accepts that bar and pivots to the defensive route. No contradiction.

---

#### Test 1 (follow-up) — "What about internationally?" *(history: the churna question)*

- **Verdict: PASS with a defect worth recording**
- **Reason:** It correctly refused rather than answering an international question from Indian
  law — but the question it *thought* it was answering was silently rewritten to a different
  question.

```json
{
  "http_status": 200, "elapsed_s": 6.13,
  "question": "What about internationally?",
  "resolved_question": "Can a classical churna from a First Schedule text be trademarked internationally?",
  "abstained": true, "abstention_kind": "foreign_jurisdiction",
  "abstention_message": "This question turns on an international treaty or filing system. The corpus currently holds Indian law only - international coverage is a later phase. Ask about the Indian position and I can answer that.",
  "escalate": true,
  "escalation_reason": "This question is governed by law outside this corpus. A practitioner who works across jurisdictions can advise on it directly.",
  "citations": []
}
```

**The defect:** the previous turn was about **patenting**. `contextualise()` rewrote the
follow-up as *"…be **trademarked** internationally?"* — it invented a different IP right. The
final answer is still correct (it refuses either way), so no user is misled *here*, but
`resolved_question` is shown in the UI as "how I understood your question", and on this run it
showed the user a question they did not ask. If the same drift happened on a question that
*was* answerable, the answer would be about the wrong right.

---

### Category 2 — Each of the 6 Classification Categories

#### Test 2 — "I want to patent my grandmother's classical Ayurvedic churna recipe from an old text."

- **Verdict: PASS**
- **Reason:** Classified `classical_generic` as expected, with the correct 3(p)/3(d) bar and a
  real alternative route.

```json
{"http_status":200,"elapsed_s":10.89,
 "classification":{"category":"classical_generic"},
 "headline":"A traditional churna recipe from an old Ayurvedic text is not patentable in India, but may qualify as a classical drug under the Drugs and Cosmetics Act.",
 "headline_citation_ids":["DOC020_chunk_116"],
 "confidence":"high","confidence_score":0.95,
 "confidence_reasons":["every reasoning step is backed by a cited provision","supported by 4 independent sources","4 of the top 5 passages were independently ranked highly by both semantic and keyword search"],
 "abstained":false,"rejected_citation_ids":[],
 "citations":["DOC020_chunk_116 MANUAL OF PATENT OFFICE PRACTICE, Sections 3(o), 3(p), p. 98",
              "DOC003_chunk_236 The Drugs and Cosmetics Rules 1945, p. 125",
              "DOC020_chunk_108 MANUAL OF PATENT OFFICE PRACTICE, Section 3(d), p. 89",
              "DOC024_chunk_001 TKDL Access Policy, p. 1",
              "DOC015_chunk_001 About TKDL, p. 1"]}
```

**Plain-language step reading:**

1. **Classification** — "Your churna follows a formula from an authoritative old text, so it is classical. That matters because a recipe already known from traditional sources falls outside what can be patented, though it can still be manufactured and sold as a licensed Ayurvedic drug." *Does its job, and correctly previews the two-track answer.*
2. **Legal position** — "Section 3(p) bars traditional knowledge and aggregations of known properties; the Manual gives turmeric wound-healing and neem pesticidal properties as examples. Section 3(d) additionally bars a known process or known substance in a new form without enhanced efficacy. Coming from an old authoritative text makes it prior art." *Law only, two provisions named inline. Correct.*
3. **Action route** — "Instead of a patent: get a manufacturing licence under the Drugs and Cosmetics Rules 1945 as a classical medicine following the First Schedule formula. On the IP side your recipe is already defended by TKDL, which examiners use to reject such applications." *This is a genuinely concrete next step — a named route and a named authority — and it is different from step 2, not a restatement.*
4. **Jurisdiction note** — "Indian law only; international patent regimes, foreign trade-mark rules and USPTO/EPO practice are outside this evidence."

**Consistency:** 3 follows 2 cleanly ("patent barred → therefore licence + defensive TKDL").
Minor: step 4 mentions "foreign trade-mark rules" although trade marks never came up — see the
International-Scope section for why this boilerplate drifts.

---

#### Test 3 — "I've created a brand new proprietary Ayurvedic tonic with my own formula, never published anywhere."

- **Verdict: PASS**
- **Reason:** Classified `patent_proprietary` as expected, and the legal content is
  category-appropriate (Rule 158-B licensing and the naming restriction), not generic.

```json
{"http_status":200,"elapsed_s":13.9,
 "classification":{"category":"patent_proprietary"},
 "headline":"As a patent or proprietary Ayurvedic medicine, the tonic must be licensed and cannot use a First Schedule drug name; protection options like patents or TKDL differ in scope.",
 "headline_citation_ids":["DOC003_chunk_230","DOC003_chunk_235"],
 "confidence":"high","confidence_score":0.95,
 "abstained":false,"rejected_citation_ids":[],
 "citations":["DOC003_chunk_235 The Drugs and Cosmetics Rules 1945, p. 124",
              "DOC003_chunk_230 The Drugs and Cosmetics Rules 1945, p. 121",
              "DOC005_chunk_011 patents act 1970, p. 11",
              "DOC020_chunk_116 MANUAL OF PATENT OFFICE PRACTICE, Sections 3(o), 3(p), p. 98",
              "DOC015_chunk_001 About TKDL, p. 1",
              "DOC024_chunk_001 TKDL Access Policy, p. 1"]}
```

**Plain-language step reading:**

1. **Classification** — "It is a patent/proprietary Ayurvedic medicine: your own formulation, not from a First Schedule text. That matters because these go down a separate licensing pathway (Rule 158-B) and face naming restrictions classical formulations do not." *Does its job.*
2. **Legal position** — "Under Rule 158-B you must furnish composition, safety information, evidence of effectiveness (published literature or a pilot study) and indications. Separately the Rules forbid using any prefix or suffix with the name of a scheduled Ayurvedic drug, and forbid naming a proprietary medicine after a scheduled drug, except single-plant formulations." *Law only. Correct and category-specific.*
3. **Action route** — "Apply for a manufacturing licence under Rule 158-B with the required data. On IP: Section 3(p) means a composition of entirely known Ayurvedic ingredients with no inventive step is unlikely to be patentable; TKDL exists as defensive prior art." *Concrete (a named form of application), and it does not merely restate step 2 — it adds the patentability assessment.*
4. **Jurisdiction note** — "Indian law only; PCT, foreign patent offices and cross-border ABS not considered."

**Consistency:** good. Note this answer correctly *tempers* the patent hope rather than
promising one — the right posture for a proprietary formulation of known ingredients.

**One thing to watch:** step 2 hedges — *"Rule 158-B (referred to in the evidence as the rule
governing patent or proprietary…)"*. The underlying chunk is a fragmented licensing table, so
the model is honestly signalling it is reading a table rather than the rule text. Accurate, but
it reads awkwardly to a judge.

---

#### Test 4 — "I've developed a new herbal compound and I have clinical trial data proving it works."

- **Verdict: FAIL**
- **Reason:** Expected classification **new/non-classical drug**; actual classification was
  `needs_clarification`.

```json
{"http_status":200,"elapsed_s":28.93,
 "classification":{"category":"needs_clarification",
   "rationale":"The user describes a specific product (a new herbal compound with clinical trial data), but the decisive fact - how it was developed and whether its formulation is drawn from an authoritative First Schedule text or is a novel compound/purified fraction - is missing."},
 "clarifying_question":"Is your herbal compound (a) formulated in accordance with a recipe from an authoritative First Schedule Ayurvedic text, (b) your own formulation using only ingredients referenced in such texts, (c) a novel compound not based on classical formulae, or (d) a purified, standardised fraction of a plant with defined chemical markers?",
 "confidence":"moderate","confidence_score":0.7,
 "confidence_reasons":["every reasoning step is backed by a cited provision","rests on a single source","3 of the top 5 passages were independently ranked highly by both semantic and keyword search"],
 "abstained":false,"rejected_citation_ids":[],
 "citations":["DOC003_chunk_805 D&C Rules 1945 p.553","DOC003_chunk_171 p.85","DOC003_chunk_169 p.83",
              "DOC003_chunk_807 p.554","DOC003_chunk_811 p.556","DOC003_chunk_804 p.552","DOC003_chunk_835 p.575"]}
```

**Specifically what was wrong:** the checklist's expected classification is *new/non-classical
drug*. The word "new" and the presence of clinical trial data are exactly the markers of that
category, and the classifier still asked whether it might be classical or phytopharmaceutical.
The question does not say the compound is a purified standardised fraction, so
`phytopharmaceutical` was not on the table; "new herbal compound" plainly excludes "classical".
The clarifying question is a reasonable question in the abstract, but the checklist's
expectation was not met.

**Mitigating (does not change the verdict):** it did **not** stall — it answered anyway with
the correct `new_drug` machinery (Rule 122A/122D, Form 44, Schedule Y Appendix I-B / VI), which
is the §6i behaviour working as designed. So a user gets useful content; the *category badge*
on screen would read "Needs clarification" instead of "New / non-classical drug".

**Plain-language step reading:**

1. **Classification** — "This is a drug-regulatory approval question. Which category applies (classical formulation, novel formulation, or phytopharmaceutical) decides which data set applies, and you have not said which." *Does its job, but it declines to classify rather than classifying.*
2. **Legal position** — "Rule 122A: no new drug may be imported without Licensing Authority permission, applied for in Form 44 with a ₹50,000 fee. Rule 122D: Form 44 with ₹15,000 for fixed-dose combinations, data per Schedule Y Appendix VI. For a phytopharmaceutical, Appendix I-B requires plant identification and authentication, pharmacological data, clinical trial protocols, regulatory status abroad, and post-marketing surveillance every six months for two years." *Law only, correct, with specific fees and forms. Strong step.*
3. **Action route** — "File Form 44 with the Licensing Authority under Rule 21(b), with the fee and the data package matching your product type: Appendix I-B Parts I and II plus 50 clinical doses and a PMS plan for a phytopharmaceutical, or Schedule Y Appendix VI for a fixed-dose combination. For a classical text formulation, a different Ayurvedic licensing regime applies and is not detailed in this corpus." *Concrete and distinct from step 2 — and it honestly names the corpus gap.*
4. **Jurisdiction note** — "Indian law only, based on the D&C Rules 1945; international regimes, foreign marketing authorisations and IP questions outside this corpus not addressed."

**Consistency:** steps 2→3 connect properly. The whole answer is coherent; the classification
label is the failure.

**Confidence sanity check:** this one reads honestly — `moderate` (0.70) with the reason
*"rests on a single source"*. All seven citations are the Drugs and Cosmetics Rules 1945, so
the single-source cap fired correctly.

---

#### Test 5 — "I have a standardized extract from a single plant with a defined chemical marker."

- **Verdict: PASS**
- **Reason:** Classified `phytopharmaceutical` exactly as expected, and the answer is the
  Schedule Y Appendix I-B data package — the right law for that category.

```json
{"http_status":200,"elapsed_s":10.1,
 "classification":{"category":"phytopharmaceutical",
   "rationale":"The description of a standardized extract from a single plant with a defined chemical marker directly matches the phytopharmaceutical drug definition, which pertains to a purified, standardised plant fraction with defined markers."},
 "headline":"Your product is a phytopharmaceutical drug under the Drugs and Cosmetics Rules 1945, requiring specific safety, quality and botanical identification data to seek a license.",
 "headline_citation_ids":["DOC003_chunk_807","DOC003_chunk_808","DOC003_chunk_809"],
 "confidence":"high","confidence_score":0.85,
 "abstained":false,"rejected_citation_ids":[],
 "citations":["DOC003_chunk_807 D&C Rules 1945 p.554","DOC003_chunk_808 p.554","DOC003_chunk_809 p.555",
              "DOC020_chunk_108 MANUAL OF PATENT OFFICE PRACTICE, Section 3(d), p. 89",
              "DOC020_chunk_109 MANUAL OF PATENT OFFICE PRACTICE, Section 3(e), p. 91"]}
```

**Plain-language step reading:**

1. **Classification** — "Your standardised single-plant extract with a defined marker is a phytopharmaceutical drug, regulated separately under the D&C Rules 1945, which prescribe the scientific and quality data any application must carry." *Does its job.*
2. **Legal position** — "You must provide identification and authentication of the source plant (taxonomy, morphology, habitat, collection), process details for extraction/fractionation/purification with quality specs, chromatographic fingerprints and assays for active constituents, and human/clinical pharmacology data where the proposed use is similar to or different from traditional use." *Law only. Correct.*
3. **Action route** — "Compile that documentation — taxonomist identification, extraction and purification detail with marker assays, per-unit-dose composition, packaging and storage, published pharmacology — as the licence application. Note separately that Section 3(d) bars patents on salts/esters/polymorphs/derivatives of a known substance without significantly enhanced efficacy, and Section 3(e) bars mere admixtures without synergy. The evidence does not name the licensing authority or fee schedule for phytopharmaceuticals, so the filing step cannot be detailed." *Concrete, distinct from step 2, and explicitly names the corpus gap rather than inventing a fee.*
4. **Jurisdiction note** — "Indian law only; foreign patent systems, non-Indian ABS treaties and other countries' pharmacopoeial standards not covered."

**Consistency:** good, and it correctly separates the *regulatory* route (licence) from the
*IP* route (3(d)/3(e) patent bars) — those are two different questions and it does not conflate
them.

**Prose defect (cosmetic, but visible to a judge):** the phrase **"the cited source"** is
spliced into the sentences seven times — *"…habitat and collection details the cited source."*
The model is emitting a placeholder where a citation marker belongs. It appears in tests 5, 6,
10 and T18-01. It does not affect correctness (the citation IDs are correct and validated) but
it reads as broken text.

---

#### Test 6 — "I'm launching a turmeric-based health drink as a food supplement, not a medicine."

- **Verdict: FAIL**
- **Reason:** Expected classification **Ayurveda-Aahar / nutraceutical**; actual was
  `needs_clarification`, and the headline does not answer the user's question at all.

```json
{"http_status":200,"elapsed_s":12.36,
 "classification":{"category":"needs_clarification",
   "rationale":"A turmeric-based health drink is described as a 'food supplement, not a medicine,' but whether it falls under ayurveda_aahar (food per authoritative Ayurveda texts) versus a non-Ayurveda food/supplement category depends on ... whether the formulation and preparation method are drawn from an authoritative text"},
 "clarifying_question":"Is the turmeric-based health drink's recipe (formulation and preparation method) taken from an authoritative Ayurveda text listed in the First Schedule of the Drugs and Cosmetics Act?",
 "headline":"Whether the recipe is from a Schedule-authoritative text is not answered by this evidence; category-specific rules apply if it is food or drug.",
 "headline_citation_ids":[], "headline_unsourced":true,
 "confidence":"moderate","confidence_score":0.6,
 "confidence_reasons":["1 of 3 reasoning steps could be sourced; the rest were left unanswered rather than asserted","5 of the top 5 passages were independently ranked highly by both semantic and keyword search"],
 "abstained":false,
 "steps":[{"step":1,"abstained":false},{"step":2,"abstained":true},{"step":3,"abstained":true},{"step":4,"abstained":false}],
 "citations":["DOC002_chunk_006 FSSAI Ayurveda Aahar Regulations, 2022, Regulation 71, p. 4",
              "DOC003_chunk_256 The Drugs and Cosmetics Rules 1945, p. 149",
              "DOC003_chunk_257 The Drugs and Cosmetics Rules 1945, p. 150"]}
```

**Specifically what was wrong — three things:**

1. **Wrong classification.** The user said "food supplement, not a medicine" and named turmeric.
   The FSSAI Ayurveda Aahara Regulations 2022 chunk was retrieved and cited. It still refused
   to commit to `ayurveda_aahar`.
2. **Two of three substantive steps abstained.** Steps 2 and 3 both carry `"abstained": true`.
   The citation guard did its job — nothing unsourced was asserted — but the user gets an
   answer that is mostly "I cannot tell you".
3. **The headline is unsourced and non-responsive.** `headline_unsourced: true`, and the
   sentence itself — *"Whether the recipe is from a Schedule-authoritative text is not answered
   by this evidence"* — restates the system's own difficulty rather than answering the user.
   This is the one sentence users read first.

**Plain-language step reading:**

1. **Classification** — "This could be FSSAI Ayurveda Aahara food, or a drug under the D&C Act, depending on your claims and where the recipe came from. FSSAI distinguishes Aahara prepared from authoritative books from products needing prior approval." *Frames the fork honestly, but does not classify.*
2. **Legal position (abstained)** — "The evidence does not name the books in the First Schedule, so I cannot tell you whether your text is on that list. Under the FSSAI Ayurveda Aahara Regulations 2022 recipes in authoritative Ayurveda books listed in Schedule A are considered for approval, but those in an Appendix/Annexure are not. Under Rule 168 Ayurvedic drugs must meet Ayurvedic Pharmacopoeia standards. Neither lets me confirm your text is on the relevant Schedule." *Correct behaviour under the rules, but note it answers a question about First-Schedule membership that the user never asked — the user asked about launching a food supplement.*
3. **Action route (abstained)** — "If the recipe is from a Schedule A authoritative book, prior Food Authority approval is not required and claims must follow those texts. If it is treated as an Ayurvedic drug under Rule 168, you must meet Pharmacopoeia standards and the excipient/colouring rules in Rules 168–169. The evidence does not say which Schedule your text is on, so check that yourself." *This is actually a usable conditional route, despite being flagged abstained.*
4. **Jurisdiction note** — "Indian law only; international IP, ABS or pharmacopoeial regimes outside this corpus."

**Consistency:** 2 and 3 do connect (both branch on the same unknown). The real inconsistency is
between the *question asked* ("I'm launching a supplement") and the *question answered*
("is your recipe in the First Schedule?"). The system latched onto a classification sub-question
and lost the user's actual concern.

---

#### Test 7 — "I've made a neem-based face cream for external use only."

- **Verdict: FAIL** — the worst of the Category 2 results
- **Reason:** Expected classification **cosmetic**; actual was `needs_clarification` **and the
  system then abstained entirely** with `out_of_scope`, producing no answer at all.

```json
{"http_status":200,"elapsed_s":8.74,
 "classification":{"category":"needs_clarification",
   "rationale":"The question describes a neem-based face cream for external use, which could be a cosmetic (cleansing/beautifying with no therapeutic claim) or an Ayurvedic medicine (diagnosis/treatment/mitigation/prevention of disease). The category is decisive for the regulatory pathway and evidence requirements."},
 "clarifying_question": null,
 "abstained":true,"abstention_kind":"out_of_scope",
 "abstention_message":"This is a product description or business statement, not a legal question requiring a legal answer.",
 "headline":null, "steps":[], "citations":[], "confidence":null,
 "escalate":false}
```

**Specifically what was wrong:**

- **Wrong classification** — the D&C Act's `cosmetic` definition (s.3(aaa), "external use…
  cleansing, beautifying") is an anchor category in this system, and "face cream for external
  use only" is close to a textbook match. It was not chosen.
- **It refused rather than answered.** The relevance gate ruled the input `out_of_scope` —
  *"a product description or business statement, not a legal question"*. That reasoning is
  literally true (test 7 as written is a statement, not a question), but the checklist's
  expectation was a cosmetic classification, and the system produced **zero steps, zero
  citations, no confidence, no headline**.
- **The clarifying question was dropped.** Classification said the category is undetermined but
  `clarifying_question` is `null`, so the user is not even told what to say next. The
  `out_of_scope` abstention message replaced it.
- **Contrast with test 17a**, where the *same* product plus an explicit "Can I patent it?"
  produced a full, well-cited answer. So the failure is triggered by the absence of an
  interrogative, not by the subject matter.

**The one thing the checklist asked for that did happen:** the checklist notes test 7 "should
NOT bring in Section 3(p)". It did not — but only because it produced no legal content at all.
That is not a meaningful pass.

**Plain-language step reading:** not applicable — there are no steps.

---

### Category 3 — General/Procedural Questions (No Product to Classify)

#### Test 8 — "What is Access and Benefit Sharing and when do I need NBA approval?"

- **Verdict: PASS**
- **Reason:** Correctly `not_applicable` (no product to classify), answered directly from the
  Biological Diversity Act/Rules, with the s.6 prior-approval-before-IPR rule named.

```json
{"http_status":200,"elapsed_s":15.37,
 "classification":{"category":"not_applicable","rationale":"...No specific product is described, named or implied, so there is nothing to classify."},
 "headline":"Access and Benefit Sharing is how India ensures fair sharing of benefits from using biological resources and traditional knowledge, and NBA approval is required before accessing such resources or seeking related IP rights.",
 "headline_citation_ids":["DOC007_chunk_019","DOC007_chunk_007","DOC022_chunk_055"],
 "confidence":"high","confidence_score":1.0,
 "confidence_reasons":["every reasoning step is backed by a cited provision","supported by 3 independent sources","5 of the top 5 passages were independently ranked highly by both semantic and keyword search"],
 "abstained":false,"rejected_citation_ids":[],
 "citations":["DOC007_chunk_003 BD Act 2002 p.4","DOC007_chunk_019 BD Act 2002 Section 21 p.12",
              "DOC007_chunk_007 BD Act 2002 p.7","DOC022_chunk_055 BD Rules 2024 Rule 13 p.53",
              "DOC008_chunk_071 BD Rules 2024 Rule 26 p.60","DOC016_chunk_035 ABS Guidelines p.19",
              "DOC016_chunk_038 ABS Guidelines Section 11 p.20","DOC016_chunk_027 ABS Guidelines p.16"]}
```

**Plain-language step reading:**

1. **Classification** — "This is an Indian biodiversity/IP question about ABS: the system controlling how biological resources and associated traditional knowledge are accessed and how benefits are shared. It matters because anyone using Indian biological material or TK may need approval before using, researching or seeking IP over it." *Does its job for a non-product question — it classifies the question type, not a product.*
2. **Legal position** — "Section 21(1) BD Act 2002: the NBA must ensure fair and equitable benefit sharing on mutually agreed terms. Section 6: persons covered by s.3(2) must get prior NBA approval **before applying** for any IPR based on research on an Indian biological resource or associated TK. Rule 13, BD Rules 2024: apply on the NBA portal in Form 1 (research/bio-survey) or Form 2 (commercial), with the fee paid to the National Biodiversity Fund." *Law only. Three provisions, all named inline.*
3. **Action route** — "File Form 1 or Form 2 on the NBA portal and pay the fee (₹10,000 individuals / ₹20,000 entities, First Schedule of the 2024 Rules). If you also want an IP right on that material you need prior s.6 approval before grant. Benefit sharing is set by the NBA; the ABS Guidelines indicate up to 1% of annual gross ex-factory sale price for commercial IP use, +25% where TK is involved, plus possible upfront payments." *Highly concrete — named forms, named portal, actual fee amounts, actual percentages.*
4. **Jurisdiction note** — "Indian law only, from the BD Act 2002, BD Rules 2024 and ABS Guidelines. Nagoya Protocol and other countries' CBD compliance not addressed."

**Consistency:** excellent — 2 states the duty, 3 tells you the form to file. Best-connected
2→3 pair in the whole run.

---

#### Test 9 — "How do I register a Geographical Indication for an Ayurvedic product?"

- **Verdict: PASS** *(with a caveat about how fast it returned)*
- **Reason:** Correctly `not_applicable`, cites the GI Act 1999 registration process
  (s.2(e), s.3, s.11(1), s.11(2)(a), 10-year renewable term).

**Caveat:** this returned in **0.02 s**, meaning it was served from the in-process answer cache
— the question had already been asked on this backend (from the browser session) before the
suite started. The content is a real prior answer, not a stub, but this particular run did not
exercise the model.

```json
{"http_status":200,"elapsed_s":0.02,
 "classification":{"category":"not_applicable"},
 "headline":"Under the GI Act, 1999, an Ayurvedic product can be registered as a Geographical Indication by filing an application with the Registrar of Geographical Indications.",
 "headline_citation_ids":["DOC012_chunk_011","DOC012_chunk_002"],
 "confidence":"high","confidence_score":0.9,
 "abstained":false,"rejected_citation_ids":[],
 "citations":["DOC017_chunk_013 Kandhamal Haladi p.16","DOC017_chunk_014 Kandhamal Haladi p.16",
              "DOC012_chunk_002 GI Act 1999 Section 2 p.6","DOC012_chunk_004 GI Act 1999 p.6",
              "DOC012_chunk_066 GI Act 1999 Section 3 p.31","DOC012_chunk_011 GI Act 1999 Section 11 p.9"]}
```

**Plain-language step reading:**

1. **Classification** — "This is about whether an Ayurvedic product qualifies as a 'good' protectable by GI. It matters because the GI Act only protects agricultural, natural or manufactured goods whose qualities come from geographical origin — and Kandhamal Haladi (turmeric) shows medicinal natural goods do fit." *Does its job, and grounds it in a real registered GI.*
2. **Legal position** — "Section 2(e): a GI identifies goods, including natural goods, as originating from a territory where a given quality, reputation or characteristic is essentially attributable to that origin. Section 2(k)(ii) defines a producer of natural goods as one who exploits them. Section 3 covers registration in specified classes and a two-part Register." *Law only.*
3. **Action route** — "Under s.11(1) an association of producers, or an organisation/authority established by law representing them, applies in writing to the Registrar of GIs in the prescribed form with the fee. Under s.11(2)(a) the application must show how the indication designates the goods as originating there and how quality/reputation is due to the geographical environment including natural and human factors. Registration lasts ten years and is renewable." *Concrete: who may apply, to whom, what the application must contain, how long it lasts.*
4. **Jurisdiction note** — "Indian law only, from the GI Act 1999; international regimes and treaty obligations not considered."

**Consistency:** step 3 is the procedural discharge of step 2's definition. No contradiction.
Note step 3 correctly flags that an *individual* cannot apply — a genuinely useful trap to warn
about.

---

#### Test 10 — "What is TKDL and how does it protect traditional knowledge?"

- **Verdict: PASS**
- **Reason:** Explains TKDL's purpose and mechanism correctly and **does not claim to search
  the TKDL database** — it describes examiners using it, which is the required abstention
  behaviour.

```json
{"http_status":200,"elapsed_s":9.13,
 "classification":{"category":"not_applicable"},
 "headline":"TKDL is India's digital database that protects traditional medicinal knowledge by converting it into international languages for use as prior art at patent offices.",
 "headline_citation_ids":["DOC023_chunk_001","DOC024_chunk_001"],
 "confidence":"high","confidence_score":0.95,
 "abstained":false,"rejected_citation_ids":[],
 "citations":["DOC015_chunk_001 About TKDL p.1","DOC023_chunk_001 TKDL Access Agreement p.1",
              "DOC020_chunk_116 MANUAL OF PATENT OFFICE PRACTICE, Sections 3(o), 3(p), p.98",
              "DOC024_chunk_003 TKDL Access Policy p.5","DOC024_chunk_005 TKDL Access Policy p.5",
              "DOC024_chunk_001 TKDL Access Policy p.1"]}
```

**Plain-language step reading:**

1. **Classification** — "This is about India's TK protection framework, specifically TKDL as a defensive mechanism. It matters because TK held in Indian languages is vulnerable to being patented abroad." *Does its job.*
2. **Legal position** — "TKDL is a Government of India proprietary database converting traditional medicinal knowledge from Hindi, Sanskrit, Arabic, Urdu, Tamil and Persian into five international languages. It is jointly held by the CGPDTM, NISCAIR/CSIR and the Department of AYUSH. Under Section 3(p) traditional knowledge and aggregations of known properties are not patentable, and the Examiner uses TKDL to decide whether a claim falls within that exclusion." *Law + institutional fact. Correct.*
3. **Action route** — "TKDL works defensively: examiners cite its ~0.226 million formulations (including neem and turmeric) against applications. EPO, USPTO and 11 other offices access it under formal agreements with confidentiality provisions, typically for three years. This breaks the language/format barrier that let the turmeric wound-healing patent be granted." *Concrete mechanism. Note it is a description rather than a user action — appropriate here, since a user cannot "file" with TKDL, and step 3 says exactly that: "rather than something a user registers with".*
4. **Jurisdiction note** — "Indian law only. International patent regimes and foreign jurisdictions are outside the scope of this evidence corpus."

**Internal inconsistency — flagged:** steps 2 and 3 spend most of their length on what
**foreign** patent offices (EPO, USPTO, 11 others) do with TKDL, and then step 4 says
international regimes are "outside the scope of this evidence corpus". Both statements are
individually defensible — the international material *is* described by Indian-side sources —
but placed together they read as self-contradictory. See the International-Scope section.

**Fact-check performed:** the figures "0.226 million medicinal formulations" and "34 million A4
pages" were verified verbatim in `DOC024_chunk_003`. Not invented.

---

#### Test 11 — "What's the difference between a trademark and a GI tag?"

- **Verdict: PASS**
- **Reason:** Explains both, and cites the Trade Marks Act 1999 and the GI Act 1999 as
  **separate** sources, exactly as the checklist requires.

```json
{"http_status":200,"elapsed_s":17.07,
 "classification":{"category":"not_applicable"},
 "headline":"A trademark identifies one business's goods, while a Geographical Indication identifies goods originating from a particular place.",
 "headline_citation_ids":["DOC012_chunk_004","DOC012_chunk_065"],
 "confidence":"high","confidence_score":1.0,
 "abstained":false,"rejected_citation_ids":[],
 "citations":["DOC012_chunk_065 GI Act 1999 p.30","DOC012_chunk_011 GI Act 1999 Section 11 p.9",
              "DOC014_chunk_012 Trade Marks Act 1999, Section 9, p.13",
              "DOC012_chunk_022 GI Act 1999 Section 23 p.14","DOC017_chunk_014 Kandhamal Haladi p.16",
              "DOC012_chunk_004 GI Act 1999 p.6"]}
```

**Plain-language step reading:**

1. **Classification** — "This is a conceptual IP-law question, not a product classification. It matters because Indian law treats trade marks and GIs as different kinds of right with different rules." *Does its job.*
2. **Legal position** — "Under the GI Act 1999 a GI shows goods come from a particular territory where a quality/reputation/characteristic is due essentially to the geographical environment including natural and human factors (s.11(2)(a)). Under Section 9 of the Trade Marks Act 1999 a trade mark is a sign distinguishing one person's goods or services from another's. The GI Act's Statement of Objects and Reasons explains it was made to protect producers of geographically linked goods from misuse of such names." *Law only, two separate statutes cited separately — the checklist's actual requirement.*
3. **Action route** — "For a trade mark, the owner applies to the Trade Marks Registry and gets an exclusive right that can be assigned or licensed. For a GI, an association of producers applies to the GI Registry (s.11(1)) and the right **cannot** be assigned, transmitted, licensed, pledged or mortgaged (s.24). GI registration lasts 10 years and is renewable; only authorised users may use it, and infringement actions lie with the registered proprietor and authorised users." *Concrete and genuinely comparative — the assignability contrast is the practically important difference, and it found it.*
4. **Jurisdiction note** — "Indian law only. TRIPS and Madrid-system filings outside this evidence."

**Consistency:** good. Step 3 does not restate step 2 — it converts definitions into two
different procedural paths.

**Citation-label note (not a failure):** step 3 attributes the assignment prohibition to
**Section 24**, while the citation card for `DOC012_chunk_022` is labelled **Section 23**. I read
the chunk: it contains both s.23 (prima facie validity) *and* s.24 (prohibition of assignment),
so the claim is genuinely supported by the cited text — the card just labels the chunk by its
opening heading. Under-labelling, not mis-citing.

---

### Category 4 — Should Trigger Safe Abstention

#### Test 12 — "Can I sell my Ayurvedic product in the United States? What does the FDA require?"

- **Verdict: PASS** — this is the safety-critical one, and it behaved correctly
- **Reason:** Refused with `foreign_jurisdiction` in 4.06 s, emitted **zero citations**, and did
  not answer from Indian law.

```json
{"http_status":200,"elapsed_s":4.06,
 "classification":{"category":"not_applicable","rationale":"...a question about US regulatory procedure, not about classifying a product under Indian Ayurvedic categories."},
 "abstained":true,"abstention_kind":"foreign_jurisdiction",
 "abstention_message":"This question is governed by another country's law. This corpus covers Indian law only, so answering it from these sources would be misleading.",
 "escalate":true,
 "escalation_reason":"This question is governed by law outside this corpus. A practitioner who works across jurisdictions can advise on it directly.",
 "headline":null,"steps":[],"citations":[],"confidence":null,
 "disclaimer":"This is information, not legal advice. ..."}
```

**Why this matters:** this is the exact query that `COMPARISON_REPORT.md` recorded as
previously being **answered** with FSSAI and D&C Rules citations. It is now refused, and the
refusal reason is specific ("another country's law"), not a generic off-topic bounce. It also
offers human escalation, which is the right outgoing route for a real legal need this system
cannot meet.

**Plain-language step reading:** not applicable — the system abstained by design, which is the
correct output.

---

#### Test 13 — "How do I bake a good chocolate cake?"

- **Verdict: PASS**
- **Reason:** Refused as `out_of_scope` (not as "foreign jurisdiction", which was a past
  defect), with a reason naming the actual subject.

```json
{"http_status":200,"elapsed_s":4.15,
 "classification":{"category":"not_applicable"},
 "abstained":true,"abstention_kind":"out_of_scope",
 "abstention_message":"The question is about baking a chocolate cake, which is not a legal question and falls entirely outside the scope of the Indian Ayurveda legal corpus.",
 "escalate":false,"steps":[],"citations":[]}
```

Correctly does **not** offer escalation — there is no legal need here. The distinction between
tests 12 and 13 (escalate vs not) is working.

---

#### Test 14 — "Will I win my patent infringement lawsuit against my competitor?"

- **Verdict: PASS**
- **Reason:** Refused to predict a case outcome, naming the reason as legal advice, and the
  standing disclaimer is present on the response.

```json
{"http_status":200,"elapsed_s":5.19,
 "classification":{"category":"not_applicable","rationale":"...It concerns litigation strategy/outcome, not the regulatory classification of a product."},
 "abstained":true,"abstention_kind":"out_of_scope",
 "abstention_message":"The question asks for a prediction about the outcome of a specific lawsuit, which is legal advice rather than a question about Indian IP or drug law that the corpus can resolve.",
 "escalate":false,"steps":[],"citations":[],
 "disclaimer":"This is information, not legal advice. It cites primary legal sources but is not a substitute for a qualified IP practitioner."}
```

**One observation, not a failure:** `escalate` is `false` here. A person with a live
infringement suit is arguably the *most* in need of a human practitioner, so this is a case
where the escalation offer would have been useful. `escalation.py` deliberately suppresses the
offer for `out_of_scope`; that rule is right for chocolate cake and arguably wrong here.

---

#### Test 15 — Greeting / empty message

- **Verdict: PASS**
- **Reason:** "hi" is answered as small talk with capability info and three starter questions;
  empty and whitespace-only input is rejected cleanly at the API boundary with a structured
  422, and no crash or malformed body in any case.

**15a — "hi":**
```json
{"http_status":200,"elapsed_s":0.02,
 "abstained":false,"abstention_kind":"conversational",
 "abstention_message":"Hello. I answer questions about Indian law for Ayurvedic products - patents, trade marks, GI, copyright, biodiversity and ABS, drug and food regulation, and pharmacopoeial standards. Every answer cites the provision it relies on. What would you like to know?",
 "example_questions":["Can a classical churna from a First Schedule text be patented?",
                      "How do I register a Geographical Indication for an Ayurvedic product?",
                      "What is Access and Benefit Sharing and when do I need NBA approval?"],
 "classification":null,"steps":[],"citations":[]}
```
Note `abstained: false` with kind `conversational` — the UI is meant to render this as a plain
reply, not as a refusal. Correct.

**15b — empty string, and 15c — `"   "`:**
```json
{"http_status":422,
 "detail":[{"type":"string_too_short","loc":["body","question"],
            "msg":"String should have at least 2 characters","ctx":{"min_length":2}}]}
```
Both return a well-formed JSON 422 in 0.02 s, no stack trace, no HTML. The whitespace case
proves the `strip_whitespace` fix holds. **This state is also unreachable from the UI** —
`App.tsx` guards with `if (!typed || loading) return;` — so a user cannot trigger it.

---

### Category 5 — Follow-Up / Conversation Memory

#### Test 16 — Ashwagandha extraction process → "What if I want to patent the plant itself instead?"

- **Verdict: PASS**
- **Reason:** The second question was resolved to *"…patent the **Ashwagandha** plant itself…"*
  without the user re-mentioning it, and it correctly gave the Section 3(j) plant exclusion and
  pointed to the Plant Varieties Act instead.

**Turn 1 — "Can I patent a new extraction process for Ashwagandha?"**
```json
{"http_status":200,"elapsed_s":27.67,
 "classification":{"category":"patent_proprietary"},
 "headline":"A new extraction process for Ashwagandha may be patentable in India only if it meets novelty, inventive step, and Section 3(d) efficacy requirements.",
 "confidence":"high","confidence_score":0.9,
 "citations":["DOC005_chunk_009 patents act 1970 Section 3 p.11","DOC020_chunk_108 Manual Section 3(d) p.89",
              "DOC020_chunk_100 Manual Section 9 p.83","DOC020_chunk_121 Manual Section 10(5) p.103",
              "DOC003_chunk_807 D&C Rules p.554","DOC003_chunk_809 p.555","DOC024_chunk_001 TKDL Access Policy p.1"]}
```

**Turn 2 — "What if I want to patent the plant itself instead?" (history = turn 1)**
```json
{"http_status":200,"elapsed_s":15.88,
 "question":"What if I want to patent the plant itself instead?",
 "resolved_question":"What if I want to patent the Ashwagandha plant itself instead?",
 "headline":"You cannot patent the Ashwagandha plant itself in India; plants are excluded from patentability, but plant varieties have a separate protection route.",
 "headline_citation_ids":["DOC020_chunk_113"],
 "classification":{"category":"not_applicable"},
 "confidence":"high","confidence_score":0.9,
 "abstained":false,"rejected_citation_ids":[],
 "citations":["DOC020_chunk_113 MANUAL OF PATENT OFFICE PRACTICE, Section 3(j), p.95",
              "DOC013_chunk_001 The Protection of Plant Varieties and Farmers Rights Act, 2001, p.5",
              "DOC022_chunk_081 BD Rules 2024 p.65","DOC008_chunk_085 BD Rules 2024 p.65"]}
```

**Plain-language step reading (turn 2):**

1. **Classification** — "This is about patent eligibility for a whole plant, not about classifying a product. It matters because plants sit at the boundary between patent law and a separate plant variety law, and which route you pick decides whether you get any right at all." *Does its job.*
2. **Legal position** — "Under Section 3(j), plants in whole or any part, seeds, varieties and species, and essentially biological processes are not inventions and cannot be patented. Microorganisms other than those merely discovered in nature may be patentable. Plant varieties get a different regime under the Protection of Plant Varieties and Farmers' Rights Act." *Law only, and exactly the Section 3(j)-type exclusion the checklist predicted.*
3. **Action route** — "Because 3(j) bars patents on plants, the route for a new Ashwagandha variety is the PPV&FR Act, not the Patents Act; a patent application on the plant itself would be refused. If your invention only *uses* Ashwagandha (an extract or formulation) the patent route is open, but Biological Diversity Rules 2024 compliance (Forms 7 and 9) may apply before filing or commercialisation." *Concrete: names the correct alternative statute and the ABS forms.*
4. **Jurisdiction note** — "Indian law only. PCT, EPO practice and UPOV outside this corpus."

**Consistency:** step 3 is the direct consequence of step 2's bar, plus a correctly scoped
carve-out ("if you claim the extract instead"). Strong.

**Small factual drift (harmless):** step 2 says the Plant Varieties Act is of **2001**, while the
Manual chunk it cites prints **2002**. 2001 is the correct year and matches the other cited
source (`DOC013_chunk_001`), so the model silently corrected the Manual's own typo. Worth
knowing, not a defect.

**Minor:** turn 2 was classified `not_applicable` even though a product (Ashwagandha) is
plainly present. Defensible — the question is about a plant, not a formulation — and it did not
affect the answer.

---

#### Test 17 — Classification question → "Why not?"

- **Verdict: FAIL**
- **Reason:** "Why not?" was refused as `too_vague`; the conversation history was sent but
  never used to resolve it, so the user gets a dead end instead of a follow-up.

**Turn 1 — "I've made a neem-based face cream for external use only. Can I patent it?"** — a
good answer (this is the same product test 7 refused; adding "Can I patent it?" made it work):
```json
{"http_status":200,"elapsed_s":14.24,
 "classification":{"category":"needs_clarification",
   "clarifying_question":"Is the cream formulated exactly as described in an authoritative Ayurvedic text listed in the First Schedule, or is it your own formulation of neem and other ingredients?"},
 "headline":"A neem-based face cream faces major patent bars in India; patentability depends on whether it shows synergy, enhanced efficacy, or is a novel combination over the prior art.",
 "confidence":"high","confidence_score":0.9,
 "citations":["DOC020_chunk_116 Manual Sections 3(o),3(p) p.98","DOC020_chunk_108 Manual Section 3(d) p.89",
              "DOC020_chunk_109 Manual Section 3(e) p.91","DOC020_chunk_104 Manual Sections 1,3 p.87",
              "DOC022_chunk_083 BD Rules 2024 p.65"]}
```

**Turn 2 — "Why not?" (history = turn 1):**
```json
{"http_status":200,"elapsed_s":1.52,
 "question":"Why not?",
 "resolved_question":null,
 "abstained":true,"abstention_kind":"too_vague",
 "abstention_message":"That is too short for me to search on. Tell me what the product is, or which part of the law you are asking about.",
 "headline":null,"steps":[],"citations":[],"confidence":null}
```

**Specifically what was wrong:** `resolved_question` is `null`, which means `contextualise()`
returned "Why not?" unchanged despite being given the previous turn. Then
`is_too_vague("Why not?")` — 0 content words after stop-word removal — refused before any
retrieval. Two separate things had to go right and neither did:

- the rewrite that worked in test 16 did not fire for a bare ellipsis;
- the vagueness guard runs *after* the rewrite, so when the rewrite is a no-op the guard has no
  safety net.

The user-visible result is a system that just answered a rich question about neem cream and
then, asked "Why not?", replies *"Tell me what the product is"* — it appears to have forgotten
the conversation one message earlier. The checklist's expectation ("a coherent follow-up tied
to Q1's answer") was not met.

**Plain-language step reading:** not applicable — no steps produced.

---

#### Test 18 — 10–12 questions in a row in one session (the §6.2 crash bug)

- **Verdict: PARTIAL**
- **Reason:** The specific bug is **fixed** — no request in the session returned a 422 and none
  crashed, including questions 9 through 12 with 8–10 history items. But 9 of the 12 questions
  could not be answered on this run because the upstream free-tier quota was exhausted from
  question 2 onward, so the full 12-question session was not demonstrated end to end.

| # | question | history sent | HTTP | outcome |
|---|---|---|---|---|
| 1 | What is the Traditional Knowledge Digital Library? | 0 | 200 | full answer, `high` (0.9), 4 citations |
| 2 | How does the Patents Act treat traditional knowledge? | 1 | **502** | upstream unavailable (see below) |
| 3 | What is a Geographical Indication? | 1 | 200 | **`too_vague` — a real bug, see below** |
| 4 | Do I need NBA approval to file a patent using Indian biodiversity? | 2 | 200 | `gate_unavailable` (quota) |
| 5 | What is a classical Ayurvedic formulation under the D&C Act? | 3 | 200 | `gate_unavailable` (quota) |
| 6 | What licence do I need to manufacture an Ayurvedic medicine? | 4 | 200 | `gate_unavailable` (quota) |
| 7 | Can I trademark the name of my Ayurvedic product? | 5 | 200 | `gate_unavailable` (quota) |
| 8 | What labelling rules apply to Ayurvedic medicines? | 6 | 200 | `gate_unavailable` (quota) |
| **9** | Can I copyright the text of my Ayurvedic formulation booklet? | **7** | **200** | `gate_unavailable` (quota) — **not a 422** |
| 10 | What are the data requirements for a phytopharmaceutical drug? | 8 | 200 | `gate_unavailable` (quota) |
| 11 | Is a plant variety protectable in India? | 9 | 200 | `gate_unavailable` (quota) |
| 12 | What does the Drugs and Magic Remedies Act prohibit? | 10 | 200 | `gate_unavailable` (quota) |

**Two findings buried in this table that are not about the quota:**

**(a) Question 3 is a genuine, reproducible bug.** *"What is a Geographical Indication?"* — an
unambiguous legal question that test 9 answers happily in a longer phrasing — was refused:
```json
{"http_status":200,"elapsed_s":17.85,
 "question":"What is a Geographical Indication?","resolved_question":null,
 "abstained":true,"abstention_kind":"too_vague",
 "abstention_message":"That is too short for me to search on. Tell me what the product is, or which part of the law you are asking about.",
 "steps":[],"citations":[]}
```
This is **not** quota-related — it is the same deterministic `MIN_CONTENT_WORDS = 3` guard as
test 17, verified by calling the function directly. Any short, well-formed question fails.

**(b) The 502 on question 2 is the one genuinely unhandled failure mode.** Every other
quota-exhausted request degraded gracefully to a 200 with `gate_unavailable` and a
user-readable message. Question 2 instead returned:
```json
{"http_status":502,"detail":"Query failed because an upstream service was unavailable. Please try again in a moment."}
```
The frontend surfaces that as an error banner rather than as a designed abstention panel, so
the same underlying cause produces two different user experiences.

**The §6.2 criterion specifically:** the report's repro was `POST /query` with 9 history items
returning 422. Re-tested directly:
```json
// SYS-6.2b: POST /query, history = 9 raw items
{"http_status":200,"elapsed_s":18.31,
 "classification":{"category":"not_applicable"},
 "headline":"TKDL is India's proprietary database converting traditional medicinal knowledge into prior art to prevent misappropriation at international patent offices.",
 "confidence":"high","confidence_score":0.9,"abstained":false,
 "citations":["DOC015_chunk_001","DOC023_chunk_001","DOC024_chunk_003","DOC020_chunk_116"]}
```
**200, full answer, no 422.** The server-side truncating validator works. **§6.2 is fixed.**

---

### Category 6 — Citation & Confidence Integrity

#### Test 19 — Spot-check citations against the actual source text

- **Verdict: PASS**
- **Reason:** All 82 citations emitted across the run were re-verified against
  `data/chunks/all_chunks.json` independently of the code that produced them — **zero
  fabricated IDs, zero excerpt mismatches, zero dangling references** — and five were read in
  full by hand to confirm the source genuinely supports the claim.

**Automated check (`verify_citations.py`, run over all 38 JSON responses):**
```
citations checked: 82 across 38 responses
responses with integrity problems: 0
```
It checks four things per citation: (1) the `chunk_id` exists in the corpus; (2) the `excerpt`
shown on the citation card is a verbatim substring of that chunk's text; (3) any `section`
string on the card actually occurs in the chunk text; (4) every `citation_id` referenced by a
reasoning step or by the headline resolves to a citation card. All four passed everywhere.
`rejected_citation_ids` was empty on every response — the model never tried to cite something
unverifiable in this run.

**Manual reads — does the source actually support the claim?**

| citation | claim made | what the source text actually says | verdict |
|---|---|---|---|
| `DOC020_chunk_116` — Manual of Patent Office Practice p.98 | "Section 3(p) bars traditional knowledge; turmeric antiseptic example; Examiner consults TKDL" | *"09.03.05.15 An invention which in effect, is traditional knowledge or which Section 3(p) is an aggregation or duplication of known properties of traditionally known component or components is not an invention… An example is the antiseptic properties of turmeric for wound healing. Another example is the pesticidal and insecticidal properties of neem. The Examiner conducts investigation by using Traditional Knowledge Digital Library (TKDL)…"* | **Supported exactly** |
| `DOC015_chunk_001` — About TKDL p.1 | "TKDL is an initiative of India to prevent misappropriation at international patent offices; the turmeric US patent showed the need" | *"…a pioneering initiative of India to protect Indian traditional medicinal knowledge and prevent its misappropriation at International Patent Offices… The grant of a US patent to wound healing properties of turmeric flags the danger…"* | **Supported exactly** |
| `DOC024_chunk_003` — TKDL Access Policy p.5 | "~0.226 million formulations across 34 million A4 pages" | *"TKDL ready to safeguard 0.226 million medicinal formulations like Neem and Turmeric in Ayurveda, Unani and Siddha which are present in 34 million A4 size pages"* | **Supported exactly** — numbers not invented |
| `DOC012_chunk_022` — GI Act 1999, card labelled "Section 23" | "a GI right cannot be assigned, transmitted, licensed, pledged or mortgaged (Section 24)" | chunk contains both s.23 and *"24. Prohibition of assignment or transmission… shall not be the subject matter of assignment, transmission, licensing, pledge, mortgage…"* | **Supported** — card under-labels the chunk, claim is genuine |
| `DOC020_chunk_113` — Manual p.95 | "Section 3(j): plants in whole or part, seeds, varieties and species are not inventions; plant varieties protected under a separate Act" | *"09.03.05.09 Plants and animals in whole or any part thereof other than Section 3(j) micro-organisms but including seeds, varieties and species… are not inventions… Plant varieties are provided protection in India under the… Protection of Plant Varieties and Farmers' Rights Act, 2002"* | **Supported** (year typo is in the source, not the answer) |

---

#### Test 20 — Confidence badge on a weakly-covered topic

- **Verdict: NOT CONCLUSIVE — could not be evaluated**
- **Reason:** The question ran after the upstream daily quota was exhausted, so the system never
  produced an answer to score a confidence badge on.

```json
{"question":"What does Article 27.3(b) of the TRIPS Agreement require for plant variety protection?",
 "http_status":200,"elapsed_s":35.61,
 "classification":{"category":"needs_clarification","rationale":"The classification service is temporarily unavailable."},
 "abstained":true,"abstention_kind":"gate_unavailable",
 "abstention_message":"I could not run the scope and jurisdiction check for this question, so I am not going to answer it. This check is what stops the assistant answering a question about another country's law from Indian sources. Please try again in a moment.",
 "confidence":null,"confidence_reasons":[],"steps":[],"citations":[]}
```

**What the rest of the run does say about calibration**, since this test could not:
of the 15 substantive answers produced before the quota died, **13 scored `high` and 2 scored
`moderate`** — and the two `moderate` ones were exactly the answers that deserved it
(test 4 at 0.70 "rests on a single source"; test 6 at 0.60 "1 of 3 reasoning steps could be
sourced"). So the badge is **no longer a constant** — the §6j calibration fixes are visibly
doing something. But 13 of 15 at `high` is still a heavily top-loaded distribution, and this
run did not include a single case where a genuinely thin answer was produced and scored, which
is precisely what test 20 was for. **The calibration question is still open.**

---

#### Test 21 — Same question twice in fresh sessions

- **Verdict: NOT CONCLUSIVE — could not be evaluated**
- **Reason:** Two separate obstacles. First, the in-process answer cache returned run 1
  (`T21a`) in **0.02 s**, byte-identical to test 1 — the same backend process, so it was a cache
  hit, not an independent generation. Second, the genuinely independent run (restart the
  backend to clear the cache, then re-ask) could not be performed because the quota was gone.

```json
// T21a - identical to Test 1's answer, served from cache
{"http_status":200,"elapsed_s":0.02,
 "classification":{"category":"classical_generic"},
 "headline":"A classical churna from a First Schedule text cannot be patented because traditional knowledge is not an invention under Section 3(p) of the Patents Act, 1970.",
 "confidence":"high","confidence_score":0.85,
 "citations":["DOC001_chunk_004","DOC020_chunk_116","DOC015_chunk_001"]}
```

**Partial signal, offered as such and not as a pass:** tests 1 and 2 are the same subject in two
different phrasings ("Can a classical churna from a First Schedule text be patented?" vs "I want
to patent my grandmother's classical churna recipe from an old text"), generated independently.
Both classified `classical_generic`, both cited `DOC020_chunk_116` for Section 3(p), both named
TKDL as the defensive route. That is consistent in substance across phrasings — but it is not
the same-question-twice test that was asked for.

**To actually run this:** restart the backend (clears the cache), ask the flagship question,
restart again, ask it again, and diff classification + citation IDs.

---

### Category 7 — Jurisdiction Handling

#### Test 22 — Toggle to International and ask the churna question

- **Verdict: NOT APPLICABLE — the International corpus is not built (deferred by design)**
- **Reason:** The checklist's expectation ("a genuinely different, internationally-framed
  answer") presupposes a phase that `CLAUDE.md` explicitly defers; `data/corpus/03_international`
  is empty. The behaviour that *does* exist is correct, so this is recorded as not-applicable
  rather than as a failure.

```json
{"question":"Can a classical churna from a First Schedule text be patented?",
 "jurisdiction":"international","http_status":200,"elapsed_s":0.0,
 "abstained":true,"abstention_kind":"foreign_jurisdiction",
 "abstention_message":"International coverage is not available yet. The corpus currently holds Indian law only. Switch to India to get the national position.",
 "escalate":true,
 "escalation_reason":"This question is governed by law outside this corpus. A practitioner who works across jurisdictions can advise on it directly.",
 "headline":null,"steps":[],"citations":[],"confidence":null}
```

**The important negative result:** it did **not** relabel the Indian answer as international.
Zero citations, no steps, no reused Indian content, and it returned in 0.0 s without spending a
model call. The failure mode the checklist was probing for does not occur.

---

#### Test 23 — Does the disabled International toggle communicate "not available yet"?

- **Verdict: PARTIAL**
- **Reason:** The button is visually and semantically disabled, but clicking it is a **silent
  no-op**, and the explanatory sentence in the UI is unreachable code.

From `frontend/src/App.tsx:262-298`:

```tsx
const unavailable = j === "international";
<button
  aria-disabled={unavailable}
  title={unavailable ? t.jurisdictionIntlNote : t.jurisdictionIndiaNote}
  onClick={() => { if (!unavailable) setJurisdiction(j); }}
  className={unavailable ? "cursor-not-allowed border-paper/10 text-paper/30" : ...}
  style={unavailable ? { backgroundImage: "repeating-linear-gradient(135deg, ...)" } : undefined}
>
...
{jurisdiction === "international" && (
  <p className="mt-2 text-[11px] ...">{t.jurisdictionIntlNote}</p>
)}
```

**What works:** greyed text, diagonal hatch fill, `cursor-not-allowed`, `aria-disabled="true"`
for screen readers, and a `title` tooltip carrying *"International coverage is not available yet
— the corpus holds Indian law only."*

**What does not:** `onClick` short-circuits, so `jurisdiction` can never become
`"international"` — which means the visible explanatory paragraph guarded by
`jurisdiction === "international"` is **dead code that can never render**. A user who clicks the
button gets no click feedback, no message, no state change. The only channel is a hover
tooltip, which does not exist on touch devices. The checklist asks that toggling "clearly
communicate 'not available yet', not silently do nothing" — on click, it does silently do
nothing.

**Note:** the *backend* handles `jurisdiction: "international"` correctly (test 22), so this is
purely a frontend affordance gap. The plumbing is real; only the click feedback is missing.

---

## System-Level Checks (from `COMPARISON_REPORT.md`)

### §6.1 — Path traversal / arbitrary file read

- **Verdict: PASS**
- **Reason:** Eight traversal and anchor-replacement payloads were fired at the running server
  with the SPA catch-all mounted. **None returned a file.** Every one returned the 951-byte
  `index.html`, byte-for-byte the size of `frontend/dist/index.html`, and six were logged
  server-side as blocked.

```
GET /..%2f..%2f.env                       -> 200  text/html  951 bytes  (index.html)
GET /..%2f..%2fbackend%2fapp%2fconfig.py  -> 200  text/html  951 bytes  (index.html)
GET /../../.env                           -> 200  text/html  951 bytes  (index.html)
GET /..%2F..%2F.env                       -> 200  text/html  951 bytes  (index.html)
GET /C:/Windows/win.ini                   -> 200  text/html  951 bytes  (index.html)   <- anchor replacement
GET /%2e%2e%2f%2e%2e%2f.env               -> 200  text/html  951 bytes  (index.html)
GET /..%252f..%252f.env                   -> 200  text/html  951 bytes  (index.html)   <- double-encoded
GET /assets/../../.env                    -> 404  application/json  {"detail":"Not Found"}
```

**Corroborating evidence:**
- `frontend/dist/index.html` is exactly **951 bytes**; `.env` is **172 bytes**. Every response
  was 951 — the fallback page, never the secret.
- The server log recorded six blocks:
  `WARNING app.main: Blocked path traversal attempt: '../../.env'`,
  `... '../../backend/app/config.py'`, and so on.
- The original report's two confirmed exploits (`200, 96 bytes, the OpenRouter API key` and
  `200, 2,780 bytes, source file`) are both closed.

**Still open, and outside what a test can fix:** `CLAUDE.md` §6j records that **the OpenRouter
key has never been rotated** since it was read out through this hole. The vulnerability is
closed; the key it leaked is still the key in `.env`. That remains a live action item.

**Bonus check — API routing (`SYS-routing`):**
```
GET /api/nope  -> 404  application/json  {"detail":"No such API endpoint."}
GET /health    -> 200  application/json  {"status":"ok", ...}
GET /          -> 200  text/html  951 bytes  (index.html)
```
Unknown `/api/` paths return JSON 404s rather than a 200 of `index.html`, so a client's
`response.ok` no longer lies. Fixed.

### §6.2 — Every conversation breaks at the 9th question

- **Verdict: PASS**
- **Reason:** Re-tested two ways and neither reproduces the 422.

1. **Direct repro of the report's payload** — `POST /query` with **9** raw history items:
   returned **200** with a full four-step answer, `confidence: high` (0.9), 4 citations. The
   server-side validator now truncates surplus history instead of rejecting it.
2. **A realistic 12-question session** (test 18) — questions 9, 10, 11 and 12 carried 7, 8, 9
   and 10 history items respectively. All returned **200**. No 422 anywhere in the session.

Client-side, `api.ts:100` also slices `history.slice(-MAX_HISTORY_TURNS)`, so both sides are
independently safe, which is what the report asked for.

---

## International-Scope Detection Cases

This section exists because you flagged the behaviour as unclear. The short answer is that
**there is no international-scope detector on the answer path** — and understanding that
resolves most of the confusion.

### The mechanism, stated plainly

Step 4's wording is **mandated by the prompt on every single answer**, not produced by any
detection logic. From `backend/app/generation.py:137`:

> `4. **Jurisdiction note** - state that this answers the position under **Indian law only**,`
> `and that international regimes are outside this corpus.`

So step 4 is a **standing scope footnote**, structurally equivalent to the disclaimer. It is
*not* the system saying "I detected that this needs international law and I am punting."

That is entirely separate from the real scope gate, which is
`AbstentionKind.FOREIGN_JURISDICTION` — an abstention that produces **zero steps and zero
citations**. When the system genuinely decides a question is out of jurisdiction, you get no
answer at all, not an answer with a caveat.

### Case-by-case

**Group A — questions that genuinely needed foreign/international law. Correctly refused, no
answer given.**

| question | detected as | did it answer anyway? | correct? |
|---|---|---|---|
| "What about internationally?" (test 1 follow-up) | `foreign_jurisdiction` | **No** — 0 steps, 0 citations | **Yes.** Genuinely needs non-Indian law. Correct refusal. *(Separate defect: the question was mis-resolved to "…trademarked internationally?" — see test 1.)* |
| "Can I sell my Ayurvedic product in the United States? What does the FDA require?" (test 12) | `foreign_jurisdiction` | **No** — 0 steps, 0 citations | **Yes.** US regulatory law. Not in the corpus. Correct refusal, and the one that matters most. |
| Churna question with the toggle set to International (test 22) | `foreign_jurisdiction` | **No** — 0 steps, 0 citations, 0.0 s | **Yes.** User explicitly asked for a jurisdiction we do not hold. |

**No case in Group A both refused and answered.** The bug you were worried about — saying "this
needs the international corpus" and then answering anyway — **does not occur on this path.**

**Group B — the standing footnote on answers that never needed international law.**

Every one of the 15 substantive answers in this run carried a step 4 saying international
regimes are outside the corpus: tests 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 16a, 16b, 17a, T18-01,
SYS-6.2b. **15 of 15.** None of these questions needed foreign law — they are all Indian-law
questions — and the system answered all of them fully. The footnote is not a punt; it is a
boilerplate scope statement.

**Is that a bug?** Not on its own. But it has two visible costs:

1. **It reads as a punt to anyone who does not know it is boilerplate.** Four sentences into
   every answer, the system volunteers a limitation nobody asked about. On test 8 (ABS) it
   names the Nagoya Protocol; on test 2 it names "foreign trade-mark rules" and "USPTO or EPO
   practice" — for a question about a grandmother's churna recipe where trade marks were never
   mentioned. The model pads the footnote with whatever foreign regimes seem topical, so it
   drifts away from the question.
2. **On one answer it directly contradicts the body — test 10.** Steps 2 and 3 explain at length
   that EPO, USPTO and 11 other international offices access TKDL under formal agreements, and
   then step 4 says *"International patent regimes and foreign jurisdictions are outside the
   scope of this evidence corpus."* Both statements are individually true (the international
   material is described *by Indian sources*), but read in sequence they are incoherent. **This
   is the one instance in the run where step 4 genuinely contradicts steps 2–3.**

   Notably, T18-01 answered the *same* subject and produced a better-calibrated step 4:
   *"…bilateral TKDL access agreements with other countries are referenced only as far as the
   Indian-side evidence describes them."* So the model can get this right; it is inconsistent
   about it.

**Group C — questions that were arguably answerable from the Indian corpus but were refused.**

**None found in this run.** No question was refused as foreign/international that Indian sources
could have answered. Test 20's TRIPS question would have been the interesting case — TRIPS
Article 27.3(b) is a treaty provision, arguably outside the corpus, and the answer would have
told us whether the gate distinguishes "a treaty question" from "a question about Indian law
implementing a treaty" — but it was killed by the quota before the gate ran.

### Your three questions, answered directly

1. **Which questions triggered it?** Explicit foreign-jurisdiction refusals: three (tests 1
   follow-up, 12, 22). Standing step-4 footnote: all 15 substantive answers.
2. **Did they genuinely need international law?** All three refusals: **yes**. All 15 footnoted
   answers: **no** — the footnote is unconditional boilerplate, not a judgement about that
   question.
3. **Did it say "outside coverage" and then answer anyway?** For real refusals, **no** — those
   produce zero steps and zero citations, never a partial answer. For the footnote, **yes by
   design**, and it is only actually confusing in **test 10**, where the footnote contradicts
   what steps 2 and 3 just said.

### Recommendation (recorded, not applied)

Make step 4 conditional on what the answer actually drew on, rather than a fixed instruction —
e.g. name only the regimes the question or the evidence actually touched, and where the evidence
*does* describe cross-border mechanisms from Indian sources (TKDL access agreements), say that
rather than blanket-disclaiming them.

---

### Run 2 — the same analysis on Gemini

The mechanism is unchanged, because it is in the prompt rather than in any model: step 4's
wording is mandated on **every** answer by `generation.py:137`. Run 2 confirms this is
model-independent — all 20 substantive Gemini answers carried it, in near-identical words
("This answers the position under Indian law only, and international regimes are outside this
corpus"), including answers where nothing international was remotely in play.

**Group A — genuinely foreign/international, correctly refused with zero output:**

| question | detected as | answered anyway? | correct? |
|---|---|---|---|
| "What about internationally?" (test 1 follow-up) | `foreign_jurisdiction` | No — 0 steps, 0 citations | **Yes** |
| "Can I sell my Ayurvedic product in the United States? What does the FDA require?" (test 12) | `foreign_jurisdiction` | No — 0 steps, 0 citations | **Yes** |
| Churna question with the toggle on International (test 22) | `foreign_jurisdiction` | No — 0 steps, 0 citations, 0.03 s | **Yes** |
| **"What does Article 27.3(b) of the TRIPS Agreement require for plant variety protection?" (test 20)** | `foreign_jurisdiction` | **No** — 0 steps, 0 citations | **Yes — and this is the new one** |

**Test 20 is the case you specifically asked to be judged, so here it is explicitly.**

- *Did it genuinely need international law?* **Yes.** TRIPS Article 27.3(b) is a WTO treaty
  provision. `data/corpus/03_international/` is empty by design, so the corpus contains no
  treaty text. There is no honest way to answer the question as asked from Indian statutes.
- *Was it actually answerable from the Indian corpus and the system incorrectly punted?*
  **No — but with a real caveat.** India's *implementation* of Article 27.3(b) is the Protection
  of Plant Varieties and Farmers' Rights Act 2001, and the corpus **does** hold it (71 chunks) —
  test 16 cites it. So a maximally helpful answer would have refused the treaty question *and
  pointed at the Indian instrument that implements it*. The abstention message does gesture in
  that direction ("Ask about the Indian position and I can answer that") but does not name the
  Act it could have named. **The refusal is correct; the handoff is generic where it could have
  been specific.**
- *Did it then answer anyway?* **No.** Zero steps, zero citations, `confidence: null`. Clean.

Note also the Run 1 follow-up defect did **not** recur: in Run 2, "What about internationally?"
was not silently rewritten into a trade-mark question.

**Group B — the standing footnote on answers that never needed foreign law.** All 20
substantive Gemini answers, same as Run 1's 15. Not a punt; boilerplate.

**Group C — refused as foreign when Indian sources could have answered.** **None.** No question
in either run was refused as foreign/international that the Indian corpus could have handled.

**The Run 1 contradiction did not recur, but a worse cousin appeared.** Run 1's test 10 had
steps 2–3 describing EPO/USPTO access to TKDL and then step 4 disclaiming international
regimes. Run 2's test 10 kept the international material shorter and the contradiction is
milder. **However**, Run 2 introduced a different and more damaging false scope claim — the
history-induced *"trademark law is not covered by the provided corpus"* and *"the provided
corpus contains no provisions regarding copyright law"* (test 18, questions 7 and 9). Those are
not jurisdiction statements, but they are the same failure family: **the system asserting a
limit on its own coverage that is not true.** Treated in full under Run 2 / Test 18.

### Recommendation (recorded, not applied)

Two changes, in priority order:

1. **Stop the relevance gate from inferring corpus scope from conversation history.** The gate
   should judge the current question against the retrieved passages, not against the topics of
   the last six turns. A cheap mitigation is to state the corpus's actual coverage in the gate
   prompt so it cannot invent a narrower one.
2. **Make step 4 conditional.** Name only the regimes the question or the evidence actually
   touched, and where the evidence *does* describe cross-border mechanisms from Indian sources
   (TKDL access agreements), say that rather than blanket-disclaiming them. Where a treaty
   question is refused, name the Indian implementing statute if the corpus holds it — as it
   does for TRIPS 27.3(b) → PPV&FR Act 2001.

---

## Cross-cutting findings

Ordered by priority, with each labelled by whether it survives a model change.

### 1. `is_too_vague()` refuses valid short questions — **architectural**, both models

`backend/app/retrieval.py:63`, `MIN_CONTENT_WORDS = 3`, counted after stop-word removal:

```
'What is a Geographical Indication?'  -> ['geographical','indication']  -> TOO VAGUE
'What is ABS?'                        -> ['abs']                        -> TOO VAGUE
'Why not?'                            -> []                             -> TOO VAGUE
```

Confirmed in Run 2 by direct HTTP call — refused in **0.02 s**, no model involved, so it cannot
be blamed on a weak model. It cost test 17 on Run 1 and test 18 question 3 on both runs.
"What is a GI?" and "What is ABS?" are questions a judge is very likely to type.

Behind it sits a second-order problem: the guard runs **after** `contextualise()`
(`generation.py:277` then `:289`), so it is meant to be the safety net under a failed rewrite —
but when the rewrite silently no-ops it refuses anyway, with no knowledge that history existed.
Gemini masked this by rewriting well; it did not fix it.

### 2. The relevance gate invents corpus gaps once a session has history — **new, Run 2**

Established by direct A/B: the same two questions are **refused with history** and **answered
confidently standalone**.

| question | in a 6–8 turn session | standalone |
|---|---|---|
| "Can I trademark the name of my Ayurvedic product?" | `out_of_scope` — *"trademark law… is not covered by the provided corpus"* | **answered**, `high` 0.85, Trade Marks Act ss.9 & 12 |
| "Can I copyright the text of my Ayurvedic formulation booklet?" | `out_of_scope` — *"the provided corpus contains no provisions regarding copyright law"* | **answered**, Copyright Act s.13(1)(a) |

Ground truth: **118 Trade Marks Act 1999 chunks, 102 Copyright Act 1957 chunks.**

The gate appears to be describing the conversation's topics rather than the corpus. This is the
most serious behavioural defect in the evaluation because it is a confident, specific,
checkable falsehood about the system itself — and it gets more likely the longer a demo runs.

### 3. Litigation advice on a live dispute — **new, Run 2, and a regression**

Test 14. Run 1 refused; Run 2 answered *"You may initiate a suit for infringement in a court
not inferior to a District Court under Section 104…"*. No outcome was predicted, every
statement is sourced, and the disclaimer is present — but nothing declined, and `escalate` is
`false`, so the user is not pointed at a practitioner. This is the single output in the
evaluation most likely to be read as legal advice.

### 4. Right category, wrong subject matter — **new shape, Run 2**

Gemini fixed all three Category 2 classification failures and then answered two of them off
target. Test 7 (a cosmetic) is answered entirely through Section 3(p) patent law — the exact
thing the checklist warned against — and its step 1 contradicts the `cosmetic` badge printed
directly above it. Test 6 (a food supplement) leads with turmeric's non-patentability before
reaching the FSSAI route that actually answers the question.

Run 1's failure was *"I won't tell you what this is"*. Run 2's is *"I know what this is and I'll
answer a different question about it"*. The second is more useful and less obviously wrong,
which arguably makes it more dangerous in a demo.

### 5. Single-source answers, and a confidence bucket that is never used — **architectural**

`confidence.py:53-54`: `HIGH_THRESHOLD = 0.75`, `MODERATE_THRESHOLD = 0.45`. Across **~50
answers over two models, `LIMITED` / "Thinly supported" never appeared once.** The worst answer
produced — unsourced headline, two of three steps abstaining, on a known corpus gap — scored
**0.50**. In practice the badge has two states, not three.

The rest of the confidence machinery is working and visibly non-constant: 0.5 on a corpus gap,
0.6–0.75 on single-source answers, 0.85–0.95 on well-corroborated ones, and the single-source
cap firing with an explicit reason string. It is the bottom bucket that is unreachable.

Related: Gemini answers rest on fewer sources than MiniMax's (test 1: 1 citation vs 3), which
pushes more answers into the single-source cap.

### 6. Flagship variance on the one question that matters most — **Run 2**

Two cold runs of *"Can a classical churna from a First Schedule text be patented?"* both got the
classification and Section 3(p) right, but one named TKDL as the defensive route and one said
*"the evidence does not provide a protection route"* — from the same retrieved chunk, which
contains the TKDL sentence in both runs. For the demo question this matters: TKDL is the part
that wins the room.

### 7. Model chatter still reaches the user — **architectural**, both models

The literal phrase **"the cited source"** is spliced mid-sentence in answers from both models
(Run 1: tests 5, 6, 10; Run 2: tests 4, 6, T20alt and others), sometimes several times in one
step — *"…habitat and collection details the cited source."* Correctness is unaffected; it
looks broken. `COMPARISON_REPORT.md` §6.15 logged this class; it is still present.

### 8. Latency and reliability improved substantially on Gemini

Median query **~12 s → ~5 s**. The suite completed with **zero** upstream failures, versus Run
1's 502 and ten `gate_unavailable` refusals. Gemini's free tier enforces a per-minute rate
limit, which produced 13 automatic fallbacks to `gemini-3.1-flash-lite` and some 35–52 s
outliers — all absorbed by the existing retry/fallback code, none surfaced to the caller.

### 9. What is working, and is worth saying out loud

- **185 citations verified across two models. Zero fabricated. Zero excerpt mismatches. Zero
  dangling references. Zero rejected.** This is the strongest result in the evaluation and it
  held across a model swap, which is exactly what you want from a guard.
- **Every jurisdiction refusal was correct in both runs**, including the US/FDA question and
  the TRIPS question, always with zero citations and no leakage of Indian law.
- **Both §6.1 and §6.2 regressions are genuinely fixed**, re-verified with the original repros
  against both configurations.
- **Fail-closed under outage works** — Run 1 refused ten times rather than answering unguarded.
- **The disclaimer was present on every single response** in both runs, including abstentions
  and the greeting.
- **The retry/fallback path is now proven**, not theoretical.

---

## Test-by-test artifacts and how to reproduce

**Artifacts committed alongside this report:**

| file | contents |
|---|---|
| `TEST_RESULTS_RAW.json` | Run 1, MiniMax — 40 raw HTTP interactions |
| `TEST_RESULTS_RAW_GEMINI.json` | Run 2, Gemini — 48 raw interactions (40 suite + 7 follow-ups + T21b) |
| `tests/run_checklist.py` | the suite runner |
| `tests/run_checklist_followups.py` | the targeted probes (F1–F4, T20alt, vagueness) |

**Reproduce Run 1 (OpenRouter / MiniMax) — needs free-tier quota:**

```
cd backend
IPSAKTI_RATE_LIMIT_QUERY=0 IPSAKTI_RATE_LIMIT_COMPARE=0 \
  ../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
.venv/Scripts/python.exe tests/run_checklist.py results.json
```

**Reproduce Run 2 (Gemini):**

```
cd backend
OPENROUTER_API_KEY=$GEMINI_API_KEY \
IPSAKTI_OPENROUTER_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/ \
IPSAKTI_MODEL=gemini-3.5-flash-lite \
IPSAKTI_FALLBACK_MODELS='["gemini-3.1-flash-lite"]' \
IPSAKTI_RATE_LIMIT_QUERY=0 IPSAKTI_RATE_LIMIT_COMPARE=0 \
  ../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
.venv/Scripts/python.exe tests/run_checklist.py results_gemini.json
.venv/Scripts/python.exe tests/run_checklist_followups.py followups.json
```

Rate limiting must be disabled or the limiter (12 queries/minute) rejects the suite. Restart
the backend before quoting latency — the in-process answer cache returns sub-second "answers"
that were generated earlier. **Test 21 requires two restarts**, one before each run, or the
second ask is a cache hit.

**Still not testable, and why:**

| item | why |
|---|---|
| Test 22 (a real international answer) | `data/corpus/03_international/` is empty by design; deferred phase |
| Test 20 as literally written | a correctly working jurisdiction gate will always refuse a TRIPS question, so it can never produce a confidence badge — the in-scope substitute (T20alt) is the right form of this test and should replace it in the checklist |
| Test 19 through the UI | tested at the API layer on the same `excerpt` field the UI renders, across all 185 citations rather than the 2–3 a manual click-through would reach |

**Two housekeeping items carried forward from `CLAUDE.md` §6j, neither fixed by this run:**

- **The OpenRouter key exposed by the §6.1 traversal hole has still not been rotated.** The hole
  is closed; the key is unchanged. Adding a second OpenRouter key does not retire the first.
- Confidence remains **uncalibrated** against labelled data. This run shows the score is
  *responsive* — 0.5 on a corpus gap versus 0.95 on a corroborated answer — which is more than
  could be said before, but responsiveness is not calibration.
