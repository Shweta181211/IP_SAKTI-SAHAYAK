# IP-SAKTI Sahayak — what it does, why, and how to defend it

> **Read this before the round.** `CLAUDE.md` is the full engineering history and
> `PROJECT_STATUS.md` is the honest state of the build. This file is neither: it is
> what you need in your head to answer a hard question in twenty seconds.
>
> Nothing in here is a claim you cannot demonstrate on the running app.

---

## Part 1 — The one-sentence version

> It answers Indian IP and regulatory questions about Ayurvedic products, and **every
> substantive sentence it prints is traceable to a real passage in a real statute** —
> because a sentence that loses its source is removed before you see it, not flagged
> afterwards.

If you say only one more thing, say this:

> The hard part is not answering. The hard part is **refusing correctly** — and you can
> watch it do that.

---

## Part 2 — What is on the screen, and what each thing is for

| Surface | What it is | Why a judge should care |
|---|---|---|
| **Key takeaway banner** | A hedged verdict from a **fixed vocabulary** | The model *cannot* print "Yes, patentable". The words are chosen by code, not by the model |
| **Evidence support gauge** | A four-band dial | Computed **after** validation, from what survived. Not a similarity score |
| **Four sealed volumes** | The reasoning trail | Closed, they are the summary. Opening one **lights that step's sources and dims the rest** |
| **Source cards** | The verbatim statute | You read the law yourself instead of trusting us |
| **"N connected"** on a card | The provision graph | Where that provision points, and what points back — quoted, not asserted |
| **"How this answer was assembled"** | The orchestration trace | Seven stages, what each decided, what it cost |
| **Citation guard panel** | Rejections and strips | The guard is *visible*. A guard you cannot see is a guard nobody believes |
| **Export readiness** | India → target market checklist | Ten fixed areas. A gap is **shown**, not missing |
| **Sources page** | Registries, orchestration, graph, audit | Where the "is this real?" questions get answered |

---

## Part 3 — The five things that make this hard to copy

### 1. Citation validation is a *choke point*, not a warning

Three layers, and each one is enforced in code:

1. The prompt sees retrieved evidence and nothing else.
2. `validate_ids()` — an id must be **both** a real chunk **and** one we actually showed
   the model. Not one or the other. Both.
3. `_build_steps()` — a step with no surviving citation has its **content replaced**.

If nothing survives at all, the whole answer degrades to an abstention rather than
shipping unsourced prose.

**And there is a fourth layer people forget:** `provision_support()` checks that
*"under Section 3(e)"* written in a **sentence** is backed by a chunk that contains
Section 3(e). A valid citation sitting next to an invented provision number is worse
than an invalid id — it *looks* sourced. Measured: on 2 of 6 cold runs the model named
a section that appeared in none of the retrieved evidence. That sentence is now removed.

> **If asked "how do you know it doesn't hallucinate?"** — Don't say "we prompt it well".
> Say: *a citation that does not resolve to a retrieved chunk is a rejection, and the
> rejections are printed on the page.* Then show the citation-guard panel.

### 2. The two jurisdictions are separated in **code**, not in a prompt

- Chroma is queried with a jurisdiction filter.
- **BM25 has one index per jurisdiction**, not one index filtered afterwards — because
  IDF is computed over whatever corpus the index was built on. A single mixed index
  would rank by a document frequency that describes neither legal system.
- The side-by-side comparison validates **citation ownership per side**: a point's
  Indian citations must resolve to Indian chunks and its international ones to
  international chunks. A point that cannot satisfy that is rejected, not softened.

> **If asked "what stops it answering an Indian question from a treaty?"** — *The two
> corpora are indexed separately and every comparison point is checked for which side
> its sources came from. It is a property we test, not an instruction we give.*

### 3. Abstention has **kinds**, and each is a different answer

| Ask this | You get | Why it matters |
|---|---|---|
| "FDA approval to sell in the USA?" | `foreign_jurisdiction` + offers a human | A scope boundary, not a topic miss |
| "What price beats my competitors?" | `out_of_scope`, does **not** offer a human | Nothing legal was asked |
| "Will I win if I sue?" | `legal_advice` | On-subject — the Patents Act does govern infringement — but nothing was *asked* that law can settle |
| "trademark" | `too_vague`, **before any model call** | Deterministic, costs nothing |
| "hello" | Answered normally | Small talk is not a refusal |

The first version got these wrong in a specific way worth knowing: a chocolate-cake
question was told it was "governed by another country's law". Subject matter is now
judged **before** jurisdiction.

> **If asked "does it just refuse everything it's unsure about?"** — *No — it refuses
> for four different reasons and the UI renders each differently. Watch: same product,
> four questions, four different refusals.*

### 4. The provision graph has **no model in it**

Nodes are provisions the corpus proves exist. Edges are cross-references read out of
each passage's own text by pattern. **No model proposes a relationship**, so none can
be invented. Every link on screen shows the sentence it was read from.

Three things it deliberately does **not** do, and the reason is the same each time —
*it would be our legal judgement, not the statute's words*:

- It does not resolve references **across** documents ("section 4 of the Trade and
  Merchandise Marks Act"), because deciding which document that is requires knowledge
  the corpus does not state.
- It does not run over the pharmacopoeia or the practice manual, where the numbers are
  recipes and paragraph numbers rather than provisions.
- It does not feed into retrieval. That was built, measured on six questions, and
  **turned off** — it helped three and hurt three, including the flagship.

> **If asked "isn't the knowledge graph just a buzzword here?"** — *It is 575 provisions
> and 602 cross-references, built in a second at startup, verified at /health, and it
> is deterministic — no model touches it. And we turned off the part that did not
> measure well rather than shipping it for the demo.*

### 5. Auditability and privacy are **two gates**, pulling opposite ways

- Consent decides what is **written**. The operational record — what was decided, how
  many sources survived, which model answered — is always written. The **question text**
  is written only on opt-in.
- `PERSONAL_FIELDS` decides what is **served**. The question is stripped on the way out
  **even when it was consented into the file**.
- `retained_question_text` is reported as a **count**, not a flag — because the claim is
  "the default retains nothing", and a count is the number that would falsify it.

> **If asked about DPDP / data protection** — *Two tiers. The audit trail carries no
> user content by default, and the reading endpoint strips it again even when it is
> there. You can read the rows on the Sources page and check.*

---

## Part 4 — The orchestration, in the order it runs

One question is **seven decisions**, not one call:

```
  1  Classify the formulation      6 categories, anchored to the statutory definition
  2  Expand the query              user's words -> statutory vocabulary
     (1 and 2 run CONCURRENTLY — both depend only on the question)
  3  Gate scope + jurisdiction     fails CLOSED: no model, no answer
  4  Retrieve and fuse             dense + BM25, per jurisdiction, RRF
  5  Generate the four-step trail  sees the evidence and nothing else
  6  Validate every citation       reject ids, replace unsourced steps, strip
                                   invented provisions
  7  Score evidence support        over what SURVIVED, not what was retrieved
```

**Model access is a chain of six endpoints across three providers**, tried best-first.
A per-minute limit is waited out; a **daily cap is recognised as unwaitable** and the
whole provider is skipped — retrying it would only add dead air. Failover went from
~48s to ~5.4s when that distinction was added.

> **If asked "is this just a ChatGPT wrapper?"** — open **"How this answer was
> assembled"** on any answer. Seven stages, each with what it decided and what it cost.
> Then say: *the model writes one of those stages. The other six are what make its
> output safe to print.*

> **If asked "what happens when your API key runs out?"** — *It fails closed. You get
> "I could not run the check, try again" — never an answer the scope gate did not
> approve. That is deliberate: an honest refusal is a worse demo and a better legal tool.*

---

## Part 5 — Export readiness, and why the *gap* is the feature

Input: product, ingredients, category (optional), health claims, target market.

Output: two checklists, ten fixed areas.

| India side | Target market |
|---|---|
| Manufacture and licensing | Regulatory pathway |
| Patent, trade mark and GI | Ingredient restrictions |
| Biodiversity and benefit sharing | Health-claim restrictions |
| Labelling, packaging and claims | Labelling and packaging |
| Records, documents and certifications | IP protection in that market |

Each line carries a status the **server derives**, never one the model assigns:

- **Checked** — the evidence states the requirement and what satisfies it
- **Needs verification** — it applies, but not that this product meets it
- **Potential blocker** — something that would bar this route
- **Not covered** — this corpus does not settle it

Two properties enforced in code, not requested in the prompt:

1. **Nothing about a country is hardcoded.** No market table, no pre-written paragraphs.
   A test greps the module for country and regulator names — **including in comments** —
   and fails if one appears.
2. **Status is derived.** No surviving citation forces "not covered"; nothing reaches
   "checked" without one.

**The demo that wins this section:** run the same product to two markets.

```
A market inside EU Directive 2004/24   5/5 India areas grounded
                                       5/5 target areas grounded, 12 sources
A market no instrument reaches         5/5 India areas grounded
                                       5/5 target areas NOT COVERED, with the reason
```

> *"None of these instruments contain specific regulatory requirements for that market."*

> **If asked "why doesn't it know about Japan?"** — *Because our corpus holds treaties
> and regional instruments, not every country's domestic marketing law — and it says so
> instead of guessing. Any tool that produced a confident Japanese checklist from this
> corpus would be making it up.*

**Print / save as PDF** produces a sheet with every source printed verbatim at the back,
built from the report object rather than the page — so what prints cannot drift from
what was validated.

---

## Part 6 — Hard questions, with answers

**"Why not just use GPT-4 / a bigger model?"**
A bigger model writes better prose. It does not make a citation resolvable. The three
validation layers are what make the answer safe, and they work identically whichever
model is behind them — which is why this runs on a free endpoint today and would run on
Sonnet 5 with a one-line config change.

**"Your confidence score — is it calibrated?"**
**No, and we say so on the page.** It is *responsive* — it moves across four bands on
real inputs, and every band is reachable — but there is no labelled dataset to calibrate
it against. That is why the raw number is hidden from users and the meter is ordinal.
Claiming calibration we have not measured would be exactly the kind of overreach this
build exists to avoid.

**"What's your accuracy?"**
Citation accuracy we can state: across the benchmark suites, **every citation an answer
prints resolves to a chunk that was actually retrieved** — re-verified by the test suite
independently of the code that produced it. Answer *quality* is bounded by a free model;
the guards make it safe, not brilliant.

**"What if the corpus is wrong or out of date?"**
Then the answer is wrong, and it will be wrong *with a citation you can check* — which
is the difference between this and a chatbot. Every card shows the source and the page.
The Sources page links the official registries so a reader can verify against the live
text.

**"Show me it failing."**
Ask it something with a false premise: *"Which section of the Patents Act permits
patenting a formulation taken from the Ashtanga Hridaya?"* It does not agree, and it
does not refuse — it **corrects the premise while citing Section 3(p)**. That is the
behaviour that is hard to build.

**"What's still broken?"**
Read them out; owning them is stronger than being caught:
- Confidence is uncalibrated.
- Compound questions dilute retrieval — *"can I patent it AND what licence do I need?"*
  retrieves the licensing half well and the patent half thinly.
- Hindi falls back to dense-only retrieval, because BM25 tokenises Devanagari to nothing.
- The flagship answer shows no graph links, because its decisive source is a practice
  manual we deliberately excluded from the graph.

---

## Part 7 — Numbers to have in your head

| | |
|---|---|
| Corpus | **3,282 chunks, 37 PDFs** — 2,457 national, 825 international |
| Instruments | 26 Indian + 11 treaties/regional |
| Provision graph | **575 provisions, 602 cross-references, 0 dangling** |
| Endpoint chain | **6 endpoints, 3 providers** |
| Stages per question | **7** |
| Readiness areas | **10** (5 India + 5 target) |
| Test suites | units 229 · security 25 · e2e 39 · gate scope 16 · legal advice 15 · subject scope 11 · style 21 · flagship 4 · benchmarks 94 |

---

## Part 8 — Ten minutes before the demo

```
1. Close every browser tab.        The backend needs ~1.5 GB and this laptop has 7.78 GB
2. Restart the backend.            Cold — a warm cache reports 0.0s and looks like a lie
3. python tests/demo_check.py      Verifies health, warms the cache, checks the flagship
4. Open http://127.0.0.1:8000      One process serves the API and the built UI
```

**Running order** — each question demonstrates something different:

1. A patentability question → the trail, the sources, the takeaway
2. A trade mark question → *a different regime, so it is not one hardcoded answer*
3. A follow-up: *"can we protect the name we sell it under?"* → conversation memory
4. A false premise → refuses the premise **while citing**
5. A US/FDA question → `foreign_jurisdiction`, offers a human
6. A pricing question → `out_of_scope`, does **not** offer a human
7. Export readiness to a covered market, then an uncovered one → **the gap**
8. Sources page → orchestration, the graph, the audit trail

**Do not** fire the test suites back to back before demoing — the free tier's per-minute
limit will trip and you will spend the first question watching a fallback.
