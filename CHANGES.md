# Changes -- national-scope hardening pass

Scope for this pass, per direction: **national law only** (international
treaty layer and full Bhashini-grade multilingual UI deliberately deferred),
but English/Hindi answer quality should be properly solid, and everything
else flagged as missing against the problem statement gets addressed at
whatever depth is realistic for a single-corpus local prototype.

## What changed

**Answer formatting** (`backend/rag_engine.py`, `frontend/app.js/styles.css`)
- Plain-summary answers now come back as **bold** lead line + `- ` bullets +
  *italic* caveat + a distinct "Key sources" line, instead of one run-on
  paragraph. A small Markdown-lite renderer (`renderAnswerMarkdown`) turns
  that into real `<strong>`/`<em>`/`<ul>` HTML client-side.
- The LLM-synthesis system prompt now asks for the same structure, so the
  optional LLM path and the plain-summary fallback path look consistent.
- Source excerpts over ~220 characters are shown truncated with a "Show full
  excerpt" toggle instead of a wall of statute text.

**Hindi/English retrieval quality** (`test_retrieval.py`, `backend/rag_engine.py`)
- `HINDI_LEGAL_TERMS` expanded from 5 entries to full coverage across every
  regime in the corpus (patents, trademarks, GI, copyright, designs, plant
  varieties, biodiversity/ABS, TKDL, drug/cosmetic/food regulation).
- `act_subtype` routing (previously trademark-only) now covers all regimes,
  in both English and Hindi, via `_route_act_subtype`.
- `ABS_TRIGGER_TERMS` gained the Hindi equivalents of every existing English
  trigger -- a Hindi-language biodiversity/export question used to silently
  skip the ABS/TKDL checklist; it no longer does.
- The escalation email (mailto) now writes its subject/body in Hindi when
  the question was Hindi, instead of always English. (This also fixed a
  pre-existing bug where the escalation email body was always blank --
  `question` wasn't being passed to the render function at all.)
- `run_eval.py` reports retrieval hit-rate and abstention rate **broken out
  by language** specifically so EN vs HI quality drift is visible, not
  averaged away.

**RAG hardening** (`test_retrieval.py`)
- `_dedupe()`: near-duplicate chunks (same Act + section + page) no longer
  eat multiple slots in the same top-k, which was crowding out genuinely
  different sources.
- `_split_subquestions()` + `_merge_result_lists()` in `rag_engine.py`:
  compound questions ("Can I patent X and do I need NBA approval for Y?")
  are heuristically split, retrieved separately, and merged/re-ranked by
  distance -- a single embedding pass was blurring both halves together
  before. Works for both `and`/`और`/`तथा` connectors.

**Lightweight knowledge-graph stand-in** (`_related_sources` in `rag_engine.py`)
- For the top-matching chunk, surfaces a few *other* passages from the same
  Act (ranked by page proximity) as a separate "Related provisions" panel.
  This is metadata-based, not a real entity/relation graph -- labelled as
  such in the UI copy so it isn't mistaken for the fuller graph phase the
  problem statement describes.

**Local audit log** (`log_interaction` in `rag_engine.py`)
- Every answered query is appended to `audit_log.jsonl` (question, confidence,
  category, ABS flag, escalate flag, timestamp -- no account/identity, no
  third-party transmission) unless the user's session has logging switched
  off. This is a first, honest step toward the DPDP-aligned posture the
  problem statement calls for -- it is **not** a compliance implementation
  by itself; retention limits, access control and a real consent-management
  flow are still undesigned.

**Evaluation harness** (`eval_set.json`, `run_eval.py`)
- 12 labelled EN/HI questions covering every regime in the corpus plus two
  deliberately out-of-corpus questions to check abstention.
- Reports retrieval hit-rate, citation completeness, safe-abstention rate,
  and ABS/TKDL flag accuracy, overall and split by language.
- Run with: `python3 run_eval.py` (needs the vector DB built first).

**Voice input** (`frontend/app.js`, `index.html`, `styles.css`)
- Browser-native Web Speech API dictation button, feature-detected (stays
  hidden on browsers without support, e.g. desktop Firefox). A small
  EN/हिं toggle sets the recognition language. No backend speech API, no
  key required -- this is the realistic slice of "voice experience"
  available without a paid STT integration.

## Explicitly still not done (out of scope for this pass, by your call)

- **International jurisdiction layer** -- no TRIPS / CBD-Nagoya / WIPO
  GRATK Treaty / PCT / Madrid / Hague / Budapest Treaty text in the corpus,
  so there's still no real jurisdiction toggle. `system_prompt` in
  `rag_engine.py` still says "India national law only" on purpose.
- **Full Bhashini-grade multilingual delivery** -- only EN/HI detection +
  templates + Hindi legal-term query expansion. No live translation
  pipeline, no additional Indian languages.
- **Real knowledge graph** -- `_related_sources` is a metadata proximity
  heuristic, not entity/relation extraction over the corpus.
- **Agentic multi-source orchestration** -- `_split_subquestions` is a
  connector-word heuristic, not a planner; it doesn't reason about *which*
  sources to consult, only splits an already-compound question.
- **Paid-source connectors** -- deliberately not faked; would need real
  user credentials/API access to a subscription service, which this
  environment doesn't have.
- **Production-grade DPDP privacy/security** -- the audit log is a first
  step, not retention policy, access control, or a consent-management UI.
