# IP-SAKTI Sahayak — project status

**Branch:** `feature/prototype1` · **Last verified:** cold backend, rate limiting disabled

This file is the honest state of the build: what was added, what was found broken and
why, and what is *still* broken. It is deliberately short on celebration. If you are
picking the project up, read this, then `CLAUDE.md` for the full engineering history and
`README.md` to run it.

> **Standing rule this project is judged on:** every factual claim about the law must
> trace to a real chunk in the corpus. Nothing here is hardcoded legal content — where
> the corpus cannot answer, the product says so.

---

## 1. What was built

### Export readiness report — `/export`, `backend/app/export_readiness.py`

The headline feature. One product, two jurisdictions, side by side: what Indian law
requires before it can be made, protected and shipped, and what the international corpus
says about placing it in a named market. Free-text market, short form, cited checklist,
ordered action plan.

It reuses the existing pipeline rather than duplicating it — `classify`, `retrieve` (with
its relevance gate), `validate_ids`, `strip_unsupported_provisions`, `confidence.assess`,
`escalation.assess` — so fixes made elsewhere cannot drift away from it.

Three properties are enforced **in code**, not requested in a prompt:

| property | how |
|---|---|
| no country is hardcoded | a test greps the module for country and regulator names and fails if one appears |
| status is derived, not claimed | `_settle_status` overrides the model: no surviving citation forces `NOT_COVERED`, and nothing reaches `VERIFIED` without one |
| the two corpora never mix | citations are validated per item; a real, retrieved chunk from the wrong corpus is dropped, and an item left with nothing becomes `NOT_COVERED` |

Measured, and the contrast is the feature:

```
Germany   EU Directive 2004/24 -> simplified registration, applicant establishment,
          labelling. 11 sources, 0 rejected, 0 jurisdiction leaks.
Brazil    target section NOT COVERED - "does not contain any instruments, treaties, or
          regional frameworks that reach Brazil".
```

### Key Takeaway banner

A one-line orientation above the reasoning. The never-a-bare-yes/no rule is **structural,
not advisory**: `schemas.TAKEAWAY_LABELS` is a closed per-intent vocabulary of hedged
labels, and `generation._build_takeaway` replaces anything outside it with "Requires
verification". A model returning "Yes, patentable" cannot put those words on the page.
The reason sentence is citation-checked like a reasoning step; one naming an unretrieved
provision drops the whole banner. Definitional questions ("What is a GI?") get no banner —
there is no matter to take a view on, and a label would invent one.

### Evidence-support gauge

Replaces `Partly supported (internal score 0.83, uncalibrated)`. A semicircular dial whose
needle rests on the **middle of a band and never between two** — the scale is ordinal and
uncalibrated, so an arbitrary angle would imply a resolution this measurement does not
have. Four bands: Thin evidence · Some support · Well supported · Strongly supported.

The raw score is gone from the user-facing view **including the accessibility tree**,
where it had survived as "(internal score 0.87, uncalibrated)" — showing screen-reader
users a false precision sighted users were spared. It now sits behind
`localStorage.ipsakti.dev = "1"`.

### The reasoning trail as four sealed volumes

Closed, a volume shows only its numeral, its seal and its title. Four paragraphs of legal
prose shown at once is four paragraphs nobody reads; the closed shelf **is** the summary —
one argument in four ordered parts — and opening one is the reader's choice about where to
look. Two rows of two; an opened volume takes ~767px of its own row while its row-mate
folds to a spine, and the other row does not move.

Opening a volume **lights that step's sources in the citation rail and dims the rest**.
That is the product's whole claim rendered as one gesture: you can see, without reading a
word, which provisions the sentence in front of you stands on.

### A dark surface, site-wide

A paper/dark switch in the site header (also `Shift+D`, ignored inside text fields),
applying to Consult, Export readiness, Treaty routes and Sources. First visit follows
`prefers-color-scheme`. It is a genuine re-skin — no sheet, no ruling, glass panels over a
lit ground — done by overriding the design tokens under one class, so components re-skin
themselves and none takes a theme prop. Colour still means what it means: haldi is the
classification verdict, indigo is sources, neem is grounded, clay is a limit.

The **landing page is excluded on purpose**: it is a fixed composition (dark hero,
deliberately light garden), not a switchable workspace.

### Provision graph — `backend/app/graph.py`, links on every source card

Statutes are a graph, not a list. A source card now carries the provisions that
passage **refers to** and the provisions that **refer back to it**, each with the
sentence it was read from.

The links are extracted from the passage's own text by pattern. **No model is
involved anywhere in this module**, which is the whole point: a relationship a
model proposes is a relationship it can invent, and this build's entire claim is
that nothing reaches the reader the corpus does not say.

```
575 provisions · 602 cross-references · 330 linked passages · 0 dangling links
built in ~1s at startup, reported and verified at /health
```

Coverage is a property of the law, not a setting: 46.7% of statute chunks and
16.5% of the D&C Rules carry at least one link, and across five real questions
7 of 14 cited passages showed connections.

**Deliberately not fed into retrieval.** Feeding graph-linked passages into the
prompt was built, measured on six questions, and turned off — it helped three
and hurt three, including the flagship. `graph_expansion_slots = 0`, the
measurement is recorded in the config comment, and a unit test asserts the zero
so the decision cannot be reversed by accident.

### Orchestration trace — "How this answer was assembled"

Every answer and every refusal now carries the five stages that ran, what each
one decided, and what it cost:

```
Classify formulation · expand query      ok   4996ms  classical_generic · 4 search formulations
Retrieve · scope and jurisdiction gate   ok   3791ms  12 passages · in scope
Generate the four-step trail             ok   2270ms  google:gemini-3.5-flash-lite
Validate every citation                  ok     39ms  3 of 3 steps sourced · 0 citations rejected
Score evidence support                   ok      3ms  Strongly supported · 2 citations
```

"12 passages, in scope" is worth reading; "retrieval: ok" is not. It is attached
to refusals too — a refusal is the hardest thing to take on trust, and the trace
is what shows the scope gate *ran and decided* rather than the model declining.

Collapsed by default: it is provenance, not the answer.

### The audit trail is readable — `GET /audit`, panel on Sources

`audit.py` has logged every question, refusal and export report since Phase 11.
Nothing surfaced it. It is now on the Sources page: the counters, the retention
statement, the names of the fields removed before serving, and the last 40 rows.

The design point is **two gates, not one**. Consent decides what is *written*;
`PERSONAL_FIELDS` decides what is *served* — the question, the resolved question
and the product are stripped on the way out even when they were consented into
the file. The summary reports `retained_question_text` as a **count**, because
the claim being made is "the default retains nothing" and a count is the number
that would falsify it.

### Smaller additions

- **Treaty routes** back on their own page (`/treaties`), separate from Export readiness —
  a lane answers *what an instrument says*, the report assesses *a product against one*.
- **The pointer is the logo's leaf**, replacing the system arrow entirely (a real `cursor`
  image, not a lagging follower element).
- **Escalation produces something.** It used to open a `mailto:` with an *empty recipient* —
  a draft addressed to nobody, which looks like a working referral. It now copies a
  prepared brief: question, reasoning, every source with its provision, and why a
  practitioner was suggested.

---

## 2. Issues found, and what was done

Ordered by how much they mattered.

### 2.1 Three of six classification anchors pointed at the wrong law

**The worst thing found.** Each category is anchored to the corpus chunk that *defines*
it. That chunk is injected into the classifier prompt under the heading "statutory
definitions, quoted verbatim from Indian law", shown to users as "Defined by …", and added
to the set of ids an answer may cite. Startup verification reported no problems.

```
patent_proprietary -> a Siddha/Unani formulary BOOK LIST
ayurveda_aahar     -> a food-additive schedule (citric acid)
new_drug           -> an Ethics Committee clinical-trial proviso
```

Two independent causes:

1. The selector was *"the shortest chunk containing the phrase"*. A term appears in more
   places than the clause defining it, and schedules are short, so schedules won.
2. `excerpt()` truncates from character zero. For a 4,000-character chunk the model saw
   the first 750; the new-drug definition sits ~1,800 in, so it was **never shown the
   definition at all**. Same failure as the relevance gate in CLAUDE.md §6c — the text was
   there and the window could not reach it.

**Fixed** by anchoring on the defining clause's own wording rather than the term
(`"formulations containing only such ingredients"`, not `"patent or proprietary
medicine"`), preferring a candidate with a defining cue beside the phrase, and excerpting a
window **centred on the phrase**. `verify_anchors()` now checks what is actually *shown*,
which is the check that would have caught it.

All six now resolve to and display the right provision — s.3(a), s.3(h), rule 122E
"Definition of new drug", Schedule Y 1.1, regulation 2(b), s.3(aaa). Classification
measured **5/5** on one product per category. `test_subject_scope` and `test_gate_scope`
both went from a sub-total to full afterwards; those were not variance, they were this.

*Detail worth keeping:* "means" is **not** used as a cue. The D&C Act extraction carries
the margin bleed described in CLAUDE.md §3 and renders it `mneans` in the definitions
clause.

### 2.2 Off-domain questions were being answered — 0/5, reproducible

> Q: *What is the best marketing strategy for my ayurvedic startup?*
> SEARCHED AS: *compliance standards for advertising and claims of ayurvedic drugs*
> GATE: `relevant=True` — "asks for business strategy **and regulatory compliance**"

`expand_query` manufactured a legal question out of a business one, and §6k's own fix —
showing the gate the SEARCHED AS lines — is what made the gate trust the rewrite. Fixed at
the gate, where the user's question is authoritative: rewrites are search vocabulary, and
**the subject matter is the user's question, never the rewrites**. **0/5 → 5/5** refused as
`out_of_scope`, positive controls intact (trade mark 4/4 answered from the Trade Marks Act).

This was pre-existing; §6m recorded it as "free-model variance" after a lucky
re-measurement. It was not variance.

### 2.3 Citation metadata — the D&C Rules named a provision on 11% of its chunks

The reported symptom was "most Drugs and Cosmetics Rules citations show *provision not
identified*". The first guess — a heading-format mismatch — was the smallest of three
causes. The largest was `_unreliable_numbers`, which banned any heading number repeating
more than three times in a document: in this document that banned 1–14 and 23 outright,
discarding **316 correctly detected real rules** in order to suppress schedule paragraphs.

Replaced with a structural **provision spine** — a statute's numbers ascend through the
document while schedule numbering restarts, so the longest ascending chain of detected
headings is the provision body, and chunks between two chain members inherit the earlier
number. Four guards, each added because the unguarded version produced a real mis-citation
(a positional bound, same-printed-page carry, a structural-divider break, and an
enumerated-list detector).

```
Drugs & Cosmetics Rules 1945   11.2% -> 20.3%   (provision body alone 58.4%)
patents act 1970               62.1% -> 92.3%
Geographical Indications Act   77.6% -> 95.5%
Trade Marks Act 1999           74.6% -> 89.8%
corpus total                   50.7% -> 55.9%
```

Two acts went *down*; both are correctness gains (AFI ingredient lists — "3. Bala (Rt.)
144 g." — were being cited as "Section 3"). **No vector-DB rebuild was needed**: the
displayed provision is derived at request time from `chunk_text`.

### 2.4 Evidence support could not tell a pinpoint citation from a page number

Every sampled answer sat in the middle band. Nothing in the score could distinguish
`Geographical Indications Act, Section 11` from `D&C Rules 1945, provision not identified,
p.1` — both are "a surviving citation from one act". Added a **specificity** component,
and counted breadth in **distinct provisions rather than acts** (counting acts capped a GI
answer citing Sections 2, 3 and 11 of the GI Act as "resting on a single source"). Caps
became ceilings so each weakness costs what it is worth.

Same captured inputs, rescored: GI `0.80 Partly supported → 0.95 Strongly supported`;
phytopharmaceutical, the known corpus gap, `0.50 → 0.367 Thin evidence`.

### 2.5 Legal-accuracy corrections

- **TKDL never described as conferring protection.** It is a defensive prior-art
  mechanism; examiners search it to refuse wrongful applications.
- **"International Patent Office" eliminated (2/6 → 0/6).** This needed a *code guard*,
  not just a prompt rule, because the phrase is in the corpus itself — `About TKDL.pdf`
  reads "misappropriation at International Patent Offices", so a model answering
  faithfully reproduces it. `normalise_institutions()` rewrites model prose only;
  **citation excerpts stay verbatim.**
- **Section 3(p) is no longer applied to anything merely Ayurvedic.** Before, a
  self-invented turmeric emulsion got *"no patent protection route is available"*. After:
  *"not automatically barred by Section 3(p) … assessed on its own novelty, inventive step
  and … 3(d) … 3(e)"*, with the Indian Patent Office named as the route.

### 2.6 Static copy asserted law with no citation

Home's category blurbs and the treaty lane captions shipped as static strings with no
citation and no validator — *"Prior approval of the National Biodiversity Authority is
required before IPR on biological resources"*, *"minimum IP standards WTO members must
meet"*. That is the fabricated-authority failure the pipeline exists to prevent, wearing a
caption's clothes. All 22 strings now name a subject and invite the question; the legal
content arrives from retrieval with its provision attached. A guard greps both files for
assertive forms and **self-tests that it would catch the original sentence**.

Deliberately kept: *"PCT, Madrid and Nagoya sit in a separate corpus"* and *"Section 3(p)
is retrieved from this layer"* are claims about **this system**, both backed by passing
tests.

### 2.7 Smaller correctness fixes

| issue | fix |
|---|---|
| `/export` claimed US FDA texts "are not in this corpus and are declined" | false — the FDA botanical-drug guidance **is** in the corpus (35 chunks). Corrected. |
| Escalation opened a `mailto:` with an empty recipient | replaced with a copied practitioner brief |
| README claimed benchmarks 94/94 | corrected to the measured 92/94, with a note to re-run |
| The claims checkbox rendered a whole sentence in letterspaced caps | it is a `<label>` inside `.readiness-field` and inherited the field-name style |
| Treaty lane CTA used **clay**, which means "a limit or a refusal" | moved to indigo, which means sources |
| Landing page went cream-on-cream in dark mode | the garden section hardcodes a cream background with `color: var(--ink)`; the landing page no longer takes the surface class |

---

### 2.8 The graph resolved four families of reference to the wrong law

Every one of these produced a link that *resolved cleanly and pointed at the
wrong provision* — worse than no link, because it looks checked. All four were
found by auditing samples of the edges, not by reading the code.

| what happened | why | fix |
|---|---|---|
| `"section 4 of the Trade and Merchandise Marks Act"` inside the Designs Act became Designs Act s.4 | matching the reference's noun to the document is not enough — both say "section" inside an Act | `_OTHER_INSTRUMENT` drops a reference followed by "of the / of that / of said"; `_SELF_INSTRUMENT` keeps "of this Act" |
| `"sections 3 and 6"` yielded only 3 | the pattern matched one number per noun | `_LIST_CONTINUATION`, but only after a **plural** noun, and the list is gathered *before* the instrument test so "sections 4 and 5 of the Trade Marks Act" loses both, not one |
| `"the Biological Diversity Rules 2024"` became a reference to rule 202 | `\d{1,3}` truncated the year, so the existing year guard was handed "202" and passed it | `(?!\d)` inside the pattern — the guard has to be in the regex, not after it |
| the Ayurvedic Formulary's `"SECTION 10 VATI AND GUTIKA"` linked to `"10. Sadananda Sharma, Rasatarangini"` (its bibliography) | the provision spine will place any ascending numerals, and a formulary, a practice manual and a treaty table of contents all have some | `LINKABLE_REGIMES` — the graph runs only over documents whose numbered provisions *are* their structure. Keeps 602 of 641 edges; removes every family the audit found wrong |

Alongside those, a link target must be a chunk that actually **shows** the
provision's heading, not merely one the spine placed by inheritance.

### 2.9 Refusals carried no trace

The four abstention paths returned before the trace was attached, so the one
answer a reader is least willing to take on trust had no evidence that anything
had run. All four now carry it, and the vagueness screen records itself as a
skipped stage — so "did it even try?" has a visible answer.


### 2.10 The citation guard was deleting correct sentences

Found by a judge-style pass over questions the build had never seen. On
*"Is the name of a traditional Kerala herbal oil eligible for GI protection?"*
the **Legal position step shipped empty** — the most important step on the page.

`provision_support` asks whether the provision named in a sentence occurs in the
retrieved text. Statutes do not print their own sub-clause numbers: the GI Act
reads `11. Application for registration.-(1) Any association of persons...`, so
the string `11(1)` occurs nowhere. Three **correct** references —
`Section 2(1)(e)`, `Section 11(1)`, `Section 11(2)(a)` — were therefore called
invented, and every sentence carrying one was removed.

The fix is deliberately narrow. A sub-clause reference is also supported when a
retrieved chunk **is** that provision (per the provision spine) **and** carries
that clause marker. Accepting the base number alone would have re-opened exactly
the hole §2.x closed: a chunk merely *mentioning* section 3 would then support a
fabricated "Section 3(e)". Here the chunk has to be section 3 itself.

Measured on the same question, before and after:

```
before   step 2 EMPTY · unsupported_provisions: 2(1)(e), 11(1), 11(2)(a)
         evidence support: moderate / "Some support"
after    step 2 cites Section 2(1)(e); step 3 cites Section 11
         unsupported_provisions: []   ·   support: high / "Well supported"
```

Four unit tests pin both directions, including the one that must never pass: a
chunk that only *mentions* a section does not support its sub-clause.


### 2.11 Both print paths opened a blank tab and did nothing

Found while verifying the new readiness sheet, and the same bug was already
shipped in the consultation briefing.

```js
window.open("", "_blank", "noopener,noreferrer")   // returns null
```

`noopener` makes `window.open` return **null** by specification, so the handle
needed to write the sheet never arrived, `if (!win) return` swallowed it, and
the user got an empty tab. Measured in Chromium: with `noopener,noreferrer`
&rarr; `null`; without &rarr; a handle.

The security property `noopener` exists to provide is kept a different way: the
document is one we compose ourselves, it loads nothing external, and it severs
its own `window.opener` before anything else runs.

*Worth remembering: a feature that fails by doing nothing looks exactly like a
feature nobody clicked.*


## 3. Current issues and known bugs

Nothing here is hidden. Read this section before demoing.

### The graph

- **The flagship shows no graph links.** Its decisive citation is the Manual of
  Patent Office Practice — a practice guide, excluded above on purpose. Fixing
  it means resolving references *across* documents, which needs a way to say
  which document "the Trade and Merchandise Marks Act" is. Doing that by hand
  would be authored legal knowledge; deriving it from `act_subtype` is plausible
  and unaudited, so it is a next step rather than a footnote.
- **Treaties are outside the graph.** They number by Article, and the noun
  helper calls anything without "rules" in its name a Section, so a treaty's
  table of contents resolves against itself. Fixing that changes citation
  *display* across 825 international chunks — a separate decision.
- `/audit` has no access control, like the rest of this build. It serves no user
  content, which is why exposing it locally is safe; a deployment needs storage
  with access control and a retention policy.

### Retrieval

- **Compound questions dilute.** *"Can I patent it, and what licence do I need?"* retrieves
  only D&C licensing rules, so the (correctly ordered) patentability sentence has to say
  the evidence is silent. A **pure** patentability question retrieves 3(d)/3(e)/3(o)/3(p)
  correctly. The fix is §6m's reserved-slots pattern applied to expansion formulations; not
  taken because it changes core retrieval and needs its own measurement.
- **"What is ABS?"** reaches food and drug regulation rather than the Biological Diversity
  Act on roughly 1 run in 3.
- **Patents Act s.3(p) is unreachable by search.** The margin-bleed extraction damage is
  too severe; the Manual of Patent Office Practice is cited instead, which states the
  provision *and* names TKDL. Better citation anyway, but the statute itself is lost to
  search.
- **~184 near-duplicate chunks** from the Biological Diversity Rules 2024 being ingested
  twice. Accepted deliberately (§6g): removing a PDF renumbers every document after it.

### Model and quota

- **Free-model output is not deterministic.** `test_flagship` scores TKDL naming at 4/5 or
  5/5 depending on the run. Re-run suites before demoing rather than trusting a past green.
- **The answer cache makes a suite lie.** A bad flagship run in `e2e_api` populated the
  cache and `benchmarks` then scored that same answer at `0.0s`. **Any suite reporting a
  sub-second answer is reusing one — restart before quoting a number.**
- Gemini's free tier is 15 requests/minute and has a daily cap. When every provider is
  capped the app returns `gate_unavailable` rather than answering ungated — that is the
  fail-closed behaviour working, not a bug.

### Not calibrated

- **Evidence support is uncalibrated.** It is now demonstrably *responsive* across four
  bands, which is not the same thing. There is no labelled data. Do not claim otherwise.

### Environment

- **The machine is the fragile part.** The backend needs ~1.5 GB and this laptop has
  8.4 GB total; it has been OOM-killed by Windows several times during development, always
  while a browser was open. Close browsers before demoing.
- **Hindi is partial.** BM25 tokenises Devanagari to `[]`, so Hindi questions fall back to
  dense-only retrieval and answers come back in English. Query expansion masks the recall
  loss, which means the degradation is invisible.

### Security

- **The OpenRouter key exposed by the §6j path-traversal bug has still not been rotated.**
  The hole is closed; the key is still compromised. This is the one item on this list that
  is not a trade-off — it just needs doing.

### A trap that has bitten three times

Writing a regex through a shell heredoc has repeatedly turned `\b` into a literal `0x08`
BACKSPACE byte, producing a pattern that **compiles, looks perfect in every rendering, and
matches nothing**. It has silently disabled a guard three times in this project. Two
defences exist and both are worth keeping: `tests/test_units.py` sweeps every backend and
test module for control characters, and any new guard should carry a self-test proving it
would catch the thing that prompted it.

---

## 4. How to verify

```bash
# one process serves the API and the built UI
cd frontend && npm run build && cd ..
IPSAKTI_RATE_LIMIT_QUERY=0 IPSAKTI_RATE_LIMIT_COMPARE=0 \
  ./.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --port 8000
# http://127.0.0.1:8000
```

Last measured, cold backend:

```
tests/test_units.py            190/190     tests/test_jurisdiction.py        10/10
tests/test_security.py          25/25      tests/test_jurisdiction_compare.py 12/12
tests/test_gate_scope.py        16/16      tests/test_style_and_steps.py      21/21
tests/test_subject_scope.py     11/11      tests/e2e_api.py                   39/39
tests/test_legal_advice.py      15/15      tests/benchmarks.py                92/94
tests/test_flagship.py           3/4       UI regression (Playwright)         23/23
frontend  tsc --noEmit clean · npm run build clean · control-character sweep clean
```

`test_flagship`'s missing point is TKDL naming at 4/5 — the documented free-model variance.
Measured separately across 5 cold runs the flagship scored Section 3(p) 5/5, TKDL 5/5,
`classical_generic` 5/5.

---

## 5. Where the history went

`COMPARISON_REPORT.md`, `TEST_RESULTS.md`, `TEST_RESULTS_PREVIOUS.md`,
`COMPARE_VERSIONS_PROMPT.md` and `docs/CLAUDE_CODE_PROMPT.md` were removed as superseded.
Their findings are recorded in `CLAUDE.md` §6g, §6j and §6k, and the files themselves remain
in git history at **`9095ca9`** and earlier. Some source comments still cite them by name as
the evidence for a fix; that is why they are worth being able to find.

`TEST_RESULTS_RAW*.json` (~750 KB) are the raw evidence behind those deleted reports and are
now orphaned. They were left in place rather than deleted unasked.

**Still current:** `CLAUDE.md` (the engineering history and the shared source of truth,
updated at the end of every phase), `README.md` (setup), `PROJECT_BRIEF.md` (the official
problem statement), `MANUAL_TEST_CHECKLIST.md`, and the two pipeline notes under `docs/`.
