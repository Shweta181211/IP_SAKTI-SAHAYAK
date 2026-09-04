# IP-SAKTI Sahayak — Version Comparison Report

**Compared:**
- **Version A (mine):** `D:\IP_SAKTI-SAHAYAK`
- **Version B (teammate's):** `D:\IP-SAKTI-HER`

**Method:** both versions were started locally and queried over HTTP with identical
questions. Version A ran on `:8000`, Version B on `:8100`. Every claim below is from
observed behaviour or from reading the code that produces it. Where I could not run
something, I say so explicitly.

> **Important caveat on fairness.** Version B's optional LLM path requires an
> `ANTHROPIC_API_KEY`. No `.env` exists in that folder, and the only key we have is an
> **OpenRouter** key, which her code cannot use (it imports the `anthropic` SDK directly).
> So Version B was necessarily tested on its **default, no-key path** — which is what her
> own `.env.example` documents as the normal mode of operation: *"The application runs
> without this key using source-grounded retrieval summaries."* If she has a working
> Anthropic key on her own machine, her LLM path may perform materially better than what
> is recorded here, and that section of this report should be re-run before any final
> decision.

---

## 1. Functional completeness

| Capability | A (mine) | B (teammate's) |
|---|---|---|
| Backend calls an LLM to generate the answer | **Yes** — every query, via OpenRouter | **Optional and off by default**; requires an Anthropic key that is not present |
| Default answer text is model-generated from corpus | **Yes** | **No** — templated prose from `_plain_summary()` |
| Classification into the 6 PS categories runs automatically | **Yes** — LLM classifier, 8 outcomes | **No** — the user picks a category from a dropdown; it is a *retrieval filter*, not a classification step |
| Retrieval queries a real vector DB | **Yes** — Chroma, 2,335 chunks | **Yes** — Chroma, 2,335 chunks (**identical DB**) |
| Citations traceable to real corpus chunks | **Yes**, validated post-generation | **Yes** for the source list; **but** answer prose is not tied to them |
| Reasoning trail as distinct steps | **Yes** — 4 steps, each separately cited | **No** — a single prose block |

### The decisive difference

Version B's normal path does not generate an answer. `backend/rag_engine.py::_plain_summary()`
returns **pre-written English/Hindi prose** with a real source list appended. Observed output
for the official benchmark:

> *"**Probable answer:** the retrieved materials are relevant, but the result depends on the
> product's composition, intended use, and the exact claims."*

That sentence is returned for **any** query that reaches the generic branch — it appeared
verbatim for the churna question, for "how do I make a chocolate cake", and for the US/FDA
question. It is a template, not an answer.

### Hardcoded content found in Version B

Three places produce authored legal text rather than corpus-derived text:

1. **`_plain_summary()` keyword special case** (`rag_engine.py` ~line 455):
   ```python
   is_patent_extraction = ("patent" in lowered_query and "extract" in lowered_query)
   ```
   This returns a fully hand-written multi-paragraph answer about **Ashwagandha extraction
   patentability** — including bulleted legal requirements — for any query containing both
   "patent" and "extract". The text is not drawn from the corpus and carries no citation for
   its substantive claims. This is exactly the kind of test-query special-casing the brief
   rules out, and it is the single most serious finding against Version B.

2. **`FORMULATION_CATEGORIES[*]["posture"]`** — each of the six categories carries authored
   legal prose (e.g. *"Faces the Section 3(p) patenting bar … defended through the TKDL"*).
   The law stated is correct, but it is **written by us, not retrieved**, and is surfaced to
   the user as the "Probable answer" whenever a category is selected. A judge asking "where
   did that sentence come from?" has no source to point at.

3. **`ABS_TRIGGER_TERMS`** — a 30-entry keyword list (English + Hindi) driving the ABS/TKDL
   flag. Defensible as a visible heuristic, and the code comments own the choice, but it is
   keyword matching and will not generalise to unseen phrasing.

Version A has no equivalent. Its only authored strings are UI chrome, abstention messages and
the disclaimer — never legal content.

---

## 2. Correctness against the official PS benchmark

**Query:** *"Can a classical churna from a First Schedule text be patented?"*

### Version A — passes on all four criteria

```
classification : classical_generic
headline       : "No, a classical churna from a First Schedule text cannot be
                  patented as such under Indian law."
step 2         : "Under Section 3(p) of the Patents Act, 1970, an invention that in
                  effect is traditional knowledge, or is an aggregation ..."
step 3         : names TKDL as the defensive route
step 4         : Indian-law-only jurisdiction note
citations      : MANUAL OF PATENT OFFICE PRACTICE, Sections 3(o), 3(p), p. 98
                 patents act 1970, Section 29, p. 25   (+7 more)
```

| Criterion | Result |
|---|---|
| Correct classification | ✅ `classical_generic` |
| Cites Section 3(p) | ✅ in prose **and** on the citation card |
| Names TKDL as defensive route | ✅ |
| Structured as separate steps | ✅ 4 distinct, individually cited steps |

### Version B — fails on all four

```
answer     : "**Probable answer:** the retrieved materials are relevant, but the result
              depends on the product's composition, intended use, and the exact claims."
confidence : medium
sources    : MANUAL OF PATENT OFFICE PRACTICE, p.97
             patents act 1970, 29. Anticipation by previous publication.—(1) An
             invention claimed in a complete specification, p.25
```

| Criterion | Result |
|---|---|
| Correct classification | ❌ none performed (user must pick from a dropdown) |
| Cites Section 3(p) | ❌ retrieved **Section 3(l)** (artistic works) and s.29 (anticipation) |
| Names TKDL | ❌ |
| Structured as separate steps | ❌ single prose block |

**Also visible above: a citation-rendering defect.** Version B prints the raw
`section_or_clause` metadata field, which in this corpus contains footnote and heading text
roughly 40% of the time. The result is a citation that reads:

> *patents act 1970, 29. Anticipation by previous publication.—(1) An invention claimed in a
> complete specification, p.25*

That is a sentence fragment presented as a statutory reference. Version A derives the section
from the chunk text and verifies it is present before display, and falls back to *act + page*
when it cannot (measured: 887/2342 chunks get a verified section, **0 contaminated**).

### Unexpected inputs (3 queries neither version was tuned on)

| Query | Version A | Version B |
|---|---|---|
| *"How do I make a good chocolate cake at home?"* | **Abstains** — `out_of_scope`, "this is a cooking/recipe question" | **Answers**: confidence `medium`, *"the retrieved materials are relevant"* + 6 D&C Rules sources |
| *"Can I sell my ayurvedic supplement in the USA under FDA rules?"* | **Abstains** — `foreign_jurisdiction`, "governed by another country's law" | **Answers**: confidence **`high`**, cites FSSAI Ayurveda Aahar Regulations |
| *"hello"* | **Abstains** — `too_vague`, blunt and unhelpful | **Handles gracefully**: a proper capability introduction |

The middle row is the most serious. Version B rates a **US regulatory question as *high*
confidence** and answers it from Indian food regulations. The PS requires jurisdictions be
"never conflated"; this is the failure mode that requirement exists to prevent.

The third row is a genuine win for Version B and is worth porting (see §Recommendation).

---

## 3. Code quality and maintainability

### Version A

**Strengths.** Nine focused modules with one responsibility each (`config`, `schemas`,
`llm`, `corpus_index`, `citations`, `retrieval`, `classification`, `generation`, `main`).
All tuning values live in `config.py`. `schemas.py` is the single API contract, mirrored by
`frontend/src/types.ts`. Adding international jurisdiction is genuinely staged: the enum,
the request field, the metadata filter and the UI toggle all already exist and are wired —
only the corpus is missing.

**Weaknesses.** `generation.py` is ~340 lines and now carries orchestration, prompt, cache
and validation; the orchestration deserves its own module. Prompts are large string
constants inline rather than versioned templates. `retrieval.py` imports `llm` inside
functions to dodge a circular import — a smell worth resolving.

### Version B

**Strengths.** `main.py` is genuinely clean and small (~90 lines) and serves the frontend
from the same process, so there is nothing to configure and no CORS to get wrong — a real
deployment advantage. Comments explain *why*, consistently and well. The `audit_log.jsonl`
with per-session consent, and `run_eval.py` + `eval_set.json`, show discipline Version A
partly lacks.

**Weaknesses.** `rag_engine.py` is **32 KB in one file** holding categories, trigger lists,
thresholds, conversation handling, sub-question splitting, two answer generators, audit
logging and orchestration. Legal prose is embedded in Python constants, so a lawyer cannot
review or correct the wording without editing code. Thresholds are inline module constants,
and the code honestly admits they were "not calibrated against a labelled evaluation set".
Adding international jurisdiction would mean touching many parts of that one file.

### Duplicate logic across the two versions

Both contain their own copy of `build_chunks.py`, `build_vector_db.py` and
`test_retrieval.py` — byte-identical in the parts that matter. Whichever base is chosen,
these should exist once.

---

## 4. UI / UX

*(Ranked last in importance, per the brief.)*

| | Version A | Version B |
|---|---|---|
| Stack | React 19 + TypeScript + Tailwind, Vite | Vanilla JS + hand-written CSS |
| Reasoning trail | 4 numbered stations on a vertical rule; hovering a step highlights exactly its sources | Single prose block; sources listed below |
| Citation display | Cards with verified section, page, and expandable **verbatim statute text** | Source list; raw `section_or_clause` (see §2 defect) |
| Loading state | Skeleton trail + "Classifying, retrieving provisions, verifying citations…" | Present |
| Error states | Typed abstention panels per kind; network errors restore the user's text | Present, simpler |
| Disclaimer | On every response | Present in the page chrome |
| Conversation history | Yes, collapsible, persisted to `localStorage` | Not observed |
| Confidence indicator | **No** | **Yes** — high/medium/low/none |
| Escalate to human | **No** | **Yes** |
| Audit log + consent toggle | **No** | **Yes** |
| Greeting / capability handling | **No** (says "too vague") | **Yes** |

Version A is the stronger interface for the graded criterion — it makes citation
traceability *visible* rather than asserted. Version B has four PS-relevant features that
Version A lacks entirely.

---

## 5. Scope adherence (PROJECT_BRIEF Part C)

Part C explicitly defers: international jurisdiction, multilingual/Bhashini, **confidence
indicator**, **human-facilitator escalation**, knowledge graph, agentic orchestration, PDF
export, TKDL similarity flagging.

**Version A** stays inside scope. The international toggle is visible but returns an honest
refusal; nothing deferred is half-built.

**Version B** ships four deferred items — confidence indicator, escalation, an ABS/TKDL
pointer, and partial Hindi support. Assessment of each:

- **Confidence indicator — built, but not trustworthy.** It is a raw distance threshold. The
  code says so honestly ("a starting heuristic … not calibrated against a labelled
  evaluation set"). I measured the same signal on this corpus during Phase 1 of Version A:
  in-corpus top-1 distances span 0.2469–0.3598 and out-of-corpus 0.3696–0.3951 — **they
  overlap**, and a nonsense query ("purple bicycle quarterly tax rebate") scores closer than
  several genuine benchmark questions. This is why the US/FDA question was rated **high**
  confidence. A confidence badge that is wrong in the dangerous direction is worse than no
  badge, because it invites the user to trust a mis-jurisdiction answer.
- **Escalation** — low risk, works, small.
- **ABS/TKDL flag** — keyword-driven; will miss unseen phrasing.
- **Hindi** — real, but retrieval degrades silently: BM25 is absent in her design and the
  corpus is English, so Hindi questions rely on dense similarity alone.

So Version B is out of MVP scope, and the flagship out-of-scope feature is actively
misleading in its current calibration.

---

## 6. Critical self-audit — flaws and gaps in MY version (Version A)

### Confirmed working
- No API key in frontend source or in the built bundle (`grep` over `frontend/dist` returns 0).
- `.env` is gitignored and verified absent from every tracked file.
- CORS is scoped to the two Vite dev origins, `allow_credentials=False`, methods limited to GET/POST.
- Input validation: `{"question":""}` → 422; wrong type → 422; `top_k: 999` → 422; oversized → 422.
- Frontend `catch` blocks mean a dead backend shows "backend offline", not a crash.
- Conversation memory **does** work — follow-ups are rewritten server-side ("what about trademarking it?" → "Can I trademark my secret cough medicine formula?"), and a change of subject is correctly *not* inherited.

### Real defects and gaps

1. **The relevance/jurisdiction gate fails OPEN.** In `retrieval.py::llm_relevance_gate`, an
   `LLMUnavailable` error returns `(True, …)` — the question proceeds. During an OpenRouter
   outage or a 429 storm, out-of-scope and **foreign-jurisdiction questions would be
   answered**. Citation validation still holds, so nothing is fabricated, but the strongest
   safety property silently degrades exactly when the service is unhealthy. There is no
   user-visible signal that the gate did not run.

2. **Whitespace-only input returns HTTP 200.** `{"question":"   "}` passes `min_length=1`
   and is caught downstream by the vagueness guard. Behaviour is safe (abstains
   `too_vague`), but the API should reject it at validation.

3. **Latency is a demo risk.** 17–40 s per cold query, three sequential model round trips.
   The cache makes repeats instant, but a judge asking a *new* question waits ~25 s with no
   streaming and no progressive output. Restarting the backend clears the cache.

4. **Output is not deterministic.** Free-model routing varies. Across development I observed
   the same query returning `ANSWER` on one run and `ABSTAIN` on the next. Benchmarks are a
   snapshot, not a guarantee.

5. **No confidence indicator, no escalation path, no audit log.** All three are named in the
   PS "Expected solution". All three are deferred by Part C, so this is scope-compliant — but
   Version B has them and we do not.

6. **`needs_clarification` still over-fires.** Mitigated by a declared
   `answer_depends_on_category` contract, but it remains model-dependent. Benchmark F4 demos
   as a clarifying question rather than a direct answer.

7. **Hindi degrades invisibly.** `corpus_index.tokenize()` matches `[a-z0-9]` only, so BM25
   contributes **0.00** for Devanagari input; retrieval silently falls back to dense-only.
   Nothing tells the user the hybrid half is inert.

8. **Greeting/small-talk handling is poor.** "hello" returns a blunt *"That is too short for
   me to search on"*. Version B does this properly.

9. **The classification anchor set is hand-maintained.** Six `DEFINITION_ANCHORS` chunk IDs
   are pinned in code. `verify_anchors()` catches drift loudly at startup, but a corpus
   rebuild that shifts IDs requires a manual fix.

10. **Missing from MVP scope:** nothing in Part C is unimplemented. The core loop —
    classify → retrieve → 4-step cited trail → citation cards + disclaimer — is complete.

### Not a defect, but worth stating
There is **no mock or placeholder data anywhere** in Version A. Every citation resolves to a
real chunk in `all_chunks.json`; the benchmark suite re-verifies this independently of the
code that produced it (94/94 criteria, 24/24 end-to-end checks, 0 fabricated citations).

---

## 7. Dataset / vector DB completeness check

Both versions share the same corpus and the same `all_chunks.json`, so **every finding here
applies equally to both**.

- **Total chunks in JSON: 2,342.** Indexed in Chroma: **2,335** (7 skipped as <3 words — all
  bare Schedule M headings such as *"5. Garments"*, *"12. Documentation"*; no legal content lost).
- **Jurisdiction tag: set on 100% of chunks** (`national` × 2,342, zero missing). ✅
- **`03_international`: correctly absent.** ✅

### Per-folder breakdown

| Folder | Chunks |
|---|---|
| `01_classification` | 882 |
| `02_national_statutes` | 738 |
| `04_registries` | 384 |
| `05_pharmacopoeia` | 338 |

All four expected folders are represented. ✅

### 🔴 Defect 1 — one PDF produced ZERO chunks: **`About TKDL.pdf`**

26 PDFs are on disk and the extraction log reports *"PDFs processed: 26 … PDFs needing manual
review: none flagged"*. But only **25 `doc_id`s** exist in the chunks — **`DOC016` is missing
entirely**.

`DOC016` is `04_registries/About TKDL.pdf`. It is **not** a scanned PDF — it extracts 5,464
characters of clean text. The loss is a **chunking bug**:

`pipeline/build_chunks.py` drops any page matching a table-of-contents pattern, including a
bare `\bCONTENTS\b`. This document's only page contains the ordinary sentence:

> *"…systematically and scientifically converting and structuring the available **contents**
> of the ancient texts on Indian Systems of Medicines…"*

The word "contents" in running prose trips the filter, the single page is discarded, and the
document contributes nothing. **The pipeline then reports success**, because it only flags
extraction failures, not documents that end with zero chunks.

This matters beyond bookkeeping: TKDL is central to the official benchmark answer, and the
one document dedicated to explaining TKDL is absent from the index. Both versions currently
answer TKDL questions from the *TKDL Access Policy* and the Manual of Patent Office Practice
instead.

**Fix:** require the TOC pattern to match a page *heading* (anchored, or `^\s*CONTENTS\s*$`)
rather than any occurrence, and add an assertion that every processed PDF yields ≥1 chunk.

### 🟠 Defect 2 — duplicate ingestion: **Biological Diversity Rules 2024**

The same instrument is ingested twice, from two folders:

| doc_id | folder | chunks |
|---|---|---|
| `DOC007` | `02_national_statutes` | 92 |
| `DOC024` | `04_registries` | 90 |

The two files are **not byte-identical** (2,470,317 vs 2,414,630 bytes) — they are different
copies of the same Rules. The result is ~182 near-duplicate chunks, about **7.8% of the whole
index**. Observable consequence: retrieval returns the same provision twice in one result
set (during Phase 3 testing, *"25. Factors to be considered while determining quantum of
penalty"* appeared at both rank 1 and rank 2). This wastes evidence slots and inflates any
apparent corroboration.

**Fix:** keep one copy, ideally the more complete file, and re-run the pipeline.

### 🟡 Defect 3 — suspiciously thin extraction: **`TKDL Access Agreement.pdf`**

`DOC021`: **2 chunks from 3 pages, average 135 tokens** — the lowest density in the corpus.
Worth opening manually to confirm nothing substantive was lost.

### Per-document table

| doc_id | chunks | pages | avg tok | document |
|---|---|---|---|---|
| DOC001 | 75 | 34 | 262 | Drugs and Cosmetics Act, 1940 |
| DOC002 | 12 | 5 | 341 | FSSAI Ayurveda Aahar Regulations, 2022 |
| DOC003 | 795 | 463 | 274 | The Drugs and Cosmetics Rules 1945 *(16 near-empty)* |
| DOC004 | 20 | 11 | 328 | Biological Diversity (Amendment) Act 2023 |
| DOC005 | 30 | 19 | 242 | Patents Rules 2024 |
| DOC006 | 51 | 22 | 250 | The Biological Diversity Act, 2002 |
| DOC007 | 92 | 38 | 361 | The Biological Diversity Rules 2024 🟠 |
| DOC008 | 102 | 44 | 268 | The Copyright Act, 1957 |
| DOC009 | 31 | 13 | 281 | The Designs Act, 2000 |
| DOC010 | 8 | 5 | 238 | Drugs and Magic Remedies Act, 1954 |
| DOC011 | 61 | 25 | 251 | Geographical Indications Act, 1999 |
| DOC012 | 65 | 26 | 260 | Plant Varieties and Farmers Rights Act, 2001 |
| DOC013 | 116 | 46 | 271 | Trade Marks Act 1999 |
| DOC014 | 162 | 61 | 237 | patents act 1970 |
| DOC015 | 48 | 26 | 272 | ABS Guidelines |
| **DOC016** | **0** | — | — | **About TKDL.pdf 🔴 MISSING** |
| DOC017 | 14 | 5 | 454 | Kandhamal Haladi |
| DOC018 | 12 | 3 | 406 | Lakadong Turmeric |
| DOC019 | 197 | 138 | 257 | MANUAL OF PATENT OFFICE PRACTICE |
| DOC020 | 9 | 4 | 426 | Madurai Marikolunthu |
| DOC021 | 2 | 2 | 135 | TKDL Access Agreement 🟡 |
| DOC022 | 7 | 6 | 310 | TKDL Access Policy |
| DOC023 | 5 | 3 | 299 | BD (Amendment) Rules 2025 |
| DOC024 | 90 | 38 | 360 | The Biological Diversity Rules 2024 🟠 |
| DOC025 | 220 | 196 | 265 | Ayurvedic Formulary of India (AFI) |
| DOC026 | 118 | 103 | 304 | Ayurvedic Pharmacopoeia of India Vol-I |

---

## Verdict

**Version A is functionally stronger, and the gap is not close on the criteria the PS grades.**

The decisive facts, all observed rather than inferred:

1. Version A **generates** answers from retrieved law. Version B, on the path that actually
   runs, returns templated prose — the same sentence for a churna question, a chocolate cake
   and a US FDA question.
2. Version A **classifies automatically**, which the PS requires. Version B asks the user to
   classify their own product, which is the question they came to ask.
3. Version A **passes the official benchmark on all four criteria**. Version B fails all
   four: no classification, retrieves §3(l) not §3(p), no TKDL, no step structure.
4. Version A **abstains correctly** on out-of-scope and foreign-jurisdiction questions.
   Version B rated a US regulatory question **high confidence** and answered it from Indian
   food law.
5. Version B contains **hardcoded legal prose**, including a keyword-triggered hand-written
   answer about Ashwagandha and six authored "posture" paragraphs. Version A has none.

This is a "working prototype" hackathon submission, and the brief ranks a working backend
above visual polish. Version B's genuine strengths — a tidier deployment story, an audit log,
an eval harness, graceful greetings — are real, but they sit on top of a system that does not
answer the benchmark question.

### Recommendation: **(a) take Version A as the base, and port five specific pieces from Version B**

Not a merge. The two differ at the architectural level — Version B has no classification step
and no generation step to merge *into*, so a merge would mean rewriting her `rag_engine.py`
against Version A's contracts, which is more work than porting the parts worth having.

**Port these, in priority order:**

| # | From Version B | To Version A | Why | Effort |
|---|---|---|---|---|
| 1 | `_GREETING_ONLY` / `_CAPABILITY_ONLY` + `_conversation_response()` (`rag_engine.py` ~L168–215) | new early branch in `generation.answer_question()`, before `is_too_vague` | Fixes a real Version A weakness: "hello" currently gets *"too short for me to search on"*. Hers answers properly. Deterministic, no API call. | ~30 min |
| 2 | `run_eval.py` + `eval_set.json` | alongside `tests/benchmarks.py` | A second, independently authored eval set is worth more than more of my own cases. Re-point it at Version A's `/query` contract. | ~1 h |
| 3 | `log_interaction()` + `audit_log.jsonl` + the consent toggle | new `backend/app/audit.py` | The PS asks for audit and DPDP-aligned privacy. Hers is small, local-only and consent-gated — a good design to adopt wholesale. | ~1 h |
| 4 | Escalation affordance (`escalate` flag → UI) | `Answer` schema + `AbstentionPanel` | PS "path to escalate to a human IP facilitator". Natural fit on Version A's existing abstention panels. | ~45 min |
| 5 | Serving the frontend from FastAPI (`StaticFiles` mount in her `main.py`) | Version A's `main.py`, for the deploy build | One process, one port, no CORS. Materially simpler to demo and to host. | ~30 min |

**Explicitly do NOT port:**
- `_plain_summary()` and the `FORMULATION_CATEGORIES[*]["posture"]` prose — authored legal
  text with no source, the exact thing the citation guard exists to prevent.
- The `is_patent_extraction` Ashwagandha special case — hardcoded answer to a test-shaped query.
- The **confidence indicator as implemented** — distance-thresholded, and measured on this
  corpus to overlap between in-corpus and out-of-corpus queries. If we want a confidence
  signal (it is deferred by Part C anyway), it must be built on the fused hybrid score plus
  the relevance gate's own verdict, not on raw distance.
- `ABS_TRIGGER_TERMS` keyword list — replace with the existing classification result if an
  ABS pointer is wanted.

### Fix in both versions, immediately (shared corpus bugs)

1. **`About TKDL.pdf` → 0 chunks.** Loosen the TOC regex to an anchored heading match, and
   assert every PDF yields ≥1 chunk. Re-run `build_chunks.py` + `build_vector_db.py`.
2. **De-duplicate Biological Diversity Rules 2024** (~182 redundant chunks, 7.8% of the index).
3. **Inspect `TKDL Access Agreement.pdf`** — 2 chunks from 3 pages looks thin.

### What to do about her work, practically

The honest framing for the team: her ingestion pipeline **is** the shared foundation — both
vector DBs are byte-for-byte equivalent because we both ran her `build_chunks.py` and
`build_vector_db.py`. That is not a small contribution; it is the corpus the entire project
stands on. The divergence is only in the application layer above it, and the five ports above
are real, named, creditable pieces of her work carried into the merged base.


---

## Addendum — what has been fixed since this report was written

Everything below was found by the comparison above and has since been repaired in
**Version A**. Re-verified end to end: `benchmarks.py` 94/94, `e2e_api.py` 24/24.

### Shared corpus (affects both versions — teammate should pull these pipeline fixes)

| Finding | Status |
|---|---|
| `About TKDL.pdf` produced zero chunks (§7 Defect 1) | **Fixed.** Contents-page pattern anchored to its own line and now also requires several headings on the page. Corpus **2,342 → 2,457 chunks** (+115 — the filter had been over-firing on other documents too). The recovered document now ranks **#1** for a TKDL query. |
| Pipeline reported "processed" for a zero-chunk PDF | **Fixed.** A PDF that extracts text but yields no chunks now logs a WARNING and is listed in the summary. Silent data loss was the real bug. |
| Duplicate Biological Diversity Rules 2024 (§7 Defect 2) | **Open, deliberately.** Removing a PDF renumbers every document after it; stacking that on the same rebuild was not worth the risk. Should be its own change. |
| `TKDL Access Agreement.pdf` thin extraction (§7 Defect 3) | **Open** — still 2 chunks from 3 pages, worth a manual look. |

### Newly discovered while fixing the above — worth telling the teammate

**`chunk_id` was not stable, and not even consistent between machines.** `doc_id` is assigned
by enumeration position, so the rebuild moved `patents act 1970` DOC014 → DOC005 and Section
3(p) `DOC019_chunk_112` → `DOC020_chunk_116`. Worse, `sorted()` on `Path` case-folds on
Windows but not on Linux, so the same corpus produced **different chunk ids depending on who
ran the pipeline**. Fixed by sorting on the lowercased POSIX relative path. Anything that
pins a chunk id — in either version — is fragile; resolve by content instead.

### Version A self-audit items (§6)

| Finding | Status |
|---|---|
| Relevance/jurisdiction gate failed **OPEN** during an LLM outage | **Fixed.** Now fails closed with a distinct `gate_unavailable` abstention telling the user to retry. |
| Whitespace-only question returned HTTP 200 | **Fixed.** `StringConstraints(strip_whitespace=True, min_length=2)` — now 422. (`Field(strip_whitespace=...)` is silently ignored in Pydantic v2, which is why the first attempt did nothing.) |
| Poor greeting handling | **Fixed** by porting the teammate's approach — `backend/app/conversation.py` answers greetings, capability questions and thanks deterministically, before any API call. |
| Pinned `DEFINITION_ANCHORS` chunk ids | **Fixed.** Anchors resolve by act name + distinctive phrase; `verify_anchors()` still fails loudly at startup. |
| Long paragraph answers | **Fixed.** `Answer.headline` gives a one-sentence direct answer; the UI clamps each step to ~2 sentences with a "Show full reasoning" toggle. |
| No confidence indicator / escalation / audit log | **Still open** — deferred by Part C. The recommended ports (items 3 and 4 in the table above) have not been done yet. |
| Latency 17–40 s; non-deterministic output | **Still open** — inherent to the free model. Cache makes repeats instant. |
| Hindi degrades silently (BM25 scores 0 on Devanagari) | **Still open.** |
