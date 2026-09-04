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

**2,457 chunks** from **26 Indian legal/regulatory PDFs** (2,342 before the post-comparison corpus fix - see §6g). All extracted cleanly with
pdfplumber; none needed OCR, none failed. Zero encoding corruption (no U+FFFD).

Chunk sizes: median 242 tokens, max 798, none over 900. 157 chunks are under 50 tokens.

### Metadata schema (every chunk)

| Field | Notes |
|---|---|
| `chunk_id` | e.g. `DOC014_chunk_011` — **this is the citation key** |
| `doc_id`, `file_name`, `folder` | provenance |
| `act_name` | 24 distinct values — use this for display citations |
| `regime_type` | 4 values: `drug_regulatory_classification`, `ip_statute`, `registry_guideline`, `pharmacopoeia_reference` |
| `act_subtype` | 12 values: `patent`, `trademark`, `copyright`, `design`, `geographical_indication`, `plant_varieties`, `biodiversity_abs`, `traditional_knowledge`, `drug_regulatory`, `food_regulatory`, `pharmacopoeia`, `other` |
| `jurisdiction` | **currently `national` for all 2,342 chunks** |
| `year`, `page_number`, `page_numbers`, `token_count` | |
| `section_or_clause` | **noisy — see below** |

### Coverage by regime

`01_classification` 882 · `02_national_statutes` 738 · `04_registries` 384 ·
`05_pharmacopoeia` 338 · `03_international` **empty (deferred, correct)**

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

3. **`jurisdiction` has exactly one value today.** The India/International toggle is real
   plumbing with one populated side — not fake UI. It becomes meaningful when
   `03_international` is populated in a later phase.

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

**Working agreement:** one phase at a time. Each phase ends with a summary, real verification
output, and an update to this file. No starting a phase whose dependency is not verified.

---

## 6a. Phase 1 findings - read this before writing `retrieval.py`

The vector DB is built: **2,335 chunks** in `data/vector_db/` (48 MB), collection
`ip_sakti_corpus`, model `intfloat/multilingual-e5-base`. Build took ~28 min on CPU.

7 of the 2,342 chunks were skipped as too short (<3 words). All 7 are bare Schedule M
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

Result over the full corpus: **887/2342 chunks (38%, measured before the §6g rebuild) get a verified section, 0 contaminated
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

`build_chunks.py` dropped any page matching a bare `CONTENTS`. The single page of
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

`OPENROUTER_API_KEY` must be set in `.env` (copy from `.env.example`) before any
classification or generation phase will run.

**LLM access goes through OpenRouter**, not the Anthropic API directly:

- Endpoint: `https://openrouter.ai/api/v1` (OpenAI-compatible `/chat/completions`)
- Client library: `openai`, **not** `anthropic`
- Default model: `minimax/minimax-m3:free` (free, 1M context)
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
