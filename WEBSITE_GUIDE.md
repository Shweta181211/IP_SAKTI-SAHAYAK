# IP Sakti Sahayak — Website Guide

This is the real, locally hosted website: a FastAPI backend (`backend/`)
serving a hand-built HTML/CSS/JS frontend (`frontend/`). One process, one
URL, no Node/npm build step required.

It reuses the existing retrieval backend as-is (`build_vector_db.py`,
`test_retrieval.py`) through a new orchestration layer, `backend/rag_engine.py`,
which adds:

- a **formulation-classification** flow (classical / patent-proprietary /
  new drug / phytopharmaceutical / Ayurveda-Aahar / cosmetic) that biases
  retrieval and states the IP posture for the chosen category,
- a **confidence indicator** derived from retrieval distance, with **safe
  abstention** (no synthesised answer) when nothing relevant was found,
- a rule-based **ABS / TKDL pointer** that fires when a query or its top
  chunks touch biological-resource / traditional-knowledge territory,
- an **escalate-to-human** prompt shown when confidence is low,
- **optional** LLM-grounded synthesis (fully off unless `ANTHROPIC_API_KEY`
  is set) — the app is a pure, safe retrieval demo without it.

The application is intentionally dependency-free on the frontend: no
Node/npm build step or second development server is required.

## 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

This installs the FastAPI server, local retrieval dependencies, and optional
LLM client used by the synthesis toggle.

## 2. Build the vector database (one-time, if `vector_db/` doesn't exist yet)

```bash
python build_vector_db.py
```

(See the note in `FRONTEND_GUIDE.md` about the `--chunks` default path — this
has already been fixed if you followed that guide.)

## 3. Run the website

From the **repo root** (not inside `backend/`):

```bash
python -m uvicorn backend.main:app --reload
```

Open **http://127.0.0.1:8000** in a browser. That's it — one server answers
both the page and its API calls (`/api/health`, `/api/formulation-categories`,
`/api/regime-types`, `/api/query`), so there's no separate frontend server
and no CORS configuration needed.

If you see a red "Vector database not found" banner in the page itself,
that means step 2 hasn't been run yet (or `vector_db/` isn't in the repo
root) — the message in the browser tells you the exact command to run.

## 4. Using the site

- **Step 1 in the left rail** — pick a formulation category. This narrows
  retrieval toward the right part of the corpus and shows the IP posture
  for that category (e.g. classical formulations face the Section 3(p)
  patent bar and are defended through TKDL, not a new patent).
- **Step 2** — optionally narrow by source type (drug/regulatory,
  IP statute, registry/guideline, pharmacopoeia).
- **Ask** a question in the chat box, in English or Hindi.
- Every answer shows a **confidence pill** (High / Medium / Low / No match)
  based on how close the retrieved text actually is to the question — low
  confidence means the app deliberately withholds a synthesised answer
  rather than guessing, and offers a "Request human IP facilitator review"
  link (a `mailto:` link — replace the placeholder address in
  `frontend/app.js` → `appendAssistantMessage()` with a real one).
- Questions that touch biological resources or traditional knowledge (by
  keyword, or because the top retrieved chunks are tagged that way) get an
  **ABS / TKDL checklist** callout.
- **Sources** at the bottom of every answer list the exact Act, section,
  page, regime type and similarity distance for every retrieved chunk —
  nothing in the reply text is invented beyond what's cited there.

## 5. Optional: LLM-grounded summaries

```bash
cp .env.example .env
# Set ANTHROPIC_API_KEY in .env
python -m uvicorn backend.main:app --reload
```

Then tick **"Synthesise a summary (LLM)"** in the left rail. The model is
instructed to answer only from the retrieved excerpts, cite every claim,
and refuse to guess when the excerpts are thin. This also requires the
`anthropic` package (already listed in `requirements.txt`). If the call fails
for any reason, the site falls
back to the plain retrieval summary rather than erroring out.

## 6. Files added in this stage

```
backend/
  main.py         — FastAPI app: routes + serves frontend/ as static files
  rag_engine.py    — classification, confidence, ABS/TKDL, optional LLM synthesis
frontend/
  index.html       — page structure
  styles.css       — visual design (forest-ink / parchment / turmeric palette)
  app.js           — fetches API data, renders the sidebar, runs the chat
requirements.txt   — added fastapi, uvicorn
WEBSITE_GUIDE.md    — this file
```

No existing extraction/chunking/embedding/retrieval file (`build_chunks.py`,
`build_vector_db.py`, `test_retrieval.py`, `all_chunks.json`) was modified.
`backend/rag_engine.py` imports `search()` from `test_retrieval.py` rather
than reimplementing it.

## 7. Known limitations / next steps

- **Confidence thresholds are a starting heuristic**, not calibrated against
  a labelled evaluation set — tune `CONFIDENCE_HIGH_MAX_DISTANCE` and
  `CONFIDENCE_MEDIUM_MAX_DISTANCE` in `backend/rag_engine.py` once you have
  real query logs.
- **Escalation is a `mailto:` link placeholder** — wire it to a real intake
  form/inbox before a public demo.
- **Jurisdiction is fixed to National (India)** for now, matching current
  project scope — the international toggle can be added later by extending
  `backend/main.py`'s `/api/query` with a `jurisdiction` field once
  international-treaty sources are added to the corpus.
- No authentication, rate limiting, or persistence (chat history is
  in-memory in the browser tab only) — fine for a local MVP demo, not for a
  public deployment.
