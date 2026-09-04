# IP-SAKTI Sahayak

A RAG-based, **source-cited** AI assistant for Intellectual Property and regulatory guidance
in Ayurveda — built for **SIH 2026 (internal round)**.

Ask an IP or regulatory question about an Ayurvedic product and the assistant classifies the
formulation, retrieves the governing provisions from a curated corpus of Indian statutes,
rules and registry material, and answers with a four-step reasoning trail where **every step
cites a real source**. If the corpus does not cover the question, it says so rather than
guessing.

> **Information, not legal advice.** This tool surfaces and cites primary legal material.
> It is not a substitute for a qualified IP practitioner.

---

## Quick start

**Prerequisites:** Python 3.11+, Node 18+ (for the frontend, from Phase 6), and an
[OpenRouter API key](https://openrouter.ai/keys).

```
# 1. Dependencies
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r pipeline\requirements.txt

# 2. API key
copy .env.example .env
#    then edit .env and set OPENROUTER_API_KEY=sk-or-v1-...

# 3. Build the vector database
#    First run downloads the embedding model (~1.1 GB) and takes a few minutes.
.venv\Scripts\python.exe pipeline\build_vector_db.py

# 4. Sanity-check retrieval
.venv\Scripts\python.exe pipeline\test_retrieval.py
```

On macOS/Linux substitute `.venv/bin/python` and `cp` for `copy`.

---

## Project layout

| Path | What it holds |
|---|---|
| `backend/app/` | FastAPI service: classification, retrieval, generation, citation validation |
| `pipeline/` | Corpus ingestion — PDF extraction, chunking, embedding |
| `data/` | `corpus.zip` (26 source PDFs), extracted chunks, ChromaDB index |
| `frontend/` | React + Tailwind UI |
| `tests/` | Benchmark and robustness suites |
| `docs/` | Pipeline and vector-DB notes |

**`CLAUDE.md` is the shared context file** — architecture, corpus quirks, stack decisions and
phase status. Read it before contributing; it is kept current with every phase.

---

## The corpus

**2,342 chunks** extracted from **26 Indian legal and regulatory PDFs**, spanning:

- **Classification** — Drugs & Cosmetics Act 1940 + Rules 1945, FSSAI Ayurveda Aahar Regulations
- **National IP statutes** — Patents Act 1970 + Rules 2024, GI Act 1999, Trade Marks Act 1999,
  Designs Act 2000, Copyright Act 1957, Plant Varieties Act 2001, Biological Diversity Act 2002
  (+ 2023 Amendment, 2024 Rules), Drugs and Magic Remedies Act 1954
- **Registries** — TKDL access policy, Manual of Patent Office Practice, GI Journal examples,
  NBA/ABS guidelines
- **Pharmacopoeia** — Ayurvedic Pharmacopoeia of India Vol-I, Ayurvedic Formulary of India

Regenerable end to end from `data/corpus.zip`:

```
.venv\Scripts\python.exe pipeline\build_chunks.py      # PDFs  -> chunks
.venv\Scripts\python.exe pipeline\build_vector_db.py   # chunks -> embeddings
```

> `build_chunks.py` wipes and regenerates `data/raw_text`, `data/chunks` and `data/logs` on
> every run. The committed `data/chunks/all_chunks.json` is the shared artifact — you do not
> need to rebuild it unless the corpus itself changes.

---

## Stack

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI |
| Vector DB | ChromaDB (local, persistent) |
| Embeddings | `intfloat/multilingual-e5-base` (local, no API key) |
| Retrieval | Hybrid — dense vectors + BM25, fused with Reciprocal Rank Fusion |
| Generation | OpenRouter (`minimax/minimax-m3:free`; upgradeable to `anthropic/claude-sonnet-5`) |
| Frontend | React + Tailwind |

Three of these deliberately differ from the baseline in `PROJECT_BRIEF.md` Part D. The
reasoning for each is documented in `CLAUDE.md` §4.

---

## How hallucination is prevented

Citation accuracy is the graded criterion, so it is enforced structurally rather than trusted:

1. **Grounded prompting** — the model answers only from the evidence chunks passed to it.
2. **Post-generation validation** — every citation ID returned by the model is checked against
   the set of chunks actually retrieved. An ID that was not retrieved is rejected, not warned about.
3. **Forced abstention** — if a reasoning step ends up with no valid citation, it is replaced
   with an explicit statement of insufficient evidence rather than shipped unsourced.

---

## Team

- **Person A** — backend: corpus processing, classification, retrieval, generation, API
- **Person B** — frontend: UI, reasoning-trail and citation components, integration, polish
