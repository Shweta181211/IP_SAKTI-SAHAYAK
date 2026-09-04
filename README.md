# IP Sakti Sahayak

> Citation-grounded Indian IP and regulatory research for Ayurveda products.

IP Sakti Sahayak is a local Retrieval-Augmented Generation (RAG) prototype for
researching Indian Ayurveda-product questions. It retrieves passages from a
curated legal and regulatory corpus, displays the exact source metadata, and
does not invent an answer when the evidence is weak.

**This is an informational research tool, not legal advice.** Always verify a
result against the cited primary source before relying on it.

## Highlights

- One-command local website: FastAPI serves both the API and browser UI.
- 2,335 locally indexed corpus chunks from Indian IP, biodiversity, drug,
  cosmetic, food-regulatory and pharmacopoeial material.
- English and Hindi query support, including Hindi legal-term expansion.
- Formulation-aware retrieval for classical, proprietary, new-drug,
  phytopharmaceutical, Ayurveda-Aahar and cosmetic contexts.
- Confidence scoring and safe abstention when retrieved evidence is weak.
- Source cards showing Act, section/clause, page, regime and similarity
  distance for every retrieved passage.
- ABS/TKDL prompts for biological-resource and traditional-knowledge queries.
- Optional local audit logging with a per-session opt-out.
- Optional Anthropic-grounded summary mode; it falls back safely to retrieval
  summaries if a key or model call is unavailable.

## Architecture

```text
Browser UI (HTML / CSS / JavaScript)
            │  /api/query
            ▼
FastAPI + RAG orchestration
            │
Query routing → multilingual embeddings → Chroma vector search
            │                                      │
            └──── confidence / citations / ABS-TKDL ┘
                           ▼
                    cited response + source cards
```

## Quick start

### 1. Requirements

- Python 3.9 or later (Python 3.10+ recommended)
- Internet access only for the first model download, if `vector_db/` has not
  been built yet

### 2. Create an environment and install packages

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Build the local vector database (first run only)

```bash
python build_vector_db.py
```

This downloads the multilingual embedding model on its first run and creates
`vector_db/`. The shipped `all_chunks.json` is the input corpus artifact.

### 4. Start the app

```bash
python -m uvicorn backend.main:app --reload
```

Open <http://127.0.0.1:8000>.

To stop the server, press `Ctrl+C` in the terminal.

## Optional LLM summaries

The default experience is fully usable without an API key: it returns a
careful retrieval-based summary. To enable the UI's LLM synthesis toggle:

```bash
cp .env.example .env
# Add your key as: ANTHROPIC_API_KEY=...
```

Never commit `.env`; it is ignored by Git.

## Quality checks

```bash
# Runs the English/Hindi retrieval and safe-abstention evaluation set.
python run_eval.py

# Prints retrieval examples and source metadata.
python test_retrieval.py
```

The evaluation report is written to `eval_report.json`, which is intentionally
not tracked because it is a generated local artifact.

## Repository layout

```text
backend/              FastAPI routes and RAG orchestration
frontend/             dependency-free browser UI
all_chunks.json       curated chunk corpus used to build the index
build_vector_db.py    local Chroma index builder
test_retrieval.py     reusable retrieval and sanity checks
run_eval.py           labelled EN/HI evaluation harness
eval_set.json         evaluation cases
WEBSITE_GUIDE.md      detailed UI and operating guide
```

The raw PDF source bundle is intentionally excluded from the GitHub-ready
package. It is only needed to re-run PDF extraction; the included chunk corpus
is sufficient to build and run the application.

## Scope and limitations

- The current corpus is limited to India; it does not provide international
  treaty analysis.
- English and Hindi are supported; this is not a full translation system.
- Confidence thresholds are heuristic starting points and should be calibrated
  using real, consented evaluation data before any production use.
- The local audit log is an MVP privacy control, not a complete DPDP compliance
  programme.

## Demo questions

- `Can I patent a new extraction process for Ashwagandha?`
- `Do I need NBA approval to export a herbal cosmetic made from Indian plants?`
- `मुझे अपने आयुर्वेदिक उत्पाद का ट्रेडमार्क कैसे कराना है?`
