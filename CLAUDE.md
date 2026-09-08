# IP-SAKTI Sahayak — Project Context

> **This file is the shared source of truth for the project.** It is updated at the end of
> every build phase. If you are picking up this repo (human or Claude Code session), read
> this first — it saves you re-deriving the state of the world.

---

## 1. What we are building

**IP-SAKTI Sahayak** — a RAG-based, source-cited AI assistant for Intellectual Property and
regulatory guidance in Ayurveda. Built for **SIH 2026 (internal round)**.

The full official problem statement is in `PROJECT_BRIEF.md`. Read Part A before writing any
answer-generation logic.

### The core loop (MVP scope — `PROJECT_BRIEF.md` Part C)

```
User question
  -> Classify the formulation (1 of 6 regulatory categories, or "not applicable")
  -> Retrieve relevant chunks from the corpus (jurisdiction-filtered)
  -> Generate a 4-step reasoning trail, each step citation-backed:
       1. Classification            2. Legal position
       3. Protection/action route   4. Jurisdiction note
  -> Display with visible citation cards + "information, not legal advice" disclaimer
```

### Non-negotiables (these are graded by the PS, not nice-to-haves)

1. **Citation-only.** Every substantive claim traces to a real chunk in our corpus.
2. **No fabricated authority.** The model may never invent a statute, section, or case.
   A citation that does not resolve to a retrieved chunk is a *rejection*, not a warning.
3. **Safe abstention.** Out-of-scope or under-evidenced questions must produce an explicit
   "I do not have a source for that" — never a plausible guess, never a silent failure.
4. **Standing disclaimer.** "Information, not legal advice" appears on every response.
5. **Generalisation.** No keyword matching or special-casing around our own test queries.
   Any in-scope Ayurveda IP/regulatory question must work.

### Explicitly deferred (do NOT build until the core loop is confirmed)

International jurisdiction (toggle visible but disabled) · multilingual/Bhashini ·
confidence indicator · human-facilitator escalation · knowledge graph · agentic
orchestration · PDF export · TKDL similarity flagging.

---

## 2. Repository layout

```
CLAUDE.md              # this file — shared context, updated every phase
README.md              # setup + run instructions
PROJECT_BRIEF.md       # the official PS, MVP scope, tech stack, phase plan

backend/
  requirements.txt     # API + retrieval + generation deps
  app/
    config.py          # paths, model IDs, thresholds — SINGLE SOURCE OF TRUTH
    schemas.py         # Pydantic contracts (the frontend depends on these)
    corpus_index.py    # loads Chroma + BM25 once at startup
    citations.py       # citation normalizer + validator  <- anti-hallucination gate
    retrieval.py       # hybrid dense+lexical retrieval
    classification.py  # 6-category formulation classifier
    generation.py      # Claude call + citation validation
    main.py            # FastAPI app

pipeline/              # corpus ingestion (built by Person B, already run)
  requirements.txt     # PDF/OCR deps only
  build_chunks.py      # PDF -> structured chunks
  build_vector_db.py   # chunks -> ChromaDB embeddings
  test_retrieval.py    # standalone retrieval sanity script (dev tool, NOT app code)

data/
  corpus.zip           # 26 source PDFs — the source of truth, committed
  corpus/              # extracted PDFs                        (gitignored)
  chunks/              # all_chunks.json + .csv — committed, shared artifact
  raw_text/            # per-page extracted text               (gitignored)
  logs/                # extraction_log.txt
  vector_db/           # ChromaDB persist dir                  (gitignored, rebuildable)

frontend/              # Vite + React + Tailwind
tests/                 # benchmark + robustness suites
docs/                  # pipeline and vector-DB notes
```

**Why `data/` is partly gitignored:** `corpus/`, `raw_text/` and `vector_db/` are all
regenerable from `data/corpus.zip` + `pipeline/`. Only the irreplaceable input
(`corpus.zip`) and the expensive shared artifact (`chunks/`) are committed.

---

## 3. The corpus — facts you need before writing retrieval code

**3,282 chunks** from **37 PDFs** - 2,457 national (26 Indian legal/regulatory documents) and
825 international (11 treaties and regional instruments, added in §6l). All extracted cleanly with
pdfplumber; none needed OCR, none failed. Zero encoding corruption (no U+FFFD).

Chunk sizes: median 242 tokens, max 798, none over 900. 157 chunks are under 50 tokens.

### Metadata schema (every chunk)

| Field | Notes |
|---|---|
| `chunk_id` | e.g. `DOC005_chunk_011` — **this is the citation key**. Never hardcode one; resolve by content (§6g) |
| `doc_id`, `file_name`, `folder` | provenance |
| `act_name` | 24 distinct values — use this for display citations |
| `regime_type` | 4 values: `drug_regulatory_classification`, `ip_statute`, `registry_guideline`, `pharmacopoeia_reference` |
| `act_subtype` | 11 values: `patent`, `trademark`, `copyright`, `design`, `geographical_indication`, `plant_varieties`, `biodiversity_abs`, `traditional_knowledge`, `drug_regulatory`, `food_regulatory`, `pharmacopoeia`. **`other` is now empty** — derived from document content, not the filename (§6j) |
| `jurisdiction` | `national` (2,457) or `international` (825). **This is the separation the PS grades** - the two are indexed and retrieved apart, never mixed in one evidence set (§6l) |
| `year`, `page_number`, `page_numbers`, `token_count` | |
| `section_or_clause` | **noisy — see below** |

### Coverage by regime

`01_classification` 948 · `02_national_statutes` 768 · `04_registries` 394 ·
`05_pharmacopoeia` 347 · `03_international` **825 (populated in §6l)**

Largest sources: Drugs & Cosmetics Rules 1945 (795), Ayurvedic Formulary of India (220),
Manual of Patent Office Practice (197), Biological Diversity Rules 2024 (182),
Patents Act 1970 (162).

### Known quirks — read these before trusting the data

1. **`section_or_clause` is noisy.** Roughly 40% of values captured *footnote* text rather
   than a section heading, for example:
   `"2. Ins. by Act 21 of 1962, s.2 (w.e.f. 27-7-1964)."`
   **Never render this field raw as a citation.** `citations.py` derives a clean display
   citation from `act_name` plus a section pattern verified to actually occur in the chunk text.

2. **Margin bleed in the Patents Act extraction.** The source PDF has a vertical sidebar
   whose letters interleave into the text stream — s.3 reads
   `"... o (n) a presentation of information; C a (o) topography ... i d (p) an invention which..."`.
   The substantive provision is intact and retrievable; cosmetic only.

3. **`jurisdiction` now has two populated values.** The India/International toggle
   answers from a genuinely separate corpus on each side. Read §6l before touching
   retrieval: BM25 has one index *per jurisdiction* rather than one index filtered
   afterwards, because IDF is computed over whatever corpus the index was built on.

### Verified coverage for our benchmark queries

All five Part F benchmarks are answerable from real corpus text:

- **Section 3(p)** (the traditional-knowledge patent bar) appears **twice**: in
  `patents act 1970` (`DOC014_chunk_011`) and in the `MANUAL OF PATENT OFFICE PRACTICE`
  p98 (`DOC020_chunk_116`) — the latter explicitly names **TKDL** as the examiner's
  prior-art route, which is exactly the official "wins the room" answer.
- **Phytopharmaceutical** — D&C Rules 1945 r.122-E + Schedule Y data requirements (7 chunks).
- **Classical / First Schedule** — D&C Act 1940 s.3(a),(h) (54 chunks).
- **ABS / NBA prior approval before IPR** — BD Act 2002 + 2023 Amendment s.6 (49 chunks).
- **GI registration** — GI Act 1999 (61 chunks).

---

## 4. Stack decisions — and why (you should be able to defend these to judges)

`PROJECT_BRIEF.md` Part D is the baseline. Four deliberate deviations, all approved:

| Layer | Brief says | We use | Reason |
|---|---|---|---|
| Embeddings | `all-MiniLM-L6-v2` | **`intfloat/multilingual-e5-base`** | 768-dim vs 384 — better recall on long statutory prose. Already multilingual, so the deferred Bhashini phase needs **no re-embedding**. |
| Retrieval | dense only | **dense + BM25, fused with Reciprocal Rank Fusion** (`rank-bm25`) | Embeddings blur exact legal tokens like "Section 3(p)" and "Rule 122-E". The lexical half makes *citation* retrieval reliable — this directly serves the graded citation-accuracy criterion. |
| Generation | `claude-sonnet-4-6` via Anthropic API | **`minimax/minimax-m3:free` via OpenRouter** | Routed through OpenRouter (OpenAI-compatible). Currently on a **free** model because the account has no credits. Chosen by head-to-head test, not by guessing — see §4a. One config change moves us to `anthropic/claude-sonnet-5` when credits exist. |
| Repo | — | nested duplicate clone deleted | `IP_SAKTI-SAHAYAK/` was a 44 MB older clone of the same remote; its HEAD was an ancestor of ours. |

Unchanged from Part D: Python + FastAPI · ChromaDB (local) · Claude API ·
React + Tailwind · Vercel (frontend) + Render/Railway (backend).

**Embedding detail that bites:** E5 models require prefixes — `passage: ` when embedding
corpus chunks, `query: ` when embedding a user question. `build_vector_db.py` already does
this. App-side retrieval **must** use `query: ` or ranking silently degrades.


### 4a. Why `minimax/minimax-m3:free` - measured, not assumed

The account has no OpenRouter credits, so generation runs on a free model. Six candidates
were tested head-to-head on a real corpus task (classify + cite, with real chunk IDs):

| model | valid JSON | correct category | fabricated IDs | latency |
|---|---|---|---|---|
| **`minimax/minimax-m3:free`** | yes | yes | **0** | 3.1s |
| `nvidia/nemotron-3-super-120b-a12b:free` | **no** | - | - | 5.6s |
| `z-ai/glm-5.2:free` | HTTP 429 | - | - | - |
| `google/gemma-4-31b-it:free` | HTTP 429 | - | - | - |
| `thinkingmachines/inkling:free` | HTTP 403 (agentic harnesses only) | - | - | - |
| `deepseek/deepseek-chat-v3.1:free` | HTTP 404 (no longer free) | - | - | - |

MiniMax M3 was then tested on the behaviour that actually matters here:

| scenario | behaviour |
|---|---|
| question covered by evidence | answered, both correct citations, 0 fabricated |
| question NOT in evidence | **abstained**, empty citations |
| adversarial false premise ("cite the section that ALLOWS it") | **abstained**, refused to invent |
| out of domain ("capital of France") | **abstained** |

It abstains correctly and does not fabricate citation IDs, which is the whole ballgame.

**Operational caveats:**
- Free models are rate-limited per-provider and per-account. Two candidates returned 429
  on every attempt. Expect intermittent 429s - generation code needs retry-with-backoff
  and a fallback model, not a bare call.
- Free-tier daily request caps apply on OpenRouter for accounts without credits. Do not
  burn requests re-running full benchmark suites casually; cache results during development.
- Regardless of model, `citations.py` validation is non-negotiable. It is what makes a
  free model safe to use here, and it must not be relaxed if we later upgrade.


---

## 5. Conventions (enforced, not suggestions)

- **Citations never render raw `section_or_clause`.** Always go through `citations.py`.
- **No keyword special-casing** in classification or retrieval. If you find yourself writing
  `if "trademark" in query`, stop — that breaks the generalisation requirement.
- **Citation IDs are validated against the retrieved set** before any response ships.
  Unretrieved ID means reject the step, not warn.
- **Metadata filters are soft, not hard.** Regime bias comes from the *classification result*,
  never from scanning the query for keywords. Hard filters break unseen questions.
- **Config lives in `backend/app/config.py`.** No model IDs or thresholds inline.
- **`temperature=0`** for classification and generation — this is a legal tool, not a chatbot.

---

## 6. Phase status

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Repo structure, env, shared docs | **Done** |
| 1 | Vector DB built + verified | **Done** |
| 2 | Classification (6 categories + 2 escape hatches) | **Done** |
| 3 | Hybrid retrieval + citation normalizer | **Done** |
| 4 | Generation — 4-step trail, validated citations | **Done** |
| 5 | FastAPI `/health` `/classify` `/query` | **Done** |
| 6 | Frontend shell, input, jurisdiction toggle | **Done** |
| 7 | Reasoning-trail + citation-card components | **Done** |
| 8 | Frontend ↔ backend integration | **Done** |
| 9 | Benchmark + robustness hardening | **Done** |
| 10 | Polish + demo rehearsal | **Done** |
| 11 | Post-audit hardening (security, robustness, coverage) | **Done** — §6j |
| 12 | Post-evaluation fixes (gate scope, fabricated provisions, subject scope, confidence) | **Done** — §6k |
| 13 | International corpus, progressive jurisdiction flow, frontend merge | **Done** — §6l |
| 14 | Outage triage: key staleness, per-minute vs daily caps, comparison retrieval | **Done** — §6m |
| 15 | Citation depth, evidence-support meter, takeaway banner, card trail, export readiness | **Done** — §6n |
| 16 | Classification anchors, uncited static copy, the volumes trail, a site-wide dark surface | **Done** — §6o |

**Working agreement:** one phase at a time. Each phase ends with a summary, real verification
output, and an update to this file. No starting a phase whose dependency is not verified.

---

## 6a. Phase 1 findings - read this before writing `retrieval.py`

The vector DB is built: **2,450 chunks** in `data/vector_db/` (48 MB), collection
`ip_sakti_corpus`, model `intfloat/multilingual-e5-base`. Build took ~28 min on CPU.

7 of the 2,457 chunks were skipped as too short (<3 words). All 7 are bare Schedule M
headings from the D&C Rules ("5. Garments", "12. Documentation") with no legal content.
Nothing of substance was lost.

`tests/probe_phase1.py` runs the verification. Three findings materially shape Phase 3:

### 1. A distance cutoff CANNOT drive abstention on its own

Measured top-1 cosine distances:

| set | min | median | max |
|---|---|---|---|
| in-corpus (n=8) | 0.2469 | 0.3159 | 0.3598 |
| out-of-corpus (n=3) | 0.2713 | 0.3696 | 0.3815 |

**Separation between worst in-corpus and best out-of-corpus: -0.0886 (negative, i.e. they
overlap).** Even the nonsense query "purple bicycle quarterly tax rebate" returns a top hit at
d=0.3815 - closer than some genuine benchmark queries. Dense distance is simply not a
usable abstention signal here.

**Implication:** abstention must come from the fused hybrid score plus an explicit relevance
judgement, not from a `distance < X` threshold. Do not ship a bare distance cutoff.

### 2. Dense-only retrieval misses the exact provision - this is why we chose hybrid

Benchmark F1 ("Can a classical churna from a First Schedule text be patented?") returns
**Section 3(l)** (artistic works) as its top hit. Sections 3(o), 3(c), 3(l), 3(e) and 3(f)
all rank above 3(p) even when queried with 3(p)'s near-verbatim text - the exclusion clauses
are near-identical in phrasing, so embeddings cannot separate them.

This is exactly the failure the BM25 half of the hybrid is there to fix: the literal token
"3(p)" discriminates where the semantics do not.

### 3. The Patents Act's own Section 3(p) is effectively unreachable by dense search

Two chunks carry the traditional-knowledge patent bar:

| chunk | source | dense rank |
|---|---|---|
| `DOC020_chunk_116` | Manual of Patent Office Practice p98 | **1** |
| `DOC014_chunk_011` | Patents Act 1970 p11 | **27** |

The Manual chunk is the better citation anyway - it states the provision *and* names TKDL as
the examiner's prior-art route, which is precisely the official benchmark answer. But the
statute's own text ranking 27th is a direct consequence of the margin-bleed extraction
artifact (§3 quirk 2). BM25 on "3(p)" should recover it; verify this in Phase 3.

### 4. "International" questions are partly in-corpus - relabel the assumption

"How do I file a PCT application in Japan?" returns d=0.2713, better than most in-corpus
queries, because the Manual of Patent Office Practice genuinely covers PCT national-phase
procedure. The corpus is not as cleanly national-only as `jurisdiction=national` suggests.
Treat "is this out of scope?" as a semantic judgement, not a metadata lookup.


---

## 6b. Phase 2 findings - classification

Modules added: `config.py`, `schemas.py`, `llm.py`, `corpus_index.py`, `classification.py`.
Verified by `tests/probe_phase2.py` (5 benchmarks + 7 unrehearsed cases).

### Definition anchors

Each category is anchored to a real corpus chunk whose text is injected into the prompt,
so classification is grounded in statute rather than model memory, and can cite what
defined it:

| category | chunk | source |
|---|---|---|
| `classical_generic` | `DOC001_chunk_004` | D&C Act 1940 s.3(a) - First Schedule formulae |
| `patent_proprietary` | `DOC001_chunk_006` | D&C Act 1940 s.3(h) |
| `new_drug` | `DOC003_chunk_167` | D&C Rules 1945 r.122-E |
| `phytopharmaceutical` | `DOC003_chunk_752` | D&C Rules 1945, Sch. Y data requirements |
| `ayurveda_aahar` | `DOC002_chunk_001` | FSSAI Ayurveda Aahar Regs 2022, reg. 2(b) |
| `cosmetic` | `DOC001_chunk_004` | D&C Act 1940 s.3(aaa) |

`verify_anchors()` checks each chunk still exists *and* still contains an expected marker
string. Call it at API startup - if the corpus is ever rebuilt and ids shift, this fails
loudly instead of silently quoting the wrong provision.

### The prompt bug worth remembering

First version classified the **official benchmark** ("Can a classical churna ... be
patented?") as `not_applicable`, because the prompt defined that outcome as "a question
about IP or regulatory process". Every question in this domain is an IP question, so the
rule swallowed real product questions - F4 and a recipe question failed the same way.

Fixed by making the test **product-presence**, not topic: Step 1 asks whether a product is
described; only if not is `not_applicable` correct. Explicitly: *"`not_applicable` means
'no product to classify', NOT 'this is an IP question'."*

Lesson for Phase 4: rules phrased around what a question is *about* will misfire, because
everything here is about IP. Phrase decision rules around what a question *contains*.

### Known corpus gap - phytopharmaceutical

**There is no clean statutory definition of "phytopharmaceutical drug" in our corpus.**
All 7 mentions were checked. D&C Rules r.2(eb) (the actual definition - a purified,
standardised fraction with defined bio-active markers) was not captured by the extraction.
What we do have:

- `DOC003_chunk_167` - r.122-E, which *includes* phytopharmaceutical drugs within "new drug"
- `DOC003_chunk_752`-`756` - Schedule Y data requirements, which describe the concept
  ("final purified fraction with defined markers") without formally defining it

Benchmark F5 ("what counts as a phytopharmaceutical?") is therefore answerable only
*descriptively*, from the data requirements. Phase 4 must not let the model paper over this
with recalled outside knowledge. Options if it matters: add the missing rule to the corpus,
or have the system state the limitation explicitly.

### Behaviour notes

- **F4 returns `needs_clarification`, not `new_drug`.** "Is my new herbal extract
  formulation patentable?" genuinely does not say whether the extract is a standardised
  fraction (phytopharmaceutical), a classical formulation, or a novel drug. It asks one
  decisive question instead of guessing - which is what the PS requires, but it does mean
  the F4 demo shows a clarifying question rather than a direct answer. Decide before demo
  day whether to use a more specified version of this query.
- A question about a recipe's *IP risk* ("can a company steal my grandmother's recipe?")
  classifies as `not_applicable` - the model reads it as an abstract IP question rather
  than a product presented for classification. Defensible, worth watching.


---

## 6c. Phase 3 findings - retrieval, citations, abstention

Modules: `retrieval.py`, `citations.py`, plus Chroma/BM25 loading in `corpus_index.py`.
Verified by `tests/probe_phase3.py`: **12/12 abstention decisions correct** (8 in-corpus
answered, 4 out-of-corpus refused).

### Neither similarity signal can drive abstention - measured, twice

| signal | in-corpus | out-of-corpus | separates? |
|---|---|---|---|
| dense distance | 0.2469 - 0.3598 | 0.3696 - 0.3951 | ~0.01 margin, too thin to trust |
| BM25 score | 11.21 - 31.16 | 11.95 - 26.29 | **no, overlaps badly** |

"What is the best marketing strategy for my ayurvedic startup?" scores **26.29** on BM25 -
beating several genuine benchmark questions - because *ayurvedic* is a high-value corpus
term. "Penalty for speeding on a national highway" scores 21.37 on *penalty* and *national*.
A threshold on either signal passed all 4 out-of-corpus questions as answerable.

**So abstention is an LLM subject-matter gate**, with the thresholds kept only as a loose
outer bound (`MAX_DENSE_DISTANCE`) and a fast path that skips the call when retrieval is
obviously tight (`CONFIDENT_DISTANCE`). Do not replace it with a threshold.

### Two bugs worth remembering

1. **The gate could not see the evidence.** It truncated each passage to 320 characters,
   but in `DOC020_chunk_116` the Section 3(p) text begins around character 240 and runs
   past 450 - so the gate abstained on the official benchmark while the answer sat just
   past its cutoff. Window is now 900 chars x 6 passages. *When a gate refuses something
   it should accept, check what it can actually see before touching the prompt.*
2. **The gate was asking the wrong question.** Phrased as "do these passages answer this?",
   it rejected partial-but-real coverage. It is now an explicit **subject-matter** check -
   "could these passages bear on this at all?" - because per-step citation validation
   downstream handles completeness.

### Query expansion is what makes the official benchmark work

Users write "can a classical churna be patented?"; the statute says "invention which in
effect is traditional knowledge or an aggregation of known properties". No shared
vocabulary, so both retrievers missed Section 3(p) entirely - the top hits were patent
office *procedure* ("Inspection and supply of copies of documents").

`expand_query()` asks the model to restate the question in statutory terms, then RRF fuses
the ranked lists from every formulation. Generated expansions for F1 included *"invention
relating to formulation disclosed in First Schedule of Indian statute excluded from
patentability"*. That surfaces `DOC020_chunk_116` into the evidence set.

Cost: one extra LLM call per query. Worth it - without expansion the flagship demo query
retrieves the wrong law.

### `REGIME_BOOST` is deliberately 0.0

The category-to-regime bias measured at 0.15 pushed the decisive Section 3(p) chunk **down**
a rank on the official benchmark, with no observed gain elsewhere. Plumbing kept, boost off.
Raise it only with evidence.

### Citation normalizer

`section_or_clause` is never used. Sections are extracted from chunk text with this
priority, learned by getting it wrong first:

1. **The chunk's own opening heading** - this identifies the provision the chunk *is*.
2. **Self-labelling references** (the Manual prints "Section 3(p)" beside each provision),
   excluding anything preceded by a cross-reference cue like "under" or "defined in".

Reading those in the opposite order labelled the D&C Act definitions clause as
"Section 33C", because that clause mentions a board *constituted under* section 33C.

A structural filter suppresses schedule/form numbering: **a heading number repeating more
than 3 times within one document cannot be a section number**, since schedules restart at 1
on every page. This killed false citations like "Rule 5" for a Schedule M paragraph headed
"5. Capsules." It is structural rather than a keyword list, so it adapts to new documents.

Result over the full corpus: **946/2457 chunks (38.5%) get a verified section, 0 contaminated
with footnote text.** The other 62% cite act plus page, which is honest. Under-citing is
safe; mis-citing is not.

Multi-provision chunks name both: `DOC020_chunk_116` renders as
*"MANUAL OF PATENT OFFICE PRACTICE, Sections 3(o), 3(p), p. 98"*.

### Still true: the Patents Act's own 3(p) is unreachable

`DOC014_chunk_011` remains absent from results even with expansion - the margin-bleed
extraction damage (§3 quirk 2) is too severe. We cite the Manual of Patent Office Practice
instead, which states the provision *and* names TKDL as the examiner's route. That is the
better citation for the demo anyway, but the statute itself is effectively lost to search.


### Two guards added after adversarial testing (`tests/stress_phase3.py`)

The 12-query Phase 3 probe was a weak test - those queries were chosen while building the
thing. A 19-case adversarial suite found real failures. Both are now fixed; the suite scores
**7/7 on assertable cases**, with all 12 judgement calls behaving sensibly.

**1. Jurisdiction guard - this was the dangerous one.**

> "Can I sell my ayurvedic supplement in the USA under FDA rules?" -> **ANSWERED**, citing
> FSSAI and the D&C Rules.

An authoritative-looking answer about the wrong country. The PS demands jurisdictions are
"never conflated", so this was a correctness bug, not a polish item. The relevance gate now
classifies jurisdiction (`india` / `foreign` / `international`) on **every** question and
refuses non-Indian ones with a specific reason.

Note this also removed the `CONFIDENT_DISTANCE` fast path: the FDA question scored 0.2980,
comfortably inside any fast path we would have set, so skipping the gate on a tight match
would have skipped the jurisdiction check too. **Jurisdiction must be checked every time.**

International questions (PCT, Nagoya, TRIPS) now abstain with a pointer to the Indian
equivalent, which is honest - `03_international/` is empty by design.

**2. Specificity guard.** `"patent?"`, `"ayurveda"` and `"help with my product"` all
retrieved near-arbitrary evidence and passed. Now blocked by a deterministic content-word
count (`MIN_CONTENT_WORDS = 3`) that runs before any API call, so it also saves free-tier
requests. Unicode-aware, so Hindi questions still pass.

`AbstentionKind` (in `schemas.py`) distinguishes `too_vague` / `foreign_jurisdiction` /
`out_of_scope` / `no_evidence`, because the UI should treat them differently - a scope
boundary is a feature to display, a vague question just needs a nudge.

### Known remaining weaknesses - do not claim these are solved

1. **The gate is not deterministic.** "Why is Ashwagandha banned in India?" returned ABSTAIN
   on one run and ANSWER on the next, same code, temperature 0. Free-model provider routing
   varies. Upgrading to `anthropic/claude-sonnet-5` should reduce this; it will not vanish.
2. **BM25 scores 0.00 on Devanagari** - `tokenize()` matches `[a-z0-9]` only, so Hindi
   questions silently fall back to dense-only retrieval. Fine for now (multilingual is
   deferred) but the degradation is invisible, so remember it before demoing in Hindi.
3. **Sample size is still small.** 19 adversarial + 12 probe cases is far better than 5
   benchmarks, but it is not proof. Treat every new failure as informative.
4. **False-premise questions are answered, deliberately.** "Which section allows patenting
   classical formulations?" retrieves Sections 3(o)/3(p) and passes the gate - correctly, as
   the right response is to refuse the premise *while citing* 3(p), not to abstain. That
   refusal is Phase 4 generation's job and must be verified there.


---

## 6d. Phase 4 findings - generation

`generation.py` holds the whole core loop: `answer_question()` = classify -> retrieve ->
generate -> validate. Verified by `tests/probe_phase4.py` (5 benchmarks + 6 off-script).

**Result: 31 citations emitted across 11 questions, 0 fabricated.** The probe re-checks every
citation against the corpus independently of the code that produced it, so this is not the
generator marking its own homework.

### The three enforcement layers

1. Prompt: evidence only, cite by chunk id, abstain when it runs out.
2. `validate_ids()`: an id must be BOTH a real chunk AND one we actually showed the model.
3. `_build_steps()`: steps 1-3 with no surviving citation have their content **replaced**
   with an explicit refusal. Step 4 is a scope statement, so it is exempt.

If nothing survives validation at all, the whole answer degrades to abstention rather than
shipping unsourced prose.

Rejected ids are returned in `Answer.rejected_citation_ids` rather than dropped silently -
a guard you can see is more convincing than one you cannot, and it is worth showing a judge.

### Three defects found and fixed during verification

1. **The classification anchor was being rejected.** F1 cited `DOC001_chunk_004` (the D&C Act
   definition backing the classification) and the validator threw it out - correctly by the
   old rule, wrongly in substance, because that chunk *is* shown to the model in the prompt.
   The allowed set is now "everything we showed the model", retrieval plus the classifier's
   defining source.
2. **Off-domain questions abstained as "foreign jurisdiction".** "How do I make a chocolate
   cake?" was told it was "governed by another country's law". The gate now judges **subject
   matter before jurisdiction**, so irrelevant questions get `out_of_scope` and only
   in-subject foreign questions get `foreign_jurisdiction`.
3. **The classifier asked needless clarifying questions.** "Can I advertise that my product
   cures diabetes?" returned `needs_clarification`, but the Drugs and Magic Remedies Act bars
   disease claims for *every* category, so the answer does not depend on it. The prompt now
   requires the model to ask only when the missing fact would change **the answer to the
   question asked**, and names the general principle: advertising, ABS, trade mark, copyright
   and labelling duties apply across categories, while patentability, licensing pathway and
   evidence requirements genuinely turn on it.

### Verified behaviours worth demoing

- **The official benchmark lands.** F1 classifies as classical/generic, cites Section 3(p)
  from the Manual of Patent Office Practice, names TKDL as the defensive route (with the
  turmeric and neem examples the Manual itself gives), and closes with the Indian-law-only
  jurisdiction note. That is the PS's "smallest thing that wins the room", end to end.
- **False premises are refused, with citations.** "Cite the exact section that ALLOWS
  patenting a classical churna" produces: *"The evidence does not contain any section that
  explicitly 'allows' [it]"*, then cites 3(p) and 3(d) for what the law actually says. It
  corrects the premise instead of agreeing, and it does so from sources.
- Unrehearsed areas (copyright, advertising, plant varieties, pharmacopoeia) answer correctly
  with no tuning specific to them.

### Known remaining softness

- `needs_clarification` still fires slightly more often than ideal (e.g. an ABS question),
  and it is nondeterministic run to run. Defensible - asking one good question is not a
  failure - but it means F4 demos as a clarifying question rather than a direct answer.
- Generation quality is bounded by the free model. The citation guard makes it *safe* on a
  weak model; it does not make the prose as sharp as Sonnet 5 would.


---

## 6e. Phases 5-8 - API, frontend, integration

### Backend API (`backend/app/main.py`)

`GET /health` · `POST /classify` · `POST /query`. Thin by design - all logic stays in the
modules, which remain testable without a server. Indexes load once in the lifespan hook
(~20s), so no user pays the embedding-model load on their first question.

`GET /health` reports corpus counts, both model ids, and `anchor_problems`, so a corpus
rebuild that shifts chunk ids is visible immediately instead of silently degrading answers.

The `international` jurisdiction returns an honest abstention rather than answering from
Indian law. **The toggle is real plumbing, not decoration.**

Run it:
```
cd backend && ..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

### Latency - the one weak spot, and what was done

A query costs three sequential model round trips: (classify ∥ expand) -> gate -> generate.
On the free endpoint that is **17-40 seconds**. Two mitigations:

1. **Classification and query expansion run concurrently** (`ThreadPoolExecutor` in
   `generation.py`) - they both depend only on the question. Removes one full round trip.
2. **A bounded in-process answer cache** (64 entries, LRU, whitespace/case-normalised key).
   Cold 30.1s -> warm **0.003s**. This matters for demo rehearsal and for a judge asking a
   question someone already asked.

Upgrading to `anthropic/claude-sonnet-5` is the real fix; the free model is the bottleneck.
Do not remove the gate to save time - that is what catches the jurisdiction failures.

### Frontend (`frontend/`, Vite + React + TS + Tailwind)

Dev: `cd frontend && npm run dev` (port 5173, proxies `/api` -> `127.0.0.1:8000`, so the
frontend never hardcodes a host and the same build works deployed behind one origin).

**Visual identity: a printed legal opinion sheet, not a chat window.** Deliberately not the
dark/violet/glowing-orb AI look. Warm paper ground with a faint horizontal ruling like a
ledger page; a transitional serif (Spectral) for legal prose, a grotesque (Inter) for chrome,
and mono (IBM Plex Mono) for statute references so citations read as *records*.

**Colour is semantic - each hue means exactly one thing:**

| token | meaning |
|---|---|
| `haldi` (turmeric #b8860b) | the classification verdict, and nothing else |
| `indigo-dye` (#2f4a63) | citations and sources |
| `neem` (#4f6b3a) | verified / guard-passed states |
| `clay` (#9c4a2f) | abstention and scope limits |

**The reasoning trail is four numbered stations joined by a vertical rule**, not chat
bubbles. Hovering a step highlights exactly the sources behind it in a sticky citation rail.
That interaction is the demo's money shot: it makes "every claim is traceable" something a
judge can *see* rather than something we assert.

Citation cards expand to the **verbatim corpus excerpt**, so a judge can read the statute
text themselves rather than trusting us.

Abstention gets a designed clay panel, never a red error toast - safe abstention is a graded
requirement of the PS, so it should look like the product working.

`frontend/src/types.ts` mirrors `backend/app/schemas.py` exactly. **They are one contract
with a network in between - change both together.**

### Conversation handling - the backend is stateless, the frontend carries context

The API has no memory: each `/query` is independent. That is a deliberate design choice
(cacheable, testable, no session state) but it creates one trap.

When an answer comes back with a `clarifying_question`, the user's next message is a reply to
*that*, and on its own it is meaningless. Sending "something inside is my own formulation"
alone abstains, correctly - it has no subject. So `App.tsx` sends

    `${previousAnswer.question} Additional detail: ${reply}`

whenever the previous answer asked something, and shows a "Replying to" chip above the
composer so the user can see context is being carried. Measured: reply alone -> abstains;
with context -> full 4-step answer with 6 citations.

Context is carried **only** after an explicit clarifying question, not on every follow-up.
Always concatenating would pollute unrelated questions with stale subject matter.

Transcript state lives in `App.tsx` as `Turn[]`, persisted to `localStorage` (last 20,
wrapped in try/catch because private windows throw). "New consultation" clears it.

### End-to-end verification (`tests/e2e_api.py`)

**24/24 checks pass** against the running API. Covers health, input validation (422s), the
full answer path, every abstention kind the UI can render, the jurisdiction toggle, and
citation integrity across multiple questions.

Notably it asserts that every `citation_id` referenced by a reasoning step resolves to a
citation card - the UI cannot show a dangling source marker.


---

## 6f. Phase 9 - benchmark hardening

`tests/benchmarks.py` scores the Part F queries on the brief's four criteria
(correct classification · real citation · no hallucinated facts · disclaimer shown) plus an
off-script suite the system was never tuned against. Citations are re-verified against
`all_chunks.json` by the test itself, independently of the code that produced them.

**Final: 94/94 criteria, 0 failures.** `tests/e2e_api.py`: 24/24.

### Four bugs the suite caught - all found by testing, none by inspection

1. **A US question was being answered with "what kind of product is it?"** Classification ran
   before the jurisdiction gate, so it asked a clarifying question about a question we were
   never going to answer. **Scope and jurisdiction are now settled before any clarification.**

2. **The abstention KIND was wrong even when abstaining was right.** The first version of the
   test only asserted *that* it abstained, so a US question refused as "off-topic" scored a
   pass. Tightened to assert `expect_abstention_kind`; a scope boundary and a topic miss are
   different answers and the UI renders them differently.

3. **"none" jurisdiction was missing.** With only india/foreign/international, a chocolate-cake
   question got labelled foreign ("governed by another country's law" - absurd), and after
   reordering, a US question got labelled merely off-topic. Adding `none` for non-legal
   questions separates the two cleanly.

4. **The generator skipped the on-point provision.** Retrieval was measured **stable** -
   `DOC020_chunk_116` appeared in 5/5 runs at ranks 1,1,1,3,3 - but the model sometimes cited
   Section 3(c) or 3(l) instead of 3(p). Indian statutes list near-identical exclusion clauses
   side by side, and the model settled for a neighbour. Fixed by telling it the evidence is
   relevance-ordered and not to prefer a general neighbour over a directly applicable
   provision. **Now 4/4 runs cite 3(p) and name TKDL.**

   *Diagnostic worth repeating: when an answer is wrong, measure retrieval separately before
   touching prompts. Here the instinct to "improve retrieval" would have wasted the effort.*

### Structural fix for needless clarifying questions

Prompt instructions did not reliably stop the classifier asking "is your product classical or
proprietary?" for questions whose answer does not depend on it (trade marks, advertising).
The classifier now must return **`answer_depends_on_category`**, and `classification.py`
downgrades `needs_clarification` to `not_applicable` when it is false. A declared, checked
contract rather than a plea.

### Still true, and worth stating plainly

- **Free-model output is not deterministic.** Individual runs vary; the suite is a snapshot,
  not a guarantee. Re-run it before the demo rather than trusting a past green.
- `top_k` raised 8 -> 12 (`config.py`) after the decisive chunk was measured landing at rank
  7 of 8 on some runs.
- The answer cache means a repeated benchmark run can report 0.0s and re-use a prior answer.
  **Restart the backend for a genuinely cold benchmark.**


---

## 6g. Post-comparison hardening (after `COMPARISON_REPORT.md`)

A rigorous comparison against the teammate's independent build surfaced defects in **ours**
and in the **shared corpus**. All are fixed; the corpus fixes changed chunk ids, so read this
before trusting any chunk id written earlier in this file.

### Corpus: `About TKDL.pdf` was silently lost, and 115 chunks with it

`build_chunks.py` dropped any page matching a bare `\bCONTENTS\b`. The single page of
`About TKDL.pdf` contains the ordinary phrase *"the available **contents** of the ancient
texts"*, so its only page was discarded and the document produced **zero chunks** - while the
log still reported "processed" and flagged nothing. TKDL is central to the flagship answer,
so losing the document explaining TKDL mattered.

Two fixes:
- The contents-page pattern is now **anchored to its own line** and additionally requires the
  page to contain several headings, so prose mentioning "contents" is safe.
- **A PDF that extracts text but yields zero chunks is now reported** as a WARNING and listed
  in the summary. Silent data loss was the real bug; the regex was only its cause.

Corpus went **2,342 -> 2,457 chunks**. Every folder gained, because the filter had been
over-firing across several documents, not just this one.

### chunk_id is no longer safe to hardcode - and the code no longer does

`doc_id` was assigned by enumeration position, so `chunk_id` moved whenever the corpus
changed. The rebuild renumbered nearly everything: `patents act 1970` DOC014 -> DOC005, the
Manual of Patent Office Practice DOC019 -> DOC020, Section 3(p) `DOC020_chunk_116` ->
`DOC020_chunk_116`.

Worse, ordering was not even stable across machines: `sorted()` on `Path` case-folds on
Windows but not on Linux, so the same corpus produced different ids depending on who ran it.

- `build_chunks.py` now sorts on the **lowercased POSIX relative path**, which is
  deterministic on every platform.
- `classification.py` **resolves definition anchors by content**, not by pinned id: each
  category names an act fragment plus a distinctive phrase, and the shortest matching chunk
  wins. `verify_anchors()` still fails loudly at startup if a provision truly disappears.
- `tests/probe_phase1.py` resolves the Section 3(p) chunks by content too.

**Rule going forward: never hardcode a chunk_id.** Resolve it from text.

### The relevance gate now fails CLOSED

It previously returned "allow" when the LLM was unavailable, reasoning that citation
validation still prevents fabrication. True, but insufficient - citation validation cannot
tell that a question was about US law. During an outage the system would have answered a
foreign-jurisdiction question from Indian statutes, confidently and with real citations.

It now refuses with `AbstentionKind.GATE_UNAVAILABLE` and tells the user to retry. An honest
refusal is a worse demo and a better legal tool.

### Small talk is answered, not refused

"hello" used to return *"That is too short for me to search on"*. `conversation.py` now
answers greetings, capability questions and thanks deterministically, before the vagueness
guard and before any API call. The patterns must match the **whole** message, so a real
question - even a short one - still goes to retrieval. Idea ported from the teammate's
`rag_engine._conversation_response`, which handled this better than we did.

### Also fixed

- Whitespace-only questions (`"   "`) returned HTTP 200; now rejected at validation
  (`min_length=2` + `strip_whitespace=True`).
- `Answer.headline` added: a one-sentence direct answer above the trail, because users were
  getting four long paragraphs before learning whether the answer was yes or no. The free
  model ignores word budgets, so the UI also clamps each step to ~2 sentences with a
  "Show full reasoning" toggle.

### Verified after the rebuild

Backend restarted on the rebuilt index (2,457 chunks in JSON, 2,450 embedded):

- `tests/benchmarks.py` **94/94 criteria, 0 failures**
- `tests/e2e_api.py` **24/24 checks**
- `anchor_problems: []` at startup, with anchors resolved by content
- whitespace-only question now HTTP 422; `hello` / `what can you do` / `thanks` answered
- **The recovered `About TKDL` document now ranks #1** for "What is the Traditional Knowledge
  Digital Library and how does it prevent misappropriation?" - it was absent from the index
  entirely before this fix.

### Known, still open

- **Duplicate ingestion — ACCEPTED, do not "fix" it casually.** `The Biological Diversity
  Rules 2024.pdf` exists in BOTH `02_national_statutes` and `04_registries` as two different
  files (2,470,317 vs 2,414,630 bytes), producing ~184 near-duplicate chunks, about 7.5% of
  the index. Retrieval sometimes returns the same provision twice in one result set.
  **Decision taken: leave it.** Removing a PDF renumbers every document after it, which
  invalidates every chunk id in flight for a cosmetic gain. The cost is a wasted evidence
  slot now and then; the cost of renumbering mid-project is worse. Revisit only if the corpus
  is being rebuilt for another reason anyway.
- `TKDL Access Agreement.pdf` still yields only 2 chunks from 3 pages - worth a manual look.


---

## 6m. Phase 14 - the outage, and three defects behind it

Every query was returning `gate_unavailable` ("Safety check unavailable") straight
after a fresh Gemini key was added. The key was fine. Three separate faults were,
and two of them are the kind that make a key rotation look like a code bug.

### A rotated key could not take effect without a restart

`llm.py::_client_for` cached the OpenAI client on `(base_url, api_key_env)` - the
NAME of the variable, not the key. A client built with a since-exhausted key was
therefore reused for the life of the process, so editing `.env` changed nothing.
`config.provider_key` compounded it: `load_dotenv()` without `override=True` will
not replace an already-loaded value, so the new key never even reached `os.environ`.

The symptom is maximally misleading - every question fails the gate while a
hand-run probe reading the same `.env` succeeds. Both are fixed: the client cache
is keyed on the key VALUE, and `.env` is authoritative (deployments ship no `.env`,
so nothing is overridden there).

### A 31-second limit was retiring a provider for 20 minutes

The one that actually caused the cascade. Gemini reports a **per-minute** limit
with status `RESOURCE_EXHAUSTED`, and `_DAILY_CAP_MARKERS` contained
`resource_exhausted`. Measured by bursting the free tier:

    quotaId: 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier'
    limit: 15, retryDelay: 31s, status: RESOURCE_EXHAUSTED

So `_is_daily_cap()` said yes and `_mark_capped()` retired that model for the full
20-minute memo. With both Gemini models retired that way and OpenRouter genuinely
out of daily quota, the whole six-endpoint chain collapsed onto Groq, which then
tripped its own per-minute token limit (ITPM 7000) and the request failed closed.

`_is_per_minute_limit()` now runs FIRST and short-circuits the daily check. A
genuine Gemini *daily* cap still classifies correctly, because its quotaId carries
`PerDay`. Verified against five real provider payloads.

*The general lesson: two limits that share a status code are two limits. Read the
payload, not the status.*

### The category comparison could not show the contrast it exists for

`compare_categories` retrieved once against the bare product description, and
`expand_query` restates the PRODUCT - so a product description expands into
product vocabulary. Measured on "ashwagandha root extract capsule standardised to
5% withanolides": all twelve chunks came from the D&C Rules 1945, `patentable`
read "Not covered in evidence" for **all four** categories, and `new_drug` and
`phytopharmaceutical` retrieved nothing at all. The module docstring and the
comment at the retrieval call both claimed a patentability bias existed. Neither
was implemented.

Two changes, and the second is the one that mattered:

1. One statutory probe per compared category, fused into the expansion. Anchored
   to the fixed `COMPARED` set - a structural property of the feature - not to
   anything scanned out of the user's wording, so 5's no-keyword-special-casing
   rule holds. This alone filled in only two of four categories.
2. **Reserved slots.** RRF rewards *consensus* across formulations, which is the
   opposite of what a comparison needs: the product's vocabulary appears in every
   ranked list and accumulates, while the provision governing exactly one category
   appears in one list and is out-scored. Each category now also gets
   `compare_probe_slots` from its own probe, merged in. No LLM call - the gate has
   already settled scope and a fixed probe needs no expansion.

Result on the same product: four categories, four cited, four *different*
patentability verdicts, and three distinct acts (D&C Rules, Manual of Patent Office
Practice, Patents Act 1970) where there had been one.

### Also fixed

| Fix | Note |
|---|---|
| Jurisdiction synthesis always failed | `max_tokens=1200` truncated it mid-array at `{"points": [`, so a healthy provider reported the whole comparison unavailable. That output is several points wide, each carrying prose for BOTH sides plus two id arrays - far larger than any other JSON reply here. Raised to 3000; measured that gpt-oss-120b returns clean JSON at 1200 on a small task, so the ceiling was the prompt's output size, not the model. |
| "Plain English" collided with the EN/HI language toggle | Renamed to **Legal terms / Simple terms**. Hindi had the same collision - "सरल भाषा" is literally "simple LANGUAGE" beside a language switcher - now विधिक शब्द / सरल शब्द. |
| `settings.fallback_models` was dead | Referenced nowhere outside its own definition since `llm_chain` superseded it, and its 24-line comment actively misdescribed current behaviour. Removed. |
| Stale benchmark expectation | The Nagoya case required a `foreign_jurisdiction` refusal, written when `03_international/` was empty. India implements Nagoya through the BD Act, so national mode now answers it - from Indian implementing law only. The assertion is deliberately *stronger* than the old one: it must cite Biological Diversity. The FDA case still refuses, because foreign **domestic** law is a real scope boundary. |

### The consultation page lost its rail

The landing page was the engaging surface and the workspace was a form with a
300px sidebar beside it, which read as two different products. The rail is gone:

- **Mode, jurisdiction and wording are pills above the composer**, where the
  decision is actually made, via one shared `PillGroup` - the rail's three
  groups had drifted into three slightly different markups and only one of them
  implemented a disabled state.
- **History and the log-consent choice are behind one header menu**, because
  they are set once a session rather than per question.
- **The interface language toggle is simply deleted.** `Shell` already owned
  one; two controls for one preference is two sources of truth. `setUiLang` is
  no longer destructured here, which is what surfaced it.
- **The empty state stayed on paper, scaled up.** Three passes, and the two
  failures are worth more than the result:

  1. Paper with a faint blob and leaf - too faint to read as a decision.
  2. The landing page's hero reproduced verbatim: pointer-tracked blob, swaying
     leaf, Fraunces headline, instrument marquee. Rejected on sight.
  3. A dark ledger workspace - restrained, small type. Rejected harder.

  What was actually being asked for, all along, was the landing page's
  **generosity** - big type, plenty of air, obvious hierarchy - and NOT its
  ground, its ornament or its content. Every attempt to borrow the *look* made
  the page worse; the one that borrowed the *scale* worked. So the final state
  is the original paper markup with the headline at
  `clamp(1.9rem, 3.4vw, 2.55rem)`, a 15.5px lead and roomier cards - plus the
  landing page's **leaf mark** above the headline, same geometry, swaying.

  The leaf is the one piece of bespoke CSS on this screen, and it does not
  reuse `leaf-sway` directly: the landing mark is ~280px, where an 8px drop
  reads as a gentle sway; on a small mark the same 8px is a lurch. The rotation
  is kept, the travel scaled, and the origin moved to the stem.

  **It sits BESIDE the headline, not above it.** Stacked, the mark cost ~80px
  of vertical room - exactly what the fourth example row needs - so both mark
  and headline had to stay small. Beside it, it occupies width the centred
  headline was not using, and that height comes back as size: leaf 74px -> 172px
  and headline 2.55rem -> 3.4rem. Below `sm` it stacks and the heading centres,
  because at 390px the mark leaves ~270px and sets the headline in six lines.

  **The leaf width is capped, not purely `vw`-scaled.** Uncapped it kept
  growing on wider screens and pushed the fourth row under the composer at
  1440x900 - on a viewport that was WIDER. Vertical room does not grow with
  width, so the ceiling is what protects the layout.

  Measured clearance between the last example card and the composer bar:
  **18px at 1280, 1440 and 1600.** All four cards must clear the composer at
  900px height - re-measure that before changing any spacing, type size or the
  leaf cap here, because almost every change on this screen trades against it.

- **The header eyebrow is hidden while the empty state shows.** Both printed
  `t.tagline`, a centimetre apart.

- The menu panel is **dark for a reason, not for taste**: `SessionList` is
  styled in cream for the old rail, so on the light panel of the first pass it
  rendered cream-on-cream and was invisible. Matching the rail's ground reuses
  that component unchanged, so the bug fix and the visual request are one edit.
- The **"825 sources"** count under the International option is gone, along
  with the now-dead `jurisdictionSources` and `sectionLang` strings.
- `ACTS` moved to `src/data/acts.ts` so the landing page and the consultation
  cannot drift apart.

### The reasoning trail became cards with two faces

The trail is still four numbered stations on a rule - it is not chat
bubbles and the medallion and connecting line are untouched. Each station
is now a card that **turns over**:

    front  what we concluded, in our words
    back   the verbatim statute it came from

That is the product's whole claim as one gesture, and it is the reason a
flip is not decoration here: it puts the law directly behind the sentence
relying on it, instead of asking the reader to trust a superscript and go
hunting for the matching card in the rail. Front stays the default, so
nothing is hidden - a reader who never turns a card loses nothing.

Three things the flip forced:

- **The container has no intrinsic height.** Both faces are absolutely
  positioned so they can occupy one box and rotate past each other, so
  the height is measured (`ResizeObserver` on the showing face) and
  transitions alongside the rotation. Two sentences of prose and an
  800-token statutory chunk are nowhere near the same size; a fixed
  height would either clip the law or leave a hole under the answer.
- **A 3D rotation is exactly what `prefers-reduced-motion` exists to
  suppress**, and it is also exactly what must not reach a printer. Both
  blocks return the faces to normal flow and show the front only -
  otherwise the trail prints as four empty boxes, because absolutely
  positioned backface-hidden faces contribute no height.
- **The back needed the same nested-button guard as the front, and did
  not have it.** Its own turn control fired `turn()` and then bubbled to
  the card's `turn()`, toggling twice for a net change of nothing - a
  control that looks broken while both handlers are working perfectly.
  Caught by a Playwright assertion, not by looking at it. Both faces now
  share one handler.

Alongside the flip, the link to the citation rail gained a second
strength, because it had exactly **one** before this: hover.

Hover is a mouse-only affordance. On a phone, and on a projector where a
presenter cannot hover precisely, the "every claim is traceable"
demonstration - the thing 6e calls the demo's money shot - **did not
exist at all**. So:

| interaction | effect |
|---|---|
| hover a card | transient: lights that step's sources |
| click the medallion | **pins** them; survives the cursor leaving |
| click the card body | turns it over to the statute |
| click a source chip | scrolls that card into view and rings it once |

The medallion pins and the card turns, deliberately as two controls: "keep
these lit while I read" and "show me the law itself" are two questions,
and one overloaded control would answer neither well.

`AnswerView` now holds `hovered` and `pinned` separately, with hover
winning while set - a passing cursor previews another step without
destroying a pin the reader deliberately placed. The rail carries a
"Showing step N ✕" control, because a pin is a *mode* and a reader who
scrolled down to the sources must be able to leave it from there.

Three things that had to be got right rather than merely built:

1. **`hovered` was a single id.** `onHoverStep` took `string[]` and
   `AnswerView` did `ids?.[0] ?? null`, so a step citing two sources lit
   exactly one of them - quietly undercutting the claim the interaction
   exists to make. It is a `string[]` end to end now.
2. **The ring flash is its own prop, not derived from `highlighted`.**
   Tied to the highlight it fired on every passing cursor, which is noise
   rather than signal. It fires only on a chip jump.
3. **A step with no citation is not a pin target and has no back face.**
   Step 4 is a scope statement and carries none by design; its medallion
   is `disabled` and its card takes `.is-flat` (no pointer, no lift, no
   turn control). A control that would light nothing, or turn over to an
   empty face, advertises itself as broken.

The connecting rule is now **drawn** downward (`scaleY`, delayed off the
same `--i` as the station) so the chain is seen being built in the order
the argument is made. That is a `transform`, so both the print block and
the reduced-motion block must pin it to `none` explicitly - otherwise the
rule prints at zero height and the trail arrives as four disconnected
boxes. Verified: 132px rule under `prefers-reduced-motion: reduce`.

Colour stays semantic. Cards use indigo (sources) and clay (abstention)
only - **haldi is deliberately not used here** even though step 1 is the
classification step, because haldi identifies the classification *verdict
badge* and nothing else (6e). Spending it on a trail card dilutes the one
thing it names.

A click that ends a text selection is a drag, not a turn - people copy
statute text out of the back face, so `getSelection().isCollapsed` gates
the body click on both faces.

Verified with Playwright, behaviour not screenshots: 16/16 flip checks and
14/14 rail/menu checks at 1440x900 (turn and turn-back, measured height
tracking the showing face, `inert` on the hidden one, selection-is-not-a-
turn, flat step has neither control, pin persistence, hover-does-not-flash,
real localStorage wipe) plus 4/4 on touch at 390px and under reduced
motion. `printBriefing.ts` builds its own HTML from the `Answer` object and
never reads this DOM, so the print path is unaffected by any of it.

### Delete-all is inline and two-step, not `window.confirm`

`useSessions.clearSessions()` rebuilds from `blankSession()` rather than
removing the storage key: the hook writes state back on every change, so
clearing the key directly is undone by the next render.

The confirm is armed inline and disarms itself after 6s. `window.confirm`
would have been one line, but it drops a system dialog on a page whose
whole identity is a printed sheet, and on a demo projector a native modal
is the one element nobody can style, dismiss quickly or screenshot. The
arming state also gives a destructive action a visible cost.

### Next steps had to be enforced in code, not asked for in the prompt

`NEXT_STEPS_PROMPT` already said, in as many words, "not a restatement of the
refusal". The model returned *"Recognize that the classical churna ... cannot
receive patent protection"* anyway. The prompt was right and the free model
under-followed it, so the rule now also lives in `_NON_ACTION_OPENERS`, which
drops any step opening with Recognise/Understand/Note/Be aware/Consider that.
Matched only at the START, so "Consider filing an application" survives.

Plain mode gained one rule for the same reason: start each step with the
consequence, never the provision. Measured after: *"You cannot patent this,
because Section 3(p) ... treats"* rather than *"Under Section 3(p) ..."*.

**And writing that guard reproduced 6k's bug exactly.** The regex went in as
`r")\x08"` - a literal BACKSPACE - because the patch string was non-raw, so
`\x08` became the escape while `\s` survived (it is not a valid escape). The
guard was inert and looked perfect in every rendering. Found only by counting
control bytes. **`test_units.py`'s control-character sweep exists for this; run
it after any regex edit.**

### Verified at the close of this phase

Cold backend on the rebuilt index, rate limiting disabled:

```
tests/test_units.py              133/133
tests/test_security.py            25/25
tests/test_gate_scope.py          16/16
tests/test_legal_advice.py        15/15
tests/test_jurisdiction.py        10/10   (was 6/6 with 2 SKIPPED in 6l)
tests/test_jurisdiction_compare.py 12/12
tests/test_style_and_steps.py     21/21
tests/test_subject_scope.py       11/11
tests/test_flagship.py             4/4    (5/5 cold runs cite 3(p) + TKDL)
tests/e2e_api.py                  39/39
tests/benchmarks.py               92/93
frontend tsc --noEmit  clean      npm run build  clean
```

The one benchmark miss was the off-domain marketing question answering instead of
refusing. Re-measured immediately: **4/4 refuse with `out_of_scope`.** Free-model
variance, and 6f's warning stands - **re-run the suites before demoing.**

Style toggle verified as an equality property, not a sample: legal and plain return
**identical** citation lists, per-step ids, classification and confidence, with
every step's prose different.

### Known still open

- **The machine is the fragile part, not the code.** The backend needs ~1.5 GB and
  this laptop has 7.78 GB total; a run was OOM-killed by Windows at 98% commit
  charge. Close browsers before demoing.
- OpenRouter is fully daily-capped (both models). Google and Groq have headroom,
  and the chain fails over correctly between them - but a burst still trips
  Gemini's 15 requests/minute free-tier limit, so do not fire suites back to back.
- Our own rate limiter (12/min) will 429 a suite run started immediately after
  another. Start the server with `IPSAKTI_RATE_LIMIT_QUERY=0` to run them.
- Confidence is still uncalibrated.
- The OpenRouter key exposed by the 6j traversal bug has still not been rotated.

---

## 6n. Phase 15 - citation depth, a four-band meter, the takeaway, cards, and export readiness

Seven phases run in order, each verified before the next. The corrections worth
carrying forward are the ones where the obvious diagnosis was wrong.

### The D&C Rules cited a provision on 11% of its chunks, and the regex was not why

Reported as "most Drugs and Cosmetics Rules citations show *provision not
identified*", and the first guess - a heading-format mismatch - was only a small
part of it. Measured, the causes were three, in ascending order of damage:

1. **Bracketed headings.** Indian Kanoon wraps any amended provision in square
   brackets: `31. [ Standard for certain imported drugs. [Substituted by...`.
   `HEADING` required `[A-Z]` straight after the number's stop and got `[`.
2. **The footnote filter fired on the amendment note.** `_heading_number`
   rejected a heading if a footnote cue appeared within 160 characters *after*
   it - and in this document an amendment note follows almost every heading. The
   discriminator is not whether a cue is present but **where it sits**: a
   footnote block opens with its cue (`2. Ins. by Act 21 of 1962`), a real
   heading puts its title first. `FOOTNOTE_LEAD_CHARS = 6`.
3. **`_unreliable_numbers` banned the numbers 1-14 and 23 outright**, because
   the schedules reuse them. That discarded **316 correctly detected real
   rules** to suppress schedule paragraphs, and it was by far the biggest cause.

The replacement is structural, not a keyword list: **a statute's provision
numbers ascend through the document while schedule numbering restarts**, so
`_provision_spine` builds the longest non-decreasing chain of detected headings
under a positional bound, and that chain is the provision body. Chunks between
two chain members inherit the earlier number.

Four guards, each added because the unguarded version produced a real
mis-citation:

| guard | what it stopped |
|---|---|
| `SPINE_MAX_LINK_GAP = 40` | the chain hopping 289 chunks into Schedule H and citing drug names as Rules 230, 285, 342, 393, 444 |
| same printed page | `Section 1` inherited onto an Ayurvedic Formulary *recipe* |
| `STRUCTURAL_DIVIDER` | a lone `CHAPTER VI FARMERS' RIGHTS` chunk inheriting the section above it |
| `MAX_NUMBERED_ENTRIES = 4` | the First Schedule *book list* cited as "Section 1", and 60+ blocks of pure footnote text |

The spine is **strictly additive**: `_repeated_numbers` is kept as the fallback,
so every citation the previous implementation produced is still produced.

```
Drugs & Cosmetics Rules 1945   11.2% -> 20.3%   (provision body alone 58.4%)
patents act 1970               62.1% -> 92.3%
Geographical Indications Act   77.6% -> 95.5%
Trade Marks Act 1999           74.6% -> 89.8%
Drugs and Cosmetics Act 1940   43.9% -> 68.3%
corpus total                   50.7% -> 55.9%
```

Two acts went *down* and both are correctness gains: AFI ingredient lists
("3. Bala (Rt.) 144 g.") were being cited as "Section 3".

**No vector-DB rebuild was needed.** The displayed provision is derived at
request time from `chunk_text`; `section_or_clause` is still ignored. A rebuild
would have renumbered every chunk id for nothing - which is precisely the
6g/6l hazard.

*General lesson: 70% of this document is Schedules and Forms, where a Rule
number would be **wrong**. The ceiling here is low on purpose.*

### Confidence: the missing component was citation specificity

Every sampled answer sat in the middle band, and the cause was that nothing in
the score could tell `Geographical Indications Act, Section 11` from
`D&C Rules 1945, provision not identified, p.1`. Both are "a surviving citation
from one act".

- **`W_SPECIFICITY = 0.25`** - the fraction of citations that resolve to a named
  provision. Worth scoring only *after* the fix above; before it, this component
  would have measured the extractor's blind spots.
- **Breadth is counted in distinct PROVISIONS, not acts.** Counting acts
  punished correctly focused answers: a GI registration question citing
  Sections 2, 3 and 11 of the GI Act - three pinpointed provisions of exactly
  the governing statute - was capped for "resting on a single source".
- **Caps became ceilings.** Every cap used to dump to MODERATE, so an answer
  with three acts, four provision-specific citations and one abstaining step
  landed in the same band as one resting on a single unpinpointed page. Each
  weakness now costs what it is worth, and a reason is recorded only when a
  ceiling actually bites.
- **A fourth band, `STRONG`.** Reserved for answers where EVERY citation names
  its provision.

Same captured inputs, rescored: GI `0.80 Partly supported -> 0.95 Strongly
supported`; phytopharmaceutical (the known corpus gap) `0.50 -> 0.367 Thin
evidence`. Before, four of eight answers sat at exactly 0.80.

`assess()` now takes built `Citation` objects rather than chunk ids, which
removes a corpus lookup from the scorer and is what makes it unit-testable.

### "International Patent Office" needed a code guard, because it is in the corpus

`About TKDL.pdf` reads "prevent its misappropriation at International Patent
Offices". A model answering faithfully from that evidence reproduces the phrase,
and did in 2 of 6 probe questions including the flagship. A prompt rule alone
would not hold, so `citations.normalise_institutions()` rewrites it - over model
prose only. **Citation excerpts stay verbatim: if the source says it, the source
card shows it saying it.** 2/6 -> 0/6.

Alongside it, two prompt corrections measured before and after:

- **TKDL confers no rights.** Now "operates as a defensive prior-art mechanism
  ... examiners use it to refuse invalid applications", and on a patent question
  "rather than being a registration route for your own rights".
- **Section 3(p) is not a blanket bar on anything Ayurvedic.** Before, a
  self-invented turmeric emulsion got *"no patent protection route is available
  for this formulation"*. After, the three situations are distinguished and it
  reads *"not automatically barred by Section 3(p) ... assessed on its own
  novelty, inventive step, and ... 3(d) ... 3(e)"*, with the Indian Patent
  Office named as the route.

### The takeaway banner: a closed vocabulary is the enforcement

`schemas.TAKEAWAY_LABELS` is a per-intent table of hedged labels, and
`generation._build_takeaway` replaces anything outside it with "Requires
verification". A model returning "Yes, patentable" therefore *cannot* put those
words on the page - the never-bare-yes/no rule is structural, not advisory.

The reason sentence is citation-checked like a step, and a reason naming an
unretrieved provision drops the whole banner. That is the 6j headline lesson
applied on the way in: **any new prose channel to the user needs its own
validation, or it becomes the hole in the guard.**

Definitional questions get no banner ("What is a GI?", "What is TKDL?" -> none),
because there is no matter to take a view on and a label would invent one.

### Evidence support, not confidence

The raw score is gone from the user-facing view - including from the
accessibility tree, where it had survived as "(internal score 0.87,
uncalibrated)", showing screen-reader users a two-decimal false precision that
sighted users were spared. It now sits behind `localStorage.ipsakti.dev = "1"`.

Rendered as a **semicircular gauge** whose needle rests on the middle of a band
and never between two: the scale is ordinal and uncalibrated, so a needle at an
arbitrary angle would imply a resolution this measurement does not have.

Palette correction: the meter used **haldi** for its middle band. Haldi
identifies the classification verdict and nothing else. Filled arc is now neem
(grounded), the bottom band clay (a limit).

### The trail is a 2x2 grid that opens in place

Four compact cards - number, icon, title, one sentence - each expanding to the
full reasoning, the named provisions, and the verbatim statute.

- **A card grows in its own column.** Spanning the grid looks richer for one
  frame and then shoves every sibling sideways, which reads as a glitch.
  `align-items: start` keeps the neighbour its natural height (measured: card 2
  170px -> 341px, card 1 unchanged at 170px).
- **The collapsed sentence is the step's own first sentence**, and the expanded
  body shows only the *remainder*. Rendering the full content there printed the
  opening sentence twice - caught by screenshot, not by reading the code.
- **`grid-template-columns: minmax(0, 1fr)` is load-bearing on mobile.** A
  single implicit column sizes to content, and the non-wrapping act names in the
  provision chips grew the grid to 404px inside a 390px viewport.

### Export readiness (`export_readiness.py`, `/export`)

India-side and target-market readiness for one product, reusing `classify`,
`retrieve` (with its gate), `validate_ids`, `strip_unsupported_provisions`,
`confidence.assess` and `escalation.assess`. Three properties are enforced in
code rather than requested in the prompt:

- **Nothing about a country is hardcoded.** No market table, no pre-written
  paragraphs. `tests/test_units.py` greps the module for country and regulator
  names and fails if one appears.
- **Status is derived.** `_settle_status` overrides the model: no surviving
  citation forces `NOT_COVERED`, and nothing reaches `VERIFIED` without one.
- **Separation is validated per item.** A real, retrieved chunk from the wrong
  corpus is dropped, and an item left with nothing becomes `NOT_COVERED`.

Measured, and the contrast is the feature:

```
Germany  EU Directive 2004/24 -> simplified registration, applicant
         establishment, labelling. 11 sources, 0 rejected, 0 leaks.
Brazil   target section NOT COVERED - "does not contain any instruments,
         treaties, or regional frameworks that reach Brazil".
```

One prompt defect found by comparing two runs: Germany came back covered once
and "does not specifically mention Germany" the next. **An instrument reaches a
market when the market falls within the instrument's own stated scope** - a
regional instrument binds its member states without naming them.

### The off-domain refusal was broken, and expansion was why

Found during the Phase 7 regression, reproducible **0/5**, not variance:

```
Q:           What is the best marketing strategy for my ayurvedic startup?
SEARCHED AS: compliance standards for advertising and claims of ayurvedic drugs
GATE:        relevant=True - "asks for business strategy and regulatory compliance"
```

`expand_query` manufactured a legal question out of a business one, and 6k's own
fix - showing the gate the SEARCHED AS lines - is what made the gate trust the
rewrite. This is the Tests 6/7 defect in a new guise.

Fixed at the gate, where the user's question is authoritative: the rewrites are
search vocabulary, and **the subject matter is the user's question, never the
rewrites**. 0/5 -> 5/5 refused as `out_of_scope`, with the positive controls
intact (trade mark 4/4 answered from the Trade Marks Act).

*Pre-existing, not introduced by this phase - 6m recorded it as "free-model
variance" after a lucky re-measurement. It is not variance.*

### Verified at the close of this phase

Cold backend, rate limiting disabled:

```
tests/test_units.py            168/168   (+35: specificity, takeaway, readiness, institutions)
tests/test_security.py          25/25
tests/test_gate_scope.py        15/16    (retrieval variance on a 3-trial check)
tests/test_legal_advice.py      15/15
tests/test_jurisdiction.py      10/10
tests/test_jurisdiction_compare.py 12/12
tests/test_style_and_steps.py   21/21
tests/test_subject_scope.py     10/11    (retrieval variance on a 2-trial check)
tests/test_flagship.py           4/4
tests/e2e_api.py                39/39 then 32/34 on a later run (one flagship variance run)
tests/benchmarks.py             92/94
UI regression (Playwright)      21/21
frontend tsc --noEmit clean     npm run build clean

flagship, 5 cold runs: Section 3(p) 5/5 | TKDL 5/5 | classical_generic 5/5
```

**The answer cache makes a suite lie.** A bad flagship run in `e2e_api`
populated the cache, and `benchmarks` then scored that same answer at `0.0s`.
Any suite reporting a sub-second answer is reusing one; restart before quoting a
number.

### Known still open

- **Retrieval dilution on compound questions.** "Can I patent it, and what
  licence do I need?" retrieves only D&C licensing rules, so the (now correctly
  ordered) patentability sentence has to say the evidence is silent. A *pure*
  patentability question retrieves 3(d)/3(e)/3(o)/3(p) correctly. The fix is
  6m's reserved-slots pattern applied to expansion formulations; not taken here
  because it is a change to core retrieval and needs its own measurement.
- **"What is ABS?" retrieves food and drug regulation** rather than the
  Biological Diversity Act on roughly 1 in 3 runs.
- ~~Hardcoded legal claims in the frontend~~ — **fixed in §6o.** All 22 strings
  now name a subject and invite the question, with a guard that fails on
  assertive forms.
- ~~`Escalate.tsx` opens a `mailto:` with an empty recipient~~ — **fixed in
  §6o.** It copies a prepared practitioner brief instead.
- Confidence is still uncalibrated - now demonstrably *responsive* across four
  bands, which is not the same thing.
- Gemini's daily quota was exhausted during this phase; the chain failed over
  and one probe run returned `gate_unavailable`, which is the fail-closed
  behaviour working.
- The OpenRouter key exposed by the 6j traversal bug has still not been rotated.


---

## 6o. Phase 16 - the anchors were pointing at the wrong law

This phase set out to remove uncited legal claims from the marketing surfaces.
Checking the corpus for something to replace them with is what surfaced the
serious defect, which had nothing to do with the marketing surfaces.

### Three of six classification anchors resolved to the wrong chunk

Each category is anchored to the chunk that DEFINES it. That chunk is injected
into the classifier prompt under the heading "statutory definitions, quoted
verbatim from Indian law", shown to the user as "Defined by ...", and added to
the set of ids an answer may cite. `verify_anchors()` reported no problems.

```
patent_proprietary -> a Siddha/Unani formulary BOOK LIST
ayurveda_aahar     -> a food-additive schedule (citric acid)
new_drug           -> an Ethics Committee clinical-trial proviso
```

Two independent causes, and the second is the one worth remembering:

1. **The selector was "the shortest chunk containing the phrase".** A term
   appears in more places than the clause defining it, and schedules are short,
   so schedules won. `"patent or proprietary medicine"` matched a First Schedule
   book list at 1,780 characters and lost to it against the 2,240-character
   definitions clause.
2. **`excerpt()` truncates from character zero.** The model is only ever shown a
   window. The new-drug definition sits ~1,800 characters into a 4,000-character
   chunk, so with a 750-character window the classifier was handed an Ethics
   Committee proviso and told it was the definition of a new drug. **The anchor
   was right and the view of it was wrong** - the same failure as the relevance
   gate in §6c, where the text was present and the window could not reach it.

Fixed three ways:

- **Anchor on the defining clause's own wording, not on the term.**
  `"formulations containing only such ingredients"` occurs once;
  `"patent or proprietary medicine"` occurs wherever the statute uses it.
- **Prefer a candidate with a defining cue beside the phrase**
  (`_is_definitional`, ±240 chars), falling back to the old rule rather than
  resolving nothing.
- **`anchor_excerpt()` centres the window on the phrase.**

`verify_anchors()` now checks what is actually **shown**, which is the check that
would have caught this. The cue test is deliberately NOT part of verification:
the D&C Act extraction carries the §3 margin bleed and renders "means" as
**"mneans"** in the definitions clause, so a grammar-based assertion would raise
false alarms at startup. Anchor on the defined content, never on the grammar.

All six now resolve to and display the right provision - s.3(a), s.3(h), rule
122E "Definition of new drug", Schedule Y 1.1, regulation 2(b), s.3(aaa) -
verified by `tests/test_units.py`, which names each wrong resolution so it cannot
come back. Classification measured **5/5**, one product per category, each citing
the right act.

**`test_subject_scope` went 10/11 -> 11/11 and `test_gate_scope` 15/16 -> 16/16
immediately afterwards.** §6n had recorded both as retrieval variance on
low-trial checks. They were this.

### The static copy asserted law with no citation

`Home.tsx` `BLOOMS[].tease` and `exportMarkets.ts` `EXPORT_LANES[].use` shipped
as static strings with no citation and no validator behind them - *"Prior
approval of the National Biodiversity Authority is required before IPR on
biological resources"*, *"minimum IP standards WTO members must meet"*. That is
the fabricated-authority failure this whole pipeline exists to prevent, wearing a
caption's clothes.

All 22 now name a subject and invite the question; the legal content arrives from
retrieval with its provision attached. A guard in `test_units.py` greps both files
for assertive forms (`is required`, `must meet`, `prior approval of`) and **self-
tests that it would catch the original sentence** while not firing on a question
about the same thing.

Deliberately kept: *"PCT, Madrid and Nagoya sit in a separate corpus"* and
*"Section 3(p) is retrieved from this layer"* are claims about **this system**,
both backed by passing tests, not uncited claims about law.

### The trail is four sealed volumes

The 2x2 card grid of §6n showed all four answers at once, which is the same flaw
the vertical stack had: the reader met four paragraphs of legal prose with no
idea which one they wanted. Closed, a volume now shows only its numeral, its seal
and its title - **the closed shelf IS the summary**, and opening one is the
reader's choice about where to look. Two rows of two; an opened volume takes
~767px of its own row while its row-mate folds to a spine, and the other row does
not move.

**Opening a volume lights that step's sources in the rail and dims the rest.**
That is the product's whole claim as one gesture, and it replaced the separate
"Pin sources" button - two controls for one intention, and the one that mattered
was the one nobody pressed.

Three mechanics that had to be got right:

- **Width animates on `flex-grow`, not `width`.** Growing one panel must shrink
  the others by exactly what it takes, and flex already solves that.
- **The body is laid out at its open width and clipped.** Reflowing as the panel
  grows rewraps the prose every frame, which reads as a stutter.
- **`flex: none` on the title.** An element with `overflow: hidden` has an
  automatic minimum size of ZERO, so when the plate's contents outgrew a closed
  row, flex chose the title as the thing to shrink and took it to 0px -
  **present in the DOM, readable to a screen reader, invisible on screen.** Found
  by measuring the box, not by looking.

Below 860px it stacks on a CSS-only `0fr`/`1fr` reveal. `min-height: 0` on the
grid item is load-bearing there: a grid item defaults to `min-height: auto` and
refuses to shrink below its content, so the row never collapsed and a closed
volume leaked its footer.

### A dark surface, owned in one place

A paper/dark switch in the site header (also `Shift+D`, ignored inside text
fields), applying to Consult, Export readiness, Treaty routes and Sources. First
visit follows `prefers-color-scheme`; `color-scheme: dark` makes native controls
and scrollbars follow.

Done by **overriding the design tokens under one class**, so components re-skin
themselves and none takes a theme prop. Only two rules needed hand-fixing - the
step medallion and the citation badge use a token as a FOREGROUND on an accent
fill, and inverting `--paper` would have made them dark-on-dark.

**That technique has one failure mode, and it bit.** Anything with a *hardcoded*
background and a *token* foreground inverts badly: the landing page's garden
section hardcodes a cream ground with `color: var(--ink)`, so the dark tokens
turned its heading cream-on-cream - present, selectable, no contrast. The landing
page is a fixed composition (dark hero, deliberately light garden) and now keeps
its own design in both modes.

A contrast sweep was written after that (walks every text node on all five pages
in both surfaces, resolves the first painted ancestor background, flags anything
under 2.2) and would have caught it before it shipped. Both surfaces are clean on
all five pages.

### Also in this phase

| Change | Note |
|---|---|
| Treaty routes back on their own page (`/treaties`) | A lane answers *what an instrument says*; the readiness report assesses *a product against one*. Stacking them made the readiness form read as a preamble to a link list. |
| The pointer is the logo's leaf | A real `cursor` image, not a follower element - a follower is two pointers at once and the system arrow wins the eye. **Hotspots must be integers**: a fractional one silently invalidates the declaration and the arrow returns. |
| Escalation copies a practitioner brief | It opened a `mailto:` with an *empty recipient* - a draft addressed to nobody, which looks like a working referral. There is no facilitator queue behind this build and inventing an address would be worse than admitting it. |
| The gauge lost its card | The white panel made a measuring instrument look like a form field. It sits on the surface in both modes now, carrying itself through depth. |
| Export form's claims checkbox rendered a sentence in letterspaced caps | It is a `<label>` inside `.readiness-field` and inherited the field-name style. |
| Treaty lane CTA moved off **clay** | Clay means a limit or a refusal; the lane opens a source view, which is what indigo means. |
| Five superseded reports deleted, `PROJECT_STATUS.md` added | See §9. |

### The backspace trap bit twice more - three times in this project

`\b` written through a shell heredoc became a literal `0x08` BACKSPACE **twice**
in this phase: once in `STRUCTURAL_DIVIDER` (the guard was inert, so a chapter
heading inherited the section above it) and once in the static-copy guard's
regex, where it matched nothing and **passed vacuously**.

The pattern compiles, looks perfect in every rendering, and matches nothing.
Two defences, both worth keeping:

1. `test_units.py` sweeps every backend and test module for control characters.
2. **Any new guard carries a self-test proving it would catch the thing that
   prompted it.** That is the only reason the second one was caught.

Build the pattern from `chr(92) + "b"` rather than writing the escape.

### Verified at the close of this phase

Cold backend, rate limiting disabled:

```
tests/test_units.py            190/190   (+22: anchors, static copy)
tests/test_security.py          25/25
tests/test_gate_scope.py        16/16    (was 15/16 - the anchor fix)
tests/test_subject_scope.py     11/11    (was 10/11 - the anchor fix)
tests/test_legal_advice.py      15/15
tests/e2e_api.py                39/39
tests/benchmarks.py             92/94
UI regression (Playwright)      23/23
tests/test_flagship.py           3/4     TKDL naming 4/5 - the §6f variance
frontend tsc --noEmit clean · npm run build clean · control-character sweep clean
classification                  5/5 categories, each citing the right act
/health                         anchor_problems: []
```

### Known still open

Unchanged from §6n except where noted above:

- **Retrieval dilution on compound questions** - "Can I patent it, and what
  licence do I need?" retrieves only D&C licensing rules. A *pure* patentability
  question retrieves 3(d)/3(e)/3(o)/3(p) correctly. The fix is §6m's
  reserved-slots pattern applied to expansion formulations; still not taken,
  because it changes core retrieval and needs its own measurement.
- **"What is ABS?"** reaches food and drug regulation rather than the Biological
  Diversity Act on roughly 1 run in 3.
- Confidence remains uncalibrated - responsive across four bands is not the same
  thing.
- Patents Act s.3(p) still unreachable by search (§6g margin bleed).
- Duplicate Biological Diversity Rules 2024 (~184 chunks) - §6g decision stands.
- Hindi still falls back to dense-only retrieval, and the degradation is
  invisible.
- **The OpenRouter key exposed by the §6j traversal bug has still not been
  rotated.** The hole is closed; the key is still compromised. This is the only
  item on this list that is not a trade-off.


---

## 7. Notes for Person B (corpus/ingestion owner)

Your work was kept intact. What changed and what deliberately did not:

- **`build_chunks.py`** — logic untouched. Only the path defaults moved to the new layout:
  `--root` now defaults to the repo root (was: the script's own folder), `--input-dir` to
  `data/corpus`, `--zip-path` to `data/corpus.zip`. Outputs now land in `data/raw_text`,
  `data/chunks`, `data/logs`.
  Note this script **wipes and regenerates** its output dirs on every run — that is why the
  log dir was moved out of `pipeline/`; pointing it there would have deleted the scripts.
- **`build_vector_db.py`** — logic untouched, path defaults now resolve from the repo root
  so it runs from any working directory.
- **`test_retrieval.py`** — **kept exactly as you wrote it**, as a dev sanity tool.
  It is *not* imported by the backend, for two reasons worth knowing:
  1. `test_retrieval.py:42` force-routes any query containing "trademark" to
     `act_subtype="trademark"`. That is keyword special-casing, which the PS
     generalisation requirement rules out for the app path.
  2. The Hindi term-expansion dict is multilingual work, which Part C defers.

  Both are perfectly reasonable in a test script. The app's `retrieval.py` reimplements
  search without them.
- **Docs** — `Corpus_Pipeline.md` and `vector_database.md` moved to `docs/` and their stale
  paths corrected (they pointed at `output/02_chunks/`, which no longer exists).

---

## 8. Running it

See `README.md` for full setup. Quick reference (Windows):

```
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r pipeline\requirements.txt

# Build the vector DB (~1.1 GB model download on first run)
.venv\Scripts\python.exe pipeline\build_vector_db.py

# Sanity-check retrieval
.venv\Scripts\python.exe pipeline\test_retrieval.py
```

A generation key must be set in `.env` (copy from `.env.example`) before any
classification or generation phase will run. **Which variable holds it is chosen by
`IPSAKTI_API_KEY_ENV`** - currently `GEMINI_API_KEY`; set it to `OPENROUTER_API_KEY`
to go back to OpenRouter. See §6k.

**LLM access goes through OpenRouter**, not the Anthropic API directly:

- Endpoint: `https://openrouter.ai/api/v1` (OpenAI-compatible `/chat/completions`)
- Client library: `openai`, **not** `anthropic`
- Default model: **`gemini-3.5-flash-lite`** via Google's OpenAI-compatible endpoint.
  Set in `.env`; comment those four lines out to return to OpenRouter. OpenRouter's
  free tier was exhausted during the Phase 12 evaluation - see §6k.
- Upgrade path: set `IPSAKTI_MODEL=anthropic/claude-sonnet-5` once the account has
  credits ($2/M in, $10/M out, roughly $0.03 per full query). No code change needed.


---

## 6h. Phase 10 - polish and demo readiness

### One process, one port

`backend/app/main.py` now serves the built frontend from `frontend/dist` and exposes the
API at **both** `/health` and `/api/health`. The browser always calls `/api/*`; Vite proxies
that in development, and in production the same server answers it. Two servers and a proxy
is fine while developing and a liability during a demo - one more thing to have forgotten
to start.

- Demo / deploy: `npm run build`, then run uvicorn, open **http://127.0.0.1:8000**.
- Frontend work: keep Vite on 5173 for hot reload; it proxies to 8000 unchanged.
- The static mount is last and the SPA fallback never shadows an API route (verified:
  `/`, `/api/health`, `/health` and `/some/route` all behave correctly).
- Bare paths are kept because `tests/e2e_api.py` and `tests/benchmarks.py` use them.

### `tests/demo_check.py`

Run ~10 minutes before demoing. It verifies health and anchor resolution, **warms the answer
cache** with the planned questions (~15s each cold, instant afterwards), asserts the flagship
still produces Section 3(p) and TKDL, and prints a suggested running order. Exits non-zero if
anything is wrong, so a problem surfaces before an audience rather than during.

**The cache is in-process. Warming it and then restarting the backend throws the warm-up
away.**

The running order is chosen so each question demonstrates something different: the flagship,
a second regime (proving it is not one hardcoded answer), ABS, a refused false premise, a
wrong-country refusal, a wrong-subject refusal, and finally a follow-up to show conversation
memory.

### Verified at the close of Phase 10

`benchmarks.py` 94/94 · `e2e_api.py` 24/24 · `demo_check.py` all assertions pass ·
python and typescript compile clean.


---

## 6i. Confidence indicator, category comparison, and the UI rebuild

### Confidence - and why it is NOT a similarity score

`backend/app/confidence.py`. The obvious implementation is a distance threshold, and it does
not work on this corpus. Measured twice:

    dense distance   in-corpus 0.2469-0.3598 | out-of-corpus 0.3696-0.3951
    BM25 score       in-corpus 11.21 -31.16  | out-of-corpus 11.95 -26.29

Both overlap. The teammate's build used raw distance and consequently rated a **US/FDA
question `high` confidence** while answering it from Indian food law. A badge that is
confident in the dangerous direction is worse than no badge.

Ours is computed **after validation**, from what actually survived:

| signal | weight | meaning |
|---|---|---|
| steps that kept a citation | 0.45 | did each substantive step stay sourced? |
| distinct sources | 0.30 | one act corroborating itself is not corroboration |
| dense/lexical agreement | 0.25 | did two independent retrievers pick the same passages? |
| rejected citations | x0.80 | the model tried to cite something unverifiable |

Plus a hard cap: **a single-source answer can never be "high"**, however cleanly cited.
Observed in testing - full step coverage and perfect retrieval agreement pushed a
single-source phytopharmaceutical answer to 0.80, which is not honest given the known corpus
gap there.

`confidence_reasons` ships with every answer and the UI shows it on click, so the score can be
interrogated rather than trusted.

### Category comparison (`/compare`)

`backend/app/comparison.py`. Same product, four categories, four different IP postures, each
cited. This is the PS's central claim - a classical formulation faces the 3(p) bar while a
phytopharmaceutical has a real pathway - made visible instead of asserted.

**Cost design:** the naive version runs the pipeline once per category, about nine model
calls. This retrieves **once** and asks for the contrast in **one** generation call, so a
comparison costs roughly what a single question does. Measured ~19s for four categories.

Citations are validated identically to a normal answer. Where the evidence does not cover a
category, that card says so and shows no sources - observed working: "Not addressed by the
supplied evidence" for `new_drug` on an ashwagandha query.

Models write chunk ids into prose despite being told not to; `_CHUNK_ID` strips any that slip
through, since the cards already carry them.

### `needs_clarification` no longer blocks the answer

Previously an undetermined category stopped everything and asked. On a free model the
classifier asks *inconsistently*, so the same follow-up would answer on one run and stall on
the next - the one benchmark failure that kept recurring.

Now: if retrieval succeeded, we answer what the evidence supports, tell the generator the
category is unsettled so it names where the answer would differ, and carry the clarifying
question **alongside** the answer. The previously flaky case went from 2/3 to **3/3
answering**, and it is better product behaviour regardless - a question is a nudge, not a
dead end.

### UI

- **Two modes** in the composer: *Ask a question* / *Compare categories*.
- **Confidence badge** above the verdict, expandable to its reasons.
- **End session** button (replaces the vaguer "Clear"), with a live count of the session.
- Older consultations collapse to one line; each can be removed individually.
- Answers can now carry an open question in a haldi panel beneath the trail.
- Example chips are now labelled by what they demonstrate, and one of them opens
  comparison mode.

### Verified

`benchmarks.py` **94/94** · `e2e_api.py` **24/24** · typecheck and build clean.


---

## 6j. Post-audit hardening — the fixes from `COMPARISON_REPORT.md` §6

Revision 2 of the comparison report audited **our own** build and found nine defects the
earlier round had not looked for. This section records what was fixed and, more usefully,
what each one teaches.

### The one that mattered: arbitrary file read, and the API key with it

`main.py`'s SPA catch-all joined an attacker-controlled URL path onto a directory and served
whatever came out. Starlette percent-decodes the path, so `GET /..%2f..%2f.env` returned
`.env` — the live OpenRouter key — in plaintext over HTTP. Every source file was readable the
same way. It existed **only in the one-process demo/deploy mode** we intend to present from.

`resolve_static()` now resolves the candidate and checks `is_relative_to(DIST_ROOT)`.

Two things worth carrying forward:

1. **Containment must be checked after resolution, never by pattern-matching the string.**
   There are two escapes, not one. Traversal (`../../.env`) is the obvious one. The other is
   **anchor replacement**: `Path("dist") / "C:/Windows/win.ini"` *discards the left operand*
   and returns the absolute path. No amount of `..` filtering catches that; a containment
   check catches both. `tests/test_security.py` covers both classes.
2. **Checking for a secret at rest is not checking for a route that reads files.** Revision 1
   verified the key was gitignored and absent from the bundle — both still true, both
   irrelevant to this bug.

### Failure modes must be distinguishable, not merely safe

Three separate defects were the same mistake: a degraded state that looked identical to a
healthy one.

- **`expand_query()` failed soft** and returned `[question]`, indistinguishable from a
  question needing no rephrasing. Measured: with expansion off, the flagship benchmark does
  **not retrieve `DOC020_chunk_116` (Section 3(p)) at all** — it returns patent-office
  *procedure* — yet still answered confidently with real citations. It now returns an
  `Expansion` carrying `ok`, and the answer carries `search_degraded` + `degraded_reason`,
  rendered above the answer. Expansion stays soft (its absence costs recall, not
  correctness); the jurisdiction gate stays fail-closed. **That asymmetry is deliberate —
  document it rather than "fixing" it.**
- **A generation outage reported `NO_EVIDENCE`**, which the UI renders as "nothing here
  covers that", telling users to rephrase a perfectly good question. Now `GATE_UNAVAILABLE`.
- **Unknown `/api/` routes returned `200 text/html`** from the SPA fallback, so `response.ok`
  was true and the client parsed `index.html` as JSON. Now 404 JSON. `/docs` and
  `/openapi.json` are opt-in via `IPSAKTI_ENABLE_DOCS`.

### The headline was the hole in the citation guard

`Answer.headline` — the sentence users actually read — was the only model prose reaching them
unvalidated. Steps get their content *replaced* when no citation survives; the headline was
passed through verbatim. It now carries `headline_citation_ids`, validated against the same
allowed set, and `headline_unsourced` when nothing backs it. It is **not** dropped when
unsupported: a correct one-line answer is still useful, it just must not *look* sourced.

*The general lesson: when you add a field to a validated response, ask what validates it.*

### A confidence badge that always said "high" was not a badge

Measured across every substantive answer in the audit: **5 of 5 scored `high`.** Three causes,
all fixed:

- The agreement component tested "did each retriever see this chunk anywhere in its 40-deep
  candidate list" — which nearly everything in the final top-12 satisfies. Every answer
  emitted the identical reason string. A 0.25-weighted component was a **constant**. It now
  requires both retrievers to have ranked the passage inside `AGREEMENT_RANK_CUTOFF`.
- The rejection penalty was multiplicative (×0.80) and could not change the outcome in the
  case that mattered: a perfect 1.0 became exactly 0.80, still above `HIGH_THRESHOLD`. Now
  subtractive per rejection, **plus** a hard cap — an answer that cited something
  unverifiable cannot be "well supported".
- **It is still not calibrated.** No labelled data exists. The construction is defensible;
  the mapping to correctness is unmeasured. Do not claim otherwise to a judge.

### `act_subtype` was wrong for 39% of the corpus, and the bug was masked

`build_chunks.py::classify()` matched subtype against the **filename**.
`The_Drugs_and_Cosmetics_Rules_1945.PDF` matched nothing — the underscores meant the
"drugs and cosmetics" marker never appeared — so 854 chunks (35% of the corpus), including
**Rule 122-E and Schedule Y**, were labelled `other`.

The damage was in retrieval: `CATEGORY_REGIME_HINTS` maps `PHYTOPHARMACEUTICAL` to
`drug_regulatory`, so the hint boosted the 82-chunk *Act* and demoted the 854-chunk *Rules*
that actually govern it. **The hint pointed away from the right law** — harmless only because
`REGIME_BOOST` is 0.0. Anyone who "improved" retrieval by raising that constant would have
made phytopharmaceutical and new-drug answers worse.

Now: filename first (normalising `_`/`-` to spaces), then `infer_subtype()` over the
document's own text by **marker frequency**. Frequency, not first-match, because position is
meaningless here — `ABS Guidelines.pdf` is a bilingual Gazette whose first ~47,000 characters
are Devanagari, so its first English marker sits halfway through the file.

Result: **`other` went from 951 chunks to 0.** All 26 documents are correctly typed. Chunk
ids and chunk text are **byte-identical** to the previous build, so the vector DB only needed
a metadata update — not a 28-minute re-embed.

*Two lessons: filenames are not metadata; and a masked bug is still a bug — it just waits.*

### The gate had drifted back to judging completeness

Measured: *"Cite the exact section that ALLOWS patenting a classical churna"* abstained
`out_of_scope` on **2 of 4 runs**. The gate was reasoning "no such section exists, so these
passages don't answer it" — the completeness-vs-scope confusion §6c was written to prevent.

`RELEVANCE_PROMPT` now states explicitly that **passages contradicting the question are
relevant**: "there is no such provision, and here is the one that governs instead" is an
answer, not a refusal. After the change: **3/3 on two different false-premise phrasings**,
with off-topic and foreign-jurisdiction refusals unchanged at 3/3.

### Everything else

| Fix | Note |
|---|---|
| History capped at 8 and **rejected** longer with a 422 | Every session broke on its 9th question. Server now truncates via a validator; client also slices. Neither side should depend on the other's limit. |
| History entries had no length cap | Same ceiling as `question` (`MAX_QUESTION_CHARS`). They land in an LLM prompt too. |
| No rate limiting on endpoints costing 3-4 LLM calls | `ratelimit.py`, per-client fixed window, `settings.rate_limit_*`. Set to 0 to disable — the suites do, since a warm cache fires faster than any human. |
| Raw exception text returned to clients | Logged server-side, generic message out. |
| Frontend `fetch` had no timeout or cancel | `AbortController`, 90s deadline, visible **Stop** button. `CancelledError` vs `TimeoutError` so a deliberate stop is not shown as an error. |
| `retrieve()` searched `queries[0]` twice | Once for thresholds, once in the fusion loop. Now computed once. |
| Suites reported cache hits as fast answers | `e2e_api.py` flags any sub-second answer as CACHED. **Restart the backend before quoting latency.** |
| Doc chunk-count drift | Corrected; `docs/Corpus_Pipeline.md` now carries a standing note to update counts on every pipeline run. |

### Free-model reality — measured, and it constrains everything

Probing all 19 free OpenRouter models on our key: **only `minimax/minimax-m3:free` and
`minimax-m2.7:free` are reachable.** The other 17 return 429 `openrouter_free_tier_daily` —
the account's free cap is **50 requests/day and it is exhausted**. MiniMax is exempt
(sponsored), which is why it still answers.

So `fallback_models` is currently **decorative**, and naively populating it made things worse:
4 retries × 3 unreachable models ≈ 48s of dead air before failing. `llm.py` now detects a
daily-cap 429 (waiting cannot help) and skips to the next model immediately, and the OpenAI
SDK's own `max_retries` is set to 0 because it was stacking a second retry layer inside ours.
**Failover: ~48s → 5.4s.** M2.7 is not a viable fallback either — it truncated mid-JSON at 250
tokens on one trial and returned empty content on the next.

$10 of credits unlocks 1000 free-model requests/day and makes the fallback list real.

### Verified at the close of Phase 11

Cold backend, rate limiting disabled, frontend rebuilt:

```
tests/test_security.py    25/25      (new - traversal, anchor replacement, no regression)
tests/test_units.py       48/48      (new - confidence, conversation, validation, limiter)
tests/e2e_api.py          37/37      (was 24 - added /compare, headline, routing)
tests/benchmarks.py       93/94
frontend tsc --noEmit     clean      npm run build clean
```

The one benchmark miss was **F1 not naming TKDL on that run**. Re-measured immediately after
with the cache cleared: **4/4 runs cite 3(p), name TKDL, and classify `classical_generic`.**
Free-model variance, not a regression — which is exactly why §6f's warning stands: **re-run
the suites before the demo rather than trusting a past green.**

### Known still open

- **The OpenRouter key has not been rotated.** The key in `.env` is byte-identical to the one
  read out through the traversal exploit. The hole is closed; the key is still compromised.
- Confidence remains uncalibrated (no labelled data).
- Duplicate Biological Diversity Rules 2024 (~184 chunks) — decision to leave it stands (§6g).
- Patents Act s.3(p) still unreachable by search (margin bleed, §6g).
- Hindi: BM25 tokenises Devanagari to `[]`; answers come back in English only. Query
  expansion masks the recall loss, which means Hindi depends on the same call that §6.3 made
  visible.
- Audit log and human-escalation (PS "expected solution", Version B has both) — **not built**;
  deferred to the next-level pass along with the UI work.

---

## 6k. Phase 12 — the fixes from `TEST_RESULTS.md`

A two-model evaluation (`TEST_RESULTS.md`, 6 Sep 2026) ran the 23-question manual
checklist plus two system checks against MiniMax M3 and Gemini 3.5 Flash Lite. This
section records what was fixed afterwards. **Three of the findings had a different root
cause than the report concluded**, and those corrections are the most useful part of this
section — the report's diagnoses are wrong in ways that would waste an afternoon.

### The single most important correction: history never reaches the gate

The report's headline finding was that the relevance gate "invents corpus gaps when
conversation history is present", from an A/B where a trademark question was refused
mid-session and answered standalone. **That mechanism does not exist.** `history` is
consumed by exactly one function, `contextualise()` (`generation.py`), and the gate never
sees it. Measured over four trials per arm:

    trademark, standalone      3 refused / 1 answered
    trademark, 6-turn history  2 refused / 2 answered
    copyright, standalone      1 refused / 3 answered
    copyright, 6-turn history  0 refused / 4 answered

History made no difference. The A/B was one sample per arm of a nondeterministic failure.
The real causes were three, all in **what the gate could see**:

1. **The distance outer bound was computed on the user's raw wording**, not on the
   formulations that actually retrieved the evidence. `"What is ABS?"` scores 0.454
   against `MAX_DENSE_DISTANCE = 0.45` and was refused *before the LLM gate ran*, while
   all twelve retrieved chunks were the Biological Diversity Act and the ABS Guidelines.
   The expansion "Access and benefit sharing" matched at rank 0. `retrieve()` now takes
   the best reading across all formulations.
2. **The gate read only the first six passages.** For "can I trademark the name of my
   Ayurvedic product?", the Trade Marks Act chunks land at ranks **6 and 8** — "Ayurvedic
   product" pulls the 949-chunk D&C Rules above them — so the gate saw five
   drug-regulation passages and was asked whether trade marks were in scope. Window is now
   the full `GATE_PASSAGE_WINDOW = 12`.
3. **The gate never saw the expansions**, so it judged wording that had retrieved nothing.
   `RELEVANCE_PROMPT` now carries a `SEARCHED AS` block.

The prompt also now states that **the passages are a search result, not an inventory**: a
body of law missing from twelve retrieved chunks is not evidence the corpus lacks it.
`_scope_message()` is the backstop — it drops any refusal reason mentioning our own
holdings, because a reason describing the *question* never needs to.

**Regression suite: `tests/test_gate_scope.py`** (16 checks), which asserts among other
things that history does *not* change the verdict, so the wrong diagnosis cannot be
re-adopted.

### "The cited source" was our own code, not model chatter

The report attributed the phrase spliced into answers on both models to model behaviour.
It was `strip_chunk_ids()`, which **substituted the literal string `"the cited source"`**
for any chunk id the model wrote inline — in exactly the mid-sentence position the id had
occupied. Ids are now removed outright.

The same three lines carried a second, invisible bug: the tidy-up replacement was a
literal **`\x01` SOH byte** instead of the `\1` backreference, so cleaning `" ."` deleted
the full stop and inserted a control character. Committed that way.

A third instance of the same class was then found by sweeping the bytes:
`comparison.py`'s `_CHUNK_ID` used literal **`\x08` BACKSPACE** bytes where `\b` word
boundaries were intended, making the pattern **unmatchable** — so the chunk-id stripper
§6i describes has been silently inert, and raw ids could reach the comparison cards.

**`tests/test_units.py` now sweeps every backend module for control characters.** All
three bugs were invisible in every rendering of the source; only the bytes showed them.

### Tests 6 and 7 were an expansion failure, not a generation failure

A neutral product description ("I've made a neem-based face cream for external use only")
was answered with three steps of Section 3(p) patent law. The cause was `expand_query`,
which rewrote it into *"patentability of neem based formulations"* and *"patent
eligibility of cosmetic preparations"*. Retrieval then correctly returned patent law and
generation correctly answered about patents — every stage faithful to a question the user
never asked. Patent vocabulary is the densest in this corpus, so it wins any ambiguous
rewrite.

`EXPANSION_PROMPT` now says: translate the vocabulary, never change the question; and
where a message raises no legal issue, expand toward the regime that *governs the product*
rather than reaching for patentability.

**`tests/test_subject_scope.py`** carries the positive controls that matter: the flagship
must *stay* patent-framed, and a naming question must still reach trade mark law. A fix
that merely suppressed patent vocabulary everywhere would break the demo.

### Fabricated authority in prose — the guard nobody had written

`validate_ids()` proves a citation **id** is real and was retrieved. Nothing proved that
*"under Section 3(e)"* in the sentence beside it was backed by a chunk containing Section
3(e). Measured on the flagship: **2 of 6 cold runs named Section 3(e), which appears in
none of the retrieved evidence** (0 of 4 retrieval checks). The citations shown alongside
were all valid, so the fabricated provision looked sourced — worse than an invalid id.

`citations.provision_support()` / `strip_unsupported_provisions()` now remove the
**sentence** carrying a provision no retrieved chunk contains (the smallest unit that can
go without leaving a claim standing in a wreck of grammar), and report it as
`Answer.unsupported_provisions`, rendered in the existing Citation-guard panel. Removal
triggers only when the provision is absent from the **whole evidence set** — a provision
retrieved but attributed to the wrong chunk is sloppy citing, not invention.

Watch the false-positive direction: the first version deleted a good sentence because
*"the Biological Diversity **Rules 2024**"* matched as "Rule 2024". Four-digit years are
now excluded.

### Other fixes

| Finding | Fix |
|---|---|
| `is_too_vague` refused *"What is a Geographical Indication?"* and *"What is ABS?"* — deterministic, both models | Question **form**, not word count: no content words is always vague; 1-2 content words passes only if something was actually asked. Corpus frequency was measured as an alternative and does not separate — "abs" occurs in 2 of 2,457 chunks and so does "something". |
| Hindi questions measured as having **zero** content words | Python's `\w` excludes combining marks, so "क्या" tokenised as `['क','य']` and both were dropped by the 2-character minimum. Marks now attach to their letters; English is bit-identical. |
| Outcome-prediction questions answered on Gemini, refused on MiniMax | Nothing **asked**. `personal_advice` is now an explicit third dimension of the gate, checked before subject matter (the Patents Act does govern infringement, so it is on-subject), mapping to `AbstentionKind.LEGAL_ADVICE`, which escalates. Verified on two models. |
| Flagship named TKDL inconsistently | Step 3 must re-read the evidence for a named register/authority/mechanism before concluding none exists. Also **restored the §6f relevance-ordering rule, which had been lost from the prompt entirely** — 3(p) citation went 3/5 → 5/6. |
| `LIMITED` confidence unreachable across ~50 answers | Agreement was scored over the **retrieved** top-5, so an answer with two abstaining steps still collected the full 0.25 for passages nobody cited. It is now scored over **cited** passages, plus two caps: ≤half the steps sourced → `LIMITED`; any abstaining step → cannot be `HIGH`. |
| `tests/test_security.py` reported 12 failures | Not a hole — the test compared an HTTP body against `read_text()`, which applies universal-newline translation. `index.html` also contains a stray `CR CR LF`, so normalising only CRLF was not enough. **25/25.** |

### Provider configuration is now configuration

OpenRouter's free tier (50/day) was exhausted during the evaluation, and
`minimax-m3:free` additionally hit a provider-side daily cap that credits do not lift. The
model was therefore switched to Gemini — but only via shell exports, which meant the
documented start command still ran on a dead model.

- `settings.llm_base_url` replaces `openrouter_base_url` (old env name kept as an alias).
- `settings.api_key_env` names **which variable holds the key**, so running on Gemini no
  longer requires putting a Gemini key in a variable called `OPENROUTER_API_KEY`.
- `.env` carries the four lines; commenting them out returns to OpenRouter.

**Use `gemini-3.5-flash-lite`, not `gemini-3.6-flash`.** 3.6 is a thinking model: at a
300-token budget it returned `completion_tokens: 7` and `finish_reason: length`, so the
gate's 250-token cap yields truncated JSON and every question fails closed. Flash Lite
returns clean JSON in ~1.5 s.

Free-tier Gemini enforces a per-minute limit; the run logged **13 automatic fallbacks** to
`gemini-3.1-flash-lite` with backoff and **no request failed as a result**. The
retry/fallback path §6j called "decorative" is now demonstrably load-bearing.

### Suites as of this phase

```
tests/test_units.py         133   unit - includes the control-character sweep
tests/test_security.py       25   traversal, anchor replacement (was 13/25)
tests/test_gate_scope.py     16   scope refusals, 10-turn session, history-invariance
tests/test_legal_advice.py   15   outcome prediction refused + controls still answered
tests/test_subject_scope.py  11   right regime, with flagship/naming positive controls
tests/test_flagship.py        4   5+ cold runs of the official benchmark
frontend/src/useSessions.test.mjs  12   session titles and dates
```

### Still open

- **`top_k` and the rank-23 outlier.** The Section 3(p) chunk is retrieved 8/8 but landed
  at rank 23 once, outside `top_k = 12`. Capturing it needs `top_k >= 24`, doubling the
  evidence in every prompt. Not taken — a global tuning change for a 1-in-8 case.
- **Retrieval dilution on product-noun-heavy IP questions.** "Can I trademark the name of
  my Ayurvedic product?" puts only 1-2 Trade Marks Act chunks in the top 12; the rest is
  D&C Rules. The gate no longer refuses it, but a thin answer is still possible.
- **Confidence remains uncalibrated** against labelled data. It is now demonstrably
  *responsive* (0.5 on a corpus gap, 0.94 on the flagship) and all three levels are
  reachable, which is more than could be said before. That is not calibration.
- Duplicate Biological Diversity Rules 2024 (~184 chunks) — §6g decision stands.
- Patents Act s.3(p) still unreachable by search (margin bleed, §6g).

---

## 6l. Phase 13 - the international corpus, the progressive flow, and the frontend merge

Two things happened in this phase: `03_international/` stopped being an empty
promise, and the parallel build's frontend was merged in. Both are recorded here
because both changed facts written earlier in this file.

### The corpus is now two corpora, and they are kept apart in code

**3,282 chunks from 37 PDFs** - `national` 2,457 (unchanged, byte-identical) and
`international` 825 across **eleven instruments**: TRIPS, CBD, Nagoya, WIPO
GRATK 2024, PCT, Madrid, Hague, Budapest, the European Patent Convention, EU
Directive 2004/24/EC, and the FDA Botanical Drug guidance. 3,275 are embedded
(7 remain too short to embed, the same Schedule M headings as always).

The problem statement requires the two answer-sets to be "visibly separate" and
"never conflated", so separation is enforced at the **evidence set**, not in the
prose:

- Chroma is queried with `where={"jurisdiction": ...}`.
- **BM25 gets one index per jurisdiction**, not one index filtered afterwards.
  IDF is computed over the corpus the index is built on: a single mixed index
  would score "patent" against 3,275 chunks of two legal systems and rank by a
  document frequency that describes neither.
- The relevance gate carries its own rules per side, and nudges across rather
  than answering across - a treaty question asked in the national corpus is
  refused *with a pointer to the toggle*, never answered from Indian law.

Measured on the rebuilt index, expansion and gate off so it holds even while
every provider is capped: **12/12 evidence sets stayed inside their own corpus**,
and both newly added instruments rank #1 for their own subject matter.

### Adding two PDFs renumbered a third of the database - and there is now a tool

`doc_id` is assigned by sorted position, so dropping `09_EPO...` and
`10_EU_Directive...` into `03_international/` shifted every document that sorts
after them. Against the existing vector DB that meant **576 ids no longer
existed, 200 ids now named a different passage, and 668 were new**. Only 2,407
of 3,183 were still correct.

The dangerous part is the middle number. A resume-style top-up would have added
the 668 and left 200 ids whose stored text belongs to *another document* -
citations that resolve, look clean, and quote the wrong instrument. A sampled
check caught it; an id-set comparison alone would not have.

`pipeline/repair_vector_db.py` does the minimum that is provably equivalent to a
full rebuild - delete stale, re-embed changed, embed new, refresh drifted
metadata - and then verifies **every id, passage and metadata field** against
`all_chunks.json`. 868 chunks re-encoded instead of 3,275, and the outcome is
checked rather than assumed. `--limit` makes it restartable, because a full pass
was OOM-killed three times on this machine.

*The rule from 6g still stands and is now load-bearing: never hardcode a
chunk_id. This phase is what that rule was protecting against.*

### Progressive disclosure, because a second jurisdiction is a second answer

The international position is **not** fetched with every question. The user gets
the national answer, and then chooses:

    ask (national)  ->  reveal the other side  ->  compare  ->  next steps

Each step is an explicit click and its own generation. Nobody pays three model
calls for a side they did not want, and - more importantly - the comparison
describes the two answers **already on screen**: both are POSTed back to
`/compare-jurisdictions` rather than regenerated, so what the reader is told is
being compared is what they can actually see.

`jurisdiction_compare.py::_validate_point` enforces citation ownership **per
side**: a point's `national_citation_ids` must resolve to national chunks and
its `international_citation_ids` to international ones. A point that cannot
satisfy that is rejected, not softened. This is the difference between
separation as a prompt instruction and separation as a checked property.

`next_steps.py` may draw on both sides, and every step is labelled with the
jurisdiction it came from. `plain_language.py` rewrites a **finished** answer:
citations are copied in code, never re-emitted by the model, so plain English
cannot quietly acquire a source the legal wording did not have.

### The frontend merge - what was taken from the parallel build

Her build and ours are descendants of the same design (same palette, same
"printed legal opinion sheet" concept), which made this a graft rather than a
rewrite. Taken from hers, essentially unchanged:

| Ported | Why |
|---|---|
| `Root.tsx` + `Shell.tsx` (react-router) | The workspace was the whole product; it is now one destination among several. |
| `pages/Home.tsx` | A landing page that explains the two layers *before* the first question. |
| `pages/Export.tsx` | Ten treaty routes, each deep-linking into `/ask?j=international&q=...`. |
| `pages/Sources.tsx` | Links to the official registries, so a judge can check us. |
| `printBriefing.ts` | The consultation as a printable opinion sheet. |
| `index.css` (superset) + Fraunces | Her stylesheet is ours plus the landing/print work. |

Kept from ours: the whole answer pipeline, the session sidebar, the progressive
jurisdiction flow, the confidence badge, next steps, plain-language mode, and
the composer.

Three things changed on the way in:

1. **Language, log consent and health moved to `Root`.** Two copies of the same
   toggle in a header and a rail is two sources of truth for one preference.
2. **A deep link that names a jurisdiction now asks in it.** `?j=` and `?q=` are
   read in separate effects, so the submit closure still held the old
   jurisdiction and a treaty link would have been asked of Indian law. The
   link's own value is passed straight to `submit`.
3. **The landing page's claims were corrected.** It described a build where the
   jurisdiction is inferred from the question. Here it is an explicit toggle
   with a default and a nudge, which is the safer design - and a landing page
   that oversells the automation is a claim a judge can falsify in ten seconds.

### Which international handling was kept, and why

| | Hers | Ours | Kept |
|---|---|---|---|
| BM25 scoping | one index, filtered after scoring | one index per jurisdiction | **ours** - filtering after scoring leaves IDF computed over both legal systems |
| Query expansion | treaty vocabulary when international | one Indian-statute prompt for both | **hers** - a real defect in ours, adopted |
| Both layers at once | `export` mode, one prompt told to keep layers distinct | progressive reveal + comparison with per-side citation validation | **ours** - separation checked in code beats separation requested in a prompt |
| Layer detection | `auto` infers the layer | explicit toggle + a refusal that points at the other one | **ours** - the refusal is demonstrable; inference is one more thing to be wrong about |

### Verified at the close of this phase

```
vector DB repair        every id, passage and metadata field matches all_chunks.json
                        3,275 embedded - national 2,450 | international 825
jurisdiction separation 12/12 evidence sets stayed inside their own corpus
                        EPC and EU Directive both rank #1 for their own subject
/health                 3,275 chunks, anchor_problems: []
routing                 / /ask /export /sources -> SPA; /api/nope -> 404 JSON
tests/test_units.py     133/133
tests/test_security.py  25/25
tests/test_jurisdiction.py  6/6 (its two answer checks SKIPPED - see below)
frontend tsc --noEmit   clean      npm run build clean
```

The national flagship was re-checked end to end on the rebuilt index: classifies
`classical_generic`, cites Section 3(p) from the Manual of Patent Office
Practice, and names TKDL.

### Blocked, and it is capacity rather than behaviour

**All three free providers are daily-capped simultaneously** - Google
(`gemini-3.5-flash-lite`), Groq (`openai/gpt-oss-120b`) and OpenRouter
(`minimax/minimax-m3:free`, capped by shared free capacity, not by credits). The
chain does the right thing: it recognises a daily cap as unwaitable, skips the
rest of that provider, and fails in ~6s rather than hanging. The user is told
`gate_unavailable` - "I could not run the check, try again" - rather than being
given an answer the gate never approved.

So these remain **unrun on the new corpus**, not failed:
`benchmarks.py`, `e2e_api.py`, `test_flagship.py`, `test_subject_scope.py`,
`test_gate_scope.py`, `test_legal_advice.py`, `test_jurisdiction_compare.py`,
`test_style_and_steps.py`. Re-run them before demoing; do not quote a past
green.

$10 of OpenRouter credit, or any provider key with headroom, unblocks all of it.

### Known still open

- The FDA Botanical Drug guidance sits in `03_international/` although it is US
  domestic law. It is *reachable* under the international toggle, which is
  arguably wrong - the gate refuses foreign domestic authorisation questions, so
  nothing conflates, but the filing is untidy. Decide before demo day.
- `act_subtype` labels ~573 international chunks `design`; `infer_subtype()`
  reads document text by marker frequency and the Hague Agreement's vocabulary
  dominates. Harmless while `REGIME_BOOST` is 0.0 - and another reason not to
  raise it without measuring first (6j).
- Confidence is still uncalibrated.
- The OpenRouter key exposed by the traversal bug (6j) has still not been
  rotated.
